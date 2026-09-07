"""Read-only final MuJoCo and Planning Scene collection for E2E acceptance."""

from __future__ import annotations

import math
import time
from typing import Any


def _contact_mentions(contact: Any, name: str) -> bool:
    return name in {
        contact.body1,
        contact.geom1,
        contact.body2,
        contact.geom2,
    }


def _simulation_readback_document(evidence: Any) -> dict[str, object]:
    return {
        "simulation_session_id": evidence.simulation_session_id,
        "reset_epoch": evidence.reset_epoch,
        "publisher_sequence": evidence.publisher_sequence,
        "simulation_step": evidence.simulation_step,
        "source_timestamp_ns": round(evidence.simulation_time_s * 1_000_000_000),
        "paused": evidence.paused,
        "cup_pose_world": [
            *evidence.object_state.position_world,
            *evidence.object_state.orientation_xyzw,
        ],
        "cup_linear_velocity_world_m_s": list(
            evidence.object_state.linear_velocity_world
        ),
        "cup_angular_velocity_world_rad_s": list(
            evidence.object_state.angular_velocity_world
        ),
        "table_contact": any(
            _contact_mentions(contact, "table_collision")
            for contact in evidence.other_object_contacts
        ),
        "left_fingertip_contact_count": len(evidence.left_fingertip_contacts),
        "right_fingertip_contact_count": len(evidence.right_fingertip_contacts),
    }


def _pose_document(pose: Any) -> list[float]:
    return [
        float(pose.position.x),
        float(pose.position.y),
        float(pose.position.z),
        float(pose.orientation.x),
        float(pose.orientation.y),
        float(pose.orientation.z),
        float(pose.orientation.w),
    ]


def _rotate(
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


def _cup_body_pose(collision_object: Any) -> list[float] | None:
    if len(collision_object.primitives) != 13 or len(collision_object.primitive_poses) != 13:
        return None
    bottom = collision_object.primitive_poses[-1]
    bottom_pose = _pose_document(bottom)
    orientation = tuple(bottom_pose[3:])
    norm = math.sqrt(sum(value * value for value in orientation))
    if not math.isfinite(norm) or norm <= 0.0:
        return None
    orientation = tuple(value / norm for value in orientation)
    offset = _rotate(orientation, (0.0, 0.0, 0.044))
    return [
        bottom_pose[0] + offset[0],
        bottom_pose[1] + offset[1],
        bottom_pose[2] + offset[2],
        *orientation,
    ]


def _planning_scene_readback_document(
    scene: Any,
    *,
    session_id: str,
    reset_epoch: int,
    source_timestamp_ns: int,
) -> dict[str, object]:
    attached = [
        item.object.id for item in scene.robot_state.attached_collision_objects
    ]
    world_objects: dict[str, object] = {}
    for item in scene.world.collision_objects:
        record: dict[str, object] = {"primitive_count": len(item.primitives)}
        if item.id == "plastic_cup":
            record["pose_xyz_xyzw"] = _cup_body_pose(item)
        world_objects[item.id] = record
    return {
        "simulation_session_id": session_id,
        "reset_epoch": reset_epoch,
        "source_timestamp_ns": source_timestamp_ns,
        "attached_object_ids": attached,
        "world_objects": world_objects,
    }


def _collect_readback(
    *,
    node: Any,
    observer: Any,
    scene_client: Any,
    scene_request: Any,
    session_id: str,
    reset_epoch: int,
    timeout_s: float,
    spin_once: Any,
    stale_error: type[Exception],
    monotonic: Any = time.monotonic,
) -> dict[str, object]:
    deadline = monotonic() + timeout_s
    evidence = None
    while monotonic() < deadline:
        spin_once(0.05)
        try:
            candidate = observer.snapshot()
        except stale_error:
            continue
        if candidate.reset_epoch == reset_epoch and not candidate.paused:
            evidence = candidate
            break
    if evidence is None:
        raise TimeoutError("fresh MuJoCo final evidence was not available")
    remaining = deadline - monotonic()
    if remaining <= 0.0 or not scene_client.wait_for_service(timeout_sec=remaining):
        raise TimeoutError("Planning Scene readback service was not available")
    future = scene_client.call_async(scene_request)
    while not future.done() and monotonic() < deadline:
        spin_once(0.05)
    if not future.done() or future.result() is None:
        raise TimeoutError("Planning Scene final readback timed out")
    source_timestamp_ns = int(node.get_clock().now().nanoseconds)
    return {
        "mujoco_final": _simulation_readback_document(evidence),
        "planning_scene_final": _planning_scene_readback_document(
            future.result().scene,
            session_id=session_id,
            reset_epoch=reset_epoch,
            source_timestamp_ns=source_timestamp_ns,
        ),
    }


def collect_final_readback(
    *,
    session_id: str,
    reset_epoch: int,
    timeout_s: float,
) -> dict[str, object]:
    """Collect fresh final facts without publishing or mutating either source."""

    if not session_id or type(reset_epoch) is not int or reset_epoch < 0:
        raise ValueError("readback identity is invalid")
    if not math.isfinite(timeout_s) or timeout_s <= 0.0:
        raise ValueError("readback timeout must be finite and positive")

    import rclpy
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import GetPlanningScene

    from so101_demo.backends.mujoco.observer import EvidenceStale, MujocoWorldObserver

    initialized_here = not rclpy.ok()
    node = None
    if initialized_here:
        rclpy.init()
    try:
        node = rclpy.create_node(
            "so101_e2e_acceptance_readback",
            start_parameter_services=False,
            enable_rosout=False,
        )
        observer = MujocoWorldObserver(node, session_id, max_age_s=min(timeout_s, 0.5))
        client = node.create_client(GetPlanningScene, "/get_planning_scene")
        request = GetPlanningScene.Request()
        request.components.components = (
            PlanningSceneComponents.WORLD_OBJECT_NAMES
            | PlanningSceneComponents.WORLD_OBJECT_GEOMETRY
            | PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        )
        return _collect_readback(
            node=node,
            observer=observer,
            scene_client=client,
            scene_request=request,
            session_id=session_id,
            reset_epoch=reset_epoch,
            timeout_s=timeout_s,
            spin_once=lambda seconds: rclpy.spin_once(
                node, timeout_sec=seconds
            ),
            stale_error=EvidenceStale,
        )
    finally:
        if node is not None:
            node.destroy_node()
        if initialized_here and rclpy.ok():
            rclpy.try_shutdown()
