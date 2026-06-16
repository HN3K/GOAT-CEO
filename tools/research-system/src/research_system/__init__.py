"""Research System — auditable, low-hallucination AI research.

Phase 0 surface: frozen on-disk data contracts (`contracts`) and folder
conventions (`paths`). Later phases add capture, retrieval, verification,
abstention, synthesis, and benchmarking on top of these contracts.
"""

from research_system.contracts import (
    SCHEMA_VERSION,
    CaptureStatus,
    Verdict,
    SubQuestionStatus,
    SourceMeta,
    SubQuestion,
    QuestionsFile,
    SourceCatalogEntry,
    Manifest,
    JudgeVote,
    Claim,
)
from research_system.paths import SubjectLayout, slugify

__all__ = [
    "SCHEMA_VERSION",
    "CaptureStatus",
    "Verdict",
    "SubQuestionStatus",
    "SourceMeta",
    "SubQuestion",
    "QuestionsFile",
    "SourceCatalogEntry",
    "Manifest",
    "JudgeVote",
    "Claim",
    "SubjectLayout",
    "slugify",
]
