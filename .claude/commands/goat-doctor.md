---
description: Validate that the GOAT-CEO harness is actually enforcing — interpreter, hook wiring, and live block/allow behavior of every gate.
---

# /goat-doctor — does the enforcement layer actually work?

GOAT-CEO's hooks are **fail-open**: if `python` isn't on PATH, or `$CLAUDE_PROJECT_DIR`
isn't expanded, or a hook crashes, the gate silently becomes a no-op and every **Gate row**
degrades to advisory. (The **Hard** `permissions.deny` rules survive — Claude Code enforces
them itself, independent of the interpreter.) `/goat-doctor` proves — rather than assumes —
that the Gate enforcement is live.

Run it after install, after a Claude Code upgrade, or any time you want to trust the gates.

## What to run

```bash
python .claude/hooks/selftest_all.py
```

It exits non-zero if ANY gate misbehaves, and prints a PASS/FAIL line per check.

## What it checks

1. **Environment**
   - `python` resolves and is ≥ 3.8 (the literal `python` token the hooks invoke).
   - `.claude/settings.json` parses as valid JSON.
   - `$CLAUDE_PROJECT_DIR` note: every hook command uses it; confirm your Claude Code
     build expands it (else replace with an absolute path).
   - `CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1` is set (the agent-teams events that several
     gates ride on only fire under this flag).

2. **Fail-open contract** — every `*.py` hook exits 0 on empty and garbage stdin (a hook
   bug must never block legitimate work).

3. **Live gate behavior** (crafted payloads, asserts the exit code):
   - STOP kill switch blocks when `agent-workspace/STOP` exists, allows when absent.
   - `guard_git_commit` blocks sweep adds (`git add -A`, `git -C <path> add -A`, `:/`,
     `-u`, `*`) and allows scoped pathspec adds.
   - `guard_secrets` blocks writes to secret-bearing paths (`.env*`, `*.pem`, `id_rsa`,
     …) and allows normal source files.
   - test gate blocks a failing/timed-out/hollow suite, allows a passing one, and (no
     config) allows in normal mode but **blocks in STRICT mode**.
   - artifact gate blocks an implementer that produced no provable work, allows one that
     moved HEAD / left changes / wrote an IMPLEMENTER-RESULT.json.
   - review gate requires a **judge-attributed** PASS; a reviewer-only PASS is rejected.
   - span validity blocks an A/B reviewer that cited no structured spans or quoted a
     non-existent line; partition gate blocks overlapping batches.

## Interpreting results

- **All PASS** → the harness is enforcing. Gate rows are live; the **Hard** `permissions.deny`
  rules are mechanical regardless of the interpreter.
- **Any FAIL on the fail-open contract** → a hook has a bug; it could block real work. Fix
  before relying on the system.
- **Any FAIL on gate behavior** → that specific guarantee is NOT being enforced as claimed;
  treat it as advisory until fixed (see `docs/enforcement-truth-table.md`).
- **Environment FAIL (no python / unexpanded var)** → *all* gates are silently inert. This
  is the single most common "I thought it was enforcing" failure.

Strict-mode runs (`agent-workspace/STRICT_MODE` present or `GOAT_CEO_STRICT=1`) additionally
turn documented degraded-allow paths into hard stops and log every fail-open event to
`agent-workspace/HOOK-FAILURES.jsonl`.
