"""Common launch arguments and explicit backend-specific action composition."""

from __future__ import annotations

import os
import platform
import re
import stat
import uuid
from dataclasses import dataclass
from functools import partial
from math import isfinite
from pathlib import Path

import yaml
from ament_index_python.packages import get_package_prefix, get_package_share_directory
from launch.actions import (
    DeclareLaunchArgument,
    EmitEvent,
    ExecuteProcess,
    IncludeLaunchDescription,
    LogInfo,
    OpaqueFunction,
    RegisterEventHandler,
    SetEnvironmentVariable,
    Shutdown,
    TimerAction,
)
from launch.event_handlers import OnProcessExit, OnProcessStart
from launch.events import Shutdown as ShutdownEvent
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile, ParameterValue

from launch import LaunchDescription

from ..core.policy_registry import load_policy_variant
from ..ports.capabilities import CapabilityRequirements
from ..profiling.launch_support import (
    LaunchProfilingSession,
    profiling_event_handlers,
    resolve_launch_profiling,
    validate_launch_profiling_values,
)
from .camera_tf import camera_static_transform_nodes
from .composition import backend_capabilities
from .provenance import (
    InstalledExecutionIdentity,
    installed_bundle,
    resolve_installed_execution_identity,
)

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
    "v5_no_cup",
    "v5_two_cups",
    "v5_cup_near_bottle",
)

_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_DEFAULT_YOLO_INFERENCE_IMAGE = (
    "so101-yolo11n-seg-inference:"
    "ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115"
)
_GROUNDED_SAM_THRESHOLD_DEFAULTS = (
    ("grounding_box_threshold", "0.35"),
    ("grounding_text_threshold", "0.25"),
    ("grounding_duplicate_iou", "0.85"),
    ("grounding_max_candidates", "16"),
    ("sam_mask_quality_threshold", "0.75"),
    ("sam_min_mask_pixels", "64"),
    ("sam_max_mask_area_ratio", "0.50"),
)


@dataclass(frozen=True, slots=True)
class _MujocoStackActions:
    robot_state_publisher: Node
    simulator: Node
    spawners: tuple[Node, ...]
    move_group: Node
    scene_setup: Node

    @property
    def actions(self) -> tuple:
        return (
            self.robot_state_publisher,
            self.simulator,
            *self.spawners,
            self.move_group,
            self.scene_setup,
        )


@dataclass(frozen=True, slots=True)
class _PerceptionEvidencePaths:
    run_root: Path
    perception: Path
    dynamic: Path


@dataclass(slots=True)
class PerceptionLaunchExitStatus:
    """First terminal child status observed by the perception launch graph."""

    returncode: int | None = None
    workflow_terminal: bool = False

    def record(self, returncode: int) -> None:
        if self.returncode is None:
            self.returncode = returncode

    def mark_workflow_terminal(self) -> None:
        self.workflow_terminal = True

    def resolve(self, launch_service_returncode: int) -> int:
        if self.returncode in {None, 0}:
            return launch_service_returncode
        return self.returncode


