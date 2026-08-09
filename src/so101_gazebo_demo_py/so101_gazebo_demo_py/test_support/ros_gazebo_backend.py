"""Live ROS/Gazebo adapter used only by the isolated attachment acceptance."""

from collections import deque
import json
import math
import os
from pathlib import Path
import re
import subprocess
import threading
import time

from ..gazebo.observer import ContactPair
from ..gazebo.transport import GazeboTransport
from .live_attachment import PoseSample


_CONTACT_SUFFIXES = (
    "wall_near", "wall_01", "wall_02", "wall_03", "wall_04", "wall_05",
    "wall_opposite", "wall_07", "wall_08", "wall_09", "wall_10", "wall_11", "bottom",
)
_XYZ = re.compile(r"\[\s*(-?[0-9.eE+]+)\s+(-?[0-9.eE+]+)\s+(-?[0-9.eE+]+)\s*\]")
_TF_TRANSLATION = re.compile(
    r"Translation:\s*\[\s*(-?[0-9.eE+]+),\s*(-?[0-9.eE+]+),\s*(-?[0-9.eE+]+)\s*\]"
)
_TF_QUATERNION = re.compile(
    r"Rotation:\s*in Quaternion\s*\[\s*(-?[0-9.eE+]+),\s*(-?[0-9.eE+]+),"
    r"\s*(-?[0-9.eE+]+),\s*(-?[0-9.eE+]+)\s*\]"
)


def contact_probe_complete(observed) -> bool:
    """A stability sample is complete once one fresh contact message is decoded."""
    return bool(observed)


def waypoint_step_seconds(point_count: int, velocity_scaling: float | None = None) -> int:
    if velocity_scaling is not None:
        return max(1, round(0.1 / velocity_scaling))
    return 2 if point_count == 10 else 3 if point_count == 5 else 4


def gripper_result_acceptable(output: str, bilateral: bool) -> bool:
    del bilateral
    return "status: SUCCEEDED" in output or (
        "error_code: -5" in output and "status: ABORTED" in output
    )


def parse_model_pose(output: str) -> tuple[float, ...]:
    """Parse Gazebo's authoritative world position and RPY orientation."""
    matches = _XYZ.findall(output)
    if len(matches) < 2:
        raise ValueError("Gazebo model pose requires position and orientation")
    x, y, z = (float(value) for value in matches[0])
    roll, pitch, yaw = (float(value) for value in matches[1])
    cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    quaternion = (
        sr * cp * cy - cr * sp * sy,
        cr * sp * cy + sr * cp * sy,
        cr * cp * sy - sr * sp * cy,
        cr * cp * cy + sr * sp * sy,
    )
    if not all(math.isfinite(value) for value in (x, y, z, *quaternion)):
        raise ValueError("Gazebo model pose is non-finite")
    return x, y, z, *quaternion


def parse_tf_pose(output: str) -> tuple[float, ...]:
    translation = _TF_TRANSLATION.findall(output)
    quaternion = _TF_QUATERNION.findall(output)
    if not translation or not quaternion:
        raise ValueError("TF pose requires translation and quaternion")
    pose = tuple(float(value) for value in (*translation[-1], *quaternion[-1]))
    if not all(math.isfinite(value) for value in pose):
        raise ValueError("TF pose is non-finite")
    return pose


def make_set_pose_request(entity_name: str, pose_xyz_xyzw: tuple[float, ...]) -> str:
    """Build the Gazebo set_pose protobuf text for one world entity."""
    if len(pose_xyz_xyzw) != 7 or not all(math.isfinite(value) for value in pose_xyz_xyzw):
        raise ValueError("set_pose requires one finite xyz+xyzw pose")
    x, y, z, qx, qy, qz, qw = pose_xyz_xyzw
    return (
        f'name: "{entity_name}" '
        f'position {{ x: {x} y: {y} z: {z} }} '
        f'orientation {{ x: {qx} y: {qy} z: {qz} w: {qw} }}'
    )


def select_stamped_transform(transforms, child_frame_id: str):
    for item in reversed(tuple(transforms)):
        if item.child_frame_id != child_frame_id:
            continue
        translation = item.transform.translation
        rotation = item.transform.rotation
        pose = (
            float(translation.x), float(translation.y), float(translation.z),
            float(rotation.x), float(rotation.y), float(rotation.z), float(rotation.w),
        )
        stamp = float(item.header.stamp.sec) + float(item.header.stamp.nanosec) * 1e-9
        if not all(math.isfinite(value) for value in (*pose, stamp)):
            return None
        return pose, stamp
    return None


