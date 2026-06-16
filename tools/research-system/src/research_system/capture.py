"""Phase 1 — Capture harness (the novel core).

Fetch a URL, mechanically strip boilerplate (trafilatura), and persist the full
cleaned article body + a provenance sidecar to disk. No model judgment: chrome
removal only, never relevance excerpting (DESIGN.md P1).

The fetch is injected (``Fetcher`` protocol) so the extraction/persistence logic
is testable offline with local HTML fixtures. ``httpx_fetcher`` is the live one.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Protocol

import trafilatura
from trafilatura.metadata import extract_metadata

from research_system.contracts import (
    CaptureStatus,
    Manifest,
    SourceCatalogEntry,
    SourceMeta,
    read_model,
    write_model,
)
from research_system.paths import SubjectLayout

EXTRACTION_METHOD = f"trafilatura@{trafilatura.__version__}"
DEFAULT_USER_AGENT = "ResearchSystem/0.1 (+source-capture)"

NowFn = Callable[[], str]


def utcnow_iso() -> str:
    """Current UTC time as an ISO-8601 ``...Z`` string (second precision)."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sha256(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


# --------------------------------------------------------------------------- #
# URL canonicalization — prefer full text over abstract/PDF stubs
# --------------------------------------------------------------------------- #
_ARXIV_RE = re.compile(r"arxiv\.org/(?:abs|pdf|html)/([^/?#]+?)(?:\.pdf)?(?:[?#].*)?$", re.I)


def arxiv_id(url: str) -> str | None:
    """Return the arXiv id (with version if present) for an abs/pdf/html URL."""
    m = _ARXIV_RE.search(url)
    return m.group(1) if m else None


def candidate_urls(url: str) -> list[str]:
    """Ordered fetch candidates for a source URL, best fidelity first.

    arXiv ``/abs/`` and ``/pdf/`` links only yield an abstract or a binary PDF;
    the ``/html/`` full-text render is far better for grounding, so we try it
    first and fall back to the PDF. Non-arXiv URLs are fetched as given.
    """
    aid = arxiv_id(url)
    if aid:
        return [f"https://arxiv.org/html/{aid}", f"https://arxiv.org/pdf/{aid}"]
    return [url]


# --------------------------------------------------------------------------- #
# Fetching (injectable)
# --------------------------------------------------------------------------- #
@dataclass
class FetchResult:
    url: str
    final_url: str | None = None
    status: int | None = None
    content: bytes | None = None     # raw response bytes (hashed for dedup)
    html: str | None = None          # decoded text passed to the extractor
    content_type: str | None = None  # response Content-Type header
    error: str | None = None


class Fetcher(Protocol):
    def __call__(self, url: str) -> FetchResult: ...


def httpx_fetcher(timeout: float = 20.0, user_agent: str = DEFAULT_USER_AGENT) -> Fetcher:
    """Live fetcher: follows redirects, sets a UA, never raises (errors → FetchResult.error)."""
    import httpx

    def _fetch(url: str) -> FetchResult:
        try:
            with httpx.Client(
                follow_redirects=True,
                timeout=timeout,
                headers={"User-Agent": user_agent},
            ) as client:
                r = client.get(url)
            return FetchResult(
                url=url,
                final_url=str(r.url),
                status=r.status_code,
                content=r.content,
                html=r.text,
                content_type=r.headers.get("content-type"),
            )
        except Exception as exc:  # network/DNS/timeout/etc. — recorded, not raised
            return FetchResult(url=url, error=f"{type(exc).__name__}: {exc}")

    return _fetch


# --------------------------------------------------------------------------- #
# Extraction (mechanical, no model)
# --------------------------------------------------------------------------- #
@dataclass
class ExtractResult:
    text: str | None
    title: str | None = None
    author: str | None = None
    date: str | None = None


def extract_content(html: str) -> ExtractResult:
    """Full main-body markdown + bibliographic metadata. Boilerplate removed."""
    text = trafilatura.extract(
        html,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
    )
    title = author = date = None
    try:
        md = extract_metadata(html)
        if md is not None:
            title, author, date = md.title, md.author, md.date
    except Exception:
        pass  # metadata is best-effort; absence is not a capture failure
    return ExtractResult(text=(text or None), title=title, author=author, date=date)


def _pdf_method() -> str:
    import pypdf

    return f"pypdf@{pypdf.__version__}"


def extract_pdf(content: bytes) -> ExtractResult:
    """Extract text (and title metadata) from PDF bytes via pypdf."""
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(content))
        parts = [t.strip() for page in reader.pages if (t := page.extract_text() or "").strip()]
        text = "\n\n".join(parts) or None
        title = None
        try:
            if reader.metadata and reader.metadata.title:
                title = str(reader.metadata.title)
        except Exception:
            pass
        return ExtractResult(text=text, title=title)
    except Exception:
        return ExtractResult(text=None)


def _looks_like_pdf(raw: bytes, content_type: str | None) -> bool:
    return raw[:5] == b"%PDF-" or (content_type is not None and "pdf" in content_type.lower())