def _render_mujoco_robot_description(
    share: Path,
    scene: str,
    *,
    headless: bool,
    sensor_rendering: bool | None = None,
    sim_speed_factor: float = -1.0,
    initial_keyframe: str = "task_start",
    platform_name: str | None = None,
) -> str:
    if initial_keyframe not in MUJOCO_CUP_KEYFRAMES:
        raise RuntimeError(f"unsupported MuJoCo initial keyframe: {initial_keyframe}")
    if not isfinite(sim_speed_factor) or (
        sim_speed_factor != -1.0 and sim_speed_factor <= 0.0
    ):
        raise RuntimeError("sim_speed_factor must be -1.0 or finite and positive")
    description = (share / "assets/mujoco/so101.urdf").read_text(encoding="utf-8")
    description = description.replace("@SO101_MUJOCO_SCENE@", scene)
    description = description.replace("@SO101_MUJOCO_INITIAL_KEYFRAME@", initial_keyframe)
    description = description.replace("@SO101_MUJOCO_HEADLESS@", str(headless).lower())
    # Preserve the historical generic behavior when no independent policy is
    # supplied. RGB-D launches explicitly keep rendering enabled in headless mode.
    if sensor_rendering is None:
        sensor_rendering = not headless
    disable_rendering = not sensor_rendering
    description = description.replace(
        "@SO101_MUJOCO_DISABLE_RENDERING@", str(disable_rendering).lower()
    )
    description = description.replace(
        "@SO101_MUJOCO_SIM_SPEED_FACTOR@", str(sim_speed_factor)
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


def _mujoco_stack_actions(
    context,
    share: Path,
    session_id: str,
    *,
    sim_speed_factor: float = -1.0,
) -> _MujocoStackActions:
    scene = LaunchConfiguration("mujoco_scene").perform(context)
    initial_keyframe = LaunchConfiguration("mujoco_initial_keyframe").perform(context)
    headless = LaunchConfiguration("headless").perform(context).lower() == "true"
    sensor_rendering_value = context.launch_configurations.get("sensor_rendering", "auto")
    if sensor_rendering_value == "auto":
        sensor_rendering = not headless
    elif sensor_rendering_value in {"true", "false"}:
        sensor_rendering = sensor_rendering_value == "true"
    else:
        raise RuntimeError("sensor_rendering must be auto, true, or false")
    timeout = LaunchConfiguration("readiness_timeout_s").perform(context)
    robot_description = _render_mujoco_robot_description(
        share,
        scene,
        headless=headless,
        sensor_rendering=sensor_rendering,
        sim_speed_factor=sim_speed_factor,
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
        executable="graceful_shutdown_move_group",
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
        robot_state_publisher=robot_state_publisher,
        simulator=simulator,
        spawners=tuple(spawners),
        move_group=move_group,
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
    simulator_shutdown = RegisterEventHandler(
        OnProcessExit(
            target_action=stack.simulator,
            on_exit=[Shutdown(reason="MuJoCo runtime exited")],
        )
    )
    actions = [*stack.actions, simulator_shutdown]
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
    required_long_lived: tuple[tuple[str, object], ...],
    successful_one_shots: tuple[tuple[str, object], ...],
    exit_status: PerceptionLaunchExitStatus,
    workflow_label: str = "Dynamic perception workflow",
    perception_start_delay_s: float = 0.0,
):
    """Create the shared fail-closed process policy for production and tests."""

    def on_scene_exit(event, _context):
        if event.returncode == 0:
            if perception_start_delay_s > 0.0:
                return [
                    workflow,
                    TimerAction(
                        period=perception_start_delay_s,
                        actions=[perception],
                    ),
                ]
            return [perception, workflow]
        exit_status.record(event.returncode)
        reason = f"SO-101 Planning Scene setup failed with exit code {event.returncode}"
        return _terminal_launch_actions(reason, failed=True)

    def required_exit_handler(label: str):
        def on_exit(event, _context):
            if exit_status.workflow_terminal:
                return []
            exit_status.record(event.returncode if event.returncode != 0 else 1)
            reason = (
                f"{label} exited before dynamic workflow completed with exit code "
                f"{event.returncode}"
            )
            return _terminal_launch_actions(reason, failed=True)

        return on_exit

    def one_shot_exit_handler(label: str):
        def on_exit(event, _context):
            if exit_status.workflow_terminal:
                return []
            if event.returncode == 0:
                return []
            exit_status.record(event.returncode)
            reason = f"{label} failed with exit code {event.returncode}"
            return _terminal_launch_actions(reason, failed=True)

        return on_exit

    def on_workflow_exit(event, _context):
        exit_status.mark_workflow_terminal()
        exit_status.record(event.returncode)
        outcome = "completed" if event.returncode == 0 else "failed"
        reason = f"{workflow_label} {outcome} with exit code {event.returncode}"
        return _terminal_launch_actions(reason, failed=event.returncode != 0)

    return (
        RegisterEventHandler(OnProcessExit(target_action=scene_setup, on_exit=on_scene_exit)),
        *(
            RegisterEventHandler(
                OnProcessExit(
                    target_action=action,
                    on_exit=required_exit_handler(label),
                )
            )
            for label, action in required_long_lived
        ),
        *(
            RegisterEventHandler(
                OnProcessExit(
                    target_action=action,
                    on_exit=one_shot_exit_handler(label),
                )
            )
            for label, action in successful_one_shots
        ),
        RegisterEventHandler(OnProcessExit(target_action=workflow, on_exit=on_workflow_exit)),
    )


def _mujoco_perception_execute_actions(
    context,
    share: Path,
    session_id: str,
    *,
    evidence_paths: _PerceptionEvidencePaths,
    perception_timeout: str,
    cup_pose_timeout: str,
    perception_backend: str,
    perception_weights: Path | None,
    perception_weights_sha256: str | None,
    perception_model_root: Path | None,
    perception_model_manifest_sha256: str | None,
    perception_device: str,
    perception_allow_cpu_fallback: bool,
    perception_runtime: str,
    perception_container_image: str,
    perception_source_root: Path | None,
    grounded_thresholds: tuple[str, ...] | None,
    exit_status: PerceptionLaunchExitStatus,
    profiling_session: LaunchProfilingSession | None = None,
):
    stack = _mujoco_stack_actions(context, share, session_id, sim_speed_factor=1.0)
    camera_transforms = tuple(camera_static_transform_nodes())
    profiling_arguments = (
        list(profiling_session.child_arguments)
        if profiling_session is not None
        else []
    )
    if perception_backend == "color_geometry":
        perception = Node(
            package="so101_demo_py",
            executable="rgbd_cup_pose",
            arguments=[
                "--startup-timeout-s",
                perception_timeout,
                "--output-topic",
                "/cup_pose",
                "--output-ply",
                str(evidence_paths.perception / "cup.ply"),
                "--evidence-json",
                str(evidence_paths.perception / "summary.json"),
                *profiling_arguments,
            ],
            parameters=[{"use_sim_time": True}],
            output="both",
        )
    elif perception_backend == "yolo_seg":
        if perception_weights is None or perception_weights_sha256 is None:
            raise RuntimeError("validated YOLO perception weights are missing")
        arguments = [
            "--startup-timeout-s",
            perception_timeout,
            "--output-topic",
            "/cup_pose",
            "--detections-topic",
            "/perception/detections",
            "--overlay-topic",
            "/perception/overlay",
            "--weights",
            str(perception_weights),
            "--weights-sha256",
            perception_weights_sha256,
            "--device",
            perception_device,
            "--request-id",
            session_id,
            "--evidence-root",
            str(evidence_paths.perception),
            "--require-output-subscriber",
            *profiling_arguments,
        ]
        if perception_allow_cpu_fallback:
            arguments.append("--allow-cpu-fallback")
        if perception_runtime in {"docker", "docker_dev"}:
            container_arguments = list(arguments)
            container_arguments[container_arguments.index(str(perception_weights))] = (
                "/models/best.pt"
            )
            container_arguments[
                container_arguments.index(str(evidence_paths.perception))
            ] = "/evidence"
            if profiling_session is not None:
                container_arguments[
                    container_arguments.index(str(profiling_session.profiling_root))
                ] = "/profiling"
            device_index = container_arguments.index("--device") + 1
            container_arguments[device_index] = "cuda"
            container_command = [
                "docker",
                "run",
                "--rm",
                "--name",
                f"so101-yolo-seg-{session_id}",
                "--gpus",
                "all",
                "--network",
                "host",
                "--ipc",
                "host",
                "--user",
                f"{os.geteuid()}:{os.getegid()}",
                "--env",
                f"ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID', '0')}",
                "--env",
                "RMW_IMPLEMENTATION="
                + os.environ.get("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp"),
                "--env",
                f"ROS_LOCALHOST_ONLY={os.environ.get('ROS_LOCALHOST_ONLY', '0')}",
                "--env",
                "HOME=/tmp/yolo-home",
                "--env",
                "YOLO_CONFIG_DIR=/opt/ultralytics",
                "--env",
                "TORCH_HOME=/opt/torch-cache",
            ]
            if perception_runtime == "docker_dev":
                container_command.extend(
                    [
                        "--env",
                        "PYTHONPATH=/workspace/so101-source",
                        "--mount",
                        "type=bind,"
                        f"src={perception_source_root},"
                        "dst=/workspace/so101-source/so101_demo,readonly",
                    ]
                )
            container_command.extend(
                [
                    "--mount",
                    f"type=bind,src={perception_weights},dst=/models/best.pt,readonly",
                    "--mount",
                    f"type=bind,src={evidence_paths.perception},dst=/evidence",
                    *(
                        [
                            "--mount",
                            "type=bind,"
                            f"src={profiling_session.profiling_root},"
                            "dst=/profiling",
                        ]
                        if profiling_session is not None
                        else []
                    ),
                    perception_container_image,
                    *container_arguments,
                ]
            )
            perception = ExecuteProcess(
                cmd=container_command,
                output="both",
            )
        else:
            perception = Node(
                package="so101_demo_py",
                executable="rgbd_object_pose",
                arguments=arguments,
                parameters=[{"use_sim_time": True}],
                output="both",
            )
    else:
        if (
            perception_model_root is None
            or perception_model_manifest_sha256 is None
            or grounded_thresholds is None
        ):
            raise RuntimeError("validated Grounded SAM perception artifacts are missing")
        arguments = [
            "--startup-timeout-s",
            perception_timeout,
            "--output-topic",
            "/cup_pose",
            "--detections-topic",
            "/perception/detections",
            "--overlay-topic",
            "/perception/overlay",
            "--backend",
            "grounded_sam",
            "--model-root",
            str(perception_model_root),
            "--model-manifest-sha256",
            perception_model_manifest_sha256,
            "--device",
            perception_device,
            "--grounding-box-threshold",
            grounded_thresholds[0],
            "--grounding-text-threshold",
            grounded_thresholds[1],
            "--duplicate-iou",
            grounded_thresholds[2],
            "--max-candidates",
            grounded_thresholds[3],
            "--sam-quality-threshold",
            grounded_thresholds[4],
            "--min-mask-pixels",
            grounded_thresholds[5],
            "--max-mask-area-ratio",
            grounded_thresholds[6],
            "--request-id",
            session_id,
            "--evidence-root",
            str(evidence_paths.perception),
            "--require-output-subscriber",
            *profiling_arguments,
        ]
        if perception_allow_cpu_fallback:
            arguments.append("--allow-cpu-fallback")
        perception = Node(
            package="so101_demo_py",
            executable="rgbd_object_pose",
            arguments=arguments,
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
            str(evidence_paths.dynamic),
            *profiling_arguments,
        ],
        output="both",
    )
    handlers = perception_pick_place_exit_handlers(
        stack.scene_setup,
        perception,
        workflow,
        required_long_lived=(
            ("MuJoCo runtime", stack.simulator),
            ("robot_state_publisher", stack.robot_state_publisher),
            ("MoveIt move_group", stack.move_group),
            *(
                (f"camera static TF {index}", node)
                for index, node in enumerate(camera_transforms, 1)
            ),
            ("RGB-D perception", perception),
        ),
        successful_one_shots=tuple(
            (f"controller spawner {_CONTROLLERS[index]}", node)
            for index, node in enumerate(stack.spawners)
        ),
        exit_status=exit_status,
        perception_start_delay_s=(
            1.0 if perception_backend in {"yolo_seg", "grounded_sam"} else 0.0
        ),
    )
    profiling_handlers = (
        profiling_event_handlers(
            profiling_session,
            scene_setup=stack.scene_setup,
            perception=perception,
            workflow=workflow,
        )
        if profiling_session is not None
        else ()
    )
    return [
        *handlers,
        *profiling_handlers,
        *camera_transforms,
        *stack.actions,
    ]


