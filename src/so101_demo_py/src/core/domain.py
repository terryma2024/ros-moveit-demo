"""ROS-free public domain model for the SO-101 workflow."""

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class State(StrEnum):
    IDLE = "IDLE"
    PREPARE_OPEN_GRIPPER = "PREPARE_OPEN_GRIPPER"
    MOVE_ABOVE_OBJECT = "MOVE_ABOVE_OBJECT"
    DESCEND = "DESCEND"
    CLOSE_GRIPPER = "CLOSE_GRIPPER"
    WAIT_GRASP_STABLE = "WAIT_GRASP_STABLE"
    MICRO_LIFT = "MICRO_LIFT"
    WAIT_MICRO_LIFT_STABLE = "WAIT_MICRO_LIFT_STABLE"
    VERIFY_PHYSICAL_GRASP = "VERIFY_PHYSICAL_GRASP"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    ATTACH_MOVEIT = "ATTACH_MOVEIT"
    LIFT = "LIFT"
    MOVE_ABOVE_PLACE = "MOVE_ABOVE_PLACE"
    DESCEND_TO_PLACE = "DESCEND_TO_PLACE"
    DETACH_MOVEIT = "DETACH_MOVEIT"
    OPEN_GRIPPER = "OPEN_GRIPPER"
    WAIT_RELEASE_SETTLE = "WAIT_RELEASE_SETTLE"
    VALIDATE_FINAL_PLACEMENT = "VALIDATE_FINAL_PLACEMENT"
    SYNC_WORLD_OBJECT = "SYNC_WORLD_OBJECT"
    RETREAT = "RETREAT"
    RECOVER_LIFT_TO_SAFE_HEIGHT = "RECOVER_LIFT_TO_SAFE_HEIGHT"
    RECOVER_MOVE_ABOVE_PICK = "RECOVER_MOVE_ABOVE_PICK"
    RECOVER_DESCEND_TO_PICK = "RECOVER_DESCEND_TO_PICK"
    RECOVER_OPEN_GRIPPER = "RECOVER_OPEN_GRIPPER"
    RECOVER_DETACH_GAZEBO = "RECOVER_DETACH_GAZEBO"
    RECOVER_DETACH_MOVEIT = "RECOVER_DETACH_MOVEIT"
    RECOVER_SYNC_WORLD_OBJECT = "RECOVER_SYNC_WORLD_OBJECT"
    RECOVER_RETREAT = "RECOVER_RETREAT"
    DONE = "DONE"
    ERROR = "ERROR"


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    PLAN_ONLY_COMPLETE = "PLAN_ONLY_COMPLETE"
    CHECKPOINT_COMPLETE = "CHECKPOINT_COMPLETE"
    DONE = "DONE"
    ERROR = "ERROR"


class ExecutionRunStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    INVALID = "INVALID"
    REJECTED = "REJECTED"


class QualificationStatus(StrEnum):
    QUALIFIED = "QUALIFIED"
    NOT_QUALIFIED = "NOT_QUALIFIED"


class RunMode(StrEnum):
    DRY_RUN = "dry_run"
    PLAN_ONLY = "plan_only"
    EXECUTE = "execute"


class ActionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    TIMED_OUT = "TIMED_OUT"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class FailureCategory(StrEnum):
    CONFIGURATION = "CONFIGURATION"
    OBSERVATION = "OBSERVATION"
    PRECONDITION = "PRECONDITION"
    PLANNING = "PLANNING"
    PLAN_VALIDATION = "PLAN_VALIDATION"
    EXECUTION = "EXECUTION"
    POSTCONDITION = "POSTCONDITION"
    COLLISION = "COLLISION"
    TF = "TF"
    GRIPPER = "GRIPPER"
    GAZEBO_ATTACHMENT = "GAZEBO_ATTACHMENT"
    MOVEIT_SCENE = "MOVEIT_SCENE"
    WORLD_INCONSISTENCY = "WORLD_INCONSISTENCY"
    CHECKPOINT = "CHECKPOINT"
    RESUME_VALIDATION = "RESUME_VALIDATION"
    INTERNAL = "INTERNAL"


@dataclass(frozen=True, slots=True)
class Failure:
    category: FailureCategory = FailureCategory.INTERNAL
    code: str = ""
    message: str = ""
    metrics: Mapping[str, float] = field(default_factory=lambda: MappingProxyType({}))


@dataclass(frozen=True, slots=True)
class ActionResult:
    status: ActionStatus = ActionStatus.FAILED
    failure: Failure | None = None


@dataclass(frozen=True, slots=True)
class RunRequest:
    mode: RunMode = RunMode.DRY_RUN
    stop_after: State | None = None
    resume: bool = False
    fail_at: State | None = None
    max_state_transitions: int = 100
    single_step: bool = False
    force_continue: bool = False
    plan_only_state: State | None = None


@dataclass(frozen=True, slots=True)
class RunResult:
    status: RunStatus = RunStatus.ERROR
    current_state: State = State.ERROR
    next_state: State | None = None
    failure: Failure | None = None
    transition_count: int = 0
    state_trace: tuple[State, ...] = ()
