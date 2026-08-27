"""Pinned ROS 2 service and joint-state client for MuJoCo reset transactions."""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass
from typing import Any

import rclpy
from controller_manager_msgs.srv import ListControllers, SwitchController
from mujoco_ros2_control_msgs.msg import FreeJointState
from mujoco_ros2_control_msgs.srv import ResetWorld, SetPause
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState


class MujocoServiceError(RuntimeError):
    """Raised when a pinned ROS interface is unavailable or returns failure."""


@dataclass(frozen=True, slots=True)
class FreeJointResetOverride:
    """Validated simulator-neutral free-joint pose applied during reset."""

    name: str
    position_world_m: tuple[float, float, float]
    orientation_xyzw: tuple[float, float, float, float] = (0.0, 0.0, 0.0, 1.0)

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name or self.name != self.name.strip():
            raise ValueError("free joint override name must be non-empty and trimmed")
        if len(self.position_world_m) != 3 or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in self.position_world_m
        ):
            raise ValueError("free joint override position must contain three finite numbers")
        if len(self.orientation_xyzw) != 4 or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in self.orientation_xyzw
        ):
            raise ValueError("free joint override orientation must contain four finite numbers")
        orientation = tuple(float(value) for value in self.orientation_xyzw)
        if not math.isclose(
            math.sqrt(sum(value * value for value in orientation)),
            1.0,
            rel_tol=0.0,
            abs_tol=1.0e-6,
        ):
            raise ValueError("free joint override orientation must be unit length")
        object.__setattr__(
            self,
            "position_world_m",
            tuple(float(value) for value in self.position_world_m),
        )
        object.__setattr__(self, "orientation_xyzw", orientation)


def _free_joint_message(value: FreeJointResetOverride) -> FreeJointState:
    message = FreeJointState()
    message.name = value.name
    message.pose.header.frame_id = ""
    message.twist.header.frame_id = ""
    (
        message.pose.pose.position.x,
        message.pose.pose.position.y,
        message.pose.pose.position.z,
    ) = value.position_world_m
    (
        message.pose.pose.orientation.x,
        message.pose.pose.orientation.y,
        message.pose.pose.orientation.z,
        message.pose.pose.orientation.w,
    ) = value.orientation_xyzw
    message.twist.twist.linear.x = 0.0
    message.twist.twist.linear.y = 0.0
    message.twist.twist.linear.z = 0.0
    message.twist.twist.angular.x = 0.0
    message.twist.twist.angular.y = 0.0
    message.twist.twist.angular.z = 0.0
    return message


