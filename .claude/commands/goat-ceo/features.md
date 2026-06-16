---
description: Configure GOAT-CEO optional features — see effective state, toggle defaults, activate per-repo, and run feature-specific actions (rubric standards, external research).
argument-hint: "[status | list | enable <feature> [repo] | disable <feature> [repo] | set-default <feature> on|off | unset <feature> [repo] | <feature> <action> …]"
allowed-tools: Read, Write, Edit, Bash(cat:*), Bash(jq:*), Bash(ls:*), Bash(git:*), Bash(rubric:*), Bash(python:*), Bash(cp:*), Bash(grep:*), Task, WebSearch, WebFetch
disable-model-invocation: true
---

# /goat-ceo:features — control GOAT-CEO's optional capabilities

The single entry point to **see, toggle, and drive** GOAT-CEO's OPTIONAL features. The
always-on enforcement layer (the `git add` sweep deny, secret-file denies, and the core
fail-open gates) is NOT managed here — that is unconditional; see `/goat-ceo:rules` and
`/goat-doctor`.

User input: `$ARGUMENTS`

## Live state (read before doing anything)

Committed global defaults — `.claude/goat-features.json` (Tier 1, tracked, cross-machine):
!`cat .claude/goat-features.json 2>/dev/null | jq '.defaults' 2>/dev/null || echo '{}  (file missing — treat all defaults as off)'`

Per-repo activation — `repo-registry.json` (Tier 2, machine-local):
!`cat repo-registry.json 2>/dev/null | jq '(.repos // {}) | map_values({access, rubricStatus, researchKbStatus, indexStatus})' 2>/dev/null || echo '(no registry yet)'`

Session toggles — `agent-workspace/` sentinels + env (Tier 3, ephemeral):
!`( ls agent-workspace/ 2>/dev/null | grep -E '^(STRICT_MODE|AUTONOMOUS-ACTIVE|INTAKE-ACTIVE|STOP|READONLY-PATHS\.json)$' || echo '(no session sentinels)' ); echo "GOAT_CEO_STRICT=${GOAT_CEO_STRICT:-unset}"`

## State model & precedence (recite this to the operator on `status`)

Optional features live in **three tiers**, because defaults must travel across machines while
per-repo activation is inherently local and session toggles are throwaway:

1. **Tier 1 — committed global default** (`.claude/goat-features.json`, `defaults.<feature>`): "is
   this feature on *by default*?" Tracked in git, so it is what another machine inherits on pull.
2. **Tier 2 — per-repo override** (`repo-registry.json` per-repo fields, e.g. `rubricStatus`,
   `researchKbStatus`, `indexStatus`, `access`): activate/deactivate a feature for a *specific*
   repo. Machine-local (absolute paths), never committed.
3. **Tier 3 — session toggle** (`agent-workspace/` sentinels like `STRICT_MODE`,
   `AUTONOMOUS-ACTIVE`; or env `GOAT_CEO_STRICT`): this-session-only, gitignored.

**Precedence — most specific wins:** `built-in default (OFF) < Tier 1 global default < Tier 2
per-repo override < Tier 3 session sentinel`. One sentence: *"session beats per-repo, per-repo beats
global, global beats the built-in OFF."*

**Safe-by-default:** every optional feature's built-in default is **OFF**; enabling is a deliberate,
explicit act. A missing/malformed config value falls back to OFF rather than erroring. Never bulk
"enable all". Probe applicability per repo and skip features that don't apply (don't fail on them).

## Verb routing

Parse the FIRST token of `$ARGUMENTS` as the verb. **No-arg ⇒ `status`.** This is plain prose
routing — reason about the tokens; there is no shell subcommand parser.

