import asyncio
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import sys
import time

import pytest

from so101_teleop.expert_validation.models import CleanupReceipt
from so101_teleop.expert_validation.control import ControlProtocolError
from so101_teleop.expert_validation.coordinator import CoordinatorStartRequest
from so101_teleop.expert_validation.lease import ValidationLeaseService
from so101_teleop.expert_validation.process_owner import ExecutionProcessOwner
from so101_teleop.expert_validation.preflight import PreflightEngine, PreflightRejected
from so101_teleop.expert_validation.store import StoreConflict, SupervisorStore
from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor

from test_expert_validation_preflight import Resources, _request
from test_expert_validation_adaptive_owner import request as _adaptive_owner_request


class Owner:
    def __init__(self):
        self.requests = []
        self.timeline = []

    async def spawn_and_wait(self, request):
        self.requests.append(request)
        point = getattr(request, "selected_point_ids", ("first-pass",))[0]
        self.timeline.append(
            f"start-{request.batch_id}-{point}-n{getattr(request, 'worker_count', 'adaptive')}-"
            "k" + str(getattr(request, 'max_points_per_worker', None))
        )
        self.timeline.append(f"cleanup-{request.batch_id}-{point}")
        return {"cleanup_complete": True, "receipt_sha256": "d" * 64}


def _supervisor(tmp_path, resources=None):
    root = tmp_path.resolve()
    store = SupervisorStore.open((root / "store").resolve())
    owner = Owner()
    supervisor = ExpertValidationSupervisor(
        store=store,
        process_owner=owner,
        preflight_engine=PreflightEngine(resources or Resources()),
    )
    return supervisor, owner, store


def _bound_without_execution(tmp_path):
    """Persist the real admitted Web binding without any physical/test outcome."""
    class CaptureOwner:
        def spawn(self, request):
            self.request = request
            return None

    supervisor, _, store = _supervisor(tmp_path)
    capture = CaptureOwner()
    supervisor.process_owner = capture
    asyncio.run(supervisor.start_first_pass(_request(tmp_path / "request", "SEQUENTIAL")))
    return supervisor, store, capture.request


def test_fixed_owner_request_has_random_identity_bound_control_credentials(tmp_path):
    supervisor, store, request = _bound_without_execution(tmp_path)
    try:
        binding = request.control_binding
        original = supervisor._requests[request.campaign_id]
        receipt = supervisor.preflight_engine.preflight(original)
        again = supervisor._owner_request(original, receipt, request.batch_id, request.batch_root)
        assert binding is not None
        assert len(binding.control_token) == 64
        assert binding.control_token != again.control_binding.control_token
        assert binding.control_token_sha256 == hashlib.sha256(binding.control_token.encode()).hexdigest()
        assert binding.control_token_sha256 != hashlib.sha256(
            f"{request.campaign_id}:{request.batch_id}".encode()
        ).hexdigest()
        assert binding.campaign_id == "campaign-1" and binding.batch_id == "b001"
        assert binding.coordinator_epoch == 1
        assert binding.control_socket == request.batch_root / "control" / "control.sock"
        assert request.environment["SO101_FIXED_CONTROL_TOKEN"] == binding.control_token
        assert request.environment["SO101_FIXED_CONTROL_CAMPAIGN_ID"] == "campaign-1"
        assert request.environment["SO101_FIXED_CONTROL_EPOCH"] == "1"
        assert request.environment["SO101_FIXED_CONTROL_SOCKET"] == str(binding.control_socket)
    finally:
        store.close()


def test_fixed_control_binding_is_durable_with_the_real_spawn_intent(tmp_path):
    _, store, request = _bound_without_execution(tmp_path)
    root = store.root
    try:
        store.record_execution_owner_intent(request)
        assert store.fixed_control_binding(request.batch_id) == request.control_binding
    finally:
        store.close()
    reopened = SupervisorStore.open(root)
    try:
        assert reopened.fixed_control_binding(request.batch_id) == request.control_binding
        assert reopened.owned_execution(request.batch_id).state == "INTENT"
        assert reopened.batch(request.batch_id).cleanup_receipt_sha256 is None
    finally:
        reopened.close()


