"""Execution results, business outcomes, worker classification and running evidence."""

from __future__ import annotations

import hashlib
import json
import os
import time
from types import SimpleNamespace

from parallel_ros_runtime_support import _lease
import pytest

EXPECTED_FINAL_CUP_POSE_WORLD = (
    -0.08, -0.25, 0.1648, 0.0, 0.0, 0.0, 1.0,
)


def _dynamic_execute_manifest(lease, *, session_id, policy_path, status="DONE"):
    from so101_demo.core.domain import State
    from so101_demo.core.dynamic_pick import DYNAMIC_MOTION_STATES
    from so101_demo.core.workflow import SO101_WORKFLOW

    failed = status != "DONE"
    trace = [State.IDLE]
    while not failed and trace[-1] not in SO101_WORKFLOW.terminal_states:
        trace.append(SO101_WORKFLOW.transitions[trace[-1]][0])

    def physical(sequence):
        return {
            "reset_epoch": 17,
            "simulation_step": sequence * 5,
            "publisher_sequence": sequence,
            "cup_position_world_m": [-0.08, -0.25, 0.1648],
            "cup_orientation_world_xyzw": [0.0, 0.0, 0.0, 1.0],
            "cup_linear_velocity_world_m_s": [0.0, 0.0, 0.0],
            "cup_angular_velocity_world_rad_s": [0.0, 0.0, 0.0],
            "left_contact_count": 0,
            "right_contact_count": 0,
            "maximum_normal_force_n": 0.2,
            "table_contact": True,
        }

    events = []
    planning = []
    for index, state in enumerate(trace[:-1]):
        if state not in SO101_WORKFLOW.action_states:
            continue
        item = {
            "state": state.value,
            "before": physical(100 + index * 2),
            "after": physical(101 + index * 2),
        }
        if state in DYNAMIC_MOTION_STATES:
            item.update(
                terminal_joint_positions_rad=[0.0] * 5,
                terminal_joint_state_source_stamp_ns=(index + 1) * 1_000_000,
                execution_reconciliations=[],
            )
            planning.append({
                "kind": "moveit_joint_plan", "state": state.value, "accepted": True,
            })
        if state is State.VALIDATE_FINAL_PLACEMENT:
            item.update(
                expected_cup_pose_world=[-0.08, -0.25, 0.1648, 0.0, 0.0, 0.0, 1.0],
                final_xy_error_m=0.0,
                final_upright_tilt_rad=0.0,
            )
        events.append(item)
    scene = {
        "attached_object_ids": [],
        "world_primitive_counts": {"plastic_cup": 13},
    }
    document = {
        "schema": "so101-dynamic-execute", "schema_version": 1,
        "parallel_lease_identity": {
            "batch_id": lease.batch_id,
            "coordinator_epoch": lease.coordinator_epoch,
            "worker_id": lease.worker_id,
            "worker_generation": lease.worker_generation,
            "point_id": lease.point_id,
            "attempt_id": lease.attempt_id,
            "lease_generation": lease.lease_generation,
        },
        "status": "ERROR" if failed else "DONE",
        "current_state": "ERROR" if failed else "DONE",
        "failure": "MOVEIT_EXECUTION_FAILED" if failed else None,
        "simulation_session_id": session_id,
        "expected_reset_epoch": 17,
        "policy_path": str(policy_path),
        "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        "state_trace": ["IDLE", "ERROR"] if failed else [item.value for item in trace],
        "transition_count": 1 if failed else len(trace) - 1,
        "state_events": [] if failed else events,
        "planning_attempts": [] if failed else planning,
        "final_samples": [] if failed else [physical(1000)],
        "planning_scene_readback": None if failed else scene,
        "release_marker_sequence": None if failed else 900,
        "failure_evidence": ({
            "failure_boundary_state": "IDLE",
            "physical_action_proven_absent": True,
            "terminal_sample": None,
            "planning_scene_readback": None,
            "capture_errors": [],
        } if failed else None),
    }
    document.update(_teacher_general_fields(failed))
    return document


def _teacher_general_observation(position, time_s):
    return {
        "position": list(position),
        "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0},
        "simulation_time_s": time_s, "frame_id": "world", "object_id": "plastic_cup",
        "session_id": "session-1", "reset_epoch": 17,
    }


