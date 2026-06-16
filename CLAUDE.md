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
  skills plus the doctrine files (`rules.md`, `anti-drift.md`, `protocols.md`,
  `templates.md`, `roster.md`, and the opt-in `unattended-mode.md`).
- `.claude/agents/` — custom subagent definitions (overseer, architect, researcher,
  implementer, verifier, ceo-assistant, cross-reviewer, roadmap-architect).
- `.claude/hooks/` — the fail-open enforcement layer (phase gates, single-committer
  guard, STOP-file kill switch, partition + reviewer-citation validators, destructive-DB
  token, compaction self-heal + resume injection, and the opt-in `rubric_heal_gate.py`).
- `.claude/settings.json` — permission `deny` rules + hook wiring.
- `specs/` — self-contained specs for bootstrapping the Codebase-Index + tooling into a
  target repo.
- `scripts/autonomous-loop.ps1` — optional outer loop for crash-resilient unattended runs.

## Conventions

- Primary content is Markdown (skills, agent defs, specs) and Python hooks. No runtime
  application code lives here.
- Source of truth is the code/files, not prose — verify against actual files.
- Per-session artifacts are written to `agent-workspace/` and `logs/` (gitignored).
- The CEO is the single committer and makes only pathspec-scoped commits
  (`git add <files>`, never `git add -A`/`.`).

## Setup

The hooks in `.claude/settings.json` invoke `python` on PATH and reference hook scripts via
`$CLAUDE_PROJECT_DIR/.claude/hooks/`. Adjust the interpreter (`python` / `python3` / `py`)
for your OS if needed, and confirm your Claude Code version expands `$CLAUDE_PROJECT_DIR` in
hook commands (otherwise replace it with an absolute path). Requires the agent-teams
feature (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`). See `README.md` → Setup.

**Optional — rubric standards grounding.** The per-repo `RUBRIC-AVAILABLE` capability
(conventions/reuse grounding + standards gate + standards reviewer) requires the external
`rubric` CLI — a **host tool** installed on the operator's PATH and run against any repo via
`--repo`; it is **not vendored here**. A target repo also needs a `.rubric/` KB
(`rubric init --no-claude`). GOAT-CEO detects rubric at intake and silently skips it for repos
that don't have it. See `README.md` → Standards grounding and `GOAT-CEO-REWORK-DESIGN.md §I`.
