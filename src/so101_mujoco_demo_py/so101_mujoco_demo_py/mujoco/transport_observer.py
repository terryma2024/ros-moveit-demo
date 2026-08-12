"""Typed force policy and lossless dynamic-transport ROS evidence adapter."""

from __future__ import annotations

import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from so101_mujoco_demo_py.dynamic_transport_evidence import (
    AtomicTransportEvidenceStore,
    ContactForceMode,
    DynamicTransportRun,
    EvidenceInvalid,
    PhysicsContactSample,
    PhysicsStepChunk,
    PhysicsStepSample,
    TransportBoundary,
    TransportBoundaryKind,
)


class ReactionLatencyInvalid(EvidenceInvalid):
    """Raised when a diagnostic stop cannot meet its registered reaction bound."""


@dataclass(frozen=True, slots=True)
class ForceDecision:
    cancel: bool
    static_threshold_crossed: bool
    diagnostic_hazard_breached: bool
    reason: str | None


@dataclass(frozen=True, slots=True)
class HazardLatch:
    simulation_session_id: str
    reset_epoch: int
    physics_step: int
    simulation_time_s: float
    force_n: float
    threshold_n: float
    evidence_loss: bool


@dataclass(frozen=True, slots=True)
class CancellationAck:
    simulation_session_id: str
    reset_epoch: int
    hazard_physics_step: int
    request_sequence: int
    observed_physics_step: int
    observed_simulation_time_s: float


class _GoalHandleBoundaryProxy:
    def __init__(self, wrapped: Any, on_cancellation_requested) -> None:
        self._wrapped = wrapped
        self._on_cancellation_requested = on_cancellation_requested

    def __getattr__(self, name: str) -> Any:
        return getattr(self._wrapped, name)

    def cancel_goal_async(self):
        try:
            self._on_cancellation_requested()
        except Exception:
            pass
        return self._wrapped.cancel_goal_async()


class _GoalFutureBoundaryProxy:
    def __init__(self, wrapped: Any, on_cancellation_requested) -> None:
        self._wrapped = wrapped
        self._on_cancellation_requested = on_cancellation_requested

    def done(self):
        return self._wrapped.done()

    def result(self):
        handle = self._wrapped.result()
        if handle is None:
            return None
        return _GoalHandleBoundaryProxy(handle, self._on_cancellation_requested)


class BoundaryActionClient:
    """Transparent ActionClient proxy that observes dispatch and cancellation calls."""

    def __init__(self, wrapped: Any, *, on_goal_dispatched, on_cancellation_requested) -> None:
        self._wrapped = wrapped
        self._on_goal_dispatched = on_goal_dispatched
        self._on_cancellation_requested = on_cancellation_requested

    def wait_for_server(self, *, timeout_sec: float):
        return self._wrapped.wait_for_server(timeout_sec=timeout_sec)

    def send_goal_async(self, goal: Any):
        future = self._wrapped.send_goal_async(goal)
        self._on_goal_dispatched()
        return _GoalFutureBoundaryProxy(future, self._on_cancellation_requested)


def _positive_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be numeric")
    if not math.isfinite(value) or value <= 0.0:
        raise ValueError(f"{name} must be finite and positive")


def check_force(
    force_n: float,
    mode: ContactForceMode,
    *,
    static_threshold_n: float,
    diagnostic_stop_n: float,
) -> ForceDecision:
    """Return the explicit phase-aware decision without a time-based grace period."""

    if not isinstance(mode, ContactForceMode):
        raise TypeError("mode must be ContactForceMode")
    _positive_finite("static_threshold_n", static_threshold_n)
    _positive_finite("diagnostic_stop_n", diagnostic_stop_n)
    if isinstance(force_n, bool) or not isinstance(force_n, (int, float)):
        raise TypeError("force_n must be numeric")
    if not math.isfinite(force_n) or force_n < 0.0:
        raise ValueError("force_n must be finite and non-negative")
    shadow_crossed = force_n > static_threshold_n
    hazard = force_n >= diagnostic_stop_n
    static_failure = mode is ContactForceMode.PRE_TRANSPORT_STATIC_HOLD and shadow_crossed
    if hazard:
        reason = "diagnostic hazard boundary reached"
    elif static_failure:
        reason = "static force boundary exceeded"
    else:
        reason = None
    return ForceDecision(
        cancel=hazard or static_failure,
        static_threshold_crossed=shadow_crossed,
        diagnostic_hazard_breached=hazard,
        reason=reason,
    )


