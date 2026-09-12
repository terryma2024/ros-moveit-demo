from __future__ import annotations

import hashlib
import json
import os
from types import SimpleNamespace
from pathlib import Path

import pytest

from so101_demo.parallel_batch.contracts import (
    BatchSummary,
    PointStatus,
    RunMode,
    ValidationStatus,
)


PACKAGE = Path(__file__).resolve().parents[1]
POINTS = PACKAGE / "config/mujoco/moveit_expert_validation_points_v1.yaml"
CONFIG = PACKAGE / "config/mujoco/parallel_batch_v1.yaml"
YOLO_SHA = "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"
GROUNDED_SHA = "0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775"


def argv(root: Path, **changes):
    values = {
        "points": str(POINTS),
        "config": str(CONFIG),
        "batch_id": "batch-1",
        "worker_count": "2",
        "max_points_per_worker": "10",
        "evidence_root": str(root),
        "broker_image": "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1",
        "yolo_weights": "/models/yolo.pt",
        "yolo_weights_sha256": YOLO_SHA,
        "grounded_root": "/models/grounded",
        "grounded_manifest_sha256": GROUNDED_SHA,
        "run_mode": "dry_run",
    }
    values.update(changes)
    result = []
    for key, value in values.items():
        if key == "point_id":
            for item in value:
                result += ["--point-id", item]
        else:
            result += ["--" + key.replace("_", "-"), str(value)]
    return result


def verified(_spec):
    return {"source_commit": "a" * 40, "models_verified": True, "image_verified": True}


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"worker_count": "1", "max_points_per_worker": "19"}, "CAPACITY"),
        ({"evidence_root": "relative"}, "ABSOLUTE"),
        ({"run_mode": "unknown"}, "MODE"),
        ({"worker_count": "true"}, "INTEGER"),
        ({"point_id": ("missing",)}, "POINT"),
        ({"point_id": ("task_start", "task_start")}, "DUPLICATE"),
        ({"yolo_weights_sha256": "0" * 64}, "YOLO"),
        ({"grounded_manifest_sha256": "0" * 64}, "GROUNDED"),
    ],
)
def test_rejects_invalid_requests_before_composition(tmp_path, changes, error):
    from so101_demo.cli.mujoco_parallel_batch import CliError, prepare_batch

    with pytest.raises(CliError, match=error):
        prepare_batch(argv(tmp_path / "batch", **changes), provenance_verifier=verified)


def test_relative_catalog_and_config_paths_are_supported(tmp_path, monkeypatch):
    from so101_demo.cli.mujoco_parallel_batch import prepare_batch

    monkeypatch.chdir(PACKAGE)
    prepared = prepare_batch(
        argv(
            tmp_path / "batch",
            points="config/mujoco/moveit_expert_validation_points_v1.yaml",
            config="config/mujoco/parallel_batch_v1.yaml",
        ),
        provenance_verifier=verified,
    )
    assert len(prepared.request.selected_point_ids) == 20