def _teacher_general_fields(failed, *, result="PASS", reasons=(), execution=None):
    """The Teacher-owned v2 fields: a clean DONE run passes; a pre-motion ERROR is a FAILED execution."""

    start = _teacher_general_observation([-0.02, -0.28, 0.165], 1.0)
    end = None if failed or result == "UNCONFIRMED" else _teacher_general_observation([-0.08, -0.25, 0.1648], 9.0)
    task = {
        "rule_version": "teacher_endpoint", "policy_sha256": "b" * 64,
        "result": "UNCONFIRMED" if failed else result, "reasons": ["END_OBSERVATION_UNCONFIRMED: x"] if failed
        else list(reasons), "measured": {},
        "start_target": {"position": [-0.02, -0.28, 0.165], "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}},
        "end_target": {"position": [-0.08, -0.25, 0.1648], "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}},
        "start_observation": start, "end_observation": end,
    }
    return {
        "teacher_execution_status": execution or ("FAILED" if failed else "COMPLETED"),
        "teacher_task_result": task,
        "teacher_start_observation": start, "teacher_end_observation": end,
        "act_data_status": "DISABLED", "process_diagnostics": [],
    }


@pytest.mark.parametrize("case", ["empty", "malformed", "wrong_identity"])
def test_exit_zero_unverifiable_dynamic_manifest_never_passes(
        tmp_path, monkeypatch, case):
    from so101_demo.parallel_batch.contracts.common import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    if case == "empty":
        manifest.write_bytes(b"")
    elif case == "malformed":
        manifest.write_bytes(b"{not-json")
    else:
        document = _dynamic_execute_manifest(
            lease, session_id="session-1", policy_path=policy
        )
        document["parallel_lease_identity"]["attempt_id"] = "stale-attempt"
        manifest.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, 0))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )

    receipt = ports.execute_result(
        lease,
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"


def test_execute_result_waits_for_configured_execution_timeout(
        tmp_path, monkeypatch):
    from so101_demo.parallel_batch.contracts.common import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    observations = iter((100.0, 200.0, 300.0, 341.0, 342.0))
    waitpid_calls = []

    monkeypatch.setattr(time, "monotonic", lambda: next(observations))
    monkeypatch.setattr(time, "sleep", lambda _duration: None)
    monkeypatch.setattr(
        os,
        "waitpid",
        lambda pid, options: (waitpid_calls.append((pid, options)) or (0, 0)),
    )
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=tmp_path, session_id="session-1"),
        catalog={},
        config=SimpleNamespace(executing_hard_timeout_s=240.0),
    )

    receipt = ports.execute_result(
        _lease(),
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert waitpid_calls == [(417, os.WNOHANG), (417, os.WNOHANG)]


@pytest.mark.parametrize(
    "manifest_status,wait_status,expected_status,expected_reason",
    [
        ("DONE", 0, "PASSED", "OK"),
        ("ERROR", 256, "FAILED", "MOVEIT_EXECUTION_FAILED"),
    ],
)
def test_exact_dynamic_manifest_maps_terminal_business_outcome(
        tmp_path, monkeypatch, manifest_status, wait_status,
        expected_status, expected_reason):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    manifest.write_text(json.dumps(_dynamic_execute_manifest(
        lease,
        session_id="session-1",
        policy_path=policy,
        status=manifest_status,
    )), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, wait_status))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )

    receipt = ports.execute_result(
        lease,
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status.value == expected_status
    assert receipt.decision.reason == expected_reason


def test_pre_motion_unreachable_manifest_is_a_failed_teacher_with_invalid_data_and_no_action(tmp_path, monkeypatch):
    """The Teacher's own terminal decision before any motion: FAILED, data INVALID for that reason, action proven absent."""
    def build(lease, policy):
        document = _dynamic_execute_manifest(lease, session_id="session-1", policy_path=policy, status="ERROR")
        document["failure"] = "DYNAMIC_TARGET_UNREACHABLE"
        return document

    receipt = _execute_with_manifest(tmp_path, monkeypatch, build, wait_status=256)

    decision = receipt.decision
    assert decision.status.value == "FAILED"
    assert decision.reason == "DYNAMIC_TARGET_UNREACHABLE"
    assert (decision.teacher_execution_status, decision.teacher_task_result) == ("FAILED", "UNCONFIRMED")
    assert (decision.act_data_status, decision.act_data_reason) == ("INVALID", "DYNAMIC_TARGET_UNREACHABLE")
    assert decision.physical_action_proven_absent is True


def test_other_pre_motion_errors_keep_their_data_side_and_do_not_prove_absence(tmp_path, monkeypatch):
    def build(lease, policy):
        return _dynamic_execute_manifest(lease, session_id="session-1", policy_path=policy, status="ERROR")

    decision = _execute_with_manifest(tmp_path, monkeypatch, build, wait_status=256).decision

    assert decision.status.value == "FAILED"
    assert (decision.act_data_status, decision.act_data_reason) == ("DISABLED", None)
    assert decision.physical_action_proven_absent is False


def test_unreachable_manifest_that_does_not_prove_the_absence_of_action_is_not_special(tmp_path, monkeypatch):
    def build(lease, policy):
        document = _dynamic_execute_manifest(lease, session_id="session-1", policy_path=policy, status="ERROR")
        document["failure"] = "DYNAMIC_TARGET_UNREACHABLE"
        document["failure_evidence"]["physical_action_proven_absent"] = False
        return document

    receipt = _execute_with_manifest(tmp_path, monkeypatch, build, wait_status=256)

    assert receipt.decision.status.value == "INDETERMINATE"
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"


@pytest.mark.parametrize(
    "failure",
    ["GRIPPER_GOAL_TIMEOUT", "GRIPPER_RESULT_TIMEOUT"],
)
def test_post_submission_error_without_controller_settlement_is_indeterminate(
        tmp_path, monkeypatch, failure):
    from so101_demo.parallel_batch.contracts.common import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest_path = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    document = _dynamic_execute_manifest(
        lease, session_id="session-1", policy_path=policy, status="ERROR"
    )
    terminal = {
        "reset_epoch": 17,
        "simulation_step": 5000,
        "publisher_sequence": 1000,
        "cup_position_world_m": [-0.08, -0.25, 0.1648],
        "cup_orientation_world_xyzw": [0.0, 0.0, 0.0, 1.0],
        "cup_linear_velocity_world_m_s": [0.0, 0.0, 0.0],
        "cup_angular_velocity_world_rad_s": [0.0, 0.0, 0.0],
        "left_contact_count": 0,
        "right_contact_count": 0,
        "maximum_normal_force_n": 0.2,
        "table_contact": True,
    }
    scene = {
        "attached_object_ids": [],
        "world_primitive_counts": {"plastic_cup": 13},
    }
    document.update(
        failure=failure,
        state_trace=["IDLE", "PREPARE_OPEN_GRIPPER", "ERROR"],
        transition_count=2,
        state_events=[{
            "state": "PREPARE_OPEN_GRIPPER",
            "before": {**terminal, "publisher_sequence": 10},
            "after": {**terminal, "publisher_sequence": 11},
            "validation_failure": failure,
        }],
        failure_evidence={
            "failure_boundary_state": "PREPARE_OPEN_GRIPPER",
            "physical_action_proven_absent": False,
            "terminal_sample": terminal,
            "planning_scene_readback": scene,
            "capture_errors": [],
        },
        # the controller never settled after the submission, so the Teacher itself reports INDETERMINATE
        teacher_execution_status="INDETERMINATE",
    )
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, 256))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )

    receipt = ports.execute_result(
        lease,
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == f"{failure}:CONTROLLER_OUTCOME_UNCONFIRMED"


def test_runtime_rejects_semantically_impossible_done_trace(tmp_path, monkeypatch):
    from so101_demo.parallel_batch.contracts.common import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest_path = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    document = _dynamic_execute_manifest(
        lease, session_id="session-1", policy_path=policy
    )
    document["state_trace"] = ["IDLE", "MOVE_ABOVE_OBJECT", "DONE"]
    document["transition_count"] = 2
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, 0))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )

    receipt = ports.execute_result(
        lease,
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"


@pytest.mark.parametrize("corruption", ["producer_target", "zero_quaternion"])
def test_runtime_rejects_untrusted_final_pose_claims(
        tmp_path, monkeypatch, corruption):
    from so101_demo.parallel_batch.contracts.common import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest_path = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    document = _dynamic_execute_manifest(
        lease, session_id="session-1", policy_path=policy
    )
    task = document["teacher_task_result"]
    if corruption == "producer_target":
        task["end_target"]["position"][:2] = [9.0, 9.0]
        task["end_observation"]["position"][:2] = [9.0, 9.0]
        document["teacher_end_observation"] = task["end_observation"]
    else:
        task["end_observation"]["orientation"] = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0}
        document["teacher_end_observation"] = task["end_observation"]
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, 0))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )

    receipt = ports.execute_result(
        lease,
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"


def _execute_with_manifest(tmp_path, monkeypatch, document_factory, *, wait_status=0):
    return _execute_with_ports(tmp_path, monkeypatch, document_factory, wait_status=wait_status)[1]


def _execute_with_ports(tmp_path, monkeypatch, document_factory, *, wait_status=0):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    manifest.write_text(json.dumps(document_factory(lease, policy)), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, wait_status))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )
    return ports, ports.execute_result(
        lease, SimpleNamespace(reset_epoch="reset-17"), SimpleNamespace(pid=417)), lease


