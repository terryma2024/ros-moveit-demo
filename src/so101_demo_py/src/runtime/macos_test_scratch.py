"""Short, private macOS test scratch for the service-campaign gates.

Darwin caps an AF_UNIX endpoint at 104 bytes including the terminating NUL. A pytest run whose
``TMPDIR`` sits under a registered evidence root (this task's root name alone is 74 characters)
overflows that limit as soon as a fixture joins its own directories onto it, and the failure shows
up far from its cause as ``UNIX_SOCKET_PATH_TOO_LONG`` / ``IPC_SOCKET_PATH_TOO_LONG`` /
``CONTROL_SOCKET_PATH_TOO_LONG`` and then ``PATH_OWNER``.

The scratch here is therefore deliberately independent of the evidence root: it is created once per
run under ``/opt/data/tmp`` (short, local, never a symlink alias), handed to the test process through
``TMPDIR``/``TMP``/``TEMP``, and listed as a deletion candidate instead of being cleaned up. Every
log, JUnit file and receipt still belongs to the single registered evidence root; only this transient
scratch lives outside it.
"""

from __future__ import annotations

import json
import os
import socket
import stat
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

#: Darwin's ``sun_path`` is 104 bytes including the trailing NUL.
DARWIN_SUN_PATH_LIMIT = 104
DEFAULT_SCRATCH_PARENT = Path("/opt/data/tmp")

#: The longest endpoint shapes the gates are known to create under ``TMPDIR``. The preflight still
#: proves the real limit with a bind; this table only says what has to fit.
KNOWN_ENDPOINT_SUFFIXES = (
    "/so101-unified-ipc/controller.sock",
    "/so101-unified-control/console.sock",
    "/so101-unified-control/worker-01.sock",
    "/pytest-of-u/pytest-0/ipc.sock",
)


