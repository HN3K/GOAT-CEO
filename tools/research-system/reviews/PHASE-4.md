# Phase 4 Review — Abstention + Gap Loop

**Date:** 2026-06-13  **Verdict:** ✅ gate passed

## What was built
`gate.py` — abstention gate + bounded retry:
- `gate_status()` — support-count quorum: 0 supported → UNANSWERED, ≥`min_support` → ANSWERED, else PARTIAL.
- `apply_gate()` — writes each sub-question's status + supported `claim_ids` (only SUPPORTED listed).
- `render_gaps_md()` / `write_gaps()` — gaps.md listing unanswered + partial sub-questions with criteria.
- `run_gap_loop()` — re-gates, retries unresolved via an injected `Resolver`, bounded by `max_iters`,
  stops early when a round is dry.

## Gate criteria
| Criterion | Result |
|-----------|--------|
| Unanswerable sub-question flagged, NOT confabulated | ✅ `test_gap_loop_flags_not_confabulates_when_dry` (stays UNANSWERED) |
| Loop terminates within cap | ✅ `test_gap_loop_respects_max_iters` (exactly 3 calls) |
| Dry discovery stops loop (no infinite retry) | ✅ stops after 1 dry round |
| Only verified (SUPPORTED) claims count toward "answered" | ✅ overreach/unsupported excluded |
| Tests | ✅ 77/77 |

## Design notes
- The no-confabulation property is structural: status reflects *verified support count*; if evidence
  isn't found, the sub-question stays flagged and lands in gaps.md. There is no path that turns an
  unsupported sub-question into an answer.
- `Resolver` is injected → the actual "discover + answer + verify more" wiring is the orchestrator's
  (P5); the loop control + abstention logic is isolated and fully tested here offline.
- Heuristic quorum is v1; conformal calibration (rigorous error bound) is Phase 7.

## Issue caught
- A test substring collision (`"unanswered one"` contains `"answered one"`) — fixed the assertion to
  check by sub-question id. Code was correct; test expectation was wrong.

## Follow-ups
- `min_support` default 2 is a heuristic; tune against the benchmark (P6) and replace with conformal (P7).