@pytest.mark.parametrize(
    "result,reasons,expected_status",
    [
        ("PASS", [], "PASSED"),
        ("FAIL", ["FINAL_XY_OUT_OF_TOLERANCE"], "FAILED"),
        ("UNCONFIRMED", ["END_OBSERVATION_UNCONFIRMED: observation is missing"], "INDETERMINATE"),
    ],
)
def test_general_worker_classifies_the_teacher_task_result(
        tmp_path, monkeypatch, result, reasons, expected_status):
    def build(lease, policy):
        document = _dynamic_execute_manifest(lease, session_id="session-1", policy_path=policy)
        document.update(_teacher_general_fields(False, result=result, reasons=reasons))
        return document

    receipt = _execute_with_manifest(tmp_path, monkeypatch, build)

    assert receipt.decision.status.value == expected_status
    if result != "PASS":
        assert receipt.decision.reason.startswith("TEACHER_TASK_")
        assert reasons[0].split(":")[0] in receipt.decision.reason


@pytest.mark.parametrize("schema", ["so101-dynamic-mujoco-execute-v4", "so101-dynamic-mujoco-execute-v0", None])
def test_worker_rejects_unknown_manifest_versions(tmp_path, monkeypatch, schema):
    from so101_demo.parallel_batch.contracts.common import AttemptStatus

    def build(lease, policy):
        document = _dynamic_execute_manifest(lease, session_id="session-1", policy_path=policy)
        if schema is None:
            document.pop("schema")
        else:
            document["schema"] = schema
        return document

    receipt = _execute_with_manifest(tmp_path, monkeypatch, build)

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"


