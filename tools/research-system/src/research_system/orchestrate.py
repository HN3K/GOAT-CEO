"""Phase 5 — End-to-end orchestrator (DESIGN §3).

Wires decompose → (retrieve + answer per sub-question, separate context) → verify
→ gate → gaps → synthesize, over an already-captured corpus. Every stage persists
its artifact, so a killed run resumes from disk without redoing completed work.

Discovery of NEW web sources is out of scope here (the corpus is captured by
Phase 1); the gap-loop ``resolver`` hook is left open for that wiring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from research_system.answer import answer_subquestion
from research_system.contracts import (
    Claim,
    QuestionsFile,
    Verdict,
    read_claims,
    read_model,
    write_claims,
    write_model,
)
from research_system.decompose import decompose
from research_system.gate import apply_gate, run_gap_loop, write_gaps
from research_system.llm import MID, STRONG, LLMClient
from research_system.synthesize import render_synthesis
from research_system.verify import DEFAULT_JUDGES, verify_claims
from research_system.paths import SubjectLayout
from research_system.retrieve import BM25Retriever, Corpus


@dataclass
class OrchestratorConfig:
    n_subquestions: int = 6
    k: int = 5
    decompose_model: str = STRONG
    # mid (Sonnet) default per the tier sweep: ~4x coverage vs cheap at high
    # faithfulness and ~half Opus's cost (see reviews/BENCHMARK-RESULTS.md).
    answer_model: str = MID
    judges: tuple[str, ...] = DEFAULT_JUDGES
    min_support: int = 2
    # calibrated conformal threshold; when set, overrides min_support at the gate.
    gate_threshold: float | None = None


@dataclass
class ResearchResult:
    questions: QuestionsFile
    claims: list[Claim] = field(default_factory=list)
    synthesis_path: Path | None = None
    n_supported: int = 0


def run_research(
    layout: SubjectLayout,
    question: str,
    llm: LLMClient,
    *,
    corpus: Corpus | None = None,
    config: OrchestratorConfig | None = None,
    resume: bool = True,
    searcher=None,
    max_gap_iters: int = 0,
) -> ResearchResult:
    config = config or OrchestratorConfig()
    layout.ensure()

    # 1. Decompose (checkpoint: questions.json) ------------------------------
    if resume and layout.questions_path.exists():
        questions = read_model(QuestionsFile, layout.questions_path)
    else:
        questions = decompose(question, llm, model=config.decompose_model, n=config.n_subquestions)
        write_model(questions, layout.questions_path)

    # 2. Corpus + retriever --------------------------------------------------
    corpus = corpus if corpus is not None else Corpus.load(layout)
    retriever = BM25Retriever(corpus)

    # 3-4. Answer + Verify (checkpoint: claims.jsonl) ------------------------
    if resume and layout.claims_path.exists():
        claims = read_claims(layout.claims_path)
    else:
        claims = []
        for sq in questions.subquestions:
            cs = answer_subquestion(sq, retriever, corpus, llm, k=config.k, model=config.answer_model)
            verify_claims(cs, corpus, llm, judges=config.judges)
            claims.extend(cs)
        write_claims(layout.claims_path, claims)

    # 5. Gate + gaps (persist statuses back to questions.json) ---------------
    if searcher is not None and max_gap_iters > 0:
        # discovery loop: unanswered sub-questions → search → capture → re-answer
        from research_system.discover import make_discovery_resolver

        resolver = make_discovery_resolver(
            layout, corpus, llm, searcher,
            k=config.k, answer_model=config.answer_model, judges=config.judges)
        run_gap_loop(questions, claims, resolver,
                     max_iters=max_gap_iters, min_support=config.min_support)
        write_claims(layout.claims_path, claims)  # persist discovered claims
    else:
        apply_gate(questions, claims, min_support=config.min_support, threshold=config.gate_threshold)
    write_model(questions, layout.questions_path)
    write_gaps(layout, questions, claims, min_support=config.min_support)

    # 6. Synthesize (deterministic, traceable) -------------------------------
    layout.synthesis_path.write_text(
        render_synthesis(question, questions, claims), encoding="utf-8"
    )

    return ResearchResult(
        questions=questions,
        claims=claims,
        synthesis_path=layout.synthesis_path,
        n_supported=sum(1 for c in claims if c.verdict is Verdict.SUPPORTED),
    )
