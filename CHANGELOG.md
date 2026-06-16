# Changelog

All notable changes to GOAT-CEO are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

GOAT-CEO is **experimental, pre-release** software with no published releases or tags; it is run
from a clone of `master`. The section below records the in-progress hardening pass rather than a
shipped version.

## [Unreleased]

A hardening pass (items **C1–C21**) responding to an external review. The headline of that review
held — every `settings.json` hook resolves to a real, fail-open script and nothing is mis-wired —
so this pass is about **closing the gap between claimed and enforced guarantees**, making gates
harder to false-pass, and making the docs honest about what is hard vs. soft. See
[`GOAT-CEO-HARDENING-PLAN.md`](GOAT-CEO-HARDENING-PLAN.md) for the full verdict table and evidence,
and [`docs/enforcement-truth-table.md`](docs/enforcement-truth-table.md) for the per-rule
hard/gate/advisory map.

### Added

- **Enforcement truth table** (`docs/enforcement-truth-table.md`) — one row per real enforcement
  rule: hard / gate / advisory, what enforces it, whether it is fail-open, whether it is self-tested,
  and known bypasses/limits. The single highest-leverage honesty doc (C13/C18 consolidation).
- **`CHANGELOG.md`** (this file) and a **Compatibility matrix** in the README (Claude Code version,
  OS, Python ≥ 3.11, agent-teams flag, hook status), with an explicit experimental/pre-release
  notice (C12).
- **Plain-language effort-tier vocabulary** in the README and `goat-ceo.md` — **three** tiers
  (Direct → Standard → Full CEO), not an L0–L5 ladder; the CEO picks the smallest safe tier (C21).
- **Decision-visibility artifact** (`agent-workspace/ASSESSMENT.md`) — when the CEO chooses a reduced
  (Direct) path that skips the pipeline, it records the chosen tier and why, so "the system did less"
  is auditable instead of silent (C19).
- **`selftest_all.py`** (hook self-test harness, added separately) — simulates payloads for the gates
  and asserts expected block/allow; referenced by the enforcement truth table's "Self-tested?" column.
  It is invoked via the `/goat-doctor` command (run manually), **not** automatically at session start
  — the session-start self-check is a separate live-fire STOP probe in `goat-ceo.md` Step 1.0a (C10).
- **`/goat-doctor` command** (`.claude/commands/goat-doctor.md`) — validates the hook interpreter,
  `settings.json` parsing, and the live block/allow behavior of every gate via `selftest_all.py`.
- **`startHead`/`IMPLEMENTER-RESULT.<batchId>.json`** evidence-of-work for the implementer artifact
  gate, replacing the always-passing `git log --oneline -1` probe (C1).
- **`JUDGE-VERDICT.json`** as the single role-attributed source the review gate reads, instead of
  "last PASS block wins" (C5).
- **`TEST-CONFIG.json`** structured test gate (target-repo `workingDirectory`, a list of required
  commands each with its own `timeoutSeconds`, plus a zero-test "hollow pass" rejection); when no
  config is present it emits a loud `TEST-GATE-DEGRADED` warning to stderr and an entry in
  `HOOK-FAILURES.jsonl` (and becomes a hard block under strict mode) (C3).
- **`ceo-commit.ps1`** PowerShell commit wrapper alongside `ceo-commit.sh` for the Windows-primary
  repo (C16).
- **Opt-in strict / fail-closed mode** (`STRICT_MODE` sentinel) plus a `HOOK-FAILURES.jsonl` audit
  trail of every fail-open event — fail-closed on policy violations/missing artifacts only, never on
  a hook crash (C20).

### Changed

- **`team-implementer`** now commits atomically to its own `worktree-<name>` branch; the docs were
  corrected to describe this accurately instead of "cannot commit" (C13).
- **Phase-0 plan gate and mandatory intake** are now explicitly labeled **SOFT BY DESIGN** (CEO
  behavioral conventions, not harness-enforced plan-mode locks) in the README, `rules.md`, and the
  truth table — behavior unchanged, honesty improved (C18).
- **"Lossless" resume wording** replaced everywhere in the public docs with "durable, machine-grounded
  resume across compaction (git state + sentinels + a compact machine-refresh block)" — the
  machine-verifiable floor is preserved; running narrative is capped and can decay (C11).
- **Reviewer read-floor** tied to the declared scope / changed-file set instead of 5 arbitrary tool
  calls (C6); **citation spans** are now mandatory per A/B verdict and validated within a line window
  rather than substring-anywhere (C7).
- **Partition disjointness** hardened: case-fold + `./` normalization, directory-containment overlap
  detection, expanded manifest schema, and hard-blocking coordinator/shared-resource conflicts (C8).
- **Test gate** runs from the target repo/worktree `cwd` (not the GOAT-CEO root) and treats a timeout
  as BLOCK/ESCALATE rather than allow (C3).
- **STOP kill switch** path set derived from `repo-registry.json`, so when the hook fires it honors a
  STOP dropped in any registered repo — not just GOAT-CEO's. With the default `teammateMode:
  in-process`, in-session teammates inherit GOAT-CEO's project hooks and are covered with no extra
  wiring; a genuinely separate session rooted in another repo still needs the hook wired at user scope
  (or in that repo) — the derived path list does not by itself wire the hook, and there is no
  auto-installer for it (C9).

### Fixed

- **`README.md` "denied by commit/push by permission rules"** — this was false. Commit/push are
  warn-only via `guard_git_commit.py`; there is no `permissions.deny` for commit. Corrected to
  warn-enforced + single-committer convention (C13).
- **Git-sweep bypasses** in `guard_git_commit.py`: the add-guard now matches intervening global flags
  (notably `git -C <path> add -A`, which could stage in *other* repos), `git add -u`, `git add :/`,
  `git add ./`, and `git add *` (C15).
- **Stale `ceo-commit.sh` header** referencing a removed `permissions.allow`/`git commit` deny pair
  (C13).
- **`IMPLEMENTATION-MANIFEST.md` (human narrative) vs `IMPLEMENTATION-MANIFEST.json` (machine-checked
  disjoint partition)** distinction documented consistently (C13).
- **Narrow secret-file deny** broadened beyond `**/.env` to cover `.env.*`, `.npmrc`, `.pypirc`,
  `secrets.json`, `*.pem`/`*.key`/`id_rsa*`, `.aws/credentials`, and `appsettings.*.json` (C14).
- **Read-only reference repos** hard-protected with per-session `Write/Edit` denies generated from
  `repo-registry.json`, instead of briefing-only (C17).

> **Note:** several items above (C1, C3, C5, C6, C7, C8, C9, C14, C15, C16, C17, C20) are mechanical
> changes to Python hooks, `settings.json`, and agent definitions delivered in companion batches of
> this same pass; this changelog records the whole pass for honesty. This documentation batch (B4)
> delivers the prose items — C11, C13 (doc portion), C18, C19, C21, the C12 doc portion, and the
> enforcement truth table.
