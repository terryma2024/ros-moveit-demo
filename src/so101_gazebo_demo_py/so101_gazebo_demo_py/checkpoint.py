"""Durable schema-v4 workflow checkpoints."""

from dataclasses import dataclass, field
from enum import StrEnum
import json
import math
import os
from pathlib import Path
import secrets
from typing import Any, Mapping

from .domain import Failure, FailureCategory, RunMode, State


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
    gazebo_task_object_pose_world: Pose | None = None
    gazebo_task_object_attached: bool | None = None
    gazebo_task_object_stationary: bool | None = None
    required_world_objects: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Checkpoint:
    run_id: str
    sequence: int
    source_mode: RunMode
    phase: CheckpointPhase
    last_completed_state: State
    failed_state: State | None
    original_failure: Failure | None
    next_state: State
    expected: ExpectedWorldState
    policy_bundle_sha256: str
    simulation_session_id: str
    resumable: bool
    release_epoch_id: str | None = None
    release_marker_sequence: int | None = None
    schema_version: int = 4


def _failure(code: str, message: str) -> Failure:
    return Failure(FailureCategory.CHECKPOINT, code, message)


def _atomic_write(path: Path, payload: bytes, prefix: str = "CHECKPOINT") -> Failure | None:
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
    except OSError as error:
        return _failure(f"{prefix}_DIRECTORY_FAILED", str(error))
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(8)}.tmp")
    fd: int | None = None
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        offset = 0
        while offset < len(payload):
            written = os.write(fd, payload[offset:])
            if written <= 0:
                raise OSError("short write")
            offset += written
        os.fsync(fd)
        os.close(fd)
        fd = None
    except OSError as error:
        if fd is not None:
            os.close(fd)
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return _failure(f"{prefix}_WRITE_FAILED", str(error))
    try:
        os.replace(temporary, path)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        return _failure(f"{prefix}_RENAME_FAILED", str(error))
    directory_fd: int | None = None
    try:
        directory_fd = os.open(path.parent, os.O_RDONLY)
        os.fsync(directory_fd)
    except OSError as error:
        return _failure(f"{prefix}_FSYNC_FAILED", str(error))
    finally:
        if directory_fd is not None:
            os.close(directory_fd)
    return None


