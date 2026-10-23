"""Command bookkeeping, manifests and the preflight receipt bound to a campaign batch."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time

from so101_teleop.expert_validation.models import (
    BatchBinding,
    CampaignBinding,
    PreflightReceipt,
    ValidationManifest,
)
from so101_teleop.expert_validation.supervisor_store.schema import (
    CommandOutcomeUnknown,
    StoreConflict,
    _json,
)


class StoreCommands:
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
