"""Durable intent and reservation store for the unified web service.

One store owns one private directory and one exclusive ``flock``. Every state change is
committed in a single ``BEGIN IMMEDIATE`` SQLite transaction with ``synchronous=FULL`` so a
crash can never leave a reservation that was only half written. The store never opens or
rewrites the existing expert-validation journal; it adds its own versioned tables.
"""

from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterator

from .contracts import (
    BLOCKED,
    CHILD_ACKED,
    CHILD_PREPARED,
    CHILD_REJECTED,
    CHILD_TERMINAL,
    IDLE,
    PHASE_ACTIVE,
    PHASE_BLOCKED,
    PHASE_CANCELLED,
    PHASE_COMPLETE,
    PHASE_PAUSED,
    RESERVING_STATES,
    TASK_ACTIVE,
    TELEOP_ACTIVE,
    UNKNOWN_OWNER,
    VALIDATION_ACTIVE,
    ActionKey,
    ActionTerminal,
    CancelIntent,
    DispatchAck,
    DispatchToken,
    Domain,
    MutationError,
    OperationSpec,
    OwnerKey,
    ParentProjection,
    PendingChildKey,
    Reservation,
    RevokeTarget,
)

SCHEMA_VERSION = 1
LOCK_FILE_NAME = "service.lock"

