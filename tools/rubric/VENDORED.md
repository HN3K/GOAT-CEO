# Vendored: rubric

This directory is a **vendored snapshot** of the `rubric` standards-grounding tool, bundled into
GOAT-CEO so a fresh clone can use the optional rubric integration **without obtaining rubric
separately**. GOAT-CEO drives rubric via its CLI; this is the source that provides that CLI.

- **Source project:** the first-party `rubric` project (vendored here from a local checkout; no public remote yet)
- **Vendored commit:** `7d0041b6144eed678fade9c14acb08e05648332b`
- **Vendored on:** 2026-06-15
- **License:** MIT (same as GOAT-CEO — first-party code)

## Install (puts the `rubric` CLI on your PATH)

```bash
pip install -e "tools/rubric[gate,retrieval]"
# Optional extras: ast-grep (external binary) for multi-language structural rules;
#                  `radon` (`pip install -e "tools/rubric[gate,retrieval,metrics]"`) for `measure`.
```

After install, GOAT-CEO detects rubric at intake (`RUBRIC-AVAILABLE`) and the grounding → gate →
Reviewer-C → measure chain activates. To enable rubric for a target repo, run `rubric init --no-claude`
in it (scaffolds `.rubric/`). See `README.md` → Standards grounding and `GOAT-CEO-REWORK-DESIGN.md §I`.

## Updating (re-vendoring)

Do **not** edit files in this directory — edit the upstream `rubric` repo and re-vendor:

```bash
git -C <rubric-repo> archive HEAD | tar -x -C tools/rubric
```

Then update the **Vendored commit** hash above. `git archive` exports only tracked files (no `.git`,
no caches), so the snapshot stays clean.
