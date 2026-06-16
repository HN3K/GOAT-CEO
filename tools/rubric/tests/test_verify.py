"""Adversarial verification of advisory findings — fabrication kill + skeptical ensemble."""

import json

from rubric.contracts import Enforcement, Finding, Severity
from rubric.llm import ScriptedClient
from rubric.verify import (
    JudgeVote,
    confidence_of,
    parse_vote,
    quote_present,
    survives,
    verify_finding,
    verify_findings,
)

CODE = "def f():\n    try:\n        g()\n    except:\n        pass\n"


def _finding(message="swallows an error", quote=None, line=4):
    return Finding(source="llm", enforcement=Enforcement.ADVISORY, severity=Severity.INFO,
                   message=message, path="f.py", line=line, quote=quote)


def _vote(real):
    return json.dumps({"verdict": "real" if real else "refuted", "rationale": "r"})


# --------------------------------------------------------------------------- #
# mechanical floor
# --------------------------------------------------------------------------- #
def test_quote_present_ignores_whitespace():
    assert quote_present("except:\n    pass", "x\nexcept:      pass\ny")
    assert not quote_present("raise ValueError()", CODE)
    assert not quote_present("", CODE)


def test_fabricated_span_is_killed_without_model_cost():
    llm = ScriptedClient(responses=[_vote(True), _vote(True), _vote(True)])
    kept, votes = verify_finding(_finding(quote="raise NeverHappens()"), CODE, llm)
    assert kept is False
    assert votes[0].model == "mechanical"
    assert llm.calls == []                      # no judge was ever called


# --------------------------------------------------------------------------- #
# parsing + aggregation
# --------------------------------------------------------------------------- #
def test_parse_vote():
    assert parse_vote(_vote(True))[0] is True
    assert parse_vote(_vote(False))[0] is False
    assert parse_vote("garbage")[0] is False    # conservative default


def test_survives_strict_majority_and_tie_is_skeptical():
    real, refuted = JudgeVote("m", True), JudgeVote("m", False)
    assert survives([real, real, refuted]) is True
    assert survives([real, refuted]) is False   # tie -> refuted
    assert survives([]) is False


def test_confidence_is_fraction_affirming():
    assert confidence_of([JudgeVote("m", True), JudgeVote("m", True), JudgeVote("m", False)]) == 2 / 3


# --------------------------------------------------------------------------- #
# ensemble end-to-end
# --------------------------------------------------------------------------- #
def test_majority_real_survives_with_confidence():
    llm = ScriptedClient(responses=[_vote(True), _vote(True), _vote(False)])
    out = verify_findings([_finding()], CODE, llm)
    assert len(out) == 1 and out[0].confidence == 2 / 3
    assert len(llm.calls) == 3                   # three judges voted


def test_majority_refuted_is_dropped():
    llm = ScriptedClient(responses=[_vote(False), _vote(False), _vote(True)])
    assert verify_findings([_finding()], CODE, llm) == []
