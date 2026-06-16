"""LLM advisory review — grounded, never blocking (DESIGN.md §3 component 3, P3).

Runs the KB's LLM-kind rules over a target, grounding the model in (a) the code,
(b) the deterministic gate findings (external facts), and (c) canonical exemplars —
so it is never self-critique-from-nothing (DESIGN: self-correction needs external
feedback). Every finding it emits is ADVISORY and can never block; the LLM reasons
about the semantic residue deterministic tools cannot express.
"""

from __future__ import annotations

import json
import re

from rubric.contracts import Enforcement, Exemplar, Finding, GateResult, RuleKind, Severity
from rubric.kb import Kb
from rubric.llm import MID, LLMClient

REVIEW_SYSTEM = (
    "You are a senior code reviewer. You ONLY flag issues that deterministic tools cannot — "
    "semantic intent, naming appropriateness, architectural fit, 'is this the right abstraction', "
    "and logic that silently violates expectations. Ground every comment in the provided code, the "
    "deterministic findings, and the canonical exemplars. Do not repeat deterministic findings. Do "
    "not invent issues. If nothing qualifies, return an empty list."
)

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def build_review_prompt(code: str, gate_findings: list[Finding],
                        exemplars: list[Exemplar], instruction: str, path: str = "") -> str:
    facts = "\n".join(f"- [{f.source} {f.rule_id or ''}] {f.message}" for f in gate_findings) or "(none)"
    ex = "\n\n".join(f"### {e.title} ({e.language})\n```{e.language}\n{e.code}\n```" for e in exemplars) or "(none)"
    return (
        f"SOURCE FILE{(' ' + path) if path else ''}:\n```\n{code}\n```\n\n"
        f"DETERMINISTIC FINDINGS ALREADY DETECTED (facts — do NOT repeat these):\n{facts}\n\n"
        f"CANONICAL EXEMPLARS (the expected style):\n{ex}\n\n"
        f"REVIEW INSTRUCTION:\n{instruction}\n\n"
        'Return ONLY JSON: {"findings":[{"message":"...","line":<int|null>,"quote":"<exact span|null>"}]}\n'
        "Report only semantic issues deterministic tools cannot catch. If none, return "
        '{"findings":[]}.'
    )


def parse_advisory(raw: str, rule_id: str, path: str) -> list[Finding]:
    m = _JSON_OBJ.search(raw or "")
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out: list[Finding] = []
    for item in data.get("findings", []) or []:
        if not isinstance(item, dict):
            continue
        msg = (item.get("message") or "").strip()
        if not msg:
            continue
        line = item.get("line")
        out.append(Finding(
            rule_id=rule_id, source="llm", enforcement=Enforcement.ADVISORY,  # never blocks
            severity=Severity.INFO, message=msg, path=path,
            line=line if isinstance(line, int) else None,
            quote=(item.get("quote") or None)))
    return out


def review_code(
    path: str,
    code: str,
    kb: Kb,
    gate_result: GateResult,
    llm: LLMClient,
    *,
    model: str = MID,
    language: str | None = None,
    exemplars: list[Exemplar] | None = None,
) -> list[Finding]:
    """Run each applicable LLM rule as a grounded advisory review."""
    rules = [r for r in kb.rules.values() if r.kind is RuleKind.LLM and r.spec
             and (language is None or not r.languages or language in r.languages)]
    findings: list[Finding] = []
    for rule in rules:
        prompt = build_review_prompt(code, gate_result.findings, exemplars or [], rule.spec, path)
        resp = llm.generate(system=REVIEW_SYSTEM, prompt=prompt, model=model)
        findings.extend(parse_advisory(resp.text, rule.id, path))
    return findings
