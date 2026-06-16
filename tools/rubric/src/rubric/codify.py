"""Codify loop — observe drift → propose a standard (DESIGN §3 component 5, P8).

This is where adversarial verification *evolves the framework*. Findings that survive the
Verify stage are real signal; when the same real issue recurs across the codebase it is no
longer a one-off nit but **drift worth codifying** into the portable KB — the factory.ai
"lint development cycle" and Semgrep "memories" pattern [s043].

The loop is deterministic and conservative: it clusters verified findings, and only the ones
that recur at/above a threshold become ``CodifyProposal``s. A proposal names the recurring
rule, carries the evidence, and (where the issue is mechanizable) suggests tightening an
advisory rule toward a deterministic one. Proposals are **human-approved before joining the
KB** — codify proposes; a person disposes.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from rubric.contracts import (
    CodifyProposal,
    Exemplar,
    Finding,
    Rule,
    write_model,
)
from rubric.kb import Kb
from rubric.llm import MID, LLMClient
from rubric.paths import RepoLayout, slugify

_WS = re.compile(r"\s+")
_NUM = re.compile(r"\d+")
_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def _cluster_key(f: Finding) -> str:
    """Group findings by rule when known, else by a normalized message shape."""
    if f.rule_id:
        return f"rule:{f.rule_id}"
    norm = _NUM.sub("#", _WS.sub(" ", f.message.lower()).strip())
    return f"msg:{norm[:80]}"


def _evidence(f: Finding) -> str:
    loc = f":{f.line}" if f.line else ""
    return f"{f.path or '?'}{loc} {f.message}".strip()


def propose_codifications(
    findings: list[Finding], *, threshold: int = 3
) -> list[CodifyProposal]:
    """Cluster verified advisory findings; propose codifying those recurring ``>= threshold``.

    Returns proposals ordered most-recurring first. Each proposal points at the recurring
    rule and its evidence; for a clustered rule it suggests tightening toward determinism.
    """
    clusters: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        clusters[_cluster_key(f)].append(f)

    proposals: list[CodifyProposal] = []
    for key, group in clusters.items():
        if len(group) < threshold:
            continue
        rule_id = group[0].rule_id
        sample = group[0].message
        evidence = [_evidence(f) for f in group[:5]]
        if rule_id:
            kind, title = "rule-tighten", f"Recurring violations of '{rule_id}'"
            rationale = (
                f"'{rule_id}' was flagged {len(group)} times and survived adversarial "
                "verification. A recurring real issue is drift: consider sharpening the rule "
                "(or adding a deterministic ast-grep pattern) so the gate blocks it earlier.")
        else:
            kind, title = "rule-new", f"Recurring un-ruled issue: {sample[:60]}"
            rationale = (
                f"This issue recurred {len(group)} times with no rule attached. Consider adding "
                "a convention + exemplar so the standard is grounded before generation.")
        proposals.append(CodifyProposal(
            kind=kind, rule_id=rule_id, title=title, rationale=rationale,
            occurrences=len(group), evidence=evidence))

    proposals.sort(key=lambda p: p.occurrences, reverse=True)
    return proposals


# --------------------------------------------------------------------------- #
# Auto-draft — turn a proposal into a concrete, schema-valid Rule (+ Exemplar)
# --------------------------------------------------------------------------- #
DRAFT_SYSTEM = (
    "You are a senior engineer codifying a RECURRING, adversarially-verified code-review finding "
    "into a reusable team standard. Draft the smallest precise rule that would catch this issue "
    "going forward. Prefer a DETERMINISTIC ast-grep rule (kind='deterministic', tool='ast-grep', "
    "spec=<ast-grep pattern>) when the issue is structurally mechanizable; otherwise an LLM rule "
    "(kind='llm', enforcement='advisory', spec=<crisp one-paragraph review instruction>). Keep "
    "'intent' to one sentence. Ground everything ONLY in the provided evidence; do not invent scope."
)


def build_draft_prompt(proposal: CodifyProposal, existing: Rule | None) -> str:
    ev = "\n".join(f"- {e}" for e in proposal.evidence) or "(none)"
    ctx = ""
    if existing is not None:
        ctx = (f"\nEXISTING RULE being tightened (id={existing.id}, kind={existing.kind.value}, "
               f"enforcement={existing.enforcement.value}):\n{existing.intent}\nspec: {existing.spec}\n")
    return (
        f"RECURRING FINDING: {proposal.title}\n"
        f"It occurred {proposal.occurrences} times. {proposal.rationale}\n"
        f"\nEVIDENCE (file:line message):\n{ev}\n{ctx}\n"
        'Return ONLY JSON:\n'
        '{"rule": {"id": "<slug>", "name": "<short name>", "intent": "<one sentence>", '
        '"kind": "deterministic|llm", "enforcement": "blocking|advisory", '
        '"tool": "ast-grep|ruff|rubric|null", "spec": "<pattern or review instruction>", '
        '"languages": ["py"], "tags": ["..."]}, '
        '"exemplar": {"title": "...", "intent": "...", "language": "py", "code": "<canonical correct code>", '
        '"tags": ["..."]} }\n'
        'Set "exemplar" to null if a code example would not add value.'
    )


def _parse_drafted(raw: str, proposal: CodifyProposal) -> CodifyProposal:
    m = _JSON_OBJ.search(raw or "")
    if not m:
        return proposal
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return proposal
    update: dict = {}
    rule_d = data.get("rule")
    if isinstance(rule_d, dict):
        rd = {k: v for k, v in rule_d.items() if v is not None}
        rd["id"] = slugify(rd.get("id") or rd.get("name") or proposal.title)
        rd.setdefault("name", rd["id"])
        try:
            update["suggested_rule"] = Rule.model_validate(rd)
        except Exception:  # noqa: BLE001 - a malformed draft must not crash codify
            pass
    ex_d = data.get("exemplar")
    if isinstance(ex_d, dict) and ex_d.get("code"):
        ed = {k: v for k, v in ex_d.items() if v is not None}
        ed.setdefault("id", f"ex-{update.get('suggested_rule').id}"
                      if update.get("suggested_rule") else f"ex-{slugify(proposal.title)}")
        ed.setdefault("intent", proposal.title)
        if update.get("suggested_rule"):
            ed.setdefault("convention_id", None)
        try:
            update["suggested_exemplar"] = Exemplar.model_validate(ed)
        except Exception:  # noqa: BLE001
            pass
    return proposal.model_copy(update=update) if update else proposal


def draft_proposal(
    proposal: CodifyProposal, llm: LLMClient, *, kb: Kb | None = None, model: str = MID
) -> CodifyProposal:
    """Use the LLM to draft a concrete Rule (+ optional Exemplar) for a proposal."""
    existing = kb.rules.get(proposal.rule_id) if (kb and proposal.rule_id) else None
    resp = llm.generate(system=DRAFT_SYSTEM, prompt=build_draft_prompt(proposal, existing), model=model)
    return _parse_drafted(resp.text, proposal)


def draft_proposals(
    proposals: list[CodifyProposal], llm: LLMClient, *, kb: Kb | None = None, model: str = MID
) -> list[CodifyProposal]:
    return [draft_proposal(p, llm, kb=kb, model=model) for p in proposals]


def save_proposals(proposals: list[CodifyProposal], layout: RepoLayout) -> list[str]:
    """Persist proposals to ``.rubric/proposals/`` for human review (not auto-merged into the KB)."""
    layout.proposals_dir.mkdir(parents=True, exist_ok=True)
    paths: list[str] = []
    for i, p in enumerate(proposals):
        path = layout.proposals_dir / f"{i:02d}-{slugify(p.title)[:50]}.json"
        write_model(p, path)
        paths.append(str(path))
    return paths
