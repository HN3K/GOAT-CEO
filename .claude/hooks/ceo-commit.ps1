<#
.SYNOPSIS
    ceo-commit.ps1 — pathspec-only commit wrapper for the GOAT-CEO single-committer rule.

.DESCRIPTION
    Windows/PowerShell sibling of ceo-commit.sh. Ports it faithfully: same args and
    semantics. Takes a commit message and one or more explicit pathspecs, stages ONLY the
    listed paths (git add -- <pathspec>...), then commits with the message.

    This wrapper is a CONVENIENCE / CONVENTION, not a settings-level-enforced path. There
    is NO permissions.allow/git-commit-deny pair in settings.json (deny beats allow in
    Claude Code, which would have locked the CEO out of its own commits). Commit discipline
    is instead enforced by the fail-open guard_git_commit.py hook (warns on raw
    `git commit`/`git push`) plus the single-committer convention. All this script does is
    keep staging pathspec-scoped — it never runs git add -A/.

.NOTES
    Usage:  ceo-commit.ps1 <commit-message> <pathspec> [pathspec...]

    Enforces:
      - At least one explicit pathspec is required (no -A / no bare "." allowed)
      - Refuses any pathspec that is literally "." or "-A" or "--all" or starts with "--"
      - Stages ONLY the listed paths (git add -- <pathspec>...)
      - Commits with the provided message

    Exit codes:  0 = success; 1 = validation error (message to stderr).

    Intentionally simple and dependency-free. It must not call Python or any external tool
    other than git.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $false, ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'

if ($null -eq $Args -or $Args.Count -lt 2) {
    [Console]::Error.WriteLine("ceo-commit.ps1: ERROR - usage: ceo-commit.ps1 <message> <pathspec> [pathspec...]")
    exit 1
}

$Message = $Args[0]
$PathSpecs = $Args[1..($Args.Count - 1)]

# Reject forbidden pathspecs
foreach ($ps in $PathSpecs) {
    if ($ps -eq "." -or $ps -eq "-A" -or $ps -eq "--all") {
        [Console]::Error.WriteLine("ceo-commit.ps1: BLOCKED - pathspec '$ps' is forbidden. Use explicit file paths.")
        [Console]::Error.WriteLine("The single-committer rule (Rule 1 / INDEX-RACE incident) requires pathspec-scoped")
        [Console]::Error.WriteLine("commits. Never use -A / . - list the actual files being committed.")
        exit 1
    }
    if ($ps -like "--*" -and $ps -ne "--") {
        [Console]::Error.WriteLine("ceo-commit.ps1: BLOCKED - flag-like argument '$ps' rejected. Only file paths allowed.")
        exit 1
    }
}

# Stage only the explicit pathspecs
& git add -- @PathSpecs
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

# Commit
& git commit -m $Message
exit $LASTEXITCODE
