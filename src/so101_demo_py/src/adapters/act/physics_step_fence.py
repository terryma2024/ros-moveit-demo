"""Read-only MuJoCo physics marker after a confirmed SEARCH stop."""

from __future__ import annotations

import math
import threading
import time

from rclpy.qos import QoSProfile, ReliabilityPolicy
from so101_mujoco_support.msg import (
    PhysicsStepEvidence, PhysicsStepFenceAck, PhysicsStepFenceRequest,
)


_QOS = QoSProfile(depth=5, reliability=ReliabilityPolicy.RELIABLE)


class RosPhysicsStepFence:
    """Retain one SEARCH marker and one later sample without command authority."""

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
        self._request_sent_monotonic_ns = None
        self._request_deadline_ns = None
        self._last_result = None
        self._closed = False
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
            self._last_result = None
            self._closed = False
            self._condition.notify_all()

    def _acknowledge(self, ack: PhysicsStepFenceAck) -> None:
        received = self.monotonic()
        received_ns = self.clock_ns()
        with self._condition:
            if not self._pending:
                return
            sample = ack.marked_sample
            previous = self._last_result
            if (self._result is not None or ack.simulation_session_id != self.session_id
                    or ack.reset_epoch != self._epoch
                    or ack.request_sequence != self._sequence
                    or type(ack.marked_physics_step) is not int
                    or ack.marked_physics_step < 1
                    or not math.isfinite(ack.marked_simulation_time_s)
                    or ack.marked_simulation_time_s < 0
                    or not math.isfinite(ack.marked_simulation_time_s * 1_000_000_000)
                    or not isinstance(sample, PhysicsStepEvidence)
                    or sample.simulation_session_id != ack.simulation_session_id
                    or sample.reset_epoch != ack.reset_epoch
                    or sample.physics_step != ack.marked_physics_step
                    or sample.simulation_time_s != ack.marked_simulation_time_s
                    or sample.truncated is not False
                    or sample.diagnostic_hazard_breached is not False
                    or not sample.model_qpos or not sample.model_qvel
                    or any(not math.isfinite(value) for value in sample.model_qpos)
                    or any(not math.isfinite(value) for value in sample.model_qvel)
                    or received < self._request_sent_wall_s
                    or type(ack.clock_interval_begin_monotonic_ns) is not int
                    or type(ack.clock_interval_end_monotonic_ns) is not int
                    or not 0 < self._request_sent_monotonic_ns <=
                       ack.clock_interval_begin_monotonic_ns <=
                       ack.clock_interval_end_monotonic_ns <= received_ns <
                       self._request_deadline_ns
                    or (self._sequence == 2 and (
                        previous is None
                        or ack.marked_physics_step <= previous["marked_physics_step"]
                        or ack.clock_interval_begin_monotonic_ns <
                           previous["clock_interval_end_monotonic_ns"]
                        or round(ack.marked_simulation_time_s * 1_000_000_000) -
                           round(previous["marked_simulation_time_s"] * 1_000_000_000) !=
                           (ack.marked_physics_step - previous["marked_physics_step"])
                           * 2_000_000))):
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
                    "request_sent_monotonic_ns": self._request_sent_monotonic_ns,
                    "ack_received_monotonic_ns": received_ns,
                    "clock_interval_begin_monotonic_ns":
                        ack.clock_interval_begin_monotonic_ns,
                    "clock_interval_end_monotonic_ns":
                        ack.clock_interval_end_monotonic_ns,
                    "clock_interval_width_ns": (
                        ack.clock_interval_end_monotonic_ns -
                        ack.clock_interval_begin_monotonic_ns),
                    "model_qpos": tuple(sample.model_qpos),
                    "model_qvel": tuple(sample.model_qvel),
                    "command_authority": False,
                }
            self._condition.notify_all()

    def request_after_stop(self, epoch: int, stopped_wall_s: float,
                           deadline_ns: int) -> dict:
        return self._request(epoch, stopped_wall_s, deadline_ns, after_step=None)

    def request_followup_after_stop(self, epoch: int, stopped_wall_s: float,
                                    after_step: int, deadline_ns: int) -> dict:
        if type(after_step) is not int or after_step < 1:
            with self._condition:
                if epoch == self._epoch:
                    self._closed = True
            raise ValueError("PHYSICS_STEP_FENCE_SCOPE_INVALID")
        return self._request(epoch, stopped_wall_s, deadline_ns,
                             after_step=after_step)

    def _request(self, epoch: int, stopped_wall_s: float,
                 deadline_ns: int, *, after_step: int | None) -> dict:
        if (type(epoch) is not int or epoch < 1
                or type(deadline_ns) is not int
                or not isinstance(stopped_wall_s, (float, int))
                or not math.isfinite(stopped_wall_s) or stopped_wall_s < 0):
            with self._condition:
                if after_step is not None and epoch == self._epoch:
                    self._closed = True
            raise ValueError("PHYSICS_STEP_FENCE_SCOPE_INVALID")
        with self._condition:
            if epoch != self._epoch:
                raise ValueError("PHYSICS_STEP_FENCE_SCOPE_INVALID")
            if self._closed or self._pending:
                raise ValueError("PHYSICS_STEP_FENCE_CLOSED")
            if after_step is None and self._sequence:
                raise ValueError("PHYSICS_STEP_FENCE_ALREADY_REQUESTED")
            if (after_step is not None and (self._sequence != 1
                    or self._last_result is None
                    or after_step != self._last_result["marked_physics_step"])):
                self._closed = True
                raise ValueError("PHYSICS_STEP_FENCE_SCOPE_INVALID")
            sent = self.monotonic()
            sent_ns = self.clock_ns()
            if (sent < stopped_wall_s or sent_ns <= 0 or sent_ns >= deadline_ns
                    or (after_step is not None and sent_ns <
                        self._last_result["ack_received_monotonic_ns"])):
                if after_step is not None:
                    self._closed = True
                raise ValueError("PHYSICS_STEP_FENCE_INVALID")
            self._sequence += 1
            self._pending = True
            self._invalid = False
            self._result = None
            self._request_sent_wall_s = sent
            self._request_sent_monotonic_ns = sent_ns
            self._request_deadline_ns = deadline_ns
            request = PhysicsStepFenceRequest(
                simulation_session_id=self.session_id, reset_epoch=epoch,
                request_sequence=self._sequence)
        try:
            self._publisher.publish(request)
        except BaseException:
            with self._condition:
                self._invalid = True
                self._pending = False
                if self._epoch == epoch:
                    self._closed = True
            raise
        with self._condition:
            while self._result is None and not self._invalid:
                remaining_s = (deadline_ns - self.clock_ns()) / 1_000_000_000
                if remaining_s <= 0:
                    self._pending = False
                    if self._epoch == epoch:
                        self._closed = True
                    raise ValueError("PHYSICS_STEP_FENCE_TIMEOUT")
                self._condition.wait(timeout=min(remaining_s, .2))
            self._pending = False
            if self._invalid or self._epoch != epoch:
                if self._epoch == epoch:
                    self._closed = True
                raise ValueError("PHYSICS_STEP_FENCE_INVALID")
            result = dict(self._result)
            self._last_result = result
            if self._sequence == 2:
                self._closed = True
            return dict(result)
