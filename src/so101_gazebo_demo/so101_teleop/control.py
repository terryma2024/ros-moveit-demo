"""Serialized mutation, lease and in-memory plan lifecycle gates."""

from __future__ import annotations

import ast
import asyncio
import time
from typing import Awaitable, Callable, Dict, Tuple

from .models import CommandResult, PlanSummary


class PlanRejected(RuntimeError):
    pass


class CommandIdReused(PlanRejected):
    pass


START_FINGERPRINT_TOLERANCE_STEPS = 10


def _start_fingerprints_match(planned: str, live: str) -> bool:
    if planned == live:
        return True
    try:
        planned_joints = dict(ast.literal_eval(planned))
        live_joints = dict(ast.literal_eval(live))
    except (SyntaxError, ValueError, TypeError):
        return False
    if planned_joints.keys() != live_joints.keys():
        return False
    return all(
        isinstance(planned_joints[name], int)
        and isinstance(live_joints[name], int)
        and abs(planned_joints[name] - live_joints[name]) < START_FINGERPRINT_TOLERANCE_STEPS
        for name in planned_joints
    )


class CommandCoordinator:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._completed: Dict[str, Tuple[str, CommandResult]] = {}

    async def run(
        self, command_id: str, fingerprint: str, operation: Callable[[], Awaitable[CommandResult]]
    ) -> CommandResult:
        cached = self._completed.get(command_id)
        if cached:
            if cached[0] != fingerprint:
                raise CommandIdReused("COMMAND_ID_REUSED")
            return cached[1]
        if self._lock.locked():
            raise PlanRejected("SERVER_BUSY")
        async with self._lock:
            cached = self._completed.get(command_id)
            if cached:
                if cached[0] != fingerprint:
                    raise CommandIdReused("COMMAND_ID_REUSED")
                return cached[1]
            result = await operation()
            self._completed[command_id] = (fingerprint, result)
            return result

    def clear(self) -> None:
        self._completed.clear()


class PlanStore:
    def __init__(self) -> None:
        self._latest: PlanSummary | None = None

    def put(self, plan: PlanSummary) -> None:
        self._latest = plan

    def clear(self) -> None:
        self._latest = None

    def require_executable(self, start_fingerprint: str, scene_revision: int, plan_id: str | None = None, now: float | None = None) -> PlanSummary:
        if self._latest is None:
            raise PlanRejected("PLAN_NOT_FOUND")
        if plan_id is not None and self._latest.plan_id != plan_id:
            raise PlanRejected("PLAN_NOT_LATEST")
        if self._latest.scene_revision != scene_revision:
            raise PlanRejected("PLAN_STALE_SCENE")
        if not _start_fingerprints_match(self._latest.start_fingerprint, start_fingerprint):
            raise PlanRejected("PLAN_STALE_START")
        if self._latest.expires_at_monotonic <= (time.monotonic() if now is None else now):
            raise PlanRejected("PLAN_EXPIRED")
        if self._latest.collisions:
            raise PlanRejected("PLAN_COLLISION")
        return self._latest
