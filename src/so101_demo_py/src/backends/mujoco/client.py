"""Pinned ROS 2 service and joint-state client for MuJoCo reset transactions."""

from __future__ import annotations

import math
import os
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
from so101_mujoco_support.msg import ScalarJointEvidence
from .observer import ATOMIC_EVIDENCE_QOS

from so101_demo.act.joints import ARM_JOINTS, ACT_JOINTS, JOINT_LIMITS, ordered_positions


class MujocoServiceError(RuntimeError):
    """Raised when a pinned ROS interface is unavailable or returns failure."""


@dataclass(frozen=True, slots=True)
class JointResetOverride:
    """Named one-degree-of-freedom reset target, in radians and radians/s."""

    name: str
    position: float
    velocity: float = 0.0

    def __post_init__(self):
        if self.name not in ACT_JOINTS:
            raise ValueError("unknown or non-scalar reset joint")
        ordered_positions({"position": self.position, "velocity": self.velocity},
                          ("position", "velocity"))
        limits = JOINT_LIMITS.get(self.name)
        if limits is not None and not limits[0] <= self.position <= limits[1]:
            raise ValueError("reset joint position is out of bounds")


def joint_override_message(items: tuple[JointResetOverride, ...]) -> JointState:
    if any(not isinstance(item, JointResetOverride) for item in items):
        raise ValueError("joint reset overrides must be validated records")
    if len(set(item.name for item in items)) != len(items):
        raise ValueError("duplicate reset joint")
    return JointState(name=[item.name for item in items],
                      position=[float(item.position) for item in items],
                      velocity=[float(item.velocity) for item in items])


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
        from so101_demo.adapters.act.leased_action_client import context_from_environment
        self.control_context = context_from_environment()
        if os.environ.get("SO101_ACT_PROFILE") in ("1", "true") and self.control_context is None:
            raise PermissionError("CONTROL_CONTEXT_REQUIRED")
        self._service_node = service_node
        self._joint_state_node = joint_state_node
        self._timeout_s = service_timeout_s
        self._pause = self._reset = self._switch = None
        if self.control_context is None:
            self._pause = service_node.create_client(SetPause, "/mujoco_ros2_control_node/set_pause")
            self._reset = service_node.create_client(ResetWorld, "/mujoco_ros2_control_node/reset_world")
            self._switch = service_node.create_client(SwitchController, "/controller_manager/switch_controller")
        self._list = service_node.create_client(
            ListControllers, "/controller_manager/list_controllers"
        )
        self._joint_lock = threading.Lock()
        self._joint_positions: dict[str, float] = {}
        self._joint_velocities: dict[str, float] = {}
        self._joint_callback_count = 0
        self._scalar_joint_callback_count = 0
        self._reset_joint_snapshot = None
        self._scalar_joint_subscription = None
        self._joint_subscription = joint_state_node.create_subscription(
            JointState, "/joint_states", self._joint_callback, qos_profile_sensor_data
        )

    def enable_reset_joint_audit(self):
        """Read authoritative paused scalar snapshots without changing policy inputs."""
        if self._scalar_joint_subscription is None:
            self._scalar_joint_subscription = self._joint_state_node.create_subscription(
                ScalarJointEvidence, "/so101/simulation/joints", self._scalar_joint_callback,
                ATOMIC_EVIDENCE_QOS)

    def _scalar_joint_callback(self, message):
        names = message.joint_names
        if (len(set(names)) != len(names) or set(names) != set(ACT_JOINTS)
                or len(names) != len(message.positions_rad)
                or len(names) != len(message.velocities_rad_s)):
            return
        positions = dict(zip(names, message.positions_rad, strict=True))
        velocities = dict(zip(names, message.velocities_rad_s, strict=True))
        stamp = message.header.stamp.sec + message.header.stamp.nanosec * 1e-9
        if (not message.simulation_session_id or stamp < 0 or not math.isfinite(stamp)
                or any(not math.isfinite(value) for value in (*positions.values(), *velocities.values()))):
            return
        with self._joint_lock:
            self._scalar_joint_callback_count += 1
            self._reset_joint_snapshot = dict(
                positions=positions, velocities=velocities, sim_time_s=stamp,
                simulation_session_id=message.simulation_session_id,
                reset_epoch=message.reset_epoch, simulation_step=message.simulation_step,
                paused=message.paused, received_wall_s=time.monotonic(),
                callback_count=self._scalar_joint_callback_count)

    @property
    def scalar_joint_callback_count(self):
        with self._joint_lock:
            return self._scalar_joint_callback_count

    def reset_joint_snapshot(self, names=ARM_JOINTS):
        with self._joint_lock:
            if self._reset_joint_snapshot is None:
                raise MujocoServiceError("reset physics snapshot is unavailable")
            snapshot = self._reset_joint_snapshot
            try:
                return dict(snapshot, positions=ordered_positions(snapshot["positions"], names),
                            velocities=ordered_positions(snapshot["velocities"], names))
            except ValueError as error:
                raise MujocoServiceError("complete reset physics snapshot is unavailable") from error

    def _joint_callback(self, message: JointState) -> None:
        if len(message.name) != len(message.position):
            return
        if len(set(message.name)) != len(message.name):
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
            self._joint_velocities = (
                dict(zip(message.name, message.velocity, strict=True))
                if len(message.velocity) == len(message.name)
                and all(math.isfinite(value) for value in message.velocity) else {}
            )
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
        if self.control_context is not None:
            from so101_demo.adapters.act.leased_action_client import connection_for
            result=connection_for(self.control_context).request("pause",self.control_context,paused=paused)
            return bool(result["pause_result"]["success"])
        request = SetPause.Request()
        request.paused = paused
        return bool(self._call(self._pause, request, "pause").success)

    def reset_world(
        self,
        keyframe: str,
        free_joint_overrides: tuple[FreeJointResetOverride, ...] = (),
        *,
        joint_overrides: tuple[JointResetOverride, ...] = (),
    ) -> bool:
        names = tuple(value.name for value in free_joint_overrides)
        if len(set(names)) != len(names):
            raise ValueError("duplicate free joint override names are not allowed")
        request = ResetWorld.Request()
        request.keyframe = keyframe
        request.state_overrides.free_joints = [
            _free_joint_message(value) for value in free_joint_overrides
        ]
        request.state_overrides.joint_states = joint_override_message(joint_overrides)
        if self.control_context is not None:
            from so101_demo.adapters.act.leased_action_client import connection_for, message_dict
            result = connection_for(self.control_context).request("reset_world", self.control_context,
                reset_request=message_dict(request))
            return bool(result["reset_result"]["success"])
        return bool(self._call(self._reset, request, "reset").success)

    def finish_reset(self) -> bool:
        if self.control_context is None:return True
        from so101_demo.adapters.act.leased_action_client import connection_for
        connection_for(self.control_context).request("finish_reset",self.control_context)
        return True

    def switch_controllers(self, *, activate, deactivate) -> bool:
        if self.control_context is not None:
            from so101_demo.adapters.act.leased_action_client import connection_for
            result=connection_for(self.control_context).request("switch_controllers",self.control_context,
                activate=list(activate),deactivate=list(deactivate))
            if not result["switch_result"]["ok"]:return False
            deadline=time.monotonic()+self._timeout_s
            while time.monotonic()<deadline:
                states=self._controller_states()
                if all(states.get(name)=="active" for name in activate) and all(states.get(name)=="inactive" for name in deactivate):return True
            raise MujocoServiceError("controller state transition timeout")
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

    def latest_joint_positions(self, names=ARM_JOINTS) -> tuple[float, ...]:
        with self._joint_lock:
            positions = dict(self._joint_positions)
        try:
            return ordered_positions(positions, names)
        except ValueError as error:
            raise MujocoServiceError("complete named joint state is unavailable") from error

    def latest_joint_velocities(self, names=ARM_JOINTS) -> tuple[float, ...]:
        with self._joint_lock:
            velocities = dict(self._joint_velocities)
        try:
            return ordered_positions(velocities, names)
        except ValueError as error:
            raise MujocoServiceError("complete named joint velocity is unavailable") from error

    def joints_converged(self, expected, tolerance: float, *, after_callback_count: int,
                         names=ARM_JOINTS) -> bool:
        if len(expected) != len(names) or any(not math.isfinite(value) for value in expected):
            return False
        if self.joint_callback_count <= after_callback_count:
            return False
        try:
            actual = self.latest_joint_positions(names)
        except MujocoServiceError:
            return False
        return all(abs(value - target) <= tolerance
                   for value, target in zip(actual, expected, strict=True))

    def progress(self) -> None:
        rclpy.spin_once(self._joint_state_node, timeout_sec=0.01)
