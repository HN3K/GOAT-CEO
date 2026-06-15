"""SessionStart hook: inject the durable resume anchor into Claude's context.

On session startup, resume, clear, or after compaction (matcher
'startup|resume|clear|compact'), injects the durable resume state via
additionalContext so the CEO immediately knows the current wave state.

Resume privileges MACHINE-READABLE STATE over decaying prose (a live-run lesson: a prose
handoff decayed within hours while git + sentinels stayed true). Two robustness properties
are load-bearing here:

  (1) SIZE-COMPLIANT + ALWAYS-READ. That same run showed the injected handoff could be
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

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")

# Claude Code stores per-project auto-memory under ~/.claude/projects/<slug>/memory, where
# <slug> is the project path with every non-alphanumeric char replaced by '-'. Derive it
# rather than hardcoding one machine's path (the old hardcoded path silently no-op'd on any
# other machine). HANDOFF_CANDIDATES also falls back to a repo-root session-handoff.md, so a
# slug miss degrades gracefully to "nothing injected", never an error.
_PROJECT_SLUG = re.sub(r"[^A-Za-z0-9]", "-", REPO_ROOT)
MEMORY_DIR = os.path.join(os.path.expanduser("~"), ".claude", "projects", _PROJECT_SLUG, "memory")

RESUME_STATE_FILE = os.path.join(WORKSPACE, "RESUME-STATE.md")
RESUME_STATE_ABS = RESUME_STATE_FILE
AUTONOMOUS_ACTIVE_FILE = os.path.join(WORKSPACE, "AUTONOMOUS-ACTIVE")

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

def _engaged(session_id):
    """True iff keep-going (unattended mode) is engaged for THIS session. Mirrors
    check_pipeline_complete._autonomous_engaged. Used to make the resume banner mode-aware."""
    try:
        if not os.path.exists(AUTONOMOUS_ACTIVE_FILE):
            return False
        with open(AUTONOMOUS_ACTIVE_FILE, "r", encoding="utf-8") as fh:
            content = fh.read().strip()
        if "session:" in content:
            return any(
                ln.strip().startswith("session:") and session_id
                and ln.strip()[len("session:"):].strip() == session_id
                for ln in content.splitlines()
            )
        return True
    except Exception:
        return False


def _verify_banner(engaged):
    """Resume banner. The perseverance / never-stop language is injected ONLY when keep-going
    is engaged (Unattended mode). In the default Collaborative mode it is neutral — the CEO
    resumes and yields at phase boundaries as normal, NOT 'never stop'."""
    lead = (
        "PERSEVERE — this may be a post-compaction resume of an UNATTENDED run. Auto-compaction "
        "is automatic, transparent, and NOT a stop condition: do NOT pause, end your turn, or "
        "wait for the operator because context was low. Re-ground from the state below, then "
        "CONTINUE from NEXT_ACTION (see commands/goat-ceo/unattended-mode.md §3).\n"
    ) if engaged else (
        "This may be a resume or post-compaction restart. Auto-compaction is transparent and "
        "lossless — re-ground from the state below and continue the current phase. You are in "
        "Collaborative mode: yield to the operator at phase boundaries as normal.\n"
    )
    return (
        "--- RESUME CONTEXT (auto-injected on startup/compact) ---\n"
        + lead +
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


def _keepgoing_status(session_id):
    """Loud ON/OFF line so the OFF state can never be silently forgotten (the failure that
    let the CEO stop at low context: AUTONOMOUS-ACTIVE was never created, so keep-going was
    dormant)."""
    try:
        engaged = False
        scoped = False
        if os.path.exists(AUTONOMOUS_ACTIVE_FILE):
            with open(AUTONOMOUS_ACTIVE_FILE, "r", encoding="utf-8") as fh:
                content = fh.read().strip()
            if "session:" in content:
                scoped = True
                engaged = any(
                    ln.strip().startswith("session:") and session_id
                    and ln.strip()[len("session:"):].strip() == session_id
                    for ln in content.splitlines()
                )
            else:
                engaged = True
        if engaged:
            return "KEEP-GOING: ON — you will NOT yield to the operator between turns. To stop, write a yield marker (AWAITING-OPERATOR / SESSION-COMPLETE / ESCALATE_REQUIRED) or the operator writes STOP.\n"
        note = " (a session:<id> scope is set for a different session)" if scoped else ""
        sid = ("  Your session id: " + session_id) if session_id else ""
        return (
            "KEEP-GOING: OFF" + note + " — you WILL yield to the operator between turns and "
            "low-context stopping is NOT prevented. If this is meant to be an UNATTENDED run, "
            "create agent-workspace/AUTONOMOUS-ACTIVE now (empty = all sessions, or a line "
            "'session:<your-id>' to scope it to you), or run scripts/autonomous-on.ps1." + sid + "\n"
        )
    except Exception:
        return ""


def main() -> int:
    try:
        raw = sys.stdin.read()
        try:
            data = json.loads(raw) if raw.strip() else {}
        except Exception:
            data = {}
        session_id = str(data.get("session_id", "") or "")

        machine_part, body_part = _read_resume_state()
        active_block = _read_active_block()

        # Critical-first ordering: banner (carries re-read pointer) -> facts -> body -> prose.
        parts = [p for p in (machine_part, body_part, active_block) if p]
        if not parts:
            return 0  # nothing to inject

        injection = _verify_banner(_engaged(session_id)) + _keepgoing_status(session_id) + "\n" + "\n\n".join(parts)

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
