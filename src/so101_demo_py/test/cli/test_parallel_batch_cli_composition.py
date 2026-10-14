"""Guard refusal, worker environment, broker mount and cleanup of the composition."""

from __future__ import annotations

import json
import os
from pathlib import Path

from parallel_batch_cli_support import (
    GROUNDED_SHA,
    YOLO_SHA,
    _scratch_root,
    _socket_fixture_root,
    adaptive_argv,
    argv,
    local_start_guard,  # noqa: F401  (pytest fixtures)
    verified,
)
import pytest

from so101_demo.parallel_batch.contracts.common import (
    RunMode,
)


def test_fixed_one_worker_starts_without_any_budget_authority(tmp_path):
    """The plain v3 default path needs no profile, no promotion and no budget environment."""

    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.contracts.linux_cuda import ParallelRuntimeConfigLinuxCuda

    prepared = prepare_batch(argv(tmp_path / "w1", worker_count="1"),
                             provenance_verifier=verified)
    assert isinstance(prepared.config, ParallelRuntimeConfigLinuxCuda)
    assert prepared.start_guard is not None
    assert prepared.start_guard_evidence["status"] in ("PASS", "WARN")
    assert prepared.start_guard_evidence["cleanup_state"] == "CLEAR"
    assert prepared.start_guard_evidence["checks"]["ram"]["unit"] == "bytes"
    assert prepared.request.worker_count == 1
    assert prepared.manifest["schema_version"] == 3
    assert prepared.manifest["start_guard"]["policy"] == {
        key: prepared.start_guard_evidence["policy"][key]
        for key in ("timeout_s", "cpu_busy_warn_fraction", "ram_minimum_bytes",
                    "ram_minimum_fraction", "gpu_minimum_bytes")}
    assert prepared.manifest["start_guard"]["cleanup_state"] == "CLEAR"
    assert "status" not in prepared.manifest["start_guard"]
    assert "live_headroom" not in prepared.manifest


def test_a_failing_guard_refuses_the_start_instead_of_allocating(tmp_path):
    """A FAIL from the real decision must surface as a CLI error, never a partial batch."""

    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch import start_guard_probe as probe_module
    from so101_demo.parallel_batch.start_guard import GuardCheck, GuardResult

    def refusing_check(self, policy, scope):
        return GuardResult(scope=scope, status="FAIL", started_monotonic_s=0.0,
                           completed_monotonic_s=0.0,
                           checks={"probe": GuardCheck("FAIL", "GPU_TARGET_NOT_VISIBLE",
                                                       None, None, "state")},
                           snapshot=None, cleanup_state="CLEAR")

    original = probe_module.ProbeCoordinator.check
    probe_module.ProbeCoordinator.check = refusing_check
    try:
        with pytest.raises(CliError, match="GPU_TARGET_NOT_VISIBLE"):
            prepare_batch(argv(tmp_path / "w1-refused", worker_count="1"),
                          provenance_verifier=verified)
    finally:
        probe_module.ProbeCoordinator.check = original


@pytest.mark.skip(reason="the adaptive entry is refused (NATIVE_MULTI_WORKER_UNSUPPORTED); this test is deleted with the pool in the removal plan Task 5")
def test_production_adaptive_factory_builds_an_internal_eight_worker_pool(tmp_path, monkeypatch):
    from dataclasses import replace

    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.adaptive_contracts import (
        PoolRequest,
        _new_pool_request_for_production_factory,
    )
    from so101_demo.parallel_batch.adaptive_pool import (
        ProductionAdaptivePoolFactory,
    )
    from so101_demo.parallel_batch.resource_allocation.models import runtime_ipc_base

    monkeypatch.setenv('SO101_PARALLEL_IPC_BASE', str(runtime_ipc_base()))

    evidence_root = Path(
        "/data/work/so101-evidence/parallel-adaptive-worker/20260914-a01"
    )
    prepared = prepare_batch(
        adaptive_argv(
            tmp_path / "source",
            batch_id="abcde",
            point_id=("task_start",),
        ),
        provenance_verifier=verified,
    )
    prepared = replace(
        prepared,
        adaptive_request=replace(
            prepared.adaptive_request,
            evidence_root=evidence_root,
        ),
    )
    request = _new_pool_request_for_production_factory(
        batch_id="abcde-g01-w08",
        run_mode=RunMode.DRY_RUN,
        selected_point_ids=("task_start",),
        worker_count=8,
        evidence_root=evidence_root / "r/abcde/p/g01w08",
    )

    pool = ProductionAdaptivePoolFactory(
        prepared,
        composition_factory=lambda *_args, **_kwargs: None,
    )(request)

    assert isinstance(pool.prepared.request, PoolRequest)
    assert pool.context.request.worker_count == 8
    assert pool.context.options.worker_count == 8
    assert pool.context.selector.choose("worker-08", ("task_start",)) == "task_start"


