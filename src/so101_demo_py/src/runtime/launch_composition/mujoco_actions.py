"""Launch actions of the MuJoCo stack and its execution."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from launch.actions import (
    RegisterEventHandler,
    Shutdown,
)
from launch.event_handlers import OnProcessExit
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile
import yaml

from so101_demo.runtime.launch_composition.common import (
    _CONTROLLERS,
    MUJOCO_CUP_KEYFRAMES,
    _advance_on_success,
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


def _render_mujoco_robot_description(
    share: Path,
    scene: str,
    *,
    headless: bool,
    sensor_rendering: bool | None = None,
    sim_speed_factor: float = -1.0,
    initial_keyframe: str = "task_start",
    platform_name: str | None = None,
    act_profile: bool = False,
) -> str:
    if initial_keyframe not in MUJOCO_CUP_KEYFRAMES:
        raise RuntimeError(f"unsupported MuJoCo initial keyframe: {initial_keyframe}")
    if act_profile and initial_keyframe not in MUJOCO_CUP_KEYFRAMES[:4]:
        raise RuntimeError(f"unsupported ACT initial keyframe: {initial_keyframe}")
    if not isfinite(sim_speed_factor) or (
        sim_speed_factor != -1.0 and sim_speed_factor <= 0.0
    ):
        raise RuntimeError("sim_speed_factor must be -1.0 or finite and positive")
    asset = "assets/mujoco/act/so101.urdf" if act_profile else "assets/mujoco/so101.urdf"
    description = (share / asset).read_text(encoding="utf-8")
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


def _moveit_parameters(share: Path, robot_description: str, *, publish_planning_scene: bool = True) -> dict:
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
        # A monitor that publishes /monitored_planning_scene keeps its scene as a diff of a parent scene and loses the colour of an
        # attached object when the publishing thread pushes and clears that diff; the ACT stack reads no monitored scene.
        "publish_planning_scene": publish_planning_scene,
        "publish_geometry_updates": publish_planning_scene,
        "publish_state_updates": publish_planning_scene,
        "publish_transforms_updates": publish_planning_scene,
        "trajectory_execution.allowed_execution_duration_scaling": 1.5,
        "trajectory_execution.allowed_goal_duration_margin": 1.0,
    }


def _mujoco_stack_actions(
    context,
    share: Path,
    session_id: str,
    *,
    sim_speed_factor: float = -1.0,
    plugin_config_filename: str = "mujoco_plugins.yaml",
    controller_parameters_path: Path | None = None,
    plugin_parameters_path: Path | None = None,
) -> _MujocoStackActions:
    if plugin_config_filename not in {
        "mujoco_plugins.yaml", "act_diagnostic_plugins.yaml", "act_camera_plugins.yaml",
    }:
        raise RuntimeError("unsupported MuJoCo plugin configuration")
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
    act_profile_value = context.launch_configurations.get("act_profile", "false")
    if act_profile_value not in {"true", "false"}:
        raise RuntimeError("act_profile must be true or false")
    act_profile = act_profile_value == "true"
    robot_description = _render_mujoco_robot_description(
        share,
        scene,
        headless=headless,
        sensor_rendering=sensor_rendering,
        sim_speed_factor=sim_speed_factor,
        initial_keyframe=initial_keyframe,
        act_profile=act_profile,
    )
    config = share / ("config/mujoco/act" if act_profile else "config/mujoco")
    for path in (controller_parameters_path, plugin_parameters_path):
        if path is not None and (not path.is_absolute() or path.resolve(strict=True) != path or not path.is_file()):
            raise ValueError("MUJOCO_PARAMETER_PATH_INVALID")
    controllers = str(controller_parameters_path or config / "ros2_controllers.yaml")
    parameters = [
        {"use_sim_time": True, "robot_description": robot_description},
        ParameterFile(controllers, allow_substs=False),
        ParameterFile(str(plugin_parameters_path or config / plugin_config_filename), allow_substs=False),
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
            # the controller manager this talks to runs on the simulation clock, so this must too: with the default
            # (system time) its activation handshakes and `--controller-manager-timeout` are measured against a
            # different clock than the one the manager runs on, and the controllers never settle. It is also what the
            # TF listener in `graceful_shutdown_move_group` was reporting: nodes on two clocks make the simulation
            # time look like it jumps backwards.
            parameters=[{"use_sim_time": True}],
            output="both",
        )
        for controller in (_CONTROLLERS + ("neck_controller",) if act_profile else _CONTROLLERS)
    ]
    move_group = Node(
        package="so101_mujoco_support",
        executable="graceful_shutdown_move_group",
        parameters=[_moveit_parameters(share, robot_description, publish_planning_scene=not act_profile),
                    {"use_sim_time": True}],
        output="both",
    )
    scene_setup = Node(
        package="so101_demo_py",
        executable="scene_setup",
        # its readiness timeout is a duration on the same simulation clock everything else here uses
        parameters=[{"use_sim_time": True, "readiness_timeout_s": float(timeout)}],
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
