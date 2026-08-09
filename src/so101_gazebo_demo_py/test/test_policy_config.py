from dataclasses import replace
import json
import math
from pathlib import Path

import pytest
import yaml

from so101_gazebo_demo_py.domain import State
from so101_gazebo_demo_py.policy_config import ConfigurationError, load_policy_bundle


CONFIG = Path(__file__).parents[1] / "config"


def load_bundle():
    return load_policy_bundle(
        CONFIG / "task_objects/light_plastic_cup.yaml",
        CONFIG / "motion_policies/light_cup_wall_pick.yaml",
        CONFIG / "validation_policies/light_cup_wall_pick.yaml",
    )


def test_loads_strict_typed_policy_bundle() -> None:
    bundle = load_bundle()
    assert bundle.object.schema_version == 1
    assert bundle.motion.policy_id == bundle.validation.policy_id == "light_cup_wall_pick"
    assert bundle.object.object_id == bundle.motion.object_id == bundle.validation.object_id == "plastic_cup"
    assert bundle.motion.arm_joints == ("1", "2", "3", "4", "5")
    assert bundle.motion.gripper_joint == "6"
    assert len(bundle.object.spawn_pose.values) == 7
    assert all(len(state.waypoints[0]) == 5 for state in bundle.motion.states.values())
    assert State.MOVE_ABOVE_OBJECT in bundle.motion.states
    assert bundle.motion.approach_outside_clearance_m == 0.001
    assert bundle.motion.grasp_tcp_translation_offset_m == (0.0, 0.0, 0.0)
    assert bundle.motion.seating_preload_rad == 0.004
    assert bundle.motion.grasp_tcp_world_x_rotation_rad == 0.0
    assert bundle.motion.states[State.RETREAT].waypoints == (
        bundle.motion.states[State.RECOVER_LIFT_TO_SAFE_HEIGHT].waypoints
    )
    assert bundle.validation.states[State.RETREAT].data["path_direction"] == [
        0.0, 0.0, 1.0,
    ]
    assert bundle.motion.states[State.MOVE_ABOVE_PLACE].waypoints[-1] == pytest.approx((
        0.39605349936733336,
        0.20811109174700002,
        0.11216949915749999,
        1.1793226274016666,
        0.0014322254539999998,
    ))
    assert bundle.motion.states[State.DESCEND_TO_PLACE].waypoints[-1] == pytest.approx((
        0.3902880767431667,
        0.4786634968135,
        0.13135032910475003,
        0.9840056686529166,
        0.001886270923083333,
    ))
    assert bundle.validation.states[State.MOVE_ABOVE_PLACE].data[
        "endpoint_position"
    ] == pytest.approx((-0.0728540412968976, -0.2466491907831009, 0.26266213748863515))
    assert bundle.validation.states[State.DESCEND_TO_PLACE].data[
        "endpoint_position"
    ] == pytest.approx((-0.07014007387726474, -0.24375048527937768, 0.20749669383910732))
    assert len(bundle.sha256) == 64


@pytest.mark.parametrize("preload", [-0.001, 0.006001])
def test_rejects_out_of_range_seating_preload(tmp_path: Path, preload: float) -> None:
    motion = yaml.safe_load(
        (CONFIG / "motion_policies/light_cup_wall_pick.yaml").read_text()
    )
    motion["gripper_actions"]["seating_preload_rad"] = preload
    motion_path = tmp_path / "motion.yaml"
    motion_path.write_text(yaml.safe_dump(motion, sort_keys=False))

    with pytest.raises(ConfigurationError, match="seating preload"):
        load_policy_bundle(
            CONFIG / "task_objects/light_plastic_cup.yaml",
            motion_path,
            CONFIG / "validation_policies/light_cup_wall_pick.yaml",
        )


@pytest.mark.parametrize("rotation", [-0.0873, 0.087266463])
def test_rejects_out_of_tolerance_world_x_rotation(tmp_path: Path, rotation: float) -> None:
    motion = yaml.safe_load(
        (CONFIG / "motion_policies/light_cup_wall_pick.yaml").read_text()
    )
    motion["grasp_tcp_world_x_rotation_rad"] = rotation
    motion_path = tmp_path / "motion.yaml"
    motion_path.write_text(yaml.safe_dump(motion, sort_keys=False))

    with pytest.raises(ConfigurationError, match="grasp TCP world-X rotation"):
        load_policy_bundle(
            CONFIG / "task_objects/light_plastic_cup.yaml",
            motion_path,
            CONFIG / "validation_policies/light_cup_wall_pick.yaml",
        )


