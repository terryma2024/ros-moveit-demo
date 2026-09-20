"""Exact process identity and process-group membership, on the platform that is running.

Everything that owns a child process in this package decides from this module: whether a recorded
owner still names the live process it was recorded from, which pids share the owner's process group,
and whether that group is really empty. Those answers must come from the operating system, never
from a parse of something the platform does not guarantee:

* Linux reads ``/proc/<pid>/stat`` and ``/proc/<pid>/cmdline``, where the start time is the process
  start tick (field 22) and argv is the exact vector handed to ``execve``.
* Darwin asks ``libproc`` for the ``proc_bsdinfo`` record, which carries the group id and a start
  time with microsecond resolution, and asks ``sysctl(KERN_PROCARGS2)`` for the exact argv. A
  ``ps -o lstart=`` probe cannot be used for identity: it resolves one second, so two processes
  started in the same second are indistinguishable.

Anything the platform refuses to report raises :class:`ProcessIdentityError`. There is no fallback
that guesses a value: an unreadable identity means "not provably mine", and every caller treats that
as "do not signal, do not reap, do not claim the tree is gone".
"""

from __future__ import annotations

import ctypes
import ctypes.util
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
from typing import Any, Protocol, Sequence

__all__ = [
    "ProcessArgv",
    "ProcessIdentity",
    "ProcessIdentityError",
    "argv_matches",
    "canonical_hash",
    "command_fingerprint",
    "group_has_live_descendants",
    "group_members",
    "identity_alive",
    "read_identity",
]

_ZOMBIE_STATE = "Z"


class ProcessIdentityError(RuntimeError):
    """A process identity cannot be read, or does not describe a live process."""

    def __init__(self, message: str = "PROCESS_IDENTITY_MISMATCH") -> None:
        super().__init__(message)


def canonical_hash(value: Any) -> str:
    """One hashing convention for every identity field, on every platform."""
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    pgid: int
    start_marker: int
    state: str
    argv: tuple[str, ...]
    command_sha256: str
    argv_sha256: str

    @property
    def live(self) -> bool:
        """Only the platform's own state letter decides this; a zombie is not a live owner."""
        return self.state != _ZOMBIE_STATE


def command_fingerprint(argv: Sequence[str]) -> str:
    """The durable fingerprint of a command line: everything after ``argv[0]``.

    ``argv[0]`` is deliberately excluded, because no platform promises to preserve it and at least
    one launcher on this host does not: the venv interpreter reports the resolved framework binary
    instead of the path it was invoked through, and it does so for some launch contexts and not
    others. Hashing the whole vector made a live, correctly owned process look like a different
    process the moment its interpreter re-exec'd, which is a false refusal in the middle of the
    ownership barrier. Every argument after the launcher is preserved byte for byte, so that is what
    this function - and every durable record that stores its result - fingerprints.
    """
    return canonical_hash(list(argv[1:]))


class ProcessArgv(Protocol):
    """Anything that carries the kernel's argv for a process."""

    argv: tuple[str, ...]


def argv_matches(identity: ProcessArgv, requested: Sequence[str]) -> bool:
    """True when ``requested`` names this process, allowing the launcher prefix to differ.

    ``argv[0]`` is not preserved by every launcher. A shebang script becomes ``[interpreter,
    script, *rest]``, and a venv interpreter that re-execs itself reports the resolved binary
    instead of the path that was asked for. What no launcher may change is the argument vector the
    caller asked for, so every argument after ``argv[0]`` must appear as an exact suffix of the
    kernel's argv, and at least the head of the kernel's argv must be the launcher we named.
    """
    requested = list(requested)
    if not requested:
        return False
    tail = requested[1:]
    if not tail:
        # Nothing but a launcher was asked for, so nothing but a launcher may be running.
        return len(identity.argv) == 1
    if len(identity.argv) < len(tail):
        return False
    return list(identity.argv[-len(tail) :]) == tail


def identity_alive(pid: int, start_marker: int, command_sha256: str) -> bool:
    """Prove that a durable owner record still names a live process, without signalling it.

    The three fields together are the identity: a pid that has been recycled cannot also carry the
    same start marker, and a process that re-execs keeps both while still running the command the
    record fingerprints.
    """
    try:
        identity = read_identity(pid)
    except ProcessIdentityError:
        return False
    return (
        identity.live
        and identity.start_marker == start_marker
        and identity.command_sha256 == command_sha256
    )


