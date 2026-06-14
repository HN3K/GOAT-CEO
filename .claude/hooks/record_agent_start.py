"""SubagentStart hook: record agent start time for the time-budget gate.

Writes (or updates) agent-workspace/AGENT-START-TIMES.json with the current
Unix timestamp keyed by agent_type.  Used by check_turn_budget.py.

This hook is non-blocking — it always exits 0 regardless of outcome.
Errors are swallowed (fail open).

Design contract: FAIL-OPEN on any internal error.  Always exit 0.
"""
import json
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
START_TIMES_FILE = os.path.join(WORKSPACE, "AGENT-START-TIMES.json")


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if not agent_type:
            return 0

        os.makedirs(WORKSPACE, exist_ok=True)

        existing: dict = {}
        if os.path.exists(START_TIMES_FILE):
            try:
                with open(START_TIMES_FILE, "r", encoding="utf-8") as fh:
                    existing = json.load(fh)
            except (json.JSONDecodeError, OSError):
                existing = {}

        session_id = data.get("session_id", agent_type)
        existing[session_id] = time.time()
        existing[agent_type] = time.time()  # also key by role for simple lookup

        with open(START_TIMES_FILE, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2)

        return 0
    except Exception:
        return 0  # fail open — never block on a monitoring write


if __name__ == "__main__":
    sys.exit(main())
