from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from so101_mujoco_demo_py.full_restart_baseline import (
    BaselineEvidenceInvalid,
    build_full_restart_baseline,
    write_baseline_artifacts,
)

PHASES = (
    "staged-approach",
    "contact-hold",
    "micro-lift",
    "policy-lift-waypoint1",
    "remaining-lift",
    "transport",
    "descend",
    "place-alignment",
    "release-retreat",
)


def _canonical(document: object) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_json(path: Path, document: object) -> str:
    content = _canonical(document)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return hashlib.sha256(content).hexdigest()


def _sample(session: str, step: int, force: float) -> dict[str, object]:
    return {
        "simulation_session_id": session,
        "reset_epoch": 1,
        "physics_step": step,
        "simulation_time_s": step * 0.002,
        "object_pose_world_xyz_xyzw": [
            -0.08 + step * 0.0001,
            -0.25,
            0.20,
            0.0,
            0.0,
            0.0,
            1.0,
        ],
        "object_twist_world_linear_angular": [0.01, 0.0, 0.0, 0.0, 0.02, 0.0],
        "maximum_normal_force_n": force,
        "left_fingertip_total_normal_force_n": force * 0.8,
        "right_fingertip_total_normal_force_n": force,
        "fingertip_max_single_contact_force_n": force,
        "global_max_single_contact_force_n": force,
        "left_fingertip_compression_m": force * 0.00001,
        "right_fingertip_compression_m": force * 0.00002,
        "net_contact_force_world_n": [force, 0.0, 0.0],
        "truncated": False,
        "left_fingertip_contacts": [],
        "right_fingertip_contacts": [],
        "other_object_contacts": [],
    }


def _write_run(root: Path, number: int, *, fingerprint_suffix: str = "a") -> None:
    experiment = f"EXP-{number}"
    session = f"MNT-Q-{experiment}-full-01"
    run_root = root / f"exp{number}"
    workflow = run_root / "teleop-evidence" / session / f"so101-teleop-workflow-{number}"
    raw_root = workflow / "transport-dynamic-raw"
    samples = [_sample(session, step, float(number - 120 + step)) for step in range(10, 13)]
    chunk = {
        "chunk_sequence": number,
        "simulation_session_id": session,
        "reset_epoch": 1,
        "first_physics_step": 10,
        "last_physics_step": 12,
        "first_simulation_time_s": 0.02,
        "last_simulation_time_s": 0.024,
        "failed_publish_attempts": 0,
        "evidence_loss": False,
        "samples": samples,
    }
    chunk_digest = _write_json(raw_root / "chunks" / "placeholder.json", chunk)
    chunk_path = raw_root / "chunks" / f"{number:06d}-{chunk_digest}.json"
    (raw_root / "chunks" / "placeholder.json").rename(chunk_path)
    run_index = {
        "schema": "so101-dynamic-transport-raw-v4",
        "run_id": session,
        "expected_session_id": session,
        "first_snapshot_session_id": session,
        "first_chunk_session_id": session,
        "chunks": [
            {
                "chunk_sequence": number,
                "first_physics_step": 10,
                "last_physics_step": 12,
                "path": f"chunks/{chunk_path.name}",
                "sha256": chunk_digest,
            }
        ],
        "boundaries": [],
        "status": "COMPLETE",
        "outcome_class": "PHYSICAL_TRANSPORT_SUCCESS",
        "physical_transport_outcome": "FORMAL_MOVE_ABOVE_PLACE_PROVED",
    }
    run_index_sha = _write_json(raw_root / "run-index.json", run_index)

    phase_hashes: dict[str, str] = {}
    for offset, phase in enumerate(PHASES):
        document: dict[str, object] = {
            "terminal_evidence": {"maximum_normal_force_n": number + offset / 10.0}
        }
        if phase == "release-retreat":
            document["final_evidence"] = {"maximum_normal_force_n": 0.2 + (number - 126) * 0.01}
        phase_hashes[f"{phase}.json"] = _write_json(workflow / f"{phase}.json", document)

    transport_summary = {
        "run_id": session,
        "acceptance_role": "diagnostic_only",
        "independent_experiment_units": 1,
        "peak_global_max_single_contact_force_n": max(
            sample["global_max_single_contact_force_n"] for sample in samples
        ),
        "force_time_exposure_n_s": float(number),
        "shadow_excess_force_time_exposure_n_s": float(number - 120),
        "maximum_left_fingertip_compression_m": max(
            sample["left_fingertip_compression_m"] for sample in samples
        ),
        "maximum_right_fingertip_compression_m": max(
            sample["right_fingertip_compression_m"] for sample in samples
        ),
        "net_contact_impulse_vector_n_s": [1.0, 0.0, 0.0],
        "sustained_overpressure_windows": [],
        "waypoints": [],
    }
    _write_json(workflow / "transport-dynamic-summary.json", transport_summary)
    manifest = {
        "schema": "so101-mujoco-live-runtime-v1",
        "simulation_session_id": session,
        "expected_reset_epoch": 1,
        "status": "DONE",
        "failure": None,
        "failed_phase": None,
        "completed_phases": [phase.replace("-", "_") for phase in PHASES],
        "phase_exit_codes": {phase.replace("-", "_"): 0 for phase in PHASES},
        "artifact_sha256": phase_hashes,
        "motion_policy_sha256": "1" * 64,
        "contact_policy_sha256": "2" * 64,
    }
    manifest_sha = _write_json(workflow / "live-runtime-manifest.json", manifest)
    result = {
        "experiment_id": f"{experiment}-01",
        "simulation_session_id": session,
        "reset_epoch": 1,
        "lifecycle": "FULL_RESTART",
        "status": "SUCCESS",
        "fingerprint": {
            "source_commit": fingerprint_suffix * 40,
            "motion_policy_sha256": "1" * 64,
            "contact_policy_sha256": "2" * 64,
            "dependency_sha256": "3" * 64,
            "robot_mjcf_sha256": "4" * 64,
            "scene_sha256": "5" * 64,
            "task_scene_sha256": "6" * 64,
            "urdf_sha256": "7" * 64,
        },
        "clean_shutdown": {"passed": True, "returncode": 0},
        "cua_visual": {"passed": number != 126},
        "moveit_controller_result": {
            "workflow_succeeded": True,
            "completed_phases": [phase.replace("-", "_") for phase in PHASES],
        },
        "owner_evidence_manifest": str(workflow / "live-runtime-manifest.json"),
        "owner_evidence_validation": {
            "manifest_sha256": manifest_sha,
            "forbidden_intervention_counters": {
                "direct_object_state_writes": 0,
                "physics_pause_calls": 0,
                "simulator_constraint_calls": 0,
            },
        },
        "physical_outcome": {
            "primary_failure": None,
            "intended_support_contact": True,
            "gripper_contact": False,
            "moveit_attached": False,
            "world_object_synchronized": True,
            "final_pose": {
                "x_m": -0.08 + (number - 126) * 0.001,
                "y_m": -0.25,
                "z_m": 0.165,
            },
            "metrics": {
                "final_upright_tilt_rad": (number - 125) * 0.001,
                "maximum_linear_speed_m_s": 0.0,
                "maximum_angular_speed_rad_s": 0.0,
            },
        },
        "transport_raw_evidence": {
            "chunk_count": 1,
            "sample_count": 3,
            "first_physics_step": 10,
            "last_physics_step": 12,
            "physics_timestep_s": 0.002,
            "lossless": True,
            "run_index": str(raw_root / "run-index.json"),
            "run_index_sha256": run_index_sha,
        },
        "artifact_sha256": {"owner_evidence_manifest": manifest_sha},
    }
    _write_json(run_root / f"exp-{number}-result.json", result)


