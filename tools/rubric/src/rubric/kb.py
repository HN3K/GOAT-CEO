"""Knowledge-base store — load/save the portable conventions plane (DESIGN.md §2).

On disk, the KB is just inspectable JSON: ``rules/<id>.json``, ``exemplars/<id>.json``,
``conventions/<id>.json``, plus a ``rubric.kb.json`` manifest. Files on disk are the
source of truth (loaded by glob); the manifest is a regenerated convenience index.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rubric.contracts import (
    Convention,
    Exemplar,
    KbManifest,
    Rule,
    read_model,
    write_model,
)
from rubric.paths import KbLayout


@dataclass
class Kb:
    name: str = "kb"
    version: str = "0.1.0"
    rules: dict[str, Rule] = field(default_factory=dict)
    exemplars: dict[str, Exemplar] = field(default_factory=dict)
    conventions: dict[str, Convention] = field(default_factory=dict)

    # mutation ------------------------------------------------------------- #
    def add_rule(self, rule: Rule) -> Rule:
        self.rules[rule.id] = rule
        return rule

    def add_exemplar(self, exemplar: Exemplar) -> Exemplar:
        self.exemplars[exemplar.id] = exemplar
        return exemplar

    def add_convention(self, convention: Convention) -> Convention:
        self.conventions[convention.id] = convention
        return convention

    # query ---------------------------------------------------------------- #
    def rules_for_language(self, language: str) -> list[Rule]:
        """Rules that apply to ``language`` (empty ``languages`` = language-agnostic)."""
        return [r for r in self.rules.values() if not r.languages or language in r.languages]

    def exemplars_for_tags(self, tags: list[str]) -> list[Exemplar]:
        want = set(tags)
        return [e for e in self.exemplars.values() if want & set(e.tags)]

    def manifest(self) -> KbManifest:
        return KbManifest(
            name=self.name,
            version=self.version,
            rule_ids=sorted(self.rules),
            exemplar_ids=sorted(self.exemplars),
            convention_ids=sorted(self.conventions),
        )

    # persistence ---------------------------------------------------------- #
    def save(self, layout: KbLayout) -> None:
        layout.ensure()
        for r in self.rules.values():
            write_model(r, layout.rule_path(r.id))
        for e in self.exemplars.values():
            write_model(e, layout.exemplar_path(e.id))
        for c in self.conventions.values():
            write_model(c, layout.convention_path(c.id))
        write_model(self.manifest(), layout.manifest_path)

    @classmethod
    def load(cls, layout: KbLayout) -> "Kb":
        name, version = "kb", "0.1.0"
        if layout.manifest_path.exists():
            m = read_model(KbManifest, layout.manifest_path)
            name, version = m.name, m.version
        rules = _load_dir(layout.rules_dir, Rule)
        exemplars = _load_dir(layout.exemplars_dir, Exemplar)
        conventions = _load_dir(layout.conventions_dir, Convention)
        return cls(name=name, version=version, rules=rules,
                   exemplars=exemplars, conventions=conventions)

    def validate_refs(self) -> list[str]:
        """Return human-readable problems: conventions referencing missing rules/exemplars."""
        problems: list[str] = []
        for c in self.conventions.values():
            for rid in c.rule_ids:
                if rid not in self.rules:
                    problems.append(f"convention {c.id}: missing rule {rid}")
            for eid in c.exemplar_ids:
                if eid not in self.exemplars:
                    problems.append(f"convention {c.id}: missing exemplar {eid}")
        return problems


def _load_dir(directory, cls):
    out = {}
    if directory.is_dir():
        for p in sorted(directory.glob("*.json")):
            out[p.stem] = read_model(cls, p)
    return out
