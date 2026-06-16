"""Phase 7 — Model-tier sweep (DESIGN §6, cost thesis).

Runs the grounded arm with the EXTRACTION (answer) model varied across tiers
while holding verification constant, scoring each with the blind verifier. This
quantifies the open-book hypothesis: cheap models should hold faithfulness on
extraction once the source text is in front of them — i.e. "X% cheaper at equal
faithfulness." Cost is measured via ``CostTracker`` (populated on live runs).
"""

from __future__ import annotations

from dataclasses import dataclass

from research_system.benchmark import ArmScore, run_grounded_arm, score_presented
from research_system.llm import CHEAP, MID, STRONG, CostTracker, LLMClient
from research_system.orchestrate import OrchestratorConfig
from research_system.retrieve import Corpus
from research_system.verify import DEFAULT_JUDGES


@dataclass
class TierOutcome:
    tier: str
    result: ArmScore
    cost_usd: float
    n_calls: int


def run_tier_sweep(
    question: str,
    corpus: Corpus,
    make_client: "callable",
    *,
    tiers: tuple[str, ...] = (CHEAP, MID, STRONG),
    base_config: OrchestratorConfig | None = None,
    score_judges: tuple[str, ...] = DEFAULT_JUDGES,
    must_include: list[str] | None = None,
) -> list[TierOutcome]:
    """For each extraction tier: run arm B with that answer model, score it, track cost.

    ``make_client`` is a 0-arg factory returning a fresh ``LLMClient`` (so each tier
    gets an independent cost meter). Verification (`base_config.judges`) is constant.
    """
    base = base_config or OrchestratorConfig()
    outcomes: list[TierOutcome] = []
    for tier in tiers:
        meter = CostTracker(make_client())
        cfg = OrchestratorConfig(
            n_subquestions=base.n_subquestions, k=base.k,
            decompose_model=base.decompose_model, answer_model=tier,
            judges=base.judges, min_support=base.min_support,
        )
        presented = run_grounded_arm(question, corpus, meter, config=cfg)
        # score with a fresh client so post-hoc scoring cost is not charged to the tier
        result = score_presented(f"answer={tier}", presented, corpus, make_client(),
                                 judges=score_judges, must_include=must_include)
        outcomes.append(TierOutcome(tier=tier, result=result,
                                    cost_usd=meter.total_cost_usd, n_calls=meter.n_calls))
    return outcomes


def _cov(r) -> str:
    return f"{r.coverage:.1%}" if r.coverage is not None else "n/a"


def format_tier_table(outcomes: list[TierOutcome]) -> str:
    lines = [
        "# Model-tier sweep (extraction model varied, verification constant)",
        "",
        "| extraction tier | claims | faithful | faithfulness | auditability | coverage | cost (USD) | calls |",
        "|-----------------|-------:|---------:|-------------:|-------------:|---------:|-----------:|------:|",
    ]
    for o in outcomes:
        r = o.result
        lines.append(
            f"| {o.tier} | {r.presented} | {r.faithful} | {r.faithfulness:.1%} | "
            f"{r.auditability:.1%} | {_cov(r)} | {o.cost_usd:.4f} | {o.n_calls} |"
        )
    lines.append("")
    lines.append("Faithfulness should stay ~100% across tiers (verification is constant); "
                 "the question is whether a stronger extractor raises COVERAGE, and at what cost.")
    return "\n".join(lines) + "\n"


def aggregate_tier_outcomes(per_question: list[list[TierOutcome]],
                            tiers: tuple[str, ...]) -> list[TierOutcome]:
    """Sum TierOutcomes across questions into one per tier (for a multi-question sweep)."""
    from research_system.benchmark import ArmScore

    agg: list[TierOutcome] = []
    for tier in tiers:
        rows = [o for q in per_question for o in q if o.tier == tier]
        if not rows:
            continue
        pres = sum(o.result.presented for o in rows)
        faith = sum(o.result.faithful for o in rows)
        covs = [o.result.coverage for o in rows if o.result.coverage is not None]
        auds = [o.result.auditability for o in rows]
        merged = ArmScore(
            name=f"answer={tier}",
            presented=pres,
            faithful=faith,
            unfaithful=pres - faith,
            auditability=(sum(auds) / len(auds) if auds else 1.0),
            cost_usd=sum(o.cost_usd for o in rows),
            coverage=(sum(covs) / len(covs) if covs else None),
        )
        agg.append(TierOutcome(tier=tier, result=merged,
                               cost_usd=sum(o.cost_usd for o in rows),
                               n_calls=sum(o.n_calls for o in rows)))
    return agg
