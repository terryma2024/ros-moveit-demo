"""A retry POST answers a typed refusal or an admitted run - never a Python exception message.

Recorded production defect (``$RUN/task12/retry-samepage-20260922T043538Z``): the console held the
instance authority, selected the genuinely ``FAILED`` point of the terminal-clean first pass,
confirmed, and POSTed its own body to
``POST /expert-validation/campaigns/{id}/full-restart-retries``. The service answered

    409 {"code": "cannot unpack non-iterable RetryStartRequest object"}

because ``production.py`` unpacked ``request, context = self._production_retry_admission(...)``
while that helper returned only the ``RetryStartRequest``. The leaked text became the console's
"campaign", which is why every later poll asked for ``GET /expert-validation/campaigns/undefined``.

The same boundary echoed the text of any other internal exception as well, so these tests pin three
independent properties:

* the console's own body shape reaches the admission and comes back with a *typed* code (or starts);
* a half-formed request is refused by name, and a shape error stays a shape error;
* no unexpected exception can cross this boundary as text.

Every case that used to replay a recorded production store now composes the whole production
environment inside ``tmp_path`` through :mod:`retry_fixture`, so the same assertions execute on any
host: no recorded directory has to exist for them to run, and the only boundary this file
intercepts is the supervisor's final ``_spawn``.
"""

from __future__ import annotations

import asyncio
import re

import pytest

from retry_fixture import (
    CAMPAIGN_ID,
    POINT_ID,
    build_retry_session,
)

ROUTE = "/expert-validation/campaigns/{campaign_id}/full-restart-retries"

#: Every code the retry endpoint can name. The admission is unchanged - this is the vocabulary the
#: console may render, and a code outside it means an exception leaked instead of a refusal.
RETRY_REFUSAL_CODES = frozenset({
    # The route's own guard and the context-kind dispatch.
    "CONFIRMATION_REQUIRED",
    "EXECUTION_CONTEXT_KIND_INVALID",
    "CANDIDATE_CONTEXT_REQUIRED",
    "CANDIDATE_CONTEXT_UNKNOWN",
    "CANDIDATE_CONTEXT_EXPIRED",
    "CANDIDATE_CONTEXT_ON_PRODUCTION_ENDPOINT",
    "PRODUCTION_CONTEXT_ON_CANDIDATE_ENDPOINT",
    "CANDIDATE_RETRY_UNAVAILABLE",
    "CANDIDATE_COMMAND_MISMATCH",
    # The production retry endpoint and its durable origin.
    "VALIDATION_CAMPAIGN_NOT_FOUND",
    "VALIDATION_RECOVERY_REQUIRED",
    "VALIDATION_MANIFEST_NOT_FOUND",
    "RETRY_ONE_POINT_PER_COMMAND",
    "RETRY_LEASE_REQUIRED",
    "RETRY_NOT_QUEUED",
    "RETRY_ORIGINAL_RESULT_UNKNOWN",
    "CAMPAIGN_FIRST_PASS_MISSING",
    "UNSUPPORTED_ON_MACOS",
    "CONTEXT_PROFILE_INVALID",
    "COMMAND_ID_REUSED",
    # The live lease that authorizes one retry context.
    "LEASE_NOT_ACTIVE",
    "LEASE_IDENTITY_MISMATCH",
    "STALE_LEASE_GENERATION",
    "LEASE_EXPIRED",
    "LEASE_ALREADY_HELD",
    "SERVICE_SESSION_ID",
    "ACTIVE_CAMPAIGN",
    # The supervisor's one-spawn boundary.
    "RETRY_PRODUCTION_CONTEXT_REQUIRED",
    "RETRY_REQUEST_INVALID",
    "RETRY_ORIGINAL_REQUEST_UNKNOWN",
    "RETRY_BATCH_ROOT_MISMATCH",
    "RETRY_PROFILE_MISMATCH",
    "RETRY_ORIGINAL_BATCH_UNKNOWN",
    "RETRY_ORIGINAL_BATCH_SELF",
    "RETRY_BINDING_UNRESOLVED",
    "RETRY_CLEANUP_INCOMPLETE",
    "RETRY_CLEANUP_BINDING_MISMATCH",
    "RETRY_EXECUTION_STILL_RUNNING",
    "RETRY_EXECUTION_FAILED",
    "RETRY_EXECUTION_TIMEOUT",
    "COMMAND_OUTCOME_UNKNOWN",
    # The store's single admission transaction.
    "RETRY_CAMPAIGN_UNKNOWN",
    "RETRY_CAMPAIGN_MISMATCH",
    "RETRY_BATCH_MISMATCH",
    "RETRY_BATCH_EXISTS",
    "RETRY_SCHEMA_MISMATCH",
    "RETRY_BATCH_KIND_MISMATCH",
    "RETRY_WORKER_COUNT_MISMATCH",
    "RETRY_CONFIG_MISMATCH",
    "RETRY_RUNTIME_CLOSURE_MISMATCH",
    "RETRY_EVIDENCE_ROOT_MISMATCH",
    "RETRY_OWNER_GENERATION_MISMATCH",
    "RETRY_PROFILE_INVALID",
    "RETRY_CONTEXT_KIND",
    "RETRY_CONTEXT_EXPIRED",
    "RETRY_INSTALL_BINDING_MISMATCH",
    "RETRY_LEASE_MISMATCH",
    "RETRY_LEASE_EXPIRED",
    "RETRY_SPAWN_INTENT_INVALID",
    "RETRY_COMMAND_ALREADY_CONSUMED",
    "RETRY_COMMAND_ID_REUSED",
    "RETRY_MANIFEST_MISMATCH",
    "RETRY_MANIFEST_UNKNOWN",
    "RETRY_ORIGINAL_BATCH_MISMATCH",
    "RETRY_ORIGINAL_CLEANUP_INCOMPLETE",
    "RETRY_ORIGINAL_SELECTION_MISMATCH",
    "RETRY_ORIGINAL_POINT_UNKNOWN",
    "RETRY_ORIGINAL_UNRUN",
    "RETRY_ORIGINAL_INDETERMINATE",
    "RETRY_ORIGINAL_NOT_FAILED",
    "RETRY_ORIGINAL_INVALID",
    "RETRY_ORIGINAL_INFRA_FAILED",
    "RETRY_ORIGINAL_NOT_TERMINAL",
    "RETRY_ORIGINAL_RESULT_MISMATCH",
    "RETRY_RECOVERY_FENCE",
    "RETRY_OWNER_ACTIVE",
    "RETRY_OWNER_UNKNOWN",
    "RETRY_MAX_RUNS_EXCEEDED",
    # The boundary's own answer when the fault was not a typed refusal at all.
    "VALIDATION_INTERNAL_ERROR",
})

