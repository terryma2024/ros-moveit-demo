"""A proposal fingerprint is the payload hash, with a separate activation receipt."""

import copy
import hashlib
import json

import pytest

from so101_demo.act.contact_policy import (
    canonical_policy_payload,
    policy_fingerprint,
    verify_activation,
)


def _payload():
    return {
        "schema_version": 1,
        "policy_id": "so101-act-contact",
        "thresholds": {
            "minimum_bilateral_force_n": 0.1,
            "maximum_compression_distance_m": 0.002,
            "maximum_safe_force_n": 3.0,
            "maximum_hold_linear_speed_m_s": 0.02,
            "minimum_stable_hold_duration_s": 0.2,
        },
        "evaluation": {"maximum_observation_age_s": 0.1, "minimum_consecutive_samples": 3},
        "allowed_other_contact_bodies": ["table_collision"],
        "mujoco_version": "3.4.0",
        "model_sha256": "a" * 64,
        "scene_sha256": "b" * 64,
        "motion_policy_sha256": "c" * 64,
        "source_evidence_sha256": "d" * 64,
        "collector_sha256": "e" * 64,
        "live_collector_sha256": "1" * 64,
        "analyzer_sha256": "f" * 64,
        "config_sha256": "1" * 64,
    }


def _receipt(payload):
    return {
        "policy_fingerprint": policy_fingerprint(payload),
        "source_evidence_sha256": payload["source_evidence_sha256"],
        "approved_by": "user",
        "approval_reference": "dispatch-30a80149",
        "approved_at": "2026-09-25T00:00:00+00:00",
        "evidence_root": "/data/work/so101-evidence/act-data/20260924-fbc25063-resume",
    }


def test_fingerprint_is_exact_canonical_payload_hash():
    payload = _payload()
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    assert canonical_policy_payload(payload) == encoded
    assert policy_fingerprint(payload) == hashlib.sha256(encoded).hexdigest()
    assert policy_fingerprint({**payload, "model_sha256": "2" * 64}) != policy_fingerprint(payload)


def test_activation_accepts_only_exact_payload_fingerprint():
    payload = _payload()
    verify_activation(payload, _receipt(payload))
    for field, replacement in (
        ("policy_fingerprint", "2" * 64),
        ("source_evidence_sha256", "2" * 64),
        ("approved_by", ""),
        ("evidence_root", ""),
    ):
        receipt = _receipt(payload)
        receipt[field] = replacement
        with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
            verify_activation(payload, receipt)


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: p.update(extra="unsigned"),
        lambda p: p["thresholds"].update(extra=1),
        lambda p: p["thresholds"].update(maximum_safe_force_n=float("nan")),
        lambda p: p["evaluation"].update(minimum_consecutive_samples=True),
        lambda p: p.update(model_sha256="0" * 64),
    ],
)
def test_payload_rejects_unknown_or_noncanonical_fields(edit):
    payload = copy.deepcopy(_payload())
    edit(payload)
    with pytest.raises(ValueError):
        canonical_policy_payload(payload)


def test_receipt_schema_and_timestamp_are_closed():
    payload = _payload()
    for edit in (
        lambda r: r.update(extra="unsigned"),
        lambda r: r.update(approved_at="2026-09-25"),
        lambda r: r.update(approval_reference=""),
    ):
        receipt = _receipt(payload)
        edit(receipt)
        with pytest.raises(ValueError, match="POLICY_NOT_ACTIVATED"):
            verify_activation(payload, receipt)
