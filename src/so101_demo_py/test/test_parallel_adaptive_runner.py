"""Cross-generation adaptive runner state-machine contracts."""

from pathlib import Path

import pytest

from so101_demo.parallel_batch.adaptive_contracts import (
    AdaptiveBatchRequest,
    BatchTerminalStatus,
    CommittedPointResult,
    InfrastructureFailure,
    InfrastructureFailureKind,
    PoolExecutionResult,
    load_adaptive_worker_options,
)
from so101_demo.parallel_batch.contracts import PointStatus, RunMode


PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE / "config/mujoco/parallel_adaptive_workers_v1.yaml"


class SimulatedCrash(BaseException):
    pass


class FakePool:
    def __init__(self, owner, request, generation):
        self.owner = owner
        self.request = request
        self.generation = generation
        self.recorder = None

    def bind_pool_running_recorder(self, recorder):
        self.recorder = recorder

    def result(self, *, terminals=(), interrupted=(), failure=None, cleanup=True):
        return PoolExecutionResult(
            tuple(
                CommittedPointResult(
                    point_id,
                    status,
                    self.request.evidence_root / "results" / point_id,
                    0,
                )
                for point_id, status in terminals
            ),
            tuple(interrupted),
            failure,
            cleanup,
        )

    def run(self):
        count = self.request.worker_count
        if count in self.owner.crash_levels:
            raise SimulatedCrash(count)
        if count in self.owner.startup_failure_levels:
            return self.result(
                failure=InfrastructureFailure(
                    InfrastructureFailureKind.STARTUP,
                    self.generation,
                    count,
                    "simulated startup failure",
                ),
                cleanup=count not in self.owner.cleanup_failure_levels,
            )
        self.recorder(())
        if count in self.owner.midrun:
            scenario = self.owner.midrun[count]
            terminals = [
                *((point, PointStatus.PASSED) for point in scenario.get("passed", ())),
                *((point, PointStatus.FAILED) for point in scenario.get("failed", ())),
            ]
            return self.result(
                terminals=terminals,
                interrupted=scenario.get("active", ()),
                failure=InfrastructureFailure(
                    InfrastructureFailureKind.PROCESS_EXIT,
                    self.generation,
                    count,
                    "simulated worker exit",
                ),
                cleanup=count not in self.owner.cleanup_failure_levels,
            )
        return self.result(
            terminals=(
                (
                    point_id,
                    PointStatus.FAILED
                    if point_id in self.owner.failed_points
                    else PointStatus.PASSED,
                )
                for point_id in self.request.selected_point_ids
            )
        )


class FakePools:
    def __init__(
        self, *, startup_failure_levels=(), failed_points=(), midrun=None,
        cleanup_failure_levels=(), crash_levels=(),
    ):
        self.startup_failure_levels = set(startup_failure_levels)
        self.failed_points = set(failed_points)
        self.midrun = {} if midrun is None else midrun
        self.cleanup_failure_levels = set(cleanup_failure_levels)
        self.crash_levels = set(crash_levels)
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return FakePool(self, request, len(self.requests))


def make_runner(tmp_path, pools, *, points=None, max_infra_attempts=None):
    from so101_demo.parallel_batch.adaptive_runner import AdaptiveBatchRunner

    options = load_adaptive_worker_options(CONFIG)
    if max_infra_attempts is not None:
        from dataclasses import replace

        options = replace(options, max_infra_attempts_per_point=max_infra_attempts)
    request = AdaptiveBatchRequest(
        "a001",
        RunMode.EXECUTE,
        tuple(points or ("p01", "p09", "p18")),
        options,
        tmp_path,
    )
    return AdaptiveBatchRunner(request, pools), request


def test_startup_failure_falls_from_w8_to_w6(tmp_path):
    pools = FakePools(startup_failure_levels={8})
    runner, _ = make_runner(tmp_path, pools)

    summary = runner.run()

    assert summary.status is BatchTerminalStatus.COMPLETED
    assert summary.initial_worker_count == 8
    assert summary.final_worker_count == 6
    assert [(item.from_count, item.to_count) for item in summary.transitions] == [(8, 6)]
    runner.close()


def test_business_failure_does_not_downgrade(tmp_path):
    pools = FakePools(failed_points={"p09"})
    runner, _ = make_runner(tmp_path, pools)

    summary = runner.run()

    assert summary.status is BatchTerminalStatus.COMPLETED_WITH_FAILURES
    assert summary.final_worker_count == 8
    assert summary.transitions == ()
    runner.close()