#: What a typed refusal looks like: one stable token, optionally one named detail. An interpreter
#: message ("cannot unpack non-iterable RetryStartRequest object") is not one.
_CODE = re.compile(r"^[A-Z][A-Z0-9_]*(?:: [^\n]{1,200})?$")
_LEAKED_PYTHON_TEXT = (
    "cannot unpack",
    "non-iterable",
    "Traceback (most recent call last)",
    "object has no attribute",
    "takes no arguments",
    "positional argument",
)

#: The refusal this file's own spawn boundary raises. It is not a service code: it only has to be a
#: single stable token, which is what proves the admission was granted and the boundary was reached.
SPAWN_REFUSED = "RETRY_SPAWN_REFUSED_BY_TEST"


@pytest.fixture()
def production_session(tmp_path):
    """The whole production composition for one test, built entirely inside ``tmp_path``."""

    session = build_retry_session(tmp_path, session_id="retry-endpoint-refusal-test")
    try:
        # The composition has to be real: if restore could not rebind this campaign, the endpoint
        # would refuse before the admission and these tests would pass for the wrong reason.
        assert session.service.get_campaign(CAMPAIGN_ID)["campaign_id"] == CAMPAIGN_ID
        assert session.store.batch(session.batch_id).cleanup_receipt_sha256 is not None, (
            "the first pass's own verified cleanup frame is what admits a retry of its failed point"
        )
        assert [item.point_id for item in session.store.retry_items(CAMPAIGN_ID)] == [POINT_ID]
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


def post_retry(service, campaign_id: str, payload: dict):
    """POST in the caller's own thread: the store's connection is bound to the thread that made it.

    ``TestClient`` dispatches through a worker thread, where every store read is a ``sqlite3``
    ``ProgrammingError`` - itself a leaked internal message, which the guard test below covers.
    """

    import httpx

    from so101_teleop.expert_validation.api import create_expert_validation_app

    app = create_expert_validation_app(service)

    async def call():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://retry-refusal-test"
        ) as client:
            return await client.post(ROUTE.format(campaign_id=campaign_id), json=payload)

    return asyncio.run(call())


