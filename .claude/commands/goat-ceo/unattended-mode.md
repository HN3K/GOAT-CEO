# GOAT-CEO — Unattended Mode (OPT-IN)

> **Read this file ONLY when you are running a genuinely unattended/overnight session with no operator present.**
> In the default **Collaborative** mode, NONE of this applies: you run the interactive pipeline, you checkpoint,
> and you **yield at phase boundaries** per `anti-drift.md` §1 (Checkpoint-and-Yield). This file is the *opt-in*
> survival layer that lets the CEO keep working across auto-compaction when nobody is there to drive.
>
> **Why this is opt-in, not the default (the evidence):** autonomy compounds errors over long horizons, compaction
> is lossy by design, and a standing "never stop" rule directly contradicts the checkpoint-and-yield contract — the
> kind of contradictory constraint that measurably degrades instruction-following. So unattended operation is a
> *narrow tool for a specific situation*, not the operating posture. Default to yielding; engage this only when you
> must run without a human.

---

## 1. Engaging unattended mode — the `AUTONOMOUS-ACTIVE` flag

Unattended operation is gated by a single sentinel: `agent-workspace/AUTONOMOUS-ACTIVE`. When it exists and is
scoped to your session, the keep-going Stop hook (§2) prevents the CEO from yielding control between turns.

**Engage it AFTER intake, not before.** Prefer to write `AUTONOMOUS-ACTIVE` only once intake is complete (after
Steps 1–2 and the Step 3.1 gate-list write). As a robust backstop, the interactive `/goat-ceo` flow writes an
`agent-workspace/INTAKE-ACTIVE` marker during intake and removes it at Step 3.1; while that marker exists the
`check_pipeline_complete.py` hook lets the CEO yield to ask the operator a question even if `AUTONOMOUS-ACTIVE` is
already (globally) set. A non-pipeline autonomous **work-queue** run (no `INTAKE-ACTIVE` marker, no `EXPECTED-GATES`)
engages keep-going normally — so this exemption does NOT weaken unattended operation.

**Scoping (avoid trapping a concurrent collaborative session):**
- Empty file (or the literal `ALL`) → engages **every** GOAT-CEO session in the workspace.
- A file containing `session:<id>` lines → engages **only** those sessions. The resume banner prints your session id.
- **The `session:` substring gotcha:** the hook tests whether the literal string `session:` appears *anywhere* in the
  file (a substring test, not line-parsed). If any prose comment in the file contains `session:`, the file is treated
  as scoped — so keep the file to bare `session:<id>` lines (or empty), with no incidental `session:` text.

**Disengaging:** delete `agent-workspace/AUTONOMOUS-ACTIVE` (operator helper: `scripts/autonomous-off.ps1`). The
resume banner leads with `KEEP-GOING: ON` / `KEEP-GOING: OFF` so you always know the state; if it says OFF and you
are supposed to be unattended, create the flag (operator helper: `scripts/autonomous-on.ps1 -SessionId <id>`).

---

## 2. The keep-going Stop hook (harness-enforced turn-end block)

When `AUTONOMOUS-ACTIVE` is engaged, `check_pipeline_complete.py` (the `Stop` hook) **blocks the CEO's turn from
ending** and re-injects "continue your NEXT_ACTION" — *unless* one of the yield markers exists. So ending a turn with
"continuing autonomously…" as your last line does not work: the hook turns you around and makes you actually take the
next action.

**Yield markers (write one of these to hand control back — the explicit, auditable way to stop):**

| Marker (`agent-workspace/…`) | Meaning |
|---|---|
| `STOP` | Operator hard halt (also the per-tool kill switch — see anti-drift §5). |
| `AWAITING-OPERATOR` | Blocked on an operator-only / irreversible action (push, DB drop, UI/cert). Name exactly what you need. **Delete it when the operator unblocks you and you resume** — otherwise keep-going stays disabled. |
| `SESSION-COMPLETE` | Mission complete. |
| `ESCALATE_REQUIRED` | Need an operator decision (review-cap reached, undeferrable conflict). |

**Independently of the flag**, while any expected `*.GATE` is still missing the hook blocks turn-end — don't end a
session with a pipeline half-done.

**Runaway backstop:** a counter (`agent-workspace/_stop_block_count.json`, CAP ≈ 20) lets the turn end and warns the
operator after ~20 consecutive blocks with no checkpoint progress (no `RESUME-STATE.md` mtime advance) and no marker —
so a stuck CEO surfaces instead of spinning. Don't rely on it; write a marker.

**Legitimate reasons to stop (never for context pressure):**

| Stop reason | Legitimate? | How you yield |
|---|---|---|
| Context window filling / "running low" | **NO — persevere through compaction (§3)** | — |
| You just reported a milestone and have a `NEXT_ACTION` left | **NO — a report is not a stop; take the next action in the SAME turn** | — |
| Operator hard halt | Yes | operator writes `STOP` |
| Blocked on operator-only / irreversible action | Yes | you write `AWAITING-OPERATOR` |
| Mission complete | Yes | you write `SESSION-COMPLETE` |
| Need an operator decision | Yes | you write `ESCALATE_REQUIRED` |

---

## 3. Perseverance through compaction (the never-stop doctrine — unattended only)

**Low context is NOT a stop condition in unattended mode.** Auto-compaction in this harness is automatic, silent, and
made lossless by a survival loop: `check_precompact.py` (PreCompact, never blocks) regenerates the machine-facts block
of `RESUME-STATE.md` before the prune; `inject_handoff_context.py` (SessionStart, `async:false`) re-injects it after.
You do not need to *do* anything for compaction to be safe — you only need to **not stop**.

