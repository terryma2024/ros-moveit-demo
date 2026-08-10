"""Deterministic ROS-free state-machine runner."""

import json
import math
import os
import secrets
import uuid
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .domain import (
    ActionResult,
    ActionStatus,
    Failure,
    FailureCategory,
    RunMode,
    RunRequest,
    RunResult,
    RunStatus,
    State,
)
from .simulation.protocols import WorldObserver
from .simulation.types import SimulationEvidence
from .workflow import SO101_WORKFLOW, resolve_transition


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    request: RunRequest
    state: State
    transition_count: int


class CheckpointPhase(StrEnum):
    FORWARD = "FORWARD"
    RECOVERY = "RECOVERY"


Pose = tuple[float, float, float, float, float, float, float]


@dataclass(frozen=True, slots=True)
class ExpectedWorldState:
    tcp_pose_world: Pose = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0)
    gripper_open: bool = False
    joint_positions: Mapping[str, float] = field(default_factory=dict)
    moveit_world_object_poses: Mapping[str, Pose] = field(default_factory=dict)
    moveit_task_object_attached: bool | None = None
    simulator_backend: str = "mujoco"
    simulator_task_object_pose_world: Pose | None = None
    simulator_task_object_constrained: bool | None = False
    simulator_task_object_stationary: bool | None = None
    task_object_supported: bool | None = None
    gripper_task_object_contact: bool | None = None
    required_world_objects: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class WorkflowCheckpoint:
    run_id: str
    sequence: int
    source_mode: RunMode
    phase: CheckpointPhase
    last_completed_state: State
    failed_state: State | None
    next_state: State
    original_failure: Failure | None
    expected: ExpectedWorldState
    policy_bundle_sha256: str
    simulation_session_id: str
    resumable: bool
    release_epoch_id: str | None = None
    release_marker_sequence: int | None = None
    schema_version: int = 5


class StateAction(Protocol):
    def run(self, context: ExecutionContext) -> ActionResult: ...


class CheckpointStore(Protocol):
    def commit(self, checkpoint: WorkflowCheckpoint) -> Failure | None: ...

    def load(self) -> tuple[WorkflowCheckpoint | None, Failure | None]: ...


def _checkpoint_failure(code: str, message: str) -> Failure:
    return Failure(FailureCategory.CHECKPOINT, code, message)


def _resume_failure(code: str, message: str) -> Failure:
    return Failure(FailureCategory.RESUME_VALIDATION, code, message)


def _validate_resume_world(
    expected: ExpectedWorldState,
    evidence: SimulationEvidence,
    observed_world: ExpectedWorldState | None,
    *,
    position_tolerance_m: float,
    orientation_tolerance_rad: float,
    stationary_velocity_tolerance: float,
    joint_tolerance_rad: float,
) -> Failure | None:
    expected_pose = expected.simulator_task_object_pose_world
    observed = evidence.object_state
    if expected_pose is not None:
        if not _poses_match(
            expected_pose,
            observed.position_world + observed.orientation_xyzw,
            position_tolerance_m,
            orientation_tolerance_rad,
        ):
            return _resume_failure(
                "RESUME_WORLD_MISMATCH",
                "task-object pose does not match checkpoint",
            )
    if expected.simulator_task_object_stationary is True and (
        max(abs(value) for value in observed.linear_velocity_world) > stationary_velocity_tolerance
        or max(abs(value) for value in observed.angular_velocity_world)
        > stationary_velocity_tolerance
    ):
        return _resume_failure(
            "RESUME_WORLD_MISMATCH",
            "task object is not stationary as required by checkpoint",
        )
    observed_gripper_contact = bool(
        evidence.left_fingertip_contacts or evidence.right_fingertip_contacts
    )
    if (
        expected.gripper_task_object_contact is not None
        and expected.gripper_task_object_contact != observed_gripper_contact
    ):
        return _resume_failure(
            "RESUME_WORLD_MISMATCH",
            "gripper contact does not match checkpoint",
        )
    if observed_world is None:
        return None
    if not _poses_match(
        expected.tcp_pose_world,
        observed_world.tcp_pose_world,
        position_tolerance_m,
        orientation_tolerance_rad,
    ):
        return _resume_failure("RESUME_WORLD_MISMATCH", "TCP pose does not match checkpoint")
    if expected.gripper_open != observed_world.gripper_open:
        return _resume_failure(
            "RESUME_WORLD_MISMATCH",
            "gripper state does not match checkpoint",
        )
    for joint, expected_position in expected.joint_positions.items():
        observed_position = observed_world.joint_positions.get(joint)
        if (
            observed_position is None
            or abs(expected_position - observed_position) > joint_tolerance_rad
        ):
            return _resume_failure(
                "RESUME_WORLD_MISMATCH",
                f"joint {joint} does not match checkpoint",
            )
    for object_name, expected_object_pose in expected.moveit_world_object_poses.items():
        observed_object_pose = observed_world.moveit_world_object_poses.get(object_name)
        if observed_object_pose is None or not _poses_match(
            expected_object_pose,
            observed_object_pose,
            position_tolerance_m,
            orientation_tolerance_rad,
        ):
            return _resume_failure(
                "RESUME_WORLD_MISMATCH",
                f"MoveIt world object {object_name} does not match checkpoint",
            )
    if (
        expected.moveit_task_object_attached is not None
        and expected.moveit_task_object_attached != observed_world.moveit_task_object_attached
    ):
        return _resume_failure(
            "RESUME_WORLD_MISMATCH",
            "MoveIt attachment does not match checkpoint",
        )
    if (
        expected.task_object_supported is not None
        and expected.task_object_supported != observed_world.task_object_supported
    ):
        return _resume_failure(
            "RESUME_WORLD_MISMATCH",
            "task-object support does not match checkpoint",
        )
    if not set(expected.required_world_objects).issubset(observed_world.moveit_world_object_poses):
        return _resume_failure(
            "RESUME_WORLD_MISMATCH",
            "required MoveIt world objects are missing",
        )
    return None


