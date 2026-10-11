"""Candidate filtering, localisation, the port factory, pause control, recovery and point capture."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from types import SimpleNamespace

import numpy as np
from parallel_ros_runtime_support import PACKAGE, _lease, _valid_worker_nodes
import pytest


def _broker_response(masks):
    """A qualified Broker response with one candidate per entry of `masks` (a 2x3 list of lists of 0/1), ids cand-0, cand-1, ..."""
    from so101_demo.parallel_batch.broker import BrokerResponse
    from so101_demo.parallel_batch.contracts.common import ExecutionKind, ModelOutcome
    from so101_demo.parallel_batch.contracts.identity import InferenceRequest

    request = InferenceRequest(
        request_id="attempt-1-yolo", model_id="plastic-cup-yolo11n-seg-v1", execution_kind=ExecutionKind.ATTEMPT,
        batch_id="batch-1", coordinator_epoch=1, worker_id="worker-01", worker_generation=1, point_id="task_start",
        lease_generation=1, reset_epoch="reset-2", image_timestamp_s=12.0,
        input_relative_path="worker-01/attempts/task_start/attempt-1/working/perception/input/rgb.npy",
        input_sha256="ab" * 32, deadline_s=5.0, attempt_id="attempt-1")

    def rle(mask):
        flat = [int(v) for row in mask for v in row]
        counts, current, run = [], 0, 0
        for value in flat:
            if value == current:
                run += 1
            else:
                counts.append(run)
                current, run = value, 1
        counts.append(run)
        return {"shape": [2, 3], "counts": counts}

    document = {
        "model_id": "plastic-cup-yolo11n-seg-v1", "weights_sha256": "ab" * 32, "runtime_device": "cuda",
        "inference_latency_ms": 1.0, "shape": [2, 3, 3], "source_stamp_ns": 12_000_000_000,
        "source_frame_id": "task_camera_frame",
        "candidates": [{"instance_id": f"cand-{index}", "class_id": "plastic_cup", "confidence": 0.9 - 0.1 * index,
                        "bbox_xyxy": [0.0, 0.0, 3.0, 2.0], "segmentation_quality": 0.95, "mask_rle": rle(mask)}
                       for index, mask in enumerate(masks)]}
    return BrokerResponse(request, 1, ModelOutcome.QUALIFIED, document, None, 1.0, 2.0, 1.1, 2.1, 1.2)


class _ByInstance:
    """A localizer whose verdict per candidate is given: a z-extent (metres), or an exception to raise."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = outcomes, []

    def localize(self, candidate, camera_info, depth_message, lookup):
        self.calls.append((candidate.instance_id, camera_info, depth_message, lookup("world", "f", 1)))
        outcome = self.outcomes[candidate.instance_id]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(instance_id=candidate.instance_id, center_world_xyz=(0.02, -0.28, 0.165),
                               points_world=np.array([[0.0, 0.0, 0.12], [0.0, 0.0, 0.12 + outcome]]))


def _ring_candidate_localizer(outcomes, masks=None):
    from so101_demo.runtime.parallel_ros_ports.observations import BrokerMaskLocalizer

    masks = masks or [[[0, 1, 1], [0, 0, 1]]] * len(outcomes)
    localizer = _ByInstance(outcomes)
    return localizer, lambda: BrokerMaskLocalizer(localizer=localizer).localize(
        _broker_response(masks), camera_info="camera", depth_message="depth", lookup_exact=lambda *a: a)


def test_keeps_the_cup_and_drops_a_flat_ring_candidate():
    localizer, call = _ring_candidate_localizer({"cand-0": 0.003, "cand-1": 0.09})      # the ring is the first (higher confidence) candidate
    assert call().instance_id == "cand-1"
    assert [c[0] for c in localizer.calls] == ["cand-0", "cand-1"], "every candidate is localized"
    assert all(c[1:3] == ("camera", "depth") for c in localizer.calls), "each against the same exact depth and TF"


def test_drops_a_candidate_whose_circle_fit_is_rejected():
    from so101_demo.application.object_pose import LocalizationError

    _, call = _ring_candidate_localizer({"cand-0": 0.09, "cand-1": LocalizationError("GEOMETRY_REJECTED", "radius 0.07 outside 0.04 +- 0.01")})
    assert call().instance_id == "cand-0"
    _, call = _ring_candidate_localizer({"cand-0": 0.09, "cand-1": LocalizationError("DEPTH_INVALID", "30 valid points")})
    assert call().instance_id == "cand-0"


def test_two_cups_are_ambiguous_and_the_message_names_the_count():
    _, call = _ring_candidate_localizer({"cand-0": 0.09, "cand-1": 0.08})
    with pytest.raises(RuntimeError, match=r"BROKER_CANDIDATE_AMBIGUOUS: 2 of 2"):
        call()


