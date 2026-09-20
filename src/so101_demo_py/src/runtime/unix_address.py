"""The private-path Unix address strategy and its exact cleanup contract.

Task 4 of the macOS MPS / private IPC plan. The production Linux transport addresses its sockets
through ``/proc/self/fd/<dirfd>/<name>``, which pins the parent directory against replacement.
Darwin has no ``bindat``/``connectat`` and ``/dev/fd/<dirfd>/<name>`` returns ``ENOENT`` (proved
in the retained probe recorded as CP-UQ226), so the macOS transport instead uses a canonical
private directory whose access control is the filesystem itself:

    <private-tmp>/so101-ipc-<uid>/         owned by the user, mode 0700, not a symlink
      b-<random-short-id>/                 fresh per campaign, mode 0700
        coordinator.sock                   mode 0600
        broker.sock
        w1.sock
        w2.sock

``<private-tmp>`` is the platform's shared sticky directory: ``/private/tmp`` on Darwin, where
``/tmp`` is a symlink to it, and ``/tmp`` on Linux. Both are root-owned and sticky, which is the
property the strategy needs from its parent. The socket path capacity differs as well, so it is
selected per platform rather than assumed.

The v4 design deliberately does **not** authenticate the client: being able to reach the socket
is the access check. That makes the filesystem contract the whole security boundary, so every
step here fails closed and cleanup only ever unlinks an exact path from its own registry.
"""

from __future__ import annotations

import os
import secrets
import socket
import stat
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Protocol, Sequence

def _platform_private_tmp() -> Path:
    """The platform's root-owned sticky shared directory.

    Darwin keeps shared temporary paths under ``/private/tmp`` and makes ``/tmp`` a symlink to
    it. Linux has a real ``/tmp``. The strategy needs a parent that another user can neither
    write to nor rename our entry inside, and both directories provide that.
    """

    return Path("/private/tmp") if sys.platform == "darwin" else Path("/tmp")


def default_sun_path_capacity_bytes() -> int:
    """The kernel's ``sun_path`` capacity for this platform."""

    return (
        DARWIN_SUN_PATH_CAPACITY_BYTES
        if sys.platform == "darwin"
        else LINUX_SUN_PATH_CAPACITY_BYTES
    )


#: The canonical private base. Never `$TMPDIR`, never the long evidence root and never a
#: user-supplied directory. `_platform_private_tmp()` picks the platform's sticky directory.
PRIVATE_TMP = _platform_private_tmp()

#: Darwin's `sun_path` is 104 bytes including the terminating NUL (probed on this host: 103
#: bytes bind, 104 fails with "AF_UNIX path too long"). Linux retains its own 108.
DARWIN_SUN_PATH_CAPACITY_BYTES = 104
LINUX_SUN_PATH_CAPACITY_BYTES = 108

#: Suffix of one campaign directory. Kept short because the whole path must fit `sun_path`.
CAMPAIGN_PREFIX = "b-"
CAMPAIGN_ID_BYTES = 6

#: The exact endpoint names a campaign may create, by role.
ENDPOINT_NAMES: Mapping[str, str] = {
    "coordinator": "coordinator.sock",
    "broker": "broker.sock",
    "worker-0": "w1.sock",
    "worker-1": "w2.sock",
}

#: Directories must be private and owned; sockets must not be reachable by group or other.
DIRECTORY_MODE = 0o700
SOCKET_MODE = 0o600

CLEANED = "CLEANED"
ALREADY_GONE = "ALREADY_GONE"
NOT_OWNED = "NOT_OWNED"


class UnixAddressError(RuntimeError):
    """The private address contract was violated; the caller must fail closed."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class CampaignIpcRoot:
    """One campaign's private directory. Fresh random id; never reused across a restart."""

    base_path: Path
    campaign_path: Path
    uid: int
    campaign_id: str

    def __post_init__(self) -> None:
        base = Path(self.base_path)
        campaign = Path(self.campaign_path)
        if campaign.parent != base:
            raise UnixAddressError("CAMPAIGN_ROOT_MISMATCH", f"{campaign} not under {base}")
        if not campaign.name.startswith(CAMPAIGN_PREFIX):
            raise UnixAddressError("CAMPAIGN_ID_INVALID", campaign.name)
        if type(self.uid) is not int or self.uid < 0:
            raise UnixAddressError("CAMPAIGN_UID_INVALID", repr(self.uid))


