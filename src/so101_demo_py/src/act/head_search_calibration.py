"""The seventeen measured head-search calibration values and their provenance.

Every value this library produces carries what produced it: its unit, the formula that computed it, the
ordered digests of its inputs, the distribution it was observed over, the margin it must keep, who owns it
in production and which consumer field reads it. The four perception values are verified against the frozen
candidate identity rather than retuned, and the hard bounds and the listed unsafe observations are refused
before any bundle is returned.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from so101_demo.perception_benchmark.contracts import canonical_sha256

#: the seventeen measured values, in the order the plan names them
MEASUREMENT_NAMES = (
    "horizontal_fov_rad",
    "lock_valid_neck_rad",
    "coarse_step_rad",
    "search_timeout_s",
    "min_confidence",
    "tracking_iou",
    "min_bbox_aspect",
    "min_area_px2",
    "center_deadband_px",
    "vertical_bounds_px",
    "max_fine_corrections",
    "max_fine_total_rad",
    "max_age_s",
    "max_skew_s",
    "submit_lead_s",
    "stop_velocity_rad_s",
    "stop_latency_s",
)
#: the four values that must equal the frozen candidate identity
CANDIDATE_MEASUREMENTS = ("min_confidence", "tracking_iou", "min_bbox_aspect", "min_area_px2")
MAX_AGE_BOUND_S = 0.15
MAX_SKEW_BOUND_S = 0.05
#: the ten approved condition classes a qualification item may carry
CONDITION_CLASSES = (
    "nominal",
    "left_anchor",
    "forward_anchor",
    "distractor_present",
    "two_cups",
    "no_cup",
    "low_light",
    "partial_occlusion",
    "fast_interruption",
    "reacquire_after_stop",
)
ANCHORS = ("default", "left", "forward")


class HeadSearchCalibrationError(ValueError):
    """A calibration the library must refuse, named so a caller can refuse by name."""


@dataclass(frozen=True, slots=True)
class Measurement:
    """One measured value and everything that explains it."""

    name: str
    value: object
    unit: str
    formula_id: str
    inputs_sha256: tuple[str, ...]
    distribution: Mapping[str, object]
    margin: float
    production_owner: str
    consumer_field: str


@dataclass(frozen=True, slots=True)
class HeadSearchCalibrationBundle:
    measurements: Mapping[str, Measurement]
    identities: Mapping[str, str]

    def to_document(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "identities": dict(self.identities),
            "measurements": {
                name: {
                    "value": measurement.value
                    if not isinstance(measurement.value, tuple)
                    else list(measurement.value),
                    "unit": measurement.unit,
                    "formula_id": measurement.formula_id,
                    "inputs_sha256": list(measurement.inputs_sha256),
                    "distribution": dict(measurement.distribution),
                    "margin": measurement.margin,
                    "production_owner": measurement.production_owner,
                    "consumer_field": measurement.consumer_field,
                }
                for name, measurement in self.measurements.items()
            },
        }

    @property
    def sha256(self) -> str:
        return canonical_sha256(self.to_document())


@dataclass(frozen=True, slots=True)
class QualificationItem:
    seed: int
    scene_group_id: str
    condition_class: str
    anchor: str


@dataclass(frozen=True, slots=True)
class ScenarioPartitions:
    calibration: tuple[int, ...]
    held_out_evaluation: tuple[int, ...]
    qualification: tuple[QualificationItem, ...]


def _section(inputs: Mapping[str, object], name: str) -> Mapping[str, object]:
    value = inputs.get(name)
    if not isinstance(value, Mapping):
        raise HeadSearchCalibrationError(
            f"HEAD_SEARCH_CALIBRATION_INVALID: the {name} section is missing"
        )
    return value


def _numbers(values: object, *, name: str) -> list[float]:
    if isinstance(values, (str, bytes)) or not isinstance(values, (list, tuple)) or not values:
        raise HeadSearchCalibrationError(
            f"HEAD_SEARCH_CALIBRATION_INVALID: {name} must be a non-empty sequence"
        )
    numbers = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise HeadSearchCalibrationError(
                f"HEAD_SEARCH_CALIBRATION_NON_FINITE: {name} holds a non-numeric sample"
            )
        numbers.append(float(value))
    return numbers


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def calibrate_head_search(inputs: Mapping[str, object]) -> HeadSearchCalibrationBundle:
    """Measure the seventeen values, refusing anything the hard bounds or the listed risks forbid."""

    geometry = _section(inputs, "geometry")
    candidate = _section(inputs, "candidate")
    timing = _section(inputs, "timing")
    episodes = _section(inputs, "episodes")
    identities = _section(inputs, "identities")

    # the unsafe-motion and identity risks are checked before the finite-sample scan, so a caller hears the
    # reason that matters rather than a generic one
    fov_sealed = float(geometry.get("horizontal_fov_rad", float("nan")))
    fine_total = episodes.get("max_fine_total_rad")
    if (
        isinstance(fine_total, bool)
        or not isinstance(fine_total, (int, float))
        or not math.isfinite(float(fine_total))
        or float(fine_total) <= 0.0
        or not math.isfinite(fov_sealed)
        or float(fine_total) > fov_sealed
    ):
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_UNSAFE_MOTION: the fine-motion allowance is not a positive finite "
            "angle no larger than one field of view"
        )
    if int(episodes.get("tracker_identity_switches", 0)) != 0:
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_IDENTITY_SWITCH: the tracker changed identity during calibration"
        )
    if int(episodes.get("val_false_candidates", 0)) != 0:
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_FALSE_CANDIDATE: the validation split produced false candidates"
        )
    if int(episodes.get("two_cup_detections", 0)) <= 0:
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_TWO_CUP_MISSING: no two-cup detection was observed"
        )

    ages = _numbers(timing.get("frame_age_s"), name="frame_age_s")
    skews = _numbers(timing.get("skew_s"), name="skew_s")
    stops = _numbers(timing.get("stop_latency_s"), name="stop_latency_s")
    for label, values in (("frame_age_s", ages), ("skew_s", skews), ("stop_latency_s", stops)):
        if any(not math.isfinite(value) for value in values):
            raise HeadSearchCalibrationError(
                f"HEAD_SEARCH_CALIBRATION_NON_FINITE: {label} holds a non-finite sample"
            )
        if any(value < 0.0 for value in values):
            raise HeadSearchCalibrationError(
                f"HEAD_SEARCH_CALIBRATION_TIME_REGRESSION: {label} holds a negative sample"
            )
    max_age = max(ages)
    max_skew = max(skews)
    if max_age > MAX_AGE_BOUND_S:
        raise HeadSearchCalibrationError(
            f"HEAD_SEARCH_CALIBRATION_BOUND: max_age_s {max_age} exceeds {MAX_AGE_BOUND_S}"
        )
    if max_skew > MAX_SKEW_BOUND_S:
        raise HeadSearchCalibrationError(
            f"HEAD_SEARCH_CALIBRATION_BOUND: max_skew_s {max_skew} exceeds {MAX_SKEW_BOUND_S}"
        )

    fov_value = geometry.get("horizontal_fov_rad")
    if (
        isinstance(fov_value, bool)
        or not isinstance(fov_value, (int, float))
        or not math.isfinite(float(fov_value))
        or not 0.0 < float(fov_value) < math.pi
    ):
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_INVALID: the horizontal field of view must be finite and inside "
            "(0, pi)"
        )
    timeout = timing.get("search_timeout_s")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(float(timeout))
        or float(timeout) <= 0.0
    ):
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_INVALID: the search timeout must be a positive finite duration"
        )
    for name in (
        "val_false_candidates",
        "two_cup_detections",
        "tracker_identity_switches",
        "max_fine_corrections",
    ):
        value = episodes.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise HeadSearchCalibrationError(
                f"HEAD_SEARCH_CALIBRATION_INVALID: {name} must be a non-negative whole count"
            )
    safe = _numbers(geometry.get("lock_valid_neck_rad"), name="lock_valid_neck_rad")
    required = _numbers(
        geometry.get("required_search_domain_rad"), name="required_search_domain_rad"
    )
    fov = float(fov_value)
    if required[0] < safe[0] - fov / 2.0 or required[1] > safe[1] + fov / 2.0:
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_DOMAIN_UNCOVERED: the safe interval cannot cover the required domain"
        )

    # (b) the four perception values must be the ones the frozen candidate identity was sealed with
    declared_identity = str(identities.get("candidate_identity_sha256", ""))
    measured_identity = canonical_sha256(
        {name: float(candidate[name]) for name in CANDIDATE_MEASUREMENTS}
    )
    if declared_identity != measured_identity:
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_IDENTITY_DRIFT: the perception values are not the frozen candidate "
            f"identity ({measured_identity[:12]} vs {declared_identity[:12]})"
        )
    geometry_digest = _digest(geometry)
    candidate_digest = _digest(candidate)
    timing_digest = _digest(timing)
    episode_digest = _digest(episodes)

    def measurement(
        name: str,
        value: object,
        *,
        unit: str,
        formula_id: str,
        inputs_sha256: Sequence[str],
        distribution: Mapping[str, object],
        margin: float,
        production_owner: str,
        consumer_field: str,
    ) -> Measurement:
        if not inputs_sha256 or any(len(item) != 64 for item in inputs_sha256):
            raise HeadSearchCalibrationError(
                f"HEAD_SEARCH_CALIBRATION_INVALID: {name} carries no ordered input digests"
            )
        return Measurement(
            name=name,
            value=value,
            unit=unit,
            formula_id=formula_id,
            inputs_sha256=tuple(inputs_sha256),
            distribution=dict(distribution),
            margin=float(margin),
            production_owner=production_owner,
            consumer_field=consumer_field,
        )

    perception = {
        name: measurement(
            name,
            float(candidate[name]),
            unit="ratio" if name != "min_area_px2" else "px^2",
            formula_id=f"frozen_candidate.{name}",
            inputs_sha256=(candidate_digest,),
            distribution={"frozen": float(candidate[name])},
            margin=0.0,
            production_owner="perception",
            consumer_field=f"head_search.{name}",
        )
        for name in CANDIDATE_MEASUREMENTS
    }
    measurements = {
        "horizontal_fov_rad": measurement(
            "horizontal_fov_rad",
            fov,
            unit="rad",
            formula_id="geometry.fov",
            inputs_sha256=(geometry_digest,),
            distribution={"value": fov},
            margin=0.0,
            production_owner="perception",
            consumer_field="head_search.horizontal_fov_rad",
        ),
        "lock_valid_neck_rad": measurement(
            "lock_valid_neck_rad",
            tuple(safe),
            unit="rad",
            formula_id="geometry.lock_valid_neck_rad",
            inputs_sha256=(geometry_digest,),
            distribution={"low": safe[0], "high": safe[1]},
            margin=0.0,
            production_owner="controller",
            consumer_field="head_search.lock_valid_neck_rad",
        ),
        "coarse_step_rad": measurement(
            "coarse_step_rad",
            float(geometry["coarse_step_rad"]),
            unit="rad",
            formula_id="geometry.coarse_step_candidate_rad",
            inputs_sha256=(geometry_digest,),
            distribution={"value": float(geometry["coarse_step_rad"])},
            margin=0.0,
            production_owner="controller",
            consumer_field="head_search.coarse_step_rad",
        ),
        "search_timeout_s": measurement(
            "search_timeout_s",
            float(timing["search_timeout_s"]),
            unit="s",
            formula_id="timing.search_timeout_s",
            inputs_sha256=(timing_digest,),
            distribution={"value": float(timing["search_timeout_s"])},
            margin=0.0,
            production_owner="controller",
            consumer_field="head_search.search_timeout_s",
        ),
        "center_deadband_px": measurement(
            "center_deadband_px",
            float(episodes["center_deadband_px"]),
            unit="px",
            formula_id="episodes.center_deadband_px",
            inputs_sha256=(episode_digest,),
            distribution={"value": float(episodes["center_deadband_px"])},
            margin=0.0,
            production_owner="controller",
            consumer_field="head_search.center_deadband_px",
        ),
        "vertical_bounds_px": measurement(
            "vertical_bounds_px",
            tuple(float(value) for value in episodes["vertical_bounds_px"]),
            unit="px",
            formula_id="episodes.vertical_bounds_px",
            inputs_sha256=(episode_digest,),
            distribution={
                "low": float(episodes["vertical_bounds_px"][0]),
                "high": float(episodes["vertical_bounds_px"][1]),
            },
            margin=0.0,
            production_owner="controller",
            consumer_field="head_search.vertical_bounds_px",
        ),
        "max_fine_corrections": measurement(
            "max_fine_corrections",
            int(episodes["max_fine_corrections"]),
            unit="count",
            formula_id="episodes.max_fine_corrections",
            inputs_sha256=(episode_digest,),
            distribution={"value": int(episodes["max_fine_corrections"])},
            margin=0.0,
            production_owner="controller",
            consumer_field="head_search.max_fine_corrections",
        ),
        "max_fine_total_rad": measurement(
            "max_fine_total_rad",
            float(fine_total),
            unit="rad",
            formula_id="episodes.max_fine_total_rad",
            inputs_sha256=(episode_digest,),
            distribution={"value": float(fine_total)},
            margin=0.0,
            production_owner="controller",
            consumer_field="head_search.max_fine_total_rad",
        ),
        "max_age_s": measurement(
            "max_age_s",
            max_age,
            unit="s",
            formula_id="timing.max_frame_age_s",
            inputs_sha256=(timing_digest,),
            distribution={"samples": len(ages), "max": max_age},
            margin=MAX_AGE_BOUND_S - max_age,
            production_owner="controller",
            consumer_field="head_search.max_age_s",
        ),
        "max_skew_s": measurement(
            "max_skew_s",
            max_skew,
            unit="s",
            formula_id="timing.max_skew_s",
            inputs_sha256=(timing_digest,),
            distribution={"samples": len(skews), "max": max_skew},
            margin=MAX_SKEW_BOUND_S - max_skew,
            production_owner="controller",
            consumer_field="head_search.max_skew_s",
        ),
        "submit_lead_s": measurement(
            "submit_lead_s",
            float(timing["submit_lead_s"]),
            unit="s",
            formula_id="timing.submit_lead_s",
            inputs_sha256=(timing_digest,),
            distribution={"value": float(timing["submit_lead_s"])},
            margin=0.0,
            production_owner="controller",
            consumer_field="head_search.submit_lead_s",
        ),
        "stop_velocity_rad_s": measurement(
            "stop_velocity_rad_s",
            float(timing["stop_velocity_rad_s"]),
            unit="rad/s",
            formula_id="timing.stop_velocity_rad_s",
            inputs_sha256=(timing_digest,),
            distribution={"value": float(timing["stop_velocity_rad_s"])},
            margin=0.0,
            production_owner="controller",
            consumer_field="head_search.stop_velocity_rad_s",
        ),
        "stop_latency_s": measurement(
            "stop_latency_s",
            max(stops),
            unit="s",
            formula_id="timing.max_stop_latency_s",
            inputs_sha256=(timing_digest,),
            distribution={"samples": len(stops), "max": max(stops)},
            margin=0.0,
            production_owner="controller",
            consumer_field="head_search.stop_latency_s",
        ),
        **perception,
    }
    if set(measurements) != set(MEASUREMENT_NAMES):
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_INVALID: the bundle does not hold exactly the seventeen values"
        )
    return HeadSearchCalibrationBundle(
        measurements=measurements,
        identities={str(key): str(value) for key, value in identities.items()},
    )


def load_scenario_partitions(document: Mapping[str, object]) -> ScenarioPartitions:
    """Read the tracked seed partitions, refusing a repeat or an unknown condition class."""

    def seeds(name: str) -> tuple[int, ...]:
        values = document.get(name)
        if not isinstance(values, (list, tuple)) or not values:
            raise HeadSearchCalibrationError(
                f"HEAD_SEARCH_CALIBRATION_INVALID: the partitions declare no {name}"
            )
        return tuple(int(value) for value in values)

    calibration = seeds("calibration")
    held_out = seeds("held_out_evaluation")
    raw_qualification = document.get("qualification")
    if not isinstance(raw_qualification, (list, tuple)) or not raw_qualification:
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_INVALID: the partitions declare no qualification list"
        )
    qualification = []
    for item in raw_qualification:
        if not isinstance(item, Mapping):
            raise HeadSearchCalibrationError(
                "HEAD_SEARCH_CALIBRATION_INVALID: a qualification item is not a mapping"
            )
        condition = str(item.get("condition_class"))
        anchor = str(item.get("anchor"))
        if condition not in CONDITION_CLASSES:
            raise HeadSearchCalibrationError(
                f"HEAD_SEARCH_CALIBRATION_INVALID: {condition!r} is not an approved condition class"
            )
        if anchor not in ANCHORS:
            raise HeadSearchCalibrationError(
                f"HEAD_SEARCH_CALIBRATION_INVALID: {anchor!r} is not an approved anchor"
            )
        qualification.append(
            QualificationItem(
                seed=int(item["seed"]),
                scene_group_id=str(item["scene_group_id"]),
                condition_class=condition,
                anchor=anchor,
            )
        )
    if len(qualification) != 40:
        raise HeadSearchCalibrationError(
            f"HEAD_SEARCH_CALIBRATION_INVALID: the qualification list must hold exactly 40 items, holds "
            f"{len(qualification)}"
        )
    by_seed: dict[object, str] = {}
    by_scene: dict[object, object] = {}
    for item in qualification:
        if item.seed in by_seed or item.scene_group_id in by_scene:
            raise HeadSearchCalibrationError(
                f"HEAD_SEARCH_CALIBRATION_INVALID: seed {item.seed} or its scene repeats inside the "
                "qualification list"
            )
        by_seed[item.seed] = item.scene_group_id
        by_scene[item.scene_group_id] = item.seed
    seen = set(calibration) | set(held_out)
    if seen & {item.seed for item in qualification} or set(calibration) & set(held_out):
        raise HeadSearchCalibrationError(
            "HEAD_SEARCH_CALIBRATION_INVALID: a seed appears in more than one partition"
        )
    return ScenarioPartitions(
        calibration=calibration, held_out_evaluation=held_out, qualification=tuple(qualification)
    )
