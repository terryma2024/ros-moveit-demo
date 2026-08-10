"""Strict adapter from the atomic MuJoCo ROS message to backend-neutral evidence."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable
from typing import Any

from rclpy.qos import qos_profile_sensor_data
from so101_mujoco_support.msg import SimulationEvidence as RosSimulationEvidence

from so101_mujoco_demo_py.simulation.types import (
    ContactEvidence,
    ObjectState,
    SimulationEvidence,
)


class EvidenceRejected(RuntimeError):
    """Raised when an atomic message violates the configured stream contract."""


class EvidenceStale(RuntimeError):
    """Raised when no sufficiently recent accepted atomic message exists."""


def vector3(value: Any) -> tuple[float, float, float]:
    return float(value.x), float(value.y), float(value.z)


def contact(value: Any) -> ContactEvidence:
    return ContactEvidence(
        body1_id=value.body1_id,
        geom1_id=value.geom1_id,
        body1=value.body1,
        geom1=value.geom1,
        body2_id=value.body2_id,
        geom2_id=value.geom2_id,
        body2=value.body2,
        geom2=value.geom2,
        position_world=vector3(value.position_world),
        normal_world=vector3(value.normal_world),
        signed_distance_m=float(value.signed_distance_m),
        normal_force_n=float(value.normal_force_n),
    )


def convert_message(message: Any) -> SimulationEvidence:
    try:
        left = tuple(contact(value) for value in message.left_fingertip_contacts)
        right = tuple(contact(value) for value in message.right_fingertip_contacts)
        other = tuple(contact(value) for value in message.other_object_contacts)
        pose = message.object_pose_world
        twist = message.object_twist_world
        stamp = message.header.stamp
        return SimulationEvidence(
            simulation_time_s=float(stamp.sec) + float(stamp.nanosec) / 1.0e9,
            frame_id=message.header.frame_id,
            publisher_sequence=message.publisher_sequence,
            simulation_step=message.simulation_step,
            reset_epoch=message.reset_epoch,
            simulation_session_id=message.simulation_session_id,
            paused=message.paused,
            object_state=ObjectState(
                body_id=message.object_body_id,
                body=message.object_body,
                position_world=vector3(pose.position),
                orientation_xyzw=(
                    float(pose.orientation.x),
                    float(pose.orientation.y),
                    float(pose.orientation.z),
                    float(pose.orientation.w),
                ),
                linear_velocity_world=vector3(twist.linear),
                angular_velocity_world=vector3(twist.angular),
            ),
            has_contact=message.has_contact,
            minimum_signed_distance_m=float(message.minimum_signed_distance_m),
            maximum_normal_force_n=float(message.maximum_normal_force_n),
            truncated=message.truncated,
            left_fingertip_contacts=left,
            right_fingertip_contacts=right,
            other_object_contacts=other,
        )
    except (AttributeError, TypeError, ValueError) as error:
        raise EvidenceRejected(f"invalid or missing atomic evidence field: {error}") from error


class MujocoWorldObserver:
    """Return the newest fresh, ordered, session-bound atomic evidence."""

    def __init__(
        self,
        node: Any,
        simulation_session_id: str,
        *,
        max_age_s: float = 0.2,
        topic: str = "/so101/simulation/evidence",
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not simulation_session_id:
            raise ValueError("simulation_session_id must be non-empty")
        if not math.isfinite(max_age_s) or max_age_s <= 0.0:
            raise ValueError("max_age_s must be finite and positive")
        self._session_id = simulation_session_id
        self._max_age_s = max_age_s
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._latest: SimulationEvidence | None = None
        self._received_at_s: float | None = None
        self._rejected_count = 0
        self._last_rejection = ""
        self._subscription = node.create_subscription(
            RosSimulationEvidence, topic, self._callback, qos_profile_sensor_data
        )

    def _callback(self, message: RosSimulationEvidence) -> None:
        try:
            self.accept(message)
        except EvidenceRejected as error:
            with self._lock:
                self._rejected_count += 1
                self._last_rejection = str(error)

    @property
    def rejected_count(self) -> int:
        with self._lock:
            return self._rejected_count

    @property
    def last_rejection(self) -> str:
        with self._lock:
            return self._last_rejection

    def accept(self, message: Any, *, received_at_s: float | None = None) -> None:
        evidence = convert_message(message)
        if evidence.simulation_session_id != self._session_id:
            raise EvidenceRejected(
                f"session mismatch: expected {self._session_id}, got {evidence.simulation_session_id}"
            )
        if evidence.truncated:
            raise EvidenceRejected("truncated atomic evidence")
        receipt = self._monotonic() if received_at_s is None else received_at_s
        if not math.isfinite(receipt):
            raise EvidenceRejected("receipt time must be finite")
        with self._lock:
            previous = self._latest
            if previous is not None:
                if evidence.publisher_sequence <= previous.publisher_sequence:
                    raise EvidenceRejected("publisher sequence must increase")
                if evidence.reset_epoch < previous.reset_epoch:
                    raise EvidenceRejected("reset epoch moved backward")
                if evidence.reset_epoch > previous.reset_epoch + 1:
                    raise EvidenceRejected("reset epoch skipped")
                if evidence.reset_epoch == previous.reset_epoch:
                    if evidence.simulation_step < previous.simulation_step:
                        raise EvidenceRejected("simulation step moved backward")
                    if evidence.simulation_step == previous.simulation_step and not evidence.paused:
                        raise EvidenceRejected("same simulation step requires paused evidence")
                elif evidence.simulation_step != 0:
                    raise EvidenceRejected("new reset epoch must begin at simulation step zero")
            self._latest = evidence
            self._received_at_s = receipt

    def snapshot(self) -> SimulationEvidence:
        now = self._monotonic()
        with self._lock:
            evidence = self._latest
            received_at_s = self._received_at_s
        if evidence is None or received_at_s is None:
            raise EvidenceStale("no atomic evidence has been accepted")
        age = now - received_at_s
        if not math.isfinite(age) or age < 0.0 or age > self._max_age_s:
            raise EvidenceStale(f"atomic evidence age {age:.3f}s exceeds {self._max_age_s:.3f}s")
        return evidence
