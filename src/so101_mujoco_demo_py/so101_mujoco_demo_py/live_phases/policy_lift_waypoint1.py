#!/usr/bin/env python3
"""production live phase: execute the first formal LIFT waypoint."""

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
EVIDENCE_PATH = Path(os.environ["SO101_EVIDENCE_ROOT"]) / "policy-lift-waypoint1.json"
ARM_JOINTS = ("1", "2", "3", "4", "5")
ALL_JOINTS = (*ARM_JOINTS, "6")
LIFT_TARGET = (
    -0.000284124852,
    0.381814591288,
    0.272246878070,
    0.916741182602,
    -0.000291565154,
)
MIN_PHYSICAL_LIFT_M = 0.005
MAX_PHYSICAL_LIFT_M = 0.10
MAX_LATERAL_DISPLACEMENT_M = 0.03
PREVIOUS_ARM_TARGET = (
    -0.00025046805641095214,
    0.4631330095326603,
    0.21318348538670218,
    0.8649578444936947,
    0.0005864330989807919,
)
PRELOAD_Q6 = -0.04850881987104013


def write_result(result: dict) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = EVIDENCE_PATH.with_name(f".{EVIDENCE_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    result = {
        "schema": "so101-live-noslip-policy-lift-waypoint1-v1",
        "simulation_session_id": SESSION_ID,
        "lift_target_arm_rad": list(LIFT_TARGET),
        "physics_pause_calls": 0,
        "simulator_constraint_calls": 0,
        "direct_object_state_writes": 0,
        "status": "RUNNING",
    }
    rclpy.init()
    node = rclpy.create_node("so101_live_policy_lift_waypoint1")
    latest_joint: dict[str, float] = {}

    def joint_callback(message: JointState) -> None:
        if len(message.name) == len(message.position):
            latest_joint.update(zip(message.name, message.position, strict=True))

    subscription = node.create_subscription(
        JointState, "/joint_states", joint_callback, qos_profile_sensor_data
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

    def stable_bilateral(epoch: int, duration_s: float = 0.30):
        start: float | None = None
        last_sequence = -1
        samples: list[dict] = []
        deadline = time.monotonic() + 5.0
        latest = None
        while time.monotonic() < deadline:
            progress()
            evidence = snapshot()
            if evidence is None or evidence.publisher_sequence == last_sequence:
                continue
            last_sequence = evidence.publisher_sequence
            if evidence.paused or evidence.reset_epoch != epoch:
                raise RuntimeError("MuJoCo pause/reset during bilateral gate")
            if evidence.maximum_normal_force_n > maximum_safe_force_n:
                raise RuntimeError("force boundary exceeded during bilateral gate")
            bilateral = bool(evidence.left_fingertip_contacts and evidence.right_fingertip_contacts)
            now = time.monotonic()
            start = start if bilateral and start is not None else (now if bilateral else None)
            samples.append(evidence_dict(evidence))
            samples = samples[-50:]
            latest = evidence
            if start is not None and now - start >= duration_s:
                return latest, samples
        raise RuntimeError("stable bilateral fingertip contact timeout")

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
        if (
            maximum_joint_error(
                start_positions[:5],
                PREVIOUS_ARM_TARGET,
            )
            > 0.01
        ):
            raise RuntimeError("robot is not at the verified EXP-081 arm endpoint")
        if abs(start_positions[-1] - PRELOAD_Q6) > 0.01:
            raise RuntimeError("gripper is not holding the verified seating preload")
        contact_evidence, pre_lift_samples = stable_bilateral(before.reset_epoch)
        result["before_micro_lift_joints_rad"] = list(start_positions)
        result["before_micro_lift_evidence"] = evidence_dict(contact_evidence)
        result["pre_lift_bilateral_samples"] = pre_lift_samples
        write_result(result)

        def attached_readback():
            query = GetPlanningScene.Request()
            query.components.components = (
                PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
                | PlanningSceneComponents.WORLD_OBJECT_NAMES
            )
            queried = get_scene.call_async(query)
            wait_for(lambda: queried.done(), 3.0, "MoveIt attach readback timeout")
            response = queried.result()
            if response is None:
                return None
            attached_ids = [
                item.object.id for item in response.scene.robot_state.attached_collision_objects
            ]
            world_ids = [item.id for item in response.scene.world.collision_objects]
            return attached_ids, world_ids

        def attached_converged():
            observed = attached_readback()
            return observed if "plastic_cup" in observed[0] else None

        attached_ids, world_ids = wait_for(
            attached_converged,
            5.0,
            "MoveIt attached object did not converge",
        )
        result["moveit_attached_ids_before_incremental_lift"] = attached_ids
        result["moveit_world_ids_before_incremental_lift"] = world_ids
        write_result(result)

        current = tuple(float(latest_joint[name]) for name in ALL_JOINTS)
        planning = MoveItPlanningClient(
            planning_service,
            request_factory=make_get_motion_plan_request,
            progress=progress,
        )
        planned = planning.plan_joint_path(
            JointPlanRequest(
                joint_names=ARM_JOINTS,
                current_positions=current[:5],
                target_positions=LIFT_TARGET,
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
            raise RuntimeError(f"LIFT planning failed: {code}")
        points = planned.trajectory.joint_trajectory.points
        result["lift_trajectory_points"] = len(points)
        trajectory_start = tuple(float(value) for value in points[0].positions)
        handoff = tuple(float(latest_joint[name]) for name in ARM_JOINTS)
        drift = maximum_joint_error(handoff, trajectory_start)
        result["plan_to_execute_drift_rad"] = drift
        if drift > 0.01:
            raise RuntimeError("LIFT plan-to-execute drift exceeded")

        lift_start = snapshot()
        if lift_start is None:
            raise RuntimeError("fresh lift-start evidence unavailable")

        def monitor() -> None:
            evidence = snapshot()
            if evidence is None:
                raise RuntimeError("stale MuJoCo evidence during LIFT")
            if evidence.paused or evidence.reset_epoch != before.reset_epoch:
                raise RuntimeError("MuJoCo pause/reset during LIFT")
            if evidence.maximum_normal_force_n > maximum_safe_force_n:
                raise RuntimeError("force boundary exceeded during LIFT")
            if not (evidence.left_fingertip_contacts and evidence.right_fingertip_contacts):
                raise RuntimeError("bilateral fingertip contact lost during policy LIFT")

        execution = MoveItExecutionClient(
            execute_action,
            goal_factory=make_execute_goal,
            progress=progress,
        ).execute(planned.trajectory, 45.0, monitor=monitor)
        if execution.failure is not None:
            raise RuntimeError(f"LIFT execution failed: {execution.failure.code}")
        wait_for(
            lambda: (
                tuple(float(latest_joint[name]) for name in ARM_JOINTS)
                if maximum_joint_error(
                    tuple(float(latest_joint[name]) for name in ARM_JOINTS), LIFT_TARGET
                )
                <= 0.01
                else None
            ),
            10.0,
            "LIFT endpoint convergence timeout",
        )
        after, hold_samples = stable_bilateral(before.reset_epoch, duration_s=0.30)
        displacement = tuple(
            actual - initial
            for actual, initial in zip(
                after.object_state.position_world,
                lift_start.object_state.position_world,
                strict=True,
            )
        )
        lateral = math.hypot(displacement[0], displacement[1])
        cup_lift_m = displacement[2]
        if not MIN_PHYSICAL_LIFT_M <= cup_lift_m <= MAX_PHYSICAL_LIFT_M:
            raise RuntimeError(f"physical policy lift outside gate: {cup_lift_m}")
        if lateral > MAX_LATERAL_DISPLACEMENT_M:
            raise RuntimeError(f"physical lateral displacement outside gate: {lateral}")
        if "table_collision" in evidence_dict(after)["other_contact_geoms"]:
            raise RuntimeError("cup remains table-supported after policy LIFT waypoint 1")
        result["after_micro_lift_joints_rad"] = [float(latest_joint[name]) for name in ALL_JOINTS]
        result["after_micro_lift_evidence"] = evidence_dict(after)
        result["post_lift_bilateral_samples"] = hold_samples
        result["cup_displacement_m"] = list(displacement)
        result["physical_micro_lift_m"] = cup_lift_m
        result["physical_lateral_drift_m"] = lateral
        result["status"] = "POLICY_LIFT_WAYPOINT1_PHYSICAL_TRANSFER_PROVED"
        write_result(result)
        print(
            f"EXP104_OK lift_m={cup_lift_m:.9f} lateral_m={lateral:.9f} "
            f"left={len(after.left_fingertip_contacts)} right={len(after.right_fingertip_contacts)}",
            flush=True,
        )
        return 0
    except Exception as error:
        result["status"] = "FAILED"
        result["error"] = f"{type(error).__name__}: {error}"
        write_result(result)
        print(f"EXP104_FAILED {type(error).__name__}: {error}", flush=True)
        return 1
    finally:
        del subscription
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
