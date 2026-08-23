"""Backend-neutral immutable world evidence values."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

Vector3 = tuple[float, float, float]
Quaternion = tuple[float, float, float, float]


def _finite_tuple(name: str, value: object, size: int) -> None:
    if not isinstance(value, tuple) or len(value) != size:
        raise TypeError(f"{name} must be an immutable {size}-tuple")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise TypeError(f"{name} must contain numbers")
    if not all(math.isfinite(float(item)) for item in value):
        raise ValueError(f"{name} must contain finite values")


def _identifier(name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


@dataclass(frozen=True, slots=True)
class PoseEvidence:
    position_m: Vector3
    orientation_xyzw: Quaternion

    def __post_init__(self) -> None:
        _finite_tuple("position_m", self.position_m, 3)
        _finite_tuple("orientation_xyzw", self.orientation_xyzw, 4)
        if math.isclose(sum(float(item) ** 2 for item in self.orientation_xyzw), 0.0):
            raise ValueError("orientation_xyzw must be non-zero")


@dataclass(frozen=True, slots=True)
class TwistEvidence:
    linear_m_s: Vector3
    angular_rad_s: Vector3

    def __post_init__(self) -> None:
        _finite_tuple("linear_m_s", self.linear_m_s, 3)
        _finite_tuple("angular_rad_s", self.angular_rad_s, 3)


@dataclass(frozen=True, slots=True)
class ContactEvidence:
    collision1: str
    collision2: str
    position_m: Vector3
    normal: Vector3
    normal_force_n: float
    backend_metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        _identifier("collision1", self.collision1)
        _identifier("collision2", self.collision2)
        _finite_tuple("position_m", self.position_m, 3)
        _finite_tuple("normal", self.normal, 3)
        if (
            isinstance(self.normal_force_n, bool)
            or not isinstance(self.normal_force_n, (int, float))
            or not math.isfinite(float(self.normal_force_n))
            or self.normal_force_n < 0.0
        ):
            raise ValueError("normal_force_n must be finite and non-negative")
        object.__setattr__(self, "backend_metadata", MappingProxyType(dict(self.backend_metadata)))


@dataclass(frozen=True, slots=True)
class WorldEvidence:
    backend: str
    session_id: str
    reset_epoch: int
    simulation_step: int
    simulation_time_s: float
    object_pose: PoseEvidence
    object_twist: TwistEvidence
    contacts: tuple[ContactEvidence, ...]
    evidence_loss: bool
    truncated: bool
    backend_metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        _identifier("backend", self.backend)
        _identifier("session_id", self.session_id)
        for name in ("reset_epoch", "simulation_step"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if (
            isinstance(self.simulation_time_s, bool)
            or not isinstance(self.simulation_time_s, (int, float))
            or not math.isfinite(float(self.simulation_time_s))
            or self.simulation_time_s < 0.0
        ):
            raise ValueError("simulation_time_s must be finite and non-negative")
        if not isinstance(self.evidence_loss, bool) or not isinstance(self.truncated, bool):
            raise TypeError("evidence flags must be boolean")
        object.__setattr__(self, "backend_metadata", MappingProxyType(dict(self.backend_metadata)))


@dataclass(frozen=True, slots=True)
class ReceivedWorldEvidence:
    evidence: WorldEvidence
    received_monotonic_s: float

    def __post_init__(self) -> None:
        if not math.isfinite(self.received_monotonic_s) or self.received_monotonic_s < 0.0:
            raise ValueError("received_monotonic_s must be finite and non-negative")
