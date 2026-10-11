"""Split plans, geometry seal requirements, scene plans, renderer settings and the dataset configuration."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping

from so101_demo.adapters.perception.mujoco_dataset.models import (
    _GEOMETRY_SEAL_KEYS,
    _NECK_KEYS,
    HEAD_SEARCH_DATASET_CONTRACT,
    HEAD_SEARCH_SCENARIOS,
    DatasetScenario,
    SceneGeometry,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


@dataclass(frozen=True, slots=True)
class RendererSettings:
    mjcf_path: Path
    camera_name: str = "task_camera"
    image_width: int = 640
    image_height: int = 480
    geometry: SceneGeometry = SceneGeometry()
    require_nonpenetrating_scene: bool = False
    neck_yaw_rad: tuple[float, float] | None = None
    camera_jitter_m: tuple[float, float] | None = None
    arm_pose_rad: tuple[float, ...] | None = None

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
        if self.camera_jitter_m is not None:
            low, high = (float(value) for value in self.camera_jitter_m)
            if low < 0.0 or high < low:
                raise ValueError("camera_jitter_m must be a nonnegative increasing two-value range")
            object.__setattr__(self, "camera_jitter_m", (low, high))
        object.__setattr__(self, "arm_pose_rad", _arm_pose_values(self.arm_pose_rad))
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
    camera_jitter_m: tuple[float, float] | None = None
    arm_pose_rad: tuple[float, ...] | None = None
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
        if self.camera_jitter_m is not None:
            low, high = (float(value) for value in self.camera_jitter_m)
            if low < 0.0 or high < low:
                raise ValueError("camera_jitter_m must be a nonnegative increasing two-value range")
            object.__setattr__(self, "camera_jitter_m", (low, high))
        object.__setattr__(self, "arm_pose_rad", _arm_pose_values(self.arm_pose_rad))
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
            camera_jitter_m=self.camera_jitter_m,
            arm_pose_rad=self.arm_pose_rad,
        )


_SEED_STARTS = {"train": 100000, "val": 200000, "test": 300000}


_MAX_SEED = 999_999_999


_LEGACY_SPLITS = ("train", "val", "test")


_TRAIN_VAL_SPLITS = ("train", "val")


_TRAIN_VAL_DATASET_CONTRACT = "so101-nonpenetrating-train-val-v1"


_TEST_SPLITS = ("test",)


_TEST_DATASET_CONTRACT = "so101-nonpenetrating-test-v1"


_NONPENETRATING_DATASET_CONTRACTS = frozenset({_TRAIN_VAL_DATASET_CONTRACT, _TEST_DATASET_CONTRACT})


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
    result = {split: base + (1 if index < remainder else 0) for index, split in enumerate(splits)}
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
            raise ValueError("geometry_seal must contain exactly " + ", ".join(_GEOMETRY_SEAL_KEYS))
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
                    scene_group_id=f"scene-{seed:09d}",
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


def _arm_pose_values(document: object) -> tuple[float, ...] | None:
    if document is None:
        return None
    if isinstance(document, (str, bytes)) or not isinstance(document, (list, tuple)):
        raise ValueError("arm_pose_rad must be a sequence of joint angles")
    values = tuple(float(value) for value in document)
    if any(not math.isfinite(value) for value in values):
        raise ValueError("arm_pose_rad must hold finite joint angles")
    return values


def _jitter_range_from_document(document: object) -> tuple[float, float] | None:
    if document is None:
        return None
    if isinstance(document, (str, bytes)) or not isinstance(document, (list, tuple)):
        raise ValueError("camera_jitter_m must be a two-value range")
    values = (float(document[0]), float(document[1]))
    if values[0] < 0.0 or values[1] < values[0]:
        raise ValueError("camera_jitter_m must be a nonnegative increasing two-value range")
    return values


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
        camera_jitter_m=_jitter_range_from_document(document.get("camera_jitter_m")),
        arm_pose_rad=_arm_pose_values(document.get("arm_pose_rad")),
        promotable=document.get("promotable", True),
    )
