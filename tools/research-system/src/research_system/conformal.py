"""Phase 7 — Calibrated abstention via split conformal prediction (DESIGN P8).

Replaces the heuristic support-count gate with a threshold that carries a
finite-sample guarantee. Given labeled calibration examples (confidence score +
whether the question was genuinely answerable), `conformal_threshold` picks τ
such that answering iff ``score >= τ`` wrongly abstains on at most a fraction
``alpha`` of truly-answerable questions — a marginal coverage guarantee under
exchangeability (Abbasi-Yadkori et al. 2024, [F-2405.01563]).

Honest scope: the guarantee is MARGINAL (averaged over draws), assumes the
calibration and test questions are exchangeable, and degrades under distribution
shift / tiny calibration sets. It bounds false-abstention on answerable items; it
does not by itself bound the converse (answering an unanswerable item) — pair it
with the verification gate, which removes unsupported claims regardless.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from research_system.contracts import Claim, Verdict


def confidence_score(claims_for_subq: list[Claim]) -> int:
    """Confidence signal for a sub-question = number of SUPPORTED claims.

    Higher = more grounded support. This is the quantity the conformal threshold
    is calibrated against (swappable for a finer score later, e.g. mean judge
    agreement)."""
    return sum(1 for c in claims_for_subq if c.verdict is Verdict.SUPPORTED)


@dataclass
class CalibrationExample:
    score: float
    answerable: bool   # ground truth: was this question genuinely answerable from the corpus?


def conformal_threshold(answerable_scores: list[float], alpha: float) -> float:
    """Split-conformal lower threshold on confidence for answerable examples.

    Returns τ such that, under exchangeability, P(score < τ | answerable) ≤ alpha
    — i.e. at most ``alpha`` of truly-answerable questions are wrongly abstained.

    Uses the standard finite-sample rank ⌊alpha·(n+1)⌋ on the sorted scores.
    ``alpha<=0`` (or too-small n) ⇒ -inf (never abstain on confidence grounds).
    """
    if not 0.0 < alpha < 1.0:
        return -math.inf
    n = len(answerable_scores)
    rank = math.floor(alpha * (n + 1))
    if rank <= 0:
        return -math.inf
    if rank > n:
        rank = n
    return sorted(answerable_scores)[rank - 1]


def calibrate(calibration: list[CalibrationExample], alpha: float) -> float:
    """Compute the abstention threshold from labeled calibration examples."""
    answerable = [c.score for c in calibration if c.answerable]
    return conformal_threshold(answerable, alpha)


def should_answer(score: float, threshold: float) -> bool:
    """Answer iff confidence meets the calibrated threshold; else abstain/flag."""
    return score >= threshold


def calibrate_from_labeled(labeled: list[tuple[list[Claim], bool]], alpha: float) -> float:
    """Compute the abstention threshold from labeled sub-questions.

    ``labeled`` = [(claims_for_subquestion, answerable_label), ...]. The confidence
    score is each sub-question's SUPPORTED-claim count. Returns the conformal
    threshold τ (answer iff score ≥ τ) guaranteeing ≤ ``alpha`` false-abstention on
    truly-answerable sub-questions, under exchangeability.
    """
    examples = [CalibrationExample(score=confidence_score(cs), answerable=ans)
                for cs, ans in labeled]
    return calibrate(examples, alpha)
