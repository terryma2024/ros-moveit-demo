"""Frozen IPC protocol tests: nothing outside the allowlist may decode."""

from __future__ import annotations

import json

import pytest

from so101_teleop.unified.ipc import (
    ALLOWED_OPERATIONS,
    DEFAULT_MAX_BYTES,
    IpcProtocolError,
    IpcRequest,
    decode_request,
    decode_safety_packet,
)

VALID_TOKEN = {
    "operation_id": "op-1",
    "child_id": "arm",
    "runtime_id": "R1",
    "execution_generation": 1,
    "deadline_ns": 1000,
    "revocation_revision": 0,
}


def document(**overrides) -> dict:
    base = dict(
        version=1,
        operation="observe",
        command_id="read-1",
        deadline_ns=100,
        service_epoch="e1",
        runtime_id="R1",
        service_token="token-1",
        payload={},
    )
    base.update(overrides)
    return base


def test_ipc_accepts_observe_for_bound_epoch_and_runtime():
    request = decode_request(json.dumps(document()).encode(), max_bytes=1024, now_ns=1)
    assert request.operation == "observe"
    assert request.runtime_id == "R1" and request.service_epoch == "e1"


def test_ipc_accepts_a_motion_packet_with_its_dispatch_token():
    request = decode_request(
        json.dumps(document(operation="execute_arm", token=VALID_TOKEN, payload={"plan_id": "p1"})).encode(),
        max_bytes=DEFAULT_MAX_BYTES,
        now_ns=1,
    )
    assert request.operation == "execute_arm"
    assert request.token is not None and request.token.child_id == "arm"


@pytest.mark.parametrize(
    "document",
    [
        {"version": 1, "operation": "shell", "payload": {"cmd": "echo unsafe"}},
        {"version": 2, "operation": "observe", "command_id": "x", "deadline_ns": 100},
        {"version": 1, "operation": "observe", "command_id": "x", "deadline_ns": 0},
        {"version": 1, "operation": "observe", "command_id": "x", "deadline_ns": 100, "executable": "foreign"},
    ],
)
def test_ipc_rejects_unknown_extra_expired_and_version(document):
    with pytest.raises(ValueError):
        decode_request(json.dumps(document).encode(), max_bytes=1024, now_ns=1)


def test_ipc_rejects_motion_without_a_token_and_with_a_foreign_runtime_token():
    with pytest.raises(IpcProtocolError, match="IPC_TOKEN_REQUIRED"):
        decode_request(
            json.dumps(document(operation="gripper", payload={"target": 0.0})).encode(),
            max_bytes=1024,
            now_ns=1,
        )
    foreign = dict(VALID_TOKEN, runtime_id="R2")
    with pytest.raises(IpcProtocolError, match="IPC_RUNTIME_MISMATCH"):
        decode_request(
            json.dumps(document(operation="gripper", token=foreign)).encode(), max_bytes=1024, now_ns=1
        )


def test_ipc_rejects_oversize_nan_and_non_object_documents():
    with pytest.raises(IpcProtocolError, match="IPC_OVERSIZE"):
        decode_request(json.dumps(document()).encode(), max_bytes=8, now_ns=1)
    with pytest.raises(IpcProtocolError, match="IPC_NOT_FINITE"):
        decode_request(b'{"version": 1, "operation": "observe", "x": NaN}', max_bytes=1024, now_ns=1)
    with pytest.raises(IpcProtocolError, match="IPC_NOT_AN_OBJECT"):
        decode_request(b"[1, 2, 3]", max_bytes=1024, now_ns=1)
    with pytest.raises(IpcProtocolError, match="IPC_NOT_JSON"):
        decode_request(b"{not json", max_bytes=1024, now_ns=1)


def test_ipc_rejects_non_finite_numbers_inside_a_payload():
    """NaN cannot arrive as JSON, but the in-process model boundary must refuse it too."""
    from pydantic import ValidationError

    with pytest.raises(ValidationError, match="IPC_PAYLOAD_NOT_FINITE"):
        IpcRequest(**document(operation="plan_joints", payload={"angles": [1.0, float("nan")]}))
    with pytest.raises(IpcProtocolError, match="IPC_NOT_FINITE"):
        decode_request(
            b'{"version": 1, "operation": "plan_joints", "payload": {"angles": [Infinity]}}',
            max_bytes=1024,
            now_ns=1,
        )


def test_ipc_allowlist_is_exactly_the_reviewed_operation_set():
    assert "shell" not in ALLOWED_OPERATIONS
    assert set(ALLOWED_OPERATIONS) == {
        "observe",
        "plan_joints",
        "plan_tcp",
        "execute_arm",
        "gripper",
        "home",
        "attachment",
        "scene_repair",
        "simulation_reset",
        "camera_preset",
        "parameters",
        "workflow",
    }
    schema = IpcRequest.model_json_schema()
    assert schema["additionalProperties"] is False
    assert schema["properties"]["version"]["const"] == 1


def test_safety_packet_is_closed_and_versioned():
    packet = {
        "version": 1,
        "operation": "revoke",
        "service_epoch": "e1",
        "owner": {"pid": 1},
        "claim": "claim-1",
        "target": {"key": {"operation_id": "op-1", "child_id": "arm"}, "revocation_revision": 1},
    }
    decoded = decode_safety_packet(json.dumps(packet).encode())
    assert decoded.operation == "revoke"
    with pytest.raises(IpcProtocolError, match="IPC_VERSION_UNSUPPORTED"):
        decode_safety_packet(json.dumps(dict(packet, version=2)).encode())
    with pytest.raises(IpcProtocolError, match="IPC_SAFETY_SCHEMA_REJECTED"):
        decode_safety_packet(json.dumps(dict(packet, extra="unsafe")).encode())
