"""Safe-by-default SO-101 pick/place runtime composition."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction
from launch.conditions import IfCondition
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


_RUNTIME_ARGUMENTS = (
    "run_mode",
    "plan_only_state",
    "stop_after",
    "resume",
    "checkpoint_path",
    "simulation_session_id",
    "object_config",
    "motion_policy",
    "validation_policy",
    "planning_diagnostics_dir",
)


def _runtime_arguments(values):
    """Return tokenized CLI arguments; omit diagnostics tokens when empty."""
    arguments = [
        "--mode", values["run_mode"],
        "--plan-only-state", values["plan_only_state"],
        "--stop-after", values["stop_after"],
        "--resume", values["resume"],
        "--checkpoint", values["checkpoint_path"],
        "--session-id", values["simulation_session_id"],
        "--object-config", values["object_config"],
        "--motion-policy", values["motion_policy"],
        "--validation-policy", values["validation_policy"],
    ]
    if values["planning_diagnostics_dir"]:
        arguments.extend(
            ["--planning-diagnostics-dir", values["planning_diagnostics_dir"]]
        )
    return arguments


def _runtime_node(context):
    values = {
        name: LaunchConfiguration(name).perform(context)
        for name in _RUNTIME_ARGUMENTS
    }
    return [
        Node(
            package="so101_gazebo_demo",
            executable="pick_place_state_machine",
            output="screen",
            arguments=_runtime_arguments(values),
        )
    ]


def generate_launch_description():
    package_share = get_package_share_directory("so101_gazebo_demo")
    run_mode = LaunchConfiguration("run_mode")
    start_simulation = LaunchConfiguration("start_simulation")
    headless = LaunchConfiguration("headless")
    stop_after = LaunchConfiguration("stop_after")
    plan_only_state = LaunchConfiguration("plan_only_state")
    resume = LaunchConfiguration("resume")
    checkpoint_path = LaunchConfiguration("checkpoint_path")
    simulation_session_id = LaunchConfiguration("simulation_session_id")
    object_config = LaunchConfiguration("object_config")
    motion_policy = LaunchConfiguration("motion_policy")
    validation_policy = LaunchConfiguration("validation_policy")

    arguments = [
        DeclareLaunchArgument("run_mode", default_value="dry_run"),
        DeclareLaunchArgument("start_simulation", default_value="false"),
        DeclareLaunchArgument("headless", default_value="false"),
        DeclareLaunchArgument("stop_after", default_value=""),
        DeclareLaunchArgument(
            "plan_only_state",
            default_value="",
            description="See docs/pick-place-launch-parameters.md",
        ),
        DeclareLaunchArgument("resume", default_value="false"),
        DeclareLaunchArgument(
            "checkpoint_path", default_value="/tmp/so101_pick_place_checkpoint.json"
        ),
        DeclareLaunchArgument("simulation_session_id", default_value=""),
        DeclareLaunchArgument("planning_diagnostics_dir", default_value=""),
        DeclareLaunchArgument(
            "object_config",
            default_value=os.path.join(
                package_share, "config", "task_objects", "light_plastic_cup.yaml"
            ),
        ),
        DeclareLaunchArgument(
            "motion_policy",
            default_value=os.path.join(
                package_share, "config", "motion_policies", "light_cup_wall_pick.yaml"
            ),
        ),
        DeclareLaunchArgument(
            "validation_policy",
            default_value=os.path.join(
                package_share,
                "config",
                "validation_policies",
                "light_cup_wall_pick.yaml",
            ),
        ),
    ]
    gazebo = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(package_share, "launch", "so101_gazebo.launch.py")
        ),
        condition=IfCondition(start_simulation),
        launch_arguments={"headless": headless, "object_config": object_config}.items(),
    )
    move_group = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(
            os.path.join(package_share, "launch", "so101_move_group_headless.launch.py")
        ),
        condition=IfCondition(start_simulation),
        launch_arguments={"object_config": object_config}.items(),
    )
    runtime = OpaqueFunction(function=_runtime_node)
    return LaunchDescription([*arguments, gazebo, move_group, runtime])
