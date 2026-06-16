"""Document-level retrieval (DESIGN §5).

Granularity stays at the whole document — no sub-document chunking, so no
chunk-fragmentation loss. Retrieval *selects* which full docs reach a
sub-question's context, and top-k is capped + ranked to stay on the good side of
the inverted-U (lost-in-the-middle / too-many-passages degradation [P4]).

v1 router = BM25 over full text. The ``Retriever`` protocol keeps it pluggable
(embedding/hybrid rerankers can drop in later, and are a benchmark variable).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol

from research_system.paths import SubjectLayout

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@dataclass
class Document:
    id: str
    text: str


class Corpus:
    """All captured source bodies for a subject (the ``sources/*.md`` files)."""

    def __init__(self, documents: list[Document]) -> None:
        self.documents = documents
        self._by_id = {d.id: d for d in documents}

    @classmethod
    def load(cls, layout: SubjectLayout) -> "Corpus":
        docs: list[Document] = []
        if layout.sources_dir.is_dir():
            for md in sorted(layout.sources_dir.glob("*.md")):
                docs.append(Document(id=md.stem, text=md.read_text(encoding="utf-8")))
        return cls(docs)

    def get(self, source_id: str) -> str:
        return self._by_id[source_id].text

    def add(self, document: Document) -> bool:
        """Add a document (e.g. a newly discovered+captured source). Returns False
        if the id already exists. Callers should rebuild the retriever afterward."""
        if document.id in self._by_id:
            return False
        self.documents.append(document)
        self._by_id[document.id] = document
        return True

    def __contains__(self, source_id: str) -> bool:
        return source_id in self._by_id

    def __len__(self) -> int:
        return len(self.documents)

    @property
    def ids(self) -> list[str]:
        return [d.id for d in self.documents]


@dataclass
class Retrieved:
    source_id: str
    score: float


class Retriever(Protocol):
    def top_k(self, query: str, k: int) -> list[Retrieved]: ...


class BM25Retriever:
    """BM25 ranking over full-document texts."""

    def __init__(self, corpus: Corpus) -> None:
        from rank_bm25 import BM25Okapi

        self.corpus = corpus
        self._ids = corpus.ids
        tokenized = [tokenize(d.text) for d in corpus.documents]
        # BM25Okapi requires a non-empty corpus; guard the empty case.
        self._bm25 = BM25Okapi(tokenized) if tokenized else None

    def top_k(self, query: str, k: int) -> list[Retrieved]:
        if self._bm25 is None or k <= 0:
            return []
        scores = self._bm25.get_scores(tokenize(query))
        ranked = sorted(zip(self._ids, scores), key=lambda t: t[1], reverse=True)
        return [Retrieved(source_id=sid, score=float(s)) for sid, s in ranked[:k]]
