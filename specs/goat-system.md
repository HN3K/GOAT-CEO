# GOAT Agent Team Pipeline — Reference Specification

> **Purpose**: Complete specification for setting up the GOAT (agent team pipeline) system in any repository. This document is passed to repos that need bootstrapping — the GOAT team reads this spec and implements the system, adapting to the target repo's conventions.

---

## What This Is

GOAT is a structured multi-agent implementation pipeline for Claude Code. It spawns specialized agents (planner, researchers, implementers, reviewers) through a 7-phase workflow with built-in quality gates and codebase index integration.

---

## Prerequisites

- **Claude Code** CLI with agent team support (`TeamCreate`, `Agent`, `SendMessage`, `TaskCreate`)
- **codebase-index-tools** CLI installed (see `tooling-system.md` spec)
- **Codebase-Index/** directory with index mappings (see `indexing-system.md` spec)

---

## File Structure

The GOAT system requires two sets of files:

### 1. Command Files (`.claude/commands/goat-team/`)

These define the pipeline workflow and agent role scripts:

| File | Purpose |
|------|---------|
| `goat.md` | Main entry point — overseer orchestrates all 7 phases |
| `goat-plan.md` | Plan-only variant (Phases 1-2, stops before implementation) |
| `goat-review.md` | Review-only variant (assumes implementation complete) |
| `planner.md` | Planner role — creates/revises plans and manifests |
| `codebase-researcher.md` | Codebase researcher — finds risks in actual code |
| `technical-researcher.md` | Technical researcher — assesses approach quality |
| `implementer.md` | Implementer — executes one manifest batch |
| `index-updater.md` | Index updater — content-aware index accuracy layer |
| `reviewer.md` | Reviewer — independent verification + index update |
| `index-check.md` | Standalone index audit utility |
| `README.md` | Pipeline documentation |

### 2. Agent Definitions (`.claude/agents/`)

These define custom agent types with tool restrictions and model assignments:

| File | Model | Tools | Used By |
|------|-------|-------|---------|
| `team-architect.md` | opus | Read, Glob, Grep, Bash, Write | planner, planner-review, planner-manifest |
| `team-researcher.md` | opus | Read, Glob, Grep, Bash, WebSearch, WebFetch | codebase-researcher, tech-researcher |
| `team-implementer.md` | sonnet | Read, Write, Edit, Bash, Glob, Grep | implementer-{N}, index-updater |
| `team-verifier.md` | sonnet | Read, Write, Edit, Glob, Grep, Bash | reviewer-a, reviewer-b |

---

## Pipeline Phases

### Phase 1: Planning
- Planner loads index context via codebase-index-tools
- Creates `agent-workspace/PLAN.md`, `ISSUE-TRACKER.md`, `RESEARCH-LOG.md`
- Signals `PLANNER_SIGNAL: RESEARCH_START`

### Phase 2: Research Loop
- Two researchers spawned simultaneously:
  - **Codebase researcher**: validates plan against actual code, finds upstream/downstream risks
  - **Technical researcher**: assesses approach quality, checks best practices, uses web search
- Both write findings to `RESEARCH-LOG.md`

### Phase 3: Plan Revision
- Planner reviews all researcher findings
- Revises plan as needed
- Evaluates exit criteria: `LOOP_CONTINUE` or `LOOP_EXIT`
- If `LOOP_CONTINUE`: back to Phase 2 with incremented iteration
- If iteration count > 3: ask user whether to continue, adjust scope, or proceed

### Phase 4: Implementation Manifest
- Planner creates `agent-workspace/IMPLEMENTATION-MANIFEST.md`
- Contains batched implementation tasks with parallelism rules
- Signals `PLANNER_SIGNAL: MANIFEST_READY`

### Phase 5: Implementation
- Implementers execute manifest batches
- Batches with no shared files run in parallel; shared files run sequentially
- Each implementer runs a post-implementation index check

### Phase 5.5: Index Update
- Dedicated index updater reads manifest to identify modified files
- For each modified file, finds its covering INDEX.md
- Compares index content against actual code
- Updates inaccuracies
- Writes update log to `REVIEW-LOG.md`

### Phase 6: Review
- Two independent reviewers spawned simultaneously
- Each reviewer:
  1. Reads plan and manifest
  2. Verifies implementation against acceptance criteria
  3. Checks for bugs, security issues, pattern violations
  4. Performs mandatory index update check
  5. Issues verdict: PASS or FAIL (with severity: Critical/Major/Minor)

### Phase 7: Finalize
- Overseer evaluates both review verdicts
- Hard gates: Index updates must be present, no stale/missing indexes
- Both PASS: summarize and clean up
- FAIL (Major only): spawn targeted fix, re-run Phase 6 (max 2 cycles)
- FAIL (Critical): ask user for guidance

---

## Pipeline Artifacts

All written to `agent-workspace/` at the repo root:

| File | Owner | Purpose |
|------|-------|---------|
| `PLAN.md` | Planner | Implementation plan with steps, risks, acceptance criteria |
| `RESEARCH-LOG.md` | Researchers, Planner | Running log of findings, signals, and iteration markers |
| `ISSUE-TRACKER.md` | All agents | Issues with severity tracking |
| `IMPLEMENTATION-MANIFEST.md` | Planner | Batched tasks with file assignments and parallelism rules |
| `REVIEW-LOG.md` | Index Updater, Reviewers | Index checks, content updates, review verdicts |

---

## Agent Role Summaries

### Planner (team-architect)
- Loads codebase index context before planning
- Creates structured plan with numbered steps, file targets, acceptance criteria
- Manages the research loop (evaluate findings, decide continue/exit)
- Creates the implementation manifest with batching strategy

### Codebase Researcher (team-researcher)
- Reads the plan and actually examines the codebase
- Identifies: files that will be affected but aren't in the plan, upstream/downstream risks, existing patterns that should be followed
- Writes findings to RESEARCH-LOG.md with issue severity ratings

### Technical Researcher (team-researcher)
- Assesses the plan's technical approach quality
- Checks for: known pitfalls, better alternatives, security concerns, performance implications
- Can use web search for current best practices
- Writes findings to RESEARCH-LOG.md with issue severity ratings

### Implementer (team-implementer)
- Executes exactly one batch from the manifest
- Does not touch files outside assigned scope
- Runs post-implementation index check
- Reports completion with file change summary

### Index Updater (team-implementer)
- Content-aware index accuracy layer (not just staleness)
- Reads each modified file's covering INDEX.md
- Compares descriptions against actual code behavior
- Updates inaccurate descriptions, not just dates

### Reviewer (team-verifier)
- Independent verification of implementation against plan
- Checks: correctness, completeness, patterns, security, test coverage
- Performs mandatory index update check before issuing verdict
- Can update INDEX.md files during review

---

## Customization for Target Repo

When setting up GOAT in a new repo, the only file that requires repo-specific customization is `goat.md`. Update the **Project-Specific Rules** section:

```markdown
## Project-Specific Rules (include in agent prompts when relevant)

- Your build system and test commands
- Code patterns and conventions (e.g., static JsonSerializerOptions, [GeneratedRegex])
- Architecture boundaries
- Tooling invocation (e.g., `python -m codebase_index_tools` or `node codebase-index-tools/cli.js`)
- Any repo-specific constraints
```

All other files are generic and work with any repo that has the codebase-index system set up.

---

## Usage

```bash
# Full pipeline
/goat-team:goat <task description>

# Plan only (stops before implementation)
/goat-team:goat-plan <task description>

# Review only (assumes implementation complete)
/goat-team:goat-review

# Standalone index audit
/goat-team:index-check
```
