"""Phase 0 gate: contracts round-trip, reject drift, and stay in sync with schemas."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from research_system.contracts import (
    SCHEMA_VERSION,
    CaptureStatus,
    Claim,
    JudgeVote,
    Manifest,
    QuestionsFile,
    SourceCatalogEntry,
    SourceMeta,
    SubQuestion,
    SubQuestionStatus,
    Verdict,
    append_claim,
    read_claims,
    read_model,
    write_claims,
    write_model,
)

REPO = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Sample builders
# --------------------------------------------------------------------------- #
def sample_questions() -> QuestionsFile:
    return QuestionsFile(
        question="Does on-disk capture reduce hallucination?",
        subquestions=[
            SubQuestion(
                id="q1",
                text="What fraction of citations are unfaithful?",
                success_criteria="A cited percentage from a primary source.",
                status=SubQuestionStatus.ANSWERED,
                claim_ids=["c1"],
            ),
            SubQuestion(
                id="q2",
                text="Does full-text grounding beat snippet grounding?",
                success_criteria="A head-to-head benchmark delta.",
            ),
        ],
    )


def sample_meta() -> SourceMeta:
    return SourceMeta(
        id="s001",
        url="https://arxiv.org/pdf/2412.18004",
        final_url="https://arxiv.org/pdf/2412.18004",
        title="Correctness is not Faithfulness in RAG Attributions",
        author="Wallat et al.",
        published_date="2024-12-23",
        fetched_at="2026-06-13T21:54:00Z",
        content_hash="sha256:abc",
        raw_hash="sha256:def",
        word_count=2310,
        language="en",
        http_status=200,
        capture_status=CaptureStatus.OK,
        extraction_method="trafilatura@1.12",
    )


def sample_manifest() -> Manifest:
    return Manifest(
        subject="ai-research-accuracy",
        question="Does on-disk capture reduce hallucination?",
        created_at="2026-06-13T21:54:00Z",
        sources=[
            SourceCatalogEntry(
                id="s001",
                url="https://arxiv.org/pdf/2412.18004",
                title="Correctness is not Faithfulness",
                capture_status=CaptureStatus.OK,
                candidate_subq_ids=["q1"],
            ),
            SourceCatalogEntry(
                id="s002",
                url="https://example.com/paywalled",
                capture_status=CaptureStatus.PAYWALL,
            ),
        ],
    )


def sample_claim() -> Claim:
    return Claim(
        id="c1",
        subq_id="q1",
        text="Up to 57% of citations in attributed RAG answers are unfaithful.",
        source_id="s001",
        quote="up to 57% of citations ... are unfaithful",
        verdict=Verdict.SUPPORTED,
        quote_present=True,
        judge_votes=[
            JudgeVote(model="judge-a", verdict=Verdict.SUPPORTED, rationale="span states it"),
            JudgeVote(model="judge-b", verdict=Verdict.SUPPORTED),
        ],
    )


# --------------------------------------------------------------------------- #
# Round-trip
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "model, cls",
    [
        (sample_questions(), QuestionsFile),
        (sample_meta(), SourceMeta),
        (sample_manifest(), Manifest),
        (sample_claim(), Claim),
    ],
)
def test_model_round_trip(tmp_path, model, cls):
    path = tmp_path / "artifact.json"
    write_model(model, path)
    loaded = read_model(cls, path)
    assert loaded == model


def test_enums_serialize_as_values(tmp_path):
    path = tmp_path / "meta.json"
    write_model(sample_meta(), path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["capture_status"] == "ok"


# --------------------------------------------------------------------------- #
# Drift protection
# --------------------------------------------------------------------------- #
def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        SourceMeta.model_validate({"id": "s1", "url": "u", "bogus": 1})


def test_bad_enum_rejected():
    with pytest.raises(ValidationError):
        SourceMeta.model_validate({"id": "s1", "url": "u", "capture_status": "nonsense"})


def test_schema_version_present():
    assert QuestionsFile(question="x").schema_version == SCHEMA_VERSION
    assert Manifest(subject="s", question="x").schema_version == SCHEMA_VERSION


# --------------------------------------------------------------------------- #
# JSONL claims
# --------------------------------------------------------------------------- #
def test_claims_jsonl_append_and_read(tmp_path):
    path = tmp_path / "claims.jsonl"
    c1 = sample_claim()
    c2 = sample_claim().model_copy(update={"id": "c2", "verdict": Verdict.UNSUPPORTED})
    append_claim(path, c1)
    append_claim(path, c2)
    loaded = read_claims(path)
    assert [c.id for c in loaded] == ["c1", "c2"]
    assert loaded[1].verdict == Verdict.UNSUPPORTED


def test_read_claims_missing_file_returns_empty(tmp_path):
    assert read_claims(tmp_path / "nope.jsonl") == []


def test_write_claims_overwrites(tmp_path):
    path = tmp_path / "claims.jsonl"
    append_claim(path, sample_claim())
    write_claims(path, [sample_claim().model_copy(update={"id": "only"})])
    loaded = read_claims(path)
    assert [c.id for c in loaded] == ["only"]


# --------------------------------------------------------------------------- #
# Generated JSON Schemas stay in sync with the models
# --------------------------------------------------------------------------- #
def test_generated_schemas_in_sync():
    import sys

    sys.path.insert(0, str(REPO / "scripts"))
    import gen_schemas  # type: ignore

    schema_dir = REPO / "src" / "research_system" / "schemas"
    rendered = gen_schemas.render()
    assert rendered, "no schemas rendered"
    for filename, expected in rendered.items():
        on_disk = (schema_dir / filename).read_text(encoding="utf-8")
        assert on_disk == expected, (
            f"{filename} is stale — run `python scripts/gen_schemas.py` and commit"
        )
