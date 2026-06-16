"""Native Claude Code hook bridge — one cross-platform entry point (`rubric hook`).

Claude Code hooks call an external command, feed it a JSON event on stdin, and read its
exit code + stdout/stderr back. Rather than ship brittle shell+``jq`` scripts (which break
on Windows), rubric exposes a single Python dispatcher so the same binary that runs the gate
also speaks the hook protocol. ``.claude/settings.json`` just calls ``rubric hook``.

Events handled:
- **PostToolUse / PreToolUse** (matcher ``Edit|Write``): run the deterministic gate on the
  touched file. A blocking violation → exit **2** with the findings on stderr, which Claude
  Code feeds back to the model so it self-heals the code (the gate stays the blocking plane).
- **SessionStart**: inject the portable conventions once, as durable grounding (the standards
  are present from turn one — grounding before generation).
- **UserPromptSubmit**: inject the task-relevant conventions + exemplars for the typed prompt
  (retrieval grounding, no LLM cost — BM25 only).

Design rule: a hook must NEVER crash the user's session. Any unexpected error degrades to a
silent no-op (exit 0). Only a real blocking gate failure exits non-zero.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from pathlib import Path

from rubric.gate import default_adapters, run_gate
from rubric.kb import Kb
from rubric.orchestrate import build_context, language_of
from rubric.paths import KbLayout

# Events that inject context (stdout, exit 0) vs gate (stderr, exit 2 on block).
_CONTEXT_EVENTS = {"SessionStart", "UserPromptSubmit"}
_GATE_EVENTS = {"PreToolUse", "PostToolUse"}


@dataclass
class HookOutput:
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


def _additional_context(event: str, text: str) -> str:
    """The documented channel for feeding context to the model from a hook."""
    return json.dumps({"hookSpecificOutput": {
        "hookEventName": event, "additionalContext": text}})


def _conventions_block(kb: Kb) -> str:
    """A compact MUST/should list of the portable conventions — cheap, always-relevant."""
    lines = ["rubric standards in effect for this repo:"]
    for r in kb.rules.values():
        tag = "MUST" if r.enforcement.value == "blocking" else "should"
        lines.append(f"- ({tag}) {r.name}: {r.intent}")
    lines.append("Run `/rubric <task>` for canonical exemplars + reusable components before writing code.")
    return "\n".join(lines)


def _gate_file(file_path: str, kb: Kb, repo: str) -> HookOutput:
    """Run the deterministic gate on one file; exit 2 + findings on stderr if it blocks."""
    if not file_path or language_of(file_path) is None or not Path(file_path).is_file():
        return HookOutput()  # not a recognized code file — no-op
    lang = language_of(file_path)
    rules = kb.rules_for_language(lang) if lang else list(kb.rules.values())
    res = run_gate(file_path, default_adapters(repo), rules)
    if res.passed:
        return HookOutput()
    msg = [f"rubric: {len(res.blocking)} blocking standard violation(s) in {file_path} - fix before continuing:"]
    for f in res.blocking:
        loc = f":{f.line}" if f.line else ""
        msg.append(f"  [{f.source} {f.rule_id or ''}] {f.message} ({f.path or file_path}{loc})")
    return HookOutput(stderr="\n".join(msg), exit_code=2)


def handle(payload: dict, *, kb_dir: str = "kb", repo: str = ".") -> HookOutput:
    """Dispatch a hook event payload → HookOutput.

    Fail-safe by contract: ANY error (broken KB, missing optional dep, subprocess failure)
    degrades to a silent no-op so a hook can never crash the user's session.
    """
    event = payload.get("hook_event_name") or payload.get("hookEventName") or ""
    try:
        kb = Kb.load(KbLayout(kb_dir))

        if event in _GATE_EVENTS:
            tool_input = payload.get("tool_input")
            file_path = tool_input.get("file_path", "") if isinstance(tool_input, dict) else ""
            # Prefer the session cwd Claude Code sends, so .rubric/tools.json resolves in subdirs.
            return _gate_file(file_path, kb, payload.get("cwd") or repo)

        if event == "SessionStart":
            if not kb.rules:
                return HookOutput()
            return HookOutput(stdout=_additional_context(event, _conventions_block(kb)))

        if event == "UserPromptSubmit":
            prompt = (payload.get("prompt") or "").strip()
            if not prompt:
                return HookOutput()
            return HookOutput(stdout=_additional_context(event, build_context(prompt, kb, k=3)))

        return HookOutput()
    except Exception:  # noqa: BLE001 - a hook must never break the session
        return HookOutput()


def main(argv: list[str] | None = None, *, stdin=None) -> int:
    """CLI shim: read the hook JSON from stdin, run ``handle``, emit the protocol."""
    import argparse

    ap = argparse.ArgumentParser(prog="rubric hook", add_help=False)
    ap.add_argument("--kb", default="kb")
    ap.add_argument("--repo", default=".")
    args, _ = ap.parse_known_args(argv)

    raw = (stdin or sys.stdin).read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        return 0  # malformed event — never break the session

    out = handle(payload, kb_dir=args.kb, repo=args.repo)
    if out.stdout:
        print(out.stdout)
    if out.stderr:
        print(out.stderr, file=sys.stderr)
    return out.exit_code
