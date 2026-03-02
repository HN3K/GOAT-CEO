# GOAT-CEO Protocols Reference
> Read by the CEO during Step 4 (Execution & Monitoring) for communication flows and error recovery.

---

## Cross-Repo Communication Flows

### OUTBOUND — Change That May Affect Another Repo

**Trigger:** Overseer determines a completed change touches a shared contract, API, schema, or interface.

**Step-by-step routing:**

1. Team member completes work and reports to its Overseer.
2. Overseer assesses: does this change touch an API, schema, config, or shared interface?
   - Overseer errs on the side of flagging — when in doubt, flag it.
   - Overseer does NOT assess actual impact — that is the CEO-Assistant's job.
3. If flagged, Overseer messages CEO with:
   - What changed (old → new, specific files/functions/endpoints)
   - Why it changed (task context)
   - Overseer's preliminary assessment: potentially breaking / likely non-breaking
4. CEO spawns or resumes a CEO-Assistant (`ceo-assistant-{affected-prefix}`) targeting the AFFECTED repo.
5. CEO-Assistant queries the affected repo's indexing/tooling to assess actual impact:
   - Searches for usages of the changed API/schema/contract
   - Identifies files, functions, or tests that reference the changed surface
   - Determines severity: breaking / non-breaking / no impact
6. CEO-Assistant reports findings to CEO.
7. CEO relays findings to the Scribe for logging in `GOAT-CEO/logs/{affected-prefix}/cross-repo.log`.
8. If no impact: CEO notes false alarm, no further action.
9. If impact confirmed: CEO routes information to the affected Overseer with full specifics.
   CEO messages the Scribe to log the routing event in `cross-repo.log` for both repos.

---

### INBOUND — Receiving Cross-Repo Information

**Trigger:** CEO sends an Overseer information about a change in a related repo.

**Phase-aware handling rules:**

- **Planning or Research phase:** Overseer instructs the active agent to incorporate the new information into the plan or research findings. Adjust scope if needed.
- **Implementation phase:**
  - If the change is non-breaking or easily absorbed: Overseer adjusts the current or next batch in-flight. No escalation needed.
  - If the change requires rework or conflicts with the current implementation batch: Overseer escalates to CEO with specifics (what conflicts, what rework is needed). CEO decides: pause and replan, or continue and address in review.
- **Review phase:** Overseer adds the cross-repo change as an additional review criterion for the active reviewers.

---

### REQUEST — Asking for Information From Another Repo

**Trigger:** Overseer needs specific information from a related repo to proceed.

**Step-by-step routing:**

1. Overseer messages CEO: "Need [specific info] from [other-repo-prefix]."
   - Include: what information is needed, why it is needed, how urgent it is.
2. CEO spawns or resumes a CEO-Assistant (`ceo-assistant-{target-prefix}`) targeting the target repo.
3. CEO-Assistant queries the target repo:
   - Uses the repo's indexing/tooling system when available.
   - Falls back to raw scanning (file structure, imports, config files) if tooling is absent.
   - Finds the requested information (API signature, schema definition, config value, etc.).
4. CEO-Assistant reports findings to CEO.
5. CEO relays findings to the Scribe for logging in `GOAT-CEO/logs/{target-prefix}/cross-repo.log`.
6. CEO relays the answer to the requesting Overseer.

---

### PAUSE/RESUME — CEO-Driven Dependency Management

**Trigger:** CEO determines one repo is ahead of a dependent repo and must wait.

**Pause semantics (Design Note 5):**

1. CEO messages the ahead Overseer: "Pause — waiting for [{other-repo}] to reach Phase {N}."
2. Upon receiving pause:
   - **Running team members finish their current work** — they complete the current task and report back to the Overseer as normal.
   - **Overseer does not request new team member spawns** — it holds at the current phase boundary.
   - **Overseer remains responsive** — it processes messages from running team members and from CEO.
3. Overseer acknowledges pause to CEO.

**Resume:**

1. When the blocking repo catches up, CEO messages the paused Overseer: "Resume — [{other-repo}] has reached Phase {N}."
2. Overseer proceeds: requests the next phase's team member spawns from CEO.
3. CEO messages the Scribe to log PAUSE and RESUME events to `logs/{prefix}/timeline.log`.

---

## Error Recovery

### Repo-Local Errors (Test failures, Review failures)

- Handled by the Overseer per standard GOAT protocol.
- Overseer coordinates re-runs, iteration loops, or rollback within the repo.
- CEO is not involved unless the Overseer explicitly escalates.
- Escalation format: Overseer messages CEO with what failed, what was tried, and what decision is needed.

---

### Cross-Repo Errors (Breaking change, Contract violation)

1. CEO detects the conflict (via OUTBOUND flow or Overseer escalation).
2. CEO pauses both affected repos using the PAUSE/RESUME protocol.
3. CEO spawns CEO-Assistants for both repos to gather full context:
   - What the change is and where it lives
   - What the consuming repo relies on and how it is broken
   - What fix options exist (change source, update consumer, negotiate interface)
