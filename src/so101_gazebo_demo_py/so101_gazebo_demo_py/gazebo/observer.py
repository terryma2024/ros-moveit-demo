"""Thread-safe latest Gazebo world observation container."""

from dataclasses import dataclass
import math
import threading
import time


# Recalibrated 2026-08-09 (CP-AUTHORIZATION-CEILING-RECALIBRATION-001) from 0.000800002:
# solver limit 0.0013 minus 0.00005 measurability guard; above the observed bilateral
# moving-pad distribution max 0.001193 m and the proven physical grasp depth ~0.0010 m
# (EXP-PEN-DIAG-001-GRASP-229, cup carried by the +0.002 m micro-lift).
MOVING_PAD_MESH_PENETRATION_CEILING_M = 0.00125
SOLVER_REPORTED_CONTACT_DEPTH_LIMIT_M = 0.0013


@dataclass(frozen=True, slots=True)
class ContactPair:
    object_collision: str
    finger_collision: str
    depths_m: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    source_timestamp_s: float
    receipt_sequence: int


@dataclass(frozen=True, slots=True)
class SupportContactEvidence:
    supported: bool
    compound_owner_collision: str | None
    intended_support_collision: str
    minimum_depth_m: float | None
    maximum_depth_m: float | None
    accepted_depth_count: int
    rejected_depth_count: int


def evaluate_support_contact(
    contacts: list[ContactPair] | tuple[ContactPair, ...],
    intended_support_collision: str,
    minimum_depth_m: float,
) -> SupportContactEvidence:
    """Reduce real task-object/table contacts with calibrated solver-noise handling."""
    if not math.isfinite(minimum_depth_m) or minimum_depth_m > 0.0:
        raise ValueError("minimum support depth must be a finite non-positive value")
    accepted: list[float] = []
    observed_finite: list[float] = []
    rejected = 0
    owner: str | None = None
    for contact in contacts:
        if contact.finger_collision != intended_support_collision:
            continue
        owner = contact.object_collision
        for depth in contact.depths_m:
            if not math.isfinite(depth):
                rejected += 1
                continue
            observed_finite.append(depth)
            if depth >= minimum_depth_m:
                accepted.append(depth)
            else:
                rejected += 1
    return SupportContactEvidence(
        supported=bool(accepted),
        compound_owner_collision=owner,
        intended_support_collision=intended_support_collision,
        minimum_depth_m=min(observed_finite, default=None),
        maximum_depth_m=max(observed_finite, default=None),
        accepted_depth_count=len(accepted),
        rejected_depth_count=rejected,
    )


@dataclass(frozen=True, slots=True)
class BilateralContactEvidence:
    fixed_finger: bool
    moving_jaw: bool
    max_fixed_pad_penetration_m: float | None
    max_moving_pad_penetration_m: float | None
    within_solver_depth_limit: bool

    @property
    def bilateral(self) -> bool:
        return self.fixed_finger and self.moving_jaw and self.within_solver_depth_limit


def evaluate_bilateral_contact(
    contacts: list[ContactPair] | tuple[ContactPair, ...],
) -> BilateralContactEvidence:
    """Reduce physical near-wall pad contacts without accepting legacy geometry."""
    fixed_depths: list[float] = []
    moving_depths: list[float] = []
    for contact in contacts:
        if not contact.object_collision.endswith("::wall_near"):
            continue
        physical_depths = [
            depth for depth in contact.depths_m if math.isfinite(depth) and depth >= 0.0
        ]
        if not physical_depths:
            continue
        if "fixed_fingertip_pad_collision_" in contact.finger_collision:
            fixed_depths.extend(physical_depths)
        elif "moving_fingertip_pad_collision_" in contact.finger_collision:
            moving_depths.extend(physical_depths)
    fixed_max = max(fixed_depths, default=None)
    moving_max = max(moving_depths, default=None)
    within_solver_limit = (
        moving_max is not None and moving_max <= SOLVER_REPORTED_CONTACT_DEPTH_LIMIT_M
    )
    return BilateralContactEvidence(
        fixed_finger=fixed_max is not None,
        moving_jaw=moving_max is not None,
        max_fixed_pad_penetration_m=fixed_max,
        max_moving_pad_penetration_m=moving_max,
        within_solver_depth_limit=within_solver_limit,
    )


@dataclass(frozen=True, slots=True)
class WorldObservation:
    captured_monotonic_s: float
    object_pose_world: tuple[float, float, float, float, float, float, float] | None
    attached: bool | None
    fixed_finger_contact: bool
    moving_jaw_contact: bool
    max_penetration_m: float | None = None
    pose_source: SourceEvidence = SourceEvidence(0.0, 0)
    support_source: SourceEvidence = SourceEvidence(0.0, 0)


class GazeboWorldObserver:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._observation = WorldObservation(time.monotonic(), None, None, False, False)

    def update(self, observation: WorldObservation) -> None:
        with self._lock:
            self._observation = observation

    def observe(self) -> WorldObservation:
        with self._lock:
            return self._observation