def _vector3(value: Any) -> tuple[float, float, float]:
    return float(value.x), float(value.y), float(value.z)


def _contact(value: Any, side: str) -> PhysicsContactSample:
    return PhysicsContactSample(
        side=side,
        object_body=str(value.body1),
        object_geom=str(value.geom1),
        other_body=str(value.body2),
        other_geom=str(value.geom2),
        signed_distance_m=float(value.signed_distance_m),
        normal_force_n=float(value.normal_force_n),
        normal_world=_vector3(value.normal_world),
    )


def _step(value: Any) -> PhysicsStepSample:
    pose = value.object_pose_world
    twist = value.object_twist_world
    return PhysicsStepSample(
        simulation_session_id=str(value.simulation_session_id),
        reset_epoch=int(value.reset_epoch),
        physics_step=int(value.physics_step),
        simulation_time_s=float(value.simulation_time_s),
        object_pose_world_xyz_xyzw=(
            float(pose.position.x),
            float(pose.position.y),
            float(pose.position.z),
            float(pose.orientation.x),
            float(pose.orientation.y),
            float(pose.orientation.z),
            float(pose.orientation.w),
        ),
        object_twist_world_linear_angular=(*_vector3(twist.linear), *_vector3(twist.angular)),
        maximum_normal_force_n=float(value.maximum_normal_force_n),
        left_fingertip_total_normal_force_n=float(value.left_fingertip_total_normal_force_n),
        right_fingertip_total_normal_force_n=float(value.right_fingertip_total_normal_force_n),
        fingertip_max_single_contact_force_n=float(value.fingertip_max_single_contact_force_n),
        global_max_single_contact_force_n=float(value.global_max_single_contact_force_n),
        left_fingertip_compression_m=float(value.left_fingertip_compression_m),
        right_fingertip_compression_m=float(value.right_fingertip_compression_m),
        net_contact_force_world_n=_vector3(value.net_contact_force_world_n),
        truncated=bool(value.truncated),
        left_fingertip_contacts=tuple(
            _contact(item, "left") for item in value.left_fingertip_contacts
        ),
        right_fingertip_contacts=tuple(
            _contact(item, "right") for item in value.right_fingertip_contacts
        ),
        other_object_contacts=tuple(
            _contact(item, "other") for item in value.other_object_contacts
        ),
    )


def convert_chunk(message: Any) -> PhysicsStepChunk:
    samples = tuple(_step(item) for item in message.samples)
    return PhysicsStepChunk(
        chunk_sequence=int(message.chunk_sequence),
        simulation_session_id=str(message.simulation_session_id),
        reset_epoch=int(message.reset_epoch),
        first_physics_step=int(message.first_physics_step),
        last_physics_step=int(message.last_physics_step),
        first_simulation_time_s=float(message.first_simulation_time_s),
        last_simulation_time_s=float(message.last_simulation_time_s),
        failed_publish_attempts=int(message.failed_publish_attempts),
        evidence_loss=bool(message.evidence_loss),
        samples=samples,
    )


def convert_hazard(message: Any) -> HazardLatch:
    return HazardLatch(
        simulation_session_id=str(message.simulation_session_id),
        reset_epoch=int(message.reset_epoch),
        physics_step=int(message.physics_step),
        simulation_time_s=float(message.simulation_time_s),
        force_n=float(message.force_n),
        threshold_n=float(message.threshold_n),
        evidence_loss=bool(message.evidence_loss),
    )


def convert_cancellation_ack(message: Any) -> CancellationAck:
    return CancellationAck(
        simulation_session_id=str(message.simulation_session_id),
        reset_epoch=int(message.reset_epoch),
        hazard_physics_step=int(message.hazard_physics_step),
        request_sequence=int(message.request_sequence),
        observed_physics_step=int(message.observed_physics_step),
        observed_simulation_time_s=float(message.observed_simulation_time_s),
    )


