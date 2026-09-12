from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


PACKAGE = Path(__file__).resolve().parents[1]


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
        worker_node_fqns=ParallelRosRuntimePorts.expected_worker_nodes(),
    )
    ports = ParallelRosRuntimePorts.for_test(
        resources=SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        observe_initial=lambda _boundary: observation,
    )
    gate = ports.initial_gate(_lease(), reset)
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


def test_point_reset_uses_qualified_override_and_scene_restore():
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    calls = []
    reset_value = SimpleNamespace(
        simulation_session_id="session-1", new_epoch=9,
    )
    scene = SimpleNamespace(success=True)

    def execute(session_id, *, keyframe, cup_position_world_m):
        calls.append((session_id, keyframe, cup_position_world_m))
        return reset_value, scene

    ports = ParallelRosRuntimePorts(
        SimpleNamespace(session_id="session-1"),
        catalog={"sample": {"cup_position_world_m": [0.1, -0.2, 0.17]}},
        dependencies={
            "execute_reset": execute,
            "current_evidence": lambda _session: SimpleNamespace(
                simulation_session_id="session-1", reset_epoch=9,
                simulation_time_s=4.5,
            )
        },
    )
    receipt = ports.reset_point(SimpleNamespace(point_id="sample", attempt_id="a1"))
    assert calls == [("session-1", "task_start", (0.1, -0.2, 0.17))]
    assert receipt.reset_epoch == "reset-9"
    assert receipt.reset_epoch_value == 9


def test_initial_gate_requires_exact_worker_node_inventory():
    from so101_demo.runtime.parallel_ros_runtime import (
        InitialGateObservation, ParallelRosRuntimePorts, ResetBoundaryReceipt,
    )

    expected = (
        "/move_group", "/mujoco_ros2_control_node", "/robot_state_publisher",
        "/so101_base_to_camera_link", "/so101_camera_link_to_task_camera_frame",
    )
    reset = ResetBoundaryReceipt("reset-2", "session-1", 10.0, 12.0, 2)
    base = dict(
        reset_epoch="reset-2", simulation_session_id="session-1",
        source_frame_monotonic_s=11.0, joint_positions=(0.0,) * 6,
        active_controller_goal_ids=(), moveit_attached_object_ids=(), has_contact=False,
        worker_node_fqns=expected,
    )
    ports = ParallelRosRuntimePorts.for_test(
        resources=SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
        observe_initial=lambda _boundary: InitialGateObservation(**base),
    )
    assert ports.initial_gate(_lease(), reset).no_stale_node is True
    for nodes in (expected[:-1], (*expected, "/stale_worker_generation_0")):
        ports.dependencies["observe_initial"] = lambda _boundary, value=nodes: (
            InitialGateObservation(**{**base, "worker_node_fqns": value})
        )
        with pytest.raises(RuntimeError, match="POINT_INITIAL_GATE"):
            ports.initial_gate(_lease(), reset)


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
    ports._reset_receipts["a"] = object()
    ports._localized["a"] = object()
    ports.rebind_resources(new)
    assert ports.resources is new
    assert ports._rgbd == {}
    assert ports._reset_receipts == {}
    assert ports._localized == {}
    assert closed == ["rgbd"]


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


def test_isolated_ros_node_never_uses_or_shuts_down_the_retained_global_context():
    from so101_demo.runtime.parallel_ros_runtime import _open_isolated_ros_node

    events = []

    class Context:
        def shutdown(self):
            events.append("private-shutdown")

    node = SimpleNamespace(destroy_node=lambda: events.append("node-destroy"))

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
    owner.close()
    owner.close()
    assert events[-2:] == ["node-destroy", "private-shutdown"]