@dataclass(frozen=True)
class RegisteredEndpoint:
    """One created socket. The registry is for cleanup and audit, never for client auth."""

    path: Path
    role: str
    owner_pid: int
    owner_birth_identity: int
    device: int
    inode: int


@dataclass(frozen=True)
class EndpointCleanup:
    """Per-endpoint cleanup outcome plus the live readback that decided it."""

    path: Path
    outcome: str
    existed_before: bool
    live_after: bool


@dataclass(frozen=True)
class CleanupReceipt:
    """The whole cleanup result: one entry per registered endpoint, then the directory."""

    endpoints: tuple[EndpointCleanup, ...]
    directory_removed: bool
    directory_live_after: bool
    directory_outcome: str
    detail: str = ""

    @property
    def complete(self) -> bool:
        return (
            all(not item.live_after for item in self.endpoints)
            and not self.directory_live_after
        )


class UnixAddressStrategy(Protocol):
    """The platform address contract shared by schema v3 (Linux) and v4 (both platforms)."""

    def create_campaign_root(self) -> CampaignIpcRoot: ...

    def endpoint_path(self, root: CampaignIpcRoot, role: str) -> Path: ...

    def validate_encoded_length(self, path: object) -> None: ...

    def cleanup_registered_endpoint(self, endpoint: RegisteredEndpoint) -> EndpointCleanup: ...


# --------------------------------------------------------------------------------------
# filesystem assertions
# --------------------------------------------------------------------------------------


def _lstat_or_none(path: Path):
    try:
        return os.lstat(path)
    except FileNotFoundError:
        return None
    except OSError as error:
        raise UnixAddressError("LSTAT_FAILED", f"{path}: {error}") from error


def require_owned_private_directory(path: Path, *, uid: int | None = None) -> None:
    """The directory must exist, be a real directory, be owned by us and be mode 0700."""

    expected_uid = os.getuid() if uid is None else uid
    metadata = _lstat_or_none(Path(path))
    if metadata is None:
        raise UnixAddressError("DIRECTORY_MISSING", str(path))
    if stat.S_ISLNK(metadata.st_mode):
        raise UnixAddressError("DIRECTORY_IS_SYMLINK", str(path))
    if not stat.S_ISDIR(metadata.st_mode):
        raise UnixAddressError("DIRECTORY_NOT_DIRECTORY", str(path))
    if metadata.st_uid != expected_uid:
        raise UnixAddressError("DIRECTORY_NOT_OWNED", f"{path} uid={metadata.st_uid}")
    granted = stat.S_IMODE(metadata.st_mode)
    if granted != DIRECTORY_MODE:
        raise UnixAddressError("DIRECTORY_MODE", f"{path} mode={granted:04o}")


def require_safe_ancestors(path: Path, *, uid: int | None = None) -> None:
    """No ancestor above ``path`` may let another user replace ``path``.

    This is the property the Linux dirfd transport gets from its inherited descriptor and the
    Darwin transport has to get from the filesystem: nobody else may be able to swap the
    directory a socket is bound into. An ancestor is acceptable when it is not group- or
    other-writable, or when it is a root-owned sticky directory (``/private/tmp``, ``/tmp``
    and ``/``).

    A per-user path under a shared sticky parent is still safe, because the sticky bit stops
    another user from renaming or removing a directory they do not own.
    """

    expected_uid = os.getuid() if uid is None else uid
    current = Path(path).parent
    while True:
        metadata = _lstat_or_none(current)
        if metadata is None:
            raise UnixAddressError("ANCESTOR_MISSING", str(current))
        if stat.S_ISLNK(metadata.st_mode):
            # /tmp -> private/tmp on Darwin is exactly this case, and it is harmless, but an
            # unexpected symlink in the chain is refused rather than reasoned about.
            if current != Path("/tmp"):
                raise UnixAddressError("ANCESTOR_IS_SYMLINK", str(current))
        elif not stat.S_ISDIR(metadata.st_mode):
            raise UnixAddressError("ANCESTOR_NOT_DIRECTORY", str(current))
        else:
            # The sticky bit is what makes a shared directory safe: it stops another user
            # from renaming or removing an entry they do not own. A writable, non-sticky
            # directory anywhere above us means someone else can swap our base out from
            # under the socket path, whoever owns that directory.
            writable = bool(stat.S_IMODE(metadata.st_mode) & (stat.S_IWGRP | stat.S_IWOTH))
            sticky_root = metadata.st_uid == 0 and bool(metadata.st_mode & stat.S_ISVTX)
            if writable and not sticky_root:
                raise UnixAddressError(
                    "ANCESTOR_WRITABLE",
                    f"{current} uid={metadata.st_uid} mode={stat.S_IMODE(metadata.st_mode):04o}"
                    " is writable without a root-owned sticky bit",
                )
        if current.parent == current:
            return
        current = current.parent


