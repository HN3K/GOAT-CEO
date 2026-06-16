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
# End-of-token: whitespace, end-of-string, a shell metacharacter that chains/terminates
# the command (`git add .;rm -rf /`, `git add .&&x`, `git add .|cat`, `git add .)`), OR a
# CLOSING QUOTE. Without the metachars these chained one-liners silently bypassed the sweep
# block (F3); without the quote-awareness, `git add "."` / `git add ':/'` / `git add "-A"`
# slipped through because the selector was wrapped in quotes the shell strips before git
# sees it (the quotes are cosmetic to git — `git add "."` stages everything just like
# `git add .`).
_EOT = r"(?:\s|$|[;&|)<>\"'])"
# Optional surrounding quote: the shell removes it, so a quoted selector sweeps identically.
_Q = r"[\"']?"
# The sweep selectors/flags themselves (no leading quote, no trailing EOT — wrappers add those).
_SWEEP_CORE = r"(?:-A|--all|-u|--update|\*|\.\/?|:\/?)"
_ADD_SWEEP = (
    r"(?:"
    + _Q + _SWEEP_CORE + _EOT +                # bare or quoted: -A  "."  './'  ":/"  "-A" ...
    r"|--\s+" + _Q + r"(?:\.\/?|:\/?|\*)" + _EOT +  # bare `--` (end-of-opts) then . / ./ / :/ / *
    r")"
)
# `git` + zero-or-more global options + `add` + (any tokens) + a sweep selector.
# The sweep selector may be the first add-argument or appear after other flags
# (e.g. `git add -v -A`), so allow non-sweep tokens before it.
_GIT_ADD_SWEEP = re.compile(
    r"\bgit\s+(?:" + _GIT_GLOBAL_OPT + r"\s+)*add\s+(?:\S+\s+)*?" + _ADD_SWEEP
)

# Shell chaining / command-substitution metacharacters. A command carrying any of these is
# NOT a clean single wrapper invocation, so the ceo-commit.sh allow must not apply to it
# (else `echo ceo-commit.sh && git add -A` would smuggle a sweep past the guard).
_HAS_CHAIN = re.compile(r"[;&|\n`]|\$\(")


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
        cmd = data.get("tool_input", {}).get("command", "")

        # BLOCK FIRST: any sweep-style `git add` (incl. `git -C <path> add -A`, `git add :/`,
        # `git add -u`, `git add *`, `git add .` / `./`, `git add -- .`, and their QUOTED
        # forms). This runs BEFORE the ceo-commit.sh allow so a chained command such as
        # `echo ceo-commit.sh && git add -A` cannot use the wrapper's name as a bypass token.
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

        # Explicit allow for the approved pathspec-only wrapper — ONLY when the command is a
        # CLEAN single invocation with no shell chaining/substitution. The bare substring is
        # not sufficient (that was the bypass): a chained command keeps going to the warn
        # checks instead of being waved through here.
        if "ceo-commit.sh" in cmd and not _HAS_CHAIN.search(cmd):
            return 0

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
