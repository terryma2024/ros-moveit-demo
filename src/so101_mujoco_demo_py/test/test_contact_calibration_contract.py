from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from so101_mujoco_demo_py.contact_policy import proposal_sha256

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE_ROOT / "config/contact_calibration.yaml"
ANALYZER = PACKAGE_ROOT / "scripts/analyze_contact_calibration.py"
PHYSICAL_REGIMES = {
    "no_contact",
    "bilateral_touch",
    "over_compression",
    "micro_lift_slip",
    "stable_hold",
}
UNILATERAL_REGIMES = {"left_only", "right_only"}
CLASSIFICATION_LABELS = PHYSICAL_REGIMES | UNILATERAL_REGIMES
ORDERED_REGIMES = tuple(sorted(CLASSIFICATION_LABELS))
SOURCE_COMMIT = "1" * 40
DEPENDENCY_COMMIT = "2" * 40
MODEL_SHA256 = "a" * 64
SCENE_SHA256 = "b" * 64
MOTION_POLICY_SHA256 = "c" * 64


def load_policy() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def contact(side: str, force_n: float, distance_m: float) -> dict:
    return {
        "side": side,
        "object_body": "cup",
        "robot_geom": f"{side}_fingertip_pad",
        "signed_distance_m": distance_m,
        "normal_force_n": force_n,
    }


def complete_evidence(*, overlapping: bool = False, schema_version: int = 2) -> dict:
    profiles = {
        "no_contact": (0.0, 0.0010, 0.0005, 0.0, False, False),
        "left_only": (0.20, -0.0001, 0.0007, 0.05, True, False),
        "right_only": (0.22, -0.0001, 0.0007, 0.05, False, True),
        "bilateral_touch": (1.00, -0.0003, 0.0010, 0.10, True, True),
        "over_compression": (6.00, -0.0025, 0.0010, 0.20, True, True),
        "micro_lift_slip": (1.50, -0.0005, 0.0800, 0.30, True, True),
        "stable_hold": (2.00, -0.0007, 0.0020, 0.50, True, True),
    }
    if overlapping:
        profiles["over_compression"] = profiles["stable_hold"]
        profiles["micro_lift_slip"] = profiles["stable_hold"]
        profiles["bilateral_touch"] = profiles["stable_hold"]

    sequence = 0
    regimes: dict[str, list[dict]] = {}
    for regime in ORDERED_REGIMES:
        base_force, base_distance, base_speed, duration, has_left, has_right = profiles[regime]
        samples = []
        for sample_index in range(25):
            sequence += 1
            force_n = base_force + sample_index * 0.001
            distance_m = base_distance - sample_index * 1.0e-7
            speed_m_s = base_speed + sample_index * 1.0e-6
            left = [contact("left", force_n, distance_m)] if has_left else []
            right = [contact("right", force_n, distance_m)] if has_right else []
            sample = {
                "regime": regime,
                "subcohorts": {
                    "table_only": regime == "no_contact" and sample_index % 2 == 0,
                    "post_release": regime == "no_contact" and sample_index % 2 == 1,
                },
                "simulation_session_id": "calibration-session",
                "reset_epoch": 4,
                "publisher_sequence": sequence,
                "simulation_step": sequence * 10,
                "simulation_time_s": sequence * 0.01,
                "receipt_monotonic_s": 100.0 + sequence * 0.01,
                "object_pose_world": {
                    "position_m": [0.20, 0.0, 0.03],
                    "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
                },
                "object_twist_world": {
                    "linear_m_s": [speed_m_s, 0.0, 0.0],
                    "angular_rad_s": [0.0, 0.0, 0.0],
                },
                "left_fingertip_contacts": left,
                "right_fingertip_contacts": right,
                "other_object_contacts": [],
                "minimum_signed_distance_m": distance_m if left or right else 0.0,
                "maximum_normal_force_n": force_n if left or right else 0.0,
                "q6_rad": 0.20,
                "arm_joint_positions_rad": [0.0, -0.4, 0.8, 0.5, 0.0],
                "tcp_pose_world": {
                    "position_m": [0.20, 0.0, 0.09],
                    "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
                },
                "contact_duration_s": duration,
            }
            if schema_version == 1:
                sample.update(
                    source_commit=SOURCE_COMMIT,
                    dependency_commit=DEPENDENCY_COMMIT,
                    model_sha256=MODEL_SHA256,
                    config_sha256=MOTION_POLICY_SHA256,
                )
            samples.append(sample)
        regimes[regime] = samples

    common = {
        "schema_version": schema_version,
        "units": {
            "signed_distance": "m",
            "normal_force": "N",
            "linear_speed": "m/s",
            "joint_position": "rad",
            "simulation_time": "s",
            "receipt_time": "s",
        },
        "regimes": regimes,
    }
    if schema_version == 1:
        common.update(
            source_commit=SOURCE_COMMIT,
            dependency_commit=DEPENDENCY_COMMIT,
            model_sha256=MODEL_SHA256,
            config_sha256=MOTION_POLICY_SHA256,
        )
    else:
        common.update(
            fingerprint={
                "source_commit": SOURCE_COMMIT,
                "dependency_commit": DEPENDENCY_COMMIT,
                "model_sha256": MODEL_SHA256,
                "scene_sha256": SCENE_SHA256,
                "motion_policy_sha256": MOTION_POLICY_SHA256,
            },
            simulation_session_id="calibration-session",
            reset_epoch=4,
        )
    return common


