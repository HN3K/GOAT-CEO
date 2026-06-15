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
import json
import os
import re
import sys

MIN_READ_CALLS = 5
READ_TOOL_NAMES = {"Read", "Grep", "Bash", "Glob"}
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
    """Yield tool names for any tool_use blocks in a transcript event (several formats)."""
    t = event.get("type", "") or event.get("event_type", "")
    if t in ("tool_use", "tool_call"):
        yield event.get("name", "") or event.get("tool_name", "")
    for block in event.get("content", []) or []:
        if isinstance(block, dict) and block.get("type") == "tool_use":
            yield block.get("name", "")
    msg = event.get("message")
    if isinstance(msg, dict):
        for block in msg.get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                yield block.get("name", "")


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
    """Single pass over the transcript: return (read_call_count, is_reviewer).

    is_reviewer is true if a "reviewer":"A"/"B" verdict marker appears in DECODED text
    content (preferred) or in the raw bytes via the escape-tolerant pattern (fallback)."""
    read_count = 0
    is_reviewer = bool(REVIEWER_MARKER_RAW.search(text))  # raw-bytes fallback
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        for name in _iter_tool_uses(event):
            if name in READ_TOOL_NAMES:
                read_count += 1
        if not is_reviewer:
            for txt in _iter_texts(event):
                if REVIEWER_MARKER.search(txt):
                    is_reviewer = True
                    break
    return read_count, is_reviewer


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

        read_count, is_reviewer = _scan(text)
        # last_assistant_message is already decoded in the payload — check it too.
        last_msg = str(data.get("last_assistant_message", "") or "")
        if not is_reviewer and REVIEWER_MARKER.search(last_msg):
            is_reviewer = True

        # Gate ONLY actual reviewers (A/B). Exempt judge/critic/other verifiers, which are
        # the same agent_type but legitimately read fewer files.
        if not is_reviewer:
            return 0

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

        return 0
    except Exception:
        return 0  # fail open — a hook bug must never block legitimate work


if __name__ == "__main__":
    sys.exit(main())
