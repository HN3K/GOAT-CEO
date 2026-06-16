"""Phase 1 gate: capture harness — extraction, provenance, failure honesty,
idempotency, dedup, boilerplate removal. All offline via injected fetchers."""

from __future__ import annotations

import research_system.capture as capture_mod
from research_system.capture import (
    CaptureItem,
    ExtractResult,
    FetchResult,
    arxiv_id,
    build_manifest,
    candidate_urls,
    capture_batch,
    capture_one,
    extract_content,
    extract_pdf,
    load_capture_items,
)
from research_system.contracts import CaptureStatus, SourceMeta, read_model
from research_system.paths import SubjectLayout

FIXED_NOW = lambda: "2026-01-01T00:00:00Z"  # noqa: E731


# A realistic article wrapped in heavy boilerplate (nav, ad, footer).
ARTICLE_HTML = """<!DOCTYPE html><html><head>
<title>Grounding Reduces Hallucination</title>
<meta name="author" content="A. Researcher">
</head><body>
<nav>HOME ABOUT CONTACT SUBSCRIBE-NOW LOGIN</nav>
<aside class="ad"><p>ADVERTISEMENT BUYNOWTOKEN limited offer click here</p></aside>
<article>
<h1>Grounding Reduces Hallucination</h1>
<p>Retrieval-augmented generation grounds each generated statement in retrieved
source text, which substantially reduces unsupported claims compared with closed
book generation that relies only on model parameters.</p>
<p>When the full source article is captured to disk, the task shifts from recall
to extraction, and even smaller models become markedly more reliable at copying
exact spans of supporting evidence.</p>
<p>Verification of each individual claim against the stored source is the decisive
step: a mechanical check that the quoted span appears verbatim in the source file
catches fabricated quotations at essentially no cost.</p>
<p>Finally, calibrated abstention lets the system flag a question as unanswered
rather than confabulate a plausible but unsupported synthesis from weak material.</p>
</article>
<footer>COPYRIGHT FOOTERJUNK all rights reserved 2026</footer>
</body></html>"""

EMPTY_HTML = "<html><head><title>Nothing</title></head><body></body></html>"


def fake_fetcher(html, *, status=200, final_url=None, error=None):
    def _f(url):
        if error is not None:
            return FetchResult(url=url, error=error)
        content = html.encode("utf-8") if html is not None else None
        return FetchResult(url=url, final_url=final_url or url, status=status,
                           content=content, html=html)
    return _f


def map_fetcher(mapping):
    def _f(url):
        html = mapping[url]
        return FetchResult(url=url, final_url=url, status=200,
                           content=html.encode("utf-8"), html=html)
    return _f


def result_map_fetcher(mapping):
    """Map candidate URL -> a prebuilt FetchResult (for fallback tests)."""
    def _f(url):
        return mapping[url]
    return _f


# --------------------------------------------------------------------------- #
# URL canonicalization
# --------------------------------------------------------------------------- #
def test_arxiv_id_and_candidates():
    assert arxiv_id("https://arxiv.org/abs/2401.00396") == "2401.00396"
    assert arxiv_id("https://arxiv.org/pdf/2412.18004") == "2412.18004"
    assert arxiv_id("https://arxiv.org/pdf/2412.18004v2.pdf") == "2412.18004v2"
    assert arxiv_id("https://arxiv.org/html/2510.17853v1") == "2510.17853v1"
    assert arxiv_id("https://example.com/paper") is None

    # abstract/pdf links are upgraded to the html full text first, pdf as fallback
    assert candidate_urls("https://arxiv.org/abs/2401.00396") == [
        "https://arxiv.org/html/2401.00396",
        "https://arxiv.org/pdf/2401.00396",
    ]
    assert candidate_urls("https://example.com/x") == ["https://example.com/x"]


# --------------------------------------------------------------------------- #
# PDF handling
# --------------------------------------------------------------------------- #
def test_extract_pdf_graceful_on_garbage():
    assert extract_pdf(b"not a real pdf").text is None


