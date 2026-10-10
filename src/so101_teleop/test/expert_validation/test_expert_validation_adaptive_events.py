from __future__ import annotations

from pathlib import Path

from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_teleop.expert_validation.adaptive_events import AdaptiveEventReader
from so101_teleop.expert_validation.coordinator_events import (
    AcceptedCoordinatorCursor,
    CampaignUpstreamBinding,
)


def test_adaptive_reader_projects_runner_generations_not_nested_journal_directly(
    tmp_path: Path,
) -> None:
    with CoordinatorJournal.create(tmp_path / "runner-journal", "a20") as journal:
        binding = CampaignUpstreamBinding(
            campaign_id="campaign-a",
            batch_id="a20",
            owner_kind="ADAPTIVE_RUNNER",
            owner_epoch_or_generation=journal.coordinator_epoch,
            journal_root=journal.root,
            batch_root=tmp_path,
        )
        journal.append(
            "BATCH_MANIFEST",
            "manifest",
            {"selected_point_ids": ["task_start", "sample_01_near_left"]},
        )
        journal.append(
            "POOL_STARTING", "pool-starting-01", {"generation": 1, "worker_count": 8}
        )
        journal.append(
            "POOL_RUNNING",
            "pool-running-01",
            {"generation": 1, "worker_count": 8, "readiness_receipts": []},
        )
        journal.append(
            "POINT_INFRA_INTERRUPTED",
            "interrupt-task-start-1",
            {"point_id": "task_start", "generation": 1, "infra_attempts": 1},
        )
        journal.append(
            "POOL_DEGRADED",
            "pool-degraded-01",
            {
                "generation": 1,
                "from_count": 8,
                "to_count": 6,
                "failure": {
                    "kind": "WORKER_PROCESS",
                    "generation": 1,
                    "worker_count": 8,
                    "detail": "worker exited",
                },
            },
        )
        journal.append(
            "POOL_STARTING", "pool-starting-02", {"generation": 2, "worker_count": 6}
        )
        reader = AdaptiveEventReader(journal, binding)

        batch = reader.read_after(AcceptedCoordinatorCursor.initial(binding))
        view = batch.projection

        assert view.current_level == 6
        assert view.current_generation == 2
        assert view.levels_used == (8, 6)
        assert view.fallbacks[0].transition == "W8_TO_W6"
        assert view.fallbacks[0].reason == "WORKER_PROCESS"
        assert view.points["task_start"].status == "INFRA_INTERRUPTED"
        assert view.points["sample_01_near_left"].status == "UNRUN"


def test_adaptive_terminal_results_are_projected_only_from_runner_events(
    tmp_path: Path,
) -> None:
    with CoordinatorJournal.create(tmp_path / "runner-journal", "a20") as journal:
        binding = CampaignUpstreamBinding(
            "campaign-a",
            "a20",
            "ADAPTIVE_RUNNER",
            journal.coordinator_epoch,
            journal.root,
            tmp_path,
        )
        journal.append(
            "BATCH_MANIFEST", "manifest", {"selected_point_ids": ["task_start"]}
        )
        journal.append(
            "POINT_RESULT_IMPORTED",
            "result-task-start",
            {
                "generation": 1,
                "result": {
                    "point_id": "task_start",
                    "status": "PASSED",
                    "evidence_root": str(tmp_path / "generation-1"),
                    "infra_attempts": 0,
                },
            },
        )
        journal.append(
            "BATCH_TERMINAL",
            "terminal",
            {
                "status": "COMPLETED",
                "initial_worker_count": 8,
                "final_worker_count": 8,
                "levels_used": [8],
                "point_results": [],
                "transitions": [],
                "cleanup_complete": True,
            },
        )

        view = AdaptiveEventReader(journal, binding).read_after(
            AcceptedCoordinatorCursor.initial(binding)
        ).projection

        assert view.points["task_start"].status == "PASSED"
        assert view.terminal_status == "COMPLETED"
        assert view.cleanup_complete is True
