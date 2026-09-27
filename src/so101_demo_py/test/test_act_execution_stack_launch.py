"""The unified child must be the only ACT command broker in its ROS domain."""

import importlib.util
from pathlib import Path

import pytest
from launch import LaunchContext
from launch.actions import DeclareLaunchArgument, OpaqueFunction, SetEnvironmentVariable
from launch.utilities import perform_substitutions
from launch_ros.actions import Node
from launch_ros.utilities import evaluate_parameters

from so101_demo.runtime import launch_composition as launch
from so101_teleop.unified.controller_reservation_paths import controller_reservation_directory


def configured(tmp_path, *, overrides=None):
    description = launch.build_act_execution_stack_launch_description()
    context = LaunchContext()
    for action in description.entities:
        if isinstance(action, DeclareLaunchArgument) and action.default_value is not None:
            context.launch_configurations[action.name] = perform_substitutions(
                context, action.default_value)
    context.launch_configurations.update({
        "session_id": "act-task8-case-01", "task_evidence_root": str(tmp_path),
        **(overrides or {}),
    })
    opaque = next(action for action in description.entities if isinstance(action, OpaqueFunction))
    return description, context, opaque


def test_dedicated_act_stack_has_sim_moveit_four_controllers_rgb_and_no_broker(tmp_path):
    description, context, opaque = configured(tmp_path)
    declared = {action.name for action in description.entities
                if isinstance(action, DeclareLaunchArgument)}
    assert "act_broker_socket" not in declared and "include_teleop" not in declared
    actions = opaque.execute(context)
    nodes = [action for action in actions if isinstance(action, Node)]
    names = [node.node_executable for node in nodes]
    assert names.count("ros2_control_node") == 1
    assert names.count("robot_state_publisher") == 1
    assert names.count("graceful_shutdown_move_group") == 1
    assert names.count("spawner") == 4
    assert names.count("static_transform_publisher") == 2
    assert names.count("scene_setup") == 1
    assert "act_command_broker" not in names
    assert "teleop_workflow" not in names and "dynamic_cup_pick_place" not in names
    assert "fixed_cup_pick_place" not in names and "rgbd_cup_pose" not in names
    simulator = next(node for node in nodes if node.node_executable == "ros2_control_node")
    for action in actions[:actions.index(simulator)]:
        if isinstance(action, SetEnvironmentVariable):
            action.execute(context)
    assert context.environment["SO101_ACT_CONTROLLER_RESERVATION_DIR"] == str(
        controller_reservation_directory(tmp_path, "act-task8-case-01"))
    assert context.environment["SO101_ACT_RESERVATION_ROOT"] == str(tmp_path)
    assert context.environment["SO101_SIMULATION_SESSION_ID"] == "act-task8-case-01"
    parameters = evaluate_parameters(context, simulator._Node__parameters)
    robot_description = parameters[0]["robot_description"]
    assert '<param name="disable_rendering">false</param>' in robot_description
    assert "head_camera_frame" in robot_description and "wrist_camera_frame" in robot_description
    plugin = Path(parameters[2])
    assert plugin.name == "mujoco_plugins.yaml" and plugin.parent.name == "act"
    text = plugin.read_text()
    assert "/head_camera/color" in text and "/wrist_camera/color" in text


def test_dedicated_stack_preserves_worker_reservation_scope(tmp_path):
    evidence_root = tmp_path / "diagnostics" / "campaign" / "task8-live" / "stack"
    _, context, opaque = configured(tmp_path, overrides={"task_evidence_root": str(evidence_root)})
    reservation_dir = controller_reservation_directory(tmp_path, "act-task8-case-01")
    context.environment["SO101_ACT_RESERVATION_ROOT"] = str(tmp_path)
    context.environment["SO101_ACT_CONTROLLER_RESERVATION_DIR"] = str(reservation_dir)
    actions = opaque.execute(context)
    for action in actions:
        if isinstance(action, SetEnvironmentVariable):
            action.execute(context)
    assert context.environment["SO101_ACT_CONTROLLER_RESERVATION_DIR"] == str(reservation_dir)
    assert context.environment["SO101_ACT_RESERVATION_ROOT"] == str(tmp_path)


@pytest.mark.parametrize("root, directory", [
    ("outside", "correct"),
    ("correct", "wrong"),
    ("correct", "missing"),
])
def test_dedicated_stack_rejects_inconsistent_worker_reservation_scope(
        tmp_path, monkeypatch, root, directory):
    evidence_root = tmp_path / "diagnostics" / "campaign" / "stack"
    _, context, opaque = configured(tmp_path, overrides={"task_evidence_root": str(evidence_root)})
    reservation_root = tmp_path if root == "correct" else tmp_path.parent / "outside"
    context.environment["SO101_ACT_RESERVATION_ROOT"] = str(reservation_root)
    if directory != "missing":
        context.environment["SO101_ACT_CONTROLLER_RESERVATION_DIR"] = (
            str(controller_reservation_directory(reservation_root, "act-task8-case-01"))
            if directory == "correct" else str(tmp_path / "wrong"))
    made = []
    monkeypatch.setattr(launch, "_mujoco_stack_actions", lambda *args, **kwargs: made.append(True))
    with pytest.raises(RuntimeError, match="ACT_STACK_RESERVATION_SCOPE_INVALID"):
        opaque.execute(context)
    assert made == []


@pytest.mark.parametrize("overrides,reason", [
    ({"headless": "false"}, "ACT_STACK_HEADLESS_REQUIRED"),
    ({"sensor_rendering": "false"}, "ACT_STACK_RGB_REQUIRED"),
    ({"act_profile": "false"}, "ACT_STACK_PROFILE_REQUIRED"),
    ({"session_id": "bad session"}, "ACT_STACK_SESSION_INVALID"),
    ({"task_evidence_root": "relative"}, "ACT_STACK_ROOT_INVALID"),
])
def test_invalid_act_stack_request_refuses_before_graph_construction(tmp_path, monkeypatch, overrides, reason):
    _, context, opaque = configured(tmp_path, overrides=overrides)
    made = []
    monkeypatch.setattr(launch, "_mujoco_stack_actions", lambda *args, **kwargs: made.append(True))
    with pytest.raises(RuntimeError, match=reason):
        opaque.execute(context)
    assert made == []


def test_public_act_execution_stack_launch_is_thin():
    path = Path(__file__).parents[1] / "launch/so101_mujoco_act_execution_stack.launch.py"
    spec = importlib.util.spec_from_file_location("act_execution_stack_launch", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    assert module.generate_launch_description() is not None
