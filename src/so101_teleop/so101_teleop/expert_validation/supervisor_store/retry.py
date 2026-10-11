"""Retry admission, binding and queue operations."""

from __future__ import annotations

import json
import sqlite3
import time

from so101_teleop.expert_validation.execution_context import (
    CANDIDATE_CONTEXT_KIND,
    CONTEXT_TYPES,
    LINUX_RETRY_PROFILE,
    LINUX_RETRY_SCHEMA_VERSION,
    PRODUCTION_CONTEXT_KIND,
    RETRY_BATCH_KIND,
    RETRY_PROFILE,
    RETRY_SCHEMA_VERSION,
    RETRY_WORKER_COUNT,
    CandidateExecutionContext,
    ProductionExecutionContext,
    install_binding_sha256,
    retry_batch_root,
)
from so101_teleop.expert_validation.models import (
    BatchBinding,
    CleanupReceipt,
    RetryItem,
    RetrySelectionBinding,
    RetryStartRequest,
)
from so101_teleop.expert_validation.owner_tree import (
    OwnerIntent,
)
from so101_teleop.expert_validation.supervisor_store.schema import StoreConflict, _json, _sha


class StoreRetry:
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
            (request.execution_profile, request.schema_version) not in {
                (RETRY_PROFILE, RETRY_SCHEMA_VERSION),
                (LINUX_RETRY_PROFILE, LINUX_RETRY_SCHEMA_VERSION),
            }
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

    def enqueue_retries(self, campaign_id: str, point_ids) -> None:
        points = tuple(point_ids)
        if len(points) != len(set(points)):
            raise StoreConflict("RETRY_POINT_DUPLICATE")
        with self._transaction():
            existing = self._connection.execute(
                "SELECT point_id FROM retry_queue WHERE campaign_id = ?", (campaign_id,)
            ).fetchall()
            if set(points).intersection(row["point_id"] for row in existing):
                raise StoreConflict("RETRY_POINT_DUPLICATE")
            first_ordinal = len(existing)
            for offset, point_id in enumerate(points):
                self._connection.execute(
                    "INSERT INTO retry_queue VALUES (?, ?, ?, 'QUEUED', NULL, NULL)",
                    (campaign_id, first_ordinal + offset, point_id),
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
