"""The text pick agent launch and its end-to-end variant."""

from __future__ import annotations

import os
from pathlib import Path
import sys
import uuid

from ament_index_python.packages import get_package_share_directory
from launch import Action, LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    ExecuteProcess,
    OpaqueFunction,
    RegisterEventHandler,
)
from launch.event_handlers import OnProcessExit, OnProcessIO
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

from so101_demo.core.task_command import CommandValidationError, validate_instruction
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
    _positive_finite_launch_value,
    installed_executable,
)
from so101_demo.runtime.launch_composition.mujoco_actions import _mujoco_stack_actions
from so101_demo.runtime.launch_composition.perception import (
    _prepare_perception_evidence_directories,
    _prepare_perception_run_root,
    perception_pick_place_exit_handlers,
)
from so101_demo.runtime.launch_composition.supervisor import (
    E2ESupervisor,
    PerceptionLaunchExitStatus,
    _PerceptionEvidencePaths,
)
from so101_demo.runtime.perception_launch import (
    PerceptionLaunchOptions,
    build_perception_action,
    declare_perception_arguments,
    parse_perception_options,
)
from so101_demo.runtime.provenance import (
    InstalledExecutionIdentity,
    resolve_installed_execution_identity,
)


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
            str(installed_executable("text_pick_agent")),
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
            *(
                ("--source-commit", execution_identity.source_commit)
                if execution_identity.source_commit is not None
                else ()
            ),
            *(
                ("--installed-prefix", execution_identity.package_prefix)
                if execution_identity.package_prefix is not None
                else ()
            ),
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


def _prepare_e2e_run_root(evidence_file: Path) -> Path:
    """Create the exclusive directory that owns the authoritative result."""

    if (
        not evidence_file.is_absolute()
        or evidence_file.name in {"", ".", ".."}
        or os.path.lexists(evidence_file)
    ):
        raise RuntimeError(
            "evidence_file must be a new usable absolute file path"
        )
    run_root = evidence_file.parent
    try:
        parent = run_root.parent.resolve(strict=True)
    except FileNotFoundError as error:
        raise RuntimeError("evidence run-root parent must exist") from error
    if not parent.is_dir() or run_root.parent.is_symlink():
        raise RuntimeError("evidence run-root parent must be a non-symlink directory")
    resolved_root = _exclusive_owned_directory(run_root, "E2E evidence root")
    if resolved_root.parent != parent:
        raise RuntimeError("E2E evidence root escapes its declared parent")
    for name in ("perception", "dynamic", "acceptance"):
        child = _exclusive_owned_directory(
            resolved_root / name, f"E2E {name} evidence directory"
        )
        if child.parent != resolved_root:
            raise RuntimeError(f"E2E {name} evidence directory escapes run root")
    return resolved_root


def _e2e_model_provenance(options: PerceptionLaunchOptions) -> dict[str, object]:
    document: dict[str, object] = {
        "backend": options.backend,
        "device": options.device,
        "runtime": options.runtime,
        "allow_cpu_fallback": options.allow_cpu_fallback,
    }
    if options.weights_path is not None:
        document.update(
            {
                "weights_path": str(options.weights_path),
                "weights_sha256": options.weights_sha256,
            }
        )
    if options.model_root is not None:
        document.update(
            {
                "model_root": str(options.model_root),
                "model_manifest_sha256": options.model_manifest_sha256,
            }
        )
    if options.runtime in {"docker", "docker_dev"}:
        document["container_image"] = options.container_image
    return document


def _e2e_process_handlers(
    supervisor: E2ESupervisor,
    *,
    scene_setup: ExecuteProcess,
    event_children: tuple[ExecuteProcess, ...],
    exit_children: tuple[ExecuteProcess, ...],
) -> list[Action]:
    handlers: list[Action] = [
        RegisterEventHandler(
            OnProcessExit(
                target_action=scene_setup,
                on_exit=lambda event, _context: supervisor.on_scene_exit(
                    event.returncode
                ),
            )
        )
    ]
    for child in event_children:
        handlers.append(
            RegisterEventHandler(
                OnProcessIO(
                    target_action=child,
                    on_stdout=lambda event, target=child: supervisor.on_stdout(
                        target, event.text
                    ),
                )
            )
        )
    for child in exit_children:
        handlers.append(
            RegisterEventHandler(
                OnProcessExit(
                    target_action=child,
                    on_exit=lambda event, _context, target=child: supervisor.on_exit(
                        target, event.returncode
                    ),
                )
            )
        )
    return handlers


