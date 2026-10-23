"""Fixture-only checks of the parallel upstream tests of the Host gate: scripts/gate/upstream_groups.py, upstream_slot.zsh, upstream_stage.zsh."""

from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pytest

GATE = Path(__file__).resolve().parents[1] / "gate"
spec = importlib.util.spec_from_file_location("upstream_groups", GATE / "upstream_groups.py")
ug = importlib.util.module_from_spec(spec)
sys.modules["upstream_groups"] = ug
spec.loader.exec_module(ug)
ZSH = shutil.which("zsh")
needs_zsh = pytest.mark.skipif(ZSH is None, reason="zsh is not installed")

# 8 performance cores with two threads (CPUs 0-15) and 8 efficiency cores (CPUs 16-23): the shape of the antzb CPU
HYBRID = "\n".join(["# CPU,CORE,MAXMHZ"] + [f"{cpu},{cpu // 2},{5300 + 100 * (cpu // 8 == 1)}" for cpu in range(16)]
                   + [f"{cpu},{8 + cpu - 16},4200" for cpu in range(16, 24)])
GROUPS = """# comment
a | 1 | pkg1 | -R ^(t_slow|t_other)$
b | 1 | pkg1 | rest
b | 1 | pkg2 | rest
c | 2 | pkg3 | -R ^t_x$
c | 2 | pkg3 | rest
"""


def parse(text=GROUPS):
    return ug.parse_groups(text)


def cpus_of(spec_text):
    return {int(c) for part in spec_text.split(",") for c in range(int(part.split("-")[0]), int(part.split("-")[-1]) + 1)}


# --- the group file ---------------------------------------------------------------------------------------------------

def test_the_shipped_group_file_parses_and_names_only_the_three_upstream_packages():
    entries = ug.parse_groups((GATE / "upstream-groups.txt").read_text())
    assert {e[2] for e in entries} == {"controller_manager", "hardware_interface_testing", "joint_trajectory_controller"}
    assert sum(1 for e in entries if e[3] == "rest") == 3        # exactly one `rest` per package


@pytest.mark.parametrize("text", ["", "a | 1 | p", "A | 1 | p | rest", "a | 0 | p | rest", "a | 1 | p | -E x", "a | 1 | p | -R (",
                                  "a | 1 | p | rest\na | 2 | q | rest"])
def test_a_malformed_group_file_is_refused(text):
    with pytest.raises((ug.GroupError, Exception)):
        ug.parse_groups(text)


def test_a_regex_may_contain_a_bar_because_the_separator_has_blanks():
    assert parse()[0][3] == "-R ^(t_slow|t_other)$"


# --- CPUs -------------------------------------------------------------------------------------------------------------

