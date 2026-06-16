# GOAT-CEO Hardening Plan — Response to External Review

**Status:** verification complete; remediation not yet started.
**Method:** every claim in the external review was checked against ground-truth source by
four independent verification agents (no claim taken on the reviewer's word). Evidence is
cited as `file:line`. This document records the verdicts and a prioritized plan.

The headline holds: **the system is strong and genuinely wired** — every hook in
`settings.json` resolves to a real, importable, fail-open script; the JSON is valid; the
bootstrap doc references only files that exist or that the CEO creates; vendored tools and
their extras are accurate. The findings are about *enforcement gaps* (gates that can falsely
pass), *doc/implementation mismatches*, and *public-consumer hardening* — not structural
breakage.

---

## 1. Verdict table (all 18 claims)

| # | Claim | Verdict | Key evidence |
|---|-------|---------|--------------|
| 1 | Implementer artifact gate falsely passes | **CONFIRMED** | `check_artifacts.py:62` runs `git log --oneline -1` (passes in any non-empty repo); comment "ahead of origin" is false. `record_agent_start.py:41` records only `time.time()`, no start-SHA |
| 2 | Verifier gate vs tool perms (deadlock) | **PARTIAL** | `team-verifier.md:8` removes Write/Edit; `check_artifacts.py:120` requires `REVIEW-LOG.md` file. But Bash remains (can write) + message-fallback documented (`team-verifier.md:15-18`) → real tension, not hard deadlock |
| 3 | Test gate inactive/weak | **CONFIRMED** | Fail-open on absent (`:38`), empty (`:51`), timeout (`:95`); `shell=True, cwd=REPO_ROOT` (`:54`) runs from GOAT-CEO root, not target repo. Partial mitigation: hollow-pass guard (`:84`) |
| 4 | Commit/push softer than docs imply | **PARTIAL** | `guard_git_commit.py:53,63` WARN (exit 0), don't block. `ceo-commit.sh:12-15` cites a `permissions.allow`/`git commit` deny pair absent from `settings.json`. (Softened: `settings.json:5` already documents the deny→hook switch) |
| 5 | Review gate doesn't verify PASS came from judge | **CONFIRMED** | `check_review_gate.py:64-73` returns the **last** fenced JSON with any `verdict`; never inspects `role`/`judge`. Docstring `:17` promises judge-attribution the code never enforces. Same role-blindness in `check_artifacts.py:52` |
| 6 | Reviewer read-count gameable | **CONFIRMED** | `check_toolcall_audit.py:28` counts `{Read,Grep,Bash,Glob}` equally by tool **name**; no tie to changed files. 5 `Glob` calls satisfy the floor |
| 7 | Span validation optional + line-agnostic | **CONFIRMED** | `check_span_validity.py:137` returns 0 if no spans found (dodge); `:151` substring-anywhere check; cited `line` only echoed in error, never validated |
| 8 | Partition checks only exact file overlap | **CONFIRMED** | `check_partition.py:86` exact set intersection; no case/`./`/directory/lockfile/shared-resource handling. Coordinator mismatch is warning-only (`:98`); only disjointness hard-blocks (`:125`) |
| 9 | STOP kill switch coverage | **CONFIRMED** | `check_stop_file.py:23` — single path: GOAT-CEO's own `agent-workspace/STOP`. Multi-repo teammate sessions uncovered unless manually user-scope-wired (self-documented `:10`) |
| 10 | No automated hook self-test suite | **CONFIRMED** | `goat-ceo.md:68-73` self-check exercises only interpreter + STOP probe + git-add dry-run. No `selftest_all.py`; other ~16 hooks assumed live |
| 11 | "Lossless resume" too absolute | **CONFIRMED** | "lossless" 11× (`README.md:44,309`, `rules.md:210`, `protocols.md:331`) vs capped/truncated injection (`inject_handoff_context.py:62-65,115`, `unattended-mode.md:167`). Facts-lossless, prose-lossy |
| 12 | No releases/versioning/CHANGELOG/doctor/compat | **PARTIAL** | No tags, no releases, no `CHANGELOG.md`, no doctor, no compat matrix — all confirmed. **LICENSE *does* exist** (MIT), so that sub-item is refuted |
| 13 | Doc claims conflict | **CONFIRMED** | (a) `README.md:62` "Cannot commit" vs `team-implementer.md:18` "Commit atomically"; **`README.md:70` "denied by permission rules" is itself wrong** — commits are warn-only. (b) `ceo-commit.sh:12-15` stale allow/deny. (c) `.md`/`.json` manifest split documented but applied inconsistently (single-repo `goat-team` never emits `.json`) |
| 14 | Secret-file protection too narrow | **CONFIRMED** | `settings.json:12-13` blocks only `**/.env` (won't even match `.env.local`). Missing `.env.*`, `.npmrc`, `.pypirc`, `secrets.json`, `*.pem`/`*.key`/`id_rsa`, `.aws/credentials`, `appsettings.Production.json` |
| 15 | git sweep bypass variants | **CONFIRMED** | Deny (`settings.json:9-11`) + hook (`guard_git_commit.py:37`) miss: `git -C <path> add -A`, `git add :/`, `git add -u`, `git add *`. The `-C` form can stage in **other repos** |
| 16 | Bash-only commit wrapper | **CONFIRMED** | `ceo-commit.sh:1` `#!/usr/bin/env bash` + bash-isms; no `ceo-commit.ps1`. Repo is Windows-primary |
| 17 | Read-only reference repos not path-protected | **CONFIRMED** | `rules.md:65` SOFT (briefing + STOP/git guards); no `READONLY-PATHS.json`, no per-path `Write/Edit` deny. Write to ref-repo path not mechanically blocked |
| 18 | Plan approval / intake are soft gates | **CONFIRMED** | `goat-ceo.md:56` "CEO behavioral convention, not a harness-enforced plan-mode lock"; `defaultMode:"plan"` not set. Honest, soft by design |

**Net: 16 confirmed, 2 partial, 0 refuted.** The two "partials" still confirm the core fact
(verifier *can* be blocked; commit/push *is* warn-only); they only soften the reviewer's
framing (deadlock / undocumented drift).

---

## 2. Wiring & runnability audit (independent)

**Can a fresh clone run this seamlessly? — Substantially yes.** No wiring defects: every
`settings.json` hook reference resolves to a real script; JSON parses; `$CLAUDE_PROJECT_DIR`
used consistently; all 19 python hooks exit 0 on empty/garbage stdin with no traceback;
vendored-tool extras (`rubric[gate,retrieval]`, `research-system[capture,retrieval,llm]`) all
exist in packaging. Three on-disk hooks are unwired **by design** (`guard_destructive_db.py`,
`rubric_heal_gate.py` — opt-in; `ceo-commit.sh` — a wrapper, not a hook).

**Environmental prerequisites / blockers (ranked):**

1. **(Medium) `python` must be on PATH.** Every hook invokes the literal string `python`. On a
   box where the interpreter is `py`/`python3` only, **all 19 hooks silently no-op (fail-open =
   allow)** and every HARD rule degrades to advisory. Documented + caught by the 1.0a self-check,
   but it is the single biggest "seamless" risk on a new machine.
2. **(Medium) Requires `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` and a CC build that emits the
   custom events.** Six wired events (`SubagentStart`, `PostToolBatch`, `TaskCompleted`,
   `TeammateIdle`, `TaskCreated`, `PermissionDenied`) are experimental agent-teams events. If a
   build doesn't emit them, those gates silently won't fire. Already known: `TaskCompleted` (test
   + review gates) does **not** fire under Workflow execution — only on the prose/TaskCreate path.
3. **(Low) `$CLAUDE_PROJECT_DIR` must be expanded** by the CC version in use, else hooks resolve
   to a literal path and fail-open. Documented.
4. **(Low) rubric / research-system need `pip install -e`** — optional, detected-and-skipped at
   intake, never block the core pipeline.
5. **(Cosmetic) Stale `ceo-commit.sh:13-15` header** referencing the removed allow/deny pair.

---

## 3. Remediation plan

Ordered by the principle the reviewer landed on: **every claimed guarantee must be either
actually enforced or clearly labeled advisory/soft.** Two tracks — *make it true* (P0/P1) and
*make the docs honest* (P2) — plus lower hardening (P3).

### P0 — Gates that can falsely pass (core-guarantee correctness)

- **[C1] Prove the implementer actually produced work.** Extend `record_agent_start.py` to
  capture `git rev-parse HEAD` (worktree/branch-aware) as `startHead` alongside the timestamp.
  Change `check_artifacts.py` to require `git rev-list --count <startHead>..HEAD > 0` **or** a
  non-empty `git diff --name-only <startHead>..HEAD`, and require a structured
  `IMPLEMENTER-RESULT.<batchId>.json` (branch, commit SHA, changed files, tests run, deviations).
  Retire the misleading `git log --oneline -1`.
- **[C5] Bind the review gate to the judge.** Require a dedicated `agent-workspace/JUDGE-VERDICT.json`
  (`{"role":"judge","verdict":"PASS","reviewersConsidered":[...],"blockingFindingsRemaining":[]}`)
  and gate **only** that file/block. Drop "last PASS block wins" in both `check_review_gate.py` and
  the role-blind `VERDICT_PATTERN` in `check_artifacts.py`.
- **[C3] Make the test gate real when it matters.** Promote `TEST-COMMAND.txt` to a structured
  `TEST-CONFIG.json` (target-repo path, command, timeout, framework, min test count); **require it
  for gated roles** before pipeline execution (don't silently fail-open — emit a loud
  `TEST-GATE-DEGRADED` sentinel if absent). Run with `cwd =` the **target repo/worktree**, not
  `REPO_ROOT`. Treat timeout as **BLOCK** (collaborative) / **ESCALATE** (unattended), not allow.
  Protect `TEST-CONFIG.json` from subagent edits. Keep the hollow-pass guard.
- **[C2] Resolve the verifier write conflict (pick one model).** Preferred: **Option B** — gate
  `team-verifier` on a transcript/last-message verdict instead of a mandatory `REVIEW-LOG.md`
  file, and have the CEO aggregate structured verifier messages into the log. Removes the
  read-only-vs-file-artifact contradiction cleanly.

### P1 — Enforcement hardening (gameable / narrow checks)

- **[C15] Close the git-sweep bypasses.** Rewrite the `guard_git_commit.py` add-regex to match
  `git` + optional intervening global flags (esp. `-C <path>`) + `add` + any sweep selector
  (`-A`, `--all`, `-u`, `.`, `./`, `:/`, `*`, bare `--`). The `-C <path>` form is the most
  dangerous — it can stage in **other** repos. Prefix denies in `settings.json` can't do this
  alone; the hook is the right home.
- **[C7] Make citations binding.** Require ≥1 structured `cited_span` for every A/B verdict
  (block on empty — kill the no-spans dodge) and validate each quote **within a line window**
  (cited line ± 3), not substring-anywhere.
- **[C6] Tie the reviewer read-floor to the diff.** Parse `tool_input` paths and require N reads
  hitting files in the declared scope / changed-file set, not 5 arbitrary tool calls.
- **[C8] Strengthen partition disjointness.** Normalize paths (case-fold, strip `./`), detect
  directory-containment overlap, expand the manifest schema (`directories`, `generatedFiles`,
  `sharedResources`, `publicInterfacesTouched`, `requiresCoordinator`), and make
  coordinator/shared-resource conflicts **hard-blocking**.
- **[C9] Multi-repo STOP coverage.** Derive STOP paths from `repo-registry.json` (or env) so the
  kill switch reaches teammate sessions in other repos; add an installer that writes user-scope
  wiring and live-fire-validates it.
- **[C4/C13b] Make commit/push enforcement match the words.** Decide: either hard-block raw
  `git commit`/`git push` for subagents (CEO wrapper the only allowed path) **or** relabel the
  docs as warn-enforced. Either way, fix the stale `ceo-commit.sh:12-15` header and the wrong
  `README.md:70` "denied by permission rules" line.

### P2 — Public-release honesty & tooling

- **[C10] Add `selftest_all.py`.** Simulate payloads for every hook and assert expected
  block/allow; wire it into the 1.0a self-check; add CI on Linux/Windows/macOS.
- **[C13/all] Author `docs/enforcement-truth-table.md`** — the single highest-leverage doc:
  `Rule | Hard/Soft | Enforced by | Fail-open? | Tested by | Known bypasses`. This is the
  honest map the reviewer is really asking for; it subsumes claims 13, 18, and the soft/hard
  labeling across the board.
- **[C11] Replace "lossless"** with "durable, machine-grounded resume across compaction
  (git state + sentinels + a compact machine-refresh block)" everywhere it appears.
- **[C12] Release hygiene:** tagged releases, `CHANGELOG.md`, a compatibility matrix (CC version
  / OS / Python / agent-teams confirmed / hooks confirmed), and a **`goat doctor`** command that
  checks interpreter-on-PATH, `$CLAUDE_PROJECT_DIR` expansion, agent-teams events, and hook
  liveness — folding in runnability blockers #1–3. (LICENSE already present.)
- **[C18]** Mark Phase-0 plan gate + mandatory intake explicitly **SOFT BY DESIGN** in README
  and the truth table.

### P3 — Lower hardening

- **[C14] Broaden secret-file deny:** `**/.env*`, `**/.npmrc`, `**/.pypirc`, `**/secrets.json`,
  `**/*.pem`, `**/*.key`, `**/id_rsa*`, `**/.aws/credentials`, `**/appsettings.*.json` — or a
  `guard_secrets.py` hook for path-pattern coverage.
- **[C16] Add `ceo-commit.ps1`** (Windows-primary repo) and document which wrapper per OS.
- **[C17] Hard-protect read-only reference repos:** generate a per-session
  `permissions.deny: Write/Edit(<ref-path>/**)` (+ mutating-Bash guard) from `repo-registry.json`
  so ro-reference is a real path block, not briefing-only.

---

## 4. Suggested execution order

The reviewer's order is sound; concretely: **C1 → C5 → C3 → C2** (P0, the false-pass gates),
then **C15 → C7/C6 → C8 → C9 → C4** (P1), then the **enforcement truth table + selftest +
doctor** (P2, which also fix the doc-honesty cluster), then P3 polish. The truth table can be
written first if we want the public docs honest *immediately* while the mechanical fixes land.

**Bottom line:** no structural breakage and nothing is mis-wired — the work is closing the gap
between claimed and enforced guarantees. Every P0 item is a gate that today can pass without
the thing it certifies being true; those are the ones worth doing first.

---

## 5. Architecture-proposal assessment & decision

A second external document proposed a full "adaptive effort control plane" redesign (L0–L5 tier
ladder, a central deterministic effort router emitting `EFFORT-DECISION.json` every run, a
per-phase JSON state machine, a ~25-file artifact model, a per-role model+effort policy table,
strict/fail-closed mode, and a command suite). Three verification agents assessed it against
ground truth, Claude Code's real primitives, and this plan.

**Verdict: ~70% already built, ~20% over-engineering or conflicts with the design of record,
~10% genuinely worth adopting.** The proposal largely describes the current system back to
itself under invented vocabulary. It does **not** warrant a separate redesign phase — the three
good ideas fold into this plan as small items.

### 5.1 Already built (proposal renames existing functionality — no action)

| Proposal | Already exists as | Evidence |
|----------|-------------------|----------|
| Hard / Gate / Advisory hook classification | The HARD vs SOFT Enforcement Map | `rules.md:23-74` |
| Multi-lens review A/B/C + completeness critic + binding judge (structured JSON) | Built in full | `templates.md:559-819`, gated by `check_review_gate.py` |
| `RESUME-ANCHOR.json` resume state | `RESUME-STATE.md` (machine block + CEO body), self-healed | `unattended-mode.md:97-125`, `check_precompact.py` |
| `/goat-doctor`, `selftest_all.py`, enforcement truth table | Already committed here as **C12, C10, C13** | §3 above |
| `TEST-CONFIG.json`, `JUDGE-VERDICT.json`, startHead/endHead `IMPLEMENTER-RESULT.json`, expanded partition manifest | Already committed here as **C3, C5, C1, C8** | §3 above |
| Per-role model assignment | The roster Model column (architect→opus, implementer/verifier→sonnet, critic→haiku, judge→opus) | `roster.md:9-19` |

### 5.2 Reject — conflicts with the design of record or infeasible as stated

- **Phase engine as a JSON state machine** (entry/exit/escalation/**rollback** per phase) — **DROP.**
  Conflicts with "the native team substrate IS the pipeline state machine" (`goat-ceo.md:308`) and
  Primitive-Ledger Rule 7 (compose, don't rebuild). A hook can enforce only the structural slice
  (gate-sentinel presence, `allowedRoles` via `agent_type`, artifact *presence*) — which
  `check_phase_gate.py`/`check_artifacts.py` already do. The rich fields are un-enforceable by a
  hook: `exitCriteria` like "no undeclared public API changes" needs a semantic API diff, and
  `rollbackBehavior` is a CEO git action a hook has no authority or context to perform. Presenting
  the whole object as "validated by hooks" overstates the substrate.
- **Central deterministic effort-scoring engine + `EFFORT-DECISION.json` every run** — **DROP the
  engine; salvage only the lightweight artifact (see 5.3).** Only *structural* signals are
  hook-computable (migrations/auth globs, repo count, file count, test-command presence). The
  discriminating axes the proposal wants to score — "files independent or coupled," "vague
  request," "architectural complexity" — are inherently model judgment (file-disjoint ≠
  conflict-free, per `GOAT-CEO-REWORK-DESIGN.md:150-152`). Forced into a hook they become
  model-judgment-with-a-JSON-wrapper. This inverts the architecture (LLM decides, hooks validate).
- **Full ~25-file artifact model** — **DROP except the four already planned.** An artifact earns
  its place by being gate-bound; C1/C3/C5/C8 add exactly the files a hook can verify. The other
  ~20 (`SESSION.json`, `PLAN.json`, `ACCEPTANCE-CRITERIA.json`, …) are write-only ceremony no hook
  reads; acceptance criteria already live as a JSON block inside `PLAN.md`.
- **Per-role "effort" policy (`auto/low/medium/high/xhigh`) + dynamic escalation** — **DEFER /
  correct.** **`effort` is an invented knob — Claude Code subagents have no such parameter.** Real
  depth/cost control = `model` + `maxTurns` caps + tool restriction + prompt. Model assignment
  already exists (5.1). Dynamic per-task model escalation is speculative with no hook-trustable
  scoring signal; defer until measured need.
- **New commands `/goat-resume`, `/goat-status`** — **DEFER.** Both duplicate existing behavior
  (Step-6 resume flow + `inject_handoff_context.py`; `STATUS.md` + `claude agents` view). Thin
  wrappers, low value. (`/goat-doctor` = C12; `/goat-review` already exists.)

> **Model-fact corrections (do not propagate the proposal's errors into docs):** there is **no
> "fast model" cheap tier** — fast mode is Opus with faster output; **no `xhigh`/`high` effort
> suffix exists**; the only real models are Opus 4.8 / Sonnet 4.6 / Haiku 4.5 / Fable 5. The
> completeness critic is "haiku," full stop.

### 5.3 Adopt — the genuinely new value (three small additions)

- **[C19] Phase-0 decision-visibility artifact.** When the CEO's Assessment-First step chooses a
  *reduced* path (investigation-only, or a trivial direct fix that skips the pipeline), emit a
  one-line `agent-workspace/ASSESSMENT.md` recording the choice and why — e.g. *"Direct fix, no
  pipeline: low-risk, one file, no API/schema/security touch, tests available."* Today that skip
  is silent (only an ad-hoc dashboard note, `protocols.md:459`), leaving no audit trail for the
  most common case. Cheap, fits the on-disk-state ethos, and turns "the system did less" into
  visible disciplined judgment. Lightweight artifact — **not** a JSON scoring engine.
- **[C20] Opt-in strict / fail-closed mode + `HOOK-FAILURES.jsonl`.** A sentinel/env-gated
  `--strict` (e.g. `agent-workspace/STRICT_MODE`, read the way hooks already read
  `PHASE-GATES.json`) for unattended/high-risk runs. **Critical scoping:** fail-closed on a
  *policy violation or missing/ambiguous artifact*, **never on a hook crash** — flipping
  `check_phase_gate`/`check_review_gate` to exit 2 on an internal exception would brick every
  worktree mid-batch (the exact lockout `settings.json:5` warns about). Start with the gates that
  are safe to fail-closed (STOP kill switch, secret-write — halting when you can't evaluate is the
  safe bias); leave crash-paths fail-open. Always append every fail-open event to
  `agent-workspace/HOOK-FAILURES.jsonl` (cheap, and directly serves the doc-honesty goal). This
  strengthens C10's selftest and the unattended safety net.
- **[C21] Plain-language effort-tier vocabulary in the README.** Name the frugality model so users
  can predict cost/behavior — but as **three tiers, not six**: *Direct* (investigation / trivial
  one-file, no pipeline) → *Standard* (plan → implement → review → test) → *Full CEO* (worktree
  fan-out and/or multi-repo). The L0–L5 ladder is false precision: the real decision is roughly
  trinary, and L0–L5 invents distinctions hooks can't enforce and operators won't track. Fold into
  the existing "frugal by default" / model-tiering prose; pair with C19 so the chosen tier is both
  documented and traced.

### 5.4 Refinement this assessment forces on an existing item

- **C1 correction (worktree cwd, not `REPO_ROOT`).** The startHead/endHead gate must read HEAD
  from the **payload `cwd`** (the implementer's worktree), following the pattern
  `check_span_validity.py:120,146` already uses — **not** the `__file__`-derived `REPO_ROOT` that
  `check_phase_gate.py:25` / `check_test_gate.py:21` / `check_artifacts.py:64` currently anchor on.
  An implementer's commits land on its worktree branch (`settings.json:18` `worktree.baseRef:
  "head"`), so a `REPO_ROOT`-anchored HEAD comparison checks the wrong repo and always-passes or
  always-fails. Record `startHead` in the `record_agent_start.py` SubagentStart hook; compare at
  SubagentStop against the worktree HEAD. (This same `REPO_ROOT`-vs-worktree fix also applies to
  C3's "run tests from the target repo" change.)

### 5.5 Net

No phase-2 redesign. Append **C19, C20, C21** to this plan (C19/C21 under the P2 legibility track,
C20 under P1), apply the **C1/C3 cwd correction**, and reject the JSON state machine, the 25-file
model, the central scoring engine, and the invented `effort` knob. The proposal's real
contribution is a sharper articulation of a principle this plan already serves — *make the system
legible and honest about what it enforces* — plus the insight that the **cheap path should leave a
trace too**.
