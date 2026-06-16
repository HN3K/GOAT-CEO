# rubric — Build Review (Phases 0–5)

**Date:** 2026-06-14  **Verdict:** ✅ complete working core, 47 tests green.

The MVP implements the full evidence-backed pipeline (DESIGN.md), composing existing tools rather than
reinventing them.

| Phase | Delivered | Gate |
|-------|-----------|------|
| 0 | Frozen contracts (Rule/Exemplar/Convention/ContextPack/Finding/GateResult/Verdict) with the blocking-vs-advisory split; two-plane layout | round-trip + drift-rejection |
| 1 | KB store (files = source of truth) + real seed KB (3 conventions spanning deterministic-blocking + LLM-advisory) | round-trip, ref-validation, real seed loads |
| 2 | Deterministic gate: `RuffAdapter` (real), `AstGrepAdapter` (subprocess), `RubricBuiltinAdapter`; graceful on missing tools | real Ruff flags F401; missing tool recorded not fatal |
| 3 | Retrieve + ContextPack (BM25, capped ≤k, reuse-aware) + injectable render | ranks right exemplars/components; MUST vs should surfaced |
| 4 | Grounded LLM advisory review (runs only LLM rules; never blocks; grounded in gate facts + exemplars) | advisory-only; billing-safe CLI client |
| 5 | Orchestrate (`enforce`, `build_context`) + CLI (`context/check/review/enforce/kb`) | end-to-end on real seed KB + real Ruff; correct exit codes |

## Principle adherence (DESIGN §1)
- **P2 LLM-grounded-by-determinism** — review is fed gate facts + exemplars, never self-critique alone. ✓
- **P3 deterministic=blocking, LLM=advisory** — enforced in the `Finding.enforcement`/`Verdict` contract; LLM findings are hard-coded ADVISORY. ✓
- **P5 compose, don't rebuild** — gate wraps Ruff/ast-grep as subprocesses; rubric owns orchestration + KB only. ✓
- **P6 cap & target** — retrieval capped ≤k. ✓
- **Honest scope** — no "senior-team" claim anywhere; README states the limit. ✓

## Verified live
`rubric kb` lists conventions; `rubric context` renders the grounding block (conventions + exemplars);
`rubric check` runs Ruff as a blocking gate (F401 → exit 1) with ast-grep gracefully recorded missing.

---

# Phase 6b — Verify + native Claude Code integration + Codify

**Date:** 2026-06-15  **Verdict:** ✅ complete, **89 tests green** (was 59); live-validated; dogfooded.

Closes the two gaps that blocked "ready to be used": LLM advisory output was unverified, and rubric
only plugged into CI/git — not into Claude Code itself.

| Area | Delivered | Gate |
|------|-----------|------|
| **Adversarial Verify** (`verify.py`) | Mechanical fabrication-kill (cited span absent → drop, zero model cost) → skeptical ensemble (default judges `(MID,STRONG,MID)`, strict-majority "real", ties→skeptic); survivors carry `confidence`. Wired as `enforce(..., verify=True)` + `--verify`. Mirrors the Research System's `verify.py`. | fabricated span killed w/o model call; majority-real kept w/ confidence; majority-refuted dropped |
| **Native Claude Code** (`hook.py`, `integration.scaffold_claude`) | One cross-platform `rubric hook` bridge (no shell/`jq`) handling PostToolUse (blocking gate, exit 2 → self-heal), SessionStart + UserPromptSubmit (context injection). `rubric init` scaffolds + **merges** `.claude/settings.json` hooks, a `/rubric` skill, a `rubric-reviewer` subagent. | hook blocks a violating edit / passes clean / no-ops non-code & broken KB; init merges without clobber; idempotent |
| **Codify loop** (`codify.py`, `rubric codify`) | Cluster recurring **verified** advisory findings → `CodifyProposal`s (rule-tighten / rule-new) with evidence; human-approved before joining KB. | below-threshold proposes nothing; recurring rule → tighten; recurring un-ruled → new; sorted by recurrence |
| **Codebase-plane indexer** (`index.py`, `rubric index`) | Symbol-level extraction (stdlib `ast`, NOT chunk-based [s033]) of top-level public functions/classes + real signatures → `.rubric/index/components.json` + per-file hashes (staleness). `context`/`/rubric` auto-load it so reuse (P4) works out of the box; test code excluded; `init` builds it. | signatures/docstrings extracted; private + test code excluded; save/load round-trip; staleness detected; dogfood surfaced the right components for a real task |

## Principle adherence
- **P2/P3 reinforced** — advisory findings now pass an *external* adversarial check (not self-critique)
  before surfacing; the blocking gate is never verified (deterministic facts need no second opinion). ✓
- **P5 compose** — the hook bridge wraps the existing gate; no analysis reimplemented. ✓
- **P8 observe-drift→codify** — implemented: verified recurrence is the codify trigger. ✓
- **Robustness** — hooks are fail-safe (any error → silent no-op; a broken KB never breaks a session);
  Windows-safe (Python bridge, not bash+jq); settings merged not clobbered. ✓

## Verified live
`rubric hook` (SessionStart injects conventions JSON; PostToolUse exit 2 + feedback on an F401 file;
exit 0 clean / non-code / missing path); `rubric init` scaffolds all five artifacts and merges settings;
`rubric codify` runs end-to-end; `rubric check` (dogfood) passes on all new source (ruff+ast-grep+builtin live).

---

# Phase 6c — Adherence + anti-bloat measurement

**Date:** 2026-06-15  **Verdict:** ✅ complete, **106 tests green**; live-validated with real radon.

Turns "is the AI's code clean?" into numbers — the metric behind the quality goal.

| Delivered | Gate |
|-----------|------|
| `measure.py` + `rubric measure`: gate-pass rate + blocking-per-KLOC (adherence); SLOC + cyclomatic complexity (anti-bloat [s028]) via `RadonAdapter` behind a `MetricAdapter` protocol (graceful if radon absent, P5); `report_delta` for before/after; reports save/load as JSON; LLM advisory opt-in (CI-cheap). `FileMetrics`/`AdherenceReport` contracts. | per-file LOC/gate/complexity; aggregates + per-KLOC density; delta shows fewer violations + lower complexity as improvement; real radon live; non-code files skipped |

## Verified live
`rubric measure src/rubric/*.py` over rubric's own 16 files → 100% gate-pass, 0 blocking, 1775 LOC,
max complexity 13 (real radon); a seeded-bloat delta correctly reported complexity 13→25 as a regression.

## Codify auto-draft (completes the evolve-the-framework loop)
`rubric codify --draft` has the LLM draft a concrete, schema-valid `Rule` (+ optional `Exemplar`) per
proposal — deterministic ast-grep when mechanizable, else an LLM advisory rule — grounded in the
evidence (and the existing rule, for tighten). `--write` persists to `.rubric/proposals/` for human
approval before promotion to the KB. Offline-tested (parse/slugify/malformed/tighten-grounding/save)
**and live-validated**: a real `claude -p` call drafted a deterministic bare-except rule + exemplar.

## Still deferred (Phase 6d, stretch)
- **Delivery**: orchestrator + fresh-worker agents with full-spec injection (mitigate the 25–39pp
  coordination penalty [s049]) — the agentic generation loop (today rubric grounds/gates an existing agent).
- **Indexer / metrics breadth**: Python ships (stdlib `ast`, radon); other languages (TS/JS/Go via
  ast-grep extraction / lizard for complexity) are a follow-up — the `Extractor`/`MetricAdapter` protocols are the seams.
- Real `claude -p` review/verify smoke (needs subscription; offline-tested via ScriptedClient).
