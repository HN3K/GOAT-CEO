"""PreCompact hook: SELF-HEALING durable-handoff refresh (autonomous-safe).

GOAL: make auto-compaction LOSSLESS and UNATTENDED. When the harness is about to
compact (auto or manual), this hook guarantees a current, machine-derived resume
anchor exists on disk BEFORE context is pruned — then ALLOWS the compaction. It
never blocks.

WHY IT NEVER BLOCKS (critical):
A PreCompact hook that exits 2 to "block" an AUTOMATIC compaction is a documented
deadlock footgun (anthropics/claude-code#941): at high context the session can't
grow AND can't compact, and with no human present the run hangs forever. For true
autonomous operation that is fatal. So this hook does the opposite of gate-and-block:
it gate-and-HEALS — it writes/refreshes the facts the resume path needs, then returns
0 so compaction proceeds. The CEO never has to stop for "low context"; the survival
loop is PreCompact(write anchor) -> compaction(summarize) -> SessionStart(re-inject
anchor) -> CEO continues.

WHAT IT WRITES:
A delimited, hook-OWNED "MACHINE-REFRESH" block at the top of agent-workspace/
RESUME-STATE.md, containing only machine-derivable facts (so it can never be a stale
narrative): an ISO timestamp, per-repo git branch/HEAD/dirty for the GOAT-CEO repo +
every repo in repo-registry.json, the *.GATE sentinels present now, the EXPECTED-GATES
list, the MISSION.md headline, and pointers to dated diagnosis docs. The CEO-authored
body below the block (PHASE / TASKS / NEXT_ACTION narrative — anti-drift §8) is
preserved verbatim; the hook only rewrites its own delimited region. If no
RESUME-STATE.md exists yet, the hook creates one from machine state alone, so even a
CEO that never wrote an anchor still resumes from facts.

Design contract: FAIL-OPEN and NEVER-BLOCK. Every path returns 0 (allow compaction);
any internal error is swallowed and still returns 0.
"""
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
RESUME_STATE_FILE = os.path.join(WORKSPACE, "RESUME-STATE.md")
EXPECTED_GATES_FILE = os.path.join(WORKSPACE, "EXPECTED-GATES.txt")
MISSION_FILE = os.path.join(WORKSPACE, "MISSION.md")
REGISTRY_FILE = os.path.join(REPO_ROOT, "repo-registry.json")

BEGIN_MARK = "<!-- BEGIN MACHINE-REFRESH (owned by check_precompact.py — regenerated at every compaction; do not hand-edit) -->"
END_MARK = "<!-- END MACHINE-REFRESH -->"
_STRIP_RE = re.compile(
    re.escape("<!-- BEGIN MACHINE-REFRESH") + r".*?" + re.escape("END MACHINE-REFRESH -->") + r"\n?",
    re.DOTALL,
)

MAX_DIAGNOSIS_DOCS = 10
MAX_REPOS = 12          # keep the machine block bounded / size-compliant
BODY_SOFT_CAP = 2000    # CEO-body chars above which the block flags BODY_OVERSIZE


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(repo_path: str, *args) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", repo_path, *args],
            capture_output=True, text=True, timeout=5,
        )
        return out.stdout.strip()
    except Exception:
        return ""


def _repo_lines() -> list:
    """One machine-derived line per repo: branch / short HEAD / dirty flag."""
    seen = set()
    repos = [("goat-ceo", REPO_ROOT)]
    try:
        if os.path.exists(REGISTRY_FILE):
            with open(REGISTRY_FILE, "r", encoding="utf-8") as fh:
                reg = json.load(fh)
            for prefix, meta in (reg.get("repos") or {}).items():
                p = meta.get("path")
                if p:
                    repos.append((prefix, p))
    except Exception:
        pass  # registry unreadable — GOAT-CEO repo line alone is still useful

    lines = []
    for prefix, path in repos:
        norm = os.path.normcase(os.path.abspath(path)) if path else ""
        if not norm or norm in seen:
            continue
        seen.add(norm)
        if not os.path.isdir(path):
            lines.append("  - {}  path={}  (MISSING)".format(prefix, path))
            continue
        head = _git(path, "rev-parse", "--short", "HEAD") or "?"
        branch = _git(path, "rev-parse", "--abbrev-ref", "HEAD") or "?"
        dirty = "yes" if _git(path, "status", "--porcelain") else "no"
        lines.append("  - {}  branch={}  head={}  dirty={}".format(prefix, branch, head, dirty))
    if len(lines) > MAX_REPOS:
        extra = len(lines) - MAX_REPOS
        lines = lines[:MAX_REPOS]
        lines.append("  - (+{} more repos — see repo-registry.json)".format(extra))
    return lines


