# Codebase Index Tooling — Reference Specification

> **Purpose**: Complete specification for building the `codebase-index-tools` CLI suite in any repository. This document is passed to repos that need bootstrapping — the GOAT team reads this spec and implements the system, choosing the appropriate language for the target repo.
>
> **Prerequisite**: A `Codebase-Index/` directory must already exist in the repo root with at least a `MASTER-INDEX.md` and one component `INDEX.md`.

---

## Overview

The `codebase-index-tools` is a local CLI suite that operates on a `Codebase-Index/` directory. It provides four commands:

| Command | Primary User | Purpose |
|---------|-------------|---------|
| `check` | CI/CD, developers, agents | Detect INDEX.md files that are stale relative to code changes |
| `inject` | AI agents | Retrieve and output relevant index content for a given task or file |
| `search` | Developers, agents | Find which indexes are relevant to a keyword or topic |
| `scaffold` | Developers, agents | Generate stub INDEX.md files for unmapped directories |

### Design Principles

- **Agent-first output.** Every command supports `--format json` so AI agents can parse results without text scraping.
- **Zero ambiguity.** Every exit code, output field, and flag is explicitly defined.
- **No external services.** All operations are local: filesystem reads, git CLI calls, and markdown parsing.
- **Composable.** Commands produce outputs that can be piped or directly loaded into agent context.
- **Fail loudly.** Errors surface clearly with actionable messages, never swallowed silently.

### Language Choice

Two reference implementations exist:
- **Python** (stdlib-only, Python 3.8+) — used in JarvisVibeGraph. Invocation: `python -m codebase_index_tools`
- **Node.js** (minimist + minimatch only, Node 18+) — used in KH-UI-AI. Invocation: `node codebase-index-tools/cli.js`

Choose based on the target repo's primary language and toolchain. Both implementations are functionally identical.

---

## Repository Structure

### Python Layout
```
codebase_index_tools/
├── __main__.py              ← python -m entry point
├── cli.py                   ← argparse setup + subcommand routing
├── config.py                ← path resolution + mappings.json loader
├── mappings.json            ← path glob → INDEX.md mapping declarations
├── commands/
│   ├── __init__.py
│   ├── check.py
│   ├── inject.py
│   ├── search.py
│   └── scaffold.py
└── lib/
    ├── __init__.py
    ├── git.py               ← git CLI wrapper (subprocess)
    ├── index_parser.py      ← INDEX.md parser
    ├── mapper.py            ← file path → INDEX.md resolver
    └── output.py            ← unified output formatting
```

### Node.js Layout
```
codebase-index-tools/
├── cli.js                   ← Entry point + command routing
├── config.js                ← path resolution + mappings.json loader
├── package.json
├── mappings.json
├── commands/
│   ├── check.js
│   ├── inject.js
│   ├── search.js
│   └── scaffold.js
└── lib/
    ├── git.js
    ├── index-parser.js
    ├── mapper.js
    └── output.js
```

Place the tools directory at the repo root, as a sibling to `Codebase-Index/`.

---

## Configuration: `mappings.json`

This file is the heart of the system. It declares which source file globs are "owned" by which INDEX.md files.

```json
{
  "config": {
    "defaultStaleDays": 30,
    "defaultBranch": "main"
  },
  "mappings": [
    {
      "id": "frontend-components",
      "description": "React UI components",
      "sourceGlobs": [
        "src/components/**/*",
        "src/ui/**/*"
      ],
      "indexFile": "Codebase-Index/frontend/components/INDEX.md",
      "staleDays": 14
    }
  ]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `config.defaultStaleDays` | No | Global staleness threshold in days. Default: 30 |
| `config.defaultBranch` | No | Branch to diff against. Default: `main` |
| `mappings[].id` | Yes | Unique identifier. Lowercase, hyphen-separated. |
| `mappings[].description` | Yes | Human-readable description of what this mapping covers |
| `mappings[].sourceGlobs` | Yes | Array of glob patterns relative to repo root |
| `mappings[].indexFile` | Yes | Path to the INDEX.md file, relative to repo root |
| `mappings[].staleDays` | No | Override for per-mapping staleness threshold |

---

## Shared Libraries

### git wrapper
- `getChangedFiles(baseBranch)` — files changed vs base branch using `git diff --name-only [base]...HEAD`
- `getFileLastCommitDate(filePath)` — last commit date via `git log -1 --format=%cI -- [path]`
- `getCurrentBranch()` — current branch name
- `isTracked(filePath)` — whether file is git-tracked
- Always run with cwd set to repo root. Wrap all calls in try/catch.

### index parser
- `parseIndex(filePath)` → `{ filePath, relativePath, title, lastUpdated, confidence, rawContent, sections, valid, warnings }`
- Extract `lastUpdated` from `Last updated: YYYY-MM-DD` in first 10 lines
- Extract `confidence` from `Confidence: High|Medium|Low`
- Extract `title` from first `# ` heading
- Extract `sections` by splitting on `## ` headings
- If `lastUpdated` missing: set null, add warning
- `findAllIndexes(indexRoot)` → all INDEX.md paths under Codebase-Index/

