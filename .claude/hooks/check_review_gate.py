"""TaskCompleted hook: review-gate — judge verdict + iteration cap.

Fires when a task is marked complete by a verifier/reviewer role.
Blocks completion (exit 2) unless:
  (a) a JUDGE-attributed verdict is PASS (C5), AND
  (b) the review iteration count is within the cap (≤2).

Judge attribution (C5): the verdict must come from the judge, not any reviewer.
We prefer agent-workspace/JUDGE-VERDICT.json
    {"role":"judge","verdict":"PASS"|"FAIL","reviewersConsidered":[],
     "blockingFindingsRemaining":[]}
and gate on it. If absent, we scan REVIEW-LOG.md for a fenced JSON block that has
BOTH a judge attribution ("role":"judge" or a truthy "judge") AND a verdict — and
gate on THAT block, NOT last-block-wins. A non-judge PASS no longer satisfies the
gate.

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
JUDGE_VERDICT_FILE = os.path.join(WORKSPACE, "JUDGE-VERDICT.json")
ITERATION_FILE = os.path.join(WORKSPACE, "REVIEW-ITERATION.txt")
ESCALATE_FILE = os.path.join(WORKSPACE, "ESCALATE_REQUIRED")
MAX_ITERATIONS = 2

GATED_ROLES = {"team-verifier"}

# Match fenced JSON blocks in the review log
JSON_BLOCK = re.compile(r"```json\s*(\{.*?\})\s*```", re.DOTALL)


def _is_judge(obj: dict) -> bool:
    """True if a JSON block is attributed to the judge."""
    role = str(obj.get("role", "")).strip().lower()
    if role == "judge":
        return True
    j = obj.get("judge")
    if isinstance(j, bool):
        return j
    # a non-empty truthy "judge" attribution (e.g. a judge name string)
    return bool(j)


def _verdict_of(obj: dict) -> str | None:
    v = str(obj.get("verdict", "")).upper()
    return v if v in ("PASS", "FAIL") else None


def _read_verdict() -> str | None:
    """Return the JUDGE's 'PASS'/'FAIL', or None if no judge-attributed verdict (C5).

    A non-judge PASS (Reviewer A/B/critic block) does NOT count — last-block-wins
    is gone. Prefer agent-workspace/JUDGE-VERDICT.json; else scan REVIEW-LOG.md for
    a fenced JSON block that is BOTH judge-attributed AND has a verdict.
    """
    # 1) Dedicated judge verdict file.
    if os.path.exists(JUDGE_VERDICT_FILE):
        try:
            with open(JUDGE_VERDICT_FILE, "r", encoding="utf-8", errors="replace") as fh:
                obj = json.load(fh)
            if isinstance(obj, dict) and _is_judge(obj):
                v = _verdict_of(obj)
                if v is not None:
                    return v
        except (json.JSONDecodeError, OSError):
            pass  # fall through to REVIEW-LOG.md scan

    # 2) REVIEW-LOG.md: gate on the judge-attributed block (last one if several).
    if not os.path.exists(REVIEW_LOG):
        return None
    try:
        with open(REVIEW_LOG, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None

    judge_verdict = None
    for match in JSON_BLOCK.finditer(text):
        try:
            obj = json.loads(match.group(1))
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict) or not _is_judge(obj):
            continue
        v = _verdict_of(obj)
        if v is not None:
            judge_verdict = v  # later judge block supersedes an earlier one
    return judge_verdict


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
                "REVIEW GATE BLOCK: no JUDGE-attributed verdict found. A reviewer "
                "PASS does NOT satisfy this gate. Provide agent-workspace/"
                'JUDGE-VERDICT.json {"role":"judge","verdict":"PASS"|"FAIL", '
                '"reviewersConsidered":[],"blockingFindingsRemaining":[]} OR a fenced '
                'json block in REVIEW-LOG.md with BOTH "role":"judge" AND a verdict, '
                "before this task can close."
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
