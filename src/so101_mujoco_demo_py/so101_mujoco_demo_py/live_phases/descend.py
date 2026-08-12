#!/usr/bin/env python3
"""production live phase: descend the physical cup to pre-release clearance."""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import rclpy
from moveit_msgs.action import ExecuteTrajectory
from moveit_msgs.msg import PlanningSceneComponents
from moveit_msgs.srv import GetMotionPlan, GetPlanningScene
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState

from so101_mujoco_demo_py.live_runtime import load_live_task_policy
from so101_mujoco_demo_py.motion.executor import (
    MoveItExecutionClient,
    SustainedConditionGuard,
    make_execute_goal,
)
from so101_mujoco_demo_py.moveit.planning import (
    JointPlanRequest,
    MoveItPlanningClient,
    make_get_motion_plan_request,
)
from so101_mujoco_demo_py.mujoco.observer import EvidenceStale, MujocoWorldObserver
from so101_mujoco_demo_py.staged_approach import maximum_joint_error

SESSION_ID = os.environ["SO101_SIMULATION_SESSION_ID"]
EXPECTED_EPOCH = int(os.environ["SO101_EXPECTED_RESET_EPOCH"])
EVIDENCE_PATH = Path(os.environ["SO101_EVIDENCE_ROOT"]) / "descend.json"
ARM_JOINTS = ("1", "2", "3", "4", "5")
ALL_JOINTS = (*ARM_JOINTS, "6")
EXPECTED_START_ARM = (
    0.3941807984901571,
    0.21134367594946993,
    0.11009181694930642,
    1.1746502503950658,
    0.0017901430972551884,
)
EXPECTED_Q6 = -0.048090900762462946
TARGETS = (
    (0.392478252768, 0.303606814934, 0.110730521878, 1.115206323144, 0.001727851167),
    (0.390581887491, 0.396495834720, 0.111832238686, 1.055724805729, 0.001868839753),
    (0.389633705130, 0.442941344113, 0.112383097091, 1.025984047022, 0.001939334047),
)
CONTACT_LOSS_GRACE_S = 0.05
RELEASE_TARGET_XYZ = (-0.0788, -0.2475, 0.1835)
MAX_ALIGNMENT_CORRECTION_M = 0.030


