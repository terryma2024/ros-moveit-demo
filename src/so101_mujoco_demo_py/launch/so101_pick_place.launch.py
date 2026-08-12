#!/usr/bin/env python3
"""One owned headless MuJoCo, ros2_control, MoveIt, and workflow composition."""

import uuid
from dataclasses import dataclass
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_share_directory
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    OpaqueFunction,
    RegisterEventHandler,
    Shutdown,
)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown as ShutdownEvent
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile

from launch import LaunchDescription

PACKAGE_NAME = "so101_mujoco_demo_py"
CONTROLLERS = ("joint_state_broadcaster", "arm_controller", "gripper_controller")


def actions_after_success_or_shutdown(event, success_actions, operation: str):
    """Advance a launch stage only when its prerequisite exited successfully."""

    if event.returncode == 0:
        return success_actions
    reason = f"{operation} failed with exit code {event.returncode}"
    return [EmitEvent(event=ShutdownEvent(reason=reason))]


@dataclass(frozen=True, slots=True)
class LaunchComposition:
    actions: tuple
    node_executables: set[tuple[str, str]]
    controller_spawners: set[str]
    includes_robot_description: bool
    includes_planning_scene: bool
    includes_observer: bool
    includes_reset_services: bool
    includes_workflow: bool
    shutdown_on_workflow_exit: bool


def render_robot_description(package_root: Path, *, headless: bool) -> str:
    description = (package_root / "urdf/so101.urdf").read_text(encoding="utf-8")
    description = description.replace("@SO101_MUJOCO_SCENE@", str(package_root / "mjcf/scene.xml"))
    description = description.replace("@SO101_MUJOCO_HEADLESS@", str(headless).lower())
    if "@SO101_" in description:
        raise RuntimeError("unresolved SO-101 URDF launch token")
    return description


def moveit_parameters(package_root: Path, robot_description: str) -> dict:
    kinematics = yaml.safe_load(
        (package_root / "config/kinematics.yaml").read_text(encoding="utf-8")
    )
    controllers = yaml.safe_load(
        (package_root / "config/moveit_controllers.yaml").read_text(encoding="utf-8")
    )
    joint_limits = yaml.safe_load(
        (package_root / "config/joint_limits.yaml").read_text(encoding="utf-8")
    )
    ompl = yaml.safe_load((package_root / "config/ompl_planning.yaml").read_text(encoding="utf-8"))
    return {
        "robot_description": robot_description,
        "robot_description_semantic": (package_root / "config/so101.srdf").read_text(
            encoding="utf-8"
        ),
        "robot_description_kinematics": kinematics,
        "robot_description_planning": joint_limits,
        "planning_pipelines": ["ompl"],
        "default_planning_pipeline": "ompl",
        "ompl": ompl,
        **controllers,
        "moveit_manage_controllers": True,
        "publish_robot_description": True,
        "publish_robot_description_semantic": True,
        "publish_planning_scene": True,
        "publish_geometry_updates": True,
        "publish_state_updates": True,
        "publish_transforms_updates": True,
        "trajectory_execution.allowed_execution_duration_scaling": 1.5,
        "trajectory_execution.allowed_goal_duration_margin": 1.0,
    }


