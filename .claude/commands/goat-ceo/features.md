---
description: Configure GOAT-CEO optional features — opens an interactive numbered menu to see, toggle, and run feature actions (rubric standards, external research). Typed verbs also work.
argument-hint: "(no args → interactive menu) | status | enable <feature> [repo] | disable <feature> [repo] | set-default <feature> on|off | unset <feature> [repo] | <feature> <action>"
allowed-tools: Read, Write, Edit, Bash(cat:*), Bash(jq:*), Bash(ls:*), Bash(git:*), Bash(rubric:*), Bash(python:*), Bash(cp:*), Bash(grep:*), Task, WebSearch, WebFetch
disable-model-invocation: true
---

# /goat-ceo:features — control GOAT-CEO's optional capabilities

The single entry point to **see, toggle, and drive** GOAT-CEO's OPTIONAL features. The always-on
enforcement layer (the `git add` sweep deny, secret-file denies, the core fail-open gates) is NOT
managed here — that is unconditional; see `/goat-ceo:rules` and `/goat-doctor`.

User input: `$ARGUMENTS`

## How this command runs

- **No arguments → INTERACTIVE MENU MODE (the default, and the normal way to use it).** Present every
  choice with the **`AskUserQuestion` tool** — Claude Code's native selectable-options picker: the
  operator clicks an option or types their own via the auto-added **"Other"**. They drill into a
  feature, then an action, and the loop continues until they quit; they should NEVER need to know verb
  syntax. CONSTRAINT: `AskUserQuestion` allows at most **4 options per question** (plus the automatic
  "Other" free-text), so when a list exceeds 4 (the 8-feature menu, rubric's ~11 actions), **group it
  into ≤4 buckets and drill down** — never hide a feature; "Other" covers anything not shown. Fall back
  to a plain numbered-text menu only if the tool is unavailable.
- **Arguments given → FAST PATH.** Treat the first token as a verb (see the Fast-path table) and
  execute it directly, then offer to drop into the menu. Power-user shortcut; identical effects.

## Live state (read first, every time, before drawing any menu)

Default layer — the shipped baseline (`.claude/goat-features.json`, committed, all-off) overlaid with
YOUR personal overrides (`.claude/goat-features.local.json`, gitignored, local-only):
!`echo 'shipped baseline:'; cat .claude/goat-features.json 2>/dev/null | jq '.defaults' 2>/dev/null || echo '{} (missing — treat as all off)'; echo 'your local overrides:'; cat .claude/goat-features.local.json 2>/dev/null | jq '.defaults' 2>/dev/null || echo '(none)'`

Per-repo activation — `repo-registry.json` (local-only, never published):
!`cat repo-registry.json 2>/dev/null | jq '(.repos // {}) | map_values({access, rubricStatus, researchKbStatus, indexStatus})' 2>/dev/null || echo '(no registry yet)'`

Session toggles — `agent-workspace/` sentinels + env (this session only):
!`( ls agent-workspace/ 2>/dev/null | grep -E '^(STRICT_MODE|AUTONOMOUS-ACTIVE|INTAKE-ACTIVE|STOP|READONLY-PATHS\.json)$' || echo '(no session sentinels)' ); echo "GOAT_CEO_STRICT=${GOAT_CEO_STRICT:-unset}"`

---

## INTERACTIVE MENU MODE  ← do this when `$ARGUMENTS` is empty

Drive the whole flow with the **`AskUserQuestion`** tool so the operator selects from clickable options
(or types their own via "Other"). Loop until they quit. Use the **Feature registry**, **Feature
actions**, and **`rubric seed`** sections below as your reference for each feature's state,
applicability, and what each action does. `AskUserQuestion` caps at **4 options/question** — group
longer lists into ≤4 buckets and drill down; never hide a feature.

### A. Main menu — pick a feature
1. From the live state above, compute each feature's **effective state + source scope** (precedence
   below) and its **applicability** to the current/active repo.
2. Call `AskUserQuestion` ("Which optional feature do you want to configure?") with the features
   GROUPED into ≤4 selectable options so none are hidden — put the current effective state in each
   option's description. A good grouping:
   - **rubric** — standards grounding + RUBRIC.GATE + Reviewer-C (`<state>`)
   - **research-kb** — capture/verify external research KB (`<state>`)
   - **Session modes** — strict-mode / unattended (`<states>`)
   - **Per-repo & manual** — codebase-index / rubric-heal-gate / read-only-ref / destructive-db
   In the question text, tell the operator the **"Other"** box accepts a feature name directly, or
   `status` (full per-tier status) / `quit`.
3. Route: a single-feature option → its **Feature submenu** (B). A group → a second `AskUserQuestion`
   listing that group's features (each ≤4). `status` → print full per-tier status, then re-ask.
   `quit` → summarize changes and stop.

