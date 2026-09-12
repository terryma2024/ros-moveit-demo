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
    WorkerState,
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


def test_worker_result_evidence_is_private_structured_and_no_replace(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import _write_worker_results
    from so101_demo.parallel_batch.worker import WorkerRunResult

    resources = SimpleNamespace(
        worker_id="worker-01", generation=1, worker_root=tmp_path
    )
    result = WorkerRunResult(
        "task_start",
        None,
        False,
        "INITIAL_GATE_FAILED",
        failure_boundary="point_initial_gate",
        failure_type="RuntimeError",
        failure_message="POINT_INITIAL_GATE_OBSERVATION_REJECTED",
    )

    path = _write_worker_results(resources, (result,))

    assert path == tmp_path / "worker-run-results.json"
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "schema_version": 1,
        "worker_id": "worker-01",
        "worker_generation": 1,
        "results": [{
            "point_id": "task_start",
            "terminal_status": None,
            "recovered": False,
            "stopped_reason": "INITIAL_GATE_FAILED",
            "failure_boundary": "point_initial_gate",
            "failure_type": "RuntimeError",
            "failure_message": "POINT_INITIAL_GATE_OBSERVATION_REJECTED",
        }],
    }
    with pytest.raises(FileExistsError):
        _write_worker_results(resources, (result,))


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
        terminal_reason="POINTS_COMPLETE" if terminal else None,
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


