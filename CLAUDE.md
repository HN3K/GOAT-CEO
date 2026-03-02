# GOAT-CEO

Meta-orchestration repo for managing work across multiple repositories simultaneously using the GOAT agent team pipeline.

## What This Repo Is

This repo contains **skill definitions, spec documents, design docs, and session logs**. It does NOT contain runtime application code. It is the central hub from which a single Claude Code session coordinates GOAT pipelines running in multiple independent repositories.

## Repo Structure

```
GOAT-CEO/
├── CLAUDE.md                          ← You are here
├── GOAT-CEO-DESIGN.md                 ← Design document for the GOAT-CEO skill
├── repo-registry.json                 ← Persists repo paths, capabilities, groups across sessions
├── .claude/
│   ├── agents/                        ← Custom agent type definitions
│   │   ├── team-architect.md          ← Planner/architect agent type — used by the Planner role (Opus)
│   │   ├── team-ceo-assistant.md      ← Cross-repo impact assessment (Opus)
│   │   ├── team-ceo-scribe.md         ← Session logger (Haiku)
│   │   ├── team-cross-reviewer.md     ← Cross-repo contract verifier (Sonnet)
│   │   ├── team-implementer.md        ← Implementers (Sonnet)
│   │   ├── team-overseer.md           ← Repo pipeline manager (Opus)
│   │   ├── team-researcher.md         ← Researchers (Opus)
│   │   └── team-verifier.md           ← Reviewers (Sonnet)
│   └── commands/
│       ├── goat-ceo.md                ← CEO orchestration entry point (multi-repo)
│       ├── goat-ceo/                  ← CEO supporting files
│       │   ├── protocols.md           ← Communication flows and error recovery
│       │   └── templates.md           ← Agent spawn prompt templates
│       └── goat-team/                 ← GOAT pipeline skill files (single-repo)
│           ├── goat.md                ← Full pipeline orchestrator
│           ├── goat-plan.md           ← Plan-only variant
│           ├── goat-review.md         ← Review-only variant
│           ├── planner.md             ← Planner role script
│           ├── codebase-researcher.md ← Codebase researcher role
│           ├── technical-researcher.md← Technical researcher role
│           ├── implementer.md         ← Implementer role script
│           ├── index-updater.md       ← Index updater role
│           ├── reviewer.md            ← Reviewer role script
│           ├── index-check.md         ← Standalone index audit
│           ├── set-models.md          ← Model assignment configuration
│           └── README.md              ← Pipeline documentation
├── specs/                             ← Reference specs for bootstrapping repos
│   ├── indexing-system.md             ← Codebase-Index system spec
│   ├── tooling-system.md             ← codebase-index-tools CLI spec
│   └── goat-system.md                ← GOAT pipeline + agents spec
└── logs/                              ← Created per session (not committed)
    └── [repo-prefix]/
        ├── decisions.log
        ├── cross-repo.log
        └── timeline.log
```

## Usage

### Multi-repo orchestration (CEO coordinates parallel pipelines across repos):
```
/goat-ceo
```

### Single-repo full pipeline (plan → research → implement → review):
```
/goat-team:goat <task description>
```

### Plan only:
```
/goat-team:goat-plan <task description>
```

### Review only:
```
/goat-team:goat-review
```

## Agent Tooling Reference

Agents use `codebase-index-tools` for index context. The invocation command varies by repo:

| Repo Type | Invocation |
|-----------|------------|
| Python | `python -m codebase_index_tools <command> --format json` |
| Node | `node codebase-index-tools/cli.js <command> --format json` |

Always use `--format json`. Check `status` field before reading `data`. On error, read `data.message`.

### Common CLI Commands

| Command | Purpose |
|---------|---------|
| `search --list` | List all indexed mappings |
| `search --query "<term>"` | Search index metadata |
| `search --query "<term>" --in-content` | Deep search inside index content |
| `inject --task "<task>"` | Load task-relevant context |
| `inject --task "<task>" --include-master` | Load task context + master index |
| `inject --file <path>` | Load context for a specific file |
| `inject --ids <id1,id2>` | Load context by mapping ID |
| `check` | Check for stale indexes |
| `check --all` | Full index audit (stale + missing) |
| `scaffold --source <dir> --dry-run` | Preview scaffold for missing index |
| `scaffold --source <dir> --output <path> --mapping-id <id>` | Write scaffold |

### Protocol

Before implementation tasks, agents should:

1. **Search** for relevant indexes: `search --query "<task>"`
2. **Load** index context: `inject --task "<task>"`
3. **After changes**, check staleness: `check`

This repo does not yet have a `Codebase-Index/` directory or `codebase-index-tools` installed. These will be set up as the first task when bootstrapping this repo.

## Conventions

- **Primary content**: Markdown files (skill definitions, design docs, spec documents)
- **No application code**: This repo does not contain runtime application code
- **Source of truth**: Code/files are source of truth — verify against actual files, not docs
- **Agent artifacts**: Written to `agent-workspace/` during pipeline runs (gitignored)
- **Session logs**: Written to `logs/` during GOAT-CEO sessions (gitignored)
