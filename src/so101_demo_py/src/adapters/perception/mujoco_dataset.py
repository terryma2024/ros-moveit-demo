"""Deterministic MuJoCo object-ID dataset generation for YOLO segmentation."""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol

import numpy as np
from so101_demo.adapters.perception.mujoco_scene_geometry import (
    ScenePenetrationError,
    TaskSceneGeometry,
    measure_task_scene_geometry,
)
from so101_demo.runtime.point_cloud_preview import write_png_rgb8
from so101_demo.runtime.task_artifacts import atomic_json


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


@dataclass(frozen=True, slots=True)
class RendererSettings:
    mjcf_path: Path
    camera_name: str = "task_camera"
    image_width: int = 640
    image_height: int = 480
    geometry: SceneGeometry = SceneGeometry()
    require_nonpenetrating_scene: bool = False

    def __post_init__(self) -> None:
        path = Path(self.mjcf_path)
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("mjcf_path must be an absolute regular file")
        if not isinstance(self.camera_name, str) or not self.camera_name:
            raise ValueError("camera_name must be non-empty")
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("image dimensions must be positive")
        if not isinstance(self.geometry, SceneGeometry):
            raise ValueError("geometry must be scene geometry")
        if type(self.require_nonpenetrating_scene) is not bool:
            raise ValueError("require_nonpenetrating_scene must be boolean")
        object.__setattr__(self, "mjcf_path", path)


@dataclass(frozen=True, slots=True)
class DatasetConfig:
    mjcf_path: Path
    split_counts: Mapping[str, int]
    generator_commit: str
    camera_name: str = "task_camera"
    image_width: int = 640
    image_height: int = 480
    seed_starts: Mapping[str, int] | None = None
    scenario_quotas: Mapping[str, Mapping[str, int]] | None = None
    geometry: SceneGeometry = SceneGeometry()
    require_nonpenetrating_scene: bool = False

    def __post_init__(self) -> None:
        if type(self.require_nonpenetrating_scene) is not bool:
            raise ValueError("require_nonpenetrating_scene must be boolean")
        path = Path(self.mjcf_path)
        if not path.is_absolute():
            path = path.resolve()
        if path.is_symlink() or not path.is_file():
            raise ValueError("mjcf_path must be a regular file")
        counts = dict(self.split_counts)
        if set(counts) != {"train", "val", "test"}:
            raise ValueError("split_counts must contain train, val, and test")
        if any(not isinstance(value, int) or value <= 0 for value in counts.values()):
            raise ValueError("split counts must be positive integers")
        if not self.generator_commit:
            raise ValueError("generator_commit must be non-empty")
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("image dimensions must be positive")
        starts = dict(_SEED_STARTS if self.seed_starts is None else self.seed_starts)
        split_seed_plan(counts, starts)
        quotas = _validated_scenario_quotas(counts, self.scenario_quotas)
        object.__setattr__(self, "mjcf_path", path)
        object.__setattr__(self, "split_counts", MappingProxyType(counts))
        object.__setattr__(self, "seed_starts", MappingProxyType(starts))
        object.__setattr__(
            self,
            "scenario_quotas",
            None
            if quotas is None
            else MappingProxyType(
                {split: MappingProxyType(values) for split, values in quotas.items()}
            ),
        )

    def renderer_settings(self) -> RendererSettings:
        return RendererSettings(
            mjcf_path=self.mjcf_path,
            camera_name=self.camera_name,
            image_width=self.image_width,
            image_height=self.image_height,
            geometry=self.geometry,
            require_nonpenetrating_scene=self.require_nonpenetrating_scene,
        )


_SEED_STARTS = {"train": 100000, "val": 200000, "test": 300000}
_MAX_SEED = 999_999_999


def _validated_scenario_quotas(
    split_counts: Mapping[str, int],
    scenario_quotas: Mapping[str, Mapping[str, int]] | None,
) -> dict[str, dict[str, int]] | None:
    if scenario_quotas is None:
        return None
    if set(scenario_quotas) != {"train", "val", "test"}:
        raise ValueError("scenario quotas must contain train, val, and test")
    known = {scenario.value for scenario in DatasetScenario}
    result: dict[str, dict[str, int]] = {}
    for split in ("train", "val", "test"):
        raw = scenario_quotas[split]
        if not isinstance(raw, Mapping) or not raw or not set(raw) <= known:
            raise ValueError("scenario quotas contain an unknown or empty scenario mapping")
        normalized = dict(raw)
        if any(type(value) is not int or value <= 0 for value in normalized.values()):
            raise ValueError("scenario quotas must be positive integers")
        if sum(normalized.values()) != split_counts[split]:
            raise ValueError("scenario quotas must sum to the configured split count")
        result[split] = normalized
    return result


