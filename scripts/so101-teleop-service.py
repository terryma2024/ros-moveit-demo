#!/usr/bin/env python3
"""Own one installed SO-101 Teleop/Expert Validation service on macOS or Linux."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid


REPO = Path(__file__).resolve().parent.parent
TERMINAL_CAMPAIGNS = frozenset({
    "COMPLETED", "COMPLETED_WITH_FAILURES", "INFRA_FAILED", "CANCELLED",
})
MAC_MODEL_ROOT = Path(
    "/opt/data/work/so101-evidence/dual-teleop-tailscale/20260923-ff228e71/models"
)
LINUX_PYTHON = Path(
    "/data/work/so101-evidence/full-ut-linux/20260923-5a0b87a8/venv/bin/python"
)


class Refused(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Refused(message)


def defaults(platform: str) -> dict[str, str]:
    if platform == "darwin":
        return {
            "python": "/opt/ros/jazzy/.venv/bin/python",
            "install_prefix": "/opt/data/so101/workspace/install",
            "durable_base": "/opt/data/work/so101-evidence/teleop-service",
            "yolo_weights": str(MAC_MODEL_ROOT / "yolo/best.pt"),
            "grounded_root": str(MAC_MODEL_ROOT / "grounded"),
            "config": "parallel_batch_v4_macos_mps_w2.yaml",
            "coordinator": "so101_macos_service_campaign",
            "domain_id": "225",
            "partition": "so101-teleop-tailscale-mac-225",
        }
    return {
        "python": str(LINUX_PYTHON),
        "install_prefix": str(REPO / "install"),
        "durable_base": "/data/work/so101-evidence/teleop-service",
        "yolo_weights": "/data/work/models/so101-perception/yolo11n-seg-plastic-cup/best.pt",
        "grounded_root": "/data/work/models/so101-perception/grounded-sam-cup-pickplace/bundle",
        "config": "parallel_batch_v3.yaml",
        "coordinator": "so101_parallel_batch",
        "domain_id": "226",
        "partition": "so101-teleop-tailscale-ai-226",
    }


def arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__,
        epilog="Run doctor, then start. Status and cleanup use the recorded PID; cleanup refuses "
               "active campaigns and preserves all logs, models, and evidence. An existing service "
               "started outside this script is never adopted or stopped. Optional paths can be "
               "overridden when the installed environment moves.",
    )
    parser.add_argument("--platform", choices=("darwin", "linux"), required=True)
    parser.add_argument("command", choices=("doctor", "start", "status", "cleanup"))
    parser.add_argument("--host", help="bind address; default: this host's Tailscale IPv4")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--python", type=Path, default=None)
    parser.add_argument("--install-prefix", type=Path, default=None)
    parser.add_argument("--evidence-root", type=Path, default=None)
    parser.add_argument("--yolo-weights", type=Path, default=None)
    parser.add_argument("--grounded-root", type=Path, default=None)
    parser.add_argument("--state-dir", type=Path, default=None)
    parser.add_argument("--domain-id", type=int, default=None)
    parser.add_argument("--partition", default=None)
    return parser.parse_args(argv)


def resolve_options(args: argparse.Namespace) -> dict[str, object]:
    cfg: dict[str, object] = defaults(args.platform)
    for name in ("python", "install_prefix", "yolo_weights", "grounded_root"):
        supplied = getattr(args, name)
        if supplied is not None:
            cfg[name] = str(supplied)
    if args.domain_id is not None:
        cfg["domain_id"] = str(args.domain_id)
    if args.partition is not None:
        cfg["partition"] = args.partition
    cfg["platform"] = args.platform
    cfg["port"] = args.port
    cfg["host"] = args.host or (tailscale_ip() if args.command in ("doctor", "start") else "")
    cfg["state_dir"] = str(args.state_dir or
                           Path.home() / ".local/state" / f"so101-teleop-service-{args.platform}")
    cfg["evidence_root"] = str(args.evidence_root) if args.evidence_root else ""
    return cfg


def tailscale_ip() -> str:
    binary = shutil.which("tailscale")
    require(binary is not None, "TAILSCALE_MISSING: install/start Tailscale or pass --host")
    result = subprocess.run([binary, "ip", "-4"], capture_output=True, text=True, timeout=10)
    require(result.returncode == 0, "TAILSCALE_UNAVAILABLE: tailscale ip -4 failed")
    addresses = result.stdout.strip().splitlines()
    require(len(addresses) == 1 and addresses[0].startswith("100."),
            "TAILSCALE_IP_INVALID: expected one Tailscale IPv4 address")
    return addresses[0]


def layout(cfg: dict[str, object]) -> dict[str, Path]:
    prefix = Path(str(cfg["install_prefix"]))
    demo = prefix / "so101_demo_py"
    teleop = prefix / "so101_teleop"
    return {
        "entry": teleop / "lib/so101_teleop/so101_unified_web_server.py",
        "web": teleop / "share/so101_teleop/web/index.html",
        "config": demo / "share/so101_demo_py/config/mujoco" / str(cfg["config"]),
        "points": demo / "share/so101_demo_py/config/mujoco/moveit_expert_validation_points_v1.yaml",
        "coordinator": demo / "lib/so101_demo_py" / str(cfg["coordinator"]),
        "adaptive_config": demo / "share/so101_demo_py/config/mujoco/parallel_adaptive_workers_v1.yaml",
        "adaptive_wrapper": demo / "lib/so101_demo_py/run_so101_adaptive_batch.zsh",
    }


def setup_files(cfg: dict[str, object]) -> list[Path]:
    if cfg["platform"] == "darwin":
        return [Path("/opt/ros/jazzy/install/setup.zsh"),
                Path("/opt/ros/jazzy/extra_ws/install/setup.zsh"),
                Path("/opt/data/so101/runtime/fork/current/local_setup.zsh"),
                Path(str(cfg["install_prefix"])) / "local_setup.zsh"]
    return [Path("/opt/ros/jazzy/setup.zsh"),
            Path(str(cfg["install_prefix"])) / "setup.zsh"]


def preflight(cfg: dict[str, object]) -> dict[str, Path]:
    require(sys.platform == cfg["platform"],
            f"PLATFORM_MISMATCH: expected {cfg['platform']}, found {sys.platform}")
    require(1 <= int(cfg["port"]) <= 65535, "PORT_INVALID")
    require(0 <= int(str(cfg["domain_id"])) <= 232, "ROS_DOMAIN_ID_INVALID")
    for name in ("python", "install_prefix", "yolo_weights", "grounded_root", "state_dir"):
        require(Path(str(cfg[name])).is_absolute(), f"{name.upper()}_NOT_ABSOLUTE")
    python = Path(str(cfg["python"]))
    require(python.is_file() and os.access(python, os.X_OK), f"PYTHON_MISSING: {python}")
    for path in setup_files(cfg):
        require(path.is_file(), f"ROS_SETUP_MISSING: {path}")
    paths = layout(cfg)
    for name, path in paths.items():
        if name.startswith("adaptive_") and cfg["platform"] == "darwin":
            continue
        require(path.is_file(), f"{name.upper()}_MISSING: {path}")
    require(Path(str(cfg["yolo_weights"])).is_file(),
            f"YOLO_WEIGHTS_MISSING: {cfg['yolo_weights']}")
    require(Path(str(cfg["grounded_root"])).is_dir(),
            f"GROUNDED_ROOT_MISSING: {cfg['grounded_root']}")
    if cfg["platform"] == "darwin":
        farm = Path("/opt/ros/jazzy/dylib_farm/current")
        require(farm.is_dir(), f"DYLIB_FARM_MISSING: {farm}; run scripts/so101-macos.zsh prepare")
    return paths


def child_environment(cfg: dict[str, object], paths: dict[str, Path], root: Path) -> dict[str, str]:
    keep = ("HOME", "USER", "LOGNAME", "LANG", "LC_ALL", "DISPLAY", "XAUTHORITY",
            "WAYLAND_DISPLAY", "XDG_RUNTIME_DIR", "DBUS_SESSION_BUS_ADDRESS")
    env = {key: os.environ[key] for key in keep if key in os.environ}
    env["PATH"] = os.pathsep.join((str(Path(str(cfg["python"])).parent),
                                   "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
                                   "/usr/sbin", "/sbin"))
    env["PYTHONNOUSERSITE"] = "1"
    env["SO101_RUNTIME_PYTHON"] = str(cfg["python"])
    env["SO101_RUNTIME_ENTRY"] = str(paths["entry"])
    env["SO101_UNIFIED_EVIDENCE_ROOT"] = str(root)
    env["SO101_TASK_ROOT"] = str(root)
    env["SO101_VALIDATION_PARALLEL_CONFIG"] = str(paths["config"].resolve())
    env["SO101_VALIDATION_COORDINATOR"] = str(paths["coordinator"].resolve())
    env["SO101_VALIDATION_POINTS"] = str(paths["points"].resolve())
    env["SO101_VALIDATION_YOLO_WEIGHTS"] = str(cfg["yolo_weights"])
    env["SO101_VALIDATION_GROUNDED_ROOT"] = str(cfg["grounded_root"])
    env["ROS_DOMAIN_ID"] = str(cfg["domain_id"])
    env["GZ_PARTITION"] = str(cfg["partition"])
    if cfg["platform"] == "linux":
        env["SO101_VALIDATION_ADAPTIVE_CONFIG"] = str(paths["adaptive_config"].resolve())
        env["SO101_VALIDATION_ADAPTIVE_WRAPPER"] = str(paths["adaptive_wrapper"].resolve())
    else:
        env["GZ_CONFIG_PATH"] = (
            "/opt/homebrew/opt/gz-sim8/share/gz:/opt/homebrew/opt/gz-transport13/share/gz:"
            "/opt/homebrew/opt/gz-msgs10/share/gz:/opt/homebrew/opt/gz-plugin2/share/gz:"
            "/opt/homebrew/opt/sdformat14/share/gz"
        )
        env["GZ_SIM_SYSTEM_PLUGIN_PATH"] = (
            "/opt/ros/jazzy/extra_ws/install/lib:"
            + str(Path(str(cfg["install_prefix"])) / "so101_gazebo_demo_cpp/lib")
        )
    for index, path in enumerate(setup_files(cfg)):
        env[f"SO101_SETUP_{index}"] = str(path)
    env["SO101_SETUP_COUNT"] = str(len(setup_files(cfg)))
    return env


SOURCE_AND_EXEC = r'''set -e
for (( i=0; i<SO101_SETUP_COUNT; i++ )); do
  key="SO101_SETUP_${i}"
  source "${(P)key}"
done
if [[ "$(uname -s)" == Darwin ]]; then
  export DYLD_LIBRARY_PATH=/opt/ros/jazzy/dylib_farm/current
fi
export PATH="${SO101_RUNTIME_PYTHON:h}:$PATH"
exec "$SO101_RUNTIME_PYTHON" "$SO101_RUNTIME_ENTRY" "$@"
'''


def command(cfg: dict[str, object], check: bool = False) -> list[str]:
    web = layout(cfg)["web"].parent
    args = ["/bin/zsh", "-f", "-c", SOURCE_AND_EXEC, "so101-teleop-service",
            "--host", str(cfg["host"]), "--port", str(cfg["port"]),
            "--static-dir", str(web)]
    if check:
        args.append("--check")
    return args


def process_identity(pid: int) -> dict[str, object] | None:
    if sys.platform == "linux":
        proc = Path("/proc") / str(pid)
        try:
            raw = (proc / "stat").read_text()
            fields = raw[raw.rfind(")") + 2:].split()
            argv = (proc / "cmdline").read_bytes().decode(errors="replace").split("\0")[:-1]
            return {"pid": pid, "uid": proc.stat().st_uid,
                    "started": fields[19], "argv": argv, "state": fields[0]}
        except (FileNotFoundError, ProcessLookupError):
            return None
    result = subprocess.run(["/bin/ps", "-o", "lstart=,uid=,state=,command=", "-p", str(pid)],
                            capture_output=True, text=True, timeout=5)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    parts = result.stdout.strip().split(maxsplit=7)
    require(len(parts) == 8, "PROCESS_METADATA_INVALID")
    return {"pid": pid, "uid": int(parts[5]), "started": " ".join(parts[:5]),
            "state": parts[6], "argv": parts[7].split()}


def verify_owned(record: dict[str, object]) -> bool:
    current = process_identity(int(record["pid"]))
    if current is None or str(current["state"]).startswith("Z"):
        return False
    require(current["uid"] == os.getuid(), "OWNER_UID_CHANGED")
    require(current["started"] == record["started"], "OWNER_START_CHANGED")
    argv = current["argv"]
    require(isinstance(argv, list) and len(argv) >= 6 and
            "python" in Path(argv[0]).name.lower() and
            str(Path(argv[1]).resolve()) == str(Path(str(record["entry"])).resolve()) and
            argv[2:6] == ["--host", str(record["host"]), "--port", str(record["port"])],
            "OWNER_COMMAND_CHANGED")
    return True


def read_state(path: Path) -> dict[str, object] | None:
    require(not path.is_symlink(), f"STATE_SYMLINK_REFUSED: {path}")
    if not path.is_file():
        return None
    state = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(state, dict) and state.get("schema") == 1, "STATE_INVALID")
    return state


def write_state(path: Path, state: dict[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        data = json.dumps(state, indent=2, sort_keys=True).encode() + b"\n"
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)


def request_json(url: str, timeout: float = 2) -> object:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(url, timeout=timeout) as response:
        return json.load(response)


def ready(url: str) -> bool:
    try:
        health = request_json(url + "/health")
        if not isinstance(health, dict) or health.get("domains", {}).get("validation") != "ready":
            return False
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url + "/", timeout=2) as response:
            return response.status == 200
    except (OSError, ValueError, urllib.error.URLError):
        return False


def free_port(host: str, port: int) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((host, port))
    except OSError as error:
        raise Refused(f"PORT_UNAVAILABLE: {host}:{port}: {error}") from error
    finally:
        sock.close()


def start(cfg: dict[str, object], state_path: Path) -> None:
    paths = preflight(cfg)
    previous = read_state(state_path)
    if previous and previous.get("running"):
        require(not verify_owned(previous), "ALREADY_RUNNING: use status or cleanup")
        raise Refused("STALE_STATE: use cleanup before start")
    root = Path(str(cfg["evidence_root"])) if cfg["evidence_root"] else (
        Path(str(previous["evidence_root"])) if previous else
        Path(str(cfg["durable_base"])) /
        (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + uuid.uuid4().hex[:8])
    )
    require(root.is_absolute(), "EVIDENCE_ROOT_NOT_ABSOLUTE")
    require(not root.is_symlink(), f"EVIDENCE_ROOT_SYMLINK_REFUSED: {root}")
    approved_base = Path("/opt/data/work/so101-evidence" if cfg["platform"] == "darwin"
                         else "/data/work/so101-evidence")
    require(root.resolve().is_relative_to(approved_base),
            f"EVIDENCE_ROOT_OUTSIDE_DURABLE_BASE: {root}")
    if previous and previous.get("evidence_root") != str(root):
        raise Refused("EVIDENCE_ROOT_CHANGED: retain previous state or use a new --state-dir")
    free_port(str(cfg["host"]), int(cfg["port"]))
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(root, 0o700)
    env = child_environment(cfg, paths, root)
    check = subprocess.run(command(cfg, check=True), env=env, capture_output=True,
                           text=True, timeout=45)
    require(check.returncode == 0 and "SO101_UNIFIED_APP_OK" in check.stdout,
            "APP_CHECK_FAILED: " + (check.stderr or check.stdout)[-600:])
    log_path = root / ("service-" + time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + ".log")
    with log_path.open("ab") as log:
        child = subprocess.Popen(command(cfg), env=env, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    identity = process_identity(child.pid)
    require(identity is not None, "SERVICE_EXITED_EARLY")
    url = f"http://{cfg['host']}:{cfg['port']}"
    try:
        for _ in range(60):
            if child.poll() is not None:
                raise Refused(f"SERVICE_EXITED: rc={child.returncode}; log={log_path}")
            if ready(url):
                break
            time.sleep(0.5)
        else:
            raise Refused(f"SERVICE_NOT_READY: {url}; log={log_path}")
        record: dict[str, object] = {
            "schema": 1, "running": True, "pid": child.pid,
            "uid": os.getuid(), "started": identity["started"],
            "python": str(cfg["python"]), "entry": str(paths["entry"]),
            "host": str(cfg["host"]), "port": int(cfg["port"]),
            "evidence_root": str(root), "log": str(log_path),
            "ros_domain_id": str(cfg["domain_id"]), "gz_partition": str(cfg["partition"]),
        }
        require(verify_owned(record), "SERVICE_IDENTITY_CHANGED_AFTER_START")
        write_state(state_path, record)
    except Exception:
        current = process_identity(child.pid)
        if current and current["uid"] == os.getuid() and current["started"] == identity["started"]:
            argv = current["argv"]
            if isinstance(argv, list) and len(argv) >= 2 and argv[1] == str(paths["entry"]):
                child.send_signal(signal.SIGTERM)
                try:
                    child.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    pass
        raise
    print(json.dumps({"result": "STARTED", **record}, sort_keys=True))


def cleanup(state_path: Path) -> None:
    record = read_state(state_path)
    require(record is not None, "NO_MANAGED_SERVICE: existing service is not owned by this script")
    if not record.get("running"):
        print(json.dumps({"result": "ALREADY_STOPPED", "evidence_root": record["evidence_root"]}))
        return
    if not verify_owned(record):
        record["running"] = False
        write_state(state_path, record)
        print(json.dumps({"result": "ALREADY_EXITED", "evidence_root": record["evidence_root"]}))
        return
    url = f"http://{record['host']}:{record['port']}"
    try:
        campaigns = request_json(url + "/expert-validation/campaigns")
    except (OSError, ValueError, urllib.error.URLError) as error:
        raise Refused(f"CAMPAIGN_STATUS_UNKNOWN: {error}") from error
    require(isinstance(campaigns, list) and all(isinstance(row, dict) for row in campaigns),
            "CAMPAIGN_STATUS_INVALID")
    active = [str(row.get("campaign_id", "unknown")) for row in campaigns
              if row.get("status") not in TERMINAL_CAMPAIGNS or
              row.get("batch_cleanup_complete") is not True]
    require(not active, "CAMPAIGN_ACTIVE: " + ",".join(active))
    pid = int(record["pid"])
    if not verify_owned(record):
        record["running"] = False
        write_state(state_path, record)
        print(json.dumps({"result": "ALREADY_EXITED", "evidence_root": record["evidence_root"]}))
        return
    if sys.platform == "linux":
        try:
            pidfd = os.pidfd_open(pid)
        except ProcessLookupError:
            pidfd = None
        if pidfd is None:
            require(not verify_owned(record), "OWNER_CHANGED_BEFORE_SIGNAL")
            record["running"] = False
            write_state(state_path, record)
            print(json.dumps({"result": "ALREADY_EXITED", "evidence_root": record["evidence_root"]}))
            return
        try:
            if verify_owned(record):
                try:
                    signal.pidfd_send_signal(pidfd, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        finally:
            os.close(pidfd)
    else:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for _ in range(100):
        try:
            owned = verify_owned(record)
        except Refused:
            current = process_identity(pid)
            if current is None or str(current["state"]).startswith("Z"):
                owned = False
            elif current["started"] == record["started"] and not current["argv"]:
                time.sleep(0.1)
                continue
            else:
                raise
        if not owned:
            record["running"] = False
            write_state(state_path, record)
            print(json.dumps({"result": "STOPPED", "pid": pid,
                              "evidence_root": record["evidence_root"]}, sort_keys=True))
            return
        time.sleep(0.1)
    raise Refused(f"STOP_TIMEOUT: PID {pid} still owns the service; no escalation sent")


def status(state_path: Path) -> None:
    record = read_state(state_path)
    require(record is not None, "NO_MANAGED_SERVICE: existing service is not owned by this script")
    alive = verify_owned(record) if record.get("running") else False
    print(json.dumps({"result": "RUNNING" if alive else "STOPPED", **record}, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    try:
        args = arguments(argv)
        cfg = resolve_options(args)
        state_dir = Path(str(cfg["state_dir"]))
        if args.command == "doctor":
            paths = preflight(cfg)
            print(json.dumps({"result": "READY", "platform": cfg["platform"],
                              "host": cfg["host"], "port": cfg["port"],
                              "python": cfg["python"], "install_prefix": cfg["install_prefix"],
                              "config": str(paths["config"]),
                              "yolo_weights": cfg["yolo_weights"],
                              "grounded_root": cfg["grounded_root"]}, sort_keys=True))
            return 0
        require(state_dir.is_absolute() and not state_dir.is_symlink(),
                f"STATE_DIR_INVALID: {state_dir}")
        state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        require(state_dir.stat().st_uid == os.getuid(), f"STATE_DIR_NOT_OWNED: {state_dir}")
        os.chmod(state_dir, 0o700)
        with (state_dir / "lock").open("a+") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            state_path = state_dir / "state.json"
            if args.command == "start":
                start(cfg, state_path)
            elif args.command == "cleanup":
                cleanup(state_path)
            else:
                status(state_path)
        return 0
    except (Refused, json.JSONDecodeError, OSError, subprocess.TimeoutExpired) as error:
        print(f"so101-teleop-service: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
