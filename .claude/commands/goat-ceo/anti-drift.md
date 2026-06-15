# GOAT-CEO Anti-Drift Supervision Protocol

> Operational runbook for the CEO. Read at session start; re-read any time an agent appears stalled.
> **Default posture is Collaborative:** agents do bounded units, checkpoint, and **YIELD at phase boundaries** so the
> operator can steer. The opt-in never-stop / keep-going / survive-compaction behavior is NOT here — it lives in
> `unattended-mode.md` and applies only when you have deliberately engaged unattended operation.
> Every mechanism here is a real Claude Code primitive. No invented capabilities.

---

## Why this file exists

The project's #1 failure class: agents ran marathon single turns during which STOP/hold orders were queued but
**undeliverable** — messages deliver only at turn boundaries, not while a tool chain is running. This produced
unauthorized mutations, kill-resistant agents, and collisions with a live operator session.

The fix is not a message. It is architecture: tight scope (short turns = fast delivery), a STOP-file that fires at the
tool boundary (faster than a turn boundary), and a quiet out-of-band monitor that alerts on stall/completion only.
This file is the operational discipline that makes those primitives work.

---

## 1. Checkpoint-and-Yield Contract (the default behavior)

**Every agent spawn prompt MUST include this block verbatim (or by reference to this file):**

```
CHECKPOINT-AND-YIELD CONTRACT:
- Do ONE bounded unit (one batch, one file set, one phase step). Report a structured result.
  Then YIELD — end your turn so queued messages and STOP signals can reach you.
- Never run a marathon. Tight scope = short tool chains = short turns = fast delivery of
  any queued redirect or STOP.
- Before any consequential action (file write, git operation, mutation), check: does the
  STOP-file PreToolUse hook allow this? If blocked, write a state note to
  agent-workspace/STATUS.md, send a checkpoint message to your contact, and END YOUR TURN.
  Do NOT retry or work around a STOP block.
- Your file scope is: {SCOPE_PATH}. Do not modify files outside this path. If you need
  something outside scope, checkpoint and ask.
```

The `{SCOPE_PATH}` placeholder is filled per-agent at spawn time. For implementers it is the batch's file set; for
researchers it is `agent-workspace/` only.

**Yielding is the default and it is correct.** The CEO yields at phase boundaries; agents yield after each bounded
unit. This is what keeps the pipeline navigable and the operator in control. The *only* place yielding is suppressed
is opt-in Unattended mode (`unattended-mode.md`), where a keep-going hook holds the turn — never assume that mode
unless you have explicitly engaged it.

**Why yield matters:** the harness delivers a `SendMessage` to a running subagent only when it finishes a tool call
and returns control. A single multi-file `Write` loop with no yield points can hold a turn for many minutes. A bounded
unit limits that window to seconds.

---

## 2. Hard Bounds

These are harness-enforced — they do not rely on the agent's compliance.

### 2a. maxTurns cap (implementer and verifier)

`maxTurns: 30` on `team-implementer`, `maxTurns: 20` on `team-verifier` (agent frontmatter). When an agent hits its
cap, the harness stops it and reports `TeammateIdle`. Treat a `maxTurns` stop like a normal completion: read
`STATUS.md` for the last checkpoint, inspect what was written, decide whether to re-spawn with a narrower scope.
**Do not raise `maxTurns` because an agent "didn't finish."** Re-spawn with tighter scope — a large cap is a symptom
of over-scoped work.

### 2b. Time-budget yield (availability-gated)

If the installed version supports `PostToolBatch` + `SubagentStart`, the `check_turn_budget.py` + `record_agent_start.py`
pair forces a hard yield when an agent runs > ~30 min. **Verify with `claude --version` before relying on it; if
absent, `maxTurns` (§2a) is the primary cap.** This is a secondary belt to `maxTurns` + the STOP-file, most relevant
to long unattended runs.

### 2c. Review iteration cap

The review fix loop is capped at 2 iterations (`agent-workspace/REVIEW-ITERATION.txt`). `check_review_gate.py` reads
it; on iteration 3+ it writes `ESCALATE_REQUIRED` and surfaces to the operator. The CEO does not spawn iteration 3
silently — it escalates.

---

## 3. STATUS.md Heartbeat Schema

Every agent writes a one-line heartbeat to `agent-workspace/STATUS.md` at each checkpoint. **Appended** (not
overwritten) so the CEO can read the full event trail.

