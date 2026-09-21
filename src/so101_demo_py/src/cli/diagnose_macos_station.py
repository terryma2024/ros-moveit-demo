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
import stat
import subprocess
import sys
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
    FULL_TASK_STATION = "FULL_TASK_STATION"


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


def full_task_station_argv(
    *,
    session_id: str,
    task_evidence_root: Path,
    scene: Path,
    readiness_timeout_s: float = 90.0,
    python_executable: Path,
    ros2_script: Path,
) -> tuple[str, ...]:
    """Return the reviewed fixed full-station argv; no arbitrary launch tokens exist."""

    if not session_id:
        raise StationDiagnosticError("STATION_SESSION_ID_REQUIRED")
    evidence = Path(task_evidence_root)
    scene_path = Path(scene)
    python_path = Path(python_executable)
    ros2_path = Path(ros2_script)
    if not all(
        path.is_absolute()
        for path in (evidence, scene_path, python_path, ros2_path)
    ):
        raise StationDiagnosticError("STATION_BINDING_INVALID", "absolute paths required")
    if readiness_timeout_s <= 0.0:
        raise StationDiagnosticError("STATION_BINDING_INVALID", "readiness timeout")
    return (
        str(python_path),
        str(ros2_path),
        "launch",
        "so101_demo_py",
        "so101_mujoco_task_station.launch.py",
        "headless:=false",
        "sensor_rendering:=true",
        "include_teleop:=false",
        f"session_id:={session_id}",
        f"task_evidence_root:={evidence}",
        f"readiness_timeout_s:={readiness_timeout_s}",
        f"mujoco_scene:={scene_path}",
        "mujoco_initial_keyframe:=task_start",
    )


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
    parser.add_argument("--control-set-manifest", default=None)
    parser.add_argument("--run-binding", default=None)
    parser.add_argument("--control", choices=("N", "P", "F"), default=None)
    options = parser.parse_args(list(argv) if argv is not None else None)
    if options.timeout_s <= 0.0:
        parser.error("--timeout-s must be positive")
    options.mode = resolve_mode(options.mode)
    if options.mode is StationMode.FULL_TASK_STATION and not all(
        (options.control_set_manifest, options.run_binding, options.control)
    ):
        parser.error(
            "FULL_TASK_STATION requires --control-set-manifest, --run-binding and --control"
        )
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


def _process_rows() -> tuple[tuple[int, int, str], ...]:
    completed = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,args="],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise StationDiagnosticError(
            "STATION_PROCESS_COLLECTOR_FAILED", completed.stderr.strip()
        )
    rows: list[tuple[int, int, str]] = []
    for line in completed.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) == 3 and fields[0].isdigit() and fields[1].isdigit():
            rows.append((int(fields[0]), int(fields[1]), fields[2]))
    return tuple(rows)


def _descendants(
    root_pid: int, rows: Sequence[tuple[int, int, str]]
) -> tuple[tuple[int, int, str], ...]:
    by_parent: dict[int, list[tuple[int, int, str]]] = {}
    for row in rows:
        by_parent.setdefault(row[1], []).append(row)
    found: list[tuple[int, int, str]] = []
    frontier = [root_pid]
    seen = {root_pid}
    while frontier:
        parent = frontier.pop()
        for row in by_parent.get(parent, ()):
            if row[0] in seen:
                continue
            seen.add(row[0])
            found.append(row)
            frontier.append(row[0])
    return tuple(found)


def _controller_process(
    launch_pid: int, *, deadline: float
) -> tuple[int, str, tuple[tuple[int, int, str], ...]]:
    last_rows: tuple[tuple[int, int, str], ...] = ()
    while time.monotonic() < deadline:
        rows = _process_rows()
        descendants = _descendants(launch_pid, rows)
        last_rows = descendants
        matches = [
            row
            for row in descendants
            if "mujoco_ros2_control" in row[2]
            and "ros2_control_node" in row[2]
        ]
        if len(matches) == 1:
            return matches[0][0], matches[0][2], descendants
        if len(matches) > 1:
            raise StationDiagnosticError(
                "STATION_CONTROLLER_PROCESS_AMBIGUOUS",
                "; ".join(row[2] for row in matches),
            )
        time.sleep(0.1)
    raise StationDiagnosticError(
        "STATION_CONTROLLER_PROCESS_MISSING",
        "; ".join(row[2] for row in last_rows),
    )


def _command_executable(command: str) -> Path:
    first = command.split(None, 1)[0]
    path = Path(first)
    if not path.is_absolute():
        raise StationDiagnosticError("STATION_CONTROLLER_EXECUTABLE_INVALID", first)
    return path.resolve(strict=True)


