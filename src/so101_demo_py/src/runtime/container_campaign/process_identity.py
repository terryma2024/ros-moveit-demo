"""Distinct Host container identity and process identity read inside its namespace."""

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re


def _sha(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _positive(value):
    return type(value) is int and value > 0


@dataclass(frozen=True, slots=True)
class ContainerOwnerKey:
    container_id: str
    docker_started_at: str
    image_digest: str
    launch_generation: int

    def __post_init__(self):
        try:
            if (not _sha(self.container_id) or type(self.image_digest) is not str
                    or not self.image_digest.startswith("sha256:") or not _sha(self.image_digest[7:])
                    or not _positive(self.launch_generation)
                    or type(self.docker_started_at) is not str
                    or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,9})?Z", self.docker_started_at) is None
                    or datetime.fromisoformat(self.docker_started_at).year < 1970):
                raise ValueError("identity")
        except (ValueError, TypeError) as error:
            raise ValueError("CONTAINER_OWNER_KEY_INVALID") from error


@dataclass(frozen=True, slots=True)
class ProcessOwnerKey:
    pid: int
    pgid: int
    started_ticks: int
    argv_sha256: str
    environment_sha256: str

    def __post_init__(self):
        if (not all(_positive(value) for value in (self.pid, self.pgid, self.started_ticks))
                or not _sha(self.argv_sha256) or not _sha(self.environment_sha256)):
            raise ValueError("PROCESS_OWNER_KEY_INVALID")


@dataclass(frozen=True, slots=True)
class ContainerChildBinding:
    container: ContainerOwnerKey
    process: ProcessOwnerKey
    pid_namespace_inode: int
    control_socket: str

    def __post_init__(self):
        if (type(self.container) is not ContainerOwnerKey or type(self.process) is not ProcessOwnerKey
                or not _positive(self.pid_namespace_inode) or type(self.control_socket) is not str
                or not Path(self.control_socket).is_absolute() or ".." in Path(self.control_socket).parts
                or "\x00" in self.control_socket):
            raise ValueError("CONTAINER_CHILD_BINDING_INVALID")


def read_process_owner(pid):
    """Use only in the process's own PID namespace; Host must use Docker identity."""
    from so101_teleop.process_identity import read_identity

    if not _positive(pid):
        raise ValueError("PROCESS_OWNER_KEY_INVALID")
    before = read_identity(pid)
    if not before.live:
        raise ValueError("PROCESS_OWNER_NOT_LIVE")
    values = Path(f"/proc/{pid}/environ").read_bytes().split(b"\x00")
    environment = {}
    for value in values:
        if not value:
            continue
        name, separator, data = value.partition(b"=")
        if not separator:
            raise ValueError("PROCESS_ENVIRONMENT_INVALID")
        key = name.decode("utf-8", "surrogateescape")
        if key in environment:
            raise ValueError("PROCESS_ENVIRONMENT_INVALID")
        environment[key] = data.decode("utf-8", "surrogateescape")
    after = read_identity(pid)
    if ((before.pid, before.pgid, before.start_marker, before.argv_sha256) != (
            after.pid, after.pgid, after.start_marker, after.argv_sha256) or not after.live):
        raise ValueError("PROCESS_OWNER_CHANGED")
    digest = hashlib.sha256(json.dumps(environment, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ProcessOwnerKey(before.pid, before.pgid, before.start_marker, before.argv_sha256, digest)


def process_owner_matches(owner):
    if type(owner) is not ProcessOwnerKey:
        return False
    try:
        return read_process_owner(owner.pid) == owner
    except (OSError, ValueError, RuntimeError):
        return False


def pid_namespace_inode():
    return os.stat("/proc/self/ns/pid").st_ino


def container_key_from_inspect(document, *, launch_generation):
    try:
        if type(document) is not dict or type(document["State"]) is not dict:
            raise ValueError("inspect object")
        return ContainerOwnerKey(document["Id"], document["State"]["StartedAt"],
                                 document["Image"], launch_generation)
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("CONTAINER_INSPECT_IDENTITY_INVALID") from error


def container_exit_proven(owner, document):
    if type(owner) is not ContainerOwnerKey:
        return False
    try:
        if container_key_from_inspect(document, launch_generation=owner.launch_generation) != owner:
            return False
        state = document["State"]
        return (state["Running"] is False and state["Restarting"] is False
                and type(state["Pid"]) is int and state["Pid"] == 0 and state["Status"] == "exited")
    except (KeyError, TypeError, ValueError):
        return False


def shard_stop_proven(binding, receipt, observed_container):
    if type(binding) is not ContainerChildBinding or type(receipt) is not dict:
        return False
    fields = {"schema_version", "kind", "generation", "process_owner", "pid_namespace_inode",
              "goals_stopped", "controllers_stopped", "ros_children_exited", "ros_graph_empty", "forced"}
    try:
        if type(receipt.get("process_owner")) is not dict:
            return False
        process = ProcessOwnerKey(**receipt["process_owner"])
    except (TypeError, ValueError):
        return False
    return (set(receipt) == fields and type(receipt["schema_version"]) is int
        and receipt["schema_version"] == 1 and receipt["kind"] == "shard_stop_receipt"
        and type(receipt["generation"]) is int and receipt["generation"] == binding.container.launch_generation
        and process == binding.process
        and type(receipt["pid_namespace_inode"]) is int
        and receipt["pid_namespace_inode"] == binding.pid_namespace_inode
        and all(receipt[name] is True for name in (
            "goals_stopped", "controllers_stopped", "ros_children_exited", "ros_graph_empty"))
        and receipt["forced"] is False and container_exit_proven(binding.container, observed_container))