def test_capture_routes_pdf_bytes(tmp_path, monkeypatch):
    lay = SubjectLayout(tmp_path, "subj")
    monkeypatch.setattr(capture_mod, "extract_pdf",
                        lambda raw: ExtractResult(text="Extracted PDF body text."))
    pdf_fetcher = lambda url: FetchResult(  # noqa: E731
        url=url, final_url=url, status=200, content=b"%PDF-1.7 ...binary...",
        html=None, content_type="application/pdf")
    meta = capture_one("s001", "https://host/file.pdf", lay, fetcher=pdf_fetcher, now=FIXED_NOW)
    assert meta.capture_status is CaptureStatus.OK
    assert meta.extraction_method.startswith("pypdf@")
    assert "Extracted PDF body text." in lay.source_md("s001").read_text(encoding="utf-8")


def test_arxiv_falls_back_to_pdf_when_html_404(tmp_path, monkeypatch):
    lay = SubjectLayout(tmp_path, "subj")
    monkeypatch.setattr(capture_mod, "extract_pdf",
                        lambda raw: ExtractResult(text="Full paper text from PDF."))
    fetcher = result_map_fetcher({
        "https://arxiv.org/html/2401.00396": FetchResult(
            url="https://arxiv.org/html/2401.00396", status=404, error=None, html="not found"),
        "https://arxiv.org/pdf/2401.00396": FetchResult(
            url="https://arxiv.org/pdf/2401.00396", final_url="https://arxiv.org/pdf/2401.00396",
            status=200, content=b"%PDF-1.7 data", html=None, content_type="application/pdf"),
    })
    meta = capture_one("s001", "https://arxiv.org/abs/2401.00396", lay,
                       fetcher=fetcher, now=FIXED_NOW)
    assert meta.capture_status is CaptureStatus.OK
    assert meta.final_url == "https://arxiv.org/pdf/2401.00396"
    assert "Full paper text from PDF." in lay.source_md("s001").read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# Extraction
# --------------------------------------------------------------------------- #
def test_extract_removes_boilerplate_keeps_body():
    ex = extract_content(ARTICLE_HTML)
    assert ex.text is not None
    assert "Retrieval-augmented generation grounds" in ex.text
    assert "calibrated abstention" in ex.text
    # boilerplate tokens must be gone
    assert "ADVERTISEMENT" not in ex.text
    assert "BUYNOWTOKEN" not in ex.text
    assert "FOOTERJUNK" not in ex.text
    assert "SUBSCRIBE-NOW" not in ex.text
    assert ex.title == "Grounding Reduces Hallucination"
    # trafilatura normalizes author punctuation ("A. Researcher" -> "A Researcher")
    assert ex.author == "A Researcher"


# --------------------------------------------------------------------------- #
# capture_one — success and failure honesty
# --------------------------------------------------------------------------- #
def test_capture_one_ok(tmp_path):
    lay = SubjectLayout(tmp_path, "subj")
    meta = capture_one("s001", "https://ex.com/a", lay,
                       fetcher=fake_fetcher(ARTICLE_HTML), now=FIXED_NOW)
    assert meta.capture_status is CaptureStatus.OK
    assert meta.content_hash and meta.raw_hash
    assert meta.word_count and meta.word_count > 20
    assert meta.title == "Grounding Reduces Hallucination"
    assert lay.source_md("s001").exists()
    body = lay.source_md("s001").read_text(encoding="utf-8")
    assert "verbatim in the source file" in body
    # sidecar persisted and reloads
    assert read_model(SourceMeta, lay.source_meta("s001")) == meta


def test_capture_one_fetch_error_recorded_not_dropped(tmp_path):
    lay = SubjectLayout(tmp_path, "subj")
    meta = capture_one("s001", "https://ex.com/a", lay,
                       fetcher=fake_fetcher(None, error="ConnectError: boom"), now=FIXED_NOW)
    assert meta.capture_status is CaptureStatus.FETCH_ERROR
    assert not lay.source_md("s001").exists()       # no body
    assert lay.source_meta("s001").exists()          # but recorded


