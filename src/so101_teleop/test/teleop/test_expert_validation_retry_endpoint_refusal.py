"""A retry POST answers a typed refusal or an admitted run - never a Python exception message.

Recorded production defect (``$RUN/task12/retry-samepage-20260922T043538Z``): the console held the
instance authority, selected the genuinely ``FAILED`` point ``sample_05_near_center`` of the
terminal-clean first pass ``b889e``, confirmed, and POSTed its own body to
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

The first two replay the recorded production store (copied, never written in place) and compose the
service through ``create_production_service`` with the recorded production environment, so no live
MuJoCo station is needed. The last two are self-contained.
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from pathlib import Path
from types import SimpleNamespace

import pytest

CAMPAIGN_ID = "campaign-e15544c0506e47b198bc907433d3ae37"
POINT_ID = "sample_05_near_center"
RECORDED_RUN = Path(os.environ.get(
    "SO101_RETRY_FIX_RUN",
    "/tmp/so101-debug-macos-service-campaign-closure-2208b154-6e9f-4ae1-a448-1fa0101df9b1",
))
RECORDED_STATE = RECORDED_RUN / "task12" / "service-runs" / "retrysamepage" / "state"
RECORDED_ENV = RECORDED_STATE.parent / "service-env.txt"

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
    """A private copy of the recorded service state: the store plus the owner tree.

    The campaign evidence tree is deliberately not copied - it is 124 MB of batch journal and the
    retry admission reads the durable projection from the store - and nothing is ever written into
    the recorded evidence root.
    """

    destination = (tmp_path / "state").resolve()
    destination.mkdir(parents=True)
    shutil.copytree(RECORDED_STATE / "validation-service", destination / "validation-service")
    shutil.copytree(RECORDED_STATE / "owner-tree", destination / "owner-tree")
    return destination


@pytest.fixture()
def production_session(tmp_path):
    from so101_teleop.expert_validation.production import create_production_service

    _require_recorded_state()
    service = create_production_service(staged_state(tmp_path), environment=production_environment())
    try:
        # The replay has to be real: if restore could not rebind the recorded campaign, the endpoint
        # would refuse before the admission and this test would pass for the wrong reason.
        assert service.get_campaign(CAMPAIGN_ID)["campaign_id"] == CAMPAIGN_ID
        # One lease, as in production: the console holds exactly one for the whole page session.
        authority = service.acquire_lease({"service_session_id": "retry-endpoint-refusal-test"})
        yield SimpleNamespace(service=service, authority=authority)
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


def assert_typed(response) -> dict:
    """The body carries a refusal code from the endpoint's own vocabulary, and nothing leaked."""

    payload = response.json()
    assert response.status_code in {200, 409}, response.text
    for leaked in _LEAKED_PYTHON_TEXT:
        assert leaked not in response.text, response.text
    if response.status_code == 200:
        assert payload["campaign_id"] == CAMPAIGN_ID
        return payload
    assert _CODE.match(payload["code"]), payload
    assert payload["code"] in RETRY_REFUSAL_CODES, payload
    return payload


def test_the_console_retry_body_is_answered_with_a_typed_code(production_session):
    """RED: this returned ``{"code": "cannot unpack non-iterable RetryStartRequest object"}``."""

    response = post_retry(
        production_session.service,
        CAMPAIGN_ID,
        console_body(production_session, "retry-endpoint-1"),
    )

    payload = assert_typed(response)
    # The admission refuses by name. This fixture stages the recorded store without the campaign's
    # batch bytes (``staged_state`` copies the store, not the 124 MB journal), so no cleanup receipt
    # can be derived here and ``RETRY_ORIGINAL_CLEANUP_INCOMPLETE`` is the refusal this replay still
    # earns. Recording the receipt from the batch's own verified cleanup bytes - which is what turns
    # this refusal into an admission for a first pass that really is terminal-clean - is covered by
    # ``test_expert_validation_campaign_layout_projection``. The point of the assertion is that the
    # admission *ran*: the request/context pair was built and reached the store's transaction
    # instead of failing on an unpack.
    assert payload["code"] == "RETRY_ORIGINAL_CLEANUP_INCOMPLETE"


