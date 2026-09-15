"""SQLite-backed durable supervisor state with one process-level writer."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
import uuid

from .models import (
    BatchBinding,
    CampaignBinding,
    CleanupReceipt,
    ExecutionOwnerIntent,
    OwnedExecutionRecord,
    PreflightReceipt,
    RetryItem,
    UpstreamCursor,
)


class StoreConflict(RuntimeError):
    """A durable identity or transaction invariant was violated."""


class CommandOutcomeUnknown(RuntimeError):
    """A command began durably but has no committed result."""


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _sha(value) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


_SCHEMA = """
CREATE TABLE IF NOT EXISTS commands (
  command_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, operation TEXT NOT NULL,
  state TEXT NOT NULL, result_json TEXT
);
CREATE TABLE IF NOT EXISTS manifests (
  manifest_id TEXT PRIMARY KEY, canonical_json TEXT NOT NULL, manifest_sha256 TEXT NOT NULL,
  source_config_sha256 TEXT NOT NULL, created_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS preflight_receipts (
  receipt_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL UNIQUE,
  manifest_id TEXT NOT NULL REFERENCES manifests(manifest_id),
  canonical_start_request_sha256 TEXT NOT NULL, receipt_json TEXT NOT NULL,
  receipt_sha256 TEXT NOT NULL, expires_at_monotonic_ns INTEGER NOT NULL, consumed_at_ns INTEGER
);
CREATE TABLE IF NOT EXISTS campaigns (
  campaign_id TEXT PRIMARY KEY, state TEXT NOT NULL,
  manifest_id TEXT NOT NULL REFERENCES manifests(manifest_id), executor_id TEXT NOT NULL,
  operation_id TEXT NOT NULL, executor_config_sha256 TEXT NOT NULL,
  execution_mode TEXT NOT NULL CHECK (execution_mode IN ('SEQUENTIAL','PARALLEL','ADAPTIVE')),
  execution_config_json TEXT NOT NULL, execution_config_sha256 TEXT NOT NULL,
  preflight_receipt_id TEXT NOT NULL UNIQUE REFERENCES preflight_receipts(receipt_id)
);
CREATE TABLE IF NOT EXISTS campaign_batches (
  batch_id TEXT PRIMARY KEY, campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  batch_kind TEXT NOT NULL CHECK (batch_kind IN ('FIRST_PASS','FULL_RESTART_RETRY')),
  point_id TEXT, state TEXT NOT NULL, coordinator_epoch INTEGER, pool_generation INTEGER,
  journal_root TEXT NOT NULL, terminal_summary_sha256 TEXT, cleanup_receipt_sha256 TEXT
);
CREATE TABLE IF NOT EXISTS upstream_cursors (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id),
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('COORDINATOR','ADAPTIVE_RUNNER')),
  owner_epoch_or_generation INTEGER NOT NULL, segment_id TEXT NOT NULL, event_id TEXT NOT NULL,
  frame_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS owned_execution (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id),
  owner_kind TEXT NOT NULL CHECK (owner_kind IN ('COORDINATOR','ADAPTIVE_WRAPPER')),
  state TEXT NOT NULL, spawn_token TEXT NOT NULL UNIQUE, expected_executable TEXT NOT NULL,
  argv_sha256 TEXT NOT NULL, environment_sha256 TEXT NOT NULL, source_commit TEXT NOT NULL,
  install_prefix TEXT NOT NULL, runtime_sha256 TEXT NOT NULL, pid INTEGER, pgid INTEGER,
  started_ticks INTEGER, control_socket TEXT, coordinator_epoch INTEGER, runner_pid INTEGER,
  runner_journal_root TEXT, acknowledged_at_ns INTEGER
);
CREATE TABLE IF NOT EXISTS adaptive_projection_cache (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id), current_generation INTEGER,
  current_level INTEGER, fallback_history_json TEXT NOT NULL, resource_observations_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS retry_queue (
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id), ordinal INTEGER NOT NULL,
  point_id TEXT NOT NULL, state TEXT NOT NULL, batch_id TEXT REFERENCES campaign_batches(batch_id),
  cleanup_receipt_sha256 TEXT, PRIMARY KEY (campaign_id, ordinal)
);
CREATE TABLE IF NOT EXISTS leases (
  lease_id TEXT PRIMARY KEY, service_session_id TEXT NOT NULL, generation INTEGER NOT NULL,
  expires_monotonic_ns INTEGER NOT NULL, state TEXT NOT NULL
);
"""


class SupervisorStore:
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
        lock_path = root / "supervisor.lock"
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o600)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            os.close(lock_fd)
            raise StoreConflict("VALIDATION_SUPERVISOR_ACTIVE") from error
        try:
            connection = sqlite3.connect(root / "supervisor.sqlite3", isolation_level=None)
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

    def begin_command(self, command_id: str, request_sha256: str, operation: str) -> None:
        with self._transaction():
            row = self._connection.execute(
                "SELECT request_sha256, operation FROM commands WHERE command_id = ?", (command_id,)
            ).fetchone()
            if row is not None:
                if row["request_sha256"] != request_sha256 or row["operation"] != operation:
                    raise StoreConflict("COMMAND_ID_REUSED")
                return
            self._connection.execute(
                "INSERT INTO commands VALUES (?, ?, ?, 'IN_PROGRESS', NULL)",
                (command_id, request_sha256, operation),
            )

    def repeat_command(self, command_id: str, request_sha256: str):
        row = self._connection.execute(
            "SELECT request_sha256, state, result_json FROM commands WHERE command_id = ?",
            (command_id,),
        ).fetchone()
        if row is None:
            return None
        if row["request_sha256"] != request_sha256:
            raise StoreConflict("COMMAND_ID_REUSED")
        if row["state"] != "COMPLETE" or row["result_json"] is None:
            raise CommandOutcomeUnknown("COMMAND_OUTCOME_UNKNOWN")
        return json.loads(row["result_json"])

    def finish_command(self, command_id: str, result) -> None:
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE commands SET state = 'COMPLETE', result_json = ? "
                "WHERE command_id = ? AND state = 'IN_PROGRESS'",
                (_json(result), command_id),
            )
            if cursor.rowcount != 1:
                raise StoreConflict("COMMAND_NOT_IN_PROGRESS")

    def record_manifest(
        self, manifest_id: str, document, *, source_config_sha256: str, created_at_ns: int
    ) -> str:
        canonical = _json(document)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with self._transaction():
            try:
                self._connection.execute(
                    "INSERT INTO manifests VALUES (?, ?, ?, ?, ?)",
                    (manifest_id, canonical, digest, source_config_sha256, created_at_ns),
                )
            except sqlite3.IntegrityError as error:
                raise StoreConflict("MANIFEST_CONFLICT") from error
        return digest

    def record_preflight_receipt(self, receipt: PreflightReceipt) -> str:
        canonical = _json(dict(receipt.receipt))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        with self._transaction():
            try:
                self._connection.execute(
                    "INSERT INTO preflight_receipts VALUES (?, ?, ?, ?, ?, ?, ?, NULL)",
                    (
                        receipt.receipt_id,
                        receipt.campaign_id,
                        receipt.manifest_id,
                        receipt.canonical_start_request_sha256,
                        canonical,
                        digest,
                        receipt.expires_at_monotonic_ns,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise StoreConflict("PREFLIGHT_RECEIPT_CONFLICT") from error
        return digest

    def consume_preflight_and_bind_campaign_batch(
        self,
        receipt_id: str,
        request_sha256: str,
        campaign: CampaignBinding,
        batch: BatchBinding,
        *,
        now_monotonic_ns: int,
    ) -> None:
        if campaign.campaign_id != batch.campaign_id or campaign.preflight_receipt_id != receipt_id:
            raise StoreConflict("CAMPAIGN_BATCH_BINDING_MISMATCH")
        config_json = _json(dict(campaign.execution_config))
        with self._transaction():
            row = self._connection.execute(
                "SELECT * FROM preflight_receipts WHERE receipt_id = ?", (receipt_id,)
            ).fetchone()
            if row is None or row["campaign_id"] != campaign.campaign_id:
                raise StoreConflict("PREFLIGHT_RECEIPT_MISMATCH")
            if row["consumed_at_ns"] is not None:
                raise StoreConflict("PREFLIGHT_RECEIPT_CONSUMED")
            if row["canonical_start_request_sha256"] != request_sha256:
                raise StoreConflict("PREFLIGHT_REQUEST_MISMATCH")
            if now_monotonic_ns >= row["expires_at_monotonic_ns"]:
                raise StoreConflict("PREFLIGHT_RECEIPT_EXPIRED")
            self._connection.execute(
                "INSERT INTO campaigns VALUES (?, 'ACTIVE', ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    campaign.campaign_id,
                    campaign.manifest_id,
                    campaign.executor_id,
                    campaign.operation_id,
                    campaign.executor_config_sha256,
                    campaign.execution_mode,
                    config_json,
                    hashlib.sha256(config_json.encode("utf-8")).hexdigest(),
                    receipt_id,
                ),
            )
            self._insert_batch(batch)
            self._connection.execute(
                "UPDATE preflight_receipts SET consumed_at_ns = ? WHERE receipt_id = ?",
                (time.time_ns(), receipt_id),
            )

    def _insert_batch(self, batch: BatchBinding) -> None:
        self._connection.execute(
            "INSERT INTO campaign_batches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                batch.batch_id,
                batch.campaign_id,
                batch.batch_kind,
                batch.point_id,
                batch.state,
                batch.coordinator_epoch,
                batch.pool_generation,
                str(batch.journal_root),
                batch.terminal_summary_sha256,
                batch.cleanup_receipt_sha256,
            ),
        )

    def bind_retry_batch(self, batch: BatchBinding) -> None:
        if batch.batch_kind != "FULL_RESTART_RETRY":
            raise StoreConflict("RETRY_BATCH_KIND")
        with self._transaction():
            row = self._connection.execute(
                "SELECT ordinal FROM retry_queue WHERE campaign_id = ? AND point_id = ? "
                "AND state = 'QUEUED' ORDER BY ordinal LIMIT 1",
                (batch.campaign_id, batch.point_id),
            ).fetchone()
            if row is None:
                raise StoreConflict("RETRY_NOT_QUEUED")
            self._insert_batch(batch)
            self._connection.execute(
                "UPDATE retry_queue SET state = 'RUNNING', batch_id = ? "
                "WHERE campaign_id = ? AND ordinal = ?",
                (batch.batch_id, batch.campaign_id, row["ordinal"]),
            )

    def record_execution_owner_intent(self, intent) -> str:
        if not isinstance(intent, ExecutionOwnerIntent):
            request = intent
            owner_kind = (
                "ADAPTIVE_WRAPPER" if hasattr(request, "runtime_root") else "COORDINATOR"
            )
            executable = request.argv[0]
            runtime_digest = hashlib.sha256(executable.encode("utf-8")).hexdigest()
            intent = ExecutionOwnerIntent(
                batch_id=request.batch_id,
                owner_kind=owner_kind,
                spawn_token="spawn-" + uuid.uuid4().hex,
                expected_executable=executable,
                argv_sha256=_sha(tuple(request.argv)),
                environment_sha256=_sha(dict(request.environment)),
                source_commit="UNKNOWN",
                install_prefix=Path(executable).parent,
                runtime_sha256=runtime_digest,
                control_socket=getattr(request, "control_socket", None),
            )
        with self._transaction():
            try:
                self._connection.execute(
                    "INSERT INTO owned_execution "
                    "(batch_id, owner_kind, state, spawn_token, expected_executable, argv_sha256, "
                    "environment_sha256, source_commit, install_prefix, runtime_sha256, control_socket) "
                    "VALUES (?, ?, 'INTENT', ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        intent.batch_id,
                        intent.owner_kind,
                        intent.spawn_token,
                        intent.expected_executable,
                        intent.argv_sha256,
                        intent.environment_sha256,
                        intent.source_commit,
                        str(intent.install_prefix),
                        intent.runtime_sha256,
                        str(intent.control_socket) if intent.control_socket else None,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise StoreConflict("EXECUTION_OWNER_INTENT_CONFLICT") from error
        return intent.spawn_token

    def acknowledge_execution_owner(self, owned=None, **values) -> None:
        if owned is not None:
            values = {
                "batch_id": owned.batch_id,
                "pid": owned.pid,
                "pgid": owned.pgid,
                "started_ticks": owned.started_ticks,
                "coordinator_epoch": getattr(owned, "coordinator_epoch", None),
                "runner_pid": getattr(owned, "runner_pid", None),
                "runner_journal_root": getattr(owned, "runner_journal_root", None),
                "argv_sha256": owned.argv_sha256,
                "environment_sha256": owned.environment_sha256,
            }
        batch_id = values["batch_id"]
        with self._transaction():
            row = self._connection.execute(
                "SELECT * FROM owned_execution WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            if row is None or row["state"] != "INTENT":
                raise StoreConflict("EXECUTION_OWNER_INTENT_MISSING")
            for name in ("argv_sha256", "environment_sha256"):
                if values.get(name) is not None and values[name] != row[name]:
                    raise StoreConflict("EXECUTION_OWNER_FINGERPRINT_MISMATCH")
            self._connection.execute(
                "UPDATE owned_execution SET state='RUNNING', pid=?, pgid=?, started_ticks=?, "
                "coordinator_epoch=?, runner_pid=?, runner_journal_root=?, acknowledged_at_ns=? "
                "WHERE batch_id=?",
                (
                    values["pid"],
                    values["pgid"],
                    values["started_ticks"],
                    values.get("coordinator_epoch"),
                    values.get("runner_pid"),
                    str(values.get("runner_journal_root"))
                    if values.get("runner_journal_root") is not None
                    else None,
                    time.time_ns(),
                    batch_id,
                ),
            )

    def owned_execution(self, batch_id: str) -> OwnedExecutionRecord | None:
        row = self._connection.execute(
            "SELECT * FROM owned_execution WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            return None
        return OwnedExecutionRecord(
            batch_id=row["batch_id"],
            owner_kind=row["owner_kind"],
            state=row["state"],
            spawn_token=row["spawn_token"],
            expected_executable=row["expected_executable"],
            argv_sha256=row["argv_sha256"],
            environment_sha256=row["environment_sha256"],
            source_commit=row["source_commit"],
            install_prefix=Path(row["install_prefix"]),
            runtime_sha256=row["runtime_sha256"],
            pid=row["pid"],
            pgid=row["pgid"],
            started_ticks=row["started_ticks"],
            control_socket=Path(row["control_socket"]) if row["control_socket"] else None,
            coordinator_epoch=row["coordinator_epoch"],
            runner_pid=row["runner_pid"],
            runner_journal_root=Path(row["runner_journal_root"])
            if row["runner_journal_root"]
            else None,
            acknowledged_at_ns=row["acknowledged_at_ns"],
        )

    owned_coordinator = owned_execution

    def accept_upstream_cursor(self, cursor: UpstreamCursor) -> None:
        with self._transaction():
            row = self._connection.execute(
                "SELECT * FROM upstream_cursors WHERE batch_id = ?", (cursor.batch_id,)
            ).fetchone()
            values = asdict(cursor)
            if row is not None:
                if (
                    row["segment_id"] == cursor.segment_id
                    and row["event_id"] == cursor.event_id
                ):
                    if all(row[key] == value for key, value in values.items()):
                        return
                    raise StoreConflict("UPSTREAM_CURSOR_CONFLICT")
                if (
                    row["owner_kind"] != cursor.owner_kind
                    or cursor.owner_epoch_or_generation < row["owner_epoch_or_generation"]
                ):
                    raise StoreConflict("UPSTREAM_CURSOR_CONFLICT")
                self._connection.execute(
                    "UPDATE upstream_cursors SET owner_epoch_or_generation=?, segment_id=?, "
                    "event_id=?, frame_sha256=? WHERE batch_id=?",
                    (
                        cursor.owner_epoch_or_generation,
                        cursor.segment_id,
                        cursor.event_id,
                        cursor.frame_sha256,
                        cursor.batch_id,
                    ),
                )
                return
            self._connection.execute(
                "INSERT INTO upstream_cursors VALUES (?, ?, ?, ?, ?, ?)",
                tuple(values.values()),
            )

    def enqueue_retries(self, campaign_id: str, point_ids) -> None:
        points = tuple(point_ids)
        if len(points) != len(set(points)):
            raise StoreConflict("RETRY_POINT_DUPLICATE")
        with self._transaction():
            for ordinal, point_id in enumerate(points):
                self._connection.execute(
                    "INSERT INTO retry_queue VALUES (?, ?, ?, 'QUEUED', NULL, NULL)",
                    (campaign_id, ordinal, point_id),
                )

    def next_retry(self, campaign_id: str) -> RetryItem | None:
        row = self._connection.execute(
            "SELECT * FROM retry_queue WHERE campaign_id = ? AND state != 'COMPLETE' "
            "ORDER BY ordinal LIMIT 1",
            (campaign_id,),
        ).fetchone()
        if row is None:
            return None
        return RetryItem(
            campaign_id=row["campaign_id"], ordinal=row["ordinal"], point_id=row["point_id"],
            state=row["state"], batch_id=row["batch_id"]
        )

    def record_cleanup_and_advance_retry(self, receipt: CleanupReceipt) -> None:
        with self._transaction():
            row = self._connection.execute(
                "SELECT ordinal, batch_id FROM retry_queue WHERE campaign_id=? AND point_id=? "
                "AND state='RUNNING'",
                (receipt.campaign_id, receipt.point_id),
            ).fetchone()
            if row is None or row["batch_id"] != receipt.batch_id:
                raise StoreConflict("RETRY_CLEANUP_BINDING_MISMATCH")
            self._connection.execute(
                "UPDATE campaign_batches SET state='CLEANED', cleanup_receipt_sha256=? "
                "WHERE batch_id=?",
                (receipt.receipt_sha256, receipt.batch_id),
            )
            self._connection.execute(
                "UPDATE retry_queue SET state='COMPLETE', cleanup_receipt_sha256=? "
                "WHERE campaign_id=? AND ordinal=?",
                (receipt.receipt_sha256, receipt.campaign_id, row["ordinal"]),
            )

    def batch(self, batch_id: str) -> BatchBinding | None:
        row = self._connection.execute(
            "SELECT * FROM campaign_batches WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            return None
        return BatchBinding(
            batch_id=row["batch_id"], campaign_id=row["campaign_id"],
            batch_kind=row["batch_kind"], point_id=row["point_id"], state=row["state"],
            coordinator_epoch=row["coordinator_epoch"], pool_generation=row["pool_generation"],
            journal_root=Path(row["journal_root"]),
            terminal_summary_sha256=row["terminal_summary_sha256"],
            cleanup_receipt_sha256=row["cleanup_receipt_sha256"]
        )

    def record_batch_cleanup(self, batch_id: str, receipt_sha256: str) -> None:
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE campaign_batches SET state='CLEANED', cleanup_receipt_sha256=? "
                "WHERE batch_id=?",
                (receipt_sha256, batch_id),
            )
            if cursor.rowcount != 1:
                raise StoreConflict("BATCH_NOT_FOUND")

    def list_campaigns(self) -> tuple[dict, ...]:
        return tuple(
            dict(row)
            for row in self._connection.execute(
                "SELECT campaign_id, state, execution_mode FROM campaigns ORDER BY campaign_id"
            )
        )

    def reconcile(self) -> dict:
        ambiguous = tuple(
            row[0] for row in self._connection.execute(
                "SELECT command_id FROM commands WHERE state='IN_PROGRESS' ORDER BY command_id"
            )
        )
        intents = tuple(
            row[0] for row in self._connection.execute(
                "SELECT batch_id FROM owned_execution WHERE state='INTENT' ORDER BY batch_id"
            )
        )
        return {"ambiguous_commands": ambiguous, "unacknowledged_owner_intents": intents}

    def table_names(self) -> set[str]:
        return {
            row[0]
            for row in self._connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
