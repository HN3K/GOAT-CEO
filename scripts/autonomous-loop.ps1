<#
.SYNOPSIS
  Tier-2 outer perseverance loop for the GOAT-CEO autonomous harness.

.DESCRIPTION
  In-session auto-compaction already makes low context lossless (anti-drift §9): the CEO
  never stops just because the window fills. This outer loop covers the ONE thing
  compaction cannot — the *process* dying (crash, reboot, terminal closed, fatal error).
  It relaunches the CEO session, and the SessionStart hook (inject_handoff_context.py)
  re-grounds it from agent-workspace/RESUME-STATE.md, so the work resumes where it left
  off with zero loss. The durable state lives in files + git, not in any one process —
  this is the Ralph principle: disposable context, durable artifacts.

  Each iteration runs `claude -p` (headless) in the repo. The CEO works until it yields,
  compacting transparently in-session. When the process exits, this loop checks the
  stop conditions and, if none are met, relaunches with --continue (same session) — or,
  if --continue cannot resume, a fresh session re-grounded purely from RESUME-STATE.md.

  STOPS WHEN (checked each iteration, before relaunch):
    - agent-workspace/SESSION-COMPLETE exists    -> mission done            (exit 0)
    - agent-workspace/STOP exists                -> operator hard halt      (exit 0)
    - agent-workspace/ESCALATE_REQUIRED exists   -> needs the operator      (exit 3)
    - -MaxIterations reached                      -> safety cap             (exit 4)

  PERMISSION POSTURE for unattended runs — pick ONE via -PermArgs:
    - Sandbox/VM only:  -PermArgs '--dangerously-skip-permissions'
    - On the host:      -PermArgs '--permission-mode dontAsk'  (denies anything not in
                        .claude/settings.json permissions.allow; never prompts)
  HARD safety constraints MUST live in settings.json `deny` rules — chat instructions are
  lost on compaction; deny rules are not (anti-drift §9d).

  BILLING: from 2026-06-15, `claude -p` / Agent SDK usage on subscription plans draws from
  a separate monthly Agent SDK credit pool. An unattended loop is exactly that usage class.

.PARAMETER Mission
  First-iteration prompt (the mission). Omit with -Resume to just continue the last session.

.PARAMETER Resume
  Skip the initial prompt; continue the most recent session from its anchor.

.PARAMETER MaxIterations
  Safety cap on relaunch count (default 100). Prevents a crash-loop from running forever.

.PARAMETER PermArgs
  Permission flags passed verbatim to claude (see PERMISSION POSTURE above).

.PARAMETER ClaudeExe
  Path/name of the claude CLI (default 'claude').

.EXAMPLE
  pwsh -File scripts/autonomous-loop.ps1 -Mission "drive the X migration to cert" -PermArgs '--permission-mode dontAsk'

.EXAMPLE
  pwsh -File scripts/autonomous-loop.ps1 -Resume -PermArgs '--dangerously-skip-permissions'
#>
[CmdletBinding()]
param(
    [string]$Mission = "",
    [switch]$Resume,
    [int]$MaxIterations = 100,
    [string]$PermArgs = "--permission-mode dontAsk",
    [string]$ClaudeExe = "claude"
)

$ErrorActionPreference = "Stop"
$RepoRoot  = Split-Path -Parent $PSScriptRoot          # scripts/ -> repo root
$Workspace = Join-Path $RepoRoot "agent-workspace"

$Complete = Join-Path $Workspace "SESSION-COMPLETE"
$Stop     = Join-Path $Workspace "STOP"
$Escalate = Join-Path $Workspace "ESCALATE_REQUIRED"

function Write-Log([string]$msg) {
    Write-Host ("[autonomous-loop {0}] {1}" -f (Get-Date -Format "yyyy-MM-ddTHH:mm:ss"), $msg)
}

# Returns $true if the loop should stop; emits the reason + sets $script:ExitCode.
function Test-StopCondition {
    if (Test-Path $Complete) { Write-Log "SESSION-COMPLETE present -> mission done."; $script:ExitCode = 0; return $true }
    if (Test-Path $Stop)     { Write-Log "STOP present -> operator halt.";            $script:ExitCode = 0; return $true }
    if (Test-Path $Escalate) { Write-Log "ESCALATE_REQUIRED present -> operator needed."; $script:ExitCode = 3; return $true }
    return $false
}

$script:ExitCode = 0
Write-Log "Repo: $RepoRoot"
Write-Log "Permission posture: $PermArgs"
if (-not (Test-Path $Workspace)) { New-Item -ItemType Directory -Path $Workspace | Out-Null }

# A stale STOP from a prior run would abort immediately — surface it rather than silently exit.
if (Test-Path $Stop) {
    Write-Log "A STOP file already exists ($Stop). Remove it to start an autonomous run. Exiting."
    exit 0
}

for ($i = 1; $i -le $MaxIterations; $i++) {
    if (Test-StopCondition) { exit $script:ExitCode }

    # Build the claude invocation. Iteration 1 with a Mission seeds the prompt; thereafter
    # (or with -Resume) we --continue the same session so the anchor + transcript carry over.
    $claudeArgs = @("-p")
    $claudeArgs += ($PermArgs -split '\s+' | Where-Object { $_ -ne "" })

    if ($i -eq 1 -and -not $Resume -and $Mission -ne "") {
        $claudeArgs += @("/goat-ceo $Mission")
        Write-Log "Iteration $i/$MaxIterations — launching fresh session with mission."
    } else {
        $claudeArgs += "--continue"
        Write-Log "Iteration $i/$MaxIterations — continuing session (--continue; anchor re-grounds the CEO)."
    }

    try {
        & $ClaudeExe @claudeArgs
        $code = $LASTEXITCODE
        Write-Log "claude exited with code $code."
    } catch {
        Write-Log "claude launch threw: $($_.Exception.Message). Will retry after a short backoff."
        $code = 1
    }

    # Re-check stop conditions now that the CEO had a turn; it may have completed/escalated.
    if (Test-StopCondition) { exit $script:ExitCode }

    # Backoff before relaunch so a hard crash-loop doesn't spin the CPU or burn credits.
    Start-Sleep -Seconds 5
}

Write-Log "MaxIterations ($MaxIterations) reached without a stop condition. Exiting (safety cap)."
exit 4
