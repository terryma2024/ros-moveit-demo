"""Reset, initial gate, shutdown and goal observations, the admitted pose and the broker mask localiser."""

from __future__ import annotations

from dataclasses import dataclass
import math
import os
from pathlib import Path
import time
from typing import Mapping

import numpy as np

from so101_demo.application.object_pose import LocalizationError, RgbdLocalizer
from so101_demo.core.detection import DetectionCandidate
from so101_demo.core.task_geometry import Pose7
from so101_demo.parallel_batch.broker import BrokerResponse
from so101_demo.parallel_batch.contracts.common import ModelOutcome
from so101_demo.parallel_batch.perception import (
    LocalizedPose,
)
from so101_demo.runtime.parallel_ros_ports.binding import RuntimeBinding
from so101_demo.runtime.container_campaign.ros_namespace import container_ros_init_options
from so101_demo.runtime.parallel_ros_ports.isolated_node import (
    _ACTIVE_GOAL_STATES,
    _open_isolated_ros_node,
)


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
    if Path("/proc").is_dir():
        for entry in Path("/proc").iterdir():
            if not entry.name.isdecimal() or int(entry.name) == os.getpid():
                continue
            try:
                values = (entry / "environ").read_bytes().split(b"\0")
            except OSError:
                continue
            if marker in values:
                pids.append(int(entry.name))
    else:
        try:
            import psutil
        except ImportError:
            psutil = None
        if psutil is not None:
            for process in psutil.process_iter(attrs=("pid",)):
                if process.pid == os.getpid():
                    continue
                try:
                    environment = process.environ()
                except (OSError, psutil.Error):
                    continue
                if environment.get("SO101_SESSION_ID") == session_id:
                    pids.append(process.pid)

    import rclpy

    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init(**container_ros_init_options())
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

    from action_msgs.msg import GoalStatusArray
    from action_msgs.srv import CancelGoal
    import rclpy
    from rclpy.qos import qos_profile_action_status_default

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

    from action_msgs.msg import GoalStatusArray
    import rclpy
    from rclpy.qos import qos_profile_action_status_default

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


def _candidates_from_response(response: BrokerResponse) -> list[DetectionCandidate]:
    """Every candidate of an authenticated, qualified Broker response, each validated and its mask decoded."""
    if (
        type(response) is not BrokerResponse
        or response.outcome is not ModelOutcome.QUALIFIED
        or type(response.candidate) is not dict
    ):
        raise RuntimeError("BROKER_QUALIFIED_RESPONSE_REQUIRED")
    batch = response.candidate
    return _candidates_from_batch(batch)