def test_with_no_cup_among_several_candidates_is_a_geometry_rejection_so_the_policy_tries_its_next_model():
    from so101_demo.application.object_pose import LocalizationError

    _, call = _ring_candidate_localizer({"cand-0": 0.003, "cand-1": 0.004})
    with pytest.raises(LocalizationError, match=r"GEOMETRY_REJECTED: no candidate is a cup \(0 of 2\)") as error:
        call()
    assert error.value.code == "GEOMETRY_REJECTED"


def test_a_lone_flat_candidate_is_not_a_cup_and_a_lone_failure_keeps_its_own_error():
    from so101_demo.application.object_pose import LocalizationError

    _, call = _ring_candidate_localizer({"cand-0": 0.003})
    with pytest.raises(LocalizationError, match="no candidate is a cup"):
        call()
    _, call = _ring_candidate_localizer({"cand-0": LocalizationError("DEPTH_INVALID", "30 valid points")})
    with pytest.raises(LocalizationError, match="DEPTH_INVALID: 30 valid points"):
        call()


def test_a_failure_of_the_shared_inputs_is_no_verdict_on_a_candidate():
    from so101_demo.application.object_pose import LocalizationError

    _, call = _ring_candidate_localizer({"cand-0": 0.09, "cand-1": LocalizationError("TF_UNAVAILABLE", "no transform")})
    with pytest.raises(LocalizationError, match="TF_UNAVAILABLE"):
        call()


def test_the_survivors_pose_is_the_localizers_result_for_its_mask_unchanged():
    localizer, call = _ring_candidate_localizer({"cand-0": 0.003, "cand-1": 0.09})
    assert call().center_world_xyz == (0.02, -0.28, 0.165)


def test_a_qualified_response_without_candidates_is_still_ambiguous():
    from so101_demo.runtime.parallel_ros_ports.observations import BrokerMaskLocalizer

    response = _broker_response([[[1, 0, 0], [0, 0, 0]]])
    response.candidate["candidates"].clear()
    with pytest.raises(RuntimeError, match="BROKER_CANDIDATE_AMBIGUOUS"):
        BrokerMaskLocalizer(localizer=_ByInstance({})).localize(response, camera_info=None, depth_message=None,
                                                                lookup_exact=lambda *a: a)


def test_localization_allows_bounded_fresh_stack_tf_discovery(monkeypatch):
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    from so101_demo.parallel_batch.contracts.identity import InferenceRequest
    from so101_demo.runtime.parallel_ros_ports import perception as runtime_module_perception
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

    monkeypatch.setattr(runtime_module_perception, "BrokerMaskLocalizer", lambda: Localizer())
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
        deadline_s=5.0,
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


def test_production_port_factory_binds_every_production_port_without_empty_side_effects():
    from so101_demo.cli.mujoco_batch.worker_process import RosWorkerRuntimePorts

    ports = RosWorkerRuntimePorts(
        SimpleNamespace(session_id="session-1"),
        catalog={"task_start": {"cup_position_world_m": [0.02, -0.28, 0.165]}},
    ).kwargs()
    assert set(ports) == RosWorkerRuntimePorts.REQUIRED
    assert all(callable(value) for value in ports.values())
    assert all("RUNTIME_PORT_NOT_READY" not in repr(value) for value in ports.values())


def test_pause_control_is_retained_across_point_freeze_and_resume() -> None:
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    events = []

    class Control:
        def set_paused(self, paused):
            events.append(("set-paused", paused))
            return True

        def close(self):
            events.append(("close",))

    control = Control()
    resources = SimpleNamespace(
        worker_id="worker-01", generation=1, session_id="session-1"
    )
    ports = ParallelRosRuntimePorts(
        resources,
        catalog={},
        dependencies={"pause_control_factory": lambda: control},
    )
    lease = _lease()
    reset = ResetBoundaryReceipt("reset-2", "session-1", 10.0, 12.0, 2)

    assert ports.resume_physics(lease, reset) is True
    assert ports.pause_physics(lease, reset) is True
    assert ports.resume_physics(lease, reset) is True
    ports.close_runtime()

    assert events == [
        ("set-paused", False),
        ("set-paused", True),
        ("set-paused", False),
        ("close",),
    ]


def test_recovery_requires_observed_child_and_ros_graph_absence():
    from so101_demo.runtime.parallel_ros_ports.observations import ShutdownObservation
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

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
    from so101_demo.parallel_batch.contracts.linux_cuda import (
        load_parallel_runtime_config_linux_cuda,
    )

    template = load_dynamic_policy_variant(PACKAGE, backend="mujoco").template
    config = load_parallel_runtime_config_linux_cuda(
        PACKAGE / "config/mujoco/parallel_batch_linux_cuda.yaml"
    )
    assert config.max_frame_age_s == template.maximum_source_age_s == 5.0
    assert config.max_rgbd_skew_s == 0.0
    assert config.max_tf_skew_s == 0.0
    lower, upper = template.workspace_bounds_m[:3], template.workspace_bounds_m[3:]
    assert all(minimum < maximum for minimum, maximum in zip(lower, upper, strict=True))


