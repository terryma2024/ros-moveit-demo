from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import stat
from types import SimpleNamespace

import numpy as np
import pytest


PACKAGE = Path(__file__).resolve().parents[1]
EXPECTED_FINAL_CUP_POSE_WORLD = (
    -0.08, -0.25, 0.1648, 0.0, 0.0, 0.0, 1.0,
)


def _lease():
    return SimpleNamespace(
        batch_id="batch-1",
        coordinator_epoch=1,
        worker_id="worker-01",
        worker_generation=1,
        point_id="task_start",
        attempt_id="attempt-1",
        lease_generation=1,
    )


def _valid_worker_nodes():
    return tuple(sorted((
        "/arm_controller", "/controller_manager", "/gripper_controller",
        "/joint_state_broadcaster", "/move_group", "/move_group/moveit",
        "/move_group_private_123456", "/moveit_987654",
        "/moveit_simple_controller_manager", "/mujoco_ros2_control_node",
        "/robot_state_publisher", "/robotsystem", "/so101_base_to_camera_link",
        "/so101_camera_link_to_task_camera_frame",
        "/transform_listener_impl_7a8b9c",
    )))


def test_broker_generation_binding_is_monotonic_and_fail_closed():
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    runtime = ParallelRosRuntimePorts(
        SimpleNamespace(), catalog={}, broker_generation=1
    )

    assert runtime.bind_broker_generation(2) is True
    assert runtime.broker_generation == 2
    for invalid in (1, 0, -1, True, None, "3"):
        with pytest.raises(RuntimeError, match="BROKER_GENERATION"):
            runtime.bind_broker_generation(invalid)
        assert runtime.broker_generation == 2


def test_production_initial_gate_queries_goals_and_uses_action_status_qos(monkeypatch):
    import rclpy
    from rclpy.qos import qos_profile_action_status_default
    from so101_demo.backends.mujoco import teleop_runtime
    from so101_demo.runtime import parallel_ros_runtime as runtime_module

    captured_qos = []

    class Future:
        def __init__(self, value):
            self.value = value

        def done(self):
            return True

        def result(self):
            return self.value

    class ServiceClient:
        def wait_for_service(self, *, timeout_sec):
            return timeout_sec > 0.0

        def call_async(self, _request):
            return Future(SimpleNamespace(
                scene=SimpleNamespace(
                    robot_state=SimpleNamespace(attached_collision_objects=[])
                )
            ))

    class CancelClient:
        def wait_for_service(self, *, timeout_sec):
            return timeout_sec > 0.0

        def call_async(self, _request):
            return Future(SimpleNamespace(goals_canceling=[]))

    class Node:
        def __init__(self, name):
            self.name = name
            self.callbacks = []
            self.graph_reads = 0

        def create_client(self, _service, name):
            return CancelClient() if name.endswith("/cancel_goal") else ServiceClient()

        def create_subscription(self, _message, _topic, callback, qos):
            captured_qos.append(qos)
            self.callbacks.append(callback)
            return object()

        def get_node_names_and_namespaces(self):
            valid = _valid_worker_nodes()
            incomplete = tuple(
                node for node in valid if node != "/so101_base_to_camera_link"
            )
            nodes = incomplete if self.graph_reads < 2 else valid
            self.graph_reads += 1
            return [
                (node.rsplit("/", 1)[1], node.rsplit("/", 1)[0] or "/")
                for node in nodes
            ]

        def destroy_node(self):
            return None

    def create_node(name):
        return Node(name)

    def spin_once(node, *, timeout_sec):
        assert timeout_sec == 0.01

    monkeypatch.setattr(rclpy, "ok", lambda: True)
    monkeypatch.setattr(rclpy, "create_node", create_node)
    monkeypatch.setattr(rclpy, "spin_once", spin_once)
    fingertip_contacts = {"left": (), "right": ()}
    monkeypatch.setattr(
        teleop_runtime,
        "current_evidence",
        lambda *_args, **_kwargs: SimpleNamespace(
            reset_epoch=2,
            has_contact=True,
            left_fingertip_contacts=fingertip_contacts["left"],
            right_fingertip_contacts=fingertip_contacts["right"],
            other_object_contacts=(SimpleNamespace(geom2="table"),),
        ),
    )

    table_supported = runtime_module.observe_parallel_initial_gate(
        runtime_module.ResetBoundaryReceipt(
            "reset-2", "session-1", 1.0, 2.0, 2, (0.0,) * 6
        ),
        timeout_s=0.25,
    )
    assert table_supported.has_contact is False
    assert table_supported.worker_node_fqns == _valid_worker_nodes()

    fingertip_contacts["left"] = (SimpleNamespace(geom1="left_fingertip"),)
    fingertip_contact = runtime_module.observe_parallel_initial_gate(
        runtime_module.ResetBoundaryReceipt(
            "reset-2", "session-1", 1.0, 2.0, 2, (0.0,) * 6
        ),
        timeout_s=0.25,
    )
    assert fingertip_contact.has_contact is True

    assert captured_qos == [qos_profile_action_status_default] * 6

    with pytest.raises(
        RuntimeError,
        match=r"^POINT_INITIAL_GATE_OBSERVATION_TIMEOUT:joint_state$",
    ):
        runtime_module.observe_parallel_initial_gate(
            runtime_module.ResetBoundaryReceipt("reset-2", "session-1", 1.0, 2.0),
            timeout_s=0.05,
        )


def test_initial_gate_requires_fresh_observed_joints_goals_attachment_contact_and_nodes():
    from so101_demo.runtime.parallel_ros_runtime import (
        InitialGateObservation,
        ParallelRosRuntimePorts,
        ResetBoundaryReceipt,
    )

    reset = ResetBoundaryReceipt("reset-2", "session-1", 10.0, 12.0)
    observation = InitialGateObservation(
        reset_epoch="reset-2",
        simulation_session_id="session-1",
        source_frame_monotonic_s=11.0,
        joint_positions=(0.0,) * 6,
        active_controller_goal_ids=(),
        moveit_attached_object_ids=(),
        has_contact=False,
        worker_node_fqns=_valid_worker_nodes(),
    )
    ports = ParallelRosRuntimePorts.for_test(
        resources=SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        observe_initial=lambda _boundary: observation,
    )
    lease = _lease()
    gate = ports.initial_gate(lease, reset)
    for field in (
        "batch_id",
        "coordinator_epoch",
        "worker_id",
        "worker_generation",
        "point_id",
        "attempt_id",
        "lease_generation",
    ):
        assert getattr(gate, field) == getattr(lease, field)
    assert gate.canonical_joints is True
    assert gate.no_controller_goal is True
    assert gate.no_attachment is True
    assert gate.no_contact is True
    assert gate.no_stale_node is True
    assert gate.source_frame_monotonic_s == 11.0

    for changed in (
        {"joint_positions": (0.1,) + (0.0,) * 5},
        {"active_controller_goal_ids": ("goal-1",)},
        {"moveit_attached_object_ids": ("plastic_cup",)},
        {"has_contact": True},
        {"worker_node_fqns": ("/move_group", "/move_group")},
    ):
        invalid = InitialGateObservation(
            **{**observation.__dict__, **changed}
        )
        ports = ParallelRosRuntimePorts.for_test(
            resources=SimpleNamespace(session_id="session-1"),
            catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
            observe_initial=lambda _boundary, value=invalid: value,
        )
        with pytest.raises(RuntimeError, match="POINT_INITIAL_GATE"):
            ports.initial_gate(_lease(), reset)


