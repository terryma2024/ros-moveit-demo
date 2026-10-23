"""The scan reads `header.stamp` from the first bytes of the CDR body instead of deserialising (to-do 2e option 1)."""
import random

import pytest

from rclpy.serialization import deserialize_message, serialize_message
from control_msgs.msg import JointTrajectoryControllerState
from sensor_msgs.msg import CameraInfo, Image, JointState
from std_msgs.msg import String

from so101_demo.act.offline import scan


def stamped(message, sec, nanosec):
    message.header.stamp.sec, message.header.stamp.nanosec = sec, nanosec
    return message


@pytest.mark.parametrize("cls", [JointTrajectoryControllerState, CameraInfo, Image, JointState])
def test_the_fast_stamp_equals_the_deserialised_stamp(cls):
    assert scan._starts_with_header(cls)
    rng = random.Random(7)
    cases = [(0, 0), (1, 999_999_999), (2**31 - 1, 999_999_999), (-5, 3), (-(2**31), 0), (104, 20_000_000)]
    cases += [(rng.randrange(0, 10**6), rng.randrange(0, 10**9)) for _ in range(200)]
    for sec, nanosec in cases:
        message = stamped(cls(), sec, nanosec)
        if cls is Image:
            message.data = bytes(range(256)) * 3
            message.header.frame_id = "wrist_camera_optical"
        if cls is JointState:
            message.name = ["a", "b"]
            message.position = [0.5, 0.25]
        data = serialize_message(message)
        full = deserialize_message(data, cls)
        assert scan._header_stamp_ns(data) == int(full.header.stamp.sec) * 10**9 + int(full.header.stamp.nanosec)


def test_a_message_without_a_leading_header_or_a_foreign_encapsulation_takes_the_full_path():
    assert not scan._starts_with_header(String)
    data = serialize_message(stamped(JointState(), 3, 4))
    assert scan._header_stamp_ns(b"\x00\x00" + data[2:]) is None        # big endian
    assert scan._header_stamp_ns(b"\x00\x07" + data[2:]) is None        # XCDR2
    assert scan._header_stamp_ns(data[:11]) is None                     # truncated
    assert scan._header_stamp_ns(b"") is None
