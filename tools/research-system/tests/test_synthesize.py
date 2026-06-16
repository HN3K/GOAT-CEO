"""Phase 5: deterministic, traceable synthesis."""

from research_system.contracts import (
    Claim,
    QuestionsFile,
    SubQuestion,
    SubQuestionStatus,
    Verdict,
)
from research_system.synthesize import render_synthesis


def claim(cid, subq, verdict, text="fact", quote="the verbatim quote"):
    return Claim(id=cid, subq_id=subq, text=text, source_id="s001", quote=quote, verdict=verdict)


def test_includes_supported_excludes_others():
    q = QuestionsFile(question="Q?", subquestions=[
        SubQuestion(id="q1", text="Sub one", success_criteria="x", status=SubQuestionStatus.ANSWERED)])
    claims = [
        claim("c0", "q1", Verdict.SUPPORTED, text="supported fact", quote="exact span one"),
        claim("c1", "q1", Verdict.UNSUPPORTED, text="bogus fact", quote="fabricated span"),
    ]
    md = render_synthesis("Q?", q, claims)
    assert "Sub one" in md
    assert "supported fact" in md and 'source `s001`: "exact span one"' in md
    assert "bogus fact" not in md          # unsupported never enters synthesis


def test_gap_pointer_when_unresolved():
    q = QuestionsFile(question="Q?", subquestions=[
        SubQuestion(id="q1", text="answered", success_criteria="x", status=SubQuestionStatus.ANSWERED),
        SubQuestion(id="q2", text="missing", success_criteria="y", status=SubQuestionStatus.UNANSWERED)])
    md = render_synthesis("Q?", q, [claim("c0", "q1", Verdict.SUPPORTED)])
    assert "gaps.md" in md and "unresolved" in md


def test_no_supported_claims_message():
    q = QuestionsFile(question="Q?", subquestions=[
        SubQuestion(id="q1", text="t", success_criteria="x", status=SubQuestionStatus.UNANSWERED)])
    md = render_synthesis("Q?", q, [claim("c0", "q1", Verdict.UNSUPPORTED)])
    assert "No sub-question reached" in md