def test_initial_gate_rejection_names_every_failed_predicate_in_fixed_order():
    from so101_demo.runtime.parallel_ros_runtime import (
        InitialGateObservation,
        ParallelRosRuntimePorts,
        ResetBoundaryReceipt,
    )

    reset = ResetBoundaryReceipt("reset-2", "session-1", 10.0, 12.0)
    rejected = InitialGateObservation(
        reset_epoch="reset-3",
        simulation_session_id="session-2",
        source_frame_monotonic_s=9.0,
        joint_positions=(0.1,) + (0.0,) * 5,
        active_controller_goal_ids=("goal-1",),
        moveit_attached_object_ids=("plastic_cup",),
        has_contact=True,
        worker_node_fqns=("/move_group",),
        node_graph_stable=False,
    )
    ports = ParallelRosRuntimePorts.for_test(
        resources=SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        observe_initial=lambda _boundary: rejected,
    )
    expected = (
        "POINT_INITIAL_GATE_OBSERVATION_REJECTED:reset_epoch,simulation_session,"
        "freshness,joints,goals,attachment,contact,stable_graph,worker_nodes"
    )
    with pytest.raises(RuntimeError) as rejected_error:
        ports.initial_gate(_lease(), reset)
    rejection, node_payload = str(rejected_error.value).split(";worker_nodes=", 1)
    assert rejection == expected
    assert json.loads(node_payload) == {
        "duplicates": [],
        "missing": [
            node for node in ParallelRosRuntimePorts.expected_worker_nodes()
            if node != "/move_group"
        ],
        "truncated": False,
        "unexpected": [],
    }

    ports.dependencies["observe_initial"] = lambda _boundary: object()
    with pytest.raises(
        RuntimeError,
        match=r"^POINT_INITIAL_GATE_OBSERVATION_REJECTED:type$",
    ):
        ports.initial_gate(_lease(), reset)


def test_broker_mask_is_decoded_row_major_and_localized_against_exact_depth_and_tf():
    from so101_demo.parallel_batch.broker import BrokerResponse
    from so101_demo.parallel_batch.contracts import (
        ExecutionKind,
        InferenceRequest,
        ModelOutcome,
    )
    from so101_demo.runtime.parallel_ros_runtime import BrokerMaskLocalizer

    request = InferenceRequest(
        request_id="attempt-1-yolo",
        model_id="plastic-cup-yolo11n-seg-v1",
        execution_kind=ExecutionKind.ATTEMPT,
        batch_id="batch-1",
        coordinator_epoch=1,
        worker_id="worker-01",
        worker_generation=1,
        point_id="task_start",
        lease_generation=1,
        reset_epoch="reset-2",
        image_timestamp_s=12.0,
        input_relative_path=(
            "worker-01/attempts/task_start/attempt-1/working/"
            "perception/input/rgb.npy"
        ),
        input_sha256="ab" * 32,
        attempt_id="attempt-1",
    )
    candidate_document = {
        "model_id": "plastic-cup-yolo11n-seg-v1",
        "weights_sha256": "ab" * 32,
        "runtime_device": "cuda",
        "inference_latency_ms": 1.0,
        "shape": [2, 3, 3],
        "source_stamp_ns": 12_000_000_000,
        "source_frame_id": "task_camera_frame",
        "candidates": [
            {
                "instance_id": "cup-1",
                "class_id": "plastic_cup",
                "confidence": 0.9,
                "bbox_xyxy": [0.0, 0.0, 3.0, 2.0],
                "segmentation_quality": 0.95,
                "mask_rle": {"shape": [2, 3], "counts": [1, 2, 2, 1]},
            }
        ],
    }
    response = BrokerResponse(
        request,
        1,
        ModelOutcome.QUALIFIED,
        candidate_document,
        None,
        1.0,
        2.0,
        1.1,
        2.1,
        1.2,
    )
    camera = SimpleNamespace(
        width=3,
        height=2,
        header=SimpleNamespace(
            frame_id="task_camera_frame",
            stamp=SimpleNamespace(sec=12, nanosec=0),
        ),
    )
    depth = SimpleNamespace(
        width=3,
        height=2,
        header=camera.header,
        data=b"depth",
    )
    seen = {}

    class Localizer:
        def localize(self, candidate, actual_camera, actual_depth, lookup):
            seen.update(
                mask=np.array(candidate.mask, copy=True),
                camera=actual_camera,
                depth=actual_depth,
                transform=lookup("world", candidate.source_frame_id, candidate.source_stamp_ns),
            )
            return "localized-from-mask"

    value = BrokerMaskLocalizer(localizer=Localizer()).localize(
        response,
        camera_info=camera,
        depth_message=depth,
        lookup_exact=lambda target, source, stamp: (target, source, stamp),
    )
    assert value == "localized-from-mask"
    assert seen["mask"].tolist() == [[False, True, True], [False, False, True]]
    assert seen["camera"] is camera
    assert seen["depth"] is depth
    assert seen["transform"] == ("world", "task_camera_frame", 12_000_000_000)


def test_localization_allows_bounded_fresh_stack_tf_discovery(monkeypatch):
    from so101_demo.parallel_batch.contracts import ExecutionKind, InferenceRequest
    from so101_demo.runtime import parallel_ros_runtime as runtime_module
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    stamp_ns = 12_000_000_000
    seen = {}

    class Localizer:
        @staticmethod
        def localize(_response, *, camera_info, depth_message, lookup_exact):
            seen["camera"] = camera_info
            seen["depth"] = depth_message
            seen["transform"] = lookup_exact(
                "world", "task_camera_frame", stamp_ns
            )
            return SimpleNamespace(center_world_xyz=(0.02, -0.28, 0.165))

    class Source:
        @staticmethod
        def lookup_exact(target, frame, stamp, timeout_s):
            seen["lookup"] = (target, frame, stamp, timeout_s)
            return "exact-transform"

    monkeypatch.setattr(runtime_module, "BrokerMaskLocalizer", lambda: Localizer())
    camera = object()
    depth = SimpleNamespace(data=b"depth")
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(session_id="session-1"), catalog={}
    )
    ports._rgbd[stamp_ns] = (Source(), camera, depth, "task_camera_frame")
    request = InferenceRequest(
        request_id="attempt-1-yolo",
        model_id="plastic-cup-yolo11n-seg-v1",
        execution_kind=ExecutionKind.ATTEMPT,
        batch_id="batch-1",
        coordinator_epoch=1,
        worker_id="worker-01",
        worker_generation=1,
        point_id="task_start",
        lease_generation=1,
        reset_epoch="reset-2",
        image_timestamp_s=12.0,
        input_relative_path=(
            "worker-01/attempts/task_start/attempt-1/working/"
            "perception/input/rgb.npy"
        ),
        input_sha256="ab" * 32,
        attempt_id="attempt-1",
    )
    response = SimpleNamespace(
        request=request,
        candidate={"source_stamp_ns": stamp_ns},
        broker_generation=1,
    )

    localized = ports.localize(_lease(), response)

    assert seen["camera"] is camera
    assert seen["depth"] is depth
    assert seen["transform"] == "exact-transform"
    assert seen["lookup"] == (
        "world", "task_camera_frame", stamp_ns, 5.0
    )
    assert localized.request is request
    assert localized.depth_timestamp_s == 12.0
    assert localized.tf_timestamp_s == 12.0


