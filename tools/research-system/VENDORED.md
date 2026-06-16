# Vendored: Research System (engine only)

A **vendored snapshot** of the Research System engine, bundled into GOAT-CEO so a fresh clone can use
the optional `RESEARCH-KB-AVAILABLE` capability (the verifiable external-research KB) **without obtaining
the Research System separately**. GOAT-CEO drives it via its scripts; this is the source that provides them.

- **Source project:** the first-party Research System project (vendored here from a local checkout; no public remote yet)
- **Vendored commit:** `34ff457c071c2416e85a01bc73d4a333307a5cad`
- **Vendored on:** 2026-06-15
- **License:** MIT (same as GOAT-CEO — first-party code)
- **Engine only:** the upstream `Research/` folder (4.6M of past research *corpora* / products) is **excluded**
  — GOAT-CEO's research KB lives in `<repo-root>/research-kb/` (gitignored), built per session.

## Install

```bash
pip install -e "tools/research-system[capture,retrieval,llm]"
# requires Python >= 3.11. Core dep is pydantic; extras add trafilatura+httpx+pypdf (capture),
# rank-bm25 (retrieval), anthropic (llm — only needed if you use the API-key client).
```

The package has **no console-script entry point** — it is invoked via its scripts. Run them from this
directory (they resolve `research_system` via `src/`), redirecting output to GOAT-CEO's shared KB with
`--research-root`:

```bash
cd tools/research-system
python scripts/run_capture.py  <sources.json> --research-root ../../research-kb --question "<q>"
python scripts/run_research.py <subject-slug> "<question>" --research-root ../../research-kb
```

GOAT-CEO uses **only** `run_capture.py` + `run_research.py` (capture → decompose → answer with exact
quotes → cross-model verify → abstain → synthesize). The `benchmark.py` / `tier_sweep.py` / `conformal.py`
/ `external.py` modules are part of the upstream product's self-validation and are NOT driven by GOAT-CEO.

**Billing:** by default the engine calls the model via `claude -p` — the **Claude subscription** (it strips
`ANTHROPIC_API_KEY`/`AUTH_TOKEN` so it never silently hits the paid API). ~$1–3 subscription credit per research
question. The backend is the `research_system.llm.LLMClient` Protocol — `run_research(layout, question, llm, ...)`
takes the client as a parameter, so it is swappable (per-token `AnthropicClient`, or a local/hybrid client you
write) without engine changes. NOTE: the engine is a separate Python process — it cannot reuse a running Claude
Code session's model; `claude -p` IS how it uses the subscription. The default's only cost beyond credit is
subprocess nesting (~60–100 serial `claude -p` spawns/run) when an agent drives it.

See `README.md` → External research KB, `GOAT-CEO-REWORK-DESIGN.md §J`, and the engine's own `DESIGN.md`.

## Updating (re-vendoring)

Do **not** edit files here — edit the upstream Research System and re-vendor, **excluding** the corpora:

```bash
git -C "<Research System repo>" archive HEAD ':!Research' | tar -x -C tools/research-system
```

Then update the **Vendored commit** hash above. The `:!Research` pathspec is required — upstream
intentionally tracks `Research/` (4.6M), and those past products must not enter GOAT-CEO.