def test_general_worker_rejects_a_pass_whose_execution_did_not_complete(tmp_path, monkeypatch):
    from so101_demo.parallel_batch.contracts.common import AttemptStatus

    def build(lease, policy):
        document = _dynamic_execute_manifest(lease, session_id="session-1", policy_path=policy, status="ERROR")
        document["teacher_task_result"]["result"] = "PASS"
        return document

    receipt = _execute_with_manifest(tmp_path, monkeypatch, build, wait_status=256)

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"


def test_a_done_run_with_audit_only_process_diagnostics_still_passes(tmp_path, monkeypatch):
    def build(lease, policy):
        document = _dynamic_execute_manifest(lease, session_id="session-1", policy_path=policy)
        document["process_diagnostics"] = [{"code": "DYNAMIC_EARLY_TABLE_CONTACT", "state": "LIFT",
                                            "audit_only": True, "count": 3}]
        return document

    receipt = _execute_with_manifest(tmp_path, monkeypatch, build)

    assert receipt.decision.status.value == "PASSED"
    assert receipt.decision.reason == "OK"


RC_DATA_INVALID = 3 << 8   # the retired "Teacher COMPLETED, data INVALID" code: no process returns it any more


def _general_with(data_status, *, result="PASS", reasons=(), status="DONE"):
    def build(lease, policy):
        document = _dynamic_execute_manifest(lease, session_id="session-1", policy_path=policy, status=status)
        document.update(_teacher_general_fields(status != "DONE", result=result, reasons=reasons))
        document["act_data_status"] = data_status
        return document
    return build


def test_a_done_run_with_the_retired_data_invalid_exit_code_is_unverifiable(tmp_path, monkeypatch):
    """REPLACED_BY the Recorder verdict: exit 3 used to say 'Teacher COMPLETED, data INVALID'; the Teacher has no data
    side now, so a DONE manifest ending with anything but exit 0 is an inconsistent receipt and claims nothing."""
    from so101_demo.parallel_batch.contracts.common import AttemptStatus
    ports, receipt, lease = _execute_with_ports(tmp_path, monkeypatch, _general_with("DISABLED"), wait_status=RC_DATA_INVALID)
    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"
    assert receipt.decision.act_data_status == "INVALID"


