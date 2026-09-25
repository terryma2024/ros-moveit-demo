"""ACT child IPC carries only closed business identity and payloads."""

from __future__ import annotations

import json
import asyncio
import sys
import time

import pytest

from so101_teleop.unified.ipc import IpcProtocolError, decode_request
from so101_teleop.unified.bridge import ActChildLaunch, ActWorkerPort, BridgeLaunch
from so101_teleop.unified.contracts import AdmittedCampaignContext, MutationError
from so101_teleop.unified.ipc import IpcReply


def packet(operation: str = "task8_phase", **overrides) -> dict:
    base = {
        "version": 1,
        "operation": operation,
        "command_id": "command-1",
        "deadline_ns": 1000,
        "service_epoch": "epoch-1",
        "runtime_id": "worker-runtime-0",
        "service_token": "private-token",
        "campaign_id": "campaign-1",
        "worker_id": "w00",
        "session_id": "session-0",
        "attempt_id": "attempt-0",
        "execution_generation": 3,
        "token": {
            "operation_id": "operation-1",
            "child_id": "w00",
            "runtime_id": "worker-runtime-0",
            "execution_generation": 3,
            "deadline_ns": 1000,
            "revocation_revision": 0,
        },
        "payload": {
            "scenario_id": "scene-1",
            "stop_after": "MICRO_LIFT",
            "manifest_sha256": "a" * 64,
            "runtime_config_sha256": "b" * 64,
            "contact_policy_fingerprint": "c" * 64,
        },
    }
    base.update(overrides)
    return base


def decode(document: dict):
    return decode_request(json.dumps(document).encode(), now_ns=1)


def test_task8_phase_packet_has_bound_worker_and_closed_payload():
    item = decode(packet())
    assert item.campaign_id == "campaign-1"
    assert item.worker_id == "w00"
    assert item.payload["stop_after"] == "MICRO_LIFT"


@pytest.mark.parametrize(
    "change",
    [
        {"worker_id": "w01"},
        {"execution_generation": 4},
        {"campaign_id": None},
        {"payload": {"scenario_id": "scene-1", "stop_after": "MICRO_LIFT", "manifest_sha256": "a" * 64,
                     "runtime_config_sha256": "b" * 64, "contact_policy_fingerprint": "c" * 64,
                     "gpu_selector": "INDEX:0"}},
    ],
)
def test_task8_packet_refuses_cross_worker_stale_generation_and_resource_recheck(change):
    with pytest.raises(IpcProtocolError, match="IPC_SCHEMA_REJECTED|IPC_WORKER_MISMATCH|IPC_GENERATION_MISMATCH"):
        decode(packet(**change))


def test_task8_full_has_no_phase_override_and_cancel_has_closed_reason():
    full = packet("task8_full", payload={
        "scenario_id": "scene-1", "manifest_sha256": "a" * 64,
        "runtime_config_sha256": "b" * 64, "contact_policy_fingerprint": "c" * 64,
    })
    assert decode(full).operation == "task8_full"
    with pytest.raises(IpcProtocolError, match="IPC_SCHEMA_REJECTED"):
        decode(packet("task8_full"))
    assert decode(packet("cancel", payload={"reason": "operator"})).operation == "cancel"
    with pytest.raises(IpcProtocolError, match="IPC_SCHEMA_REJECTED"):
        decode(packet("cancel", payload={"reason": "operator", "shell": "bad"}))


def _context() -> AdmittedCampaignContext:
    return AdmittedCampaignContext(
        campaign_id="campaign-1", operation_id="operation-1", workload_kind="task8_phase",
        service_epoch="epoch-1", execution_generation=3,
        stable_host_id="ai-station-1", physical_gpu_uuid="GPU-physical-a", worker_count=1,
        source_sha256="f" * 64, manifest_sha256="a" * 64,
        runtime_config_sha256="b" * 64, collection_config_sha256="c" * 64,
        contact_policy_fingerprint="d" * 64, domain_session_map_sha256="e" * 64,
        resource_binding_id="binding-1", evidence_root="/data/work/so101-evidence/task",
        admitted_at_monotonic_s=1.0, deadline_monotonic_s=10**12,
    )


def _launch(worker_id="w00", domain=40):
    return ActChildLaunch(
        campaign_id="campaign-1", worker_id=worker_id, execution_generation=3,
        ros_domain_id=domain, namespace=f"/act/{worker_id}",
        controller_name=f"{worker_id}_controller", mujoco_session_id=f"session-{worker_id}",
        socket_root=f"/tmp/act-{worker_id}",
    )


class _Client:
    service_epoch = "epoch-1"
    runtime_id = "runtime-w00"
    service_token = "private"

    def __init__(self):
        self.packets = []
        self.worker_id = "w00"

    async def call(self, packet):
        self.packets.append(packet)
        return IpcReply(accepted=True, result={
            "operation_id": "operation-1", "campaign_id": "campaign-1",
            "worker_id": self.worker_id, "execution_generation": 3,
            "body": {"status": "ACCEPTED"},
        })


def test_worker_port_binds_task8_packet_and_rejects_foreign_reply():
    client = _Client()
    port = ActWorkerPort(_context(), _launch(), client)
    request = {
        "session_id": "session-w00", "attempt_id": "attempt-1", "scenario_id": "scene-1",
        "mode": "phase_prefix", "stop_after": "MICRO_LIFT",
        "contact_policy_fingerprint": "d" * 64, "deadline_ns": time.monotonic_ns() + 10**9,
    }
    assert asyncio.run(port.task8(request)) == {"status": "ACCEPTED"}
    sent = client.packets[-1]
    assert sent.operation == "task8_phase" and sent.worker_id == "w00"
    assert sent.token.operation_id == "operation-1"
    assert "physical_gpu_uuid" not in sent.payload and "resource_binding_id" not in sent.payload
    client.worker_id = "w01"
    with pytest.raises(MutationError, match="ACT_REPLY_IDENTITY_MISMATCH"):
        asyncio.run(port.task8(request))


def test_bridge_launch_derives_distinct_worker_runtime_environment(tmp_path):
    base = BridgeLaunch(
        ros_python=__import__("pathlib").Path(sys.executable), install_prefix=tmp_path,
        runtime_id="runtime", environment={"ROS_DOMAIN_ID": "1"}, socket_root=tmp_path / "base",
    )
    first = base.for_act_worker(_launch("w00", 40))
    second = base.for_act_worker(_launch("w01", 41))
    assert first.runtime_id != second.runtime_id
    assert first.socket_root != second.socket_root
    assert first.environment["ROS_DOMAIN_ID"] == "40"
    assert second.environment["ROS_DOMAIN_ID"] == "41"
    assert first.environment["SO101_ACT_WORKER_ID"] == "w00"
    assert second.environment["SO101_SIMULATION_SESSION_ID"] == "session-w01"
