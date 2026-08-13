"""ROS composition for Gazebo reset observation, cancellation, and robot control."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import yaml

from ...backends.gazebo.commands import GazeboCommandAdapter
from ...backends.gazebo.reset import (
    GazeboPhysicalResetPort,
    GazeboResetObservationPort,
    GazeboResetState,
    GazeboRobotResetPort,
    GazeboSceneResetPort,
    execute_gazebo_reset_transaction,
)
from ...control.gripper.client import GripperClient
from ...control.moveit.planning import MoveItPlanningClient
from ...control.planning_scene.task_scene import RosTaskScenePort
from ...control.trajectory.executor import MoveItExecutionClient, make_execute_goal
from ...core.domain import ActionStatus
from ...core.task_geometry import Pose7, load_task_geometry
from ...ports.reset import ResetStepReceipt, TransactionalResetReceipt, TransactionalResetRequest


class GazeboAttachmentMonitor:
    """Durable local projection of the detachable-joint StringMsg state."""

    def __init__(self, state: GazeboResetState, topic: str) -> None:
        from gz.msgs10.stringmsg_pb2 import StringMsg
        from gz.transport13 import Node

        self._state = state
        self._node = Node()
        self._topic = topic

        def update(message: StringMsg) -> None:
            value = str(message.data).strip().lower()
            if value in {"attached", "detached"}:
                with self._state._lock:
                    self._state.attached = value == "attached"

        self._node.subscribe(StringMsg, topic, update)

    def close(self) -> None:
        self._node.unsubscribe(self._topic)


def record_gazebo_pose_vector(state: GazeboResetState, message: Any) -> None:
    """Project named Gazebo Pose_V entities without the lossy ROS TF bridge."""

    with state._lock:
        for item in message.pose:
            name = str(item.name)
            if name in {"plastic_cup", "body", "gripper"}:
                state.entity_ids[name] = int(item.id)
            if name != "plastic_cup":
                continue
            state.cup_pose = Pose7(
                (
                    float(item.position.x),
                    float(item.position.y),
                    float(item.position.z),
                    float(item.orientation.x),
                    float(item.orientation.y),
                    float(item.orientation.z),
                    float(item.orientation.w),
                )
            )


class GazeboPoseMonitor:
    """Durable named Gazebo entity projection used by Reset verification."""

    def __init__(self, state: GazeboResetState, topic: str) -> None:
        from gz.msgs10.pose_v_pb2 import Pose_V
        from gz.transport13 import Node

        self._state = state
        self._node = Node()
        self._topic = topic
        self._node.subscribe(
            Pose_V,
            topic,
            lambda message: record_gazebo_pose_vector(self._state, message),
        )

    def close(self) -> None:
        self._node.unsubscribe(self._topic)


class RosGoalCancellationPort:
    _ACTIVE = {1, 2, 3}

    def __init__(self, node: Any, progress, timeout_s: float) -> None:
        from action_msgs.msg import GoalStatusArray
        from action_msgs.srv import CancelGoal

        self._node = node
        self._progress = progress
        self._timeout_s = timeout_s
        self._cancel_type = CancelGoal
        self._clients = {
            "arm": node.create_client(
                CancelGoal, "/arm_controller/follow_joint_trajectory/_action/cancel_goal"
            ),
            "gripper": node.create_client(
                CancelGoal,
                "/gripper_controller/follow_joint_trajectory/_action/cancel_goal",
            ),
        }
        self._statuses: dict[str, tuple[int, ...]] = {"arm": (), "gripper": ()}

        def callback(name: str):
            def update(message: GoalStatusArray) -> None:
                self._statuses[name] = tuple(int(item.status) for item in message.status_list)

            return update

        self._subscriptions = [
            node.create_subscription(
                GoalStatusArray,
                f"/{controller}_controller/follow_joint_trajectory/_action/status",
                callback(controller),
                10,
            )
            for controller in ("arm", "gripper")
        ]

    def _cancel(self, name: str) -> ResetStepReceipt:
        client = self._clients[name]
        if not client.wait_for_service(timeout_sec=self._timeout_s):
            return ResetStepReceipt(
                False,
                f"RESET_{name.upper()}_CANCEL_UNAVAILABLE",
                {"controller": name},
            )
        future = client.call_async(self._cancel_type.Request())
        deadline = time.monotonic() + self._timeout_s
        while not future.done() and time.monotonic() < deadline:
            self._progress()
        if not future.done() or future.result() is None:
            return ResetStepReceipt(
                False,
                f"RESET_{name.upper()}_CANCEL_TIMEOUT",
                {"controller": name},
            )
        response = future.result()
        while time.monotonic() < deadline:
            self._progress()
            active = [value for value in self._statuses[name] if value in self._ACTIVE]
            if not active:
                return ResetStepReceipt(
                    True,
                    None,
                    {
                        "controller": name,
                        "return_code": int(response.return_code),
                        "terminal_statuses": list(self._statuses[name]),
                    },
                )
        return ResetStepReceipt(
            False,
            f"RESET_{name.upper()}_CANCEL_SETTLE_TIMEOUT",
            {"active_statuses": list(self._statuses[name])},
        )

    def cancel_arm_goals(self) -> ResetStepReceipt:
        return self._cancel("arm")

    def cancel_gripper_goals(self) -> ResetStepReceipt:
        return self._cancel("gripper")


class _RefreshingObservationPort:
    def __init__(self, runtime: RosGazeboResetRuntime, delegate: Any) -> None:
        self._runtime = runtime
        self._delegate = delegate

    def observe_initial(self) -> ResetStepReceipt:
        refreshed = self._runtime.refresh_controllers()
        if not refreshed.success:
            return refreshed
        self._runtime.progress()
        return self._delegate.observe_initial()

    def verify_final(self) -> ResetStepReceipt:
        refreshed = self._runtime.refresh_controllers()
        if not refreshed.success:
            return refreshed
        self._runtime.progress()
        return self._delegate.verify_final()


class RosGazeboResetRuntime:
    def __init__(self, share: Path, session_id: str) -> None:
        import rclpy
        from control_msgs.action import FollowJointTrajectory
        from controller_manager_msgs.srv import ListControllers
        from moveit_msgs.action import ExecuteTrajectory
        from moveit_msgs.srv import GetMotionPlan
        from rclpy.action import ActionClient
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from sensor_msgs.msg import JointState
        from tf2_msgs.msg import TFMessage

        self._rclpy = rclpy
        self._owns_rclpy = not rclpy.ok()
        if self._owns_rclpy:
            rclpy.init(args=None)
        self.node = rclpy.create_node("so101_gazebo_transactional_reset")
        self.state = GazeboResetState()
        config = yaml.safe_load((share / "config/gazebo/reset.yaml").read_bytes())
        self.config = config
        self.timeout_s = float(config["operation_timeout_s"])
        self.geometry = load_task_geometry(
            share / "assets/common/geometry-manifest.yaml"
        )
        self._controller_type = ListControllers
        self._controllers = self.node.create_client(
            ListControllers, "/controller_manager/list_controllers"
        )

        def joints(message: JointState) -> None:
            with self.state._lock:
                self.state.positions = {
                    name: float(value)
                    for name, value in zip(message.name, message.position, strict=True)
                }
                self.state.velocities = (
                    {
                        name: float(value)
                        for name, value in zip(message.name, message.velocity, strict=True)
                    }
                    if len(message.name) == len(message.velocity)
                    else {}
                )

        def transforms(message: TFMessage) -> None:
            with self.state._lock:
                self.state.tf_frames.update(item.child_frame_id for item in message.transforms)

        static_tf_qos = QoSProfile(
            depth=100,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
            reliability=ReliabilityPolicy.RELIABLE,
        )

        self._subscriptions = [
            self.node.create_subscription(JointState, config["topics"]["joints"], joints, 100),
            self.node.create_subscription(TFMessage, config["topics"]["tf"], transforms, 100),
            self.node.create_subscription(TFMessage, "/tf_static", transforms, static_tf_qos),
        ]
        self._pose = GazeboPoseMonitor(
            self.state, "/world/so101_pick_place/pose/info"
        )
        self._attachment = GazeboAttachmentMonitor(
            self.state, config["topics"]["attachment_state"]
        )
        scene_adapter = RosTaskScenePort(self.node, "gazebo", self.timeout_s)
        self.scene = GazeboSceneResetPort(scene_adapter, self.geometry)
        self.goals = RosGoalCancellationPort(self.node, self.progress, self.timeout_s)
        commands = GazeboCommandAdapter(
            process_timeout_s=min(5.0, self.timeout_s),
            service_timeout_ms=int(self.timeout_s * 1000),
        )
        deadline = time.monotonic() + self.timeout_s
        entity_ids: dict[str, int] = {}
        while time.monotonic() < deadline:
            entity_ids = self.state.snapshot()["entity_ids"]  # type: ignore[assignment]
            if {"gripper", "body"} <= set(entity_ids):
                break
            self.progress()
        if {"gripper", "body"} <= set(entity_ids):
            attachment_probe = commands.observe_attachment(
                parent_entity_id=entity_ids["gripper"],
                child_entity_id=entity_ids["body"],
            )
            with self.state._lock:
                self.state.attachment_probe = dict(attachment_probe.evidence)
                if attachment_probe.success:
                    self.state.attached = bool(
                        attachment_probe.evidence["attached"]
                    )
        else:
            with self.state._lock:
                self.state.attachment_probe = {
                    "failure_code": "RESET_GAZEBO_ENTITY_IDS_UNAVAILABLE",
                    "entity_ids": entity_ids,
                }
        self.physical = GazeboPhysicalResetPort(
            commands,
            observe_attachment=self._observe_attachment,
            observe_pose=self._observe_pose,
            timeout_s=self.timeout_s,
        )
        plan_client = self.node.create_client(GetMotionPlan, "/plan_kinematic_path")
        execute_client = ActionClient(self.node, ExecuteTrajectory, "/execute_trajectory")
        planner = MoveItPlanningClient(plan_client, progress=self.progress)
        executor = MoveItExecutionClient(
            execute_client, goal_factory=make_execute_goal, progress=self.progress
        )
        gripper_action = ActionClient(
            self.node,
            FollowJointTrajectory,
            "/gripper_controller/follow_joint_trajectory",
        )
        gripper = GripperClient(gripper_action, progress=self.progress)

        def command_gripper(target: float) -> ResetStepReceipt:
            result = gripper.command(target, 2.0, self.timeout_s)
            return ResetStepReceipt(
                result.status is ActionStatus.SUCCEEDED,
                None
                if result.status is ActionStatus.SUCCEEDED
                else "RESET_GRIPPER_OPEN_FAILED",
                {
                    "target": target,
                    "action_status": result.status.value,
                    "action_failure": None
                    if result.failure is None
                    else result.failure.code,
                },
            )

        self.robot = GazeboRobotResetPort(
            planner=planner,
            executor=executor,
            command_gripper=command_gripper,
            observe_joints=self._observe_joints,
            home_positions=tuple(float(value) for value in config["home_positions"]),
            gripper_open_position=float(config["gripper_open_position"]),
            position_tolerance=float(config["position_tolerance"]),
            velocity_tolerance=float(config["velocity_tolerance"]),
            timeout_s=self.timeout_s,
        )
        observation = GazeboResetObservationPort(
            self.state,
            scene_adapter,
            self.geometry,
            tuple(float(value) for value in config["home_positions"]),
            float(config["gripper_open_position"]),
            float(config["position_tolerance"]),
            float(config["velocity_tolerance"]),
        )
        self.observation = _RefreshingObservationPort(self, observation)
        self.request = TransactionalResetRequest(
            backend="gazebo",
            session_id=session_id,
            named_home_state=str(config["named_home_state"]),
            parking_pose=Pose7(tuple(float(value) for value in config["parking_pose_xyz_xyzw"])),
            spawn_pose=self.geometry.object("plastic_cup").pose,
        )

    def progress(self) -> None:
        self._rclpy.spin_once(self.node, timeout_sec=0.01)

    def _observe_attachment(self) -> bool | None:
        self.progress()
        return self.state.snapshot()["attached"]  # type: ignore[return-value]

    def _observe_pose(self) -> Pose7 | None:
        self.progress()
        return self.state.snapshot()["cup_pose"]  # type: ignore[return-value]

    def _observe_joints(self) -> tuple[dict[str, float], dict[str, float]]:
        self.progress()
        value = self.state.snapshot()
        return value["positions"], value["velocities"]  # type: ignore[return-value]

    def refresh_controllers(self) -> ResetStepReceipt:
        if not self._controllers.wait_for_service(timeout_sec=self.timeout_s):
            return ResetStepReceipt(
                False, "RESET_CONTROLLER_SERVICE_UNAVAILABLE", {}
            )
        future = self._controllers.call_async(self._controller_type.Request())
        deadline = time.monotonic() + self.timeout_s
        while not future.done() and time.monotonic() < deadline:
            self.progress()
        if not future.done() or future.result() is None:
            return ResetStepReceipt(False, "RESET_CONTROLLER_OBSERVE_TIMEOUT", {})
        controllers = {
            value.name: value.state for value in future.result().controller
        }
        with self.state._lock:
            self.state.controllers = controllers
        return ResetStepReceipt(True, None, {"controllers": controllers})

    def run(self) -> TransactionalResetReceipt:
        return execute_gazebo_reset_transaction(
            self.request,
            observation=self.observation,
            goals=self.goals,
            physical=self.physical,
            scene=self.scene,
            robot=self.robot,
        )

    def close(self) -> None:
        self._attachment.close()
        self._pose.close()
        self.node.destroy_node()
        if self._owns_rclpy and self._rclpy.ok():
            self._rclpy.shutdown()


def run_gazebo_reset(share: Path, session_id: str) -> TransactionalResetReceipt:
    runtime = RosGazeboResetRuntime(share, session_id)
    try:
        return runtime.run()
    finally:
        runtime.close()
