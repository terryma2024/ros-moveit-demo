"""Task 15: the gateway is an allow-list, and a command without a service goes nowhere."""

import pytest

from so101_teleop.act_gateway import ALLOWED_COMMANDS, ActGateway


class _Service:
    def __init__(self):
        self.commands = []

    def command(self, name, payload):
        self.commands.append((name, payload))
        return {"name": name, "accepted": True}

    def status(self):
        return {"phase": "SEARCH", "remaining_s": 42.0, "cameras": {"head": True, "wrist": True}}


def test_gateway_rejects_arbitrary_command():
    with pytest.raises(ValueError):
        ActGateway(service=None).command("shell", {"command": "echo bad"})


def test_only_act_commands_reach_the_service():
    service = _Service()
    gateway = ActGateway(service)
    assert gateway.command("start", {"bundle": "b"})["accepted"] is True
    assert service.commands == [("start", {"bundle": "b"})]
    for name in ("shell", "exec", "", "START", None, 1):
        with pytest.raises(ValueError, match="ACT_COMMAND_NOT_ALLOWED"):
            gateway.command(name, {})
    assert len(service.commands) == 1                       # nothing else reached it
    assert gateway.status()["cameras"] == {"head": True, "wrist": True}
    assert tuple(ALLOWED_COMMANDS) == ("start", "resume", "stop", "status", "tick")


def test_a_missing_service_or_payload_is_refused_before_any_effect():
    with pytest.raises(ValueError, match="ACT_GATEWAY_SERVICE_UNAVAILABLE"):
        ActGateway(service=None).command("stop", {})
    with pytest.raises(ValueError, match="ACT_GATEWAY_SERVICE_UNAVAILABLE"):
        ActGateway(service=None).status()
    with pytest.raises(ValueError, match="ACT_COMMAND_PAYLOAD_REQUIRED"):
        ActGateway(_Service()).command("start", {})
    with pytest.raises(ValueError, match="ACT_COMMAND_PAYLOAD_INVALID"):
        ActGateway(_Service()).command("stop", ["not", "a", "mapping"])
    with pytest.raises(ValueError, match="ACT_GATEWAY_SERVICE_UNAVAILABLE"):
        ActGateway(object()).command("stop", {})            # a service that cannot command is no service

    class _Mute:
        def command(self, name, payload):
            return "not a mapping"

        def status(self):
            return None

    with pytest.raises(ValueError, match="ACT_GATEWAY_OUTCOME_INVALID"):
        ActGateway(_Mute()).command("stop", {})
    with pytest.raises(ValueError, match="ACT_GATEWAY_OUTCOME_INVALID"):
        ActGateway(_Mute()).status()
