"""Phase 6: deployment integration — git-changed files, scaffold, init, check --changed."""

import json
import subprocess
from pathlib import Path

from rubric.cli import main
from rubric.integration import git_changed_files, scaffold_claude, scaffold_repo

REPO = Path(__file__).resolve().parent.parent
SEED = str(REPO / "kb")


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)


def _init_repo(root):
    _git(root, "init")
    _git(root, "config", "user.email", "t@t")
    _git(root, "config", "user.name", "t")


def test_scaffold_creates_config(tmp_path):
    created = scaffold_repo(str(tmp_path))
    assert (tmp_path / ".rubric" / "tools.json").exists()
    assert (tmp_path / ".rubric" / "README.md").exists()
    assert any("tools.json" in c for c in created)


def test_scaffold_with_git_writes_hook(tmp_path):
    _init_repo(tmp_path)
    scaffold_repo(str(tmp_path))
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    assert hook.exists() and "rubric check --changed" in hook.read_text(encoding="utf-8")


def test_git_changed_files_staged(tmp_path):
    _init_repo(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "a.py")
    changed = git_changed_files(str(tmp_path), staged=True)
    assert any(c.endswith("a.py") for c in changed)


def test_init_command(tmp_path, capsys):
    assert main(["init", "--repo", str(tmp_path)]) == 0
    assert (tmp_path / ".rubric" / "tools.json").exists()
    assert "CI step" in capsys.readouterr().out


def test_check_changed_fails_on_staged_violation(tmp_path, capsys):
    _init_repo(tmp_path)
    (tmp_path / "bad.py").write_text("import os\n", encoding="utf-8")   # F401
    _git(tmp_path, "add", "bad.py")
    rc = main(["check", "--changed", "--repo", str(tmp_path), "--kb", SEED])
    assert rc == 1
    assert "FAIL" in capsys.readouterr().out


def test_check_multiple_files(tmp_path, capsys):
    good = tmp_path / "ok.py"
    good.write_text("a = 1\n", encoding="utf-8")
    bad = tmp_path / "bad.py"
    bad.write_text("import sys\n", encoding="utf-8")
    rc = main(["check", str(good), str(bad), "--kb", SEED])
    assert rc == 1                          # one file fails -> overall fail
    out = capsys.readouterr().out
    assert "PASS  " in out and "FAIL  " in out


# --------------------------------------------------------------------------- #
# native Claude Code integration
# --------------------------------------------------------------------------- #
def test_scaffold_claude_creates_hooks_skill_subagent(tmp_path):
    touched = scaffold_claude(str(tmp_path), kb=".rubric/kb")
    settings = tmp_path / ".claude" / "settings.json"
    assert settings.exists()
    cfg = json.loads(settings.read_text(encoding="utf-8"))
    assert "PostToolUse" in cfg["hooks"] and "SessionStart" in cfg["hooks"]
    assert cfg["hooks"]["PostToolUse"][0]["matcher"] == "Edit|Write"
    assert "rubric hook" in cfg["hooks"]["PostToolUse"][0]["hooks"][0]["command"]
    assert (tmp_path / ".claude" / "skills" / "rubric" / "SKILL.md").exists()
    assert (tmp_path / ".claude" / "agents" / "rubric-reviewer.md").exists()
    assert len(touched) == 3


def test_scaffold_claude_is_idempotent(tmp_path):
    scaffold_claude(str(tmp_path))
    second = scaffold_claude(str(tmp_path))
    assert second == []                     # nothing re-created
    cfg = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert len(cfg["hooks"]["PostToolUse"]) == 1   # not duplicated


def test_scaffold_claude_merges_existing_settings(tmp_path):
    claude = tmp_path / ".claude"
    claude.mkdir()
    (claude / "settings.json").write_text(
        json.dumps({"model": "opus", "hooks": {"Stop": [{"hooks": []}]}}), encoding="utf-8")
    scaffold_claude(str(tmp_path))
    cfg = json.loads((claude / "settings.json").read_text(encoding="utf-8"))
    assert cfg["model"] == "opus"           # preserved
    assert "Stop" in cfg["hooks"] and "PostToolUse" in cfg["hooks"]   # merged


def test_init_scaffolds_claude_by_default(tmp_path):
    assert main(["init", "--repo", str(tmp_path)]) == 0
    assert (tmp_path / ".claude" / "settings.json").exists()


def test_init_no_claude_flag_skips(tmp_path):
    assert main(["init", "--repo", str(tmp_path), "--no-claude"]) == 0
    assert not (tmp_path / ".claude").exists()
