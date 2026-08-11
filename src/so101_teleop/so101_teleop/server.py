"""Simulation-only Teleop service backed by live ROS 2 actions and MoveIt services.

The API process never invents a successful robot operation: joint plans come
from ``/plan_kinematic_path`` and executions use MoveIt's
``/execute_trajectory`` action.  The worker owns rclpy subscriptions, TF and
all action/service clients.  This keeps browser code out of the ROS graph and
makes controller/MoveIt unavailability a fail-closed API result.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import re
import subprocess
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import rclpy
from control_msgs.action import FollowJointTrajectory
from controller_manager_msgs.srv import ListControllers
from geometry_msgs.msg import PoseStamped
from moveit_msgs.action import ExecuteTrajectory
from moveit_msgs.msg import Constraints, JointConstraint, MoveItErrorCodes
from moveit_msgs.srv import GetMotionPlan, GetPositionIK, GetStateValidity
from moveit_msgs.msg import RobotState
from rclpy.action import ActionClient
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from sensor_msgs.msg import JointState
from std_msgs.msg import Empty, String
from tf2_ros import Buffer, TransformListener
from tf2_msgs.msg import TFMessage
from ros_gz_interfaces.msg import Contacts
from gz.transport13 import Node as GzTransportNode
from gz.msgs10.pose_v_pb2 import Pose_V
from gz.msgs10.stringmsg_pb2 import StringMsg

from .api import create_app, validate_bind_address
from .backends.protocol import (
    BackendEnvelope,
    BackendProtocol,
    ResetRequest,
    SceneRequest,
    WorkflowRequest,
)
from .camera import CameraController
from .control import CommandCoordinator, CommandIdReused, PlanRejected, PlanStore
from .models import (CommandResult, JointPlanRequest, JointSample, PhysicalOutcomeEvidence,
                     PlanSummary, Pose6D, ServerMode, TcpPlanRequest, TelemetrySnapshot)
from .telemetry import physical_outcome_from_checkpoint, TelemetryCollector

JOINT_START_FINGERPRINT_RESOLUTION_RAD = 1e-4
SO101_JOINT_POSITION_LIMITS_RAD: dict[str, tuple[float, float]] = {
    "1": (-1.91986, 1.91986),
    "2": (-1.74533, 1.74533),
    "3": (-1.74533, 1.5708),
    "4": (-1.65806, 1.65806),
    "5": (-2.79253, 2.79253),
    "6": (-0.059600220867817, 1.74533),
}
TELEOP_ENVIRONMENT_KEYS = (
    "ROS_DOMAIN_ID", "ROS_DISTRO", "ROS_VERSION", "ROS_PYTHON_VERSION",
    "ROS_AUTOMATIC_DISCOVERY_RANGE", "AMENT_PREFIX_PATH", "COLCON_PREFIX_PATH",
    "GZ_PARTITION", "GZ_CONFIG_PATH", "GZ_SIM_RESOURCE_PATH",
    "GZ_SIM_SYSTEM_PLUGIN_PATH", "PYTHONPATH", "LD_LIBRARY_PATH",
)


def read_teleop_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Return only environment metadata approved for operator diagnostics."""
    return {key: environment[key] for key in TELEOP_ENVIRONMENT_KEYS if environment.get(key)}


def _quaternion_to_rpy(x: float, y: float, z: float, w: float) -> tuple[float, float, float]:
    sinr = 2.0 * (w * x + y * z); cosr = 1.0 - 2.0 * (x * x + y * y)
    roll = math.atan2(sinr, cosr)
    sinp = max(-1.0, min(1.0, 2.0 * (w * y - z * x)))
    pitch = math.asin(sinp)
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return roll, pitch, yaw


def _rpy_to_quaternion(roll: float, pitch: float, yaw: float) -> tuple[float, float, float, float]:
    cr, sr = math.cos(roll / 2), math.sin(roll / 2)
    cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
    cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
    return (sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy)


def _joint_fingerprint(positions: dict[str, float]) -> str:
    """Quantize feedback at 0.1 mrad; executor still rejects >=1 mrad state drift."""
    return repr(sorted((name, round(value / JOINT_START_FINGERPRINT_RESOLUTION_RAD))
                        for name, value in positions.items()))


@dataclass
class StoredTrajectory:
    summary: PlanSummary
    trajectory: object
    session_id: str
    snapshot_revision: int


