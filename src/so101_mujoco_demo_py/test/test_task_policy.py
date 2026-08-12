import hashlib
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml

from so101_mujoco_demo_py.contact_policy import (
    ApprovalRecord,
    ContactPolicyFingerprint,
    approve_proposal,
    proposal_sha256,
)
from so101_mujoco_demo_py.task_policy import load_task_policy

MOTION_POLICY = (
    Path(__file__).parents[1] / "config" / "motion_policies" / "light_cup_wall_pick.yaml"
)

EXPECTED_STATES = {
    "MOVE_ABOVE_OBJECT",
    "DESCEND",
    "LIFT",
    "MOVE_ABOVE_PLACE",
    "DESCEND_TO_PLACE",
    "RETREAT",
    "RECOVER_LIFT_TO_SAFE_HEIGHT",
    "RECOVER_MOVE_ABOVE_PICK",
    "RECOVER_DESCEND_TO_PICK",
    "RECOVER_RETREAT",
}


def write_candidate(tmp_path: Path, change) -> Path:
    document = yaml.safe_load(MOTION_POLICY.read_text(encoding="utf-8"))
    change(document)
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return candidate


def write_approved_contact_policy(tmp_path: Path) -> tuple[Path, ContactPolicyFingerprint]:
    fingerprint = ContactPolicyFingerprint(
        dependency_commit="2" * 40,
        model_sha256="a" * 64,
        scene_sha256="b" * 64,
        motion_policy_sha256=hashlib.sha256(MOTION_POLICY.read_bytes()).hexdigest(),
        source_evidence_sha256="d" * 64,
    )
    document: dict[str, object] = {
        "schema_version": 2,
        "policy_id": "light_cup_wall_pick-contact",
        "calibration_status": "VALID",
        "fingerprint": {
            "source_commit": "1" * 40,
            "dependency_commit": fingerprint.dependency_commit,
            "model_sha256": fingerprint.model_sha256,
            "scene_sha256": fingerprint.scene_sha256,
            "motion_policy_sha256": fingerprint.motion_policy_sha256,
            "source_evidence_sha256": fingerprint.source_evidence_sha256,
        },
        "evaluation": {
            "maximum_observation_age_s": 0.1,
            "minimum_consecutive_samples": 5,
        },
        "allowed_other_contact_bodies": ["table"],
        "thresholds": {
            "minimum_bilateral_force_n": 0.5,
            "maximum_compression_distance_m": 0.0015,
            "maximum_safe_force_n": 5.0,
            "maximum_hold_linear_speed_m_s": 0.01,
            "minimum_stable_hold_duration_s": 0.3,
        },
        "approval": {
            "enabled": False,
            "approved": False,
            "approved_by": None,
            "approved_at": None,
            "proposal_sha256": None,
        },
    }
    proposal_hash = proposal_sha256(document)
    document["approval"]["proposal_sha256"] = proposal_hash  # type: ignore[index]
    approved = approve_proposal(
        document,
        ApprovalRecord(proposal_hash, "user", "2026-08-12T12:00:00+08:00"),
    )
    path = tmp_path / "approved-contact.yaml"
    path.write_text(yaml.safe_dump(approved, sort_keys=False), encoding="utf-8")
    return path, fingerprint


def test_loads_single_source_motion_and_final_outcome_policy() -> None:
    policy = load_task_policy(MOTION_POLICY)

    assert policy.policy_id == "light_cup_wall_pick"
    assert policy.object_id == "plastic_cup"
    assert policy.gripper.grasp_close_q6 == -0.047608632840292
    assert policy.states["MOVE_ABOVE_PLACE"].velocity_scaling == 0.10
    assert policy.physical_outcome.final_target_min_xy_m == (-0.090, -0.260)
    assert policy.physical_outcome.final_target_max_xy_m == (-0.070, -0.240)
    assert policy.maximum_diagnostic_force_n == 11.60
    assert set(policy.states) == EXPECTED_STATES
    assert (
        policy.fingerprint.motion_policy_sha256
        == hashlib.sha256(MOTION_POLICY.read_bytes()).hexdigest()
    )
    assert policy.fingerprint.contact_policy_sha256 is None


def test_returns_immutable_policy_values() -> None:
    policy = load_task_policy(MOTION_POLICY)

    with pytest.raises(TypeError):
        policy.states["UNREVIEWED"] = policy.states["LIFT"]  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        policy.gripper.release_q6 = 0.0  # type: ignore[misc]
    assert isinstance(policy.states["LIFT"].waypoints, tuple)
    assert isinstance(policy.states["LIFT"].waypoints[0], tuple)


