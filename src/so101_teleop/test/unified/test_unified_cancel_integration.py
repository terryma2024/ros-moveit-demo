"""Safety cancellation through the real unified routes.

Only the innermost ``WorkerPort`` is test-owned. The request travels through the real app factory,
the real admission gateway, the real arbiter and the real safety lane, so this exercises the
production cancel path rather than a toy.
"""

from __future__ import annotations

import asyncio

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

ORIGIN = "http://127.0.0.1:8000"
LEASE = LeaseIdentity("l1", "s1", 1, 10**15)


class BlockingWorker:
    """A real WorkerPort whose gripper dispatch blocks until the test releases it."""

    def __init__(self) -> None:
        self.arm_dispatched = asyncio.Event()
        self.gripper_reached = asyncio.Event()
        self.gripper_allowed = asyncio.Event()
        self.cancelled: list[str] = []
        self.terminals: list[ActionTerminal] = []
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _set(self, event: asyncio.Event) -> None:
        if self._loop is not None:
            self._loop.call_soon_threadsafe(event.set)
        else:
            event.set()

    async def dispatch_arm(self, plan_id, token):
        key = ActionKey(token.operation_id, "arm", "goal-arm", OwnerKey(1, 1, 1, "a", "e"), "R1", 1)
        self.arm_dispatched.set()
        return DispatchAck(key, True)

    async def dispatch_gripper(self, target, token):
        key = ActionKey(token.operation_id, "gripper", "goal-grip", OwnerKey(1, 1, 1, "a", "e"), "R1", 1)
        self._set(self.gripper_reached)
        await self.gripper_allowed.wait()
        return DispatchAck(key, True)

    async def wait_terminal(self, ack):
        # The arm must succeed, otherwise the parent settles immediately and never reaches the
        # gripper step - the window this test is about.
        if ack.key.child_id == "gripper":
            await self.gripper_allowed.wait()
            terminal = ActionTerminal(ack.key, False, True, True)
        else:
            terminal = ActionTerminal(ack.key, True, True, True)
        self.terminals.append(terminal)
        return terminal

    async def plan_home(self):
        return "home-plan"

    async def workflow(self, operation, run_id, token):
        raise AssertionError("workflow is not part of this test")


class Harness:
    def __init__(self, tmp_path) -> None:
        self.store = IntentStore.open(tmp_path / "state")
        self.arbiter = GlobalMutationArbiter(self.store, clock_ns=lambda: 1)
        self.registry = InstanceRegistry(
            self.arbiter, service_epoch="e1", origin=ORIGIN, clock_ns=lambda: 1
        )
        self.goals = GoalRegistry()
        self.worker = BlockingWorker()
        self.lane = SafetyLane(
            self.goals,
            self.arbiter,
            limits=SafetyLimits(0.5, 0.5, 4),
            authorize=lambda authority, key: None,
            service_epoch="e1",
        )
        gateway = AdmissionGateway(self.arbiter, self.registry)

        async def guard(authority):
            self.registry.require_bound(authority)

        sequencer = ParentSequencer(self.worker, self.arbiter, authority_guard=guard)
        self.service = ProductionTeleopService(
            self.worker,
            admission=gateway,
            parents=sequencer,
            safety=self.lane,
            arbiter=self.arbiter,
            backend_view=BackendView(
                "mujoco", "so101", "run", {"manual_joint_execute": True}
            ),
            runtime_id="R1",
            service_epoch="e1",
        )
        self.services = UnifiedServices(
            teleop=self.service,
            tasks=None,
            validation=None,
            arbiter=self.arbiter,
            instances=self.registry,
            safety=self.lane,
        )
        self.app = create_unified_app(self.services, bind_address="127.0.0.1")
        proof = self.registry.register(Domain.TELEOP)
        self.binding = self.registry.connect(proof.instance_id, proof.proof, origin=ORIGIN)
        self.authority = self.registry.claim(self.binding, LEASE)

    def headers(self) -> dict:
        return {
            "X-SO101-Instance-ID": self.authority.instance_id,
            "X-SO101-Instance-Proof": self.authority.proof,
            "X-SO101-Channel-Revision": str(self.authority.channel_revision),
            "X-SO101-Execution-Generation": str(self.authority.execution_generation),
        }

    def close(self) -> None:
        self.store.close()


def test_cancel_through_real_routes_bypasses_the_busy_parent(tmp_path):
    async def run():
        harness = Harness(tmp_path)
        loop = asyncio.get_running_loop()
        harness.worker.bind_loop(loop)
        try:
            with TestClient(harness.app) as client:
                # A register-only goal exists so the lane has a real cancel target.
                start = asyncio.create_task(
                    harness.service.execute_all(
                        {"command_id": "all-1", "plan_id": "p1", "gripper_target": 0.0},
                        authority=harness.authority,
                        lease=LEASE,
                    )
                )
                await asyncio.wait_for(harness.worker.arm_dispatched.wait(), 1)
                # The parent holds the reservation while the gripper step is blocked, so a second
                # domain cannot start: that is the window the plan cares about.
                assert not harness.arbiter.is_idle()

                response = client.post(
                    "/execution/cancel",
                    json={"command_id": "cancel-1", "operation_id": _single_operation(harness)},
                    headers=harness.headers(),
                )
                assert response.status_code == 200, response.text
                assert response.json()["accepted"] is True
                # The cancellation is durable before any goal work happens.
                parent = harness.arbiter.store.parent_record(_single_operation(harness))
                assert parent is not None and parent["cancel_requested"] == 1
                # The reservation is NOT released by accepting the cancel.
                assert not harness.arbiter.is_idle()

                harness.worker.gripper_allowed.set()
                projection = await asyncio.wait_for(start, 2)
                assert projection.phase != "COMPLETE"
        finally:
            await harness.lane.close()
            harness.close()

    asyncio.run(run())


def _single_operation(harness: Harness) -> str:
    row = harness.arbiter.store._query_one("SELECT operation_id FROM parents ORDER BY created_ns DESC LIMIT 1")
    assert row is not None
    return row["operation_id"]
