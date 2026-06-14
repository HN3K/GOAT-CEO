# GOAT-CEO Anti-Drift Supervision Protocol
> Operational runbook for the CEO. Read this at session start and re-read any time an agent appears stalled.
> This file encodes Doctrine #3 (anti-drift / supervision) from the rework design.
> Every mechanism here is a real Claude Code primitive. No invented capabilities.

---

## Why this file exists

The project's #1 failure class: agents ran marathon single turns during which STOP/hold orders were queued but **undeliverable** — messages deliver only at turn boundaries, not while a tool chain is running. This produced unauthorized DB rebuilds, kill-resistant agents, and collisions with a live operator session. The incident names: **marathon-turn/undeliverable-stop** (2026-06-12 session).

The fix is not a message. It is architecture: tight scope (short turns = fast delivery), a STOP-file that fires at the tool boundary (faster than a turn boundary), and a quiet out-of-band monitor that alerts on stall/completion only — not on every heartbeat. This file is the operational discipline that makes those primitives work.

---

## 1. Checkpoint-and-Yield Contract

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

The `{SCOPE_PATH}` placeholder is filled per-agent at spawn time by the CEO. For implementers, it is the batch's file set. For researchers, it is `agent-workspace/` only.

**Why yield matters:** The harness delivers a `SendMessage` to a running subagent only when that subagent finishes a tool call and returns control to the model. A single multi-file `Write` loop with no yield points can hold a turn for many minutes. A bounded unit (one file, one commit, one step) limits that window to seconds.

---

## 2. Hard Bounds

These are harness-enforced — they do not rely on the agent's compliance.

### 2a. maxTurns cap (implementer and verifier)

Set in agent frontmatter:

```yaml
maxTurns: 30
```

This is configured on `team-implementer` and `team-verifier`. When an agent hits its cap, the harness stops it and reports `TeammateIdle`. The CEO treats a `maxTurns` stop the same as a normal completion: read `agent-workspace/STATUS.md` for the last checkpoint, inspect what was written, decide whether to re-spawn with a narrower scope.

**Do not increase `maxTurns` in response to an agent "not finishing."** Re-spawn with a tighter scope instead. A large `maxTurns` is a symptom of over-scoped work.

### 2b. Time-budget yield (PostToolBatch / SubagentStart hook pair)

**Availability-gate this before relying on it.** Run:

```
claude --version
```

If the installed version supports `PostToolBatch` and `SubagentStart` hooks, the hook pair `check_turn_budget.py` + `write_start_time.py` is active (wired in project-scope `.claude/settings.json`). It reads a start-time file written by `SubagentStart` and forces exit 2 if elapsed > 30 minutes, causing a hard yield.

**If those hooks are absent:** `maxTurns` (§2a) is the primary hard cap. The stall monitor (§4) is the secondary detection layer. Do not assume the time-budget hook is active without confirming the version.

### 2c. Review iteration cap

The review fix loop is capped at 2 iterations. A sidecar file `agent-workspace/REVIEW-ITERATION.txt` tracks the count. The `check_review_gate.py` hook (`TaskCompleted`) reads this file. On iteration 3+, it writes `ESCALATE_REQUIRED` to `agent-workspace/` and exits with a message to the CEO. The CEO does not spawn iteration 3 silently — it escalates to the operator.

---

## 3. STATUS.md Heartbeat Schema

Every agent writes a one-line heartbeat to `agent-workspace/STATUS.md` at each checkpoint. The file is APPENDED (not overwritten) so the CEO can read the full event trail.

**Format (one line per checkpoint):**

```
{ISO_TIMESTAMP} | {AGENT_NAME} | {PHASE} | {UNIT} | {STATUS}
```

**Status values:**
- `RUNNING` — in progress, next checkpoint in ≤5 tool calls
- `CHECKPOINT` — bounded unit complete, yielding
- `BLOCKED` — STOP-file fired or out-of-scope request; ended turn
- `DONE` — all assigned work complete
- `ERROR` — unexpected failure; see RESEARCH-LOG.md or REVIEW-LOG.md for detail

**Examples:**

```
2026-01-15T14:03:07Z | api-implementer-2 | Phase-3 | Batch-2/file:src/loader.py | CHECKPOINT
2026-01-15T14:07:22Z | api-implementer-2 | Phase-3 | Batch-2/file:src/validator.py | CHECKPOINT
2026-01-15T14:09:01Z | api-implementer-2 | Phase-3 | Batch-2 | DONE
```

