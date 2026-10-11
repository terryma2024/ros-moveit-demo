"""The dataset contract names, scenarios, render events and labelled sample records."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping

import numpy as np

from so101_demo.adapters.perception.mujoco_scene_geometry import (
    TaskSceneGeometry,
)

HEAD_SEARCH_DATASET_CONTRACT = "so101-head-search-yolo-seg-v1"


HEAD_SEARCH_SCENARIOS = (
    "no_cup",
    "one_cup_distractors",
    "two_cups",
    "cup_near_bottle",
)


_GEOMETRY_SEAL_KEYS = ("required", "accepted_seal_sha256")


_NECK_KEYS = ("min_rad", "max_rad")


class DatasetScenario(str, Enum):
    NO_CUP = "no_cup"
    ONE_CUP_DISTRACTORS = "one_cup_distractors"
    TWO_CUPS = "two_cups"
    CUP_NEAR_BOTTLE = "cup_near_bottle"
    SMALL_FAR_CUP = "small_far_cup"
    PARTIALLY_OCCLUDED_CUP = "partially_occluded_cup"

    @property
    def cup_count(self) -> int:
        return {
            DatasetScenario.NO_CUP: 0,
            DatasetScenario.ONE_CUP_DISTRACTORS: 1,
            DatasetScenario.TWO_CUPS: 2,
            DatasetScenario.CUP_NEAR_BOTTLE: 1,
            DatasetScenario.SMALL_FAR_CUP: 1,
            DatasetScenario.PARTIALLY_OCCLUDED_CUP: 1,
        }[self]

    @classmethod
    def for_cup_count(cls, cup_count: int) -> "DatasetScenario":
        try:
            return {
                0: cls.NO_CUP,
                1: cls.ONE_CUP_DISTRACTORS,
                2: cls.TWO_CUPS,
            }[cup_count]
        except KeyError as error:
            raise ValueError("cup_count must be 0, 1, or 2") from error


_RENDER_EVENT_KINDS = frozenset(
    {
        "geometry_measured",
        "penetration_rejected",
        "rgb_render_started",
        "rgb_render_finished",
        "segmentation_render_started",
        "segmentation_render_finished",
        "scenario_rejected",
        "accepted",
    }
)


@dataclass(frozen=True, slots=True)
class RenderEvent:
    kind: str
    seed: int
    scenario: DatasetScenario
    attempt_index: int
    receipt: TaskSceneGeometry | None = None

    def __post_init__(self) -> None:
        if self.kind not in _RENDER_EVENT_KINDS:
            raise ValueError("unknown render event kind")
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("render event seed must be a nonnegative integer")
        if not isinstance(self.scenario, DatasetScenario):
            raise ValueError("render event scenario must be a dataset scenario")
        if type(self.attempt_index) is not int or self.attempt_index < 0:
            raise ValueError("render event attempt index must be a nonnegative integer")
        if self.receipt is not None:
            if not isinstance(self.receipt, TaskSceneGeometry):
                raise ValueError("render event receipt must be task scene geometry")
            self.receipt.validate_scope(self.scenario.cup_count)


RenderEventSink = Callable[[RenderEvent], object]


class RenderObserverError(RuntimeError):
    """A synchronous render event observer failed."""


def _emit_render_event(
    sink: RenderEventSink | None,
    kind: str,
    seed: int,
    scenario: DatasetScenario,
    attempt_index: int,
    receipt: TaskSceneGeometry | None,
) -> None:
    if sink is not None:
        try:
            sink(RenderEvent(kind, seed, scenario, attempt_index, receipt))
        except Exception as error:
            raise RenderObserverError("render event observer failed") from error


@dataclass(frozen=True, slots=True)
class RawRender:
    rgb8: np.ndarray
    geom_ids: np.ndarray
    geom_body_ids: np.ndarray
    body_names: Mapping[int, str]
    amodal_geom_ids: np.ndarray | None = None
    occluder_body_name: str | None = None
    occlusion_reference: str | None = None
    geometry_receipt: TaskSceneGeometry | None = None
    camera_name: str | None = None
    neck_rad: float | None = None
    camera_position_m: tuple[float, float, float] | None = None
    camera_quaternion_wxyz: tuple[float, float, float, float] | None = None
    camera_local_position_m: tuple[float, float, float] | None = None
    camera_local_xyaxes: tuple[float, ...] | None = None
    camera_fovy_rad: float | None = None
    arm_pose_rad: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        rgb = np.array(self.rgb8, dtype=np.uint8, copy=True)
        geom_ids = np.array(self.geom_ids, dtype=np.int32, copy=True)
        geom_body_ids = np.array(self.geom_body_ids, dtype=np.int32, copy=True)
        amodal_geom_ids = (
            None
            if self.amodal_geom_ids is None
            else np.array(self.amodal_geom_ids, dtype=np.int32, copy=True)
        )
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("RGB render must have HxWx3 dimensions")
        if geom_ids.ndim != 2 or geom_ids.shape != rgb.shape[:2]:
            raise ValueError("RGB and object-ID dimensions must match")
        if geom_body_ids.ndim != 1:
            raise ValueError("geom_body_ids must be one-dimensional")
        if amodal_geom_ids is not None and amodal_geom_ids.shape != geom_ids.shape:
            raise ValueError("visible and amodal object-ID dimensions must match")
        if (amodal_geom_ids is None) != (self.occluder_body_name is None):
            raise ValueError("amodal truth and occluder body name must be provided together")
        if (amodal_geom_ids is None) != (self.occlusion_reference is None):
            raise ValueError("amodal truth and occlusion reference must be provided together")
        if self.camera_name is not None and (
            not isinstance(self.camera_name, str) or not self.camera_name
        ):
            raise ValueError("camera_name must be a non-empty string when it is recorded")
        if self.camera_position_m is not None:
            object.__setattr__(
                self,
                "camera_position_m",
                tuple(float(value) for value in self.camera_position_m),
            )
        if self.camera_quaternion_wxyz is not None:
            object.__setattr__(
                self,
                "camera_quaternion_wxyz",
                tuple(float(value) for value in self.camera_quaternion_wxyz),
            )
        if self.camera_local_position_m is not None:
            object.__setattr__(
                self,
                "camera_local_position_m",
                tuple(float(value) for value in self.camera_local_position_m),
            )
        if self.camera_local_xyaxes is not None:
            object.__setattr__(
                self,
                "camera_local_xyaxes",
                tuple(float(value) for value in self.camera_local_xyaxes),
            )
        if self.camera_fovy_rad is not None:
            object.__setattr__(self, "camera_fovy_rad", float(self.camera_fovy_rad))
        if self.arm_pose_rad is not None:
            object.__setattr__(
                self, "arm_pose_rad", tuple(float(value) for value in self.arm_pose_rad)
            )
        if self.neck_rad is not None:
            object.__setattr__(self, "neck_rad", float(self.neck_rad))
        normalized_names: dict[int, str] = {}
        for body_id, name in self.body_names.items():
            if int(body_id) < 0 or not isinstance(name, str) or not name:
                raise ValueError("body names must map nonnegative IDs to names")
            normalized_names[int(body_id)] = name
        rgb.setflags(write=False)
        geom_ids.setflags(write=False)
        geom_body_ids.setflags(write=False)
        if amodal_geom_ids is not None:
            amodal_geom_ids.setflags(write=False)
        object.__setattr__(self, "rgb8", rgb)
        object.__setattr__(self, "geom_ids", geom_ids)
        object.__setattr__(self, "geom_body_ids", geom_body_ids)
        object.__setattr__(self, "amodal_geom_ids", amodal_geom_ids)
        object.__setattr__(self, "body_names", MappingProxyType(normalized_names))


@dataclass(frozen=True, slots=True)
class LabeledInstance:
    body_id: int
    body_name: str
    mask: np.ndarray
    polygon_xy: tuple[tuple[float, float], ...]
    amodal_mask: np.ndarray | None = None
    paired_reference_mask: np.ndarray | None = None
    occluder_body_name: str | None = None
    occlusion_reference: str | None = None

    def __post_init__(self) -> None:
        mask = np.array(self.mask, dtype=bool, copy=True)
        amodal_mask = (
            None if self.amodal_mask is None else np.array(self.amodal_mask, dtype=bool, copy=True)
        )
        paired_reference_mask = (
            None
            if self.paired_reference_mask is None
            else np.array(self.paired_reference_mask, dtype=bool, copy=True)
        )
        if mask.ndim != 2 or not mask.any():
            raise ValueError("instance mask must be a non-empty 2D mask")
        if len(self.polygon_xy) < 3:
            raise ValueError("instance polygon must have at least three points")
        if any(not (0.0 <= coordinate <= 1.0) for point in self.polygon_xy for coordinate in point):
            raise ValueError("instance polygon coordinates must be normalized")
        if amodal_mask is not None:
            if amodal_mask.shape != mask.shape or not amodal_mask.any():
                raise ValueError("amodal mask must be non-empty and match visible mask")
            if paired_reference_mask is None or paired_reference_mask.shape != mask.shape:
                raise ValueError("paired-reference mask must match measured masks")
            if not np.array_equal(amodal_mask, mask | paired_reference_mask):
                raise ValueError("amodal mask must equal visible union paired-reference mask")
            if not self.occluder_body_name or not self.occlusion_reference:
                raise ValueError("measured occlusion requires its occluder and reference")
            amodal_mask.setflags(write=False)
            paired_reference_mask.setflags(write=False)
        elif self.occluder_body_name is not None or self.occlusion_reference is not None:
            raise ValueError("unmeasured occlusion cannot declare an occluder or reference")
        elif paired_reference_mask is not None:
            raise ValueError("unmeasured occlusion cannot include a paired-reference mask")
        mask.setflags(write=False)
        object.__setattr__(self, "mask", mask)
        object.__setattr__(self, "amodal_mask", amodal_mask)
        object.__setattr__(self, "paired_reference_mask", paired_reference_mask)

    @property
    def visible_pixel_count(self) -> int:
        return int(self.mask.sum())

    @property
    def occlusion_measured(self) -> bool:
        return self.amodal_mask is not None

    @property
    def amodal_pixel_count(self) -> int | None:
        return None if self.amodal_mask is None else int(self.amodal_mask.sum())

    @property
    def paired_reference_pixel_count(self) -> int | None:
        if self.paired_reference_mask is None:
            return None
        return int(self.paired_reference_mask.sum())

    @property
    def occluded_pixel_count(self) -> int | None:
        if self.amodal_mask is None:
            return None
        return int(self.amodal_mask.sum() - self.mask.sum())

    @property
    def visible_fraction(self) -> float | None:
        if self.amodal_mask is None:
            return None
        return self.visible_pixel_count / int(self.amodal_mask.sum())

    @property
    def occlusion_state(self) -> str:
        if self.amodal_mask is None:
            return "unmeasured"
        return "partial" if self.occluded_pixel_count else "none"


@dataclass(frozen=True, slots=True)
class LabeledSample:
    seed: int
    scenario: DatasetScenario
    rgb8: np.ndarray
    instances: tuple[LabeledInstance, ...]

    def __post_init__(self) -> None:
        rgb = np.array(self.rgb8, dtype=np.uint8, copy=True)
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("sample RGB must have HxWx3 dimensions")
        if any(instance.mask.shape != rgb.shape[:2] for instance in self.instances):
            raise ValueError("sample RGB and instance mask dimensions must match")
        rgb.setflags(write=False)
        object.__setattr__(self, "rgb8", rgb)


@dataclass(frozen=True, slots=True)
class SceneGeometry:
    ordinary_camera_jitter_m: tuple[float, float] = (-0.015, 0.015)
    cup_a_xy_jitter_m: tuple[float, float] = (-0.045, 0.045)
    cup_b_xy_jitter_m: tuple[float, float] = (-0.025, 0.025)
    bottle_xy_jitter_m: tuple[float, float] = (-0.025, 0.025)
    far_camera_retreat_m: tuple[float, float] = (2.4, 3.0)
    partial_cup_xy_jitter_m: tuple[float, float] = (-0.025, 0.025)
    partial_bottle_longitudinal_m: tuple[float, float] = (0.055, 0.105)
    partial_bottle_perpendicular_m: tuple[float, float] = (-0.025, 0.025)
    small_bbox_area_max_exclusive: float = 1024.0
    visible_pixel_count_minimum: int = 64
    partial_visible_fraction: tuple[float, float] = (0.35, 0.8)
    maximum_deterministic_attempts: int = 64

    def __post_init__(self) -> None:
        range_names = (
            "ordinary_camera_jitter_m",
            "cup_a_xy_jitter_m",
            "cup_b_xy_jitter_m",
            "bottle_xy_jitter_m",
            "far_camera_retreat_m",
            "partial_cup_xy_jitter_m",
            "partial_bottle_longitudinal_m",
            "partial_bottle_perpendicular_m",
            "partial_visible_fraction",
        )
        for name in range_names:
            value = tuple(float(item) for item in getattr(self, name))
            if len(value) != 2 or value[0] >= value[1]:
                raise ValueError(f"{name} must be an increasing two-value range")
            object.__setattr__(self, name, value)
        if self.far_camera_retreat_m[0] <= 0.0:
            raise ValueError("far camera retreat must be positive")
        if not 0.0 < self.partial_visible_fraction[0] < self.partial_visible_fraction[1] < 1.0:
            raise ValueError("partial visible fraction must be strictly within (0, 1)")
        if self.small_bbox_area_max_exclusive <= 0.0:
            raise ValueError("small bbox area threshold must be positive")
        if self.visible_pixel_count_minimum <= 0:
            raise ValueError("visible pixel minimum must be positive")
        if self.maximum_deterministic_attempts <= 0:
            raise ValueError("maximum deterministic attempts must be positive")

    @classmethod
    def from_mapping(cls, document: Mapping[str, Any] | None) -> "SceneGeometry":
        if document is None:
            return cls()
        expected = set(asdict(cls()))
        if set(document) != expected:
            raise ValueError("scene_geometry must contain exactly the registered fields")
        return cls(**dict(document))
