"""The original controller message is converted when a reader takes the frame, not when the frame is accepted (to-do 2e option 2)."""
import json
import math

import pytest

from control_msgs.msg import JointTrajectoryControllerState
from rosidl_runtime_py.convert import message_to_ordereddict

from so101_demo.adapters.act import controller_reference_observer as module
from so101_demo.adapters.act.controller_reference_observer import ControllerReferenceObserver

from so101_demo.act.joints import ARM_JOINTS

NAMES = tuple(ARM_JOINTS[:5])


def state(stamp_ns, *, seed=0.0):
    message = JointTrajectoryControllerState()
    message.header.stamp.sec, message.header.stamp.nanosec = divmod(stamp_ns, 1_000_000_000)
    message.header.frame_id = "base"
    message.joint_names = list(NAMES)
    for index, point in enumerate((message.reference, message.feedback, message.error, message.output)):
        point.positions = [seed + index + 0.1 * j for j in range(5)]
        point.velocities = [0.01 * j - index for j in range(5)]
        point.accelerations = [0.5 * j for j in range(5)]
        point.effort = [1e-3 * j + seed for j in range(5)]
        point.time_from_start.sec, point.time_from_start.nanosec = index, 5
    return message


def observer():
    watcher = ControllerReferenceObserver(max_frames=256, kinds=("arm",))
    watcher.reset("s", 1, source_floor_ns=1_000_000_000)
    return watcher


def eager(message):
    return json.loads(json.dumps(message_to_ordereddict(message), allow_nan=False))


def test_the_frame_a_reader_takes_equals_the_eager_conversion_and_keeps_the_key_order():
    watcher = observer()
    messages = [state(1_100_000_000 + 2_000_000 * n, seed=n * 0.37) for n in range(60)]
    for number, message in enumerate(messages):
        assert watcher.accept("arm", message, received_monotonic_s=10.0 + number * 0.002)
    _, frames = watcher.recent("arm", now_monotonic_s=10.2, max_wall_age_s=1.0)
    assert len(frames) == 60
    for frame, message in zip(frames, messages):
        assert frame["original_message"] == eager(message)
        assert list(frame) == ["sim_stamp_ns", "received_monotonic_ns", "joint_names", "positions", "velocities", "observer_sequence",
                               "original_message"]
        assert "_message" not in frame
    identity, window = watcher.matching_by_stamp("arm", now_sim_ns=1_100_000_000 + 2_000_000 * 59, window_ns=10**9,
                                                 target_ns=1_100_000_000 + 2_000_000 * 3, tolerance_ns=0)
    assert [item["original_message"] for item in window] == [eager(messages[3])]
    _, by_stamp = watcher.recent_by_stamp("arm", now_sim_ns=1_100_000_000 + 2_000_000 * 59, window_ns=4_000_000)
    assert [item["original_message"] for item in by_stamp] == [eager(m) for m in messages[57:60]]


def test_a_returned_frame_is_a_copy_the_reader_cannot_use_to_change_the_retained_one():
    watcher = observer()
    message = state(1_100_000_000)
    watcher.accept("arm", message, received_monotonic_s=10.0)
    _, first = watcher.recent("arm", now_monotonic_s=10.01, max_wall_age_s=1.0)
    first[0]["original_message"]["feedback"]["positions"][0] = 99.0
    first[0]["positions"]
    _, second = watcher.recent("arm", now_monotonic_s=10.01, max_wall_age_s=1.0)
    assert second[0]["original_message"] == eager(message)


@pytest.mark.parametrize("bad", [math.nan, math.inf, -math.inf])
@pytest.mark.parametrize("where", ["feedback.positions", "error.effort", "output.velocities", "reference.accelerations"])
def test_a_float_json_refuses_is_still_refused_at_accept_with_the_same_hazard_text(where, bad):
    message = state(1_100_000_000)
    point, field = where.split(".")
    getattr(getattr(message, point), field)[1] = bad
    try:
        eager(message)
    except ValueError as error:
        expected = str(error)
    assert expected
    watcher = observer()
    accepted = watcher.accept("arm", message, received_monotonic_s=10.0)
    assert accepted is False and watcher._hazard == expected, (watcher._hazard, expected)


def test_the_plan_covers_every_float_field_of_the_state_message_including_the_multi_dof_points():
    plan = dict(module._plan_of(JointTrajectoryControllerState))
    assert plan["reference"] == "m" and plan["speed_scaling_factor"] == "f" and plan["multi_dof_error"] == "m"
    assert "joint_names" not in plan and "header" in plan
    from trajectory_msgs.msg import JointTrajectoryPoint, MultiDOFJointTrajectoryPoint
    assert dict(module._plan_of(JointTrajectoryPoint)) == {"positions": "fa", "velocities": "fa", "accelerations": "fa", "effort": "fa",
                                                           "time_from_start": "m"}
    assert dict(module._plan_of(MultiDOFJointTrajectoryPoint))["transforms"] == "ma"


@pytest.mark.parametrize("bad", [math.nan, math.inf])
def test_a_non_finite_float_in_a_multi_dof_point_or_the_scaling_factor_is_found(bad):
    from geometry_msgs.msg import Transform
    message = state(1_100_000_000)
    assert module._serialisable(message) is True
    message.speed_scaling_factor = bad
    assert module._serialisable(message) is False
    message.speed_scaling_factor = 1.0
    transform = Transform()
    transform.translation.x = bad
    message.multi_dof_feedback.transforms = [transform]
    assert module._serialisable(message) is False
