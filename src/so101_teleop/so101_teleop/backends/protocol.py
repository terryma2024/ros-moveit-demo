"""Backend-neutral values exchanged across the Teleop owner boundary."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Literal, Mapping


BackendId = Literal["gazebo_cpp", "gazebo_py", "mujoco_py"]


class BackendOperation(str, Enum):
    WORKFLOW = "workflow"
    RESET_WORLD = "reset_world"
    SCENE = "scene"


@dataclass(frozen=True)
class BackendCapabilities:
    backend_probe: bool
    workflow_execute: bool
    workflow_start: bool
    workflow_run: bool
    workflow_resume: bool
    reset_world: bool
    scene_operations: bool
    physical_observation: bool
    manual_joint_execute: bool
    manual_tcp_execute: bool
    camera_presets: bool

    def as_dict(self) -> dict[str, bool]:
        return {
            name: getattr(self, name)
            for name in self.__dataclass_fields__
        }


@dataclass(frozen=True)
class BackendError:
    code: str
    message: str
    owner_failure_code: str | None = None


@dataclass(frozen=True)
class BackendEnvelope:
    ok: bool
    backend: BackendId
    operation: str
    session_id: str | None
    owner_package: str
    owner_executable: str
    exit_code: int | None
    result: Mapping[str, Any] | None = None
    error: BackendError | None = None


@dataclass(frozen=True)
class WorkflowRequest:
    operation: Literal["start", "run", "step", "resume", "force-continue"]
    session_id: str
    checkpoint: Path


@dataclass(frozen=True)
class ResetRequest:
    session_id: str


@dataclass(frozen=True)
class SceneRequest:
    operation: Literal["observe", "attach", "detach", "upsert"]
    session_id: str