def _batch(tmp_path: Path) -> Path:
    root = tmp_path / "evidence"
    for number in range(126, 131):
        _write_run(root, number)
    return root


def test_builds_deterministic_two_level_baseline(tmp_path: Path) -> None:
    root = _batch(tmp_path)

    first = build_full_restart_baseline(
        root,
        tuple(f"EXP-{number}" for number in range(126, 131)),
        visual_waivers={"EXP-126"},
    )
    second = build_full_restart_baseline(
        root,
        tuple(f"EXP-{number}" for number in range(126, 131)),
        visual_waivers={"EXP-126"},
    )

    assert first == second
    assert first["schema"] == "so101-full-restart-baseline-v1"
    assert first["lifecycle"] == "FULL_RESTART"
    assert first["independent_experiment_units"] == 5
    assert first["raw_transport"]["sample_count"] == 15
    assert first["raw_transport"]["sample_role"] == "repeated_measure_diagnostic"
    assert first["policy_effect"] == "NONE_READ_ONLY_BASELINE"
    assert first["raw_transport"]["metrics"]["maximum_normal_force_n"] == {
        "min": 16.0,
        "p50": 19.0,
        "p95": 21.299999999999997,
        "p99": 21.86,
        "max": 22.0,
    }
    assert first["final_outcome"]["final_x_m"]["p50"] == pytest.approx(-0.078)
    assert first["experiments"][0]["visual_evidence"] == "USER_WAIVER"
    assert first["experiments"][1]["visual_evidence"] == "VERIFIED"


def test_rejects_mixed_runtime_fingerprint(tmp_path: Path) -> None:
    root = _batch(tmp_path)
    _write_run(root, 130, fingerprint_suffix="b")

    with pytest.raises(BaselineEvidenceInvalid, match="runtime fingerprint"):
        build_full_restart_baseline(
            root,
            tuple(f"EXP-{number}" for number in range(126, 131)),
            visual_waivers={"EXP-126"},
        )


def test_rejects_tampered_content_addressed_chunk(tmp_path: Path) -> None:
    root = _batch(tmp_path)
    chunk = next((root / "exp127").glob("**/chunks/*.json"))
    chunk.write_bytes(chunk.read_bytes() + b" ")

    with pytest.raises(BaselineEvidenceInvalid, match="chunk sha256"):
        build_full_restart_baseline(
            root,
            tuple(f"EXP-{number}" for number in range(126, 131)),
            visual_waivers={"EXP-126"},
        )


def test_requires_explicit_visual_waiver(tmp_path: Path) -> None:
    root = _batch(tmp_path)

    with pytest.raises(BaselineEvidenceInvalid, match="visual evidence"):
        build_full_restart_baseline(
            root,
            tuple(f"EXP-{number}" for number in range(126, 131)),
        )


def test_writes_pretty_json_and_matching_sha256(tmp_path: Path) -> None:
    document = {"schema": "example", "value": 1}
    output = tmp_path / "baseline.json"
    digest_path = tmp_path / "baseline.sha256"

    digest = write_baseline_artifacts(document, output, digest_path)

    assert output.read_text(encoding="utf-8").startswith('{\n  "schema"')
    assert hashlib.sha256(output.read_bytes()).hexdigest() == digest
    assert digest_path.read_text(encoding="utf-8") == f"{digest}  baseline.json\n"
