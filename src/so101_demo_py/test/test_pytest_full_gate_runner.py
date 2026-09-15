"""Focused contracts for the deterministic ordinary pytest gate runner."""

from pathlib import Path

import pytest
from tools.so101_pytest_gate import (
    SERIAL_MODULES,
    CoverageError,
    ProcessOutcome,
    assign_lpt,
    create_process_layout,
    discover_ordinary_modules,
    load_module_durations,
    split_lanes,
    validate_exact_coverage,
    validate_process_outcomes,
    validate_source_status,
    validate_worker_count,
)


def test_lpt_assignment_is_deterministic_and_balances_the_longest_module() -> None:
    modules = tuple(Path(f"test/test_{name}.py") for name in "abcd")
    durations = {
        modules[0]: 10.0,
        modules[1]: 8.0,
        modules[2]: 3.0,
        modules[3]: 1.0,
    }

    first = assign_lpt(modules, worker_count=2, durations=durations)
    second = assign_lpt(tuple(reversed(modules)), worker_count=2, durations=durations)

    assert first == second
    assert first == ((modules[0], modules[3]), (modules[1], modules[2]))


def test_lpt_uses_a_deterministic_fallback_without_timing_data() -> None:
    modules = tuple(Path(f"test/test_{name}.py") for name in "abc")

    assert assign_lpt(modules, worker_count=2, durations={}) == (
        (modules[0], modules[2]),
        (modules[1],),
    )
    assert load_module_durations(None, Path("test")) == {}


def test_historical_junit_durations_are_summed_by_whole_module(tmp_path: Path) -> None:
    junit = tmp_path / "history.xml"
    junit.write_text(
        "<testsuites><testsuite>\n"
        '<testcase classname="test.test_a" name="one" time="1.25"/>\n'
        '<testcase classname="test.test_a" name="two" time="0.75"/>\n'
        '<testcase classname="test.test_b.Case" name="three" time="3.5"/>\n'
        "</testsuite></testsuites>\n",
        encoding="utf-8",
    )

    assert load_module_durations(junit, Path("test")) == {
        Path("test/test_a.py"): 2.0,
        Path("test/test_b.py"): 3.5,
    }


def test_serial_lane_is_ordered_and_excluded_from_parallel_shards() -> None:
    modules = (
        Path("test/test_other.py"),
        Path("test/test_text_pick_agent_e2e_process.py"),
        Path("test/test_parallel_adaptive_integration.py"),
        Path("test/test_parallel_batch_resources.py"),
    )

    serial, parallel = split_lanes(modules)

    assert tuple(path.name for path in serial) == SERIAL_MODULES
    assert parallel == (Path("test/test_other.py"),)
    assert not set(serial) & set(parallel)


def test_exact_node_union_accepts_each_expected_node_once() -> None:
    expected = ("test/test_a.py::test_one", "test/test_b.py::test_two[x]")

    result = validate_exact_coverage(
        expected,
        ((expected[0],), (expected[1],)),
    )

    assert result["expected_count"] == 2
    assert result["actual_count"] == 2
    assert result["collection_sha256"]


@pytest.mark.parametrize(
    ("actual", "message"),
    (
        (("test/test_a.py::test_one",), "missing"),
        (
            ("test/test_a.py::test_one", "test/test_a.py::test_one"),
            "duplicate",
        ),
        (("test/test_a.py::test_one", "test/test_c.py::test_extra"), "unexpected"),
    ),
)
def test_exact_node_union_rejects_missing_duplicate_or_unexpected(
    actual: tuple[str, ...], message: str
) -> None:
    expected = ("test/test_a.py::test_one", "test/test_b.py::test_two")

    with pytest.raises(CoverageError, match=message):
        validate_exact_coverage(expected, (actual,))


def test_exact_node_union_rejects_benchmark_and_zero_collection() -> None:
    with pytest.raises(CoverageError, match="nonzero"):
        validate_exact_coverage((), ())
    with pytest.raises(CoverageError, match="benchmark"):
        validate_exact_coverage(
            ("benchmark_test/test_slow.py::test_model",),
            (("benchmark_test/test_slow.py::test_model",),),
        )


@pytest.mark.parametrize(
    "outcome",
    (
        ProcessOutcome("shard-1", 7, False, True, True),
        ProcessOutcome("shard-1", -9, True, True, True),
        ProcessOutcome("shard-1", 0, False, False, True),
        ProcessOutcome("shard-1", 0, False, True, False),
    ),
)
def test_shard_failures_timeouts_provenance_and_junit_fail_closed(
    outcome: ProcessOutcome,
) -> None:
    with pytest.raises(RuntimeError, match="shard-1"):
        validate_process_outcomes((outcome,))


def test_ordinary_discovery_excludes_benchmark_tree(tmp_path: Path) -> None:
    package = tmp_path / "package"
    ordinary = package / "test"
    benchmark = package / "benchmark_test"
    ordinary.mkdir(parents=True)
    benchmark.mkdir()
    (ordinary / "test_fast.py").write_text("def test_fast(): pass\n", encoding="utf-8")
    (benchmark / "test_slow.py").write_text("def test_slow(): pass\n", encoding="utf-8")

    modules = discover_ordinary_modules(package)

    assert modules == (ordinary / "test_fast.py",)
    assert all("benchmark_test" not in path.parts for path in modules)


def test_every_pytest_process_layout_has_isolated_fresh_paths(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()

    first = create_process_layout(run_root, "serial")
    second = create_process_layout(run_root, "shard-01")

    assert first.root != second.root
    for layout in (first, second):
        assert layout.tmp_dir.is_dir()
        assert layout.ros_home.is_dir()
        assert layout.ros_log_dir.is_dir()
        assert layout.environment["TMPDIR"] == str(layout.tmp_dir)
        assert layout.environment["TMP"] == str(layout.tmp_dir)
        assert layout.environment["TEMP"] == str(layout.tmp_dir)
        assert layout.environment["ROS_HOME"] == str(layout.ros_home)
        assert layout.environment["ROS_LOG_DIR"] == str(layout.ros_log_dir)
        assert layout.junit_path.parent == layout.root
        assert layout.log_path.parent == layout.root
        assert layout.ownership_path.parent == layout.root
    with pytest.raises(FileExistsError):
        create_process_layout(run_root, "serial")


@pytest.mark.parametrize("worker_count", (1, 2, 4))
def test_required_runtime_worker_counts_are_supported(worker_count: int) -> None:
    assert validate_worker_count(worker_count) == worker_count


@pytest.mark.parametrize("worker_count", (0, -1))
def test_nonpositive_worker_counts_are_rejected(worker_count: int) -> None:
    with pytest.raises(ValueError, match="worker"):
        validate_worker_count(worker_count)


def test_only_explicit_audit_paths_may_be_dirty() -> None:
    ledger = "docs/experiments/so101-pytest-parallel-gate-experiment-ledger.md"

    validate_source_status(f" M {ledger}", (ledger,), allow_dirty=False)
    with pytest.raises(RuntimeError, match="tools/runner.py"):
        validate_source_status(
            f" M {ledger}\n M tools/runner.py",
            (ledger,),
            allow_dirty=False,
        )


def test_broad_dirty_override_is_diagnostic_only() -> None:
    validate_source_status(" M tools/runner.py", (), allow_dirty=True)
