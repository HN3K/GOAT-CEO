# GOAT-CEO

A multi-repo orchestration harness for Claude Code. One Claude Code session acts as a
"CEO" that drives structured, gated agent pipelines across several repositories in
parallel and coordinates changes that cross repo boundaries. It runs **interactively by
default** — you confirm the plan and the CEO yields to steer at phase boundaries — with an
**opt-in unattended mode** that keeps working through context compaction without losing state.

It is **not** an application or a daemon. It is a set of Claude Code skills (slash
commands), custom subagent definitions, and `settings.json` hooks that turn a single
Claude Code session into a supervised, rule-enforced orchestrator built entirely on
native Claude Code primitives.

> **Status: experimental.** Requires Claude Code with the agent-teams feature
> (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). The hooks invoke `python` on PATH via
> `$CLAUDE_PROJECT_DIR` — adjust the interpreter for your OS (see [Setup](#setup)).
> MIT licensed.

---

## What it does

- **Drives N repos from one session.** Each repo gets its own "Overseer" subagent running a
  6-phase pipeline (plan → research → implement → index → review → finalize). Repos run in
  parallel; the human watches one terminal.
- **Routes cross-repo changes.** Repos declared as a related group flag contract/schema/API
  changes to the CEO, which classifies them and assesses impact before any dependent repo
  acts. Repos declared isolated receive nothing about each other.
- **Enforces gates with hooks, not vibes.** Phase transitions, single-committer discipline,
  test gates, review gates, and stop signals are enforced by `settings.json` hooks that run
  regardless of what the model "decides." A hook can block a tool call (`exit 2`) even under
  `--dangerously-skip-permissions`.
- **Two modes: collaborative by default, unattended on opt-in.** By default the CEO yields to
  the operator at phase boundaries — the highest-quality mode. When you explicitly engage
  unattended mode, a self-healing `PreCompact` hook writes a machine-readable resume anchor
  (git HEADs, phase gates, mission, task snapshot) to disk before every compaction and a
  `SessionStart` hook re-injects it afterward, so the run keeps working *through* compaction
  without a human. See [Operating modes](#operating-modes).
- **Is frugal by default.** Before spawning a pipeline, the Overseer reads the code and
  assesses whether the task needs a pipeline at all. Investigation/verification tasks and
  one-line fixes are resolved directly — no 8-agent pipeline for a typo.

---

## How it works

### Roles

| Role | Claude Code subagent type | Count | Responsibility |
|---|---|---|---|
| **CEO** | the main session | 1 | Sole integrator. Owns the mission, the rules, the phase gates, and is the **single committer** (all `git` writes go through it). Spawns Overseers and cross-repo agents. |
| **Overseer** | `team-overseer` | 1 per repo | Runs one repo's 6-phase pipeline. Spawns its own pipeline agents. Reports phase completions and cross-repo flags to the CEO. |
| **Architect / Planner** | `team-architect` | per phase | Writes the plan (Phase 1); acts as the review judge (Phase 5). |
| **Researcher** | `team-researcher` | 2 parallel | Codebase + technical research; iterate until a 5-condition convergence gate passes. |
| **Implementer** | `team-implementer` | N batches | Execute batched edits, optionally in isolated git worktrees. Cannot commit — they report a branch + file list. |
| **Verifier** | `team-verifier` | 2 + per-branch | Independent dual review; per-worktree diff verification. |
| **CEO-Assistant** | `team-ceo-assistant` | on demand | Read-only cross-repo impact scout (spawned in plan mode). |
| **Cross-Repo Reviewer** | `team-cross-reviewer` | per group | Verifies API/schema/config alignment across a related group after all members finish. |

**Single authority, flat integration.** Overseers may spawn their own pipeline agents
(native deep spawn), but the CEO is the only agent that commits. Implementers are denied
commit/push by permission rules and hand back worktree branches for the CEO to merge in a
fixed order, running the test suite between merges.

### The pipeline (per repo)

| Phase | What happens | Gate to advance |
|:--:|---|---|
| **0** | **Assessment.** Overseer reads code/tests and decides if a pipeline is warranted. Non-code tasks end here. | — |
| **1** | **Plan.** Architect writes `PLAN.md` (goal, acceptance criteria as a fenced JSON block, task breakdown). | `PLAN.GATE` (CEO writes after plan approval) |
| **2** | **Research.** Two researchers annotate the plan; architect revises; loop exits on a 5-condition AND-gate, emitting `IMPLEMENTATION-MANIFEST.md`. | `RESEARCH.GATE` |
| **3** | **Implement.** Implementers execute batches (parallel via worktrees when file sets are disjoint/uncertain). CEO merges branches + runs the suite. | `IMPLEMENT.GATE` |
| **4** | **Index.** One pass on merged main updates/repairs the Codebase-Index. | `INDEX.GATE` (0 stale + 0 missing) |
| **5** | **Review.** Two independent, fresh-context reviewers (correctness + test-quality with a reward-hack audit) → completeness critic → a bias-mitigated judge emits binding PASS/FAIL JSON. | `REVIEW.GATE` (judge PASS; capped at 2 fix iterations then escalates) |
| **6** | **Finalize.** CEO re-runs the broad suite against a frozen baseline, then makes one pathspec-scoped commit. | — |

Phase gates are **sentinel files** (`agent-workspace/<PHASE>.GATE`). A `PreToolUse` hook
blocks a role from writing until its required gate exists; a `Stop` hook blocks the CEO's
turn from ending while any expected gate is missing.

---

## How it interacts with Claude Code

GOAT-CEO is deliberately built on native primitives — there is no external state store,
queue, or daemon. The orchestration *is* the Claude Code feature surface:

| Claude Code primitive | How GOAT-CEO uses it |
|---|---|
| **Skills / slash commands** | `/goat-ceo` (multi-repo) and `/goat-team:*` (single-repo pipeline variants) are the entry points; supporting doctrine files are read on demand. |
| **Agent teams** (`TeamCreate`, `Agent`, `SendMessage`, `TeammateIdle`) | The team is the live pipeline substrate. Overseers are background teammates; the CEO is the fixed lead. `SendMessage` delivers redirects at turn boundaries. |
| **Subagents with isolated context** | Verbose work (research, review, large reads) runs in subagents with their **own** context windows; only short structured results return to the CEO. This is the primary defense against CEO context exhaustion. |
| **Task list** (`TaskCreate`, `TaskList`, `addBlockedBy`) | One task per phase per repo, chained with `addBlockedBy` to enforce phase order. The shared task list doubles as the cross-repo dashboard. |
| **Hooks** (`settings.json`) | The enforcement layer — see [below](#the-hook-enforcement-layer). Hooks block independently of permission mode. |
| **`permissions.deny`** | Hard, unconditional rules (`git add -A/.`, `DROP DATABASE`, `.env` writes, registry writes). Enforced even under `--dangerously-skip-permissions`. |
| **Permission modes** | Read-only scouts (CEO-Assistant, reviewers) run in `plan` mode; unattended runs use `dontAsk` + a tight allow-list or sandboxed bypass. |
| **Worktree isolation** | Parallel implementers each get a fresh git worktree (`isolation: worktree`) so concurrent edits never collide; the CEO merges branches afterward. |
| **Workflow tool** (optional) | When available, the per-repo pipeline can be authored as a JavaScript Workflow script so the plan lives in the script, not the CEO's context. A prose state-machine fallback runs the same 6 phases without it. |
| **`additionalContext` injection** | The `SessionStart` hook injects the resume anchor into a fresh/compacted session. |
| **Plan-mode approval** | The Phase 1→2 gate is the native teammate plan-approval primitive — the architect cannot write until the CEO approves its plan. |

### The hook enforcement layer

All hooks are **fail-open**: any exception exits 0, so a hook bug never blocks legitimate
work. They are wired in `.claude/settings.json`.

| Event | Hook | Effect |
|---|---|---|
| `PreToolUse` | `check_phase_gate.py` | Blocks a role's Write/Edit/Bash until its required `*.GATE` exists. |
| `PreToolUse` | `guard_git_commit.py` | Surfaces every commit/push for review (single-committer discipline). |
| `PreToolUse` | `guard_destructive_db.py` | Requires an approval token before destructive DB operations. |
| `PreToolUse` | `check_stop_file.py` | If `agent-workspace/STOP` exists, halts the agent at its next tool boundary (faster than a turn boundary — the kill switch for a runaway agent). |
| `SubagentStop` / `TeammateIdle` | `check_artifacts.py` | Blocks a subagent/Overseer from finishing until its declared deliverable exists. |
| `PostToolBatch` | `check_turn_budget.py` | Forces a yield if a subagent runs past a time budget. |
| `TaskCompleted` | `check_test_gate.py`, `check_review_gate.py`, `check_toolcall_audit.py` | Blocks task closure unless the suite passes **and actually ran tests** (a zero-test "hollow pass" is rejected) / judge verdict is PASS / reviewer actually read files. |
| `Stop` | `check_pipeline_complete.py` | Blocks the CEO's turn from ending while any expected `*.GATE` is missing or an escalation is pending; in opt-in unattended mode it also holds the turn so the run continues. |
| `PreCompact` | `check_precompact.py` | Self-heals the resume anchor before compaction (never blocks). |
| `SessionStart` | `inject_handoff_context.py` | Re-injects the resume anchor on startup/resume/compact. |

---

## Operating modes

GOAT-CEO runs in one of two modes, chosen at the start of a session. **Collaborative is the
default**; unattended is a deliberate opt-in.

- **Collaborative (default).** An operator is present. The CEO runs the interactive intake,
  presents the plan for confirmation, and **yields at phase boundaries** so the operator can
  steer. This is the highest-quality mode and the right choice for almost every session — none
  of the never-stop machinery below applies.
- **Unattended (opt-in).** For a genuinely unattended/overnight run with no operator present.
  Only when you explicitly engage it does the CEO turn on the keep-going survival layer that
  lets it work *through* Claude Code's auto-compaction:
  1. **Before compaction** — `check_precompact.py` regenerates a machine-readable
     `agent-workspace/RESUME-STATE.md` from ground truth (per-repo `git` HEAD/branch, the
     `*.GATE` sentinels present, the mission headline, dated diagnosis-doc pointers), preserves
     the CEO-authored body (phase, task snapshot, next action), and **allows** the compaction.
     It never blocks — blocking an auto-compaction at full context would deadlock the run.
  2. **After compaction** — `inject_handoff_context.py` (synchronous, so delivery is
     guaranteed) re-injects that anchor **facts-first**, with a "verify against git + sentinels
     before trusting" banner. The resume banner only tells the CEO to "keep working through
     compaction" when unattended mode is engaged.
  3. **Doctrine** — in unattended mode only, low context is *not* a stop condition; the
     legitimate stops are an operator `STOP` file, a hard escalation, or mission completion.

The resume anchor is **machine-derived facts, not decaying prose**, and every durable artifact
has a size budget so it is never truncated at the injection boundary. An optional outer loop
(`scripts/autonomous-loop.ps1`) relaunches the session on process death (crash, reboot) and the
`SessionStart` hook re-grounds it — so an unattended run survives not just compaction but the
process itself dying. All of this behavior lives in one opt-in doctrine file
(`.claude/commands/goat-ceo/unattended-mode.md`); in collaborative mode it is dormant.

---

## The Codebase-Index

Agents get their bearings from a hand-maintained `Codebase-Index/` (per-directory
`INDEX.md` files describing structure, patterns, and dependencies) queried through a local
`codebase-index-tools` CLI — no embeddings, no vector DB, no external service. It is
deterministic and human-readable.

```
search --query "auth"          # which indexes cover authentication
inject  --task "fix login bug"  # load all relevant context for a task
check   --all                   # audit for stale / missing indexes (gates Phase 4)
scaffold --source src/new-mod   # stub an INDEX.md for unmapped code
```

If a target repo has no index/tooling, GOAT-CEO can bootstrap it (auto-detect language,
scaffold, install the CLI) from the self-contained specs in `specs/`. Repos may also be
registered as **read-only reference** sources that agents may cite but never modify.

---

## Pros and cons

**Strengths**

- One session coordinates many repos; no terminal-juggling, no manual context copying.
- Guardrails are hook-enforced, so they hold even when the model is wrong or under
  `--dangerously-skip-permissions` — `deny` rules and blocking hooks still fire.
- Opt-in unattended mode gives lossless resume across compaction and process death — durable
  state lives in files + git, not in the context window.
- Frugal: assessment-first means trivial tasks don't spawn a pipeline.
- All state is inspectable on disk (`agent-workspace/`, `*.GATE`, `RESUME-STATE.md`, logs)
  and in git — no hidden state, no database.
- Cross-repo contract verification catches integration drift before it ships.

**Costs and limits**

- **Token-heavy.** A full multi-repo wave spawns many agents. Assessment-first and model
  tiering reduce this, but large waves are expensive. This is not the cheap path.
- **Experimental dependency.** Requires the agent-teams feature flag; behavior tracks the
  current Claude Code version and can shift between releases.
- **Environment-specific as shipped.** Hooks invoke `python` on PATH via `$CLAUDE_PROJECT_DIR`;
  confirm your OS has the right interpreter on PATH and that your Claude Code version expands
  `$CLAUDE_PROJECT_DIR` in hook commands.
- **Quality erodes slightly across many compactions** (summarization is lossy); mitigated by
  externalizing state, but a multi-day single session is not free of drift.
- **Single-session orchestration** is a single point of failure for the CEO; the resume
  anchor + outer loop mitigate it but this is not a distributed system.
- **Setup cost.** Per-repo Codebase-Index + tooling must exist or be bootstrapped, and the
  cross-repo features assume a shared session topology.
- **Complexity.** Many moving parts (agents, hooks, doctrine). For a single small task in a
  single repo, plain Claude Code is simpler.

---

## Setup

1. Requires Claude Code with agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, set in
   `.claude/settings.json`).
2. **Confirm the hook interpreter for your environment.** Hooks invoke `python` on PATH via
   `$CLAUDE_PROJECT_DIR/.claude/hooks/`. Adjust the interpreter (`python`/`python3`/`py`) for
   your OS if needed, and confirm your Claude Code version expands `$CLAUDE_PROJECT_DIR` in
   hook commands (otherwise replace it with an absolute path).
3. Hooks must be trusted on first run. For unattended use, encode hard safety as
   `permissions.deny` rules (these survive `--dangerously-skip-permissions`); never rely on
   chat instructions, which are lost on compaction.

---

## Commands

```
/goat-ceo                                  # multi-repo orchestration (interactive by default; opt-in unattended)
/goat-team:goat <task>                     # single-repo full pipeline
/goat-team:goat-plan <task>                # plan + research only, no code changes
/goat-team:goat-review                     # dual-reviewer audit of existing changes
/goat-team:index-check                     # audit/update the Codebase-Index without a pipeline
```

---

## Layout

```
.claude/
  commands/
    goat-ceo.md                 # multi-repo CEO entry point
    goat-ceo/                   # rules.md, protocols.md, templates.md, roster.md, anti-drift.md, unattended-mode.md
    goat-team/                  # single-repo pipeline skill + role scripts
  agents/                       # custom subagent definitions (team-overseer, -architect, ...)
  hooks/                        # the enforcement layer (Python) + autonomous-loop notes
  settings.json                 # permission deny rules + hook wiring
specs/                          # self-contained bootstrap specs (index system, tooling, GOAT)
scripts/autonomous-loop.ps1     # optional Tier-2 outer loop (restart-on-crash)
agent-workspace/                # per-session artifacts incl. RESUME-STATE.md (gitignored)
logs/                           # per-session audit trail (gitignored)
```

---

## Credits

Inspired by [GSD — Get Shit Done](https://github.com/gsd-build/get-shit-done), which
established that structured, phase-based agent pipelines outperform ad-hoc prompting.
GOAT-CEO extends that idea across repository boundaries and adds a hook-enforced rule layer
and an opt-in unattended compaction-survival mode. MIT licensed.