**Why STATUS.md and not SendMessage:** An in-band message to the CEO burns the CEO's context. A file write is free. The CEO reads STATUS.md on-demand (when the stall monitor fires, or when deciding whether to re-scope). The CEO does NOT poll STATUS.md — that is the monitor's job.

---

## 4. Quiet Out-of-Band Monitor (the side-channel pattern)

### 4a. The claude agents view (primary)

During any pipeline wave:

1. Open the `claude agents` view (the agents panel in the Claude Code UI).
2. The panel refreshes every ~15 seconds. It shows each running agent's name, model, status, and the most recent tool call.
3. An agent showing `Working` with no new tool calls across two refresh cycles (~30 seconds) is a candidate stall. An agent that has not written to `agent-workspace/STATUS.md` for > 5 minutes while showing `Working` is a confirmed stall.

**What the CEO does NOT do:** send an in-band poll message ("how is it going?") to the running agent. That message queues for the next turn boundary — exactly the problem. The out-of-band view answers "is it moving?" without spending a message.

### 4b. Background stall monitor

When running a batch of implementers, start a background stall monitor. Use `run_in_background: true` on a Bash tool call.

**Platform note:** This machine is Windows 11. The Bash tool uses Git Bash, which may or may not have GNU coreutils `stat -c %Y` available. Use the PowerShell variant below if `stat` is unreliable — it is always available on this machine.

**PowerShell variant (recommended for this machine):**

```powershell
# Background stall monitor — PowerShell — alerts only on stall, silent otherwise
$sentinel = "agent-workspace/STATUS.md"
$thresholdSeconds = 300  # 5 minutes = stall threshold
$lastAlertAge = 0

while ($true) {
  if (Test-Path $sentinel) {
    $lastWrite = (Get-Item $sentinel).LastWriteTimeUtc
    $ageSeconds = ([DateTime]::UtcNow - $lastWrite).TotalSeconds
    if ($ageSeconds -gt $thresholdSeconds -and $ageSeconds -gt $lastAlertAge) {
      Write-Output "STALL ALERT: STATUS.md not updated for $([int]$ageSeconds)s — check claude agents view"
      $lastAlertAge = $ageSeconds
    }
  }
  Start-Sleep -Seconds 60
}
```

**Bash variant (if Git Bash has coreutils):**

```bash
# Background stall monitor — Bash — alerts only on stall
SENTINEL="agent-workspace/STATUS.md"
THRESHOLD_SECONDS=300
LAST_ALERT=0

while true; do
  if [ -f "$SENTINEL" ]; then
    # GNU stat: stat -c %Y; BSD/macOS stat: stat -f %m
    # On Windows Git Bash without coreutils, both may fail — use PowerShell variant instead
    LAST_MOD=$(stat -c %Y "$SENTINEL" 2>/dev/null || stat -f %m "$SENTINEL" 2>/dev/null)
    if [ -n "$LAST_MOD" ]; then
      NOW=$(date +%s)
      AGE=$(( NOW - LAST_MOD ))
      if [ $AGE -gt $THRESHOLD_SECONDS ] && [ $AGE -gt $LAST_ALERT ]; then
        echo "STALL ALERT: STATUS.md not updated for ${AGE}s — check claude agents view"
        LAST_ALERT=$AGE
      fi
    fi
  fi
  sleep 60
done
```

**The monitor fires ONLY on stall.** Silent = good; output = investigate. A monitor that talks every 15 seconds trains the CEO to ignore it; a monitor that talks only on anomaly gets acted on.

**No `asyncRewake` primitive exists in Claude Code.** Any reference to `asyncRewake: true` in prior design documents refers to a speculative/unverified feature that does not appear in current docs. Do not rely on it. The background Bash/PowerShell loop above is the portable, verified fallback and is sufficient.

### 4c. Stall response protocol

When the monitor fires or the `claude agents` view shows an anomaly:

1. **Do not immediately send a message.** First read `agent-workspace/STATUS.md` (last few lines). If `CHECKPOINT` or `DONE` appears recently, the monitor was a false alarm (file-mod lag). No action needed.
2. **If genuinely stalled** (no `STATUS.md` update, agent shows `Working` in panel for > 5 min): write `agent-workspace/STOP` — this fires the `PreToolUse` hook at the agent's **next tool boundary**, which is faster than a turn boundary. The agent will write `BLOCKED` to STATUS.md and end its turn.
3. **After the STOP fires** (agent surfaces and shows output): read STATUS.md, read any partial output in `agent-workspace/`, decide whether to re-spawn with narrower scope or resume.
4. **To clear the STOP and allow the agent to resume** (after you have confirmed it is safe): run `Remove-Item agent-workspace/STOP` in a Bash call. The hook already whitelists this specific remove command.

---

## 5. STOP-File Kill Switch

### 5a. What it is

`agent-workspace/STOP` is a sentinel file. The `check_stop_file.py` hook is wired at `PreToolUse` in **user-scope** `~/.claude/settings.json`. It is a user-scope hook so it reaches agents running in all repo subdirectories — not just the GOAT-CEO root.

**Matcher (widened from default — see design §C.1 #2):**

```json
{ "matcher": "Bash|PowerShell|Write|Edit" }
```

The original matcher was `Bash|PowerShell`. The rework widens it to include `Write` and `Edit` so an implementer doing only file mutations (no Bash calls) is also gated. An agent that writes but never runs a shell command was previously invisible to the stop-file gate.

### 5b. How to issue a hard stop

```
# Write the STOP file — fires at the agent's next tool boundary
# Use an absolute path; the agent's cwd may differ from the CEO's
Write agent-workspace/STOP with content: "CEO_STOP {ISO_TIMESTAMP}"
```

Or equivalently from a Bash tool call:

```bash
echo "CEO_STOP $(date -u +%Y-%m-%dT%H:%M:%SZ)" > "agent-workspace/STOP"
```

### 5c. When to use hard stop vs soft redirect

| Situation | Action |
|-----------|--------|
| Agent is between turns (shows Idle or TeammateIdle) | SendMessage — delivers immediately |
| Agent is mid-turn, you need to redirect scope gently | SendMessage — queues for next turn boundary; acceptable if scope is tight |
| Agent is mid-turn, you need it to stop NOW (stall, unauthorized scope, destructive action imminent) | Write STOP — fires at next tool boundary, faster than a turn boundary |
| Agent has stopped and you want to give it new instructions | SendMessage or re-spawn with new prompt |
| Agent is ignoring messages (marathon turn > 5 min, no STATUS.md update) | Write STOP, then monitor `claude agents` view for BLOCKED status |

**Never** use both a STOP and a rapid re-spawn simultaneously. Write STOP, confirm the agent has surfaced (watch STATUS.md or the agents panel), THEN decide to re-spawn. Racing a STOP with a re-spawn creates two agents potentially in the same scope.

### 5d. Per-repo STOP files for multi-repo waves

In a multi-repo CEO session, the `check_stop_file.py` hook checks a list of `STOP_PATHS` configured in the hook script. Each repo's `agent-workspace/STOP` path should be in that list. The user-scope hook reaches agents in any cwd.

When you need to stop ALL agents simultaneously (e.g., a cross-repo conflict that invalidates work in progress):

```bash
# Stop all active repos at once
foreach ($repo in @("C:/path/repo-a", "C:/path/repo-b")) {
  $ts = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
  Set-Content "$repo/agent-workspace/STOP" "CEO_STOP $ts"
}
```

To resume individual repos, remove their STOP files one at a time: `Remove-Item <repo>/agent-workspace/STOP`.

---

## 6. Drift Detection and Correction Protocol

### 6a. Drift patterns and triggers

| Pattern | Signal | Response |
|---------|--------|----------|
| **Marathon turn** | `claude agents` panel shows `Working` > 5 min with no STATUS.md update | Write STOP. Re-scope after agent surfaces. |
| **Scope creep** | Agent STATUS.md or output references files outside `{SCOPE_PATH}` | Write STOP immediately. The `PreToolUse` path-check hook (if wired) has already gated the write; if not wired, the STATUS.md is your early warning. Re-spawn with explicit scope. |
| **Silent completion claim** | Agent reports DONE but STATUS.md shows no CHECKPOINT entries and no new commits on its worktree branch | Do NOT accept the claim. Run `git log worktree-<name>` and read STATUS.md. If empty: the agent completed nothing. Re-spawn. |
| **Unauthorized rebuild/mutation** | Agent's STATUS.md UNIT field references a DB or file not in its batch assignment | Write STOP. Verify what was actually written before re-scoping. |
| **Message pile-up** | You have sent 3+ messages to an agent and none have been acknowledged | The agent is in a marathon turn. Write STOP. Do not send more messages. |

### 6b. After a STOP fires — the recovery checklist

1. Read `agent-workspace/STATUS.md` — last N lines. What was the last CHECKPOINT UNIT?
2. Run `git diff` on the agent's worktree branch (if using worktree isolation) or on main (if not isolated). What was actually written?
3. Confirm the written state is consistent with the CHECKPOINT entries. If they diverge (agent wrote files not in STATUS.md), treat the written state as authoritative.
4. Determine: is the partial work safe to keep, or does it need to be rolled back before re-spawning?
5. Re-spawn with a prompt that includes: the last confirmed CHECKPOINT UNIT, the files already written, and a narrower scope for the remaining work.

### 6c. Drift from the MISSION, not just from scope

Scope creep is a file-level symptom. Architectural drift is subtler: an agent that is technically in scope but is solving a different problem than what the PLAN.md specifies. Detection:

- **Research drift:** researcher returns findings unrelated to the 5-condition convergence gate. Verify against `agent-workspace/PLAN.md` section by section.
- **Implementation drift:** implementer implements something not in `agent-workspace/IMPLEMENTATION-MANIFEST.md`. The `check_artifacts.py` hook catches missing artifacts on `SubagentStop`; the inverse (extra artifacts) is detected by the CEO reading the git diff.
- **Review drift:** reviewer issues a PASS on criteria not in `PLAN.md`'s acceptance block, while silent on criteria that ARE in the block. The `check_toolcall_audit.py` hook and the completeness-critic pass catch this mechanically.

In all three cases: the correction is NOT to ask the drifted agent to self-correct in the same turn. End the turn (STOP or let it yield), read what it produced, then re-spawn with a prompt that explicitly names the missing item and states "your ONLY job this turn is X."

### 6d. Drift correction message template

When re-spawning after drift:

```
You are {AGENT_NAME} resuming Phase {N} for {REPO_PREFIX}.

Prior state:
- Last confirmed checkpoint: {LAST_CHECKPOINT_UNIT}
- Files already written: {FILES_WRITTEN}
- What was missed or drifted: {DRIFT_DESCRIPTION}

Your ONLY job this turn:
{SINGLE_BOUNDED_UNIT}

Do NOT re-do work already confirmed in STATUS.md.
Do NOT expand scope beyond the single unit above.
Report CHECKPOINT to STATUS.md when the unit is complete, then YIELD.
```

This template enforces the three anti-drift properties: bounded unit, no scope expansion, mandatory yield.

---

## 7. CEO Altitude Discipline (anti-context-burn)

The CEO is the most expensive agent in the session. Context burn is the #1 cause of the CEO "forgetting" a gate criterion mid-session — the chronic long-session failure mode.

**Rules:**

1. **Never explore deeply yourself.** If you need to understand a codebase decision, spawn a `team-researcher` or `team-ceo-assistant`. Do not run 30 `Read` calls in your own turn.
2. **Monitor out-of-band.** Read STATUS.md when the monitor fires. Do not poll it on every turn.
3. **Plan lives in files, not context.** The current phase gate state is in `agent-workspace/*.GATE`. The mission is in `agent-workspace/MISSION.md`. Re-read the file when you need the state — do not maintain it in working memory across turns.
4. **When idle (pipelines running), do lightweight non-colliding work only.** Memory persistence, next-phase briefs, decision-queue consolidation. Stay interruptible. Do not spawn new agents while existing ones are mid-turn on the same files.
5. **Gate transitions, do not narrate them.** When Phase N completes: check the gate sentinel (`agent-workspace/PHASE.GATE`), advance, spawn the next phase. One action. Do not write multi-paragraph summaries to yourself of what just happened.

**The `Stop` hook** (`check_pipeline_complete.py`) enforces the terminal gate: the CEO cannot end the session while any `*.GATE` is missing or `ESCALATE_REQUIRED` is set. This is the harness telling you "you are not done" without relying on you to remember.

---

## 8. Checkpoint-Cadence Durable Handoff Refresh (Doctrine #2 + #3)

> **First live-run lesson (HARNESS-SELF-REVIEW.md F1):** a prose session handoff **decays within hours** during fast iteration. On the 2026-06-13 run the top-block diagnosis was already false within the same evening (it asserted a blocker was a "stale red herring" when the fix had in fact landed and a fresh rebuild had failed elsewhere). The anchors that actually restored state were `git log`, the `*.GATE` / status sentinels, and a **dated** diagnosis doc — never the narrative. So the durable handoff is **not a session-end chore. It is regenerated at every checkpoint, and it is FACTS, not prose.**

### 8a. The hard rule (non-negotiable, tied to Checkpoint-and-Yield §1)

A "checkpoint" is any of: the CEO writes a `*.GATE` sentinel; the CEO advances a phase; or a bounded unit completes under the §1 Checkpoint-and-Yield contract. **At every checkpoint, in the SAME turn, BEFORE spawning the next phase or going idle, the CEO MUST regenerate the durable handoff:**

1. **Rewrite `agent-workspace/RESUME-STATE.md`** — the machine-readable resume anchor (schema in §8b). Overwrite it whole; it is a snapshot, not a log.
2. **Refresh the `★ ACTIVE` block of `session-handoff.md`** to a one-line pointer at RESUME-STATE.md + the single next action. Keep the narrative short; the facts live in RESUME-STATE.md.

**The harness has your back, but do not lean on it for quality.** The `check_precompact.py` PreCompact hook is **self-healing and never blocks** (it must not — blocking an automatic compaction at high context would deadlock an unattended run; see §9 and anthropics/claude-code#941). At every compaction it regenerates a machine-derived facts block (git HEAD/branch per repo, `GATES_PRESENT`, `GATES_EXPECTED`, MISSION headline, diagnosis-doc pointers) at the top of `RESUME-STATE.md` and then ALLOWS compaction. So even if you forget, the *factual floor* always survives a prune. What the hook canNOT derive is your intent — `PHASE`, the `TASKS` snapshot, and the single concrete `NEXT_ACTION`. **That is your job at every checkpoint**, and it is what turns a bare factual floor into a true zero-loss resume. Do it.

The discipline order is: **do the bounded unit → write its `*.GATE` (if it closes a phase) → refresh the RESUME-STATE.md body (PHASE/TASKS/NEXT_ACTION) → THEN advance.** The hook owns the machine block; you own the body. (The old flat 24h staleness clock AND the old block-on-stale behavior are both gone — neither survived contact with autonomous operation.)

### 8b. `RESUME-STATE.md` structure — a hook-owned machine block + a CEO-owned body

The file has **two regions**. The TOP block is owned and rewritten by `check_precompact.py` at every compaction — never hand-edit it. The BODY below it is yours, refreshed at every checkpoint. The injector surfaces the whole file; resume reads the machine block as authoritative and the body for intent.

```markdown
<!-- BEGIN MACHINE-REFRESH (owned by check_precompact.py — regenerated at every compaction; do not hand-edit) -->
COMPACT_REFRESHED_AT: 2026-06-13T20:15:00Z
MISSION: <MISSION.md headline>
GATES_PRESENT: [PLAN.GATE, RESEARCH.GATE]
GATES_EXPECTED: [PLAN.GATE, RESEARCH.GATE, IMPLEMENT.GATE, INDEX.GATE, REVIEW.GATE]
GIT_STATE (machine-derived; AUTHORITATIVE on resume — verify against this, Doctrine #2):
  - goat-ceo  branch=master              head=626011a  dirty=yes
  - api       branch=feature/login-fix   head=a1b2c3d  dirty=no
DIAGNOSIS_DOCS (dated machine-written evidence; outrank prose):
  - agent-workspace/DEBUG-FINDINGS-2026-01-15.md
<!-- END MACHINE-REFRESH -->

# RESUME-STATE — durable resume anchor   (CEO-owned body below — refresh at every checkpoint)
PHASE:        Phase 3 — Implement
TASKS:        # snapshot of TaskList (id / owner / status / title)
  - id: 3  owner: api-implementer-1  status: in_progress  title: fix token refresh race
  - id: 4  owner: api-reviewer-a     status: blocked      title: dual review
NEXT_ACTION:  <single concrete next action the resuming CEO should take>
```

Rules: (a) you write only the body — the machine block is regenerated for you; (b) keep `GATES_PRESENT`/git facts out of the body (they live in the machine block, captured from `git rev-parse` and the `*.GATE` glob, never remembered); (c) `NEXT_ACTION` is one concrete step, not a plan; (d) on resume, where the machine block and your body disagree (e.g. a gate exists that your body's PHASE predates), the machine block + git win — re-derive and continue.

### 8c. Why machine-readable beats prose for resume

- **Prose narrates a moment; facts name a state.** "the bug is in the cache layer" is an interpretation that goes stale. `head: a1b2c3d` + `GATES_PRESENT: [...]` are checkable against `git log` and `ls agent-workspace/*.GATE` — they cannot silently lie, because the resume step verifies them.
- **The injector privileges it.** The `inject_handoff_context.py` SessionStart hook injects `RESUME-STATE.md` FIRST (authoritative) and the `session-handoff.md` prose block SECOND (secondary, "may be stale"), under a Doctrine-#2 "VERIFY BEFORE TRUSTING" banner. So a fresh/compacted session resumes from facts, then reconciles the narrative against them.
- **It closes the F1 gap.** A restart mid-pipeline reconstructs the full state from RESUME-STATE.md + `git` + sentinels, with zero reliance on a decayed top block.

---

## 9. Autonomous Perseverance Through Compaction (the never-stop doctrine)

> **The single most important rule for unattended operation: low context is NOT a stop condition. You do not pause, hand off, or wait for the operator because the context window is filling. There may be no human present. Stopping = the mission halts indefinitely. You persevere.**

### 9a. Why you can safely keep going

Auto-compaction in this harness is **automatic, silent, and lossless**. When the window fills, the harness summarizes older turns and continues in the same session — no confirmation, no pause. This repo wraps that built-in behavior in a survival loop so nothing is lost across the prune:

```
        you keep working ──▶ context fills ──▶ harness auto-compacts
              ▲                                          │
              │                                          ▼
   SessionStart(source=compact) re-injects      PreCompact self-heals:
   RESUME-STATE.md (async:false, guaranteed)  ◀── writes the machine facts
   + "PERSEVERE, continue from NEXT_ACTION"        block to RESUME-STATE.md,
                                                    then ALLOWS the compaction
```

Both ends are harness-enforced and were execution-verified: `check_precompact.py` (never blocks, always refreshes the anchor) and `inject_handoff_context.py` (re-injects it, async:false so it lands before your first post-compaction turn, with an explicit "re-read the file by absolute path" fallback). You do not need to *do* anything for compaction to be safe — you only need to **not stop**.

### 9b. What you do — and do NOT do — as context fills

- **DO keep executing.** Treat a high token count as a non-event. Continue the current bounded unit, write your checkpoint anchor as always (§8), spawn the next phase. The compaction will happen under you and you will continue on the other side.
- **DO stay lean structurally** so compaction is rare and clean (quality degrades a little with each summarization, so minimize them): delegate ALL verbose work to subagents — each teammate/subagent gets its **own** context window, and only a short structured result returns to you (this is the biggest lever you have, and agent-teams are already enabled). Keep your own turns short. Never read large files or run wide searches in your own turn — that is a researcher's job.
- **DO treat files + git as your real memory** (the Ralph principle). Your context is disposable scratch space; the durable state is `RESUME-STATE.md`, `agent-workspace/` artifacts, the `*.GATE` sentinels, `MISSION.md`, and git. Anything important must live there, not in your head — then summarization can never lose it.
- **DO NOT** end your turn, write a "handoff and wait", spawn a "fresh CEO continuation", or ask the operator to `/resume` or start a new session **because context is low**. That instinct (trained by older handoff-before-compaction habits) is now wrong and is the exact behavior we are removing. The handoff is automatic; your job is to keep moving.
- **DO NOT** re-plan, re-summarize the whole session to yourself, or re-derive completed phases after a compaction. Read the re-injected RESUME-STATE.md, verify the machine block against git + sentinels (Doctrine #2), and resume the single `NEXT_ACTION`.

### 9c. The only legitimate reasons to stop

Stopping is reserved for genuine terminal conditions — never for context pressure:

| Stop reason | Legitimate? |
|---|---|
| Context window is filling / "running low" | **NO — persevere through compaction** |
| `agent-workspace/STOP` written by the operator | Yes — operator hard stop |
| `ESCALATE_REQUIRED` set (review iteration cap, undeferrable conflict) | Yes — surface to operator, then idle |
| All `*.GATE` present + mission complete | Yes — clean shutdown (protocols.md Part 5 "Normal completion") |
| A decision genuinely requires the operator (and Channels/escalation can't proceed unattended) | Yes — escalate, then idle |

For everything else: keep working.

### 9d. Crash resilience beyond a single session (Tier 2)

In-session auto-compaction (above) handles low context with zero loss. The remaining risk is the *process* dying (machine reboot, terminal closed, fatal error) — which compaction cannot help with. For that, an **outer loop** restarts the session and the SessionStart hook re-injects the anchor, so the CEO resumes exactly where it left off. The ready-to-launch wrapper is `scripts/autonomous-loop.ps1` (and `.sh`); see its header for usage and the unattended permission posture (`--dangerously-skip-permissions` in a sandbox, or a tight `permissions.allow` + `dontAsk`, with hard `deny` rules carrying the safety guarantees — chat instructions are lost on compaction, deny rules are not). The outer loop is optional for "survive compaction"; it is what makes the system survive *anything*.

---

## 10. Handoff & Memory Size Compliance (small enough to be read, or it is worthless)

> **A handoff or memory that exceeds budget gets truncated at the injection boundary or skipped on auto-load — and an unread anchor is worse than none, because it looks like coverage while silently losing state (this is the F1 truncation, made permanent).** Every durable artifact this system writes MUST stay small enough to be injected/loaded WHOLE. Compliance is not optional polish; it is what makes the perseverance loop (§9) actually lossless.

### 10a. The budgets (hard)

| Artifact | Budget | Rule |
|---|---|---|
| `RESUME-STATE.md` **body** (CEO-owned) | ≤ ~2000 chars / ~25 lines | `PHASE` + `NEXT_ACTION` first; `TASKS` = only the *active/blocked* ones, not the whole history. It is a **snapshot, not a log** — overwrite it, never append. The machine block on top is bounded by the hook (≤12 repos, ≤10 diagnosis pointers). `check_precompact.py` stamps `HANDOFF_HEALTH:` every compaction and flags `BODY_OVERSIZE` — when you see that flag, trim immediately. |
| `session-handoff.md` `★ ACTIVE` block | ≤ ~1500 chars | One CURRENT-STATE block. **Supersede, don't accumulate**: when state changes, replace the block (mark the old one `(superseded)` and push detail to a dated topic file). Long prose here is the thing that decays (F1) — keep it to a pointer + the single next move. |
| `MEMORY.md` (auto-loaded EVERY session) | under the auto-load cap | This file is injected into context on every session start — if it bloats, it either gets truncated or crowds out real work. One **one-line** index entry per memory (`- [Title](file.md) — hook`). Move all detail into the per-memory file. The existing note "removed here to keep this index under the auto-load size cap" is the standing discipline — honor it. |
| Individual memory files | one fact each | One memory = one file = one fact (per the memory protocol). Don't grow a file into an essay. **Supersede or delete** stale memories rather than appending corrections; a wrong memory that is still loaded actively misleads. Convert relative dates to absolute. |

### 10b. Why the injection is robust even so (but don't lean on it)

`inject_handoff_context.py` is built to degrade gracefully: it injects **critical-first** (re-read pointer → machine facts → `PHASE`/`NEXT_ACTION` → rest of body → prose), caps each region independently, and appends an explicit `…[truncated — read the full anchor at <abs path>]` marker plus an always-present re-read pointer in the banner. So if something is oversized, the resume degrades to "go read the file from disk," not silent loss. **But that is the safety net, not the plan** — if the file on disk is itself bloated, re-reading it just burns the context you were trying to save. The plan is: keep the artifacts small enough to inject whole.

### 10c. The discipline (every checkpoint: trim, don't grow)

- When you refresh `RESUME-STATE.md` (§8), **prune** finished tasks and stale detail rather than piling on. If `NEXT_ACTION` changed, replace it; don't keep a trail.
- When you persist memory, first check for an existing file that already covers it and **update/supersede** it; add at most a one-line `MEMORY.md` pointer. Never write session-only chatter to memory.
- Treat `agent-workspace/` dated docs (`*-FAILURE.md`, probe outputs, Gate-B reports) as the place for *volume* — they're pointed at from the anchor, read on demand, and never auto-injected. Keep the anchor and memory as thin indices over that detail.
- If you're tempted to write a long narrative "so the next session understands," stop: the next session reads `RESUME-STATE.md` (facts) + `git` + the dated docs it points to. Narrative is the thing that decays and gets cut. Write the pointer, not the essay.