def _configured_text_pick_agent_e2e_actions(context):
    instruction_value = LaunchConfiguration("instruction").perform(context)
    try:
        instruction = validate_instruction(instruction_value)
    except CommandValidationError as error:
        raise RuntimeError(f"instruction is invalid: {error.reason}") from error
    if LaunchConfiguration("run_mode").perform(context) != "execute":
        raise RuntimeError("E2E launch requires run_mode=execute")
    if LaunchConfiguration("execute").perform(context) != "true":
        raise RuntimeError("E2E launch requires execute:=true")
    if LaunchConfiguration("skip_confirmation").perform(context) != "true":
        raise RuntimeError("E2E launch requires skip_confirmation:=true")
    if LaunchConfiguration("sensor_rendering").perform(context) != "true":
        raise RuntimeError("E2E launch requires sensor_rendering=true")
    if LaunchConfiguration("headless").perform(context) not in {"true", "false"}:
        raise RuntimeError("headless must be true or false")

    readiness_timeout = _positive_finite_launch_value(context, "readiness_timeout_s")
    perception_timeout = _positive_finite_launch_value(
        context, "perception_startup_timeout_s"
    )
    cup_pose_timeout = _positive_finite_launch_value(context, "cup_pose_timeout_s")
    initial_keyframe = LaunchConfiguration("mujoco_initial_keyframe").perform(context)
    if initial_keyframe not in MUJOCO_CUP_KEYFRAMES:
        raise RuntimeError(f"unsupported MuJoCo initial keyframe: {initial_keyframe}")
    session_id = LaunchConfiguration("session_id").perform(context)
    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise RuntimeError("session_id must use safe characters")
    scene = Path(LaunchConfiguration("mujoco_scene").perform(context))
    if not scene.is_absolute() or scene.is_symlink() or not scene.is_file():
        raise RuntimeError("mujoco_scene must be an existing absolute non-symlink file")

    # Model and platform checks are deliberately completed before creating the
    # evidence root or any launch action.
    perception_options = parse_perception_options(context)
    evidence_file = Path(LaunchConfiguration("evidence_file").perform(context))
    if (
        not evidence_file.is_absolute()
        or evidence_file.name in {"", ".", ".."}
        or os.path.lexists(evidence_file)
    ):
        raise RuntimeError("evidence_file must be a new usable absolute file path")
    if os.path.lexists(evidence_file.parent):
        raise RuntimeError(f"E2E evidence root already exists: {evidence_file.parent}")

    execution_identity = resolve_installed_execution_identity()
    share = Path(get_package_share_directory("so101_demo_py"))
    run_root = _prepare_e2e_run_root(evidence_file)
    workflow_id = f"workflow-{uuid.uuid4().hex}"
    request_id = f"request-{uuid.uuid4().hex}"
    stack = _mujoco_stack_actions(context, share, session_id, sim_speed_factor=1.0)
    camera_transforms = tuple(camera_static_transform_nodes())

    executable = (
        installed_executable("text_pick_agent")
    )
    text_agent = ExecuteProcess(
        cmd=[
            str(executable),
            "--instruction",
            instruction,
            "--request-id",
            request_id,
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
            str(run_root / "dynamic"),
            *(
                ("--source-commit", execution_identity.source_commit)
                if execution_identity.source_commit is not None
                else ()
            ),
            *(
                ("--installed-prefix", execution_identity.package_prefix)
                if execution_identity.package_prefix is not None
                else ()
            ),
            "--emit-workflow-events",
            "--workflow-id",
            workflow_id,
        ],
        output="both",
    )
    perception = build_perception_action(
        perception_options,
        evidence_root=run_root / "perception",
        request_id=request_id,
        workflow_id=workflow_id,
        # Keep the one-inference publisher alive until the supervisor tears the
        # stack down. A one-shot process can exit before a best-effort subscriber
        # receives the published pose on slower DDS hosts.
        child_arguments=(),
    )
    container_cleanup_actions: tuple[ExecuteProcess, ...] = ()
    model_provenance = _e2e_model_provenance(perception_options)
    if (
        perception_options.backend == "yolo_seg"
        and perception_options.runtime in {"docker", "docker_dev"}
    ):
        container_name = f"so101-yolo-seg-{request_id}"
        model_provenance.update(
            {
                "owned_container_name": container_name,
                "owned_container_cid_file": str(
                    run_root / "perception" / "container.cid"
                ),
                "owned_container_label": f"so101.workflow_id={workflow_id}",
            }
        )
        cleanup_code = (
            "import subprocess,sys; "
            "name=sys.argv[1]; "
            "probe=subprocess.run(['docker','container','inspect',name],"
            "stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
            "raise SystemExit(0 if probe.returncode else "
            "subprocess.run(['docker','rm','-f',name]).returncode)"
        )
        container_cleanup_actions = (
            ExecuteProcess(
                cmd=[sys.executable, "-c", cleanup_code, container_name],
                output="both",
            ),
        )
    validator = Node(
        package="so101_demo_py",
        executable="e2e_acceptance",
        arguments=[
            "--run-root",
            str(run_root),
            "--workflow-id",
            workflow_id,
            "--request-id",
            request_id,
            "--session-id",
            session_id,
            "--expected-reset-epoch",
            "0",
            "--emit-workflow-events",
        ],
        output="both",
    )
    supervisor = E2ESupervisor(
        workflow_id=workflow_id,
        request_id=request_id,
        session_id=session_id,
        backend=perception_options.backend,
        source_commit=execution_identity.source_commit,
        installed_prefix=execution_identity.package_prefix,
        run_root=run_root,
        result_file=evidence_file,
        text_agent_action=text_agent,
        perception_action=perception,
        validator_action=validator,
        container_cleanup_actions=container_cleanup_actions,
        model_provenance=model_provenance,
        perception_startup_timeout_s=float(perception_timeout),
        cup_pose_timeout_s=float(cup_pose_timeout),
    )
    for label, action in (
        ("robot_state_publisher", stack.robot_state_publisher),
        ("MuJoCo runtime", stack.simulator),
        ("MoveIt move_group", stack.move_group),
        *(
            (f"camera static TF {index}", node)
            for index, node in enumerate(camera_transforms, 1)
        ),
    ):
        supervisor.register_owned(
            action, label=label, required_long_lived=True, started=True
        )
    for index, spawner in enumerate(stack.spawners):
        supervisor.register_owned(
            spawner,
            label=f"controller spawner {_CONTROLLERS[index]}",
            required_long_lived=False,
            started=True,
        )

    event_children = (text_agent, perception, validator)
    exit_children = (
        *event_children,
        *container_cleanup_actions,
        stack.robot_state_publisher,
        stack.simulator,
        *stack.spawners,
        stack.move_group,
        *camera_transforms,
    )
    handlers = _e2e_process_handlers(
        supervisor,
        scene_setup=stack.scene_setup,
        event_children=event_children,
        exit_children=exit_children,
    )
    # Handlers are returned before every process action. Business children are
    # only introduced later by supervisor callbacks.
    return [
        *handlers,
        supervisor.arm_timeout("STACK_READINESS", float(readiness_timeout)),
        *camera_transforms,
        *stack.actions,
    ]


