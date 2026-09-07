"""Common launch arguments and explicit backend-specific action composition."""

from __future__ import annotations

import json
import os
import platform
import re
import signal
import stat
import sys
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass
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
from launch.event_handlers import OnProcessExit, OnProcessIO, OnProcessStart
from launch.events import Shutdown as ShutdownEvent
from launch.events.process import SignalProcess
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import Command, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterFile, ParameterValue

from launch import Action, LaunchDescription

from ..core.task_command import CommandValidationError, validate_instruction
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
from .perception_launch import (
    PerceptionLaunchOptions,
    build_perception_action,
    declare_perception_arguments,
    parse_perception_options,
)
from .workflow_events import (
    EventDecoder,
    EventEmitter,
    WorkflowEvent,
    WorkflowProtocolError,
    WorkflowState,
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


@dataclass(slots=True)
class _OwnedE2EProcess:
    action: ExecuteProcess
    label: str
    required_long_lived: bool
    cleanup_only: bool = False
    started: bool = False
    exited: bool = False


class E2ESupervisor:
    """Drive one E2E graph exclusively from validated child events."""

    _RUNTIME_TIMEOUT_S = 600.0
    _VALIDATOR_TIMEOUT_S = 30.0
    _RECOVERY_TIMEOUT_S = 30.0
    _SIGINT_TIMEOUT_S = 10.0
    _SIGTERM_TIMEOUT_S = 5.0
    _SIGKILL_TIMEOUT_S = 5.0

    def __init__(
        self,
        *,
        workflow_id: str,
        request_id: str,
        session_id: str,
        backend: str,
        source_commit: str,
        installed_prefix: str,
        run_root: Path,
        result_file: Path,
        text_agent_action: ExecuteProcess,
        perception_action: ExecuteProcess,
        validator_action: ExecuteProcess,
        container_cleanup_actions: tuple[ExecuteProcess, ...] = (),
        model_provenance: dict[str, object] | None = None,
        perception_startup_timeout_s: float = 30.0,
        cup_pose_timeout_s: float = 45.0,
        clock_ns=time.time_ns,
    ) -> None:
        self.workflow_id = workflow_id
        self.request_id = request_id
        self.session_id = session_id
        self.backend = backend
        self.source_commit = source_commit
        self.installed_prefix = installed_prefix
        self.run_root = run_root
        self.result_file = result_file
        self.text_agent_action = text_agent_action
        self.perception_action = perception_action
        self.validator_action = validator_action
        self.container_cleanup_actions = container_cleanup_actions
        self.model_provenance = dict(model_provenance or {})
        self.perception_startup_timeout_s = perception_startup_timeout_s
        self.cup_pose_timeout_s = cup_pose_timeout_s
        self._clock_ns = clock_ns
        self.workflow_state = WorkflowState(backend)
        self.current_phase = "STACK_READINESS"
        self.primary_failure: dict[str, object] | None = None
        self.secondary_failures: list[dict[str, object]] = []
        self.shutting_down = False
        self._recovery_pending = False
        self.accepted = False
        self.runtime_exit_code: int | None = None
        self.perception_started = False
        self.validator_started = False
        self._terminal_children: set[int] = set()
        self._events: list[WorkflowEvent] = []
        self._owned: dict[int, _OwnedE2EProcess] = {}
        self._deadline_generations: dict[str, int] = {}
        self._decoders = {
            id(text_agent_action): EventDecoder(
                workflow_id, frozenset({"text_agent", "dynamic_runtime"})
            ),
            id(perception_action): EventDecoder(
                workflow_id, frozenset({"perception"})
            ),
            id(validator_action): EventDecoder(
                workflow_id, frozenset({"e2e_validator"})
            ),
        }
        self.register_owned(
            text_agent_action,
            label="Text Agent and dynamic runtime",
            required_long_lived=False,
        )
        self.register_owned(
            perception_action,
            label="perception",
            required_long_lived=backend == "color_geometry",
        )
        self.register_owned(
            validator_action,
            label="E2E validator",
            required_long_lived=False,
        )
        for cleanup_action in container_cleanup_actions:
            self.register_owned(
                cleanup_action,
                label="owned perception container cleanup",
                required_long_lived=False,
                cleanup_only=True,
            )

    def register_owned(
        self,
        action: ExecuteProcess,
        *,
        label: str,
        required_long_lived: bool,
        started: bool = False,
        cleanup_only: bool = False,
    ) -> None:
        self._owned[id(action)] = _OwnedE2EProcess(
            action=action,
            label=label,
            required_long_lived=required_long_lived,
            cleanup_only=cleanup_only,
            started=started,
        )

    def _atomic_write(self, path: Path, data: bytes) -> None:
        temporary: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="wb", dir=self.run_root, prefix=f".{path.name}.", delete=False
            ) as stream:
                temporary = stream.name
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                try:
                    Path(temporary).unlink()
                except OSError:
                    pass

    def _persist_trace(self) -> None:
        content = b"".join(
            (
                json.dumps(
                    asdict(event),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                + "\n"
            ).encode("utf-8")
            for event in self._events
        )
        self._atomic_write(self.run_root / "workflow-events.ndjson", content)

    def _failure_record(
        self,
        *,
        component: str,
        code: str,
        message: str,
        exit_code: int | None = None,
    ) -> dict[str, object]:
        return {
            "component": component,
            "code": code,
            "phase": self.current_phase,
            "message": message,
            "exit_code": exit_code,
            "timestamp_ns": self._clock_ns(),
        }

    def _record_failure(self, **values) -> None:
        record = self._failure_record(**values)
        if self.primary_failure is None:
            self.primary_failure = record
        else:
            self.secondary_failures.append(record)

    def _artifact_paths(self) -> dict[str, str]:
        return {
            "event_trace": str(self.run_root / "workflow-events.ndjson"),
            "result": str(self.result_file),
            "perception": str(self.run_root / "perception"),
            "dynamic": str(self.run_root / "dynamic"),
            "acceptance": str(self.run_root / "acceptance"),
        }

    def _write_result(self, *, cleanup_complete: bool) -> None:
        acceptance: dict[str, object] = {}
        acceptance_path = self.run_root / "acceptance" / "result.json"
        if acceptance_path.is_file() and not acceptance_path.is_symlink():
            try:
                loaded = json.loads(acceptance_path.read_text(encoding="utf-8"))
                if type(loaded) is dict:
                    acceptance = loaded
            except (OSError, ValueError):
                acceptance = {}
        document = {
            "schema_version": 1,
            "workflow_id": self.workflow_id,
            "request_id": self.request_id,
            "simulation_session_id": self.session_id,
            "source_commit": self.source_commit,
            "installed_prefix": self.installed_prefix,
            "perception_backend": self.backend,
            "model_provenance": self.model_provenance,
            "event_trace": [asdict(event) for event in self._events],
            "primary_failure": self.primary_failure,
            "secondary_failures": self.secondary_failures,
            "runtime_exit_code": self.runtime_exit_code,
            "physical_outcome": acceptance.get("physical_outcome", {}),
            "planning_scene_outcome": acceptance.get(
                "planning_scene_outcome", {}
            ),
            "machine_accepted": self.accepted,
            "owned_process_cleanup": {
                "complete": cleanup_complete,
                "remaining": [
                    owned.label
                    for owned in self._owned.values()
                    if owned.started and not owned.exited
                ],
            },
            "artifact_paths": self._artifact_paths(),
        }
        self._atomic_write(
            self.result_file,
            (json.dumps(document, indent=2, sort_keys=True) + "\n").encode(),
        )

    def arm_timeout(self, phase: str, seconds: float) -> TimerAction:
        generation = self._deadline_generations.get(phase, 0) + 1
        self._deadline_generations[phase] = generation
        return TimerAction(
            period=seconds,
            actions=[
                OpaqueFunction(
                    function=lambda _context: self.on_timeout(phase, generation)
                )
            ],
        )

    def _cancel_timeout(self, phase: str) -> None:
        self._deadline_generations[phase] = (
            self._deadline_generations.get(phase, 0) + 1
        )

    def on_timeout(self, phase: str, generation: int) -> list[Action]:
        if generation != self._deadline_generations.get(phase):
            return []
        if self.shutting_down and phase not in {"SIGINT", "SIGTERM", "SIGKILL"}:
            return []
        if phase == "RECOVERY":
            return self._begin_teardown()
        if phase in {"SIGINT", "SIGTERM", "SIGKILL"}:
            next_signal = {
                "SIGINT": (signal.SIGTERM, "SIGTERM", self._SIGTERM_TIMEOUT_S),
                "SIGTERM": ("SIGKILL", "SIGKILL", self._SIGKILL_TIMEOUT_S),
            }.get(phase)
            self._record_failure(
                component="supervisor",
                code="OWNED_PROCESS_CLEANUP_TIMEOUT",
                message=f"owned processes did not exit after {phase}",
            )
            if next_signal is not None:
                signal_number, next_phase, seconds = next_signal
                return [
                    *self._signal_actions(signal_number),
                    self.arm_timeout(next_phase, seconds),
                ]
            try:
                self._write_result(cleanup_complete=False)
            except OSError:
                pass
            return _terminal_launch_actions(
                "SO-101 E2E owned process cleanup failed", failed=True
            )
        self._record_failure(
            component="supervisor",
            code="WORKFLOW_TIMEOUT",
            message=f"{phase} deadline expired",
        )
        return self._begin_failure_shutdown()

    def _signal_actions(self, signal_number) -> list[Action]:
        actions: list[Action] = []
        for owned in self._owned.values():
            if not owned.started or owned.exited:
                continue
            actions.append(
                EmitEvent(
                    event=SignalProcess(
                        signal_number=signal_number,
                        process_matcher=lambda candidate, target=owned.action: candidate
                        is target,
                    )
                )
            )
        return actions

    def _begin_failure_shutdown(self) -> list[Action]:
        if self.shutting_down or self._recovery_pending:
            return []
        self._recovery_pending = True
        self.current_phase = "RECOVERY"
        # The dynamic runtime owns action-level cancellation/recovery. Let its
        # SIGINT handler finish that bounded recovery before global escalation.
        text = self._owned[id(self.text_agent_action)]
        if not text.started or text.exited:
            return self._begin_teardown()
        return [
            EmitEvent(
                event=SignalProcess(
                    signal_number=signal.SIGINT,
                    process_matcher=lambda candidate: candidate
                    is self.text_agent_action,
                )
            ),
            self.arm_timeout("RECOVERY", self._RECOVERY_TIMEOUT_S),
        ]

    def _begin_teardown(self) -> list[Action]:
        self.shutting_down = True
        self.current_phase = "TEARDOWN"
        actions = self._signal_actions(signal.SIGINT)
        for cleanup_action in self.container_cleanup_actions:
            owned = self._owned[id(cleanup_action)]
            if not owned.started:
                owned.started = True
                actions.append(cleanup_action)
        if not actions:
            return self._finish_cleanup()
        actions.append(self.arm_timeout("SIGINT", self._SIGINT_TIMEOUT_S))
        return actions

    def _finish_cleanup(self) -> list[Action]:
        remaining = [
            item for item in self._owned.values() if item.started and not item.exited
        ]
        if remaining:
            return []
        try:
            self._write_result(cleanup_complete=True)
        except OSError as error:
            self._record_failure(
                component="supervisor",
                code="EVIDENCE_WRITE_FAILED",
                message=str(error),
            )
            return _terminal_launch_actions(
                "SO-101 E2E result write failed", failed=True
            )
        failed = self.primary_failure is not None or not self.accepted
        reason = "SO-101 E2E failed" if failed else "SO-101 E2E accepted"
        return _terminal_launch_actions(reason, failed=failed)

    def on_scene_exit(self, returncode: int) -> list[Action]:
        if returncode != 0:
            self._record_failure(
                component="scene_setup",
                code="SCENE_SETUP_FAILED",
                message="Planning Scene setup failed",
                exit_code=returncode,
            )
            return self._begin_failure_shutdown()
        self._cancel_timeout("STACK_READINESS")
        lines: list[str] = []
        emitter = EventEmitter(
            self.workflow_id, "supervisor", lines.append, self._clock_ns
        )
        event = emitter.emit("STACK_READY", payload={})
        self._events.append(event)
        try:
            self._persist_trace()
            self.workflow_state.accept(event)
        except (OSError, WorkflowProtocolError) as error:
            self._record_failure(
                component="supervisor",
                code=(
                    "EVIDENCE_WRITE_FAILED"
                    if isinstance(error, OSError)
                    else "EVENT_PROTOCOL_INVALID"
                ),
                message=str(error),
            )
            return self._begin_failure_shutdown()
        self.current_phase = "AGENT"
        self._owned[id(self.text_agent_action)].started = True
        return [self.text_agent_action]

    def _actions_for_event(self, event: WorkflowEvent) -> list[Action]:
        effect = self.workflow_state.accept(event)
        self.current_phase = event.event
        if event.status == "ERROR":
            self._terminal_children.add(id(self._action_for_component(event.component)))
        if effect == "FAIL":
            self._record_failure(
                component=event.component,
                code=event.failure_code or "EVENT_PROTOCOL_INVALID",
                message=f"{event.event} reported failure",
            )
            return self._begin_failure_shutdown()
        if event.event == "RUNTIME_STARTED":
            return [self.arm_timeout("RUNTIME", self._RUNTIME_TIMEOUT_S)]
        if effect == "START_PERCEPTION":
            if self.perception_started:
                raise WorkflowProtocolError("perception already started")
            self.perception_started = True
            self._owned[id(self.perception_action)].started = True
            return [
                self.perception_action,
                self.arm_timeout(
                    "PERCEPTION_STARTUP", self.perception_startup_timeout_s
                ),
            ]
        if event.event == "PERCEPTION_READY":
            self._cancel_timeout("PERCEPTION_STARTUP")
            return [self.arm_timeout("CUP_POSE", self.cup_pose_timeout_s)]
        if event.event == "CUP_POSE_PUBLISHED":
            self._cancel_timeout("CUP_POSE")
            self._terminal_children.add(id(self.perception_action))
        if effect == "START_ACCEPTANCE":
            self._cancel_timeout("RUNTIME")
            if self.validator_started:
                raise WorkflowProtocolError("validator already started")
            self.validator_started = True
            self._terminal_children.add(id(self.text_agent_action))
            self._owned[id(self.validator_action)].started = True
            return [
                self.validator_action,
                self.arm_timeout("VALIDATOR", self._VALIDATOR_TIMEOUT_S),
            ]
        if effect == "ACCEPT":
            self._cancel_timeout("VALIDATOR")
            self.accepted = True
            self._terminal_children.add(id(self.validator_action))
            return self._begin_teardown()
        return []

    def _action_for_component(self, component: str) -> ExecuteProcess:
        if component in {"text_agent", "dynamic_runtime"}:
            return self.text_agent_action
        if component == "perception":
            return self.perception_action
        return self.validator_action

    def on_stdout(self, child: ExecuteProcess, chunk: bytes) -> list[Action]:
        decoder = self._decoders.get(id(child))
        if decoder is None:
            self._record_failure(
                component="supervisor",
                code="EVENT_PROTOCOL_INVALID",
                message="stdout received from unregistered child",
            )
            return self._begin_failure_shutdown()
        actions: list[Action] = []
        try:
            for event in decoder.feed(chunk, now_ns=self._clock_ns()):
                self._events.append(event)
                self._persist_trace()
                actions.extend(self._actions_for_event(event))
        except (OSError, WorkflowProtocolError) as error:
            self._record_failure(
                component="supervisor",
                code=(
                    "EVIDENCE_WRITE_FAILED"
                    if isinstance(error, OSError)
                    else "EVENT_PROTOCOL_INVALID"
                ),
                message=getattr(error, "detail", str(error)),
            )
            actions.extend(self._begin_failure_shutdown())
        return actions

    def on_exit(self, child: ExecuteProcess, returncode: int) -> list[Action]:
        owned = self._owned.get(id(child))
        if owned is None:
            return []
        owned.exited = True
        try:
            decoder = self._decoders.get(id(child))
            if decoder is not None:
                decoder.finish(now_ns=self._clock_ns())
        except WorkflowProtocolError as error:
            self._record_failure(
                component=owned.label,
                code="EVENT_PROTOCOL_INVALID",
                message=error.detail,
                exit_code=returncode,
            )
        if child is self.text_agent_action:
            self.runtime_exit_code = returncode
        if owned.cleanup_only:
            if returncode != 0:
                self._record_failure(
                    component=owned.label,
                    code="OWNED_CONTAINER_CLEANUP_FAILED",
                    message="owned container cleanup returned nonzero",
                    exit_code=returncode,
                )
            return self._finish_cleanup() if self.shutting_down else []
        if self.shutting_down:
            return self._finish_cleanup()
        if self._recovery_pending and child is self.text_agent_action:
            if id(child) not in self._terminal_children and returncode != 0:
                self._record_failure(
                    component=owned.label,
                    code="CHILD_EXITED_WITHOUT_TERMINAL_EVENT",
                    message="child exited during recovery without a terminal event",
                    exit_code=returncode,
                )
            return self._begin_teardown()
        if owned.required_long_lived and not self.accepted:
            self._record_failure(
                component=owned.label,
                code="REQUIRED_PROCESS_EXITED",
                message="required process exited before E2E acceptance",
                exit_code=returncode,
            )
            return self._begin_failure_shutdown()
        if id(child) not in self._terminal_children and returncode != 0:
            self._record_failure(
                component=owned.label,
                code="CHILD_EXITED_WITHOUT_TERMINAL_EVENT",
                message="child exited without a valid terminal event",
                exit_code=returncode,
            )
            return self._begin_failure_shutdown()
        if child is self.text_agent_action and id(child) not in self._terminal_children:
            self._record_failure(
                component=owned.label,
                code="CHILD_EXITED_WITHOUT_TERMINAL_EVENT",
                message="Text Agent exited before runtime terminal event",
                exit_code=returncode,
            )
            return self._begin_failure_shutdown()
        return []


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
        Path(execution_identity.package_prefix)
        / "lib"
        / "so101_demo_py"
        / "text_pick_agent"
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
            "--source-commit",
            execution_identity.source_commit,
            "--installed-prefix",
            execution_identity.package_prefix,
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