def unilateral_contracts() -> dict:
    return {
        "left_only": {
            "stable_grasp_allowed": False,
            "expected_failure_code": "GRASP_RIGHT_CONTACT_MISSING",
            "physical_evidence": {
                "disposition": "physical_unreachable",
                "references": [
                    {"experiment_id": "EXP-062", "artifact_sha256": "6" * 64},
                    {"experiment_id": "EXP-066", "artifact_sha256": "7" * 64},
                ],
            },
            "physical_calibration_sample_count": None,
            "physical_evaluation_sample_count": None,
            "physical_misclassification_rate": None,
        },
        "right_only": {
            "stable_grasp_allowed": False,
            "expected_failure_code": "GRASP_LEFT_CONTACT_MISSING",
            "physical_evidence": {
                "disposition": "observed",
                "references": [
                    {"experiment_id": "EXP-072", "artifact_sha256": "8" * 64},
                ],
            },
            "physical_calibration_sample_count": None,
            "physical_evaluation_sample_count": None,
            "physical_misclassification_rate": None,
        },
    }


def schema_v3_evidence(*, overlapping: bool = False) -> dict:
    evidence = complete_evidence(overlapping=overlapping)
    evidence["schema_version"] = 3
    evidence["regimes"] = {name: evidence["regimes"][name] for name in sorted(PHYSICAL_REGIMES)}
    evidence["unilateral_rejection_contracts"] = unilateral_contracts()
    return evidence


def run_analyzer(tmp_path: Path, evidence: dict) -> tuple[subprocess.CompletedProcess[str], Path]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "evidence.json"
    output = tmp_path / "proposal.yaml"
    source.write_text(json.dumps(evidence), encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ANALYZER), "--input", str(source), "--output", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    return result, output


def test_checked_in_policy_is_schema_v3_planned_and_disabled() -> None:
    policy = load_policy()

    assert policy["schema_version"] == 3
    assert policy["policy_id"] == "light_cup_wall_pick-contact"
    assert policy["calibration_status"] == "PLANNED"
    assert policy["approval"] == {
        "enabled": False,
        "approved": False,
        "approved_by": None,
        "approved_at": None,
        "proposal_sha256": None,
    }
    assert policy["evaluation"] == {
        "maximum_observation_age_s": 0.10,
        "minimum_consecutive_samples": 5,
    }
    assert set(policy["regimes"]) == PHYSICAL_REGIMES
    assert set(policy["unilateral_rejection_contracts"]) == UNILATERAL_REGIMES
    assert len(policy["fingerprint"]["source_commit"]) == 40
    assert len(policy["fingerprint"]["dependency_commit"]) == 40
    for field in ("model_sha256", "scene_sha256", "motion_policy_sha256"):
        assert len(policy["fingerprint"][field]) == 64
        assert set(policy["fingerprint"][field]) != {"0"}
    assert policy["fingerprint"]["source_evidence_sha256"] is None
    assert all(value is None for value in policy["thresholds"].values())


