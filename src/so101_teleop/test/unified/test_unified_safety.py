"""Contract tests for the isolated safety lane.

The lane must deliver a cancel and wait for stop evidence without ever waiting on the
ordinary mutation locks or the normal command executor. These tests use the real
arbiter and real durable state; only the goal handles are test fakes.
"""

from __future__ import annotations

import asyncio

import pytest

from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.contracts import (
    ActionKey,
    ActionTerminal,
    DispatchAck,
    Domain,
    MutationError,
    OperationSpec,
    OwnerKey,
    RequestAuthority,
)
from so101_teleop.unified.goals import GoalRegistry
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.safety import SafetyAuthority, SafetyLane, SafetyLimits

WATCHDOG = SafetyAuthority("watchdog", Domain.TELEOP, "e1", 1, None)


def owner() -> OwnerKey:
    return OwnerKey(11, 11, 9, "a", "e")


class Rig:
    """Real store/arbiter plus registered fake goals."""

    def __init__(self, tmp_path, *, limits: SafetyLimits = SafetyLimits(0.2, 0.5, 2)) -> None:
        self.store = IntentStore.open(tmp_path / "state")
        self.arbiter = GlobalMutationArbiter(self.store, clock_ns=lambda: 1)
        self.goals = GoalRegistry()
        self.lane = SafetyLane(self.goals, self.arbiter, limits=limits, authorize=lambda a, k: None)
        self.cancelled: list[str] = []
        self.gates: dict[str, asyncio.Event] = {}

    def parent(self, command_id: str = "grip-1", *, kind: str = "gripper") -> str:
        reservation = self.arbiter.begin(OperationSpec(command_id, Domain.TELEOP, kind, {}, "R1", 1, 10**9))
        return reservation.operation_id

    def register(
        self,
        operation_id: str,
        child_id: str,
        goal_uuid: str,
        *,
        hang_cancel: bool = False,
        hang_observe: bool = False,
    ):
        key = ActionKey(operation_id, child_id, goal_uuid, owner(), "R1", 1)
        gate = asyncio.Event()
        self.gates[goal_uuid] = gate

        async def cancel() -> bool:
            self.cancelled.append(goal_uuid)
            if hang_cancel:
                await gate.wait()
            return True

        async def observe() -> ActionTerminal:
            if hang_observe:
                await gate.wait()
            return ActionTerminal(key, False, True, True)

        self.goals.register(key, cancel=cancel, observe=observe)
        return key

    def acknowledge(self, key: ActionKey) -> None:
        token = self.arbiter.prepare_child(key.operation_id, key.child_id)
        self.arbiter.record_ack(token, DispatchAck(key, True))

    async def close(self) -> None:
        await self.lane.close()
        self.store.close()


def test_isolated_lane_delivers_and_waits_for_stop_evidence(tmp_path):
    async def run():
        store = IntentStore.open(tmp_path / "state")
        arb = GlobalMutationArbiter(store, clock_ns=lambda: 1)
        goals, delivered, stopped = GoalRegistry(), asyncio.Event(), asyncio.Event()
        parent = arb.begin(OperationSpec("grip-1", Domain.TELEOP, "gripper", {"target": 0.0}, "R1", 1, 100))
        token = arb.prepare_child(parent.operation_id, "gripper")
        key = ActionKey(parent.operation_id, "gripper", "goal-6", OwnerKey(11, 11, 9, "a", "e"), "R1", 1)
        arb.record_ack(token, DispatchAck(key, True))

        async def cancel():
            delivered.set()
            return True

        async def observe():
            await stopped.wait()
            return ActionTerminal(key, False, True, True)

        goals.register(key, cancel=cancel, observe=observe)
        lane = SafetyLane(goals, arb, limits=SafetyLimits(0.2, 0.5, 2), authorize=lambda a, k: None)
        authority = SafetyAuthority("watchdog", Domain.TELEOP, "e1", 1, None)
        pending = asyncio.create_task(lane.cancel(key, authority))
        await asyncio.wait_for(delivered.wait(), 0.2)
        assert not pending.done()
        stopped.set()
        receipt = await pending
        assert receipt.terminal.stopped_confirmed
        await lane.close()
        store.close()

    asyncio.run(run())


def test_parent_cancel_is_durable_before_the_goal_is_touched(tmp_path):
    async def run():
        rig = Rig(tmp_path)
        try:
            operation_id = rig.parent()
            key = rig.register(operation_id, "arm", "goal-arm")
            rig.acknowledge(key)
            await rig.lane.cancel(key, WATCHDOG)
            parent = rig.arbiter.store.parent_record(operation_id)
            assert parent is not None and parent["cancel_requested"] == 1
            with pytest.raises(MutationError, match="INTENT_REVOKED"):
                rig.arbiter.prepare_child(operation_id, "gripper")
        finally:
            await rig.close()

    asyncio.run(run())


