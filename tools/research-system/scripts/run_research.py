"""Run the research pipeline over a captured corpus (subscription-billed).

Usage:
  python scripts/run_research.py SUBJECT_SLUG "RESEARCH QUESTION" [options]

Options:
  --research-root DIR     default ./Research
  --k INT                 docs retrieved per sub-question (default 5)
  --n INT                 max sub-questions (default 6)
  --answer-model TIER     cheap|mid|strong (default cheap)
  --decompose-model TIER  cheap|mid|strong (default strong)
  --judges INT            ensemble size for verification (default 3, uses mid/strong)
  --min-support INT       supported claims needed for "answered" (default 2)
  --no-resume             ignore on-disk checkpoints and recompute

Billing: uses the Claude Code subscription via `claude -p` (ANTHROPIC_API_KEY is
stripped from the subprocess env). Capture the corpus first with run_capture.py.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from research_system.llm import CHEAP, MID, STRONG, ClaudeCLIClient
from research_system.orchestrate import OrchestratorConfig, run_research
from research_system.paths import SubjectLayout

REPO = Path(__file__).resolve().parent.parent
_TIERS = {"cheap": CHEAP, "mid": MID, "strong": STRONG}


def _judge_tuple(n: int) -> tuple[str, ...]:
    # alternate mid/strong so the ensemble mixes a different model than the cheap answerer
    return tuple((MID if i % 2 == 0 else STRONG) for i in range(max(1, n)))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("subject")
    ap.add_argument("question")
    ap.add_argument("--research-root", default=str(REPO / "Research"))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--n", type=int, default=6)
    ap.add_argument("--answer-model", choices=_TIERS, default="mid")
    ap.add_argument("--decompose-model", choices=_TIERS, default="strong")
    ap.add_argument("--judges", type=int, default=3)
    ap.add_argument("--min-support", type=int, default=2)
    ap.add_argument("--gate-threshold", type=float, default=None,
                    help="calibrated conformal threshold (from run_calibration.py); overrides min-support")
    ap.add_argument("--discover", type=int, default=0, metavar="ITERS",
                    help="enable web discovery for unanswered sub-questions (max gap-loop iterations)")
    ap.add_argument("--no-resume", action="store_true")
    args = ap.parse_args()

    layout = SubjectLayout(args.research_root, args.subject)
    if not layout.sources_dir.is_dir():
        raise SystemExit(f"No captured corpus at {layout.sources_dir} — run run_capture.py first.")

    config = OrchestratorConfig(
        n_subquestions=args.n, k=args.k,
        decompose_model=_TIERS[args.decompose_model],
        answer_model=_TIERS[args.answer_model],
        judges=_judge_tuple(args.judges),
        min_support=args.min_support,
        gate_threshold=args.gate_threshold,
    )
    print(f"Researching '{args.question}' over {layout.root} "
          f"(k={args.k}, judges={len(config.judges)}, answer={args.answer_model})")

    client = ClaudeCLIClient()
    searcher = None
    if args.discover > 0:
        from research_system.discover import ClaudeWebSearcher
        searcher = ClaudeWebSearcher(client)
        print(f"web discovery enabled (max {args.discover} gap iterations)")

    res = run_research(layout, args.question, client,
                       config=config, resume=not args.no_resume,
                       searcher=searcher, max_gap_iters=args.discover)

    answered = sum(1 for sq in res.questions.subquestions if sq.status.value == "answered")
    print(f"\nsub-questions: {len(res.questions.subquestions)}  answered: {answered}")
    print(f"claims: {len(res.claims)}  supported: {res.n_supported}")
    print(f"synthesis -> {res.synthesis_path}")
    print(f"gaps      -> {layout.gaps_path}")


if __name__ == "__main__":
    main()
