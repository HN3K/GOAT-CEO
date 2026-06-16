"""rubric — ground AI coding agents in your standards.

Phase 0 surface: frozen contracts (``contracts``) and on-disk layout (``paths``).
Later phases add the KB store, deterministic gate, retrieval, LLM review, and CLI.
"""

from rubric.contracts import (
    SCHEMA_VERSION,
    Component,
    ContextPack,
    Convention,
    Enforcement,
    Exemplar,
    Finding,
    GateResult,
    KbManifest,
    Rule,
    RuleKind,
    Severity,
    Verdict,
)
from rubric.paths import KbLayout, RepoLayout, slugify

__all__ = [
    "SCHEMA_VERSION",
    "RuleKind",
    "Enforcement",
    "Severity",
    "Rule",
    "Exemplar",
    "Convention",
    "KbManifest",
    "Component",
    "ContextPack",
    "Finding",
    "GateResult",
    "Verdict",
    "KbLayout",
    "RepoLayout",
    "slugify",
]