def select_gazebo_pose(message, entity_name: str):
    for item in reversed(tuple(message.pose)):
        if item.name != entity_name:
            continue
        pose = (
            float(item.position.x), float(item.position.y), float(item.position.z),
            float(item.orientation.x), float(item.orientation.y),
            float(item.orientation.z), float(item.orientation.w),
        )
        stamp = float(message.header.stamp.sec) + float(message.header.stamp.nsec) * 1e-9
        if not all(math.isfinite(value) for value in (*pose, stamp)):
            return None
        return pose, stamp
    return None


def close_gazebo_subscription(node, topic: str) -> None:
    node.unsubscribe(topic)


def pose_pair_ready(observed, max_pair_age_s: float) -> bool:
    if None in observed.values():
        return False
    _, object_stamp = observed["object"]
    _, tcp_stamp = observed["tcp"]
    return abs(object_stamp - tcp_stamp) <= max_pair_age_s


def closest_pose_pair(object_samples, tcp_samples):
    if not object_samples or not tcp_samples:
        return {"object": None, "tcp": None}
    object_sample, tcp_sample = min(
        ((object_sample, tcp_sample)
         for object_sample in object_samples
         for tcp_sample in tcp_samples),
        key=lambda pair: abs(pair[0][1] - pair[1][1]),
    )
    return {"object": object_sample, "tcp": tcp_sample}


def _command(arguments: list[str], timeout_s: float = 40.0, *, check: bool = True) -> str:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout_s)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(arguments)}\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout + result.stderr


