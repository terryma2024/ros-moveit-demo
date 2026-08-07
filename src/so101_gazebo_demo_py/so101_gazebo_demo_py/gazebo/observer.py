"""Thread-safe latest Gazebo world observation container."""

from dataclasses import dataclass
import math
import threading
import time


MOVING_PAD_MESH_PENETRATION_CEILING_M = 0.000800002
SOLVER_REPORTED_CONTACT_DEPTH_LIMIT_M = 0.0013


@dataclass(frozen=True, slots=True)
class ContactPair:
    object_collision: str
    finger_collision: str
    depths_m: tuple[float, ...]


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
