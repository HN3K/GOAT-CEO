"""Phase 5 — Synthesis (DESIGN §3 component 8), deterministic by design.

The final report is ASSEMBLED from verified claims, not re-narrated by a model.
Every line is a SUPPORTED claim shown with its source id and verbatim quote, so
the report is traceable to sources by construction — there is no path for an
unsupported sentence to enter. Unresolved sub-questions are pointed to gaps.md.

(An optional LLM "narrative" layer could be added later, but it would itself have
to pass re-verification; the deterministic assembly is the trustworthy core.)
"""

from __future__ import annotations

from research_system.contracts import Claim, QuestionsFile, SubQuestionStatus, Verdict


def render_synthesis(question: str, questions: QuestionsFile, claims: list[Claim]) -> str:
    supported = [c for c in claims if c.verdict is Verdict.SUPPORTED]
    by_subq: dict[str, list[Claim]] = {}
    for c in supported:
        by_subq.setdefault(c.subq_id, []).append(c)

    lines = [
        f"# Research Synthesis: {question}",
        "",
        "> Every claim below is verified against a stored source and shown with its exact "
        "quote. Sub-questions without verified support are listed in `gaps.md`, not answered here.",
        "",
    ]

    answered_any = False
    for sq in questions.subquestions:
        scs = by_subq.get(sq.id, [])
        if not scs:
            continue
        answered_any = True
        lines += [f"## {sq.text}", ""]
        for c in scs:
            lines += [f"- {c.text}", f'  - source `{c.source_id}`: "{c.quote}"']
        lines.append("")

    if not answered_any:
        lines += ["_No sub-question reached the verified-support threshold. See `gaps.md`._", ""]

    n_gap = sum(
        1 for sq in questions.subquestions
        if sq.status in (SubQuestionStatus.UNANSWERED, SubQuestionStatus.PARTIAL)
    )
    if n_gap:
        lines += [f"---", "", f"**{n_gap} sub-question(s) unresolved** — see `gaps.md` for follow-up research.", ""]

    return "\n".join(lines) + "\n"