def _readiness_argv(manifest) -> tuple[str, ...]:
    relative = "lib/so101_demo_py/motion_stack_ready"
    if relative not in manifest.closure.inventory:
        raise StationDiagnosticError("STATION_READINESS_EXECUTABLE_INVALID", relative)
    candidate = manifest.install_root / relative
    try:
        executable = candidate.resolve(strict=True)
    except OSError as error:
        raise StationDiagnosticError(
            "STATION_READINESS_EXECUTABLE_INVALID", str(candidate)
        ) from error
    if (
        candidate.is_symlink()
        or not executable.is_relative_to(manifest.install_root)
        or not executable.is_file()
        or not os.access(executable, os.X_OK)
    ):
        raise StationDiagnosticError(
            "STATION_READINESS_EXECUTABLE_INVALID", str(candidate)
        )
    return (
        str(manifest.semantic.python_executable),
        str(executable),
        "--timeout-s",
        "90.0",
    )


def _phase_markers(log_text: str, *, ready: bool) -> tuple[str, ...]:
    checks = (
        ("PLUGIN_RESOLVED", "Loaded hardware 'RobotSystem' from plugin"),
        ("SIMULATION_ENDPOINT_READY", "Running MuJoCo UI task on the process main thread"),
        ("HARDWARE_INITIALIZING", "Initialize hardware"),
        ("HARDWARE_READY", "Resource Manager has been successfully initialized"),
        ("CONTROLLER_MANAGER_SERVICES_READY", "Starting Controller Manager services"),
    )
    markers = [name for name, token in checks if token in log_text]
    if ready:
        for name, _token in checks:
            if name not in markers:
                markers.append(name)
        markers.append("CONTROLLERS_ACTIVE")
    order = {phase.value: index for index, phase in enumerate(StationPhase)}
    return tuple(sorted(set(markers), key=order.__getitem__))


def _first_bad_phase(markers: Sequence[str]) -> str | None:
    observed = set(markers)
    for phase in StationPhase:
        if phase.value not in observed:
            return phase.value
    return None


def _identity_alive(pid: int, birth: int) -> bool:
    from ..runtime.runtime_closure import read_process_birth_identity

    try:
        return read_process_birth_identity(pid) == birth
    except Exception:
        return False


def _bounded_cleanup(
    launch,
    identities: Mapping[int, int],
) -> dict[str, object]:
    escalation: list[dict[str, object]] = []
    signals = (
        (signal.SIGINT, 10.0),
        (signal.SIGTERM, 5.0),
        (signal.SIGKILL, 3.0),
    )
    for sent_signal, timeout_s in signals:
        alive = [pid for pid, birth in identities.items() if _identity_alive(pid, birth)]
        if not alive:
            break
        signalled: list[int] = []
        try:
            if launch.poll() is None:
                os.killpg(int(launch.pid), sent_signal)
                signalled.append(int(launch.pid))
        except (ProcessLookupError, PermissionError):
            pass
        for pid in alive:
            if pid == launch.pid or not _identity_alive(pid, identities[pid]):
                continue
            try:
                os.kill(pid, sent_signal)
                signalled.append(pid)
            except (ProcessLookupError, PermissionError):
                continue
        escalation.append({"signal": sent_signal.name, "pids": sorted(set(signalled))})
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            if not any(
                _identity_alive(pid, birth) for pid, birth in identities.items()
            ):
                break
            time.sleep(0.1)
    residue = [
        pid for pid, birth in identities.items() if _identity_alive(pid, birth)
    ]
    return {
        "escalation": escalation,
        "residue_pids": residue,
        "complete": not residue,
    }


def _socket_residue(root: Path) -> tuple[str, ...]:
    sockets: list[str] = []
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = [
            name
            for name in directories
            if not (Path(current) / name).is_symlink()
        ]
        for name in files:
            path = Path(current) / name
            try:
                mode = os.lstat(path).st_mode
            except OSError:
                continue
            if stat.S_ISSOCK(mode):
                sockets.append(str(path))
    return tuple(sorted(sockets))


