#!/usr/bin/env python3
"""production live phase: bounded closed-loop TCP correction before release."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import rclpy
from moveit_msgs.action import ExecuteTrajectory
from moveit_msgs.msg import PlanningSceneComponents
from moveit_msgs.srv import GetMotionPlan, GetPlanningScene
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import JointState
from so101_demo.application.dynamic_transport_evidence import ContactForceMode
from so101_demo.application.pick_place import load_live_task_policy
from so101_demo.application.place_alignment import (
    align_cup_for_release,
    load_place_alignment_policy,
    release_alignment_target,
)
from so101_demo.backends.mujoco.observer import EvidenceStale, MujocoWorldObserver
from so101_demo.backends.mujoco.transport_observer import check_force
from so101_demo.control.moveit.planning import (
    MoveItPlanningClient,
    PosePlanRequest,
)
from so101_demo.control.trajectory.executor import (
    MoveItExecutionClient,
    SustainedConditionGuard,
    make_execute_goal,
)
from tf2_ros import Buffer, TransformListener

SESSION_ID = os.environ["SO101_SIMULATION_SESSION_ID"]
EXPECTED_EPOCH = int(os.environ["SO101_EXPECTED_RESET_EPOCH"])
EVIDENCE_PATH = Path(os.environ["SO101_EVIDENCE_ROOT"]) / "place-alignment.json"
POLICY_PATH = Path(os.environ["SO101_MOTION_POLICY"])
PLACE_XYZ = (-0.080, -0.250, 0.165)
ALL_JOINTS = ("1", "2", "3", "4", "5", "6")
DIAGNOSTIC_HARD_STOP_FORCE_N = 11.60


def atomic_write(document: dict) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = EVIDENCE_PATH.with_name(f".{EVIDENCE_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, EVIDENCE_PATH)


def evidence_dict(value) -> dict:
    return {
        "publisher_sequence": value.publisher_sequence,
        "simulation_step": value.simulation_step,
        "reset_epoch": value.reset_epoch,
        "paused": value.paused,
        "cup_position_world_m": list(value.object_state.position_world),
        "left_contact_count": len(value.left_fingertip_contacts),
        "right_contact_count": len(value.right_fingertip_contacts),
        "other_contact_geoms": sorted({item.geom2 for item in value.other_object_contacts}),
        "maximum_normal_force_n": value.maximum_normal_force_n,
    }


def main() -> int:
    task_policy = load_live_task_policy()
    assert task_policy.contact is not None
    maximum_safe_force_n = task_policy.contact.thresholds.maximum_safe_force_n
    policy = load_place_alignment_policy(POLICY_PATH)
    target = release_alignment_target(PLACE_XYZ, policy)
    result: dict = {
        "schema": "so101-live-place-alignment-v1",
        "simulation_session_id": SESSION_ID,
        "reset_epoch": EXPECTED_EPOCH,
        "target_cup_position_world_m": list(target),
        "policy": {
            "settling_compensation_m": list(policy.settling_compensation_m),
            "xy_tolerance_m": policy.xy_tolerance_m,
            "z_tolerance_m": policy.z_tolerance_m,
            "max_attempts": policy.max_attempts,
            "max_axis_correction_m": policy.max_axis_correction_m,
        },
        "physics_pause_calls": 0,
        "simulator_constraint_calls": 0,
        "direct_object_state_writes": 0,
        "executions": [],
        "status": "RUNNING",
    }
    rclpy.init()
    node = rclpy.create_node("so101_live_place_alignment")
    latest_joint: dict[str, float] = {}

    def on_joints(message: JointState) -> None:
        if len(message.name) == len(message.position):
            latest_joint.update(zip(message.name, message.position, strict=True))

    subscription = node.create_subscription(
        JointState, "/joint_states", on_joints, qos_profile_sensor_data
    )
    observer = MujocoWorldObserver(node, SESSION_ID, max_age_s=0.5)
    planning_service = node.create_client(GetMotionPlan, "/plan_kinematic_path")
    scene_service = node.create_client(GetPlanningScene, "/get_planning_scene")
    execute_action = ActionClient(node, ExecuteTrajectory, "/execute_trajectory")
    tf_buffer = Buffer()
    tf_listener = TransformListener(tf_buffer, node)
    del tf_listener

    def progress() -> None:
        rclpy.spin_once(node, timeout_sec=0.01)

    def wait_for(predicate, timeout_s: float, message: str):
        deadline = time.monotonic() + timeout_s
        while rclpy.ok() and time.monotonic() < deadline:
            value = predicate()
            if value is not None and value is not False:
                return value
            progress()
        raise RuntimeError(message)

    def snapshot():
        try:
            return observer.snapshot()
        except EvidenceStale:
            return None

    def validate(value) -> None:
        if value.paused or value.reset_epoch != EXPECTED_EPOCH:
            raise RuntimeError("MuJoCo pause/reset during place alignment")
        decision = check_force(
            value.maximum_normal_force_n,
            ContactForceMode.DYNAMIC_HELD_OBJECT_MOTION,
            static_threshold_n=maximum_safe_force_n,
            diagnostic_stop_n=DIAGNOSTIC_HARD_STOP_FORCE_N,
        )
        if decision.cancel:
            raise RuntimeError(f"{decision.reason} during place alignment")

    def stable_bilateral(duration_s: float = 0.20):
        started: float | None = None
        last_sequence = -1
        latest = None
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            progress()
            value = snapshot()
            if value is None or value.publisher_sequence == last_sequence:
                continue
            last_sequence = value.publisher_sequence
            validate(value)
            bilateral = bool(value.left_fingertip_contacts and value.right_fingertip_contacts)
            table_contact = any(
                item.geom2 == "table_collision" for item in value.other_object_contacts
            )
            healthy = bilateral and not table_contact
            now = time.monotonic()
            started = started if healthy and started is not None else (now if healthy else None)
            latest = value
            if started is not None and now - started >= duration_s:
                return latest
        raise RuntimeError("stable bilateral off-table state timeout")

    planning = MoveItPlanningClient(planning_service, progress=progress)

    def execute_translation(delta: tuple[float, float, float]) -> None:
        before = stable_bilateral()
        transform = wait_for(
            lambda: lookup_transform(tf_buffer),
            5.0,
            "world-to-TCP transform unavailable",
        )
        translation = transform.transform.translation
        rotation = transform.transform.rotation
        current = tuple(float(latest_joint[name]) for name in ALL_JOINTS)
        request = PosePlanRequest(
            joint_names=ALL_JOINTS,
            current_positions=current,
            target_position_m=(
                translation.x + delta[0],
                translation.y + delta[1],
                translation.z + delta[2],
            ),
            target_orientation_xyzw=(
                rotation.x,
                rotation.y,
                rotation.z,
                rotation.w,
            ),
            orientation_tolerance_rad=(0.05, 0.05, 0.05),
            position_tolerance_m=0.001,
            velocity_scaling=0.03,
            acceleration_scaling=0.03,
            planning_time_s=8.0,
        )
        planned = planning.plan_pose_path(request, timeout_s=15.0)
        if planned.failure is not None or planned.trajectory is None:
            code = "EMPTY" if planned.failure is None else planned.failure.code
            raise RuntimeError(f"place alignment planning failed: {code}")
        contact_guard = SustainedConditionGuard(0.05)

        def monitor() -> None:
            value = snapshot()
            if value is None:
                raise RuntimeError("stale MuJoCo evidence during place alignment")
            validate(value)
            contact_guard.require(
                bool(value.left_fingertip_contacts and value.right_fingertip_contacts),
                "bilateral contact lost during place alignment",
            )
            if any(item.geom2 == "table_collision" for item in value.other_object_contacts):
                raise RuntimeError("cup touched table before release")

        executed = MoveItExecutionClient(
            execute_action,
            goal_factory=make_execute_goal,
            progress=progress,
        ).execute(planned.trajectory, 45.0, monitor=monitor)
        if executed.failure is not None:
            raise RuntimeError(
                "place alignment execution failed: "
                f"{executed.failure.code}: {executed.failure.message}"
            )
        after = stable_bilateral()
        result["executions"].append(
            {
                "commanded_translation_m": list(delta),
                "trajectory_points": len(planned.trajectory.joint_trajectory.points),
                "before_evidence": evidence_dict(before),
                "after_evidence": evidence_dict(after),
            }
        )
        atomic_write(result)

    try:
        for client, name in (
            (planning_service, "/plan_kinematic_path"),
            (scene_service, "/get_planning_scene"),
        ):
            if not client.wait_for_service(timeout_sec=20.0):
                raise RuntimeError(f"{name} unavailable")
        if not execute_action.wait_for_server(timeout_sec=20.0):
            raise RuntimeError("execute action unavailable")
        wait_for(lambda: len(latest_joint) == 6, 5.0, "joint state unavailable")
        initial = stable_bilateral()
        query = GetPlanningScene.Request()
        query.components.components = PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        queried = scene_service.call_async(query)
        wait_for(lambda: queried.done(), 5.0, "Planning Scene readback timeout")
        attached_ids = [
            item.object.id for item in queried.result().scene.robot_state.attached_collision_objects
        ]
        if "plastic_cup" not in attached_ids:
            raise RuntimeError("MoveIt collision shadow is not attached")
        result["before_evidence"] = evidence_dict(initial)
        result["moveit_attached_ids"] = attached_ids
        atomic_write(result)

        aligned = align_cup_for_release(
            lambda: tuple(stable_bilateral().object_state.position_world),
            target,
            execute_translation,
            policy,
        )
        terminal = stable_bilateral()
        result["alignment"] = {
            "position_m": list(aligned.position_m),
            "attempt_count": aligned.attempt_count,
            "telemetry": [
                {
                    "attempt": item.attempt,
                    "before_position_m": list(item.before_position_m),
                    "commanded_translation_m": list(item.commanded_translation_m),
                    "after_position_m": list(item.after_position_m),
                    "before_xy_error_m": item.before_xy_error_m,
                    "after_xy_error_m": item.after_xy_error_m,
                }
                for item in aligned.telemetry
            ],
        }
        result["terminal_evidence"] = evidence_dict(terminal)
        result["status"] = "PRE_RELEASE_ALIGNMENT_PROVED"
        atomic_write(result)
        print(
            f"EXP115_ALIGNMENT_OK attempts={aligned.attempt_count} position={aligned.position_m}",
            flush=True,
        )
        return 0
    except Exception as error:
        result["status"] = "FAILED"
        result["error"] = f"{type(error).__name__}: {error}"
        atomic_write(result)
        print(f"EXP115_ALIGNMENT_FAILED {type(error).__name__}: {error}", flush=True)
        return 1
    finally:
        del subscription
        node.destroy_node()
        rclpy.shutdown()


def lookup_transform(buffer: Buffer):
    try:
        return buffer.lookup_transform("world", "so101_tcp", Time(), timeout=Duration(seconds=0.05))
    except Exception:
        return None


if __name__ == "__main__":
    raise SystemExit(main())
