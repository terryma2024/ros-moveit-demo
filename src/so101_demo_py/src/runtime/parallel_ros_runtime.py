"""Concrete, observation-backed ROS/MuJoCo ports for one parallel Worker."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import time
from types import SimpleNamespace
from typing import Callable, Mapping

import numpy as np

from ..application.object_pose import LocalizationError, RgbdLocalizer
from ..application.qualification_stack import ros2_command
from ..core.detection import DetectionCandidate
from ..core.task_geometry import Pose7
from ..parallel_batch.broker import BrokerResponse
from ..parallel_batch.contracts import AttemptStatus, ModelOutcome, RunMode
from ..parallel_batch.perception import (
    AdmissionContext,
    LocalizedPose,
    PerceptionPolicy,
    PoseAdmissionLatch,
)
from ..ros.rgbd_snapshot import RosRgbdSnapshotSource
from .parallel_worker_runtime import (
    ExecutionCompletionReceipt,
    InferenceSnapshotReceipt,
    NumericEvidenceReceipt,
    RosDynamicPlanPrefixAdapter,
    RuntimeDecision,
    SourceStampedCapture,
)


_RESET_JOINTS = (0.0,) * 6
_ACTIVE_GOAL_STATES = {1, 2, 3}
_NODE_DIAGNOSTIC_LIMIT = 16
_NODE_DIAGNOSTIC_NAME_LIMIT = 96
_EXACT_TF_DISCOVERY_TIMEOUT_S = 5.0


def _mkdir_private_chain(root, target):
    """Create and verify each target directory beneath a private root."""

    root = Path(root).absolute()
    target = Path(target).absolute()
    try:
        parts = target.relative_to(root).parts
    except ValueError as error:
        raise RuntimeError("BROKER_INPUT_DIRECTORY_ESCAPE") from error
    current = root
    for part in (None, *parts):
        if part is not None:
            current = current / part
            try:
                current.mkdir(mode=0o700)
            except FileExistsError:
                pass
        info = current.lstat()
        if (
            not stat.S_ISDIR(info.st_mode)
            or current.is_symlink()
            or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700
        ):
            raise RuntimeError("BROKER_INPUT_DIRECTORY_IDENTITY")
    return target


def _worker_node_diagnostic(observed, expected):
    """Return bounded deterministic detail without changing exact equality."""

    normalized = tuple(
        node if isinstance(node, str) else f"<non-string:{type(node).__name__}>"
        for node in observed
    )
    counts = {}
    for node in normalized:
        counts[node] = counts.get(node, 0) + 1
    observed_set = set(normalized)
    groups = {
        "missing": sorted(set(expected) - observed_set),
        "unexpected": sorted(observed_set - set(expected)),
        "duplicates": sorted(node for node, count in counts.items() if count > 1),
    }
    truncated = any(
        len(values) > _NODE_DIAGNOSTIC_LIMIT
        or any(len(value) > _NODE_DIAGNOSTIC_NAME_LIMIT for value in values)
        for values in groups.values()
    )
    bounded = {
        name: [
            value[:_NODE_DIAGNOSTIC_NAME_LIMIT]
            for value in values[:_NODE_DIAGNOSTIC_LIMIT]
        ]
        for name, values in groups.items()
    }
    bounded["truncated"] = truncated
    payload = json.dumps(bounded, sort_keys=True, separators=(",", ":"))
    while len(payload.encode()) > 320:
        for name in ("unexpected", "duplicates", "missing"):
            if bounded[name]:
                bounded[name].pop()
                bounded["truncated"] = True
                break
        else:  # pragma: no cover - fixed JSON keys alone are well below the cap
            raise RuntimeError("NODE_DIAGNOSTIC_BOUND")
        payload = json.dumps(bounded, sort_keys=True, separators=(",", ":"))
    return payload


class _IsolatedRosNode:
    def __init__(self, node, context, executor):
        self.node = node
        self.context = context
        self.executor = executor
        self._closed = False

    def spin_once(self, *, timeout_sec):
        if self._closed:
            raise RuntimeError("ISOLATED_ROS_NODE_CLOSED")
        self.executor.spin_once(timeout_sec=timeout_sec)

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            self.executor.remove_node(self.node)
        finally:
            try:
                self.executor.shutdown()
            finally:
                try:
                    self.node.destroy_node()
                finally:
                    self.context.shutdown()


def _open_isolated_ros_node(rclpy, name, **node_options):
    """Create a node whose init/shutdown cannot touch another runtime context."""

    from rclpy.executors import SingleThreadedExecutor

    context = rclpy.context.Context()
    rclpy.init(context=context)
    try:
        node = rclpy.create_node(name, context=context, **node_options)
    except Exception:
        context.shutdown()
        raise
    try:
        executor = SingleThreadedExecutor(context=context)
        executor.add_node(node)
    except Exception:
        node.destroy_node()
        context.shutdown()
        raise
    return _IsolatedRosNode(node, context, executor)


@dataclass(frozen=True)
class ResetBoundaryReceipt:
    reset_epoch: str
    simulation_session_id: str
    reset_completed_monotonic_s: float
    simulation_time_s: float
    reset_epoch_value: int | None = None
    joint_positions: tuple[float, ...] | None = None
    batch_id: str | None = None
    coordinator_epoch: int | None = None
    worker_id: str | None = None
    worker_generation: int | None = None
    point_id: str | None = None
    attempt_id: str | None = None
    lease_generation: int | None = None

    def __post_init__(self):
        if (
            not isinstance(self.reset_epoch, str)
            or not self.reset_epoch
            or not isinstance(self.simulation_session_id, str)
            or not self.simulation_session_id
            or not math.isfinite(self.reset_completed_monotonic_s)
            or self.reset_completed_monotonic_s < 0.0
            or not math.isfinite(self.simulation_time_s)
            or self.simulation_time_s < 0.0
        ):
            raise ValueError("invalid reset boundary receipt")
        expected = self.reset_epoch.removeprefix("reset-")
        if not expected.isascii() or not expected.isdecimal():
            raise ValueError("invalid reset boundary receipt")
        numeric = int(expected)
        if self.reset_epoch_value is None:
            object.__setattr__(self, "reset_epoch_value", numeric)
        elif type(self.reset_epoch_value) is not int or self.reset_epoch_value != numeric:
            raise ValueError("invalid reset boundary receipt")
        if self.joint_positions is not None and (
            type(self.joint_positions) is not tuple
            or len(self.joint_positions) != 6
            or any(
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
                for value in self.joint_positions
            )
        ):
            raise ValueError("invalid reset boundary receipt")


@dataclass(frozen=True)
class InitialGateObservation:
    reset_epoch: str
    simulation_session_id: str
    source_frame_monotonic_s: float
    joint_positions: tuple[float, ...]
    active_controller_goal_ids: tuple[str, ...]
    moveit_attached_object_ids: tuple[str, ...]
    has_contact: bool
    worker_node_fqns: tuple[str, ...]
    node_graph_stable: bool = True

    def __post_init__(self):
        if (
            not isinstance(self.reset_epoch, str)
            or not self.reset_epoch
            or not isinstance(self.simulation_session_id, str)
            or not self.simulation_session_id
            or not math.isfinite(self.source_frame_monotonic_s)
            or self.source_frame_monotonic_s < 0.0
            or len(self.joint_positions) != 6
            or any(not math.isfinite(value) for value in self.joint_positions)
            or type(self.active_controller_goal_ids) is not tuple
            or type(self.moveit_attached_object_ids) is not tuple
            or type(self.has_contact) is not bool
            or type(self.worker_node_fqns) is not tuple
            or type(self.node_graph_stable) is not bool
        ):
            raise ValueError("invalid initial-gate observation")


@dataclass(frozen=True)
class ShutdownObservation:
    remaining_session_pids: tuple[int, ...]
    worker_node_fqns: tuple[str, ...]
    node_graph_stable: bool


def observe_worker_shutdown(session_id: str, *, timeout_s: float) -> ShutdownObservation:
    """Read back both OS process ownership and the isolated ROS graph."""

    if not isinstance(session_id, str) or not session_id or timeout_s <= 0.0:
        raise ValueError("SHUTDOWN_OBSERVATION_INPUT")
    marker = f"SO101_SESSION_ID={session_id}".encode()
    pids = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdecimal() or int(entry.name) == os.getpid():
            continue
        try:
            values = (entry / "environ").read_bytes().split(b"\0")
        except OSError:
            continue
        if marker in values:
            pids.append(int(entry.name))

    import rclpy

    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init()
    node = rclpy.create_node("so101_parallel_recovery_observer")
    deadline = time.monotonic() + timeout_s
    previous = None
    stable = 0
    graph = ()
    try:
        while time.monotonic() < deadline and stable < 2:
            rclpy.spin_once(node, timeout_sec=0.02)
            graph = tuple(sorted(
                f"{namespace.rstrip('/')}/{name}"
                for name, namespace in node.get_node_names_and_namespaces()
                if name != "so101_parallel_recovery_observer"
            ))
            if graph == previous:
                stable += 1
            else:
                previous, stable = graph, 1
        return ShutdownObservation(tuple(sorted(pids)), graph, stable >= 2)
    finally:
        node.destroy_node()
        if initialized_here and rclpy.ok():
            rclpy.shutdown()


def cancel_and_confirm_parallel_goals(*, timeout_s: float) -> bool:
    """Cancel arm, gripper, and MoveIt execution goals and observe all settled."""

    import rclpy
    from rclpy.qos import qos_profile_action_status_default
    from action_msgs.msg import GoalStatusArray
    from action_msgs.srv import CancelGoal

    owner = _open_isolated_ros_node(rclpy, "so101_parallel_goal_cancellation")
    node = owner.node
    names = {
        "arm": "/arm_controller/follow_joint_trajectory/_action",
        "gripper": "/gripper_controller/follow_joint_trajectory/_action",
        "moveit": "/execute_trajectory/_action",
    }
    statuses = {name: None for name in names}

    def callback(name):
        return lambda message: statuses.__setitem__(
            name, tuple(int(item.status) for item in message.status_list)
        )

    subscriptions = [
        node.create_subscription(
            GoalStatusArray,
            prefix + "/status",
            callback(name),
            qos_profile_action_status_default,
        )
        for name, prefix in names.items()
    ]
    clients = {
        name: node.create_client(CancelGoal, prefix + "/cancel_goal")
        for name, prefix in names.items()
    }
    try:
        deadline = time.monotonic() + timeout_s
        futures = []
        for client in clients.values():
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not client.wait_for_service(timeout_sec=remaining):
                return False
            futures.append(client.call_async(CancelGoal.Request()))
        while time.monotonic() < deadline:
            owner.spin_once(timeout_sec=0.01)
            if (
                all(future.done() and future.result() is not None for future in futures)
                and all(value is not None for value in statuses.values())
                and all(
                    status not in _ACTIVE_GOAL_STATES
                    for values in statuses.values()
                    for status in values
                )
            ):
                return True
        return False
    finally:
        del subscriptions
        owner.close()


def observe_no_parallel_goals(*, timeout_s: float) -> bool:
    """Independently observe exact controller and MoveIt status topics settled."""

    import rclpy
    from rclpy.qos import qos_profile_action_status_default
    from action_msgs.msg import GoalStatusArray

    owner = _open_isolated_ros_node(rclpy, "so101_parallel_goal_confirmation")
    node = owner.node
    topics = (
        "/arm_controller/follow_joint_trajectory/_action/status",
        "/gripper_controller/follow_joint_trajectory/_action/status",
        "/execute_trajectory/_action/status",
    )
    statuses = {topic: None for topic in topics}
    subscriptions = [
        node.create_subscription(
            GoalStatusArray,
            topic,
            lambda message, key=topic: statuses.__setitem__(
                key, tuple(int(item.status) for item in message.status_list)
            ),
            qos_profile_action_status_default,
        )
        for topic in topics
    ]
    try:
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            owner.spin_once(timeout_sec=0.01)
            if all(value is not None for value in statuses.values()):
                return all(
                    status not in _ACTIVE_GOAL_STATES
                    for values in statuses.values()
                    for status in values
                )
        return False
    finally:
        del subscriptions
        owner.close()


@dataclass(frozen=True, slots=True)
class AdmittedPose:
    frame_id: str
    source_stamp_ns: int
    received_monotonic_s: float
    pose_world: Pose7
    reset_epoch: str
    localized: LocalizedPose

    @property
    def perception_chain_complete(self):
        return True


@dataclass(frozen=True, slots=True)
class PerceptionTerminal:
    disposition: str
    reason: str
    failure_type: str | None = None
    failure_message: str | None = None

    @property
    def perception_terminal(self):
        return True

    @property
    def perception_chain_complete(self):
        return True


def _decode_row_major_mask(document: Mapping[str, object]) -> np.ndarray:
    if not isinstance(document, Mapping) or set(document) != {"shape", "counts"}:
        raise ValueError("BROKER_MASK_RLE_FIELDS")
    shape, counts = document["shape"], document["counts"]
    if (
        type(shape) is not list
        or len(shape) != 2
        or any(type(value) is not int or value <= 0 for value in shape)
        or type(counts) is not list
        or not counts
        or any(type(value) is not int or value < 0 for value in counts)
        or sum(counts) != shape[0] * shape[1]
    ):
        raise ValueError("BROKER_MASK_RLE_INVALID")
    flat = np.empty(shape[0] * shape[1], dtype=np.bool_)
    offset = 0
    selected = False
    for count in counts:
        flat[offset : offset + count] = selected
        offset += count
        selected = not selected
    return flat.reshape(tuple(shape), order="C")


def _candidate_from_response(response: BrokerResponse) -> DetectionCandidate:
    if (
        type(response) is not BrokerResponse
        or response.outcome is not ModelOutcome.QUALIFIED
        or type(response.candidate) is not dict
    ):
        raise RuntimeError("BROKER_QUALIFIED_RESPONSE_REQUIRED")
    batch = response.candidate
    if set(batch) != {
        "model_id",
        "weights_sha256",
        "runtime_device",
        "inference_latency_ms",
        "shape",
        "source_stamp_ns",
        "source_frame_id",
        "candidates",
    } or type(batch["candidates"]) is not list or len(batch["candidates"]) != 1:
        raise RuntimeError("BROKER_CANDIDATE_AMBIGUOUS")
    item = batch["candidates"][0]
    if type(item) is not dict or set(item) != {
        "instance_id",
        "class_id",
        "confidence",
        "bbox_xyxy",
        "segmentation_quality",
        "mask_rle",
    }:
        raise RuntimeError("BROKER_CANDIDATE_FIELDS")
    shape = batch["shape"]
    if (
        type(shape) is not list
        or len(shape) != 3
        or shape[2] != 3
        or any(type(value) is not int or value <= 0 for value in shape)
    ):
        raise RuntimeError("BROKER_CANDIDATE_SHAPE")
    try:
        return DetectionCandidate(
            item["instance_id"],
            item["class_id"],
            item["confidence"],
            tuple(item["bbox_xyxy"]),
            _decode_row_major_mask(item["mask_rle"]),
            batch["source_stamp_ns"],
            batch["source_frame_id"],
            shape[1],
            shape[0],
            item["segmentation_quality"],
        )
    except (TypeError, ValueError) as error:
        raise RuntimeError("BROKER_CANDIDATE_INVALID") from error


class BrokerMaskLocalizer:
    """Feed only the authenticated Broker mask to the reviewed RGB-D localizer."""

    def __init__(self, *, localizer=None):
        self.localizer = localizer or RgbdLocalizer()

    def localize(self, response, *, camera_info, depth_message, lookup_exact):
        candidate = _candidate_from_response(response)
        return self.localizer.localize(
            candidate,
            camera_info,
            depth_message,
            lookup_exact,
        )


def observe_parallel_initial_gate(
    boundary: ResetBoundaryReceipt,
    *,
    timeout_s: float = 5.0,
) -> InitialGateObservation:
    """Collect fresh joint, goal, scene, graph and MuJoCo contact observations."""

    from ..backends.mujoco.teleop_runtime import current_evidence

    evidence = current_evidence(boundary.simulation_session_id, timeout_s=timeout_s)
    evidence_received = time.monotonic()
    if str(evidence.reset_epoch) != boundary.reset_epoch.removeprefix("reset-"):
        raise RuntimeError("POINT_INITIAL_GATE_RESET_EPOCH")

    import rclpy
    from rclpy.qos import qos_profile_action_status_default
    from action_msgs.msg import GoalStatusArray
    from action_msgs.srv import CancelGoal
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import GetPlanningScene

    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init()
    service_node = rclpy.create_node("so101_parallel_gate_services")
    graph_node = rclpy.create_node("so101_parallel_gate_graph")
    goal_receipts = {}
    goal_ids = set()

    def goal_callback(topic, message):
        goal_receipts[topic] = time.monotonic()
        for status in message.status_list:
            if int(status.status) in _ACTIVE_GOAL_STATES:
                goal_ids.add(bytes(status.goal_info.goal_id.uuid).hex())

    topics = (
        "/execute_trajectory/_action/status",
        "/arm_controller/follow_joint_trajectory/_action/status",
        "/gripper_controller/follow_joint_trajectory/_action/status",
    )
    subscriptions = [
        graph_node.create_subscription(
            GoalStatusArray,
            topic,
            lambda message, name=topic: goal_callback(name, message),
            qos_profile_action_status_default,
        )
        for topic in topics
    ]
    action_prefixes = {
        "execute_trajectory": "/execute_trajectory/_action",
        "arm_controller": "/arm_controller/follow_joint_trajectory/_action",
        "gripper_controller": "/gripper_controller/follow_joint_trajectory/_action",
    }
    cancel_clients = {
        name: service_node.create_client(CancelGoal, prefix + "/cancel_goal")
        for name, prefix in action_prefixes.items()
    }
    scene_client = service_node.create_client(GetPlanningScene, "/get_planning_scene")
    try:
        if not scene_client.wait_for_service(timeout_sec=timeout_s):
            raise RuntimeError("POINT_INITIAL_GATE_SCENE_UNAVAILABLE")
        if any(
            not client.wait_for_service(timeout_sec=timeout_s)
            for client in cancel_clients.values()
        ):
            raise RuntimeError("POINT_INITIAL_GATE_GOAL_CANCEL_UNAVAILABLE")
        scene_request = GetPlanningScene.Request()
        scene_request.components.components = (
            PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        )
        scene_future = scene_client.call_async(scene_request)
        cancel_futures = {
            name: client.call_async(CancelGoal.Request())
            for name, client in cancel_clients.items()
        }
        deadline = time.monotonic() + timeout_s
        previous_graph = None
        stable_graph_samples = 0
        while time.monotonic() < deadline:
            rclpy.spin_once(service_node, timeout_sec=0.01)
            rclpy.spin_once(graph_node, timeout_sec=0.01)
            graph = tuple(
                sorted(
                    f"{namespace.rstrip('/')}/{name}"
                    for name, namespace in graph_node.get_node_names_and_namespaces()
                    if not name.startswith("so101_parallel_gate_")
                )
            )
            if graph == previous_graph:
                stable_graph_samples += 1
            else:
                previous_graph = graph
                stable_graph_samples = 1
            if (
                boundary.joint_positions is not None
                and all(future.done() for future in cancel_futures.values())
                and scene_future.done()
                and stable_graph_samples >= 2
                and ParallelRosRuntimePorts.worker_node_inventory_matches(graph)
            ):
                break
        else:
            missing = []
            if boundary.joint_positions is None:
                missing.append("joint_state")
            missing.extend(
                name + "_cancel"
                for name, future in cancel_futures.items()
                if not future.done()
            )
            if not scene_future.done():
                missing.append("planning_scene")
            if stable_graph_samples < 2:
                missing.append("stable_graph")
            if missing:
                raise RuntimeError(
                    "POINT_INITIAL_GATE_OBSERVATION_TIMEOUT:" + ",".join(missing)
                )
        for future in cancel_futures.values():
            response = future.result()
            if response is None:
                raise RuntimeError("POINT_INITIAL_GATE_GOAL_CANCEL_UNAVAILABLE")
            for goal in response.goals_canceling:
                goal_ids.add(bytes(goal.goal_id.uuid).hex())
        scene_response = scene_future.result()
        if scene_response is None:
            raise RuntimeError("POINT_INITIAL_GATE_SCENE_UNAVAILABLE")
        attached = tuple(
            sorted(
                item.object.id
                for item in scene_response.scene.robot_state.attached_collision_objects
            )
        )
        received = max(evidence_received, *goal_receipts.values(), time.monotonic())
        return InitialGateObservation(
            boundary.reset_epoch,
            boundary.simulation_session_id,
            received,
            boundary.joint_positions,
            tuple(sorted(goal_ids)),
            attached,
            bool(
                evidence.left_fingertip_contacts
                or evidence.right_fingertip_contacts
            ),
            graph,
            stable_graph_samples >= 2,
        )
    finally:
        del subscriptions
        graph_node.destroy_node()
        service_node.destroy_node()
        if initialized_here and rclpy.ok():
            rclpy.shutdown()


class ParallelRosRuntimePorts:
    """Lazy concrete Task 10 ports; tests may replace individual observations."""

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
    def worker_node_inventory_matches(cls, nodes):
        if (
            type(nodes) is not tuple
            or any(not isinstance(node, str) for node in nodes)
            or tuple(sorted(nodes)) != nodes
            or len(set(nodes)) != len(nodes)
        ):
            return False
        required = set(cls.expected_worker_nodes())
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
        self._close_pose_publisher()
        if self._planner is not None:
            self._planner.close()
            self._planner = None
        self.resources = resources
        return True

    def close_runtime(self):
        for source, *_rest in tuple(self._rgbd.values()):
            source.close()
        self._rgbd.clear()
        self._close_pose_publisher()
        if self._planner is not None:
            self._planner.close()
            self._planner = None

    @classmethod
    def for_test(cls, *, resources, catalog, observe_initial):
        return cls(
            resources,
            catalog=catalog,
            dependencies={"observe_initial": observe_initial},
        )

    def kwargs(self):
        return {name: getattr(self, name) for name in self.REQUIRED}

    def ready_probe(self, _requirements):
        call = self.dependencies.get("ready_probe")
        if call is not None:
            return call(_requirements)
        completed = subprocess.run(
            ros2_command("run", "so101_demo_py", "motion_stack_ready", "--timeout-s", "60"),
            timeout=65.0,
            check=False,
        )
        return completed.returncode == 0

    def reset_point(self, lease):
        call = self.dependencies.get("reset_point")
        point = self.catalog[lease.point_id]
        qualified = call is None
        if qualified:
            call = self.dependencies.get("execute_reset")
        if call is None:
            from ..cli.teleop_reset import execute_mujoco_reset

            call = execute_mujoco_reset
        if qualified:
            value, scene = call(
                self.resources.session_id,
                keyframe="task_start",
                cup_position_world_m=tuple(point["cup_position_world_m"]),
            )
            if getattr(scene, "success", None) is not True:
                raise RuntimeError("RESET_PLANNING_SCENE_RESTORE")
        else:
            value = call(lease, point)
        observe = self.dependencies.get("current_evidence")
        if observe is None:
            from ..backends.mujoco.teleop_runtime import current_evidence

            observe = current_evidence
        evidence = observe(value.simulation_session_id)
        if (
            evidence.simulation_session_id != value.simulation_session_id
            or evidence.reset_epoch != value.new_epoch
        ):
            raise RuntimeError("RESET_WATERMARK_IDENTITY")
        joint_positions = getattr(value, "joint_positions", None)
        receipt = ResetBoundaryReceipt(
            f"reset-{value.new_epoch}",
            value.simulation_session_id,
            time.monotonic(),
            evidence.simulation_time_s,
            value.new_epoch,
            None if joint_positions is None else tuple(joint_positions),
            batch_id=lease.batch_id,
            coordinator_epoch=lease.coordinator_epoch,
            worker_id=lease.worker_id,
            worker_generation=lease.worker_generation,
            point_id=lease.point_id,
            attempt_id=lease.attempt_id,
            lease_generation=lease.lease_generation,
        )
        self._reset_receipts[lease.attempt_id] = receipt
        return receipt

    def reserve_workspace(self, lease, reset_receipt):
        call = self.dependencies.get("reserve_workspace")
        if call is None:
            raise RuntimeError("WORKSPACE_RESERVATION_PORT_REQUIRED")
        return call(lease, reset_receipt)

    def initial_gate(self, lease, reset_receipt):
        call = self.dependencies.get("observe_initial", observe_parallel_initial_gate)
        value = call(reset_receipt)
        if type(value) is not InitialGateObservation:
            failures = ["type"]
        else:
            predicates = (
                ("reset_epoch", value.reset_epoch == reset_receipt.reset_epoch),
                (
                    "simulation_session",
                    value.simulation_session_id == reset_receipt.simulation_session_id,
                ),
                (
                    "freshness",
                    value.source_frame_monotonic_s
                    > reset_receipt.reset_completed_monotonic_s,
                ),
                (
                    "joints",
                    all(
                        abs(actual - expected) <= 0.002
                        for actual, expected in zip(
                            value.joint_positions, _RESET_JOINTS, strict=True
                        )
                    ),
                ),
                ("goals", not value.active_controller_goal_ids),
                ("attachment", not value.moveit_attached_object_ids),
                ("contact", value.has_contact is False),
                ("stable_graph", value.node_graph_stable is True),
                (
                    "worker_nodes",
                    self.worker_node_inventory_matches(value.worker_node_fqns),
                ),
            )
            failures = [name for name, accepted in predicates if not accepted]
        if failures:
            message = "POINT_INITIAL_GATE_OBSERVATION_REJECTED:" + ",".join(failures)
            if type(value) is InitialGateObservation and "worker_nodes" in failures:
                message += ";worker_nodes=" + _worker_node_diagnostic(
                    value.worker_node_fqns, self.expected_worker_nodes()
                )
            raise RuntimeError(message)
        return SimpleNamespace(
            batch_id=lease.batch_id,
            coordinator_epoch=lease.coordinator_epoch,
            worker_id=lease.worker_id,
            worker_generation=lease.worker_generation,
            point_id=lease.point_id,
            attempt_id=lease.attempt_id,
            lease_generation=lease.lease_generation,
            reset_epoch=value.reset_epoch,
            simulation_session_id=value.simulation_session_id,
            source_frame_monotonic_s=value.source_frame_monotonic_s,
            canonical_joints=True,
            no_controller_goal=True,
            no_attachment=True,
            no_contact=True,
            no_stale_node=True,
        )

    def _capture_aligned(self):
        factory = self.dependencies.get("rgbd_source", RosRgbdSnapshotSource)
        source = factory()
        aligned = source.capture(15.0)
        return source, aligned, time.monotonic()

    def capture_rgb(self, path, boundary):
        from ..cli.rgbd_point_cloud import _decode_rgb, message_stamp_ns
        from .point_cloud_preview import write_png_rgb8

        source, (camera, color, depth), received = self._capture_aligned()
        try:
            if received <= boundary:
                raise RuntimeError("RGB_SOURCE_NOT_FRESH")
            rgb = np.array(_decode_rgb(color), copy=True)
            stamp = message_stamp_ns(color)
            if path.suffix == ".npy":
                path.parent.mkdir(parents=True, exist_ok=True)
                buffer = io.BytesIO()
                np.save(buffer, rgb, allow_pickle=False)
                payload = buffer.getvalue()
                descriptor = os.open(
                    path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o400,
                )
                try:
                    os.write(descriptor, payload)
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
                receipt = InferenceSnapshotReceipt(
                    path,
                    received,
                    stamp,
                    color.header.frame_id,
                    tuple(rgb.shape),
                    hashlib.sha256(payload).hexdigest(),
                    simulation_session_id=self.resources.session_id,
                    source_clock="ros_sim",
                )
                batch_root = self.resources.worker_root.parent.parent
                relative = path.relative_to(self.resources.worker_root.parent)
                broker_copy = batch_root / "broker-inputs" / relative
                _mkdir_private_chain(
                    batch_root / "broker-inputs", broker_copy.parent
                )
                os.link(path, broker_copy, follow_symlinks=False)
                parent_fd = os.open(
                    broker_copy.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                )
                try:
                    os.fsync(parent_fd)
                finally:
                    os.close(parent_fd)
                self._rgbd[stamp] = (source, camera, depth, color.header.frame_id)
                source = None
                return receipt
            write_png_rgb8(rgb, path)
            return SourceStampedCapture(path, received, source_stamp_ns=stamp)
        finally:
            if source is not None:
                source.close()

    def localize(self, lease, broker_result):
        request = broker_result.request
        if broker_result.candidate.get("source_stamp_ns") != round(
            request.image_timestamp_s * 1_000_000_000
        ):
            raise RuntimeError("BROKER_RGB_IDENTITY_MISMATCH")
        try:
            source, camera, depth, frame_id = self._rgbd[
                round(request.image_timestamp_s * 1_000_000_000)
            ]
        except (AttributeError, KeyError) as error:
            raise RuntimeError("BROKER_RGBD_IDENTITY_MISSING") from error
        localized = BrokerMaskLocalizer().localize(
            broker_result,
            camera_info=camera,
            depth_message=depth,
            lookup_exact=lambda target, frame, stamp: source.lookup_exact(
                target, frame, stamp, _EXACT_TF_DISCOVERY_TIMEOUT_S
            ),
        )
        depth_hash = hashlib.sha256(bytes(depth.data)).hexdigest()
        value = LocalizedPose(
            request,
            broker_result.broker_generation,
            self.resources.session_id,
            request.image_timestamp_s,
            depth_hash,
            request.image_timestamp_s,
            frame_id,
            "world",
            localized.center_world_xyz,
            (0.0, 0.0, 0.0, 1.0),
        )
        self._localized[lease.attempt_id] = (value, depth, localized)
        return value

    def _source_clock(self, reset_receipt):
        call = self.dependencies.get("source_clock")
        if call is not None:
            return call(reset_receipt)
        sources = [source for source, *_rest in self._rgbd.values()]
        if len(sources) != 1:
            raise RuntimeError("SOURCE_CLOCK_IDENTITY")
        node = getattr(sources[0], "_node", None)
        if node is None:
            raise RuntimeError("SOURCE_CLOCK_IDENTITY")
        return int(node.get_clock().now().nanoseconds) / 1_000_000_000.0

    def _dynamic_template(self):
        supplied = self.dependencies.get("dynamic_template")
        if supplied is not None:
            return supplied()
        from ament_index_python.packages import get_package_share_directory
        from ..core.dynamic_pick_policy import load_dynamic_policy_variant

        return load_dynamic_policy_variant(
            Path(get_package_share_directory("so101_demo_py")), backend="mujoco"
        ).template

    def run_perception_chain(
        self, lease, execution_kind, snapshot, broker_request
    ):
        """Drive the reviewed two-model policy and durable admission latch."""

        from ..cli.rgbd_point_cloud import message_stamp_ns
        from ..parallel_batch.contracts import ExecutionKind
        from ..runtime.parallel_perception_runtime import GROUNDED_ID

        if execution_kind not in (ExecutionKind.ATTEMPT, ExecutionKind.VALIDATION):
            raise RuntimeError("PERCEPTION_EXECUTION_KIND")
        if type(self.broker_generation) is not int or self.broker_generation <= 0:
            raise RuntimeError("BROKER_GENERATION_AUTHORITY")
        reset = self._reset_receipts.get(lease.attempt_id)
        if reset is None:
            raise RuntimeError("PERCEPTION_RESET_RECEIPT")
        try:
            _source, _camera, depth, _frame = self._rgbd[snapshot.source_stamp_ns]
        except KeyError as error:
            raise RuntimeError("PERCEPTION_RGBD_IDENTITY") from error
        depth_stamp_s = message_stamp_ns(depth) / 1_000_000_000.0
        depth_hash = hashlib.sha256(bytes(depth.data)).hexdigest()
        workspace_provider = self.dependencies.get("workspace_provider")
        authorize = self.dependencies.get("authorize")
        if not callable(workspace_provider) or not callable(authorize):
            raise RuntimeError("PERCEPTION_AUTHORITY_PORTS")
        template = self._dynamic_template()
        bounds = tuple(template.workspace_bounds_m)
        context = AdmissionContext(
            reset.simulation_session_id,
            reset.simulation_time_s,
            snapshot.source_frame_id,
            "world",
            self.config.max_frame_age_s,
            self.config.max_rgbd_skew_s,
            self.config.max_tf_skew_s,
        )

        def geometry_gate(request, localized):
            del request
            return all(
                bounds[index] <= localized.position_xyz[index] <= bounds[index + 3]
                for index in range(3)
            )

        def quality_gate(request, localized):
            response = self._admission_candidates.get(request.request_id)
            if (
                response is None
                or response.request != request
                or response.outcome is not ModelOutcome.QUALIFIED
                or localized.request != request
                or response.candidate.get("model_id") != request.model_id
            ):
                return False
            candidate = _candidate_from_response(response)
            return bool(candidate.mask.any())

        latch = PoseAdmissionLatch(
            workspace_provider(lease),
            context,
            broker_generation=self.broker_generation,
            clock=lambda: self._source_clock(reset),
            authorize=authorize,
            geometry_gate=geometry_gate,
            quality_gate=quality_gate,
        )
        policy = PerceptionPolicy(
            latch,
            yolo_model_id=self.config.yolo_model_id,
            grounded_model_id=GROUNDED_ID,
        )
        decision = policy.decision
        source = self._rgbd[snapshot.source_stamp_ns][0]
        retain_source = False
        failure_type = None
        failure_message = None
        try:
            while decision.next_model is not None:
                response = broker_request(
                decision.next_model,
                before_send=lambda request: policy.start_request(
                    request,
                    depth_timestamp_s=depth_stamp_s,
                    depth_sha256=depth_hash,
                ),
                )
                if response.broker_generation != self.broker_generation:
                    raise RuntimeError("BROKER_GENERATION_CHANGED")
                if response.outcome in {
                    ModelOutcome.INFRA_ERROR,
                    ModelOutcome.QUEUE_TIMEOUT,
                    ModelOutcome.INFERENCE_TIMEOUT,
                }:
                    failure_type = f"BrokerResponse.{response.outcome.value}"
                    failure_message = response.reason or response.outcome.value
                if response.outcome is ModelOutcome.QUALIFIED:
                    self._admission_candidates[response.request.request_id] = response
                    try:
                        localized = self.localize(lease, response)
                    except LocalizationError as error:
                        if error.code != "GEOMETRY_REJECTED":
                            raise
                        decision = policy.record_result(
                            response.request,
                            ModelOutcome.NORMAL_REJECTION,
                            broker_generation=response.broker_generation,
                        )
                        continue
                    policy.record_result(
                        response.request,
                        response.outcome,
                        broker_generation=response.broker_generation,
                    )
                    decision = policy.admit_pose(response.request, localized)
                    if decision.disposition == "CONTINUE":
                        admitted = self._admitted_pose(lease, localized)
                        self._admitted[lease.attempt_id] = admitted
                        retain_source = True
                        return admitted
                else:
                    decision = policy.record_result(
                    response.request,
                    response.outcome,
                    broker_generation=response.broker_generation,
                )
            return PerceptionTerminal(
                decision.disposition,
                decision.reason or "PERCEPTION_TERMINAL",
                failure_type,
                failure_message,
            )
        finally:
            if not retain_source:
                close = getattr(source, "close", None)
                if callable(close):
                    close()
                self._rgbd.pop(snapshot.source_stamp_ns, None)

    @staticmethod
    def _admitted_pose(lease, localized):
        del lease
        pose = Pose7((*localized.position_xyz, *localized.orientation_xyzw))
        return AdmittedPose(
            "world",
            round(localized.request.image_timestamp_s * 1_000_000_000),
            time.monotonic(),
            pose,
            localized.request.reset_epoch,
            localized,
        )

    def admit_pose(self, lease, localized):
        if type(localized) is PerceptionTerminal:
            return localized
        if type(localized) is AdmittedPose:
            if self._admitted.get(lease.attempt_id) is not localized:
                raise RuntimeError("POSE_ADMISSION_IDENTITY")
            return localized
        if self._localized.get(lease.attempt_id, (None,))[0] is not localized:
            raise RuntimeError("POSE_LOCALIZATION_IDENTITY")
        return self._admitted_pose(lease, localized)

    def _close_pose_publisher(self):
        owner = self._pose_publisher_owner
        self._pose_publisher_owner = None
        self._pose_publisher = None
        if owner is not None:
            owner.close()

    def _prime_pose_publisher(self):
        if self._pose_publisher_owner is not None:
            if self._pose_publisher is None:
                raise RuntimeError("POSE_PUBLISHER_STATE")
            return self._pose_publisher_owner, self._pose_publisher
        if self._pose_publisher is not None:
            raise RuntimeError("POSE_PUBLISHER_STATE")

        import rclpy
        from geometry_msgs.msg import PoseStamped
        from rclpy.parameter import Parameter

        owner = _open_isolated_ros_node(
            rclpy,
            "so101_parallel_pose_publisher",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        try:
            publisher = owner.node.create_publisher(PoseStamped, "/cup_pose", 10)
        except Exception:
            owner.close()
            raise
        self._pose_publisher_owner = owner
        self._pose_publisher = publisher
        return owner, publisher

    def publish_pose(self, admitted):
        call = self.dependencies.get("publish_pose")
        if call is not None:
            return call(admitted)
        import rclpy
        from geometry_msgs.msg import PoseStamped
        from rclpy.parameter import Parameter

        retained = self._pose_publisher_owner is not None
        initialized_here = False
        if retained:
            owner, publisher = self._prime_pose_publisher()
            node = owner.node
            spin_once = lambda duration: owner.spin_once(timeout_sec=duration)
        else:
            initialized_here = not rclpy.ok()
            if initialized_here:
                rclpy.init()
            node = rclpy.create_node(
                "so101_parallel_pose_publisher",
                parameter_overrides=[Parameter("use_sim_time", value=True)],
            )
            publisher = node.create_publisher(PoseStamped, "/cup_pose", 10)
            spin_once = lambda duration: rclpy.spin_once(
                node, timeout_sec=duration
            )
        try:
            message = PoseStamped()
            message.header.frame_id = "world"
            message.header.stamp.sec, message.header.stamp.nanosec = divmod(
                admitted.source_stamp_ns, 1_000_000_000
            )
            values = admitted.pose_world.values
            (
                message.pose.position.x,
                message.pose.position.y,
                message.pose.position.z,
                message.pose.orientation.x,
                message.pose.orientation.y,
                message.pose.orientation.z,
                message.pose.orientation.w,
            ) = values
            deadline = time.monotonic() + 2.0
            while node.get_clock().now().nanoseconds < admitted.source_stamp_ns:
                remaining = deadline - time.monotonic()
                if remaining <= 0.0:
                    return False
                spin_once(min(0.02, remaining))
            while publisher.get_subscription_count() < 1 and time.monotonic() < deadline:
                spin_once(0.02)
            if publisher.get_subscription_count() < 1:
                return False
            publisher.publish(message)
            spin_once(0.05)
            return True
        finally:
            if not retained:
                node.destroy_node()
                if initialized_here and rclpy.ok():
                    rclpy.shutdown()

    def _planning_adapter(self):
        if self._planner is not None:
            return self._planner
        call = self.dependencies.get("planning_adapter")
        if call is not None:
            self._planner = call()
            return self._planner
        import rclpy
        from ament_index_python.packages import get_package_share_directory
        from rclpy.parameter import Parameter
        from ..control.planning_scene.task_scene import RosTaskScenePort
        from ..core.dynamic_pick_policy import load_dynamic_policy_variant

        context = rclpy.context.Context()
        rclpy.init(context=context)
        node = rclpy.create_node(
            "so101_parallel_planner",
            context=context,
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        try:
            loaded = load_dynamic_policy_variant(
                Path(get_package_share_directory("so101_demo_py")), backend="mujoco"
            )
            scene = RosTaskScenePort(
                node, "mujoco", loaded.template.planning_timeout_s
            )
            self._planner = RosDynamicPlanPrefixAdapter(
                node, loaded.template, scene, owned_context=context
            )
        except Exception:
            node.destroy_node()
            context.shutdown()
            raise
        return self._planner

    def plan_prefix(self, lease, admitted, states):
        return self._planning_adapter()(lease, admitted, states)

    def consumer_ready(self, child):
        call = self.dependencies.get("consumer_ready")
        if call is not None:
            return call(child)

        deadline = time.monotonic() + 20.0
        try:
            owner, publisher = self._prime_pose_publisher()
        except Exception:
            self._close_pose_publisher()
            return False
        while time.monotonic() < deadline:
            if not Path(f"/proc/{child.pid}").exists():
                self._close_pose_publisher()
                return False
            try:
                owner.spin_once(timeout_sec=0.02)
                consumer_nodes = tuple(
                    f"{namespace.rstrip('/')}/{name}"
                    for name, namespace in owner.node.get_node_names_and_namespaces()
                    if name == "so101_dynamic_cup_pick_place"
                )
                if (
                    consumer_nodes == ("/so101_dynamic_cup_pick_place",)
                    and publisher.get_subscription_count() == 1
                    and owner.node.get_clock().now().nanoseconds > 0
                ):
                    return True
            except Exception:
                self._close_pose_publisher()
                return False
        self._close_pose_publisher()
        return False

    def _dynamic_policy_identity(self):
        supplied = self.dependencies.get("dynamic_policy_identity")
        if supplied is not None:
            path, sha256 = supplied()
            return str(path), sha256
        from ament_index_python.packages import get_package_share_directory
        from ..core.dynamic_pick_policy import load_dynamic_policy_variant

        loaded = load_dynamic_policy_variant(
            Path(get_package_share_directory("so101_demo_py")), backend="mujoco"
        )
        return str(loaded.path), loaded.sha256

    def _trusted_final_cup_pose(self, policy_path, policy_sha256):
        supplied = self.dependencies.get("expected_final_cup_pose_world")
        if supplied is not None:
            return list(supplied())
        path = Path(policy_path)
        if hashlib.sha256(path.read_bytes()).hexdigest() != policy_sha256:
            raise ValueError("DYNAMIC_POLICY_CHANGED")
        from ..core.dynamic_pick import compose_pose, inverse_pose
        from ..core.dynamic_pick_policy import load_dynamic_pick_template

        template = load_dynamic_pick_template(
            path,
            expected_backend="mujoco",
            expected_execution_allowed=True,
        )
        return list(compose_pose(
            template.place_tcp_world,
            inverse_pose(template.cup_to_tcp_grasp),
        ).values)

    def _dynamic_manifest_outcome(self, manifest, lease, admitted, exit_code):
        """Verify one immutable terminal consumer document before classification."""
        descriptor = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            before = os.fstat(descriptor)
            if (
                not stat.S_ISREG(before.st_mode)
                or before.st_uid != os.getuid()
                or before.st_size <= 0
                or before.st_size > 8 * 1024 * 1024
            ):
                raise ValueError("DYNAMIC_MANIFEST_FILE")
            payload = os.read(descriptor, before.st_size + 1)
            after = os.fstat(descriptor)
            if (
                len(payload) != before.st_size
                or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            ):
                raise ValueError("DYNAMIC_MANIFEST_CHANGED")
        finally:
            os.close(descriptor)
        document = json.loads(payload)
        required = {
            "schema", "parallel_lease_identity", "status", "current_state",
            "failure", "simulation_session_id", "expected_reset_epoch",
            "policy_path", "policy_sha256", "state_trace", "transition_count",
            "state_events", "planning_attempts", "final_samples",
            "planning_scene_readback", "release_marker_sequence",
        }
        if type(document) is not dict or not required.issubset(document):
            raise ValueError("DYNAMIC_MANIFEST_SCHEMA")
        if document["schema"] != "so101-dynamic-mujoco-execute-v1":
            raise ValueError("DYNAMIC_MANIFEST_SCHEMA")
        expected_identity = {
            name: getattr(lease, name)
            for name in (
                "batch_id", "coordinator_epoch", "worker_id",
                "worker_generation", "point_id", "attempt_id",
                "lease_generation",
            )
        }
        if document["parallel_lease_identity"] != expected_identity:
            raise ValueError("DYNAMIC_MANIFEST_LEASE_IDENTITY")
        reset_epoch = getattr(admitted, "reset_epoch", None)
        if (
            not isinstance(reset_epoch, str)
            or not reset_epoch.startswith("reset-")
            or not reset_epoch[6:].isascii()
            or not reset_epoch[6:].isdecimal()
            or document["expected_reset_epoch"] != int(reset_epoch[6:])
            or document["simulation_session_id"] != self.resources.session_id
        ):
            raise ValueError("DYNAMIC_MANIFEST_RUNTIME_IDENTITY")
        policy_path, policy_sha256 = self._dynamic_policy_identity()
        if (
            document["policy_path"] != policy_path
            or document["policy_sha256"] != policy_sha256
            or re.fullmatch(r"[0-9a-f]{64}", policy_sha256) is None
        ):
            raise ValueError("DYNAMIC_MANIFEST_POLICY_IDENTITY")
        status = document["status"]
        failure = document["failure"]
        if status == "DONE":
            if exit_code != 0:
                raise ValueError("DYNAMIC_MANIFEST_DONE")
        elif status == "ERROR":
            if exit_code == 0:
                raise ValueError("DYNAMIC_MANIFEST_ERROR")
        else:
            raise ValueError("DYNAMIC_MANIFEST_STATUS")
        from ..parallel_batch.dynamic_manifest import validate_dynamic_manifest_semantics

        outcome = validate_dynamic_manifest_semantics(
            document,
            expected_status=status,
            expected_reset_epoch=int(reset_epoch[6:]),
            expected_final_cup_pose_world=self._trusted_final_cup_pose(
                policy_path, policy_sha256
            ),
        )
        if outcome is AttemptStatus.PASSED:
            return outcome, "OK"
        if outcome is AttemptStatus.FAILED:
            return outcome, failure
        return outcome, f"{failure}:CONTROLLER_OUTCOME_UNCONFIRMED"

    def execute_result(self, lease, admitted, child):
        call = self.dependencies.get("execute_result")
        if call is not None:
            return call(lease, admitted, child)
        deadline = time.monotonic() + 180.0
        status = None
        while time.monotonic() < deadline:
            waited, observed = os.waitpid(child.pid, os.WNOHANG)
            if waited == child.pid:
                status = os.waitstatus_to_exitcode(observed)
                break
            time.sleep(0.05)
        manifest = (
            self.resources.worker_root
            / f"attempts/{lease.point_id}/{lease.attempt_id}/working/dynamic/"
            "dynamic-execute-manifest.json"
        )
        from ..parallel_batch.contracts import AttemptStatus

        try:
            outcome, reason = self._dynamic_manifest_outcome(
                manifest, lease, admitted, status
            )
        except (OSError, UnicodeError, ValueError, TypeError, json.JSONDecodeError):
            outcome = AttemptStatus.INDETERMINATE
            reason = "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"
        decision = RuntimeDecision(
            outcome,
            reason,
            physical_action_proven_absent=False,
        )
        return ExecutionCompletionReceipt(decision, time.monotonic())

    def capture_numeric_evidence(self, lease, localized, root, boundary):
        root.mkdir(parents=True, exist_ok=False)
        value, depth, localized_object = self._localized[lease.attempt_id]
        if value is not localized:
            raise RuntimeError("NUMERIC_LOCALIZATION_IDENTITY")
        physical = self._running_evidence(localized.request.image_timestamp_s)
        documents = {
            "depth.json": {
                "source_stamp_ns": localized.request.image_timestamp_s * 1_000_000_000,
                "sha256": localized.depth_sha256,
                "byte_count": len(depth.data),
            },
            "tf.json": {
                "source_frame": localized.source_frame,
                "target_frame": localized.target_frame,
                "source_stamp_s": localized.tf_timestamp_s,
                "center_world_xyz": list(localized.position_xyz),
            },
            "physical.json": asdict(physical),
        }
        paths = []
        for name, document in documents.items():
            path = root / name
            path.write_text(json.dumps(document, sort_keys=True), encoding="utf-8")
            paths.append(path)
        observed = time.monotonic()
        if observed <= boundary:
            raise RuntimeError("NUMERIC_EVIDENCE_STALE")
        del localized_object
        try:
            return NumericEvidenceReceipt(*paths, observed)
        finally:
            stamp = round(localized.request.image_timestamp_s * 1_000_000_000)
            retained = self._rgbd.pop(stamp, None)
            if retained is not None:
                close = getattr(retained[0], "close", None)
                if callable(close):
                    close()

    def _running_evidence(self, minimum_simulation_time_s):
        call = self.dependencies.get("running_evidence")
        if call is not None:
            return call(self.resources.session_id, minimum_simulation_time_s)
        sources = [source for source, *_rest in self._rgbd.values()]
        if len(sources) != 1 or getattr(sources[0], "_node", None) is None:
            raise RuntimeError("RUNNING_EVIDENCE_SOURCE_CONTEXT")
        from ..backends.mujoco.observer import EvidenceStale, MujocoWorldObserver
        import rclpy

        node = sources[0]._node
        observer = MujocoWorldObserver(
            node, self.resources.session_id, max_age_s=1.0
        )
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.01)
            try:
                evidence = observer.snapshot()
            except EvidenceStale:
                continue
            if (
                evidence.simulation_session_id == self.resources.session_id
                and evidence.paused is False
                and evidence.simulation_time_s >= minimum_simulation_time_s
            ):
                return evidence
        raise RuntimeError("RUNNING_EVIDENCE_UNAVAILABLE")

    def cancel_motion(self, lease):
        call = self.dependencies.get("cancel_motion")
        if call is not None:
            return call(lease)
        del lease
        return cancel_and_confirm_parallel_goals(timeout_s=5.0)

    def confirm_no_controller_goal(self, lease):
        call = self.dependencies.get("confirm_no_controller_goal")
        if call is not None:
            return call(lease)
        if lease.attempt_id not in self._reset_receipts:
            return False
        return observe_no_parallel_goals(timeout_s=5.0)

    def resume_physics(self, lease, reset_receipt):
        call = self.dependencies.get("resume_physics")
        if call is not None:
            return call(lease, reset_receipt)
        if (
            reset_receipt.simulation_session_id != self.resources.session_id
            or reset_receipt.reset_epoch_value is None
        ):
            return False
        from ..backends.mujoco.lifecycle import resume_physics

        return resume_physics(None)

    def recovery(self, worker_id, generation, deadline):
        call = self.dependencies.get("recovery")
        if call is not None:
            return call(worker_id, generation, deadline)
        if time.monotonic() >= deadline:
            return False
        if worker_id != self.resources.worker_id or generation != self.resources.generation:
            return False
        if self._planner is not None:
            self._planner.close()
            self._planner = None
        observe = self.dependencies.get("observe_shutdown", observe_worker_shutdown)
        observed = observe(
            self.resources.session_id,
            timeout_s=max(0.001, min(5.0, deadline - time.monotonic())),
        )
        return (
            type(observed) is ShutdownObservation
            and time.monotonic() < deadline
            and not observed.remaining_session_pids
            and not observed.worker_node_fqns
            and observed.node_graph_stable
        )
