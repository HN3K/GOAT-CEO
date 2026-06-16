"""Phase 4 gate: grounded advisory review — never blocks, runs only LLM rules."""

import json
import subprocess


from rubric.contracts import (
    Enforcement,
    Exemplar,
    Finding,
    GateResult,
    Rule,
    RuleKind,
)
from rubric.kb import Kb
from rubric.llm import CHEAP, ClaudeCLIClient, ScriptedClient
from rubric.review import build_review_prompt, parse_advisory, review_code


def kb_with_llm_rule():
    kb = Kb(name="t")
    kb.add_rule(Rule(id="appropriate-error", name="errors", intent="i", kind=RuleKind.LLM,
                     enforcement=Enforcement.ADVISORY,
                     spec="Are errors handled appropriately and not swallowed?", languages=["py"]))
    kb.add_rule(Rule(id="no-default", name="d", intent="i", kind=RuleKind.DETERMINISTIC,
                     enforcement=Enforcement.BLOCKING, tool="ast-grep"))  # must be ignored by review
    return kb


def gate():
    return GateResult(target="f.py", findings=[
        Finding(source="ruff", rule_id="F401", enforcement=Enforcement.BLOCKING, message="unused import")])


# --------------------------------------------------------------------------- #
def test_build_prompt_grounds_in_facts_and_exemplars():
    p = build_review_prompt("code here", gate().findings,
                            [Exemplar(id="e", title="Err", intent="i", language="py", code="raise X()")],
                            "review errors", "f.py")
    assert "code here" in p and "unused import" in p and "raise X()" in p and "review errors" in p


def test_parse_advisory_valid_is_advisory():
    raw = json.dumps({"findings": [{"message": "swallows timeout error", "line": 4, "quote": "except: pass"}]})
    out = parse_advisory(raw, "appropriate-error", "f.py")
    assert len(out) == 1
    f = out[0]
    assert f.enforcement is Enforcement.ADVISORY and f.source == "llm"
    assert f.line == 4 and f.rule_id == "appropriate-error"


def test_parse_advisory_unparseable_and_empty():
    assert parse_advisory("not json", "r", "f.py") == []
    assert parse_advisory(json.dumps({"findings": []}), "r", "f.py") == []


def test_review_runs_only_llm_rules_and_never_blocks():
    llm = ScriptedClient(router=lambda s, p: json.dumps(
        {"findings": [{"message": "this silently swallows an error two callers rely on", "line": 2}]}))
    out = review_code("f.py", "try:\n  x()\nexcept: pass", kb_with_llm_rule(), gate(), llm, language="py")
    assert len(out) == 1                      # only the 1 LLM rule ran (deterministic rule ignored)
    assert all(f.enforcement is Enforcement.ADVISORY for f in out)
    assert len(llm.calls) == 1               # exactly one LLM call (the single LLM rule)


def test_review_no_llm_rules_no_calls():
    kb = Kb(name="t")
    kb.add_rule(Rule(id="d", name="d", intent="i", kind=RuleKind.DETERMINISTIC,
                     enforcement=Enforcement.BLOCKING, tool="ruff"))
    llm = ScriptedClient(responses=["unused"])
    assert review_code("f.py", "code", kb, gate(), llm) == []
    assert llm.calls == []


# --------------------------------------------------------------------------- #
# subscription billing safety (offline)
# --------------------------------------------------------------------------- #
def test_cli_client_strips_api_key(monkeypatch):
    captured = {}

    class P:
        returncode = 0
        stdout = json.dumps({"result": "ok", "total_cost_usd": 0.01})
        stderr = ""

    def fake_run(args, **kw):
        captured["args"] = args
        captured["env"] = kw.get("env")
        captured["input"] = kw.get("input")
        return P()

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-strip-me")
    resp = ClaudeCLIClient().generate(system="S", prompt="P", model=CHEAP)
    assert resp.text == "ok"
    assert captured["args"][:2] == ["claude", "-p"]
    assert "--bare" not in captured["args"]
    assert captured["input"] == "P"
    assert "ANTHROPIC_API_KEY" not in captured["env"]
