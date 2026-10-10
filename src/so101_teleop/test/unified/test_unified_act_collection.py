"""Task 15: the unified ACT collection path, from the command route to the service.

The panel and the headless CLI are meant to drive the same session through the same service, so these tests
follow one command from the HTTP route through the allow-list to the service, and check that a refused or
ungated request stops before it can reach anything.
"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from so101_teleop.act_gateway import ActGateway
from so101_teleop.unified.app import act_router


class _CollectionService:
    """A unified service stand-in that records what the gateway asked it to do."""

    def __init__(self, *, refuse=False):
        self.commands = []
        self.refuse = refuse

    def command(self, name, payload):
        self.commands.append((name, payload))
        if self.refuse:
            raise ValueError("ACT_SESSION_NOT_ADMITTED")
        return {"name": name, "accepted": True, "session_id": payload.get("session_id", "")}

    def status(self):
        return {"phase": "RECORD", "remaining_s": 88.0,
                "cameras": {"head": True, "wrist": True}, "outcome": None}


def _endpoints(service):
    router = act_router(SimpleNamespace(act_gateway_service=service))
    return {route.path: route.endpoint for route in router.routes}, router


def test_the_collection_command_route_reaches_the_service_through_the_allow_list():
    service = _CollectionService()
    endpoints, _router = _endpoints(service)
    accepted = asyncio.run(endpoints["/act/command"](
        {"name": "start", "payload": {"session_id": "session-1", "bundle": "bundle.json"}}))
    assert accepted == {"name": "start", "accepted": True, "session_id": "session-1"}
    assert service.commands == [("start", {"session_id": "session-1", "bundle": "bundle.json"})]
    status = asyncio.run(endpoints["/act/status"]())
    assert status["phase"] == "RECORD" and status["remaining_s"] == 88.0


def test_a_command_outside_the_allow_list_never_reaches_a_collection_service():
    service = _CollectionService()
    endpoints, _router = _endpoints(service)
    for name in ("shell", "exec", "collect-anything", ""):
        refused = asyncio.run(endpoints["/act/command"]({"name": name, "payload": {}}))
        assert refused.status_code == 503
    assert service.commands == []                    # nothing was collected, nothing was commanded


def test_a_service_refusal_is_reported_without_a_session_leaking_out():
    service = _CollectionService(refuse=True)
    endpoints, _router = _endpoints(service)
    # `start` needs a payload, so give it one: the point here is the service's refusal, not the schema
    refused = asyncio.run(endpoints["/act/command"](
        {"name": "start", "payload": {"session_id": "session-1"}}))
    assert refused.status_code == 503
    assert "ACT_SESSION_NOT_ADMITTED" in refused.body.decode()
    assert service.commands == [("start", {"session_id": "session-1"})]


def test_the_routes_are_authority_gated_and_a_bad_body_is_a_schema_error():
    _endpoints_dict, router = _endpoints(_CollectionService())
    # every ACT route carries the teleop authority dependency, so the collection path is not ungated
    assert router.dependencies, "the ACT router must carry an authority dependency"
    for route in router.routes:
        assert route.dependencies or router.dependencies
    endpoints, _router = _endpoints(_CollectionService())
    with pytest.raises(HTTPException) as error:
        asyncio.run(endpoints["/act/command"]({"payload": {}}))
    assert error.value.status_code == 422


def test_the_gateway_alone_refuses_everything_when_no_service_is_wired():
    gateway = ActGateway(None)
    with pytest.raises(ValueError, match="ACT_GATEWAY_SERVICE_UNAVAILABLE"):
        gateway.command("start", {"bundle": "b"})
    with pytest.raises(ValueError, match="ACT_COMMAND_NOT_ALLOWED"):
        gateway.command("shell", {"command": "echo bad"})
