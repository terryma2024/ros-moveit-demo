from so101_demo.core.domain import (
    ExecutionRunStatus,
    FailureCategory,
    QualificationStatus,
)
from so101_demo.runtime.result_manifest import classify_run


def test_valid_policy_failure_is_not_invalid() -> None:
    result = classify_run(
        backend="gazebo",
        session_id="session-1",
        reset_epoch=2,
        policy_sha256="a" * 64,
        bundle_sha256="b" * 64,
        error_code="PATH_TOLERANCE_VIOLATED",
        evidence_valid=True,
        first_failed_phase="MOVE_ABOVE_OBJECT",
        failure_category=FailureCategory.EXECUTION,
    )
    assert result.run_status is ExecutionRunStatus.FAILED
    assert result.qualification_status is QualificationStatus.NOT_QUALIFIED


def test_contaminated_evidence_is_invalid() -> None:
    result = classify_run(
        backend="mujoco",
        session_id="session-1",
        reset_epoch=2,
        policy_sha256="a" * 64,
        bundle_sha256="b" * 64,
        error_code="EVIDENCE_GAP",
        evidence_valid=False,
    )
    assert result.run_status is ExecutionRunStatus.INVALID
    assert result.qualification_status is QualificationStatus.NOT_QUALIFIED


def test_capability_rejection_is_distinct_from_invalid() -> None:
    result = classify_run(
        backend="real_stub",
        session_id="none",
        reset_epoch=0,
        policy_sha256="a" * 64,
        bundle_sha256="b" * 64,
        error_code="REAL_HARDWARE_NOT_CONFIGURED",
        evidence_valid=True,
        rejected=True,
    )
    assert result.run_status is ExecutionRunStatus.REJECTED
