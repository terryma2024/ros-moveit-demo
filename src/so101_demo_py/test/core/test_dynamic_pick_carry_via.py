"""R3-a: the carry via-point of the dynamic pick targets, and the per-episode template.

Without a via offset nothing changes (the schema 3, 4 and 5 behaviour); with one, MOVE_ABOVE_PLACE carries a via-point between the lift
and above-place targets, and every other target is the one it always was."""

import dataclasses

import pytest

from so101_demo.act import teacher_diversity as td
from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import DynamicPickError, resolve_motion_targets
from test_dynamic_pick import _sample, _template


def test_without_a_via_offset_the_targets_are_the_ones_they_always_were():
    targets = resolve_motion_targets(_sample(), _template())
    assert targets.carry_via is None
    assert targets.for_state(State.MOVE_ABOVE_PLACE).position_m == pytest.approx((0.19, -0.18, 0.28))
    assert targets.for_state(State.LIFT).position_m == pytest.approx((0.02, -0.28, 0.30))
    explicit = resolve_motion_targets(_sample(), _template(), carry_via_offset_m=None)
    assert dict(explicit.targets) == dict(targets.targets) and explicit.carry_via is None


def test_the_via_point_is_the_lift_above_place_midpoint_plus_the_offset():
    targets = resolve_motion_targets(_sample(), _template(), carry_via_offset_m=(0.01, -0.02, 0.03))
    lift = targets.for_state(State.LIFT).position_m
    above = targets.for_state(State.MOVE_ABOVE_PLACE).position_m
    via = targets.carry_via.position_m
    assert via == pytest.approx(tuple((a + b) / 2 + o for a, b, o in zip(lift, above, (0.01, -0.02, 0.03))))
    # the orientation is the interpolation of the two targets' (both identity here)
    assert targets.carry_via.orientation_xyzw == pytest.approx((0.0, 0.0, 0.0, 1.0))


def test_a_via_offset_changes_no_other_target():
    plain = resolve_motion_targets(_sample(), _template())
    with_via = resolve_motion_targets(_sample(), _template(), carry_via_offset_m=(0.03, 0.03, -0.03))
    assert dict(with_via.targets) == dict(plain.targets)


def test_a_via_point_outside_the_workspace_is_refused():
    with pytest.raises(DynamicPickError, match="CUP_POSE_OUT_OF_WORKSPACE"):
        resolve_motion_targets(_sample(), _template(), carry_via_offset_m=(0.0, 0.0, 0.5))


@pytest.mark.parametrize("offset", [(0.0, 0.0), (0.0, 0.0, float("nan")), "abc", (0.0, 0.0, True)])
def test_a_malformed_via_offset_is_refused(offset):
    with pytest.raises(DynamicPickError, match="DYNAMIC_PICK_INVALID"):
        resolve_motion_targets(_sample(), _template(), carry_via_offset_m=offset)


def test_the_episode_template_shifts_only_the_two_clearances():
    template = _template()
    values = {"pregrasp_height_offset_m": 0.012, "place_approach_height_offset_m": -0.014}
    shifted = td.episode_template(template, values)
    assert shifted.pregrasp_world_z_clearance_m == pytest.approx(template.pregrasp_world_z_clearance_m + 0.012)
    assert shifted.place_approach_world_z_clearance_m == pytest.approx(template.place_approach_world_z_clearance_m - 0.014)
    for field in dataclasses.fields(template):
        if field.name not in ("pregrasp_world_z_clearance_m", "place_approach_world_z_clearance_m"):
            assert getattr(shifted, field.name) == getattr(template, field.name), field.name
    targets = resolve_motion_targets(_sample(), shifted)
    plain = resolve_motion_targets(_sample(), template)
    assert targets.for_state(State.MOVE_ABOVE_OBJECT).position_m[2] == pytest.approx(
        plain.for_state(State.MOVE_ABOVE_OBJECT).position_m[2] + 0.012)
    assert targets.for_state(State.MOVE_ABOVE_PLACE).position_m[2] == pytest.approx(
        plain.for_state(State.MOVE_ABOVE_PLACE).position_m[2] - 0.014)
    # the endpoint targets (the grasp and the place pose) do not move
    for state in (State.DESCEND, State.DESCEND_TO_PLACE, State.LIFT, State.RETREAT):
        assert targets.for_state(state) == plain.for_state(state)
