# GOAT-CEO — Rework Design

> **Status:** active design of record. **Authored:** 2026-06-15.
> **Supersedes:** the deleted `GOAT-CEO-DESIGN.md` (pre-rework, removed in the June harness-v2 pass).
> This document is the authoritative source for: the **primitive ledger** (§0, cited by `goat-ceo.md`,
> `rules.md`, `protocols.md`), the **fan-out / Workflow-substrate decision** (§A–§E), and the
> **agent roster rationale** (§F, referenced by `roster.md`).
>
> Doctrine prose (`rules.md`, `protocols.md`, `anti-drift.md`) is the operational layer; this is the
> design layer that explains *why* those mechanisms exist and which primitives are sanctioned to build on.

---

## §0 — Primitive Ledger (authoritative)

**The rule (Doctrine #7):** GOAT-CEO builds ONLY on the native Claude Code primitives listed below. Any
mechanism not in this table must be cleared in this document (by the architect, with operator sign-off)
before it is built. This prevents the accretion of hand-rolled scaffolding that rots when the harness
updates. When in doubt, prefer a native primitive over a bespoke one.

| # | Primitive | Native mechanism | GOAT-CEO use | Do NOT hand-roll instead |
|---|---|---|---|---|
| P1 | Skills / slash commands | `/goat-ceo`, `/goat-team:*`; supporting doctrine files read on demand | Entry points + on-demand doctrine | A bespoke command parser |
| P2 | Agent teams | `TeamCreate`, `Agent` (spawn), `SendMessage`, `TeammateIdle` event | The live pipeline substrate; Overseers are background teammates, CEO is fixed lead | A custom message bus or spawn-request relay |
| P3 | Subagents (isolated context) | `Agent` tool; frontmatter `tools`/`model`/`maxTurns`/`disallowedTools`/`permissionMode`/`isolation`/`memory`; `agentType` override | Verbose work runs in subagents; only structured results return to the CEO — the primary defense against CEO context exhaustion | A manual "summarize then discard" loop |
| P4 | Task list | `TaskCreate`, `TaskList`, `TaskGet`, `TaskUpdate`, `addBlockedBy`; `TaskCreated`/`TaskCompleted` events | One task per phase per repo, chained with `addBlockedBy`; the shared list doubles as the cross-repo dashboard | A markdown manifest task tracker |
| P5 | Hooks | `settings.json` events: `PreToolUse`, `PostToolBatch`, `SubagentStart`, `SubagentStop`, `TeammateIdle`, `TaskCreated`, `TaskCompleted`, `Stop`, `PreCompact`, `SessionStart`, `PermissionDenied` | The fail-open enforcement layer (`.claude/hooks/`) | Prompt-only "please remember to" rules for anything mechanically enforceable |
| P6 | Permissions | `permissions.deny`; permission modes (`plan`, `dontAsk`, `acceptEdits`) | Unconditional denies (`git add -A/.`, `.env`); read-only scouts in `plan` mode | A custom approval gate |
| P7 | Git worktree isolation | `isolation: worktree` (frontmatter / `agent()` opt); `worktree.baseRef`; `cleanupPeriodDays`; `.worktreeinclude` | Parallel implementers get isolated trees so concurrent edits never collide | File locks or copy-dirs |
| P8 | Workflow tool | `agent()`, `parallel()`, `pipeline()`, `phase()`, `log()`, `budget`, `schema` (StructuredOutput), `isolation:'worktree'`, `agentType`, nested `workflow()` | Deterministic fan-out/merge control flow for autonomous execution phases (§A, §B) | A CEO-improvised prose merge loop, a custom DAG runner |
| P9 | `additionalContext` injection | `SessionStart` hook | Re-inject the resume anchor on fresh/compacted/resumed sessions | A bespoke "paste the state back in" convention |
| P10 | Plan-mode approval | Native teammate plan-approval primitive | The Phase 1→2 gate — architect cannot write until the CEO approves its plan | A prose "wait for my OK" |
| P11 | MCP tools | Surfaced via `ToolSearch` (deferred tools), schemas loaded on demand | Per-agent access to session-connected MCP servers | Re-implementing an integration the MCP server already provides |
| P12 | Memory | `memory: project` frontmatter; file-based memory dir | Cross-session persistence of decisions/state | An ad-hoc state file no primitive reads |

**Retired hand-rolled mechanisms** (removed because a native primitive covers them — do not reintroduce):
- **Scribe logger** (`team-ceo-scribe`) → the `claude agents` view + OTEL timeline cover observability natively (P2/P3). Tier-2 cross-repo decisions are logged directly by the CEO to `logs/<prefix>/cross-repo.log`.
- **Overseer→CEO spawn-request indirection** → native multi-level spawn (P2/P3); the CEO/Overseer spawn directly.
- **Markdown manifest task tracker** → native `TaskCreate`/`TaskList` (P4).
- **Manual read-eval orchestration loop** → the Workflow tool's `pipeline()`/`parallel()` (P8) for autonomous phases.

---

## §A — Why this rework: two separable decisions

The rework is framed as "fan out more with worktrees," but research (2026-06-15) showed that conflates **two
orthogonal decisions**. Keeping them separate is the central design insight — each can be banked independently.

- **Decision A — Workflow-as-substrate.** Move the *autonomous execution* phases from CEO-improvised prose into
  a deterministic Workflow script (P8). **Buys:** context economy (verbose agent output stays out of the CEO's
  window — the single biggest win), deterministic control flow, native within-session resume.
- **Decision B — Worktree fan-out throughput.** A machine-readable disjoint-partition + a speculative/batched
  merge gate. **Buys:** real wall-clock speed and scale. **Substrate-agnostic** — works whether execution is a
  Workflow script or prose. This is the actual speed/scale prize, and the higher-ROI, lower-risk half.

**The system is already a hybrid.** `goat-ceo.md §4.1` already names Workflow the *primary* execution path with
the prose state-machine as *fallback*, and a skeleton exists at `templates.md §17`. So this rework is **promotion
+ porting**, not a greenfield rebuild.

---

## §B — Enforcement model under Workflow (empirically verified)

The make-or-break question was: do the `settings.json` hooks fire on **Workflow-spawned** agents? Resolved by a
live probe on **2026-06-15**: a Workflow `agent({agentType:'team-architect'})` attempting a `Write` against a
declared-but-unmet phase gate was **BLOCKED** by `check_phase_gate.py` with the exact message
`PHASE GATE BLOCK: role 'team-architect' cannot use Write...`. This proves **both** that PreToolUse hooks fire on
Workflow agents **and** that the agent's role is carried in the hook payload.

| Gate class | Wired on | Survives Workflow execution? | Migration action |
|---|---|---|---|
| Phase order (`check_phase_gate.py`), STOP kill-switch (`check_stop_file.py`), registry role-gate (`guard_registry.py`), commit/push guard (`guard_git_commit.py`) | `PreToolUse` | **YES — verified** (phase gate empirically; others share the same mechanism) | Carry over unchanged |
| Test gate (`check_test_gate.py`), review gate (`check_review_gate.py`), tool-call audit (`check_toolcall_audit.py`), review-iteration cap | `TaskCompleted` | **NO** — Workflows bypass the Task system (results live in script variables) | Re-express as explicit script stages |
| Artifact presence (`check_artifacts.py`), partition validity (`check_partition.py`) | `SubagentStop` / `TeammateIdle` | **YES — verified** (2026-06-15 probe: `SubagentStop` fires on Workflow agents and the payload carries `agent_type` plus `agent_transcript_path`) | Carry over unchanged |
| Pipeline-complete (`check_pipeline_complete.py`) | `Stop` (CEO turn) | **YES** — filesystem-based (`*.GATE` + `EXPECTED-GATES.txt`), execution-model independent | Carry over unchanged |
| Worktree isolation, `maxTurns`, `disallowedTools`, `permissionMode: plan` | frontmatter | **YES** — frontmatter applies however the subagent is spawned | Carry over unchanged |

**Gates-as-stages (the three Task-wired gates become *more* deterministic, not lost):**
- **Test gate** → after the implement/merge stage, the script runs the broad suite itself and `throw`s on
  non-zero (the logic is already standalone in `check_test_gate.py`, including the hollow-pass guard). A stage
  is *stricter* than the fail-open TaskCompleted hook.
- **Review gate + iteration cap** → `agent(prompt, {schema: VERDICT})`; the script checks `.verdict==='PASS'`,
  writes `REVIEW.GATE` or increments `REVIEW-ITERATION.txt` / writes `ESCALATE_REQUIRED`.
- **Tool-call audit** → it inspects a specific subagent's transcript. The 2026-06-15 probe showed the
  `SubagentStop` payload includes `agent_transcript_path` — so this gate is likely **salvageable** by rewiring
  it from `TaskCompleted` to a `SubagentStop` hook that reads that path (instead of being lost). Until rewired,
  the fresh-context adversarial reviewer (templates §12) remains the substantive backstop.

**Verdict:** enforcement *survives* the migration. The scary "enforcement silently evaporates" risk is retired.

---

## §C — The interactive / scripted seam

Research (control-theory + agent-systems literature, 2026-06-15) and the repo structure converge on the same
boundary. The seam is **Step 3.1** — where the CEO writes `EXPECTED-GATES.txt` and removes `INTAKE-ACTIVE`.

- **Interactive CEO loop (≤ Step 3.1):** intake (Steps 1.0–1.3, mandatory per Doctrine #8), plan approval
  (native plan-mode gate, P10), repo confirmation. A script cannot run intake (Workflows are non-interactive;
  `AskUserQuestion` fails inside them).
- **Scripted kernel (Step 4 body):** the per-repo 6-phase fan-out/merge driving logic, with the three
  Task-wired gates as stages (§B).
- **CEO again (Steps 5–6):** cross-repo routing, **single-committer merge/land** (stays CEO-manual — see §D),
  independent Phase-6 verification, final commit.

This is the **control-plane / data-plane** pattern: the interactive CEO is the control plane (can be idle or
compacted while the kernel runs); the Workflow script is the data plane.

**Steering mechanisms (ranked by value ÷ throughput cost) — do NOT use per-step approval:**
1. **STOP-file kill switch** (now fires on `Bash|PowerShell|Write|Edit`, verified) — coarse, ~zero cost, highest ROI. Make it discoverable.
2. **Per-agent worktree isolation** — makes interruption cheap (discard partial work with one command).
3. **Phase-boundary yields** — the kernel pauses *between* phases to check for operator input; matches the phased design; resume at boundaries (not mid-step).
4. **Async watch channel** (`STATUS.md` + `claude agents` view) — observation tier; keeps operator situation-awareness alive.
5. **Risk-triggered hard yield** on irreversible actions only (~0.8% of actions) — the one place a blocking gate earns its cost.

Per-step approval is rejected: automation-bias evidence shows high-frequency gates degrade the very oversight
they advertise, and intermediate autonomy beats full human-in-the-loop for recoverability.

---

## §D — Worktree fan-out & reconvergence architecture

**Fan-out is cheap; reconvergence is the architecture.** The current serial "merge → full suite → merge"
(`protocols.md §D`) is correct for safety but is an **Amdahl bottleneck** — if the test run is a fraction *s*
of the work, fan-out caps at ~1/s regardless of agent count, and stops paying off at roughly N ≈ 1/s.

**Target: a layered deterministic pipeline.**
```
PLAN     Architect emits a machine-readable partition: per task →
         { files[] (disjoint), merge_order, blockedBy[], shared/generated/lockfile
           resources reserved to ONE coordinator task, frozen interfaces }.
FAN-OUT  One agent per task in its own worktree (P7). Dependent tasks STACK
         (branch from parent, not HEAD). A few hard, test-covered tasks MAY use
         BEST-OF-N (k attempts, winner chosen by EXECUTING TESTS, not an LLM judge).
GATE     Speculative/batched merge queue: test N branches in parallel against
         predicted trunk; land only if bit-for-bit green (Bors / Uber-SubmitQueue model).
BISECT   On batch failure, fall back to linearized sequential merges + git bisect
         (log2 N) to localize the culprit, eject it, re-batch.
RESIDUAL Integration agent touches ONLY semantic conflicts + red tests the scripted
         merge could not resolve — gated by a green suite.
```

**Hard constraints, grounded in research and doctrine:**
- **Merge stays CEO-manual.** Single-committer (Doctrine #1, the INDEX-RACE incident) is load-bearing; the
  script owns fan-*out* and `throw`s at the integration boundary for the CEO to land. Relaxing this re-opens the
  exact corruption class it was built to close.
- **File-disjoint ≠ semantic-conflict-free.** A signature change in one file + a new caller in another (zero file
  overlap) breaks at runtime. Defense: freeze interfaces across the DAG; reserve all shared/generated/lockfile
  resources to one coordinator branch; always run the full suite post-merge.
- **Octopus merge is all-or-nothing** and leaves nothing to bisect; keep the linearizable fallback (BISECT stage).
- **Never let an LLM be the final gate.** LLM merge-resolution is <60% correct; best-of-N's selection gap is
  ~30–55 points. Selection and merge-acceptance are decided by **executing tests**, with a human on the residual.

**New artifact required:** `IMPLEMENTATION-MANIFEST.json` (the structured partition) — today the partition is
free-form prose in `IMPLEMENTATION-MANIFEST.md`, which the integrate stage cannot verify programmatically.

---

## §E — Costs & risks accepted

| # | Cost / risk | Mitigation |
|---|---|---|
| R1 | Loss of the native-Task cross-repo dashboard under Workflow (P4) | Rebuild supervision on `STATUS.md` heartbeats + `claude agents` view; keep Tasks for the cross-repo DAG if a hybrid retains them |
| R2 | Workflow resumes **within-session only** — weaker crash/compaction survival than today's prose-fallback + PreCompact anchor | Keep the prose state-machine as disaster-recovery (do NOT delete it); phase-boundary checkpointing |
| R3 | Tool-call audit gate has no clean Workflow home | **Likely salvageable** — rewire from `TaskCompleted` to a `SubagentStop` hook reading the `agent_transcript_path` the 2026-06-15 probe confirmed is in the payload; until then, fresh-context adversarial reviewer + test gate |
| R4 | ~~`SubagentStop` artifact gate firing on Workflow agents is unverified~~ **RESOLVED 2026-06-15** | Probe confirmed `SubagentStop` fires on Workflow agents and carries `agent_type` (+ `agent_transcript_path`). `check_artifacts.py` / `check_partition.py` carry over unchanged |
| R5 | Partition-quality risk: a bad disjoint partition causes conflicts/rework | Interface freezes + coordinator-owned shared resources + full-suite post-merge; `log()` any partition the architect could not prove disjoint |

---

## §F — Agent roster (design rationale)

The **operational** agent-to-phase map is the single source of truth in
[`.claude/commands/goat-ceo/roster.md`](.claude/commands/goat-ceo/roster.md) — it is NOT duplicated here to
avoid drift. This section records the *design intent* behind it:

- **One agent type per phase responsibility**, with the heavy/verbose roles (researcher, implementer, verifier)
  isolated in subagents (P3) so their context never lands in the CEO window.
- **Hard constraints live in frontmatter, not prose** (P3/P6): `isolation: worktree` (implementer),
  `permissionMode: plan` (ceo-assistant), `disallowedTools` (implementer/overseer/roadmap-architect),
  `maxTurns` caps — these are harness-enforced and survive any execution-substrate change (§B).
- **Spawn authority:** Overseer spawns the four pipeline agents directly (P2 multi-level spawn — no relay);
  `team-ceo-assistant` and `team-cross-reviewer` are CEO-exclusive (cross-repo authority).
- **Lightweight inline roles** (completeness-critic, judge) are inline `Agent` calls with minimal tool sets, not
  separate agent files — they are cheap, phase-local, and defined by their spawn template.
- **Under Decision A**, the Overseer's phase-*driving* body shrinks (the Workflow script drives phases); the
  Overseer becomes a thinner per-repo launcher/supervisor. The agent *types* and their constraints are unchanged.

---

## §G — Migration sequencing & open items

**Recommended order (de-risked):**
1. **Decision B first, substrate-agnostic** — author `IMPLEMENTATION-MANIFEST.json` schema + the speculative-batch
   merge gate. Highest ROI, lowest risk, pays off in either substrate.
2. **Verify R4** — a follow-up probe for `SubagentStop` on Workflow agents (cheap; closes the last enforcement unknown).
3. **Decision A vertical slice** — convert one repo's Step-4 execution into a Workflow script with the three gates
   as stages; prove the end-to-end pattern before broad rollout.
4. **Keep the prose fallback** as disaster-recovery (R2).

**Landed (this session, 2026-06-15):**
- ✅ Step 1 — Decision-B **doctrine**: the `IMPLEMENTATION-MANIFEST.json` schema + the speculative-batch
  reconvergence procedure are in `protocols.md §D`; the architect emits the partition (`templates.md §5`);
  the research gate requires it (`protocols.md`/`goat-ceo.md`); `rules.md` Rule 5 and the overseer wire to it.
- ✅ Step 1 — Decision-B **enforcement**: `.claude/hooks/check_partition.py` validates disjointness — a
  `SubagentStop` gate on the architect (blocks an invalid partition) and a CLI the CEO runs at the research
  gate. Tested across valid / overlapping / dangling-ref / hook-role cases.
- ✅ Step 3 — Decision-A reference kernel: `.claude/commands/goat-ceo/pipeline-kernel.reference.js` — a
  correct, API-validated Workflow execution kernel (research → revise → partition → worktree fan-out → merge
  handoff), plus the review-kernel verdict-gate-as-stage in `templates.md §17`. Replaces the prior broken
  skeleton (wrong `agent({subagent_type})` API + `fs`-based gate checks Workflows cannot run).
- By design, NOT in the script: the §D speculative-MERGE itself stays CEO-manual (single committer, Doctrine
  #1) — the kernel fans out and hands the branch list back; the CEO lands and launches the review kernel.
- Remaining to make execution fully live: instantiate the kernel against a real target repo + task (the CEO
  fills `{VARIABLE}`s at Step 3.1); optionally rewire the tool-call audit onto `SubagentStop` (R3).

**Verified facts (2026-06-15, all live probes):**
- ✅ PreToolUse hooks fire on Workflow agents and carry `agent_type`.
- ✅ `SubagentStop` fires on Workflow agents and carries `agent_type` + `agent_transcript_path` (R4 resolved).
- ✅ Workflows bypass the Task system → `TaskCompleted` gates do not fire (docs + design).
- ✅ Workflows are non-interactive; `AskUserQuestion` unavailable inside them.
- ✅ Worktree branches return unmerged; the parent/CEO merges.

**Open items:** whether to retain a Task-based cross-repo DAG in a hybrid (R1); rewiring the tool-call audit
onto `SubagentStop`/`agent_transcript_path` (R3 — now a build task, not an unknown).

---

## §H — Research provenance

This design is backed by a 2026-06-15 research pass (four parallel agents + one live Workflow probe) covering:
hook/worktree behavior under Workflow, parallel-branch reconvergence strategies (Amdahl limits, speculative merge
queues, stacked branches, best-of-N selection gap), the interactive/autonomous seam (control-plane/data-plane,
steering mechanisms), and a file-grounded migration impact map. Confidence is highest where claims are peer-
reviewed or empirically probed (the enforcement-survival result, the Amdahl ceiling, the selection gap) and lower
where they rest on vendor documentation (specific autonomy-telemetry figures). Where a claim is vendor-sourced it
is treated as directional, not load-bearing.
