"""Publish one broker identity and capability outside the ROS graph."""

import os
from pathlib import Path
import re
import secrets
import stat
from typing import Mapping

from so101_teleop.unified.controller_reservation_paths import (
    controller_reservation_directory, prepare_controller_reservation_directory,
)


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
        linked = False
        own_identity = None
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as output:
                os.fchmod(output.fileno(), 0o600)
                output.write(body)
                output.flush()
                os.fsync(output.fileno())
            own_file = os.stat(temporary, dir_fd=directory, follow_symlinks=False)
            own_identity = (own_file.st_dev, own_file.st_ino)
            os.link(temporary, destination.name,
                    src_dir_fd=directory, dst_dir_fd=directory, follow_symlinks=False)
            linked = True
            os.unlink(temporary, dir_fd=directory)
            os.fsync(directory)
        except BaseException:
            if linked:
                try:
                    current = os.stat(destination.name, dir_fd=directory, follow_symlinks=False)
                except FileNotFoundError:
                    pass
                else:
                    if (current.st_dev, current.st_ino) == own_identity:
                        os.unlink(destination.name, dir_fd=directory)
            raise
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass
    finally:
        os.close(directory)
    return capability


def _remove_owned_provisions(directory: Path, identities: dict[str, tuple[int, int]]) -> None:
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(descriptor)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise PermissionError("CONTROLLER_RESERVATION_PROVISION_DIRECTORY_INVALID")
        for name, identity in identities.items():
            try:
                current = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if ((current.st_dev, current.st_ino) != identity or not stat.S_ISREG(current.st_mode)
                    or current.st_uid != os.geteuid()):
                raise PermissionError("CONTROLLER_RESERVATION_PROVISION_OWNERSHIP_CHANGED")
            os.unlink(name, dir_fd=descriptor)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class ControllerReservationProvisions:
    """Keep one broker's role capabilities in memory until its owned files close."""

    def __init__(self, directory: Path, capabilities: dict[str, bytes],
                 identities: dict[str, tuple[int, int]]) -> None:
        self.directory = directory
        self._capabilities = capabilities
        self._identities = identities
        self._closed = False

    @property
    def capabilities(self) -> dict[str, bytes]:
        if self._closed:
            raise RuntimeError("CONTROLLER_RESERVATION_PROVISIONS_CLOSED")
        return self._capabilities.copy()

    @classmethod
    def publish(cls, environment: Mapping[str, str], session_id: str):
        try:
            root = Path(environment["SO101_ACT_RESERVATION_ROOT"])
            configured = Path(environment["SO101_ACT_CONTROLLER_RESERVATION_DIR"])
            declared_session = environment["SO101_SIMULATION_SESSION_ID"]
            expected = controller_reservation_directory(root, session_id)
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("CONTROLLER_RESERVATION_PROVISION_SCOPE_INVALID") from error
        if declared_session != session_id or configured != expected:
            raise ValueError("CONTROLLER_RESERVATION_PROVISION_SCOPE_INVALID")
        if len(os.fsencode(expected / "gripper.sock")) > 107:
            raise ValueError("CONTROLLER_RESERVATION_SOCKET_PATH_TOO_LONG")
        directory = prepare_controller_reservation_directory(root, session_id)
        capabilities: dict[str, bytes] = {}
        identities: dict[str, tuple[int, int]] = {}
        try:
            for role in ("arm", "gripper"):
                name = f"{role}.provision"
                path = directory / name
                capabilities[role] = write_controller_reservation_provision(
                    path, role=role, session_id=session_id)
                info = path.lstat()
                identities[name] = (info.st_dev, info.st_ino)
        except BaseException:
            _remove_owned_provisions(directory, identities)
            raise
        return cls(directory, capabilities, identities)

    def close(self) -> None:
        if self._closed:
            return
        _remove_owned_provisions(self.directory, self._identities)
        self._capabilities.clear()
        self._closed = True
