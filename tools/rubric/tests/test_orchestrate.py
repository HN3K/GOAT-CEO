"""Phase 5 gate: enforce combines blocking gate + advisory review into a Verdict."""

import json

from rubric.contracts import Enforcement, Finding, Rule, RuleKind, Severity
from rubric.kb import Kb
from rubric.llm import ScriptedClient
from rubric.orchestrate import build_context, enforce, language_of


class FakeAdapter:
    def __init__(self, name, findings, available=True):
        self.name = name
        self._f = findings
        self._a = available

    def available(self):
        return self._a

    def run(self, target, rules):
        return list(self._f)


def kb_with_rules():
    kb = Kb(name="t")
    kb.add_rule(Rule(id="errors", name="errors", intent="i", kind=RuleKind.LLM,
                     enforcement=Enforcement.ADVISORY, spec="check error handling", languages=["py"]))
    return kb


def test_language_of():
    assert language_of("a/b.py") == "py"
    assert language_of("x.tsx") == "tsx"
    assert language_of("Makefile") is None


def test_enforce_blocking_plus_advisory(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("try:\n  x()\nexcept: pass\n", encoding="utf-8")
    block = Finding(source="fake", rule_id="r", enforcement=Enforcement.BLOCKING,
                    severity=Severity.ERROR, message="deterministic block")
    llm = ScriptedClient(router=lambda s, p: json.dumps(
        {"findings": [{"message": "swallows an error callers rely on", "line": 3}]}))

    v = enforce(str(f), kb_with_rules(), adapters=[FakeAdapter("fake", [block])],
                llm=llm, language="py")
    assert v.passed is False
    assert [b.message for b in v.blocking] == ["deterministic block"]
    assert any(a.source == "llm" for a in v.advisory)
    assert all(a.enforcement is Enforcement.ADVISORY for a in v.advisory)


def _routed_client(verdict: str):
    """Review returns one finding; the adversarial verifier returns ``verdict`` for every judge."""
    def route(system, prompt):
        if "fact-checker" in system:          # VERIFY_SYSTEM
            return json.dumps({"verdict": verdict, "rationale": "r"})
        return json.dumps({"findings": [{"message": "swallows an error", "line": 3}]})
    return ScriptedClient(router=route)


def test_enforce_verify_drops_refuted_advisory(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("try:\n  x()\nexcept: pass\n", encoding="utf-8")
    v = enforce(str(f), kb_with_rules(), adapters=[FakeAdapter("fake", [])],
                llm=_routed_client("refuted"), language="py", verify=True)
    assert [a for a in v.advisory if a.source == "llm"] == []   # refuted -> dropped


def test_enforce_verify_keeps_confirmed_advisory_with_confidence(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("try:\n  x()\nexcept: pass\n", encoding="utf-8")
    v = enforce(str(f), kb_with_rules(), adapters=[FakeAdapter("fake", [])],
                llm=_routed_client("real"), language="py", verify=True)
    llm_findings = [a for a in v.advisory if a.source == "llm"]
    assert len(llm_findings) == 1 and llm_findings[0].confidence == 1.0


def test_enforce_no_llm_is_deterministic_only(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n", encoding="utf-8")
    v = enforce(str(f), kb_with_rules(), adapters=[FakeAdapter("fake", [])], llm=None, language="py")
    assert v.passed is True and v.blocking == [] and v.advisory == []


def test_enforce_passes_when_no_blocking(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n", encoding="utf-8")
    advisory = Finding(source="fake", enforcement=Enforcement.ADVISORY, message="nit")
    v = enforce(str(f), kb_with_rules(), adapters=[FakeAdapter("fake", [advisory])],
                llm=None, language="py")
    assert v.passed is True
    assert [a.message for a in v.advisory] == ["nit"]   # advisory deterministic finding surfaced


def test_build_context_renders(tmp_path):
    from rubric.contracts import Exemplar
    kb = Kb(name="t")
    kb.add_exemplar(Exemplar(id="e", title="Service", intent="how we write services",
                             language="ts", code="export class FooService {}", tags=["service"]))
    out = build_context("add a new service", kb, language="ts", k=3)
    assert "Standards context for: add a new service" in out
    assert "FooService" in out
