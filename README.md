# GOAT-CEO

A meta-orchestration system that coordinates AI agent teams across multiple repositories simultaneously using Claude Code.

---

## The Problem

Working across multiple repositories with AI agents is harder than it looks. Each Claude Code session has its own context boundary — it cannot natively see what another session is doing, coordinate shared contracts, or synchronize dependent work across repos. Naive approaches either collapse everything into one giant context (brittle, expensive) or run sessions in complete isolation (fine for unrelated work, but breaks down the moment repos share an API, schema, or configuration surface).

GOAT-CEO solves this by treating multi-repo coordination as an explicit orchestration problem: one session acts as executive, spawning isolated per-repo pipelines and routing cross-repo information deliberately, without contaminating unrelated work.

---

## Inspiration and Origins

GOAT-CEO was directly inspired by [GSD — Get Shit Done](https://github.com/gsd-build/get-shit-done), a framework that brought real structure and discipline to AI agent workflows. GSD demonstrated that structured, phase-based agent pipelines produce substantially better outcomes than ad-hoc prompting — a lesson that shaped every design decision in GOAT-CEO.

GOAT-CEO takes a different path: rather than coordinating a single repo, it leverages Claude Code's experimental agent teams system to run parallel GOAT pipelines across independent repositories, with a single session acting as the informed executive across all of them. The credit for pioneering structured agent workflows belongs to the GSD creator. GOAT-CEO stands on that foundation.

---

## How It Works

Your Claude Code session becomes the CEO — the sole orchestration authority for the session. The CEO spawns one Overseer per repository, and each Overseer independently manages a full 6-phase GOAT pipeline for its repo. The CEO routes cross-repo information where needed, pauses dependent work when one repo is ahead of another, and spawns CEO-Assistants on demand for context scouting. A dedicated Scribe agent handles all session logging, keeping the CEO's output clean.

```
Your Claude Code session (CEO)
│
├── Spawns: ceo-scribe (session logger, runs for entire session)
│
├── Spawns: api-overseer  →  manages 6-phase GOAT pipeline for api-repo
│   ├── api-planner
│   ├── api-researcher-codebase, api-researcher-technical  (parallel)
│   ├── api-implementer-1, api-implementer-2              (parallel when safe)
│   ├── api-index-updater
│   └── api-reviewer-a, api-reviewer-b                    (independent)
│
├── Spawns: web-overseer  →  manages 6-phase GOAT pipeline for web-repo
│   └── (same structure, isolated team)
│
├── Spawns: ceo-assistant-api  →  context scout (on demand, per event)
├── Spawns: ceo-assistant-web  →  context scout (on demand, per event)
│
└── Spawns: cross-reviewer    →  verifies contracts across related repos (at finalization)
```

Cross-repo communication flows only through the CEO. Overseers flag changes that may affect related repos; the CEO dispatches a CEO-Assistant to assess actual impact before routing anything. Unrelated repos see none of this — they run as if they are the only repo in the session.

---

## The Codebase-Index System

The GOAT pipeline depends on a companion system: **Codebase-Index** with **codebase-index-tools**. This is what makes the pipeline practical at scale.

### What Codebase-Index Is

`Codebase-Index/` is a directory of hand-curated `INDEX.md` files that live alongside your code. Each file describes a component or area of the codebase: its directory structure, key files, patterns, dependencies, known gotchas, and relationships to other areas. These are not generated docs — they represent deliberate, maintained knowledge about how the codebase is organized and why.

The index is layered: a `MASTER-INDEX.md` provides the architectural overview and routes agents to the right component indexes. Section indexes go deeper. The result is a semantic map that any agent can navigate in seconds, without reading hundreds of source files.

### What codebase-index-tools Does

`codebase-index-tools` is a local CLI that agents use to interact with the index programmatically:

| Command | Purpose |
|---------|---------|
| `search` | Find which indexes are relevant to a keyword or task |
| `inject` | Load relevant index content into agent context for a task |
| `check` | Detect index files that are stale relative to recent code changes |
| `scaffold` | Generate stub INDEX.md files for unmapped directories |

All commands support `--format json` for agent consumption. The CLI is stdlib-only (Python 3.8+ or Node 18+) with no external service dependencies.

### Why It Matters

Without the index system, agents waste significant context on raw file exploration — reading directory trees, tracing imports, mapping dependencies — before any actual work begins. With it, an agent loads the relevant index context in a single command and starts with full situational awareness.

More importantly, the GOAT pipeline treats index accuracy as a first-class concern. A dedicated Index Updater phase runs after every implementation batch, and both reviewers verify index coverage before the pipeline closes. An outdated index is treated as an unresolved issue, not a cosmetic problem.

---

## The GOAT Pipeline

Each Overseer runs a 6-phase pipeline for its assigned repository:

| Phase | Name | Description |
|-------|------|-------------|
| 0 | Assessment | Overseer reads the task, orients independently, and determines whether code changes are actually required. Non-implementation tasks (investigation, verification, diagnosis) are resolved here directly — the pipeline does not activate. |
| 1 | Planning | Architect agent loads index context, analyzes the task, creates `PLAN.md` and writes shared `index-context.md`. |
| 2 | Research & Revision Loop | Codebase and technical researchers investigate in parallel, architect revises the plan, loop iterates until clean pass. On exit, architect generates `IMPLEMENTATION-MANIFEST.md` inline. |
| 3 | Implementation | Implementers execute batches (parallel when no file conflicts exist). |
| 4 | Index Update | Dedicated agent ensures all affected `INDEX.md` files reflect the new code, plus progressive enrichment of neighboring unindexed areas. |
| 5 | Review | Two independent reviewers verify implementation correctness and Index Updater completeness. |
| 6 | Finalize | Overseer evaluates reviewer verdicts, handles failures, and summarizes the work. |

Pipeline artifacts (`PLAN.md`, `RESEARCH-LOG.md`, `IMPLEMENTATION-MANIFEST.md`, `REVIEW-LOG.md`) are written to `agent-workspace/` in each repo and serve as checkpoints for Overseer recovery if a long-running session is interrupted.

---

## Repo Structure

```
GOAT-CEO/
├── CLAUDE.md                          ← Repo instructions (read by all agents)
├── GOAT-CEO-DESIGN.md                 ← Full design document with function tree
├── .claude/
│   ├── agents/                        ← Custom agent type definitions
│   │   ├── team-architect.md          ← Planner/architect (Opus)
│   │   ├── team-ceo-assistant.md      ← Cross-repo impact assessment (Opus)
│   │   ├── team-ceo-scribe.md         ← Session logger (Haiku)
│   │   ├── team-cross-reviewer.md     ← Cross-repo contract verifier (Sonnet)
│   │   ├── team-implementer.md        ← Implementers (Sonnet)
│   │   ├── team-overseer.md           ← Repo pipeline manager (Opus)
│   │   ├── team-researcher.md         ← Researchers (Opus)
│   │   └── team-verifier.md           ← Reviewers (Sonnet)
│   └── commands/
│       ├── goat-ceo.md                ← CEO orchestration entry point
│       ├── goat-ceo/                  ← CEO supporting files
│       │   ├── protocols.md           ← Communication flows and error recovery
│       │   └── templates.md           ← Agent spawn prompt templates
│       └── goat-team/                 ← GOAT pipeline skill files
│           ├── goat.md                ← Full pipeline orchestrator
│           ├── goat-plan.md           ← Plan-only variant
│           ├── goat-review.md         ← Review-only variant
│           ├── planner.md             ← Planner role script
│           ├── codebase-researcher.md ← Codebase researcher role
│           ├── technical-researcher.md← Technical researcher role
│           ├── implementer.md         ← Implementer role script
│           ├── index-updater.md       ← Index updater role
│           ├── reviewer.md            ← Reviewer role script
│           ├── index-check.md         ← Standalone index audit
│           ├── set-models.md          ← Model assignment configuration
│           └── README.md              ← Pipeline documentation
├── specs/                             ← Reference specs for bootstrapping repos
│   ├── indexing-system.md             ← Codebase-Index system spec
│   ├── tooling-system.md              ← codebase-index-tools CLI spec
│   └── goat-system.md                 ← GOAT pipeline + agents spec
└── logs/                              ← Created per session (gitignored)
    └── [repo-prefix]/
        ├── decisions.log
        ├── cross-repo.log
        └── timeline.log
```

---

## Quick Start

Multi-repo orchestration session (CEO mode):
```
/goat-ceo
```

Full single-repo pipeline (plan through review):
```
/goat-team:goat <task description>
```

Plan only (stops before implementation):
```
/goat-team:goat-plan <task description>
```

Review only (assumes implementation is done):
```
/goat-team:goat-review
```

---

## Key Concepts

| Term | Definition |
|------|-----------|
| **Overseer** | Long-running agent that manages the full GOAT pipeline for one repository. Coordinates team members, filters messages, and requests agent spawns from the CEO. |
| **CEO-Assistant** | On-demand context scout. Spawned by the CEO to query a specific repo's index and code — used for dependency detection and cross-repo impact assessment. |
| **Scribe** | Lightweight persistent agent (Haiku) that handles all session logging. The CEO sends brief event messages; the Scribe writes formatted entries to `logs/`. |
| **Assessment-First Protocol** | Before activating the full GOAT pipeline, the Overseer independently reads and evaluates the task. If no code changes are needed (investigation, verification, diagnosis), the Overseer resolves the task directly. The pipeline only activates when implementation is required. |
| **Phase 0** | The assessment phase. Distinct from Phase 1 (Planning) — it determines whether the pipeline should run at all. |
| **Related Groups** | Repos that share APIs, schemas, or configuration surfaces. Their Overseers can flag changes to the CEO, who routes cross-repo information and manages dependency pauses. |
| **Isolated Repos** | Repos with no cross-repo dependencies in the session. They receive no information about other repos' tasks and run as if they are the only repo. |
| **Codebase-Index** | A directory of hand-curated `INDEX.md` files that map a codebase's structure, patterns, and relationships. The semantic knowledge layer that agents load before working. |
| **codebase-index-tools** | Local CLI for querying and maintaining the Codebase-Index. Provides `search`, `inject`, `check`, and `scaffold` commands. Agent-first design with `--format json` on all commands. |

---

## Status

GOAT-CEO is experimental. It is designed specifically for Claude Code's agent teams feature (`TeamCreate`, `Agent`, `SendMessage`, `TaskCreate`) and assumes that capability is available in your Claude Code environment. The system has not been tested against other agent frameworks or orchestration tools.

The specs in `specs/` are designed to be passed directly to a GOAT team as bootstrapping instructions — if a target repo is missing the indexing or tooling systems, the CEO can copy those spec files into the repo and the GOAT team will set up the systems as its first task.
