# GOAT-CEO

A multi-repo orchestration harness for Claude Code. One Claude Code session acts as a **"CEO"**
that drives a structured, gated agent pipeline across several repositories in parallel,
coordinates changes that cross repo boundaries, and is the single committer for all of them. It
runs **interactively by default** — you confirm the plan and the CEO yields to steer at phase
boundaries — with an **opt-in unattended mode** that keeps working through context compaction
without losing state.

It is **not** an application or a daemon. It is a set of Claude Code skills (slash commands),
custom subagent definitions, and `settings.json` hooks that turn a single Claude Code session
into a supervised, rule-enforced orchestrator built on native Claude Code primitives — plus
**four opt-in knowledge planes** (internal-code index, coding-standards, a verifiable
external-research KB, and worktree fan-out) that are inert until you enable them.

> **Status: experimental.** Requires Claude Code with the agent-teams feature
> (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, already set in `.claude/settings.json`). Hooks invoke
> `python` on PATH via `$CLAUDE_PROJECT_DIR` — adjust the interpreter for your OS (see
> [Setup](#setup)). MIT licensed.

---

## What it does

- **Drives N repos from one session.** Each repo gets its own "Overseer" subagent running a
  6-phase pipeline (plan → research → implement → index → review → finalize). Repos run in
  parallel; you watch one terminal.
- **Routes cross-repo changes.** Repos declared as a related group flag contract/schema/API
  changes to the CEO, which classifies and assesses impact before any dependent repo acts. Repos
  declared isolated receive nothing about each other.
- **Enforces gates with hooks, not vibes.** Phase order, single-committer discipline, test/review
  gates, anti-hallucination checks, and a STOP kill-switch are enforced by `settings.json` hooks
  that fire regardless of what the model "decides" — a hook can block a tool call (`exit 2`) even
  under `--dangerously-skip-permissions`. Every hook is **fail-open** (a hook bug never blocks
  legitimate work), and the CEO live-fire-tests the enforcement layer at session start.
- **Fans implementers out into isolated worktrees.** Disjoint work runs as parallel implementers
  in their own git worktrees, then reconverges through a speculative-batch merge — see
  [Worktree fan-out](#worktree-fan-out-and-reconvergence).
- **Builds four opt-in knowledge planes.** Internal-code grounding (Codebase-Index), coding
  standards + reuse (rubric), a verifiable, re-queryable external-research KB (Research System),
  and throughput (fan-out) — each disjoint, opt-in, and a no-op when absent. See
  [Knowledge planes](#the-four-knowledge-planes-optional).
- **Two modes: collaborative by default, unattended on opt-in.** Unattended runs survive
  Claude Code's auto-compaction with **durable, machine-grounded resume** (git state + sentinels
  + a compact machine-refresh block) via a self-healing resume anchor — machine-verifiable state
  is preserved across compaction; running narrative is capped and can decay. See
  [Operating modes](#operating-modes).
- **Is frugal by default.** Before spawning a pipeline, the Overseer reads the code and assesses
  whether the task needs one at all — investigation/verification tasks and one-line fixes are
  resolved directly. No 8-agent pipeline for a typo. The CEO picks the smallest of **three effort
  tiers** that completes the task safely — see [Effort tiers](#effort-tiers-how-much-machinery).

---

## Effort tiers — how much machinery

GOAT-CEO is frugal by default: it does **not** run the full pipeline for every task. The CEO sizes
each request to the smallest of **three tiers** that completes it safely — there is no L0–L5 ladder,
the real decision is roughly trinary:

| Tier | When | What runs |
|---|---|---|
| **Direct** | Investigation/verification only, or a trivial one-file edit with no API/schema/security touch and tests available. | No pipeline. The CEO (or one Overseer) answers or makes the edit directly. |
| **Standard** | A normal change in one repo. | The per-repo pipeline: plan → implement → review → test. |
| **Full CEO** | Work that fans out into parallel worktrees and/or spans multiple repos. | Worktree fan-out, speculative-batch merge, cross-repo routing — the whole harness. |

The CEO **picks the smallest tier that is safe** and escalates a tier up if the work turns out to be
riskier than it looked (touches a security/permissions/schema surface, won't decompose cleanly, etc.).

When the CEO chooses a **reduced** path (Direct — investigation-only or a trivial direct fix that
skips the pipeline), that choice is **recorded**: it emits a one-line `agent-workspace/ASSESSMENT.md`
naming the chosen tier and why. This makes "the system chose to do less" auditable rather than
silent — see the C19 decision-visibility artifact documented in
[`.claude/commands/goat-ceo.md`](.claude/commands/goat-ceo.md).

---

## How it works

### Roles

| Role | Subagent type | Model | Count | Responsibility |
|---|---|---|---|---|
| **CEO** | the main session | session model | 1 | Sole integrator. Owns the mission, the rules, the phase gates, and is the **single committer**. Writes every gate; spawns Overseers + cross-repo agents. |
| **Overseer** | `team-overseer` | opus | 1 per repo | Runs one repo's 6-phase pipeline; spawns its own pipeline agents (native deep spawn); reports phase completions + cross-repo flags to the CEO. |
| **Architect / Planner** | `team-architect` | opus | per phase | Writes `PLAN.md` + the partition manifest (Phase 1); revises after research (Phase 2). Also the framing for the review **judge** (opus, read-only). |
| **Researcher** | `team-researcher` | opus | 2 parallel | Codebase + technical research; cite `file:line`; iterate until a 5-condition convergence gate passes. Has `WebSearch`/`WebFetch`. |
| **Implementer** | `team-implementer` | sonnet | N batches | Execute batched edits in **isolated worktrees** (`maxTurns: 30`, cannot spawn sub-agents). Commit *atomically to their own `worktree-<name>` branch*; never push and never commit to main — they hand the CEO a branch + file list to merge. (Commit/push discipline is warn-enforced + single-committer convention, not a hard permission deny — see [Hook enforcement](#the-hook-enforcement-layer).) |
| **Verifier** | `team-verifier` | sonnet | 2+ | Independent dual review (correctness + test-quality); per-worktree diff checks. Read-only on production paths. Also the framing for the **completeness critic** (haiku). |
| **CEO-Assistant** | `team-ceo-assistant` | opus | on demand | Read-only cross-repo impact scout (`permissionMode: plan` — hard read-only). CEO-only. |
| **Cross-Repo Reviewer** | `team-cross-reviewer` | sonnet | per group | Verifies API/schema/config alignment across a related group after all members finish. CEO-only. |
| **Roadmap Architect** | `team-roadmap-architect` | opus | per initiative | Maintains a single milestone roadmap; cannot spawn sub-agents. |

**Single authority, flat integration.** Overseers spawn their own pipeline agents, but the CEO is
the only agent that commits **to main**. Implementers commit atomically to their own
`worktree-<name>` branch and hand those branches back for the CEO to merge — they never push and
never commit to main. This is **not** a hard permission deny: raw `git commit`/`git push` are
*warn-enforced* by the `guard_git_commit.py` hook (it surfaces the command for review, it does not
block it), and single-committer-to-main is a convention the CEO upholds. The unconditional hard deny
covers only the bare `git add -A`/`git add .` sweep. See
[Hook enforcement](#the-hook-enforcement-layer) and
[docs/enforcement-truth-table.md](docs/enforcement-truth-table.md).

### The pipeline (per repo)

| Phase | What happens | Gate to advance |
|:--:|---|---|
| **0** | **Assessment.** Overseer reads code/tests, decides if a pipeline is warranted. Non-code tasks end here. *(The Phase-0 plan gate and mandatory intake are **soft by design** — see note below.)* | — |
| **1** | **Plan.** Architect writes `PLAN.md` (goal, acceptance criteria as fenced JSON, task breakdown). Native plan-approval gate. | `PLAN.GATE` |
| **2** | **Research.** Two researchers annotate the plan; architect revises; loop exits on a 5-condition AND-gate, emitting the partition in two forms: `IMPLEMENTATION-MANIFEST.md` (human-readable batch narrative) and `IMPLEMENTATION-MANIFEST.json` (the machine-checked disjoint partition the `check_partition.py` hook validates). | `RESEARCH.GATE` |
| **3** | **Implement + integrate.** Implementers execute batches in parallel worktrees; the CEO does the speculative-batch merge and runs the suite. | `IMPLEMENT.GATE` (+ optional `RUBRIC.GATE`) |
| **4** | **Index.** One pass on merged main updates/repairs the Codebase-Index. | `INDEX.GATE` (0 stale + 0 missing) |
| **5** | **Review.** Two fresh-context reviewers (correctness + test-quality with a reward-hack audit), optionally a third standards reviewer → completeness critic → a bias-mitigated judge emits binding PASS/FAIL JSON. | `REVIEW.GATE` (judge PASS; capped at 2 fix iterations then escalates) |
| **6** | **Finalize.** CEO re-runs the broad suite against a frozen baseline, then makes one pathspec-scoped commit. | — |

Phase gates are **sentinel files** (`agent-workspace/<PHASE>.GATE`). **The CEO writes every gate;
the hooks only *validate* it** (a `PreToolUse` hook blocks a role from writing until its required
gate exists; a `Stop` hook blocks the CEO's turn from ending while any expected gate is missing).
The one hook that writes anything is `check_review_gate.py`, which writes `ESCALATE_REQUIRED` past
the iteration cap.

> **Soft by design: the Phase-0 plan gate and mandatory intake.** Two of the gates above are
> **CEO behavioral conventions, not harness-enforced plan-mode locks** — and that is deliberate.
> The **Phase-0 plan-approval gate** (the CEO drafts a coordination plan and waits for your
> confirmation before launching the pipeline) and the **mandatory-intake rule** (always confirm the
> repo set and run the index/prerequisite check first, even when the goal names repos) are enforced
> by prompt discipline, not by a hook: `permissions.defaultMode: "plan"` is **not** set in
> `.claude/settings.json`, so no hook can mechanically block the CEO from skipping them. They are
> labeled SOFT in [`rules.md`](.claude/commands/goat-ceo/rules.md)'s enforcement map and in
> [docs/enforcement-truth-table.md](docs/enforcement-truth-table.md). The *hard* gates are the
> sentinel-file phase order, the test/review gates, the anti-hallucination checks, the
> single-committer `git add -A/.` deny, and the STOP kill switch — see the truth table for the
> precise hard/soft/advisory split.

---

## The four knowledge planes (optional)

GOAT-CEO's quality comes from grounding agents in knowledge — and four *optional* planes deepen
that. Each is **detected at intake, recorded in `repo-registry.json`, disjoint from the others,
and a complete no-op when absent** (the pipeline runs exactly as before). They answer different
questions:

| Plane | Question | Where it lives | Enabled by |
|---|---|---|---|
| **Codebase-Index** | internal code — *"where things live"* | per-repo `Codebase-Index/` + `codebase-index-tools` CLI | `INDEX-AVAILABLE` |
| **rubric** | conventions / reuse — *"what to call, how to write it"* | vendored `tools/rubric/`; per-repo `.rubric/` KB | `RUBRIC-AVAILABLE` |
| **Research KB** | external — *"why / what does prior art say"* | vendored `tools/research-system/`; shared `research-kb/` | `RESEARCH-KB-AVAILABLE` |
| **Worktree fan-out** | throughput — *"do it faster"* | native `isolation: worktree` + `IMPLEMENTATION-MANIFEST.json` | parallel batches |

### Codebase-Index — internal code

A hand-curated, layered Markdown map of a repo's own code (`MASTER-INDEX.md` → section `INDEX.md`),
queried through a local `codebase-index-tools` CLI — no embeddings, no vector DB, deterministic and
human-readable. When available, researchers and implementers run `search`/`inject` to load
task-relevant context *before* touching files, and `check` after. If a repo has no index, GOAT-CEO
can bootstrap one from the self-contained specs in [`specs/`](specs/). Repos may also be registered
as **read-only reference** sources agents may cite but never modify.

```
search --query "auth"           # which indexes cover authentication
inject  --task "fix login bug"  # load all relevant context for a task
check   --all                   # audit for stale / missing indexes (gates Phase 4)
```

### rubric — coding standards + reuse

[rubric](tools/rubric/) is a Claude Code-native standards system, **vendored under `tools/rubric/`**
and run as a host tool (`pip install -e "tools/rubric[gate,retrieval]"`). It answers the
standards/reuse axis the correctness-focused pipeline doesn't, through its **deterministic surface**
(no nested LLM calls on the common path):

- **Grounding (Phase 3).** `rubric context "<task>"` injects the repo's conventions, canonical
  exemplars, and *existing reusable components* (symbol-level, via `ast`) before an implementer
  writes — so it reuses what's there instead of reinventing it. Complements the Codebase-Index's
  architectural map.
- **Gate (Phase 3→4).** A conditional `RUBRIC.GATE`: the CEO runs `rubric check` (deterministic,
  exit-1 on violation) on the merged diff; a blocking standards violation is treated as a fact,
  like a failing test.
- **Standards review (Phase 5).** A third reviewer ("Reviewer C") runs rubric's own
  adversarially-verified review (deterministic gate + grounded review + a mechanical span-check +
  a 3-judge refutation ensemble) as a standards lens feeding the judge — **orthogonal** to the
  correctness/test reviewers, never a replacement.
- **Measurement / self-evolution.** `rubric measure` reports before/after adherence + anti-bloat
  deltas in the session summary; `rubric codify` proposes new standards from recurring verified
  findings for **human approval** (never auto-merged). An opt-in capped self-heal gate
  (`rubric_heal_gate.py`) can feed violations back to the implementer mid-turn.

rubric also lent GOAT-CEO its mechanical **span-check** — confirming a reviewer's cited `file:line`
actually exists — which is grafted onto the correctness reviewers (A/B) as a `SubagentStop` hook,
catching fabricated citations a read-count audit can't. *Full value on Python; partial on Node
(gate + conventions, but no symbol-level reuse index yet); the seed KB is a template — a repo
supplies its own conventions for real value.*

### Research KB — verifiable external research

[The Research System](tools/research-system/) is an auditable external-document research engine,
**vendored under `tools/research-system/`** (engine only; install with
`pip install -e "tools/research-system[capture,retrieval,llm]"`, Python ≥ 3.11). Its non-redundant
value over the built-in `deep-research` skill is **persistence + mechanical provenance**: a
re-queryable corpus where every claim resolves to a verbatim quote in a stored source.

- **Capture-always, verify-on-demand.** The technical researcher captures *every* external source
  it consults into a shared `research-kb/` corpus via `run_capture` (free, no LLM — full source
  text + provenance), so the KB grows comprehensively at near-zero cost. The expensive claim-level
  verify (`run_research`) runs *on demand* over already-captured sources.
- **Reuse-before-research.** Before commissioning an online run, the researcher checks the KB; a
  verified subject covering the question is cited and the run is skipped. The KB compounds across
  sessions, so online research — and its tokens — get rarer over time.
- **Verified vs. captured is recorded, not guessed.** Every claim carries a `verdict`
  (`supported`/`overreach`/`unsupported`); the synthesis contains *only* supported claims. A
  subject with `claims.jsonl` is **verified**; one with only `sources/` is **captured-but-unverified**
  (raw material until verified). Only `verdict: supported` claims may back a finding.
- **Feeds rubric.** Verified, *sourced* coding-standards distill into rubric rules/exemplars (via
  `codify`, human-approved) — making conventions evidence-backed ("we enforce X because [source]").

**Honesty boundary:** it certifies **claim-level traceability to a stored source (faithfulness +
provenance), not truth** — a claim faithfully grounded in a *wrong* source still passes; source
quality stays a human judgment. The corpus is shared cross-repo (gitignored, grows per session);
its LLM stages run on your Claude **subscription** (~$1–3 credit per verified question), so they're
opt-in and gated to subjects "worth persisting."

---

## Worktree fan-out and reconvergence

Phase 3 is where the pipeline parallelizes. When the plan decomposes into independent work, each
batch runs as its own `team-implementer` in an **isolated git worktree** (`isolation: worktree`) —
separate working directories sharing one object store, so concurrent edits never collide.
Implementers commit to their own `worktree-<name>` branch; the CEO remains the only committer.

**Fan-out is cheap; reconvergence is the hard part.** A naive "merge one branch, run the full
suite, merge the next" is Amdahl-bound. So the CEO reconverges with a **speculative-batch** strategy:

1. **Partition.** The architect emits `IMPLEMENTATION-MANIFEST.json` — per batch: a disjoint file
   scope, merge order, dependency edges (`blockedBy`), one coordinator batch that owns
   shared/generated/lockfile resources, and frozen interfaces. A `SubagentStop` hook
   (`check_partition.py`) rejects a partition whose independent batches overlap *before* any
   implementer runs.
2. **Verify, then speculatively merge.** Each branch's diff is checked against its declared scope;
   then all disjoint branches are merged onto a throwaway integration branch and the suite runs
   **once**. Green → fast-forward main. Red → merge one at a time until it reddens — the offending
   branch is the culprit (the merge position *is* the bisect result), eject it and re-batch.
3. **Stacked work lands bottom-up.** Dependent batches merge after their parents, restacking as
   needed.

Merge stays **CEO-manual** by design (single-committer discipline). The same logic runs either as
prose the CEO follows or — when the Workflow tool is available — as a deterministic JavaScript
pipeline ([`.claude/commands/goat-ceo/pipeline-kernel.reference.js`](.claude/commands/goat-ceo/pipeline-kernel.reference.js))
that fans agents out with `isolation:'worktree'` and returns the branch list for the CEO to land. A
best-of-N variant (k attempts at one hard task, winner chosen by **executing tests**, never an LLM
judge) is supported for the rare task that won't decompose. Design + cost models:
[`GOAT-CEO-REWORK-DESIGN.md §D`](GOAT-CEO-REWORK-DESIGN.md).

---

## The hook enforcement layer

All hooks are **fail-open**: any exception exits 0, so a hook bug never blocks legitimate work.
They are wired in `.claude/settings.json`. Because they all invoke the literal `python` interpreter
and fail open, a *missing or mis-named* interpreter would silently disable every gate — so the CEO
runs a **live-fire enforcement self-check** at session start (write `STOP` → attempt a gated action
→ confirm it's blocked) before trusting any HARD rule.

| Event | Hook | Effect |
|---|---|---|
| `PreToolUse` (`Bash\|PowerShell\|Write\|Edit`) | `check_stop_file.py` | If `agent-workspace/STOP` exists, halts the agent at its next tool boundary (faster than a turn boundary — the runaway kill switch). Allows the bare `rm/del STOP` that clears it. |
| `PreToolUse` (`Bash`) | `guard_git_commit.py` | Hard-blocks `git add -A`/`.`; **warns** (not blocks) on raw `git commit`/`git push` for single-committer review. |
| `PreToolUse` (`Write\|Edit`) | `guard_registry.py` | Role-gates `repo-registry.json` writes — CEO + `team-overseer` allowed, other subagents blocked. |
| `PreToolUse` (`Write\|Edit\|Bash`) | `check_phase_gate.py` | Blocks a role's writes until its required `*.GATE` sentinel exists (reads `PHASE-GATES.json`). |
| `SubagentStart` | `record_agent_start.py` | Records agent start times (feeds the turn-budget gate). |
| `SubagentStop` / `TeammateIdle` | `check_artifacts.py` | Blocks a subagent/Overseer from finishing until its declared deliverable exists (PLAN.md / RESEARCH-LOG.md / a verdict block / etc.). |
| `SubagentStop` | `check_partition.py` | Rejects an invalid disjoint-partition manifest (overlapping independent batches) when the architect stops. |
| `SubagentStop` | `check_toolcall_audit.py` | Blocks a reviewer's verdict if it read fewer than 5 files (anti-hallucination), counting calls in *its own* transcript. Gates only the A/B reviewers. |
| `SubagentStop` | `check_span_validity.py` | Blocks a reviewer's verdict if any cited `file:line` span doesn't actually exist in the file — catches fabricated citations a read-count can't. |
| `PostToolBatch` | `check_turn_budget.py` | Forces a yield if an implementer/verifier runs past a ~30-minute budget (availability-gated). |
| `TaskCompleted` | `check_test_gate.py` | Blocks task closure unless the broad suite passes **and actually ran tests** (a zero-test "hollow pass" is rejected). |
| `TaskCompleted` | `check_review_gate.py` | Blocks closure unless the judge verdict is PASS; past 2 fix iterations, writes `ESCALATE_REQUIRED`. |
| `Stop` | `check_pipeline_complete.py` | Blocks the CEO's turn from ending while any expected `*.GATE` is missing or an escalation is pending; in opt-in unattended mode it also holds the turn so the run continues. |
| `PreCompact` | `check_precompact.py` | Self-heals the resume anchor before compaction (**never blocks** — blocking an auto-compaction would deadlock the run). |
| `SessionStart` | `inject_handoff_context.py` | Re-injects the resume anchor (facts-first) on startup/resume/clear/compact. |
| `TaskCreated` | `check_task_naming.py` | Warns (doesn't block) on off-convention task titles. |
| `PermissionDenied` | `log_denial.py` | Appends every denied tool call to an audit log. |

`permissions.deny` also hard-blocks `git add -A/.` (exact-match, so scoped `git add .claude/foo`
still works) and `.env` writes — enforced even under `--dangerously-skip-permissions`. Two hooks
ship but are **opt-in, not wired by default**: `rubric_heal_gate.py` (the capped rubric self-heal,
installed into a target repo) and `guard_destructive_db.py` (a `DROP/RESTORE DATABASE` approval-token
guard, wired at user scope only for repos that need it).

---

## Operating modes

GOAT-CEO runs in one of two modes, chosen at the start of a session. **Collaborative is the default**;
unattended is a deliberate opt-in.

- **Collaborative (default).** An operator is present. The CEO runs the interactive intake, presents
  the plan for confirmation, and **yields at phase boundaries** so you can steer. The keep-going
  machinery stays dormant.
- **Unattended (opt-in).** For a genuinely unattended/overnight run. Only when you explicitly engage
  it (the `AUTONOMOUS-ACTIVE` sentinel) does the CEO turn on the keep-going survival layer that lets
  it work *through* Claude Code's auto-compaction:
  1. **Before compaction** — `check_precompact.py` regenerates a machine-readable `RESUME-STATE.md`
     from ground truth (per-repo git HEAD/branch, the `*.GATE` sentinels present, the mission, a task
     snapshot) and **always allows** the compaction.
  2. **After compaction** — `inject_handoff_context.py` re-injects that anchor **facts-first**, with
     a "verify against git + sentinels before trusting" banner.
  3. **Doctrine** — in unattended mode only, low context is *not* a stop condition; the legitimate
     stops are an operator `STOP` file, a hard escalation, or mission completion.

The resume anchor is **machine-derived facts, not decaying prose**, and on resume git + sentinels
win over any prose disagreement. An optional outer loop
([`scripts/autonomous-loop.ps1`](scripts/autonomous-loop.ps1)) relaunches the session on process
death — so an unattended run survives not just compaction but the process itself dying. All of this
lives in one opt-in doctrine file (`.claude/commands/goat-ceo/unattended-mode.md`); in collaborative
mode it is dormant.

---

## Built on native Claude Code primitives

There is no external state store, queue, or daemon — the orchestration *is* the Claude Code feature
surface. A **Primitive Ledger** (`GOAT-CEO-REWORK-DESIGN.md §0`) is the authoritative list of what
GOAT-CEO is allowed to build on; anything not in it must be cleared before being built (Rule 7 —
"compose, don't rebuild").

| Primitive | How GOAT-CEO uses it |
|---|---|
| **Skills / slash commands** | `/goat-ceo` (multi-repo) and `/goat-team:*` (single-repo variants). |
| **Agent teams** (`TeamCreate`, `Agent`, `SendMessage`, `TeammateIdle`) | The live pipeline substrate; Overseers are background teammates, the CEO the fixed lead. |
| **Subagents with isolated context** | Verbose work runs in subagents with their own context windows; only short structured results return to the CEO — the primary defense against CEO context exhaustion. |
| **Task list** (`TaskCreate`, `TaskList`, `addBlockedBy`) | One task per phase per repo, chained to enforce order; doubles as the cross-repo dashboard. |
| **Hooks** (`settings.json`) | The fail-open enforcement layer above. |
| **`permissions.deny` / permission modes** | Unconditional denies (`git add -A/.`, `.env`); read-only scouts run in `plan` mode. |
| **Worktree isolation** | Parallel implementers each get a fresh git worktree; the CEO merges afterward. |
| **Workflow tool** (optional) | The per-repo pipeline can be a JavaScript Workflow script, holding the plan out of the CEO's context. A prose fallback runs the same phases without it. |
| **`additionalContext` injection** | The `SessionStart` hook injects the resume anchor into a fresh/compacted session. |
| **Plan-mode approval** | The Phase 1→2 gate is the native teammate plan-approval primitive. |
| **Vendored tools** (P13/P14) | rubric and the Research System are *cleared compositions* — they wrap existing tools (ast-grep/Ruff/ESLint; trafilatura/BM25) and own a KB, rather than reinventing analysis or research. |

---

## Pros and cons

**Strengths**

- One session coordinates many repos — no terminal-juggling, no manual context copying.
- Guardrails are hook-enforced, so they hold even when the model is wrong or under
  `--dangerously-skip-permissions`.
- Anti-hallucination is mechanical, not advisory: reviewers must read files *and* every cited
  `file:line` span must actually resolve; "tests pass" is independently re-verified against a frozen
  baseline.
- Opt-in unattended mode gives **durable, machine-grounded resume** across compaction and process
  death (git state + sentinels + a compact machine-refresh block) — the machine-verifiable floor is
  preserved; running prose is capped and can decay.
- Four opt-in knowledge planes compound quality — and the research KB makes *future* sessions
  cheaper (verified findings are reused instead of re-researched).
- All state is inspectable on disk (`agent-workspace/`, `*.GATE`, `RESUME-STATE.md`, the KBs) and in
  git — no hidden state, no database. The repo is self-contained (both optional tools are vendored).

**Costs and limits**

- **Token-heavy.** A full multi-repo wave spawns many agents. Assessment-first and model tiering
  reduce this, but large waves are expensive — this is not the cheap path.
- **The LLM-using optional features bill your Claude subscription** via `claude -p` (rubric's
  Reviewer C + codify; the Research System's verify) — opt-in and gated, but real (~$1–3/research
  question, ~60–100 serial subprocess calls per research run).
- **Experimental dependency.** Requires the agent-teams feature flag; behavior tracks the current
  Claude Code version.
- **Environment-specific.** Hooks invoke `python` via `$CLAUDE_PROJECT_DIR`; a wrong interpreter
  silently disables enforcement (the Step 1.0a self-check guards this).
- **The vendored tools are days old, zero-soak** — pin commits, depend on their stable CLI surface;
  rubric is Python-full / Node-partial; the research KB certifies *traceability-to-source, not truth*.
- **Single-session orchestration** is a single point of failure for the CEO (mitigated by the resume
  anchor + outer loop, but not a distributed system); quality erodes slightly across many compactions.
- **Complexity.** Many moving parts. For one small task in one repo, plain Claude Code is simpler.

---

## Setup

**Required**

1. Claude Code with agent teams (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`, already set in
   `.claude/settings.json`).
2. **Confirm the hook interpreter for your environment.** Hooks invoke `python` on PATH via
   `$CLAUDE_PROJECT_DIR/.claude/hooks/`. Adjust the interpreter (`python`/`python3`/`py`) for your
   OS, and confirm your Claude Code version expands `$CLAUDE_PROJECT_DIR` in hook commands (else
   replace it with an absolute path). The CEO live-fire-tests this at session start.
3. Hooks must be trusted on first run. Encode hard safety as `permissions.deny` rules (they survive
   `--dangerously-skip-permissions`); never rely on chat instructions, which are lost on compaction.

**Optional — the knowledge planes** (each enables a `*-AVAILABLE` capability; skip any and the
pipeline runs unchanged)

- **rubric** (vendored, self-contained): `pip install -e "tools/rubric[gate,retrieval]"`, then
  `rubric init --no-claude` in a target repo. Optional: the `ast-grep` binary (multi-language
  structural rules); `radon` (`[...,metrics]`) for `measure`. See
  [`tools/rubric/VENDORED.md`](tools/rubric/VENDORED.md).
- **Research System** (vendored engine, self-contained):
  `pip install -e "tools/research-system[capture,retrieval,llm]"` (**Python ≥ 3.11**). Driven via
  `tools/research-system/scripts/run_capture.py` + `run_research.py` with `--research-root research-kb`.
  See [`tools/research-system/VENDORED.md`](tools/research-system/VENDORED.md).
- **Codebase-Index**: per-repo; bootstrapped from [`specs/`](specs/) if a target repo lacks it.

### Compatibility

**This is experimental, pre-release software.** There are no published releases or tags — you run it
from a clone of `master`. The matrix below records what it has been exercised against, not a support
guarantee.

| Dimension | Status |
|---|---|
| Claude Code version | Tested against the agent-teams experimental builds current at time of writing; behavior tracks the installed version. Run `claude --version` and confirm the custom hook events fire (the CEO live-fire-tests this at session start). |
| OS | **Windows-primary** (developed/run on Windows 11). The commit wrapper ships as `ceo-commit.sh` (Git Bash) and `.ps1` outer loops (`scripts/autonomous-loop.ps1`) for PowerShell. Hooks are OS-agnostic Python; macOS/Linux are expected to work but are less soaked. |
| Python | **3.11+** (the vendored Research System requires ≥ 3.11; hooks themselves run on ≥ 3.8). Must be reachable as `python` on PATH or every fail-open hook silently no-ops. |
| Agent-teams flag | **Required** — `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` (already set in `.claude/settings.json`). |
| Hooks confirmed | All hooks are fail-open and validated to exit 0 on empty/garbage input; the CEO runs a live-fire enforcement self-check at session start. Some gates are availability-gated on experimental events (`PostToolBatch`, `TaskCompleted`, etc.) — they degrade to advisory if the build doesn't emit them. |

`/goat-doctor` validates setup (interpreter-on-PATH, `$CLAUDE_PROJECT_DIR` expansion, agent-teams
events, hook liveness). The honest hard/soft/advisory split for every enforcement rule lives in
[docs/enforcement-truth-table.md](docs/enforcement-truth-table.md); see also
[CHANGELOG.md](CHANGELOG.md) for what changed in the current hardening pass.

**Optional — strict / fail-closed mode.** An opt-in strict mode (`agent-workspace/STRICT_MODE`
sentinel or `GOAT_CEO_STRICT=1`) turns the test gate's no-config degraded-allow into a hard stop and
logs fail-open/degraded events to `agent-workspace/HOOK-FAILURES.jsonl`. Today it affects that one
gate; the helper is shared so other degraded-allow paths can opt in later.

---

## Commands

```
/goat-ceo                          # multi-repo orchestration (interactive by default; opt-in unattended)
/goat-team:goat <task>             # single-repo full 6-phase pipeline
/goat-team:goat-plan <task>        # plan + research only, no code changes
/goat-team:goat-review             # dual-reviewer audit of existing changes
/goat-team:index-check             # audit/update the Codebase-Index without a pipeline
/goat-team:set-models              # change GOAT agent model assignments
```

---

## Layout

```
.claude/
  commands/
    goat-ceo.md                 # multi-repo CEO entry point
    goat-ceo/                   # doctrine: rules.md, protocols.md, templates.md, roster.md,
                                #   anti-drift.md, unattended-mode.md + pipeline-kernel.reference.js
    goat-team/                  # single-repo pipeline skill + role scripts
  agents/                       # 8 custom subagent definitions (overseer, architect, ...)
  hooks/                        # the fail-open enforcement layer (Python)
  settings.json                 # permission deny rules + hook wiring
specs/                          # self-contained bootstrap specs (index system, tooling, GOAT)
tools/rubric/                   # vendored rubric standards tool — pip install -e to enable
tools/research-system/          # vendored research engine (corpora excluded) — pip install -e to enable
scripts/autonomous-loop.ps1     # optional outer loop (restart-on-crash, unattended)
GOAT-CEO-REWORK-DESIGN.md        # the design of record (§0 primitive ledger … §J)
agent-workspace/  logs/  research-kb/  repo-registry.json   # per-session / local state (gitignored)
```

The **design of record** is [`GOAT-CEO-REWORK-DESIGN.md`](GOAT-CEO-REWORK-DESIGN.md): §0 the
primitive ledger, §A–§E the worktree fan-out design, §I the rubric integration, §J the Research
System integration. Both vendored tools are bundled (no submodule — neither has a shared remote), so
a fresh clone is self-contained; you just `pip install -e` the ones you want.

---

## Credits

Inspired by [GSD — Get Shit Done](https://github.com/gsd-build/get-shit-done), which established
that structured, phase-based agent pipelines outperform ad-hoc prompting. GOAT-CEO extends that
across repository boundaries and adds a hook-enforced rule layer, worktree fan-out, opt-in
compaction-survival, and four opt-in knowledge planes. MIT licensed.
