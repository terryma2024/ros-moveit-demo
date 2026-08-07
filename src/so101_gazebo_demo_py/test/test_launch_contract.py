import importlib.util
from pathlib import Path

from launch import LaunchContext, LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.utilities import perform_substitutions
from launch_ros.actions import Node


PACKAGE = Path(__file__).parents[1]
LAUNCH_NAMES = (
    "so101_display.launch.py", "so101_controller.launch.py",
    "so101_gazebo.launch.py", "so101_move_group_headless.launch.py",
    "so101_moveit.launch.py",
)


def load(name: str) -> LaunchDescription:
    path = PACKAGE / "launch" / name
    spec = importlib.util.spec_from_file_location(name.replace(".", "_"), path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.generate_launch_description()
    assert isinstance(result, LaunchDescription)
    return result


def test_all_public_stack_launches_generate() -> None:
    for name in LAUNCH_NAMES:
        assert list(load(name).entities)


def test_gazebo_headless_default_is_false() -> None:
    arguments = {
        entity.name: perform_substitutions(LaunchContext(), entity.default_value)
        for entity in load("so101_gazebo.launch.py").entities
        if isinstance(entity, DeclareLaunchArgument)
    }
    assert arguments["headless"] == "false"


def test_controller_launch_names_all_public_controllers() -> None:
    nodes = [entity for entity in load("so101_controller.launch.py").entities if isinstance(entity, Node)]
    arguments = {str(argument) for node in nodes for argument in (node._Node__arguments or [])}
    assert {"joint_state_broadcaster", "arm_controller", "gripper_controller"} <= arguments


def test_launches_use_only_new_package_assets() -> None:
    for name in LAUNCH_NAMES:
        text = (PACKAGE / "launch" / name).read_text()
        assert 'get_package_share_directory("so101_gazebo_demo")' not in text
        assert 'package_name="so101_gazebo_demo"' not in text
        assert "libso101_attachment_collision_system.so" not in text
