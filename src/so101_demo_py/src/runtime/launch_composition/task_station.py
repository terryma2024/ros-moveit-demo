"""The task station and ACT execution stack launches."""

from __future__ import annotations

from functools import partial
from pathlib import Path
import platform
import uuid

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    IncludeLaunchDescription,
    OpaqueFunction,
    RegisterEventHandler,
    SetEnvironmentVariable,
    Shutdown,
)
from launch.event_handlers import OnProcessExit, OnProcessStart
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration

from so101_demo.runtime.camera_tf import camera_static_transform_nodes
from so101_demo.runtime.launch_composition.common import _SESSION_ID_PATTERN, MUJOCO_CUP_KEYFRAMES
from so101_demo.runtime.launch_composition.mujoco_actions import _mujoco_stack_actions


def _configured_task_station_actions(context):
    session_id = LaunchConfiguration("session_id").perform(context)
    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise RuntimeError("task station session_id is invalid")
    headless = LaunchConfiguration("headless").perform(context)
    if headless not in {"true", "false"}:
        raise RuntimeError("headless must be true or false")
    sensor_rendering = LaunchConfiguration("sensor_rendering").perform(context)
    if sensor_rendering != "true":
        raise RuntimeError("task station requires sensor_rendering=true")
    evidence_root = Path(
        LaunchConfiguration("task_evidence_root").perform(context)
    )
    if not evidence_root.is_absolute():
        raise RuntimeError("task_evidence_root must be absolute")
    include_teleop = LaunchConfiguration("include_teleop").perform(context)
    if include_teleop not in {"true", "false"}:
        raise RuntimeError("include_teleop must be true or false")
    platform_name = platform.system()
    if headless == "true":
        if platform_name == "Darwin":
            raise RuntimeError("macOS task station requires headless=false")
        if platform_name != "Linux":
            raise RuntimeError("headless task station requires Linux")
        if include_teleop == "true":
            raise RuntimeError("headless task station requires include_teleop=false")
    act_profile = context.launch_configurations.get("act_profile", "false") == "true"
    environment_actions = []
    if act_profile:
        # The ACT profile is the same station with the frozen diagnostic-episode inputs checked before anything starts.
        # There is no command broker and no reservation: the Teacher drives plain JointTrajectoryControllers.
        first_inputs = context.launch_configurations.get("act_diagnostic_episode_inputs", "")
        first_pin = context.launch_configurations.get("act_expected_inputs_sha256", "")
        if bool(first_inputs) != bool(first_pin):
            raise ValueError("EPISODE_INPUTS_IDENTITY_REQUIRED")
        if first_inputs:
            from so101_demo.act.diagnostic_episode_inputs import (
                validate_execution_snapshot_binding,
                verify_frozen_inputs,
            )
            frozen = verify_frozen_inputs(Path(first_inputs))
            if frozen["inputs_sha256"] != first_pin:
                raise ValueError("EPISODE_INPUTS_IDENTITY_MISMATCH")
            if frozen.get("mode") != "preselected_target_diagnostic":
                raise ValueError("EPISODE_INPUTS_DIAGNOSTIC_REQUIRED")
            binding = frozen.get("execution_snapshot")
            if binding is None:
                raise ValueError("EPISODE_EXECUTION_INPUTS_REQUIRED")
            validate_execution_snapshot_binding(binding)
            import hashlib

            from so101_demo.act.execution_snapshot import (
                verify_execution_snapshot,
                verify_installed_station_assets,
            )
            snapshot_root = Path(first_inputs).parent / binding["path"]
            snapshot = verify_execution_snapshot(snapshot_root, expected_sha256=binding["sha256"])
            verify_installed_station_assets(Path(get_package_share_directory("so101_demo_py")), snapshot)
            selected_scene = Path(LaunchConfiguration("mujoco_scene").perform(context))
            frozen_scene = snapshot_root / snapshot["scene_path"]
            if (selected_scene != frozen_scene or selected_scene.is_symlink()
                    or hashlib.sha256(selected_scene.read_bytes()).hexdigest()
                    != snapshot["files"][snapshot["scene_path"]]["sha256"]):
                raise ValueError("EPISODE_FROZEN_SCENE_MISMATCH")
            if (LaunchConfiguration("mujoco_initial_keyframe").perform(context)
                    != snapshot["targets"]["reset_keyframe"]):
                raise ValueError("EPISODE_FROZEN_RESET_KEYFRAME_MISMATCH")
        environment_actions = [SetEnvironmentVariable("SO101_ACT_PROFILE", "1"),
                               SetEnvironmentVariable("SO101_SIMULATION_SESSION_ID", session_id)]
    share = Path(get_package_share_directory("so101_demo_py"))
    stack = _mujoco_stack_actions(
        context, share, session_id,
        sim_speed_factor=1.0 if act_profile else -1.0,
        plugin_config_filename="mujoco_plugins.yaml",
    )
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
        SetEnvironmentVariable("SO101_TASK_EVIDENCE_ROOT", str(evidence_root)),
        *environment_actions,
        *teleop_actions,
        *camera_static_transform_nodes(),
        *stack.actions,
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


