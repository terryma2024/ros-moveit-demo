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
    if document.get("schema_version") != 2:
        raise ValueError("contact policy schema_version must be 2")
    _nonempty_string(document.get("policy_id"), "policy_id")
    if document.get("calibration_status") != "VALID":
        raise ValueError("approved contact policy requires calibration_status VALID")
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
