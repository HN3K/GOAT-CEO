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
| P13 | External standards-grounding CLI (`rubric`) — **optional, opt-in per repo** | The `rubric` console-script CLI (deterministic surface: `context`, `check`/`enforce --no-llm`, `index`, `measure`), run as a HOST tool against any target repo | Ground implementers in conventions + symbol-level reuse before they write, and gate convention drift deterministically at integration — the standards/reuse layer GOAT-CEO otherwise lacks. **Cleared composition** (Rule 7): rubric wraps ast/ast-grep/Ruff/ESLint and owns a two-plane KB; it does NOT duplicate the Codebase-Index (different plane) and is used via its CLI only. Its own Claude Code hooks / `claude -p` LLM path are NOT used in-pipeline. See §I. | Re-implementing a linter/standards-enforcement layer by hand; hand-rolling a conventions KB |
| P14 | External research-capture-and-verify CLI (Research System) — **optional, opt-in** | The vendored `tools/research-system/` engine (`run_capture`/`run_research`): capture web sources in full → claim-level exact-quote attribution → cross-model verify → abstain → synthesize | Build a reusable, auditable external-research KB (`research-kb/`) so researchers REUSE verified findings before re-running online research, and feed evidence-backed standards into rubric (§J). **Cleared composition** (Rule 7): wraps trafilatura/BM25/`claude -p`, owns an on-disk auditable corpus; does NOT duplicate the Codebase-Index (code plane), rubric (conventions plane), or the `deep-research` skill (ephemeral). Driven via its scripts; LLM backend is the Claude subscription (`claude -p`) by default, swappable via the `LLMClient` seam. Certifies traceability-to-source, not truth. See §J. | Re-implementing a web-capture/verification research pipeline by hand |

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
| Test gate (`check_test_gate.py`), review gate (`check_review_gate.py`), review-iteration cap | `TaskCompleted` | **NO** — Workflows bypass the Task system (results live in script variables) | Re-express as explicit script stages |
| Artifact presence (`check_artifacts.py`), partition validity (`check_partition.py`), reviewer tool-call audit (`check_toolcall_audit.py`) | `SubagentStop` / `TeammateIdle` | **YES — verified** (2026-06-15 probe: `SubagentStop` fires on Workflow agents and the payload carries `agent_type` plus `agent_transcript_path`) | Carry over unchanged |
| Pipeline-complete (`check_pipeline_complete.py`) | `Stop` (CEO turn) | **YES** — filesystem-based (`*.GATE` + `EXPECTED-GATES.txt`), execution-model independent | Carry over unchanged |
| Worktree isolation, `maxTurns`, `disallowedTools`, `permissionMode: plan` | frontmatter | **YES** — frontmatter applies however the subagent is spawned | Carry over unchanged |

**Gates-as-stages (the three Task-wired gates become *more* deterministic, not lost):**
- **Test gate** → after the implement/merge stage, the script runs the broad suite itself and `throw`s on
  non-zero (the logic is already standalone in `check_test_gate.py`, including the hollow-pass guard). A stage
  is *stricter* than the fail-open TaskCompleted hook.
- **Review gate + iteration cap** → `agent(prompt, {schema: VERDICT})`; the script checks `.verdict==='PASS'`,
  writes `REVIEW.GATE` or increments `REVIEW-ITERATION.txt` / writes `ESCALATE_REQUIRED`.
