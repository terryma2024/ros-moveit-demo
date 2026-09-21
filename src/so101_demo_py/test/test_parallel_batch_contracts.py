import hashlib
from dataclasses import fields
from pathlib import Path

import pytest
import yaml


PACKAGE = Path(__file__).resolve().parents[1]
POINTS_PATH = PACKAGE / "config/mujoco/moveit_expert_validation_points_v1.yaml"
CONFIG_PATH = PACKAGE / "config/mujoco/parallel_batch_v1.yaml"


def test_capacity_and_frozen_points():
    """A changed catalog or insufficient startup capacity must be rejected."""

    from so101_demo.parallel_batch.contracts import ContractError, validate_capacity

    assert hashlib.sha256(POINTS_PATH.read_bytes()).hexdigest() == (
        "c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5"
    )
    document = yaml.safe_load(POINTS_PATH.read_text(encoding="utf-8"))
    ids = [item["id"] for item in document["points"]]
    assert len(ids) == len(set(ids)) == 20
    assert [ids[index] for index in (0, 8, 17, 18, 19)] == [
        "task_start",
        "sample_05_near_center",
        "sample_14_far_right",
        "sample_15_far_center",
        "sample_16_far_right",
    ]
    with pytest.raises(ContractError, match="INSUFFICIENT_CAPACITY"):
        validate_capacity(worker_count=2, max_points_per_worker=9, point_count=20)


@pytest.mark.parametrize("value", [True, 0, -1])
def test_capacity_rejects_boolean_zero_and_negative_values(value):
    """Treating bool or nonpositive capacity as an integer admits invalid batches."""

    from so101_demo.parallel_batch.contracts import ContractError, validate_capacity

    with pytest.raises(ContractError, match="POSITIVE_INTEGER"):
        validate_capacity(worker_count=value, max_points_per_worker=10, point_count=20)


def test_capacity_accepts_exact_and_excess_capacity():
    """Exact and surplus worker capacity must retain the CLI's selected capacity."""

    from so101_demo.parallel_batch.contracts import validate_capacity

    assert validate_capacity(worker_count=2, max_points_per_worker=10, point_count=20) == 20
    assert validate_capacity(worker_count=3, max_points_per_worker=10, point_count=20) == 30


def test_runtime_config_loads_the_frozen_values():
    """Changing closed runtime defaults must require a new configuration artifact."""

    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config

    config = load_parallel_runtime_config(CONFIG_PATH)
    assert config.backend == "mujoco"
    assert config.ros_domain_ids == (181, 182, 183, 184, 185, 186, 187, 188)
    assert config.max_worker_count == 8
    assert config.max_points_per_worker_upper_bound == 20
    assert config.heartbeat_interval_s == 1.0
    assert config.lease_duration_s == 300.0
    assert config.batch_hard_timeout_s == 5400.0
    assert config.broker_queue_capacity_per_model == 3
    assert config.requested_device == "cuda"
    assert config.allow_cpu_fallback is False
    assert config.required_live_headroom_ratio == 0.20


@pytest.mark.parametrize(
    ("mutated_key", "mutated_value", "error"),
    [
        ("unexpected", 1, "UNKNOWN_CONFIG_FIELD"),
        ("heartbeat_interval_s", float("inf"), "FINITE"),
        ("max_worker_count", True, "POSITIVE_INTEGER"),
    ],
)
def test_runtime_config_rejects_unknown_boolean_and_nonfinite_values(
    tmp_path, mutated_key, mutated_value, error
):
    """Loose YAML parsing could silently admit an unsafe scheduler configuration."""

    from so101_demo.parallel_batch.contracts import ContractError, load_parallel_runtime_config

    document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    document[mutated_key] = mutated_value
    path = tmp_path / "parallel_batch.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContractError, match=error):
        load_parallel_runtime_config(path)


def test_closed_statuses_keep_candidates_distinct_from_accepted_poses():
    """A model candidate must not be mistaken for the Worker-local POSE_ACCEPTED latch."""

    from so101_demo.parallel_batch.contracts import (
        AttemptStatus,
        ModelOutcome,
        PointStatus,
        ValidationStatus,
        WorkerState,
    )

    assert tuple(PointStatus) == (
        PointStatus.UNRUN,
        PointStatus.PASSED,
        PointStatus.FAILED,
        PointStatus.INDETERMINATE,
    )
    assert tuple(ValidationStatus) == (
        ValidationStatus.VALIDATION_PASSED,
        ValidationStatus.VALIDATION_FAILED,
        ValidationStatus.VALIDATION_INVALID,
    )
    assert ModelOutcome.QUALIFIED.value == "QUALIFIED"
    assert "POSE_ACCEPTED" not in {outcome.value for outcome in ModelOutcome}
    assert AttemptStatus.INVALID.value == "INVALID"
    assert tuple(WorkerState) == (
        WorkerState.STARTING,
        WorkerState.AVAILABLE,
        WorkerState.LEASED,
        WorkerState.INITIALIZING,
        WorkerState.EXECUTING,
        WorkerState.FINALIZING,
        WorkerState.RECOVERING,
        WorkerState.QUARANTINED,
        WorkerState.STOPPED,
    )


def test_batch_request_and_identities_reject_path_traversal_and_mixed_execution_ids():
    """A mixed attempt/validation identity could authorize the wrong sealed workspace."""

    from so101_demo.parallel_batch.contracts import (
        BatchRequest,
        ContractError,
        ExecutionKind,
        InferenceRequest,
        RunMode,
    )

    with pytest.raises(ContractError, match="ABSOLUTE_EVIDENCE_ROOT"):
        BatchRequest(
            batch_id="batch-1",
            run_mode=RunMode.DRY_RUN,
            selected_point_ids=("task_start",),
            worker_count=1,
            max_points_per_worker=1,
            evidence_root=Path("relative/evidence"),
        )
    request_fields = dict(
        request_id="request-1",
        model_id="yolo",
        execution_kind=ExecutionKind.ATTEMPT,
        batch_id="batch-1",
        coordinator_epoch=1,
        worker_id="worker-01",
        worker_generation=1,
        point_id="task_start",
        lease_generation=1,
        reset_epoch="reset-1",
        image_timestamp_s=1.0,
        input_relative_path="perception/input/rgb.npy",
        input_sha256="a" * 64,
        deadline_s=5.0,
        attempt_id="attempt-1",
    )
    with pytest.raises(ContractError, match="MIXED_EXECUTION_IDENTITY"):
        InferenceRequest(**request_fields, validation_id="validation-1")
    with pytest.raises(ContractError, match="SAFE_RELATIVE_PATH"):
        InferenceRequest(**(request_fields | {"input_relative_path": "../rgb.npy"}))


def test_validation_summary_cannot_claim_execute_qualification():
    """Twenty passing validation records must never become a 20/20 execute qualification."""

    from so101_demo.parallel_batch.contracts import (
        BatchSummary,
        PointStatus,
        RunMode,
        ValidationStatus,
    )

    point_ids = tuple(f"point-{index:02d}" for index in range(20))
    summary = BatchSummary(
        run_mode=RunMode.PLAN_ONLY,
        point_statuses={point_id: PointStatus.UNRUN for point_id in point_ids},
        validation_statuses={
            point_id: ValidationStatus.VALIDATION_PASSED for point_id in point_ids
        },
        batch_cleanup_complete=True,
        batch_terminal=True,
        terminal_reason="POINTS_COMPLETE",
    )

    assert summary.validation_complete is True
    assert summary.validation_passed is True
    assert summary.qualification_applicable is False
    assert summary.qualification_passed is False


def test_all_passing_dry_run_validations_never_qualify_execute_coverage():
    """A complete dry-run projection must not become a physical 20/20 result."""

    from so101_demo.parallel_batch.contracts import (
        BatchSummary,
        PointStatus,
        RunMode,
        ValidationStatus,
    )

    point_ids = tuple(f"point-{index:02d}" for index in range(20))
    summary = BatchSummary(
        run_mode=RunMode.DRY_RUN,
        point_statuses={point_id: PointStatus.UNRUN for point_id in point_ids},
        validation_statuses={
            point_id: ValidationStatus.VALIDATION_PASSED for point_id in point_ids
        },
        batch_terminal=True,
        terminal_reason="POINTS_COMPLETE",
    )

    assert summary.validation_complete is True
    assert summary.validation_passed is True
    assert set(summary.point_statuses.values()) == {PointStatus.UNRUN}
    assert summary.qualification_applicable is False
    assert summary.qualification_passed is False


