from __future__ import annotations

import copy
import hashlib
import json
from types import SimpleNamespace

import pytest


SUCCESS_TRACE = [
    "IDLE",
    "PREPARE_OPEN_GRIPPER",
    "MOVE_ABOVE_OBJECT",
    "DESCEND",
    "CLOSE_GRIPPER",
    "WAIT_GRASP_STABLE",
    "MICRO_LIFT",
    "WAIT_MICRO_LIFT_STABLE",
    "VERIFY_PHYSICAL_GRASP",
    "ATTACH_MOVEIT",
    "LIFT",
    "MOVE_ABOVE_PLACE",
    "DESCEND_TO_PLACE",
    "DETACH_MOVEIT",
    "OPEN_GRIPPER",
    "WAIT_RELEASE_SETTLE",
    "VALIDATE_FINAL_PLACEMENT",
    "SYNC_WORLD_OBJECT",
    "RETREAT",
    "DONE",
]


def _motion_event(state: str, before, after) -> dict[str, object]:
    return {
        "state": state,
        "before": before,
        "after": after,
        "trajectory_points": 3,
        "terminal_joint_state_generation": 4,
        "terminal_joint_state_source_stamp_ns": 2_000_000_000,
        "terminal_joint_state_received_monotonic_s": 20.0,
        "terminal_position_error_m": 0.001,
        "terminal_orientation_error_rad": 0.02,
        "terminal_fk_pose": [0.0, 0.0, 0.25, 0.0, 0.0, 0.0, 1.0],
        "target_pose": [0.0, 0.0, 0.25, 0.0, 0.0, 0.0, 1.0],
        "execution_reconciliations": [],
    }


