from pathlib import Path
from xml.etree import ElementTree

import yaml


PACKAGE = Path(__file__).resolve().parents[1]
FORK = PACKAGE.parents[1] / "third_party" / "mujoco_ros2_control"
PROBE = PACKAGE / "test/macos_camera_topic_probe.py"


def test_task_camera_is_configured_as_the_mujoco_camera_plugin() -> None:
    """The SO-101 RGB-D stream must enter through pluginlib, not URDF sensors."""
    parameters = yaml.safe_load(
        (PACKAGE / "config/mujoco/mujoco_plugins.yaml").read_text(encoding="utf-8")
    )["/**"]["ros__parameters"]

    camera = parameters["mujoco_plugins"]["mujoco_camera_plugin"]
    assert camera["type"] == "mujoco_ros2_control_plugins/CameraPlugin"
    assert camera["camera_publish_rate"] == 10.0
    task_camera = camera["task_camera"]
    assert task_camera["frame_name"] == "task_camera_frame"
    assert task_camera["info_topic"] == "/task_camera/camera_info"
    assert task_camera["image_topic"] == "/task_camera/color"
    assert task_camera["depth_topic"] == "/task_camera/depth"


def test_pinned_fork_builds_camera_plugin_instead_of_system_camera_wrapper() -> None:
    """Keep the lifecycle boundary at pluginlib as upstream does."""
    plugin_cmake = (FORK / "mujoco_ros2_control_plugins/CMakeLists.txt").read_text(encoding="utf-8")
    system_cmake = (FORK / "mujoco_ros2_control/CMakeLists.txt").read_text(encoding="utf-8")

    assert "src/camera_plugin.cpp" in plugin_cmake
    assert "src/mujoco_cameras.cpp" not in system_cmake


def test_task_camera_declares_a_nontrivial_rgbd_resolution() -> None:
    camera = next(
        camera
        for camera in ElementTree.parse(PACKAGE / "assets/mujoco/scene.xml").iter("camera")
        if camera.attrib.get("name") == "task_camera"
    )
    assert camera.attrib["resolution"] == "640 480"


def test_runtime_probe_enforces_the_cross_platform_rgbd_contract() -> None:
    probe = PROBE.read_text(encoding="utf-8")

    assert '(color.width, color.height) != (640, 480)' in probe
    assert 'color.header.frame_id != "task_camera_frame"' in probe
    assert "not 8.0 <= frequency_hz <= 12.0" in probe
    assert 'color.encoding.lower() != "rgb8"' in probe
    assert 'depth.encoding.upper() != "32FC1"' in probe
    for topic in (
        "/task_camera/camera_info",
        "/task_camera/color",
        "/task_camera/depth",
    ):
        assert topic in probe
