"""Concrete, observation-backed ROS/MuJoCo ports for one parallel Worker."""

from __future__ import annotations

from typing import Callable, Mapping

from so101_demo.parallel_batch.contracts import RunMode
from so101_demo.runtime.parallel_ros_ports.binding import RuntimeBinding
from so101_demo.runtime.parallel_ros_ports.execution import ExecutionPorts
from so101_demo.runtime.parallel_ros_ports.perception import PerceptionPorts
from so101_demo.runtime.parallel_ros_ports.point_gate import PointGate
from so101_demo.runtime.parallel_ros_ports.recovery import RecoveryPorts


class ParallelRosRuntimePorts(RuntimeBinding, PointGate, PerceptionPorts, ExecutionPorts, RecoveryPorts):
    """Lazy concrete ROS ports; tests may replace individual observations."""

    REQUIRED = {
        "ready_probe",
        "reset_point",
        "reserve_workspace",
        "initial_gate",
        "localize",
        "admit_pose",
        "publish_pose",
        "plan_prefix",
        "execute_result",
        "consumer_ready",
        "capture_rgb",
        "capture_numeric_evidence",
        "cancel_motion",
        "confirm_no_controller_goal",
        "pause_physics",
        "resume_physics",
        "recovery",
        "close_runtime",
    }

    def __init__(
        self,
        resources,
        *,
        catalog,
        config=None,
        mode=RunMode.PLAN_ONLY,
        broker_generation=None,
        dependencies: Mapping[str, Callable] | None = None,
    ):
        self.resources = resources
        self.catalog = dict(catalog)
        self.config = config
        self.mode = mode
        self.broker_generation = broker_generation
        self.dependencies = dict(dependencies or {})
        self._reset_receipts = {}
        self._rgbd = {}
        self._localized = {}
        self._admitted = {}
        self._admission_candidates = {}
        self._planner = None
        self._pose_publisher_owner = None
        self._pose_publisher = None
        self._pause_control = None
        self._minimum_inference_stamp_ns = None

    @classmethod
    def for_test(cls, *, resources, catalog, observe_initial):
        return cls(
            resources,
            catalog=catalog,
            dependencies={"observe_initial": observe_initial},
        )

    def kwargs(self):
        return {name: getattr(self, name) for name in self.REQUIRED}

    RUNNING_EVIDENCE_TIMEOUT_S = 5.0


