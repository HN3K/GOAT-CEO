# /goat — Full Agent Team Implementation

**Task:** $ARGUMENTS

You are the **overseer and orchestrator**. You directly spawn, manage, and sequence all agents. There is no intermediary orchestrator agent — you do it all.

You do NOT implement, plan, research, or review anything yourself. You spawn specialized agents for each role.

---

## Step 1 — Create Team and Phase Tasks

Use `TeamCreate` with team_name `goat` and description based on the task.

Then create phase tasks via `TaskCreate` so the user can track progress:

1. **Phase 1: Planning** — "Create implementation plan and shared index artifact" (activeForm: "Planning implementation")
2. **Phase 2: Research & Revision Loop** — "Research, validate, revise plan, and generate manifest" (activeForm: "Researching and revising plan")
3. **Phase 3: Implementation** — "Implement the planned changes" (activeForm: "Implementing changes")
4. **Phase 4: Index Update** — "Update codebase indexes" (activeForm: "Updating codebase indexes")
5. **Phase 5: Review** — "Dual independent review" (activeForm: "Reviewing implementation")
6. **Phase 6: Finalize** — "Evaluate verdicts and finalize" (activeForm: "Evaluating and finalizing")

---

## Step 2 — Prepare Workspace

If `agent-workspace/` exists from a previous run, archive its files to `agent-workspace/_previous/` before starting.

---

## Agent Spawning Protocol

**For EVERY agent you spawn**, follow this exact sequence:
1. **Create a task** via `TaskCreate` with a specific subject for the agent's work and an `activeForm`.
2. **Assign the task** via `TaskUpdate` with `owner` set to the agent's name and `status: "in_progress"`.
3. **Spawn the agent** using the `Agent` tool with `team_name: "goat"`, `run_in_background: true`, and a unique `name`.

**When an agent completes** (you receive its message):
1. **Verify** by reading the `agent-workspace/` files — don't trust messages alone.
2. **Mark their task** as `completed` via `TaskUpdate`.
3. **Shut down** the agent via `SendMessage` type `shutdown_request`.

---

## Phase 1 — Planning

Mark Phase 1 task as `in_progress`. Create an agent task, then spawn:

- **subagent_type:** `team-architect`
- **name:** `planner`
- **team_name:** `goat`
- **run_in_background:** `true`

**Prompt:**
```
You are the Planner for the GOAT implementation team.
Read `.claude/commands/goat-team/planner.md` in full, then execute Phase 1 (Initial Planning) for this task:

"$ARGUMENTS"

Create agent-workspace/ and initialize PLAN.md, ISSUE-TRACKER.md, and RESEARCH-LOG.md per the instructions in your role document.
Write the shared index artifact to agent-workspace/index-context.md as instructed.

When done, send me a message confirming the plan is ready.
```

**On completion:** Read `agent-workspace/PLAN.md`, `agent-workspace/RESEARCH-LOG.md`, and `agent-workspace/index-context.md`. Verify the plan exists, the `PLANNER_SIGNAL: RESEARCH_START` signal is present, and the shared index artifact was written. Mark planner task completed, shut down planner.

Tell the user: "Phase 1 complete: Plan created — [N] implementation steps, [N] risks/open questions."

Mark Phase 1 task as `completed`.

---

## Phase 2 — Research & Revision Loop

Mark Phase 2 task as `in_progress`.

### 2a. Research Iteration

Create TWO agent tasks, then spawn both **simultaneously**:

**Codebase Researcher:**
- **subagent_type:** `team-researcher`
- **name:** `codebase-researcher`

**Prompt:**
```
You are the Codebase Researcher for the GOAT implementation team.
Read `.claude/commands/goat-team/codebase-researcher.md` in full, then execute your iteration steps.

Task: "$ARGUMENTS"
This is iteration {N}.

Read agent-workspace/PLAN.md and agent-workspace/RESEARCH-LOG.md first.
Follow every step in your role document. End with your completion signal in RESEARCH-LOG.md.

When done, send me a message with your issue count.
```