def test_fixed_owner_ack_cannot_change_the_durable_control_epoch(tmp_path):
    _, store, request = _bound_without_execution(tmp_path)
    try:
        store.record_execution_owner_intent(request)
        with pytest.raises(StoreConflict, match="FIXED_CONTROL_OWNER_ACK_MISMATCH"):
            store.acknowledge_execution_owner(
                batch_id=request.batch_id, pid=101, pgid=101, started_ticks=100,
                coordinator_epoch=2,
            )
        assert store.owned_execution(request.batch_id).state == "INTENT"
        assert store.fixed_control_binding(request.batch_id).coordinator_epoch == 1
        assert store.batch(request.batch_id).cleanup_receipt_sha256 is None
    finally:
        store.close()


@pytest.mark.parametrize("reason", ["USER_CANCELLED", "LEASE_EXPIRED"])
def test_live_fixed_supervisor_uses_real_authenticated_coordinator_not_signals(tmp_path, reason):
    supervisor, store, request = _bound_without_execution(tmp_path)
    owner = ExecutionProcessOwner(store=store)
    supervisor.process_owner = owner
    # Evaluate the new binding before spawning; RED never starts an accidental CLI.
    binding = request.control_binding
    assert binding is not None
    config = Path(__file__).resolve().parents[3] / "so101_demo_py/config/mujoco/parallel_batch_v1.yaml"
    program = '''
import json, os, pathlib, time
from so101_demo.parallel_batch.contracts import BatchRequest, RunMode, load_parallel_runtime_config
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.web_control import FixedCoordinatorControlServer
root = pathlib.Path(os.environ["TOY_BATCH_ROOT"])
journal = CoordinatorJournal.create(root / "coordinator", "b001")
request = BatchRequest("b001", RunMode.EXECUTE, ("p1", "p2"), 2, 2, root)
coordinator = BatchCoordinator(journal, request, config=load_parallel_runtime_config(os.environ["TOY_CONFIG"]), result_port=None)
coordinator.register_worker("w1", generation=1)
coordinator.register_worker("w2", generation=1)
path = pathlib.Path(os.environ["SO101_FIXED_CONTROL_SOCKET"])
path.parent.mkdir(mode=0o700)
server = FixedCoordinatorControlServer(coordinator=coordinator, campaign_id=os.environ["SO101_FIXED_CONTROL_CAMPAIGN_ID"], control_token=os.environ["SO101_FIXED_CONTROL_TOKEN"], path=path)
server.start()
try:
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        snapshot = coordinator.snapshot()
        if snapshot.terminal_reason:
            (root / "toy-stop.json").write_text(json.dumps({"reason": snapshot.terminal_reason, "fenced": all(w.stop_requested and not w.action_allowed for w in snapshot.workers.values()), "cleanup": snapshot.summary.batch_cleanup_complete}))
            break
        time.sleep(0.01)
finally:
    server.close()
    journal.close()
'''
    toy = replace(request, argv=(sys.executable, "-c", program), environment={
        **request.environment, "TOY_BATCH_ROOT": str(request.batch_root), "TOY_CONFIG": str(config),
    })
    execution = owner.spawn(toy)
    try:
        deadline = time.monotonic() + 3
        while not binding.control_socket.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert binding.control_socket.exists()
        result = supervisor.cancel_for_reason(reason)
        assert result.state == "STOPPING" and result.batch_cleanup_complete is False
        deadline = time.monotonic() + 3
        while owner.poll(execution).running and time.monotonic() < deadline:
            time.sleep(0.01)
        assert owner.poll(execution).exit_code == 0
        stop = json.loads((request.batch_root / "toy-stop.json").read_text())
        assert stop == {"reason": "WEB_CANCEL_REQUESTED", "fenced": True, "cleanup": False}
        assert store.batch(request.batch_id).cleanup_receipt_sha256 is None
        assert store.recovery_fence(request.campaign_id) is None
    finally:
        owner._children[execution.pid].wait(timeout=5)
        store.close()