@pytest.mark.parametrize("identifier", ["../escape", "/absolute", ".", "..", "worker/01"])
def test_path_bearing_identifiers_reject_traversal_and_separators(identifier):
    """Path-like identities must not escape their coordinator-owned workspace."""

    from so101_demo.parallel_batch.contracts import (
        AttemptIdentity,
        ContractError,
        ValidationIdentity,
    )

    attempt = dict(
        batch_id="batch-1",
        coordinator_epoch=1,
        worker_id="worker-01",
        worker_generation=1,
        point_id="task_start",
        attempt_id="attempt-1",
        lease_generation=1,
    )
    validation = {
        "batch_id": "batch-1",
        "coordinator_epoch": 1,
        "worker_id": "worker-01",
        "worker_generation": 1,
        "point_id": "task_start",
        "validation_id": "validation-1",
        "lease_generation": 1,
    }
    for field_name in ("batch_id", "worker_id", "point_id", "attempt_id"):
        with pytest.raises(ContractError, match="IDENTIFIER"):
            AttemptIdentity(**(attempt | {field_name: identifier}))
    with pytest.raises(ContractError, match="IDENTIFIER"):
        ValidationIdentity(**(validation | {"validation_id": identifier}))


def test_relative_input_path_rejects_dot_component():
    """The current-directory path is not a sealed perception input filename."""

    from so101_demo.parallel_batch.contracts import (
        ContractError,
        ExecutionKind,
        InferenceRequest,
    )

    with pytest.raises(ContractError, match="SAFE_RELATIVE_PATH"):
        InferenceRequest(
            request_id="request-1",
            model_id="yolo",
            execution_kind=ExecutionKind.ATTEMPT,
            batch_id="batch-1",
            coordinator_epoch=1,
            worker_id="worker-01",
            worker_generation=1,
            point_id="task_start",
            lease_generation=1,
            reset_epoch="reset-1",
            image_timestamp_s=1.0,
            input_relative_path=".",
            input_sha256="a" * 64,
            deadline_s=5.0,
            attempt_id="attempt-1",
        )


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("max_worker_count", 4),
        ("heartbeat_timeout_s", 6.0),
        ("ros_domain_ids", [181, 182, 184]),
        ("broker_queue_capacity_per_model", 4),
        ("max_frame_age_s", 4.0),
        ("max_rgbd_skew_s", 0.01),
        ("max_tf_skew_s", 0.01),
        ("min_available_gpu_gib", 7),
    ],
)
def test_runtime_config_rejects_reviewed_value_drift(tmp_path, key, value):
    """Changing any admission-critical v1 value requires a new reviewed config."""

    from so101_demo.parallel_batch.contracts import ContractError, load_parallel_runtime_config

    document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    document[key] = value
    path = tmp_path / "drifted.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    with pytest.raises(ContractError, match="FROZEN_RUNTIME_VALUE"):
        load_parallel_runtime_config(path)


def test_runtime_config_exposes_reviewed_model_hashes_without_yaml_schema_drift():
    """Model provenance must be frozen even though the reviewed YAML has no hash keys."""

    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config

    config = load_parallel_runtime_config(CONFIG_PATH)
    assert config.yolo_weights_sha256 == (
        "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"
    )
    assert config.grounded_sam_manifest_sha256 == (
        "b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05"
    )
    assert "yolo_weights_sha256" not in yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_runtime_schema_and_batch_selection_reject_coercible_types(tmp_path):
    """Float schema versions and string selections must not be normalized into valid inputs."""

    from so101_demo.parallel_batch.contracts import (
        BatchRequest,
        ContractError,
        RunMode,
        load_parallel_runtime_config,
    )

    document = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    document["schema_version"] = 1.0
    path = tmp_path / "float-schema.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    with pytest.raises(ContractError, match="SCHEMA_VERSION"):
        load_parallel_runtime_config(path)
    with pytest.raises(ContractError, match="POINT_ID_SEQUENCE"):
        BatchRequest(
            batch_id="batch-1",
            run_mode=RunMode.DRY_RUN,
            selected_point_ids="abc",
            worker_count=1,
            max_points_per_worker=1,
            evidence_root=Path("/tmp/parallel-evidence"),
        )


def test_batch_request_rejects_duplicate_empty_and_overbound_selection_controls():
    """Duplicate IDs and counts beyond frozen admission limits must fail before leasing."""

    from so101_demo.parallel_batch.contracts import BatchRequest, ContractError, RunMode

    shared = dict(
        batch_id="batch-1",
        run_mode=RunMode.DRY_RUN,
        evidence_root=Path("/tmp/parallel-evidence"),
    )
    with pytest.raises(ContractError, match="UNIQUE_POINT_IDS"):
        BatchRequest(
            **shared,
            selected_point_ids=("task_start", "task_start"),
            worker_count=1,
            max_points_per_worker=2,
        )
    with pytest.raises(ContractError, match="EMPTY_ID"):
        BatchRequest(**shared, selected_point_ids=("",), worker_count=1, max_points_per_worker=1)
    with pytest.raises(ContractError, match="MAX_WORKER_COUNT"):
        BatchRequest(
            **shared,
            selected_point_ids=("task_start",),
            worker_count=9,
            max_points_per_worker=1,
        )
    with pytest.raises(ContractError, match="MAX_POINTS_PER_WORKER"):
        BatchRequest(
            **shared,
            selected_point_ids=("task_start",),
            worker_count=1,
            max_points_per_worker=21,
        )


def test_lease_and_normalized_validation_identity_reject_invalid_boundaries():
    """Nonfinite leases and mixed response identities cannot be fenced safely."""

    from so101_demo.parallel_batch.contracts import (
        ContractError,
        ExecutionKind,
        LeaseIdentity,
        NormalizedInferenceResponseIdentity,
    )

    lease = dict(
        batch_id="batch-1",
        coordinator_epoch=1,
        worker_id="worker-01",
        worker_generation=1,
        point_id="task_start",
        attempt_id="attempt-1",
        lease_generation=1,
        lease_issued_monotonic_s=2.0,
        lease_deadline_monotonic_s=1.0,
    )
    with pytest.raises(ContractError, match="LEASE_DEADLINE_ORDER"):
        LeaseIdentity(**lease)
    with pytest.raises(ContractError, match="FINITE"):
        LeaseIdentity(**(lease | {"lease_deadline_monotonic_s": float("inf")}))
    with pytest.raises(ContractError, match="MIXED_EXECUTION_IDENTITY"):
        NormalizedInferenceResponseIdentity(
            request_id="request-1",
            execution_kind=ExecutionKind.VALIDATION,
            batch_id="batch-1",
            coordinator_epoch=1,
            worker_id="worker-01",
            worker_generation=1,
            point_id="task_start",
            lease_generation=1,
            attempt_id="attempt-1",
        )


def test_pending_validation_and_batch_terminality_keep_qualification_false():
    """A pending validation projection is not complete and cannot contaminate physical status."""

    from so101_demo.parallel_batch.contracts import (
        BatchSummary,
        ContractError,
        PointStatus,
        RunMode,
        ValidationStatus,
    )

    pending = BatchSummary(
        run_mode=RunMode.DRY_RUN,
        point_statuses={"task_start": PointStatus.UNRUN, "point-2": PointStatus.UNRUN},
        validation_statuses={"task_start": ValidationStatus.VALIDATION_PASSED},
        batch_terminal=False,
    )
    assert pending.validation_complete is False
    assert pending.validation_passed is False
    assert pending.qualification_applicable is False
    assert pending.qualification_passed is False
    terminal_execute = BatchSummary(
        run_mode=RunMode.EXECUTE,
        point_statuses={"task_start": PointStatus.UNRUN},
        batch_terminal=True,
    )
    assert terminal_execute.execution_complete is True
    with pytest.raises(ContractError, match="VALIDATION_PHYSICAL_UNRUN"):
        BatchSummary(
            run_mode=RunMode.PLAN_ONLY,
            point_statuses={"task_start": PointStatus.PASSED},
            validation_statuses={"task_start": ValidationStatus.VALIDATION_PASSED},
            batch_terminal=True,
        )


def test_execute_qualification_requires_normal_points_complete_terminal_reason():
    """Durable PASSED points cannot qualify a dependency-failed batch."""

    from so101_demo.parallel_batch.contracts import BatchSummary, PointStatus, RunMode

    statuses = {"task_start": PointStatus.PASSED}
    completed = BatchSummary(
        run_mode=RunMode.EXECUTE,
        point_statuses=statuses,
        batch_terminal=True,
        batch_cleanup_complete=True,
        terminal_reason="POINTS_COMPLETE",
    )
    dependency_failed = BatchSummary(
        run_mode=RunMode.EXECUTE,
        point_statuses=statuses,
        batch_terminal=True,
        batch_cleanup_complete=True,
        terminal_reason="SHARED_DEPENDENCY_UNAVAILABLE",
    )

    assert completed.qualification_passed is True
    assert dependency_failed.point_statuses == statuses
    assert dependency_failed.coverage_complete is True
    assert dependency_failed.qualification_passed is False