4. CEO presents the conflict to the user with full context from both CEO-Assistants.
5. User decides: fix in source repo, fix in consumer repo, or replan both.
6. CEO routes the decision to the relevant Overseers and resumes affected repos.
7. CEO messages the Scribe to log the conflict and resolution to `cross-repo.log` for both repos.

---

### Overseer Failure (Crash, Context exhaustion)

**Detection:** CEO determines an Overseer is unresponsive after a reasonable wait.

**Recovery steps:**

1. CEO reads `agent-workspace/` in the failed Overseer's repo to determine:
   - Which phase was in progress (check PLAN.md, IMPLEMENTATION-MANIFEST.md, REVIEW-LOG.md)
   - Which artifacts exist (what is complete vs. in-progress)
   - Which team members may still be running (check last known spawns)
2. CEO shuts down any orphaned team members (sends `shutdown_request` to each).
3. CEO spawns a NEW Overseer for the repo using the Overseer template from `templates.md`.

**Respawn instructions to include in the new Overseer's prompt:**

```
Resume from Phase {N}.
These artifacts already exist: {LIST_OF_ARTIFACTS}.
These phases are complete: {LIST_OF_COMPLETE_PHASES}.
These team members may still be running: {LIST_OR_NONE}.
Read agent-workspace/ to re-ground yourself before requesting any new spawns.
```

4. New Overseer reads `agent-workspace/` to verify state and continues the pipeline from the checkpoint.
5. CEO messages the Scribe to log the failure and respawn to `logs/{prefix}/timeline.log` and `decisions.log`.

---

### Infrastructure Errors (Repo unreachable, Tool failure)

- CEO reports to user: what failed, what was being attempted, which repos are affected.
- CEO suggests remediation (retry, check path, restart tool, manual intervention).
- CEO pauses affected repos pending user response.
- Resume normal operation once user confirms the issue is resolved.

---

## Progress Dashboard

CEO updates and displays the dashboard after each phase completion, cross-repo event, pause/resume, or error. The dashboard is the primary output the user sees — keep it current and accurate.

**Update triggers:** phase completion, cross-repo event, pause/resume, error/escalation, user request.

**Display rule:** Only show the dashboard and CEO decisions to the user. Suppress verbose logging output (log entries are written to files silently).

### Session Dashboard Format

The dashboard uses a tree-style layout with a three-part structure per repo:
1. **Title line** — repo name + task, then thin horizontal line (`───`) extending to the right margin
2. **Progress line** — indented below: block-character progress bar, phase info, activity, agents
3. **Detail tree** — cumulative metrics (impl, review, research) as branches

Framed by a double-line (`════`) header and footer. Output as regular text.

**Mid-session example:**

```
SESSION DASHBOARD                                              {ISO_TIMESTAMP}
════════════════════════════════════════════════════════════════════════════════════

api — Fix 3 web UI bugs ───────────────────────────────────────────────────────────
  █████▓░░  5/7 Implementation (running) | Batch 2/4 | Agents: api-implementer-2
  ├── Research: 3 found (1C 2M) — resolved > clean pass
  └── Review: pending

web — Verify auth tokens ──────────────────────────────────────────────────────────
  ▓  Assessment (done) — No code changes needed.

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

**Completed session example:**

```
SESSION COMPLETE                                               {ISO_TIMESTAMP}
════════════════════════════════════════════════════════════════════════════════════

kh — Fix 3 web UI bugs ────────────────────────────────────────────────────────────
  ████████  7/7 Complete | 3 files changed
  ├── Impl: 2/2 batches
  ├── Review: A: PASS, B: PASS
  └── Research: 0 found — clean

kh — Verify mapper depths ─────────────────────────────────────────────────────────
  ▓  Assessment (done) — No code changes needed.

jvg — CSharpNormalizer ────────────────────────────────────────────────────────────
  ████████  7/7 Complete | 4 files changed | commit: 3200e25
  ├── Impl: 4/4 batches
  ├── Review: A: PASS, B: PASS
  └── Research: 5 found (1C 3M 1m) — resolved > clean pass