def require_root_owned_sticky_directory(path: Path) -> None:
    """The sticky parent must be a root-owned sticky directory, not a symlink."""

    metadata = _lstat_or_none(Path(path))
    if metadata is None:
        raise UnixAddressError("BASE_MISSING", str(path))
    if stat.S_ISLNK(metadata.st_mode):
        raise UnixAddressError("BASE_IS_SYMLINK", str(path))
    if not stat.S_ISDIR(metadata.st_mode):
        raise UnixAddressError("BASE_NOT_DIRECTORY", str(path))
    if metadata.st_uid != 0:
        raise UnixAddressError("BASE_NOT_ROOT_OWNED", f"{path} uid={metadata.st_uid}")
    if not metadata.st_mode & stat.S_ISVTX:
        raise UnixAddressError("BASE_NOT_STICKY", str(path))


def encoded_length_ok(path: object, *, capacity_bytes: int) -> bool:
    encoded = os.fsencode(str(path))
    return bool(encoded) and b"\x00" not in encoded and len(encoded) + 1 <= capacity_bytes


def require_encoded_length(path: object, *, capacity_bytes: int) -> None:
    """The encoded path plus its terminating NUL must fit the kernel's `sun_path`."""

    encoded = os.fsencode(str(path))
    if not encoded or b"\x00" in encoded:
        raise UnixAddressError("SOCKET_PATH_INVALID", str(path))
    if len(encoded) + 1 > capacity_bytes:
        raise UnixAddressError(
            "SOCKET_PATH_TOO_LONG", f"{len(encoded)} bytes + NUL > {capacity_bytes}"
        )


def require_endpoint_stat(path: Path, *, uid: int) -> os.stat_result:
    """The endpoint must be a socket, owned by us, mode 0600, and not a symlink."""

    metadata = _lstat_or_none(Path(path))
    if metadata is None:
        raise UnixAddressError("ENDPOINT_MISSING", str(path))
    if stat.S_ISLNK(metadata.st_mode):
        raise UnixAddressError("ENDPOINT_IS_SYMLINK", str(path))
    if not stat.S_ISSOCK(metadata.st_mode):
        raise UnixAddressError("ENDPOINT_NOT_SOCKET", str(path))
    if metadata.st_uid != uid:
        raise UnixAddressError("ENDPOINT_NOT_OWNED", f"{path} uid={metadata.st_uid}")
    granted = stat.S_IMODE(metadata.st_mode)
    if granted != SOCKET_MODE:
        raise UnixAddressError("ENDPOINT_MODE", f"{path} mode={granted:04o}")
    return metadata


