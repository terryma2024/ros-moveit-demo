"""Task 15: the ACT gateway behind the teleop panel.

The panel and the headless CLI must drive the same session through the same service, so the gateway is an
allow-list rather than a pass-through: a name that is not an ACT command is refused before anything else is
consulted, and with no service there is nothing to command.
"""

from __future__ import annotations

ALLOWED_COMMANDS = ("start", "resume", "stop", "status", "tick")
_PAYLOAD_REQUIRED = {"start", "resume"}


class ActGateway:
    """Commands one ACT session through the unified service."""

    def __init__(self, service: object) -> None:
        self.service = service

    def command(self, name: str, payload: dict | None = None) -> dict:
        if name not in ALLOWED_COMMANDS:
            # an arbitrary command (a shell, say) is not an ACT command, whatever the caller intends
            raise ValueError("ACT_COMMAND_NOT_ALLOWED")
        payload = {} if payload is None else payload
        if not isinstance(payload, dict):
            raise ValueError("ACT_COMMAND_PAYLOAD_INVALID")
        if name in _PAYLOAD_REQUIRED and not payload:
            raise ValueError("ACT_COMMAND_PAYLOAD_REQUIRED")
        if self.service is None:
            raise ValueError("ACT_GATEWAY_SERVICE_UNAVAILABLE")
        handler = getattr(self.service, "command", None)
        if not callable(handler):
            raise ValueError("ACT_GATEWAY_SERVICE_UNAVAILABLE")
        outcome = handler(name, payload)
        if not isinstance(outcome, dict):
            raise ValueError("ACT_GATEWAY_OUTCOME_INVALID")
        return outcome

    def status(self) -> dict:
        """The panel's read path: the session state, or a refusal when there is no service."""

        if self.service is None:
            raise ValueError("ACT_GATEWAY_SERVICE_UNAVAILABLE")
        reader = getattr(self.service, "status", None)
        if not callable(reader):
            raise ValueError("ACT_GATEWAY_SERVICE_UNAVAILABLE")
        state = reader()
        if not isinstance(state, dict):
            raise ValueError("ACT_GATEWAY_OUTCOME_INVALID")
        return state
