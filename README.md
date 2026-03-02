<div align="center">

# GOAT-CEO

### One session. Every repo. Total coordination.

**The multi-repo orchestration layer for Claude Code agent teams.**

Point it at your repos. Describe the work. Walk away.<br>
GOAT-CEO spawns parallel agent pipelines, routes cross-repo changes,<br>
and delivers reviewed, indexed, tested code — across every repo at once.

[![Built for Claude Code](https://img.shields.io/badge/Built_for-Claude_Code-7C3AED?style=for-the-badge&logo=data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHdpZHRoPSIyNCIgaGVpZ2h0PSIyNCIgdmlld0JveD0iMCAwIDI0IDI0IiBmaWxsPSJub25lIiBzdHJva2U9IndoaXRlIiBzdHJva2Utd2lkdGg9IjIiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCI+PHBhdGggZD0iTTEyIDJMMiA3bDEwIDUgMTAtNS0xMC01eiIvPjxwYXRoIGQ9Ik0yIDE3bDEwIDUgMTAtNSIvPjxwYXRoIGQ9Ik0yIDEybDEwIDUgMTAtNSIvPjwvc3ZnPg==)](https://docs.anthropic.com/en/docs/agents-and-tools/claude-code/overview)
[![Experimental](https://img.shields.io/badge/Status-Experimental-orange?style=for-the-badge)](https://github.com/HN3K/GOAT-CEO)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue?style=for-the-badge)](LICENSE)

</div>

---

## The Problem

You're the human switchboard.

You have repos that need work — maybe they share an API, maybe they don't. Either way, you're juggling terminals, copy-pasting context between sessions, manually checking that changes in one place didn't break something in another, and hoping you didn't miss anything. Every repo is its own isolated world, and you're the only bridge between them.

This doesn't scale to 2 repos. It definitely doesn't scale to 5.

**GOAT-CEO replaces the switchboard with an executive.**

One session coordinates everything. Repos that share surfaces get automatic cross-repo routing. Repos that don't share anything get perfect isolation. Simple tasks don't waste a full agent pipeline. Complex tasks get a structured one. You describe what needs to happen. The CEO figures out how.

---

## What It Looks Like

```
SESSION DASHBOARD                                              2026-03-01T14:32:00Z
════════════════════════════════════════════════════════════════════════════════════

api — Fix 3 web UI bugs ───────────────────────────────────────────────────────────
  █████▓░░  5/7 Implementation (running) | Batch 2/4 | Agents: api-implementer-2
  ├── Research: 3 found (1C 2M) — resolved > clean pass
  └── Review: pending

web — Verify auth tokens ──────────────────────────────────────────────────────────
  ▓  Assessment (done) — No code changes needed.              ← no pipeline wasted

db — Migrate user schema ──────────────────────────────────────────────────────────
  ██▓░░░░░  2/7 Research, Iter 1 (running) | Agents: db-researcher-codebase, -tech
  └── Research: I1 in progress...

jvg — CSharpNormalizer ────────────────────────────────────────────────────────────
  ████████  7/7 Complete | 4 files changed | commit: 3200e25
  ├── Impl: 4/4 batches
  ├── Review: A: PASS, B: PASS
  └── Research: 5 found (1C 3M 1m) — resolved > clean pass

Cross-Repo ────────────────────────────────────────────────────────────────────────
  1 outbound (1 confirmed) | 1 inbound | 0 pauses | 0 conflicts

════════════════════════════════════════════════════════════════════════════════════
```

Four repos. Parallel pipelines. One terminal. Everything tracked.

The `web` repo didn't need code changes — the Overseer figured that out on its own and resolved it directly. No agents spawned. No tokens wasted. The CEO is frugal.

---

## What You Can Do With It

**"I need to build matching components across two repos."**<br>
Build an API endpoint in one repo and its client in another — simultaneously. Cross-repo communication means both teams see the same contract from day one. A cross-repo reviewer verifies alignment at the end. No integration surprise.

**"I have 5 unrelated projects and I don't want 5 terminals."**<br>
Declare them isolated. GOAT-CEO runs them all in parallel with zero cross-contamination. Each repo gets its own agent team, its own pipeline, its own progress bar — all in one session. You watch the dashboard instead of alt-tabbing between windows.

**"It's probably a one-line fix, I don't need a whole pipeline for this."**<br>
You don't get one. The Overseer reads the code first and assesses what's actually needed. Simple fix? It handles it alone — one agent instead of eight. The full pipeline only activates when the task genuinely requires planning, research, implementation, and review.

**"I want a structured implementation with real quality gates."**<br>
The 6-phase pipeline runs a research loop that iterates until zero issues remain, batches implementation for parallel execution, and dual-reviews everything with two independent reviewers. If the index isn't updated, the review fails. No shortcuts.

**"I just want a plan — I'll decide about implementation later."**<br>
Run `/goat-team:goat-plan`. You get a fully researched plan with all risks identified and resolved. No code touched. Review it yourself and decide when to proceed.

**"I made changes manually. I want them reviewed properly."**<br>
Run `/goat-team:goat-review`. Two independent reviewers verify your work against the plan and check index coverage. Same quality gate as the full pipeline.

**"Verify that the auth flow is correct — I don't need changes, I need answers."**<br>
The Overseer investigates directly. Reads code, runs tests, traces the flow, reports findings. No pipeline agents spawned. Assessment-First handles investigation, verification, and diagnostic tasks without burning resources.

**"This repo doesn't have any of the indexing or tooling set up."**<br>
Point GOAT-CEO at it anyway. Auto-bootstrap detects the language, scaffolds the Codebase-Index, installs the CLI tools, and validates — automatically. Or let the Overseer set it up through the pipeline if you want more control.

**"My session crashed halfway through a complex task."**<br>
Every phase writes artifacts to `agent-workspace/` — plan, research log, manifest, review log. If an Overseer runs out of context, the CEO reads the artifacts, cleans up orphaned agents, and spawns a fresh Overseer that resumes exactly where the last one stopped. This is expected, not an error.

**"I used GOAT-CEO yesterday on these same repos."**<br>
Quick Start mode. The repo registry remembers your repos, capabilities, and relationship groups. Select by number, skip registration, go straight to work.

---

## The CEO is Frugal

This isn't "throw agents at everything and hope for the best." The CEO hates wasting tokens.

Every task goes through the **Assessment-First Protocol** before a single pipeline agent is spawned:

1. The Overseer receives the task and independently reads the code, runs tests, checks logs, and evaluates what's actually needed.
2. **If no code changes are needed** — investigation, verification, diagnosis — the Overseer resolves it directly and reports back. Done. One agent, zero pipeline overhead.
3. **If it's a narrow fix** — the Overseer requests only what's necessary from the CEO. Not every task needs two researchers, three implementers, and dual review.
4. **If it genuinely requires the full pipeline** — planning, research, implementation, review — then and only then does the CEO authorize the full agent team.

The dashboard shows this in action. When you see `Assessment (done) — No code changes needed`, that's a task that would have spawned 8+ agents in a naive system. The CEO said no.

**Model Profiles** give you another cost lever. Default uses Opus where it matters (planning, research) and Sonnet where speed matters (implementation, review). Economy mode drops to Sonnet/Haiku. Premium goes full Opus. Or pick per role.

---

## Architecture

```
Your Claude Code session (CEO)                       ← sole spawn authority
│
├── ceo-scribe            Dedicated logger (Haiku, runs entire session)
│
├── api-overseer          Manages 6-phase pipeline for api-repo
│   ├── api-planner                                  ← Opus
│   ├── api-researcher-codebase    ╮                 ← Opus, parallel
│   ├── api-researcher-technical   ╯
│   ├── api-implementer-1         ╮                  ← Sonnet, parallel when safe
│   ├── api-implementer-2         ╯
│   ├── api-index-updater                            ← Sonnet
│   ├── api-reviewer-a            ╮                  ← Sonnet, independent
│   └── api-reviewer-b            ╯
│
├── web-overseer          Same structure, hermetically isolated
│   └── ...
│
├── ceo-assistant-api     Cross-repo impact scout (on demand, Opus)
├── ceo-assistant-web     Cross-repo impact scout (on demand, Opus)
│
└── cross-reviewer        Verifies contracts across related repos (at finalization)
```

**Flat hierarchy, single authority.** The CEO spawns every agent. Overseers manage their pipelines but request all spawns and shutdowns through the CEO. No agent-spawning-agent chains. No authority ambiguity.

**Isolation is real.** Isolated repos receive zero information about other repos. Their Overseers don't know other repos exist. They operate as if they're the only repo in the session.

**Cross-repo communication is deliberate.** Related repos flag changes to the CEO. Non-breaking changes (Tier 1) are relayed directly. Breaking changes (Tier 2) trigger a CEO-Assistant impact assessment before anyone acts. Nothing leaks. Nothing is assumed.

---

## The Pipeline

Each repo runs a structured 6-phase pipeline (plus Phase 0 assessment):

| Phase | What Happens |
|:-----:|-------------|
| **0** | **Assessment** — Overseer evaluates the task. Non-code tasks resolved here. Pipeline only activates for real implementation work. |
| **1** | **Planning** — Architect loads index context, creates the plan, writes shared context for researchers. |
| **2** | **Research & Revision** — Codebase researcher and technical researcher investigate in parallel. Architect revises. Loop iterates until both report zero issues. On exit, generates the implementation manifest. |
| **3** | **Implementation** — Implementers execute batched tasks. Parallel when no file conflicts; sequential when files overlap. |
| **4** | **Index Update** — Updates all affected indexes AND enriches neighboring unindexed areas. Every run leaves the index more complete. |
| **5** | **Review** — Two independent reviewers verify implementation AND Index Updater completeness. Incomplete index = FAIL. |
| **6** | **Finalize** — Evaluate verdicts, route failures by severity, commit on success. |

The research loop has no iteration cap — quality is the only exit condition. If iteration count exceeds 3, you're consulted. The loop doesn't silently give up.

---

## Cross-Repo Communication

When repos share APIs, schemas, or configuration:

```
Overseer A detects a shared surface was modified
        │
        ▼
   CEO receives the flag with tier classification
        │
        ├── Tier 1 (non-breaking, additive)
        │   └── Relay directly to affected Overseer — no assessment needed
        │
        └── Tier 2 (breaking or uncertain)
            └── Spawn CEO-Assistant to assess actual impact
                    │
                    ├── No impact → false alarm, no action
                    └── Impact confirmed → route specifics to affected Overseer
```

**Dependency pauses are automatic.** If Repo B is building a client against Repo A's API, and Repo B gets ahead before Repo A has finalized the contract — the CEO pauses Repo B. Running work finishes, but no new phases start. When Repo A catches up, the CEO resumes Repo B. You don't manage this. The CEO does.

**Cross-Repo Reviewer** runs after all repos in a related group complete. It verifies that API contracts, shared schemas, and configuration assumptions actually align — with specific file paths and literal values from each repo. Produces ALIGNED / MISMATCH / UNTESTED verdicts.

---

## The Codebase-Index

The secret weapon. Hand-curated `INDEX.md` files that live alongside your code — describing structure, patterns, dependencies, and relationships. Not generated docs. Maintained knowledge.

```
Codebase-Index/
├── MASTER-INDEX.md          ← Architectural overview, routes to components
├── api/
│   └── INDEX.md             ← API endpoints, middleware, auth patterns
├── core/
│   └── INDEX.md             ← Business logic, data models, services
└── infrastructure/
    └── INDEX.md             ← Deployment, config, monitoring
```

Agents query it through `codebase-index-tools`:

| Command | What It Does |
|---------|-------------|
| `search --query "auth"` | Find which indexes cover authentication |
| `inject --task "fix login bug"` | Load all relevant context for a task |
| `check --all` | Audit for stale or missing indexes |
| `scaffold --source src/new-module` | Generate stub INDEX.md for unmapped code |

No embeddings. No vector database. No external services. Just a local CLI (Python 3.8+ or Node 18+) reading structured markdown. Deterministic, inspectable, human-readable.

**Progressive enrichment** means the index grows automatically. The Index Updater doesn't just fix what changed — it scans neighboring unindexed code and scaffolds new indexes. Every pipeline run leaves the codebase better mapped than before.

---

## Quick Start

```bash
# Multi-repo orchestration — the full CEO experience
/goat-ceo

# Single-repo pipeline — plan, research, implement, review
/goat-team:goat Fix the authentication bug in the login flow

# Plan only — get a researched plan, decide later
/goat-team:goat-plan Design the new caching layer

# Review only — audit existing work with dual reviewers
/goat-team:goat-review

# Index maintenance — audit and update without running a pipeline
/goat-team:index-check
```

> [!NOTE]
> GOAT-CEO requires Claude Code with agent teams support (`TeamCreate`, `Agent`, `SendMessage`, `TaskCreate`). This is an experimental feature — check your Claude Code environment for availability.

---

## Session Audit Trail

Every session is fully logged by a dedicated Scribe agent (Haiku — lightweight, runs the entire session):

| Log | What It Captures |
|-----|-----------------|
| `timeline.log` | Phase progression, agent spawns/shutdowns, key events |
| `decisions.log` | CEO decisions with rationale — why pipeline was skipped, why a pause was issued |
| `cross-repo.log` | Every cross-repo communication, impact assessment, and routing decision |

The CEO doesn't waste turns on log formatting. It sends brief event messages to the Scribe; the Scribe handles the rest. Critical events are logged immediately. Routine events are batched to reduce overhead.

---

<details>
<summary><strong>Repo Structure</strong></summary>

```
GOAT-CEO/
├── CLAUDE.md                          ← Repo instructions + agent tooling reference
├── GOAT-CEO-DESIGN.md                 ← Full design document (function tree, 16 decisions)
├── repo-registry.json                 ← Persists repos, capabilities, groups across sessions
├── .claude/
│   ├── agents/                        ← 8 custom agent type definitions
│   └── commands/
│       ├── goat-ceo.md                ← CEO orchestration entry point
│       ├── goat-ceo/
│       │   ├── protocols.md           ← Communication flows, error recovery, dashboard
│       │   └── templates.md           ← 11 agent spawn prompt templates
│       └── goat-team/
│           ├── goat.md                ← Full pipeline orchestrator
│           ├── planner.md             ← Planner role script
│           ├── codebase-researcher.md ← Codebase researcher role
│           ├── technical-researcher.md← Technical researcher role
│           ├── implementer.md         ← Implementer role script
│           ├── index-updater.md       ← Index updater role
│           ├── reviewer.md            ← Reviewer role script
│           └── ...                    ← Plan-only, review-only, index-check variants
├── specs/                             ← Self-contained bootstrapping specs
│   ├── indexing-system.md             ← Codebase-Index system spec
│   ├── tooling-system.md              ← codebase-index-tools CLI spec
│   └── goat-system.md                 ← GOAT pipeline + agents spec
└── logs/                              ← Per-session audit trail (gitignored)
    └── [repo-prefix]/
        ├── timeline.log
        ├── decisions.log
        └── cross-repo.log
```

</details>

---

## Inspiration

GOAT-CEO was directly inspired by [**GSD — Get Shit Done**](https://github.com/gsd-build/get-shit-done), the framework that proved structured, phase-based agent pipelines produce substantially better outcomes than ad-hoc prompting. GSD pioneered the discipline. GOAT-CEO extends it across repository boundaries.

Where GSD coordinates a single repo with precision, GOAT-CEO runs parallel GOAT pipelines across independent repositories — with a single session acting as the informed executive across all of them.

---

## Status

GOAT-CEO is **experimental**. It is built specifically for Claude Code's agent teams feature and assumes that capability is available in your environment.

The specs in `specs/` are designed to be self-contained bootstrapping instructions. Point GOAT-CEO at a repo missing the indexing or tooling systems, and it will set them up — either automatically or through the Overseer-driven pipeline.

---

<div align="center">

**Your repos have a CEO now.**

Built on the shoulders of [GSD](https://github.com/gsd-build/get-shit-done).

</div>
