from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE_ROOT / "config/contact_calibration.yaml"
ANALYZER = PACKAGE_ROOT / "scripts/analyze_contact_calibration.py"
REGIMES = {
    "no_contact",
    "left_only",
    "right_only",
    "bilateral_touch",
    "over_compression",
    "micro_lift_slip",
    "stable_hold",
}
ORDERED_REGIMES = tuple(sorted(REGIMES))
SOURCE_COMMIT = "1" * 40
DEPENDENCY_COMMIT = "2" * 40
MODEL_SHA256 = "a" * 64
CONFIG_SHA256 = "b" * 64


def load_policy() -> dict:
    return yaml.safe_load(CONFIG.read_text(encoding="utf-8"))


def complete_policy() -> dict:
    policy = load_policy()
    policy["source_commit"] = SOURCE_COMMIT
    policy["dependency_commit"] = DEPENDENCY_COMMIT
    policy["model_sha256"] = MODEL_SHA256
    policy["config_sha256"] = CONFIG_SHA256
    policy["source_evidence_sha256"] = "c" * 64
    policy["units"] = {
        "signed_distance": "m",
        "normal_force": "N",
        "linear_speed": "m/s",
        "joint_position": "rad",
        "simulation_time": "s",
        "receipt_time": "s",
    }
    policy["calibration_status"] = "PLANNED"
    policy["misclassification_matrix"] = {
        actual: {predicted: 0 for predicted in ORDERED_REGIMES} for actual in ORDERED_REGIMES
    }
    return policy


def contact(side: str, force_n: float, distance_m: float) -> dict:
    return {
        "side": side,
        "object_body": "cup",
        "robot_geom": f"{side}_fingertip_pad",
        "signed_distance_m": distance_m,
        "normal_force_n": force_n,
    }


def complete_evidence(*, overlapping: bool = False) -> dict:
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
            samples.append(
                {
                    "regime": regime,
                    "subcohorts": {
                        "table_only": regime == "no_contact" and sample_index % 2 == 0,
                        "post_release": regime == "no_contact" and sample_index % 2 == 1,
                    },
                    "source_commit": SOURCE_COMMIT,
                    "dependency_commit": DEPENDENCY_COMMIT,
                    "model_sha256": MODEL_SHA256,
                    "config_sha256": CONFIG_SHA256,
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
                    "distance_m": distance_m if left or right else 0.0,
                    "force_n": force_n if left or right else 0.0,
                    "linear_speed_m_s": speed_m_s,
                    "q6_rad": 0.20,
                    "arm_joint_positions_rad": [0.0, -0.4, 0.8, 0.5, 0.0],
                    "tcp_pose_world": {
                        "position_m": [0.20, 0.0, 0.09],
                        "orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
                    },
                    "contact_duration_s": duration,
                }
            )
        regimes[regime] = samples
    return {
        "schema_version": 1,
        "units": {
            "signed_distance": "m",
            "normal_force": "N",
            "linear_speed": "m/s",
            "joint_position": "rad",
            "simulation_time": "s",
            "receipt_time": "s",
        },
        "source_commit": SOURCE_COMMIT,
        "dependency_commit": DEPENDENCY_COMMIT,
        "model_sha256": MODEL_SHA256,
        "config_sha256": CONFIG_SHA256,
        "regimes": regimes,
    }


def run_analyzer(tmp_path: Path, evidence: dict) -> tuple[subprocess.CompletedProcess[str], Path]:
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


def test_calibration_policy_is_complete_traceable_and_disabled() -> None:
    policy = load_policy()

    assert policy["schema_version"] == 1
    assert set(policy["regimes"]) == REGIMES
    assert policy["approved_by_user"] is False
    assert policy["enabled"] is False
    assert policy["units"] == {
        "signed_distance": "m",
        "normal_force": "N",
        "linear_speed": "m/s",
        "joint_position": "rad",
        "simulation_time": "s",
        "receipt_time": "s",
    }
    assert policy["model_sha256"] and len(policy["model_sha256"]) == 64
    assert policy["config_sha256"] and len(policy["config_sha256"]) == 64
    assert policy["source_evidence_sha256"] is None
    assert policy["calibration_status"] in {"PLANNED", "VALID"}
    assert set(policy["thresholds"]) == {
        "minimum_bilateral_force_n",
        "maximum_compression_distance_m",
        "maximum_safe_force_n",
        "maximum_hold_linear_speed_m_s",
        "minimum_stable_hold_duration_s",
    }
    for regime in REGIMES:
        result = policy["regimes"][regime]
        assert result["sample_count"] >= 0
        assert set(result["quantiles"]) == {"p05", "p50", "p95"}
    assert set(policy["misclassification_matrix"]) == REGIMES
    if policy["calibration_status"] == "VALID":
        assert all(value is not None for value in policy["thresholds"].values())
        assert all(policy["regimes"][regime]["sample_count"] >= 20 for regime in REGIMES)


def test_enabled_policy_requires_explicit_user_approval(tmp_path: Path) -> None:
    policy = load_policy()
    policy["enabled"] = True
    policy["approved_by_user"] = False
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(ANALYZER), "--validate", str(candidate)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "approved_by_user" in result.stderr


def test_analyzer_rejects_missing_regime_and_nonfinite_samples(tmp_path: Path) -> None:
    evidence = complete_evidence()
    evidence["regimes"].pop("right_only")
    evidence["regimes"]["no_contact"][0]["maximum_normal_force_n"] = float("nan")
    source = tmp_path / "invalid.json"
    source.write_text(json.dumps(evidence), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(ANALYZER), "--input", str(source), "--output", str(tmp_path / "x")],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "right_only" in result.stderr or "nonfinite" in result.stderr


