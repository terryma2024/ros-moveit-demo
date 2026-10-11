"""Dynamic manifest policy, localisation failures, rebinding, shutdown and goal checks."""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

from parallel_ros_runtime_support import PACKAGE, _lease
import pytest


def test_localization_infrastructure_failure_never_triggers_fallback(tmp_path):
    from so101_demo.application.object_pose import LocalizationError
    from so101_demo.parallel_batch.artifacts import ValidationWorkspace
    from so101_demo.parallel_batch.broker import BrokerResponse
    from so101_demo.parallel_batch.contracts.common import ExecutionKind, ModelOutcome, RunMode
    from so101_demo.parallel_batch.contracts.identity import ValidationIdentity
    from so101_demo.parallel_batch.contracts.linux_cuda import (
        load_parallel_runtime_config_linux_cuda,
    )
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts
    from so101_demo.runtime.parallel_worker_parts.receipts import InferenceSnapshotReceipt

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
        config=load_parallel_runtime_config_linux_cuda(PACKAGE / "config/mujoco/parallel_batch_linux_cuda.yaml"),
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
        from so101_demo.parallel_batch.contracts.identity import InferenceRequest
        request = InferenceRequest(
            request_id=f"attempt-1-{model_id}", model_id=model_id,
            execution_kind=ExecutionKind.VALIDATION, batch_id="batch-1",
            coordinator_epoch=1, worker_id="worker-01", worker_generation=1,
            point_id="task_start", lease_generation=1, reset_epoch="reset-2",
            image_timestamp_s=12.0,
            input_relative_path="worker-01/validations/task_start/attempt-1/working/perception/input/rgb.npy",
            input_sha256=snapshot.input_sha256, deadline_s=5.0,
            validation_id="attempt-1",
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
    from so101_demo.runtime.parallel_ros_ports import recovery as ros_runtime_recovery
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    events = []
    monkeypatch.setattr(
        ros_runtime_recovery,
        "cancel_and_confirm_parallel_goals",
        lambda *, timeout_s: events.append(("cancel", timeout_s)) or True,
    )
    monkeypatch.setattr(
        ros_runtime_recovery,
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
    from rclpy.qos import qos_profile_action_status_default

    from so101_demo.runtime.parallel_ros_ports import observations as ros_runtime_observations
    from so101_demo.runtime.parallel_ros_ports import perception as ros_runtime_perception

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
        ros_runtime_observations, "_open_isolated_ros_node", lambda *_args, **_kwargs: Owner()
    )
    monkeypatch.setattr(
        ros_runtime_perception, "_open_isolated_ros_node", lambda *_args, **_kwargs: Owner()
    )

    assert ros_runtime_observations.cancel_and_confirm_parallel_goals(timeout_s=1.0) is True
    assert ros_runtime_observations.observe_no_parallel_goals(timeout_s=1.0) is True
    assert captured_qos == [qos_profile_action_status_default] * 6
