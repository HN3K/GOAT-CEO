"""Partition-manifest validator for agent-workspace/IMPLEMENTATION-MANIFEST.json.

Enforces the disjoint-partition contract the speculative-batch reconvergence stage
relies on (protocols.md §D, GOAT-CEO-REWORK-DESIGN.md §D). The integrate stage merges
all independent batches together and tests once - that is only safe if independent
batches (`blockedBy == []`) have genuinely non-overlapping `files[]`.

Dual-mode:
  - SubagentStop hook (team-architect): reads the hook JSON from stdin. If the architect
    is stopping and IMPLEMENTATION-MANIFEST.json exists but is INVALID, exit 2 to block
    the stop with an actionable message. Other roles / absent manifest -> exit 0.
  - CLI (no stdin, e.g. `python .claude/hooks/check_partition.py`): validate the manifest
    and print a human verdict. Exit 0 valid, 1 invalid. The CEO runs this when verifying
    the research gate before writing RESEARCH.GATE.

Design contract: FAIL-OPEN as a hook - any UNEXPECTED internal error exits 0 so a bug
never blocks legitimate work. A manifest that is ABSENT is not an error (a session with
no parallel batches need not emit one) -> allow. Only a PRESENT-but-INVALID partition
blocks. Dependency-free (stdlib only).

Validation rules:
  1. JSON parses and has a list `batches`.
  2. Each batch has a unique `id` and a list `files`.
  3. Every independent batch (no `dependsOn`/`blockedBy`) is pairwise NON-OVERLAPPING with
     every other independent batch, where overlap is computed over NORMALIZED file AND
     directory claims and includes DIRECTORY-CONTAINMENT (batch A's dir `src/` overlaps
     batch B's file `src/foo.py` or its dir `src/sub/`).
  4. Every `dependsOn`/`blockedBy` entry references an existing batch id.
  5. (v2, HARD) No `sharedResources` entry may be claimed by more than one batch.
  6. (v2, HARD) A batch (or the manifest) with `requiresCoordinator: true` must name a
     coordinator (`coordinatorBatch` at the manifest level, or `coordinator`/
     `coordinatorBatch` on the batch) that resolves to an existing batch id.
  7. `coordinatorBatch`, if set, must name an existing batch (HARD). Legacy
     `ownsSharedResources` consistency stays advisory.

Path normalization (rule 3 & 5): casefold (case-insensitive FS), strip leading `./`,
collapse `\` to `/`, collapse repeated `/`, strip a trailing `/` for comparison.

Back-compat: v1 manifests (only `files[]`, `blockedBy`, `coordinatorBatch`) validate
unchanged. v2 adds `directories[]`, `sharedResources[]`, `requiresCoordinator`, and a
`conflictPolicy` object (the last is descriptive metadata; not enforced beyond parsing).
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST_PATH = os.path.join(REPO_ROOT, "agent-workspace", "IMPLEMENTATION-MANIFEST.json")


def _norm_path(p):
    """Normalize a path for case/separator/`./`-insensitive comparison."""
    if not isinstance(p, str):
        return ""
    s = p.strip().replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    while "//" in s:
        s = s.replace("//", "/")
    s = s.rstrip("/")
    return s.casefold()


def _deps(b):
    """Dependency edges for a batch — supports both v2 `dependsOn` and v1 `blockedBy`."""
    out = []
    for key in ("dependsOn", "blockedBy"):
        v = b.get(key)
        if isinstance(v, list):
            out.extend(v)
    return out


def _is_contained(child, parent):
    """True if normalized path `child` is the same as, or lives under, directory `parent`."""
    if not child or not parent:
        return False
    return child == parent or child.startswith(parent + "/")


def _claims(b):
    """Return (files_set, dirs_set) of normalized path claims for a batch."""
    files = {_norm_path(f) for f in (b.get("files") or []) if _norm_path(f)}
    dirs = {_norm_path(d) for d in (b.get("directories") or []) if _norm_path(d)}
    return files, dirs


def _overlap(a, c):
    """Normalized overlap between two batches: shared files/dirs AND dir-containment."""
    fa, da = _claims(a)
    fc, dc = _claims(c)
    hits = set()
    # Direct file/dir name collisions.
    hits |= (fa & fc)
    hits |= (da & dc)
    # Directory containment: a's directory contains c's file or dir (and vice-versa).
    for d in da:
        for p in (fc | dc):
            if _is_contained(p, d):
                hits.add(p)
    for d in dc:
        for p in (fa | da):
            if _is_contained(p, d):
                hits.add(p)
    return hits


def validate(manifest):
    """Return (errors, warnings) lists. errors are hard (block); warnings are advisory."""
    errors = []
    warnings = []

    batches = manifest.get("batches")
    if not isinstance(batches, list):
        return (["'batches' is missing or not a list"], warnings)

    ids = []
    for i, b in enumerate(batches):
        if not isinstance(b, dict):
            errors.append("batch #{} is not an object".format(i))
            continue
        bid = b.get("id")
        if not bid:
            errors.append("batch #{} has no 'id'".format(i))
        else:
            ids.append(bid)
        if not isinstance(b.get("files", []), list):
            errors.append("batch '{}' has a non-list 'files'".format(bid))
        if not isinstance(b.get("directories", []), list):
            errors.append("batch '{}' has a non-list 'directories'".format(bid))

    dupe = set(x for x in ids if ids.count(x) > 1)
    if dupe:
        errors.append("duplicate batch ids: {}".format(", ".join(sorted(dupe))))

    id_set = set(ids)

    # Rule 4 - dependency references resolve (dependsOn or blockedBy).
    for b in batches:
        if not isinstance(b, dict):
            continue
        for dep in _deps(b):
            if dep not in id_set:
                errors.append(
                    "batch '{}' depends on unknown id '{}'".format(b.get("id"), dep)
                )

    # Rule 3 - independent batches must be pairwise non-overlapping (normalized + dir-contain).
    independent = [
        b for b in batches
        if isinstance(b, dict) and not _deps(b)
    ]
    for i in range(len(independent)):
        for j in range(i + 1, len(independent)):
            a, c = independent[i], independent[j]
            overlap = _overlap(a, c)
            if overlap:
                errors.append(
                    "independent batches '{}' and '{}' overlap on path(s): {} "
                    "(file/dir collision or directory-containment; independent batches merge "
                    "together and test once - they MUST be disjoint; give one a dependsOn the "
                    "other, or merge them).".format(
                        a.get("id"), c.get("id"), ", ".join(sorted(overlap))
                    )
                )

    # Rule 5 (v2, HARD) - no sharedResource claimed by more than one batch.
    shared_claims = {}
    for b in batches:
        if not isinstance(b, dict):
            continue
        for res in (b.get("sharedResources") or []):
            key = _norm_path(res) if isinstance(res, str) else None
            if not key:
                continue
            shared_claims.setdefault(key, []).append(b.get("id"))
    for res, claimants in shared_claims.items():
        if len(claimants) > 1:
            errors.append(
                "sharedResource '{}' is claimed by more than one batch ({}); a shared "
                "resource must have a single owner.".format(res, ", ".join(str(x) for x in claimants))
            )

    # Rule 7 (HARD) - coordinatorBatch, if set, must resolve.
    coordinator = manifest.get("coordinatorBatch")
    if coordinator and coordinator not in id_set:
        errors.append("coordinatorBatch '{}' is not an existing batch id".format(coordinator))

    # Rule 6 (v2, HARD) - requiresCoordinator:true demands a declared, resolvable coordinator.
    def _has_resolvable_coordinator(batch=None):
        cands = [coordinator]
        if batch is not None:
            cands += [batch.get("coordinator"), batch.get("coordinatorBatch")]
        return any(c and c in id_set for c in cands)

    if manifest.get("requiresCoordinator") is True and not _has_resolvable_coordinator():
        errors.append(
            "manifest sets requiresCoordinator:true but declares no coordinatorBatch that "
            "resolves to an existing batch id."
        )
    for b in batches:
        if isinstance(b, dict) and b.get("requiresCoordinator") is True:
            if not _has_resolvable_coordinator(b):
                errors.append(
                    "batch '{}' sets requiresCoordinator:true but no coordinator "
                    "(batch.coordinator / manifest.coordinatorBatch) resolves to an "
                    "existing batch id.".format(b.get("id"))
                )

    # Legacy advisory - ownsSharedResources consistency.
    owners = [b.get("id") for b in batches if isinstance(b, dict) and b.get("ownsSharedResources")]
    if len(owners) > 1:
        warnings.append("more than one batch sets ownsSharedResources: {}".format(", ".join(owners)))
    if coordinator and owners and coordinator not in owners:
        warnings.append(
            "coordinatorBatch '{}' is not the batch that ownsSharedResources ({})".format(
                coordinator, ", ".join(owners)
            )
        )

    return (errors, warnings)


def run_hook(raw):
    """SubagentStop mode. exit 2 blocks the architect's stop on an invalid manifest."""
    data = json.loads(raw) if raw.strip() else {}
    agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
    if agent_type != "team-architect":
        return 0  # only gate the architect's partition output
    if not os.path.exists(MANIFEST_PATH):
        return 0  # no partition emitted (e.g. single-batch run) - not an error
    with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)  # a JSONDecodeError here is a real fault -> blocks below
    errors, _ = validate(manifest)
    if errors:
        # Guard the write so an I/O/encoding failure can never downgrade a real block to
        # an allow (the surrounding fail-open would otherwise turn exit 2 into exit 0).
        try:
            sys.stderr.write(
                "PARTITION INVALID (IMPLEMENTATION-MANIFEST.json) - the reconvergence stage "
                "cannot rely on this partition. Fix and re-emit before ending your turn:\n- "
                + "\n- ".join(errors)
            )
        except Exception:
            pass
        return 2
    return 0


