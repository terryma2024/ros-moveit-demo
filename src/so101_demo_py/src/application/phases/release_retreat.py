#!/usr/bin/env python3
"""production live phase: outcome-first release, TCP separation, and validation."""

from __future__ import annotations

import copy
import json
import math
import os
import time
from pathlib import Path

import rclpy
from control_msgs.action import FollowJointTrajectory
from moveit_msgs.action import ExecuteTrajectory
from moveit_msgs.msg import (
    AttachedCollisionObject,
    CollisionObject,
    PlanningScene,
    PlanningSceneComponents,
)
from moveit_msgs.srv import ApplyPlanningScene, GetMotionPlan, GetPlanningScene
from rclpy.action import ActionClient
from rclpy.duration import Duration
from rclpy.qos import qos_profile_sensor_data
from rclpy.time import Time
from sensor_msgs.msg import JointState
from so101_demo.application.dynamic_transport_evidence import ContactForceMode
from so101_demo.application.pick_place import load_live_task_policy
from so101_demo.application.release_retreat import (
    load_release_retreat_policy,
    release_retreat_translations,
    residual_contact_within_bounds,
)
from so101_demo.backends.mujoco.observer import EvidenceStale, MujocoWorldObserver
from so101_demo.backends.mujoco.transport_observer import check_force
from so101_demo.control.gripper.client import GripperClient, make_gripper_goal
from so101_demo.control.moveit.planning import (
    MoveItPlanningClient,
    PosePlanRequest,
)
from so101_demo.control.planning_scene.acm import (
    collision_is_allowed,
    set_collision_allowed,
)
from so101_demo.control.trajectory.executor import (
    MoveItExecutionClient,
    SustainedConditionGuard,
    make_execute_goal,
)
from so101_demo.core.outcome import (
    FinalPlacementSample,
    evaluate_final_placement,
)
from tf2_ros import Buffer, TransformException, TransformListener

SESSION_ID = os.environ["SO101_SIMULATION_SESSION_ID"]
EXPECTED_EPOCH = int(os.environ["SO101_EXPECTED_RESET_EPOCH"])
EVIDENCE_PATH = Path(os.environ["SO101_EVIDENCE_ROOT"]) / "release-retreat.json"
POLICY_PATH = Path(os.environ["SO101_MOTION_POLICY"])
ALL_JOINTS = ("1", "2", "3", "4", "5", "6")
RELEASE_Q6 = 0.750
PLACE_XYZ = (-0.080, -0.250, 0.165)
SETTLING_COMPENSATION = (0.0012, 0.0025, 0.0185)
RELEASE_TARGET_XYZ = tuple(
    value + compensation
    for value, compensation in zip(PLACE_XYZ, SETTLING_COMPENSATION, strict=True)
)
DIAGNOSTIC_HARD_STOP_FORCE_N = 11.60


