"""Shared strict-mode + fail-open-logging helpers for GOAT-CEO hooks (C20).

Design contract (mirrors GOAT-CEO-HARDENING-PLAN.md §5.3 C20):

  - The harness is FAIL-OPEN by default: a hook bug / crash must never block
    legitimate work. Strict mode does NOT change that — a hook that hits an
    internal exception STILL allows (exit 0). Failing closed on a *crash* would
    brick every worktree mid-batch.

  - What strict mode DOES change: *documented degraded-allow* paths — places where
    a gate today allows because its CONFIG is missing. Currently the only integrated
    path is the test gate's no-config branch (check_test_gate.py): with no TEST-CONFIG
    /TEST-COMMAND it normally warns+allows, but in strict mode it BLOCKS, because for
    an unattended / high-risk run "I couldn't evaluate the test gate" should halt, not
    wave through. This helper is shared so other degraded-allow paths can opt in the
    same way; STOP and secret-write are NOT among them — they are already unconditional
    blocks and do not consult strict mode.

  - Every fail-open / degraded-allow event is appended to
    agent-workspace/HOOK-FAILURES.jsonl so an operator can SEE when enforcement
    silently degraded (the plan's "visible warning artifact").

Enable strict mode by either:
  - creating the sentinel file  agent-workspace/STRICT_MODE   (any contents), or
  - setting the env var         GOAT_CEO_STRICT=1

Both checks are exception-safe and default to NON-strict (fail-open) on any error.
"""
import json
import os
import time

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_WORKSPACE = os.path.join(_REPO_ROOT, "agent-workspace")
_STRICT_SENTINEL = os.path.join(_WORKSPACE, "STRICT_MODE")
_FAILURES_LOG = os.path.join(_WORKSPACE, "HOOK-FAILURES.jsonl")


def strict_mode() -> bool:
    """True if strict mode is enabled via sentinel file or env var. Never raises."""
    try:
        if os.path.exists(_STRICT_SENTINEL):
            return True
        val = os.environ.get("GOAT_CEO_STRICT", "").strip().lower()
        return val in ("1", "true", "yes", "on")
    except Exception:
        return False


def log_failopen(hook: str, reason: str, extra: dict | None = None) -> None:
    """Append a degraded/fail-open event to agent-workspace/HOOK-FAILURES.jsonl.

    Best-effort and bulletproof: any error here is swallowed so the logging itself
    can never break a hook (which would reintroduce the crash-bricks-session mode).
    """
    try:
        rec = {
            "ts": time.time(),
            "hook": hook,
            "reason": reason,
            "strict": strict_mode(),
        }
        if isinstance(extra, dict):
            rec.update(extra)
        os.makedirs(_WORKSPACE, exist_ok=True)
        with open(_FAILURES_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")
    except Exception:
        pass
