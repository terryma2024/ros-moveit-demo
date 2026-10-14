"""Fixed campaign roles, selected GPU and least-privilege Docker launch argv.

This consumes the unified entry's selected resources; it issues no resource
authorization and performs no Docker mutation. A shard's ROS identity is fixed (`act_instance.identity`): the
private network (`--network none`) and private IPC (`--ipc private`) are its only isolation, so neither may change. The image map has exactly head,
teacher and shard entries from the frozen campaign configuration.
"""

from dataclasses import dataclass
import json
import math
from pathlib import Path
import re

from so101_demo.runtime.act_instance.identity import instance_environment
from so101_demo.runtime.container_campaign.paths import _path, build_role_mounts
from so101_demo.runtime.inference.config import _image, _open_regular, calibration_runtime_hash


def _require(condition):
    if not condition:
        raise ValueError("CONTAINER_LAUNCH_INVALID")


def _input_path(value):
    path = _path(value)
    _require(path.is_file() and not any(character in str(path) for character in (",", "\n", "\r")))
    return path


@dataclass(frozen=True, slots=True)
class InferenceLaunchArgs:
    config: Path
    generation: str
    startup_deadline_monotonic_ns: int
    receive_budget_s: float
    head_descriptor: Path | None = None
    head_descriptor_sha256: str | None = None

    def __post_init__(self):
        try:
            _input_path(self.config)
            _require(type(self.generation) is str and bool(re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", self.generation)))
            _require(type(self.startup_deadline_monotonic_ns) is int and self.startup_deadline_monotonic_ns > 0)
            _require(type(self.receive_budget_s) in (int, float)
                     and math.isfinite(self.receive_budget_s) and self.receive_budget_s > 0)
            if self.head_descriptor is None:
                _require(self.head_descriptor_sha256 is None)
            else:
                _input_path(self.head_descriptor)
                _require(calibration_runtime_hash(self.head_descriptor) == self.head_descriptor_sha256)
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("CONTAINER_LAUNCH_INVALID") from error


@dataclass(frozen=True, slots=True)
class ShardLaunchArgs:
    spec: Path
    mujoco_session_id: str

    def __post_init__(self):
        try:
            _input_path(self.spec)
            _require(type(self.mujoco_session_id) is str
                     and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", self.mujoco_session_id) is not None)
        except (OSError, ValueError, TypeError) as error:
            raise ValueError("CONTAINER_LAUNCH_INVALID") from error


def instance_private_environment(owned):
    """The temp, cache and log locations every instance gets inside its own owned root, container or native alike."""
    temporary = owned / "tmp"
    return ["NVIDIA_DRIVER_CAPABILITIES=compute,utility,graphics",
        "TMPDIR="+str(temporary), "TMP="+str(temporary), "TEMP="+str(temporary),
        "PYTHONNOUSERSITE=1", "PYTHONDONTWRITEBYTECODE=1",
        "YOLO_CONFIG_DIR="+str(temporary / "ultralytics"),
        "TORCH_HOME="+str(temporary / "torch"), "HF_HOME="+str(temporary / "huggingface"),
        "XDG_CACHE_HOME="+str(temporary / "cache"), "XDG_CONFIG_HOME="+str(temporary / "config"),
        "MPLCONFIGDIR="+str(temporary / "matplotlib"), "ROS_HOME="+str(temporary / "ros-home"),
        "ROS_LOG_DIR="+str(owned / "ros-logs")]


# A shard is the cheapest thing to lose when the host runs out of memory: its task is retried by the next campaign, an unrelated
# process is not. 900 ranks above the default 0 of the Teacher and Head services and above other user processes (observed
# at 200), and stays below 1000 so the kernel's own "always first" value is left to no one. Docker accepts a positive
# value from an unprivileged client (the daemon applies it); only negative values need CAP_SYS_RESOURCE.
SHARD_OOM_SCORE_ADJ = 900


def build_container_argv(*, role, image, gpu_uuid, host_paths, container_name, uid, gid):
    try:
        _require(role in ("head", "teacher", "shard"))
        _require(type(image) is dict and set(image) == {"head", "teacher", "shard"})
        for record in image.values():
            _image(record)
        _require(image["head"] == image["teacher"])
        _require(type(gpu_uuid) is str and re.fullmatch(
            r"GPU-[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}", gpu_uuid) is not None)
        _require(type(container_name) is str and re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", container_name) is not None)
        _require(type(uid) is int and uid > 0 and type(gid) is int and gid > 0)
        _require(type(host_paths) is dict and set(host_paths) == {
            "owned_root", "approved_inputs", "socket_roots", "config_paths", "entry"})
        owned = _path(host_paths["owned_root"], directory=True)
        entry = host_paths['entry']
        task_output = None
        if role == 'shard':
            _require(type(entry) is ShardLaunchArgs)
            with _open_regular(entry.spec) as stream:
                spec = json.load(stream)
            _require(type(spec) is dict)
            if spec.get('workload_kind') == 'act_collection':
                task_output = owned/'output'
        mounts = build_role_mounts(role, **{name: host_paths[name] for name in (
            "owned_root", "approved_inputs", "socket_roots", "config_paths")},
            task_output_root=task_output)
        temporary = _path(owned / "tmp", directory=True)
        _require((owned.stat().st_uid, owned.stat().st_gid) == (uid, gid))
        _require((temporary.stat().st_uid, temporary.stat().st_gid) == (uid, gid))
        for mount in mounts:
            _require(not any(character in str(path) for path in (mount.source, mount.target)
                             for character in (",", "\n", "\r")))
        environment = instance_private_environment(owned)
        if role == "shard":
            _require(type(entry) is ShardLaunchArgs)
            _require(entry.spec in host_paths["config_paths"])
            command = ["campaign_shard", "--spec", str(entry.spec)]
            environment.extend(instance_environment(mujoco_session_id=entry.mujoco_session_id))
        else:
            _require(type(entry) is InferenceLaunchArgs and entry.config in host_paths["config_paths"])
            _require((entry.head_descriptor is not None) == (role == "head"))
            command = ["campaign_inference", "--config", str(entry.config), "--socket", "/act/ipc/inference.sock",
                "--role", role, "--generation", entry.generation, "--gpu-uuid", gpu_uuid,
                "--startup-deadline-monotonic-ns", str(entry.startup_deadline_monotonic_ns),
                "--receive-budget-s", str(entry.receive_budget_s)]
            if role == "head":
                _require(entry.head_descriptor in host_paths["config_paths"])
                command.extend(["--head-descriptor", str(entry.head_descriptor),
                                "--head-descriptor-sha256", entry.head_descriptor_sha256])
        argv = ["docker", "run", "--detach", "--name", container_name, "--user", f"{uid}:{gid}",
            "--read-only", "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--network", "none", "--ipc", "private", "--restart", "no", "--gpus", "device="+gpu_uuid]
        for value in environment:
            argv.extend(["--env", value])
        for mount in mounts:
            value = f"type=bind,src={mount.source},dst={mount.target}"
            argv.extend(["--mount", value+(",readonly" if mount.read_only else "")])
        if role == "shard":
            argv.extend(["--oom-score-adj", str(SHARD_OOM_SCORE_ADJ)])
        return argv+[image[role]["digest"]]+command
    except (OSError, ValueError, TypeError, KeyError) as error:
        raise ValueError("CONTAINER_LAUNCH_INVALID") from error
