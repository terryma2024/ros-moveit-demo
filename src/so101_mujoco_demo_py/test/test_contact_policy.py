from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from so101_mujoco_demo_py.contact_policy import (
    ApprovalRecord,
    ContactPolicyFingerprint,
    approve_proposal,
    load_approved_contact_policy,
    proposal_sha256,
)


def fingerprint() -> ContactPolicyFingerprint:
    return ContactPolicyFingerprint(
        dependency_commit="2" * 40,
        model_sha256="a" * 64,
        scene_sha256="b" * 64,
        motion_policy_sha256="c" * 64,
        source_evidence_sha256="d" * 64,
    )


def valid_disabled_proposal() -> dict[str, object]:
    document: dict[str, object] = {
        "schema_version": 2,
        "policy_id": "light_cup_wall_pick-contact",
        "calibration_status": "VALID",
        "fingerprint": {
            "source_commit": "1" * 40,
            "dependency_commit": "2" * 40,
            "model_sha256": "a" * 64,
            "scene_sha256": "b" * 64,
            "motion_policy_sha256": "c" * 64,
            "source_evidence_sha256": "d" * 64,
        },
        "evaluation": {
            "maximum_observation_age_s": 0.10,
            "minimum_consecutive_samples": 5,
        },
        "allowed_other_contact_bodies": ["table"],
        "thresholds": {
            "minimum_bilateral_force_n": 0.50,
            "maximum_compression_distance_m": 0.0015,
            "maximum_safe_force_n": 5.0,
            "maximum_hold_linear_speed_m_s": 0.01,
            "minimum_stable_hold_duration_s": 0.30,
        },
        "approval": {
            "enabled": False,
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "proposal_sha256": None,
        },
    }
    document["approval"]["proposal_sha256"] = proposal_sha256(document)  # type: ignore[index]
    return document


def approved_document() -> dict[str, object]:
    proposal = valid_disabled_proposal()
    proposal_hash = proposal["approval"]["proposal_sha256"]  # type: ignore[index]
    return approve_proposal(
        proposal,
        ApprovalRecord(
            proposal_sha256=proposal_hash,  # type: ignore[arg-type]
            approved_by="user",
            approved_at="2026-08-12T12:00:00+08:00",
        ),
    )


def write_policy(tmp_path: Path, document: dict[str, object]) -> Path:
    path = tmp_path / "contact-policy.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def test_proposal_hash_excludes_only_approval_envelope() -> None:
    proposal = valid_disabled_proposal()
    first = proposal_sha256(proposal)

    proposal["approval"] = {
        "enabled": True,
        "approved": True,
        "approved_by": "user",
        "approved_at": "2026-08-12T12:00:00+08:00",
        "proposal_sha256": first,
    }

    assert proposal_sha256(proposal) == first
    proposal["thresholds"]["minimum_bilateral_force_n"] = 0.51  # type: ignore[index]
    assert proposal_sha256(proposal) != first


def test_approval_activates_an_exact_hash_without_mutating_proposal() -> None:
    proposal = valid_disabled_proposal()
    proposal_hash = proposal["approval"]["proposal_sha256"]  # type: ignore[index]

    approved = approve_proposal(
        proposal,
        ApprovalRecord(proposal_hash, "user", "2026-08-12T12:00:00+08:00"),  # type: ignore[arg-type]
    )

    assert proposal["approval"]["enabled"] is False  # type: ignore[index]
    assert approved["approval"] == {
        "enabled": True,
        "approved": True,
        "approved_by": "user",
        "approved_at": "2026-08-12T12:00:00+08:00",
        "proposal_sha256": proposal_hash,
    }
    assert proposal_sha256(approved) == proposal_hash


def test_approval_requires_exact_hash_and_timezone() -> None:
    proposal = valid_disabled_proposal()

    with pytest.raises(ValueError, match="proposal hash mismatch"):
        approve_proposal(
            proposal,
            ApprovalRecord("e" * 64, "user", "2026-08-12T12:00:00+08:00"),
        )
    with pytest.raises(ValueError, match="timezone"):
        approve_proposal(
            proposal,
            ApprovalRecord(
                proposal["approval"]["proposal_sha256"],  # type: ignore[index,arg-type]
                "user",
                "2026-08-12T12:00:00",
            ),
        )


def test_loads_only_active_hash_bound_policy(tmp_path: Path) -> None:
    policy = load_approved_contact_policy(
        write_policy(tmp_path, approved_document()), fingerprint()
    )

    assert policy.policy_id == "light_cup_wall_pick-contact"
    assert policy.thresholds.minimum_bilateral_force_n == 0.50
    assert policy.evaluation.minimum_consecutive_samples == 5
    assert policy.allowed_other_contact_bodies == frozenset({"table"})
    assert policy.fingerprint == fingerprint()
    assert policy.approval.approved_by == "user"


def test_rejects_disabled_or_modified_policy(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="not approved and enabled"):
        load_approved_contact_policy(
            write_policy(tmp_path, valid_disabled_proposal()),
            fingerprint(),
        )

    modified = approved_document()
    modified["thresholds"]["maximum_safe_force_n"] = 5.1  # type: ignore[index]
    with pytest.raises(ValueError, match="proposal hash mismatch"):
        load_approved_contact_policy(write_policy(tmp_path, modified), fingerprint())


@pytest.mark.parametrize(
    ("mutation", "message"),
    (
        (
            lambda item: item["fingerprint"].update(source_evidence_sha256="0" * 64),
            "placeholder",
        ),
        (
            lambda item: item["thresholds"].update(minimum_bilateral_force_n=5.0),
            "below maximum_safe_force_n",
        ),
        (
            lambda item: item["evaluation"].update(minimum_consecutive_samples=0),
            "positive integer",
        ),
        (
            lambda item: item.update(allowed_other_contact_bodies=[""]),
            "non-empty",
        ),
    ),
)
def test_rejects_unsafe_approved_policy_fields(tmp_path: Path, mutation, message: str) -> None:
    document = approved_document()
    mutation(document)
    document["approval"]["proposal_sha256"] = proposal_sha256(document)  # type: ignore[index]

    with pytest.raises(ValueError, match=message):
        load_approved_contact_policy(write_policy(tmp_path, document), fingerprint())


def test_rejects_changed_expected_artifact_fingerprint(tmp_path: Path) -> None:
    changed = ContactPolicyFingerprint(
        dependency_commit="2" * 40,
        model_sha256="f" * 64,
        scene_sha256="b" * 64,
        motion_policy_sha256="c" * 64,
        source_evidence_sha256="d" * 64,
    )

    with pytest.raises(ValueError, match="fingerprint mismatch"):
        load_approved_contact_policy(write_policy(tmp_path, approved_document()), changed)