def run_full_task_station_control(
    *, manifest_path: Path, binding_path: Path, control: str
) -> dict[str, object]:
    """Launch, attest, stop, and classify one manifest-bound full-station control."""

    from ..runtime.macos_dlopen_probe import (
        GateAControlObservation,
        GateARunBinding,
        _closure_dylib_basenames,
        load_binding,
        load_manifest,
        verify_filtered_ros_dylib_farm,
        write_json,
    )
    from ..runtime.runtime_closure import (
        RuntimeClosureError,
        build_runtime_process_attestation,
        default_loaded_image_probe,
        read_process_birth_identity,
        verify_runtime_closure,
    )

    manifest = load_manifest(manifest_path)
    binding = load_binding(binding_path)
    if control != binding.control:
        raise StationDiagnosticError("STATION_CONTROL_MISMATCH", control)
    expected = GateARunBinding.create(
        run_root=binding.run_root,
        session_id=binding.session_id,
        ros_domain_id=binding.ros_domain_id,
        control=control,
        manifest=manifest,
    )
    if (
        expected.expanded_argv != binding.expanded_argv
        or dict(expected.expanded_environment)
        != dict(binding.expanded_environment)
        or expected.normalized_semantic_sha256
        != binding.normalized_semantic_sha256
    ):
        raise StationDiagnosticError("STATION_SEMANTIC_DRIFT")
    expected_argv = full_task_station_argv(
        session_id=binding.session_id,
        task_evidence_root=binding.task_evidence_root,
        scene=manifest.scene_path,
        readiness_timeout_s=90.0,
        python_executable=manifest.semantic.python_executable,
        ros2_script=manifest.semantic.ros2_script,
    )
    if binding.expanded_argv != expected_argv:
        raise StationDiagnosticError("STATION_SEMANTIC_DRIFT", "argv")
    verify_filtered_ros_dylib_farm(
        manifest.ros_dylib_farm,
        excluded_basenames=_closure_dylib_basenames(manifest.closure),
    )
    verify_runtime_closure(
        manifest.closure,
        install_root=manifest.install_root,
        source_commit=manifest.closure.source_commit,
        mujoco_ros2_control_commit=manifest.closure.mujoco_ros2_control_commit,
        environment=manifest.semantic.environment,
    )
    intent_path = binding.run_root / "controller-runtime-spawn-intent.json"
    write_json(
        intent_path,
        {
            "role": "controller_runtime",
            "ancestor_role": "full_task_station_launcher",
            "executable_pattern": "mujoco_ros2_control/ros2_control_node",
            "manifest_sha256": manifest.sha256,
        },
    )
    stdout_path = binding.run_root / "station.stdout.log"
    stderr_path = binding.run_root / "station.stderr.log"
    identities: dict[int, int] = {}
    controller_attestation = None
    controller_identity: dict[str, object] | None = None
    collector_healthy = True
    invalid_reasons: list[str] = []
    timed_out = False
    readiness_document: dict[str, object] = {}
    with stdout_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
        "w", encoding="utf-8"
    ) as stderr:
        launch = subprocess.Popen(
            list(binding.expanded_argv),
            env=dict(binding.expanded_environment),
            stdout=stdout,
            stderr=stderr,
            text=True,
            start_new_session=True,
        )
        launch_birth = read_process_birth_identity(int(launch.pid))
        identities[int(launch.pid)] = launch_birth
        try:
            controller_pid, controller_command, descendants = _controller_process(
                int(launch.pid), deadline=time.monotonic() + 30.0
            )
            for pid, _parent, _command in descendants:
                try:
                    identities[pid] = read_process_birth_identity(pid)
                except RuntimeClosureError:
                    continue
            controller_birth_before = read_process_birth_identity(controller_pid)
            identities[controller_pid] = controller_birth_before
            controller_executable = _command_executable(controller_command)
            readiness = subprocess.run(
                _readiness_argv(manifest),
                check=False,
                capture_output=True,
                text=True,
                env=dict(binding.expanded_environment),
                timeout=100.0,
            )
            for line in reversed(readiness.stdout.splitlines()):
                if line.startswith("{"):
                    readiness_document = json.loads(line)
                    break
            ready = bool(readiness.returncode == 0 and readiness_document.get("ready"))
            loaded_images = default_loaded_image_probe(controller_pid)
            controller_birth_after = read_process_birth_identity(controller_pid)
            controller_identity = {
                "role": "controller_runtime",
                "pid": controller_pid,
                "birth_identity_before": controller_birth_before,
                "birth_identity_after": controller_birth_after,
                "executable": str(controller_executable),
                "command": controller_command,
            }
            try:
                controller_attestation = build_runtime_process_attestation(
                    closure=manifest.closure,
                    install_root=manifest.install_root,
                    role="controller_runtime",
                    pid=controller_pid,
                    birth_identity_before=controller_birth_before,
                    birth_identity_after=controller_birth_after,
                    executable=controller_executable,
                    loaded_images=loaded_images,
                    required_relative_paths=(
                        manifest.plugin_relative_path,
                        manifest.vendor_relative_path,
                    ),
                )
            except RuntimeClosureError as error:
                if ready:
                    invalid_reasons.append(error.code)
        except subprocess.TimeoutExpired:
            timed_out = True
            ready = False
            invalid_reasons.append("READINESS_SUBPROCESS_TIMEOUT")
        except StationDiagnosticError as error:
            ready = False
            collector_healthy = error.code != "STATION_PROCESS_COLLECTOR_FAILED"
            invalid_reasons.append(error.code)
        finally:
            stdout.flush()
            stderr.flush()
            try:
                rows = _process_rows()
                for pid, _parent, _command in _descendants(int(launch.pid), rows):
                    try:
                        identities.setdefault(pid, read_process_birth_identity(pid))
                    except RuntimeClosureError:
                        continue
            except StationDiagnosticError:
                collector_healthy = False
                invalid_reasons.append("STATION_PROCESS_COLLECTOR_FAILED")
            cleanup = _bounded_cleanup(launch, identities)
    log_text = stdout_path.read_text(encoding="utf-8", errors="replace") + "\n" + stderr_path.read_text(
        encoding="utf-8", errors="replace"
    )
    markers = _phase_markers(log_text, ready=ready)
    dlopen_path = binding.run_root / "dlopen.json"
    if not dlopen_path.is_file():
        invalid_reasons.append("DLOPEN_OBSERVATION_MISSING")
        dlopen_document: dict[str, object] = {}
    else:
        dlopen_document = json.loads(dlopen_path.read_text(encoding="utf-8"))
    marker_list = dlopen_document.get("markers", [])
    dlopen_marker = marker_list[-1] if marker_list else None
    loader_error = dlopen_document.get("dlerror")
    vendor_token = "@rpath/libmujoco.3.4.0.dylib"
    exact_vendor_missing = bool(
        dlopen_marker == "DLOPEN_FAILED"
        and isinstance(loader_error, str)
        and vendor_token in loader_error
        and vendor_token in log_text
    )
    cleanup_complete = bool(cleanup["complete"])
    sockets = _socket_residue(binding.run_root)
    if sockets:
        cleanup_complete = False
        invalid_reasons.append("IPC_RESIDUE")
    plugin_attested = False
    vendor_attested = False
    if controller_attestation is not None:
        attested_paths = {
            item.relative_path for item in controller_attestation.loaded_images
        }
        plugin_attested = manifest.plugin_relative_path in attested_paths
        vendor_attested = manifest.vendor_relative_path in attested_paths
    process_stable = bool(
        controller_identity
        and controller_identity["birth_identity_before"]
        == controller_identity["birth_identity_after"]
    )
    executable_attested = bool(
        controller_identity
        and Path(str(controller_identity["executable"])).is_relative_to(
            manifest.install_root
        )
    )
    first_bad = None if ready else _first_bad_phase(markers)
    observation = GateAControlObservation(
        invariants_valid=not invalid_reasons,
        collector_healthy=collector_healthy,
        process_identity_stable=process_stable,
        controller_role_attested=controller_identity is not None,
        controller_executable_attested=executable_attested,
        dlopen_marker=dlopen_marker,
        loader_error=(None if loader_error is None else str(loader_error)),
        exact_vendor_missing=exact_vendor_missing,
        plugin_image_attested=plugin_attested,
        vendor_image_attested=vendor_attested,
        ros_instance_markers=markers,
        ready=ready,
        first_bad_phase=first_bad,
        timed_out=timed_out,
        cleanup_complete=cleanup_complete,
        invalid_reasons=tuple(sorted(set(invalid_reasons))),
    )
    report = {
        "schema_version": 1,
        "control": control,
        "manifest_sha256": manifest.sha256,
        "binding": binding.as_document(),
        "spawn_intent": str(intent_path),
        "controller_identity": controller_identity,
        "runtime_process_attestation": (
            None
            if controller_attestation is None
            else controller_attestation.as_document()
        ),
        "readiness": readiness_document,
        "phase_markers": list(markers),
        "cleanup": cleanup,
        "ipc_residue": list(sockets),
        "control_observation": observation.as_document(),
        "observation_class": observation.observation_class.value,
    }
    write_json(binding.report_path, report)
    write_json(binding.run_root / "control-observation.json", observation.as_document())
    return report


def main(arguments: Sequence[str] | None = None) -> int:
    options = parse_arguments(arguments)
    mode = resolve_mode(options.mode)
    if mode is StationMode.FULL_TASK_STATION:
        report = run_full_task_station_control(
            manifest_path=Path(options.control_set_manifest),
            binding_path=Path(options.run_binding),
            control=options.control,
        )
        print(json.dumps(report, sort_keys=True), flush=True)
        return 0 if report["observation_class"] == "PASS" else 1
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
    "run_full_task_station_control",
    "station_argv",
    "full_task_station_argv",
    "station_robot_description",
    "terminate_station_process",
]
