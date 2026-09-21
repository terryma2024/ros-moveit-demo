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


def test_reader_verifies_real_sealed_directory_manifest_and_merges_deltas(
    tmp_path: Path,
) -> None:
    sealed = tmp_path / "workers/worker-01/attempts/task_start/lease-1/sealed"
    sealed.mkdir(parents=True)
    manifest = sealed / "attempt_result_manifest.json"
    manifest.write_text('{"schema_version":1}', encoding="utf-8")
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()

    with CoordinatorJournal.create(tmp_path / "journal", "batch-a") as journal:
        upstream = binding(journal, tmp_path)
        reader = CoordinatorEventReader(journal, upstream)
        journal.append(
            "BATCH_STARTED",
            "start",
            {
                "delta": {
                    "points": {"task_start": {"status": "UNRUN", "attempts": 0}},
                    "workers": {"worker-01": {"generation": 1, "state": "AVAILABLE"}},
                    "batch_cleanup_complete": False,
                }
            },
        )
        journal.append(
            "RESULT_COMMITTED",
            "result-p01",
            {
                "delta": {
                    "points": {"task_start": {"status": "PASSED", "attempts": 1}},
                    "workers": {"worker-01": {"generation": 2, "state": "RECOVERING"}},
                },
                "identity": {"point_id": "task_start"},
                "response": {"location": str(sealed), "sha256": digest},
            },
        )
        journal.append(
            "BATCH_CLEANUP_COMPLETE",
            "cleanup",
            {
                "delta": {
                    "workers": {"worker-01": {"generation": 2, "state": "STOPPED"}},
                    "batch_cleanup_complete": True,
                }
            },
        )

        projected = reader.read_after(reader.initial_cursor).projected_state

    assert projected["points"]["task_start"] == {
        "status": "PASSED",
        "attempts": 1,
    }
    assert projected["workers"]["worker-01"] == {
        "generation": 2,
        "state": "STOPPED",
    }
    assert projected["batch_cleanup_complete"] is True


# --------------------------------------------------------------------------------------
# Task 5: a projection source adapts and verifies, it never merges payload.delta
# --------------------------------------------------------------------------------------


def test_projection_source_verifies_and_passes_deltas_through_unchanged(tmp_path: Path) -> None:
    from so101_teleop.expert_validation.projection_source import (
        CoordinatorJournalSource,
        VerifiedEventBatch,
    )
    from so101_teleop.expert_validation.reducer import CanonicalCampaignReducer

    sealed = tmp_path / "sealed" / "attempt_result_manifest.json"
    sealed.parent.mkdir()
    sealed.write_text('{"status": "PASSED"}', encoding="utf-8")
    digest = hashlib.sha256(sealed.read_bytes()).hexdigest()

    with CoordinatorJournal.create(tmp_path / "journal", "batch-a") as journal:
        journal.append("CAMPAIGN_STARTED", "start", {
            "campaign_id": "campaign-a", "batch_id": "batch-a",
            "runtime_identity_sha256": "a" * 64, "config_sha256": "b" * 64,
        })
        journal.append("RESULT_COMMITTED", "result-1", {
            "point_id": "p1", "attempt_id": "p1-attempt-1",
            "result_sha256": "c" * 64, "outcome": "PASSED",
            "response": {"location": str(sealed), "sha256": digest},
            "delta": {"points": {"p1": {"status": "PASSED"}}},
        })
        upstream = binding(journal, tmp_path)
        source = CoordinatorJournalSource(
            journal, upstream, manifest_verifier=lambda *_args: None)

        batch = source.read_after(AcceptedCoordinatorCursor.initial(upstream))

        assert isinstance(batch, VerifiedEventBatch)
        assert [event.type for event in batch.events] == ["CAMPAIGN_STARTED", "RESULT_COMMITTED"]
        # The source only adapts and verifies: the delta travels through untouched and no
        # projection state is derived here.
        assert batch.events[1].payload["delta"] == {"points": {"p1": {"status": "PASSED"}}}
        assert not hasattr(batch, "projected_state")
        assert not hasattr(batch, "projected_point_states")
        assert batch.next_cursor.sequence == 2
        assert batch.next_cursor.frame_sha256 == batch.events[-1].frame_sha256

        # The canonical reducer, not the source, derives the point terminal.
        reducer = CanonicalCampaignReducer()
        state = reducer.apply(None, batch.events[0])
        state = reducer.apply(state, batch.events[1])
        assert state.points["p1"].status.value == "PASSED"
        assert state.points["p1"].phase.value == "TERMINAL"