def scenario_plan(config: DatasetConfig) -> dict[str, tuple[DatasetScenario, ...]]:
    """Return the deterministic quota-derived scenario schedule for every split."""

    result: dict[str, tuple[DatasetScenario, ...]] = {}
    for split in ("train", "val", "test"):
        if config.scenario_quotas is None:
            scenarios = tuple(DatasetScenario)
            result[split] = tuple(
                scenarios[index % len(scenarios)] for index in range(config.split_counts[split])
            )
            continue
        remaining = dict(config.scenario_quotas[split])
        scheduled: list[DatasetScenario] = []
        while remaining:
            for scenario in DatasetScenario:
                count = remaining.get(scenario.value, 0)
                if count <= 0:
                    continue
                scheduled.append(scenario)
                if count == 1:
                    del remaining[scenario.value]
                else:
                    remaining[scenario.value] = count - 1
        result[split] = tuple(scheduled)
    return result


def split_seed_plan(
    split_counts: Mapping[str, int],
    seed_starts: Mapping[str, int] | None = None,
) -> dict[str, tuple[int, ...]]:
    counts = dict(split_counts)
    if set(counts) != set(_SEED_STARTS):
        raise ValueError("split counts must contain train, val, and test")
    starts = dict(_SEED_STARTS if seed_starts is None else seed_starts)
    if set(starts) != set(_SEED_STARTS):
        raise ValueError("seed_starts must contain train, val, and test")
    result: dict[str, tuple[int, ...]] = {}
    for split in ("train", "val", "test"):
        count = counts[split]
        if not isinstance(count, int) or count <= 0:
            raise ValueError("split counts must be positive integers")
        start = starts[split]
        if type(start) is not int or start < 0:
            raise ValueError("seed starts must be nonnegative integers")
        if count > _MAX_SEED - start + 1:
            raise ValueError("seed range exceeds the nine-digit namespace")
        result[split] = tuple(range(start, start + count))
    split_names = tuple(result)
    for index, left in enumerate(split_names):
        for right in split_names[index + 1 :]:
            if set(result[left]).intersection(result[right]):
                raise ValueError("seed ranges must be disjoint")
    return result


def limited_split_counts(
    split_counts: Mapping[str, int], sample_limit: int | None
) -> dict[str, int]:
    counts = dict(split_counts)
    split_seed_plan(counts)
    if sample_limit is None:
        return counts
    if not isinstance(sample_limit, int) or sample_limit < 3:
        raise ValueError("sample_limit must be at least three")
    if sample_limit > sum(counts.values()):
        raise ValueError("sample_limit cannot exceed configured sample count")
    base, remainder = divmod(sample_limit, 3)
    result = {
        split: base + (1 if index < remainder else 0)
        for index, split in enumerate(("train", "val", "test"))
    }
    if any(result[split] > counts[split] for split in result):
        raise ValueError("sample_limit allocation exceeds a configured split")
    return result


def load_dataset_config(
    path: Path,
    *,
    generator_commit: str,
    sample_limit: int | None = None,
) -> DatasetConfig:
    config_path = Path(path)
    if config_path.is_symlink() or not config_path.is_file():
        raise ValueError("dataset config must be a regular file")
    contents = config_path.read_text(encoding="utf-8")
    try:
        document = json.loads(contents)
    except json.JSONDecodeError:
        try:
            import yaml
        except ImportError as error:
            raise RuntimeError("PyYAML is required to read dataset configuration") from error
        document = yaml.safe_load(contents)
    if not isinstance(document, dict):
        raise ValueError("dataset config must contain a mapping")
    required = {
        "mjcf_path",
        "camera_name",
        "image_width",
        "image_height",
        "split_counts",
    }
    if not required <= document.keys():
        raise ValueError("dataset config is missing required fields")
    mjcf = Path(str(document["mjcf_path"]))
    if not mjcf.is_absolute():
        mjcf = (config_path.parent / mjcf).resolve()
    raw_counts = document["split_counts"]
    if not isinstance(raw_counts, dict):
        raise ValueError("split_counts must be a mapping")
    raw_seed_starts = document.get("seed_starts")
    if raw_seed_starts is not None and not isinstance(raw_seed_starts, dict):
        raise ValueError("seed_starts must be a mapping")
    split_seed_plan(raw_counts, raw_seed_starts)
    raw_scenario_quotas = document.get("scenario_quotas")
    if raw_scenario_quotas is not None and not isinstance(raw_scenario_quotas, dict):
        raise ValueError("scenario_quotas must be a mapping")
    if sample_limit is not None and raw_scenario_quotas is not None:
        raise ValueError("sample_limit cannot alter preregistered scenario quotas")
    counts = limited_split_counts(raw_counts, sample_limit)
    return DatasetConfig(
        mjcf_path=mjcf,
        split_counts=counts,
        generator_commit=generator_commit,
        camera_name=str(document["camera_name"]),
        image_width=int(document["image_width"]),
        image_height=int(document["image_height"]),
        seed_starts=raw_seed_starts,
        scenario_quotas=raw_scenario_quotas,
        geometry=SceneGeometry.from_mapping(document.get("scene_geometry")),
        require_nonpenetrating_scene=document.get("require_nonpenetrating_scene", False),
    )


