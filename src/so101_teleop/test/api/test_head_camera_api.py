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
    """A descriptor whose owner is this live process, because a dead owner is now refused."""

    import os

    from so101_teleop.head_camera import process_start_ticks

    return {
        "operation": "TELEOP_ACCEPTANCE",
        "runtime_id": "runtime-0001",
        "head_search_runtime_id": "runtime-0001",
        "model_id": "head-search-runtime",
        "bundle_sha256": "a" * 64,
        "simulation_session_id": "session-0001",
        "execution_generation": 1,
        "owner": {"pid": os.getpid(), "started_ticks": process_start_ticks(os.getpid())},
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
    def sample(index: int) -> dict:
        return {"neck_velocity_rad_s": 0.01, "sim_time_s": 1.0 + index * 0.1}

    assert services.status()["state"] == "STOPPING", "a stop in progress is never reported stopped"
    assert services.stop(raw_sample=sample(0))["state"] == "STOPPING"
    assert services.stop(raw_sample=sample(1))["state"] == "STOPPING"
    assert services.stop(raw_sample=sample(2))["state"] == "STOPPED"
    assert services.stop(raw_sample=sample(1))["state"] == "STOPPING", "time regression restarts the proof"
    assert services.stop(raw_sample=None)["state"] == "STOPPING", "a missing sample cannot advance it"
    assert services.stop(raw_sample=sample(3))["consecutive_samples"] == 1

    # a negative velocity is not a stopped neck, however fresh the samples are
    for index in range(3):
        negative = {"neck_velocity_rad_s": -0.5, "sim_time_s": 10.0 + index}
        assert services.stop(raw_sample=negative)["consecutive_samples"] == 0
    assert services.stop_state() == "STOPPING"


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
    assert client.post("/teleop/head-camera/stop", json={"sim_time_s": 1.0}).json()["state"] == "STOPPING"
    sealed = client.post(
        "/teleop/head-camera/target", json={"target_rad": 0.5, "safe_interval_rad": [-99.0, 99.0]}
    )
    assert sealed.status_code == 409
    assert sealed.json()["detail"]["code"] == "HEAD_TARGET_INTERVAL_SEALED"
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


def test_composition_refuses_a_dead_or_drifted_owner(tmp_path: Path) -> None:
    from so101_teleop.head_camera import CompositionBlocked, verify_owner

    import os

    from so101_teleop.head_camera import process_start_ticks

    live = {"pid": os.getpid(), "started_ticks": process_start_ticks(os.getpid())}
    verify_owner(live)  # a live owner with the kernel's ticks is accepted
    with pytest.raises(CompositionBlocked, match="HEAD_CAMERA_CONNECTION_MISMATCH"):
        verify_owner({"pid": os.getpid(), "started_ticks": 1})
    with pytest.raises(CompositionBlocked, match="HEAD_CAMERA_CONNECTION_MISMATCH"):
        verify_owner({"pid": 999999999, "started_ticks": 1})
    with pytest.raises(CompositionBlocked, match="HEAD_CAMERA_CONNECTION_MISMATCH"):
        verify_owner(live, expected_owner=4242)

    descriptor = valid_descriptor(tmp_path)
    dead = {**descriptor, "owner": {"pid": 999999999, "started_ticks": 1}}
    environment = environment_for(tmp_path, dead)
    with pytest.raises(CompositionBlocked, match="HEAD_CAMERA_CONNECTION_MISMATCH"):
        compose_head_camera(environment)


def test_a_zombie_process_is_not_a_live_owner(tmp_path: Path) -> None:
    """A zombie keeps its /proc entry and start ticks but has exited, so it is no owner."""

    import os
    import signal
    import time

    from so101_teleop.head_camera import CompositionBlocked, process_start_ticks, verify_owner

    child = os.fork()
    if child == 0:  # pragma: no cover - the child sleeps until it is killed
        time.sleep(30)
        os._exit(0)
    try:
        # the child is alive and running here, so its ticks are readable and it would be a valid owner
        alive_ticks = process_start_ticks(child)
        deadline = time.monotonic() + 5.0
        while alive_ticks is None and time.monotonic() < deadline:
            time.sleep(0.02)
            alive_ticks = process_start_ticks(child)
        assert alive_ticks is not None and alive_ticks > 0
        verify_owner({"pid": child, "started_ticks": alive_ticks})

        os.kill(child, signal.SIGKILL)
        # wait for the kernel to report the zombie state directly, reading /proc rather than the helper
        state = None
        vanished = False
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            try:
                fields = Path(f"/proc/{child}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            except OSError:
                # only a /proc entry that has gone away counts as external reaping
                vanished = True
                break
            state = fields[0]
            if state == "Z":
                break
            time.sleep(0.02)
        if state == "Z":
            # the ticks are still on record for the zombie, and the owner check must still refuse it
            fields = Path(f"/proc/{child}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1].split()
            assert int(fields[19]) == alive_ticks, "the zombie keeps its recorded start ticks"
            assert process_start_ticks(child) is None
            with pytest.raises(CompositionBlocked, match="HEAD_CAMERA_CONNECTION_MISMATCH"):
                verify_owner({"pid": child, "started_ticks": alive_ticks})
        elif vanished:
            pytest.skip("an external reaper removed the child before the zombie state was observed")
        else:
            # a still-readable process that never became a zombie is a failure, not a reason to skip
            pytest.fail(f"the child never reached the zombie state (state {state!r})")
    finally:
        try:
            os.waitpid(child, 0)
        except ChildProcessError:  # pragma: no cover - already reaped
            pass


def test_status_carries_every_field_the_shipped_panel_reads(tmp_path: Path) -> None:
    """The panel destructures `safe_interval_rad` and gates the controls on qualified/authority.

    A status that omits them is not a view-only page: `HeadCameraPanel` destructures the interval
    unconditionally, so the shipped tab throws while rendering a perfectly available domain (found by
    the Task 14 Step 6 acceptance, HS-325).
    """

    descriptor = valid_descriptor(tmp_path)
    descriptor["safe_interval_rad"] = [-6.283175307179587, 6.283175307179587]
    services = compose_head_camera(environment_for(tmp_path, descriptor))

    status = services.status()

    assert status["safe_interval_rad"] == [-6.283175307179587, 6.283175307179587]
    assert status["qualified"] is False, "a descriptor without a closed report is never qualified"
    assert status["authority"] is False, "the view-only composition holds no controller authority"
    assert status["detector_constructed"] == 0
    assert status["state"] == "STOPPING"


def test_status_reports_a_closed_report_and_authority_only_when_declared(tmp_path: Path) -> None:
    descriptor = valid_descriptor(tmp_path)
    descriptor["safe_interval_rad"] = [-0.2, 0.3]
    descriptor["qualification_report"] = {"status": "HEAD_SEARCH_QUALIFIED", "path": "/x/report.json"}
    descriptor["authority"] = True
    services = compose_head_camera(environment_for(tmp_path, descriptor))

    status = services.status()

    assert status["qualified"] is True
    assert status["authority"] is True
    assert status["safe_interval_rad"] == [-0.2, 0.3]


def test_the_unified_composition_root_exposes_the_head_camera_domain(tmp_path: Path) -> None:
    """The router reads `services.head_camera`; nothing composed it, so the whole domain answered 503.

    Found by the Task 14 Step 6 acceptance (HS-325): `compose_head_camera_service` existed, was unit
    tested, and was never called by the composition root the installed app actually runs.
    """

    from so101_teleop.unified.compose import compose_domain_services

    descriptor = valid_descriptor(tmp_path)
    descriptor["safe_interval_rad"] = [-0.2, 0.3]
    environment = environment_for(tmp_path, descriptor)
    evidence_root = tmp_path / "evidence"
    environment["SO101_UNIFIED_EVIDENCE_ROOT"] = str(evidence_root)

    services = compose_domain_services(environment=environment, evidence_root=evidence_root)

    assert services.head_camera is not None, "the closed descriptor must compose the domain"
    status = services.head_camera.status()
    assert status["operation"] == "TELEOP_ACCEPTANCE"
    assert status["safe_interval_rad"] == [-0.2, 0.3]
    assert status["detector_constructed"] == 0


def test_the_unified_composition_root_keeps_a_drifted_domain_unavailable(tmp_path: Path) -> None:
    from so101_teleop.unified.compose import compose_domain_services

    descriptor = valid_descriptor(tmp_path)
    environment = environment_for(tmp_path, descriptor, runtime_id="another-runtime")
    evidence_root = tmp_path / "evidence"
    environment["SO101_UNIFIED_EVIDENCE_ROOT"] = str(evidence_root)

    services = compose_domain_services(environment=environment, evidence_root=evidence_root)

    assert services.head_camera is None
    assert "HEAD_CAMERA_CONNECTION_MISMATCH" in services.head_camera_error


def test_the_unified_composition_root_leaves_the_domain_unavailable_without_a_connection(
    tmp_path: Path,
) -> None:
    from so101_teleop.unified.compose import compose_domain_services

    evidence_root = tmp_path / "evidence"
    services = compose_domain_services(
        environment={"SO101_UNIFIED_EVIDENCE_ROOT": str(evidence_root)}, evidence_root=evidence_root
    )

    assert services.head_camera is None
    assert services.head_camera_error is None, "no declaration is not a refusal"


def test_the_stream_endpoint_really_upgrades_the_websocket(tmp_path: Path) -> None:
    """The handshake must reach the handler, not be closed as a failed query validation.

    `head_camera.py` carries `from __future__ import annotations`, so every annotation is a string that
    FastAPI resolves against the module's globals. `WebSocket` was imported *inside* the router factory,
    so the annotation was unresolvable: FastAPI validated the socket itself as a query parameter named
    `websocket` and closed every handshake with 403 before the handler ran. Found by the Task 14 Step 6
    acceptance (HS-325); the plan's raw/overlay pair is impossible without this route.
    """

    from fastapi import FastAPI
    from starlette.testclient import TestClient

    from so101_teleop.head_camera import head_camera_router

    descriptor = valid_descriptor(tmp_path)
    descriptor["safe_interval_rad"] = [-0.2, 0.3]
    backend = compose_head_camera(environment_for(tmp_path, descriptor))
    services = type("Services", (), {"head_camera": backend})()
    app = FastAPI()
    app.include_router(head_camera_router(services))

    with TestClient(app).websocket_connect("/teleop/head-camera/stream") as socket:
        socket.send_text("frame")
        envelope = socket.receive_json()

    assert envelope["sequence"] == 1
    assert envelope["model_id"] == descriptor["model_id"]
    assert envelope["bundle_sha256"] == descriptor["bundle_sha256"]
    assert backend.status()["detector_constructed"] == 0
