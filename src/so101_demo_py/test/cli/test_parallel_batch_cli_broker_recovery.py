"""Broker restart, discovery and recovery while leases are paused."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from parallel_batch_cli_support import (
    CONFIG,
    SimpleLease,
    _scratch_root,
    argv,
    local_start_guard,  # noqa: F401  (pytest fixtures)
    verified,
)
import pytest

from so101_demo.parallel_batch.contracts.common import (
    PointStatus,
    RunMode,
    ValidationStatus,
    WorkerState,
)


def test_broker_exit_restarts_fresh_generation_while_leases_remain_paused(tmp_path):
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot
    from so101_demo.runtime.parallel_processes import OwnedProcess

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)

        def ros_domain_in_use(self, _domain):
            return False

        def socket_in_use(self, _path):
            return False

    class Supervisor:
        def __init__(self):
            self.started = []
            self.retired = []
            self.pause_deadline = None

        def start(self, role, command, **_kwargs):
            self.started.append((role, tuple(command)))
            generation = len(self.started)
            return OwnedProcess(
                "batch-1", role, 100 + generation, 100 + generation,
                tuple(command), 10 + generation,
            )

        def retire_owned(self, process, **_kwargs):
            snapshot = composition.coordinator.snapshot()
            assert snapshot.broker_healthy is False
            self.pause_deadline = snapshot.broker_recovery_deadline_monotonic_s
            assert composition.coordinator.grant_lease(
                "worker-01", generation=1,
            ) is None
            assert snapshot.workers["worker-01"].lease_count == 0
            self.retired.append(process)
            return True

    scratch = _scratch_root()
    root = scratch / "f22br"
    spec = prepare_batch(
        argv(
            root,
            worker_count="1",
                        point_id=("task_start",),
            run_mode="plan_only",
        ),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    supervisor = Supervisor()
    composition = ProductionBatchComposition(
        spec,
        resource_probe=Probe(),
        claim_root=scratch / "f22brc",
        supervisor=supervisor,
        broker_command_builder=lambda owner: (
            "broker", str(owner.broker_spec_path),
        ),
        container_brokers=False,   # the bare host program `broker` is not a container
    )
    composition.coordinator.register_worker("worker-01", generation=1)
    old_process = composition._start_broker()
    old_root = composition.broker_runtime_root
    old_spec = composition.broker_spec_path
    ready_checks = []
    composition._wait_broker_ready = lambda **values: ready_checks.append(values) or True
    try:
        assert composition._recover_broker(old_process, 17) is True
        assert supervisor.retired == [old_process]
        assert composition.broker_generation == 2
        assert composition.broker_runtime_root != old_root
        assert composition.broker_spec_path != old_spec
        assert "authority_token_path" not in json.loads(
            composition.broker_spec_path.read_text()
        )
        assert json.loads(composition.broker_spec_path.read_text())[
            "broker_generation"
        ] == 2
        assert ready_checks == [{"deadline_monotonic_s": supervisor.pause_deadline}]
        assert composition.coordinator.snapshot().broker_healthy is True
    finally:
        composition._release_partial()


def test_authenticated_worker_discovers_only_the_current_healthy_broker(tmp_path):
    import threading

    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.cli.mujoco_batch.rpc_proxies import _CoordinatorRpcProxy
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot
    from so101_demo.runtime.parallel_ipc.frames import IpcError

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)

        def ros_domain_in_use(self, _domain):
            return False

        def socket_in_use(self, _path):
            return False

    scratch = _scratch_root()
    root = scratch / "f22bd"
    spec = prepare_batch(
        argv(
            root,
            worker_count="1",
                        point_id=("task_start",),
            run_mode="plan_only",
        ),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    composition = ProductionBatchComposition(
        spec,
        resource_probe=Probe(),
        claim_root=scratch / "f22bdc",
        broker_command_builder=lambda _owner: ("broker",),
    )
    worker = composition.resource_manifest.workers[0]
    document = json.loads(composition.worker_specs[0].read_text())
    proxy = _CoordinatorRpcProxy(
        document["socket_path"],
        document["token_path"],
        worker_id=worker.worker_id,
        generation=worker.generation,
        mode=RunMode.PLAN_ONLY,
        coordinator_epoch=document["coordinator_epoch"],
    )
    worker_thread = threading.Thread(
        target=composition.worker_servers[0].serve_forever,
        daemon=True,
    )
    worker_thread.start()
    composition._server_threads.append(worker_thread)
    try:
        with pytest.raises(CliError, match="ACTIVE_LEASE_REQUIRED"):
            proxy.current_broker()
        composition.adaptive_context = SimpleNamespace()
        with pytest.raises(IpcError, match="STARTUP_BROKER_WORKER"):
            proxy.startup_broker()
        proxy.register_worker("worker-01", generation=1)
        composition.coordinator.mark_broker_health(True)
        assert proxy.startup_broker() == {
            "healthy": True,
            "broker_generation": 1,
            "broker_socket_path": str(root / "ipc/broker/perception.sock"),
            "recovery_deadline_monotonic_s": None,
        }
        assert composition.coordinator.snapshot().workers[
            "worker-01"
        ].lease_count == 0
        composition.adaptive_context = None
        from so101_demo.parallel_batch.worker_parts.contracts import LeaseGrantPaused

        composition.coordinator.mark_broker_health(False)
        with pytest.raises(LeaseGrantPaused, match="BROKER_RECOVERING"):
            proxy.grant_lease(
                "worker-01", generation=1, request_key="f22-paused-grant"
            )
        assert composition.coordinator.snapshot().workers[
            "worker-01"
        ].lease_count == 0
        composition.coordinator.mark_broker_health(True)
        dropped_ack = composition.coordinator.grant_lease_outcome(
            "worker-01", generation=1, request_key="f22-discovery-lease"
        )["lease"]
        composition.coordinator.mark_broker_health(False)
        lease = proxy.grant_lease(
            "worker-01", generation=1, request_key="f22-discovery-lease"
        )
        assert lease == dropped_ack
        assert composition.coordinator.snapshot().workers[
            "worker-01"
        ].lease_count == 1
        proxy.ack_lease(lease, request_key="f22-discovery-lease-ack")
        assert proxy.current_broker() == {
            "healthy": False,
            "broker_generation": None,
            "broker_socket_path": None,
            "recovery_deadline_monotonic_s": (
                composition.coordinator.snapshot()
                .broker_recovery_deadline_monotonic_s
            ),
        }
        composition.coordinator.mark_broker_health(True)
        first = proxy.current_broker()
        assert first == {
            "healthy": True,
            "broker_generation": 1,
            "broker_socket_path": str(root / "ipc/broker/perception.sock"),
            "recovery_deadline_monotonic_s": None,
        }
        composition._prepare_broker_generation(2)
        composition.coordinator.mark_broker_health(True)
        current = proxy.current_broker()
        assert current["healthy"] is True
        assert current["broker_generation"] == 2
        assert current["broker_socket_path"] == str(
            root / "ipc/broker-g2/perception.sock"
        )
        assert current["broker_socket_path"] != first["broker_socket_path"]
        from dataclasses import replace
        proxy._lease = replace(lease, attempt_id="stale-attempt")
        with pytest.raises(IpcError, match="STALE_LEASE"):
            proxy.current_broker()
        proxy._lease = lease
        composition.coordinator.result_port = SimpleNamespace(
            verify=lambda *_args: {
                "status": "VALIDATION_INVALID",
                "sha256": "c" * 64,
            }
        )
        committed = proxy.commit_validation(
            lease, "/sealed-invalid", request_key="f22-invalid-commit"
        )
        assert committed["status"] is ValidationStatus.VALIDATION_INVALID
        assert composition.coordinator.snapshot().workers[
            "worker-01"
        ].state is WorkerState.RECOVERING
        assert proxy.current_broker()["broker_generation"] == 2
    finally:
        composition._stop_servers()
        composition._release_partial()


def test_broker_recovery_deadline_failure_keeps_shared_dependency_reason(tmp_path):
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot
    from so101_demo.runtime.parallel_processes import OwnedProcess

    class Clock:
        now = 100.0

        def __call__(self):
            return self.now

        def sleep(self, duration):
            self.now += duration

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)

        def ros_domain_in_use(self, _domain):
            return False

        def socket_in_use(self, _path):
            return False

    class Supervisor:
        def retire_owned(self, _process, **_kwargs):
            return False

    clock = Clock()
    scratch = _scratch_root()
    spec = prepare_batch(
        argv(
            scratch / "f22dl",
            worker_count="1",
                        point_id=("task_start",),
            run_mode="plan_only",
        ),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    composition = ProductionBatchComposition(
        spec,
        resource_probe=Probe(),
        claim_root=scratch / "f22dlc",
        supervisor=Supervisor(),
        broker_command_builder=lambda _owner: ("broker",),
        clock=clock,
        sleep=clock.sleep,
    )
    old = OwnedProcess("batch-1", "broker", 101, 101, ("broker",), 11)
    try:
        assert composition._recover_broker(old, 17) is False
        snapshot = composition.coordinator.snapshot()
        assert clock.now == 190.0
        assert snapshot.broker_healthy is False
        assert snapshot.terminal_reason == "SHARED_DEPENDENCY_UNAVAILABLE"
    finally:
        composition._release_partial()


def test_failed_broker_recovery_waits_for_active_physical_stage_before_shutdown(
        tmp_path):
    from test_parallel_batch_fault_injection import (
        Clock,
        gate_summary,
        make_coordinator,
    )

    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    clock = Clock()
    coordinator, journal = make_coordinator(tmp_path, clock, points=("p1",))
    try:
        lease = coordinator.grant_lease("worker-01", generation=1)
        coordinator.ack_lease(lease, request_key="f22-active-ack")
        coordinator.ack_attempt_started(
            lease,
            request_key="f22-active-start",
            gate_summary=gate_summary(lease),
        )
        coordinator.mark_broker_health(False)
        for now in range(104, 190, 4):
            clock.now = float(now)
            lease = coordinator.heartbeat(lease)
        clock.now = 190.0
        snapshot = coordinator.tick()
        assert snapshot.broker_recovery_failed is True
        assert snapshot.terminal_reason is None
        assert snapshot.workers["worker-01"].lease is not None

        composition = object.__new__(ProductionBatchComposition)
        composition.coordinator = coordinator
        composition._clock = clock
        composition._sleep = lambda duration: setattr(
            clock, "now", clock.now + duration
        )

        settled = composition._settle_shared_dependency_failure()

        assert settled.terminal_reason == "SHARED_DEPENDENCY_UNAVAILABLE"
        assert settled.points["p1"].status is PointStatus.INDETERMINATE
        assert settled.workers["worker-01"].lease_count == 1
        assert all(
            event.type != "BATCH_STOPPING"
            or event.payload["delta"].get("terminal_reason")
            == "SHARED_DEPENDENCY_UNAVAILABLE"
            for event in journal.replay().events
        )
    finally:
        journal.close()


def test_pre_pose_broker_outage_seals_invalid_and_runs_worker_recovery():
    from parallel_batch_worker_support import Fake

    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode
    from so101_demo.parallel_batch.worker import ParallelWorker

    fake = Fake(RunMode.EXECUTE)
    fake.broker.raise_request = CliError("BROKER_UNHEALTHY")

    result = ParallelWorker(fake.ports()).run_one()

    assert result.terminal_status is AttemptStatus.INVALID
    assert result.recovered is True
    assert "pose_admission" not in fake.runtime.calls
    assert "submit_motion" not in fake.runtime.calls
    assert fake.results.calls[0][1] is AttemptStatus.INVALID


def test_pose_accepted_before_broker_outage_can_complete_without_another_request():
    from parallel_batch_worker_support import Fake

    from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode
    from so101_demo.parallel_batch.worker import ParallelWorker

    fake = Fake(RunMode.EXECUTE)
    original_admit = fake.runtime.admit_pose
    broker_outage = []

    def admit_then_lose_broker(lease, chain):
        admitted = original_admit(lease, chain)
        broker_outage.append("BROKER_UNHEALTHY_AFTER_POSE_ACCEPTED")
        return admitted

    fake.runtime.admit_pose = admit_then_lose_broker

    result = ParallelWorker(fake.ports()).run_one()

    assert broker_outage == ["BROKER_UNHEALTHY_AFTER_POSE_ACCEPTED"]
    assert result.terminal_status is AttemptStatus.PASSED
    assert fake.runtime.calls.index("pose_admission") < fake.runtime.calls.index(
        "submit_motion"
    )
    assert len([
        call for call in fake.broker.calls if call[0] == "request_model"
    ]) == 1


def test_worker_stays_alive_across_a_paused_grant_and_resumes_remaining_work():
    from parallel_batch_worker_support import Fake

    from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode
    from so101_demo.parallel_batch.worker import ParallelWorker
    from so101_demo.parallel_batch.worker_parts.contracts import LeaseGrantPaused

    fake = Fake(RunMode.EXECUTE)
    grant = fake.coordinator.grant_lease
    paused = True

    def pause_once(*args, **kwargs):
        nonlocal paused
        if paused:
            paused = False
            raise LeaseGrantPaused("BROKER_RECOVERING")
        return grant(*args, **kwargs)

    fake.coordinator.grant_lease = pause_once

    results = ParallelWorker(fake.ports()).run()

    assert [result.stopped_reason for result in results] == [
        "POINT_TERMINAL", "NO_POINT",
    ]
    assert results[0].terminal_status is AttemptStatus.PASSED
    assert fake.coordinator.next_point == 2


def test_existing_worker_fetches_current_broker_before_each_request_and_recovery(
    tmp_path,
):
    from so101_demo.cli.mujoco_batch.rpc_proxies import _WorkerBrokerProxy
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    from so101_demo.parallel_batch.contracts.linux_cuda import (
        load_parallel_runtime_config_linux_cuda,
    )
    from so101_demo.runtime.parallel_worker_parts.receipts import InferenceSnapshotReceipt

    endpoint = tmp_path / "broker-g2.sock"
    discoveries = []

    class Coordinator:
        coordinator_epoch = 1
        worker_id = "worker-01"
        generation = 1
        token = "a" * 64

        def current_broker(self):
            discoveries.append("current")
            return {
                "healthy": True,
                "broker_generation": 2,
                "broker_socket_path": str(endpoint),
                "recovery_deadline_monotonic_s": None,
            }

    clients = []
    generation_bindings = []

    class Client:
        def __init__(self, path, **_kwargs):
            self.path = Path(path)
            clients.append(self.path)

        def call(self, message):
            operation = message["payload"]["operation"]
            if operation == "cancel_generation":
                return {"payload": {"cancelled": True}}
            return {"payload": {
                "request_id": "attempt-1-plastic-cup-yolo11n-seg-v1",
                "model_id": "plastic-cup-yolo11n-seg-v1",
                "model_version": load_parallel_runtime_config_linux_cuda(
                    CONFIG
                ).yolo_weights_sha256,
                "broker_generation": 2,
                "outcome": "NORMAL_REJECTION",
                "candidate": None,
                "reason": "none",
                "queued_monotonic_s": 1.0,
                "queue_deadline_monotonic_s": 2.0,
                "started_monotonic_s": 1.1,
                "inference_deadline_monotonic_s": 2.1,
                "completed_monotonic_s": 1.2,
            }}

    worker_root = tmp_path / "worker-01"
    input_path = (
        worker_root
        / "validations/task_start/attempt-1/working/perception/input/rgb.npy"
    )
    input_path.parent.mkdir(parents=True)
    input_path.write_bytes(b"npy")
    def perception_runner(
        lease, execution_kind, snapshot, broker_request,
    ):
        assert generation_bindings[-1] == 2
        return broker_request(
            "plastic-cup-yolo11n-seg-v1", before_send=lambda _request: None
        )

    proxy = _WorkerBrokerProxy(
        Coordinator(),
        tmp_path / "broker-g1.sock",
        SimpleNamespace(worker_root=worker_root),
        load_parallel_runtime_config_linux_cuda(CONFIG),
        broker_generation=1,
        broker_generation_consumer=generation_bindings.append,
        perception_runner=perception_runner,
        client_factory=Client,
    )
    response = proxy.request_model(
        SimpleLease(),
        ExecutionKind.VALIDATION,
        snapshot=InferenceSnapshotReceipt(
            input_path,
            11.0,
            12_000_000_000,
            "task_camera_frame",
            (2, 3, 3),
            hashlib.sha256(b"npy").hexdigest(),
        ),
        start_event_id="validation-start-attempt-1",
        start_event_type="VALIDATION_STARTED",
        reset_epoch="reset-1",
    )
    assert response.broker_generation == 2
    assert proxy.cancel_generation("worker-01", 1) is True
    assert generation_bindings == [2, 2, 2, 2]
    assert discoveries == ["current", "current", "current", "current"]
    assert clients == [
        tmp_path / "broker-g1.sock",
        endpoint,
        endpoint,
        endpoint,
        endpoint,
    ]


def test_legacy_cli_flag_is_an_explicit_error():
    """The retired lifetime quota flag is refused before any resource is touched."""

    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.contracts.common import ContractError
    with pytest.raises(ContractError) as error:
        prepare_batch(['--max-points-per-worker', '20'])
    assert error.value.code == 'LEGACY_MAX_POINTS_PER_WORKER_UNSUPPORTED'