def run_cli():
    """CLI mode for the CEO at the research gate. exit 0 valid, 1 invalid."""
    if not os.path.exists(MANIFEST_PATH):
        print("PARTITION: no IMPLEMENTATION-MANIFEST.json present (OK if this run has no parallel batches).")
        return 0
    try:
        with open(MANIFEST_PATH, "r", encoding="utf-8") as fh:
            manifest = json.load(fh)
    except (OSError, ValueError) as exc:
        print("PARTITION INVALID: cannot parse IMPLEMENTATION-MANIFEST.json: {}".format(exc))
        return 1
    errors, warnings = validate(manifest)
    for w in warnings:
        print("PARTITION WARNING: {}".format(w))
    if errors:
        print("PARTITION INVALID:")
        for e in errors:
            print("  - {}".format(e))
        return 1
    n = len(manifest.get("batches", []))
    print("PARTITION OK: {} batch(es), independent batches are file-disjoint.".format(n))
    return 0


def main():
    # Capture stdin once. A tty (interactive CEO) is never read (would block); piped
    # stdin is read. Hook mode iff the piped data is non-empty (Claude Code sends the
    # event JSON). Empty/no stdin -> CLI mode (the CEO running it via a shell).
    try:
        raw = "" if sys.stdin.isatty() else sys.stdin.read()
    except Exception:
        raw = ""

    try:
        if raw.strip():
            return run_hook(raw)
        return run_cli()
    except Exception:
        # FAIL-OPEN as a hook: an unexpected bug must never block legitimate work.
        return 0


if __name__ == "__main__":
    sys.exit(main())
