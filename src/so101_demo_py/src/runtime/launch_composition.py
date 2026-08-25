"""Common launch arguments and explicit backend-specific action composition."""

from __future__ import annotations

import os
import re
import stat
import uuid
from dataclasses import dataclass
from math import isfinite
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
from .camera_tf import camera_static_transform_nodes
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

MUJOCO_CUP_KEYFRAMES = (
    "task_start",
    "cup_test_forward_5cm",
    "cup_test_left_5cm",
    "cup_test_right_5cm",
)

_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True, slots=True)
class _MujocoStackActions:
    actions: tuple
    scene_setup: Node


@dataclass(slots=True)
class PerceptionLaunchExitStatus:
    """First terminal child status observed by the perception launch graph."""

    returncode: int | None = None

    def record(self, returncode: int) -> None:
        if self.returncode is None:
            self.returncode = returncode

    def resolve(self, launch_service_returncode: int) -> int:
        if self.returncode is None:
            return launch_service_returncode
        return self.returncode


def _render_mujoco_robot_description(
    share: Path,
    scene: str,
    *,
    headless: bool,
    initial_keyframe: str = "task_start",
    platform_name: str | None = None,
) -> str:
    if initial_keyframe not in MUJOCO_CUP_KEYFRAMES:
        raise RuntimeError(f"unsupported MuJoCo initial keyframe: {initial_keyframe}")
    description = (share / "assets/mujoco/so101.urdf").read_text(encoding="utf-8")
    description = description.replace("@SO101_MUJOCO_SCENE@", scene)
    description = description.replace("@SO101_MUJOCO_INITIAL_KEYFRAME@", initial_keyframe)
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


def _mujoco_stack_actions(context, share: Path, session_id: str) -> _MujocoStackActions:
    scene = LaunchConfiguration("mujoco_scene").perform(context)
    initial_keyframe = LaunchConfiguration("mujoco_initial_keyframe").perform(context)
    headless = LaunchConfiguration("headless").perform(context).lower() == "true"
    timeout = LaunchConfiguration("readiness_timeout_s").perform(context)
    robot_description = _render_mujoco_robot_description(
        share,
        scene,
        headless=headless,
        initial_keyframe=initial_keyframe,
    )
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
    return _MujocoStackActions(
        actions=(
            robot_state_publisher,
            simulator,
            *spawners,
            move_group,
            scene_setup,
        ),
        scene_setup=scene_setup,
    )


def _mujoco_execute_actions(
    context, share: Path, policy, session_id: str, *, include_workflow: bool
):
    evidence_file = Path(LaunchConfiguration("evidence_file").perform(context))
    evidence_root = evidence_file.parent / f"{evidence_file.stem}.d"
    stack = _mujoco_stack_actions(context, share, session_id)
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
            target_action=stack.scene_setup,
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
    actions = list(stack.actions)
    if include_workflow:
        actions.extend((start_workflow, shutdown))
    return actions


def _raise_launch_failure(_context, message: str):
    raise RuntimeError(message)


def _terminal_launch_actions(reason: str, *, failed: bool):
    actions = [EmitEvent(event=ShutdownEvent(reason=reason))]
    if failed:
        actions.append(OpaqueFunction(function=_raise_launch_failure, args=[reason]))
    return actions


def perception_pick_place_exit_handlers(
    scene_setup,
    perception,
    workflow,
    *,
    exit_status: PerceptionLaunchExitStatus,
):
    """Create the shared fail-closed process policy for production and tests."""

    state = {"workflow_exited": False}

    def on_scene_exit(event, _context):
        if event.returncode == 0:
            return [perception, workflow]
        exit_status.record(event.returncode)
        reason = (
            "SO-101 Planning Scene setup failed with exit code "
            f"{event.returncode}"
        )
        return _terminal_launch_actions(reason, failed=True)

    def on_perception_exit(event, _context):
        if state["workflow_exited"]:
            return []
        exit_status.record(event.returncode if event.returncode != 0 else 1)
        reason = (
            "RGB-D perception exited before dynamic workflow completed with exit code "
            f"{event.returncode}"
        )
        return _terminal_launch_actions(reason, failed=True)

    def on_workflow_exit(event, _context):
        state["workflow_exited"] = True
        exit_status.record(event.returncode)
        outcome = "completed" if event.returncode == 0 else "failed"
        reason = (
            f"Dynamic perception workflow {outcome} with exit code {event.returncode}"
        )
        return _terminal_launch_actions(reason, failed=event.returncode != 0)

    return (
        RegisterEventHandler(
            OnProcessExit(target_action=scene_setup, on_exit=on_scene_exit)
        ),
        RegisterEventHandler(
            OnProcessExit(target_action=perception, on_exit=on_perception_exit)
        ),
        RegisterEventHandler(
            OnProcessExit(target_action=workflow, on_exit=on_workflow_exit)
        ),
    )