def test_upstream_groups_get_whole_fast_cores_and_the_rest_is_everything_else():
    out = ug.allocate(parse(), ug.read_topology(HYBRID), 0.33)
    groups = {name: cpus_of(text) for name, text in out["groups"].items()}
    assert set(groups) == {"a", "b", "c"}
    everything = set().union(*groups.values()) | cpus_of(out["rest"])
    assert everything == set(range(24)) and not (set().union(*groups.values()) & cpus_of(out["rest"]))
    for cpus in groups.values():
        assert len(cpus) % 2 == 0 and all(cpu // 2 * 2 in cpus and cpu // 2 * 2 + 1 in cpus for cpu in cpus)    # both threads of each core
        assert all(cpu < 16 for cpu in cpus)                                                                      # performance cores first
    assert out["upstream_cpus"] == sum(len(c) for c in groups.values()) >= round(24 * 0.33)
    assert len(groups["c"]) > len(groups["a"])                      # weight 2 vs 1


def test_the_share_scales_the_upstream_cpus_and_every_group_keeps_a_core():
    topology = ug.read_topology(HYBRID)
    small = ug.allocate(parse(), topology, 0.01)
    assert all(len(cpus_of(text)) >= 2 for text in small["groups"].values())
    large = ug.allocate(parse(), topology, 0.6)
    assert large["upstream_cpus"] > small["upstream_cpus"] and cpus_of(large["rest"])


def test_too_few_cores_for_the_groups_are_refused():
    with pytest.raises(ug.GroupError, match="UPSTREAM_CPUS_INVALID"):
        ug.allocate(parse(), ug.read_topology("0,0,1\n1,0,1\n2,1,1\n3,1,1"), 0.5)


def test_cpu_lists_are_compact():
    assert ug.cpu_list([3, 1, 2, 7, 9, 10]) == "1-3,7,9-10"


# --- partition --------------------------------------------------------------------------------------------------------

def listing(*names):
    return "Test project /x\n" + "".join(f"  Test #{i}: {n}\n" for i, n in enumerate(names, 1)) + f"\nTotal Tests: {len(names)}\n"


def test_every_test_lands_in_exactly_one_group():
    names = {"pkg1": ug.ctest_names(listing("t_slow", "t_other", "t_a", "t_b")), "pkg2": ug.ctest_names(listing("t_c"))}
    entries = [e for e in parse() if e[2] in names]
    parts = ug.partition(entries, names)
    assert parts[("a", "pkg1")] == ("R", "^(t_slow|t_other)$")
    assert parts[("b", "pkg1")] == ("E", "^(t_other|t_slow)$")
    assert parts[("b", "pkg2")] == ("A", "")
    lines = ug.spec_lines(entries, parts)
    assert lines[0].split("\t") == ["a", "pkg1", "R", "^(t_slow|t_other)$"]


@pytest.mark.parametrize("names, code", [
    ({"pkg1": ["t_slow", "t_a"]}, "UPSTREAM_SELECTOR_STALE"),                       # t_other is gone: the group file is out of date
    ({"pkg1": ["t_slow", "t_other"]}, "UPSTREAM_REST_EMPTY"),
])
def test_a_stale_selector_or_an_empty_rest_is_refused(names, code):
    with pytest.raises(ug.GroupError, match=code):
        ug.partition([e for e in parse() if e[2] == "pkg1"], names)


def test_overlap_two_rests_and_an_ungrouped_package_are_refused():
    overlap = [("a", 1, "p", "-R ^t_.$"), ("b", 1, "p", "-R ^t_a$"), ("c", 1, "p", "rest")]
    with pytest.raises(ug.GroupError, match="UPSTREAM_SELECTOR_OVERLAP"):
        ug.partition(overlap, {"p": ["t_a", "t_b", "t_z"]})
    with pytest.raises(ug.GroupError, match="UPSTREAM_REST_NOT_ONE"):
        ug.partition([("a", 1, "p", "-R ^t_a$")], {"p": ["t_a", "t_b"]})
    with pytest.raises(ug.GroupError, match="UPSTREAM_PACKAGE_UNGROUPED"):
        ug.partition(parse(), {"other": ["t"]})


def test_the_shipped_groups_cover_the_known_upstream_tests(tmp_path):
    names = {"controller_manager": ["test_controller_manager", "test_controller_manager_srvs", "test_spawner_unspawner", "test_advanced_spawner",
                                    "test_hardware_spawner", "test_controllers_chaining_with_controller_manager"],
             "hardware_interface_testing": ["test_resource_manager", "test_resource_manager_prepare_perform_switch"],
             "joint_trajectory_controller": ["test_trajectory", "test_tolerances", "test_trajectory_controller", "test_trajectory_actions",
                                             "test_state_queue_publication", "test_load_joint_trajectory_controller"]}
    for package, tests in names.items():
        (tmp_path / f"{package}.txt").write_text(listing(*tests))
    done = subprocess.run([sys.executable, "-I", str(GATE / "upstream_groups.py"), "spec", "--groups", str(GATE / "upstream-groups.txt"),
                           "--package-lists", str(tmp_path)], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    rows = [line.split("\t") for line in done.stdout.splitlines()]
    assert {row[0] for row in rows} == {"slow-jtc", "slow-cm-a", "slow-cm-b", "other"}
    assert ["slow-jtc", "joint_trajectory_controller", "R", "^test_trajectory_actions$"] in rows


# --- executed sets ----------------------------------------------------------------------------------------------------

def write_build(base, package, phases, gtests):
    for tag, tests in phases.items():
        directory = base / package / "Testing" / tag
        directory.mkdir(parents=True)
        body = "".join(f'<Test Status="{status}"><Name>{name}</Name><Results><NamedMeasurement type="numeric/double" name="Execution Time">'
                       f"<Value>{seconds}</Value></NamedMeasurement></Results></Test>" for name, status, seconds in tests)
        (directory / "Test.xml").write_text(f"<Site><Testing>{body}</Testing></Site>")
        (base / package / "Testing" / "TAG").write_text(tag + "\n")
    results = base / package / "test_results" / package
    results.mkdir(parents=True)
    for name, count in gtests.items():
        (results / name).write_text(f'<testsuites tests="{count}"></testsuites>')


def test_sets_are_the_same_for_one_phase_and_for_the_tests_split_over_phases(tmp_path):
    one, split = tmp_path / "one", tmp_path / "split"
    tests = [("t_a", "passed", 1.5), ("t_b", "passed", 90.0), ("t_c", "passed", 3.0)]
    gtests = {"t_a.gtest.xml": 4, "t_b.gtest.xml": 10}
    write_build(one, "pkg", {"20261021-0100": tests}, gtests)
    write_build(split, "pkg", {"20261021-0100": tests[:1], "20261021-0102": tests[1:]}, gtests)
    a, b = ug.collect_sets(one, ["pkg"]), ug.collect_sets(split, ["pkg"])
    assert ug.compare_sets(a, b) == []
    assert a["pkg"]["ctest"] == {"t_a": "passed", "t_b": "passed", "t_c": "passed"} and a["pkg"]["gtest_cases"]["t_b.gtest.xml"] == 10


def test_a_missing_test_a_changed_status_and_a_changed_case_count_are_differences(tmp_path):
    ref, other = tmp_path / "ref", tmp_path / "other"
    write_build(ref, "pkg", {"20261021-0100": [("t_a", "passed", 1), ("t_b", "passed", 1)]}, {"x.gtest.xml": 4})
    write_build(other, "pkg", {"20261021-0100": [("t_a", "failed", 1)]}, {"x.gtest.xml": 3})
    problems = ug.compare_sets(ug.collect_sets(ref, ["pkg"]), ug.collect_sets(other, ["pkg"]))
    assert any("t_b" in p for p in problems) and any("t_a" in p and "failed" in p for p in problems) and any("x.gtest.xml" in p for p in problems)


def test_the_same_test_in_two_phases_is_flagged(tmp_path):
    write_build(tmp_path, "pkg", {"20261021-0100": [("t_a", "passed", 1)], "20261021-0102": [("t_a", "passed", 1)]}, {})
    assert ug.collect_sets(tmp_path, ["pkg"])["pkg"]["ctest"] == {"t_a": "duplicate"}


def test_timing_lists_the_slowest_tests_first(tmp_path):
    write_build(tmp_path, "pkg", {"20261021-0100": [("fast", "passed", 1.0), ("slow", "passed", 278.4), ("mid", "passed", 40.0)]}, {})
    assert [name for _, name, _ in ug.timing(tmp_path, ["pkg"], 2)["pkg"]] == ["slow", "mid"]


# --- the start slots --------------------------------------------------------------------------------------------------

@needs_zsh
def test_starts_of_one_package_are_serialised_and_spaced_while_other_packages_do_not_wait(tmp_path):
    script = f"source {GATE / 'upstream_slot.zsh'}; upstream_slot {tmp_path} $1; print -r -- $EPOCHSECONDS > {tmp_path}/started.$1.$2"
    env = {**os.environ, "UPSTREAM_SLOT_GAP_S": "2"}
    t0 = time.time()
    procs = [subprocess.Popen([ZSH, "-c", script, "zsh", package, str(i)], env=env) for i, package in enumerate(["p", "p", "p", "q"])]
    for proc in procs:
        assert proc.wait(30) == 0
    stamps = sorted(int((tmp_path / f"started.p.{i}").read_text()) for i in range(3))
    assert stamps[1] - stamps[0] >= 2 and stamps[2] - stamps[1] >= 2
    assert int((tmp_path / "started.q.3").read_text()) - int(t0) <= 1 or int((tmp_path / "started.q.3").read_text()) <= stamps[1]


# --- the stage --------------------------------------------------------------------------------------------------------

@pytest.fixture
def stage(tmp_path):
    """A fake build tree (ctest -N lists), a fake taskset and a fake part script that records what it was given."""
    build, run = tmp_path / "build", tmp_path / "run"
    run.mkdir()
    fake = tmp_path / "bin"
    fake.mkdir()
    (fake / "ctest").write_text('#!/bin/sh\ncat ctest-list.txt\n')
    (fake / "taskset").write_text('#!/bin/sh\nprintf "%s " "$@" > "$UPSTREAM_SPEC.taskset"\nshift 2\nexec "$@"\n')
    part = tmp_path / "part.zsh"
    part.write_text('print -r -- "$UPSTREAM_GROUP_DOMAIN $2" > $UPSTREAM_SPEC.part\n[[ -n $FAKE_FAIL && $2 == up-$FAKE_FAIL ]] && exit 1\nexit 0\n')
    lists = {"controller_manager": ["test_controller_manager", "test_controller_manager_srvs", "test_spawner_unspawner", "test_advanced_spawner",
                                    "test_hardware_spawner"],
             "hardware_interface_testing": ["test_resource_manager"],
             "joint_trajectory_controller": ["test_trajectory", "test_trajectory_actions", "test_trajectory_controller"]}
    for package, tests in lists.items():
        directory = build / "build" / package
        directory.mkdir(parents=True)
        (directory / "ctest-list.txt").write_text(listing(*tests))
    for tool in ("ctest", "taskset"):
        (fake / tool).chmod(0o755)
    cpus = tmp_path / "cpus.json"
    cpus.write_text(json.dumps({"groups": {"slow-jtc": "8-9", "slow-cm-a": "10-11", "slow-cm-b": "0-1", "other": "2-3"}, "rest": "4-7,12-23"}))

    def run_stage(**extra):
        env = {**os.environ, "GATE_HOST": "antzb", "GATE_BUILD": str(build), "GATE": str(tmp_path), "GATE_SCRATCH": str(tmp_path),
               "UPSTREAM_CPUS": str(cpus), "GATE_PART_SCRIPT": str(part), "GATE_TASKSET": str(fake / "taskset"),
               "PATH": f"{fake}:{os.environ['PATH']}", **extra}
        # ctest -N runs in each package's build directory
        return subprocess.run([ZSH, str(GATE / "upstream_stage.zsh"), str(run)], env=env, capture_output=True, text=True, cwd=tmp_path)
    return run, run_stage


@needs_zsh
def test_the_stage_starts_every_group_on_its_cpus_in_its_own_domain_and_finishes_with_done(stage):
    run, run_stage = stage
    done = run_stage()
    assert done.returncode == 0, done.stdout + done.stderr
    assert (run / "upstream.rc").read_text().strip() == "0" and (run / "upstream.done").exists()
    layout = dict(line.split()[0:2] for line in (run / "upstream-groups.txt").read_text().splitlines())
    assert layout == {"group=slow-jtc": "cpus=8-9", "group=slow-cm-a": "cpus=10-11", "group=slow-cm-b": "cpus=0-1", "group=other": "cpus=2-3"}
    domains = [line.split("domain=")[1] for line in (run / "upstream-groups.txt").read_text().splitlines()]
    assert sorted(domains) == ["223", "224", "225", "226"]
    for group, cpus in {"slow-jtc": "8-9", "other": "2-3"}.items():
        assert (run / "upstream-spec" / f"{group}.tsv.taskset").read_text().startswith(f"-c {cpus} zsh")
    assert "joint_trajectory_controller\tR\t^test_trajectory_actions$" in (run / "upstream-spec" / "slow-jtc.tsv").read_text()
    other = (run / "upstream-spec" / "other.tsv").read_text().splitlines()
    assert [row.split("\t")[1] for row in other] == ["hardware_interface_testing", "joint_trajectory_controller", "controller_manager"]


@needs_zsh
def test_a_failing_group_fails_the_stage_and_the_others_still_finish(stage):
    run, run_stage = stage
    done = run_stage(FAKE_FAIL="slow-cm-a")
    assert done.returncode == 1 and (run / "upstream.rc").read_text().strip() == "1" and (run / "upstream.done").exists()
    assert "slow-cm-a rc=1" in (run / "upstream-parts.rc.txt").read_text() and "other rc=0" in (run / "upstream-parts.rc.txt").read_text()


@needs_zsh
def test_a_group_file_that_no_longer_matches_the_tests_stops_the_stage_before_anything_runs(stage):
    run, run_stage = stage
    (run.parent / "build" / "build" / "joint_trajectory_controller" / "ctest-list.txt").write_text(listing("test_trajectory"))
    done = run_stage()
    assert done.returncode == 91 and (run / "upstream.rc").read_text().strip() == "91" and (run / "upstream.done").exists()
    assert not (run / "upstream-groups.txt").exists()


@needs_zsh
def test_skipped_decisions_leave_out_their_packages(stage):
    run, run_stage = stage
    done = run_stage(FAST_SKIP_ROS2_CONTROL="1")
    assert done.returncode == 0, done.stderr
    packages = {row.split("\t")[1] for tsv in (run / "upstream-spec").glob("*.tsv") if tsv.name != "all.tsv" for row in tsv.read_text().splitlines()}
    assert packages == {"joint_trajectory_controller"}
    nothing = run_stage(FAST_SKIP_ROS2_CONTROL="1", FAST_SKIP_JTC_UPSTREAM="1")
    assert nothing.returncode == 0 and (run / "upstream.done").exists()


@needs_zsh
@pytest.mark.parametrize("last,now,expected", [(0, 100, 0), (30, 40, 20), (44, 50, 10), (46, 50, 70), (59, 60, 60)])
def test_the_minute_rule_waits_for_the_first_tag_minute_after_the_last_start_plus_margin(last, now, expected):
    base = 1_700_000_040          # a whole minute
    env = {k: v for k, v in os.environ.items() if k != "UPSTREAM_SLOT_GAP_S"}
    out = subprocess.run([ZSH, "-c", f"source {GATE / 'upstream_slot.zsh'}; upstream_slot_delay {base + last} {base + now}"], env=env,
                         capture_output=True, text=True)
    assert int(out.stdout.strip()) == expected, out.stderr
