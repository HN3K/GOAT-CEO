"""Retrieve + assemble the ContextPack (DESIGN.md §3 component 1).

Selects the few most relevant exemplars, the applicable rules, and the existing
repo components to REUSE for a task — capped and ranked (≤k), because precise
contextual exemplars help and over-stuffing backfires (DESIGN P6). The
ContextPack is the artifact injected before the model writes; rendering it is how
reuse + conventions reach generation.
"""

from __future__ import annotations

import re

from rubric.contracts import Component, ContextPack, Exemplar, Rule
from rubric.kb import Kb

_TOKEN = re.compile(r"[a-z0-9]+")


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


def _rank(query: str, docs: list[tuple[str, str]], k: int) -> list[str]:
    """BM25-rank (id, text) docs by query; return top-k ids (k<=0 or empty → [])."""
    if not docs or k <= 0:
        return []
    from rank_bm25 import BM25Okapi

    bm25 = BM25Okapi([tokenize(text) for _, text in docs])
    scores = bm25.get_scores(tokenize(query))
    ranked = sorted(zip((i for i, _ in docs), scores), key=lambda t: t[1], reverse=True)
    return [i for i, _ in ranked[:k]]


def select_exemplars(kb: Kb, task: str, k: int = 5) -> list[Exemplar]:
    docs = [(e.id, f"{e.title} {e.intent} {' '.join(e.tags)} {e.code}") for e in kb.exemplars.values()]
    return [kb.exemplars[i] for i in _rank(task, docs, k)]


def select_rules(kb: Kb, language: str | None = None) -> list[Rule]:
    """All applicable rules (the standards to enforce). Rules are terse; not capped."""
    if language is None:
        return list(kb.rules.values())
    return kb.rules_for_language(language)


def select_components(components: list[Component], task: str, k: int = 5) -> list[Component]:
    docs = [(c.id, f"{c.name} {c.signature or ''} {c.summary or ''}") for c in components]
    order = _rank(task, docs, k)
    by_id = {c.id: c for c in components}
    return [by_id[i] for i in order]


def build_context_pack(
    task: str,
    kb: Kb,
    *,
    language: str | None = None,
    components: list[Component] | None = None,
    k: int = 5,
) -> ContextPack:
    return ContextPack(
        task=task,
        exemplars=select_exemplars(kb, task, k),
        rules=select_rules(kb, language),
        components=select_components(components or [], task, k),
    )


def render_context_pack(pack: ContextPack) -> str:
    """Render the pack as an injectable prompt block (conventions + exemplars + reuse)."""
    lines = [f"# Standards context for: {pack.task}", ""]

    if pack.rules:
        lines += ["## Conventions to follow", ""]
        for r in pack.rules:
            tag = "MUST" if r.enforcement.value == "blocking" else "should"
            lines.append(f"- ({tag}) **{r.name}** - {r.intent}")
        lines.append("")

    if pack.components:
        lines += ["## Existing components — REUSE these, do not reinvent", ""]
        for c in pack.components:
            sig = f" `{c.signature}`" if c.signature else ""
            where = f" ({c.path})" if c.path else ""
            lines.append(f"- **{c.name}**{sig}{where}{(' — ' + c.summary) if c.summary else ''}")
        lines.append("")

    if pack.exemplars:
        lines += ["## Canonical exemplars — match this style", ""]
        for e in pack.exemplars:
            lines += [f"### {e.title} ({e.language}) - {e.intent}",
                      f"```{e.language}", e.code, "```", ""]

    return "\n".join(lines).rstrip() + "\n"
