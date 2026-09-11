"""Backend-neutral sequential reachability for perception-driven task points."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from ..core.domain import State
from ..core.dynamic_pick import (
    DYNAMIC_REACHABILITY_STATES,
    CupPoseSample,
    DynamicPickError,
    DynamicPickTemplate,
    resolve_motion_targets,
)
from ..core.task_geometry import Pose7
from ..core.task_points import TaskPoint
from ..ports.evidence import PoseEvidence
from ..ports.robot_control import JointStateEvidence

_UNKNOWN_FAILURE_CODES = frozenset(
    {
        "SCENE_STALE",
        "JOINT_STATE_STALE",
        "JOINT_STATE_UNAVAILABLE",
        "PLANNER_UNAVAILABLE",
        "PLAN_TIMEOUT",
        "TERMINAL_STATE_UNAVAILABLE",
    }
)

_SO101_GRIPPER_JOINT = "6"
_SO101_PREOPEN_Q6 = 0.465038


class ReachabilityStatus(StrEnum):
    REACHABLE = "REACHABLE"
    UNREACHABLE = "UNREACHABLE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class SegmentPlanReceipt:
    accepted: bool
    terminal_state: JointStateEvidence | None
    moveit_error_code: int | None
    failure_code: str | None
    collision_pairs: tuple[tuple[str, str], ...] = ()
    planning_receipts: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class ReachabilitySegment:
    state: State
    target: PoseEvidence
    accepted: bool
    moveit_error_code: int | None
    failure_code: str | None
    collision_pairs: tuple[tuple[str, str], ...]
    planning_receipts: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True, slots=True)
class ReachabilityReport:
    point_id: str
    status: ReachabilityStatus
    segments: tuple[ReachabilitySegment, ...]
    first_failure_code: str | None
    scene_revision: int | None


class ReachabilityPlannerPort(Protocol):
    def plan(
        self,
        state: State,
        target: PoseEvidence,
        start: JointStateEvidence,
        cup_pose_world: PoseEvidence,
        timeout_s: float,
    ) -> SegmentPlanReceipt: ...


def prepare_reachability_start_state(
    observed: JointStateEvidence,
) -> JointStateEvidence:
    """Model the real PREPARE_OPEN_GRIPPER predecessor for plan-only checks."""

    if _SO101_GRIPPER_JOINT not in observed.names:
        raise ValueError("GRIPPER_JOINT_STATE_UNAVAILABLE")
    positions = list(observed.positions_rad)
    positions[observed.names.index(_SO101_GRIPPER_JOINT)] = _SO101_PREOPEN_Q6
    return JointStateEvidence(
        observed.names,
        tuple(positions),
        observed.observed_monotonic_s,
    )


def _report(
    point: TaskPoint,
    status: ReachabilityStatus,
    segments: list[ReachabilitySegment],
    failure_code: str | None,
    scene_revision: int | None,
) -> ReachabilityReport:
    return ReachabilityReport(
        point_id=point.id,
        status=status,
        segments=tuple(segments),
        first_failure_code=failure_code,
        scene_revision=scene_revision,
    )


def check_task_reachability(
    point: TaskPoint,
    template: DynamicPickTemplate,
    start_state: JointStateEvidence | None,
    planner: ReachabilityPlannerPort,
    *,
    scene_revision: int | None = None,
) -> ReachabilityReport:
    """Plan all seven dynamic motion states without executing any trajectory."""

    if start_state is None:
        return _report(
            point,
            ReachabilityStatus.UNKNOWN,
            [],
            "JOINT_STATE_UNAVAILABLE",
            scene_revision,
        )

    cup_pose_world = PoseEvidence(
        point.cup_position_world_m,
        (0.0, 0.0, 0.0, 1.0),
    )
    sample = CupPoseSample(
        frame_id="world",
        source_stamp_ns=1,
        received_monotonic_s=0.0,
        pose_world=Pose7((*point.cup_position_world_m, 0.0, 0.0, 0.0, 1.0)),
    )
    try:
        targets = resolve_motion_targets(sample, template)
    except DynamicPickError:
        return _report(
            point,
            ReachabilityStatus.UNREACHABLE,
            [],
            "TARGET_RESOLUTION_FAILED",
            scene_revision,
        )

    segments: list[ReachabilitySegment] = []
    current_start = start_state
    prepare_horizon = getattr(planner, "prepare_horizon", None)
    if callable(prepare_horizon):
        try:
            prepare_horizon(targets, current_start)
        except Exception:
            return _report(
                point,
                ReachabilityStatus.UNKNOWN,
                [],
                "PLANNER_UNAVAILABLE",
                scene_revision,
            )
    for state in DYNAMIC_REACHABILITY_STATES:
        target = targets.for_state(state)
        try:
            receipt = planner.plan(
                state,
                target,
                current_start,
                cup_pose_world,
                template.planning_timeout_s,
            )
        except Exception:
            failure_code = "PLANNER_UNAVAILABLE"
            segments.append(
                ReachabilitySegment(
                    state,
                    target,
                    False,
                    None,
                    failure_code,
                    (),
                )
            )
            return _report(
                point,
                ReachabilityStatus.UNKNOWN,
                segments,
                failure_code,
                scene_revision,
            )

        failure_code = receipt.failure_code
        accepted = receipt.accepted and receipt.terminal_state is not None
        if receipt.accepted and receipt.terminal_state is None:
            failure_code = "TERMINAL_STATE_UNAVAILABLE"
        segments.append(
            ReachabilitySegment(
                state=state,
                target=target,
                accepted=accepted,
                moveit_error_code=receipt.moveit_error_code,
                failure_code=failure_code,
                collision_pairs=receipt.collision_pairs,
                planning_receipts=receipt.planning_receipts,
            )
        )
        if not accepted:
            status = (
                ReachabilityStatus.UNKNOWN
                if failure_code in _UNKNOWN_FAILURE_CODES
                else ReachabilityStatus.UNREACHABLE
            )
            return _report(
                point,
                status,
                segments,
                failure_code or "MOVEIT_PLAN_FAILED",
                scene_revision,
            )
        current_start = receipt.terminal_state

    return _report(
        point,
        ReachabilityStatus.REACHABLE,
        segments,
        None,
        scene_revision,
    )