def test_arm_and_gripper_goals_cancel_independently(tmp_path):
    async def run():
        rig = Rig(tmp_path)
        try:
            operation_id = rig.parent("all-1", kind="execute_all")
            arm = rig.register(operation_id, "arm", "goal-arm")
            gripper = rig.register(operation_id, "gripper", "goal-grip")
            rig.acknowledge(arm)
            rig.acknowledge(gripper)
            rig.gates["goal-arm"].set()
            await rig.lane.cancel(arm, WATCHDOG)
            assert rig.cancelled == ["goal-arm"]
            with pytest.raises(MutationError, match="UNKNOWN_GOAL"):
                rig.goals.require(
                    ActionKey(operation_id, "arm", "goal-other", owner(), "R1", 1)
                )
            rig.gates["goal-grip"].set()
            await rig.lane.cancel(gripper, WATCHDOG)
            assert rig.cancelled == ["goal-arm", "goal-grip"]
        finally:
            await rig.close()

    asyncio.run(run())


def test_duplicate_cancel_merges_into_one_delivery(tmp_path):
    async def run():
        rig = Rig(tmp_path)
        try:
            operation_id = rig.parent()
            key = rig.register(operation_id, "gripper", "goal-grip")
            rig.acknowledge(key)
            rig.gates["goal-grip"].set()
            first, second = await asyncio.gather(
                rig.lane.cancel(key, WATCHDOG), rig.lane.cancel(key, WATCHDOG)
            )
            assert rig.cancelled == ["goal-grip"]
            assert first.key == second.key == key
        finally:
            await rig.close()

    asyncio.run(run())


def test_late_ack_is_registered_then_safely_cancelled(tmp_path):
    async def run():
        rig = Rig(tmp_path)
        try:
            operation_id = rig.parent("all-2", kind="execute_all")
            key = rig.register(operation_id, "arm", "goal-late")
            token = rig.arbiter.prepare_child(operation_id, "arm")
            intent = rig.arbiter.cancel_parent(operation_id)
            assert [target.key.child_id for target in intent.targets] == ["arm"]
            rig.arbiter.record_ack(token, DispatchAck(key, True))  # accepted after the cancel
            rig.gates["goal-late"].set()
            receipt = await rig.lane.cancel(key, WATCHDOG)
            assert rig.cancelled == ["goal-late"]
            assert receipt.accepted
        finally:
            await rig.close()

    asyncio.run(run())


def test_foreign_authority_is_refused_before_delivery(tmp_path):
    async def run():
        store = IntentStore.open(tmp_path / "state")
        arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
        goals = GoalRegistry()
        delivered = asyncio.Event()
        parent = arbiter.begin(OperationSpec("grip-2", Domain.TELEOP, "gripper", {}, "R1", 1, 10**9))
        key = ActionKey(parent.operation_id, "gripper", "goal-6", owner(), "R1", 1)

        def refuse(authority, requested):
            raise MutationError("CONTROLLER_INSTANCE_MISMATCH: foreign instance")

        async def cancel():
            delivered.set()
            return True

        async def observe():
            return ActionTerminal(key, False, True, True)

        goals.register(key, cancel=cancel, observe=observe)
        lane = SafetyLane(goals, arbiter, limits=SafetyLimits(0.2, 0.5, 2), authorize=refuse)
        with pytest.raises(MutationError, match="CONTROLLER_INSTANCE_MISMATCH"):
            await lane.cancel(key, WATCHDOG)
        assert not delivered.is_set()
        await lane.close()
        store.close()

    asyncio.run(run())


def test_browser_authority_requires_a_bound_instance(tmp_path):
    async def run():
        rig = Rig(tmp_path)
        try:
            operation_id = rig.parent()
            key = rig.register(operation_id, "gripper", "goal-grip")
            rig.acknowledge(key)
            rig.gates["goal-grip"].set()
            browser = SafetyAuthority(
                "browser", Domain.TELEOP, "e1", 1, RequestAuthority(Domain.TELEOP, "i", "p", 1, 1)
            )
            assert (await rig.lane.cancel(key, browser)).accepted
            anonymous = SafetyAuthority("browser", Domain.TELEOP, "e1", 1, None)
            with pytest.raises(MutationError, match="INSTANCE_AUTHORITY_REQUIRED"):
                await rig.lane.cancel(key, anonymous)
        finally:
            await rig.close()

    asyncio.run(run())


