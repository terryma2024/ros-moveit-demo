"""Candidate context issuance and first pass admission."""

from __future__ import annotations

from pathlib import Path
import sqlite3
import time

from so101_teleop.expert_validation.execution_context import (
    CANDIDATE_CONTEXT_KIND,
    CONTEXT_TYPES,
    ProductionExecutionContext,
    runtime_closure_sha256,
)
from so101_teleop.expert_validation.models import (
    BatchBinding,
    CampaignBinding,
    FirstPassSelectionBinding,
    PreflightReceipt,
)
from so101_teleop.expert_validation.owner_tree import (
    OwnerIntent,
)
from so101_teleop.expert_validation.preflight import canonical_start_request_sha256
from so101_teleop.expert_validation.supervisor_store.schema import StoreConflict, _json, _sha


class StoreFirstPass:
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
