"""Live ROS/Gazebo adapter used only by the isolated attachment acceptance."""

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
    return "status: SUCCEEDED" in output or (
        bilateral and "error_code: -5" in output and "status: ABORTED" in output
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


def select_stamped_transform(transforms, child_frame_id: str):
    for item in reversed(tuple(transforms)):
        if item.child_frame_id != child_frame_id:
            continue
        translation=item.transform.translation; rotation=item.transform.rotation
        pose=(
            float(translation.x),float(translation.y),float(translation.z),
            float(rotation.x),float(rotation.y),float(rotation.z),float(rotation.w),
        )
        stamp=float(item.header.stamp.sec)+float(item.header.stamp.nanosec)*1e-9
        if not all(math.isfinite(value) for value in (*pose,stamp)):
            return None
        return pose,stamp
    return None


def _command(arguments: list[str], timeout_s: float = 40.0, *, check: bool = True) -> str:
    result = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout_s)
    if check and result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(arguments)}\n{result.stdout}\n{result.stderr}"
        )
    return result.stdout + result.stderr


class RosGazeboLiveBackend:
    def __init__(self) -> None:
        if not os.environ.get("GZ_PARTITION") or not os.environ.get("ROS_DOMAIN_ID"):
            raise RuntimeError("live attachment gate requires isolated GZ_PARTITION and ROS_DOMAIN_ID")
        self.transport = GazeboTransport()
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
        safe_bilateral=False
        if "error_code: -5" in output:
            from ..gazebo.observer import (
                evaluate_bilateral_contact, MOVING_PAD_MESH_PENETRATION_CEILING_M,
            )
            evidence=evaluate_bilateral_contact(self.contacts())
            safe_bilateral=(
                evidence.bilateral and evidence.max_moving_pad_penetration_m is not None
                and evidence.max_moving_pad_penetration_m <= MOVING_PAD_MESH_PENETRATION_CEILING_M
            )
        if not gripper_result_acceptable(output,safe_bilateral):
            raise RuntimeError(f"gripper trajectory did not succeed:\n{output}")

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
        import rclpy
        from rclpy.qos import qos_profile_sensor_data
        from tf2_msgs.msg import TFMessage

        rclpy.init(); node=rclpy.create_node("so101_live_pose_pair_probe")
        observed={"object":None,"tcp":None}
        def receive_object(message):
            selected=select_stamped_transform(message.transforms,"plastic_cup")
            if selected is not None: observed["object"]=selected
        def receive_tcp(message):
            selected=select_stamped_transform(message.transforms,"so101_tcp")
            if selected is not None: observed["tcp"]=selected
        object_subscription=node.create_subscription(
            TFMessage,"/so101/gazebo_pose_info",receive_object,qos_profile_sensor_data,
        )
        tcp_subscription=node.create_subscription(
            TFMessage,"/tf",receive_tcp,qos_profile_sensor_data,
        )
        deadline=time.monotonic()+3.0
        try:
            while time.monotonic()<deadline and None in observed.values():
                rclpy.spin_once(node,timeout_sec=.05)
        finally:
            node.destroy_subscription(object_subscription)
            node.destroy_subscription(tcp_subscription)
            node.destroy_node(); rclpy.shutdown()
        if None in observed.values():
            raise RuntimeError(f"fresh Gazebo/TCP pose pair unavailable: {observed}")
        object_pose,object_stamp=observed["object"]
        tcp_pose,tcp_stamp=observed["tcp"]
        self._arm_moved_since_sample=False
        return PoseSample(
            object_pose[:3],tcp_pose[:3],object_pose[3:],tcp_pose[3:],
            abs(object_stamp-tcp_stamp),
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
