import importlib.util
from pathlib import Path

from launch.actions import DeclareLaunchArgument, OpaqueFunction
from launch_ros.actions import Node

from launch import LaunchContext
from so101_demo.runtime.launch_composition import build_task_station_launch_description


PACKAGE = Path(__file__).parents[1]


def test_task_station_launch_is_visible_persistent_and_has_camera_tf(tmp_path: Path) -> None:
    description = build_task_station_launch_description()
    declared = {
        entity.name: entity
        for entity in description.entities
        if isinstance(entity, DeclareLaunchArgument)
    }
    context = LaunchContext()
    for name, argument in declared.items():
        context.launch_configurations[name] = argument.default_value[0].perform(context)
    context.launch_configurations.update(
        {
            "session_id": "sim-a",
            "task_evidence_root": str(tmp_path),
            "include_teleop": "false",
        }
    )
    opaque = next(
        entity for entity in description.entities if isinstance(entity, OpaqueFunction)
    )
    actions = opaque.execute(context)
    nodes = [action for action in actions if isinstance(action, Node)]
    executables = [node.node_executable for node in nodes]

    assert context.launch_configurations["headless"] == "false"
    assert executables.count("static_transform_publisher") == 2
    assert "ros2_control_node" in executables
    assert "so101_move_group" in executables
    assert "rgbd_cup_pose" not in executables
    assert "dynamic_cup_pick_place" not in executables


def test_public_task_station_launcher_is_thin() -> None:
    path = PACKAGE / "launch/so101_mujoco_task_station.launch.py"
    source = path.read_text()
    assert "DeclareLaunchArgument" not in source
    spec = importlib.util.spec_from_file_location("task_station_launch", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.generate_launch_description() is not None
