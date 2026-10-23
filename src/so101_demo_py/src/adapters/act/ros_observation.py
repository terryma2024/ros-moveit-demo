"""Subscribe only to RGB and measured joints; exclude reset-era queued messages.

The acquisition identity of a camera frame is created here, at the first place a real published frame
exists in Python: the decoded uint8 pixels and the publisher's sim-time stamp are both in hand, and
the digest is taken from those bytes before anything downstream can copy, resize or re-encode them.
Nothing downstream may mint or renumber that identity.
"""

import numpy as np
import threading
import time
from rclpy.qos import qos_profile_sensor_data, QoSProfile, ReliabilityPolicy

RGB_QOS=QoSProfile(depth=32,reliability=ReliabilityPolicy.RELIABLE)
from sensor_msgs.msg import Image, JointState

from so101_demo.act.acquisition import AcquisitionMinter
from so101_demo.act.joints import ACT_JOINTS, ARM_JOINTS, ordered_positions
from so101_demo.act.rig_profile import DEFAULT_RIG
from so101_demo.act.synchronizer import time_ns


class RosObservationAdapter:
    def __init__(self, node, synchronizer, *, capture=None, reset_epoch=None,
                 on_hazard=None, sim_time=None):
        self._lock = getattr(capture, "ingress_lock", None) or threading.RLock()
        self.synchronizer = synchronizer
        #: the rig is the synchronizer's: the cameras this adapter subscribes to, mints and pairs, and the neck only if it has one
        self.rig = getattr(synchronizer, "rig", DEFAULT_RIG)
        self.cameras = self.rig.camera_names
        self.session_id = None
        self.source_floor_s = None
        self.rejected = []
        self.hazard = None
        self.hazards = []
        if on_hazard is not None and not callable(on_hazard):
            raise ValueError("INPUT_HAZARD_CALLBACK_INVALID")
        if sim_time is not None and not callable(sim_time):
            raise ValueError("INPUT_CLOCK_INVALID")
        self.on_hazard = on_hazard
        self.sim_time = sim_time
        self._node = node
        self._closed = False
        # the capture is optional so the observation path keeps working without an episode, and the
        # minter belongs to this adapter because this is where a real frame first exists
        self.capture = capture
        self.reset_epoch = reset_epoch
        self.acquisitions = AcquisitionMinter(self.rig)
        self.last_acquisitions = {}
        self._pre_capture_frames = {}
        self._capture_seed_admitted = False
        self._activation_in_progress = False
        self.subscriptions = []
        try:
            for stream in self.cameras:
                self.subscriptions.append(node.create_subscription(Image, self.rig.camera(stream).image_topic,
                    lambda message, stream=stream: self._image(stream, message), RGB_QOS))
            self.subscriptions.append(node.create_subscription(JointState, "/joint_states",
                self._joints, qos_profile_sensor_data))
        except BaseException as error:
            try:
                self.close()
            except BaseException as cleanup_error:
                error.add_note("Owned observation retirement also failed: " + str(cleanup_error))
            raise

    def reset(self, session_id, *, source_floor_s, reset_epoch=None):
        from so101_demo.act.contracts import finite
        with self._lock:
            if self.hazard is not None or getattr(self.capture, "started", False):
                raise ValueError("INPUT_COLLECTION_RESET_FORBIDDEN")
            self.source_floor_s = finite(source_floor_s, nonnegative=True)
            self.session_id = session_id
            if reset_epoch is not None:
                self.reset_epoch = reset_epoch
            self.acquisitions = AcquisitionMinter(self.rig)
            self.last_acquisitions = {}
            self._pre_capture_frames = {}
            self._capture_seed_admitted = False
            self.synchronizer.reset(session_id)

    def _stamp(self, message):
        if (message.header.stamp.sec < 0
                or not 0 <= message.header.stamp.nanosec < 1_000_000_000):
            raise ValueError("INPUT_TIMESTAMP_INVALID")
        stamp_ns = int(message.header.stamp.sec) * 1_000_000_000 + int(message.header.stamp.nanosec)
        stamp = stamp_ns / 1e9
        if self.session_id is None or stamp_ns <= time_ns(self.source_floor_s):
            raise ValueError("INPUT_RESET_STALE")
        if self.sim_time is not None:
            from so101_demo.act.contracts import finite
            now = finite(self.sim_time(), nonnegative=True)
            if stamp_ns > time_ns(now):
                raise ValueError("INPUT_TIMESTAMP_FUTURE")
        return stamp

    def _reject(self, reason, *, received_monotonic_s):
        self.rejected.append(reason)
        self.rejected = self.rejected[-64:]
        # Explicitly excluded reset-era queued messages may be ignored only before collection.
        # An active run cannot regain validity from a later good frame.
        if self.capture is not None and (getattr(self.capture, "active", False)
                                        or self._activation_in_progress):
            newly_latched = self.hazard is None
            if self.hazard is None:
                self.hazard = reason
                self.hazards.append({"reason": reason,
                    "received_monotonic_ns": round(received_monotonic_s * 1e9)})
            if getattr(self.capture, "active", False):
                try:
                    self.capture.reject_source(self.hazard)
                except ValueError:
                    pass  # Latched in capture; callback returns so control progress can stop.
            if newly_latched and self.on_hazard is not None:
                self.on_hazard(self.hazard)

    def close(self):
        with self._lock:
            if not self._closed:
                failure = None
                for subscription in self.subscriptions:
                    try:
                        self._node.destroy_subscription(subscription)
                    except BaseException as error:
                        if failure is None:
                            failure = error
                        else:
                            failure.add_note("Further observation retirement failed: " + str(error))
                self._closed = True
                if failure is not None:
                    raise failure

    def _image(self, stream, message):
        received = self.synchronizer.monotonic()
        with self._lock:
            self._image_locked(stream, message, received_monotonic_s=received)

    def _image_locked(self, stream, message, *, received_monotonic_s=None):
        if self.hazard is not None or self._closed:
            return
        if self._activation_in_progress:
            self._reject("INPUT_COLLECTION_ACTIVATION_REENTRANT",
                         received_monotonic_s=received_monotonic_s)
            return
        if (self.capture is not None and self.capture.started and not self.capture.active):
            # Terminal input is outside this capture; it cannot seed or reset another episode.
            return
        try:
            stamp = self._stamp(message)
            if ((message.encoding, message.width, message.height, message.step)
                    != ("rgb8", 640, 480, 1920) or len(message.data) != 640 * 480 * 3):
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
                if getattr(self.capture, "active", False):
                    self.capture.on_acquisition(frame, pixels)
                else:
                    self._pre_capture_frames[stream] = (frame, pixels)
            self.synchronizer.push(stream, self.session_id, stamp, pixels,
                                   received_monotonic_s=received_monotonic_s)
        except (AttributeError, TypeError, ValueError, OverflowError) as error:
            self._reject(str(error), received_monotonic_s=(time.monotonic()
                         if received_monotonic_s is None else received_monotonic_s))

    def capture_seed_pair(self, *, min_stamp_s):
        """Read original pre-capture slots without admitting, renumbering, or writing them."""
        from so101_demo.act.contracts import finite
        with self._lock:
            floor = finite(min_stamp_s, nonnegative=True)
            if (self._closed or self.hazard is not None or self.capture is None
                    or self.capture.started or self._capture_seed_admitted):
                raise ValueError("INPUT_COLLECTION_SEED_FIXED")
            if set(self._pre_capture_frames) != set(self.cameras):
                raise ValueError("INPUT_COLLECTION_SEED_UNAVAILABLE")
            pair = {camera: (frame, pixels.copy()) for camera, (frame, pixels) in self._pre_capture_frames.items()}
            self._validate_capture_seed(pair, floor=floor)
            return pair

    def seed_pair_refusal(self, floor, reserve_s=0.0):
        """Read-only, silent: None when the current pre-capture pair would pass `_validate_capture_seed`, else its reason.

        `reserve_s > 0` additionally requires that much age budget to remain (K5b), so a wait can end on a pair that
        will still be valid after activation. The default 0 is identical to `_validate_capture_seed`.

        A missing camera reports INPUT_COLLECTION_SEED_UNAVAILABLE, the code `capture_seed_pair` uses for it.
        """
        from so101_demo.act.contracts import finite
        with self._lock:
            floor = finite(floor, nonnegative=True)
            if set(self._pre_capture_frames) != set(self.cameras):
                return "INPUT_COLLECTION_SEED_UNAVAILABLE"
            refusal = self._seed_refusal(dict(self._pre_capture_frames), floor=floor, reserve_s=reserve_s)
            return None if refusal is None else refusal[0]

    def seed_pair_valid(self, floor):
        """Read-only: would the current pre-capture pair pass `_validate_capture_seed` right now?"""
        return self.seed_pair_refusal(floor) is None

    def _validate_capture_seed(self, pair, *, floor):
        refusal = self._seed_refusal(pair, floor=floor)
        if refusal is not None:
            reason, facts = refusal
            if facts is not None:
                self._report_seed_refusal(reason, facts)
            raise ValueError(reason)

    def _seed_refusal(self, pair, *, floor, reserve_s=0.0):
        """Return None when the pair is a valid seed, else `(reason, facts)`. Shared by the raising and read-only paths."""
        from so101_demo.act.acquisition import pixel_digest
        from so101_demo.act.contracts import ContractError, finite
        if not isinstance(pair, dict) or set(pair) != set(self.cameras) or self.sim_time is None:
            return "INPUT_COLLECTION_SEED_INVALID", None
        now_ns = time_ns(self.synchronizer.monotonic())
        sim_now_ns = time_ns(finite(self.sim_time(), nonnegative=True))
        age_ns = time_ns(self.synchronizer.max_age_s)
        max_skew_ns = time_ns(self.synchronizer.max_skew_s)
        try:
            reserve_ns = time_ns(finite(reserve_s, nonnegative=True))
        except ContractError:
            raise ValueError("INPUT_COLLECTION_SEED_RESERVE_INVALID") from None
        if reserve_ns >= age_ns:
            raise ValueError("INPUT_COLLECTION_SEED_RESERVE_INVALID")
        bound_ns = age_ns - reserve_ns

        def facts():
            return {"floor_ns": time_ns(floor), "sim_now_ns": sim_now_ns, "now_ns": now_ns, "age_ns": age_ns,
                    "max_skew_ns": max_skew_ns,
                    "cameras": {camera: {"stamp_ns": time_ns(pair[camera][0].stamp_s),
                                         "received_monotonic_ns": pair[camera][0].received_monotonic_ns}
                                for camera in self.cameras}}

        stamps = []
        for camera in self.cameras:
            frame, pixels = pair[camera]
            original = self._pre_capture_frames.get(camera)
            if (original is None or frame != original[0] or frame.camera != camera
                    or (frame.session_id, frame.reset_epoch) != (self.session_id, self.reset_epoch)
                    or pixel_digest(pixels) != frame.pixel_sha256):
                return "INPUT_COLLECTION_SEED_INVALID", None
            stamp_ns = time_ns(frame.stamp_s)
            if (stamp_ns < time_ns(floor) or not 0 <= sim_now_ns - stamp_ns <= bound_ns
                    or not 0 <= now_ns - frame.received_monotonic_ns <= bound_ns):
                return "INPUT_COLLECTION_SEED_EXPIRED", facts()
            stamps.append(stamp_ns)
        if max(stamps) - min(stamps) > max_skew_ns:
            return "INPUT_COLLECTION_SEED_SKEW_INVALID", facts()
        return None

    @staticmethod
    def _report_seed_refusal(reason, facts):
        """Observation only (D16): one stderr line of refusal facts. Never raises and never changes the refusal."""
        try:
            import json
            import sys
            print("INPUT_COLLECTION_SEED_REFUSAL " + json.dumps({"reason": reason, **facts}, sort_keys=True,
                  separators=(",", ":")), file=sys.stderr, flush=True)
        except Exception:
            pass

    def activate_capture(self, *, min_stamp_s, activate):
        """Fence original seed selection, owner activation and admission against ingress."""
        if not callable(activate):
            raise ValueError("INPUT_COLLECTION_ACTIVATION_INVALID")
        with self._lock:
            pair = self.capture_seed_pair(min_stamp_s=min_stamp_s)
            self._activation_in_progress = True
            try:
                activate(max(frame.stamp_s for frame, pixels in pair.values()))
                self.admit_capture_seed(pair)
            except BaseException as error:
                if self.capture.started:
                    self._reject(str(error) or type(error).__name__, received_monotonic_s=self.synchronizer.monotonic())
                raise
            finally:
                self._activation_in_progress = False
            return pair

    def admit_capture_seed(self, pair):
        """Admit the same original pair once, after the owner's capture activation."""
        with self._lock:
            try:
                if self.hazard is not None:
                    raise ValueError(self.hazard)
                if (self._closed or self._capture_seed_admitted
                        or self.capture is None or not getattr(self.capture, "active", False)):
                    raise ValueError("INPUT_COLLECTION_SEED_FIXED")
                self._validate_capture_seed(pair, floor=self.source_floor_s)
                for camera in self.cameras:
                    self.capture.on_acquisition(*pair[camera])
                self._capture_seed_admitted = True
                self._pre_capture_frames.clear()
            except (AttributeError, TypeError, ValueError) as error:
                self._reject(str(error), received_monotonic_s=self.synchronizer.monotonic())
                raise

    def _joints(self, message):
        received = self.synchronizer.monotonic()
        with self._lock:
            self._joints_locked(message, received_monotonic_s=received)

    def _joints_locked(self, message, *, received_monotonic_s=None):
        if self.hazard is not None or self._closed:
            return
        if self._activation_in_progress:
            self._reject("INPUT_COLLECTION_ACTIVATION_REENTRANT",
                         received_monotonic_s=received_monotonic_s)
            return
        if (self.capture is not None and self.capture.started and not self.capture.active):
            return
        try:
            stamp = self._stamp(message)
            if len(message.name) != len(message.position) or len(set(message.name)) != len(message.name):
                raise ValueError("JOINT_MAPPING_INVALID")
            values = ordered_positions(dict(zip(message.name, message.position, strict=True)),
                                       ACT_JOINTS if self.rig.has_neck else ARM_JOINTS)
            self.synchronizer.push("arm", self.session_id, stamp, values[:6],
                                   received_monotonic_s=received_monotonic_s)
            if self.rig.has_neck:
                self.synchronizer.push("neck", self.session_id, stamp, values[6],
                                       received_monotonic_s=received_monotonic_s)
        except (AttributeError, TypeError, ValueError, OverflowError) as error:
            self._reject(str(error), received_monotonic_s=(time.monotonic()
                         if received_monotonic_s is None else received_monotonic_s))
