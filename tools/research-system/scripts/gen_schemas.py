"""Generate JSON Schema files from the pydantic contracts.

Run: ``python scripts/gen_schemas.py``
Writes one ``<model>.schema.json`` per top-level contract into
``src/research_system/schemas/``. A test asserts these stay in sync with the
models, so regenerate and commit whenever a contract changes.
"""

from __future__ import annotations

import json
from pathlib import Path

from research_system.contracts import (
    Claim,
    Manifest,
    QuestionsFile,
    SourceMeta,
)

# Top-level (file-backed) contracts only. Nested models (SubQuestion, JudgeVote,
# SourceCatalogEntry) appear inside these schemas via $defs.
TOP_LEVEL = {
    "questions": QuestionsFile,
    "manifest": Manifest,
    "source_meta": SourceMeta,
    "claim": Claim,
}

SCHEMA_DIR = Path(__file__).resolve().parent.parent / "src" / "research_system" / "schemas"


def render() -> dict[str, str]:
    """Return {filename: json_text} for each top-level contract schema."""
    out: dict[str, str] = {}
    for name, model in TOP_LEVEL.items():
        schema = model.model_json_schema()
        out[f"{name}.schema.json"] = json.dumps(schema, indent=2, sort_keys=True) + "\n"
    return out


def write() -> None:
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for filename, text in render().items():
        (SCHEMA_DIR / filename).write_text(text, encoding="utf-8")
        print(f"wrote {SCHEMA_DIR / filename}")


if __name__ == "__main__":
    write()