@pytest.fixture
def accepted_document() -> dict[str, object]:
    pick = {
        "publisher_sequence": 20,
        "reset_epoch": 7,
        "cup_position_world_m": [0.02, -0.28, 0.165],
        "cup_orientation_world_xyzw": [0.0, 0.0, 0.0, 1.0],
        "cup_linear_velocity_world_m_s": [0.0, 0.0, 0.0],
        "cup_angular_velocity_world_rad_s": [0.0, 0.0, 0.0],
        "left_contact_count": 1,
        "right_contact_count": 1,
        "table_contact": False,
    }
    lifted = copy.deepcopy(pick)
    lifted["publisher_sequence"] = 30
    lifted["cup_position_world_m"] = [0.02, -0.28, 0.225]
    transported = copy.deepcopy(lifted)
    transported["publisher_sequence"] = 40
    transported["cup_position_world_m"] = [-0.07, -0.23, 0.225]
    released = copy.deepcopy(transported)
    released.update(
        {
            "publisher_sequence": 51,
            "cup_position_world_m": [-0.07, -0.23, 0.165],
            "left_contact_count": 0,
            "right_contact_count": 0,
            "table_contact": True,
        }
    )
    events = [
        {"state": state, "before": pick, "after": pick}
        for state in SUCCESS_TRACE[1:-1]
    ]
    by_state = {event["state"]: event for event in events}
    for state in (
        "MOVE_ABOVE_OBJECT",
        "DESCEND",
        "MICRO_LIFT",
        "LIFT",
        "MOVE_ABOVE_PLACE",
        "DESCEND_TO_PLACE",
        "RETREAT",
    ):
        index = events.index(by_state[state])
        before = pick
        after = pick
        if state == "MICRO_LIFT":
            after = copy.deepcopy(pick)
            after["cup_position_world_m"] = [0.02, -0.28, 0.169]
        elif state == "LIFT":
            before, after = pick, lifted
        elif state == "MOVE_ABOVE_PLACE":
            before, after = lifted, transported
        elif state in {"DESCEND_TO_PLACE", "RETREAT"}:
            before, after = transported, released
        events[index] = _motion_event(state, before, after)
        by_state[state] = events[index]
    by_state["MICRO_LIFT"].update(
        {
            "physical_cup_lift_m": 0.004,
            "physical_bilateral_contact": True,
            "physical_table_contact": False,
            "validation_failure": None,
        }
    )
    by_state["WAIT_RELEASE_SETTLE"].update({"before": transported, "after": released})
    by_state["VALIDATE_FINAL_PLACEMENT"].update(
        {
            "before": released,
            "after": released,
            "final_xy_error_m": 0.002,
            "final_upright_tilt_rad": 0.0,
        }
    )

    final_pose = [-0.07, -0.23, 0.165, 0.0, 0.0, 0.0, 1.0]
    return {
        "expected_identity": {
            "workflow_id": "workflow-001",
            "request_id": "request-001",
            "simulation_session_id": "session-001",
            "reset_epoch": 7,
        },
        "dynamic": {
            "schema": "so101-dynamic-mujoco-execute-v1",
            "workflow_id": "workflow-001",
            "request_id": "request-001",
            "simulation_session_id": "session-001",
            "expected_reset_epoch": 7,
            "policy_sha256": "a" * 64,
            "status": "DONE",
            "current_state": "DONE",
            "failure": None,
            "state_trace": SUCCESS_TRACE,
            "state_events": events,
            "resolved_targets": {
                "LIFT": [0.02, -0.28, 0.225, 0.0, 0.0, 0.0, 1.0],
                "MOVE_ABOVE_PLACE": [-0.07, -0.23, 0.225, 0.0, 0.0, 0.0, 1.0],
            },
            "release_marker_sequence": 50,
            "planning_scene_readback": {
                "attached_object_ids": [],
                "world_primitive_counts": {
                    "table": 1,
                    "pedestal": 1,
                    "plastic_cup": 13,
                },
            },
            "input_frame_id": "task_camera_frame",
            "input_source_stamp_ns": 1_000_000_000,
            "final_samples": [released],
        },
        "perception": {
            "status": "OK",
            "failure": None,
            "request_id": "request-001",
            "source_stamp_ns": 1_000_000_000,
            "source_frame_id": "task_camera_frame",
            "published_cup_pose": True,
        },
        "mujoco_final": {
            "simulation_session_id": "session-001",
            "reset_epoch": 7,
            "publisher_sequence": 60,
            "simulation_step": 500,
            "source_timestamp_ns": 3_000_000_000,
            "paused": False,
            "cup_pose_world": final_pose,
            "cup_linear_velocity_world_m_s": [0.0, 0.0, 0.0],
            "cup_angular_velocity_world_rad_s": [0.0, 0.0, 0.0],
            "table_contact": True,
            "left_fingertip_contact_count": 0,
            "right_fingertip_contact_count": 0,
        },
        "planning_scene_final": {
            "simulation_session_id": "session-001",
            "reset_epoch": 7,
            "source_timestamp_ns": 3_000_000_100,
            "attached_object_ids": [],
            "world_objects": {
                "table": {"primitive_count": 1},
                "pedestal": {"primitive_count": 1},
                "plastic_cup": {
                    "primitive_count": 13,
                    "pose_xyz_xyzw": list(final_pose),
                },
            },
        },
        "policy": {
            "qualification_status": "LOCAL_E2E_CANDIDATE",
            "sha256": "a" * 64,
            "terminal_position_tolerance_m": 0.002,
            "terminal_orientation_tolerance_rad": 0.10,
            "final_pose_position_tolerance_m": 0.01,
            "final_pose_orientation_tolerance_rad": 0.10,
            "support_height_range_m": [0.155, 0.175],
            "max_upright_tilt_rad": 0.15,
            "max_linear_speed_m_s": 0.001,
            "max_angular_speed_rad_s": 0.05,
            "max_readback_skew_ns": 1_000_000_000,
        },
    }


def test_missing_evidence_is_rejected() -> None:
    from so101_demo.application.e2e_acceptance import validate_e2e_evidence

    report = validate_e2e_evidence({})
    assert report.accepted is False
    assert report.failures
    json.dumps(report.to_document())


@pytest.mark.parametrize("value", [None, [], "invalid", {"dynamic": []}])
def test_malformed_evidence_is_serializably_rejected(value) -> None:
    from so101_demo.application.e2e_acceptance import validate_e2e_evidence

    report = validate_e2e_evidence(value)
    assert report.accepted is False
    assert report.failures
    json.dumps(report.to_document(), allow_nan=False)


def test_complete_correlated_evidence_is_accepted(accepted_document) -> None:
    from so101_demo.application.e2e_acceptance import validate_e2e_evidence

    report = validate_e2e_evidence(accepted_document)
    assert report.accepted is True
    assert report.failures == ()
    assert report.physical_outcome["stable"] is True
    assert report.planning_scene_outcome["pose_matches_mujoco"] is True


