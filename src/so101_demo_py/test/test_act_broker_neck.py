"""The common ACT broker owns neck search and proves its physical stop."""

import math
import threading
from types import SimpleNamespace

import pytest
from control_msgs.action import FollowJointTrajectory
from trajectory_msgs.msg import JointTrajectoryPoint

from so101_demo.adapters.act.leased_action_client import ACTIONS, message_dict
from so101_demo.adapters.act.ros_broker import ACTION_TYPES, RosBrokerDriver, validated_goal


def test_neck_is_a_closed_broker_action_with_bounded_goal():
    assert ACTIONS['/neck_controller/follow_joint_trajectory'] == 'neck'
    assert ACTION_TYPES['neck'] is FollowJointTrajectory
    goal = FollowJointTrajectory.Goal()
    goal.trajectory.joint_names = ['neck_yaw_joint']
    start = JointTrajectoryPoint(positions=[0.])
    target = JointTrajectoryPoint(positions=[2 * math.pi])
    target.time_from_start.sec = 1
    goal.trajectory.points = [start, target]
    assert validated_goal('neck', message_dict(goal)).trajectory.joint_names == ['neck_yaw_joint']
    target.positions = [2 * math.pi + 0.001]
    with pytest.raises(ValueError, match='JOINT_LIMIT_INVALID'):
        validated_goal('neck', message_dict(goal))


def test_common_stop_needs_fresh_stationary_neck_even_if_arm_is_still():
    driver = object.__new__(RosBrokerDriver)
    driver.monotonic = lambda: 10.
    driver.max_age = 1.5
    driver.stop_velocity = .002
    driver._lock = threading.RLock()
    driver._records = {}
    driver._pending_writes = []
    driver._cancel_all = []
    driver._received = 10.
    driver._velocity = (0.,) * 6
    driver._neck_velocity = .01
    driver._statuses = {}
    driver._stop_confirmed_at = 10.
    driver.clients = {kind: SimpleNamespace(server_is_ready=lambda: True) for kind in ACTION_TYPES}
    assert not driver.stopped()
    driver._neck_velocity = 0.
    assert driver.stopped()
    driver._neck_velocity = None
    assert not driver.stopped()
