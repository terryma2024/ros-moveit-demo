import importlib.util
import platform
from pathlib import Path
from types import SimpleNamespace

import pytest

from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    RegisterEventHandler,
)
from launch.event_handlers import OnProcessStart
from launch_ros.actions import Node

from launch import LaunchContext
import so101_demo.runtime.launch_composition as launch_composition
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
    assert "graceful_shutdown_move_group" in executables
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


def test_task_station_starts_teleop_with_exact_mujoco_process_pid() -> None:
    context = LaunchContext()
    context.launch_configurations["teleop_port"] = "8080"

    actions = launch_composition._task_station_teleop_actions(
        SimpleNamespace(pid=53900),
        context,
        teleop_share=Path("/installed/share/so101_teleop"),
        session_id="sim-a",
    )

    actions[0].execute(context)
    assert context.environment["SO101_TASK_STATION_MUJOCO_PID"] == "53900"
    assert isinstance(actions[1], IncludeLaunchDescription)


def test_task_station_registers_teleop_start_handler_before_mujoco(
    tmp_path: Path,
) -> None:
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
            "include_teleop": "true",
        }
    )
    opaque = next(
        entity for entity in description.entities if isinstance(entity, OpaqueFunction)
    )
    actions = opaque.execute(context)

    mujoco_index = next(
        index
        for index, action in enumerate(actions)
        if isinstance(action, Node) and action.node_executable == "ros2_control_node"
    )
    handler_index = next(
        index
        for index, action in enumerate(actions)
        if isinstance(action, RegisterEventHandler)
        and isinstance(action.event_handler, OnProcessStart)
    )
    assert handler_index < mujoco_index


def _configured_task_station(tmp_path: Path, monkeypatch, **values):
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
            "session_id": "parallel-a",
            "task_evidence_root": str(tmp_path),
            **values,
        }
    )
    opaque = next(
        entity for entity in description.entities if isinstance(entity, OpaqueFunction)
    )
    monkeypatch.setattr(platform, "system", lambda: values.pop("platform_name", "Linux"))
    return opaque.execute(context)


def test_linux_headless_task_station_keeps_camera_controllers_and_moveit(
    tmp_path: Path, monkeypatch
) -> None:
    actions = _configured_task_station(
        tmp_path,
        monkeypatch,
        platform_name="Linux",
        headless="true",
        sensor_rendering="true",
        include_teleop="false",
    )
    executables = [
        action.node_executable for action in actions if isinstance(action, Node)
    ]

    assert executables.count("static_transform_publisher") == 2
    assert "ros2_control_node" in executables
    assert "graceful_shutdown_move_group" in executables


@pytest.mark.parametrize(
    ("platform_name", "sensor_rendering", "include_teleop", "message"),
    (
        ("Darwin", "true", "false", "macOS"),
        ("Linux", "false", "false", "sensor_rendering"),
        ("Linux", "true", "true", "include_teleop"),
    ),
)
def test_headless_task_station_rejects_unsupported_platform_or_shared_ui(
    tmp_path: Path,
    monkeypatch,
    platform_name: str,
    sensor_rendering: str,
    include_teleop: str,
    message: str,
) -> None:
    with pytest.raises(RuntimeError, match=message):
        _configured_task_station(
            tmp_path,
            monkeypatch,
            platform_name=platform_name,
            headless="true",
            sensor_rendering=sensor_rendering,
            include_teleop=include_teleop,
        )