def assert_typed(response, *, injected=()) -> dict:
    """The body carries a refusal code from the endpoint's own vocabulary, and nothing leaked.

    ``injected`` names codes a test's own intercepted boundary raises. Those are still required to
    be a single stable token, but they are not service vocabulary and are never treated as one.
    """

    payload = response.json()
    assert response.status_code in {200, 409}, response.text
    for leaked in _LEAKED_PYTHON_TEXT:
        assert leaked not in response.text, response.text
    if response.status_code == 200:
        assert payload["campaign_id"] == CAMPAIGN_ID
        return payload
    assert _CODE.match(payload["code"]), payload
    if payload["code"] not in injected:
        assert payload["code"] in RETRY_REFUSAL_CODES, payload
    return payload


def _refuse_the_spawn(monkeypatch, code: str = SPAWN_REFUSED) -> list:
    """Intercept the one external process boundary, and record whether it was reached at all."""

    from so101_teleop.expert_validation.supervisor import ExpertValidationSupervisor

    calls: list = []

    async def refuse(self, request, *, owner_intent=None):
        calls.append(request)
        raise RuntimeError(code)

    monkeypatch.setattr(ExpertValidationSupervisor, "_spawn", refuse)
    return calls


def test_the_console_retry_body_is_answered_with_a_typed_code(production_session, monkeypatch):
    """RED: this returned ``{"code": "cannot unpack non-iterable RetryStartRequest object"}``."""

    session = production_session
    calls = _refuse_the_spawn(monkeypatch)

    response = post_retry(
        session.service, CAMPAIGN_ID, console_body(session, "retry-endpoint-1")
    )

    payload = assert_typed(response, injected=(SPAWN_REFUSED,))
    # The console's body is admissible here - the first pass really is terminal-clean and its
    # failed point really is queued - so it reaches the spawn boundary, and the answer is that
    # boundary's own single-token code rather than a Python detail. The point of the assertion is
    # that the admission *ran*: the pair was built, the transaction committed, one spawn happened.
    assert payload["code"] == SPAWN_REFUSED, payload
    assert len(calls) == 1, calls
    admissions = session.store.retry_admissions(CAMPAIGN_ID)
    assert [(row["batch_id"], row["point_id"]) for row in admissions] == [
        ("retry-001", POINT_ID)
    ], "the admission transaction committed before the spawn boundary was reached"


def test_the_console_retry_body_is_refused_by_name_when_cleanup_never_committed(
    tmp_path, monkeypatch
):
    """The console's own body, answered with a code from its vocabulary, for a first pass that
    never committed cleanup: the admission refuses by name instead of reaching the boundary."""

    session = build_retry_session(
        tmp_path, cleanup_complete=None, session_id="retry-endpoint-refusal-no-cleanup"
    )
    try:
        assert session.store.batch(session.batch_id).cleanup_receipt_sha256 is None
        calls = _refuse_the_spawn(monkeypatch)

        response = post_retry(
            session.service, CAMPAIGN_ID, console_body(session, "retry-endpoint-cleanup-1")
        )

        payload = assert_typed(response)
        assert payload["code"] == "RETRY_ORIGINAL_CLEANUP_INCOMPLETE", payload
        assert calls == [], "no process may be spawned for a first pass that never cleaned up"
        assert session.store.retry_admissions(CAMPAIGN_ID) == ()
    finally:
        session.close()


def test_a_half_formed_retry_request_is_refused_by_name(production_session):
    """A mismatched point and a missing phrase are refusals; a malformed shape is a shape error."""

    session = production_session
    service = session.service
    mismatched = post_retry(
        service,
        CAMPAIGN_ID,
        console_body(session, "retry-endpoint-2", point_ids=("sample_99_absent",)),
    )
    assert assert_typed(mismatched)["code"] == "RETRY_NOT_QUEUED"

    unconfirmed = console_body(session, "retry-endpoint-3")
    unconfirmed["confirmation"] = "yes"
    assert assert_typed(post_retry(service, CAMPAIGN_ID, unconfirmed))["code"] == (
        "CONFIRMATION_REQUIRED"
    )

    incomplete = console_body(session, "retry-endpoint-4")
    del incomplete["point_ids"]
    response = post_retry(service, CAMPAIGN_ID, incomplete)
    assert response.status_code == 422, response.text
    assert "cannot unpack" not in response.text and "Traceback" not in response.text

    foreign = {**console_body(session, "retry-endpoint-5"), "point_count": 20}
    response = post_retry(service, CAMPAIGN_ID, foreign)
    assert response.status_code == 422, response.text


