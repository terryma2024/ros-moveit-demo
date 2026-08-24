"""ROS adapter for one absolute-deadline `/cup_pose` acquisition."""

from __future__ import annotations

import time
from typing import Any

from ..cli.cup_pose_subscriber import status_line, validate_pose_message
from ..core.dynamic_pick import CupPoseSample, DynamicPickTemplate
from ..core.task_geometry import Pose7
from ..ports.cup_pose_source import acquire_one


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
        qos = QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
            reliability=ReliabilityPolicy.BEST_EFFORT,
            durability=DurabilityPolicy.VOLATILE,
        )
        self._subscription = node.create_subscription(
            PoseStamped,
            "/cup_pose",
            lambda message: self._messages.append((message, time.monotonic())),
            qos,
        )

    def _receive(self):
        return self._messages.pop(0) if self._messages else None

    def _convert(self, item: tuple[Any, float]) -> CupPoseSample:
        message, received = item
        frame_id, position, orientation = validate_pose_message(message)
        if frame_id != self._template.planning_frame:
            raise ValueError("CUP_POSE_TF_UNAVAILABLE: V2.1 requires frame_id=world")
        stamp = message.header.stamp
        stamp_ns = int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)
        if stamp_ns <= 0:
            raise ValueError("CUP_POSE_STALE: source stamp must be non-zero")
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
