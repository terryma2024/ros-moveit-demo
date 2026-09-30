"""Deterministic MuJoCo object-ID dataset generation for YOLO segmentation."""

from __future__ import annotations

import hashlib
import json
import math
import os
from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol

import numpy as np
from so101_demo.act.head_camera_geometry import scene_source_digests
from so101_demo.adapters.perception.mujoco_scene_geometry import (
    ScenePenetrationError,
    TaskSceneGeometry,
    measure_task_scene_geometry,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256
from so101_demo.runtime.point_cloud_preview import write_png_rgb8
from so101_demo.runtime.task_artifacts import atomic_json

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


@dataclass(frozen=True, slots=True)
class RendererSettings:
    mjcf_path: Path
    camera_name: str = "task_camera"
    image_width: int = 640
    image_height: int = 480
    geometry: SceneGeometry = SceneGeometry()
    require_nonpenetrating_scene: bool = False
    neck_yaw_rad: tuple[float, float] | None = None

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
        if self.neck_yaw_rad is not None:
            low, high = (float(value) for value in self.neck_yaw_rad)
            if not low < high:
                raise ValueError("neck_yaw_rad must be an increasing two-value range")
            object.__setattr__(self, "neck_yaw_rad", (low, high))
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
    dataset_contract: str | None = None
    schema_version: int = 2
    geometry_seal: GeometrySealRequirement | None = None
    neck_yaw_rad: tuple[float, float] | None = None
    promotable: bool = True

    def __post_init__(self) -> None:
        if type(self.require_nonpenetrating_scene) is not bool:
            raise ValueError("require_nonpenetrating_scene must be boolean")
        if self.dataset_contract in _NONPENETRATING_DATASET_CONTRACTS:
            if self.require_nonpenetrating_scene is not True:
                raise ValueError("nonpenetrating dataset contract requires its geometry gate")
            if type(self.schema_version) is not int or self.schema_version != 2:
                raise ValueError("nonpenetrating dataset contract requires schema version 2")
        path = Path(self.mjcf_path)
        if not path.is_absolute():
            path = path.resolve()
        if path.is_symlink() or not path.is_file():
            raise ValueError("mjcf_path must be a regular file")
        splits = _dataset_splits(self.dataset_contract)
        raw_counts = dict(self.split_counts)
        if set(raw_counts) != set(splits):
            raise ValueError("split_counts must exactly match the dataset contract")
        counts = {split: raw_counts[split] for split in splits}
        if any(type(value) is not int or value <= 0 for value in counts.values()):
            raise ValueError("split counts must be positive integers")
        if not self.generator_commit:
            raise ValueError("generator_commit must be non-empty")
        if self.image_width <= 0 or self.image_height <= 0:
            raise ValueError("image dimensions must be positive")
        if self.seed_starts is None and splits != _LEGACY_SPLITS:
            raise ValueError("seed_starts are required for the dataset contract")
        raw_starts = dict(_SEED_STARTS if self.seed_starts is None else self.seed_starts)
        if set(raw_starts) != set(splits):
            raise ValueError("seed_starts must exactly match the dataset contract")
        starts = {split: raw_starts[split] for split in splits}
        split_seed_plan(counts, starts)
        if type(self.promotable) is not bool:
            raise ValueError("promotable must be boolean")
        if self.geometry_seal is not None and not isinstance(
            self.geometry_seal, GeometrySealRequirement
        ):
            raise ValueError("geometry_seal must be a geometry seal requirement")
        if self.neck_yaw_rad is not None:
            low, high = (float(value) for value in self.neck_yaw_rad)
            if not low < high:
                raise ValueError("neck_yaw_rad must be an increasing two-value range")
            object.__setattr__(self, "neck_yaw_rad", (low, high))
        if self.dataset_contract == HEAD_SEARCH_DATASET_CONTRACT:
            if self.geometry_seal is None or self.geometry_seal.required is not True:
                raise ValueError(
                    "HEAD_CAMERA_GEOMETRY_SEAL_REQUIRED: the head search dataset contract requires "
                    "its frozen production-camera seal"
                )
            if self.neck_yaw_rad is None:
                raise ValueError(
                    "HEAD_DATASET_NECK_SAMPLING_REQUIRED: the head search dataset contract freezes "
                    "its neck-yaw sampling range"
                )
            head_scenario_quotas(counts)
        quotas = _validated_scenario_quotas(counts, self.scenario_quotas)
        if self.dataset_contract == _TRAIN_VAL_DATASET_CONTRACT:
            _validate_official_train_val_population(counts, starts, quotas)
        elif self.dataset_contract == _TEST_DATASET_CONTRACT:
            _validate_official_test_population(counts, starts, quotas)
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
            neck_yaw_rad=self.neck_yaw_rad,
        )


