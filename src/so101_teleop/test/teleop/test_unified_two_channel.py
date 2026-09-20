"""Two-channel race tests over real child sockets.

The child runs the production ChildRuntime servers; the web side runs the production
BridgeClient. Only the leaf ActionDriver is test-owned.
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path

import pytest

from so101_teleop.unified.contracts import MutationError
from so101_teleop.unified.ipc import IpcRequest

HARNESS_PATH = Path(__file__).parents[1] / "e2e/unified_child_harness.py"


def load_harness():
    spec = importlib.util.spec_from_file_location("unified_child_harness", HARNESS_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def harness_module():
    return load_harness()


def test_safe_revoke_wins_before_delayed_normal_packet(tmp_path, harness_module):
    async def run():
        h = await harness_module.TwoChannelHarness.start(tmp_path)
        try:
            token = h.prepare_child()
            h.hold_normal_delivery()
            pending = asyncio.create_task(h.send(token))
            await asyncio.sleep(0.05)
            receipt = await h.revoke(token)
            assert receipt.linearized and not receipt.submitted
            await h.release_normal_delivery()
            with pytest.raises(MutationError, match="INTENT_REVOKED"):
                await pending
            assert (await h.stats()).submit_count == 0
        finally:
            await h.close()

    asyncio.run(run())


def test_submit_wins_exactly_once_and_cancel_targets_the_real_uuid(tmp_path, harness_module):
    async def run():
        h = await harness_module.TwoChannelHarness.start(tmp_path)
        try:
            token = h.prepare_child()
            ack = await h.send(token)
            assert ack.accepted and ack.key.goal_uuid == "goal-arm"
            repeated = await h.send(token)
            assert repeated.key.goal_uuid == "goal-arm"
            stats = await h.stats()
            assert stats.submit_count == 1, "a repeated token must not submit a second goal"
            receipt = await h.revoke(token)
            assert receipt.linearized and receipt.submitted
            stats = await h.stats()
            assert stats.cancel_uuids == ("goal-arm",)
            assert stats.pending_uuids == ("goal-arm",)
            assert not h.arbiter.is_idle(), "an unconfirmed cancel never releases the reservation"
        finally:
            await h.close()

    asyncio.run(run())


def test_expired_queued_mutation_is_never_dispatched(tmp_path, harness_module):
    async def run():
        h = await harness_module.TwoChannelHarness.start(tmp_path)
        try:
            token = h.prepare_child()
            stale = IpcRequest(
                version=1,
                operation="execute_arm",
                command_id="stale-1",
                deadline_ns=1,
                service_epoch="e1",
                runtime_id="R1",
                service_token="test-service-token",
                token={
                    "operation_id": token.operation_id,
                    "child_id": token.child_id,
                    "runtime_id": token.runtime_id,
                    "execution_generation": token.execution_generation,
                    "deadline_ns": token.deadline_ns,
                    "revocation_revision": token.revocation_revision,
                },
            )
            reply = await h.client.call(stale)
            assert not reply.accepted
            assert "IPC_DEADLINE_EXPIRED" in reply.code
            assert (await h.stats()).submit_count == 0
        finally:
            await h.close()

    asyncio.run(run())


def test_repeated_and_stale_revokes_do_not_undo_the_tombstone(tmp_path, harness_module):
    async def run():
        h = await harness_module.TwoChannelHarness.start(tmp_path)
        try:
            token = h.prepare_child()
            first = await h.revoke(token)
            second = await h.revoke(token)
            assert first.linearized and second.linearized
            h.hold_normal_delivery()
            pending = asyncio.create_task(h.send(token))
            await asyncio.sleep(0.05)
            await h.release_normal_delivery()
            with pytest.raises(MutationError, match="INTENT_REVOKED"):
                await pending
            assert (await h.stats()).submit_count == 0
        finally:
            await h.close()

    asyncio.run(run())


def test_web_death_latch_refuses_new_work_and_cancels_known_pending(tmp_path, harness_module):
    async def run():
        h = await harness_module.TwoChannelHarness.start(tmp_path)
        try:
            token = h.prepare_child()
            ack = await h.send(token)
            await h.runtime.mark_web_dead("web heartbeat lost")
            stats = await h.stats()
            assert stats.cancel_uuids == (ack.key.goal_uuid,)
            h.hold_normal_delivery()
            sibling = h.arbiter.prepare_child(token.operation_id, "gripper")
            late = asyncio.create_task(h.send(sibling))
            await asyncio.sleep(0.05)
            await h.release_normal_delivery()
            with pytest.raises(MutationError, match="WEB_DEAD"):
                await late
            assert (await h.stats()).submit_count == 1
        finally:
            await h.close()

    asyncio.run(run())


def test_wrong_epoch_or_token_never_reaches_the_child(tmp_path, harness_module):
    async def run():
        h = await harness_module.TwoChannelHarness.start(tmp_path)
        try:
            token = h.prepare_child()
            wrong_epoch = IpcRequest(
                version=1,
                operation="execute_arm",
                command_id="wrong-epoch",
                deadline_ns=10**18,
                service_epoch="e2",
                runtime_id="R1",
                service_token="test-service-token",
                token={
                    "operation_id": token.operation_id,
                    "child_id": token.child_id,
                    "runtime_id": token.runtime_id,
                    "execution_generation": token.execution_generation,
                    "deadline_ns": token.deadline_ns,
                    "revocation_revision": token.revocation_revision,
                },
            )
            reply = await h.client.call(wrong_epoch)
            assert not reply.accepted and "IPC_EPOCH_REJECTED" in reply.code
            wrong_token = wrong_epoch.model_copy(update={"service_epoch": "e1", "service_token": "bad"})
            reply = await h.client.call(wrong_token)
            assert not reply.accepted and "IPC_TOKEN_REJECTED" in reply.code
            assert (await h.stats()).submit_count == 0
        finally:
            await h.close()

    asyncio.run(run())
