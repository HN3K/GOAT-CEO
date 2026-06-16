"""Run the capture harness against a sources.json queue → on-disk corpus.

Usage:
  python scripts/run_capture.py [SOURCES_JSON] [--research-root DIR] [--question Q] [--force]

Defaults to the ai-research-accuracy fixture.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from research_system.capture import (
    build_manifest,
    capture_batch,
    httpx_fetcher,
    load_capture_items,
)
from research_system.contracts import CaptureStatus
from research_system.paths import SubjectLayout

REPO = Path(__file__).resolve().parent.parent
DEFAULT_SOURCES = REPO / "Research" / "ai-research-accuracy" / "sources.json"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("sources_json", nargs="?", default=str(DEFAULT_SOURCES))
    ap.add_argument("--research-root", default=str(REPO / "Research"))
    ap.add_argument("--question", default="Accurately performing research with AI agents, "
                    "minimizing hallucinations, and getting accurate results.")
    ap.add_argument("--force", action="store_true", help="re-capture even if already present")
    ap.add_argument("--timeout", type=float, default=25.0)
    args = ap.parse_args()

    subject, items = load_capture_items(args.sources_json)
    layout = SubjectLayout(args.research_root, subject)
    print(f"Subject: {subject}  ({len(items)} sources) -> {layout.root}")

    report = capture_batch(
        layout, items,
        fetcher=httpx_fetcher(timeout=args.timeout),
        force=args.force,
    )
    manifest = build_manifest(layout, subject, args.question, items, report)

    print("\n== per-source ==")
    for item in items:
        if item.id in report.duplicates:
            print(f"  {item.id}  DUP -> {report.duplicates[item.id]:8}  {item.url}")
        else:
            status = report.statuses.get(item.id, CaptureStatus.FETCH_ERROR)
            print(f"  {item.id}  {status.value:11}  {item.url}")

    print(f"\n{report.summary()}")
    ok = sum(1 for e in manifest.sources if e.capture_status is CaptureStatus.OK)
    print(f"manifest: {len(manifest.sources)} entries, {ok} OK -> {layout.manifest_path}")


if __name__ == "__main__":
    main()
