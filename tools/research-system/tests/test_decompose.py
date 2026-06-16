"""Phase 5: question decomposition."""

import json

from research_system.decompose import decompose, parse_subquestions
from research_system.llm import ScriptedClient


def test_parse_assigns_ids_and_criteria():
    raw = json.dumps({"subquestions": [
        {"text": "What is X?", "success_criteria": "a definition"},
        {"text": "How big is Y?", "success_criteria": "a number"}]})
    sqs = parse_subquestions(raw, max_n=6)
    assert [s.id for s in sqs] == ["q1", "q2"]
    assert sqs[0].text == "What is X?" and sqs[1].success_criteria == "a number"


def test_parse_drops_empty():
    raw = json.dumps({"subquestions": [{"text": "keep"}, {"text": ""}, {"text": "also keep"}]})
    assert [s.text for s in parse_subquestions(raw, max_n=6)] == ["keep", "also keep"]


def test_parse_caps_to_max_n():
    raw = json.dumps({"subquestions": [{"text": "a"}, {"text": "b"}, {"text": "c"}]})
    assert [s.text for s in parse_subquestions(raw, max_n=2)] == ["a", "b"]


def test_parse_unparseable_returns_empty():
    assert parse_subquestions("not json", 6) == []


def test_decompose_builds_questions_file():
    llm = ScriptedClient(responses=[json.dumps({"subquestions": [
        {"text": "Q1?", "success_criteria": "c1"}]})])
    qf = decompose("big question", llm, n=6)
    assert qf.question == "big question"
    assert len(qf.subquestions) == 1 and qf.subquestions[0].id == "q1"
