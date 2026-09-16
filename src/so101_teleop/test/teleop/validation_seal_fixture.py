"""Hermetic producer-shaped evidence for validation bridge boundary tests."""

import base64
from dataclasses import asdict

from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import DYNAMIC_MOTION_STATES
from so101_demo.core.workflow import SO101_WORKFLOW
from so101_demo.parallel_batch.artifacts import AttemptWorkspace
from so101_demo.parallel_batch.contracts import RunMode


def make_sealed_attempt(worker_root, identity, *, succeeded=True):
    session = f"session-{identity.worker_id}-{identity.worker_generation}"
    workspace = AttemptWorkspace.create(
        worker_root, identity, reset_epoch="reset-7",
        source_stamp={"reset_completed_monotonic_s": 12.5,
                      "simulation_session_id": session, "simulation_time_s": 31.25},
        run_mode=RunMode.EXECUTE,
    )
    workspace.write_json("attempt-result.json", {
        "status": "PASSED" if succeeded else "FAILED",
        "reason": "OK" if succeeded else "INITIAL_GATE_REJECTED",
        "physical_action_proven_absent": not succeeded,
    })
    # A valid PNG, rather than bytes that only satisfy an upstream nonempty check.
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aL1sAAAAASUVORK5CYII="
    )
    (workspace.path / "initial-rgb.png").write_bytes(png)
    rgb = workspace.path / "perception/input/rgb.npy"
    rgb.parent.mkdir(parents=True)
    rgb.write_bytes(b"controlled-rgb-input")
    if not succeeded:
        return workspace.seal()

    workspace.write_json("pose_accepted.json", {
        "type": "POSE_ACCEPTED", "request": {
            **asdict(identity), "execution_kind": "attempt", "validation_id": None,
            "reset_epoch": "reset-7",
        },
    })
    workspace.write_json("numeric/depth.json", {
        "source_stamp_ns": 32_000_000_000, "sha256": "a" * 64, "byte_count": 1,
    })
    workspace.write_json("numeric/tf.json", {
        "source_frame": "task_camera_frame", "target_frame": "world",
        "source_stamp_s": 32.0, "center_world_xyz": [0.0, 0.0, 0.16],
    })
    workspace.write_json("numeric/physical.json", {
        "simulation_session_id": session, "reset_epoch": 7, "simulation_step": 1,
        "publisher_sequence": 1, "paused": False,
        "object_state": {"position_world": [0.0, 0.0, 0.16]},
    })

    def physical(sequence):
        return {
            "reset_epoch": 7, "simulation_step": sequence * 5,
            "publisher_sequence": sequence,
            "cup_position_world_m": [-0.08, -0.25, 0.1648],
            "cup_orientation_world_xyzw": [0.0, 0.0, 0.0, 1.0],
            "cup_linear_velocity_world_m_s": [0.0] * 3,
            "cup_angular_velocity_world_rad_s": [0.0] * 3,
            "left_contact_count": 0, "right_contact_count": 0,
            "maximum_normal_force_n": 0.2, "table_contact": True,
        }

    trace = [State.IDLE]
    while trace[-1] not in SO101_WORKFLOW.terminal_states:
        trace.append(SO101_WORKFLOW.transitions[trace[-1]][0])
    events, planning = [], []
    for index, state in enumerate(trace[:-1]):
        if state not in SO101_WORKFLOW.action_states:
            continue
        item = {"state": state.value, "before": physical(100 + index * 2),
                "after": physical(101 + index * 2)}
        if state in DYNAMIC_MOTION_STATES:
            item.update(terminal_joint_positions_rad=[0.0] * 5,
                        terminal_joint_state_source_stamp_ns=(index + 1) * 1_000_000,
                        execution_reconciliations=[])
            planning.append({"kind": "moveit_joint_plan", "state": state.value,
                             "accepted": True})
        if state is State.VALIDATE_FINAL_PLACEMENT:
            item.update(expected_cup_pose_world=[-0.08, -0.25, 0.1648, 0, 0, 0, 1],
                        final_xy_error_m=0.0, final_upright_tilt_rad=0.0)
        events.append(item)
    workspace.write_json("dynamic/dynamic-execute-manifest.json", {
        "parallel_lease_identity": asdict(identity), "simulation_session_id": session,
        "expected_reset_epoch": 7, "status": "DONE", "current_state": "DONE",
        "failure": None, "state_trace": [state.value for state in trace],
        "transition_count": len(trace) - 1, "state_events": events,
        "planning_attempts": planning, "final_samples": [physical(1000)],
        "planning_scene_readback": {"attached_object_ids": [],
                                    "world_primitive_counts": {"plastic_cup": 13}},
        "release_marker_sequence": 900,
    })
    (workspace.path / "terminal-rgb.png").write_bytes(png)
    return workspace.seal()
