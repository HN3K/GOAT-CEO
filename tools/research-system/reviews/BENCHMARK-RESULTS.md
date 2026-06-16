# Benchmark Results — B (verified) vs A′ (unverified)

**Date:** 2026-06-14  **Corpus:** ai-research-accuracy (15 sources, ~125k words)
**Config:** 6 questions, k=3, n=4, 3-judge ensemble (mid/strong). Subscription-billed.

| metric | B (verified) | A′ (unverified) |
|--------|-------------:|----------------:|
| claims presented | 19 | 70 |
| faithful (post-hoc) | 19 | 20 |
| **unfaithful shipped** | **0** | **50** |
| faithfulness | **100%** | 28.6% |
| auditability | 100% | 54.2% |
| coverage (vs checklist) | 43.3% | 86.7% |
| gap-honesty (out-of-corpus) | 1/1 | 1/1 |
| cost (USD) | 6.45 | 3.65 |

## Headline
On 6 real research questions over the same corpus, the **naive arm shipped 50 unfaithful claims out of
70 (71%)**; the **verified arm shipped 0 of 19 (100% faithful)**. Both correctly abstained on the
out-of-corpus question. This quantitatively validates the system's core thesis on real data, under the
full 3-judge ensemble (not just a single-judge smoke).

## What the numbers mean
- **Faithfulness 100% vs 28.6%** — verification removed every unsupported claim; without it, ~7 in 10
  presented claims were unfaithful.
- **Auditability 54.2% (A′)** — nearly half of A′'s claims had no verbatim quote at all. The cheap
  Haiku answerer paraphrases/fabricates quotes heavily when unchecked; the *mechanical* check alone
  (zero model cost) catches most of these before any judge runs.
- **Gap-honesty 1/1 both** — neither arm fabricated an answer to the unanswerable question; the
  answerer itself returned ~no claims out-of-corpus. Verification is the backstop, not the only guard.

## The honest tradeoff: coverage
B's coverage (43.3%) is well below A′'s (86.7%). B is conservative — it drops everything it can't
verify, so it surfaces fewer of the expected checklist facts. This is a real cost of rigor and the
benchmark surfaces it rather than hiding it.

## The actionable finding: extraction is the bottleneck, not verification
A′ produced 70 claims of which only 20 were faithful — the **cheap answerer is noisy (71% junk)**.
Verification catches all the noise, but B's coverage suffers because *good* claims are scarce in noisy
output. The lever is therefore **extraction quality**, not verification:
- Test a stronger answer model (Phase 7 `tier_sweep` is built for exactly this — does Sonnet/Opus
  extraction raise B's coverage at equal faithfulness, and is the cost worth it?).
- Improve the answer prompt to demand longer, exactly-verbatim quotes and fewer speculative claims.
- Consider keeping `overreach`-verdict claims as "qualified" rather than dropping them, to recover
  coverage without shipping unfaithful claims.

## Cost
B $6.45 / A′ $3.65 (A′ = shared upstream; B = upstream + $2.79 verification). Plus blind-scoring spend
(not charged to either arm). Total run ≈ $10–13. Verification roughly doubled the answer-side cost but
eliminated all 50 unfaithful claims.

## Caveats
- Coverage is a keyword-proxy (`must_include` substring match), not a semantic judge — treat as
  directional.
- Single benchmark, one corpus/domain; not a generalization claim.
- Blind scoring reuses the verifier family; for full independence use disjoint `score_judges`.

---

# Tier Sweep — extraction model varied, verification constant (2026-06-14)

**Config:** 2 answerable questions, k=3, n=3, 3-judge ensemble held constant; answer model swept.

| extraction | claims | faithfulness | auditability | coverage | cost (USD) |
|------------|-------:|-------------:|-------------:|---------:|-----------:|
| cheap (Haiku) | 4 | 100.0% | 100% | 16.7% | 2.24 |
| mid (Sonnet)  | 19 | 94.7% | 100% | 62.5% | 5.08 |
| strong (Opus) | 31 | 93.5% | 100% | 83.3% | 9.70 |

## The finding (resolves the benchmark's coverage weakness)
**Extraction quality was the bottleneck, confirmed.** Stronger extraction raises coverage almost
5× (17% → 83%) and quadruples-plus the verified claims surfaced (4 → 31), while auditability stays
100% (the mechanical check guarantees verbatim quotes regardless of tier). The cheap Haiku extractor
was leaving most verifiable facts on the table, exactly as the benchmark suggested.

## On the faithfulness dip (100% → 94.7% → 93.5%)
This is NOT stronger models being less faithful. B only presents claims its verification ensemble
passed; the 94.7/93.5% are from an *independent* scoring ensemble re-judging them, and ~1–2 borderline
claims flipped. Auditability is 100% across all tiers, so these are **judge-disagreement on borderline
cases, not fabrications** — a measure of residual LLM-as-judge noise (~5%), consistent with the
literature. It also means B's "100% faithful" is really "~95–100% by an independent ensemble."

## Recommendation
**Switch the default answer model from cheap → mid (Sonnet).** It nearly 4× the coverage (17→62.5%)
at high faithfulness for ~half the cost of Opus. Opus buys another ~20pts of coverage at ~2× the cost —
worth it only when completeness matters more than spend. Cheap (Haiku) is a false economy here: it
ships almost nothing verifiable.

## Caveat
Only 2 questions, so the small faithfulness dips rest on 1–2 claims. The coverage trend is large and
monotonic and is the robust signal.

---

# Three-arm picture — adding A (stock deep-research)

Scored the saved deep-research report's 11 findings against the corpus (judged faithfulness; auditability
= verbatim traceability into stored sources).

| arm | faithfulness | auditability | notes |
|-----|-------------:|-------------:|-------|
| **A** stock deep-research | 63.6% (judged) | **0%** | verifies internally, but cites external URLs — no verbatim trace into stored text |
| **A′** naive (unverified) | 28.6% | 54.2% | no verification — ships mostly unfaithful claims |
| **B** ours (verified) | ~95–100% | **100%** | grounded + per-claim verified + abstains |

## Read
- **The unique value of B is the *combination*.** Deep-research (A) is reasonably faithful because it
  runs its own adversarial verification — but it is **0% auditable**: you cannot trace any finding to a
  verbatim span in a stored source. That is precisely the gap this project set out to close.
- **A is more faithful than A′** — confirming that *verification* (which A does internally and B does
  explicitly) is what drives faithfulness; the naive arm without it is worst.
- **Only B delivers faithfulness AND auditability AND abstention together.**

## Honest caveats on A's number
A's 63.6% is a *soft* measure: the grounding judge sees only top-k retrieved context with no
pre-supplied quote, so retrieval misses and the higher-level/merged nature of deep-research findings
depress it — it is not purely "deep-research was wrong." The robust, structural number is **auditability
0%**, which is not noisy. Treat A's faithfulness as directional.