def test_capture_one_http_4xx_is_fetch_error(tmp_path):
    lay = SubjectLayout(tmp_path, "subj")
    meta = capture_one("s001", "https://ex.com/a", lay,
                       fetcher=fake_fetcher("nope", status=404), now=FIXED_NOW)
    assert meta.capture_status is CaptureStatus.FETCH_ERROR
    assert meta.http_status == 404


def test_capture_one_empty_extraction(tmp_path):
    lay = SubjectLayout(tmp_path, "subj")
    meta = capture_one("s001", "https://ex.com/a", lay,
                       fetcher=fake_fetcher(EMPTY_HTML), now=FIXED_NOW)
    assert meta.capture_status is CaptureStatus.EMPTY
    assert not lay.source_md("s001").exists()
    assert meta.raw_hash is not None                 # we did fetch something


# --------------------------------------------------------------------------- #
# Batch — idempotency and dedup
# --------------------------------------------------------------------------- #
def test_capture_batch_idempotent(tmp_path):
    lay = SubjectLayout(tmp_path, "subj")
    items = [CaptureItem("s001", "https://ex.com/a")]
    f = fake_fetcher(ARTICLE_HTML)

    r1 = capture_batch(lay, items, fetcher=f, now=FIXED_NOW)
    h1 = read_model(SourceMeta, lay.source_meta("s001")).content_hash
    body1 = lay.source_md("s001").read_text(encoding="utf-8")

    r2 = capture_batch(lay, items, fetcher=f, now=lambda: "2099-09-09T00:00:00Z")
    h2 = read_model(SourceMeta, lay.source_meta("s001")).content_hash
    body2 = lay.source_md("s001").read_text(encoding="utf-8")

    assert r1.captured == ["s001"]
    assert r2.captured == [] and r2.skipped_existing == ["s001"]
    assert h1 == h2                                  # content stable
    assert body1 == body2                            # bytes unchanged on re-run


def test_capture_batch_dedup_same_content(tmp_path):
    lay = SubjectLayout(tmp_path, "subj")
    items = [CaptureItem("s001", "https://ex.com/a"),
             CaptureItem("s002", "https://mirror.com/a")]
    f = map_fetcher({"https://ex.com/a": ARTICLE_HTML,
                     "https://mirror.com/a": ARTICLE_HTML})
    r = capture_batch(lay, items, fetcher=f, now=FIXED_NOW)
    assert r.captured == ["s001"]
    assert r.duplicates == {"s002": "s001"}
    assert lay.source_md("s001").exists()
    assert not lay.source_md("s002").exists()        # dup not duplicated on disk


# --------------------------------------------------------------------------- #
# Manifest + loader
# --------------------------------------------------------------------------- #
def test_build_manifest_excludes_dups_records_statuses(tmp_path):
    lay = SubjectLayout(tmp_path, "subj")
    items = [CaptureItem("s001", "https://ex.com/a", title="Good"),
             CaptureItem("s002", "https://mirror.com/a"),   # dup of s001
             CaptureItem("s003", "https://bad.com/x")]      # fetch error
    f = map_fetcher({"https://ex.com/a": ARTICLE_HTML,
                     "https://mirror.com/a": ARTICLE_HTML,
                     "https://bad.com/x": EMPTY_HTML})
    r = capture_batch(lay, items, fetcher=f, now=FIXED_NOW)
    m = build_manifest(lay, "subj", "the question?", items, r, now=FIXED_NOW)

    ids = {e.id for e in m.sources}
    assert ids == {"s001", "s003"}                   # dup excluded
    by_id = {e.id: e for e in m.sources}
    assert by_id["s001"].capture_status is CaptureStatus.OK
    assert by_id["s003"].capture_status is CaptureStatus.EMPTY
    assert read_model(type(m), lay.manifest_path) == m


def test_load_capture_items(tmp_path):
    sources_json = tmp_path / "sources.json"
    sources_json.write_text(
        '{"subject":"demo","sources":['
        '{"id":"s001","url":"https://a","title":"A"},'
        '{"id":"s002","url":"https://b"}]}',
        encoding="utf-8",
    )
    subject, items = load_capture_items(sources_json)
    assert subject == "demo"
    assert [i.id for i in items] == ["s001", "s002"]
    assert items[0].title == "A" and items[1].title is None
