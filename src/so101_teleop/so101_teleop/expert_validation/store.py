"""SQLite-backed durable supervisor state with one process-level writer."""

from __future__ import annotations

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import sqlite3
import stat

from so101_teleop.expert_validation.supervisor_store.commands import StoreCommands
from so101_teleop.expert_validation.supervisor_store.first_pass import StoreFirstPass
from so101_teleop.expert_validation.supervisor_store.leases import StoreLeases
from so101_teleop.expert_validation.supervisor_store.owner import StoreOwner
from so101_teleop.expert_validation.supervisor_store.projection import StoreProjection
from so101_teleop.expert_validation.supervisor_store.retry import StoreRetry
from so101_teleop.expert_validation.supervisor_store.schema import _SCHEMA, StoreConflict


class SupervisorStore(StoreCommands, StoreRetry, StoreFirstPass, StoreOwner, StoreProjection, StoreLeases):
    def __init__(self, root: Path, lock_fd: int, connection: sqlite3.Connection) -> None:
        self.root = root
        self._lock_fd = lock_fd
        self._connection = connection

    @classmethod
    def open(cls, root: Path) -> "SupervisorStore":
        root = Path(root)
        if not root.is_absolute() or root != root.resolve(strict=False) or root.is_symlink():
            raise StoreConflict("STORE_ROOT_INVALID")
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        root_stat = root.stat()
        if root_stat.st_uid != os.getuid() or stat.S_IMODE(root_stat.st_mode) != 0o700:
            raise StoreConflict("STORE_ROOT_NOT_PRIVATE")
        lock_path = root / "supervisor.lock"
        lock_fd = os.open(
            lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600
        )
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(lock_fd)
            raise StoreConflict("VALIDATION_SUPERVISOR_ACTIVE") from error
        try:
            database = root / "supervisor.sqlite3"
            database_fd = os.open(
                database, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC | os.O_NOFOLLOW, 0o600
            )
            try:
                metadata = os.fstat(database_fd)
                if (
                    not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                    or metadata.st_nlink != 1
                ):
                    raise StoreConflict("STORE_DATABASE_INVALID")
                os.fchmod(database_fd, 0o600)
            finally:
                os.close(database_fd)
            connection = sqlite3.connect(database, isolation_level=None)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.executescript(_SCHEMA)
        except Exception:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)
            raise
        return cls(root, lock_fd, connection)

    def close(self) -> None:
        if self._connection is None:
            return
        self._connection.close()
        self._connection = None
        fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        os.close(self._lock_fd)

    @contextmanager
    def _transaction(self):
        self._connection.execute("BEGIN IMMEDIATE")
        try:
            yield
        except Exception:
            self._connection.execute("ROLLBACK")
            raise
        else:
            self._connection.execute("COMMIT")

    # -- one-time retry admission: one command, one binding, one owner intent, one transaction ---

    #: Every coordinate a retry request and its execution context must agree on. The code names the
    #: one that drifted, so a refusal is diagnosable without reading the rows. The manifest is not
    #: here: it belongs to the campaign row, and is checked against the context there.
    _RETRY_COORDINATES = (
        ("campaign_id", "RETRY_CAMPAIGN_MISMATCH"),
        ("batch_id", "RETRY_BATCH_MISMATCH"),
        ("execution_profile", "RETRY_PROFILE_MISMATCH"),
        ("schema_version", "RETRY_SCHEMA_MISMATCH"),
        ("batch_kind", "RETRY_BATCH_KIND_MISMATCH"),
        ("worker_count", "RETRY_WORKER_COUNT_MISMATCH"),
        ("config_sha256", "RETRY_CONFIG_MISMATCH"),
        ("runtime_closure_sha256", "RETRY_RUNTIME_CLOSURE_MISMATCH"),
        ("evidence_root", "RETRY_EVIDENCE_ROOT_MISMATCH"),
        ("owner_generation", "RETRY_OWNER_GENERATION_MISMATCH"),
    )

    #: The durable owner state a ``RUNNING`` execution is retired to once its process is proven
    #: gone. It is a state of the owner row, not of the batch: the batch keeps whatever terminal or
    #: cleaned state its own journal earned.
    OWNER_STATE_EXITED = "EXITED"

    # -- one-time candidate context issuance ---------------------------------------------------

    #: The one issuance operation this store records in the shared one-time command table.
    CANDIDATE_ISSUANCE_OPERATION = "ISSUE_CANDIDATE_CONTEXT"

    # -- one-time candidate first-pass admission -----------------------------------------------

    #: Every coordinate a first-pass request and its candidate context must agree on.
    _FIRST_PASS_COORDINATES = (
        ("campaign_id", "FIRST_PASS_CAMPAIGN_MISMATCH"),
        ("batch_id", "FIRST_PASS_BATCH_MISMATCH"),
        ("manifest_id", "FIRST_PASS_MANIFEST_MISMATCH"),
        ("execution_profile", "FIRST_PASS_PROFILE_MISMATCH"),
        ("worker_count", "FIRST_PASS_WORKER_COUNT_MISMATCH"),
    )

    # -- persistent owner tree: intent before spawn, confirmation after readback ---------------



