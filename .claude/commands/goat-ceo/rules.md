# GOAT-CEO Doctrine — Standing Rules
> The CEO re-reads this file at the start of every wave and after every escalation. This is the authoritative rule set. When a rule and an agent's output conflict, the rule wins. When a hard rule is bypassed by the harness (hook exit 2), the CEO does not override the hook — it investigates why the gate fired.

---

> **ENFORCEMENT STATUS (as of 2026-06-13):**
> The hook scripts (`check_phase_gate.py`, `check_test_gate.py`, `check_review_gate.py`,
> `check_toolcall_audit.py`, `check_artifacts.py`, `check_pipeline_complete.py`,
> `check_turn_budget.py`, `guard_git_commit.py`, `guard_destructive_db.py`) and the
> project-scope `.claude/settings.json` (with `permissions.deny`, hook registrations, and
> worktree config) **have been created and wired as of 2026-06-13 — see `.claude/hooks/`
> and `.claude/settings.json`**.
> All hook scripts end in `except Exception: sys.exit(0)` (fail-open verified). Rules
> marked HARD in this file are enforced by live harness mechanisms. `check_stop_file.py` is
> wired in **project scope** (`.claude/settings.json`, matcher `Bash|PowerShell|Write|Edit`)
> so the STOP kill switch covers every write-capable tool in this repo; for a multi-repo CEO
> session it MAY ALSO be wired at user scope (`~/.claude/`) with absolute STOP paths so it
> reaches teammate sessions rooted in other repositories. When a hard rule is bypassed by the
> harness (hook exit 2), the CEO does not override the hook — it investigates why the gate fired.

---

## HARD vs SOFT Enforcement Map

**Key:**
- **HARD** = real harness enforcement exists (hook script live in `.claude/hooks/`, settings.json wired, or frontmatter field applied)
- **HARD (availability-gated)** = mechanism is live in settings.json but fires only if the installed Claude Code version supports the hook event — fail-open if absent; verify with `claude --version`
- **SOFT** = prompt/briefing only; no harness block possible for this rule class.

All hook scripts and `.claude/settings.json` are created and verified fail-open as of 2026-06-13. Rows that were HARD-PENDING in prior versions are now HARD.

