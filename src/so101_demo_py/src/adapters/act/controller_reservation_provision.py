"""Publish one broker identity and capability outside the ROS graph."""

import os
from pathlib import Path
import re
import secrets
import stat


_ROLE_CODES = {"arm": 1, "gripper": 2}
_SESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)


def _process_start_ticks(pid: int) -> int:
    line = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
    fields = line[line.rfind(")") + 2:].split()
    if len(fields) < 20 or fields[0] == "Z":
        raise RuntimeError("CONTROLLER_RESERVATION_PEER_INVALID")
    value = int(fields[19])
    if value <= 0:
        raise RuntimeError("CONTROLLER_RESERVATION_PEER_INVALID")
    return value


def _private_parent(path: Path):
    if (not path.is_absolute() or path != Path(os.path.normpath(path))
            or not path.name or "\x00" in str(path)):
        raise ValueError("CONTROLLER_RESERVATION_PROVISION_PATH_INVALID")
    ancestor = path.parent
    while True:
        info = ancestor.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise PermissionError("CONTROLLER_RESERVATION_PROVISION_PATH_INVALID")
        if ancestor == ancestor.parent:
            break
        ancestor = ancestor.parent
    parent = path.parent.lstat()
    if (parent.st_uid != os.geteuid()
            or stat.S_IMODE(parent.st_mode) != 0o700):
        raise PermissionError("CONTROLLER_RESERVATION_PROVISION_DIRECTORY_INVALID")
    return parent


def write_controller_reservation_provision(
    path: Path, *, role: str, session_id: str,
) -> bytes:
    """Publish a fresh private file once and return its capability in memory."""
    if role not in _ROLE_CODES or not isinstance(session_id, str) or not _SESSION.fullmatch(session_id):
        raise ValueError("CONTROLLER_RESERVATION_PROVISION_SCOPE_INVALID")
    destination = Path(path)
    parent = _private_parent(destination)
    uid, pid = os.geteuid(), os.getpid()
    ticks = _process_start_ticks(pid)
    if not (0 <= uid < 2**32 and 0 < pid < 2**32 and 0 < ticks < 2**64):
        raise RuntimeError("CONTROLLER_RESERVATION_PEER_INVALID")
    capability = secrets.token_bytes(32)
    if not any(capability):
        raise RuntimeError("CONTROLLER_RESERVATION_CAPABILITY_INVALID")
    session = session_id.encode("ascii")
    body = (b"SOPR" + bytes((1, _ROLE_CODES[role], len(session), 0))
            + uid.to_bytes(4, "big") + pid.to_bytes(4, "big")
            + ticks.to_bytes(8, "big") + capability + session)

    directory = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = f".{destination.name}.{secrets.token_hex(8)}.tmp"
    try:
        opened = os.fstat(directory)
        if (opened.st_dev != parent.st_dev or opened.st_ino != parent.st_ino
                or opened.st_uid != uid or stat.S_IMODE(opened.st_mode) != 0o700):
            raise PermissionError("CONTROLLER_RESERVATION_PROVISION_DIRECTORY_INVALID")
        descriptor = os.open(
            temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as output:
                os.fchmod(output.fileno(), 0o600)
                output.write(body)
                output.flush()
                os.fsync(output.fileno())
            os.link(temporary, destination.name,
                    src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
    finally:
        os.close(directory)
    return capability