def test_delivery_timeout_blocks_and_reports(tmp_path):
    async def run():
        rig = Rig(tmp_path, limits=SafetyLimits(0.05, 0.5, 2))
        try:
            operation_id = rig.parent()
            key = rig.register(operation_id, "gripper", "goal-grip", hang_cancel=True)
            rig.acknowledge(key)
            receipt = await rig.lane.cancel(key, WATCHDOG)
            assert receipt.accepted is False
            assert receipt.blocked_reason == "CANCEL_DELIVERY_TIMEOUT"
            assert not rig.arbiter.is_idle()
        finally:
            await rig.close()

    asyncio.run(run())


def test_accepted_cancel_without_stop_proof_blocks_and_never_settles(tmp_path):
    async def run():
        rig = Rig(tmp_path, limits=SafetyLimits(0.5, 0.05, 2))
        try:
            operation_id = rig.parent()
            key = rig.register(operation_id, "gripper", "goal-grip", hang_observe=True)
            rig.acknowledge(key)
            receipt = await rig.lane.cancel(key, WATCHDOG)
            assert receipt.blocked_reason == "STOP_NOT_CONFIRMED"
            assert receipt.terminal is None
            assert not rig.arbiter.is_idle()
            with pytest.raises(MutationError):
                rig.arbiter.settle(operation_id, cleanup_confirmed=False)
            with pytest.raises(MutationError, match="BLOCKED"):
                rig.arbiter.begin(OperationSpec("v1", Domain.VALIDATION, "start", {}, "R1", 1, 10**9))
        finally:
            rig.gates["goal-grip"].set()
            await rig.close()

    asyncio.run(run())


def test_full_safe_queue_refuses_instead_of_queueing_behind_mutations(tmp_path):
    async def run():
        rig = Rig(tmp_path, limits=SafetyLimits(0.5, 0.5, 1))
        try:
            operation_id = rig.parent("all-3", kind="execute_all")
            keys = []
            for child_id in ("arm", "gripper", "extra"):
                key = rig.register(operation_id, child_id, f"goal-{child_id}", hang_cancel=True)
                rig.acknowledge(key)
                keys.append(key)
            first = asyncio.create_task(rig.lane.cancel(keys[0], WATCHDOG))
            await asyncio.sleep(0.05)
            second = asyncio.create_task(rig.lane.cancel(keys[1], WATCHDOG))
            await asyncio.sleep(0.05)
            with pytest.raises(MutationError, match="SAFETY_QUEUE_FULL"):
                await rig.lane.cancel(keys[2], WATCHDOG)
            assert not rig.arbiter.is_idle()
            for key in keys:
                rig.gates[key.goal_uuid].set()
            await asyncio.gather(first, second)
        finally:
            await rig.close()

    asyncio.run(run())


def test_revoke_without_a_pending_authorizer_is_refused(tmp_path):
    async def run():
        store = IntentStore.open(tmp_path / "state")
        arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
        lane = SafetyLane(
            GoalRegistry(), arbiter, limits=SafetyLimits(0.2, 0.5, 2), authorize=lambda a, k: None
        )
        parent = arbiter.begin(OperationSpec("all-4", Domain.TELEOP, "execute_all", {}, "R1", 1, 10**9))
        arbiter.prepare_child(parent.operation_id, "arm")
        intent = arbiter.cancel_parent(parent.operation_id)
        with pytest.raises(MutationError, match="SAFETY_PENDING_AUTHORIZER_MISSING"):
            await lane.revoke(intent.targets[0], WATCHDOG)
        await lane.close()
        store.close()

    asyncio.run(run())


def test_revoke_linearizes_prepared_children_without_goal_handles(tmp_path):
    async def run():
        store = IntentStore.open(tmp_path / "state")
        arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
        seen: list[str] = []

        def authorize_pending(authority, target):
            seen.append(target.key.child_id)

        lane = SafetyLane(
            GoalRegistry(),
            arbiter,
            limits=SafetyLimits(0.2, 0.5, 2),
            authorize=lambda a, k: None,
            authorize_pending=authorize_pending,
        )
        parent = arbiter.begin(OperationSpec("all-5", Domain.TELEOP, "execute_all", {}, "R1", 1, 10**9))
        arbiter.prepare_child(parent.operation_id, "arm")
        intent = arbiter.cancel_parent(parent.operation_id)
        receipt = await lane.revoke(intent.targets[0], WATCHDOG)
        assert seen == ["arm"]
        assert receipt.linearized is True
        assert receipt.submitted is False
        await lane.close()
        store.close()

    asyncio.run(run())
