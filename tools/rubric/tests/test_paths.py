"""Phase 0 gate: KB + repo layout conventions."""

import pytest

from rubric.paths import KbLayout, RepoLayout, slugify


@pytest.mark.parametrize("raw, expected", [
    ("My Team Conventions!", "my-team-conventions"),
    ("  No Default Exports  ", "no-default-exports"),
])
def test_slugify(raw, expected):
    assert slugify(raw) == expected


def test_slugify_empty_raises():
    with pytest.raises(ValueError):
        slugify("!!!")


def test_kb_layout(tmp_path):
    kb = KbLayout(tmp_path / "kb")
    assert kb.rules_dir == kb.root / "rules"
    assert kb.exemplars_dir == kb.root / "exemplars"
    assert kb.conventions_dir == kb.root / "conventions"
    assert kb.manifest_path.name == "rubric.kb.json"
    assert kb.rule_path("r1") == kb.root / "rules" / "r1.json"
    assert kb.exemplar_path("e1") == kb.root / "exemplars" / "e1.json"
    kb.ensure()
    assert kb.rules_dir.is_dir() and kb.exemplars_dir.is_dir() and kb.conventions_dir.is_dir()


def test_repo_layout(tmp_path):
    repo = RepoLayout(tmp_path / "repo")
    assert repo.rubric_dir == repo.repo_root / ".rubric"
    assert repo.index_dir == repo.repo_root / ".rubric" / "index"
    repo.ensure()
    assert repo.index_dir.is_dir()
