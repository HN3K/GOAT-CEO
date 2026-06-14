"""PreToolUse hook: destructive database operation guard.

Blocks DROP DATABASE and RESTORE DATABASE unless an approval token file
is present at agent-workspace/RESTORE-APPROVED.token.

Policy (fail-open — any exception exits 0 = allow):
  BLOCK (exit 2):
    - RESTORE DATABASE  — without approval token
    - DROP DATABASE     — without approval token
  ALLOW (exit 0):
    - RESTORE DATABASE  — token present (single-use: token is consumed after allowing)
    - DROP DATABASE     — token present (single-use: token is consumed after allowing)
    - all other commands

Token path: agent-workspace/RESTORE-APPROVED.token
  Write this file before issuing a RESTORE DATABASE or DROP DATABASE command.
  The hook consumes it (deletes it) after allowing the guarded operation — so
  each destructive operation needs its own token.

Design contract: FAIL-OPEN — any exception exits 0.
exit 0 = allow; exit 2 = BLOCK.
"""
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TOKEN_PATH = os.path.join(REPO_ROOT, "agent-workspace", "RESTORE-APPROVED.token")

DESTRUCTIVE_PATTERN = re.compile(
    r"\b(RESTORE\s+DATABASE|DROP\s+DATABASE)\b", re.IGNORECASE
)


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        cmd = data.get("tool_input", {}).get("command", "")

        if not DESTRUCTIVE_PATTERN.search(cmd):
            return 0  # not a destructive DB op — allow

        if os.path.exists(TOKEN_PATH):
            # Token present — consume it (single-use) and allow
            try:
                os.remove(TOKEN_PATH)
            except OSError:
                pass  # fail-open: if removal fails, still allow (token was present)
            return 0

        # No token — block with an actionable message
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": (
                        "Blocked: DROP DATABASE / RESTORE DATABASE requires an approval token. "
                        "Write 'agent-workspace/RESTORE-APPROVED.token' to authorize this "
                        "single operation, then retry. The token is consumed after use."
                    ),
                }
            )
        )
        return 2

    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
