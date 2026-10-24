"""Schema 6 is "a base schema plus `diversity`": the DESCEND two-stage keys (and the OPEN_GRIPPER duration) of schema 5 are optional.

Absent, DESCEND and the gripper behave exactly as in schema 4: six interpolated poses, the template scaling, a 2.0 s gripper command.
So the diversity block is orthogonal to the DESCEND mode, and a schema 6 policy with neutral diversity on carry_b's keys plans like carry_b."""

import copy
import math
from types import SimpleNamespace

import pytest
import yaml

from so101_demo.act import teacher_diversity as td
from so101_demo.act.teacher_endpoint import (
    DESCEND_DISTANCE_FIELD,
    DESCEND_FIELDS,
    OPEN_DURATION_FIELD,
    load_teacher_execution_policy,
    speed_policy_value,
)
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import CupPoseSample, resolve_motion_targets
from so101_demo.core.task_geometry import Pose7
from paths import PACKAGE_ROOT

from test_pick_horizon_precompute import START, ik, targets, teacher, template  # noqa: F401 - fixtures
from test_teacher_moveit_execution import make_adapter

CONFIG = PACKAGE_ROOT / "config/act"
CARRY_B = CONFIG / "teacher_execution_policy_side_wrist_fast_carry_b.yaml"
CARRY_B_DIVERSITY = CONFIG / "teacher_execution_policy_side_wrist_fast_carry_b_diversity.yaml"
INVALID = "TEACHER_EXECUTION_POLICY_INVALID"
NEUTRAL = {
    "campaign_seed": 1,
    "start_pose": {"distribution": "uniform", "half_range_rad": 0.0, "max_redraws": 1},
    "pregrasp_height": {"distribution": "uniform", "half_range_m": 0.0},
    "place_approach_height": {"distribution": "uniform", "half_range_m": 0.0},
    "carry_via": {"distribution": "uniform_box", "half_extent_m": [0.0, 0.0, 0.0]},
    "speed_scale": {"distribution": "uniform", "low": 1.0, "high": 1.0},
    "ompl": {"num_planning_attempts": 1},
}
SAMPLE = CupPoseSample("world", 1, 0.0, Pose7((0.051023, -0.339445, 0.165, 0.0, 0.0, 0.0, 1.0)))


def carry_b_document():
    return yaml.safe_load(CARRY_B.read_bytes())


def load_document(document):
    return load_teacher_execution_policy(yaml.safe_dump(document).encode())


def neutral_document(**extra):
    return {**carry_b_document(), "schema_version": 6, "diversity": copy.deepcopy(NEUTRAL), **extra}


# ---- the loader ------------------------------------------------------------------------------------------------------------

def test_a_schema_6_policy_needs_no_descend_keys_and_has_none():
    policy = load_document(neutral_document())
    assert policy["schema_version"] == 6 and not set(DESCEND_FIELDS) & set(policy) and OPEN_DURATION_FIELD not in policy


def test_the_base_values_of_a_schema_6_policy_are_carry_b_s():
    base, six = load_teacher_execution_policy(CARRY_B), load_document(neutral_document())
    for key in set(base) - {"schema_version", "policy_sha256"}:
        assert base[key] == six[key], key
    assert set(six) == set(base) | {"diversity"} and six["policy_sha256"] != base["policy_sha256"]


def test_the_open_duration_alone_and_the_complete_descend_group_are_each_allowed():
    assert load_document(neutral_document(**{OPEN_DURATION_FIELD: 1.0}))[OPEN_DURATION_FIELD] == 1.0
    group = {"descend_approach_velocity_scaling": 0.03, "descend_approach_acceleration_scaling": 0.03, DESCEND_DISTANCE_FIELD: 0.02}
    policy = load_document(neutral_document(**group))
    assert policy[DESCEND_DISTANCE_FIELD] == 0.02 and OPEN_DURATION_FIELD not in policy


@pytest.mark.parametrize("keep", [("descend_approach_velocity_scaling",), (DESCEND_DISTANCE_FIELD,),
                                  ("descend_approach_velocity_scaling", DESCEND_DISTANCE_FIELD)])
def test_the_descend_group_is_all_or_none(keep):
    group = {"descend_approach_velocity_scaling": 0.03, "descend_approach_acceleration_scaling": 0.03, DESCEND_DISTANCE_FIELD: 0.02}
    with pytest.raises(ValueError, match=INVALID):
        load_document(neutral_document(**{key: group[key] for key in keep}))


