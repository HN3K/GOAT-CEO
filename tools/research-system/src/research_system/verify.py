"""Phase 3 — Per-claim adversarial verification (DESIGN §3 component 6).

Three stages, cheapest first:
  6a  mechanical  — is the quote present verbatim in the stored source? If not,
                    the claim is UNSUPPORTED with zero model cost (fabrication kill).
  6b  grounded    — an adversarial judge, given the claim + quote + surrounding
                    source context, decides supported / overreach / unsupported.
                    Defaults to 'unsupported' under uncertainty.
  6c  ensemble    — several judges (a DIFFERENT model than generation) vote; only a
                    strict majority of 'supported' passes. Cancels single-judge
                    over-rejection (16–17% recall) and self-preference bias [P6].

Verification is grounded in the STORED source text, never the judge's parametric
knowledge — the literature's key caveat about naive LLM-as-judge.
"""

from __future__ import annotations

import json
import re
from collections import Counter

from research_system.contracts import Claim, JudgeVote, Verdict
from research_system.grounding import normalize_ws, quote_present
from research_system.llm import MID, STRONG, LLMClient
from research_system.retrieve import Corpus

# Default ensemble: a different/stronger tier than the cheap answerer, 3 votes.
DEFAULT_JUDGES: tuple[str, ...] = (MID, STRONG, MID)

VERIFY_SYSTEM = (
    "You are a strict, adversarial fact-checker. You are given a CLAIM, a QUOTE that "
    "was supposedly copied from a source, and the surrounding SOURCE CONTEXT. Decide "
    "whether the source genuinely supports the claim. Be skeptical: if you are unsure, "
    "answer 'unsupported'. Use ONLY the provided context, never outside knowledge."
)

_VERIFY_INSTRUCTIONS = """\
Decide one verdict for the CLAIM with respect to the SOURCE CONTEXT:
- "supported"   : the context clearly and fully establishes the claim.
- "overreach"   : the quote/context is real and related, but the claim asserts MORE
                  than the context establishes (extrapolation, stronger wording, added scope).
- "unsupported" : the context does not establish the claim, or contradicts it.

Return ONLY a JSON object: {"verdict": "supported|overreach|unsupported", "rationale": "<one sentence>"}
When uncertain, prefer "unsupported". Output the JSON object and nothing else."""


def context_window(source_text: str, quote: str, radius: int = 1500) -> str:
    """A focused excerpt of ``source_text`` around ``quote`` (±``radius`` chars).

    Tries exact then case-insensitive location; if the quote only matches after
    whitespace-normalization, falls back to a head excerpt plus the quote so the
    judge still sees the verbatim span.
    """
    idx = source_text.find(quote)
    if idx == -1:
        idx = source_text.lower().find(quote.lower())
    if idx == -1:
        head = source_text[: 2 * radius]
        return f"{head}\n\n[...quote located after whitespace normalization...]\n{quote}"
    start = max(0, idx - radius)
    end = min(len(source_text), idx + len(quote) + radius)
    return source_text[start:end]


def build_verify_prompt(claim_text: str, quote: str, source_context: str) -> str:
    return (
        f"CLAIM:\n{claim_text}\n\n"
        f"QUOTE (verbatim from source):\n{quote}\n\n"
        f"SOURCE CONTEXT:\n{source_context}\n\n"
        f"{_VERIFY_INSTRUCTIONS}"
    )


_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)
_VERDICTS = {v.value: v for v in Verdict}


def parse_verdict(raw: str) -> tuple[Verdict, str | None]:
    """Parse a judge response → (verdict, rationale). Conservative on failure."""
    m = _JSON_OBJ.search(raw or "")
    if m:
        try:
            data = json.loads(m.group(0))
            v = _VERDICTS.get(str(data.get("verdict", "")).strip().lower())
            if v is not None and v is not Verdict.PENDING:
                return v, (data.get("rationale") or None)
        except json.JSONDecodeError:
            pass
    return Verdict.UNSUPPORTED, "unparseable judge response (defaulted conservative)"


def aggregate_votes(votes: list[JudgeVote]) -> Verdict:
    """Strict-majority 'supported' to pass; otherwise the more skeptical verdict.

    Adversarial bias: a tie never yields 'supported'. Between the negatives,
    'unsupported' wins ties over 'overreach' (more conservative).
    """
    if not votes:
        return Verdict.UNSUPPORTED
    counts = Counter(v.verdict for v in votes)
    n = len(votes)
    if counts[Verdict.SUPPORTED] * 2 > n:
        return Verdict.SUPPORTED
    if counts[Verdict.UNSUPPORTED] >= counts[Verdict.OVERREACH]:
        return Verdict.UNSUPPORTED
    return Verdict.OVERREACH


def verify_claim(
    claim: Claim,
    corpus: Corpus,
    llm: LLMClient,
    *,
    judges: tuple[str, ...] = DEFAULT_JUDGES,
    radius: int = 1500,
) -> Claim:
    """Run 6a→6b→6c on one claim, populating ``quote_present``, ``judge_votes``,
    and ``verdict`` in place; returns the same claim for convenience."""
    source = corpus.get(claim.source_id) if claim.source_id in corpus else ""
    present = quote_present(claim.quote, source)
    claim.quote_present = present

    # 6a — mechanical fabrication kill (no model cost)
    if not present:
        claim.verdict = Verdict.UNSUPPORTED
        claim.judge_votes = [
            JudgeVote(model="mechanical", verdict=Verdict.UNSUPPORTED,
                      rationale="quote not found verbatim in stored source")
        ]
        return claim

    # 6b/6c — adversarial ensemble grounded in the stored source
    ctx = context_window(source, claim.quote, radius)
    prompt = build_verify_prompt(claim.text, claim.quote, ctx)
    votes: list[JudgeVote] = []
    for model in judges:
        resp = llm.generate(system=VERIFY_SYSTEM, prompt=prompt, model=model)
        verdict, rationale = parse_verdict(resp.text)
        votes.append(JudgeVote(model=model, verdict=verdict, rationale=rationale))
    claim.judge_votes = votes
    claim.verdict = aggregate_votes(votes)
    return claim


def verify_claims(
    claims: list[Claim],
    corpus: Corpus,
    llm: LLMClient,
    *,
    judges: tuple[str, ...] = DEFAULT_JUDGES,
    radius: int = 1500,
) -> list[Claim]:
    return [verify_claim(c, corpus, llm, judges=judges, radius=radius) for c in claims]
