"""SubagentStart hook: record agent start time + worktree HEAD for the gates.

Writes (or updates) agent-workspace/AGENT-START-TIMES.json with the current
Unix timestamp keyed by agent_type.  Used by check_turn_budget.py.

ALSO records the start HEAD of the agent's working tree (resolved from the
payload `cwd`, NOT this file's REPO_ROOT — the implementer works in its own
worktree). Stored as "<key>_startHead" alongside the timestamp. check_artifacts.py
uses this baseline to prove the implementer actually produced work (C1) instead of
the old `git log --oneline -1` check that passes in any non-empty repo.

This hook is non-blocking — it always exits 0 regardless of outcome.
Errors are swallowed (fail open).

Design contract: FAIL-OPEN on any internal error.  Always exit 0.
"""
import json
import os
import subprocess
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
START_TIMES_FILE = os.path.join(WORKSPACE, "AGENT-START-TIMES.json")


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if not agent_type:
            return 0

        os.makedirs(WORKSPACE, exist_ok=True)

        existing: dict = {}
        if os.path.exists(START_TIMES_FILE):
            try:
                with open(START_TIMES_FILE, "r", encoding="utf-8") as fh:
                    existing = json.load(fh)
            except (json.JSONDecodeError, OSError):
                existing = {}

        session_id = data.get("session_id", agent_type)
        existing[session_id] = time.time()
        existing[agent_type] = time.time()  # also key by role for simple lookup

        # Capture the start HEAD of the AGENT'S worktree (from payload cwd, not
        # this file's REPO_ROOT). The implementer's commits land on its worktree
        # branch, so the gate must baseline against that tree. Fail-open: if git
        # fails or cwd is missing, just skip the SHA (gate then warns + allows).
        cwd = data.get("cwd", "") or ""
        if cwd:
            try:
                head = subprocess.run(
                    ["git", "-C", cwd, "rev-parse", "HEAD"],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                sha = (head.stdout or "").strip()
                if head.returncode == 0 and sha:
                    existing[session_id + "_startHead"] = sha
                    existing[agent_type + "_startHead"] = sha
            except Exception:
                pass  # fail open — never block a monitoring write on a git failure

        with open(START_TIMES_FILE, "w", encoding="utf-8") as fh:
            json.dump(existing, fh, indent=2)

        return 0
    except Exception:
        return 0  # fail open — never block on a monitoring write


if __name__ == "__main__":
    sys.exit(main())