@pytest.mark.parametrize("run_mode", ["DRY_RUN", "PLAN_ONLY"])
def test_validation_pass_requires_normal_points_complete_terminal_reason(run_mode):
    """A dependency failure preserves validation history without reporting pass."""

    from so101_demo.parallel_batch.contracts import (
        BatchSummary,
        PointStatus,
        RunMode,
        ValidationStatus,
    )

    summary = BatchSummary(
        run_mode=RunMode[run_mode],
        point_statuses={"task_start": PointStatus.UNRUN},
        validation_statuses={"task_start": ValidationStatus.VALIDATION_PASSED},
        batch_terminal=True,
        batch_cleanup_complete=True,
        terminal_reason="SHARED_DEPENDENCY_UNAVAILABLE",
    )

    assert summary.validation_statuses["task_start"] is ValidationStatus.VALIDATION_PASSED
    assert summary.validation_complete is True
    assert summary.validation_passed is False


@pytest.mark.parametrize("workers", [1, 2, 8])
def test_fixed_batch_contract_supports_exact_count_through_eight(tmp_path, workers):
    from so101_demo.parallel_batch.contracts import BatchRequest, RunMode
    request = BatchRequest("eight", RunMode.EXECUTE, tuple(f"p{i}" for i in range(20)),
                           workers, 20 if workers == 1 else 10 if workers == 2 else 3, tmp_path)
    assert request.worker_count == workers


def test_fixed_batch_nine_is_outside_supported_range(tmp_path):
    from so101_demo.parallel_batch.contracts import BatchRequest, RunMode, ContractError
    with pytest.raises(ContractError, match="MAX_WORKER_COUNT"):
        BatchRequest("nine", RunMode.EXECUTE, ("p1",), 9, 1, tmp_path)


V2_CONFIG_PATH = PACKAGE / "config/mujoco/parallel_batch_v2.yaml"


