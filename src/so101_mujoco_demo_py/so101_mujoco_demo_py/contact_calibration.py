"""Validate and analyze atomic MuJoCo contact-calibration evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import yaml

REGIMES = (
    "no_contact",
    "left_only",
    "right_only",
    "bilateral_touch",
    "over_compression",
    "micro_lift_slip",
    "stable_hold",
)
REQUIRED_UNITS = {
    "signed_distance": "m",
    "normal_force": "N",
    "linear_speed": "m/s",
    "joint_position": "rad",
    "simulation_time": "s",
    "receipt_time": "s",
}
HASH_FIELDS = ("model_sha256", "config_sha256")
COMMIT_FIELDS = ("source_commit", "dependency_commit")
CONTACT_FIELDS = (
    "left_fingertip_contacts",
    "right_fingertip_contacts",
    "other_object_contacts",
)
METRICS = (
    "minimum_signed_distance_m",
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
    fingerprint: dict[str, str],
) -> dict[str, Any]:
    sample = _mapping(sample_value, f"{regime} sample")
    if sample.get("regime") != regime:
        raise ValueError(f"sample regime mismatch for {regime}")
    subcohorts = _mapping(sample.get("subcohorts"), "subcohorts")
    if set(subcohorts) != {"table_only", "post_release"} or any(
        not isinstance(value, bool) for value in subcohorts.values()
    ):
        raise ValueError("subcohorts must contain boolean table_only and post_release flags")
    for field, expected in fingerprint.items():
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
    if evidence.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    _validate_units(evidence.get("units"))
    fingerprint = {
        field: _identifier(evidence.get(field), field, 40 if field in COMMIT_FIELDS else 64)
        for field in (*COMMIT_FIELDS, *HASH_FIELDS)
    }
    regimes = _mapping(evidence.get("regimes"), "regimes")
    if set(regimes) != set(REGIMES):
        missing = sorted(set(REGIMES) - set(regimes))
        raise ValueError(f"missing regimes: {missing}")

    samples: list[dict[str, Any]] = []
    for regime in REGIMES:
        regime_samples = _list(regimes[regime], regime)
        if len(regime_samples) < 20:
            raise ValueError(f"{regime} requires at least 20 valid samples")
        samples.extend(_validate_sample(sample, regime, fingerprint) for sample in regime_samples)

    sessions = {sample["simulation_session_id"] for sample in samples}
    if len(sessions) != 1:
        raise ValueError("mixed simulation session data")
    reset_epochs = {sample["reset_epoch"] for sample in samples}
    if len(reset_epochs) != 1:
        raise ValueError("mixed reset epoch data")
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
    return evidence


def _contact_force(sample: dict[str, Any], field: str) -> float:
    return max((float(item["normal_force_n"]) for item in sample[field]), default=0.0)


def sample_metrics(sample: dict[str, Any]) -> dict[str, float]:
    linear = sample["object_twist_world"]["linear_m_s"]
    return {
        "minimum_signed_distance_m": float(sample["minimum_signed_distance_m"]),
        "maximum_normal_force_n": float(sample["maximum_normal_force_n"]),
        "linear_speed_m_s": math.sqrt(sum(float(value) ** 2 for value in linear)),
        "left_normal_force_n": _contact_force(sample, "left_fingertip_contacts"),
        "right_normal_force_n": _contact_force(sample, "right_fingertip_contacts"),
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


def _thresholds(
    regimes: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, float], dict[str, float]]:
    metrics = {
        name: [sample_metrics(sample) for sample in samples] for name, samples in regimes.items()
    }
    unilateral = _flatten(metrics, ("no_contact", "left_only", "right_only"))
    bilateral = _flatten(
        metrics,
        ("bilateral_touch", "over_compression", "micro_lift_slip", "stable_hold"),
    )
    minimum_force, force_margin = _separating_threshold(
        [sample["maximum_normal_force_n"] for sample in unilateral],
        [sample["maximum_normal_force_n"] for sample in bilateral],
        "bilateral force",
    )
    acceptable_compression = _flatten(
        metrics, ("bilateral_touch", "micro_lift_slip", "stable_hold")
    )
    maximum_compression, compression_margin = _separating_threshold(
        [max(0.0, -sample["minimum_signed_distance_m"]) for sample in acceptable_compression],
        [max(0.0, -sample["minimum_signed_distance_m"]) for sample in metrics["over_compression"]],
        "compression distance",
    )
    acceptable_force = _flatten(metrics, ("bilateral_touch", "micro_lift_slip", "stable_hold"))
    maximum_force, safe_force_margin = _separating_threshold(
        [sample["maximum_normal_force_n"] for sample in acceptable_force],
        [sample["maximum_normal_force_n"] for sample in metrics["over_compression"]],
        "safe force",
    )
    maximum_speed, speed_margin = _separating_threshold(
        [sample["linear_speed_m_s"] for sample in metrics["stable_hold"]],
        [sample["linear_speed_m_s"] for sample in metrics["micro_lift_slip"]],
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


def classify(sample: dict[str, Any], thresholds: dict[str, float]) -> str:
    """Classify one atomic sample using only calibrated measurements."""
    left = bool(sample["left_fingertip_contacts"])
    right = bool(sample["right_fingertip_contacts"])
    if not left and not right:
        return "no_contact"
    if left and not right:
        return "left_only"
    if right and not left:
        return "right_only"
    metrics = sample_metrics(sample)
    compression = max(0.0, -metrics["minimum_signed_distance_m"])
    if (
        compression >= thresholds["maximum_compression_distance_m"]
        or metrics["maximum_normal_force_n"] >= thresholds["maximum_safe_force_n"]
    ):
        return "over_compression"
    if metrics["linear_speed_m_s"] >= thresholds["maximum_hold_linear_speed_m_s"]:
        return "micro_lift_slip"
    if metrics["contact_duration_s"] >= thresholds["minimum_stable_hold_duration_s"]:
        return "stable_hold"
    return "bilateral_touch"


def _summaries(regimes: dict[str, list[dict[str, Any]]]) -> dict[str, dict[str, Any]]:
    summaries: dict[str, dict[str, Any]] = {}
    for regime in REGIMES:
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
    """Validate a disabled proposal without granting approval or enablement."""
    policy = _mapping(policy_value, "policy")
    if policy.get("schema_version") != 1:
        raise ValueError("unsupported schema_version")
    if policy.get("enabled") is not False:
        if policy.get("approved_by_user") is not True:
            raise ValueError(
                "enabled policy requires approved_by_user, and this proposal must remain disabled"
            )
        raise ValueError("contact calibration proposal must remain disabled")
    if policy.get("approved_by_user") is not False:
        raise ValueError("approved_by_user must remain false pending the approval stop")
    _validate_units(policy.get("units"))
    for field in COMMIT_FIELDS:
        _identifier(policy.get(field), field, 40)
    for field in HASH_FIELDS:
        _identifier(policy.get(field), field, 64)
    source_hash = policy.get("source_evidence_sha256")
    if source_hash is not None:
        _identifier(source_hash, "source_evidence_sha256", 64)
    regimes = _mapping(policy.get("regimes"), "regimes")
    if set(regimes) != set(REGIMES):
        raise ValueError("policy must contain every calibration regime")
    for regime in REGIMES:
        summary = _mapping(regimes[regime], regime)
        _integer(summary.get("sample_count"), f"{regime}.sample_count")
        quantiles = _mapping(summary.get("quantiles"), f"{regime}.quantiles")
        if set(quantiles) != {"p05", "p50", "p95"}:
            raise ValueError(f"{regime} quantiles must contain p05, p50, and p95")
    matrix = _mapping(policy.get("misclassification_matrix"), "confusion matrix")
    if set(matrix) != set(REGIMES):
        raise ValueError("confusion matrix must contain every actual regime")
    for actual in REGIMES:
        row = _mapping(matrix[actual], f"confusion matrix row {actual}")
        if set(row) != set(REGIMES):
            raise ValueError(f"confusion matrix row {actual} has empty cells")
        for predicted, count in row.items():
            _integer(count, f"confusion matrix {actual}/{predicted}")
    status = policy.get("calibration_status")
    if status not in {"PLANNED", "FAILED", "VALID"}:
        raise ValueError("calibration_status must be PLANNED, FAILED, or VALID")
    if status == "VALID":
        if source_hash is None:
            raise ValueError("VALID policy requires source_evidence_sha256")
        if any(regimes[name]["sample_count"] < 20 for name in REGIMES):
            raise ValueError("VALID policy requires at least 20 samples per regime")
        thresholds = _mapping(policy.get("thresholds"), "thresholds")
        if not thresholds or any(not math.isfinite(float(value)) for value in thresholds.values()):
            raise ValueError("VALID policy requires finite proposed thresholds")
    return policy


def analyze_bytes(raw: bytes) -> dict[str, Any]:
    """Analyze raw JSON evidence and return a disabled proposal."""
    evidence = validate_evidence(json.loads(raw))
    all_regimes = evidence["regimes"]
    calibration = {
        name: [sample for sample in all_regimes[name] if sample["publisher_sequence"] % 5]
        for name in REGIMES
    }
    evaluation = {
        name: [sample for sample in all_regimes[name] if sample["publisher_sequence"] % 5 == 0]
        for name in REGIMES
    }
    matrix = {actual: {predicted: 0 for predicted in REGIMES} for actual in REGIMES}
    proposal: dict[str, Any] = {
        "schema_version": 1,
        "calibration_status": "FAILED",
        "failure_reason": None,
        "approved_by_user": False,
        "enabled": False,
        "units": dict(REQUIRED_UNITS),
        "source_commit": evidence["source_commit"],
        "dependency_commit": evidence["dependency_commit"],
        "model_sha256": evidence["model_sha256"],
        "config_sha256": evidence["config_sha256"],
        "source_evidence_sha256": hashlib.sha256(raw).hexdigest(),
        "split_method": "publisher_sequence_modulo_5",
        "calibration_sample_count": sum(map(len, calibration.values())),
        "evaluation_sample_count": sum(map(len, evaluation.values())),
        "regimes": _summaries(all_regimes),
        "thresholds": {},
        "safety_margins": {},
        "false_positive_count": 0,
        "false_negative_count": 0,
        "misclassification_matrix": matrix,
        "negative_control_labels": {"table_only": {}, "post_release": {}},
    }
    try:
        thresholds, margins = _thresholds(calibration)
    except ValueError as error:
        proposal["failure_reason"] = str(error)
        validate_policy(proposal)
        return proposal
    proposal["thresholds"] = thresholds
    proposal["safety_margins"] = margins
    errors = 0
    for actual in REGIMES:
        for sample in evaluation[actual]:
            predicted = classify(sample, thresholds)
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
    validate_policy(proposal)
    return proposal


def analyze(source: Path) -> dict[str, Any]:
    return analyze_bytes(source.read_bytes())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--validate", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.validate:
            validate_policy(yaml.safe_load(args.validate.read_text(encoding="utf-8")))
        elif args.input and args.output:
            proposal = analyze(args.input)
            args.output.write_text(yaml.safe_dump(proposal, sort_keys=False), encoding="utf-8")
            if proposal["calibration_status"] != "VALID":
                print(proposal["failure_reason"], file=sys.stderr)
                return 1
        else:
            parser.error("choose --validate or --input with --output")
    except (KeyError, TypeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0
