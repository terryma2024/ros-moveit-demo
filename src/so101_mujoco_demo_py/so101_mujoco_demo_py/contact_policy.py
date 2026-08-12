"""Hash-bound activation and typed loading for calibrated contact policy."""

from __future__ import annotations

import copy
import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

_THRESHOLD_KEYS = frozenset(
    {
        "minimum_bilateral_force_n",
        "maximum_compression_distance_m",
        "maximum_safe_force_n",
        "maximum_hold_linear_speed_m_s",
        "minimum_stable_hold_duration_s",
    }
)
_EVALUATION_KEYS = frozenset({"maximum_observation_age_s", "minimum_consecutive_samples"})
_FINGERPRINT_KEYS = frozenset(
    {
        "source_commit",
        "dependency_commit",
        "model_sha256",
        "scene_sha256",
        "motion_policy_sha256",
        "source_evidence_sha256",
    }
)
_APPROVAL_KEYS = frozenset({"enabled", "approved", "approved_by", "approved_at", "proposal_sha256"})
_UNILATERAL_CONTRACT_KEYS = frozenset(
    {
        "stable_grasp_allowed",
        "expected_failure_code",
        "physical_evidence",
        "physical_calibration_sample_count",
        "physical_evaluation_sample_count",
        "physical_misclassification_rate",
    }
)
_UNILATERAL_FAILURE_CODES = {
    "left_only": "GRASP_RIGHT_CONTACT_MISSING",
    "right_only": "GRASP_LEFT_CONTACT_MISSING",
}
_DIAGNOSTIC_PROPOSAL_KEYS = frozenset(
    {
        "schema_version",
        "proposal_kind",
        "policy_id",
        "acceptance_role",
        "independent_experiment_units",
        "statistical_design",
        "static_contact_contract",
        "dynamic_transport_contract",
        "metric_definitions",
        "provenance",
        "frozen_behavior",
        "runs",
        "descriptive_results",
        "approval",
    }
)
_DIAGNOSTIC_PROVENANCE_KEYS = frozenset(
    {
        "source_commit",
        "dependency_commit",
        "install_tree_sha256",
        "runtime_fingerprint_sha256",
        "contact_policy_sha256",
    }
)
_FROZEN_BEHAVIOR_KEYS = frozenset(
    {
        "manifest_sha256",
        "motion_policy_sha256",
        "grasp_strategy_sha256",
        "baseline_transport_sha256",
        "scene_sha256",
        "robot_mjcf_sha256",
        "protected_gazebo_tree_oid",
    }
)
_DYNAMIC_RUN_KEYS = frozenset(
    {
        "run_id",
        "run_role",
        "status",
        "outcome_class",
        "physical_transport_outcome",
        "simulation_session_id",
        "reset_epoch",
        "source_commit",
        "install_tree_sha256",
        "runtime_fingerprint_sha256",
        "raw_evidence_sha256",
        "summary_sha256",
        "peak_global_max_single_contact_force_n",
        "force_time_exposure_n_s",
        "shadow_excess_force_time_exposure_n_s",
        "net_contact_impulse_vector_n_s",
        "maximum_left_fingertip_compression_m",
        "maximum_right_fingertip_compression_m",
        "sustained_overpressure_windows",
        "waypoints",
    }
)
_WAYPOINT_DIAGNOSTIC_KEYS = frozenset(
    {
        "waypoint",
        "statistical_role",
        "first_physics_step",
        "last_physics_step",
        "peak_global_max_single_contact_force_n",
        "force_time_exposure_n_s",
        "shadow_excess_force_time_exposure_n_s",
        "net_contact_impulse_vector_n_s",
        "maximum_left_fingertip_compression_m",
        "maximum_right_fingertip_compression_m",
    }
)
_METRIC_DEFINITIONS = {
    "maximum_normal_force_n": "maximum single normal force across all tracked cup contacts",
    "left_fingertip_total_normal_force_n": "sum of cup-left-fingertip normal contact forces per physics step",
    "right_fingertip_total_normal_force_n": "sum of cup-right-fingertip normal contact forces per physics step",
    "fingertip_max_single_contact_force_n": "maximum single normal force across cup-fingertip contacts per physics step",
    "global_max_single_contact_force_n": "maximum single normal force across all tracked cup contacts per physics step",
    "force_time_exposure_n_s": "simulation-time trapezoidal integral of global_max_single_contact_force_n",
    "shadow_excess_force_time_exposure_n_s": "simulation-time trapezoidal integral of max(global_max_single_contact_force_n-static_shadow_threshold,0)",
    "net_contact_impulse_vector_n_s": "simulation-time trapezoidal integral of the vector sum of tracked contact normal forces",
    "left_fingertip_compression_m": "max(0,-signed_distance) over cup-left-fingertip whitelist contacts only",
    "right_fingertip_compression_m": "max(0,-signed_distance) over cup-right-fingertip whitelist contacts only",
    "sustained_overpressure_window": "contiguous physics steps strictly above the static shadow threshold with no grace period",
}


