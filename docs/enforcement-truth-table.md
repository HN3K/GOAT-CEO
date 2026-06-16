# Enforcement Truth Table

This is the honest, per-rule map of what GOAT-CEO actually enforces — the centerpiece of the
hardening pass (C13/C18). It exists so nobody has to infer enforcement strength from marketing prose:
each row states whether a rule is **Hard**, a **Gate**, or **Advisory**, what enforces it, whether it
is **fail-open**, whether it is covered by an automated self-test, and the **known bypasses/limits**.

Read this alongside the HARD/SOFT map in
[`.claude/commands/goat-ceo/rules.md`](../.claude/commands/goat-ceo/rules.md) and the hook wiring in
[`.claude/settings.json`](../.claude/settings.json). Where a claim elsewhere in the docs and this
table disagree, **this table wins** — it is sourced directly from the hooks and settings.

## How to read the columns

- **Hard / Gate / Advisory**
  - **Hard** = an unconditional `permissions.deny` rule; survives `--dangerously-skip-permissions`,
    does not depend on a Python interpreter being present.
  - **Gate** = a Python hook that can block a tool call / stop / turn-end (`exit 2`). Real
    enforcement, but only while the interpreter resolves and the hook event fires (see fail-open).
  - **Advisory** = a convention, briefing, or warn-only hook. No mechanical block — relies on CEO
    discipline or surfaces a warning the operator/CEO can override.
- **Fail-open?** — **Every Python hook in this repo is fail-open**: any internal exception exits 0
  (allow). A hook bug therefore never blocks legitimate work — and equally, a *dead interpreter*
  silently disables every Gate row at once (see the global caveat below). `permissions.deny` rules
  are the only non-fail-open enforcement.
- **Self-tested?** — whether the rule is covered by `selftest_all.py` (the hook self-test harness
  added in this pass, C10). It **has shipped** (`.claude/hooks/selftest_all.py`) and is run via the
  `/goat-doctor` command (manually — it is **not** wired into session start; the session-start check
  is the separate live-fire STOP probe in `goat-ceo.md` Step 1.0a). Its check groups A–K cover the
  fail-open contract for every hook plus the STOP, git-sweep, secret-write, test, artifact,
  review/judge, span, partition, phase, and reviewer read-audit gates; rows it does not exercise are
  marked "No".
- **Known bypasses / limits** — the honest caveats. If a row has none, it still inherits the global
  caveats below.

## Global caveats (apply to every Gate row)

1. **Dead/mis-named interpreter no-ops every hook.** All hooks invoke the literal string `python` on
   PATH. On a box where the interpreter is `py`/`python3`-only or shadowed (e.g. the Windows Store
   stub), **every Gate row silently degrades to advisory** (fail-open = allow). This is the single
   biggest enforcement risk; the CEO runs a live-fire self-check at session start to catch it, and
   `/goat-doctor` re-checks it.
2. **`$CLAUDE_PROJECT_DIR` must expand** in hook commands, and the Claude Code build must emit the
   experimental agent-teams events (`SubagentStart`, `SubagentStop`, `PostToolBatch`, `TaskCompleted`,
   `TeammateIdle`, `TaskCreated`, `PermissionDenied`). If an event doesn't fire on the installed
   build, the gates bound to it silently won't run. Known: `TaskCompleted` does not fire under
   Workflow execution — only on the prose/TaskCreate path.
3. **Fail-open is a deliberate choice.** It prevents a hook bug from bricking every worktree
   mid-batch. The cost is that "can't evaluate" biases toward "allow". The opt-in strict mode (C20,
   enabled via `agent-workspace/STRICT_MODE` or `GOAT_CEO_STRICT=1`) currently affects exactly **one**
   documented degraded-allow path — the test gate's no-config branch, where the normal warn+allow
   becomes a hard block (`check_test_gate.py` is the only hook that consults `strict_mode()`). It also
   logs every fail-open/degraded event to `HOOK-FAILURES.jsonl`. STOP (`check_stop_file.py`) and
   secret-write (`guard_secrets.py`) are **already unconditional blocks** and do **not** consult strict
   mode. The `_strict.py` helper is shared so other degraded-allow paths can opt in later. All optional
   capabilities (rubric, research KB, strict mode, …) are surfaced and toggled through the
   **`/goat-ceo:features`** command: defaults in the committed `.claude/goat-features.json` (all OFF),
   overlaid by the **gitignored** `.claude/goat-features.local.json` (personal), then per-repo flags in
   `repo-registry.json`, then session sentinels in `agent-workspace/`. Everything defaults OFF.

