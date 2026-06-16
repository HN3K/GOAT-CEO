# Phase 2 Review — Retrieve + Answer (+ LLM substrate)

**Date:** 2026-06-13  **Verdict:** ✅ gate passed

## What was built
- `grounding.py` — `quote_present()`: whitespace-normalized verbatim quote check. The free,
  model-free anti-hallucination floor (verification step 6a), reused by Answer and Verify.
- `retrieve.py` — `Corpus.load()` + `BM25Retriever`: document-level retrieval, capped/ranked
  top-k (no chunking; avoids inverted-U context-stuffing per P4). `Retriever` is a Protocol → pluggable.
- `answer.py` — `answer_subquestion()`: retrieves top-k full docs, asks the model (separate context
  per sub-question) for atomic claims each with an exact quote + source id, parses defensively.
- `llm.py` — injectable `LLMClient`; `ScriptedClient` (fake), `ClaudeCLIClient` (subscription),
  `AnthropicClient` (API). Semantic model tiers resolved per client.

## Gate criteria
| Criterion | Result |
|-----------|--------|
| Emitted quotes present verbatim in cited file (mechanical check) | ✅ `test_answer_emits_grounded_claims_with_verbatim_quote` |
| Fabricated quote caught | ✅ `quote_present=False` flagged (not silently kept) |
| top-k cap enforced; no context-stuffing | ✅ `test_top_k_is_capped` |
| BM25 ranks relevant doc first | ✅ |
| Unanswerable → no claims | ✅ |
| Unknown source id / empty fields dropped | ✅ defensive parse |
| Tests | ✅ 59/59 |

## Subscription directive (mid-phase) — handled
User: bill all LLM calls to the Claude Code subscription. Because the pipeline depends only on the
`LLMClient` Protocol, this was a backend swap, **zero rework** of Phases 2–7.
- Consulted claude-code-guide, then **verified every flag against the installed CLI** — which caught
  the guide's `--bare` recommendation as WRONG: `--bare` forces API-key auth and ignores subscription
  OAuth. Avoided.
- `ClaudeCLIClient`: `claude -p` + stdin prompt + `--system-prompt` + `--output-format json`; strips
  `ANTHROPIC_API_KEY`/`ANTHROPIC_AUTH_TOKEN` from subprocess env (billing-safety, tested).
- **Live-verified**: `echo ... | claude -p --model haiku --output-format json` → `{"result":"OK",
  "usage":{...},"total_cost_usd":...}`, billed to subscription. Client parses all three.

## Issues caught & decisions
1. **Large prompts** (answer prompts embed whole ~8k-word documents) → pass via **stdin**, not argv,
   to avoid command-line length limits. Tested.
2. **Default 30k-token CC system prompt** loads when `--system-prompt` is omitted (seen in smoke test
   cache_creation). Our client always passes `--system-prompt`, which *replaces* it — less overhead,
   no coding-assistant framing bias on research extraction.
3. **No temperature control via CLI** — accepted for interface parity, ignored; model defaults apply.
   Logged as a limitation; Agent SDK is the escape hatch if ever needed.

## Residual / follow-ups
- Live answering over the real corpus is exercised in Phase 5 (needs the subscription, runs there).
- Tool-use is not explicitly disabled in `claude -p`; for pure Q&A prompts it returns a single result.
  If a future prompt risks agentic tool calls, add `--disallowedTools`. Not needed now.
- BM25 router v1 only; embedding/hybrid rerank is a Phase 6 benchmark variable.
