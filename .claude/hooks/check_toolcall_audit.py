"""TaskCompleted hook: reviewer tool-call audit.

Blocks a verifier task from closing if the verifier issued a verdict without
reading a minimum number of implementation files.  A reviewer who writes
REVIEW-LOG.md without reading files is a hallucination vector (equivalent of
mock-only testing).

Minimum thresholds:
    Read / Grep / Bash calls combined: >= MIN_READ_CALLS (default: 5)

The hook reads the session transcript JSONL to count file-reading tool calls
made by this agent in its current session.  If the transcript is unavailable
(e.g. path not found), the hook fails open.

Transcript location: Claude Code writes session JSONL under:
    %APPDATA%/Claude/projects/<hash>/sessions/<session-id>.jsonl
or on non-Windows:
    ~/.claude/projects/<hash>/sessions/<session-id>.jsonl

We look at CLAUDE_PROJECT_DIR env var first, then fall back to searching the
most recently modified JSONL under ~/.claude/projects/.

Design contract: FAIL-OPEN on any internal error.
exit 0 = allow; exit 2 = BLOCK (stderr shown to agent).
"""
import glob
import json
import os
import sys

MIN_READ_CALLS = 5
READ_TOOL_NAMES = {"Read", "Grep", "Bash", "Glob"}
GATED_ROLES = {"team-verifier"}


def _find_latest_session_jsonl() -> str | None:
    """Return path to the most recently modified session JSONL, or None."""
    # Try common Claude Code session log locations
    candidates = []
    search_roots = []

    appdata = os.environ.get("APPDATA", "")
    home = os.path.expanduser("~")

    for root in [
        os.path.join(appdata, "Claude", "projects"),
        os.path.join(home, ".claude", "projects"),
    ]:
        if os.path.isdir(root):
            search_roots.append(root)

    for root in search_roots:
        pattern = os.path.join(root, "**", "sessions", "*.jsonl")
        candidates.extend(glob.glob(pattern, recursive=True))

    if not candidates:
        return None

    # Most recently modified file is the active session
    return max(candidates, key=os.path.getmtime)


def _count_read_calls(jsonl_path: str) -> int:
    """Count Read/Grep/Bash/Glob tool calls in the session transcript."""
    count = 0
    try:
        with open(jsonl_path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Look for tool_use events
                tool = event.get("type", "") or event.get("event_type", "")
                if tool in ("tool_use", "tool_call"):
                    tool_name = event.get("name", "") or event.get("tool_name", "")
                    if tool_name in READ_TOOL_NAMES:
                        count += 1
                # Also handle nested content blocks (some transcript formats)
                for block in event.get("content", []) or []:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        if block.get("name", "") in READ_TOOL_NAMES:
                            count += 1
    except (OSError, IOError):
        pass
    return count


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if agent_type not in GATED_ROLES:
            return 0

        jsonl_path = _find_latest_session_jsonl()
        if not jsonl_path:
            # Transcript not found — fail open, but warn
            sys.stderr.write(
                "WARNING (check_toolcall_audit): session transcript not found. "
                "Tool-call audit cannot verify reviewer read count. "
                "Failing open — ensure the reviewer genuinely read implementation files."
            )
            return 0

        read_count = _count_read_calls(jsonl_path)

        if read_count < MIN_READ_CALLS:
            sys.stderr.write(
                "TOOL-CALL AUDIT BLOCK: reviewer issued a verdict after only {} "
                "file-read tool calls (minimum: {}). "
                "A verdict without reading implementation files is a hallucination "
                "vector. Read the actual changed files, grep for usage, run at least "
                "one runtime check the implementer did NOT report, "
                "then re-issue your verdict.".format(read_count, MIN_READ_CALLS)
            )
            return 2

        return 0
    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