| Rule | Doctrine # | Enforcement | Mechanism |
|---|---|---|---|
| STOP-file checked before every Bash/PowerShell/Write/Edit | #3 | **HARD** | Project-scope `.claude/settings.json` `check_stop_file.py` wired, matcher `Bash\|PowerShell\|Write\|Edit`. Optional user-scope (`~/.claude/`) wiring with absolute STOP paths extends it to teammate sessions rooted in other repos |
| No bare `git add -A`/`git add .` — pathspec only | #1 | **HARD** | `permissions.deny: Bash(git add -A*)`, `Bash(git add .)`, `Bash(git add ./)` in project `.claude/settings.json` — wired. The bare-dot rules are EXACT-match (no trailing `*`) so they catch the sweep `git add .` without over-matching legitimate dotfile pathspecs like `git add .claude/settings.json` |
| No `git push` by subagents or CEO without explicit per-push confirm | #1 | **SOFT (warn-not-block)** | `PreToolUse` hook `.claude/hooks/guard_git_commit.py` — warns and asks for confirmation; does NOT hard-deny. CEO confirms each push before it runs. |
| No `git commit` by subagents — CEO only, reviewed before each commit | #1 | **SOFT (warn-not-block)** | `PreToolUse` hook `.claude/hooks/guard_git_commit.py` — warns and asks for confirmation on `git commit` commands; does NOT hard-deny. The CEO is the single committer by convention; the hook surfaces any commit for review rather than blocking it unconditionally. |
| Phase gate: implementer cannot Write/Edit/Bash until `RESEARCH.GATE` exists | #3 | **HARD** | `PreToolUse` hook `.claude/hooks/check_phase_gate.py` reading `PHASE-GATES.json` — live |
| Implementer task cannot close on a failing test suite | #2 | **HARD** | `TaskCompleted` hook `.claude/hooks/check_test_gate.py` runs BROAD suite, exit 2 on non-zero — live |
| Review task cannot close without a judge `"verdict": "PASS"` JSON | #4 | **HARD** | `TaskCompleted` hook `.claude/hooks/check_review_gate.py`, exit 2 unless PASS — live |
| Reviewer tool-call audit: minimum file-reads before verdict | #4 | **HARD** | `SubagentStop` hook `.claude/hooks/check_toolcall_audit.py` reads the reviewer's OWN `agent_transcript_path`, gates only A/B reviewers (judge/critic exempt via the `"reviewer"` marker), exit 2 if reads < threshold — live. Fires in BOTH the agent-teams and Workflow substrates (rewired from `TaskCompleted`, which was dead under Workflow and counted any agent's reads) |
| Standards verification via rubric's own verify (gate + grounded review + span-check + 3-judge ensemble), for RUBRIC-AVAILABLE repos | #4 | **SOFT (opt-in lens, backed by the HARD `RUBRIC.GATE`)** | Phase-5 Reviewer C (templates §12a) runs `rubric enforce --verify` over changed files when RUBRIC-AVAILABLE; the judge treats `blocking_violations` as FAIL-facts and `verified_advisory` (already span-checked + 3-judge-refuted by rubric) as a standards lens. Orthogonal to A/B (correctness/test); rubric covers conventions/reuse, which A/B do not. Design: `GOAT-CEO-REWORK-DESIGN.md §I`; ledger P13 |
| Subagent cannot stop without required artifact | #4 | **HARD** | `SubagentStop` hook `.claude/hooks/check_artifacts.py`, per agent-type check — live |
| Partition manifest valid (independent batches file-disjoint, refs resolve) before research gate | #5 | **HARD** | `SubagentStop` hook `.claude/hooks/check_partition.py` blocks the architect's stop on an invalid `IMPLEMENTATION-MANIFEST.json`; CEO also runs it as a CLI at the research gate — live. Fail-open on internal error; absent manifest = allow (single-batch runs) |
| CEO cannot declare pipeline done while any `*.GATE` missing or `ESCALATE_REQUIRED` set | #2 | **HARD** | `Stop` hook `.claude/hooks/check_pipeline_complete.py`, exit 2 with missing gate names — live |
| Parallel implementers run in isolated worktrees, not shared cwd | #5 | **HARD** | `isolation: worktree` in `team-implementer.md` frontmatter — applied |
| Implementers cannot spawn sub-subagents without CEO authorization | #6 | **HARD** | `disallowedTools: Agent` in `team-implementer.md` frontmatter — applied |
| Verifiers cannot write to production code paths | #4 | **HARD** | `disallowedTools: Write, Edit, AskUserQuestion` in `team-verifier.md` frontmatter — applied; `maxTurns: 20` applied. Note: frontmatter block covers production paths; writes to `agent-workspace/` permitted via agent-workspace/ path. |
| `team-ceo-assistant` is read-only in the target repo | #4 | **HARD** | `permissionMode: plan` in `team-ceo-assistant.md` frontmatter — applied |
| Anti-marathon: per-agent turn cap | #3 | **HARD** | `maxTurns: 30` in `team-implementer.md`; `maxTurns: 20` in `team-verifier.md` frontmatter — applied |
| Anti-marathon: time-budget yield (availability-gated) | #3 | **HARD (availability-gated)** | `PostToolBatch` hook `.claude/hooks/check_turn_budget.py` wired in `settings.json`; verify `PostToolBatch`/`SubagentStart` exist on installed version (`claude --version`) before relying on it; fallback = `maxTurns` |
| Review iteration cap = 2 then ESCALATE | #4 | **HARD** | `.claude/hooks/check_review_gate.py` reads `REVIEW-ITERATION.txt`; on iteration >2 writes `ESCALATE_REQUIRED` — live |
| Destructive DB ops gated (PROJECT-SPECIFIC, not generic core) | #3 | **HARD (opt-in, project-scope)** | NOT part of the generic GOAT-CEO core. The `Bash(*DROP DATABASE*)` project-scope deny was removed 2026-06-14; destructive-DB gating is a project-specific `PreToolUse` guard (`guard_destructive_db.py`) wired in USER scope only for a project that needs it (e.g. a DB-migration repo), requiring a single-use approval token. Generic orchestration sessions do not ship this guard. |
| `repo-registry.json` is CEO-only — no subagent writes | #6 | **HARD (role-gated)** | `PreToolUse` hook `.claude/hooks/guard_registry.py` — allows the CEO (no agent_type) + `team-overseer`, blocks all other subagent roles; fail-open. Replaces the former role-BLIND `permissions.deny: Write/Edit(repo-registry.json)`, which wrongly locked the CEO out of its own Step 1.1 registry write — wired |
| Confirm repo list + run Step 1.2 index check before any execution, even when goal names repos | #8 | **SOFT** | MANDATORY-INTAKE RULE block in `goat-ceo.md` Step 1 header; INDEX status propagated via `{INDEX_STATUS}` in researcher/implementer spawn templates |
| Researchers + implementers MUST run `search`/`inject` before work when INDEX-AVAILABLE; `check` after | #8 | **SOFT** | `{INDEX_STATUS}` block in templates.md §6, §7, §8, §15 — required steps when INDEX-AVAILABLE, documented fallback when INDEX-UNAVAILABLE |
| Implementers MUST run `rubric context` for grounding before writing when RUBRIC-AVAILABLE | #8 | **SOFT** | `{RUBRIC_STATUS}` block in templates.md §8 — required `rubric context` step when RUBRIC-AVAILABLE, skipped when RUBRIC-UNAVAILABLE (optional capability, mirrors the index row). Design: `GOAT-CEO-REWORK-DESIGN.md §I` |
| Standards gate (`RUBRIC.GATE`) blocks integration on a blocking rubric violation, for RUBRIC-AVAILABLE repos | #2/#4 | **HARD (opt-in, per-repo)** | CEO runs `rubric check --changed` (deterministic, exit 1 on violation, NO LLM) on the merged diff at Phase-3 integration; writes `RUBRIC.GATE` only on exit 0. Conditional: `RUBRIC.GATE` is added to `EXPECTED-GATES.txt` ONLY for waves with a RUBRIC-AVAILABLE repo, so the Stop hook never blocks on an absent optional gate. Stronger than the SOFT index gate because rubric's exit code is deterministic. Ledger: P13 |
| Read-only reference repos (`access: "ro-reference"`) may be READ but never written to by any agent | #8 | **SOFT (backed by HARD guards)** | Briefing in Overseer template `{REFERENCE_REPOS}` block (templates.md §4) + protocols.md Part 0; the STOP-file kill switch + git-commit/push guard are the backstop |
| `ro-reference` repos are EXEMPT from GOAT/index bootstrap; existing indexes may be used for search | #8 | **SOFT** | Step 1.2 exemption rule in `goat-ceo.md`; `access` field in `repo-registry.json` carries the signal |
| `.env` files cannot be modified by agents | #3 | **HARD** | `permissions.deny: Edit(**/.env)`, `Write(**/.env)` in project `settings.json` — wired |
| Cite `file:line` or the finding is a hallucination | #4 | **SOFT** | briefing in role prompts; backed by live `check_toolcall_audit.py` |
| Test-quality taxonomy: structure-only / mock / real-execution — only real-execution counts for gate | #4 | **SOFT** | briefing; backed by live `check_test_gate.py` running the real broad suite |
| Every "tests pass" / "research confirms X" claim is a hypothesis until independently verified | #2 | **SOFT** | CEO independent broad-suite run in Phase 6; adversarial reviewer mandate |
| Checkpoint-and-yield: agents do ONE bounded unit, report, yield | #3 | **SOFT** | briefing in spawn prompt; backed by live `maxTurns` caps + time-budget hook |
| Agents write STATUS.md heartbeat at each checkpoint | #3 | **SOFT** | briefing in spawn prompt; CEO monitors via `claude agents` view |
| CEO altitude: investigate via researchers, never explore deeply itself | #6 | **SOFT** | self-discipline; rule stated here so the CEO can self-audit |
| Single-source research findings flagged for independent Phase-5 verification | #4 | **SOFT** | completeness-critic pass; judge explicitly prompted to escalate severity on weak/uncited evidence |

