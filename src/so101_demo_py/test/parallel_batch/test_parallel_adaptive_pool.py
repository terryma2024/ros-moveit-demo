"""Safety contracts for adaptive pool startup readiness."""

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.parallel_batch.contracts.common import (
    AttemptStatus,
    PointStatus,
    RunMode,
    ValidationStatus,
)
from so101_demo.parallel_batch.contracts.identity import BatchSummary
from paths import PACKAGE_ROOT


def valid_receipt(worker_id="w1", *, generation=1, observed=10.0):
    from so101_demo.parallel_batch.adaptive_pool import WorkerReadinessReceipt

    return WorkerReadinessReceipt(
        worker_id=worker_id,
        generation=generation,
        process_start_ticks=1234,
        coordinator_registered=True,
        runtime_ready=True,
        broker_ready=True,
        broker_generation=1,
        observed_monotonic_s=observed,
    )


def test_w16_socket_paths_keep_two_digit_worker_identities():
    """W10 through W16 retain the established two-digit endpoint names."""

    from so101_demo.parallel_batch.adaptive_pool import adaptive_socket_paths

    paths = adaptive_socket_paths(Path("/tmp/w16-pool"), 16)
    rendered = {str(path) for path in paths}

    assert len(paths) == 50
    assert "/tmp/w16-pool/ipc/worker-10.sock" in rendered
    assert "/tmp/w16-pool/ipc/worker-16-control.sock" in rendered


def test_worker_cannot_request_a_lease_before_release_start():
    from so101_demo.parallel_batch.adaptive_pool import WorkerStartGate

    gate = WorkerStartGate(expected_worker_id="w1", generation=1)
    gate.record_readiness(valid_receipt("w1", generation=1))

    assert gate.wait_released(timeout_s=0.0) is False
    gate.release("w1", generation=1)
    assert gate.wait_released(timeout_s=0.0) is True


@pytest.mark.parametrize(
    "receipt",
    [
        lambda: valid_receipt("w2"),
        lambda: valid_receipt(generation=2),
        lambda: replace(valid_receipt(), runtime_ready=False),
        lambda: replace(valid_receipt(), broker_ready=False),
    ],
)
def test_start_gate_rejects_wrong_identity_or_incomplete_readiness(receipt):
    from so101_demo.parallel_batch.adaptive_pool import WorkerStartGate

    gate = WorkerStartGate(expected_worker_id="w1", generation=1)

    with pytest.raises(ValueError, match="WORKER_READINESS"):
        gate.record_readiness(receipt())


def test_release_requires_a_recorded_matching_receipt():
    from so101_demo.parallel_batch.adaptive_pool import WorkerStartGate

    gate = WorkerStartGate(expected_worker_id="w1", generation=1)
    with pytest.raises(ValueError, match="WORKER_NOT_READY"):
        gate.release("w1", generation=1)
    gate.record_readiness(valid_receipt())
    with pytest.raises(ValueError, match="WORKER_IDENTITY"):
        gate.release("w2", generation=1)


def test_readiness_receipt_rejects_boolean_numeric_fields():
    from so101_demo.parallel_batch.adaptive_pool import WorkerReadinessReceipt

    with pytest.raises(ValueError, match="PROCESS_START_TICKS"):
        WorkerReadinessReceipt("w1", 1, True, True, True, True, 1, 10.0)


