"""Own one isolated headless ROS/MuJoCo contact calibration session."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import time

from so101_demo.act.contact_calibration import _canonical, _write_exclusive
from so101_demo.act.contact_diagnostic import build_contact_diagnostic_manifest
from so101_demo.adapters.act.leased_action_client import BrokerConnection

EVIDENCE_PLUGIN_SHA256 = "0e8701975ea394f437bebd1fcd7dfcddde7adb28602f6c25c10e4cacb5ba18a5"
RUNNER_NAMES = ("acquire.py", "stop_proof.py", "reset.py", "run.py")


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _task_processes(domain_id: int, *, proc_root: Path = Path("/proc")) -> list[tuple[int, str]]:
    token = f"ROS_DOMAIN_ID={domain_id}".encode()
    records = []
    for path in proc_root.iterdir():
        if not path.name.isdigit() or int(path.name) == os.getpid():
            continue
        try:
            # This collector launches as the current user. Other owners'
            # /proc environments can be unreadable and cannot be our child.
            if path.stat().st_uid != os.getuid():
                continue
            environment = (path / "environ").read_bytes().split(b"\0")
            if token not in environment:
                continue
            command = (path / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
        except FileNotFoundError:
            continue
        except PermissionError as error:
            # Same-user login managers can be nondumpable. Inspect their
            # readable process identity; all other denials stay fail-closed.
            try:
                status = (path / "status").read_text()
                command_bytes = (path / "cmdline").read_bytes()
            except FileNotFoundError:
                continue
            if any(line.startswith("State:") and line.split()[1] == "Z"
                   for line in status.splitlines()):
                continue
            if (command_bytes.startswith(b"/usr/lib/systemd/systemd\0--user\0") or
                    command_bytes.startswith(b"(sd-pam)\0") or
                    command_bytes.startswith(b"sshd: ")):
                continue
            raise RuntimeError(f"PROC_ENV_UNVERIFIABLE: {path.name}") from error
        records.append((int(path.name), command))
    return records


def _domain_graph(domain_id: int, environment: dict[str, str]) -> str:
    scoped = dict(environment, ROS_DOMAIN_ID=str(domain_id))
    result = subprocess.run(["/opt/ros/jazzy/bin/ros2", "node", "list"],
                            env=scoped, capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise RuntimeError("ROS domain graph read failed: " + result.stderr)
    subprocess.run(["/opt/ros/jazzy/bin/ros2", "daemon", "stop"],
                   env=scoped, capture_output=True, text=True, timeout=15)
    time.sleep(2.)
    return result.stdout


def _status(socket: Path, session_id: str, attempt_id: str) -> dict:
    connection = BrokerConnection(str(socket), timeout_s=3.)
    try:
        return connection.request("status", {
            "owner": "recovery", "session_id": session_id, "attempt_id": attempt_id,
        })
    finally:
        connection.close()


def _await_startup(run: Path, session_id: str) -> dict:
    deadline = time.monotonic() + 35.
    last_error = None
    while time.monotonic() < deadline:
        if (run / "ipc/a").exists():
            try:
                state = _status(run / "ipc/a", session_id, "live-startup")
                if (state["state"] == "IDLE" and state["stop_confirmed"] is True and
                        state["hazard_reason"] is None):
                    return state
            except (OSError, RuntimeError, ValueError) as error:
                last_error = error
        time.sleep(.2)
    raise RuntimeError("live startup stop proof is missing: " + repr(last_error))


def _verify_plugin_and_speed(run: Path, domain_id: int) -> None:
    deadline = time.monotonic() + 10.
    while time.monotonic() < deadline:
        log = (run / "launch.log").read_text(errors="replace")
        match = re.search(r"\[ros2_control_node-4\]: process started with pid \[(\d+)\]", log)
        if match and "Running the simulation at 60.00 percent speed" in log:
            lines = [line for line in (Path("/proc") / match[1] / "maps").read_text().splitlines()
                     if "libso101_simulation_evidence_plugin.so" in line]
            if lines:
                mapped = Path(lines[0].split()[-1])
                digest = hashlib.sha256(mapped.read_bytes()).hexdigest()
                _write_exclusive(run / "plugin-map.txt", ("\n".join(lines) + "\n").encode())
                if digest != EVIDENCE_PLUGIN_SHA256:
                    raise RuntimeError("mapped evidence plugin hash mismatch")
                _write_exclusive(run / "plugin-sha256.txt", (digest + "\n").encode())
                return
        time.sleep(.1)
    raise RuntimeError("mapped evidence plugin or 60 percent sim speed is missing")


def _launch_script(run: Path, install_base: Path, venv_python: Path,
                   domain_id: int, partition: str, session_id: str,
                   scene_path: Path) -> bytes:
    site_packages = venv_python.parent.parent / "lib/python3.12/site-packages"
    values = {
        "run": run, "install": install_base, "site": site_packages,
        "partition": partition, "session": session_id, "scene": scene_path,
    }
    quote = lambda key: shlex.quote(str(values[key]))
    return (f"#!/usr/bin/zsh\nset -o pipefail\n"
            f"source /opt/ros/jazzy/setup.zsh\nsource {quote('install')}/setup.zsh\n"
            f"export PYTHONPATH={quote('site')}:$PYTHONPATH\n"
            f"export ROS_DOMAIN_ID={domain_id} GZ_PARTITION={quote('partition')}\n"
            f"print -r -- \"$$\" > {quote('run')}/launch.pid\n"
            f"/opt/ros/jazzy/bin/ros2 launch so101_demo_py so101_mujoco_act.launch.py "
            f"session_id:={quote('session')} task_evidence_root:={quote('run')} "
            f"act_broker_socket:={quote('run')}/ipc/a "
            f"act_contact_diagnostic_manifest:={quote('run')}/contact-manifest.json "
            f"mujoco_scene:={quote('scene')} headless:=true sensor_rendering:=true "
            f"include_teleop:=false act_calibration_mode:=true "
            f"act_stop_velocity_rad_s:=.002 act_max_age_s:=.2 "
            f"act_submit_lead_s:=.05 act_accept_timeout_s:=.03 "
            f"act_stop_timeout_s:=1 act_permit_ttl_s:=.1 "
            f"> {quote('run')}/launch.log 2>&1\n"
            f"launch_rc=$?\nprint -r -- \"$launch_rc\" > {quote('run')}/launch.exit\n"
            f"exit \"$launch_rc\"\n").encode()


def _run_script(run: Path, name: str, environment: dict[str, str], timeout_s: float) -> None:
    path = run / name
    with (run / f"{path.stem}.log").open("xb") as log:
        result = subprocess.run([sys.executable, str(path)], env=environment,
                                stdout=log, stderr=subprocess.STDOUT, timeout=timeout_s)
        log.flush()
        os.fsync(log.fileno())
    _write_exclusive(run / f"{path.stem}.exit", f"{result.returncode}\n".encode())
    if result.returncode:
        raise RuntimeError(f"live {name} failed with exit {result.returncode}")


def run_live_session(
    run_root: Path, *, scene_path: Path, motion_policy_path: Path,
    plugin_path: Path, regime: str, seed: int, session_id: str,
    attempt_id: str, domain_id: int, partition: str, tmux_name: str,
    install_base: Path, venv_python: Path, source_commit: str,
) -> Path:
    """Start, prove, execute and stop exactly one fresh isolated session."""

    run = Path(run_root).resolve()
    if len(os.fsencode(str(run / "ipc/a"))) > 107:
        raise ValueError("broker Unix socket path exceeds 107 bytes")
    if not (0 <= domain_id <= 232) or not partition or not tmux_name:
        raise ValueError("live domain, partition or tmux identity is invalid")
    for path in (Path("/opt/ros/jazzy/bin/ros2"), Path(venv_python)):
        if not path.is_file() or not os.access(path, os.X_OK):
            raise ValueError(f"live executable is missing: {path}")
    if not (Path(install_base) / "setup.zsh").is_file():
        raise ValueError("live task overlay is missing")
    environment = dict(os.environ, ROS_DOMAIN_ID=str(domain_id), GZ_PARTITION=partition,
                       SO101_ACT_SOURCE_COMMIT=source_commit)
    run.mkdir(mode=0o750)
    _fsync_directory(run.parent)
    (run / "ipc").mkdir(mode=0o750)
    _fsync_directory(run)
    manifest = build_contact_diagnostic_manifest(
        scene_path=scene_path, motion_policy_path=motion_policy_path,
        plugin_path=plugin_path, regime=regime, seed=seed,
        session_id=session_id, attempt_id=attempt_id)
    _write_exclusive(run / "contact-manifest.json", _canonical(manifest) + b"\n")
    runner = Path(__file__).resolve().parent / "live_calibration_runner"
    for name in RUNNER_NAMES:
        _write_exclusive(run / name, (runner / name).read_bytes())
    _write_exclusive(run / "launch.zsh", _launch_script(
        run, Path(install_base), Path(venv_python), domain_id, partition,
        session_id, Path(scene_path)))
    if _domain_graph(domain_id, environment).strip() or _task_processes(domain_id):
        raise RuntimeError("live domain has an existing graph or process")
    if subprocess.run(["tmux", "has-session", "-t", tmux_name],
                      capture_output=True).returncode == 0:
        raise RuntimeError("owned live tmux name already exists")
    _write_exclusive(run / "domain-preflight.txt", b"")
    _write_exclusive(run / "process-preflight.txt", b"")
    started = False
    try:
        subprocess.run(["tmux", "new-session", "-d", "-s", tmux_name,
                        "zsh", str(run / "launch.zsh")], check=True)
        started = True
        startup = _await_startup(run, session_id)
        _write_exclusive(run / "broker-start.json", _canonical(startup) + b"\n")
        _verify_plugin_and_speed(run, domain_id)
        _run_script(run, "reset.py", environment, 70.)
        _run_script(run, "run.py", environment, 120.)
        final = _status(run / "ipc/a", session_id, "live-post-success")
        _write_exclusive(run / "broker-post-success.json", _canonical(final) + b"\n")
        if (final["state"] != "IDLE" or final["stop_confirmed"] is not True or
                final["hazard_reason"] is not None):
            raise RuntimeError("live final stop proof is invalid")
    except BaseException as error:
        _write_exclusive(run / "session-error.json", _canonical({
            "error": repr(error), "time_wall_s": time.time(),
        }) + b"\n")
        raise
    finally:
        if started:
            _write_exclusive(run / "stop-request.txt", b"C-c sent to owned tmux\n")
            subprocess.run(["tmux", "send-keys", "-t", tmux_name, "C-c"],
                           capture_output=True, text=True)
            deadline = time.monotonic() + 15.
            while time.monotonic() < deadline and subprocess.run(
                ["tmux", "has-session", "-t", tmux_name], capture_output=True
            ).returncode == 0:
                time.sleep(.2)
            graph = _domain_graph(domain_id, environment)
            _write_exclusive(run / "domain-post-stop-late.txt", graph.encode())
            processes = _task_processes(domain_id)
            _write_exclusive(run / "process-post-stop-late.txt", _canonical(processes) + b"\n")
            if graph.strip() or processes:
                raise RuntimeError("live stack did not clear after stop")
    return run
