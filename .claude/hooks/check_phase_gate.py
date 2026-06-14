"""PreToolUse hook: phase-gate approval-token pattern.

Blocks Write / Edit / Bash by non-CEO roles until the required phase gate
sentinel exists in agent-workspace/.  The gate map is read from
agent-workspace/PHASE-GATES.json which the driver (CEO / Workflow script)
writes at session start to declare which role needs which sentinel before it
can act.

PHASE-GATES.json shape:
    {
        "team-implementer": ["RESEARCH.GATE"],
        "team-verifier":    ["IMPLEMENT.GATE", "INDEX.GATE"],
        "team-overseer":    []
    }

An entry absent from the map == no gate required (allow).

Design contract: FAIL-OPEN on any internal error.
exit 0 = allow; exit 2 = BLOCK (stderr shown to agent).
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
GATE_MAP_PATH = os.path.join(WORKSPACE, "PHASE-GATES.json")

# Only gate these tools — reads / observability tools are always allowed.
GATED_TOOL_NAMES = {"Write", "Edit", "Bash", "PowerShell"}


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        tool_name = data.get("tool_name", "")
        if tool_name not in GATED_TOOL_NAMES:
            return 0  # not a write-capable tool — allow

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if not agent_type:
            return 0  # can't identify role — fail open (may be CEO main session)

        # CEO / orchestrator sessions are never gated by this hook.
        if agent_type in ("", "goat-ceo", "team-overseer"):
            return 0

        if not os.path.exists(GATE_MAP_PATH):
            return 0  # no gate map written yet — fail open

        with open(GATE_MAP_PATH, "r", encoding="utf-8") as fh:
            gate_map = json.load(fh)

        required_gates = gate_map.get(agent_type, [])
        if not required_gates:
            return 0  # role has no gates defined — allow

        missing = []
        for sentinel in required_gates:
            path = os.path.join(WORKSPACE, sentinel)
            if not os.path.exists(path):
                missing.append(sentinel)

        if missing:
            sys.stderr.write(
                "PHASE GATE BLOCK: role '{}' cannot use {} until the following "
                "gate sentinels exist in agent-workspace/: {}. "
                "Your phase has not been unlocked yet. "
                "Report your current state to the CEO and END YOUR TURN.".format(
                    agent_type, tool_name, ", ".join(missing)
                )
            )
            return 2

        return 0
    except Exception:
        return 0  # fail open — hook bug must never block legitimate work


if __name__ == "__main__":
    sys.exit(main())
