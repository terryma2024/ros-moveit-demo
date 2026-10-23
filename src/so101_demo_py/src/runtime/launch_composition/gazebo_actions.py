"""Launch actions of the Gazebo model and its execution."""

from __future__ import annotations

import os
from pathlib import Path

from ament_index_python.packages import get_package_share_directory
from launch.actions import (
    IncludeLaunchDescription,
    OpaqueFunction,
    RegisterEventHandler,
    SetEnvironmentVariable,
    Shutdown,
    TimerAction,
)
from launch.event_handlers import OnProcessExit
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue

from so101_demo.runtime.launch_composition.common import _CONTROLLERS, _advance_on_success
from so101_demo.runtime.launch_composition.mujoco_actions import _moveit_parameters


def _materialize_gazebo_model(context, share: Path):
    from so101_demo.backends.gazebo.model_asset import materialize_prepared_model

    output_root = Path(os.environ.get("ROS_LOG_DIR", "/tmp"))
    runtime_model = output_root / f"so101-unified-prepared-{os.getpid()}.sdf"
    materialize_prepared_model(
        share / "assets/gazebo/so101_prepared.sdf",
        share,
        runtime_model,
    )
    return [
        Node(
            package="ros_gz_sim",
            executable="create",
            arguments=["-file", str(runtime_model), "-name", "so101"],
            output="both",
        )
    ]


def _gazebo_execute_actions(
    context,
    share: Path,
    policy,
    bundle,
    session_id: str,
    *,
    include_workflow: bool,
):
    world = LaunchConfiguration("gazebo_world").perform(context)
    headless = LaunchConfiguration("headless").perform(context).lower() == "true"
    timeout = LaunchConfiguration("readiness_timeout_s").perform(context)
    evidence_file = LaunchConfiguration("evidence_file").perform(context)
    ros_gz_share = Path(get_package_share_directory("ros_gz_sim"))
    gz_args = f"{'-s ' if headless else ''}-v 4 -r --physics-engine gz-physics-bullet-featherstone-plugin {world}"
    simulator = IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(ros_gz_share / "launch/gz_sim.launch.py")),
        launch_arguments={"gz_args": gz_args}.items(),
    )
    xacro = share / "assets/gazebo/urdf/so101.urdf.xacro"
    robot_description = ParameterValue(
        Command(
            [
                "xacro ",
                str(xacro),
                " base_height:=0.1899186 use_gazebo:=true gazebo_collision_primitives:=true",
            ]
        ),
        value_type=str,
    )
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"robot_description": robot_description, "use_sim_time": True}],
        output="both",
    )
    bridge = Node(
        package="ros_gz_bridge",
        executable="parameter_bridge",
        arguments=[
            "/clock@rosgraph_msgs/msg/Clock[gz.msgs.Clock",
            "/world/so101_pick_place/pose/info@tf2_msgs/msg/TFMessage[gz.msgs.Pose_V",
            "/world/so101_pick_place/stats@ros_gz_interfaces/msg/WorldStatistics[gz.msgs.WorldStatistics",
        ],
        remappings=[
            ("/world/so101_pick_place/pose/info", "/so101/gazebo_pose_info"),
            ("/world/so101_pick_place/stats", "/so101/gazebo_world_stats"),
        ],
        output="both",
    )
    spawn = TimerAction(
        period=3.0,
        actions=[OpaqueFunction(function=_materialize_gazebo_model, args=[share]), bridge],
    )
    controllers = TimerAction(
        period=8.0,
        actions=[
            Node(
                package="controller_manager",
                executable="spawner",
                arguments=[
                    name,
                    "--controller-manager",
                    "/controller_manager",
                    "--switch-timeout",
                    timeout,
                    "--param-file",
                    str(share / "config/so101_controllers.yaml"),
                ],
                output="both",
            )
            for name in _CONTROLLERS
        ],
    )
    moveit = _moveit_parameters(share, robot_description)
    move_group = TimerAction(
        period=8.0,
        actions=[
            Node(
                package="moveit_ros_move_group",
                executable="move_group",
                parameters=[moveit, {"use_sim_time": True}],
                output="both",
            )
        ],
    )
    workflow = Node(
        package="so101_demo_py",
        executable="gazebo_execute",
        arguments=[
            "--session-id",
            session_id,
            "--policy",
            str(policy.path),
            "--result",
            evidence_file,
            *(
                ("--source-commit", str(bundle.manifest["inputs"]["source_commit"]))
                if bundle.manifest["inputs"].get("source_commit") is not None
                else ()
            ),
            *(
                ("--installed-prefix", str(bundle.manifest["inputs"]["package_prefix"]))
                if bundle.manifest["inputs"].get("package_prefix") is not None
                else ()
            ),
            "--policy-sha256",
            policy.policy_sha256,
            "--bundle-sha256",
            bundle.bundle_sha256,
            "--readiness-timeout-s",
            timeout,
        ],
        output="both",
    )
    readiness = Node(
        package="so101_demo_py",
        executable="motion_stack_ready",
        arguments=["--timeout-s", timeout],
        output="both",
    )
    delayed_readiness = TimerAction(period=8.0, actions=[readiness])
    scene_setup = Node(
        package="so101_demo_py",
        executable="scene_setup",
        arguments=["--backend", "gazebo"],
        parameters=[{"readiness_timeout_s": float(timeout)}],
        output="both",
    )
    start_scene = RegisterEventHandler(
        OnProcessExit(
            target_action=readiness,
            on_exit=lambda event, context: _advance_on_success(
                event, scene_setup, "Gazebo readiness"
            ),
        )
    )
    start_workflow = RegisterEventHandler(
        OnProcessExit(
            target_action=scene_setup,
            on_exit=lambda event, context: _advance_on_success(
                event, workflow, "Gazebo Planning Scene setup"
            ),
        )
    )
    shutdown = RegisterEventHandler(
        OnProcessExit(target_action=workflow, on_exit=[Shutdown(reason="Gazebo execute complete")])
    )
    actions = [
        SetEnvironmentVariable("GZ_SIM_RESOURCE_PATH", str(share.parent)),
        simulator,
        robot_state_publisher,
        spawn,
        controllers,
        move_group,
    ]
    if include_workflow:
        actions.extend((delayed_readiness, start_scene, start_workflow, shutdown))
    return actions