def test_worker_process_environment_is_the_exact_pick_place_validation_whitelist(tmp_path):
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    class Supervisor:
        def __init__(self):
            self.environments = []
        def start(self, _role, _command, *, environment=None):
            self.environments.append(dict(environment))

    monkey = "SO101_TEST_SECRET_MUST_NOT_LEAK"
    os.environ[monkey] = "secret"
    scratch = _scratch_root()
    spec = prepare_batch(
        argv(scratch / "x", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {**verified(value), "image_id": "sha256:" + "b" * 64},
    )
    supervisor = Supervisor()
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "xc",
        supervisor=supervisor, broker_command_builder=lambda _owner: ("broker",),
    )
    try:
        composition._start_workers()
        assert supervisor.environments == [
            dict(composition.resource_manifest.workers[0].environment)
        ]
        assert monkey not in supervisor.environments[0]
    finally:
        composition._release_partial()
        os.environ.pop(monkey, None)


def test_broker_runtime_mount_cannot_see_worker_tokens_or_coordinator_sockets(tmp_path):
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.cli.parallel_perception_broker import container_run_argv
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    scratch = _scratch_root()
    spec = prepare_batch(
        argv(scratch / "b", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {**verified(value), "image_id": "sha256:" + "b" * 64},
    )
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "bc",
        broker_command_builder=lambda _owner: ("broker",),
    )
    try:
        runtime_root = composition.broker_spec_path.parent
        assert not list(runtime_root.glob("worker-*.token"))
        assert not list(runtime_root.glob("worker-*.sock"))
        command = container_run_argv(
            spec.request.evidence_root, runtime_root=runtime_root,
            input_root=composition.broker_input_root,
            image_id="sha256:" + "b" * 64,
            yolo_weights=spec.yolo_weights, grounded_root=spec.grounded_root,
            gpu_groups=[44], uid=os.getuid(), gid=os.getgid(),
            batch_id=spec.request.batch_id, broker_generation=1,
            path_checker=lambda path, **_kwargs: Path(path),
        )
        runtime_mounts = [
            command[index + 1] for index, value in enumerate(command) if value == "--volume"
        ]
        assert f"{runtime_root}:/runtime:rw" in runtime_mounts
        assert f"{composition.broker_input_root}:/inputs:ro" in runtime_mounts
        assert all(f"{spec.request.evidence_root / 'workers'}:/inputs" not in mount
                   for mount in runtime_mounts)
        assert all(str(composition.authority.ipc_root) + ":/runtime" not in mount for mount in runtime_mounts)
    finally:
        composition._release_partial()


