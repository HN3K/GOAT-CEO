# Index Check — Audit and Update Stale Indexes

Run a full audit of all codebase indexes, identify stale and missing entries, update them, and confirm a clean state. No planning or implementation — this is index maintenance only.

---

## Step 1 — Full Audit

# Tooling command varies by repo — check CLAUDE.md for the correct invocation
# Python repos: python -m codebase_index_tools <command> --format json
# Node repos: node codebase-index-tools/cli.js <command> --format json

Run the full index check:
```bash
python -m codebase_index_tools check --all --format json
```

Parse the JSON output. Report the summary:
- Total indexes checked
- Count of OK / Stale / Missing

If `data.summary.stale === 0` and `data.summary.missing === 0`:
```
INDEX CHECK — ALL CLEAN
─────────────────────────────────────────────────
Total indexes:  [N]
Status:         All OK — no updates needed
─────────────────────────────────────────────────
```
**Stop here. Nothing to do.**

---

## Step 2 — List All Issues

For each result where `status` is `"stale"` or `"missing"`, output:

```
STALE/MISSING INDEXES FOUND
─────────────────────────────────────────────────
```

For each stale entry:
```
STALE: [indexFile]
  Mapping: [mappingId] — [description]
  Last updated: [indexLastUpdated]
  Most recent change: [mostRecentChangedFile] ([mostRecentSourceChange])
  Reason: [reason]
```

For each missing entry:
```
MISSING: [indexFile]
  Mapping: [mappingId] — [description]
  Changed files: [list first 5 changedFiles]
```

---

## Step 3 — Update Stale Indexes

For each stale index:

1. Read the current INDEX.md file.
2. Load index context to understand what changed:
   ```bash
   python -m codebase_index_tools inject --ids [mappingId] --format json
   ```
3. Review the changed files listed in the check results. Read each changed file to understand what was modified.
4. Update the INDEX.md:
   - Update the Directory Map if file structure changed
   - Update the Key Files table if files were added/removed/renamed
   - Update Patterns & Conventions if new patterns were introduced
   - Update Known Gotchas if relevant
   - Update Dependencies if dependency graph changed
   - Set `Last updated:` to today's date (YYYY-MM-DD)
   - Set `Confidence:` based on the depth of your review (High if thorough, Medium if partial)
5. Do NOT rewrite the entire file — only update sections that are actually affected by the changes.

---

## Step 4 — Scaffold Missing Indexes

For each missing index:

1. Preview:
   ```bash
   python -m codebase_index_tools scaffold --source [source-dir-from-mapping-globs] --dry-run --format json
   ```
2. Write:
   ```bash
   python -m codebase_index_tools scaffold --source [source-dir] --output [indexFile-from-mapping]
   ```
3. Fill in the generated stub with accurate content by reading the source directory files.

---

## Step 5 — Verify Clean State

Run the check again:
```bash
python -m codebase_index_tools check --all --format json
```

Must return `data.summary.stale === 0` and `data.summary.missing === 0`.

If clean:
```
INDEX CHECK COMPLETE
─────────────────────────────────────────────────
Total indexes:     [N]
Indexes updated:   [list of updated indexFile paths]
Indexes created:   [list of scaffolded paths, or "none"]
Status:            ALL CLEAN
─────────────────────────────────────────────────
```

If any remain stale or missing after updates, report them with the reason they could not be resolved.