# --------------------------------------------------------------------------- #
# Capture one source
# --------------------------------------------------------------------------- #
def capture_one(
    source_id: str,
    url: str,
    layout: SubjectLayout,
    *,
    fetcher: Fetcher,
    now: NowFn = utcnow_iso,
) -> SourceMeta:
    """Fetch + extract + persist one source. Always writes a meta sidecar — a
    failed capture is recorded with a non-OK ``capture_status``, never dropped.

    Tries fidelity-ordered candidate URLs (e.g. arXiv ``/html/`` before ``/pdf/``)
    and routes PDF bytes through the PDF extractor. ``meta.url`` keeps the original
    requested URL; ``meta.final_url`` records which candidate actually succeeded.
    """
    meta = SourceMeta(id=source_id, url=url, fetched_at=now(), extraction_method=EXTRACTION_METHOD)
    got_body = False

    for cand in candidate_urls(url):
        fr = fetcher(cand)
        meta.http_status = fr.status
        meta.final_url = fr.final_url

        # fetch failure / HTTP error → try the next candidate
        if fr.error is not None or (fr.status is not None and fr.status >= 400):
            continue
        raw_bytes = fr.content if fr.content is not None else (fr.html.encode("utf-8") if fr.html else None)
        if raw_bytes is None:
            continue

        got_body = True
        meta.raw_hash = _sha256(raw_bytes)

        if _looks_like_pdf(raw_bytes, fr.content_type):
            ex = extract_pdf(raw_bytes)
            method = _pdf_method()
        else:
            html = fr.html if fr.html is not None else raw_bytes.decode("utf-8", "ignore")
            ex = extract_content(html)
            method = EXTRACTION_METHOD

        if ex.text and ex.text.strip():
            text = ex.text.strip() + "\n"
            layout.sources_dir.mkdir(parents=True, exist_ok=True)
            layout.source_md(source_id).write_text(text, encoding="utf-8")
            meta.content_hash = _sha256(text.encode("utf-8"))
            meta.word_count = len(text.split())
            meta.title = ex.title
            meta.author = ex.author
            meta.published_date = ex.date
            meta.extraction_method = method
            meta.capture_status = CaptureStatus.OK
            write_model(meta, layout.source_meta(source_id))
            return meta
        # fetched but nothing extractable → try the next candidate

    meta.capture_status = CaptureStatus.EMPTY if got_body else CaptureStatus.FETCH_ERROR
    write_model(meta, layout.source_meta(source_id))
    return meta


# --------------------------------------------------------------------------- #
# Batch capture + catalog
# --------------------------------------------------------------------------- #
@dataclass
class CaptureItem:
    id: str
    url: str
    title: str | None = None


@dataclass
class CaptureReport:
    captured: list[str] = field(default_factory=list)
    skipped_existing: list[str] = field(default_factory=list)
    duplicates: dict[str, str] = field(default_factory=dict)  # dup_id -> kept_id
    failures: list[str] = field(default_factory=list)
    statuses: dict[str, CaptureStatus] = field(default_factory=dict)

    def summary(self) -> str:
        return (
            f"captured={len(self.captured)} skipped={len(self.skipped_existing)} "
            f"duplicates={len(self.duplicates)} failures={len(self.failures)}"
        )


def capture_batch(
    layout: SubjectLayout,
    items: list[CaptureItem],
    *,
    fetcher: Fetcher,
    force: bool = False,
    now: NowFn = utcnow_iso,
) -> CaptureReport:
    """Capture many sources idempotently.

    - Existing captures are skipped unless ``force`` (re-run is cheap & stable).
    - Content duplicates (same ``raw_hash`` reached via different URLs) keep the
      first occurrence; later ones are recorded in ``duplicates`` and their files
      removed so the corpus has no redundant copies.
    """
    layout.ensure()
    report = CaptureReport()
    seen_raw: dict[str, str] = {}

    for item in items:
        meta_path = layout.source_meta(item.id)
        if meta_path.exists() and not force:
            existing = read_model(SourceMeta, meta_path)
            report.skipped_existing.append(item.id)
            report.statuses[item.id] = existing.capture_status
            if existing.raw_hash:
                seen_raw.setdefault(existing.raw_hash, item.id)
            continue

        meta = capture_one(item.id, item.url, layout, fetcher=fetcher, now=now)
        report.statuses[item.id] = meta.capture_status

        if meta.capture_status is not CaptureStatus.OK:
            report.failures.append(item.id)
            continue

        if meta.raw_hash and meta.raw_hash in seen_raw:
            kept = seen_raw[meta.raw_hash]
            layout.source_md(item.id).unlink(missing_ok=True)
            layout.source_meta(item.id).unlink(missing_ok=True)
            report.duplicates[item.id] = kept
            report.statuses.pop(item.id, None)
            continue

        if meta.raw_hash:
            seen_raw[meta.raw_hash] = item.id
        report.captured.append(item.id)

    return report


def build_manifest(
    layout: SubjectLayout,
    subject: str,
    question: str,
    items: list[CaptureItem],
    report: CaptureReport,
    *,
    now: NowFn = utcnow_iso,
) -> Manifest:
    """Write manifest.json: run metadata + source catalog (dups excluded)."""
    entries: list[SourceCatalogEntry] = []
    for item in items:
        if item.id in report.duplicates:
            continue
        status = report.statuses.get(item.id, CaptureStatus.FETCH_ERROR)
        entries.append(
            SourceCatalogEntry(
                id=item.id,
                url=item.url,
                title=item.title,
                capture_status=status,
                candidate_subq_ids=[],  # populated later by Decompose/Catalog
            )
        )
    manifest = Manifest(subject=subject, question=question, created_at=now(), sources=entries)
    write_model(manifest, layout.manifest_path)
    return manifest


def load_capture_items(sources_json_path: str | Path) -> tuple[str, list[CaptureItem]]:
    """Parse a sources.json capture queue → (subject_slug, items)."""
    data = json.loads(Path(sources_json_path).read_text(encoding="utf-8"))
    subject = data.get("subject", "")
    items = [
        CaptureItem(id=s["id"], url=s["url"], title=s.get("title"))
        for s in data.get("sources", [])
    ]
    return subject, items
