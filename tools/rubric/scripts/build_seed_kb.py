"""Build a real starter conventions KB and save it to ./kb.

Three conventions grounded in well-evidenced practice (factory.ai's agent-lint
categories: grep-ability, testability, error semantics). Two are deterministic
(blocking), one is LLM-judged (advisory) — demonstrating the boundary split.

Run: python scripts/build_seed_kb.py
"""

from __future__ import annotations

from pathlib import Path

from rubric.contracts import Convention, Enforcement, Exemplar, Rule, RuleKind
from rubric.kb import Kb
from rubric.paths import KbLayout

REPO = Path(__file__).resolve().parent.parent


def build() -> Kb:
    kb = Kb(name="rubric-starter", version="0.1.0")

    # 1. Named exports (grep-ability) — DETERMINISTIC / BLOCKING -------------- #
    kb.add_rule(Rule(
        id="no-default-export",
        name="No default exports",
        intent="Named exports are greppable: `export const Foo` and `import { Foo }` are precisely "
               "searchable by agents and tools; default exports are not.",
        kind=RuleKind.DETERMINISTIC, enforcement=Enforcement.BLOCKING,
        tool="ast-grep", spec="export default $X", languages=["ts", "tsx", "js"],
        tags=["imports", "grep-ability"]))
    kb.add_exemplar(Exemplar(
        id="ex-named-export", title="Named export", intent="how we export",
        language="ts", code="export const UserService = createService();",
        tags=["imports", "grep-ability"], convention_id="named-exports"))
    kb.add_convention(Convention(
        id="named-exports", name="Named exports only",
        intent="Every module uses named exports so the codebase is greppable and refactor-safe.",
        rule_ids=["no-default-export"], exemplar_ids=["ex-named-export"],
        tags=["imports", "grep-ability"]))

    # 2. Colocated tests (testability) — DETERMINISTIC / BLOCKING ------------- #
    kb.add_rule(Rule(
        id="require-colocated-test",
        name="Colocated unit test",
        intent="Each logic file has a sibling `*.test.ts`, so tests are discoverable and "
               "one-to-one with the code they cover.",
        kind=RuleKind.DETERMINISTIC, enforcement=Enforcement.BLOCKING,
        tool="rubric", spec="colocated-test", languages=["ts", "tsx"],
        tags=["testability"]))
    kb.add_exemplar(Exemplar(
        id="ex-colocated-test", title="Colocated test layout", intent="how we place tests",
        language="ts", code="// user-service.ts  ->  user-service.test.ts (sibling)",
        tags=["testability"], convention_id="colocated-tests"))
    kb.add_convention(Convention(
        id="colocated-tests", name="Colocated tests",
        intent="Unit tests live next to the code they cover, one-to-one.",
        rule_ids=["require-colocated-test"], exemplar_ids=["ex-colocated-test"],
        tags=["testability"]))

    # 3. Error handling (semantics) — LLM / ADVISORY ------------------------- #
    kb.add_rule(Rule(
        id="appropriate-error-type",
        name="Appropriate, non-swallowed errors",
        intent="Errors use the project's taxonomy and are never silently swallowed; whether an "
               "error is handled APPROPRIATELY is a semantic judgment a linter cannot make.",
        kind=RuleKind.LLM, enforcement=Enforcement.ADVISORY,
        tool=None,
        spec="Review error handling: are errors typed with the project's taxonomy, propagated or "
             "handled deliberately (never silently swallowed), and is the chosen handling "
             "appropriate for the call site? Cite the exact line.",
        languages=["ts", "tsx", "py"], tags=["errors", "semantics"]))
    kb.add_exemplar(Exemplar(
        id="ex-error-handling", title="Typed, non-swallowed error", intent="how we handle errors",
        language="ts",
        code=("try {\n  return await repo.load(id);\n} catch (e) {\n"
              "  throw new NotFoundError(`user ${id}`, { cause: e });\n}"),
        tags=["errors", "semantics"], convention_id="error-handling"))
    kb.add_convention(Convention(
        id="error-handling", name="Deliberate error handling",
        intent="Errors are typed, deliberate, and never silently swallowed.",
        rule_ids=["appropriate-error-type"], exemplar_ids=["ex-error-handling"],
        tags=["errors", "semantics"]))

    return kb


def main() -> None:
    kb = build()
    layout = KbLayout(REPO / "kb")
    kb.save(layout)
    problems = Kb.load(layout).validate_refs()
    print(f"seed KB -> {layout.root}  ({len(kb.rules)} rules, {len(kb.exemplars)} exemplars, "
          f"{len(kb.conventions)} conventions)")
    print("ref check:", "clean" if not problems else problems)


if __name__ == "__main__":
    main()
