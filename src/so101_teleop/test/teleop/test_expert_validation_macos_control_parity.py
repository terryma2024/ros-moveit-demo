"""The macOS control endpoint must speak the service's wire exactly, and claim no more than it can.

Two implementations of one wire is a drift risk, so this file pins them against each other: the field
sets, the reply shape, the refusals, and the fact that an acknowledgement never authorizes a stop. The
Linux server is exercised from the other side by the control suite; this one is exercised by the
service's own client, exactly as a launched campaign would be.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import sys

import pytest

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # the control suite owns the short-root helper this file reuses
    sys.path.insert(0, str(HERE))

from test_expert_validation_control import _short_private_root  # noqa: E402

from so101_demo.parallel_batch import macos_control_endpoint as endpoint_module  # noqa: E402
from so101_demo.parallel_batch import web_control  # noqa: E402
from so101_teleop.expert_validation import control as service_control  # noqa: E402
from so101_teleop.expert_validation.control import (  # noqa: E402
    CleanupNotAuthorized,
    ControlProtocolError,
    CoordinatorControlClient,
    authorize_coordinator_stop,
)
from so101_teleop.expert_validation.coordinator import CoordinatorBinding  # noqa: E402

TOKEN = "7c" * 32


class StubCampaign:
    """The smallest honest stand-in: it owns one stop transition and one cleanup fact."""

    def __init__(self) -> None:
        self.stop_calls: list[str] = []
        self.terminal = False
        self.cleanup_complete = False

    def state(self) -> dict:
        return {
            "state": "TERMINAL" if self.terminal else "STOPPING" if self.stop_calls else "RUNNING",
            "batch_terminal": self.terminal,
            "batch_cleanup_complete": self.cleanup_complete,
        }

    def request_stop(self, command_id: str) -> None:
        self.stop_calls.append(command_id)


def _endpoint(root: Path, campaign: StubCampaign):
    # The service requires an absolute normalized batch root, so the short root is resolved first.
    root = Path(root).resolve()
    path = root / "c.sock"
    endpoint = endpoint_module.MacosFixedControlEndpoint(
        campaign_id="campaign-a",
        batch_id="batch-a",
        coordinator_epoch=1,
        path=path,
        control_token=TOKEN,
        state_provider=campaign.state,
        request_stop=campaign.request_stop,
    )
    binding = CoordinatorBinding(
        campaign_id="campaign-a",
        batch_id="batch-a",
        batch_root=root,
        control_socket=path,
        coordinator_epoch=1,
        control_token=TOKEN,
        control_token_sha256=hashlib.sha256(TOKEN.encode()).hexdigest(),
    )
    return endpoint, binding


def test_the_reply_shape_is_the_service_client_contract():
    """The endpoint's reply field set is compared to the client's, not to a copy of it."""
    campaign = StubCampaign()
    endpoint, _binding = _endpoint(_short_private_root("p"), campaign)
    request = {
        "schema_version": 1,
        "command_id": "status-1",
        "campaign_id": "campaign-a",
        "batch_id": "batch-a",
        "coordinator_epoch": 1,
        "operation": "STATUS",
        "request_sha256": "0" * 64,
        "control_token": TOKEN,
    }
    unsigned = {name: request[name] for name in web_control._UNSIGNED_FIELDS}
    import json

    request["request_sha256"] = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    reply = endpoint.reply_for(request)
    assert set(reply) == service_control._REPLY_FIELDS
    assert endpoint_module._REQUEST_FIELDS is web_control._REQUEST_FIELDS, (
        "the request field set must be the one the Linux server validates, not a second copy"
    )
    assert set(reply) == service_control._REPLY_FIELDS


def test_a_real_cancel_reaches_the_campaign_and_never_authorizes_a_stop():
    campaign = StubCampaign()
    root = _short_private_root("p")
    endpoint, binding = _endpoint(root, campaign)
    try:
        endpoint.start()
        client = CoordinatorControlClient()
        assert client.status(command_id="status-1", binding=binding).state == "RUNNING"
        result = client.cancel(command_id="cancel-1", binding=binding)
        assert result.state == "STOPPING"
        assert campaign.stop_calls == ["cancel-1"], "the durable stop must be requested exactly once"
        assert result.batch_cleanup_complete is False
        assert result.cleanup_receipt_sha256 is None
        with pytest.raises(CleanupNotAuthorized, match="BATCH_NOT_TERMINAL"):
            authorize_coordinator_stop(result, binding)

        campaign.terminal = True
        campaign.cleanup_complete = True
        terminal = client.status(command_id="status-2", binding=binding)
        assert terminal.state == "TERMINAL" and terminal.batch_terminal
        with pytest.raises(CleanupNotAuthorized, match="OWNED_DESCENDANTS_REMAIN"):
            authorize_coordinator_stop(terminal, binding)
    finally:
        endpoint.close()
    assert not binding.control_socket.exists(), "the endpoint removes only the socket it bound"


def test_the_endpoint_refuses_a_wrong_token_and_leaves_the_campaign_alone():
    campaign = StubCampaign()
    root = _short_private_root("p")
    endpoint, binding = _endpoint(root, campaign)
    wrong = CoordinatorBinding(
        campaign_id=binding.campaign_id,
        batch_id=binding.batch_id,
        batch_root=binding.batch_root,
        control_socket=binding.control_socket,
        coordinator_epoch=binding.coordinator_epoch,
        control_token="ff" * 32,
        control_token_sha256=hashlib.sha256(("ff" * 32).encode()).hexdigest(),
    )
    try:
        endpoint.start()
        with pytest.raises(ControlProtocolError):
            CoordinatorControlClient(timeout_s=1.0).cancel(command_id="cancel-bad", binding=wrong)
        assert campaign.stop_calls == []
    finally:
        endpoint.close()


def test_the_endpoint_creates_its_private_directory(tmp_path):
    """The service names `<batch_root>/control/control.sock`; nothing had created that directory.

    The first live launch of the adapter died exactly here with ``FileNotFoundError`` on
    ``os.open(self.path.parent)`` - after the service had already recorded the start - so the endpoint
    owns creating the directory, privately, and still verifies it before binding.
    """
    campaign = StubCampaign()
    root = _short_private_root("p").resolve()
    endpoint, binding = _endpoint(root, campaign)
    nested = root / "batch" / "control"
    endpoint.path = nested / "control.sock"
    binding = type(binding)(
        campaign_id=binding.campaign_id,
        batch_id=binding.batch_id,
        batch_root=root,
        control_socket=endpoint.path,
        coordinator_epoch=binding.coordinator_epoch,
        control_token=binding.control_token,
        control_token_sha256=binding.control_token_sha256,
    )
    assert not nested.exists()
    try:
        endpoint.start()
        assert nested.is_dir()
        assert oct(os.stat(nested).st_mode & 0o777) == "0o700"
        result = CoordinatorControlClient().cancel(command_id="cancel-nested", binding=binding)
        assert result.state == "STOPPING"
    finally:
        endpoint.close()


def test_the_endpoint_refuses_a_directory_that_is_not_private(tmp_path):
    campaign = StubCampaign()
    root = _short_private_root("p")
    endpoint, _binding = _endpoint(root, campaign)
    os.chmod(root, 0o755)
    try:
        with pytest.raises(Exception, match="CONTROL_SOCKET_DIRECTORY_MODE|PERMISSION|Permission"):
            endpoint.start()
    finally:
        endpoint.close()
        os.chmod(root, 0o700)


def test_the_endpoint_never_replaces_an_existing_endpoint():
    campaign = StubCampaign()
    root = _short_private_root("p")
    endpoint, binding = _endpoint(root, campaign)
    binding.control_socket.write_text("not a socket\n")
    try:
        with pytest.raises(OSError):
            endpoint.start()
        assert binding.control_socket.read_text() == "not a socket\n"
    finally:
        endpoint.close()
        binding.control_socket.unlink()
