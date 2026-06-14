"""Stop hook: CEO pipeline-completeness gate.

Fires when the main CEO session is about to end its turn.  Blocks (exit 0 with
"decision":"block") if:
  (a) any *.GATE file is missing from agent-workspace/ that was expected, OR
  (b) agent-workspace/ESCALATE_REQUIRED exists.

The CEO declares the expected gates by writing agent-workspace/EXPECTED-GATES.txt
(one sentinel filename per line, e.g. PLAN.GATE, RESEARCH.GATE, ...).
If EXPECTED-GATES.txt is absent, the hook fails open (pipeline has not started).

This enforces Doctrine #2: the CEO cannot declare "done" while any phase gate
is open or while an unresolved escalation is pending.

The hook injects additionalContext listing the missing gates so the CEO knows
exactly what to address before its turn ends.

NOTE on exit codes: Claude Code's Stop hook ignores stdout JSON on exit 2
(only exit 0 JSON is processed for additionalContext).  We therefore exit 0
with "decision":"block" so the additionalContext reaches Claude.  stderr still
carries the gate-block message for operator logs.

Design contract: FAIL-OPEN on any internal error.
exit 0 + decision:allow = let turn end; exit 0 + decision:block = BLOCK with additionalContext.
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
EXPECTED_GATES_FILE = os.path.join(WORKSPACE, "EXPECTED-GATES.txt")
ESCALATE_FILE = os.path.join(WORKSPACE, "ESCALATE_REQUIRED")


def main() -> int:
    try:
        # Read stdin but do not filter on agent_type — the Stop hook only fires
        # for the main CEO session (not subagents); subagent stop is handled by
        # check_artifacts.py on SubagentStop.  The old agent_type filter
        # (which allowed team-overseer through) was fragile and unnecessary.
        raw = sys.stdin.read()
        # (data reserved for future use; we don't key on agent_type)

        if not os.path.exists(EXPECTED_GATES_FILE):
            return 0  # no pipeline started — allow

        with open(EXPECTED_GATES_FILE, "r", encoding="utf-8") as fh:
            expected = [
                line.strip()
                for line in fh
                if line.strip() and not line.strip().startswith("#")
            ]

        if not expected:
            return 0

        missing_gates = []
        for sentinel in expected:
            path = os.path.join(WORKSPACE, sentinel)
            if not os.path.exists(path):
                missing_gates.append(sentinel)

        escalate_pending = os.path.exists(ESCALATE_FILE)

        if not missing_gates and not escalate_pending:
            return 0  # all clear — allow

        problems = []
        if missing_gates:
            problems.append("Missing phase gates: " + ", ".join(missing_gates))
        if escalate_pending:
            try:
                with open(ESCALATE_FILE, "r", encoding="utf-8") as fh:
                    note = fh.read(500).strip()
            except OSError:
                note = "(unreadable)"
            problems.append("ESCALATE_REQUIRED is set: " + note)

        problem_text = " | ".join(problems)
        context_msg = (
            "PIPELINE INCOMPLETE — your turn cannot end cleanly.\n"
            + problem_text
            + "\n\nAddress the above before ending your turn. "
            "If a gate is missing because no pipeline is running, "
            "update agent-workspace/EXPECTED-GATES.txt to reflect "
            "the current state."
        )

        # Exit 0 with decision:block so additionalContext is delivered to Claude.
        # (exit 2 causes Claude Code to drop stdout JSON; exit 0 is required for
        # the hookSpecificOutput additionalContext to reach the model.)
        result = {
            "decision": "block",
            "reason": "PIPELINE GATE BLOCK: " + problem_text,
            "hookSpecificOutput": {
                "hookEventName": "Stop",
                "additionalContext": context_msg,
            },
        }
        sys.stdout.write(json.dumps(result))
        sys.stderr.write("PIPELINE GATE BLOCK: " + problem_text)
        return 0

    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
