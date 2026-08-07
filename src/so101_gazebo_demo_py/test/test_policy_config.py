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
    assert len(bundle.sha256) == 64


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
