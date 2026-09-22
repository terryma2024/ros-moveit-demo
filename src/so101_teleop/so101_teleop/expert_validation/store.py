"""SQLite-backed durable supervisor state with one process-level writer."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import asdict, dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import time
import uuid

from .coordinator import CoordinatorBinding, CoordinatorStartRequest
from .preflight import canonical_start_request_sha256
from ..process_identity import (
    IDENTITY_EXITED,
    command_fingerprint,
    group_has_live_descendants,
    identity_state,
)

from .owner_tree import ConfirmedOwnerProcess, OwnerIntent, OwnerRecord
from .execution_context import (
    CONTEXT_TYPES,
    CANDIDATE_CONTEXT_KIND,
    CandidateExecutionContext,
    ProductionExecutionContext,
    PRODUCTION_CONTEXT_KIND,
    RETRY_BATCH_KIND,
    RETRY_PROFILE,
    RETRY_SCHEMA_VERSION,
    RETRY_WORKER_COUNT,
    install_binding_sha256,
    retry_batch_root,
    runtime_closure_sha256,
)
from .models import (
    BatchBinding,
    CampaignBinding,
    CleanupReceipt,
    ExecutionOwnerIntent,
    FirstPassSelectionBinding,
    OwnedExecutionRecord,
    PreflightReceipt,
    RetryItem,
    RetrySelectionBinding,
    RetryStartRequest,
    UpstreamCursor,
    ValidationManifest,
)


@dataclass(frozen=True)
class ProjectionSnapshot:
    """The durable reducer state and accepted cursor of one batch."""

    state: object | None
    cursor: object | None


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
CREATE TABLE IF NOT EXISTS projection_state (
  batch_id TEXT PRIMARY KEY REFERENCES campaign_batches(batch_id),
  state_json TEXT NOT NULL,
  owner_epoch_or_generation INTEGER NOT NULL, segment_id TEXT NOT NULL,
  event_id TEXT NOT NULL, frame_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS projection_events (
  batch_id TEXT NOT NULL REFERENCES campaign_batches(batch_id),
  sequence INTEGER NOT NULL, frame_sha256 TEXT NOT NULL, attempt_id TEXT,
  PRIMARY KEY (batch_id, sequence, frame_sha256)
);
CREATE TABLE IF NOT EXISTS projection_attempts (
  batch_id TEXT NOT NULL REFERENCES campaign_batches(batch_id),
  attempt_id TEXT NOT NULL, point_id TEXT,
  PRIMARY KEY (batch_id, attempt_id)
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
CREATE TABLE IF NOT EXISTS fixed_control_bindings (
  batch_id TEXT PRIMARY KEY REFERENCES owned_execution(batch_id),
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id), batch_root TEXT NOT NULL,
  control_socket TEXT NOT NULL, coordinator_epoch INTEGER NOT NULL,
  control_token TEXT NOT NULL, control_token_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery_fences (
  campaign_id TEXT PRIMARY KEY REFERENCES campaigns(campaign_id),
  batch_id TEXT NOT NULL REFERENCES campaign_batches(batch_id),
  reason TEXT NOT NULL, command_id TEXT NOT NULL, created_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_intents (
  spawn_token TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL,
  batch_id TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('ADAPTER','CAMPAIGN','BROKER','WORKER','STATION')),
  generation INTEGER NOT NULL,
  parent_spawn_token TEXT,
  expected_executable TEXT NOT NULL,
  argv_sha256 TEXT NOT NULL,
  own_session INTEGER NOT NULL,
  created_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_processes (
  spawn_token TEXT PRIMARY KEY REFERENCES owner_intents(spawn_token),
  pid INTEGER NOT NULL, pgid INTEGER NOT NULL, started_ticks INTEGER NOT NULL,
  command_sha256 TEXT NOT NULL, confirmed_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS owner_cleanup_receipts (
  campaign_id TEXT NOT NULL, batch_id TEXT NOT NULL, generation INTEGER NOT NULL,
  receipt_sha256 TEXT NOT NULL, receipt_json TEXT NOT NULL, recorded_at_ns INTEGER NOT NULL,
  PRIMARY KEY (campaign_id, batch_id, generation)
);
CREATE TABLE IF NOT EXISTS operator_recoveries (
  campaign_id TEXT PRIMARY KEY REFERENCES recovery_fences(campaign_id),
  command_id TEXT NOT NULL UNIQUE,
  receipt_json TEXT NOT NULL, receipt_sha256 TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS retry_admissions (
  command_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  context_kind TEXT NOT NULL CHECK (context_kind IN ('CANDIDATE','PRODUCTION')),
  context_id TEXT NOT NULL, context_scope TEXT NOT NULL,
  batch_id TEXT NOT NULL UNIQUE REFERENCES campaign_batches(batch_id),
  point_id TEXT NOT NULL,
  original_batch_id TEXT NOT NULL REFERENCES campaign_batches(batch_id),
  original_result_sha256 TEXT NOT NULL,
  execution_profile TEXT NOT NULL, schema_version INTEGER NOT NULL,
  config_sha256 TEXT NOT NULL, runtime_closure_sha256 TEXT NOT NULL,
  worker_count INTEGER NOT NULL, evidence_root TEXT NOT NULL,
  lease_id TEXT, lease_generation INTEGER, owner_generation INTEGER NOT NULL,
  max_runs INTEGER, spawn_token TEXT NOT NULL,
  binding_json TEXT NOT NULL, binding_sha256 TEXT NOT NULL, created_at_ns INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS first_pass_admissions (
  command_id TEXT PRIMARY KEY,
  campaign_id TEXT NOT NULL REFERENCES campaigns(campaign_id),
  context_kind TEXT NOT NULL CHECK (context_kind IN ('CANDIDATE')),
  context_id TEXT NOT NULL, context_scope TEXT NOT NULL,
  batch_id TEXT NOT NULL UNIQUE REFERENCES campaign_batches(batch_id),
  manifest_id TEXT NOT NULL,
  execution_profile TEXT NOT NULL, schema_version INTEGER NOT NULL,
  config_sha256 TEXT NOT NULL, runtime_closure_sha256 TEXT NOT NULL,
  worker_count INTEGER NOT NULL, evidence_root TEXT NOT NULL,
  owner_generation INTEGER NOT NULL, max_runs INTEGER,
  spawn_token TEXT NOT NULL,
  binding_json TEXT NOT NULL, binding_sha256 TEXT NOT NULL, created_at_ns INTEGER NOT NULL
);
"""