@pytest.mark.parametrize("source_now,accepted", [(12.0, True), (1000.0, False)])
def test_model_policy_persists_admission_and_rejects_mixed_source_clock(
    tmp_path, source_now, accepted
):
    from so101_demo.parallel_batch.artifacts import ValidationWorkspace
    from so101_demo.parallel_batch.broker import BrokerResponse
    from so101_demo.parallel_batch.contracts.common import ExecutionKind, ModelOutcome, RunMode
    from so101_demo.parallel_batch.contracts.identity import InferenceRequest, ValidationIdentity
    from so101_demo.parallel_batch.contracts.linux_cuda import (
        load_parallel_runtime_config_linux_cuda,
    )
    from so101_demo.parallel_batch.perception import LocalizedPose, PerceptionError
    from so101_demo.runtime.parallel_ros_ports.observations import (
        AdmittedPose,
        ResetBoundaryReceipt,
    )
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts
    from so101_demo.runtime.parallel_worker_parts.receipts import InferenceSnapshotReceipt

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
    config = load_parallel_runtime_config_linux_cuda(
        PACKAGE / "config/mujoco/parallel_batch_linux_cuda.yaml"
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
            input_sha256=snapshot.input_sha256, deadline_s=5.0,
            validation_id="attempt-1",
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
    from so101_demo.parallel_batch.contracts.common import ExecutionKind, ModelOutcome, RunMode
    from so101_demo.parallel_batch.contracts.identity import InferenceRequest, ValidationIdentity
    from so101_demo.parallel_batch.contracts.linux_cuda import (
        load_parallel_runtime_config_linux_cuda,
    )
    from so101_demo.runtime.parallel_ros_ports.observations import (
        PerceptionTerminal,
        ResetBoundaryReceipt,
    )
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts
    from so101_demo.runtime.parallel_worker_parts.receipts import InferenceSnapshotReceipt

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
    config = load_parallel_runtime_config_linux_cuda(
        PACKAGE / "config/mujoco/parallel_batch_linux_cuda.yaml"
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
            input_sha256=snapshot.input_sha256, deadline_s=5.0,
            validation_id="attempt-1",
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


def test_inference_capture_retries_frame_older_than_child_ready_fence(
    tmp_path, monkeypatch
):
    from so101_demo.cli import rgbd_point_cloud
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

    worker_root = tmp_path / "workers/worker-01"
    worker_root.mkdir(parents=True, mode=0o700)
    (tmp_path / "broker-inputs").mkdir(mode=0o700)
    closed = []

    def sample(stamp_ns):
        source = SimpleNamespace(close=lambda: closed.append(stamp_ns))
        color = SimpleNamespace(
            header=SimpleNamespace(
                frame_id="task_camera_frame",
                stamp=SimpleNamespace(
                    sec=stamp_ns // 1_000_000_000,
                    nanosec=stamp_ns % 1_000_000_000,
                ),
            )
        )
        return source, (object(), color, object()), 11.0

    captures = [sample(100), sample(200)]
    ports = ParallelRosRuntimePorts(
        SimpleNamespace(worker_root=worker_root, session_id="session-1"),
        catalog={},
    )
    ports._minimum_inference_stamp_ns = 200
    ports._capture_aligned = lambda: captures.pop(0)
    monkeypatch.setattr(
        rgbd_point_cloud,
        "_decode_rgb",
        lambda _message: np.zeros((2, 3, 3), dtype=np.uint8),
    )
    destination = (
        worker_root
        / "attempts/task_start/attempt-1/working/perception/input/rgb.npy"
    )

    receipt = ports.capture_rgb(destination, 10.0)

    assert receipt.source_stamp_ns == 200
    assert closed == [100]
    assert ports._minimum_inference_stamp_ns is None
    ports.close_runtime()
    assert closed == [100, 200]


def test_initial_gate_requires_exact_worker_node_inventory():
    from so101_demo.runtime.parallel_ros_ports.observations import (
        InitialGateObservation,
        ResetBoundaryReceipt,
    )
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

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
    from so101_demo.parallel_batch.worker_parts.contracts import _bounded_failure_message
    from so101_demo.runtime.parallel_ros_ports.observations import (
        InitialGateObservation,
        ResetBoundaryReceipt,
    )
    from so101_demo.runtime.parallel_ros_runtime import ParallelRosRuntimePorts

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