@pytest.mark.parametrize("mode", [RunMode.DRY_RUN, RunMode.PLAN_ONLY])
def test_nonexecute_dependency_failure_keeps_validation_history_but_exits_nonzero(mode):
    from so101_demo.cli.mujoco_parallel_batch import outcome_document

    failed = BatchSummary(
        mode,
        {"task_start": PointStatus.UNRUN},
        batch_terminal=True,
        validation_statuses={
            "task_start": ValidationStatus.VALIDATION_PASSED,
        },
        batch_cleanup_complete=True,
        terminal_reason="SHARED_DEPENDENCY_UNAVAILABLE",
    )

    code, document = outcome_document(failed)

    assert code == 1
    assert document["validation_statuses"] == {
        "task_start": "VALIDATION_PASSED",
    }
    assert document["validation_passed"] is False


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
    assert worker_spec["broker_socket_path"] == str(root / "ipc/broker/perception.sock")
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
    import threading

    from so101_demo.cli.mujoco_parallel_batch import (
        ProductionBatchComposition, _write_json, prepare_batch,
    )
    from so101_demo.parallel_batch.resources import ResourceSnapshot
    from so101_demo.runtime.parallel_ipc import BrokerTransport, _BrokerCoordinatorClient

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
        composition._start_servers()
        authority_call = _BrokerCoordinatorClient(
            composition.broker_authority_server.path,
            composition.broker_token_path,
            coordinator_epoch=composition.journal.coordinator_epoch,
            generation=1,
            deadline_s=1.0,
            max_frame_bytes=spec.config.broker_max_frame_bytes,
        )
        transport = BrokerTransport(
            ipc_root=composition.broker_runtime_root,
            config=spec.config,
            generation=1,
            authority_call=authority_call,
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
    from so101_demo.cli.mujoco_parallel_batch import (
        CliError, ProductionBatchComposition, _write_json, prepare_batch,
    )
    from so101_demo.parallel_batch.resources import ResourceSnapshot

    class Probe:
        def snapshot(self): return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain): return False
        def socket_in_use(self, _path): return False

    class Supervisor:
        processes = ()
        def assert_healthy(self): return None

    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(scratch / "ns", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
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
    from so101_demo.cli.mujoco_parallel_batch import (
        CliError, ProductionBatchComposition, prepare_batch,
    )
    from so101_demo.parallel_batch.resources import ResourceSnapshot

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

    scratch = Path(os.environ["TMPDIR"]).parent
    clock = Clock()
    spec = prepare_batch(
        argv(scratch / "s", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
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
    from so101_demo.cli.mujoco_parallel_batch import (
        ProductionBatchComposition, prepare_batch,
    )
    from so101_demo.parallel_batch.resources import ResourceSnapshot

    class Probe:
        def snapshot(self): return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain): return False
        def socket_in_use(self, _path): return False

    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(scratch / "c", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
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
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition

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


def test_broker_cleanup_waits_for_exact_auto_remove_after_successful_stop(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import (
        CliError,
        ProductionBatchComposition,
    )

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
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition

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
    from so101_demo.cli.mujoco_parallel_batch import (
        ProductionBatchComposition, _write_json, prepare_batch,
    )
    from so101_demo.parallel_batch.resources import ResourceSnapshot

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

    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(scratch / "race", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {
            **verified(value), "image_id": "sha256:" + "b" * 64,
        },
    )
    composition = ProductionBatchComposition(
        spec, resource_probe=Probe(), claim_root=scratch / "race-claims",
        supervisor=Supervisor(), broker_command_builder=lambda _owner: ("broker",),
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
        nonlocal checks
        if path == composition.broker_socket_path:
            checks += 1
            if checks == 1:
                listener.bind(
                    f"/proc/self/fd/{directory_fd}/{composition.broker_socket_path.name}"
                )
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
                root / "ipc/broker/broker-g1.token",
            coordinator_epoch=composition.journal.coordinator_epoch,
            generation=1,
            deadline_s=1.0,
            max_frame_bytes=spec.config.broker_max_frame_bytes,
        )
        transport = BrokerTransport(
            ipc_root=root / "ipc/broker",
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
        valid_snapshot = Snapshot(
            (4, 5, 3), 12_000_000_000, "task_camera_frame",
            start_key, "VALIDATION_STARTED", response.identity,
        )
        assert transport.authorize(request, valid_snapshot) is True
        composition.coordinator.request_stop(reason="RACE_STOP")
        assert transport.authorize(request, valid_snapshot) is False
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
            current_broker=lambda: {
                "healthy": True,
                "broker_generation": 2,
                "broker_socket_path": str(tmp_path / "perception-g2.sock"),
                "recovery_deadline_monotonic_s": None,
            },
        ),
        tmp_path / "perception.sock",
        SimpleNamespace(worker_root=worker_root),
        load_parallel_runtime_config(CONFIG),
        broker_generation=1,
    )
    proxy._call = lambda _message: {
        "broker_generation": 1,
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


def test_frozen_worker_topology_defaults_to_two_by_ten(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import prepare_batch

    values = argv(tmp_path / "defaults")
    for flag in ("--worker-count", "--max-points-per-worker"):
        index = values.index(flag)
        del values[index:index + 2]
    prepared = prepare_batch(values, provenance_verifier=verified)
    assert prepared.request.worker_count == 2
    assert prepared.request.max_points_per_worker == 10
    assert prepared.manifest["worker_count"] == 2
    assert prepared.manifest["max_points_per_worker"] == 10


def test_worker_process_environment_is_the_exact_task8_whitelist(tmp_path):
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
            self.environments = []
        def start(self, _role, _command, *, environment=None):
            self.environments.append(dict(environment))

    monkey = "SO101_TEST_SECRET_MUST_NOT_LEAK"
    os.environ[monkey] = "secret"
    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(scratch / "x", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
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
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition, prepare_batch
    from so101_demo.parallel_batch.resources import ResourceSnapshot
    from so101_demo.cli.parallel_perception_broker import container_run_argv

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(scratch / "b", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
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
    from so101_demo.cli.mujoco_parallel_batch import CliError, _validate_rpc_payload

    valid = {"operation": operation, **payload}
    assert _validate_rpc_payload(valid) == valid
    with pytest.raises(CliError, match="RPC_PAYLOAD_SCHEMA"):
        _validate_rpc_payload({**valid, "extra": True})
    removable = next(name for name in valid if name != "operation") if len(valid) > 1 else "operation"
    with pytest.raises(CliError, match="RPC_PAYLOAD_SCHEMA"):
        _validate_rpc_payload({name: value for name, value in valid.items() if name != removable})


def test_constructor_failure_releases_partial_allocator_journal_and_endpoints(tmp_path, monkeypatch):
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition, prepare_batch
    from so101_demo.parallel_batch.resources import ResourceSnapshot
    import so101_demo.cli.mujoco_parallel_batch as batch_cli

    class Probe:
        def snapshot(self):
            return ResourceSnapshot(32, 64.0, 16.0)
        def ros_domain_in_use(self, _domain):
            return False
        def socket_in_use(self, _path):
            return False

    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(scratch / "f", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
        provenance_verifier=lambda value: {**verified(value), "image_id": "sha256:" + "b" * 64},
    )
    real = batch_cli.AuthenticatedUnixServer
    calls = []

    def fail_second(*args, **kwargs):
        if len(calls) == 1:
            raise RuntimeError("constructor fault")
        calls.append(real(*args, **kwargs))
        return calls[-1]

    monkeypatch.setattr(batch_cli, "AuthenticatedUnixServer", fail_second)
    with pytest.raises(RuntimeError, match="constructor fault"):
        ProductionBatchComposition(
            spec, resource_probe=Probe(), claim_root=scratch / "fc"
        )
    assert all(server.path.exists() is False for server in calls)
    assert not (scratch / "fc" / spec.request.batch_id).exists()


def test_composition_cleanup_invokes_real_worker_control_actions_in_order():
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition

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
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition

    class Control:
        def call(self, _operation):
            raise AssertionError("a reaped Worker has no live control socket")

    owner = object.__new__(ProductionBatchComposition)
    owner.worker_controls = [Control(), Control()]
    owner._worker_children_reaped = True

    assert owner._worker_control("cancel_motion") is True


def test_broker_ready_receipt_is_exactly_bound_to_batch_generation_and_image():
    from so101_demo.cli.mujoco_parallel_batch import CliError, _validate_broker_ready

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
    from so101_demo.cli.mujoco_parallel_batch import CliError, ProductionBatchComposition, prepare_batch
    from so101_demo.parallel_batch.resources import ResourceSnapshot

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
    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(scratch / "v", worker_count="1", max_points_per_worker="1",
             point_id=("task_start",), run_mode="plan_only"),
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
    from so101_demo.cli.mujoco_parallel_batch import _WorkerControlProxy

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
    from so101_demo.cli.mujoco_parallel_batch import _WorkerControlProxy
    from so101_demo.runtime.parallel_ipc import AuthenticatedUnixServer, WorkerTokenAuthority

    authority = WorkerTokenAuthority(tmp_path, coordinator_epoch=3)
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


def test_provenance_rejects_mixed_source_install_overlay_before_snapshot(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import (
        CliError,
        _validate_provenance_overlay,
    )

    repository = tmp_path / "checkout"
    module = repository / "src/so101_demo_py/src/cli/mujoco_parallel_batch.py"
    console = repository / "install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    config = repository / "src/so101_demo_py/config/mujoco/parallel_batch_v1.yaml"
    points = repository / "src/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml"
    for path in (module, console, config, points):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("approved", encoding="utf-8")
    _validate_provenance_overlay(repository, module, console, config, points)

    foreign = tmp_path / "other/install/so101_parallel_batch"
    foreign.parent.mkdir(parents=True)
    foreign.write_text("mixed", encoding="utf-8")
    with pytest.raises(CliError, match="MIXED_OVERLAY"):
        _validate_provenance_overlay(repository, module, foreign, config, points)


def test_installed_provenance_binds_exact_editable_tree_and_rejects_stale_target(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import (
        CliError, _installed_overlay_identity,
    )
    from so101_demo.cli.parallel_perception_broker import source_hash

    repository = tmp_path / "checkout"
    source = repository / "src/so101_demo_py/src"
    module = source / "cli/mujoco_parallel_batch.py"
    module.parent.mkdir(parents=True)
    module.write_text("approved = True\n", encoding="utf-8")
    build = repository / "build/so101_demo_py"
    build.mkdir(parents=True)
    (build / "so101_demo").symlink_to(source, target_is_directory=True)
    console = repository / "install/so101_demo_py/lib/so101_demo_py/so101_parallel_batch"
    console.parent.mkdir(parents=True)
    console.write_text("#!/bin/sh\n", encoding="utf-8")
    egg = repository / "install/so101_demo_py/lib/python3.12/site-packages/so101-demo-py.egg-link"
    egg.parent.mkdir(parents=True)
    egg.write_text(str(build) + "\n.\n", encoding="utf-8")
    import_path = build / "so101_demo/cli/mujoco_parallel_batch.py"

    metadata = build / "so101_demo_py.egg-info/entry_points.txt"
    metadata.parent.mkdir(parents=True)
    metadata.write_text(
        "[console_scripts]\n"
        "so101_parallel_batch = so101_demo.cli.mujoco_parallel_batch:main\n",
        encoding="utf-8",
    )

    with pytest.raises(CliError, match="CONSOLE"):
        _installed_overlay_identity(
            repository, import_path, console, source_hash=source_hash
        )

    console.write_text(_canonical_console_wrapper(), encoding="utf-8")
    identity = _installed_overlay_identity(
        repository, import_path, console, source_hash=source_hash
    )
    assert identity["installed_module_tree_sha256"] == source_hash(source)

    stale = repository / "stale/so101_demo"
    stale.mkdir(parents=True)
    (stale / "old.py").write_text("old = True\n", encoding="utf-8")
    (build / "so101_demo").unlink()
    (build / "so101_demo").symlink_to(stale, target_is_directory=True)
    with pytest.raises(CliError, match="INSTALLED_OVERLAY|INSTALLED_BYTES"):
        _installed_overlay_identity(
            repository, import_path, console, source_hash=source_hash
        )


def _canonical_console_wrapper():
    return """#!/usr/bin/python3
# EASY-INSTALL-ENTRY-SCRIPT: 'so101-demo-py','console_scripts','so101_parallel_batch'
import re
import sys

# for compatibility with easy_install; see #2198
__requires__ = 'so101-demo-py'

try:
    from importlib.metadata import distribution
except ImportError:
    try:
        from importlib_metadata import distribution
    except ImportError:
        from pkg_resources import load_entry_point


def importlib_load_entry_point(spec, group, name):
    dist_name, _, _ = spec.partition('==')
    matches = (
        entry_point
        for entry_point in distribution(dist_name).entry_points
        if entry_point.group == group and entry_point.name == name
    )
    return next(matches).load()


globals().setdefault('load_entry_point', importlib_load_entry_point)


if __name__ == '__main__':
    sys.argv[0] = re.sub(r'(-script\\.pyw?|\\.exe)?$', '', sys.argv[0])
    sys.exit(load_entry_point('so101-demo-py', 'console_scripts', 'so101_parallel_batch')())
"""


def test_broker_exit_restarts_fresh_generation_while_leases_remain_paused(tmp_path):
    from so101_demo.cli.mujoco_parallel_batch import (
        ProductionBatchComposition,
        prepare_batch,
    )
    from so101_demo.parallel_batch.resources import ResourceSnapshot
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

    scratch = Path(os.environ["TMPDIR"]).parent
    root = scratch / "f22br"
    spec = prepare_batch(
        argv(
            root,
            worker_count="1",
            max_points_per_worker="1",
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
    )
    composition.coordinator.register_worker("worker-01", generation=1)
    old_process = composition._start_broker()
    old_root = composition.broker_runtime_root
    old_spec = composition.broker_spec_path
    old_token = composition.broker_token_path
    old_token_bytes = old_token.read_bytes()
    ready_checks = []
    composition._wait_broker_ready = lambda **values: ready_checks.append(values) or True
    try:
        assert composition._recover_broker(old_process, 17) is True
        assert supervisor.retired == [old_process]
        assert composition.broker_generation == 2
        assert composition.broker_runtime_root != old_root
        assert composition.broker_spec_path != old_spec
        assert composition.broker_token_path != old_token
        assert composition.broker_token_path.read_bytes() != old_token_bytes
        assert json.loads(composition.broker_spec_path.read_text())[
            "broker_generation"
        ] == 2
        assert ready_checks == [{"deadline_monotonic_s": supervisor.pause_deadline}]
        assert composition.coordinator.snapshot().broker_healthy is True
    finally:
        composition._release_partial()


def test_authenticated_worker_discovers_only_the_current_healthy_broker(tmp_path):
    import threading

    from so101_demo.cli.mujoco_parallel_batch import (
        CliError,
        ProductionBatchComposition,
        _CoordinatorRpcProxy,
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

    scratch = Path(os.environ["TMPDIR"]).parent
    root = scratch / "f22bd"
    spec = prepare_batch(
        argv(
            root,
            worker_count="1",
            max_points_per_worker="1",
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
        proxy.register_worker("worker-01", generation=1)
        from so101_demo.parallel_batch.worker import LeaseGrantPaused

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
        from so101_demo.runtime.parallel_ipc import IpcError

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
    from so101_demo.cli.mujoco_parallel_batch import (
        ProductionBatchComposition,
        prepare_batch,
    )
    from so101_demo.parallel_batch.resources import ResourceSnapshot
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
    scratch = Path(os.environ["TMPDIR"]).parent
    spec = prepare_batch(
        argv(
            scratch / "f22dl",
            worker_count="1",
            max_points_per_worker="1",
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
    from so101_demo.cli.mujoco_parallel_batch import ProductionBatchComposition

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
    from test_parallel_batch_worker import Fake
    from so101_demo.cli.mujoco_parallel_batch import CliError
    from so101_demo.parallel_batch.contracts import AttemptStatus, RunMode
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
    from test_parallel_batch_worker import Fake
    from so101_demo.parallel_batch.contracts import AttemptStatus, RunMode
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
    from test_parallel_batch_worker import Fake
    from so101_demo.parallel_batch.contracts import AttemptStatus, RunMode
    from so101_demo.parallel_batch.worker import LeaseGrantPaused, ParallelWorker

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
    from so101_demo.cli.mujoco_parallel_batch import _WorkerBrokerProxy
    from so101_demo.parallel_batch.contracts import (
        ExecutionKind,
        load_parallel_runtime_config,
    )
    from so101_demo.runtime.parallel_worker_runtime import InferenceSnapshotReceipt

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

    class Client:
        def __init__(self, path, **_kwargs):
            self.path = Path(path)
            clients.append(self.path)

        def call(self, message):
            operation = message["payload"]["operation"]
            if operation == "cancel_generation":
                return {"payload": {"cancelled": True}}
            return {"payload": {
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
    proxy = _WorkerBrokerProxy(
        Coordinator(),
        tmp_path / "broker-g1.sock",
        SimpleNamespace(worker_root=worker_root),
        load_parallel_runtime_config(CONFIG),
        broker_generation=1,
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
    assert discoveries == ["current", "current", "current"]
    assert clients == [
        tmp_path / "broker-g1.sock",
        endpoint,
        endpoint,
        endpoint,
    ]
