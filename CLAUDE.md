# GOAT-CEO

Multi-repo orchestration harness for Claude Code. See `README.md` for the full
description, architecture, and how it interacts with Claude Code.

This repository contains **skill definitions, custom subagent definitions, and
`settings.json` hooks** — not runtime application code. A single Claude Code session
("the CEO") uses them to drive gated agent pipelines across multiple repositories in
parallel — interactively by default, with an opt-in unattended mode that runs through
context compaction.

## Layout

- `.claude/commands/` — the `/goat-ceo` (multi-repo) and `/goat-team:*` (single-repo)
  skills, the `/goat-ceo:features` optional-feature control command (`goat-ceo/features.md`),
  the `/goat-doctor` enforcement validator, plus the doctrine files (`rules.md`, `anti-drift.md`,
  `protocols.md`, `templates.md`, `roster.md`, and the opt-in `unattended-mode.md`).
- `.claude/agents/` — custom subagent definitions (overseer, architect, researcher,
  implementer, verifier, ceo-assistant, cross-reviewer, roadmap-architect).
- `.claude/hooks/` — the fail-open enforcement layer (phase gates, single-committer
  guard, STOP-file kill switch, partition + reviewer-citation validators, destructive-DB
  token, compaction self-heal + resume injection, and the opt-in `rubric_heal_gate.py`).
- `.claude/settings.json` — permission `deny` rules + hook wiring (incl. `PYTHONUTF8=1`).
- `.claude/goat-features.json` / `.claude/goat-features.local.json` — optional-feature defaults:
  a committed neutral baseline (everything OFF) + a gitignored personal-overrides file. Managed by
  `/goat-ceo:features`.
- `specs/` — self-contained specs for bootstrapping the Codebase-Index + tooling into a
  target repo.
- `scripts/` — `autonomous-loop.ps1` (optional crash-resilient outer loop) and `log_capability.py`
  (capability-audit logger → the gitignored `logs/rubric-enforcement.jsonl` / `logs/research.jsonl`).
- `tools/rubric/` — **vendored** copy of the `rubric` standards tool (the optional
  `RUBRIC-AVAILABLE` capability). Bundled so the integration works from a fresh clone; install
  with `pip install -e "tools/rubric[gate,retrieval]"`. See `tools/rubric/VENDORED.md`.

## Conventions

- Primary content is Markdown (skills, agent defs, specs) and Python hooks. No runtime
  application code lives here **except** the vendored `rubric` tool under `tools/rubric/`
  (a first-party tool bundled so the integration works from a fresh clone — edit it
  upstream and re-vendor, never directly here).
- Source of truth is the code/files, not prose — verify against actual files.
- Per-session artifacts (`agent-workspace/`, `logs/`) and local-only state (`repo-registry.json`,
  `research-kb/`, `.claude/goat-features.local.json`) are gitignored; the committed
  `.claude/goat-features.json` baseline is the deliberate exception (and stays all-OFF — personal
  preferences never get published).
- Optional capabilities (rubric, research KB, codebase-index, strict mode, …) are seen and toggled
  via the `/goat-ceo:features` command; all default OFF.
- The CEO is the single committer and makes only pathspec-scoped commits
  (`git add <files>`, never `git add -A`/`.`).
- **Documentation parity — before every push.** Never push a new change/feature without updating the
  relevant docs in the SAME change. Order: **build → validate → update docs → commit → push.** At
  minimum update `CHANGELOG.md`; also update whichever of `README.md`,
  `docs/enforcement-truth-table.md`, `.claude/commands/goat-ceo/rules.md`, and this `CLAUDE.md` the
  change affects (new command/feature/flag, behavior change, new file, corrected claim). A push whose
  diff changes code/behavior but no docs is a defect. (Doctrine: `rules.md` Rule 9.)

## Setup

The hooks in `.claude/settings.json` invoke `python` on PATH and reference hook scripts via
`$CLAUDE_PROJECT_DIR/.claude/hooks/`. Adjust the interpreter (`python` / `python3` / `py`)
for your OS if needed, and confirm your Claude Code version expands `$CLAUDE_PROJECT_DIR` in
hook commands (otherwise replace it with an absolute path). Requires the agent-teams
feature (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). See `README.md` → Setup.

**Optional — rubric standards grounding.** The per-repo `RUBRIC-AVAILABLE` capability
(conventions/reuse grounding + standards gate + standards reviewer) uses the `rubric` CLI,
which is **vendored under `tools/rubric/`** — install it with `pip install -e
"tools/rubric[gate,retrieval]"` (puts `rubric` on PATH; the repo-scoped commands — `check`/`context`/
`measure`/`init` — take `--repo <path>`). A target repo also needs a `.rubric/` KB: `rubric init
--no-claude` scaffolds the `.rubric/` directory + linter wiring but creates **no conventions KB** —
the rules/conventions are operator-authored (seed them via `/goat-ceo:features → rubric seed`, which
proposes candidates from your code + best-practice research for you to pick). Intake detection =
`.rubric/` exists AND `rubric kb --kb .rubric/kb` responds; GOAT-CEO silently skips rubric for repos
without it. A deterministic rule only gates when its analyzer (`ast-grep`/`ruff`/a configured linter)
is on PATH. On Windows, `settings.json` sets `PYTHONUTF8=1` (already wired) so rubric's non-ASCII CLI
output doesn't crash the console. See `README.md` → Standards grounding, `tools/rubric/VENDORED.md`,
and `GOAT-CEO-REWORK-DESIGN.md §I`.