class MujocoRosClient:
    """Synchronous bounded facade over the pinned 0.1.0 service interfaces."""

    def __init__(
        self, service_node: Any, joint_state_node: Any, *, service_timeout_s: float = 5.0
    ) -> None:
        if not math.isfinite(service_timeout_s) or service_timeout_s <= 0.0:
            raise ValueError("service_timeout_s must be finite and positive")
        self._service_node = service_node
        self._joint_state_node = joint_state_node
        self._timeout_s = service_timeout_s
        self._pause = service_node.create_client(SetPause, "/mujoco_ros2_control_node/set_pause")
        self._reset = service_node.create_client(
            ResetWorld, "/mujoco_ros2_control_node/reset_world"
        )
        self._switch = service_node.create_client(
            SwitchController, "/controller_manager/switch_controller"
        )
        self._list = service_node.create_client(
            ListControllers, "/controller_manager/list_controllers"
        )
        self._joint_lock = threading.Lock()
        self._joint_positions: dict[str, float] = {}
        self._joint_callback_count = 0
        self._joint_subscription = joint_state_node.create_subscription(
            JointState, "/joint_states", self._joint_callback, qos_profile_sensor_data
        )

    def _joint_callback(self, message: JointState) -> None:
        if len(message.name) != len(message.position):
            return
        positions = {}
        for name, position in zip(message.name, message.position, strict=True):
            value = float(position)
            if not math.isfinite(value):
                return
            positions[name] = value
        if any(str(index) not in positions for index in range(1, 7)):
            return
        with self._joint_lock:
            self._joint_positions = positions
            self._joint_callback_count += 1

    @property
    def joint_callback_count(self) -> int:
        with self._joint_lock:
            return self._joint_callback_count

    def _call(self, client: Any, request: Any, operation: str) -> Any:
        if not client.wait_for_service(timeout_sec=self._timeout_s):
            raise MujocoServiceError(f"{operation} service unavailable")
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self._service_node, future, timeout_sec=self._timeout_s)
        if not future.done():
            raise MujocoServiceError(f"{operation} service timeout")
        error = future.exception()
        if error is not None:
            raise MujocoServiceError(f"{operation} service error: {error}")
        response = future.result()
        if response is None:
            raise MujocoServiceError(f"{operation} returned no response")
        return response

    def pause(self, paused: bool) -> bool:
        request = SetPause.Request()
        request.paused = paused
        return bool(self._call(self._pause, request, "pause").success)

    def reset_world(
        self,
        keyframe: str,
        free_joint_overrides: tuple[FreeJointResetOverride, ...] = (),
    ) -> bool:
        names = tuple(value.name for value in free_joint_overrides)
        if len(set(names)) != len(names):
            raise ValueError("duplicate free joint override names are not allowed")
        request = ResetWorld.Request()
        request.keyframe = keyframe
        request.state_overrides.free_joints = [
            _free_joint_message(value) for value in free_joint_overrides
        ]
        return bool(self._call(self._reset, request, "reset").success)

    def switch_controllers(self, *, activate, deactivate) -> bool:
        request = SwitchController.Request()
        request.activate_controllers = list(activate)
        request.deactivate_controllers = list(deactivate)
        request.strictness = SwitchController.Request.STRICT
        request.activate_asap = True
        request.timeout.sec = int(self._timeout_s)
        request.timeout.nanosec = int((self._timeout_s % 1.0) * 1.0e9)
        if not self._switch.wait_for_service(timeout_sec=self._timeout_s):
            raise MujocoServiceError("switch controllers service unavailable")
        switch_future = self._switch.call_async(request)
        deadline = time.monotonic() + self._timeout_s
        rclpy.spin_until_future_complete(
            self._service_node, switch_future, timeout_sec=self._timeout_s
        )
        if not switch_future.done():
            raise MujocoServiceError("switch controllers service timeout")
        if switch_future.exception() is not None:
            raise MujocoServiceError(
                f"switch controllers service error: {switch_future.exception()}"
            )
        if switch_future.result() is None or not switch_future.result().ok:
            return False
        while time.monotonic() < deadline:
            states = self._controller_states()
            if all(states.get(name) == "active" for name in activate) and all(
                states.get(name) == "inactive" for name in deactivate
            ):
                return True
        raise MujocoServiceError("controller state transition timeout")

    def _controller_states(self) -> dict[str, str]:
        response = self._call(self._list, ListControllers.Request(), "list controllers")
        return {controller.name: controller.state for controller in response.controller}

    def controllers_active(self, names) -> bool:
        states = self._controller_states()
        return all(states.get(name) == "active" for name in names)

    def latest_joint_positions(self) -> tuple[float, ...]:
        with self._joint_lock:
            positions = dict(self._joint_positions)
        try:
            return tuple(positions[str(index)] for index in range(1, 7))
        except KeyError as error:
            raise MujocoServiceError("complete six-joint state is unavailable") from error

    def joints_converged(self, expected, tolerance: float, *, after_callback_count: int) -> bool:
        if self.joint_callback_count <= after_callback_count:
            return False
        try:
            actual = self.latest_joint_positions()
        except MujocoServiceError:
            return False
        return all(abs(value - target) <= tolerance for value, target in zip(actual, expected))

    def progress(self) -> None:
        rclpy.spin_once(self._joint_state_node, timeout_sec=0.01)
