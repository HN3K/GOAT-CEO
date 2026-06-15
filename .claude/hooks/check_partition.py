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
  3. Every independent batch (`blockedBy` empty/absent) has `files[]` pairwise-disjoint
     from every other independent batch.
  4. Every `blockedBy` entry references an existing batch id (no dangling/cyclic-by-typo).
  5. At most one `coordinatorBatch`; if set it must name an existing batch, and a batch
     with `ownsSharedResources: true` should be that coordinator. (Advisory - a mismatch
     is reported but, for a hook, only the disjointness rule (#3) hard-blocks.)
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MANIFEST_PATH = os.path.join(REPO_ROOT, "agent-workspace", "IMPLEMENTATION-MANIFEST.json")


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

    dupe = set(x for x in ids if ids.count(x) > 1)
    if dupe:
        errors.append("duplicate batch ids: {}".format(", ".join(sorted(dupe))))

    id_set = set(ids)

    # Rule 4 - blockedBy references resolve.
    for b in batches:
        if not isinstance(b, dict):
            continue
        for dep in (b.get("blockedBy") or []):
            if dep not in id_set:
                errors.append(
                    "batch '{}' blockedBy references unknown id '{}'".format(b.get("id"), dep)
                )

    # Rule 3 - independent batches must be pairwise file-disjoint.
    independent = [
        b for b in batches
        if isinstance(b, dict) and not (b.get("blockedBy") or [])
    ]
    for i in range(len(independent)):
        for j in range(i + 1, len(independent)):
            a, c = independent[i], independent[j]
            fa = set(a.get("files", []) or [])
            fc = set(c.get("files", []) or [])
            overlap = fa & fc
            if overlap:
                errors.append(
                    "independent batches '{}' and '{}' overlap on files: {} "
                    "(independent batches merge together and test once - they MUST be "
                    "disjoint; give one of them a blockedBy dependency on the other, or "
                    "merge them into a single batch)".format(
                        a.get("id"), c.get("id"), ", ".join(sorted(overlap))
                    )
                )

    # Rule 5 - coordinator consistency (advisory).
    coordinator = manifest.get("coordinatorBatch")
    if coordinator and coordinator not in id_set:
        warnings.append("coordinatorBatch '{}' is not an existing batch id".format(coordinator))
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