**DO** keep executing through a high token count (treat it as a non-event); stay lean structurally so compactions are
rare and clean (delegate ALL verbose work to subagents — each has its own window; keep your own turns short; never
read large files yourself); treat files + git as your real memory.

**DO NOT** end your turn / write a "handoff and wait" / spawn a "fresh CEO continuation" / ask the operator to
`/resume` *because context is low*. DO NOT re-plan or re-summarize the whole session after a compaction — read the
re-injected `RESUME-STATE.md`, verify the machine block against git + sentinels, and resume the single `NEXT_ACTION`.

**Compaction is lossy — minimize it, don't celebrate riding through it.** A clean context per phase (subagent-per-
phase) beats a marathon CEO session. The goal is fewer, cleaner cycles, not infinite ones.

---

## 4. Durable resume anchor — `RESUME-STATE.md` machine block + CEO body

`RESUME-STATE.md` has two regions. The **TOP machine block** is owned and regenerated by `check_precompact.py` at
every compaction (git HEAD/branch per repo, `GATES_PRESENT`, `GATES_EXPECTED`, MISSION headline, dated diagnosis
pointers) — **never hand-edit it.** The **BODY** is yours, refreshed at every checkpoint.

```markdown
<!-- BEGIN MACHINE-REFRESH (owned by check_precompact.py — do not hand-edit) -->
COMPACT_REFRESHED_AT: <ISO>
MISSION: <headline>
GATES_PRESENT: [PLAN.GATE, RESEARCH.GATE]
GATES_EXPECTED: [PLAN.GATE, RESEARCH.GATE, IMPLEMENT.GATE, INDEX.GATE, REVIEW.GATE]
GIT_STATE (AUTHORITATIVE on resume — verify against this):
  - goat-ceo  branch=master  head=<sha>  dirty=yes
DIAGNOSIS_DOCS: agent-workspace/DEBUG-FINDINGS-<date>.md
<!-- END MACHINE-REFRESH -->

# RESUME-STATE — durable resume anchor (CEO-owned body — refresh at every checkpoint)
PHASE:        Phase 3 — Implement
TASKS:        # snapshot of TaskList (only active/blocked, not history)
  - id: 3  owner: api-implementer-1  status: in_progress  title: fix token refresh race
NEXT_ACTION:  <single concrete next action>
```

Rules: you write only the body; keep git facts out of the body (they live in the machine block); `NEXT_ACTION` is one
concrete step; on resume, where the machine block and your body disagree, **git + sentinels win** — re-derive and
regenerate immediately. Why machine-readable beats prose: prose narrates a moment and decays within hours; facts name
a state that the resume step verifies against `git log` and `ls *.GATE`, so they cannot silently lie.

---

## 5. Crash resilience beyond a single session (outer loop)

In-session auto-compaction handles low context with zero loss. The remaining risk is the *process* dying (reboot,
terminal closed, fatal error) — which compaction cannot help. For that, an **outer loop** restarts the session and the
SessionStart hook re-injects the anchor, so the CEO resumes where it left off. Wrapper: `scripts/autonomous-loop.ps1`
(and `.sh`) — see its header for usage and the unattended permission posture (`--dangerously-skip-permissions` in a
sandbox, or a tight `permissions.allow` + `dontAsk`, with hard `deny` rules carrying the safety guarantees, since
chat instructions are lost on compaction but deny rules are not). The outer loop is optional for "survive
compaction"; it is what makes the system survive *anything*.

---

## 6. Background stall monitor (out-of-band, unattended only)

In an unattended wave, start a background monitor that alerts ONLY on stall (silent = good). Use `run_in_background:
true` on a Bash call. Primary detection in any mode is the `claude agents` view (anti-drift §4) + the STOP-file; this
script is the unattended add-on for when no human is watching the panel.

```powershell
# Background stall monitor — alerts only when STATUS.md goes stale
$sentinel = "$PWD/agent-workspace/STATUS.md"   # run from the repo root, or set an absolute path
$threshold = 300; $lastAlert = 0
while ($true) {
  if (Test-Path $sentinel) {
    $age = ([DateTime]::UtcNow - (Get-Item $sentinel).LastWriteTimeUtc).TotalSeconds
    if ($age -gt $threshold -and $age -gt $lastAlert) {
      Write-Output "STALL ALERT: STATUS.md not updated for $([int]$age)s — check claude agents view"; $lastAlert = $age
    }
  }
  Start-Sleep -Seconds 60
}
```

(There is **no** `asyncRewake` primitive in Claude Code; this background loop is the portable, verified fallback.)

---

## 7. Handoff & memory size compliance (so the survival loop is actually lossless)

A handoff or memory that exceeds budget gets truncated at the injection boundary or skipped on auto-load — and an
unread anchor is worse than none, because it looks like coverage while silently losing state. Every durable artifact
must stay small enough to inject/load WHOLE.

| Artifact | Budget | Rule |
|---|---|---|
| `RESUME-STATE.md` **body** | ≤ ~2000 chars / ~25 lines | `PHASE` + `NEXT_ACTION` first; `TASKS` = only active/blocked. Snapshot, not log — overwrite, never append. |
| `session-handoff.md` `★ ACTIVE` block | ≤ ~1500 chars | One CURRENT-STATE block. Supersede, don't accumulate; push detail to a dated topic file. |
| `MEMORY.md` (auto-loaded every session) | under the auto-load cap | One-line index entry per memory; move detail into per-memory files. If oversized it truncates or crowds out work. |
| Individual memory files | one fact each | Supersede or delete stale memories rather than appending corrections. Convert relative dates to absolute. |

Every checkpoint: **trim, don't grow.** Treat `agent-workspace/` dated docs as the place for volume (read on demand,
never auto-injected); keep the anchor and memory as thin indices over that detail.