```
{ISO_TIMESTAMP} | {AGENT_NAME} | {PHASE} | {UNIT} | {STATUS}
```

Status values: `RUNNING` (next checkpoint ≤5 tool calls) · `CHECKPOINT` (bounded unit done, yielding) · `BLOCKED`
(STOP fired / out-of-scope; ended turn) · `DONE` (all assigned work complete) · `ERROR` (see RESEARCH-LOG.md /
REVIEW-LOG.md).

**Why STATUS.md and not SendMessage:** an in-band message burns the CEO's context; a file write is free. The CEO reads
STATUS.md on-demand (when the monitor fires, or when deciding whether to re-scope) — it does NOT poll it.

---

## 4. Quiet Out-of-Band Monitor

### 4a. The `claude agents` view (primary, all modes)

During any wave, watch the `claude agents` panel (~15s refresh): name, model, status, most recent tool call. An agent
showing `Working` with no new tool calls across two refresh cycles (~30s) is a candidate stall; one that has not
written STATUS.md for > 5 min while showing `Working` is a confirmed stall.

**The CEO does NOT send an in-band poll** ("how's it going?") to a running agent — that message queues for the next
turn boundary, exactly the problem. The out-of-band view answers "is it moving?" without spending a message.

(For genuinely unattended runs with no human at the panel, add the background stall-monitor script in
`unattended-mode.md` §6 — it alerts only on stall.)

### 4b. Stall response protocol

1. **Don't immediately message.** First read `STATUS.md` (last lines). A recent `CHECKPOINT`/`DONE` = false alarm
   (file-mod lag); no action.
2. **If genuinely stalled** (no STATUS.md update, `Working` > 5 min): write `agent-workspace/STOP` — fires the
   `PreToolUse` hook at the agent's **next tool boundary** (faster than a turn boundary). The agent writes `BLOCKED`
   and ends its turn.
3. **After STOP fires:** read STATUS.md + partial output, decide re-spawn-with-narrower-scope or resume.
4. **To clear the STOP** (once safe): `Remove-Item agent-workspace/STOP` (the hook whitelists this remove).

---

## 5. STOP-File Kill Switch

### 5a. What it is

`agent-workspace/STOP` is a sentinel. `check_stop_file.py` is wired at `PreToolUse` in **project scope**
(`.claude/settings.json`) with matcher `Bash|PowerShell|Write|Edit`, so it gates every write-capable tool in this repo
— including an implementer doing only file mutations (no Bash). For a multi-repo CEO session, ALSO wire it at
**user scope** (`~/.claude/`) with absolute STOP paths so it reaches teammate sessions rooted in other repositories
(see §5d).

### 5b. How to issue a hard stop

```
# Use an absolute path; the agent's cwd may differ from the CEO's.
Write agent-workspace/STOP with content: "CEO_STOP {ISO_TIMESTAMP}"
```

### 5c. Hard stop vs soft redirect

| Situation | Action |
|-----------|--------|
| Agent between turns (Idle / TeammateIdle) | SendMessage — delivers immediately |
| Agent mid-turn, gentle scope redirect | SendMessage — queues for next turn boundary; OK if scope is tight |
| Agent mid-turn, must stop NOW (stall / unauthorized scope / destructive action imminent) | Write STOP — fires at next tool boundary |
| Agent stopped, new instructions | SendMessage or re-spawn |
| Agent ignoring messages (marathon > 5 min, no STATUS.md) | Write STOP, then watch the panel for BLOCKED |

**Never** race a STOP with a rapid re-spawn — write STOP, confirm the agent surfaced, THEN decide to re-spawn.

### 5d. Per-repo STOP files for multi-repo waves

The project-scope hook checks this repo's `agent-workspace/STOP`. For multi-repo coverage, the optional user-scope
hook checks a list of `STOP_PATHS`; each repo's `agent-workspace/STOP` should be in it. To stop ALL agents at once,
write each repo's STOP file; to resume, remove them one at a time.

---

## 6. Drift Detection and Correction Protocol

### 6a. Patterns and triggers

| Pattern | Signal | Response |
|---------|--------|----------|
| **Marathon turn** | `Working` > 5 min, no STATUS.md update | Write STOP; re-scope after surface |
| **Scope creep** | STATUS.md/output references files outside `{SCOPE_PATH}` | Write STOP; re-spawn with explicit scope |
| **Silent completion claim** | reports DONE but no CHECKPOINT entries and no commits on its branch | Don't accept; `git log` the branch + read STATUS.md; if empty, re-spawn |
| **Unauthorized mutation** | STATUS.md UNIT references a DB/file not in its batch | Write STOP; verify what was actually written before re-scoping |
| **Message pile-up** | 3+ unacknowledged messages | It's in a marathon turn — write STOP; stop sending messages |