def _mujoco_text_pick_agent_execute_actions(
    context,
    share: Path,
    session_id: str,
    *,
    instruction: str,
    evidence_paths: _PerceptionEvidencePaths,
    perception_timeout: str,
    cup_pose_timeout: str,
    execution_identity: InstalledExecutionIdentity,
    exit_status: PerceptionLaunchExitStatus,
    profiling_session: LaunchProfilingSession | None = None,
):
    stack = _mujoco_stack_actions(context, share, session_id)
    camera_transforms = tuple(camera_static_transform_nodes())
    profiling_arguments = (
        list(profiling_session.child_arguments)
        if profiling_session is not None
        else []
    )
    perception = Node(
        package="so101_demo_py",
        executable="rgbd_cup_pose",
        arguments=[
            "--startup-timeout-s",
            perception_timeout,
            "--output-topic",
            "/cup_pose",
            "--output-ply",
            str(evidence_paths.perception / "cup.ply"),
            "--evidence-json",
            str(evidence_paths.perception / "summary.json"),
            *profiling_arguments,
        ],
        parameters=[{"use_sim_time": True}],
        output="both",
    )
    workflow = ExecuteProcess(
        cmd=[
            str(
                Path(execution_identity.package_prefix)
                / "lib"
                / "so101_demo_py"
                / "text_pick_agent"
            ),
            "--instruction",
            instruction,
            "--mode",
            "execute",
            "--execute",
            "--skip-confirmation",
            "--backend",
            "mujoco",
            "--cup-pose-timeout-s",
            cup_pose_timeout,
            "--session-id",
            session_id,
            "--expected-reset-epoch",
            "0",
            "--evidence-root",
            str(evidence_paths.dynamic),
            "--source-commit",
            execution_identity.source_commit,
            "--installed-prefix",
            execution_identity.package_prefix,
            *profiling_arguments,
        ],
        output="both",
    )
    handlers = perception_pick_place_exit_handlers(
        stack.scene_setup,
        perception,
        workflow,
        required_long_lived=(
            ("MuJoCo runtime", stack.simulator),
            ("robot_state_publisher", stack.robot_state_publisher),
            ("MoveIt move_group", stack.move_group),
            *(
                (f"camera static TF {index}", node)
                for index, node in enumerate(camera_transforms, 1)
            ),
            ("RGB-D perception", perception),
        ),
        successful_one_shots=tuple(
            (f"controller spawner {_CONTROLLERS[index]}", node)
            for index, node in enumerate(stack.spawners)
        ),
        exit_status=exit_status,
        workflow_label="Text Agent RGB-D workflow",
    )
    profiling_handlers = (
        profiling_event_handlers(
            profiling_session,
            scene_setup=stack.scene_setup,
            perception=perception,
            workflow=workflow,
        )
        if profiling_session is not None
        else ()
    )
    return [
        *handlers,
        *profiling_handlers,
        *camera_transforms,
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


def _grounded_sam_threshold_launch_values(context) -> tuple[str, ...]:
    values: list[str] = []
    for name, default in _GROUNDED_SAM_THRESHOLD_DEFAULTS:
        value = LaunchConfiguration(name).perform(context) or default
        if name in {"grounding_max_candidates", "sam_min_mask_pixels"}:
            try:
                parsed = int(value)
            except ValueError as error:
                raise RuntimeError(f"{name} must be a positive integer") from error
            if str(parsed) != value or parsed <= 0:
                raise RuntimeError(f"{name} must be a positive integer")
        else:
            try:
                parsed = float(value)
            except ValueError as error:
                raise RuntimeError(f"{name} must be a finite probability") from error
            if not isfinite(parsed) or not 0.0 <= parsed <= 1.0:
                raise RuntimeError(f"{name} must be a finite probability")
            if name == "sam_max_mask_area_ratio" and parsed <= 0.0:
                raise RuntimeError(f"{name} must be greater than zero")
        values.append(value)
    return tuple(values)


def _forbidden_backend_arguments(context, names: tuple[str, ...]) -> None:
    for name in names:
        if LaunchConfiguration(name).perform(context):
            raise RuntimeError(f"{name} is only valid for its matching perception backend")


def _reject_nondefault_grounded_sam_thresholds(context) -> None:
    for name, default in _GROUNDED_SAM_THRESHOLD_DEFAULTS:
        if LaunchConfiguration(name).perform(context) != default:
            raise RuntimeError(f"{name} is only valid for the grounded_sam perception backend")


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


def _exclusive_owned_directory(path: Path, label: str) -> Path:
    try:
        path.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError as error:
        raise RuntimeError(f"{label} already exists: {path}") from error
    return _owned_directory(path, label)


def _prepare_perception_evidence_root(
    evidence_file: Path, session_id: str
) -> _PerceptionEvidencePaths:
    run_root = _prepare_perception_run_root(evidence_file, session_id)
    return _prepare_perception_evidence_directories(run_root)


def _prepare_perception_run_root(evidence_file: Path, session_id: str) -> Path:
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
    resolved_run_root = _exclusive_owned_directory(run_root, "session evidence root")
    if resolved_run_root.parent != resolved_base:
        raise RuntimeError("session evidence root escapes derived evidence root")
    return resolved_run_root


def _prepare_perception_evidence_directories(
    resolved_run_root: Path,
) -> _PerceptionEvidencePaths:

    perception = _exclusive_owned_directory(
        resolved_run_root / "perception", "perception evidence directory"
    )
    if perception.parent != resolved_run_root:
        raise RuntimeError("perception evidence directory escapes session root")
    dynamic = _exclusive_owned_directory(
        resolved_run_root / "dynamic", "dynamic evidence directory"
    )
    if dynamic.parent != resolved_run_root:
        raise RuntimeError("dynamic evidence directory escapes session root")
    return _PerceptionEvidencePaths(
        run_root=resolved_run_root,
        perception=perception,
        dynamic=dynamic,
    )


def _configured_perception_pick_place_actions(context, *, exit_status: PerceptionLaunchExitStatus):
    run_mode = LaunchConfiguration("run_mode").perform(context)
    execute = LaunchConfiguration("execute").perform(context)
    headless = LaunchConfiguration("headless").perform(context)
    profiling_mode = LaunchConfiguration("profiling").perform(context)
    profiling_output_root = LaunchConfiguration("profiling_output_root").perform(context)
    profiling_require_system_trace = LaunchConfiguration(
        "profiling_require_system_trace"
    ).perform(context)
    if run_mode != "execute":
        raise RuntimeError("perception pick-place requires run_mode=execute")
    if execute != "true":
        raise RuntimeError("perception pick-place requires execute:=true")
    if headless not in {"true", "false"}:
        raise RuntimeError("headless must be true or false")
    validate_launch_profiling_values(
        mode_value=profiling_mode,
        output_root_value=profiling_output_root,
        require_system_trace_value=profiling_require_system_trace,
    )

    initial_keyframe = LaunchConfiguration("mujoco_initial_keyframe").perform(context)
    if initial_keyframe not in MUJOCO_CUP_KEYFRAMES:
        raise RuntimeError(f"unsupported MuJoCo initial keyframe: {initial_keyframe}")

    _positive_finite_launch_value(context, "readiness_timeout_s")
    perception_timeout = _positive_finite_launch_value(context, "perception_startup_timeout_s")
    cup_pose_timeout = _positive_finite_launch_value(context, "cup_pose_timeout_s")

    perception_backend = LaunchConfiguration("perception_backend").perform(context)
    if perception_backend not in {"color_geometry", "yolo_seg", "grounded_sam"}:
        raise RuntimeError("perception_backend must be color_geometry, yolo_seg, or grounded_sam")
    perception_weights: Path | None = None
    perception_weights_sha256: str | None = None
    perception_model_root: Path | None = None
    perception_model_manifest_sha256: str | None = None
    grounded_thresholds: tuple[str, ...] | None = None
    perception_device = LaunchConfiguration("perception_device").perform(context)
    if perception_device not in {"auto", "cuda", "mps", "cpu"}:
        raise RuntimeError("perception_device must be auto, cuda, mps, or cpu")
    perception_runtime = LaunchConfiguration("perception_runtime").perform(context)
    if perception_runtime not in {"auto", "host", "docker", "docker_dev"}:
        raise RuntimeError(
            "perception_runtime must be auto, host, docker, or docker_dev"
        )
    host_platform = platform.system()
    if perception_runtime == "auto":
        if host_platform == "Darwin":
            perception_runtime = "host"
            if perception_device == "auto":
                perception_device = "mps"
        elif host_platform == "Linux":
            perception_runtime = "docker"
        else:
            raise RuntimeError(
                f"perception_runtime auto does not support platform {host_platform}"
            )
    docker_runtimes = {"docker", "docker_dev"}
    if perception_runtime in docker_runtimes and host_platform != "Linux":
        raise RuntimeError("YOLO inference Docker runtime is supported only on Linux")
    if perception_runtime in docker_runtimes and perception_device not in {
        "auto",
        "cuda",
    }:
        raise RuntimeError("YOLO inference Docker runtime requires CUDA")
    perception_container_image = LaunchConfiguration(
        "perception_container_image"
    ).perform(context)
    if not perception_container_image or any(
        character.isspace() for character in perception_container_image
    ):
        raise RuntimeError("perception_container_image must be a non-empty image reference")
    source_root_value = LaunchConfiguration("perception_source_root").perform(
        context
    )
    perception_source_root: Path | None = None
    if perception_runtime == "docker_dev":
        candidate_source_root = Path(source_root_value)
        if (
            not candidate_source_root.is_absolute()
            or candidate_source_root.is_symlink()
            or not candidate_source_root.is_dir()
            or not (candidate_source_root / "__init__.py").is_file()
            or not (candidate_source_root / "runtime").is_dir()
            or "," in source_root_value
        ):
            raise RuntimeError(
                "perception_source_root must be an absolute, non-symlink Python "
                "source directory for so101_demo"
            )
        perception_source_root = candidate_source_root.resolve(strict=True)
    elif source_root_value:
        raise RuntimeError(
            "perception_source_root is accepted only with perception_runtime=docker_dev"
        )
    cpu_fallback_value = LaunchConfiguration("perception_allow_cpu_fallback").perform(context)
    if cpu_fallback_value not in {"true", "false"}:
        raise RuntimeError("perception_allow_cpu_fallback must be true or false")
    if perception_backend == "color_geometry":
        _forbidden_backend_arguments(
            context,
            (
                "perception_weights",
                "perception_weights_sha256",
                "perception_model_root",
                "perception_model_manifest_sha256",
            ),
        )
        _reject_nondefault_grounded_sam_thresholds(context)
    elif perception_backend == "yolo_seg":
        _forbidden_backend_arguments(
            context,
            (
                "perception_model_root",
                "perception_model_manifest_sha256",
            ),
        )
        _reject_nondefault_grounded_sam_thresholds(context)
        perception_weights = Path(
            LaunchConfiguration("perception_weights").perform(context)
        )
        if (
            not perception_weights.is_absolute()
            or perception_weights.is_symlink()
            or not perception_weights.is_file()
        ):
            raise RuntimeError("perception_weights must be an existing absolute file")
        perception_weights_sha256 = LaunchConfiguration(
            "perception_weights_sha256"
        ).perform(context)
        if re.fullmatch(r"[0-9a-f]{64}", perception_weights_sha256) is None:
            raise RuntimeError(
                "perception_weights_sha256 must be a lowercase SHA256 digest"
            )
    else:
        _forbidden_backend_arguments(
            context,
            ("perception_weights", "perception_weights_sha256"),
        )
        perception_model_root = Path(
            LaunchConfiguration("perception_model_root").perform(context)
        )
        if (
            not perception_model_root.is_absolute()
            or perception_model_root.is_symlink()
            or not perception_model_root.is_dir()
        ):
            raise RuntimeError(
                "perception_model_root must be an existing absolute non-symlink directory"
            )
        perception_model_manifest_sha256 = LaunchConfiguration(
            "perception_model_manifest_sha256"
        ).perform(context)
        if re.fullmatch(r"[0-9a-f]{64}", perception_model_manifest_sha256) is None:
            raise RuntimeError(
                "perception_model_manifest_sha256 must be a lowercase SHA256 digest"
            )
        grounded_thresholds = _grounded_sam_threshold_launch_values(context)

    session_id = LaunchConfiguration("session_id").perform(context)
    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise RuntimeError(
            "session_id must start with an alphanumeric character and contain only "
            "letters, digits, dot, underscore, or hyphen"
        )

    evidence_file = Path(LaunchConfiguration("evidence_file").perform(context))
    if not evidence_file.is_absolute() or evidence_file.name in {"", ".", ".."}:
        raise RuntimeError("evidence_file must be a usable absolute file path")
    if os.path.lexists(evidence_file):
        raise RuntimeError("evidence_file must not already exist")
    scene = Path(LaunchConfiguration("mujoco_scene").perform(context))
    if not scene.is_absolute():
        raise RuntimeError("mujoco_scene must be an absolute file path")
    if not scene.is_file():
        raise RuntimeError(f"mujoco_scene does not exist: {scene}")

    share = Path(get_package_share_directory("so101_demo_py"))
    run_root = _prepare_perception_run_root(evidence_file, session_id)
    profiling_session = resolve_launch_profiling(
        mode_value=profiling_mode,
        output_root_value=profiling_output_root,
        require_system_trace_value=profiling_require_system_trace,
        run_root=run_root,
        session_id=session_id,
        source_commit=None,
        installed_prefix=None,
    )
    evidence_paths = _prepare_perception_evidence_directories(run_root)
    application_actions = _mujoco_perception_execute_actions(
        context,
        share,
        session_id,
        evidence_paths=evidence_paths,
        perception_timeout=perception_timeout,
        cup_pose_timeout=cup_pose_timeout,
        perception_backend=perception_backend,
        perception_weights=perception_weights,
        perception_weights_sha256=perception_weights_sha256,
        perception_model_root=perception_model_root,
        perception_model_manifest_sha256=perception_model_manifest_sha256,
        perception_device=perception_device,
        perception_allow_cpu_fallback=cpu_fallback_value == "true",
        perception_runtime=perception_runtime,
        perception_container_image=perception_container_image,
        perception_source_root=perception_source_root,
        grounded_thresholds=grounded_thresholds,
        exit_status=exit_status,
        profiling_session=profiling_session,
    )
    if profiling_session is None:
        return application_actions
    return [*profiling_session.prefix_actions, *application_actions]


def _configured_text_pick_agent_actions(context, *, exit_status: PerceptionLaunchExitStatus):
    instruction = LaunchConfiguration("instruction").perform(context)
    run_mode = LaunchConfiguration("run_mode").perform(context)
    execute = LaunchConfiguration("execute").perform(context)
    skip_confirmation = LaunchConfiguration("skip_confirmation").perform(context)
    headless = LaunchConfiguration("headless").perform(context)
    sensor_rendering = LaunchConfiguration("sensor_rendering").perform(context)
    profiling_mode = LaunchConfiguration("profiling").perform(context)
    profiling_output_root = LaunchConfiguration("profiling_output_root").perform(context)
    profiling_require_system_trace = LaunchConfiguration(
        "profiling_require_system_trace"
    ).perform(context)
    if not instruction.strip():
        raise RuntimeError("instruction must be non-empty")
    if run_mode != "execute":
        raise RuntimeError("text-agent launch requires run_mode=execute")
    if execute != "true":
        raise RuntimeError("text-agent launch requires execute:=true")
    if skip_confirmation != "true":
        raise RuntimeError("text-agent launch requires skip_confirmation:=true")
    if sensor_rendering != "true":
        raise RuntimeError("text-agent launch requires sensor_rendering=true")
    if headless not in {"true", "false"}:
        raise RuntimeError("headless must be true or false")
    validate_launch_profiling_values(
        mode_value=profiling_mode,
        output_root_value=profiling_output_root,
        require_system_trace_value=profiling_require_system_trace,
    )

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
    if os.path.lexists(evidence_file):
        raise RuntimeError("evidence_file must not already exist")
    scene = Path(LaunchConfiguration("mujoco_scene").perform(context))
    if not scene.is_absolute():
        raise RuntimeError("mujoco_scene must be an absolute file path")
    if not scene.is_file():
        raise RuntimeError(f"mujoco_scene does not exist: {scene}")

    execution_identity = resolve_installed_execution_identity()
    share = Path(get_package_share_directory("so101_demo_py"))
    run_root = _prepare_perception_run_root(evidence_file, session_id)
    profiling_session = resolve_launch_profiling(
        mode_value=profiling_mode,
        output_root_value=profiling_output_root,
        require_system_trace_value=profiling_require_system_trace,
        run_root=run_root,
        session_id=session_id,
        source_commit=execution_identity.source_commit,
        installed_prefix=execution_identity.package_prefix,
    )
    evidence_paths = _prepare_perception_evidence_directories(run_root)
    application_actions = _mujoco_text_pick_agent_execute_actions(
        context,
        share,
        session_id,
        instruction=instruction,
        evidence_paths=evidence_paths,
        perception_timeout=perception_timeout,
        cup_pose_timeout=cup_pose_timeout,
        execution_identity=execution_identity,
        exit_status=exit_status,
        profiling_session=profiling_session,
    )
    if profiling_session is None:
        return application_actions
    return [*profiling_session.prefix_actions, *application_actions]


def build_launch_description(*, backend: str, pick_place: bool) -> LaunchDescription:
    if backend not in {"mujoco", "gazebo"}:
        raise ValueError(f"unsupported launch backend: {backend}")
    share = Path(get_package_share_directory("so101_demo_py"))
    unique = uuid.uuid4().hex
    arguments = [
        DeclareLaunchArgument("run_mode", default_value="dry_run", choices=("dry_run", "execute")),
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
                    "sensor_rendering",
                    default_value="auto",
                    choices=("auto", "true", "false"),
                ),
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
            DeclareLaunchArgument("execute", default_value="false", choices=("true", "false")),
            DeclareLaunchArgument("headless", default_value="false", choices=("true", "false")),
            DeclareLaunchArgument(
                "sensor_rendering", default_value="true", choices=("true", "false")
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
            DeclareLaunchArgument("perception_startup_timeout_s", default_value="30.0"),
            DeclareLaunchArgument("cup_pose_timeout_s", default_value="45.0"),
            DeclareLaunchArgument(
                "perception_backend",
                default_value="color_geometry",
                choices=("color_geometry", "yolo_seg", "grounded_sam"),
            ),
            DeclareLaunchArgument("perception_weights", default_value=""),
            DeclareLaunchArgument("perception_weights_sha256", default_value=""),
            DeclareLaunchArgument("perception_model_root", default_value=""),
            DeclareLaunchArgument("perception_model_manifest_sha256", default_value=""),
            DeclareLaunchArgument(
                "perception_device",
                default_value="auto",
                choices=("auto", "cuda", "mps", "cpu"),
            ),
            DeclareLaunchArgument(
                "perception_allow_cpu_fallback",
                default_value="false",
                choices=("true", "false"),
            ),
            DeclareLaunchArgument(
                "perception_runtime",
                default_value="auto",
                choices=("auto", "host", "docker", "docker_dev"),
            ),
            DeclareLaunchArgument(
                "perception_container_image",
                default_value=_DEFAULT_YOLO_INFERENCE_IMAGE,
            ),
            DeclareLaunchArgument("perception_source_root", default_value=""),
            *(
                DeclareLaunchArgument(name, default_value=default)
                for name, default in _GROUNDED_SAM_THRESHOLD_DEFAULTS
            ),
            DeclareLaunchArgument(
                "profiling",
                default_value="off",
                choices=("off", "summary", "trace"),
            ),
            DeclareLaunchArgument("profiling_output_root", default_value=""),
            DeclareLaunchArgument(
                "profiling_require_system_trace",
                default_value="false",
                choices=("true", "false"),
            ),
            OpaqueFunction(
                function=_configured_perception_pick_place_actions,
                kwargs={"exit_status": exit_status},
            ),
        ]
    )


