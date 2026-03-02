# Agent Team — Review Only

Spawn two independent reviewers to review existing work in `agent-workspace/`. This command assumes implementation is already complete and PLAN.md, IMPLEMENTATION-MANIFEST.md, and modified files exist.

**Context:** $ARGUMENTS

---

## Tooling Reference

# Tooling command varies by repo — check CLAUDE.md for the correct invocation
# Python repos: python -m codebase_index_tools <command> --format json
# Node repos: node codebase-index-tools/cli.js <command> --format json

All commands run from the repo root:
```bash
python -m codebase_index_tools <command> [options]
```

**Always use `--format json`** when output will be parsed programmatically.

---

## Prerequisites

Verify these files exist before proceeding:
- `agent-workspace/PLAN.md`
- `agent-workspace/IMPLEMENTATION-MANIFEST.md`

If either is missing, report the error and stop. Do not fabricate these files.

If `agent-workspace/REVIEW-LOG.md` exists, append to it. If not, create it.

---

## Phase 5 — Review

**Agents:** Two Reviewers — always exactly two, always independent

Spawn both reviewers in parallel. Each reviewer independently:

**Step 1 — Load context:**
Read `agent-workspace/PLAN.md`, `agent-workspace/IMPLEMENTATION-MANIFEST.md`, and `agent-workspace/REVIEW-LOG.md` (if it exists).

**Step 2 — Run full index audit:**
```bash
python -m codebase_index_tools check --all --format json
```
Capture full JSON output for the review log.

**Step 3 — Verify index coverage per changed file:**
For each file listed as modified in IMPLEMENTATION-MANIFEST.md:
```bash
python -m codebase_index_tools inject --file [modified-file-path] --format json
```
If `data.indexes` is empty, the file has no index coverage — flag as an issue.

**Step 4 — Verify completion criteria:**
Check each item in the manifest's `## Completion Criteria` against actual codebase state. Read the actual files and verify the changes were made correctly.

**Step 5 — Log findings:**
Each reviewer writes to REVIEW-LOG.md:
```markdown
## Review [A|B] — [DATE]

### Index Check Results (--all)
[paste full check --all --format json output]

### Per-File Index Coverage
- `path/to/file` → [indexFile] — covered / not covered

### Completion Criteria Verification
- [ ] [criterion] — PASS / FAIL — [notes]

### Issues Found
| ID | Severity | File | Description |
|----|----------|------|-------------|

### Verdict
PASS / FAIL
```

**Severity Taxonomy:**

| Severity | Definition | Required Action |
|----------|-----------|-----------------|
| `critical` | Contradicts the plan, breaks existing functionality, or security issue | Report — requires replanning |
| `major` | Materially incomplete or significant gap vs. the plan | Report — requires targeted fix + re-review |
| `minor` | Small deviation, style issue, or non-breaking omission | Fix in place |
| `info` | Observation, no action required | Log only |

---

## Phase 6 — Index Update (Mandatory)

After both reviewers complete their review:

1. Run `check --all --format json`. Collect all stale/missing entries.
2. For each stale index: update the INDEX.md content to reflect changes, set `Last updated:` to today.
3. For each missing index: scaffold and fill in.
4. Verify clean: `check --all --format json` must return `data.summary.stale === 0` and `data.summary.missing === 0`.
5. Log final result to REVIEW-LOG.md under `## Final Index Check`.

---

## On Completion

Output the combined verdict and summary:

```
REVIEW COMPLETE
─────────────────────────────────────────────────
Reviewer A verdict:  [PASS/FAIL]
Reviewer B verdict:  [PASS/FAIL]
Issues found:        [N critical / N major / N minor / N info]
Indexes updated:     [list of indexFile paths, or "none"]
Index state:         [CLEAN / N stale remaining]
Workspace:           agent-workspace/
─────────────────────────────────────────────────
```

**If critical or major issues found:** Report them clearly. The user should fix the issues and run `/goat-review` again.

**If only minor/info or no issues:** Fix minors in place and report PASS.