def test_duplicate_batch_root_rejected_before_provenance_side_effect(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import CliError, prepare_batch

    root = tmp_path / "batch"
    root.mkdir()
    called = []
    with pytest.raises(CliError, match="DUPLICATE_BATCH"):
        prepare_batch(argv(root), provenance_verifier=lambda spec: called.append(spec))
    assert called == []


def test_selection_uses_catalog_order_and_hash_and_omission_selects_all(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import prepare_batch

    selected = prepare_batch(
        argv(
            tmp_path / "selected",
            worker_count="2",
            max_points_per_worker="1",
            point_id=("sample_16_far_right", "task_start"),
        ),
        provenance_verifier=verified,
    )
    assert selected.request.selected_point_ids == ("task_start", "sample_16_far_right")
    payload = json.dumps(
        ["task_start", "sample_16_far_right"], separators=(",", ":")
    ).encode()
    assert selected.selection_sha256 == hashlib.sha256(payload).hexdigest()
    complete = prepare_batch(argv(tmp_path / "complete"), provenance_verifier=verified)
    assert len(complete.request.selected_point_ids) == 20
    assert complete.request.selected_point_ids[0] == "task_start"
    assert complete.request.selected_point_ids[-1] == "sample_16_far_right"
    assert complete.manifest["worker_count"] == 2
    assert complete.manifest["max_points_per_worker"] == 10
    assert "fixed_partitions" not in complete.manifest


def test_stale_or_inconsistent_provenance_is_rejected(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import CliError, prepare_batch

    with pytest.raises(CliError, match="PROVENANCE"):
        prepare_batch(argv(tmp_path / "batch"), provenance_verifier=lambda _spec: False)


def summary(mode, statuses, *, cleanup=True, terminal=True):
    points = {point: PointStatus.UNRUN for point in statuses}
    validations = {}
    if mode is RunMode.EXECUTE:
        points = statuses
    else:
        validations = statuses
    return BatchSummary(
        mode,
        points,
        batch_terminal=terminal,
        validation_statuses=validations,
        batch_cleanup_complete=cleanup,
    )


@pytest.mark.parametrize("mode", [RunMode.DRY_RUN, RunMode.PLAN_ONLY])
def test_nonexecute_exit_and_aggregate_matrix(mode):
    from so101_demo.cli.mujoco_parallel_batch import outcome_document

    passed = summary(mode, {"task_start": ValidationStatus.VALIDATION_PASSED})
    code, document = outcome_document(passed)
    assert code == 0
    assert document["validation_passed"] is True
    assert document["qualification_applicable"] is False
    assert document["qualification_passed"] is False
    assert document["point_statuses"] == {"task_start": "UNRUN"}

    failed = summary(mode, {"task_start": ValidationStatus.VALIDATION_FAILED})
    assert outcome_document(failed)[0] == 1
    assert outcome_document(summary(mode, {"task_start": ValidationStatus.VALIDATION_PASSED}, cleanup=False))[0] == 1


def test_execute_exit_matrix_and_validation_does_not_qualify():
    from so101_demo.cli.mujoco_parallel_batch import outcome_document

    passed = summary(RunMode.EXECUTE, {"task_start": PointStatus.PASSED})
    code, document = outcome_document(passed)
    assert code == 0
    assert document["qualification_applicable"] is True
    assert document["qualification_passed"] is True
    assert outcome_document(summary(RunMode.EXECUTE, {"task_start": PointStatus.FAILED}))[0] == 1
    assert outcome_document(summary(RunMode.EXECUTE, {"task_start": PointStatus.PASSED}, cleanup=False))[0] == 1


def test_cli_dependency_injection_runs_composition_and_writes_real_outcome(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import run_cli

    seen = []

    class Composition:
        def run(self):
            return summary(
                RunMode.DRY_RUN,
                {point: ValidationStatus.VALIDATION_PASSED for point in self.spec.request.selected_point_ids},
            )

        def __init__(self, spec):
            self.spec = spec
            seen.append(spec)

    root = tmp_path / "batch"
    code = run_cli(
        argv(root),
        provenance_verifier=verified,
        composition_factory=Composition,
    )
    assert code == 0
    assert len(seen) == 1
    aggregate = json.loads((root / "aggregate_results.json").read_text())
    assert aggregate["qualification_applicable"] is False
    assert aggregate["qualification_passed"] is False
    assert set(aggregate["point_statuses"].values()) == {"UNRUN"}


def test_cli_never_unlinks_or_replaces_an_existing_aggregate(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import run_cli

    class Composition:
        def __init__(self, spec):
            self.spec = spec

        def run(self):
            aggregate = self.spec.request.evidence_root / "aggregate_results.json"
            aggregate.write_text("coordinator-owned", encoding="utf-8")
            return summary(
                RunMode.DRY_RUN,
                {"task_start": ValidationStatus.VALIDATION_PASSED},
            )

    root = tmp_path / "owned-aggregate"
    assert run_cli(
        argv(
            root,
            worker_count="1",
            max_points_per_worker="1",
            point_id=("task_start",),
        ),
        provenance_verifier=verified,
        composition_factory=Composition,
    ) == 1
    assert (root / "aggregate_results.json").read_text() == "coordinator-owned"


def test_default_production_composition_derives_real_dry_run_snapshot():
    from so101_demo.cli.mujoco_parallel_batch import (
        ProductionBatchComposition,
        prepare_batch,
    )
    from so101_demo.parallel_batch.coordinator import BatchCoordinator
    from so101_demo.parallel_batch.resources import ResourceSnapshot, WorkerResourceAllocator
    from so101_demo.parallel_batch.worker import ParallelWorker
    from so101_demo.runtime.parallel_worker_runtime import DryRunWorkerRuntime

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    scratch = Path(os.environ["TMPDIR"]).parent
    root = scratch / "pc"
    spec = prepare_batch(
        argv(
            root,
            worker_count="1",
            max_points_per_worker="1",
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
    from so101_demo.cli.mujoco_parallel_batch import (
        ProductionBatchComposition,
        prepare_batch,
    )
    from so101_demo.parallel_batch.resources import ResourceSnapshot

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

    scratch = Path(os.environ["TMPDIR"]).parent
    root = scratch / "eb"
    supervisor = Supervisor()
    spec = prepare_batch(
        argv(
            root,
            worker_count="1",
            max_points_per_worker="1",
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
    assert broker_spec["authority_endpoint"] == "/runtime/broker-authority.sock"
    assert broker_spec["config_path"] == "/runtime/runtime-config.yaml"
    assert broker_spec["authority_token_path"] == "/runtime/broker-g1.token"
    worker_spec = json.loads(composition.worker_specs[0].read_text())
    assert worker_spec["broker_socket_path"] == str(root / "ipc/perception.sock")
    assert worker_spec["broker_generation"] == 1
    composition._start_broker()
    assert supervisor.started == [
        ("broker", ("docker", "run", str(composition.broker_spec_path)))
    ]
    composition.journal.close()
    composition.allocator.close()


def test_physical_worker_launches_receive_exact_isolated_environments(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition, prepare_batch
    from so101_demo.parallel_batch.resources import ResourceSnapshot

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

    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(
            scratch / "e", worker_count="2", max_points_per_worker="1",
            point_id=("task_start", "sample_01_near_left"), run_mode="plan_only",
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
    composition.journal.close()
    composition.allocator.close()


def test_broker_start_rejects_missing_image_id_and_mutable_tag_drift(tmp_path, monkeypatch):
    from so101_demo.cli.mujoco_parallel_batch import (
        CliError, ProductionBatchComposition, prepare_batch,
    )
    from so101_demo.parallel_batch.resources import ResourceSnapshot
    import so101_demo.cli.parallel_perception_broker as broker_cli

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    scratch = Path(os.environ["TMPDIR"]).parent
    base = prepare_batch(
        argv(scratch / "im", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=verified,
    )
    missing = ProductionBatchComposition(
        base, resource_probe=Probe(), claim_root=scratch / "imc"
    )
    with pytest.raises(CliError, match="IMAGE_ID_REQUIRED"):
        missing._start_broker()
    missing.journal.close()
    missing.allocator.close()

    bound = prepare_batch(
        argv(scratch / "id", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
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
    drift.journal.close()
    drift.allocator.close()


def test_workers_cannot_start_until_broker_socket_and_ready_receipt_exist(tmp_path):
    import socket

    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition, prepare_batch
    from so101_demo.parallel_batch.resources import ResourceSnapshot

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

    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(scratch / "br", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    supervisor = Supervisor()
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "brc",
        supervisor=supervisor, broker_command_builder=lambda _owner: ("broker",),
    )
    directory_fd = os.open(composition.authority.ipc_root, os.O_RDONLY | os.O_DIRECTORY)
    listener = socket.socket(socket.AF_UNIX)
    try:
        listener.bind(f"/proc/self/fd/{directory_fd}/{composition.broker_socket_path.name}")
        (composition.authority.ipc_root / "ready.json").write_text("{}")
        assert composition._wait_broker_ready() is True
        assert supervisor.health_checks >= 1
    finally:
        listener.close()
        os.close(directory_fd)
        composition.journal.close()
        composition.allocator.close()


def test_composition_always_runs_fail_closed_cleanup_when_worker_start_raises(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition, prepare_batch
    from so101_demo.parallel_batch.resources import ResourceSnapshot

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

    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(scratch / "ce", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="dry_run"),
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
    assert supervisor.cleanup_facts == (False, True, True, True)


def test_broker_authority_verifies_the_exact_committed_start_event(tmp_path):
    import threading

    from so101_demo.cli.mujoco_parallel_batch import (
        ProductionBatchComposition,
        _CoordinatorRpcProxy,
        _WorkerBrokerProxy,
        prepare_batch,
    )
    from so101_demo.parallel_batch.broker import BrokerResponse, BrokerSubmission
    from so101_demo.parallel_batch.contracts import ExecutionKind, ModelOutcome
    from so101_demo.parallel_batch.resources import ResourceSnapshot
    from so101_demo.runtime.parallel_ipc import (
        BrokerTransport,
        _BrokerCoordinatorClient,
    )
    from so101_demo.runtime.parallel_worker_runtime import InferenceSnapshotReceipt
    from so101_demo.runtime.parallel_perception_runtime import Snapshot

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

    scratch = Path(os.environ["TMPDIR"]).parent
    root = scratch / "ba"
    spec = prepare_batch(
        argv(
            root,
            worker_count="1",
            max_points_per_worker="1",
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
        authority_call = _BrokerCoordinatorClient(
            composition.broker_authority_server.path,
            root / "ipc/broker-g1.token",
            coordinator_epoch=composition.journal.coordinator_epoch,
            generation=1,
            deadline_s=1.0,
            max_frame_bytes=spec.config.broker_max_frame_bytes,
        )
        transport = BrokerTransport(
            ipc_root=root / "ipc",
            config=spec.config,
            generation=1,
            authority_call=authority_call,
            deadline_s=1.0,
        )

        class Service:
            def __init__(self):
                self.request = None

            def submit(self, request, _snapshot):
                self.request = request
                return BrokerSubmission(True)

            def run_next(self):
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

            def poll_response(self, _request):
                return None

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
        request = response.request
        snapshot = Snapshot(
            (4, 5, 3),
            12_000_000_000,
            "task_camera_frame",
            "wrong-start-key",
            "VALIDATION_STARTED",
            response.identity,
        )
        assert transport.authorize(request, snapshot) is False
    finally:
        if broker_server is not None:
            broker_server.close()
        composition._stop_servers()
        composition.journal.close()
        composition.allocator.close()


@pytest.mark.parametrize("mode", ("plan_only", "execute"))
def test_default_composition_constructs_physical_runtime_ports_lazily(mode):
    from so101_demo.cli.mujoco_parallel_batch import (
        ProductionBatchComposition,
        prepare_batch,
    )
    from so101_demo.parallel_batch.resources import ResourceSnapshot
    from so101_demo.runtime.parallel_worker_runtime import ParallelWorkerRuntime

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    scratch = Path(os.environ["TMPDIR"]).parent
    root = scratch / ("pp" if mode == "plan_only" else "pe")
    side_effects = {
        name: (lambda *_args, **_kwargs: True)
        for name in (
            "ready_probe", "reset_point", "initial_gate", "localize",
            "admit_pose", "publish_pose", "plan_prefix", "execute_result",
            "consumer_ready", "capture_rgb", "capture_numeric_evidence",
            "cancel_motion", "confirm_no_controller_goal", "recovery",
        )
    }
    spec = prepare_batch(
        argv(root, worker_count="1", max_points_per_worker="1", point_id=("task_start",), run_mode=mode),
        provenance_verifier=verified,
    )
    composition = ProductionBatchComposition(
        spec,
        resource_probe=Probe(),
        claim_root=scratch / ("clp" if mode == "plan_only" else "cle"),
        runtime_side_effects_factory=lambda _resources: side_effects,
    )
    from so101_demo.cli.mujoco_parallel_batch import _build_worker_from_spec
    _worker, runtime = _build_worker_from_spec(
        composition.worker_specs[0], runtime_side_effects=side_effects
    )
    assert isinstance(runtime, ParallelWorkerRuntime)
    composition._start_servers()
    try:
        document = json.loads(composition.worker_specs[0].read_text())
        from so101_demo.cli.mujoco_parallel_batch import _CoordinatorRpcProxy
        proxy = _CoordinatorRpcProxy(
            document["socket_path"], document["token_path"],
            worker_id="worker-01", generation=1,
            mode=RunMode(mode),
            coordinator_epoch=document["coordinator_epoch"],
        )
        replacement = proxy.replace_resources("worker-01", expected_generation=1)
        assert replacement.generation == 2
        assert replacement.session_id != composition.resource_manifest.workers[0].session_id
        assert replacement.worker_root == composition.resource_manifest.workers[0].worker_root
    finally:
        composition._stop_servers()
    SimpleLease.coordinator_epoch = composition.journal.coordinator_epoch
    argv_value = runtime.consumer_argv("reset-1", SimpleLease())
    if mode == "plan_only":
        assert argv_value is None
    else:
        assert "--execute" in argv_value
        assert "--expected-reset-epoch" in argv_value
    composition.journal.close()
    composition.allocator.close()


class SimpleLease:
    batch_id = "batch-1"
    coordinator_epoch = 1
    worker_id = "worker-01"
    worker_generation = 1
    point_id = "task_start"
    attempt_id = "attempt-1"
    lease_generation = 1


def test_artifact_workspace_is_reserved_before_runtime_files_and_reused_for_seal(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import _ArtifactResults
    from so101_demo.runtime.parallel_ros_runtime import ResetBoundaryReceipt

    lease = SimpleLease()
    root = tmp_path / "worker-01"
    results = _ArtifactResults({"worker-01": root}, RunMode.PLAN_ONLY)
    receipt = ResetBoundaryReceipt("reset-7", "session-worker-01", 12.5, 31.25)
    assert results.reserve_workspace(lease, receipt) is True
    working = root / "validations/task_start/attempt-1/working"
    identity = json.loads((working / "workspace_identity.json").read_text())
    assert identity["reset_epoch"] == "reset-7"
    assert identity["source_stamp"] == {
        "reset_completed_monotonic_s": 12.5,
        "simulation_session_id": "session-worker-01",
        "simulation_time_s": 31.25,
    }
    (working / "initial-rgb.png").write_bytes(b"png")
    (working / "perception").mkdir()
    (working / "perception/rgb.npy").write_bytes(b"npy")
    decision = SimpleNamespace(
        status=ValidationStatus.VALIDATION_PASSED,
        reason="OK",
        physical_action_proven_absent=True,
    )
    sealed = Path(results.seal_validation(lease, decision))
    assert sealed == working.parent / "sealed"
    assert (sealed / "initial-rgb.png").read_bytes() == b"png"
    assert (sealed / "perception/rgb.npy").read_bytes() == b"npy"


def test_worker_broker_proxy_rejects_unexpected_generation_before_return(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import CliError, _WorkerBrokerProxy
    from so101_demo.parallel_batch.contracts import (
        ExecutionKind,
        load_parallel_runtime_config,
    )
    from so101_demo.runtime.parallel_worker_runtime import InferenceSnapshotReceipt

    worker_root = tmp_path / "worker-01"
    path = worker_root / "validations/task_start/attempt-1/working/perception/input/rgb.npy"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"npy")
    proxy = _WorkerBrokerProxy(
        SimpleNamespace(
            coordinator_epoch=1, worker_id="worker-01", generation=1,
            token="a" * 64,
        ),
        tmp_path / "perception.sock",
        SimpleNamespace(worker_root=worker_root),
        load_parallel_runtime_config(CONFIG),
        broker_generation=1,
    )
    proxy._call = lambda _message: {
        "broker_generation": 2,
        "outcome": "NORMAL_REJECTION",
        "candidate": None,
        "reason": "none",
        "queued_monotonic_s": 1.0,
        "queue_deadline_monotonic_s": 2.0,
        "started_monotonic_s": 1.1,
        "inference_deadline_monotonic_s": 2.1,
        "completed_monotonic_s": 1.2,
    }
    with pytest.raises(CliError, match="BROKER_GENERATION_CHANGED"):
        proxy.request_model(
            SimpleLease(), ExecutionKind.VALIDATION,
            snapshot=InferenceSnapshotReceipt(
                path, 11.0, 12_000_000_000, "task_camera_frame", (2, 3, 3),
                hashlib.sha256(b"npy").hexdigest(),
            ),
            start_event_id="validation-start-attempt-1",
            start_event_type="VALIDATION_STARTED",
            reset_epoch="reset-1",
        )