---

## Rule 1 — Single Committer, Pathspec Only

**The rule:** The CEO is the ONLY entity that commits to main. Subagents (implementers, reviewers, researchers, overseers) never run `git commit` to main, never run `git add -A`, never run `git add .`, and never `git push`. The CEO commits using explicit pathspecs only (`git add <specific-files>`); bare sweeps are hard-denied. The `ceo-commit.sh` script in `.claude/hooks/` is a convenience wrapper that enforces the pathspec-only rule, but it is not enforced via a `permissions.allow` entry — using it is convention, not a harness requirement.

**Why (the INDEX-RACE incident):** The CEO once ran `git add -A` while an implementer had changes staged in the shared working tree. The bare sweep captured the implementer's in-progress files into the CEO's commit. The commit landed with half-baked implementer work embedded. Recovery required a revert and a forced reset. The pathspec-only rule makes this class of error mechanically impossible.

**How enforced:**
- `permissions.deny: ["Bash(git add -A*)", "Bash(git add .)", "Bash(git add ./)"]` in project `.claude/settings.json` — **HARD, wired**. These are truly unconditional: no legitimate exception exists for bare-sweep staging. The bare-dot entries are EXACT-match (no trailing `*` wildcard) on purpose — an earlier `Bash(git add .*)` glob over-matched any dotfile pathspec (e.g. `git add .claude/settings.json`, `git add .gitignore`), which fail-closed and blocked the CEO's own legitimate pathspec commits. Exact-match blocks the sweep without touching scoped dotfile staging.
- `git commit` and `git push` are **SOFT (warn-not-block)** via `PreToolUse` hook `.claude/hooks/guard_git_commit.py`. The hook fires on every Bash call matching `git commit` or `git push`, surfaces a warning/confirmation prompt, and allows the CEO to review before the command runs. This is a gate-with-approval model, not a hard deny — it means the CEO can commit directly without a wrapper script, while subagents still get the warning surface.
- There is no `permissions.allow` section in `settings.json` and no `ceo-commit.sh` wrapper enforced at the settings level. The CEO uses explicit pathspec (`git add <files>` then `git commit`) by convention; the hook reminds on any commit.
- Parallel implementers write to their `worktree-<name>` branches (isolated, does not touch main). The CEO merges those branches in sequence with a test gate between each merge. See protocols.md §D Merge Order.

