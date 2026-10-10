"""The canonical reducer over verified committed campaign events (design section 9).

One reducer, four orthogonal axes: point status, execution phase, attempt validity/
infrastructure outcome, and the batch's business/infrastructure/cleanup/fence fields. Sources may
only adapt and verify events; they must never merge a `payload.delta` themselves, and a point
terminal may only be derived from a verified result - never invented by a `POINT_TERMINAL` event
or by an attempt-level `INVALID`.

The module is imported lazily so a missing implementation fails as an assertion rather than a
collection error.
"""

from __future__ import annotations

import importlib
import importlib.util
import json

import pytest


def _reducer_module():
    spec = importlib.util.find_spec("so101_teleop.expert_validation.reducer")
    assert spec is not None, "so101_teleop.expert_validation.reducer is not implemented yet"
    return importlib.import_module("so101_teleop.expert_validation.reducer")


CAMPAIGN = "campaign-a"
BATCH = "batch-a"
RUNTIME = "a" * 64
CONFIG = "b" * 64


class _Event:
    """The verified-event surface the reducer consumes."""

    def __init__(self, event_type, payload, *, sequence, epoch=1, frame="c" * 64, batch=BATCH):
        self.type = event_type
        self.payload = payload
        self.sequence = sequence
        self.coordinator_epoch = epoch
        self.frame_sha256 = frame
        self.batch_id = batch


def _started(module, sequence=1):
    return module.CanonicalCampaignReducer().apply(
        None,
        _Event(
            "CAMPAIGN_STARTED",
            {
                "campaign_id": CAMPAIGN,
                "batch_id": BATCH,
                "runtime_identity_sha256": RUNTIME,
                "config_sha256": CONFIG,
            },
            sequence=sequence,
        ),
    )


def _result_payload(point_id, attempt_id, outcome, *, result_sha256="d" * 64):
    return {
        "point_id": point_id,
        "attempt_id": attempt_id,
        "result_sha256": result_sha256,
        "outcome": outcome,
        "attempt_validity": "VALID",
    }


def test_axes_start_orthogonal_and_unrun(tmp_path=None) -> None:
    module = _reducer_module()
    state = _started(module)

    assert state.points == {}
    assert state.batch_business_terminal is None
    assert state.batch_infrastructure_terminal is None
    assert state.batch_cleanup_complete is False
    assert state.recovery_fence is False
    assert state.runtime_identity_sha256 == RUNTIME
    assert state.config_sha256 == CONFIG


def test_lease_and_attempt_change_only_the_execution_phase() -> None:
    module = _reducer_module()
    state = _started(module)

    leased = module.CanonicalCampaignReducer().apply(
        state,
        _Event("POINT_LEASED", {"point_id": "p1", "attempt_id": "p1-attempt-1"}, sequence=2),
    )
    point = leased.points["p1"]
    assert point.phase is module.ExecutionPhase.LEASED
    assert point.status is module.PointStatus.UNRUN
    assert point.attempt_id == "p1-attempt-1"

    running = module.CanonicalCampaignReducer().apply(
        leased,
        _Event("ATTEMPT_STARTED", {"point_id": "p1", "attempt_id": "p1-attempt-1"}, sequence=3),
    )
    point = running.points["p1"]
    assert point.phase is module.ExecutionPhase.RUNNING
    assert point.status is module.PointStatus.UNRUN
    assert running.batch_cleanup_complete is False


def test_result_committed_derives_the_point_terminal() -> None:
    module = _reducer_module()
    reducer = module.CanonicalCampaignReducer()
    state = _started(module)
    state = reducer.apply(state, _Event("POINT_LEASED", {"point_id": "p1", "attempt_id": "a1"}, sequence=2))
    state = reducer.apply(state, _Event("ATTEMPT_STARTED", {"point_id": "p1", "attempt_id": "a1"}, sequence=3))
    state = reducer.apply(
        state,
        _Event("RESULT_COMMITTED", _result_payload("p1", "a1", "FAILED", result_sha256="e" * 64), sequence=4),
    )

    point = state.points["p1"]
    assert point.status is module.PointStatus.FAILED
    assert point.phase is module.ExecutionPhase.TERMINAL
    assert point.result_sha256 == "e" * 64
    assert state.attempts["a1"].validity is module.AttemptValidity.VALID


