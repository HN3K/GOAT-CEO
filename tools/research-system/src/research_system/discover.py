"""Web discovery — find and capture NEW sources for unanswered sub-questions
(DESIGN §3 component 2; wires into the Phase-4 gap loop).

The orchestrator normally queries a pre-captured corpus. With a `Searcher`, an
unanswered sub-question can instead trigger: search the web → capture the new
sources to disk (boilerplate-stripped, same as Phase 1) → extend the corpus →
re-answer → re-verify. Newly captured sources get ids ``d001, d002, …``.

`Searcher` is a protocol so it is fakeable in tests. `ClaudeWebSearcher` is a
best-effort live implementation via `claude -p` web search.

LIVE CAVEAT: `claude -p` web-search reliability and clean URL extraction are not
guaranteed — the model may return fewer/no URLs or knowledge-based (possibly
stale) URLs if a live search isn't triggered. Validate before relying on it; the
mechanical capture step still records honest `capture_status` for anything fetched.
"""

from __future__ import annotations

import itertools
import json
import re
from typing import Callable, Protocol

from research_system.answer import answer_subquestion
from research_system.capture import Fetcher, capture_one, httpx_fetcher
from research_system.contracts import Claim, CaptureStatus, SubQuestion
from research_system.gate import Resolver
from research_system.llm import MID, LLMClient
from research_system.paths import SubjectLayout
from research_system.retrieve import BM25Retriever, Corpus, Document
from research_system.verify import DEFAULT_JUDGES, verify_claim

_URL = re.compile(r"https?://[^\s\"'<>)\]]+")


class Searcher(Protocol):
    def search(self, query: str, max_results: int = 5) -> list[str]: ...


class ClaudeWebSearcher:
    """Best-effort URL discovery via `claude -p` web search (subscription-billed)."""

    SYSTEM = (
        "You are a research librarian. Use web search to find authoritative primary "
        "sources (papers, official docs) that answer the user's query. Return ONLY a "
        "JSON array of URL strings, most authoritative first. No prose."
    )

    def __init__(self, llm: LLMClient, model: str = MID) -> None:
        self.llm = llm
        self.model = model

    def search(self, query: str, max_results: int = 5) -> list[str]:
        prompt = (f"Find up to {max_results} authoritative source URLs that answer:\n{query}\n\n"
                  'Return ONLY a JSON array of URLs, e.g. ["https://...","https://..."]')
        text = self.llm.generate(system=self.SYSTEM, prompt=prompt, model=self.model).text
        urls: list[str] = []
        m = re.search(r"\[.*\]", text or "", re.DOTALL)
        if m:
            try:
                urls = [u for u in json.loads(m.group(0)) if isinstance(u, str)]
            except json.JSONDecodeError:
                urls = []
        if not urls:  # fallback: scrape any URLs from the text
            urls = _URL.findall(text or "")
        # dedup, cap
        seen, out = set(), []
        for u in urls:
            if u not in seen:
                seen.add(u)
                out.append(u)
        return out[:max_results]


def make_discovery_resolver(
    layout: SubjectLayout,
    corpus: Corpus,
    llm: LLMClient,
    searcher: Searcher,
    *,
    k: int = 5,
    answer_model: str = MID,
    judges: tuple[str, ...] = DEFAULT_JUDGES,
    fetcher: Fetcher | None = None,
    discover_k: int = 4,
    id_prefix: str = "d",
) -> Resolver:
    """Build a gap-loop `Resolver` that discovers+captures new sources, then re-answers.

    The corpus is extended in place (and on disk under ``sources/``); each call
    rebuilds the retriever to include freshly captured documents.
    """
    fetcher = fetcher or httpx_fetcher()
    counter = itertools.count(1)

    def _next_id() -> str:
        # skip ids already present (e.g. across resolver invocations)
        while True:
            sid = f"{id_prefix}{next(counter):03d}"
            if sid not in corpus:
                return sid

    def resolve(pending: list[SubQuestion]) -> list[Claim]:
        new_claims: list[Claim] = []
        captured_any = False
        for sq in pending:
            for url in searcher.search(sq.text, max_results=discover_k):
                sid = _next_id()
                meta = capture_one(sid, url, layout, fetcher=fetcher)
                if meta.capture_status is CaptureStatus.OK:
                    corpus.add(Document(id=sid, text=layout.source_md(sid).read_text(encoding="utf-8")))
                    captured_any = True
        if not captured_any:
            return []  # discovery dry → gap loop will stop
        retriever = BM25Retriever(corpus)  # rebuild to include new docs
        for sq in pending:
            cs = answer_subquestion(sq, retriever, corpus, llm, k=k, model=answer_model)
            for c in cs:
                verify_claim(c, corpus, llm, judges=judges)
            new_claims.extend(cs)
        return new_claims

    return resolve
