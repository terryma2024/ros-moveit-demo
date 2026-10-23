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
class NativeOwnerKey:
    """The Host identity of a native instance: its process group leader, the instance process itself.

    The five process fields are exactly the instance's own `ProcessOwnerKey`, so the Host can compare what it launched with
    what the instance reports about itself. The instance leads a process group of its own (it is started in a new session)."""

    pid: int
    pgid: int
    started_ticks: int
    argv_sha256: str
    environment_sha256: str
    launch_generation: int

    def __post_init__(self):
        if (not all(_positive(value) for value in (self.pid, self.pgid, self.started_ticks, self.launch_generation))
                or self.pgid != self.pid or not _sha(self.argv_sha256) or not _sha(self.environment_sha256)):
            raise ValueError("NATIVE_OWNER_KEY_INVALID")

    @classmethod
    def from_process(cls, process, *, launch_generation):
        if type(process) is not ProcessOwnerKey:
            raise ValueError("NATIVE_OWNER_KEY_INVALID")
        return cls(process.pid, process.pgid, process.started_ticks, process.argv_sha256, process.environment_sha256,
                   launch_generation)

    def process_key(self):
        return ProcessOwnerKey(self.pid, self.pgid, self.started_ticks, self.argv_sha256, self.environment_sha256)


@dataclass(frozen=True, slots=True)
class ContainerChildBinding:
    """The registered owner of a shard instance, its own process identity and the control socket.

    `container` is the Docker identity of a container instance or the `NativeOwnerKey` of a native one; everything else is the
    same for both: the instance process, the PID namespace it reports and the control socket under the owned root."""

    container: ContainerOwnerKey | NativeOwnerKey
    process: ProcessOwnerKey
    pid_namespace_inode: int
    control_socket: str

    def __post_init__(self):
        if (type(self.container) not in (ContainerOwnerKey, NativeOwnerKey) or type(self.process) is not ProcessOwnerKey
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


NATIVE_EXIT_KIND = "native_instance_exit"
_NATIVE_EXIT_FIELDS = {"schema_version", "kind", "pid", "pgid", "started_ticks", "argv_sha256", "owned_root",
                       "leader_state", "group_members", "marker_survivors", "graph_clear"}
#: How the leader can be gone: no process at the pid, a zombie nobody waited for, or a different process at a reused pid.
NATIVE_LEADER_GONE = ("absent", "zombie", "replaced")


def native_exit_proven(owner, document):
    """Whether `document` proves the exact registered native instance is gone, with nothing left of it.

    Four facts, all read from the operating system and the Host ROS graph when the document was made: the leader is not a
    live process (`leader_state`), its process group has no live member, no process on the Host still carries the
    instance marker of its owned root (descendants in other sessions, such as the ROS stack), and the Host ROS graph on the
    fixed domain has no node. The instance's own stop receipt is a separate proof (`shard_stop_proven`)."""
    if type(owner) is not NativeOwnerKey:
        return False
    try:
        return (type(document) is dict and set(document) == _NATIVE_EXIT_FIELDS
            and type(document["schema_version"]) is int and document["schema_version"] == 1
            and document["kind"] == NATIVE_EXIT_KIND
            and all(type(document[name]) is type(getattr(owner, name)) and document[name] == getattr(owner, name)
                    for name in ("pid", "pgid", "started_ticks", "argv_sha256"))
            and type(document["owned_root"]) is str
            and document["leader_state"] in NATIVE_LEADER_GONE
            and type(document["group_members"]) is list and document["group_members"] == []
            and type(document["marker_survivors"]) is list and document["marker_survivors"] == []
            and document["graph_clear"] is True)
    except (KeyError, TypeError):
        return False


def owner_exit_proven(owner, document):
    """The exit proof of whichever kind of owner this is."""
    if type(owner) is NativeOwnerKey:
        return native_exit_proven(owner, document)
    return container_exit_proven(owner, document)


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
        and receipt["forced"] is False and owner_exit_proven(binding.container, observed_container))
