# rubric — Design

**What it is:** a thin orchestration layer + a portable two-plane knowledge base that makes AI
coding agents follow *your* standards — consistent conventions, genuine reuse, concise code — by
**grounding the model in exact exemplars and wrapping existing deterministic tools**, not by
reinventing linters.

**Evidence base:** 3 verified research runs (~57 sources) in the Research System corpus
`ai-coding-standards-enforcement/`. Key findings are cited inline as `[F: …]`.

---

## 1. Principles (each backed by the research)

| # | Principle | Finding |
|---|-----------|---------|
| P1 | **Ground, don't rule.** Inject exact in-repo/canonical exemplars before the model writes; exemplars beat static rule files. | RACG works; exemplars-as-ICL > rules; directives+exemplars cut verbosity ~70% |
| P2 | **LLM-grounded-by-determinism.** Deterministic tools extract structured facts → feed the LLM → LLM reasons what rules can't. | Convergent across CodeRabbit/Semgrep/Sourcegraph/Greptile [s018,s040,s044] |
| P3 | **Deterministic = blocking gate; LLM = advisory.** Hard rules block CI; LLM feedback is variable, kept advisory. | Industry pattern; LLM-alone unreliable (88% FP IDORs) [s040,s044] |
| P4 | **Reuse is retrieval.** Surface the existing components relevant to a task or the model reinvents them. | Missing dependency context → redundant reimplementation [s033] |
| P5 | **Compose, don't rebuild.** Wrap ast-grep/Ruff/ESLint/type-checkers; never reimplement analysis. | Contrarian verdict: production systems compose existing tools |
| P6 | **Cap & target retrieval (~5).** Precise contextual/API exemplars, not lookalikes or whole-corpus dumps. | ~5-doc sweet spot; chunk-fragmentation → hallucinated-not-reused methods [s033] |
| P7 | **Full-context to each worker.** If using fresh sub-agents, inject the full spec — isolation alone costs 25–39pp. | Specification Gap [s049] |
| P8 | **Observe-drift → codify.** Triage decisions become rules/exemplars; keep the KB fresh. | Semgrep "memories" [s043]; staleness checks (reference impl) |

**Honest non-goal:** no evidence shows any system reliably makes AI code *indistinguishable from a
senior team*. rubric targets measurable gains in consistency, reuse, conciseness, and hard-rule
adherence — not a proven "senior-team" guarantee.

---

## 2. The two-plane knowledge base

```
Conventions plane (PORTABLE, prescriptive — "how we build", travels across repos)
  rules/        deterministic rule specs (ast-grep/semgrep/ruff/eslint configs) + metadata
  exemplars/    canonical code examples per convention (the ICL grounding)
  conventions/  groups: a convention = rules + exemplars + intent prose

Codebase plane (PER-REPO, descriptive — "what exists / where", drives reuse)
  index/components.json   reusable-component catalog (symbol-level: one entry per top-level
                          function/class with its real signature) + per-file content hashes
  built by `rubric index` (stdlib `ast`, symbol-level NOT chunk-based [s033]); staleness-checked
```

A new project = **inject the portable conventions plane** + **build its own codebase plane**. rubric
serves both via one retrieval interface: `rubric index` populates the codebase plane, and
`rubric context` / the `/rubric` skill auto-load it so the relevant existing components are surfaced
for reuse before the model writes. Test code is excluded — the catalog is the reusable API surface.

---

## 3. Pipeline (components, each a pure function over the KB + target)

```
            ┌─────────────┐
 task ────▶ │ 1. Retrieve │  select ≤5 relevant exemplars + rules + existing components (router; reuse-aware)
            └─────────────┘
                  │  → ContextPack (the "inject before generation" artifact)
                  ▼  (model generates code — rubric grounds it; generation itself is the agent's)
            ┌─────────────┐
            │ 2. Gate     │  DETERMINISTIC, BLOCKING: run tool adapters (ast-grep/Ruff/…) → structured Findings + pass/fail
            └─────────────┘     also extracts facts (signatures/deps/complexity/duplication)
                  │
                  ▼
            ┌─────────────┐
            │ 3. Review   │  LLM, ADVISORY: grounded in (code + gate facts + exemplars) → semantic/intent/abstraction findings
            └─────────────┘     never self-critique-alone; different model than generation
                  │
                  ▼
            ┌─────────────┐
            │ 4. Verify   │  ADVERSARIAL: mechanical fabrication-kill (is the cited span real?) → skeptical
            └─────────────┘     ensemble (a different/stronger tier REFUTES each finding; strict majority to survive)
                  │
                  ▼
            ┌─────────────┐
            │ 5. Verdict  │  combine: blocking gate decides merge; verified advisory annotates; report
            └─────────────┘
                  │
                  ▼
            ┌─────────────┐
            │ 6. Codify   │  observe-drift → propose new rule/exemplar from RECURRING VERIFIED findings (KB grows)
            └─────────────┘
```