class DynamicTransportEvidenceObserver:
    """Checkpoint chunks and retain the first physical-step hazard notification."""

    def __init__(
        self,
        *,
        simulation_session_id: str,
        reset_epoch: int,
        store: AtomicTransportEvidenceStore,
        maximum_reaction_steps: int,
        node: Any | None = None,
        chunk_topic: str = "/so101/simulation/physics_step_chunks",
        hazard_topic: str = "/so101/simulation/physics_hazard",
        cancellation_request_topic: str = "/so101/simulation/physics_cancellation_request",
        cancellation_ack_topic: str = "/so101/simulation/physics_cancellation_ack",
    ) -> None:
        if not simulation_session_id:
            raise ValueError("simulation_session_id must be non-empty")
        if reset_epoch < 0:
            raise ValueError("reset_epoch must be non-negative")
        if maximum_reaction_steps < 0:
            raise ValueError("maximum_reaction_steps must be non-negative")
        self._session_id = simulation_session_id
        self._reset_epoch = reset_epoch
        self._store = store
        self._maximum_reaction_steps = maximum_reaction_steps
        self._lock = threading.Lock()
        self._last_step: int | None = None
        self._last_chunk_sequence: int | None = None
        self._hazard: HazardLatch | None = None
        self._boundaries: list[TransportBoundary] = []
        self._chunks: list[PhysicsStepChunk] = []
        self._cancellation_request_step: int | None = None
        self._reaction_upper_bound_steps: int | None = None
        self._request_sequence = 0
        self._outstanding_request_sequence: int | None = None
        self._cancellation_request_publisher: Any | None = None
        self._invalid_reason: str | None = None
        self._subscriptions: list[Any] = []
        if node is not None:
            from rclpy.qos import QoSProfile, ReliabilityPolicy
            from so101_mujoco_support.msg import (
                PhysicsCancellationAck,
                PhysicsCancellationRequest,
                PhysicsHazardLatch,
                PhysicsStepEvidenceChunk,
            )

            reliable = QoSProfile(depth=20, reliability=ReliabilityPolicy.RELIABLE)
            self._subscriptions = [
                node.create_subscription(
                    PhysicsStepEvidenceChunk, chunk_topic, self._chunk_callback, reliable
                ),
                node.create_subscription(
                    PhysicsHazardLatch, hazard_topic, self._hazard_callback, reliable
                ),
                node.create_subscription(
                    PhysicsCancellationAck,
                    cancellation_ack_topic,
                    self._cancellation_ack_callback,
                    reliable,
                ),
            ]
            self._cancellation_request_type = PhysicsCancellationRequest
            self._cancellation_request_publisher = node.create_publisher(
                PhysicsCancellationRequest, cancellation_request_topic, reliable
            )

    @property
    def boundaries(self) -> tuple[TransportBoundary, ...]:
        with self._lock:
            return tuple(self._boundaries)

    @property
    def hazard(self) -> HazardLatch | None:
        with self._lock:
            return self._hazard

    @property
    def invalid_reason(self) -> str | None:
        with self._lock:
            return self._invalid_reason

    @property
    def latest_physics_step(self) -> int | None:
        with self._lock:
            return self._last_step

    @property
    def cancellation_request_upper_bound_step(self) -> int | None:
        with self._lock:
            return self._cancellation_request_step

    @property
    def reaction_upper_bound_steps(self) -> int | None:
        with self._lock:
            return self._reaction_upper_bound_steps

    def _record_invalid(self, error: Exception) -> None:
        with self._lock:
            if self._invalid_reason is None:
                self._invalid_reason = f"{type(error).__name__}: {error}"

    def _chunk_callback(self, message: Any) -> None:
        try:
            self.accept_chunk(convert_chunk(message))
        except (EvidenceInvalid, TypeError, ValueError, AttributeError) as error:
            self._record_invalid(error)

    def _hazard_callback(self, message: Any) -> None:
        try:
            self.accept_hazard(convert_hazard(message))
        except (EvidenceInvalid, TypeError, ValueError, AttributeError) as error:
            self._record_invalid(error)

    def _cancellation_ack_callback(self, message: Any) -> None:
        try:
            self.accept_cancellation_ack(convert_cancellation_ack(message))
        except (EvidenceInvalid, TypeError, ValueError, AttributeError) as error:
            self._record_invalid(error)

    def accept_chunk(self, chunk: PhysicsStepChunk) -> str:
        if chunk.simulation_session_id != self._session_id:
            raise EvidenceInvalid("chunk simulation session mismatch")
        if chunk.reset_epoch != self._reset_epoch:
            raise EvidenceInvalid("chunk reset epoch mismatch")
        if chunk.evidence_loss:
            raise EvidenceInvalid("chunk evidence loss latched")
        if not chunk.samples:
            raise EvidenceInvalid("empty physics-step chunk")
        with self._lock:
            expected_sequence = (
                chunk.chunk_sequence
                if self._last_chunk_sequence is None
                else self._last_chunk_sequence + 1
            )
            if chunk.chunk_sequence != expected_sequence:
                raise EvidenceInvalid("chunk sequence mismatch")
            if self._last_step is not None and chunk.first_physics_step != self._last_step + 1:
                raise EvidenceInvalid("physics-step chunk gap")
            digest = self._store.checkpoint_chunk(chunk)
            self._chunks.append(chunk)
            self._last_chunk_sequence = chunk.chunk_sequence
            self._last_step = chunk.last_physics_step
            return digest

    def accept_hazard(self, hazard: HazardLatch) -> None:
        if hazard.simulation_session_id != self._session_id:
            raise EvidenceInvalid("hazard simulation session mismatch")
        if hazard.reset_epoch != self._reset_epoch:
            raise EvidenceInvalid("hazard reset epoch mismatch")
        if hazard.evidence_loss:
            raise EvidenceInvalid("hazard reports evidence loss")
        if hazard.force_n < hazard.threshold_n:
            raise EvidenceInvalid("hazard force is below its inclusive threshold")
        with self._lock:
            if self._hazard is None:
                self._hazard = hazard

    def _checkpoint_boundary(self, kind: TransportBoundaryKind, waypoint: int) -> TransportBoundary:
        with self._lock:
            if self._last_step is None:
                raise EvidenceInvalid("cannot bind boundary before a physics-step chunk")
            boundary = TransportBoundary(kind, waypoint, self._last_step)
            self._store.checkpoint_boundary(boundary)
            self._boundaries.append(boundary)
            return boundary

    def mark_goal_dispatched(self, *, waypoint: int) -> TransportBoundary:
        with self._lock:
            first = not self._boundaries
        if first:
            phase = self._checkpoint_boundary(TransportBoundaryKind.PHASE_START, waypoint)
            self._checkpoint_boundary(TransportBoundaryKind.WAYPOINT_START, waypoint)
            return phase
        return self._checkpoint_boundary(TransportBoundaryKind.WAYPOINT_START, waypoint)

    def mark_waypoint_complete(self, *, waypoint: int) -> TransportBoundary:
        return self._checkpoint_boundary(TransportBoundaryKind.WAYPOINT_END, waypoint)

    def mark_phase_complete(self, *, waypoint: int) -> TransportBoundary:
        return self._checkpoint_boundary(TransportBoundaryKind.PHASE_END, waypoint)

    def mark_cancellation_requested(self, physics_step: int) -> int:
        with self._lock:
            hazard = self._hazard
        if hazard is None:
            raise EvidenceInvalid("cancellation request has no hazard latch")
        reaction_steps = physics_step - hazard.physics_step
        if reaction_steps < 0:
            raise EvidenceInvalid("cancellation request precedes hazard latch")
        with self._lock:
            self._cancellation_request_step = physics_step
            self._reaction_upper_bound_steps = reaction_steps
        if reaction_steps > self._maximum_reaction_steps:
            raise ReactionLatencyInvalid(
                f"cancellation exceeded {self._maximum_reaction_steps} physics steps"
            )
        return reaction_steps

    def publish_cancellation_request(self) -> int:
        with self._lock:
            hazard = self._hazard
            publisher = self._cancellation_request_publisher
            message_type = getattr(self, "_cancellation_request_type", None)
            sequence = self._request_sequence
            self._request_sequence += 1
            self._outstanding_request_sequence = sequence
        if hazard is None:
            raise EvidenceInvalid("cancellation request has no hazard latch")
        if publisher is None or message_type is None:
            raise EvidenceInvalid("cancellation request publisher is unavailable")
        message = message_type()
        message.simulation_session_id = self._session_id
        message.reset_epoch = self._reset_epoch
        message.hazard_physics_step = hazard.physics_step
        message.request_sequence = sequence
        publisher.publish(message)
        return sequence

    def accept_cancellation_ack(self, ack: CancellationAck) -> int:
        with self._lock:
            hazard = self._hazard
            expected_sequence = self._outstanding_request_sequence
        if ack.simulation_session_id != self._session_id:
            raise EvidenceInvalid("cancellation ack simulation session mismatch")
        if ack.reset_epoch != self._reset_epoch:
            raise EvidenceInvalid("cancellation ack reset epoch mismatch")
        if hazard is None:
            raise EvidenceInvalid("cancellation ack has no hazard latch")
        if ack.hazard_physics_step != hazard.physics_step:
            raise EvidenceInvalid("cancellation ack hazard step mismatch")
        if expected_sequence is not None and ack.request_sequence != expected_sequence:
            raise EvidenceInvalid("cancellation ack request sequence mismatch")
        return self.mark_cancellation_requested(ack.observed_physics_step)

    def record_invalid(self, error: Exception) -> None:
        self._record_invalid(error)

    def build_run(
        self, *, physics_timestep_s: float, physical_transport_outcome: str
    ) -> DynamicTransportRun:
        with self._lock:
            chunks = tuple(self._chunks)
            boundaries = tuple(self._boundaries)
            invalid_reason = self._invalid_reason
        if invalid_reason is not None:
            raise EvidenceInvalid(invalid_reason)
        return DynamicTransportRun(
            run_id=self._store.run_id,
            simulation_session_id=self._session_id,
            reset_epoch=self._reset_epoch,
            physics_timestep_s=physics_timestep_s,
            chunks=chunks,
            boundaries=boundaries,
            physical_transport_outcome=physical_transport_outcome,
        )

    def close_success(self, *, physical_transport_outcome: str) -> Path:
        return self._store.close_complete(
            physical_transport_outcome=physical_transport_outcome,
        )

    def close_safety_abort(self) -> Path:
        with self._lock:
            hazard = self._hazard
            cancellation = self._cancellation_request_step
        if hazard is None or cancellation is None:
            raise EvidenceInvalid("safety abort is missing hazard or cancellation evidence")
        with self._lock:
            last_step = self._last_step
        if last_step is None or last_step < hazard.physics_step:
            raise EvidenceInvalid("safety abort raw evidence does not include the trigger step")
        return self._store.close_partial(
            outcome_class="VALID_SAFETY_ABORT",
            trigger_physics_step=hazard.physics_step,
            trigger_simulation_time_s=hazard.simulation_time_s,
            trigger_force_n=hazard.force_n,
            cancellation_request_physics_step=cancellation,
            reaction_steps=cancellation - hazard.physics_step,
            reaction_bound_kind="plugin_ack_upper_bound",
            maximum_reaction_steps=self._maximum_reaction_steps,
        )

    def close_invalid_abort(self) -> Path:
        with self._lock:
            hazard = self._hazard
            cancellation = self._cancellation_request_step
            invalid_reason = self._invalid_reason
        if hazard is None or invalid_reason is None:
            raise EvidenceInvalid("invalid abort is missing hazard or invalid reason")
        terminal: dict[str, Any] = {
            "invalid_reason": invalid_reason,
            "maximum_reaction_steps": self._maximum_reaction_steps,
            "reaction_bound_kind": "plugin_ack_upper_bound",
        }
        if cancellation is not None:
            terminal.update(
                {
                    "cancellation_request_physics_step": cancellation,
                    "reaction_steps": cancellation - hazard.physics_step,
                }
            )
        return self._store.close_partial(
            outcome_class="INVALID_EVIDENCE",
            trigger_physics_step=hazard.physics_step,
            **terminal,
        )

    def close_invalid(self, error: Exception) -> Path:
        self._record_invalid(error)
        with self._lock:
            invalid_reason = self._invalid_reason
            last_step = self._last_step
        assert invalid_reason is not None
        terminal: dict[str, Any] = {}
        if last_step is not None:
            terminal["last_physics_step"] = last_step
        return self._store.close_invalid(
            invalid_reason=invalid_reason,
            **terminal,
        )
