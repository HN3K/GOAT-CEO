# GOAT-CEO — Multi-Repo Executive Orchestration Skill

## Purpose

GOAT-CEO is a meta-orchestration skill that sits above individual GOAT pipelines.
It allows a single Claude Code session to manage work across multiple repositories
simultaneously — spawning isolated or interconnected GOAT teams per repo, routing
cross-repo information where needed, and keeping unrelated work hermetically sealed.

All repos are independent git repositories. Each repo is expected to have (or will
be bootstrapped with) the standard GOAT skill, codebase-index system, and tooling
system.

---

## Design Decisions (Resolved)

| # | Decision | Resolution |
|---|----------|------------|
| A | Agent depth | Flat team — CEO spawns ALL agents. Overseers manage, don't spawn. Overseers message CEO to request new agents. |
| B | CEO role | Informed executive — CEO-Assistant agents scout repo context via indexing/tooling. CEO makes decisions from their reports. |
| C | Cross-repo comms | Message-only through CEO. No shared channel files. CEO relays findings to Scribe for logging in GOAT-CEO repo. Tiered routing: Tier 1 (informational) relayed directly, Tier 2 (decision-required) uses CEO-Assistant assessment. |
| D | Sync strategy | Overseer-driven — Overseers track progress and report to CEO. CEO pauses dependent teams when needed, lets independent work continue. |
| E | Message filtering | Overseers act as repo team leads. Team members route through Overseer. Direct-to-CEO messaging only for critical emergencies. |
| E2 | Cross-repo tiers | Tier 1 (informational, additive, non-breaking): CEO relays directly Overseer→CEO→Overseer. Tier 2 (decision-required, breaking/uncertain): full CEO-Assistant assessment before routing. |
| F | Recovery | Respawn Overseer from artifacts. agent-workspace/ serves as checkpoint. |
| G | Final review | Dedicated cross-repo reviewer agent with access to both repos simultaneously. |
| H | Bootstrapping | Spec markdown files passed to repo. GOAT team's first task is to set up indexing/tooling, adapting to repo conventions. CEO does not implement directly. |
| I | Git structure | All repos are separate git repositories. No concurrency concerns. |
| J | Assessment-first | **Key behavior:** Overseers always orient and assess before requesting any agent spawns. For verification, investigation, diagnostic, or exploratory tasks, the Overseer handles them directly. The full pipeline is only activated when the assessment determines code changes are required. This prevents unnecessary agent spawns for tasks that don't need the full pipeline. |
| K | Repo registry | `repo-registry.json` persists repo paths, capabilities, groups, and bootstrap status across sessions. Quick Start mode reads from registry. |
| L | Hybrid logging | Critical events (decisions, cross-repo, errors) logged immediately to Scribe. Routine events (spawns, shutdowns, phases) batched via `BATCH LOG:` messages. Reduces CEO↔Scribe overhead. |
| M | CEO-Assistant scope | CEO-Assistants scoped to cross-repo impact assessment only. Single-repo questions route to Overseers via Assessment-First. |
| N | Reviewer scope | Reviewers verify the Index Updater's work — they do NOT update indexes themselves. If Index Updater missed something, verdict is FAIL. |
| O | Shared index artifact | Planner writes `index-context.md` in Phase 1. Researchers read it as base context, avoiding redundant CLI calls. |
| P | Progressive enrichment | Index Updater scans neighboring unindexed code during each pipeline run. Every run leaves the index system more complete, not just current. |

---

## Function Tree