### B. Feature submenu — pick an action
1. Show the feature's state across **all tiers** (built-in / Tier-1 global / Tier-2 per-repo / Tier-3
   session) + applicability in one short block, so the operator sees what overrides what.
2. Call `AskUserQuestion` with that feature's ACTIONS. If it has ≤4, list them directly. If more (e.g.
   rubric), ask the CATEGORY first, then the specific action in a follow-up `AskUserQuestion`:
   - **Toggle** — enable / disable (per-repo) · set personal default · unset override
   - **Inspect** — `status` (what's enforced) · `measure`
   - **Run** — `seed` · `gate <files>` · `verify <file>` · `codify <files>`
   - **Self-heal** — `heal on/off`
   For features with only toggles (`strict-mode`, `unattended`, `codebase-index`), present those
   directly (≤4). For manual/user-scope features (`rubric-heal-gate`, `destructive-db`), the "enable"
   action PRINTS the exact copy/wiring steps and confirms — it never silently edits another repo or
   user settings. Use the question text to offer Back / quit (or rely on "Other").
3. The operator's selection routes to **Acting** (C).

### C. Acting on a choice
- **State changes** (enable/disable/set-default/unset, heal on/off): make the binary/scope decision
  itself an `AskUserQuestion` where natural — `on | off`; **which repo** (offer the registered repos as
  options + "Other"); **per-repo vs personal default**. Then state EXACTLY which file/field/sentinel will
  change, perform the write, re-show the feature's state with new provenance, and return to (B).
- **Feature actions** (rubric status/seed/gate/measure/verify/codify, research status/capture/run/
  benchmark): run the mapped command(s) from **Feature actions**; for `rubric seed` follow that
  section step by step (its candidate selection also uses `AskUserQuestion`, `multiSelect`, grouped ≤4
  per question). Show the result, then return to (B).
- **Missing value** (which repo? which files? which language?): ask — via `AskUserQuestion` when it's a
  choice, else a plain question. Never guess.
- **Loop:** re-present the relevant menu (via `AskUserQuestion`) after each action until the operator
  picks quit, then print a one-line summary of any changes made this session.

---

## FAST PATH  ← do this when `$ARGUMENTS` is non-empty

Parse the first token as the verb and execute directly (then offer the menu). Same effects as the
menu actions.

| Verb | Effect | Writes |
|---|---|---|
| `status` | Effective state of every feature **with source scope** (provenance). | nothing |
| `list` | Every feature + one-line description + applicability. | nothing |
| `enable <feature> [repo]` | Per-repo ON override (Tier 2). | `repo-registry.json` |
| `disable <feature> [repo]` | Per-repo explicit OFF (Tier 2). | `repo-registry.json` |
| `set-default <feature> on\|off` | Your **personal** default (gitignored, local-only — not published). | `.claude/goat-features.local.json` |
| `unset <feature> [repo]` | Remove a repo's override → fall back to default. | `repo-registry.json` |
| `<feature> <action> …` | Forward to that feature's action handler. | varies |

`repo-registry.json` writes are role-gated by `guard_registry.py` (the CEO / no-`agent_type` writer is
allowed). If the on-disk registry is missing the documented fields (it may be stale), backfill the
documented schema (`goat-ceo.md` Step 1.1) rather than erroring.

---

## State model & precedence (recite on `status` / full-status)

Optional features resolve across these layers; **none of a user's personal choices are ever
committed/published** — only the neutral shipped baseline is in git:

1. **Built-in default** — OFF for every optional feature.
2. **Shipped baseline** (`.claude/goat-features.json`, committed): the project's neutral default
   (everything OFF). This file is shared with everyone who uses GOAT-CEO, so it is NOT for personal
   preferences — leave it at the baseline unless you are deliberately changing the project default.
3. **Personal default** (`.claude/goat-features.local.json`, **gitignored, local-only**): your own
   default for a feature, overlaying the baseline. Never published or imposed on other users.
   **`set-default` writes HERE.**
4. **Per-repo override** (`repo-registry.json` fields: `rubricStatus`, `researchKbStatus`,
   `indexStatus`, `access`): activate/deactivate for a *specific* repo. Local-only, never committed.
5. **Session toggle** (`agent-workspace/` sentinels like `STRICT_MODE`, `AUTONOMOUS-ACTIVE`; or env
   `GOAT_CEO_STRICT`): this-session-only, gitignored.

**Precedence — most specific wins:** `built-in (OFF) < shipped baseline < personal default < per-repo
override < session sentinel`.

**Safe-by-default:** every feature's built-in default is **OFF**; enabling is deliberate. A
missing/malformed value falls back to OFF rather than erroring. Never bulk "enable all". Probe
applicability per repo and skip features that don't apply.

**`status` line shape (provenance is the point):** `feature = <on|off|n/a> (<source>)`, e.g.
`rubric = on (personal default)`, `research-kb = off (shipped baseline)`,
`strict-mode = on (session: STRICT_MODE)`, `codebase-index = n/a (no Codebase-Index/ in this repo)`.

## Feature registry (the canonical list of what's toggleable)

| Feature | Tier(s) | What it does | ON mechanism | OFF mechanism | Applicability probe |
|---|---|---|---|---|---|
| **rubric** | 1 + 2 | Standards grounding (`rubric context`) + `RUBRIC.GATE` (`rubric check`) + Reviewer-C | repo `rubricStatus: "RUBRIC-AVAILABLE"`; personal default in `goat-features.local.json` | `rubricStatus: "RUBRIC-UNAVAILABLE"` | `.rubric/` exists AND `rubric kb --kb .rubric/kb` exits 0 |
| **research-kb** | 1 + shared | Capture-always / verify-on-demand research KB vs ephemeral WebSearch | create `research-kb/` + `researchKbStatus: "RESEARCH-KB-AVAILABLE"`; personal default in `goat-features.local.json` | `RESEARCH-KB-UNAVAILABLE` | `tools/research-system` importable AND `research-kb/` present/creatable |
| **codebase-index** | 2 | Agents use `search`/`inject`/`check` vs direct reads | `indexStatus: "INDEX-AVAILABLE"` (detection-driven) | `INDEX-UNAVAILABLE` | `Codebase-Index/` + `codebase-index-tools` respond |
| **strict-mode** | 1 + 3 | Degraded-allow paths (e.g. test gate w/ no config) BLOCK instead of warn-allow | `touch agent-workspace/STRICT_MODE` or env `GOAT_CEO_STRICT=1`; personal default in `goat-features.local.json` | `rm agent-workspace/STRICT_MODE` + unset env | always |
| **rubric-heal-gate** | 2 (manual) | Opt-in PostToolUse self-heal (≤2 cycles/file) in a TARGET repo | copy `.claude/hooks/rubric_heal_gate.py` into the target repo's `.claude/hooks/` + wire PostToolUse `Edit\|Write` | remove that wiring | rubric available in the target repo |
| **unattended** | 1 + 3 | Keep-going / survive-compaction layer | `touch agent-workspace/AUTONOMOUS-ACTIVE` (empty = all sessions; `session:<id>` = scoped); personal default in `goat-features.local.json` | `rm agent-workspace/AUTONOMOUS-ACTIVE` | always; read `unattended-mode.md` first |
| **read-only-reference** | 2 + 3 | Mark a repo readable-but-never-writable | `access: "ro-reference"` + add path to `agent-workspace/READONLY-PATHS.json` | remove from both | per reference repo |
| **destructive-db-guard** | user-scope (manual) | Block `DROP/RESTORE DATABASE` without a token | wire `guard_destructive_db.py` at USER scope (`~/.claude/settings.json`) | unwire | only repos that touch a DB |

## Feature actions

### rubric `<action>`
- **`status`** — what is actually enforced. Run `rubric kb --kb .rubric/kb` (lists conventions/rules/
  exemplars) and `rubric check --changed --repo <path> --kb .rubric/kb` (deterministic gate). State
  plainly: **only `kind: deterministic` + `enforcement: blocking` rules whose backing analyzer is on
  PATH actually BLOCK**; conventions/exemplars + `llm`/advisory rules are guidance. Flag any blocking
  rule whose tool (`ast-grep`/`ruff`/a `tools.json` linter) is missing from PATH — it silently won't run.
- **`seed [repo]`** — discover & propose standards, operator selects. *(See the dedicated section.)*
- **`gate <files…>`** — `rubric check <files> --repo <path> --kb .rubric/kb` (exit 1 = violation).
- **`measure`** — `rubric measure --changed --repo <path> --kb .rubric/kb [--baseline … --save …]` (advisory).
- **`verify <file>`** — `rubric enforce <file> --verify --kb .rubric/kb` (gate + adversarial LLM review; subscription-billed).
- **`codify <files…>`** — `rubric codify <files> --repo <path> --draft --write --kb .rubric/kb` → `.rubric/proposals/` for human approval (from code-review drift, NOT research).
- **`heal on|off [repo]`** — toggle the opt-in self-heal hook in a target repo (print/perform the copy + wiring).

### research `<action>`
- **`status`** — scan `research-kb/`: per subject dir, `synthesis.md` + `claims.jsonl` ⇒ **VERIFIED**; only `sources/` ⇒ **CAPTURED**. (The engine generates no `INDEX.md`; derive the catalog by scanning.)
- **`capture <sources.json>`** — `python tools/research-system/scripts/run_capture.py <sources.json> --research-root research-kb` (free, no LLM).
- **`run <slug> "<question>" [--discover N]`** — `python tools/research-system/scripts/run_research.py <slug> "<question>" --research-root research-kb [--discover N]` (decompose→retrieve→answer→verify→synthesize; subscription-billed; `--discover N` adds web search for gaps).
- **`benchmark <slug>`** — `python tools/research-system/scripts/run_benchmark.py <slug> --research-root research-kb` (faithfulness check).

> All `rubric`/`research` shell calls run with UTF-8 forced (`settings.json` sets `PYTHONUTF8=1`),
> required on Windows or rubric's non-ASCII output crashes the console.

## `rubric seed` — discover & author standards (operator-selected)

The point is NOT to dump a generic starter KB — it is to find what THIS repo should enforce, from two
sources, then let the operator choose. Steps:

**0. Preconditions.** Confirm the repo is rubric-capable (`.rubric/` exists and `rubric kb --kb
.rubric/kb` responds); if `.rubric/` is missing, offer `rubric init --no-claude --repo <path>` first
(note: `init` creates NO `kb/` — that's what this flow fills). Confirm the repo's primary
language(s)/framework — they drive both passes.

**1. Codebase-derived candidates (your own code).** Spawn 1–2 **read-only** agents (`Explore` /
`team-researcher`) to mine the repo for conventions it ALREADY follows — export/naming style,
error-handling, test colocation, module/layering, logging, API-contract idioms — and read
`.rubric/index/components.json`. Each candidate: the observed pattern, how widespread, and a proposed
mechanical rule (`ast-grep`/`ruff`/`tools.json`) or an advisory convention.

**2. Research-derived candidates (internet).** Spawn internet-research agent(s) for relevant external
best practices/standards for the repo's language/framework/domain. If **research-kb is on/available**,
drive the research system so results are captured + verified: `research run <slug> "best-practice
coding standards & conventions for <lang/framework/domain>" --discover 6`, then read supported claims
+ `synthesis.md`. Otherwise use `WebSearch`/`WebFetch` (or the `deep-research` skill). Each candidate:
the standard, a **1–2 sentence rationale (why adopt it)**, a source citation, and whether it is
mechanically enforceable (with which analyzer) or advisory.

**3. Present the candidates for selection (mandatory — never auto-adopt).** Use `AskUserQuestion` with
`multiSelect: true` so the operator ticks the ones to adopt (group into ≤4 options per question and ask
in batches when there are many; "Other" lets them name extras or edits). For EACH candidate convey:
source tag **📁 codebase-derived** / **🌐 researched**; title + the **why**; proposed enforcement
**BLOCKING (deterministic via `<tool>`)** or **ADVISORY**; backing analyzer + whether it's on PATH (⚠️
if missing — it would silently not run); target language(s) — put this in each option's description.
They may accept/reject/edit/split any. Researched standards are opinionated and may be wrong for this
repo — explicit operator selection is required.

**4. Author the selected.** For each chosen item write the matching `.rubric/kb/` JSON (schemas below)
and update the manifest: mechanical → `rules/<id>.json` (`kind:"deterministic"`, `enforcement:
"blocking"`, `tool`, `spec`, `languages`) + optional `conventions/` grouping + `exemplars/`; advisory →
`conventions/<id>.json` (+ `exemplars/`). Show the new files / a diff and confirm.

**5. Verify + report.** Run `rubric kb --kb .rubric/kb` (confirm new counts) and `rubric check
--changed --repo <path> --kb .rubric/kb` (gate runs as expected). **Warn loudly** for any blocking rule
whose analyzer is missing from PATH. Record what was added + the research provenance (which
claims/sources backed each rule) so it's auditable.

### KB file schemas (write under `.rubric/kb/`)
- **convention** `conventions/<id>.json`: `{id, name, intent, rule_ids[], exemplar_ids[], tags[]}` — advisory grouping; never blocks alone.
- **rule** `rules/<id>.json`: `{id, name, intent, kind:"deterministic"|"llm", enforcement:"blocking"|"advisory", tool:"ast-grep"|"ruff"|"rubric"|null, spec, languages[], tags[]}` — only `deterministic` + `blocking` + an available tool actually gates.
- **exemplar** `exemplars/<id>.json`: `{id, title, intent, language, code, tags[], convention_id, source}`.
- **manifest** `rubric.kb.json`: `{schema_version, name, version, rule_ids[], exemplar_ids[], convention_ids[]}` — keep id lists in sync with the files.

> rubric has no built-in `claims.jsonl → KB` bridge (`rubric codify` only ingests code-review
> findings); this flow IS that bridge, performed in-session with operator approval.

## Notes
- Never touches the always-on enforcement layer or `permissions.deny`.
- All changes reversible: Tier-1 via `set-default`, Tier-2 via `unset`/`disable`, Tier-3 by removing the sentinel.
- If anything is ambiguous (which repo, language, on/off), ASK — don't guess.
