"""ACT memory capture and actual RGB-D/cup geometry/admission production ports."""

import importlib
import json
from dataclasses import replace
from types import SimpleNamespace as NS

import numpy as np
import pytest


def header(stamp=12_000_000_000):
    return NS(stamp=NS(sec=stamp // 10**9, nanosec=stamp % 10**9), frame_id="camera_optical")


def cylinder(*, radius=0.04, height=0.09):
    """Raycast a cup wall; all backprojection, cleanup and circle fitting remain real."""
    width, rows, focal = 160, 120, 400.0
    v, u = np.mgrid[:rows, :width]
    a, b = (u - 80) / focal, (v - 60) / focal
    aa = a*a + 1
    bb = -2*(a*0.02 + 0.52)
    cc = 0.02**2 + 0.52**2 - radius**2
    disc = bb*bb - 4*aa*cc
    depth = (-bb - np.sqrt(np.maximum(disc, 0))) / (2*aa)
    z = 0.17 - b*depth
    mask = (disc > 0) & (z >= 0.12) & (z <= 0.12 + height)
    values = np.where(mask, depth, 0).astype("<f4")
    camera = NS(header=header(), width=width, height=rows,
                k=[focal, 0., 80., 0., focal, 60., 0., 0., 1.])
    message = NS(header=header(), width=width, height=rows, encoding="32FC1", step=width*4,
                 is_bigendian=False, data=values.tobytes())
    transform = NS(transform=NS(translation=NS(x=0., y=-0.8, z=0.17),
        rotation=NS(x=-np.sqrt(0.5), y=0., z=0., w=np.sqrt(0.5))))
    return mask, camera, message, transform


def build_case(tmp_path, *, radius=0.04, height=0.09):
    from so101_demo.parallel_batch.artifacts import AttemptWorkspace
    from so101_demo.parallel_batch.contracts.common import ExecutionKind, RunMode
    from so101_demo.parallel_batch.contracts.identity import AttemptIdentity, LeaseIdentity
    from so101_demo.runtime.parallel_ros_ports.observations import ResetBoundaryReceipt
    module = importlib.import_module("so101_demo.runtime.act_ros_runtime")
    identity = dict(batch_id="batch", coordinator_epoch=1, worker_id="worker", worker_generation=1,
                    point_id="point", attempt_id="attempt", lease_generation=1)
    lease = LeaseIdentity(**identity, lease_issued_monotonic_s=1., lease_deadline_monotonic_s=100.)
    workspace = AttemptWorkspace.create(tmp_path / "workers/worker", AttemptIdentity(**identity),
        reset_epoch="reset-2", source_stamp={"simulation_time_s": 10.0}, run_mode=RunMode.EXECUTE)
    mask, camera, depth, transform = cylinder(radius=radius, height=height)
    calls, closed = [], []
    source = NS(lookup_exact=lambda *args: calls.append(args) or transform,
                close=lambda: closed.append(True))
    ports = module.ActRosRuntimePorts(NS(session_id="session", worker_id="worker", generation=1),
        catalog={}, config=NS(yolo_model_id="cup-model", max_frame_age_s=1., max_rgbd_skew_s=0.05,
                              max_tf_skew_s=0.05), broker_generation=1,
        dependencies={"workspace_provider": lambda _lease: workspace, "authorize": lambda _req: True,
          "source_clock": lambda _reset: 12.0, "dynamic_template": lambda: NS(
              workspace_bounds_m=(-0.2, -0.5, 0.1, 0.2, -0.1, 0.3))})
    ports._reset_receipts["attempt"] = ResetBoundaryReceipt("reset-2", "session", 1., 10.)
    ports._rgbd[12_000_000_000] = (source, camera, depth, "camera_optical")
    local = importlib.import_module("so101_demo.parallel_batch.act_inference")
    frame = local.ActInferenceFrame(np.zeros((120, 160, 3), dtype=np.uint8), 2., 12_000_000_000,
                                    "camera_optical", "session", "ros_sim", 1)
    request = local.ActInferenceRequest(**identity, request_id="r1", model_id="cup-model",
        reset_epoch="reset-2", image_timestamp_s=12., execution_kind=ExecutionKind.ATTEMPT,
        source_stamp_ns=frame.source_stamp_ns, source_frame_id=frame.source_frame_id,
        image_shape=frame.shape, simulation_session_id="session", frame_sequence=1,
        service_generation="teacher-g1", deadline_monotonic_ns=10**18)
    flat = mask.ravel()
    edges = np.flatnonzero(flat[1:] != flat[:-1]) + 1
    counts = np.diff(np.r_[0, edges, len(flat)]).tolist()
    if flat[0]:
        counts.insert(0, 0)
    batch = {"model_id": request.model_id, "weights_sha256": "a"*64, "runtime_device": "cuda",
        "inference_latency_ms": 1., "shape": list(frame.shape), "source_stamp_ns": frame.source_stamp_ns,
        "source_frame_id": frame.source_frame_id, "candidates": [{"instance_id": "cup", "class_id": "plastic_cup",
            "confidence": 0.9, "bbox_xyxy": [0., 0., 160., 120.], "segmentation_quality": 0.9,
            "mask_rle": {"shape": [120, 160], "counts": counts}}]}
    wire = {"schema_version": 1, "kind": "inference_response", "request_id": "r1",
        "service_generation": "teacher-g1", "source_stamp_ns": frame.source_stamp_ns,
        "source_frame_id": frame.source_frame_id, "outcome": "DETECTED", "reason": "",
        "batch": batch, "timing": dict(received_monotonic_ns=1, queued_monotonic_ns=2,
                                      started_monotonic_ns=3, completed_monotonic_ns=4)}
    result = local.ActInferenceResult(request, 1, wire, 1, 5)
    return NS(ports=ports, lease=lease, workspace=workspace, frame=frame, request=request,
              result=result, wire=wire, calls=calls, closed=closed, source=source,
              camera=camera, depth=depth)


def run(h):
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    calls = []
    def infer(model_id, *, before_send):
        calls.append(model_id)
        before_send(h.request)
        return h.result
    result = h.ports.run_perception_chain(h.lease, ExecutionKind.ATTEMPT, h.frame, infer)
    assert calls == ["cup-model"]
    return result


def test_real_cup_geometry_and_durable_admission_accept_cup_without_staging_file(tmp_path):
    from so101_demo.runtime.parallel_ros_ports.observations import AdmittedPose
    h = build_case(tmp_path)
    value = run(h)
    assert type(value) is AdmittedPose
    np.testing.assert_allclose(value.localized.position_xyz, (0.02, -0.28, 0.165), atol=0.001)
    assert h.calls == [("world", "camera_optical", 12_000_000_000, 5.0)]
    assert not h.closed  # source retained for Teacher execution
    document = json.loads((h.workspace.path / "pose_accepted.json").read_text())
    assert "input_relative_path" not in document["request"]
    assert not (h.workspace.path / "perception/input").exists()
    audit = json.loads((h.workspace.path / "perception/inference/r1.json").read_text())
    assert audit["response"] == h.wire
    assert audit["request"]["frame_sequence"] == 1


@pytest.mark.parametrize("changes", [{"radius": 0.07}, {"height": 0.02}])
def test_real_cup_geometry_rejection_is_failed_and_never_selects_grounded(tmp_path, changes):
    h = build_case(tmp_path, **changes)
    value = run(h)
    assert (value.disposition, value.reason) == ("FAILED", "PERCEPTION_NO_POSE")
    assert h.closed == [True]
    assert not (h.workspace.path / "pose_accepted.json").exists()


@pytest.mark.parametrize("outcome, disposition", [("NOT_DETECTED", "FAILED"), ("INPUT_INVALID", "INVALID"),
    ("QUEUE_FULL", "INVALID"), ("QUEUE_TIMEOUT", "INVALID"), ("INFERENCE_TIMEOUT", "INVALID"),
    ("MODEL_ERROR", "FAILED"), ("INFRA_ERROR", "INVALID")])
def test_production_act_ports_preserve_wire_failure_and_local_terminal(tmp_path, outcome, disposition):
    h = build_case(tmp_path)
    local = importlib.import_module("so101_demo.parallel_batch.act_inference")
    h.result = local.ActInferenceResult(h.request, 1, h.wire | {
        "outcome": outcome, "batch": None, "reason": "original-service-reason"}, 1, 5)
    value = run(h)
    assert value.disposition == disposition
    assert value.failure_type == f"ActInferenceResponse.{outcome}"
    assert value.failure_message == "original-service-reason"
    assert not h.calls and h.closed == [True]


def test_act_memory_capture_keeps_original_pixels_and_owns_aligned_source(tmp_path):
    h = build_case(tmp_path)
    h.ports._rgbd.clear()
    pixels = np.arange(120*160*3, dtype=np.uint8).reshape(120, 160, 3)
    color = NS(header=header(), width=160, height=120, encoding="rgb8", step=160*3,
               is_bigendian=False, data=pixels.tobytes())
    h.ports._capture_aligned = lambda: (h.source, (h.camera, color, h.depth), 2.)
    value = h.ports.capture_act_frame(h.lease, 1.)
    assert value.rgb8.tobytes() == pixels.tobytes()
    assert value.source_clock == "ros_sim" and value.simulation_session_id == "session"
    assert value.sequence == 1 and not value.rgb8.flags.writeable
    assert h.ports._rgbd[value.source_stamp_ns][0] is h.source and not h.closed
    assert list(tmp_path.rglob("*.npy")) == []
    assert list(tmp_path.rglob("broker-inputs")) == []


def test_act_capture_refuses_old_frame_and_closes_source(tmp_path):
    h = build_case(tmp_path)
    color = NS(header=header(), width=160, height=120, encoding="rgb8", step=160*3,
               is_bigendian=False, data=h.frame.rgb8.tobytes())
    h.ports._capture_aligned = lambda: (h.source, (h.camera, color, h.depth), 2.)
    with pytest.raises(RuntimeError, match="RGB_SOURCE_NOT_FRESH"):
        h.ports.capture_act_frame(h.lease, 2.)
    assert h.closed == [True]


def test_failed_aligned_acquisition_closes_owned_rgbd_source(tmp_path):
    h = build_case(tmp_path)
    def fail(_timeout):
        raise TimeoutError("camera unavailable")
    h.source.capture = fail
    h.ports.dependencies["rgbd_source"] = lambda: h.source
    with pytest.raises(TimeoutError, match="camera unavailable"):
        h.ports.capture_act_frame(h.lease, 1.)
    assert h.closed == [True]


def test_consumer_watermark_refusal_is_bounded_and_closes_each_source(tmp_path):
    h = build_case(tmp_path)
    h.ports._minimum_inference_stamp_ns = 13_000_000_000
    color = NS(header=header(), width=160, height=120, encoding="rgb8", step=160*3,
               is_bigendian=False, data=h.frame.rgb8.tobytes())
    h.ports._capture_aligned = lambda: (h.source, (h.camera, color, h.depth), 2.)
    with pytest.raises(RuntimeError, match="RGB_SOURCE_PREDATES_CONSUMER_READY"):
        h.ports.capture_act_frame(h.lease, 1.)
    assert h.closed == [True]*5


def test_next_reset_releases_previous_act_rgbd_and_local_candidate_memory(tmp_path):
    h = build_case(tmp_path)
    run(h)
    assert not h.ports._admission_candidates
    h.ports.catalog["point"] = {}
    h.ports.dependencies["reset_point"] = lambda *_args: NS(simulation_session_id="session", new_epoch=3)
    h.ports.dependencies["current_evidence"] = lambda _session: NS(
        simulation_session_id="session", reset_epoch=3, simulation_time_s=13.)
    h.ports.reset_point(h.lease)
    assert h.closed == [True]
    assert not h.ports._rgbd and not h.ports._localized and not h.ports._admitted


@pytest.mark.parametrize("field, value", [("frame_sequence", 2), ("image_shape", (2, 3, 3)),
    ("source_frame_id", "other"), ("simulation_session_id", "other")])
def test_act_ports_refuse_request_for_another_memory_capture(tmp_path, field, value):
    h = build_case(tmp_path)
    h.request = replace(h.request, **{field: value})
    with pytest.raises(RuntimeError, match="ACT_REQUEST_CAPTURE_IDENTITY"):
        run(h)
    assert not h.calls and not (h.workspace.path / "pose_accepted.json").exists()


@pytest.mark.parametrize("generation_changed", [False, True])
def test_cancelled_result_does_not_enter_cup_geometry_or_publish_pose(tmp_path, generation_changed):
    h = build_case(tmp_path)
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    # Authorization is bound before the request starts, so use a mutable external authority.
    authority = NS(current=True)
    h.ports.dependencies["authorize"] = lambda _req: authority.current
    def cancelled(_model, *, before_send):
        before_send(h.request)
        authority.current = generation_changed
        return replace(h.result, broker_generation=2) if generation_changed else h.result
    value = h.ports.run_perception_chain(h.lease, ExecutionKind.ATTEMPT, h.frame, cancelled)
    assert value.disposition == "CANCELLED"
    assert not h.calls and h.closed == [True]
    assert not (h.workspace.path / "pose_accepted.json").exists()


def test_real_unix_teacher_adapter_to_actual_cup_geometry_and_durable_admission(tmp_path):
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    from so101_demo.runtime.act_teacher_client import ActTeacherClient
    from so101_demo.runtime.inference.client import InferenceClient
    from so101_demo.runtime.inference.service import InferenceUnixServer
    from so101_demo.runtime.parallel_ros_ports.observations import AdmittedPose
    from test_service import service_fixture
    h = build_case(tmp_path)
    service, _gates, _started, calls, executors = service_fixture(tmp_path)
    executors[0].batch = h.wire["batch"]
    server = InferenceUnixServer(service=service, socket_path=tmp_path / "teacher.sock", receive_budget_s=0.5)
    try:
        server.start()
        client = InferenceClient(socket_path=tmp_path / "teacher.sock", service_generation="g1", max_frame_bytes=2**20)
        expected = {field: getattr(h.lease, field) for field in (
            "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
            "point_id", "attempt_id", "lease_generation")}
        expected.update(reset_epoch="reset-2", session_id="session")
        owner = ActTeacherClient(client=client, resources=h.ports.resources, model_id="cup-model",
            weights_sha256="a"*64, classes={"0": "plastic_cup"}, query_class_id="plastic_cup",
            launch_generation=1, request_budget_s=1., context_probe=lambda *_args: expected,
            perception_runner=h.ports.run_perception_chain)
        value = owner.request_model(h.lease, ExecutionKind.ATTEMPT, snapshot=h.frame,
            reset_epoch="reset-2", start_event_id="attempt-start-attempt", start_event_type="ATTEMPT_STARTED")
        assert type(value) is AdmittedPose
        assert len(calls) == 1 and calls[0][2] == h.frame.rgb8.tobytes()
        document = json.loads((h.workspace.path / "pose_accepted.json").read_text())
        assert document["request"]["service_generation"] == "g1"
        assert not list(tmp_path.rglob("*.npy"))
    finally:
        server.close()
        service.close()