```
GOAT-CEO
│
├── 1. STARTUP & SESSION INITIALIZATION
│   │
│   ├── 1.0 Mode Selection
│   │   ├── Check for repo-registry.json existence
│   │   ├── If exists: offer Quick Start (Q) vs Full Setup (F)
│   │   └── If not exists: go to Full Setup
│   │
│   ├── 1.Q Quick Start Flow (from registry)
│   │   ├── Read repo-registry.json
│   │   ├── Display registered repos table with status
│   │   ├── User selects by number, group name, or "all"
│   │   ├── Validate paths still exist and are git repos
│   │   ├── Re-detect capabilities (GOAT, index, tooling)
│   │   ├── Load relationship groups from registry
│   │   └── Skip to 2.1 (Task Gathering)
│   │
│   ├── 1.1 Repo Registration (Full Guided)
│   │   ├── User provides repo paths (1..N)
│   │   ├── For each repo: validate, detect capabilities
│   │   ├── Present summary table
│   │   └── Create/update repo-registry.json
│   │
│   ├── 1.1.5 Model Profile Selection
│   │   ├── Present profile options: Default / Economy / Premium / Custom
│   │   ├── Default: opus planners/researchers, sonnet implementers/reviewers
│   │   ├── Economy: sonnet planners/researchers, haiku implementers/reviewers
│   │   ├── Premium: opus for all roles
│   │   └── Record for agent spawning in Step 3
│   │
│   ├── 1.2 Prerequisite Check & Automated Bootstrap (conditional)
│   │   ├── Options: Auto-bootstrap (A) / Manual setup (B) / Skip (C)
│   │   ├── Auto-bootstrap: detect language, scaffold, set sourceGlobs, populate, validate
│   │   ├── Manual: copy spec files, Overseer runs setup
│   │   └── Mark bootstrapped: true in registry on success
│   │
│   └── 1.3 Relationship Mapping
│       ├── "Which repos need to communicate with one another?"
│       ├── "Which repos should be fully isolated?"
│       ├── User defines relationship groups:
│       │   ├── RELATED GROUP(s) — repos that share information
│       │   │   └── Example: [my-api-service, my-web-app] — "API consumer ↔ provider"
│       │   └── ISOLATED REPO(s) — repos with no cross-repo traffic
│       │       └── Example: [my-docs-site] — "standalone site, no dependencies"
│       └── CEO builds a Relationship Graph:
│           ├── Nodes = repos
│           ├── Edges = communication channels (bidirectional or directional)
│           └── No edges = isolated
│
├── 2. TASK GATHERING
│   │
│   ├── 2.1 Per-Repo Task Assignment
│   │   ├── For each registered repo:
│   │   │   ├── "What work needs to be done in [repo]?"
│   │   │   └── User provides task description(s)
│   │   └── CEO records: { repo, tasks[], relationship_group }
│   │
│   ├── 2.2 Cross-Repo Dependency Detection (Related Groups Only)
│   │   ├── For repos WITH indexing/tooling already present:
│   │   │   ├── CEO spawns CEO-Assistant(s) to scout each related repo's context
│   │   │   └── CEO-Assistants use the repo's indexing/tooling system to gather:
│   │   │       ├── API surface (endpoints, contracts, schemas)
│   │   │       ├── Shared interfaces or data models
│   │   │       ├── External dependencies and configuration
│   │   │       └── Areas affected by the user's requested tasks
│   │   ├── For repos NEEDING BOOTSTRAP (no indexing/tooling yet):
│   │   │   ├── CEO-Assistants fall back to raw code scanning (file structure,
│   │   │   │   package manifests, import statements, config files)
│   │   │   ├── Dependency detection is best-effort until bootstrap completes
│   │   │   └── CEO notifies user: "Full dependency detection for [repo] will
│   │   │       be available after bootstrap. Detected so far: [list]"
│   │   ├── CEO-Assistants report findings to CEO
│   │   ├── CEO identifies potential cross-repo impacts from reports
│   │   ├── Presents detected dependencies to user for confirmation
│   │   └── User can add/remove/correct dependencies
│   │
│   └── 2.3 Execution Plan Summary
│       ├── Display: repos, tasks, groups, detected dependencies
│       ├── Display: which repos will run GOAT pipelines in parallel
│       ├── Display: which repos have cross-repo communication via CEO
│       └── "Does this look correct? Ready to begin?"
│
├── 3. TEAM SPAWNING & WORKSPACE SETUP
│   │
│   ├── 3.1 Single Team Creation
│   │   ├── CEO creates ONE team: "goat-ceo"
│   │   ├── ALL agents across ALL repos are members of this team
│   │   └── Agent naming convention: [repo-prefix]-[role]
│   │       ├── Examples: api-overseer, api-planner, api-researcher-codebase
│   │       ├── Examples: web-overseer, web-planner, web-implementer-1
│   │       └── CEO-level agents: ceo-assistant-api, ceo-assistant-web, cross-reviewer
│   │
│   ├── 3.2 Per-Repo Overseer Spawning
│   │   ├── For each repo with tasks:
│   │   │   ├── CEO spawns: [prefix]-overseer
│   │   │   │   ├── Passes: repo path (Overseer's working directory)
│   │   │   │   ├── Passes: repo-specific CLAUDE.md context
│   │   │   │   ├── Passes: repo-specific tasks
│   │   │   │   ├── Passes: repo-specific project rules
│   │   │   │   ├── Passes: relationship status (isolated or related + group info)
│   │   │   │   └── Passes: list of what related repos are working on (if applicable)
│   │   │   │
│   │   │   ├── Overseer's role:
│   │   │   │   ├── Manages the 6-phase GOAT pipeline for its repo
│   │   │   │   ├── Coordinates team members within its repo
│   │   │   │   ├── Tracks progress and filters messages to CEO
│   │   │   │   └── Does NOT spawn agents — requests spawns from CEO
│   │   │   │
│   │   │   └── Initialize agent-workspace/ in the repo
│   │   │
│   │   └── If repo needs bootstrapping (from 1.2.1):
│   │       ├── Overseer's first task: set up indexing/tooling from spec files
│   │       ├── User-requested tasks queued until bootstrap completes
│   │       └── After bootstrap completes:
│   │           ├── CEO spawns CEO-Assistant to re-run dependency detection
│   │           │   with the now-available indexing/tooling system
│   │           ├── CEO-Assistant reports full dependency findings to CEO
│   │           ├── If NEW dependencies discovered (missed during best-effort scan):
│   │           │   ├── CEO notifies user of newly detected dependencies
│   │           │   └── CEO updates cross-repo communication accordingly
│   │           └── Overseer then proceeds to user-requested tasks
│   │
│   ├── 3.3 Agent Spawn Protocol (CEO-Controlled)
│   │   ├── When Overseer needs an agent (e.g., planner, researcher):
│   │   │   ├── Overseer messages CEO: "Requesting [prefix]-planner for Phase 1"
│   │   │   │   └── Includes: role, repo path, context to pass, phase/task details
│   │   │   ├── CEO spawns the agent with:
│   │   │   │   ├── team_name: "goat-ceo"
│   │   │   │   ├── name: "[prefix]-[role]"
│   │   │   │   ├── Working directory: the repo path
│   │   │   │   ├── Restriction: agent works ONLY within its assigned repo
│   │   │   │   └── run_in_background: true
│   │   │   └── CEO confirms spawn to Overseer
│   │   │
│   │   └── Overseer manages the team member's lifecycle:
│   │       ├── Receives messages from team members
│   │       ├── Verifies work by reading agent-workspace/ artifacts
│   │       ├── Requests shutdown via CEO when team member's work is complete
│   │       └── Requests next team member spawn for the next phase
│   │
│   ├── 3.4 CEO-Assistant Spawning & Logging
│   │   ├── CEO spawns CEO-Assistants as needed: ceo-assistant-[prefix]
│   │   ├── Each CEO-Assistant:
│   │   │   ├── Has access to ONE specific repo
│   │   │   ├── Uses that repo's indexing/tooling system for context
│   │   │   ├── Reports findings to CEO for decision-making
│   │   │   └── Does not write to logs — CEO relays findings to Scribe for logging
│   │   │
│   │   ├── Log files in GOAT-CEO/logs/[repo-prefix]/:
│   │   │   ├── decisions.log — CEO decisions affecting this repo
│   │   │   ├── cross-repo.log — cross-repo communications routed through CEO
│   │   │   └── timeline.log — phase progression and key events
│   │   │
│   │   ├── Logging responsibility:
│   │   │   ├── CEO sends brief event messages to the Scribe for logging
│   │   │   ├── CEO-Assistants report findings to CEO; CEO relays key facts to Scribe
│   │   │   ├── The Scribe writes all formatted log entries (see protocols.md, Scribe-Managed Logging)
│   │   │   └── This keeps logging off the CEO's terminal and ensures consistent formatting
│   │   │
│   │   └── CEO-Assistants are spawned on-demand, not permanently running
│   │
│   └── 3.5 Isolation Enforcement (Isolated Repos)
│       ├── Isolated repo agents:
│       │   ├── Are given NO information about other repos' tasks or context
│       │   ├── Their Overseer does not participate in cross-repo communication
│       │   ├── Overseer only messages CEO for: spawn requests, progress, errors
│       │   └── Operate as if they are the only repo in the session
│       └── CEO only interacts with isolated repos for:
│           ├── Agent spawn requests from Overseer
│           ├── Progress reporting to user
│           └── Error escalation
│
├── 4. EXECUTION & MONITORING
│   │
│   ├── 4.1 Parallel Execution
│   │   ├── ALL repo GOAT pipelines start simultaneously
│   │   ├── Each Overseer independently manages its 6-phase pipeline
│   │   ├── Isolated repos run fully independently
│   │   └── Related repos run independently with Overseer-driven reporting
│   │
│   ├── 4.2 Cross-Repo Communication Flow (Related Groups Only)
│   │   │
│   │   ├── OUTBOUND (repo makes a change that may affect others):
│   │   │   ├── Team member completes work that touches a shared contract/API/schema
│   │   │   ├── Team member reports to its Overseer
│   │   │   ├── Overseer assesses: "Could this affect a related repo?"
│   │   │   │   ├── Overseer's knowledge of related repos is HIGH-LEVEL ONLY
│   │   │   │   │   (task summaries provided at spawn time)
│   │   │   │   ├── Overseer errs on the side of FLAGGING — if a change touches
│   │   │   │   │   any API, schema, config, or shared interface, flag it
│   │   │   │   └── Overseer does NOT assess actual impact — that's the
│   │   │   │       CEO-Assistant's job
│   │   │   ├── If FLAGGED: Overseer messages CEO with change details
│   │   │   │   ├── What changed (old → new)
│   │   │   │   ├── Why it changed
│   │   │   │   └── Overseer's assessment: potentially breaking / non-breaking
│   │   │   ├── CEO determines routing tier:
│   │   │   │   ├── Tier 1 (informational): relay directly to affected Overseer
│   │   │   │   └── Tier 2 (decision-required): spawn CEO-Assistant for assessment
│   │   │   ├── CEO spawns/resumes a CEO-Assistant to assess ACTUAL impact
│   │   │   │   ├── CEO-Assistant uses the AFFECTED repo's indexing/tooling
│   │   │   │   │   to determine if the change truly impacts that repo
│   │   │   │   ├── If impact confirmed: CEO-Assistant reports specifics to CEO
│   │   │   │   └── If no impact: CEO-Assistant reports false alarm, CEO takes no action
│   │   │   ├── CEO relays assessment to Scribe for logging in GOAT-CEO/logs/
│   │   │   └── If impact confirmed: CEO routes the information to affected Overseer
│   │   │
│   │   ├── INBOUND (repo receives cross-repo information):
│   │   │   ├── Overseer receives message from CEO about a change in another repo
│   │   │   ├── Overseer assesses impact on current pipeline phase
│   │   │   ├── If currently in PLANNING/RESEARCH: incorporate into plan
│   │   │   ├── If currently in IMPLEMENTATION:
│   │   │   │   ├── If change is non-breaking or easily absorbed: adjust in-flight
│   │   │   │   └── If change requires rework or conflicts with current batch:
│   │   │   │       ├── Overseer escalates to CEO with specifics
│   │   │   │       └── CEO decides: pause repo and replan, or continue and
│   │   │   │           address in review phase
│   │   │   └── If currently in REVIEW: add as review criterion
│   │   │
│   │   ├── REQUEST (repo needs info FROM another repo):
│   │   │   ├── Overseer messages CEO: "Need [specific info] from [other repo]"
│   │   │   ├── CEO spawns/resumes CEO-Assistant for the target repo
│   │   │   ├── CEO-Assistant queries target repo's indexes/code
│   │   │   ├── CEO-Assistant reports findings to CEO
│   │   │   ├── CEO relays answer to requesting Overseer
│   │   │   └── CEO relays exchange to Scribe for logging in GOAT-CEO/logs/
│   │   │
│   │   └── PAUSE/RESUME (CEO-driven dependency management):
│   │       ├── Overseers report phase completions to CEO
│   │       ├── CEO tracks relative progress across related repos
│   │       ├── If work is DEPENDENT and one repo is ahead:
│   │       │   ├── CEO messages the ahead Overseer: "Pause — waiting for [repo]"
│   │       │   ├── Overseer holds, no new agent spawn requests
│   │       │   └── CEO resumes when the other repo catches up
│   │       └── If work is INDEPENDENT: both repos proceed without waiting
│   │
│   ├── 4.3 Message Routing Hierarchy
│   │   │
│   │   ├── NORMAL FLOW (99% of messages):
│   │   │   └── Team member → Overseer → (Overseer handles locally)
│   │   │
│   │   ├── ESCALATION FLOW (Overseer can't handle alone):
│   │   │   └── Team member → Overseer → CEO → (CEO decides + routes)
│   │   │
│   │   ├── EMERGENCY FLOW (critical failure, pipeline blocked):
│   │   │   └── Team member → CEO directly (bypasses Overseer)
│   │   │
│   │   └── CROSS-REPO FLOW:
│   │       └── Overseer A → CEO → CEO-Assistant → CEO → Overseer B
│   │
│   ├── 4.4 Progress Dashboard
│   │   ├── CEO maintains a live view of all repos:
│   │   │   ├── [Repo] → Phase [N] → Status [running/paused/blocked/complete]
│   │   │   ├── [Repo] → Active agents: [prefix-role, ...]
│   │   │   ├── [Repo] → Issues: [count by severity]
│   │   │   └── [Repo] → Cross-repo events: [count]
│   │   ├── User can ask CEO for status at any time
│   │   └── CEO proactively reports:
│   │       ├── Phase completions
│   │       ├── Cross-repo impacts detected
│   │       ├── Pauses/resumes due to dependencies
│   │       └── Errors requiring user input
│   │
│   └── 4.5 Error Handling & Recovery
│       │
│       ├── Repo-local errors (test failures, review failures):
│       │   └── Handled by Overseer per standard GOAT protocol
│       │
│       ├── Cross-repo errors (breaking change, contract violation):
│       │   ├── CEO pauses affected repos
│       │   ├── CEO-Assistant gathers context from both repos
│       │   ├── CEO presents conflict to user with full context
│       │   └── User decides: fix in source repo, fix in consumer, or replan
│       │
│       ├── Overseer failure (crash, context exhaustion):
│       │   ├── CEO detects Overseer is unresponsive
│       │   ├── CEO reads agent-workspace/ in the repo to determine:
│       │   │   ├── Which phase was in progress
│       │   │   ├── Which artifacts exist (PLAN.md, MANIFEST, etc.)
│       │   │   └── Which team members may still be running
│       │   ├── CEO shuts down any orphaned team members
│       │   ├── CEO spawns a NEW Overseer with instructions:
│       │   │   ├── "Resume from Phase [N]"
│       │   │   ├── "These artifacts already exist: [list]"
│       │   │   └── "These phases are complete: [list]"
│       │   └── New Overseer continues the pipeline from the checkpoint
│       │
│       └── Infrastructure errors (repo unreachable, tool failure):
│           └── CEO reports to user, suggests remediation
│
├── 5. FINALIZATION
│   │
│   ├── 5.1 Per-Repo Completion
│   │   ├── Each GOAT pipeline reaches Phase 6 independently
│   │   ├── Overseer reports final status to CEO
│   │   └── CEO marks repo as complete
│   │
│   ├── 5.2 Cross-Repo Verification (Related Groups Only)
│   │   ├── After ALL repos in a related group complete:
│   │   │   ├── CEO spawns a DEDICATED CROSS-REPO REVIEWER
│   │   │   │   ├── Name: cross-reviewer-[group-name]
│   │   │   │   ├── Has access to ALL repos in the related group
│   │   │   │   ├── Uses each repo's indexing/tooling to load context
│   │   │   │   └── Responsibilities:
│   │   │   │       ├── Verify API contracts align across repos
│   │   │   │       ├── Verify shared schemas/models are consistent
│   │   │   │       ├── Verify configuration assumptions match
│   │   │   │       ├── Check that changes in one repo don't break the other
│   │   │   │       └── Review GOAT-CEO/logs/ for unresolved cross-repo items
│   │   │   │
│   │   │   ├── Cross-repo reviewer produces a verification report:
│   │   │   │   ├── ALIGNED — contracts match, no issues
│   │   │   │   ├── MISMATCH — specific discrepancies listed
│   │   │   │   └── UNTESTED — areas that couldn't be verified
│   │   │   │
│   │   │   └── CEO reviews the report:
│   │   │       ├── ALIGNED: proceed to summary
│   │   │       ├── MISMATCH: escalate to user with specifics
│   │   │       └── UNTESTED: flag for user awareness
│   │   │
│   │   └── If discrepancies found:
│   │       ├── CEO can spawn targeted fix agents in affected repos
│   │       └── Or escalate to user for manual resolution
│   │
│   ├── 5.3 Session Summary
│   │   ├── Per repo:
│   │   │   ├── Tasks completed
│   │   │   ├── Research iterations
│   │   │   ├── Implementation batches
│   │   │   ├── Review verdicts
│   │   │   └── Files modified
│   │   ├── Cross-repo:
│   │   │   ├── Changes communicated between repos
│   │   │   ├── Dependencies managed (pauses/resumes)
│   │   │   ├── Conflicts resolved
│   │   │   └── Cross-repo verification result
│   │   └── Overall session metrics
│   │
│   └── 5.4 Cleanup
│       ├── Shut down all team members (Overseers, CEO-Assistants, repo agents, reviewer)
│       ├── Delete team: "goat-ceo"
│       ├── Preserve agent-workspace/ in each repo (per-repo artifacts)
│       └── Preserve GOAT-CEO/logs/ (cross-repo audit trail)
│
└── 6. AGENT HIERARCHY & ROLES
    │
    ├── GOAT-CEO (the user's Claude Code session)
    │   ├── Role: Executive orchestrator and sole spawn authority
    │   ├── Spawns: ALL agents across all repos (one flat team)
    │   ├── Manages: cross-repo communication, dependency pausing, user interaction
    │   ├── Informed by: CEO-Assistants that scout repo context via indexing/tooling
    │   └── Does NOT: touch code, implement changes, or work within any single repo
    │
    ├── CEO-Scribe (one per session, persistent)
    │   ├── Role: Dedicated session logger — receives events from CEO, writes formatted log entries
    │   ├── Model: Haiku (lightweight — formatting and writing only, no analysis)
    │   ├── Spawned: at session start (Step 3.1), before any other agents
    │   ├── Writes to: GOAT-CEO/logs/[repo-prefix]/ (all log files)
    │   ├── Keeps: logging off the CEO's terminal — CEO sends brief messages, Scribe writes entries
    │   └── Does NOT: make decisions, contact Overseers, or modify anything outside logs/
    │
    ├── CEO-Assistant (one per repo, spawned on-demand)
    │   ├── Role: Cross-repo impact assessment specialist
    │   ├── Access: ONE specific repo's indexing/tooling system
    │   ├── Reports: findings to CEO (API surfaces, contracts, impact assessments)
    │   ├── Scoped to cross-repo concerns only — single-repo questions route to Overseers
    │   ├── Does NOT: write to log files — CEO relays findings to Scribe for logging
    │   └── Does NOT: make decisions, communicate with Overseers, or modify code
    │
    ├── Repo Overseer (one per repo, long-running)
    │   ├── Role: Repo team lead — manages the 6-phase GOAT pipeline
    │   ├── FIRST: Independently assess the task before requesting any spawns
    │   │   ├── Read code, configs, tests, logs, and existing artifacts
    │   │   ├── Run tests, query APIs, check system state
    │   │   └── If task is verification/investigation/diagnostic → complete directly,
    │   │       report findings, end. Do NOT activate the pipeline.
    │   ├── Coordinates: all team members within its repo (only when code changes needed)
    │   ├── Filters: messages — handles most locally, escalates to CEO when needed
    │   ├── Requests: agent spawns and shutdowns from CEO
    │   ├── Reports: phase completions, cross-repo-relevant changes, errors
    │   └── Does NOT: spawn agents, access other repos, or make cross-repo decisions
    │
    ├── Repo Team Members (spawned per repo, per phase, by CEO on Overseer request)
    │   ├── [prefix]-planner — creates plan and manifest
    │   ├── [prefix]-researcher-codebase — validates plan against code
    │   ├── [prefix]-researcher-technical — validates plan against best practices
    │   ├── [prefix]-implementer-[N] — executes batched implementation
    │   ├── [prefix]-index-updater — synchronizes codebase indexes
    │   └── [prefix]-reviewer-a, [prefix]-reviewer-b — independent verification
    │   │
    │   ├── All repo team members:
    │   │   ├── Work ONLY within their assigned repo
    │   │   ├── Message their Overseer (not CEO) for routine communication
    │   │   ├── Can message CEO directly ONLY for critical emergencies
    │   │   └── Follow standard GOAT role scripts from the repo's .claude/commands/
    │   │
    │   └── Naming examples for 2 repos (api = my-api-service, web = my-web-app):
    │       ├── api-overseer, api-planner, api-researcher-codebase, api-implementer-1
    │       └── web-overseer, web-planner, web-researcher-technical, web-reviewer-a
    │
    └── Cross-Repo Reviewer (spawned once at finalization, for related groups)
        ├── Role: Verifies cross-repo contract alignment after all repos complete
        ├── Access: ALL repos in a related group (multi-repo access)
        ├── Uses: each repo's indexing/tooling system
        ├── Produces: verification report (ALIGNED / MISMATCH / UNTESTED)
        └── Spawned only once, at the end, after per-repo reviews pass
```

