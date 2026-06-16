"""SubagentStop hook: reviewer tool-call audit.

Blocks a REVIEWER (a `team-verifier` that produced a "reviewer":"A"/"B" verdict) from
stopping if it issued its verdict after fewer than MIN_READ_CALLS file-reading tool
calls. A reviewer that writes a verdict without reading the implementation is a
hallucination vector — the review equivalent of mock-only testing.

Why SubagentStop (not TaskCompleted): TaskCompleted does NOT fire for Workflow-spawned
agents, so the audit was dead under the Workflow execution substrate. SubagentStop fires
in BOTH the agent-teams and Workflow substrates, and its payload carries
`agent_transcript_path` — THIS subagent's OWN transcript — so the read count is precise.
The previous version scanned "the most recently modified session JSONL", which counted
ANY agent's reads (could be the CEO's), inflating or misattributing the count.

Only actual reviewers (A/B) are gated. The completeness-critic and judge are also
`team-verifier` but legitimately read fewer files, so they are EXEMPTED by requiring the
reviewer verdict marker `"reviewer": "A"|"B"` to be present before enforcing the minimum.

Design contract: FAIL-OPEN on any internal error. exit 0 = allow stop; exit 2 = BLOCK
(stderr shown to the agent). Dependency-free (stdlib only).
"""
import glob as _glob
import json
import os
import re
import subprocess
import sys

# Central GOAT-CEO workspace (this hook lives in .claude/hooks/, so REPO_ROOT is
# three dirs up). The batch baseline / implementer evidence often lives HERE rather
# than in the reviewer's own worktree, so the changed-set derivation consults it.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")

MIN_READ_CALLS = 5
# C6: of the reviewer's path-bearing reads, at least this many must land in the
# changed-file set (the actual diff under review), not just any 5 tool calls.
MIN_DIFF_READS = 3
READ_TOOL_NAMES = {"Read", "Grep", "Bash", "Glob"}
# Tools whose tool_input carries a file path we can match against the diff.
PATH_TOOL_NAMES = {"Read", "Grep"}
GATED_ROLES = {"team-verifier"}
# A reviewer (not judge/critic) emits a verdict block with "reviewer": "A" or "B".
# Decoded form (matched against decoded text content + last_assistant_message):
REVIEWER_MARKER = re.compile(r'"reviewer"\s*:\s*"(A|B)"')
# Escape-tolerant form (matched against the RAW transcript bytes, where the verdict block
# lives inside a JSON string so its quotes are backslash-escaped):
REVIEWER_MARKER_RAW = re.compile(r'\\?"reviewer\\?"\s*:\s*\\?"(A|B)\\?"')


def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, IOError):
        return None


def _iter_tool_uses(event):
    """Yield (name, tool_input) for any tool_use blocks in an event (several formats).

    tool_input is the input dict if present (Read/Grep carry a file path there), else {}.
    Existing callers that only need the name can ignore the second element."""
    t = event.get("type", "") or event.get("event_type", "")
    if t in ("tool_use", "tool_call"):
        yield (
            event.get("name", "") or event.get("tool_name", ""),
            event.get("input") or event.get("tool_input") or {},
        )
    for block in event.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            yield (block.get("name", ""), block.get("input") or {})
    msg = event.get("message")
    if isinstance(msg, dict):
        for block in msg.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield (block.get("name", ""), block.get("input") or {})


def _read_path_from_input(name, tinput):
    """Extract a candidate file path from a Read/Grep tool_input (best-effort)."""
    if not isinstance(tinput, dict):
        return None
    if name == "Read":
        return tinput.get("file_path") or tinput.get("path")
    if name == "Grep":
        # Grep's `path` may be a dir; still useful for containment matching.
        return tinput.get("path")
    return None


def _norm_rel(p, cwd):
    """Normalize a path to a cwd-relative, forward-slash, casefolded form for matching."""
    if not p or not isinstance(p, str):
        return ""
    s = p.strip().replace("\\", "/")
    cwdn = (cwd or "").replace("\\", "/").rstrip("/")
    if cwdn and s.casefold().startswith(cwdn.casefold() + "/"):
        s = s[len(cwdn) + 1:]
    while s.startswith("./"):
        s = s[2:]
    while "//" in s:
        s = s.replace("//", "/")
    return s.strip("/").casefold()