@pytest.mark.parametrize(
    "operation,payload",
    [
        ("register_worker", {"generation": 1, "recovery_deadline_monotonic_s": None}),
        ("grant_lease", {"generation": 1}),
        ("heartbeat", {}),
        ("ack_lease", {}),
        ("ack_validation_started", {"gate_summary": {}}),
        ("begin_finalizing", {}),
        ("commit_validation", {"location": "/sealed"}),
        ("record_recovery", {
            "generation": 1, "succeeded": False, "fenced": False,
            "owned_processes_stopped": False, "controllers_stopped": False,
            "readmitted": False, "recovery_deadline_monotonic_s": 1.0,
        }),
        ("replace_resources", {"expected_generation": 1}),
    ],
)
def test_coordinator_rpc_payload_schema_rejects_extra_and_missing_before_mutation(
    operation, payload
):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.rpc_proxies import _validate_rpc_payload

    valid = {"operation": operation, **payload}
    assert _validate_rpc_payload(valid) == valid
    with pytest.raises(CliError, match="RPC_PAYLOAD_SCHEMA"):
        _validate_rpc_payload({**valid, "extra": True})
    removable = next(name for name in valid if name != "operation") if len(valid) > 1 else "operation"
    with pytest.raises(CliError, match="RPC_PAYLOAD_SCHEMA"):
        _validate_rpc_payload({name: value for name, value in valid.items() if name != removable})