def compose_launch(
    package_root: Path,
    *,
    run_mode: str,
    execute: bool,
    headless: bool,
    start_simulation: bool,
    simulation_session_id: str,
    evidence_file: str,
    safe_pose: str,
    readiness_timeout_s: float,
    launch_workflow: bool = True,
) -> LaunchComposition:
    if run_mode not in {"dry_run", "execute"}:
        raise RuntimeError(f"unsupported run_mode: {run_mode}")
    if execute != (run_mode == "execute"):
        raise RuntimeError("run_mode execute and execute:=true must be selected together")
    if not simulation_session_id:
        raise RuntimeError("simulation_session_id must be non-empty")

    robot_description = render_robot_description(package_root, headless=headless)
    controller_file = str(package_root / "config/ros2_controllers.yaml")
    plugin_file = str(package_root / "config/mujoco_plugins.yaml")
    common_parameters = [
        {"use_sim_time": True, "robot_description": robot_description},
        ParameterFile(controller_file, allow_substs=False),
        ParameterFile(plugin_file, allow_substs=False),
        {"simulation_session_id": simulation_session_id},
    ]
    nodes: list[Node] = []
    controller_spawners: set[str] = set()
    if start_simulation:
        nodes.extend(
            [
                Node(
                    package="robot_state_publisher",
                    executable="robot_state_publisher",
                    parameters=[{"use_sim_time": True, "robot_description": robot_description}],
                    output="both",
                ),
                Node(
                    package="mujoco_ros2_control",
                    executable="ros2_control_node",
                    parameters=common_parameters,
                    output="both",
                    emulate_tty=True,
                    on_exit=Shutdown(reason="MuJoCo runtime exited"),
                ),
            ]
        )
        for controller in CONTROLLERS:
            nodes.append(
                Node(
                    package="controller_manager",
                    executable="spawner",
                    arguments=[
                        controller,
                        "--controller-manager-timeout",
                        str(readiness_timeout_s),
                        "--param-file",
                        controller_file,
                    ],
                    output="both",
                )
            )
            controller_spawners.add(controller)

    move_group = Node(
        package="so101_mujoco_support",
        executable="so101_move_group",
        parameters=[moveit_parameters(package_root, robot_description), {"use_sim_time": True}],
        output="both",
    )
    nodes.append(move_group)
    scene_setup = Node(
        package=PACKAGE_NAME,
        executable="scene_setup",
        parameters=[
            {
                "use_sim_time": True,
                "readiness_timeout_s": readiness_timeout_s,
            }
        ],
        output="both",
    )
    nodes.append(scene_setup)
    workflow_arguments = [
        "--run-mode",
        run_mode,
        "--simulation-session-id",
        simulation_session_id,
        "--safe-pose",
        safe_pose,
        "--config",
        str(package_root / "config/headless_execution.yaml"),
        "--evidence-file",
        evidence_file,
        "--readiness-timeout-s",
        str(readiness_timeout_s),
    ]
    if execute:
        workflow_arguments.append("--execute")
    workflow = Node(
        package=PACKAGE_NAME,
        executable="headless_execution",
        arguments=workflow_arguments,
        parameters=[{"use_sim_time": True}],
        output="both",
    )
    all_nodes = (*nodes, workflow) if launch_workflow else tuple(nodes)
    if launch_workflow:
        start_workflow_after_scene = RegisterEventHandler(
            OnProcessExit(
                target_action=scene_setup,
                on_exit=lambda event, context: actions_after_success_or_shutdown(
                    event,
                    [workflow],
                    "SO-101 MuJoCo Planning Scene setup",
                ),
            )
        )
        shutdown = RegisterEventHandler(
            OnProcessExit(
                target_action=workflow,
                on_exit=[Shutdown(reason="headless workflow complete")],
            )
        )
        # The workflow is absent from root actions: scene setup owns its gate.
        actions = (*nodes, start_workflow_after_scene, shutdown)
    else:
        # Interactive owners keep the stack alive after scene setup exits.
        actions = tuple(nodes)
    return LaunchComposition(
        actions=actions,
        node_executables={(node.node_package, node.node_executable) for node in all_nodes},
        controller_spawners=controller_spawners,
        includes_robot_description=True,
        includes_planning_scene=(
            (scene_setup.node_package, scene_setup.node_executable) == (PACKAGE_NAME, "scene_setup")
            and workflow not in actions
        ),
        includes_observer=start_simulation,
        includes_reset_services=start_simulation,
        includes_workflow=launch_workflow,
        shutdown_on_workflow_exit=launch_workflow,
    )


def launch_setup(context):
    package_root = Path(get_package_share_directory(PACKAGE_NAME))
    run_mode = LaunchConfiguration("run_mode").perform(context)
    execute = LaunchConfiguration("execute").perform(context).lower() == "true"
    composition = compose_launch(
        package_root,
        run_mode=run_mode,
        execute=execute,
        headless=LaunchConfiguration("headless").perform(context).lower() == "true",
        start_simulation=(
            LaunchConfiguration("start_simulation").perform(context).lower() == "true"
        ),
        simulation_session_id=LaunchConfiguration("simulation_session_id").perform(context),
        evidence_file=LaunchConfiguration("evidence_file").perform(context),
        safe_pose=LaunchConfiguration("safe_pose").perform(context),
        readiness_timeout_s=float(LaunchConfiguration("readiness_timeout_s").perform(context)),
        launch_workflow=(LaunchConfiguration("launch_workflow").perform(context).lower() == "true"),
    )
    return list(composition.actions)


def generate_launch_description() -> LaunchDescription:
    unique = uuid.uuid4().hex
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "run_mode", default_value="dry_run", choices=["dry_run", "execute"]
            ),
            DeclareLaunchArgument("execute", default_value="false", choices=["true", "false"]),
            DeclareLaunchArgument("headless", default_value="true", choices=["true", "false"]),
            DeclareLaunchArgument(
                "start_simulation", default_value="true", choices=["true", "false"]
            ),
            DeclareLaunchArgument(
                "launch_workflow", default_value="true", choices=["true", "false"]
            ),
            DeclareLaunchArgument("safe_pose", default_value="task12_safe"),
            DeclareLaunchArgument("contact_policy", default_value=""),
            DeclareLaunchArgument("readiness_timeout_s", default_value="30.0"),
            DeclareLaunchArgument("simulation_session_id", default_value=unique),
            DeclareLaunchArgument(
                "evidence_file", default_value=f"/tmp/so101-headless-{unique}.json"
            ),
            OpaqueFunction(function=launch_setup),
        ]
    )
