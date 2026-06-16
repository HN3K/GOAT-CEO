"""Deterministic gate — compose existing tools, never reimplement them (DESIGN P5).

Each ``ToolAdapter`` wraps an external analyzer (Ruff, ast-grep, …) as a subprocess
and maps its output to ``Finding``s. The gate runs the available adapters over a
target and aggregates a ``GateResult``; absent tools are recorded, never fatal.
Deterministic findings are the BLOCKING hard gate (DESIGN P3).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from rubric.contracts import Enforcement, Finding, GateResult, Rule, Severity
from rubric.paths import RepoLayout


@runtime_checkable
class ToolAdapter(Protocol):
    name: str

    def available(self) -> bool: ...

    def run(self, target: str, rules: list[Rule]) -> list[Finding]: ...


def _which(binary: str) -> bool:
    return shutil.which(binary) is not None


# --------------------------------------------------------------------------- #
# Ruff — real, pip-installable (one concrete deterministic engine)
# --------------------------------------------------------------------------- #
class RuffAdapter:
    """Runs Ruff over Python targets using the repo's Ruff config (tool-default)."""

    name = "ruff"

    def __init__(self, ruff_bin: str = "ruff", enforcement: Enforcement = Enforcement.BLOCKING) -> None:
        self.ruff_bin = ruff_bin
        self.enforcement = enforcement

    def available(self) -> bool:
        return _which(self.ruff_bin)

    def run(self, target: str, rules: list[Rule] | None = None) -> list[Finding]:
        if Path(target).suffix != ".py":   # Ruff is Python-only; never lint other files
            return []
        proc = subprocess.run(
            [self.ruff_bin, "check", "--output-format", "json", str(target)],
            capture_output=True, text=True, encoding="utf-8",
        )
        try:
            items = json.loads(proc.stdout or "[]")
        except json.JSONDecodeError:
            return []
        out: list[Finding] = []
        for it in items:
            loc = it.get("location") or {}
            out.append(Finding(
                source="ruff", rule_id=it.get("code"), enforcement=self.enforcement,
                severity=Severity.ERROR, message=it.get("message", ""),
                path=it.get("filename"), line=loc.get("row")))
        return out


# --------------------------------------------------------------------------- #
# ast-grep — external binary; runs the KB's own structural patterns
# --------------------------------------------------------------------------- #
class AstGrepAdapter:
    """Runs each KB rule whose ``tool == 'ast-grep'`` as an ast-grep pattern search."""

    name = "ast-grep"

    def __init__(self, ast_grep_bin: str | None = None) -> None:
        self.ast_grep_bin = ast_grep_bin or ("sg" if _which("sg") else "ast-grep")

    def available(self) -> bool:
        return _which("sg") or _which("ast-grep")

    def run(self, target: str, rules: list[Rule] | None = None) -> list[Finding]:
        out: list[Finding] = []
        for r in [r for r in (rules or []) if r.tool == "ast-grep" and r.spec]:
            proc = subprocess.run(
                [self.ast_grep_bin, "run", "--pattern", r.spec, "--json", str(target)],
                capture_output=True, text=True, encoding="utf-8",
            )
            try:
                matches = json.loads(proc.stdout or "[]")
            except json.JSONDecodeError:
                continue
            for m in matches:
                start = (m.get("range") or {}).get("start") or {}
                line0 = start.get("line")
                out.append(Finding(
                    source="ast-grep", rule_id=r.id, enforcement=r.enforcement,
                    severity=Severity.ERROR, message=r.intent,
                    path=m.get("file"),
                    line=(line0 + 1) if isinstance(line0, int) else None,  # ast-grep is 0-indexed
                    quote=m.get("text")))
        return out


# --------------------------------------------------------------------------- #
# Rubric-native structural checks (tiny; not a reimplemented linter)
# --------------------------------------------------------------------------- #
class RubricBuiltinAdapter:
    """Trivial structural checks rubric owns (e.g. colocated-test file existence)."""

    name = "rubric"

    def available(self) -> bool:
        return True

    def run(self, target: str, rules: list[Rule] | None = None) -> list[Finding]:
        out: list[Finding] = []
        p = Path(target)
        for r in [r for r in (rules or []) if r.tool == "rubric"]:
            if r.spec == "colocated-test" and p.suffix in (".ts", ".tsx") and ".test." not in p.name:
                sibling = p.with_name(f"{p.stem}.test{p.suffix}")
                if not sibling.exists():
                    out.append(Finding(
                        source="rubric", rule_id=r.id, enforcement=r.enforcement,
                        severity=Severity.WARNING, message=r.intent, path=str(p)))
        return out