@pytest.mark.parametrize(
    "offset",
    [(-0.001001, 0.0, 0.0), (-0.0005, 0.0005, 0.0)],
)
def test_rejects_out_of_range_or_multi_axis_tcp_candidate(
    tmp_path: Path, offset: tuple[float, float, float],
) -> None:
    motion = yaml.safe_load(
        (CONFIG / "motion_policies/light_cup_wall_pick.yaml").read_text()
    )
    motion["grasp_tcp_translation_offset_m"] = list(offset)
    motion_path = tmp_path / "motion.yaml"
    motion_path.write_text(yaml.safe_dump(motion, sort_keys=False))

    with pytest.raises(ConfigurationError, match="grasp TCP translation"):
        load_policy_bundle(
            CONFIG / "task_objects/light_plastic_cup.yaml",
            motion_path,
            CONFIG / "validation_policies/light_cup_wall_pick.yaml",
        )


def test_loads_calibrated_physical_outcome_policy() -> None:
    outcome = load_bundle().validation.physical_outcome
    assert outcome.intended_support_collision == "table::table_top::collision"
    assert outcome.minimum_support_contact_depth_m == -0.0000001
    assert outcome.final_target_min_xy_m == (-0.085, -0.255)
    assert outcome.final_target_max_xy_m == (-0.075, -0.245)
    assert outcome.support_height_range_m == (0.155, 0.175)
    assert outcome.consecutive_samples == 5
    assert outcome.max_telemetry_samples == 40
    assert outcome.planning_shadow.max_position_divergence_m == 0.005
    assert outcome.planning_shadow.max_orientation_divergence_rad == 0.070


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("physical_outcome", "consecutive_samples"), 0),
        (("physical_outcome", "minimum_stable_duration_s"), 0.0),
        (("physical_outcome", "settle_timeout_s"), 0.1),
        (("physical_outcome", "final_target_region", "max_xy_m"), [-0.09, -0.26]),
        (("physical_outcome", "support_height_range_m"), [0.18, 0.15]),
    ],
)
def test_rejects_invalid_physical_outcome_contract(
    tmp_path: Path, path: tuple[str, ...], value: object,
) -> None:
    validation = yaml.safe_load(
        (CONFIG / "validation_policies/light_cup_wall_pick.yaml").read_text()
    )
    target = validation
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    validation_path = tmp_path / "validation.yaml"
    validation_path.write_text(yaml.safe_dump(validation, sort_keys=False))
    with pytest.raises(ConfigurationError):
        load_policy_bundle(
            CONFIG / "task_objects/light_plastic_cup.yaml",
            CONFIG / "motion_policies/light_cup_wall_pick.yaml",
            validation_path,
        )


def test_rejects_unknown_physical_outcome_key(tmp_path: Path) -> None:
    validation = yaml.safe_load(
        (CONFIG / "validation_policies/light_cup_wall_pick.yaml").read_text()
    )
    validation["physical_outcome"]["permissive_escape_hatch"] = True
    validation_path = tmp_path / "validation.yaml"
    validation_path.write_text(yaml.safe_dump(validation, sort_keys=False))
    with pytest.raises(ConfigurationError, match="unknown"):
        load_policy_bundle(
            CONFIG / "task_objects/light_plastic_cup.yaml",
            CONFIG / "motion_policies/light_cup_wall_pick.yaml",
            validation_path,
        )


def test_fingerprint_depends_on_data_not_yaml_formatting(tmp_path: Path) -> None:
    original = load_bundle()
    paths = []
    for index, source in enumerate((
        CONFIG / "task_objects/light_plastic_cup.yaml",
        CONFIG / "motion_policies/light_cup_wall_pick.yaml",
        CONFIG / "validation_policies/light_cup_wall_pick.yaml",
    )):
        destination = tmp_path / f"{index}-{source.name}"
        destination.write_text(yaml.safe_dump(yaml.safe_load(source.read_text()), sort_keys=False))
        paths.append(destination)
    assert load_policy_bundle(*paths).sha256 == original.sha256


@pytest.mark.parametrize("bad_value", [True, math.nan, math.inf])
def test_rejects_boolean_or_nonfinite_numeric_values(tmp_path: Path, bad_value: object) -> None:
    object_data = yaml.safe_load((CONFIG / "task_objects/light_plastic_cup.yaml").read_text())
    object_data["model"]["mass_kg"] = bad_value
    object_path = tmp_path / "object.yaml"
    object_path.write_text(yaml.safe_dump(object_data))
    with pytest.raises(ConfigurationError):
        load_policy_bundle(
            object_path,
            CONFIG / "motion_policies/light_cup_wall_pick.yaml",
            CONFIG / "validation_policies/light_cup_wall_pick.yaml",
        )


def test_rejects_unknown_motion_state(tmp_path: Path) -> None:
    motion = yaml.safe_load((CONFIG / "motion_policies/light_cup_wall_pick.yaml").read_text())
    motion["states"]["NOT_A_STATE"] = motion["states"].pop("MOVE_ABOVE_OBJECT")
    path = tmp_path / "motion.yaml"
    path.write_text(json.dumps(motion))
    with pytest.raises(ConfigurationError, match="unknown state"):
        load_policy_bundle(
            CONFIG / "task_objects/light_plastic_cup.yaml", path,
            CONFIG / "validation_policies/light_cup_wall_pick.yaml",
        )