def test_attempt_invalid_never_becomes_a_business_failure() -> None:
    module = _reducer_module()
    reducer = module.CanonicalCampaignReducer()
    state = _started(module)
    state = reducer.apply(state, _Event("POINT_LEASED", {"point_id": "p1", "attempt_id": "a1"}, sequence=2))
    payload = {
        "point_id": "p1",
        "attempt_id": "a1",
        "attempt_validity": "INVALID",
        "infrastructure_outcome": "FAILED",
    }
    state = reducer.apply(state, _Event("ATTEMPT_STARTED", payload, sequence=3))

    attempt = state.attempts["a1"]
    assert attempt.validity is module.AttemptValidity.INVALID
    assert attempt.infrastructure is module.InfrastructureOutcome.FAILED
    assert state.points["p1"].status is module.PointStatus.UNRUN
    assert state.batch_infrastructure_terminal == "ATTEMPT_INVALID"


def test_point_terminal_only_confirms_the_same_result() -> None:
    module = _reducer_module()
    reducer = module.CanonicalCampaignReducer()
    state = _started(module)
    state = reducer.apply(state, _Event("POINT_LEASED", {"point_id": "p1", "attempt_id": "a1"}, sequence=2))
    state = reducer.apply(
        state,
        _Event("RESULT_COMMITTED", _result_payload("p1", "a1", "PASSED", result_sha256="f" * 64), sequence=3),
    )
    confirmed = reducer.apply(
        state,
        _Event("POINT_TERMINAL", {"point_id": "p1", "result_sha256": "f" * 64}, sequence=4),
    )
    assert confirmed.points["p1"].status is module.PointStatus.PASSED

    with pytest.raises(module.ReducerError) as mismatch:
        reducer.apply(
            state,
            _Event("POINT_TERMINAL", {"point_id": "p1", "result_sha256": "0" * 64}, sequence=5),
        )
    assert mismatch.value.code == "REDUCER_TERMINAL_RESULT_MISMATCH"


def test_point_terminal_cannot_create_a_terminal_by_itself() -> None:
    module = _reducer_module()
    reducer = module.CanonicalCampaignReducer()
    state = _started(module)
    with pytest.raises(module.ReducerError) as error:
        reducer.apply(
            state,
            _Event("POINT_TERMINAL", {"point_id": "p1", "result_sha256": "f" * 64}, sequence=2),
        )
    assert error.value.code == "REDUCER_TERMINAL_WITHOUT_RESULT"


def test_batch_terminal_does_not_imply_cleanup() -> None:
    module = _reducer_module()
    reducer = module.CanonicalCampaignReducer()
    state = _started(module)
    terminal = reducer.apply(
        state,
        _Event("BATCH_TERMINAL", {"business_terminal": "COMPLETE"}, sequence=2),
    )
    assert terminal.batch_business_terminal == "COMPLETE"
    assert terminal.batch_cleanup_complete is False

    cleaned = reducer.apply(
        terminal, _Event("CLEANUP_COMMITTED", {"cleanup_complete": True}, sequence=3)
    )
    assert cleaned.batch_cleanup_complete is True

    with pytest.raises(module.ReducerError) as late:
        reducer.apply(cleaned, _Event("POINT_LEASED", {"point_id": "p9", "attempt_id": "a9"}, sequence=4))
    assert late.value.code == "REDUCER_APPEND_AFTER_TERMINAL"


def test_identity_drift_and_batch_mismatch_are_refused() -> None:
    module = _reducer_module()
    reducer = module.CanonicalCampaignReducer()
    state = _started(module)

    with pytest.raises(module.ReducerError) as drift:
        reducer.apply(
            state,
            _Event(
                "CAMPAIGN_STARTED",
                {
                    "campaign_id": CAMPAIGN,
                    "batch_id": BATCH,
                    "runtime_identity_sha256": "9" * 64,
                    "config_sha256": CONFIG,
                },
                sequence=2,
            ),
        )
    assert drift.value.code == "REDUCER_IDENTITY_DRIFT"

    with pytest.raises(module.ReducerError) as other_batch:
        reducer.apply(
            state,
            _Event("POINT_LEASED", {"point_id": "p1", "attempt_id": "a1"}, sequence=2, batch="batch-b"),
        )
    assert other_batch.value.code == "REDUCER_BATCH_MISMATCH"