def test_done_with_exit_0_carries_the_teacher_fields_and_the_constant_disabled_data_status(tmp_path, monkeypatch):
    ports, receipt, lease = _execute_with_ports(tmp_path, monkeypatch, _general_with("DISABLED"))

    assert receipt.decision.status.value == "PASSED"
    assert (receipt.decision.teacher_execution_status, receipt.decision.teacher_task_result) == ("COMPLETED", "PASS")
    assert receipt.decision.act_data_status == "DISABLED", "the Recorder's verdict replaces it afterwards"
    assert not hasattr(ports, "act_data_status"), "the per-attempt side table is replaced by the decision fields"


def test_a_teacher_task_fail_with_exit_0_is_a_fail_with_disabled_data(tmp_path, monkeypatch):
    ports, receipt, lease = _execute_with_ports(
        tmp_path, monkeypatch, _general_with("DISABLED", result="FAIL", reasons=["FINAL_XY_OUT_OF_TOLERANCE"]))

    assert receipt.decision.status.value == "FAILED"
    assert receipt.decision.reason == "TEACHER_TASK_FAIL:FINAL_XY_OUT_OF_TOLERANCE"
    assert (receipt.decision.teacher_execution_status, receipt.decision.teacher_task_result) == ("COMPLETED", "FAIL")


@pytest.mark.parametrize(
    "case",
    ["exit3_disabled", "exit3_retired_schema", "exit1_done"],
)
def test_inconsistent_exit_code_and_manifest_never_classify(tmp_path, monkeypatch, case):
    from so101_demo.parallel_batch.contracts.common import AttemptStatus

    def build(lease, policy):
        document = _general_with("DISABLED")(lease, policy)
        if case == "exit3_retired_schema":
            document["schema"] = "so101-dynamic-mujoco-execute-v1"      # the retired manifest: no longer read at all
            for key in ("teacher_execution_status", "teacher_task_result", "teacher_start_observation",
                        "teacher_end_observation", "act_data_status", "process_diagnostics"):
                document.pop(key)
        return document

    wait_status = {"exit1_done": 1 << 8}.get(case, RC_DATA_INVALID)
    ports, receipt, lease = _execute_with_ports(tmp_path, monkeypatch, build, wait_status=wait_status)

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"
    # an unverifiable receipt claims nothing positive: INDETERMINATE/UNCONFIRMED with the data marked INVALID
    assert (receipt.decision.teacher_execution_status, receipt.decision.teacher_task_result) == (
        "INDETERMINATE", "UNCONFIRMED")
    assert receipt.decision.act_data_status == "INVALID"


def _frozen_policy_receipt(tmp_path, monkeypatch, *, frozen_bytes):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest = (worker_root / "attempts" / lease.point_id / lease.attempt_id
                / "working" / "dynamic" / "dynamic-execute-manifest.json")
    manifest.parent.mkdir(parents=True)
    installed = tmp_path / "installed" / "mujoco.yaml"
    frozen = tmp_path / "frozen-snapshot" / "mujoco.yaml"
    for path, data in ((installed, b"policy\n"), (frozen, frozen_bytes)):
        path.parent.mkdir()
        path.write_bytes(data)
    document = _dynamic_execute_manifest(lease, session_id="session-1", policy_path=frozen)
    manifest.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, 0))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"), catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (str(installed), hashlib.sha256(installed.read_bytes()).hexdigest()),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        })
    return ports.execute_result(lease, SimpleNamespace(reset_epoch="reset-17"), SimpleNamespace(pid=417))


def test_c4_a_frozen_snapshot_policy_with_the_same_bytes_is_the_trusted_policy(tmp_path, monkeypatch):
    receipt = _frozen_policy_receipt(tmp_path, monkeypatch, frozen_bytes=b"policy\n")
    assert receipt.decision.reason != "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"


def test_c4_a_policy_with_other_bytes_is_still_refused(tmp_path, monkeypatch):
    receipt = _frozen_policy_receipt(tmp_path, monkeypatch, frozen_bytes=b"other\n")
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"


def _ports_with_observer(monkeypatch, observer_class, *, timeout_s=0.05):
    import rclpy

    from so101_demo.backends.mujoco import observer as observer_module
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    monkeypatch.setattr(observer_module, "MujocoWorldObserver", observer_class)
    monkeypatch.setattr(rclpy, "spin_once", lambda node, timeout_sec=0.0: None)
    ports = ParallelRosRuntimePorts(SimpleNamespace(session_id="session-1"), catalog={})
    ports.RUNNING_EVIDENCE_TIMEOUT_S = timeout_s
    ports._rgbd[7_000_000_000] = (SimpleNamespace(_node=object()), None, None, "task_camera_frame")
    return ports


