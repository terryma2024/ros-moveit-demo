"""Canonical ACT contact policy payloads and separate activation receipts.

The disabled proposal envelope and activation receipt are never part of the
policy fingerprint.  Callers must verify both before enabling live motion.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any

_PAYLOAD_KEYS = frozenset(
    {
        "schema_version", "policy_id", "thresholds", "evaluation",
        "allowed_other_contact_bodies", "mujoco_version", "model_sha256",
        "scene_sha256", "motion_policy_sha256", "source_evidence_sha256",
        "collector_sha256", "live_collector_sha256", "analyzer_sha256", "config_sha256",
    }
)
_THRESHOLD_KEYS = frozenset(
    {
        "minimum_bilateral_force_n", "maximum_compression_distance_m",
        "maximum_safe_force_n", "maximum_hold_linear_speed_m_s",
        "minimum_stable_hold_duration_s",
    }
)
_EVALUATION_KEYS = frozenset(
    {"maximum_observation_age_s", "minimum_consecutive_samples"}
)
_RECEIPT_KEYS = frozenset(
    {
        "policy_fingerprint", "source_evidence_sha256", "approved_by",
        "approval_reference", "approved_at", "evidence_root",
    }
)
_HEX64 = re.compile(r"[0-9a-f]{64}\Z")
#: a receipt that re-binds an approved calibration to another scene and model whose stripped physics fingerprint is the same
#: (`contact_derivation.py`): it names how it was derived and cites the old receipt, the equivalence record and the fingerprint
DERIVED_BY = "stripped_physics_fingerprint_equivalence"
_DERIVED_KEYS = frozenset({"derived_by", "old_receipt_sha256", "equivalence_record_sha256", "stripped_fingerprint_sha256"})

#: The user's recorded rule deviation: fit offline, validate with Teacher spot-checks instead of the live cohort.
VALIDATION_OFFLINE_SPOT_CHECK = "offline_fit_teacher_spot_check"
VALIDATION_DECISION = "owner_deviation_offline_cohort"
VALIDATION_MODES = (VALIDATION_OFFLINE_SPOT_CHECK,)
#: A receipt kind that may only be used by a preselected_target_diagnostic freeze (never by default, never installed).
SPOT_CHECK_CANDIDATE = "spot_check_candidate"
SPOT_CHECK_FREEZE_MODE = "preselected_target_diagnostic"
_CANDIDATE_APPROVER = re.compile(r"(plan|agent):[A-Za-z0-9_.:/-][A-Za-z0-9_.:/ -]*\Z")


def validation_descriptor_sha256(mode: str = VALIDATION_OFFLINE_SPOT_CHECK) -> str:
    """The value `live_collector_sha256` carries in a spot-check proposal: the mode is inside the fingerprint."""

    if mode not in VALIDATION_MODES:
        raise ValueError("unknown validation mode")
    return hashlib.sha256(json.dumps({"validation_mode": mode, "decision": VALIDATION_DECISION}, sort_keys=True,
                                     separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def spot_check_receipt_allowed(frozen_mode) -> bool:
    """Only a frozen preselected_target_diagnostic input set may carry a spot_check_candidate receipt."""

    return frozen_mode == SPOT_CHECK_FREEZE_MODE


def _exact(value: Any, fields: frozenset[str], name: str) -> dict[str, Any]:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{name} has missing or unknown fields")
    return value


def _nonempty(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{name} must be a nonempty trimmed string")
    return value


def _sha(value: Any, name: str) -> str:
    if not isinstance(value, str) or not _HEX64.fullmatch(value) or set(value) == {"0"}:
        raise ValueError(f"{name} must be a real lowercase SHA-256")
    return value


def _positive(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite and positive")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError(f"{name} must be finite and positive")
    return number


def canonical_policy_payload(payload: dict[str, Any]) -> bytes:
    """Validate a closed runtime payload and return its unique UTF-8 encoding."""

    item = _exact(payload, _PAYLOAD_KEYS, "ACT contact payload")
    if type(item["schema_version"]) is not int or item["schema_version"] != 1:
        raise ValueError("unsupported ACT contact policy schema")
    _nonempty(item["policy_id"], "policy_id")
    _nonempty(item["mujoco_version"], "mujoco_version")
    for field in (
        "model_sha256", "scene_sha256", "motion_policy_sha256",
        "source_evidence_sha256", "collector_sha256", "live_collector_sha256", "analyzer_sha256",
        "config_sha256",
    ):
        _sha(item[field], field)

    thresholds = _exact(item["thresholds"], _THRESHOLD_KEYS, "thresholds")
    for field in _THRESHOLD_KEYS:
        _positive(thresholds[field], field)
    if thresholds["minimum_bilateral_force_n"] >= thresholds["maximum_safe_force_n"]:
        raise ValueError("bilateral minimum must be below the safe force ceiling")

    evaluation = _exact(item["evaluation"], _EVALUATION_KEYS, "evaluation")
    _positive(evaluation["maximum_observation_age_s"], "maximum_observation_age_s")
    count = evaluation["minimum_consecutive_samples"]
    if type(count) is not int or count < 1:
        raise ValueError("minimum_consecutive_samples must be a positive integer")

    bodies = item["allowed_other_contact_bodies"]
    if not isinstance(bodies, list) or any(
        not isinstance(body, str) or not body.strip() or body != body.strip()
        for body in bodies
    ) or bodies != sorted(set(bodies)):
        raise ValueError("allowed_other_contact_bodies must be sorted and unique")
    return json.dumps(
        item, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def policy_fingerprint(payload: dict[str, Any]) -> str:
    """SHA-256 of the canonical runtime payload, never of the proposal envelope."""

    return hashlib.sha256(canonical_policy_payload(payload)).hexdigest()


def verify_activation(
    payload: dict[str, Any],
    receipt: dict[str, Any],
    *,
    expected_model_sha256: str | None = None,
    expected_scene_sha256: str | None = None,
    expected_mujoco_version: str | None = None,
    allow_spot_check_candidate: bool = False,
) -> None:
    """Fail closed unless a distinct receipt approves this exact applicable payload.

    A receipt of kind `spot_check_candidate` is refused unless the caller opts in (only a frozen
    preselected_target_diagnostic input set does); it must name a plan or agent, never the user, and apply to a payload
    bound to the offline_fit_teacher_spot_check validation mode.
    """

    try:
        fingerprint = policy_fingerprint(payload)
        keyed = isinstance(receipt, dict) and "receipt_kind" in receipt
        derived = isinstance(receipt, dict) and "derived_by" in receipt
        if keyed and derived:
            raise ValueError("a derived receipt has no kind")
        approved = _exact(receipt, _RECEIPT_KEYS | ({"receipt_kind"} if keyed else set()) | (_DERIVED_KEYS if derived else set()),
                          "activation receipt")
        if derived:
            if approved["derived_by"] != DERIVED_BY:
                raise ValueError("unknown derivation")
            for field in ("old_receipt_sha256", "equivalence_record_sha256", "stripped_fingerprint_sha256"):
                _sha(approved[field], field)
        if keyed:
            if (not allow_spot_check_candidate or approved["receipt_kind"] != SPOT_CHECK_CANDIDATE
                    or payload["live_collector_sha256"] != validation_descriptor_sha256()
                    or not isinstance(approved["approved_by"], str)
                    or _CANDIDATE_APPROVER.fullmatch(approved["approved_by"]) is None):
                raise ValueError("spot-check candidate receipt not allowed")
        if _sha(approved["policy_fingerprint"], "policy_fingerprint") != fingerprint:
            raise ValueError("fingerprint mismatch")
        if _sha(approved["source_evidence_sha256"], "source_evidence_sha256") != payload["source_evidence_sha256"]:
            raise ValueError("evidence mismatch")
        _nonempty(approved["approved_by"], "approved_by")
        _nonempty(approved["approval_reference"], "approval_reference")
        approved_at = _nonempty(approved["approved_at"], "approved_at")
        parsed = datetime.fromisoformat(approved_at)
        if "T" not in approved_at or parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("approval timestamp needs timezone")
        evidence_root = Path(_nonempty(approved["evidence_root"], "evidence_root"))
        if not evidence_root.is_absolute() or ".." in evidence_root.parts:
            raise ValueError("evidence root must be absolute")
        for expected, field in (
            (expected_model_sha256, "model_sha256"),
            (expected_scene_sha256, "scene_sha256"),
            (expected_mujoco_version, "mujoco_version"),
        ):
            if expected is not None and payload[field] != expected:
                raise ValueError(f"{field} mismatch")
    except (TypeError, KeyError, ValueError) as error:
        raise ValueError("POLICY_NOT_ACTIVATED") from error
