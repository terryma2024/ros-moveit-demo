"""Bounded, outcome-first post-release TCP retreat geometry."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

Vector3 = tuple[float, float, float]


def _positive_finite(value: float, name: str) -> float:
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return converted


def _position(value: object, name: str) -> Vector3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three numbers")
    converted = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in converted):
        raise ValueError(f"{name} must contain only finite values")
    return converted


@dataclass(frozen=True, slots=True)
class ReleaseRetreatPolicy:
    """Limits for separating an opened gripper from a released cup."""

    radial_separation_m: float
    vertical_clearance_m: float
    orientation_tolerance_rad: float
    position_tolerance_m: float
    velocity_scaling: float
    acceleration_scaling: float
    residual_contact_grace_s: float
    max_residual_fingertip_force_n: float
    max_released_cup_displacement_m: float

    def __post_init__(self) -> None:
        radial = _positive_finite(self.radial_separation_m, "radial separation")
        if radial > 0.030:
            raise ValueError("radial separation must stay within the 0.030 m bound")
        vertical = _positive_finite(self.vertical_clearance_m, "vertical clearance")
        if vertical > 0.100:
            raise ValueError("vertical clearance must stay within the 0.100 m bound")
        orientation = _positive_finite(self.orientation_tolerance_rad, "orientation tolerance")
        if orientation > math.pi:
            raise ValueError("orientation tolerance must not exceed pi")
        _positive_finite(self.position_tolerance_m, "position tolerance")
        grace = _positive_finite(self.residual_contact_grace_s, "residual contact grace")
        if grace > 0.20:
            raise ValueError("residual contact grace must stay within 0.20 s")
        force = _positive_finite(
            self.max_residual_fingertip_force_n,
            "maximum residual fingertip force",
        )
        if force > 0.10:
            raise ValueError("maximum residual fingertip force must stay within 0.10 N")
        displacement = _positive_finite(
            self.max_released_cup_displacement_m,
            "maximum released cup displacement",
        )
        if displacement > 0.010:
            raise ValueError("maximum released cup displacement must stay within 0.010 m")
        for value, name in (
            (self.velocity_scaling, "velocity scaling"),
            (self.acceleration_scaling, "acceleration scaling"),
        ):
            scaling = _positive_finite(value, name)
            if scaling > 1.0:
                raise ValueError(f"{name} must not exceed 1.0")


def policy_from_mapping(document: Mapping[str, Any]) -> ReleaseRetreatPolicy:
    settings = document.get("release_retreat")
    if not isinstance(settings, Mapping):
        raise ValueError("release_retreat mapping is required")
    return ReleaseRetreatPolicy(
        radial_separation_m=float(settings.get("radial_separation_m")),
        vertical_clearance_m=float(settings.get("vertical_clearance_m")),
        orientation_tolerance_rad=float(settings.get("orientation_tolerance_rad")),
        position_tolerance_m=float(settings.get("position_tolerance_m")),
        velocity_scaling=float(settings.get("velocity_scaling")),
        acceleration_scaling=float(settings.get("acceleration_scaling")),
        residual_contact_grace_s=float(settings.get("residual_contact_grace_s")),
        max_residual_fingertip_force_n=float(settings.get("max_residual_fingertip_force_n")),
        max_released_cup_displacement_m=float(settings.get("max_released_cup_displacement_m")),
    )


def load_release_retreat_policy(path: Path) -> ReleaseRetreatPolicy:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("motion policy must be a mapping")
    return policy_from_mapping(document)


def release_retreat_translations(
    tcp_position_m: Vector3,
    cup_position_m: Vector3,
    policy: ReleaseRetreatPolicy,
) -> tuple[Vector3, Vector3]:
    """Return radial separation followed by a world-z clearance move."""

    tcp = _position(tcp_position_m, "tcp_position_m")
    cup = _position(cup_position_m, "cup_position_m")
    dx = tcp[0] - cup[0]
    dy = tcp[1] - cup[1]
    radial = math.hypot(dx, dy)
    if radial < 0.001:
        raise RuntimeError("release separation requires a finite radial direction")
    scale = policy.radial_separation_m / radial
    return (
        (dx * scale, dy * scale, 0.0),
        (0.0, 0.0, policy.vertical_clearance_m),
    )


def residual_contact_within_bounds(
    maximum_fingertip_force_n: float,
    released_cup_displacement_m: float,
    policy: ReleaseRetreatPolicy,
) -> bool:
    """Return whether the transient fixed-pad manifold remains harmless."""

    force = float(maximum_fingertip_force_n)
    displacement = float(released_cup_displacement_m)
    return (
        math.isfinite(force)
        and force >= 0.0
        and force <= policy.max_residual_fingertip_force_n
        and math.isfinite(displacement)
        and displacement >= 0.0
        and displacement <= policy.max_released_cup_displacement_m
    )
