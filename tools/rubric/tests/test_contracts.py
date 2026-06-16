"""Phase 0 gate: contracts round-trip, reject drift, enforce blocking/advisory split."""

import pytest
from pydantic import ValidationError

from rubric.contracts import (
    SCHEMA_VERSION,
    Component,
    ContextPack,
    Convention,
    Enforcement,
    Exemplar,
    Finding,
    GateResult,
    KbManifest,
    Rule,
    RuleKind,
    Verdict,
    read_model,
    write_model,
)


def sample_rule(**kw):
    base = dict(id="no-default-export", name="No default exports", intent="grep-ability",
                kind=RuleKind.DETERMINISTIC, enforcement=Enforcement.BLOCKING,
                tool="ast-grep", spec="no-default-export", languages=["ts"], tags=["imports"])
    base.update(kw)
    return Rule(**base)


def sample_exemplar():
    return Exemplar(id="ex-service", title="Service class", intent="how we write services",
                    language="ts", code="export class FooService {}", tags=["service"])


@pytest.mark.parametrize("model, cls", [
    (sample_rule(), Rule),
    (sample_exemplar(), Exemplar),
    (Convention(id="c1", name="Imports", intent="x", rule_ids=["r"], exemplar_ids=["e"]), Convention),
    (KbManifest(name="kb", rule_ids=["r"]), KbManifest),
    (ContextPack(task="add endpoint", exemplars=[sample_exemplar()], rules=[sample_rule()],
                 components=[Component(id="c", name="db")]), ContextPack),
])
def test_round_trip(tmp_path, model, cls):
    p = tmp_path / "m.json"
    write_model(model, p)
    assert read_model(cls, p) == model


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        Rule.model_validate({"id": "x", "name": "y", "intent": "z", "kind": "deterministic",
                             "enforcement": "blocking", "bogus": 1})


def test_bad_enum_rejected():
    with pytest.raises(ValidationError):
        sample_rule(kind="magic")


def test_schema_version():
    assert KbManifest(name="k").schema_version == SCHEMA_VERSION


# --- the load-bearing rule: blocking vs advisory (DESIGN P3) ----------------- #
def test_gate_blocking_fails_advisory_passes():
    blocking = Finding(source="ruff", enforcement=Enforcement.BLOCKING, message="E501")
    advisory = Finding(source="llm", enforcement=Enforcement.ADVISORY, message="consider renaming")

    g_block = GateResult(target="f.py", findings=[blocking, advisory])
    assert g_block.blocking == [blocking]
    assert g_block.passed is False

    g_pass = GateResult(target="f.py", findings=[advisory])
    assert g_pass.blocking == []
    assert g_pass.passed is True


def test_verdict_round_trip(tmp_path):
    v = Verdict(target="f.py", passed=False,
                blocking=[Finding(source="ast-grep", enforcement=Enforcement.BLOCKING, message="x")],
                advisory=[Finding(source="llm", enforcement=Enforcement.ADVISORY, message="y")])
    write_model(v, tmp_path / "v.json")
    assert read_model(Verdict, tmp_path / "v.json") == v
