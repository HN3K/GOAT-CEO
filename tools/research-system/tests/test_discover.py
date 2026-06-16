"""Item 1: web discovery wiring — unanswered sub-question -> search -> capture -> re-answer."""

import json

from research_system.capture import FetchResult
from research_system.contracts import QuestionsFile, SubQuestion, SubQuestionStatus
from research_system.discover import ClaudeWebSearcher, make_discovery_resolver
from research_system.gate import run_gap_loop
from research_system.llm import ScriptedClient
from research_system.paths import SubjectLayout
from research_system.retrieve import Corpus

# substantial article so trafilatura extracts the body cleanly
QUOTE = "releases oxygen as a byproduct of converting carbon dioxide and water"
ARTICLE = f"""<!DOCTYPE html><html><head><title>Photosynthesis</title></head><body>
<nav>HOME ADS</nav>
<article>
<h1>Photosynthesis</h1>
<p>Photosynthesis is the process by which green plants and some other organisms convert
light energy into chemical energy stored in glucose molecules for later use.</p>
<p>In the chloroplasts, chlorophyll absorbs sunlight and drives a reaction that
{QUOTE}, which is essential for aerobic life on Earth.</p>
<p>The released oxygen diffuses out of the leaf and into the atmosphere, while the
glucose produced fuels the plant's metabolism and growth over time.</p>
</article>
<footer>copyright junk</footer></body></html>"""


class FakeSearcher:
    def __init__(self, urls):
        self.urls = urls
        self.queries = []

    def search(self, query, max_results=5):
        self.queries.append(query)
        return self.urls[:max_results]


def discovery_router(system, prompt):
    if "meticulous research extractor" in system:           # answer
        return json.dumps({"answerable": True, "claims": [
            {"text": "Photosynthesis releases oxygen", "source_id": "d001", "quote": QUOTE}]})
    if "adversarial fact-checker" in system:                # verify
        return json.dumps({"verdict": "supported"})
    return ""


def fake_fetcher(url):
    return FetchResult(url=url, final_url=url, status=200,
                       content=ARTICLE.encode("utf-8"), html=ARTICLE)


# --------------------------------------------------------------------------- #
# ClaudeWebSearcher URL parsing
# --------------------------------------------------------------------------- #
def test_web_searcher_parses_json_array():
    llm = ScriptedClient(responses=['["https://a.org/x", "https://b.org/y"]'])
    assert ClaudeWebSearcher(llm).search("q", 5) == ["https://a.org/x", "https://b.org/y"]


def test_web_searcher_fallback_scrapes_urls():
    llm = ScriptedClient(responses=["See https://a.org/x and https://a.org/x and https://c.org/z"])
    out = ClaudeWebSearcher(llm).search("q", 5)
    assert out == ["https://a.org/x", "https://c.org/z"]   # deduped, order preserved


# --------------------------------------------------------------------------- #
# Discovery resolver wired into the gap loop
# --------------------------------------------------------------------------- #
def test_discovery_resolves_unanswered_subquestion(tmp_path):
    layout = SubjectLayout(tmp_path, "subj").ensure()
    corpus = Corpus([])                                   # empty -> q1 unanswerable initially
    questions = QuestionsFile(question="Q?", subquestions=[
        SubQuestion(id="q1", text="What does photosynthesis release?", success_criteria="a gas")])

    llm = ScriptedClient(router=discovery_router)
    resolver = make_discovery_resolver(
        layout, corpus, llm, FakeSearcher(["http://found.example/photosynthesis"]),
        judges=("mid",), fetcher=fake_fetcher)

    questions, claims = run_gap_loop(questions, [], resolver, max_iters=2, min_support=1)

    assert questions.subquestions[0].status is SubQuestionStatus.ANSWERED
    assert "d001" in corpus                               # new source captured into corpus
    assert layout.source_md("d001").exists()             # and persisted to disk
    assert any(c.verdict.value == "supported" for c in claims)


def test_discovery_dry_search_leaves_gap(tmp_path):
    layout = SubjectLayout(tmp_path, "subj").ensure()
    corpus = Corpus([])
    questions = QuestionsFile(question="Q?", subquestions=[
        SubQuestion(id="q1", text="unanswerable", success_criteria="x")])
    resolver = make_discovery_resolver(
        layout, corpus, ScriptedClient(router=discovery_router), FakeSearcher([]),  # no URLs
        judges=("mid",), fetcher=fake_fetcher)

    questions, claims = run_gap_loop(questions, [], resolver, max_iters=2, min_support=1)
    assert questions.subquestions[0].status is SubQuestionStatus.UNANSWERED  # flagged, not faked
