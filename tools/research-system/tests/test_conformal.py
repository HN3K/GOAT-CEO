"""Phase 7: split-conformal abstention threshold + coverage guarantee."""

import math

from research_system.conformal import (
    CalibrationExample,
    calibrate,
    confidence_score,
    conformal_threshold,
    should_answer,
)
from research_system.contracts import Claim, Verdict


def test_threshold_quantile_math():
    scores = list(range(10))  # 0..9
    # rank = floor(0.2 * 11) = 2 -> sorted[1] = 1
    assert conformal_threshold(scores, 0.2) == 1
    # rank = floor(0.1 * 11) = 1 -> sorted[0] = 0
    assert conformal_threshold(scores, 0.1) == 0


def test_threshold_degenerate_alpha():
    scores = list(range(10))
    assert conformal_threshold(scores, 0.0) == -math.inf
    assert conformal_threshold(scores, 1.0) == -math.inf      # out of (0,1)
    assert conformal_threshold([], 0.2) == -math.inf


def test_coverage_guarantee_on_calibration():
    scores = list(range(10))
    alpha = 0.2
    tau = conformal_threshold(scores, alpha)
    abstained = [s for s in scores if not should_answer(s, tau)]
    assert len(abstained) / len(scores) <= alpha     # ≤ alpha truly-answerable abstained


def test_calibrate_uses_only_answerable():
    cal = [
        CalibrationExample(score=5, answerable=True),
        CalibrationExample(score=6, answerable=True),
        CalibrationExample(score=0, answerable=False),   # ignored
        CalibrationExample(score=7, answerable=True),
    ]
    tau = calibrate(cal, 0.2)
    # only scores [5,6,7] used; rank=floor(0.2*4)=0 -> -inf (answer all 3 answerable)
    assert tau == -math.inf


def test_should_answer():
    assert should_answer(3, 2) and should_answer(2, 2)
    assert not should_answer(1, 2)


def test_confidence_score_counts_supported():
    cs = [
        Claim(id="a", subq_id="q", text="t", source_id="s", quote="x", verdict=Verdict.SUPPORTED),
        Claim(id="b", subq_id="q", text="t", source_id="s", quote="x", verdict=Verdict.UNSUPPORTED),
        Claim(id="c", subq_id="q", text="t", source_id="s", quote="x", verdict=Verdict.SUPPORTED),
    ]
    assert confidence_score(cs) == 2


def _sup(subq, k):
    return [Claim(id=f"{subq}-{i}", subq_id=subq, text="t", source_id="s", quote="x",
                  verdict=Verdict.SUPPORTED) for i in range(k)]


def test_calibrate_from_labeled():
    from research_system.conformal import calibrate_from_labeled
    # answerable sub-questions have scores 1..5; unanswerable have 0
    labeled = [(_sup("a", k), True) for k in (1, 2, 3, 4, 5)] + [(_sup("n", 0), False)]
    tau = calibrate_from_labeled(labeled, alpha=0.2)
    # answerable scores [1,2,3,4,5]; rank=floor(0.2*6)=1 -> sorted[0]=1
    assert tau == 1


def test_gate_uses_threshold_over_min_support():
    from research_system.gate import gate_status
    from research_system.contracts import SubQuestionStatus
    cs = _sup("q", 3)  # 3 supported claims
    # heuristic min_support=5 -> PARTIAL; conformal threshold=2 -> ANSWERED (overrides)
    assert gate_status(cs, min_support=5) is SubQuestionStatus.PARTIAL
    assert gate_status(cs, min_support=5, threshold=2) is SubQuestionStatus.ANSWERED
    assert gate_status(_sup("q", 0), threshold=2) is SubQuestionStatus.UNANSWERED
