"""PostToolBatch hook: time-budget yield (availability-gated).

Forces a hard yield if an implementer or verifier agent has been running
for longer than BUDGET_MINUTES.  Reads the agent start time from
agent-workspace/AGENT-START-TIMES.json (written by SubagentStart companion
hook or by the CEO at spawn time).

Availability gate: PostToolBatch and SubagentStart are verified hooks per the
REWORK-REVIEW feature table.  If the JSON file is absent (harness version that
doesn't write it), the hook fails open silently.

On exit 2, the agent is stopped before the next model call.  The agent should
write a STATE note and checkpoint message before its next tool call is blocked.

Design contract: FAIL-OPEN on any internal error.
exit 0 = allow; exit 2 = BLOCK (stops agentic loop before next model call).
"""
import json
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
START_TIMES_FILE = os.path.join(WORKSPACE, "AGENT-START-TIMES.json")

BUDGET_MINUTES = 30  # trigger hard yield after 30 min of continuous running
GATED_ROLES = {"team-implementer", "team-verifier"}


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if agent_type not in GATED_ROLES:
            return 0

        if not os.path.exists(START_TIMES_FILE):
            return 0  # no start-time data — fail open

        with open(START_TIMES_FILE, "r", encoding="utf-8") as fh:
            start_times = json.load(fh)

        # Key is agent_type; in a multi-agent session you'd key by session ID,
        # but for simplicity key by role (only one agent of each role per wave).
        session_id = data.get("session_id", agent_type)
        start_ts = start_times.get(session_id) or start_times.get(agent_type)
        if start_ts is None:
            return 0  # no start time for this agent — fail open

        elapsed_minutes = (time.time() - float(start_ts)) / 60.0
        if elapsed_minutes >= BUDGET_MINUTES:
            sys.stderr.write(
                "TIME BUDGET YIELD: role '{}' has been running for {:.1f} minutes "
                "(budget: {} min). Stopping agentic loop before next model call. "
                "Write your current state to STATUS.md in agent-workspace/, "
                "send a checkpoint message to the CEO, and END YOUR TURN. "
                "The CEO will re-spawn you for the next batch if needed.".format(
                    agent_type, elapsed_minutes, BUDGET_MINUTES
                )
            )
            return 2

        return 0
    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
