# Phase 1 Review — Capture Harness

**Date:** 2026-06-13  **Verdict:** ✅ gate passed (with two honest residual limitations logged)

## What was built
`src/research_system/capture.py` + `scripts/run_capture.py`: fetch → boilerplate-strip
(trafilatura) → persist full text + provenance sidecar. Injectable `Fetcher` for offline
tests; `httpx_fetcher` for live runs.

## Gate criteria
| Criterion | Result |
|-----------|--------|
| Sources captured with clean full-body text | ✅ 14/15 OK, **~110k words** total |
| Failures recorded honestly, not dropped | ✅ s015 → `fetch_error` (recorded, no body) |
| Re-run idempotent (hashes stable, no dupes) | ✅ no-op re-run: `captured=0 skipped=15` |
| Unit tests | ✅ 34/34 pass |

## Issues caught by the review (and fixed before sign-off)
1. **arXiv `/abs/` captured only the abstract** (s001: 413w). The first live run "succeeded"
   on 9 sources but four were abstract-only stubs — a fidelity failure masquerading as success,
   which would have poisoned the benchmark. **Fix:** `candidate_urls()` upgrades `/abs/` & `/pdf/`
   → `/html/` full text first. s001 now **8,212 words**.
2. **PDFs → EMPTY** (5 sources; trafilatura can't parse PDF binary). **Fix:** `extract_pdf()`
   (pypdf) fallback, triggered by `%PDF-` magic bytes / content-type. s007 PDF now **18,703 words**.
3. **2023 arXiv papers have no `/html/` render** (s009, s010). **Fix:** the candidate list falls
   back `/html/` → `/pdf/` automatically; both captured via pypdf. Verified by
   `test_arxiv_falls_back_to_pdf_when_html_404`.

## Residual limitations (logged, not blocking)
- **s015 (MIT Press)** — 403 bot block. Needs a browser-based fetch fallback for
  Cloudflare-protected sites; out of scope for Phase 1. Recorded as `fetch_error`.
- **s005 (Anthropic page)** — only 202 words (JS-rendered / summary page). The *same paper*
  (Question Decomposition, 2307.11768) is captured in full as **s010**, so no content is lost
  for this corpus. Flags a general gap: JS-heavy pages need a rendering fetcher.
- **PDF extraction is lexically imperfect** (pypdf can merge columns / mangle ligatures). This does
  NOT break correctness: the verifier matches quotes against the *stored* `sources/<id>.md`, so
  internal consistency holds regardless of extraction fidelity. Quality, not correctness.

## Code assessment
- Encoding pinned to UTF-8 on every read/write (Windows cp1252 hazard avoided). ✓
- Failed captures always write a sidecar with a non-OK status → gate-visible. ✓
- `meta.url` preserves the originally-requested URL; `meta.final_url` records the candidate that
  actually succeeded → provenance intact through canonicalization. ✓
- Dedup by `raw_hash` removes redundant on-disk copies; `skipped_existing` guards re-runs. ✓

## Follow-ups for later phases
- Consider a browser/rendering fetcher (Playwright) for bot-blocked + JS-heavy sources.
- Optional: strip residual LaTeX author macros from arXiv HTML heads (e.g. s001 first line).