@pytest.mark.parametrize("key,value", [("descend_approach_velocity_scaling", 1.5), (DESCEND_DISTANCE_FIELD, 0.2), (OPEN_DURATION_FIELD, 60.0)])
def test_the_optional_keys_keep_their_ranges_when_present(key, value):
    group = {"descend_approach_velocity_scaling": 0.03, "descend_approach_acceleration_scaling": 0.03, DESCEND_DISTANCE_FIELD: 0.02,
             OPEN_DURATION_FIELD: 1.0}
    with pytest.raises(ValueError, match=INVALID):
        load_document(neutral_document(**{**group, key: value}))


def test_a_schema_6_policy_with_all_the_schema_5_keys_still_loads_as_before():
    policy = load_teacher_execution_policy(CONFIG / "teacher_execution_policy_side_wrist_experimental_two_leg_diversity.yaml")
    assert policy["schema_version"] == 6 and policy[DESCEND_DISTANCE_FIELD] == 0.02 and policy[OPEN_DURATION_FIELD] == 1.0


def test_schema_4_and_5_still_require_what_they_required():
    five = yaml.safe_load((CONFIG / "teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml").read_bytes())
    for key in DESCEND_FIELDS:
        missing = dict(five)
        del missing[key]
        with pytest.raises(ValueError, match=INVALID):
            load_document(missing)
    with pytest.raises(ValueError, match=INVALID):
        load_document({**carry_b_document(), DESCEND_DISTANCE_FIELD: 0.02})            # schema 4 is closed without them


def test_the_speed_policy_value_falls_back_for_an_absent_optional_key_of_schema_6_only():
    six = load_document(neutral_document())
    assert speed_policy_value(six, DESCEND_DISTANCE_FIELD, 7.0, since_schema=5) == 7.0
    assert speed_policy_value(six, OPEN_DURATION_FIELD, 2.0, since_schema=5) == 2.0
    assert speed_policy_value(six, "retreat_velocity_scaling", 9.0) == six["retreat_velocity_scaling"]
    five = {**load_teacher_execution_policy(CONFIG / "teacher_execution_policy_side_wrist_fast_two_leg_open_1s.yaml")}
    del five[DESCEND_DISTANCE_FIELD]
    with pytest.raises(RuntimeError, match="TEACHER_POLICY_UNAVAILABLE"):
        speed_policy_value(five, DESCEND_DISTANCE_FIELD, 7.0, since_schema=5)


def test_neutral_ranges_are_allowed_and_derive_neutral_values():
    diversity = td.parse_diversity(copy.deepcopy(NEUTRAL))
    values = td.derive_episode_values(diversity, "act-0001")
    assert values["start_pose"]["offsets_rad"] == [0.0] * 5 and values["pregrasp_height_offset_m"] == 0.0
    assert values["place_approach_height_offset_m"] == 0.0 and values["carry_via_offset_m"] == [0.0, 0.0, 0.0] and values["speed_scale"] == 1.0
    td.validate_episode_values(diversity, values, expect_derived=True)


# ---- the shipped carry_b + diversity file --------------------------------------------------------------------------------------

def test_the_shipped_carry_b_diversity_file_is_carry_b_plus_the_agreed_block():
    shipped = yaml.safe_load(CARRY_B_DIVERSITY.read_bytes())
    base = carry_b_document()
    assert {k: v for k, v in shipped.items() if k not in ("schema_version", "diversity")} == {k: v for k, v in base.items() if k != "schema_version"}
    assert shipped["schema_version"] == 6
    loaded = load_teacher_execution_policy(CARRY_B_DIVERSITY)
    diversity = loaded["diversity"]
    assert diversity["start_pose"]["half_range_rad"] == 0.15 and diversity["pregrasp_height"]["half_range_m"] == 0.015
    assert diversity["place_approach_height"]["half_range_m"] == 0.015 and diversity["carry_via"]["half_extent_m"] == [0.03, 0.03, 0.03]
    assert (diversity["speed_scale"]["low"], diversity["speed_scale"]["high"]) == (0.7, 1.3) and diversity["ompl"]["num_planning_attempts"] == 1
    assert not set(DESCEND_FIELDS) & set(loaded) and OPEN_DURATION_FIELD not in loaded


def test_the_two_leg_diversity_example_is_marked_experimental_and_not_under_its_old_name():
    assert not (CONFIG / "teacher_execution_policy_side_wrist_diversity.yaml").exists()
    text = (CONFIG / "teacher_execution_policy_side_wrist_experimental_two_leg_diversity.yaml").read_text()
    assert "EXPERIMENTAL" in text and "EXP-635" in text


# ---- the Teacher on a neutral schema 6 policy plans like carry_b --------------------------------------------------------------

def adapter(tmp_path, ik, template, targets, path):
    return teacher(tmp_path, ik, template, targets, policy_path=path)


def neutral_path(tmp_path):
    path = tmp_path / "teacher_execution_policy_neutral6.yaml"
    path.write_text(yaml.safe_dump(neutral_document()))
    return path