class RosGazeboLiveBackend:
    def __init__(self, max_pair_age_s: float = 0.10) -> None:
        if not os.environ.get("GZ_PARTITION") or not os.environ.get("ROS_DOMAIN_ID"):
            raise RuntimeError("live attachment gate requires isolated GZ_PARTITION and ROS_DOMAIN_ID")
        self.transport = GazeboTransport()
        self.max_pair_age_s = max_pair_age_s
        self._arm_moved_since_sample = True

    def move_arm(
        self, points: tuple[tuple[float, ...], ...], velocity_scaling: float | None = None
    ) -> None:
        step = waypoint_step_seconds(len(points), velocity_scaling)
        goal = {
            "trajectory": {
                "joint_names": list("12345"),
                "points": [
                    {"positions": point, "time_from_start": {"sec": step * index}}
                    for index, point in enumerate(points, 1)
                ],
            }
        }
        output = _command([
            "ros2", "action", "send_goal", "/arm_controller/follow_joint_trajectory",
            "control_msgs/action/FollowJointTrajectory", json.dumps(goal),
        ], timeout_s=step * len(points) + 20.0)
        if "status: SUCCEEDED" not in output:
            raise RuntimeError(f"arm trajectory did not succeed:\n{output}")
        self._arm_moved_since_sample = True

    def move_gripper(self, target_q6: float) -> None:
        duration = 8 if target_q6 < 0.0 else 5
        goal = {
            "trajectory": {
                "joint_names": ["6"],
                "points": [{"positions": [target_q6], "time_from_start": {"sec": duration}}],
            }
        }
        output = _command([
            "ros2", "action", "send_goal", "/gripper_controller/follow_joint_trajectory",
            "control_msgs/action/FollowJointTrajectory", json.dumps(goal),
        ], timeout_s=duration + 20.0)
        if not gripper_result_acceptable(output, bilateral=False):
            raise RuntimeError(f"gripper trajectory did not succeed:\n{output}")

    def set_object_pose(self, pose_xyz_xyzw: tuple[float, ...]) -> None:
        output = _command([
            "gz", "service", "-s", "/world/so101_pick_place/set_pose",
            "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
            "--timeout", "5000", "--req",
            make_set_pose_request("plastic_cup", pose_xyz_xyzw),
        ], timeout_s=10.0)
        if "data: true" not in output:
            raise RuntimeError(f"Gazebo set_pose did not succeed:\n{output}")
        self._arm_moved_since_sample = True

    def contacts(self) -> tuple[ContactPair, ...]:
        import rclpy
        from ros_gz_interfaces.msg import Contacts

        rclpy.init()
        node = rclpy.create_node("so101_attachment_live_contact_probe")
        lock = threading.Lock()
        observed: list[ContactPair] = []

        def receive(message: Contacts) -> None:
            additions = []
            for contact in message.contacts:
                first = contact.collision1.name
                second = contact.collision2.name
                if "plastic_cup::" in first:
                    object_collision, finger_collision = first, second
                elif "plastic_cup::" in second:
                    object_collision, finger_collision = second, first
                else:
                    continue
                additions.append(ContactPair(object_collision, finger_collision, tuple(contact.depths)))
            with lock:
                observed.extend(additions)
        subscription = node.create_subscription(Contacts, "/task_object/contacts", receive, 100)
        deadline = time.monotonic() + 3.0
        try:
            while time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.1)
                with lock:
                    if contact_probe_complete(observed):
                        break
        finally:
            node.destroy_subscription(subscription)
            node.destroy_node()
            rclpy.shutdown()
        with lock:
            return tuple(observed)

    def set_attached(self, attached: bool) -> None:
        topic = "/so101/attach_object" if attached else "/so101/detach_object"
        if not self.transport.publish_empty(topic):
            raise RuntimeError(f"cannot publish {topic}")
        requested = "attached" if attached else "detached"
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            if self.attachment_state() == requested:
                return
            time.sleep(0.1)
        raise RuntimeError(f"durable Gazebo attachment state did not converge to {requested}")

    def sample(self) -> PoseSample:
        from gz.msgs10.pose_v_pb2 import Pose_V
        from gz.transport13 import Node as GazeboNode
        import rclpy
        from rclpy.duration import Duration
        from tf2_ros import Buffer, TransformListener

        rclpy.init()
        node = rclpy.create_node("so101_live_pose_pair_probe")
        object_samples = deque(maxlen=64)
        tcp_samples = deque(maxlen=64)
        gazebo_node = GazeboNode()
        buffer = Buffer()
        listener = TransformListener(buffer, node)

        def receive_object(message):
            selected = select_gazebo_pose(message, "plastic_cup")
            if selected is not None:
                object_samples.append(selected)

        pose_topic = "/world/so101_pick_place/pose/info"
        if not gazebo_node.subscribe(Pose_V, pose_topic, receive_object):
            node.destroy_node()
            rclpy.shutdown()
            raise RuntimeError("cannot subscribe to Gazebo pose info")
        deadline = time.monotonic() + 3.0
        try:
            while time.monotonic() < deadline:
                observed = closest_pose_pair(object_samples, tcp_samples)
                if pose_pair_ready(observed, self.max_pair_age_s):
                    break
                rclpy.spin_once(node, timeout_sec=0.05)
                try:
                    transform = buffer.lookup_transform(
                        "world", "so101_tcp", rclpy.time.Time(),
                        timeout=Duration(seconds=0.01),
                    )
                    translation = transform.transform.translation
                    rotation = transform.transform.rotation
                    stamp = transform.header.stamp
                    tcp_sample = (
                        (
                            float(translation.x), float(translation.y), float(translation.z),
                            float(rotation.x), float(rotation.y),
                            float(rotation.z), float(rotation.w),
                        ),
                        float(stamp.sec) + float(stamp.nanosec) * 1e-9,
                    )
                    if not tcp_samples or tcp_samples[-1][1] != tcp_sample[1]:
                        tcp_samples.append(tcp_sample)
                except Exception:
                    pass
        finally:
            close_gazebo_subscription(gazebo_node, pose_topic)
            del listener
            node.destroy_node()
            rclpy.shutdown()
        observed = closest_pose_pair(object_samples, tcp_samples)
        if not pose_pair_ready(observed, self.max_pair_age_s):
            raise RuntimeError(f"fresh Gazebo/TCP pose pair unavailable: {observed}")
        object_pose, object_stamp = observed["object"]
        tcp_pose, tcp_stamp = observed["tcp"]
        self._arm_moved_since_sample = False
        return PoseSample(
            object_pose[:3], tcp_pose[:3], object_pose[3:], tcp_pose[3:],
            abs(object_stamp - tcp_stamp),
        )

    def attachment_state(self) -> str:
        output = _command([
            "gz", "topic", "-e", "-t", "/so101/object_attached", "-n", "1",
        ], timeout_s=5.0)
        if '"attached"' in output:
            return "attached"
        if '"detached"' in output:
            return "detached"
        raise RuntimeError(f"invalid durable attachment state:\n{output}")

    def solver_stable(self) -> bool:
        sample = self.sample()
        return all(math.isfinite(value) for value in (*sample.object_xyz, *sample.tcp_xyz))

    def original_collision_plugin_loaded(self) -> bool:
        partition = os.environ["GZ_PARTITION"].encode()
        for process in Path("/proc").iterdir():
            if not process.name.isdigit():
                continue
            try:
                environment = (process / "environ").read_bytes()
                command = (process / "cmdline").read_bytes()
                if partition not in environment or b"gz sim" not in command:
                    continue
                if "libso101_attachment_collision_system.so" in (process / "maps").read_text():
                    return True
            except (FileNotFoundError, PermissionError, ProcessLookupError, UnicodeDecodeError):
                continue
        return False