def build_text_pick_agent_launch_description(
    exit_status: PerceptionLaunchExitStatus | None = None,
) -> LaunchDescription:
    """Build the explicit MuJoCo natural-language RGB-D execute graph."""

    share = Path(get_package_share_directory("so101_demo_py"))
    unique = uuid.uuid4().hex
    if exit_status is None:
        exit_status = PerceptionLaunchExitStatus()
    return LaunchDescription(
        [
            DeclareLaunchArgument("instruction"),
            DeclareLaunchArgument(
                "run_mode", default_value="dry_run", choices=("dry_run", "execute")
            ),
            DeclareLaunchArgument("execute", default_value="false", choices=("true", "false")),
            DeclareLaunchArgument(
                "skip_confirmation", default_value="false", choices=("true", "false")
            ),
            DeclareLaunchArgument("headless", default_value="false", choices=("true", "false")),
            DeclareLaunchArgument(
                "sensor_rendering", default_value="true", choices=("true",)
            ),
            DeclareLaunchArgument("session_id", default_value=unique),
            DeclareLaunchArgument(
                "evidence_file", default_value=f"/tmp/so101-text-agent-{unique}.json"
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
            DeclareLaunchArgument("perception_startup_timeout_s", default_value="30.0"),
            DeclareLaunchArgument("cup_pose_timeout_s", default_value="45.0"),
            DeclareLaunchArgument(
                "profiling",
                default_value="off",
                choices=("off", "summary", "trace"),
            ),
            DeclareLaunchArgument("profiling_output_root", default_value=""),
            DeclareLaunchArgument(
                "profiling_require_system_trace",
                default_value="false",
                choices=("true", "false"),
            ),
            OpaqueFunction(
                function=_configured_text_pick_agent_actions,
                kwargs={"exit_status": exit_status},
            ),
        ]
    )


def _configured_task_station_actions(context):
    session_id = LaunchConfiguration("session_id").perform(context)
    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise RuntimeError("task station session_id is invalid")
    headless = LaunchConfiguration("headless").perform(context)
    if headless != "false":
        raise RuntimeError("macOS task station requires headless=false")
    evidence_root = Path(
        LaunchConfiguration("task_evidence_root").perform(context)
    )
    if not evidence_root.is_absolute():
        raise RuntimeError("task_evidence_root must be absolute")
    include_teleop = LaunchConfiguration("include_teleop").perform(context)
    if include_teleop not in {"true", "false"}:
        raise RuntimeError("include_teleop must be true or false")
    share = Path(get_package_share_directory("so101_demo_py"))
    stack = _mujoco_stack_actions(context, share, session_id)
    teleop_actions = []
    if include_teleop == "true":
        teleop_share = Path(get_package_share_directory("so101_teleop"))
        teleop_actions.append(
            RegisterEventHandler(
                OnProcessStart(
                    target_action=stack.simulator,
                    on_start=partial(
                        _task_station_teleop_actions,
                        teleop_share=teleop_share,
                        session_id=session_id,
                    ),
                )
            )
        )
    actions = [
        *teleop_actions,
        *camera_static_transform_nodes(),
        *stack.actions,
        SetEnvironmentVariable("SO101_TASK_EVIDENCE_ROOT", str(evidence_root)),
        RegisterEventHandler(
            OnProcessExit(
                target_action=stack.simulator,
                on_exit=[Shutdown(reason="MuJoCo task station runtime exited")],
            )
        ),
    ]
    return actions


def _task_station_teleop_actions(
    event,
    context,
    *,
    teleop_share: Path,
    session_id: str,
):
    del context
    mujoco_pid = int(event.pid)
    if mujoco_pid <= 0:
        raise RuntimeError("task station MuJoCo PID must be positive")
    return (
        SetEnvironmentVariable(
            "SO101_TASK_STATION_MUJOCO_PID",
            str(mujoco_pid),
        ),
        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                str(teleop_share / "launch/so101_teleop.launch.py")
            ),
            launch_arguments={
                "backend": "mujoco_py",
                "bind_address": "127.0.0.1",
                "port": LaunchConfiguration("teleop_port"),
                "simulation_session_id": session_id,
                "build_web_if_needed": "false",
            }.items(),
        ),
    )


def build_task_station_launch_description() -> LaunchDescription:
    """Build one visible persistent MuJoCo/MoveIt/camera-TF task station."""

    share = Path(get_package_share_directory("so101_demo_py"))
    unique = uuid.uuid4().hex
    return LaunchDescription(
        [
            DeclareLaunchArgument("headless", default_value="false", choices=("false",)),
            DeclareLaunchArgument(
                "sensor_rendering", default_value="true", choices=("true",)
            ),
            DeclareLaunchArgument("session_id", default_value=unique),
            DeclareLaunchArgument(
                "task_evidence_root",
                default_value=f"/tmp/so101-task-station-{unique}",
            ),
            DeclareLaunchArgument(
                "include_teleop",
                default_value="true",
                choices=("true", "false"),
            ),
            DeclareLaunchArgument("teleop_port", default_value="8080"),
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
            OpaqueFunction(function=_configured_task_station_actions),
        ]
    )