def test_descend_is_six_interpolated_waypoints_for_carry_b_and_for_neutral_schema_6(tmp_path, ik, template, targets):
    base = adapter(tmp_path, ik, template, targets, CARRY_B)
    six = adapter(tmp_path, ik, template, targets, neutral_path(tmp_path))
    assert base._descend_final_distance_m() is None and six._descend_final_distance_m() is None
    start, grasp = targets.for_state(State.MOVE_ABOVE_OBJECT), targets.for_state(State.DESCEND)
    expected = [base._interpolate_pose(start, grasp, k / 6.0) for k in range(1, 7)]
    assert base._motion_waypoints(State.DESCEND, start, grasp) == expected == six._motion_waypoints(State.DESCEND, start, grasp)
    # the pick-prefix horizon is the six-segment one
    steps = six._motion_horizon(State.DESCEND, [], START)
    assert [step.waypoint.segment_index for step in steps] == [1, 2, 3, 4, 5, 6]


def test_every_state_plans_with_the_scaling_of_carry_b_under_neutral_diversity(tmp_path):
    def scalings(path, speed_scale=None):
        value = make_adapter(tmp_path)
        value._template = SimpleNamespace(velocity_scaling=0.03, acceleration_scaling=0.03)
        value._execution_snapshot_root = tmp_path
        value._execution_policy = load_teacher_execution_policy(path)
        if speed_scale is not None:
            value._episode_diversity = {"speed_scale": speed_scale}
        value._descend_grasp_target = None
        step = SimpleNamespace(waypoint=SimpleNamespace(target=None))
        return {state: value._planning_scaling(state, step) for state in State if state.name.startswith(("MOVE", "DESCEND", "LIFT", "RETREAT", "MICRO"))}

    assert scalings(CARRY_B) == scalings(neutral_path(tmp_path), speed_scale=1.0)


def test_the_gripper_commands_keep_two_seconds_without_the_optional_duration(tmp_path):
    for path in (CARRY_B, neutral_path(tmp_path)):
        value = make_adapter(tmp_path)
        value._execution_snapshot_root = tmp_path
        value._execution_policy = load_teacher_execution_policy(path)
        assert [value._gripper_duration_s(state) for state in (State.OPEN_GRIPPER, State.CLOSE_GRIPPER)] == [2.0, 2.0]
        assert value._gripper_duration_s(State.PREPARE_OPEN_GRIPPER) == value._execution_policy["prepare_open_gripper_duration_s"]


def test_the_frozen_descend_distance_is_none_for_schema_6_without_it_and_read_when_present():
    from so101_demo.ros.dynamic_runtime import _frozen_descend_final_distance_m

    def frozen(**values):
        return {"teacher_execution_policy": {"values": {"schema_version": 6, **values}}}

    assert _frozen_descend_final_distance_m(frozen()) is None
    assert _frozen_descend_final_distance_m(frozen(**{DESCEND_DISTANCE_FIELD: 0.02})) == 0.02
    with pytest.raises(RuntimeError, match="TEACHER_POLICY_UNAVAILABLE"):
        _frozen_descend_final_distance_m({"teacher_execution_policy": {"values": {"schema_version": 5}}})


def test_neutral_diversity_gives_the_targets_and_waypoints_of_carry_b(tmp_path, ik, template, targets):
    """Derived values of the neutral block are zero; the episode template is the template and the targets are the targets (the via-point
    at zero offset is the midpoint of the line, so the two legs reproduce the six interpolated waypoints up to rounding)."""
    values = td.values_for_policy(load_document(neutral_document()), "act-0001")
    assert td.episode_template(template, values) == template
    via_targets = resolve_motion_targets(SAMPLE, template, carry_via_offset_m=tuple(values["carry_via_offset_m"]))
    plain = resolve_motion_targets(SAMPLE, template)
    assert dict(via_targets.targets) == dict(plain.targets)
    value = adapter(tmp_path, ik, template, via_targets, neutral_path(tmp_path))
    base = adapter(tmp_path, ik, template, plain, CARRY_B)
    start = plain.for_state(State.LIFT)                # the carry starts at the end of LIFT: the via-point at zero offset is the midpoint of the line
    target = plain.for_state(State.MOVE_ABOVE_PLACE)
    with_via = value._motion_waypoints(State.MOVE_ABOVE_PLACE, start, target)
    without = base._motion_waypoints(State.MOVE_ABOVE_PLACE, start, target)
    assert len(with_via) == len(without) == 6
    for a, b in zip(with_via, without):
        assert math.dist(a.position_m, b.position_m) < 1e-9
        # the orientation is a normalised linear blend, applied in two steps through the midpoint: equal to well under a milliradian
        assert max(abs(x - y) for x, y in zip(a.orientation_xyzw, b.orientation_xyzw)) < 1e-3