def test_an_unexpected_internal_error_is_not_echoed_to_the_console():
    """A Python detail is not a contract: an untyped fault answers with the boundary's own code."""

    class Exploding:
        def retry_campaign_api(self, campaign_id, body):
            raise TypeError("cannot unpack non-iterable RetryStartRequest object")

    response = post_retry(Exploding(), CAMPAIGN_ID, {
        "service_session_id": "s", "lease_id": "l", "lease_generation": 1,
        "command_id": "exploding-1", "point_ids": [POINT_ID],
        "confirmation": "CONFIRM FULL_RESTART RETRIES",
    })

    assert response.status_code == 409, response.text
    assert response.json()["code"] == "VALIDATION_INTERNAL_ERROR", response.text


def test_the_retry_admission_returns_the_request_and_its_registered_context(production_session):
    """The caller's contract: one admission yields the request *and* the context that authorizes it.

    Asserted against the composed production service rather than a hand-built double, so the pair is
    the one the real restore, the real manifest geometry and the real lease produce.
    """

    from so101_teleop.expert_validation.execution_context import (
        ProductionExecutionContext,
        RETRY_BATCH_KIND,
        RETRY_WORKER_COUNT,
    )
    from so101_teleop.expert_validation.models import RetryStartRequest

    session = production_session
    service = session.service

    result = service._production_retry_admission(
        CAMPAIGN_ID, POINT_ID, {"command_id": "cmd-admission-1"}
    )

    assert isinstance(result, tuple) and len(result) == 2, (
        "the retry endpoint unpacks (request, context); one returned value is a TypeError at the "
        f"boundary - got {result!r}"
    )
    request, context = result
    assert isinstance(request, RetryStartRequest)
    assert isinstance(context, ProductionExecutionContext)
    assert (request.campaign_id, request.point_id) == (CAMPAIGN_ID, POINT_ID)
    assert (request.batch_id, request.original_batch_id) == ("retry-001", session.batch_id)
    assert (request.batch_kind, request.worker_count) == (RETRY_BATCH_KIND, RETRY_WORKER_COUNT)
    assert context.schema_version == request.schema_version
    assert (context.lease_id, context.lease_generation) == (
        session.authority["lease_id"], session.authority["generation"]
    )
    assert (request.lease_id if hasattr(request, "lease_id") else context.lease_id) == (
        session.authority["lease_id"]
    )
    assert str(request.install_prefix) == service._campaign_requests[CAMPAIGN_ID].install_prefix
    assert request.original_result_sha256 == session.store.read_projection_state(
        session.batch_id
    ).state.points[POINT_ID].result_sha256


def test_linux_retry_admission_binds_the_original_installed_v3_document(production_session):
    """On Linux the restored request names no profile, so the v3 document *is* the retry's binding.

    The task-local document is a byte copy of this repository's real v3 document, and the admission
    re-hashes it against the digest the restored request carries: the retry executes exactly the
    bytes the first pass executed, or it refuses.
    """

    from so101_teleop.expert_validation.execution_context import LINUX_RETRY_PROFILE
    from so101_teleop.expert_validation.production import _sha256
    from so101_teleop.expert_validation.service import ServiceConflict

    session = production_session
    service = session.service
    restored = service._campaign_requests[CAMPAIGN_ID]
    document = restored.parallel_config_path
    assert restored.execution_profile is None, "the receipt named no profile: this is the v3 path"

    request, context = service._production_retry_admission(
        CAMPAIGN_ID, POINT_ID, {"command_id": "cmd-linux-1"}
    )

    assert (request.execution_profile, context.execution_profile) == (
        LINUX_RETRY_PROFILE, LINUX_RETRY_PROFILE,
    )
    assert (request.schema_version, context.schema_version) == (3, 3)
    assert request.config_sha256 == _sha256(document) == restored.parallel_config_sha256

    # The control: the same admission refuses the moment those bytes stop matching the digest the
    # restored request bound, so the equality above is a real verification and not a restatement.
    document.write_text(document.read_text(encoding="utf-8") + "\n# drifted\n", encoding="utf-8")
    with pytest.raises(ServiceConflict, match="RETRY_CONFIG_HASH_MISMATCH"):
        service._production_retry_admission(CAMPAIGN_ID, POINT_ID, {"command_id": "cmd-linux-2"})
