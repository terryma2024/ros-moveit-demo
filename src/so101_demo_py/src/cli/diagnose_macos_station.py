"""Bounded macOS station diagnostic: locate the first bad boundary, do not guess a cause.

Design section 4.2 replaces "wait for the whole motion stack and report a generic timeout"
with layered observation:

* two closed launch modes -- ``MINIMAL_CONTROLLER_MANAGER`` (controller_manager's own
  ``ros2_control_node``, no ``RobotSystem``) and ``ROBOT_SYSTEM_CONTROLLER_MANAGER`` (the
  MuJoCo hardware node with the same robot description and controller/plugin config as the
  station);
* a direct ``/controller_manager/list_controllers`` client that starts as soon as its own
  service is visible, independent of the MoveIt service/action graph;
* structured phases with independent deadlines (``PLUGIN_RESOLVED`` ...
  ``CONTROLLERS_ACTIVE``) and distinct failure codes for DDS invisibility, a bounded call
  timeout, inactive controllers and missing MoveIt services/actions.

The report records what was observed -- server PID/birth identity, loaded images, ROS
domain, the direct call result, the node/service graph and the phase deadlines. It never
declares a root cause from a single observation. Arbitrary launch argv is not accepted: the
CLI only selects one of the two closed modes.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import time
import uuid
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from .motion_stack_ready import (
    CONTROLLER_MANAGER_SERVICE,
    CONTROLLER_NAMES,
    MOVEIT_ACTION_NAMES,
    MOVEIT_SERVICE_NAMES,
)


class StationDiagnosticError(RuntimeError):
    """Fail-closed diagnostic error with a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


class StationMode(StrEnum):
    MINIMAL_CONTROLLER_MANAGER = "MINIMAL_CONTROLLER_MANAGER"
    ROBOT_SYSTEM_CONTROLLER_MANAGER = "ROBOT_SYSTEM_CONTROLLER_MANAGER"


class StationPhase(StrEnum):
    PLUGIN_RESOLVED = "PLUGIN_RESOLVED"
    SIMULATION_ENDPOINT_READY = "SIMULATION_ENDPOINT_READY"
    HARDWARE_INITIALIZING = "HARDWARE_INITIALIZING"
    HARDWARE_READY = "HARDWARE_READY"
    CONTROLLER_MANAGER_SERVICES_READY = "CONTROLLER_MANAGER_SERVICES_READY"
    CONTROLLERS_ACTIVE = "CONTROLLERS_ACTIVE"


_SECOND = 1_000_000_000
PHASE_BUDGETS_NS: Mapping[StationPhase, int] = {
    StationPhase.PLUGIN_RESOLVED: 5 * _SECOND,
    StationPhase.SIMULATION_ENDPOINT_READY: 20 * _SECOND,
    StationPhase.HARDWARE_INITIALIZING: 10 * _SECOND,
    StationPhase.HARDWARE_READY: 10 * _SECOND,
    StationPhase.CONTROLLER_MANAGER_SERVICES_READY: 10 * _SECOND,
    StationPhase.CONTROLLERS_ACTIVE: 30 * _SECOND,
}
HARDWARE_INITIALIZING_BUDGET_NS = PHASE_BUDGETS_NS[StationPhase.HARDWARE_INITIALIZING]
HARDWARE_READY_BUDGET_NS = PHASE_BUDGETS_NS[StationPhase.HARDWARE_READY]

FAILURE_SERVICE_INVISIBLE = "STATION_CONTROLLER_SERVICE_INVISIBLE"
FAILURE_CALL_TIMEOUT = "STATION_CONTROLLER_CALL_TIMEOUT"
FAILURE_CONTROLLERS_NOT_ACTIVE = "STATION_CONTROLLERS_NOT_ACTIVE"
FAILURE_MOVEIT_SERVICES = "STATION_MOVEIT_SERVICES_UNAVAILABLE"
FAILURE_MOVEIT_ACTIONS = "STATION_MOVEIT_ACTIONS_UNAVAILABLE"

_CLI_DEFAULT_TIMEOUT_S = 60.0


