"""Score an EXTERNAL research report (e.g. the stock deep-research skill) as
benchmark arm A, against our captured corpus (DESIGN §7).

A deep-research report is synthesized prose whose findings cite external URLs —
it carries no verbatim spans into our stored files. So:
- **auditability ≈ 0** by construction (no quote traces to a stored source) — the
  headline differentiator vs arm B's 100%.
- **faithfulness** is judged: each finding's claim is checked against the most
  relevant corpus documents by the same adversarial ensemble (grounding judge,
  no pre-supplied quote). Since deep-research cited many of the same papers we
  captured, this is a fair "does our corpus support this finding?" measure.
"""

from __future__ import annotations

import json
from pathlib import Path

from research_system.benchmark import ArmScore
from research_system.contracts import JudgeVote, Verdict
from research_system.grounding import quote_present
from research_system.llm import LLMClient
from research_system.retrieve import BM25Retriever, Corpus
from research_system.verify import (
    DEFAULT_JUDGES,
    VERIFY_SYSTEM,
    aggregate_votes,
    build_verify_prompt,
    parse_verdict,
)


def load_findings(report_path: str | Path) -> list[dict]:
    """Load deep-research findings from its saved JSON (handles {result:{findings}})."""
    data = json.loads(Path(report_path).read_text(encoding="utf-8"))
    res = data.get("result", data)
    return res.get("findings", []) or []


def judge_corpus_support(
    claim_text: str,
    corpus: Corpus,
    retriever: BM25Retriever,
    llm: LLMClient,
    *,
    k: int = 3,
    judges: tuple[str, ...] = DEFAULT_JUDGES,
    max_ctx: int = 6000,
) -> Verdict:
    """Ensemble judgment of whether the corpus supports a (quote-less) claim."""
    hits = retriever.top_k(claim_text, k)
    ctx = "\n\n".join(corpus.get(h.source_id) for h in hits)[:max_ctx]
    if not ctx:
        return Verdict.UNSUPPORTED
    prompt = build_verify_prompt(claim_text, "(no verbatim quote supplied — judge against context)", ctx)
    votes = []
    for m in judges:
        verdict, _ = parse_verdict(llm.generate(system=VERIFY_SYSTEM, prompt=prompt, model=m).text)
        votes.append(JudgeVote(model=m, verdict=verdict))
    return aggregate_votes(votes)


def score_external_report(
    findings: list[dict],
    corpus: Corpus,
    llm: LLMClient,
    *,
    k: int = 3,
    judges: tuple[str, ...] = DEFAULT_JUDGES,
    name: str = "A (deep-research)",
) -> ArmScore:
    """Score external findings as a benchmark arm: judged faithfulness, ~0 auditability."""
    retriever = BM25Retriever(corpus)
    n = len(findings)
    faithful = 0
    auditable = 0
    for f in findings:
        claim = (f.get("claim") or "").strip()
        if claim and judge_corpus_support(claim, corpus, retriever, llm, k=k, judges=judges) is Verdict.SUPPORTED:
            faithful += 1
        # auditability: does the finding hand us a span that is verbatim in a STORED source?
        evidence = (f.get("evidence") or "").strip()
        if evidence and any(quote_present(evidence[:120], corpus.get(sid)) for sid in corpus.ids):
            auditable += 1
    return ArmScore(
        name=name,
        presented=n,
        faithful=faithful,
        unfaithful=n - faithful,
        auditability=(auditable / n if n else 0.0),
        cost_usd=0.0,
    )