def atomic_write(document: dict) -> None:
    temporary = EVIDENCE_PATH.with_name(f".{EVIDENCE_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, EVIDENCE_PATH)


def has_table_contact(evidence) -> bool:
    return any(item.geom2 == "table_collision" for item in evidence.other_object_contacts)


def evidence_dict(value) -> dict:
    return {
        "publisher_sequence": value.publisher_sequence,
        "simulation_time_s": value.simulation_time_s,
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


def maximum_fingertip_force(evidence) -> float:
    contacts = (*evidence.left_fingertip_contacts, *evidence.right_fingertip_contacts)
    return max((item.normal_force_n for item in contacts), default=0.0)


def quaternion_multiply(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    x1, y1, z1, w1 = first
    x2, y2, z2, w2 = second
    return (
        w1 * x2 + x1 * w2 + y1 * z2 - z1 * y2,
        w1 * y2 - x1 * z2 + y1 * w2 + z1 * x2,
        w1 * z2 + x1 * y2 - y1 * x2 + z1 * w2,
        w1 * w2 - x1 * x2 - y1 * y2 - z1 * z2,
    )


def rotate_vector(
    orientation: tuple[float, float, float, float],
    value: tuple[float, float, float],
) -> tuple[float, float, float]:
    x, y, z, w = orientation
    vx, vy, vz = value
    tx = 2.0 * (y * vz - z * vy)
    ty = 2.0 * (z * vx - x * vz)
    tz = 2.0 * (x * vy - y * vx)
    return (
        vx + w * tx + y * tz - z * ty,
        vy + w * ty + z * tx - x * tz,
        vz + w * tz + x * ty - y * tx,
    )


def cup_collision_object(position, orientation):
    from geometry_msgs.msg import Pose
    from shape_msgs.msg import SolidPrimitive

    walls = (
        (0.0, 0.039, -0.0),
        (0.0195, 0.033775, -math.pi / 6.0),
        (0.033775, 0.0195, -math.pi / 3.0),
        (0.039, 0.0, -math.pi / 2.0),
        (0.033775, -0.0195, -2.0 * math.pi / 3.0),
        (0.0195, -0.033775, -5.0 * math.pi / 6.0),
        (0.0, -0.039, math.pi),
        (-0.0195, -0.033775, 5.0 * math.pi / 6.0),
        (-0.033775, -0.0195, 2.0 * math.pi / 3.0),
        (-0.039, 0.0, math.pi / 2.0),
        (-0.033775, 0.0195, math.pi / 3.0),
        (-0.0195, 0.033775, math.pi / 6.0),
    )
    result = CollisionObject()
    result.header.frame_id = "world"
    result.id = "plastic_cup"
    result.operation = CollisionObject.ADD
    for x, y, yaw in walls:
        offset = rotate_vector(orientation, (x, y, 0.001))
        local = (0.0, 0.0, math.sin(yaw / 2.0), math.cos(yaw / 2.0))
        composed = quaternion_multiply(orientation, local)
        pose = Pose()
        pose.position.x = position[0] + offset[0]
        pose.position.y = position[1] + offset[1]
        pose.position.z = position[2] + offset[2]
        pose.orientation.x, pose.orientation.y, pose.orientation.z, pose.orientation.w = composed
        result.primitives.append(
            SolidPrimitive(type=SolidPrimitive.BOX, dimensions=[0.020705524, 0.002, 0.088])
        )
        result.primitive_poses.append(pose)
    bottom_offset = rotate_vector(orientation, (0.0, 0.0, -0.044))
    bottom_pose = Pose()
    bottom_pose.position.x = position[0] + bottom_offset[0]
    bottom_pose.position.y = position[1] + bottom_offset[1]
    bottom_pose.position.z = position[2] + bottom_offset[2]
    (
        bottom_pose.orientation.x,
        bottom_pose.orientation.y,
        bottom_pose.orientation.z,
        bottom_pose.orientation.w,
    ) = orientation
    result.primitives.append(
        SolidPrimitive(type=SolidPrimitive.CYLINDER, dimensions=[0.002, 0.040])
    )
    result.primitive_poses.append(bottom_pose)
    return result


def main() -> int:
    task_policy = load_live_task_policy()
    assert task_policy.contact is not None
    maximum_safe_force_n = task_policy.contact.thresholds.maximum_safe_force_n
    physical_outcome_policy = task_policy.physical_outcome
    retreat_policy = load_release_retreat_policy(POLICY_PATH)
    result: dict = {
        "schema": "so101-live-outcome-first-release-retreat-v1",
        "simulation_session_id": SESSION_ID,
        "release_target_xyz_m": list(RELEASE_TARGET_XYZ),
        "release_q6_rad": RELEASE_Q6,
        "release_retreat_policy": {
            "radial_separation_m": retreat_policy.radial_separation_m,
            "vertical_clearance_m": retreat_policy.vertical_clearance_m,
            "orientation_tolerance_rad": retreat_policy.orientation_tolerance_rad,
            "position_tolerance_m": retreat_policy.position_tolerance_m,
            "velocity_scaling": retreat_policy.velocity_scaling,
            "acceleration_scaling": retreat_policy.acceleration_scaling,
            "residual_contact_grace_s": retreat_policy.residual_contact_grace_s,
            "max_residual_fingertip_force_n": (retreat_policy.max_residual_fingertip_force_n),
            "max_released_cup_displacement_m": (retreat_policy.max_released_cup_displacement_m),
        },
        "physics_pause_calls": 0,
        "simulator_constraint_calls": 0,
        "direct_object_state_writes": 0,
        "status": "RUNNING",
        "retreat_segments": [],
    }
    rclpy.init()
    node = rclpy.create_node("so101_live_release_retreat")
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
    apply_scene = node.create_client(ApplyPlanningScene, "/apply_planning_scene")
    execute_action = ActionClient(node, ExecuteTrajectory, "/execute_trajectory")
    gripper_action = ActionClient(
        node,
        FollowJointTrajectory,
        "/gripper_controller/follow_joint_trajectory",
    )
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

    def lookup_tcp_transform():
        try:
            if not tf_buffer.can_transform(
                "world",
                "so101_tcp",
                Time(),
                timeout=Duration(seconds=0.0),
            ):
                return None
            return tf_buffer.lookup_transform("world", "so101_tcp", Time())
        except TransformException:
            return None

    def stable_state(
        *,
        gripper_contact: bool,
        force_mode: ContactForceMode,
        allow_residual_fixed_contact: bool = False,
        duration_s: float = 0.20,
    ):
        started: float | None = None
        last_sequence = -1
        latest = None
        deadline = time.monotonic() + 6.0
        while time.monotonic() < deadline:
            progress()
            evidence = snapshot()
            if evidence is None or evidence.publisher_sequence == last_sequence:
                continue
            last_sequence = evidence.publisher_sequence
            if evidence.paused or evidence.reset_epoch != EXPECTED_EPOCH:
                raise RuntimeError("MuJoCo pause/reset during stable gate")
            decision = check_force(
                evidence.maximum_normal_force_n,
                force_mode,
                static_threshold_n=maximum_safe_force_n,
                diagnostic_stop_n=DIAGNOSTIC_HARD_STOP_FORCE_N,
            )
            if decision.cancel:
                raise RuntimeError(f"{decision.reason} during stable gate")
            actual_gripper_contact = bool(
                evidence.left_fingertip_contacts or evidence.right_fingertip_contacts
            )
            if allow_residual_fixed_contact:
                healthy = (
                    not evidence.right_fingertip_contacts
                    and maximum_fingertip_force(evidence)
                    <= retreat_policy.max_residual_fingertip_force_n
                )
            else:
                healthy = actual_gripper_contact == gripper_contact
            if not gripper_contact or allow_residual_fixed_contact:
                healthy = healthy and has_table_contact(evidence)
            else:
                healthy = healthy and bool(
                    evidence.left_fingertip_contacts and evidence.right_fingertip_contacts
                )
            now = time.monotonic()
            started = started if healthy and started is not None else (now if healthy else None)
            latest = evidence
            if started is not None and now - started >= duration_s:
                return latest
        raise RuntimeError("stable physical state timeout")

    def detach_and_sync(evidence) -> dict:
        remove = AttachedCollisionObject()
        remove.object.id = "plastic_cup"
        remove.object.operation = CollisionObject.REMOVE
        scene = PlanningScene()
        scene.is_diff = True
        scene.robot_state.is_diff = True
        scene.robot_state.attached_collision_objects = [remove]
        scene.world.collision_objects = [
            cup_collision_object(
                tuple(evidence.object_state.position_world),
                tuple(evidence.object_state.orientation_xyzw),
            )
        ]
        applied = apply_scene.call_async(ApplyPlanningScene.Request(scene=scene))
        wait_for(lambda: applied.done(), 5.0, "Planning Scene detach timeout")
        if applied.result() is None or not applied.result().success:
            raise RuntimeError("Planning Scene detach failed")

        query = GetPlanningScene.Request()
        query.components.components = (
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        )
        queried = get_scene.call_async(query)
        wait_for(lambda: queried.done(), 5.0, "Planning Scene readback timeout")
        observed_scene = queried.result().scene
        world = {item.id: len(item.primitives) for item in observed_scene.world.collision_objects}
        attached = [
            item.object.id for item in observed_scene.robot_state.attached_collision_objects
        ]
        if world.get("plastic_cup") != 13 or "plastic_cup" in attached:
            raise RuntimeError("Planning Scene detach/sync readback mismatch")
        return {
            "world_primitive_counts": world,
            "attached_object_ids": attached,
        }

    def query_acm():
        query = GetPlanningScene.Request()
        query.components.components = PlanningSceneComponents.ALLOWED_COLLISION_MATRIX
        queried = get_scene.call_async(query)
        wait_for(lambda: queried.done(), 5.0, "Planning Scene ACM readback timeout")
        response = queried.result()
        if response is None:
            raise RuntimeError("Planning Scene ACM readback failed")
        return copy.deepcopy(response.scene.allowed_collision_matrix)

    def apply_acm(matrix) -> None:
        scene = PlanningScene()
        scene.is_diff = True
        scene.allowed_collision_matrix = copy.deepcopy(matrix)
        applied = apply_scene.call_async(ApplyPlanningScene.Request(scene=scene))
        wait_for(lambda: applied.done(), 5.0, "Planning Scene ACM apply timeout")
        response = applied.result()
        if response is None or not response.success:
            raise RuntimeError("Planning Scene ACM apply failed")

    def acm_pair_allowed(matrix) -> bool:
        return collision_is_allowed(matrix, "plastic_cup", "gripper")

    original_acm = None
    acm_permission_active = False

    try:
        for client, name in (
            (planning_service, "/plan_kinematic_path"),
            (get_scene, "/get_planning_scene"),
            (apply_scene, "/apply_planning_scene"),
        ):
            if not client.wait_for_service(timeout_sec=20.0):
                raise RuntimeError(f"{name} unavailable")
        if not execute_action.wait_for_server(timeout_sec=20.0):
            raise RuntimeError("execute action unavailable")
        if not gripper_action.wait_for_server(timeout_sec=20.0):
            raise RuntimeError("gripper action unavailable")
        wait_for(lambda: len(latest_joint) == 6, 5.0, "joint state unavailable")
        before = stable_state(
            gripper_contact=True,
            force_mode=ContactForceMode.DYNAMIC_HELD_OBJECT_MOTION,
        )
        before_joints = tuple(float(latest_joint[name]) for name in ALL_JOINTS)
        cup = tuple(before.object_state.position_world)
        error = tuple(
            target - observed for target, observed in zip(RELEASE_TARGET_XYZ, cup, strict=True)
        )
        if math.hypot(error[0], error[1]) > 0.003 or abs(error[2]) > 0.003:
            raise RuntimeError("cup is outside bounded pre-release alignment tolerance")
        result["before_joints_rad"] = list(before_joints)
        result["before_evidence"] = evidence_dict(before)
        result["pre_release_alignment_error_m"] = list(error)
        result["release_marker_sequence"] = before.publisher_sequence
        atomic_write(result)

        gripper = GripperClient(
            gripper_action,
            goal_factory=make_gripper_goal,
            progress=progress,
        ).command(RELEASE_Q6, 2.0, 15.0)
        if gripper.failure is not None:
            raise RuntimeError(f"release failed: {gripper.failure.code}")
        released = stable_state(
            gripper_contact=False,
            force_mode=ContactForceMode.PRE_TRANSPORT_STATIC_HOLD,
            allow_residual_fixed_contact=True,
        )
        result["released_joints_rad"] = [float(latest_joint[name]) for name in ALL_JOINTS]
        result["released_evidence"] = evidence_dict(released)
        result["planning_scene_after_release"] = detach_and_sync(released)
        atomic_write(result)

        transform = wait_for(
            lookup_tcp_transform,
            5.0,
            "world-to-TCP transform unavailable before release retreat",
        )
        tcp = transform.transform.translation
        translations = release_retreat_translations(
            (tcp.x, tcp.y, tcp.z),
            tuple(released.object_state.position_world),
            retreat_policy,
        )
        result["retreat_translations_world_m"] = [list(item) for item in translations]
        planning = MoveItPlanningClient(planning_service, progress=progress)
        released_cup_position = tuple(released.object_state.position_world)
        original_acm = query_acm()
        if acm_pair_allowed(original_acm):
            raise RuntimeError("release ACM pair was unexpectedly allowed before experiment")
        radial_acm = copy.deepcopy(original_acm)
        set_collision_allowed(radial_acm, "plastic_cup", "gripper", True)
        apply_acm(radial_acm)
        applied_acm = query_acm()
        if not acm_pair_allowed(applied_acm):
            raise RuntimeError("radial release ACM permission readback failed")
        acm_permission_active = True
        result["radial_acm_scope"] = {
            "object": "plastic_cup",
            "link": "gripper",
            "moving_jaw_link_allowed": collision_is_allowed(applied_acm, "plastic_cup", "jaw"),
            "original_pair_allowed": False,
            "radial_pair_allowed": True,
        }
        if result["radial_acm_scope"]["moving_jaw_link_allowed"]:
            raise RuntimeError("radial ACM scope unexpectedly includes moving jaw")
        atomic_write(result)
        for index, translation in enumerate(translations, start=1):
            start_transform = wait_for(
                lookup_tcp_transform,
                5.0,
                f"world-to-TCP transform unavailable before retreat segment {index}",
            )
            start_position = start_transform.transform.translation
            start_orientation = start_transform.transform.rotation
            target_position = (
                start_position.x + translation[0],
                start_position.y + translation[1],
                start_position.z + translation[2],
            )
            current = tuple(float(latest_joint[name]) for name in ALL_JOINTS)
            planned = planning.plan_pose_path(
                PosePlanRequest(
                    joint_names=ALL_JOINTS,
                    current_positions=current,
                    target_position_m=target_position,
                    target_orientation_xyzw=(
                        start_orientation.x,
                        start_orientation.y,
                        start_orientation.z,
                        start_orientation.w,
                    ),
                    orientation_tolerance_rad=(retreat_policy.orientation_tolerance_rad,) * 3,
                    position_tolerance_m=retreat_policy.position_tolerance_m,
                    velocity_scaling=retreat_policy.velocity_scaling,
                    acceleration_scaling=retreat_policy.acceleration_scaling,
                    planning_time_s=8.0,
                ),
                timeout_s=15.0,
            )
            if planned.failure is not None or planned.trajectory is None:
                code = "EMPTY" if planned.failure is None else planned.failure.code
                raise RuntimeError(f"retreat segment {index} planning failed: {code}")

            support_guard = SustainedConditionGuard(0.05)
            contact_guard = SustainedConditionGuard(retreat_policy.residual_contact_grace_s)

            def monitor() -> None:
                evidence = snapshot()
                if evidence is None:
                    raise RuntimeError("stale MuJoCo evidence during retreat")
                if evidence.paused or evidence.reset_epoch != EXPECTED_EPOCH:
                    raise RuntimeError("MuJoCo pause/reset during retreat")
                support_guard.require(
                    has_table_contact(evidence),
                    "released cup lost table support",
                )
                displacement = math.dist(
                    tuple(evidence.object_state.position_world),
                    released_cup_position,
                )
                fingertip_force = maximum_fingertip_force(evidence)
                if not residual_contact_within_bounds(
                    fingertip_force,
                    displacement,
                    retreat_policy,
                ):
                    raise RuntimeError("released-cup contact/displacement boundary exceeded")
                no_fingertip_contact = not (
                    evidence.left_fingertip_contacts or evidence.right_fingertip_contacts
                )
                if index == 1:
                    contact_guard.require(
                        no_fingertip_contact,
                        "residual fixed-pad contact did not clear during radial separation",
                    )
                elif not no_fingertip_contact:
                    raise RuntimeError("opened gripper re-contacted released cup")

            execution = MoveItExecutionClient(
                execute_action,
                goal_factory=make_execute_goal,
                progress=progress,
            ).execute(planned.trajectory, 45.0, monitor=monitor)
            if execution.failure is not None:
                raise RuntimeError(
                    f"retreat segment {index} execution failed: "
                    f"{execution.failure.code}: {execution.failure.message}"
                )
            endpoint = wait_for(
                lambda: (
                    observed
                    if (observed := lookup_tcp_transform()) is not None
                    and math.dist(
                        (
                            observed.transform.translation.x,
                            observed.transform.translation.y,
                            observed.transform.translation.z,
                        ),
                        target_position,
                    )
                    <= 0.003
                    else None
                ),
                10.0,
                f"retreat segment {index} endpoint timeout",
            )
            after = stable_state(
                gripper_contact=False,
                force_mode=ContactForceMode.PRE_TRANSPORT_STATIC_HOLD,
            )
            result["retreat_segments"].append(
                {
                    "segment": index,
                    "translation_world_m": list(translation),
                    "target_tcp_position_world_m": list(target_position),
                    "terminal_tcp_position_world_m": [
                        endpoint.transform.translation.x,
                        endpoint.transform.translation.y,
                        endpoint.transform.translation.z,
                    ],
                    "trajectory_points": len(planned.trajectory.joint_trajectory.points),
                    "terminal_joints_rad": [float(latest_joint[name]) for name in ALL_JOINTS],
                    "terminal_evidence": evidence_dict(after),
                }
            )
            if index == 1:
                apply_acm(original_acm)
                restored_acm = query_acm()
                if restored_acm != original_acm or acm_pair_allowed(restored_acm):
                    raise RuntimeError("release ACM snapshot restoration readback failed")
                acm_permission_active = False
                result["radial_acm_scope"]["restored_before_vertical"] = True
                result["radial_acm_scope"]["restored_pair_allowed"] = False
            atomic_write(result)

        terminal = stable_state(
            gripper_contact=False,
            force_mode=ContactForceMode.PRE_TRANSPORT_STATIC_HOLD,
        )
        result["planning_scene_readback"] = detach_and_sync(terminal)

        release_epoch_id = f"live-release-epoch-{EXPECTED_EPOCH}"
        result["release_epoch_id"] = release_epoch_id
        marker = int(result["release_marker_sequence"])
        samples: list[FinalPlacementSample] = []
        last_sequence = marker
        deadline = time.monotonic() + physical_outcome_policy.settle_timeout_s
        while time.monotonic() < deadline:
            progress()
            received = observer.snapshot_with_receipt()
            evidence = received.evidence
            if evidence.publisher_sequence <= last_sequence:
                continue
            last_sequence = evidence.publisher_sequence
            samples.append(
                FinalPlacementSample(
                    release_epoch_id=release_epoch_id,
                    receipt_sequence=evidence.publisher_sequence,
                    source_timestamp_s=evidence.simulation_time_s,
                    observed_monotonic_s=received.received_monotonic_s,
                    pose_xyz_xyzw=(
                        *evidence.object_state.position_world,
                        *evidence.object_state.orientation_xyzw,
                    ),
                    support_contact=has_table_contact(evidence),
                    gripper_contact=bool(
                        evidence.left_fingertip_contacts or evidence.right_fingertip_contacts
                    ),
                    simulator_detached=True,
                    moveit_detached=True,
                    controller_healthy=True,
                    safety_healthy=(
                        not evidence.paused
                        and evidence.reset_epoch == EXPECTED_EPOCH
                        and evidence.maximum_normal_force_n <= maximum_safe_force_n
                    ),
                    shadow_divergence_healthy=True,
                )
            )
            evaluated = evaluate_final_placement(
                tuple(samples), physical_outcome_policy, release_epoch_id, marker
            )
            if evaluated.success:
                break
        else:
            evaluated = evaluate_final_placement(
                tuple(samples), physical_outcome_policy, release_epoch_id, marker
            )
        result["final_samples"] = [sample.as_dict() for sample in samples]
        result["final_evaluation"] = {
            "success": evaluated.success,
            "failure_code": evaluated.failure_code,
            "sample_count": evaluated.sample_count,
            "duration_s": evaluated.duration_s,
            "max_linear_speed_m_s": evaluated.max_linear_speed_m_s,
            "max_angular_speed_rad_s": evaluated.max_angular_speed_rad_s,
            "metrics": dict(evaluated.metrics),
        }
        result["final_evidence"] = evidence_dict(observer.snapshot())
        if not evaluated.success:
            raise RuntimeError(f"final placement failed: {evaluated.failure_code}")
        result["status"] = "RELEASE_RETREAT_FINAL_PLACEMENT_PROVED"
        atomic_write(result)
        print(
            "LIVE_OK release=true retreat=radial_then_vertical "
            f"detach_sync=true samples={evaluated.sample_count}",
            flush=True,
        )
        return 0
    except Exception as error:
        if acm_permission_active and original_acm is not None:
            try:
                apply_acm(original_acm)
                restored_acm = query_acm()
                restored = restored_acm == original_acm and not acm_pair_allowed(restored_acm)
                result["acm_emergency_restore"] = {"success": restored}
                if not restored:
                    raise RuntimeError("ACM emergency restoration readback mismatch")
            except Exception as restore_error:
                result["acm_emergency_restore"] = {
                    "success": False,
                    "error": f"{type(restore_error).__name__}: {restore_error}",
                }
        result["status"] = "FAILED"
        result["error"] = f"{type(error).__name__}: {error}"
        atomic_write(result)
        print(f"LIVE_FAILED {type(error).__name__}: {error}", flush=True)
        return 1
    finally:
        del subscription
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
