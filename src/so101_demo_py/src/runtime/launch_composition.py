"""Common launch arguments and explicit backend-specific action composition."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    LogInfo,
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

from ..core.policy_registry import load_policy_variant
from .provenance import installed_bundle

COMMON_ARGUMENTS = {
    "run_mode",
    "execute",
    "headless",
    "policy_id",
    "policy_version",
    "session_id",
    "evidence_file",
    "readiness_timeout_s",
}

_CONTROLLERS = ("joint_state_broadcaster", "arm_controller", "gripper_controller")


def _render_mujoco_robot_description(share: Path, scene: str, *, headless: bool) -> str:
    description = (share / "assets/mujoco/so101.urdf").read_text(encoding="utf-8")
    description = description.replace("@SO101_MUJOCO_SCENE@", scene)
    description = description.replace("@SO101_MUJOCO_HEADLESS@", str(headless).lower())
    if "@SO101_" in description:
        raise RuntimeError("unresolved SO-101 URDF launch token")
    return description


def _moveit_parameters(share: Path, robot_description: str) -> dict:
    config = share / "config/mujoco"
    controllers = yaml.safe_load((config / "moveit_controllers.yaml").read_bytes())
    return {
        "robot_description": robot_description,
        "robot_description_semantic": (config / "so101.srdf").read_text(encoding="utf-8"),
        "robot_description_kinematics": yaml.safe_load((config / "kinematics.yaml").read_bytes()),
        "robot_description_planning": yaml.safe_load((config / "joint_limits.yaml").read_bytes()),
        "planning_pipelines": ["ompl"],
        "default_planning_pipeline": "ompl",
        "ompl": yaml.safe_load((config / "ompl_planning.yaml").read_bytes()),
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


def _advance_on_success(event, action, operation: str):
    if event.returncode == 0:
        return [action]
    return [
        EmitEvent(
            event=ShutdownEvent(reason=f"{operation} failed with exit code {event.returncode}")
        )
    ]


def _mujoco_execute_actions(context, share: Path, policy, session_id: str):
    scene = LaunchConfiguration("mujoco_scene").perform(context)
    headless = LaunchConfiguration("headless").perform(context).lower() == "true"
    timeout = LaunchConfiguration("readiness_timeout_s").perform(context)
    evidence_file = Path(LaunchConfiguration("evidence_file").perform(context))
    evidence_root = evidence_file.parent / f"{evidence_file.stem}.d"
    robot_description = _render_mujoco_robot_description(share, scene, headless=headless)
    config = share / "config/mujoco"
    controllers = str(config / "ros2_controllers.yaml")
    parameters = [
        {"use_sim_time": True, "robot_description": robot_description},
        ParameterFile(controllers, allow_substs=False),
        ParameterFile(str(config / "mujoco_plugins.yaml"), allow_substs=False),
        {"simulation_session_id": session_id},
    ]
    robot_state_publisher = Node(
        package="robot_state_publisher",
        executable="robot_state_publisher",
        parameters=[{"use_sim_time": True, "robot_description": robot_description}],
        output="both",
    )
    simulator = Node(
        package="mujoco_ros2_control",
        executable="ros2_control_node",
        parameters=parameters,
        output="both",
        emulate_tty=True,
        on_exit=Shutdown(reason="MuJoCo runtime exited"),
    )
    spawners = [
        Node(
            package="controller_manager",
            executable="spawner",
            arguments=[
                controller,
                "--controller-manager-timeout",
                timeout,
                "--param-file",
                controllers,
            ],
            output="both",
        )
        for controller in _CONTROLLERS
    ]
    move_group = Node(
        package="so101_mujoco_support",
        executable="so101_move_group",
        parameters=[_moveit_parameters(share, robot_description), {"use_sim_time": True}],
        output="both",
    )
    scene_setup = Node(
        package="so101_demo_py",
        executable="scene_setup",
        output="both",
    )
    workflow = Node(
        package="so101_demo_py",
        executable="pick_place",
        arguments=[
            "--backend",
            "mujoco",
            "--run-mode",
            "execute",
            "--execute",
            "--session-id",
            session_id,
            "--expected-reset-epoch",
            "0",
            "--evidence-root",
            str(evidence_root),
            "--motion-policy",
            str(policy.path),
            "--contact-policy",
            str(share / "config/contact_calibration.yaml"),
        ],
        output="both",
    )
    start_workflow = RegisterEventHandler(
        OnProcessExit(
            target_action=scene_setup,
            on_exit=lambda event, context: _advance_on_success(
                event, workflow, "SO-101 Planning Scene setup"
            ),
        )
    )
    shutdown = RegisterEventHandler(
        OnProcessExit(
            target_action=workflow,
            on_exit=[Shutdown(reason="SO-101 workflow complete")],
        )
    )
    return [
        robot_state_publisher,
        simulator,
        *spawners,
        move_group,
        scene_setup,
        start_workflow,
        shutdown,
    ]


def _configured_actions(context, *, backend: str, pick_place: bool):
    run_mode = LaunchConfiguration("run_mode").perform(context)
    execute = LaunchConfiguration("execute").perform(context).lower() == "true"
    if run_mode not in {"dry_run", "execute"}:
        raise RuntimeError(f"unsupported run_mode: {run_mode}")
    if execute != (run_mode == "execute"):
        raise RuntimeError("run_mode execute and execute:=true must be selected together")
    session_id = LaunchConfiguration("session_id").perform(context)
    if not session_id:
        raise RuntimeError("session_id must be non-empty")
    share = Path(get_package_share_directory("so101_demo_py"))
    prefix = Path(get_package_prefix("so101_demo_py"))
    policy = load_policy_variant(
        LaunchConfiguration("policy_id").perform(context),
        LaunchConfiguration("policy_version").perform(context),
        backend,
        share,
    )
    bundle = installed_bundle()
    source_commit = str(bundle.manifest["inputs"]["source_commit"])
    messages = [
        LogInfo(msg=f"so101 backend={backend}"),
        LogInfo(msg=f"so101 source_commit={source_commit}"),
        LogInfo(msg=f"so101 installed_prefix={prefix}"),
        LogInfo(msg=f"so101 policy_sha256={policy.policy_sha256}"),
        LogInfo(msg=f"so101 bundle_sha256={bundle.bundle_sha256}"),
        LogInfo(msg=f"so101 execute={str(execute).lower()} session_id={session_id}"),
        LogInfo(msg=f"so101 ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID', '')}"),
    ]
    if backend == "gazebo":
        messages.append(LogInfo(msg=f"so101 GZ_PARTITION={os.environ.get('GZ_PARTITION', '')}"))
    if run_mode == "dry_run":
        if not pick_place:
            return messages
        workflow = Node(
            package="so101_demo_py",
            executable="pick_place",
            arguments=["--backend", backend, "--run-mode", "dry_run"],
            output="both",
            on_exit=Shutdown(reason="SO-101 dry run complete"),
        )
        return [*messages, workflow]
    if backend == "mujoco":
        return [*messages, *_mujoco_execute_actions(context, share, policy, session_id)]
    raise RuntimeError(f"{backend} execute graph is not registered")


def build_launch_description(*, backend: str, pick_place: bool) -> LaunchDescription:
    if backend not in {"mujoco", "gazebo"}:
        raise ValueError(f"unsupported launch backend: {backend}")
    share = Path(get_package_share_directory("so101_demo_py"))
    unique = uuid.uuid4().hex
    arguments = [
        DeclareLaunchArgument(
            "run_mode", default_value="dry_run", choices=("dry_run", "execute")
        ),
        DeclareLaunchArgument("execute", default_value="false", choices=("true", "false")),
        DeclareLaunchArgument("headless", default_value="true", choices=("true", "false")),
        DeclareLaunchArgument("policy_id", default_value="light_cup_wall_pick"),
        DeclareLaunchArgument("policy_version", default_value="v1"),
        DeclareLaunchArgument("session_id", default_value=unique),
        DeclareLaunchArgument("evidence_file", default_value=f"/tmp/so101-{unique}.json"),
        DeclareLaunchArgument("readiness_timeout_s", default_value="30.0"),
    ]
    if backend == "mujoco":
        arguments.append(
            DeclareLaunchArgument(
                "mujoco_scene", default_value=str(share / "assets/mujoco/scene.xml")
            )
        )
    else:
        arguments.append(
            DeclareLaunchArgument(
                "gazebo_world", default_value=str(share / "assets/gazebo/world.sdf")
            )
        )
    return LaunchDescription(
        [
            *arguments,
            OpaqueFunction(
                function=_configured_actions,
                kwargs={"backend": backend, "pick_place": pick_place},
            ),
        ]
    )
