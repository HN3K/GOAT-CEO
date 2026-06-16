# rubric

> Ground AI coding agents in *your* standards — consistent conventions, real reuse, concise code.

rubric is a thin orchestration layer + a **portable two-plane knowledge base** that makes AI coding
agents follow your team's standards by **grounding the model in exact exemplars and wrapping existing
deterministic tools** (ast-grep, Ruff, ESLint, type-checkers) — *not* by reinventing linters.

It is the build output of a 3-run, ~57-source verified research effort (see the Research System
corpus `ai-coding-standards-enforcement/`). Design rationale and evidence: [`DESIGN.md`](DESIGN.md).

## The idea in one picture

```
  task ─▶ Retrieve (≤5 exemplars + rules + existing components)  ─▶ ContextPack injected before the model writes
                                                                     │
  code ─▶ Gate  (deterministic, BLOCKING: ast-grep/Ruff/… + facts) ─┤
       ─▶ Review(LLM, ADVISORY: intent/abstraction, grounded)       │
       ─▶ Verify(adversarial ensemble: refute false positives)     ─┴─▶ Verdict (gate decides, advisory annotates) ─▶ Codify (recurring drift→rule)
```

- **Deterministic = blocking gate. LLM = advisory.** (The evidence-backed split.)
- **Advisory findings are adversarially verified** before they surface — a skeptical ensemble
  (a different/stronger tier) must affirm each one, mirroring the Research System's verifier.
- **The KB self-evolves:** recurring verified findings are codified — `codify --draft` has the LLM
  draft a concrete rule/exemplar into `.rubric/proposals/` for human approval.
- **Reuse is retrieval:** `rubric index` extracts your repo's reusable components (symbol-level via
  `ast`, not chunks) so `context`/`/rubric` surface them — or the model reinvents them.
- **Compose, don't rebuild:** rubric wraps existing analysis tools; it owns orchestration + the KB.
- **Native to Claude Code:** a PostToolUse hook gates Claude's own edits in real time; a
  SessionStart hook injects the standards; `/rubric` + the `rubric-reviewer` subagent ground & audit.

**Honest scope:** rubric targets measurable gains in consistency, reuse, conciseness, and hard-rule
adherence. No evidence shows any system reliably makes AI code *indistinguishable from a senior team*;
that is not claimed.

## Status

| Phase | What | State |
|-------|------|-------|
| 0 | Foundations & frozen contracts | ✅ done |
| 1 | Two-plane KB store + seed KB | ✅ done |
| 2 | Deterministic gate (Ruff/ast-grep/builtin) | ✅ done |
| 3 | Retrieve + ContextPack | ✅ done |
| 4 | Grounded LLM advisory review | ✅ done |
| 5 | Orchestrate + CLI | ✅ done |
| 6a | Deployment: ast-grep live, generic config adapter, `--changed`, `init` hook | ✅ done (live-validated) |
| 6b | **Adversarial Verify stage** + **native Claude Code integration** (hooks/skill/subagent) + **Codify loop** + **codebase-plane indexer** (reuse) | ✅ done (live-validated) |
| 6c | **Adherence + anti-bloat measurement** (`rubric measure`: gate-pass rate, complexity, LOC, before/after deltas) | ✅ done (**106 tests**; live-validated) |
| 6d | Delivery (orchestrator + fresh-worker, full-spec injection) | planned (stretch) |

Roadmap: [`ROADMAP.md`](ROADMAP.md).

## Use it

```bash
python -m pip install -e ".[gate,retrieval,dev]"   # + install ast-grep separately (optional)

rubric kb                                   # list your conventions
rubric context "add a user service" --language ts   # grounding block to inject BEFORE the model writes
rubric check  path/to/file.py               # deterministic blocking gate (exit 1 on violation) — CI/pre-commit
rubric review path/to/file.py --verify      # grounded LLM advisory review, adversarially verified (subscription)
rubric enforce path/to/file.py --verify     # gate + verified review -> verdict
rubric codify path/to/*.py --draft --write  # propose+draft KB standards from recurring verified findings -> .rubric/proposals/
rubric index                                # build the codebase-plane index of reusable components (powers reuse)
rubric measure src/*.py --save base.json    # quantify adherence + anti-bloat (gate-pass, complexity, LOC); diff with --baseline
rubric init                                 # scaffold .rubric/, git pre-commit, AND native Claude Code hooks/skill/subagent
```

`check`/`enforce` exit non-zero on a blocking failure (use as a CI gate or pre-commit hook).
`review` is advisory and never fails the build. `--verify` runs an adversarial ensemble that drops
false positives (and fabricated code spans). LLM calls bill to the Claude Code subscription.

### Native Claude Code integration (`rubric init`)

`rubric init` wires rubric into Claude Code so it works *while you code*, not just in CI:

- **PostToolUse hook** (`Edit|Write`) → runs the blocking gate on every file Claude edits; a
  violation is fed straight back to Claude to self-heal. Cross-platform (`rubric hook`, no shell/`jq`).
- **SessionStart hook** → injects your conventions as durable context from turn one.
- **`/rubric <task>` skill** → surfaces canonical exemplars + reusable components before you write.
- **`rubric-reviewer` subagent** → read-only auditor running `rubric enforce --verify`.

It *merges* into an existing `.claude/settings.json` (never clobbers); `--no-claude` skips it.

## Develop

```bash
python -m pytest          # gate (112 tests)
```

Python core; subprocess to language-agnostic CLIs; LLM via the Claude Code subscription (`claude -p`).
