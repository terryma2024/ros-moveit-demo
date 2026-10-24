"""R3-a: the Teacher diversity block, its deterministic per-episode derivation and its range checks (pure, standalone)."""

from __future__ import annotations

import copy
import math

import pytest

from so101_demo.act import teacher_diversity as td

SEED = 20261024
BLOCK = {
    "campaign_seed": SEED,
    "start_pose": {"distribution": "uniform", "half_range_rad": 0.15, "max_redraws": 8},
    "pregrasp_height": {"distribution": "uniform", "half_range_m": 0.015},
    "place_approach_height": {"distribution": "uniform", "half_range_m": 0.015},
    "carry_via": {"distribution": "uniform_box", "half_extent_m": [0.03, 0.03, 0.03]},
    "speed_scale": {"distribution": "uniform", "low": 0.7, "high": 1.3},
    "ompl": {"num_planning_attempts": 3},
}
INVALID = "TEACHER_DIVERSITY_INVALID"


def block(**changes):
    document = copy.deepcopy(BLOCK)
    for key, value in changes.items():
        document[key] = value
    return document


@pytest.fixture()
def diversity():
    return td.parse_diversity(copy.deepcopy(BLOCK))


def test_the_default_block_parses_and_is_canonical(diversity):
    assert diversity["campaign_seed"] == SEED
    assert diversity["start_pose"]["half_range_rad"] == 0.15 and diversity["start_pose"]["max_redraws"] == 8
    assert diversity["carry_via"]["half_extent_m"] == [0.03, 0.03, 0.03]
    assert diversity["speed_scale"] == {"distribution": "uniform", "low": 0.7, "high": 1.3}
    assert diversity["ompl"] == {"num_planning_attempts": 3}
    assert td.parse_diversity(diversity) == diversity            # parsing a parsed block changes nothing


@pytest.mark.parametrize("mutate", [
    lambda b: b.pop("campaign_seed"), lambda b: b.pop("ompl"), lambda b: b.update(invented=1),
    lambda b: b["start_pose"].update(invented=1), lambda b: b["start_pose"].pop("max_redraws"),
    lambda b: b["speed_scale"].pop("low"),
])
def test_the_block_is_closed(mutate):
    document = copy.deepcopy(BLOCK)
    mutate(document)
    with pytest.raises(ValueError, match=INVALID):
        td.parse_diversity(document)


@pytest.mark.parametrize("path,value", [
    (("campaign_seed",), -1), (("campaign_seed",), 1.5), (("campaign_seed",), True), (("campaign_seed",), "7"),
    (("campaign_seed",), 2 ** 63),
    (("start_pose", "distribution"), "normal"),
    (("start_pose", "half_range_rad"), 0.0), (("start_pose", "half_range_rad"), -0.1), (("start_pose", "half_range_rad"), 0.31),
    (("start_pose", "half_range_rad"), float("nan")), (("start_pose", "half_range_rad"), True),
    (("start_pose", "max_redraws"), 0), (("start_pose", "max_redraws"), 33), (("start_pose", "max_redraws"), 2.0),
    (("pregrasp_height", "half_range_m"), -0.001), (("pregrasp_height", "half_range_m"), 0.031),
    (("pregrasp_height", "half_range_m"), float("inf")),
    (("place_approach_height", "half_range_m"), 0.031),
    (("carry_via", "half_extent_m"), [0.03, 0.03]), (("carry_via", "half_extent_m"), [0.03, 0.03, 0.061]),
    (("carry_via", "half_extent_m"), [0.03, -0.01, 0.03]), (("carry_via", "half_extent_m"), 0.03),
    (("carry_via", "distribution"), "uniform"),
    (("speed_scale", "low"), 0.49), (("speed_scale", "low"), 1.01), (("speed_scale", "high"), 0.99),
    (("speed_scale", "high"), 1.51), (("speed_scale",), {"distribution": "uniform", "low": 0.9, "high": 0.8}),
    (("ompl", "num_planning_attempts"), 0), (("ompl", "num_planning_attempts"), 11), (("ompl", "num_planning_attempts"), 2.0),
    (("ompl", "num_planning_attempts"), True),
])
def test_out_of_range_or_mistyped_policy_values_are_refused_at_load(path, value):
    document = copy.deepcopy(BLOCK)
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    with pytest.raises(ValueError, match=INVALID):
        td.parse_diversity(document)