def production_pool(tmp_path, summary, **composition_state):
    from dataclasses import replace as dc_replace

    from so101_demo.parallel_batch.adaptive_contracts import (
        _new_pool_request_for_production_factory,
        load_adaptive_worker_options,
    )
    from so101_demo.parallel_batch.adaptive_pool import (
        AdaptivePointSelector,
        AdaptivePoolContext,
        ProductionAdaptivePool,
    )

    request = _new_pool_request_for_production_factory(
        batch_id="a001-g01-w01",
        run_mode=summary.run_mode,
        selected_point_ids=tuple(summary.point_statuses),
        worker_count=1,
        evidence_root=tmp_path / "r/a001/p/g01w01",
    )
    options = dc_replace(
        load_adaptive_worker_options(
            PACKAGE_ROOT
            / "config/mujoco/adaptive_worker_pool.yaml"
        ),
        worker_count=1,
        fallback_worker_counts=(),
    )
    context = AdaptivePoolContext(
        request,
        options,
        AdaptivePointSelector(request.selected_point_ids, ("worker-01",), 3),
    )
    default_locations = {
        point_id: tmp_path / "sealed" / point_id
        for point_id, status in summary.point_statuses.items()
        if status in {PointStatus.PASSED, PointStatus.FAILED}
    }

    class Composition:
        worker_exit_codes = composition_state.get("worker_exit_codes", ())
        adaptive_cleanup_complete = composition_state.get(
            "adaptive_cleanup_complete", True
        )
        adaptive_attempt_statuses = composition_state.get(
            "adaptive_attempt_statuses", {}
        )
        adaptive_result_locations = composition_state.get(
            "adaptive_result_locations", default_locations
        )

        def __init__(self, *_args, **kwargs):
            self.pool_running_recorder = kwargs["pool_running_recorder"]

        def run(self):
            exception = composition_state.get("exception")
            if exception is not None:
                raise exception
            self.pool_running_recorder(())
            return summary

    return ProductionAdaptivePool(
        prepared=SimpleNamespace(request=request),
        context=context,
        generation=1,
        composition_factory=Composition,
    )


def execute_summary(statuses, *, cleanup=True):
    return BatchSummary(
        RunMode.EXECUTE,
        statuses,
        batch_terminal=True,
        batch_cleanup_complete=cleanup,
        terminal_reason="POINTS_COMPLETE",
    )


def test_production_adapter_keeps_business_failure_in_the_same_pool(tmp_path):
    pool = production_pool(
        tmp_path,
        execute_summary({"p1": PointStatus.PASSED, "p2": PointStatus.FAILED}),
    )
    pool.bind_pool_running_recorder(lambda _receipts: None)

    result = pool.run()

    assert [item.status for item in result.terminal_results] == [
        PointStatus.PASSED,
        PointStatus.FAILED,
    ]
    assert result.infrastructure_failure is None


@pytest.mark.parametrize(
    ("state", "kind"),
    [
        ({"adaptive_attempt_statuses": {"p1": AttemptStatus.INVALID}}, "RECOVERY"),
        ({"worker_exit_codes": (17,)}, "PROCESS_EXIT"),
        ({"exception": RuntimeError("BROKER_DISCONNECTED")}, "BROKER_DISCONNECTED"),
    ],
)
def test_production_adapter_names_infrastructure_failures(tmp_path, state, kind):
    pool = production_pool(
        tmp_path,
        execute_summary({"p1": PointStatus.UNRUN}, cleanup=kind != "PROCESS_EXIT"),
        **state,
    )
    pool.bind_pool_running_recorder(lambda _receipts: None)

    result = pool.run()

    assert result.infrastructure_failure.kind.value == kind


def test_startup_exception_persists_stage_traceback_chain_and_cleanup(tmp_path):
    pool = production_pool(
        tmp_path,
        execute_summary({"p1": PointStatus.UNRUN}, cleanup=False),
    )

    def fail_during_construction(*_args, **_kwargs):
        try:
            raise OSError("domain claim unavailable")
        except OSError as cause:
            error = RuntimeError("composition construction failed")
            error.startup_stage = "resource_allocation"
            error.partial_cleanup = {
                "worker_servers": [],
                "journal": None,
                "allocator": {
                    "succeeded": True,
                    "error_type": None,
                    "error_message": None,
                },
            }
            raise error from cause

    pool.composition_factory = fail_during_construction
    pool.context.request.evidence_root.parent.mkdir(parents=True, mode=0o700)
    pool.bind_pool_running_recorder(lambda _receipts: None)

    result = pool.run()

    report_path = tmp_path / "r/a001/p/g01w01-failure.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["stage"] == "resource_allocation"
    assert report["pool_running"] is False
    assert report["cleanup_complete"] is False
    assert report["exception_chain"] == [
        {"type": "RuntimeError", "message": "composition construction failed"},
        {"type": "OSError", "message": "domain claim unavailable"},
    ]
    assert report["partial_cleanup"] == {
        "worker_servers": [],
        "journal": None,
        "allocator": {
            "succeeded": True,
            "error_type": None,
            "error_message": None,
        },
    }
    assert "raise error from cause" in report["traceback"]
    assert result.infrastructure_failure.detail == (
        "RuntimeError: composition construction failed"
    )