def read_identity(pid: int) -> ProcessIdentity:
    """Read ``pid`` exactly, or raise; never return a partially known identity."""
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        raise ProcessIdentityError()
    if sys.platform == "darwin":
        return _read_identity_darwin(pid)
    return _read_identity_proc(pid)


def group_members(pgid: int) -> dict[int, str]:
    """Every pid currently in ``pgid`` with its platform state letter."""
    if not isinstance(pgid, int) or isinstance(pgid, bool) or pgid <= 0:
        return {}
    if sys.platform == "darwin":
        return _darwin_group_members(pgid)
    return _proc_group_members(pgid)


def group_has_live_descendants(pgid: int, leader_pid: int) -> bool:
    """True when the group still holds a process other than the leader that is not a zombie.

    A group this module cannot read is reported as holding a descendant: the only claim worth
    failing closed on is "the tree is gone".
    """
    try:
        members = group_members(pgid)
    except ProcessIdentityError:
        return True
    for pid, state in members.items():
        if pid != leader_pid and state != _ZOMBIE_STATE:
            return True
    return False


# -- Linux -----------------------------------------------------------------------------------


def _read_identity_proc(pid: int) -> ProcessIdentity:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        tail = stat[stat.rfind(")") + 2 :].split()
        command_line = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError, OSError) as error:
        raise ProcessIdentityError() from error
    argv = tuple(
        item.decode("utf-8", errors="surrogateescape")
        for item in command_line.rstrip(b"\0").split(b"\0")
    )
    return ProcessIdentity(
        pid=pid,
        pgid=int(tail[2]),
        start_marker=int(tail[19]),
        state=tail[0],
        argv=argv,
        command_sha256=command_fingerprint(argv),
        argv_sha256=canonical_hash(list(argv)),
    )


def _proc_group_members(pgid: int) -> dict[int, str]:
    members: dict[int, str] = {}
    for stat_path in Path("/proc").glob("[0-9]*/stat"):
        try:
            document = stat_path.read_text(encoding="utf-8")
            pid = int(document.split(" ", 1)[0])
            tail = document[document.rfind(")") + 2 :].split()
            if int(tail[2]) == pgid:
                members[pid] = tail[0]
        except (FileNotFoundError, ProcessLookupError, PermissionError, OSError, ValueError):
            continue
    return members


# -- Darwin ----------------------------------------------------------------------------------

# libproc.h: PROC_PIDTBSDINFO. The kernel writes a ``struct proc_bsdinfo``; the fields this module
# reads are at fixed offsets and the call reports how many bytes it wrote, so a short answer is a
# refusal rather than a partially filled record.
_PROC_PIDTBSDINFO = 3
_BSDINFO_MIN_BYTES = 136
_BSDINFO_PID = 12
_BSDINFO_STATUS = 4
_BSDINFO_PGID = 100
_BSDINFO_START_SEC = 120
_BSDINFO_START_USEC = 128
_BSDINFO_BUFFER = 256

# sys/proc.h: the status field maps onto the state letter ``ps`` prints.
_DARWIN_STATES = {1: "I", 2: "R", 3: "S", 4: "T", 5: "Z"}

# sys/sysctl.h: KERN_PROCARGS2 returns ``int argc``, the exec path, then argv.
_CTL_KERN = 1
_KERN_PROCARGS2 = 49
_MAX_ARGV = 4096
_GROUP_BUFFER_PIDS = 256
_MAX_GROUP_PIDS = 65536

_LIBPROC: Any = None
_LIBC: Any = None


def _libproc() -> Any:
    global _LIBPROC
    if _LIBPROC is None:
        library = ctypes.util.find_library("proc") or "/usr/lib/libproc.dylib"
        loaded = ctypes.CDLL(library, use_errno=True)
        loaded.proc_pidinfo.restype = ctypes.c_int
        loaded.proc_pidinfo.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        loaded.proc_listpgrppids.restype = ctypes.c_int
        loaded.proc_listpgrppids.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_int]
        _LIBPROC = loaded
    return _LIBPROC