def test_analyzer_accepts_schema_v3_five_physical_regimes_and_contracts(
    tmp_path: Path,
) -> None:
    result, output = run_analyzer(tmp_path, schema_v3_evidence())

    assert result.returncode == 0, result.stderr
    proposal = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert proposal["schema_version"] == 3
    assert proposal["source_schema_version"] == 3
    assert set(proposal["regimes"]) == PHYSICAL_REGIMES
    assert set(proposal["misclassification_matrix"]) == PHYSICAL_REGIMES
    assert all(
        set(proposal["misclassification_matrix"][actual]) == CLASSIFICATION_LABELS
        for actual in PHYSICAL_REGIMES
    )
    assert proposal["calibration_sample_count"] == 100
    assert proposal["evaluation_sample_count"] == 25
    assert proposal["false_positive_count"] == 0
    assert proposal["false_negative_count"] == 0
    assert proposal["unilateral_rejection_contracts"] == unilateral_contracts()
    for contract in proposal["unilateral_rejection_contracts"].values():
        assert contract["stable_grasp_allowed"] is False
        assert contract["physical_calibration_sample_count"] is None
        assert contract["physical_evaluation_sample_count"] is None
        assert contract["physical_misclassification_rate"] is None


@pytest.mark.parametrize("schema_version", (1, 2))
def test_analyzer_accepts_archived_v1_and_current_v2_raw_evidence(
    tmp_path: Path, schema_version: int
) -> None:
    result, output = run_analyzer(tmp_path, complete_evidence(schema_version=schema_version))

    assert result.returncode == 0, result.stderr
    proposal = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert proposal["schema_version"] == 2
    assert proposal["calibration_status"] == "VALID"
    assert proposal["approval"]["enabled"] is False
    assert proposal["approval"]["approved"] is False
    assert proposal["approval"]["proposal_sha256"] == proposal_sha256(proposal)
    assert proposal["fingerprint"]["model_sha256"] == MODEL_SHA256
    assert proposal["fingerprint"]["motion_policy_sha256"] == MOTION_POLICY_SHA256
    if schema_version == 1:
        assert proposal["fingerprint"]["scene_sha256"] == MOTION_POLICY_SHA256
        assert proposal["source_schema_version"] == 1
    else:
        assert proposal["fingerprint"]["scene_sha256"] == SCENE_SHA256
        assert proposal["source_schema_version"] == 2


def test_analyzer_reports_deterministic_quality_and_margins(tmp_path: Path) -> None:
    result, output = run_analyzer(tmp_path, complete_evidence())

    assert result.returncode == 0, result.stderr
    proposal = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert proposal["split_method"] == "per_regime_ordered_index_modulo_5"
    assert proposal["calibration_sample_count"] == 140
    assert proposal["evaluation_sample_count"] == 35
    assert proposal["false_positive_count"] == 0
    assert proposal["false_negative_count"] == 0
    assert proposal["regimes"]["stable_hold"]["sample_count"] == 25
    assert proposal["thresholds"]["maximum_safe_force_n"] > 0.0
    assert all(value > 0.0 for value in proposal["safety_margins"].values())
    assert all(
        sum(proposal["misclassification_matrix"][actual].values()) == 5
        for actual in ORDERED_REGIMES
    )


def test_split_is_per_regime_and_independent_of_publisher_sequence_residue(
    tmp_path: Path,
) -> None:
    evidence = schema_v3_evidence()
    for sample in (sample for regime in PHYSICAL_REGIMES for sample in evidence["regimes"][regime]):
        sample["publisher_sequence"] = sample["publisher_sequence"] * 5 + 1

    result, output = run_analyzer(tmp_path, evidence)

    assert result.returncode == 0, result.stderr
    proposal = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert proposal["split_method"] == "per_regime_ordered_index_modulo_5"
    assert proposal["calibration_sample_count"] == 100
    assert proposal["evaluation_sample_count"] == 25
    assert all(
        sum(proposal["misclassification_matrix"][actual].values()) == 5
        for actual in PHYSICAL_REGIMES
    )


def test_table_support_force_does_not_define_bilateral_fingertip_threshold(
    tmp_path: Path,
) -> None:
    evidence = complete_evidence()
    for sample in evidence["regimes"]["no_contact"]:
        sample["other_object_contacts"] = [contact("other", 4.0, -0.0002)]
        sample["minimum_signed_distance_m"] = -0.0002
        sample["maximum_normal_force_n"] = 4.0

    result, output = run_analyzer(tmp_path, evidence)

    assert result.returncode == 0, result.stderr
    proposal = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert 0.22 < proposal["thresholds"]["minimum_bilateral_force_n"] < 1.0