def test_a_zero_width_height_axis_is_allowed_and_switches_that_axis_off():
    parsed = td.parse_diversity(block(pregrasp_height={"distribution": "uniform", "half_range_m": 0.0}))
    values = td.derive_episode_values(parsed, "scene-1")
    assert values["pregrasp_height_offset_m"] == 0.0


def test_the_derivation_is_deterministic_and_has_the_closed_shape(diversity):
    first = td.derive_episode_values(diversity, "act-0001")
    second = td.derive_episode_values(copy.deepcopy(diversity), "act-0001")
    assert first == second
    assert set(first) == {"schema", "scene_id", "campaign_seed", "start_pose", "pregrasp_height_offset_m",
                          "place_approach_height_offset_m", "carry_via_offset_m", "speed_scale", "ompl"}
    assert first["scene_id"] == "act-0001" and first["campaign_seed"] == SEED
    assert set(first["start_pose"]) == {"draw_index", "joints", "offsets_rad"}
    assert first["start_pose"]["draw_index"] == 0 and first["start_pose"]["joints"] == ["1", "2", "3", "4", "5"]
    assert len(first["start_pose"]["offsets_rad"]) == 5 and len(first["carry_via_offset_m"]) == 3
    assert set(first["ompl"]) == {"num_planning_attempts", "seed", "seed_applied"}
    assert first["ompl"]["num_planning_attempts"] == 3 and first["ompl"]["seed_applied"] is False


def test_the_derivation_is_pinned_to_a_golden_value(diversity):
    """The hash-to-uniform recipe is part of the run identity: changing it changes every episode of every campaign."""
    values = td.derive_episode_values(diversity, "act-0001")
    assert values == GOLDEN_ACT_0001


def test_scene_and_campaign_seed_change_the_values(diversity):
    base = td.derive_episode_values(diversity, "act-0001")
    assert td.derive_episode_values(diversity, "act-0002") != base
    other = td.parse_diversity(block(campaign_seed=SEED + 1))
    assert td.derive_episode_values(other, "act-0001") != base


def test_every_derived_value_lies_inside_the_declared_ranges_over_many_scenes(diversity):
    seen_signs = set()
    for number in range(300):
        values = td.derive_episode_values(diversity, f"act-{number:04d}")
        td.validate_episode_values(diversity, values)                 # does not raise
        assert all(abs(v) <= 0.15 for v in values["start_pose"]["offsets_rad"])
        assert abs(values["pregrasp_height_offset_m"]) <= 0.015 and abs(values["place_approach_height_offset_m"]) <= 0.015
        assert all(abs(v) <= 0.03 for v in values["carry_via_offset_m"])
        assert 0.7 <= values["speed_scale"] <= 1.3
        seen_signs.add(values["start_pose"]["offsets_rad"][0] > 0)
    assert seen_signs == {True, False}                                # it really varies


def test_the_axes_are_drawn_independently(diversity):
    values = [td.derive_episode_values(diversity, f"s{n}") for n in range(50)]
    assert len({v["pregrasp_height_offset_m"] for v in values}) == 50
    assert len({v["speed_scale"] for v in values}) == 50
    assert len({v["pregrasp_height_offset_m"] for v in values} & {v["place_approach_height_offset_m"] for v in values}) == 0


@pytest.mark.parametrize("mutate", [
    lambda v: v["start_pose"]["offsets_rad"].__setitem__(0, 0.151),
    lambda v: v.__setitem__("pregrasp_height_offset_m", 0.0151),
    lambda v: v.__setitem__("place_approach_height_offset_m", -0.016),
    lambda v: v["carry_via_offset_m"].__setitem__(2, 0.031),
    lambda v: v.__setitem__("speed_scale", 1.31), lambda v: v.__setitem__("speed_scale", 0.69),
    lambda v: v.__setitem__("speed_scale", float("nan")),
    lambda v: v["ompl"].__setitem__("num_planning_attempts", 4),
    lambda v: v.__setitem__("campaign_seed", 1), lambda v: v.__setitem__("scene_id", ""),
    lambda v: v["start_pose"].__setitem__("draw_index", 9), lambda v: v["start_pose"]["offsets_rad"].append(0.0),
    lambda v: v.__setitem__("invented", 1), lambda v: v.pop("speed_scale"),
])
def test_derived_values_outside_their_ranges_or_not_the_closed_shape_are_refused(diversity, mutate):
    values = td.derive_episode_values(diversity, "act-0001")
    mutate(values)
    with pytest.raises(ValueError, match=INVALID):
        td.validate_episode_values(diversity, values)


