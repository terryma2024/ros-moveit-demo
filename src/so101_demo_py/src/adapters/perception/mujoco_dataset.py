"""Deterministic MuJoCo object-ID dataset generation for YOLO segmentation."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Protocol

import numpy as np

from so101_demo.runtime.point_cloud_preview import write_png_rgb8
from so101_demo.runtime.task_artifacts import atomic_json


class DatasetScenario(str, Enum):
    NO_CUP = "no_cup"
    ONE_CUP_DISTRACTORS = "one_cup_distractors"
    TWO_CUPS = "two_cups"
    CUP_NEAR_BOTTLE = "cup_near_bottle"

    @property
    def cup_count(self) -> int:
        return {
            DatasetScenario.NO_CUP: 0,
            DatasetScenario.ONE_CUP_DISTRACTORS: 1,
            DatasetScenario.TWO_CUPS: 2,
            DatasetScenario.CUP_NEAR_BOTTLE: 1,
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


@dataclass(frozen=True, slots=True)
class RawRender:
    rgb8: np.ndarray
    geom_ids: np.ndarray
    geom_body_ids: np.ndarray
    body_names: Mapping[int, str]

    def __post_init__(self) -> None:
        rgb = np.array(self.rgb8, dtype=np.uint8, copy=True)
        geom_ids = np.array(self.geom_ids, dtype=np.int32, copy=True)
        geom_body_ids = np.array(self.geom_body_ids, dtype=np.int32, copy=True)
        if rgb.ndim != 3 or rgb.shape[2] != 3:
            raise ValueError("RGB render must have HxWx3 dimensions")
        if geom_ids.ndim != 2 or geom_ids.shape != rgb.shape[:2]:
            raise ValueError("RGB and object-ID dimensions must match")
        if geom_body_ids.ndim != 1:
            raise ValueError("geom_body_ids must be one-dimensional")
        normalized_names: dict[int, str] = {}
        for body_id, name in self.body_names.items():
            if int(body_id) < 0 or not isinstance(name, str) or not name:
                raise ValueError("body names must map nonnegative IDs to names")
            normalized_names[int(body_id)] = name
        rgb.setflags(write=False)
        geom_ids.setflags(write=False)
        geom_body_ids.setflags(write=False)
        object.__setattr__(self, "rgb8", rgb)
        object.__setattr__(self, "geom_ids", geom_ids)
        object.__setattr__(self, "geom_body_ids", geom_body_ids)
        object.__setattr__(self, "body_names", MappingProxyType(normalized_names))


@dataclass(frozen=True, slots=True)
class LabeledInstance:
    body_id: int
    body_name: str
    mask: np.ndarray
    polygon_xy: tuple[tuple[float, float], ...]

    def __post_init__(self) -> None:
        mask = np.array(self.mask, dtype=bool, copy=True)
        if mask.ndim != 2 or not mask.any():
            raise ValueError("instance mask must be a non-empty 2D mask")
        if len(self.polygon_xy) < 3:
            raise ValueError("instance polygon must have at least three points")
        if any(
            not (0.0 <= coordinate <= 1.0)
            for point in self.polygon_xy
            for coordinate in point
        ):
            raise ValueError("instance polygon coordinates must be normalized")
        mask.setflags(write=False)
        object.__setattr__(self, "mask", mask)


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
class DatasetConfig:
    mjcf_path: Path
    split_counts: Mapping[str, int]
    generator_commit: str
    camera_name: str = "task_camera"
    image_width: int = 640
    image_height: int = 480

    def __post_init__(self) -> None:
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
        object.__setattr__(self, "mjcf_path", path)
        object.__setattr__(self, "split_counts", MappingProxyType(counts))


_SEED_STARTS = {"train": 100000, "val": 200000, "test": 300000}


def split_seed_plan(split_counts: Mapping[str, int]) -> dict[str, tuple[int, ...]]:
    counts = dict(split_counts)
    if set(counts) != set(_SEED_STARTS):
        raise ValueError("split counts must contain train, val, and test")
    result: dict[str, tuple[int, ...]] = {}
    for split in ("train", "val", "test"):
        count = counts[split]
        if not isinstance(count, int) or count <= 0:
            raise ValueError("split counts must be positive integers")
        start = _SEED_STARTS[split]
        result[split] = tuple(range(start, start + count))
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
    counts = limited_split_counts(raw_counts, sample_limit)
    return DatasetConfig(
        mjcf_path=mjcf,
        split_counts=counts,
        generator_commit=generator_commit,
        camera_name=str(document["camera_name"]),
        image_width=int(document["image_width"]),
        image_height=int(document["image_height"]),
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
        return (first[0] - origin[0]) * (second[1] - origin[1]) - (
            first[1] - origin[1]
        ) * (second[0] - origin[0])

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


def build_labeled_sample(
    render: RawRender,
    *,
    seed: int,
    scenario: DatasetScenario,
) -> LabeledSample:
    visible_geom_ids = np.unique(render.geom_ids[render.geom_ids >= 0])
    if any(geom_id >= len(render.geom_body_ids) for geom_id in visible_geom_ids):
        raise ValueError("segmentation contains an out-of-range geom ID")
    instances: list[LabeledInstance] = []
    for body_id, body_name in sorted(render.body_names.items()):
        if body_name != "plastic_cup" and not body_name.startswith("plastic_cup_"):
            continue
        target_geoms = np.flatnonzero(render.geom_body_ids == body_id)
        mask = np.isin(render.geom_ids, target_geoms)
        if not mask.any():
            continue
        instances.append(
            LabeledInstance(
                body_id=body_id,
                body_name=body_name,
                mask=mask,
                polygon_xy=_polygon_from_mask(mask),
            )
        )
    return LabeledSample(seed, scenario, render.rgb8, tuple(instances))


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
            f"{coordinate:.9f}"
            for point in instance.polygon_xy
            for coordinate in point
        )
        rows.append(f"0 {coordinates}")
    return "" if not rows else "\n".join(rows) + "\n"


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
    seeds = split_seed_plan(config.split_counts)
    scenarios = tuple(DatasetScenario)
    samples: list[dict[str, Any]] = []
    artifacts: list[str] = []
    class_instance_total = 0
    try:
        for split in ("train", "val", "test"):
            for index, seed in enumerate(seeds[split]):
                scenario = scenarios[index % len(scenarios)]
                sample = build_labeled_sample(
                    active_renderer.render(seed, scenario),
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
                        "instances": [
                            {
                                "body_id": item.body_id,
                                "body_name": item.body_name,
                                "visible_pixel_count": int(item.mask.sum()),
                                "polygon_xy": [list(point) for point in item.polygon_xy],
                            }
                            for item in sample.instances
                        ],
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
            "schema_version": 1,
            "generator_commit": config.generator_commit,
            "mjcf_sha256": hashlib.sha256(config.mjcf_path.read_bytes()).hexdigest(),
            "camera_name": config.camera_name,
            "image_width": config.image_width,
            "image_height": config.image_height,
            "sample_count": len(samples),
            "split_counts": {
                split: config.split_counts[split] for split in sorted(config.split_counts)
            },
            "seed_ranges": {
                split: [values[0], values[-1]] for split, values in seeds.items()
            },
            "class_instance_totals": {"plastic_cup": class_instance_total},
            "samples": samples,
            "artifacts": sorted(artifacts),
        }
        atomic_json(root / "dataset-manifest.json", manifest)
        return manifest
    finally:
        if owned_renderer:
            active_renderer.close()


class MuJoCoDatasetRenderer:
    """Lazy MuJoCo renderer; segmentation is derived only from geom/body IDs."""

    def __init__(self, config: DatasetConfig) -> None:
        try:
            import mujoco
        except ImportError as error:
            raise RuntimeError("MuJoCo Python binding is required for dataset rendering") from error
        self._mujoco = mujoco
        self._config = config
        self._model = mujoco.MjModel.from_xml_path(str(config.mjcf_path))
        self._data = mujoco.MjData(self._model)
        self._renderer = mujoco.Renderer(
            self._model,
            height=config.image_height,
            width=config.image_width,
        )
        self._base_camera_position = np.array(
            self._model.cam_pos[self._camera_id()], copy=True
        )

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

    def _prepare(self, seed: int, scenario: DatasetScenario) -> None:
        random = np.random.default_rng(seed)
        self._mujoco.mj_resetData(self._model, self._data)
        hidden = np.array((2.0, 2.0, 2.0))
        cup_a = np.array((0.02, -0.28, 0.165))
        cup_a[:2] += random.uniform(-0.045, 0.045, size=2)
        cup_b = np.array((-0.09, -0.31, 0.165))
        cup_b[:2] += random.uniform(-0.025, 0.025, size=2)
        bottle = np.array((0.11, -0.22, 0.19))
        bottle[:2] += random.uniform(-0.025, 0.025, size=2)
        if scenario == DatasetScenario.CUP_NEAR_BOTTLE:
            bottle[:2] = cup_a[:2] + np.array((0.075, 0.0))
        self._set_free_joint_position(
            "cup_free_joint", cup_a if scenario.cup_count >= 1 else hidden
        )
        self._set_free_joint_position(
            "cup_b_free_joint", cup_b if scenario.cup_count == 2 else hidden
        )
        self._set_free_joint_position("bottle_free_joint", bottle)
        camera_id = self._camera_id()
        self._model.cam_pos[camera_id] = self._base_camera_position + random.uniform(
            -0.015, 0.015, size=3
        )
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

    def render(self, seed: int, scenario: DatasetScenario) -> RawRender:
        self._prepare(seed, scenario)
        self._renderer.disable_segmentation_rendering()
        self._renderer.update_scene(self._data, camera=self._config.camera_name)
        rgb = np.array(self._renderer.render(), dtype=np.uint8, copy=True)
        self._renderer.enable_segmentation_rendering()
        self._renderer.update_scene(self._data, camera=self._config.camera_name)
        segmentation = np.array(self._renderer.render(), copy=True)
        self._renderer.disable_segmentation_rendering()
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
            geom_ids=self._geom_ids(segmentation),
            geom_body_ids=np.asarray(self._model.geom_bodyid),
            body_names=body_names,
        )

    def close(self) -> None:
        self._renderer.close()
