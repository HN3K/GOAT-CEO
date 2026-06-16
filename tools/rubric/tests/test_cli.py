"""Phase 5 gate: CLI end-to-end (real seed KB + real Ruff)."""

from pathlib import Path

from rubric.cli import main

REPO = Path(__file__).resolve().parent.parent
SEED = str(REPO / "kb")


def test_kb_command(capsys):
    assert main(["kb", "--kb", SEED]) == 0
    out = capsys.readouterr().out
    assert "rubric-starter" in out and "named-exports" in out


def test_context_command(capsys):
    assert main(["context", "add error handling", "--kb", SEED, "--language", "ts"]) == 0
    out = capsys.readouterr().out
    assert "Standards context for: add error handling" in out
    assert "Conventions to follow" in out


def test_check_skips_non_code_files(tmp_path, capsys):
    doc = tmp_path / "notes.txt"
    doc.write_text("# concept doc\nfree prose, not code", encoding="utf-8")
    assert main(["check", str(doc), "--kb", SEED]) == 0   # docs/data are not gated
    assert "no code files" in capsys.readouterr().out


def test_check_clean_file_passes(tmp_path, capsys):
    f = tmp_path / "ok.py"
    f.write_text("a = 1\n", encoding="utf-8")
    assert main(["check", str(f), "--kb", SEED]) == 0
    assert "PASS" in capsys.readouterr().out


def test_check_bad_file_fails(tmp_path, capsys):
    f = tmp_path / "bad.py"
    f.write_text("import os\n", encoding="utf-8")        # F401
    assert main(["check", str(f), "--kb", SEED]) == 1     # blocking -> non-zero exit
    out = capsys.readouterr().out
    assert "FAIL" in out and "ruff" in out


def test_enforce_no_llm_blocks_on_violation(tmp_path, capsys):
    f = tmp_path / "bad.py"
    f.write_text("import sys\n", encoding="utf-8")        # F401
    assert main(["enforce", str(f), "--kb", SEED, "--no-llm"]) == 1
    assert "verdict: FAIL" in capsys.readouterr().out
