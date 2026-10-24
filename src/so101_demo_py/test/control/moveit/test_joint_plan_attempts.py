"""R3-a: the OMPL planning attempts of a joint plan request (MoveIt's request has no planner seed field)."""

import pytest

from so101_demo.control.moveit.planning import JointPlanRequest, MoveItPlanningClient, make_get_motion_plan_request


def _request(**changes):
    return JointPlanRequest(
        joint_names=("1", "2", "3", "4", "5"), current_positions=(0.0,) * 5, target_positions=(0.1,) * 5, **changes)


def test_the_default_is_one_attempt_exactly_as_before():
    request = _request()
    assert request.num_planning_attempts == 1
    wire = make_get_motion_plan_request(request)
    assert wire.motion_plan_request.num_planning_attempts == 1


def test_the_attempts_reach_the_wire_request():
    wire = make_get_motion_plan_request(_request(num_planning_attempts=3))
    assert wire.motion_plan_request.num_planning_attempts == 3


@pytest.mark.parametrize("value", [0, -1, 11, 2.0, True, None, "3"])
def test_attempts_outside_one_to_ten_or_not_integers_are_refused(value):
    with pytest.raises(ValueError, match="planning attempts"):
        _request(num_planning_attempts=value)


def test_the_request_carries_no_seed_field():
    """MoveIt's MotionPlanRequest has no random seed: OMPL seeds its generator once per process. The R3-a seed is therefore recorded, not sent."""
    from moveit_msgs.msg import MotionPlanRequest

    assert not [name for name in MotionPlanRequest.get_fields_and_field_types() if "seed" in name]


def test_a_planning_client_forwards_the_attempts_through_its_default_factory():
    seen = []

    class Future:
        def done(self):
            return True

        def result(self):
            return None

    class Client:
        def wait_for_service(self, timeout_sec):
            return True

        def call_async(self, wire):
            seen.append(wire.motion_plan_request.num_planning_attempts)
            return Future()

    MoveItPlanningClient(Client()).plan_joint_path(_request(num_planning_attempts=4), timeout_s=1.0)
    assert seen == [4]
