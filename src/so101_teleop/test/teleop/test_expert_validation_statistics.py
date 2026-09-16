from pathlib import Path

import pytest

from so101_demo.parallel_batch.adaptive_contracts import (
    AdaptiveBatchSummary,
    BatchTerminalStatus,
    CommittedPointResult,
)
from so101_demo.parallel_batch.contracts import BatchSummary, PointStatus, RunMode
from so101_teleop.expert_validation.statistics import (
    AdaptivePointProjection,
    AttemptProjection,
    BrokerProjection,
    PointProjection,
    StatisticsProjectionError,
    WorkerProjection,
    summarize_adaptive_first_pass,
    summarize_first_pass,
)


def _fixed_summary(
    statuses,
    *,
    terminal=True,
    cleanup=True,
    reason="POINTS_COMPLETE",
):
    return BatchSummary(
        run_mode=RunMode.EXECUTE,
        point_statuses=statuses,
        batch_terminal=terminal,
        batch_cleanup_complete=cleanup,
        terminal_reason=reason,
    )


def _point(point_id, status, **overrides):
    defaults = {
        "evaluated": status in {PointStatus.PASSED, PointStatus.FAILED},
        "execution_started": status in {PointStatus.PASSED, PointStatus.FAILED},
    }
    defaults.update(overrides)
    return PointProjection(point_id=point_id, status=status, **defaults)


def test_unreachable_is_evaluated_failure_not_unexecuted():
    view = summarize_first_pass(
        _fixed_summary({"task_start": PointStatus.FAILED}),
        [
            _point(
                "task_start",
                PointStatus.FAILED,
                reason="UNREACHABLE",
                evaluated=True,
                execution_started=False,
            )
        ],
    )

    assert view.valid_failed == 1
    assert view.not_executed == 0
    assert view.execution_started == 0


def test_indeterminate_is_not_product_failure_or_retry_candidate():
    view = summarize_first_pass(
        _fixed_summary(
            {"task_start": PointStatus.INDETERMINATE},
            cleanup=True,
            reason="OWNER_LOST",
        ),
        [
            _point(
                "task_start",
                PointStatus.INDETERMINATE,
                evaluated=False,
                execution_started=True,
                reason="OWNER_LOST",
            )
        ],
    )

    assert view.indeterminate == 1
    assert view.valid_failed == 0
    assert not view.points[0].retry_eligible


def test_web_never_upgrades_coordinator_qualification():
    view = summarize_first_pass(
        _fixed_summary({"task_start": PointStatus.PASSED}, cleanup=False),
        [_point("task_start", PointStatus.PASSED)],
    )

    assert view.valid_succeeded == 1
    assert view.qualified_success_rate is None
    assert view.qualification_passed is False


def test_fixed_projection_preserves_workers_broker_and_invalid_attempts():
    points = [
        _point("a", PointStatus.PASSED, invalid_attempts=1),
        _point("b", PointStatus.FAILED),
    ]
    workers = [
        WorkerProjection("w1", 1, "STOPPED"),
        WorkerProjection("w2", 1, "QUARANTINED", quarantine_reason="RECOVERY_FAILED"),
    ]
    broker = BrokerProjection(available=False, reason="BROKER_UNAVAILABLE")

    view = summarize_first_pass(
        _fixed_summary({"a": PointStatus.PASSED, "b": PointStatus.FAILED}),
        points,
        workers=workers,
        broker=broker,
    )

    assert view.invalid_attempts == 1
    assert view.valid_succeeded == 1
    assert view.valid_failed == 1
    assert view.points[1].retry_eligible
    assert view.workers == tuple(workers)
    assert view.broker == broker


def test_multiple_workers_can_be_active_in_a_nonterminal_batch():
    summary = _fixed_summary(
        {"a": PointStatus.UNRUN, "b": PointStatus.UNRUN},
        terminal=False,
        cleanup=False,
        reason=None,
    )
    points = [
        _point(
            "a",
            PointStatus.UNRUN,
            evaluated=False,
            execution_started=True,
            active_worker_id="w1",
        ),
        _point(
            "b",
            PointStatus.UNRUN,
            evaluated=False,
            execution_started=True,
            active_worker_id="w2",
        ),
    ]
    workers = [
        WorkerProjection("w1", 1, "EXECUTING", active_point_id="a"),
        WorkerProjection("w2", 1, "EXECUTING", active_point_id="b"),
    ]

    view = summarize_first_pass(summary, points, workers=workers)

    assert [worker.active_point_id for worker in view.workers] == ["a", "b"]
    assert not any(point.retry_eligible for point in view.points)


