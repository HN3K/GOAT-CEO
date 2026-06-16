"""Codebase-plane indexer — extract reusable components so the model reuses, not reinvents.

This is the per-repo half of the two-plane KB (DESIGN §2) and the engine behind P4
("reuse is retrieval"): unless the existing components relevant to a task are surfaced
*before* generation, the model reimplements them — missing dependency context drives
redundant reinvention, and the fix is providing the real building blocks [s033].

Extraction is **symbol-level, not chunk-based**: the corpus is explicit that chunking
fragments coherent units and makes the model hallucinate plausible-but-nonexistent methods
instead of reusing real ones [s033]. So we parse each file and emit one ``Component`` per
top-level function/class with its real signature — deterministic, via the Python stdlib
``ast`` (no new dependency; "compose, don't rebuild"). Other languages plug in as extractors.

The index is written to the codebase plane (``.rubric/index/components.json``) alongside a
per-file content hash so staleness is detectable.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Protocol, runtime_checkable

from rubric.contracts import Component
from rubric.paths import RepoLayout

_DEFAULT_EXCLUDE = (".git", "__pycache__", ".venv", "venv", "node_modules",
                    "build", "dist", ".rubric", ".ruff_cache", ".pytest_cache",
                    "tests", "test", "__tests__")


def _is_test_file(name: str) -> bool:
    """Test code is not reusable API — keep it out of the reuse catalog."""
    stem = name.rsplit(".", 1)[0]
    return (name.startswith("test_") or stem.endswith("_test")
            or ".test" in name or ".spec" in name or name == "conftest.py")


@runtime_checkable
class Extractor(Protocol):
    language: str
    suffixes: tuple[str, ...]

    def extract(self, rel_path: str, source: str) -> list[Component]: ...


# --------------------------------------------------------------------------- #
# Python — stdlib ast (symbol-level, dependency-free)
# --------------------------------------------------------------------------- #
class PythonExtractor:
    """Top-level public functions and classes, with real signatures, via ``ast``."""

    language = "py"
    suffixes = (".py",)

    def extract(self, rel_path: str, source: str) -> list[Component]:
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []  # un-parseable file: skip, never crash the index
        out: list[Component] = []
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name.startswith("_"):
                    continue  # private surface — not the reusable API
                out.append(self._function(rel_path, node))
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                out.append(self._class(rel_path, node))
        return out

    def _function(self, rel_path: str, node) -> Component:
        prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
        ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
        signature = f"{prefix} {node.name}({ast.unparse(node.args)}){ret}"
        return Component(id=f"{rel_path}::{node.name}", name=node.name,
                         signature=signature, path=rel_path,
                         summary=_docstring_summary(node))

    def _class(self, rel_path: str, node) -> Component:
        bases = ", ".join(ast.unparse(b) for b in node.bases)
        signature = f"class {node.name}({bases})" if bases else f"class {node.name}"
        methods = [n.name for n in node.body
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and not n.name.startswith("_")]
        summary = _docstring_summary(node)
        if methods:
            summary = (summary + " " if summary else "") + f"methods: {', '.join(methods)}"
        return Component(id=f"{rel_path}::{node.name}", name=node.name,
                         signature=signature, path=rel_path, summary=summary or None)


def _docstring_summary(node) -> str | None:
    doc = ast.get_docstring(node)
    return doc.strip().splitlines()[0].strip() if doc else None


DEFAULT_EXTRACTORS: tuple[Extractor, ...] = (PythonExtractor(),)


# --------------------------------------------------------------------------- #
# Indexer
# --------------------------------------------------------------------------- #
def _iter_code_files(root: Path, suffixes: set[str], exclude: tuple[str, ...]):
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix not in suffixes:
            continue
        if any(part in exclude for part in p.relative_to(root).parts):
            continue
        if _is_test_file(p.name):
            continue
        yield p


def index_repo(
    repo_root: str = ".", *,
    extractors: tuple[Extractor, ...] = DEFAULT_EXTRACTORS,
    exclude: tuple[str, ...] = _DEFAULT_EXCLUDE,
) -> tuple[list[Component], dict[str, str]]:
    """Walk ``repo_root`` and extract reusable components. Returns ``(components, file_hashes)``."""
    root = Path(repo_root)
    by_suffix = {sfx: ex for ex in extractors for sfx in ex.suffixes}
    components: list[Component] = []
    hashes: dict[str, str] = {}
    for path in _iter_code_files(root, set(by_suffix), exclude):
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        rel = path.relative_to(root).as_posix()
        hashes[rel] = hashlib.sha1(source.encode("utf-8")).hexdigest()
        components.extend(by_suffix[path.suffix].extract(rel, source))
    return components, hashes


def save_index(components: list[Component], hashes: dict[str, str], layout: RepoLayout) -> None:
    layout.ensure()
    payload = {"components": [c.model_dump() for c in components], "files": hashes}
    layout.components_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_components(layout: RepoLayout) -> list[Component]:
    """Load the codebase-plane component catalog (empty if not yet indexed)."""
    p = layout.components_path
    if not p.exists():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [Component.model_validate(c) for c in raw.get("components", [])]


def stale_files(repo_root: str, layout: RepoLayout, *,
                extractors: tuple[Extractor, ...] = DEFAULT_EXTRACTORS,
                exclude: tuple[str, ...] = _DEFAULT_EXCLUDE) -> list[str]:
    """Files whose current content hash differs from the saved index (added/changed/removed)."""
    p = layout.components_path
    if not p.exists():
        return []
    try:
        saved = json.loads(p.read_text(encoding="utf-8")).get("files", {})
    except json.JSONDecodeError:
        return []
    _, current = index_repo(repo_root, extractors=extractors, exclude=exclude)
    added_or_removed = set(saved) ^ set(current)
    changed = {f for f in (set(saved) & set(current)) if saved[f] != current[f]}
    return sorted(added_or_removed | changed)