def _mujoco_perception_execute_actions(
    context,
    share: Path,
    session_id: str,
    *,
    evidence_root: Path,
    perception_timeout: str,
    cup_pose_timeout: str,
    exit_status: PerceptionLaunchExitStatus,
):
    stack = _mujoco_stack_actions(context, share, session_id)
    perception = Node(
        package="so101_demo_py",
        executable="rgbd_cup_pose",
        arguments=[
            "--startup-timeout-s",
            perception_timeout,
            "--output-topic",
            "/cup_pose",
            "--output-ply",
            str(evidence_root / "perception/cup.ply"),
            "--evidence-json",
            str(evidence_root / "perception/summary.json"),
        ],
        parameters=[{"use_sim_time": True}],
        output="both",
    )
    workflow = Node(
        package="so101_demo_py",
        executable="dynamic_cup_pick_place",
        arguments=[
            "--backend",
            "mujoco",
            "--mode",
            "execute",
            "--execute",
            "--cup-pose-timeout-s",
            cup_pose_timeout,
            "--scene-source",
            "observe_only",
            "--session-id",
            session_id,
            "--expected-reset-epoch",
            "0",
            "--evidence-root",
            str(evidence_root / "dynamic"),
        ],
        output="both",
    )
    handlers = perception_pick_place_exit_handlers(
        stack.scene_setup,
        perception,
        workflow,
        exit_status=exit_status,
    )
    return [
        *handlers,
        *camera_static_transform_nodes(),
        *stack.actions,
    ]


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


