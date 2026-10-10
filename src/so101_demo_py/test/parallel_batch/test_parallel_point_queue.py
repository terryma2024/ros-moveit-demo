"""Durable shared point queue for the macOS service campaign (design section 8).

The two W2 slots are concurrent capacity, not a static point assignment: every selected point
enters one fsync-backed queue, one lease carries exactly one point, and an unselected point can
never obtain a lease, an invocation or a result. These tests drive the RED/GREEN boundary of
plan Task 2 and import the module under test lazily so a missing implementation fails as an
assertion rather than a collection error.
"""

from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path

import pytest

from test_parallel_selection import (  # noqa: F401 - shared catalog fixture helpers
    ALL_IDS,
    ANCHOR_IDS,
    CLOSURE_SHA,
    CONFIG_SHA,
    SAMPLE_IDS,
    _catalog_document,
    _first_pass,
    _selection_module,
    _write_catalog,
)


def _queue_module():
    spec = importlib.util.find_spec("so101_demo.parallel_batch.queue")
    assert spec is not None, "so101_demo.parallel_batch.queue is not implemented yet"
    return importlib.import_module("so101_demo.parallel_batch.queue")


def _binding(module, catalog: Path, point_ids=ALL_IDS):
    return _first_pass(module, catalog, point_ids)


def _queue(module, tmp_path: Path, binding, *, root: Path | None = None):
    return module.DurablePointQueue(
        root=root if root is not None else tmp_path / "queue", binding=binding
    )


def _worker(module, worker_id: str, slot_id: str, generation: int = 1):
    return module.WorkerIdentity(
        worker_id=worker_id, slot_id=slot_id, generation=generation
    )


def _digest(label: str) -> str:
    import hashlib

    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _result(module, lease, outcome: str = "PASSED", *, suffix: str = "a"):
    return module.CommittedResult(
        point_id=lease.point_id,
        attempt_id=lease.attempt_id,
        outcome=outcome,
        evidence_sha256=_digest(f"evidence-{suffix}"),
        result_sha256=_digest(f"result-{suffix}"),
    )


# --------------------------------------------------------------------------------------
# The whole selected set drains exactly once
# --------------------------------------------------------------------------------------


