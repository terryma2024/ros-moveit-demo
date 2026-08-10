"""Bounded stable-window physical grasp evidence."""

from dataclasses import dataclass
import time
from typing import Callable

from ..domain import Failure, FailureCategory


@dataclass(frozen=True, slots=True)
class GraspSample:
    simulation_session_id: str
    policy_bundle_sha256: str
    monotonic_time_s: float
    fixed_contact: bool
    moving_contact: bool
    required_wall: str
    forbidden_contacts: frozenset[str]
    penetration_m: float
    q6_position: float
    q6_velocity: float
    contact_height_m: float
    object_position: tuple[float, float, float]


@dataclass(frozen=True, slots=True)
class StabilizedGraspEvidence:
    simulation_session_id: str
    policy_bundle_sha256: str
    sample_count: int
    representative: GraspSample | None
    failure: Failure | None


class PhysicalGraspStabilizer:
    def __init__(self, source: Callable[[], GraspSample | None], policy_bundle_sha256: str,
                 progress: Callable[[], None] = lambda: None) -> None:
        self._source, self._fingerprint, self._progress = source, policy_bundle_sha256, progress

    def capture(self, session_id: str, window_s: float) -> StabilizedGraspEvidence:
        deadline = time.monotonic() + window_s; accepted = []
        mismatch = None
        while time.monotonic() < deadline:
            sample = self._source()
            if sample is not None:
                if sample.policy_bundle_sha256 != self._fingerprint:
                    mismatch = Failure(FailureCategory.OBSERVATION, "PHYSICAL_GRASP_EVIDENCE_FINGERPRINT_MISMATCH", "fingerprint differs")
                elif sample.simulation_session_id == session_id:
                    accepted.append(sample)
                    if len(accepted) >= 2: break
            self._progress(); time.sleep(.0001)
        if not accepted:
            failure = mismatch or Failure(FailureCategory.OBSERVATION, "PHYSICAL_GRASP_STABLE_TIMEOUT", "no fresh stable samples")
            return StabilizedGraspEvidence(session_id, self._fingerprint, 0, None, failure)
        return StabilizedGraspEvidence(session_id, self._fingerprint, len(accepted), accepted[-1], None)
