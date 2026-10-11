"""Requests, resume, selection, retry, fixed web stop and outcome of the parallel batch command."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

from parallel_batch_cli_support import (
    PACKAGE,
    POINTS,
    _cancel_fixed_cli,
    _fixed_web_spec,
    _FixedWebProbe,
    _scratch_root,
    argv,
    local_start_guard,  # noqa: F401  (pytest fixtures)
    summary,
    verified,
)
import pytest

from so101_demo.parallel_batch.contracts.common import (
    PointStatus,
    RunMode,
    ValidationStatus,
)
from so101_demo.parallel_batch.contracts.identity import BatchSummary


def test_linux_cuda_retry_cli_records_the_admitted_original_chain(tmp_path):
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    catalog_sha256 = hashlib.sha256(POINTS.read_bytes()).hexdigest()
    values = argv(
        tmp_path / "linux-retry", worker_count="1", point_id=("task_start",),
        batch_kind="FULL_RESTART_RETRY",
        original_selection_sha256="a" * 64,
        original_result_sha256="b" * 64,
        original_catalog_sha256=catalog_sha256,
        original_batch_id="first-pass-1",
    )
    prepared = prepare_batch(values, provenance_verifier=verified)

    assert prepared.request.batch_kind.value == "FULL_RESTART_RETRY"
    assert prepared.manifest["retry_binding"] == {
        "original_selection_sha256": "a" * 64,
        "original_result_sha256": "b" * 64,
        "original_catalog_sha256": catalog_sha256,
        "original_batch_id": "first-pass-1",
    }


def test_linux_cuda_retry_cli_refuses_an_unnamed_original_chain(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    with pytest.raises(CliError, match="RETRY_ROOT_REQUIRED"):
        prepare_batch(
            argv(
                tmp_path / "linux-retry-missing", worker_count="1",
                point_id=("task_start",), batch_kind="FULL_RESTART_RETRY",
            ),
            provenance_verifier=verified,
        )


def test_linux_cuda_retry_cli_refuses_a_foreign_catalog_digest(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    with pytest.raises(CliError, match="RETRY_CATALOG_MISMATCH"):
        prepare_batch(
            argv(
                tmp_path / "linux-retry-catalog", worker_count="1",
                point_id=("task_start",), batch_kind="FULL_RESTART_RETRY",
                original_selection_sha256="a" * 64,
                original_result_sha256="b" * 64,
                original_catalog_sha256="c" * 64,
                original_batch_id="first-pass-1",
            ),
            provenance_verifier=verified,
        )


@pytest.mark.parametrize("corrupt_cleanup", [False, True])
def test_fixed_cli_authenticated_stop_uses_existing_cleanup_not_worker_launch(
    tmp_path, monkeypatch, corrupt_cleanup,
):
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    spec, values = _fixed_web_spec(tmp_path, monkeypatch)

    def forbidden_worker_launch(_owner, _path):
        raise AssertionError("cancelled Worker must not be launched")

    composition = ProductionBatchComposition(
        spec, resource_probe=_FixedWebProbe(), claim_root=tmp_path / "claims",
        worker_launcher=forbidden_worker_launch,
    )
    run_entered = False
    try:
        path = Path(values["SO101_FIXED_CONTROL_SOCKET"])
        assert path.is_socket()
        assert all(key not in os.environ for key in values)
        assert values["SO101_FIXED_CONTROL_TOKEN"] not in composition.worker_specs[0].read_text()
        if corrupt_cleanup:
            orphan = composition.resource_manifest.workers[0].worker_root / "owned-runtime-processes.json"
            orphan.write_text(json.dumps({"schema_version": 1, "processes": [{"invalid": "identity"}]}))
            orphan.chmod(0o600)
        wait = composition._wait_broker_ready

        def observe_cancel_before_workers():
            ack = _cancel_fixed_cli(values, spec.request.batch_id)
            assert ack["state"] == "STOPPING" and ack["batch_cleanup_complete"] is False
            assert ack["owned_descendants_gone"] is False
            assert ack["assigned_ros_domains_clear"] is False
            assert ack["cleanup_receipt_sha256"] is None
            return wait()

        monkeypatch.setattr(composition, "_wait_broker_ready", observe_cancel_before_workers)
        run_entered = True
        summary = composition.run()
        assert composition.coordinator.snapshot().terminal_reason == "WEB_CANCEL_REQUESTED"
        assert summary.point_statuses == {"task_start": PointStatus.UNRUN}
        assert summary.qualification_passed is False
        assert summary.batch_cleanup_complete is (not corrupt_cleanup)
        gates = json.loads((spec.request.evidence_root / "cleanup-gates.json").read_text())
        assert set(gates["actions"]) == {"stop_leases", "cancel_goal", "confirm_goal_cancelled", "request_recovery"}
        assert gates["cleanup_gates_passed"] is (not corrupt_cleanup)
        assert not path.exists()
    finally:
        if not run_entered:
            composition._release_partial()
            composition._release_runtime_ipc_root()


@pytest.mark.parametrize("key,value,reason", [
    ("SO101_FIXED_CONTROL_TOKEN", None, "FIXED_CONTROL_ENV_INCOMPLETE"),
    ("SO101_FIXED_CONTROL_TOKEN", "predictable", "FIXED_CONTROL_TOKEN_INVALID"),
    ("SO101_FIXED_CONTROL_CAMPAIGN_ID", "bad/campaign", "FIXED_CONTROL_CAMPAIGN_INVALID"),
    ("SO101_FIXED_CONTROL_EPOCH", "0", "FIXED_CONTROL_EPOCH_INVALID"),
    ("SO101_FIXED_CONTROL_SOCKET", "/tmp/unbound-control.sock", "FIXED_CONTROL_SOCKET_INVALID"),
])
def test_fixed_cli_rejects_unbound_credentials_before_allocation(tmp_path, monkeypatch, key, value, reason):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    spec, values = _fixed_web_spec(tmp_path, monkeypatch)
    if value is None:
        monkeypatch.delenv(key)
    else:
        monkeypatch.setenv(key, value)
    composition = None
    try:
        with pytest.raises(CliError, match=reason):
            composition = ProductionBatchComposition(
                spec, resource_probe=_FixedWebProbe(), claim_root=tmp_path / "claims",
            )
        assert not spec.request.evidence_root.exists()
        assert all(name not in os.environ for name in values)
    finally:
        if composition is not None:
            composition._release_partial()
            composition._release_runtime_ipc_root()


def test_fixed_cli_epoch_matches_real_journal_before_endpoint_or_worker_setup(tmp_path, monkeypatch):
    from dataclasses import replace

    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    spec, values = _fixed_web_spec(tmp_path, monkeypatch)
    # A short source-test root needs no external IPC. Retain its allocated
    # evidence and partial cleanup record; do not delete durable scratch.
    monkeypatch.delenv("SO101_PARALLEL_IPC_BASE")
    root = _scratch_root() / "qe"
    spec = replace(spec, request=replace(spec.request, evidence_root=root))
    monkeypatch.setenv("SO101_FIXED_CONTROL_SOCKET", str(root / "control/control.sock"))
    monkeypatch.setenv("SO101_FIXED_CONTROL_EPOCH", "2")
    with pytest.raises(CliError, match="FIXED_CONTROL_COORDINATOR_EPOCH_MISMATCH") as rejected:
        ProductionBatchComposition(spec, resource_probe=_FixedWebProbe(), claim_root=tmp_path / "claims")
    assert rejected.value.partial_cleanup["journal"]["succeeded"] is True
    assert rejected.value.partial_cleanup["worker_servers"] == []
    assert not (root / "control/control.sock").exists()
    assert all(key not in os.environ for key in values)


def test_fixed_cli_credentials_cannot_open_an_adaptive_pool_endpoint(tmp_path, monkeypatch):
    from dataclasses import replace

    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition
    from so101_demo.parallel_batch.adaptive_contracts import (
        _new_pool_request_for_production_factory,
    )

    spec, values = _fixed_web_spec(tmp_path, monkeypatch)
    pool = _new_pool_request_for_production_factory(
        batch_id=spec.request.batch_id, run_mode=spec.request.run_mode,
        selected_point_ids=spec.request.selected_point_ids, worker_count=1,
        evidence_root=spec.request.evidence_root,
    )
    with pytest.raises(CliError, match="FIXED_CONTROL_REQUEST_REQUIRED"):
        ProductionBatchComposition(replace(spec, request=pool), resource_probe=_FixedWebProbe())
    assert not spec.request.evidence_root.exists()
    assert all(key not in os.environ for key in values)


def test_fixed_cli_checks_authenticated_stop_during_broker_ready_loop(tmp_path, monkeypatch):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.composition import ProductionBatchComposition

    spec, values = _fixed_web_spec(tmp_path, monkeypatch, run_mode="plan_only")
    composition = ProductionBatchComposition(
        spec, resource_probe=_FixedWebProbe(), claim_root=tmp_path / "claims",
        broker_command_builder=lambda _owner: ("unused-broker",),
    )
    slept = []

    def observe_stop_at_first_sleep(delay):
        slept.append(delay)
        ack = _cancel_fixed_cli(values, spec.request.batch_id)
        assert ack["state"] == "STOPPING" and ack["batch_cleanup_complete"] is False

    composition._start_servers()
    try:
        monkeypatch.setattr(composition, "_sleep", observe_stop_at_first_sleep)
        with pytest.raises(CliError, match="WEB_CANCEL_REQUESTED"):
            composition._wait_broker_ready()
        assert slept == [0.01]
        assert composition.supervisor.processes == ()
    finally:
        composition._stop_servers()
        composition.journal.close()
        composition.allocator.close()
        composition._release_runtime_ipc_root()


def test_runtime_package_root_uses_installed_share_for_copied_module(tmp_path):
    from so101_demo.cli.mujoco_batch.provenance import _runtime_package_root

    module_path = (
        tmp_path
        / "install/so101_demo_py/lib/python3.12/site-packages/so101_demo/cli"
        / "mujoco_parallel_batch.py"
    )
    module_path.parent.mkdir(parents=True)
    module_path.write_text("# installed module\n", encoding="utf-8")
    share = tmp_path / "install/so101_demo_py/share/so101_demo_py"
    policy = share / "config/policies/dynamic_cup_pick/mujoco.yaml"
    policy.parent.mkdir(parents=True)
    policy.write_text("schema_version: 1\n", encoding="utf-8")

    assert _runtime_package_root(
        module_path=module_path,
        share_directory_provider=lambda _package: str(share),
    ) == share


def test_shutdown_signal_handler_is_idempotent_while_cleanup_unwinds(monkeypatch):
    import signal

    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_parallel_batch import _run_with_shutdown_signals

    handlers = {}

    def install(number, handler):
        previous = handlers.get(number, signal.SIG_DFL)
        handlers[number] = handler
        return previous

    monkeypatch.setattr(signal, "signal", install)

    def interrupted_call():
        try:
            handlers[signal.SIGTERM](signal.SIGTERM, None)
        except CliError as error:
            handlers[signal.SIGINT](signal.SIGINT, None)
            raise error

    with pytest.raises(CliError, match="SHUTDOWN_SIGNAL:SIGTERM"):
        _run_with_shutdown_signals(interrupted_call)


def test_worker_result_evidence_is_private_structured_and_no_replace(tmp_path):
    from so101_demo.cli.mujoco_batch.worker_process import _write_worker_results
    from so101_demo.parallel_batch.worker_parts.contracts import WorkerRunResult

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


def test_recovered_initial_gate_terminal_is_not_a_worker_process_failure():
    from so101_demo.cli.mujoco_batch.worker_process import _worker_results_failed
    from so101_demo.parallel_batch.contracts.common import AttemptStatus, ValidationStatus

    recovered = SimpleNamespace(
        stopped_reason="INITIAL_GATE_FAILED",
        terminal_status=AttemptStatus.INVALID,
        recovered=True,
    )
    ordinary = SimpleNamespace(
        stopped_reason="NO_POINT",
        terminal_status=None,
        recovered=False,
    )

    assert _worker_results_failed((recovered, ordinary)) is False
    assert _worker_results_failed((
        SimpleNamespace(
            stopped_reason="INITIAL_GATE_FAILED",
            terminal_status=ValidationStatus.VALIDATION_INVALID,
            recovered=True,
        ),
        ordinary,
    )) is False
    assert _worker_results_failed((
        SimpleNamespace(
            stopped_reason="INITIAL_GATE_FAILED",
            terminal_status=AttemptStatus.INVALID,
            recovered=False,
        ),
    )) is True
    assert _worker_results_failed((
        SimpleNamespace(
            stopped_reason="INITIAL_GATE_FAILED",
            terminal_status=None,
            recovered=True,
        ),
    )) is True


def test_adaptive_worker_process_classifies_recovered_invalid_as_infrastructure():
    from so101_demo.cli.mujoco_batch.worker_process import _worker_results_failed
    from so101_demo.parallel_batch.contracts.common import AttemptStatus

    invalid = SimpleNamespace(
        point_id="task_start",
        stopped_reason="INITIAL_GATE_FAILED",
        terminal_status=AttemptStatus.INVALID,
        recovered=True,
    )
    exhausted = SimpleNamespace(
        point_id=None,
        stopped_reason="NO_POINT",
        terminal_status=None,
        recovered=False,
    )
    stopped = SimpleNamespace(
        point_id=None,
        stopped_reason="STOP_REQUESTED",
        terminal_status=None,
        recovered=False,
    )

    assert _worker_results_failed((invalid, exhausted)) is False
    assert _worker_results_failed(
        (invalid, exhausted), adaptive_workers=True
    ) is True
    assert _worker_results_failed(
        (exhausted, stopped), adaptive_workers=True
    ) is False


@pytest.mark.parametrize(
    "changes,error",
    [
        ({"worker_count": "9"}, "WORKER_COUNT"),
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
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    with pytest.raises(CliError, match=error):
        prepare_batch(argv(tmp_path / "batch", **changes), provenance_verifier=verified)


def test_relative_catalog_and_config_paths_are_supported(tmp_path, monkeypatch):
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    monkeypatch.chdir(PACKAGE)
    prepared = prepare_batch(
        argv(
            tmp_path / "batch",
            points="config/mujoco/moveit_expert_validation_points.yaml",
            config="config/mujoco/parallel_batch_linux_cuda.yaml",
        ),
        provenance_verifier=verified,
    )
    assert len(prepared.request.selected_point_ids) == 20


def test_duplicate_batch_root_rejected_before_provenance_side_effect(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    root = tmp_path / "batch"
    root.mkdir()
    called = []
    with pytest.raises(CliError, match="DUPLICATE_BATCH"):
        prepare_batch(argv(root), provenance_verifier=lambda spec: called.append(spec))
    assert called == []


def test_explicit_resume_replays_started_dry_run_and_continues_remaining_point(tmp_path):
    """A production recovery mode reaches replay without starting physical runtime."""
    from so101_demo.cli.mujoco_batch.common import _write_json
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
    root = scratch / 'r'
    values = argv(
        root,
        worker_count='1',
        point_id=('task_start', 'sample_01_near_left'),
    )
    first = prepare_batch(values, provenance_verifier=verified)
    original = ProductionBatchComposition(
        first,
        resource_probe=Probe(),
        claim_root=scratch / 'rc',
        worker_launcher=lambda owner, path: owner._run_worker_local(path),
    )
    _write_json(root / 'batch_manifest.json', first.manifest)
    original.coordinator.register_worker('worker-01', generation=1)
    lease = original.coordinator.grant_lease('worker-01', generation=1)
    original.coordinator.ack_lease(lease, request_key='crash-ack')
    original.coordinator.ack_validation_started(
        lease,
        request_key='crash-start',
        gate_summary={
            'schema_version': 1,
            'kind': 'SCHEDULER_START',
            'batch_id': lease.batch_id,
            'coordinator_epoch': lease.coordinator_epoch,
            'worker_id': lease.worker_id,
            'worker_generation': lease.worker_generation,
            'point_id': lease.point_id,
            'attempt_id': lease.attempt_id,
            'lease_generation': lease.lease_generation,
            'point_gate_applicable': False,
            'physical_runtime_started': False,
            'scheduler_only': True,
        },
    )
    original.supervisor.write_manifest()
    original._release_partial()

    recovered = prepare_batch(values + ['--resume'], provenance_verifier=verified)
    assert recovered.resume is True
    resumed = ProductionBatchComposition(
        recovered,
        resource_probe=Probe(),
        claim_root=scratch / 'rc',
        worker_launcher=lambda owner, path: owner._run_worker_local(path),
    )
    assert resumed.journal.coordinator_epoch == 2
    result = resumed.run()
    assert result.validation_statuses == {
        'task_start': ValidationStatus.VALIDATION_INVALID,
        'sample_01_near_left': ValidationStatus.VALIDATION_PASSED,
    }
    assert result.point_statuses == {
        'task_start': PointStatus.UNRUN,
        'sample_01_near_left': PointStatus.UNRUN,
    }
    assert resumed.resource_manifest.workers[0].generation == 2
    assert all(
        b'ATTEMPT_STARTED' not in path.read_bytes()
        for path in (root / 'coordinator/events').glob('*.journal')
    )


def test_explicit_resume_rejects_changed_frozen_batch_manifest(tmp_path):
    """Recovery cannot change selection, capacity, mode, root, or provenance."""
    from so101_demo.cli.mujoco_batch.common import CliError, _write_json
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    root = tmp_path / 'batch'
    prepared = prepare_batch(argv(root), provenance_verifier=verified)
    root.mkdir(mode=0o700)
    changed = dict(prepared.manifest)
    changed['worker_count'] = 3
    _write_json(root / 'batch_manifest.json', changed)

    with pytest.raises(CliError, match='RECOVERY_BATCH_MANIFEST_MISMATCH'):
        prepare_batch(argv(root) + ['--resume'], provenance_verifier=verified)


def test_selection_uses_catalog_order_and_hash_and_omission_selects_all(tmp_path):
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    selected = prepare_batch(
        argv(
            tmp_path / "selected",
            worker_count="2",
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
    assert "fixed_partitions" not in complete.manifest


def test_stale_or_inconsistent_provenance_is_rejected(tmp_path):
    from so101_demo.cli.mujoco_batch.common import CliError
    from so101_demo.cli.mujoco_batch.request import prepare_batch

    with pytest.raises(CliError, match="PROVENANCE"):
        prepare_batch(argv(tmp_path / "batch"), provenance_verifier=lambda _spec: False)


@pytest.mark.parametrize("mode", [RunMode.DRY_RUN, RunMode.PLAN_ONLY])
def test_nonexecute_exit_and_aggregate_matrix(mode):
    from so101_demo.cli.mujoco_batch.outcome import outcome_document

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
    from so101_demo.cli.mujoco_batch.outcome import outcome_document

    passed = summary(RunMode.EXECUTE, {"task_start": PointStatus.PASSED})
    code, document = outcome_document(passed)
    assert code == 0
    assert document["qualification_applicable"] is True
    assert document["qualification_passed"] is True
    assert outcome_document(summary(RunMode.EXECUTE, {"task_start": PointStatus.FAILED}))[0] == 1
    assert outcome_document(summary(RunMode.EXECUTE, {"task_start": PointStatus.PASSED}, cleanup=False))[0] == 1


@pytest.mark.parametrize("mode", [RunMode.DRY_RUN, RunMode.PLAN_ONLY])
def test_nonexecute_dependency_failure_keeps_validation_history_but_exits_nonzero(mode):
    from so101_demo.cli.mujoco_batch.outcome import outcome_document

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
                        point_id=("task_start",),
        ),
        provenance_verifier=verified,
        composition_factory=Composition,
    ) == 1
    assert (root / "aggregate_results.json").read_text() == "coordinator-owned"
