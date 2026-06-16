"""Frozen data contracts for rubric (DESIGN.md §3).

The two-plane knowledge base and the pipeline talk only through these models.
``extra="forbid"`` makes schema drift fail loudly. Bump SCHEMA_VERSION on any
breaking change and regenerate ``schemas/`` (scripts/gen_schemas.py).
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "0.1.0"
_Model = TypeVar("_Model", bound=BaseModel)


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class RuleKind(str, Enum):
    """How a rule is checked. DESIGN P2/P3."""

    DETERMINISTIC = "deterministic"   # an external tool (ast-grep/ruff/...) decides
    LLM = "llm"                       # requires model judgment (semantic/intent/abstraction)


class Enforcement(str, Enum):
    """Whether a finding can block. Deterministic→may block; LLM→advisory only (DESIGN P3)."""

    BLOCKING = "blocking"
    ADVISORY = "advisory"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #
class _Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Conventions plane (portable): Rule, Exemplar, Convention
# --------------------------------------------------------------------------- #
class Rule(_Contract):
    id: str
    name: str
    intent: str                                  # the "why", in human language
    kind: RuleKind
    enforcement: Enforcement
    tool: str | None = None                      # deterministic: "ast-grep" | "ruff" | ...
    spec: str | None = None                      # deterministic: rule pattern/config id; llm: review prompt
    languages: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class Exemplar(_Contract):
    """A canonical code example — the ICL grounding (exemplars > rules, DESIGN P1)."""

    id: str
    title: str
    intent: str
    language: str
    code: str                                    # the exact canonical snippet
    tags: list[str] = Field(default_factory=list)
    convention_id: str | None = None
    source: str | None = None                    # provenance (repo path / url)


class Convention(_Contract):
    """Groups rules + exemplars that express one standard."""

    id: str
    name: str
    intent: str
    rule_ids: list[str] = Field(default_factory=list)
    exemplar_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class KbManifest(_Contract):
    """Index of the portable conventions plane."""

    schema_version: str = SCHEMA_VERSION
    name: str
    version: str = "0.1.0"
    rule_ids: list[str] = Field(default_factory=list)
    exemplar_ids: list[str] = Field(default_factory=list)
    convention_ids: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Pipeline artifacts
# --------------------------------------------------------------------------- #
class Component(_Contract):
    """An existing in-repo component surfaced for REUSE (DESIGN P4)."""

    id: str
    name: str
    signature: str | None = None                 # e.g. function/class signature
    path: str | None = None
    summary: str | None = None


class ContextPack(_Contract):
    """The pre-generation grounding artifact injected before the model writes."""

    task: str
    exemplars: list[Exemplar] = Field(default_factory=list)
    rules: list[Rule] = Field(default_factory=list)
    components: list[Component] = Field(default_factory=list)


class Finding(_Contract):
    """A single issue. Deterministic findings may be BLOCKING; LLM findings are ADVISORY."""

    rule_id: str | None = None
    source: str                                  # "ruff" | "ast-grep" | "llm" | ...
    enforcement: Enforcement
    severity: Severity = Severity.WARNING
    message: str
    path: str | None = None
    line: int | None = None
    quote: str | None = None                     # the offending code span (auditability)
    confidence: float | None = None              # advisory only: fraction of adversarial judges that confirmed


class GateResult(_Contract):
    """Output of the deterministic gate (DESIGN §3 component 2)."""

    target: str
    findings: list[Finding] = Field(default_factory=list)
    tools_run: list[str] = Field(default_factory=list)
    tools_missing: list[str] = Field(default_factory=list)   # absent tools, recorded not crashed

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.enforcement is Enforcement.BLOCKING]

    @property
    def passed(self) -> bool:
        return not self.blocking


class Verdict(_Contract):
    """Final combined decision: blocking gate decides; advisory annotates (DESIGN §3 component 4)."""

    target: str
    passed: bool
    blocking: list[Finding] = Field(default_factory=list)
    advisory: list[Finding] = Field(default_factory=list)


class FileMetrics(_Contract):
    """Per-file adherence + anti-bloat metrics (DESIGN §6c). Conciseness is measurable here:
    SLOC and cyclomatic complexity are the quantitative anti-bloat signal [s028]."""

    path: str
    language: str | None = None
    loc: int = 0                                  # non-blank physical lines (universal)
    sloc: int | None = None                      # source lines, comments/blank excluded (radon)
    complexity_max: int | None = None            # highest cyclomatic complexity in the file
    complexity_avg: float | None = None
    gate_passed: bool = True                      # no blocking violation
    blocking_count: int = 0
    advisory_count: int = 0


class AdherenceReport(_Contract):
    """Aggregate adherence over a set of files — the quantitative 'is the code clean?' answer."""

    target: str
    files: list[FileMetrics] = Field(default_factory=list)
    metrics_tool: str | None = None              # which metric adapter ran (None = unavailable)

    @property
    def loc_total(self) -> int:
        return sum(f.loc for f in self.files)

    @property
    def gate_pass_rate(self) -> float:
        return (sum(f.gate_passed for f in self.files) / len(self.files)) if self.files else 1.0

    @property
    def blocking_total(self) -> int:
        return sum(f.blocking_count for f in self.files)

    @property
    def advisory_total(self) -> int:
        return sum(f.advisory_count for f in self.files)

    @property
    def blocking_per_kloc(self) -> float:
        return (self.blocking_total / self.loc_total * 1000) if self.loc_total else 0.0

    @property
    def complexity_max(self) -> int | None:
        vals = [f.complexity_max for f in self.files if f.complexity_max is not None]
        return max(vals) if vals else None


class CodifyProposal(_Contract):
    """A recurring (verified) finding the framework proposes to codify into the KB.

    The Codify loop (DESIGN §3 component 5, P8 observe-drift→codify): when the same
    issue survives adversarial verification repeatedly, it is drift worth turning into a
    standard. A proposal is human-approved before it joins the KB.
    """

    kind: str                                    # "exemplar" | "rule-tighten" | "rule-new"
    rule_id: str | None = None                   # the recurring rule that triggered this, if any
    title: str
    rationale: str
    occurrences: int
    evidence: list[str] = Field(default_factory=list)   # sample "file:line message" spans
    suggested_rule: Rule | None = None
    suggested_exemplar: Exemplar | None = None


# --------------------------------------------------------------------------- #
# (de)serialization helpers
# --------------------------------------------------------------------------- #
def write_model(model: BaseModel, path: str | Path) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(model.model_dump_json(indent=2), encoding="utf-8")


def read_model(cls: type[_Model], path: str | Path) -> _Model:
    return cls.model_validate_json(Path(path).read_text(encoding="utf-8"))
