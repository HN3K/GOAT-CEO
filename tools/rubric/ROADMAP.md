# rubric — Roadmap

Phased, each behind a validation gate (tests green on real fixtures). No phase starts until the prior
gate passes. Same discipline as the Research System. Per-phase reviews in `reviews/`.

```
P0 Foundations ─▶ P1 KB store ─▶ P2 Deterministic gate ─▶ P3 Retrieve + ContextPack ─▶ P4 LLM review ─▶ P5 Orchestrate + CLI ─▶ P6a Deployment ─▶ P6b Verify + native Claude + Codify + indexer ─▶ P6c Measurement ─▶ P6d Delivery (stretch)
```

## Phase 0 — Foundations & contracts
**Build:** Python project; pydantic models for `Rule`, `Exemplar`, `Convention`, `Finding`,
`ContextPack`, `GateResult`, `Verdict`; on-disk KB layout (two planes) + path conventions; JSON schemas.
**Gate:** contracts round-trip; drift-rejection (`extra="forbid"`); schema sync. `pytest` green.

## Phase 1 — Knowledge-base store
**Build:** load/save the portable conventions plane (rules + exemplars + conventions) and the per-repo
codebase index; a seed KB (a few real conventions+exemplars); staleness metadata.
**Gate:** author → save → load round-trips; seed KB validates; missing-tool/missing-file handled.

## Phase 2 — Deterministic gate (compose existing tools)
**Build:** `ToolAdapter` protocol; `RuffAdapter` (real, pip-installable), `AstGrepAdapter` (subprocess,
graceful if absent), `FakeAdapter` (tests); run adapters over a target → structured `Finding`s +
blocking pass/fail; fact extraction (signatures/complexity/duplication where available).
**Gate:** Ruff adapter flags a real lint violation in a fixture; ast-grep adapter parses rule output
(mocked); blocking vs non-blocking honored; absent tool degrades gracefully (recorded, not crash).

## Phase 3 — Retrieve + ContextPack
**Build:** router/retriever (BM25 + tag routing, capped ≤5) over exemplars/rules/components; reuse-aware
component selection; assemble the pre-generation `ContextPack`.
**Gate:** for a task, returns the right exemplars + the relevant existing components; cap enforced;
ContextPack serializes to an injectable prompt block.

## Phase 4 — LLM advisory review
**Build:** grounded review via `ClaudeCLIClient` (subscription); prompt = code + gate facts + exemplars;
structured `AdvisoryFinding`s; advisory-only (never blocks); different model than generation.
**Gate:** with a fake client, produces structured advisory findings grounded in provided facts; a
fabricated/unsupported finding is handled; live smoke on one tiny example.

## Phase 5 — Orchestrate + CLI
**Build:** wire Retrieve→Gate→Review→Verdict→(Codify stub); `rubric` CLI (`context`, `check`, `review`,
`enforce`, `kb`); verdict report (blocking decides, advisory annotates).
**Gate:** end-to-end on a fixture repo: `rubric enforce` produces a verdict; blocking gate fails on a
seeded violation; advisory annotates; resumable/inspectable outputs.

## Phase 6a — Deployment integration ✅
**Build:** `git_changed_files` + `rubric check --changed`; `rubric init` scaffolds `.rubric/` + a git
pre-commit hook; ast-grep live; generic config-driven `CommandAdapter` (wrap any linter by config).
**Gate:** `check --changed` fails on a staged violation; live end-to-end on the seed KB + real Ruff.

## Phase 6b — Verify + native Claude integration + Codify ✅
**Build:**
- **Adversarial Verify stage** (`verify.py`): mechanical fabrication-kill → skeptical ensemble
  (default judges `(MID, STRONG, MID)`, strict-majority, ties→skeptic); `--verify` on review/enforce.
  Mirrors the Research System's claim verifier. Survivors carry a `confidence`.
- **Native Claude Code integration**: a cross-platform `rubric hook` bridge + `rubric init` wiring of a
  PostToolUse gate, a SessionStart grounding hook, a `/rubric` skill, and a `rubric-reviewer` subagent;
  settings merged not clobbered; hooks fail-safe to a no-op.
- **Codify loop** (`codify.py` + `rubric codify`): cluster recurring verified findings → `CodifyProposal`s;
  `--draft` has the LLM draft a concrete, schema-valid Rule (+ optional Exemplar); `--write` persists to
  `.rubric/proposals/` for human approval before joining the KB.
- **Codebase-plane indexer** (`index.py` + `rubric index`): symbol-level component extraction (stdlib
  `ast`, not chunk-based [s033]) → `.rubric/index/components.json`; `context`/`/rubric` auto-load it so
  reuse (P4) works without hand-supplied components. Test code excluded; staleness-checked.
**Gate:** verify drops a refuted/fabricated finding and keeps a confirmed one with confidence; hook gates
a violating edit (exit 2) and injects conventions; init scaffolds + merges; codify proposes from recurrence;
index extracts signatures and surfaces the right components for a real task (dogfooded).
**State:** ✅ done — 98 tests; live-validated (`rubric hook`, `rubric init`, `rubric index`, dogfooded).

## Phase 6c — Adherence + anti-bloat measurement ✅
**Build:** `measure.py` + `rubric measure` — gate-pass rate + blocking-violation density (adherence)
and SLOC + cyclomatic complexity (anti-bloat, the measurable face of bloat [s028]) via a `MetricAdapter`
wrapping `radon` (graceful if absent, P5). Reports save to JSON and diff against a baseline
(`report_delta`) for before/after (ungrounded vs rubric-grounded). LLM advisory is opt-in (CI-cheap).
**Gate:** LOC/gate/complexity measured per file; aggregates + per-KLOC density; before/after delta shows
fewer violations and lower complexity as improvement; real radon live.
**State:** ✅ done — 106 tests; live-validated (dogfooded `rubric measure` on own src with real radon).

## Phase 6d — Delivery (stretch)
**Build:** orchestrator + fresh-worker delivery with full-spec injection (mitigate the 25–39pp penalty).
**Gate:** a fresh worker produces grounded code that passes the gate on a fixture task.

## Cross-cutting
- Compose, never reimplement analysis (P5 principle).
- Deterministic = blocking, LLM = advisory (P3 principle) — enforced in the Verdict contract.
- Honest limits: report what's measured; "senior-team-indistinguishable" is not claimed.
