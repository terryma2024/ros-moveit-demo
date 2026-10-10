"""Task 15: the ACT routes exist, are gated, and refuse rather than inventing a session."""

import asyncio
from types import SimpleNamespace

import pytest

from so101_teleop.unified.app import act_router


class _Service:
    def __init__(self, *, ok=True):
        self.ok = ok
        self.calls = []

    def command(self, name, payload):
        self.calls.append((name, payload))
        return {"name": name, "accepted": self.ok}

    def status(self):
        return {"phase": "SEARCH", "remaining_s": 5.0, "cameras": {"head": True, "wrist": True}}


def _handlers(service):
    router = act_router(SimpleNamespace(act_gateway_service=service))
    paths = [route.path for route in router.routes]
    endpoints = {route.path: route.endpoint for route in router.routes}
    return paths, endpoints


def test_the_act_routes_are_declared_on_the_unified_router():
    paths, _endpoints = _handlers(_Service())
    assert paths == ["/act/status", "/act/command"]


def test_status_and_command_delegate_through_the_allow_list():
    paths, endpoints = _handlers(_Service())
    assert paths[0] == "/act/status"
    status = asyncio.run(endpoints["/act/status"]())
    assert status["phase"] == "SEARCH"
    accepted = asyncio.run(endpoints["/act/command"](
        {"name": "start", "payload": {"bundle": "b"}}))
    assert accepted["accepted"] is True


def test_a_refused_command_answers_503_rather_than_reaching_the_service():
    service = _Service()
    _paths, endpoints = _handlers(service)
    refused = asyncio.run(endpoints["/act/command"](
        {"name": "shell", "payload": {"command": "echo bad"}}))
    assert refused.status_code == 503
    assert service.calls == []                       # the gateway refused before the service saw it


def test_no_service_means_no_session_rather_than_a_crash():
    _paths, endpoints = _handlers(None)
    missing = asyncio.run(endpoints["/act/status"]())
    assert missing.status_code == 503
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        asyncio.run(endpoints["/act/command"]({"payload": {}}))