def build_text_pick_agent_e2e_launch_description() -> LaunchDescription:
    """Build the supervised multibackend natural-language MuJoCo E2E graph."""

    share = Path(get_package_share_directory("so101_demo_py"))
    unique = uuid.uuid4().hex
    return LaunchDescription(
        [
            DeclareLaunchArgument("instruction"),
            DeclareLaunchArgument(
                "run_mode", default_value="dry_run", choices=("dry_run", "execute")
            ),
            DeclareLaunchArgument(
                "execute", default_value="false", choices=("true", "false")
            ),
            DeclareLaunchArgument(
                "skip_confirmation", default_value="false", choices=("true", "false")
            ),
            DeclareLaunchArgument(
                "headless", default_value="false", choices=("true", "false")
            ),
            DeclareLaunchArgument(
                "sensor_rendering", default_value="true", choices=("true",)
            ),
            DeclareLaunchArgument("session_id", default_value=unique),
            DeclareLaunchArgument(
                "evidence_file",
                default_value=f"/tmp/so101-text-agent-e2e-{unique}/e2e-result.json",
            ),
            DeclareLaunchArgument("readiness_timeout_s", default_value="90.0"),
            DeclareLaunchArgument(
                "mujoco_scene",
                default_value=str(
                    (share / "assets/mujoco/scene.xml").resolve(strict=True)
                ),
            ),
            DeclareLaunchArgument(
                "mujoco_initial_keyframe",
                default_value="task_start",
                choices=MUJOCO_CUP_KEYFRAMES,
            ),
            DeclareLaunchArgument("perception_startup_timeout_s", default_value="30.0"),
            DeclareLaunchArgument("cup_pose_timeout_s", default_value="45.0"),
            *declare_perception_arguments(default_backend="yolo_seg"),
            OpaqueFunction(function=_configured_text_pick_agent_e2e_actions),
        ]
    )
