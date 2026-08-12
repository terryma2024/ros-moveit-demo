import hashlib
import json
from dataclasses import replace
from pathlib import Path

import yaml

from so101_mujoco_demo_py.contact_policy import (
    ApprovalRecord,
    approve_proposal,
    proposal_sha256,
)
from so101_mujoco_demo_py.live_runtime import (
    LIVE_PHASES,
    LiveRuntimeConfig,
    _validate_final_release,
    build_phase_specs,
    load_live_task_policy,
    run_live_workflow,
)
from so101_mujoco_demo_py.task_policy import load_task_policy

MOTION_POLICY = (
    Path(__file__).parents[1] / "config" / "motion_policies" / "light_cup_wall_pick.yaml"
)
PACKAGE_ROOT = MOTION_POLICY.parents[2]


def write_approved_contact_policy(
    tmp_path: Path,
    *,
    model_sha256: str | None = None,
    maximum_safe_force_n: float = 5.0,
) -> Path:
    dependency = yaml.safe_load(
        (PACKAGE_ROOT / "config" / "dependency-lock.yaml").read_text(encoding="utf-8")
    )["fork"]["commit"]
    document: dict[str, object] = {
        "schema_version": 2,
        "policy_id": "light_cup_wall_pick-contact",
        "calibration_status": "VALID",
        "fingerprint": {
            "source_commit": "1" * 40,
            "dependency_commit": dependency,
            "model_sha256": model_sha256
            or hashlib.sha256((PACKAGE_ROOT / "mjcf" / "so101.xml").read_bytes()).hexdigest(),
            "scene_sha256": hashlib.sha256(
                (PACKAGE_ROOT / "mjcf" / "scene.xml").read_bytes()
            ).hexdigest(),
            "motion_policy_sha256": hashlib.sha256(MOTION_POLICY.read_bytes()).hexdigest(),
            "source_evidence_sha256": "d" * 64,
        },
        "evaluation": {
            "maximum_observation_age_s": 0.1,
            "minimum_consecutive_samples": 5,
        },
        "allowed_other_contact_bodies": ["table_collision"],
        "thresholds": {
            "minimum_bilateral_force_n": 0.5,
            "maximum_compression_distance_m": 0.0015,
            "maximum_safe_force_n": maximum_safe_force_n,
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
    return path


def write_disabled_contact_policy(tmp_path: Path) -> Path:
    document = yaml.safe_load(write_approved_contact_policy(tmp_path).read_text(encoding="utf-8"))
    document["approval"].update(
        enabled=False,
        approved=False,
        approved_by=None,
        approved_at=None,
    )
    path = tmp_path / "disabled-contact.yaml"
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")
    return path


def config(tmp_path: Path) -> LiveRuntimeConfig:
    return LiveRuntimeConfig(
        simulation_session_id="test-session",
        expected_reset_epoch=7,
        evidence_root=tmp_path / "evidence",
        motion_policy=MOTION_POLICY,
        contact_policy=write_approved_contact_policy(tmp_path),
        python_executable="python-under-test",
    )


def test_disabled_contact_policy_fails_before_resume_or_phase_commands(tmp_path) -> None:
    runtime = replace(config(tmp_path), contact_policy=write_disabled_contact_policy(tmp_path))
    observed = []

    result = run_live_workflow(
        runtime,
        resume=lambda _config: observed.append("resume") or True,
        command_runner=lambda *_args: observed.append("phase") or 0,
    )

    assert not result.success
    assert result.failure == "CONTACT_POLICY_NOT_APPROVED"
    assert result.failed_phase == "preflight"
    assert observed == []


def test_changed_physical_fingerprint_fails_before_side_effects(tmp_path) -> None:
    runtime = replace(
        config(tmp_path),
        contact_policy=write_approved_contact_policy(tmp_path, model_sha256="f" * 64),
    )
    observed = []

    result = run_live_workflow(
        runtime,
        resume=lambda _config: observed.append("resume") or True,
        command_runner=lambda *_args: observed.append("phase") or 0,
    )

    assert not result.success
    assert result.failure == "POLICY_FINGERPRINT_MISMATCH"
    assert result.failed_phase == "preflight"
    assert observed == []


def evidence_for(phase_name: str, status: str) -> dict:
    result = {
        "status": status,
        "simulation_session_id": "test-session",
        "reset_epoch": 7,
    }
    if phase_name == "release_retreat":
        samples = [
            {
                "release_epoch_id": "live-release-epoch-7",
                "receipt_sequence": 101 + index,
                "source_timestamp_s": 10.0 + index * 0.05,
                "observed_monotonic_s": 20.0 + index * 0.05,
                "pose_xyz_xyzw": [-0.08, -0.25, 0.165, 0.0, 0.0, 0.0, 1.0],
                "support_contact": True,
                "gripper_contact": False,
                "gazebo_detached": True,
                "moveit_detached": True,
                "controller_healthy": True,
                "safety_healthy": True,
                "shadow_divergence_healthy": True,
            }
            for index in range(5)
        ]
        result.update(
            {
                "release_epoch_id": "live-release-epoch-7",
                "release_marker_sequence": 100,
                "final_samples": samples,
                "final_evaluation": {"success": True},
                "final_evidence": {
                    "cup_position_world_m": [-0.08, -0.25, 0.165],
                    "left_contact_count": 0,
                    "right_contact_count": 0,
                    "table_contact": True,
                    "reset_epoch": 7,
                },
                "radial_acm_scope": {
                    "moving_jaw_link_allowed": False,
                    "restored_before_vertical": True,
                    "restored_pair_allowed": False,
                },
                "planning_scene_readback": {
                    "attached_object_ids": [],
                    "world_primitive_counts": {
                        "table": 1,
                        "pedestal": 1,
                        "plastic_cup": 13,
                    },
                },
            }
        )
    return result


def test_final_release_recomputes_samples_with_injected_policy() -> None:
    document = evidence_for("release_retreat", "RELEASE_RETREAT_FINAL_PLACEMENT_PROVED")
    document["final_evaluation"] = {"success": False}
    physical = load_task_policy(MOTION_POLICY).physical_outcome

    assert _validate_final_release(document, physical)
    assert not _validate_final_release(
        document,
        replace(
            physical,
            final_target_min_xy_m=(-0.060, -0.260),
            final_target_max_xy_m=(-0.050, -0.240),
        ),
    )


def test_final_release_rejects_unreviewed_or_mistyped_sample_fields() -> None:
    physical = load_task_policy(MOTION_POLICY).physical_outcome
    document = evidence_for("release_retreat", "RELEASE_RETREAT_FINAL_PLACEMENT_PROVED")
    document["final_samples"][0]["unreviewed"] = True
    assert not _validate_final_release(document, physical)

    document = evidence_for("release_retreat", "RELEASE_RETREAT_FINAL_PLACEMENT_PROVED")
    document["final_samples"][0]["support_contact"] = 1
    assert not _validate_final_release(document, physical)


def test_phase_specs_use_one_production_entry_sequence_and_frozen_environment(tmp_path) -> None:
    runtime = config(tmp_path)

    specs, environment = build_phase_specs(runtime)

    assert tuple(spec.name for spec in specs) == LIVE_PHASES
    assert specs[0].command[:3] == (
        "python-under-test",
        "-m",
        "so101_mujoco_demo_py.staged_approach",
    )
    assert specs[-1].command[:3] == (
        "python-under-test",
        "-m",
        "so101_mujoco_demo_py.live_phases.release_retreat",
    )
    assert environment["SO101_SIMULATION_SESSION_ID"] == "test-session"
    assert environment["SO101_EXPECTED_RESET_EPOCH"] == "7"
    assert environment["SO101_EVIDENCE_ROOT"] == str(runtime.evidence_root)
    assert environment["SO101_MOTION_POLICY"] == str(runtime.motion_policy)
    assert environment["SO101_CONTACT_POLICY"] == str(runtime.contact_policy)
    assert (
        environment["SO101_MODEL_SHA256"]
        == hashlib.sha256((PACKAGE_ROOT / "mjcf" / "so101.xml").read_bytes()).hexdigest()
    )


def test_temporary_live_phases_receive_one_hash_bound_changed_threshold(tmp_path) -> None:
    runtime = replace(
        config(tmp_path),
        contact_policy=write_approved_contact_policy(tmp_path, maximum_safe_force_n=4.25),
    )
    _, environment = build_phase_specs(runtime)

    loaded = load_live_task_policy(environment)

    assert loaded.contact is not None
    assert loaded.contact.thresholds.maximum_safe_force_n == 4.25
    phase_root = PACKAGE_ROOT / "so101_mujoco_demo_py" / "live_phases"
    for phase in LIVE_PHASES[1:]:
        source = (phase_root / f"{phase}.py").read_text(encoding="utf-8")
        assert "load_live_task_policy()" in source
        assert "maximum_safe_force_n" in source


def test_live_runtime_runs_once_in_order_and_writes_fail_visible_manifest(tmp_path) -> None:
    runtime = config(tmp_path)
    observed = []

    def resume(_config) -> bool:
        observed.append("resume_physics")
        return True

    def run_phase(spec, _environment, _log_path) -> int:
        observed.append(spec.name)
        spec.evidence_path.write_text(
            json.dumps(evidence_for(spec.name, spec.expected_status)), encoding="utf-8"
        )
        return 0

    result = run_live_workflow(runtime, resume=resume, command_runner=run_phase)

    assert result.success
    assert result.failed_phase is None
    assert observed == ["resume_physics", *LIVE_PHASES]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "DONE"
    assert manifest["completed_phases"] == list(LIVE_PHASES)
    assert set(manifest["artifact_sha256"]) == {
        spec.evidence_path.name for spec in build_phase_specs(runtime)[0]
    }


def test_live_runtime_stops_at_first_failed_phase_and_preserves_prior_evidence(tmp_path) -> None:
    runtime = config(tmp_path)
    observed = []

    def run_phase(spec, _environment, _log_path) -> int:
        observed.append(spec.name)
        if spec.name == "micro_lift":
            return 17
        spec.evidence_path.write_text(
            json.dumps(evidence_for(spec.name, spec.expected_status)), encoding="utf-8"
        )
        return 0

    result = run_live_workflow(
        runtime,
        resume=lambda _config: True,
        command_runner=run_phase,
    )

    assert not result.success
    assert result.failed_phase == "micro_lift"
    assert observed == ["staged_approach", "contact_hold", "micro_lift"]
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["failed_phase"] == "micro_lift"
    assert manifest["phase_exit_codes"]["micro_lift"] == 17


def test_release_success_rejects_unrestored_acm_or_nonphysical_final_state(tmp_path) -> None:
    runtime = config(tmp_path)

    def run_phase(spec, _environment, _log_path) -> int:
        document = evidence_for(spec.name, spec.expected_status)
        if spec.name == "release_retreat":
            document["radial_acm_scope"]["restored_before_vertical"] = False
        spec.evidence_path.write_text(json.dumps(document), encoding="utf-8")
        return 0

    result = run_live_workflow(
        runtime,
        resume=lambda _config: True,
        command_runner=run_phase,
    )

    assert not result.success
    assert result.failed_phase == "release_retreat"
    assert result.failure == "PHYSICAL_FINAL_EVIDENCE_REJECTED"
