"""TaskCompleted hook: broad test-suite gate.

Fires when a task is marked complete.  Blocks completion (exit 2) if the
broad test suite fails.  Reads the test command from agent-workspace/
TEST-COMMAND.txt (one line, written by the CEO at session start).  If that
file is absent the hook fails open — the CEO must write the command for the
gate to be active.

This enforces Doctrine #2: "every 'tests pass' claim is a hypothesis until
independently verified."  Mock-only suites passed on 7+ real-run failures
before this gate existed.

Design contract: FAIL-OPEN on any internal error.
exit 0 = allow task to close; exit 2 = BLOCK (stderr shown to agent).
"""
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
TEST_CMD_PATH = os.path.join(WORKSPACE, "TEST-COMMAND.txt")

# Only gate implementer and verifier task completions.
GATED_ROLES = {"team-implementer", "team-verifier"}


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if agent_type not in GATED_ROLES:
            return 0  # not a gated role — allow

        if not os.path.exists(TEST_CMD_PATH):
            # No test command configured — fail open but warn via stderr
            # (informational, not a block — the gate is inactive without the file)
            sys.stderr.write(
                "WARNING (check_test_gate): agent-workspace/TEST-COMMAND.txt "
                "is absent. The broad test-suite gate is INACTIVE for this "
                "session. CEO must write the test command to activate it."
            )
            return 0

        with open(TEST_CMD_PATH, "r", encoding="utf-8") as fh:
            test_cmd = fh.read().strip()

        if not test_cmd:
            return 0  # empty file — fail open

        result = subprocess.run(
            test_cmd,
            shell=True,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute cap — a hung test suite should not hang the hook
        )

        if result.returncode != 0:
            out_tail = (result.stdout or "")[-1500:].strip()
            err_tail = (result.stderr or "")[-500:].strip()
            sys.stderr.write(
                "TEST GATE BLOCK: broad test suite FAILED (exit {}).\n"
                "Task cannot be marked complete until all tests pass.\n"
                "Command: {}\n"
                "--- last stdout ---\n{}\n"
                "--- last stderr ---\n{}".format(
                    result.returncode, test_cmd, out_tail, err_tail
                )
            )
            return 2

        # Hollow-pass guard (reward-hacking defense): a suite that runs ZERO tests exits 0 and
        # trivially "passes". A passing gate must actually execute tests. These markers are the
        # standard pytest/unittest zero-collected strings and do not collide with passing output
        # (e.g. "collected 0 items", not "0 passed" which is a substring of "10 passed"). The
        # SEMANTIC reward-hack audit (sys.exit(0) / __eq__ overrides / conftest force-pass /
        # hardcoded expected values / deleted-or-skipped tests) is Reviewer B's job — see
        # templates.md §12; a fresh-context reviewer catches what a regex cannot.
        combined = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
        HOLLOW = ("no tests ran", "collected 0 items", "ran 0 tests", "no tests found")
        if any(marker in combined for marker in HOLLOW):
            sys.stderr.write(
                "TEST GATE BLOCK: the suite reported success but ran ZERO tests (hollow pass). "
                "A passing gate must actually execute tests — check the test command/selection.\n"
                "Command: {}\n--- output tail ---\n{}".format(test_cmd, combined[-1500:].strip())
            )
            return 2

        return 0
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "WARNING (check_test_gate): test suite timed out after 5 min. "
            "Failing open to avoid blocking the pipeline. Investigate manually."
        )
        return 0  # fail open on timeout
    except Exception:
        return 0  # fail open — hook bug must never block legitimate work


if __name__ == "__main__":
    sys.exit(main())
