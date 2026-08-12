"""Validate and analyze atomic MuJoCo contact-calibration evidence."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import os
import sys
import tempfile
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from so101_mujoco_demo_py.contact_policy import (
    ApprovalRecord,
    approve_proposal,
    dynamic_metric_definitions,
    proposal_sha256,
    validate_dynamic_diagnostic_proposal,
    validate_unilateral_rejection_contracts,
)

PHYSICAL_REGIMES = (
    "no_contact",
    "bilateral_touch",
    "over_compression",
    "micro_lift_slip",
    "stable_hold",
)
UNILATERAL_REGIMES = ("left_only", "right_only")
CLASSIFICATION_LABELS = (
    "no_contact",
    "left_only",
    "right_only",
    "bilateral_touch",
    "over_compression",
    "micro_lift_slip",
    "stable_hold",
)
# Archived schema-v1/v2 evidence used all seven labels as physical cohorts.
REGIMES = CLASSIFICATION_LABELS
REQUIRED_UNITS = {
    "signed_distance": "m",
    "normal_force": "N",
    "linear_speed": "m/s",
    "joint_position": "rad",
    "simulation_time": "s",
    "receipt_time": "s",
}
V1_HASH_FIELDS = ("model_sha256", "config_sha256")
V2_HASH_FIELDS = ("model_sha256", "scene_sha256", "motion_policy_sha256")
COMMIT_FIELDS = ("source_commit", "dependency_commit")
CONTACT_FIELDS = (
    "left_fingertip_contacts",
    "right_fingertip_contacts",
    "other_object_contacts",
)
METRICS = (
    "minimum_signed_distance_m",
    "minimum_fingertip_signed_distance_m",
    "maximum_normal_force_n",
    "linear_speed_m_s",
    "left_normal_force_n",
    "right_normal_force_n",
    "other_normal_force_n",
    "contact_duration_s",
)


def quantile(values: list[float], fraction: float) -> float:
    """Return a linearly interpolated quantile for a non-empty finite sample."""
    if not values:
        raise ValueError("quantiles require at least one value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def _mapping(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a mapping")
    return value


def _list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise ValueError(f"{name} must be a list")
    return value


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be numeric and finite")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _identifier(value: Any, name: str, length: int) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise ValueError(f"{name} must be a {length}-character hexadecimal identifier")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{name} must be hexadecimal") from error
    if set(value) == {"0"}:
        raise ValueError(f"{name} uses a placeholder hash")
    return value


def _vector(value: Any, name: str, length: int) -> list[float]:
    result = _list(value, name)
    if len(result) != length:
        raise ValueError(f"{name} must contain {length} values")
    return [_finite(item, name) for item in result]


def _validate_units(value: Any) -> dict[str, str]:
    units = _mapping(value, "units")
    if units != REQUIRED_UNITS:
        raise ValueError(f"units must be exactly {REQUIRED_UNITS}")
    return units


def _validate_contact(value: Any, name: str) -> None:
    item = _mapping(value, name)
    for field in ("object_body", "robot_geom"):
        if not isinstance(item.get(field), str) or not item[field]:
            raise ValueError(f"{name}.{field} must be a non-empty string")
    _finite(item.get("signed_distance_m"), f"{name}.signed_distance_m")
    force = _finite(item.get("normal_force_n"), f"{name}.normal_force_n")
    if force < 0.0:
        raise ValueError(f"{name}.normal_force_n must be non-negative")


def _validate_pose(value: Any, name: str) -> None:
    pose = _mapping(value, name)
    _vector(pose.get("position_m"), f"{name}.position_m", 3)
    orientation = _vector(pose.get("orientation_xyzw"), f"{name}.orientation_xyzw", 4)
    if math.isclose(sum(component**2 for component in orientation), 0.0):
        raise ValueError(f"{name}.orientation_xyzw must be non-zero")


def _validate_sample(
    sample_value: Any,
    regime: str,
    legacy_fingerprint: dict[str, str] | None,
) -> dict[str, Any]:
    sample = _mapping(sample_value, f"{regime} sample")
    if sample.get("regime") != regime:
        raise ValueError(f"sample regime mismatch for {regime}")
    subcohorts = _mapping(sample.get("subcohorts"), "subcohorts")
    if set(subcohorts) != {"table_only", "post_release"} or any(
        not isinstance(value, bool) for value in subcohorts.values()
    ):
        raise ValueError("subcohorts must contain boolean table_only and post_release flags")
    if legacy_fingerprint is not None:
        for field, expected in legacy_fingerprint.items():
            length = 40 if field in COMMIT_FIELDS else 64
            actual = _identifier(sample.get(field), field, length)
            if actual != expected:
                raise ValueError(f"mixed fingerprint data in {field}")
    session = sample.get("simulation_session_id")
    if not isinstance(session, str) or not session:
        raise ValueError("simulation_session_id must be a non-empty string")
    for field in ("reset_epoch", "publisher_sequence", "simulation_step"):
        _integer(sample.get(field), field)
    for field in (
        "simulation_time_s",
        "receipt_monotonic_s",
        "minimum_signed_distance_m",
        "maximum_normal_force_n",
        "q6_rad",
        "contact_duration_s",
    ):
        _finite(sample.get(field), field)
    _validate_pose(sample.get("object_pose_world"), "object_pose_world")
    twist = _mapping(sample.get("object_twist_world"), "object_twist_world")
    _vector(twist.get("linear_m_s"), "object_twist_world.linear_m_s", 3)
    _vector(twist.get("angular_rad_s"), "object_twist_world.angular_rad_s", 3)
    _vector(sample.get("arm_joint_positions_rad"), "arm_joint_positions_rad", 5)
    _validate_pose(sample.get("tcp_pose_world"), "tcp_pose_world")
    for field in CONTACT_FIELDS:
        contacts = _list(sample.get(field), field)
        for index, contact in enumerate(contacts):
            _validate_contact(contact, f"{field}[{index}]")
    return sample


def validate_evidence(evidence_value: Any) -> dict[str, Any]:
    """Validate a complete, single-provenance raw calibration matrix."""
    evidence = _mapping(evidence_value, "evidence")
    schema_version = evidence.get("schema_version")
    if schema_version not in {1, 2, 3}:
        raise ValueError("unsupported schema_version")
    _validate_units(evidence.get("units"))
    legacy_fingerprint: dict[str, str] | None = None
    if schema_version == 1:
        legacy_fingerprint = {
            field: _identifier(evidence.get(field), field, 40 if field in COMMIT_FIELDS else 64)
            for field in (*COMMIT_FIELDS, *V1_HASH_FIELDS)
        }
        normalized_fingerprint = {
            "source_commit": legacy_fingerprint["source_commit"],
            "dependency_commit": legacy_fingerprint["dependency_commit"],
            "model_sha256": legacy_fingerprint["model_sha256"],
            "scene_sha256": legacy_fingerprint["config_sha256"],
            "motion_policy_sha256": legacy_fingerprint["config_sha256"],
        }
    else:
        fingerprint_value = _mapping(evidence.get("fingerprint"), "fingerprint")
        required = {*COMMIT_FIELDS, *V2_HASH_FIELDS}
        if set(fingerprint_value) != required:
            raise ValueError("fingerprint must contain exact schema-v2 artifact identities")
        normalized_fingerprint = {
            field: _identifier(
                fingerprint_value.get(field),
                field,
                40 if field in COMMIT_FIELDS else 64,
            )
            for field in (*COMMIT_FIELDS, *V2_HASH_FIELDS)
        }
    regimes = _mapping(evidence.get("regimes"), "regimes")
    required_regimes = PHYSICAL_REGIMES if schema_version == 3 else REGIMES
    if set(regimes) != set(required_regimes):
        missing = sorted(set(required_regimes) - set(regimes))
        if schema_version == 3:
            raise ValueError(
                f"schema-v3 physical regimes must be exactly {list(PHYSICAL_REGIMES)}; "
                f"missing={missing}"
            )
        raise ValueError(f"missing regimes: {missing}")
    unilateral_contracts = None
    if schema_version == 3:
        unilateral_contracts = validate_unilateral_rejection_contracts(
            evidence.get("unilateral_rejection_contracts")
        )

    samples: list[dict[str, Any]] = []
    for regime in required_regimes:
        regime_samples = _list(regimes[regime], regime)
        if len(regime_samples) < 20:
            raise ValueError(f"{regime} requires at least 20 valid samples")
        samples.extend(
            _validate_sample(sample, regime, legacy_fingerprint) for sample in regime_samples
        )

    sessions = {sample["simulation_session_id"] for sample in samples}
    if len(sessions) != 1:
        raise ValueError("mixed simulation session data")
    reset_epochs = {sample["reset_epoch"] for sample in samples}
    if len(reset_epochs) != 1:
        raise ValueError("mixed reset epoch data")
    if schema_version == 2:
        if evidence.get("simulation_session_id") != next(iter(sessions)):
            raise ValueError("top-level simulation session mismatch")
        if evidence.get("reset_epoch") != next(iter(reset_epochs)):
            raise ValueError("top-level reset epoch mismatch")
    ordered = sorted(samples, key=lambda sample: sample["publisher_sequence"])
    for previous, current in zip(ordered, ordered[1:], strict=False):
        if current["publisher_sequence"] <= previous["publisher_sequence"]:
            raise ValueError("publisher sequence must be unique and strictly increasing")
        if current["simulation_step"] < previous["simulation_step"]:
            raise ValueError("simulation step is stale or non-monotonic")
        if current["simulation_time_s"] < previous["simulation_time_s"]:
            raise ValueError("simulation time is stale or non-monotonic")
        if current["receipt_monotonic_s"] <= previous["receipt_monotonic_s"]:
            raise ValueError("receipt time is stale or non-monotonic")
    normalized = copy.deepcopy(evidence)
    normalized["normalized_fingerprint"] = normalized_fingerprint
    normalized["source_schema_version"] = schema_version
    if unilateral_contracts is not None:
        normalized["unilateral_rejection_contracts"] = unilateral_contracts
    return normalized


def _contact_force(sample: dict[str, Any], field: str) -> float:
    return sum(float(item["normal_force_n"]) for item in sample[field])


def _minimum_fingertip_signed_distance(sample: dict[str, Any]) -> float:
    contacts = (
        *sample["left_fingertip_contacts"],
        *sample["right_fingertip_contacts"],
    )
    return min((float(item["signed_distance_m"]) for item in contacts), default=0.0)


def sample_metrics(sample: dict[str, Any]) -> dict[str, float]:
    linear = sample["object_twist_world"]["linear_m_s"]
    left_force = _contact_force(sample, "left_fingertip_contacts")
    right_force = _contact_force(sample, "right_fingertip_contacts")
    return {
        "minimum_signed_distance_m": float(sample["minimum_signed_distance_m"]),
        "minimum_fingertip_signed_distance_m": _minimum_fingertip_signed_distance(sample),
        "maximum_normal_force_n": float(sample["maximum_normal_force_n"]),
        "linear_speed_m_s": math.sqrt(sum(float(value) ** 2 for value in linear)),
        "left_normal_force_n": left_force,
        "right_normal_force_n": right_force,
        "bilateral_force_n": min(left_force, right_force),
        "other_normal_force_n": _contact_force(sample, "other_object_contacts"),
        "contact_duration_s": float(sample["contact_duration_s"]),
    }


def _flatten(
    regimes: dict[str, list[dict[str, Any]]], names: Iterable[str]
) -> list[dict[str, Any]]:
    return [sample for name in names for sample in regimes[name]]


def _separating_threshold(
    negative: list[float], positive: list[float], label: str
) -> tuple[float, float]:
    negative_edge = max(negative)
    positive_edge = min(positive)
    margin = positive_edge - negative_edge
    if margin <= 0.0:
        raise ValueError(f"overlapping distributions do not separate {label}")
    return (negative_edge + positive_edge) / 2.0, margin


def _positive_scale_threshold(
    negative: list[float], positive: list[float], label: str
) -> tuple[float, float]:
    """Separate a positive scale metric without bias toward the larger magnitude."""
    negative_edge = max(negative)
    positive_edge = max(positive)
    margin = positive_edge - negative_edge
    if negative_edge < 0.0 or margin <= 0.0:
        raise ValueError(f"overlapping distributions do not separate {label}")
    threshold = (
        math.sqrt(negative_edge * positive_edge) if negative_edge > 0.0 else positive_edge / 2.0
    )
    return threshold, margin


def _thresholds(
    regimes: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, float], dict[str, float]]:
    metrics = {
        name: [sample_metrics(sample) for sample in samples] for name, samples in regimes.items()
    }
    negative_names = tuple(
        name for name in ("no_contact", "left_only", "right_only") if name in metrics
    )
    unilateral = _flatten(metrics, negative_names)
    bilateral = _flatten(
        metrics,
        ("bilateral_touch", "over_compression", "micro_lift_slip", "stable_hold"),
    )
    minimum_force, force_margin = _separating_threshold(
        [sample["bilateral_force_n"] for sample in unilateral],
        [sample["bilateral_force_n"] for sample in bilateral],
        "bilateral force",
    )
    acceptable_compression = _flatten(
        metrics, ("bilateral_touch", "micro_lift_slip", "stable_hold")
    )
    maximum_compression, compression_margin = _separating_threshold(
        [
            max(0.0, -sample["minimum_fingertip_signed_distance_m"])
            for sample in acceptable_compression
        ],
        [
            max(0.0, -sample["minimum_fingertip_signed_distance_m"])
            for sample in metrics["over_compression"]
        ],
        "compression distance",
    )
    acceptable_force = _flatten(metrics, ("bilateral_touch", "micro_lift_slip", "stable_hold"))
    maximum_force, safe_force_margin = _separating_threshold(
        [sample["maximum_normal_force_n"] for sample in acceptable_force],
        [sample["maximum_normal_force_n"] for sample in metrics["over_compression"]],
        "safe force",
    )
    maximum_speed, speed_margin = _positive_scale_threshold(
        [sample["linear_speed_m_s"] for sample in metrics["stable_hold"]],
        [max(sample["linear_speed_m_s"] for sample in metrics["micro_lift_slip"])],
        "hold linear speed",
    )
    minimum_duration, duration_margin = _separating_threshold(
        [sample["contact_duration_s"] for sample in metrics["bilateral_touch"]],
        [sample["contact_duration_s"] for sample in metrics["stable_hold"]],
        "stable hold duration",
    )
    return (
        {
            "minimum_bilateral_force_n": minimum_force,
            "maximum_compression_distance_m": maximum_compression,
            "maximum_safe_force_n": maximum_force,
            "maximum_hold_linear_speed_m_s": maximum_speed,
            "minimum_stable_hold_duration_s": minimum_duration,
        },
        {
            "bilateral_force_n": force_margin,
            "compression_distance_m": compression_margin,
            "safe_force_n": safe_force_margin,
            "hold_linear_speed_m_s": speed_margin,
            "stable_hold_duration_s": duration_margin,
        },
    )


def classify(
    sample: dict[str, Any],
    thresholds: dict[str, float],
    *,
    window_maximum_linear_speed_m_s: float | None = None,
) -> str:
    """Classify one sample while matching the live window-maximum slip gate."""
    left = bool(sample["left_fingertip_contacts"])
    right = bool(sample["right_fingertip_contacts"])
    if not left and not right:
        return "no_contact"
    if left and not right:
        return "left_only"
    if right and not left:
        return "right_only"
    metrics = sample_metrics(sample)
    compression = max(0.0, -metrics["minimum_fingertip_signed_distance_m"])
    if (
        compression >= thresholds["maximum_compression_distance_m"]
        or metrics["maximum_normal_force_n"] >= thresholds["maximum_safe_force_n"]
    ):
        return "over_compression"
    slip_speed = (
        metrics["linear_speed_m_s"]
        if window_maximum_linear_speed_m_s is None
        else window_maximum_linear_speed_m_s
    )
    if slip_speed >= thresholds["maximum_hold_linear_speed_m_s"]:
        return "micro_lift_slip"
    if metrics["contact_duration_s"] >= thresholds["minimum_stable_hold_duration_s"]:
        return "stable_hold"
    return "bilateral_touch"


def _summaries(regimes: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for regime in regimes:
        values = [sample_metrics(sample) for sample in regimes[regime]]
        summaries[regime] = {
            "sample_count": len(values),
            "quantiles": {
                label: {
                    metric: quantile([sample[metric] for sample in values], fraction)
                    for metric in METRICS
                }
                for label, fraction in (("p05", 0.05), ("p50", 0.50), ("p95", 0.95))
            },
        }
    return summaries


def validate_policy(policy_value: Any) -> dict[str, Any]:
    """Validate a schema-v2/v3 template, disabled proposal, or approved policy."""
    policy = _mapping(policy_value, "policy")
    schema_version = policy.get("schema_version")
    if schema_version == 4:
        return validate_dynamic_diagnostic_proposal(policy)
    if schema_version not in {2, 3}:
        raise ValueError("unsupported schema_version")
    if policy.get("policy_id") != "light_cup_wall_pick-contact":
        raise ValueError("unsupported policy_id")
    _validate_units(policy.get("units"))
    fingerprint = _mapping(policy.get("fingerprint"), "fingerprint")
    expected_fingerprint = {
        "source_commit",
        "dependency_commit",
        "model_sha256",
        "scene_sha256",
        "motion_policy_sha256",
        "source_evidence_sha256",
    }
    if set(fingerprint) != expected_fingerprint:
        raise ValueError("fingerprint must contain exact policy artifact identities")
    for field in COMMIT_FIELDS:
        _identifier(fingerprint.get(field), f"fingerprint.{field}", 40)
    for field in V2_HASH_FIELDS:
        _identifier(fingerprint.get(field), f"fingerprint.{field}", 64)
    source_hash = fingerprint.get("source_evidence_sha256")
    if source_hash is not None:
        _identifier(source_hash, "fingerprint.source_evidence_sha256", 64)
    evaluation = _mapping(policy.get("evaluation"), "evaluation")
    if set(evaluation) != {"maximum_observation_age_s", "minimum_consecutive_samples"}:
        raise ValueError("evaluation controls are incomplete")
    if _finite(evaluation["maximum_observation_age_s"], "maximum_observation_age_s") <= 0.0:
        raise ValueError("maximum_observation_age_s must be positive")
    if _integer(evaluation["minimum_consecutive_samples"], "minimum_consecutive_samples") <= 0:
        raise ValueError("minimum_consecutive_samples must be positive")
    allowed = _list(policy.get("allowed_other_contact_bodies"), "allowed_other_contact_bodies")
    if any(not isinstance(item, str) or not item for item in allowed):
        raise ValueError("allowed_other_contact_bodies must contain non-empty strings")
    policy_regimes = PHYSICAL_REGIMES if schema_version == 3 else REGIMES
    regimes = _mapping(policy.get("regimes"), "regimes")
    if set(regimes) != set(policy_regimes):
        raise ValueError("policy must contain every calibration regime")
    for regime in policy_regimes:
        summary = _mapping(regimes[regime], regime)
        _integer(summary.get("sample_count"), f"{regime}.sample_count")
        quantiles = _mapping(summary.get("quantiles"), f"{regime}.quantiles")
        if set(quantiles) != {"p05", "p50", "p95"}:
            raise ValueError(f"{regime} quantiles must contain p05, p50, and p95")
    if schema_version == 3:
        validate_unilateral_rejection_contracts(policy.get("unilateral_rejection_contracts"))
    matrix = _mapping(policy.get("misclassification_matrix"), "confusion matrix")
    if set(matrix) != set(policy_regimes):
        raise ValueError("confusion matrix must contain every actual regime")
    for actual in policy_regimes:
        row = _mapping(matrix[actual], f"confusion matrix row {actual}")
        if set(row) != set(CLASSIFICATION_LABELS):
            raise ValueError(f"confusion matrix row {actual} has empty cells")
        for predicted, count in row.items():
            _integer(count, f"confusion matrix {actual}/{predicted}")
    status = policy.get("calibration_status")
    if status not in {"PLANNED", "FAILED", "VALID"}:
        raise ValueError("calibration_status must be PLANNED, FAILED, or VALID")
    thresholds = _mapping(policy.get("thresholds"), "thresholds")
    expected_thresholds = {
        "minimum_bilateral_force_n",
        "maximum_compression_distance_m",
        "maximum_safe_force_n",
        "maximum_hold_linear_speed_m_s",
        "minimum_stable_hold_duration_s",
    }
    if set(thresholds) != expected_thresholds:
        raise ValueError("thresholds are incomplete")
    if status == "VALID":
        if source_hash is None:
            raise ValueError("VALID policy requires source_evidence_sha256")
        if any(regimes[name]["sample_count"] < 20 for name in policy_regimes):
            raise ValueError("VALID policy requires at least 20 samples per regime")
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) <= 0.0
            for value in thresholds.values()
        ):
            raise ValueError("VALID policy requires finite proposed thresholds")
        if thresholds["minimum_bilateral_force_n"] >= thresholds["maximum_safe_force_n"]:
            raise ValueError("minimum bilateral force must remain below maximum safe force")
    elif status == "PLANNED" and any(value is not None for value in thresholds.values()):
        raise ValueError("PLANNED policy thresholds must remain null")

    approval = _mapping(policy.get("approval"), "approval")
    expected_approval = {
        "enabled",
        "approved",
        "approved_by",
        "approved_at",
        "proposal_sha256",
    }
    if set(approval) != expected_approval:
        raise ValueError("approval envelope is incomplete")
    enabled = approval["enabled"]
    approved = approval["approved"]
    if not isinstance(enabled, bool) or not isinstance(approved, bool):
        raise ValueError("approval enabled/approved flags must be boolean")
    if enabled != approved:
        raise ValueError("enabled policy requires approved approval metadata")
    proposal_hash = approval["proposal_sha256"]
    if status == "PLANNED":
        if enabled or approval["approved_by"] is not None or approval["approved_at"] is not None:
            raise ValueError("PLANNED policy must remain disabled and unapproved")
        if proposal_hash is not None:
            raise ValueError("PLANNED policy must not claim a proposal hash")
    else:
        stored_hash = _identifier(proposal_hash, "approval.proposal_sha256", 64)
        if stored_hash != proposal_sha256(policy):
            raise ValueError("proposal hash mismatch")
        if enabled:
            if not isinstance(approval["approved_by"], str) or not approval["approved_by"]:
                raise ValueError("approved policy requires approved_by")
            if not isinstance(approval["approved_at"], str) or not approval["approved_at"]:
                raise ValueError("approved policy requires approved_at")
            try:
                approved_at = datetime.fromisoformat(approval["approved_at"])
            except ValueError as error:
                raise ValueError(
                    "approved_at must be an ISO-8601 timestamp with timezone"
                ) from error
            if approved_at.tzinfo is None or approved_at.utcoffset() is None:
                raise ValueError("approved_at must include a timezone")
        elif approval["approved_by"] is not None or approval["approved_at"] is not None:
            raise ValueError("disabled proposal must not contain approval identity")
    return policy


def build_dynamic_transport_proposal(
    runs: list[dict[str, Any]],
    *,
    provenance: dict[str, Any],
    frozen_behavior: dict[str, Any],
) -> dict[str, Any]:
    """Build a deterministic disabled schema-v4 diagnostic-only proposal."""

    copied_runs = copy.deepcopy(runs)
    peak_forces = [float(item["peak_global_max_single_contact_force_n"]) for item in copied_runs]
    exposures = [float(item["force_time_exposure_n_s"]) for item in copied_runs]
    shadow_exposures = [
        float(item["shadow_excess_force_time_exposure_n_s"]) for item in copied_runs
    ]
    proposal: dict[str, Any] = {
        "schema_version": 4,
        "proposal_kind": "phase_aware_dynamic_transport_diagnostic",
        "policy_id": "light_cup_wall_pick-contact",
        "acceptance_role": "diagnostic_only",
        "independent_experiment_units": 5,
        "statistical_design": {
            "runs_1_to_4": "descriptive_repeats",
            "run_5": "preregistered_replication",
            "waypoint_role": "repeated_measure",
            "fits_dynamic_threshold": False,
        },
        "static_contact_contract": {
            "phase": "PRE_TRANSPORT_STATIC_HOLD",
            "metric": "maximum_normal_force_n",
            "comparison": ">",
            "maximum_safe_force_n": 1.1579004532160448,
            "role": "formal_hard_gate",
        },
        "dynamic_transport_contract": {
            "phase": "DYNAMIC_TRANSPORT_SHADOW",
            "shadow_metric": "maximum_normal_force_n",
            "static_shadow_threshold_n": 1.1579004532160448,
            "static_threshold_role": "shadow_only",
            "hazard_metric": "global_max_single_contact_force_n",
            "diagnostic_hard_stop_n": 11.60,
            "hazard_comparison": ">=",
            "diagnostic_hard_stop_role": "absolute_diagnostic_safety_stop_only",
            "maximum_reaction_steps": 25,
            "maximum_reaction_time_s": 0.050,
            "reaction_bound_kind": "plugin_ack_upper_bound",
        },
        "metric_definitions": dynamic_metric_definitions(),
        "provenance": copy.deepcopy(provenance),
        "frozen_behavior": copy.deepcopy(frozen_behavior),
        "runs": copied_runs,
        "descriptive_results": {
            "run_count": len(copied_runs),
            "peak_force_range_n": [min(peak_forces), max(peak_forces)],
            "force_time_exposure_range_n_s": [min(exposures), max(exposures)],
            "shadow_excess_exposure_range_n_s": [
                min(shadow_exposures),
                max(shadow_exposures),
            ],
            "maximum_left_fingertip_compression_m": max(
                float(item["maximum_left_fingertip_compression_m"]) for item in copied_runs
            ),
            "maximum_right_fingertip_compression_m": max(
                float(item["maximum_right_fingertip_compression_m"]) for item in copied_runs
            ),
        },
        "approval": {
            "enabled": False,
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "proposal_sha256": None,
        },
    }
    proposal["approval"]["proposal_sha256"] = proposal_sha256(proposal)
    validate_dynamic_diagnostic_proposal(proposal)
    return proposal


def analyze_bytes(raw: bytes) -> dict[str, Any]:
    """Analyze raw JSON evidence and return a disabled proposal."""
    evidence = validate_evidence(json.loads(raw))
    all_regimes = evidence["regimes"]
    analyzed_regimes = PHYSICAL_REGIMES if evidence["source_schema_version"] == 3 else REGIMES
    ordered_regimes = {
        name: sorted(all_regimes[name], key=lambda sample: sample["publisher_sequence"])
        for name in analyzed_regimes
    }
    calibration = {
        name: [sample for index, sample in enumerate(ordered_regimes[name], start=1) if index % 5]
        for name in analyzed_regimes
    }
    evaluation = {
        name: [
            sample for index, sample in enumerate(ordered_regimes[name], start=1) if index % 5 == 0
        ]
        for name in analyzed_regimes
    }
    matrix = {
        actual: {predicted: 0 for predicted in CLASSIFICATION_LABELS} for actual in analyzed_regimes
    }
    proposal_schema_version = 3 if evidence["source_schema_version"] == 3 else 2
    proposal: dict[str, Any] = {
        "schema_version": proposal_schema_version,
        "policy_id": "light_cup_wall_pick-contact",
        "source_schema_version": evidence["source_schema_version"],
        "calibration_status": "FAILED",
        "failure_reason": None,
        "units": dict(REQUIRED_UNITS),
        "fingerprint": {
            **evidence["normalized_fingerprint"],
            "source_evidence_sha256": hashlib.sha256(raw).hexdigest(),
        },
        "evaluation": {
            "maximum_observation_age_s": 0.10,
            "minimum_consecutive_samples": 5,
        },
        "allowed_other_contact_bodies": ["table"],
        "split_method": "per_regime_ordered_index_modulo_5",
        "classification_contract": {
            "slip_metric": "maximum_linear_speed_over_split_window_m_s",
            "calibration_window_sample_counts": {
                name: len(calibration[name]) for name in analyzed_regimes
            },
            "evaluation_window_sample_counts": {
                name: len(evaluation[name]) for name in analyzed_regimes
            },
        },
        "calibration_sample_count": sum(map(len, calibration.values())),
        "evaluation_sample_count": sum(map(len, evaluation.values())),
        "regimes": _summaries(all_regimes),
        "thresholds": {},
        "safety_margins": {},
        "false_positive_count": 0,
        "false_negative_count": 0,
        "misclassification_matrix": matrix,
        "negative_control_labels": {"table_only": {}, "post_release": {}},
        "approval": {
            "enabled": False,
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "proposal_sha256": None,
        },
    }
    if proposal_schema_version == 3:
        proposal["unilateral_rejection_contracts"] = copy.deepcopy(
            evidence["unilateral_rejection_contracts"]
        )
    try:
        thresholds, margins = _thresholds(calibration)
    except ValueError as error:
        proposal["failure_reason"] = str(error)
        proposal["thresholds"] = {
            "minimum_bilateral_force_n": None,
            "maximum_compression_distance_m": None,
            "maximum_safe_force_n": None,
            "maximum_hold_linear_speed_m_s": None,
            "minimum_stable_hold_duration_s": None,
        }
        proposal["approval"]["proposal_sha256"] = proposal_sha256(proposal)
        validate_policy(proposal)
        return proposal
    proposal["thresholds"] = thresholds
    proposal["safety_margins"] = margins
    errors = 0
    for actual in analyzed_regimes:
        window_maximum_speed = max(
            (sample_metrics(sample)["linear_speed_m_s"] for sample in evaluation[actual]),
            default=0.0,
        )
        for sample in evaluation[actual]:
            predicted = classify(
                sample,
                thresholds,
                window_maximum_linear_speed_m_s=window_maximum_speed,
            )
            matrix[actual][predicted] += 1
            errors += predicted != actual
            for subcohort in ("table_only", "post_release"):
                if sample["subcohorts"][subcohort]:
                    labels = proposal["negative_control_labels"][subcohort]
                    labels[predicted] = labels.get(predicted, 0) + 1
    proposal["false_positive_count"] = errors
    proposal["false_negative_count"] = errors
    if errors:
        proposal["failure_reason"] = f"evaluation classification has {errors} errors"
    else:
        proposal["calibration_status"] = "VALID"
    proposal["approval"]["proposal_sha256"] = proposal_sha256(proposal)
    validate_policy(proposal)
    return proposal


def analyze(source: Path) -> dict[str, Any]:
    return analyze_bytes(source.read_bytes())


def _atomic_yaml_write(path: Path, document: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            yaml.safe_dump(document, stream, sort_keys=False)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--dynamic-input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", type=Path)
    parser.add_argument("--approve", type=Path)
    parser.add_argument("--proposal-sha256")
    parser.add_argument("--approved-by")
    parser.add_argument("--approved-at")
    args = parser.parse_args(argv)
    try:
        if args.dynamic_input and args.output:
            dynamic_input = _mapping(
                json.loads(args.dynamic_input.read_text(encoding="utf-8")),
                "dynamic input",
            )
            if set(dynamic_input) != {"runs", "provenance", "frozen_behavior"}:
                raise ValueError(
                    "dynamic input must contain exact runs, provenance, and frozen_behavior keys"
                )
            proposal = build_dynamic_transport_proposal(
                _list(dynamic_input["runs"], "runs"),
                provenance=_mapping(dynamic_input["provenance"], "provenance"),
                frozen_behavior=_mapping(dynamic_input["frozen_behavior"], "frozen_behavior"),
            )
            _atomic_yaml_write(args.output, proposal)
        elif args.validate:
            validate_policy(yaml.safe_load(args.validate.read_text(encoding="utf-8")))
        elif args.approve and args.output:
            if not all((args.proposal_sha256, args.approved_by, args.approved_at)):
                parser.error(
                    "--approve requires proposal hash, approval identity, time, and output"
                )
            proposal = yaml.safe_load(args.approve.read_text(encoding="utf-8"))
            activated = approve_proposal(
                proposal,
                ApprovalRecord(
                    proposal_sha256=args.proposal_sha256,
                    approved_by=args.approved_by,
                    approved_at=args.approved_at,
                ),
            )
            validate_policy(activated)
            if args.output.is_file():
                existing = yaml.safe_load(args.output.read_text(encoding="utf-8"))
                existing_approval = _mapping(existing.get("approval"), "existing approval")
                if (
                    existing_approval.get("approved") is True
                    and existing_approval.get("proposal_sha256")
                    != activated["approval"]["proposal_sha256"]
                ):
                    raise ValueError("refusing to overwrite approved policy with different hash")
            _atomic_yaml_write(args.output, activated)
        elif args.input and args.output:
            proposal = analyze(args.input)
            _atomic_yaml_write(args.output, proposal)
            if proposal["calibration_status"] != "VALID":
                print(proposal["failure_reason"], file=sys.stderr)
                return 1
        else:
            parser.error("choose --validate, --approve with --output, or --input with --output")
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0