**Technical Researcher:**
- **subagent_type:** `team-researcher`
- **name:** `tech-researcher`

**Prompt:**
```
You are the Technical Researcher for the GOAT implementation team.
Read `.claude/commands/goat-team/technical-researcher.md` in full, then execute your iteration steps.

Task: "$ARGUMENTS"
This is iteration {N}.

Read agent-workspace/PLAN.md and agent-workspace/RESEARCH-LOG.md first.
Follow every step in your role document. End with your completion signal in RESEARCH-LOG.md.

When done, send me a message with your issue count.
```

**On completion:** Wait for both messages. Read `RESEARCH-LOG.md` to confirm both wrote entries. Mark both tasks completed, shut down both.

Tell the user: "Phase 2 iteration {N}: Codebase researcher found [N] issues, Technical researcher found [N] issues."

### 2b. Plan Revision & Loop Decision

Create an agent task, then spawn:

- **subagent_type:** `team-architect`
- **name:** `planner-review`

**Prompt:**
```
You are the Planner for the GOAT implementation team.
Read `.claude/commands/goat-team/planner.md` in full, then execute Phase 2 (Post-Research Review).

Task: "$ARGUMENTS"
This is iteration {N}.

Read agent-workspace/PLAN.md, agent-workspace/RESEARCH-LOG.md, and agent-workspace/ISSUE-TRACKER.md.
Review all researcher findings from this iteration. Revise the plan as needed.
Evaluate exit criteria and write your signal: LOOP_CONTINUE or LOOP_EXIT.

If LOOP_EXIT: also generate the Implementation Manifest inline — execute Phase 3 (Implementation Manifest) from your role document immediately. Write agent-workspace/IMPLEMENTATION-MANIFEST.md before signaling.

When done, send me a message with your signal (LOOP_CONTINUE or LOOP_EXIT) and, if exiting, confirmation that the manifest is ready.
```

**On completion:** Read `RESEARCH-LOG.md` for the signal:
- `LOOP_CONTINUE` → Mark task completed, shut down planner, go back to 2a with iteration N+1
- `LOOP_EXIT` → Read the manifest. Verify it has batches, parallelism rules, completion criteria, and `PLANNER_SIGNAL: MANIFEST_READY`. Mark task completed, shut down planner.

**If iteration count > 3:** Ask the user whether to continue, adjust scope, or proceed with known gaps.

On loop exit, mark Phase 2 task as `completed`. Tell the user: "Research loop complete after {N} iterations. Manifest ready — {N} batches."

---

## Phase 3 — Implementation

Mark Phase 3 task as `in_progress`. Read `agent-workspace/IMPLEMENTATION-MANIFEST.md` to determine batch structure.

For each batch, create an agent task (use `addBlockedBy` for sequential batches), then spawn:

- **subagent_type:** `team-implementer`
- **name:** `implementer-{N}`

**Prompt:**
```
You are Implementer-{N} for the GOAT implementation team.
Read `.claude/commands/goat-team/implementer.md` in full, then execute your assigned batch.

Task: "$ARGUMENTS"
Your assignment: Batch {N}

Read agent-workspace/PLAN.md and agent-workspace/IMPLEMENTATION-MANIFEST.md.
Execute exactly your batch. Do not touch files outside your scope.
Follow every step in your role document, including the post-implementation index check.

When done, send me a message confirming your batch is complete.
```

**Parallelism:** Batches with no shared files → spawn simultaneously. Shared files → sequential.

**On completion:** Wait for all implementer messages. Verify each batch is COMPLETE. Mark all tasks completed, shut down all implementers.

Mark Phase 3 task as `completed`. Tell the user: "Implementation complete — {N} batches done."

---

## Phase 4 — Index Content Update

Mark Phase 4 task as `in_progress`. Create an agent task, then spawn:

- **subagent_type:** `team-implementer`
- **name:** `index-updater`

