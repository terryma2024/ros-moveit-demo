from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest
import yaml

from so101_mujoco_demo_py.contact_calibration import (
    build_dynamic_transport_proposal,
    main,
    validate_policy,
)
from so101_mujoco_demo_py.contact_policy import (
    ApprovalRecord,
    approve_proposal,
    proposal_sha256,
    validate_dynamic_diagnostic_proposal,
)

STATIC_THRESHOLD_N = 1.1579004532160448
DIAGNOSTIC_STOP_N = 11.60


def digest(character: str) -> str:
    return character * 64


def waypoint(index: int) -> dict:
    return {
        "waypoint": index,
        "statistical_role": "repeated_measure",
        "first_physics_step": index * 100,
        "last_physics_step": index * 100 + 99,
        "peak_global_max_single_contact_force_n": 2.0 + index / 10.0,
        "force_time_exposure_n_s": 0.02 + index / 1000.0,
        "shadow_excess_force_time_exposure_n_s": 0.01 + index / 1000.0,
        "net_contact_impulse_vector_n_s": [0.01, 0.02, 0.03],
        "maximum_left_fingertip_compression_m": 0.001,
        "maximum_right_fingertip_compression_m": 0.0015,
    }


def run(index: int) -> dict:
    summary_hash_characters = ("8", "9", "a", "b", "c")
    return {
        "run_id": f"EXP-{109 + index}",
        "run_role": "preregistered_replication" if index == 5 else "descriptive_repeat",
        "status": "VALID",
        "outcome_class": "PHYSICAL_TRANSPORT_SUCCESS",
        "physical_transport_outcome": "FORMAL_MOVE_ABOVE_PLACE_PROVED",
        "simulation_session_id": f"MNT-A-PHASE-exp{109 + index}-full-01",
        "reset_epoch": 1,
        "source_commit": "a" * 40,
        "install_tree_sha256": digest("c"),
        "runtime_fingerprint_sha256": digest("d"),
        "raw_evidence_sha256": digest(chr(ord("a") + index - 1)),
        "summary_sha256": digest(summary_hash_characters[index - 1]),
        "peak_global_max_single_contact_force_n": 2.5 + index / 10.0,
        "force_time_exposure_n_s": 0.1 + index / 100.0,
        "shadow_excess_force_time_exposure_n_s": 0.05 + index / 100.0,
        "net_contact_impulse_vector_n_s": [0.1, 0.2, 0.3],
        "maximum_left_fingertip_compression_m": 0.001,
        "maximum_right_fingertip_compression_m": 0.0015,
        "sustained_overpressure_windows": [],
        "waypoints": [waypoint(item) for item in range(1, 6)],
    }


def provenance() -> dict:
    return {
        "source_commit": "a" * 40,
        "dependency_commit": "b" * 40,
        "install_tree_sha256": digest("c"),
        "runtime_fingerprint_sha256": digest("d"),
        "contact_policy_sha256": digest("e"),
    }


def frozen_behavior() -> dict:
    return {
        "manifest_sha256": digest("1"),
        "motion_policy_sha256": digest("2"),
        "grasp_strategy_sha256": digest("3"),
        "baseline_transport_sha256": digest("4"),
        "scene_sha256": digest("5"),
        "robot_mjcf_sha256": digest("6"),
        "protected_gazebo_tree_oid": "7" * 40,
    }


def proposal() -> dict:
    return build_dynamic_transport_proposal(
        [run(index) for index in range(1, 6)],
        provenance=provenance(),
        frozen_behavior=frozen_behavior(),
    )


def test_builds_deterministic_disabled_diagnostic_only_schema_v4() -> None:
    first = proposal()
    second = proposal()

    assert first == second
    assert first["schema_version"] == 4
    assert first["acceptance_role"] == "diagnostic_only"
    assert first["independent_experiment_units"] == 5
    assert first["static_contact_contract"]["maximum_safe_force_n"] == STATIC_THRESHOLD_N
    assert first["dynamic_transport_contract"]["diagnostic_hard_stop_n"] == DIAGNOSTIC_STOP_N
    assert first["dynamic_transport_contract"]["static_threshold_role"] == "shadow_only"
    assert first["approval"] == {
        "enabled": False,
        "approved": False,
        "approved_by": None,
        "approved_at": None,
        "proposal_sha256": proposal_sha256(first),
    }
    assert all(item["run_role"] == "descriptive_repeat" for item in first["runs"][:4])
    assert first["runs"][4]["run_role"] == "preregistered_replication"
    assert all(
        detail["statistical_role"] == "repeated_measure"
        for item in first["runs"]
        for detail in item["waypoints"]
    )
    assert "dynamic_acceptance_threshold_n" not in repr(first)
    validate_dynamic_diagnostic_proposal(first)
    validate_policy(first)


def test_schema_v4_cannot_be_activated_as_a_runtime_contact_policy() -> None:
    document = proposal()

    with pytest.raises(ValueError, match="schema_version must be 2 or 3"):
        approve_proposal(
            document,
            ApprovalRecord(
                document["approval"]["proposal_sha256"], "user", "2026-08-12T18:00:00+08:00"
            ),
        )


def test_cli_writes_identical_schema_v4_bytes_from_identical_input(tmp_path: Path) -> None:
    input_path = tmp_path / "dynamic-input.json"
    first_path = tmp_path / "first.yaml"
    second_path = tmp_path / "second.yaml"
    input_path.write_text(
        json.dumps(
            {
                "runs": [run(index) for index in range(1, 6)],
                "provenance": provenance(),
                "frozen_behavior": frozen_behavior(),
            }
        ),
        encoding="utf-8",
    )

    assert main(["--dynamic-input", str(input_path), "--output", str(first_path)]) == 0
    assert main(["--dynamic-input", str(input_path), "--output", str(second_path)]) == 0

    assert first_path.read_bytes() == second_path.read_bytes()
    validate_dynamic_diagnostic_proposal(yaml.safe_load(first_path.read_bytes()))


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda item: item["runs"].pop(), "exactly five independent"),
        (lambda item: item["runs"].append(copy.deepcopy(item["runs"][0])), "exactly five"),
        (
            lambda item: item["runs"][1].update(run_id=item["runs"][0]["run_id"]),
            "unique run_id",
        ),
        (
            lambda item: item.update(dynamic_acceptance_threshold_n=3.0),
            "unknown diagnostic proposal keys",
        ),
        (lambda item: item["approval"].update(enabled=True), "must remain disabled"),
        (
            lambda item: item["runs"][0].update(outcome_class="VALID_SAFETY_ABORT"),
            "physical transport successes",
        ),
        (lambda item: item["runs"][0].pop("raw_evidence_sha256"), "raw_evidence_sha256"),
        (lambda item: item.update(independent_experiment_units=25), "exactly five"),
        (
            lambda item: item["runs"][0]["waypoints"][0].update(
                statistical_role="independent_sample"
            ),
            "repeated_measure",
        ),
    ],
)
def test_schema_v4_rejects_invalid_statistics_activation_or_missing_provenance(
    mutate, message: str
) -> None:
    document = proposal()
    mutate(document)

    with pytest.raises(ValueError, match=message):
        validate_dynamic_diagnostic_proposal(document)
