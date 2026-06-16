# Phase 7 Review — Model-Tier Sweep + Conformal Abstention (stretch)

**Date:** 2026-06-13  **Verdict:** ✅ gate passed (harness + math proven offline)

## What was built
- `llm.py::CostTracker` — wraps any client, accumulates cost/tokens/calls (cost populated on live runs).
- `tier_sweep.py` — runs arm B with the **extraction model varied** (cheap/mid/strong) while holding
  verification constant; scores each with the blind verifier and meters cost. Quantifies "X% cheaper at
  equal faithfulness" (the open-book cost thesis).
- `conformal.py` — split-conformal abstention threshold with a finite-sample coverage guarantee,
  replacing the heuristic support-count gate when a calibration set is available.

## Gate criteria
| Criterion | Result |
|-----------|--------|
| Tier sweep runs each tier, scores + costs | ✅ `test_tier_sweep_runs_each_tier` |
| Cost tracking accumulates | ✅ `test_cost_tracker_accumulates` |
| Conformal threshold math correct | ✅ `test_threshold_quantile_math` (rank ⌊α(n+1)⌋) |
| Coverage guarantee holds on calibration | ✅ ≤ α answerable abstained |
| Degenerate α handled | ✅ -inf (never abstain) |
| Tests | ✅ 98/98 |

## Honesty about the conformal guarantee
Documented in `conformal.py`: the bound is **marginal** (averaged over draws), assumes
**exchangeability** of calibration/test questions, and **degrades under distribution shift / small
calibration sets**. It bounds false-abstention on answerable items; it does not by itself bound
answering an unanswerable item — that is the verification gate's job (which removes unsupported claims
regardless). This matches the literature's caveats on conformal abstention [F-2405.01563].

## Not yet wired (deliberate)
- The conformal threshold is **available but not yet swapped into the orchestrator gate** — doing so
  needs a labeled calibration set of questions (answerable + ground-truth). The heuristic `min_support`
  remains the default until that calibration data exists. Logged as the natural next step after the
  first live benchmark produces labeled outcomes.
- Live tier-sweep numbers (the actual cheap-vs-strong cost delta) require a live run; the harness is
  ready and cost-metered.
