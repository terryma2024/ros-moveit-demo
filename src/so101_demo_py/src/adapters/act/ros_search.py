"""Causal RGB/CameraInfo/feedback search port; neck commands use injected ownership."""

from collections import deque
from concurrent.futures import Future
import math
import threading
import time

import numpy as np
from rclpy.qos import qos_profile_sensor_data, QoSProfile, ReliabilityPolicy

RGB_QOS=QoSProfile(depth=32,reliability=ReliabilityPolicy.RELIABLE)
from rclpy.time import Time
from sensor_msgs.msg import Image, CameraInfo, JointState

from so101_demo.act.contracts import finite
from so101_demo.act.synchronizer import causal_sample
from .detector import detect_head


def stamp_s(message):
    return message.header.stamp.sec + message.header.stamp.nanosec * 1e-9


def rotation_matrix(quaternion):
    x, y, z, w = (finite(getattr(quaternion, name)) for name in ("x", "y", "z", "w"))
    if not math.isclose(x*x+y*y+z*z+w*w, 1., abs_tol=1e-6):
        raise ValueError("CAMERA_ROTATION_INVALID")
    return np.array(((1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)),
                     (2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)),
                     (2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y))))


class RosSearchAdapter:
    def __init__(self, node, search, detector_runtime, neck_port, *, tf_buffer=None,
                 monotonic=time.monotonic):
        self.search, self.detector_runtime, self.neck_port = search, detector_runtime, neck_port
        self.monotonic = monotonic
        self._lock = threading.RLock()
        self._generation=0;self.input_errors=deque(maxlen=32)
        self._pending_detection=None;self._detector_reset_required=False
        self.images, self.infos, self.feedback = (deque(maxlen=32) for _ in range(3))
        self.source_floor_s = None
        self.last_command = None
        self.last_detections_stamp = None
        if tf_buffer is None:
            from tf2_ros import Buffer, TransformListener
            self.tf_buffer = Buffer()
            self.tf_listener = TransformListener(self.tf_buffer, node)
        else:
            self.tf_buffer, self.tf_listener = tf_buffer, None
        self.subscriptions = [
            node.create_subscription(Image, "/head_camera/color", self._image, RGB_QOS),
            node.create_subscription(CameraInfo, "/head_camera/camera_info", self._info, RGB_QOS),
            node.create_subscription(JointState, "/joint_states", self._joints, qos_profile_sensor_data)]

    def reset(self, config, *, source_floor_s):
        with self._lock:
            self._generation+=1;self.input_errors.clear()
            self.source_floor_s = finite(source_floor_s, nonnegative=True)
            self.search.reset(config)
            if self._pending_detection is not None and not self._pending_detection['future'].done():
                self._detector_reset_required=True
            else:
                self.detector_runtime.reset();self._pending_detection=None
                self._detector_reset_required=False
            for buffer in (self.images,self.infos,self.feedback): buffer.clear()
            self.last_command = self.last_detections_stamp = None

    def _append(self, buffer, message):
        stamp = stamp_s(message)
        if self.source_floor_s is None or stamp <= self.source_floor_s:
            return
        if buffer and stamp <= buffer[-1][0]: return
        buffer.append((stamp, (message, self.monotonic())))

    def _image(self, message):
        with self._lock: self._append(self.images, message)

    def _info(self, message):
        with self._lock: self._append(self.infos, message)

    def _joints(self, message):
        with self._lock:
            if (len(set(message.name)) != len(message.name)
                    or len(message.name) != len(message.position)
                    or len(message.name) != len(message.velocity)
                    or "neck_yaw_joint" not in message.name): return
            self._append(self.feedback, message)

    def _stop_and_confirm(self,generation):
        try:
            if self.neck_port.stop_and_confirm() is not True:raise RuntimeError("SEARCH_STOP_UNCONFIRMED")
        except Exception as error:
            with self._lock:
                if self._generation==generation:self.search.fail("SEARCH_STOP_UNCONFIRMED")
            raise RuntimeError("SEARCH_STOP_UNCONFIRMED") from error
        with self._lock:
            if self._generation!=generation:raise RuntimeError("SEARCH_RESET_DURING_TICK")
            self.last_command=None

    def _queue_detection(self,generation,image,frame,feedback,info_received):
        with self._lock:
            if self._generation!=generation:raise RuntimeError("SEARCH_RESET_DURING_TICK")
            if self._pending_detection is not None:return self._pending_detection
            future=Future()
            job=dict(generation=generation,future=future,frame=frame,feedback=feedback,info_received=info_received)
            self._pending_detection=job
            rgb=np.frombuffer(bytes(image.data),np.uint8).reshape(480,640,3)
            config=dict(self.search.config)
            def infer():
                try:
                    result=detect_head(rgb,dict(runtime=self.detector_runtime,
                        session_id=config['session_id'],attempt_id=config['attempt_id'],
                        source_stamp_ns=image.header.stamp.sec*1000000000+image.header.stamp.nanosec,
                        source_frame_id=image.header.frame_id))
                    future.set_result(result)
                except Exception as error:future.set_exception(error)
            threading.Thread(target=infer,daemon=True,name='act-head-rgb-detector').start()
            return job

    def tick(self, *, safe_observe, now_wall_s=None):
        started=self.monotonic()
        now=finite(started if now_wall_s is None else now_wall_s,nonnegative=True)
        with self._lock:
            generation=self._generation;config=dict(self.search.config)
            decision=self.search.advance_deadline(now)
            if decision is None and safe_observe is not True:decision=self.search.fail("SEARCH_UNSAFE")
            images,infos,feedback_buffer=(tuple(value) for value in (self.images,self.infos,self.feedback))
            pending=self._pending_detection
            if pending is not None and pending['generation']!=generation and pending['future'].done():
                self.detector_runtime.reset();self._pending_detection=pending=None
                self._detector_reset_required=False
        # A single daemon inference job never blocks the monotonic tick. Old
        # jobs cannot populate a reset attempt, and no new job overtakes them.
        if decision is None:
            try:
                if pending is not None:
                    if not pending['future'].done():
                        decision=dict(neck_target_rad=None,stop=True,status="INPUT_PENDING")
                    elif pending['generation']==generation:
                        frame=dict(pending['frame'],detections=pending['future'].result())
                        feedback=dict(pending['feedback'],safe_observe=safe_observe)
                        info_received=pending['info_received']
                        with self._lock:
                            if self._generation!=generation:raise RuntimeError("SEARCH_RESET_DURING_TICK")
                            self.detections=frame['detections'];self.last_detections_stamp=frame['sim_time_s']
                            self._pending_detection=None
                else:
                    if not images:raise ValueError("INPUT_STALE")
                    source_time,(image,received_at)=images[-1]
                    info,info_received=causal_sample(infos,source_time,config['max_skew_s'])
                    joints,feedback_received=causal_sample(feedback_buffer,source_time,config['max_skew_s'])
                    if stamp_s(info)!=source_time or info.header.frame_id!=image.header.frame_id:
                        raise ValueError("INPUT_CAMERA_INFO_INVALID")
                    index=joints.name.index('neck_yaw_joint')
                    feedback=dict(session_id=config['session_id'],attempt_id=config['attempt_id'],
                        sim_time_s=stamp_s(joints),received_wall_s=feedback_received,
                        neck_yaw_rad=finite(joints.position[index]),neck_velocity_rad_s=finite(joints.velocity[index]),
                        safe_observe=safe_observe)
                    if (image.encoding,image.width,image.height,image.step,len(image.data))!=(
                            'rgb8',640,480,1920,640*480*3):raise ValueError('INPUT_RGB_INVALID')
                    transform=self.tf_buffer.lookup_transform('base',image.header.frame_id,Time.from_msg(joints.header.stamp))
                    rotation=rotation_matrix(transform.transform.rotation)
                    frame=dict(session_id=config['session_id'],attempt_id=config['attempt_id'],
                        sim_time_s=source_time,received_wall_s=received_at,detections=[],
                        k=tuple(info.k),distortion=tuple(info.d),rotation_optical_to_base=rotation,
                        frame_id=image.header.frame_id)
                    settled=(abs(feedback['neck_yaw_rad']-self.search.target)<=config['goal_tolerance_rad']
                             and abs(feedback['neck_velocity_rad_s'])<=config['settle_velocity_rad_s'])
                    fresh=(all(0<=now-value<=config['max_age_s'] for value in (received_at,info_received,feedback_received))
                           and 0<=source_time-feedback['sim_time_s']<=config['max_skew_s'])
                    new=(self.search.last_frame_s is None or source_time>self.search.last_frame_s)
                    post_motion=self.search.motion_source_s is None or source_time>self.search.motion_source_s
                    if settled and fresh and new and post_motion:
                        self._queue_detection(generation,image,frame,feedback,info_received)
                        decision=dict(neck_target_rad=None,stop=True,status='INPUT_PENDING')
                elapsed=self.monotonic()-started
                if elapsed<0:raise ValueError('SEARCH_CLOCK_INVALID')
                with self._lock:
                    if self._generation!=generation:raise RuntimeError('SEARCH_RESET_DURING_TICK')
                    terminal=self.search.advance_deadline(now+elapsed)
                    if terminal is not None:decision=terminal
                    if decision is None:
                        if not 0<=now+elapsed-info_received<=config['max_age_s']:raise ValueError('INPUT_STALE')
                        decision=self.search.tick(frame,feedback,now+elapsed)
            except Exception as error:
                with self._lock:
                    if self._generation!=generation:raise RuntimeError('SEARCH_RESET_DURING_TICK') from error
                    if pending is not None and pending['future'].done():self._pending_detection=None
                    self.input_errors.append(dict(error=repr(error),wall_s=self.monotonic()))
                    elapsed=self.monotonic()-started
                    if elapsed<0:self.search.fail('SEARCH_CLOCK_INVALID');raise ValueError('SEARCH_CLOCK_INVALID') from error
                    decision=self.search.advance_deadline(now+elapsed) or dict(neck_target_rad=None,stop=True,status='INPUT_STALE')
        if 'found' in decision or decision['stop']:
            self._stop_and_confirm(generation)
        else:
            with self._lock:
                if self._generation!=generation:raise RuntimeError('SEARCH_RESET_DURING_TICK')
                if decision['neck_target_rad']!=self.last_command:
                    self.neck_port.command_neck(decision['neck_target_rad'],session_id=config['session_id'],
                        attempt_id=config['attempt_id'],observation_time_s=frame['sim_time_s'])
                    self.last_command=decision['neck_target_rad']
        return decision
