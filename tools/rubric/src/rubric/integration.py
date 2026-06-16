"""Deployment integration — make rubric enforce *during* the build.

- ``git_changed_files`` → enforce only what changed (pre-commit / CI).
- ``scaffold_repo`` (``rubric init``) → drop a ``.rubric/`` config (a tools.json
  template for the stack's linters) and a git pre-commit hook that runs
  ``rubric check --changed``. The deterministic gate is the blocking hook; this is
  how rubric plugs into the loop.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rubric.paths import RepoLayout

TOOLS_TEMPLATE = {
    "_comment": "Wrap your stack's linters here — added by config, not code. "
                "fmt=json (flat list, dotted field paths) or fmt=regex (named groups).",
    "tools": [
        {
            "name": "eslint",
            "command": ["eslint", "--format", "unix", "{target}"],
            "fmt": "regex",
            "regex": r"^(?P<path>[^:]+):(?P<line>\d+):\d+:\s+(?P<message>.+?)\s+(?P<code>\S+)$",
            "enforcement": "blocking",
        }
    ],
}

PRE_COMMIT_HOOK = """#!/bin/sh
# rubric: block the commit on deterministic standard violations in staged files.
exec rubric check --changed --kb "{kb}"
"""

CI_SNIPPET = (
    "# CI step (e.g. GitHub Actions):\n"
    "#   - run: pip install rubric && rubric check --changed --kb {kb}\n"
)

# --------------------------------------------------------------------------- #
# Native Claude Code integration (hooks + skill + subagent)
# --------------------------------------------------------------------------- #
RUBRIC_SKILL = """\
---
name: rubric
description: >-
  Ground the next piece of code in this repo's standards. Use BEFORE writing or
  editing code: it surfaces the canonical exemplars, reusable existing components,
  and conventions for the task so the work matches the team's style instead of
  reinventing patterns.
argument-hint: "<what you are about to build>"
allowed-tools: Bash(rubric *)
---

# rubric — standards grounding for: $ARGUMENTS

Canonical exemplars, reusable components, and conventions for this task:

!`rubric context "$ARGUMENTS" --kb {kb}`

Follow the conventions above, REUSE the listed components instead of reinventing
them, and match the exemplar style. After writing, the deterministic gate runs
automatically on save (PostToolUse hook); run `rubric enforce <file> --verify` for
an adversarially-verified advisory review.
"""

RUBRIC_SUBAGENT = """\
---
name: rubric-reviewer
description: >-
  Read-only code-quality auditor. Delegate after implementing a change to validate
  it against this repo's rubric standards. Runs the deterministic blocking gate plus
  an adversarially-verified LLM advisory review and reports findings; never edits.
tools: Read, Grep, Glob, Bash(rubric *)
model: inherit
---

You audit code against the project's rubric standards. You never modify files.

When invoked:
1. Identify the changed/target files (use git or the user's pointer).
2. For each code file run: `rubric enforce <file> --verify --kb .rubric/kb`
   - The deterministic gate is BLOCKING (real violations that must be fixed).
   - The advisory review is ADVISORY and already adversarially verified — report it
     as suggestions, with each finding's confidence.
3. Report grouped as **Blocking** (must fix) and **Advisory** (consider), each with
   file:line and the exact rule. Be concise. Do not edit code; hand fixes back.
"""


def _merge_claude_hooks(settings: dict, hook_cmd: str) -> bool:
    """Idempotently add rubric's PostToolUse + SessionStart hooks. Returns True if changed."""
    hooks = settings.setdefault("hooks", {})
    changed = False
    wanted = {
        "PostToolUse": {"matcher": "Edit|Write",
                        "hooks": [{"type": "command", "command": hook_cmd}]},
        "SessionStart": {"hooks": [{"type": "command", "command": hook_cmd}]},
    }
    for event, entry in wanted.items():
        existing = hooks.setdefault(event, [])
        already = any(
            h.get("command") == hook_cmd
            for grp in existing if isinstance(grp, dict)
            for h in grp.get("hooks", []) if isinstance(h, dict)
        )
        if not already:
            existing.append(entry)
            changed = True
    return changed


def scaffold_claude(repo_root: str = ".", *, kb: str = ".rubric/kb") -> list[str]:
    """Wire rubric into Claude Code natively: PostToolUse + SessionStart hooks, a `/rubric`
    skill, and a `rubric-reviewer` subagent. Merges (never clobbers) existing settings.
    Returns created/updated paths."""
    root = Path(repo_root)
    claude = root / ".claude"
    touched: list[str] = []
    hook_cmd = f"rubric hook --kb {kb}"

    settings_path = claude / "settings.json"
    settings: dict = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            settings = {}
    if _merge_claude_hooks(settings, hook_cmd):
        settings_path.parent.mkdir(parents=True, exist_ok=True)
        settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")
        touched.append(str(settings_path))

    skill = claude / "skills" / "rubric" / "SKILL.md"
    if not skill.exists():
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text(RUBRIC_SKILL.format(kb=kb), encoding="utf-8")
        touched.append(str(skill))

    agent = claude / "agents" / "rubric-reviewer.md"
    if not agent.exists():
        agent.parent.mkdir(parents=True, exist_ok=True)
        agent.write_text(RUBRIC_SUBAGENT, encoding="utf-8")
        touched.append(str(agent))

    return touched


def git_changed_files(repo_root: str = ".", *, staged: bool = True) -> list[str]:
    """Files changed in the working tree. ``staged`` → only staged (pre-commit)."""
    args = ["git", "-C", str(repo_root), "diff"] + (["--cached"] if staged else []) + ["--name-only"]
    proc = subprocess.run(args, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        return []
    root = Path(repo_root)
    return [str(root / line.strip()) for line in proc.stdout.splitlines() if line.strip()]


def scaffold_repo(repo_root: str = ".", *, kb: str = ".rubric/kb") -> list[str]:
    """Create .rubric/ config + a git pre-commit hook. Returns created paths."""
    layout = RepoLayout(repo_root).ensure()
    created: list[str] = []

    tools = layout.rubric_dir / "tools.json"
    if not tools.exists():
        tools.write_text(json.dumps(TOOLS_TEMPLATE, indent=2), encoding="utf-8")
        created.append(str(tools))

    readme = layout.rubric_dir / "README.md"
    if not readme.exists():
        readme.write_text(
            "# .rubric\n\n`tools.json` wires your stack's linters. Put your conventions KB under "
            "`kb/`. Run `rubric check --changed` to gate.\n", encoding="utf-8")
        created.append(str(readme))

    hooks_dir = Path(repo_root) / ".git" / "hooks"
    if hooks_dir.is_dir():
        hook = hooks_dir / "pre-commit"
        hook.write_text(PRE_COMMIT_HOOK.format(kb=kb), encoding="utf-8", newline="\n")
        try:
            hook.chmod(0o755)
        except OSError:
            pass
        created.append(str(hook))

    return created