**Prompt:**
```
You are the Index Updater for the GOAT implementation team.
Read `.claude/commands/goat-team/index-updater.md` in full, then execute all steps.

Task: "$ARGUMENTS"

Read agent-workspace/IMPLEMENTATION-MANIFEST.md to identify which files were modified.
For each modified file, find its covering INDEX.md, compare the index content against the actual code, and update any inaccuracies.
Write your update log to agent-workspace/REVIEW-LOG.md with the mandatory `### Content Accuracy Updates` section.

When done, send me a message confirming the index update is complete.
```

**On completion:** Read `REVIEW-LOG.md`. Verify `## Index Content Update`, `### Content Accuracy Updates`, and `INDEX_UPDATER_SIGNAL: COMPLETE` are present. If missing, message the agent to fix. Otherwise mark task completed, shut down.

Mark Phase 4 task as `completed`. Tell the user: "Index update complete."

---

## Phase 5 — Review

Mark Phase 5 task as `in_progress`. Create TWO agent tasks, then spawn both **simultaneously**:

**Reviewer A:**
- **subagent_type:** `team-verifier`
- **name:** `reviewer-a`

**Prompt:**
```
You are Reviewer A for the GOAT implementation team.
Read `.claude/commands/goat-team/reviewer.md` in full, then execute all steps.

Task: "$ARGUMENTS"

Read agent-workspace/PLAN.md and agent-workspace/IMPLEMENTATION-MANIFEST.md.
Write your findings to agent-workspace/REVIEW-LOG.md under "## Review A".
Complete the mandatory index verification (verify the Index Updater's work) before issuing your verdict.

When done, send me a message with your verdict (PASS or FAIL).
```

**Reviewer B:**
- **subagent_type:** `team-verifier`
- **name:** `reviewer-b`

**Prompt:**
```
You are Reviewer B for the GOAT implementation team.
Read `.claude/commands/goat-team/reviewer.md` in full, then execute all steps independently.

Task: "$ARGUMENTS"

Read agent-workspace/PLAN.md and agent-workspace/IMPLEMENTATION-MANIFEST.md.
Write your findings to agent-workspace/REVIEW-LOG.md under "## Review B".
Complete the mandatory index verification (verify the Index Updater's work) before issuing your verdict.

When done, send me a message with your verdict (PASS or FAIL).
```

**On completion:** Wait for both messages. Mark both tasks completed, shut down both.

Mark Phase 5 task as `completed`. Tell the user: "Review complete — A: [verdict], B: [verdict]."

---

## Phase 6 — Evaluate & Finalize

Mark Phase 6 task as `in_progress`. Read `agent-workspace/REVIEW-LOG.md` and evaluate.

**Hard gates before accepting PASS:**
1. `## Index Content Update` with `### Content Accuracy Updates` exists (Phase 4 output)
2. `## Index Verification` exists with clean check results

**Both PASS + gates pass:** Mark Phase 6 completed. Summarize to user and clean up team.

**Any FAIL — Critical:** Ask the user for guidance (may need replanning).

**Any FAIL — Major only:** Spawn targeted implementer to fix, re-run Phase 5. Max 2 cycles before asking user.

**Any FAIL — Minor only:** Spawn single implementer to fix, re-run Phase 5. If still fails, ask user.

---

## Wrap Up

When the pipeline completes:

1. **Summarize** to the user: task, iterations, batches, verdicts, index updates, files modified, items needing human verification
2. **Shut down** any remaining agents via `SendMessage` type `shutdown_request`
3. **Clean up** the team with `TeamDelete`
4. **Point the user** to `agent-workspace/` for full artifacts

---

## Staying Available

Throughout the entire pipeline, remain available for user conversation. If the user asks about progress, check `TaskList` and relay the current state. You are both orchestrator and conversational partner.

---

## Project-Specific Rules (include in agent prompts when relevant)

- **Repo type:** Meta-orchestration — this repo contains skill definitions, specs, and logs
- **Primary content:** Markdown files (skill definitions, design docs, spec documents)
- **No application code** — this repo does not contain runtime application code
- **Tooling:** codebase-index-tools (language TBD based on bootstrap)
- **Source of truth:** Code is source of truth — verify against actual files, not docs