@pytest.mark.parametrize(
    ("path", "replacement", "failure"),
    [
        (("dynamic", "workflow_id"), "other", "E2E_IDENTITY_MISMATCH"),
        (("perception", "request_id"), "other", "E2E_IDENTITY_MISMATCH"),
        (("mujoco_final", "reset_epoch"), 8, "E2E_IDENTITY_MISMATCH"),
        (("dynamic", "status"), "RUNNING", "E2E_DYNAMIC_EVIDENCE_INVALID"),
        (("dynamic", "state_trace"), SUCCESS_TRACE[:-1], "E2E_DYNAMIC_EVIDENCE_INVALID"),
        (("dynamic", "release_marker_sequence"), 70, "E2E_DYNAMIC_EVIDENCE_INVALID"),
        (("mujoco_final", "table_contact"), False, "E2E_MUJOCO_FINAL_INVALID"),
        (
            ("mujoco_final", "left_fingertip_contact_count"),
            1,
            "E2E_MUJOCO_FINAL_INVALID",
        ),
        (
            ("planning_scene_final", "attached_object_ids"),
            ["plastic_cup"],
            "E2E_PLANNING_SCENE_INVALID",
        ),
        (
            ("policy", "qualification_status"),
            "CALIBRATION_REQUIRED",
            "E2E_DYNAMIC_EVIDENCE_INVALID",
        ),
    ],
)
def test_each_invalid_fact_is_rejected(
    accepted_document,
    path: tuple[str, str],
    replacement,
    failure: str,
) -> None:
    from so101_demo.application.e2e_acceptance import validate_e2e_evidence

    document = copy.deepcopy(accepted_document)
    document[path[0]][path[1]] = replacement
    report = validate_e2e_evidence(document)

    assert report.accepted is False
    assert failure in report.failures


def test_controller_feedback_and_micro_lift_are_required(accepted_document) -> None:
    from so101_demo.application.e2e_acceptance import validate_e2e_evidence

    for state, field, value in (
        ("LIFT", "terminal_joint_state_generation", 0),
        ("LIFT", "terminal_position_error_m", 0.2),
        ("MICRO_LIFT", "physical_cup_lift_m", 0.0),
    ):
        document = copy.deepcopy(accepted_document)
        event = next(
            item
            for item in document["dynamic"]["state_events"]
            if item["state"] == state
        )
        event[field] = value
        report = validate_e2e_evidence(document)
        assert "E2E_DYNAMIC_EVIDENCE_INVALID" in report.failures


def test_final_pose_and_timestamps_must_agree(accepted_document) -> None:
    from so101_demo.application.e2e_acceptance import validate_e2e_evidence

    pose_mismatch = copy.deepcopy(accepted_document)
    pose_mismatch["planning_scene_final"]["world_objects"]["plastic_cup"][
        "pose_xyz_xyzw"
    ][0] += 0.1
    report = validate_e2e_evidence(pose_mismatch)
    assert "E2E_PLANNING_SCENE_INVALID" in report.failures

    stale = copy.deepcopy(accepted_document)
    stale["planning_scene_final"]["source_timestamp_ns"] += 2_000_000_000
    report = validate_e2e_evidence(stale)
    assert "E2E_PLANNING_SCENE_INVALID" in report.failures