class MacOSTestScratchError(RuntimeError):
    """Fail-closed scratch error carrying a stable machine-readable code."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


@dataclass(frozen=True, slots=True)
class MacOSTestScratch:
    """One private, short, owner-checked scratch directory."""

    scratch_path: Path
    evidence_run_root: Path
    owner_uid: int
    mode: int
    max_endpoint_bytes: int
    receipt_path: Path

    @property
    def sun_path_limit(self) -> int:
        return DARWIN_SUN_PATH_LIMIT

    @property
    def endpoint_headroom_bytes(self) -> int:
        return self.sun_path_limit - self.max_endpoint_bytes

    def environment(self) -> dict[str, str]:
        """The three variables a test process needs, all pointing at the same short directory."""

        value = str(self.scratch_path)
        return {"TMPDIR": value, "TMP": value, "TEMP": value}

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "scratch_path": str(self.scratch_path),
            "evidence_run_root": str(self.evidence_run_root),
            "owner_uid": self.owner_uid,
            "mode": f"{self.mode:04o}",
            "max_endpoint_bytes": self.max_endpoint_bytes,
            "sun_path_limit": self.sun_path_limit,
            "endpoint_headroom_bytes": self.endpoint_headroom_bytes,
            "deletion_candidate": True,
            "receipt_path": str(self.receipt_path),
        }


def _atomic_write_json(path: Path, document: dict[str, object]) -> str:
    import hashlib

    encoded = json.dumps(document, indent=2, sort_keys=True).encode("utf-8")
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        os.write(descriptor, encoded)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    return hashlib.sha256(encoded).hexdigest()


def longest_endpoint_bytes(scratch_path: Path, suffixes: Sequence[str]) -> int:
    base = str(scratch_path)
    return max(len(base) + len(suffix) for suffix in suffixes)


def probe_endpoint_bind(scratch_path: Path, suffix: str) -> int:
    """Bind one real AF_UNIX socket at the longest known endpoint shape.

    Returns the observed endpoint length. A path that is too long fails with ``OSError`` from the
    kernel; the caller turns that into a fail-closed report instead of guessing from a constant.
    """

    endpoint = Path(f"{scratch_path}{suffix}")
    endpoint.parent.mkdir(parents=True, exist_ok=True)
    if len(str(endpoint).encode()) + 1 > DARWIN_SUN_PATH_LIMIT:
        raise MacOSTestScratchError("SCRATCH_ENDPOINT_TOO_LONG", str(endpoint))
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        server.bind(str(endpoint))
        server.listen(1)
    except OSError as error:
        raise MacOSTestScratchError(
            "SCRATCH_ENDPOINT_BIND_FAILED", f"{endpoint}: {error}"
        ) from error
    finally:
        server.close()
        try:
            endpoint.unlink()
        except OSError:
            pass
    return len(str(endpoint))


def prepare_macos_test_scratch(
    evidence_run_root: Path,
    scratch_parent: Path = DEFAULT_SCRATCH_PARENT,
    *,
    known_endpoint_suffixes: Sequence[str] = KNOWN_ENDPOINT_SUFFIXES,
    run_id: str | None = None,
) -> MacOSTestScratch:
    """Create the run's short scratch and write its identity receipt into the evidence root."""

    run_root = Path(evidence_run_root)
    if run_root.is_symlink():
        raise MacOSTestScratchError("SCRATCH_RUN_ROOT_INVALID", str(run_root))
    if not run_root.is_dir():
        run_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if not run_root.is_dir():
        raise MacOSTestScratchError("SCRATCH_RUN_ROOT_INVALID", str(run_root))
    parent = Path(scratch_parent)
    if parent.is_symlink():
        raise MacOSTestScratchError("SCRATCH_PARENT_SYMLINK", str(parent))
    if not parent.is_dir():
        raise MacOSTestScratchError("SCRATCH_PARENT_MISSING", str(parent))
    parent_status = parent.stat()
    if parent_status.st_uid != os.getuid():
        raise MacOSTestScratchError("SCRATCH_PARENT_OWNER", str(parent))
    parent_mode = stat.S_IMODE(parent_status.st_mode)
    if parent_mode & 0o077:
        raise MacOSTestScratchError("SCRATCH_PARENT_MODE", f"{parent_mode:04o}")

    identifier = run_id or f"{uuid.uuid4().hex[:8]}"
    scratch_path = parent / f"so101-service-gate-{identifier}"
    if scratch_path.exists() or scratch_path.is_symlink():
        raise MacOSTestScratchError("SCRATCH_ALREADY_EXISTS", str(scratch_path))
    # The endpoint budget is a property of the intended path, so an over-long shape is refused
    # before anything is created and nothing is left behind for the operator to clean up.
    max_endpoint_bytes = longest_endpoint_bytes(scratch_path, known_endpoint_suffixes)
    if max_endpoint_bytes >= DARWIN_SUN_PATH_LIMIT:
        raise MacOSTestScratchError(
            "SCRATCH_ENDPOINT_TOO_LONG", f"{max_endpoint_bytes} >= {DARWIN_SUN_PATH_LIMIT}"
        )
    try:
        # mkdir is the O_EXCL equivalent for a directory: an existing path never gets reused.
        os.mkdir(scratch_path, 0o700)
    except FileExistsError as error:
        raise MacOSTestScratchError("SCRATCH_ALREADY_EXISTS", str(scratch_path)) from error
    except OSError as error:
        raise MacOSTestScratchError("SCRATCH_CREATE_FAILED", str(error)) from error

    if scratch_path.is_symlink():
        raise MacOSTestScratchError("SCRATCH_IS_SYMLINK", str(scratch_path))
    status = scratch_path.stat()
    if status.st_uid != os.getuid():
        raise MacOSTestScratchError("SCRATCH_OWNER_MISMATCH", str(status.st_uid))
    if stat.S_IMODE(status.st_mode) != 0o700:
        raise MacOSTestScratchError("SCRATCH_MODE_MISMATCH", f"{stat.S_IMODE(status.st_mode):04o}")
    if scratch_path.resolve() != scratch_path:
        raise MacOSTestScratchError("SCRATCH_PATH_ESCAPE", str(scratch_path.resolve()))

    receipt_path = run_root / "scratch-identity.json"
    scratch = MacOSTestScratch(
        scratch_path=scratch_path,
        evidence_run_root=run_root,
        owner_uid=status.st_uid,
        mode=stat.S_IMODE(status.st_mode),
        max_endpoint_bytes=max_endpoint_bytes,
        receipt_path=receipt_path,
    )
    document = dict(scratch.as_document())
    document["tempfile_gettempdir_expected"] = str(scratch_path)
    document["created_by_pid"] = os.getpid()
    _atomic_write_json(receipt_path, document)
    return scratch


def read_back_tempdir(python: Path, environment: dict[str, str]) -> Path:
    """Ask the exact test interpreter what it thinks its temporary directory is."""

    import subprocess

    merged = dict(os.environ)
    merged.update(environment)
    completed = subprocess.run(
        [str(python), "-c", "import tempfile; print(tempfile.gettempdir())"],
        check=False,
        capture_output=True,
        text=True,
        env=merged,
    )
    if completed.returncode != 0:
        raise MacOSTestScratchError(
            "SCRATCH_TEMPDIR_PROBE_FAILED", completed.stderr.strip()
        )
    return Path(completed.stdout.strip())


def default_scratch_parent() -> Path:
    """The parent the gates use, honouring an explicit override for tests and fixtures."""

    override = os.environ.get("SO101_MACOS_TEST_SCRATCH_PARENT")
    return Path(override) if override else DEFAULT_SCRATCH_PARENT
