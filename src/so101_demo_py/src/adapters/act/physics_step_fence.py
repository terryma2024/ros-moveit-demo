"""Read-only MuJoCo physics marker after a confirmed SEARCH stop."""

from __future__ import annotations

import math
import threading
import time

from rclpy.qos import QoSProfile, ReliabilityPolicy
from so101_mujoco_support.msg import PhysicsStepFenceAck, PhysicsStepFenceRequest


_QOS = QoSProfile(depth=5, reliability=ReliabilityPolicy.RELIABLE)


class RosPhysicsStepFence:
    """Accept one scoped marker per reset epoch; never grant command authority."""

    def __init__(self, node, session_id: str, *, monotonic=time.monotonic,
                 clock_ns=time.monotonic_ns) -> None:
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("PHYSICS_STEP_FENCE_SCOPE_INVALID")
        self.session_id = session_id
        self.monotonic = monotonic
        self.clock_ns = clock_ns
        self._condition = threading.Condition()
        self._epoch = None
        self._sequence = 0
        self._pending = False
        self._result = None
        self._invalid = False
        self._request_sent_wall_s = None
        self._publisher = node.create_publisher(
            PhysicsStepFenceRequest, "/so101/simulation/physics_step_fence_request", _QOS)
        self._subscription = node.create_subscription(
            PhysicsStepFenceAck, "/so101/simulation/physics_step_fence_ack",
            self._acknowledge, _QOS)

    def arm(self, epoch: int) -> None:
        if type(epoch) is not int or epoch < 1:
            raise ValueError("PHYSICS_STEP_FENCE_SCOPE_INVALID")
        with self._condition:
            if self._pending:
                self._invalid = True
            self._epoch = epoch
            self._sequence = 0
            self._condition.notify_all()

    def _acknowledge(self, ack: PhysicsStepFenceAck) -> None:
        received = self.monotonic()
        with self._condition:
            if not self._pending:
                return
            if (self._result is not None or ack.simulation_session_id != self.session_id
                    or ack.reset_epoch != self._epoch
                    or ack.request_sequence != self._sequence
                    or type(ack.marked_physics_step) is not int
                    or ack.marked_physics_step < 1
                    or not math.isfinite(ack.marked_simulation_time_s)
                    or ack.marked_simulation_time_s < 0
                    or received < self._request_sent_wall_s):
                self._invalid = True
            else:
                self._result = {
                    "session_id": self.session_id,
                    "reset_epoch": self._epoch,
                    "request_sequence": self._sequence,
                    "marked_physics_step": ack.marked_physics_step,
                    "marked_simulation_time_s": ack.marked_simulation_time_s,
                    "request_sent_wall_s": self._request_sent_wall_s,
                    "ack_received_wall_s": received,
                    "command_authority": False,
                }
            self._condition.notify_all()

    def request_after_stop(self, epoch: int, stopped_wall_s: float,
                           deadline_ns: int) -> dict:
        if (type(epoch) is not int or epoch < 1
                or type(deadline_ns) is not int
                or not isinstance(stopped_wall_s, (float, int))
                or not math.isfinite(stopped_wall_s) or stopped_wall_s < 0):
            raise ValueError("PHYSICS_STEP_FENCE_SCOPE_INVALID")
        with self._condition:
            if epoch != self._epoch:
                raise ValueError("PHYSICS_STEP_FENCE_SCOPE_INVALID")
            if self._sequence:
                raise ValueError("PHYSICS_STEP_FENCE_ALREADY_REQUESTED")
            sent = self.monotonic()
            if sent < stopped_wall_s or self.clock_ns() >= deadline_ns:
                raise ValueError("PHYSICS_STEP_FENCE_INVALID")
            self._sequence = 1
            self._pending = True
            self._invalid = False
            self._result = None
            self._request_sent_wall_s = sent
            request = PhysicsStepFenceRequest(
                simulation_session_id=self.session_id, reset_epoch=epoch,
                request_sequence=self._sequence)
        try:
            self._publisher.publish(request)
        except BaseException:
            with self._condition:
                self._invalid = True
                self._pending = False
            raise
        with self._condition:
            while self._result is None and not self._invalid:
                remaining_s = (deadline_ns - self.clock_ns()) / 1_000_000_000
                if remaining_s <= 0:
                    self._pending = False
                    raise ValueError("PHYSICS_STEP_FENCE_TIMEOUT")
                self._condition.wait(timeout=min(remaining_s, .2))
            self._pending = False
            if self._invalid or self._epoch != epoch:
                raise ValueError("PHYSICS_STEP_FENCE_INVALID")
            return dict(self._result)
