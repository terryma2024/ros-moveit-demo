"""Backend-specific, bounded pre-release cup alignment."""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

Vector3 = tuple[float, float, float]


def _vector3(value: object, name: str) -> Vector3:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain three numbers")
    converted = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in converted):
        raise ValueError(f"{name} must contain only finite values")
    return converted


@dataclass(frozen=True, slots=True)
class PlaceAlignmentPolicy:
    settling_compensation_m: Vector3
    xy_tolerance_m: float
    z_tolerance_m: float
    max_attempts: int
    max_axis_correction_m: float

    def __post_init__(self) -> None:
        _vector3(self.settling_compensation_m, "settling_compensation_m")
        scalars = (
            self.xy_tolerance_m,
            self.z_tolerance_m,
            self.max_axis_correction_m,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in scalars):
            raise ValueError("alignment tolerances and correction bound must be positive")
        if not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool):
            raise TypeError("max_attempts must be an integer")
        if self.max_attempts < 0:
            raise ValueError("max_attempts must be non-negative")


@dataclass(frozen=True, slots=True)
class AlignmentTelemetry:
    attempt: int
    before_position_m: Vector3
    commanded_translation_m: Vector3
    after_position_m: Vector3
    before_xy_error_m: float
    after_xy_error_m: float


@dataclass(frozen=True, slots=True)
class PlaceAlignmentResult:
    position_m: Vector3
    attempt_count: int
    telemetry: tuple[AlignmentTelemetry, ...]


def policy_from_mapping(document: Mapping[str, Any]) -> PlaceAlignmentPolicy:
    settings = document.get("place_alignment")
    if not isinstance(settings, Mapping):
        raise ValueError("place_alignment mapping is required")
    return PlaceAlignmentPolicy(
        settling_compensation_m=_vector3(
            settings.get("settling_compensation_m"),
            "place_alignment.settling_compensation_m",
        ),
        xy_tolerance_m=float(settings.get("xy_tolerance_m")),
        z_tolerance_m=float(settings.get("z_tolerance_m")),
        max_attempts=int(settings.get("max_attempts")),
        max_axis_correction_m=float(settings.get("max_axis_correction_m")),
    )


def load_place_alignment_policy(path: Path) -> PlaceAlignmentPolicy:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise ValueError("motion policy must be a mapping")
    return policy_from_mapping(document)


def measured_settling_compensation(
    pre_release_position_m: Vector3,
    settled_position_m: Vector3,
) -> Vector3:
    pre_release = _vector3(pre_release_position_m, "pre_release_position_m")
    settled = _vector3(settled_position_m, "settled_position_m")
    return tuple(before - after for before, after in zip(pre_release, settled, strict=True))


def release_alignment_target(
    place_position_m: Vector3,
    policy: PlaceAlignmentPolicy,
) -> Vector3:
    place = _vector3(place_position_m, "place_position_m")
    return tuple(
        value + compensation
        for value, compensation in zip(place, policy.settling_compensation_m, strict=True)
    )


def _error(target: Vector3, observed: Vector3) -> Vector3:
    return tuple(desired - actual for desired, actual in zip(target, observed, strict=True))


def _aligned(error: Vector3, policy: PlaceAlignmentPolicy) -> bool:
    return (
        math.hypot(error[0], error[1]) <= policy.xy_tolerance_m
        and abs(error[2]) <= policy.z_tolerance_m
    )


def align_cup_for_release(
    observe_position: Callable[[], Vector3],
    target_position_m: Vector3,
    execute_translation: Callable[[Vector3], None],
    policy: PlaceAlignmentPolicy,
) -> PlaceAlignmentResult:
    """Correct the observed cup pose with a bounded same-run feedback loop."""

    target = _vector3(target_position_m, "target_position_m")
    current = _vector3(observe_position(), "observed_position_m")
    telemetry: list[AlignmentTelemetry] = []
    for attempt in range(policy.max_attempts + 1):
        error = _error(target, current)
        if _aligned(error, policy):
            return PlaceAlignmentResult(current, attempt, tuple(telemetry))
        if attempt == policy.max_attempts:
            break
        if any(abs(value) > policy.max_axis_correction_m for value in error):
            raise RuntimeError(f"place alignment correction exceeds bound: {error}")
        before_error = math.hypot(error[0], error[1])
        execute_translation(error)
        after = _vector3(observe_position(), "observed_position_m")
        after_error = _error(target, after)
        telemetry.append(
            AlignmentTelemetry(
                attempt=attempt + 1,
                before_position_m=current,
                commanded_translation_m=error,
                after_position_m=after,
                before_xy_error_m=before_error,
                after_xy_error_m=math.hypot(after_error[0], after_error[1]),
            )
        )
        current = after
    raise RuntimeError(
        f"place alignment did not converge within {policy.max_attempts} attempts: {current}"
    )