════════════════════════════════════════════════════════════════════════════════════
```

### Layout Rules

**Frame:** Double-line (`════`) header underline and footer. Header line has `SESSION DASHBOARD` or `SESSION COMPLETE` left-aligned, timestamp right-aligned.

**Title line:** `{prefix} — {task} ───`. Thin horizontal line (`─`) extends to a consistent right margin (~80 chars). Separates each repo visually.

**Progress bar:** Block characters for instant visual completion:
- `█` = phase complete
- `▓` = phase active
- `░` = phase pending
- 8 segments representing phases 0–7.
- **Completed repos** (whether via full pipeline or Phase 0 resolution) show a full bar: `████████`
- Assessment-only repos in progress use a single `▓`.

**Progress line:** Indented 2 spaces. Format: `{bar}  {N}/7 {phase-name} ({status}) | {activity} | Agents: {list}`.
- Status values: `running`, `paused`, `blocked`, `done`
- Activity: current batch, iteration, or step (when applicable)
- Agents: active agent names (omit segment when none)

**Detail tree:** Indented 2 spaces, using `├──` (intermediate) and `└──` (last). Only include lines that apply:
- **Impl** — `{N}/{total} batches`
- **Review** — `A: PASS/FAIL, B: PASS/FAIL` or `pending`
- **Research** — compact single-line format: `{found} found ({severity}) — resolved > clean pass`
  - Severity key: `C` = critical, `M` = major, `m` = minor
  - `>` separates iterations: text before `>` is iteration 1 result, after is iteration 2
  - In-progress: `I1 in progress...`
  - Single iteration with no issues: `0 found — clean`
- **Assessment** — Phase 0 single line: `Assessment (done) — {result}`
- **CEO Decision** — When the CEO makes a routing decision (e.g., direct fix instead of full pipeline, pipeline activation, loop exit), display it prominently on the progress line or as a detail tree entry prefixed with `CEO Decision:`. This ensures users understand why a repo took an unusual path (e.g., skipping the pipeline). Format: `CEO Decision: {action} ({rationale})`
  - Examples: `CEO Decision: Direct fix (pipeline skipped, narrow scope)`, `CEO Decision: Pipeline activated (new subsystem, 37 test cases)`, `CEO Decision: LOOP_EXIT after clean verification`
- **Files changed** — count of modified files (shown for repos past implementation)
- **Commit** — hash (shown for completed repos that committed)
- **TASK COMPLETED** — final line in the detail tree for any repo whose work is finished. Signals clearly that no further work is pending for this repo. Always use `└── TASK COMPLETED` as the last tree entry.

**Omit what doesn't apply.** A repo in Phase 2 has no Impl or Review. A Phase 0 repo shows only the assessment line. Only display what exists. When a repo is complete, always show the full progress bar (`████████`) and end with `└── TASK COMPLETED`.

**Cross-Repo section:** Only shown when related groups exist. Uses the same thin-line title. Omit for isolated-only sessions.

---

## Logging Format

### Timestamp Format

ISO 8601: `YYYY-MM-DDTHH:MM:SSZ`
Example: `2026-03-01T14:23:07Z`

### Entry Format

```
[timestamp] [EVENT_TYPE] — description
```

Example: `2026-03-01T14:23:07Z PHASE_COMPLETE — {prefix} Phase 2 (Research) complete. Artifacts: PLAN.md, RESEARCH-NOTES.md.`

---

### Scribe-Managed Logging

**All logging is handled by the Scribe agent (`ceo-scribe`).** The CEO does not write log entries directly. Instead, the CEO sends brief messages to the Scribe describing events, and the Scribe writes properly formatted entries to the correct files.

The Scribe is spawned at session start (Step 3.1) and runs for the entire session.

**Event types the Scribe handles:**

| Event Type | Log File | Triggered By |
|------------|----------|-------------|
| `SESSION_START` | `timeline.log` | CEO message at session start |
| `SESSION_END` | `timeline.log` | CEO message at session end |
| `PHASE_COMPLETE` | `timeline.log` | CEO message after Overseer reports |
| `AGENT_SPAWN` | `timeline.log` | CEO message after spawning an agent |
| `AGENT_SHUTDOWN` | `timeline.log` | CEO message after shutting down an agent |
| `PAUSE` | `timeline.log` | CEO message when pausing a repo |
| `RESUME` | `timeline.log` | CEO message when resuming a repo |
| `ERROR` | `timeline.log` | CEO message when error detected |
| `DECISION` | `decisions.log` | CEO message when making a strategic decision |
| `CROSS_REPO_ROUTE` | `cross-repo.log` | CEO message when routing info between repos |
| `IMPACT_ASSESSMENT` | `cross-repo.log` | CEO relays CEO-Assistant findings to Scribe |
| `CONTEXT_REPORT` | `timeline.log` | CEO relays CEO-Assistant findings to Scribe |

**File targets:**

- `logs/{repo-prefix}/timeline.log` — Phase progression and all events for this repo
- `logs/{repo-prefix}/decisions.log` — CEO decisions affecting this specific repo
- `logs/{repo-prefix}/cross-repo.log` — All cross-repo communications routed through CEO for this repo

**CEO-to-Scribe message examples:**

- `"kh: Spawned kh-planner for Phase 1. Task: Fix 3 web UI bugs."`
- `"jvg: Phase 2 complete. Research Iter 1: 5 issues (1C 3M 1m). All resolved in plan revision."`
- `"Decision for kh: Respawning overseer — previous one only reviewed code, did not run actual mapper."`
- `"Cross-repo: api auth change affects web. Routed to web-overseer. Severity: major."`

**CEO-Assistant reports:** When a CEO-Assistant completes a mission, the CEO relays the findings to the Scribe for logging. The CEO-Assistant itself does not write to log files.