def _libc() -> Any:
    global _LIBC
    if _LIBC is None:
        _LIBC = ctypes.CDLL(ctypes.util.find_library("c"), use_errno=True)
    return _LIBC


def _darwin_bsdinfo(pid: int) -> dict[str, int]:
    buffer = ctypes.create_string_buffer(_BSDINFO_BUFFER)
    written = _libproc().proc_pidinfo(pid, _PROC_PIDTBSDINFO, 0, buffer, _BSDINFO_BUFFER)
    if written < _BSDINFO_MIN_BYTES:
        # No such process, not ours to read, or a shorter record than this module understands.
        raise ProcessIdentityError()
    raw = buffer.raw[:written]
    return {
        "pid": struct.unpack_from("<I", raw, _BSDINFO_PID)[0],
        "status": struct.unpack_from("<I", raw, _BSDINFO_STATUS)[0],
        "pgid": struct.unpack_from("<I", raw, _BSDINFO_PGID)[0],
        "start": struct.unpack_from("<Q", raw, _BSDINFO_START_SEC)[0] * 1_000_000
        + struct.unpack_from("<Q", raw, _BSDINFO_START_USEC)[0],
    }


def _darwin_argv(pid: int) -> tuple[tuple[str, ...], str]:
    mib = (ctypes.c_int * 3)(_CTL_KERN, _KERN_PROCARGS2, pid)
    size = ctypes.c_size_t(0)
    libc = _libc()
    if libc.sysctl(mib, 3, None, ctypes.byref(size), None, 0) != 0 or size.value <= 4:
        raise ProcessIdentityError()
    buffer = ctypes.create_string_buffer(size.value)
    if libc.sysctl(mib, 3, buffer, ctypes.byref(size), None, 0) != 0:
        raise ProcessIdentityError()
    raw = buffer.raw[: size.value]
    try:
        argc = struct.unpack_from("<i", raw, 0)[0]
        if not 0 < argc <= _MAX_ARGV:
            raise ProcessIdentityError()
        cursor = raw.index(b"\0", 4)
        executable = raw[4:cursor].decode("utf-8", errors="surrogateescape")
        while cursor < len(raw) and raw[cursor] == 0:
            cursor += 1
        argv: list[str] = []
        for _ in range(argc):
            end = raw.index(b"\0", cursor)
            argv.append(raw[cursor:end].decode("utf-8", errors="surrogateescape"))
            cursor = end + 1
    except (ValueError, struct.error) as error:
        raise ProcessIdentityError() from error
    return tuple(argv), executable


def _read_identity_darwin(pid: int) -> ProcessIdentity:
    info = _darwin_bsdinfo(pid)
    argv, _executable = _darwin_argv(pid)
    state = _DARWIN_STATES.get(info["status"])
    if state is None:
        raise ProcessIdentityError()
    if info["pid"] != pid:
        # The kernel answered about a different process than the one that was asked for.
        raise ProcessIdentityError()
    return ProcessIdentity(
        pid=pid,
        pgid=info["pgid"],
        start_marker=info["start"],
        state=state,
        argv=argv,
        command_sha256=command_fingerprint(argv),
        argv_sha256=canonical_hash(list(argv)),
    )


def _darwin_group_members(pgid: int) -> dict[int, str]:
    """Read the group from ``ps``: ``libproc`` reports a zombie as ESRCH and cannot be used here.

    A zombie is still a member of its group but is not a live process, and ``proc_pidinfo``
    refuses to describe one at all, so the group table has to come from the one interface on this
    platform that still reports a zombie's state letter. Every row is validated; a table this
    module cannot parse is a refusal, not an empty group.
    """
    try:
        completed = subprocess.run(
            ["ps", "-A", "-o", "pid=", "-o", "pgid=", "-o", "state="],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise ProcessIdentityError() from error
    if completed.returncode != 0:
        raise ProcessIdentityError()
    members: dict[int, str] = {}
    for line in completed.stdout.splitlines():
        fields = line.split()
        if not fields:
            continue
        if len(fields) != 3 or not fields[0].isdigit() or not fields[1].isdigit() or not fields[2]:
            raise ProcessIdentityError()
        if int(fields[1]) == pgid:
            members[int(fields[0])] = fields[2][0]
    return members
