import asyncio
from pathlib import Path

import pytest

from so101_teleop.expert_validation.models import CleanupReceipt
from so101_teleop.expert_validation.preflight import PreflightEngine, PreflightRejected
from so101_teleop.expert_validation.store import SupervisorStore
from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor

from test_expert_validation_preflight import Resources, _request


class Owner:
    def __init__(self):
        self.requests = []
        self.timeline = []

    async def spawn_and_wait(self, request):
        self.requests.append(request)
        point = getattr(request, "selected_point_ids", ("first-pass",))[0]
        self.timeline.append(
            f"start-{request.batch_id}-{point}-n{getattr(request, 'worker_count', 'adaptive')}-"
            f"k{getattr(request, 'max_points_per_worker', 'none')}"
        )
        self.timeline.append(f"cleanup-{request.batch_id}-{point}")
        return {"cleanup_complete": True, "receipt_sha256": "d" * 64}


def _supervisor(tmp_path, resources=None):
    root = tmp_path.resolve()
    store = SupervisorStore.open((root / "store").resolve())
    owner = Owner()
    supervisor = ExpertValidationSupervisor(
        store=store,
        process_owner=owner,
        preflight_engine=PreflightEngine(resources or Resources()),
    )
    return supervisor, owner, store


def test_sequential_and_parallel_use_same_coordinator_path(tmp_path):
    supervisor, owner, store = _supervisor(tmp_path)
    try:
        asyncio.run(supervisor.start_first_pass(_request(tmp_path / "seq", "SEQUENTIAL")))
        asyncio.run(
            supervisor.start_first_pass(
                _request(
                    tmp_path / "par",
                    "PARALLEL",
                    campaign_id="campaign-2",
                    batch_id="b002",
                    manifest_id="manifest-2",
                    worker_count=2,
                    max_points_per_worker=2,
                )
            )
        )
        assert [type(request).__name__ for request in owner.requests] == [
            "CoordinatorStartRequest",
            "CoordinatorStartRequest",
        ]
        assert [
            (request.worker_count, request.max_points_per_worker)
            for request in owner.requests
        ] == [(1, 4), (2, 2)]
    finally:
        store.close()


def test_installed_coordinator_is_discoverable_on_child_path(tmp_path):
    supervisor, owner, store = _supervisor(tmp_path)
    coordinator = tmp_path / "install/lib/so101_demo_py/so101_parallel_batch"
    coordinator.parent.mkdir(parents=True)
    coordinator.write_text("console\n", encoding="utf-8")
    try:
        request = _request(
            tmp_path / "seq",
            "SEQUENTIAL",
            coordinator_executable_path=coordinator.resolve(),
            environment={"PATH": "/usr/bin"},
        )
        asyncio.run(supervisor.start_first_pass(request))

        assert owner.requests[-1].environment["PATH"] == (
            f"{coordinator.parent.resolve()}:/usr/bin"
        )
    finally:
        store.close()


def test_parallel_rejection_never_spawns_or_downgrades(tmp_path):
    supervisor, owner, store = _supervisor(
        tmp_path, Resources(admitted=False, reasons=("GPU_HEADROOM",))
    )
    try:
        with pytest.raises(PreflightRejected, match="GPU_HEADROOM"):
            asyncio.run(supervisor.start_first_pass(_request(tmp_path, "PARALLEL")))
        assert owner.requests == []
    finally:
        store.close()


def test_adaptive_uses_one_wrapper_request_without_k(tmp_path):
    supervisor, owner, store = _supervisor(tmp_path)
    try:
        asyncio.run(
            supervisor.start_first_pass(_request(tmp_path, "ADAPTIVE", count=20))
        )
        request = owner.requests[-1]
        assert type(request).__name__ == "AdaptiveStartRequest"
        assert request.levels == (8, 6, 4, 2, 1)
        assert "--max-points-per-worker" not in request.argv
    finally:
        store.close()


def test_each_retry_is_a_new_n1_k1_batch_after_prior_cleanup(tmp_path):
    supervisor, owner, store = _supervisor(tmp_path)
    try:
        request = _request(tmp_path, "SEQUENTIAL", campaign_id="campaign-retry")
        asyncio.run(supervisor.start_first_pass(request))
        owner.timeline.clear()
        asyncio.run(supervisor.start_retries("campaign-retry", ("point_1", "point_2")))
        assert owner.timeline == [
            "start-retry-001-point_1-n1-k1",
            "cleanup-retry-001-point_1",
            "start-retry-002-point_2-n1-k1",
            "cleanup-retry-002-point_2",
        ]
        assert store.next_retry("campaign-retry") is None
    finally:
        store.close()


def test_all_success_retry_is_explicitly_not_applicable(tmp_path):
    supervisor, _owner, store = _supervisor(tmp_path)
    try:
        request = _request(tmp_path, "SEQUENTIAL", campaign_id="campaign-success")
        asyncio.run(supervisor.start_first_pass(request))
        assert asyncio.run(supervisor.start_retries("campaign-success", ())) == {
            "status": "LIVE_RETRY_NOT_APPLICABLE_ALL_SUCCEEDED"
        }
    finally:
        store.close()
