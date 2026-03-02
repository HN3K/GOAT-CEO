# GOAT — Agent Team Pipeline

A structured multi-agent implementation pipeline for Claude Code. Spawns specialized agents (planner, researchers, implementers, reviewers) through a 6-phase workflow with built-in quality gates.

## Prerequisites

- **Claude Code** CLI with agent team support (`TeamCreate`, `Agent`, `SendMessage`, `TaskCreate`)
- **codebase-index-tools** CLI installed at repo root (Python: `python -m codebase_index_tools`, Node: `node codebase-index-tools/cli.js`)
- **Codebase-Index/** (or equivalent) directory with index mappings for your project

## Setup (GOAT-CEO context)

This repo (`GOAT-CEO`) is the meta-orchestration repo — it contains skill definitions, specs, and pipeline logs. It does not contain runtime application code. The GOAT pipeline is already configured and ready to use.

1. The `.claude/commands/goat-team/` directory is already set up in this repo — no copying needed.

2. Custom agent definitions live in `.claude/agents/`:
   - `team-architect.md` — Planner/architect roles (Phases 1, 2)
   - `team-researcher.md` — Codebase and technical researchers (Phase 2)
   - `team-implementer.md` — Implementers and index updater (Phases 3, 4)
   - `team-verifier.md` — Reviewers (Phase 5)

3. The `goat.md` command is already configured with GOAT-CEO project-specific rules. If you use this pipeline in another repo, copy the `.md` files and update the **Project-Specific Rules** section in `goat.md`:

   ```markdown
   ## Project-Specific Rules (include in agent prompts when relevant)

   - Your build system and test commands
   - Code patterns and conventions
   - Architecture boundaries
   - Any repo-specific constraints
   ```

4. Check `CLAUDE.md` in the target repo for the correct tooling invocation before running agents that use `codebase-index-tools`.

## Usage

### Full pipeline (plan → research → implement → review):
```
/goat Fix the authentication bug in the login flow
```

### Plan only (stops before implementation):
```
/goat-plan Design the new caching layer
```

### Review only (assumes implementation is already done):
```
/goat-review Review the changes in agent-workspace/
```

### Index maintenance:
```
/index-check
```

## Files

| File | Purpose |
|------|---------|
| `goat.md` | Main entry point — overseer orchestrates all phases |
| `goat-plan.md` | Plan-only variant (Phases 1-2, stops before implementation) |
| `goat-review.md` | Review-only variant (assumes implementation complete) |
| `planner.md` | Planner agent role — creates/revises plans and manifests |
| `codebase-researcher.md` | Codebase researcher — finds upstream/downstream risks |
| `technical-researcher.md` | Technical researcher — assesses approach quality |
| `implementer.md` | Implementer agent — executes one manifest batch |
| `index-updater.md` | Index updater — content-aware index accuracy layer |
| `reviewer.md` | Reviewer agent — independent verification |
| `index-check.md` | Standalone index audit and update utility |

## Agent Types

The pipeline uses custom agent definitions from `.claude/agents/`:

| Agent type | Used by roles |
|------------|--------------|
| `team-architect` | planner, planner-review, planner-manifest |
| `team-researcher` | codebase-researcher, tech-researcher |
| `team-implementer` | implementer-{N}, index-updater |
| `team-verifier` | reviewer-a, reviewer-b |

## Pipeline Phases

1. **Planning** — Planner loads index context, creates PLAN.md and shared index-context.md
2. **Research & Revision Loop** — Two researchers investigate in parallel, planner revises, loop until clean. On exit, planner generates IMPLEMENTATION-MANIFEST.md inline
3. **Implementation** — Implementers execute batches (parallel when no file conflicts)
4. **Index Update** — Index updater ensures indexes match code changes + progressive enrichment
5. **Review** — Two independent reviewers verify implementation and Index Updater completeness
6. **Finalize** — Overseer evaluates verdicts, handles failures, summarizes

## Artifacts

All pipeline artifacts are written to `agent-workspace/` at the repo root:

| File | Owner | Purpose |
|------|-------|---------|
| `PLAN.md` | Planner | Implementation plan |
| `RESEARCH-LOG.md` | Researchers | Running log of findings and signals |
| `ISSUE-TRACKER.md` | All agents | Issues with severity tracking |
| `IMPLEMENTATION-MANIFEST.md` | Planner | Batched implementation tasks |
| `REVIEW-LOG.md` | Implementers, Index Updater, Reviewers | Index checks and review verdicts |

## Customization

The only file that needs per-repo customization is `goat.md`. Everything else is generic and works with any repo that has `codebase-index-tools` and a `Codebase-Index/` (or equivalent) directory set up.
