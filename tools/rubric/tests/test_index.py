"""Codebase-plane indexer — symbol-level component extraction for reuse retrieval (P4)."""

from rubric.index import (
    PythonExtractor,
    index_repo,
    load_components,
    save_index,
    stale_files,
)
from rubric.paths import RepoLayout

SRC = '''\
"""module."""

CONST = 1


def make_user(name: str, age: int = 0) -> dict:
    """Create a user record."""
    return {"name": name, "age": age}


async def fetch(url: str):
    ...


def _private_helper():
    ...


class UserService:
    """Manages users."""

    def create(self, name): ...
    def _internal(self): ...
'''


# --------------------------------------------------------------------------- #
# extractor
# --------------------------------------------------------------------------- #
def test_extracts_public_functions_with_signatures():
    comps = {c.name: c for c in PythonExtractor().extract("svc.py", SRC)}
    assert comps["make_user"].signature == "def make_user(name: str, age: int=0) -> dict"
    assert comps["make_user"].summary == "Create a user record."
    assert comps["fetch"].signature == "async def fetch(url: str)"
    assert comps["make_user"].id == "svc.py::make_user"


def test_skips_private_names():
    names = {c.name for c in PythonExtractor().extract("svc.py", SRC)}
    assert "_private_helper" not in names


def test_class_signature_and_method_summary():
    cls = next(c for c in PythonExtractor().extract("svc.py", SRC) if c.name == "UserService")
    assert cls.signature == "class UserService"
    assert "Manages users." in cls.summary and "create" in cls.summary
    assert "_internal" not in cls.summary       # private methods excluded


def test_syntax_error_is_skipped_not_fatal():
    assert PythonExtractor().extract("bad.py", "def (: oops") == []


# --------------------------------------------------------------------------- #
# repo indexing + persistence + staleness
# --------------------------------------------------------------------------- #
def test_index_repo_walks_and_excludes(tmp_path):
    (tmp_path / "a.py").write_text(SRC, encoding="utf-8")
    pkg = tmp_path / "__pycache__"
    pkg.mkdir()
    (pkg / "junk.py").write_text("def ignored(): ...", encoding="utf-8")
    comps, hashes = index_repo(str(tmp_path))
    names = {c.name for c in comps}
    assert "make_user" in names and "UserService" in names
    assert "ignored" not in names               # excluded dir skipped
    assert "a.py" in hashes


def test_index_excludes_test_code(tmp_path):
    (tmp_path / "service.py").write_text(SRC, encoding="utf-8")
    (tmp_path / "test_service.py").write_text("def test_make_user(): ...", encoding="utf-8")
    (tmp_path / "service_test.py").write_text("def helper_in_test(): ...", encoding="utf-8")
    comps, _ = index_repo(str(tmp_path))
    names = {c.name for c in comps}
    assert "make_user" in names                 # real API kept
    assert "test_make_user" not in names and "helper_in_test" not in names  # test code excluded


def test_save_and_load_roundtrip(tmp_path):
    (tmp_path / "a.py").write_text(SRC, encoding="utf-8")
    comps, hashes = index_repo(str(tmp_path))
    layout = RepoLayout(str(tmp_path))
    save_index(comps, hashes, layout)
    assert layout.components_path.exists()
    loaded = load_components(layout)
    assert {c.name for c in loaded} == {c.name for c in comps}


def test_load_missing_index_is_empty(tmp_path):
    assert load_components(RepoLayout(str(tmp_path))) == []


def test_stale_files_detects_change(tmp_path):
    f = tmp_path / "a.py"
    f.write_text(SRC, encoding="utf-8")
    layout = RepoLayout(str(tmp_path))
    comps, hashes = index_repo(str(tmp_path))
    save_index(comps, hashes, layout)
    assert stale_files(str(tmp_path), layout) == []     # fresh
    f.write_text(SRC + "\ndef added(): ...\n", encoding="utf-8")
    assert "a.py" in stale_files(str(tmp_path), layout)  # changed -> stale