def test_a_half_formed_retry_request_is_refused_by_name(production_session):
    """A mismatched point and a missing phrase are refusals; a malformed shape is a shape error."""

    service = production_session.service
    mismatched = post_retry(
        service,
        CAMPAIGN_ID,
        console_body(production_session, "retry-endpoint-2", point_ids=("sample_99_absent",)),
    )
    assert assert_typed(mismatched)["code"] == "RETRY_NOT_QUEUED"

    unconfirmed = console_body(production_session, "retry-endpoint-3")
    unconfirmed["confirmation"] = "yes"
    assert assert_typed(post_retry(service, CAMPAIGN_ID, unconfirmed))["code"] == (
        "CONFIRMATION_REQUIRED"
    )

    incomplete = console_body(production_session, "retry-endpoint-4")
    del incomplete["point_ids"]
    response = post_retry(service, CAMPAIGN_ID, incomplete)
    assert response.status_code == 422, response.text
    assert "cannot unpack" not in response.text and "Traceback" not in response.text

    foreign = {**console_body(production_session, "retry-endpoint-5"), "point_count": 20}
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


def test_the_retry_admission_returns_the_request_and_its_registered_context():
    """The caller's contract: one admission yields the request *and* the context that authorizes it."""

    from so101_teleop.expert_validation.execution_context import (
        ProductionExecutionContext,
        RETRY_PROFILE,
        RETRY_SCHEMA_VERSION,
    )
    from so101_teleop.expert_validation.models import RetryStartRequest
    from so101_teleop.expert_validation.production import ProductionExpertValidationService

    install_prefix = Path("/opt/so101/install")
    evidence_root = Path("/evidence/campaigns")
    service = object.__new__(ProductionExpertValidationService)
    service.store = SimpleNamespace(
        current_lease=lambda: {
            "lease_id": "lease-1", "service_session_id": "session-1", "generation": 7,
            "expires_monotonic_ns": 2**62,
        },
        campaign_batches=lambda _campaign_id: [
            SimpleNamespace(batch_kind="FIRST_PASS", batch_id="b889e")
        ],
    )
    service._retry_origin = lambda campaign_id, point_id: (
        SimpleNamespace(
            install_prefix=install_prefix, evidence_root=evidence_root, manifest_id="manifest-1"
        ),
        SimpleNamespace(ordinal=0, point_id=point_id),
        "1" * 64,
        "2" * 64,
        "3" * 64,
    )
    service.register_production_context = lambda context: context
    service._installed_profile_document = lambda _profile: SimpleNamespace(config_sha256="4" * 64)

    result = service._production_retry_admission(CAMPAIGN_ID, POINT_ID, {"command_id": "cmd-1"})

    assert isinstance(result, tuple) and len(result) == 2, (
        "the retry endpoint unpacks (request, context); one returned value is a TypeError at the "
        f"boundary - got {result!r}"
    )
    request, context = result
    assert isinstance(request, RetryStartRequest)
    assert isinstance(context, ProductionExecutionContext)
    assert (request.campaign_id, request.point_id) == (CAMPAIGN_ID, POINT_ID)
    assert request.execution_profile == RETRY_PROFILE
    assert context.schema_version == RETRY_SCHEMA_VERSION
    assert (context.lease_id, context.lease_generation) == ("lease-1", 7)
    assert request.install_prefix == install_prefix


def test_linux_retry_admission_binds_the_original_installed_v3_document(monkeypatch):
    from so101_teleop.expert_validation import production
    from so101_teleop.expert_validation.execution_context import LINUX_RETRY_PROFILE

    document = Path(__file__).resolve().parents[3] / "so101_demo_py/config/mujoco/parallel_batch_v3.yaml"
    service = object.__new__(production.ProductionExpertValidationService)
    service.store = SimpleNamespace(
        current_lease=lambda: {
            "lease_id": "lease-1", "service_session_id": "session-1", "generation": 1,
            "expires_monotonic_ns": 2**62,
        },
        campaign_batches=lambda _campaign_id: [
            SimpleNamespace(batch_kind="FIRST_PASS", batch_id="b889e")
        ],
    )
    service._retry_origin = lambda _campaign_id, point_id: (
        SimpleNamespace(
            install_prefix=Path("/opt/so101/install"),
            evidence_root=Path("/evidence/campaigns"),
            manifest_id="manifest-1",
            execution_profile=None,
            parallel_config_path=document,
            parallel_config_sha256=production._sha256(document),
        ),
        SimpleNamespace(ordinal=0, point_id=point_id),
        "1" * 64, "2" * 64, "3" * 64,
    )
    service.register_production_context = lambda context: context
    monkeypatch.setattr(production.sys, "platform", "linux")

    request, context = service._production_retry_admission(
        CAMPAIGN_ID, POINT_ID, {"command_id": "cmd-linux-1"}
    )

    assert (request.execution_profile, context.execution_profile) == (
        LINUX_RETRY_PROFILE, LINUX_RETRY_PROFILE,
    )
    assert (request.schema_version, context.schema_version) == (3, 3)
    assert request.config_sha256 == production._sha256(document)
