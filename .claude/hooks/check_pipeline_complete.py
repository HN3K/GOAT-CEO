"""Stop hook: CEO keep-going enforcement + pipeline-completeness gate.

Fires when the main CEO session is about to end its turn. Its job is to stop the CEO
from going idle while there is still autonomous work to do — the failure mode where the
CEO reports a milestone, writes "continuing autonomously", and then ends its turn anyway
(a voluntary yield that nothing re-invokes). See commands/goat-ceo/unattended-mode.md (the
opt-in keep-going layer); in the default Collaborative mode this hook only enforces
pipeline-gate completeness.

KEEP-GOING IS OPT-IN. It engages only when agent-workspace/AUTONOMOUS-ACTIVE exists — the
CEO (or operator) writes that flag to declare "this is an unattended run; do not yield to
me between turns." Without the flag, the hook keeps only its original pipeline-completeness
behavior (block while expected *.GATE sentinels are missing) and otherwise lets the turn
end — so collaborative, turn-by-turn sessions are unaffected.

BEHAVIOR — when AUTONOMOUS-ACTIVE is set (or a pipeline has open gates), the turn-end is
BLOCKED (the CEO is forced to take another turn and continue its NEXT_ACTION) UNLESS one of
these legitimate yield conditions holds:
  - agent-workspace/STOP                 (operator hard halt)
  - agent-workspace/AWAITING-OPERATOR    (CEO declared it is blocked on an operator-only /
                                          irreversible action — push, DB drop, UI/cert)
  - agent-workspace/SESSION-COMPLETE     (mission done)
  - agent-workspace/ESCALATE_REQUIRED    (needs an operator decision; surface it)
When blocked, additionalContext tells the CEO exactly how to continue or how to yield.

RUNAWAY BACKSTOP — a consecutive-block counter (agent-workspace/_stop_block_count.json)
prevents an infinite token-burn loop if the CEO neither progresses nor writes a yield
marker. The counter resets whenever RESUME-STATE.md is updated (a checkpoint = progress).
After CAP consecutive blocks with NO progress and NO yield marker, the hook allows the
turn to end and warns — so a stuck CEO surfaces to the operator instead of spinning.

NOTE on exit codes: Claude Code's Stop hook ignores stdout JSON on exit 2; only exit 0
JSON is processed. So we exit 0 with {"decision":"block"} to deliver additionalContext.

Design contract: FAIL-OPEN on any internal error.
exit 0 + no/allow decision = let turn end; exit 0 + decision:block = keep going.
"""
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")

EXPECTED_GATES_FILE = os.path.join(WORKSPACE, "EXPECTED-GATES.txt")
AUTONOMOUS_ACTIVE_FILE = os.path.join(WORKSPACE, "AUTONOMOUS-ACTIVE")
RESUME_STATE_FILE = os.path.join(WORKSPACE, "RESUME-STATE.md")
COUNTER_FILE = os.path.join(WORKSPACE, "_stop_block_count.json")

# Files whose presence is a LEGITIMATE yield (allow the turn to end).
YIELD_MARKERS = [
    os.path.join(WORKSPACE, "STOP"),
    os.path.join(WORKSPACE, "AWAITING-OPERATOR"),
    os.path.join(WORKSPACE, "SESSION-COMPLETE"),
    os.path.join(WORKSPACE, "ESCALATE_REQUIRED"),
]

CAP = 20  # consecutive forced-continues with NO progress before yielding (runaway backstop)


def _expected_gates():
    try:
        with open(EXPECTED_GATES_FILE, "r", encoding="utf-8") as fh:
            return [l.strip() for l in fh if l.strip() and not l.strip().startswith("#")]
    except OSError:
        return []


