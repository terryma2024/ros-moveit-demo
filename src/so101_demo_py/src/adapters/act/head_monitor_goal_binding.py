"""CPU-only complete raw-goal binding before the monitor's inventory ACK.

Run on the operation worker, outside watchdog/cache locks. This validates goal
identity only; epoch/readiness/claim, safe motion and native admission remain
separate guards. No action or ROS node is created here.
"""

import hashlib
import hmac
import json

from control_msgs.action import FollowJointTrajectory
from rclpy.serialization import deserialize_message
from rosidl_runtime_py.convert import message_to_ordereddict

from so101_demo.act.head_monitor import canonical_bytes
from so101_demo.act.head_monitor_ipc import _bounded_payload, _check_deadline


def validate_goal_inventory(record, payload, *, deadline=None):
    """Own the record and compare every decoded ROS field and raw-byte digest."""
    try:
        _check_deadline(deadline)
        if type(payload) is not bytes or not 0 < len(payload) <= 1_048_576:
            raise ValueError('HEAD_MONITOR_CDR_INVALID')
        owned = _bounded_payload(record, deadline)
        expected = owned['payload_sha256']
        actual = hashlib.sha256(payload).hexdigest()
        if type(expected) is not str or not hmac.compare_digest(expected, actual):
            raise ValueError('HEAD_MONITOR_CDR_DIGEST_MISMATCH')
        _check_deadline(deadline)
        message = deserialize_message(payload, FollowJointTrajectory.Goal)
        decoded = message_to_ordereddict(message)
        if decoded['trajectory']['joint_names'] != ['neck_yaw_joint']:
            raise ValueError('HEAD_MONITOR_CDR_ROLE_INVALID')
        # No abbreviated arrays, omitted defaults, float coercion, or partial
        # goal descriptions: canonical bytes also distinguish bool from int.
        if canonical_bytes(decoded) != canonical_bytes(owned['typed_goal']):
            raise ValueError('HEAD_MONITOR_CDR_TYPED_GOAL_MISMATCH')
        result = json.loads(canonical_bytes(owned))
        _check_deadline(deadline)
        return result
    except (KeyError, TypeError, RuntimeError, ValueError, OverflowError) as error:
        raise ValueError('HEAD_MONITOR_CDR_BINDING_REFUSED') from error