def test_production_port_factory_binds_every_task10_port_without_empty_side_effects():
    from so101_demo.cli.mujoco_parallel_batch import RosWorkerRuntimePorts

    ports = RosWorkerRuntimePorts(
        SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
    ).kwargs()
    assert set(ports) == RosWorkerRuntimePorts.REQUIRED
    assert all(callable(value) for value in ports.values())
    assert all("RUNTIME_PORT_NOT_READY" not in repr(value) for value in ports.values())


def test_recovery_requires_observed_child_and_ros_graph_absence():
    from so101_demo.runtime.parallel_ros_runtime import (
        ParallelRosRuntimePorts,
        ShutdownObservation,
    )

    resources = SimpleNamespace(
        worker_id="worker-01", generation=1, session_id="session-1"
    )
    observations = [
        ShutdownObservation((9001,), (), True),
        ShutdownObservation((), ("/move_group",), True),
        ShutdownObservation((), (), True),
    ]
    ports = ParallelRosRuntimePorts(
        resources,
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        dependencies={"observe_shutdown": lambda *_args, **_kwargs: observations.pop(0)},
    )
    import time
    deadline = time.monotonic() + 10.0
    assert ports.recovery("worker-01", 1, deadline) is False
    assert ports.recovery("worker-01", 1, deadline) is False
    assert ports.recovery("worker-01", 1, deadline) is True
    assert ports.recovery("worker-02", 1, deadline) is False


def test_f21_config_reuses_dynamic_age_and_orders_workspace_min_then_max():
    from so101_demo.core.dynamic_pick_policy import load_dynamic_policy_variant
    from so101_demo.parallel_batch.contracts import load_parallel_runtime_config

    template = load_dynamic_policy_variant(PACKAGE, backend="mujoco").template
    config = load_parallel_runtime_config(
        PACKAGE / "config/mujoco/parallel_batch_v1.yaml"
    )
    assert config.max_frame_age_s == template.maximum_source_age_s == 5.0
    assert config.max_rgbd_skew_s == 0.0
    assert config.max_tf_skew_s == 0.0
    lower, upper = template.workspace_bounds_m[:3], template.workspace_bounds_m[3:]
    assert all(minimum < maximum for minimum, maximum in zip(lower, upper, strict=True))


@pytest.mark.parametrize("source_now,accepted", [(12.0, True), (1000.0, False)])
def test_task5_policy_persists_admission_and_rejects_mixed_source_clock(
    tmp_path, source_now, accepted
):
    from so101_demo.parallel_batch.artifacts import ValidationWorkspace
    from so101_demo.parallel_batch.contracts import (
        ExecutionKind,
        InferenceRequest,
        ModelOutcome,
        RunMode,
        ValidationIdentity,
        load_parallel_runtime_config,
    )
    from so101_demo.parallel_batch.broker import BrokerResponse
    from so101_demo.parallel_batch.perception import LocalizedPose, PerceptionError
    from so101_demo.runtime.parallel_ros_runtime import (
        AdmittedPose,
        ParallelRosRuntimePorts,
        ResetBoundaryReceipt,
    )
    from so101_demo.runtime.parallel_worker_runtime import InferenceSnapshotReceipt

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    workspace = ValidationWorkspace.create(
        worker_root,
        ValidationIdentity(
            lease.batch_id, lease.coordinator_epoch, lease.worker_id,
            lease.worker_generation, lease.point_id, lease.attempt_id,
            lease.lease_generation,
        ),
        reset_epoch="reset-2",
        source_stamp={"simulation_time_s": 10.0},
        run_mode=RunMode.PLAN_ONLY,
    )
    rgb_path = workspace.path / "perception/input/rgb.npy"
    rgb_path.parent.mkdir(parents=True)
    rgb_path.write_bytes(b"npy")
    rgb_path.chmod(0o400)
    snapshot = InferenceSnapshotReceipt(
        rgb_path, 11.0, 12_000_000_000, "task_camera_frame", (2, 3, 3),
        hashlib.sha256(b"npy").hexdigest(),
    )
    depth = SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=12, nanosec=0)),
        data=b"depth",
    )
    resources = SimpleNamespace(
        worker_id="worker-01", generation=1, session_id="session-1"
    )
    config = load_parallel_runtime_config(
        PACKAGE / "config/mujoco/parallel_batch_v1.yaml"
    )
    ports = ParallelRosRuntimePorts(
        resources,
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        config=config,
        broker_generation=1,
        dependencies={
            "workspace_provider": lambda _lease: workspace,
            "authorize": lambda _request: True,
            "source_clock": lambda _reset: source_now,
            "dynamic_template": lambda: SimpleNamespace(
                workspace_bounds_m=(-0.3, -0.5, 0.1, 0.35, 0.2, 0.5)
            ),
        },
    )
    ports._reset_receipts[lease.attempt_id] = ResetBoundaryReceipt(
        "reset-2", "session-1", 10.0, 10.0
    )
    ports._rgbd[snapshot.source_stamp_ns] = (
        object(), object(), depth, "task_camera_frame"
    )
    requested = []

    def broker_request(model_id, before_send):
        request = InferenceRequest(
            request_id=f"attempt-1-{model_id}", model_id=model_id,
            execution_kind=ExecutionKind.VALIDATION, batch_id="batch-1",
            coordinator_epoch=1, worker_id="worker-01", worker_generation=1,
            point_id="task_start", lease_generation=1, reset_epoch="reset-2",
            image_timestamp_s=12.0,
            input_relative_path=(
                "worker-01/validations/task_start/attempt-1/working/"
                "perception/input/rgb.npy"
            ),
            input_sha256=snapshot.input_sha256, validation_id="attempt-1",
        )
        before_send(request)
        requested.append(model_id)
        response = BrokerResponse(
            request, 1, ModelOutcome.QUALIFIED,
            {
                "model_id": model_id, "weights_sha256": "a" * 64,
                "runtime_device": "cuda", "inference_latency_ms": 1.0,
                "shape": [2, 3, 3], "source_stamp_ns": 12_000_000_000,
                "source_frame_id": "task_camera_frame", "candidates": [{
                    "instance_id": "cup-1", "class_id": "plastic_cup",
                    "confidence": 0.9, "bbox_xyxy": [0.0, 0.0, 3.0, 2.0],
                    "segmentation_quality": 0.95,
                    "mask_rle": {"shape": [2, 3], "counts": [0, 6]},
                }],
            },
            None, 1.0, 2.0, 1.1, 2.1, 1.2,
        )
        ports.localize = lambda _lease, _response: LocalizedPose(
            request, 1, "session-1", 12.0, hashlib.sha256(b"depth").hexdigest(),
            12.0, "task_camera_frame", "world", (0.02, -0.28, 0.165),
            (0.0, 0.0, 0.0, 1.0),
        )
        return response

    if accepted:
        admitted = ports.run_perception_chain(
            lease, ExecutionKind.VALIDATION, snapshot, broker_request
        )
        assert isinstance(admitted, AdmittedPose)
        assert requested == [config.yolo_model_id]
        assert (workspace.path / "pose_accepted.json").is_file()
    else:
        with pytest.raises(PerceptionError, match="STALE_RGBD"):
            ports.run_perception_chain(
                lease, ExecutionKind.VALIDATION, snapshot, broker_request
            )
        assert requested == []
        assert not (workspace.path / "pose_accepted.json").exists()


