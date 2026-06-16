"""PostToolUse hook (Edit|Write): CAPPED rubric self-heal gate — TARGET-REPO opt-in.

Wraps `rubric check <edited-file>` so a blocking standards violation is fed back to Claude to
self-heal in real time — BUT with a per-file heal cap so an un-satisfiable rule cannot thrash an
implementer into its `maxTurns` / turn-budget (the R-A risk in GOAT-CEO-REWORK-DESIGN.md §I.5).
rubric's raw PostToolUse hook has NO such cap; this wrapper adds it.

Per edited code file:
  - run `rubric check <file> --kb .rubric/kb` (deterministic, no LLM);
  - CLEAN -> clear the file's heal counter, allow (exit 0);
  - BLOCKING + attempts < CAP -> increment the counter, exit 2 (Claude self-heals on the stderr);
  - BLOCKING + attempts >= CAP -> exit 0 (DEGRADE to advisory) and append the unresolved violation to
    agent-workspace/RUBRIC-DEGRADED.md, so the CEO's RUBRIC.GATE still catches it at integration. The
    implementer is never thrashed past the cap.

INSTALL into a TARGET repo's `.claude/settings.json` (NOT the GOAT-CEO meta-repo) as a PostToolUse
`Edit|Write` hook, for RUBRIC-AVAILABLE repos that opt into real-time heal. The DEFAULT GOAT-CEO flow
uses the CEO-run RUBRIC.GATE at integration instead (no real-time hook); this wrapper is the opt-in
upgrade for repos that want in-loop correction with the thrash-guard.

Design contract: FAIL-OPEN. Needs `rubric` on PATH + a `.rubric/kb`; absent -> allow. stdlib only.
exit 0 = allow; exit 2 = self-heal (stderr shown to the model).
"""
import datetime
import json
import os
import re
import subprocess
import sys

CAP = 2  # max self-heal cycles per file before degrading to advisory
CODE_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".sql", ".rs", ".rb", ".java"}

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
COUNTER_PATH = os.path.join(WORKSPACE, "RUBRIC-HEAL.json")
DEGRADED_PATH = os.path.join(WORKSPACE, "RUBRIC-DEGRADED.md")

# Enforcement audit log (logs/ is gitignored — local trail, not published). Self-contained
# inline append so this hook stays a single portable file when copied into a target repo;
# it mirrors scripts/log_capability.py's schema so both writers share one log format.
ENFORCEMENT_LOG = os.path.join(REPO_ROOT, "logs", "rubric-enforcement.jsonl")
_RULE_RE = re.compile(r"\[(?:ast-grep|ruff|rubric)\s+([^\]]+)\]")


def _log_enforcement(file_path, action, detail):
    """Record that rubric ENFORCED a standard (caught a blocking violation). Fail-open."""
    try:
        rec = {
            "ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "log": "rubric-enforcement", "source": "heal-gate", "action": action,
            "repo": REPO_ROOT, "rules": sorted(set(_RULE_RE.findall(detail or ""))),
            "files": [file_path],
        }
        if detail:
            rec["detail"] = detail[:400]
        os.makedirs(os.path.dirname(ENFORCEMENT_LOG), exist_ok=True)
        with open(ENFORCEMENT_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass  # logging must NEVER break the hook


def _load_counters():
    try:
        with open(COUNTER_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_counters(c):
    try:
        os.makedirs(WORKSPACE, exist_ok=True)
        with open(COUNTER_PATH, "w", encoding="utf-8") as fh:
            json.dump(c, fh)
    except OSError:
        pass


def _has_blocking(file_path, cwd):
    """Return (is_blocking, detail). Testable seam: RUBRIC_HEAL_TEST_FORCE=block|clean bypasses rubric."""
    forced = os.environ.get("RUBRIC_HEAL_TEST_FORCE")
    if forced == "block":
        return True, "TEST forced block"
    if forced == "clean":
        return False, ""
    try:
        result = subprocess.run(
            ["rubric", "check", file_path, "--kb", ".rubric/kb"],
            cwd=cwd, capture_output=True, text=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return False, ""  # rubric absent / errored — fail open (no block)
    # `rubric check` exits 1 on a blocking violation, 0 otherwise.
    if result.returncode == 1:
        return True, (result.stdout or "").strip()[-1200:]
    return False, ""


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        tool_input = data.get("tool_input") or {}
        file_path = tool_input.get("file_path") or ""
        cwd = data.get("cwd") or REPO_ROOT
        if not file_path:
            return 0
        if os.path.splitext(file_path)[1].lower() not in CODE_SUFFIXES:
            return 0  # not a gated code file

        is_blocking, detail = _has_blocking(file_path, cwd)
        counters = _load_counters()

        if not is_blocking:
            if file_path in counters:  # file now clean — clear its counter
                counters.pop(file_path, None)
                _save_counters(counters)
            return 0

        attempts = int(counters.get(file_path, 0))
        if attempts < CAP:
            counters[file_path] = attempts + 1
            _save_counters(counters)
            _log_enforcement(file_path, "blocked", detail)
            try:
                sys.stderr.write(
                    "RUBRIC SELF-HEAL ({}/{}): the file you just edited has a blocking standards "
                    "violation. Fix it now and re-save:\n{}".format(attempts + 1, CAP, detail)
                )
            except Exception:
                pass
            return 2

        # Cap reached — degrade to advisory so the implementer is not thrashed past maxTurns.
        try:
            os.makedirs(WORKSPACE, exist_ok=True)
            with open(DEGRADED_PATH, "a", encoding="utf-8") as fh:
                fh.write("- {} — unresolved after {} heal attempts:\n  {}\n".format(file_path, CAP, detail[:400]))
        except OSError:
            pass
        _log_enforcement(file_path, "degraded", detail)
        return 0  # allow; the CEO's RUBRIC.GATE still catches this at integration

    except Exception:
        return 0  # fail open — a hook bug must never block legitimate work


if __name__ == "__main__":
    sys.exit(main())
