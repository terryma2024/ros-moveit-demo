from types import SimpleNamespace

import pytest

from so101_teleop.backends.protocol import BackendEnvelope, BackendError
from so101_teleop.main import select_backend


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
