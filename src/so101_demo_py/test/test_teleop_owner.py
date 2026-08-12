from __future__ import annotations

import json
from pathlib import Path

from so101_demo.cli.teleop_reset import build_parser as reset_parser
from so101_demo.cli.teleop_workflow import owner_result, production_arguments


def test_reset_cli_requires_physical_session() -> None:
    options = reset_parser().parse_args(["--session-id", "sim-a"])

    assert options.session_id == "sim-a"
    assert options.keyframe == "task_start"


def test_workflow_arguments_bind_unified_policy_and_epoch() -> None:
    values = production_arguments(
        session_id="sim-a",
        reset_epoch=7,
        checkpoint=Path("/data/work/run-1.json"),
        package_share=Path("/installed/share/so101_demo_py"),
    )

    assert values[:3] == ["--backend", "mujoco", "--mode"]
    assert values[values.index("--expected-reset-epoch") + 1] == "7"
    assert values[values.index("--motion-policy") + 1].endswith(
        "/so101_demo_py/config/policies/light_cup_wall_pick/v1/mujoco.yaml"
    )


def test_owner_result_exposes_physical_outcome(tmp_path: Path) -> None:
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

    assert result["trace"] == "staged_approach -> release_retreat"
    assert result["physical_outcome"]["primary_failure"] is None
    assert result["physical_outcome"]["world_object_synchronized"] is True
