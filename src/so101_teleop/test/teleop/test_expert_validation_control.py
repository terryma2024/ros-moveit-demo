from dataclasses import replace
import hashlib
import json
from pathlib import Path

import pytest

from so101_teleop.expert_validation.control import (
    AdaptiveStatus,
    AdaptiveWrapperControl,
    BatchCleanupAuthorization,
    CleanupNotAuthorized,
    ControlProtocolError,
    CoordinatorControlClient,
    authorize_coordinator_stop,
    decode_frame,
    encode_frame,
)
from so101_teleop.expert_validation.coordinator import CoordinatorBinding
from so101_teleop.expert_validation.process_owner import OwnedAdaptiveWrapper


def _binding(tmp_path, epoch=4):
    token = "secret-token"
    return CoordinatorBinding(
        campaign_id="campaign-a",
        batch_id="batch-a",
        batch_root=tmp_path.resolve(),
        control_socket=(tmp_path / "control.sock").resolve(),
        coordinator_epoch=epoch,
        control_token=token,
        control_token_sha256=hashlib.sha256(token.encode()).hexdigest(),
    )


def _reply(request, **changes):
    document = {
        "schema_version": 1,
        "command_id": request["command_id"],
        "campaign_id": request["campaign_id"],
        "batch_id": request["batch_id"],
        "coordinator_epoch": request["coordinator_epoch"],
        "operation": request["operation"],
        "request_sha256": request["request_sha256"],
        "state": "TERMINAL",
        "batch_terminal": True,
        "batch_cleanup_complete": True,
        "owned_descendants_gone": True,
        "assigned_ros_domains_clear": True,
        "cleanup_receipt_sha256": "a" * 64,
    }
    document.update(changes)
    return document


class RecordingTransport:
    def __init__(self):
        self.sent = []
        self.changes = {}

    def __call__(self, _binding, request, _timeout):
        self.sent.append(request)
        return _reply(request, **self.changes)


def test_cancel_goes_to_coordinator_with_canonical_command_identity(tmp_path):
    transport = RecordingTransport()
    control = CoordinatorControlClient(transport=transport)

    result = control.cancel(command_id="cancel-1", binding=_binding(tmp_path))

    assert transport.sent[-1]["operation"] == "CANCEL_BATCH"
    assert result.command_id == "cancel-1"


def test_coordinator_stop_requires_terminal_cleanup(tmp_path):
    transport = RecordingTransport()
    transport.changes = {"batch_cleanup_complete": False}
    control = CoordinatorControlClient(transport=transport)
    binding = _binding(tmp_path)

    with pytest.raises(CleanupNotAuthorized, match="BATCH_CLEANUP_INCOMPLETE"):
        authorize_coordinator_stop(
            control.status(command_id="status-1", binding=binding), binding
        )


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"coordinator_epoch": 3}, "COORDINATOR_EPOCH_MISMATCH"),
        ({"batch_id": "batch-b"}, "BATCH_ID_MISMATCH"),
        ({"schema_version": 2}, "CONTROL_SCHEMA_VERSION"),
        ({"command_id": "other"}, "COMMAND_ID_MISMATCH"),
        ({"request_sha256": "f" * 64}, "REQUEST_HASH_MISMATCH"),
    ],
)
def test_control_rejects_mismatched_reply_identity(tmp_path, changes, error):
    transport = RecordingTransport()
    transport.changes = changes
    control = CoordinatorControlClient(transport=transport)

    with pytest.raises(ControlProtocolError, match=error):
        control.status(command_id="status-1", binding=_binding(tmp_path))


@pytest.mark.parametrize(
    ("changes", "error"),
    [
        ({"batch_terminal": False}, "BATCH_NOT_TERMINAL"),
        ({"owned_descendants_gone": False}, "OWNED_DESCENDANTS_REMAIN"),
        ({"assigned_ros_domains_clear": False}, "ROS_DOMAINS_NOT_CLEAR"),
        ({"cleanup_receipt_sha256": None}, "CLEANUP_RECEIPT_INVALID"),
    ],
)
def test_cleanup_authorization_requires_all_independent_receipts(
    tmp_path, changes, error
):
    transport = RecordingTransport()
    transport.changes = changes
    binding = _binding(tmp_path)
    status = CoordinatorControlClient(transport=transport).status(
        command_id="status-1", binding=binding
    )

    with pytest.raises(CleanupNotAuthorized, match=error):
        authorize_coordinator_stop(status, binding)


def test_frame_codec_rejects_partial_and_oversized_frames():
    frame = encode_frame({"schema_version": 1}, max_frame_bytes=128)
    assert decode_frame(frame, max_frame_bytes=128) == {"schema_version": 1}
    with pytest.raises(ControlProtocolError, match="PARTIAL_FRAME"):
        decode_frame(frame[:-1], max_frame_bytes=128)
    with pytest.raises(ControlProtocolError, match="FRAME_TOO_LARGE"):
        decode_frame((129).to_bytes(4, "big") + b"{}", max_frame_bytes=128)


class AdaptiveOwner:
    def __init__(self):
        self.cancelled = []

    def request_cancel(self, owned):
        self.cancelled.append(owned.pid)


def _adaptive_owned(tmp_path):
    return OwnedAdaptiveWrapper(
        campaign_id="campaign-a",
        batch_id="a20",
        pid=123,
        pgid=123,
        started_ticks=7,
        argv_sha256="b" * 64,
        environment_sha256="c" * 64,
        runner_pid=124,
        runner_batch_id="a20",
        runner_journal_root=(tmp_path / "r/a20").resolve(),
    )


def test_adaptive_cleanup_failure_never_starts_next_generation(tmp_path):
    owned = _adaptive_owned(tmp_path)
    status = AdaptiveStatus(
        wrapper_pid=owned.pid,
        wrapper_started_ticks=owned.started_ticks,
        runner_pid=owned.runner_pid,
        batch_id=owned.batch_id,
        state="DEGRADING",
        generation_cleanup_complete=False,
        batch_terminal=False,
        batch_cleanup_complete=False,
    )
    control = AdaptiveWrapperControl(AdaptiveOwner(), lambda: status)

    with pytest.raises(CleanupNotAuthorized, match="GENERATION_CLEANUP_INCOMPLETE"):
        control.await_next_generation(owned)


def test_adaptive_cancel_targets_wrapper_and_rejects_binding_mismatch(tmp_path):
    owned = _adaptive_owned(tmp_path)
    owner = AdaptiveOwner()
    status = AdaptiveStatus(
        wrapper_pid=owned.pid,
        wrapper_started_ticks=owned.started_ticks,
        runner_pid=owned.runner_pid,
        batch_id=owned.batch_id,
        state="RUNNING",
        generation_cleanup_complete=False,
        batch_terminal=False,
        batch_cleanup_complete=False,
    )
    control = AdaptiveWrapperControl(owner, lambda: status)
    control.cancel(owned)
    assert owner.cancelled == [owned.pid]

    bad = replace(status, wrapper_pid=999)
    with pytest.raises(ControlProtocolError, match="ADAPTIVE_WRAPPER_IDENTITY_MISMATCH"):
        AdaptiveWrapperControl(owner, lambda: bad).status(owned)
