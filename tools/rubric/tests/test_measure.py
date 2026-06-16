"""Adherence + anti-bloat measurement — gate-pass rate, complexity, LOC, before/after deltas."""

from rubric.contracts import Enforcement, Finding, Rule, RuleKind, Severity
from rubric.kb import Kb
from rubric.measure import (
    ComplexityResult,
    RadonAdapter,
    measure,
    measure_file,
    report_delta,
)


class FakeAdapter:
    def __init__(self, name, findings):
        self.name = name
        self._f = findings

    def available(self):
        return True

    def run(self, target, rules):
        return list(self._f)


class FakeMetric:
    name = "fake-metric"

    def __init__(self, result):
        self._r = result

    def available(self):
        return True

    def measure(self, path, code):
        return self._r


def _kb():
    kb = Kb(name="t")
    kb.add_rule(Rule(id="r", name="r", intent="i", kind=RuleKind.DETERMINISTIC,
                     enforcement=Enforcement.BLOCKING, tool="fake"))
    return kb


def _block():
    return Finding(source="fake", enforcement=Enforcement.BLOCKING, severity=Severity.ERROR, message="bad")


# --------------------------------------------------------------------------- #
# per-file
# --------------------------------------------------------------------------- #
def test_measure_file_counts_loc_and_gate(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("a = 1\n\nb = 2\n", encoding="utf-8")    # 2 non-blank lines
    fm = measure_file(str(f), _kb(), [FakeAdapter("fake", [])],
                      metric=FakeMetric(ComplexityResult(sloc=2, complexity_max=1, complexity_avg=1.0)))
    assert fm.loc == 2 and fm.sloc == 2 and fm.complexity_max == 1
    assert fm.gate_passed is True and fm.blocking_count == 0


def test_measure_file_records_blocking(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n", encoding="utf-8")
    fm = measure_file(str(f), _kb(), [FakeAdapter("fake", [_block()])], metric=FakeMetric(None))
    assert fm.gate_passed is False and fm.blocking_count == 1
    assert fm.complexity_max is None                       # metric returned None -> recorded absent


# --------------------------------------------------------------------------- #
# aggregate report
# --------------------------------------------------------------------------- #
def test_report_aggregates(tmp_path):
    good = tmp_path / "ok.py"
    good.write_text("a = 1\n", encoding="utf-8")
    bad = tmp_path / "bad.py"
    bad.write_text("b = 2\n", encoding="utf-8")
    adapters = [FakeAdapter("fake", [])]
    # one clean, one failing -> use distinct adapter sets via two measures merged
    rep = measure([str(good)], _kb(), adapters, metric=FakeMetric(None))
    assert rep.gate_pass_rate == 1.0 and rep.loc_total == 1
    rep2 = measure([str(bad)], _kb(), [FakeAdapter("fake", [_block()])], metric=FakeMetric(None))
    assert rep2.gate_pass_rate == 0.0 and rep2.blocking_total == 1
    assert rep2.blocking_per_kloc == 1000.0               # 1 blocking / 1 loc * 1000


def test_measure_skips_non_code_files(tmp_path):
    doc = tmp_path / "notes.txt"
    doc.write_text("hello", encoding="utf-8")
    rep = measure([str(doc)], _kb(), [FakeAdapter("fake", [])], metric=FakeMetric(None))
    assert rep.files == []


# --------------------------------------------------------------------------- #
# before/after delta
# --------------------------------------------------------------------------- #
def test_report_delta_shows_improvement(tmp_path):
    f = tmp_path / "m.py"
    f.write_text("x = 1\n", encoding="utf-8")
    before = measure([str(f)], _kb(), [FakeAdapter("fake", [_block()])],
                     metric=FakeMetric(ComplexityResult(complexity_max=10)))
    after = measure([str(f)], _kb(), [FakeAdapter("fake", [])],
                    metric=FakeMetric(ComplexityResult(complexity_max=4)))
    delta = report_delta(before, after)
    assert delta["blocking_total"] == -1                  # one fewer violation
    assert delta["complexity_max"] == -6                  # complexity dropped
    assert delta["gate_pass_rate"] == 1.0                 # 0% -> 100%


# --------------------------------------------------------------------------- #
# real radon (anti-bloat signal)
# --------------------------------------------------------------------------- #
def test_radon_adapter_live(tmp_path):
    adapter = RadonAdapter()
    if not adapter.available():
        return                                            # radon optional; skip if absent
    code = "def f(x):\n    if x:\n        return 1\n    return 0\n"
    res = adapter.measure(str(tmp_path / "x.py"), code)
    assert res is not None and res.complexity_max >= 2 and res.sloc >= 3
    assert adapter.measure(str(tmp_path / "x.txt"), code) is None   # non-python -> None
