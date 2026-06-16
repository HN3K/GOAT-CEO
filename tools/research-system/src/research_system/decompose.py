"""Phase 5 — Question decomposition (DESIGN §3 component 1).

Split the research question into atomic, independently-answerable sub-questions,
each with an explicit success criterion. Answered later in SEPARATE contexts
(faithfulness over chain-of-thought [F-2307.11768]).
"""

from __future__ import annotations

import json
import re

from research_system.contracts import QuestionsFile, SubQuestion
from research_system.llm import STRONG, LLMClient

DECOMPOSE_SYSTEM = (
    "You break a research question into atomic, independently-answerable sub-questions. "
    "Each sub-question targets ONE fact or relationship and has a concrete success "
    "criterion describing what a satisfactory answer must contain."
)

_INSTRUCTIONS = """\
Decompose the QUESTION into {n} or fewer atomic sub-questions.

Return ONLY a JSON object:
{{"subquestions": [{{"text": "<sub-question>", "success_criteria": "<what a good answer must contain>"}}]}}

Rules:
- Each sub-question must be answerable on its own from source documents.
- Cover distinct facets; do not overlap.
- Output the JSON object and nothing else."""


def build_decompose_prompt(question: str, n: int) -> str:
    return f"QUESTION:\n{question}\n\n{_INSTRUCTIONS.format(n=n)}"


_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def parse_subquestions(raw: str, max_n: int) -> list[SubQuestion]:
    m = _JSON_OBJ.search(raw or "")
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out: list[SubQuestion] = []
    for i, item in enumerate(data.get("subquestions", [])[:max_n], start=1):
        if not isinstance(item, dict):
            continue
        text = (item.get("text") or "").strip()
        if not text:
            continue
        out.append(SubQuestion(
            id=f"q{i}",
            text=text,
            success_criteria=(item.get("success_criteria") or "").strip(),
        ))
    return out


def decompose(question: str, llm: LLMClient, *, model: str = STRONG, n: int = 6) -> QuestionsFile:
    resp = llm.generate(system=DECOMPOSE_SYSTEM, prompt=build_decompose_prompt(question, n), model=model)
    return QuestionsFile(question=question, subquestions=parse_subquestions(resp.text, n))
