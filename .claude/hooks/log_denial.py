"""PermissionDenied hook: audit trail for denied actions.

Appends every denied tool call to agent-workspace/DENIAL-LOG.txt so the CEO
can review patterns, diagnose mis-fires, and tune deny rules.

Non-blocking (async in settings.json): always exits 0.

Design contract: FAIL-OPEN on any internal error.  Always exit 0.
"""
import json
import os
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
LOG_FILE = os.path.join(WORKSPACE, "DENIAL-LOG.txt")


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        tool_name = data.get("tool_name", "unknown")
        tool_input = data.get("tool_input", {})
        agent_type = data.get("agent_type") or data.get("subagent_type") or "main-session"
        reason = data.get("denial_reason", "")

        # Summarize the denied command (truncated to avoid huge log entries)
        command = ""
        if isinstance(tool_input, dict):
            command = str(tool_input.get("command") or tool_input.get("file_path") or "")[:200]

        ts = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        entry = "[{}] DENIED tool={} role={} command={!r} reason={!r}\n".format(
            ts, tool_name, agent_type, command, reason
        )

        os.makedirs(WORKSPACE, exist_ok=True)
        with open(LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(entry)

        return 0
    except Exception:
        return 0  # fail open — logging must never block work


if __name__ == "__main__":
    sys.exit(main())
