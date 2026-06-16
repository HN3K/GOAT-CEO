"""Phase 2 gate: deterministic adapters, aggregation, missing-tool grace, real Ruff."""

import json
import subprocess

import pytest

from rubric.contracts import Enforcement, Finding, Rule, RuleKind
from rubric.gate import (
    AstGrepAdapter,
    CommandAdapter,
    CommandSpec,
    RubricBuiltinAdapter,
    RuffAdapter,
    load_command_adapters,
    run_gate,
)


class FakeAdapter:
    def __init__(self, name, findings, available=True):
        self.name = name
        self._findings = findings
        self._available = available

    def available(self):
        return self._available

    def run(self, target, rules):
        return list(self._findings)


def block(msg="x"):
    return Finding(source="fake", enforcement=Enforcement.BLOCKING, message=msg)


def advise(msg="y"):
    return Finding(source="fake", enforcement=Enforcement.ADVISORY, message=msg)


# --------------------------------------------------------------------------- #
# Aggregation + grace
# --------------------------------------------------------------------------- #
def test_run_gate_aggregates_and_blocks():
    res = run_gate("f.py", [FakeAdapter("a", [block(), advise()])])
    assert res.tools_run == ["a"] and res.tools_missing == []
    assert len(res.findings) == 2
    assert res.passed is False and len(res.blocking) == 1


def test_run_gate_advisory_only_passes():
    res = run_gate("f.py", [FakeAdapter("a", [advise()])])
    assert res.passed is True


def test_missing_tool_recorded_not_fatal():
    res = run_gate("f.py", [FakeAdapter("present", [block()]),
                            FakeAdapter("absent", [block()], available=False)])
    assert res.tools_run == ["present"] and res.tools_missing == ["absent"]
    assert len(res.findings) == 1   # absent adapter contributed nothing, no crash


# --------------------------------------------------------------------------- #
# ast-grep adapter (subprocess mocked) — rule-driven, carries rule enforcement
# --------------------------------------------------------------------------- #
def test_ast_grep_adapter_maps_matches(monkeypatch):
    rule = Rule(id="no-default-export", name="n", intent="no default exports",
                kind=RuleKind.DETERMINISTIC, enforcement=Enforcement.BLOCKING,
                tool="ast-grep", spec="export default $X", languages=["ts"])

    def fake_run(args, **kw):
        class P:
            stdout = json.dumps([{"file": "a.ts", "text": "export default Foo",
                                  "range": {"start": {"line": 3}}}])
        return P()

    monkeypatch.setattr(subprocess, "run", fake_run)
    ad = AstGrepAdapter(ast_grep_bin="sg")
    findings = ad.run("a.ts", [rule])
    assert len(findings) == 1
    f = findings[0]
    assert f.rule_id == "no-default-export" and f.enforcement is Enforcement.BLOCKING
    assert f.line == 4 and f.quote == "export default Foo"   # ast-grep 0-indexed -> +1


def test_ast_grep_adapter_live(tmp_path):
    """Real ast-grep (pip ast-grep-cli) flags a default export."""
    ad = AstGrepAdapter()
    if not ad.available():
        pytest.skip("ast-grep not installed")
    f = tmp_path / "t.ts"
    f.write_text("const a = 1;\nexport default a;\n", encoding="utf-8")
    rule = Rule(id="no-default-export", name="n", intent="no default exports",
                kind=RuleKind.DETERMINISTIC, enforcement=Enforcement.BLOCKING,
                tool="ast-grep", spec="export default $X", languages=["ts"])
    findings = ad.run(str(f), [rule])
    assert len(findings) == 1
    assert findings[0].rule_id == "no-default-export" and findings[0].line == 2  # 1-indexed


# --------------------------------------------------------------------------- #
# Generic config-driven adapter
# --------------------------------------------------------------------------- #
def test_command_adapter_json(monkeypatch):
    spec = CommandSpec(name="toolx", command=["toolx", "{target}"],
                       fields={"message": "msg", "path": "file", "line": "row", "code": "id"})

    def fake_run(cmd, **kw):
        assert cmd == ["toolx", "a.py"]   # {target} substituted

        class P:
            stdout = json.dumps([{"msg": "bad thing", "file": "a.py", "row": 7, "id": "X1"}])
        return P()

    monkeypatch.setattr(subprocess, "run", fake_run)
    findings = CommandAdapter(spec).run("a.py")
    assert len(findings) == 1
    f = findings[0]
    assert f.source == "toolx" and f.message == "bad thing" and f.line == 7 and f.rule_id == "X1"
    assert f.enforcement is Enforcement.BLOCKING


def test_command_adapter_regex(monkeypatch):
    spec = CommandSpec(name="eslint", command=["eslint", "{target}"], fmt="regex",
                       regex=r"^(?P<path>[^:]+):(?P<line>\d+):\d+:\s+(?P<message>.+?)\s+(?P<code>\S+)$")

    def fake_run(cmd, **kw):
        class P:
            stdout = "a.ts:12:5: Unexpected console statement no-console\n"
        return P()

    monkeypatch.setattr(subprocess, "run", fake_run)
    findings = CommandAdapter(spec).run("a.ts")
    assert len(findings) == 1 and findings[0].line == 12 and findings[0].rule_id == "no-console"


def test_load_command_adapters(tmp_path):
    cfg = tmp_path / "tools.json"
    cfg.write_text(json.dumps({"tools": [
        {"name": "eslint", "command": ["eslint", "--format", "unix", "{target}"],
         "fmt": "regex", "regex": "x", "enforcement": "blocking"}]}), encoding="utf-8")
    adapters = load_command_adapters(cfg)
    assert len(adapters) == 1 and adapters[0].name == "eslint"
    assert adapters[0].spec.enforcement is Enforcement.BLOCKING
    assert load_command_adapters(tmp_path / "missing.json") == []


# --------------------------------------------------------------------------- #
# rubric-native colocated-test check
# --------------------------------------------------------------------------- #
def test_colocated_test_builtin(tmp_path):
    rule = Rule(id="require-colocated-test", name="n", intent="need a sibling test",
                kind=RuleKind.DETERMINISTIC, enforcement=Enforcement.BLOCKING,
                tool="rubric", spec="colocated-test", languages=["ts"])
    src = tmp_path / "user-service.ts"
    src.write_text("export const x = 1;", encoding="utf-8")
    ad = RubricBuiltinAdapter()

    findings = ad.run(str(src), [rule])
    assert len(findings) == 1 and findings[0].rule_id == "require-colocated-test"

    (tmp_path / "user-service.test.ts").write_text("// test", encoding="utf-8")
    assert ad.run(str(src), [rule]) == []   # sibling now present


# --------------------------------------------------------------------------- #
# Ruff adapter — REAL (ruff installed)
# --------------------------------------------------------------------------- #
def test_ruff_adapter_skips_non_python(tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("free text, definitely not python !!!", encoding="utf-8")
    assert RuffAdapter().run(str(doc)) == []   # never lint non-.py files


def test_ruff_adapter_flags_real_violation(tmp_path):
    bad = tmp_path / "bad.py"
    bad.write_text("import os\n", encoding="utf-8")   # F401 unused import
    ad = RuffAdapter()
    assert ad.available() is True
    res = run_gate(str(bad), [ad])
    assert res.tools_run == ["ruff"]
    assert any(f.source == "ruff" for f in res.findings)
    assert res.passed is False                         # ruff findings are blocking
