# Set Models — Change GOAT Agent Model Assignments

You are executing the `/goat-team:set-models` skill. Parse `$ARGUMENTS` and follow the instructions below.

## Agent Files

The 4 GOAT agent definition files live at `.claude/agents/`:
- `team-architect.md`
- `team-researcher.md`
- `team-implementer.md`
- `team-verifier.md`

Each has YAML frontmatter with a `model:` field. This skill edits that field directly.

## Valid Models

`opus`, `sonnet`, `haiku`

## Profiles

| Profile    | team-architect | team-researcher | team-implementer | team-verifier |
|------------|---------------|----------------|-----------------|--------------|
| quality    | opus          | opus           | opus            | opus         |
| balanced   | opus          | opus           | sonnet          | sonnet       |
| speed      | sonnet        | sonnet         | sonnet          | haiku        |
| budget     | sonnet        | haiku          | haiku           | haiku        |

## Execution

### Step 1 — Read current state

Read all 4 agent files in `.claude/agents/` and extract the current `model:` value from each.

### Step 2 — Parse arguments

- **No arguments**: Display the current model assignments as a table, then stop.
- **One argument matching a profile name** (`quality`, `balanced`, `speed`, `budget`): Apply that profile to all 4 files.
- **Two arguments** `<agent-name> <model>`: Change that single agent's model. The agent name must match one of the 4 agent names (with or without the `team-` prefix). The model must be one of the valid models.
- **Anything else**: Show usage help and the current table.

### Step 3 — Apply changes

For each file that needs updating, use the Edit tool to replace the existing `model: <old>` line with `model: <new>` in the YAML frontmatter. Only edit files where the model is actually changing.

### Step 4 — Confirm

Display the updated model assignments as a table showing all 4 agents and their models. If a profile was applied, mention which profile. If a single agent was changed, mention which agent and what it changed from/to.

## Output Format

Use this table format for displaying model assignments:

```
Agent              Model
─────────────────  ──────
team-architect     opus
team-researcher    opus
team-implementer   sonnet
team-verifier      sonnet
```

## Usage Examples

```
/goat-team:set-models              → show current assignments
/goat-team:set-models quality      → all agents use opus
/goat-team:set-models budget       → cost-optimized assignment
/goat-team:set-models architect opus → change only team-architect
/goat-team:set-models team-researcher haiku → change only team-researcher
```
