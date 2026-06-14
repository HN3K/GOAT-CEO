"""TaskCompleted hook: review-gate — judge verdict + iteration cap.

Fires when a task is marked complete by a verifier/reviewer role.
Blocks completion (exit 2) unless:
  (a) agent-workspace/REVIEW-LOG.md contains a fenced JSON block with
      "verdict": "PASS" from the judge, AND
  (b) the review iteration count is within the cap (≤2).

If the iteration cap is exceeded, WRITES agent-workspace/ESCALATE_REQUIRED
and exits 1 (allow the task to close so the pipeline can surface this to the
CEO, but the CEO's Stop hook will catch ESCALATE_REQUIRED before the session
can end cleanly).

REVIEW-LOG.md must contain at minimum:
    ```json
    {"verdict": "PASS", "judge": "..."}
    ```
    or
    ```json
    {"verdict": "FAIL", ...}
    ```

REVIEW-ITERATION.txt: single integer line, incremented by the CEO on each fix
loop. Written by the CEO before re-running Phase 5.  Absent == iteration 1.

Design contract: FAIL-OPEN on any internal error.
exit 0 = allow; exit 2 = BLOCK; exit 1 = allow but ESCALATE was written.
"""
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
REVIEW_LOG = os.path.join(WORKSPACE, "REVIEW-LOG.md")
ITERATION_FILE = os.path.join(WORKSPACE, "REVIEW-ITERATION.txt")
ESCALATE_FILE = os.path.join(WORKSPACE, "ESCALATE_REQUIRED")
MAX_ITERATIONS = 2

GATED_ROLES = {"team-verifier"}

# Match fenced JSON blocks in the review log
JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _read_verdict() -> str | None:
    """Return 'PASS', 'FAIL', or None if not parseable.

    REVIEW-LOG.md accumulates blocks from Reviewer A, Reviewer B, the
    completeness critic, and the judge in that order.  The judge writes LAST.
    We must read the LAST fenced JSON block that contains a 'verdict' field,
    not the first (which would be Reviewer A's block, not the judge's).
    """
    if not os.path.exists(REVIEW_LOG):
        return None
    try:
        with open(REVIEW_LOG, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None

    # Collect all verdict-bearing blocks, then take the last one.
    verdicts = []
    for match in JSON_BLOCK.finditer(text):
        try:
            obj = json.loads(match.group(1))
            verdict = str(obj.get("verdict", "")).upper()
            if verdict in ("PASS", "FAIL"):
                verdicts.append(verdict)
        except json.JSONDecodeError:
            continue
    return verdicts[-1] if verdicts else None


def _read_iteration() -> int:
    if not os.path.exists(ITERATION_FILE):
        return 1
    try:
        with open(ITERATION_FILE, "r", encoding="utf-8") as fh:
            return int(fh.read().strip())
    except (OSError, ValueError):
        return 1


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if agent_type not in GATED_ROLES:
            return 0  # not a gated role — allow

        iteration = _read_iteration()

        if iteration > MAX_ITERATIONS:
            # Cap exceeded — write ESCALATE and allow the close so the CEO sees it
            try:
                with open(ESCALATE_FILE, "w", encoding="utf-8") as fh:
                    fh.write(
                        "ESCALATE_REQUIRED: review iteration cap ({}) exceeded. "
                        "Surface open findings to operator before proceeding.\n".format(
                            MAX_ITERATIONS
                        )
                    )
            except OSError:
                pass
            sys.stderr.write(
                "REVIEW ITERATION CAP EXCEEDED (iteration {}). "
                "ESCALATE_REQUIRED written — CEO cannot close the pipeline "
                "until this is resolved. Surfacing to operator.".format(iteration)
            )
            return 1  # allow close (so the task stack doesn't deadlock), but escalate

        verdict = _read_verdict()

        if verdict is None:
            sys.stderr.write(
                "REVIEW GATE BLOCK: agent-workspace/REVIEW-LOG.md is absent or "
                "contains no fenced JSON block with a 'verdict' field. "
                "The judge must write a verdict block before this task can close. "
                'Expected format: ```json\\n{"verdict": "PASS"|"FAIL", ...}\\n```'
            )
            return 2

        if verdict != "PASS":
            sys.stderr.write(
                "REVIEW GATE BLOCK: judge verdict is '{}', not PASS. "
                "Task cannot close. Address the open findings in REVIEW-LOG.md "
                "and re-run the review cycle. "
                "(Review iteration {}/{})".format(verdict, iteration, MAX_ITERATIONS)
            )
            return 2

        return 0
    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
