import asyncio
from unittest.mock import AsyncMock

import pytest

from so101_teleop.control import (
    CommandCoordinator,
    CommandIdReused,
    PlanRejected,
    PlanStore,
)
from so101_teleop.models import CommandResult, PlanSummary


def result(command_id="c1"):
    return CommandResult(command_id=command_id, accepted=True, succeeded=True, code="OK", message="ok")


def test_duplicate_command_runs_once_and_returns_cached_result():
    """Removing idempotency would execute the same robot mutation twice after a retry."""
    async def scenario():
        coordinator = CommandCoordinator()
        operation = AsyncMock(return_value=result())

        first = await coordinator.run("c1", "fingerprint", operation)
        second = await coordinator.run("c1", "fingerprint", operation)

        assert first == second
        assert operation.await_count == 1

    asyncio.run(scenario())


def test_reused_command_id_with_different_payload_is_rejected():
    """Allowing a changed payload under one command ID could replay a different motion."""
    async def scenario():
        coordinator = CommandCoordinator()
        await coordinator.run("c1", "first", AsyncMock(return_value=result()))

        with pytest.raises(CommandIdReused, match="COMMAND_ID_REUSED"):
            await coordinator.run("c1", "second", AsyncMock(return_value=result()))

    asyncio.run(scenario())


def test_changed_scene_invalidates_plan():
    """Ignoring Planning Scene revisions can execute a path against the wrong obstacles."""
    store = PlanStore()
    plan = PlanSummary(
        plan_id="p1",
        start_fingerprint="joint-a",
        target_fingerprint="target-a",
        scene_revision=4,
        expires_at_monotonic=10_000.0,
    )
    store.put(plan)

    with pytest.raises(PlanRejected, match="PLAN_STALE_SCENE"):
        store.require_executable("joint-a", 5, now=1.0)


def test_busy_mutation_is_rejected_instead_of_running_concurrently():
    """Removing the single writer lock permits two simulation mutations to overlap."""
    async def scenario():
        coordinator = CommandCoordinator()
        started = asyncio.Event()
        release = asyncio.Event()

        async def slow_operation():
            started.set()
            await release.wait()
            return result("slow")

        task = asyncio.create_task(coordinator.run("slow", "one", slow_operation))
        await started.wait()
        with pytest.raises(PlanRejected, match="SERVER_BUSY"):
            await coordinator.run("fast", "two", AsyncMock(return_value=result("fast")))
        release.set()
        await task

    asyncio.run(scenario())
