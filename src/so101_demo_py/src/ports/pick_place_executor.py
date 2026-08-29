from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class ExecutorDispatchError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True, slots=True)
class DynamicCupPickPlaceRequest:
    request_id: str
    capability: str
    backend: str
    scene_source: str
    target_object: str
    action: str


@dataclass(frozen=True, slots=True)
class RuntimeDispatchResult:
    exit_code: int
    runtime_session_id: str


@dataclass(frozen=True, slots=True)
class VerifiedArtifact:
    path: str
    sha256: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True, slots=True)
class ExecutionProvenance:
    source_commit: str
    installed_prefix: str
    entrypoint: VerifiedArtifact | None
    module: VerifiedArtifact | None
    executable: VerifiedArtifact | None
    session_id: str
    expected_reset_epoch: int
    evidence_root: str

    def to_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "schema_version": 1,
            "source_commit": self.source_commit,
            "installed_prefix": self.installed_prefix,
            "session_id": self.session_id,
            "expected_reset_epoch": self.expected_reset_epoch,
            "evidence_root": self.evidence_root,
        }
        for name in ("entrypoint", "module", "executable"):
            artifact = getattr(self, name)
            if artifact is not None:
                result[name] = artifact.to_dict()
        return result


class PickPlaceExecutorPort(Protocol):
    def dispatch(
        self,
        request: DynamicCupPickPlaceRequest,
    ) -> RuntimeDispatchResult:
        ...
