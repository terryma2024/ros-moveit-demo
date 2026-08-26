from pathlib import Path
from xml.etree import ElementTree

import yaml

PACKAGE = Path(__file__).resolve().parents[1]
FORK = PACKAGE.parents[1] / "third_party" / "mujoco_ros2_control"
PROBE = PACKAGE / "test/macos_camera_topic_probe.py"
CAMERA_PLUGIN_XML = FORK / "mujoco_ros2_control_plugins/mujoco_ros2_control_plugins.xml"
CAMERA_PLUGIN_SOURCE = FORK / "mujoco_ros2_control_plugins/src/camera_plugin.cpp"


def test_task_camera_is_configured_as_the_mujoco_camera_plugin() -> None:
    """The SO-101 RGB-D stream must enter through pluginlib, not URDF sensors."""
    parameters = yaml.safe_load(
        (PACKAGE / "config/mujoco/mujoco_plugins.yaml").read_text(encoding="utf-8")
    )["/**"]["ros__parameters"]

    camera = parameters["mujoco_plugins"]["mujoco_camera_plugin"]
    assert camera["type"] == "mujoco_ros2_control_plugins/CameraPlugin"
    assert camera["camera_publish_rate"] == 10.0
    task_camera = camera["task_camera"]
    assert task_camera["policy"] == "streaming"
    assert task_camera["frame_name"] == "task_camera_frame"
    assert task_camera["info_topic"] == "/task_camera/camera_info"
    assert task_camera["image_topic"] == "/task_camera/color"
    assert task_camera["depth_topic"] == "/task_camera/depth"


def test_pinned_fork_builds_camera_plugin_instead_of_system_camera_wrapper() -> None:
    """Keep the lifecycle boundary at pluginlib as upstream does."""
    plugin_cmake = (FORK / "mujoco_ros2_control_plugins/CMakeLists.txt").read_text(encoding="utf-8")
    system_cmake = (FORK / "mujoco_ros2_control/CMakeLists.txt").read_text(encoding="utf-8")
    plugin_classes = ElementTree.parse(CAMERA_PLUGIN_XML).getroot().findall("class")
    camera_plugin = next(
        item
        for item in plugin_classes
        if item.attrib["name"] == "mujoco_ros2_control_plugins/CameraPlugin"
    )

    assert "src/camera_plugin.cpp" in plugin_cmake
    assert "src/mujoco_cameras.cpp" not in system_cmake
    assert camera_plugin.attrib["type"] == "mujoco_ros2_control_plugins::CameraPlugin"
    assert (
        camera_plugin.attrib["base_class_type"]
        == "mujoco_ros2_control_plugins::MuJoCoROS2ControlPluginBase"
    )


def test_pinned_camera_plugin_closes_its_render_worker_before_shutdown() -> None:
    source = CAMERA_PLUGIN_SOURCE.read_text(encoding="utf-8")

    assert "void CameraPlugin::cleanup()" in source
    assert "close_rendering();" in source
    assert "void CameraPlugin::close_rendering()" in source
    assert "set_rendering_enabled(false);" in source
    assert "void CameraPlugin::close()" in source
    assert "stop_requested_ = true;" in source
    assert "rendering_thread_.join();" in source


def test_task_camera_declares_a_nontrivial_rgbd_resolution() -> None:
    camera = next(
        camera
        for camera in ElementTree.parse(PACKAGE / "assets/mujoco/scene.xml").iter("camera")
        if camera.attrib.get("name") == "task_camera"
    )
    assert camera.attrib["resolution"] == "640 480"
    assert camera.attrib["pos"] == "0.65 -0.65 0.55"
    assert camera.attrib["xyaxes"] == "0.7 0.7 0 -0.35 0.35 0.87"


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


def test_support_package_declares_opengl_egl_build_contract() -> None:
    package = ElementTree.parse(PACKAGE.parent / "so101_mujoco_support/package.xml")
    build_dependencies = {element.text for element in package.getroot().findall("build_depend")}

    assert "opengl" in build_dependencies