def _read_json(path):
    try:
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            return None
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _changed_from_results():
    """Union of `changedFiles` across central IMPLEMENTER-RESULT*.json. Set or None.

    The implementer's own declared diff — the most direct, git-free source of the
    change under review."""
    files = set()
    for path in _glob.glob(os.path.join(WORKSPACE, "IMPLEMENTER-RESULT*.json")):
        obj = _read_json(path)
        if not isinstance(obj, dict):
            continue
        changed = obj.get("changedFiles")
        if isinstance(changed, list):
            for p in changed:
                if isinstance(p, str) and p.strip():
                    files.add(p)
    return files or None


def _changed_from_manifest():
    """Union of every batch's `files[]` in central IMPLEMENTATION-MANIFEST.json.

    The declared change scope for the whole partition. Used when no per-batch
    implementer result is available."""
    obj = _read_json(os.path.join(WORKSPACE, "IMPLEMENTATION-MANIFEST.json"))
    if not isinstance(obj, dict):
        return None
    batches = obj.get("batches")
    if not isinstance(batches, list):
        return None
    files = set()
    for b in batches:
        if not isinstance(b, dict):
            continue
        for p in b.get("files") or []:
            if isinstance(p, str) and p.strip():
                files.add(p)
    return files or None


def _baseline_from(path):
    """First whitespace-delimited token of a BASELINE.txt at `path`, or None."""
    try:
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            cand = fh.read().strip().split()
        return cand[0] if cand else None
    except OSError:
        return None


def _changed_from_git(cwd):
    """git diff <baseline>..HEAD in `cwd`, where the baseline comes from BASELINE.txt
    under the reviewer cwd OR the central GOAT-CEO agent-workspace/. Set or None.

    We do NOT guess HEAD~1..HEAD without a real baseline — on a multi-commit batch that
    yields a too-narrow diff and would false-BLOCK a reviewer who read the real changes (F1)."""
    if not cwd or not os.path.isdir(cwd):
        return None
    baseline = (
        _baseline_from(os.path.join(cwd, "agent-workspace", "BASELINE.txt"))
        or _baseline_from(os.path.join(WORKSPACE, "BASELINE.txt"))
    )
    if not baseline:
        return None
    try:
        proc = subprocess.run(
            ["git", "-C", cwd, "diff", "--name-only", baseline + "..HEAD"],
            capture_output=True, text=True, timeout=15,
        )
    except Exception:
        return None
    if proc.returncode != 0:
        return None
    changed = {_norm_rel(line, cwd) for line in (proc.stdout or "").splitlines() if line.strip()}
    changed.discard("")
    return changed or None


def _changed_set(cwd):
    """Return a set of normalized changed paths, or None if undeterminable.

    Source order — first that yields a non-empty set wins (C6 fallback chain). The
    real batch baseline frequently lives in the CENTRAL GOAT-CEO agent-workspace/ rather
    than the reviewer's worktree, so relying on a single cwd-local BASELINE.txt
    degraded the diff-tied check to the bare name-count floor too often:
      1. central IMPLEMENTER-RESULT*.json `changedFiles` (implementer's declared diff);
      2. central IMPLEMENTATION-MANIFEST.json batch `files[]` (declared change scope);
      3. git diff against a BASELINE.txt (reviewer cwd, then central workspace).
    Only None (caller fail-soft to the name floor) if every source is empty."""
    try:
        for source in (_changed_from_results, _changed_from_manifest):
            raw = source()
            if raw:
                norm = {_norm_rel(p, cwd) for p in raw}
                norm.discard("")
                if norm:
                    return norm
        return _changed_from_git(cwd)
    except Exception:
        return None


def _iter_texts(event):
    """Yield decoded text-block strings from a transcript event."""
    for block in event.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "text":
            yield block.get("text", "") or ""
    msg = event.get("message")
    if isinstance(msg, dict):
        for block in msg.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                yield block.get("text", "") or ""


