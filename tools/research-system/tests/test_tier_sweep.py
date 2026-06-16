"""Phase 7: model-tier sweep harness + cost tracking."""

import json

from research_system.llm import CHEAP, MID, CostTracker, LLMResponse, ScriptedClient
from research_system.orchestrate import OrchestratorConfig
from research_system.retrieve import Corpus, Document
from research_system.tier_sweep import format_tier_table, run_tier_sweep

DOC = "Verified fact: photosynthesis releases oxygen as a byproduct of converting CO2 and water."


def router(system, prompt):
    if "break a research question" in system:
        return json.dumps({"subquestions": [{"text": "What is released?", "success_criteria": "gas"}]})
    if "meticulous research extractor" in system:
        return json.dumps({"answerable": True, "claims": [
            {"text": "releases oxygen", "source_id": "s001",
             "quote": "photosynthesis releases oxygen as a byproduct"}]})
    if "adversarial fact-checker" in system:
        return json.dumps({"verdict": "supported", "rationale": "ok"})
    return ""


def test_cost_tracker_accumulates():
    class FakeCostClient:
        def generate(self, **kw):
            return LLMResponse(text="x", model="m", input_tokens=3, output_tokens=2, cost_usd=0.01)

    meter = CostTracker(FakeCostClient())
    for _ in range(3):
        meter.generate(system="s", prompt="p", model="m")
    assert meter.n_calls == 3
    assert round(meter.total_cost_usd, 2) == 0.03
    assert meter.input_tokens == 9 and meter.output_tokens == 6


def test_tier_sweep_runs_each_tier():
    corpus = Corpus([Document(id="s001", text=DOC)])
    outcomes = run_tier_sweep(
        "what does photosynthesis release?", corpus,
        make_client=lambda: ScriptedClient(router=router),
        tiers=(CHEAP, MID),
        base_config=OrchestratorConfig(judges=("mid",)),
        score_judges=("mid",),
    )
    assert [o.tier for o in outcomes] == [CHEAP, MID]
    for o in outcomes:
        assert o.result.presented == 1
        assert o.result.faithfulness == 1.0
        assert o.n_calls > 0          # the tier was actually exercised

    table = format_tier_table(outcomes)
    assert "extraction tier" in table and "cheap" in table and "mid" in table
