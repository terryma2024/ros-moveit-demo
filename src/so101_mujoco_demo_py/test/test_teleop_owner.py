import json
from pathlib import Path

from so101_mujoco_demo_py.teleop_reset import build_parser as reset_parser
from so101_mujoco_demo_py.teleop_workflow import owner_result, production_arguments


def test_reset_cli_requires_the_physical_simulation_session() -> None:
    options = reset_parser().parse_args(["--session-id", "sim-a"])

    assert options.session_id == "sim-a"
    assert options.keyframe == "task_start"


def test_workflow_arguments_bind_current_epoch_and_installed_policy() -> None:
    values = production_arguments(
        session_id="sim-a",
        reset_epoch=7,
        checkpoint=Path("/tmp/run-1.json"),
        package_share=Path("/installed/share/so101_mujoco_demo_py"),
    )

    assert values[:3] == ["--mode", "execute", "--execute"]
    assert values[values.index("--expected-reset-epoch") + 1] == "7"
    assert values[values.index("--session-id") + 1] == "sim-a"
    assert values[values.index("--motion-policy") + 1] == (
        "/installed/share/so101_mujoco_demo_py/config/motion_policies/light_cup_wall_pick.yaml"
    )
    assert values[values.index("--contact-policy") + 1] == (
        "/installed/share/so101_mujoco_demo_py/config/contact_calibration.yaml"
    )


def test_workflow_owner_returns_manifest_bound_physical_outcome(tmp_path) -> None:
    (tmp_path / "live-runtime-manifest.json").write_text(
        json.dumps(
            {
                "status": "DONE",
                "simulation_session_id": "sim-a",
                "completed_phases": ["staged_approach", "release_retreat"],
            }
        )
    )
    (tmp_path / "release-retreat.json").write_text(
        json.dumps(
            {
                "released_evidence": {"publisher_sequence": 10},
                "final_evidence": {
                    "publisher_sequence": 20,
                    "cup_position_world_m": [-0.0788, -0.2475, 0.1655],
                    "cup_orientation_world_xyzw": [0.0, 0.0, 0.0, 1.0],
                    "left_contact_count": 0,
                    "right_contact_count": 0,
                    "table_contact": True,
                },
                "final_evaluation": {
                    "sample_count": 21,
                    "duration_s": 0.2,
                    "failure_code": None,
                    "metrics": {"final_upright_tilt_rad": 0.01},
                },
                "planning_scene_readback": {
                    "attached_object_ids": [],
                    "world_primitive_counts": {"plastic_cup": 13},
                },
            }
        )
    )

    result = owner_result(tmp_path)

    assert result["status"] == "DONE"
    assert result["trace"] == "staged_approach -> release_retreat"
    assert result["evidence_manifest"] == str(tmp_path / "live-runtime-manifest.json")
    assert result["physical_outcome"]["release_epoch_id"] == "sim-a:release:10"
    assert result["physical_outcome"]["intended_support_contact"] is True
    assert result["physical_outcome"]["world_object_synchronized"] is True