class DarwinPrivatePathUnixAddress:
    """The v4 Darwin strategy: a canonical private directory and exact unlinking."""

    def __init__(self, *, uid: int | None = None, base_path: Path | None = None,
                 capacity_bytes: int | None = None,
                 register_pid: bool = True) -> None:
        self._uid = os.getuid() if uid is None else int(uid)
        self._base_path = Path(base_path) if base_path is not None else (
            PRIVATE_TMP / f"so101-ipc-{self._uid}"
        )
        self._capacity = int(
            default_sun_path_capacity_bytes() if capacity_bytes is None else capacity_bytes
        )
        self._register_pid = bool(register_pid)
        self._registry: dict[Path, RegisteredEndpoint] = {}

    @property
    def uid(self) -> int:
        return self._uid

    @property
    def base_path(self) -> Path:
        return self._base_path

    @property
    def capacity_bytes(self) -> int:
        return self._capacity

    @property
    def registry(self) -> tuple[RegisteredEndpoint, ...]:
        return tuple(self._registry.values())

    def create_campaign_root(self) -> CampaignIpcRoot:
        """Create one fresh campaign directory, or fail closed. Never reuse a colliding path."""

        # Nobody else may be able to swap the directory we are about to bind into.
        require_safe_ancestors(self._base_path, uid=self._uid)
        if self._base_path.exists():
            require_owned_private_directory(self._base_path, uid=self._uid)
        else:
            try:
                os.mkdir(self._base_path, DIRECTORY_MODE)
            except FileExistsError:
                pass
            except OSError as error:
                raise UnixAddressError("BASE_CREATE_FAILED", str(error)) from error
            require_owned_private_directory(self._base_path, uid=self._uid)
        if self._base_path == PRIVATE_TMP / f"so101-ipc-{self._uid}":
            # The canonical base must sit directly in a root-owned sticky directory.
            require_root_owned_sticky_directory(self._base_path.parent)

        for _ in range(8):
            campaign_id = f"{CAMPAIGN_PREFIX}{secrets.token_hex(CAMPAIGN_ID_BYTES)}"
            campaign_path = self._base_path / campaign_id
            try:
                os.mkdir(campaign_path, DIRECTORY_MODE)
            except FileExistsError:
                # A colliding id is never reused and never deleted: try another id.
                continue
            except OSError as error:
                raise UnixAddressError("CAMPAIGN_CREATE_FAILED", str(error)) from error
            # mkdir honours umask, so set the mode explicitly and re-assert it.
            os.chmod(campaign_path, DIRECTORY_MODE)
            require_owned_private_directory(campaign_path, uid=self._uid)
            return CampaignIpcRoot(
                base_path=self._base_path, campaign_path=campaign_path, uid=self._uid,
                campaign_id=campaign_id,
            )
        raise UnixAddressError("CAMPAIGN_ID_COLLISION", str(self._base_path))

    def endpoint_path(self, root: CampaignIpcRoot, role: str) -> Path:
        """The exact socket path for a role, with the encoded-length check applied."""

        if not isinstance(root, CampaignIpcRoot):
            raise UnixAddressError("CAMPAIGN_ROOT_TYPE", type(root).__name__)
        name = ENDPOINT_NAMES.get(role)
        if name is None:
            raise UnixAddressError("ENDPOINT_ROLE_UNKNOWN", role)
        path = root.campaign_path / name
        self.validate_encoded_length(path)
        return path

    def validate_encoded_length(self, path: object) -> None:
        require_encoded_length(path, capacity_bytes=self._capacity)

    def register_endpoint(self, path: Path, *, role: str, owner_pid: int,
                          owner_birth_identity: int) -> RegisteredEndpoint:
        """Record a created socket after asserting its real ownership and mode."""

        metadata = require_endpoint_stat(path, uid=self._uid)
        endpoint = RegisteredEndpoint(
            path=Path(path), role=role, owner_pid=int(owner_pid),
            owner_birth_identity=int(owner_birth_identity),
            device=int(metadata.st_dev), inode=int(metadata.st_ino),
        )
        self._registry[Path(path)] = endpoint
        return endpoint

    def bind_endpoint(self, root: CampaignIpcRoot, role: str, *, owner_pid: int,
                      owner_birth_identity: int,
                      listener: socket.socket | None = None) -> RegisteredEndpoint:
        """Bind one role's socket with mode 0600 before anything can connect to it."""

        path = self.endpoint_path(root, role)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        previous_umask = os.umask(0o177)
        try:
            sock.bind(str(path))
        except OSError as error:
            sock.close()
            raise UnixAddressError("ENDPOINT_BIND_FAILED", f"{path}: {error}") from error
        finally:
            os.umask(previous_umask)
        os.chmod(path, SOCKET_MODE)
        if listener is not None:
            listener(path)
        return self.register_endpoint(path, role=role, owner_pid=owner_pid,
                                      owner_birth_identity=owner_birth_identity)

    def cleanup_registered_endpoint(self, endpoint: RegisteredEndpoint) -> EndpointCleanup:
        """Unlink exactly one registered socket after re-checking its identity."""

        if not isinstance(endpoint, RegisteredEndpoint):
            raise UnixAddressError("ENDPOINT_TYPE", type(endpoint).__name__)
        path = Path(endpoint.path)
        if self._registry.get(path) != endpoint:
            return EndpointCleanup(path=path, outcome=NOT_OWNED, existed_before=False,
                                   live_after=path.exists() or os.path.lexists(path))
        metadata = _lstat_or_none(path)
        if metadata is None:
            self._registry.pop(path, None)
            return EndpointCleanup(path=path, outcome=ALREADY_GONE, existed_before=False,
                                   live_after=False)
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISSOCK(metadata.st_mode):
            # Something replaced our socket. Report it and do not delete an unknown object.
            return EndpointCleanup(path=path, outcome=NOT_OWNED, existed_before=True,
                                   live_after=True)
        if (int(metadata.st_dev), int(metadata.st_ino)) != (endpoint.device, endpoint.inode):
            return EndpointCleanup(path=path, outcome=NOT_OWNED, existed_before=True,
                                   live_after=True)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        except OSError as error:
            raise UnixAddressError("ENDPOINT_UNLINK_FAILED", f"{path}: {error}") from error
        self._registry.pop(path, None)
        return EndpointCleanup(path=path, outcome=CLEANED, existed_before=True,
                               live_after=os.path.lexists(path))

    def cleanup_campaign(self, root: CampaignIpcRoot) -> CleanupReceipt:
        """Clean every registered endpoint of one campaign, then remove its exact directory."""

        if not isinstance(root, CampaignIpcRoot):
            raise UnixAddressError("CAMPAIGN_ROOT_TYPE", type(root).__name__)
        entries: list[EndpointCleanup] = []
        for endpoint in [item for item in self._registry.values()
                         if item.path.parent == root.campaign_path]:
            entries.append(self.cleanup_registered_endpoint(endpoint))
        directory_removed = False
        if root.campaign_path.exists():
            leftovers = sorted(item.name for item in root.campaign_path.iterdir())
            if not leftovers:
                try:
                    os.rmdir(root.campaign_path)
                    directory_removed = True
                except OSError as error:
                    raise UnixAddressError(
                        "CAMPAIGN_RMDIR_FAILED", f"{root.campaign_path}: {error}") from error
                directory_outcome = CLEANED
            else:
                # Unknown objects are never deleted; the caller decides what to do.
                directory_outcome = NOT_OWNED
        else:
            directory_outcome = ALREADY_GONE
        return CleanupReceipt(
            endpoints=tuple(entries), directory_removed=directory_removed,
            directory_live_after=root.campaign_path.exists(),
            directory_outcome=directory_outcome,
            detail="exact registered endpoints only",
        )


