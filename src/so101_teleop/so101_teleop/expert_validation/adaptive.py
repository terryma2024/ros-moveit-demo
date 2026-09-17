"""Typed adaptive-wrapper launch contracts for the validation Web service."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType
from typing import Mapping


_SHORT_BATCH_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,4}$", re.ASCII)
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class AdaptiveStartRequest:
    campaign_id: str
    batch_id: str
    preferred_worker_count: int
    fallback_worker_counts: tuple[int, ...]
    initial_points_per_worker: int
    worker_start_timeout_s: float
    max_infra_attempts_per_point: int
    yolo_executor_count: int
    argv: tuple[str, ...]
    environment: Mapping[str, str]
    evidence_root: Path
    adaptive_config_sha256: str
    catalog_sha256: str
    yolo_weights_sha256: str
    grounded_sam_manifest_sha256: str
    broker_image_id: str
    selected_point_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.campaign_id, str) or _IDENTIFIER.fullmatch(self.campaign_id) is None:
            raise ValueError("CAMPAIGN_ID_INVALID")
        if not isinstance(self.batch_id, str) or _SHORT_BATCH_ID.fullmatch(self.batch_id) is None:
            raise ValueError("ADAPTIVE_BATCH_ID")
        preferred = self.preferred_worker_count
        if isinstance(preferred, bool) or not isinstance(preferred, int) or not 1 <= preferred <= 16:
            raise ValueError("ADAPTIVE_WORKER_COUNT")
        fallbacks = tuple(self.fallback_worker_counts)
        if any(
            isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 16
            for count in fallbacks
        ) or any(next_count >= count for count, next_count in zip((preferred, *fallbacks), fallbacks)):
            raise ValueError("ADAPTIVE_FALLBACK_TIERS")
        object.__setattr__(self, "fallback_worker_counts", fallbacks)
        for name in ("initial_points_per_worker", "max_infra_attempts_per_point"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name.upper()}_POSITIVE")
        if (
            isinstance(self.worker_start_timeout_s, bool)
            or not isinstance(self.worker_start_timeout_s, (int, float))
            or self.worker_start_timeout_s <= 0
        ):
            raise ValueError("WORKER_START_TIMEOUT_POSITIVE")
        if type(self.yolo_executor_count) is not int or self.yolo_executor_count not in {1, 2, 4}:
            raise ValueError("YOLO_EXECUTOR_COUNT")
        argv = tuple(self.argv)
        if not argv or any(not isinstance(item, str) or not item for item in argv):
            raise ValueError("ADAPTIVE_ARGV")
        if "--max-points-per-worker" in argv or "--live-headroom-evidence" in argv:
            raise ValueError("ADAPTIVE_FIXED_FIELD")
        object.__setattr__(self, "argv", argv)
        if not isinstance(self.environment, Mapping) or any(
            not isinstance(key, str)
            or not key
            or not isinstance(value, str)
            for key, value in self.environment.items()
        ):
            raise ValueError("ADAPTIVE_ENVIRONMENT")
        object.__setattr__(self, "environment", MappingProxyType(dict(self.environment)))
        root = Path(self.evidence_root)
        if not root.is_absolute() or root != root.resolve(strict=False):
            raise ValueError("EVIDENCE_ROOT_ABSOLUTE_NORMALIZED")
        object.__setattr__(self, "evidence_root", root)
        for name in (
            "adaptive_config_sha256",
            "catalog_sha256",
            "yolo_weights_sha256",
            "grounded_sam_manifest_sha256",
        ):
            if _SHA256.fullmatch(getattr(self, name)) is None:
                raise ValueError(f"{name.upper()}_INVALID")
        if not isinstance(self.broker_image_id, str) or not self.broker_image_id:
            raise ValueError("BROKER_IMAGE_ID")
        point_ids = tuple(self.selected_point_ids)
        if any(not isinstance(point_id, str) or not point_id for point_id in point_ids):
            raise ValueError("SELECTED_POINT_IDS")
        if len(point_ids) != len(set(point_ids)):
            raise ValueError("SELECTED_POINT_IDS")
        object.__setattr__(self, "selected_point_ids", point_ids)

    @property
    def runtime_root(self) -> Path:
        return self.evidence_root / "r" / self.batch_id

    @property
    def levels(self) -> tuple[int, ...]:
        return (self.preferred_worker_count, *self.fallback_worker_counts)

    @property
    def owner_kind(self) -> str:
        return "ADAPTIVE_WRAPPER"

    @property
    def max_points_per_worker(self):
        return None
