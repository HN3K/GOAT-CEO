"""Phase 6 — Benchmark harness (DESIGN §7).

Answers the literature's open question #1: does per-claim verification + abstention
on top of grounded synthesis actually help, on the SAME corpus?

Clean isolation. Both arms share the SAME upstream — one decomposition, one set of
answered claims — and differ at exactly ONE step:
  B  (verified)   — verify each claim; present only SUPPORTED ones; abstain otherwise.
  A' (unverified) — present ALL answered claims (no verification, no gate).
So A' = "B minus verification". Differences in faithfulness/auditability are attributable
to verification alone, with the search/decompose/answer confounds held fixed.

(A — stock deep-research — is an external CC workflow; score its saved report with
`score_presented` separately.)

Metrics: faithfulness, hallucination (unfaithful count), auditability, coverage (vs a
must-include checklist), gap-honesty (present ~0 on out-of-corpus questions), and cost.
Scoring is blind: each arm's PRESENTED claims are re-verified post-hoc by a fresh ensemble.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from research_system.answer import answer_subquestion
from research_system.contracts import Claim, Verdict
from research_system.decompose import decompose
from research_system.grounding import quote_present
from research_system.llm import CostTracker, LLMClient
from research_system.orchestrate import OrchestratorConfig
from research_system.retrieve import BM25Retriever, Corpus
from research_system.verify import DEFAULT_JUDGES, verify_claim

MakeClient = Callable[[], LLMClient]


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
@dataclass
class ArmScore:
    name: str
    presented: int
    faithful: int
    unfaithful: int
    auditability: float          # fraction of presented claims with a verbatim quote
    cost_usd: float
    coverage: float | None = None      # fraction of must-include facts surfaced (answerable Qs)
    gap_honest: bool | None = None     # for out-of-corpus Qs: did it present ~0 claims?

    @property
    def faithfulness(self) -> float:
        return self.faithful / self.presented if self.presented else 1.0


def _coverage(presented: list[Claim], must_include: list[str] | None) -> float | None:
    if not must_include:
        return None
    hay = " ".join((c.text + " " + c.quote) for c in presented).lower()
    hit = sum(1 for key in must_include if key.lower() in hay)
    return hit / len(must_include)


def score_presented(
    name: str,
    presented: list[Claim],
    corpus: Corpus,
    score_client: LLMClient,
    *,
    judges: tuple[str, ...] = DEFAULT_JUDGES,
    cost_usd: float = 0.0,
    must_include: list[str] | None = None,
    answerable: bool = True,
) -> ArmScore:
    """Blind post-hoc verification of an arm's presented claims → faithfulness etc."""
    scored = [verify_claim(c.model_copy(deep=True), corpus, score_client, judges=judges)
              for c in presented]
    faithful = sum(1 for c in scored if c.verdict is Verdict.SUPPORTED)
    auditable = sum(
        1 for c in presented
        if c.source_id in corpus and quote_present(c.quote, corpus.get(c.source_id))
    )
    n = len(presented)
    return ArmScore(
        name=name,
        presented=n,
        faithful=faithful,
        unfaithful=n - faithful,
        auditability=(auditable / n if n else 1.0),
        cost_usd=cost_usd,
        coverage=_coverage(presented, must_include),
        gap_honest=(None if answerable else (n == 0)),
    )


def run_grounded_arm(question: str, corpus: Corpus, llm: LLMClient,
                     *, config: OrchestratorConfig | None = None) -> list[Claim]:
    """Arm B as a standalone: decompose → answer → verify → present SUPPORTED claims.
    Used by the tier sweep (verification held constant, extraction model varied)."""
    config = config or OrchestratorConfig()
    retriever = BM25Retriever(corpus)
    questions = decompose(question, llm, model=config.decompose_model, n=config.n_subquestions)
    presented: list[Claim] = []
    for sq in questions.subquestions:
        cs = answer_subquestion(sq, retriever, corpus, llm, k=config.k, model=config.answer_model)
        for c in cs:
            verify_claim(c, corpus, llm, judges=config.judges)
        presented += [c for c in cs if c.verdict is Verdict.SUPPORTED]
    return presented


# --------------------------------------------------------------------------- #
# Comparison (shared upstream, differ only at verification)
# --------------------------------------------------------------------------- #
@dataclass
class QuestionComparison:
    question: str
    answerable: bool
    verified: ArmScore
    unverified: ArmScore