_SEED_STARTS = {"train": 100000, "val": 200000, "test": 300000}
_MAX_SEED = 999_999_999
_LEGACY_SPLITS = ("train", "val", "test")
_TRAIN_VAL_SPLITS = ("train", "val")
_TRAIN_VAL_DATASET_CONTRACT = "so101-nonpenetrating-train-val-v1"
_TEST_SPLITS = ("test",)
_TEST_DATASET_CONTRACT = "so101-nonpenetrating-test-v1"
_NONPENETRATING_DATASET_CONTRACTS = frozenset(
    {_TRAIN_VAL_DATASET_CONTRACT, _TEST_DATASET_CONTRACT}
)
_TRAIN_VAL_SPLIT_COUNTS = {"train": 1200, "val": 300}
_TRAIN_VAL_SEED_STARTS = {"train": 450_000_000, "val": 460_000_000}
_TRAIN_VAL_SCENARIO_QUOTAS = {
    "train": {scenario.value: 200 for scenario in DatasetScenario},
    "val": {scenario.value: 50 for scenario in DatasetScenario},
}
_TEST_SPLIT_COUNTS = {"test": 300}
_TEST_SEED_STARTS = {"test": 470_000_000}
_TEST_SCENARIO_QUOTAS = {
    "test": {scenario.value: 50 for scenario in DatasetScenario},
}


def _dataset_splits(dataset_contract: str | None) -> tuple[str, ...]:
    if dataset_contract is None or dataset_contract == HEAD_SEARCH_DATASET_CONTRACT:
        return _LEGACY_SPLITS
    if dataset_contract == _TRAIN_VAL_DATASET_CONTRACT:
        return _TRAIN_VAL_SPLITS
    if dataset_contract == _TEST_DATASET_CONTRACT:
        return _TEST_SPLITS
    raise ValueError("unknown dataset contract")


def _splits_for_maps(*maps: Mapping[str, object]) -> tuple[str, ...]:
    key_sets = [set(item) for item in maps]
    for splits in (_LEGACY_SPLITS, _TRAIN_VAL_SPLITS, _TEST_SPLITS):
        if all(keys == set(splits) for keys in key_sets):
            return splits
    raise ValueError("split maps must exactly match a supported dataset contract")


def _validated_scenario_quotas(
    split_counts: Mapping[str, int],
    scenario_quotas: Mapping[str, Mapping[str, int]] | None,
) -> dict[str, dict[str, int]] | None:
    if scenario_quotas is None:
        return None
    splits = _splits_for_maps(split_counts, scenario_quotas)
    known = {scenario.value for scenario in DatasetScenario}
    result: dict[str, dict[str, int]] = {}
    for split in splits:
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


def _validate_official_train_val_population(
    split_counts: Mapping[str, int],
    seed_starts: Mapping[str, int],
    scenario_quotas: Mapping[str, Mapping[str, int]] | None,
) -> None:
    if dict(split_counts) != _TRAIN_VAL_SPLIT_COUNTS:
        raise ValueError("official dataset contract population has invalid split counts")
    if dict(seed_starts) != _TRAIN_VAL_SEED_STARTS:
        raise ValueError("official dataset contract population has invalid seed starts")
    if scenario_quotas is None or any(
        dict(scenario_quotas[split]) != _TRAIN_VAL_SCENARIO_QUOTAS[split]
        for split in _TRAIN_VAL_SPLITS
    ):
        raise ValueError("official dataset contract population has invalid scenario quotas")


