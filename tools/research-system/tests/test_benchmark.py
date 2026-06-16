"""Phase 6 gate: B (verified) ships fewer unfaithful claims than A' (unverified),
with clean isolation (shared upstream), plus coverage + gap-honesty + cost."""

import json

from research_system.benchmark import (
    compare_arms,
    format_comparison,
    run_grounded_arm,
    score_presented,
)
from research_system.llm import LLMResponse, ScriptedClient
from research_system.orchestrate import OrchestratorConfig
from research_system.retrieve import Corpus, Document

DOC = "Verified fact: photosynthesis releases oxygen as a byproduct of converting CO2 and water."


def make_router(answer_payload):
    def router(system, prompt):
        if "break a research question" in system:                   # decompose
            return json.dumps({"subquestions": [
                {"text": "What is released?", "success_criteria": "a gas"}]})
        if "meticulous research extractor" in system:               # answer
            return json.dumps(answer_payload)
        if "adversarial fact-checker" in system:                    # verify
            return json.dumps({"verdict": "supported", "rationale": "ok"})
        return ""
    return router


REAL_AND_FAKE = {"answerable": True, "claims": [
    {"text": "Photosynthesis releases oxygen", "source_id": "s001",
     "quote": "photosynthesis releases oxygen as a byproduct"},          # real
    {"text": "Photosynthesis releases pure helium", "source_id": "s001",
     "quote": "photosynthesis releases pure helium daily"}]}             # fabricated


def corpus():
    return Corpus([Document(id="s001", text=DOC)])


def mk(router):
    return lambda: ScriptedClient(router=router)


def test_isolation_naive_presents_all_verified_filters():
    c = corpus()
    comp = compare_arms("q", c, mk(make_router(REAL_AND_FAKE)),
                        config=OrchestratorConfig(judges=("mid",)), score_judges=("mid",))
    # shared upstream answered 2 claims; A' keeps both, B keeps only the verified one
    assert comp.unverified.presented == 2
    assert comp.verified.presented == 1


def test_b_beats_naive_on_faithfulness_and_auditability():
    comp = compare_arms("q", corpus(), mk(make_router(REAL_AND_FAKE)),
                        config=OrchestratorConfig(judges=("mid",)), score_judges=("mid",),
                        must_include=["oxygen"])
    assert comp.verified.faithfulness == 1.0 and comp.verified.unfaithful == 0
    assert comp.verified.auditability == 1.0
    assert comp.unverified.faithfulness == 0.5 and comp.unverified.unfaithful == 1
    assert comp.unverified.auditability == 0.5
    assert comp.verified.coverage == 1.0          # "oxygen" present in B's claims
    table = format_comparison([comp])
    assert "unfaithful" in table and "gap-honesty" in table and "cost" in table


def test_gap_honesty_on_out_of_corpus_question():
    # answer fabricates claims whose quotes are NOT in the corpus (out-of-corpus question)
    fake_only = {"answerable": True, "claims": [
        {"text": "The CEO's address is 5 Foo St", "source_id": "s001",
         "quote": "the ceo lives at 5 foo street"}]}
    comp = compare_arms("unanswerable q", corpus(), mk(make_router(fake_only)),
                        config=OrchestratorConfig(judges=("mid",)), score_judges=("mid",),
                        answerable=False)
    # B verifies -> fabricated quote fails mechanical -> presents 0 -> gap-honest
    assert comp.verified.presented == 0
    assert comp.verified.gap_honest is True
    # A' presents the fabrication -> not gap-honest
    assert comp.unverified.presented == 1
    assert comp.unverified.gap_honest is False


def test_cost_attribution_verification_marginal():
    # fake client that reports a per-call cost so arm costs are comparable
    class CostClient:
        def generate(self, **kw):
            return LLMResponse(text=json.dumps(
                {"subquestions": [{"text": "t", "success_criteria": "c"}]}
                if "break a research question" in kw["system"] else
                ({"verdict": "supported"} if "adversarial" in kw["system"] else REAL_AND_FAKE)),
                model="m", cost_usd=0.01)

    comp = compare_arms("q", corpus(), lambda: CostClient(),
                        config=OrchestratorConfig(judges=("mid",)), score_judges=("mid",))
    # A' cost = upstream only; B cost = upstream + verification > A'
    assert comp.verified.cost_usd > comp.unverified.cost_usd


def test_run_grounded_arm_standalone():
    presented = run_grounded_arm("q", corpus(), ScriptedClient(router=make_router(REAL_AND_FAKE)),
                                 config=OrchestratorConfig(judges=("mid",)))
    assert len(presented) == 1 and presented[0].text == "Photosynthesis releases oxygen"
