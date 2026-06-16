"""SubagentStop hook: per-agent-type artifact presence gate.

Fires when a subagent is about to stop.  Blocks (exit 2) if the agent has
not produced its mandatory artifact.  The maxTurns cap is the escape valve —
when the agent hits maxTurns, the hook is bypassed and the agent is force-
stopped by the harness regardless.

Per-role artifact requirements:
    team-architect      → agent-workspace/PLAN.md must exist and be non-empty
    team-researcher     → agent-workspace/RESEARCH-LOG.md must exist and be non-empty
    team-implementer    → provable work: worktree HEAD moved past the recorded
                          startHead, OR an IMPLEMENTER-RESULT*.json with a real
                          endHead+changedFiles, OR uncommitted working-tree changes
    team-verifier       → a PASS/FAIL verdict in the verifier transcript OR REVIEW-LOG.md
    team-overseer       → agent-workspace/STATUS.md must exist (heartbeat written)
    team-ceo-assistant  → no file artifact required (reports inline to CEO)
    team-cross-reviewer → agent-workspace/CROSS-REVIEW-REPORT.md must exist

Roles not in this table are allowed to stop freely.

Design contract: FAIL-OPEN on any internal error.
exit 0 = allow stop; exit 2 = BLOCK (agent must complete its artifact).
"""
import glob as _glob
import json
import os
import re
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.join(REPO_ROOT, "agent-workspace")
START_TIMES_FILE = os.path.join(WORKSPACE, "AGENT-START-TIMES.json")

# Artifact map: role -> list of (path, description) pairs; ALL must exist.
# Paths that start with "git:" are checked via git rather than filesystem.
ARTIFACT_MAP = {
    "team-architect": [
        (os.path.join(WORKSPACE, "PLAN.md"), "PLAN.md in agent-workspace/"),
    ],
    "team-researcher": [
        (os.path.join(WORKSPACE, "RESEARCH-LOG.md"), "RESEARCH-LOG.md in agent-workspace/"),
    ],
    # team-verifier checked separately (C2): verdict may live in the verifier's
    # transcript OR REVIEW-LOG.md — the verifier has Write/Edit removed, so it
    # need not write the file itself.
    "team-overseer": [
        (os.path.join(WORKSPACE, "STATUS.md"), "STATUS.md heartbeat in agent-workspace/"),
    ],
    "team-cross-reviewer": [
        (os.path.join(WORKSPACE, "CROSS-REVIEW-REPORT.md"), "CROSS-REVIEW-REPORT.md in agent-workspace/"),
    ],
    # team-implementer checked separately (git commit check)
}

VERDICT_PATTERN = re.compile(r'"verdict"\s*:\s*"(PASS|FAIL)"', re.IGNORECASE)


