# Remaining Items — Review

**Date:** 2026-06-14  **Verdict:** ✅ all three wired, tested (111 tests)

## 1. Conformal abstention wired into the gate
- `gate_status`/`apply_gate` take an optional calibrated `threshold` that overrides the heuristic
  `min_support`; `OrchestratorConfig.gate_threshold` + `run_research --gate-threshold` expose it.
- `conformal.calibrate_from_labeled` turns labeled sub-questions → threshold; `scripts/run_calibration.py`
  builds a labeled set from the benchmark fixture and writes `calibration.json`.
- **Honest scope:** the benchmark fixture is small, so a calibrated τ is illustrative; with too few
  examples conformal returns -inf (answer-all) and the system keeps the heuristic gate. The wiring is
  complete and tested; it becomes valuable with a larger labeled calibration set.
- Tests: `test_gate_uses_threshold_over_min_support`, `test_calibrate_from_labeled`.

## 2. Stock deep-research scored as arm A
- `external.py`: `load_findings` + `score_external_report` — judges each deep-research finding against
  the corpus (grounding judge, no pre-supplied quote) and measures verbatim auditability.
- **Live result (11 findings):** A = 63.6% judged-faithful, **0% auditable**. Three-arm picture:
  A faithful-but-unauditable, A′ worst, B faithful+auditable. See `BENCHMARK-RESULTS.md`.
- `scripts/run_external_score.py`; tests offline. A's faithfulness is directional (judge sees only
  retrieved context); auditability 0% is the robust structural result.

## 3. Web discovery wired into the gap loop
- `discover.py`: `Searcher` protocol; `ClaudeWebSearcher` (best-effort `claude -p` web search →
  JSON/scraped URLs); `make_discovery_resolver` — unanswered sub-question → search → capture to disk
  (Phase-1 pipeline, ids `d001…`) → extend corpus → re-answer → re-verify.
- Wired into `run_research(searcher=, max_gap_iters=)` and `run_research.py --discover N`.
- Tests: empty corpus → discover → capture → **ANSWERED** end-to-end; dry search → stays flagged
  (no confabulation). Decoupled from `OrchestratorConfig` to avoid a circular import.
- **LIVE CAVEAT (documented in-module):** `claude -p` web-search reliability and clean URL extraction
  are not guaranteed; the model may return few/no or knowledge-based URLs. The mechanical capture step
  still records honest `capture_status`. Validate live before relying on it for production research.

## Net
The system now covers the full lifecycle: capture (incl. discovery for gaps) → retrieve → answer →
verify → calibrated-or-heuristic abstention → synthesize, plus a 3-arm benchmark (A/A′/B) and a
tier sweep. Remaining work is data/validation, not architecture: a larger conformal calibration set,
and live validation of the web searcher.
