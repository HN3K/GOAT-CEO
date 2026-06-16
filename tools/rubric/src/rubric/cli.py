"""rubric CLI — `context`, `check`, `review`, `enforce`, `kb`.

`check`/`enforce` exit non-zero on a blocking failure so rubric works as a CI gate
or pre-commit hook. `review` is advisory and never fails the build.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rubric.gate import default_adapters, run_gate
from rubric.kb import Kb
from rubric.llm import MID
from rubric.orchestrate import build_context, enforce, language_of
from rubric.paths import KbLayout

DEFAULT_KB = "kb"


def _load_kb(kb_dir: str) -> Kb:
    return Kb.load(KbLayout(kb_dir))


def _default_adapters(repo: str = "."):
    return default_adapters(repo)


def _print_findings(findings, label: str) -> None:
    if not findings:
        print(f"  ({label}: none)")
        return
    for f in findings:
        loc = f":{f.line}" if f.line else ""
        print(f"  [{f.source} {f.rule_id or ''}] {f.message} ({f.path or ''}{loc})")


def _make_llm():
    from rubric.llm import ClaudeCLIClient

    return ClaudeCLIClient()


def cmd_context(args) -> int:
    from rubric.index import load_components
    from rubric.paths import RepoLayout

    components = load_components(RepoLayout(args.repo))
    print(build_context(args.task, _load_kb(args.kb), language=args.language,
                        components=components, k=args.k))
    return 0


def cmd_index(args) -> int:
    from rubric.index import index_repo, save_index
    from rubric.paths import RepoLayout

    layout = RepoLayout(args.repo)
    components, hashes = index_repo(args.repo)
    save_index(components, hashes, layout)
    print(f"indexed {len(components)} reusable component(s) from {len(hashes)} file(s)")
    print(f"-> {layout.components_path}")
    return 0


def cmd_check(args) -> int:
    kb = _load_kb(args.kb)
    files = list(args.files)
    if args.changed:
        from rubric.integration import git_changed_files

        files += git_changed_files(args.repo)
    # only gate recognized code files — never lint docs/data/config (e.g. .txt, .json)
    files = [f for f in files if Path(f).is_file() and language_of(f) is not None]
    if not files:
        print("no code files to check")
        return 0

    adapters = _default_adapters(args.repo)
    overall_pass = True
    for f in files:
        lang = language_of(f)
        rules = kb.rules_for_language(lang) if lang else list(kb.rules.values())
        res = run_gate(f, adapters, rules)
        print(f"{'PASS' if res.passed else 'FAIL'}  {f}  (ran: {','.join(res.tools_run) or 'none'})")
        _print_findings(res.blocking, "blocking")
        overall_pass = overall_pass and res.passed
    return 0 if overall_pass else 1


def cmd_init(args) -> int:
    from rubric.index import index_repo, save_index
    from rubric.integration import CI_SNIPPET, scaffold_claude, scaffold_repo
    from rubric.paths import RepoLayout

    created = scaffold_repo(args.repo, kb=args.kb)
    if not args.no_claude:
        created += scaffold_claude(args.repo, kb=args.kb)
    for c in created:
        print(f"created {c}")
    if not created:
        print("already initialized")

    components, hashes = index_repo(args.repo)
    save_index(components, hashes, RepoLayout(args.repo))
    print(f"indexed {len(components)} reusable component(s) from {len(hashes)} file(s)")
    print()
    print(CI_SNIPPET.format(kb=args.kb))
    if not args.no_claude:
        print("# Claude Code: PostToolUse + SessionStart hooks, /rubric skill, and the")
        print("# rubric-reviewer subagent are wired in .claude/ (rubric must be on PATH).")
    return 0


def cmd_hook(args) -> int:
    from rubric.hook import main as hook_main

    return hook_main(["--kb", args.kb, "--repo", args.repo])


def cmd_review(args) -> int:
    v = enforce(args.file, _load_kb(args.kb), adapters=_default_adapters(),
                llm=_make_llm(), model=args.model, verify=args.verify)
    print("advisory review:")
    _print_findings(v.advisory, "advisory")
    return 0  # advisory never fails the build


def cmd_enforce(args) -> int:
    llm = None if args.no_llm else _make_llm()
    v = enforce(args.file, _load_kb(args.kb), adapters=_default_adapters(), llm=llm,
                model=args.model, verify=args.verify)
    print(f"verdict: {'PASS' if v.passed else 'FAIL'}")
    print("blocking:")
    _print_findings(v.blocking, "blocking")
    print("advisory:")
    _print_findings(v.advisory, "advisory")
    return 0 if v.passed else 1


def cmd_codify(args) -> int:
    from rubric.codify import draft_proposals, propose_codifications, save_proposals
    from rubric.paths import RepoLayout

    kb = _load_kb(args.kb)
    llm = None if args.no_llm else _make_llm()
    advisory = []
    for f in args.files:
        if Path(f).is_file() and language_of(f) is not None:
            v = enforce(f, kb, adapters=_default_adapters(args.repo), llm=llm,
                        model=args.model, verify=not args.no_llm)
            advisory += v.advisory
    proposals = propose_codifications(advisory, threshold=args.threshold)
    if not proposals:
        print(f"no recurring findings at threshold {args.threshold} "
              f"({len(advisory)} advisory finding(s) seen)")
        return 0
    if args.draft and llm is not None:
        proposals = draft_proposals(proposals, llm, kb=kb, model=args.model)

    print(f"{len(proposals)} codify proposal(s) from {len(advisory)} advisory finding(s):\n")
    for p in proposals:
        print(f"- [{p.kind}] {p.title}  (x{p.occurrences})")
        print(f"    {p.rationale}")
        for e in p.evidence:
            print(f"    · {e}")
        if p.suggested_rule:
            r = p.suggested_rule
            print(f"    DRAFT rule: {r.id} ({r.kind.value}/{r.enforcement.value}) — {r.intent}")
        if p.suggested_exemplar:
            print(f"    DRAFT exemplar: {p.suggested_exemplar.title}")
    if args.write:
        for path in save_proposals(proposals, RepoLayout(args.repo)):
            print(f"\nwrote {path}")
    return 0


def cmd_measure(args) -> int:
    from rubric.contracts import AdherenceReport, read_model, write_model
    from rubric.measure import measure, report_delta

    kb = _load_kb(args.kb)
    files = list(args.files)
    if args.changed:
        from rubric.integration import git_changed_files

        files += git_changed_files(args.repo)
    files = [f for f in files if Path(f).is_file() and language_of(f) is not None]
    llm = _make_llm() if args.llm else None
    rep = measure(files, kb, _default_adapters(args.repo), llm=llm, model=args.model, verify=args.verify)

    print(f"adherence over {rep.target}  (metrics: {rep.metrics_tool or 'unavailable'})")
    print(f"  gate-pass rate     : {rep.gate_pass_rate:.0%}  ({rep.blocking_total} blocking)")
    print(f"  blocking per KLOC  : {rep.blocking_per_kloc:.1f}")
    print(f"  advisory findings  : {rep.advisory_total}")
    print(f"  LOC total          : {rep.loc_total}")
    print(f"  max complexity     : {rep.complexity_max if rep.complexity_max is not None else 'n/a'}")

    if args.baseline and Path(args.baseline).is_file():
        delta = report_delta(read_model(AdherenceReport, args.baseline), rep)
        print("\ndelta vs baseline (negative bloat/complexity = improvement):")
        for k, v in delta.items():
            print(f"  {k}: {v:+}" if isinstance(v, (int, float)) else f"  {k}: {v}")
    if args.save:
        write_model(rep, args.save)
        print(f"\nsaved report -> {args.save}")
    return 0


def cmd_kb(args) -> int:
    kb = _load_kb(args.kb)
    print(f"KB '{kb.name}' v{kb.version}: {len(kb.conventions)} conventions, "
          f"{len(kb.rules)} rules, {len(kb.exemplars)} exemplars")
    for c in kb.conventions.values():
        print(f"- {c.id}: {c.name}  (rules={c.rule_ids}, exemplars={c.exemplar_ids})")
    return 0


def _add_kb(p):
    p.add_argument("--kb", default=DEFAULT_KB, help="conventions KB directory (default: ./kb)")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="rubric", description="Ground AI coding agents in your standards.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("context", help="render the pre-generation grounding block for a task")
    p.add_argument("task")
    p.add_argument("--language")
    p.add_argument("--repo", default=".", help="repo root (auto-loads .rubric/index components for reuse)")
    p.add_argument("-k", type=int, default=5)
    _add_kb(p)
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("index", help="build the codebase-plane index of reusable components")
    p.add_argument("--repo", default=".")
    p.set_defaults(func=cmd_index)

    p = sub.add_parser("check", help="deterministic gate (blocking) over files")
    p.add_argument("files", nargs="*", help="files to check (or use --changed)")
    p.add_argument("--changed", action="store_true", help="check git-staged changed files")
    p.add_argument("--repo", default=".", help="repo root (for --changed + .rubric/tools.json)")
    _add_kb(p)
    p.set_defaults(func=cmd_check)

    p = sub.add_parser("init", help="scaffold .rubric/ + git pre-commit + Claude Code integration")
    p.add_argument("--repo", default=".")
    p.add_argument("--kb", default=".rubric/kb")
    p.add_argument("--no-claude", action="store_true",
                   help="skip the native Claude Code hooks/skill/subagent scaffolding")
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("review", help="LLM advisory review (subscription-billed)")
    p.add_argument("file")
    p.add_argument("--model", default=MID)
    p.add_argument("--verify", action="store_true",
                   help="adversarially verify advisory findings (drop false positives)")
    _add_kb(p)
    p.set_defaults(func=cmd_review)

    p = sub.add_parser("enforce", help="gate + review -> verdict (exit 1 if blocking)")
    p.add_argument("file")
    p.add_argument("--model", default=MID)
    p.add_argument("--no-llm", action="store_true", help="deterministic gate only")
    p.add_argument("--verify", action="store_true",
                   help="adversarially verify advisory findings (drop false positives)")
    _add_kb(p)
    p.set_defaults(func=cmd_enforce)

    p = sub.add_parser("hook", help="Claude Code hook bridge (reads event JSON on stdin)")
    p.add_argument("--repo", default=".")
    _add_kb(p)
    p.set_defaults(func=cmd_hook)

    p = sub.add_parser("codify", help="propose KB standards from recurring verified findings")
    p.add_argument("files", nargs="+", help="files to scan for recurring drift")
    p.add_argument("--threshold", type=int, default=3, help="min recurrences to propose (default 3)")
    p.add_argument("--repo", default=".", help="repo root (for .rubric/tools.json + proposals)")
    p.add_argument("--draft", action="store_true", help="LLM-draft a concrete rule/exemplar per proposal")
    p.add_argument("--write", action="store_true", help="persist proposals to .rubric/proposals/")
    p.add_argument("--model", default=MID)
    p.add_argument("--no-llm", action="store_true", help="deterministic findings only (no LLM/verify)")
    _add_kb(p)
    p.set_defaults(func=cmd_codify)

    p = sub.add_parser("measure", help="quantify adherence + anti-bloat (gate-pass, complexity, LOC)")
    p.add_argument("files", nargs="*", help="files to measure (or use --changed)")
    p.add_argument("--changed", action="store_true", help="measure git-staged changed files")
    p.add_argument("--repo", default=".", help="repo root (for --changed + .rubric/tools.json)")
    p.add_argument("--baseline", help="a saved report JSON to diff against (before/after)")
    p.add_argument("--save", help="write the report JSON to this path")
    p.add_argument("--llm", action="store_true", help="include LLM advisory findings (subscription)")
    p.add_argument("--verify", action="store_true", help="adversarially verify advisory (with --llm)")
    p.add_argument("--model", default=MID)
    _add_kb(p)
    p.set_defaults(func=cmd_measure)

    p = sub.add_parser("kb", help="list KB contents")
    _add_kb(p)
    p.set_defaults(func=cmd_kb)

    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args) or 0


if __name__ == "__main__":
    sys.exit(main())
