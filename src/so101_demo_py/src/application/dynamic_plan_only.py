"""Single-state dynamic MoveIt plan-only application boundary."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

from ..core.domain import State
from ..core.workflow import SO101_WORKFLOW
from ..ports.evidence import PoseEvidence
from ..ports.robot_control import PlanResult, RobotControlPort, TcpMotionRequest
from ..ports.cup_scene_observation import CupSceneObservationPort
from .cup_pose_preflight import validate_cup_scene


class DynamicPlanOnlyError(ValueError):
    pass


class MotionTargetProvider(Protocol):
    def target_for(self, state: State) -> PoseEvidence: ...


@dataclass(frozen=True, slots=True)
class DynamicPlanningOptions:
    planning_frame: str
    planning_group: str
    tcp_link: str
    position_tolerance_m: float
    orientation_tolerance_rad: tuple[float, float, float]
    planning_timeout_s: float
    velocity_scaling: float
    acceleration_scaling: float

    def __post_init__(self) -> None:
        values = (
            self.position_tolerance_m,
            *self.orientation_tolerance_rad,
            self.planning_timeout_s,
            self.velocity_scaling,
            self.acceleration_scaling,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in values):
            raise DynamicPlanOnlyError("DYNAMIC_PLANNING_OPTIONS_INVALID")


def plan_dynamic_state(
    *,
    state: State,
    provider: MotionTargetProvider,
    control: RobotControlPort,
    options: DynamicPlanningOptions,
) -> PlanResult:
    if state not in SO101_WORKFLOW.plan_only_states:
        raise DynamicPlanOnlyError(f"PLAN_ONLY_STATE_UNSUPPORTED: {state.value}")
    target = provider.target_for(state)
    return control.plan_tcp_motion(
        TcpMotionRequest(
            target_pose=target,
            timeout_s=options.planning_timeout_s,
            planning_frame=options.planning_frame,
            planning_group=options.planning_group,
            tcp_link=options.tcp_link,
            position_tolerance_m=options.position_tolerance_m,
            orientation_tolerance_rad=options.orientation_tolerance_rad,
            velocity_scaling=options.velocity_scaling,
            acceleration_scaling=options.acceleration_scaling,
        )
    )


def plan_dynamic_state_with_scene_gates(
    *,
    state: State,
    provider: MotionTargetProvider,
    control: RobotControlPort,
    options: DynamicPlanningOptions,
    scene: CupSceneObservationPort,
    sample,
    template,
) -> tuple[PlanResult, object, object]:
    before = scene.observe(options.planning_timeout_s)
    validate_cup_scene(sample, before, template)
    plan = plan_dynamic_state(state=state, provider=provider, control=control, options=options)
    if not plan.accepted:
        return plan, before, None
    after = scene.observe(options.planning_timeout_s)
    validate_cup_scene(sample, after, template)
    return plan, before, after
