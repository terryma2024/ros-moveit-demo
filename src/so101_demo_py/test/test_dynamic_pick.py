import math

import pytest

from so101_demo.core.domain import State
from so101_demo.core.task_geometry import Pose7


def _template():
    from so101_demo.core.dynamic_pick import DynamicPickTemplate

    return DynamicPickTemplate(
        policy_id="dynamic_cup_pick",
        planning_frame="world",
        object_id="plastic_cup",
        planning_group="arm",
        arm_joint_names=("1", "2", "3", "4", "5"),
        tcp_link="so101_tcp",
        cup_to_tcp_grasp=Pose7((0.0, 0.0, 0.035, 0.0, 0.0, 0.0, 1.0)),
        pregrasp_world_z_clearance_m=0.08,
        micro_lift_world_z_clearance_m=0.02,
        lift_world_z_clearance_m=0.10,
        place_tcp_world=Pose7((0.19, -0.18, 0.20, 0.0, 0.0, 0.0, 1.0)),
        place_approach_world_z_clearance_m=0.08,
        retreat_world_z_clearance_m=0.10,
        workspace_bounds_m=(-0.30, -0.50, 0.10, 0.35, 0.20, 0.50),
        maximum_source_age_s=0.20,
        maximum_future_skew_s=0.02,
        scene_position_tolerance_m=0.01,
        scene_orientation_tolerance_rad=0.10,
        position_tolerance_m=0.002,
        orientation_tolerance_rad=(0.10, 0.10, 0.10),
        planning_timeout_s=5.0,
        velocity_scaling=0.03,
        acceleration_scaling=0.03,
    )


def _sample(x: float = 0.02):
    from so101_demo.core.dynamic_pick import CupPoseSample

    return CupPoseSample(
        frame_id="world",
        source_stamp_ns=1_000_000_000,
        received_monotonic_s=3.0,
        pose_world=Pose7((x, -0.28, 0.165, 0.0, 0.0, 0.0, 1.0)),
    )


def test_resolves_complete_forward_and_recovery_motion_targets() -> None:
    from so101_demo.core.dynamic_pick import DYNAMIC_MOTION_STATES, resolve_motion_targets

    targets = resolve_motion_targets(_sample(), _template())

    assert set(targets.targets) == DYNAMIC_MOTION_STATES
    assert targets.for_state(State.MOVE_ABOVE_OBJECT).position_m == pytest.approx(
        (0.02, -0.28, 0.28)
    )
    assert targets.for_state(State.DESCEND).position_m == pytest.approx((0.02, -0.28, 0.20))
    assert targets.for_state(State.MICRO_LIFT).position_m == pytest.approx(
        (0.02, -0.28, 0.22)
    )
    assert targets.for_state(State.LIFT).position_m == pytest.approx((0.02, -0.28, 0.30))


def test_cup_translation_changes_every_pick_family_target_by_same_amount() -> None:
    from so101_demo.core.dynamic_pick import resolve_motion_targets

    left = resolve_motion_targets(_sample(0.02), _template())
    right = resolve_motion_targets(_sample(0.12), _template())

    for state in (State.MOVE_ABOVE_OBJECT, State.DESCEND, State.MICRO_LIFT, State.LIFT):
        assert right.for_state(state).position_m[0] - left.for_state(state).position_m[
            0
        ] == pytest.approx(
            0.10
        )


def test_pose_composition_rotates_cup_relative_translation() -> None:
    from so101_demo.core.dynamic_pick import compose_pose

    half_turn = math.sqrt(0.5)
    result = compose_pose(
        Pose7((1.0, 2.0, 3.0, 0.0, 0.0, half_turn, half_turn)),
        Pose7((0.10, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)),
    )

    assert result.values[:3] == pytest.approx((1.0, 2.1, 3.0))
    assert math.sqrt(sum(value * value for value in result.values[3:])) == pytest.approx(1.0)


def test_pose_inverse_recovers_parent_pose_for_place_validation() -> None:
    from so101_demo.core.dynamic_pick import compose_pose, inverse_pose

    parent = Pose7((0.1, -0.2, 0.3, 0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5)))
    child = Pose7((0.02, 0.03, 0.04, 0.1, 0.2, 0.3, 0.9))
    composed = compose_pose(parent, child)

    recovered = compose_pose(composed, inverse_pose(child))

    assert recovered.values == pytest.approx(parent.values)


def test_rejects_a_resolved_target_outside_workspace() -> None:
    from so101_demo.core.dynamic_pick import DynamicPickError, resolve_motion_targets

    with pytest.raises(DynamicPickError, match="CUP_POSE_OUT_OF_WORKSPACE"):
        resolve_motion_targets(_sample(0.50), _template())