def _validate_official_test_population(
    split_counts: Mapping[str, int],
    seed_starts: Mapping[str, int],
    scenario_quotas: Mapping[str, Mapping[str, int]] | None,
) -> None:
    if dict(split_counts) != _TEST_SPLIT_COUNTS:
        raise ValueError("official test dataset contract population has invalid split counts")
    if dict(seed_starts) != _TEST_SEED_STARTS:
        raise ValueError("official test dataset contract population has invalid seed starts")
    if scenario_quotas is None or dict(scenario_quotas["test"]) != _TEST_SCENARIO_QUOTAS["test"]:
        raise ValueError("official test dataset contract population has invalid scenario quotas")


def scenario_plan(config: DatasetConfig) -> dict[str, tuple[DatasetScenario, ...]]:
    """Return the deterministic quota-derived scenario schedule for every split."""

    result: dict[str, tuple[DatasetScenario, ...]] = {}
    for split in config.split_counts:
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
    starts = dict(_SEED_STARTS if seed_starts is None else seed_starts)
    try:
        splits = _splits_for_maps(counts, starts)
    except ValueError as error:
        raise ValueError("seed_starts must exactly match split_counts") from error
    result: dict[str, tuple[int, ...]] = {}
    for split in splits:
        count = counts[split]
        if type(count) is not int or count <= 0:
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
    splits = _splits_for_maps(counts)
    if any(type(value) is not int or value <= 0 for value in counts.values()):
        raise ValueError("split counts must be positive integers")
    if sample_limit is None:
        return {split: counts[split] for split in splits}
    if type(sample_limit) is not int or sample_limit < len(splits):
        raise ValueError(f"sample_limit must be at least {len(splits)}")
    if sample_limit > sum(counts.values()):
        raise ValueError("sample_limit cannot exceed configured sample count")
    base, remainder = divmod(sample_limit, len(splits))
    result = {
        split: base + (1 if index < remainder else 0)
        for index, split in enumerate(splits)
    }
    if any(result[split] > counts[split] for split in result):
        raise ValueError("sample_limit allocation exceeds a configured split")
    return result


@dataclass(frozen=True, slots=True)
class GeometrySealRequirement:
    """One dataset profile's frozen acceptance for the production-camera seal."""

    required: bool
    accepted_seal_sha256: str

    def __post_init__(self) -> None:
        if type(self.required) is not bool:
            raise ValueError("geometry_seal required must be boolean")
        digest = self.accepted_seal_sha256
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
        ):
            raise ValueError("geometry_seal accepted_seal_sha256 must be a lowercase SHA256 digest")

    @classmethod
    def from_mapping(cls, document: object) -> "GeometrySealRequirement":
        if not isinstance(document, Mapping) or set(document) != set(_GEOMETRY_SEAL_KEYS):
            raise ValueError(
                "geometry_seal must contain exactly " + ", ".join(_GEOMETRY_SEAL_KEYS)
            )
        return cls(
            required=document["required"],
            accepted_seal_sha256=document["accepted_seal_sha256"],
        )

    def to_document(self) -> dict[str, object]:
        return {"required": self.required, "accepted_seal_sha256": self.accepted_seal_sha256}


def geometry_seal_sha256(seal: Mapping[str, Any]) -> str:
    """The seal's own digest: everything but the digest field, canonically encoded."""

    if not isinstance(seal, Mapping):
        raise ValueError("geometry seal must be a mapping")
    return canonical_sha256({key: value for key, value in seal.items() if key != "seal_sha256"})


@dataclass(frozen=True, slots=True)
class HeadCameraSceneSample:
    seed: int
    split: str
    scenario: str
    camera_name: str
    scene_group_id: str


@dataclass(frozen=True, slots=True)
class HeadCameraScenePlan:
    camera_name: str
    counts_by_split: Mapping[str, Mapping[str, int]]
    samples: tuple[HeadCameraSceneSample, ...]
    promotable: bool = True

    def counts(self, split: str) -> dict[str, int]:
        return dict(self.counts_by_split[split])

    def scenario_quotas(self) -> dict[str, dict[str, int]]:
        return {split: dict(values) for split, values in self.counts_by_split.items()}