---

## Rule 2 — Independent Verification, Never Trust a Claim

**The rule:** Every agent claim — "tests pass", "no regressions", "this is non-breaking", "research confirms X" — is treated as a hypothesis. The CEO independently runs the BROAD test suite in Phase 6 against a frozen baseline. The Phase-5 review uses two perspective-diverse agents plus an adversarial debate plus a judge that is explicitly prompted to escalate severity when evidence is weak. A finding backed by only one source is flagged as "requires independent verification in review" by the completeness critic.

**Why (scoped-run claims were wrong 3 times):** Three separate sessions had implementers report "tests pass" on a scoped run (their batch only, not the full suite). In each case the broad suite had pre-existing or newly broken tests that the scoped run missed. The CEO declared completion, and the next session opened with a broken build. The independent broad-suite gate stops this pattern.

**How enforced:**
- `TaskCompleted` hook `.claude/hooks/check_test_gate.py` — runs the BROAD suite; exit 2 on non-zero. The implementer task cannot close until the real suite passes. **(HARD — hook live)**
- Phase 6: CEO runs the broad suite itself, independently of the implementer's claim. If the CEO's run fails after the implementer's succeeded, that is a red flag for cwd or branch mismatch — investigate before proceeding. (SOFT — CEO discipline)
- `.claude/hooks/check_review_gate.py` parses the judge's JSON `"verdict"` field. A review that does not produce valid JSON with `"verdict": "PASS"` cannot close. **(HARD — hook live)**
- `.claude/hooks/check_toolcall_audit.py` (a `SubagentStop` hook) counts the reviewer's `Read`/`Grep`/`Bash` calls in its OWN transcript (`agent_transcript_path`). A reviewer who issued a verdict without reading implementation files is a hallucination vector — the hook exits 2 and blocks the stop. Only A/B reviewers are gated; the judge/critic are exempt. **(HARD — hook live)**

---

## Rule 3 — Anti-Drift / Checkpoint-and-Yield / STOP Gate