def test_two_slots_drain_twenty_selected_points_exactly_once(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _binding(selection, catalog)
    queue = _queue(module, tmp_path, binding)

    first = _worker(module, "w1", "slot-0")
    second = _worker(module, "w2", "slot-1")
    leased: list[str] = []
    results: list[str] = []
    index = 0
    while True:
        worker = first if index % 2 == 0 else second
        lease = queue.lease_next(worker)
        if lease is None:
            break
        assert lease.identity[0] == binding.campaign_id
        assert lease.identity[1] == binding.batch_id
        assert lease.identity[2] == lease.point_id
        assert lease.identity[3] == lease.attempt_id
        assert lease.identity[4] == lease.generation == 1
        assert lease.identity[5] == worker.worker_id
        assert lease.slot_id == worker.slot_id
        assert lease.point_sha256 == next(
            point.point_sha256 for point in binding.points if point.point_id == lease.point_id
        )
        leased.append(lease.point_id)
        queue.commit_result(lease, _result(module, lease, suffix="abcdef"[index % 6]))
        results.append(lease.point_id)
        index += 1

    assert index == 20
    assert leased == list(ALL_IDS)
    assert results == list(ALL_IDS)
    assert len(set(leased)) == 20
    snapshot = queue.snapshot()
    assert snapshot.pending_point_ids == ()
    assert snapshot.active_leases == ()
    assert tuple(result.point_id for result in snapshot.results) == ALL_IDS
    assert queue.lease_next(first) is None


def test_unselected_catalog_points_never_reach_a_lease(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    catalog = _write_catalog(tmp_path)
    selected = ANCHOR_IDS + SAMPLE_IDS[:1]
    binding = _binding(selection, catalog, selected)
    queue = _queue(module, tmp_path, binding)

    leased = []
    while True:
        lease = queue.lease_next(_worker(module, "w1", "slot-0"))
        if lease is None:
            break
        leased.append(lease.point_id)
        queue.commit_result(lease, _result(module, lease))

    assert leased == list(selected)
    unselected = set(ALL_IDS) - set(selected)
    assert unselected and not (set(leased) & unselected)


# --------------------------------------------------------------------------------------
# One lease at a time, idempotent repeats, stale generations
# --------------------------------------------------------------------------------------


def test_duplicate_lease_request_from_the_same_worker_is_idempotent(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _binding(selection, catalog)
    queue = _queue(module, tmp_path, binding)

    first = _worker(module, "w1", "slot-0")
    lease = queue.lease_next(first)
    again = queue.lease_next(first)

    assert lease is not None and again is not None
    assert lease.sha256 == again.sha256
    assert lease.identity == again.identity

    other = queue.lease_next(_worker(module, "w2", "slot-1"))
    assert other is not None
    assert other.point_id != lease.point_id
    assert other.worker_id == "w2" and other.slot_id == "slot-1"


def test_stale_generation_is_refused(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _binding(selection, catalog)
    queue = _queue(module, tmp_path, binding)

    lease = queue.lease_next(_worker(module, "w1", "slot-0", generation=2))
    assert lease is not None and lease.generation == 2

    with pytest.raises(module.QueueError) as stale_commit:
        queue.commit_result(
            lease, _result(module, lease), worker=_worker(module, "w1", "slot-0", generation=1)
        )
    assert stale_commit.value.code == "QUEUE_STALE_GENERATION"

    with pytest.raises(module.QueueError) as stale_lease:
        queue.lease_next(_worker(module, "w1", "slot-0", generation=1))
    assert stale_lease.value.code == "QUEUE_STALE_GENERATION"


def test_commit_without_the_owning_worker_is_refused(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _binding(selection, catalog)
    queue = _queue(module, tmp_path, binding)

    lease = queue.lease_next(_worker(module, "w1", "slot-0"))
    assert lease is not None

    with pytest.raises(module.QueueError) as error:
        queue.commit_result(lease, _result(module, lease), worker=_worker(module, "w2", "slot-1"))
    assert error.value.code == "QUEUE_LEASE_OWNER_MISMATCH"


# --------------------------------------------------------------------------------------
# Forged leases, unselected injection, duplicate results, invalid outcomes
# --------------------------------------------------------------------------------------


def test_forged_and_unselected_leases_are_refused(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _binding(selection, catalog, ANCHOR_IDS + SAMPLE_IDS[:1])
    queue = _queue(module, tmp_path, binding)
    rejected = SAMPLE_IDS[5]

    forged = module.PointLease(
        campaign_id=binding.campaign_id,
        batch_id=binding.batch_id,
        point_id=rejected,
        attempt_id=f"{rejected}-attempt-1",
        generation=1,
        worker_id="w1",
        slot_id="slot-0",
        point_sha256="a" * 64,
    )
    with pytest.raises(module.QueueError) as unselected:
        queue.commit_result(
            forged, _result(module, forged), worker=_worker(module, "w1", "slot-0")
        )
    assert unselected.value.code == "QUEUE_UNSELECTED_POINT"

    lease = queue.lease_next(_worker(module, "w1", "slot-0"))
    assert lease is not None
    tampered = module.PointLease(
        campaign_id=lease.campaign_id,
        batch_id=lease.batch_id,
        point_id=lease.point_id,
        attempt_id=lease.attempt_id,
        generation=lease.generation,
        worker_id=lease.worker_id,
        slot_id=lease.slot_id,
        point_sha256="b" * 64,
    )
    with pytest.raises(module.QueueError) as mismatch:
        queue.commit_result(
            tampered, _result(module, tampered), worker=_worker(module, "w1", "slot-0")
        )
    assert mismatch.value.code == "QUEUE_LEASE_MISMATCH"


def test_a_duplicate_result_cannot_be_committed_twice(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _binding(selection, catalog)
    queue = _queue(module, tmp_path, binding)

    worker = _worker(module, "w1", "slot-0")
    lease = queue.lease_next(worker)
    assert lease is not None
    queue.commit_result(lease, _result(module, lease))

    with pytest.raises(module.QueueError) as duplicate:
        queue.commit_result(lease, _result(module, lease), worker=worker)
    assert duplicate.value.code == "QUEUE_POINT_TERMINAL"

    snapshot = queue.snapshot()
    assert [result.point_id for result in snapshot.results] == [lease.point_id]


def test_attempt_invalid_is_not_a_business_outcome(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _binding(selection, catalog)
    queue = _queue(module, tmp_path, binding)

    lease = queue.lease_next(_worker(module, "w1", "slot-0"))
    assert lease is not None
    with pytest.raises(module.QueueError) as error:
        queue.commit_result(
            lease, _result(module, lease, outcome="INVALID"), worker=_worker(module, "w1", "slot-0")
        )
    assert error.value.code == "QUEUE_OUTCOME_INVALID"


# --------------------------------------------------------------------------------------
# Durability and recovery
# --------------------------------------------------------------------------------------


def test_queue_survives_reopen_without_loss_or_double_lease(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _binding(selection, catalog)
    root = tmp_path / "queue"
    queue = _queue(module, tmp_path, binding, root=root)

    first_worker = _worker(module, "w1", "slot-0")
    second_worker = _worker(module, "w2", "slot-1")
    first_lease = queue.lease_next(first_worker)
    second_lease = queue.lease_next(second_worker)
    assert first_lease is not None and second_lease is not None
    queue.commit_result(first_lease, _result(module, first_lease))

    reopened = _queue(module, tmp_path, binding, root=root)
    snapshot = reopened.snapshot()
    assert [result.point_id for result in snapshot.results] == [first_lease.point_id]
    assert [lease.point_id for lease in snapshot.active_leases] == [second_lease.point_id]

    repeat = reopened.lease_next(first_worker)
    assert repeat is not None and repeat.point_id != first_lease.point_id
    assert repeat.point_id != second_lease.point_id

    with pytest.raises(module.QueueError):
        reopened.commit_result(
            first_lease, _result(module, first_lease), worker=first_worker
        )

    state = json.loads((root / "queue-state.json").read_text(encoding="utf-8"))
    assert state["committed_results"]
    assert state["selection_sha256"] == binding.selection_sha256


def test_abandoned_lease_is_recovered_by_a_higher_generation(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    catalog = _write_catalog(tmp_path)
    binding = _binding(selection, catalog)
    root = tmp_path / "queue"
    queue = _queue(module, tmp_path, binding, root=root)

    dying = _worker(module, "w1", "slot-0", generation=1)
    abandoned = queue.lease_next(dying)
    assert abandoned is not None

    recovered = _queue(module, tmp_path, binding, root=root)
    replacement = _worker(module, "w1b", "slot-0", generation=2)
    lease = recovered.lease_next(replacement)
    assert lease is not None
    assert lease.point_id == abandoned.point_id
    assert lease.generation == 2 and lease.worker_id == "w1b"
    assert recovered.snapshot().abandoned_attempts == (abandoned.attempt_id,)

    with pytest.raises(module.QueueError):
        recovered.commit_result(
            abandoned, _result(module, abandoned), worker=dying
        )

    recovered.commit_result(lease, _result(module, lease), worker=replacement)
    assert [result.point_id for result in recovered.snapshot().results] == [lease.point_id]


def test_queue_refuses_a_binding_that_is_not_a_selection_binding(tmp_path: Path) -> None:
    selection = _selection_module()
    module = _queue_module()
    with pytest.raises(module.QueueError) as error:
        module.DurablePointQueue(root=tmp_path / "q", binding=object())
    assert error.value.code == "QUEUE_BINDING_TYPE"
