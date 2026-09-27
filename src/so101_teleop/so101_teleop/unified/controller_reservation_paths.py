"""Locate a private controller registration directory for one simulation run."""

import hashlib
import os
from pathlib import Path
import re
import stat
from typing import Mapping


_SESSION = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}\Z", re.ASCII)
RESERVATION_ROOT_ENV = "SO101_ACT_RESERVATION_ROOT"


def controller_reservation_root(
    campaign_root: Path, environment: Mapping[str, str],
) -> Path:
    campaign = Path(campaign_root)
    selected = Path(environment.get(RESERVATION_ROOT_ENV, str(campaign)))
    if (not campaign.is_absolute() or campaign != Path(os.path.normpath(campaign))
            or not selected.is_absolute() or selected != Path(os.path.normpath(selected))
            or not campaign.is_relative_to(selected)):
        raise ValueError("CONTROLLER_RESERVATION_ROOT_INVALID")
    return selected


def controller_reservation_directory(evidence_root: Path, session_id: str) -> Path:
    root = Path(evidence_root)
    if (not root.is_absolute() or root != Path(os.path.normpath(root))
            or not isinstance(session_id, str) or not _SESSION.fullmatch(session_id)
            or "\x00" in str(root)):
        raise ValueError("CONTROLLER_RESERVATION_SCOPE_INVALID")
    digest = hashlib.sha256(session_id.encode("ascii")).hexdigest()[:16]
    return root / "ipc" / digest


def _open_private_child(parent: int, name: str) -> int:
    created = False
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent)
        created = True
    except FileExistsError:
        pass
    descriptor = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=parent)
    try:
        if created:
            os.fchmod(descriptor, 0o700)
        info = os.fstat(descriptor)
        if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid()
                or stat.S_IMODE(info.st_mode) != 0o700):
            raise PermissionError("CONTROLLER_RESERVATION_DIRECTORY_INVALID")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def prepare_controller_reservation_directory(evidence_root: Path, session_id: str) -> Path:
    directory = controller_reservation_directory(evidence_root, session_id)
    ancestor = directory.parent.parent
    while True:
        info = ancestor.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise PermissionError("CONTROLLER_RESERVATION_ROOT_INVALID")
        if ancestor == ancestor.parent:
            break
        ancestor = ancestor.parent
    if directory.parent.parent.lstat().st_uid != os.geteuid():
        raise PermissionError("CONTROLLER_RESERVATION_ROOT_INVALID")
    root = os.open(directory.parent.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW |
                   os.O_CLOEXEC)
    try:
        ipc = _open_private_child(root, "ipc")
        try:
            run = _open_private_child(ipc, directory.name)
            os.close(run)
        finally:
            os.close(ipc)
    finally:
        os.close(root)
    return directory