def _owner_intent_from_row(row) -> OwnerIntent:
    return OwnerIntent(
        campaign_id=row["campaign_id"],
        batch_id=row["batch_id"],
        role=row["role"],
        generation=row["generation"],
        spawn_token=row["spawn_token"],
        parent_spawn_token=row["parent_spawn_token"],
        expected_executable=row["expected_executable"],
        argv_sha256=row["argv_sha256"],
        own_session=bool(row["own_session"]),
        created_at_ns=row["created_at_ns"],
    )


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

    def manifest(self, manifest_id: str, *, current_source_config_sha256: str) -> ValidationManifest | None:
        row = self._connection.execute(
            "SELECT * FROM manifests WHERE manifest_id = ?", (manifest_id,)
        ).fetchone()
        if row is None:
            return None
        return ValidationManifest(
            manifest_id=row["manifest_id"],
            canonical_document=json.loads(row["canonical_json"]),
            manifest_sha256=row["manifest_sha256"],
            source_config_sha256=row["source_config_sha256"],
            created_at_ns=row["created_at_ns"],
            stale=row["source_config_sha256"] != current_source_config_sha256,
        )

    def record_preflight_receipt(self, receipt: PreflightReceipt) -> str:
        with self._transaction():
            return self._record_preflight_receipt_locked(receipt)

    def _record_preflight_receipt_locked(self, receipt: PreflightReceipt) -> str:
        canonical = _json(dict(receipt.receipt))
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
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
        with self._transaction():
            self._consume_preflight_locked(
                receipt_id, request_sha256, campaign, batch, now_monotonic_ns=now_monotonic_ns
            )

    def _consume_preflight_locked(
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

    def admit_retry(
        self,
        *,
        request: RetryStartRequest,
        context: CandidateExecutionContext | ProductionExecutionContext,
        spawn_intent: OwnerIntent,
    ) -> RetrySelectionBinding:
        """Admit exactly one retry, or commit nothing at all.

        One SQLite transaction consumes the one-time command, validates the original business
        ``FAILED`` result and its terminal-clean batch, refuses any active or unknown owner and any
        standing fence, checks the profile/config/closure/worker-count/batch/evidence-root/lease
        binding the context carries, then creates the retry binding *and* writes the owner spawn
        intent. If any step fails, every row rolls back and the command is not consumed, so a
        corrected admission can still use it.

        A spawn that fails *after* this returns keeps the intent (unconfirmed) and the fence the
        caller records; because the command row is still ``IN_PROGRESS`` it can never be replayed.
        """

        if not isinstance(request, RetryStartRequest):
            raise StoreConflict("RETRY_REQUEST_INVALID")
        if not isinstance(context, CONTEXT_TYPES):
            raise StoreConflict("RETRY_CONTEXT_KIND")
        if not isinstance(spawn_intent, OwnerIntent):
            raise StoreConflict("RETRY_SPAWN_INTENT_INVALID")
        now_monotonic_ns = time.monotonic_ns()
        with self._transaction():
            self._check_retry_coordinates(request, context, now_monotonic_ns)
            self._consume_retry_command(request, context)
            self._check_retry_original(request, context)
            self._check_retry_owner(request)
            return self._bind_admitted_retry(request, context, spawn_intent)

    def _check_retry_coordinates(self, request, context, now_monotonic_ns: int) -> None:
        for name, code in self._RETRY_COORDINATES:
            if getattr(request, name) != getattr(context, name):
                raise StoreConflict(code)
        if context.is_expired(now_monotonic_ns):
            raise StoreConflict("RETRY_CONTEXT_EXPIRED")
        if (
            request.execution_profile != RETRY_PROFILE
            or request.schema_version != RETRY_SCHEMA_VERSION
            or request.batch_kind != RETRY_BATCH_KIND
            or request.worker_count != RETRY_WORKER_COUNT
        ):
            raise StoreConflict("RETRY_PROFILE_INVALID")
        if context.kind == PRODUCTION_CONTEXT_KIND:
            self._check_production_retry_binding(request, context, now_monotonic_ns)
        else:
            self._check_candidate_retry_budget(context)

    def _check_production_retry_binding(self, request, context, now_monotonic_ns: int) -> None:
        """The installed copy, the service session and the live control lease, checked as bound."""

        if context.install_binding() != context.install_binding_sha256 or (
            context.install_binding()
            != install_binding_sha256(
                install_prefix=request.install_prefix,
                runtime_closure_sha256=request.runtime_closure_sha256,
            )
        ):
            raise StoreConflict("RETRY_INSTALL_BINDING_MISMATCH")
        lease = self.current_lease()
        if lease is None:
            raise StoreConflict("RETRY_LEASE_REQUIRED")
        if (
            lease["lease_id"] != context.lease_id
            or lease["service_session_id"] != context.service_session_id
            or lease["generation"] != context.lease_generation
        ):
            raise StoreConflict("RETRY_LEASE_MISMATCH")
        if now_monotonic_ns >= lease["expires_monotonic_ns"]:
            raise StoreConflict("RETRY_LEASE_EXPIRED")

    def _check_candidate_retry_budget(self, context) -> None:
        """A candidate dispatch authorizes a bounded number of admitted runs, never more."""

        row = self._connection.execute(
            "SELECT COUNT(*) FROM retry_admissions WHERE context_kind = ? AND context_scope = ?",
            (CANDIDATE_CONTEXT_KIND, context.scope),
        ).fetchone()
        if int(row[0]) >= context.max_runs:
            raise StoreConflict("RETRY_MAX_RUNS_EXCEEDED")

    def _consume_retry_command(self, request, context) -> None:
        digest = _sha({
            "operation": "ADMIT_RETRY",
            "request": request.as_document(),
            "context": context.as_document(),
        })
        row = self._connection.execute(
            "SELECT request_sha256 FROM commands WHERE command_id = ?", (request.command_id,)
        ).fetchone()
        if row is not None:
            if row["request_sha256"] == digest:
                raise StoreConflict("RETRY_COMMAND_ALREADY_CONSUMED")
            raise StoreConflict("RETRY_COMMAND_ID_REUSED")
        self._connection.execute(
            "INSERT INTO commands VALUES (?, ?, 'ADMIT_RETRY', 'IN_PROGRESS', NULL)",
            (request.command_id, digest),
        )

    def _check_retry_original(self, request, context) -> None:
        """The original must be a committed *business* failure of a terminal-clean first pass."""

        campaign = self._connection.execute(
            "SELECT manifest_id FROM campaigns WHERE campaign_id = ?", (request.campaign_id,)
        ).fetchone()
        if campaign is None:
            raise StoreConflict("RETRY_CAMPAIGN_UNKNOWN")
        if campaign["manifest_id"] != context.manifest_id:
            raise StoreConflict("RETRY_MANIFEST_MISMATCH")

        original = self.batch(request.original_batch_id)
        if original is None:
            raise StoreConflict("RETRY_ORIGINAL_BATCH_UNKNOWN")
        if original.campaign_id != request.campaign_id or original.batch_kind != "FIRST_PASS":
            raise StoreConflict("RETRY_ORIGINAL_BATCH_MISMATCH")
        if self.batch(request.batch_id) is not None:
            raise StoreConflict("RETRY_BATCH_EXISTS")
        if original.cleanup_receipt_sha256 is None:
            raise StoreConflict("RETRY_ORIGINAL_CLEANUP_INCOMPLETE")

        queue = self._connection.execute(
            "SELECT ordinal FROM retry_queue WHERE campaign_id = ? AND point_id = ? "
            "AND state = 'QUEUED' ORDER BY ordinal LIMIT 1",
            (request.campaign_id, request.point_id),
        ).fetchone()
        if queue is None:
            raise StoreConflict("RETRY_NOT_QUEUED")

        manifest = self._connection.execute(
            "SELECT canonical_json FROM manifests WHERE manifest_id = ?",
            (context.manifest_id,),
        ).fetchone()
        if manifest is None:
            raise StoreConflict("RETRY_MANIFEST_UNKNOWN")
        document = json.loads(manifest["canonical_json"])
        if (
            document.get("catalog_sha256") != request.original_catalog_sha256
            or document.get("selection_sha256") != request.original_selection_sha256
        ):
            raise StoreConflict("RETRY_ORIGINAL_SELECTION_MISMATCH")
        if request.point_id not in tuple(document.get("point_ids") or ()):
            raise StoreConflict("RETRY_ORIGINAL_POINT_UNKNOWN")

        state = self.read_projection_state(request.original_batch_id).state
        point = None if state is None else state.points.get(request.point_id)
        if point is None or point.status.value == "UNRUN":
            raise StoreConflict("RETRY_ORIGINAL_UNRUN")
        if point.status.value == "INDETERMINATE":
            raise StoreConflict("RETRY_ORIGINAL_INDETERMINATE")
        if point.status.value != "FAILED":
            raise StoreConflict("RETRY_ORIGINAL_NOT_FAILED")
        attempts = tuple(
            attempt for attempt in state.attempts.values()
            if attempt.point_id == request.point_id
        )
        if any(attempt.validity.value == "INVALID" for attempt in attempts):
            # An attempt-level INVALID is not a business failure and never becomes one.
            raise StoreConflict("RETRY_ORIGINAL_INVALID")
        if any(attempt.infrastructure.value == "FAILED" for attempt in attempts):
            raise StoreConflict("RETRY_ORIGINAL_INFRA_FAILED")
        if point.phase.value != "TERMINAL" or point.result_sha256 is None:
            raise StoreConflict("RETRY_ORIGINAL_NOT_TERMINAL")
        if point.result_sha256 != request.original_result_sha256:
            raise StoreConflict("RETRY_ORIGINAL_RESULT_MISMATCH")
        if state.batch_business_terminal is None:
            raise StoreConflict("RETRY_ORIGINAL_NOT_TERMINAL")
        if state.batch_cleanup_complete is not True:
            raise StoreConflict("RETRY_ORIGINAL_CLEANUP_INCOMPLETE")

    def _check_retry_owner(self, request) -> None:
        """No standing fence, no live owner and no spawn whose outcome is unknowable."""

        self._check_no_owner_or_fence(
            request.campaign_id,
            fence="RETRY_RECOVERY_FENCE",
            active="RETRY_OWNER_ACTIVE",
            unknown="RETRY_OWNER_UNKNOWN",
        )

    #: The durable owner state a ``RUNNING`` execution is retired to once its process is proven
    #: gone. It is a state of the owner row, not of the batch: the batch keeps whatever terminal or
    #: cleaned state its own journal earned.
    OWNER_STATE_EXITED = "EXITED"

    def reconcile_exited_execution_owner(self, batch_id: str) -> bool:
        """Retire one ``RUNNING`` owner whose recorded process is proven gone; never assume it.

        The only evidence that retires an owner is a proven-absent identity: the platform reports no
        process at the recorded pid, or the pid now carries a different start marker, and the
        recorded process group holds no live process other than that leader. Everything else - a
        live process, an identity this caller may not read, a row without a recorded identity, a
        group that cannot be read or still has members - leaves the row ``RUNNING`` and returns
        ``False``, because an unknown owner must keep blocking.

        The transition is idempotent and moves exactly the row the proof was read from: the update
        is guarded on the batch, the spawn token and the whole recorded identity, so an unrelated
        owner row can never be overwritten and a second call changes nothing. ``True`` means the
        post-condition holds - this batch has no standing ``RUNNING`` owner any more.
        """

        row = self._connection.execute(
            "SELECT * FROM owned_execution WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None or row["state"] != "RUNNING":
            return True
        if not self._owner_identity_proven_gone(row):
            return False
        cursor = self._connection.execute(
            "UPDATE owned_execution SET state = ? "
            "WHERE batch_id = ? AND state = 'RUNNING' AND spawn_token = ? "
            "AND pid IS ? AND pgid IS ? AND started_ticks IS ?",
            (
                self.OWNER_STATE_EXITED,
                batch_id,
                row["spawn_token"],
                row["pid"],
                row["pgid"],
                row["started_ticks"],
            ),
        )
        if cursor.rowcount != 1:
            # The row moved under the proof. Nothing may be retired without knowing which row was.
            raise StoreConflict("EXECUTION_OWNER_RECONCILE_MISMATCH")
        return True

    def _owner_identity_proven_gone(self, row) -> bool:
        """Whether the identity of one ``RUNNING`` owner row is proven not to be running.

        The identity read and the group read are the same machinery the supervisor's own
        unresolved-owner question uses, so the store and the supervisor cannot disagree about one
        process. A row that never recorded an identity (a spawn intent that was never acknowledged)
        is not this method's business: it stays ``INTENT`` and keeps blocking as unknowable.
        """

        # A group id this reader cannot even ask about would answer "no members", so the recorded
        # coordinates are required to be a real identity before either read is consulted.
        if type(row["pid"]) is not int or row["pid"] <= 0:
            return False
        if type(row["pgid"]) is not int or row["pgid"] <= 0:
            return False
        if type(row["started_ticks"]) is not int or row["started_ticks"] < 0:
            return False
        if (
            identity_state(row["pid"], row["started_ticks"], row["argv_sha256"])
            != IDENTITY_EXITED
        ):
            return False
        return not group_has_live_descendants(row["pgid"], row["pid"])

    def _check_no_owner_or_fence(
        self, campaign_id: str | None, *, fence: str, active: str, unknown: str
    ) -> None:
        """Refuse when an owner is live or unknowable, or when a recovery fence stands.

        ``campaign_id=None`` asks the host-wide question a *new* run has to answer: this host runs
        one live execution, so an unresolved owner anywhere blocks a new authorization. A named
        campaign asks the narrower question a retry of that campaign asks.

        A ``RUNNING`` row is not live by itself: the state is written once, when the owner is
        acknowledged, and nothing in this store ever writes it back. So the row is reconciled
        against the recorded process first, and only a proven-dead owner stops blocking - a live
        one, an unreadable one and a row in any state this build does not know all still refuse.
        """

        if campaign_id is None:
            fenced = self.has_recovery_fence()
        else:
            fenced = self.recovery_fence(campaign_id) is not None
        if fenced:
            raise StoreConflict(fence)
        if campaign_id is None:
            rows = self._connection.execute(
                "SELECT o.state, o.batch_id FROM owned_execution o "
                "JOIN campaign_batches b USING (batch_id)"
            ).fetchall()
        else:
            rows = self._connection.execute(
                "SELECT o.state, o.batch_id FROM owned_execution o "
                "JOIN campaign_batches b USING (batch_id) WHERE b.campaign_id = ?",
                (campaign_id,),
            ).fetchall()
        for row in rows:
            if row["state"] == "RUNNING":
                if not self.reconcile_exited_execution_owner(row["batch_id"]):
                    raise StoreConflict(active)
                continue
            if row["state"] == "INTENT":
                raise StoreConflict(unknown)
            if row["state"] != self.OWNER_STATE_EXITED:
                # A state this build cannot reason about is not a retired owner.
                raise StoreConflict(active)
        statement = (
            "SELECT i.spawn_token FROM owner_intents i "
            "LEFT JOIN owner_processes p ON p.spawn_token = i.spawn_token "
            "JOIN campaign_batches b ON b.batch_id = i.batch_id "
            "WHERE p.spawn_token IS NULL AND b.cleanup_receipt_sha256 IS NULL"
        )
        parameters: tuple = ()
        if campaign_id is not None:
            statement += " AND i.campaign_id = ?"
            parameters = (campaign_id,)
        unconfirmed = self._connection.execute(
            statement + " LIMIT 1", parameters
        ).fetchone()
        if unconfirmed is not None:
            raise StoreConflict(unknown)

    # -- one-time candidate context issuance ---------------------------------------------------

    #: The one issuance operation this store records in the shared one-time command table.
    CANDIDATE_ISSUANCE_OPERATION = "ISSUE_CANDIDATE_CONTEXT"

    def admit_candidate_context_issuance(
        self,
        *,
        command_id: str,
        request_sha256: str,
        context_id: str,
        campaign_id: str,
        document,
    ) -> None:
        """Consume one issuance command and record the context it minted, or commit nothing.

        The command is the caller's own id: a replay of the same issuance and a reuse of the id for
        a different request are both refused, by name. Nothing is issued while a recovery fence
        stands or an owner is live or unknowable, so a context never authorizes a run the host
        cannot account for. The issued document is durable with the command, so the issuance can be
        audited without trusting a later caller's restatement of it.
        """

        if not isinstance(document, dict):
            raise StoreConflict("CONTEXT_DOCUMENT_INVALID")
        with self._transaction():
            row = self._connection.execute(
                "SELECT request_sha256, operation FROM commands WHERE command_id = ?",
                (command_id,),
            ).fetchone()
            if row is not None:
                if row["operation"] != self.CANDIDATE_ISSUANCE_OPERATION:
                    raise StoreConflict("CONTEXT_COMMAND_ID_REUSED")
                if row["request_sha256"] == request_sha256:
                    raise StoreConflict("CONTEXT_COMMAND_ALREADY_CONSUMED")
                raise StoreConflict("CONTEXT_COMMAND_ID_REUSED")
            self._check_no_owner_or_fence(
                None,
                fence="CONTEXT_RECOVERY_FENCE",
                active="CONTEXT_OWNER_ACTIVE",
                unknown="CONTEXT_OWNER_UNKNOWN",
            )
            self._connection.execute(
                "INSERT INTO commands VALUES (?, ?, ?, 'COMPLETE', ?)",
                (command_id, request_sha256, self.CANDIDATE_ISSUANCE_OPERATION, _json(document)),
            )

    # -- one-time candidate first-pass admission -----------------------------------------------

    #: Every coordinate a first-pass request and its candidate context must agree on.
    _FIRST_PASS_COORDINATES = (
        ("campaign_id", "FIRST_PASS_CAMPAIGN_MISMATCH"),
        ("batch_id", "FIRST_PASS_BATCH_MISMATCH"),
        ("manifest_id", "FIRST_PASS_MANIFEST_MISMATCH"),
        ("execution_profile", "FIRST_PASS_PROFILE_MISMATCH"),
        ("worker_count", "FIRST_PASS_WORKER_COUNT_MISMATCH"),
    )

    def admit_first_pass(
        self,
        *,
        request,
        context,
        receipt: PreflightReceipt,
        campaign: CampaignBinding,
        batch: BatchBinding,
        spawn_intent: OwnerIntent,
    ) -> FirstPassSelectionBinding:
        """Admit exactly one candidate first pass, or commit nothing at all.

        One SQLite transaction consumes the context's one-time command, checks the profile, config,
        runtime closure, evidence root and owner generation the context binds, refuses any existing
        campaign or batch and any standing fence or unresolved owner, consumes the preflight receipt
        and writes the campaign, the batch, the admission row and the owner spawn intent. A refused
        admission rolls everything back, so the command is still usable once the cause is corrected.
        """

        if not isinstance(context, CONTEXT_TYPES):
            raise StoreConflict("FIRST_PASS_CONTEXT_KIND")
        if isinstance(context, ProductionExecutionContext):
            raise StoreConflict("FIRST_PASS_CANDIDATE_CONTEXT_REQUIRED")
        if not isinstance(receipt, PreflightReceipt):
            raise StoreConflict("FIRST_PASS_RECEIPT_REQUIRED")
        if not isinstance(spawn_intent, OwnerIntent):
            raise StoreConflict("FIRST_PASS_SPAWN_INTENT_INVALID")
        now_monotonic_ns = time.monotonic_ns()
        with self._transaction():
            self._check_first_pass_coordinates(request, context, now_monotonic_ns)
            self._consume_first_pass_command(request, context)
            self._check_candidate_first_pass_budget(context)
            self._check_first_pass_fresh(request)
            self._check_no_owner_or_fence(
                None,
                fence="FIRST_PASS_RECOVERY_FENCE",
                active="FIRST_PASS_OWNER_ACTIVE",
                unknown="FIRST_PASS_OWNER_UNKNOWN",
            )
            if (
                receipt.campaign_id != request.campaign_id
                or receipt.manifest_id != request.manifest_id
            ):
                raise StoreConflict("PREFLIGHT_RECEIPT_MISMATCH")
            self._record_preflight_receipt_locked(receipt)
            self._consume_preflight_locked(
                receipt.receipt_id,
                receipt.canonical_start_request_sha256,
                campaign,
                batch,
                now_monotonic_ns=now_monotonic_ns,
            )
            return self._bind_admitted_first_pass(request, context, spawn_intent)

    def _check_first_pass_coordinates(self, request, context, now_monotonic_ns: int) -> None:
        if context.batch_kind != "FIRST_PASS":
            raise StoreConflict("FIRST_PASS_BATCH_KIND")
        for name, code in self._FIRST_PASS_COORDINATES:
            if getattr(request, name) != getattr(context, name):
                raise StoreConflict(code)
        if request.lease_generation != context.owner_generation:
            raise StoreConflict("FIRST_PASS_OWNER_GENERATION_MISMATCH")
        if context.is_expired(now_monotonic_ns):
            raise StoreConflict("FIRST_PASS_CONTEXT_EXPIRED")
        if request.parallel_config_sha256 != context.config_sha256:
            raise StoreConflict("FIRST_PASS_CONFIG_MISMATCH")
        if runtime_closure_sha256(request) != context.runtime_closure_sha256:
            raise StoreConflict("FIRST_PASS_RUNTIME_CLOSURE_MISMATCH")
        if Path(request.evidence_root) != context.evidence_root:
            raise StoreConflict("FIRST_PASS_EVIDENCE_ROOT_MISMATCH")

    def _consume_first_pass_command(self, request, context) -> None:
        digest = _sha({
            "operation": "ADMIT_CANDIDATE_FIRST_PASS",
            "request": canonical_start_request_sha256(request),
            "context": context.as_document(),
        })
        row = self._connection.execute(
            "SELECT request_sha256 FROM commands WHERE command_id = ?", (context.command_id,)
        ).fetchone()
        if row is not None:
            if row["request_sha256"] == digest:
                raise StoreConflict("FIRST_PASS_COMMAND_ALREADY_CONSUMED")
            raise StoreConflict("FIRST_PASS_COMMAND_ID_REUSED")
        self._connection.execute(
            "INSERT INTO commands VALUES (?, ?, 'ADMIT_CANDIDATE_FIRST_PASS', 'IN_PROGRESS', NULL)",
            (context.command_id, digest),
        )

    def _check_candidate_first_pass_budget(self, context) -> None:
        """A candidate dispatch authorizes a bounded number of admitted runs, never more."""

        row = self._connection.execute(
            "SELECT COUNT(*) FROM first_pass_admissions "
            "WHERE context_kind = ? AND context_scope = ?",
            (CANDIDATE_CONTEXT_KIND, context.scope),
        ).fetchone()
        if int(row[0]) >= context.max_runs:
            raise StoreConflict("FIRST_PASS_MAX_RUNS_EXCEEDED")

    def _check_first_pass_fresh(self, request) -> None:
        if self._connection.execute(
            "SELECT 1 FROM campaigns WHERE campaign_id = ?", (request.campaign_id,)
        ).fetchone() is not None:
            raise StoreConflict("FIRST_PASS_CAMPAIGN_EXISTS")
        if self._connection.execute(
            "SELECT 1 FROM campaign_batches WHERE batch_id = ?", (request.batch_id,)
        ).fetchone() is not None:
            raise StoreConflict("FIRST_PASS_BATCH_EXISTS")

    def _bind_admitted_first_pass(
        self, request, context, spawn_intent: OwnerIntent
    ) -> FirstPassSelectionBinding:
        if (
            spawn_intent.campaign_id != request.campaign_id
            or spawn_intent.batch_id != request.batch_id
        ):
            raise StoreConflict("FIRST_PASS_SPAWN_INTENT_MISMATCH")
        if spawn_intent.generation != context.owner_generation:
            raise StoreConflict("FIRST_PASS_OWNER_GENERATION_MISMATCH")
        binding = FirstPassSelectionBinding(
            command_id=context.command_id,
            campaign_id=request.campaign_id,
            batch_id=request.batch_id,
            manifest_id=request.manifest_id,
            execution_profile=context.execution_profile,
            schema_version=context.schema_version,
            batch_kind=context.batch_kind,
            config_sha256=context.config_sha256,
            runtime_closure_sha256=context.runtime_closure_sha256,
            worker_count=context.worker_count,
            evidence_root=context.evidence_root,
            owner_generation=context.owner_generation,
            context_kind=context.kind,
            context_id=context.context_id,
            spawn_token=spawn_intent.spawn_token,
        )
        try:
            self._connection.execute(
                "INSERT INTO first_pass_admissions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?, ?, ?, ?)",
                (
                    context.command_id,
                    request.campaign_id,
                    context.kind,
                    context.context_id,
                    context.scope,
                    request.batch_id,
                    request.manifest_id,
                    context.execution_profile,
                    context.schema_version,
                    context.config_sha256,
                    context.runtime_closure_sha256,
                    context.worker_count,
                    str(context.evidence_root),
                    context.owner_generation,
                    getattr(context, "max_runs", None),
                    spawn_intent.spawn_token,
                    _json(binding.as_document()),
                    binding.binding_sha256,
                    time.time_ns(),
                ),
            )
            self._connection.execute(
                "INSERT INTO owner_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    spawn_intent.spawn_token,
                    spawn_intent.campaign_id,
                    spawn_intent.batch_id,
                    spawn_intent.role,
                    spawn_intent.generation,
                    spawn_intent.parent_spawn_token,
                    spawn_intent.expected_executable,
                    spawn_intent.argv_sha256,
                    1 if spawn_intent.own_session else 0,
                    spawn_intent.created_at_ns,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise StoreConflict("FIRST_PASS_OWNER_INTENT_CONFLICT") from error
        return binding

    def first_pass_admission(self, command_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM first_pass_admissions WHERE command_id = ?", (command_id,)
        ).fetchone()
        return None if row is None else dict(row)

    def first_pass_admissions(self, campaign_id: str) -> tuple[dict, ...]:
        return tuple(
            dict(row)
            for row in self._connection.execute(
                "SELECT * FROM first_pass_admissions WHERE campaign_id = ? "
                "ORDER BY created_at_ns, command_id",
                (campaign_id,),
            )
        )

    def _bind_admitted_retry(
        self, request, context, spawn_intent: OwnerIntent
    ) -> RetrySelectionBinding:
        if (
            spawn_intent.campaign_id != request.campaign_id
            or spawn_intent.batch_id != request.batch_id
        ):
            raise StoreConflict("RETRY_SPAWN_INTENT_MISMATCH")
        if spawn_intent.generation != request.owner_generation:
            raise StoreConflict("RETRY_OWNER_GENERATION_MISMATCH")
        binding = RetrySelectionBinding(
            command_id=request.command_id,
            campaign_id=request.campaign_id,
            batch_id=request.batch_id,
            point_id=request.point_id,
            original_batch_id=request.original_batch_id,
            original_catalog_sha256=request.original_catalog_sha256,
            original_selection_sha256=request.original_selection_sha256,
            original_result_sha256=request.original_result_sha256,
            original_outcome="FAILED",
            execution_profile=request.execution_profile,
            schema_version=request.schema_version,
            config_sha256=request.config_sha256,
            runtime_closure_sha256=request.runtime_closure_sha256,
            worker_count=request.worker_count,
            evidence_root=request.evidence_root,
            owner_generation=request.owner_generation,
            context_kind=context.kind,
            spawn_token=spawn_intent.spawn_token,
            lease_id=getattr(context, "lease_id", None),
            lease_generation=getattr(context, "lease_generation", None),
        )
        queue = self._connection.execute(
            "SELECT ordinal FROM retry_queue WHERE campaign_id = ? AND point_id = ? "
            "AND state = 'QUEUED' ORDER BY ordinal LIMIT 1",
            (request.campaign_id, request.point_id),
        ).fetchone()
        if queue is None:
            raise StoreConflict("RETRY_NOT_QUEUED")
        try:
            self._insert_batch(BatchBinding(
                batch_id=request.batch_id,
                campaign_id=request.campaign_id,
                batch_kind=RETRY_BATCH_KIND,
                point_id=request.point_id,
                journal_root=retry_batch_root(
                    request.evidence_root, request.campaign_id, request.batch_id),
                coordinator_epoch=request.owner_generation,
            ))
            self._connection.execute(
                "UPDATE retry_queue SET state = 'RUNNING', batch_id = ? "
                "WHERE campaign_id = ? AND ordinal = ?",
                (request.batch_id, request.campaign_id, queue["ordinal"]),
            )
            self._connection.execute(
                "INSERT INTO retry_admissions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, "
                "?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    request.command_id,
                    request.campaign_id,
                    context.kind,
                    context.context_id,
                    context.scope,
                    request.batch_id,
                    request.point_id,
                    request.original_batch_id,
                    request.original_result_sha256,
                    request.execution_profile,
                    request.schema_version,
                    request.config_sha256,
                    request.runtime_closure_sha256,
                    request.worker_count,
                    str(request.evidence_root),
                    getattr(context, "lease_id", None),
                    getattr(context, "lease_generation", None),
                    request.owner_generation,
                    getattr(context, "max_runs", None),
                    spawn_intent.spawn_token,
                    _json(binding.as_document()),
                    binding.binding_sha256,
                    time.time_ns(),
                ),
            )
            self._connection.execute(
                "INSERT INTO owner_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    spawn_intent.spawn_token,
                    spawn_intent.campaign_id,
                    spawn_intent.batch_id,
                    spawn_intent.role,
                    spawn_intent.generation,
                    spawn_intent.parent_spawn_token,
                    spawn_intent.expected_executable,
                    spawn_intent.argv_sha256,
                    1 if spawn_intent.own_session else 0,
                    spawn_intent.created_at_ns,
                ),
            )
        except sqlite3.IntegrityError as error:
            raise StoreConflict("RETRY_OWNER_INTENT_CONFLICT") from error
        return binding

    def retry_admission(self, command_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM retry_admissions WHERE command_id = ?", (command_id,)
        ).fetchone()
        return None if row is None else dict(row)

    def retry_admissions(self, campaign_id: str) -> tuple[dict, ...]:
        return tuple(
            dict(row)
            for row in self._connection.execute(
                "SELECT * FROM retry_admissions WHERE campaign_id = ? "
                "ORDER BY created_at_ns, command_id",
                (campaign_id,),
            )
        )

    def preflight_receipt(self, receipt_id: str) -> dict | None:
        """One durable receipt document, exactly as it was recorded."""

        row = self._connection.execute(
            "SELECT * FROM preflight_receipts WHERE receipt_id = ?", (receipt_id,)
        ).fetchone()
        return None if row is None else dict(row)

    def campaign_preflight_receipt(self, campaign_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM preflight_receipts WHERE campaign_id = ?", (campaign_id,)
        ).fetchone()
        return None if row is None else dict(row)

    def record_execution_owner_intent(self, intent) -> str:
        binding = intent.control_binding if isinstance(intent, CoordinatorStartRequest) else None
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
                # The durable fingerprint is the requested command line without its launcher: the
                # kernel may rewrite argv[0] when an interpreter re-execs itself.
                argv_sha256=command_fingerprint(request.argv),
                environment_sha256=_sha(dict(request.environment)),
                source_commit="UNKNOWN",
                install_prefix=Path(executable).parent,
                runtime_sha256=runtime_digest,
                control_socket=getattr(request, "control_socket", None),
            )
        with self._transaction():
            if binding is not None:
                self._validate_fixed_binding(binding)
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
                        # Debug metadata column: a no-Git deployment records UNKNOWN
                        # rather than a fabricated commit, and never refuses.
                        intent.source_commit or "UNKNOWN",
                        str(intent.install_prefix),
                        intent.runtime_sha256,
                        str(intent.control_socket) if intent.control_socket else None,
                    ),
                )
                if binding is not None:
                    self._connection.execute(
                        "INSERT INTO fixed_control_bindings VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (binding.batch_id, binding.campaign_id, str(binding.batch_root),
                         str(binding.control_socket), binding.coordinator_epoch,
                         binding.control_token, binding.control_token_sha256),
                    )
            except sqlite3.IntegrityError as error:
                raise StoreConflict("EXECUTION_OWNER_INTENT_CONFLICT") from error
        return intent.spawn_token


    # -- persistent owner tree: intent before spawn, confirmation after readback ---------------

    def record_owner_intent(self, intent: OwnerIntent) -> OwnerIntent:
        """Persist one spawn intent before its real spawn.

        The intent table is the only thing a recovery may trust about a spawn that never
        confirmed: it must therefore exist *before* ``Popen``, and a duplicate token may never be
        overwritten by a different intent.
        """
        if not isinstance(intent, OwnerIntent):
            raise StoreConflict("OWNER_INTENT_INVALID")
        with self._transaction():
            try:
                self._connection.execute(
                    "INSERT INTO owner_intents VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        intent.spawn_token,
                        intent.campaign_id,
                        intent.batch_id,
                        intent.role,
                        intent.generation,
                        intent.parent_spawn_token,
                        intent.expected_executable,
                        intent.argv_sha256,
                        1 if intent.own_session else 0,
                        intent.created_at_ns,
                    ),
                )
            except sqlite3.IntegrityError as error:
                try:
                    existing = self.owner_intent(intent.spawn_token)
                except Exception:
                    existing = None
                if existing != intent:
                    raise StoreConflict("OWNER_INTENT_CONFLICT") from error
        return intent

    def owner_intent(self, spawn_token: str) -> OwnerIntent | None:
        row = self._connection.execute(
            "SELECT * FROM owner_intents WHERE spawn_token=?", (spawn_token,)
        ).fetchone()
        return None if row is None else _owner_intent_from_row(row)

    def confirm_owner_process(self, confirmed: ConfirmedOwnerProcess) -> ConfirmedOwnerProcess:
        """Persist the readback identity of a spawned process.

        Confirmation is only accepted for an intent that is already durable: an unconfirmed spawn
        is exactly the case recovery must refuse to guess about.
        """
        if not isinstance(confirmed, ConfirmedOwnerProcess):
            raise StoreConflict("OWNER_CONFIRMATION_INVALID")
        with self._transaction():
            if self.owner_intent(confirmed.spawn_token) is None:
                raise StoreConflict("OWNER_INTENT_MISSING")
            try:
                self._connection.execute(
                    "INSERT INTO owner_processes VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        confirmed.spawn_token,
                        confirmed.pid,
                        confirmed.pgid,
                        confirmed.started_ticks,
                        confirmed.command_sha256,
                        confirmed.confirmed_at_ns,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise StoreConflict("OWNER_CONFIRMATION_CONFLICT") from error
        return confirmed

    def owner_tree(
        self, campaign_id: str, batch_id: str, generation: int | None = None
    ) -> tuple[OwnerRecord, ...]:
        """Every durable intent of one campaign/batch, oldest first, with its confirmation."""
        query = (
            "SELECT i.*, p.pid AS confirmed_pid, p.pgid AS confirmed_pgid, "
            "p.started_ticks AS confirmed_started_ticks, "
            "p.command_sha256 AS confirmed_command_sha256, "
            "p.confirmed_at_ns AS confirmed_at_ns "
            "FROM owner_intents i LEFT JOIN owner_processes p "
            "ON p.spawn_token = i.spawn_token "
            "WHERE i.campaign_id=? AND i.batch_id=?"
        )
        parameters: list[object] = [campaign_id, batch_id]
        if generation is not None:
            query += " AND i.generation=?"
            parameters.append(generation)
        query += " ORDER BY i.created_at_ns, i.spawn_token"
        records = []
        for row in self._connection.execute(query, tuple(parameters)):
            intent = _owner_intent_from_row(row)
            if row["confirmed_pid"] is None:
                records.append(OwnerRecord(intent=intent, confirmed=None))
                continue
            records.append(
                OwnerRecord(
                    intent=intent,
                    confirmed=ConfirmedOwnerProcess(
                        spawn_token=intent.spawn_token,
                        pid=row["confirmed_pid"],
                        pgid=row["confirmed_pgid"],
                        started_ticks=row["confirmed_started_ticks"],
                        command_sha256=row["confirmed_command_sha256"],
                        confirmed_at_ns=row["confirmed_at_ns"],
                    ),
                )
            )
        return tuple(records)

    def owner_cleanup_receipt(
        self, campaign_id: str, batch_id: str, generation: int
    ) -> dict | None:
        row = self._connection.execute(
            "SELECT receipt_json, receipt_sha256 FROM owner_cleanup_receipts "
            "WHERE campaign_id=? AND batch_id=? AND generation=?",
            (campaign_id, batch_id, generation),
        ).fetchone()
        return None if row is None else dict(json.loads(row["receipt_json"]))

    def record_owner_cleanup_receipt(self, receipt) -> None:
        """Index a fsynced leaf-first cleanup receipt. A generation is committed once."""
        document = receipt.as_document()
        with self._transaction():
            try:
                self._connection.execute(
                    "INSERT INTO owner_cleanup_receipts VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        receipt.campaign_id,
                        receipt.batch_id,
                        receipt.generation,
                        receipt.receipt_sha256,
                        json.dumps(document, sort_keys=True, separators=(",", ":")),
                        time.time_ns(),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise StoreConflict("OWNER_RECEIPT_CONFLICT") from error

    def _validate_fixed_binding(self, binding: CoordinatorBinding) -> None:
        batch = self.batch(binding.batch_id)
        if (
            batch is None or batch.campaign_id != binding.campaign_id
            or batch.journal_root != binding.batch_root
            or batch.coordinator_epoch != binding.coordinator_epoch
        ):
            raise StoreConflict("FIXED_CONTROL_BATCH_BINDING_MISMATCH")

    def fixed_control_binding(self, batch_id: str) -> CoordinatorBinding | None:
        row = self._connection.execute(
            "SELECT * FROM fixed_control_bindings WHERE batch_id=?", (batch_id,)
        ).fetchone()
        if row is None:
            return None
        binding = CoordinatorBinding(
            row["campaign_id"], row["batch_id"], Path(row["batch_root"]),
            Path(row["control_socket"]), row["coordinator_epoch"],
            row["control_token"], row["control_token_sha256"],
        )
        self._validate_fixed_binding(binding)
        return binding

    def record_recovery_fence(
        self,
        campaign_id: str,
        batch_id: str,
        *,
        reason: str,
        command_id: str,
        generation: int | None = None,
    ) -> None:
        """Record one campaign-scoped fence, optionally for an exact owner-tree generation.

        The row is campaign-scoped and its reason already names the generation the reaper
        concluded, so ``generation`` is validated for interface parity with the directory sink and
        deliberately not stored; every caller that predates it is unchanged.
        """
        if generation is not None and (
            type(generation) is not int or isinstance(generation, bool) or generation < 1
        ):
            raise StoreConflict("RECOVERY_FENCE_GENERATION_INVALID")
        with self._transaction():
            batch = self.batch(batch_id)
            if batch is None or batch.campaign_id != campaign_id:
                raise StoreConflict("RECOVERY_FENCE_BATCH_MISMATCH")
            self._connection.execute(
                "INSERT OR IGNORE INTO recovery_fences VALUES (?, ?, ?, ?, ?)",
                (campaign_id, batch_id, reason, command_id, time.time_ns()),
            )

    def recovery_fence(self, campaign_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM recovery_fences WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        return dict(row) if row is not None else None

    def has_recovery_fence(self) -> bool:
        for row in self._connection.execute("SELECT campaign_id FROM recovery_fences"):
            try:
                if self.operator_recovery(row["campaign_id"]) is None:
                    return True
            except StoreConflict:
                return True
        return False

    def operator_recovery_context(self, campaign_id: str) -> dict:
        """Return historical binding facts, never control credentials or success claims."""
        campaign = self._connection.execute(
            "SELECT * FROM campaigns WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        fence = self.recovery_fence(campaign_id)
        if campaign is None or fence is None:
            raise StoreConflict("RECOVERY_FENCE_NOT_FOUND")
        batches = [dict(row) for row in self._connection.execute(
            "SELECT * FROM campaign_batches WHERE campaign_id=? ORDER BY batch_id", (campaign_id,)
        )]
        owners = [dict(row) for row in self._connection.execute(
            "SELECT o.* FROM owned_execution o JOIN campaign_batches b USING(batch_id) "
            "WHERE b.campaign_id=? ORDER BY o.batch_id", (campaign_id,)
        )]
        receipt = self._connection.execute(
            "SELECT receipt_json,receipt_sha256 FROM preflight_receipts WHERE receipt_id=?",
            (campaign["preflight_receipt_id"],),
        ).fetchone()
        if receipt is None:
            raise StoreConflict("RECOVERY_PREFLIGHT_NOT_FOUND")
        document = json.loads(receipt["receipt_json"])
        if _sha(document) != receipt["receipt_sha256"]:
            raise StoreConflict("RECOVERY_PREFLIGHT_INVALID")
        binding = {"campaign": dict(campaign), "batches": batches, "owners": owners,
                   "preflight_receipt_sha256": receipt["receipt_sha256"]}
        return {**binding, "fence": fence, "fence_sha256": _sha(fence),
                "binding_sha256": _sha(binding), "preflight": document}

    def _check_operator_receipt(self, campaign_id: str, receipt: dict) -> None:
        context = self.operator_recovery_context(campaign_id)
        if (
            receipt.get("campaign_id") != campaign_id
            or receipt.get("fence_sha256") != context["fence_sha256"]
            or receipt.get("binding_sha256") != context["binding_sha256"]
            or receipt.get("status") != "OPERATOR_RECOVERED_ABORTED"
            or receipt.get("execution_success") is not False
            or receipt.get("upstream_cleanup_claimed") is not False
        ):
            raise StoreConflict("RECOVERY_RECEIPT_INVALID")
        for prefix in ("report", "backup", "config"):
            path = Path(receipt[f"{prefix}_path"])
            if (
                not path.is_absolute() or path != path.resolve(strict=True)
                or not path.is_relative_to(self.root / "operator-recovery")
            ):
                raise StoreConflict("RECOVERY_EVIDENCE_INVALID")
            metadata = path.stat(follow_symlinks=False)
            if (
                not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid()
                or metadata.st_nlink != 1 or stat.S_IMODE(metadata.st_mode) != 0o600
                or hashlib.sha256(path.read_bytes()).hexdigest() != receipt[f"{prefix}_sha256"]
            ):
                raise StoreConflict("RECOVERY_EVIDENCE_INVALID")
        report = json.loads(Path(receipt["report_path"]).read_bytes())
        for key in ("campaign_id", "command_id", "fence_sha256", "binding_sha256"):
            if report.get(key) != receipt.get(key):
                raise StoreConflict("RECOVERY_REPORT_INVALID")
        if receipt["config_sha256"] != context["preflight"].get("parallel_config_sha256"):
            raise StoreConflict("RECOVERY_CONFIG_MISMATCH")

    def operator_recovery(self, campaign_id: str) -> dict | None:
        row = self._connection.execute(
            "SELECT * FROM operator_recoveries WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        if row is None:
            return None
        try:
            receipt = json.loads(row["receipt_json"])
            if _sha(receipt) != row["receipt_sha256"] or receipt.get("command_id") != row["command_id"]:
                raise StoreConflict("RECOVERY_RECEIPT_INVALID")
            self._check_operator_receipt(campaign_id, receipt)
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise StoreConflict("RECOVERY_RECEIPT_INVALID") from error
        return receipt

    def record_operator_recovery(self, receipt: dict) -> dict:
        """Commit only an audited abort resolution; original fence/history stays intact."""
        campaign_id = receipt["campaign_id"]
        request = {key: receipt[key] for key in (
            "campaign_id", "command_id", "fence_sha256", "binding_sha256", "config_sha256",
        )}
        digest = _sha(request)
        with self._transaction():
            self._check_operator_receipt(campaign_id, receipt)
            if self._connection.execute(
                "SELECT 1 FROM commands WHERE command_id=?", (receipt["command_id"],)
            ).fetchone() is not None:
                raise StoreConflict("COMMAND_ID_REUSED")
            if self.operator_recovery(campaign_id) is not None:
                raise StoreConflict("RECOVERY_ALREADY_RESOLVED")
            self._connection.execute("INSERT INTO operator_recoveries VALUES (?, ?, ?, ?)",
                                     (campaign_id, receipt["command_id"], _json(receipt), _sha(receipt)))
            self._connection.execute("INSERT INTO commands VALUES (?, ?, ?, ?, ?)",
                                     (receipt["command_id"], digest, "OPERATOR_RECOVERY", "COMPLETE", _json(receipt)))
        return receipt

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
            binding = self.fixed_control_binding(batch_id)
            if binding is not None and (
                values.get("coordinator_epoch") != binding.coordinator_epoch
                or type(values.get("coordinator_epoch")) is not int
            ):
                raise StoreConflict("FIXED_CONTROL_OWNER_ACK_MISMATCH")
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
            self._accept_cursor_locked(cursor)

    def _accept_cursor_locked(self, cursor: UpstreamCursor) -> None:
        if True:
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

    def accept_projection_batch(
        self,
        *,
        batch_id: str,
        expected_cursor: UpstreamCursor | None,
        events,
        next_cursor: UpstreamCursor | None,
        reducer,
    ):
        """Apply verified events, their attempts and the accepted cursor in one transaction.

        Every step - idempotency, reducer state, attempt dedupe and cursor - commits or rolls
        back together, so a failure after the reducer cannot leave a state that the cursor does
        not describe. Replaying an already accepted event is idempotent and never counts an
        attempt twice.
        """

        from .reducer import CampaignReducerState

        with self._transaction():
            row = self._connection.execute(
                "SELECT * FROM projection_state WHERE batch_id = ?", (batch_id,)
            ).fetchone()
            stored_cursor = (
                None
                if row is None
                else UpstreamCursor(
                    batch_id=batch_id,
                    owner_kind="COORDINATOR",
                    owner_epoch_or_generation=row["owner_epoch_or_generation"],
                    segment_id=row["segment_id"],
                    event_id=row["event_id"],
                    frame_sha256=row["frame_sha256"],
                )
            )
            if expected_cursor != stored_cursor:
                raise StoreConflict("PROJECTION_CURSOR_MISMATCH")
            state = (
                None
                if row is None
                else CampaignReducerState.from_document(json.loads(row["state_json"]))
            )
            for event in events:
                if getattr(event, "batch_id", batch_id) != batch_id:
                    raise StoreConflict("PROJECTION_BATCH_MISMATCH")
                seen = self._connection.execute(
                    "SELECT 1 FROM projection_events WHERE batch_id = ? AND sequence = ? "
                    "AND frame_sha256 = ?",
                    (batch_id, event.sequence, event.frame_sha256),
                ).fetchone()
                if seen is not None:
                    continue
                payload = event.payload if isinstance(event.payload, dict) else {}
                attempt_id = getattr(event, "attempt_id", None) or payload.get("attempt_id")
                point_id = getattr(event, "point_id", None) or payload.get("point_id")
                if attempt_id is not None:
                    recorded = self._connection.execute(
                        "SELECT point_id FROM projection_attempts WHERE batch_id = ? "
                        "AND attempt_id = ?",
                        (batch_id, attempt_id),
                    ).fetchone()
                    if recorded is None:
                        self._connection.execute(
                            "INSERT INTO projection_attempts VALUES (?, ?, ?)",
                            (batch_id, attempt_id, point_id),
                        )
                    elif (
                        point_id is not None
                        and recorded["point_id"] is not None
                        and recorded["point_id"] != point_id
                    ):
                        # One attempt id may span lease/start/result events of the same point,
                        # but it can never be reused for a different point.
                        raise StoreConflict("PROJECTION_ATTEMPT_DUPLICATE")
                state = reducer.apply(state, event)
                self._connection.execute(
                    "INSERT INTO projection_events VALUES (?, ?, ?, ?)",
                    (batch_id, event.sequence, event.frame_sha256, attempt_id),
                )
            if next_cursor is not None:
                payload = json.dumps(state.as_document(), sort_keys=True) if state else "{}"
                if row is None:
                    self._connection.execute(
                        "INSERT INTO projection_state VALUES (?, ?, ?, ?, ?, ?)",
                        (batch_id, payload, next_cursor.owner_epoch_or_generation,
                         next_cursor.segment_id, next_cursor.event_id, next_cursor.frame_sha256),
                    )
                else:
                    self._connection.execute(
                        "UPDATE projection_state SET state_json = ?, owner_epoch_or_generation = ?,"
                        " segment_id = ?, event_id = ?, frame_sha256 = ? WHERE batch_id = ?",
                        (payload, next_cursor.owner_epoch_or_generation, next_cursor.segment_id,
                         next_cursor.event_id, next_cursor.frame_sha256, batch_id),
                    )
                self._accept_cursor_locked(next_cursor)
            return state

    def read_projection_state(self, batch_id: str):
        """Return the persisted reducer state and accepted cursor for one batch."""

        from .reducer import CampaignReducerState

        row = self._connection.execute(
            "SELECT * FROM projection_state WHERE batch_id = ?", (batch_id,)
        ).fetchone()
        if row is None:
            return ProjectionSnapshot(None, None)
        return ProjectionSnapshot(
            CampaignReducerState.from_document(json.loads(row["state_json"])),
            UpstreamCursor(
                batch_id=batch_id,
                owner_kind="COORDINATOR",
                owner_epoch_or_generation=row["owner_epoch_or_generation"],
                segment_id=row["segment_id"],
                event_id=row["event_id"],
                frame_sha256=row["frame_sha256"],
            ),
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

    def retry_items(self, campaign_id: str) -> tuple[RetryItem, ...]:
        return tuple(
            RetryItem(
                campaign_id=row["campaign_id"], ordinal=row["ordinal"],
                point_id=row["point_id"], state=row["state"], batch_id=row["batch_id"],
            )
            for row in self._connection.execute(
                "SELECT * FROM retry_queue WHERE campaign_id = ? ORDER BY ordinal",
                (campaign_id,),
            )
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
        """Commit the one cleanup receipt a batch's own verified bytes prove.

        Recording the same receipt again is idempotent; a *different* receipt is refused rather than
        written over. The column is the durable fact a retry admission checks for its original, so a
        later caller with other bytes may not replace what was already verified and committed.
        """

        if (
            not isinstance(receipt_sha256, str)
            or len(receipt_sha256) != 64
            or any(character not in "0123456789abcdef" for character in receipt_sha256)
        ):
            raise StoreConflict("BATCH_CLEANUP_RECEIPT_INVALID")
        with self._transaction():
            row = self._connection.execute(
                "SELECT cleanup_receipt_sha256 FROM campaign_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if row is None:
                raise StoreConflict("BATCH_NOT_FOUND")
            if row["cleanup_receipt_sha256"] not in (None, receipt_sha256):
                raise StoreConflict("BATCH_CLEANUP_RECEIPT_CONFLICT")
            self._connection.execute(
                "UPDATE campaign_batches SET state='CLEANED', cleanup_receipt_sha256=? "
                "WHERE batch_id=?",
                (receipt_sha256, batch_id),
            )

    def list_campaigns(self) -> tuple[dict, ...]:
        return tuple(
            dict(row)
            for row in self._connection.execute(
                "SELECT campaign_id, state, execution_mode FROM campaigns ORDER BY campaign_id"
            )
        )

    def campaign_records(self) -> tuple[dict, ...]:
        return tuple(
            dict(row)
            for row in self._connection.execute("SELECT * FROM campaigns ORDER BY campaign_id")
        )

    def campaign_batches(self, campaign_id: str) -> tuple[BatchBinding, ...]:
        return tuple(
            self.batch(row["batch_id"])
            for row in self._connection.execute(
                "SELECT batch_id FROM campaign_batches WHERE campaign_id=? ORDER BY batch_id",
                (campaign_id,),
            )
        )

    def owned_executions(self, states: tuple[str, ...]) -> tuple[OwnedExecutionRecord, ...]:
        marks = ",".join("?" for _ in states)
        return tuple(
            self.owned_execution(row["batch_id"])
            for row in self._connection.execute(
                f"SELECT batch_id FROM owned_execution WHERE state IN ({marks}) ORDER BY batch_id",
                states,
            )
        )

    def invalidate_active_leases(self) -> int:
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE leases SET state='RESTART_INVALIDATED' WHERE state='ACTIVE'"
            )
            return cursor.rowcount

    def next_lease_generation(self) -> int:
        row = self._connection.execute(
            "SELECT COALESCE(MAX(generation), 0) + 1 FROM leases"
        ).fetchone()
        return int(row[0])

    def insert_lease(
        self, lease_id: str, service_session_id: str, generation: int, expires_ns: int
    ) -> None:
        with self._transaction():
            active = self._connection.execute(
                "SELECT lease_id FROM leases WHERE state='ACTIVE'"
            ).fetchone()
            if active is not None:
                raise StoreConflict("LEASE_ALREADY_HELD")
            self._connection.execute(
                "INSERT INTO leases VALUES (?, ?, ?, ?, 'ACTIVE')",
                (lease_id, service_session_id, generation, expires_ns),
            )

    def current_lease(self):
        return self._connection.execute(
            "SELECT * FROM leases WHERE state='ACTIVE' ORDER BY generation DESC LIMIT 1"
        ).fetchone()

    def renew_lease(
        self,
        lease_id: str,
        service_session_id: str,
        generation: int,
        new_generation: int,
        expires_ns: int,
    ) -> None:
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE leases SET generation=?, expires_monotonic_ns=? "
                "WHERE lease_id=? AND service_session_id=? AND generation=? AND state='ACTIVE'",
                (new_generation, expires_ns, lease_id, service_session_id, generation),
            )
            if cursor.rowcount != 1:
                raise StoreConflict("STALE_LEASE_GENERATION")

    def set_lease_state(
        self, lease_id: str, generation: int, state: str
    ) -> None:
        with self._transaction():
            cursor = self._connection.execute(
                "UPDATE leases SET state=? WHERE lease_id=? AND generation=? AND state='ACTIVE'",
                (state, lease_id, generation),
            )
            if cursor.rowcount != 1:
                raise StoreConflict("LEASE_NOT_ACTIVE")

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