@pytest.mark.parametrize(
    "outcome,response_reason,expected_type,expected_message",
    [
        (
            "INFRA_ERROR",
            "INPUT_OPENED_OWNER_MODE",
            "BrokerResponse.INFRA_ERROR",
            "INPUT_OPENED_OWNER_MODE",
        ),
        ("NORMAL_REJECTION", None, None, None),
    ],
)
def test_perception_terminal_preserves_only_broker_infrastructure_diagnostic(
    tmp_path, outcome, response_reason, expected_type, expected_message
):
    from so101_demo.parallel_batch.artifacts import ValidationWorkspace
    from so101_demo.parallel_batch.broker import BrokerResponse
    from so101_demo.parallel_batch.contracts import (
        ExecutionKind,
        InferenceRequest,
        ModelOutcome,
        RunMode,
        ValidationIdentity,
        load_parallel_runtime_config,
    )
    from so101_demo.runtime.parallel_ros_runtime import (
        ParallelRosRuntimePorts,
        PerceptionTerminal,
        ResetBoundaryReceipt,
    )
    from so101_demo.runtime.parallel_worker_runtime import InferenceSnapshotReceipt

    lease = _lease()
    workspace = ValidationWorkspace.create(
        tmp_path / "worker-01",
        ValidationIdentity(
            lease.batch_id, lease.coordinator_epoch, lease.worker_id,
            lease.worker_generation, lease.point_id, lease.attempt_id,
            lease.lease_generation,
        ),
        reset_epoch="reset-2",
        source_stamp={"simulation_time_s": 10.0},
        run_mode=RunMode.PLAN_ONLY,
    )
    rgb_path = workspace.path / "perception/input/rgb.npy"
    rgb_path.parent.mkdir(parents=True)
    rgb_path.write_bytes(b"npy")
    rgb_path.chmod(0o400)
    snapshot = InferenceSnapshotReceipt(
        rgb_path, 11.0, 12_000_000_000, "task_camera_frame", (2, 3, 3),
        hashlib.sha256(b"npy").hexdigest(),
    )
    depth = SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=12, nanosec=0)),
        data=b"depth",
    )
    config = load_parallel_runtime_config(
        PACKAGE / "config/mujoco/parallel_batch_v1.yaml"
    )
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(
            worker_id="worker-01", generation=1, session_id="session-1"
        ),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        config=config,
        broker_generation=1,
        dependencies={
            "workspace_provider": lambda _lease: workspace,
            "authorize": lambda _request: True,
            "source_clock": lambda _reset: 12.0,
            "dynamic_template": lambda: SimpleNamespace(
                workspace_bounds_m=(-0.3, -0.5, 0.1, 0.35, 0.2, 0.5)
            ),
        },
    )
    ports._reset_receipts[lease.attempt_id] = ResetBoundaryReceipt(
        "reset-2", "session-1", 10.0, 10.0
    )
    ports._rgbd[snapshot.source_stamp_ns] = (
        SimpleNamespace(close=lambda: None), object(), depth, "task_camera_frame"
    )

    def broker_request(model_id, before_send):
        request = InferenceRequest(
            request_id=f"attempt-1-{model_id}", model_id=model_id,
            execution_kind=ExecutionKind.VALIDATION, batch_id="batch-1",
            coordinator_epoch=1, worker_id="worker-01", worker_generation=1,
            point_id="task_start", lease_generation=1, reset_epoch="reset-2",
            image_timestamp_s=12.0,
            input_relative_path=(
                "worker-01/validations/task_start/attempt-1/working/"
                "perception/input/rgb.npy"
            ),
            input_sha256=snapshot.input_sha256, validation_id="attempt-1",
        )
        before_send(request)
        return BrokerResponse(
            request, 1, ModelOutcome(outcome), None, response_reason,
            1.0, 2.0, 1.1, 2.1, 1.2,
        )

    terminal = ports.run_perception_chain(
        lease, ExecutionKind.VALIDATION, snapshot, broker_request
    )

    assert isinstance(terminal, PerceptionTerminal)
    assert terminal.failure_type == expected_type
    assert terminal.failure_message == expected_message


def test_point_reset_uses_qualified_override_and_scene_restore():
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    calls = []
    lease = _lease()
    reset_value = SimpleNamespace(
        simulation_session_id="session-1", new_epoch=9,
    )
    scene = SimpleNamespace(success=True)

    def execute(session_id, *, keyframe, cup_position_world_m):
        calls.append((session_id, keyframe, cup_position_world_m))
        return reset_value, scene

    ports = ParallelRosRuntimePorts(
        SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.1, -0.2, 0.17]}},
        dependencies={
            "execute_reset": execute,
            "current_evidence": lambda _session: SimpleNamespace(
                simulation_session_id="session-1", reset_epoch=9,
                simulation_time_s=4.5,
            )
        },
    )
    receipt = ports.reset_point(lease)
    assert calls == [("session-1", "task_start", (0.1, -0.2, 0.17))]
    assert receipt.reset_epoch == "reset-9"
    assert receipt.reset_epoch_value == 9
    for field in (
        "batch_id",
        "coordinator_epoch",
        "worker_id",
        "worker_generation",
        "point_id",
        "attempt_id",
        "lease_generation",
    ):
        assert type(getattr(receipt, field)) is type(getattr(lease, field))
        assert getattr(receipt, field) == getattr(lease, field)


def test_capture_rgb_mirror_creates_private_directory_chain(tmp_path, monkeypatch):
    from so101_demo.cli import rgbd_point_cloud
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    worker_root = tmp_path / "workers/worker-01"
    worker_root.mkdir(parents=True, mode=0o700)
    broker_root = tmp_path / "broker-inputs"
    broker_root.mkdir(mode=0o700)
    color = SimpleNamespace(
        header=SimpleNamespace(
            frame_id="task_camera_frame",
            stamp=SimpleNamespace(sec=12, nanosec=34),
        )
    )
    source = SimpleNamespace(close=lambda: None)
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
    )
    ports._capture_aligned = lambda: (
        source,
        (object(), color, object()),
        11.0,
    )
    monkeypatch.setattr(
        rgbd_point_cloud,
        "_decode_rgb",
        lambda _message: np.zeros((2, 3, 3), dtype=np.uint8),
    )
    destination = (
        worker_root
        / "attempts/task_start/attempt-1/working/perception/input/rgb.npy"
    )
    previous_umask = os.umask(0o002)
    try:
        receipt = ports.capture_rgb(destination, 10.0)
    finally:
        os.umask(previous_umask)

    mirror = broker_root / destination.relative_to(worker_root.parent)
    assert receipt.path == destination
    assert mirror.stat().st_ino == destination.stat().st_ino
    current = mirror.parent
    while current != broker_root:
        info = current.lstat()
        assert stat.S_ISDIR(info.st_mode)
        assert not current.is_symlink()
        assert info.st_uid == os.getuid()
        assert stat.S_IMODE(info.st_mode) == 0o700
        current = current.parent
    source.close()


