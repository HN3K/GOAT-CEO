# Phase 6 Review — Benchmark Harness

**Date:** 2026-06-13  **Verdict:** ✅ gate passed (harness + offline-proven headline result)

## What was built
`benchmark.py` + `scripts/run_benchmark.py`:
- **Arm B** (`run_grounded_arm`) — decompose → answer → verify → present only SUPPORTED claims.
- **Arm A'** (`run_naive_arm`) — retrieve → answer once → present ALL claims, no verify, no gate
  (= B minus persistence+verification; isolates the variable we added, controlling the search confound
  by sharing one corpus).
- `score_presented` — independent/blind post-hoc verification of each arm's presented claims →
  faithfulness + auditability.
- `compare_arms` / `format_comparison` — B-vs-A' table across a question set.
- Example fixture `Research/ai-research-accuracy/benchmark_questions.json` (5 answerable + 1
  deliberately out-of-corpus question for gap-honesty).

## Gate criteria
| Criterion | Result |
|-----------|--------|
| Produces A/A'/B comparison; A' isolates the variable | ✅ B vs A' on shared corpus |
| Headline metric demonstrated | ✅ `test_compare_arms_b_beats_naive_on_faithfulness`: B 100% faithful / 0 unfaithful, A' 50% / 1 unfaithful |
| Naive presents all, grounded filters | ✅ `test_naive_presents_all_grounded_filters` |
| Mechanical check makes scoring deterministic | ✅ fabricated "helium" quote fails verbatim match regardless of judge |
| Tests | ✅ 90/90 |

## What this measures (and the literature gap it fills)
Open question #1 from the deep-research run: *no published head-to-head of full-text grounded
synthesis vs naive RAG on the same corpus.* This harness is exactly that. The offline test proves the
mechanism: A' ships fabricated claims that B filters; faithfulness and auditability both favor B.

## Scope decisions / honest limitations
- **Arm A (stock deep-research)** is an external Claude Code workflow, not callable from this Python
  harness. Its saved report (`deep-research-raw.json`) can be scored with `score_presented` separately;
  left as a manual add-on rather than automated, to avoid a brittle cross-tool dependency.
- **Live full run not executed** (cost: many pipeline runs × ensemble over big docs). Ready via
  `run_benchmark.py`; this is the user-triggered "after build" step.
- **Coverage & gap-honesty metrics** are partially captured (B presenting 0 claims for the
  out-of-corpus question *is* gap-honesty; A' fabricating *is* the failure). A fuller eval would add
  per-question fact-checklists for a recall number — logged as a fixture-authoring follow-up.
- Faithfulness scoring reuses the same verifier family as Arm B; for a fully independent score, use a
  different `score_judges` set than B's `judges` (the API supports this; defaults overlap).

---

## Readiness hardening (2026-06-13, before live benchmark)

Reviewing Phase 6 as "benchmark-grade" surfaced four gaps, now fixed:
1. **Clean isolation** — arms now share ONE upstream (decompose + answer); they differ *only* at
   verification (B verifies+filters, A' presents all). Differences are attributable to verification
   alone, not to decomposition. (Previously A' also skipped decomposition — conflated.)
2. **Cost in the report** — `CostTracker` wired in; report shows per-arm cost and verification's
   marginal cost. Upstream cost is shared; only verification is charged to B.
3. **Metrics completed** — added **coverage** (vs `must_include` keyword checklist) and **gap-honesty**
   (out-of-corpus questions → present ~0 claims). Fixture now carries `answerable` + `must_include`.
4. **Corpus completed** — s015 (abstention survey) recovered via its arXiv version (2407.18418);
   corpus now **15/15 sources, ~125k words**.

### Live smoke on the REAL corpus (k=2, n=2, 1 judge)
Confirmed the benchmark path runs end-to-end on real large documents with real models:

| metric | B (verified) | A' (unverified) |
|--------|-------------:|----------------:|
| claims presented | 1 | 9 |
| **unfaithful shipped** | **0** | **8** |
| faithfulness | 100% | 11.1% |
| gap-honesty (out-of-corpus) | 1/1 | 1/1 |
| cost (USD) | 0.49 | 0.45 |

The headline holds on real data: the naive arm ships unfaithful claims that verification removes; both
arms correctly abstained on the out-of-corpus question. **Caveat:** the smoke used `judges=1` — exactly
the single-judge over-rejection regime [F-CiteGuard] — so A's "8 unfaithful" is an upper bound; the
default 3-judge ensemble will reject fewer. Run the full benchmark with `--judges 3` for the real
numbers. Cost note: 2 questions at minimal settings ≈ $0.94; the full 6-question run at k=5/3-judges
will be materially higher.
