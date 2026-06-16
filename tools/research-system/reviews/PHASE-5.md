# Phase 5 Review — Synthesize + End-to-End Orchestrator

**Date:** 2026-06-13  **Verdict:** ✅ gate passed (incl. a live real-model validation)

## What was built
- `decompose.py` — question → atomic sub-questions + success criteria (LLM, strong tier).
- `synthesize.py` — **deterministic** assembly of SUPPORTED claims into a cited report. No LLM
  re-narration → every line traces to a source + verbatim quote by construction (removes a
  hallucination vector entirely).
- `orchestrate.py` — `run_research()` wires decompose → answer (per sub-question, separate context)
  → verify → gate → gaps → synthesize, with **stage checkpoints** (questions.json, claims.jsonl) for
  resume-from-disk.
- `scripts/run_research.py` — subscription-billed CLI over a captured corpus.

## Gate criteria
| Criterion | Result |
|-----------|--------|
| End-to-end run produces synthesis + gaps | ✅ offline test + live run |
| Every synthesis line traces to source_id + verbatim quote | ✅ offline `test_end_to_end_traceable`; **live: 10/10 citations traceable** |
| Mid-run kill + resume reproduces state | ✅ `test_resume_skips_all_completed_stages`, `test_resume_after_decompose_only...` |
| Only verified claims enter synthesis | ✅ unsupported excluded by construction |
| Tests | ✅ 88/88 |

## Live validation (real models, controlled cost)
Ran the full pipeline on a tiny 2-document corpus via `claude -p` (subscription, cheap tier, 1 judge):
- Real **Haiku followed the JSON contract** for decompose, answer, AND verify — the key risk that
  fakes cannot exercise. Confirmed parseable on first try.
- Answerer produced **exact verbatim quotes**, not paraphrases: 10/10 claims' quotes present in their
  cited source. Grounding holds against real model behavior.
- Synthesis well-structured, every claim cited. (Output inspected; corpus then removed.)

## Design decision: deterministic synthesis
The report is assembled from verified claims rather than written by an LLM. This guarantees
traceability and means synthesis costs zero tokens and cannot hallucinate. An optional LLM "narrative"
layer remains possible later but would itself need re-verification — the deterministic core is the
trustworthy default.

## Residual / follow-ups
- **Full ai-research-accuracy live run** was NOT executed here (cost control: big docs × ensemble ×
  many claims). It is ready via `run_research.py` and is the natural first step of the Phase 6
  benchmark, which the user triggers.
- Web **discovery** (finding new sources) is not wired into the gap-loop resolver yet; the orchestrator
  operates over the pre-captured corpus. Logged for when fresh-from-scratch research is needed.
