"""Phase 1 gate: KB store round-trip, queries, ref validation, real seed KB."""

from pathlib import Path

from rubric.contracts import Convention, Enforcement, Exemplar, Rule, RuleKind
from rubric.kb import Kb
from rubric.paths import KbLayout

REPO = Path(__file__).resolve().parent.parent


def make_kb():
    kb = Kb(name="t")
    kb.add_rule(Rule(id="r-ts", name="ts rule", intent="i", kind=RuleKind.DETERMINISTIC,
                     enforcement=Enforcement.BLOCKING, tool="ast-grep", languages=["ts"], tags=["a"]))
    kb.add_rule(Rule(id="r-any", name="any rule", intent="i", kind=RuleKind.LLM,
                     enforcement=Enforcement.ADVISORY, tags=["b"]))  # no languages = agnostic
    kb.add_exemplar(Exemplar(id="e1", title="t", intent="i", language="ts", code="x", tags=["a"]))
    kb.add_convention(Convention(id="c1", name="c", intent="i", rule_ids=["r-ts"], exemplar_ids=["e1"]))
    return kb


def test_save_load_round_trip(tmp_path):
    kb = make_kb()
    layout = KbLayout(tmp_path / "kb")
    kb.save(layout)
    loaded = Kb.load(layout)
    assert set(loaded.rules) == {"r-ts", "r-any"}
    assert set(loaded.exemplars) == {"e1"}
    assert set(loaded.conventions) == {"c1"}
    assert loaded.rules["r-ts"] == kb.rules["r-ts"]
    assert loaded.name == "t"


def test_rules_for_language():
    kb = make_kb()
    ts = {r.id for r in kb.rules_for_language("ts")}
    py = {r.id for r in kb.rules_for_language("py")}
    assert ts == {"r-ts", "r-any"}      # r-any is language-agnostic
    assert py == {"r-any"}              # r-ts is ts-only


def test_exemplars_for_tags():
    kb = make_kb()
    assert [e.id for e in kb.exemplars_for_tags(["a"])] == ["e1"]
    assert kb.exemplars_for_tags(["zzz"]) == []


def test_validate_refs_detects_missing():
    kb = Kb(name="t")
    kb.add_convention(Convention(id="c", name="c", intent="i",
                                 rule_ids=["ghost"], exemplar_ids=["nope"]))
    problems = kb.validate_refs()
    assert any("missing rule ghost" in p for p in problems)
    assert any("missing exemplar nope" in p for p in problems)


def test_real_seed_kb_loads_clean():
    layout = KbLayout(REPO / "kb")
    kb = Kb.load(layout)
    assert kb.name == "rubric-starter"
    assert {"named-exports", "colocated-tests", "error-handling"} <= set(kb.conventions)
    assert kb.validate_refs() == []
    # the boundary split is represented: at least one blocking-deterministic + one advisory-LLM rule
    kinds = {(r.kind, r.enforcement) for r in kb.rules.values()}
    assert (RuleKind.DETERMINISTIC, Enforcement.BLOCKING) in kinds
    assert (RuleKind.LLM, Enforcement.ADVISORY) in kinds
