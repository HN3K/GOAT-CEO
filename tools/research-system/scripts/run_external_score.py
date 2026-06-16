"""Score the saved stock deep-research report (arm A) against the corpus.

Usage:
  python scripts/run_external_score.py SUBJECT_SLUG [--report FILE] [--k 3] [--judges 3]

Defaults to Research/<subject>/deep-research-raw.json. Subscription-billed
(judges each finding against the corpus). Writes external_arm_report.md.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from research_system.external import load_findings, score_external_report
from research_system.llm import MID, STRONG, ClaudeCLIClient
from research_system.paths import SubjectLayout
from research_system.retrieve import Corpus

REPO = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject")
    ap.add_argument("--research-root", default=str(REPO / "Research"))
    ap.add_argument("--report", default=None)
    ap.add_argument("--k", type=int, default=3)
    ap.add_argument("--judges", type=int, default=3)
    args = ap.parse_args()

    layout = SubjectLayout(args.research_root, args.subject)
    report = Path(args.report) if args.report else (layout.root / "deep-research-raw.json")
    findings = load_findings(report)
    corpus = Corpus.load(layout)
    judges = tuple((MID if i % 2 == 0 else STRONG) for i in range(max(1, args.judges)))

    print(f"Scoring {len(findings)} deep-research findings against {len(corpus)} corpus docs "
          f"(judges={len(judges)})")
    s = score_external_report(findings, corpus, ClaudeCLIClient(), k=args.k, judges=judges)

    md = (
        f"# External arm A (deep-research) scored against corpus\n\n"
        f"| metric | A (deep-research) |\n|--------|------------------:|\n"
        f"| findings presented | {s.presented} |\n"
        f"| faithful (corpus-judged) | {s.faithful} |\n"
        f"| faithfulness | {s.faithfulness:.1%} |\n"
        f"| **auditability (verbatim trace)** | {s.auditability:.1%} |\n\n"
        f"Auditability is ~0 by construction: deep-research cites external URLs, not verbatim spans in\n"
        f"the stored corpus. Compare to arm B (100% auditable). Faithfulness is a judged "
        f"'does our corpus support this finding?' measure.\n"
    )
    out = layout.root / "external_arm_report.md"
    out.write_text(md, encoding="utf-8")
    print("\n" + md)
    print(f"report -> {out}")


if __name__ == "__main__":
    main()