def _convex_hull(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    unique = sorted(set(points))
    if len(unique) <= 1:
        return unique

    def cross(
        origin: tuple[int, int],
        first: tuple[int, int],
        second: tuple[int, int],
    ) -> int:
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (first[1] - origin[1]) * (
            second[0] - origin[0]
        )

    lower: list[tuple[int, int]] = []
    for point in unique:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], point) <= 0:
            lower.pop()
        lower.append(point)
    upper: list[tuple[int, int]] = []
    for point in reversed(unique):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], point) <= 0:
            upper.pop()
        upper.append(point)
    return lower[:-1] + upper[:-1]


def _polygon_from_mask(mask: np.ndarray) -> tuple[tuple[float, float], ...]:
    height, width = mask.shape
    rows, columns = np.nonzero(mask)
    hull = _convex_hull(list(zip(columns.tolist(), rows.tolist(), strict=True)))
    if len(hull) < 3:
        left, right = int(columns.min()), int(columns.max())
        top, bottom = int(rows.min()), int(rows.max())
        hull = [(left, top), (right, top), (right, bottom), (left, bottom)]
    x_scale = max(1, width - 1)
    y_scale = max(1, height - 1)
    return tuple(
        (
            min(1.0, max(0.0, x / x_scale)),
            min(1.0, max(0.0, y / y_scale)),
        )
        for x, y in hull
    )


def encode_binary_mask_rle(mask: np.ndarray) -> tuple[int, ...]:
    """Encode a row-major binary mask as alternating zero/one run lengths."""

    normalized = np.asarray(mask, dtype=bool)
    if normalized.ndim != 2:
        raise ValueError("binary mask must be two-dimensional")
    flat = normalized.reshape(-1)
    counts: list[int] = []
    expected = False
    run = 0
    for value in flat:
        bit = bool(value)
        if bit == expected:
            run += 1
        else:
            counts.append(run)
            expected = bit
            run = 1
    counts.append(run)
    return tuple(counts)


def decode_binary_mask_rle(counts: Any, shape_hw: Any) -> np.ndarray:
    """Decode the canonical row-major alternating binary-mask RLE."""

    if (
        not isinstance(shape_hw, (tuple, list))
        or len(shape_hw) != 2
        or any(type(value) is not int or value <= 0 for value in shape_hw)
    ):
        raise ValueError("mask shape must contain two positive integers")
    if (
        not isinstance(counts, (tuple, list))
        or not counts
        or any(type(value) is not int or value < 0 for value in counts)
    ):
        raise ValueError("mask RLE counts must be nonnegative integers")
    total = int(shape_hw[0]) * int(shape_hw[1])
    if sum(counts) != total:
        raise ValueError("mask RLE counts do not match the declared shape")
    flat = np.empty(total, dtype=bool)
    offset = 0
    value = False
    for count in counts:
        flat[offset : offset + count] = value
        offset += count
        value = not value
    return flat.reshape((int(shape_hw[0]), int(shape_hw[1])))


def _mask_sha256(mask: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(mask, dtype=np.uint8).tobytes(order="C")).hexdigest()


def build_labeled_sample(
    render: RawRender,
    *,
    seed: int,
    scenario: DatasetScenario,
) -> LabeledSample:
    active_cup_bodies = {
        DatasetScenario.NO_CUP: frozenset(),
        DatasetScenario.ONE_CUP_DISTRACTORS: frozenset({"plastic_cup"}),
        DatasetScenario.TWO_CUPS: frozenset({"plastic_cup", "plastic_cup_b"}),
        DatasetScenario.CUP_NEAR_BOTTLE: frozenset({"plastic_cup"}),
        DatasetScenario.SMALL_FAR_CUP: frozenset({"plastic_cup"}),
        DatasetScenario.PARTIALLY_OCCLUDED_CUP: frozenset({"plastic_cup"}),
    }[scenario]
    visible_geom_ids = np.unique(render.geom_ids[render.geom_ids >= 0])
    if any(geom_id >= len(render.geom_body_ids) for geom_id in visible_geom_ids):
        raise ValueError("segmentation contains an out-of-range geom ID")
    instances: list[LabeledInstance] = []
    for body_id, body_name in sorted(render.body_names.items()):
        if body_name not in active_cup_bodies:
            continue
        target_geoms = np.flatnonzero(render.geom_body_ids == body_id)
        mask = np.isin(render.geom_ids, target_geoms)
        if not mask.any():
            continue
        paired_reference_mask = (
            None
            if render.amodal_geom_ids is None
            else np.isin(render.amodal_geom_ids, target_geoms)
        )
        amodal_mask = None if paired_reference_mask is None else mask | paired_reference_mask
        instances.append(
            LabeledInstance(
                body_id=body_id,
                body_name=body_name,
                mask=mask,
                polygon_xy=_polygon_from_mask(mask),
                amodal_mask=amodal_mask,
                paired_reference_mask=paired_reference_mask,
                occluder_body_name=render.occluder_body_name,
                occlusion_reference=render.occlusion_reference,
            )
        )
    return LabeledSample(seed, scenario, render.rgb8, tuple(instances))


