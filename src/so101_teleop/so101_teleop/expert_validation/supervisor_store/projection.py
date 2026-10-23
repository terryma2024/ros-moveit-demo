"""Upstream cursors, projection batches, batch cleanup and campaign records."""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from so101_teleop.expert_validation.models import (
    BatchBinding,
    UpstreamCursor,
)
from so101_teleop.expert_validation.supervisor_store.schema import (
    ProjectionSnapshot,
    StoreConflict,
)


class StoreProjection:
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

        from so101_teleop.expert_validation.reducer import CampaignReducerState

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

        from so101_teleop.expert_validation.reducer import CampaignReducerState

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