def test_initial_gate_requires_exact_worker_node_inventory():
    from so101_demo.runtime.parallel_ros_runtime import (
        InitialGateObservation, ParallelRosRuntimePorts, ResetBoundaryReceipt,
    )

    expected = (
        "/arm_controller", "/gripper_controller", "/joint_state_broadcaster",
        "/move_group", "/mujoco_ros2_control_node", "/robot_state_publisher",
        "/so101_base_to_camera_link", "/so101_camera_link_to_task_camera_frame",
    )
    legitimate_internal = (
        "/controller_manager", "/move_group/moveit",
        "/move_group_private_123456", "/moveit_987654",
        "/moveit_simple_controller_manager", "/robotsystem",
        "/transform_listener_impl_7a8b9c",
    )
    valid_nodes = tuple(sorted((*expected, *legitimate_internal)))
    assert valid_nodes == _valid_worker_nodes()
    reset = ResetBoundaryReceipt("reset-2", "session-1", 10.0, 12.0, 2)
    base = dict(
        reset_epoch="reset-2", simulation_session_id="session-1",
        source_frame_monotonic_s=11.0, joint_positions=(0.0,) * 6,
        active_controller_goal_ids=(), moveit_attached_object_ids=(), has_contact=False,
        worker_node_fqns=valid_nodes,
    )
    ports = ParallelRosRuntimePorts.for_test(
        resources=SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        observe_initial=lambda _boundary: InitialGateObservation(**base),
    )
    assert ports.initial_gate(_lease(), reset).no_stale_node is True
    invalid_node_sets = (
        tuple(node for node in valid_nodes if node != "/arm_controller"),
        (*valid_nodes, "/stale_worker_generation_0"),
        (*valid_nodes, "/moveit_123"),
        tuple("/moveit_bad" if node == "/moveit_987654" else node
              for node in valid_nodes),
        tuple(sorted((*valid_nodes, "/controller_manager"))),
    )
    for nodes in invalid_node_sets:
        ports.dependencies["observe_initial"] = lambda _boundary, value=nodes: (
            InitialGateObservation(**{**base, "worker_node_fqns": value})
        )
        with pytest.raises(RuntimeError, match="POINT_INITIAL_GATE"):
            ports.initial_gate(_lease(), reset)


def test_initial_gate_worker_node_diagnostic_is_bounded_and_deterministic():
    from so101_demo.parallel_batch.worker import _bounded_failure_message
    from so101_demo.runtime.parallel_ros_runtime import (
        InitialGateObservation, ParallelRosRuntimePorts, ResetBoundaryReceipt,
    )

    expected = ParallelRosRuntimePorts.expected_worker_nodes()
    observed = (*expected[:-1], "/zeta", "/alpha", "/alpha", *(
        f"/unknown_{index:02d}_" + "x" * 180 for index in range(24)
    ))
    reset = ResetBoundaryReceipt("reset-2", "session-1", 10.0, 12.0, 2)
    observation = InitialGateObservation(
        reset_epoch="reset-2", simulation_session_id="session-1",
        source_frame_monotonic_s=11.0, joint_positions=(0.0,) * 6,
        active_controller_goal_ids=(), moveit_attached_object_ids=(),
        has_contact=False, worker_node_fqns=observed,
    )
    ports = ParallelRosRuntimePorts.for_test(
        resources=SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        observe_initial=lambda _boundary: observation,
    )

    with pytest.raises(RuntimeError) as rejected_error:
        ports.initial_gate(_lease(), reset)
    rejection, node_payload = str(rejected_error.value).split(";worker_nodes=", 1)
    assert rejection == "POINT_INITIAL_GATE_OBSERVATION_REJECTED:worker_nodes"
    diagnostic = json.loads(node_payload)
    assert diagnostic["missing"] == [expected[-1]]
    assert diagnostic["duplicates"] == ["/alpha"]
    ordered_unexpected = [
        node[:96] for node in sorted(set(observed) - set(expected))
    ]
    assert diagnostic["unexpected"]
    assert diagnostic["unexpected"] == ordered_unexpected[:len(diagnostic["unexpected"])]
    assert len(diagnostic["unexpected"]) <= 16
    assert diagnostic["truncated"] is True
    assert len(node_payload.encode()) <= 320
    assert _bounded_failure_message(rejected_error.value) == str(rejected_error.value)


def _dynamic_execute_manifest(lease, *, session_id, policy_path, status="DONE"):
    from so101_demo.core.domain import State
    from so101_demo.core.dynamic_pick import DYNAMIC_MOTION_STATES
    from so101_demo.core.workflow import SO101_WORKFLOW

    failed = status != "DONE"
    trace = [State.IDLE]
    while not failed and trace[-1] not in SO101_WORKFLOW.terminal_states:
        trace.append(SO101_WORKFLOW.transitions[trace[-1]][0])

    def physical(sequence):
        return {
            "reset_epoch": 17,
            "simulation_step": sequence * 5,
            "publisher_sequence": sequence,
            "cup_position_world_m": [-0.08, -0.25, 0.1648],
            "cup_orientation_world_xyzw": [0.0, 0.0, 0.0, 1.0],
            "cup_linear_velocity_world_m_s": [0.0, 0.0, 0.0],
            "cup_angular_velocity_world_rad_s": [0.0, 0.0, 0.0],
            "left_contact_count": 0,
            "right_contact_count": 0,
            "maximum_normal_force_n": 0.2,
            "table_contact": True,
        }

    events = []
    planning = []
    for index, state in enumerate(trace[:-1]):
        if state not in SO101_WORKFLOW.action_states:
            continue
        item = {
            "state": state.value,
            "before": physical(100 + index * 2),
            "after": physical(101 + index * 2),
        }
        if state in DYNAMIC_MOTION_STATES:
            item.update(
                terminal_joint_positions_rad=[0.0] * 5,
                terminal_joint_state_source_stamp_ns=(index + 1) * 1_000_000,
                execution_reconciliations=[],
            )
            planning.append({
                "kind": "moveit_joint_plan", "state": state.value, "accepted": True,
            })
        if state is State.VALIDATE_FINAL_PLACEMENT:
            item.update(
                expected_cup_pose_world=[-0.08, -0.25, 0.1648, 0.0, 0.0, 0.0, 1.0],
                final_xy_error_m=0.0,
                final_upright_tilt_rad=0.0,
            )
        events.append(item)
    scene = {
        "attached_object_ids": [],
        "world_primitive_counts": {"plastic_cup": 13},
    }
    return {
        "schema": "so101-dynamic-mujoco-execute-v1",
        "parallel_lease_identity": {
            "batch_id": lease.batch_id,
            "coordinator_epoch": lease.coordinator_epoch,
            "worker_id": lease.worker_id,
            "worker_generation": lease.worker_generation,
            "point_id": lease.point_id,
            "attempt_id": lease.attempt_id,
            "lease_generation": lease.lease_generation,
        },
        "status": "ERROR" if failed else "DONE",
        "current_state": "ERROR" if failed else "DONE",
        "failure": "MOVEIT_EXECUTION_FAILED" if failed else None,
        "simulation_session_id": session_id,
        "expected_reset_epoch": 17,
        "policy_path": str(policy_path),
        "policy_sha256": hashlib.sha256(policy_path.read_bytes()).hexdigest(),
        "state_trace": ["IDLE", "ERROR"] if failed else [item.value for item in trace],
        "transition_count": 1 if failed else len(trace) - 1,
        "state_events": [] if failed else events,
        "planning_attempts": [] if failed else planning,
        "final_samples": [] if failed else [physical(1000)],
        "planning_scene_readback": None if failed else scene,
        "release_marker_sequence": None if failed else 900,
        "failure_evidence": ({
            "failure_boundary_state": "IDLE",
            "physical_action_proven_absent": True,
            "terminal_sample": None,
            "planning_scene_readback": None,
            "capture_errors": [],
        } if failed else None),
    }
