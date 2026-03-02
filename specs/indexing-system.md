# Codebase-Index System — Reference Specification

> **Purpose**: Complete specification for setting up a layered codebase indexing system in any repository. This document is passed to repos that need bootstrapping — the GOAT team reads this spec and implements the system, adapting to the target repo's conventions.

---

## What This Is

The `Codebase-Index` is a structured documentation system that lives alongside your code. It provides a navigable, layered map of your codebase — organized by component, section, and responsibility — so that anyone (or any AI agent) can quickly understand the architecture and locate the exact context needed for any given task.

It is **not** generated documentation. It is **not** an API reference. It is a curated, human-maintained (and AI-assisted) knowledge layer that captures *structure*, *intent*, *patterns*, and *relationships* across your codebase.

---

## Why This Exists

When working in large codebases, most time is spent on orientation — figuring out where things live, what depends on what, and what patterns are in use. This is true for developers and especially for AI coding agents operating with limited context windows.

A hand-curated index acts as a **semantic map**. Instead of searching blindly, a developer or AI agent can:

1. Open `MASTER-INDEX.md` and find the relevant component area in seconds
2. Follow the link to that component's `INDEX.md` for focused context
3. Extract only the specific file paths and patterns needed
4. Begin working with full situational awareness

This gives deterministic, inspectable, human-readable retrieval — no embeddings required.

---

## Directory Structure

```
Codebase-Index/
│
├── README.md                          ← Explanation of the system
├── MASTER-INDEX.md                    ← Primary entry point
│
├── [component-or-section]/
│   ├── INDEX.md                       ← Section overview
│   └── [sub-component]/
│       └── INDEX.md                   ← More specific index
│
└── shared/
    ├── INDEX.md
    └── [sub-component]/
        └── INDEX.md
```

### Layering Rules

| Layer | Scope | Contains |
|-------|-------|----------|
| `MASTER-INDEX.md` | Entire codebase | Architecture overview, component map, task→index routing table |
| Section `INDEX.md` | One major area (e.g. `frontend/`, `backend/`) | Directory map, key files, dependencies, patterns |
| Sub-component `INDEX.md` | One feature or module | Specific files, function signatures, gotchas, related indexes |

**The higher the layer, the broader the view. The deeper the layer, the more implementation-specific.**

Never put implementation details in the master index. Never put architectural decisions only in a leaf index. Each layer owns its level of abstraction.

**Depth limit**: No more than 3 levels of nesting below `Codebase-Index/`.

---

## File Templates

### MASTER-INDEX.md

```markdown
# [Project Name] — Master Index
> Last updated: YYYY-MM-DD | Codebase version: x.x | Confidence: High / Medium / Low

## Project Overview
[2-3 sentences: what this project does, its primary tech stack, and its deployment target.]

## Architecture Overview
[Mermaid diagram or description of the high-level architecture.]

## Component Map

| Area | Purpose | Root Path | Index |
|------|---------|-----------|-------|
| [Component] | [What it does] | `path/` | [→](./component/INDEX.md) |

## Cross-Cutting Concerns

> These systems span multiple components. Check here before assuming something is self-contained.

- **[Concern]:** [Where it lives, what it touches]

## Task → Index Routing

> Use this table to immediately identify which indexes are relevant to your task.

| Task | Primary Index | Secondary Index |
|------|--------------|-----------------|
| [Task type] | [Link to index] | [Link or —] |

## Dependencies (if applicable)

| Package | Version | Used By |
|---------|---------|---------|
| [dep] | [version] | [where] |
```

### Section INDEX.md

```markdown
# [Section Name] Index
> Parent: [Master Index](../MASTER-INDEX.md)
> Last updated: YYYY-MM-DD | Confidence: High / Medium / Low

## Purpose
[One paragraph: what this section is responsible for and what it is explicitly NOT responsible for.]

## Directory Map
[Code block with inline annotations]

## Key Files

| File | Role | Notes |
|------|------|-------|
| `file.ext` | [What it does] | [Important notes] |

## Dependencies

- **Upstream (this depends on):** [list]
- **Downstream (depends on this):** [list]

## Patterns & Conventions
[Bullet list of naming conventions, structural patterns, coding standards specific to this section.]

## Known Gotchas
[Things that are non-obvious, past bugs, architectural decisions that look wrong but aren't.]

## Co-Change Indexes
> When working in this area, you will likely also need these indexes:
- [Related Index](../other-section/INDEX.md) — reason it's related
```

---

## Conventions

| Convention | Rule |
|------------|------|
| File naming | All index files are named `INDEX.md` (uppercase) |
| Folder naming | Lowercase, hyphen-separated (`state-management/`, not `StateManagement/`) |
| Links | Always use relative links between index files |
| Diagrams | Use Mermaid code blocks for portability |
| Dates | ISO 8601 (`YYYY-MM-DD`) in all `Last updated` fields |
| Confidence | Every index file carries a `Confidence: High / Medium / Low` tag |
| Depth limit | No more than 3 levels of nesting below `Codebase-Index/` |

---

## How to Build This Index

### Starting from Scratch

1. **Create the directory** — Add `Codebase-Index/` to your repo root.
2. **Map your top-level sections** — Identify 4-8 major areas of your codebase. Create a folder for each.
3. **Write the MASTER-INDEX.md** — Fill in the component map and architecture overview first. Leave the task routing table for after section indexes exist.
4. **Write section INDEX.md files** — Work top-down. Section indexes before sub-component indexes.
5. **Go deeper on active areas** — Don't try to index everything at once. Index the areas you're actively working in first, then expand over time.
6. **Update the task routing table** — Once section indexes exist, complete the master routing table.

### Keeping It Current

- On every PR that touches a component: update that component's `INDEX.md` if file structure, patterns, or dependencies changed.
- On every PR that changes architecture: update `MASTER-INDEX.md` and the architecture diagram.
- Add a `Confidence` field to each index (`High / Medium / Low`) and update it honestly.
- A low-confidence index is still useful — it signals where documentation debt exists.

### Using with AI Agents

When starting a task, reference this index explicitly:

```
Before starting, read Codebase-Index/MASTER-INDEX.md to understand the architecture.
Use the Task → Index Routing table to identify which component indexes are relevant.
Read those component indexes before touching any code.
```

---

## What This Is Not

- **Not a substitute for inline code comments.** Comments explain *how*. This index explains *where* and *why*.
- **Not generated docs.** Don't auto-generate this from code — the value is in curated judgment calls about structure and relationships.
- **Not exhaustive.** You do not need an index file for every single directory. Index areas that have meaningful structure, patterns, or cross-component relationships.
- **Not static.** An outdated index is worse than none. Treat index files as living documents.
