import argparse
import json
from pathlib import Path

from so101_demo.application.backend_execute import ExecuteBoundary, classify_execute_boundary
from so101_demo.backends.gazebo.execute import _complete_runtime_options
from so101_demo.core.domain import (
    ActionResult,
    ActionStatus,
    ExecutionRunStatus,
    Failure,
    FailureCategory,
    QualificationStatus,
)
from so101_demo.runtime.result_manifest import write_run_result


def test_teleop_request_derives_result_from_checkpoint(tmp_path) -> None:
    policy = tmp_path / "policy.yaml"
    policy.write_text("policy: test\n")
    checkpoint = tmp_path / "session" / "checkpoint.json"
    options = argparse.Namespace(
        session_id="gazebo-session",
        checkpoint=checkpoint,
        result=None,
        policy=policy,
        source_commit="c" * 40,
        installed_prefix="/opt/so101/fusion-final",
        policy_sha256="a" * 64,
        bundle_sha256="b" * 64,
    )

    _complete_runtime_options(options)

    assert options.result == checkpoint.with_name("gazebo-run-result.json")
    assert options.policy == policy
    assert options.source_commit == "c" * 40


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


def test_execute_source_has_no_synthetic_incomplete_failure() -> None:
    source = Path("src/so101_demo_py/src/backends/gazebo/execute.py").read_text(
        encoding="utf-8"
    )
    assert "GAZEBO_EXECUTE_INCOMPLETE" not in source