def _autonomous_engaged(session_id):
    """Is keep-going engaged for THIS session?

    agent-workspace/AUTONOMOUS-ACTIVE controls it:
      - absent                       -> NOT engaged
      - empty, or any content with NO 'session:' line -> engaged for ALL sessions
      - contains 'session:<id>' line(s) -> engaged ONLY for those session ids
        (lets one session run unattended without trapping a concurrent collaborative
         session in the same agent-workspace)
    """
    try:
        with open(AUTONOMOUS_ACTIVE_FILE, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
    except OSError:
        return False  # absent / unreadable -> not engaged
    if not content:
        return True
    if "session:" in content:
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("session:") and session_id and line[len("session:"):].strip() == session_id:
                return True
        return False  # scoped to other session(s)
    return True  # non-empty but unscoped -> all sessions


def _reset_counter():
    try:
        if os.path.exists(COUNTER_FILE):
            os.remove(COUNTER_FILE)
    except OSError:
        pass


def _allow():
    _reset_counter()
    return 0


def _resume_mtime():
    try:
        return os.path.getmtime(RESUME_STATE_FILE)
    except OSError:
        return 0.0


def _read_counter():
    try:
        with open(COUNTER_FILE, "r", encoding="utf-8") as fh:
            d = json.load(fh)
        return int(d.get("count", 0)), float(d.get("resume_mtime", 0.0))
    except Exception:
        return 0, 0.0


def _write_counter(count, mtime):
    try:
        with open(COUNTER_FILE, "w", encoding="utf-8") as fh:
            json.dump({"count": count, "resume_mtime": mtime}, fh)
    except OSError:
        pass


def _block(context_msg, reason):
    result = {
        "decision": "block",
        "reason": reason,
        "hookSpecificOutput": {"hookEventName": "Stop", "additionalContext": context_msg},
    }
    sys.stdout.write(json.dumps(result))
    sys.stderr.write(reason)
    return 0


def main() -> int:
    try:
        raw = sys.stdin.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except Exception:
            data = {}
        session_id = str(data.get("session_id", "") or "")

        expected = _expected_gates()
        autonomous = _autonomous_engaged(session_id)

        # INTAKE EXEMPTION: the interactive /goat-ceo flow writes agent-workspace/INTAKE-ACTIVE
        # while it runs Steps 1-2 (operator intake) and removes it at Step 3.1 (when the
        # pipeline + EXPECTED-GATES are declared). While that marker exists the CEO is mid-intake
        # and MUST be able to end a turn to ask the operator a question — even if AUTONOMOUS-ACTIVE
        # is globally set. This keys off the EXPLICIT intake marker, NOT "no EXPECTED-GATES", so a
        # non-pipeline autonomous WORK-QUEUE run (gates absent, no intake marker) still engages
        # keep-going normally and is NOT weakened. See unattended-mode.md §1.
        if os.path.exists(os.path.join(WORKSPACE, "INTAKE-ACTIVE")):
            return _allow()

        # Nothing forces continuation: no pipeline declared AND not an autonomous run.
        if not expected and not autonomous:
            return _allow()

        # Legitimate yields — the CEO is allowed to end its turn.
        if any(os.path.exists(m) for m in YIELD_MARKERS):
            return _allow()

        missing = [g for g in expected if not os.path.exists(os.path.join(WORKSPACE, g))]

        # Two distinct jobs, evaluated here:
        #   PURPOSE A — pipeline completeness (both modes): block while expected gates remain.
        #   PURPOSE B — keep-going (opt-in only): block a voluntary yield while AUTONOMOUS-ACTIVE.
        # Pipeline complete AND not autonomous = collaborative session done → allow. Pipeline
        # complete BUT autonomous still engaged → fall through to the keep-going block below.
        if not missing and not autonomous:
            return _allow()

        # Runaway backstop: reset the block counter whenever a checkpoint advanced
        # RESUME-STATE.md (= real progress). Only a CEO that keeps trying to stop WITHOUT
        # progressing or writing a yield marker climbs toward CAP.
        rmtime = _resume_mtime()
        count, last_mtime = _read_counter()
        if rmtime > last_mtime:
            count = 0
        count += 1
        if count > CAP:
            _reset_counter()
            sys.stderr.write(
                "KEEP-GOING BACKSTOP: {} consecutive turn-ends with no checkpoint progress "
                "and no yield marker — allowing the turn to end so the operator can check. "
                "(The CEO may be stuck; inspect agent-workspace/RESUME-STATE.md.)".format(CAP)
            )
            return 0  # allow — surface to operator rather than spin
        _write_counter(count, rmtime)

        # Otherwise BLOCK — force another turn and tell the CEO how to continue / yield.
        if missing:
            msg = (
                "PIPELINE INCOMPLETE — do not end your turn. Missing gates: "
                + ", ".join(missing)
                + ". Continue the pipeline toward these gates now, in this turn."
            )
            reason = "KEEP-GOING (gates open): " + ", ".join(missing)
        else:
            msg = (
                "THIS IS NOT A STOP. A milestone/phase being done is not a reason to end your "
                "turn and wait for the operator. If there is autonomous work remaining (your "
                "NEXT_ACTION in agent-workspace/RESUME-STATE.md), DO IT NOW in this turn — do "
                "not just report that you 'will continue'. You may end your turn ONLY by first "
                "writing one of:\n"
                "  - agent-workspace/AWAITING-OPERATOR  (you are genuinely blocked on an "
                "operator-only/irreversible action — name exactly what you need: a push, a DB "
                "drop, a UI/cert step). Delete it when the operator unblocks you and you resume.\n"
                "  - agent-workspace/SESSION-COMPLETE   (the whole mission is done).\n"
                "  - agent-workspace/ESCALATE_REQUIRED  (you need an operator decision).\n"
                "If your last action was a status report, take the next concrete step instead."
            )
            reason = "KEEP-GOING (autonomous work pending; no yield marker)"
        return _block(msg, reason)

    except Exception:
        return 0  # fail open — never trap the CEO


if __name__ == "__main__":
    sys.exit(main())