---

## Implementation Notes & Known Tradeoffs

### Note 1: Overseer Longevity

The Overseer no longer spawns agents, but it still needs to survive across all 6 phases.
Each phase involves: requesting a spawn, waiting for the team member to finish, reading
artifacts, deciding the next phase, and requesting the next spawn. This can amount to
dozens of turns for a single background agent, and context exhaustion mid-pipeline is
likely for complex tasks.

**Mitigation**: The artifact-checkpoint recovery mechanism (section 4.5) makes this
recoverable rather than catastrophic. When an Overseer is respawned, it reads
`agent-workspace/` to determine completed phases and resumes from the last checkpoint.
This is an expected occurrence, not an error condition.

### Note 2: Team Member Shutdown Flow

The shutdown sequence for team members is explicitly:

1. Team member finishes work and messages its Overseer
2. Overseer verifies work by reading `agent-workspace/` artifacts
3. Overseer messages CEO: "[prefix]-[role] has completed, requesting shutdown"
4. CEO sends `shutdown_request` to the team member
5. Team member responds with `shutdown_response` (approve) and terminates

The CEO is always the one who sends `shutdown_request` because the CEO is the team
leader and sole spawn authority. Overseers request shutdowns, they do not issue them.

### Note 3: Bootstrap Is a Priority Pipeline

