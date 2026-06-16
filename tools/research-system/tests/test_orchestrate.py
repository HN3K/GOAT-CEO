"""Phase 5 gate: end-to-end orchestration, traceability, resumability."""

import json
import re

from research_system.grounding import quote_present
from research_system.llm import ScriptedClient
from research_system.orchestrate import OrchestratorConfig, run_research
from research_system.paths import SubjectLayout
from research_system.retrieve import Corpus

DOC1 = (
    "Alpha: the sky appears blue due to Rayleigh scattering of sunlight. "
    "Beta: water boils at 100 C at sea level under standard pressure."
)


def router(system, prompt):
    if "break a research question" in system:                       # decompose
        return json.dumps({"subquestions": [
            {"text": "Why is the sky blue?", "success_criteria": "a mechanism"},
            {"text": "When does water boil?", "success_criteria": "a temperature"}]})
    if "meticulous research extractor" in system:                   # answer
        return json.dumps({"answerable": True, "claims": [
            {"text": "Sky is blue from Rayleigh scattering", "source_id": "s001",
             "quote": "the sky appears blue due to Rayleigh scattering"},
            {"text": "Water boils at 100 C at sea level", "source_id": "s001",
             "quote": "water boils at 100 C at sea level"}]})
    if "adversarial fact-checker" in system:                        # verify
        return json.dumps({"verdict": "supported", "rationale": "ok"})
    return ""


def setup_corpus(tmp_path):
    lay = SubjectLayout(tmp_path, "demo").ensure()
    lay.source_md("s001").write_text(DOC1, encoding="utf-8")
    return lay


def test_end_to_end_traceable(tmp_path):
    lay = setup_corpus(tmp_path)
    corpus = Corpus.load(lay)
    res = run_research(lay, "explain natural phenomena", ScriptedClient(router=router),
                       config=OrchestratorConfig(min_support=2))
    assert res.n_supported == 4
    assert lay.questions_path.exists() and lay.claims_path.exists()
    assert lay.synthesis_path.exists() and lay.gaps_path.exists()

    # GATE: every citation in synthesis.md traces to a verbatim quote in its source
    text = lay.synthesis_path.read_text(encoding="utf-8")
    cites = re.findall(r'source `(\w+)`: "(.+)"', text)
    assert len(cites) == 4
    for sid, quote in cites:
        assert quote_present(quote, corpus.get(sid))


def test_resume_skips_all_completed_stages(tmp_path):
    lay = setup_corpus(tmp_path)
    run_research(lay, "q", ScriptedClient(router=router), config=OrchestratorConfig(min_support=2))

    # All checkpoints exist; a fresh client must NOT be called on resume.
    llm2 = ScriptedClient(responses=[])
    res2 = run_research(lay, "q", llm2, resume=True, config=OrchestratorConfig(min_support=2))
    assert llm2.calls == []
    assert res2.n_supported == 4


def test_resume_after_decompose_only_runs_answer_not_decompose(tmp_path):
    lay = setup_corpus(tmp_path)
    # simulate a kill right after decompose: only questions.json present
    from research_system.contracts import write_model
    from research_system.decompose import decompose
    write_model(decompose("q", ScriptedClient(router=router), n=2), lay.questions_path)
    assert not lay.claims_path.exists()

    llm = ScriptedClient(router=router)
    res = run_research(lay, "q", llm, resume=True, config=OrchestratorConfig(min_support=2))
    # decompose must NOT have been re-invoked
    assert not any("break a research question" in c["system"] for c in llm.calls)
    assert res.n_supported == 4
