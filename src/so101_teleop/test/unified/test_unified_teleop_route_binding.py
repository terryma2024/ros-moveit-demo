"""A bound HTTP Teleop mutation reaches the same production admission boundary."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from so101_teleop.unified.admission import AdmissionGateway
from so101_teleop.unified.app import create_unified_app
from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.contracts import (
    ActionKey,
    ActionTerminal,
    DispatchAck,
    Domain,
    LeaseIdentity,
    OwnerKey,
)
from so101_teleop.unified.goals import GoalRegistry
from so101_teleop.unified.instances import InstanceRegistry
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.parents import ParentSequencer
from so101_teleop.unified.ports import UnifiedServices
from so101_teleop.unified.safety import SafetyLane, SafetyLimits
from so101_teleop.unified.teleop_service import BackendView, ProductionTeleopService


class RecordingWorker:
    def __init__(self) -> None:
        self.commands = []
        self.children = []

    async def command(self, name, body, reservation):
        assert reservation is not None
        self.commands.append((name, body, reservation))
        return {"command_id": body["command_id"], "accepted": True, "succeeded": True, "code": "OK"}

    async def dispatch_arm(self, plan_id, token):
        self.children.append(("arm", plan_id))
        return self._ack(token, "arm")

    async def dispatch_gripper(self, target, token):
        self.children.append(("gripper", target))
        return self._ack(token, "gripper")

    def _ack(self, token, child_id):
        key = ActionKey(
            token.operation_id,
            child_id,
            f"goal-{child_id}",
            OwnerKey(1, 1, 1, "a", "e"),
            "R1",
            1,
        )
        return DispatchAck(key, True)

    async def wait_terminal(self, ack):
        return ActionTerminal(ack.key, True, True, True)


@pytest.mark.parametrize(
    ("path", "body", "expected_command"),
    [
        ("/plan/joints", {"command_id": "joint-1"}, "plan_joints"),
        ("/plans/p1/execute", {"command_id": "execute-1"}, "execute"),
        ("/plans/p1/execute-all", {"command_id": "all-1"}, None),
    ],
)
def test_bound_teleop_http_mutation_reaches_production_admission(
    tmp_path, path, body, expected_command
):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    registry = InstanceRegistry(
        arbiter, service_epoch="e1", origin="http://127.0.0.1:8000", clock_ns=lambda: 1
    )
    lane = SafetyLane(
        GoalRegistry(), arbiter, limits=SafetyLimits(0.5, 0.5, 4),
        authorize=lambda authority, key: None, service_epoch="e1",
    )
    worker = RecordingWorker()

    async def guard(authority):
        registry.require_bound(authority)

    service = ProductionTeleopService(
        worker,
        admission=AdmissionGateway(arbiter, registry),
        parents=ParentSequencer(worker, arbiter, authority_guard=guard),
        safety=lane,
        arbiter=arbiter,
        backend_view=BackendView("mujoco", "so101", "run", {"manual_joint_execute": True}),
        runtime_id="R1",
        service_epoch="e1",
    )
    app = create_unified_app(
        UnifiedServices(teleop=service, tasks=None, validation=None, arbiter=arbiter,
                        instances=registry, safety=lane),
        bind_address="127.0.0.1",
    )
    proof = registry.register(Domain.TELEOP)
    binding = registry.connect(proof.instance_id, proof.proof, origin="http://127.0.0.1:8000")
    authority = registry.claim(binding, LeaseIdentity("l1", "s1", 1, 10**15))
    headers = {
        "X-SO101-Instance-ID": authority.instance_id,
        "X-SO101-Instance-Proof": authority.proof,
        "X-SO101-Channel-Revision": str(authority.channel_revision),
        "X-SO101-Execution-Generation": str(authority.execution_generation),
    }
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            stale = client.post(path, json=body, headers={**headers, "X-SO101-Execution-Generation": "0"})
            assert stale.status_code == 409
            assert not worker.commands and not worker.children
            response = client.post(path, json=body, headers=headers)
        assert response.status_code == 200, response.text
        if expected_command is None:
            assert worker.children == [("arm", "p1"), ("gripper", 0.0)]
            assert arbiter.is_idle()
        else:
            assert [name for name, _body, _reservation in worker.commands] == [expected_command]
            assert not arbiter.is_idle()
    finally:
        store.close()
