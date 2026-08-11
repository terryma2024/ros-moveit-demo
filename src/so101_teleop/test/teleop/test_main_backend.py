import importlib
import sys
from types import SimpleNamespace

import pytest

from so101_teleop.backends.protocol import BackendEnvelope, BackendError
from so101_teleop.main import select_backend


main_module = importlib.import_module("so101_teleop.main")


class Adapter:
    def __init__(self, profile, envelope):
        self.profile = profile
        self._envelope = envelope

    def probe(self):
        return self._envelope


def envelope(*, ok, error=None):
    return BackendEnvelope(
        ok=ok,
        backend="gazebo_cpp",
        operation="backend_probe",
        session_id=None,
        owner_package="so101_gazebo_demo_cpp",
        owner_executable="pick_place_state_machine",
        exit_code=0 if ok else None,
        result={} if ok else None,
        error=error,
    )


def test_backend_is_required_before_profile_or_adapter_construction():
    calls = []

    with pytest.raises(RuntimeError, match="SO101_TELEOP_BACKEND is required"):
        select_backend(
            {},
            profile_loader=lambda backend: calls.append(("profile", backend)),
            adapter_factory=lambda profile: calls.append(("adapter", profile)),
        )

    assert calls == []


def test_selected_backend_probe_failure_aborts_with_normalized_code():
    profile = SimpleNamespace(backend="gazebo_cpp")
    failure = BackendError("BACKEND_EXECUTABLE_NOT_FOUND", "owner missing")

    with pytest.raises(RuntimeError, match="BACKEND_EXECUTABLE_NOT_FOUND: owner missing"):
        select_backend(
            {"SO101_TELEOP_BACKEND": "gazebo_cpp"},
            profile_loader=lambda backend: profile,
            adapter_factory=lambda selected: Adapter(
                selected, envelope(ok=False, error=failure)
            ),
        )


def test_selected_backend_is_frozen_after_successful_probe():
    profile = SimpleNamespace(backend="gazebo_py")
    adapter = Adapter(profile, BackendEnvelope(
        ok=True,
        backend="gazebo_py",
        operation="backend_probe",
        session_id=None,
        owner_package="so101_gazebo_demo_py",
        owner_executable="pick_place_state_machine",
        exit_code=0,
        result={"status": "available"},
    ))

    selected = select_backend(
        {"SO101_TELEOP_BACKEND": "gazebo_py"},
        profile_loader=lambda backend: profile,
        adapter_factory=lambda selected_profile: adapter,
    )

    assert selected is adapter
    assert selected.profile.backend == "gazebo_py"


def test_server_lifecycle_stops_ros_worker_when_uvicorn_returns(monkeypatch, tmp_path):
    events = []

    class Worker:
        def __init__(self, backend):
            events.append(("construct", backend))

        def start(self):
            events.append(("start",))

        def stop(self):
            events.append(("stop",))

    backend = object()
    monkeypatch.setenv("SO101_CAMERA_VIEWS", str(tmp_path / "camera.yaml"))
    monkeypatch.setattr(main_module, "validate_bind_address", lambda address: address)
    monkeypatch.setattr(main_module, "select_backend", lambda environment: backend)
    monkeypatch.setattr(main_module, "RosTelemetryWorker", Worker)
    monkeypatch.setattr(main_module, "load_camera_presets", lambda path: {})
    monkeypatch.setattr(main_module, "CameraController", lambda presets: object())
    monkeypatch.setattr(main_module, "TeleopService", lambda *args, **kwargs: object())
    monkeypatch.setattr(main_module, "installed_web_assets", lambda: tmp_path)
    monkeypatch.setattr(main_module, "create_app", lambda *args, **kwargs: "app")
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(
        run=lambda *args, **kwargs: events.append(("serve",))))

    main_module.main()

    assert events == [
        ("construct", backend),
        ("start",),
        ("serve",),
        ("stop",),
    ]
