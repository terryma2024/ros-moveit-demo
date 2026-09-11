import hashlib
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
    assert config.ros_domain_ids == (181, 182, 183)
    assert config.max_worker_count == 3
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
    )

    assert summary.validation_complete is True
    assert summary.validation_passed is True
    assert summary.qualification_applicable is False
    assert summary.qualification_passed is False