def test_midrun_failure_preserves_terminal_results_and_requeues_only_remaining(tmp_path):
    pools = FakePools(
        midrun={
            8: {
                "passed": ("p01",),
                "failed": ("p09",),
                "active": ("p18",),
            }
        }
    )
    runner, _ = make_runner(tmp_path, pools)

    summary = runner.run()

    assert pools.requests[1].worker_count == 6
    assert "p01" not in pools.requests[1].selected_point_ids
    assert "p09" not in pools.requests[1].selected_point_ids
    assert "p18" in pools.requests[1].selected_point_ids
    assert {result.point_id for result in summary.point_results} == {"p01", "p09", "p18"}
    runner.close()


def test_full_ladder_ends_in_infra_failed_after_w1_failure(tmp_path):
    pools = FakePools(startup_failure_levels={8, 6, 4, 2, 1})
    runner, _ = make_runner(tmp_path, pools)

    summary = runner.run()

    assert summary.status is BatchTerminalStatus.INFRA_FAILED
    assert summary.levels_used == (8, 6, 4, 2, 1)
    assert summary.final_worker_count == 1
    assert len(summary.transitions) == 4
    runner.close()


def test_cleanup_failure_never_starts_the_next_pool(tmp_path):
    pools = FakePools(startup_failure_levels={8}, cleanup_failure_levels={8})
    runner, _ = make_runner(tmp_path, pools)

    summary = runner.run()

    assert summary.status is BatchTerminalStatus.INFRA_FAILED
    assert [request.worker_count for request in pools.requests] == [8]
    assert summary.cleanup_complete is False
    runner.close()


def test_infra_attempt_limit_fails_before_another_pool_starts(tmp_path):
    pools = FakePools(midrun={8: {"active": ("p18",)}})
    runner, _ = make_runner(tmp_path, pools, max_infra_attempts=1)

    summary = runner.run()

    assert summary.status is BatchTerminalStatus.INFRA_FAILED
    assert [request.worker_count for request in pools.requests] == [8]
    runner.close()


def test_terminal_result_import_is_idempotent_but_conflicting_status_fails(tmp_path):
    from so101_demo.parallel_batch.adaptive_runner import AdaptiveRunnerError

    runner, _ = make_runner(tmp_path, FakePools(), points=("p01",))
    passed = CommittedPointResult(
        "p01", PointStatus.PASSED, tmp_path / "passed", 0
    )
    runner._import_result(passed, 1)
    runner._import_result(passed, 1)

    with pytest.raises(AdaptiveRunnerError, match="TERMINAL_RESULT_CONFLICT"):
        runner._import_result(
            CommittedPointResult(
                "p01", PointStatus.FAILED, tmp_path / "failed", 0
            ),
            1,
        )
    runner.close()


def test_pool_root_and_required_append_only_events_are_frozen(tmp_path):
    pools = FakePools(midrun={8: {"active": ("p18",)}})
    runner, _ = make_runner(tmp_path, pools)

    runner.run()

    assert pools.requests[0].evidence_root == tmp_path / "r/a001/p/g01w08"
    assert pools.requests[1].evidence_root == tmp_path / "r/a001/p/g02w06"
    event_types = {event.type for event in runner.journal.replay().events}
    assert {
        "POOL_STARTING",
        "POOL_RUNNING",
        "POINT_RESULT_IMPORTED",
        "POINT_INFRA_INTERRUPTED",
        "POOL_DEGRADED",
        "BATCH_TERMINAL",
    } <= event_types
    runner.close()


def test_infrastructure_failure_after_all_results_does_not_start_an_empty_pool(tmp_path):
    pools = FakePools(
        midrun={8: {"passed": ("p01", "p09", "p18"), "active": ()}}
    )
    runner, _ = make_runner(tmp_path, pools)

    summary = runner.run()

    assert summary.status is BatchTerminalStatus.COMPLETED
    assert [request.worker_count for request in pools.requests] == [8]
    runner.close()


def test_replay_preserves_results_attempts_and_fallback_without_auto_resume(tmp_path):
    pools = FakePools(
        midrun={8: {"passed": ("p01",), "active": ("p18",)}},
        crash_levels={6},
    )
    runner, request = make_runner(tmp_path, pools)
    with pytest.raises(SimulatedCrash):
        runner.run()
    before = runner.state_snapshot()
    runner.close()

    replacement_pools = FakePools()
    from so101_demo.parallel_batch.adaptive_runner import AdaptiveBatchRunner

    restored = AdaptiveBatchRunner(request, replacement_pools)
    assert restored.state_snapshot() == before
    report = restored.terminal_report()
    assert report.status is BatchTerminalStatus.INFRA_FAILED
    assert replacement_pools.requests == []
    restored.close()