def _poses_match(
    expected: Pose,
    observed: Pose,
    position_tolerance_m: float,
    orientation_tolerance_rad: float,
) -> bool:
    expected_q = expected[3:]
    observed_q = observed[3:]
    expected_norm = math.sqrt(sum(value * value for value in expected_q))
    observed_norm = math.sqrt(sum(value * value for value in observed_q))
    if expected_norm == 0.0 or observed_norm == 0.0:
        return False
    quaternion_dot = abs(
        sum(first * second for first, second in zip(expected_q, observed_q))
        / (expected_norm * observed_norm)
    )
    orientation_error = 2.0 * math.acos(max(-1.0, min(1.0, quaternion_dot)))
    return (
        math.dist(expected[:3], observed[:3]) <= position_tolerance_m
        and orientation_error <= orientation_tolerance_rad
    )


def _finite(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("nonfinite numeric value")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError("nonfinite numeric value")
    return converted


def _integer(value: Any) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("invalid nonnegative integer")
    return value


def _bool(value: Any) -> bool:
    if not isinstance(value, bool):
        raise ValueError("invalid boolean")
    return value


def _optional_bool(value: Any) -> bool | None:
    return None if value is None else _bool(value)


def _pose(value: Any) -> Pose:
    if not isinstance(value, list) or len(value) != 7:
        raise ValueError("pose must have seven values")
    return tuple(_finite(item) for item in value)  # type: ignore[return-value]


def _failure_json(value: Failure | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "category": value.category.value,
        "code": value.code,
        "message": value.message,
        "metrics": dict(value.metrics),
    }


def _expected_json(value: ExpectedWorldState) -> dict[str, Any]:
    return {
        "tcp_pose_world": list(value.tcp_pose_world),
        "gripper_open": value.gripper_open,
        "joint_positions": dict(value.joint_positions),
        "moveit_world_object_poses": {
            key: list(pose) for key, pose in value.moveit_world_object_poses.items()
        },
        "moveit_task_object_attached": value.moveit_task_object_attached,
        "simulator_backend": value.simulator_backend,
        "simulator_task_object_pose_world": (
            None
            if value.simulator_task_object_pose_world is None
            else list(value.simulator_task_object_pose_world)
        ),
        "simulator_task_object_constrained": value.simulator_task_object_constrained,
        "simulator_task_object_stationary": value.simulator_task_object_stationary,
        "task_object_supported": value.task_object_supported,
        "gripper_task_object_contact": value.gripper_task_object_contact,
        "required_world_objects": list(value.required_world_objects),
    }


def _atomic_write(path: Path, payload: bytes) -> Failure | None:
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
    except OSError as error:
        return _checkpoint_failure("CHECKPOINT_DIRECTORY_FAILED", str(error))
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    descriptor: int | None = None
    try:
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(descriptor, payload[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(descriptor)
        os.close(descriptor)
        descriptor = None
    except OSError as error:
        if descriptor is not None:
            os.close(descriptor)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return _checkpoint_failure("CHECKPOINT_WRITE_FAILED", str(error))
    try:
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        return _checkpoint_failure("CHECKPOINT_RENAME_FAILED", str(error))
    directory_descriptor: int | None = None
    try:
        directory_descriptor = os.open(path.parent, os.O_RDONLY)
        os.fsync(directory_descriptor)
    except OSError as error:
        return _checkpoint_failure("CHECKPOINT_FSYNC_FAILED", str(error))
    finally:
        if directory_descriptor is not None:
            os.close(directory_descriptor)
    return None


class FileCheckpointStore:
    """Atomically persist backend-neutral workflow transition checkpoints."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def commit(self, checkpoint: WorkflowCheckpoint) -> Failure | None:
        failure = checkpoint.original_failure
        document = {
            "schema_version": checkpoint.schema_version,
            "run_id": checkpoint.run_id,
            "sequence": checkpoint.sequence,
            "source_mode": checkpoint.source_mode.value,
            "phase": checkpoint.phase.value,
            "last_completed_state": checkpoint.last_completed_state.value,
            "failed_state": (
                None if checkpoint.failed_state is None else checkpoint.failed_state.value
            ),
            "next_state": checkpoint.next_state.value,
            "original_failure": _failure_json(failure),
            "expected": _expected_json(checkpoint.expected),
            "policy_bundle_sha256": checkpoint.policy_bundle_sha256,
            "simulation_session_id": checkpoint.simulation_session_id,
            "resumable": checkpoint.resumable,
            "release_epoch_id": checkpoint.release_epoch_id,
            "release_marker_sequence": checkpoint.release_marker_sequence,
        }
        try:
            if checkpoint.schema_version != 5 or checkpoint.sequence < 0:
                raise ValueError("invalid schema or sequence")
            if checkpoint.expected.simulator_backend != "mujoco":
                raise ValueError("invalid simulator backend")
            if checkpoint.expected.simulator_task_object_constrained is not False:
                raise ValueError("MuJoCo checkpoint must prove unconstrained object")
            if checkpoint.release_epoch_id is not None:
                if not checkpoint.release_epoch_id or checkpoint.release_marker_sequence is None:
                    raise ValueError("release epoch requires marker sequence")
                if checkpoint.release_marker_sequence < 0 or checkpoint.resumable:
                    raise ValueError("active release epoch must be non-resumable")
            elif checkpoint.release_marker_sequence is not None:
                raise ValueError("release marker requires epoch")
            payload = json.dumps(
                document,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        except (TypeError, ValueError) as error:
            return _checkpoint_failure("CHECKPOINT_INVALID_DATA", str(error))
        return _atomic_write(self.path, payload)

    def load(self) -> tuple[WorkflowCheckpoint | None, Failure | None]:
        if not self.path.exists():
            return None, _checkpoint_failure("CHECKPOINT_NOT_FOUND", "checkpoint does not exist")
        try:
            document = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            return None, _checkpoint_failure("CHECKPOINT_PARSE_FAILED", str(error))
        try:
            schema_version = _integer(document["schema_version"])
            if schema_version not in {4, 5}:
                raise ValueError("incompatible checkpoint schema")
            failure_document = document["original_failure"]
            failure = (
                None
                if failure_document is None
                else Failure(
                    FailureCategory(failure_document["category"]),
                    str(failure_document["code"]),
                    str(failure_document["message"]),
                    {
                        str(key): _finite(value)
                        for key, value in failure_document["metrics"].items()
                    },
                )
            )
            expected_document = document["expected"]
            if schema_version == 4:
                constrained = _optional_bool(expected_document["gazebo_task_object_attached"])
                if constrained is True:
                    raise ValueError("v4 Gazebo-constrained object cannot be migrated")
                simulator_pose = expected_document["gazebo_task_object_pose_world"]
                simulator_stationary = expected_document["gazebo_task_object_stationary"]
            else:
                if str(expected_document["simulator_backend"]) != "mujoco":
                    raise ValueError("simulator backend mismatch")
                constrained = _optional_bool(expected_document["simulator_task_object_constrained"])
                simulator_pose = expected_document["simulator_task_object_pose_world"]
                simulator_stationary = expected_document["simulator_task_object_stationary"]
            if schema_version == 5 and constrained is not False:
                raise ValueError("physical workflow requires unconstrained task object")
            expected_world = ExpectedWorldState(
                tcp_pose_world=_pose(expected_document["tcp_pose_world"]),
                gripper_open=_bool(expected_document["gripper_open"]),
                joint_positions={
                    str(key): _finite(value)
                    for key, value in expected_document["joint_positions"].items()
                },
                moveit_world_object_poses={
                    str(key): _pose(value)
                    for key, value in expected_document["moveit_world_object_poses"].items()
                },
                moveit_task_object_attached=_optional_bool(
                    expected_document["moveit_task_object_attached"]
                ),
                simulator_backend="mujoco",
                simulator_task_object_pose_world=(
                    None if simulator_pose is None else _pose(simulator_pose)
                ),
                simulator_task_object_constrained=constrained,
                simulator_task_object_stationary=_optional_bool(simulator_stationary),
                task_object_supported=_optional_bool(expected_document["task_object_supported"]),
                gripper_task_object_contact=_optional_bool(
                    expected_document["gripper_task_object_contact"]
                ),
                required_world_objects=tuple(
                    str(value) for value in expected_document["required_world_objects"]
                ),
            )
            checkpoint = WorkflowCheckpoint(
                run_id=str(document["run_id"]),
                sequence=_integer(document["sequence"]),
                source_mode=RunMode(document["source_mode"]),
                phase=CheckpointPhase(document["phase"]),
                last_completed_state=State(document["last_completed_state"]),
                failed_state=(
                    None if document["failed_state"] is None else State(document["failed_state"])
                ),
                next_state=State(document["next_state"]),
                original_failure=failure,
                expected=expected_world,
                policy_bundle_sha256=str(document["policy_bundle_sha256"]),
                simulation_session_id=str(document["simulation_session_id"]),
                resumable=_bool(document["resumable"]),
                release_epoch_id=document["release_epoch_id"],
                release_marker_sequence=(
                    None
                    if document["release_marker_sequence"] is None
                    else _integer(document["release_marker_sequence"])
                ),
            )
            if checkpoint.release_epoch_id is not None and checkpoint.resumable:
                raise ValueError("active release epoch must be non-resumable")
        except (KeyError, TypeError, ValueError) as error:
            code = (
                "CHECKPOINT_INVALID_ENUM"
                if isinstance(error, ValueError) and "is not a valid" in str(error)
                else "CHECKPOINT_INCOMPATIBLE"
            )
            return None, _checkpoint_failure(code, str(error))
        return checkpoint, None


class StateMachineRunner:
    def __init__(
        self,
        actions: Mapping[State, StateAction],
        checkpoint_store: CheckpointStore | None = None,
        session_id: str = "",
        policy_bundle_sha256: str = "",
        world_observer: WorldObserver | None = None,
        expected_world_provider: Callable[[ExecutionContext], ExpectedWorldState] | None = None,
        observed_world_provider: Callable[[], ExpectedWorldState] | None = None,
        resume_position_tolerance_m: float = 0.003,
        resume_orientation_tolerance_rad: float = 0.07,
        resume_stationary_velocity_tolerance: float = 0.001,
        resume_joint_tolerance_rad: float = 0.002,
    ) -> None:
        self.actions = dict(actions)
        self.checkpoint_store = checkpoint_store
        self.session_id = session_id
        self.policy_bundle_sha256 = policy_bundle_sha256
        self.world_observer = world_observer
        self.expected_world_provider = expected_world_provider
        self.observed_world_provider = observed_world_provider
        self.resume_position_tolerance_m = resume_position_tolerance_m
        self.resume_orientation_tolerance_rad = resume_orientation_tolerance_rad
        self.resume_stationary_velocity_tolerance = resume_stationary_velocity_tolerance
        self.resume_joint_tolerance_rad = resume_joint_tolerance_rad
        self.release_epoch_id: str | None = None
        self.release_marker_sequence: int | None = None
        self.release_reset_epoch: int | None = None

    def _error(
        self,
        code: str,
        trace: list[State],
        count: int,
        category: FailureCategory = FailureCategory.INTERNAL,
    ) -> RunResult:
        return RunResult(
            RunStatus.ERROR,
            trace[-1],
            None,
            Failure(category, code),
            count,
            tuple(trace),
        )

    def _commit(
        self,
        request: RunRequest,
        completed: State,
        next_state: State,
        count: int,
        failure: Failure | None,
    ) -> Failure | None:
        if completed is State.OPEN_GRIPPER and self.release_epoch_id is None:
            self.release_epoch_id = str(uuid.uuid4())
            if self.world_observer is None:
                if request.mode is RunMode.EXECUTE:
                    return Failure(
                        FailureCategory.OBSERVATION,
                        "RELEASE_MARKER_OBSERVER_REQUIRED",
                    )
                self.release_marker_sequence = count
            else:
                try:
                    evidence = self.world_observer.snapshot()
                except Exception as error:
                    return Failure(
                        FailureCategory.OBSERVATION,
                        "RELEASE_MARKER_OBSERVATION_FAILED",
                        str(error),
                    )
                expected_session = self.session_id or "dry-run"
                if evidence.simulation_session_id != expected_session:
                    return Failure(
                        FailureCategory.OBSERVATION,
                        "RELEASE_MARKER_SESSION_MISMATCH",
                    )
                self.release_marker_sequence = evidence.publisher_sequence
                self.release_reset_epoch = evidence.reset_epoch
        if self.checkpoint_store is None:
            return None
        if self.expected_world_provider is None:
            if request.mode is RunMode.EXECUTE:
                return _checkpoint_failure(
                    "CHECKPOINT_EXPECTED_WORLD_REQUIRED",
                    "execute checkpoints require an expected-world provider",
                )
            expected_world = ExpectedWorldState()
        else:
            try:
                expected_world = self.expected_world_provider(
                    ExecutionContext(request, completed, count)
                )
            except Exception as error:
                return _checkpoint_failure("CHECKPOINT_EXPECTED_WORLD_FAILED", str(error))
            if not isinstance(expected_world, ExpectedWorldState):
                return _checkpoint_failure(
                    "CHECKPOINT_EXPECTED_WORLD_FAILED",
                    "expected-world provider returned the wrong type",
                )
        release_active = completed in {
            State.OPEN_GRIPPER,
            State.WAIT_RELEASE_SETTLE,
            State.VALIDATE_FINAL_PLACEMENT,
        }
        checkpoint = WorkflowCheckpoint(
            run_id=str(uuid.uuid4()),
            sequence=count,
            source_mode=request.mode,
            phase=(
                CheckpointPhase.RECOVERY
                if completed.name.startswith("RECOVER_")
                else CheckpointPhase.FORWARD
            ),
            last_completed_state=completed,
            failed_state=completed if failure is not None else None,
            next_state=next_state,
            original_failure=failure,
            expected=expected_world,
            policy_bundle_sha256=self.policy_bundle_sha256 or "unconfigured",
            simulation_session_id=self.session_id or "dry-run",
            resumable=not release_active,
            release_epoch_id=self.release_epoch_id if release_active else None,
            release_marker_sequence=(self.release_marker_sequence if release_active else None),
        )
        return self.checkpoint_store.commit(checkpoint)

    def run(self, request: RunRequest) -> RunResult:
        if request.force_continue:
            return self._error(
                "FORCE_CONTINUE_NOT_ALLOWED",
                [State.IDLE],
                0,
                FailureCategory.RESUME_VALIDATION,
            )
        if request.mode is RunMode.PLAN_ONLY:
            state = request.plan_only_state
            if state not in SO101_WORKFLOW.plan_only_states:
                return self._error(
                    "PLAN_ONLY_STATE_UNSUPPORTED",
                    [State.IDLE],
                    0,
                    FailureCategory.CONFIGURATION,
                )
            action = self.actions.get(state)
            if action is None:
                return self._error("ACTION_NOT_REGISTERED", [state], 0)
            result = action.run(ExecutionContext(request, state, 0))
            if result.status is not ActionStatus.SUCCEEDED:
                return RunResult(RunStatus.ERROR, state, None, result.failure, 1, (state,))
            return RunResult(
                RunStatus.PLAN_ONLY_COMPLETE,
                state,
                None,
                None,
                1,
                (state,),
            )

        if request.resume:
            if self.checkpoint_store is None:
                return self._error(
                    "RESUME_CHECKPOINT_REQUIRED",
                    [State.IDLE],
                    0,
                    FailureCategory.RESUME_VALIDATION,
                )
            checkpoint, load_failure = self.checkpoint_store.load()
            if load_failure is not None or checkpoint is None:
                failure = load_failure or _checkpoint_failure(
                    "CHECKPOINT_INCOMPATIBLE", "checkpoint did not load"
                )
                return RunResult(RunStatus.ERROR, State.IDLE, None, failure, 0, (State.IDLE,))
            if checkpoint.release_epoch_id is not None:
                return self._error(
                    "RESUME_RELEASE_EPOCH_ACTIVE",
                    [checkpoint.last_completed_state],
                    checkpoint.sequence,
                    FailureCategory.RESUME_VALIDATION,
                )
            if not checkpoint.resumable:
                return self._error(
                    "RESUME_CHECKPOINT_NOT_RESUMABLE",
                    [checkpoint.last_completed_state],
                    checkpoint.sequence,
                    FailureCategory.RESUME_VALIDATION,
                )
            if checkpoint.source_mode is not request.mode:
                return self._error(
                    "RESUME_MODE_MISMATCH",
                    [checkpoint.last_completed_state],
                    checkpoint.sequence,
                    FailureCategory.RESUME_VALIDATION,
                )
            expected_session = self.session_id or "dry-run"
            if checkpoint.simulation_session_id != expected_session:
                return self._error(
                    "RESUME_SESSION_MISMATCH",
                    [checkpoint.last_completed_state],
                    checkpoint.sequence,
                    FailureCategory.RESUME_VALIDATION,
                )
            if (
                self.policy_bundle_sha256
                and checkpoint.policy_bundle_sha256 != self.policy_bundle_sha256
            ):
                return self._error(
                    "RESUME_POLICY_MISMATCH",
                    [checkpoint.last_completed_state],
                    checkpoint.sequence,
                    FailureCategory.RESUME_VALIDATION,
                )
            if checkpoint.expected.simulator_backend != "mujoco":
                return self._error(
                    "RESUME_BACKEND_MISMATCH",
                    [checkpoint.last_completed_state],
                    checkpoint.sequence,
                    FailureCategory.RESUME_VALIDATION,
                )
            if checkpoint.expected.simulator_task_object_constrained is None:
                return self._error(
                    "RESUME_SIMULATOR_CONSTRAINT_UNKNOWN",
                    [checkpoint.last_completed_state],
                    checkpoint.sequence,
                    FailureCategory.RESUME_VALIDATION,
                )
            if checkpoint.expected.simulator_task_object_constrained is True:
                return self._error(
                    "RESUME_SIMULATOR_CONSTRAINT_PRESENT",
                    [checkpoint.last_completed_state],
                    checkpoint.sequence,
                    FailureCategory.RESUME_VALIDATION,
                )
            observed_world: ExpectedWorldState | None = None
            if request.mode is RunMode.EXECUTE:
                if self.observed_world_provider is None:
                    return self._error(
                        "RESUME_OBSERVATION_REQUIRED",
                        [checkpoint.last_completed_state],
                        checkpoint.sequence,
                        FailureCategory.RESUME_VALIDATION,
                    )
                try:
                    observed_world = self.observed_world_provider()
                except Exception as error:
                    return RunResult(
                        RunStatus.ERROR,
                        checkpoint.last_completed_state,
                        None,
                        _resume_failure("RESUME_OBSERVATION_FAILED", str(error)),
                        checkpoint.sequence,
                        (checkpoint.last_completed_state,),
                    )
                if not isinstance(observed_world, ExpectedWorldState):
                    return self._error(
                        "RESUME_OBSERVATION_FAILED",
                        [checkpoint.last_completed_state],
                        checkpoint.sequence,
                        FailureCategory.RESUME_VALIDATION,
                    )
            if self.world_observer is None:
                if request.mode is not RunMode.DRY_RUN:
                    return self._error(
                        "RESUME_OBSERVER_REQUIRED",
                        [checkpoint.last_completed_state],
                        checkpoint.sequence,
                        FailureCategory.RESUME_VALIDATION,
                    )
            else:
                try:
                    evidence = self.world_observer.snapshot()
                except Exception as error:
                    return RunResult(
                        RunStatus.ERROR,
                        checkpoint.last_completed_state,
                        None,
                        _resume_failure("RESUME_OBSERVATION_FAILED", str(error)),
                        checkpoint.sequence,
                        (checkpoint.last_completed_state,),
                    )
                if evidence.simulation_session_id != expected_session:
                    return self._error(
                        "RESUME_SESSION_MISMATCH",
                        [checkpoint.last_completed_state],
                        checkpoint.sequence,
                        FailureCategory.RESUME_VALIDATION,
                    )
                world_failure = _validate_resume_world(
                    checkpoint.expected,
                    evidence,
                    observed_world,
                    position_tolerance_m=self.resume_position_tolerance_m,
                    orientation_tolerance_rad=self.resume_orientation_tolerance_rad,
                    stationary_velocity_tolerance=(self.resume_stationary_velocity_tolerance),
                    joint_tolerance_rad=self.resume_joint_tolerance_rad,
                )
                if world_failure is not None:
                    return RunResult(
                        RunStatus.ERROR,
                        checkpoint.last_completed_state,
                        None,
                        world_failure,
                        checkpoint.sequence,
                        (checkpoint.last_completed_state,),
                    )
            trace = [checkpoint.last_completed_state, checkpoint.next_state]
            current = checkpoint.next_state
            count = checkpoint.sequence
            original_failure = checkpoint.original_failure
        else:
            trace = [State.IDLE, State.PREPARE_OPEN_GRIPPER]
            current = State.PREPARE_OPEN_GRIPPER
            count = 1
            original_failure = None
        while current not in SO101_WORKFLOW.terminal_states:
            if count >= request.max_state_transitions:
                return self._error("MAX_STATE_TRANSITIONS_EXCEEDED", trace, count)
            action = self.actions.get(current)
            if action is None:
                return self._error("ACTION_NOT_REGISTERED", trace, count)
            action_result = action.run(ExecutionContext(request, current, count))
            count += 1
            if action_result.status is not ActionStatus.SUCCEEDED and original_failure is None:
                original_failure = action_result.failure or Failure(
                    FailureCategory.INTERNAL, "ACTION_FAILED"
                )
            next_state = resolve_transition(current, action_result.status)
            commit_failure = self._commit(request, current, next_state, count, original_failure)
            if commit_failure is not None:
                return RunResult(
                    RunStatus.ERROR,
                    current,
                    None,
                    commit_failure,
                    count,
                    tuple(trace),
                )
            if next_state is State.VALIDATION_FAILED:
                trace.append(State.VALIDATION_FAILED)
                return RunResult(
                    RunStatus.CHECKPOINT_COMPLETE,
                    State.VALIDATION_FAILED,
                    State.ATTACH_MOVEIT,
                    original_failure,
                    count,
                    tuple(trace),
                )
            if request.stop_after is current or request.single_step:
                return RunResult(
                    RunStatus.CHECKPOINT_COMPLETE,
                    current,
                    next_state,
                    original_failure,
                    count,
                    tuple(trace),
                )
            current = next_state
            trace.append(current)
        if current is State.DONE:
            return RunResult(RunStatus.DONE, current, None, None, count, tuple(trace))
        return RunResult(
            RunStatus.ERROR,
            current,
            None,
            original_failure,
            count,
            tuple(trace),
        )


@dataclass(slots=True)
class SuccessfulAction:
    def run(self, context: ExecutionContext) -> ActionResult:
        if context.request.fail_at is context.state:
            return ActionResult(
                ActionStatus.FAILED,
                Failure(
                    FailureCategory.INTERNAL,
                    "INJECTED_FAILURE",
                    "failure injected by request",
                ),
            )
        return ActionResult(ActionStatus.SUCCEEDED)


def dry_run_actions() -> dict[State, StateAction]:
    return {state: SuccessfulAction() for state in SO101_WORKFLOW.action_states}
