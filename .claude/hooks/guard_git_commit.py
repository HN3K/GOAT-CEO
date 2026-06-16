"""PreToolUse hook: git discipline guard.

Belt-and-suspenders enforcement for git staging/commit/push discipline.

Policy (fail-open — any exception exits 0 = allow):
  BLOCK (exit 2) — any `git [global-opts] add <sweep-selector>`, where global-opts may
  include the dangerous `-C <path>` / `-c k=v` / `--git-dir=...` forms (the `-C <path>`
  form can stage in ANOTHER repo), and the sweep selector is one of:
    -A, --all, -u, --update, ., ./, :/, :, *, or a bare `--` followed by `.`
  Scoped pathspec adds (e.g. `git add path/to/file.py`, `git add .claude/settings.json`)
  are explicitly ALLOWED.
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

# Global options that may legitimately sit between `git` and the subcommand `add`.
# We consume them so the sweep-selector check still fires on e.g. `git -C /repo add -A`.
#   -C <path>        run as if git was started in <path>  (DANGEROUS: another repo)
#   -c <k=v>         override a config var for one command
#   --git-dir=...    / --work-tree=... / --namespace=...  (=value forms)
#   -p / --paginate / --no-pager / --bare / --literal-pathspecs ... (bare flags)
# Pattern: an option token, optionally followed by its argument (a non-flag token).
_GIT_GLOBAL_OPT = (
    r"(?:"
    r"-C\s+\S+"                 # -C <path>
    r"|-c\s+\S+"               # -c <k=v>
    r"|--(?:git-dir|work-tree|namespace|super-prefix)(?:=\S+|\s+\S+)"
    r"|--exec-path(?:=\S+)?"
    r"|-p|--paginate|--no-pager|--bare|--no-replace-objects"
    r"|--literal-pathspecs|--no-optional-locks|--icase-pathspecs"
    r")"
)
# A "sweep" pathspec/flag for `add` that stages broadly (the thing we forbid):
#   -A / --all / -u / --update / . / ./ / :/ / : / *  / `-- .`
# End-of-token: whitespace, end-of-string, OR a shell metacharacter that chains/terminates
# the command (`git add .;rm -rf /`, `git add .&&x`, `git add .|cat`, `git add .)`). Without
# the metachars these chained one-liners silently bypassed the sweep block. (F3)
_EOT = r"(?:\s|$|[;&|)<>])"
_ADD_SWEEP = (
    r"(?:"
    r"-A\b|--all\b|-u\b|--update\b"            # whole-tree update flags
    r"|\*" + _EOT +                             # glob-all
    r"|\.\/?" + _EOT +                          # . or ./
    r"|:\/?" + _EOT +                           # :/ (repo root magic) or bare :
    r"|--\s+\.\/?" + _EOT +                     # bare -- then . or ./
    r")"
)
# `git` + zero-or-more global options + `add` + (any tokens) + a sweep selector.
# The sweep selector may be the first add-argument or appear after other flags
# (e.g. `git add -v -A`), so allow non-sweep tokens before it.
_GIT_ADD_SWEEP = re.compile(
    r"\bgit\s+(?:" + _GIT_GLOBAL_OPT + r"\s+)*add\s+(?:\S+\s+)*?" + _ADD_SWEEP
)


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        cmd = data.get("tool_input", {}).get("command", "")

        # Explicit allow: ceo-commit.sh path (before any block checks)
        if "ceo-commit.sh" in cmd:
            return 0

        # BLOCK: any sweep-style `git add` (incl. `git -C <path> add -A`, `git add :/`,
        # `git add -u`, `git add *`, `git add .` / `./`, `git add -- .`).
        if _GIT_ADD_SWEEP.search(cmd):
            print(
                json.dumps(
                    {
                        "decision": "block",
                        "reason": (
                            "Blocked: a sweep-style 'git add' (e.g. -A, --all, -u, ., ./, "
                            ":/, *, '-- .', or a '-C <path> add -A' targeting another repo) "
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
