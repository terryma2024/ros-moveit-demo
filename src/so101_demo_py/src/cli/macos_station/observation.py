"""Station argv, direct controller observation, phase deadlines, the report and the station process."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
import os
from pathlib import Path
import signal
import subprocess
import time

from so101_demo.cli.macos_station.contracts import (
    FAILURE_CALL_TIMEOUT,
    FAILURE_CONTROLLERS_NOT_ACTIVE,
    FAILURE_MOVEIT_ACTIONS,
    FAILURE_MOVEIT_SERVICES,
    FAILURE_SERVICE_INVISIBLE,
    PHASE_BUDGETS_NS,
    DirectControllerObservation,
    PhaseDeadline,
    StationDiagnosticError,
    StationDiagnosticReport,
    StationMode,
    StationPhase,
    StationProcessHandle,
)
from so101_demo.cli.motion_stack_ready import (
    CONTROLLER_NAMES,
    MOVEIT_ACTION_NAMES,
    MOVEIT_SERVICE_NAMES,
)


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

    from so101_demo.runtime.launch_composition import _render_mujoco_robot_description

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

    from so101_demo.runtime.runtime_closure import read_process_birth_identity

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