def _positive_finite_launch_value(context, name: str) -> str:
    value = LaunchConfiguration(name).perform(context)
    try:
        parsed = float(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be finite and positive") from error
    if not isfinite(parsed) or parsed <= 0.0:
        raise RuntimeError(f"{name} must be finite and positive")
    return value


def _owned_directory(path: Path, label: str) -> Path:
    try:
        path.mkdir(mode=0o700)
    except FileExistsError:
        pass
    metadata = path.lstat()
    if stat.S_ISLNK(metadata.st_mode):
        raise RuntimeError(f"{label} must not be a symlink: {path}")
    if not stat.S_ISDIR(metadata.st_mode):
        raise RuntimeError(f"{label} must be a directory: {path}")
    if metadata.st_uid != os.geteuid():
        raise RuntimeError(f"{label} must be owned by the current user: {path}")
    return path.resolve(strict=True)


def _prepare_perception_evidence_root(
    evidence_file: Path, session_id: str
) -> Path:
    try:
        evidence_parent = evidence_file.parent.resolve(strict=True)
    except FileNotFoundError as error:
        raise RuntimeError("evidence_file parent directory must exist") from error
    if not evidence_parent.is_dir():
        raise RuntimeError("evidence_file parent must be a directory")

    base = evidence_parent / f"{evidence_file.stem}.d"
    resolved_base = _owned_directory(base, "derived evidence root")
    if resolved_base.parent != evidence_parent:
        raise RuntimeError("derived evidence root escapes evidence_file parent")

    run_root = resolved_base / session_id
    resolved_run_root = _owned_directory(run_root, "session evidence root")
    if resolved_run_root.parent != resolved_base:
        raise RuntimeError("session evidence root escapes derived evidence root")
    return resolved_run_root


def _configured_perception_pick_place_actions(
    context, *, exit_status: PerceptionLaunchExitStatus
):
    run_mode = LaunchConfiguration("run_mode").perform(context)
    execute = LaunchConfiguration("execute").perform(context)
    headless = LaunchConfiguration("headless").perform(context)
    if run_mode != "execute":
        raise RuntimeError("perception pick-place requires run_mode=execute")
    if execute != "true":
        raise RuntimeError("perception pick-place requires execute:=true")
    if headless not in {"true", "false"}:
        raise RuntimeError("headless must be true or false")

    initial_keyframe = LaunchConfiguration("mujoco_initial_keyframe").perform(context)
    if initial_keyframe not in MUJOCO_CUP_KEYFRAMES:
        raise RuntimeError(f"unsupported MuJoCo initial keyframe: {initial_keyframe}")

    _positive_finite_launch_value(context, "readiness_timeout_s")
    perception_timeout = _positive_finite_launch_value(
        context, "perception_startup_timeout_s"
    )
    cup_pose_timeout = _positive_finite_launch_value(context, "cup_pose_timeout_s")

    session_id = LaunchConfiguration("session_id").perform(context)
    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise RuntimeError(
            "session_id must start with an alphanumeric character and contain only "
            "letters, digits, dot, underscore, or hyphen"
        )

    evidence_file = Path(LaunchConfiguration("evidence_file").perform(context))
    if not evidence_file.is_absolute() or evidence_file.name in {"", ".", ".."}:
        raise RuntimeError("evidence_file must be a usable absolute file path")
    if evidence_file.exists() and not evidence_file.is_file():
        raise RuntimeError("evidence_file must identify a file, not a directory")
    scene = Path(LaunchConfiguration("mujoco_scene").perform(context))
    if not scene.is_absolute():
        raise RuntimeError("mujoco_scene must be an absolute file path")
    if not scene.is_file():
        raise RuntimeError(f"mujoco_scene does not exist: {scene}")

    share = Path(get_package_share_directory("so101_demo_py"))
    evidence_root = _prepare_perception_evidence_root(evidence_file, session_id)
    return _mujoco_perception_execute_actions(
        context,
        share,
        session_id,
        evidence_root=evidence_root,
        perception_timeout=perception_timeout,
        cup_pose_timeout=cup_pose_timeout,
        exit_status=exit_status,
    )


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
        arguments.extend(
            (
                DeclareLaunchArgument(
                    "mujoco_scene", default_value=str(share / "assets/mujoco/scene.xml")
                ),
                DeclareLaunchArgument(
                    "mujoco_initial_keyframe",
                    default_value="task_start",
                    choices=MUJOCO_CUP_KEYFRAMES,
                ),
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


def build_perception_pick_place_launch_description(
    exit_status: PerceptionLaunchExitStatus | None = None,
) -> LaunchDescription:
    """Build the explicit MuJoCo RGB-D-driven execute graph."""

    share = Path(get_package_share_directory("so101_demo_py"))
    unique = uuid.uuid4().hex
    if exit_status is None:
        exit_status = PerceptionLaunchExitStatus()
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "run_mode", default_value="dry_run", choices=("dry_run", "execute")
            ),
            DeclareLaunchArgument(
                "execute", default_value="false", choices=("true", "false")
            ),
            DeclareLaunchArgument(
                "headless", default_value="false", choices=("true", "false")
            ),
            DeclareLaunchArgument("session_id", default_value=unique),
            DeclareLaunchArgument(
                "evidence_file", default_value=f"/tmp/so101-perception-{unique}.json"
            ),
            DeclareLaunchArgument("readiness_timeout_s", default_value="90.0"),
            DeclareLaunchArgument(
                "mujoco_scene",
                default_value=str(share / "assets/mujoco/scene.xml"),
            ),
            DeclareLaunchArgument(
                "mujoco_initial_keyframe",
                default_value="task_start",
                choices=MUJOCO_CUP_KEYFRAMES,
            ),
            DeclareLaunchArgument(
                "perception_startup_timeout_s", default_value="30.0"
            ),
            DeclareLaunchArgument("cup_pose_timeout_s", default_value="45.0"),
            OpaqueFunction(
                function=_configured_perception_pick_place_actions,
                kwargs={"exit_status": exit_status},
            ),
        ]
    )