def build_task_station_launch_description(*, act_profile: bool = False) -> LaunchDescription:
    """Build one visible persistent MuJoCo/MoveIt/camera-TF task station."""

    share = Path(get_package_share_directory("so101_demo_py"))
    unique = uuid.uuid4().hex
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "headless", default_value="false", choices=("true", "false")
            ),
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
                default_value="false" if act_profile else "true",
                choices=("true", "false"),
            ),
            DeclareLaunchArgument("teleop_port", default_value="8080"),
            DeclareLaunchArgument("readiness_timeout_s", default_value="90.0"),
            DeclareLaunchArgument(
                "mujoco_scene",
                default_value=str(share / ("assets/mujoco/act/scene.xml" if act_profile
                                          else "assets/mujoco/scene.xml")),
            ),
            DeclareLaunchArgument(
                "mujoco_initial_keyframe",
                default_value="task_start",
                choices=MUJOCO_CUP_KEYFRAMES[:4] if act_profile else MUJOCO_CUP_KEYFRAMES,
            ),
            *([DeclareLaunchArgument("act_profile", default_value="true", choices=("true",)),
               DeclareLaunchArgument("act_diagnostic_episode_inputs", default_value=""),
               DeclareLaunchArgument("act_expected_inputs_sha256", default_value="")]
              if act_profile else []),
            OpaqueFunction(function=_configured_task_station_actions),
        ]
    )


def _configured_act_execution_stack_actions(context, *, controller_parameters_path=None, plugin_parameters_path=None):
    """ACT simulation only; the admitted unified child owns command authority."""
    if platform.system() != "Linux" or LaunchConfiguration("headless").perform(context) != "true":
        raise RuntimeError("ACT_STACK_HEADLESS_REQUIRED")
    if LaunchConfiguration("sensor_rendering").perform(context) != "true":
        raise RuntimeError("ACT_STACK_RGB_REQUIRED")
    if LaunchConfiguration("act_profile").perform(context) != "true":
        raise RuntimeError("ACT_STACK_PROFILE_REQUIRED")
    session_id = LaunchConfiguration("session_id").perform(context)
    if not _SESSION_ID_PATTERN.fullmatch(session_id):
        raise RuntimeError("ACT_STACK_SESSION_INVALID")
    evidence_root = Path(LaunchConfiguration("task_evidence_root").perform(context))
    if not evidence_root.is_absolute() or ".." in evidence_root.parts:
        raise RuntimeError("ACT_STACK_ROOT_INVALID")
    scene = Path(LaunchConfiguration("mujoco_scene").perform(context))
    if not scene.is_absolute() or not scene.is_file():
        raise RuntimeError("ACT_STACK_SCENE_INVALID")
    share = Path(get_package_share_directory("so101_demo_py"))
    stack = _mujoco_stack_actions(context, share, session_id, sim_speed_factor=1.0,
        controller_parameters_path=controller_parameters_path, plugin_parameters_path=plugin_parameters_path)
    return [
        SetEnvironmentVariable("SO101_ACT_PROFILE", "1"),
        SetEnvironmentVariable("SO101_TASK_EVIDENCE_ROOT", str(evidence_root)),
        SetEnvironmentVariable("SO101_SIMULATION_SESSION_ID", session_id),
        *camera_static_transform_nodes(),
        *stack.actions,
        RegisterEventHandler(OnProcessExit(
            target_action=stack.simulator,
            on_exit=[Shutdown(reason="ACT execution simulator exited")],
        )),
    ]


def build_act_execution_stack_launch_description() -> LaunchDescription:
    """Create one headless ACT simulator stack with no command broker or UI."""
    share = Path(get_package_share_directory("so101_demo_py"))
    return LaunchDescription([
        DeclareLaunchArgument("headless", default_value="true", choices=("true",)),
        DeclareLaunchArgument("sensor_rendering", default_value="true", choices=("true",)),
        DeclareLaunchArgument("act_profile", default_value="true", choices=("true",)),
        DeclareLaunchArgument("session_id"),
        DeclareLaunchArgument("task_evidence_root"),
        DeclareLaunchArgument("readiness_timeout_s", default_value="90.0"),
        DeclareLaunchArgument(
            "mujoco_scene", default_value=str(share / "assets/mujoco/act/scene.xml"),
        ),
        DeclareLaunchArgument(
            "mujoco_initial_keyframe", default_value="task_start",
            choices=MUJOCO_CUP_KEYFRAMES[:4],
        ),
        OpaqueFunction(function=_configured_act_execution_stack_actions),
    ])
