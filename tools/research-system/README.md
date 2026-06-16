# Research System

Auditable, low-hallucination AI research. Sources are captured **in full** to
disk with provenance; answers are decomposed into sub-questions, attributed at
the claim level with **exact quotes**, verified against the stored source text by
a different model, and **flagged rather than confabulated** when support is weak.

- **Design:** [`DESIGN.md`](DESIGN.md) — architecture, principles (each tied to research evidence), schemas, failure-mode analysis.
- **Roadmap:** [`ROADMAP.md`](ROADMAP.md) — phased build, each behind a validation gate.
- **Evidence base:** [`Research/ai-research-accuracy/`](Research/ai-research-accuracy/) — the verified deep-research run that informed the design (and the first benchmark fixture).

## Status

| Phase | What | State |
|-------|------|-------|
| 0 | Foundations & frozen data contracts | ✅ done |
| 1 | Capture harness (trafilatura → on-disk corpus) | ✅ done (14/15 sources, ~110k words) |
| 2 | Retrieve (BM25) + Answer + LLM substrate | ✅ done |
| 3 | Verifier (mechanical + ensemble judge) | ✅ done |
| 4 | Abstention gate + gap loop | ✅ done |
| 5 | Decompose + synthesis + orchestrator | ✅ done (live-validated) |
| 6 | Benchmark harness (B vs A′) | ✅ done |
| 7 | Model-tier sweep + conformal abstention | ✅ done |

All gates green: **`pytest` → 98 passed**. Per-phase reviews in `reviews/`.

### Run it (subscription-billed)
```bash
python scripts/run_capture.py                      # build/refresh the corpus
python scripts/run_research.py <subject> "<question>"   # full pipeline -> synthesis.md + gaps.md
python scripts/run_benchmark.py <subject>          # B-vs-A' faithfulness comparison
```

## Layout

```
src/research_system/
  contracts.py     frozen pydantic models for every on-disk artifact (DESIGN §4)
  paths.py         per-subject folder conventions
  schemas/         JSON Schemas generated from the models (gen_schemas.py)
scripts/gen_schemas.py   regenerate JSON Schemas after a contract change
tests/             Phase 0 gate: round-trip, drift-rejection, schema-sync
Research/<slug>/   a research subject's corpus (the product)
```

## Develop

```bash
python -m pip install -e ".[dev]"   # or just ensure pydantic + pytest are present
python -m pytest                     # run the gate
python scripts/gen_schemas.py        # regenerate JSON Schemas (commit the result)
```

Tests import from `src/` via `pyproject.toml`'s `pythonpath` setting — no install
strictly required to run them.

## Substrate

Standalone Python (Anthropic SDK + trafilatura) — chosen for capture fidelity,
deterministic/swappable model calls, and reproducible benchmarking. See
[`DESIGN.md` §9](DESIGN.md).
