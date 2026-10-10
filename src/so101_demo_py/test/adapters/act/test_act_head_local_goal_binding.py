"""Exact original CDR and every decoded FollowJointTrajectory Goal field are bound."""

import copy
import hashlib
import json

import pytest

from control_msgs.action import FollowJointTrajectory
from control_msgs.msg import JointTolerance
from rclpy.serialization import serialize_message
from rosidl_runtime_py.convert import message_to_ordereddict
from trajectory_msgs.msg import JointTrajectoryPoint


def binding():
    from so101_demo.adapters.act.head_goal_binding import validate_goal_inventory
    from so101_demo.act.head_evidence_identity import canonical_bytes
    message = FollowJointTrajectory.Goal()
    message.trajectory.joint_names = ['neck_yaw_joint']
    message.trajectory.header.frame_id = 'arm_base'
    message.trajectory.points.append(JointTrajectoryPoint(
        positions=[0.15], velocities=[0.0], accelerations=[0.0], effort=[0.0]))
    tolerance = JointTolerance(name='neck_yaw_joint', position=0.1,
        velocity=0.2, acceleration=0.3)
    message.path_tolerance.append(tolerance)
    message.goal_tolerance.append(JointTolerance(name='neck_yaw_joint', position=0.04,
        velocity=0.05, acceleration=0.06))
    message.goal_time_tolerance.sec = 1
    payload = serialize_message(message)
    typed = json.loads(canonical_bytes(message_to_ordereddict(message)))
    record = {'goal_uuid': '00000000-0000-4000-8000-000000000001', 'typed_goal': typed,
        'payload_sha256': hashlib.sha256(payload).hexdigest(), 'generation': 11,
        'controller_identity': {'generation': 11, 'incarnation': 'controller', 'boot': 'boot-1'},
        'attempt_epoch': 'attempt', 'session_id': 'session', 'role': 'neck',
        'operation_sequence': 1, 'claim_monotonic_ns': 100,
        'deadline_ns': 400_000_100}
    return validate_goal_inventory, record, payload


def test_neutral_goal_binding_accepts_complete_original_cdr_and_typed_identity():
    validate, record, payload = binding()
    assert validate(record, payload) == record


def test_neutral_goal_binding_refuses_wrong_original_cdr_digest():
    validate, record, payload = binding()
    damaged = dict(record, payload_sha256='f' * 64)
    with pytest.raises(ValueError, match='BINDING_REFUSED'):
        validate(damaged, payload)


@pytest.mark.parametrize('field,value', [
    ('frame_id', 'other_frame'),
    ('joint_names', ['other_joint']),
    ('path_position', 0.2),
    ('goal_velocity', 0.07),
    ('goal_time', 2),
    ('point_position', 0.25),
])
def test_neutral_goal_binding_refuses_change_to_any_decoded_goal_section(field, value):
    validate, record, payload = binding()
    damaged = copy.deepcopy(record)
    if field == 'frame_id': damaged['typed_goal']['trajectory']['header']['frame_id'] = value
    elif field == 'joint_names': damaged['typed_goal']['trajectory']['joint_names'] = value
    elif field == 'path_position': damaged['typed_goal']['path_tolerance'][0]['position'] = value
    elif field == 'goal_velocity': damaged['typed_goal']['goal_tolerance'][0]['velocity'] = value
    elif field == 'goal_time': damaged['typed_goal']['goal_time_tolerance']['sec'] = value
    else: damaged['typed_goal']['trajectory']['points'][0]['positions'][0] = value
    with pytest.raises(ValueError, match='BINDING_REFUSED'):
        validate(damaged, payload)


def test_neutral_goal_binding_rejects_unbounded_or_non_json_record_values():
    validate, record, payload = binding()
    damaged = copy.deepcopy(record)
    damaged['typed_goal']['trajectory']['header']['frame_id'] = float('nan')
    with pytest.raises(ValueError, match='BINDING_REFUSED'):
        validate(damaged, payload)