def test_rejects_unknown_root_key(tmp_path: Path) -> None:
    candidate = write_candidate(tmp_path, lambda document: document.update(unreviewed=True))

    with pytest.raises(ValueError, match="unknown task policy keys: unreviewed"):
        load_task_policy(candidate)


def test_rejects_non_five_joint_motion_vector(tmp_path: Path) -> None:
    def change(document: dict[str, object]) -> None:
        document["states"]["LIFT"]["waypoints"][0] = [0.0] * 4  # type: ignore[index]

    candidate = write_candidate(tmp_path, change)

    with pytest.raises(ValueError, match=r"LIFT.waypoints\[0\].*five arm joints"):
        load_task_policy(candidate)


def test_rejects_nonfinite_scaling(tmp_path: Path) -> None:
    def change(document: dict[str, object]) -> None:
        document["states"]["LIFT"]["velocity_scaling"] = float("nan")  # type: ignore[index]

    candidate = write_candidate(tmp_path, change)

    with pytest.raises(ValueError, match="LIFT.velocity_scaling.*finite"):
        load_task_policy(candidate)


@pytest.mark.parametrize(
    ("keys", "value", "message"),
    (
        (("states", "RETREAT", "acceleration_scaling"), 1.01, "must not exceed 1.0"),
        (("physical_outcome", "consecutive_samples"), 0, "positive integer"),
        (("physical_outcome", "settle_timeout_s"), 0.0, "must be positive"),
    ),
)
def test_rejects_nonpositive_counts_durations_and_excess_scaling(
    tmp_path: Path,
    keys: tuple[str, ...],
    value: object,
    message: str,
) -> None:
    def change(document: dict[str, object]) -> None:
        target = document
        for key in keys[:-1]:
            target = target[key]  # type: ignore[assignment]
        target[keys[-1]] = value

    candidate = write_candidate(tmp_path, change)

    with pytest.raises(ValueError, match=message):
        load_task_policy(candidate)


def test_rejects_reversed_final_target_bounds(tmp_path: Path) -> None:
    def change(document: dict[str, object]) -> None:
        document["physical_outcome"]["final_target_region"]["min_xy_m"] = [  # type: ignore[index]
            -0.060,
            -0.260,
        ]

    candidate = write_candidate(tmp_path, change)

    with pytest.raises(ValueError, match="final_target_region.*ordered"):
        load_task_policy(candidate)


def test_rejects_unknown_planning_shadow_key(tmp_path: Path) -> None:
    def change(document: dict[str, object]) -> None:
        document["physical_outcome"]["planning_shadow"]["unreviewed"] = 1  # type: ignore[index]

    candidate = write_candidate(tmp_path, change)

    with pytest.raises(ValueError, match="unknown planning_shadow keys: unreviewed"):
        load_task_policy(candidate)


def test_loads_approved_contact_policy_into_one_task_boundary(tmp_path: Path) -> None:
    contact_path, expected = write_approved_contact_policy(tmp_path)

    policy = load_task_policy(
        MOTION_POLICY,
        contact_path,
        expected,
        require_approved_contact=True,
    )

    assert policy.contact is not None
    assert policy.contact.thresholds.maximum_safe_force_n == 5.0
    assert (
        policy.fingerprint.contact_policy_sha256
        == hashlib.sha256(contact_path.read_bytes()).hexdigest()
    )


def test_required_contact_policy_fails_closed_before_loading_motion_only() -> None:
    with pytest.raises(ValueError, match="approved contact policy is required"):
        load_task_policy(MOTION_POLICY, require_approved_contact=True)


def test_rejects_contact_policy_bound_to_different_motion_bytes(tmp_path: Path) -> None:
    contact_path, expected = write_approved_contact_policy(tmp_path)
    changed = ContactPolicyFingerprint(
        dependency_commit=expected.dependency_commit,
        model_sha256=expected.model_sha256,
        scene_sha256=expected.scene_sha256,
        motion_policy_sha256="e" * 64,
        source_evidence_sha256=expected.source_evidence_sha256,
    )

    with pytest.raises(ValueError, match="motion policy fingerprint mismatch"):
        load_task_policy(MOTION_POLICY, contact_path, changed, require_approved_contact=True)
