"""The Teleop head camera consumes the closed connection and constructs no detector."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from so101_teleop.head_camera import (
    CONNECTION_ENV,
    RUNTIME_ID_ENV,
    SOCKET_DIR_ENV,
    CompositionBlocked,
    compose_head_camera,
    load_descriptor,
)


def valid_descriptor(tmp_path: Path) -> dict:
    return {
        "operation": "TELEOP_ACCEPTANCE",
        "runtime_id": "runtime-0001",
        "head_search_runtime_id": "runtime-0001",
        "model_id": "head-search-v2",
        "bundle_sha256": "a" * 64,
        "simulation_session_id": "session-0001",
        "execution_generation": 1,
        "owner": {"pid": 4242, "started_ticks": 900000},
        "bridge_socket_root": str(tmp_path),
    }


def environment_for(tmp_path: Path, descriptor: dict, *, socket_root=None, runtime_id=None) -> dict:
    path = tmp_path / "head-camera-connection.json"
    path.write_text(json.dumps(descriptor), encoding="utf-8")
    return {
        CONNECTION_ENV: str(path),
        SOCKET_DIR_ENV: str(socket_root if socket_root is not None else tmp_path),
        RUNTIME_ID_ENV: runtime_id or descriptor["runtime_id"],
    }


def test_head_camera_stream_uses_composed_detector_identity(tmp_path: Path) -> None:
    descriptor = valid_descriptor(tmp_path)
    services = compose_head_camera(environment_for(tmp_path, descriptor))
    detector = object()
    services.detector = detector

    envelope = services.publish_once(jpeg=b"frame", detections=({"class_id": 0},))

    assert envelope.model_id == descriptor["model_id"]
    assert services.detector_factory_calls == 0, "the backend must not construct a detector"
    assert services.status()["detector_constructed"] == 0


def test_out_of_range_target_is_refused_before_submit(tmp_path: Path) -> None:
    descriptor = valid_descriptor(tmp_path)
    services = compose_head_camera(environment_for(tmp_path, descriptor))
    with pytest.raises(ValueError, match="HEAD_TARGET_OUT_OF_RANGE"):
        services.submit_target(target_rad=99.0, safe_interval_rad=(-1.0, 1.0))
    assert services.submit_target(target_rad=0.5, safe_interval_rad=(-1.0, 1.0))["status"] == "SUBMITTED"


def test_composition_rejects_connection_descriptor_owner_or_socket_drift(tmp_path: Path) -> None:
    descriptor = valid_descriptor(tmp_path)
    with pytest.raises(CompositionBlocked, match="HEAD_CAMERA_CONNECTION_MISMATCH"):
        compose_head_camera(
            environment_for(tmp_path, descriptor, socket_root=tmp_path / "other")
        )
    with pytest.raises(CompositionBlocked, match="HEAD_CAMERA_CONNECTION_MISMATCH"):
        compose_head_camera(environment_for(tmp_path, descriptor, runtime_id="other-runtime"))
    missing = environment_for(tmp_path, descriptor)
    Path(missing[CONNECTION_ENV]).unlink()
    with pytest.raises(Exception, match="HEAD_CAMERA_UNAVAILABLE"):
        load_descriptor(missing)


def test_bridge_child_consumes_exact_head_runtime_authority(tmp_path: Path) -> None:
    descriptor = valid_descriptor(tmp_path)
    services = compose_head_camera(environment_for(tmp_path, descriptor))
    assert services.runtime_owner == descriptor["owner"]
    assert services.simulation_session_id == descriptor["simulation_session_id"]
    assert services.execution_generation == descriptor["execution_generation"]


def test_stop_needs_three_consecutive_raw_samples(tmp_path: Path) -> None:
    descriptor = valid_descriptor(tmp_path)
    services = compose_head_camera(environment_for(tmp_path, descriptor))
    assert services.stop()["state"] == "STOPPING"
    assert services.stop()["state"] == "STOPPING"
    assert services.stop()["state"] == "STOPPED"
    assert services.stop(raw_sample_ok=False)["state"] == "STOPPING", "a gap restarts the proof"
    assert services.stop()["consecutive_samples"] == 1


def test_capture_is_atomic_and_refuses_stale_or_mismatched_frames(tmp_path: Path) -> None:
    descriptor = valid_descriptor(tmp_path)
    services = compose_head_camera(environment_for(tmp_path, descriptor))
    with pytest.raises(ValueError, match="HEAD_CAPTURE_NO_FRAME"):
        services.capture()

    services.publish_once(jpeg=b"frame")
    assert services.capture()["sequence"] == 1
    with pytest.raises(ValueError, match="HEAD_CAPTURE_STALE_FRAME"):
        services.capture(now_wall_s=services._last_frame.captured_wall_s + 10.0)

    services.descriptor = {**dict(services.descriptor), "bundle_sha256": "b" * 64}
    with pytest.raises(ValueError, match="HEAD_CAPTURE_FRAME_MISMATCH"):
        services.capture()