def _failure_json(value: Failure | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return {
        "category": value.category.value, "code": value.code,
        "message": value.message, "metrics": dict(value.metrics),
    }


def _expected_json(value: ExpectedWorldState) -> dict[str, Any]:
    return {
        "tcp_pose_world": list(value.tcp_pose_world),
        "gripper_open": value.gripper_open,
        "joint_positions": dict(value.joint_positions),
        "moveit_world_object_poses": {key: list(pose) for key, pose in value.moveit_world_object_poses.items()},
        "moveit_task_object_attached": value.moveit_task_object_attached,
        "gazebo_task_object_pose_world": None if value.gazebo_task_object_pose_world is None else list(value.gazebo_task_object_pose_world),
        "gazebo_task_object_attached": value.gazebo_task_object_attached,
        "gazebo_task_object_stationary": value.gazebo_task_object_stationary,
        "required_world_objects": list(value.required_world_objects),
    }


def _checkpoint_json(value: Checkpoint) -> dict[str, Any]:
    return {
        "schema_version": value.schema_version, "run_id": value.run_id,
        "sequence": value.sequence, "source_mode": value.source_mode.value,
        "phase": value.phase.value, "last_completed_state": value.last_completed_state.value,
        "failed_state": None if value.failed_state is None else value.failed_state.value,
        "original_failure": _failure_json(value.original_failure),
        "next_state": value.next_state.value, "expected": _expected_json(value.expected),
        "policy_bundle_sha256": value.policy_bundle_sha256,
        "simulation_session_id": value.simulation_session_id, "resumable": value.resumable,
        "release_epoch_id": value.release_epoch_id,
        "release_marker_sequence": value.release_marker_sequence,
    }


class FileCheckpointStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    def commit(self, checkpoint: Checkpoint) -> Failure | None:
        try:
            if checkpoint.schema_version != 4 or checkpoint.sequence < 0:
                raise ValueError("invalid schema or sequence")
            if checkpoint.release_epoch_id is not None:
                if not checkpoint.release_epoch_id or checkpoint.release_marker_sequence is None:
                    raise ValueError("release epoch requires marker sequence")
                if checkpoint.release_marker_sequence < 0 or checkpoint.resumable:
                    raise ValueError("active release epoch must be non-resumable")
            elif checkpoint.release_marker_sequence is not None:
                raise ValueError("release marker requires epoch")
            body = json.dumps(_checkpoint_json(checkpoint), sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
        except (TypeError, ValueError) as error:
            return _failure("CHECKPOINT_INVALID_DATA", str(error))
        return _atomic_write(self.path, body)

    def load(self) -> tuple[Checkpoint | None, Failure | None]:
        if not self.path.exists():
            return None, _failure("CHECKPOINT_NOT_FOUND", "checkpoint does not exist")
        try:
            document = json.loads(self.path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            return None, _failure("CHECKPOINT_PARSE_FAILED", str(error))
        try:
            expected_keys = {
                "schema_version", "run_id", "sequence", "source_mode", "phase",
                "last_completed_state", "failed_state", "original_failure", "next_state",
                "expected", "policy_bundle_sha256", "simulation_session_id", "resumable",
                "release_epoch_id", "release_marker_sequence",
            }
            if set(document) != expected_keys or document["schema_version"] != 4:
                raise ValueError("incompatible checkpoint schema")
            expected = document["expected"]
            expected_world = ExpectedWorldState(
                tcp_pose_world=_pose(expected["tcp_pose_world"]),
                gripper_open=_bool(expected["gripper_open"]),
                joint_positions={key: _finite(value) for key, value in expected["joint_positions"].items()},
                moveit_world_object_poses={key: _pose(value) for key, value in expected["moveit_world_object_poses"].items()},
                moveit_task_object_attached=_optional_bool(expected["moveit_task_object_attached"]),
                gazebo_task_object_pose_world=None if expected["gazebo_task_object_pose_world"] is None else _pose(expected["gazebo_task_object_pose_world"]),
                gazebo_task_object_attached=_optional_bool(expected["gazebo_task_object_attached"]),
                gazebo_task_object_stationary=_optional_bool(expected["gazebo_task_object_stationary"]),
                required_world_objects=tuple(str(value) for value in expected["required_world_objects"]),
            )
            original = document["original_failure"]
            parsed_failure = None if original is None else Failure(
                FailureCategory(original["category"]), str(original["code"]),
                str(original["message"]), {key: _finite(value) for key, value in original["metrics"].items()},
            )
            checkpoint = Checkpoint(
                run_id=str(document["run_id"]), sequence=_integer(document["sequence"]),
                source_mode=RunMode(document["source_mode"]), phase=CheckpointPhase(document["phase"]),
                last_completed_state=State(document["last_completed_state"]),
                failed_state=None if document["failed_state"] is None else State(document["failed_state"]),
                original_failure=parsed_failure, next_state=State(document["next_state"]),
                expected=expected_world, policy_bundle_sha256=str(document["policy_bundle_sha256"]),
                simulation_session_id=str(document["simulation_session_id"]),
                resumable=_bool(document["resumable"]),
                release_epoch_id=(
                    None if document["release_epoch_id"] is None
                    else str(document["release_epoch_id"])
                ),
                release_marker_sequence=(
                    None if document["release_marker_sequence"] is None
                    else _integer(document["release_marker_sequence"])
                ),
            )
            if checkpoint.release_epoch_id is not None and checkpoint.resumable:
                raise ValueError("active release epoch must be non-resumable")
            return checkpoint, None
        except (KeyError, TypeError, ValueError) as error:
            code = "CHECKPOINT_INVALID_ENUM" if isinstance(error, ValueError) and "is not a valid" in str(error) else "CHECKPOINT_INCOMPATIBLE"
            return None, _failure(code, str(error))


def _finite(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        raise ValueError("nonfinite numeric value")
    return float(value)


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
