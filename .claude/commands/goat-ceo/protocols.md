# GOAT-CEO Protocols Reference
> Read by the CEO on-demand during execution: cross-repo routing, phase-gate transitions, clean-shutdown, recovery. All primitives used here are from `GOAT-CEO-REWORK-DESIGN.md §0` — do not invent beyond that list.

---

## Part 0 — Session Setup (first CEO actions every wave)

> **Intake prerequisite (Rule #8 — non-skippable):** Before any step below runs, the CEO MUST have completed `goat-ceo.md` Steps 1 and 2 in full: repo list confirmed with the operator (including any `ro-reference` repos), Step 1.2 prerequisite/index check run for EVERY active `rw` repo, INDEX-AVAILABLE or INDEX-UNAVAILABLE recorded in `repo-registry.json`. The steps below are the AUTONOMOUS phase that follows confirmed intake — do not start them based on a directive goal alone.
>
> **Read-only reference repos (Rule #8):** Repos with `access: "ro-reference"` in `repo-registry.json` are ground-truth sources. Agents may READ them (Read/Grep/Glob tool calls, cite file:line). Agents are FORBIDDEN from writing to them — no Write, Edit, Bash mutation, or git operation targeting a reference repo path. The git-commit/push guard and STOP-file kill switch already block most mutations; this briefing makes the intent explicit for any operation those hooks do not cover.

**Step 1 — Create the team.** The CEO's first action is `TeamCreate` with a session-scoped name (`goat-ceo-YYYYMMDD-HHMM`). Config lives at `~/.claude/teams/{name}/config.json`. The CEO becomes the fixed lead. All Overseers will become teammates of this team.

**Step 2 — Spawn Overseers as background teammates.** For each repo in the wave, spawn the `team-overseer` agent with `run_in_background: true` so the CEO turn does not block while Overseers initialize. Assign each Overseer a task via `TaskCreate` with its repo name as the task name and the Overseer's name as the owner. The shared task list IS the live cross-repo pipeline dashboard.

**Step 3 — Write `agent-workspace/MISSION.md`, `agent-workspace/PHASE-GATES.json`, and `agent-workspace/EXPECTED-GATES.txt`.** MISSION.md holds the goal, wave scope, and open questions. PHASE-GATES.json maps each role to the sentinel file it requires before it may Write/Edit/Bash (flat top-level object, no "roles" wrapper). EXPECTED-GATES.txt activates the `check_pipeline_complete.py` Stop hook — without it the hook fails open and never blocks session end. Write one sentinel filename per line:
```
PLAN.GATE
RESEARCH.GATE
IMPLEMENT.GATE
INDEX.GATE
REVIEW.GATE
```
All three files must exist before any Overseer starts Phase 1.

**Step 4 — Workflow ID awareness.** If a Workflow script is used to drive the pipeline, record its ID in MISSION.md immediately after launch. Workflows resume only within the same session — if the session ends with a Workflow in flight, the next session must restart it from the last completed phase (not resume mid-script). The prose fallback state-machine in `goat-ceo.md §4.B` is the recovery path.

**Step 5 — Concurrency cap.** The platform supports a maximum of 16 concurrent agents per Workflow phase and 1000 total agents per session. Size phases accordingly: ≤16 parallel implementers or reviewers per phase; batch larger sweeps.

---

## Part 1 — Cross-Repo Communication Flows

### Tier Classification (classify before routing every OUTBOUND flag)

**Tier 1 — Informational:**
The change is additive and non-breaking. The affected repo needs to know but no code change is required on its side. CEO relays directly to the affected Overseer via `SendMessage`. No CEO-Assistant spawn needed.
- Examples: new API endpoints (not modified), new config keys added (not renamed), progress updates, new optional parameters.

**Tier 2 — Breaking (requires CEO-Assistant assessment):**
The change may break a consuming repo. CEO spawns or resumes a `team-ceo-assistant` against the AFFECTED repo's actual files before routing.
- Examples: API signature changes, schema column renames/drops, removed endpoints, behavioral changes, dependency version bumps.

**Classification rule:** If the Overseer's flag says "non-breaking" AND the change is strictly additive (nothing removed, nothing renamed, nothing changed), → Tier 1. Otherwise → Tier 2. The CEO errs toward Tier 2 on ambiguity. The CEO-Assistant is cheap; a missed breaking change is not.

**Session topology check:** Agent teams are single-session, single-cwd. Overseer-to-Overseer `SendMessage` works only if both Overseers share the same session. If repos are in independent sessions, ALL inter-repo communication goes through the CEO — it reads one session's STATUS.md and relays to the other. Validate session topology before relying on peer-relay.

---

### OUTBOUND — A Change in Repo A That May Affect Repo B

**Trigger:** Overseer for Repo A reports a completed change that touches a shared contract, API, schema, or interface.

1. Overseer reports to CEO: what changed (old → new, specific `file:line`), why it changed (task context), preliminary flag: "potentially breaking" or "likely non-breaking". Overseer errs on the side of flagging — impact assessment is the CEO-Assistant's job, not the Overseer's.

2. CEO classifies the tier.

3. **Tier 1 path:** CEO sends a `SendMessage` to the affected Overseer with the full change description. CEO writes a one-liner to `logs/<affected-prefix>/cross-repo.log`: `[ISO_TIMESTAMP] TIER1_RELAY — <what changed> from <source-prefix>`. Done.

4. **Tier 2 path:** CEO spawns `team-ceo-assistant` named `ceo-assistant-<affected-prefix>`, targeting `<affected-repo-path>`. Spawn with `permissionMode: plan` (read-only scout — HARD, not advisory). The CEO-Assistant's mission is: "Read the actual files in this repo. Find all usages of `<changed surface>`. Determine severity: CONFIRMED_BREAKING / NO_IMPACT / UNCLEAR. Cite `file:line` for every reference you find. Return a structured JSON block: `{\"verdict\": \"...\", \"severity\": \"...\", \"affected_files\": [...], \"evidence\": [...]}`. Do NOT propose fixes."

5. CEO-Assistant returns the JSON block. CEO reads it.
   - `NO_IMPACT` → log as false alarm. No routing. Done.
   - `CONFIRMED_BREAKING` or `UNCLEAR` → proceed to step 6.

6. CEO writes to `logs/<affected-prefix>/cross-repo.log`: `[ISO_TIMESTAMP] TIER2_ASSESSMENT — <verdict>/<severity> — <affected-prefix> impact from <source-prefix>. Files: <list>`.

7. CEO routes to the affected Overseer via `SendMessage`: "Cross-repo change from `<source-prefix>`: `<what changed>`. CEO-Assistant verdict: `<CONFIRMED_BREAKING|UNCLEAR>`. Severity: `<severity>`. Affected files in your repo: `<list with file:line>`. You must address this before your Phase 5 gate closes."

8. If the affected Overseer is mid-implementation, CEO classifies: rework-now vs. address-in-review. Default = address-in-review (less disruption). CEO escalates to operator only if the conflict cannot be deferred.

---

### INBOUND — Receiving a Cross-Repo Notification in Repo B

**Trigger:** CEO sends an Overseer information about a change in a related repo.

- **Planning or Research phase:** Overseer instructs the active architect or researcher to incorporate the new information. Update PLAN.md or RESEARCH-LOG.md. Flag the change as an external input. No escalation needed unless scope changes materially.

- **Implementation phase (non-breaking or easily absorbed):** Overseer adjusts the current or next implementer batch scope. No escalation needed.

- **Implementation phase (requires rework or conflicts with in-flight batch):** Overseer escalates to CEO: what conflicts, what batch is affected, what rework is required. CEO decides: (a) pause the implementer batch, (b) let the batch complete and address in review, (c) replan. CEO relays the decision back to the Overseer. CEO writes to `decisions.log`.

- **Review phase:** Overseer adds the cross-repo change as an explicit additional review criterion for both reviewers (Reviewer A and B). Criterion: "Verify that `<changed surface>` integration from `<source-prefix>` is handled correctly."

---

### REQUEST — Repo A Needs Information From Repo B

**Trigger:** Overseer needs specific information from another repo to proceed (API signature, schema shape, config value, etc.).

1. Overseer messages CEO: "Need `<specific info>` from `<target-prefix>`. Reason: `<why>`. Urgency: `<blocking|non-blocking>`."

2. CEO spawns `team-ceo-assistant` named `ceo-assistant-<target-prefix>` with `permissionMode: plan`. Mission: "Find `<specific info>` in this repo. Use `codebase-index-tools search` and `inject` first. Fall back to direct file reads. Cite `file:line`. Return the information in a structured block." CEO-Assistant does NOT speculate — if the information is absent or ambiguous, it returns `{"found": false, "note": "..."}`.

3. CEO receives the result. CEO relays to the requesting Overseer via `SendMessage`. CEO writes to `cross-repo.log`: `[ISO_TIMESTAMP] REQUEST_FULFILLED — <target-prefix> → <requesting-prefix>: <summary>`.

4. If the CEO-Assistant returned `found: false`, CEO tells the Overseer: "Information not available in `<target-prefix>` at this time. Options: (a) proceed with stated assumption documented in PLAN.md, (b) escalate to operator."

---

### PAUSE / RESUME — Dependency Management

**Trigger:** CEO determines one repo is ahead of a dependency and must wait.

**Pause:**
1. CEO sends `SendMessage` to the ahead Overseer: "PAUSE — waiting for `<other-prefix>` to reach Phase `<N>`. Continue your current unit to completion. Do not start the next phase."
2. Running agents finish their current bounded unit and report back normally. The Overseer does not spawn the next batch.
3. Overseer acknowledges PAUSE to CEO. CEO writes to `logs/<prefix>/timeline.log`: `[ISO_TIMESTAMP] PAUSE — <prefix> paused pending <other-prefix> Phase <N>`.

**Resume:**
1. When the blocking repo reaches the required phase, CEO sends `SendMessage` to the paused Overseer: "RESUME — `<other-prefix>` has reached Phase `<N>`. Proceed to Phase `<M>`."
2. Overseer proceeds to spawn the next phase's agents.
3. CEO writes to `logs/<prefix>/timeline.log`: `[ISO_TIMESTAMP] RESUME — <prefix> resumed after <other-prefix> Phase <N> complete`.

---

## Part 2 — Phase Gate Protocol

### Gate Sentinels

Each phase end is gated by a sentinel file in `agent-workspace/`. The `check_phase_gate.py` `PreToolUse` hook reads `agent-workspace/PHASE-GATES.json` (written by the CEO at wave start) to map role → required sentinel.

```
agent-workspace/PLAN.GATE         — written by CEO after SubagentStop hook validates PLAN.md structure
agent-workspace/RESEARCH.GATE     — written by CEO after 5-condition AND-gate passes
agent-workspace/IMPLEMENT.GATE    — written by CEO after worktree merge + broad suite passes
agent-workspace/INDEX.GATE        — written by CEO after codebase-index-tools check --all returns 0 stale
agent-workspace/REVIEW.GATE       — written by CEO after judge JSON "verdict": "PASS" + dual reviewer PASS
agent-workspace/RUBRIC.GATE       — (OPTIONAL, only for RUBRIC-AVAILABLE repos) written by CEO after `rubric check` exits 0 on the merged diff; added to EXPECTED-GATES only for such waves

(No hook writes any *.GATE file. Hooks only VALIDATE — exit 0 to allow, exit 2 to block;
check_review_gate.py additionally writes ESCALATE_REQUIRED. The CEO is the sole gate writer,
which keeps gate advancement a deliberate CEO decision, not a hook side effect.)
```

The `check_pipeline_complete.py` Stop hook blocks the CEO's turn from ending while any `*.GATE` is missing or `agent-workspace/ESCALATE_REQUIRED` is set.

### Phase Transitions (CEO actions at each gate)

**Native plan-approval gate (Phase 1 → Phase 2):**
The architect (`team-architect`) runs as a teammate in plan mode. After the architect submits its plan, the **CEO reviews the plan draft and explicitly approves it** using the native teammate plan-approval primitive before the architect proceeds to execution mode. This is the native implementation of the Phase 1→2 gate — it replaces the old `goat-plan` separate-session pattern with a harness-enforced approval step. The CEO MUST approve the plan before the architect may take any write action. Criteria for approval: PLAN.md contains all required sections, the fenced JSON acceptance-criteria block is present, and all criteria are testable (not vague). If the plan fails criteria: CEO rejects with specific required changes; architect revises and resubmits.

**Plan → Research (PLAN.GATE write):**
- After CEO plan-approval (above), the `SubagentStop` hook `.claude/hooks/check_artifacts.py` verifies PLAN.md exists and has the required structure when the architect subagent stops. On success it exits 0 (allows the subagent to stop). **The hook does NOT write PLAN.GATE** — it only validates artifact presence. **(HARD validation — hook live)**
- CEO action: after `check_artifacts.py` passes (task closes), **CEO explicitly writes `agent-workspace/PLAN.GATE`** to advance the pipeline, then spawns researchers.

**Research → Implement (RESEARCH.GATE write):**
- CEO (or overseer) verifies the 5-condition AND-gate: both researchers at 0 open issues, all ISSUE-TRACKER.md items resolved or dismissed, no plan gaps, every step has an executable command, BOTH `IMPLEMENTATION-MANIFEST.md` AND `IMPLEMENTATION-MANIFEST.json` exist. The CEO confirms the partition with `python .claude/hooks/check_partition.py` (exit 0 = valid; independent batches are file-disjoint, blockedBy refs resolve). The same validator also runs as a `SubagentStop` gate on the architect, so an invalid partition blocks the architect's stop. On pass, CEO writes `RESEARCH.GATE`.
- CEO action: spawn implementers (with worktree isolation if parallel).

**Implement → Index (IMPLEMENT.GATE write):**
- CEO merges worktree branches in fixed order, running the broad suite between each merge (`check_test_gate.py` via TaskCompleted, or CEO-run equivalent). On all merges passing, CEO writes `IMPLEMENT.GATE`.
- CEO action: spawn index-updater on merged main (no isolation — runs ONCE on main, never per-worktree).

**Index → Review (INDEX.GATE write):**
- CEO runs `codebase-index-tools check --all --format json` on merged main; parses JSON; if `stale > 0` or `missing > 0`, re-spawns the index-updater to fix and re-checks. On `0 stale / 0 missing`, CEO writes `INDEX.GATE`. (No index-check hook is wired; this gate is CEO-validated. A `TaskCompleted` index hook could be added later, but is not present today.)
- CEO action: spawn Reviewer A + Reviewer B simultaneously.

**Review → Verify/Finalize (REVIEW.GATE write):**
- `check_review_gate.py` on TaskCompleted: parses judge's JSON verdict block; exit 2 unless `"verdict": "PASS"`; increments `REVIEW-ITERATION.txt`. On iteration > 2, exit 1 (allow) but writes `ESCALATE_REQUIRED`.
- Completeness critic runs as a haiku subagent after both reviewers: emits JSON list of acceptance criteria addressed by neither reviewer. CEO reads this before advancing.
- On dual PASS + judge PASS + no uncovered criteria, CEO writes `REVIEW.GATE`.
- CEO action: Phase 6 — CEO runs broad suite independently.

**Verify (Phase 6 — CEO-run):**
- CEO runs the broad suite against a frozen baseline (the commit SHA at the start of the wave, recorded in `agent-workspace/BASELINE.txt`).
- If the CEO's run fails after the implementer's run passed: red flag for branch/cwd mismatch — investigate before proceeding.
- On pass + all five GATE sentinels present + `ESCALATE_REQUIRED` absent: CEO commits via `ceo-commit.sh <pathspec>`, writes SESSION COMPLETE to the dashboard.

---

## Part 3 — Anti-Drift Supervision Protocol

### Out-of-Band Monitor (never poll in-band)

The CEO monitors running agents via two side-channels. Do NOT send in-band poll messages to a busy agent — messages deliver only at turn boundaries, and a marathon turn has no boundaries.

**Side-channel 1 — `claude agents` view:** The 15-second-refresh summary shows agent status, longest-running item, and most recent output. An agent showing "Working" with no status update for anomalously long signals stall or marathon. The CEO checks this view after each cross-repo event or on a natural pause.

**Side-channel 2 — STATUS.md heartbeat:** Agents write one-line heartbeat updates to `agent-workspace/STATUS.md` at each checkpoint. Schema:
```
[ISO_TIMESTAMP] [AGENT_NAME] [PHASE] [CURRENT_UNIT] [STATUS: working|checkpoint|yielding|done]
```
The CEO monitors STATUS.md staleness via a background Bash until-loop (`run_in_background: true`). This platform is Windows 11; `stat -c %Y` (GNU) and `stat -f %m` (BSD/macOS) are NOT available natively. Use PowerShell to read the last-write timestamp:

**PowerShell (Windows — preferred on this platform):**
```powershell
$sentinel = "agent-workspace/STATUS.md"
$threshold = 120  # seconds
while ($true) {
    $age = ([DateTime]::UtcNow - (Get-Item $sentinel).LastWriteTimeUtc).TotalSeconds
    if ($age -gt $threshold) { Write-Output "STALL detected: $sentinel is ${age}s old"; break }
    Start-Sleep 30
}
```

**Bash fallback (only if Git Bash with GNU coreutils is confirmed installed):**
```bash
sentinel="agent-workspace/STATUS.md"
threshold=120
while true; do
    age=$(( $(date +%s) - $(date -r "$sentinel" +%s 2>/dev/null || echo 0) ))
    [ "$age" -gt "$threshold" ] && { echo "STALL: $sentinel is ${age}s old"; break; }
    sleep 30
done
```

When the loop exits, the CEO receives a notification and checks whether STATUS.md updated (progress) or the staleness threshold was met (stall). If stall: CEO writes `agent-workspace/STOP` — the `PreToolUse` hook halts the agent at its next tool boundary (faster than a turn boundary).

**Note:** There is no native `asyncRewake` primitive in Claude Code. The PowerShell/Bash background loop above is the correct and portable stall-detection mechanism.

### Hard Stop vs Soft Redirect

| Situation | CEO action | Delivery |
|---|---|---|
| Agent is stalled / marathon / hit unauthorized territory | Write `agent-workspace/STOP` | Fires at next tool boundary (fast) |
| Agent needs a course correction but is working normally | `SendMessage` with specific redirect | Fires at next turn boundary |
| Agent needs to be shut down cleanly | `SendMessage`: "Complete your current unit, write STATE note, then stop." + write `STOP` as backup | Message first; STOP as safety net |

### STOP-File Lifecycle

- CEO writes `agent-workspace/STOP` to halt agents.
- The `PreToolUse` hook (`check_stop_file.py`) reads this file before every `Bash`/`PowerShell`/`Write`/`Edit` call and exits 2 if present.
- The hook contains an explicit allow for `Remove-Item .../STOP` so the CEO can clear the file to resume.
- After clearing STOP and verifying agent state, CEO resumes by `SendMessage`: "STOP cleared. Resume from `<last STATE note>`. Write a STATUS.md heartbeat before your first tool call."

---

## Part 4 — Worktree Reconvergence (§D Integration)

Fan-out is cheap; reconvergence is the bottleneck. A pure serial "merge → full suite → merge" is
Amdahl-bound — it caps fan-out speedup at ~1/s (s = the test-suite fraction of total work) and stops
paying off at roughly N ≈ 1/s branches. The CEO reconverges using a **speculative batch** strategy driven
by the structured partition the architect emits. Merge stays CEO-driven (single committer, Doctrine #1);
the design rationale is `GOAT-CEO-REWORK-DESIGN.md §D`.

### Input — the partition manifest (`IMPLEMENTATION-MANIFEST.json`)

The architect emits this machine-readable partition alongside the human-readable `IMPLEMENTATION-MANIFEST.md`:

```json
{
  "baseRef": "<SHA the worktrees branch from>",
  "coordinatorBatch": "batch-3",
  "frozenInterfaces": ["payments.charge(amount, currency)", "User.serialize()"],
  "batches": [
    { "id": "batch-1", "branch": "worktree-auth",
      "files": ["src/auth/login.py", "src/auth/session.py"],
      "mergeOrder": 1, "blockedBy": [], "ownsSharedResources": false },
    { "id": "batch-3", "branch": "worktree-deps",
      "files": ["package-lock.json", "src/registry.py"],
      "mergeOrder": 3, "blockedBy": ["batch-1"], "ownsSharedResources": true }
  ]
}
```

Field rules:
- `files` — explicit and **disjoint across independent batches**. Two batches with `blockedBy: []` MUST have
  non-overlapping `files`; the integrate stage refuses to speculatively batch any two that overlap.
- `mergeOrder` — total order for stacked landing and for the bisect fallback.
- `blockedBy` — batch ids this batch depends on (stacked work). Non-empty ⇒ the branch was cut from its
  parent's tip, not from `baseRef`, and lands AFTER its parents (bottom-up).
- `ownsSharedResources` — exactly ONE batch (`coordinatorBatch`) owns every shared/generated/lockfile
  resource (lockfiles, route tables, DI registries, generated code); all other batches must avoid them.
- `frozenInterfaces` — signatures touched by >1 batch; no batch may change them. This defends against the
  semantic conflict git is blind to (a signature change in one file + a new caller in a disjoint file).

### Integrate procedure (CEO-driven)

1. **Per-branch scope verify.** For each branch, CEO spawns a read-only `team-verifier`: "Run
   `git diff <baseRef>..worktree-<name>`. Confirm the changed paths are a SUBSET of this batch's `files[]`
   and that no `frozenInterfaces` signature changed. PASS/FAIL with file:line." Do NOT merge a FAIL branch.

2. **Speculative batch (independent branches).** Take all PASS branches with `blockedBy: []`. Because their
   `files[]` are disjoint they cannot textually conflict. On a throwaway integration branch off `baseRef`,
   merge them all (`--no-ff`), then run the BROAD suite ONCE on the combined state.
   - **Green →** fast-forward `master` to the integration branch (one validated, coherent landing — the
     serial fraction shrinks to a single suite run, not one-per-branch).
   - **Red →** fall back to LINEARIZED landing: re-merge the same branches one at a time in `mergeOrder`,
     running the suite after each, until it reddens — that branch is the culprit (the merge position IS the
     bisect result; no separate `git bisect` needed). Eject it, escalate it, re-batch the remainder.

3. **Stacked batches (dependent branches).** Land batches with non-empty `blockedBy` bottom-up in
   `mergeOrder`, after their parents are on `master`. If a parent landed with changes, restack (rebase the
   dependent branch onto the new `master` tip) before merging; re-run the suite after each land.

4. **Conflict handling.** A textual conflict on a *verified-disjoint* batch means the partition was wrong —
   treat it as a partition-quality failure. Do NOT force-merge: (a) CEO cherry-picks non-conflicting commits,
   (b) CEO spawns a manual-merge subagent with both branches + the conflict, or (c) escalate. Log it as
   evidence the partition was not actually disjoint.

5. **Land complete.** CEO writes `IMPLEMENT.GATE`. Phase 4 (index update) runs ONCE on merged main.

6. **Cleanup.** CEO removes merged worktrees (`git worktree remove worktree-<name> --force`);
   `cleanupPeriodDays: 7` sweeps orphans.

7. **Pathspec discipline.** Every CEO `git add` uses explicit pathspecs; `git add -A` / `git add .` are
   denied at the settings level and never typed, even during recovery.

**Best-of-N selection.** If a batch ran best-of-N (k attempts in k worktrees for one hard task), the winner
is chosen by EXECUTING the batch's tests, never by an LLM judge — only the winner's branch enters step 1;
discard losing worktrees with `git worktree remove --force`.

---

## Part 5 — Clean Shutdown Protocol

### Normal completion

1. All `*.GATE` sentinels exist. `ESCALATE_REQUIRED` is absent. `.claude/hooks/check_pipeline_complete.py` Stop hook allows the CEO turn to end. **(HARD — hook live)**
2. CEO writes SESSION COMPLETE dashboard entry.
3. CEO updates `repo-registry.json` with the wave's outcome (committed SHA, phase reached, open questions).
4. CEO writes `agent-workspace/MISSION.md` final state checkpoint.
5. If milestone-level task: CEO spawns `team-roadmap-architect` type-2 close (updates the roadmap milestone as complete with evidence).
6. **Graceful shutdown (native shutdown protocol):** CEO sends a `SendMessage` to each active Overseer: "Pipeline complete. Finish your current unit, write your final STATUS.md entry, then shut down." Each Overseer acknowledges shutdown or rejects (with reason). CEO waits for Overseer acknowledgement before calling `TeamDelete`. If an Overseer does not acknowledge within a reasonable time, CEO uses the forced shutdown path below.
7. CEO calls `TeamDelete` to disband the team and clean up teammate processes. Do not skip `TeamDelete` — it ensures clean process termination. If teammates are still running when `TeamDelete` is called, the call fails; send shutdown requests first.

### Forced shutdown (operator STOP only)

> Context pressure is NOT a forced-shutdown trigger. This path fires only on an operator `STOP` file or a genuine terminal escalation — never because the window is filling. For low context, see "Context-limit approach" below — compaction gives durable, machine-grounded resume and is not a shutdown trigger.

1. CEO writes `agent-workspace/STOP` immediately (halts all agent tool calls at their next boundary).
2. CEO writes `agent-workspace/MISSION.md` with CURRENT STATE block: phase reached, which sentinels exist, which agents were running (names + last STATUS.md entry), which tasks were open, what the next action should be.
3. CEO updates `repo-registry.json` partial state.
4. CEO writes a final STATUS.md entry: `[ISO_TIMESTAMP] CEO SESSION_END phase=<N> reason=forced next=<action>`.
5. CEO response to operator: concise state summary referencing `MISSION.md` path and the next-action line.

### Context-limit approach (mode-dependent)

Auto-compaction in this harness is automatic and silent, and gives **durable, machine-grounded resume** (git state + sentinels + a compact machine-refresh block) — the machine-verifiable floor is preserved across the prune; running narrative is capped and can decay. It is **not** a shutdown trigger in either mode.

**Collaborative (default):** when your window fills, keep working — stay lean (delegate verbose work to subagents, keep your turns short, never read large files yourself) and treat files + git (`RESUME-STATE.md`, `agent-workspace/`, `*.GATE`, `MISSION.md`) as your durable memory. After a compaction, resume: read the re-injected `RESUME-STATE.md`, verify its machine block against `git` + `*.GATE`, then continue the single `NEXT_ACTION` — do not re-plan or re-derive completed phases. You still yield to the operator at phase boundaries (that's the default).

**Unattended (opt-in):** the keep-going survival layer additionally prevents the CEO from yielding *between* turns, so an unattended run continues across compaction with no human present. Engage it only for genuinely unattended runs, after intake. For perseverance discipline, the outer-loop wrapper (`scripts/autonomous-loop.ps1`, process-death resilience), and the resume-anchor schema, see `unattended-mode.md` (§3–§5).

---

## Part 6 — Recovery Protocol

### Agent crash / context exhaustion / unresponsive agent

**Detection:** Agent has not written a STATUS.md heartbeat in > 2× the expected unit time, and the `claude agents` view shows it stalled.

1. CEO writes `agent-workspace/STOP` (cancels further tool calls from the stalled agent).
2. CEO reads `agent-workspace/` to determine state:
   - Which `*.GATE` sentinels exist (what phases completed).
   - Which artifacts are present (PLAN.md, RESEARCH-LOG.md, IMPLEMENTATION-MANIFEST.md, etc.).
   - What the agent's last STATUS.md entry says.
   - Whether the agent committed anything to its worktree branch (`git log worktree-<name>` if applicable).
3. CEO clears the STOP file (`Remove-Item agent-workspace/STOP`).
4. CEO spawns a replacement agent of the same type with a reconstruction brief:
   ```
   Resume from [PHASE] for [REPO].
   Existing artifacts: [LIST].
   Your worktree branch (if applicable): worktree-<name>.
   Last state note: [LAST_STATUS_LINE].
   Read agent-workspace/ before any action. Write a STATUS.md heartbeat as your first action.
   Continue from: [SPECIFIC_NEXT_ACTION].
   ```
5. CEO writes to `logs/<prefix>/timeline.log`: `[ISO_TIMESTAMP] AGENT_RECOVERED — <name> respawned from Phase <N>`.

### /resume behavior note

`/resume` restores the CEO's context but does NOT restore in-process teammates. On resume, the CEO MUST: (a) read `agent-workspace/MISSION.md`, (b) check STATUS.md for last heartbeats, (c) check which `*.GATE` sentinels exist, (d) use the `claude agents` view to see if any agents are still running or idle, then treat unresponsive ones as crashed and apply the recovery steps above.

### Overseer crash (multi-repo wave)

Same as agent crash recovery above, with two additions:
- CEO also checks the per-repo `logs/<prefix>/timeline.log` for last known phase.
- The replacement Overseer is spawned with the OUTBOUND/INBOUND flow context for its repo's relationships (read from `repo-registry.json`).

---

## Part 7 — Escalation Protocol

### Escalation triggers

- `ESCALATE_REQUIRED` written by `check_review_gate.py` after 2 review iterations.
- Judge issues a verdict of `FAIL` with findings that cannot be addressed within the current wave scope.
- Cross-repo conflict that cannot be deferred to review (both repos in active implementation, conflict is in shared foundation code).
- CEO-Assistant returns `UNCLEAR` on a Tier-2 impact assessment and the Overseer cannot proceed without resolution.
- Infrastructure failure (repo unreachable, codebase-index-tools failing, test runner broken).

### Escalation to operator format

When escalating, the CEO provides exactly:
1. **What happened:** the specific gate that fired or the conflict encountered.
2. **What was tried:** the fix loops already attempted (with iteration numbers).
3. **The decision needed:** a specific binary or multiple-choice question, not an open-ended "what should I do?"
4. **The cost of each option:** brief, concrete.
5. **CEO's recommendation:** which option, and why, in one sentence.

The CEO does NOT dump raw agent output, full reviewer transcripts, or long diffs in the escalation — those are available in `agent-workspace/` for the operator to pull if needed.

### After operator decision

CEO relays the decision to the relevant Overseer via `SendMessage`, updates `MISSION.md`, writes to `decisions.log`, clears `ESCALATE_REQUIRED` if applicable, and resumes the pipeline at the appropriate phase gate.

### Remote approval via Channels (unattended runs)

For unattended pipeline runs where the operator is away, the CEO can surface blocking decisions to the operator's phone via **Channels** (requires `claude --channels plugin:telegram@claude-plugins-official` at session launch, v2.1.80+). Channels pushes permission prompts and escalation messages to Telegram/Discord so the operator can approve or deny remotely.

**Constraints and non-substitutions:**
- Channels is a research preview requiring the `--channels` flag; not available on Bedrock/Vertex/Foundry.
- The session MUST be running (open terminal) for events to arrive. This is not a fully-unattended mechanism — for fully-unattended runs where nobody will watch the session, use `--dangerously-skip-permissions` with hard deny rules instead (never as a substitute for deny rules).
- For this harness, Channels is OPTIONAL: use it when an operator wants remote approval on blocking escalations without being at the terminal. When not using Channels, the CEO escalates in-band and the operator responds on their next check-in.

---

## Part 8 — Logging (Lightweight, Direct)

The `team-ceo-scribe` agent is REMOVED. The CEO logs directly. Three files per repo, written by the CEO using the `Write`/`Edit` tools (the CEO's own permissions allow this; subagents do not write log files).

**Files:**
- `logs/<prefix>/timeline.log` — phase events, agent spawns/shutdowns, PAUSE/RESUME.
- `logs/<prefix>/decisions.log` — CEO decisions affecting repo strategy.
- `logs/<prefix>/cross-repo.log` — all cross-repo communications routed through CEO.

**Entry format:**
```
[YYYY-MM-DDTHH:MM:SSZ] [EVENT_TYPE] — description
```

**Critical events (log immediately):**
`DECISION`, `CROSS_REPO_ROUTE`, `TIER2_ASSESSMENT`, `ERROR`, `ESCALATION`, `PAUSE`, `RESUME`, `AGENT_RECOVERED`.

**Routine events (batch at phase boundaries):**
`PHASE_COMPLETE`, `AGENT_SPAWN`, `AGENT_SHUTDOWN`, `SESSION_START`, `SESSION_END`.

The CEO batches routine events into a single `Edit` call at each phase transition rather than one `Edit` per event. This reduces tool-call overhead during active phases.

---

## Session Dashboard

CEO updates the dashboard after each phase completion, cross-repo event, pause/resume, or error. Dashboard format is defined in the existing protocol layout below.

### Format

```
SESSION DASHBOARD                                              {ISO_TIMESTAMP}
════════════════════════════════════════════════════════════════════════════════

{prefix} — {task} ─────────────────────────────────────────────────────────────
  {bar}  {N}/6 {phase-name} ({status}) | {activity} | Agents: {list}
  ├── Research: {summary}
  ├── Impl: {N}/{total} batches
  └── Review: {A: PASS/FAIL, B: PASS/FAIL} | Judge: {PASS/FAIL/pending}

Cross-Repo ────────────────────────────────────────────────────────────────────
  {N} outbound ({N} confirmed) | {N} inbound | {N} pauses | {N} conflicts

════════════════════════════════════════════════════════════════════════════════
```

Progress bar characters: `█` = phase complete, `▓` = phase active, `░` = phase pending. 6 segments (phases 1–6).

CEO Decision lines use prefix `CEO Decision:` when the CEO makes a routing or escalation call that deviates from the default path. Example: `CEO Decision: Direct fix (pipeline skipped — trivial one-liner)`.

Only show fields that exist. A repo in Phase 2 has no Impl or Review line. Completed repos show `████████` and end with `└── TASK COMPLETED`.