def _bbox_area_px2(instance: LabeledInstance) -> float:
    height, width = instance.mask.shape
    x_values = [point[0] for point in instance.polygon_xy]
    y_values = [point[1] for point in instance.polygon_xy]
    return (max(x_values) - min(x_values)) * width * (max(y_values) - min(y_values)) * height


def _sample_meets_acceptance(sample: LabeledSample, geometry: SceneGeometry) -> bool:
    if sample.scenario == DatasetScenario.SMALL_FAR_CUP:
        if len(sample.instances) != 1:
            return False
        instance = sample.instances[0]
        return (
            instance.visible_pixel_count >= geometry.visible_pixel_count_minimum
            and 0.0 < _bbox_area_px2(instance) < geometry.small_bbox_area_max_exclusive
        )
    if sample.scenario == DatasetScenario.PARTIALLY_OCCLUDED_CUP:
        if len(sample.instances) != 1:
            return False
        instance = sample.instances[0]
        fraction = instance.visible_fraction
        return (
            instance.occlusion_measured
            and instance.occlusion_state == "partial"
            and instance.visible_pixel_count >= geometry.visible_pixel_count_minimum
            and instance.occluded_pixel_count is not None
            and instance.occluded_pixel_count >= 1
            and fraction is not None
            and geometry.partial_visible_fraction[0]
            <= fraction
            <= geometry.partial_visible_fraction[1]
        )
    return True


def _validate_observed_penetration_error(
    error: ScenePenetrationError,
    *,
    seed: int,
    scenario: DatasetScenario,
    attempt_index: int,
) -> TaskSceneGeometry:
    receipt = getattr(error, "receipt", None)
    if not isinstance(receipt, TaskSceneGeometry):
        raise ValueError("observed penetration receipt is missing or invalid")
    if (
        getattr(error, "seed", None) != seed
        or getattr(error, "scenario", None) != scenario
        or getattr(error, "attempt_index", None) != attempt_index
    ):
        raise ValueError("observed penetration context does not match the active attempt")
    receipt.validate_scope(scenario.cup_count)
    if receipt.accepted:
        raise ValueError("observed penetration receipt must reject the scene")
    return receipt


def select_bounded_render(
    seed: int,
    scenario: DatasetScenario,
    render_attempt: Callable[[np.random.Generator], RawRender],
    geometry: SceneGeometry,
    *,
    require_nonpenetrating_scene: bool = False,
    event_sink: RenderEventSink | None = None,
) -> RawRender:
    """Select the first deterministic render satisfying an augmented scenario gate."""

    bounded = scenario in {
        DatasetScenario.SMALL_FAR_CUP,
        DatasetScenario.PARTIALLY_OCCLUDED_CUP,
    }
    attempts = geometry.maximum_deterministic_attempts if bounded or require_nonpenetrating_scene else 1
    scenario_ordinal = tuple(DatasetScenario).index(scenario)
    for attempt_index in range(attempts):
        random = np.random.default_rng(
            np.random.SeedSequence([seed, scenario_ordinal, attempt_index])
        )
        try:
            render = render_attempt(random)
        except ScenePenetrationError as error:
            if require_nonpenetrating_scene:
                if event_sink is not None:
                    _validate_observed_penetration_error(
                        error,
                        seed=seed,
                        scenario=scenario,
                        attempt_index=attempt_index,
                    )
                continue
            raise
        if require_nonpenetrating_scene:
            if not isinstance(render.geometry_receipt, TaskSceneGeometry):
                raise ValueError("required geometry receipt is missing or invalid")
            render.geometry_receipt.validate_scope(scenario.cup_count)
            if not render.geometry_receipt.accepted:
                continue
        sample = build_labeled_sample(render, seed=seed, scenario=scenario)
        if _sample_meets_acceptance(sample, geometry):
            _emit_render_event(
                event_sink,
                "accepted",
                seed,
                scenario,
                attempt_index,
                render.geometry_receipt,
            )
            return render
        _emit_render_event(
            event_sink,
            "scenario_rejected",
            seed,
            scenario,
            attempt_index,
            render.geometry_receipt,
        )
    raise RuntimeError(f"{scenario.value} failed {attempts} deterministic attempts for seed {seed}")


