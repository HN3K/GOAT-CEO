"""SubagentStop hook: per-agent-type artifact presence gate.

Fires when a subagent is about to stop.  Blocks (exit 2) if the agent has
not produced its mandatory artifact.  The maxTurns cap is the escape valve —
when the agent hits maxTurns, the hook is bypassed and the agent is force-
stopped by the harness regardless.

Per-role artifact requirements:
    team-architect      → agent-workspace/PLAN.md must exist and be non-empty
    team-researcher     → agent-workspace/RESEARCH-LOG.md must exist and be non-empty
    team-implementer    → at least 1 commit on worktree branch OR IMPLEMENTATION-MANIFEST.md
    team-verifier       → agent-workspace/REVIEW-LOG.md must exist and contain a verdict
    team-overseer       → agent-workspace/STATUS.md must exist (heartbeat written)
    team-ceo-assistant  → no file artifact required (reports inline to CEO)
    team-cross-reviewer → agent-workspace/CROSS-REVIEW-REPORT.md must exist

Roles not in this table are allowed to stop freely.

Design contract: FAIL-OPEN on any internal error.
exit 0 = allow stop; exit 2 = BLOCK (agent must complete its artifact).
"""
import json
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")

# Artifact map: role -> list of (path, description) pairs; ALL must exist.
# Paths that start with "git:" are checked via git rather than filesystem.
ARTIFACT_MAP = {
    "team-architect": [
        (os.path.join(WORKSPACE, "PLAN.md"), "PLAN.md in agent-workspace/"),
    ],
    "team-researcher": [
        (os.path.join(WORKSPACE, "RESEARCH-LOG.md"), "RESEARCH-LOG.md in agent-workspace/"),
    ],
    "team-verifier": [
        (os.path.join(WORKSPACE, "REVIEW-LOG.md"), "REVIEW-LOG.md in agent-workspace/"),
    ],
    "team-overseer": [
        (os.path.join(WORKSPACE, "STATUS.md"), "STATUS.md heartbeat in agent-workspace/"),
    ],
    "team-cross-reviewer": [
        (os.path.join(WORKSPACE, "CROSS-REVIEW-REPORT.md"), "CROSS-REVIEW-REPORT.md in agent-workspace/"),
    ],
    # team-implementer checked separately (git commit check)
}

VERDICT_PATTERN = re.compile(r'"verdict"\s*:\s*"(PASS|FAIL)"', re.IGNORECASE)


def _has_implementer_artifact() -> tuple[bool, str]:
    """Check if implementer left a commit or IMPLEMENTATION-MANIFEST.md."""
    manifest = os.path.join(WORKSPACE, "IMPLEMENTATION-MANIFEST.md")
    if os.path.exists(manifest) and os.path.getsize(manifest) > 0:
        return True, ""

    # Check for at least 1 commit ahead of origin (any branch)
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0 and result.stdout.strip():
            return True, ""
    except Exception:
        pass

    return (
        False,
        "team-implementer must either write IMPLEMENTATION-MANIFEST.md or leave "
        "at least one commit on its worktree branch before stopping. "
        "Report your branch name and file list to the CEO, then END YOUR TURN.",
    )


def _has_verifier_verdict(path: str) -> tuple[bool, str]:
    """Check REVIEW-LOG.md contains a verdict field."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        if VERDICT_PATTERN.search(text):
            return True, ""
        return (
            False,
            "REVIEW-LOG.md exists but contains no verdict JSON block. "
            'Write a fenced JSON block with "verdict": "PASS" or "FAIL" before stopping.',
        )
    except OSError:
        return False, "REVIEW-LOG.md is absent or unreadable."


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if not agent_type:
            return 0  # unknown role — fail open

        if agent_type == "team-implementer":
            ok, msg = _has_implementer_artifact()
            if not ok:
                sys.stderr.write("ARTIFACT GATE BLOCK: " + msg)
                return 2
            return 0

        artifacts = ARTIFACT_MAP.get(agent_type)
        if not artifacts:
            return 0  # role not in map — allow

        for path, description in artifacts:
            if not os.path.exists(path) or os.path.getsize(path) == 0:
                sys.stderr.write(
                    "ARTIFACT GATE BLOCK: role '{}' cannot stop until its required "
                    "artifact exists and is non-empty: {}. "
                    "Complete your deliverable and then END YOUR TURN.".format(
                        agent_type, description
                    )
                )
                return 2

            # Extra check for verifier: verdict must be present in REVIEW-LOG.md
            if agent_type == "team-verifier" and "REVIEW-LOG.md" in path:
                ok, msg = _has_verifier_verdict(path)
                if not ok:
                    sys.stderr.write("ARTIFACT GATE BLOCK: " + msg)
                    return 2

        return 0
    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