@dataclass(frozen=True, slots=True)
class DirectControllerObservation:
    """One bounded direct query of the controller manager, without the MoveIt graph."""

    service_visible: bool
    call_completed: bool
    controllers: Mapping[str, str]
    ros_domain_id: int
    observed_monotonic_ns: int

    def as_document(self) -> dict[str, object]:
        return {
            "service_visible": self.service_visible,
            "call_completed": self.call_completed,
            "controllers": dict(self.controllers),
            "ros_domain_id": self.ros_domain_id,
            "observed_monotonic_ns": self.observed_monotonic_ns,
        }


@dataclass(frozen=True, slots=True)
class PhaseDeadline:
    phase: StationPhase
    deadline_monotonic_ns: int
    observed_monotonic_ns: int | None
    expired: bool

    def as_document(self) -> dict[str, object]:
        return {
            "phase": self.phase.value,
            "deadline_monotonic_ns": self.deadline_monotonic_ns,
            "observed_monotonic_ns": self.observed_monotonic_ns,
            "expired": self.expired,
        }


@dataclass(frozen=True, slots=True)
class StationDiagnosticReport:
    mode: StationMode
    ros_domain_id: int
    observation: DirectControllerObservation
    phases: tuple[PhaseDeadline, ...]
    server_pid: int | None
    server_birth_identity: int | None
    loaded_images: tuple[str, ...]
    node_names: tuple[str, ...]
    service_names: tuple[str, ...]
    failure_code: str | None

    @property
    def last_observed_phase(self) -> StationPhase | None:
        observed = [
            record.phase for record in self.phases if record.observed_monotonic_ns is not None
        ]
        return observed[-1] if observed else None

    def as_document(self) -> dict[str, object]:
        return {
            "mode": self.mode.value,
            "ros_domain_id": self.ros_domain_id,
            "observation": self.observation.as_document(),
            "phases": [record.as_document() for record in self.phases],
            "last_observed_phase": (
                None if self.last_observed_phase is None else self.last_observed_phase.value
            ),
            "server_pid": self.server_pid,
            "server_birth_identity": self.server_birth_identity,
            "loaded_images": list(self.loaded_images),
            "node_names": list(self.node_names),
            "service_names": list(self.service_names),
            "failure_code": self.failure_code,
        }


@dataclass(frozen=True, slots=True)
class StationProcessHandle:
    """The task-owned diagnostic child and the identity read back for it."""

    pid: int
    birth_identity: int
    argv: tuple[str, ...]
    process: object


def resolve_mode(value: str) -> StationMode:
    try:
        return StationMode(value)
    except ValueError as error:
        raise StationDiagnosticError(
            "STATION_LAUNCH_MODE_UNSUPPORTED",
            f"{value!r} is not one of {[mode.value for mode in StationMode]}",
        ) from error


def station_argv(
    mode: StationMode,
    *,
    share_root: Path,
    session_id: str,
    robot_description: str | None = None,
) -> tuple[str, ...]:
    """The closed command line for one diagnostic mode.

    ``MINIMAL_CONTROLLER_MANAGER`` starts controller_manager's own node and therefore loads
    no ``RobotSystem``. ``ROBOT_SYSTEM_CONTROLLER_MANAGER`` starts the same MuJoCo hardware
    node the station uses, with the same controller and plugin configuration.
    """

    if not isinstance(mode, StationMode):
        raise StationDiagnosticError("STATION_LAUNCH_MODE_UNSUPPORTED", str(mode))
    if not session_id:
        raise StationDiagnosticError("STATION_SESSION_ID_REQUIRED", "session id is required")
    if mode is StationMode.MINIMAL_CONTROLLER_MANAGER:
        return (
            "ros2",
            "run",
            "controller_manager",
            "ros2_control_node",
            "--ros-args",
            "-p",
            "use_sim_time:=true",
        )
    config = Path(share_root) / "config" / "mujoco"
    argv = [
        "ros2",
        "run",
        "mujoco_ros2_control",
        "ros2_control_node",
        "--ros-args",
        "-p",
        "use_sim_time:=true",
        "--params-file",
        str(config / "ros2_controllers.yaml"),
        "--params-file",
        str(config / "mujoco_plugins.yaml"),
        "-p",
        f"simulation_session_id:={session_id}",
    ]
    if robot_description is not None:
        argv.extend(["-p", f"robot_description:={robot_description}"])
    return tuple(argv)


