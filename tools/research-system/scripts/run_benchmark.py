"""Run the B-vs-A' benchmark over a captured corpus (subscription-billed).

Usage:
  python scripts/run_benchmark.py SUBJECT_SLUG [--questions FILE] [--k INT] [--judges INT]

Reads a questions file (default Research/<subject>/benchmark_questions.json):
  {"subject": "...", "questions": [
     {"q": "...", "answerable": true, "must_include": ["phrase", ...]},
     {"q": "...", "answerable": false}                       # out-of-corpus gap-honesty probe
  ]}
(Plain strings are also accepted and treated as answerable with no checklist.)

Writes a comparison report to Research/<subject>/benchmark_report.md.
NOTE: this runs the live pipeline many times — it spends subscription credit.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_system.benchmark import compare_arms, format_comparison
from research_system.llm import MID, STRONG, ClaudeCLIClient
from research_system.orchestrate import OrchestratorConfig
from research_system.paths import SubjectLayout
from research_system.retrieve import Corpus

REPO = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject")
    ap.add_argument("--research-root", default=str(REPO / "Research"))
    ap.add_argument("--questions", default=None)
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--n", type=int, default=6, help="max sub-questions per question")
    ap.add_argument("--judges", type=int, default=3)
    args = ap.parse_args()

    layout = SubjectLayout(args.research_root, args.subject)
    qfile = Path(args.questions) if args.questions else (layout.root / "benchmark_questions.json")
    raw_questions = json.loads(qfile.read_text(encoding="utf-8"))["questions"]

    corpus = Corpus.load(layout)
    make_client = ClaudeCLIClient  # 0-arg factory: fresh client (+ cost meter) per arm
    judges = tuple((MID if i % 2 == 0 else STRONG) for i in range(max(1, args.judges)))
    config = OrchestratorConfig(k=args.k, n_subquestions=args.n, judges=judges)

    print(f"Benchmarking {len(raw_questions)} question(s) over {layout.root} "
          f"({len(corpus)} docs, judges={len(judges)})")
    out = layout.root / "benchmark_report.md"
    comps = []
    for i, item in enumerate(raw_questions, 1):
        spec = {"q": item} if isinstance(item, str) else item
        q = spec["q"]
        print(f"  [{i}/{len(raw_questions)}] {q[:66]}")
        comps.append(compare_arms(
            q, corpus, make_client, config=config, score_judges=judges,
            must_include=spec.get("must_include"),
            answerable=spec.get("answerable", True),
        ))
        # incremental write: a crash mid-run still preserves completed questions
        out.write_text(format_comparison(comps), encoding="utf-8")

    print("\n" + format_comparison(comps))
    print(f"report -> {out}")


if __name__ == "__main__":
    main()
