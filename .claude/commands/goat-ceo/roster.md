# GOAT-CEO — Agent Roster
> Authoritative agent-to-phase map. Single source of truth — do not duplicate in goat-ceo.md.
> Last updated: 2026-06-13 (rework). Reference: GOAT-CEO-REWORK-DESIGN.md §F.

---

## Roster Table

| Agent file | Model | Phase | CEO deploys when | Hard constraints (frontmatter / settings) | Soft notes |
|---|---|---|---|---|---|
| `team-roadmap-architect` | opus | Pre-1 (initiative start) + Post-6 (milestone close) + type-3 (reshape) | **Type-1:** initiative starts, no roadmap exists — spawn once to create. **Type-2:** Phase 6 Finalize reports a closed M-NN milestone — spawn to flip status + advance successors. **Type-3:** operator authorizes a re-shape — spawn with candidate milestone IDs. | `disallowedTools: Agent` (cannot spawn sub-agents — routes researcher requests to CEO as Open questions). Writes only roadmap file + scratch artifact + `agent-workspace/`. No production code. | Three distinct invocation types — pass the type explicitly in the spawn prompt (templates §1/2/3). Type-2 is mechanical; judgment re-shaping is type-3 only, never type-2. |
| `team-architect` | opus | 1 — Plan + 2 — Research revision | Phase 1 start; re-engaged after each research iteration to resolve annotations and produce the revised manifest on LOOP_EXIT. | No hard constraints beyond role default. Writes `agent-workspace/PLAN.md` and `IMPLEMENTATION-MANIFEST.md` only; does not write production code. | PLAN.md must reference the roadmap milestone ID (if one exists) and must not weaken milestone Acceptance criteria. The `SubagentStop` hook (`check_artifacts.py`) blocks if PLAN.md is absent at agent stop. |
| `team-researcher` | opus | 2 — Research | Phase 2 — spawned x2 in parallel (codebase framing + technical framing). Re-spawned if research loop iterates. | No hard constraints beyond role default. Read-heavy; does not modify production files. | Spawn both simultaneously (fan-out). Each must cite file:line for every claim. Findings marked SINGLE-SOURCE require independent corroboration in Phase 5 review. The completeness critic tracks unverified SINGLE-SOURCE items. |
| `team-implementer` | sonnet | 3 — Implement + 4 — Index (reuse) | Phase 3: spawned per batch per the manifest. Phase 4: re-spawned as index-updater on **merged main only** (no worktree). | **`isolation: worktree`** (parallel batches get isolated git worktrees — prevents cwd collision). **`maxTurns: 30`** (hard cap; no marathon turns). **`disallowedTools: Agent`** (cannot spawn sub-subagents). `git push`, `git add -A`, `git add .`, `git commit` denied by project `settings.json` — reports file list; CEO commits. | Phase 4 (index) reuses this agent type but WITHOUT `isolation: worktree` — must run on merged main. Checkpoint-and-yield contract is embedded in every spawn prompt (templates §8/10). IMPLEMENTER REPORT format required (branch name + explicit file list). |
| `team-verifier` | sonnet | 5 — Review + §D per-branch pre-merge review | Phase 5: spawned x2 simultaneously (Reviewer A = correctness perspective, Reviewer B = test-quality perspective). Also spawned per worktree branch during the CEO merge step (§D) for a pre-merge diff check before each merge. | **`disallowedTools: Write, Edit`** on production paths (writes to `agent-workspace/` only). **`maxTurns: 20`** (hard cap). | Reviewers must produce a structured JSON verdict block — the judge and the `check_review_gate.py` hook parse it. The tool-call audit hook (`check_toolcall_audit.py`, a `SubagentStop` hook) counts the reviewer's Read/Grep/Bash calls in its own transcript (A/B reviewers only); insufficient reads block the reviewer's stop. Each reviewer MUST run at least one runtime check the implementer did not report. |
| `team-overseer` | opus | All phases (per-repo coordinator) | One per repo in a multi-repo CEO wave. Spawned at session start for each repo in scope; runs for the life of that repo's pipeline. | `disallowedTools: AskUserQuestion`. **Direct spawn authority**: Overseer spawns `team-architect`, `team-researcher`, `team-implementer`, `team-verifier` directly via the Agent tool — no CEO relay required. CEO-exclusive: Overseer does NOT spawn `team-ceo-assistant` or `team-cross-reviewer`; those are CEO-only. | Assessment-First: the overseer orients and assesses before spawning any pipeline agent. Investigation-only tasks are handled directly without activating the pipeline. Cross-repo flags must include Tier 1 or Tier 2 classification. Phase completions and cross-repo flags reported to CEO. |
| `team-ceo-assistant` | opus | On-demand — Tier-2 cross-repo assessment | When a Tier-2 (potentially breaking) cross-repo flag fires. Also spawned on REQUEST flow (Overseer needs info from another repo). Read-only scout against the OTHER repo's actual files. | **`permissionMode: plan`** — hard read-only enforced by harness; cannot Write, Edit, or run mutations regardless of what the prompt says. Replaces the prior prose "you are read-only" which was soft-only. | Reports to CEO only; CEO relays to the Overseer and (when relevant) to the log. A CEO-Assistant that issues UNCLEAR must explain what additional access would resolve it — the CEO then decides whether to escalate to the operator or accept ambiguity. |
| `team-cross-reviewer` | sonnet | Post-6 — cross-repo contract verification | After ALL repos in a related group complete their Phase 6. Spawned once per related group. The CEO's `Stop` hook blocks pipeline-complete declaration if any MISMATCH result exists. | Reports to CEO only; does not write to production files or contact Overseers. Writes only a report message. | Verification checklist: API contracts, shared data models, configuration, breaking changes, cross-repo-flags.md. A MISMATCH finding requires exact file:line + actual values from each repo (not a description). UNTESTED is allowed when access is genuinely unavailable, but must state why. |
| `team-ceo-scribe` | haiku | (session) — REMOVED | — | — | **REMOVED from routine use.** The `claude agents` view + OTEL timeline cover session observability natively. Agent file renamed to `.md.REMOVED` so it is not loaded by Claude Code. Cross-repo Tier-2 decisions are logged directly by the CEO as short entries in `logs/<prefix>/cross-repo.log` (canonical path — also used by protocols.md and goat-ceo.md). |

