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
6. CEO-Assistant reports findings to CEO and logs assessment to `GOAT-CEO/logs/{affected-prefix}/cross-repo.log`.
7. If no impact: CEO notes false alarm, takes no action. CEO logs to `cross-repo.log`.
8. If impact confirmed: CEO routes information to the affected Overseer with full specifics.
   CEO logs routing event to `cross-repo.log` for both repos.

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
5. CEO-Assistant logs the exchange to `GOAT-CEO/logs/{target-prefix}/cross-repo.log`.
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
3. CEO logs PAUSE and RESUME events to `logs/{prefix}/timeline.log`.

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
7. CEO logs the conflict and resolution to `cross-repo.log` for both repos.

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
5. CEO logs the failure and respawn to `logs/{prefix}/timeline.log` and `decisions.log`.

---

### Infrastructure Errors (Repo unreachable, Tool failure)

- CEO reports to user: what failed, what was being attempted, which repos are affected.
- CEO suggests remediation (retry, check path, restart tool, manual intervention).
- CEO pauses affected repos pending user response.
- Resume normal operation once user confirms the issue is resolved.

---

## Progress Dashboard

CEO updates the dashboard after each phase completion, cross-repo event, pause/resume, or on user request.

### Session Dashboard Format

```
## Session Dashboard — {ISO_TIMESTAMP}

| Repo | Phase | Status | Active Agents | Issues | Cross-Repo Events |
|------|-------|--------|---------------|--------|-------------------|
| {prefix} | {N} — {phase-name} | running | {agent-list} | {count} | {count} |
| {prefix} | {N} — {phase-name} | paused | {agent-list} | {count} | {count} |
| {prefix} | {N} — {phase-name} | blocked | {agent-list} | {count} | {count} |
| {prefix} | complete | done | — | {count} | {count} |
```

**Status values:** `running` | `paused` | `blocked` | `complete`

**Issues:** count by severity — format as `{critical}/{major}/{minor}` (e.g., `0/1/2`)

**Cross-Repo Events:** cumulative count of OUTBOUND flags, INBOUND notifications, and REQUESTs for this repo.

### Per-Repo Detail (on request or when escalating)

```
### {prefix} — Phase {N}: {phase-name}
- Status: {running|paused|blocked|complete}
- Active agents: {list or none}
- Last event: {description} at {timestamp}
- Open issues: {list or none}
- Cross-repo items: {list or none}
```

### Cross-Repo Summary

```
### Cross-Repo Activity
- Outbound flags: {count} ({confirmed-impact} confirmed impact, {false-alarm} false alarms)
- Inbound notifications: {count}
- Info requests: {count}
- Active pauses: {list of paused repos and reason}
- Unresolved conflicts: {count}
```

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

### CEO Direct Logging

**When:** CEO writes these entries directly using the Write tool (no CEO-Assistant needed).
**Event types:**

| Event Type | Log File | Description |
|------------|----------|-------------|
| `PHASE_COMPLETE` | `timeline.log` | A repo's GOAT phase reached completion |
| `AGENT_SPAWN` | `timeline.log` | CEO spawned an agent (include name, role, phase) |
| `AGENT_SHUTDOWN` | `timeline.log` | CEO shut down an agent (include name, reason) |
| `PAUSE` | `timeline.log` | CEO paused a repo (include repo, reason) |
| `RESUME` | `timeline.log` | CEO resumed a repo (include repo, trigger) |
| `DECISION` | `decisions.log` | CEO made a decision affecting repo strategy |
| `CROSS_REPO_ROUTE` | `cross-repo.log` | CEO routed cross-repo info (include source, dest, summary) |
| `ERROR` | `timeline.log` | Error detected or escalated |

---

### CEO-Assistant Logging

**When:** CEO-Assistants write detailed analytical entries when spawned.
**Event types:**

| Event Type | Log File | Description |
|------------|----------|-------------|
| `CONTEXT_REPORT` | `timeline.log` | General repo context gathered for CEO |
| `IMPACT_ASSESSMENT` | `cross-repo.log` | Assessed whether a change impacts this repo |
| `CROSS_REPO_ANALYSIS` | `cross-repo.log` | Full analysis of cross-repo dependency or conflict |
| `DEPENDENCY_SCAN` | `timeline.log` | Scanned repo for dependencies (during Step 2.2 or post-bootstrap) |

**File targets:**

- `logs/{repo-prefix}/decisions.log` — CEO decisions affecting this specific repo
- `logs/{repo-prefix}/cross-repo.log` — All cross-repo communications routed through CEO for this repo
- `logs/{repo-prefix}/timeline.log` — Phase progression and all events for this repo
