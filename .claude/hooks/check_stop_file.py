"""PreToolUse hook: operator STOP-file kill switch.

If `agent-workspace/STOP` exists, this blocks the agent's next Bash/PowerShell/Write/Edit
at the tool boundary (faster than a turn boundary), so a runaway or marathon agent can be
halted deterministically instead of waiting for a turn to end. The orchestrator clears it
with a bare `Remove-Item`/`rm`/`del ... STOP`, which this hook explicitly allows so the CEO
can resume.

Wire at PreToolUse with matcher "Bash|PowerShell|Write|Edit". For a multi-repo CEO session
you may ALSO wire this at user scope (~/.claude/settings.json) with absolute STOP paths so
it reaches teammate sessions rooted in other repositories; in that deployment, add each
repo's `agent-workspace/STOP` to STOP_PATHS.

Contract: exit 0 = allow; exit 2 = BLOCK (stderr is shown to the agent).
Design rule: FAIL OPEN — any internal error allows the call. Keep this dependency-free.
"""
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STOP_PATHS = [os.path.join(REPO_ROOT, "agent-workspace", "STOP")]

# Allow a bare removal command (no chaining, nothing else on the line) targeting a STOP
# file so the orchestrator can clear the stop and resume.
CLEAR_STOP = re.compile(
    r"^\s*(Remove-Item|del|rm)\s+[^;&|()`$]*\bSTOP\b[^;&|()`$]*$", re.IGNORECASE
)


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        command = str((data.get("tool_input") or {}).get("command") or "")

        if command and CLEAR_STOP.match(command):
            return 0

        for stop in STOP_PATHS:
            if os.path.exists(stop):
                note = ""
                try:
                    with open(stop, "r", encoding="utf-8", errors="replace") as fh:
                        note = fh.read(500).strip()
                except OSError:
                    pass
                sys.stderr.write(
                    "OPERATOR STOP IS IN EFFECT (" + stop + "). This is NOT a recoverable "
                    "error — do not retry, do not work around it. Write a brief state note "
                    "of where you stopped, send your checkpoint message, and END YOUR TURN "
                    "now." + ("\nSTOP note: " + note if note else "")
                )
                return 2

        return 0
    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
