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
        self._last_tcp_xyz: tuple[float, float, float] | None = None
        self._arm_moved_since_sample = True

    def move_arm(self, points: tuple[tuple[float, ...], ...]) -> None:
        step = 2 if len(points) == 10 else 3 if len(points) == 5 else 4
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
        if "status: SUCCEEDED" not in output:
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
        time.sleep(1.0)
        model_output = _command(["gz", "model", "-m", "plastic_cup", "-p"], timeout_s=5.0)
        model_matches = _XYZ.findall(model_output)
        if not model_matches:
            raise RuntimeError(f"plastic_cup pose unavailable:\n{model_output}")
        object_xyz = tuple(float(value) for value in model_matches[0])
        tf_output = ""
        tf_matches = []
        for _attempt in range(3):
            tf_output = _command([
                "timeout", "3", "ros2", "run", "tf2_ros", "tf2_echo", "world", "so101_tcp",
            ], timeout_s=5.0, check=False)
            tf_matches = _TF_TRANSLATION.findall(tf_output)
            if tf_matches:
                break
        if not tf_matches:
            if self._arm_moved_since_sample or self._last_tcp_xyz is None:
                raise RuntimeError(f"fresh so101_tcp transform unavailable:\n{tf_output}")
            tcp_xyz = self._last_tcp_xyz
        else:
            tcp_xyz = tuple(float(value) for value in tf_matches[-1])
            self._last_tcp_xyz = tcp_xyz
        self._arm_moved_since_sample = False
        return PoseSample(object_xyz, tcp_xyz)

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
