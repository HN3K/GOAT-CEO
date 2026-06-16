"""Adversarial verification of advisory findings (DESIGN P3 + the Research System's verifier).

LLM review findings are *advisory* and, left alone, carry the LLM's false-positive rate
(the corpus: a self-critiquing model degrades without external feedback [s006]; LLM-alone
review hit 88% FP on IDORs [s040]). This stage filters them the way the Research System
verifies claims — cheapest check first:

  1. mechanical   — if the finding cites an offending code span (``quote``), is that span
                    actually present in the file? A fabricated/paraphrased span is killed
                    with zero model cost (the hallucination floor).
  2. adversarial  — N independent judges (a DIFFERENT/stronger tier than the reviewer) each
     ensemble       try to REFUTE the finding, grounded ONLY in the code. A strict majority
                    must affirm it is REAL or the finding is dropped; ties go to the skeptic.

Survivors are annotated with ``confidence`` (fraction of judges affirming). This inserts a
Verify stage into the pipeline: Retrieve → Gate → Review → **Verify** → Verdict.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass

from rubric.contracts import Finding
from rubric.llm import MID, STRONG, LLMClient

# A different/stronger tier than the cheap reviewer, 3 votes — cancels single-judge
# over-rejection and self-preference bias (Research System DEFAULT_JUDGES).
DEFAULT_JUDGES: tuple[str, ...] = (MID, STRONG, MID)

VERIFY_SYSTEM = (
    "You are a strict, adversarial code-review fact-checker. You are given a SOURCE FILE and a "
    "single advisory finding another reviewer raised about it. Decide whether the finding is "
    "genuinely REAL and actionable in THIS code as written — or a false positive: speculative, "
    "already handled, based on code you cannot see, or simply not supported by the file. Be "
    "skeptical: if you cannot concretely confirm the issue from the provided code, answer "
    "'refuted'. Use ONLY the provided code, never assumptions about unseen code."
)

_VERIFY_INSTRUCTIONS = """\
Decide one verdict for the FINDING with respect to the SOURCE FILE:
- "real"    : the code as written concretely exhibits the issue the finding describes.
- "refuted" : the issue is not present, is speculative, is already handled, or depends on
              code not shown. When in doubt, choose this.

Return ONLY a JSON object: {"verdict": "real|refuted", "rationale": "<one sentence>"}
Output the JSON object and nothing else."""

_WS = re.compile(r"\s+")
_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def _normalize_ws(text: str) -> str:
    return _WS.sub(" ", text).strip()


def quote_present(quote: str, code: str) -> bool:
    """True if ``quote`` appears in ``code`` ignoring only whitespace (markdown/PDF reflow)."""
    q = _normalize_ws(quote)
    return bool(q) and q in _normalize_ws(code)


def build_verify_prompt(code: str, finding: Finding, path: str = "") -> str:
    span = f"\nCITED CODE SPAN:\n{finding.quote}\n" if finding.quote else ""
    loc = f" (line {finding.line})" if finding.line else ""
    return (
        f"SOURCE FILE{(' ' + path) if path else ''}:\n```\n{code}\n```\n\n"
        f"FINDING{loc}:\n{finding.message}\n{span}\n"
        f"{_VERIFY_INSTRUCTIONS}"
    )


@dataclass
class JudgeVote:
    model: str
    real: bool
    rationale: str | None = None


def parse_vote(raw: str) -> tuple[bool, str | None]:
    """Parse a judge response → (is_real, rationale). Conservative (refuted) on failure."""
    m = _JSON_OBJ.search(raw or "")
    if m:
        try:
            data = json.loads(m.group(0))
            verdict = str(data.get("verdict", "")).strip().lower()
            if verdict in ("real", "refuted"):
                return verdict == "real", (data.get("rationale") or None)
        except json.JSONDecodeError:
            pass
    return False, "unparseable judge response (defaulted to refuted)"


def confidence_of(votes: list[JudgeVote]) -> float:
    return (sum(1 for v in votes if v.real) / len(votes)) if votes else 0.0


def survives(votes: list[JudgeVote]) -> bool:
    """Strict majority of judges must affirm REAL; a tie is refuted (adversarial bias)."""
    if not votes:
        return False
    return Counter(v.real for v in votes)[True] * 2 > len(votes)


def verify_finding(
    finding: Finding,
    code: str,
    llm: LLMClient,
    *,
    judges: tuple[str, ...] = DEFAULT_JUDGES,
) -> tuple[bool, list[JudgeVote]]:
    """Run mechanical → adversarial-ensemble verification on one finding.

    Returns ``(kept, votes)``. ``kept`` is False if the cited span is fabricated or the
    ensemble fails to reach a strict-majority 'real'.
    """
    # 1 — mechanical fabrication kill (free): a cited span that isn't in the file is invented.
    if finding.quote and not quote_present(finding.quote, code):
        return False, [JudgeVote(model="mechanical", real=False,
                                 rationale="cited code span not present in file")]

    # 2 — adversarial ensemble, grounded only in the code.
    prompt = build_verify_prompt(code, finding, finding.path or "")
    votes: list[JudgeVote] = []
    for model in judges:
        resp = llm.generate(system=VERIFY_SYSTEM, prompt=prompt, model=model)
        real, rationale = parse_vote(resp.text)
        votes.append(JudgeVote(model=model, real=real, rationale=rationale))
    return survives(votes), votes


def verify_findings(
    findings: list[Finding],
    code: str,
    llm: LLMClient,
    *,
    judges: tuple[str, ...] = DEFAULT_JUDGES,
) -> list[Finding]:
    """Filter advisory findings through adversarial verification.

    Returns only the survivors, each annotated with ``confidence`` (fraction of judges
    affirming). Findings whose cited span is fabricated, or that the ensemble refutes, are
    dropped — the auditable false-positive guard before findings reach the Verdict.
    """
    kept: list[Finding] = []
    for f in findings:
        survived, votes = verify_finding(f, code, llm, judges=judges)
        if survived:
            kept.append(f.model_copy(update={"confidence": confidence_of(votes)}))
    return kept