| Verb | Effect | Writes |
|---|---|---|
| *(none)* / `status` | Show effective state of every feature **with its source scope** (provenance), per repo where relevant. | nothing |
| `list` | List every toggleable feature + a one-line description + applicability. | nothing |
| `enable <feature> [repo]` | Turn the feature ON for a repo (Tier 2). `repo` defaults to the repo under discussion / the one the operator names. | `repo-registry.json` |
| `disable <feature> [repo]` | Explicit OFF override for a repo (Tier 2). | `repo-registry.json` |
| `set-default <feature> on\|off` | Set the **committed global default** (Tier 1). | `.claude/goat-features.json` |
| `unset <feature> [repo]` | Remove a repo's override so it falls back to the global default. Distinct from `disable` (which is an explicit OFF). | `repo-registry.json` |
| `<feature> <action> …` | Forward to that feature's action handler (see below). | varies |

On every state-changing verb: make the edit, then **re-print the affected `status` line(s) with
provenance** so the operator sees the new effective value and where it comes from. For Tier-2 writes,
remember `repo-registry.json` is role-gated by `guard_registry.py` (the CEO / no-`agent_type` writer
is allowed). If a repo lacks the documented fields (the on-disk registry may be stale), backfill the
documented schema (`goat-ceo.md` Step 1.1) rather than erroring.

### `status` output shape (provenance is the whole point)
For each feature print: `feature = <on|off|n/a> (<source>)`, e.g.
- `rubric = on (per-repo: craft)`
- `research-kb = off (global default)`
- `strict-mode = on (session: STRICT_MODE sentinel)`
- `codebase-index = n/a (not applicable — no Codebase-Index/ in this repo)`
Show a `?` and a one-line reason when a feature is enabled by default but the repo can't actually use
it (e.g. rubric default-on but no `.rubric/` KB present).

## Feature registry (canonical list — the source of truth for what's toggleable)

| Feature | Tier(s) | What it does | ON mechanism | OFF mechanism | Applicability probe |
|---|---|---|---|---|---|
| **rubric** | 1 + 2 | Standards grounding (`rubric context`) + the `RUBRIC.GATE` (`rubric check`) + Reviewer-C | repo field `rubricStatus: "RUBRIC-AVAILABLE"`; default in `goat-features.json` | `rubricStatus: "RUBRIC-UNAVAILABLE"` | `.rubric/` exists AND `rubric kb --kb .rubric/kb` exits 0 |
| **research-kb** | 1 + (shared) | Capture-always / verify-on-demand external research KB vs ephemeral WebSearch | create `research-kb/` + `researchKbStatus: "RESEARCH-KB-AVAILABLE"`; default in `goat-features.json` | `RESEARCH-KB-UNAVAILABLE` | `tools/research-system` importable AND `research-kb/` present/creatable |
| **codebase-index** | 2 | Agents use `search`/`inject`/`check` instead of direct reads | `indexStatus: "INDEX-AVAILABLE"` (detection-driven) | `INDEX-UNAVAILABLE` | `Codebase-Index/` + `codebase-index-tools` respond |
| **strict-mode** | 1 + 3 | Degraded-allow paths (e.g. test gate w/ no config) BLOCK instead of warn-allow | `touch agent-workspace/STRICT_MODE` or env `GOAT_CEO_STRICT=1`; default in `goat-features.json` | `rm agent-workspace/STRICT_MODE` + unset env | always applicable |
| **rubric-heal-gate** | 2 (manual) | Opt-in PostToolUse self-heal (≤2 cycles/file) in a TARGET repo | copy `.claude/hooks/rubric_heal_gate.py` into the target repo's `.claude/hooks/` + wire as PostToolUse `Edit\|Write` | remove that wiring | rubric available in the target repo |
| **unattended** | 1 + 3 | Keep-going / survive-compaction layer | `touch agent-workspace/AUTONOMOUS-ACTIVE` (empty = all sessions; `session:<id>` = scoped); default in `goat-features.json` | `rm agent-workspace/AUTONOMOUS-ACTIVE` | always applicable; read `unattended-mode.md` first |
| **read-only-reference** | 2 + 3 | Mark a repo readable-but-never-writable | `access: "ro-reference"` + add its path to `agent-workspace/READONLY-PATHS.json` | remove from both | per reference repo |
| **destructive-db-guard** | user-scope (manual) | Block `DROP/RESTORE DATABASE` without a token | wire `guard_destructive_db.py` at USER scope (`~/.claude/settings.json`) | unwire | only repos that touch a DB |