def station_robot_description(
    share_root: Path,
    *,
    scene: Path | None = None,
    initial_keyframe: str = "task_start",
    headless: bool = False,
    sensor_rendering: bool = True,
    sim_speed_factor: float = -1.0,
) -> str:
    """Render the same robot description the task station uses (no second code path)."""

    from ..runtime.launch_composition import _render_mujoco_robot_description

    share = Path(share_root)
    resolved_scene = (
        Path(scene) if scene is not None else share / "assets" / "mujoco" / "scene.xml"
    )
    return _render_mujoco_robot_description(
        share,
        str(resolved_scene),
        headless=headless,
        sensor_rendering=sensor_rendering,
        sim_speed_factor=sim_speed_factor,
        initial_keyframe=initial_keyframe,
    )


def observe_direct_controllers(
    client,
    *,
    request_factory: Callable[[], object],
    spin_until_future_complete: Callable[..., object],
    node,
    timeout_s: float,
    ros_domain_id: int,
    clock: Callable[[], int] = time.monotonic_ns,
    pending=None,
) -> DirectControllerObservation:
    """Advance one direct controller query without overlapping requests.

    The query is attempted whenever the client's own service is visible -- the MoveIt
    service/action graph is not consulted here.
    """

    service_visible = bool(client.service_is_ready())
    if pending is None and service_visible:
        pending = client.call_async(request_factory())
    if pending is not None:
        spin_until_future_complete(node, pending, timeout_sec=timeout_s)
        if pending.done():
            response = pending.result()
            if response is not None:
                return DirectControllerObservation(
                    service_visible=service_visible,
                    call_completed=True,
                    controllers={value.name: value.state for value in response.controller},
                    ros_domain_id=ros_domain_id,
                    observed_monotonic_ns=int(clock()),
                )
    return DirectControllerObservation(
        service_visible=service_visible,
        call_completed=False,
        controllers={},
        ros_domain_id=ros_domain_id,
        observed_monotonic_ns=int(clock()),
    )


def classify_observation(
    observation: DirectControllerObservation,
    *,
    moveit_services: Mapping[str, bool],
    moveit_actions: Mapping[str, bool],
    moveit_required: bool = True,
) -> tuple[StationPhase, str | None]:
    """Map one observation to the last structured phase and (if any) its failure code.

    ``moveit_required=False`` reports the controller boundary only; the MoveIt graph is then
    judged by ``motion_stack_ready``, which owns aggregate readiness.
    """

    if not observation.service_visible:
        return StationPhase.HARDWARE_INITIALIZING, FAILURE_SERVICE_INVISIBLE
    if not observation.call_completed:
        return StationPhase.CONTROLLER_MANAGER_SERVICES_READY, FAILURE_CALL_TIMEOUT
    if any(
        observation.controllers.get(name) != "active" for name in CONTROLLER_NAMES
    ):
        return StationPhase.CONTROLLER_MANAGER_SERVICES_READY, FAILURE_CONTROLLERS_NOT_ACTIVE
    if not moveit_required:
        return StationPhase.CONTROLLERS_ACTIVE, None
    if not all(moveit_services.get(name, False) for name in MOVEIT_SERVICE_NAMES):
        return StationPhase.CONTROLLERS_ACTIVE, FAILURE_MOVEIT_SERVICES
    if not all(moveit_actions.get(name, False) for name in MOVEIT_ACTION_NAMES):
        return StationPhase.CONTROLLERS_ACTIVE, FAILURE_MOVEIT_ACTIONS
    return StationPhase.CONTROLLERS_ACTIVE, None


def phase_deadlines(
    *,
    marks: Mapping[StationPhase, int],
    started_monotonic_ns: int,
    now_monotonic_ns: int,
) -> tuple[PhaseDeadline, ...]:
    """Per-phase deadlines chained from the previous phase's observation, not one global one."""

    records: list[PhaseDeadline] = []
    predecessor = int(started_monotonic_ns)
    for phase in StationPhase:
        deadline = predecessor + PHASE_BUDGETS_NS[phase]
        observed = marks.get(phase)
        if observed is None:
            expired = int(now_monotonic_ns) > deadline
            records.append(PhaseDeadline(phase, deadline, None, expired))
            continue
        observed = int(observed)
        records.append(PhaseDeadline(phase, deadline, observed, observed > deadline))
        predecessor = observed
    return tuple(records)


