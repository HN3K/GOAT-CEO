"""Native Claude Code hook bridge — gate events, context injection, fail-safe degradation."""

import io
import json

from rubric.hook import handle, main

REPO = __import__("pathlib").Path(__file__).resolve().parent.parent
SEED = str(REPO / "kb")


def _payload(**kw):
    return kw


# --------------------------------------------------------------------------- #
# gate events (PostToolUse / PreToolUse)
# --------------------------------------------------------------------------- #
def test_posttooluse_blocks_on_violation(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import os\n", encoding="utf-8")          # F401
    out = handle(_payload(hook_event_name="PostToolUse",
                          tool_input={"file_path": str(bad)}), kb_dir=SEED)
    assert out.exit_code == 2
    assert "blocking standard violation" in out.stderr and "bad.py" in out.stderr


def test_posttooluse_passes_clean_file(tmp_path):
    ok = tmp_path / "ok.py"
    ok.write_text("a = 1\n", encoding="utf-8")
    out = handle(_payload(hook_event_name="PostToolUse",
                          tool_input={"file_path": str(ok)}), kb_dir=SEED)
    assert out.exit_code == 0 and out.stderr == ""


def test_gate_ignores_non_code_files(tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("import os not real code", encoding="utf-8")
    out = handle(_payload(hook_event_name="PostToolUse",
                          tool_input={"file_path": str(doc)}), kb_dir=SEED)
    assert out.exit_code == 0


def test_gate_missing_file_path_is_noop():
    out = handle(_payload(hook_event_name="PreToolUse", tool_input={}), kb_dir=SEED)
    assert out.exit_code == 0 and out.stdout == "" and out.stderr == ""


def test_gate_malformed_tool_input_is_noop():
    # tool_input arriving as a non-dict must degrade to a no-op, not crash
    out = handle(_payload(hook_event_name="PostToolUse", tool_input="oops"), kb_dir=SEED)
    assert out.exit_code == 0 and out.stderr == ""


def test_gate_uses_payload_cwd_for_repo(tmp_path, monkeypatch):
    # the gate should honor the cwd Claude Code sends (subdir/monorepo robustness)
    bad = tmp_path / "bad.py"
    bad.write_text("import os\n", encoding="utf-8")
    out = handle(_payload(hook_event_name="PostToolUse", cwd=str(tmp_path),
                          tool_input={"file_path": str(bad)}), kb_dir=SEED)
    assert out.exit_code == 2 and "bad.py" in out.stderr


# --------------------------------------------------------------------------- #
# context-injection events
# --------------------------------------------------------------------------- #
def test_sessionstart_injects_conventions():
    out = handle(_payload(hook_event_name="SessionStart"), kb_dir=SEED)
    assert out.exit_code == 0
    data = json.loads(out.stdout)
    assert data["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "rubric standards" in data["hookSpecificOutput"]["additionalContext"]


def test_userpromptsubmit_injects_task_context():
    out = handle(_payload(hook_event_name="UserPromptSubmit",
                          prompt="add error handling to the service"), kb_dir=SEED)
    data = json.loads(out.stdout)
    assert "Standards context" in data["hookSpecificOutput"]["additionalContext"]


def test_userpromptsubmit_empty_prompt_noop():
    out = handle(_payload(hook_event_name="UserPromptSubmit", prompt="  "), kb_dir=SEED)
    assert out.stdout == "" and out.exit_code == 0


# --------------------------------------------------------------------------- #
# fail-safe: a hook must never crash the session
# --------------------------------------------------------------------------- #
def test_broken_kb_degrades_to_noop():
    out = handle(_payload(hook_event_name="SessionStart"), kb_dir="/nonexistent/kb/path")
    assert out.exit_code == 0 and out.stdout == ""


def test_unknown_event_is_noop():
    assert handle(_payload(hook_event_name="Stop"), kb_dir=SEED).exit_code == 0


def test_main_reads_stdin_and_emits_protocol(tmp_path, capsys):
    bad = tmp_path / "bad.py"
    bad.write_text("import os\n", encoding="utf-8")
    stdin = io.StringIO(json.dumps({"hook_event_name": "PostToolUse",
                                    "tool_input": {"file_path": str(bad)}}))
    rc = main(["--kb", SEED], stdin=stdin)
    assert rc == 2
    assert "blocking standard violation" in capsys.readouterr().err


def test_main_malformed_json_is_noop(capsys):
    assert main(["--kb", SEED], stdin=io.StringIO("not json")) == 0
