"""Phase 3 gate: retrieval selects right exemplars/components, caps, renders pack."""

from rubric.contracts import Component, Enforcement, Exemplar, Rule, RuleKind
from rubric.kb import Kb
from rubric.retrieve import (
    build_context_pack,
    render_context_pack,
    select_components,
    select_exemplars,
    select_rules,
)


def make_kb():
    kb = Kb(name="t")
    kb.add_exemplar(Exemplar(id="ex-err", title="Error handling", intent="how we handle errors",
                             language="ts", code="throw new NotFoundError()", tags=["errors"]))
    kb.add_exemplar(Exemplar(id="ex-svc", title="Service class", intent="how we write services",
                             language="ts", code="export class FooService {}", tags=["service"]))
    kb.add_rule(Rule(id="r-ts", name="ts only", intent="i", kind=RuleKind.DETERMINISTIC,
                     enforcement=Enforcement.BLOCKING, tool="ast-grep", languages=["ts"]))
    kb.add_rule(Rule(id="r-any", name="agnostic", intent="i", kind=RuleKind.LLM,
                     enforcement=Enforcement.ADVISORY))
    return kb


def test_select_exemplars_ranks_relevant_first():
    kb = make_kb()
    out = select_exemplars(kb, "add error handling to the loader", k=2)
    assert out[0].id == "ex-err"


def test_select_exemplars_caps():
    kb = make_kb()
    assert len(select_exemplars(kb, "service error", k=1)) == 1
    assert select_exemplars(kb, "x", k=0) == []


def test_select_rules_by_language():
    kb = make_kb()
    assert {r.id for r in select_rules(kb, "ts")} == {"r-ts", "r-any"}
    assert {r.id for r in select_rules(kb, "py")} == {"r-any"}


def test_select_components_reuse_ranking():
    comps = [
        Component(id="db", name="Database", signature="db.query(sql)", summary="postgres access"),
        Component(id="mail", name="Mailer", signature="send(to, body)", summary="email sending"),
    ]
    out = select_components(comps, "store the user in the database", k=1)
    assert out[0].id == "db"


def test_build_and_render_context_pack():
    kb = make_kb()
    comps = [Component(id="db", name="Database", signature="db.query(sql)", summary="postgres access")]
    pack = build_context_pack("add error handling that stores to the database",
                              kb, language="ts", components=comps, k=2)
    assert pack.task.startswith("add error handling")
    assert any(e.id == "ex-err" for e in pack.exemplars)
    assert any(c.id == "db" for c in pack.components)
    assert {r.id for r in pack.rules} == {"r-ts", "r-any"}

    rendered = render_context_pack(pack)
    assert "Conventions to follow" in rendered
    assert "REUSE these" in rendered and "Database" in rendered     # reuse section
    assert "Canonical exemplars" in rendered and "NotFoundError" in rendered
    assert "(MUST)" in rendered and "(should)" in rendered          # blocking vs advisory surfaced
