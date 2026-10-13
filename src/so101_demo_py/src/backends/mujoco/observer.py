"""Strict adapter from the atomic MuJoCo ROS message to backend-neutral evidence."""

from __future__ import annotations

import json
import math
import sys
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from rclpy.qos import (
    DurabilityPolicy,
    HistoryPolicy,
    QoSProfile,
    ReliabilityPolicy,
)
from so101_demo.core.simulation.types import (
    ContactEvidence,
    ObjectState,
    ReceivedSimulationEvidence,
    SimulationEvidence,
)
from so101_mujoco_support.msg import SimulationEvidence as RosSimulationEvidence


class EvidenceRejected(RuntimeError):
    """Raised when an atomic message violates the configured stream contract."""


class EvidenceStale(RuntimeError):
    """Raised when no sufficiently recent accepted atomic message exists."""


ATOMIC_EVIDENCE_QOS = QoSProfile(
    history=HistoryPolicy.KEEP_LAST,
    depth=1,
    reliability=ReliabilityPolicy.RELIABLE,
    durability=DurabilityPolicy.TRANSIENT_LOCAL,
)


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
        subscription_depth: int = 1,
        monotonic: Callable[[], float] = time.monotonic,
        on_hazard: Callable[[str], None] | None = None,
        history_capacity: int = 256,
        on_sequence_gap: Callable[[int, int], None] | None = None,
        accept_truncated: bool = False,
        rebaseline_stale_join: bool = False,
    ) -> None:
        if not simulation_session_id:
            raise ValueError("simulation_session_id must be non-empty")
        if not math.isfinite(max_age_s) or max_age_s <= 0.0:
            raise ValueError("max_age_s must be finite and positive")
        if on_hazard is not None and not callable(on_hazard):
            raise ValueError("on_hazard must be callable")
        if on_sequence_gap is not None and not callable(on_sequence_gap):
            raise ValueError("on_sequence_gap must be callable")
        if (type(subscription_depth) is not int
                or not 1 <= subscription_depth <= 256):
            raise ValueError("subscription depth must be an integer from 1 to 256")
        if type(history_capacity) is not int or not 1 <= history_capacity <= 4096:
            raise ValueError("history capacity must be an integer from 1 to 4096")
        self._session_id = simulation_session_id
        self._max_age_s = max_age_s
        self._monotonic = monotonic
        self._on_hazard = on_hazard
        # When given, a publisher sequence gap is data completeness: it is reported to this port
        # as (previous, current) and is not a strict hazard. Without it the gap stays a hazard.
        self._on_sequence_gap = on_sequence_gap
        # Teacher policy v3: a sample whose contact list was truncated still carries the cup state, so it keeps the control evidence
        # fresh; it is counted (and offered to the taps, which mark the telemetry incomplete) instead of rejected. Default: rejected.
        self._accept_truncated = accept_truncated
        # A one-shot observer that joins a long-lived publisher is first handed the publisher's transient-local replay (the
        # newest samples of the PREVIOUS epoch when it joins within the replay depth of a reset). A depth-1 reader keeps only
        # the newest of the rest, so the new epoch's step-zero sample may never reach it. With this set, a later epoch seen
        # while the observer still holds only that one joining sample becomes the new baseline instead of a hazard. It is a
        # statement about what a late joiner can know, so continuous observers (reset client, Teacher) leave it off.
        self._rebaseline_stale_join = rebaseline_stale_join
        self._lock = threading.Lock()
        self._latest: SimulationEvidence | None = None
        self._received_at_s: float | None = None
        self._history: deque[ReceivedSimulationEvidence] = deque(maxlen=history_capacity)
        self._strict_hazard: str | None = None
        self._gap_log: deque = deque(maxlen=16)   # what each gap looked like
        self._rejection_log: deque = deque(maxlen=16)
        self._callback_count = 0
        self._rejected_count = 0
        self._truncated_count = 0
        self._last_rejection = ""
        # Observation-only taps (Teacher policy v3 process telemetry): called with (evidence, receipt) after a message is accepted
        self._taps: list[Callable[[SimulationEvidence, float], None]] = []
        qos = ATOMIC_EVIDENCE_QOS if subscription_depth == 1 else QoSProfile(
            history=HistoryPolicy.KEEP_LAST,
            depth=subscription_depth,
            reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        self._subscription = node.create_subscription(
            RosSimulationEvidence, topic, self._callback, qos
        )

    def _callback(self, message: RosSimulationEvidence) -> None:
        received_at_s = self._monotonic()
        with self._lock:
            self._callback_count += 1
            previous_hazard = self._strict_hazard
        try:
            self.accept(message, received_at_s=received_at_s)
        except EvidenceRejected as error:
            with self._lock:
                self._rejection_log.append({"reason": str(error), "callback_count": self._callback_count,
                                            "received_monotonic_s": received_at_s})
                self._rejected_count += 1
                self._last_rejection = str(error)
                self._strict_hazard = str(error)
        with self._lock:
            current_hazard = self._strict_hazard
        if current_hazard is not None and current_hazard != previous_hazard and self._on_hazard is not None:
            self._on_hazard(current_hazard)

    @property
    def callback_count(self) -> int:
        with self._lock:
            return self._callback_count

    def add_tap(self, tap: Callable[[SimulationEvidence, float], None]) -> None:
        """Offer every accepted evidence message to `tap` (observation only: a tap that raises is ignored)."""
        self._taps.append(tap)

    @property
    def truncated_count(self) -> int:
        """How many messages arrived with a truncated contact list (rejected, or accepted when `accept_truncated` is set)."""
        with self._lock:
            return self._truncated_count

    @property
    def rejected_count(self) -> int:
        with self._lock:
            return self._rejected_count

    @property
    def last_rejection(self) -> str:
        with self._lock:
            return self._last_rejection

    @property
    def publisher_count(self) -> int:
        return self._subscription.get_publisher_count()

    def accept(self, message: Any, *, received_at_s: float | None = None) -> None:
        evidence = convert_message(message)
        if evidence.simulation_session_id != self._session_id:
            raise EvidenceRejected(
                f"session mismatch: expected {self._session_id}, got {evidence.simulation_session_id}"
            )
        if evidence.truncated:
            with self._lock:
                self._truncated_count += 1
            if not self._accept_truncated:
                raise EvidenceRejected("truncated atomic evidence")
        receipt = self._monotonic() if received_at_s is None else received_at_s
        if not math.isfinite(receipt) or receipt < 0.0:
            raise EvidenceRejected("receipt time must be finite and non-negative")
        gap = None
        with self._lock:
            previous = self._latest
            if previous is not None:
                if evidence.publisher_sequence <= previous.publisher_sequence:
                    raise EvidenceRejected("publisher sequence must increase")
                if evidence.reset_epoch < previous.reset_epoch:
                    raise EvidenceRejected("reset epoch moved backward")
                rebaseline = (self._rebaseline_stale_join and len(self._history) == 1
                              and evidence.reset_epoch > previous.reset_epoch)
                if rebaseline:
                    self._rebaseline_stale_join = False   # the join is a one-time event
                elif evidence.reset_epoch > previous.reset_epoch + 1:
                    raise EvidenceRejected("reset epoch skipped")
                elif evidence.reset_epoch == previous.reset_epoch:
                    if evidence.simulation_step < previous.simulation_step:
                        raise EvidenceRejected("simulation step moved backward")
                    if evidence.simulation_step == previous.simulation_step and not evidence.paused:
                        raise EvidenceRejected("same simulation step requires paused evidence")
                elif evidence.simulation_step != 0:
                    raise EvidenceRejected("new reset epoch must begin at simulation step zero")
            self._latest = evidence
            self._received_at_s = receipt
            if previous is not None and evidence.reset_epoch != previous.reset_epoch:
                self._history.clear()
                self._strict_hazard = None
            elif previous is not None and evidence.publisher_sequence != previous.publisher_sequence + 1:
                if self._on_sequence_gap is None:
                    self._strict_hazard = "atomic evidence publisher sequence gap"
                else:
                    gap = (previous.publisher_sequence, evidence.publisher_sequence)
                self._gap_log.append({
                    "previous_sequence": previous.publisher_sequence, "sequence": evidence.publisher_sequence,
                    "missing": evidence.publisher_sequence - previous.publisher_sequence - 1,
                    "step": evidence.simulation_step, "previous_step": previous.simulation_step,
                    "sim_time_s": evidence.simulation_time_s, "callback_count": self._callback_count,
                    "received_monotonic_s": receipt})
            self._history.append(ReceivedSimulationEvidence(evidence, receipt))
        for tap in self._taps:
            try:
                tap(evidence, receipt)
            except Exception:
                pass  # a telemetry tap can never turn an accepted message into a rejection
        if gap is not None:
            try:
                self._on_sequence_gap(*gap)
            except Exception:
                pass  # an audit port can never turn a completeness observation into a rejection

    def diagnostics(self) -> dict:
        """Observation only: the gaps and rejections this observer saw (bounded), and its callback count."""
        with self._lock:
            return {"gaps": list(self._gap_log), "rejections": list(self._rejection_log),
                    "callbacks": self._callback_count, "retained": len(self._history)}

    def latest_summary(self) -> dict | None:
        """Observation only: what the newest accepted message said and how old it is (None before the first one)."""
        with self._lock:
            evidence, received_at_s = self._latest, self._received_at_s
        if evidence is None or received_at_s is None:
            return None
        return {"paused": evidence.paused, "simulation_time_s": evidence.simulation_time_s,
                "publisher_sequence": evidence.publisher_sequence, "simulation_step": evidence.simulation_step,
                "reset_epoch": evidence.reset_epoch, "age_s": round(self._monotonic() - received_at_s, 3)}

    def recent_summaries(self, limit: int = 5) -> list[dict]:
        """Observation only: the newest accepted messages (oldest first), whatever their age, for a failure to name."""
        with self._lock:
            frames = list(self._history)[-limit:]
        now = self._monotonic()
        return [{"paused": item.evidence.paused, "reset_epoch": item.evidence.reset_epoch,
                 "simulation_step": item.evidence.simulation_step, "publisher_sequence": item.evidence.publisher_sequence,
                 "age_s": round(now - item.received_monotonic_s, 3)} for item in frames]

    def snapshot(self) -> SimulationEvidence:
        return self.snapshot_with_receipt().evidence

    def snapshot_with_receipt(self) -> ReceivedSimulationEvidence:
        with self._lock:
            evidence = self._latest
            received_at_s = self._received_at_s
        if evidence is None or received_at_s is None:
            raise EvidenceStale("no atomic evidence has been accepted")
        now = self._monotonic()
        age = now - received_at_s
        if not math.isfinite(age) or age < 0.0 or age > self._max_age_s:
            raise EvidenceStale(f"atomic evidence age {age:.3f}s exceeds {self._max_age_s:.3f}s")
        return ReceivedSimulationEvidence(evidence, received_at_s)

    def recent_with_receipts(self) -> tuple[ReceivedSimulationEvidence, ...]:
        """Fresh bounded history for a common physics-step join."""
        with self._lock:
            values = tuple(self._history)
            hazard = self._strict_hazard
        if hazard is not None:
            raise EvidenceRejected(hazard)
        if not values:
            raise EvidenceStale("no atomic evidence has been accepted")
        now = self._monotonic()
        if not math.isfinite(now) or now < values[-1].received_monotonic_s:
            raise EvidenceStale("atomic evidence receipt is in the future")
        fresh = tuple(value for value in values
                      if 0 <= now - value.received_monotonic_s <= self._max_age_s)
        if not fresh:
            raise EvidenceStale("no fresh atomic evidence remains")
        return fresh

    def retained_with_receipts(self) -> tuple[ReceivedSimulationEvidence, ...]:
        """Unfiltered retained history; diagnostics only, never a freshness or authority source."""
        with self._lock:
            return tuple(self._history)

    def original_records_after(self, publisher_sequence: int) -> tuple[ReceivedSimulationEvidence, ...]:
        """Drain originals by sequence; expired evidence is still retained audit input."""
        if type(publisher_sequence) is not int or publisher_sequence < 0:
            raise ValueError("retention sequence must be a nonnegative integer")
        with self._lock:
            if self._strict_hazard is not None:
                raise EvidenceRejected(self._strict_hazard)
            values = tuple(record for record in self._history
                           if record.evidence.publisher_sequence > publisher_sequence)
            if self._on_sequence_gap is not None and any(
                    later.evidence.publisher_sequence != earlier.evidence.publisher_sequence + 1
                    for earlier, later in zip(values, values[1:])):
                # With an audit port a gap is not a sticky hazard, but the records handed out as the retained
                # original must be gap-free: a gap inside them is data loss (a gap before them is not in the data).
                raise EvidenceRejected("atomic evidence publisher sequence gap")
            if values and values[0].evidence.publisher_sequence != publisher_sequence + 1:
                # Observation only (D17): record the retention facts; never let this line mask the rejection.
                try:
                    print("WORLD_EVIDENCE_RETENTION_LOST " + json.dumps({
                        "cursor": publisher_sequence,
                        "first_retained_sequence": values[0].evidence.publisher_sequence,
                        "last_retained_sequence": values[-1].evidence.publisher_sequence,
                        "retained": len(self._history), "capacity": self._history.maxlen}),
                        file=sys.stderr, flush=True)
                except Exception:
                    pass
                raise EvidenceRejected("atomic evidence retention prefix lost")
            return values
