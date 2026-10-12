"""ACT keeps source/lease identity in memory, separate from the generic file Broker."""

from dataclasses import asdict
import importlib

import numpy as np
import pytest

from so101_demo.parallel_batch.perception import PerceptionError
from test_parallel_batch_perception import harness, pose


def module():
    return importlib.import_module("so101_demo.parallel_batch.act_inference")


def act_request(h):
    values = asdict(h.req)
    for field in ("input_relative_path", "input_sha256", "deadline_s"):
        del values[field]
    values.update(source_stamp_ns=101_000_000_000, source_frame_id="camera_optical",
        image_shape=(2, 3, 3), simulation_session_id="session-1", frame_sequence=1,
        service_generation="teacher-g1", deadline_monotonic_ns=2_000_000_000)
    return module().ActInferenceRequest(**values)


def act_latch(h):
    return module().ActPoseAdmissionLatch(h.workspace, h.context, broker_generation=1,
        clock=lambda: h.control.now, authorize=lambda request: h.control.authorized,
        geometry_gate=lambda request, value: h.control.geometry,
        quality_gate=lambda request, value: h.control.quality)


def test_frame_owns_readonly_original_pixels_without_path_or_transport_hash():
    rgb = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
    frame = module().ActInferenceFrame(rgb8=rgb, source_stamp_monotonic_s=1.0, source_stamp_ns=7,
        source_frame_id="head", simulation_session_id="session", source_clock="ros_sim", sequence=1)
    rgb[:] = 0
    assert frame.rgb8.tobytes() == bytes(range(18))
    assert not frame.rgb8.flags.writeable
    assert not hasattr(frame, "path") and not hasattr(frame, "input_sha256")


def test_act_local_pose_is_durably_admitted_without_any_staging_file(tmp_path):
    h = harness(tmp_path)
    req, latch = act_request(h), act_latch(h)
    values = {name: getattr(pose(h.req), name) for name in asdict(pose(h.req))}
    values["request"] = req
    localized = module().ActLocalizedPose(**values)
    latch.expect(req, depth_timestamp_s=101.0, depth_sha256="b" * 64)
    assert latch.accept(req, localized) is True
    assert latch.accepted is True
    assert (h.workspace.path / "pose_accepted.json").is_file()
    assert not (h.workspace.path / "perception/input").exists()
    assert "input_relative_path" not in asdict(req) and "input_sha256" not in asdict(req)


def test_generic_and_act_latches_each_accept_only_their_current_local_request_type(tmp_path):
    h = harness(tmp_path)
    req, latch = act_request(h), act_latch(h)
    with pytest.raises(PerceptionError, match="REQUEST_IDENTITY_REQUIRED"):
        h.latch.expect(req, depth_timestamp_s=101.0, depth_sha256="b" * 64)
    with pytest.raises(PerceptionError, match="REQUEST_IDENTITY_REQUIRED"):
        latch.expect(h.req, depth_timestamp_s=101.0, depth_sha256="b" * 64)


def test_act_request_cannot_claim_another_session_or_camera(tmp_path):
    from dataclasses import replace
    h = harness(tmp_path)
    req, latch = act_request(h), act_latch(h)
    for bad in (replace(req, simulation_session_id="other"), replace(req, source_frame_id="other")):
        with pytest.raises(PerceptionError, match="INPUT_SOURCE_IDENTITY_MISMATCH"):
            latch.expect(bad, depth_timestamp_s=101.0, depth_sha256="b" * 64)


def test_act_clock_and_image_metadata_cannot_disagree(tmp_path):
    from dataclasses import replace
    h = harness(tmp_path)
    req = act_request(h)
    with pytest.raises(ValueError, match="ACT_INFERENCE_REQUEST_INVALID"):
        replace(req, source_stamp_ns=100_000_000_000)


def test_generic_pose_type_cannot_bypass_act_pose_admission(tmp_path):
    h = harness(tmp_path)
    req, latch = act_request(h), act_latch(h)
    latch.expect(req, depth_timestamp_s=101.0, depth_sha256="b" * 64)
    assert latch.accept(req, pose(h.req)) is False
    assert latch.accepted is False


def test_act_visible_write_failure_preserves_the_existing_adjudication_fence(tmp_path, monkeypatch):
    h = harness(tmp_path)
    req, latch = act_request(h), act_latch(h)
    values = {name: getattr(pose(h.req), name) for name in asdict(pose(h.req))}
    values["request"] = req
    localized = module().ActLocalizedPose(**values)
    latch.expect(req, depth_timestamp_s=101.0, depth_sha256="b" * 64)
    original = h.workspace.write_json
    def broken(path, document):
        original(path, document)
        raise OSError("partial durable write")
    monkeypatch.setattr(h.workspace, "write_json", broken)
    with pytest.raises(OSError):
        latch.accept(req, localized)
    assert latch.requires_adjudication and not latch.accepted
