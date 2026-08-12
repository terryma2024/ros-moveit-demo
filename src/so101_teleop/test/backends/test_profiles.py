from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from so101_teleop.backends.profile import ProfileError, load_profile_file
from so101_teleop.backends.protocol import BackendOperation
from so101_teleop.backends.registry import BACKEND_IDS, load_backend_profile


PACKAGE = Path(__file__).resolve().parents[2]


def test_registry_accepts_only_fixed_backend_ids():
    assert BACKEND_IDS == ("gazebo_cpp", "gazebo_py", "mujoco_py")
    with pytest.raises(ProfileError, match="BACKEND_ID_INVALID"):
        load_backend_profile("request-selected", PACKAGE)


def test_gazebo_cpp_profile_pins_installed_owners():
    profile = load_backend_profile("gazebo_cpp", PACKAGE)

    assert profile.owner_package == "so101_gazebo_demo_cpp"
    assert profile.operations[BackendOperation.WORKFLOW].executable == "pick_place_state_machine"
    assert profile.operations[BackendOperation.RESET_WORLD].executable == "reset_so101_world"
    scene = profile.operations[BackendOperation.SCENE]
    assert scene.executable == "so101_moveit_scene"
    assert scene.scene_style == "positional"
    assert profile.capabilities.workflow_stop is False
    assert all(
        value
        for name, value in profile.capabilities.as_dict().items()
        if name != "workflow_stop"
    )


def test_gazebo_py_profile_pins_python_cli_differences():
    profile = load_backend_profile("gazebo_py", PACKAGE)

    workflow = profile.operations[BackendOperation.WORKFLOW]
    scene = profile.operations[BackendOperation.SCENE]
    assert profile.owner_package == "so101_gazebo_demo_py"
    assert workflow.fixed_args == ("--live-runtime",)
    assert scene.scene_style == "flag"
    assert profile.capabilities.scene_operations is False
    assert profile.capabilities.workflow_run is True


def test_mujoco_profile_exposes_only_qualified_live_boundaries():
    profile = load_backend_profile("mujoco_py", PACKAGE)

    assert profile.owner_package == "so101_mujoco_demo_py"
    assert profile.probe.executable == "pick_place_state_machine"
    assert set(profile.operations) == {
        BackendOperation.WORKFLOW,
        BackendOperation.RESET_WORLD,
        BackendOperation.CAMERA_PRESET,
    }
    assert profile.capabilities.as_dict() == {
        "backend_probe": True,
        "workflow_execute": True,
        "workflow_start": False,
        "workflow_run": True,
        "workflow_resume": False,
        "workflow_stop": False,
        "reset_world": True,
        "scene_operations": False,
        "physical_observation": False,
        "manual_joint_execute": False,
        "manual_tcp_execute": False,
        "camera_presets": True,
    }


def test_profiles_and_nested_specs_are_frozen():
    profile = load_backend_profile("gazebo_cpp", PACKAGE)
    with pytest.raises(FrozenInstanceError):
        profile.owner_package = "injected"
    with pytest.raises(TypeError):
        profile.operations[BackendOperation.WORKFLOW] = profile.probe


def test_profile_rejects_request_selected_executable(tmp_path):
    path = tmp_path / "gazebo_cpp.yaml"
    path.write_text("backend: gazebo_cpp\nowner_package: injected\nextra: shell\n")
    with pytest.raises(ProfileError, match="PROFILE_SCHEMA_INVALID"):
        load_profile_file(path, expected_backend="gazebo_cpp")


def test_profile_rejects_backend_mismatch(tmp_path):
    source = PACKAGE / "config" / "backends" / "gazebo_cpp.yaml"
    path = tmp_path / "gazebo_py.yaml"
    path.write_text(source.read_text())
    with pytest.raises(ProfileError, match="PROFILE_BACKEND_MISMATCH"):
        load_profile_file(path, expected_backend="gazebo_py")