def test_localization_infrastructure_failure_never_triggers_fallback(tmp_path):
    from so101_demo.application.object_pose import LocalizationError
    from so101_demo.parallel_batch.artifacts import ValidationWorkspace
    from so101_demo.parallel_batch.contracts import (
        ExecutionKind, ModelOutcome, RunMode, ValidationIdentity,
        load_parallel_runtime_config,
    )
    from so101_demo.parallel_batch.broker import BrokerResponse
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts, ResetBoundaryReceipt
    from so101_demo.runtime.parallel_worker_runtime import InferenceSnapshotReceipt

    lease = _lease()
    workspace = ValidationWorkspace.create(
        tmp_path / "workers/worker-01",
        ValidationIdentity(
            lease.batch_id, lease.coordinator_epoch, lease.worker_id,
            lease.worker_generation, lease.point_id, lease.attempt_id,
            lease.lease_generation,
        ),
        reset_epoch="reset-2",
        source_stamp={"simulation_time_s": 10.0},
        run_mode=RunMode.PLAN_ONLY,
    )
    path = tmp_path / "workers/worker-01/validations/task_start/attempt-1/working/perception/input/rgb.npy"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"npy")
    path.chmod(0o400)
    snapshot = InferenceSnapshotReceipt(
        path, 11.0, 12_000_000_000, "task_camera_frame", (2, 3, 3),
        hashlib.sha256(b"npy").hexdigest(),
    )
    depth = SimpleNamespace(
        header=SimpleNamespace(stamp=SimpleNamespace(sec=12, nanosec=0)), data=b"depth"
    )
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_id="worker-01", generation=1, session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        config=load_parallel_runtime_config(PACKAGE / "config/mujoco/parallel_batch_v1.yaml"),
        broker_generation=1,
        dependencies={
                "workspace_provider": lambda _lease: workspace,
            "authorize": lambda _request: True,
            "source_clock": lambda _reset: 12.0,
            "dynamic_template": lambda: SimpleNamespace(
                workspace_bounds_m=(-0.3, -0.5, 0.1, 0.35, 0.2, 0.5)
            ),
        },
    )
    ports._reset_receipts[lease.attempt_id] = ResetBoundaryReceipt(
        "reset-2", "session-1", 10.0, 10.0, 2
    )
    source = SimpleNamespace(close=lambda: None)
    ports._rgbd[snapshot.source_stamp_ns] = (source, object(), depth, "task_camera_frame")
    calls = []

    def broker_request(model_id, before_send):
        from so101_demo.parallel_batch.contracts import InferenceRequest
        request = InferenceRequest(
            request_id=f"attempt-1-{model_id}", model_id=model_id,
            execution_kind=ExecutionKind.VALIDATION, batch_id="batch-1",
            coordinator_epoch=1, worker_id="worker-01", worker_generation=1,
            point_id="task_start", lease_generation=1, reset_epoch="reset-2",
            image_timestamp_s=12.0,
            input_relative_path="worker-01/validations/task_start/attempt-1/working/perception/input/rgb.npy",
            input_sha256=snapshot.input_sha256, validation_id="attempt-1",
        )
        before_send(request)
        calls.append(model_id)
        return BrokerResponse(request, 1, ModelOutcome.QUALIFIED, {
            "model_id": model_id, "weights_sha256": "a" * 64, "runtime_device": "cuda",
            "inference_latency_ms": 1.0, "shape": [2, 3, 3],
            "source_stamp_ns": 12_000_000_000, "source_frame_id": "task_camera_frame",
            "candidates": [{"instance_id": "cup", "class_id": "plastic_cup",
                "confidence": 0.9, "bbox_xyxy": [0.0, 0.0, 3.0, 2.0],
                "segmentation_quality": 0.9,
                "mask_rle": {"shape": [2, 3], "counts": [0, 6]}}]},
            None, 1.0, 2.0, 1.1, 2.1, 1.2)

    ports.localize = lambda *_args: (_ for _ in ()).throw(
        LocalizationError("TF_UNAVAILABLE", "missing")
    )
    with pytest.raises(LocalizationError, match="TF_UNAVAILABLE"):
        ports.run_perception_chain(lease, ExecutionKind.VALIDATION, snapshot, broker_request)
    assert len(calls) == 1


def test_resource_rebind_closes_generation_state_and_uses_new_session():
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    closed = []
    old = SimpleNamespace(worker_id="worker-01", generation=1, session_id="session-g1")
    new = SimpleNamespace(worker_id="worker-01", generation=2, session_id="session-g2")
    ports = ParallelRosRuntimePorts(old, catalog={})
    ports._rgbd[1] = (SimpleNamespace(close=lambda: closed.append("rgbd")), None, None, None)
    ports._pose_publisher_owner = SimpleNamespace(
        close=lambda: closed.append("pose-publisher")
    )
    ports._pose_publisher = object()
    ports._reset_receipts["a"] = object()
    ports._localized["a"] = object()
    ports.rebind_resources(new)
    assert ports.resources is new
    assert ports._rgbd == {}
    assert ports._reset_receipts == {}
    assert ports._localized == {}
    assert closed == ["rgbd", "pose-publisher"]
    assert ports._pose_publisher_owner is None
    assert ports._pose_publisher is None


def test_shutdown_cancels_and_independently_confirms_goals_without_reset(monkeypatch):
    import so101_demo.runtime.parallel_ros_runtime as ros_runtime
    from so101_demo.runtime.parallel_ros_runtime import (
        ParallelRosRuntimePorts,
        ResetBoundaryReceipt,
    )

    events = []
    monkeypatch.setattr(
        ros_runtime,
        "cancel_and_confirm_parallel_goals",
        lambda *, timeout_s: events.append(("cancel", timeout_s)) or True,
    )
    monkeypatch.setattr(
        ros_runtime,
        "observe_no_parallel_goals",
        lambda *, timeout_s: events.append(("confirm", timeout_s)) or True,
    )
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        dependencies={"reset_point": lambda *_args: events.append(("reset",))},
    )
    lease = _lease()
    ports._reset_receipts[lease.attempt_id] = ResetBoundaryReceipt(
        "reset-2", "session-1", 10.0, 10.0, 2
    )
    assert ports.cancel_motion(lease) is True
    assert ports.confirm_no_controller_goal(lease) is True
    assert events == [("cancel", 5.0), ("confirm", 5.0)]


