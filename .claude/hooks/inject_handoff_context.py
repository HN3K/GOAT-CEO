"""SessionStart hook: inject the durable resume anchor into Claude's context.

On session startup, resume, clear, or after compaction (matcher
'startup|resume|clear|compact'), injects the durable resume state via
additionalContext so the CEO immediately knows the current wave state.

Resume privileges MACHINE-READABLE STATE over decaying prose (HARNESS-SELF-REVIEW.md
F1). Two robustness properties are load-bearing here:

  (1) SIZE-COMPLIANT + ALWAYS-READ. F1 also recorded that the injected handoff was
      "TRUNCATED mid-line at the harness boundary". So the injection is kept SMALL,
      ordered CRITICAL-FIRST, and every region is independently capped with an explicit
      truncation marker. Order: banner (with re-read pointer) -> machine facts block ->
      PHASE/NEXT_ACTION -> rest of body -> prose narrative. If the harness cuts the tail,
      the re-read pointer + the authoritative facts + the next action all survive. The
      banner ALWAYS carries the absolute path to re-read from disk, so even a fully
      dropped additionalContext degrades to "go read the file" rather than silent loss.

  (2) FACTS BEFORE NARRATIVE. The hook-owned MACHINE-REFRESH block (git HEAD/branch,
      gates, mission, diagnosis pointers — regenerated every compaction by
      check_precompact.py) is injected first and labelled authoritative; the
      session-handoff prose is injected last and labelled secondary/may-be-stale.

Design contract: FAIL-OPEN on any internal error. Always exit 0.
"""
import json
import os
import re
import sys

MEMORY_DIR = os.environ.get("GOATCEO_MEMORY_DIR", "")
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")

RESUME_STATE_FILE = os.path.join(WORKSPACE, "RESUME-STATE.md")
RESUME_STATE_ABS = RESUME_STATE_FILE

HANDOFF_CANDIDATES = [
    os.path.join(MEMORY_DIR, "session-handoff.md"),
    os.path.join(REPO_ROOT, "session-handoff.md"),
]

# The hook-owned machine block, delimited by check_precompact.py's markers.
MACHINE_RE = re.compile(
    re.escape("<!-- BEGIN MACHINE-REFRESH") + r".*?" + re.escape("END MACHINE-REFRESH -->"),
    re.DOTALL,
)
# Prose ACTIVE block in session-handoff.md
ACTIVE_PATTERN = re.compile(r"(★{3,}.*?(?=\n#{1,3}|\Z))", re.DOTALL)
# Resume essentials to surface first from the CEO body
PRIORITY_LINE_RE = re.compile(r"^\s*(PHASE|NEXT_ACTION|ESCALATIONS)\s*:.*$", re.IGNORECASE | re.MULTILINE)

# Tight per-region budgets — keep the total injection small so the harness never cuts it.
MACHINE_BLOCK_MAX = 1800   # machine block is bounded by construction; this is a safety cap
BODY_MAX_CHARS = 1600      # CEO-authored body (PHASE/TASKS/NEXT_ACTION)
PROSE_MAX_CHARS = 1200     # narrative — secondary, capped tightest

VERIFY_BANNER = (
    "--- RESUME CONTEXT (auto-injected on startup/compact) ---\n"
    "PERSEVERE — this may be a post-compaction resume. Auto-compaction is automatic and "
    "transparent under this harness; it is NOT a stop condition. Do NOT pause, end your turn, "
    "or wait for the operator because context was low — there may be no human present. "
    "Re-ground from the state below, then CONTINUE the work from NEXT_ACTION (anti-drift §9).\n"
    "RE-READ THE SOURCE OF TRUTH: this injected block is intentionally small and may be "
    "truncated; the full anchor on disk is authoritative — read it now if you need more than "
    "what is below: " + RESUME_STATE_ABS + "\n"
    "DOCTRINE #2 — VERIFY BEFORE TRUSTING: the narrative may have decayed, but the "
    "MACHINE-REFRESH block is regenerated from git+sentinels at every compaction and is "
    "authoritative. Reconcile against ground truth — `git log`/`git status` per repo and the "
    "*.GATE sentinels in agent-workspace/ — and trust the machine block + git over the prose.\n"
)

_TRUNC = "\n…[truncated — read the full anchor at " + RESUME_STATE_ABS + "]"


def _cap(text, limit):
    """Truncate to limit, appending an explicit re-read marker when cut."""
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + _TRUNC


def _read_resume_state():
    """Return (machine_part, body_part) injection strings, or (None, None)."""
    try:
        if not os.path.exists(RESUME_STATE_FILE):
            return None, None
        with open(RESUME_STATE_FILE, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None, None
    if not text.strip():
        return None, None

    m = MACHINE_RE.search(text)
    machine_part = None
    if m:
        machine_part = (
            "=== MACHINE FACTS (authoritative; regenerated every compaction) ===\n"
            + _cap(m.group(0).strip(), MACHINE_BLOCK_MAX)
        )
        body = MACHINE_RE.sub("", text).strip()
    else:
        body = text.strip()

    body_part = None
    if body:
        # Surface PHASE / NEXT_ACTION / ESCALATIONS first so they survive any tail cut.
        priority = "\n".join(mo.group(0).strip() for mo in PRIORITY_LINE_RE.finditer(body))
        rest = PRIORITY_LINE_RE.sub("", body).strip()
        composed = (priority + ("\n\n" if priority and rest else "") + rest).strip()
        body_part = (
            "=== RESUME BODY (CEO-authored; PHASE / NEXT_ACTION first) ===\n"
            + _cap(composed, BODY_MAX_CHARS)
        )
    return machine_part, body_part


def _read_active_block():
    """Prose ACTIVE block from session-handoff.md — narrative, injected last."""
    for candidate in HANDOFF_CANDIDATES:
        if not os.path.exists(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        match = ACTIVE_PATTERN.search(text)
        block = match.group(0) if match else text
        return (
            "=== SESSION HANDOFF — NARRATIVE (secondary; may be stale) ===\n"
            + _cap(block.strip(), PROSE_MAX_CHARS)
        )
    return None


def main() -> int:
    try:
        machine_part, body_part = _read_resume_state()
        active_block = _read_active_block()

        # Critical-first ordering: banner (carries re-read pointer) -> facts -> body -> prose.
        parts = [p for p in (machine_part, body_part, active_block) if p]
        if not parts:
            return 0  # nothing to inject

        injection = VERIFY_BANNER + "\n" + "\n\n".join(parts)

        output = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": injection,
            }
        }
        sys.stdout.write(json.dumps(output))
        return 0
    except Exception:
        return 0  # fail open — context injection failure must never block the session


if __name__ == "__main__":
    sys.exit(main())
