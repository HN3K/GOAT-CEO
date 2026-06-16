"""Phase 4 gate: abstention status, gap report, bounded retry loop (no confabulation)."""

from research_system.contracts import (
    Claim,
    QuestionsFile,
    SubQuestion,
    SubQuestionStatus,
    Verdict,
)
from research_system.gate import (
    apply_gate,
    gate_status,
    render_gaps_md,
    run_gap_loop,
    unresolved,
    write_gaps,
)
from research_system.paths import SubjectLayout


def claim(cid, subq, verdict):
    return Claim(id=cid, subq_id=subq, text="t", source_id="s001", quote="q", verdict=verdict)


def questions():
    return QuestionsFile(question="Q?", subquestions=[
        SubQuestion(id="q1", text="answered one", success_criteria="x"),
        SubQuestion(id="q2", text="partial one", success_criteria="y"),
        SubQuestion(id="q3", text="unanswered one", success_criteria="z"),
    ])


# --------------------------------------------------------------------------- #
# gate_status
# --------------------------------------------------------------------------- #
def test_gate_status_thresholds():
    S, U = Verdict.SUPPORTED, Verdict.UNSUPPORTED
    assert gate_status([], min_support=2) is SubQuestionStatus.UNANSWERED
    assert gate_status([claim("a", "q", U)], min_support=2) is SubQuestionStatus.UNANSWERED
    assert gate_status([claim("a", "q", S)], min_support=2) is SubQuestionStatus.PARTIAL
    assert gate_status([claim("a", "q", S), claim("b", "q", S)], min_support=2) is SubQuestionStatus.ANSWERED


def test_apply_gate_sets_status_and_supported_claim_ids():
    q = questions()
    claims = [
        claim("q1-c0", "q1", Verdict.SUPPORTED), claim("q1-c1", "q1", Verdict.SUPPORTED),
        claim("q2-c0", "q2", Verdict.SUPPORTED), claim("q2-c1", "q2", Verdict.OVERREACH),
        claim("q3-c0", "q3", Verdict.UNSUPPORTED),
    ]
    apply_gate(q, claims, min_support=2)
    by = {sq.id: sq for sq in q.subquestions}
    assert by["q1"].status is SubQuestionStatus.ANSWERED
    assert by["q1"].claim_ids == ["q1-c0", "q1-c1"]
    assert by["q2"].status is SubQuestionStatus.PARTIAL
    assert by["q2"].claim_ids == ["q2-c0"]              # only supported listed
    assert by["q3"].status is SubQuestionStatus.UNANSWERED
    assert by["q3"].claim_ids == []


def test_unresolved_includes_partial_and_unanswered():
    q = questions()
    apply_gate(q, [claim("q1-c0", "q1", Verdict.SUPPORTED), claim("q1-c1", "q1", Verdict.SUPPORTED),
                   claim("q2-c0", "q2", Verdict.SUPPORTED)], min_support=2)
    assert {sq.id for sq in unresolved(q)} == {"q2", "q3"}


# --------------------------------------------------------------------------- #
# gap report
# --------------------------------------------------------------------------- #
def test_render_gaps_md(tmp_path):
    q = questions()
    claims = [claim("q1-c0", "q1", Verdict.SUPPORTED), claim("q1-c1", "q1", Verdict.SUPPORTED),
              claim("q2-c0", "q2", Verdict.SUPPORTED)]
    apply_gate(q, claims, min_support=2)
    md = render_gaps_md(q, claims, min_support=2)
    assert "unanswered one" in md and "partial one" in md
    assert "[q1]" not in md          # answered subq omitted from gaps (check by id)
    lay = SubjectLayout(tmp_path, "subj").ensure()
    write_gaps(lay, q, claims, min_support=2)
    assert lay.gaps_path.exists()


def test_render_gaps_no_gaps():
    q = QuestionsFile(question="Q?", subquestions=[SubQuestion(id="q1", text="t", success_criteria="x")])
    apply_gate(q, [claim("a", "q1", Verdict.SUPPORTED), claim("b", "q1", Verdict.SUPPORTED)], min_support=2)
    assert "No gaps" in render_gaps_md(q, [])


# --------------------------------------------------------------------------- #
# bounded gap loop — the no-confabulation property
# --------------------------------------------------------------------------- #
def test_gap_loop_resolves_when_evidence_found():
    q = questions()
    # initially nothing supported -> all unresolved
    claims = []

    def resolver(pending):
        # "discovers" two supported claims for each pending sub-question
        out = []
        for sq in pending:
            out += [claim(f"{sq.id}-n0", sq.id, Verdict.SUPPORTED),
                    claim(f"{sq.id}-n1", sq.id, Verdict.SUPPORTED)]
        return out

    q, claims = run_gap_loop(q, claims, resolver, max_iters=2, min_support=2)
    assert all(sq.status is SubQuestionStatus.ANSWERED for sq in q.subquestions)


def test_gap_loop_flags_not_confabulates_when_dry():
    q = questions()
    calls = {"n": 0}

    def dry_resolver(pending):
        calls["n"] += 1
        return []  # discovery finds nothing new

    q, claims = run_gap_loop(q, [], dry_resolver, max_iters=3, min_support=2)
    # unresolved sub-questions remain flagged, NOT answered
    assert all(sq.status is SubQuestionStatus.UNANSWERED for sq in q.subquestions)
    assert calls["n"] == 1  # stopped immediately once a round was dry


def test_gap_loop_respects_max_iters():
    q = questions()
    calls = {"n": 0}

    def insufficient_resolver(pending):
        calls["n"] += 1
        # always returns ONE supported claim per subq -> PARTIAL, never reaches ANSWERED
        return [claim(f"{sq.id}-i{calls['n']}", sq.id, Verdict.SUPPORTED) for sq in pending]

    q, claims = run_gap_loop(q, [], insufficient_resolver, max_iters=3, min_support=5)
    assert calls["n"] == 3  # capped
    assert any(sq.status is SubQuestionStatus.PARTIAL for sq in q.subquestions)