### 6b. After a STOP fires — recovery checklist

1. Read STATUS.md last N lines — what was the last CHECKPOINT UNIT?
2. `git diff` the agent's branch (worktree) or main — what was actually written?
3. If written state diverges from STATUS.md, treat the written state as authoritative.
4. Decide: partial work safe to keep, or roll back before re-spawning?
5. Re-spawn with: last confirmed CHECKPOINT, files already written, and a narrower scope for the remainder.

### 6c. Drift from the MISSION, not just scope

Scope creep is file-level; architectural drift is subtler — an agent technically in scope but solving a different
problem than `PLAN.md`. Detect per-phase: research drift (findings unrelated to the convergence gate — check PLAN.md
section by section), implementation drift (building something not in `IMPLEMENTATION-MANIFEST.md` — `check_artifacts.py`
catches missing artifacts; the inverse is caught by the CEO reading the git diff), review drift (PASS on criteria not
in PLAN.md's acceptance block — `check_toolcall_audit.py` + the completeness critic catch this).

In all cases: do NOT ask the drifted agent to self-correct in the same turn. End the turn, read what it produced, then
re-spawn with a prompt that names the missing item and states "your ONLY job this turn is X."

### 6d. Drift correction template

```
You are {AGENT_NAME} resuming Phase {N} for {REPO_PREFIX}.
Prior state:
- Last confirmed checkpoint: {LAST_CHECKPOINT_UNIT}
- Files already written: {FILES_WRITTEN}
- What was missed or drifted: {DRIFT_DESCRIPTION}
Your ONLY job this turn: {SINGLE_BOUNDED_UNIT}
Do NOT re-do confirmed work. Do NOT expand scope. Report CHECKPOINT to STATUS.md, then YIELD.
```

---

## 7. CEO Altitude Discipline (the load-bearing rule)

The CEO is the most expensive agent in the session, and context burn is the #1 cause of the CEO "forgetting" a gate
criterion mid-session. **This is the single most important supervision rule — treat it as load-bearing, not one
guideline among many.**

1. **Never explore deeply yourself.** Need to understand a codebase decision? Spawn a `team-researcher` or
   `team-ceo-assistant`. Do not run 30 `Read` calls in your own turn.
2. **Monitor out-of-band.** Read STATUS.md when the monitor fires; do not poll every turn.
3. **Plan lives in files, not context.** Gate state is in `agent-workspace/*.GATE`; the mission is in `MISSION.md`.
   Re-read the file when you need the state — don't carry it in working memory across turns.
4. **When idle (pipelines running), do lightweight non-colliding work only** — memory persistence, next-phase briefs,
   decision-queue consolidation. Stay interruptible.
5. **Gate transitions, don't narrate them.** Phase N completes → check the gate sentinel, advance, spawn the next
   phase. One action. No multi-paragraph self-summaries.

The `Stop` hook (`check_pipeline_complete.py`) enforces the terminal gate: the CEO cannot end the session while any
expected `*.GATE` is missing or `ESCALATE_REQUIRED` is set — the harness telling you "you are not done" without
relying on you to remember.

---

## 8. Checkpoint Discipline (durable state)

A "checkpoint" is any of: the CEO writes a `*.GATE`; advances a phase; or a bounded unit completes. At each one, in
the same turn before advancing, refresh the **body** of `agent-workspace/RESUME-STATE.md` (PHASE, `TASKS` snapshot
from `TaskList`, single concrete `NEXT_ACTION`) and append a one-line STATUS.md heartbeat. This is cheap state hygiene
that makes any `/resume` or restart zero-loss.

You write only the body. The **machine block** on top of `RESUME-STATE.md` (git HEAD/branch per repo, `GATES_PRESENT`,
diagnosis pointers) is regenerated automatically by `check_precompact.py` — never hand-edit it. On resume, where the
machine block and your body disagree, **git + sentinels win**: re-derive and regenerate the body immediately.

The full machine-block schema, the compaction-survival rationale, and the handoff/memory size budgets live in
`unattended-mode.md` (§4, §7) — they matter most for long/unattended runs. In Collaborative mode, this lightweight
checkpoint discipline is all you need; do not turn it into a multi-file ceremony every gate.
