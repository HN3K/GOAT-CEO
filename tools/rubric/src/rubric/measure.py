"""Adherence + anti-bloat measurement (DESIGN §6c).

Quantifies "is the AI's code actually clean?" — the metric behind the goal that a
quality-conscious reviewer is satisfied. Two families, both grounded in the corpus:

- **Adherence**: gate-pass rate and blocking-violation density (per KLOC). The deterministic
  gate is the ground truth for hard-rule conformance.
- **Anti-bloat / conciseness**: SLOC and cyclomatic complexity — the measurable face of bloat
  (high-capacity models consolidate edge-cases into Long Methods [s028]). Per P5 (compose,
  don't rebuild) these come from ``radon``, wrapped as a ``MetricAdapter``; absent → recorded,
  not fatal (same graceful-degradation contract as the gate).

A report can be saved and diffed against a later run (``report_delta``) to show before/after —
e.g. ungrounded generation vs rubric-grounded — turning "cleaner" into a number.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from rubric.contracts import AdherenceReport, Enforcement, FileMetrics
from rubric.gate import ToolAdapter, run_gate
from rubric.kb import Kb
from rubric.llm import MID, LLMClient
from rubric.orchestrate import language_of
from rubric.review import review_code
from rubric.verify import verify_findings


@dataclass
class ComplexityResult:
    sloc: int | None = None
    complexity_max: int | None = None
    complexity_avg: float | None = None


@runtime_checkable
class MetricAdapter(Protocol):
    name: str

    def available(self) -> bool: ...

    def measure(self, path: str, code: str) -> ComplexityResult | None: ...


class RadonAdapter:
    """Cyclomatic complexity + raw SLOC via radon (Python). Graceful if radon is absent."""

    name = "radon"

    def available(self) -> bool:
        try:
            import radon  # noqa: F401
        except ImportError:
            return False
        return True

    def measure(self, path: str, code: str) -> ComplexityResult | None:
        if Path(path).suffix != ".py":
            return None
        try:
            from radon.complexity import cc_visit
            from radon.raw import analyze
            blocks = cc_visit(code)
            raw = analyze(code)
        except (ImportError, SyntaxError):
            return None
        complexities = [b.complexity for b in blocks]
        return ComplexityResult(
            sloc=raw.sloc,
            complexity_max=max(complexities) if complexities else 0,
            complexity_avg=round(sum(complexities) / len(complexities), 2) if complexities else 0.0,
        )


def _loc(code: str) -> int:
    """Non-blank physical lines — a universal size signal (no tool needed)."""
    return sum(1 for line in code.splitlines() if line.strip())


def measure_file(
    path: str,
    kb: Kb,
    adapters: list[ToolAdapter],
    *,
    metric: MetricAdapter | None = None,
    llm: LLMClient | None = None,
    model: str = MID,
    verify: bool = False,
) -> FileMetrics:
    """Measure one file: gate adherence + (optional LLM advisory) + anti-bloat metrics.

    LLM review is opt-in (cost); by default measurement is deterministic and CI-cheap.
    """
    code = Path(path).read_text(encoding="utf-8")
    lang = language_of(path)
    rules = kb.rules_for_language(lang) if lang else list(kb.rules.values())
    gate = run_gate(path, adapters, rules)

    advisory = [f for f in gate.findings if f.enforcement is Enforcement.ADVISORY]
    if llm is not None:
        llm_findings = review_code(path, code, kb, gate, llm, model=model, language=lang)
        advisory += verify_findings(llm_findings, code, llm) if verify else llm_findings

    cr = metric.measure(path, code) if metric and metric.available() else None
    return FileMetrics(
        path=path, language=lang, loc=_loc(code),
        sloc=cr.sloc if cr else None,
        complexity_max=cr.complexity_max if cr else None,
        complexity_avg=cr.complexity_avg if cr else None,
        gate_passed=gate.passed, blocking_count=len(gate.blocking),
        advisory_count=len(advisory))


def measure(
    paths: list[str],
    kb: Kb,
    adapters: list[ToolAdapter],
    *,
    metric: MetricAdapter | None = None,
    llm: LLMClient | None = None,
    model: str = MID,
    verify: bool = False,
) -> AdherenceReport:
    """Measure adherence + anti-bloat across files into an ``AdherenceReport``."""
    metric = metric if metric is not None else RadonAdapter()
    files = [
        measure_file(p, kb, adapters, metric=metric, llm=llm, model=model, verify=verify)
        for p in paths if Path(p).is_file() and language_of(p) is not None
    ]
    tool = metric.name if (metric and metric.available()) else None
    return AdherenceReport(target=f"{len(files)} file(s)", files=files, metrics_tool=tool)


def report_delta(baseline: AdherenceReport, current: AdherenceReport) -> dict:
    """Before/after deltas for the headline metrics (negative complexity/bloat = improvement)."""
    def d(now: float, was: float) -> float:
        return round(now - was, 3)

    return {
        "gate_pass_rate": d(current.gate_pass_rate, baseline.gate_pass_rate),
        "blocking_total": current.blocking_total - baseline.blocking_total,
        "blocking_per_kloc": d(current.blocking_per_kloc, baseline.blocking_per_kloc),
        "advisory_total": current.advisory_total - baseline.advisory_total,
        "loc_total": current.loc_total - baseline.loc_total,
        "complexity_max": (None if current.complexity_max is None or baseline.complexity_max is None
                           else current.complexity_max - baseline.complexity_max),
    }
