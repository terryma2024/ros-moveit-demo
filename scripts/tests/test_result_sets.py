"""Fixture-only checks of scripts/gate/result_sets.py (serial-versus-parallel equivalence of the Host gate)."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

GATE = Path(__file__).resolve().parents[1] / "gate"
spec = importlib.util.spec_from_file_location("result_sets", GATE / "result_sets.py")
rs = importlib.util.module_from_spec(spec)
sys.modules["result_sets"] = rs
spec.loader.exec_module(rs)


def make(base, package, cases, time="1.0"):
    pdir = base / package
    (pdir / "Testing" / "20260101-0000").mkdir(parents=True)
    (pdir / "Testing" / "20260101-0000" / "Test.xml").write_text(
        '<Site><Testing><Test Status="passed"><Name>t1</Name></Test></Testing></Site>')
    (pdir / "test_results" / package).mkdir(parents=True)
    xml = "".join(f'<testcase classname="{c}" name="{n}" time="{time}">{extra}</testcase>' for c, n, extra in cases)
    (pdir / "test_results" / package / "a.gtest.xml").write_text(f"<testsuites><testsuite>{xml}</testsuite></testsuites>")


def test_identical_trees_with_different_times_compare_equal(tmp_path):
    make(tmp_path / "a", "p", [("S", "x", ""), ("S", "y", "<skipped/>")], time="1.0")
    make(tmp_path / "b", "p", [("S", "x", ""), ("S", "y", "<skipped/>")], time="9.0")
    a = rs.collect(tmp_path / "a")
    assert rs.compare(a, rs.collect(tmp_path / "b")) == []
    assert a["p"]["cases"]["p/a.gtest.xml::S::y"] == "skipped"


def test_a_missing_case_a_changed_result_and_a_missing_package_are_reported(tmp_path):
    make(tmp_path / "a", "p", [("S", "x", ""), ("S", "y", "")])
    make(tmp_path / "a", "q", [("S", "z", "")])
    make(tmp_path / "b", "p", [("S", "x", '<failure message="m"/>')])
    text = "\n".join(rs.compare(rs.collect(tmp_path / "a"), rs.collect(tmp_path / "b")))
    assert "q: only in A" in text
    assert "S::y" in text and "A=passed B=None" in text
    assert "S::x" in text and "B=failed" in text


def test_duplicate_cases_are_both_kept(tmp_path):
    make(tmp_path, "p", [("S", "x", ""), ("S", "x", "")])
    assert len(rs.collect(tmp_path)["p"]["cases"]) == 2


def test_cli_round_trip(tmp_path):
    make(tmp_path / "a", "p", [("S", "x", "")])
    out = tmp_path / "o.json"
    assert rs.main(["collect", "--build-base", str(tmp_path / "a"), "--out", str(out)]) == 0
    assert rs.main(["compare", str(out), str(out)]) == 0
    assert json.loads(out.read_text())["p"]["ctest"] == {"t1": "passed"}