- **Tool-call audit** → **DONE (2026-06-15):** rewired from `TaskCompleted` to a `SubagentStop` hook that reads
  the reviewer's OWN `agent_transcript_path` (the probe confirmed the payload carries it). It now fires in both
  substrates and is *more* precise than before (the old version counted any agent's reads from "the latest
  session JSONL"). Gates only A/B reviewers — the judge/critic are exempted via the `"reviewer"` verdict marker.
  Not a casualty after all.

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
| R3 | ~~Tool-call audit gate has no clean Workflow home~~ **RESOLVED 2026-06-15** | Rewired to a `SubagentStop` hook reading the reviewer's own `agent_transcript_path`; fires in both substrates, gates only A/B reviewers (judge/critic exempt). More precise than the old `TaskCompleted` version |
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
- ✅ R3 — rewired the reviewer tool-call audit (`check_toolcall_audit.py`) from `TaskCompleted` to a
  `SubagentStop` hook reading the reviewer's own `agent_transcript_path`. Works in both substrates, gates only
  A/B reviewers (judge/critic exempt), tested across pass/block/exempt/role cases.
- Remaining to make execution fully live: instantiate the kernel against a real target repo + task (the CEO
  fills `{VARIABLE}`s at Step 3.1).

**Verified facts (2026-06-15, all live probes):**
- ✅ PreToolUse hooks fire on Workflow agents and carry `agent_type`.
- ✅ `SubagentStop` fires on Workflow agents and carries `agent_type` + `agent_transcript_path` (R4 resolved).
- ✅ Workflows bypass the Task system → `TaskCompleted` gates do not fire (docs + design).
- ✅ Workflows are non-interactive; `AskUserQuestion` unavailable inside them.
- ✅ Worktree branches return unmerged; the parent/CEO merges.

**Open items:** whether to retain a Task-based cross-repo DAG in a hybrid (R1). (R3 — tool-call audit — done.)

---

## §H — Research provenance

This design is backed by a 2026-06-15 research pass (four parallel agents + one live Workflow probe) covering:
hook/worktree behavior under Workflow, parallel-branch reconvergence strategies (Amdahl limits, speculative merge
queues, stacked branches, best-of-N selection gap), the interactive/autonomous seam (control-plane/data-plane,
steering mechanisms), and a file-grounded migration impact map. Confidence is highest where claims are peer-
reviewed or empirically probed (the enforcement-survival result, the Amdahl ceiling, the selection gap) and lower
where they rest on vendor documentation (specific autonomy-telemetry figures). Where a claim is vendor-sourced it
is treated as directional, not load-bearing.

---

## §I — Optional integration: `rubric` standards-grounding (RUBRIC-AVAILABLE)

> **Status:** design of record (2026-06-15). **Not yet built.** Primitive ledger: P13. Source project:
> `C:\Users\hnthr\source\KadenSeriousProjects\rubric` (pin a commit before depending on it — built 2026-06-14/15,
> zero soak). Backed by a 4-agent analysis pass (capability/CLI contracts, integration-point mapping,
> overlap/merge design, readiness/orchestration-fit).

`rubric` is a Claude Code-native standards system: a two-plane KB (portable **conventions/exemplars** + per-repo
**symbol-level reuse catalog** via `ast`), a deterministic blocking gate (ast-grep/Ruff/ESLint), an adversarially-
verified advisory review, and a codify loop. It fills GOAT-CEO's clearest gap: GOAT-CEO guarantees *tests pass* and
*review happened*, but nothing grounds implementers in house conventions + reusable components before they write,
and nothing blocks convention drift. rubric is the **optional, opt-in per-repo** capability that does, modeled on
the existing `INDEX-AVAILABLE` pattern. It honors Rule 7 (compose, don't rebuild) and is cleared as P13.

### §I.1 — Six load-bearing decisions (the safe shape)

The naive "bolt rubric's full pipeline into Phase 5" double-pays for adversarial review, risks verdict collisions,
and can blow the implementer's `maxTurns` on self-heal thrash. The adopted shape avoids all three:

1. **Deterministic surface only, in-pipeline.** Use `rubric context` (grounding), `rubric check` / `enforce --no-llm`
   (gate), `rubric index` (reuse catalog), `rubric measure` — all **free, zero LLM calls**. Do NOT run rubric's
   `--verify` ensemble or its `claude -p` path in-pipeline (the seed KB has 0 LLM-rules, so this adds zero
   mandatory LLM cost). Any LLM standards-review (v2) runs via GOAT-CEO's own `team-verifier` reading the KB, not
   rubric's `claude -p` (avoids Claude-in-Claude nesting + invisible subscription billing).
2. **rubric is a HOST tool, not a per-repo dependency — and is VENDORED at `tools/rubric/`.** Bundled in
   this repo so a fresh clone is self-contained; install once with `pip install -e "tools/rubric[gate,retrieval]"`
   (puts `rubric` on PATH), then invoke `rubric <cmd> --repo <target> --kb <portable-kb>` against any target repo.
   Resolves the Python-only problem — rubric is never added to a Node repo's toolchain; the conventions/exemplars
   plane is language-agnostic. (Vendored rather than a git submodule because the upstream rubric repo has no shared
   remote; re-vendor via `git archive` per `tools/rubric/VENDORED.md`.)
3. **Merge retrieval into the ONE existing grounding artifact.** The planes are genuinely disjoint: Codebase-Index
   = architectural map + task routing (the "where"); rubric = symbol signatures + conventions + exemplars (the
   "what to call / how"). The Planner appends `rubric context`'s three sections to the single
   `agent-workspace/index-context.md` it already writes in Phase 1. No competing second grounding path.
4. **rubric is a lens feeding the judge, never a parallel verdict.** Its *blocking gate* = a deterministic FAIL
   fact (like the test gate); its *advisory* output = unverified input the judge weighs. GOAT-CEO's judge stays the
   single binding verdict (`check_review_gate.py`); rubric never writes to the gate-read verdict slot.
5. **No rubric Claude Code hooks in GOAT-CEO repos** — bootstrap with `rubric init --no-claude` (installs `.rubric/`
   + git pre-commit + the reuse index, but NOT rubric's SessionStart/`/rubric`/PostToolUse hooks, which would be a
   second grounding path + double-inject). The CEO runs `rubric check --changed` as a **deterministic gate step at
   integration** (`RUBRIC.GATE`), NOT as a real-time PostToolUse self-heal hook — which sidesteps the single sharpest
   risk (R-A below).
6. **Primitive-Ledger entry first.** Adopting rubric without a cleared §0 row would violate Rule 7's *procedure*
   even though it honors its spirit. P13 is that row.

### §I.2 — Integration map (a clean `INDEX-AVAILABLE` mirror)

| # | Where | Change | INDEX analog |
|---|---|---|---|
| 1 | `repo-registry.json` + `goat-ceo.md §1.1` schema | add `"rubric": true\|false` + `"rubricStatus": "RUBRIC-AVAILABLE"\|"RUBRIC-UNAVAILABLE"`; optional `"rubricConventions": "<shared-kb-path>"` for cross-repo standards sharing (no INDEX analog) | `index`/`tooling` booleans + `indexStatus` |
| 2 | `goat-ceo.md §1.2` intake | detect `.rubric/` + `rubric kb` responds → record status; bootstrap offer A/B/C where A = `rubric init --no-claude`. `ro-reference` repos are EXEMPT | the Codebase-Index detect + A/B/C bootstrap |
| 3 | `templates.md` §6/§7/§8 | add a `{RUBRIC_STATUS}` block: when AVAILABLE, Planner-pulled `rubric context` grounding is in the shared artifact; implementers also run `rubric check <changed>` before reporting complete | the `{INDEX_STATUS}` block |
| 4 | `protocols.md §D` / `goat-ceo.md` Phase 3→4 | `RUBRIC.GATE` — CEO runs `rubric check --changed` (or `enforce --no-llm`) on the merged diff; exit 0 → write the gate. Add to `EXPECTED-GATES.txt` ONLY for waves with ≥1 RUBRIC-AVAILABLE repo (else the Stop hook blocks on an absent optional gate). Under Workflow: a `TaskCompleted` rubric hook would NOT fire → express as a script stage (`run rubric check; throw on non-zero`), exactly like the test gate | `INDEX.GATE` (CEO-validated, no hook) — but rubric's is HARD (deterministic exit code) where INDEX's is SOFT |
| 5 | `goat-ceo.md` Phase 6 / Session Summary | `rubric measure --save` baseline at wave start; `--baseline` delta in the finalize report (gate-pass, complexity, SLOC) | none (net-new reporting surface) |
| 6 | `rules.md` (Rule 8/new Rule 9 + 2 HARD/SOFT rows), `roster.md` (Reviewer-C row, v2), §0/§B/§E here | doctrine rows for the grounding (SOFT) + gate (HARD, opt-in/target-repo) | Rule 8 + the index HARD/SOFT rows |

**Divergences from INDEX to honor:** (a) console script `rubric <cmd>`, NOT `python -m … --format json`; (b) **no
`--format json`** anywhere — parse stdout text or read the JSON files rubric writes (`measure --save`, `index`,
`codify --write`); (c) after `init`, pass `--kb .rubric/kb` on every call; (d) only `check`/`enforce` return
non-zero on violation; (e) a v2 rubric-reviewer must be EXEMPT from `check_toolcall_audit` (its evidence is a
subprocess, not Read calls).

### §I.3 — The complementary grounding merge (one artifact, fixed order)

```
agent-workspace/index-context.md   (written ONCE by the Planner in Phase 1; read-only downstream)
├─ § Architectural map & task routing      ← codebase-index `inject --ids <planner-selected>`   (the "where")
├─ § Existing components — REUSE these      ← rubric context  → ## Existing components            (symbol signatures)
├─ § Conventions to follow (MUST/should)    ← rubric context  → ## Conventions
└─ § Canonical exemplars — match this style ← rubric context  → ## Canonical exemplars
```

Path-string dedup: rubric is authoritative for **signatures**, codebase-index for **purpose/architecture**; never
print a path's signature twice. Token budget (~2–3k): map ≤1.2k, components ≤600, conventions ≤300, exemplars ≤900
(truncate exemplars first). Degraded modes: both-absent → direct Read/Grep (today's `INDEX-UNAVAILABLE`); one-absent
→ the present half only. rubric's own context/SessionStart hooks are disabled so this stays the sole grounding path.

### §I.4 — Scope: v1 (build) vs v2 (defer)

- **v1 (safe, deterministic, zero added LLM cost):** P13 ledger row + RUBRIC-AVAILABLE registry flag + intake
  detection/bootstrap + Planner grounding-merge + CEO-run `RUBRIC.GATE` + `measure` deltas + doctrine rows.
  Delivers the full "ground before write, gate before merge" loop with zero self-heal risk.
- **v2 standards-review lens — BUILT (2026-06-15), as Reviewer C.** Head-to-head analysis (two deep-dive agents)
  found GOAT-CEO's Phase 5 (correctness + test-integrity + acceptance-criteria) and rubric's verification
  (standards/conventions/reuse) are **orthogonal targets — not substitutes**; replacing one with the other would
  delete a whole verification axis. So Reviewer C **adds** rubric's standards verification, RUBRIC-AVAILABLE repos
  only, without touching A/B. **Decision change vs the v1 plan:** Reviewer C runs rubric's OWN `rubric enforce
  --verify` (its gate + grounded review + mechanical span-check + 3-judge ensemble) — NOT a `team-verifier`
  re-reading the KB — because the operator explicitly chose to *use rubric's verification system* where rubric is
  enabled. Cost accepted: `enforce --verify` runs rubric's `claude -p` path (≈1 review call/LLM-rule + 3 judge
  calls/finding, per file, serial). The judge composes Review C: `blocking_violations` = FAIL-facts;
  `verified_advisory` = an already-verified lens. Reviewer C is naturally audit-exempt (`reviewer:"C"`).
  Wiring: templates §12a + §14 + §17 kernel; `goat-ceo.md` Phase 5; `roster.md`; a `rules.md` row.
- **v2 span-check graft — BUILT (2026-06-15).** Grafted rubric's mechanical span-check onto GOAT's A/B
  *correctness* reviewers: they now emit `cited_spans:[{file,line,quote}]`, and `.claude/hooks/check_span_validity.py`
  (`SubagentStop`) opens each cited span and blocks the verdict (exit 2) if it does not exist in the file
  (whitespace-normalized). This is the one rubric mechanism strictly superior even for correctness — GOAT's
  read-floor counts *that* ≥5 reads happened, not *that* a cited `foo.py:213` resolves. Guards against false
  blocks (parses only the reviewer's own assistant output, skips placeholders/prompt-echo, requires a substantive
  quote, fail-open). Tested across valid / fabricated / file-not-found / placeholder / prompt-only / trivial /
  exempt / whitespace cases. Judge/critic/Reviewer-C exempt.
- **v2 self-heal gate — BUILT (2026-06-15).** `.claude/hooks/rubric_heal_gate.py` wraps `rubric check` with a
  per-file heal CAP (default 2): a blocking violation feeds back to Claude to self-heal in real time, but after
  the cap it DEGRADES to advisory (logs to `RUBRIC-DEGRADED.md` for the CEO's `RUBRIC.GATE` to catch) instead of
  thrashing the implementer past `maxTurns:30` (the R-A risk). TARGET-REPO opt-in: copied into a repo's
  `.claude/hooks/` and wired as a PostToolUse `Edit|Write` hook for repos that want in-loop heal; the default
  flow stays the CEO-run `RUBRIC.GATE` at integration. Tested: heal×2 → degrade; clean clears the counter;
  non-code exempt; fail-open. Has a `RUBRIC_HEAL_TEST_FORCE` test seam.
- **v2 codify loop — BUILT (doctrine).** At session close, for RUBRIC-AVAILABLE repos the CEO MAY run
  `rubric codify --draft --write` over the changed files to propose KB standards from recurring verified findings
  (lands in `.rubric/proposals/` for HUMAN approval — never auto-merged) and surfaces the proposals in the session
  summary. Opt-in (uses rubric's `claude -p`); advisory. Wired in `goat-ceo.md` Phase 6.
- **v2 cross-repo conventions — BUILT (doctrine).** Optional `rubricConventions` registry field lets several `rw`
  repos in a group point at ONE shared conventions KB (rubric's conventions plane is portable); the rubric
  commands pass `--kb <shared-path>`. Wired in the `goat-ceo.md §1.1` schema + relationship-mapping intake.
- **All §I v2 items are now built.** Remaining is operational hardening only: soak rubric, author real per-repo KBs,
  and (optional) a TS/JS reuse-index extractor upstream in rubric for full Node coverage.

### §I.5 — Caveats & top risks

- **Node coverage is partial:** rubric gives Node repos a gate (ast-grep + ESLint-via-`.rubric/tools.json` config)
  and language-agnostic conventions/exemplars, but **no symbol-level reuse index** (Python-only today). Full value
  on Python; partial on Node. Honest framing required in the docs.
- **Seed KB is TS-first** → target repos must supply their own KB to get real value; rubric ships the mechanism,
  not your standards.
- **2 days old, zero soak** → pin a commit; depend on the stable CLI surface, not the hook bridge.

| Risk | Mitigation |
|---|---|
| **R-A: self-heal loop blows `maxTurns:30`.** rubric's PostToolUse gate exits 2 → model re-edits → re-fires; on an un-satisfiable rule the implementer thrashes, trips the turn budget, dies mid-batch, then `check_artifacts` blocks its stop → escalation cascade. | v1 does NOT install rubric's PostToolUse hook in-pipeline; the gate runs as a CEO deterministic step at integration. v2's native gate needs a per-file heal cap (≤2 cycles, then degrade to advisory). |
| **R-B: two adversarial-verify stacks → cost blowup + verdict collision.** | Run rubric WITHOUT `--verify` in-pipeline; rubric Review = advisory lens, rubric Gate = fact; GOAT-CEO's judge is the single skeptic. |
| **R-C: Python-only rubric on a Node repo / not on PATH.** | Host-tool install (decision 2); record RUBRIC-AVAILABLE per repo; degrade gracefully. |
| **R-D: KB / reuse-catalog staleness surfaces phantom symbols.** | Grounding artifact built once at Phase 1 (read-only that run); re-run `rubric index` in the Phase-4 index-update step so the catalog refreshes with the markdown indexes. |
| **R-E: version coupling (rubric v0.0.1 + harness hook semantics).** | Pin rubric; keep its hooks OUT of GOAT-CEO sessions (`init --no-claude`); depend only on the CLI surface. Both systems fail-open, so a contract break degrades to no-op. |

### §I.6 — Decisions resolved (2026-06-15); v1 BUILT

- ✅ **Host-tool install** model confirmed — rubric is installed once in the operator env and run against any target repo via `--repo`.
- ✅ `RUBRIC.GATE` is **conditional** — added to `EXPECTED-GATES.txt` only for waves with ≥1 RUBRIC-AVAILABLE repo, so the Stop hook never blocks on an absent optional gate.
- ✅ `measure` deltas **ship in v1** (Phase 6 finalize report).

**v1 landed (2026-06-15):** `rubric`/`rubricStatus` registry fields + Step 1.2 detection/bootstrap (`rubric init --no-claude`) + `{RUBRIC_STATUS}` grounding block in the implementer template (per-agent: runs `rubric context` before writing, reports `rubric check` violations) + a CEO-run conditional `RUBRIC.GATE` at Phase 3 integration + `rubric measure` baseline/delta in Phase 6 + doctrine rows in `rules.md`. v2 items (LLM review-lens via `team-verifier`, native self-heal gate, codify loop, cross-repo conventions) remain deferred.

Note: in the CEO pipeline each implementer assembles its own grounding (runs `inject` + `rubric context` in its own context window — no shared file, so no competing-path concern). The single-`index-context.md`-artifact merge in §I.3 applies to the goat-team single-repo planner path; either way rubric's own context/SessionStart hooks stay disabled (`init --no-claude`).

> **Cross-link to §J (rubric ← research):** a research subject run through the Research System can produce
> verified, *sourced* coding-standard claims that distill into candidate rubric rules/exemplars via rubric's
> `codify` / `.rubric/proposals/` flow — making rubric conventions evidence-backed ("we enforce X because
> [stored source span]") rather than hand-asserted. Still human-approved (rubric never auto-merges proposals;
> the Research System certifies faithfulness, not truth). See §J.1.

---

## §J — Optional integration: Research System (RESEARCH-KB-AVAILABLE)

> **Status:** design of record (2026-06-15), v1 being built. **Vendored engine:** `tools/research-system/`
> (commit `34ff457`, the 4.6M `Research/` corpora excluded). **Ledger:** P14. Backed by a 4-agent analysis pass.

The Research System is an auditable **external-document** research engine: capture web/PDF sources in full →
decompose → answer with claim-level **exact quotes** → cross-model verify (mechanical quote-match + 3-judge
ensemble) → **abstain** rather than confabulate → deterministic synthesis. It adds a FOURTH, disjoint knowledge
plane: Codebase-Index = internal code ("where"); rubric = conventions/reuse ("what to call"); **Research KB =
external research ("why / prior art")**. It does NOT read code or verify repos.

Its genuine, non-redundant value over the built-in `deep-research` skill and GOAT-CEO's Phase-2 research is
**persistence + mechanical provenance**: a re-queryable corpus where every claim resolves to a verbatim span in
a stored source, with honest abstention. It certifies **claim-level traceability to a stored source (faithfulness
+ provenance), NOT truth** — a claim faithfully grounded in a wrong source still passes; source quality and
correctness stay a human judgment. (Doctrine must say "traceable to source," never "100% verifiable/true".)

### §J.1 — The two payoff mechanics (why a 4th plane earns its keep)

1. **Capture-always, verify-on-demand (the compounding win).** The technical researcher CAPTURES every external
   source it consults into the shared KB (`run_capture` — FREE, no LLM: full source text + provenance), so the KB
   grows comprehensively at near-zero cost. The expensive claim-level VERIFY (`run_research`) runs on demand —
   when a subject warrants a verified synthesis, or when a query needs verified claims (it runs over already-captured
   sources, no re-fetch). Reuse-before-research: a VERIFIED subject (`synthesis.md` present) → cite + SKIP the
   online run; a CAPTURED-but-unverified subject → verify over stored sources rather than re-fetch. Over sessions
   the KB compounds and online runs get rarer.
   **Verified vs captured is RECORDED, not guessed** (your sources may be a mix): the engine stamps every claim
   with a `verdict` (`supported`/`overreach`/`unsupported`/`pending`); `synthesis.md` contains ONLY `supported`
   claims; a subject is VERIFIED iff it has `claims.jsonl`/`synthesis.md`, else CAPTURED-but-unverified (only
   `sources/`). ONLY `verdict: supported` claims may back a finding or be SINGLE-SOURCE-exempt — raw captured
   sources are unverified until `run_research` runs. (The abstention gate then decides "enough supported claims to
   answer?" — the threshold is the gate, not a guess.)
2. **Research → rubric standards (the cross-feature loop; see §I).** A subject like "evidence-based error-handling
   conventions for Python services" yields verified, SOURCED claims; those distill into candidate rubric
   rules/exemplars via rubric's `codify`/`.rubric/proposals/` flow, making rubric conventions evidence-backed with
   provenance instead of hand-asserted. Human-approved (rubric never auto-merges; faithfulness != truth). This is
   the one place the external-research plane touches code quality directly.

### §J.2 — Load-bearing decisions
1. **Opt-in, standalone — NOT auto-fired in a phase.** `claude -p` capture/verify ~ 60-100 serial calls
   (~$1-3/question). The technical researcher invokes it deliberately for persist-worthy subjects; throwaway
   lookups stay on WebSearch/`deep-research`.
2. **Backend via the `LLMClient` seam — v1 uses the Claude *subscription*.** The default `ClaudeCLIClient`
   calls `claude -p` (the SAME subscription GOAT-CEO runs on — no per-token cost, full verification quality).
   The engine runs as a separate Python process, so it CANNOT reuse the orchestrator's in-session model; the
   realistic backends are `claude -p` (subscription), the per-token Anthropic API, or a local server. Because
   `run_research(layout, question, llm, ...)` takes the client as a parameter, the backend is swappable without
   engine changes (e.g. a local+Claude *hybrid* — local for decompose/answer, but keep the 3-judge verify on a
   strong model or the "verified" guarantee degrades). The only downside of the default is subprocess nesting
   overhead (~60–100 serial `claude -p` spawns when an agent drives it) — accepted because runs are opt-in and
   gated to "worth persisting." (Earlier drafts said "route through GOAT's own model"; that was imprecise — a
   separate process can't tap the in-session model; `claude -p` IS how it uses the subscription.)
3. **Shared, cross-repo KB** at `<repo-root>/research-kb/` (gitignored like `logs/`). Research isn't owned by one
   repo — the divergence from per-repo INDEX/rubric siting, and what makes findings reusable across repos/sessions.
4. **Out of the per-write grounding path.** A Phase-2 *input* (read on demand by the technical researcher), never
   injected into every implementer like index/rubric — keeps the planes disjoint (no third competing grounding block).
5. **All-SOFT, NO `RESEARCH.GATE`.** Research is additive context, not a correctness gate. Findings feed the
   EXISTING 5-condition convergence gate + Phase-5 judge as pre-verified inputs, EXEMPT from SINGLE-SOURCE
   escalation (cross-model quote-match + ensemble already satisfies independent corroboration).
6. **Vendor engine only** (`git archive HEAD :!Research`); no console-script -> run
   `python scripts/run_research.py --research-root <kb>` from `tools/research-system/`.

### §J.3 — v1 integration map (RESEARCH-KB-AVAILABLE, mirrors §I)

| # | Where | Change |
|---|---|---|
| 1 | `repo-registry.json` + `goat-ceo.md §1.1` | `researchKb` bool + `researchKbStatus` + shared `researchKbRoot` |
| 2 | `goat-ceo.md §1.2` intake | detect `tools/research-system` importable + `research-kb/` creatable; A/B bootstrap; `ro-reference` EXEMPT (may READ the shared KB) |
| 3 | `templates.md §7` (technical researcher ONLY) | `{RESEARCH_KB_STATUS}` block: reuse-before-research -> drive `run_capture`/`run_research` for persist-worthy subjects -> cite `{slug, source_id, quote, verdict}` |
| 4 | `templates.md` critic + judge | note: Research-System findings are pre-verified -> not SINGLE-SOURCE |
| 5 | `research-kb/` + `.gitignore` + `INDEX.md` | shared corpus root (gitignored); subject catalog the researcher greps before researching |
| 6 | `rules.md` (SOFT rows) + `§0` P14 + this §J | doctrine + design-of-record + ledger |
| 7 | `§I` cross-link | research -> rubric codify (the §J.1.2 loop) |

### §J.4 — caveats & risks
- **Zero soak** (built 2026-06-13/14, no remote) -> pin the commit.
- **`claude -p` subscription cost + subprocess nesting** on capture/verify-heavy runs -> opt-in, gated to "worth
  persisting," cost-flagged. v1 uses the subscription (default `ClaudeCLIClient`); a per-token API or local+Claude
  hybrid is a swap via the `LLMClient` seam if cost/nesting ever bites.
- **Web discovery unreliable** (`discover.py` LIVE CAVEAT) -> pre-supply URLs for headless runs; `--discover` is opportunistic.
- **`requires-python >= 3.11`**; capture can fail on JS/paywall (recorded as `capture_status`, visible to the gate).
- **Three-KB fragmentation** -> mitigated by keeping the research corpus OUT of the grounding path (decision #4).
- **Strains "no app code"** -> second vendored Python tool; accepted (P14 cleared composition, like rubric P13).
