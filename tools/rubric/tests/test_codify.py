"""Codify loop — recurring verified findings become KB proposals (observe-drift→codify)."""

import json
from pathlib import Path

from rubric.codify import (
    draft_proposal,
    propose_codifications,
    save_proposals,
)
from rubric.contracts import CodifyProposal, Enforcement, Finding, RuleKind, Severity
from rubric.kb import Kb
from rubric.llm import ScriptedClient
from rubric.paths import RepoLayout


def _f(rule_id=None, message="m", path="a.py", line=1):
    return Finding(source="llm", rule_id=rule_id, enforcement=Enforcement.ADVISORY,
                   severity=Severity.INFO, message=message, path=path, line=line)


def _proposal(**kw):
    base = dict(kind="rule-new", title="Magic numbers", rationale="recurs", occurrences=3,
                evidence=["a.py:1 magic number"])
    base.update(kw)
    return CodifyProposal(**base)


def test_below_threshold_proposes_nothing():
    assert propose_codifications([_f(rule_id="r"), _f(rule_id="r")], threshold=3) == []


def test_recurring_rule_proposes_tightening():
    findings = [_f(rule_id="errors", path=f"f{i}.py", line=i) for i in range(4)]
    props = propose_codifications(findings, threshold=3)
    assert len(props) == 1
    assert props[0].kind == "rule-tighten" and props[0].rule_id == "errors"
    assert props[0].occurrences == 4
    assert len(props[0].evidence) == 4


def test_recurring_unruled_issue_proposes_new_rule():
    findings = [_f(rule_id=None, message="magic number 42 here", path=f"f{i}.py") for i in range(3)]
    props = propose_codifications(findings, threshold=3)
    assert len(props) == 1 and props[0].kind == "rule-new"


def test_clusters_unruled_by_normalized_message():
    # differing line numbers normalize to the same shape -> one cluster
    findings = [_f(rule_id=None, message=f"magic number {n}") for n in (1, 2, 3, 4)]
    props = propose_codifications(findings, threshold=4)
    assert len(props) == 1 and props[0].occurrences == 4


def test_proposals_sorted_by_occurrence():
    findings = ([_f(rule_id="a") for _ in range(3)] + [_f(rule_id="b") for _ in range(5)])
    props = propose_codifications(findings, threshold=3)
    assert [p.rule_id for p in props] == ["b", "a"]


# --------------------------------------------------------------------------- #
# auto-draft (LLM)
# --------------------------------------------------------------------------- #
def test_draft_populates_rule_and_exemplar():
    drafted = json.dumps({
        "rule": {"id": "no-magic-numbers", "name": "No magic numbers", "intent": "Name constants.",
                 "kind": "llm", "enforcement": "advisory", "spec": "Flag unexplained literals.",
                 "languages": ["py"], "tags": ["clarity"]},
        "exemplar": {"title": "Named constant", "intent": "use a name", "language": "py",
                     "code": "MAX_RETRIES = 3", "tags": ["clarity"]}})
    out = draft_proposal(_proposal(), ScriptedClient(responses=[drafted]))
    assert out.suggested_rule is not None
    assert out.suggested_rule.id == "no-magic-numbers" and out.suggested_rule.kind is RuleKind.LLM
    assert out.suggested_exemplar is not None and out.suggested_exemplar.code == "MAX_RETRIES = 3"


def test_draft_slugifies_id_and_survives_missing_fields():
    drafted = json.dumps({"rule": {"name": "Some Rule!!", "intent": "x", "kind": "llm",
                                   "enforcement": "advisory", "spec": "s"}, "exemplar": None})
    out = draft_proposal(_proposal(), ScriptedClient(responses=[drafted]))
    assert out.suggested_rule.id == "some-rule" and out.suggested_exemplar is None


def test_draft_malformed_json_returns_proposal_unchanged():
    out = draft_proposal(_proposal(), ScriptedClient(responses=["not json at all"]))
    assert out.suggested_rule is None and out.suggested_exemplar is None


def test_draft_tighten_grounds_in_existing_rule():
    kb = Kb(name="t")
    from rubric.contracts import Rule
    kb.add_rule(Rule(id="errors", name="errors", intent="no swallow", kind=RuleKind.LLM,
                     enforcement=Enforcement.ADVISORY, spec="check errors"))
    seen = {}

    def route(system, prompt):
        seen["prompt"] = prompt
        return json.dumps({"rule": {"id": "errors", "name": "errors", "intent": "tightened",
                                    "kind": "deterministic", "enforcement": "blocking",
                                    "tool": "ast-grep", "spec": "except: $$$"}, "exemplar": None})
    out = draft_proposal(_proposal(kind="rule-tighten", rule_id="errors", title="Recurring errors"),
                         ScriptedClient(router=route), kb=kb)
    assert "EXISTING RULE" in seen["prompt"] and "check errors" in seen["prompt"]
    assert out.suggested_rule.tool == "ast-grep"


def test_save_proposals_writes_files(tmp_path):
    paths = save_proposals([_proposal(), _proposal(title="Other")], RepoLayout(str(tmp_path)))
    assert len(paths) == 2
    assert (tmp_path / ".rubric" / "proposals").is_dir()
    data = json.loads(Path(paths[0]).read_text(encoding="utf-8"))
    assert data["title"] == "Magic numbers"