# --------------------------------------------------------------------------- #
# Generic config-driven adapter — wrap ANY linter without writing code
# --------------------------------------------------------------------------- #
def _dig(obj, dotted: str):
    cur = obj
    for key in dotted.split("."):
        cur = cur.get(key) if isinstance(cur, dict) else None
    return cur


@dataclass
class CommandSpec:
    """Declarative config to wrap an external linter as an adapter (no code).

    ``command`` uses a ``{target}`` placeholder. ``fmt`` is ``"json"`` (a flat list
    of objects, fields mapped by dotted path) or ``"regex"`` (named groups
    ``path``/``line``/``message``/``code``). This is how a new stack's tooling
    (ESLint via ``--format unix``, mypy, etc.) is added — by config.
    """

    name: str
    command: list[str]
    bin: str | None = None
    enforcement: Enforcement = Enforcement.BLOCKING
    severity: Severity = Severity.ERROR
    fmt: str = "json"
    json_list_path: str | None = None
    fields: dict[str, str] = field(default_factory=lambda: {
        "message": "message", "path": "filename", "line": "location.row", "code": "code"})
    regex: str | None = None


class CommandAdapter:
    """Runs a CommandSpec over a target and maps output to Findings."""

    def __init__(self, spec: CommandSpec) -> None:
        self.spec = spec
        self.name = spec.name

    def available(self) -> bool:
        return _which(self.spec.bin or self.spec.command[0])

    def run(self, target: str, rules: list[Rule] | None = None) -> list[Finding]:
        cmd = [a.replace("{target}", str(target)) for a in self.spec.command]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        if self.spec.fmt == "regex":
            return self._parse_regex(proc.stdout)
        return self._parse_json(proc.stdout)

    def _finding(self, *, message, path=None, line=None, code=None) -> Finding:
        return Finding(
            source=self.name, rule_id=code, enforcement=self.spec.enforcement,
            severity=self.spec.severity, message=message or "",
            path=path, line=line if isinstance(line, int) else None)

    def _parse_json(self, stdout: str) -> list[Finding]:
        try:
            data = json.loads(stdout or "[]")
        except json.JSONDecodeError:
            return []
        items = _dig(data, self.spec.json_list_path) if self.spec.json_list_path else data
        if not isinstance(items, list):
            return []
        f = self.spec.fields
        out: list[Finding] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            out.append(self._finding(
                message=str(_dig(it, f.get("message", "message")) or ""),
                path=_dig(it, f["path"]) if f.get("path") else None,
                line=_dig(it, f["line"]) if f.get("line") else None,
                code=_dig(it, f["code"]) if f.get("code") else None))
        return out

    def _parse_regex(self, stdout: str) -> list[Finding]:
        if not self.spec.regex:
            return []
        out: list[Finding] = []
        for m in re.finditer(self.spec.regex, stdout or "", re.MULTILINE):
            g = m.groupdict()
            ln = g.get("line")
            out.append(self._finding(
                message=(g.get("message") or "").strip(), path=g.get("path"),
                line=int(ln) if ln and ln.isdigit() else None, code=g.get("code")))
        return out


def load_command_adapters(config_path: str | Path) -> list[CommandAdapter]:
    """Load CommandAdapters from a JSON config (a list of CommandSpec dicts)."""
    p = Path(config_path)
    if not p.exists():
        return []
    raw = json.loads(p.read_text(encoding="utf-8"))
    specs = raw.get("tools", raw) if isinstance(raw, dict) else raw
    out: list[CommandAdapter] = []
    for d in specs:
        d = dict(d)
        if "enforcement" in d:
            d["enforcement"] = Enforcement(d["enforcement"])
        if "severity" in d:
            d["severity"] = Severity(d["severity"])
        out.append(CommandAdapter(CommandSpec(**d)))
    return out


# --------------------------------------------------------------------------- #
# Gate runner
# --------------------------------------------------------------------------- #
def default_adapters(repo: str = ".") -> list[ToolAdapter]:
    """The standard adapter set: Ruff + ast-grep + rubric builtin + any ``.rubric/tools.json``."""
    extra = load_command_adapters(RepoLayout(repo).rubric_dir / "tools.json")
    return [RuffAdapter(), AstGrepAdapter(), RubricBuiltinAdapter(), *extra]


def run_gate(
    target: str, adapters: list[ToolAdapter], rules: list[Rule] | None = None
) -> GateResult:
    """Run available adapters over ``target``; record missing tools, aggregate findings."""
    findings: list[Finding] = []
    ran: list[str] = []
    missing: list[str] = []
    for adapter in adapters:
        if adapter.available():
            findings.extend(adapter.run(target, rules or []))
            ran.append(adapter.name)
        else:
            missing.append(adapter.name)
    return GateResult(target=str(target), findings=findings, tools_run=ran, tools_missing=missing)
