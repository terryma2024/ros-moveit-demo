"""MuJoCo-owned live boundaries used by the simulator-neutral Teleop adapter."""

from __future__ import annotations

import time

import rclpy
from mujoco_ros2_control_msgs.srv import SetPause

from .client import FreeJointResetOverride, MujocoRosClient
from .observer import EvidenceStale, MujocoWorldObserver
from .reset import MujocoResetClient

CONTROLLERS = ("arm_controller", "gripper_controller")
RESET_JOINTS = (0.0,) * 6
CUP_START = (0.02, -0.28, 0.165)


def _pause_snapshot(node, observer, timeout_s: float):
    client = node.create_client(SetPause, "/mujoco_ros2_control_node/set_pause")
    if not client.wait_for_service(timeout_sec=timeout_s):
        raise RuntimeError("pause service unavailable")
    discovery_deadline = time.monotonic() + timeout_s
    while rclpy.ok() and time.monotonic() <= discovery_deadline:
        if observer.publisher_count > 0:
            break
        rclpy.spin_once(node, timeout_sec=0.01)
    else:
        raise RuntimeError("atomic evidence publisher discovery timed out")
    request = SetPause.Request()
    request.paused = True
    deadline = time.monotonic() + timeout_s
    retry_period_s = min(0.05, timeout_s / 2.0)
    next_request_s = time.monotonic()
    future = None
    pause_accepted = False
    response_received = False
    while rclpy.ok() and time.monotonic() <= deadline:
        now = time.monotonic()
        if future is None and now >= next_request_s:
            future = client.call_async(request)
            next_request_s = now + retry_period_s
        rclpy.spin_once(node, timeout_sec=0.01)
        if future is not None and future.done():
            response = future.result()
            if response is None:
                raise RuntimeError("pause snapshot request failed")
            response_received = True
            pause_accepted = pause_accepted or bool(response.success)
            future = None
        try:
            evidence = observer.snapshot()
        except EvidenceStale:
            continue
        if evidence.paused:
            return evidence
    if not response_received:
        raise RuntimeError("pause snapshot request timed out")
    if not pause_accepted:
        raise RuntimeError("pause snapshot request failed")
    raise RuntimeError("fresh paused atomic MuJoCo evidence unavailable")


def current_evidence(simulation_session_id: str, timeout_s: float = 5.0):
    """Return a fresh paused snapshot without advancing physics."""

    rclpy.init()
    node = rclpy.create_node("so101_teleop_mujoco_evidence")
    observer = MujocoWorldObserver(node, simulation_session_id, max_age_s=1.0)
    try:
        evidence = _pause_snapshot(node, observer, timeout_s)
        if evidence.simulation_session_id != simulation_session_id:
            raise RuntimeError("atomic evidence session mismatch")
        return evidence
    finally:
        node.destroy_node()
        rclpy.shutdown()


def transactional_reset(
    simulation_session_id: str,
    *,
    keyframe: str = "task_start",
    expected_object_position=CUP_START,
    free_joint_overrides: tuple[FreeJointResetOverride, ...] = (),
    timeout_s: float = 10.0,
):
    """Run the qualified controller/pause/reset/epoch transaction."""

    rclpy.init()
    service_node = rclpy.create_node("so101_teleop_mujoco_reset_services")
    joint_node = rclpy.create_node("so101_teleop_mujoco_reset_joints")
    observer_node = rclpy.create_node("so101_teleop_mujoco_reset_evidence")
    services = MujocoRosClient(service_node, joint_node, service_timeout_s=timeout_s)
    observer = MujocoWorldObserver(observer_node, simulation_session_id, max_age_s=1.0)

    def progress() -> None:
        rclpy.spin_once(observer_node, timeout_sec=0.005)
        services.progress()

    resetter = MujocoResetClient(
        services,
        observer,
        simulation_session_id=simulation_session_id,
        controller_names=CONTROLLERS,
        expected_joint_positions=RESET_JOINTS,
        expected_object_position=expected_object_position,
        timeout_s=timeout_s,
        progress=progress,
    )
    try:
        return resetter.reset(keyframe, free_joint_overrides)
    finally:
        observer_node.destroy_node()
        joint_node.destroy_node()
        service_node.destroy_node()
        rclpy.shutdown()
