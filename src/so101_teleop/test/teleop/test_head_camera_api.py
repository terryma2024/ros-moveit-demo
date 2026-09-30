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


def test_composition_derives_the_head_runtime_from_the_closed_descriptor(tmp_path: Path) -> None:
    from so101_teleop.unified.compose import CompositionBlocked as Blocked
    from so101_teleop.unified.compose import compose_head_camera_service

    descriptor = valid_descriptor(tmp_path)
    environment = environment_for(tmp_path, descriptor)
    if True:
        environment["SO101_UNIFIED_SOCKET_DIR"] = str(tmp_path)
        environment["SO101_UNIFIED_RUNTIME_ID"] = descriptor["runtime_id"]
    services = compose_head_camera_service(environment)
    assert services is not None
    assert services.detector_factory_calls == 0
    assert services.execution_generation == descriptor["execution_generation"]

    with pytest.raises(Blocked, match="HEAD_CAMERA_CONNECTION_MISMATCH"):
        compose_head_camera_service({**environment, "SO101_UNIFIED_RUNTIME_ID": "other"})
    with pytest.raises(Blocked, match="HEAD_CAMERA_CONNECTION_MISMATCH"):
        compose_head_camera_service({**environment, "SO101_UNIFIED_SOCKET_DIR": str(tmp_path / "x")})

    assert compose_head_camera_service({}) is None, "no closed connection keeps the domain unavailable"


def test_the_router_exposes_the_five_endpoints_over_the_composed_backend(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from so101_teleop.head_camera import head_camera_router

    descriptor = valid_descriptor(tmp_path)
    descriptor["safe_interval_rad"] = [-1.0, 1.0]

    class Services:
        def __init__(self, backend):
            self.head_camera = backend

    class Unavailable:
        head_camera = None

    def client_for(services) -> TestClient:
        application = FastAPI()
        application.include_router(head_camera_router(services))
        return TestClient(application)

    services = Services(compose_head_camera(environment_for(tmp_path, descriptor)))
    client = client_for(services)
    assert client.get("/teleop/head-camera/status").json()["detector_constructed"] == 0
    refused = client.post("/teleop/head-camera/target", json={"target_rad": 99.0})
    assert refused.status_code == 409
    assert refused.json()["detail"]["code"] == "HEAD_TARGET_OUT_OF_RANGE"
    assert client.post("/teleop/head-camera/target", json={"target_rad": 0.5}).status_code == 200
    assert client.post("/teleop/head-camera/stop", json={}).json()["state"] == "STOPPING"
    # the stream endpoint exists and refuses an unavailable domain; its live framing is exercised by
    # Task 11's installed smoke and Task 14's end-to-end run, where a real socket and teardown exist
    router = head_camera_router(services)
    declared = {getattr(route, "path", None) for route in router.routes}
    assert {
        "/teleop/head-camera/status",
        "/teleop/head-camera/stream",
        "/teleop/head-camera/target",
        "/teleop/head-camera/stop",
        "/teleop/head-camera/capture",
    } <= declared

    unavailable = client_for(Unavailable())
    assert unavailable.get("/teleop/head-camera/status").status_code == 503
    assert unavailable.post("/teleop/head-camera/capture").status_code == 503
