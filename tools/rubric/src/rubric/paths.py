"""On-disk layout for rubric's two planes (DESIGN.md §2).

Conventions plane (portable): a KB directory of rules/, exemplars/, conventions/.
Codebase plane (per-repo): a ``.rubric/`` directory inside the target repository.
"""

from __future__ import annotations

import re
from pathlib import Path

_SLUG = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    s = _SLUG.sub("-", name.strip().lower()).strip("-")
    if not s:
        raise ValueError(f"{name!r} produced an empty slug")
    return s


class KbLayout:
    """Resolves paths for a portable conventions knowledge base."""

    def __init__(self, kb_root: str | Path) -> None:
        self.root = Path(kb_root)

    @property
    def rules_dir(self) -> Path:
        return self.root / "rules"

    @property
    def exemplars_dir(self) -> Path:
        return self.root / "exemplars"

    @property
    def conventions_dir(self) -> Path:
        return self.root / "conventions"

    @property
    def manifest_path(self) -> Path:
        return self.root / "rubric.kb.json"

    def rule_path(self, rule_id: str) -> Path:
        return self.rules_dir / f"{rule_id}.json"

    def exemplar_path(self, exemplar_id: str) -> Path:
        return self.exemplars_dir / f"{exemplar_id}.json"

    def convention_path(self, convention_id: str) -> Path:
        return self.conventions_dir / f"{convention_id}.json"

    def ensure(self) -> "KbLayout":
        for d in (self.rules_dir, self.exemplars_dir, self.conventions_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self


class RepoLayout:
    """Resolves the per-repo ``.rubric/`` codebase-plane paths."""

    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)

    @property
    def rubric_dir(self) -> Path:
        return self.repo_root / ".rubric"

    @property
    def index_dir(self) -> Path:
        return self.rubric_dir / "index"

    @property
    def components_path(self) -> Path:
        """The per-repo codebase-plane index of reusable components (DESIGN §2)."""
        return self.index_dir / "components.json"

    @property
    def proposals_dir(self) -> Path:
        """Codify proposals pending human approval before promotion to the KB (DESIGN P8)."""
        return self.rubric_dir / "proposals"

    def ensure(self) -> "RepoLayout":
        self.index_dir.mkdir(parents=True, exist_ok=True)
        return self