def test_table_support_penetration_does_not_define_fingertip_compression_threshold(
    tmp_path: Path,
) -> None:
    evidence = schema_v3_evidence()
    for regime in ("bilateral_touch", "micro_lift_slip", "stable_hold"):
        for sample in evidence["regimes"][regime]:
            sample["other_object_contacts"] = [contact("other", 0.1, -0.004)]
            sample["minimum_signed_distance_m"] = -0.004

    result, output = run_analyzer(tmp_path, evidence)

    assert result.returncode == 0, result.stderr
    proposal = yaml.safe_load(output.read_text(encoding="utf-8"))
    threshold = proposal["thresholds"]["maximum_compression_distance_m"]
    assert 0.0007 < threshold < 0.0025
    assert proposal["regimes"]["stable_hold"]["quantiles"]["p50"][
        "minimum_signed_distance_m"
    ] == pytest.approx(-0.004)
    assert proposal["regimes"]["stable_hold"]["quantiles"]["p50"][
        "minimum_fingertip_signed_distance_m"
    ] == pytest.approx(-0.0007012)


def test_slip_calibration_uses_the_same_window_maximum_as_live_grasp(
    tmp_path: Path,
) -> None:
    evidence = schema_v3_evidence()
    for sample in evidence["regimes"]["bilateral_touch"]:
        sample["object_twist_world"]["linear_m_s"] = [1.0e-8, 0.0, 0.0]
    for sample in evidence["regimes"]["stable_hold"]:
        sample["object_twist_world"]["linear_m_s"] = [1.0e-6, 0.0, 0.0]
    for index, sample in enumerate(evidence["regimes"]["micro_lift_slip"]):
        speed_m_s = 0.002 if index == 0 else 0.0002 if index == 4 else 0.5e-6
        sample["object_twist_world"]["linear_m_s"] = [speed_m_s, 0.0, 0.0]

    result, output = run_analyzer(tmp_path, evidence)

    assert result.returncode == 0, result.stderr
    proposal = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert proposal["calibration_status"] == "VALID"
    assert proposal["classification_contract"] == {
        "slip_metric": "maximum_linear_speed_over_split_window_m_s",
        "calibration_window_sample_counts": dict.fromkeys(PHYSICAL_REGIMES, 20),
        "evaluation_window_sample_counts": dict.fromkeys(PHYSICAL_REGIMES, 5),
    }
    assert proposal["misclassification_matrix"]["micro_lift_slip"]["micro_lift_slip"] == 5
    assert 1.0e-6 < proposal["thresholds"]["maximum_hold_linear_speed_m_s"] < 0.0002


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (
            lambda item: item["unilateral_rejection_contracts"]["left_only"].update(
                physical_misclassification_rate=0.0
            ),
            "null",
        ),
        (
            lambda item: item["unilateral_rejection_contracts"]["right_only"][
                "physical_evidence"
            ].update(disposition="missing"),
            "disposition",
        ),
        (
            lambda item: item["unilateral_rejection_contracts"]["left_only"][
                "physical_evidence"
            ].update(references=[]),
            "reference",
        ),
        (
            lambda item: item["regimes"].update(left_only=[]),
            "physical regimes",
        ),
    ),
)
def test_schema_v3_rejects_fabricated_or_unbound_unilateral_statistics(
    tmp_path: Path, mutate, message: str
) -> None:
    evidence = schema_v3_evidence()
    mutate(evidence)

    result, output = run_analyzer(tmp_path, evidence)

    assert result.returncode != 0
    assert message in result.stderr.lower()
    assert not output.exists()


@pytest.mark.parametrize(
    ("mutate", "message"),
    (
        (lambda item: item["regimes"].pop("right_only"), "right_only"),
        (
            lambda item: item["regimes"]["stable_hold"].__setitem__(slice(19, None), []),
            "20",
        ),
        (
            lambda item: item["regimes"]["stable_hold"][0].__setitem__(
                "simulation_session_id", "other-session"
            ),
            "session",
        ),
        (
            lambda item: item["regimes"]["stable_hold"][0].__setitem__("reset_epoch", 5),
            "reset",
        ),
        (
            lambda item: item["regimes"]["stable_hold"][1].__setitem__(
                "publisher_sequence",
                item["regimes"]["stable_hold"][0]["publisher_sequence"],
            ),
            "sequence",
        ),
        (
            lambda item: item["regimes"]["stable_hold"][0].pop("left_fingertip_contacts"),
            "left_fingertip_contacts",
        ),
        (
            lambda item: item["regimes"]["stable_hold"][0].__setitem__(
                "maximum_normal_force_n", float("inf")
            ),
            "finite",
        ),
        (
            lambda item: item["fingerprint"].update(scene_sha256="0" * 64),
            "placeholder",
        ),
    ),
)
def test_analyzer_rejects_invalid_atomic_evidence(tmp_path: Path, mutate, message: str) -> None:
    evidence = complete_evidence()
    mutate(evidence)

    result, output = run_analyzer(tmp_path, evidence)

    assert result.returncode != 0
    assert message in result.stderr.lower()
    assert not output.exists()


