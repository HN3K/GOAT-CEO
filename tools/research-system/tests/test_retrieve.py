"""Phase 2 gate: document-level BM25 retrieval, capped top-k."""

from research_system.paths import SubjectLayout
from research_system.retrieve import BM25Retriever, Corpus, Document, tokenize


def _make_corpus(tmp_path):
    lay = SubjectLayout(tmp_path, "subj").ensure()
    lay.source_md("s001").write_text(
        "Retrieval augmented generation grounds claims in retrieved source text "
        "and reduces hallucination in language models.", encoding="utf-8")
    lay.source_md("s002").write_text(
        "Conformal prediction provides calibrated abstention with finite sample "
        "error bounds for deciding when to abstain.", encoding="utf-8")
    lay.source_md("s003").write_text(
        "The weather today is sunny with a gentle breeze and mild temperatures.",
        encoding="utf-8")
    return lay


def test_tokenize():
    assert tokenize("Hello, RAG-2 world!") == ["hello", "rag", "2", "world"]


def test_corpus_load(tmp_path):
    lay = _make_corpus(tmp_path)
    corpus = Corpus.load(lay)
    assert len(corpus) == 3
    assert set(corpus.ids) == {"s001", "s002", "s003"}
    assert "grounds claims" in corpus.get("s001")
    assert "s001" in corpus and "nope" not in corpus


def test_bm25_ranks_relevant_first(tmp_path):
    corpus = Corpus.load(_make_corpus(tmp_path))
    r = BM25Retriever(corpus)
    hits = r.top_k("retrieval grounding hallucination", k=3)
    assert hits[0].source_id == "s001"
    hits2 = r.top_k("calibrated abstention error bounds", k=3)
    assert hits2[0].source_id == "s002"


def test_top_k_is_capped(tmp_path):
    corpus = Corpus.load(_make_corpus(tmp_path))
    r = BM25Retriever(corpus)
    assert len(r.top_k("text", k=2)) == 2
    assert r.top_k("text", k=0) == []


def test_empty_corpus(tmp_path):
    lay = SubjectLayout(tmp_path, "empty").ensure()
    r = BM25Retriever(Corpus.load(lay))
    assert r.top_k("anything", k=5) == []
