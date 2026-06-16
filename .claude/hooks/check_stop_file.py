"""PreToolUse hook: operator STOP-file kill switch.

If `agent-workspace/STOP` exists, this blocks the agent's next Bash/PowerShell/Write/Edit
at the tool boundary (faster than a turn boundary), so a runaway or marathon agent can be
halted deterministically instead of waiting for a turn to end. The orchestrator clears it
with a bare `Remove-Item`/`rm`/`del ... STOP`, which this hook explicitly allows so the CEO
can resume.

Wire at PreToolUse with matcher "Bash|PowerShell|Write|Edit". The STOP path SET is derived
automatically: GOAT-CEO's own `agent-workspace/STOP` is always covered, and — if
`repo-registry.json` is present at the GOAT-CEO root — every registered repo's
`<repo-root>/agent-workspace/STOP` is added too. So when this hook FIRES it honors a STOP
dropped in ANY registered repo, not only GOAT-CEO's.

Coverage still depends on the hook actually RUNNING in the agent's session — the derived path
list does not by itself wire the hook into other repos. With the default `teammateMode:
in-process` (see .claude/settings.json), teammates run inside THIS session and inherit
GOAT-CEO's project-scope hooks, so the registry-derived set reaches them with no extra wiring.
A genuinely SEPARATE Claude Code session rooted in another repo does NOT inherit these project
hooks; cover it by wiring this hook at user scope (or in that repo's settings). There is no
installer that does this automatically — it is manual.

Contract: exit 0 = allow; exit 2 = BLOCK (stderr is shown to the agent).
Design rule: FAIL OPEN — any internal error allows the call. Keep this dependency-free.
"""
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REGISTRY_PATH = os.path.join(REPO_ROOT, "repo-registry.json")


def _registry_stop_paths():
    """Derive `<repo-root>/agent-workspace/STOP` for every registered repo.

    repo-registry.json shape: {"repos": {"<name>": {"path"|"root": "<dir>", ...}}}.
    Best-effort and exception-safe: a malformed/absent registry yields no extra paths
    (the caller still has the GOAT-CEO default), preserving fail-open behavior.
    """
    paths = []
    try:
        if not os.path.exists(REGISTRY_PATH):
            return paths
        with open(REGISTRY_PATH, "r", encoding="utf-8", errors="replace") as fh:
            reg = json.load(fh)
        repos = reg.get("repos")
        # Accept either {"repos": {...}} or a bare top-level mapping of repos.
        if not isinstance(repos, dict):
            repos = reg if isinstance(reg, dict) else {}
        for entry in repos.values():
            if not isinstance(entry, dict):
                continue
            root = entry.get("root") or entry.get("path")
            if not root or not isinstance(root, str):
                continue
            paths.append(os.path.join(root, "agent-workspace", "STOP"))
    except Exception:
        return []  # never let registry parsing break the kill switch
    return paths


# Always cover GOAT-CEO's own STOP; add registered repos' STOP files when known.
STOP_PATHS = [os.path.join(REPO_ROOT, "agent-workspace", "STOP")] + _registry_stop_paths()

# Allow a bare removal command (no chaining, nothing else on the line) targeting a STOP
# file so the orchestrator can clear the stop and resume.
CLEAR_STOP = re.compile(
    r"^\s*(Remove-Item|del|rm)\s+[^;&|()`$]*\bSTOP\b[^;&|()`$]*$", re.IGNORECASE
)


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        command = str((data.get("tool_input") or {}).get("command") or "")

        if command and CLEAR_STOP.match(command):
            return 0

        for stop in STOP_PATHS:
            if os.path.exists(stop):
                note = ""
                try:
                    with open(stop, "r", encoding="utf-8", errors="replace") as fh:
                        note = fh.read(500).strip()
                except OSError:
                    pass
                sys.stderr.write(
                    "OPERATOR STOP IS IN EFFECT (" + stop + "). This is NOT a recoverable "
                    "error — do not retry, do not work around it. Write a brief state note "
                    "of where you stopped, send your checkpoint message, and END YOUR TURN "
                    "now." + ("\nSTOP note: " + note if note else "")
                )
                return 2

        return 0
    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
