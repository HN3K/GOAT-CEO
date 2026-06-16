# Phase 3 Review — Verifier

**Date:** 2026-06-13  **Verdict:** ✅ gate passed

## What was built
`verify.py` — per-claim adversarial verification in three cheapest-first stages:
- **6a mechanical** `quote_present` → fabricated/absent quote ⇒ `UNSUPPORTED` at zero model cost.
- **6b grounded judge** — adversarial prompt over the claim + quote + `context_window()` excerpt of
  the *stored* source; defaults to `unsupported` under uncertainty.
- **6c ensemble** — `DEFAULT_JUDGES=(MID, STRONG, MID)` vote; `aggregate_votes()` passes only on a
  strict majority of `supported`, ties/splits resolve to the more skeptical verdict.

## Gate criteria
| Criterion | Result |
|-----------|--------|
| Fabricated quotes caught 100% mechanically | ✅ `test_mechanical_kills_fabricated_quote_without_llm` (and 0 LLM calls) |
| Verdicts grounded in stored source, not parametric knowledge | ✅ judges see only `context_window` excerpt |
| Ensemble beats single judge on false-reject | ✅ `test_ensemble_rescues_single_judge_false_rejection` (2 supported override 1 wrong reject) |
| Overreach detected distinctly from unsupported | ✅ `test_overreach_majority_detected` |
| Conservative aggregation (tie never passes) | ✅ `test_aggregate_strict_majority_supported` |
| Tests | ✅ 69/69 |

## Design notes / assessment
- **Mechanical pre-check is the cheap floor**: it kills fabrications before any model runs — the
  highest-leverage, model-independent guard, exactly as the literature motivates.
- **Different model than generation** (answerer = cheap; judges = mid/strong) + ensemble → cancels
  the single-judge over-rejection (16–17% recall) and self-preference bias findings [P6].
- **Grounded, not parametric**: `context_window()` feeds the judge a focused ±1500-char excerpt of the
  stored source around the quote (CiteGuard "retrieve surrounding context" pattern), with a verbatim
  fallback. Verification never relies on the judge's own knowledge.

## Residual / follow-ups
- **Cost**: 3 judges × every claim is the most expensive stage. Phase 5 orchestrator will expose
  `judges` config (and could verify a ranked subset) so subscription spend is tunable.
- **Perspective diversity**: ensemble currently varies the *model*, not the *lens*. A future upgrade
  could give each judge a distinct angle (does-it-reproduce / scope / contradiction). Logged.
- Live judging over the real corpus runs in Phase 5.
