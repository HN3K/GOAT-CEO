"""Frozen on-disk data contracts for the Research System.

Every pipeline component reads and writes only these models, serialized as the
files described in DESIGN.md §4. Models use ``extra="forbid"`` so that schema
drift (a stray or renamed field) fails loudly instead of silently corrupting a
corpus. Bump ``SCHEMA_VERSION`` on any breaking change and regenerate the JSON
Schemas under ``schemas/`` (see ``scripts/gen_schemas.py``).

File ownership (DESIGN.md §9.1):
  questions.json  -> QuestionsFile   (Decompose writes; Gate updates status)
  manifest.json   -> Manifest        (Capture/Catalog write)
  sources/<id>.meta.json -> SourceMeta  (Capture writes)
  claims.jsonl    -> Claim per line  (Answer appends; Verify updates verdict)
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Iterable, TypeVar

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "0.1.0"

_Model = TypeVar("_Model", bound=BaseModel)


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class CaptureStatus(str, Enum):
    """Outcome of a capture attempt. Non-OK statuses keep failed sources visible
    to the gate so missing evidence cannot masquerade as covered (DESIGN §4)."""

    OK = "ok"
    EMPTY = "empty"            # fetched but no extractable main body
    PAYWALL = "paywall"
    FETCH_ERROR = "fetch_error"
    JS_REQUIRED = "js_required"


class Verdict(str, Enum):
    """Per-claim verification verdict (DESIGN §3 component 6)."""

    PENDING = "pending"
    SUPPORTED = "supported"
    OVERREACH = "overreach"      # quote exists but claim exceeds what it supports
    UNSUPPORTED = "unsupported"  # quote absent or contradicted


class SubQuestionStatus(str, Enum):
    """Per-sub-question gate status (DESIGN §3 component 7)."""

    PENDING = "pending"
    ANSWERED = "answered"
    PARTIAL = "partial"
    UNANSWERED = "unanswered"


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #
class _Contract(BaseModel):
    """Strict base: unknown fields are rejected to catch schema drift early."""

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# questions.json
# --------------------------------------------------------------------------- #
class SubQuestion(_Contract):
    id: str
    text: str
    success_criteria: str
    status: SubQuestionStatus = SubQuestionStatus.PENDING
    claim_ids: list[str] = Field(default_factory=list)


class QuestionsFile(_Contract):
    schema_version: str = SCHEMA_VERSION
    question: str
    subquestions: list[SubQuestion] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# sources/<id>.meta.json
# --------------------------------------------------------------------------- #
class SourceMeta(_Contract):
    id: str
    url: str
    final_url: str | None = None
    title: str | None = None
    author: str | None = None
    published_date: str | None = None
    fetched_at: str | None = None            # ISO-8601 UTC
    content_hash: str | None = None          # sha256 of cleaned text
    raw_hash: str | None = None              # sha256 of original HTML (dedup)
    word_count: int | None = None
    language: str | None = None
    http_status: int | None = None
    capture_status: CaptureStatus = CaptureStatus.OK
    extraction_method: str | None = None


# --------------------------------------------------------------------------- #
# manifest.json
# --------------------------------------------------------------------------- #
class SourceCatalogEntry(_Contract):
    id: str
    url: str
    title: str | None = None
    capture_status: CaptureStatus = CaptureStatus.OK
    candidate_subq_ids: list[str] = Field(default_factory=list)


class Manifest(_Contract):
    schema_version: str = SCHEMA_VERSION
    subject: str                              # slug
    question: str
    created_at: str | None = None             # ISO-8601 UTC
    sources: list[SourceCatalogEntry] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# claims.jsonl
# --------------------------------------------------------------------------- #
class JudgeVote(_Contract):
    model: str
    verdict: Verdict
    rationale: str | None = None


class Claim(_Contract):
    id: str
    subq_id: str
    text: str
    source_id: str
    quote: str                                # exact span copied from the source
    verdict: Verdict = Verdict.PENDING
    quote_present: bool | None = None         # mechanical verbatim check (6a)
    judge_votes: list[JudgeVote] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# (de)serialization helpers — single source of truth for on-disk encoding
# --------------------------------------------------------------------------- #
def write_model(model: BaseModel, path: str | Path) -> None:
    """Write a single contract model to ``path`` as pretty JSON (UTF-8)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def read_model(cls: type[_Model], path: str | Path) -> _Model:
    """Read and validate a single contract model from ``path``."""
    return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))


def append_claim(path: str | Path, claim: Claim) -> None:
    """Append one Claim as a JSON line to ``claims.jsonl``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as fh:
        fh.write(claim.model_dump_json() + "\n")


def write_claims(path: str | Path, claims: Iterable[Claim]) -> None:
    """Write (overwrite) a full set of claims to ``claims.jsonl``."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for claim in claims:
            fh.write(claim.model_dump_json() + "\n")


def read_claims(path: str | Path) -> list[Claim]:
    """Read and validate all claims from a ``claims.jsonl`` file."""
    p = Path(path)
    if not p.exists():
        return []
    out: list[Claim] = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(Claim.model_validate_json(line))
    return out
