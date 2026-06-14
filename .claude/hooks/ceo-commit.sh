#!/usr/bin/env bash
# ceo-commit.sh — pathspec-only commit wrapper for the GOAT-CEO single-committer rule.
#
# Usage:  ceo-commit.sh <commit-message> <pathspec> [pathspec...]
#
# Enforces:
#   - At least one explicit pathspec is required (no -A / no bare "." allowed)
#   - Refuses any pathspec that is literally "." or "-A" or starts with "--"
#   - Stages ONLY the listed paths (git add <pathspec>...)
#   - Commits with the provided message
#
# This is the ONLY permitted commit path for the CEO.  It is listed in
# settings.json permissions.allow so it can bypass the Bash(git commit *)
# deny rule.  The deny + allow pattern keeps the path narrow: only this
# wrapper can commit; no subagent can run git commit directly.
#
# Exit codes:  0 = success; 1 = validation error (message to stderr).
#
# NOTE: this script is intentionally simple and dependency-free.
# It must not call Python or any external tool.

set -euo pipefail

if [[ $# -lt 2 ]]; then
    echo "ceo-commit.sh: ERROR — usage: ceo-commit.sh <message> <pathspec> [pathspec...]" >&2
    exit 1
fi

MESSAGE="$1"
shift  # remaining args are pathspecs

PATHSPECS=("$@")

# Reject forbidden pathspecs
for ps in "${PATHSPECS[@]}"; do
    if [[ "$ps" == "." || "$ps" == "-A" || "$ps" == "--all" ]]; then
        echo "ceo-commit.sh: BLOCKED — pathspec '${ps}' is forbidden. Use explicit file paths." >&2
        echo "The single-committer rule (Rule 1 / INDEX-RACE incident) requires pathspec-scoped" >&2
        echo "commits. Never use -A / . — list the actual files being committed." >&2
        exit 1
    fi
    if [[ "$ps" == --* && "$ps" != "--" ]]; then
        echo "ceo-commit.sh: BLOCKED — flag-like argument '${ps}' rejected. Only file paths allowed." >&2
        exit 1
    fi
done

# Stage only the explicit pathspecs
git add -- "${PATHSPECS[@]}"

# Commit
git commit -m "$MESSAGE"