For the manual/user-scope features (`rubric-heal-gate`, `destructive-db-guard`, user-scope STOP),
`enable` does NOT silently edit another repo / user settings — it prints the exact copy + wiring steps
and offers to perform them with confirmation.

## Feature-specific actions

### rubric `<action>`
- **`rubric status`** — what is actually enforced in the repo. Run `rubric kb --kb .rubric/kb` (lists
  conventions/rules/exemplars) and `rubric check --changed --repo <path> --kb .rubric/kb` (runs the
  deterministic gate). Then state plainly: **only `kind: deterministic` + `enforcement: blocking`
  rules whose backing analyzer is on PATH actually BLOCK**; conventions/exemplars and `llm`/advisory
  rules are guidance only. Flag any blocking rule whose tool (`ast-grep`/`ruff`/a `tools.json` linter)
  is missing from PATH — it silently won't run.
- **`rubric seed [repo]`** — discover & propose standards, operator selects. *(See the dedicated
  section below — this is the headline flow.)*
- **`rubric gate <files…>`** — `rubric check <files> --repo <path> --kb .rubric/kb` (exit 1 = violation).
- **`rubric measure`** — `rubric measure --changed --repo <path> --kb .rubric/kb [--baseline … --save …]`: SLOC/complexity/gate-pass deltas (advisory, never blocks).
- **`rubric verify <file>`** — `rubric enforce <file> --verify --kb .rubric/kb`: deterministic gate + adversarially-verified LLM review (subscription-billed).
- **`rubric codify <files…>`** — `rubric codify <files> --repo <path> --draft --write --kb .rubric/kb`: proposes rules from **recurring code-review drift** (NOT research) into `.rubric/proposals/` for human approval.
- **`rubric heal on|off [repo]`** — toggle the opt-in self-heal hook in a target repo (prints/performs the copy + wiring; see registry table).

### research `<action>`
- **`research status`** — filesystem scan of `research-kb/`: per subject dir, `synthesis.md` + `claims.jsonl` present ⇒ **VERIFIED**; only `sources/` ⇒ **CAPTURED**. (The engine does not generate an `INDEX.md`; this command derives the catalog by scanning.)
- **`research capture <sources.json>`** — `python tools/research-system/scripts/run_capture.py <sources.json> --research-root research-kb` (free, no LLM).
- **`research run <slug> "<question>" [--discover N]`** — `python tools/research-system/scripts/run_research.py <slug> "<question>" --research-root research-kb [--discover N]` (decompose → retrieve → answer → verify → synthesize; subscription-billed; `--discover` adds web search for gaps).
- **`research benchmark <slug>`** — `python tools/research-system/scripts/run_benchmark.py <slug>` (faithfulness check).

> All `rubric`/`research` shell calls run with UTF-8 forced (`settings.json` sets `PYTHONUTF8=1`),
> which is required on Windows or rubric's non-ASCII output crashes the console.

## `rubric seed` — discover & author standards (operator-selected)

The point of seeding is NOT to dump a generic starter KB. It is to figure out **what THIS repo should
enforce**, from two complementary sources, then let the operator choose. Run these steps:

**0. Preconditions.** Confirm the target repo is rubric-capable: `.rubric/` exists and `rubric kb
--kb .rubric/kb` responds. If `.rubric/` is missing, offer `rubric init --no-claude --repo <path>`
first (note: `init` creates NO `kb/` — that's exactly what this flow fills). Confirm the repo's
primary language(s)/framework — they drive both discovery passes.

**1. Codebase-derived candidates (your own code).** Spawn 1–2 **read-only** agents (`Explore` or
`team-researcher`) to mine the target repo for the conventions it *already* follows — export/naming
style, error-handling patterns, test colocation, module/layering layout, logging, API-contract
idioms, etc. — and to read `.rubric/index/components.json` (rubric's reuse index). Each candidate
reports: the observed pattern, how widespread it is (so we don't codify a one-off), and a proposed
mechanical rule (`ast-grep`/`ruff`/`tools.json`) or, if not mechanizable, an advisory convention.

**2. Research-derived candidates (internet).** Spawn internet-research agent(s) for relevant external
best practices / standards / conventions for the repo's language/framework/domain:
- If **research-kb is on/available**, drive the research system so results are captured + verified:
  `research run <slug> "best-practice coding standards & conventions for <lang/framework/domain>"
  --discover 6` — then read the supported claims + `synthesis.md`.
- Otherwise use `WebSearch`/`WebFetch` (or the `deep-research` skill) directly.
  Each candidate reports: the standard, a **1–2 sentence rationale (why adopt it)**, a source
  citation, and whether it is mechanically enforceable (and with which analyzer) or advisory.

**3. Present a selection menu to the operator (mandatory — never auto-adopt).** Consolidate both
passes into one numbered list. For EACH candidate show:
- source tag: **📁 codebase-derived** or **🌐 researched**
- title + the **why** (brief rationale; for researched items include the citation)
- proposed enforcement: **BLOCKING (deterministic via `<tool>`)** or **ADVISORY**
- backing analyzer + whether it is currently on PATH (⚠️ if missing — it would silently not run)
- target language(s)
Ask the operator which to implement. They may accept, reject, edit, or split any candidate. Researched
standards are opinionated and may be wrong for this repo — operator selection is **required**, not a
rubber stamp.

**4. Author the selected candidates.** For each chosen item write the matching `.rubric/kb/` JSON
(schemas below) and update the manifest (`.rubric/kb/rubric.kb.json`):
- mechanical → a `rules/<id>.json` with `kind:"deterministic"`, `enforcement:"blocking"`, `tool`, `spec`, `languages` (+ an optional `conventions/` grouping and an `exemplars/` example)
- advisory → a `conventions/<id>.json` (+ `exemplars/`) only
Prefer writing to `.rubric/kb/` directly since the operator already approved; show the new files /
a diff and confirm before finalizing.

**5. Verify + report.** Run `rubric kb --kb .rubric/kb` (confirm the new counts) and `rubric check
--changed --repo <path> --kb .rubric/kb` (confirm the gate runs clean / as expected). **Warn loudly**
for any blocking rule whose analyzer is missing from PATH (install it or the rule is inert). Record
what was added and the research provenance (which claims/sources backed each rule) so the additions
are auditable.

### KB file schemas (write these under `.rubric/kb/`)
- **convention** `conventions/<id>.json`: `{id, name, intent, rule_ids[], exemplar_ids[], tags[]}` — advisory grouping; does not block on its own.
- **rule** `rules/<id>.json`: `{id, name, intent, kind:"deterministic"|"llm", enforcement:"blocking"|"advisory", tool:"ast-grep"|"ruff"|"rubric"|null, spec, languages[], tags[]}` — only `deterministic` + `blocking` + an available tool actually gates.
- **exemplar** `exemplars/<id>.json`: `{id, title, intent, language, code, tags[], convention_id, source}`.
- **manifest** `rubric.kb.json`: `{schema_version, name, version, rule_ids[], exemplar_ids[], convention_ids[]}` — keep the id lists in sync with the files.

> Note: there is no built-in `claims.jsonl → KB` bridge in rubric (`rubric codify` only ingests
> code-review findings). This flow IS that bridge, performed in-session with operator approval.

## Notes
- This command never touches the always-on enforcement layer or `permissions.deny`.
- All writes are reversible: Tier-1 via `set-default`, Tier-2 via `unset`/`disable`, Tier-3 by
  removing the sentinel.
- If anything is ambiguous (which repo, which language, on/off), ASK — don't guess.
