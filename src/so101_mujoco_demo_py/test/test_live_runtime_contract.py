import json
from dataclasses import replace
from pathlib import Path

from so101_mujoco_demo_py.live_runtime import (
    LIVE_PHASES,
    LiveRuntimeConfig,
    _validate_final_release,
    build_phase_specs,
    run_live_workflow,
)
from so101_mujoco_demo_py.task_policy import load_task_policy

MOTION_POLICY = (
    Path(__file__).parents[1] / "config" / "motion_policies" / "light_cup_wall_pick.yaml"
)


def config(tmp_path: Path) -> LiveRuntimeConfig:
    policy = tmp_path / "policy.yaml"
    policy.write_bytes(MOTION_POLICY.read_bytes())
    return LiveRuntimeConfig(
        simulation_session_id="test-session",
        expected_reset_epoch=7,
        evidence_root=tmp_path / "evidence",
        motion_policy=policy,
        python_executable="python-under-test",
    )


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