def head_scenario_quotas(counts: Mapping[str, int]) -> dict[str, dict[str, int]]:
    """The four-scenario quotas one split count implies, or a refusal by name."""

    quotas: dict[str, dict[str, int]] = {}
    for split, value in dict(counts).items():
        if type(value) is not int or value <= 0 or value % len(HEAD_SEARCH_SCENARIOS) != 0:
            raise ValueError(
                "HEAD_SCENE_PLAN_COUNTS_INVALID: every split count must be a positive multiple of "
                f"{len(HEAD_SEARCH_SCENARIOS)}"
            )
        quotas[split] = {
            scenario: value // len(HEAD_SEARCH_SCENARIOS) for scenario in HEAD_SEARCH_SCENARIOS
        }
    return quotas


def _quota_schedule(quotas: Mapping[str, int]) -> tuple[str, ...]:
    remaining = {scenario: int(count) for scenario, count in quotas.items() if int(count) > 0}
    scheduled: list[str] = []
    while remaining:
        for scenario in HEAD_SEARCH_SCENARIOS:
            count = remaining.get(scenario, 0)
            if count <= 0:
                continue
            scheduled.append(scenario)
            if count == 1:
                del remaining[scenario]
            else:
                remaining[scenario] = count - 1
    return tuple(scheduled)


def split_scene_plan(
    *,
    camera_name: str,
    counts: Mapping[str, int],
    seed_starts: Mapping[str, int] | None = None,
    promotable: bool = True,
) -> HeadCameraScenePlan:
    """The head-camera plan: one image per world state, balanced across the four scenarios."""

    if not isinstance(camera_name, str) or not camera_name:
        raise ValueError("HEAD_SCENE_PLAN_CAMERA_INVALID: camera_name must be a non-empty string")
    if type(promotable) is not bool:
        raise ValueError("HEAD_SCENE_PLAN_PROMOTABLE_INVALID: promotable must be boolean")
    raw_counts = dict(counts)
    quotas = head_scenario_quotas(raw_counts)
    seeds = split_seed_plan(raw_counts, seed_starts)
    samples: list[HeadCameraSceneSample] = []
    for split, split_seeds in seeds.items():
        schedule = _quota_schedule(quotas[split])
        for seed, scenario in zip(split_seeds, schedule, strict=True):
            samples.append(
                HeadCameraSceneSample(
                    seed=seed,
                    split=split,
                    scenario=scenario,
                    camera_name=camera_name,
                    scene_group_id=f"{camera_name}-scene-{seed:09d}",
                )
            )
    return HeadCameraScenePlan(
        camera_name=camera_name,
        counts_by_split=MappingProxyType(
            {split: MappingProxyType(dict(values)) for split, values in quotas.items()}
        ),
        samples=tuple(samples),
        promotable=promotable,
    )


def _neck_range_from_document(document: object) -> tuple[float, float] | None:
    if document is None:
        return None
    if not isinstance(document, Mapping) or set(document) != set(_NECK_KEYS):
        raise ValueError("neck_yaw_rad must contain exactly " + ", ".join(_NECK_KEYS))
    return (float(document["min_rad"]), float(document["max_rad"]))


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
    dataset_contract = document.get("dataset_contract")
    splits = _dataset_splits(dataset_contract)
    if set(raw_counts) != set(splits):
        raise ValueError("split_counts must exactly match the dataset contract")
    if raw_seed_starts is None and splits != _LEGACY_SPLITS:
        raise ValueError("seed_starts are required for the dataset contract")
    effective_seed_starts = _SEED_STARTS if raw_seed_starts is None else raw_seed_starts
    split_seed_plan(raw_counts, effective_seed_starts)
    raw_scenario_quotas = document.get("scenario_quotas")
    if raw_scenario_quotas is not None and not isinstance(raw_scenario_quotas, dict):
        raise ValueError("scenario_quotas must be a mapping")
    if sample_limit is not None and raw_scenario_quotas is not None:
        raise ValueError("sample_limit cannot alter preregistered scenario quotas")
    counts = limited_split_counts(raw_counts, sample_limit)
    if dataset_contract == HEAD_SEARCH_DATASET_CONTRACT and raw_scenario_quotas is None:
        raw_scenario_quotas = head_scenario_quotas(counts)
    schema_version = document.get("schema_version")
    if dataset_contract in _NONPENETRATING_DATASET_CONTRACTS and (
        type(schema_version) is not int or schema_version != 2
    ):
        raise ValueError("nonpenetrating dataset contract requires schema version 2")
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
        dataset_contract=dataset_contract,
        schema_version=2 if dataset_contract is None else schema_version,
        geometry_seal=(
            None
            if document.get("geometry_seal") is None
            else GeometrySealRequirement.from_mapping(document["geometry_seal"])
        ),
        neck_yaw_rad=_neck_range_from_document(document.get("neck_yaw_rad")),
        promotable=document.get("promotable", True),
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


