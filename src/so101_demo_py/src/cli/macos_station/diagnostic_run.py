"""Argument parsing, process inspection, cleanup and the diagnostic run."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping, Sequence
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import time
import uuid

from so101_demo.cli.macos_station.contracts import (
    _CLI_DEFAULT_TIMEOUT_S,
    DirectControllerObservation,
    StationDiagnosticError,
    StationDiagnosticReport,
    StationMode,
    StationPhase,
    StationProcessHandle,
)
from so101_demo.cli.macos_station.observation import (
    _PendingClient,
    build_station_report,
    classify_observation,
    launch_station_process,
    observe_direct_controllers,
    phase_deadlines,
    resolve_mode,
    station_argv,
    terminate_station_process,
)
from so101_demo.cli.motion_stack_ready import (
    CONTROLLER_MANAGER_SERVICE,
    CONTROLLER_NAMES,
)


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
    parser.add_argument("--farm-contract-receipt", default=None)
    parser.add_argument("--output", default=None)
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
    if options.mode is StationMode.FIXED_DYLIB_FARM_FULL_TASK_STATION:
        # The farm mode owns the whole lifecycle, so it is refused before any spawn when a
        # receipt, a run binding or an output path is missing, and it never accepts the
        # legacy control-set arguments.
        if not all(
            (options.farm_contract_receipt, options.run_binding, options.output)
        ):
            parser.error(
                "FIXED_DYLIB_FARM_FULL_TASK_STATION requires --farm-contract-receipt, "
                "--run-binding and --output"
            )
        if options.control_set_manifest is not None or options.control is not None:
            parser.error(
                "FIXED_DYLIB_FARM_FULL_TASK_STATION does not accept "
                "--control-set-manifest or --control"
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
    launch_pid: int,
    *,
    deadline: float,
    rows_reader: Callable[[], tuple[tuple[int, int, str], ...]] = _process_rows,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> tuple[int, str, tuple[tuple[int, int, str], ...]]:
    last_rows: tuple[tuple[int, int, str], ...] = ()
    while clock() < deadline:
        rows = rows_reader()
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
        sleep(0.1)
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
    from so101_demo.runtime.runtime_closure import read_process_birth_identity

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


def _atomic_write_json(path: Path, document: Mapping[str, object]) -> str:
    """Write one JSON report through a private temporary file, then rename it into place."""

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(document, indent=2, sort_keys=True).encode("utf-8")
    temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, target)
    return hashlib.sha256(encoded).hexdigest()