---

## Lightweight roles (not separate agent files — spawn inline)

| Role | Model | Phase | Spawn as | Notes |
|---|---|---|---|---|
| **completeness-critic** | haiku | 5 — after dual review | Inline Agent call with `tools: Read, Grep` and the §13 template as prompt | Runs after both reviewer verdicts are in `REVIEW-LOG.md`. Emits JSON list of silent gaps (acceptance criteria mentioned by neither reviewer). Fast and cheap — no human-visible delay in normal execution. |
| **judge** | opus | 5 — after completeness critic | Inline Agent call with `tools: Read` only and the §14 template as prompt | Issues the binding verdict JSON. Explicitly prompted to escalate severity on weak/uncited findings and to treat SINGLE-SOURCE findings without corroboration as gaps. The `check_review_gate.py` hook parses the verdict JSON; exit 2 blocks task completion on FAIL. |

---

## Deployment rules summary

**Single-repo pipeline (no CEO):** use `team-overseer` to coordinate phases 1–6 directly.

**Multi-repo CEO wave:** CEO spawns one `team-overseer` per repo, monitors via `claude agents` view
and `agent-workspace/STATUS.md` heartbeats. CEO is the single committer (Doctrine #1).

**`isolation: worktree` rule:** apply ONLY when ≥2 implementers run in parallel with uncertain or overlapping file sets. Single implementer or disjoint-by-construction batches = no isolation (worktree has setup cost; overkill for one agent). Index Updater (Phase 4) ALWAYS runs on merged main without isolation — index race otherwise.

**Parallel fan-out pairs:**
- Research phase: researcher-codebase + researcher-technical (always parallel)
- Review phase: reviewer-a + reviewer-b (always parallel) — plus **reviewer-c (standards lens, RUBRIC-AVAILABLE repos ONLY)** which runs rubric's own `rubric enforce --verify` (templates §12a; `reviewer:"C"` → naturally audit-exempt) — followed by completeness-critic + judge (sequential after the verdicts exist). The judge composes Review C: rubric `blocking_violations` are facts → FAIL; `verified_advisory` is an already-verified standards lens to weigh.
- Implement batches: parallel only when no shared files; otherwise sequenced with `addBlockedBy`

**Phase gate enforcement:** each phase writes a `*.GATE` sentinel when complete. The `check_phase_gate.py` PreToolUse hook blocks Write/Edit/Bash until the prior phase's gate exists. Do not manually delete gate sentinels — write `agent-workspace/STOP` to halt a pipeline cleanly instead.

**Review iteration cap:** `REVIEW-ITERATION.txt` tracks how many times Phase 5 has run. After iteration 2, the judge sets `escalate_required: true`. The `check_review_gate.py` hook writes `ESCALATE_REQUIRED` and surfaces to the operator rather than looping again.