def test_constructor_failure_releases_partial_allocator_journal_and_endpoints(tmp_path, monkeypatch):
    import so101_demo.cli.mujoco_batch.composition as batch_cli
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    scratch = _scratch_root()
    spec = prepare_batch(
        argv(scratch / "f", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {**verified(value), "image_id": "sha256:" + "b" * 64},
    )
    real = batch_cli.AuthenticatedUnixServer
    calls = []

    def fail_first(*args, **kwargs):
        if not calls:
            raise RuntimeError("constructor fault")
        calls.append(real(*args, **kwargs))
        return calls[-1]

    monkeypatch.setattr(batch_cli, "AuthenticatedUnixServer", fail_first)
    with pytest.raises(RuntimeError, match="constructor fault") as raised:
        ProductionBatchComposition(
            spec, resource_probe=Probe(), claim_root=scratch / "fc"
        )
    assert raised.value.startup_stage == "worker_ipc"
    assert raised.value.partial_cleanup == {
        "worker_servers": [],
        "journal": {"succeeded": True, "error_type": None, "error_message": None},
        "allocator": {"succeeded": True, "error_type": None, "error_message": None},
    }
    assert all(server.path.exists() is False for server in calls)
    assert not (scratch / "fc" / spec.request.batch_id).exists()


def test_composition_cleanup_invokes_real_worker_control_actions_in_order():
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    events = []

    class Coordinator:
        def request_stop(self, *, reason):
            events.append(("stop", reason))
            return True

    class Control:
        def call(self, operation):
            events.append((operation,))
            return True

    owner = object.__new__(ProductionBatchComposition)
    owner.coordinator = Coordinator()
    owner.worker_controls = [Control(), Control()]
    assert owner._stop_new_leases() is True
    assert owner._cancel_worker_goals() is True
    assert owner._confirm_worker_goals_cancelled() is True
    assert owner._request_worker_recovery() is True
    assert events == [
        ("stop", "SUPERVISOR_SHUTDOWN"),
        ("stop",), ("stop",),
        ("cancel_motion",), ("cancel_motion",),
        ("confirm_no_controller_goal",), ("confirm_no_controller_goal",),
        ("recover",), ("recover",),
    ]


def test_cleanup_skips_dead_control_rpc_after_worker_groups_are_reaped():
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    class Control:
        def call(self, _operation):
            raise AssertionError("a reaped Worker has no live control socket")

    owner = object.__new__(ProductionBatchComposition)
    owner.worker_controls = [Control(), Control()]
    owner._worker_children_reaped = True

    assert owner._worker_control("cancel_motion") is True


def test_broker_ready_receipt_is_exactly_bound_to_batch_generation_and_image():
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.outcome import _validate_broker_ready

    expected = {
        "batch_id": "batch-1", "run_mode": "plan_only", "coordinator_epoch": 3,
        "broker_generation": 1, "image_id": "sha256:" + "b" * 64,
        "yolo_weights_sha256": YOLO_SHA,
        "grounded_manifest_sha256": GROUNDED_SHA,
    }
    receipt = {
        "schema_version": 1, "kind": "so101_parallel_broker_ready",
        **expected,
        "models": {
            "plastic-cup-yolo11n-seg-v1": {"ready": True, "weights_sha256": YOLO_SHA},
            "grounded-sam": {"ready": True, "manifest_sha256": GROUNDED_SHA},
        },
    }
    assert _validate_broker_ready(receipt, expected) is True
    for mutation in ({}, {**receipt, "broker_generation": 2}, {**receipt, "extra": True}):
        with pytest.raises(CliError, match="BROKER_READY_RECEIPT"):
            _validate_broker_ready(mutation, expected)


def test_physical_start_revalidates_complete_provenance_before_process_side_effect(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    record = {
        **verified({}), "image_id": "sha256:" + "b" * 64,
        "source_tree_sha256": "c" * 64, "source_dirty": False,
        "installed_console_sha256": "d" * 64, "installed_module_sha256": "e" * 64,
    }
    scratch = _scratch_root()
    spec = prepare_batch(
        argv(scratch / "v", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda _value: record,
    )

    class Supervisor:
        def __init__(self):
            self.started = []
        def start(self, *args, **kwargs):
            self.started.append((args, kwargs))

    supervisor = Supervisor()
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "vc",
        supervisor=supervisor, broker_command_builder=lambda _owner: ("broker",),
        provenance_revalidator=lambda _inputs: {**record, "source_dirty": True},
    )
    try:
        with pytest.raises(CliError, match="PROVENANCE_DRIFT"):
            composition._start_broker()
        assert supervisor.started == []
    finally:
        composition._release_partial()


def test_crashed_worker_recovery_terminates_only_exact_recorded_children(tmp_path):
    import signal

    from so101_demo.cli.mujoco_batch.rpc_proxies import _WorkerControlProxy

    token = tmp_path / "control.token"
    token.write_text("ab" * 32, encoding="ascii")
    token.chmod(0o600)
    manifest = tmp_path / "children.json"
    manifest.write_text(json.dumps({
        "schema_version": 1,
        "processes": [{
            "role": "task-station", "pid": 711, "pgid": 700,
            "cmdline": ["task-station"], "start_time_ticks": 91,
        }],
    }), encoding="utf-8")
    manifest.chmod(0o600)
    alive = {711: (700, ("task-station",), 91)}
    signals = []

    def send(pid, value):
        signals.append((pid, value))
        alive.pop(pid, None)

    proxy = _WorkerControlProxy(
        tmp_path / "absent.sock", token,
        worker_id="worker-01", generation=1, coordinator_epoch=1,
        deadline_s=0.1, orphan_manifest=manifest,
        identity_probe=lambda pid: alive.get(pid, (0, (), 0)),
        signal_process=send,
    )
    assert proxy.call("cancel_motion") is False
    assert proxy.call("recover") is True
    assert signals == [(711, signal.SIGINT)]


def test_worker_control_proxy_completes_real_authenticated_socket_round_trip(tmp_path):
    import threading

    from so101_demo.cli.mujoco_batch.rpc_proxies import _WorkerControlProxy
    from so101_demo.runtime.parallel_ipc.authority import (
        AuthenticatedUnixServer,
        WorkerTokenAuthority,
    )

    authority = WorkerTokenAuthority(
        _socket_fixture_root(tmp_path, "proxy"), coordinator_epoch=3)
    token = authority.issue("worker-01-control", 1)
    endpoint = authority.ipc_root / "worker-01-control.sock"
    calls = []
    server = AuthenticatedUnixServer(
        endpoint,
        authority,
        lambda message: calls.append(message["payload"]["operation"])
        or {"completed": True},
        deadline_s=1.0,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        proxy = _WorkerControlProxy(
            endpoint, token, worker_id="worker-01", generation=1,
            coordinator_epoch=3, deadline_s=1.0,
        )
        for operation in (
            "stop", "cancel_motion", "confirm_no_controller_goal", "recover"
        ):
            assert proxy.call(operation) is True
        assert calls == [
            "stop", "cancel_motion", "confirm_no_controller_goal", "recover"
        ]
    finally:
        server.close()
        thread.join(timeout=1.0)
