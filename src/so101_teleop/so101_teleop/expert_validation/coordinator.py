"""Typed fixed-coordinator launch contracts for the validation Web service."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping


_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _absolute_normalized(name: str, value: Path) -> Path:
    path = Path(value)
    if not path.is_absolute() or path != path.resolve(strict=False):
        raise ValueError(f"{name}_ABSOLUTE_NORMALIZED")
    return path


@dataclass(frozen=True)
class CoordinatorStartRequest:
    campaign_id: str
    batch_id: str
    execution_mode: str
    worker_count: int
    argv: tuple[str, ...]
    environment: Mapping[str, str] = field(repr=False)
    batch_root: Path
    control_socket: Path
    control_token_sha256: str
    coordinator_epoch: int = 1
    selected_point_ids: tuple[str, ...] = ()
    # Retained only so historical v1 rows keep deserialising; new v2 runs omit it.
    max_points_per_worker: int | None = None

    def __post_init__(self) -> None:
        for name in ("campaign_id", "batch_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
                raise ValueError(f"{name.upper()}_INVALID")
        if self.execution_mode not in {"SEQUENTIAL", "PARALLEL"}:
            raise ValueError("FIXED_EXECUTION_MODE")
        for name in ("worker_count", "coordinator_epoch"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name.upper()}_POSITIVE")
        if self.max_points_per_worker is not None and (
            isinstance(self.max_points_per_worker, bool)
            or not isinstance(self.max_points_per_worker, int)
            or self.max_points_per_worker <= 0
        ):
            raise ValueError("MAX_POINTS_PER_WORKER_POSITIVE")
        if self.execution_mode == "SEQUENTIAL" and self.worker_count != 1:
            raise ValueError("SEQUENTIAL_WORKER_COUNT")
        argv = tuple(self.argv)
        if not argv or any(not isinstance(item, str) or not item for item in argv):
            raise ValueError("COORDINATOR_ARGV")
        object.__setattr__(self, "argv", argv)
        if not isinstance(self.environment, Mapping) or any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            for key, value in self.environment.items()
        ):
            raise ValueError("COORDINATOR_ENVIRONMENT")
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))
        batch_root = _absolute_normalized("BATCH_ROOT", self.batch_root)
        control_socket = _absolute_normalized("CONTROL_SOCKET", self.control_socket)
        if not control_socket.is_relative_to(batch_root):
            raise ValueError("CONTROL_SOCKET_OUTSIDE_BATCH_ROOT")
        object.__setattr__(self, "batch_root", batch_root)
        object.__setattr__(self, "control_socket", control_socket)
        if _SHA256.fullmatch(self.control_token_sha256) is None:
            raise ValueError("CONTROL_TOKEN_SHA256")
        point_ids = tuple(self.selected_point_ids)
        if any(not isinstance(point_id, str) or not point_id for point_id in point_ids):
            raise ValueError("SELECTED_POINT_IDS")
        if len(point_ids) != len(set(point_ids)):
            raise ValueError("SELECTED_POINT_IDS")
        object.__setattr__(self, "selected_point_ids", point_ids)
        self.control_binding

    @property
    def control_binding(self) -> CoordinatorBinding | None:
        keys = (
            "SO101_FIXED_CONTROL_TOKEN", "SO101_FIXED_CONTROL_CAMPAIGN_ID",
            "SO101_FIXED_CONTROL_EPOCH", "SO101_FIXED_CONTROL_SOCKET",
        )
        present = tuple(key in self.environment for key in keys)
        if not any(present):
            return None
        if not all(present):
            raise ValueError("CONTROL_BINDING_INCOMPLETE")
        token, campaign, epoch, socket_path = (self.environment[key] for key in keys)
        if (
            _SHA256.fullmatch(token) is None
            or campaign != self.campaign_id
            or epoch != str(self.coordinator_epoch)
            or socket_path != str(self.control_socket)
        ):
            raise ValueError("CONTROL_BINDING_MISMATCH")
        return CoordinatorBinding(
            self.campaign_id, self.batch_id, self.batch_root, self.control_socket,
            self.coordinator_epoch, token, self.control_token_sha256,
        )

    @property
    def owner_kind(self) -> str:
        return "COORDINATOR"


@dataclass(frozen=True)
class CoordinatorBinding:
    campaign_id: str
    batch_id: str
    batch_root: Path
    control_socket: Path
    coordinator_epoch: int
    control_token: str = field(repr=False)
    control_token_sha256: str

    def __post_init__(self) -> None:
        for name in ("campaign_id", "batch_id"):
            value = getattr(self, name)
            if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
                raise ValueError(f"{name.upper()}_INVALID")
        if (
            isinstance(self.coordinator_epoch, bool)
            or not isinstance(self.coordinator_epoch, int)
            or self.coordinator_epoch <= 0
        ):
            raise ValueError("COORDINATOR_EPOCH_POSITIVE")
        root = _absolute_normalized("BATCH_ROOT", self.batch_root)
        socket_path = _absolute_normalized("CONTROL_SOCKET", self.control_socket)
        if not socket_path.is_relative_to(root):
            raise ValueError("CONTROL_SOCKET_OUTSIDE_BATCH_ROOT")
        object.__setattr__(self, "batch_root", root)
        object.__setattr__(self, "control_socket", socket_path)
        if not isinstance(self.control_token, str) or not self.control_token:
            raise ValueError("CONTROL_TOKEN")
        digest = __import__("hashlib").sha256(self.control_token.encode("utf-8")).hexdigest()
        if digest != self.control_token_sha256:
            raise ValueError("CONTROL_TOKEN_SHA256")
