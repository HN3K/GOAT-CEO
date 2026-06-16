"""Folder conventions for a research subject (DESIGN.md §4).

A subject's entire state lives under ``<research_root>/<slug>/``. Every path a
pipeline component touches is derived here so the layout has one definition.
"""

from __future__ import annotations

import re
from pathlib import Path

_SLUG_STRIP = re.compile(r"[^a-z0-9]+")


def slugify(name: str) -> str:
    """Turn a research subject into a filesystem-safe slug.

    >>> slugify("Accurately Performing Research with AI!")
    'accurately-performing-research-with-ai'
    """
    s = _SLUG_STRIP.sub("-", name.strip().lower()).strip("-")
    if not s:
        raise ValueError(f"subject {name!r} produced an empty slug")
    return s


class SubjectLayout:
    """Resolves every on-disk path for one research subject.

    ``slug`` is used verbatim as the directory name; pass an already-slugified
    value or use :meth:`from_subject` to slugify a human title.
    """

    def __init__(self, research_root: str | Path, slug: str) -> None:
        self.research_root = Path(research_root)
        self.slug = slug
        self.root = self.research_root / slug

    @classmethod
    def from_subject(cls, research_root: str | Path, subject: str) -> "SubjectLayout":
        return cls(research_root, slugify(subject))

    # directories ---------------------------------------------------------- #
    @property
    def sources_dir(self) -> Path:
        return self.root / "sources"

    # per-source files ----------------------------------------------------- #
    def source_md(self, source_id: str) -> Path:
        return self.sources_dir / f"{source_id}.md"

    def source_meta(self, source_id: str) -> Path:
        return self.sources_dir / f"{source_id}.meta.json"

    # subject-level files -------------------------------------------------- #
    @property
    def questions_path(self) -> Path:
        return self.root / "questions.json"

    @property
    def manifest_path(self) -> Path:
        return self.root / "manifest.json"

    @property
    def claims_path(self) -> Path:
        return self.root / "claims.jsonl"

    @property
    def gaps_path(self) -> Path:
        return self.root / "gaps.md"

    @property
    def synthesis_path(self) -> Path:
        return self.root / "synthesis.md"

    # helpers -------------------------------------------------------------- #
    def ensure(self) -> "SubjectLayout":
        """Create the subject and sources directories if absent."""
        self.sources_dir.mkdir(parents=True, exist_ok=True)
        return self

    def __repr__(self) -> str:  # pragma: no cover - debug aid
        return f"SubjectLayout(root={self.root!s})"