When a repo is missing the indexing/tooling/GOAT systems (section 1.2), the bootstrap
process can run in two modes: auto-bootstrap (CEO detects language, scaffolds, and populates
indexes automatically) or Overseer-driven (Overseer requests team members to read spec files,
set up the systems, and adapt them to the repo's conventions). This means:

- A bootstrap repo will take significantly longer before user-requested tasks begin
- The bootstrap pipeline is the Overseer's first priority; user tasks are queued behind it
- The bootstrap pipeline follows the same phase structure as any other GOAT task
- Auto-bootstrap is faster for standard project layouts; Overseer-driven is more flexible

This is by design — the indexing/tooling systems are prerequisites for the quality
guarantees that the rest of the pipeline depends on.

### Note 4: Cross-Repo Reviewer Multi-Repo Access

The cross-repo reviewer (section 5.2) needs to access multiple repos simultaneously, but
agents operate from a single working directory. To handle this:

- The cross-repo reviewer's prompt must include the **absolute paths** to all repos in the
  related group
- The reviewer uses absolute paths (not relative) when reading files or running
  indexing/tooling commands in each repo
- The reviewer's working directory can be set to the GOAT-CEO repo itself, since it is
  neutral to all repos

### Note 5: Pause Semantics

When the CEO instructs an Overseer to pause (section 4.2, PAUSE/RESUME), the behavior is:

- **Team members already running continue** — they finish their current work and report
  back to the Overseer as normal
- **The Overseer does not request new team member spawns** — it holds at the current phase
  boundary and does not advance to the next phase
- **The Overseer remains responsive** — it still processes incoming messages from its
  running team members and from the CEO
- **Resume**: when the CEO sends a resume message, the Overseer proceeds with the next
  phase and requests the necessary team member spawns

Pausing means "don't advance phases," not "freeze all running work."

### Note 6: Repo Registry Persistence

`repo-registry.json` in the GOAT-CEO repo root persists repo information across sessions.
It stores: repo paths, capabilities (GOAT, index, tooling), bootstrap status, group membership,
and last session timestamp. Quick Start mode reads from the registry to skip the full
registration flow for returning users. The registry is updated at the end of each session.

### Note 7: Hybrid Logging Strategy

To reduce CEO↔Scribe message overhead, events are classified as critical (logged immediately)
or routine (batched). Critical events include CEO decisions, cross-repo routing, errors, and
pauses. Routine events include agent spawns/shutdowns, phase completions, and session lifecycle.
The CEO sends batched events with a `BATCH LOG:` prefix, and the Scribe processes each line
as a separate entry. This typically reduces Scribe messages by 40-60% while maintaining
comprehensive audit trails.

---

## GOAT-CEO Repo Structure

```
GOAT-CEO/
├── GOAT-CEO-DESIGN.md          ← this document
├── repo-registry.json          ← persists repo paths, capabilities, groups across sessions
├── .claude/
│   ├── agents/                 ← custom agent type definitions
│   └── commands/
│       ├── goat-ceo/           ← CEO orchestration skill
│       │   ├── protocols.md    ← communication flows and error recovery
│       │   └── templates.md    ← agent spawn prompt templates
│       └── goat-team/          ← GOAT pipeline skill files
├── logs/                       ← created per session, maintained by Scribe
│   ├── [repo-prefix]/
│   │   ├── decisions.log       ← CEO decisions affecting this repo
│   │   ├── cross-repo.log     ← cross-repo communications
│   │   └── timeline.log       ← phase progression and key events
│   └── session-summary.md     ← final summary after all work completes
└── specs/                      ← reference specs for bootstrapping new repos
    ├── indexing-system.md      ← how the codebase-index system works
    ├── tooling-system.md       ← how codebase-index-tools works
    └── goat-system.md          ← how the GOAT skill/agents/commands work
```
