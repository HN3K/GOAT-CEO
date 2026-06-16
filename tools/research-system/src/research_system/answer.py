"""Answer one sub-question from the corpus, in isolation (DESIGN §3 component 5).

Each sub-question is answered in a SEPARATE LLM context (faithfulness over CoT,
[F-2307.11768]) using only its retrieved top-k full documents. The model must
return atomic claims, each carrying an EXACT quoted span and the source id it
came from. Output is parsed and validated defensively — unknown source ids and
empty fields are dropped rather than trusted.
"""

from __future__ import annotations

import json
import re
from typing import Callable

from research_system.contracts import Claim, SubQuestion, Verdict
from research_system.grounding import quote_present
from research_system.llm import CHEAP, LLMClient
from research_system.retrieve import Corpus, Retriever

ANSWER_SYSTEM = (
    "You are a meticulous research extractor. You answer ONLY using the SOURCES "
    "provided in the prompt. Never use outside knowledge. For every claim you make, "
    "copy an EXACT verbatim span from the source that supports it. If the sources do "
    "not answer the question, return an empty claims list. Do not speculate."
)

_ANSWER_INSTRUCTIONS = """\
Answer the QUESTION using only the SOURCES above.

Return ONLY a JSON object with this exact shape:
{
  "answerable": true | false,
  "claims": [
    {"text": "<one atomic factual claim>",
     "source_id": "<the source id the quote is from>",
     "quote": "<EXACT verbatim span copied from that source that supports the claim>"}
  ]
}

Rules:
- Every quote MUST be copied verbatim (character-for-character) from the cited source.
- Use only source ids that appear in the SOURCES section.
- One claim = one fact. Prefer several precise claims over one broad claim.
- If the sources do not answer the question, return {"answerable": false, "claims": []}.
- Output the JSON object and nothing else."""


def build_answer_prompt(question: str, docs: list[tuple[str, str]]) -> str:
    """docs = [(source_id, full_text), ...]."""
    blocks = [f"=== SOURCE {sid} ===\n{text}" for sid, text in docs]
    return (
        "SOURCES:\n\n"
        + "\n\n".join(blocks)
        + f"\n\n=== QUESTION ===\n{question}\n\n"
        + _ANSWER_INSTRUCTIONS
    )


_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def parse_claims(raw: str, subq_id: str, allowed_ids: set[str]) -> list[Claim]:
    """Parse the model's JSON into validated Claim objects.

    Defensive: tolerates surrounding prose, drops claims with unknown source ids
    or empty text/quote. Returns [] on unparseable output (treated as no answer).
    """
    m = _JSON_OBJ.search(raw or "")
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []

    claims: list[Claim] = []
    for i, item in enumerate(data.get("claims", []) or []):
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        source_id = (item.get("source_id") or "").strip()
        quote = (item.get("quote") or "").strip()
        if not text or not quote or source_id not in allowed_ids:
            continue
        claims.append(
            Claim(
                id=f"{subq_id}-c{i}",
                subq_id=subq_id,
                text=text,
                source_id=source_id,
                quote=quote,
                verdict=Verdict.PENDING,
            )
        )
    return claims


def answer_subquestion(
    subq: SubQuestion,
    retriever: Retriever,
    corpus: Corpus,
    llm: LLMClient,
    *,
    k: int = 5,
    model: str = CHEAP,
    mark_quote_presence: bool = True,
) -> list[Claim]:
    """Retrieve top-k docs, ask the model, return validated claims.

    With ``mark_quote_presence`` (default), each claim's ``quote_present`` is set
    by the mechanical check against the cited source — a cheap self-check; the
    authoritative verdict still comes from the Verify stage (P3).
    """
    hits = retriever.top_k(subq.text, k)
    docs = [(h.source_id, corpus.get(h.source_id)) for h in hits if h.source_id in corpus]
    if not docs:
        return []

    prompt = build_answer_prompt(subq.text, docs)
    resp = llm.generate(system=ANSWER_SYSTEM, prompt=prompt, model=model)
    claims = parse_claims(resp.text, subq.id, allowed_ids={sid for sid, _ in docs})

    if mark_quote_presence:
        for c in claims:
            c.quote_present = quote_present(c.quote, corpus.get(c.source_id))
    return claims