def compare_arms(
    question: str,
    corpus: Corpus,
    make_client: MakeClient,
    *,
    config: OrchestratorConfig | None = None,
    score_judges: tuple[str, ...] = DEFAULT_JUDGES,
    must_include: list[str] | None = None,
    answerable: bool = True,
) -> QuestionComparison:
    config = config or OrchestratorConfig()
    retriever = BM25Retriever(corpus)

    # --- shared upstream: decompose + answer once (metered) -------------------
    upstream = CostTracker(make_client())
    questions = decompose(question, upstream, model=config.decompose_model, n=config.n_subquestions)
    answered: list[Claim] = []
    for sq in questions.subquestions:
        answered += answer_subquestion(sq, retriever, corpus, upstream,
                                       k=config.k, model=config.answer_model)
    upstream_cost = upstream.total_cost_usd

    # A' (unverified): present every answered claim, no verification -----------
    naive_presented = list(answered)

    # B (verified): verify each claim, present only supported ------------------
    vmeter = CostTracker(make_client())
    for c in answered:
        verify_claim(c, corpus, vmeter, judges=config.judges)
    grounded_presented = [c for c in answered if c.verdict is Verdict.SUPPORTED]

    # --- blind scoring (separate client; not charged to either arm) -----------
    sc = make_client()
    verified = score_presented("B verified", grounded_presented, corpus, sc, judges=score_judges,
                               cost_usd=upstream_cost + vmeter.total_cost_usd,
                               must_include=must_include, answerable=answerable)
    unverified = score_presented("A' unverified", naive_presented, corpus, sc, judges=score_judges,
                                 cost_usd=upstream_cost,
                                 must_include=must_include, answerable=answerable)
    return QuestionComparison(question=question, answerable=answerable,
                              verified=verified, unverified=unverified)


# --------------------------------------------------------------------------- #
# Aggregate report
# --------------------------------------------------------------------------- #
def format_comparison(comps: list[QuestionComparison]) -> str:
    def s(sel):  # sum a field across arms
        return sum(sel(c.verified) for c in comps), sum(sel(c.unverified) for c in comps)

    pres_b, pres_a = s(lambda r: r.presented)
    faith_b, faith_a = s(lambda r: r.faithful)
    unf_b, unf_a = s(lambda r: r.unfaithful)
    cost_b, cost_a = s(lambda r: r.cost_usd)
    fr_b = faith_b / pres_b if pres_b else 1.0
    fr_a = faith_a / pres_a if pres_a else 1.0
    aud_b = sum(c.verified.auditability for c in comps) / len(comps) if comps else 1.0
    aud_a = sum(c.unverified.auditability for c in comps) / len(comps) if comps else 1.0

    cov_b = [c.verified.coverage for c in comps if c.verified.coverage is not None]
    cov_a = [c.unverified.coverage for c in comps if c.unverified.coverage is not None]
    covs_b = f"{sum(cov_b)/len(cov_b):.1%}" if cov_b else "n/a"
    covs_a = f"{sum(cov_a)/len(cov_a):.1%}" if cov_a else "n/a"

    unans = [c for c in comps if not c.answerable]
    gh_b = sum(1 for c in unans if c.verified.gap_honest)
    gh_a = sum(1 for c in unans if c.unverified.gap_honest)
    ghs_b = f"{gh_b}/{len(unans)}" if unans else "n/a"
    ghs_a = f"{gh_a}/{len(unans)}" if unans else "n/a"

    lines = [
        f"# Benchmark: B verified vs A' unverified — {len(comps)} question(s)",
        "",
        "Both arms share decomposition + retrieval + answers; they differ ONLY at verification.",
        "",
        "| metric | B (verified) | A' (unverified) |",
        "|--------|-------------:|----------------:|",
        f"| claims presented | {pres_b} | {pres_a} |",
        f"| faithful (post-hoc) | {faith_b} | {faith_a} |",
        f"| **unfaithful shipped** | {unf_b} | {unf_a} |",
        f"| faithfulness | {fr_b:.1%} | {fr_a:.1%} |",
        f"| auditability | {aud_b:.1%} | {aud_a:.1%} |",
        f"| coverage (vs checklist) | {covs_b} | {covs_a} |",
        f"| gap-honesty (out-of-corpus) | {ghs_b} | {ghs_a} |",
        f"| cost (USD) | {cost_b:.4f} | {cost_a:.4f} |",
        "",
        f"A' shipped {unf_a} unfaithful claim(s) that B's verification removed "
        f"(B kept {pres_b}, A' kept {pres_a}). Verification's marginal cost: "
        f"${cost_b - cost_a:.4f}.",
    ]
    return "\n".join(lines) + "\n"