def build_station_report(
    *,
    mode: StationMode,
    ros_domain_id: int,
    observation: DirectControllerObservation,
    phases: Sequence[PhaseDeadline],
    server_pid: int | None = None,
    server_birth_identity: int | None = None,
    loaded_images: Sequence[str] = (),
    node_names: Sequence[str] = (),
    service_names: Sequence[str] = (),
    failure_code: str | None = None,
) -> StationDiagnosticReport:
    return StationDiagnosticReport(
        mode=mode,
        ros_domain_id=int(ros_domain_id),
        observation=observation,
        phases=tuple(phases),
        server_pid=None if server_pid is None else int(server_pid),
        server_birth_identity=(
            None if server_birth_identity is None else int(server_birth_identity)
        ),
        loaded_images=tuple(str(path) for path in loaded_images),
        node_names=tuple(str(name) for name in node_names),
        service_names=tuple(str(name) for name in service_names),
        failure_code=failure_code,
    )


class _PendingClient:
    """Adapter that keeps exactly one direct controller request in flight."""

    def __init__(self, client) -> None:
        self._client = client
        self.pending = None

    def service_is_ready(self) -> bool:
        return bool(self._client.service_is_ready())

    def call_async(self, request):
        self.pending = self._client.call_async(request)
        return self.pending


def launch_station_process(
    argv: Sequence[str], *, environment: Mapping[str, str] | None = None
) -> StationProcessHandle:
    """Start the diagnostic child as an owned process group and read back its identity."""

    from ..runtime.runtime_closure import read_process_birth_identity

    merged = dict(os.environ)
    if environment is not None:
        merged.update(environment)
    child = subprocess.Popen(
        [str(item) for item in argv],
        start_new_session=True,
        env=merged,
    )
    try:
        birth_identity = read_process_birth_identity(int(child.pid))
    except BaseException:
        terminate_station_process(
            StationProcessHandle(int(child.pid), 0, tuple(argv), child)
        )
        raise
    return StationProcessHandle(
        pid=int(child.pid),
        birth_identity=int(birth_identity),
        argv=tuple(str(item) for item in argv),
        process=child,
    )


def terminate_station_process(
    handle: StationProcessHandle, *, timeout_s: float = 10.0
) -> None:
    """Stop exactly the diagnostic child this run started."""

    child = handle.process
    if getattr(child, "poll", lambda: 0)() is not None:
        return
    try:
        os.killpg(handle.pid, signal.SIGINT)
    except (ProcessLookupError, PermissionError):
        return
    try:
        child.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(handle.pid, signal.SIGTERM)
        except (ProcessLookupError, PermissionError):
            return
        child.wait(timeout=timeout_s)


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="so101_diagnose_macos_station")
    parser.add_argument(
        "--mode",
        required=True,
        choices=[mode.value for mode in StationMode],
        help="closed diagnostic mode; arbitrary launch argv is not accepted",
    )
    parser.add_argument("--timeout-s", type=float, default=_CLI_DEFAULT_TIMEOUT_S)
    parser.add_argument("--session-id", default=None)
    parser.add_argument("--share-root", default=None)
    options = parser.parse_args(list(argv) if argv is not None else None)
    if options.timeout_s <= 0.0:
        parser.error("--timeout-s must be positive")
    options.mode = resolve_mode(options.mode)
    return options


