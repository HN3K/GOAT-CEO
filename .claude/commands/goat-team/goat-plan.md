# Agent Team — Plan Only (Stops Before Implementation)

You are the orchestrator for a structured agent team planning system. Execute Phases 1–2 fully, then output the finalized PLAN.md and STOP. Do not proceed to implementation.

**Task:** $ARGUMENTS

> **After this command completes**, review the plan in `agent-workspace/PLAN.md`. When ready to implement, run `/goat-implement` to continue with Phases 3–6.

---

## Tooling Reference

# Tooling command varies by repo — check CLAUDE.md for the correct invocation
# Python repos: python -m codebase_index_tools <command> --format json
# Node repos: node codebase-index-tools/cli.js <command> --format json

All agents use the `codebase-index-tools` CLI from the repo root:
```bash
python -m codebase_index_tools <command> [options]
```

**Always use `--format json`** when output will be parsed programmatically.

### Commands

- **`search --list`** — List all known mappings.
- **`search --query "..." [--in-content]`** — Find relevant indexes by keyword.
- **`inject --task "..." [--include-master] [--file ...] [--ids ...]`** — Load index content.
- **`check [--all]`** — Detect stale/missing indexes.
- **`scaffold --source <dir> [--dry-run]`** — Generate INDEX.md stubs.

---

## Shared Artifacts

Create `agent-workspace/` at the repo root with these files:

| File | Owner | Purpose |
|------|-------|---------|
| `agent-workspace/PLAN.md` | Planner | Primary planning document |
| `agent-workspace/RESEARCH-LOG.md` | Researchers | Running log of findings |
| `agent-workspace/ISSUE-TRACKER.md` | All agents | Issues with severity |

---

## Phase 1 — Planning

**Agent:** Planner

1. Run `search --list --format json` to get all available mappings.
2. Run `inject --task "$ARGUMENTS" --include-master --format json` to load task-relevant context. Read all `data.indexes[].content`.
3. If the task touches a specific known file, also run `inject --file [path] --format json`.
4. Create `agent-workspace/` directory and initialize:
   - `PLAN.md` (using template below)
   - `ISSUE-TRACKER.md` (empty issues list)
   - `RESEARCH-LOG.md` (iteration counter = 1, no entries yet)
5. Activate Codebase Researcher and Technical Researcher simultaneously.

**PLAN.md Template:**
```markdown
# Implementation Plan — [Task Name]
> Created: [DATE] | Status: DRAFT | Iteration: 1

## Task Summary
[What needs to be done, 2–3 sentences.]

## Goals
- [Explicit, measurable goal]

## Out of Scope
- [What this task explicitly does NOT do]

## Affected Areas
> Source: inject --include-master output.

## Implementation Approach
[Narrative. Specific enough that an implementer can work from it without asking questions.]

## Implementation Steps
> These become batches in IMPLEMENTATION-MANIFEST.md.
1. [Step]
2. [Step]

## Dependencies Between Steps
[Which steps must complete before others.]

## Risks & Open Questions

## Researcher Annotations
> Format: `[CODEBASE|TECHNICAL] [ISSUE|INFO|SUGGESTION] [SEVERITY: critical|major|minor|info] — [Finding]`

## Decisions Log
> Planner records all decisions and dismissals with reasoning.
```

---

## Phase 2 — Research Loop

**Agents:** Codebase Researcher + Technical Researcher (parallel)
**Then:** Planner reviews, revises, evaluates exit criteria
**Repeats** until all exit criteria are met

### Codebase Researcher — Per Iteration

Spawn a `general-purpose` agent:
> Read `.claude/commands/codebase-researcher.md` in full, then execute your iteration steps. Task: "$ARGUMENTS". This is iteration [N]. Read agent-workspace/PLAN.md and agent-workspace/RESEARCH-LOG.md first.

### Technical Researcher — Per Iteration

Spawn a `general-purpose` agent:
> Read `.claude/commands/technical-researcher.md` in full, then execute your iteration steps. Task: "$ARGUMENTS". This is iteration [N]. Read agent-workspace/PLAN.md and agent-workspace/RESEARCH-LOG.md first.

### Planner — Post-Research Review (Per Iteration)

1. Read all new annotations in PLAN.md and open items in ISSUE-TRACKER.md.
2. For each annotation: critical/major → must resolve; minor → use judgment; info → incorporate or dismiss with reasoning. Record in Decisions Log.
3. Increment iteration counter. Update Status field.
4. Evaluate loop exit criteria — **all must be true:**
   - Codebase Researcher log for this iteration: `Issues found: 0`
   - Technical Researcher log for this iteration: `Issues found: 0`
   - All ISSUE-TRACKER.md items: `RESOLVED` or `DISMISSED`
   - Planner review finds no gaps, ambiguities, or unresolved risks
   - Every step in Implementation Steps is specific enough to execute without clarification
5. If criteria not met: re-activate both researchers.
6. If criteria met: **STOP HERE.**

There is no iteration cap. Quality is the only exit condition.

---

## On Completion

When the research loop exits cleanly:

1. Set PLAN.md status to `APPROVED — AWAITING IMPLEMENTATION`.
2. Output the full contents of `agent-workspace/PLAN.md` for human review.
3. Output this message:

```
PLAN COMPLETE — AWAITING APPROVAL
─────────────────────────────────────────────────
Task:                $ARGUMENTS
Plan iterations:     [N]
Research loops:      [N]
Open issues:         0 (all resolved or dismissed)
Workspace:           agent-workspace/
─────────────────────────────────────────────────

Review the plan in agent-workspace/PLAN.md.
When ready to proceed, run: /goat-implement
```

**Do NOT proceed to implementation. Do NOT create IMPLEMENTATION-MANIFEST.md. Stop here and wait for human approval.**
