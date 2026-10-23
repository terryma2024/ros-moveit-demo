"""Fixture-only checks of scripts/gate/teleop_pytest.py: the selection of the so101_teleop modules for one xdist run, and the comparison of the
executed tests of two runs."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

GATE = Path(__file__).resolve().parents[1] / "gate"
spec = importlib.util.spec_from_file_location("teleop_pytest", GATE / "teleop_pytest.py")
tp = importlib.util.module_from_spec(spec)
sys.modules["teleop_pytest"] = tp
spec.loader.exec_module(tp)

CMAKE = """
  so101_add_pytest_test(test_a test/a/test_a.py)
  so101_add_pytest_test(test_b test/b/test_b.py)
  so101_add_pytest_test( test_c   test/test_c.py )
  # so101_add_pytest_test(test_commented test/nothing.py) is still matched by the same regex the ctest registration test uses
"""


def package(tmp_path, files=("test/a/test_a.py", "test/b/test_b.py", "test/test_c.py", "test/nothing.py")):
    for name in files:
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / name).write_text("")
    return tmp_path


def test_the_paths_are_the_registered_files_in_registration_order_without_the_serial_ones(tmp_path):
    root = package(tmp_path)
    assert tp.selected_paths(CMAKE, root) == [str(root / "test/a/test_a.py"), str(root / "test/b/test_b.py"),
                                             str(root / "test/test_c.py"), str(root / "test/nothing.py")]
    assert tp.selected_paths(CMAKE, root, ["test_b", "test_commented"]) == [str(root / "test/a/test_a.py"), str(root / "test/test_c.py")]


def test_an_unregistered_exclusion_a_missing_file_and_duplicates_are_refused(tmp_path):
    root = package(tmp_path, files=("test/a/test_a.py", "test/b/test_b.py", "test/test_c.py"))
    with pytest.raises(tp.SelectionError, match="excluded but not registered: test_typo"):
        tp.selected_paths(CMAKE, root, ["test_typo"])
    with pytest.raises(tp.SelectionError, match="registered file missing: test/nothing.py"):
        tp.selected_paths(CMAKE, root)
    root = package(tmp_path)
    with pytest.raises(tp.SelectionError, match="duplicate registration name: test_a"):
        tp.selected_paths(CMAKE + "so101_add_pytest_test(test_a test/b/test_b.py)\n", root)
    with pytest.raises(tp.SelectionError, match="duplicate registration path: test/a/test_a.py"):
        tp.selected_paths(CMAKE + "so101_add_pytest_test(test_d test/a/test_a.py)\n", root)


def write_xunit(path, cases):
    body = "".join(
        f'<testcase classname="{classname}" name="{name}">' + {"pass": "", "fail": "<failure/>", "error": "<error/>", "skipped": "<skipped/>"}[status]
        + "</testcase>" for classname, name, status in cases)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'<?xml version="1.0"?><testsuites><testsuite name="s">{body}</testsuite></testsuites>')


def test_the_executed_tests_of_many_files_and_of_one_file_are_the_same_set(tmp_path):
    cases = [("so101_teleop.test.a", "test_one", "pass"), ("so101_teleop.test.a", "test_two", "fail"),
             ("so101_teleop.test.b", "test_three[x]", "skipped"), ("so101_teleop.test.b", "test_four", "error")]
    write_xunit(tmp_path / "many" / "test_a.xunit.xml", cases[:2])
    write_xunit(tmp_path / "many" / "test_b.xunit.xml", cases[2:])
    write_xunit(tmp_path / "one" / "so101_teleop_xdist.xunit.xml", cases)
    many, one = tp.executed_tests(tmp_path / "many"), tp.executed_tests(tmp_path / "one")
    assert many == one and len(many) == 4 and set(many.values()) == {"pass", "fail", "skipped", "error"}
    assert tp.compare_sets(many, one) == []


def test_a_missing_test_or_a_different_result_is_a_difference(tmp_path):
    a = {"x::1": "pass", "x::2": "pass", "x::3": "fail"}
    b = {"x::1": "pass", "x::3": "pass", "x::4": "pass"}
    assert tp.compare_sets(a, b) == ["only in A: x::2", "only in B: x::4", "x::3: A fail B pass"]


def test_a_test_id_seen_in_two_files_is_refused(tmp_path):
    write_xunit(tmp_path / "a.xunit.xml", [("c", "t", "pass")])
    write_xunit(tmp_path / "b.xunit.xml", [("c", "t", "pass")])
    with pytest.raises(tp.SelectionError, match="test id seen twice: c::t"):
        tp.executed_tests(tmp_path)


def test_the_command_line_exit_codes(tmp_path):
    a, b = tmp_path / "a.json", tmp_path / "b.json"
    a.write_text(json.dumps({"x": "pass"}))
    b.write_text(json.dumps({"x": "pass"}))
    run = lambda *args: subprocess.run([sys.executable, "-I", str(GATE / "teleop_pytest.py"), *args], capture_output=True, text=True)
    assert run("compare", str(a), str(b)).returncode == 0
    b.write_text(json.dumps({"x": "fail"}))
    done = run("compare", str(a), str(b))
    assert done.returncode == 1 and "x: A pass B fail" in done.stdout
    assert run("paths", "--cmake", str(tmp_path / "none"), "--root", str(tmp_path)).returncode == 2


def test_the_real_registrations_select_every_ordinary_module_of_the_package():
    root = GATE.parents[1] / "src" / "so101_teleop"
    cmake = (root / "CMakeLists.txt").read_text()
    paths = tp.selected_paths(cmake, root)
    assert len(paths) == len(tp.registered(cmake)) > 100 and all(Path(path).is_file() for path in paths)
