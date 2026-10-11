"""The perception pick-place launch: evidence directories, exit handlers and the launch description."""

from __future__ import annotations

import os
from pathlib import Path
import uuid

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    OpaqueFunction,
    RegisterEventHandler,
    TimerAction,
)
from launch.event_handlers import OnProcessExit
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from so101_demo.profiling.launch_support import (
    LaunchProfilingSession,
    profiling_event_handlers,
    resolve_launch_profiling,
    validate_launch_profiling_values,
)
from so101_demo.runtime.camera_tf import camera_static_transform_nodes
from so101_demo.runtime.launch_composition.common import (
    _CONTROLLERS,
    _SESSION_ID_PATTERN,
    MUJOCO_CUP_KEYFRAMES,
    _exclusive_owned_directory,
    _owned_directory,
    _positive_finite_launch_value,
    _terminal_launch_actions,
)
from so101_demo.runtime.launch_composition.mujoco_actions import _mujoco_stack_actions
from so101_demo.runtime.launch_composition.supervisor import (
    PerceptionLaunchExitStatus,
    _PerceptionEvidencePaths,
)
from so101_demo.runtime.perception_launch import (
    PerceptionLaunchOptions,
    build_perception_action,
    declare_perception_arguments,
    parse_perception_options,
)


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
    cup_pose_timeout: str,
    perception_options: PerceptionLaunchOptions,
    exit_status: PerceptionLaunchExitStatus,
    profiling_session: LaunchProfilingSession | None = None,
):
    stack = _mujoco_stack_actions(context, share, session_id, sim_speed_factor=1.0)
    camera_transforms = tuple(camera_static_transform_nodes())
    profiling_arguments = (
        tuple(profiling_session.child_arguments)
        if profiling_session is not None
        else ()
    )
    perception = build_perception_action(
        perception_options,
        evidence_root=evidence_paths.perception,
        request_id=session_id,
        child_arguments=profiling_arguments,
        profiling_root=(
            profiling_session.profiling_root
            if profiling_session is not None
            else None
        ),
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
            1.0
            if perception_options.backend in {"yolo_seg", "grounded_sam"}
            else 0.0
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
    perception_options = parse_perception_options(context)
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
        cup_pose_timeout=cup_pose_timeout,
        perception_options=perception_options,
        exit_status=exit_status,
        profiling_session=profiling_session,
    )
    if profiling_session is None:
        return application_actions
    return [*profiling_session.prefix_actions, *application_actions]


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
            *declare_perception_arguments(default_backend="color_geometry"),
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
