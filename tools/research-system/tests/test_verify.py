"""Phase 3 gate: mechanical fabrication kill, grounded judging, ensemble quorum."""

import json

from research_system.contracts import Claim, JudgeVote, Verdict
from research_system.llm import ScriptedClient
from research_system.retrieve import Corpus, Document
from research_system.verify import (
    aggregate_votes,
    build_verify_prompt,
    context_window,
    parse_verdict,
    verify_claim,
)

SOURCE = (
    "Intro paragraph with background material that is fairly long. " * 30
    + "RAGTruth comprises nearly 18,000 naturally generated responses from diverse LLMs. "
    + "Tail paragraph with more discussion and analysis follows here. " * 30
)


def corpus():
    return Corpus([Document(id="s001", text=SOURCE)])


def claim(quote, text="RAGTruth has ~18,000 responses", source_id="s001"):
    return Claim(id="c1", subq_id="q1", text=text, source_id=source_id, quote=quote)


def vote(v):
    return json.dumps({"verdict": v, "rationale": "because"})


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def test_context_window_locates_quote():
    q = "nearly 18,000 naturally generated responses"
    ctx = context_window(SOURCE, q, radius=100)
    assert q in ctx
    assert len(ctx) < len(SOURCE)  # focused window, not whole doc


def test_context_window_fallback_when_absent():
    ctx = context_window(SOURCE, "this exact phrase is not present", radius=50)
    assert "this exact phrase is not present" in ctx  # appended for the judge


def test_parse_verdict_valid_and_default():
    assert parse_verdict(vote("supported"))[0] is Verdict.SUPPORTED
    assert parse_verdict(vote("overreach"))[0] is Verdict.OVERREACH
    assert parse_verdict("garbage non-json")[0] is Verdict.UNSUPPORTED  # conservative


def test_build_verify_prompt_has_parts():
    p = build_verify_prompt("claim", "quote", "ctx")
    assert "CLAIM:" in p and "QUOTE" in p and "SOURCE CONTEXT:" in p


# --------------------------------------------------------------------------- #
# aggregate_votes
# --------------------------------------------------------------------------- #
def _votes(*vs):
    return [JudgeVote(model="m", verdict=v) for v in vs]


def test_aggregate_strict_majority_supported():
    S, U, O = Verdict.SUPPORTED, Verdict.UNSUPPORTED, Verdict.OVERREACH
    assert aggregate_votes(_votes(S, S, S)) is S
    assert aggregate_votes(_votes(S, S, U)) is S        # 2/3 supported passes
    assert aggregate_votes(_votes(S, U, O)) is U        # no majority -> conservative
    assert aggregate_votes(_votes(O, O, S)) is O        # overreach majority
    assert aggregate_votes(_votes(U, U, S)) is U
    assert aggregate_votes(_votes(S, U)) is U           # tie never passes


# --------------------------------------------------------------------------- #
# verify_claim — the three stages
# --------------------------------------------------------------------------- #
def test_mechanical_kills_fabricated_quote_without_llm():
    llm = ScriptedClient(responses=[vote("supported")] * 3)  # should be untouched
    c = verify_claim(claim("a quote that is absolutely not in the source"), corpus(), llm)
    assert c.verdict is Verdict.UNSUPPORTED
    assert c.quote_present is False
    assert c.judge_votes[0].model == "mechanical"
    assert llm.calls == []  # zero model cost for fabrication


def test_present_quote_unanimous_supported():
    llm = ScriptedClient(responses=[vote("supported")] * 3)
    c = verify_claim(claim("nearly 18,000 naturally generated responses"), corpus(), llm)
    assert c.quote_present is True
    assert c.verdict is Verdict.SUPPORTED
    assert len(c.judge_votes) == 3


def test_ensemble_rescues_single_judge_false_rejection():
    # one judge wrongly says 'unsupported'; the other two say 'supported'
    llm = ScriptedClient(responses=[vote("supported"), vote("unsupported"), vote("supported")])
    c = verify_claim(claim("nearly 18,000 naturally generated responses"), corpus(), llm)
    assert c.verdict is Verdict.SUPPORTED  # ensemble overrides the lone false-reject
    # a single-judge verifier using that 2nd vote alone would have wrongly rejected.


def test_overreach_majority_detected():
    llm = ScriptedClient(responses=[vote("overreach"), vote("overreach"), vote("supported")])
    c = verify_claim(claim("nearly 18,000 naturally generated responses",
                           text="RAGTruth proves all RAG hallucination is solved"), corpus(), llm)
    assert c.verdict is Verdict.OVERREACH


def test_unknown_source_is_unsupported():
    llm = ScriptedClient(responses=[vote("supported")] * 3)
    c = verify_claim(claim("anything", source_id="s999"), corpus(), llm)
    assert c.verdict is Verdict.UNSUPPORTED
    assert llm.calls == []