class RosTelemetryWorker:
    """The sole owner of ROS graph objects and live MoveIt/controller calls."""
    def __init__(self, backend: BackendProtocol | None) -> None:
        self._backend = backend
        self._collector = TelemetryCollector(); self._lock = threading.Lock()
        self._environment = read_teleop_environment(os.environ)
        self._latest = TelemetrySnapshot(mode=ServerMode.STARTING, environment=self._environment)
        self._joints: dict[str, JointSample] = {}; self._joint_stamp = 0.0
        # A session must be non-empty even when a launch file did not provide
        # one: leases, plans and checkpoints use it as a stale-state boundary.
        self._session_id = os.environ.get("SO101_SIMULATION_SESSION_ID") or f"startup-{uuid.uuid4()}"
        self._attached: bool | None = None; self._moveit_attached: bool | None = None; self._node: Node | None = None
        self._object_pose: Pose6D | None = None; self._object_stamp = 0.0
        self._gazebo_contacts = []; self._contacts_stamp = 0.0
        self._moveit_collisions = []; self._moveit_stamp = 0.0
        self._plans: dict[str, StoredTrajectory] = {}; self._active_goal = None
        self._attachment_evidence: dict[str, str] = {}
        self._physical_outcome: PhysicalOutcomeEvidence | None = None
        self._gazebo_transport = None
        self._scene_revision = 0; self._scene_tuple = None; self._scene_stamp = 0.0

    def start(self) -> None:
        rclpy.init(args=None)
        self._node = Node("so101_teleop_server", parameter_overrides=[
            rclpy.Parameter("use_sim_time", rclpy.Parameter.Type.BOOL, True)])
        self._tf = Buffer(); self._listener = TransformListener(self._tf, self._node, spin_thread=False)
        self._node.create_subscription(JointState, "/joint_states", self._on_joints, 20)
        self._node.create_subscription(String, "/so101/object_attached_event", self._on_attachment, 10)
        self._node.create_subscription(TFMessage, "/so101/gazebo_pose_info", self._on_gazebo_pose, 20)
        self._node.create_subscription(Contacts, "/task_object/contacts", self._on_contacts, 20)
        self._attach_pub = self._node.create_publisher(Empty, "/so101/attach_object", 10)
        self._detach_pub = self._node.create_publisher(Empty, "/so101/detach_object", 10)
        self._plan_client = self._node.create_client(GetMotionPlan, "/plan_kinematic_path")
        self._ik_client = self._node.create_client(GetPositionIK, "/compute_ik")
        self._state_validity = self._node.create_client(GetStateValidity, "/check_state_validity")
        self._controllers = self._node.create_client(ListControllers, "/controller_manager/list_controllers")
        self._execute = ActionClient(self._node, ExecuteTrajectory, "/execute_trajectory")
        self._arm = ActionClient(self._node, FollowJointTrajectory,
                                 "/arm_controller/follow_joint_trajectory")
        self._gripper = ActionClient(self._node, FollowJointTrajectory,
                                     "/gripper_controller/follow_joint_trajectory")
        self._node.create_timer(0.20, self._publish_snapshot)
        executor = SingleThreadedExecutor(); executor.add_node(self._node)
        threading.Thread(target=executor.spin, name="so101-rclpy", daemon=True).start()
        threading.Thread(target=self._state_validity_sampler, name="so101-state-validity", daemon=True).start()
        self._gazebo_transport = GzTransportNode()
        self._gazebo_transport.subscribe(Pose_V, "/world/so101_pick_place/pose/info", self._on_gazebo_pose_v)
        self._gazebo_transport.subscribe(StringMsg, "/so101/object_attached", self._on_gazebo_attachment_state)
        threading.Thread(target=self._scene_observer_sampler, name="so101-scene-observer", daemon=True).start()

    def _on_joints(self, message: JointState) -> None:
        indexed = {name: index for index, name in enumerate(message.name)}
        self._joints = {name: JointSample(name=name, position_rad=message.position[indexed[name]],
                         velocity_rad_s=message.velocity[indexed[name]] if indexed[name] < len(message.velocity) else 0.0,
                         lower_limit_rad=SO101_JOINT_POSITION_LIMITS_RAD[name][0],
                         upper_limit_rad=SO101_JOINT_POSITION_LIMITS_RAD[name][1])
                        for name in map(str, range(1, 7)) if name in indexed}
        self._joint_stamp = time.time()

    def _on_attachment(self, message: String) -> None:
        if message.data in ("attached", "detached"):
            self._attached = message.data == "attached"

    def _on_gazebo_pose(self, message: TFMessage) -> None:
        """The bridge is diagnostic only: Pose_V may lose all entity names."""
        return

    def _on_gazebo_pose_v(self, message: Pose_V) -> None:
        """Gazebo Pose_V carries the authoritative entity identity and world pose."""
        for pose in message.pose:
            if pose.name != "plastic_cup":
                continue
            roll, pitch, yaw = _quaternion_to_rpy(pose.orientation.x, pose.orientation.y,
                                                   pose.orientation.z, pose.orientation.w)
            with self._lock:
                self._object_pose = Pose6D(frame_id="world", tcp_frame="plastic_cup",
                    x_m=pose.position.x, y_m=pose.position.y, z_m=pose.position.z,
                    roll_rad=roll, pitch_rad=pitch, yaw_rad=yaw)
                self._object_stamp = time.time()
            return

    def _on_gazebo_attachment_state(self, message: StringMsg) -> None:
        """Durable Gazebo relay state is the authority for initial detached evidence."""
        if message.data in ("attached", "detached"):
            with self._lock:
                self._attached = message.data == "attached"
                self._record_scene_observation(self._attached, self._moveit_attached)

    def _record_scene_observation(self, gazebo_attached: bool | None, moveit_attached: bool | None) -> None:
        """Only an independently observed complete tuple can establish/change scene revision."""
        if gazebo_attached is None or moveit_attached is None:
            return
        observed = (gazebo_attached, moveit_attached)
        if self._scene_tuple is None:
            self._scene_tuple = observed
        elif self._scene_tuple != observed:
            self._scene_tuple = observed
            self._scene_revision += 1
        self._scene_stamp = time.time()

    def _scene_observer_sampler(self) -> None:
        """Planning Scene attachment is sampled independently of mutation commands."""
        while rclpy.ok():
            try:
                self.query_moveit_attachment()
            except RuntimeError:
                self._moveit_attached = None
            time.sleep(1.0)

    def _on_contacts(self, message: Contacts) -> None:
        from .models import CollisionPair
        self._gazebo_contacts = [CollisionPair(source="gazebo_contacts", object_a=item.collision1.name,
            object_b=item.collision2.name, depth_m=max(item.depths) if item.depths else None,
            first_seen_at=time.time(), last_seen_at=time.time()) for item in message.contacts]
        self._contacts_stamp = time.time()

    def _state_validity_sampler(self) -> None:
        while rclpy.ok():
            try:
                self._sample_state_validity()
            except Exception:
                self._moveit_collisions = []
                self._moveit_stamp = 0.0
            time.sleep(1.0)

    def _sample_state_validity(self) -> None:
        if self._node is None or not self._state_validity.wait_for_service(timeout_sec=0.2):
            return
        positions = self._current_positions()
        request = GetStateValidity.Request(); request.group_name = "arm"
        request.robot_state = RobotState(); request.robot_state.joint_state.name = [str(i) for i in range(1, 7)]
        request.robot_state.joint_state.position = [positions[str(i)] for i in range(1, 7)]
        future = self._state_validity.call_async(request); deadline = time.monotonic() + 1.0
        while not future.done() and time.monotonic() < deadline: time.sleep(.01)
        if not future.done() or future.result() is None: return
        from .models import CollisionPair
        result = future.result()
        self._moveit_collisions = [CollisionPair(source="moveit_check_state_validity", object_a=c.contact_body_1,
            object_b=c.contact_body_2, depth_m=c.depth, first_seen_at=time.time(), last_seen_at=time.time()) for c in result.contacts]
        self._moveit_stamp = time.time()

    def _call(self, client, request, timeout_s: float = 5.0):
        if not client.wait_for_service(timeout_sec=min(timeout_s, 1.0)):
            raise RuntimeError("ROS_SERVICE_UNAVAILABLE")
        future = client.call_async(request); deadline = time.monotonic() + timeout_s
        while not future.done() and time.monotonic() < deadline: time.sleep(0.01)
        if not future.done(): raise RuntimeError("ROS_SERVICE_TIMEOUT")
        return future.result()

    def _controllers_state(self) -> dict[str, str]:
        # This runs in the single-threaded executor timer.  Calling a service
        # synchronously from this callback would starve that same executor, so
        # use action-server graph readiness here; command paths still receive
        # the controller action result before reporting success.
        return {
            "arm_controller": "active" if self._arm.server_is_ready() else "inactive",
            "gripper_controller": "active" if self._gripper.server_is_ready() else "inactive",
        }

    def _tcp(self) -> Pose6D | None:
        try:
            transform = self._tf.lookup_transform("world", "so101_tcp", rclpy.time.Time(), timeout=rclpy.duration.Duration(seconds=0.02))
        except Exception:
            return None
        t = transform.transform.translation; q = transform.transform.rotation
        roll, pitch, yaw = _quaternion_to_rpy(q.x, q.y, q.z, q.w)
        return Pose6D(frame_id="world", tcp_frame="so101_tcp", x_m=t.x, y_m=t.y, z_m=t.z,
                      roll_rad=roll, pitch_rad=pitch, yaw_rad=yaw)

    def _publish_snapshot(self) -> None:
        tcp = self._tcp(); now = time.time(); controllers = self._controllers_state()
        fresh = self._joint_stamp and now - self._joint_stamp <= 0.5
        from .models import CollisionPair
        object_age = max(0.0, now - self._object_stamp) if self._object_stamp else 999.0
        contact_age = max(0.0, now - self._contacts_stamp) if self._contacts_stamp else 999.0
        moveit_age = max(0.0, now - self._moveit_stamp) if self._moveit_stamp else 999.0
        gazebo_contacts = self._gazebo_contacts if contact_age <= 2.0 else [CollisionPair(source="gazebo_contacts:unknown" if not self._contacts_stamp else "gazebo_contacts:stale", object_a="unknown", object_b="unknown")]
        moveit_collisions = self._moveit_collisions if moveit_age <= 2.0 else [CollisionPair(source="moveit_check_state_validity:unknown" if not self._moveit_stamp else "moveit_check_state_validity:stale", object_a="unknown", object_b="unknown")]
        mode = ServerMode.READY if fresh and len(self._joints) == 6 and tcp and all(
            controllers.get(name) == "active" for name in ("arm_controller", "gripper_controller")) else ServerMode.READ_ONLY
        snapshot = TelemetrySnapshot(mode=mode, simulation_session_id=self._session_id,
            environment=self._environment,
            joints=dict(self._joints), tcp=tcp, object_pose=self._object_pose if object_age <= 2.0 else None,
            controllers=controllers, gazebo_attached=self._attached, moveit_attached=self._moveit_attached,
            gazebo_contacts=gazebo_contacts, moveit_collisions=moveit_collisions,
            source_ages_s={"joints": max(0.0, now - self._joint_stamp) if self._joint_stamp else 999.0,
                           "tcp": 0.0 if tcp else 999.0, "object": object_age, "gazebo_contacts": contact_age,
                           "moveit_collisions": moveit_age, "scene": max(0.0, now - self._scene_stamp) if self._scene_stamp else 999.0},
            scene_revision=self._scene_revision, revision=int(now * 1000),
            physical_outcome=self._physical_outcome)
        with self._lock: self._latest = self._collector.publish(snapshot)

    def snapshot(self) -> TelemetrySnapshot:
        with self._lock: return self._latest.copy(deep=True)

    def _current_positions(self) -> dict[str, float]:
        snapshot = self.snapshot()
        if set(snapshot.joints) != {str(index) for index in range(1, 7)}:
            raise RuntimeError("READINESS_JOINTS_MISSING")
        return {name: sample.position_rad for name, sample in snapshot.joints.items()}

    def plan_joints(
        self,
        target: dict[str, float],
        velocity_scaling_factor: float = 0.10,
        acceleration_scaling_factor: float = 0.10,
    ) -> StoredTrajectory:
        start = self._current_positions(); arm = {str(i): float(target[str(i)]) for i in range(1, 6)}
        request = GetMotionPlan.Request(); motion = request.motion_plan_request
        motion.group_name = "arm"; motion.allowed_planning_time = 3.0; motion.num_planning_attempts = 1
        motion.max_velocity_scaling_factor = velocity_scaling_factor
        motion.max_acceleration_scaling_factor = acceleration_scaling_factor
        motion.start_state.joint_state.name = [str(i) for i in range(1, 6)]
        motion.start_state.joint_state.position = [start[str(i)] for i in range(1, 6)]
        goal = Constraints(); goal.joint_constraints = [JointConstraint(joint_name=name, position=value,
            tolerance_above=0.0005, tolerance_below=0.0005, weight=1.0) for name, value in arm.items()]
        motion.goal_constraints = [goal]
        response = self._call(self._plan_client, request, 6.0).motion_plan_response
        if response.error_code.val != MoveItErrorCodes.SUCCESS or not response.trajectory.joint_trajectory.points:
            raise RuntimeError(f"MOVEIT_PLAN_FAILED_{response.error_code.val}")
        trajectory = response.trajectory; points = trajectory.joint_trajectory.points
        seconds = points[-1].time_from_start.sec + points[-1].time_from_start.nanosec / 1e9
        summary = PlanSummary(plan_id=str(uuid.uuid4()), start_fingerprint=_joint_fingerprint({str(i): start[str(i)] for i in range(1, 6)}),
            target_fingerprint=repr(sorted(arm.items())), scene_revision=self.snapshot().scene_revision, expires_at_monotonic=time.monotonic() + 30.0,
            trajectory_points=len(points), estimated_duration_s=seconds,
            max_joint_delta_rad=max(abs(arm[name] - start[name]) for name in arm), collisions=[])
        stored = StoredTrajectory(summary, trajectory, self.snapshot().simulation_session_id,
                                  self.snapshot().revision); self._plans[summary.plan_id] = stored
        return stored

    def plan_tcp(self, target: Pose6D) -> StoredTrajectory:
        start = self._current_positions(); request = GetPositionIK.Request(); ik = request.ik_request
        ik.group_name = "arm"; ik.ik_link_name = target.tcp_frame; ik.avoid_collisions = True
        ik.robot_state.joint_state.name = [str(i) for i in range(1, 6)]
        ik.robot_state.joint_state.position = [start[str(i)] for i in range(1, 6)]
        ik.pose_stamped = PoseStamped(); ik.pose_stamped.header.frame_id = target.frame_id
        ik.pose_stamped.pose.position.x, ik.pose_stamped.pose.position.y, ik.pose_stamped.pose.position.z = target.x_m, target.y_m, target.z_m
        q = _rpy_to_quaternion(target.roll_rad, target.pitch_rad, target.yaw_rad)
        ik.pose_stamped.pose.orientation.x, ik.pose_stamped.pose.orientation.y, ik.pose_stamped.pose.orientation.z, ik.pose_stamped.pose.orientation.w = q
        ik.timeout.sec = 60
        response = self._call(self._ik_client, request, 65.0)
        if response.error_code.val != MoveItErrorCodes.SUCCESS: raise RuntimeError(f"MOVEIT_IK_FAILED_{response.error_code.val}")
        positions = dict(zip(response.solution.joint_state.name, response.solution.joint_state.position))
        stored = self.plan_joints({str(i): positions[str(i)] for i in range(1, 6)})
        stored.summary.ik_solution_rad.update({str(i): positions[str(i)] for i in range(1, 6)})
        return stored

    def execute_plan(self, plan_id: str) -> None:
        plan = self._plans.get(plan_id)
        if plan is None: raise RuntimeError("PLAN_NOT_FOUND")
        if plan.summary.expires_at_monotonic <= time.monotonic(): raise RuntimeError("PLAN_EXPIRED")
        goal = ExecuteTrajectory.Goal(); goal.trajectory = plan.trajectory
        if not self._execute.wait_for_server(timeout_sec=2.0): raise RuntimeError("MOVEIT_EXECUTE_UNAVAILABLE")
        accepted = self._execute.send_goal_async(goal); deadline = time.monotonic()+5
        while not accepted.done() and time.monotonic()<deadline: time.sleep(.01)
        handle = accepted.result()
        if handle is None or not handle.accepted: raise RuntimeError("MOVEIT_EXECUTE_REJECTED")
        self._active_goal = handle; result = handle.get_result_async(); deadline=time.monotonic()+30
        while not result.done() and time.monotonic()<deadline: time.sleep(.02)
        if not result.done() or result.result().result.error_code.val != MoveItErrorCodes.SUCCESS: raise RuntimeError("MOVEIT_EXECUTE_FAILED")
        self._plans.pop(plan_id, None)

    def gripper(self, position: float) -> None:
        from trajectory_msgs.msg import JointTrajectory, JointTrajectoryPoint
        goal = FollowJointTrajectory.Goal(); goal.trajectory = JointTrajectory(joint_names=["6"])
        point=JointTrajectoryPoint(positions=[position]); point.time_from_start.sec=1; goal.trajectory.points=[point]
        if not self._gripper.wait_for_server(timeout_sec=2): raise RuntimeError("GRIPPER_ACTION_UNAVAILABLE")
        future=self._gripper.send_goal_async(goal); deadline=time.monotonic()+3
        while not future.done() and time.monotonic()<deadline: time.sleep(.01)
        handle=future.result()
        if handle is None or not handle.accepted: raise RuntimeError("GRIPPER_ACTION_REJECTED")
        result=handle.get_result_async(); deadline=time.monotonic()+8
        while not result.done() and time.monotonic()<deadline: time.sleep(.01)
        if not result.done() or result.result().result.error_code != 0: raise RuntimeError("GRIPPER_ACTION_FAILED")

    def publish_attachment(self, attach: bool) -> None:
        (self._attach_pub if attach else self._detach_pub).publish(Empty())

    def _wait_gazebo_attachment(self, attached: bool, timeout_s: float = 4.0) -> bool:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if self.snapshot().gazebo_attached is attached:
                return True
            time.sleep(.05)
        return False

    def query_moveit_attachment(self) -> bool:
        """Read the Planning Scene owner; never infer this from a requested command."""
        if self._backend is None:
            raise RuntimeError("BACKEND_NOT_CONFIGURED")
        envelope = self._backend.scene_operation(
            SceneRequest("observe", self._session_id)
        )
        if not envelope.ok:
            code = envelope.error.code if envelope.error is not None else "BACKEND_OPERATION_FAILED"
            raise RuntimeError(code)
        observed = (envelope.result or {}).get("task_object_attached")
        if isinstance(observed, str):
            observed = {"true": True, "false": False}.get(observed.casefold())
        if not isinstance(observed, bool):
            self._moveit_attached = None
            raise RuntimeError("MOVEIT_SCENE_OBSERVATION_UNPARSEABLE")
        self._moveit_attached = observed
        with self._lock:
            self._record_scene_observation(self._attached, self._moveit_attached)
        return self._moveit_attached

    def _rollback_gazebo_attachment(self, expected: bool) -> bool:
        self.publish_attachment(expected)
        return self._wait_gazebo_attachment(expected)

    def attachment_transaction(self, attach: bool) -> bool:
        """Commit Gazebo then MoveIt, proving both layers and rolling Gazebo back on failure."""
        self._attachment_evidence = {"requested": "attached" if attach else "detached"}
        self.publish_attachment(attach)
        if not self._wait_gazebo_attachment(attach):
            self._attachment_evidence["gazebo"] = "timeout"
            raise RuntimeError("GAZEBO_ATTACHMENT_CONVERGENCE_TIMEOUT")
        self._attachment_evidence["gazebo"] = "attached" if attach else "detached"
        try:
            # The selected backend owner performs the scene mutation. Its subsequent
            # `observe` call is a separate PlanningScene query, not command echo.
            if self._backend is None:
                raise RuntimeError("BACKEND_NOT_CONFIGURED")
            envelope = self._backend.scene_operation(
                SceneRequest("attach" if attach else "detach", self._session_id)
            )
            if not envelope.ok:
                code = envelope.error.code if envelope.error is not None else "BACKEND_OPERATION_FAILED"
                raise RuntimeError(code)
            if self.query_moveit_attachment() is not attach:
                raise RuntimeError("MOVEIT_SCENE_STATE_MISMATCH")
            self._attachment_evidence["moveit"] = "attached" if attach else "detached"
            return True
        except RuntimeError as error:
            # Restore the prior Gazebo state when the independent MoveIt layer
            # cannot commit or cannot be observed.  The returned code records
            # whether the compensation itself converged.
            self._moveit_attached = None
            try:
                envelope = self._backend.scene_operation(
                    SceneRequest("detach" if attach else "attach", self._session_id)
                )
                if not envelope.ok:
                    code = envelope.error.code if envelope.error is not None else "BACKEND_OPERATION_FAILED"
                    raise RuntimeError(code)
                compensated = self.query_moveit_attachment() is (not attach)
                self._attachment_evidence["moveit_rollback"] = "converged" if compensated else "mismatch"
            except RuntimeError:
                self._attachment_evidence["moveit_rollback"] = "failed"
            rolled_back = self._rollback_gazebo_attachment(not attach)
            self._attachment_evidence["gazebo_rollback"] = "converged" if rolled_back else "failed"
            try:
                observed = self.query_moveit_attachment()
                self._attachment_evidence["moveit_after_failure"] = "attached" if observed else "detached"
            except RuntimeError:
                self._moveit_attached = None
                self._attachment_evidence["moveit_after_failure"] = "unavailable"
            if rolled_back:
                prefix = "MOVEIT_SCENE_STATE_MISMATCH" if str(error) == "MOVEIT_SCENE_STATE_MISMATCH" else "MOVEIT_SCENE_OWNER_FAILED"
                raise RuntimeError(f"{prefix}_GAZEBO_ROLLED_BACK") from error
            raise RuntimeError("MOVEIT_SCENE_FAILURE_GAZEBO_ROLLBACK_FAILED") from error

    def capture_gazebo(self) -> Path:
        """Capture only the unique Gazebo X11 window, never the desktop."""
        root=subprocess.run(["xprop", "-root", "_NET_CLIENT_LIST"], text=True, capture_output=True, check=False)
        ids=re.findall(r"0x[0-9a-fA-F]+", root.stdout); matches=[]
        for window_id in ids:
            props=subprocess.run(["xprop", "-id", window_id, "WM_CLASS", "_NET_WM_NAME"], text=True, capture_output=True, check=False).stdout.casefold()
            if "gz-sim-gui" in props or "gazebo gui" in props: matches.append(window_id)
        if len(matches) != 1: raise RuntimeError("GAZEBO_WINDOW_AMBIGUOUS" if matches else "GAZEBO_WINDOW_NOT_FOUND")
        info=subprocess.run(["xwininfo", "-id", matches[0]], text=True, capture_output=True, check=False).stdout
        def field(name: str) -> int:
            found=re.search(rf"{re.escape(name)}:\s*(-?\d+)", info)
            if not found: raise RuntimeError("GAZEBO_WINDOW_GEOMETRY_FAILED")
            return int(found.group(1))
        x,y,width,height=(field("Absolute upper-left X"),field("Absolute upper-left Y"),field("Width"),field("Height"))
        directory=Path(os.environ.get("SO101_TELEOP_CAPTURE_DIR", "/tmp/so101-teleop-captures")); directory.mkdir(parents=True, exist_ok=True)
        output=directory / f"gazebo-{int(time.time()*1000)}.png"
        result=subprocess.run(["ffmpeg","-y","-hide_banner","-loglevel","error","-f","x11grab","-video_size",f"{width}x{height}","-i",f"{os.environ.get('DISPLAY','')}+{x},{y}","-frames:v","1",str(output)], capture_output=True, text=True, check=False)
        if result.returncode or not output.is_file() or output.stat().st_size < 64: raise RuntimeError("GAZEBO_SCREENSHOT_CAPTURE_FAILED")
        return output

    def cancel(self) -> None:
        if self._active_goal is not None: self._active_goal.cancel_goal_async()

    def start_fingerprint(self) -> str:
        current=self._current_positions()
        return _joint_fingerprint({str(i): current[str(i)] for i in range(1, 6)})

    def home(self) -> None:
        stored=self.plan_joints({str(i): 0.0 for i in range(1, 6)})
        self.execute_plan(stored.summary.plan_id)
        self.gripper(-0.059600220867817)

    def invalidate_session(self) -> str:
        self._plans.clear(); self._active_goal=None; self._attached=None; self._session_id=f"reset-{uuid.uuid4()}"
        # /snapshot is served from the telemetry cache; update that cache in
        # the same critical section so a successful reset never exposes the
        # prior session to a command racing the next timer tick.
        with self._lock:
            self._latest.simulation_session_id = self._session_id
        return self._session_id


