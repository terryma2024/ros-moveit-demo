from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
import yaml
from so101_teleop.backends.profile import ProfileError, load_profile_file
from so101_teleop.backends.protocol import BackendOperation
from so101_teleop.backends.registry import BACKEND_IDS, load_backend_profile

PACKAGE = Path(__file__).resolve().parents[2]
DEMO_PACKAGE = PACKAGE.parent / "so101_demo_py"


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
        if name not in {
            "workflow_stop", "task_batch", "task_reachability",
            "sensor_capture", "task_environment_shutdown",
        }
    )


def test_gazebo_py_profile_routes_run_to_canonical_bounded_execute():
    profile = load_backend_profile("gazebo_py", PACKAGE)

    assert profile.owner_package == "so101_demo_py"
    assert profile.probe.executable == "pick_place"
    assert set(profile.operations) == {
        BackendOperation.WORKFLOW,
        BackendOperation.RESET_WORLD,
        BackendOperation.SCENE,
        BackendOperation.CAMERA_PRESET,
    }
    assert profile.operations[BackendOperation.WORKFLOW].executable == "gazebo_execute"
    reset = profile.operations[BackendOperation.RESET_WORLD]
    assert (reset.package, reset.executable, reset.fixed_args, reset.session_style) == (
        "so101_demo_py", "teleop_reset", ("--backend", "gazebo"), "flag"
    )
    scene = profile.operations[BackendOperation.SCENE]
    assert (scene.package, scene.executable, scene.fixed_args, scene.scene_style) == (
        "so101_demo_py", "scene_setup", ("--backend", "gazebo"), "positional"
    )
    camera = profile.operations[BackendOperation.CAMERA_PRESET]
    assert (camera.package, camera.executable, camera.fixed_args) == (
        "so101_demo_py", "camera_preset", ("--backend", "gazebo")
    )
    assert profile.camera_presets == ("overview", "top", "side", "gripper", "cup")
    camera_config = yaml.safe_load(
        (DEMO_PACKAGE / "config/gazebo/camera_views.yaml").read_text()
    )
    assert profile.camera_presets == tuple(camera_config["presets"])
    assert profile.capabilities.as_dict() == {
        "backend_probe": True,
        "workflow_execute": True,
        "workflow_start": False,
        "workflow_run": True,
        "workflow_resume": False,
        "workflow_stop": False,
        "reset_world": True,
        "scene_operations": True,
        "physical_observation": True,
        "manual_joint_execute": True,
        "manual_tcp_execute": True,
        "camera_presets": True,
        "task_batch": False,
        "task_reachability": False,
        "sensor_capture": False,
        "task_environment_shutdown": False,
    }


def test_mujoco_profile_exposes_only_qualified_live_boundaries():
    profile = load_backend_profile("mujoco_py", PACKAGE)

    assert profile.owner_package == "so101_demo_py"
    assert profile.probe.executable == "teleop_workflow"
    assert set(profile.operations) == {
        BackendOperation.WORKFLOW,
        BackendOperation.RESET_WORLD,
        BackendOperation.CAMERA_PRESET,
        BackendOperation.TASK_BATCH,
        BackendOperation.TASK_REACHABILITY,
        BackendOperation.SENSOR_CAPTURE,
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
        "task_batch": True,
        "task_reachability": True,
        "sensor_capture": True,
        "task_environment_shutdown": True,
    }
    assert profile.operations[BackendOperation.TASK_BATCH].executable == (
        "so101_mujoco_rgbd_batch"
    )
    assert profile.operations[BackendOperation.TASK_REACHABILITY].executable == (
        "task_reachability"
    )
    assert profile.operations[BackendOperation.SENSOR_CAPTURE].executable == (
        "rgbd_sensor_capture"
    )


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
