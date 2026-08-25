"""Common launch arguments and explicit backend-specific action composition."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
    RegisterEventHandler,
    SetEnvironmentVariable,
    Shutdown,
    TimerAction,
)
from launch.event_handlers import OnProcessExit
from launch.events import Shutdown as ShutdownEvent
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile, ParameterValue

from launch import LaunchDescription

from ..core.policy_registry import load_policy_variant
from ..ports.capabilities import CapabilityRequirements
from .composition import backend_capabilities
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


def _render_mujoco_robot_description(
    share: Path, scene: str, *, headless: bool, platform_name: str | None = None
) -> str:
    description = (share / "assets/mujoco/so101.urdf").read_text(encoding="utf-8")
    description = description.replace("@SO101_MUJOCO_SCENE@", scene)
    description = description.replace("@SO101_MUJOCO_HEADLESS@", str(headless).lower())
    # Interactive Darwin launches use the fork's main-thread-owned GLFW context
    # path.  Only an explicitly headless launch suppresses camera rendering.
    disable_rendering = headless
    description = description.replace(
        "@SO101_MUJOCO_DISABLE_RENDERING@", str(disable_rendering).lower()
    )
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


def _mujoco_execute_actions(
    context, share: Path, policy, session_id: str, *, include_workflow: bool
):
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
        parameters=[{"readiness_timeout_s": float(timeout)}],
        output="both",
    )
    workflow = Node(
        package="so101_demo_py",
        executable="fixed_cup_pick_place",
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
    actions = [
        robot_state_publisher,
        simulator,
        *spawners,
        move_group,
        scene_setup,
    ]
    if include_workflow:
        actions.extend((start_workflow, shutdown))
    return actions


def _materialize_gazebo_model(context, share: Path):
    from ..backends.gazebo.model_asset import materialize_prepared_model

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
            "--source-commit",
            str(bundle.manifest["inputs"]["source_commit"]),
            "--installed-prefix",
            str(bundle.manifest["inputs"]["package_prefix"]),
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
        executable="gazebo_ready",
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
    capabilities = backend_capabilities(backend)
    base_capabilities = CapabilityRequirements.base_execute().validate(capabilities)
    source_commit = str(bundle.manifest["inputs"]["source_commit"])
    messages = [
        LogInfo(msg=f"so101 backend={backend}"),
        LogInfo(msg=f"so101 source_commit={source_commit}"),
        LogInfo(msg=f"so101 installed_prefix={prefix}"),
        LogInfo(msg=f"so101 policy_sha256={policy.policy_sha256}"),
        LogInfo(msg=f"so101 bundle_sha256={bundle.bundle_sha256}"),
        LogInfo(msg=f"so101 execute={str(execute).lower()} session_id={session_id}"),
        LogInfo(
            msg="so101 base_execute_capabilities="
            + ("accepted" if base_capabilities.accepted else "rejected")
        ),
        LogInfo(
            msg="so101 lossless_physics_step_trace="
            + str(capabilities.lossless_physics_step_trace).lower()
        ),
        LogInfo(msg=f"so101 ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID', '')}"),
    ]
    if backend == "gazebo":
        messages.append(LogInfo(msg=f"so101 GZ_PARTITION={os.environ.get('GZ_PARTITION', '')}"))
    if run_mode == "dry_run":
        if not pick_place:
            return messages
        workflow = Node(
            package="so101_demo_py",
            executable="fixed_cup_pick_place",
            arguments=["--backend", backend, "--run-mode", "dry_run"],
            output="both",
            on_exit=Shutdown(reason="SO-101 dry run complete"),
        )
        return [*messages, workflow]
    if backend == "mujoco":
        return [
            *messages,
            *_mujoco_execute_actions(
                context, share, policy, session_id, include_workflow=pick_place
            ),
        ]
    if backend == "gazebo":
        return [
            *messages,
            *_gazebo_execute_actions(
                context,
                share,
                policy,
                bundle,
                session_id,
                include_workflow=pick_place,
            ),
        ]
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
        DeclareLaunchArgument("readiness_timeout_s", default_value="90.0"),
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