def _candidates_from_batch(batch) -> list[DetectionCandidate]:
    """Decode the common normalized batch after its caller checks response identity."""
    if set(batch) != {
        "model_id",
        "weights_sha256",
        "runtime_device",
        "inference_latency_ms",
        "shape",
        "source_stamp_ns",
        "source_frame_id",
        "candidates",
    } or type(batch["candidates"]) is not list or not batch["candidates"]:
        raise RuntimeError("BROKER_CANDIDATE_AMBIGUOUS")
    shape = batch["shape"]
    if (
        type(shape) is not list
        or len(shape) != 3
        or shape[2] != 3
        or any(type(value) is not int or value <= 0 for value in shape)
    ):
        raise RuntimeError("BROKER_CANDIDATE_SHAPE")
    candidates = []
    for item in batch["candidates"]:
        if type(item) is not dict or set(item) != {
            "instance_id",
            "class_id",
            "confidence",
            "bbox_xyxy",
            "segmentation_quality",
            "mask_rle",
        }:
            raise RuntimeError("BROKER_CANDIDATE_FIELDS")
        try:
            candidates.append(
                DetectionCandidate(
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
            )
        except (TypeError, ValueError) as error:
            raise RuntimeError("BROKER_CANDIDATE_INVALID") from error
    return candidates


#: Cup geometry filtering: a candidate is the cup only if the xy circle fit of radius 0.04 +- 0.01 m succeeds and its
#: points span at least this much height. The red landing ring is flat (a few millimetres), the cup is 0.09 m tall.
MINIMUM_CUP_Z_EXTENT_M = 0.05


#: verdict on any candidate and propagates.
_CANDIDATE_LEVEL_FAILURES = frozenset({"GEOMETRY_REJECTED", "DEPTH_INVALID"})


class CupCandidateLocalizer:
    """Localize candidate masks in RGB-D and select exactly one with valid cup geometry."""

    def __init__(self, *, localizer=None):
        self.localizer = localizer or RgbdLocalizer()

    def localize(self, response, *, camera_info, depth_message, lookup_exact):
        """Localize every candidate; exactly one must be a cup: it localizes (circle fit) and spans >= 0.05 m in z.

        The survivor's pose is the localizer's own result for its mask, unchanged. More than one survivor is
        BROKER_CANDIDATE_AMBIGUOUS (the count is in the message); none is GEOMETRY_REJECTED (the policy then tries its next model)
        unless the only candidate failed for a reason that is not geometry, which propagates unchanged.
        """
        candidates = _candidates_from_response(response)
        return self.localize_candidates(candidates, camera_info=camera_info,
            depth_message=depth_message, lookup_exact=lookup_exact)

    def localize_candidates(self, candidates, *, camera_info, depth_message, lookup_exact):
        """Select the cup by circle fit and vertical extent from validated raw candidates."""
        survivors, rejected, first_error = [], [], None
        for candidate in candidates:
            try:
                localized = self.localizer.localize(candidate, camera_info, depth_message, lookup_exact)
            except LocalizationError as error:
                if error.code not in _CANDIDATE_LEVEL_FAILURES or len(candidates) == 1:
                    raise
                first_error = first_error or error
                rejected.append(f"{candidate.instance_id}:{error.code}")
                continue
            extent = _z_extent_m(localized)
            if extent is None or extent < MINIMUM_CUP_Z_EXTENT_M:
                shown = "unknown" if extent is None else f"{extent:.4f}"
                rejected.append(f"{candidate.instance_id}:Z_EXTENT={shown}")
                continue
            survivors.append(localized)
        if len(survivors) == 1:
            return survivors[0]
        if survivors:
            raise RuntimeError(f"BROKER_CANDIDATE_AMBIGUOUS: {len(survivors)} of {len(candidates)} candidates are cups")
        raise LocalizationError(
            "GEOMETRY_REJECTED",
            f"no candidate is a cup (0 of {len(candidates)}): {', '.join(rejected)}",
        )


def _z_extent_m(localized) -> float | None:
    points = getattr(localized, "points_world", None)
    if points is None:
        return None
    z = np.asarray(points, dtype=np.float64)[:, 2]
    return float(z.max() - z.min()) if z.size else None


def observe_parallel_initial_gate(
    boundary: ResetBoundaryReceipt,
    *,
    timeout_s: float = 5.0,
    namespace: str | None = None,
    teacher_profile: bool = False,
) -> InitialGateObservation:
    """Collect fresh joint, goal, scene, graph and MuJoCo contact observations."""

    from so101_demo.backends.mujoco.teleop_runtime import current_evidence

    evidence = current_evidence(boundary.simulation_session_id, timeout_s=timeout_s)
    evidence_received = time.monotonic()
    if str(evidence.reset_epoch) != boundary.reset_epoch.removeprefix("reset-"):
        raise RuntimeError("POINT_INITIAL_GATE_RESET_EPOCH")

    from action_msgs.msg import GoalStatusArray
    from action_msgs.srv import CancelGoal
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import GetPlanningScene
    import rclpy
    from rclpy.qos import qos_profile_action_status_default

    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init(**container_ros_init_options())
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
                and RuntimeBinding.worker_node_inventory_matches(graph,
                    namespace=namespace,teacher_profile=teacher_profile)
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