def _gates_present() -> list:
    try:
        return sorted(os.path.basename(p) for p in glob.glob(os.path.join(WORKSPACE, "*.GATE")))
    except Exception:
        return []


def _gates_expected() -> list:
    try:
        with open(EXPECTED_GATES_FILE, "r", encoding="utf-8") as fh:
            return [l.strip() for l in fh if l.strip() and not l.strip().startswith("#")]
    except Exception:
        return []


def _mission_headline() -> str:
    try:
        with open(MISSION_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                s = line.strip()
                if s and not s.startswith("#"):
                    return s[:240]
    except Exception:
        pass
    return "(no agent-workspace/MISSION.md — set the mission)"


def _diagnosis_docs() -> list:
    try:
        hits = glob.glob(os.path.join(WORKSPACE, "*FAILURE*.md"))
        hits += glob.glob(os.path.join(WORKSPACE, "*-20[0-9][0-9]-*.md"))
        names = sorted({os.path.basename(h) for h in hits})
        return ["agent-workspace/" + n for n in names[:MAX_DIAGNOSIS_DOCS]]
    except Exception:
        return []


def _build_machine_block(body_health: str = "") -> str:
    repo_lines = _repo_lines() or ["  - goat-ceo  (git state unavailable)"]
    diag = _diagnosis_docs()
    diag_block = "\n".join("  - " + d for d in diag) if diag else "  (none found)"
    health_line = ("HANDOFF_HEALTH: " + body_health + "\n") if body_health else ""
    return (
        BEGIN_MARK + "\n"
        + "COMPACT_REFRESHED_AT: " + _now_iso() + "\n"
        + "MISSION: " + _mission_headline() + "\n"
        + "GATES_PRESENT: [" + ", ".join(_gates_present()) + "]\n"
        + "GATES_EXPECTED: [" + ", ".join(_gates_expected()) + "]\n"
        + "GIT_STATE (machine-derived; AUTHORITATIVE on resume — verify against this, Doctrine #2):\n"
        + "\n".join(repo_lines) + "\n"
        + "DIAGNOSIS_DOCS (dated machine-written evidence; outrank prose):\n"
        + diag_block + "\n"
        + health_line
        + END_MARK + "\n"
    )


_STUB_BODY = (
    "# RESUME-STATE — durable resume anchor\n"
    "<!-- The block ABOVE is machine-refreshed at every compaction and is authoritative.\n"
    "     The CEO fills the fields BELOW at each checkpoint (anti-drift §8): PHASE, TASKS,\n"
    "     and a single concrete NEXT_ACTION. On resume: verify the machine block against\n"
    "     git + agent-workspace/*.GATE before trusting (Doctrine #2), then continue. -->\n"
    "PHASE:        (infer from GATES_PRESENT above; CEO to set)\n"
    "TASKS:        (CEO to snapshot from TaskList)\n"
    "NEXT_ACTION:  reconstruct from PHASE + GATES_PRESENT; read agent-workspace/STATUS.md tail\n"
    "              and the DIAGNOSIS_DOCS above, then resume the pipeline. Do NOT stop for the\n"
    "              operator — auto-compaction is transparent; persevere (anti-drift §9).\n"
)


def main() -> int:
    try:
        body = ""
        try:
            if os.path.exists(RESUME_STATE_FILE):
                with open(RESUME_STATE_FILE, "r", encoding="utf-8", errors="replace") as fh:
                    body = fh.read()
                body = _STRIP_RE.sub("", body).lstrip("\n")
        except OSError:
            body = ""

        if not body.strip():
            body = _STUB_BODY

        # Size-compliance signal: flag an oversized CEO body so it stays readable/lean.
        body_len = len(body)
        if body_len > BODY_SOFT_CAP:
            body_health = (
                "BODY_OVERSIZE — {} chars > {} budget. Trim RESUME-STATE.md body to the "
                "essentials (PHASE + a few TASKS + one NEXT_ACTION); it is a snapshot, not a "
                "log. Oversized anchors get truncated on injection and stop being read.".format(
                    body_len, BODY_SOFT_CAP
                )
            )
        else:
            body_health = "ok ({} chars)".format(body_len)

        machine_block = _build_machine_block(body_health)

        os.makedirs(WORKSPACE, exist_ok=True)
        with open(RESUME_STATE_FILE, "w", encoding="utf-8") as fh:
            fh.write(machine_block + "\n" + body)

        sys.stderr.write(
            "PRECOMPACT OK: refreshed agent-workspace/RESUME-STATE.md machine block "
            "(allowing compaction; resume is lossless via SessionStart re-injection)."
        )
        return 0  # ALWAYS allow — never block an autonomous run
    except Exception:
        return 0  # fail open — a hook bug must never block compaction


if __name__ == "__main__":
    sys.exit(main())
