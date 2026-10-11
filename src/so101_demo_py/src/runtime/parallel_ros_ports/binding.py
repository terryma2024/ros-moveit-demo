"""Broker generation binding, worker node inventory and the ready probe."""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

from so101_demo.application.qualification_stack import ros2_command
from so101_demo.runtime.parallel_ros_ports.isolated_node import _ready_failure_message


class RuntimeBinding:
    def bind_broker_generation(self, generation):
        """Advance the policy authority to an authenticated discovered Broker."""
        if type(generation) is not int or generation <= 0:
            raise RuntimeError("BROKER_GENERATION_AUTHORITY")
        if (
            type(self.broker_generation) is not int
            or self.broker_generation <= 0
            or generation < self.broker_generation
        ):
            raise RuntimeError("BROKER_GENERATION_ROLLBACK")
        self.broker_generation = generation
        return True

    @staticmethod
    def expected_worker_nodes():
        return (
            "/arm_controller",
            "/gripper_controller",
            "/joint_state_broadcaster",
            "/move_group",
            "/mujoco_ros2_control_node",
            "/robot_state_publisher",
            "/so101_base_to_camera_link",
            "/so101_camera_link_to_task_camera_frame",
        )

    @classmethod
    def worker_node_inventory_matches(cls, nodes, *, teacher_profile=False):
        if (
            type(nodes) is not tuple
            or any(not isinstance(node, str) for node in nodes)
            or tuple(sorted(nodes)) != nodes
            or len(set(nodes)) != len(nodes)
        ):
            return False
        required = set(cls.expected_worker_nodes())
        if teacher_profile:
            required.add("/neck_controller")
        fixed_internal = {
            "/controller_manager",
            "/move_group/moveit",
            "/moveit_simple_controller_manager",
            "/robotsystem",
        }
        generated = (
            re.compile(r"/move_group_private_[0-9]+"),
            re.compile(r"/moveit_[0-9]+"),
            re.compile(r"/transform_listener_impl_[0-9a-f]+"),
        )
        category_counts = [0] * len(generated)
        for node in nodes:
            if node in required or node in fixed_internal:
                continue
            matches = [
                index for index, pattern in enumerate(generated)
                if pattern.fullmatch(node)
            ]
            if len(matches) != 1:
                return False
            category_counts[matches[0]] += 1
        return (
            required.issubset(nodes)
            and fixed_internal.issubset(nodes)
            and category_counts == [1, 1, 1]
        )

    def rebind_resources(self, resources):
        if (
            getattr(resources, "worker_id", None) != getattr(self.resources, "worker_id", None)
            or getattr(resources, "generation", 0) != getattr(self.resources, "generation", 0) + 1
            or getattr(resources, "session_id", None) == getattr(self.resources, "session_id", None)
        ):
            raise RuntimeError("RUNTIME_RESOURCE_REBIND_IDENTITY")
        for source, *_rest in self._rgbd.values():
            source.close()
        self._rgbd.clear()
        self._reset_receipts.clear()
        self._localized.clear()
        self._admitted.clear()
        self._admission_candidates.clear()
        self._minimum_inference_stamp_ns = None
        self._close_pose_publisher()
        self._close_pause_control()
        if self._planner is not None:
            self._planner.close()
            self._planner = None
        self.resources = resources
        return True

    def close_runtime(self):
        for source, *_rest in tuple(self._rgbd.values()):
            source.close()
        self._rgbd.clear()
        self._minimum_inference_stamp_ns = None
        self._close_pose_publisher()
        self._close_pause_control()
        if self._planner is not None:
            self._planner.close()
            self._planner = None

    def ready_probe(self, _requirements):
        call = self.dependencies.get("ready_probe")
        if call is not None:
            return call(_requirements)
        # The ACT station also has the neck controller; there is no broker to wait for.
        arguments = ("--include-neck",) if self.dependencies.get("act_profile") is True else ()
        completed = subprocess.run(
            ros2_command("run", "so101_demo_py", "motion_stack_ready", "--timeout-s", "60", *arguments),
            timeout=65.0,
            check=False,
            capture_output=True,
            text=True,
        )
        # The probe's own verdict used to go to the parent's stdout only; keep it (and say why in the worker result).
        for stream, text in ((sys.stdout, completed.stdout), (sys.stderr, completed.stderr)):
            if text:
                stream.write(text)
                stream.flush()
        self.ready_failure_message = None
        if completed.returncode != 0:
            self.ready_failure_message = _ready_failure_message(completed)
            root = getattr(getattr(self, "resources", None), "worker_root", None)
            if root is not None:
                try:
                    (Path(root) / "ready-probe-failure.json").write_text(json.dumps(
                        {"returncode": completed.returncode, "message": self.ready_failure_message,
                         "stdout_tail": (completed.stdout or "")[-4000:], "stderr_tail": (completed.stderr or "")[-2000:]},
                        sort_keys=True) + "\n")
                except OSError:
                    pass
        return completed.returncode == 0
