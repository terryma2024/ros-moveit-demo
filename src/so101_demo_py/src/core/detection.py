"""Model-independent contracts for instance detection and RGB-D localization."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from numbers import Real
from typing import Literal

import numpy as np

RuntimeDevice = Literal["cuda", "mps", "cpu"]

_CLASS_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _owned_read_only(value: np.ndarray) -> np.ndarray:
    result = np.array(value, copy=True)
    result.setflags(write=False)
    return result


def _validate_class_id(value: str) -> None:
    if not isinstance(value, str) or _CLASS_ID.fullmatch(value) is None:
        raise ValueError("class_id must be a canonical lowercase identifier")


@dataclass(frozen=True, slots=True)
class DetectionFrame:
    rgb8: np.ndarray
    source_stamp_ns: int
    source_frame_id: str

    def __post_init__(self) -> None:
        if self.rgb8.ndim != 3 or self.rgb8.shape[2] != 3:
            raise ValueError("rgb8 shape must be (height, width, 3)")
        if self.rgb8.dtype != np.uint8:
            raise ValueError("rgb8 dtype must be uint8")
        if self.source_stamp_ns <= 0:
            raise ValueError("source stamp must be nonzero")
        if not self.source_frame_id:
            raise ValueError("source frame_id must be non-empty")
        object.__setattr__(self, "rgb8", _owned_read_only(self.rgb8))

    @property
    def image_width(self) -> int:
        return int(self.rgb8.shape[1])

    @property
    def image_height(self) -> int:
        return int(self.rgb8.shape[0])


@dataclass(frozen=True, slots=True)
class DetectionQuery:
    class_id: str

    def __post_init__(self) -> None:
        if self.class_id != "plastic_cup":
            raise ValueError("class_id is not in the detection query whitelist")


@dataclass(frozen=True, slots=True)
class DetectionCandidate:
    instance_id: str
    class_id: str
    confidence: float
    bbox_xyxy: tuple[float, float, float, float]
    mask: np.ndarray
    source_stamp_ns: int
    source_frame_id: str
    image_width: int
    image_height: int
    segmentation_quality: float | None = None

    def __post_init__(self) -> None:
        if not self.instance_id:
            raise ValueError("instance_id must be non-empty")
        _validate_class_id(self.class_id)
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be finite and in [0, 1]")
        if self.segmentation_quality is not None:
            if isinstance(self.segmentation_quality, (bool, np.bool_)) or not isinstance(
                self.segmentation_quality, Real
            ):
                raise ValueError("segmentation_quality must be finite and in [0, 1]")
            segmentation_quality = float(self.segmentation_quality)
            if (
                not math.isfinite(segmentation_quality)
                or not 0.0 <= segmentation_quality <= 1.0
            ):
                raise ValueError("segmentation_quality must be finite and in [0, 1]")
            object.__setattr__(self, "segmentation_quality", segmentation_quality)
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("image dimensions must be positive")
        if len(self.bbox_xyxy) != 4 or not all(
            math.isfinite(value) for value in self.bbox_xyxy
        ):
            raise ValueError("bbox must contain four finite values")
        x_min, y_min, x_max, y_max = self.bbox_xyxy
        if not (
            0.0 <= x_min < x_max <= float(self.image_width)
            and 0.0 <= y_min < y_max <= float(self.image_height)
        ):
            raise ValueError("bbox must have positive area inside the image")
        if self.mask.dtype != np.bool_:
            raise ValueError("mask dtype must be boolean")
        if self.mask.shape != (self.image_height, self.image_width):
            raise ValueError("mask shape must match image dimensions")
        if not bool(self.mask.any()):
            raise ValueError("mask must contain at least one selected pixel")
        if self.source_stamp_ns <= 0:
            raise ValueError("source stamp must be nonzero")
        if not self.source_frame_id:
            raise ValueError("source frame_id must be non-empty")
        object.__setattr__(self, "mask", _owned_read_only(self.mask))


@dataclass(frozen=True, slots=True)
class DetectionBatch:
    model_id: str
    weights_sha256: str
    runtime_device: RuntimeDevice
    inference_latency_ms: float
    image_width: int
    image_height: int
    candidates: tuple[DetectionCandidate, ...]

    def __post_init__(self) -> None:
        if not self.model_id:
            raise ValueError("model_id must be non-empty")
        if _SHA256.fullmatch(self.weights_sha256) is None:
            raise ValueError("weights_sha256 must be a lowercase SHA256 digest")
        if self.runtime_device not in {"cuda", "mps", "cpu"}:
            raise ValueError("runtime_device must be cuda, mps, or cpu")
        if not math.isfinite(self.inference_latency_ms) or self.inference_latency_ms < 0.0:
            raise ValueError("inference_latency_ms must be finite and nonnegative")
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("image dimensions must be positive")
        candidates = tuple(self.candidates)
        instance_ids = [candidate.instance_id for candidate in candidates]
        if len(instance_ids) != len(set(instance_ids)):
            raise ValueError("candidate instance_id values must be unique")
        if any(
            (candidate.image_width, candidate.image_height)
            != (self.image_width, self.image_height)
            for candidate in candidates
        ):
            raise ValueError("candidate dimensions must match batch dimensions")
        if candidates:
            source_keys = {
                (candidate.source_stamp_ns, candidate.source_frame_id)
                for candidate in candidates
            }
            if len(source_keys) != 1:
                raise ValueError("candidates must share one source frame and stamp")
        object.__setattr__(self, "candidates", candidates)


@dataclass(frozen=True, slots=True)
class LocalizedObject:
    instance_id: str
    class_id: str
    source_stamp_ns: int
    source_frame_id: str
    center_world_xyz: tuple[float, float, float]
    fitted_radius_m: float
    valid_depth_point_count: int
    points_world: np.ndarray

    def __post_init__(self) -> None:
        if not self.instance_id:
            raise ValueError("instance_id must be non-empty")
        _validate_class_id(self.class_id)
        if self.source_stamp_ns <= 0:
            raise ValueError("source stamp must be nonzero")
        if not self.source_frame_id:
            raise ValueError("source frame_id must be non-empty")
        if len(self.center_world_xyz) != 3 or not all(
            math.isfinite(value) for value in self.center_world_xyz
        ):
            raise ValueError("center_world_xyz must contain three finite values")
        if not math.isfinite(self.fitted_radius_m) or self.fitted_radius_m <= 0.0:
            raise ValueError("fitted_radius_m must be finite and positive")
        if self.valid_depth_point_count <= 0:
            raise ValueError("valid_depth_point_count must be positive")
        if self.points_world.ndim != 2 or self.points_world.shape != (
            self.valid_depth_point_count,
            3,
        ):
            raise ValueError("points_world shape must match valid_depth_point_count")
        if not np.isfinite(self.points_world).all():
            raise ValueError("points_world must contain finite values")
        object.__setattr__(self, "points_world", _owned_read_only(self.points_world))