@dataclass(frozen=True, slots=True)
class ContactThresholds:
    minimum_bilateral_force_n: float
    maximum_compression_distance_m: float
    maximum_safe_force_n: float
    maximum_hold_linear_speed_m_s: float
    minimum_stable_hold_duration_s: float


@dataclass(frozen=True, slots=True)
class ContactEvaluationPolicy:
    maximum_observation_age_s: float
    minimum_consecutive_samples: int


@dataclass(frozen=True, slots=True)
class ApprovalRecord:
    proposal_sha256: str
    approved_by: str
    approved_at: str


@dataclass(frozen=True, slots=True)
class ContactPolicyFingerprint:
    dependency_commit: str
    model_sha256: str
    scene_sha256: str
    motion_policy_sha256: str
    source_evidence_sha256: str


@dataclass(frozen=True, slots=True)
class ApprovedContactPolicy:
    policy_id: str
    thresholds: ContactThresholds
    evaluation: ContactEvaluationPolicy
    allowed_other_contact_bodies: frozenset[str]
    fingerprint: ContactPolicyFingerprint
    approval: ApprovalRecord


def _mapping(value: object, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    if not all(isinstance(key, str) for key in value):
        raise ValueError(f"{name} keys must be strings")
    return value


def _exact_keys(value: Mapping[str, Any], expected: frozenset[str], name: str) -> None:
    unknown = sorted(set(value) - expected)
    if unknown:
        raise ValueError(f"unknown {name} keys: {', '.join(unknown)}")
    missing = sorted(expected - set(value))
    if missing:
        raise ValueError(f"missing {name} keys: {', '.join(missing)}")


def _identifier(value: object, name: str, length: int) -> str:
    if not isinstance(value, str) or len(value) != length:
        raise ValueError(f"{name} must be a {length}-character hexadecimal identifier")
    try:
        int(value, 16)
    except ValueError as error:
        raise ValueError(f"{name} must be hexadecimal") from error
    if set(value) == {"0"}:
        raise ValueError(f"{name} uses a placeholder hash")
    return value


def _nonempty_string(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _positive(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be positive and finite")
    try:
        converted = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be positive and finite") from error
    if not math.isfinite(converted) or converted <= 0.0:
        raise ValueError(f"{name} must be positive and finite")
    return converted


def _positive_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _timestamp(value: object) -> str:
    result = _nonempty_string(value, "approved_at")
    try:
        parsed = datetime.fromisoformat(result)
    except ValueError as error:
        raise ValueError("approved_at must be an ISO-8601 timestamp with timezone") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("approved_at must include a timezone")
    return result


def validate_unilateral_rejection_contracts(value: object) -> dict[str, object]:
    """Validate evidence-bound unilateral contracts as non-statistical metadata."""

    source = _mapping(value, "unilateral_rejection_contracts")
    _exact_keys(source, frozenset(_UNILATERAL_FAILURE_CODES), "unilateral contract")
    for regime, expected_code in _UNILATERAL_FAILURE_CODES.items():
        contract = _mapping(source[regime], f"{regime} contract")
        _exact_keys(contract, _UNILATERAL_CONTRACT_KEYS, f"{regime} contract")
        if contract["stable_grasp_allowed"] is not False:
            raise ValueError(f"{regime}.stable_grasp_allowed must be false")
        if contract["expected_failure_code"] != expected_code:
            raise ValueError(f"{regime}.expected_failure_code is invalid")
        for field in (
            "physical_calibration_sample_count",
            "physical_evaluation_sample_count",
            "physical_misclassification_rate",
        ):
            if contract[field] is not None:
                raise ValueError(f"{regime}.{field} must be null for a non-statistical contract")
        physical = _mapping(contract["physical_evidence"], f"{regime}.physical_evidence")
        _exact_keys(
            physical,
            frozenset({"disposition", "references"}),
            f"{regime}.physical_evidence",
        )
        if physical["disposition"] not in {"observed", "physical_unreachable"}:
            raise ValueError(f"{regime}.physical_evidence disposition is invalid")
        references = physical["references"]
        if not isinstance(references, list) or not references:
            raise ValueError(f"{regime}.physical_evidence requires an authentic reference")
        for index, reference_value in enumerate(references):
            reference = _mapping(reference_value, f"{regime} reference {index}")
            _exact_keys(
                reference,
                frozenset({"experiment_id", "artifact_sha256"}),
                f"{regime} reference {index}",
            )
            _nonempty_string(reference["experiment_id"], f"{regime} reference experiment_id")
            _identifier(reference["artifact_sha256"], f"{regime} artifact_sha256", 64)
    return copy.deepcopy(dict(source))


def proposal_sha256(document: Mapping[str, object]) -> str:
    """Hash every proposal field except activation/approval metadata."""

    subject = copy.deepcopy(dict(document))
    subject.pop("approval", None)
    try:
        canonical = json.dumps(
            subject,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise ValueError("proposal must contain finite JSON-compatible values") from error
    return hashlib.sha256(canonical).hexdigest()


def _nonnegative(value: object, name: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{name} must be non-negative and finite")
    try:
        converted = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be non-negative and finite") from error
    if not math.isfinite(converted) or converted < 0.0:
        raise ValueError(f"{name} must be non-negative and finite")
    return converted


def _nonnegative_integer(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    return value


def _vector3(value: object, name: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{name} must contain three finite values")
    return tuple(
        _nonnegative(abs(float(item)), name) * (-1.0 if float(item) < 0.0 else 1.0)
        for item in value
    )


def _validate_waypoint_diagnostic(value: object, expected_waypoint: int) -> None:
    item = _mapping(value, f"waypoint {expected_waypoint}")
    _exact_keys(item, _WAYPOINT_DIAGNOSTIC_KEYS, f"waypoint {expected_waypoint}")
    if item["waypoint"] != expected_waypoint:
        raise ValueError("waypoint order must remain 1 through 5")
    if item["statistical_role"] != "repeated_measure":
        raise ValueError("waypoint statistical_role must be repeated_measure")
    first = _nonnegative_integer(item["first_physics_step"], "first_physics_step")
    last = _nonnegative_integer(item["last_physics_step"], "last_physics_step")
    if last < first:
        raise ValueError("waypoint physics-step range is reversed")
    for name in (
        "peak_global_max_single_contact_force_n",
        "force_time_exposure_n_s",
        "shadow_excess_force_time_exposure_n_s",
        "maximum_left_fingertip_compression_m",
        "maximum_right_fingertip_compression_m",
    ):
        _nonnegative(item[name], name)
    _vector3(item["net_contact_impulse_vector_n_s"], "net_contact_impulse_vector_n_s")


def _validate_dynamic_run(
    value: object,
    *,
    index: int,
    provenance: Mapping[str, Any],
) -> str:
    item = _mapping(value, f"dynamic run {index}")
    _exact_keys(item, _DYNAMIC_RUN_KEYS, f"dynamic run {index}")
    run_id = _nonempty_string(item["run_id"], "run_id")
    expected_role = "preregistered_replication" if index == 5 else "descriptive_repeat"
    if item["run_role"] != expected_role:
        raise ValueError(f"run {index} must use run_role {expected_role}")
    if item["status"] != "VALID" or item["outcome_class"] != "PHYSICAL_TRANSPORT_SUCCESS":
        raise ValueError("schema-v4 proposal requires five physical transport successes")
    if item["physical_transport_outcome"] != "FORMAL_MOVE_ABOVE_PLACE_PROVED":
        raise ValueError("physical transport outcome is not formally proved")
    _nonempty_string(item["simulation_session_id"], "simulation_session_id")
    _nonnegative_integer(item["reset_epoch"], "reset_epoch")
    _identifier(item["source_commit"], "run.source_commit", 40)
    for name in (
        "install_tree_sha256",
        "runtime_fingerprint_sha256",
        "raw_evidence_sha256",
        "summary_sha256",
    ):
        _identifier(item[name], f"run.{name}", 64)
    for name in ("source_commit", "install_tree_sha256", "runtime_fingerprint_sha256"):
        if item[name] != provenance[name]:
            raise ValueError(f"run {name} does not match fixed batch provenance")
    for name in (
        "peak_global_max_single_contact_force_n",
        "force_time_exposure_n_s",
        "shadow_excess_force_time_exposure_n_s",
        "maximum_left_fingertip_compression_m",
        "maximum_right_fingertip_compression_m",
    ):
        _nonnegative(item[name], name)
    _vector3(item["net_contact_impulse_vector_n_s"], "net_contact_impulse_vector_n_s")
    windows = item["sustained_overpressure_windows"]
    if not isinstance(windows, list):
        raise ValueError("sustained_overpressure_windows must be a list")
    waypoints = item["waypoints"]
    if not isinstance(waypoints, list) or len(waypoints) != 5:
        raise ValueError("each run must contain five waypoint repeated measures")
    for waypoint_index, waypoint in enumerate(waypoints, start=1):
        _validate_waypoint_diagnostic(waypoint, waypoint_index)
    return run_id


def validate_dynamic_diagnostic_proposal(value: object) -> dict[str, object]:
    """Validate a schema-v4 proposal that can never become a runtime threshold policy."""

    document = _mapping(value, "diagnostic proposal")
    _exact_keys(document, _DIAGNOSTIC_PROPOSAL_KEYS, "diagnostic proposal")
    if document["schema_version"] != 4:
        raise ValueError("diagnostic proposal schema_version must be 4")
    if document["proposal_kind"] != "phase_aware_dynamic_transport_diagnostic":
        raise ValueError("unsupported diagnostic proposal_kind")
    if document["policy_id"] != "light_cup_wall_pick-contact":
        raise ValueError("unsupported policy_id")
    if document["acceptance_role"] != "diagnostic_only":
        raise ValueError("schema-v4 acceptance_role must be diagnostic_only")
    if document["independent_experiment_units"] != 5:
        raise ValueError("schema-v4 requires exactly five independent experiment units")

    statistical = _mapping(document["statistical_design"], "statistical_design")
    _exact_keys(
        statistical,
        frozenset({"runs_1_to_4", "run_5", "waypoint_role", "fits_dynamic_threshold"}),
        "statistical_design",
    )
    if statistical != {
        "runs_1_to_4": "descriptive_repeats",
        "run_5": "preregistered_replication",
        "waypoint_role": "repeated_measure",
        "fits_dynamic_threshold": False,
    }:
        raise ValueError("schema-v4 statistical design is invalid")

    static = _mapping(document["static_contact_contract"], "static_contact_contract")
    _exact_keys(
        static,
        frozenset({"phase", "metric", "comparison", "maximum_safe_force_n", "role"}),
        "static_contact_contract",
    )
    if static != {
        "phase": "PRE_TRANSPORT_STATIC_HOLD",
        "metric": "maximum_normal_force_n",
        "comparison": ">",
        "maximum_safe_force_n": 1.1579004532160448,
        "role": "formal_hard_gate",
    }:
        raise ValueError("static contact contract changed")

    dynamic = _mapping(document["dynamic_transport_contract"], "dynamic_transport_contract")
    _exact_keys(
        dynamic,
        frozenset(
            {
                "phase",
                "shadow_metric",
                "static_shadow_threshold_n",
                "static_threshold_role",
                "hazard_metric",
                "diagnostic_hard_stop_n",
                "hazard_comparison",
                "diagnostic_hard_stop_role",
                "maximum_reaction_steps",
                "maximum_reaction_time_s",
                "reaction_bound_kind",
            }
        ),
        "dynamic_transport_contract",
    )
    expected_dynamic = {
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
    }
    if dynamic != expected_dynamic:
        raise ValueError("dynamic diagnostic contract changed")

    if document["metric_definitions"] != _METRIC_DEFINITIONS:
        raise ValueError("metric definitions are incomplete or changed")
    provenance = _mapping(document["provenance"], "provenance")
    _exact_keys(provenance, _DIAGNOSTIC_PROVENANCE_KEYS, "provenance")
    for name in ("source_commit", "dependency_commit"):
        _identifier(provenance[name], f"provenance.{name}", 40)
    for name in _DIAGNOSTIC_PROVENANCE_KEYS - {"source_commit", "dependency_commit"}:
        _identifier(provenance[name], f"provenance.{name}", 64)

    frozen = _mapping(document["frozen_behavior"], "frozen_behavior")
    _exact_keys(frozen, _FROZEN_BEHAVIOR_KEYS, "frozen_behavior")
    for name in _FROZEN_BEHAVIOR_KEYS - {"protected_gazebo_tree_oid"}:
        _identifier(frozen[name], f"frozen_behavior.{name}", 64)
    _identifier(
        frozen["protected_gazebo_tree_oid"],
        "frozen_behavior.protected_gazebo_tree_oid",
        40,
    )

    runs = document["runs"]
    if not isinstance(runs, list) or len(runs) != 5:
        raise ValueError("schema-v4 requires exactly five independent runs")
    run_ids = [
        _validate_dynamic_run(item, index=index, provenance=provenance)
        for index, item in enumerate(runs, start=1)
    ]
    if len(set(run_ids)) != 5:
        raise ValueError("schema-v4 requires a unique run_id for every run")

    descriptive = _mapping(document["descriptive_results"], "descriptive_results")
    _exact_keys(
        descriptive,
        frozenset(
            {
                "run_count",
                "peak_force_range_n",
                "force_time_exposure_range_n_s",
                "shadow_excess_exposure_range_n_s",
                "maximum_left_fingertip_compression_m",
                "maximum_right_fingertip_compression_m",
            }
        ),
        "descriptive_results",
    )
    if descriptive["run_count"] != 5:
        raise ValueError("descriptive_results must contain exactly five runs")
    for name in (
        "peak_force_range_n",
        "force_time_exposure_range_n_s",
        "shadow_excess_exposure_range_n_s",
    ):
        bounds = descriptive[name]
        if not isinstance(bounds, list) or len(bounds) != 2:
            raise ValueError(f"{name} must contain minimum and maximum")
        low, high = (_nonnegative(item, name) for item in bounds)
        if high < low:
            raise ValueError(f"{name} is reversed")
    _nonnegative(
        descriptive["maximum_left_fingertip_compression_m"],
        "maximum_left_fingertip_compression_m",
    )
    _nonnegative(
        descriptive["maximum_right_fingertip_compression_m"],
        "maximum_right_fingertip_compression_m",
    )

    approval = _approval(document)
    if (
        approval["enabled"] is not False
        or approval["approved"] is not False
        or approval["approved_by"] is not None
        or approval["approved_at"] is not None
    ):
        raise ValueError("schema-v4 diagnostic proposal must remain disabled and unapproved")
    stored_hash = _identifier(approval["proposal_sha256"], "proposal_sha256", 64)
    if stored_hash != proposal_sha256(document):
        raise ValueError("proposal hash mismatch")
    return copy.deepcopy(dict(document))


def dynamic_metric_definitions() -> dict[str, str]:
    return dict(_METRIC_DEFINITIONS)


def _fingerprint(document: Mapping[str, Any]) -> ContactPolicyFingerprint:
    source = _mapping(document.get("fingerprint"), "fingerprint")
    _exact_keys(source, _FINGERPRINT_KEYS, "fingerprint")
    _identifier(source["source_commit"], "fingerprint.source_commit", 40)
    return ContactPolicyFingerprint(
        dependency_commit=_identifier(
            source["dependency_commit"], "fingerprint.dependency_commit", 40
        ),
        model_sha256=_identifier(source["model_sha256"], "fingerprint.model_sha256", 64),
        scene_sha256=_identifier(source["scene_sha256"], "fingerprint.scene_sha256", 64),
        motion_policy_sha256=_identifier(
            source["motion_policy_sha256"], "fingerprint.motion_policy_sha256", 64
        ),
        source_evidence_sha256=_identifier(
            source["source_evidence_sha256"],
            "fingerprint.source_evidence_sha256",
            64,
        ),
    )


def _thresholds(document: Mapping[str, Any]) -> ContactThresholds:
    source = _mapping(document.get("thresholds"), "thresholds")
    _exact_keys(source, _THRESHOLD_KEYS, "thresholds")
    result = ContactThresholds(
        minimum_bilateral_force_n=_positive(
            source["minimum_bilateral_force_n"], "minimum_bilateral_force_n"
        ),
        maximum_compression_distance_m=_positive(
            source["maximum_compression_distance_m"],
            "maximum_compression_distance_m",
        ),
        maximum_safe_force_n=_positive(source["maximum_safe_force_n"], "maximum_safe_force_n"),
        maximum_hold_linear_speed_m_s=_positive(
            source["maximum_hold_linear_speed_m_s"],
            "maximum_hold_linear_speed_m_s",
        ),
        minimum_stable_hold_duration_s=_positive(
            source["minimum_stable_hold_duration_s"],
            "minimum_stable_hold_duration_s",
        ),
    )
    if result.minimum_bilateral_force_n >= result.maximum_safe_force_n:
        raise ValueError("minimum_bilateral_force_n must be below maximum_safe_force_n")
    return result


def _evaluation(document: Mapping[str, Any]) -> ContactEvaluationPolicy:
    source = _mapping(document.get("evaluation"), "evaluation")
    _exact_keys(source, _EVALUATION_KEYS, "evaluation")
    return ContactEvaluationPolicy(
        maximum_observation_age_s=_positive(
            source["maximum_observation_age_s"], "maximum_observation_age_s"
        ),
        minimum_consecutive_samples=_positive_integer(
            source["minimum_consecutive_samples"], "minimum_consecutive_samples"
        ),
    )


def _allowed_bodies(document: Mapping[str, Any]) -> frozenset[str]:
    source = document.get("allowed_other_contact_bodies")
    if not isinstance(source, list):
        raise ValueError("allowed_other_contact_bodies must be a list")
    converted = tuple(
        _nonempty_string(item, f"allowed_other_contact_bodies[{index}]")
        for index, item in enumerate(source)
    )
    if len(set(converted)) != len(converted):
        raise ValueError("allowed_other_contact_bodies must not contain duplicates")
    return frozenset(converted)


def _approval(document: Mapping[str, Any]) -> Mapping[str, Any]:
    source = _mapping(document.get("approval"), "approval")
    _exact_keys(source, _APPROVAL_KEYS, "approval")
    return source


def _validate_proposal_content(
    document: Mapping[str, Any],
) -> tuple[
    ContactPolicyFingerprint,
    ContactThresholds,
    ContactEvaluationPolicy,
    frozenset[str],
]:
    schema_version = document.get("schema_version")
    if schema_version not in {2, 3}:
        raise ValueError("contact policy schema_version must be 2 or 3")
    _nonempty_string(document.get("policy_id"), "policy_id")
    if document.get("calibration_status") != "VALID":
        raise ValueError("approved contact policy requires calibration_status VALID")
    if schema_version == 3:
        validate_unilateral_rejection_contracts(document.get("unilateral_rejection_contracts"))
    return (
        _fingerprint(document),
        _thresholds(document),
        _evaluation(document),
        _allowed_bodies(document),
    )


def approve_proposal(document: Mapping[str, object], approval: ApprovalRecord) -> dict[str, object]:
    """Activate an immutable proposal only for the explicitly supplied hash."""

    source = _mapping(document, "proposal")
    envelope = _approval(source)
    if envelope["enabled"] is not False or envelope["approved"] is not False:
        raise ValueError("proposal is already approved or enabled")
    if envelope["approved_by"] is not None or envelope["approved_at"] is not None:
        raise ValueError("disabled proposal must not contain approval identity")
    stored_hash = _identifier(envelope["proposal_sha256"], "proposal_sha256", 64)
    supplied_hash = _identifier(approval.proposal_sha256, "proposal_sha256", 64)
    computed_hash = proposal_sha256(source)
    if supplied_hash != computed_hash or stored_hash != computed_hash:
        raise ValueError("proposal hash mismatch")
    _validate_proposal_content(source)
    approved_by = _nonempty_string(approval.approved_by, "approved_by")
    approved_at = _timestamp(approval.approved_at)

    activated = copy.deepcopy(dict(source))
    activated["approval"] = {
        "enabled": True,
        "approved": True,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "proposal_sha256": computed_hash,
    }
    return activated


def load_approved_contact_policy(
    path: Path,
    expected_fingerprint: ContactPolicyFingerprint,
) -> ApprovedContactPolicy:
    """Load an active policy and reject any approval or artifact drift."""

    document = _mapping(yaml.safe_load(path.read_bytes()), "contact policy")
    envelope = _approval(document)
    if envelope["enabled"] is not True or envelope["approved"] is not True:
        raise ValueError("contact policy is not approved and enabled")
    stored_hash = _identifier(envelope["proposal_sha256"], "proposal_sha256", 64)
    if stored_hash != proposal_sha256(document):
        raise ValueError("proposal hash mismatch")
    actual_fingerprint, thresholds, evaluation, allowed_bodies = _validate_proposal_content(
        document
    )
    if actual_fingerprint != expected_fingerprint:
        raise ValueError("contact policy fingerprint mismatch")
    approval = ApprovalRecord(
        proposal_sha256=stored_hash,
        approved_by=_nonempty_string(envelope["approved_by"], "approved_by"),
        approved_at=_timestamp(envelope["approved_at"]),
    )
    return ApprovedContactPolicy(
        policy_id=_nonempty_string(document["policy_id"], "policy_id"),
        thresholds=thresholds,
        evaluation=evaluation,
        allowed_other_contact_bodies=allowed_bodies,
        fingerprint=actual_fingerprint,
        approval=approval,
    )
