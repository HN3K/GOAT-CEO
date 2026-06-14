"""PreToolUse hook: git discipline guard.

Belt-and-suspenders enforcement for git staging/commit/push discipline.

Policy (fail-open — any exception exits 0 = allow):
  BLOCK (exit 2):
    - git add -A  (already in permissions.deny; hook is belt-and-suspenders)
    - git add .   (already in permissions.deny; hook is belt-and-suspenders)
    - git add --all
  WARN-NOT-BLOCK (exit 0 + stderr message):
    - raw 'git commit' not routed through .claude/hooks/ceo-commit.sh
    - raw 'git push' (any form)
  ALLOW (exit 0, silent):
    - .claude/hooks/ceo-commit.sh  (pathspec-only wrapper, safe)
    - git commit via ceo-commit.sh
    - all other commands

Design contract: FAIL-OPEN — any exception exits 0.
exit 0 = allow; exit 2 = BLOCK.
"""
import json
import re
import sys


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        cmd = data.get("tool_input", {}).get("command", "")

        # Explicit allow: ceo-commit.sh path (before any block checks)
        if "ceo-commit.sh" in cmd:
            return 0

        # BLOCK: git add -A / git add . / git add --all
        if re.search(r"\bgit\s+add\s+(-A\b|--all\b|\.(?:\s|$))", cmd):
            print(
                json.dumps(
                    {
                        "decision": "block",
                        "reason": (
                            "Blocked: 'git add -A / git add . / git add --all' "
                            "violates single-committer doctrine. "
                            "Stage explicit pathspecs only, via .claude/hooks/ceo-commit.sh."
                        ),
                    }
                )
            )
            return 2

        # WARN-NOT-BLOCK: raw git commit (not via ceo-commit.sh)
        if re.search(r"\bgit\s+commit\b", cmd):
            sys.stderr.write(
                "GIT-DISCIPLINE WARN: raw 'git commit' detected. "
                "The single-committer doctrine requires routing commits through "
                ".claude/hooks/ceo-commit.sh (pathspec-only wrapper). "
                "Allowing this time but prefer the approved path.\n"
            )
            return 0

        # WARN-NOT-BLOCK: raw git push (any form)
        if re.search(r"\bgit\s+push\b", cmd):
            sys.stderr.write(
                "GIT-DISCIPLINE WARN: raw 'git push' detected. "
                "Pushes must be authorized per-push by the operator. "
                "Allowing but this action requires explicit operator confirmation.\n"
            )
            return 0

        return 0

    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
