"""MuJoCo readiness, pause, and shutdown adapter."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence
from typing import Any

from ...ports.lifecycle import PauseReceipt, ReadinessResult, ShutdownResult


def _identity(evidence: Any) -> tuple[str, int]:
    session_id = getattr(evidence, "session_id", None) or getattr(
        evidence, "simulation_session_id", ""
    )
    return str(session_id), int(evidence.reset_epoch)


def _paused(evidence: Any) -> bool | None:
    value = getattr(evidence, "paused", None)
    if value is None:
        value = getattr(evidence, "backend_metadata", {}).get("paused")
    return value if isinstance(value, bool) else None


class MujocoLifecycleAdapter:
    def __init__(
        self,
        services: Any,
        observer: Any,
        *,
        controller_names: Sequence[str] = ("arm_controller", "gripper_controller"),
        shutdown_callback: Callable[[float], bool] | None = None,
    ) -> None:
        self._services = services
        self._observer = observer
        self._controller_names = tuple(controller_names)
        self._shutdown_callback = shutdown_callback

    def readiness(self, timeout_s: float) -> ReadinessResult:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            return ReadinessResult(False, error_code="READINESS_TIMEOUT_INVALID")
        try:
            evidence = self._observer.snapshot()
            session_id, reset_epoch = _identity(evidence)
            if not session_id or not self._services.controllers_active(self._controller_names):
                raise RuntimeError("world or controller state is not confirmed")
        except Exception:
            return ReadinessResult(False, error_code="WORLD_STATE_NOT_CONFIRMED")
        return ReadinessResult(True, session_id, reset_epoch)

    def pause(self, paused: bool) -> PauseReceipt:
        try:
            if not self._services.pause(paused):
                return PauseReceipt(False, paused, error_code="PAUSE_SERVICE_FAILED")
            evidence = self._observer.snapshot()
            session_id, reset_epoch = _identity(evidence)
            if not session_id or _paused(evidence) is not paused:
                raise RuntimeError("post-request world state is not confirmed")
        except Exception:
            return PauseReceipt(False, paused, error_code="WORLD_STATE_NOT_CONFIRMED")
        return PauseReceipt(True, paused, session_id, reset_epoch)

    def shutdown(self, timeout_s: float) -> ShutdownResult:
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            return ShutdownResult(False, "SHUTDOWN_TIMEOUT_INVALID")
        if self._shutdown_callback is None:
            return ShutdownResult(False, "SHUTDOWN_NOT_CONFIGURED")
        try:
            accepted = self._shutdown_callback(timeout_s)
        except Exception:
            return ShutdownResult(False, "SHUTDOWN_FAILED")
        return ShutdownResult(bool(accepted), None if accepted else "SHUTDOWN_FAILED")


class MujocoPauseControl:
    """Retain one private ROS participant across point pause/resume calls."""

    def __init__(self) -> None:
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        from mujoco_ros2_control_msgs.srv import SetPause

        self._context = rclpy.context.Context()
        rclpy.init(context=self._context)
        self._node = rclpy.create_node(
            "so101_live_runtime_pause_control", context=self._context
        )
        self._executor = SingleThreadedExecutor(context=self._context)
        self._executor.add_node(self._node)
        self._client = self._node.create_client(
            SetPause, "/mujoco_ros2_control_node/set_pause"
        )
        self._request_type = SetPause.Request
        self._closed = False

    def set_paused(self, paused: bool) -> bool:
        if self._closed:
            raise RuntimeError("MuJoCo pause control is closed")
        if type(paused) is not bool:
            raise TypeError("paused must be bool")
        if not self._client.wait_for_service(timeout_sec=5.0):
            return False
        request = self._request_type()
        request.paused = paused
        future = self._client.call_async(request)
        deadline = time.monotonic() + 5.0
        while not future.done() and time.monotonic() < deadline:
            self._executor.spin_once(timeout_sec=0.01)
        response = future.result() if future.done() else None
        return bool(response is not None and response.success)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._executor.remove_node(self._node)
        self._executor.shutdown()
        self._node.destroy_node()
        self._context.shutdown()


def _set_physics_paused(paused: bool) -> bool:
    control = MujocoPauseControl()
    try:
        return control.set_paused(paused)
    finally:
        control.close()


def pause_physics(config: Any) -> bool:
    """Freeze a qualified MuJoCo stack while its immutable RGB waits for inference."""

    del config
    return _set_physics_paused(True)


def resume_physics(config: Any) -> bool:
    """Resume a qualified MuJoCo stack; application code receives this as a callback."""

    del config
    return _set_physics_paused(False)