class DatasetRenderer(Protocol):
    def render(self, seed: int, scenario: DatasetScenario) -> RawRender: ...

    def close(self) -> None: ...


def _exclusive_text(path: Path, contents: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        stream.write(contents)
        stream.flush()
        os.fsync(stream.fileno())


def _label_text(sample: LabeledSample) -> str:
    rows = []
    for instance in sample.instances:
        coordinates = " ".join(
            f"{coordinate:.9f}" for point in instance.polygon_xy for coordinate in point
        )
        rows.append(f"0 {coordinates}")
    return "" if not rows else "\n".join(rows) + "\n"


def _truth_instance_document(instance: LabeledInstance) -> dict[str, Any]:
    document: dict[str, Any] = {
        "body_id": instance.body_id,
        "body_name": instance.body_name,
        "mask_shape_hw": list(instance.mask.shape),
        "visible_pixel_count": instance.visible_pixel_count,
        "visible_mask_rle_counts": list(encode_binary_mask_rle(instance.mask)),
        "visible_mask_sha256": _mask_sha256(instance.mask),
        "polygon_xy": [list(point) for point in instance.polygon_xy],
        "occlusion_measured": instance.occlusion_measured,
        "occlusion_state": instance.occlusion_state,
    }
    if not instance.occlusion_measured:
        return document
    assert instance.amodal_mask is not None
    assert instance.paired_reference_mask is not None
    assert instance.amodal_pixel_count is not None
    assert instance.paired_reference_pixel_count is not None
    assert instance.occluded_pixel_count is not None
    assert instance.visible_fraction is not None
    document.update(
        {
            "paired_reference_pixel_count": instance.paired_reference_pixel_count,
            "paired_reference_mask_rle_counts": list(
                encode_binary_mask_rle(instance.paired_reference_mask)
            ),
            "paired_reference_mask_sha256": _mask_sha256(instance.paired_reference_mask),
            "amodal_pixel_count": instance.amodal_pixel_count,
            "amodal_mask_rle_counts": list(encode_binary_mask_rle(instance.amodal_mask)),
            "amodal_mask_sha256": _mask_sha256(instance.amodal_mask),
            "occluded_pixel_count": instance.occluded_pixel_count,
            "visible_fraction": instance.visible_fraction,
            "occluder_body_name": instance.occluder_body_name,
            "occlusion_reference": instance.occlusion_reference,
        }
    )
    return document


def _resolved_scenario_quotas(
    schedules: Mapping[str, tuple[DatasetScenario, ...]],
) -> dict[str, dict[str, int]]:
    return {
        split: dict(
            sorted(
                Counter(scenario.value for scenario in schedule).items(),
                key=lambda item: tuple(DatasetScenario).index(DatasetScenario(item[0])),
            )
        )
        for split, schedule in schedules.items()
    }


def _scene_geometry_document(geometry: SceneGeometry) -> dict[str, Any]:
    return {
        name: list(value) if isinstance(value, tuple) else value
        for name, value in asdict(geometry).items()
    }


def generate_dataset(
    config: DatasetConfig,
    output_root: Path,
    *,
    renderer: DatasetRenderer | None = None,
) -> dict[str, Any]:
    root = Path(output_root)
    if root.exists() or root.is_symlink():
        raise FileExistsError(f"output root already exists: {root}")
    root.mkdir(parents=True, mode=0o700)
    owned_renderer = renderer is None
    active_renderer = renderer or MuJoCoDatasetRenderer(config)
    seeds = split_seed_plan(config.split_counts, config.seed_starts)
    schedules = scenario_plan(config)
    samples: list[dict[str, Any]] = []
    artifacts: list[str] = []
    class_instance_total = 0
    try:
        for split in ("train", "val", "test"):
            for seed, scenario in zip(seeds[split], schedules[split], strict=True):
                render = active_renderer.render(seed, scenario)
                extra_truth: dict[str, Any] = {}
                if config.require_nonpenetrating_scene:
                    receipt = render.geometry_receipt
                    if not isinstance(receipt, TaskSceneGeometry) or not receipt.accepted:
                        raise ValueError("required accepted geometry receipt is missing or invalid")
                    receipt.validate_scope(scenario.cup_count)
                    extra_truth["scene_geometry"] = {
                        "policy": "task-visual-nonpenetration-v1",
                        "accepted": True,
                        **asdict(receipt),
                    }
                sample = build_labeled_sample(
                    render,
                    seed=seed,
                    scenario=scenario,
                )
                stem = f"{seed:09d}"
                image_relative = Path("images") / split / f"{stem}.png"
                label_relative = Path("labels") / split / f"{stem}.txt"
                truth_relative = Path("truth") / split / f"{stem}.json"
                image_path = root / image_relative
                image_path.parent.mkdir(parents=True, exist_ok=True)
                write_png_rgb8(sample.rgb8, image_path)
                _exclusive_text(root / label_relative, _label_text(sample))
                atomic_json(
                    root / truth_relative,
                    {
                        "seed": seed,
                        "split": split,
                        "scenario": scenario.value,
                        "configured_cup_count": scenario.cup_count,
                        "visible_instance_count": len(sample.instances),
                        "instances": [_truth_instance_document(item) for item in sample.instances],
                        **extra_truth,
                    },
                )
                relative_paths = (image_relative, label_relative, truth_relative)
                artifacts.extend(path.as_posix() for path in relative_paths)
                class_instance_total += len(sample.instances)
                samples.append(
                    {
                        "seed": seed,
                        "split": split,
                        "scenario": scenario.value,
                        "configured_cup_count": scenario.cup_count,
                        "visible_instance_count": len(sample.instances),
                        "image": image_relative.as_posix(),
                        "label": label_relative.as_posix(),
                        "truth": truth_relative.as_posix(),
                    }
                )
        dataset_yaml = (
            "path: .\n"
            "train: images/train\n"
            "val: images/val\n"
            "test: images/test\n"
            "names:\n"
            "  0: plastic_cup\n"
        )
        _exclusive_text(root / "dataset.yaml", dataset_yaml)
        artifacts.append("dataset.yaml")
        manifest: dict[str, Any] = {
            "schema_version": 2,
            "generator_commit": config.generator_commit,
            "mjcf_sha256": hashlib.sha256(config.mjcf_path.read_bytes()).hexdigest(),
            "camera_name": config.camera_name,
            "image_width": config.image_width,
            "image_height": config.image_height,
            "sample_count": len(samples),
            "split_counts": {
                split: config.split_counts[split] for split in sorted(config.split_counts)
            },
            "seed_starts": {
                split: config.seed_starts[split] for split in sorted(config.seed_starts)
            },
            "seed_ranges": {split: [values[0], values[-1]] for split, values in seeds.items()},
            "scenario_quotas": _resolved_scenario_quotas(schedules),
            "scene_geometry": _scene_geometry_document(config.geometry),
            "truth_contract": {
                "mask_order": "row_major",
                "mask_rle": "alternating_zero_one_counts_starting_with_zero",
                "mask_sha256": "sha256_uint8_row_major_bytes",
                "partial_occlusion_reference": "visible_union_paired_segmentation_with_declared_occluder_hidden",
                "canonical_amodal": "visible_bitwise_union_paired_reference",
            },
            "class_instance_totals": {"plastic_cup": class_instance_total},
            "samples": samples,
            "artifacts": sorted(artifacts),
        }
        if config.require_nonpenetrating_scene:
            manifest["scene_geometry_policy"] = "task-visual-nonpenetration-v1"
        atomic_json(root / "dataset-manifest.json", manifest)
        return manifest
    finally:
        if owned_renderer:
            active_renderer.close()


class MuJoCoDatasetRenderer:
    """Lazy MuJoCo renderer; segmentation is derived only from geom/body IDs."""

    def __init__(self, config: DatasetConfig | RendererSettings) -> None:
        try:
            import mujoco
        except ImportError as error:
            raise RuntimeError("MuJoCo Python binding is required for dataset rendering") from error
        self._mujoco = mujoco
        self._config = config.renderer_settings() if isinstance(config, DatasetConfig) else config
        self._model = mujoco.MjModel.from_xml_path(str(self._config.mjcf_path))
        self._data = mujoco.MjData(self._model)
        self._renderer = mujoco.Renderer(
            self._model,
            height=self._config.image_height,
            width=self._config.image_width,
        )
        # Color IDs are categorical: resolving multisamples can invent another
        # valid geom ID at an edge. Keep RGB antialiasing in its original context.
        self._segmentation_renderer = None
        rgb_samples = self._model.vis.quality.offsamples
        try:
            try:
                self._model.vis.quality.offsamples = 0
                self._segmentation_renderer = mujoco.Renderer(
                    self._model,
                    height=self._config.image_height,
                    width=self._config.image_width,
                )
                if self._segmentation_renderer._mjr_context.offSamples != 0:
                    raise RuntimeError("CATEGORICAL_MULTISAMPLING_FORBIDDEN")
            finally:
                self._model.vis.quality.offsamples = rgb_samples
        except Exception:
            self.close()
            raise
        self._base_camera_position = np.array(self._model.cam_pos[self._camera_id()], copy=True)
        camera_rotation = np.asarray(self._model.cam_mat0[self._camera_id()]).reshape(3, 3)
        self._camera_local_positive_z = np.array(camera_rotation[:, 2], copy=True)
        self._camera_local_positive_z /= np.linalg.norm(self._camera_local_positive_z)

    def _camera_id(self) -> int:
        identifier = self._mujoco.mj_name2id(
            self._model,
            self._mujoco.mjtObj.mjOBJ_CAMERA,
            self._config.camera_name,
        )
        if identifier < 0:
            raise RuntimeError(f"camera not found: {self._config.camera_name}")
        return int(identifier)

    def _set_free_joint_position(self, joint_name: str, xyz: np.ndarray) -> None:
        identifier = self._mujoco.mj_name2id(
            self._model,
            self._mujoco.mjtObj.mjOBJ_JOINT,
            joint_name,
        )
        if identifier < 0:
            raise RuntimeError(f"free joint not found: {joint_name}")
        address = int(self._model.jnt_qposadr[identifier])
        self._data.qpos[address : address + 3] = xyz
        self._data.qpos[address + 3 : address + 7] = (1.0, 0.0, 0.0, 0.0)
        dof_address = int(self._model.jnt_dofadr[identifier])
        self._data.qvel[dof_address : dof_address + 6] = 0.0

    def _prepare(self, random: np.random.Generator, scenario: DatasetScenario) -> None:
        self._mujoco.mj_resetData(self._model, self._data)
        geometry = self._config.geometry
        hidden = np.array((2.0, 2.0, 2.0))
        cup_a = np.array((0.02, -0.28, 0.165))
        cup_a_jitter = (
            geometry.partial_cup_xy_jitter_m
            if scenario == DatasetScenario.PARTIALLY_OCCLUDED_CUP
            else geometry.cup_a_xy_jitter_m
        )
        cup_a[:2] += random.uniform(*cup_a_jitter, size=2)
        cup_b = np.array((-0.09, -0.31, 0.165))
        cup_b[:2] += random.uniform(*geometry.cup_b_xy_jitter_m, size=2)
        bottle = np.array((0.11, -0.22, 0.19))
        bottle[:2] += random.uniform(*geometry.bottle_xy_jitter_m, size=2)
        if scenario == DatasetScenario.CUP_NEAR_BOTTLE:
            bottle[:2] = cup_a[:2] + np.array((0.075, 0.0))
        camera_id = self._camera_id()
        camera_position = self._base_camera_position + random.uniform(
            *geometry.ordinary_camera_jitter_m, size=3
        )
        if scenario == DatasetScenario.SMALL_FAR_CUP:
            camera_position += self._camera_local_positive_z * random.uniform(
                *geometry.far_camera_retreat_m
            )
        if scenario == DatasetScenario.PARTIALLY_OCCLUDED_CUP:
            toward_camera = camera_position[:2] - cup_a[:2]
            toward_camera /= np.linalg.norm(toward_camera)
            perpendicular = np.array((-toward_camera[1], toward_camera[0]))
            bottle[:2] = (
                cup_a[:2]
                + toward_camera * random.uniform(*geometry.partial_bottle_longitudinal_m)
                + perpendicular * random.uniform(*geometry.partial_bottle_perpendicular_m)
            )
        self._set_free_joint_position(
            "cup_free_joint", cup_a if scenario.cup_count >= 1 else hidden
        )
        self._set_free_joint_position(
            "cup_b_free_joint", cup_b if scenario.cup_count == 2 else hidden
        )
        self._set_free_joint_position("bottle_free_joint", bottle)
        self._model.cam_pos[camera_id] = camera_position
        for material_name in ("cup_a_material", "cup_b_material", "bottle_material"):
            material_id = self._mujoco.mj_name2id(
                self._model,
                self._mujoco.mjtObj.mjOBJ_MATERIAL,
                material_name,
            )
            if material_id >= 0:
                self._model.mat_rgba[material_id, :3] = random.uniform(0.1, 1.0, size=3)
        self._mujoco.mj_forward(self._model, self._data)

    def _geom_ids(self, segmentation: np.ndarray) -> np.ndarray:
        if segmentation.ndim != 3 or segmentation.shape[2] != 2:
            raise RuntimeError("MuJoCo segmentation render must have HxWx2 dimensions")
        geom_type = int(self._mujoco.mjtObj.mjOBJ_GEOM)
        first_is_type = segmentation[:, :, 0] == geom_type
        second_is_type = segmentation[:, :, 1] == geom_type
        result = np.full(segmentation.shape[:2], -1, dtype=np.int32)
        if int(first_is_type.sum()) >= int(second_is_type.sum()):
            result[first_is_type] = segmentation[:, :, 1][first_is_type]
        else:
            result[second_is_type] = segmentation[:, :, 0][second_is_type]
        return result

    def _segmentation(self) -> np.ndarray:
        renderer = self._segmentation_renderer
        renderer.enable_segmentation_rendering()
        try:
            renderer.update_scene(self._data, camera=self._config.camera_name)
            segmentation = np.array(renderer.render(), copy=True)
        finally:
            renderer.disable_segmentation_rendering()
        return self._geom_ids(segmentation)

    def _render_attempt(
        self,
        random: np.random.Generator,
        scenario: DatasetScenario,
        *,
        seed: int,
        attempt_index: int,
        event_sink: RenderEventSink | None = None,
    ) -> RawRender:
        self._prepare(random, scenario)
        geometry_receipt = None
        if self._config.require_nonpenetrating_scene:
            geometry_receipt = measure_task_scene_geometry(
                self._model, self._data, active_cup_count=scenario.cup_count
            )
            _emit_render_event(
                event_sink,
                "geometry_measured",
                seed,
                scenario,
                attempt_index,
                geometry_receipt,
            )
            if not geometry_receipt.accepted:
                _emit_render_event(
                    event_sink,
                    "penetration_rejected",
                    seed,
                    scenario,
                    attempt_index,
                    geometry_receipt,
                )
                raise ScenePenetrationError(
                    "intersecting task visual solids",
                    receipt=geometry_receipt,
                    seed=seed,
                    scenario=scenario,
                    attempt_index=attempt_index,
                )
        _emit_render_event(
            event_sink,
            "rgb_render_started",
            seed,
            scenario,
            attempt_index,
            geometry_receipt,
        )
        self._renderer.disable_segmentation_rendering()
        self._renderer.update_scene(self._data, camera=self._config.camera_name)
        rgb = np.array(self._renderer.render(), dtype=np.uint8, copy=True)
        _emit_render_event(
            event_sink,
            "rgb_render_finished",
            seed,
            scenario,
            attempt_index,
            geometry_receipt,
        )
        _emit_render_event(
            event_sink,
            "segmentation_render_started",
            seed,
            scenario,
            attempt_index,
            geometry_receipt,
        )
        visible_geom_ids = self._segmentation()
        _emit_render_event(
            event_sink,
            "segmentation_render_finished",
            seed,
            scenario,
            attempt_index,
            geometry_receipt,
        )
        amodal_geom_ids = None
        occluder_body_name = None
        occlusion_reference = None
        if scenario == DatasetScenario.PARTIALLY_OCCLUDED_CUP:
            self._set_free_joint_position("bottle_free_joint", np.array((2.0, 2.0, 2.0)))
            self._mujoco.mj_forward(self._model, self._data)
            _emit_render_event(
                event_sink,
                "segmentation_render_started",
                seed,
                scenario,
                attempt_index,
                geometry_receipt,
            )
            amodal_geom_ids = self._segmentation()
            _emit_render_event(
                event_sink,
                "segmentation_render_finished",
                seed,
                scenario,
                attempt_index,
                geometry_receipt,
            )
            occluder_body_name = "orange_bottle"
            occlusion_reference = "visible_union_paired_segmentation_with_declared_occluder_hidden"
        body_names = {
            body_id: name
            for body_id in range(self._model.nbody)
            if (
                name := self._mujoco.mj_id2name(
                    self._model, self._mujoco.mjtObj.mjOBJ_BODY, body_id
                )
            )
            is not None
        }
        return RawRender(
            rgb8=rgb,
            geom_ids=visible_geom_ids,
            geom_body_ids=np.asarray(self._model.geom_bodyid),
            body_names=body_names,
            amodal_geom_ids=amodal_geom_ids,
            occluder_body_name=occluder_body_name,
            occlusion_reference=occlusion_reference,
            geometry_receipt=geometry_receipt,
        )

    def render(
        self,
        seed: int,
        scenario: DatasetScenario,
        *,
        event_sink: RenderEventSink | None = None,
    ) -> RawRender:
        attempt_index = -1

        def render_attempt(random: np.random.Generator) -> RawRender:
            nonlocal attempt_index
            attempt_index += 1
            return self._render_attempt(
                random,
                scenario,
                seed=seed,
                attempt_index=attempt_index,
                event_sink=event_sink,
            )

        return select_bounded_render(
            seed,
            scenario,
            render_attempt,
            self._config.geometry,
            require_nonpenetrating_scene=self._config.require_nonpenetrating_scene,
            event_sink=event_sink,
        )

    def close(self) -> None:
        try:
            if self._segmentation_renderer is not None:
                self._segmentation_renderer.close()
        finally:
            self._renderer.close()
