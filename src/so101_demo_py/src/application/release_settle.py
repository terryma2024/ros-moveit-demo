"""Bounded, cancellable collection for an active physical release epoch."""

import math
from dataclasses import dataclass
from typing import Callable

from ..core.outcome import (
    FinalPlacementResult,
    FinalPlacementSample,
    PhysicalOutcomePolicy,
    evaluate_final_placement,
)
from ..core.simulation.protocols import ReceiptTimedWorldObserver
from ..core.simulation.types import ContactEvidence, SimulationEvidence


@dataclass(frozen=True, slots=True)
class ReleaseSettleResult:
    status: str
    samples: tuple[FinalPlacementSample, ...]
    evaluation: FinalPlacementResult


@dataclass(frozen=True, slots=True)
class OutcomeCorroboration:
    moveit_detached: bool
    controller_healthy: bool
    safety_healthy: bool
    shadow_divergence_healthy: bool


def _matches_collision(contact: ContactEvidence, collision: str) -> bool:
    return collision in {
        contact.body1,
        contact.geom1,
        contact.body2,
        contact.geom2,
    }


def sample_from_simulation_evidence(
    evidence: SimulationEvidence,
    policy: PhysicalOutcomePolicy,
    release_epoch_id: str,
    corroboration: OutcomeCorroboration,
    observed_monotonic_s: float,
) -> FinalPlacementSample:
    """Convert Task 5 atomic evidence without importing a simulator-specific message."""
    support_contact = any(
        _matches_collision(contact, policy.intended_support_collision)
        and contact.signed_distance_m <= policy.minimum_support_signed_distance_m
        for contact in evidence.other_object_contacts
    )
    gripper_contact = bool(evidence.left_fingertip_contacts or evidence.right_fingertip_contacts)
    object_state = evidence.object_state
    return FinalPlacementSample(
        release_epoch_id=release_epoch_id,
        receipt_sequence=evidence.publisher_sequence,
        source_timestamp_s=evidence.simulation_time_s,
        observed_monotonic_s=observed_monotonic_s,
        pose_xyz_xyzw=object_state.position_world + object_state.orientation_xyzw,
        support_contact=support_contact,
        gripper_contact=gripper_contact,
        simulator_detached=True,
        moveit_detached=corroboration.moveit_detached,
        controller_healthy=corroboration.controller_healthy,
        safety_healthy=corroboration.safety_healthy,
        shadow_divergence_healthy=corroboration.shadow_divergence_healthy,
    )


class ReleaseSettleExecutor:
    def __init__(
        self,
        policy: PhysicalOutcomePolicy,
        observer: ReceiptTimedWorldObserver,
        corroborate: Callable[[], OutcomeCorroboration],
        monotonic: Callable[[], float],
        wait: Callable[[float], None],
        cancelled: Callable[[], bool],
    ) -> None:
        if not isinstance(observer, ReceiptTimedWorldObserver):
            raise TypeError("release settle requires receipt-timed simulation evidence")
        self._policy = policy
        self._observer = observer
        self._corroborate = corroborate
        self._monotonic = monotonic
        self._wait = wait
        self._cancelled = cancelled

    def run(
        self,
        release_epoch_id: str,
        release_marker_sequence: int,
        release_reset_epoch: int | None = None,
    ) -> ReleaseSettleResult:
        start = self._monotonic()
        samples: list[FinalPlacementSample] = []
        evaluation = evaluate_final_placement(
            (),
            self._policy,
            release_epoch_id,
            release_marker_sequence,
        )
        while self._monotonic() - start <= self._policy.settle_timeout_s:
            if self._cancelled():
                return ReleaseSettleResult("CANCELLED", tuple(samples), evaluation)
            received = self._observer.snapshot_with_receipt()
            observed_monotonic_s = self._monotonic()
            observation_age_s = observed_monotonic_s - received.received_monotonic_s
            fresh = (
                math.isfinite(observation_age_s)
                and 0.0 <= observation_age_s <= self._policy.max_observation_age_s
            )
            evidence = received.evidence
            if fresh and release_reset_epoch is None:
                release_reset_epoch = evidence.reset_epoch
            if fresh and evidence.reset_epoch == release_reset_epoch:
                samples.append(
                    sample_from_simulation_evidence(
                        evidence,
                        self._policy,
                        release_epoch_id,
                        self._corroborate(),
                        received.received_monotonic_s,
                    )
                )
            if len(samples) > self._policy.max_telemetry_samples:
                samples.pop(0)
            evaluation = evaluate_final_placement(
                tuple(samples),
                self._policy,
                release_epoch_id,
                release_marker_sequence,
            )
            if evaluation.success:
                return ReleaseSettleResult("SUCCEEDED", tuple(samples), evaluation)
            self._wait(self._policy.sample_interval_s)
        return ReleaseSettleResult("TIMED_OUT", tuple(samples), evaluation)