def test_recovery_goal_checks_use_transient_local_action_status_qos(monkeypatch):
    import rclpy
    from rclpy.qos import qos_profile_action_status_default
    from so101_demo.runtime import parallel_ros_runtime as ros_runtime

    captured_qos = []

    class Future:
        @staticmethod
        def done():
            return True

        @staticmethod
        def result():
            return SimpleNamespace(goals_canceling=[])

    class Client:
        @staticmethod
        def wait_for_service(*, timeout_sec):
            return timeout_sec > 0.0

        @staticmethod
        def call_async(_request):
            return Future()

    class Node:
        def __init__(self):
            self.callbacks = []

        def create_subscription(self, _message, _topic, callback, qos):
            captured_qos.append(qos)
            self.callbacks.append(callback)
            return object()

        @staticmethod
        def create_client(_service, _topic):
            return Client()

    class Owner:
        def __init__(self):
            self.node = Node()

        def spin_once(self, *, timeout_sec):
            assert timeout_sec > 0.0
            message = SimpleNamespace(status_list=[])
            for callback in self.node.callbacks:
                callback(message)

        @staticmethod
        def close():
            return None

    monkeypatch.setattr(
        ros_runtime, "_open_isolated_ros_node", lambda *_args, **_kwargs: Owner()
    )

    assert ros_runtime.cancel_and_confirm_parallel_goals(timeout_s=1.0) is True
    assert ros_runtime.observe_no_parallel_goals(timeout_s=1.0) is True
    assert captured_qos == [qos_profile_action_status_default] * 6


def test_isolated_ros_node_owns_executor_for_its_private_context(monkeypatch):
    import rclpy.executors
    from so101_demo.runtime.parallel_ros_runtime import _open_isolated_ros_node

    events = []

    class Context:
        def shutdown(self):
            events.append("private-shutdown")

    node = SimpleNamespace(destroy_node=lambda: events.append("node-destroy"))

    class Executor:
        def __init__(self, *, context):
            events.append(("executor", context))

        def add_node(self, value):
            events.append(("add", value))

        def spin_once(self, *, timeout_sec):
            events.append(("spin", timeout_sec))

        def remove_node(self, value):
            events.append(("remove", value))

        def shutdown(self):
            events.append("executor-shutdown")

    monkeypatch.setattr(rclpy.executors, "SingleThreadedExecutor", Executor)

    class Rclpy:
        context = SimpleNamespace(Context=Context)

        @staticmethod
        def ok():
            return True

        @staticmethod
        def init(*, context):
            events.append(("init", context))

        @staticmethod
        def create_node(name, *, context, **kwargs):
            events.append(("create", name, context, kwargs))
            return node

    owner = _open_isolated_ros_node(Rclpy, "isolated")
    assert owner.node is node
    assert events[0][0] == "init"
    assert events[1][0:2] == ("create", "isolated")
    assert events[0][1] is events[1][2]
    assert events[2] == ("executor", events[0][1])
    assert events[3] == ("add", node)
    owner.spin_once(timeout_sec=0.25)
    assert events[4] == ("spin", 0.25)
    owner.close()
    owner.close()
    assert events[-4:] == [
        ("remove", node), "executor-shutdown", "node-destroy", "private-shutdown"
    ]


def test_pose_publication_waits_for_admitted_source_on_isolated_sim_clock(monkeypatch):
    import rclpy
    from so101_demo.core.task_geometry import Pose7
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    clock_ns = [0]
    created = {}
    published = []

    class Publisher:
        @staticmethod
        def get_subscription_count():
            return 1

        @staticmethod
        def publish(message):
            published.append((clock_ns[0], message))

    class Node:
        @staticmethod
        def create_publisher(*_args):
            return Publisher()

        @staticmethod
        def get_clock():
            return SimpleNamespace(
                now=lambda: SimpleNamespace(nanoseconds=clock_ns[0])
            )

        @staticmethod
        def destroy_node():
            return None

    def create_node(name, **kwargs):
        created.update(name=name, kwargs=kwargs)
        return Node()

    def spin_once(_node, *, timeout_sec):
        assert 0.0 < timeout_sec <= 0.05
        clock_ns[0] += 40_000_000

    monkeypatch.setattr(rclpy, "ok", lambda: True)
    monkeypatch.setattr(rclpy, "create_node", create_node)
    monkeypatch.setattr(rclpy, "spin_once", spin_once)
    admitted = SimpleNamespace(
        source_stamp_ns=100_000_000,
        pose_world=Pose7((1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0)),
    )
    ports = ParallelRosRuntimePorts(SimpleNamespace(), catalog={})

    assert ports.publish_pose(admitted) is True
    assert created["name"] == "so101_parallel_pose_publisher"
    overrides = created["kwargs"]["parameter_overrides"]
    assert [(parameter.name, parameter.value) for parameter in overrides] == [
        ("use_sim_time", True)
    ]
    assert published[0][0] >= admitted.source_stamp_ns
    message = published[0][1]
    assert (message.header.stamp.sec, message.header.stamp.nanosec) == (0, 100_000_000)
    assert message.header.frame_id == "world"
    assert (
        message.pose.position.x,
        message.pose.position.y,
        message.pose.position.z,
        message.pose.orientation.x,
        message.pose.orientation.y,
        message.pose.orientation.z,
        message.pose.orientation.w,
    ) == admitted.pose_world.values


def test_consumer_readiness_primes_and_retains_isolated_pose_publisher(monkeypatch):
    from so101_demo.core.task_geometry import Pose7
    from so101_demo.runtime import parallel_ros_runtime as runtime_module
    from so101_demo.runtime import task_batch_runtime
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    events = []
    published = []

    class Publisher:
        @staticmethod
        def get_subscription_count():
            return 1

        @staticmethod
        def publish(message):
            published.append(message)

    class Node:
        @staticmethod
        def create_publisher(*_args):
            events.append("publisher-created")
            return Publisher()

        @staticmethod
        def get_node_names_and_namespaces():
            return [
                ("so101_parallel_pose_publisher", "/"),
                ("so101_dynamic_cup_pick_place", "/"),
            ]

        @staticmethod
        def get_clock():
            return SimpleNamespace(
                now=lambda: SimpleNamespace(nanoseconds=200_000_000)
            )

    class Owner:
        node = Node()
        closed = False

        @staticmethod
        def spin_once(*, timeout_sec):
            events.append(("spin", timeout_sec))

        def close(self):
            self.closed = True
            events.append("closed")

    owner = Owner()

    class GraphProbe:
        def __init__(self):
            raise AssertionError("consumer readiness must not shell out to ros2")

    monkeypatch.setattr(task_batch_runtime, "RosGraphProbe", GraphProbe)
    monkeypatch.setattr(
        runtime_module,
        "_open_isolated_ros_node",
        lambda *_args, **_kwargs: owner,
    )
    ports = ParallelRosRuntimePorts(SimpleNamespace(), catalog={})

    assert ports.consumer_ready(SimpleNamespace(pid=os.getpid())) is True
    assert events[0] == "publisher-created"
    admitted = SimpleNamespace(
        source_stamp_ns=100_000_000,
        pose_world=Pose7((1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0)),
    )
    assert ports.publish_pose(admitted) is True
    assert len(published) == 1
    assert owner.closed is False

    ports.close_runtime()
    assert owner.closed is True


