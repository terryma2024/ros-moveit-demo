"""Immutable backend-neutral simulation evidence values."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TypeAlias

Vector3: TypeAlias = tuple[float, float, float]
Quaternion: TypeAlias = tuple[float, float, float, float]


def _identifier(name: str, value: object) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")


def _name(name: str, value: object) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _finite_tuple(name: str, value: object, length: int) -> None:
    if not isinstance(value, tuple) or len(value) != length:
        raise TypeError(f"{name} must be an immutable {length}-tuple")
    if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in value):
        raise TypeError(f"{name} must contain only numbers")
    if not all(math.isfinite(float(item)) for item in value):
        raise ValueError(f"{name} must contain only finite values")


@dataclass(frozen=True, slots=True)
class ObjectState:
    body_id: int
    body: str
    position_world: Vector3
    orientation_xyzw: Quaternion
    linear_velocity_world: Vector3
    angular_velocity_world: Vector3

    def __post_init__(self) -> None:
        _identifier("body_id", self.body_id)
        _name("body", self.body)
        _finite_tuple("position_world", self.position_world, 3)
        _finite_tuple("orientation_xyzw", self.orientation_xyzw, 4)
        _finite_tuple("linear_velocity_world", self.linear_velocity_world, 3)
        _finite_tuple("angular_velocity_world", self.angular_velocity_world, 3)
        if math.isclose(sum(float(item) ** 2 for item in self.orientation_xyzw), 0.0):
            raise ValueError("orientation_xyzw must be non-zero")


@dataclass(frozen=True, slots=True)
class ContactEvidence:
    body1_id: int
    geom1_id: int
    body1: str
    geom1: str
    body2_id: int
    geom2_id: int
    body2: str
    geom2: str
    position_world: Vector3
    normal_world: Vector3
    signed_distance_m: float
    normal_force_n: float

    def __post_init__(self) -> None:
        for field_name in ("body1_id", "geom1_id", "body2_id", "geom2_id"):
            _identifier(field_name, getattr(self, field_name))
        for field_name in ("body1", "geom1", "body2", "geom2"):
            _name(field_name, getattr(self, field_name))
        _finite_tuple("position_world", self.position_world, 3)
        _finite_tuple("normal_world", self.normal_world, 3)
        if not math.isfinite(self.signed_distance_m):
            raise ValueError("signed_distance_m must be finite")
        if not math.isfinite(self.normal_force_n) or self.normal_force_n < 0.0:
            raise ValueError("normal_force_n must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class SimulationEvidence:
    simulation_time_s: float
    frame_id: str
    publisher_sequence: int
    simulation_step: int
    reset_epoch: int
    simulation_session_id: str
    paused: bool
    object_state: ObjectState
    has_contact: bool
    minimum_signed_distance_m: float
    maximum_normal_force_n: float
    truncated: bool
    left_fingertip_contacts: tuple[ContactEvidence, ...]
    right_fingertip_contacts: tuple[ContactEvidence, ...]
    other_object_contacts: tuple[ContactEvidence, ...]

    def __post_init__(self) -> None:
        if not math.isfinite(self.simulation_time_s) or self.simulation_time_s < 0.0:
            raise ValueError("simulation_time_s must be finite and non-negative")
        if self.frame_id != "world":
            raise ValueError("frame_id must be world")
        for field_name in ("publisher_sequence", "simulation_step", "reset_epoch"):
            _identifier(field_name, getattr(self, field_name))
        _name("simulation_session_id", self.simulation_session_id)
        if not isinstance(self.paused, bool) or not isinstance(self.truncated, bool):
            raise TypeError("paused and truncated must be bool")
        if not isinstance(self.object_state, ObjectState):
            raise TypeError("object_state must be ObjectState")
        arrays = (
            self.left_fingertip_contacts,
            self.right_fingertip_contacts,
            self.other_object_contacts,
        )
        if any(not isinstance(array, tuple) for array in arrays):
            raise TypeError("contact arrays must be immutable tuples")
        contacts = tuple(item for array in arrays for item in array)
        if any(not isinstance(item, ContactEvidence) for item in contacts):
            raise TypeError("contact arrays must contain ContactEvidence")
        if any(
            item.body1_id != self.object_state.body_id or item.body1 != self.object_state.body
            for item in contacts
        ):
            raise ValueError("contact object identity must match object_state")
        if self.has_contact != bool(contacts):
            raise ValueError("zero-contact state and has_contact disagree")
        if not contacts:
            if self.minimum_signed_distance_m != 0.0 or self.maximum_normal_force_n != 0.0:
                raise ValueError("zero-contact aggregates must be zero")
            return
        expected_distance = min(item.signed_distance_m for item in contacts)
        expected_force = max(item.normal_force_n for item in contacts)
        if not math.isclose(self.minimum_signed_distance_m, expected_distance, abs_tol=1e-12):
            raise ValueError("minimum distance aggregate mismatch")
        if not math.isclose(self.maximum_normal_force_n, expected_force, abs_tol=1e-12):
            raise ValueError("maximum force aggregate mismatch")

    @property
    def ordering_key(self) -> tuple[str, int, int]:
        return self.simulation_session_id, self.reset_epoch, self.simulation_step


@dataclass(frozen=True, slots=True)
class ReceivedSimulationEvidence:
    """Atomic evidence paired with its local callback-acceptance clock value."""

    evidence: SimulationEvidence
    received_monotonic_s: float

    def __post_init__(self) -> None:
        if not isinstance(self.evidence, SimulationEvidence):
            raise TypeError("evidence must be SimulationEvidence")
        if not math.isfinite(self.received_monotonic_s) or self.received_monotonic_s < 0.0:
            raise ValueError("received_monotonic_s must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ResetReceipt:
    old_epoch: int
    new_epoch: int
    keyframe: str
    simulation_step: int
    simulation_session_id: str

    def __post_init__(self) -> None:
        for field_name in ("old_epoch", "new_epoch", "simulation_step"):
            _identifier(field_name, getattr(self, field_name))
        if self.new_epoch != self.old_epoch + 1:
            raise ValueError("new_epoch must increment old_epoch exactly once")
        _name("keyframe", self.keyframe)
        _name("simulation_session_id", self.simulation_session_id)