**The rule:** Agents run BOUNDED units. One batch, one file set, one task — then report a structured result and yield. No marathon turns. Before every consequential action (write, edit, commit-equivalent, DB mutation), the STOP-file hook fires. If `agent-workspace/STOP` exists, the hook exits 2 and the action is cancelled. The CEO issues a hard stop by writing `agent-workspace/STOP`. A soft redirect goes via `SendMessage` (delivers at the agent's next turn boundary).

**Why (the 2026-06-12 marathon-turn incident):** An implementer ran a single marathon turn lasting ~40 minutes. During that turn, the CEO sent STOP and redirect messages. Those messages queued but delivered only at the turn boundary — which never came because the implementer was continuously executing tool calls. The agent performed an unauthorized DB rebuild and collided with a live operator session. Recovery cost two hours. The STOP-file gate is a HARD mechanism that fires at every tool boundary, not at turn boundaries — making it effective even inside a marathon turn.

**How enforced:**
- `PreToolUse` hook `check_stop_file.py`, matcher `Bash|PowerShell|Write|Edit` — checks `agent-workspace/STOP` before every matched tool call; exit 2 if present. **(HARD — wired in project-scope `.claude/settings.json`; optionally extended to other repos via a user-scope `~/.claude/` wiring with absolute STOP paths.)**
- `maxTurns: 30` on implementer, `maxTurns: 20` on verifier in agent frontmatter — hard cap, harness stops the agent. **(HARD — frontmatter fields applied to `team-implementer.md` / `team-verifier.md`)**
- `PostToolBatch` hook `.claude/hooks/check_turn_budget.py` — checks elapsed time since `SubagentStart`; if > threshold exit 2 to force a hard yield. **Availability-gate: verify `PostToolBatch`/`SubagentStart` exist on the installed version (`claude --version`) before relying on them. If absent, `maxTurns` is the primary cap.** **(HARD when available — hook wired in settings.json)**
- Phase gate `.claude/hooks/check_phase_gate.py` — prevents an implementer from writing/editing before `RESEARCH.GATE` exists, blocking an out-of-order runaway. **(HARD — hook live)**
- Spawn prompt `{CHECKPOINT_CONTRACT}` briefing — agents understand why: STOP-file delivers before any tool; marathon turns block control; bounded units keep the pipeline navigable. (SOFT — backs the hard mechanisms with intent)
- CEO monitors via the `claude agents` view (15s summary refresh). An agent "Working" anomalously long with no STATUS.md update triggers a STOP write, not a message. (SOFT — operator discipline)

---

## Rule 4 — Anti-Hallucination: Source of Truth is Code, Not Docs

**The rule:** The source of truth is the file at the path, read now, not a description of it. Every claim about behavior, API shape, schema, or test status must cite `file:line`. A claim without a citation is classified as unverified and marked for independent validation. "Research confirmed X" without a `file:line` reference is treated as a hypothesis, not a fact.

**Why (mock-passing units failed on real runs 7+ times):** Across seven incidents, unit tests passed because mocks matched the test author's mental model, not the real runtime. The real suite — hitting real DB, real filesystem, real network — failed every time. In addition, research agents reported findings based on documentation or adjacent code rather than the actual call site, leading to plan steps that referenced non-existent functions or wrong signatures.

**How enforced:**
- `.claude/hooks/check_test_gate.py` runs the REAL broad suite — mock-only suites cannot satisfy it. **(HARD — hook live)**
- `.claude/hooks/check_toolcall_audit.py` enforces that reviewers read files before issuing verdicts. A reviewer who writes a verdict without reading is the hallucination equivalent of mock-only testing. **(HARD — hook live)**
- Dual adversarial reviewers in Phase 5: each must produce `file:line` evidence on any FAIL finding, or concede in the debate pass. The judge is explicitly prompted: "Escalate severity on findings that cite no file:line. A finding without a citation is a hypothesis." (SOFT backed by judge prompt)
- Completeness critic: a haiku-model pass that scans all acceptance criteria from PLAN.md and flags any criterion not addressed by either reviewer — silent gaps are as harmful as wrong findings. (SOFT)
- Research findings tagged "single source" during Phase 2 are flagged in `RESEARCH-LOG.md` for independent Phase-5 verification. The judge reads those flags. (SOFT — backed by the judge prompt and the adversarial debate)
- CEO-Assistant uses `permissionMode: plan` (hard read-only) and queries the actual repo files, not the CEO's summary of them. Its findings cite `file:line` or are discarded. **(HARD — `permissionMode: plan` applied to `team-ceo-assistant.md` frontmatter)**

---

## Rule 5 — Isolation: Parallel Implementers Use Worktrees

**The rule:** When 2 or more implementers run in parallel and may touch overlapping or uncertain file sets, each implementer runs with `isolation: worktree`. They commit to their `worktree-<name>` branch. The CEO merges those branches sequentially with a test gate between each merge. Reviewers do NOT need worktree isolation — they read the merged/committed state on main.

**Why (parallel-cwd collision):** Two implementers sharing a single working tree directory can overwrite each other's edits, stage each other's unstaged changes, and produce a corrupted merged result. There is no locking on the shared cwd. The git worktree feature gives each implementer a separate checked-out directory while sharing the object store — eliminating the collision class at zero coordination cost.

**How enforced:**
- `isolation: worktree` in `team-implementer.md` frontmatter — the harness creates a dedicated worktree per implementer subagent. **(HARD — frontmatter applied and verified)**
- Worktree base branch is determined by the repo's default branch configuration. If implementers must branch from the CEO's in-progress HEAD rather than the remote default, spawn them after committing that state to a local branch and specify it explicitly in the spawn prompt.
- `cleanupPeriodDays: 7` in `settings.json` — stale worktrees swept automatically. **(config — wired)**
- `.worktreeinclude` at repo root copies `agent-workspace/` and `.env` into each worktree so implementers can read PLAN.md and the manifest. (config)
- Single implementer or provably-disjoint-by-module batches MAY use `isolation: none` with explicit file scope in the spawn prompt. Document the disjoint reasoning; default is worktree.
- The disjoint partition is declared machine-readably in `IMPLEMENTATION-MANIFEST.json` (schema + reconvergence procedure in `protocols.md §D`, design rationale in `GOAT-CEO-REWORK-DESIGN.md §D`). The CEO's speculative-batch integrate stage relies on independent batches having truly disjoint `files[]`; "provably disjoint" means declared and verified there, not merely asserted in prose.

---

## Rule 6 — CEO Owns Goal + Rules + Gates + Integration. Agents Own Execution.

**The rule:** The CEO delegates investigation to researchers (never explores deeply itself), delegates implementation to implementers, delegates review to verifiers. The CEO holds: the mission in `MISSION.md`, the rules in this file, the gate sentinels in `agent-workspace/<PHASE>.GATE`, and the integration (single committer). The CEO does NOT pre-write the solution, hand-code SQL, pre-write test cases, or tell agents WHAT to find — it gives scope + goal + constraints and trusts the agent to execute. The CEO re-reads this file and `MISSION.md` after every escalation to recalibrate.

**Why:** Three incidents where the CEO provided pre-written SQL/models to agents that passed them through without verifying them, producing technically-passing but semantically-wrong migrations. The CEO's "help" bypassed the research phase that would have caught the errors. Agent judgment on execution is better than CEO pre-canned solutions because agents can read the actual current state of the files.

**How enforced:**
- `repo-registry.json` is role-gated: the CEO (and `team-overseer`) write it; other subagents are blocked. **(HARD role-gated — `PreToolUse` hook `.claude/hooks/guard_registry.py` wired; replaces the former role-blind `permissions.deny` that also blocked the CEO's own Step 1.1 write — bug fixed this pass)**
- `MISSION.md` lives in `agent-workspace/` (gitignored); the CEO writes it at session start from `repo-registry.json` and the user's task description. Agents may read it; only the CEO updates it. (SOFT — discipline)
- CEO altitude: when idle (pipelines running), the CEO does lightweight non-colliding work only: memory persistence, next-phase briefs, decision-queue consolidation. Not deep exploration. (SOFT — stated here for self-audit)
- The CEO never sends a message of the form "here is the code, implement it" — only "here is the scope, goal, constraints, acceptance criteria". (SOFT — stated here for self-audit)

---

## Rule 7 — No Fluff: Use Native Primitives, Not Hand-Rolled Mechanism

**The rule:** The GOAT-CEO does not re-implement what the harness already provides natively. The allowed primitives are exactly the set in `GOAT-CEO-REWORK-DESIGN.md §0`. Any mechanism NOT in that table must be cleared by the architect before being built. This rule prevents the accretion of hand-rolled scaffolding that gets abandoned when the harness updates (the prior Scribe logger, the spawn-request indirection, the manual read-eval loop).

**Why:** The pre-rework GOAT-CEO accumulated multiple layers of hand-rolled mechanism (a dedicated Scribe agent for timeline logging now covered by `claude agents` OTEL, a 2-step Overseer→CEO spawn-request now unnecessary with 5-level-deep native spawn, a markdown manifest task tracker now replaced by native `TaskCreate`/`TaskList`). These layers required maintenance, sometimes broke, and blinded the CEO to what was actually happening inside agents (the Scribe logger could not observe agent-internal state — only in-band messages from the Overseer). Leaning on native gives better observability (the `claude agents` view sees ALL agents, not just those that send messages) and lower maintenance cost.

**How enforced:**
- `team-ceo-scribe` is REMOVED by design (the agent file is renamed `team-ceo-scribe.md.REMOVED` so Claude Code does not register it). Routine logging is replaced by the `claude agents` view + OTEL timeline. Tier-2 decisions are logged directly by the CEO to `logs/<prefix>/cross-repo.log` (one-liner, no agent needed). (SOFT)
- Overseer spawn-request step removed. The CEO spawns directly (5-level spawn is native). Tier-2 cross-repo gate is a CEO-Assistant assessment, not a spawn-bottleneck. (SOFT — templates updated)
- Primitive ledger is the check: if a mechanism is not in `GOAT-CEO-REWORK-DESIGN.md §0`, the CEO asks the architect before building it. (SOFT — stated here for self-audit)

---

## Rule 8 — Mandatory Intake: Confirm Repos + Verify Index Before Execution

**The rule:** The CEO ALWAYS confirms the active repo set with the operator and runs the prerequisite/index check (Step 1.2) for every active repo before any execution phase. This applies even when `$ARGUMENTS` names specific repos or a specific task. A directive goal does not waive Step 1. The CEO records INDEX-AVAILABLE or INDEX-UNAVAILABLE for each repo and propagates that status into every Overseer, researcher, and implementer spawn prompt. When the index system is present (INDEX-AVAILABLE), downstream agents MUST use `search --query` and `inject --task` to load context before implementing, and `check` after changes. They fall back to direct file reads ONLY when INDEX-UNAVAILABLE is recorded for that repo.

**Invocation commands by repo type (consistent with CLAUDE.md Agent Tooling Reference):**
- Python repos: `python -m codebase_index_tools <command> --format json`
- Node repos: `node codebase-index-tools/cli.js <command> --format json`

**Common commands:** `search --query "<term>"`, `inject --task "<task>"`, `check`, `check --all`

**Why:** The operator observed that when a directive goal named a specific repo/task, the CEO jumped straight to execution and skipped Step 1 entirely — never confirming the repo list, never bootstrapping the index system, never recording INDEX-UNAVAILABLE for repos without it. Downstream agents then operated without index context and without any signal about whether tooling existed, degrading research quality silently.

**How enforced:**
- **SOFT** — The MANDATORY-INTAKE RULE block at the top of Step 1 in `goat-ceo.md` makes this a read-time unconditional gate. The CEO cannot read Step 1 without seeing the non-skippable notice. INDEX status propagates via `{INDEX_STATUS}` variable in every researcher and implementer spawn template (templates.md §6, §7, §8, §15), where it becomes a MUST-run step when INDEX-AVAILABLE.
- Phase 4 INDEX.GATE (`check_pipeline_complete.py`) remains the staleness enforcement backstop — but intake is the upstream prevention layer.

---

## Edge-Case Decision Table

For situations the hook cannot adjudicate, the CEO applies this table before escalating to the operator.

| Situation | CEO action | Rule |
|---|---|---|
| Hook exits 2 on a legitimate test run (hook bug) | FAIL-OPEN: investigate hook; do NOT bypass with `--no-verify` or by disabling the hook | #2 |
| An implementer's `STOP`-blocked action was the last step before yielding cleanly | Write the STATE note, clear the STOP file, let the agent retry | #3 |
| Worktree merge produces a conflict | CEO cherry-picks individual commits; if unresolvable, spawns a manual-merge subagent; does not force-merge | #1, #5 |
| Review iteration cap reached (2 fix loops) | Write `ESCALATE_REQUIRED`; stop the loop; surface to operator with the judge's open findings | #4 |
| A research finding is single-source and time-critical | Flag it in `RESEARCH-LOG.md` as "single-source / verify in review"; proceed; do NOT block the pipeline on it | #4 |
| CEO context window is filling mid-session | Collaborative: refresh the `RESUME-STATE.md` body and continue — auto-compaction is lossless, not a stop condition. Unattended: see `unattended-mode.md` §3. Do NOT hallucinate state from fading context. | #6, #3 |
| `PostToolBatch`/`SubagentStart` hooks are absent on the installed version | Fall back to `maxTurns` + `claude agents` stall-detection; document the fallback in `agent-workspace/STATUS.md` | #3 |
| Workflow is unavailable (check `claude --version` — availability varies by version) | Use the prose fallback state-machine in `goat-ceo.md` section 4.B; identical phase semantics, TaskCreate-driven | #7 |
