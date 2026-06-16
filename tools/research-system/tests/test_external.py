"""Item 3: score an external (deep-research) report as arm A against the corpus."""

import json

from research_system.external import load_findings, score_external_report
from research_system.llm import ScriptedClient
from research_system.retrieve import Corpus, Document

DOC = "The survey reports that up to 57% of citations in attributed RAG answers are unfaithful."


def router_supported(system, prompt):
    if "adversarial fact-checker" in system:
        return json.dumps({"verdict": "supported"})
    return ""


def test_load_findings_handles_result_wrapper(tmp_path):
    p = tmp_path / "r.json"
    p.write_text(json.dumps({"result": {"findings": [{"claim": "x", "evidence": "y"}]}}),
                 encoding="utf-8")
    f = load_findings(p)
    assert len(f) == 1 and f[0]["claim"] == "x"


def test_score_external_faithfulness_and_auditability():
    corpus = Corpus([Document(id="s001", text=DOC)])
    findings = [
        # evidence span IS verbatim in the corpus -> auditable
        {"claim": "57% of citations are unfaithful",
         "evidence": "up to 57% of citations in attributed RAG answers are unfaithful"},
        # evidence not in corpus -> not auditable
        {"claim": "unrelated claim about helium", "evidence": "helium is the lightest noble gas"},
    ]
    score = score_external_report(findings, corpus, ScriptedClient(router=router_supported),
                                  judges=("mid",))
    assert score.presented == 2
    assert score.faithful == 2                 # judge (fake) supports both
    assert score.auditability == 0.5           # 1 of 2 findings has a verbatim corpus span
    assert score.name.startswith("A")


def test_score_external_empty():
    score = score_external_report([], Corpus([Document(id="s001", text=DOC)]),
                                  ScriptedClient(router=router_supported))
    assert score.presented == 0 and score.auditability == 0.0