def test_readback_documents_preserve_atomic_simulation_and_scene_facts() -> None:
    from so101_demo.ros.e2e_acceptance_readback import (
        _planning_scene_readback_document,
        _simulation_readback_document,
    )

    contact = SimpleNamespace(
        body1="plastic_cup",
        geom1="cup_bottom",
        body2="table",
        geom2="table_collision",
    )
    evidence = SimpleNamespace(
        simulation_session_id="session-001",
        reset_epoch=7,
        publisher_sequence=60,
        simulation_step=500,
        simulation_time_s=3.0,
        paused=False,
        object_state=SimpleNamespace(
            position_world=(-0.07, -0.23, 0.165),
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            linear_velocity_world=(0.0, 0.0, 0.0),
            angular_velocity_world=(0.0, 0.0, 0.0),
        ),
        other_object_contacts=(contact,),
        left_fingertip_contacts=(),
        right_fingertip_contacts=(),
    )
    simulation = _simulation_readback_document(evidence)
    assert simulation["source_timestamp_ns"] == 3_000_000_000
    assert simulation["table_contact"] is True

    def pose(z: float):
        return SimpleNamespace(
            position=SimpleNamespace(x=-0.07, y=-0.23, z=z),
            orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
        )

    cup = SimpleNamespace(
        id="plastic_cup",
        primitives=[object()] * 13,
        primitive_poses=[pose(0.0)] * 12 + [pose(0.121)],
    )
    scene = SimpleNamespace(
        robot_state=SimpleNamespace(attached_collision_objects=[]),
        world=SimpleNamespace(
            collision_objects=[
                SimpleNamespace(id="table", primitives=[object()]),
                SimpleNamespace(id="pedestal", primitives=[object()]),
                cup,
            ]
        ),
    )
    planning = _planning_scene_readback_document(
        scene,
        session_id="session-001",
        reset_epoch=7,
        source_timestamp_ns=3_000_000_100,
    )
    assert planning["attached_object_ids"] == []
    cup_record = planning["world_objects"]["plastic_cup"]
    assert cup_record["primitive_count"] == 13
    assert cup_record["pose_xyz_xyzw"] == pytest.approx(
        [-0.07, -0.23, 0.165, 0.0, 0.0, 0.0, 1.0]
    )


def test_readback_runtime_uses_only_observer_and_get_scene_client() -> None:
    from so101_demo.ros.e2e_acceptance_readback import _collect_readback

    timeline = []
    contact = SimpleNamespace(
        body1="plastic_cup",
        geom1="cup_bottom",
        body2="table",
        geom2="table_collision",
    )
    evidence = SimpleNamespace(
        simulation_session_id="session-001",
        reset_epoch=7,
        publisher_sequence=60,
        simulation_step=500,
        simulation_time_s=3.0,
        paused=False,
        object_state=SimpleNamespace(
            position_world=(-0.07, -0.23, 0.165),
            orientation_xyzw=(0.0, 0.0, 0.0, 1.0),
            linear_velocity_world=(0.0, 0.0, 0.0),
            angular_velocity_world=(0.0, 0.0, 0.0),
        ),
        other_object_contacts=(contact,),
        left_fingertip_contacts=(),
        right_fingertip_contacts=(),
    )
    pose = SimpleNamespace(
        position=SimpleNamespace(x=-0.07, y=-0.23, z=0.121),
        orientation=SimpleNamespace(x=0.0, y=0.0, z=0.0, w=1.0),
    )
    scene = SimpleNamespace(
        robot_state=SimpleNamespace(attached_collision_objects=[]),
        world=SimpleNamespace(
            collision_objects=[
                SimpleNamespace(id="table", primitives=[object()]),
                SimpleNamespace(id="pedestal", primitives=[object()]),
                SimpleNamespace(
                    id="plastic_cup",
                    primitives=[object()] * 13,
                    primitive_poses=[pose] * 13,
                ),
            ]
        ),
    )

    class Observer:
        def snapshot(self):
            timeline.append("snapshot")
            return evidence

    class Future:
        def done(self):
            return True

        def result(self):
            return SimpleNamespace(scene=scene)

    class Client:
        def wait_for_service(self, *, timeout_sec):
            assert timeout_sec > 0.0
            timeline.append("wait-for-get-scene")
            return True

        def call_async(self, request):
            assert request is scene_request
            timeline.append("get-scene")
            return Future()

    scene_request = object()
    result = _collect_readback(
        node=SimpleNamespace(
            get_clock=lambda: SimpleNamespace(
                now=lambda: SimpleNamespace(nanoseconds=3_000_000_100)
            )
        ),
        observer=Observer(),
        scene_client=Client(),
        scene_request=scene_request,
        session_id="session-001",
        reset_epoch=7,
        timeout_s=1.0,
        spin_once=lambda _seconds: timeline.append("spin"),
        stale_error=RuntimeError,
        monotonic=lambda: 0.0,
    )

    assert timeline == ["spin", "snapshot", "wait-for-get-scene", "get-scene"]
    assert set(result) == {"mujoco_final", "planning_scene_final"}


