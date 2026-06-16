"""Phase 2 gate: answerer emits validated, grounded claims; quotes verbatim."""

import json

from research_system.answer import answer_subquestion, build_answer_prompt, parse_claims
from research_system.contracts import SubQuestion, Verdict
from research_system.llm import ScriptedClient
from research_system.retrieve import Corpus, Document, Retrieved

DOC_TEXT = (
    "RAGTruth comprises nearly 18,000 naturally generated responses from diverse LLMs. "
    "A fine-tuned small model achieves competitive hallucination detection versus GPT-4."
)


class FakeRetriever:
    def __init__(self, ids):
        self._ids = ids

    def top_k(self, query, k):
        return [Retrieved(source_id=i, score=1.0) for i in self._ids[:k]]


def make_corpus():
    return Corpus([Document(id="s001", text=DOC_TEXT),
                   Document(id="s002", text="Unrelated text about weather.")])


def subq():
    return SubQuestion(id="q1", text="How big is RAGTruth?", success_criteria="a number")


# --------------------------------------------------------------------------- #
# prompt + parsing
# --------------------------------------------------------------------------- #
def test_build_prompt_includes_ids_and_question():
    p = build_answer_prompt("How big is RAGTruth?", [("s001", DOC_TEXT)])
    assert "SOURCE s001" in p and "How big is RAGTruth?" in p


def test_parse_claims_valid():
    raw = json.dumps({"answerable": True, "claims": [
        {"text": "RAGTruth has ~18,000 responses", "source_id": "s001",
         "quote": "nearly 18,000 naturally generated responses"}]})
    claims = parse_claims(raw, "q1", {"s001"})
    assert len(claims) == 1
    assert claims[0].id == "q1-c0" and claims[0].verdict is Verdict.PENDING


def test_parse_claims_drops_unknown_source_and_empty():
    raw = json.dumps({"claims": [
        {"text": "x", "source_id": "s999", "quote": "q"},      # unknown id
        {"text": "", "source_id": "s001", "quote": "q"},        # empty text
        {"text": "y", "source_id": "s001", "quote": ""}]})      # empty quote
    assert parse_claims(raw, "q1", {"s001"}) == []


def test_parse_claims_tolerates_prose_wrapper():
    raw = 'Sure! Here is the JSON:\n{"claims":[{"text":"t","source_id":"s001","quote":"q"}]}\nDone.'
    assert len(parse_claims(raw, "q1", {"s001"})) == 1


def test_parse_claims_unparseable_returns_empty():
    assert parse_claims("not json at all", "q1", {"s001"}) == []


# --------------------------------------------------------------------------- #
# answer_subquestion end-to-end (fake LLM)
# --------------------------------------------------------------------------- #
def test_answer_emits_grounded_claims_with_verbatim_quote():
    llm = ScriptedClient(responses=[json.dumps({"answerable": True, "claims": [
        {"text": "RAGTruth has nearly 18,000 responses", "source_id": "s001",
         "quote": "nearly 18,000 naturally generated responses"}]})])
    claims = answer_subquestion(subq(), FakeRetriever(["s001"]), make_corpus(), llm, k=5)
    assert len(claims) == 1
    # the gate criterion: emitted quote is present verbatim in the cited source
    assert claims[0].quote_present is True


def test_answer_flags_fabricated_quote_as_not_present():
    llm = ScriptedClient(responses=[json.dumps({"answerable": True, "claims": [
        {"text": "RAGTruth has a million responses", "source_id": "s001",
         "quote": "exactly one million annotated responses"}]})])  # not in source
    claims = answer_subquestion(subq(), FakeRetriever(["s001"]), make_corpus(), llm, k=5)
    assert len(claims) == 1
    assert claims[0].quote_present is False  # caught by mechanical check


def test_answer_unanswerable_returns_empty():
    llm = ScriptedClient(responses=[json.dumps({"answerable": False, "claims": []})])
    assert answer_subquestion(subq(), FakeRetriever(["s001"]), make_corpus(), llm, k=5) == []


def test_answer_no_docs_returns_empty_without_calling_llm():
    llm = ScriptedClient(responses=["should not be used"])
    claims = answer_subquestion(subq(), FakeRetriever([]), make_corpus(), llm, k=5)
    assert claims == []
    assert llm.calls == []
