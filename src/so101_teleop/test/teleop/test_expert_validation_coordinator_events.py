from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_teleop.expert_validation.coordinator_events import (
    AcceptedCoordinatorCursor,
    CampaignUpstreamBinding,
    CoordinatorEventReader,
    CoordinatorProjectionError,
)


def binding(journal: CoordinatorJournal, root: Path) -> CampaignUpstreamBinding:
    return CampaignUpstreamBinding(
        campaign_id="campaign-a",
        batch_id="batch-a",
        owner_kind="COORDINATOR",
        owner_epoch_or_generation=journal.coordinator_epoch,
        journal_root=journal.root,
        batch_root=root,
    )


def test_reader_accepts_only_bound_batch_and_contiguous_chain(tmp_path: Path) -> None:
    with CoordinatorJournal.create(tmp_path / "journal", "batch-a") as journal:
        journal.append("BATCH_STARTED", "start", {"delta": {"points": {}}})
        journal.append("LEASE_GRANTED", "lease", {"delta": {}})
        journal.append("ATTEMPT_STARTED", "attempt", {"delta": {}})
        upstream = binding(journal, tmp_path)
        reader = CoordinatorEventReader(journal, upstream)

        batch = reader.read_after(AcceptedCoordinatorCursor.initial(upstream))

        assert [event.type for event in batch.events] == [
            "BATCH_STARTED",
            "LEASE_GRANTED",
            "ATTEMPT_STARTED",
        ]
        assert all(event.batch_id == upstream.batch_id for event in batch.events)
        assert batch.next_cursor.frame_sha256 == batch.events[-1].frame_sha256
        assert batch.next_cursor.sequence == 3


def test_result_is_not_visible_before_coordinator_commit(tmp_path: Path) -> None:
    sealed = tmp_path / "sealed" / "result.json"
    sealed.parent.mkdir()
    sealed.write_text('{"status":"PASSED"}', encoding="utf-8")
    digest = hashlib.sha256(sealed.read_bytes()).hexdigest()
    verified: list[Path] = []

    def verify(reference, _binding) -> None:
        path = Path(reference["location"])
        assert hashlib.sha256(path.read_bytes()).hexdigest() == reference["sha256"]
        verified.append(path)

    with CoordinatorJournal.create(tmp_path / "journal", "batch-a") as journal:
        upstream = binding(journal, tmp_path)
        reader = CoordinatorEventReader(journal, upstream, manifest_verifier=verify)
        journal.append(
            "BATCH_STARTED",
            "start",
            {"delta": {"points": {"task_start": {"status": "UNRUN"}}}},
        )

        assert reader.read_after(reader.initial_cursor).projected_point_states == {
            "task_start": "UNRUN"
        }
        assert verified == []

        journal.append(
            "RESULT_COMMITTED",
            "result-p01",
            {
                "delta": {"points": {"task_start": {"status": "PASSED"}}},
                "identity": {"point_id": "task_start"},
                "response": {"location": str(sealed), "sha256": digest},
            },
        )

        assert reader.read_after(reader.initial_cursor).projected_point_states == {
            "task_start": "PASSED"
        }
        assert verified == [sealed]


def test_cursor_or_binding_mismatch_fails_closed(tmp_path: Path) -> None:
    with CoordinatorJournal.create(tmp_path / "journal", "batch-a") as journal:
        upstream = binding(journal, tmp_path)
        reader = CoordinatorEventReader(journal, upstream)
        journal.append("BATCH_STARTED", "start", {"delta": {"points": {}}})
        cursor = reader.read_after(reader.initial_cursor).next_cursor

        with pytest.raises(CoordinatorProjectionError, match="CURSOR_BATCH_MISMATCH"):
            reader.read_after(
                AcceptedCoordinatorCursor(
                    "other", cursor.owner_epoch_or_generation, cursor.sequence,
                    cursor.frame_sha256,
                )
            )
        with pytest.raises(CoordinatorProjectionError, match="JOURNAL_ROOT_MISMATCH"):
            CoordinatorEventReader(
                journal,
                CampaignUpstreamBinding(
                    "campaign-a",
                    "batch-a",
                    "COORDINATOR",
                    journal.coordinator_epoch,
                    tmp_path / "other",
                    tmp_path,
                ),
            )