def test_v1_can_be_read_but_not_executed(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError, require_v2_execution
    with pytest.raises(ContractError) as error:
        require_v2_execution(1, 1)
    assert error.value.code == 'LEGACY_CONTRACT_EXECUTION_FORBIDDEN'
    with pytest.raises(ContractError):
        require_v2_execution(3, 2)
    assert require_v2_execution(2, 2) is None


def test_v1_yaml_bytes_and_hash_are_frozen():
    """v1 stays byte-identical; the new contract must never migrate it in place."""

    assert hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest() == (
        "aadcac01da5342bd81cc560d12dd77e526a8b29751832f3bdd1f7e6f528a93a3"
    )


def test_historical_contract_view_is_readonly_and_byte_stable():
    from so101_demo.parallel_batch.contracts import read_historical_contract
    first = read_historical_contract(CONFIG_PATH)
    second = read_historical_contract(CONFIG_PATH)
    assert first.version == 1
    assert first.raw_sha256 == hashlib.sha256(CONFIG_PATH.read_bytes()).hexdigest()
    assert first.raw_sha256 == second.raw_sha256
    assert dict(first.payload) == dict(second.payload) == yaml.safe_load(CONFIG_PATH.read_text())
    assert first.readonly is True
    with pytest.raises(TypeError):
        first.payload["schema_version"] = 2
    with pytest.raises((TypeError, AttributeError)):
        first.raw_sha256 = "b" * 64


def test_historical_contract_rejects_unknown_versions(tmp_path):
    from so101_demo.parallel_batch.contracts import ContractError, read_historical_contract
    document = tmp_path / "future.yaml"
    document.write_text("schema_version: 3\n")
    with pytest.raises(ContractError) as error:
        read_historical_contract(document)
    assert error.value.code == "UNKNOWN_SCHEMA_VERSION"


def test_v2_config_is_closed_and_carries_no_quota_fields():
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config_v2
    config = load_parallel_runtime_config_v2(V2_CONFIG_PATH)
    assert config.schema_version == 2
    for removed in ("max_points_per_worker", "max_points_per_worker_upper_bound",
                    "min_logical_cpu_per_worker", "available_ram_base_gib",
                    "available_ram_per_worker_gib", "min_available_gpu_gib",
                    "required_live_headroom_ratio"):
        assert not hasattr(config, removed), removed
    assert config.heartbeat_timeout_s == 5.0
    assert config.batch_hard_timeout_s == 5400.0
    assert config.ros_domain_ids == (181, 182, 183, 184, 185, 186, 187, 188)
    assert config.max_worker_count == 8
    assert config.deployment.approved_profile_path is None
    assert config.deployment.approved_profile_sha256 is None
    assert config.deployment.promotion_record_path is None


def test_v2_config_rejects_unknown_duplicate_and_nonfinite_fields(tmp_path):
    from so101_demo.parallel_batch.contracts import (
        ContractError, load_parallel_runtime_config_v2)
    document = yaml.safe_load(V2_CONFIG_PATH.read_text())
    unknown = tmp_path / "unknown.yaml"
    document["execution"]["max_points_per_worker"] = 20
    unknown.write_text(yaml.safe_dump(document, sort_keys=False))
    with pytest.raises(ContractError) as error:
        load_parallel_runtime_config_v2(unknown)
    assert error.value.code.startswith("UNKNOWN_EXECUTION_FIELD")
    duplicate = tmp_path / "duplicate.yaml"
    duplicate.write_text(V2_CONFIG_PATH.read_text() + "\nschema_version: 2\n")
    with pytest.raises(ContractError) as error:
        load_parallel_runtime_config_v2(duplicate)
    assert error.value.code == "DUPLICATE_KEY"
    nonfinite = tmp_path / "nonfinite.yaml"
    document = yaml.safe_load(V2_CONFIG_PATH.read_text())
    document["execution"]["heartbeat_timeout_s"] = float("nan")
    nonfinite.write_text(yaml.safe_dump(document, sort_keys=False))
    with pytest.raises(ContractError) as error:
        load_parallel_runtime_config_v2(nonfinite)
    assert error.value.code.startswith("NONFINITE")


def test_v2_fixed_execution_config_is_mode_and_count_only():
    from so101_demo.parallel_batch.contracts import ContractError, FixedExecutionConfigV2
    assert FixedExecutionConfigV2(2, "SEQUENTIAL", 1).worker_count == 1
    assert FixedExecutionConfigV2(2, "PARALLEL", 8).execution_mode == "PARALLEL"
    with pytest.raises(ContractError):
        FixedExecutionConfigV2(1, "PARALLEL", 2)
    with pytest.raises(ContractError):
        FixedExecutionConfigV2(2, "ADAPTIVE", 2)
    with pytest.raises(ContractError):
        FixedExecutionConfigV2(2, "SEQUENTIAL", 2)
    with pytest.raises(ContractError):
        FixedExecutionConfigV2(2, "PARALLEL", 1)
    with pytest.raises(ContractError):
        FixedExecutionConfigV2(2, "PARALLEL", 9)


def test_v2_request_has_no_lifetime_quota_and_keeps_retry_single_point(tmp_path):
    from so101_demo.parallel_batch.contracts import (
        BatchKindV2, BatchRequestV2, ContractError, RunMode)
    request = BatchRequestV2("batch-a", RunMode.EXECUTE, tuple(f"p{i}" for i in range(20)),
                             2, tmp_path, BatchKindV2.FIRST_PASS)
    assert request.schema_version == 2
    assert not hasattr(request, "max_points_per_worker")
    retry = BatchRequestV2("batch-retry", RunMode.EXECUTE, ("p1",), 1, tmp_path,
                           BatchKindV2.FULL_RESTART_RETRY)
    assert retry.selected_point_ids == ("p1",)
    with pytest.raises(ContractError):
        BatchRequestV2("batch-retry", RunMode.EXECUTE, ("p1", "p2"), 1, tmp_path,
                       BatchKindV2.FULL_RESTART_RETRY)
    with pytest.raises(ContractError):
        BatchRequestV2("batch-retry", RunMode.EXECUTE, ("p1",), 2, tmp_path,
                       BatchKindV2.FULL_RESTART_RETRY)
    with pytest.raises(ContractError):
        BatchRequestV2("batch-nine", RunMode.EXECUTE, ("p1",), 9, tmp_path,
                       BatchKindV2.FIRST_PASS)


def test_runtime_config_loader_selects_the_parser_by_schema(tmp_path):
    """The broker transport loads a config shared by both generations, and the v1 parser
    refuses a v2 document (`UNKNOWN_CONFIG_FIELD: ['deployment', 'execution']`), which is
    exactly how the broker died at startup in run56. The loader must choose by schema."""

    from so101_demo.parallel_batch.contracts import (
        ContractError, load_runtime_config_any_schema)

    loaded = load_runtime_config_any_schema(V2_CONFIG_PATH)
    assert getattr(loaded, "schema_version", None) == 2
    unknown = tmp_path / "v9.yaml"
    unknown.write_text("schema_version: 9\n")
    with pytest.raises(ContractError, match="SCHEMA_VERSION"):
        load_runtime_config_any_schema(unknown)


# --------------------------------------------------------------------------------------
# Version 3: the active budget-free runtime contract (lightweight start guard plan, Task 3)
# --------------------------------------------------------------------------------------

V3_CONFIG_PATH = PACKAGE / "config/mujoco/parallel_batch_v3.yaml"


def _v3_document() -> dict:
    import yaml

    return yaml.safe_load(V3_CONFIG_PATH.read_text())


def test_v3_config_is_closed_budget_free_and_carries_the_guard():
    """The active document keeps the functional fields, adds the guard, and has no
    measurement, safety, coverage or deployment section left to consult."""

    import so101_demo.parallel_batch.contracts as contracts

    config = contracts.load_parallel_runtime_config_v3(V3_CONFIG_PATH)
    assert config.schema_version == 3
    assert config.max_worker_count == 8
    assert config.gpu_device.selector_kind == "INDEX"
    assert config.gpu_device.selector == "0"
    assert config.start_guard.timeout_s == 2.0
    assert config.start_guard.ram_minimum_bytes == 1 << 30
    document = _v3_document()
    assert set(document) == {"schema_version", "execution", "start_guard"}
    for retired in ("sampling", "safety", "coverage", "deployment", "measurement"):
        assert retired not in document
        assert retired not in document["execution"]
    field_names = {item.name for item in fields(contracts.ParallelRuntimeConfigV3)}
    for retired in ("measurement", "deployment", "profile_sha256", "qualification_sha256",
                    "execution_identity_sha256", "capacity_fraction"):
        assert retired not in field_names


def test_v3_execution_field_set_is_exactly_the_closed_list():
    import so101_demo.parallel_batch.contracts as contracts

    assert set(contracts.EXECUTION_V3_FIELDS) == set(
        item.name for item in fields(contracts.ParallelRuntimeConfigV3)
    ) - {"schema_version", "start_guard"}
    assert len(contracts.EXECUTION_V3_FIELDS) == 38
    assert contracts.START_GUARD_FIELDS == {
        "timeout_s", "cpu_busy_warn_fraction", "ram_minimum_bytes", "ram_minimum_fraction",
        "gpu_minimum_bytes"}


def test_v3_config_rejects_unknown_duplicate_and_legacy_sections(tmp_path):
    import yaml

    from so101_demo.parallel_batch.contracts import (
        ContractError, load_parallel_runtime_config_v3)

    document = _v3_document()

    extra_top = dict(document)
    extra_top["deployment"] = {"approved_profile_path": None}
    path = tmp_path / "extra-top.yaml"
    path.write_text(yaml.safe_dump(extra_top))
    with pytest.raises(ContractError, match="UNKNOWN_CONFIG_FIELD"):
        load_parallel_runtime_config_v3(path)

    extra_guard = _v3_document()
    extra_guard["start_guard"]["capacity_fraction"] = 0.8
    path = tmp_path / "extra-guard.yaml"
    path.write_text(yaml.safe_dump(extra_guard))
    with pytest.raises(ContractError, match="UNKNOWN_START_GUARD_FIELD"):
        load_parallel_runtime_config_v3(path)

    legacy_execution = _v3_document()
    legacy_execution["execution"]["safety"] = {"capacity_fraction": 0.8}
    path = tmp_path / "legacy-execution.yaml"
    path.write_text(yaml.safe_dump(legacy_execution))
    with pytest.raises(ContractError, match="UNKNOWN_EXECUTION_FIELD"):
        load_parallel_runtime_config_v3(path)

    missing_selector = _v3_document()
    missing_selector["execution"].pop("gpu_device")
    path = tmp_path / "missing-selector.yaml"
    path.write_text(yaml.safe_dump(missing_selector))
    with pytest.raises(ContractError, match="MISSING_EXECUTION_FIELD"):
        load_parallel_runtime_config_v3(path)

    bad_guard = _v3_document()
    bad_guard["start_guard"]["timeout_s"] = 60
    path = tmp_path / "bad-guard.yaml"
    path.write_text(yaml.safe_dump(bad_guard))
    with pytest.raises(ContractError, match="START_GUARD_INVALID"):
        load_parallel_runtime_config_v3(path)

    missing_guard = _v3_document()
    missing_guard.pop("start_guard")
    path = tmp_path / "missing-guard.yaml"
    path.write_text(yaml.safe_dump(missing_guard))
    with pytest.raises(ContractError, match="MISSING_CONFIG_FIELD"):
        load_parallel_runtime_config_v3(path)


def test_require_v3_execution_refuses_every_legacy_version():
    import so101_demo.parallel_batch.contracts as contracts

    contracts.require_v3_execution(3, 3)
    for request_version, config_version in ((1, 1), (2, 2), (3, 2), (2, 3), (True, 3)):
        with pytest.raises(contracts.ContractError,
                           match="CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"):
            contracts.require_v3_execution(request_version, config_version)


def test_v3_request_round_trips_and_history_reads_never_become_active(tmp_path):
    import so101_demo.parallel_batch.contracts as contracts

    request = contracts.BatchRequestV3(
        batch_id="v3-batch", run_mode=contracts.RunMode.EXECUTE, selected_point_ids=("p1", "p2"),
        worker_count=4, evidence_root=tmp_path, batch_kind=contracts.BatchKindV3.FIRST_PASS)
    document = contracts.batch_request_to_document(request)
    assert document["schema_version"] == 3
    assert set(document) == set(contracts.REQUEST_V3_FIELDS)
    restored = contracts.batch_request_from_document(document, for_execution=True)
    assert restored == request

    legacy = {"schema_version": 2, "batch_id": "old", "run_mode": "EXECUTE",
              "selected_point_ids": ["p1"], "worker_count": 1,
              "evidence_root": str(tmp_path), "batch_kind": "FIRST_PASS",
              "profile_sha256": "0" * 64}
    with pytest.raises(contracts.ContractError,
                       match="CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"):
        contracts.batch_request_from_document(legacy, for_execution=True)
    history_view = contracts.batch_request_from_document(legacy, for_execution=False)
    assert isinstance(history_view, dict) and not isinstance(history_view, contracts.BatchRequestV3)
    assert history_view["profile_sha256"] == "0" * 64


def test_v3_request_keeps_retry_single_point_n1(tmp_path):
    import so101_demo.parallel_batch.contracts as contracts

    contracts.BatchRequestV3(
        batch_id="retry-one", run_mode=contracts.RunMode.EXECUTE, selected_point_ids=("p1",),
        worker_count=1, evidence_root=tmp_path,
        batch_kind=contracts.BatchKindV3.FULL_RESTART_RETRY)
    for point_ids, workers in ((("p1", "p2"), 1), (("p1",), 2)):
        with pytest.raises(contracts.ContractError, match="RETRY_SINGLE_POINT_N1"):
            contracts.BatchRequestV3(
                batch_id="retry-bad", run_mode=contracts.RunMode.EXECUTE, selected_point_ids=point_ids,
                worker_count=workers, evidence_root=tmp_path,
                batch_kind=contracts.BatchKindV3.FULL_RESTART_RETRY)


def test_gpu_selector_requires_an_explicit_well_formed_choice():
    import so101_demo.parallel_batch.contracts as contracts

    assert contracts.GpuDeviceSelector("UUID", "GPU-abc").selector == "GPU-abc"
    assert contracts.GpuDeviceSelector("INDEX", "0").selector_kind == "INDEX"
    for kind, selector in (("HOST", "0"), ("INDEX", "zero"), ("INDEX", ""),
                           ("UUID", "0"), ("INDEX", "0.0")):
        with pytest.raises(contracts.ContractError):
            contracts.GpuDeviceSelector(kind, selector)


def test_runtime_config_loader_selects_v3_parser(tmp_path):
    import so101_demo.parallel_batch.contracts as contracts

    loaded = contracts.load_runtime_config_any_schema(V3_CONFIG_PATH)
    assert isinstance(loaded, contracts.ParallelRuntimeConfigV3)
    assert loaded.schema_version == 3
    assert isinstance(contracts.load_runtime_config_any_schema(V2_CONFIG_PATH),
                      contracts.ParallelRuntimeConfigV2)


def test_budget_environment_does_not_change_v3_loading(monkeypatch):
    """The retired authority environment must not influence the active contract."""

    import so101_demo.parallel_batch.contracts as contracts

    baseline = contracts.load_parallel_runtime_config_v3(V3_CONFIG_PATH)
    for name in ("SO101_VALIDATION_BUDGET_PROFILE", "SO101_VALIDATION_BUDGET_PROFILE_SHA256",
                 "SO101_VALIDATION_PROMOTION_RECORD", "SO101_VALIDATION_QUALIFICATION_PATHS",
                 "SO101_VALIDATION_EXECUTION_IDENTITY", "SO101_PARALLEL_RUNTIME_CONFIG",
                 "SO101_VALIDATION_PROVENANCE_BINDING"):
        monkeypatch.setenv(name, "/nonexistent/retired")
    monkeypatch.setenv("SO101_VALIDATION_LOCATION_BINDING", "/nonexistent/location.json")
    assert contracts.load_parallel_runtime_config_v3(V3_CONFIG_PATH) == baseline


# --------------------------------------------------------------------------------------
# Version 4: the closed macOS MPS W2 contract
#
# Version 4 keeps exactly two closed platform combinations. The Linux one
# (`cuda` + `proc_fd_unix`) is retained in the contract and covered by offline unit
# assertions only; the Darwin one (`mps` + `darwin_private_path_unix`) is what this
# task executes for real at exact worker_count=2.
# --------------------------------------------------------------------------------------

V4_CONFIG_PATH = PACKAGE / "config/mujoco/parallel_batch_v4_macos_mps_w2.yaml"
V3_CONFIG_SHA256 = "991b5c1b4fbd0cc1f0a97bd20a5b5a4e02028634f3f4ef288ad87554b383ab70"


def _v4_document() -> dict:
    return yaml.safe_load(V4_CONFIG_PATH.read_text())


def test_schema_v3_bytes_are_frozen_by_the_v4_work():
    """Adding v4 must not rewrite one byte of the v3 document or its parser surface."""

    import so101_demo.parallel_batch.contracts as contracts

    digest = hashlib.sha256(V3_CONFIG_PATH.read_bytes()).hexdigest()
    assert digest == V3_CONFIG_SHA256
    config = contracts.load_parallel_runtime_config_v3(V3_CONFIG_PATH)
    assert config.schema_version == 3
    assert config.requested_device == "cuda"
    assert config.max_worker_count == 8
    assert set(contracts.EXECUTION_V3_FIELDS) == set(
        item.name for item in fields(contracts.ParallelRuntimeConfigV3)
    ) - {"schema_version", "start_guard"}
    # v3 selects its platform the v3 way; the v4 accelerator vocabulary must not leak in.
    assert "accelerator" not in {item.name for item in fields(contracts.ParallelRuntimeConfigV3)}
    assert "ipc_transport" not in {item.name for item in fields(contracts.ParallelRuntimeConfigV3)}


def test_schema_v4_macos_document_resolves_the_closed_darwin_combination():
    """The shipped macOS document resolves to mps + darwin_private_path_unix + cgl at W2."""

    import so101_demo.parallel_batch.contracts as contracts

    config = contracts.load_parallel_runtime_config_v4(V4_CONFIG_PATH)
    assert isinstance(config, contracts.ParallelRuntimeConfigV4)
    assert config.schema_version == 4
    assert config.accelerator.kind is contracts.AcceleratorKind.MPS
    assert config.accelerator.selector == "default"
    assert config.requested_device == "mps"
    assert config.allow_cpu_fallback is False
    assert config.worker_count == 2
    assert config.ipc_transport is contracts.IpcTransport.DARWIN_PRIVATE_PATH_UNIX
    assert config.mujoco_gl == "cgl"
    assert config.mps_process_memory_fraction == 0.8
    assert config.start_guard.mps_minimum_headroom_bytes == 1 << 30


def test_schema_v4_retains_the_linux_combination_in_the_contract():
    """The Linux v4 combination stays declared even though this task cannot execute it."""

    import so101_demo.parallel_batch.contracts as contracts

    document = _v4_document()
    document["accelerator"] = {"kind": "cuda", "selector": "INDEX:0"}
    document["requested_device"] = "cuda"
    document["ipc_transport"] = "proc_fd_unix"
    document["mujoco_gl"] = "egl"
    # The MPS allocator cap and the unified-memory headroom belong to the Darwin combination.
    document["mps_process_memory_fraction"] = None
    document["start_guard"].pop("mps_minimum_headroom_bytes")
    config = contracts.parse_parallel_runtime_config_v4(document)
    assert config.accelerator.kind is contracts.AcceleratorKind.CUDA
    assert config.ipc_transport is contracts.IpcTransport.PROC_FD_UNIX
    assert config.mujoco_gl == "egl"
    assert config.worker_count == 2
    assert config.mps_process_memory_fraction is None
    assert config.mps_minimum_headroom_bytes is None


def test_schema_v4_refuses_mps_fields_on_the_linux_combination():
    """An MPS threshold or allocator cap must not be smuggled into the CUDA combination."""

    import so101_demo.parallel_batch.contracts as contracts

    linux = _v4_document()
    linux["accelerator"] = {"kind": "cuda", "selector": "INDEX:0"}
    linux["requested_device"] = "cuda"
    linux["ipc_transport"] = "proc_fd_unix"
    linux["mujoco_gl"] = "egl"

    leaking_cap = dict(linux)
    with pytest.raises(contracts.ContractError, match="MPS_PROCESS_MEMORY_FRACTION"):
        contracts.parse_parallel_runtime_config_v4(leaking_cap)

    leaking_headroom = _v4_document()
    leaking_headroom.update({
        "accelerator": {"kind": "cuda", "selector": "INDEX:0"},
        "requested_device": "cuda",
        "ipc_transport": "proc_fd_unix",
        "mujoco_gl": "egl",
        "mps_process_memory_fraction": None,
    })
    with pytest.raises(contracts.ContractError, match="MPS_MINIMUM_HEADROOM_BYTES"):
        contracts.parse_parallel_runtime_config_v4(leaking_headroom)


@pytest.mark.parametrize("worker_count", [1, 3, 4, 6, 8])
def test_schema_v4_platform_worker_count_is_exactly_two(worker_count):
    """W4/W6/W8 and W1 are outside this contract's declared platform support."""

    import so101_demo.parallel_batch.contracts as contracts

    document = _v4_document()
    document["worker_count"] = worker_count
    with pytest.raises(contracts.ContractError, match="PLATFORM_WORKER_COUNT_UNSUPPORTED"):
        contracts.parse_parallel_runtime_config_v4(document)


@pytest.mark.parametrize(
    "key, value",
    [
        ("requested_device", "cpu"),
        ("allow_cpu_fallback", True),
        ("ipc_transport", "auto_tcp"),
        ("mujoco_gl", "osmesa"),
    ],
)
def test_schema_v4_rejects_cpu_fallback_and_cross_platform_combinations(key, value):
    """No CPU device, CPU fallback, arbitrary TCP transport or third GL backend is admitted."""

    import so101_demo.parallel_batch.contracts as contracts

    document = _v4_document()
    document[key] = value
    with pytest.raises(contracts.ContractError):
        contracts.parse_parallel_runtime_config_v4(document)


def test_schema_v4_rejects_cross_platform_accelerator_and_ipc_pairs():
    """Accelerator, IPC transport and GL backend must form one closed combination."""

    import so101_demo.parallel_batch.contracts as contracts

    document = _v4_document()
    document["ipc_transport"] = "proc_fd_unix"
    with pytest.raises(contracts.ContractError):
        contracts.parse_parallel_runtime_config_v4(document)

    document = _v4_document()
    document["mujoco_gl"] = "egl"
    with pytest.raises(contracts.ContractError):
        contracts.parse_parallel_runtime_config_v4(document)

    document = _v4_document()
    document["accelerator"] = {"kind": "cuda", "selector": "INDEX:0"}
    with pytest.raises(contracts.ContractError):
        contracts.parse_parallel_runtime_config_v4(document)


@pytest.mark.parametrize(
    "fraction", [0, 0.0, -0.1, 1.5, 2, None, "0.8"]
)
def test_schema_v4_rejects_non_positive_or_coercible_memory_fraction(fraction):
    """The allocator cap must be a real number in (0, 1] before any MPS allocation."""

    import so101_demo.parallel_batch.contracts as contracts

    document = _v4_document()
    document["mps_process_memory_fraction"] = fraction
    with pytest.raises(contracts.ContractError):
        contracts.parse_parallel_runtime_config_v4(document)


@pytest.mark.parametrize("headroom", [0, -1, 1.5, True, "1073741824", None])
def test_schema_v4_requires_a_positive_integer_headroom(headroom):
    """The fixed headroom is a positive byte count, never a scaled or coerced budget."""

    import so101_demo.parallel_batch.contracts as contracts

    document = _v4_document()
    document["start_guard"]["mps_minimum_headroom_bytes"] = headroom
    with pytest.raises(contracts.ContractError):
        contracts.parse_parallel_runtime_config_v4(document)


def test_schema_v4_document_is_closed_against_unknown_fields(tmp_path):
    """Unknown top-level, accelerator, execution or guard fields all fail closed."""

    import so101_demo.parallel_batch.contracts as contracts

    for mutate, expected in (
        (lambda d: d.update({"deployment": {"approved_profile_path": None}}),
         "UNKNOWN_CONFIG_FIELD"),
        (lambda d: d["accelerator"].update({"device_index": 0}), "UNKNOWN_ACCELERATOR_FIELD"),
        (lambda d: d["execution"].update({"cpu_budget": 4}), "UNKNOWN_EXECUTION_FIELD"),
        (lambda d: d["start_guard"].update({"mps_headroom_gib": 1}),
         "UNKNOWN_START_GUARD_FIELD"),
    ):
        document = _v4_document()
        mutate(document)
        path = tmp_path / "v4-drift.yaml"
        path.write_text(yaml.safe_dump(document))
        with pytest.raises(contracts.ContractError, match=expected):
            contracts.load_parallel_runtime_config_v4(path)


def test_schema_v4_auto_transport_resolves_per_platform():
    """`auto` resolves to the current platform's closed default and never to TCP."""

    import so101_demo.parallel_batch.contracts as contracts
    import sys

    document = _v4_document()
    document["ipc_transport"] = "auto"
    if sys.platform == "darwin":
        document["accelerator"] = {"kind": "mps", "selector": "default"}
        document["requested_device"] = "mps"
        document["mujoco_gl"] = "cgl"
        config = contracts.parse_parallel_runtime_config_v4(document)
        assert config.ipc_transport is contracts.IpcTransport.DARWIN_PRIVATE_PATH_UNIX
    else:
        document["accelerator"] = {"kind": "cuda", "selector": "INDEX:0"}
        document["requested_device"] = "cuda"
        document["mujoco_gl"] = "egl"
        document["mps_process_memory_fraction"] = None
        document["start_guard"].pop("mps_minimum_headroom_bytes")
        config = contracts.parse_parallel_runtime_config_v4(document)
        assert config.ipc_transport is contracts.IpcTransport.PROC_FD_UNIX


def test_schema_v4_manifest_records_resolved_platform_values():
    """A resolved manifest must never report `auto`; it records the real platform choice."""

    import so101_demo.parallel_batch.contracts as contracts

    config = contracts.load_parallel_runtime_config_v4(V4_CONFIG_PATH)
    manifest = config.resolved_manifest()
    assert manifest["accelerator"] == "mps"
    assert manifest["ipc_transport"] == "darwin_private_path_unix"
    assert manifest["mujoco_gl"] == "cgl"
    assert manifest["worker_count"] == 2
    assert manifest["mps_minimum_headroom_bytes"] == 1 << 30
    assert "auto" not in set(manifest.values())


def test_schema_v4_keeps_the_v3_runtime_values_frozen():
    """v4 reuses the frozen functional timing/frame values instead of redefining them."""

    import so101_demo.parallel_batch.contracts as contracts

    config = contracts.load_parallel_runtime_config_v4(V4_CONFIG_PATH)
    assert "ros_domain_ids" not in contracts.FROZEN_RUNTIME_VALUES_V4, (
        "ros_domain_ids is a per-platform isolation choice, not a frozen runtime value"
    )
    for name, expected in contracts.FROZEN_RUNTIME_VALUES_V4.items():
        if name == "accelerator_kind":
            assert str(config.accelerator.kind) == expected, name
            continue
        if name == "accelerator_selector":
            assert config.accelerator.resolved_selector == expected, name
            continue
        assert getattr(config, name) == expected, name
    # The functional timing/frame values v4 does not redefine must still match v3 exactly.
    # The platform selection itself (`requested_device`, `allow_cpu_fallback`) may differ.
    shared = ((set(contracts.FROZEN_RUNTIME_VALUES_V4)
               & set(contracts._FROZEN_RUNTIME_VALUES_V3))
              - {"schema_version", "requested_device", "allow_cpu_fallback"})
    assert len(shared) >= 30
    for name in shared:
        assert (contracts.FROZEN_RUNTIME_VALUES_V4[name]
                == contracts._FROZEN_RUNTIME_VALUES_V3[name]), name


def test_runtime_config_loader_selects_v4_parser():
    """The any-schema loader must dispatch v4 to the v4 parser and keep v3 intact."""

    import so101_demo.parallel_batch.contracts as contracts

    loaded = contracts.load_runtime_config_any_schema(V4_CONFIG_PATH)
    assert isinstance(loaded, contracts.ParallelRuntimeConfigV4)
    assert isinstance(contracts.load_runtime_config_any_schema(V3_CONFIG_PATH),
                      contracts.ParallelRuntimeConfigV3)


def test_require_v4_execution_refuses_other_versions():
    """Execution admission is version-exact: v4 runs only against a v4 config."""

    import so101_demo.parallel_batch.contracts as contracts

    contracts.require_v4_execution(4, 4)
    for request_version, config_version in ((3, 3), (4, 3), (3, 4), (2, 2), (True, 4)):
        with pytest.raises(contracts.ContractError, match="CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"):
            contracts.require_v4_execution(request_version, config_version)


def test_schema_v4_declares_the_independent_snapshot_limit():
    """The snapshot ceiling is its own closed field, separate from the control-frame cap."""

    import so101_demo.parallel_batch.contracts as contracts

    config = contracts.load_parallel_runtime_config_v4(V4_CONFIG_PATH)
    assert config.max_input_snapshot_bytes == 64 * 1024 * 1024
    assert config.max_input_snapshot_bytes != config.broker_max_frame_bytes
    assert config.resolved_manifest()["max_input_snapshot_bytes"] == 64 * 1024 * 1024

    for bad in (0, -1, 1.5, True, "67108864"):
        document = _v4_document()
        document["max_input_snapshot_bytes"] = bad
        with pytest.raises(contracts.ContractError):
            contracts.parse_parallel_runtime_config_v4(document)

    missing = _v4_document()
    missing.pop("max_input_snapshot_bytes")
    with pytest.raises(contracts.ContractError, match="MISSING_CONFIG_FIELD"):
        contracts.parse_parallel_runtime_config_v4(missing)


def test_frozen_model_digests_match_the_published_hub_artifacts():
    """The frozen digests must name the artifacts that are actually published.

    Both bundles are published under `zjumty/` on the Hugging Face Hub. The YOLO weights were
    always the published file; the Grounded SAM manifest digest had drifted from the published
    bundle (`b55bb601…`, which the benchmark report calls the frozen production candidate and
    which pairs with threshold-lock `b02e3be2…`) to the earlier `0486be2f…`. This pins both to the
    published values so the next drift fails here instead of at a campaign start.
    """

    import so101_demo.parallel_batch.contracts as contracts

    assert contracts._FROZEN_YOLO_WEIGHTS_SHA256 == (
        "f281d25258493e2c7c220dd1d84a7ca4f0501adf99ed4a921a065d74ace40781"
    )
    assert contracts._FROZEN_GROUNDED_SAM_MANIFEST_SHA256 == (
        "b55bb601d311407df8f9f25d9da18649f6bd78ac1299148bde0d07f7cfdfed05"
    )
    # Both runtime schemas must expose the same pair, so a platform cannot freeze its own.
    for schema in (contracts.ParallelRuntimeConfigV3, contracts.ParallelRuntimeConfigV4):
        assert schema.FROZEN_YOLO_WEIGHTS_SHA256 == contracts._FROZEN_YOLO_WEIGHTS_SHA256
        assert (schema.FROZEN_GROUNDED_SAM_MANIFEST_SHA256
                == contracts._FROZEN_GROUNDED_SAM_MANIFEST_SHA256)


def test_the_benchmark_and_training_configs_carry_the_same_frozen_digests():
    """Every config that names a model digest names the same one as the code."""

    from pathlib import Path as _Path

    import so101_demo.parallel_batch.contracts as contracts

    package = _Path(__file__).resolve().parents[1]
    benchmark = (package / "config/perception_benchmark/benchmark.yaml").read_text()
    assert contracts._FROZEN_YOLO_WEIGHTS_SHA256 in benchmark
    assert contracts._FROZEN_GROUNDED_SAM_MANIFEST_SHA256 in benchmark
    for name in ("grounding_dino_training.yaml",
                 "grounding_dino_domain_retention_training.yaml",
                 "grounding_dino_domain_retention_last_stage_training.yaml"):
        text = (package / "config/perception" / name).read_text()
        assert contracts._FROZEN_GROUNDED_SAM_MANIFEST_SHA256 in text, name


def test_the_retired_grounded_sam_manifest_digest_is_not_used_anywhere():
    """The superseded digest must not linger in any shipped config or constant."""

    from pathlib import Path as _Path

    retired = "0486be2fca63736d847ffd5566bd0b59db87da829e25623412bbbdf187df1775"
    package = _Path(__file__).resolve().parents[1]
    for pattern in ("config/**/*.yaml", "config/**/*.json"):
        for path in package.glob(pattern):
            assert retired not in path.read_text(), path


# --------------------------------------------------------------------------------------
# Versions 5 and 6: the two closed macOS W1 profiles
#
# The support matrix is fixed by the design: W2 first-pass is v4, W1 full-restart retry is
# v5, W1 first-pass is v6. Each document admits exactly one combination, the routing key is
# `(schema_version, execution_profile, batch_kind, worker_count)`, and everything else is
# refused with a typed error before any spawn.
# --------------------------------------------------------------------------------------

V5_CONFIG_PATH = PACKAGE / "config/mujoco/parallel_batch_v5_macos_mps_w1_retry.yaml"
V6_CONFIG_PATH = PACKAGE / "config/mujoco/parallel_batch_v6_macos_mps_w1_first_pass.yaml"
V4_CONFIG_SHA256 = "2f9d7a87fe57a0440cdfd139c2ac42b7af86002edfcc2ed2ef3077568dc6b06b"


def _v5_document() -> dict:
    return yaml.safe_load(V5_CONFIG_PATH.read_text())


def _v6_document() -> dict:
    return yaml.safe_load(V6_CONFIG_PATH.read_text())


def test_the_frozen_v4_document_is_unchanged_by_the_w1_profiles():
    """v5/v6 are new files: the v4 document's bytes are frozen, not rewritten."""

    assert hashlib.sha256(V4_CONFIG_PATH.read_bytes()).hexdigest() == V4_CONFIG_SHA256
    config = contracts_module().load_parallel_runtime_config_v4(V4_CONFIG_PATH)
    assert config.worker_count == 2
    assert config.ros_domain_ids == (181, 182)


def contracts_module():
    import so101_demo.parallel_batch.contracts as contracts

    return contracts


def test_schema_v5_resolves_the_single_w1_retry_profile():
    """v5 admits W1 `FULL_RESTART_RETRY` and nothing else."""

    contracts = contracts_module()

    config = contracts.load_parallel_runtime_config_v5(V5_CONFIG_PATH)
    assert isinstance(config, contracts.ParallelRuntimeConfigV5)
    assert config.schema_version == 5
    assert config.worker_count == 1
    assert config.ros_domain_ids == (181,)
    assert str(config.execution_profile) == "MPS_W1_FULL_RESTART_RETRY"
    assert str(config.batch_kind) == "FULL_RESTART_RETRY"
    assert config.accelerator.kind is contracts.AcceleratorKind.MPS
    assert config.accelerator.resolved_selector == "default"
    assert config.requested_device == "mps"
    assert config.allow_cpu_fallback is False
    assert config.ipc_transport is contracts.IpcTransport.DARWIN_PRIVATE_PATH_UNIX
    assert config.mujoco_gl == "cgl"
    assert config.mps_process_memory_fraction == 0.8
    assert config.mps_minimum_headroom_bytes == 1 << 30
    assert config.resolved_manifest()["schema_version"] == 5
    assert config.resolved_manifest()["worker_count"] == 1


def test_schema_v6_resolves_the_single_w1_first_pass_profile():
    """v6 admits W1 `FIRST_PASS` and nothing else."""

    contracts = contracts_module()

    config = contracts.load_parallel_runtime_config_v6(V6_CONFIG_PATH)
    assert isinstance(config, contracts.ParallelRuntimeConfigV6)
    assert config.schema_version == 6
    assert config.worker_count == 1
    assert config.ros_domain_ids == (181,)
    assert str(config.execution_profile) == "MPS_W1_FIRST_PASS"
    assert str(config.batch_kind) == "FIRST_PASS"
    assert config.mps_minimum_headroom_bytes == 1 << 30
    assert config.resolved_manifest()["schema_version"] == 6
    assert config.resolved_manifest()["worker_count"] == 1


@pytest.mark.parametrize("version", [5, 6])
@pytest.mark.parametrize("worker_count", [0, 2, 3, 4, 6, 8])
def test_the_w1_profiles_are_exactly_one_worker(version, worker_count):
    """Any other count is a different platform claim these documents do not make."""

    contracts = contracts_module()

    document = _v5_document() if version == 5 else _v6_document()
    document["worker_count"] = worker_count
    with pytest.raises(contracts.ContractError, match="PLATFORM_WORKER_COUNT_UNSUPPORTED"):
        (contracts.parse_parallel_runtime_config_v5 if version == 5
         else contracts.parse_parallel_runtime_config_v6)(document)


@pytest.mark.parametrize("version", [5, 6])
@pytest.mark.parametrize(
    "key, value",
    [
        ("requested_device", "cpu"),
        ("requested_device", "cuda"),
        ("allow_cpu_fallback", True),
        ("ipc_transport", "proc_fd_unix"),
        ("ipc_transport", "auto_tcp"),
        ("mujoco_gl", "egl"),
        ("mujoco_gl", "osmesa"),
        ("mps_process_memory_fraction", None),
    ],
)
def test_the_w1_profiles_refuse_cpu_fallback_and_linux_transport(version, key, value):
    """No CPU fallback, no CUDA device and no Linux transport on a W1 document."""

    contracts = contracts_module()

    document = _v5_document() if version == 5 else _v6_document()
    document[key] = value
    parser = (contracts.parse_parallel_runtime_config_v5 if version == 5
              else contracts.parse_parallel_runtime_config_v6)
    with pytest.raises(contracts.ContractError):
        parser(document)


@pytest.mark.parametrize("version", [5, 6])
def test_the_w1_profiles_refuse_a_cuda_accelerator(version):
    """The MPS combination is the only one either W1 profile admits."""

    contracts = contracts_module()

    document = _v5_document() if version == 5 else _v6_document()
    document["accelerator"] = {"kind": "cuda", "selector": "INDEX:0"}
    document["requested_device"] = "cuda"
    document["ipc_transport"] = "proc_fd_unix"
    document["mujoco_gl"] = "egl"
    document["mps_process_memory_fraction"] = None
    parser = (contracts.parse_parallel_runtime_config_v5 if version == 5
              else contracts.parse_parallel_runtime_config_v6)
    with pytest.raises(contracts.ContractError, match="PLATFORM_COMBINATION_UNSUPPORTED"):
        parser(document)


@pytest.mark.parametrize("version", [5, 6])
def test_the_w1_profiles_are_closed_against_unknown_fields(version, tmp_path):
    """An unknown top-level, execution or guard key is refused, including a profile key.

    The profile is a property of the schema, not a document field: a file that tries to name
    its own profile must not parse.
    """

    contracts = contracts_module()

    base = _v5_document() if version == 5 else _v6_document()
    for mutate, expected in (
        (lambda d: d.update({"execution_profile": "MPS_W1_FIRST_PASS"}), "UNKNOWN_CONFIG_FIELD"),
        (lambda d: d.update({"worker_profile": "MPS_W1_FIRST_PASS"}), "UNKNOWN_CONFIG_FIELD"),
        (lambda d: d["execution"].update({"worker_count": 1}), "UNKNOWN_EXECUTION_FIELD"),
        (lambda d: d["accelerator"].update({"device_index": 0}), "UNKNOWN_ACCELERATOR_FIELD"),
        (lambda d: d["start_guard"].update({"mps_headroom_gib": 1}),
         "UNKNOWN_START_GUARD_FIELD"),
    ):
        document = dict(base)
        document["execution"] = dict(base["execution"])
        document["accelerator"] = dict(base["accelerator"])
        document["start_guard"] = dict(base["start_guard"])
        mutate(document)
        path = tmp_path / f"v{version}-drift.yaml"
        path.write_text(yaml.safe_dump(document))
        loader = (contracts.load_parallel_runtime_config_v5 if version == 5
                  else contracts.load_parallel_runtime_config_v6)
        with pytest.raises(contracts.ContractError, match=expected):
            loader(path)


def test_the_w1_profiles_share_every_closed_field_set_with_v4():
    """v5/v6 add no field and remove none: the shape is the v4 shape at W1."""

    contracts = contracts_module()
    from dataclasses import fields

    for schema in (contracts.ParallelRuntimeConfigV5, contracts.ParallelRuntimeConfigV6):
        assert {item.name for item in fields(schema)} == {
            item.name for item in fields(contracts.ParallelRuntimeConfigV4)}
    assert contracts.V5_CONFIG_FIELDS == contracts.V4_CONFIG_FIELDS
    assert contracts.V6_CONFIG_FIELDS == contracts.V4_CONFIG_FIELDS
    assert contracts.EXECUTION_V5_FIELDS == contracts.EXECUTION_V4_FIELDS
    assert contracts.EXECUTION_V6_FIELDS == contracts.EXECUTION_V4_FIELDS
    assert contracts.START_GUARD_V5_FIELDS == contracts.START_GUARD_V4_FIELDS
    assert contracts.START_GUARD_V6_FIELDS == contracts.START_GUARD_V4_FIELDS


def test_the_w1_profiles_invent_no_budget_or_qualification_field():
    """A W1 profile is a routing fact, not a capacity or qualification claim."""

    contracts = contracts_module()
    from dataclasses import fields

    forbidden = ("budget", "qualification", "promotion", "forecast", "profile", "adaptive")
    v4_fields = {item.name for item in fields(contracts.ParallelRuntimeConfigV4)}
    for schema in (contracts.ParallelRuntimeConfigV5, contracts.ParallelRuntimeConfigV6):
        names = {item.name for item in fields(schema)}
        assert names == v4_fields, "a W1 profile adds no field, so it can invent no claim"
        for name in names:
            assert not any(token in name for token in forbidden), name


def test_require_v5_and_v6_execution_are_version_exact():
    """Execution admission stays version-exact for the new profiles too."""

    contracts = contracts_module()

    contracts.require_v5_execution(5, 5)
    contracts.require_v6_execution(6, 6)
    for require, request_version, config_version in (
        (contracts.require_v5_execution, 5, 4),
        (contracts.require_v5_execution, 4, 5),
        (contracts.require_v5_execution, 6, 6),
        (contracts.require_v6_execution, 6, 5),
        (contracts.require_v6_execution, 5, 6),
        (contracts.require_v6_execution, True, 6),
    ):
        with pytest.raises(contracts.ContractError,
                           match="CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"):
            require(request_version, config_version)


@pytest.mark.parametrize(
    "route, expected",
    [
        # the three admitted combinations, one line each
        ((4, "MPS_W2_FIRST_PASS", "FIRST_PASS", 2), None),
        ((5, "MPS_W1_FULL_RESTART_RETRY", "FULL_RESTART_RETRY", 1), None),
        ((6, "MPS_W1_FIRST_PASS", "FIRST_PASS", 1), None),
        # a v4 document claiming W1
        ((4, "MPS_W1_FIRST_PASS", "FIRST_PASS", 1), "PROFILE_SCHEMA_MISMATCH"),
        ((4, "MPS_W1_FULL_RESTART_RETRY", "FULL_RESTART_RETRY", 1), "PROFILE_SCHEMA_MISMATCH"),
        # a v5 document claiming first-pass
        ((5, "MPS_W1_FIRST_PASS", "FIRST_PASS", 1), "PROFILE_SCHEMA_MISMATCH"),
        # a v6 document claiming retry
        ((6, "MPS_W1_FULL_RESTART_RETRY", "FULL_RESTART_RETRY", 1), "PROFILE_SCHEMA_MISMATCH"),
        # a profile whose batch kind is not the one it admits
        ((5, "MPS_W1_FULL_RESTART_RETRY", "FIRST_PASS", 1), "PROFILE_BATCH_KIND_MISMATCH"),
        ((6, "MPS_W1_FIRST_PASS", "FULL_RESTART_RETRY", 1), "PROFILE_BATCH_KIND_MISMATCH"),
        ((4, "MPS_W2_FIRST_PASS", "FULL_RESTART_RETRY", 2), "PROFILE_BATCH_KIND_MISMATCH"),
        # adaptive is not a macOS capability at all
        ((5, "MPS_W1_FULL_RESTART_RETRY", "ADAPTIVE_POOL", 1), "ADAPTIVE_UNSUPPORTED_ON_MACOS"),
        ((4, "MPS_W2_FIRST_PASS", "ADAPTIVE_POOL", 2), "ADAPTIVE_UNSUPPORTED_ON_MACOS"),
        # N>2 and the unsupported W1 counts
        ((4, "MPS_W2_FIRST_PASS", "FIRST_PASS", 4), "PLATFORM_WORKER_COUNT_UNSUPPORTED"),
        ((5, "MPS_W1_FULL_RESTART_RETRY", "FULL_RESTART_RETRY", 2),
         "PLATFORM_WORKER_COUNT_UNSUPPORTED"),
        ((6, "MPS_W1_FIRST_PASS", "FIRST_PASS", 8), "PLATFORM_WORKER_COUNT_UNSUPPORTED"),
        # an unknown profile
        ((6, "MPS_W4_FIRST_PASS", "FIRST_PASS", 1), "EXECUTION_PROFILE_UNKNOWN"),
        # a schema no profile is approved for
        ((3, "MPS_W2_FIRST_PASS", "FIRST_PASS", 2), "CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"),
        ((7, "MPS_W2_FIRST_PASS", "FIRST_PASS", 2), "CONFIG_VERSION_UNSUPPORTED_FOR_EXECUTION"),
    ],
)
def test_the_execution_routing_table_admits_exactly_three_combinations(route, expected):
    """One accepted line per approved combination; every other key is refused by name."""

    contracts = contracts_module()

    schema_version, execution_profile, batch_kind, worker_count = route
    if expected is None:
        resolved = contracts.resolve_execution_route(
            schema_version=schema_version, execution_profile=execution_profile,
            batch_kind=batch_kind, worker_count=worker_count)
        assert resolved.schema_version == schema_version
        assert resolved.worker_count == worker_count
        assert str(resolved.batch_kind) == batch_kind
        return
    with pytest.raises(contracts.ContractError, match=expected):
        contracts.resolve_execution_route(
            schema_version=schema_version, execution_profile=execution_profile,
            batch_kind=batch_kind, worker_count=worker_count)


def test_a_profile_is_never_inferred_from_the_selected_point_count():
    """`None` is the shape an inference would produce, and it is refused by name."""

    contracts = contracts_module()

    with pytest.raises(contracts.ContractError, match="PROFILE_FROM_SELECTED_POINTS"):
        contracts.resolve_execution_route(
            schema_version=6, execution_profile=None, batch_kind="FIRST_PASS", worker_count=1)
    with pytest.raises(contracts.ContractError, match="PROFILE_FROM_SELECTED_POINTS"):
        contracts.resolve_execution_route(
            schema_version=4, execution_profile="MPS_W2_FIRST_PASS", batch_kind="FIRST_PASS",
            worker_count=None)
    with pytest.raises(contracts.ContractError, match="EXECUTION_PROFILE_UNKNOWN"):
        contracts.resolve_execution_route(
            schema_version=6, execution_profile="W1", batch_kind="FIRST_PASS", worker_count=1)


def test_the_routing_table_names_the_three_approved_profiles_only():
    """The table is the support matrix: three rows, no N>2 and no adaptive row."""

    contracts = contracts_module()

    assert len(contracts.APPROVED_EXECUTION_ROUTES) == 3
    assert {(route.schema_version, str(route.execution_profile))
            for route in contracts.APPROVED_EXECUTION_ROUTES} == {
        (4, "MPS_W2_FIRST_PASS"),
        (5, "MPS_W1_FULL_RESTART_RETRY"),
        (6, "MPS_W1_FIRST_PASS"),
    }
    assert {route.worker_count for route in contracts.APPROVED_EXECUTION_ROUTES} == {1, 2}
    assert "ADAPTIVE_POOL" not in {str(route.batch_kind)
                                   for route in contracts.APPROVED_EXECUTION_ROUTES}


def test_the_w1_runtime_values_reuse_the_v4_freeze():
    """v5/v6 restate the v4 functional freeze; only the schema and the count change."""

    contracts = contracts_module()

    for values, version in ((contracts.FROZEN_RUNTIME_VALUES_V5, 5),
                            (contracts.FROZEN_RUNTIME_VALUES_V6, 6)):
        shared = set(values) & set(contracts.FROZEN_RUNTIME_VALUES_V4)
        assert len(shared) >= 30
        for name in shared - {"schema_version", "worker_count"}:
            assert values[name] == contracts.FROZEN_RUNTIME_VALUES_V4[name], name
        assert values["schema_version"] == version
        assert values["worker_count"] == 1
    for config in (contracts.load_parallel_runtime_config_v5(V5_CONFIG_PATH),
                   contracts.load_parallel_runtime_config_v6(V6_CONFIG_PATH)):
        for name, expected in (contracts.FROZEN_RUNTIME_VALUES_V5.items()
                               if config.schema_version == 5
                               else contracts.FROZEN_RUNTIME_VALUES_V6.items()):
            assert getattr(config, name) == expected, name


def test_the_any_schema_loader_selects_the_w1_profiles():
    """The history-side loader is not left behind by the new schemas."""

    contracts = contracts_module()

    assert isinstance(contracts.load_runtime_config_any_schema(V5_CONFIG_PATH),
                      contracts.ParallelRuntimeConfigV5)
    assert isinstance(contracts.load_runtime_config_any_schema(V6_CONFIG_PATH),
                      contracts.ParallelRuntimeConfigV6)
