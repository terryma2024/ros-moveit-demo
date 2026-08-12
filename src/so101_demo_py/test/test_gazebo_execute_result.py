import json

from so101_demo.application.backend_execute import ExecuteBoundary, classify_execute_boundary
from so101_demo.core.domain import (
    ActionResult,
    ActionStatus,
    ExecutionRunStatus,
    Failure,
    FailureCategory,
    QualificationStatus,
)
from so101_demo.runtime.result_manifest import write_run_result


def test_policy_failure_reports_real_boundary(tmp_path) -> None:
    boundary = ExecuteBoundary(
        phase="MOVE_ABOVE_OBJECT",
        action=ActionResult(
            ActionStatus.FAILED,
            Failure(
                FailureCategory.EXECUTION,
                "PATH_TOLERANCE_VIOLATED",
                "arm controller rejected the physical trajectory",
            ),
        ),
        evidence_valid=True,
        evidence_refs=("initial-world.json", "arm-action.json"),
    )

    result = classify_execute_boundary(
        boundary,
        backend="gazebo",
        session_id="gazebo-session",
        reset_epoch=0,
        source_commit="c" * 40,
        installed_prefix="/opt/so101/fusion-final",
        policy_sha256="a" * 64,
        bundle_sha256="b" * 64,
    )

    assert result.run_status is ExecutionRunStatus.FAILED
    assert result.qualification_status is QualificationStatus.NOT_QUALIFIED
    assert result.first_failed_phase == "MOVE_ABOVE_OBJECT"
    assert result.error_code == "PATH_TOLERANCE_VIOLATED"
    path = write_run_result(tmp_path / "result.json", result)
    document = json.loads(path.read_text())
    assert document["run_status"] == "FAILED"
    assert document["source_commit"] == "c" * 40
    assert document["installed_prefix"] == "/opt/so101/fusion-final"
    assert document["evidence_refs"] == ["initial-world.json", "arm-action.json"]


def test_successful_action_is_not_qualified_for_gazebo() -> None:
    result = classify_execute_boundary(
        ExecuteBoundary("release_retreat", ActionResult(ActionStatus.SUCCEEDED), True),
        backend="gazebo",
        session_id="gazebo-session",
        reset_epoch=0,
        source_commit="c" * 40,
        installed_prefix="/opt/so101/fusion-final",
        policy_sha256="a" * 64,
        bundle_sha256="b" * 64,
    )

    assert result.run_status is ExecutionRunStatus.SUCCEEDED
    assert result.qualification_status is QualificationStatus.NOT_QUALIFIED


def test_invalid_evidence_is_not_a_policy_failure() -> None:
    result = classify_execute_boundary(
        ExecuteBoundary(
            "MOVE_ABOVE_OBJECT",
            ActionResult(
                ActionStatus.FAILED,
                Failure(FailureCategory.EXECUTION, "PATH_TOLERANCE_VIOLATED"),
            ),
            False,
        ),
        backend="gazebo",
        session_id="gazebo-session",
        reset_epoch=0,
        source_commit="c" * 40,
        installed_prefix="/opt/so101/fusion-final",
        policy_sha256="a" * 64,
        bundle_sha256="b" * 64,
    )

    assert result.run_status is ExecutionRunStatus.INVALID


def test_skipped_is_not_a_run_status() -> None:
    assert "SKIPPED" not in {value.value for value in ExecutionRunStatus}
