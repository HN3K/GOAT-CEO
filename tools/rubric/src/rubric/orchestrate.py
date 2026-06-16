"""End-to-end orchestration (DESIGN.md §3): Retrieve → Gate → Review → Verdict.

Two entry points:
- ``build_context(task, kb, ...)`` → the pre-generation grounding block (inject before the model writes).
- ``enforce(path, kb, ...)`` → run the deterministic gate (blocking) + grounded LLM review (advisory)
  over an existing file and combine into a ``Verdict``. The gate decides pass/fail; the LLM annotates.
"""

from __future__ import annotations

from pathlib import Path

from rubric.contracts import Component, Enforcement, Exemplar, Verdict
from rubric.gate import ToolAdapter, run_gate
from rubric.kb import Kb
from rubric.llm import MID, LLMClient
from rubric.retrieve import build_context_pack, render_context_pack, select_exemplars
from rubric.review import review_code
from rubric.verify import DEFAULT_JUDGES, verify_findings

_SUFFIX_LANG = {".py": "py", ".ts": "ts", ".tsx": "tsx", ".js": "js", ".jsx": "jsx",
                ".go": "go", ".sql": "sql", ".rs": "rs", ".rb": "rb", ".java": "java"}


def language_of(path: str) -> str | None:
    return _SUFFIX_LANG.get(Path(path).suffix)


def build_context(
    task: str, kb: Kb, *, language: str | None = None,
    components: list[Component] | None = None, k: int = 5,
) -> str:
    """Render the inject-before-generation grounding block for a task."""
    return render_context_pack(build_context_pack(task, kb, language=language, components=components, k=k))


def enforce(
    path: str,
    kb: Kb,
    *,
    adapters: list[ToolAdapter],
    llm: LLMClient | None = None,
    language: str | None = None,
    model: str = MID,
    exemplars: list[Exemplar] | None = None,
    k_exemplars: int = 3,
    verify: bool = False,
    verify_judges: tuple[str, ...] = DEFAULT_JUDGES,
) -> Verdict:
    """Deterministic gate (blocking) + optional grounded LLM review (advisory) → Verdict.

    With ``verify=True`` the LLM advisory findings are passed through adversarial
    verification (Verify stage) before the Verdict — fabricated or refuted findings are
    dropped and survivors carry a ``confidence``. The gate (blocking) is never verified;
    deterministic facts need no second opinion.
    """
    code = Path(path).read_text(encoding="utf-8")
    lang = language or language_of(path)
    rules = kb.rules_for_language(lang) if lang else list(kb.rules.values())

    gate_result = run_gate(path, adapters, rules)

    advisory = list(f for f in gate_result.findings if f.enforcement is Enforcement.ADVISORY)
    if llm is not None:
        ex = exemplars if exemplars is not None else select_exemplars(kb, code, k=k_exemplars)
        llm_findings = review_code(path, code, kb, gate_result, llm,
                                   model=model, language=lang, exemplars=ex)
        if verify and llm_findings:
            llm_findings = verify_findings(llm_findings, code, llm, judges=verify_judges)
        advisory += llm_findings

    blocking = gate_result.blocking
    return Verdict(target=str(path), passed=not blocking, blocking=blocking, advisory=advisory)
