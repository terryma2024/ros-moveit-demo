"""Broker start, readiness, cleanup and exit capture of the parallel batch composition."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from parallel_batch_cli_support import (
    _scratch_root,
    argv,
    local_start_guard,  # noqa: F401  (pytest fixtures)
    verified,
)
import pytest

from so101_demo.parallel_batch.contracts.common import (
    PointStatus,
    RunMode,
)


def test_default_production_composition_derives_real_dry_run_snapshot():
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.coordinator import BatchCoordinator
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot
    from so101_demo.parallel_batch.resources import WorkerResourceAllocator
    from so101_demo.parallel_batch.worker import ParallelWorker
    from so101_demo.runtime.parallel_worker_runtime import DryRunWorkerRuntime

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    scratch = _scratch_root()
    root = scratch / "pc"
    spec = prepare_batch(
        argv(
            root,
            worker_count="1",
                        point_id=("task_start",),
        ),
        provenance_verifier=verified,
    )
    composition = ProductionBatchComposition(
        spec,
        resource_probe=Probe(),
        claim_root=scratch / "claims",
        worker_launcher=lambda owner, path: owner._run_worker_local(path),
    )
    assert isinstance(composition.allocator, WorkerResourceAllocator)
    assert isinstance(composition.coordinator, BatchCoordinator)
    assert not hasattr(composition, "broker")
    assert composition.broker_spec_path is None
    assert composition.results is not composition.result_verifier
    # the port is chosen by the contract it must implement (correction 4): without an episode scope the generic
    # adapter keeps its own paths, exactly as the coordinator's ACT gate requires; with one the composition
    # builds the verifying class the gate selects, so a real ACT episode takes that path
    from so101_demo.act.result_store import ActCollectionResultVerifier

    # stated as "not the ACT class" rather than "is this other class", because this codebase has two adapter classes
    # under similar names and the contract is about which one the coordinator's gate recognises
    assert not isinstance(composition.result_verifier, ActCollectionResultVerifier)
    # The positive direction needs a spec whose evidence root does not collide with the one this composition already
    # claimed, and the file's own idiom for that is to rebind it. With the episode scope present the
    # composition must build the class the coordinator's gate selects, so a real ACT episode takes that path.
    judging = ProductionBatchComposition(
        replace(spec, request=replace(spec.request, evidence_root=scratch / "act-evidence")),
        resource_probe=Probe(),
        claim_root=scratch / "claims-act",
        worker_launcher=lambda owner, path: owner._run_worker_local(path),
        episode_scope_path=str(scratch / "original-common-scope.json"),
    )
    assert isinstance(judging.result_verifier, ActCollectionResultVerifier)
    assert judging.result_verifier.scope == scratch / "original-common-scope.json"
    assert judging.coordinator.result_port is judging.result_verifier
    summary = composition.run()
    assert isinstance(composition.last_local_components[0], ParallelWorker)
    assert isinstance(composition.last_local_components[1], DryRunWorkerRuntime)
    assert summary.validation_passed is True
    assert summary.qualification_passed is False
    assert summary.point_statuses == {"task_start": PointStatus.UNRUN}
    aggregate = json.loads((root / "coordinator/aggregate_results.json").read_text())
    assert aggregate["validation_passed"] is True
    assert aggregate["qualification_passed"] is False


def test_physical_composition_prepares_and_supervises_one_external_broker(
    tmp_path,
):
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
            self.started = []

        def start(self, role, command, **_kwargs):
            self.started.append((role, tuple(command)))

    scratch = _scratch_root()
    root = scratch / "eb"
    supervisor = Supervisor()
    spec = prepare_batch(
        argv(
            root,
            worker_count="1",
                        point_id=("task_start",),
            run_mode="plan_only",
        ),
        provenance_verifier=lambda _spec: {
            **verified(_spec),
            "image_id": "sha256:" + "b" * 64,
        },
    )
    composition = ProductionBatchComposition(
        spec,
        resource_probe=Probe(),
        claim_root=scratch / "external-broker-claims",
        supervisor=supervisor,
        broker_command_builder=lambda owner: (
            "docker",
            "run",
            str(owner.broker_spec_path),
        ),
    )

    assert not hasattr(composition, "broker")
    broker_spec = json.loads(composition.broker_spec_path.read_text())
    assert broker_spec["broker_generation"] == 1
    assert broker_spec["coordinator_epoch"] == composition.journal.coordinator_epoch
    assert "authority_endpoint" not in broker_spec
    assert "queue_capacity_per_model" not in broker_spec
    assert broker_spec["config_path"] == "/runtime/runtime-config.yaml"
    assert "authority_token_path" not in broker_spec
    worker_spec = json.loads(composition.worker_specs[0].read_text())
    assert worker_spec["broker_socket_path"] == str(root / "ipc/broker/perception.sock")
    assert worker_spec["broker_generation"] == 1
    composition._start_broker()
    assert supervisor.started == [
        ("broker", ("docker", "run", str(composition.broker_spec_path)))
    ]
    composition._release_partial()


def test_physical_broker_receives_validated_external_ipc_root(tmp_path, monkeypatch):
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    import so101_demo.cli.parallel_perception_broker as broker_cli
    from so101_demo.parallel_batch.resource_allocation.models import (
        ResourceSnapshot,
        runtime_ipc_base,
    )

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

        def start(self, role, command):
            self.started.append((role, tuple(command)))
            return SimpleNamespace(role=role)

    batch_id = 't23-broker-call'
    runtime_base = runtime_ipc_base()
    monkeypatch.setenv('SO101_PARALLEL_IPC_BASE', str(runtime_base))
    record = {
        **verified({}),
        'image_id': 'sha256:' + 'b' * 64,
    }
    spec = prepare_batch(
        argv(
            tmp_path / 'batch',
            batch_id=batch_id,
            worker_count='1',
            point_id=('task_start',),
            run_mode='plan_only',
        ),
        provenance_verifier=lambda _value: record,
    )
    supervisor = Supervisor()
    captured = {}
    monkeypatch.setattr(broker_cli, 'image_record', lambda _image: {
        'image_id': record['image_id'],
    })
    monkeypatch.setattr(broker_cli, 'gpu_groups', lambda: [44])

    def command_builder(batch_root, **kwargs):
        captured.update(batch_root=batch_root, **kwargs)
        return ('docker', 'run', 'broker')

    monkeypatch.setattr(broker_cli, 'container_run_argv', command_builder)
    composition = ProductionBatchComposition(
        spec,
        resource_probe=Probe(),
        claim_root=tmp_path / 'claims',
        supervisor=supervisor,
    )
    try:
        composition._start_broker()
        assert captured['runtime_ipc_root'] == runtime_base / f'so101-{batch_id}'
        assert captured['runtime_root'] == captured['runtime_ipc_root'] / 'broker'
        assert supervisor.started == [('broker', ('docker', 'run', 'broker'))]
    finally:
        composition._release_partial()
        assert composition._release_runtime_ipc_root() is True


def test_physical_worker_launches_receive_exact_isolated_environments(tmp_path):
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
            self.calls = []
        def start(self, role, command, *, environment=None):
            self.calls.append((role, tuple(command), dict(environment or {})))

    scratch = _scratch_root()
    spec = prepare_batch(
        argv(
            scratch / "e", worker_count="2",             point_id=("task_start", "sample_01_near_left"), run_mode="plan_only",
        ),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    supervisor = Supervisor()
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "ec",
        supervisor=supervisor, broker_command_builder=lambda _owner: ("broker",),
    )
    composition._start_workers()
    environments = [call[2] for call in supervisor.calls]
    resources = composition.resource_manifest.workers
    assert [env["ROS_DOMAIN_ID"] for env in environments] == [
        str(item.ros_domain_id) for item in resources
    ]
    assert [env["ROS_HOME"] for env in environments] == [
        str(item.ros_home) for item in resources
    ]
    assert [env["SO101_SESSION_ID"] for env in environments] == [
        item.session_id for item in resources
    ]
    assert len(set(env["ROS_DOMAIN_ID"] for env in environments)) == 2
    composition._release_partial()


def test_broker_start_rejects_missing_image_id_and_mutable_tag_drift(tmp_path, monkeypatch):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    import so101_demo.cli.parallel_perception_broker as broker_cli
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    scratch = _scratch_root()
    base = prepare_batch(
        argv(scratch / "im", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=verified,
    )
    missing = ProductionBatchComposition(
        base, resource_probe=Probe(), claim_root=scratch / "imc"
    )
    with pytest.raises(CliError, match="IMAGE_ID_REQUIRED"):
        missing._start_broker()
    missing._release_partial()

    bound = prepare_batch(
        argv(scratch / "id", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
            "source_sha256": "1" * 64,
        },
    )
    drift = ProductionBatchComposition(
        bound, resource_probe=Probe(), claim_root=scratch / "idc"
    )
    monkeypatch.setattr(broker_cli, "image_record", lambda _tag: {
        "image_id": "sha256:" + "c" * 64, "source_sha256": "1" * 64,
    })
    with pytest.raises(CliError, match="TAG_DRIFT"):
        drift._start_broker()
    drift._release_partial()


def test_workers_cannot_start_until_broker_socket_and_ready_receipt_exist(tmp_path):
    import threading

    from so101_demo.cli.mujoco_batch.common import _write_json
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot
    from so101_demo.runtime.parallel_ipc.broker_transport import BrokerTransport

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    class Supervisor:
        processes = ()
        def __init__(self):
            self.health_checks = 0
        def start(self, *_args, **_kwargs):
            return None
        def assert_healthy(self):
            self.health_checks += 1

    scratch = _scratch_root()
    spec = prepare_batch(
        argv(scratch / "br", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    supervisor = Supervisor()
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "brc",
        supervisor=supervisor, broker_command_builder=lambda _owner: ("broker",),
    )
    composition._uses_production_broker_container = True
    composition.broker_container_id_path.write_text("c" * 64 + "\n", encoding="ascii")
    composition.broker_container_id_path.chmod(0o664)
    broker_server = None
    try:
        ready = {
            "schema_version": 1,
            "kind": "so101_parallel_broker_ready",
            "batch_id": spec.request.batch_id,
            "run_mode": spec.request.run_mode.value,
            "coordinator_epoch": composition.journal.coordinator_epoch,
            "broker_generation": 1,
            "image_id": spec.provenance["image_id"],
            "yolo_weights_sha256": spec.yolo_weights_sha256,
            "grounded_manifest_sha256": spec.grounded_manifest_sha256,
            "models": {
                "plastic-cup-yolo11n-seg-v1": {
                    "ready": True,
                    "weights_sha256": spec.yolo_weights_sha256,
                },
                "grounded-sam": {
                    "ready": True,
                    "manifest_sha256": spec.grounded_manifest_sha256,
                },
            },
        }
        transport = BrokerTransport(
            ipc_root=composition.broker_runtime_root,
            config=spec.config,
            generation=1,
            deadline_s=1.0,
        )
        transport.bind_ready_identity(ready)
        broker_server = transport.server(
            SimpleNamespace(), endpoint=composition.broker_socket_path
        )
        broker_thread = threading.Thread(
            target=broker_server.serve_forever, daemon=True
        )
        broker_thread.start()
        _write_json(composition.broker_runtime_root / "ready.json", ready)
        assert composition._wait_broker_ready() is True
        assert composition.broker_container_id_path.stat().st_mode & 0o777 == 0o600
        assert supervisor.health_checks >= 1
    finally:
        if broker_server is not None:
            broker_server.close()
            broker_thread.join(timeout=1.0)
        composition._stop_servers()
        composition._release_partial()


def test_broker_ready_rejects_regular_file_endpoint(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError, _write_json
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot

    class Probe:
        def snapshot(self): return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain): return False
        def socket_in_use(self, _path): return False

    class Supervisor:
        processes = ()
        def assert_healthy(self): return None

    scratch = _scratch_root()
    spec = prepare_batch(
        argv(scratch / "ns", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "nsc",
        supervisor=Supervisor(), broker_command_builder=lambda _owner: ("broker",),
    )
    try:
        composition.broker_socket_path.write_bytes(b"not a socket")
        composition.broker_socket_path.chmod(0o600)
        _write_json(composition.broker_runtime_root / "ready.json", {})
        with pytest.raises(CliError, match="BROKER_READY"):
            composition._wait_broker_ready()
    finally:
        composition._release_partial()


def test_initial_broker_ready_uses_broker_startup_budget_not_heartbeat(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot

    class Probe:
        def snapshot(self): return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain): return False
        def socket_in_use(self, _path): return False

    class Supervisor:
        processes = ()
        def assert_healthy(self): return None

    class Clock:
        value = 100.0
        def __call__(self): return self.value
        def sleep(self, _seconds): self.value += 10.0

    scratch = _scratch_root()
    clock = Clock()
    spec = prepare_batch(
        argv(scratch / "s", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "sc",
        supervisor=Supervisor(), broker_command_builder=lambda _owner: ("broker",),
        clock=clock, sleep=clock.sleep,
    )
    try:
        with pytest.raises(CliError, match="BROKER_READY_TIMEOUT"):
            composition._wait_broker_ready()
        assert clock.value - 100.0 >= spec.config.broker_recovery_timeout_s
        assert clock.value - 100.0 < spec.config.broker_recovery_timeout_s + 10.0
    finally:
        composition._release_partial()


def test_broker_container_cleanup_stops_only_exact_labeled_batch_container(tmp_path):
    from types import SimpleNamespace

    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot

    class Probe:
        def snapshot(self): return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain): return False
        def socket_in_use(self, _path): return False

    scratch = _scratch_root()
    spec = prepare_batch(
        argv(scratch / "c", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    calls = []
    container_id = "c" * 64

    def run(command, **_kwargs):
        calls.append(tuple(command))
        if command[1] == "inspect" and len(calls) == 1:
            document = [{
                "Id": container_id,
                "Image": spec.provenance["image_id"],
                "Config": {"Labels": {
                    "com.so101.batch-id": spec.request.batch_id,
                    "com.so101.broker-generation": "1",
                }},
                "Mounts": [
                    {"Source": str(composition.broker_runtime_root),
                     "Destination": "/runtime"},
                    {"Source": str(composition.broker_input_root),
                     "Destination": "/inputs"},
                ],
            }]
            return SimpleNamespace(returncode=0, stdout=json.dumps(document), stderr="")
        if command[1] == "stop":
            return SimpleNamespace(returncode=0, stdout=container_id, stderr="")
        return SimpleNamespace(returncode=1, stdout="", stderr="absent")

    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "cc",
        container_runner=run,
    )
    try:
        composition.broker_container_id_path.write_text(container_id + "\n")
        composition.broker_container_id_path.chmod(0o600)
        assert composition._retire_broker_container() is True
        assert calls[0][:4] == ("docker", "inspect", "--type", "container")
        assert calls[1][:3] == ("docker", "stop", "--timeout")
        assert calls[2][:4] == ("docker", "inspect", "--type", "container")
    finally:
        composition._release_partial()


def test_broker_cleanup_accepts_exact_container_removed_during_stop_race(tmp_path):
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    owner = object.__new__(ProductionBatchComposition)
    owner._uses_production_broker_container = True
    owner.broker_spec_path = tmp_path / "broker-spec.json"
    owner.broker_generation = 1
    owner.broker_runtime_root = tmp_path / "ipc"
    owner.broker_input_root = tmp_path / "inputs"
    owner.broker_runtime_root.mkdir()
    owner.broker_input_root.mkdir()
    owner.broker_container_id_path = owner.broker_runtime_root / "container.cid"
    container_id = "c" * 64
    owner.broker_container_id_path.write_text(container_id + "\n", encoding="ascii")
    owner.broker_container_id_path.chmod(0o600)
    owner.spec = SimpleNamespace(
        provenance={"image_id": "sha256:" + "b" * 64},
        request=SimpleNamespace(batch_id="batch-1"),
        config=SimpleNamespace(heartbeat_timeout_s=1.0),
    )
    inspections = iter([
        SimpleNamespace(returncode=0, stdout=json.dumps([{
            "Id": container_id,
            "Image": owner.spec.provenance["image_id"],
            "Config": {"Labels": {
                "com.so101.batch-id": "batch-1",
                "com.so101.broker-generation": "1",
            }},
            "Mounts": [
                {"Source": str(owner.broker_runtime_root), "Destination": "/runtime"},
                {"Source": str(owner.broker_input_root), "Destination": "/inputs"},
            ],
        }]), stderr=""),
        SimpleNamespace(returncode=1, stdout="", stderr="absent"),
    ])

    def run(command, **_kwargs):
        if command[1] == "inspect":
            return next(inspections)
        assert command[1] == "stop"
        return SimpleNamespace(returncode=1, stdout="", stderr="already removed")

    owner._container_runner = run
    owner._clock = lambda: 0.0
    owner._sleep = lambda _seconds: None

    assert owner._retire_broker_container() is True


def test_broker_exit_capture_persists_process_container_logs_and_events(tmp_path):
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    owner = object.__new__(ProductionBatchComposition)
    owner.broker_runtime_root = tmp_path / "broker"
    owner.broker_runtime_root.mkdir()
    owner.broker_container_id_path = owner.broker_runtime_root / "container.cid"
    container_id = "c" * 64
    owner.broker_container_id_path.write_text(container_id + "\n", encoding="ascii")
    owner.broker_container_id_path.chmod(0o600)
    state = {
        "Status": "exited",
        "Running": False,
        "Paused": False,
        "Restarting": False,
        "OOMKilled": False,
        "Dead": False,
        "Pid": 0,
        "ExitCode": 17,
        "Error": "broker crashed",
        "StartedAt": "2026-09-15T11:00:00Z",
        "FinishedAt": "2026-09-15T11:03:00Z",
    }

    def run(command, **_kwargs):
        if command[1:3] == ["inspect", "--type"]:
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([{"Id": container_id, "State": state}]),
                stderr="",
            )
        if command[1] == "logs":
            return SimpleNamespace(returncode=0, stdout="last broker line\n", stderr="")
        assert command[1] == "events"
        return SimpleNamespace(
            returncode=0,
            stdout='{"status":"die","exitCode":"17"}\n',
            stderr="",
        )

    owner._container_runner = run
    process = SimpleNamespace(
        role="broker", pid=123, pgid=123, start_time=456,
        cmdline=("docker", "run"), batch_id="a001-g01-w10",
    )

    owner._capture_broker_exit_evidence(process, 17)

    report = json.loads(
        (owner.broker_runtime_root / "broker-exit.json").read_text(encoding="utf-8")
    )
    assert report["process"] == {
        "role": "broker",
        "pid": 123,
        "pgid": 123,
        "start_time": 456,
        "exit_code": 17,
    }
    assert report["container"]["id"] == container_id
    assert report["container"]["state"] == state
    assert report["logs"] == {"returncode": 0, "stdout": "last broker line\n", "stderr": ""}
    assert report["events"]["stdout"] == '{"status":"die","exitCode":"17"}\n'


def test_broker_cleanup_waits_for_exact_auto_remove_after_successful_stop(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    owner = object.__new__(ProductionBatchComposition)
    owner._uses_production_broker_container = True
    owner.broker_spec_path = tmp_path / "broker-spec.json"
    owner.broker_generation = 1
    owner.broker_runtime_root = tmp_path / "ipc"
    owner.broker_input_root = tmp_path / "inputs"
    owner.broker_runtime_root.mkdir()
    owner.broker_input_root.mkdir()
    owner.broker_container_id_path = owner.broker_runtime_root / "container.cid"
    container_id = "c" * 64
    owner.broker_container_id_path.write_text(container_id + "\n", encoding="ascii")
    owner.broker_container_id_path.chmod(0o600)
    owner.spec = SimpleNamespace(
        provenance={"image_id": "sha256:" + "b" * 64},
        request=SimpleNamespace(batch_id="batch-1"),
        config=SimpleNamespace(heartbeat_timeout_s=1.0),
    )
    present = SimpleNamespace(
        returncode=0,
        stdout=json.dumps(
            [
                {
                    "Id": container_id,
                    "Image": owner.spec.provenance["image_id"],
                    "Config": {
                        "Labels": {
                            "com.so101.batch-id": "batch-1",
                            "com.so101.broker-generation": "1",
                        }
                    },
                    "Mounts": [
                        {
                            "Source": str(owner.broker_runtime_root),
                            "Destination": "/runtime",
                        },
                        {
                            "Source": str(owner.broker_input_root),
                            "Destination": "/inputs",
                        },
                    ],
                }
            ]
        ),
        stderr="",
    )
    absent = SimpleNamespace(returncode=1, stdout="", stderr="absent")
    inspections = iter((present, present, absent))
    calls = []

    def run(command, **_kwargs):
        calls.append(tuple(command))
        if command[1] == "inspect":
            return next(inspections)
        assert command[1] == "stop"
        return SimpleNamespace(returncode=0, stdout=container_id, stderr="")

    class Clock:
        value = 10.0

        def __call__(self):
            return self.value

        def sleep(self, seconds):
            self.value += seconds

    clock = Clock()
    owner._container_runner = run
    owner._clock = clock
    owner._sleep = clock.sleep

    assert owner._retire_broker_container() is True
    assert [call[1] for call in calls] == ["inspect", "stop", "inspect", "inspect"]
    assert clock.value > 10.0

    clock.value = 20.0
    owner._container_inspect = lambda _container_id: present
    owner._container_runner = lambda *_args, **_kwargs: SimpleNamespace(
        returncode=0, stdout=container_id, stderr=""
    )
    with pytest.raises(CliError, match="BROKER_CONTAINER_SURVIVED"):
        owner._retire_broker_container()
    assert clock.value >= 21.0


def test_broker_container_id_is_hardened_before_cleanup(tmp_path):
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    owner = object.__new__(ProductionBatchComposition)
    owner.broker_container_id_path = tmp_path / "container.cid"
    owner.broker_container_id_path.write_text("c" * 64 + "\n", encoding="ascii")
    owner.broker_container_id_path.chmod(0o664)

    assert owner._harden_broker_container_id() is True
    assert owner.broker_container_id_path.stat().st_mode & 0o777 == 0o600


def test_broker_socket_appearing_between_readiness_checks_is_snapshotted_once(
    tmp_path, monkeypatch,
):
    import socket

    from so101_demo.cli.mujoco_batch.common import _write_json
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot

    class Probe:
        def snapshot(self): return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain): return False
        def socket_in_use(self, _path): return False

    class Supervisor:
        processes = ()
        def assert_healthy(self): return None

    class HealthClient:
        def __init__(self, *_args, **_kwargs): pass
        def call(self, message):
            return {"payload": {
                "ready": ready,
                "ready_sha256": message["payload"]["ready_sha256"],
            }}

    scratch = _scratch_root()
    spec = prepare_batch(
        argv(scratch / "race", worker_count="1",              point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "race-claims",
        supervisor=Supervisor(), broker_command_builder=lambda _owner: ("broker",),
        container_brokers=False,   # the bare host program `broker` is not a container
        broker_health_client_factory=HealthClient,
    )
    ready = {
        "schema_version": 1, "kind": "so101_parallel_broker_ready",
        "batch_id": spec.request.batch_id, "run_mode": "plan_only",
        "coordinator_epoch": composition.journal.coordinator_epoch,
        "broker_generation": 1, "image_id": spec.provenance["image_id"],
        "yolo_weights_sha256": spec.yolo_weights_sha256,
        "grounded_manifest_sha256": spec.grounded_manifest_sha256,
        "models": {
            "plastic-cup-yolo11n-seg-v1": {
                "ready": True, "weights_sha256": spec.yolo_weights_sha256,
            },
            "grounded-sam": {
                "ready": True,
                "manifest_sha256": spec.grounded_manifest_sha256,
            },
        },
    }
    _write_json(composition.broker_runtime_root / "ready.json", ready)
    listener = socket.socket(socket.AF_UNIX)
    directory_fd = os.open(
        composition.broker_runtime_root, os.O_RDONLY | os.O_DIRECTORY
    )
    original_lstat = Path.lstat
    checks = 0

    def racing_lstat(path):
        from so101_demo.runtime.parallel_ipc.frames import transport_address

        nonlocal checks
        if path == composition.broker_socket_path:
            checks += 1
            if checks == 1:
                listener.bind(transport_address(composition.broker_socket_path, directory_fd))
                composition.broker_socket_path.chmod(0o600)
                raise FileNotFoundError(path)
        return original_lstat(path)

    monkeypatch.setattr(Path, "lstat", racing_lstat)
    try:
        assert composition._wait_broker_ready() is True
    finally:
        listener.close()
        os.close(directory_fd)
        composition._release_partial()


def test_composition_always_runs_fail_closed_cleanup_when_worker_start_raises(tmp_path):
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
        processes = ()
        def __init__(self):
            self.cleanup_facts = None
        def shutdown(self, **actions):
            self.cleanup_facts = tuple(action() for action in actions.values())
            return all(self.cleanup_facts)

    scratch = _scratch_root()
    spec = prepare_batch(
        argv(scratch / "ce", worker_count="1",              point_id=("task_start",), run_mode="dry_run"),
        provenance_verifier=verified,
    )
    supervisor = Supervisor()
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "cec",
        supervisor=supervisor,
        worker_launcher=lambda *_args: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    with pytest.raises(RuntimeError, match="boom"):
        composition.run()
    assert supervisor.cleanup_facts == (True, True, True, True)
    cleanup_receipt = json.loads(
        (spec.request.evidence_root / "cleanup-gates.json").read_text(
            encoding="utf-8"
        )
    )
    assert cleanup_receipt == {
        "schema_version": 1,
        "batch_id": "batch-1",
        "actions": {
            "stop_leases": {
                "succeeded": True,
                "error_type": None,
                "error_message": None,
            },
            "cancel_goal": {
                "succeeded": True,
                "error_type": None,
                "error_message": None,
            },
            "confirm_goal_cancelled": {
                "succeeded": True,
                "error_type": None,
                "error_message": None,
            },
            "request_recovery": {
                "succeeded": True,
                "error_type": None,
                "error_message": None,
            },
        },
        "process_cleanup": {
            "succeeded": True,
            "error_type": None,
            "error_message": None,
        },
        "container_cleanup": {
            "succeeded": True,
            "error_type": None,
            "error_message": None,
        },
        "cleanup_gates_passed": True,
        "coordinator_completion": {
            "attempted": True,
            "succeeded": True,
            "error_type": None,
            "error_message": None,
        },
        "batch_cleanup_complete": True,
    }
    assert (spec.request.evidence_root / "cleanup-gates.json").stat().st_mode & 0o777 == 0o600


def test_broker_transport_does_not_interpret_committed_start_event(tmp_path):
    import threading

    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.cli.mujoco_batch.request import prepare_batch
    from so101_demo.cli.mujoco_batch.rpc_proxies import _CoordinatorRpcProxy, _WorkerBrokerProxy
    from so101_demo.parallel_batch.broker import BrokerResponse, BrokerSubmission
    from so101_demo.parallel_batch.contracts.common import ExecutionKind, ModelOutcome
    from so101_demo.parallel_batch.resource_allocation.models import ResourceSnapshot
    from so101_demo.runtime.parallel_ipc.broker_transport import BrokerTransport
    from so101_demo.runtime.parallel_worker_parts.receipts import InferenceSnapshotReceipt

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)

        def ros_domain_in_use(self, _domain):
            return False

        def socket_in_use(self, _path):
            return False

    class Supervisor:
        def start(self, *_args, **_kwargs):
            return None

    scratch = _scratch_root()
    root = scratch / "ba"
    spec = prepare_batch(
        argv(
            root,
            worker_count="1",
                        point_id=("task_start",),
            run_mode="plan_only",
        ),
        provenance_verifier=lambda value: {
            **verified(value),
            "image_id": "sha256:" + "b" * 64,
        },
    )
    composition = ProductionBatchComposition(
        spec,
        resource_probe=Probe(),
        claim_root=scratch / "bac",
        supervisor=Supervisor(),
        broker_command_builder=lambda _owner: ("broker",),
    )
    worker_document = json.loads(composition.worker_specs[0].read_text())
    resources = composition.resource_manifest.workers[0]
    coordinator = _CoordinatorRpcProxy(
        worker_document["socket_path"],
        worker_document["token_path"],
        worker_id=resources.worker_id,
        generation=resources.generation,
        mode=RunMode.PLAN_ONLY,
        coordinator_epoch=composition.journal.coordinator_epoch,
    )
    composition._start_servers()
    broker_server = None
    try:
        coordinator.register_worker("worker-01", generation=1)
        lease = coordinator.grant_lease(
            "worker-01", generation=1, request_key="lease-request-1"
        )
        assert composition.coordinator.snapshot().workers["worker-01"].workspace == (
            resources.worker_root
            / "validations" / lease.point_id / lease.attempt_id
        )
        coordinator.ack_lease(lease, request_key="lease-ack-1")
        start_key = "validation-start-attempt-1"
        coordinator.ack_validation_started(
            lease,
            request_key=start_key,
            gate_summary={
                "schema_version": 1,
                "kind": "POINT_INITIAL_GATE",
                "batch_id": lease.batch_id,
                "coordinator_epoch": lease.coordinator_epoch,
                "worker_id": lease.worker_id,
                "worker_generation": lease.worker_generation,
                "point_id": lease.point_id,
                "attempt_id": lease.attempt_id,
                "lease_generation": lease.lease_generation,
                "reset_epoch": "reset-1",
                "simulation_session_id": resources.session_id,
                "reset_completed_monotonic_s": 10.0,
                "source_frame_monotonic_s": 11.0,
                "canonical_joints": True,
                "no_controller_goal": True,
                "no_attachment": True,
                "no_contact": True,
                "no_stale_node": True,
            },
        )
        transport = BrokerTransport(
            ipc_root=root / "ipc/broker",
            config=spec.config,
            generation=1,
            deadline_s=1.0,
        )

        class Service:
            def __init__(self):
                self.request = None

            def submit(self, request, _snapshot):
                self.request = request
                return BrokerSubmission(True)

            def wait_response(self, request, timeout_s):
                assert request == self.request
                assert timeout_s == 1.0
                return BrokerResponse(
                    self.request,
                    1,
                    ModelOutcome.QUALIFIED,
                    {"source": "broker-process"},
                    None,
                    12.0,
                    13.0,
                    12.1,
                    13.1,
                    12.2,
                )

        broker_server = transport.server(
            Service(), endpoint=composition.broker_socket_path
        )
        thread = threading.Thread(target=broker_server.serve_once)
        thread.start()
        input_path = (
            resources.worker_root
            / "validations/task_start/attempt-1/working/perception/input/rgb.npy"
        )
        input_path.parent.mkdir(parents=True)
        input_path.write_bytes(b"npy")
        input_path.chmod(0o400)
        broker = _WorkerBrokerProxy(
            coordinator, composition.broker_socket_path, resources, spec.config,
            broker_generation=1,
        )
        broker.client.deadline_s = 1.0
        response = broker.request_model(
            lease,
            ExecutionKind.VALIDATION,
            snapshot=InferenceSnapshotReceipt(
                input_path,
                11.5,
                12_000_000_000,
                "task_camera_frame",
                (4, 5, 3),
                hashlib.sha256(b"npy").hexdigest(),
            ),
            start_event_id=start_key,
            start_event_type="VALIDATION_STARTED",
            reset_epoch="reset-1",
        )
        thread.join(timeout=2.0)
        assert response.candidate == {"source": "broker-process"}
        assert not hasattr(transport, "authorize")
    finally:
        if broker_server is not None:
            broker_server.close()
        composition._stop_servers()
        composition.journal.close()
        composition.allocator.close()