def test_missing_fixed_channel_preserves_child_and_durably_fences_recovery(tmp_path):
    supervisor, store, request = _bound_without_execution(tmp_path)
    owner = ExecutionProcessOwner(store=store)
    supervisor.process_owner = owner
    toy = replace(request, argv=(sys.executable, "-c", "import time; time.sleep(0.8)"))
    execution = owner.spawn(toy)
    root = store.root
    try:
        with pytest.raises(ControlProtocolError, match="COORDINATOR_SOCKET_UNAVAILABLE"):
            supervisor.cancel_for_reason("USER_CANCELLED")
        assert owner.poll(execution).running
        fence = store.recovery_fence(request.campaign_id)
        assert fence["reason"] == "COORDINATOR_SOCKET_UNAVAILABLE"
        assert store.has_recovery_fence() is True
        assert store.batch(request.batch_id).cleanup_receipt_sha256 is None
    finally:
        owner._children[execution.pid].wait(timeout=3)
        store.close()
    reopened = SupervisorStore.open(root)
    try:
        assert reopened.recovery_fence(request.campaign_id)["reason"] == "COORDINATOR_SOCKET_UNAVAILABLE"
        assert reopened.has_recovery_fence() is True
    finally:
        reopened.close()


def test_lease_expiry_does_not_cancel_an_already_exited_owner_without_descendants(tmp_path):
    """A retained binding is not evidence that the completed batch can be cancelled."""
    supervisor, _, store = _supervisor(tmp_path)
    owner = ExecutionProcessOwner(cleanup_checker=lambda _: True)
    supervisor.process_owner = owner
    root = (tmp_path / "batch").resolve()
    execution = owner.spawn(CoordinatorStartRequest(
        campaign_id="campaign-a", batch_id="batch-a", execution_mode="SEQUENTIAL",
        worker_count=1, max_points_per_worker=1,
        argv=(sys.executable, "-c", "import time; time.sleep(0.2)"),
        environment={}, batch_root=root, control_socket=root / "control.sock",
        control_token_sha256="a" * 64,
    ))
    try:
        deadline = time.monotonic() + 3
        while owner.poll(execution).running and time.monotonic() < deadline:
            time.sleep(0.01)
        status = owner.poll(execution)
        assert status.exit_code == 0 and not status.descendants_alive
        assert owner.active_execution == execution
        assert supervisor.has_unresolved_campaign() is False
        clock = [1_000]
        lease_service = ValidationLeaseService(
            store, supervisor, clock_ns=lambda: clock[0], duration_ns=100,
        )
        lease = lease_service.acquire("browser-a")
        clock[0] = lease.expires_monotonic_ns
        assert lease_service.expire_due() is True
        assert lease_service.current() is None
        assert supervisor.has_unresolved_campaign() is False
    finally:
        if owner.poll(execution).running:
            owner.stop_after_cleanup(execution)
        store.close()


def test_cancel_for_reason_still_delegates_to_the_live_exact_adaptive_wrapper(tmp_path):
    supervisor, _, store = _supervisor(tmp_path)
    owner = ExecutionProcessOwner()
    supervisor.process_owner = owner
    request = _adaptive_owner_request(tmp_path / "adaptive")
    execution = owner.spawn(request)
    try:
        deadline = time.monotonic() + 3
        handshake = request.runtime_root / "handshake.json"
        while not handshake.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert handshake.is_file()
        assert supervisor.has_unresolved_campaign() is True
        supervisor.cancel_for_reason("LEASE_EXPIRED")
        deadline = time.monotonic() + 3
        while owner.poll(execution).running and time.monotonic() < deadline:
            time.sleep(0.01)
        status = owner.poll(execution)
        assert not status.running and not status.descendants_alive
        assert json.loads((request.runtime_root / "cleanup.json").read_text())["cleanup_complete"] is True
    finally:
        if owner.poll(execution).running:
            owner.request_cancel(execution)
            deadline = time.monotonic() + 3
            while owner.poll(execution).running and time.monotonic() < deadline:
                time.sleep(0.01)
        store.close()


def test_sequential_and_parallel_use_same_coordinator_path(tmp_path):
    supervisor, owner, store = _supervisor(tmp_path)
    try:
        asyncio.run(supervisor.start_first_pass(_request(tmp_path / "seq", "SEQUENTIAL")))
        asyncio.run(
            supervisor.start_first_pass(
                _request(
                    tmp_path / "par",
                    "PARALLEL",
                    campaign_id="campaign-2",
                    batch_id="b002",
                    manifest_id="manifest-2",
                    worker_count=2,
                )
            )
        )
        assert [type(request).__name__ for request in owner.requests] == [
            "CoordinatorStartRequest",
            "CoordinatorStartRequest",
        ]
        assert [
            (request.worker_count, request.max_points_per_worker)
            for request in owner.requests
        ] == [(1, None), (2, None)]
        assert [request.selected_point_ids for request in owner.requests] == [
            tuple(f"point_{index}" for index in range(1, 5)),
            tuple(f"point_{index}" for index in range(1, 5)),
        ]
    finally:
        store.close()


