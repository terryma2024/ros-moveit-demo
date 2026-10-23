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


# --- two ctest phases of one package in the same minute (so101_teleop serial then parallel) --------------------------------------------------

def ctest_phase(base, package, names, tag="20260101-0000"):
    """What one `ctest` run leaves: Testing/TAG (the newest tag) and Testing/<tag>/Test.xml, overwritten when the minute is the same."""
    testing = base / package / "Testing"
    (testing / tag).mkdir(parents=True, exist_ok=True)
    (testing / "TAG").write_text(tag + "\n")
    tests = "".join(f'<Test Status="passed"><Name>{n}</Name></Test>' for n in names)
    (testing / tag / "Test.xml").write_text(f"<Site><Testing>{tests}</Testing></Site>")


def test_a_second_phase_in_the_same_minute_overwrites_the_first_without_preserve(tmp_path):
    ctest_phase(tmp_path, "p", ["serial1", "serial2"])
    ctest_phase(tmp_path, "p", ["par1"])
    assert list(rs.collect(tmp_path)["p"]["ctest"]) == ["par1"]


def test_preserve_keeps_every_phase_so_the_union_is_the_serial_set(tmp_path):
    ctest_phase(tmp_path, "p", ["serial1", "serial2"])
    assert rs.main(["preserve", "--build-base", str(tmp_path), "--package", "p", "--tag", "serial"]) == 0
    ctest_phase(tmp_path, "p", ["par1", "par2"])
    assert rs.main(["preserve", "--build-base", str(tmp_path), "--package", "p", "--tag", "parallel"]) == 0
    assert sorted(rs.collect(tmp_path)["p"]["ctest"]) == ["par1", "par2", "serial1", "serial2"]
    serial = tmp_path / "s"
    ctest_phase(serial, "p", ["serial1", "serial2", "par1", "par2"])
    assert rs.compare(rs.collect(serial), rs.collect(tmp_path)) == []


def test_preserve_is_idempotent_and_a_phase_name_is_not_reused(tmp_path):
    ctest_phase(tmp_path, "p", ["a"])
    assert rs.main(["preserve", "--build-base", str(tmp_path), "--package", "p", "--tag", "x"]) == 0
    assert rs.main(["preserve", "--build-base", str(tmp_path), "--package", "p", "--tag", "x"]) == 0
    ctest_phase(tmp_path, "p", ["b"])
    assert rs.main(["preserve", "--build-base", str(tmp_path), "--package", "p", "--tag", "x"]) == 2
    assert (tmp_path / "p" / "Testing" / "20260101-0000-x" / "Test.xml").read_text().count("<Name>a</Name>") == 1


def test_preserve_refuses_a_package_without_a_ctest_run(tmp_path):
    (tmp_path / "p").mkdir()
    assert rs.main(["preserve", "--build-base", str(tmp_path), "--package", "p", "--tag", "x"]) == 2


def test_the_extra_phase_summary_counts_a_preserved_copy_of_the_newest_phase_once(tmp_path):
    import subprocess
    ctest_phase(tmp_path, "p", ["serial1"])
    rs.main(["preserve", "--build-base", str(tmp_path), "--package", "p", "--tag", "serial"])
    ctest_phase(tmp_path, "p", ["par1", "par2"])
    rs.main(["preserve", "--build-base", str(tmp_path), "--package", "p", "--tag", "parallel"])
    log = tmp_path / "result.log"
    log.write_text("Summary: 2 tests, 0 errors, 0 failures, 0 skipped\n")
    out = subprocess.run(["python3", "-I", str(GATE / "ctest_extra_phases.py"), str(tmp_path), str(log)], capture_output=True, text=True).stdout
    assert "[colcon 2 + older ctest phases 1]" in out and out.count("older ctest phase, not read") == 1
