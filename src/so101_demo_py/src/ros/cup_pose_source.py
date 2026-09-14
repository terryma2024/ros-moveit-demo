"""ROS adapter for one absolute-deadline `/cup_pose` acquisition."""

from __future__ import annotations

from dataclasses import dataclass
import math
import time
from typing import Any

from ..cli.cup_pose_subscriber import status_line, validate_pose_message
from ..core.dynamic_pick import CupPoseSample, DynamicPickTemplate
from ..core.task_geometry import Pose7
from ..ports.cup_pose_source import CupPoseSourceError, acquire_one


@dataclass(frozen=True)
class PoseReceiveBoundary:
    ready_ros_ns: int
    ready_monotonic_s: float


class RosCupPoseSource:
    def __init__(self, node: Any, template: DynamicPickTemplate) -> None:
        from geometry_msgs.msg import PoseStamped
        from rclpy.qos import (
            DurabilityPolicy,
            HistoryPolicy,
            QoSProfile,
            ReliabilityPolicy,
        )

        self._node = node
        self._template = template
        self._messages: list[tuple[Any, float]] = []
        self._boundary: PoseReceiveBoundary | None = None
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._subscription = node.create_subscription(
            PoseStamped,
            "/cup_pose",
            lambda message: self._messages.append((message, time.monotonic())),
            qos,
        )

    def arm(self, timeout_s: float) -> PoseReceiveBoundary:
        """Wait for simulated ROS time, then exclude all pre-READY samples."""

        import rclpy

        if (
            isinstance(timeout_s, bool)
            or not isinstance(timeout_s, (int, float))
            or not math.isfinite(timeout_s)
            or timeout_s <= 0.0
        ):
            raise ValueError("timeout_s must be finite and positive")
        deadline = time.monotonic() + float(timeout_s)
        while True:
            ready_ros_ns = int(self._node.get_clock().now().nanoseconds)
            if ready_ros_ns > 0:
                self._messages.clear()
                boundary = PoseReceiveBoundary(
                    ready_ros_ns=ready_ros_ns,
                    ready_monotonic_s=time.monotonic(),
                )
                self._boundary = boundary
                return boundary
            remaining = deadline - time.monotonic()
            if remaining <= 0.0:
                raise CupPoseSourceError(
                    "ROS_CLOCK_TIMEOUT",
                    "ROS clock did not become positive before cup-pose READY",
                )
            rclpy.spin_once(self._node, timeout_sec=min(0.05, remaining))

    def _receive(self):
        return self._messages.pop(0) if self._messages else None

    def _convert(self, item: tuple[Any, float]) -> CupPoseSample:
        message, received = item
        boundary = self._boundary
        if boundary is None:
            raise ValueError("CUP_POSE_READY_BOUNDARY_MISSING")
        frame_id, position, orientation = validate_pose_message(message)
        if frame_id != self._template.planning_frame:
            raise ValueError("CUP_POSE_TF_UNAVAILABLE: V2.1 requires frame_id=world")
        stamp = message.header.stamp
        stamp_ns = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
        if stamp_ns <= 0:
            raise ValueError("CUP_POSE_STALE: source stamp must be non-zero")
        if (
            received <= boundary.ready_monotonic_s
            or stamp_ns < boundary.ready_ros_ns
        ):
            raise ValueError("CUP_POSE_STALE: message predates READY boundary")
        now_ns = int(self._node.get_clock().now().nanoseconds)
        age_s = (now_ns - stamp_ns) * 1e-9
        if age_s > self._template.maximum_source_age_s:
            raise ValueError("CUP_POSE_STALE: source age exceeds template maximum")
        if age_s < -self._template.maximum_future_skew_s:
            raise ValueError("CUP_POSE_STALE: source stamp is too far in the future")
        return CupPoseSample(
            frame_id,
            stamp_ns,
            received,
            Pose7((*position, *orientation)),
        )

    def get_one(self, timeout_s: float) -> CupPoseSample:
        import rclpy

        try:
            return acquire_one(
                receive=self._receive,
                spin_once=lambda duration: rclpy.spin_once(
                    self._node, timeout_sec=duration
                ),
                convert=self._convert,
                on_invalid=lambda error: print(
                    status_line("ERROR", failure="CUP_POSE_INVALID", message=error), flush=True
                ),
                timeout_s=timeout_s,
            )
        finally:
            self._node.destroy_subscription(self._subscription)
