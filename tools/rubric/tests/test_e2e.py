"""End-to-end lifecycle: init → index → context (reuse) → gate (hook) → measure.

Proves the pieces integrate as one system on a realistic fresh repo, using the project's own
seed KB. No LLM (deterministic path) so it runs in CI without a subscription.
"""

import json
from pathlib import Path

from rubric.cli import main
from rubric.hook import handle

REPO = Path(__file__).resolve().parent.parent
SEED = str(REPO / "kb")


def _py(p: Path, text: str):
    p.write_text(text, encoding="utf-8")


def test_full_lifecycle(tmp_path, capsys):
    # a small "project": one reusable component file, one clean file, one violating file
    _py(tmp_path / "db.py", '"""data layer."""\n\n\ndef save_user(name: str) -> int:\n'
                            '    """Persist a user and return its id."""\n    return 1\n')
    _py(tmp_path / "clean.py", "from db import save_user\n\nuid = save_user('x')\n")
    _py(tmp_path / "bad.py", "import os\n")          # F401 -> blocking

    # 1. init: scaffolds .rubric + .claude + builds the codebase index
    assert main(["init", "--repo", str(tmp_path), "--kb", SEED]) == 0
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".rubric" / "index" / "components.json").exists()
    capsys.readouterr()

    # 2. index round-trips and captured the reusable component (not the private/test surface)
    idx = json.loads((tmp_path / ".rubric" / "index" / "components.json").read_text(encoding="utf-8"))
    names = {c["name"] for c in idx["components"]}
    assert "save_user" in names

    # 3. context surfaces that component for a relevant task (reuse, P4)
    assert main(["context", "store a new user record", "--language", "py",
                 "--repo", str(tmp_path), "--kb", SEED]) == 0
    ctx = capsys.readouterr().out
    assert "save_user" in ctx and "REUSE" in ctx

    # 4. the native hook gates a violating edit (exit 2) and passes a clean one (exit 0)
    bad = handle({"hook_event_name": "PostToolUse", "cwd": str(tmp_path),
                  "tool_input": {"file_path": str(tmp_path / "bad.py")}}, kb_dir=SEED)
    assert bad.exit_code == 2 and "bad.py" in bad.stderr
    clean = handle({"hook_event_name": "PostToolUse", "cwd": str(tmp_path),
                    "tool_input": {"file_path": str(tmp_path / "clean.py")}}, kb_dir=SEED)
    assert clean.exit_code == 0

    # 5. measure produces an adherence report over the project (2 of 3 files pass the gate)
    assert main(["measure", str(tmp_path / "db.py"), str(tmp_path / "clean.py"),
                 str(tmp_path / "bad.py"), "--repo", str(tmp_path), "--kb", SEED]) == 0
    out = capsys.readouterr().out
    assert "gate-pass rate" in out and "67%" in out      # 2/3 files clean
