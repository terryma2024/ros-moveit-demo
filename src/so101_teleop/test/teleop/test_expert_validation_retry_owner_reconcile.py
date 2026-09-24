"""The retry admission retires a finished owner, and only a finished one.

Recorded production defect (``$RUN/task12/cleanup-fix/probe/probe-live-next-refusal.log``): after
the cleanup-receipt fix (``af93107a``) the console's retry of the genuinely ``FAILED`` point was
refused

    409 {"code": "RETRY_OWNER_ACTIVE"}

The refusal was not about a live owner. The recorded store held exactly one ``owned_execution`` row

    batch_id=bf16a state=RUNNING pid=25005 pgid=25005 started_ticks=1790054976931255

whose process was gone (``ps -p 25005`` was empty and process group 25005 had no members), and whose
batch was terminal-clean. The only write this store ever makes to that column is ``INTENT ->
RUNNING`` on the spawn ACK (``acknowledge_execution_owner``), so nothing ever retired the row, and
``_check_no_owner_or_fence`` refused on the state alone - a first pass that had finished blocked its
own retry for good.

These tests compose the same production state inside ``tmp_path`` through :mod:`retry_fixture`: a
real batch whose bytes the projection accepts, a real finished owner row whose identity is proven
gone by the kernel, and the real service assembled by ``create_production_service``. The positive
case asserts the admission is *granted* and reaches the spawn boundary; the negatives assert that a
live owner, an identity the platform will not report, and a first pass that never committed cleanup
all still refuse by name.
"""

from __future__ import annotations

import asyncio

import pytest

from retry_fixture import (
    CAMPAIGN_ID,
    POINT_ID,
    build_retry_session,
    end_owner_process,
    install_live_owner,
)
from so101_teleop.process_identity import IDENTITY_EXITED, identity_state

ROUTE = "/expert-validation/campaigns/{campaign_id}/full-restart-retries"
#: The one batch the admission mints for the first retry of a campaign: ``retry-<ordinal + 1>``.
RETRY_BATCH_ID = "retry-001"
#: The token this file's own spawn boundary raises, so the admission is proven to have been granted.
SPAWN_REFUSED = "RETRY_SPAWN_REFUSED_BY_TEST"


@pytest.fixture()
def production_session(tmp_path):
    """The composed production service, with the durable state the retry admission will read."""

    session = build_retry_session(tmp_path, session_id="retry-owner-reconcile-test")
    try:
        store = session.store
        # The replay has to be real: if restore could not rebind the campaign, the endpoint would
        # refuse before the admission and these tests would pass for the wrong reason.
        assert session.service.get_campaign(CAMPAIGN_ID)["campaign_id"] == CAMPAIGN_ID
        # The receipt gate the previous fix repaired is passed here, by the batch's own bytes - the
        # refusal under test is the one *after* it.
        receipt = store.batch(session.batch_id).cleanup_receipt_sha256
        assert receipt is not None, "the first pass's cleanup bytes earned no durable receipt"
        owner = store.owned_execution(session.batch_id)
        assert owner.state == "RUNNING", "the condition under test is a RUNNING owner row"
        assert identity_state(
            owner.pid, owner.started_ticks, owner.argv_sha256
        ) == IDENTITY_EXITED, "the recorded owner process must be proven gone, never assumed gone"
        assert [item.state for item in store.retry_items(CAMPAIGN_ID)] == ["QUEUED"]
        yield session
    finally:
        session.close()


def console_body(session, command_id: str, point_ids=(POINT_ID,)) -> dict:
    """The body the console builds: the lease authority, one command id, the points, the phrase."""

    return {
        **session.lease_body,
        "command_id": command_id,
        "point_ids": list(point_ids),
        "confirmation": "CONFIRM FULL_RESTART RETRIES",
    }


def post_retry(service, payload: dict):
    """POST in the caller's own thread: the store's connection is thread-bound."""

    import httpx

    from so101_teleop.expert_validation.api import create_expert_validation_app

    app = create_expert_validation_app(service)

    async def call():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://retry-owner-reconcile-test"
        ) as client:
            return await client.post(ROUTE.format(campaign_id=CAMPAIGN_ID), json=payload)

    return asyncio.run(call())


def _refuse_the_spawn(monkeypatch, code: str = SPAWN_REFUSED) -> list:
    """Intercept the one external process boundary, and record whether it was reached at all."""

    from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor

    calls: list = []

    async def refuse(self, request, *, owner_intent=None):
        calls.append(request)
        raise RuntimeError(code)

    monkeypatch.setattr(ExpertValidationSupervisor, "_spawn", refuse)
    return calls