def test_production_adapter_cleanup_false_is_infrastructure(tmp_path):
    pool = production_pool(
        tmp_path,
        execute_summary({"p1": PointStatus.UNRUN}, cleanup=False),
    )
    pool.bind_pool_running_recorder(lambda _receipts: None)

    result = pool.run()

    assert result.infrastructure_failure.kind.value == "CLEANUP"
    assert result.cleanup_complete is False


def test_nonzero_worker_can_degrade_after_verified_adaptive_cleanup(tmp_path):
    pool = production_pool(
        tmp_path,
        execute_summary({"p1": PointStatus.UNRUN}, cleanup=True),
        worker_exit_codes=(17,),
        adaptive_cleanup_complete=True,
    )
    pool.bind_pool_running_recorder(lambda _receipts: None)

    result = pool.run()

    assert result.infrastructure_failure.kind.value == "PROCESS_EXIT"
    assert result.cleanup_complete is True


def test_production_adapter_imports_only_fsync_located_terminal_results(tmp_path):
    pool = production_pool(
        tmp_path,
        execute_summary({"p1": PointStatus.PASSED}),
        adaptive_result_locations={},
    )
    pool.bind_pool_running_recorder(lambda _receipts: None)

    result = pool.run()

    assert result.terminal_results == ()
    assert result.interrupted_point_ids == ("p1",)
    assert result.infrastructure_failure.kind.value == "COORDINATOR"


def test_plan_only_validation_never_becomes_a_physical_terminal_result(tmp_path):
    summary = BatchSummary(
        RunMode.PLAN_ONLY,
        {"p1": PointStatus.UNRUN},
        batch_terminal=True,
        validation_statuses={"p1": ValidationStatus.VALIDATION_PASSED},
        batch_cleanup_complete=True,
        terminal_reason="POINTS_COMPLETE",
    )
    pool = production_pool(tmp_path, summary)
    pool.bind_pool_running_recorder(lambda _receipts: None)

    result = pool.run()

    assert result.terminal_results == ()
    assert result.infrastructure_failure is None


def test_adaptive_socket_paths_freeze_the_107_byte_boundary():
    from so101_demo.parallel_batch.adaptive_pool import adaptive_socket_paths

    root = Path(
        "/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01/"
        "r/abcde/p/g01w08"
    )
    paths = adaptive_socket_paths(root, 8)

    assert len(str(root / "ipc/worker-08-control.sock").encode()) == 107
    assert len(str(root / "ipc/broker/authority.sock").encode()) == 106
    assert max(len(str(path).encode()) for path in paths) == 107
    assert all("broker-authority.sock" not in str(path) for path in paths)


def test_adaptive_socket_paths_can_use_explicit_short_runtime_root():
    from so101_demo.parallel_batch.adaptive_pool import adaptive_socket_paths

    durable = Path("/data/work/so101-evidence/" + "x" * 120)
    ipc = Path("/run/user/1000/so101-a1-g01-w08")
    paths = adaptive_socket_paths(durable, 8, ipc_root=ipc)

    assert all(path.is_relative_to(ipc) for path in paths)
    assert max(len(str(path).encode()) for path in paths) < 108

