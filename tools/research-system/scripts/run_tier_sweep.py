"""Model-tier sweep: vary the EXTRACTION model, hold verification constant.

Tests the open-book cost thesis + the benchmark's coverage finding: does a stronger
answer model raise B's coverage while faithfulness stays ~100%, and is it worth the cost?

Usage:
  python scripts/run_tier_sweep.py SUBJECT_SLUG [--questions FILE] [--limit N]
      [--tiers cheap,mid,strong] [--k INT] [--n INT] [--judges INT]

Reads the same questions file as the benchmark (answerable items used). Writes
Research/<subject>/tier_sweep_report.md. Subscription-billed (runs arm B once per tier).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from research_system.llm import CHEAP, MID, STRONG, ClaudeCLIClient
from research_system.orchestrate import OrchestratorConfig
from research_system.paths import SubjectLayout
from research_system.retrieve import Corpus
from research_system.tier_sweep import aggregate_tier_outcomes, format_tier_table, run_tier_sweep

REPO = Path(__file__).resolve().parent.parent
_TIERS = {"cheap": CHEAP, "mid": MID, "strong": STRONG}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject")
    ap.add_argument("--research-root", default=str(REPO / "Research"))
    ap.add_argument("--questions", default=None)
    ap.add_argument("--limit", type=int, default=2, help="number of answerable questions to use")
    ap.add_argument("--tiers", default="cheap,mid,strong")
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--judges", type=int, default=3)
    args = ap.parse_args()

    layout = SubjectLayout(args.research_root, args.subject)
    qfile = Path(args.questions) if args.questions else (layout.root / "benchmark_questions.json")
    raw = json.loads(qfile.read_text(encoding="utf-8"))["questions"]
    # answerable items only, up to --limit
    specs = []
    for item in raw:
        spec = {"q": item, "answerable": True} if isinstance(item, str) else item
        if spec.get("answerable", True):
            specs.append(spec)
        if len(specs) >= args.limit:
            break

    tiers = tuple(_TIERS[t.strip()] for t in args.tiers.split(","))
    judges = tuple((MID if i % 2 == 0 else STRONG) for i in range(max(1, args.judges)))
    base = OrchestratorConfig(k=args.k, n_subquestions=args.n, judges=judges)

    corpus = Corpus.load(layout)
    print(f"Tier sweep over {len(specs)} question(s), tiers={tiers}, "
          f"k={args.k}, n={args.n}, judges={len(judges)} ({len(corpus)} docs)")

    per_question = []
    for i, spec in enumerate(specs, 1):
        print(f"  [{i}/{len(specs)}] {spec['q'][:60]}")
        outcomes = run_tier_sweep(spec["q"], corpus, ClaudeCLIClient,
                                  tiers=tiers, base_config=base, score_judges=judges,
                                  must_include=spec.get("must_include"))
        per_question.append(outcomes)

    agg = aggregate_tier_outcomes(per_question, tiers)
    report = format_tier_table(agg)
    out = layout.root / "tier_sweep_report.md"
    out.write_text(report, encoding="utf-8")
    print("\n" + report)
    print(f"report -> {out}")


if __name__ == "__main__":
    main()