def test_the_console_retry_of_a_finished_first_pass_is_admitted_not_refused(
    production_session, monkeypatch
):
    """RED: this answered ``409 {"code": "RETRY_OWNER_ACTIVE"}`` for a first pass that had finished.

    The owner row is a real one: a ``RUNNING`` row whose recorded process the kernel proves gone.
    The console request must now pass the owner gate and reach the one owner-spawn boundary - which
    this test refuses by name, because the point of the assertion is that the *admission* was
    granted, not that a real MuJoCo batch started inside a unit test.
    """

    session = production_session
    service, store = session.service, session.store
    before = store.owned_execution(session.batch_id)
    calls = _refuse_the_spawn(monkeypatch)

    response = post_retry(service, console_body(session, "retry-owner-reconcile-1"))

    assert response.status_code == 409, response.text
    assert response.json()["code"] == SPAWN_REFUSED, response.text
    assert len(calls) == 1, "the admission must reach the spawn boundary exactly once"

    retired = store.owned_execution(session.batch_id)
    assert retired.state == "EXITED", "the finished owner is retired durably, not skipped once"
    assert (retired.pid, retired.pgid, retired.started_ticks) == (
        before.pid, before.pgid, before.started_ticks
    ), "retiring the row must not rewrite the identity it was proven from"

    items = store.retry_items(CAMPAIGN_ID)
    assert [(item.point_id, item.state, item.batch_id) for item in items] == [
        (POINT_ID, "RUNNING", RETRY_BATCH_ID)
    ], "the admission transaction committed: the queue entry is bound to the retry batch"
    admissions = store.retry_admissions(CAMPAIGN_ID)
    assert [(row["batch_id"], row["point_id"]) for row in admissions] == [
        (RETRY_BATCH_ID, POINT_ID)
    ]
    assert store.batch(RETRY_BATCH_ID).batch_kind == "FULL_RESTART_RETRY"
    assert store.recovery_fence(CAMPAIGN_ID)["reason"] == (
        f"RETRY_SPAWN_FAILED: {SPAWN_REFUSED}"
    ), "the run stopped at the spawn boundary this test raised from"


def test_a_genuinely_live_owner_is_never_retired(production_session):
    """A live owner is never retired: ``RETRY_OWNER_ACTIVE`` is still the code, one gate deeper.

    The row is rewritten to name a process that really is running (the identity is read from the
    kernel), so this is the negative the fix must not lose.
    """

    from so101_teleop.expert_validation.store import StoreConflict

    session = production_session
    service, store = session.service, session.store
    process = install_live_owner(store, batch_id=session.batch_id)
    try:
        request, context = service._production_retry_admission(
            CAMPAIGN_ID, POINT_ID, {"command_id": "retry-owner-live-1"}
        )
        with pytest.raises(StoreConflict, match="RETRY_OWNER_ACTIVE"):
            asyncio.run(
                service.supervisor.start_production_retry(request=request, context=context)
            )
        assert store.owned_execution(session.batch_id).state == "RUNNING"
        assert [item.state for item in store.retry_items(CAMPAIGN_ID)] == ["QUEUED"]
        # The console's own gate agrees, one step earlier, and refuses without consuming anything.
        refused = post_retry(service, console_body(session, "retry-owner-live-2"))
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "VALIDATION_RECOVERY_REQUIRED", refused.text
        assert store.retry_admissions(CAMPAIGN_ID) == ()
    finally:
        end_owner_process(process)


def test_an_owner_identity_the_platform_will_not_report_still_refuses(
    production_session, monkeypatch
):
    """Fail closed: a row whose identity cannot be read is never retired on assumption."""

    from so101_teleop import process_identity
    from so101_teleop.expert_validation.store import StoreConflict

    session = production_session
    service, store = session.service, session.store

    def refuse(_pid):
        raise process_identity.ProcessIdentityError()

    monkeypatch.setattr(process_identity, "read_identity", refuse)

    request, context = service._production_retry_admission(
        CAMPAIGN_ID, POINT_ID, {"command_id": "retry-owner-unreadable-1"}
    )
    with pytest.raises(StoreConflict, match="RETRY_OWNER_ACTIVE"):
        asyncio.run(
            service.supervisor.start_production_retry(request=request, context=context)
        )

    assert store.owned_execution(session.batch_id).state == "RUNNING"
    assert store.retry_admissions(CAMPAIGN_ID) == ()


def test_a_first_pass_that_never_committed_cleanup_still_refuses_the_retry(tmp_path):
    """The missing receipt is refused before the owner gate: the row is not even retired.

    The admission validates the original's terminal-clean bytes before it looks at owners, and its
    transaction commits nothing at all - including the retirement of a row it never needed to read.
    """

    from so101_teleop.expert_validation.store import StoreConflict

    session = build_retry_session(
        tmp_path, cleanup_complete=None, session_id="retry-owner-no-cleanup"
    )
    try:
        service, store = session.service, session.store
        assert store.batch(session.batch_id).cleanup_receipt_sha256 is None
        request, context = service._production_retry_admission(
            CAMPAIGN_ID, POINT_ID, {"command_id": "retry-owner-no-cleanup-1"}
        )

        with pytest.raises(StoreConflict, match="RETRY_ORIGINAL_CLEANUP_INCOMPLETE"):
            asyncio.run(
                service.supervisor.start_production_retry(request=request, context=context)
            )

        assert store.owned_execution(session.batch_id).state == "RUNNING"
        assert store.retry_admissions(CAMPAIGN_ID) == ()
        assert [(item.point_id, item.state) for item in store.retry_items(CAMPAIGN_ID)] == [
            (POINT_ID, "QUEUED")
        ]
        # And the console's own body earns the same named refusal, from the endpoint's vocabulary.
        refused = post_retry(service, console_body(session, "retry-owner-no-cleanup-2"))
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "RETRY_ORIGINAL_CLEANUP_INCOMPLETE", refused.text
    finally:
        session.close()