def test_pose_publication_fails_closed_when_sim_clock_cannot_reach_source(monkeypatch):
    import rclpy
    from so101_demo.core.task_geometry import Pose7
    from so101_demo.runtime import parallel_ros_runtime as runtime_module
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    monotonic_s = [0.0]
    published = []

    class Publisher:
        @staticmethod
        def get_subscription_count():
            return 1

        @staticmethod
        def publish(message):
            published.append(message)

    class Node:
        @staticmethod
        def create_publisher(*_args):
            return Publisher()

        @staticmethod
        def get_clock():
            return SimpleNamespace(now=lambda: SimpleNamespace(nanoseconds=0))

        @staticmethod
        def destroy_node():
            return None

    def monotonic():
        monotonic_s[0] += 1.0
        return monotonic_s[0]

    monkeypatch.setattr(runtime_module.time, "monotonic", monotonic)
    monkeypatch.setattr(rclpy, "ok", lambda: True)
    monkeypatch.setattr(rclpy, "create_node", lambda *_args, **_kwargs: Node())
    monkeypatch.setattr(rclpy, "spin_once", lambda *_args, **_kwargs: None)
    admitted = SimpleNamespace(
        source_stamp_ns=100_000_000,
        pose_world=Pose7((1.0, 2.0, 3.0, 0.0, 0.0, 0.0, 1.0)),
    )

    assert ParallelRosRuntimePorts(SimpleNamespace(), catalog={}).publish_pose(admitted) is False
    assert published == []


@pytest.mark.parametrize("case", ["empty", "malformed", "wrong_identity"])
def test_exit_zero_unverifiable_dynamic_manifest_never_passes(
        tmp_path, monkeypatch, case):
    from so101_demo.parallel_batch.contracts import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    if case == "empty":
        manifest.write_bytes(b"")
    elif case == "malformed":
        manifest.write_bytes(b"{not-json")
    else:
        document = _dynamic_execute_manifest(
            lease, session_id="session-1", policy_path=policy
        )
        document["parallel_lease_identity"]["attempt_id"] = "stale-attempt"
        manifest.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, 0))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )

    receipt = ports.execute_result(
        lease,
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"


@pytest.mark.parametrize(
    "manifest_status,wait_status,expected_status,expected_reason",
    [
        ("DONE", 0, "PASSED", "OK"),
        ("ERROR", 256, "FAILED", "MOVEIT_EXECUTION_FAILED"),
    ],
)
def test_exact_dynamic_manifest_maps_terminal_business_outcome(
        tmp_path, monkeypatch, manifest_status, wait_status,
        expected_status, expected_reason):
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    manifest.write_text(json.dumps(_dynamic_execute_manifest(
        lease,
        session_id="session-1",
        policy_path=policy,
        status=manifest_status,
    )), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, wait_status))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )

    receipt = ports.execute_result(
        lease,
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status.value == expected_status
    assert receipt.decision.reason == expected_reason


@pytest.mark.parametrize(
    "failure",
    ["GRIPPER_GOAL_TIMEOUT", "GRIPPER_RESULT_TIMEOUT"],
)
def test_post_submission_error_without_controller_settlement_is_indeterminate(
        tmp_path, monkeypatch, failure):
    from so101_demo.parallel_batch.contracts import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest_path = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    document = _dynamic_execute_manifest(
        lease, session_id="session-1", policy_path=policy, status="ERROR"
    )
    terminal = {
        "reset_epoch": 17,
        "simulation_step": 5000,
        "publisher_sequence": 1000,
        "cup_position_world_m": [-0.08, -0.25, 0.1648],
        "cup_orientation_world_xyzw": [0.0, 0.0, 0.0, 1.0],
        "cup_linear_velocity_world_m_s": [0.0, 0.0, 0.0],
        "cup_angular_velocity_world_rad_s": [0.0, 0.0, 0.0],
        "left_contact_count": 0,
        "right_contact_count": 0,
        "maximum_normal_force_n": 0.2,
        "table_contact": True,
    }
    scene = {
        "attached_object_ids": [],
        "world_primitive_counts": {"plastic_cup": 13},
    }
    document.update(
        failure=failure,
        state_trace=["IDLE", "PREPARE_OPEN_GRIPPER", "ERROR"],
        transition_count=2,
        state_events=[{
            "state": "PREPARE_OPEN_GRIPPER",
            "before": {**terminal, "publisher_sequence": 10},
            "after": {**terminal, "publisher_sequence": 11},
            "validation_failure": failure,
        }],
        failure_evidence={
            "failure_boundary_state": "PREPARE_OPEN_GRIPPER",
            "physical_action_proven_absent": False,
            "terminal_sample": terminal,
            "planning_scene_readback": scene,
            "capture_errors": [],
        },
    )
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, 256))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )

    receipt = ports.execute_result(
        lease,
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == f"{failure}:CONTROLLER_OUTCOME_UNCONFIRMED"


def test_runtime_rejects_semantically_impossible_done_trace(tmp_path, monkeypatch):
    from so101_demo.parallel_batch.contracts import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest_path = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    document = _dynamic_execute_manifest(
        lease, session_id="session-1", policy_path=policy
    )
    document["state_trace"] = ["IDLE", "MOVE_ABOVE_OBJECT", "DONE"]
    document["transition_count"] = 2
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, 0))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )

    receipt = ports.execute_result(
        lease,
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"


@pytest.mark.parametrize("corruption", ["producer_target", "zero_quaternion"])
def test_runtime_rejects_untrusted_final_pose_claims(
        tmp_path, monkeypatch, corruption):
    from so101_demo.parallel_batch.contracts import AttemptStatus
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    lease = _lease()
    worker_root = tmp_path / "worker-01"
    manifest_path = (
        worker_root / "attempts" / lease.point_id / lease.attempt_id
        / "working" / "dynamic" / "dynamic-execute-manifest.json"
    )
    manifest_path.parent.mkdir(parents=True)
    policy = tmp_path / "mujoco.yaml"
    policy.write_bytes(b"policy\n")
    document = _dynamic_execute_manifest(
        lease, session_id="session-1", policy_path=policy
    )
    if corruption == "producer_target":
        document["final_samples"][0]["cup_position_world_m"][:2] = [9.0, 9.0]
        validation = next(
            item for item in document["state_events"]
            if item["state"] == "VALIDATE_FINAL_PLACEMENT"
        )
        validation["expected_cup_pose_world"][:2] = [9.0, 9.0]
    else:
        document["final_samples"][0]["cup_orientation_world_xyzw"] = [0.0] * 4
    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    monkeypatch.setattr(os, "waitpid", lambda *_args: (417, 0))
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
        dependencies={
            "dynamic_policy_identity": lambda: (
                str(policy), hashlib.sha256(policy.read_bytes()).hexdigest()
            ),
            "expected_final_cup_pose_world": lambda: EXPECTED_FINAL_CUP_POSE_WORLD,
        },
    )

    receipt = ports.execute_result(
        lease,
        SimpleNamespace(reset_epoch="reset-17"),
        SimpleNamespace(pid=417),
    )

    assert receipt.decision.status is AttemptStatus.INDETERMINATE
    assert receipt.decision.reason == "DYNAMIC_EXECUTION_RECEIPT_UNVERIFIABLE"