def test_installed_coordinator_is_discoverable_on_child_path(tmp_path):
    supervisor, owner, store = _supervisor(tmp_path)
    coordinator = tmp_path / "install/lib/so101_demo_py/so101_parallel_batch"
    coordinator.parent.mkdir(parents=True)
    coordinator.write_text("console\n", encoding="utf-8")
    try:
        request = _request(
            tmp_path / "seq",
            "SEQUENTIAL",
            coordinator_executable_path=coordinator.resolve(),
            environment={"PATH": "/usr/bin"},
        )
        asyncio.run(supervisor.start_first_pass(request))

        assert owner.requests[-1].environment["PATH"] == (
            f"{coordinator.parent.resolve()}:/usr/bin"
        )
        assert owner.requests[-1].environment["SO101_PARALLEL_IPC_BASE"] == (
            f"/run/user/{os.getuid()}"
        )
    finally:
        store.close()


def test_parallel_rejection_never_spawns_or_downgrades(tmp_path):
    supervisor, owner, store = _supervisor(
        tmp_path, Resources(admitted=False, reasons=("GPU_HEADROOM",))
    )
    try:
        with pytest.raises(PreflightRejected, match="GPU_HEADROOM"):
            asyncio.run(supervisor.start_first_pass(_request(tmp_path, "PARALLEL")))
        assert owner.requests == []
    finally:
        store.close()


def test_adaptive_uses_one_wrapper_request_without_k(tmp_path):
    supervisor, owner, store = _supervisor(tmp_path)
    try:
        asyncio.run(
            supervisor.start_first_pass(_request(tmp_path, "ADAPTIVE", count=20))
        )
        request = owner.requests[-1]
        assert type(request).__name__ == "AdaptiveStartRequest"
        assert request.levels == (8, 6, 4, 2, 1)
        assert "--max-points-per-worker" not in request.argv
    finally:
        store.close()


def test_each_retry_is_a_new_n1_single_point_batch_after_prior_cleanup(tmp_path):
    supervisor, owner, store = _supervisor(tmp_path)
    try:
        request = _request(tmp_path, "SEQUENTIAL", campaign_id="campaign-retry")
        asyncio.run(supervisor.start_first_pass(request))
        owner.timeline.clear()
        asyncio.run(supervisor.start_retries("campaign-retry", ("point_1", "point_2")))
        assert owner.timeline == [
            "start-retry-001-point_1-n1-kNone",
            "cleanup-retry-001-point_1",
            "start-retry-002-point_2-n1-kNone",
            "cleanup-retry-002-point_2",
        ]
        assert store.next_retry("campaign-retry") is None
    finally:
        store.close()


def test_all_success_retry_is_explicitly_not_applicable(tmp_path):
    supervisor, _owner, store = _supervisor(tmp_path)
    try:
        request = _request(tmp_path, "SEQUENTIAL", campaign_id="campaign-success")
        asyncio.run(supervisor.start_first_pass(request))
        assert asyncio.run(supervisor.start_retries("campaign-success", ())) == {
            "status": "LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED"
        }
    finally:
        store.close()

def test_the_runner_is_spawned_with_an_interpreter_that_has_its_dependencies(tmp_path):
    """The spawn argv used to name /usr/bin/python3 literally.

    On macOS that is Apple's Python 3.9, which has no PyYAML, so the runner died during import and the
    execution barrier refused the start with EXEC_BARRIER_ACK_MISSING after its ten-second wait - an
    interpreter problem wearing a runtime problem's clothes.
    """
    _supervisor_, store, request = _bound_without_execution(tmp_path)
    try:
        assert request.argv[0] in (sys.executable, "ros2"), request.argv[:2]
        assert request.argv[0] != "/usr/bin/python3", request.argv[:2]
    finally:
        store.close()