class _SilentObserver:
    publisher_count, callback_count, rejected_count, last_rejection = 1, 0, 0, ""

    def __init__(self, node, session_id, **keywords):
        pass

    def snapshot(self):
        from so101_demo.backends.mujoco.observer import EvidenceStale

        raise EvidenceStale("no atomic evidence has been accepted")

    def latest_summary(self):
        return None


def test_running_evidence_that_never_arrives_names_what_the_observer_saw(monkeypatch):
    ports = _ports_with_observer(monkeypatch, _SilentObserver)
    with pytest.raises(RuntimeError) as caught:
        ports._running_evidence(7.0)
    message = str(caught.value)
    assert message.startswith("RUNNING_EVIDENCE_UNAVAILABLE: ")
    seen = json.loads(message.split(": ", 1)[1])
    assert seen == {"callbacks": 0, "last_rejection": "", "latest": None, "minimum_simulation_time_s": 7.0, "publishers": 1, "rejected": 0}


def test_running_evidence_that_stays_paused_says_so(monkeypatch):
    class Paused(_SilentObserver):
        def snapshot(self):
            return SimpleNamespace(simulation_session_id="session-1", paused=True, simulation_time_s=7.4)

        def latest_summary(self):
            return {"paused": True, "simulation_time_s": 7.4, "age_s": 0.0}

    ports = _ports_with_observer(monkeypatch, Paused)
    with pytest.raises(RuntimeError, match="RUNNING_EVIDENCE_UNAVAILABLE") as caught:
        ports._running_evidence(7.0)
    assert json.loads(str(caught.value).split(": ", 1)[1])["latest"]["paused"] is True


def test_running_evidence_returns_the_first_unpaused_message_past_the_image_stamp(monkeypatch):
    class Running(_SilentObserver):
        def snapshot(self):
            return SimpleNamespace(simulation_session_id="session-1", paused=False, simulation_time_s=7.5)

    assert _ports_with_observer(monkeypatch, Running)._running_evidence(7.0).simulation_time_s == 7.5


def test_the_worker_binds_the_manifest_to_the_frozen_execution_policy(tmp_path):
    """The frozen policy reaches the manifest validator, so a v2 run needs its place_height record and a v1 run has none."""
    import json
    import os

    from so101_demo.parallel_batch import dynamic_manifest
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    policy = {"place_height_mode": "tilt_compensated"}

    identity = {name: 1 for name in ("batch_id", "coordinator_epoch", "worker_id", "worker_generation", "point_id", "attempt_id",
                                     "lease_generation")}
    document = {
        "schema": "so101-dynamic-execute", "schema_version": 1, "parallel_lease_identity": identity, "status": "DONE",
        "current_state": "DONE", "failure": None, "simulation_session_id": "session-1", "expected_reset_epoch": 3,
        "policy_path": "p", "policy_sha256": "a" * 64, "state_trace": [], "transition_count": 0, "state_events": [],
        "planning_attempts": [], "final_samples": [], "planning_scene_readback": {}, "release_marker_sequence": None,
        "teacher_execution_status": "COMPLETED", "teacher_task_result": {}, "act_data_status": "VALID",
        "process_diagnostics": [], "teacher_start_observation": {}, "teacher_end_observation": {}}
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(document))
    os.chmod(path, 0o600)
    seen = {}

    class Reached(Exception):
        pass

    def spy(*args, **kwargs):
        seen.update(kwargs)
        raise Reached

    for dependency in (policy, None):
        runtime = object.__new__(ParallelRosRuntimePorts)
        runtime.dependencies = {"teacher_execution_policy": dependency}
        runtime.resources = SimpleNamespace(session_id="session-1")
        runtime._dynamic_policy_identity = lambda: ("p", "a" * 64)
        runtime._trusted_final_cup_pose = lambda *a: None
        lease = SimpleNamespace(**identity)
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(dynamic_manifest, "validate_dynamic_manifest_semantics", spy)
            with pytest.raises(Reached):
                runtime._dynamic_manifest_outcome(path, lease, SimpleNamespace(reset_epoch="reset-3"), 0)
        assert seen["frozen_execution_policy"] is dependency