def _head_profile_context(
    config: DatasetConfig, geometry_seal: Mapping[str, Any] | None
) -> dict[str, Any] | None:
    """Refuse to render head-camera data unless the sealed production camera is the one in use."""

    if config.dataset_contract != HEAD_SEARCH_DATASET_CONTRACT:
        return None
    if geometry_seal is None:
        raise ValueError(
            "HEAD_CAMERA_GEOMETRY_SEAL_REQUIRED: refusing to render head-camera data without the "
            "production-camera seal"
        )
    if config.geometry_seal is None or geometry_seal_sha256(geometry_seal) != (
        config.geometry_seal.accepted_seal_sha256
    ):
        raise ValueError(
            "HEAD_CAMERA_GEOMETRY_SEAL_DRIFT: the supplied seal is not the accepted production-camera "
            "seal"
        )
    seal_camera = str(geometry_seal.get("camera_name", ""))
    if seal_camera != config.camera_name:
        raise ValueError(
            "HEAD_CAMERA_GEOMETRY_SEAL_CAMERA_MISMATCH: the seal names camera "
            f"{seal_camera!r} but this dataset renders {config.camera_name!r}"
        )
    seal_sources = geometry_seal.get("source_digests") or {}
    scene_sources = scene_source_digests(config.mjcf_path)
    if seal_sources.get("camera_source_sha256") != scene_sources["camera_source_sha256"]:
        raise ValueError(
            "HEAD_DATASET_CAMERA_SOURCE_DRIFT: this dataset's scene includes a different camera "
            "source than the sealed production camera"
        )
    lock = [float(value) for value in geometry_seal.get("lock_valid_neck_rad") or []]
    if len(lock) != 2 or config.neck_yaw_rad is None:
        raise ValueError(
            "HEAD_DATASET_NECK_SAMPLING_REQUIRED: the head dataset needs both a sealed safe interval "
            "and a frozen neck-yaw sampling range"
        )
    low, high = config.neck_yaw_rad
    if low < lock[0] or high > lock[1]:
        raise ValueError(
            "HEAD_DATASET_NECK_SAMPLING_UNSAFE: the neck-yaw sampling range "
            f"[{low}, {high}] leaves the sealed safe interval {lock}"
        )
    focal_px = (config.image_width / 2.0) / math.tan(float(geometry_seal["horizontal_fov_rad"]) / 2.0)
    return {
        "seal_sha256": geometry_seal_sha256(geometry_seal),
        "focal_px": focal_px,
        "principal_point_px": (config.image_width / 2.0, config.image_height / 2.0),
    }