def test_values_that_disagree_with_their_own_derivation_are_refused(diversity):
    values = td.derive_episode_values(diversity, "act-0001")
    values["speed_scale"] = 1.0                                       # in range, but not what (seed, scene) derive
    with pytest.raises(ValueError, match=INVALID):
        td.validate_episode_values(diversity, values, expect_derived=True)


def test_start_pose_candidates_begin_with_the_derived_draw_and_are_bounded(diversity):
    candidates = td.start_pose_candidates(diversity, "act-0001")
    assert len(candidates) == 9 and candidates[0] == tuple(td.derive_episode_values(diversity, "act-0001")["start_pose"]["offsets_rad"])
    assert len(set(candidates)) == 9
    assert all(len(c) == 5 and all(abs(v) <= 0.15 for v in c) for c in candidates)


def test_select_start_pose_takes_the_first_accepted_draw_and_records_the_rejections(diversity):
    candidates = td.start_pose_candidates(diversity, "act-0001")
    rejected_first_two = {candidates[0], candidates[1]}
    chosen = td.select_start_pose(diversity, "act-0001", lambda offsets: (offsets not in rejected_first_two, "pose-check"))
    assert chosen["draw_index"] == 2 and chosen["offsets_rad"] == list(candidates[2])
    assert [item["draw_index"] for item in chosen["rejected"]] == [0, 1]
    assert all(item["reason"] == "pose-check" for item in chosen["rejected"])


def test_select_start_pose_fails_closed_after_the_bounded_number_of_redraws(diversity):
    calls = []

    def always_reject(offsets):
        calls.append(offsets)
        return False, "collision"

    with pytest.raises(ValueError, match="TEACHER_DIVERSITY_START_POSE_REJECTED"):
        td.select_start_pose(diversity, "act-0001", always_reject)
    assert len(calls) == 9                                            # max_redraws + the first draw, and not one more


def test_the_measured_start_pose_is_matched_back_to_its_draw(diversity):
    candidates = td.start_pose_candidates(diversity, "act-0001")
    measured = (*[v + 0.0004 for v in candidates[3]], 0.0)             # the arm settles within a fraction of a milliradian
    assert td.matching_start_draw(diversity, "act-0001", measured) == 3
    assert td.matching_start_draw(diversity, "act-0001", (0.0,) * 6) is None
    assert td.matching_start_draw(diversity, "act-0001", (0.0,) * 5) is None


def test_the_reset_joint_vector_adds_the_offsets_to_the_arm_joints_only(diversity):
    offsets = (0.1, -0.1, 0.05, 0.02, -0.03)
    assert td.reset_joint_positions(offsets, ("1", "2", "3", "4", "5", "6")) == (0.1, -0.1, 0.05, 0.02, -0.03, 0.0)
    assert td.reset_joint_positions(offsets, ("1", "2", "3", "4", "5", "6", "neck_yaw_joint")) == (
        0.1, -0.1, 0.05, 0.02, -0.03, 0.0, 0.0)


def test_joint_limits_are_checked_with_a_margin():
    inside = (0.1, 0.0, 0.0, 0.0, 0.0, 0.0)
    assert td.joints_within_limits(inside, margin_rad=0.02)
    assert not td.joints_within_limits((0.0, 0.0, 1.68, 0.0, 0.0, 0.0), margin_rad=0.02)     # joint 3 limit is 1.69
    assert td.joints_within_limits((0.0, 0.0, 1.68, 0.0, 0.0, 0.0), margin_rad=0.0)
    assert not td.joints_within_limits((float("nan"), 0, 0, 0, 0, 0), margin_rad=0.02)


def test_the_carry_via_point_is_the_lift_to_above_place_midpoint_plus_the_offset():
    lift = ((0.0, 0.1, 0.30), (0.0, 0.0, 0.0, 1.0))
    above = ((0.2, -0.1, 0.20), (0.0, 0.0, 0.0, 1.0))
    position = td.carry_via_position(lift[0], above[0], (0.01, -0.02, 0.03))
    assert position == pytest.approx((0.11, 0.0 - 0.02 + 0.0, 0.25 + 0.03))
    assert td.carry_via_position(lift[0], above[0], (0.0, 0.0, 0.0)) == pytest.approx((0.1, 0.0, 0.25))