@pytest.mark.parametrize(
    ("point", "terminal", "cleanup", "eligible"),
    [
        (_point("p", PointStatus.FAILED), True, True, True),
        (_point("p", PointStatus.FAILED, active_worker_id="w1"), False, False, False),
        (_point("p", PointStatus.UNRUN, evaluated=False, execution_started=False), True, True, False),
        (
            _point(
                "p",
                PointStatus.INDETERMINATE,
                evaluated=False,
                execution_started=True,
            ),
            True,
            True,
            False,
        ),
    ],
)
def test_fixed_retry_eligibility_is_derived_not_trusted(point, terminal, cleanup, eligible):
    summary = _fixed_summary(
        {"p": point.status}, terminal=terminal, cleanup=cleanup, reason="CAPACITY_EXHAUSTED"
    )
    view = summarize_first_pass(summary, [point])
    assert view.points[0].retry_eligible is eligible


def test_fixed_projection_fails_closed_on_count_or_status_mismatch():
    summary = _fixed_summary({"a": PointStatus.PASSED, "b": PointStatus.FAILED})

    with pytest.raises(StatisticsProjectionError, match="POINT_SET_MISMATCH"):
        summarize_first_pass(summary, [_point("a", PointStatus.PASSED)])
    with pytest.raises(StatisticsProjectionError, match="POINT_STATUS_MISMATCH"):
        summarize_first_pass(
            summary,
            [_point("a", PointStatus.PASSED), _point("b", PointStatus.PASSED)],
        )


def test_terminal_batch_cannot_have_an_active_lease():
    with pytest.raises(StatisticsProjectionError, match="TERMINAL_ACTIVE_LEASE"):
        summarize_first_pass(
            _fixed_summary({"a": PointStatus.PASSED}),
            [_point("a", PointStatus.PASSED, active_worker_id="w1")],
            workers=[WorkerProjection("w1", 2, "QUARANTINED", active_point_id="a")],
        )


def _adaptive_summary(status, results, *, cleanup=True, levels=(8, 6)):
    return AdaptiveBatchSummary(
        status=status,
        initial_worker_count=levels[0],
        final_worker_count=levels[-1],
        levels_used=levels,
        point_results=tuple(results),
        transitions=(),
        cleanup_complete=cleanup,
    )


def _result(point_id, status, attempts=0):
    return CommittedPointResult(
        point_id=point_id,
        status=status,
        evidence_root=Path("/tmp/adaptive-result") / point_id,
        infra_attempts=attempts,
    )


def test_adaptive_summary_preserves_attempt_history_and_runner_terminal():
    point = AdaptivePointProjection(
        point_id="a",
        status=PointStatus.PASSED,
        attempts=(
            AttemptProjection(1, "INDETERMINATE", reason="INFRA_INTERRUPTED"),
            AttemptProjection(2, "PASSED"),
        ),
    )
    view = summarize_adaptive_first_pass(
        _adaptive_summary(
            BatchTerminalStatus.COMPLETED,
            [_result("a", PointStatus.PASSED, attempts=1)],
        ),
        [point],
    )

    assert view.status == "COMPLETED"
    assert view.levels_used == (8, 6)
    assert view.points[0].status == "PASSED"
    assert view.points[0].attempts[0].status == "INDETERMINATE"


@pytest.mark.parametrize(
    ("terminal_status", "point_status", "cleanup", "eligible"),
    [
        (BatchTerminalStatus.COMPLETED, PointStatus.PASSED, True, False),
        (BatchTerminalStatus.COMPLETED_WITH_FAILURES, PointStatus.FAILED, True, True),
        (BatchTerminalStatus.COMPLETED_WITH_FAILURES, PointStatus.FAILED, False, False),
        (BatchTerminalStatus.INFRA_FAILED, PointStatus.UNRUN, True, False),
    ],
)
def test_adaptive_retry_and_terminal_status_rules(
    terminal_status, point_status, cleanup, eligible
):
    results = []
    if point_status in {PointStatus.PASSED, PointStatus.FAILED}:
        results.append(_result("a", point_status))
    point = AdaptivePointProjection(
        point_id="a",
        status=point_status,
        reason="INFRA_INTERRUPTED" if point_status is PointStatus.UNRUN else None,
    )

    view = summarize_adaptive_first_pass(
        _adaptive_summary(terminal_status, results, cleanup=cleanup, levels=(1,)),
        [point],
    )

    assert view.points[0].retry_eligible is eligible


def test_adaptive_terminal_result_is_immutable_and_must_match_runner():
    summary = _adaptive_summary(
        BatchTerminalStatus.COMPLETED,
        [_result("a", PointStatus.PASSED)],
        levels=(1,),
    )

    with pytest.raises(StatisticsProjectionError, match="ADAPTIVE_RESULT_MISMATCH"):
        summarize_adaptive_first_pass(
            summary,
            [AdaptivePointProjection("a", PointStatus.FAILED)],
        )


def test_adaptive_business_failure_does_not_imply_fallback():
    view = summarize_adaptive_first_pass(
        _adaptive_summary(
            BatchTerminalStatus.COMPLETED_WITH_FAILURES,
            [_result("a", PointStatus.FAILED)],
            levels=(8,),
        ),
        [AdaptivePointProjection("a", PointStatus.FAILED)],
    )

    assert view.levels_used == (8,)
    assert view.status == "COMPLETED_WITH_FAILURES"