### Component contracts
- **Retrieve** — `(task, kb, corpus_index) → ContextPack{exemplars[], rules[], components[]}` (capped, reranked).
- **Gate** — `(target, rules) → GateResult{findings[], blocking_failures}` via injectable `ToolAdapter`s
  (`AstGrepAdapter`, `RuffAdapter`, …; subprocess; graceful if tool absent). Deterministic.
- **Review** — `(target, gate_facts, exemplars, llm) → [AdvisoryFinding]`. LLM grounded; advisory only.
- **Verify** — `(advisory[], code, llm) → [AdvisoryFinding]` survivors with `confidence`. Mechanical
  fabrication-kill (cited span absent → drop, zero model cost) then a skeptical ensemble (default
  judges `(MID, STRONG, MID)`) that must reach a strict majority "real"; ties go to the skeptic.
  Mirrors the Research System's claim verifier — the false-positive guard for LLM advisory output.
- **Verdict** — `(gate_result, verified_advisory) → Verdict{passed, blocking[], advisory[]}`.
- **Codify** — `(recurring_verified_findings) → [CodifyProposal]` (human-approved before joining the KB).

### Native Claude Code integration (§3a)
rubric ships a single cross-platform hook bridge (`rubric hook`, no shell/`jq`) and `rubric init`
wires it into `.claude/`:
- **PostToolUse** (`Edit|Write`) runs the deterministic gate on each edited file; a blocking
  violation exits 2 so Claude Code feeds it back to the model to self-heal. The gate stays the
  blocking plane — now enforced *during* generation, not just in CI.
- **SessionStart** injects the conventions as durable grounding (standards present from turn one).
- **`/rubric` skill** renders the task's ContextPack on demand; **`rubric-reviewer` subagent** runs
  `rubric enforce --verify` read-only. Settings are *merged*, never clobbered. Fail-safe: any hook
  error degrades to a silent no-op — a broken KB never breaks the user's session.

---

## 4. Composition (what rubric wraps, never reimplements)
- **Structural rules:** `ast-grep` / Semgrep (language-agnostic AST patterns) — the primary deterministic substrate.
- **Lint/format/type:** Ruff/ESLint/mypy/tsc — via adapters.
- **Complexity/duplication:** radon/`lizard` / jscpd — for the anti-bloat signal (conciseness is measurable here).
- **LLM:** Claude via the subscription CLI (`claude -p`), same client pattern as the Research System.

rubric owns **orchestration, the two-plane KB, retrieval-grounding, the blocking/advisory split, and the codify loop** — the parts no off-the-shelf tool combines.

---

## 5. Tech & conventions
- **Python core** (subprocess to language-agnostic CLIs). Pydantic contracts (`extra="forbid"`), injectable
  protocols (ToolAdapter, LLMClient) for offline testing — patterns proven in the Research System.
- Subscription-billed LLM via `claude -p` (strip `ANTHROPIC_API_KEY`; never `--bare`).
- Per-phase tests + review gates; nothing merges without its gate green.

---

## 6. Key decisions / open
- **Decided:** name `rubric`; Python core; compose existing tools; deterministic=blocking, LLM=advisory.
- **Decided (resolved in build):**
  - *How rubric plugs into a real agent loop* → **natively, all three surfaces**: CI/pre-commit (git
    hook), Claude Code hooks (PostToolUse gate + SessionStart grounding), and on-demand skill/subagent.
    The one `rubric hook` bridge serves the Claude Code surface cross-platform.
  - *LLM advisory reliability* → an **adversarial Verify stage** (mechanical fabrication-kill + skeptical
    ensemble) filters false positives before findings reach the Verdict, and only **verified recurring**
    findings feed Codify.
- **Done (ROADMAP 6c):** quantitative adherence + anti-bloat measurement (`rubric measure`) — gate-pass
  rate, blocking density, SLOC, cyclomatic complexity, before/after deltas; `radon` wrapped as a
  `MetricAdapter` (P5, graceful if absent).
- **Open (stretch — ROADMAP 6d):** exemplar selection/refresh policy; the fresh-worker delivery loop with
  full-spec injection (the agentic generation side — today rubric grounds/gates an existing agent).
