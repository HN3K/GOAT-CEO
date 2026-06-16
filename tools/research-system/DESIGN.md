# Research System — Design

**Status:** Draft for validation. No build until this and `ROADMAP.md` are approved.
**Last updated:** 2026-06-13
**Evidence base:** `Research/ai-research-accuracy/synthesis.md` (deep-research run `wn082ern1`). Findings cited inline as [F#].

---

## 1. Problem & goal

AI web research is fast at gathering breadth but loses fidelity at synthesis: important detail is dropped and hallucinations slip in because everything is squeezed through a model's compression into a concise answer. The model's output is trusted without a way to trace each statement back to a source.

**Goal:** a research system where every answer is (a) grounded in full source text captured to disk, (b) attributed at the claim level with an exact quote, (c) verified against the stored source by a different model, and (d) abstained-on and flagged when support is insufficient — producing an auditable, low-hallucination research artifact that can be re-queried without re-fetching.

**Non-goal (stated honestly):** this system guarantees *faithfulness to sources and full provenance*. It does **not** adjudicate whether the sources themselves are true. A claim faithfully grounded in a low-quality source is still only as good as that source. We surface source quality so the synthesizer and the human can weigh it; we do not claim to detect false-but-well-sourced information. See §8.

---

## 2. Design principles (each backed by the research)

| # | Principle | Evidence |
|---|-----------|----------|
| P1 | Capture **full** boilerplate-stripped text, never pre-judged excerpts. Relevance selection is deferred to query time. | Full-text grounding beats snippet/abstract grounding ~12pts [F-CiteGuard] |
| P2 | Store **provenance + content hashes** per source for audit and staleness/dedup. | Auditability requirement; correctness≠faithfulness [F-2412.18004] |
| P3 | **Decompose** the question into atomic sub-questions answered in **separate contexts**. | Factored decomposition improves faithfulness over CoT [F-2307.11768] |
| P4 | **Targeted, capped, reranked** retrieval per sub-question — do NOT context-stuff, even with a 1M window. | Lost-in-the-middle U-curve persists in long-context models; inverted-U on passage count; stronger retriever can worsen it [F-LostInMiddle, F-ICLR2025] |
| P5 | Every claim carries an **exact quoted span** from a specific stored source. | Enables mechanical verification; claim-level attribution [F-FACTS] |
| P6 | Verify each claim: **mechanical quote-match → grounded judgment by a *different* model → ensemble vote**, against stored full text. | Single LLM judge = 16–17% recall (over-rejects); self-preference +3.23%; judge must be retrieval-grounded [F-CiteGuard, F-FACTS] |
| P7 | **Claim-level gate**: a sub-question answer is only "accurate" if *every* information-bearing claim is grounded; otherwise flag. | FACTS all-or-nothing grounding [F-FACTS] |
| P8 | **Abstain and flag** below a calibrated confidence threshold; never confabulate from weak returns. Loop back to search for gaps. | Conformal abstention gives bounded error rate [F-2405.01563] |
| P9 | **Tier models by stage** — cheap for open-book/mechanical work, strong for reasoning. | Open-book shifts small models from recall to copy; fine-tuned detector rivals GPT-4 [F-RAGTruth] |

---

## 3. Architecture — components & contracts

The pipeline is a sequence of components, each a pure function over on-disk files. This makes every stage independently testable, the whole pipeline resumable, and the corpus re-queryable without re-capture.

```
        ┌──────────────┐
  Q ───▶│ 1. Decompose │──▶ questions.json (sub-questions + success criteria)
        └──────────────┘
               │
               ▼
        ┌──────────────┐
        │ 2. Discover  │──▶ candidate URLs per sub-question (fan-out WebSearch, URL-dedup)
        └──────────────┘
               │
               ▼
        ┌──────────────┐   ◀── THE NOVEL CORE
        │ 3. Capture   │──▶ sources/<id>.md  +  sources/<id>.meta.json   (trafilatura, hashes, dedup)
        └──────────────┘
               │
               ▼
        ┌──────────────┐
        │ 4. Catalog   │──▶ manifest.json (source catalog + sub-question routing tags)
        └──────────────┘
               │
               ▼ (per sub-question, separate context)
        ┌──────────────┐
        │ 5. Retrieve  │──▶ capped top-k full docs, reranked   (router: angle-tag + BM25; pluggable)
        │  + Answer    │──▶ draft claims [{text, source_id, quote}]
        └──────────────┘
               │
               ▼ (per claim)
        ┌──────────────┐
        │ 6. Verify    │──▶ 6a mechanical quote-match → 6b grounded judge (different model) → 6c ensemble vote
        └──────────────┘     verdict ∈ {supported, overreach, unsupported}  → claims.jsonl
               │
               ▼ (per sub-question)
        ┌──────────────┐
        │ 7. Gate /    │──▶ status ∈ {answered, partial, unanswered}; unanswered → gaps.md + loop to (2)
        │  Abstain     │
        └──────────────┘
               │
               ▼
        ┌──────────────┐
        │ 8. Synthesize│──▶ synthesis.md (verified claims only; conflicts surfaced; gaps explicit; every line traceable)
        └──────────────┘

  ┌────────────────────────────────────────────────────────────────────┐
  │ 9. Benchmark harness (separate): arms A (stock deep-research), B     │
  │    (this pipeline), A′ (B minus persistence+verification). Blind     │
  │    judge over faithfulness / hallucination / coverage / gap-honesty  │
  │    / auditability / cost.                                            │
  └────────────────────────────────────────────────────────────────────┘
```

### Component contracts (inputs → outputs)

- **1. Decompose** — `question:str` → `questions.json`: `[{id, text, success_criteria}]`. Strong model.
- **2. Discover** — `sub-questions` → candidate `[{url, title, found_by_subq, quality_guess}]`, URL-deduped. Web search.
- **3. Capture** — `urls` → for each: `sources/<id>.md` (cleaned full text, markdown structure preserved) + `sources/<id>.meta.json` (§4). Mechanical (trafilatura). Dedup by `raw_hash`. **No model.**
- **4. Catalog** — captured sources → `manifest.json`: run metadata + `[{id, meta, candidate_subq_ids}]`.
- **5. Retrieve+Answer** — `(sub-question, corpus)` → top-k docs (capped, reranked) → `[{claim, source_id, quote}]`. Runs in an isolated context per sub-question. Cheap model viable (open-book).
- **6. Verify** — `claim` → `{verdict, judge_votes}`. 6a verbatim quote present in `sources/<id>.md`? (normalized string match — fabrication catch, free). 6b different-model adversarial judge: does the span *support* the claim without overreach? May pull surrounding context from the stored file (CiteGuard `ask_for_more_context` pattern). 6c ensemble quorum (cancel self-preference). Appended to `claims.jsonl`.
- **7. Gate/Abstain** — verified claims per sub-question → `status`. Threshold heuristic (quorum) at first; conformal calibration as a later upgrade. Unanswered/partial → `gaps.md`, optional loop to (2) bounded by a max-iteration cap.
- **8. Synthesize** — answered sub-questions → `synthesis.md`. Strong model. Only `supported` claims; surfaces source conflicts; states gaps explicitly.

---

## 4. On-disk layout & schemas

```
Research/<subject-slug>/
  manifest.json          run metadata, sub-question list + status, source catalog
  questions.json         [{id, text, success_criteria, status, claim_ids}]
  sources/
    s001.md              cleaned FULL article body (boilerplate removed, structure kept)
    s001.meta.json       provenance sidecar (below)
  claims.jsonl           one line per claim: {id, subq_id, text, source_id, quote, verdict, judge_votes}
  gaps.md                unanswered / partial sub-questions → follow-up needed
  synthesis.md           final cited report
```

**`meta.json` sidecar** (audit + dedup + staleness):
```json
{
  "id": "s001",
  "url": "...", "final_url": "...",
  "title": "...", "author": "...", "published_date": "...",
  "fetched_at": "2026-06-13T21:54:00Z",
  "content_hash": "sha256:...",     // cleaned text — detects changed content on re-run
  "raw_hash": "sha256:...",         // original HTML — dedups same article via different URLs
  "word_count": 2310, "language": "en",
  "http_status": 200,
  "capture_status": "ok",           // ok | empty | paywall | fetch_error | js_required
  "extraction_method": "trafilatura@<ver>"
}
```
A failed capture is **recorded, not silently dropped** — `capture_status` ≠ ok means the source is visible to the gate, so missing evidence can't masquerade as covered.

---

## 5. Retrieval strategy (the part I corrected)

Earlier I suggested "1M context, load everything." The research refutes that [P4]. Final design:

- Granularity stays at the **whole document** (no chunking loss) — but we **select** which documents reach each sub-question's context rather than loading the whole corpus.
- The **router** is a pluggable interface. v1 = `found_by_subq` angle tag (free, from discovery) + BM25 over full text. Optional v2 = document-level embedding similarity. Vector RAG with sub-document chunking is a **last resort**, only if a corpus outgrows the context budget — and even then, retrieve whole docs.
- **Cap top-k and rerank** per sub-question to stay on the good side of the inverted-U; do not maximize recall blindly.
- Pluggability matters because retrieval strategy is itself a **benchmark variable** (§7, A′ ablation).

---

## 6. Model tiering (cost)

| Stage | Task type | Tier |
|-------|-----------|------|
| Decompose | reasoning | strong |
| Discover (query gen) | light | cheap |
| Capture | mechanical | **none** (trafilatura) |
| Route/retrieve | mechanical/light | cheap or none |
| Answer (extract+quote) | open-book extractive | **cheap** |
| Verify 6a quote-match | string compare | **none** |
| Verify 6b/6c judge | subtle judgment | mid/strong, **different model**, ensemble |
| Synthesize | reasoning | strong |

Token volume concentrates in Capture (no model) and Answer (cheap), so the strong-model stages are a small fraction of cost. Model tier becomes a **benchmark axis** to quantify "X% cheaper at equal faithfulness."

---

## 7. Benchmark design

Addresses the literature's **open question #1** (no published head-to-head of full-text grounded synthesis vs chunked RAG on the same corpus).

- **Arms:** A = stock deep-research skill. B = this pipeline. **A′ = B minus persistence+verification** (and/or minus targeted retrieval) — isolates the variable we added, controlling for search-quality confound between A and B.
- **Fixture:** the `ai-research-accuracy` topic to start; question set with checkable answers, seeded with (a) commonly-misreported "trap" facts and (b) deliberately unanswerable sub-questions.
- **Metrics:** (1) faithfulness — % claims supported by cited source [headline]; (2) hallucination rate — % unsupported/fabricated; (3) coverage — vs per-question fact checklist; (4) gap-honesty — flags vs confabulates on unanswerable parts; (5) auditability — time to trace a claim to a source span; (6) cost/latency/tokens.
- **Grading:** blind; separate judge model (different from any generator) with ground-truth sources in hand; ensemble to limit judge bias.

---

## 8. Logical validation — failure-mode walkthrough

Tracing a question end-to-end and stress-testing each stage:

1. **Capture fails (paywall/JS-rendered):** `capture_status` records it; source visible to gate; never silently treated as covered. ✅
2. **Answerer fabricates a quote:** verify 6a verbatim match fails → claim killed at zero model cost. ✅
3. **Answerer overreaches a real quote:** verify 6b grounded judge flags `overreach` → demoted to gap. ✅
4. **Single judge over-rejects a valid claim** (the 16–17% recall risk): mitigated by mechanical pre-check + ensemble quorum + allowing the judge to pull surrounding context from the stored file. ✅ (residual risk tracked — measure false-reject rate in Phase 3)
5. **Relevant doc missed by retrieval:** sub-question fails the gate → `partial/unanswered` → loop back to discovery (bounded). ✅
6. **Context overload / lost-in-the-middle:** prevented by capped top-k + separate-context per sub-question [P3,P4]. ✅
7. **Source is well-written but wrong:** ⚠️ **Not solved.** System certifies faithfulness-to-source + provenance, not truth. Mitigation: surface `quality` tags, prefer primary sources, surface cross-source conflicts in synthesis, let the human adjudicate. Stated as an explicit non-goal (§1).
8. **Two URLs, same article:** `raw_hash` dedup. ✅
9. **Re-run after a page changed:** `content_hash` mismatch flags drift. ✅
10. **Infinite gap-loop:** bounded by max-iteration cap; remaining gaps reported honestly rather than chased forever. ✅

Conclusion: every failure mode is either handled or explicitly declared out of scope. No finding in the research contradicts this architecture; the two residual risks it names (single-judge over-trust, context over-stuffing) are directly engineered against by P4 and P6.

---

## 9. Key open decision (needs sign-off before Phase 0)

**Implementation substrate** — two viable philosophies:

- **(I) Standalone Python harness** using the Anthropic SDK (web-search tool) + trafilatura. Portable, reproducible, clean model-tier swapping, not locked to Claude Code, easiest to benchmark rigorously. **Recommended.**
- **(II) Claude-Code-native** skill/workflow reusing the agent harness, WebSearch/WebFetch, like deep-research itself. Faster to prototype, but couples capture fidelity to WebFetch (which may pre-summarize) and complicates cheap-model swapping and reproducible benchmarking.

**Recommendation: (I) Python core, with an optional thin Claude Code `/research` wrapper later.** Rationale: capture fidelity needs raw fetch + trafilatura (not WebFetch's processed output); benchmarking and model-tiering need deterministic, swappable model calls. Decision belongs to the user — it shapes Phase 0.

**DECIDED (2026-06-13): Option (I) Standalone Python.** Anthropic SDK (web-search tool) + trafilatura. Roadmap Phase 0 proceeds on this basis.

### 9.1 Contract reconciliation (sub-question status ownership)
To avoid duplicated state: **`questions.json` owns the original question + sub-questions + their status + claim refs** (written by Decompose, updated by Gate). **`manifest.json` owns run metadata + the source catalog** (id → capture status + candidate sub-question ids). Sub-question status lives only in `questions.json`.

### 9.2 LLM access — Claude Code subscription (decided 2026-06-13)
All model calls bill to the user's **Claude Code subscription**, not a pay-per-token API key. The pipeline talks to an injectable `LLMClient` (`llm.py`), so the backend is a swap, not a rewrite:
- **`ClaudeCLIClient` (default for live runs)** — shells out to `claude -p --model <alias> --system-prompt <sys> --output-format json`, prompt piped via **stdin** (answer prompts embed whole documents → too big for argv). Parses `result` + `usage` + `total_cost_usd`.
- **Billing safety:** the subprocess env is stripped of `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` (their presence silently switches billing to the paid API). **`--bare` is forbidden** — verified against the installed CLI, it forces API-key auth and ignores subscription OAuth. Passing `--system-prompt` also replaces the ~30k-token default coding system prompt, cutting overhead and removing assistant-framing bias.
- **`AnthropicClient`** — pay-per-token fallback (needs a key); not used by default.
- **Model tiers** are semantic tokens (`strong`/`mid`/`cheap`) resolved per client → CLI aliases `opus`/`sonnet`/`haiku` or API ids. Verified live: `claude -p` stdin+json works, billed to subscription.
- **Limitation:** the CLI exposes no temperature/max_tokens; model defaults apply (accepted for parity, ignored). If fine-grained sampling control is ever needed, the Claude Agent SDK is the alternative.
