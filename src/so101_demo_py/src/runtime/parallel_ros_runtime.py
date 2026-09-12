"""Concrete, observation-backed ROS/MuJoCo ports for one parallel Worker."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import io
import json
import math
import os
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
from typing import Callable, Mapping

import numpy as np

from ..application.object_pose import RgbdLocalizer
from ..application.qualification_stack import ros2_command
from ..core.detection import DetectionCandidate
from ..core.task_geometry import Pose7
from ..parallel_batch.broker import BrokerResponse
from ..parallel_batch.contracts import ModelOutcome, RunMode
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


@dataclass(frozen=True)
class ResetBoundaryReceipt:
    reset_epoch: str
    simulation_session_id: str
    reset_completed_monotonic_s: float
    simulation_time_s: float

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
    from action_msgs.msg import GoalStatusArray
    from moveit_msgs.msg import PlanningSceneComponents
    from moveit_msgs.srv import GetPlanningScene
    from ..backends.mujoco.client import MujocoRosClient

    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init()
    service_node = rclpy.create_node("so101_parallel_gate_services")
    joint_node = rclpy.create_node("so101_parallel_gate_joints")
    graph_node = rclpy.create_node("so101_parallel_gate_graph")
    services = MujocoRosClient(service_node, joint_node, service_timeout_s=timeout_s)
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
            10,
        )
        for topic in topics
    ]
    scene_client = service_node.create_client(GetPlanningScene, "/get_planning_scene")
    try:
        if not scene_client.wait_for_service(timeout_sec=timeout_s):
            raise RuntimeError("POINT_INITIAL_GATE_SCENE_UNAVAILABLE")
        scene_request = GetPlanningScene.Request()
        scene_request.components.components = (
            PlanningSceneComponents.ROBOT_STATE_ATTACHED_OBJECTS
        )
        scene_future = scene_client.call_async(scene_request)
        deadline = time.monotonic() + timeout_s
        previous_graph = None
        stable_graph_samples = 0
        while time.monotonic() < deadline:
            services.progress()
            rclpy.spin_once(service_node, timeout_sec=0.01)
            rclpy.spin_once(graph_node, timeout_sec=0.01)
            graph = tuple(
                sorted(
                    f"{namespace.rstrip('/')}/{name}"
                    for name, namespace in graph_node.get_node_names_and_namespaces()
                )
            )
            if graph == previous_graph:
                stable_graph_samples += 1
            else:
                previous_graph = graph
                stable_graph_samples = 1
            if (
                services.joint_callback_count > 0
                and set(goal_receipts) == set(topics)
                and scene_future.done()
                and stable_graph_samples >= 2
            ):
                break
        else:
            raise RuntimeError("POINT_INITIAL_GATE_OBSERVATION_TIMEOUT")
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
            services.latest_joint_positions(),
            tuple(sorted(goal_ids)),
            attached,
            evidence.has_contact,
            graph,
            stable_graph_samples >= 2,
        )
    finally:
        del subscriptions
        graph_node.destroy_node()
        joint_node.destroy_node()
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
        "recovery",
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
        if call is None:
            from ..backends.mujoco.teleop_runtime import transactional_reset

            value = transactional_reset(
                self.resources.session_id,
                expected_object_position=tuple(point["cup_position_world_m"]),
            )
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
        receipt = ResetBoundaryReceipt(
            f"reset-{value.new_epoch}",
            value.simulation_session_id,
            time.monotonic(),
            evidence.simulation_time_s,
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
        valid = (
            type(value) is InitialGateObservation
            and value.reset_epoch == reset_receipt.reset_epoch
            and value.simulation_session_id == reset_receipt.simulation_session_id
            and value.source_frame_monotonic_s > reset_receipt.reset_completed_monotonic_s
            and all(abs(actual - expected) <= 0.002 for actual, expected in zip(
                value.joint_positions, _RESET_JOINTS, strict=True
            ))
            and not value.active_controller_goal_ids
            and not value.moveit_attached_object_ids
            and value.has_contact is False
            and value.node_graph_stable is True
            and len(value.worker_node_fqns) == len(set(value.worker_node_fqns))
        )
        if not valid:
            raise RuntimeError("POINT_INITIAL_GATE_OBSERVATION_REJECTED")
        return SimpleNamespace(
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
                )
                self._rgbd[stamp] = (source, camera, depth, color.header.frame_id)
                source = None
                return receipt
            write_png_rgb8(rgb, path)
            return SourceStampedCapture(path, received)
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
        try:
            localized = BrokerMaskLocalizer().localize(
                broker_result,
                camera_info=camera,
                depth_message=depth,
                lookup_exact=lambda target, frame, stamp: source.lookup_exact(
                    target, frame, stamp, 0.2
                ),
            )
        finally:
            source.close()
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
        from ..backends.mujoco.teleop_runtime import current_evidence

        evidence = current_evidence(reset_receipt.simulation_session_id)
        if (
            evidence.simulation_session_id != reset_receipt.simulation_session_id
            or f"reset-{evidence.reset_epoch}" != reset_receipt.reset_epoch
        ):
            raise RuntimeError("SOURCE_CLOCK_IDENTITY")
        return evidence.simulation_time_s

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
            if response.outcome is ModelOutcome.QUALIFIED:
                self._admission_candidates[response.request.request_id] = response
                try:
                    localized = self.localize(lease, response)
                except Exception:
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
        )

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

    def publish_pose(self, admitted):
        call = self.dependencies.get("publish_pose")
        if call is not None:
            return call(admitted)
        import rclpy
        from geometry_msgs.msg import PoseStamped

        initialized_here = not rclpy.ok()
        if initialized_here:
            rclpy.init()
        node = rclpy.create_node("so101_parallel_pose_publisher")
        publisher = node.create_publisher(PoseStamped, "/cup_pose", 10)
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
            while publisher.get_subscription_count() < 1 and time.monotonic() < deadline:
                rclpy.spin_once(node, timeout_sec=0.02)
            if publisher.get_subscription_count() < 1:
                return False
            publisher.publish(message)
            rclpy.spin_once(node, timeout_sec=0.05)
            return True
        finally:
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

        if not rclpy.ok():
            rclpy.init()
        node = rclpy.create_node(
            "so101_parallel_planner",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        loaded = load_dynamic_policy_variant(
            Path(get_package_share_directory("so101_demo_py")), backend="mujoco"
        )
        scene = RosTaskScenePort(node, "mujoco", loaded.template.planning_timeout_s)
        self._planner = RosDynamicPlanPrefixAdapter(node, loaded.template, scene)
        return self._planner

    def plan_prefix(self, lease, admitted, states):
        return self._planning_adapter()(lease, admitted, states)

    def consumer_ready(self, child):
        call = self.dependencies.get("consumer_ready")
        if call is not None:
            return call(child)
        from .task_batch_runtime import RosGraphProbe

        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if not Path(f"/proc/{child.pid}").exists():
                return False
            if RosGraphProbe().subscription_count(
                "/so101_dynamic_cup_pick_place", "/cup_pose"
            ) == 1:
                return True
            time.sleep(0.05)
        return False

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

        passed = status == 0 and manifest.is_file()
        decision = RuntimeDecision(
            AttemptStatus.PASSED if passed else AttemptStatus.INDETERMINATE,
            "OK" if passed else "DYNAMIC_EXECUTION_RECEIPT_MISSING",
            physical_action_proven_absent=False,
        )
        return ExecutionCompletionReceipt(decision, time.monotonic())

    def capture_numeric_evidence(self, lease, localized, root, boundary):
        root.mkdir(parents=True, exist_ok=False)
        value, depth, localized_object = self._localized[lease.attempt_id]
        if value is not localized:
            raise RuntimeError("NUMERIC_LOCALIZATION_IDENTITY")
        from ..backends.mujoco.teleop_runtime import current_evidence

        physical = current_evidence(self.resources.session_id)
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
        return NumericEvidenceReceipt(*paths, observed)

    def cancel_motion(self, lease):
        call = self.dependencies.get("cancel_motion")
        if call is not None:
            return call(lease)
        return self.reset_point(lease) is not None

    def confirm_no_controller_goal(self, lease):
        call = self.dependencies.get("confirm_no_controller_goal")
        if call is not None:
            return call(lease)
        receipt = self._reset_receipts.get(lease.attempt_id)
        if receipt is None:
            return False
        observed = observe_parallel_initial_gate(receipt)
        return not observed.active_controller_goal_ids

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