def _sample_camera_document(
    config: DatasetConfig, context: Mapping[str, Any], render: RawRender, scene_group_id: str
) -> dict[str, Any]:
    if render.camera_name != config.camera_name:
        raise ValueError(
            "HEAD_DATASET_CAMERA_IDENTITY_MISSING: the render did not report the profile's camera "
            f"({render.camera_name!r} != {config.camera_name!r})"
        )
    if render.camera_position_m is None or render.camera_quaternion_wxyz is None:
        raise ValueError(
            "HEAD_DATASET_CAMERA_IDENTITY_MISSING: the render did not report the camera's world pose"
        )
    focal = float(context["focal_px"])
    cx, cy = (float(value) for value in context["principal_point_px"])
    return {
        "frame_id": render.camera_name,
        "width": config.image_width,
        "height": config.image_height,
        "k": [focal, 0.0, cx, 0.0, focal, cy, 0.0, 0.0, 1.0],
        "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
        "distortion_model": "plumb_bob",
        "position_m": list(render.camera_position_m),
        "quaternion_wxyz": list(render.camera_quaternion_wxyz),
        "neck_rad": render.neck_rad,
        "scene_group_id": scene_group_id,
    }


def generate_dataset(
    config: DatasetConfig,
    output_root: Path,
    *,
    renderer: DatasetRenderer | None = None,
    geometry_seal: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(output_root)
    if root.exists() or root.is_symlink():
        raise FileExistsError(f"output root already exists: {root}")
    head_context = _head_profile_context(config, geometry_seal)
    root.mkdir(parents=True, mode=0o700)
    owned_renderer = renderer is None
    active_renderer = renderer or MuJoCoDatasetRenderer(config)
    seeds = split_seed_plan(config.split_counts, config.seed_starts)
    schedules = scenario_plan(config)
    samples: list[dict[str, Any]] = []
    artifacts: list[str] = []
    class_instance_total = 0
    try:
        for split in config.split_counts:
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
                scene_group_id = None
                camera_document: dict[str, Any] | None = None
                raw_mask_sha256 = None
                if head_context is not None:
                    scene_group_id = f"{config.camera_name}-scene-{seed:09d}"
                    camera_document = _sample_camera_document(
                        config, head_context, render, scene_group_id
                    )
                    raw_mask_sha256 = canonical_sha256(
                        [
                            _mask_sha256(instance.mask)
                            for instance in sample.instances
                        ]
                    )
                stem = f"{seed:09d}"
                image_relative = Path("images") / split / f"{stem}.png"
                label_relative = Path("labels") / split / f"{stem}.txt"
                truth_relative = Path("truth") / split / f"{stem}.json"
                image_path = root / image_relative
                image_path.parent.mkdir(parents=True, exist_ok=True)
                write_png_rgb8(sample.rgb8, image_path)
                _exclusive_text(root / label_relative, _label_text(sample))
                truth_document: dict[str, Any] = {
                    "seed": seed,
                    "split": split,
                    "scenario": scenario.value,
                    "configured_cup_count": scenario.cup_count,
                    "visible_instance_count": len(sample.instances),
                    "instances": [_truth_instance_document(item) for item in sample.instances],
                    **extra_truth,
                }
                if scene_group_id is not None:
                    truth_document["scene_group_id"] = scene_group_id
                    truth_document["camera"] = camera_document
                    truth_document["raw_mask_sha256"] = raw_mask_sha256
                atomic_json(root / truth_relative, truth_document)
                relative_paths = (image_relative, label_relative, truth_relative)
                artifacts.extend(path.as_posix() for path in relative_paths)
                class_instance_total += len(sample.instances)
                sample_record: dict[str, Any] = {
                    "seed": seed,
                    "split": split,
                    "scenario": scenario.value,
                    "configured_cup_count": scenario.cup_count,
                    "visible_instance_count": len(sample.instances),
                    "image": image_relative.as_posix(),
                    "label": label_relative.as_posix(),
                    "truth": truth_relative.as_posix(),
                }
                if scene_group_id is not None:
                    sample_record["scene_group_id"] = scene_group_id
                    sample_record["camera"] = camera_document
                    sample_record["raw_mask_sha256"] = raw_mask_sha256
                samples.append(sample_record)
        dataset_yaml = "path: .\n"
        for split in config.split_counts:
            dataset_yaml += f"{split}: images/{split}\n"
        dataset_yaml += "names:\n  0: plastic_cup\n"
        _exclusive_text(root / "dataset.yaml", dataset_yaml)
        artifacts.append("dataset.yaml")
        manifest: dict[str, Any] = {
            "schema_version": config.schema_version,
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
        if config.dataset_contract is not None:
            manifest["dataset_contract"] = config.dataset_contract
            manifest["member_splits"] = list(_dataset_splits(config.dataset_contract))
        manifest["promotable"] = config.promotable
        if head_context is not None:
            manifest["geometry_seal_sha256"] = head_context["seal_sha256"]
            manifest["camera_identity"] = {
                "frame_id": config.camera_name,
                "width": config.image_width,
                "height": config.image_height,
                "focal_px": head_context["focal_px"],
                "distortion_model": "plumb_bob",
            }
            manifest["neck_yaw_rad"] = list(config.neck_yaw_rad or ())
            group_ids = [item["scene_group_id"] for item in samples]
            if len(set(group_ids)) != len(group_ids):
                raise ValueError(
                    "HEAD_DATASET_SCENE_GROUP_DUPLICATE: a scene_group_id appears twice in one dataset"
                )
            manifest["scene_group_ids"] = group_ids
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
        self._neck_rad: float | None = None
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
        self._neck_rad = None
        if self._config.neck_yaw_rad is not None:
            low, high = self._config.neck_yaw_rad
            neck_id = self._mujoco.mj_name2id(
                self._model, self._mujoco.mjtObj.mjOBJ_JOINT, "neck_yaw_joint"
            )
            if neck_id < 0:
                raise RuntimeError("neck joint not found: neck_yaw_joint")
            self._neck_rad = float(random.uniform(low, high))
            self._data.qpos[int(self._model.jnt_qposadr[neck_id])] = self._neck_rad
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
        camera_id = self._camera_id()
        camera_quaternion = np.zeros(4, dtype=np.float64)
        self._mujoco.mju_mat2Quat(camera_quaternion, self._data.cam_xmat[camera_id])
        return RawRender(
            rgb8=rgb,
            geom_ids=visible_geom_ids,
            geom_body_ids=np.asarray(self._model.geom_bodyid),
            body_names=body_names,
            amodal_geom_ids=amodal_geom_ids,
            occluder_body_name=occluder_body_name,
            occlusion_reference=occlusion_reference,
            geometry_receipt=geometry_receipt,
            camera_name=self._config.camera_name,
            neck_rad=self._neck_rad,
            camera_position_m=tuple(float(value) for value in self._data.cam_xpos[camera_id]),
            camera_quaternion_wxyz=tuple(float(value) for value in camera_quaternion),
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


def verify_head_search_manifest(
    manifest: Mapping[str, Any],
    *,
    dataset_root: Path,
    geometry_seal: Mapping[str, Any],
    expected_train: int,
    expected_val: int,
    expected_test: int,
    require_non_promotable: bool = False,
) -> dict[str, Any]:
    """Read one head-camera manifest back against its own files and the accepted seal.

    A manifest is a claim; this is the check that the claim is about the dataset on disk: exact
    counts, four balanced scenarios, one image per `scene_group_id`, a camera identity on every
    sample, every declared file present, and a promotion state that matches the profile it names.
    """

    if not isinstance(manifest, Mapping):
        raise ValueError("HEAD_DATASET_MANIFEST_INVALID: manifest must be a mapping")
    expected = {"train": expected_train, "val": expected_val, "test": expected_test}
    for value in expected.values():
        if type(value) is not int or value <= 0:
            raise ValueError(
                "HEAD_DATASET_EXPECTATION_INVALID: expected counts must be positive integers"
            )
    if manifest.get("dataset_contract") != HEAD_SEARCH_DATASET_CONTRACT:
        raise ValueError(
            "HEAD_DATASET_CONTRACT_INVALID: this is not a head search dataset manifest"
        )
    if manifest.get("camera_name") != geometry_seal.get("camera_name"):
        raise ValueError(
            "HEAD_DATASET_CAMERA_MISMATCH: the manifest names camera "
            f"{manifest.get('camera_name')!r} but the seal names {geometry_seal.get('camera_name')!r}"
        )
    if manifest.get("geometry_seal_sha256") != geometry_seal_sha256(geometry_seal):
        raise ValueError(
            "HEAD_DATASET_GEOMETRY_SEAL_DRIFT: the manifest was not produced under this seal"
        )
    raw_counts = manifest.get("split_counts") or {}
    split_counts = {split: int(raw_counts.get(split, 0)) for split in expected}
    if split_counts != expected:
        raise ValueError(
            f"HEAD_DATASET_COUNT_MISMATCH: the manifest holds {split_counts}, expected {expected}"
        )
    samples = list(manifest.get("samples") or [])
    if len(samples) != sum(expected.values()):
        raise ValueError(
            f"HEAD_DATASET_COUNT_MISMATCH: the manifest holds {len(samples)} samples, expected "
            f"{sum(expected.values())}"
        )
    groups: dict[str, str] = {}
    scenario_counts: dict[str, Counter[str]] = {split: Counter() for split in expected}
    root = Path(dataset_root)
    for sample in samples:
        split = str(sample.get("split"))
        if split not in expected:
            raise ValueError(f"HEAD_DATASET_SPLIT_INVALID: unknown split {split!r}")
        scenario = str(sample.get("scenario"))
        if scenario not in HEAD_SEARCH_SCENARIOS:
            raise ValueError(f"HEAD_DATASET_SCENARIO_INVALID: unknown scenario {scenario!r}")
        group = str(sample.get("scene_group_id") or "")
        if not group:
            raise ValueError(
                f"HEAD_DATASET_SCENE_GROUP_MISSING: seed {sample.get('seed')} declares no scene group"
            )
        camera = sample.get("camera") or {}
        if (
            camera.get("frame_id") != geometry_seal.get("camera_name")
            or len(camera.get("k") or []) != 9
            or len(camera.get("distortion") or []) != 5
        ):
            raise ValueError(
                "HEAD_DATASET_CAMERA_IDENTITY_MISSING: seed "
                f"{sample.get('seed')} carries no complete camera identity"
            )
        if group in groups:
            raise ValueError(
                f"HEAD_DATASET_SCENE_GROUP_DUPLICATE: {group} is claimed by more than one sample"
            )
        groups[group] = split
        scenario_counts[split][scenario] += 1
        for key in ("image", "label", "truth"):
            relative = sample.get(key)
            if not relative or not (root / str(relative)).is_file():
                raise ValueError(
                    f"HEAD_DATASET_FILE_MISSING: {key} {relative!r} of seed {sample.get('seed')} "
                    "is not on disk"
                )
    for split, quota in head_scenario_quotas(expected).items():
        observed = dict(scenario_counts[split])
        if observed != quota:
            raise ValueError(
                f"HEAD_DATASET_SCENARIO_QUOTA_MISMATCH: {split} holds {observed}, expected {quota}"
            )
    for split, count in expected.items():
        images = sorted((root / "images" / split).glob("*.png"))
        labels = sorted((root / "labels" / split).glob("*.txt"))
        truths = sorted((root / "truth" / split).glob("*.json"))
        if not len(images) == len(labels) == len(truths) == count:
            raise ValueError(
                f"HEAD_DATASET_COUNT_MISMATCH: {split} holds {len(images)} images, {len(labels)} "
                f"labels and {len(truths)} truth files, expected {count} of each"
            )
    promotable = bool(manifest.get("promotable", False))
    if require_non_promotable and promotable:
        raise ValueError(
            "HEAD_DATASET_PROMOTABLE_FORBIDDEN: a smoke dataset must stay non-promotable"
        )
    if not require_non_promotable and not promotable:
        raise ValueError(
            "HEAD_DATASET_NOT_PROMOTABLE: this manifest is a smoke dataset and cannot satisfy the "
            "production contract"
        )
    return {
        "status": "OK",
        "sample_count": len(samples),
        "scene_group_count": len(groups),
        "split_counts": dict(split_counts),
        "scenario_counts": {split: dict(values) for split, values in scenario_counts.items()},
        "promotable": promotable,
        "geometry_seal_sha256": str(manifest.get("geometry_seal_sha256")),
    }