def _scan(text):
    """Single pass over the transcript: return (read_call_count, is_reviewer, read_paths).

    read_paths is the list of file paths pulled from Read/Grep tool_input calls (for C6
    diff-tied matching). is_reviewer is true if a "reviewer":"A"/"B" verdict marker appears
    in DECODED text content (preferred) or in the raw bytes (escape-tolerant fallback)."""
    read_count = 0
    read_paths = []
    is_reviewer = bool(REVIEWER_MARKER_RAW.search(text))  # raw-bytes fallback
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        for name, tinput in _iter_tool_uses(event):
            if name in READ_TOOL_NAMES:
                read_count += 1
            if name in PATH_TOOL_NAMES:
                p = _read_path_from_input(name, tinput)
                if p:
                    read_paths.append(p)
        if not is_reviewer:
            for txt in _iter_texts(event):
                if REVIEWER_MARKER.search(txt):
                    is_reviewer = True
                    break
    return read_count, is_reviewer, read_paths


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if agent_type not in GATED_ROLES:
            return 0

        tpath = data.get("agent_transcript_path", "") or data.get("transcript_path", "")
        if not tpath or not os.path.exists(tpath):
            sys.stderr.write(
                "WARNING (check_toolcall_audit): no readable agent_transcript_path; cannot "
                "verify reviewer read count. Failing open."
            )
            return 0

        text = _read_text(tpath)
        if text is None:
            return 0  # unreadable — fail open

        read_count, is_reviewer, read_paths = _scan(text)
        # last_assistant_message is already decoded in the payload — check it too.
        last_msg = str(data.get("last_assistant_message", "") or "")
        if not is_reviewer and REVIEWER_MARKER.search(last_msg):
            is_reviewer = True

        # Gate ONLY actual reviewers (A/B). Exempt judge/critic/other verifiers, which are
        # the same agent_type but legitimately read fewer files.
        if not is_reviewer:
            return 0

        # First floor: bare count of file-reading tool calls (cheap, catches the obvious
        # "verdict with no reads" case).
        if read_count < MIN_READ_CALLS:
            try:
                sys.stderr.write(
                    "TOOL-CALL AUDIT BLOCK: reviewer issued a verdict after only {} file-read "
                    "tool calls (minimum: {}). A verdict without reading the implementation is a "
                    "hallucination vector. Read the actual changed files, grep for usage, run at "
                    "least one runtime check the implementer did NOT report, then re-issue your "
                    "verdict before ending your turn.".format(read_count, MIN_READ_CALLS)
                )
            except Exception:
                pass  # never let an I/O failure downgrade a block to an allow
            return 2

        # C6 — tie the read-floor to the actual diff. The name-count above is gameable with
        # 5 unrelated reads, so additionally require that several of the reviewer's reads land
        # on files that are actually in the changed set. If the changed set cannot be
        # determined (no git, detached, no diff, no cwd), FAIL SOFT to the name-count above.
        cwd = data.get("cwd", "") or ""
        changed = _changed_set(cwd)
        if changed:
            # Count the reviewer's Read/Grep CALLS that landed on a changed file. A call
            # hits the diff if its normalized path equals a changed path, or (a directory
            # grep) contains a changed path. This ties the floor to the actual diff so 5
            # unrelated reads no longer satisfy it.
            hits = 0
            for p in read_paths:
                rp = _norm_rel(p, cwd)
                if not rp:
                    continue
                if rp in changed or any(
                    cf == rp or cf.startswith(rp + "/") for cf in changed
                ):
                    hits += 1
            if hits < MIN_DIFF_READS:
                try:
                    sys.stderr.write(
                        "TOOL-CALL AUDIT BLOCK: reviewer's reads do not cover the change under "
                        "review — only {} of your file reads hit the changed set (minimum: {}). "
                        "Counting unrelated reads does not constitute reviewing THIS diff. Open "
                        "the actual changed files (git diff), grep for their usage, run a check "
                        "the implementer did NOT report, then re-issue your verdict.".format(
                            hits, MIN_DIFF_READS
                        )
                    )
                except Exception:
                    pass  # never let an I/O failure downgrade a block to an allow
                return 2

        return 0
    except Exception:
        return 0  # fail open — a hook bug must never block legitimate work


if __name__ == "__main__":
    sys.exit(main())