def test_the_speed_scale_scales_and_caps_at_one():
    assert td.scaled_scaling(0.1, 1.3) == pytest.approx(0.13)
    assert td.scaled_scaling(0.1, 0.7) == pytest.approx(0.07)
    assert td.scaled_scaling(0.9, 1.3) == 1.0
    assert td.scaled_scaling(1.0, 0.7) == pytest.approx(0.7)
    with pytest.raises(ValueError, match=INVALID):
        td.scaled_scaling(0.1, 0.0)
    with pytest.raises(ValueError, match=INVALID):
        td.scaled_scaling(0.0, 1.0)


# the MuJoCo collision check of the start pose, on a fixture model: a two-link arm over a table, plus a cup on the table
ARM_XML = """
<mujoco>
  <compiler angle="radian"/>
  <worldbody>
    <geom name="table_collision" type="box" size="1 1 0.05" pos="0 0 -0.05"/>
    <body name="base" pos="0 0 0.03">
      <inertial pos="0 0 0" mass="1" diaginertia="0.01 0.01 0.01"/>
      <joint name="1" type="hinge" axis="0 0 1" range="-3 3"/>
      <body name="link" pos="0 0 0">
        <inertial pos="0.1 0 0" mass="1" diaginertia="0.01 0.01 0.01"/>
        <joint name="2" type="hinge" axis="0 1 0" range="-1.7 1.7"/>
        <geom name="arm_link" type="capsule" fromto="0 0 0 0.25 0 0" size="0.02"/>
      </body>
    </body>
    <body name="plastic_cup" pos="0.6 0.6 0.05">
      <freejoint name="cup_free_joint"/>
      <geom name="cup_collision" type="cylinder" size="0.03 0.05"/>
    </body>
  </worldbody>
  <keyframe><key name="task_start" qpos="0 0 0.6 0.6 0.05 1 0 0 0"/></keyframe>
</mujoco>
"""


@pytest.fixture()
def checker():
    pytest.importorskip("mujoco")
    return td.StartPoseCollisionCheck.from_xml_string(ARM_XML, cup_body="plastic_cup", joint_names=("1", "2"))


def test_the_baseline_pose_is_collision_free(checker):
    assert checker.check((0.0, 0.0)) == (True, "")


def test_a_pose_that_drives_the_arm_into_the_table_is_rejected(checker):
    accepted, reason = checker.check((0.0, 0.2))                      # joint 2 rotates the link tip down into the table
    assert accepted is False and reason.startswith("COLLISION:") and "table_collision" in reason


def test_a_pose_beyond_the_model_joint_range_is_rejected_before_any_contact_test(checker):
    accepted, reason = checker.check((0.0, 1.9))
    assert accepted is False and reason.startswith("JOINT_LIMIT:")


def test_the_cup_position_enters_the_check(checker):
    sweeping = (0.0, 0.0)
    assert checker.check(sweeping, cup_position=(0.6, 0.6, 0.05)) == (True, "")
    accepted, reason = checker.check(sweeping, cup_position=(0.12, 0.0, 0.05))   # the cup sits in the arm
    assert accepted is False and "cup_collision" in reason


#: derived once from the recipe `so101-teacher-diversity-v1` (sha256 of "recipe|seed|scene|axis|index|draw", first 8 bytes / 2^64) and pinned
GOLDEN_ACT_0001 = {
    "schema": 1, "scene_id": "act-0001", "campaign_seed": 20261024,
    "start_pose": {"draw_index": 0, "joints": ["1", "2", "3", "4", "5"],
                   "offsets_rad": [0.1254207088368319, -0.019722030860760954, 0.1470936144669786, 0.10952324618889642,
                                   -0.12332865620907094]},
    "pregrasp_height_offset_m": 0.012363921029548615,
    "place_approach_height_offset_m": 0.005297577684898027,
    "carry_via_offset_m": [-0.013135852765072618, 0.019323227120371173, -0.019649629566175938],
    "speed_scale": 1.2144501484832424,
    "ompl": {"num_planning_attempts": 3, "seed": 569365291, "seed_applied": False},
}
