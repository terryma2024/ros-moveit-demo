"""MoveIt planning adapter with a single collision evidence path for joint and TCP goals."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Dict, List, Protocol

from .models import CollisionPair, JointPlanRequest, PlanSummary, TcpPlanRequest, TelemetrySnapshot


class MoveItBackend(Protocol):
    async def solve_ik(self, target, seed: Dict[str, float]) -> Dict[str, float]: ...
    async def plan_joints(self, target: Dict[str, float], start: Dict[str, float]) -> List[Dict[str, float]]: ...
    async def validate(self, joints: Dict[str, float], waypoint_index: int) -> List[CollisionPair]: ...


@dataclass(frozen=True)
class GatewayPlanResult:
    code: str
    plan: PlanSummary
    collisions: List[CollisionPair]


class MoveItGateway:
    def __init__(self, backend: MoveItBackend, plan_ttl_s: float = 30.0) -> None:
        self._backend = backend
        self._plan_ttl_s = plan_ttl_s

    async def plan_joints(self, request: JointPlanRequest, snapshot: TelemetrySnapshot) -> GatewayPlanResult:
        target = {name: value for name, value in request.target_joints_rad.items() if name in {"1", "2", "3", "4", "5"}}
        if set(target) != {"1", "2", "3", "4", "5"}:
            return self._result("ARM_TARGET_INCOMPLETE", {}, snapshot, [])
        start = {name: snapshot.joints[name].position_rad for name in map(str, range(1, 6))}
        trajectory = await self._backend.plan_joints(target, start)
        collisions = await self._trajectory_collisions(trajectory)
        return self._result("TRAJECTORY_COLLISION" if collisions else "OK", target, snapshot, collisions,
                            len(trajectory))

    async def plan_tcp(self, request: TcpPlanRequest, snapshot: TelemetrySnapshot) -> GatewayPlanResult:
        seed = {name: snapshot.joints[name].position_rad for name in map(str, range(1, 6))}
        solution = await self._backend.solve_ik(request.target, seed)
        arm_request = JointPlanRequest(command_id=request.command_id, target_joints_rad=solution)
        result = await self.plan_joints(arm_request, snapshot)
        return GatewayPlanResult(result.code, result.plan.copy(update={"ik_solution_rad": solution}), result.collisions)

    async def _trajectory_collisions(self, trajectory: List[Dict[str, float]]) -> List[CollisionPair]:
        for index, waypoint in enumerate(trajectory):
            collisions = await self._backend.validate(waypoint, index)
            if collisions:
                return [collision.copy(update={"waypoint_index": index}) for collision in collisions]
        return []

    def _result(self, code: str, target: Dict[str, float], snapshot: TelemetrySnapshot,
                collisions: List[CollisionPair], trajectory_points: int = 0) -> GatewayPlanResult:
        start = {name: snapshot.joints[name].position_rad for name in map(str, range(1, 6))}
        summary = PlanSummary(
            plan_id=str(uuid.uuid4()),
            start_fingerprint=repr(sorted(start.items())),
            target_fingerprint=repr(sorted(target.items())),
            scene_revision=snapshot.scene_revision,
            expires_at_monotonic=time.monotonic() + self._plan_ttl_s,
            trajectory_points=trajectory_points,
            max_joint_delta_rad=max((abs(target[name] - start[name]) for name in target), default=0.0),
            collisions=collisions,
        )
        return GatewayPlanResult(code, summary, collisions)
