"""Bounded, monitor-neutral CDR and complete typed-goal binding."""

import hashlib
import hmac
import json

from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.convert import message_to_ordereddict

from so101_demo.act.head_evidence_identity import bounded_payload, canonical_bytes, check_deadline


def validate_goal_inventory(record, payload, *, deadline=None):
    """Bind original CDR bytes to every decoded ROS Goal field."""
    try:
        check_deadline(deadline)
        if type(payload) is not bytes or not 0 < len(payload) <= 1_048_576:
            raise ValueError('HEAD_GOAL_CDR_INVALID')
        owned = bounded_payload(record, deadline)
        expected = owned['payload_sha256']
        actual = hashlib.sha256(payload).hexdigest()
        if type(expected) is not str or not hmac.compare_digest(expected, actual):
            raise ValueError('HEAD_GOAL_CDR_DIGEST_MISMATCH')
        check_deadline(deadline)
        message = deserialize_message(payload, FollowJointTrajectory.Goal)
        decoded = message_to_ordereddict(message)
        if decoded['trajectory']['joint_names'] != ['neck_yaw_joint']:
            raise ValueError('HEAD_GOAL_ROLE_INVALID')
        if canonical_bytes(decoded) != canonical_bytes(owned['typed_goal']):
            raise ValueError('HEAD_GOAL_TYPED_IDENTITY_MISMATCH')
        result = json.loads(canonical_bytes(owned))
        check_deadline(deadline)
        return result
    except (KeyError, TypeError, RuntimeError, ValueError, OverflowError) as error:
        raise ValueError('HEAD_GOAL_BINDING_REFUSED') from error
