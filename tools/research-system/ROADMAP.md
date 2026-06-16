# Research System — Roadmap

**Status:** Draft for validation. Build begins only after this is approved and the §9 substrate decision in `DESIGN.md` is made.
**Principle:** every phase ships an independently testable deliverable behind an explicit **validation gate**. No phase starts until the prior gate passes. The corpus on disk is the source of truth at every step.

---

## Dependency order

```
P0 Foundations ─▶ P1 Capture ─▶ P2 Retrieve+Answer ─▶ P3 Verify ─▶ P4 Abstain+Gap loop ─▶ P5 Synthesize+E2E ─▶ P6 Benchmark
                                                                                                          └▶ P7 Model-tier + conformal (stretch)
```
P1 is the novel core and the earliest point of real value (variant B exists once P1 ships). P6 is the payoff (the head-to-head). P7 quantifies the cost thesis.

---

## Phase 0 — Foundations & contracts
**Goal:** scaffold + frozen data contracts so every later component is independently testable.
**Build:** repo structure; dependency setup (per §9 decision); JSON schemas for `questions.json`, `manifest.json`, `meta.json`, `claims.jsonl`; folder conventions; tiny fixtures.
**Gate:** schema round-trip tests pass (write → read → validate) for every artifact type; a hand-authored sample `Research/<subject>/` validates clean.
**Depends on:** §9 substrate decision.

## Phase 1 — Capture harness  ◀ novel core
**Goal:** turn a URL list into a faithful, provenance-stamped on-disk corpus.
**Build:** fetch → trafilatura extraction (full text, structure preserved, boilerplate stripped) → `sources/<id>.md` + `meta.json` with both hashes, `capture_status`, dedup by `raw_hash`.
**Gate:** run on `Research/ai-research-accuracy/sources.json` (15 URLs). Verify: (a) every reachable source captured with clean main-body text on manual spot-check; (b) failures recorded with honest `capture_status`, not dropped; (c) re-run is idempotent (hashes stable, no dupes). **Deliverable: the first real variant-B corpus.**
**Depends on:** P0.

## Phase 2 — Retrieve + Answer
**Goal:** answer one sub-question with exact-quote claims from the corpus, in an isolated context.
**Build:** pluggable router (v1: angle-tag + BM25), capped top-k + rerank; per-sub-question answerer emitting `[{claim, source_id, quote}]`; separate context per sub-question.
**Gate:** for a set of sub-questions, ≥X% of emitted quotes are present verbatim in the cited file (mechanical check), and retrieved docs demonstrably contain the answer for spot-checked cases. No context-stuffing (top-k cap enforced).
**Depends on:** P1.

## Phase 3 — Verifier
**Goal:** catch fabricated quotes, unsupported claims, and overreach without over-rejecting valid claims.
**Build:** 6a verbatim quote-match → 6b different-model adversarial grounded judge (may pull surrounding context from the stored file) → 6c ensemble quorum.
**Gate:** on a small labeled set with injected known-good / fabricated-quote / overreach claims: fabricated quotes caught at 100% (mechanical); measure false-reject and false-accept rates and confirm ensemble beats single-judge on false-reject (the 16–17% recall risk).
**Depends on:** P2.

## Phase 4 — Abstention + gap loop
**Goal:** know when not to answer; flag gaps instead of confabulating; chase gaps with bounded follow-up.
**Build:** per-sub-question gate (heuristic quorum v1) → `status`; `gaps.md`; bounded loop-back to discovery for unanswered sub-questions (max-iteration cap).
**Gate:** seed a deliberately unanswerable sub-question — system flags `unanswered` and writes `gaps.md` rather than producing a confident answer; loop terminates within the cap.
**Depends on:** P3.

## Phase 5 — Synthesize + end-to-end
**Goal:** full pipeline producing a traceable cited report; resumable.
**Build:** synthesizer (verified claims only, conflicts surfaced, gaps explicit); orchestrator wiring P1–P4; resume-from-disk.
**Gate:** run end-to-end on `ai-research-accuracy`; every sentence in `synthesis.md` traces to a `source_id` + verbatim quote; killing the run mid-way and resuming reproduces state from disk.
**Depends on:** P4.

## Phase 6 — Benchmark harness  ◀ payoff
**Goal:** the head-to-head the literature lacks.
**Build:** arms A (stock deep-research), B (this pipeline), A′ (B minus persistence+verification); metric scorers (faithfulness, hallucination, coverage, gap-honesty, auditability, cost); blind judge; question set + fact checklists + unanswerable seeds.
**Gate:** produces the A/B/A′ comparison table across all 6 metrics on the `ai-research-accuracy` fixture, with the search-confound controlled by the A′ arm.
**Depends on:** P5.

## Phase 7 — Model-tier sweep + conformal abstention (stretch)
**Goal:** quantify the cost thesis and upgrade abstention from heuristic to calibrated.
**Build:** cheap-vs-strong extraction sweep (verification held constant); conformal calibration of the abstention threshold.
**Gate:** report "X% cheaper at statistically-equal faithfulness" with CIs; conformal threshold holds its target error rate on a held-out calibration set.
**Depends on:** P6.

---

## Cross-cutting validation rules
- A phase is "done" only when its gate passes on the **real** `ai-research-accuracy` corpus, not a toy.
- Every component reads/writes only the §4 contracts — no hidden state — so any phase is re-runnable in isolation.
- Honesty over coverage: anything dropped, skipped, or uncaptured is logged where the gate can see it.

## Decisions still open (resolve before/at the noted phase)
1. **§9 substrate** — Python standalone (recommended) vs Claude-Code-native. *Before P0.*
2. **Which cheap / strong / judge models** to bind to each tier (§6). *Before P2/P3.*
3. **Router v1 exactness** — angle-tag only, BM25, or both; top-k cap value. *In P2, tune in P6.*
4. **Benchmark question set authorship** — reuse `ai-research-accuracy` sub-questions vs author a fresh graded set with trap/unanswerable seeds. *Before P6.*