class TeleopService:
    def __init__(
        self,
        worker: RosTelemetryWorker,
        camera: CameraController | None = None,
        *,
        backend: BackendProtocol,
    ) -> None:
        self._worker=worker; self._commands=CommandCoordinator(); self._plans=PlanStore(); self._lease: tuple[str,float] | None=None
        self._camera = camera
        self._backend = backend
        self._parameters=Path(os.environ.get("SO101_TELEOP_PARAMETERS", "/tmp/so101-teleop-parameters.json"))
        self._workflow: dict[str, tuple[Path, str]] = {}
    async def health(self):
        snapshot=self._worker.snapshot(); return {"ok": True, "simulation_only": True, "mode": snapshot.mode,
            "ros_worker": "rclpy", "moveit_plan_service": "/plan_kinematic_path", "moveit_execute_action": "/execute_trajectory"}
    async def current_snapshot(self): return self._worker.snapshot()
    async def capabilities(self):
        profile = self._backend.profile
        return {
            "simulation_only": True,
            "bind_policy": "loopback_or_tailscale",
            "backend": profile.backend,
            "owner_package": profile.owner_package,
            "owner_executable": profile.probe.executable,
            "capabilities": self._backend.capabilities().as_dict(),
        }
    async def camera_presets(self):
        if not self._backend.capabilities().camera_presets:
            return {"presets": []}
        return {"presets": self._camera.names if self._camera else []}
    async def telemetry_wait(self): await asyncio.sleep(.2)
    def _result(self, body, ok, code, message, **kw): return CommandResult(command_id=body.get("command_id", ""), accepted=ok, succeeded=ok, code=code, message=message, snapshot_revision=self._worker.snapshot().revision, **kw)
    def _lease_ok(self, body) -> bool: return self._lease is not None and self._lease[0] == body.get("lease_id") and self._lease[1] > time.monotonic()
    def _ready(self, body) -> bool:
        snapshot=self._worker.snapshot()
        return snapshot.mode is ServerMode.READY and self._lease_ok(body) and (
            not body.get("session_id") or body["session_id"] == snapshot.simulation_session_id)
    def _mutation_gate(self, body):
        if self._worker.snapshot().mode is not ServerMode.READY: return self._result(body,False,"READINESS_NOT_SATISFIED","fresh ROS, TF and controller evidence required")
        if not self._lease_ok(body): return self._result(body,False,"LEASE_REQUIRED","valid lease required")
        if body.get("session_id") and body["session_id"] != self._worker.snapshot().simulation_session_id: return self._result(body,False,"SESSION_MISMATCH","simulation session changed")
        return None
    def _required_capability(self, name: str) -> str | None:
        if name.startswith("workflow_"):
            operation = name.removeprefix("workflow_")
            return {
                "start": "workflow_start",
                "run": "workflow_run",
                "step": "workflow_resume",
                "resume": "workflow_resume",
                "force-continue": "workflow_resume",
                "reset": "workflow_resume",
                "stop": "workflow_resume",
            }.get(operation)
        return {
            "simulation_reset": "reset_world",
            "scene_repair": "scene_operations",
            "attachment_attach": "scene_operations",
            "attachment_detach": "scene_operations",
            "plan_joints": "manual_joint_execute",
            "plan_tcp": "manual_tcp_execute",
            "gripper": "manual_joint_execute",
            "robot_home": "manual_joint_execute",
            "screenshot": "physical_observation",
            "camera_preset": "camera_presets",
        }.get(name)
    def _backend_unavailable(self, body, capability: str):
        return self._result(
            body,
            False,
            "BACKEND_CAPABILITY_UNAVAILABLE",
            f"{capability} is unavailable for backend {self._backend.profile.backend}",
            layers={
                "backend": self._backend.profile.backend,
                "owner_package": self._backend.profile.owner_package,
                "capability": capability,
            },
        )
    def _backend_result(self, body, envelope: BackendEnvelope):
        if envelope.ok:
            return None
        error = envelope.error
        return self._result(
            body,
            False,
            error.code if error is not None else "BACKEND_OPERATION_FAILED",
            error.message if error is not None else "backend operation failed",
            layers={
                "backend": envelope.backend,
                "owner_package": envelope.owner_package,
                "owner_executable": envelope.owner_executable,
                "owner_failure_code": error.owner_failure_code if error else None,
            },
        )
    async def execute_plan(self, plan_id: str, body: dict):
        return await self.command("execute", {**body, "plan_id": plan_id})
    async def command(self, name: str, body: dict):
        command_id=body.get("command_id", "")
        if not command_id: return self._result(body, False, "COMMAND_ID_REQUIRED", "command_id is required")
        capability = self._required_capability(name)
        if capability is not None and not getattr(self._backend.capabilities(), capability):
            return self._backend_unavailable(body, capability)
        # Lease liveness is independent of mutation serialization.  A valid
        # operator must be able to renew while a long MoveIt/workflow owner
        # holds the command lock, otherwise the UI loses its lease even though
        # the command it started is still progressing.
        if name == "lease_renew":
            if not self._lease_ok(body): return self._result(body,False,"LEASE_REQUIRED","valid lease required")
            self._lease=(self._lease[0],time.monotonic()+30); return self._result(body,True,"OK","lease renewed")
        async def operation():
            try:
                if name == "lease":
                    if self._lease is not None and self._lease[1] > time.monotonic():
                        return self._result(body,False,"LEASE_BUSY","another operator holds the control lease")
                    lease_id=str(uuid.uuid4()); self._lease=(lease_id,time.monotonic()+30); return self._result(body,True,"OK","lease acquired",layers={"lease_id":lease_id})
                if name in ("plan_joints", "plan_tcp"):
                    if gate:=self._mutation_gate(body): return gate
                    if name == "plan_joints":
                        velocity_scaling = float(body.get("velocity_scaling_factor", 0.10))
                        acceleration_scaling = float(body.get("acceleration_scaling_factor", 0.10))
                        if not 0.01 <= velocity_scaling <= 0.10 or not 0.01 <= acceleration_scaling <= 0.10:
                            raise ValueError("PLAN_SCALING_OUT_OF_RANGE")
                        stored=await asyncio.to_thread(
                            self._worker.plan_joints,
                            body.get("target_joints_rad", {}),
                            velocity_scaling,
                            acceleration_scaling,
                        )
                    else: stored=await asyncio.to_thread(self._worker.plan_tcp, Pose6D(**body["target"]))
                    self._plans.put(stored.summary); return self._result(body,True,"OK","MoveIt plan created",layers={"plan_id":stored.summary.plan_id,"trajectory_points":str(stored.summary.trajectory_points)})
                if name == "execute":
                    if gate:=self._mutation_gate(body): return gate
                    plan_id=body.get("plan_id", "")
                    stored=self._worker._plans.get(plan_id)
                    if stored is None: raise PlanRejected("PLAN_NOT_FOUND")
                    live_session=self._worker.snapshot().simulation_session_id
                    if stored.session_id != live_session: raise PlanRejected("PLAN_STALE_SESSION")
                    plan=self._plans.require_executable(self._worker.start_fingerprint(), self._worker.snapshot().scene_revision, plan_id)
                    await asyncio.to_thread(self._worker.execute_plan, plan.plan_id); self._plans.clear(); return self._result(body,True,"OK","MoveIt trajectory executed")
                if name == "gripper":
                    if gate:=self._mutation_gate(body): return gate
                    await asyncio.to_thread(self._worker.gripper, float(body["target_position_rad"])); return self._result(body,True,"OK","gripper action completed")
                if name == "cancel":
                    if gate:=self._mutation_gate(body): return gate
                    await asyncio.to_thread(self._worker.cancel); return self._result(body,True,"OK","active MoveIt goal cancellation requested")
                if name in ("attachment_attach", "attachment_detach"):
                    if gate:=self._mutation_gate(body): return gate
                    attached=name == "attachment_attach"
                    if not await asyncio.to_thread(self._worker.attachment_transaction, attached): return self._result(body,False,"GAZEBO_ATTACHMENT_UNVERIFIED","Gazebo attachment event did not converge")
                    self._worker._plans.clear(); self._plans.clear()
                    return self._result(body,True,"OK","Gazebo and independently queried MoveIt scene converged",layers=dict(getattr(self._worker, "_attachment_evidence", {"gazebo": "attached" if attached else "detached", "moveit": "unreported"})))
                if name == "screenshot":
                    if gate:=self._mutation_gate(body): return gate
                    path=await asyncio.to_thread(self._worker.capture_gazebo); return self._result(body,True,"OK","Gazebo window PNG captured",data={"url":"/captures/"+path.name})
                if name == "camera_preset":
                    if gate:=self._mutation_gate(body): return gate
                    if self._camera is None: return self._result(body,False,"GAZEBO_CAMERA_NOT_CONFIGURED","camera presets are unavailable")
                    preset = str(body.get("preset", ""))
                    await asyncio.to_thread(self._camera.apply, preset)
                    return self._result(body,True,"OK",f"Gazebo camera moved to {preset}",data={"preset":preset})
                if name == "parameters_save":
                    if gate:=self._mutation_gate(body): return gate
                    payload={"target_joints_rad":body.get("target_joints_rad",{}),"target_tcp":body.get("target_tcp"),"saved_session_id":self._worker.snapshot().simulation_session_id}
                    self._parameters.parent.mkdir(parents=True,exist_ok=True); self._parameters.write_text(json.dumps(payload,indent=2)); return self._result(body,True,"OK","target parameters saved",data={"parameters":payload})
                if name == "parameters_load":
                    if gate:=self._mutation_gate(body): return gate
                    if not self._parameters.is_file(): return self._result(body,False,"PARAMETERS_NOT_FOUND","no saved server parameter file")
                    payload=json.loads(self._parameters.read_text()); return self._result(body,True,"OK","target parameters restored",data={"parameters":payload})
                if name in ("robot_home", "scene_repair", "simulation_reset"):
                    if gate:=self._mutation_gate(body): return gate
                    required="CONFIRM " + name.upper()
                    if body.get("confirmation") != required: return self._result(body,False,"CONFIRMATION_REQUIRED","second server-side confirmation required")
                    if name == "robot_home":
                        await asyncio.to_thread(self._worker.home)
                        # Home changes the real start state; invalidate both the
                        # service summary and the worker's executable trajectory.
                        self._worker._plans.clear(); self._plans.clear()
                        return self._result(body,True,"OK","MoveIt home trajectory and gripper action converged",layers={"owner":"moveit_execute_trajectory"})
                    if name == "simulation_reset":
                        envelope = await asyncio.to_thread(
                            self._backend.reset_world,
                            ResetRequest(self._worker.snapshot().simulation_session_id),
                        )
                        if failure := self._backend_result(body, envelope):
                            return failure
                        new_session=self._worker.invalidate_session(); self._plans.clear(); self._lease=None; self._workflow.clear(); self._commands.clear()
                        return self._result(body,True,"OK","backend reset owner converged and prior session invalidated",layers={"owner":envelope.owner_executable,"session_id":new_session})
                    envelope = await asyncio.to_thread(
                        self._backend.scene_operation,
                        SceneRequest("upsert", self._worker.snapshot().simulation_session_id),
                    )
                    if failure := self._backend_result(body, envelope):
                        return failure
                    # Scene repair can alter collision/attachment state.  The
                    # worker cache must not retain a trajectory the API no
                    # longer exposes as current.
                    self._worker._plans.clear(); self._plans.clear()
                    return self._result(body,True,"OK","backend scene owner converged",layers={"owner":envelope.owner_executable})
                if name.startswith("workflow_"):
                    if gate:=self._mutation_gate(body): return gate
                    operation=name.removeprefix("workflow_")
                    session_id=self._worker.snapshot().simulation_session_id
                    if operation in ("start", "run"):
                        if any(workflow_session == session_id
                               for _, workflow_session in self._workflow.values()):
                            return self._result(body,False,"WORKFLOW_ALREADY_STARTED","reset the existing workflow before starting a new one")
                        run_id=str(uuid.uuid4()); checkpoint=Path("/tmp") / f"so101-teleop-workflow-{run_id}.json"; self._workflow[run_id]=(checkpoint,session_id)
                    else:
                        run_id=body.get("run_id", ""); entry=self._workflow.get(run_id)
                        if entry is None: return self._result(body,False,"WORKFLOW_RUN_MISMATCH","unknown workflow run")
                        checkpoint, session=entry
                        if session != session_id: return self._result(body,False,"SESSION_MISMATCH","workflow session invalidated")
                    if operation == "reset":
                        if body.get("confirmation") != "CONFIRM WORKFLOW_RESET": return self._result(body,False,"CONFIRMATION_REQUIRED","second server-side confirmation required")
                        self._workflow.pop(run_id, None); return self._result(body,True,"OK","workflow checkpoint invalidated")
                    if operation == "force-continue":
                        if body.get("operator_confirmation") != "FORCE CONTINUE": return self._result(body,False,"OVERRIDE_NOT_ALLOWED","physical validation confirmation required")
                    if operation == "stop": return self._result(body,True,"OK","workflow is checkpoint-controlled; no transition was requested")
                    envelope = await asyncio.to_thread(
                        self._backend.run_workflow,
                        WorkflowRequest(operation, session_id, checkpoint),
                    )
                    if failure := self._backend_result(body, envelope):
                        if operation in ("start", "run"):
                            self._workflow.pop(run_id, None)
                        return failure
                    output = str((envelope.result or {}).get("trace", ""))
                    trace=output.removeprefix("trace=")
                    states=[state.strip() for state in trace.split("->") if state.strip()]
                    physical_outcome = None
                    if checkpoint.is_file():
                        checkpoint_data = json.loads(checkpoint.read_text())
                        if checkpoint_data.get("last_completed_state") in {
                                "WAIT_RELEASE_SETTLE", "VALIDATE_FINAL_PLACEMENT",
                                "SYNC_WORLD_OBJECT"}:
                            physical_outcome = physical_outcome_from_checkpoint(checkpoint_data)
                            self._worker._physical_outcome = physical_outcome
                    return self._result(body,True,"OK","backend checkpoint owner completed workflow request",data={"workflow":{"run_id":run_id,"current_state":states[-1] if states else "IDLE","next_state":None,"trace":states,"checkpoint_fresh":checkpoint.is_file(),"physical_outcome":physical_outcome.dict() if physical_outcome else None}})
                return self._result(body,False,"READINESS_NOT_SATISFIED",f"{name} requires a live dedicated gateway")
            except (RuntimeError, PlanRejected, KeyError, ValueError) as error:
                layers = dict(getattr(self._worker, "_attachment_evidence", {})) if name.startswith("attachment_") else {}
                return self._result(body,False,str(error),"live ROS operation did not complete", layers=layers)
        try: return await self._commands.run(command_id, repr((name, sorted(body.items()))), operation)
        except CommandIdReused: return self._result(body,False,"COMMAND_ID_REUSED","command_id payload differs")
        except PlanRejected as error: return self._result(body,False,str(error),"command rejected")


def main() -> None:
    from .main import main as lifecycle_main
    lifecycle_main()


if __name__ == "__main__": main()