LEASE_CLAIMING = "CLAIMING"
LEASE_RENEWING = "RENEWING"
LEASE_BOUND = "BOUND"
LEASE_FAILED = "FAILED"
LEASE_UNKNOWN = "UNKNOWN"
#: States that keep the durable admission fence closed until an explicit recovery.
OPEN_LEASE_STATES = (LEASE_CLAIMING, LEASE_RENEWING, LEASE_FAILED, LEASE_UNKNOWN)
DATABASE_FILE_NAME = "intents.sqlite3"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS global_state (
  singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
  state TEXT NOT NULL,
  owner_operation_id TEXT,
  owner_domain TEXT,
  blocked_reason TEXT,
  updated_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS parents (
  operation_id TEXT PRIMARY KEY,
  command_id TEXT NOT NULL UNIQUE,
  fingerprint TEXT NOT NULL,
  domain TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  runtime_id TEXT NOT NULL,
  execution_generation INTEGER NOT NULL,
  deadline_ns INTEGER NOT NULL,
  phase TEXT NOT NULL,
  blocked_reason TEXT,
  cancel_requested INTEGER NOT NULL DEFAULT 0,
  revocation_revision INTEGER NOT NULL DEFAULT 0,
  created_ns INTEGER NOT NULL,
  updated_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS execution_generations (
  domain TEXT PRIMARY KEY,
  generation INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS lease_operations (
  claim_id TEXT PRIMARY KEY,
  domain TEXT NOT NULL,
  state TEXT NOT NULL,
  lease_json TEXT,
  reason TEXT,
  created_ns INTEGER NOT NULL,
  updated_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS children (
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,
  operation_id TEXT NOT NULL,
  child_id TEXT NOT NULL,
  runtime_id TEXT NOT NULL,
  execution_generation INTEGER NOT NULL,
  revocation_revision INTEGER NOT NULL,
  deadline_ns INTEGER NOT NULL,
  phase TEXT NOT NULL,
  accepted INTEGER,
  goal_uuid TEXT,
  owner_json TEXT,
  succeeded INTEGER,
  stopped_confirmed INTEGER,
  cleanup_confirmed INTEGER,
  UNIQUE (operation_id, child_id)
);
"""


@dataclass(frozen=True)
class _SettleOutcome:
    projection: ParentProjection
    code: str | None


class IntentStore:
    """Owns the durable reservation state of exactly one service instance."""

    def __init__(self, root: Path, lock_fd: int, connection: sqlite3.Connection) -> None:
        self.root = root
        self._lock_fd = lock_fd
        self._connection = connection
        self._thread_lock = threading.RLock()
        self._closed = False
        self._clock_ns = time.monotonic_ns

    # -- lifecycle ---------------------------------------------------------------

    @classmethod
    def open(cls, root: Path) -> "IntentStore":
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        lock_path = root / LOCK_FILE_NAME
        try:
            lock_fd = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        except OSError as error:
            raise MutationError(f"SERVICE_LOCK_UNSAFE: {lock_path}: {error}") from error
        os.chmod(lock_path, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            os.close(lock_fd)
            raise MutationError(
                f"SERVICE_INSTANCE_LOCKED: {root} is already owned by another service instance"
            ) from error
        database_path = root / DATABASE_FILE_NAME
        connection = sqlite3.connect(database_path, check_same_thread=False, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript(_SCHEMA)
        connection.execute(
            "INSERT OR IGNORE INTO schema_meta (key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        connection.execute(
            "INSERT OR IGNORE INTO global_state (singleton, state, updated_ns) VALUES (1, ?, 0)",
            (IDLE,),
        )
        with contextlib.suppress(OSError):
            os.chmod(database_path, 0o600)
        store = cls(root, lock_fd, connection)
        store._reconcile_after_open()
        return store

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(sqlite3.Error):
            self._connection.close()
        with contextlib.suppress(OSError):
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(self._lock_fd)

    # -- transactions ------------------------------------------------------------

    @contextlib.contextmanager
    def immediate_transaction(self) -> Iterator[None]:
        """Run a write transaction that reads and writes under one exclusive lock."""
        with self._thread_lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    self._connection.execute("ROLLBACK")
                raise
            self._connection.execute("COMMIT")

    def _query_one(self, sql: str, parameters: tuple = ()) -> sqlite3.Row | None:
        return self._connection.execute(sql, parameters).fetchone()

    def _query_all(self, sql: str, parameters: tuple = ()) -> list[sqlite3.Row]:
        return list(self._connection.execute(sql, parameters).fetchall())

    def _reconcile_after_open(self) -> None:
        """An unconverged intent from a previous service epoch blocks, never resumes."""
        with self.immediate_transaction():
            unconverged = self._query_all(
                "SELECT operation_id, phase FROM parents WHERE phase NOT IN (?, ?)",
                (PHASE_COMPLETE, PHASE_CANCELLED),
            )
            if unconverged:
                self._mark_blocked_locked("UNCLEANED_INTENT_AFTER_RESTART")
                return
            if self.open_lease_fences():
                self._mark_blocked_locked("UNRESOLVED_LEASE_FENCE_AFTER_RESTART")
                return
            state = self._global_state_locked()[0]
            if state in RESERVING_STATES:
                self._mark_blocked_locked("UNCLEANED_RESERVATION_AFTER_RESTART")

    # -- global state ------------------------------------------------------------

    def _global_state_locked(self) -> tuple[str, str | None]:
        row = self._query_one("SELECT state, blocked_reason FROM global_state WHERE singleton = 1")
        assert row is not None
        return row["state"], row["blocked_reason"]

    def _mark_blocked_locked(self, reason: str) -> None:
        self._connection.execute(
            "UPDATE global_state SET state = ?, blocked_reason = ?, updated_ns = ? WHERE singleton = 1",
            (BLOCKED, reason, self._now_ns()),
        )
        self._connection.execute(
            "UPDATE parents SET phase = ?, blocked_reason = ?, updated_ns = ? "
            "WHERE phase NOT IN (?, ?)",
            (PHASE_BLOCKED, reason, self._now_ns(), PHASE_COMPLETE, PHASE_CANCELLED),
        )

    def _now_ns(self) -> int:
        return self._clock_ns()

    def set_clock(self, clock_ns) -> None:
        """Adopt the owning arbiter's clock so stored timestamps share one time base."""
        self._clock_ns = clock_ns

    def global_state(self) -> tuple[str, str | None]:
        with self._thread_lock:
            return self._global_state_locked()

    def block(self, reason: str) -> None:
        with self.immediate_transaction():
            self._mark_blocked_locked(reason)

    # -- idempotency and admission ----------------------------------------------

    def fingerprint(self, spec: OperationSpec) -> str:
        document = {
            "command_id": spec.command_id,
            "domain": str(spec.domain),
            "kind": spec.kind,
            "payload": spec.payload,
            "runtime_id": spec.runtime_id,
            "execution_generation": spec.execution_generation,
        }
        try:
            canonical = json.dumps(
                document, sort_keys=True, separators=(",", ":"), allow_nan=False
            )
        except (TypeError, ValueError) as error:
            raise MutationError(f"PAYLOAD_NOT_CANONICAL: {error}") from error
        return hashlib.sha256(canonical.encode()).hexdigest()

    def repeat(self, command_id: str, fingerprint: str) -> Reservation | None:
        row = self._query_one("SELECT * FROM parents WHERE command_id = ?", (command_id,))
        if row is None:
            return None
        if row["fingerprint"] != fingerprint:
            raise MutationError(
                f"COMMAND_ID_REUSED: {command_id} already recorded with a different payload"
            )
        return self._reservation_from_row(row)

    def require_idle(self) -> None:
        state, reason = self._global_state_locked()
        if state == BLOCKED:
            raise MutationError(f"BLOCKED: {reason or 'unspecified'}")
        if state != IDLE:
            raise MutationError(f"GLOBAL_MUTATION_BUSY: {state}")
        fences = self.open_lease_fences()
        if fences:
            raise MutationError(f"LEASE_FENCE_OPEN: {', '.join(fences)}")

    def insert_parent(self, spec: OperationSpec) -> Reservation:
        operation_id = uuid.uuid4().hex
        now = self._now_ns()
        self._connection.execute(
            "INSERT INTO parents (operation_id, command_id, fingerprint, domain, kind, payload_json,"
            " runtime_id, execution_generation, deadline_ns, phase, cancel_requested,"
            " revocation_revision, created_ns, updated_ns)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?)",
            (
                operation_id,
                spec.command_id,
                self.fingerprint(spec),
                str(spec.domain),
                spec.kind,
                json.dumps(spec.payload, sort_keys=True, allow_nan=False),
                spec.runtime_id,
                spec.execution_generation,
                spec.deadline_ns,
                PHASE_ACTIVE,
                now,
                now,
            ),
        )
        self._connection.execute(
            "UPDATE global_state SET state = ?, owner_operation_id = ?, owner_domain = ?,"
            " blocked_reason = NULL, updated_ns = ? WHERE singleton = 1",
            (self._reserving_state(spec), operation_id, str(spec.domain), now),
        )
        row = self._query_one("SELECT * FROM parents WHERE operation_id = ?", (operation_id,))
        assert row is not None
        return self._reservation_from_row(row)

    @staticmethod
    def _reserving_state(spec: OperationSpec) -> str:
        if spec.kind.startswith("task"):
            return TASK_ACTIVE
        return TELEOP_ACTIVE if spec.domain is Domain.TELEOP else VALIDATION_ACTIVE

    # -- children ----------------------------------------------------------------

    def prepare_child(self, operation_id: str, child_id: str, *, now_ns: int) -> DispatchToken:
        parent = self._require_parent(operation_id)
        if parent["cancel_requested"]:
            raise MutationError(f"INTENT_REVOKED: {operation_id} already cancelled")
        if parent["phase"] == PHASE_BLOCKED:
            raise MutationError(f"BLOCKED: {parent['blocked_reason'] or operation_id}")
        if parent["phase"] == PHASE_PAUSED:
            raise MutationError(f"PAUSED: {operation_id} is paused")
        if parent["phase"] != PHASE_ACTIVE:
            raise MutationError(f"PARENT_NOT_ACTIVE: {operation_id} is {parent['phase']}")
        if now_ns > parent["deadline_ns"]:
            raise MutationError(
                f"DEADLINE_EXPIRED: {operation_id} deadline {parent['deadline_ns']} < {now_ns}"
            )
        existing = self._query_one(
            "SELECT * FROM children WHERE operation_id = ? AND child_id = ?",
            (operation_id, child_id),
        )
        if existing is not None:
            if existing["phase"] == CHILD_TERMINAL:
                raise MutationError(f"CHILD_ALREADY_TERMINAL: {operation_id}/{child_id}")
            return self._token_from_row(existing)
        self._connection.execute(
            "INSERT INTO children (operation_id, child_id, runtime_id, execution_generation,"
            " revocation_revision, deadline_ns, phase) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                operation_id,
                child_id,
                parent["runtime_id"],
                parent["execution_generation"],
                parent["revocation_revision"],
                parent["deadline_ns"],
                CHILD_PREPARED,
            ),
        )
        row = self._query_one(
            "SELECT * FROM children WHERE operation_id = ? AND child_id = ?",
            (operation_id, child_id),
        )
        assert row is not None
        return self._token_from_row(row)

    def record_ack(self, token: DispatchToken, ack: DispatchAck) -> None:
        row = self._query_one(
            "SELECT * FROM children WHERE operation_id = ? AND child_id = ?",
            (token.operation_id, token.child_id),
        )
        if row is None:
            raise MutationError(f"UNKNOWN_CHILD: {token.operation_id}/{token.child_id}")
        if (
            row["runtime_id"] != token.runtime_id
            or row["execution_generation"] != token.execution_generation
        ):
            raise MutationError(f"STALE_DISPATCH_TOKEN: {token.operation_id}/{token.child_id}")
        accepted = bool(ack.accepted)
        phase = row["phase"]
        if phase != CHILD_TERMINAL:
            phase = CHILD_ACKED if accepted else CHILD_REJECTED
        self._connection.execute(
            "UPDATE children SET phase = ?, accepted = ?, goal_uuid = ?, owner_json = ?"
            " WHERE operation_id = ? AND child_id = ?",
            (
                phase,
                int(accepted),
                ack.key.goal_uuid,
                json.dumps(asdict(ack.key.owner), sort_keys=True),
                token.operation_id,
                token.child_id,
            ),
        )

    def record_terminal(self, terminal: ActionTerminal) -> None:
        key = terminal.key
        row = self._query_one(
            "SELECT * FROM children WHERE operation_id = ? AND child_id = ?",
            (key.operation_id, key.child_id),
        )
        if row is None:
            raise MutationError(f"UNKNOWN_CHILD: {key.operation_id}/{key.child_id}")
        if row["goal_uuid"] not in (None, key.goal_uuid):
            raise MutationError(
                f"ACTION_IDENTITY_MISMATCH: {key.operation_id}/{key.child_id} "
                f"recorded {row['goal_uuid']} but terminal reports {key.goal_uuid}"
            )
        self._connection.execute(
            "UPDATE children SET phase = ?, goal_uuid = ?, owner_json = ?, succeeded = ?,"
            " stopped_confirmed = ?, cleanup_confirmed = ? WHERE operation_id = ? AND child_id = ?",
            (
                CHILD_TERMINAL,
                key.goal_uuid,
                json.dumps(asdict(key.owner), sort_keys=True),
                int(terminal.succeeded),
                int(terminal.stopped_confirmed),
                int(terminal.cleanup_confirmed),
                key.operation_id,
                key.child_id,
            ),
        )

    def cancel_parent(self, operation_id: str) -> CancelIntent:
        parent = self._require_parent(operation_id)
        revision = parent["revocation_revision"] + 1
        self._connection.execute(
            "UPDATE parents SET cancel_requested = 1, revocation_revision = ?, updated_ns = ?"
            " WHERE operation_id = ?",
            (revision, self._now_ns(), operation_id),
        )
        rows = self._query_all(
            "SELECT * FROM children WHERE operation_id = ? AND phase != ? ORDER BY sequence",
            (operation_id, CHILD_TERMINAL),
        )
        targets = tuple(
            RevokeTarget(
                PendingChildKey(
                    operation_id=operation_id,
                    child_id=row["child_id"],
                    runtime_id=row["runtime_id"],
                    execution_generation=row["execution_generation"],
                ),
                revision,
            )
            for row in rows
        )
        return CancelIntent(operation_id, targets)

    def pause(self, operation_id: str) -> None:
        parent = self._require_parent(operation_id)
        if parent["phase"] != PHASE_ACTIVE:
            raise MutationError(f"PARENT_NOT_ACTIVE: {operation_id} is {parent['phase']}")
        self._connection.execute(
            "UPDATE parents SET phase = ?, updated_ns = ? WHERE operation_id = ?",
            (PHASE_PAUSED, self._now_ns(), operation_id),
        )

    def settle_locked(
        self, operation_id: str, *, cleanup_confirmed: bool
    ) -> "_SettleOutcome":
        """Settle inside the caller's transaction, committing any refusal fence.

        A refusal must persist even though the caller raises: the transaction is allowed
        to commit and the caller raises afterwards, so a blocked parent can never be
        rolled back into "active" by the refusal itself.
        """
        parent = self._require_parent(operation_id)
        rows = self._children(operation_id)
        unconverged = [row for row in rows if row["phase"] != CHILD_TERMINAL]
        if unconverged:
            self._mark_blocked_locked(f"UNCONVERGED_CHILD: {operation_id}")
            return _SettleOutcome(
                projection=self.projection(operation_id),
                code=(
                    f"UNCONVERGED_CHILD: {operation_id} still has "
                    f"{', '.join(row['child_id'] for row in unconverged)}"
                ),
            )
        unproven = [
            row
            for row in rows
            if not (row["cleanup_confirmed"] or cleanup_confirmed)
            or (not row["succeeded"] and not row["stopped_confirmed"])
        ]
        if unproven:
            self._mark_blocked_locked(f"CLEANUP_NOT_CONFIRMED: {operation_id}")
            return _SettleOutcome(
                projection=self.projection(operation_id),
                code=(
                    f"CLEANUP_NOT_CONFIRMED: {operation_id} lacks cleanup or stop proof for "
                    f"{', '.join(row['child_id'] for row in unproven)}"
                ),
            )
        phase = PHASE_CANCELLED if parent["cancel_requested"] else PHASE_COMPLETE
        self._connection.execute(
            "UPDATE parents SET phase = ?, updated_ns = ? WHERE operation_id = ?",
            (phase, self._now_ns(), operation_id),
        )
        self._connection.execute(
            "UPDATE global_state SET state = ?, owner_operation_id = NULL, owner_domain = NULL,"
            " blocked_reason = NULL, updated_ns = ? WHERE singleton = 1",
            (IDLE, self._now_ns()),
        )
        return _SettleOutcome(projection=self.projection(operation_id), code=None)

    def settle(self, operation_id: str, *, cleanup_confirmed: bool) -> ParentProjection:
        """Settle one parent; raises after committing the fence when proof is missing."""
        with self.immediate_transaction():
            outcome = self.settle_locked(operation_id, cleanup_confirmed=cleanup_confirmed)
        if outcome.code:
            raise MutationError(outcome.code)
        return outcome.projection

    def projection(self, operation_id: str) -> ParentProjection:
        parent = self._query_one("SELECT * FROM parents WHERE operation_id = ?", (operation_id,))
        if parent is None:
            raise MutationError(f"UNKNOWN_OPERATION: {operation_id}")
        children = []
        for row in self._children(operation_id):
            owner = UNKNOWN_OWNER
            if row["owner_json"]:
                owner = OwnerKey(**json.loads(row["owner_json"]))
            children.append(
                ActionTerminal(
                    key=ActionKey(
                        operation_id=operation_id,
                        child_id=row["child_id"],
                        goal_uuid=row["goal_uuid"] or "",
                        owner=owner,
                        runtime_id=row["runtime_id"],
                        execution_generation=row["execution_generation"],
                    ),
                    succeeded=bool(row["succeeded"]),
                    stopped_confirmed=bool(row["stopped_confirmed"]),
                    cleanup_confirmed=bool(row["cleanup_confirmed"]),
                )
            )
        return ParentProjection(
            operation_id=operation_id,
            phase=parent["phase"],
            children=tuple(children),
            blocked_reason=parent["blocked_reason"],
        )

    # -- execution generations and lease fences ----------------------------------

    def execution_generation(self, domain) -> int:
        row = self._query_one(
            "SELECT generation FROM execution_generations WHERE domain = ?", (str(domain),)
        )
        return int(row["generation"]) if row is not None else 0

    def bump_execution_generation_locked(self, domain) -> int:
        """Advance the domain generation inside the caller's transaction."""
        generation = self.execution_generation(domain) + 1
        self._connection.execute(
            "INSERT INTO execution_generations (domain, generation) VALUES (?, ?)"
            " ON CONFLICT(domain) DO UPDATE SET generation = excluded.generation",
            (str(domain), generation),
        )
        return generation

    def open_lease_fence(self, domain, state: str) -> str:
        claim_id = uuid.uuid4().hex
        with self.immediate_transaction():
            now = self._now_ns()
            self._connection.execute(
                "INSERT INTO lease_operations (claim_id, domain, state, created_ns, updated_ns)"
                " VALUES (?, ?, ?, ?, ?)",
                (claim_id, str(domain), state, now, now),
            )
        return claim_id

    def record_lease_identity(self, claim_id: str, lease) -> None:
        self._connection.execute(
            "UPDATE lease_operations SET lease_json = ?, updated_ns = ? WHERE claim_id = ?",
            (json.dumps(asdict(lease), sort_keys=True), self._now_ns(), claim_id),
        )

    def finish_lease_fence_locked(self, claim_id: str, state: str, *, expect: str) -> None:
        row = self._query_one("SELECT state FROM lease_operations WHERE claim_id = ?", (claim_id,))
        if row is None:
            raise MutationError(f"UNKNOWN_LEASE_FENCE: {claim_id}")
        if row["state"] != expect:
            raise MutationError(
                f"LEASE_FENCE_STATE_CHANGED: {claim_id} is {row['state']}, expected {expect}"
            )
        self._connection.execute(
            "UPDATE lease_operations SET state = ?, updated_ns = ? WHERE claim_id = ?",
            (state, self._now_ns(), claim_id),
        )

    def fail_lease_fence(self, claim_id: str, reason: str) -> None:
        """Keep an unresolved fence and block the service; never auto-retry the lease."""
        with self.immediate_transaction():
            row = self._query_one("SELECT state, reason FROM lease_operations WHERE claim_id = ?", (claim_id,))
            if row is None:
                raise MutationError(f"UNKNOWN_LEASE_FENCE: {claim_id}")
            if row["state"] in OPEN_LEASE_STATES and row["reason"]:
                return
            self._connection.execute(
                "UPDATE lease_operations SET state = ?, reason = ?, updated_ns = ? WHERE claim_id = ?",
                (LEASE_FAILED, reason, self._now_ns(), claim_id),
            )
            self._mark_blocked_locked(f"LEASE_FENCE_FAILED: {reason}")

    def open_lease_fences(self) -> tuple[str, ...]:
        placeholders = ", ".join("?" for _ in OPEN_LEASE_STATES)
        rows = self._query_all(
            f"SELECT claim_id FROM lease_operations WHERE state IN ({placeholders}) ORDER BY created_ns",
            OPEN_LEASE_STATES,
        )
        return tuple(row["claim_id"] for row in rows)

    def open_renew_fence(self, domain) -> str | None:
        row = self._query_one(
            "SELECT claim_id FROM lease_operations WHERE domain = ? AND state = ?"
            " ORDER BY created_ns LIMIT 1",
            (str(domain), LEASE_RENEWING),
        )
        return row["claim_id"] if row is not None else None

    def lease_operation(self, claim_id: str) -> dict | None:
        row = self._query_one("SELECT * FROM lease_operations WHERE claim_id = ?", (claim_id,))
        if row is None:
            return None
        return {
            "claim_id": row["claim_id"],
            "domain": row["domain"],
            "state": row["state"],
            "lease": json.loads(row["lease_json"]) if row["lease_json"] else None,
            "reason": row["reason"],
        }

    # -- helpers -----------------------------------------------------------------

    def _require_parent(self, operation_id: str) -> sqlite3.Row:
        parent = self._query_one("SELECT * FROM parents WHERE operation_id = ?", (operation_id,))
        if parent is None:
            raise MutationError(f"UNKNOWN_OPERATION: {operation_id}")
        return parent

    def _children(self, operation_id: str) -> list[sqlite3.Row]:
        return self._query_all(
            "SELECT * FROM children WHERE operation_id = ? ORDER BY sequence", (operation_id,)
        )

    @staticmethod
    def _reservation_from_row(row: sqlite3.Row) -> Reservation:
        spec = OperationSpec(
            command_id=row["command_id"],
            domain=Domain(row["domain"]),
            kind=row["kind"],
            payload=json.loads(row["payload_json"]),
            runtime_id=row["runtime_id"],
            execution_generation=row["execution_generation"],
            deadline_ns=row["deadline_ns"],
        )
        return Reservation(
            operation_id=row["operation_id"],
            spec=spec,
            phase=row["phase"],
            cancel_requested=bool(row["cancel_requested"]),
        )

    @staticmethod
    def _token_from_row(row: sqlite3.Row) -> DispatchToken:
        return DispatchToken(
            operation_id=row["operation_id"],
            child_id=row["child_id"],
            runtime_id=row["runtime_id"],
            execution_generation=row["execution_generation"],
            deadline_ns=row["deadline_ns"],
            revocation_revision=row["revocation_revision"],
        )