def run_diagnostic(
    *,
    mode: StationMode,
    share_root: Path,
    session_id: str,
    ros_domain_id: int,
    timeout_s: float,
    robot_description: str | None = None,
    spawn: Callable[..., StationProcessHandle] = launch_station_process,
    terminate: Callable[..., None] = terminate_station_process,
    clock: Callable[[], int] = time.monotonic_ns,
    rclpy_module=None,
    environment: Mapping[str, str] | None = None,
) -> tuple[StationDiagnosticReport, StationProcessHandle]:
    """Run one bounded diagnostic mode and report the boundary it reached."""

    if rclpy_module is None:  # pragma: no cover - live path
        import rclpy as rclpy_module
    from controller_manager_msgs.srv import ListControllers

    argv = station_argv(
        mode, share_root=share_root, session_id=session_id, robot_description=robot_description
    )
    started = int(clock())
    handle = spawn(argv, environment=environment)
    marks: dict[StationPhase, int] = {StationPhase.PLUGIN_RESOLVED: int(clock())}
    try:
        rclpy_module.init()
        node = rclpy_module.create_node("so101_macos_station_diagnostic")
        try:
            tracker = _PendingClient(
                node.create_client(ListControllers, CONTROLLER_MANAGER_SERVICE)
            )
            deadline = time.monotonic() + max(0.0, float(timeout_s))
            observation = DirectControllerObservation(False, False, {}, ros_domain_id, int(clock()))
            node_names: tuple[str, ...] = ()
            service_names: tuple[str, ...] = ()
            while rclpy_module.ok() and time.monotonic() < deadline:
                remaining = max(0.0, deadline - time.monotonic())
                observation = observe_direct_controllers(
                    tracker,
                    request_factory=ListControllers.Request,
                    spin_until_future_complete=rclpy_module.spin_until_future_complete,
                    node=node,
                    timeout_s=min(1.0, remaining),
                    ros_domain_id=ros_domain_id,
                    clock=clock,
                    pending=tracker.pending,
                )
                node_names = tuple(sorted(node.get_node_names()))
                service_names = tuple(
                    sorted(
                        name for name, _types in node.get_service_names_and_types()
                    )
                )
                if observation.service_visible and (
                    StationPhase.CONTROLLER_MANAGER_SERVICES_READY not in marks
                ):
                    marks[StationPhase.CONTROLLER_MANAGER_SERVICES_READY] = int(clock())
                if observation.call_completed and all(
                    observation.controllers.get(name) == "active"
                    for name in CONTROLLER_NAMES
                ):
                    marks[StationPhase.CONTROLLERS_ACTIVE] = int(clock())
                    break
                rclpy_module.spin_once(node, timeout_sec=0.05)
            _phase, failure_code = classify_observation(
                observation,
                moveit_services={},
                moveit_actions={},
                moveit_required=False,
            )
            return (
                build_station_report(
                    mode=mode,
                    ros_domain_id=ros_domain_id,
                    observation=observation,
                    phases=phase_deadlines(
                        marks=marks,
                        started_monotonic_ns=started,
                        now_monotonic_ns=int(clock()),
                    ),
                    server_pid=handle.pid,
                    server_birth_identity=handle.birth_identity,
                    loaded_images=(),
                    node_names=node_names,
                    service_names=service_names,
                    failure_code=failure_code,
                ),
                handle,
            )
        finally:
            node.destroy_node()
            rclpy_module.shutdown()
    finally:
        terminate(handle)


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    mode = resolve_mode(options.mode)
    session_id = options.session_id or f"diagnostic-{uuid.uuid4().hex}"
    if options.share_root is not None:
        share_root = Path(options.share_root)
    else:  # pragma: no cover - live path
        from ament_index_python.packages import get_package_share_directory

        share_root = Path(get_package_share_directory("so101_demo_py"))
    robot_description = None
    if mode is StationMode.ROBOT_SYSTEM_CONTROLLER_MANAGER:
        robot_description = station_robot_description(share_root)
    report, _handle = run_diagnostic(
        mode=mode,
        share_root=share_root,
        session_id=session_id,
        ros_domain_id=int(os.environ.get("ROS_DOMAIN_ID", "0")),
        timeout_s=options.timeout_s,
        robot_description=robot_description,
    )
    print(json.dumps(report.as_document(), sort_keys=True), flush=True)
    return 0 if report.failure_code is None else 1


if __name__ == "__main__":  # pragma: no cover - console script path
    raise SystemExit(main())


__all__ = [
    "DirectControllerObservation",
    "HARDWARE_INITIALIZING_BUDGET_NS",
    "HARDWARE_READY_BUDGET_NS",
    "PhaseDeadline",
    "StationDiagnosticError",
    "StationDiagnosticReport",
    "StationMode",
    "StationPhase",
    "StationProcessHandle",
    "build_station_report",
    "classify_observation",
    "launch_station_process",
    "main",
    "observe_direct_controllers",
    "parse_arguments",
    "phase_deadlines",
    "resolve_mode",
    "run_diagnostic",
    "station_argv",
    "station_robot_description",
    "terminate_station_process",
]