def test_analyzer_builds_disabled_quantile_policy_from_complete_matrix(tmp_path: Path) -> None:
    evidence = complete_evidence()
    source = tmp_path / "matrix.json"
    output = tmp_path / "policy.yaml"
    source.write_text(json.dumps(evidence), encoding="utf-8")

    subprocess.run(
        [sys.executable, str(ANALYZER), "--input", str(source), "--output", str(output)],
        check=True,
    )
    policy = yaml.safe_load(output.read_text(encoding="utf-8"))

    assert policy["enabled"] is False
    assert policy["approved_by_user"] is False
    assert policy["regimes"]["stable_hold"]["sample_count"] == 25
    assert policy["thresholds"]["maximum_safe_force_n"] > 0.0


@pytest.mark.parametrize("approved", [False, True])
def test_policy_remains_disabled_at_approval_stop(tmp_path: Path, approved: bool) -> None:
    policy = load_policy()
    policy["enabled"] = approved
    policy["approved_by_user"] = approved
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(ANALYZER), "--validate", str(candidate)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert (result.returncode == 0) is not approved


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda policy: policy.__setitem__("model_sha256", "0" * 64), "placeholder"),
        (lambda policy: policy.pop("units"), "units"),
        (
            lambda policy: policy["regimes"]["stable_hold"].pop("quantiles"),
            "quantiles",
        ),
        (
            lambda policy: policy["misclassification_matrix"]["stable_hold"].clear(),
            "confusion",
        ),
        (
            lambda policy: policy.update({"enabled": True, "approved_by_user": True}),
            "disabled",
        ),
    ],
)
def test_policy_validation_rejects_incomplete_or_enabled_proposals(
    tmp_path: Path, mutation, message: str
) -> None:
    policy = complete_policy()
    mutation(policy)
    candidate = tmp_path / "candidate.yaml"
    candidate.write_text(yaml.safe_dump(policy, sort_keys=False), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(ANALYZER), "--validate", str(candidate)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert message in result.stderr.lower()


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda evidence: evidence["regimes"]["stable_hold"].__setitem__(slice(19, None), []),
            "20",
        ),
        (
            lambda evidence: evidence["regimes"]["stable_hold"][0].__setitem__(
                "simulation_session_id", "other-session"
            ),
            "session",
        ),
        (
            lambda evidence: evidence["regimes"]["stable_hold"][0].__setitem__("reset_epoch", 5),
            "reset",
        ),
        (
            lambda evidence: evidence["regimes"]["stable_hold"][0].__setitem__(
                "model_sha256", "d" * 64
            ),
            "fingerprint",
        ),
        (
            lambda evidence: evidence["regimes"]["stable_hold"][1].__setitem__(
                "publisher_sequence",
                evidence["regimes"]["stable_hold"][0]["publisher_sequence"],
            ),
            "sequence",
        ),
        (
            lambda evidence: evidence["regimes"]["stable_hold"][0].pop("left_fingertip_contacts"),
            "left_fingertip_contacts",
        ),
        (
            lambda evidence: evidence["regimes"]["stable_hold"][0].__setitem__(
                "maximum_normal_force_n", float("inf")
            ),
            "finite",
        ),
    ],
)
def test_analyzer_rejects_invalid_atomic_evidence(tmp_path: Path, mutate, message: str) -> None:
    evidence = complete_evidence()
    mutate(evidence)

    result, output = run_analyzer(tmp_path, evidence)

    assert result.returncode != 0
    assert message in result.stderr.lower()
    assert not output.exists()


def test_analyzer_rejects_overlapping_distributions_without_manufactured_thresholds(
    tmp_path: Path,
) -> None:
    result, output = run_analyzer(tmp_path, complete_evidence(overlapping=True))

    assert result.returncode != 0
    assert "overlap" in result.stderr.lower() or "separat" in result.stderr.lower()
    if output.exists():
        assert yaml.safe_load(output.read_text(encoding="utf-8"))["calibration_status"] != "VALID"


def test_analyzer_reports_deterministic_evaluation_quality_and_data_margins(
    tmp_path: Path,
) -> None:
    result, output = run_analyzer(tmp_path, complete_evidence())

    assert result.returncode == 0, result.stderr
    policy = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert policy["calibration_status"] == "VALID"
    assert policy["approved_by_user"] is False
    assert policy["enabled"] is False
    assert policy["split_method"] == "publisher_sequence_modulo_5"
    assert policy["calibration_sample_count"] == 140
    assert policy["evaluation_sample_count"] == 35
    assert policy["false_positive_count"] == 0
    assert policy["false_negative_count"] == 0
    assert all(
        sum(policy["misclassification_matrix"][actual].values()) == 5 for actual in ORDERED_REGIMES
    )
    for regime in ORDERED_REGIMES:
        summary = policy["regimes"][regime]
        assert summary["sample_count"] == 25
        assert set(summary["quantiles"]) == {"p05", "p50", "p95"}
        assert "left_normal_force_n" in summary["quantiles"]["p50"]
        assert "right_normal_force_n" in summary["quantiles"]["p50"]
    assert set(policy["safety_margins"]) == {
        "bilateral_force_n",
        "compression_distance_m",
        "safe_force_n",
        "hold_linear_speed_m_s",
        "stable_hold_duration_s",
    }
