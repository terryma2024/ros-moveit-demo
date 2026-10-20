"""`clamp_positions`: small joint-limit overshoots are clamped to the limit, larger ones are refused, nothing else changes."""

import pytest

from so101_demo.act.joints import ACT_JOINT_LIMITS, ARM_JOINTS, JOINT_LIMITS, clamp_positions

WRIST_FLEX_HIGH = ACT_JOINT_LIMITS["4"][1]
ELBOW_HIGH = ACT_JOINT_LIMITS["3"][1]
GRIPPER_LOW = ACT_JOINT_LIMITS["6"][0]
INSIDE = (0.0, 0.1, -0.2, 0.3, 0.0, 0.5)


def _row(**changes):
    row = list(INSIDE)
    for index, value in changes.items():
        row[int(index.lstrip("j"))] = value
    return tuple(row)


def test_rows_inside_the_limits_are_returned_unchanged_with_no_clamps():
    rows, clamps = clamp_positions((INSIDE, _row(j1=0.2)), 0.01)
    assert rows == (INSIDE, _row(j1=0.2)) and clamps == []


def test_an_overshoot_within_the_tolerance_is_clamped_to_the_limit_and_recorded():
    original = WRIST_FLEX_HIGH + 0.0019
    rows, clamps = clamp_positions((INSIDE, _row(j3=original)), 0.01)
    assert rows[0] == INSIDE and rows[1][3] == WRIST_FLEX_HIGH
    assert rows[1][:3] == INSIDE[:3] and rows[1][4:] == INSIDE[4:]
    assert clamps == [{"position_index": 1, "joint_index": 3, "joint": ARM_JOINTS[3], "original": original,
                       "clamped": WRIST_FLEX_HIGH, "limit": WRIST_FLEX_HIGH}]


def test_a_low_side_overshoot_is_clamped_to_the_lower_limit():
    rows, clamps = clamp_positions((_row(j5=GRIPPER_LOW - 0.004),), 0.01)
    assert rows[0][5] == GRIPPER_LOW and clamps[0]["joint_index"] == 5 and clamps[0]["clamped"] == GRIPPER_LOW


def test_just_inside_the_tolerance_is_clamped_and_just_above_it_is_refused():
    at = WRIST_FLEX_HIGH + 0.00999
    rows, clamps = clamp_positions((_row(j3=at),), 0.01)
    assert rows[0][3] == WRIST_FLEX_HIGH and len(clamps) == 1
    with pytest.raises(ValueError, match="JOINT_LIMIT_INVALID"):
        clamp_positions((_row(j3=WRIST_FLEX_HIGH + 0.0101),), 0.01)


def test_several_joints_and_positions_are_clamped_together_each_recorded():
    rows, clamps = clamp_positions((_row(j2=ELBOW_HIGH + 0.001, j3=WRIST_FLEX_HIGH + 0.002),
                                    _row(j5=GRIPPER_LOW - 0.003)), 0.01)
    assert (rows[0][2], rows[0][3], rows[1][5]) == (ELBOW_HIGH, WRIST_FLEX_HIGH, GRIPPER_LOW)
    assert [(c["position_index"], c["joint_index"]) for c in clamps] == [(0, 2), (0, 3), (1, 5)]


def test_one_joint_beyond_the_tolerance_refuses_the_whole_prefix_and_clamps_nothing():
    with pytest.raises(ValueError, match="JOINT_LIMIT_INVALID"):
        clamp_positions((_row(j3=WRIST_FLEX_HIGH + 0.002), _row(j2=ELBOW_HIGH + 0.05)), 0.01)


def test_the_profile_selects_the_limit_table():
    # elbow 1.6 is inside the ACT range (1.69) and 0.03 above the main-profile limit (1.5708): beyond the tolerance there
    with pytest.raises(ValueError, match="JOINT_LIMIT_INVALID"):
        clamp_positions((_row(j2=1.6),), 0.01, profile="main")
    rows, _ = clamp_positions((_row(j2=1.6),), 0.01, profile="act")
    assert rows[0][2] == 1.6
    assert JOINT_LIMITS["3"][1] == 1.5708


@pytest.mark.parametrize("tolerance", [0, -0.01, float("nan"), float("inf"), True, "0.01", None])
def test_a_tolerance_that_is_not_a_positive_finite_number_is_refused(tolerance):
    with pytest.raises(ValueError, match="CLAMP_TOLERANCE_INVALID"):
        clamp_positions((INSIDE,), tolerance)
