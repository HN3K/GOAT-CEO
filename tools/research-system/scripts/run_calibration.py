"""Calibrate the conformal abstention threshold from labeled questions.

Runs the grounded pipeline over labeled questions (the benchmark fixture: each
question's `answerable` flag labels its sub-questions), records each sub-question's
SUPPORTED-claim count, and computes the conformal threshold τ such that answering
iff score ≥ τ wrongly abstains on ≤ alpha of truly-answerable sub-questions.

Usage:
  python scripts/run_calibration.py SUBJECT_SLUG [--alpha 0.1] [--k 3] [--n 4] [--judges 3]

Writes Research/<subject>/calibration.json. Use the result with:
  python scripts/run_research.py SUBJECT "Q" --gate-threshold <τ>

NOTE: live + subscription-billed (one grounded run per question). The benchmark
fixture is small — treat τ as illustrative; a larger labeled set gives a tighter,
more trustworthy bound. With too few examples conformal returns -inf (answer all),
in which case keep the heuristic min_support gate.
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from research_system.answer import answer_subquestion
from research_system.conformal import calibrate_from_labeled
from research_system.contracts import Claim
from research_system.decompose import decompose
from research_system.llm import MID, STRONG, ClaudeCLIClient
from research_system.orchestrate import OrchestratorConfig
from research_system.paths import SubjectLayout
from research_system.retrieve import BM25Retriever, Corpus
from research_system.verify import verify_claim

REPO = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject")
    ap.add_argument("--research-root", default=str(REPO / "Research"))
    ap.add_argument("--questions", default=None)
    ap.add_argument("--alpha", type=float, default=0.1)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--n", type=int, default=4)
    ap.add_argument("--judges", type=int, default=3)
    args = ap.parse_args()

    layout = SubjectLayout(args.research_root, args.subject)
    qfile = Path(args.questions) if args.questions else (layout.root / "benchmark_questions.json")
    raw = json.loads(qfile.read_text(encoding="utf-8"))["questions"]

    corpus = Corpus.load(layout)
    retriever = BM25Retriever(corpus)
    llm = ClaudeCLIClient()
    judges = tuple((MID if i % 2 == 0 else STRONG) for i in range(max(1, args.judges)))
    cfg = OrchestratorConfig(k=args.k, n_subquestions=args.n, judges=judges)

    labeled: list[tuple[list[Claim], bool]] = []
    for item in raw:
        spec = {"q": item, "answerable": True} if isinstance(item, str) else item
        q, answerable = spec["q"], spec.get("answerable", True)
        print(f"  {'ANS' if answerable else 'NEG'} | {q[:60]}")
        questions = decompose(q, llm, model=cfg.decompose_model, n=cfg.n_subquestions)
        for sq in questions.subquestions:
            cs = answer_subquestion(sq, retriever, corpus, llm, k=cfg.k, model=cfg.answer_model)
            for c in cs:
                verify_claim(c, corpus, llm, judges=judges)
            labeled.append((cs, answerable))

    tau = calibrate_from_labeled(labeled, args.alpha)
    n_ans = sum(1 for _, a in labeled if a)
    out = {
        "alpha": args.alpha,
        "threshold": (None if tau == -math.inf else tau),
        "threshold_raw": ("-inf" if tau == -math.inf else tau),
        "n_subquestions": len(labeled),
        "n_answerable": n_ans,
        "note": "answer iff supported-claim count >= threshold; -inf/null means answer all "
                "(too few calibration examples) -> keep heuristic min_support.",
    }
    (layout.root / "calibration.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(f"\nthreshold τ = {out['threshold_raw']}  (alpha={args.alpha}, "
          f"{n_ans}/{len(labeled)} answerable sub-questions)")
    print(f"-> {layout.root / 'calibration.json'}")
    if tau != -math.inf:
        print(f"use: python scripts/run_research.py {args.subject} \"<Q>\" --gate-threshold {tau}")


if __name__ == "__main__":
    main()