## The table

| Rule | Hard / Gate / Advisory | Enforced by | Fail-open? | Self-tested? | Known bypasses / limits |
|---|---|---|---|---|---|
| **STOP kill switch** — `agent-workspace/STOP` halts the next Bash/PowerShell/Write/Edit | **Gate** | `check_stop_file.py` (PreToolUse `Bash\|PowerShell\|Write\|Edit`) | Yes (exit 0 on crash) | Yes (selftest_all.py, group B); also the only rule live-fire-probed at session start | The STOP path SET is registry-derived: when the hook fires it honors a STOP in GOAT-CEO **or** any repo in `repo-registry.json` (C9). Coverage then depends on the hook RUNNING in the agent's session: with `teammateMode: in-process` (the default), teammates inherit GOAT-CEO's project hooks, so the derived set reaches them with no extra wiring. A genuinely **separate** session rooted in another repo does NOT inherit these project hooks — wire this hook at user scope (or in that repo) to cover it. The path list alone does not solve hook-wiring, and there is no installer that does it automatically. Allows the bare `rm/del STOP` that clears it. |
| **Secret-file writes** — block writes to env/key/credential files | **Hard** (`permissions.deny`) + **Gate** (defense-in-depth) | `permissions.deny` for `**/.env`, `**/.env.local`, `**/.env.*.local`, `**/.npmrc`, `**/.pypirc`, `**/secrets.json`, `**/*.pem`, `**/*.key`, `**/id_rsa*`, `**/.aws/credentials`, `**/appsettings.*.json`; plus `guard_secrets.py` (PreToolUse `Write\|Edit`) for broader path patterns | Deny: **No**. Hook layer: Yes | Yes (selftest_all.py, group D) — hook layer | The hard deny covers `.env`, `.env.local`, and `.env.*.local` — **not** every `.env.*` variant. Broader names like `.env.production` / `.env.dev` are caught only by the fail-open `guard_secrets.py` hook (which matches `.env.*` while allowing `.env.example`/`.sample`/`.template`/`.dist` templates), i.e. hook-enforced, NOT hard-denied. The deny is glob-based; an unanticipated secret filename slips the deny and relies on the hook. Reading secrets is not blocked (only Write/Edit). |
| **Broad git-add sweep** — no `git add -A` / `git add .` | **Hard** (`permissions.deny`) + **Gate** | `permissions.deny: Bash(git add -A*)`, `Bash(git add .)`, `Bash(git add ./)`; plus `guard_git_commit.py` add-regex | Deny: **No**. Hook: Yes | Yes (selftest_all.py, group C) | Deny is exact/prefix match (kept exact so scoped `git add .claude/foo` still works). Variants the *deny alone* misses — `git -C <path> add -A`, `git add -u`, `git add :/`, `git add *` — are now caught by the **hook** regex (C15); the `-C <path>` form is the dangerous one because it can stage in **other** repos. |
| **Single-committer / commit-push** — only the CEO commits to main; subagents commit only to their worktree branch, never push | **Advisory** (warn-only) | `guard_git_commit.py` (PreToolUse `Bash`) warns on raw `git commit`/`git push`; single-committer-to-main is convention | Yes | Yes (selftest_all.py, group C) — asserts warn-allow, not block | **Warn-only, not a hard deny.** There is no `permissions.deny` for `git commit`. The hook surfaces the command for review and **allows** it. An implementer committing to its own `worktree-<name>` branch is expected and correct; the convention is "no push, no commit to main," upheld by the CEO, not mechanically blocked. |
| **Phase gate** — a role can't Write/Edit/Bash until its required `*.GATE` sentinel exists | **Gate** | `check_phase_gate.py` (PreToolUse `Write\|Edit\|Bash`), reads `PHASE-GATES.json` keyed by `agent_type` | Yes | Yes (selftest_all.py, group J) | If `PHASE-GATES.json` is absent/empty the hook fails open (no gate map = allow). Anchored on `REPO_ROOT`, so it gates by sentinel presence, not by which repo HEAD moved. |
| **Implementer artifact gate** — subagent can't stop without its declared deliverable | **Gate** | `check_artifacts.py` (SubagentStop / TeammateIdle), per `agent_type` | Yes | Yes (selftest_all.py, group F) | Proves work three ways (C1): worktree HEAD moved past the recorded `startHead`, a dirty working tree, or a **current-run** `IMPLEMENTER-RESULT*.json`. A result file binds only if `endHead == current HEAD`, OR its `startHead == this run's recorded baseline` **AND** its `cwd` matches the payload cwd (cwd is mandatory on this path — two batches can share a baseline SHA, so startHead alone is not enough). `sessionId` is **not** a binder (one CEO session spans many batches). The fresh, unspoofable signals (HEAD-moved, dirty tree) are checked before the result file. Residual: relies on `record_agent_start.py` having captured a `startHead` baseline — when that is absent the gate fails open (can't prove ABSENCE of work without a baseline). |
| **Verifier verdict** — verifier produces a structured verdict before stopping | **Gate** | `check_artifacts.py` (verifier `agent_type` branch) | Yes | Yes (selftest_all.py, group F) | Verifier is read-only on production paths (frontmatter `disallowedTools: Write, Edit`) but retains Bash; the gate checks for the verdict artifact/message, not that the review was substantive. |
| **Test gate** — task can't close on a failing suite; a zero-test "hollow pass" is rejected | **Gate** | `check_test_gate.py` (TaskCompleted) | Yes | Yes (selftest_all.py, group E — incl. strict-mode no-config block) | C3 landed: a nonzero exit, a **timeout**, and a zero-test hollow pass all BLOCK, and the suite runs from the target worktree (payload `cwd` / configured `workingDirectory`), not `REPO_ROOT`. When unconfigured it emits a loud `TEST-GATE-DEGRADED` stderr warning + a `HOOK-FAILURES.jsonl` entry and ALLOWs (fail-open by design) — or BLOCKs under strict mode. Residual: the gate is only as good as the configured command, and it does **not** fire under Workflow execution (event caveat #2). |
| **Review / judge gate** — task can't close without judge `verdict: PASS` | **Gate** | `check_review_gate.py` (TaskCompleted); writes `ESCALATE_REQUIRED` past 2 iterations | Yes (but it *writes* a sentinel — the one hook that does) | Yes (selftest_all.py, group G) | C5 landed: gates on a judge-attributed verdict (prefers `JUDGE-VERDICT.json`, else a fenced block in `REVIEW-LOG.md` that is BOTH `"role":"judge"` AND has a verdict) — a non-judge PASS no longer satisfies it, and last-block-wins is gone. A PASS that still carries a non-empty `blockingFindingsRemaining` is treated as a block (contradictory). Residual: does not fire under Workflow (caveat #2). |
| **Reviewer read-audit** — A/B reviewer must read files before a verdict | **Gate** | `check_toolcall_audit.py` (SubagentStop), reads the reviewer's own transcript; gates only A/B | Yes | Yes (selftest_all.py, group K) | C6 landed: beyond the bare floor of `MIN_READ_CALLS` file reads, at least `MIN_DIFF_READS` of the reviewer's Read/Grep calls must land in the **changed-file set**, derived via a fallback chain — central `IMPLEMENTER-RESULT*.json` `changedFiles` → `IMPLEMENTATION-MANIFEST.json` batch scope → `git diff` from a `BASELINE.txt` (reviewer cwd, then central workspace). Residual: if NONE of those sources is determinable the diff-tie can't be computed and the audit fails soft to the name-count floor. Judge/critic/Reviewer-C exempt by marker. |
| **Citation span validity** — a cited `file:line` must actually resolve | **Gate** | `check_span_validity.py` (SubagentStop), A/B reviewers only | Yes | Yes (selftest_all.py, group H) | C7 landed: an A/B verdict with ZERO structured `cited_spans` BLOCKs (the empty-spans dodge is closed), and each span is validated within cited line ± `LINE_WINDOW` — a missing or out-of-range `line` is itself a block (the whole-file-substring fallback is no longer reachable for the gate, only for advisory callers). Residual: placeholder-looking and sub-`MIN_QUOTE` spans are skipped (anti-false-positive), and the check runs only on A/B reviewers (judge/critic/Reviewer-C exempt). |
| **Partition disjointness** — independent batches must be file-disjoint before the research gate | **Gate** | `check_partition.py` (SubagentStop on architect); CEO also runs it as a CLI | Yes; absent manifest = allow (single-batch) | Yes (selftest_all.py, group I) | C8 landed: matching normalizes paths (case-fold + `./` stripping), checks directory containment, validates declared dependencies, and hard-blocks shared-resource overlap — not the old exact `files[]` set-intersection. Residual: an absent manifest is treated as a single-batch run (allow), and the gate reasons over the *declared* manifest, not the eventual real diff. |
| **Registry guard** — `repo-registry.json` is CEO/Overseer-only | **Gate** (role-gated) | `guard_registry.py` (PreToolUse `Write\|Edit`): allows CEO (no `agent_type`) + `team-overseer`, blocks other subagents | Yes | No (not in selftest_all.py) | Role is inferred from the hook payload's `agent_type`; if a build doesn't populate it the no-`agent_type` path treats the writer as the CEO (allow). Replaced a former role-blind deny that wrongly locked the CEO out. |
| **Destructive-DB token** — `DROP/RESTORE DATABASE` requires a single-use approval token | **Gate** (opt-in, user-scope only) | `guard_destructive_db.py` — **ships in `.claude/hooks/` but is NOT wired in this repo's `settings.json`** | Yes | Not in selftest_all.py (not part of generic core) | **Inert by default.** Project-specific; only enforces if an operator wires it at user scope for a DB repo. A generic GOAT-CEO session does not ship this guard — do not assume DB ops are gated. |
| **Plan-mode / Phase-0 plan gate** — CEO presents the plan and waits for confirmation before launching | **Advisory** (SOFT BY DESIGN) | CEO behavioral convention in `goat-ceo.md` Step 0/1 | n/a (no hook) | No | **Deliberately not a harness lock.** `permissions.defaultMode: "plan"` is **not** set, so no hook can block the CEO from launching without confirmation. Honest, soft by design (C18). |
| **Mandatory intake** — always confirm repos + run the index/prereq check first | **Advisory** (SOFT BY DESIGN) | MANDATORY-INTAKE RULE block in `goat-ceo.md` Step 1; `{INDEX_STATUS}` propagation | n/a (no hook) | No | Prompt discipline only. The Phase-4 `INDEX.GATE` is a downstream backstop for staleness, but intake itself is not hook-enforced (C18). |
| **Turn-budget yield** — implementer/verifier yields past a ~30-min budget | **Gate** (availability-gated) | `check_turn_budget.py` (PostToolBatch) + `maxTurns` frontmatter caps | Yes | No (not in selftest_all.py) | Depends on `PostToolBatch`/`SubagentStart` existing on the build (caveat #2); fallback is the `maxTurns` frontmatter cap, which is a real harness cap independent of the hook. |
| **Worktree isolation / per-agent caps** — parallel implementers in worktrees, `maxTurns`, no sub-spawn, read-only verifiers/scout | **Hard** (frontmatter, harness-applied) | `isolation: worktree`, `maxTurns`, `disallowedTools: Agent`/`Write,Edit`, `permissionMode: plan` in agent defs | n/a (not a hook) | No (harness-native, not a Python gate) | Enforced by Claude Code applying the frontmatter, not by a fail-open hook — so these do **not** depend on the interpreter. A verifier still has Bash and could in principle write via a shell command (the frontmatter blocks Write/Edit tools, not all shell writes). |
| **Resume-anchor self-heal** — regenerate machine facts before compaction; re-inject after | **Advisory** (never blocks) | `check_precompact.py` (PreCompact, never blocks) + `inject_handoff_context.py` (SessionStart) | Yes (PreCompact intentionally never blocks — blocking auto-compaction would deadlock) | No | Not an enforcement gate — a survival mechanism. Preserves the **machine-verifiable floor** (git state + sentinels + machine-refresh block); injected prose is capped/truncated and can decay, which is why resume re-grounds from facts. |
| **Task-naming convention** | **Advisory** (warn-only) | `check_task_naming.py` (TaskCreated) — warns, never blocks | Yes | No | Cosmetic; off-convention titles warn only. |
| **Denial audit log** | **Advisory** (logging) | `log_denial.py` (PermissionDenied) — appends to an audit log | Yes | No | Observability, not enforcement. |
| **Capability audit logs** — record every rubric enforcement + research action | **Advisory** (logging) | `scripts/log_capability.py` (CEO / `/goat-ceo:features` runs → `logs/rubric-enforcement.jsonl`, `logs/research.jsonl`) + `rubric_heal_gate.py` `_log_enforcement` (→ `logs/rubric-enforcement.jsonl`) | Yes (append failures swallowed) | No | Observability, not a gate. Append-only JSONL under `logs/` (gitignored); written only when the optional rubric/research capability actually runs — absent for a vanilla session. `rubric-enforcement.jsonl` records every block/heal/degrade rubric caught; `research.jsonl` every capture/run/benchmark. View via `/goat-ceo:features` → rubric/research → `log`. |
| **`rubric` self-heal cap** — capped standards self-heal in a target repo | **Gate** (opt-in, target-repo) | `rubric_heal_gate.py` (PostToolUse `Edit\|Write`) — **ships but not wired by default** | Yes | No | Inert unless copied into a target repo and wired. Heals ≤2 cycles/file then degrades to advisory + logs `RUBRIC-DEGRADED.md`; each block/degrade is also recorded to `logs/rubric-enforcement.jsonl`. |
| **`RUBRIC.GATE`** — blocking rubric violation blocks integration (RUBRIC-AVAILABLE repos) | **Gate** (deterministic CLI, opt-in per repo) | CEO runs `rubric check --changed` (exit 1 on violation) at Phase-3 integration; writes the gate only on exit 0 | The CLI is deterministic; the CEO's choice to run it is convention | No | Only present when a repo is RUBRIC-AVAILABLE and the gate is added to `EXPECTED-GATES.txt` for that wave; otherwise absent (and must be, or the Stop hook blocks forever on a missing optional gate). A deterministic rule only blocks when its analyzer (`ast-grep`/`ruff`/a `tools.json` linter) is on PATH — a missing analyzer silently doesn't fire. rubric's CLI output needs `PYTHONUTF8=1` (set in `settings.json`) on Windows or it can crash on non-ASCII. Enabled/seen via `/goat-ceo:features`; blocking findings logged to `logs/rubric-enforcement.jsonl`. |

## Bottom line

The genuinely **hard** (interpreter-independent) enforcement is small and precise: the
`git add -A/.` deny, the secret-file denies, and the harness-applied agent frontmatter caps. Almost
everything else is a **fail-open Python gate** — real and useful when the interpreter and events are
present, advisory the moment they aren't. The Phase-0 plan gate and mandatory intake are **advisory
by design**. Several gates listed here (artifact, review, test, span, partition, read-audit) had
false-pass holes that the C1/C3/C5/C6/C7/C8 batches closed — and a follow-up pass closed the
second-order gaps (stale `IMPLEMENTER-RESULT` files, judge PASS with open blockers, missing citation
line anchors, and the read-audit baseline fallback). Every "Known bypasses / limits" cell above
describes the **current** code; where a residual limit remains it is named explicitly.