def _decoded_transcript_text(path: str) -> str:
    """Return assistant text from a JSONL transcript, JSON-decoded.

    A transcript stores the verdict block JSON-encoded inside a content string, so
    its quotes are backslash-escaped on disk (\\"verdict\\":...). Rather than match
    escaped bytes (fragile across single/double escaping), we decode each JSONL line
    and concatenate the assistant text — yielding clean, unescaped JSON the plain
    VERDICT_PATTERN matches. Mirrors check_span_validity.py's _assistant_text.
    Falls back to the raw file text if a line isn't decodable.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
    except OSError:
        return ""
    parts = [raw]  # include raw so an unescaped verdict (rare) still matches
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        msg = ev.get("message") if isinstance(ev.get("message"), dict) else ev
        content = msg.get("content") if isinstance(msg, dict) else None
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", "") or "")
    return "\n".join(parts)


def _git(cwd: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", cwd, *args],
        capture_output=True,
        text=True,
        timeout=10,
    )


def _recorded_start_head(agent_type: str, session_id: str) -> str | None:
    """Return the startHead recorded by record_agent_start.py, or None if unknown."""
    if not os.path.exists(START_TIMES_FILE):
        return None
    try:
        with open(START_TIMES_FILE, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
    for key in (session_id + "_startHead", agent_type + "_startHead"):
        sha = data.get(key)
        if isinstance(sha, str) and sha.strip():
            return sha.strip()
    return None


def _norm_path(p: str) -> str:
    """Normalize a path for equality comparison (case + separators + abs)."""
    try:
        return os.path.normcase(os.path.abspath(p))
    except Exception:
        return os.path.normcase((p or "").replace("\\", "/"))


def _implementer_result_evidence(
    start_head: str | None, cur_head: str | None, cwd: str
) -> bool:
    """True if a CURRENT-RUN IMPLEMENTER-RESULT*.json proves work.

    Schema (written by the implementer / CEO):
        {sessionId, batchId, cwd, branch, startHead, endHead, changedFiles[], testsRun[],
         deviationsFromPlan[]}
    Evidence = non-empty file whose endHead differs from the baseline AND whose
    changedFiles is non-empty AND which is bound to THIS run.

    CURRENT-RUN BINDING (anti-stale, including earlier batches of the SAME session):
    a leftover result file must NOT clear a later no-op implementer. A file counts only if:
      - its `endHead` matches the CURRENT worktree HEAD (the change it claims is in this
        tree right now), OR
      - its `startHead` matches the baseline recorded for THIS run by record_agent_start.py.
        That baseline advances on every SubagentStart, so a prior batch's result carries a
        stale startHead and will NOT match.
    `sessionId` is deliberately NOT used as a binder: the SubagentStop payload session can be
    shared across an entire CEO session, so it cannot distinguish batches. As a final
    cross-worktree guard, if the file names a `cwd` and we have a payload cwd, they must match
    — rejecting a same-session result whose startHead collides but came from another worktree.
    """
    for path in sorted(_glob.glob(os.path.join(WORKSPACE, "IMPLEMENTER-RESULT*.json"))):
        try:
            if os.path.getsize(path) == 0:
                continue
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                obj = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(obj, dict):
            continue
        end_head = str(obj.get("endHead", "") or "").strip()
        changed = obj.get("changedFiles") or []
        if not end_head or not isinstance(changed, list) or not changed:
            continue
        rec_start = str(obj.get("startHead", "") or "").strip()
        # endHead must differ from the baseline (prefer the recorded startHead,
        # else the one declared in the result file).
        baseline = start_head or rec_start
        if baseline and end_head == baseline:
            continue
        # Current-run binding — reject stale files (incl. earlier same-session batches).
        bound = (cur_head and end_head == cur_head) or (
            start_head and rec_start and rec_start == start_head
        )
        if not bound:
            continue
        # Cross-worktree guard: a named cwd must match the payload cwd when both are present.
        rec_cwd = str(obj.get("cwd", "") or "").strip()
        if rec_cwd and cwd and _norm_path(rec_cwd) != _norm_path(cwd):
            continue
        return True
    return False


def _has_implementer_artifact(cwd: str, agent_type: str, session_id: str) -> tuple[bool, str]:
    """Prove the implementer actually produced work (C1).

    PASS (allow) if ANY of:
      (a) current worktree HEAD != recorded startHead;
      (b) `git status --porcelain` shows uncommitted changes;
      (c) a CURRENT-RUN IMPLEMENTER-RESULT*.json with endHead != startHead and
          non-empty changedFiles (bound to this session/HEAD — see
          _implementer_result_evidence).
    BLOCK only if startHead is KNOWN and HEAD == startHead and no working-tree changes
    and no current-run result evidence (provably no work). If startHead is UNKNOWN, WARN
    and ALLOW (fail-open — never block on a missing baseline).

    The fresh, worktree-local signals (a) and (b) are checked BEFORE the result-file
    evidence (c): a stale artifact can never fake a moved HEAD or a dirty tree, so the
    unspoofable signals win first and (c) only ever has to clear a genuinely no-op tree
    with a current-run result file. Reads HEAD from the PAYLOAD cwd (the implementer's
    worktree), never REPO_ROOT.
    """
    start_head = _recorded_start_head(agent_type, session_id)

    if not cwd:
        # No worktree to inspect — a current-run-bound result file (startHead match) may
        # still prove work; otherwise fail open.
        if _implementer_result_evidence(start_head, None, ""):
            return True, ""
        sys.stderr.write(
            "WARNING (check_artifacts): no payload cwd for team-implementer; "
            "cannot verify worktree HEAD. Allowing (fail-open).\n"
        )
        return True, ""

    # Read the current worktree HEAD up front (used by both the HEAD-moved check and
    # the result-file current-run binding).
    cur_head = None
    try:
        r = _git(cwd, "rev-parse", "HEAD")
        if r.returncode == 0:
            cur_head = (r.stdout or "").strip()
    except Exception:
        cur_head = None

    # (a) HEAD moved past the recorded baseline — strongest, freshest, unspoofable signal.
    if start_head is not None and cur_head and cur_head != start_head:
        return True, ""

    # (b) uncommitted working-tree changes — also fresh and worktree-local.
    try:
        s = _git(cwd, "status", "--porcelain")
        if s.returncode == 0 and (s.stdout or "").strip():
            return True, ""
    except Exception:
        pass  # if status fails we fall through to the remaining checks

    # (c) structured result evidence — only if bound to THIS run (anti-stale).
    if _implementer_result_evidence(start_head, cur_head, cwd):
        return True, ""

    if start_head is None:
        sys.stderr.write(
            "WARNING (check_artifacts): no recorded startHead for team-implementer "
            "(SubagentStart baseline missing). Allowing (fail-open) — cannot prove "
            "absence of work without a baseline.\n"
        )
        return True, ""

    if cur_head is None:
        # Could not read the worktree HEAD at all (git unavailable / transient failure).
        # "I cannot evaluate" must ALLOW, not block — failing closed here would brick an
        # implementer that may well have done real work, violating the fail-open contract. (F2)
        sys.stderr.write(
            "WARNING (check_artifacts): could not read worktree HEAD for team-implementer "
            "(git unavailable/failed). Allowing (fail-open) — cannot prove absence of work.\n"
        )
        return True, ""

    return (
        False,
        "team-implementer produced NO provable work: worktree HEAD is unchanged "
        "from its start baseline ({}), the working tree is clean, and no CURRENT-RUN "
        "IMPLEMENTER-RESULT*.json (one whose endHead matches the current HEAD or whose "
        "startHead matches this run's baseline, with a matching cwd) exists. Make your "
        "code changes (commit on your worktree branch or write "
        "IMPLEMENTER-RESULT.<batchId>.json with startHead + endHead + cwd + changedFiles), "
        "then report to the CEO and END YOUR TURN.".format((start_head or "")[:12]),
    )


def _has_verifier_verdict(transcript_path: str, review_log: str) -> tuple[bool, str]:
    """Verifier verdict path (C2).

    ALLOW if a PASS/FAIL verdict appears in EITHER the verifier's own transcript
    (payload agent_transcript_path) OR agent-workspace/REVIEW-LOG.md. The verifier
    has Write/Edit removed, so it reports its verdict as a structured message; the
    CEO aggregates it into REVIEW-LOG.md. Either source satisfies the gate.
    """
    # Transcript: decode assistant text so the verdict's escaped quotes resolve.
    if transcript_path and os.path.exists(transcript_path):
        if VERDICT_PATTERN.search(_decoded_transcript_text(transcript_path)):
            return True, ""
    # REVIEW-LOG.md: plain markdown, verdict block is unescaped.
    if review_log and os.path.exists(review_log):
        try:
            with open(review_log, "r", encoding="utf-8", errors="replace") as fh:
                if VERDICT_PATTERN.search(fh.read()):
                    return True, ""
        except OSError:
            pass
    return (
        False,
        "team-verifier produced no PASS/FAIL verdict in its transcript or in "
        "agent-workspace/REVIEW-LOG.md. Emit a structured JSON verdict block "
        '("verdict": "PASS"|"FAIL") as your final message before stopping.',
    )


def main() -> int:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}

        agent_type = data.get("agent_type", "") or data.get("subagent_type", "")
        if not agent_type:
            return 0  # unknown role — fail open

        cwd = data.get("cwd", "") or ""
        session_id = data.get("session_id", "") or agent_type

        if agent_type == "team-implementer":
            ok, msg = _has_implementer_artifact(cwd, agent_type, session_id)
            if not ok:
                sys.stderr.write("ARTIFACT GATE BLOCK: " + msg)
                return 2
            return 0

        if agent_type == "team-verifier":
            transcript_path = (
                data.get("agent_transcript_path", "")
                or data.get("transcript_path", "")
            )
            review_log = os.path.join(WORKSPACE, "REVIEW-LOG.md")
            ok, msg = _has_verifier_verdict(transcript_path, review_log)
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

        return 0
    except Exception:
        return 0  # fail open


if __name__ == "__main__":
    sys.exit(main())
