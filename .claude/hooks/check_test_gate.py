"""TaskCompleted hook: broad test-suite gate (C3).

Fires when a task is marked complete.  Blocks completion (exit 2) if the broad
test suite fails or times out.

Configuration (preferred → fallback):
  1. agent-workspace/TEST-CONFIG.json — structured, target-repo aware:
        {
          "workingDirectory": "<dir>",   # where to run; resolved relative to the
                                          #   target repo (payload cwd) if relative.
          "commands": [
            {"name": "...", "command": "...", "timeoutSeconds": 300, "required": true}
          ]
        }
     Each REQUIRED command runs with cwd = the resolved workingDirectory.
  2. agent-workspace/TEST-COMMAND.txt — one shell line; runs with cwd = the
     payload `cwd` (the target repo/worktree), NEVER this file's REPO_ROOT.

Gate semantics:
  - Nonzero exit          → BLOCK (exit 2).
  - Timeout               → BLOCK (exit 2) — do NOT allow on timeout.
  - Hollow pass (0 tests) → BLOCK (exit 2).
  - No config at all      → loud DEGRADED warning to stderr, then ALLOW (fail-open
                            by design — the gate is inactive until configured).

This enforces Doctrine #2: "every 'tests pass' claim is a hypothesis until
independently verified."  Mock-only suites passed on 7+ real-run failures before
this gate existed.

Design contract: FAIL-OPEN on any internal error.
exit 0 = allow task to close; exit 2 = BLOCK (stderr shown to agent).
"""
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
TEST_CMD_PATH = os.path.join(WORKSPACE, "TEST-COMMAND.txt")
TEST_CONFIG_PATH = os.path.join(WORKSPACE, "TEST-CONFIG.json")

# Strict-mode + fail-open-logging helpers (C20). Guarded so a missing _strict.py
# can never break this hook (fail-open is preserved).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from _strict import strict_mode, log_failopen
except Exception:  # pragma: no cover - defensive
    def strict_mode() -> bool:
        return False

    def log_failopen(*_a, **_k) -> None:
        pass

# Only gate implementer and verifier task completions.
GATED_ROLES = {"team-implementer", "team-verifier"}

# pytest/unittest zero-collected markers (do not collide with "10 passed").
HOLLOW = ("no tests ran", "collected 0 items", "ran 0 tests", "no tests found")


def _hollow(stdout: str, stderr: str) -> bool:
    combined = ((stdout or "") + "\n" + (stderr or "")).lower()
    return any(marker in combined for marker in HOLLOW)


def _run_one(command: str, cwd: str, timeout: int) -> int:
    """Run one command. Return 0 = pass, 2 = block (nonzero/timeout/hollow)."""
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        sys.stderr.write(
            "TEST GATE BLOCK: test command TIMED OUT after {}s — treating as FAILURE "
            "(a hung suite is not a passing suite). Task cannot be marked complete.\n"
            "Command: {}\nWorking dir: {}".format(timeout, command, cwd)
        )
        return 2

    if result.returncode != 0:
        out_tail = (result.stdout or "")[-1500:].strip()
        err_tail = (result.stderr or "")[-500:].strip()
        sys.stderr.write(
            "TEST GATE BLOCK: test command FAILED (exit {}).\n"
            "Task cannot be marked complete until all tests pass.\n"
            "Command: {}\nWorking dir: {}\n"
            "--- last stdout ---\n{}\n"
            "--- last stderr ---\n{}".format(
                result.returncode, command, cwd, out_tail, err_tail
            )
        )
        return 2

    # Hollow-pass guard (reward-hacking defense): a suite that runs ZERO tests
    # exits 0 and trivially "passes". The SEMANTIC reward-hack audit is Reviewer
    # B's job (templates.md §12); this catches only the zero-collected case.
    if _hollow(result.stdout, result.stderr):
        combined = ((result.stdout or "") + "\n" + (result.stderr or "")).lower()
        sys.stderr.write(
            "TEST GATE BLOCK: the suite reported success but ran ZERO tests (hollow pass). "
            "A passing gate must actually execute tests — check the test command/selection.\n"
            "Command: {}\nWorking dir: {}\n--- output tail ---\n{}".format(
                command, cwd, combined[-1500:].strip()
            )
        )
        return 2

    return 0


def _run_from_config(payload_cwd: str) -> int | None:
    """Run the structured TEST-CONFIG.json suite. Return 0/2, or None if no config."""
    if not os.path.exists(TEST_CONFIG_PATH):
        return None
    try:
        with open(TEST_CONFIG_PATH, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(cfg, dict):
        return None

    commands = cfg.get("commands")
    if not isinstance(commands, list) or not commands:
        return None

    # Resolve the working directory: relative paths are anchored to the target
    # repo (payload cwd), NOT this hook's REPO_ROOT.
    work_dir = cfg.get("workingDirectory") or ""
    base = payload_cwd or os.getcwd()
    if work_dir:
        run_cwd = work_dir if os.path.isabs(work_dir) else os.path.join(base, work_dir)
    else:
        run_cwd = base

    ran_required = False
    for entry in commands:
        if not isinstance(entry, dict):
            continue
        if not entry.get("required", True):
            continue
        command = entry.get("command")
        if not command or not isinstance(command, str):
            continue
        ran_required = True
        try:
            timeout = int(entry.get("timeoutSeconds", 300))
        except (TypeError, ValueError):
            timeout = 300
        rc = _run_one(command, run_cwd, timeout)
        if rc == 2:
            return 2

    if not ran_required:
        # Config present but no usable required command — treat as no config.
        return None
    return 0


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if agent_type not in GATED_ROLES:
            return 0  # not a gated role — allow

        payload_cwd = data.get("cwd", "") or ""

        # 1) Structured TEST-CONFIG.json (target-repo aware).
        rc = _run_from_config(payload_cwd)
        if rc is not None:
            return rc

        # 2) Fall back to TEST-COMMAND.txt, run from the payload cwd.
        if os.path.exists(TEST_CMD_PATH):
            with open(TEST_CMD_PATH, "r", encoding="utf-8") as fh:
                test_cmd = fh.read().strip()
            if test_cmd:
                run_cwd = payload_cwd or os.getcwd()
                return _run_one(test_cmd, run_cwd, 300)

        # 3) No config at all. Normally a loud DEGRADED warning then ALLOW (fail-open by
        #    design). In STRICT mode this documented degraded-allow path becomes a BLOCK:
        #    an unattended/high-risk run should not silently skip the test gate. Either
        #    way the degradation is logged to HOOK-FAILURES.jsonl so it's visible.
        log_failopen(
            "check_test_gate",
            "no TEST-CONFIG.json / TEST-COMMAND.txt — broad test gate inactive",
            {"agent_type": agent_type},
        )
        if strict_mode():
            sys.stderr.write(
                "TEST-GATE-BLOCK (strict): no agent-workspace/TEST-CONFIG.json or "
                "TEST-COMMAND.txt, and STRICT mode is on. Configure tests (or clear "
                "agent-workspace/STRICT_MODE) before completing this task."
            )
            return 2
        sys.stderr.write(
            "TEST-GATE-DEGRADED (check_test_gate): neither agent-workspace/TEST-CONFIG.json "
            "nor a non-empty agent-workspace/TEST-COMMAND.txt is present. The broad "
            "test-suite gate is INACTIVE for this session. The CEO must configure tests "
            "to activate it (or enable STRICT mode to make this a hard stop)."
        )
        return 0
    except Exception:
        return 0  # fail open — a hook bug must never block legitimate work


if __name__ == "__main__":
    sys.exit(main())
