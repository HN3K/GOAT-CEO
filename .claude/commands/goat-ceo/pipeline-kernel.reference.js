// ─────────────────────────────────────────────────────────────────────────────
// REFERENCE Workflow kernel for one repo's autonomous execution (Decision A slice).
// The CEO authors a {VARIABLE}-filled copy at Step 3.1 (AFTER intake + plan approval)
// and launches it. This is a reference pattern, not a runnable named workflow.
//
// Correct against the real Workflow API + the 2026-06-15 probe findings:
//   • API: agent(prompt, opts), parallel(thunks), pipeline(items, ...stages), phase(),
//     log(), args, budget. NOT agent({subagent_type, prompt}); NOT parallel([promises]).
//   • NO Node/fs access. The script CANNOT read files or *.GATE sentinels. Cross-phase
//     state flows through agent return values (schema) and the durable journal (resume via
//     resumeFromRunId) — never fs. To get the partition into the script, an agent reads it.
//   • Hooks that fire on Workflow agents (verified): PreToolUse (phase-gate, STOP, registry,
//     commit guard) and SubagentStop (check_artifacts, check_partition) — these still enforce.
//     TaskCompleted hooks do NOT fire — so the test/review gates are explicit STAGES here.
//   • Merge stays CEO-manual (Doctrine #1). The kernel does fan-OUT and ENDS by returning the
//     branch list; the CEO runs §D reconvergence and launches the review kernel. A Workflow
//     can't pause for the CEO, so the fan-out and the merge are deliberately separate runs.
// ─────────────────────────────────────────────────────────────────────────────

export const meta = {
  name: '{REPO_PREFIX}-goat-kernel',
  description: 'Autonomous execution kernel for {REPO_PREFIX}: research -> revise -> implement fan-out. Merge + review are separate CEO-gated runs.',
  phases: [
    { title: 'Research' },
    { title: 'Revise' },
    { title: 'Partition' },
    { title: 'Implement' },
  ],
}

// Agents return structured results because the script has no fs to read artifacts from.
const RESEARCH_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    openIssues: { type: 'number' },
    summary: { type: 'string' },
  },
  required: ['openIssues', 'summary'],
}

const PARTITION_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    valid: { type: 'boolean' },
    reason: { type: 'string' },
    batches: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        properties: {
          id: { type: 'string' },
          branch: { type: 'string' },
          scope: { type: 'string', description: "one-line summary of this batch's files[]" },
          blockedBy: { type: 'array', items: { type: 'string' } },
        },
        required: ['id', 'branch', 'scope', 'blockedBy'],
      },
    },
  },
  required: ['valid', 'reason', 'batches'],
}

const IMPL_SCHEMA = {
  type: 'object', additionalProperties: false,
  properties: {
    filesChanged: { type: 'array', items: { type: 'string' } },
    committed: { type: 'boolean' },
    notes: { type: 'string' },
  },
  required: ['filesChanged', 'committed', 'notes'],
}

// ── Phase: Research (parallel fan-out) ───────────────────────────────────────
phase('Research')
const research = await parallel([
  () => agent(`[Codebase Researcher template §6, variables filled. Cite file:line for every claim. Return the count of open issues you could not resolve.]`,
              { label: 'research:codebase', agentType: 'team-researcher', schema: RESEARCH_SCHEMA }),
  () => agent(`[Technical Researcher template §7, variables filled. Cite file:line. Return open-issue count.]`,
              { label: 'research:technical', agentType: 'team-researcher', schema: RESEARCH_SCHEMA }),
])
const openIssues = research.filter(Boolean).reduce((n, r) => n + (r.openIssues || 0), 0)
log(`research complete: ${openIssues} open issue(s) across both framings`)

// ── Phase: Revise (architect reconciles findings; emits the partition manifest) ──
// The architect HAS file tools, so it writes PLAN.md + IMPLEMENTATION-MANIFEST.{md,json}.
// Its SubagentStop check_partition.py gate (verified to fire on Workflow agents) blocks an
// invalid partition before this agent can stop.
phase('Revise')
await agent(
  `[Architect revision pass §5: read RESEARCH-LOG.md, resolve every annotation, and (re)emit
    agent-workspace/IMPLEMENTATION-MANIFEST.json with disjoint independent batches. ${openIssues}
    issue(s) were found — drive them to zero before finishing. Do NOT write any *.GATE file.]`,
  { label: 'architect:revise', agentType: 'team-architect' },
)

// ── Phase: Partition (read the manifest INTO the script — agents have fs, the script does not) ──
phase('Partition')
const part = await agent(
  `Read agent-workspace/IMPLEMENTATION-MANIFEST.json and return its batches as structured output:
   per batch its id, branch (worktree-<name>), a one-line scope summary, and blockedBy[]. Set
   valid=false with a reason if the file is missing or its independent batches overlap on files.`,
  { label: 'partition:read', agentType: 'team-researcher', schema: PARTITION_SCHEMA },
)
if (!part || !part.valid) {
  throw new Error(`Partition invalid: ${part ? part.reason : 'no result'} — fix IMPLEMENTATION-MANIFEST.json before implementing.`)
}
log(`partition: ${part.batches.length} batch(es)`)

// ── Phase: Implement (worktree fan-out over INDEPENDENT batches) ──────────────
// Each implementer runs in its own worktree (isolation:'worktree') so concurrent edits never
// collide; it commits to worktree-<name> only — never main. Stacked (blockedBy) batches are
// deferred to the CEO's bottom-up land (§D), since they depend on prior branches being merged.
phase('Implement')
const independent = part.batches.filter(b => (b.blockedBy || []).length === 0)
const dependent   = part.batches.filter(b => (b.blockedBy || []).length > 0)
if (dependent.length) log(`${dependent.length} stacked batch(es) deferred to the CEO bottom-up land`)

const built = await parallel(
  independent.map(b => () =>
    agent(`[Implementer template §8 for batch ${b.id} (${b.scope}). Commit to your worktree branch
            ${b.branch} ONLY — never main. Report your file list.]`,
          { label: `implement:${b.id}`, agentType: 'team-implementer', isolation: 'worktree', schema: IMPL_SCHEMA })
      .then(r => (r ? { batchId: b.id, branch: b.branch, ...r } : null))
  )
)
const branches = built.filter(Boolean)

// ── Merge handoff: the kernel STOPS; the CEO owns reconvergence ───────────────
log(`fan-out complete: ${branches.length} worktree branch(es) ready for the CEO merge step`)
return {
  ready: 'merge',
  branches,
  stacked: dependent.map(b => ({ id: b.id, branch: b.branch, blockedBy: b.blockedBy })),
  nextCeoSteps: [
    'Run §D: per-branch scope verify -> speculative-batch merge -> broad suite ONCE -> land or bisect.',
    'Land stacked batches bottom-up (restack on each land).',
    'Write agent-workspace/IMPLEMENT.GATE after a clean land.',
    'Launch the review kernel (see §17 of templates.md); on judge PASS write REVIEW.GATE.',
  ],
}