def test_reducer_is_pure_and_idempotent() -> None:
    module = _reducer_module()
    reducer = module.CanonicalCampaignReducer()
    state = _started(module)
    before = json.dumps(state.as_document(), sort_keys=True)
    event = _Event("POINT_LEASED", {"point_id": "p1", "attempt_id": "a1"}, sequence=2)

    once = reducer.apply(state, event)
    twice = reducer.apply(once, event)

    assert json.dumps(state.as_document(), sort_keys=True) == before
    assert twice.as_document() == once.as_document()
    assert twice.last_sequence == 2


def test_sequence_regression_is_refused() -> None:
    module = _reducer_module()
    reducer = module.CanonicalCampaignReducer()
    state = reducer.apply(
        _started(module),
        _Event("POINT_LEASED", {"point_id": "p1", "attempt_id": "a1"}, sequence=2),
    )
    with pytest.raises(module.ReducerError) as error:
        reducer.apply(
            state,
            _Event(
                "POINT_LEASED",
                {"point_id": "p2", "attempt_id": "a2"},
                sequence=2,
                frame="d" * 64,
            ),
        )
    assert error.value.code == "REDUCER_SEQUENCE_REGRESSION"

    # The exact same event replayed is idempotent rather than a regression.
    assert reducer.apply(state, _Event(
        "POINT_LEASED", {"point_id": "p1", "attempt_id": "a1"}, sequence=2)
    ).as_document() == state.as_document()


# -- Task 5: the service-facing document is derived from canonical state, never from a delta ---


def _leased(module, state, *, sequence=2, worker_id="worker-01", generation=1):
    return module.CanonicalCampaignReducer().apply(
        state,
        _Event(
            "POINT_LEASED",
            {
                "point_id": "point-a",
                "attempt_id": "point-a-lease-1",
                "worker_id": worker_id,
                "worker_generation": generation,
                "lease_generation": 1,
            },
            sequence=sequence,
        ),
    )


def test_projection_document_reports_lease_worker_and_running_attempt():
    module = _reducer_module()
    state = _leased(module, _started(module))

    document = module.projection_document(state)

    point = document["points"]["point-a"]
    assert point["status"] == "UNRUN"
    assert point["phase"] == "LEASED"
    assert point["attempts"] == 1
    assert point["terminal"] is False
    assert point["active_attempt"] == "point-a-lease-1"
    worker = document["workers"]["worker-01"]
    assert worker["generation"] == 1
    assert worker["lease_count"] == 1
    assert worker["state"] == "EXECUTING"
    assert worker["lease"] == {"point_id": "point-a", "attempt_id": "point-a-lease-1"}
    assert document["terminal_reason"] is None
    assert document["batch_cleanup_complete"] is False


def test_projection_document_reports_terminal_result_and_cleaned_up_worker():
    module = _reducer_module()
    state = _leased(module, _started(module))
    state = module.CanonicalCampaignReducer().apply(
        state,
        _Event(
            "ATTEMPT_STARTED",
            {"point_id": "point-a", "attempt_id": "point-a-lease-1", "worker_id": "worker-01"},
            sequence=3,
        ),
    )
    state = module.CanonicalCampaignReducer().apply(
        state,
        _Event(
            "RESULT_COMMITTED",
            {
                "point_id": "point-a",
                "attempt_id": "point-a-lease-1",
                "outcome": "FAILED",
                "result_sha256": "d" * 64,
            },
            sequence=4,
        ),
    )
    state = module.CanonicalCampaignReducer().apply(
        state,
        _Event("BATCH_TERMINAL", {"business_terminal": "POINTS_COMPLETE"}, sequence=5),
    )
    state = module.CanonicalCampaignReducer().apply(
        state, _Event("CLEANUP_COMMITTED", {"cleanup_complete": True}, sequence=6)
    )

    document = module.projection_document(state)

    point = document["points"]["point-a"]
    assert point["status"] == "FAILED"
    assert point["terminal"] is True
    assert point["active_attempt"] is None
    worker = document["workers"]["worker-01"]
    assert worker["state"] == "STOPPED"
    assert worker["lease"] is None
    assert worker["lease_count"] == 1
    assert document["terminal_reason"] == "POINTS_COMPLETE"
    assert document["batch_cleanup_complete"] is True


def test_projection_document_round_trips_worker_state_through_the_state_document():
    module = _reducer_module()
    state = _leased(module, _started(module), worker_id="worker-02", generation=3)

    restored = module.CampaignReducerState.from_document(state.as_document())

    assert restored.workers["worker-02"].as_document() == {
        "worker_id": "worker-02",
        "worker_generation": 3,
        "lease_count": 1,
        "slot_id": None,
    }
    assert restored == state
