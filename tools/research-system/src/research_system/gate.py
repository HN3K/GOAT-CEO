"""Phase 4 — Abstention gate + bounded gap loop (DESIGN §3 component 7).

A sub-question is only "answered" when enough of its claims survive verification.
Otherwise it is flagged (partial/unanswered) and written to gaps.md — the system
abstains rather than confabulating from weak material [P8]. Unresolved
sub-questions can be retried via a bounded loop that calls back into discovery.

v1 gate is a heuristic support-count quorum; conformal calibration is Phase 7.
"""

from __future__ import annotations

from typing import Callable

from research_system.contracts import (
    Claim,
    QuestionsFile,
    SubQuestion,
    SubQuestionStatus,
    Verdict,
)
from research_system.paths import SubjectLayout

# A resolver takes the still-unresolved sub-questions and returns NEW verified
# claims for them (discover -> answer -> verify). Injected by the orchestrator (P5).
Resolver = Callable[[list[SubQuestion]], list[Claim]]


def gate_status(
    claims_for_subq: list[Claim], *, min_support: int = 2, threshold: float | None = None
) -> SubQuestionStatus:
    """Status from the count of SUPPORTED claims.

    0 supported → UNANSWERED; ≥ cut → ANSWERED; in between → PARTIAL. The cut is the
    calibrated conformal ``threshold`` when provided (DESIGN P8), else the heuristic
    ``min_support``.
    """
    n = sum(1 for c in claims_for_subq if c.verdict is Verdict.SUPPORTED)
    if n == 0:
        return SubQuestionStatus.UNANSWERED
    cut = threshold if threshold is not None else min_support
    if n >= cut:
        return SubQuestionStatus.ANSWERED
    return SubQuestionStatus.PARTIAL


def apply_gate(
    questions: QuestionsFile, claims: list[Claim], *, min_support: int = 2,
    threshold: float | None = None,
) -> QuestionsFile:
    """Set each sub-question's status + supported claim_ids in place."""
    for sq in questions.subquestions:
        cs = [c for c in claims if c.subq_id == sq.id]
        sq.status = gate_status(cs, min_support=min_support, threshold=threshold)
        sq.claim_ids = [c.id for c in cs if c.verdict is Verdict.SUPPORTED]
    return questions


def unresolved(questions: QuestionsFile) -> list[SubQuestion]:
    """Sub-questions that still need work (unanswered or partial)."""
    return [
        sq for sq in questions.subquestions
        if sq.status in (SubQuestionStatus.UNANSWERED, SubQuestionStatus.PARTIAL)
    ]


def render_gaps_md(questions: QuestionsFile, claims: list[Claim], *, min_support: int = 2) -> str:
    """Human-readable gap report for the unresolved sub-questions."""
    def supported(sq_id: str) -> int:
        return sum(1 for c in claims if c.subq_id == sq_id and c.verdict is Verdict.SUPPORTED)

    una = [sq for sq in questions.subquestions if sq.status is SubQuestionStatus.UNANSWERED]
    par = [sq for sq in questions.subquestions if sq.status is SubQuestionStatus.PARTIAL]

    lines = ["# Research Gaps", "", f"Question: {questions.question}", ""]
    if not una and not par:
        lines.append("_No gaps — every sub-question is answered._")
        return "\n".join(lines) + "\n"

    if una:
        lines += ["## Unanswered (no verified support — requires follow-up research)", ""]
        for sq in una:
            lines += [f"- **[{sq.id}]** {sq.text}", f"  - success criteria: {sq.success_criteria}",
                      f"  - supported claims: {supported(sq.id)}"]
        lines.append("")
    if par:
        lines += [f"## Partial (some support, below threshold of {min_support})", ""]
        for sq in par:
            lines += [f"- **[{sq.id}]** {sq.text}", f"  - success criteria: {sq.success_criteria}",
                      f"  - supported claims: {supported(sq.id)} (need {min_support})"]
        lines.append("")
    return "\n".join(lines) + "\n"


def write_gaps(
    layout: SubjectLayout, questions: QuestionsFile, claims: list[Claim], *, min_support: int = 2
) -> None:
    layout.root.mkdir(parents=True, exist_ok=True)
    layout.gaps_path.write_text(render_gaps_md(questions, claims, min_support=min_support),
                                encoding="utf-8")


def run_gap_loop(
    questions: QuestionsFile,
    claims: list[Claim],
    resolver: Resolver,
    *,
    max_iters: int = 2,
    min_support: int = 2,
) -> tuple[QuestionsFile, list[Claim]]:
    """Gate, then retry unresolved sub-questions up to ``max_iters`` times.

    Terminates early when nothing is unresolved or when a round yields no new
    claims (prevents an infinite loop). Whatever remains unresolved stays flagged
    — the system does not fabricate to close a gap.
    """
    apply_gate(questions, claims, min_support=min_support)
    for _ in range(max_iters):
        pending = unresolved(questions)
        if not pending:
            break
        new_claims = resolver(pending)
        if not new_claims:
            break  # discovery dry — stop and leave the gap flagged
        claims.extend(new_claims)
        apply_gate(questions, claims, min_support=min_support)
    return questions, claims
