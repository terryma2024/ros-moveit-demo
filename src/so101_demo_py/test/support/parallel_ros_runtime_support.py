"""Fixtures and helpers shared by the parallel ROS runtime port tests."""

from __future__ import annotations

from types import SimpleNamespace

from paths import PACKAGE_ROOT

PACKAGE = PACKAGE_ROOT


def _lease():
    return SimpleNamespace(
        batch_id="batch-1",
        coordinator_epoch=1,
        worker_id="worker-01",
        worker_generation=1,
        point_id="task_start",
        attempt_id="attempt-1",
        lease_generation=1,
    )


def _valid_worker_nodes():
    return tuple(sorted((
        "/arm_controller", "/controller_manager", "/gripper_controller",
        "/joint_state_broadcaster", "/move_group", "/move_group/moveit",
        "/move_group_private_123456", "/moveit_987654",
        "/moveit_simple_controller_manager", "/mujoco_ros2_control_node",
        "/robot_state_publisher", "/robotsystem", "/so101_base_to_camera_link",
        "/so101_camera_link_to_task_camera_frame",
        "/transform_listener_impl_7a8b9c",
    )))
