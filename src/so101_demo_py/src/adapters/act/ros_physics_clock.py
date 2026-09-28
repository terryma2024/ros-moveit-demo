"""Source-only ROS chunk receiver with exact callback receipts across reset arm."""

from __future__ import annotations

import copy
import math
import threading
from collections import deque

from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk

from so101_demo.core.simulation.types import SimulationEvidence

from .physics_clock_history import PhysicsClockHistory


_TOPIC = "/so101/simulation/physics_step_chunks"


class RosPhysicsClockAdapter:
    """Keep bounded original chunks; never grant a broker or goal permission."""

    def __init__(self, node, history, *, on_hazard,
                 pending_chunk_capacity=128, pending_sample_capacity=5000):
        if (not isinstance(history, PhysicsClockHistory)
                or not callable(on_hazard)
                or type(pending_chunk_capacity) is not int
                or pending_chunk_capacity < 1
                or type(pending_sample_capacity) is not int
                or pending_sample_capacity < 1):
            raise ValueError("PHYSICS_CLOCK_ADAPTER_CONFIG_INVALID")
        self.history = history
        self.on_hazard = on_hazard
        self.chunk_capacity = pending_chunk_capacity
        self.sample_capacity = pending_sample_capacity
        self._lock = threading.RLock()
        self._pending = deque()
        self._pending_samples = 0
        self._lost_epochs = set()
        self._unscoped_failure = False
        self._notified_epochs = set()
        self._armed = False
        self.subscription = node.create_subscription(
            PhysicsStepEvidenceChunk, _TOPIC, self.accept_message,
            QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE,
                       durability=DurabilityPolicy.VOLATILE))

    def _scope(self, chunk):
        if (not isinstance(chunk, PhysicsStepEvidenceChunk)
                or not isinstance(chunk.simulation_session_id, str)
                or not chunk.simulation_session_id
                or type(chunk.reset_epoch) is not int
                or chunk.reset_epoch < 0 or not chunk.samples
                or type(chunk.chunk_sequence) is not int
                or chunk.chunk_sequence < 0
                or any(not isinstance(sample, PhysicsStepEvidence)
                       or sample.simulation_session_id != chunk.simulation_session_id
                       or sample.reset_epoch != chunk.reset_epoch
                       for sample in chunk.samples)):
            raise ValueError("PHYSICS_CHUNK_ENVELOPE_INVALID")
        steps = [sample.physics_step for sample in chunk.samples]
        if (any(type(step) is not int or step < 1 for step in steps)
                or steps != list(range(steps[0], steps[0] + len(steps)))
                or chunk.first_physics_step != steps[0]
                or chunk.last_physics_step != steps[-1]
                or any(not isinstance(value, (int, float))
                       or isinstance(value, bool) or not math.isfinite(value)
                       for value in (chunk.first_simulation_time_s,
                                     chunk.last_simulation_time_s,
                                     chunk.samples[0].simulation_time_s,
                                     chunk.samples[-1].simulation_time_s))
                or round(chunk.first_simulation_time_s * 1_000_000_000) !=
                   round(chunk.samples[0].simulation_time_s * 1_000_000_000)
                or round(chunk.last_simulation_time_s * 1_000_000_000) !=
                   round(chunk.samples[-1].simulation_time_s * 1_000_000_000)):
            raise ValueError("PHYSICS_CHUNK_ENVELOPE_INVALID")
        return chunk.simulation_session_id, chunk.reset_epoch

    def _notify(self):
        epoch = self.history.epoch
        if self.history.hazard is not None and epoch not in self._notified_epochs:
            self._notified_epochs.add(epoch)
            self.on_hazard(self.history.hazard)

    @property
    def evidence_ready(self):
        """Delegate the fail-closed evidence predicate; never grants authority."""
        with self._lock:
            return self.history.evidence_ready

    def check_health(self, *, now_ns=None):
        """Poll the bounded health contract and notify at most once per epoch.

        The history can only detect silence when someone asks, so the owning
        runtime must call this at a period shorter than the configured silence
        bound and treat False as a closed epoch.
        """
        with self._lock:
            healthy = self.history.check_health(now_ns=now_ns)
            self._notify()
            return healthy

    def _append_pending(self, chunk, receipt_ns, scope):
        samples = len(chunk.samples)
        if samples > self.sample_capacity:
            self._lost_epochs.add(scope)
            return
        while (len(self._pending) >= self.chunk_capacity
               or self._pending_samples + samples > self.sample_capacity):
            old_chunk, _, old_scope = self._pending.popleft()
            self._pending_samples -= len(old_chunk.samples)
            self._lost_epochs.add(old_scope)
        self._pending.append((chunk, receipt_ns, scope))
        self._pending_samples += samples

    def _consume(self, chunk, receipt_ns, scope):
        current = (self.history.session_id, self.history.epoch)
        if scope[0] != current[0]:
            self.history.latch("PHYSICS_CHUNK_FOREIGN_SESSION")
        elif scope[1] < current[1]:
            return
        elif scope[1] > current[1]:
            self._append_pending(chunk, receipt_ns, scope)
            self.history.latch("PHYSICS_CHUNK_FUTURE_EPOCH")
        elif self.history.hazard is None:
            try:
                self.history.accept_chunk(chunk, received_monotonic_ns=receipt_ns)
            except ValueError:
                pass  # PhysicsClockHistory retains the specific sticky source reason.
        self._notify()

    def accept_message(self, message):
        receipt_ns = self.history.clock_ns()
        with self._lock:
            try:
                if type(receipt_ns) is not int or receipt_ns < 1:
                    raise ValueError("PHYSICS_CHUNK_RECEIPT_INVALID")
                chunk = copy.deepcopy(message)
                scope = self._scope(chunk)
                if not self._armed:
                    if scope != (self.history.session_id, 0):
                        self._append_pending(chunk, receipt_ns, scope)
                else:
                    self._consume(chunk, receipt_ns, scope)
            except (AttributeError, TypeError, ValueError, OverflowError):
                if self._armed:
                    self.history.latch("PHYSICS_CHUNK_CALLBACK_INVALID")
                    self._notify()
                else:
                    self._unscoped_failure = True

    def arm(self, reset_snapshot):
        if (not isinstance(reset_snapshot, SimulationEvidence)
                or reset_snapshot.simulation_session_id != self.history.session_id
                or reset_snapshot.paused is not True
                or reset_snapshot.truncated is not False
                or reset_snapshot.simulation_step != 0
                or reset_snapshot.reset_epoch < 1
                or not math.isfinite(reset_snapshot.simulation_time_s)):
            raise ValueError("PHYSICS_CLOCK_RESET_INVALID")
        with self._lock:
            epoch = reset_snapshot.reset_epoch
            self.history.arm(epoch, source_floor_s=reset_snapshot.simulation_time_s)
            self._armed = True
            current = (self.history.session_id, epoch)
            if current in self._lost_epochs or self._unscoped_failure:
                self.history.latch("PHYSICS_CHUNK_PREARM_LOSS")
            remaining = deque()
            remaining_samples = 0
            while self._pending:
                chunk, receipt_ns, scope = self._pending.popleft()
                if scope[0] == current[0] and scope[1] < epoch:
                    continue
                if scope[1] > epoch and scope[0] == current[0]:
                    remaining.append((chunk, receipt_ns, scope))
                    remaining_samples += len(chunk.samples)
                    self.history.latch("PHYSICS_CHUNK_FUTURE_EPOCH")
                    continue
                if self.history.hazard is None:
                    self._consume(chunk, receipt_ns, scope)
            self._pending = remaining
            self._pending_samples = remaining_samples
            self._lost_epochs = {scope for scope in self._lost_epochs
                                 if scope[0] != current[0] or scope[1] >= epoch}
            self._unscoped_failure = False
            self._notify()
            if self.history.hazard is not None:
                raise ValueError("PHYSICS_CLOCK_ARM_INVALID")
            return epoch
