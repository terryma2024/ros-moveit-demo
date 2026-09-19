"""Subscribe only to RGB and measured joints; exclude reset-era queued messages."""

import numpy as np
import threading
from rclpy.qos import qos_profile_sensor_data, QoSProfile, ReliabilityPolicy

RGB_QOS=QoSProfile(depth=32,reliability=ReliabilityPolicy.RELIABLE)
from sensor_msgs.msg import Image, JointState

from so101_demo.act.joints import ACT_JOINTS, ordered_positions


class RosObservationAdapter:
    def __init__(self, node, synchronizer):
        self._lock = threading.RLock()
        self.synchronizer = synchronizer
        self.session_id = None
        self.source_floor_s = None
        self.rejected = []
        self.subscriptions = [node.create_subscription(Image, f"/{stream}_camera/color",
            lambda message, stream=stream: self._image(stream, message), RGB_QOS)
            for stream in ("head", "wrist")]
        self.subscriptions.append(node.create_subscription(JointState, "/joint_states",
            self._joints, qos_profile_sensor_data))

    def reset(self, session_id, *, source_floor_s):
        from so101_demo.act.contracts import finite
        with self._lock:
            self.source_floor_s = finite(source_floor_s, nonnegative=True)
            self.session_id = session_id
            self.synchronizer.reset(session_id)

    def _stamp(self, message):
        stamp = message.header.stamp.sec + message.header.stamp.nanosec * 1e-9
        if self.session_id is None or stamp <= self.source_floor_s:
            raise ValueError("INPUT_RESET_STALE")
        return stamp

    def _image(self, stream, message):
        with self._lock:
            self._image_locked(stream, message)

    def _image_locked(self, stream, message):
        try:
            stamp = self._stamp(message)
            if (message.encoding, message.width, message.height, message.step) != ("rgb8", 640, 480, 1920):
                raise ValueError("INPUT_RGB_INVALID")
            pixels = np.frombuffer(bytes(message.data), dtype=np.uint8).reshape((480, 640, 3))
            self.synchronizer.push(stream, self.session_id, stamp, pixels)
        except ValueError as error:
            self.rejected.append(str(error)); self.rejected = self.rejected[-64:]

    def _joints(self, message):
        with self._lock:
            self._joints_locked(message)

    def _joints_locked(self, message):
        try:
            stamp = self._stamp(message)
            if len(message.name) != len(message.position) or len(set(message.name)) != len(message.name):
                raise ValueError("JOINT_MAPPING_INVALID")
            values = ordered_positions(dict(zip(message.name, message.position, strict=True)), ACT_JOINTS)
            self.synchronizer.push("arm", self.session_id, stamp, values[:6])
            self.synchronizer.push("neck", self.session_id, stamp, values[6])
        except ValueError as error:
            self.rejected.append(str(error)); self.rejected = self.rejected[-64:]
