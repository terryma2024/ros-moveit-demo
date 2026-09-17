"""Safety contracts for adaptive pool startup readiness."""

from dataclasses import replace
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from so101_demo.parallel_batch.contracts import (
    AttemptStatus,
    BatchSummary,
    PointStatus,
    RunMode,
    ValidationStatus,
)


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


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def sleep(self, duration):
        self.now += duration


class HealthySupervisor:
    def __init__(self):
        self.checks = 0

    def assert_healthy(self):
        self.checks += 1


def startup_composition(clock, controls, recorder):
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition

    composition = object.__new__(ProductionBatchComposition)
    composition._clock = clock
    composition._sleep = clock.sleep
    composition.supervisor = HealthySupervisor()
    composition.worker_controls = controls
    composition._adaptive_worker_processes = {
        control.worker_id: SimpleNamespace(start_time=1234)
        for control in controls
    }
    composition.broker_generation = 1
    composition.adaptive_context = SimpleNamespace(
        options=SimpleNamespace(worker_start_timeout_s=120.0)
    )
    composition._pool_running_recorder = recorder
    return composition


def test_control_socket_appearing_after_six_seconds_uses_shared_120_second_deadline():
    clock = FakeClock()

    class Control:
        worker_id = "w1"
        generation = 1

        def readiness(self):
            return None if clock.now < 6.0 else valid_receipt(observed=clock.now)

        def release_start(self):
            return True

    recorded = []
    composition = startup_composition(clock, [Control()], recorded.append)

    composition._release_adaptive_workers()

    assert clock.now >= 6.0
    assert len(recorded) == 1


@pytest.mark.parametrize("transport_error", ["DEADLINE_EXCEEDED", "TRUNCATED_FRAME"])
def test_transient_readiness_transport_failure_is_retried_before_shared_deadline(
    transport_error,
):
    from so101_demo.runtime.parallel_ipc import IpcError

    clock = FakeClock()

    class Control:
        worker_id = "w1"
        generation = 1

        def __init__(self):
            self.readiness_calls = 0

        def readiness(self):
            self.readiness_calls += 1
            if self.readiness_calls == 1:
                raise IpcError(transport_error)
            return valid_receipt(observed=clock.now)

        def release_start(self):
            return True

    control = Control()
    recorded = []
    composition = startup_composition(clock, [control], recorded.append)

    composition._release_adaptive_workers()

    assert control.readiness_calls == 3
    assert len(recorded) == 1


def test_worker_ready_timeout_occurs_without_release_or_pool_running_record():
    clock = FakeClock()

    class Control:
        worker_id = "w1"
        generation = 1

        def readiness(self):
            return None

        def release_start(self):
            raise AssertionError("unready worker was released")

    recorded = []
    composition = startup_composition(clock, [Control()], recorded.append)

    from so101_demo.cli.mujoco_parallel_batch import CliError

    with pytest.raises(CliError, match="WORKER_READY_TIMEOUT"):
        composition._release_adaptive_workers()
    assert clock.now == 120.0
    assert recorded == []


def test_second_release_failure_is_after_pool_running_linearization():
    clock = FakeClock()
    order = []

    class Control:
        generation = 1

        def __init__(self, worker_id, succeeds):
            self.worker_id = worker_id
            self.succeeds = succeeds

        def readiness(self):
            return valid_receipt(self.worker_id, observed=clock.now)

        def release_start(self):
            order.append(("release", self.worker_id))
            return self.succeeds

    composition = startup_composition(
        clock,
        [Control("w1", True), Control("w2", False)],
        lambda receipts: order.append(("pool_running", len(receipts))),
    )

    from so101_demo.cli.mujoco_parallel_batch import CliError

    with pytest.raises(CliError, match="POOL_RUNTIME_RELEASE_FAILED"):
        composition._release_adaptive_workers()
    assert order == [
        ("pool_running", 2),
        ("release", "w1"),
        ("release", "w2"),
    ]


@pytest.mark.parametrize(
    "change",
    [
        {"broker_generation": 2},
        {"observed_monotonic_s": -0.1},
    ],
)
def test_final_readiness_recheck_rejects_wrong_broker_or_stale_receipt(change):
    clock = FakeClock()
    clock.now = 2.0

    class Control:
        worker_id = "w1"
        generation = 1

        def readiness(self):
            values = {
                "broker_generation": 1,
                "observed_monotonic_s": clock.now,
            }
            values.update(change)
            if values["observed_monotonic_s"] < 0:
                values["observed_monotonic_s"] = 0.0
            return replace(valid_receipt(observed=clock.now), **values)

        def release_start(self):
            raise AssertionError("invalid receipt was released")

    composition = startup_composition(clock, [Control()], lambda _receipts: None)

    from so101_demo.cli.mujoco_parallel_batch import CliError

    with pytest.raises(CliError, match="WORKER_READINESS_INVALID"):
        composition._release_adaptive_workers()


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
        max_points_per_worker=len(summary.point_statuses),
        evidence_root=tmp_path / "r/a001/p/g01w01",
    )
    options = dc_replace(
        load_adaptive_worker_options(
            Path(__file__).resolve().parents[1]
            / "config/mujoco/parallel_adaptive_workers_v1.yaml"
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


@pytest.mark.parametrize(
    ("worker_count", "yolo_executor_count"),
    [(8, 2), (1, 1)],
)
def test_adaptive_broker_runtime_spec_carries_effective_concurrency(
    tmp_path, monkeypatch, worker_count, yolo_executor_count
):
    from so101_demo.cli import mujoco_parallel_batch as cli
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config

    config_path = (
        Path(__file__).resolve().parents[1]
        / "config/mujoco/parallel_batch_v1.yaml"
    )
    config = load_parallel_runtime_config(config_path)
    owner = object.__new__(cli.ProductionBatchComposition)
    ipc_root = tmp_path / "ipc"
    ipc_root.mkdir()
    owner.authority = SimpleNamespace(ipc_root=ipc_root)
    owner.broker_generation = 0
    owner.adaptive_context = SimpleNamespace(
        request=SimpleNamespace(worker_count=worker_count),
        options=SimpleNamespace(yolo_executor_count=2),
    )
    owner.journal = SimpleNamespace(coordinator_epoch=3)
    owner.spec = SimpleNamespace(
        request=SimpleNamespace(
            batch_id="abcde-g01-w08",
            evidence_root=tmp_path,
            run_mode=RunMode.PLAN_ONLY,
        ),
        config=config,
        config_path=config_path,
        provenance={"image_id": "sha256:" + "b" * 64},
        yolo_weights_sha256=config.yolo_weights_sha256,
        grounded_manifest_sha256=config.grounded_sam_manifest_sha256,
    )
    owner._coordinator_handler = lambda _message: None

    owner._prepare_broker_generation(1)

    document = json.loads(owner.broker_spec_path.read_text(encoding="utf-8"))
    expected_deadline = max(
        config.yolo_queue_timeout_s + config.yolo_inference_timeout_s,
        config.grounded_sam_queue_timeout_s
        + config.grounded_sam_inference_timeout_s,
    ) + config.heartbeat_timeout_s
    assert expected_deadline == 75.0
    assert document["queue_capacity_per_model"] == worker_count
    assert document["connection_handler_count"] == worker_count
    assert document["yolo_executor_count"] == yolo_executor_count
    assert document["grounded_sam_executor_count"] == 1
    assert document["request_deadline_s"] == expected_deadline
    assert "authority_endpoint" not in document
    assert "authority_token_path" not in document