def atomic_write(document: dict) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = EVIDENCE_PATH.with_name(f".{EVIDENCE_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, EVIDENCE_PATH)


def has_table_contact(evidence) -> bool:
    return any(item.geom2 == "table_collision" for item in evidence.other_object_contacts)


def evidence_dict(value) -> dict:
    return {
        "publisher_sequence": value.publisher_sequence,
        "simulation_step": value.simulation_step,
        "reset_epoch": value.reset_epoch,
        "paused": value.paused,
        "cup_position_world_m": list(value.object_state.position_world),
        "cup_orientation_world_xyzw": list(value.object_state.orientation_xyzw),
        "cup_linear_velocity_world_m_s": list(value.object_state.linear_velocity_world),
        "cup_angular_velocity_world_rad_s": list(value.object_state.angular_velocity_world),
        "left_contact_count": len(value.left_fingertip_contacts),
        "right_contact_count": len(value.right_fingertip_contacts),
        "table_contact": has_table_contact(value),
        "other_contact_geoms": sorted({item.geom2 for item in value.other_object_contacts}),
        "maximum_normal_force_n": value.maximum_normal_force_n,
    }


def main() -> int:
    task_policy = load_live_task_policy()
    assert task_policy.contact is not None
    maximum_safe_force_n = task_policy.contact.thresholds.maximum_safe_force_n
    result: dict = {
        "schema": "so101-live-noslip-descend-v1",
        "simulation_session_id": SESSION_ID,
        "targets_arm_rad": [list(target) for target in TARGETS],
        "contact_loss_grace_s": CONTACT_LOSS_GRACE_S,
        "physics_pause_calls": 0,
        "simulator_constraint_calls": 0,
        "direct_object_state_writes": 0,
        "status": "RUNNING",
        "segments": [],
    }
    rclpy.init()
    node = rclpy.create_node("so101_live_descend")
    latest_joint: dict[str, float] = {}

    def on_joints(message: JointState) -> None:
        if len(message.name) == len(message.position):
            latest_joint.update(zip(message.name, message.position, strict=True))

    subscription = node.create_subscription(
        JointState, "/joint_states", on_joints, qos_profile_sensor_data
    )
    observer = MujocoWorldObserver(node, SESSION_ID, max_age_s=0.5)
    planning_service = node.create_client(GetMotionPlan, "/plan_kinematic_path")
    get_scene = node.create_client(GetPlanningScene, "/get_planning_scene")
    execute_action = ActionClient(node, ExecuteTrajectory, "/execute_trajectory")

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

    def stable_gate(epoch: int, *, require_support: bool):
        start: float | None = None
        last_sequence = -1
        latest = None
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            progress()
            evidence = snapshot()
            if evidence is None or evidence.publisher_sequence == last_sequence:
                continue
            last_sequence = evidence.publisher_sequence
            if evidence.paused or evidence.reset_epoch != epoch:
                raise RuntimeError("MuJoCo pause/reset during stable gate")
            if evidence.maximum_normal_force_n > maximum_safe_force_n:
                raise RuntimeError("force boundary exceeded during stable gate")
            bilateral = bool(evidence.left_fingertip_contacts and evidence.right_fingertip_contacts)
            support_ok = has_table_contact(evidence) == require_support
            now = time.monotonic()
            healthy = bilateral and support_ok
            start = start if healthy and start is not None else (now if healthy else None)
            latest = evidence
            if start is not None and now - start >= 0.20:
                return latest
        raise RuntimeError("stable physical gate timeout")

    try:
        for client, name in (
            (planning_service, "/plan_kinematic_path"),
            (get_scene, "/get_planning_scene"),
        ):
            if not client.wait_for_service(timeout_sec=20.0):
                raise RuntimeError(f"{name} unavailable")
        if not execute_action.wait_for_server(timeout_sec=20.0):
            raise RuntimeError("execute action unavailable")
        wait_for(lambda: len(latest_joint) == 6, 5.0, "joint state unavailable")
        before = wait_for(snapshot, 5.0, "MuJoCo evidence unavailable")
        if before.paused or before.reset_epoch != EXPECTED_EPOCH:
            raise RuntimeError("unexpected initial MuJoCo provenance")
        start_positions = tuple(float(latest_joint[name]) for name in ALL_JOINTS)
        if maximum_joint_error(start_positions[:5], EXPECTED_START_ARM) > 0.01:
            raise RuntimeError("robot is not at CP-141 endpoint")
        if abs(start_positions[-1] - EXPECTED_Q6) > 0.002:
            raise RuntimeError("q6 is not at CP-141 endpoint")
        stable = stable_gate(before.reset_epoch, require_support=False)
        initial_cup = tuple(stable.object_state.position_world)
        result["before_joints_rad"] = list(start_positions)
        result["before_evidence"] = evidence_dict(stable)

        query = GetPlanningScene.Request()
        query.components.components = PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        queried = get_scene.call_async(query)
        wait_for(lambda: queried.done(), 3.0, "MoveIt attach readback timeout")
        response = queried.result()
        attached_ids = (
            []
            if response is None
            else [item.object.id for item in response.scene.robot_state.attached_collision_objects]
        )
        if "plastic_cup" not in attached_ids:
            raise RuntimeError("MoveIt collision shadow is not attached")
        result["moveit_attached_ids"] = attached_ids
        atomic_write(result)

        planning = MoveItPlanningClient(
            planning_service,
            request_factory=make_get_motion_plan_request,
            progress=progress,
        )
        previous_cup = initial_cup
        for index, target in enumerate(TARGETS, start=1):
            current = tuple(float(latest_joint[name]) for name in ALL_JOINTS)
            planned = planning.plan_joint_path(
                JointPlanRequest(
                    joint_names=ARM_JOINTS,
                    current_positions=current[:5],
                    target_positions=target,
                    velocity_scaling=0.05,
                    acceleration_scaling=0.05,
                    planning_time_s=5.0,
                    start_state_joint_names=ALL_JOINTS,
                    start_state_positions=current,
                ),
                timeout_s=12.0,
            )
            if planned.failure is not None or planned.trajectory is None:
                code = "EMPTY" if planned.failure is None else planned.failure.code
                raise RuntimeError(f"descend waypoint {index} planning failed: {code}")
            trajectory_start = tuple(
                float(value) for value in planned.trajectory.joint_trajectory.points[0].positions
            )
            handoff = tuple(float(latest_joint[name]) for name in ARM_JOINTS)
            drift = maximum_joint_error(handoff, trajectory_start)
            if drift > 0.01:
                raise RuntimeError(f"descend waypoint {index} plan drift exceeded")

            contact_guard = SustainedConditionGuard(CONTACT_LOSS_GRACE_S)
            allow_support = False

            def monitor() -> None:
                evidence = snapshot()
                if evidence is None:
                    raise RuntimeError("stale MuJoCo evidence during descend")
                if evidence.paused or evidence.reset_epoch != before.reset_epoch:
                    raise RuntimeError("MuJoCo pause/reset during descend")
                if evidence.maximum_normal_force_n > maximum_safe_force_n:
                    raise RuntimeError("force boundary exceeded during descend")
                contact_guard.require(
                    bool(evidence.left_fingertip_contacts and evidence.right_fingertip_contacts),
                    "bilateral contact lost",
                )
                if has_table_contact(evidence) and not allow_support:
                    raise RuntimeError("cup contacted table before final waypoint")

            execution = MoveItExecutionClient(
                execute_action,
                goal_factory=make_execute_goal,
                progress=progress,
            ).execute(planned.trajectory, 45.0, monitor=monitor)
            if execution.failure is not None:
                raise RuntimeError(
                    f"descend waypoint {index} execution failed: "
                    f"{execution.failure.code}: {execution.failure.message}"
                )
            wait_for(
                lambda: (
                    tuple(float(latest_joint[name]) for name in ARM_JOINTS)
                    if maximum_joint_error(
                        tuple(float(latest_joint[name]) for name in ARM_JOINTS),
                        target,
                    )
                    <= 0.01
                    else None
                ),
                10.0,
                f"descend waypoint {index} endpoint timeout",
            )
            after = stable_gate(before.reset_epoch, require_support=False)
            cup = tuple(after.object_state.position_world)
            result["segments"].append(
                {
                    "waypoint": index,
                    "trajectory_points": len(planned.trajectory.joint_trajectory.points),
                    "plan_to_execute_drift_rad": drift,
                    "terminal_joints_rad": [float(latest_joint[name]) for name in ALL_JOINTS],
                    "terminal_evidence": evidence_dict(after),
                    "segment_cup_displacement_m": math.dist(cup, previous_cup),
                }
            )
            atomic_write(result)
            previous_cup = cup

        terminal = tuple(result["segments"][-1]["terminal_evidence"]["cup_position_world_m"])
        total_vertical_descent = initial_cup[2] - terminal[2]
        total_lateral = math.hypot(terminal[0] - initial_cup[0], terminal[1] - initial_cup[1])
        if not 0.04 <= total_vertical_descent <= 0.09:
            raise RuntimeError("total vertical descent outside gate")
        if total_lateral > 0.03:
            raise RuntimeError("total lateral displacement exceeded")
        alignment_correction = math.dist(terminal, RELEASE_TARGET_XYZ)
        if alignment_correction > MAX_ALIGNMENT_CORRECTION_M:
            raise RuntimeError("pre-release pose exceeds bounded alignment correction")
        result.update(
            {
                "status": "FORMAL_DESCEND_TO_PRE_RELEASE_CLEARANCE_PROVED",
                "total_vertical_descent_m": total_vertical_descent,
                "total_lateral_displacement_m": total_lateral,
                "required_alignment_correction_m": alignment_correction,
            }
        )
        atomic_write(result)
        print(
            f"EXP108_OK dz_m={total_vertical_descent:.9f} "
            f"lateral_m={total_lateral:.9f} segments={len(TARGETS)}",
            flush=True,
        )
        return 0
    except Exception as error:
        result["status"] = "FAILED"
        result["error"] = f"{type(error).__name__}: {error}"
        atomic_write(result)
        print(f"EXP108_FAILED {type(error).__name__}: {error}", flush=True)
        return 1
    finally:
        del subscription
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