def _write_cli_inputs(tmp_path, accepted_document) -> None:
    run_root = tmp_path / "run"
    (run_root / "dynamic").mkdir(parents=True)
    (run_root / "perception").mkdir()
    policy_root = tmp_path / "policy"
    policy_root.mkdir()
    policy_path = policy_root / "mujoco.yaml"
    policy_path.write_text(
        """\
backend: mujoco
planning:
  position_tolerance_m: 0.002
  orientation_tolerance_rad: [0.10, 0.10, 0.10]
safety:
  scene_position_tolerance_m: 0.01
  scene_orientation_tolerance_rad: 0.10
  maximum_source_age_s: 5.0
""",
        encoding="utf-8",
    )
    (policy_root / "manifest.yaml").write_text(
        """\
variants:
  mujoco:
    qualification_status: LOCAL_E2E_CANDIDATE
""",
        encoding="utf-8",
    )
    dynamic = copy.deepcopy(accepted_document["dynamic"])
    dynamic["policy_path"] = str(policy_path)
    dynamic["policy_sha256"] = hashlib.sha256(policy_path.read_bytes()).hexdigest()
    (run_root / "dynamic" / "dynamic-execute-manifest.json").write_text(
        json.dumps(dynamic),
        encoding="utf-8",
    )
    (run_root / "perception" / "result.json").write_text(
        json.dumps(accepted_document["perception"]),
        encoding="utf-8",
    )


def test_policy_document_accepts_colcon_symlink_install(
    tmp_path, accepted_document
) -> None:
    from so101_demo.cli import e2e_acceptance

    _write_cli_inputs(tmp_path, accepted_document)
    policy_path = tmp_path / "policy" / "mujoco.yaml"
    source_path = policy_path.with_name("mujoco-source.yaml")
    policy_path.rename(source_path)
    policy_path.symlink_to(source_path)
    dynamic = e2e_acceptance._read_document(
        tmp_path / "run" / "dynamic" / "dynamic-execute-manifest.json"
    )

    policy = e2e_acceptance._policy_document(dynamic)

    assert policy["sha256"] == hashlib.sha256(source_path.read_bytes()).hexdigest()


def test_acceptance_cli_persists_readback_and_emits_terminal_event(
    tmp_path, accepted_document, capsys
) -> None:
    from so101_demo.cli import e2e_acceptance

    _write_cli_inputs(tmp_path, accepted_document)
    readback = {
        "mujoco_final": accepted_document["mujoco_final"],
        "planning_scene_final": accepted_document["planning_scene_final"],
    }
    result = e2e_acceptance.main(
        [
            "--run-root",
            str(tmp_path / "run"),
            "--workflow-id",
            "workflow-001",
            "--request-id",
            "request-001",
            "--session-id",
            "session-001",
            "--expected-reset-epoch",
            "7",
            "--emit-workflow-events",
            "--ros-args",
        ],
        _collect=lambda **_kwargs: copy.deepcopy(readback),
    )

    captured = capsys.readouterr()
    assert result == 0
    assert '"event":"E2E_ACCEPTED"' in captured.out
    assert '"accepted": true' in captured.err
    result_path = tmp_path / "run" / "acceptance" / "result.json"
    assert json.loads(result_path.read_text())["accepted"] is True
    assert (tmp_path / "run" / "acceptance" / "mujoco-final.json").is_file()
    assert (
        tmp_path / "run" / "acceptance" / "planning-scene-final.json"
    ).is_file()


def test_acceptance_cli_emits_rejection_for_invalid_final_readback(
    tmp_path, accepted_document, capsys
) -> None:
    from so101_demo.cli import e2e_acceptance

    _write_cli_inputs(tmp_path, accepted_document)
    readback = {
        "mujoco_final": copy.deepcopy(accepted_document["mujoco_final"]),
        "planning_scene_final": accepted_document["planning_scene_final"],
    }
    readback["mujoco_final"]["table_contact"] = False

    result = e2e_acceptance.main(
        [
            "--run-root",
            str(tmp_path / "run"),
            "--workflow-id",
            "workflow-001",
            "--request-id",
            "request-001",
            "--session-id",
            "session-001",
            "--expected-reset-epoch",
            "7",
            "--emit-workflow-events",
        ],
        _collect=lambda **_kwargs: copy.deepcopy(readback),
    )

    captured = capsys.readouterr()
    assert result == 1
    assert '"event":"E2E_REJECTED"' in captured.out
    assert "E2E_MUJOCO_FINAL_INVALID" in captured.err