def test_analyzer_rejects_overlapping_distributions(tmp_path: Path) -> None:
    result, output = run_analyzer(tmp_path, complete_evidence(overlapping=True))

    assert result.returncode != 0
    assert "overlap" in result.stderr.lower() or "separat" in result.stderr.lower()
    if output.exists():
        assert yaml.safe_load(output.read_text(encoding="utf-8"))["calibration_status"] != "VALID"


def test_validate_accepts_disabled_proposal_but_rejects_fake_activation(tmp_path: Path) -> None:
    result, output = run_analyzer(tmp_path, complete_evidence())
    assert result.returncode == 0

    valid = subprocess.run(
        [sys.executable, str(ANALYZER), "--validate", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert valid.returncode == 0, valid.stderr

    document = yaml.safe_load(output.read_text(encoding="utf-8"))
    document["approval"]["enabled"] = True
    fake = tmp_path / "fake.yaml"
    fake.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    rejected = subprocess.run(
        [sys.executable, str(ANALYZER), "--validate", str(fake)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert rejected.returncode != 0
    assert "approved" in rejected.stderr.lower()


def test_approval_cli_activates_exact_hash_and_refuses_different_overwrite(tmp_path: Path) -> None:
    result, proposal_path = run_analyzer(tmp_path, complete_evidence())
    assert result.returncode == 0
    proposal = yaml.safe_load(proposal_path.read_text(encoding="utf-8"))
    proposal_hash = proposal["approval"]["proposal_sha256"]
    output = tmp_path / "approved.yaml"

    approved = subprocess.run(
        [
            sys.executable,
            str(ANALYZER),
            "--approve",
            str(proposal_path),
            "--proposal-sha256",
            proposal_hash,
            "--approved-by",
            "user",
            "--approved-at",
            "2026-08-12T12:00:00+08:00",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert approved.returncode == 0, approved.stderr
    activated = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert activated["approval"]["enabled"] is True
    assert activated["approval"]["approved"] is True
    assert activated["approval"]["proposal_sha256"] == proposal_hash

    changed = complete_evidence()
    changed["regimes"]["stable_hold"][0]["contact_duration_s"] = 0.55
    changed_result, changed_path = run_analyzer(tmp_path / "changed", changed)
    assert changed_result.returncode == 0
    changed_proposal = yaml.safe_load(changed_path.read_text(encoding="utf-8"))
    refused = subprocess.run(
        [
            sys.executable,
            str(ANALYZER),
            "--approve",
            str(changed_path),
            "--proposal-sha256",
            changed_proposal["approval"]["proposal_sha256"],
            "--approved-by",
            "user",
            "--approved-at",
            "2026-08-12T12:01:00+08:00",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert refused.returncode != 0
    assert "different hash" in refused.stderr.lower()
    assert yaml.safe_load(output.read_text(encoding="utf-8")) == activated


def test_validate_rejects_approved_policy_without_timezone(tmp_path: Path) -> None:
    result, proposal_path = run_analyzer(tmp_path, complete_evidence())
    assert result.returncode == 0
    proposal = yaml.safe_load(proposal_path.read_text(encoding="utf-8"))
    proposal_hash = proposal["approval"]["proposal_sha256"]
    output = tmp_path / "approved.yaml"
    subprocess.run(
        [
            sys.executable,
            str(ANALYZER),
            "--approve",
            str(proposal_path),
            "--proposal-sha256",
            proposal_hash,
            "--approved-by",
            "user",
            "--approved-at",
            "2026-08-12T12:00:00+08:00",
            "--output",
            str(output),
        ],
        check=True,
    )
    document = yaml.safe_load(output.read_text(encoding="utf-8"))
    document["approval"]["approved_at"] = "2026-08-12T12:00:00"
    output.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    invalid = subprocess.run(
        [sys.executable, str(ANALYZER), "--validate", str(output)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert invalid.returncode != 0
    assert "timezone" in invalid.stderr.lower()
