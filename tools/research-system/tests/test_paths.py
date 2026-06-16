"""Phase 0 gate: folder conventions and a full subject-layout round-trip."""

from __future__ import annotations

import pytest

from research_system.contracts import (
    CaptureStatus,
    Manifest,
    QuestionsFile,
    SourceCatalogEntry,
    SourceMeta,
    SubQuestion,
    read_model,
    write_model,
)
from research_system.paths import SubjectLayout, slugify


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Accurately Performing Research with AI!", "accurately-performing-research-with-ai"),
        ("  Lost in the Middle  ", "lost-in-the-middle"),
        ("RAG vs. Long-Context", "rag-vs-long-context"),
        ("UPPER_snake CASE", "upper-snake-case"),
    ],
)
def test_slugify(raw, expected):
    assert slugify(raw) == expected


def test_slugify_empty_raises():
    with pytest.raises(ValueError):
        slugify("!!!")


def test_layout_paths(tmp_path):
    lay = SubjectLayout(tmp_path, "ai-research-accuracy")
    assert lay.root == tmp_path / "ai-research-accuracy"
    assert lay.sources_dir == lay.root / "sources"
    assert lay.source_md("s001") == lay.root / "sources" / "s001.md"
    assert lay.source_meta("s001") == lay.root / "sources" / "s001.meta.json"
    assert lay.questions_path.name == "questions.json"
    assert lay.manifest_path.name == "manifest.json"
    assert lay.claims_path.name == "claims.jsonl"
    assert lay.gaps_path.name == "gaps.md"
    assert lay.synthesis_path.name == "synthesis.md"


def test_from_subject_slugifies(tmp_path):
    lay = SubjectLayout.from_subject(tmp_path, "Lost in the Middle")
    assert lay.slug == "lost-in-the-middle"


def test_ensure_creates_dirs(tmp_path):
    lay = SubjectLayout(tmp_path, "subj").ensure()
    assert lay.sources_dir.is_dir()


def test_full_subject_layout_round_trips(tmp_path):
    """Build a complete subject directory and read every artifact back clean.

    This is the Phase 0 gate's end-to-end check: the on-disk layout that later
    phases produce can be written and re-validated without loss.
    """
    lay = SubjectLayout(tmp_path, "demo").ensure()

    # questions.json
    write_model(
        QuestionsFile(
            question="Does on-disk capture reduce hallucination?",
            subquestions=[
                SubQuestion(id="q1", text="unfaithful citation rate?", success_criteria="a %"),
            ],
        ),
        lay.questions_path,
    )

    # one source: cleaned text + meta sidecar
    lay.source_md("s001").write_text("# Title\n\nFull article body.\n", encoding="utf-8")
    write_model(
        SourceMeta(id="s001", url="https://example.com", capture_status=CaptureStatus.OK),
        lay.source_meta("s001"),
    )

    # manifest.json
    write_model(
        Manifest(
            subject="demo",
            question="Does on-disk capture reduce hallucination?",
            sources=[SourceCatalogEntry(id="s001", url="https://example.com", candidate_subq_ids=["q1"])],
        ),
        lay.manifest_path,
    )

    # read everything back
    q = read_model(QuestionsFile, lay.questions_path)
    m = read_model(Manifest, lay.manifest_path)
    meta = read_model(SourceMeta, lay.source_meta("s001"))

    assert q.subquestions[0].id == "q1"
    assert m.sources[0].id == "s001"
    assert meta.capture_status is CaptureStatus.OK
    assert lay.source_md("s001").read_text(encoding="utf-8").startswith("# Title")
