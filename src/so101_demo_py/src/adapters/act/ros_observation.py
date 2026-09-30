"""Subscribe only to RGB and measured joints; exclude reset-era queued messages.

The acquisition identity of a camera frame is created here, at the first place a real published frame
exists in Python: the decoded uint8 pixels and the publisher's sim-time stamp are both in hand, and
the digest is taken from those bytes before anything downstream can copy, resize or re-encode them.
Nothing downstream may mint or renumber that identity.
"""

import numpy as np
import threading
from rclpy.qos import qos_profile_sensor_data, QoSProfile, ReliabilityPolicy

RGB_QOS=QoSProfile(depth=32,reliability=ReliabilityPolicy.RELIABLE)
from sensor_msgs.msg import Image, JointState

from so101_demo.act.acquisition import AcquisitionMinter
from so101_demo.act.joints import ACT_JOINTS, ordered_positions


class RosObservationAdapter:
    def __init__(self, node, synchronizer, *, capture=None, reset_epoch=None):
        self._lock = threading.RLock()
        self.synchronizer = synchronizer
        self.session_id = None
        self.source_floor_s = None
        self.rejected = []
        # the capture is optional so the observation path keeps working without an episode, and the
        # minter belongs to this adapter because this is where a real frame first exists
        self.capture = capture
        self.reset_epoch = reset_epoch
        self.acquisitions = AcquisitionMinter()
        self.last_acquisitions = {}
        self.subscriptions = [node.create_subscription(Image, f"/{stream}_camera/color",
            lambda message, stream=stream: self._image(stream, message), RGB_QOS)
            for stream in ("head", "wrist")]
        self.subscriptions.append(node.create_subscription(JointState, "/joint_states",
            self._joints, qos_profile_sensor_data))

    def reset(self, session_id, *, source_floor_s, reset_epoch=None):
        from so101_demo.act.contracts import finite
        with self._lock:
            self.source_floor_s = finite(source_floor_s, nonnegative=True)
            self.session_id = session_id
            if reset_epoch is not None:
                self.reset_epoch = reset_epoch
            self.acquisitions = AcquisitionMinter()
            self.last_acquisitions = {}
            self.synchronizer.reset(session_id)

    def _stamp(self, message):
        stamp = message.header.stamp.sec + message.header.stamp.nanosec * 1e-9
        if self.session_id is None or stamp <= self.source_floor_s:
            raise ValueError("INPUT_RESET_STALE")
        return stamp

    def _image(self, stream, message):
        received = self.synchronizer.monotonic()
        with self._lock:
            self._image_locked(stream, message, received_monotonic_s=received)

    def _image_locked(self, stream, message, *, received_monotonic_s=None):
        try:
            stamp = self._stamp(message)
            if (message.encoding, message.width, message.height, message.step) != ("rgb8", 640, 480, 1920):
                raise ValueError("INPUT_RGB_INVALID")
            pixels = np.frombuffer(bytes(message.data), dtype=np.uint8).reshape((480, 640, 3))
            if self.capture is not None:
                # mint at the producer boundary, before any consumer can select or re-encode it
                frame = self.acquisitions.mint(
                    stream, session_id=self.session_id, reset_epoch=self.reset_epoch,
                    stamp_s=stamp,
                    received_monotonic_ns=max(1, int(round(received_monotonic_s * 1e9))),
                    pixels=pixels)
                self.last_acquisitions[stream] = frame
                self.capture.on_acquisition(frame, pixels)
            self.synchronizer.push(stream, self.session_id, stamp, pixels,
                                   received_monotonic_s=received_monotonic_s)
        except ValueError as error:
            self.rejected.append(str(error)); self.rejected = self.rejected[-64:]

    def _joints(self, message):
        received = self.synchronizer.monotonic()
        with self._lock:
            self._joints_locked(message, received_monotonic_s=received)

    def _joints_locked(self, message, *, received_monotonic_s=None):
        try:
            stamp = self._stamp(message)
            if len(message.name) != len(message.position) or len(set(message.name)) != len(message.name):
                raise ValueError("JOINT_MAPPING_INVALID")
            values = ordered_positions(dict(zip(message.name, message.position, strict=True)), ACT_JOINTS)
            self.synchronizer.push("arm", self.session_id, stamp, values[:6],
                                   received_monotonic_s=received_monotonic_s)
            self.synchronizer.push("neck", self.session_id, stamp, values[6],
                                   received_monotonic_s=received_monotonic_s)
        except ValueError as error:
            self.rejected.append(str(error)); self.rejected = self.rejected[-64:]