### mapper
- `resolveFileToMappings(filePath, mappings)` → all matching mappings (a file can belong to multiple)
- `groupFilesByIndex(changedFiles, mappings)` → Map of indexFile → { mapping, files[] }
- `searchMappings(query, mappings)` → mappings scored by keyword match on description/id

### output
- `printResult(data, format, command)` — text or JSON output
- `printError(message, format)` — error + exit 1
- `printWarning(message)` — stderr warning, does not exit

**JSON envelope** (all commands):
```json
{
  "command": "<command-name>",
  "status": "success | warning | error",
  "timestamp": "ISO-8601",
  "data": { }
}
```

---

## Command: `check`

Detect stale INDEX.md files relative to recent code changes.

```
check [--base <branch>] [--format text|json] [--strict] [--all]
```

**Behavior:**
1. Get changed files (or all tracked files if `--all`)
2. Group by responsible INDEX.md using mappings
3. For each affected index: compare source file commit dates against `Last updated` date
4. Report: `ok`, `stale` (source newer than index by > staleDays), or `missing` (INDEX.md doesn't exist)
5. `--strict`: exit code 1 if any stale/missing indexes

**Text output:**
```
CODEBASE INDEX — STALE CHECK
Comparing against: main | 3 indexes affected

✅  backend/auth/INDEX.md — Mapping: backend-auth | Last updated: 2025-11-20
⚠️  STALE: frontend/components/INDEX.md — 41 days behind
❌  MISSING: backend/payments/INDEX.md

SUMMARY: 1 ok · 1 stale · 1 missing
```

---

## Command: `inject`

Load relevant INDEX.md content for a task or file. Primary command for AI agent context loading.

```
inject [--task <description>] [--file <path>] [--ids <id,id>] [--include-master] [--format text|json]
```

**Behavior:**
1. Resolve targets from `--task` (keyword search), `--file` (mapping lookup), `--ids` (direct)
2. Merge and deduplicate resolved index paths
3. Optionally prepend MASTER-INDEX.md
4. Load and parse each index
5. Output full content (text mode uses clear delimiters for agent parsing)

**Text output uses delimiters**: `═══` for outer boundaries, `━━━` for per-index sections. These are not decorative — they help agents parse section boundaries.

---

## Command: `search`

Find relevant indexes without loading full content. Faster than `inject` for discovery.

```
search [--query <terms>] [--list] [--in-content] [--format text|json]
```

**Behavior:**
- `--list`: show all mappings with existence status
- `--query`: tokenize on whitespace, score mappings by keyword hits in description/id
- `--in-content`: also search inside INDEX.md file content
- Results sorted by score descending

---

## Command: `scaffold`

Generate pre-filled INDEX.md stubs for unmapped directories.

```
scaffold [--source <dir>] [--output <path>] [--mapping-id <id>] [--dry-run] [--init-mappings] [--format text|json]
```

**Behavior:**
- Scans source directory, builds directory tree (max 2 levels), selects key files
- Generates template with today's date, `Confidence: Low`, and TODO placeholders
- `--init-mappings`: scan existing Codebase-Index/ structure and generate starter `mappings.json` (sourceGlobs left as TODO)
- `--dry-run`: print without writing
- Never overwrite existing INDEX.md without warning

---

## Error Handling

| Condition | Behavior |
|-----------|----------|
| `Codebase-Index/` not found | Clear path error, suggest fix, exit 1 |
| `mappings.json` not found | Path error, suggest `--init-mappings`, exit 1 |
| Git not available | "git not found in PATH", exit 1 |
| INDEX.md file missing | `status: "missing"` in results, do not crash |
| INDEX.md has no `Last updated` | Warning, mark confidence as Low |
| No indexes match query | "no matches" message, suggest `--list`, exit 1 |
| Output path already exists | Warning, do not overwrite silently |

---

## Agent Usage Protocol

Add to the repo's `CLAUDE.md`:

```markdown
## Codebase Index Protocol

Before beginning any implementation task:

1. Discover relevant indexes:
   [tooling-command] search --query "[task]" --format json

2. Load index context:
   [tooling-command] inject --task "[task]" --format json

3. After making changes, check for stale indexes:
   [tooling-command] check --format json

If `check` returns stale indexes, update the relevant INDEX.md files and set their "Last updated" date to today.
```

Replace `[tooling-command]` with the actual invocation for the target repo:
- Python: `python -m codebase_index_tools`
- Node.js: `node codebase-index-tools/cli.js`

---

## Implementation Order

1. **Shared libraries first** — all commands depend on them
2. **`check` second** — exercises every library, highest-priority command
3. **`inject` third** — primary agent command
4. **`search` fourth** — lightweight discovery
5. **`scaffold` last** — only needed during initial setup

---

## Key Rules

- `mappings.json` is the source of truth for file→index relationships
- Staleness is based on `Last updated` date in the INDEX.md, NOT the file's git commit date — this is intentional (reflects human judgment)
- Never mutate `mappings.json` from commands other than `scaffold --init-mappings`
- All commands must work with `--format json` even on errors
- Dependencies: stdlib-only for Python; minimist + minimatch only for Node.js