class ProcFdUnixAddress:
    """The frozen schema-v3 Linux strategy. Unchanged; it simply satisfies the same protocol."""

    def __init__(self, *, capacity_bytes: int = LINUX_SUN_PATH_CAPACITY_BYTES) -> None:
        self._capacity = int(capacity_bytes)

    def create_campaign_root(self) -> CampaignIpcRoot:  # pragma: no cover - Linux only
        from ..runtime.parallel_ipc import require_proc_fd_transport

        require_proc_fd_transport()
        raise UnixAddressError(
            "PROC_FD_CAMPAIGN_ROOT",
            "the v3 dirfd transport binds through an inherited descriptor, not a durable root",
        )

    def endpoint_path(self, root: CampaignIpcRoot, role: str) -> Path:  # pragma: no cover
        name = ENDPOINT_NAMES.get(role)
        if name is None:
            raise UnixAddressError("ENDPOINT_ROLE_UNKNOWN", role)
        return Path(root.campaign_path) / name

    def validate_encoded_length(self, path: object) -> None:
        require_encoded_length(path, capacity_bytes=self._capacity)

    def cleanup_registered_endpoint(  # pragma: no cover - Linux only
            self, endpoint: RegisteredEndpoint) -> EndpointCleanup:
        raise UnixAddressError(
            "PROC_FD_CLEANUP_UNSUPPORTED",
            "v3 endpoints are owned by their process and die with it",
        )
