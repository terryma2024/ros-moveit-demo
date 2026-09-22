"""The retry admission retires a finished owner, and only a finished one.

Recorded production defect (``$RUN/task12/cleanup-fix/probe/probe-live-next-refusal.log``): after
the cleanup-receipt fix (``af93107a``) the console's retry of the genuinely ``FAILED`` point
``sample_05_near_center`` was refused

    409 {"code": "RETRY_OWNER_ACTIVE"}

The refusal was not about a live owner. The recorded store held exactly one ``owned_execution`` row

    batch_id=bf16a state=RUNNING pid=25005 pgid=25005 started_ticks=1790054976931255
    spawn_token=spawn-3e59db631b524d949c6f309b3399a3e0

whose process was gone (``ps -p 25005`` was empty and process group 25005 had no members), and whose
batch ``bf16a`` was terminal-clean (``CLEANUP_COMMITTED``, receipt ``f43880c1...``). The only write
this store ever makes to that column is ``INTENT -> RUNNING`` on the spawn ACK
(``acknowledge_execution_owner``, ``store.py:1512`` at ``af93107a``), so nothing ever retired the
row, and ``_check_no_owner_or_fence`` (``store.py:703-717``) refused on the state alone - a first
pass that had finished blocked its own retry for good. The same stale row poisons the host-wide
question a *new* run asks, which is the same check with ``campaign_id=None``.

These tests replay the recorded production store (copied, never written in place) through the
recorded production environment and the real endpoint, so the admission runs exactly as it did in
the refused live session. The positive case asserts the admission is *granted* and reaches the
spawn boundary; the negatives assert that a live owner, an identity the platform will not report,
and a row the store cannot retire all still refuse by name.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

CAMPAIGN_ID = "campaign-4d9af7fca30f49939f952db367338454"
BATCH_ID = "bf16a"
POINT_ID = "sample_05_near_center"
#: The durable receipt of ``bf16a``'s own verified ``CLEANUP_COMMITTED`` frame.
CLEANUP_RECEIPT = "f43880c1f5afea5fdcf28bd8ab56218a7200df7e714134c495ebd0e11a5b0e86"
#: The recorded identity of the finished coordinator, exactly as the store and owner tree hold it.
RECORDED_PID = 25005
RECORDED_PGID = 25005
RECORDED_STARTED_TICKS = 1790054976931255

RECORDED_RUN = Path(os.environ.get(
    "SO101_OWNER_FIX_RUN",
    "/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1",
))
RECORDED_STATE = RECORDED_RUN / "task12" / "service-runs" / "retryafterfix" / "state"
RECORDED_ENV = RECORDED_STATE.parent / "service-env.txt"

ROUTE = "/expert-validation/campaigns/{campaign_id}/full-restart-retries"


def _require_recorded_state() -> None:
    if not (RECORDED_STATE / "validation-service" / "supervisor.sqlite3").is_file():
        pytest.skip(f"recorded production state is not present at {RECORDED_STATE}")


def production_environment() -> dict:
    """The recorded production service environment, restricted to the layout keys."""

    environment = dict(os.environ)
    for line in RECORDED_ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("SO101_VALIDATION_"):
            key, _, value = line.partition("=")
            environment[key] = value
    return environment


def staged_state(tmp_path: Path) -> Path:
    """A private copy of the recorded service state: store, owner tree and the batch's bytes.

    The campaign bytes are copied here (unlike the endpoint-refusal replay, which deliberately
    stages only the store): this replay needs the receipt the admission gate reads, and that receipt
    is derived from ``bf16a``'s own verified journal. Nothing is ever written into the recorded run.
    """

    destination = (tmp_path / "state").resolve()
    destination.mkdir(parents=True)
    for name in ("validation-service", "owner-tree", "campaigns"):
        shutil.copytree(RECORDED_STATE / name, destination / name)
    return destination


@pytest.fixture()
def replay_session(tmp_path):
    from so101_teleop.expert_validation.production import create_production_service

    _require_recorded_state()
    service = create_production_service(staged_state(tmp_path), environment=production_environment())
    try:
        store = service.store
        # The replay has to be real: if restore could not rebind the recorded campaign, the endpoint
        # would refuse before the admission and these tests would pass for the wrong reason.
        assert service.get_campaign(CAMPAIGN_ID)["campaign_id"] == CAMPAIGN_ID
        # The receipt gate the previous fix repaired is passed here, by the batch's own bytes - the
        # refusal under test is the one *after* it.
        assert store.batch(BATCH_ID).cleanup_receipt_sha256 == CLEANUP_RECEIPT
        owner = store.owned_execution(BATCH_ID)
        assert (owner.state, owner.pid, owner.pgid, owner.started_ticks) == (
            "RUNNING", RECORDED_PID, RECORDED_PGID, RECORDED_STARTED_TICKS
        ), "the recorded condition is a RUNNING owner row whose process is gone"
        assert [item.state for item in store.retry_items(CAMPAIGN_ID)] == ["QUEUED"]
        # One lease, as in production: the console holds exactly one for the whole page session.
        authority = service.acquire_lease({"service_session_id": "retry-owner-reconcile-test"})
        yield SimpleNamespace(service=service, store=store, authority=authority)
    finally:
        service.store.close()


def console_body(session, command_id: str, point_ids=(POINT_ID,)) -> dict:
    """The body the console builds: the lease authority, one command id, the points, the phrase."""

    lease = session.authority
    return {
        "service_session_id": lease["service_session_id"],
        "lease_id": lease["lease_id"],
        "lease_generation": lease["generation"],
        "command_id": command_id,
        "point_ids": list(point_ids),
        "confirmation": "CONFIRM FULL_RESTART RETRIES",
    }


def post_retry(service, payload: dict):
    """POST in the caller's own thread: the store's connection is bound to the thread that made it."""

    import httpx

    from so101_teleop.expert_validation.api import create_expert_validation_app

    app = create_expert_validation_app(service)

    async def call():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://retry-owner-reconcile-test"
        ) as client:
            return await client.post(ROUTE.format(campaign_id=CAMPAIGN_ID), json=payload)

    return asyncio.run(call())


def _spawn_owner_process() -> subprocess.Popen:
    return subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(120)"],
        start_new_session=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _end_owner_process(process: subprocess.Popen, timeout: float = 5.0) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=timeout)


def test_the_console_retry_of_a_finished_first_pass_is_admitted_not_refused(replay_session, monkeypatch):
    """RED: this answered ``409 {"code": "RETRY_OWNER_ACTIVE"}`` for a first pass that had finished.

    The recorded row is exactly the one above: a RUNNING owner whose process is proven gone. The
    console request must now pass the owner gate and reach the one owner-spawn boundary - which this
    test refuses by name, because the point of the assertion is that the *admission* was granted,
    not that a real MuJoCo batch started inside a unit test.
    """

    from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor

    service, store = replay_session.service, replay_session.store

    async def refuse_the_spawn(self, request, *, owner_intent=None):
        raise RuntimeError("RETRY_SPAWN_REFUSED_BY_TEST")

    monkeypatch.setattr(ExpertValidationSupervisor, "_spawn", refuse_the_spawn)
    response = post_retry(service, console_body(replay_session, "retry-owner-reconcile-1"))

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "RETRY_SPAWN_REFUSED_BY_TEST", response.text

    retired = store.owned_execution(BATCH_ID)
    assert retired.state == "EXITED", "the finished owner is retired durably, not skipped once"
    assert (retired.pid, retired.pgid, retired.started_ticks) == (
        RECORDED_PID, RECORDED_PGID, RECORDED_STARTED_TICKS
    ), "retiring the row must not rewrite the identity it was proven from"

    items = store.retry_items(CAMPAIGN_ID)
    assert [(item.point_id, item.state, item.batch_id) for item in items] == [
        (POINT_ID, "RUNNING", "retry-001")
    ], "the admission transaction committed: the queue entry is bound to the retry batch"
    admissions = store.retry_admissions(CAMPAIGN_ID)
    assert [(row["batch_id"], row["point_id"]) for row in admissions] == [("retry-001", POINT_ID)]
    assert store.recovery_fence(CAMPAIGN_ID)["reason"] == (
        "RETRY_SPAWN_FAILED: RETRY_SPAWN_REFUSED_BY_TEST"
    ), "the run stopped at the spawn boundary this test raised from"


def test_a_live_recorded_owner_still_refuses_at_the_retry_admission(replay_session):
    """A live owner is never retired: ``RETRY_OWNER_ACTIVE`` is still the code, one gate deeper.

    The row is rewritten to name a process that really is running (the identity is read from the
    kernel), so this is the negative the fix must not lose.
    """

    service, store = replay_session.service, replay_session.store
    process = _spawn_owner_process()
    try:
        from so101_teleop.expert_validation.store import StoreConflict
        from so101_teleop.process_identity import read_identity

        identity = read_identity(process.pid)
        store._connection.execute(
            "UPDATE owned_execution SET pid=?, pgid=?, started_ticks=?, argv_sha256=? "
            "WHERE batch_id=?",
            (identity.pid, identity.pgid, identity.start_marker, identity.command_sha256, BATCH_ID),
        )
        request, context = service._production_retry_admission(
            CAMPAIGN_ID, POINT_ID, {"command_id": "retry-owner-live-1"}
        )
        with pytest.raises(StoreConflict, match="RETRY_OWNER_ACTIVE"):
            asyncio.run(
                service.supervisor.start_production_retry(request=request, context=context)
            )
        assert store.owned_execution(BATCH_ID).state == "RUNNING"
        assert [item.state for item in store.retry_items(CAMPAIGN_ID)] == ["QUEUED"]
        # The console's own gate agrees, one step earlier, and refuses without consuming anything.
        refused = post_retry(service, console_body(replay_session, "retry-owner-live-2"))
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "VALIDATION_RECOVERY_REQUIRED", refused.text
        assert store.retry_admissions(CAMPAIGN_ID) == ()
    finally:
        _end_owner_process(process)


def test_an_owner_identity_the_platform_will_not_report_still_refuses(replay_session):
    """Fail closed: a row whose identity cannot be read is never retired on assumption."""

    from so101_teleop import process_identity
    from so101_teleop.expert_validation.store import StoreConflict

    service, store = replay_session.service, replay_session.store

    def refuse(_pid):
        raise process_identity.ProcessIdentityError()

    original = process_identity.read_identity
    process_identity.read_identity = refuse
    try:
        request, context = service._production_retry_admission(
            CAMPAIGN_ID, POINT_ID, {"command_id": "retry-owner-unreadable-1"}
        )
        with pytest.raises(StoreConflict, match="RETRY_OWNER_ACTIVE"):
            asyncio.run(
                service.supervisor.start_production_retry(request=request, context=context)
            )
    finally:
        process_identity.read_identity = original

    assert store.owned_execution(BATCH_ID).state == "RUNNING"
    assert store.retry_admissions(CAMPAIGN_ID) == ()
