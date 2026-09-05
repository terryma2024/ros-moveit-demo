"""Convert the immutable synthetic YOLO-Seg data into DINO box inventories."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

import yaml
from so101_demo.adapters.perception.mujoco_dataset import decode_binary_mask_rle

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")
_LEGACY_SPLITS = ("train", "val", "test")
_TRAIN_VAL_SPLITS = ("train", "val")
_TRAIN_VAL_DATASET_CONTRACT = "so101-nonpenetrating-train-val-v1"
_SCENE_GEOMETRY_POLICY = "task-visual-nonpenetration-v1"
_TRAIN_VAL_SCENE_GEOMETRY = {
    "ordinary_camera_jitter_m": [-0.015, 0.015],
    "cup_a_xy_jitter_m": [-0.045, 0.045],
    "cup_b_xy_jitter_m": [-0.025, 0.025],
    "bottle_xy_jitter_m": [-0.025, 0.025],
    "far_camera_retreat_m": [2.4, 3.0],
    "partial_cup_xy_jitter_m": [-0.025, 0.025],
    "partial_bottle_longitudinal_m": [0.055, 0.105],
    "partial_bottle_perpendicular_m": [-0.025, 0.025],
    "small_bbox_area_max_exclusive": 1024.0,
    "visible_pixel_count_minimum": 64,
    "partial_visible_fraction": [0.35, 0.8],
    "maximum_deterministic_attempts": 64,
}
_TRAIN_VAL_TRUTH_CONTRACT = {
    "mask_order": "row_major",
    "mask_rle": "alternating_zero_one_counts_starting_with_zero",
    "mask_sha256": "sha256_uint8_row_major_bytes",
    "partial_occlusion_reference": (
        "visible_union_paired_segmentation_with_declared_occluder_hidden"
    ),
    "canonical_amodal": "visible_bitwise_union_paired_reference",
}
_CUP_BODY_NAMES = frozenset({"plastic_cup", "plastic_cup_b"})
_SCENARIO_CUPS = {
    "no_cup": (),
    "one_cup_distractors": ("plastic_cup",),
    "two_cups": ("plastic_cup", "plastic_cup_b"),
    "cup_near_bottle": ("plastic_cup",),
    "small_far_cup": ("plastic_cup",),
    "partially_occluded_cup": ("plastic_cup",),
}
_TRAIN_VAL_SCENARIOS = tuple(_SCENARIO_CUPS)
_TRAIN_VAL_SPLIT_COUNTS = {"train": 1200, "val": 300}
_TRAIN_VAL_SEED_STARTS = {"train": 450_000_000, "val": 460_000_000}
_TRAIN_VAL_SEED_RANGES = {
    "train": [450_000_000, 450_001_199],
    "val": [460_000_000, 460_000_299],
}
_TRAIN_VAL_SCENARIO_QUOTAS = {
    "train": {scenario: 200 for scenario in _TRAIN_VAL_SCENARIOS},
    "val": {scenario: 50 for scenario in _TRAIN_VAL_SCENARIOS},
}
_VISUAL_GEOMS = {
    "plastic_cup": frozenset(
        {
            "cup_a_wall_near_visual",
            "cup_a_wall_01_visual",
            "cup_a_wall_02_visual",
            "cup_a_wall_03_visual",
            "cup_a_wall_04_visual",
            "cup_a_wall_05_visual",
            "cup_a_wall_opposite_visual",
            "cup_a_wall_07_visual",
            "cup_a_wall_08_visual",
            "cup_a_wall_09_visual",
            "cup_a_wall_10_visual",
            "cup_a_wall_11_visual",
            "cup_a_bottom_visual",
        }
    ),
    "plastic_cup_b": frozenset(
        {
            "cup_b_wall_near_visual",
            "cup_b_wall_01_visual",
            "cup_b_wall_02_visual",
            "cup_b_wall_03_visual",
            "cup_b_wall_04_visual",
            "cup_b_wall_05_visual",
            "cup_b_wall_opposite_visual",
            "cup_b_wall_07_visual",
            "cup_b_wall_08_visual",
            "cup_b_wall_09_visual",
            "cup_b_wall_10_visual",
            "cup_b_wall_11_visual",
            "cup_b_bottom_visual",
        }
    ),
    "orange_bottle": frozenset({"bottle_visual", "bottle_neck_visual"}),
    "table": frozenset({"table_visual"}),
    "neutral_block": frozenset({"neutral_block_visual"}),
    "base_pedestal": frozenset({"base_pedestal_visual"}),
}
_SAMPLE_FIELDS = {
    "configured_cup_count",
    "image",
    "label",
    "scenario",
    "seed",
    "split",
    "truth",
    "visible_instance_count",
}


class GroundingDinoDatasetError(RuntimeError):
    """Fail-closed dataset conversion error with a stable reason code."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class BoundingBox:
    """Canonical normalized and pixel-coordinate xyxy box."""

    normalized_xyxy: tuple[float, float, float, float]
    absolute_xyxy: tuple[float, float, float, float]


def _fail(code: str, detail: str) -> GroundingDinoDatasetError:
    return GroundingDinoDatasetError(code, detail)


def _positive_dimension(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise _fail("MANIFEST_INVALID", f"{name} must be a positive integer")
    return value


def polygon_to_box(
    polygon: Sequence[Sequence[float]], image_width: int, image_height: int
) -> BoundingBox:
    """Return an xyxy box for a normalized polygon, including image boundaries."""

    width = _positive_dimension(image_width, "image_width")
    height = _positive_dimension(image_height, "image_height")
    if not isinstance(polygon, Sequence) or isinstance(polygon, (str, bytes)):
        raise _fail("POLYGON_INVALID", "polygon must be a point sequence")
    points: list[tuple[float, float]] = []
    for point in polygon:
        if not isinstance(point, Sequence) or isinstance(point, (str, bytes)) or len(point) != 2:
            raise _fail("POLYGON_INVALID", "each polygon point must contain x and y")
        x, y = point
        if (
            isinstance(x, bool)
            or isinstance(y, bool)
            or not isinstance(x, (int, float))
            or not isinstance(y, (int, float))
        ):
            raise _fail("POLYGON_INVALID", "polygon coordinates must be numbers")
        normalized_x = float(x)
        normalized_y = float(y)
        if (
            not math.isfinite(normalized_x)
            or not math.isfinite(normalized_y)
            or not 0.0 <= normalized_x <= 1.0
            or not 0.0 <= normalized_y <= 1.0
        ):
            raise _fail("POLYGON_INVALID", "polygon coordinates must be finite in [0, 1]")
        points.append((normalized_x, normalized_y))
    if len(points) < 3:
        raise _fail("POLYGON_INVALID", "polygon must contain at least three points")
    left = min(point[0] for point in points)
    top = min(point[1] for point in points)
    right = max(point[0] for point in points)
    bottom = max(point[1] for point in points)
    if right <= left or bottom <= top:
        raise _fail("POLYGON_INVALID", "polygon produces a degenerate box")
    return BoundingBox(
        normalized_xyxy=(left, top, right, bottom),
        absolute_xyxy=(left * width, top * height, right * width, bottom * height),
    )


def binary_mask_to_box(mask: Any, image_width: int, image_height: int) -> BoundingBox:
    """Return the exact nonzero-pixel extent of a visible binary mask."""

    width = _positive_dimension(image_width, "image_width")
    height = _positive_dimension(image_height, "image_height")
    if getattr(mask, "shape", None) != (height, width):
        raise _fail("VISIBLE_TRUTH_INVALID", "mask shape differs from image")
    rows, columns = mask.nonzero()
    if len(rows) == 0:
        raise _fail("VISIBLE_TRUTH_INVALID", "mask is empty")
    left = int(columns.min())
    top = int(rows.min())
    right = int(columns.max())
    bottom = int(rows.max())
    if right <= left or bottom <= top:
        raise _fail("VISIBLE_TRUTH_INVALID", "mask produces a degenerate box")
    x_scale = max(1, width - 1)
    y_scale = max(1, height - 1)
    return BoundingBox(
        normalized_xyxy=(
            left / x_scale,
            top / y_scale,
            right / x_scale,
            bottom / y_scale,
        ),
        absolute_xyxy=(float(left), float(top), float(right), float(bottom)),
    )


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _canonical_json(document: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _relative_path(value: object, *, field: str) -> PurePosixPath:
    if not isinstance(value, str) or not value:
        raise _fail("MANIFEST_INVALID", f"{field} must be a non-empty path")
    relative = PurePosixPath(value)
    if (
        relative.is_absolute()
        or "\\" in value
        or any(part in {"", ".", ".."} for part in relative.parts)
    ):
        raise _fail("SOURCE_PATH_INVALID", f"{field} escapes source root: {value!r}")
    return relative


def _source_file(source_root: Path, relative: PurePosixPath) -> Path:
    candidate = source_root.joinpath(*relative.parts)
    current = source_root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise _fail("SOURCE_PATH_INVALID", f"source member is a symlink: {relative}")
    if not candidate.is_file():
        raise _fail("SOURCE_MEMBER_MISSING", relative.as_posix())
    return candidate


def _read_bytes(source_root: Path, relative: PurePosixPath) -> bytes:
    try:
        return _source_file(source_root, relative).read_bytes()
    except OSError as error:
        raise _fail("SOURCE_READ_FAILED", f"{relative}: {error}") from error


def _json_mapping(payload: bytes, *, member: str) -> dict[str, Any]:
    try:
        document = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise _fail("SOURCE_JSON_INVALID", f"{member}: {error}") from error
    if not isinstance(document, Mapping):
        raise _fail("SOURCE_JSON_INVALID", f"{member} must contain an object")
    return dict(document)


def _integer(value: object, *, field: str, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise _fail("MANIFEST_INVALID", f"{field} must be an integer >= {minimum}")
    return value


def _dataset_contract(source_root: Path, splits: tuple[str, ...]) -> None:
    relative = PurePosixPath("dataset.yaml")
    payload = _read_bytes(source_root, relative)
    try:
        document = yaml.safe_load(payload)
    except yaml.YAMLError as error:
        raise _fail("DATASET_YAML_INVALID", str(error)) from error
    if not isinstance(document, Mapping):
        raise _fail("DATASET_YAML_INVALID", "dataset.yaml must contain a mapping")
    expected = {
        "path": ".",
        "train": "images/train",
        "val": "images/val",
        "names": {0: "plastic_cup"},
    }
    if splits == _LEGACY_SPLITS:
        expected = {
            "path": ".",
            "train": "images/train",
            "val": "images/val",
            "test": "images/test",
            "names": {0: "plastic_cup"},
        }
    if dict(document) != expected:
        raise _fail("DATASET_YAML_INVALID", "dataset contract is not the fixed cup dataset")


def _manifest(source_root: Path) -> tuple[dict[str, Any], bytes]:
    relative = PurePosixPath("dataset-manifest.json")
    payload = _read_bytes(source_root, relative)
    document = _json_mapping(payload, member=relative.as_posix())
    dataset_contract = document.get("dataset_contract")
    if dataset_contract is None:
        if "dataset_contract" in document:
            raise _fail("MANIFEST_INVALID", "dataset_contract must be a supported string")
        splits = _LEGACY_SPLITS
        if "member_splits" in document:
            raise _fail("MANIFEST_INVALID", "legacy manifest must not declare member_splits")
    elif dataset_contract == _TRAIN_VAL_DATASET_CONTRACT:
        splits = _TRAIN_VAL_SPLITS
        if document.get("member_splits") != list(splits):
            raise _fail("MANIFEST_INVALID", "member_splits must be exactly train then val")
    else:
        raise _fail("MANIFEST_INVALID", "unknown dataset_contract")
    schema_version = document.get("schema_version")
    if splits == _TRAIN_VAL_SPLITS:
        schema_is_valid = type(schema_version) is int and schema_version == 2
    else:
        schema_is_valid = schema_version in {1, 2}
    if not schema_is_valid:
        raise _fail("MANIFEST_INVALID", "schema_version is invalid for the dataset contract")
    samples = document.get("samples")
    if not isinstance(samples, list):
        raise _fail("MANIFEST_INVALID", "samples must be a list")
    sample_count = _integer(document.get("sample_count"), field="sample_count")
    if sample_count != len(samples):
        raise _fail("MANIFEST_INVALID", "sample_count does not match samples")
    split_counts = document.get("split_counts")
    if not isinstance(split_counts, Mapping) or set(split_counts) != set(splits):
        raise _fail("MANIFEST_INVALID", "split_counts do not match the dataset contract")
    for split in splits:
        _integer(
            split_counts[split],
            field=f"split_counts.{split}",
            minimum=1 if splits == _TRAIN_VAL_SPLITS else 0,
        )
    _positive_dimension(document.get("image_width"), "image_width")
    _positive_dimension(document.get("image_height"), "image_height")
    generator_commit = document.get("generator_commit")
    mjcf_sha256 = document.get("mjcf_sha256")
    if not isinstance(generator_commit, str) or _COMMIT.fullmatch(generator_commit) is None:
        raise _fail("MANIFEST_INVALID", "generator_commit must be a lowercase Git SHA")
    if not isinstance(mjcf_sha256, str) or _SHA256.fullmatch(mjcf_sha256) is None:
        raise _fail("MANIFEST_INVALID", "mjcf_sha256 must be a lowercase SHA256")
    if schema_version == 2:
        quotas = document.get("scenario_quotas")
        if not isinstance(quotas, Mapping) or set(quotas) != set(splits):
            raise _fail("MANIFEST_INVALID", "scenario_quotas must contain all splits")
        for split in splits:
            split_quotas = quotas[split]
            if not isinstance(split_quotas, Mapping) or any(
                isinstance(value, bool) or not isinstance(value, int) or value <= 0
                for value in split_quotas.values()
            ):
                raise _fail("MANIFEST_INVALID", f"scenario_quotas.{split} is invalid")
            if sum(split_quotas.values()) != split_counts[split]:
                raise _fail("MANIFEST_INVALID", f"scenario_quotas.{split} count mismatch")
        if not isinstance(document.get("scene_geometry"), Mapping):
            raise _fail("MANIFEST_INVALID", "scene_geometry must be present in schema 2")
        if not isinstance(document.get("truth_contract"), Mapping):
            raise _fail("MANIFEST_INVALID", "truth_contract must be present in schema 2")
    if splits == _TRAIN_VAL_SPLITS:
        if document.get("scene_geometry_policy") != _SCENE_GEOMETRY_POLICY:
            raise _fail("MANIFEST_INVALID", "scene_geometry_policy is invalid")
        if document.get("scene_geometry") != _TRAIN_VAL_SCENE_GEOMETRY:
            raise _fail("MANIFEST_INVALID", "scene_geometry is invalid")
        if document.get("truth_contract") != _TRAIN_VAL_TRUTH_CONTRACT:
            raise _fail("MANIFEST_INVALID", "truth_contract is invalid")
        seed_starts = document.get("seed_starts")
        seed_ranges = document.get("seed_ranges")
        if not isinstance(seed_starts, Mapping) or set(seed_starts) != set(splits):
            raise _fail("MANIFEST_INVALID", "seed_starts do not match member_splits")
        if not isinstance(seed_ranges, Mapping) or set(seed_ranges) != set(splits):
            raise _fail("MANIFEST_INVALID", "seed_ranges do not match member_splits")
        occupied: list[tuple[int, int]] = []
        for split in splits:
            start = _integer(seed_starts[split], field=f"seed_starts.{split}")
            value = seed_ranges[split]
            if (
                not isinstance(value, list)
                or len(value) != 2
                or any(type(item) is not int for item in value)
                or value != [start, start + split_counts[split] - 1]
            ):
                raise _fail("MANIFEST_INVALID", f"seed_ranges.{split} is invalid")
            occupied.append((value[0], value[1]))
        if occupied[0][1] >= occupied[1][0] and occupied[1][1] >= occupied[0][0]:
            raise _fail("SPLIT_SEEDS_OVERLAP", "declared seed ranges overlap")
    return document, payload


def _sample_paths(sample: Mapping[str, Any]) -> dict[str, PurePosixPath]:
    return {
        name: _relative_path(sample.get(name), field=name) for name in ("image", "label", "truth")
    }


def _validate_sample_shape(
    sample: object, index: int, splits: tuple[str, ...] | None = None
) -> dict[str, Any]:
    if not isinstance(sample, Mapping) or set(sample) != _SAMPLE_FIELDS:
        raise _fail("MANIFEST_INVALID", f"sample {index} has unsupported or missing fields")
    normalized = dict(sample)
    split = normalized["split"]
    if split not in (_LEGACY_SPLITS if splits is None else splits):
        raise _fail("MANIFEST_INVALID", f"sample {index} has invalid split")
    _integer(normalized["seed"], field=f"samples[{index}].seed")
    configured = _integer(
        normalized["configured_cup_count"],
        field=f"samples[{index}].configured_cup_count",
    )
    visible = _integer(
        normalized["visible_instance_count"],
        field=f"samples[{index}].visible_instance_count",
    )
    if visible > configured:
        raise _fail("MANIFEST_INVALID", f"sample {index} has visible > configured cups")
    if not isinstance(normalized["scenario"], str) or not normalized["scenario"]:
        raise _fail("MANIFEST_INVALID", f"sample {index} scenario must be non-empty")
    _sample_paths(normalized)
    return normalized


def _validate_manifest_members(
    manifest: Mapping[str, Any],
    samples: list[dict[str, Any]],
    splits: tuple[str, ...] | None = None,
) -> None:
    if splits is None:
        splits = (
            _TRAIN_VAL_SPLITS
            if manifest.get("dataset_contract") == _TRAIN_VAL_DATASET_CONTRACT
            else _LEGACY_SPLITS
        )
    actual_counts = Counter(sample["split"] for sample in samples)
    expected_counts = manifest["split_counts"]
    if any(actual_counts[split] != expected_counts[split] for split in splits):
        raise _fail("MANIFEST_INVALID", "split_counts do not match samples")
    if manifest["schema_version"] == 2:
        for split in splits:
            actual_scenarios = Counter(
                sample["scenario"] for sample in samples if sample["split"] == split
            )
            if dict(actual_scenarios) != dict(manifest["scenario_quotas"][split]):
                raise _fail(
                    "MANIFEST_INVALID",
                    f"scenario_quotas.{split} do not match samples",
                )

    seed_owners: dict[int, str] = {}
    for sample in samples:
        seed = sample["seed"]
        owner = seed_owners.get(seed)
        if owner is not None:
            raise _fail(
                "SPLIT_SEEDS_OVERLAP",
                f"seed {seed} appears in both {owner} and {sample['split']}",
            )
        seed_owners[seed] = sample["split"]
    if splits == _TRAIN_VAL_SPLITS:
        for sample in samples:
            declared_range = manifest["seed_ranges"][sample["split"]]
            if not declared_range[0] <= sample["seed"] <= declared_range[1]:
                raise _fail("MANIFEST_INVALID", "sample seed is outside its declared range")

    seen_by_split: dict[str, set[str]] = {split: set() for split in splits}
    all_members: set[str] = set()
    for sample in samples:
        for relative in _sample_paths(sample).values():
            member = relative.as_posix()
            if member in all_members:
                raise _fail("SPLIT_MEMBERS_OVERLAP", member)
            all_members.add(member)
            seen_by_split[sample["split"]].add(member)
    for left_index, left in enumerate(splits):
        for right in splits[left_index + 1 :]:
            overlap = seen_by_split[left] & seen_by_split[right]
            if overlap:
                raise _fail("SPLIT_MEMBERS_OVERLAP", sorted(overlap)[0])

    for index, sample in enumerate(samples):
        paths = _sample_paths(sample)
        for kind, prefix in (
            ("image", "images"),
            ("label", "labels"),
            ("truth", "truth"),
        ):
            expected_parent = PurePosixPath(prefix) / sample["split"]
            if paths[kind].parent != expected_parent:
                raise _fail(
                    "MANIFEST_INVALID",
                    f"sample {index} {kind} is outside its split directory",
                )

    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list) or not all(isinstance(item, str) for item in artifacts):
        raise _fail("MANIFEST_INVALID", "artifacts must be a string list")
    expected_artifacts = {"dataset.yaml", *all_members}
    if len(artifacts) != len(set(artifacts)) or set(artifacts) != expected_artifacts:
        raise _fail("MANIFEST_INVALID", "artifacts do not exactly match sample members")


def _validate_official_train_val_version(manifest: Mapping[str, Any]) -> None:
    if manifest.get("dataset_contract") != _TRAIN_VAL_DATASET_CONTRACT:
        raise _fail("MANIFEST_INVALID", "official dataset contract discriminator is invalid")
    if manifest.get("member_splits") != list(_TRAIN_VAL_SPLITS):
        raise _fail("MANIFEST_INVALID", "official dataset member splits are invalid")
    if manifest.get("split_counts") != _TRAIN_VAL_SPLIT_COUNTS:
        raise _fail("MANIFEST_INVALID", "official dataset split counts are invalid")
    if manifest.get("seed_starts") != _TRAIN_VAL_SEED_STARTS:
        raise _fail("MANIFEST_INVALID", "official dataset seed starts are invalid")
    if manifest.get("seed_ranges") != _TRAIN_VAL_SEED_RANGES:
        raise _fail("MANIFEST_INVALID", "official dataset seed ranges are invalid")
    quotas = manifest.get("scenario_quotas")
    if not isinstance(quotas, Mapping) or set(quotas) != set(_TRAIN_VAL_SPLITS):
        raise _fail("MANIFEST_INVALID", "official dataset scenario quotas are invalid")
    if any(
        not isinstance(quotas[split], Mapping)
        or dict(quotas[split]) != _TRAIN_VAL_SCENARIO_QUOTAS[split]
        for split in _TRAIN_VAL_SPLITS
    ):
        raise _fail("MANIFEST_INVALID", "official dataset scenario quotas are invalid")
    samples = manifest.get("samples")
    if not isinstance(samples, list) or len(samples) != sum(_TRAIN_VAL_SPLIT_COUNTS.values()):
        raise _fail("MANIFEST_INVALID", "official dataset sample population is invalid")
    position = 0
    for split in _TRAIN_VAL_SPLITS:
        start = _TRAIN_VAL_SEED_STARTS[split]
        for offset in range(_TRAIN_VAL_SPLIT_COUNTS[split]):
            sample = samples[position]
            scenario = _TRAIN_VAL_SCENARIOS[offset % len(_TRAIN_VAL_SCENARIOS)]
            if not isinstance(sample, Mapping) or (
                sample.get("split") != split
                or sample.get("seed") != start + offset
                or sample.get("scenario") != scenario
                or sample.get("configured_cup_count") != len(_SCENARIO_CUPS[scenario])
            ):
                raise _fail("MANIFEST_INVALID", "official dataset sample schedule is invalid")
            position += 1


def _validate_train_val_source_tree(
    source_root: Path,
    manifest: Mapping[str, Any],
    samples: list[dict[str, Any]],
) -> None:
    expected_files = {PurePosixPath("dataset.yaml"), PurePosixPath("dataset-manifest.json")}
    for index, sample in enumerate(samples):
        split = sample["split"]
        seed = sample["seed"]
        expected_paths = {
            "image": PurePosixPath("images") / split / f"{seed:09d}.png",
            "label": PurePosixPath("labels") / split / f"{seed:09d}.txt",
            "truth": PurePosixPath("truth") / split / f"{seed:09d}.json",
        }
        if _sample_paths(sample) != expected_paths:
            raise _fail("MANIFEST_INVALID", f"sample {index} paths are not canonical")
        expected_files.update(expected_paths.values())

    expected_directories: set[PurePosixPath] = set()
    for relative in expected_files:
        parent = relative.parent
        while parent.parts:
            expected_directories.add(parent)
            parent = parent.parent

    actual_files: set[PurePosixPath] = set()
    actual_directories: set[PurePosixPath] = set()

    def visit(directory: Path, relative: PurePosixPath) -> None:
        try:
            with os.scandir(directory) as iterator:
                entries = list(iterator)
        except OSError as error:
            raise _fail("SOURCE_PATH_INVALID", f"cannot inventory {relative}: {error}") from error
        for entry in entries:
            child_relative = relative / entry.name
            try:
                if entry.is_symlink():
                    raise _fail("SOURCE_PATH_INVALID", f"source member is a symlink: {child_relative}")
                if entry.is_dir(follow_symlinks=False):
                    if child_relative not in expected_directories:
                        raise _fail(
                            "MANIFEST_INVALID",
                            f"unexpected source directory: {child_relative}",
                        )
                    actual_directories.add(child_relative)
                    visit(Path(entry.path), child_relative)
                elif entry.is_file(follow_symlinks=False):
                    actual_files.add(child_relative)
                else:
                    raise _fail(
                        "SOURCE_PATH_INVALID", f"source member has unsupported type: {child_relative}"
                    )
            except OSError as error:
                raise _fail(
                    "SOURCE_PATH_INVALID", f"cannot inspect source member {child_relative}: {error}"
                ) from error

    visit(source_root, PurePosixPath())
    if actual_files != expected_files or actual_directories != expected_directories:
        raise _fail("MANIFEST_INVALID", "source tree does not exactly match canonical members")


def _label_polygons(payload: bytes, *, member: str) -> list[list[tuple[float, float]]]:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as error:
        raise _fail("LABEL_INVALID", f"{member}: not UTF-8") from error
    polygons: list[list[tuple[float, float]]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        fields = line.split()
        if fields[0] != "0":
            raise _fail("CLASS_INVALID", f"{member}:{line_number}: only class 0 is allowed")
        coordinates = fields[1:]
        if len(coordinates) < 6 or len(coordinates) % 2:
            raise _fail("POLYGON_INVALID", f"{member}:{line_number}: invalid coordinate count")
        try:
            values = [float(value) for value in coordinates]
        except ValueError as error:
            raise _fail(
                "POLYGON_INVALID", f"{member}:{line_number}: non-numeric coordinate"
            ) from error
        polygons.append(list(zip(values[::2], values[1::2], strict=True)))
    return polygons


def _ordered_geometry_scope(scenario: object) -> list[tuple[str, str]]:
    try:
        cups = _SCENARIO_CUPS[scenario]
    except (KeyError, TypeError) as error:
        raise _fail("GEOMETRY_RECEIPT_INVALID", "scenario has no task geometry scope") from error
    dynamic = [*cups, "orange_bottle"]
    result = [
        (dynamic[left], dynamic[right])
        for left in range(len(dynamic))
        for right in range(left + 1, len(dynamic))
    ]
    result.extend(
        (body, static)
        for body in dynamic
        for static in ("table", "neutral_block", "base_pedestal")
    )
    return result


def _validate_geometry_receipt(truth: Mapping[str, Any], *, member: str, scenario: object) -> None:
    receipt = truth.get("scene_geometry")
    if not isinstance(receipt, Mapping) or set(receipt) != {
        "policy",
        "accepted",
        "pairs",
        "state_sha256",
    }:
        raise _fail("GEOMETRY_RECEIPT_INVALID", f"{member}: receipt keys are invalid")
    if receipt.get("policy") != _SCENE_GEOMETRY_POLICY or receipt.get("accepted") is not True:
        raise _fail("GEOMETRY_RECEIPT_INVALID", f"{member}: policy or acceptance is invalid")
    state_sha256 = receipt.get("state_sha256")
    if not isinstance(state_sha256, str) or _SHA256.fullmatch(state_sha256) is None:
        raise _fail("GEOMETRY_RECEIPT_INVALID", f"{member}: state SHA256 is invalid")
    pairs = receipt.get("pairs")
    expected = _ordered_geometry_scope(scenario)
    if not isinstance(pairs, list) or len(pairs) != len(expected):
        raise _fail("GEOMETRY_RECEIPT_INVALID", f"{member}: pair scope is incomplete")
    for index, (pair, body_names) in enumerate(zip(pairs, expected, strict=True)):
        if not isinstance(pair, Mapping) or set(pair) != {
            "body_names",
            "geom_names",
            "primitive_pair_count",
            "signed_distance_m",
        }:
            raise _fail("GEOMETRY_RECEIPT_INVALID", f"{member}: pair {index} keys are invalid")
        if pair.get("body_names") != list(body_names):
            raise _fail("GEOMETRY_RECEIPT_INVALID", f"{member}: pair {index} bodies are invalid")
        geom_names = pair.get("geom_names")
        if (
            not isinstance(geom_names, list)
            or len(geom_names) != 2
            or any(type(name) is not str for name in geom_names)
            or any(
                geom_name not in _VISUAL_GEOMS[body_name]
                for body_name, geom_name in zip(body_names, geom_names, strict=True)
            )
        ):
            raise _fail("GEOMETRY_RECEIPT_INVALID", f"{member}: pair {index} geoms are invalid")
        primitive_count = pair.get("primitive_pair_count")
        if type(primitive_count) is not int or primitive_count <= 0:
            raise _fail(
                "GEOMETRY_RECEIPT_INVALID",
                f"{member}: pair {index} primitive count is invalid",
            )
        distance = pair.get("signed_distance_m")
        distance_is_finite = False
        if not isinstance(distance, bool) and isinstance(distance, (int, float)):
            try:
                distance_is_finite = math.isfinite(distance)
            except OverflowError:
                pass
        if not distance_is_finite or distance < -1e-9:
            raise _fail(
                "GEOMETRY_RECEIPT_INVALID", f"{member}: pair {index} distance is invalid"
            )


def _validate_train_val_scenario_truth(
    sample: Mapping[str, Any], instances: list[Any], *, member: str
) -> None:
    scenario = sample["scenario"]
    try:
        allowed_bodies = _SCENARIO_CUPS[scenario]
    except (KeyError, TypeError) as error:
        raise _fail("TRUTH_MISMATCH", f"{member}: scenario is invalid") from error
    if sample["configured_cup_count"] != len(allowed_bodies):
        raise _fail("TRUTH_MISMATCH", f"{member}: configured cups differ from scenario")
    body_names = [
        instance.get("body_name") if isinstance(instance, Mapping) else None
        for instance in instances
    ]
    if (
        any(type(body_name) is not str for body_name in body_names)
        or len(body_names) != len(set(body_names))
        or not set(body_names) <= set(allowed_bodies)
    ):
        raise _fail("TRUTH_MISMATCH", f"{member}: target bodies differ from scenario")
    if scenario in {"small_far_cup", "partially_occluded_cup"} and not body_names:
        raise _fail("TRUTH_MISMATCH", f"{member}: required scenario target is absent")


def _truth_instances(
    payload: bytes,
    *,
    member: str,
    sample: Mapping[str, Any],
    image_width: int,
    image_height: int,
    schema_version: int,
    scene_geometry: Mapping[str, Any] | None,
    require_complete_visible_truth: bool = False,
    require_geometry_receipt: bool = False,
) -> list[dict[str, Any]]:
    truth = _json_mapping(payload, member=member)
    for field in (
        "seed",
        "split",
        "scenario",
        "configured_cup_count",
        "visible_instance_count",
    ):
        if truth.get(field) != sample[field]:
            raise _fail("TRUTH_MISMATCH", f"{member}: {field} differs from manifest")
    if require_geometry_receipt:
        _validate_geometry_receipt(truth, member=member, scenario=sample["scenario"])
    instances = truth.get("instances")
    if not isinstance(instances, list) or len(instances) != sample["visible_instance_count"]:
        raise _fail("TRUTH_MISMATCH", f"{member}: instances differ from visible count")
    if require_complete_visible_truth:
        _validate_train_val_scenario_truth(sample, instances, member=member)
    normalized: list[dict[str, Any]] = []
    for index, instance in enumerate(instances):
        if not isinstance(instance, Mapping) or instance.get("body_name") not in _CUP_BODY_NAMES:
            raise _fail(
                "CLASS_INVALID",
                f"{member}: instance {index} is not a registered cup body",
            )
        visible_pixels = instance.get("visible_pixel_count")
        if (
            isinstance(visible_pixels, bool)
            or not isinstance(visible_pixels, int)
            or visible_pixels <= 0
        ):
            raise _fail("TRUTH_MISMATCH", f"{member}: instance {index} visible pixels invalid")
        truth_box = polygon_to_box(instance.get("polygon_xy", ()), image_width, image_height)
        occlusion = None
        if schema_version == 2:
            measured = instance.get("occlusion_measured")
            state = instance.get("occlusion_state")
            if not isinstance(measured, bool) or state not in {
                "unmeasured",
                "none",
                "partial",
            }:
                raise _fail(
                    "OCCLUSION_TRUTH_INVALID",
                    f"{member}: instance {index} measurement state invalid",
                )
            visible_fields = {
                "mask_shape_hw",
                "visible_mask_rle_counts",
                "visible_mask_sha256",
            }
            present_visible_fields = visible_fields.intersection(instance)
            visible_mask = None
            if require_complete_visible_truth and present_visible_fields != visible_fields:
                raise _fail(
                    "VISIBLE_TRUTH_INVALID",
                    f"{member}: instance {index} visible-mask fields are incomplete",
                )
            if present_visible_fields:
                if present_visible_fields != visible_fields:
                    raise _fail(
                        "VISIBLE_TRUTH_INVALID",
                        f"{member}: instance {index} visible-mask fields are incomplete",
                    )
                try:
                    visible_mask = decode_binary_mask_rle(
                        instance.get("visible_mask_rle_counts"),
                        instance.get("mask_shape_hw"),
                    )
                    visible_box = binary_mask_to_box(
                        visible_mask,
                        image_width,
                        image_height,
                    )
                except (GroundingDinoDatasetError, ValueError) as error:
                    raise _fail(
                        "VISIBLE_TRUTH_INVALID",
                        f"{member}: instance {index}: {error}",
                    ) from error
                visible_hash = _sha256_bytes(visible_mask.astype("uint8").tobytes(order="C"))
                if (
                    instance.get("visible_mask_sha256") != visible_hash
                    or int(visible_mask.sum()) != visible_pixels
                    or not _boxes_match(truth_box, visible_box)
                ):
                    raise _fail(
                        "VISIBLE_TRUTH_INVALID",
                        f"{member}: instance {index} mask, count, hash, or box differs",
                    )
                truth_box = visible_box
            if measured:
                if visible_mask is None:
                    raise _fail(
                        "OCCLUSION_TRUTH_INVALID",
                        f"{member}: instance {index} visible mask is absent",
                    )
                if require_complete_visible_truth:
                    partial_fields = {
                        "paired_reference_mask_rle_counts",
                        "paired_reference_mask_sha256",
                        "paired_reference_pixel_count",
                        "amodal_mask_rle_counts",
                        "amodal_mask_sha256",
                        "amodal_pixel_count",
                        "occluded_pixel_count",
                        "visible_fraction",
                        "occluder_body_name",
                        "occlusion_reference",
                    }
                    if not partial_fields <= instance.keys():
                        raise _fail(
                            "OCCLUSION_TRUTH_INVALID",
                            f"{member}: instance {index} partial truth is incomplete",
                        )
                try:
                    paired_reference_mask = decode_binary_mask_rle(
                        instance.get("paired_reference_mask_rle_counts"),
                        instance.get("mask_shape_hw"),
                    )
                    amodal_mask = decode_binary_mask_rle(
                        instance.get("amodal_mask_rle_counts"),
                        instance.get("mask_shape_hw"),
                    )
                except ValueError as error:
                    raise _fail(
                        "OCCLUSION_TRUTH_INVALID",
                        f"{member}: instance {index}: {error}",
                    ) from error
                paired_reference_hash = _sha256_bytes(
                    paired_reference_mask.astype("uint8").tobytes(order="C")
                )
                amodal_hash = _sha256_bytes(amodal_mask.astype("uint8").tobytes(order="C"))
                paired_reference_pixels = int(paired_reference_mask.sum())
                amodal_pixels = int(amodal_mask.sum())
                occluded_pixels = amodal_pixels - visible_pixels
                fraction = visible_pixels / amodal_pixels if amodal_pixels else -1.0
                if (
                    instance.get("paired_reference_mask_sha256") != paired_reference_hash
                    or instance.get("amodal_mask_sha256") != amodal_hash
                    or instance.get("paired_reference_pixel_count") != paired_reference_pixels
                    or instance.get("amodal_pixel_count") != amodal_pixels
                    or instance.get("occluded_pixel_count") != occluded_pixels
                    or not isinstance(instance.get("visible_fraction"), (int, float))
                    or not math.isclose(
                        float(instance["visible_fraction"]),
                        fraction,
                        rel_tol=0.0,
                        abs_tol=1e-12,
                    )
                    or not bool((amodal_mask == (visible_mask | paired_reference_mask)).all())
                    or (
                        require_complete_visible_truth
                        and (
                            type(instance.get("paired_reference_pixel_count")) is not int
                            or type(instance.get("amodal_pixel_count")) is not int
                            or type(instance.get("occluded_pixel_count")) is not int
                            or isinstance(instance.get("visible_fraction"), bool)
                            or not bool((visible_mask <= amodal_mask).all())
                            or not bool((amodal_mask & ~visible_mask).any())
                        )
                    )
                ):
                    raise _fail(
                        "OCCLUSION_TRUTH_INVALID",
                        f"{member}: instance {index} masks, counts, or hashes differ",
                    )
                expected_state = "partial" if occluded_pixels else "none"
                if state != expected_state:
                    raise _fail(
                        "OCCLUSION_TRUTH_INVALID",
                        f"{member}: instance {index} state differs from masks",
                    )
                occluder = instance.get("occluder_body_name")
                reference = instance.get("occlusion_reference")
                if not isinstance(occluder, str) or not isinstance(reference, str):
                    raise _fail(
                        "OCCLUSION_TRUTH_INVALID",
                        f"{member}: instance {index} occluder provenance is absent",
                    )
                occlusion = {
                    "amodal_pixel_count": amodal_pixels,
                    "occluded_pixel_count": occluded_pixels,
                    "occluder_body_name": occluder,
                    "state": state,
                    "visible_fraction": fraction,
                }
            elif state != "unmeasured":
                raise _fail(
                    "OCCLUSION_TRUTH_INVALID",
                    f"{member}: instance {index} unmeasured state is inconsistent",
                )
            if sample["scenario"] == "partially_occluded_cup":
                assert scene_geometry is not None
                fraction_range = scene_geometry.get("partial_visible_fraction")
                minimum_pixels = scene_geometry.get("visible_pixel_count_minimum")
                if (
                    occlusion is None
                    or occlusion["state"] != "partial"
                    or occlusion["occluder_body_name"] != "orange_bottle"
                    or instance.get("occlusion_reference")
                    != "visible_union_paired_segmentation_with_declared_occluder_hidden"
                    or not isinstance(fraction_range, list)
                    or len(fraction_range) != 2
                    or not fraction_range[0] <= fraction <= fraction_range[1]
                    or not isinstance(minimum_pixels, int)
                    or visible_pixels < minimum_pixels
                ):
                    raise _fail(
                        "OCCLUSION_TRUTH_INVALID",
                        f"{member}: instance {index} violates partial-occlusion contract",
                    )
        if schema_version == 2 and sample["scenario"] == "small_far_cup":
            assert scene_geometry is not None
            left, top, right, bottom = truth_box.absolute_xyxy
            area = (right - left) * (bottom - top)
            threshold = scene_geometry.get("small_bbox_area_max_exclusive")
            minimum_pixels = scene_geometry.get("visible_pixel_count_minimum")
            if (
                not isinstance(threshold, (int, float))
                or not 0.0 < area < float(threshold)
                or not isinstance(minimum_pixels, int)
                or visible_pixels < minimum_pixels
            ):
                raise _fail(
                    "SMALL_TRUTH_INVALID",
                    f"{member}: instance {index} violates small-target contract",
                )
        normalized.append(
            {
                "visible_pixel_count": visible_pixels,
                "box": truth_box,
                "occlusion": occlusion,
            }
        )
    return normalized


def _box_document(
    box: BoundingBox, *, image_width: int, image_height: int
) -> dict[str, Any]:
    """Export trainer coordinates, not the polygon's pixel-center normalization."""
    width = _positive_dimension(image_width, "image_width")
    height = _positive_dimension(image_height, "image_height")
    left, top, right, bottom = box.absolute_xyxy
    return {
        "absolute_xyxy": list(box.absolute_xyxy),
        "class_name": "cup",
        "normalized_xyxy": [left / width, top / height, right / width, bottom / height],
        "text": "cup.",
    }


def _boxes_match(left: BoundingBox, right: BoundingBox) -> bool:
    return all(
        math.isclose(a, b, rel_tol=0.0, abs_tol=1e-6)
        for a, b in zip(left.normalized_xyxy, right.normalized_xyxy, strict=True)
    )


def _profile(
    samples: list[dict[str, Any]],
    inventories: Mapping[str, list[dict[str, Any]]],
    *,
    schema_version: int,
    include_test_seal: bool = True,
) -> dict[str, Any]:
    profile: dict[str, Any] = {"schema_version": 1}
    samples_by_split = {
        split: [sample for sample in samples if sample["split"] == split]
        for split in ("train", "val")
    }
    for split in ("train", "val"):
        split_samples = samples_by_split[split]
        records = inventories[split]
        area_counts: Counter[str] = Counter()
        instance_count = 0
        occlusion_counts: Counter[str] = Counter()
        for record in records:
            for box in record["boxes"]:
                left, top, right, bottom = box["absolute_xyxy"]
                area = (right - left) * (bottom - top)
                bucket = "small" if area < 32**2 else "medium" if area < 96**2 else "large"
                area_counts[bucket] += 1
                instance_count += 1
                occlusion = box.get("occlusion")
                if occlusion is None:
                    occlusion_counts["unmeasured"] += 1
                else:
                    occlusion_counts[f"measured_{occlusion['state']}"] += 1
        configured_count = sum(sample["configured_cup_count"] for sample in split_samples)
        visible_count = sum(sample["visible_instance_count"] for sample in split_samples)
        profile[split] = {
            "area_bucket_counts": {
                bucket: area_counts[bucket] for bucket in ("small", "medium", "large")
            },
            "background": "unknown",
            "configured_instance_count": configured_count,
            "fully_hidden_instance_count": configured_count - visible_count,
            "image_count": len(split_samples),
            "instance_count": instance_count,
            "lighting": "unknown",
            "partial_occlusion": (
                "unknown"
                if schema_version == 1
                else {
                    "measured_none": occlusion_counts["measured_none"],
                    "measured_partial": occlusion_counts["measured_partial"],
                    "unmeasured": occlusion_counts["unmeasured"],
                }
            ),
            "scenario_counts": dict(
                sorted(Counter(sample["scenario"] for sample in split_samples).items())
            ),
            "visible_cup_count_per_image": dict(
                sorted(
                    Counter(
                        str(sample["visible_instance_count"]) for sample in split_samples
                    ).items()
                )
            ),
        }
    if include_test_seal:
        profile["test"] = {
            "sample_count": sum(sample["split"] == "test" for sample in samples),
            "sealed": True,
        }
    return profile


def _write_file(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        try:
            os.close(descriptor)
        except OSError:
            pass
        raise


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def convert_dataset(
    source_root: Path,
    output_root: Path,
    *,
    source_archive_sha256: str,
    converter_commit: str,
) -> dict[str, str]:
    """Validate and convert train/val while retaining a cryptographic test seal."""

    source_root = Path(source_root)
    output_root = Path(output_root)
    if not source_root.is_absolute() or not output_root.is_absolute():
        raise _fail("PATH_NOT_ABSOLUTE", "source and output roots must be absolute")
    if output_root.exists() or output_root.is_symlink():
        raise _fail("OUTPUT_ROOT_ALREADY_EXISTS", str(output_root))
    if source_root.is_symlink():
        raise _fail("SOURCE_PATH_INVALID", "source root must not be a symlink")
    try:
        source_root = source_root.resolve(strict=True)
    except OSError as error:
        raise _fail("SOURCE_ROOT_INVALID", str(error)) from error
    if not source_root.is_dir():
        raise _fail("SOURCE_ROOT_INVALID", "source root is not a directory")
    if _SHA256.fullmatch(source_archive_sha256) is None:
        raise _fail("PROVENANCE_INVALID", "source archive SHA256 is invalid")
    if _COMMIT.fullmatch(converter_commit) is None:
        raise _fail("PROVENANCE_INVALID", "converter commit is invalid")

    manifest, manifest_payload = _manifest(source_root)
    splits = (
        _TRAIN_VAL_SPLITS
        if manifest.get("dataset_contract") == _TRAIN_VAL_DATASET_CONTRACT
        else _LEGACY_SPLITS
    )
    if splits == _TRAIN_VAL_SPLITS:
        _validate_official_train_val_version(manifest)
    _dataset_contract(source_root, splits)
    samples = [
        _validate_sample_shape(sample, index, splits)
        for index, sample in enumerate(manifest["samples"])
    ]
    _validate_manifest_members(manifest, samples, splits)
    if splits == _TRAIN_VAL_SPLITS:
        _validate_train_val_source_tree(source_root, manifest, samples)
    width = manifest["image_width"]
    height = manifest["image_height"]
    source_manifest_sha256 = _sha256_bytes(manifest_payload)
    common = {
        "class_name": "cup",
        "converter_commit": converter_commit,
        "image_height": height,
        "image_width": width,
        "prompt": "cup.",
        "schema_version": 1,
        "source_archive_sha256": source_archive_sha256,
        "source_generator_commit": manifest["generator_commit"],
        "source_manifest_sha256": source_manifest_sha256,
        "source_mjcf_sha256": manifest["mjcf_sha256"],
    }
    inventories: dict[str, list[dict[str, Any]]] = {"train": [], "val": []}
    sealed_samples: list[dict[str, Any]] = []
    for sample in sorted(
        manifest["samples"], key=lambda item: (splits.index(item["split"]), item["seed"])
    ):
        paths = _sample_paths(sample)
        payloads = {name: _read_bytes(source_root, path) for name, path in paths.items()}
        hashes = {f"{name}_sha256": _sha256_bytes(payload) for name, payload in payloads.items()}
        base_record = {
            "image_relpath": paths["image"].as_posix(),
            "label_relpath": paths["label"].as_posix(),
            "truth_relpath": paths["truth"].as_posix(),
            **hashes,
        }
        split = sample["split"]
        if split == "test":
            sealed_samples.append(base_record)
            continue

        polygons = _label_polygons(payloads["label"], member=paths["label"].as_posix())
        truth_instances = _truth_instances(
            payloads["truth"],
            member=paths["truth"].as_posix(),
            sample=sample,
            image_width=width,
            image_height=height,
            schema_version=manifest["schema_version"],
            scene_geometry=manifest.get("scene_geometry"),
            require_complete_visible_truth=splits == _TRAIN_VAL_SPLITS,
            require_geometry_receipt=splits == _TRAIN_VAL_SPLITS,
        )
        if len(polygons) != len(truth_instances):
            raise _fail("TRUTH_MISMATCH", f"{paths['label']}: label/truth instance count differs")
        boxes: list[dict[str, Any]] = []
        for polygon, truth_instance in zip(polygons, truth_instances, strict=True):
            label_box = polygon_to_box(polygon, width, height)
            if not _boxes_match(label_box, truth_instance["box"]):
                raise _fail("TRUTH_MISMATCH", f"{paths['label']}: label/truth box differs")
            box_document = _box_document(
                truth_instance["box"], image_width=width, image_height=height
            )
            box_document["visible_pixel_count"] = truth_instance["visible_pixel_count"]
            if manifest["schema_version"] == 2:
                box_document["occlusion"] = truth_instance["occlusion"]
            boxes.append(box_document)
        inventories[split].append(
            {
                **base_record,
                "boxes": boxes,
                "configured_cup_count": sample["configured_cup_count"],
                "scenario": sample["scenario"],
                "seed": sample["seed"],
                "visible_instance_count": sample["visible_instance_count"],
            }
        )

    documents: dict[str, dict[str, Any]] = {}
    for split in ("train", "val"):
        documents[f"{split}/inventory.json"] = {
            **common,
            "sample_count": len(inventories[split]),
            "samples": inventories[split],
            "split": split,
        }
    if splits == _LEGACY_SPLITS:
        documents["test-sealed-members.json"] = {
            "converter_commit": converter_commit,
            "sample_count": len(sealed_samples),
            "samples": sealed_samples,
            "schema_version": 1,
            "sealed": True,
            "source_archive_sha256": source_archive_sha256,
            "source_manifest_sha256": source_manifest_sha256,
            "split": "test",
        }
    documents["dataset-profile.json"] = _profile(
        samples,
        inventories,
        schema_version=manifest["schema_version"],
        include_test_seal=splits == _LEGACY_SPLITS,
    )
    payloads = {relative: _canonical_json(document) for relative, document in documents.items()}
    output_root.mkdir(parents=True, exist_ok=False)
    for relative in sorted(payloads):
        _write_file(output_root / relative, payloads[relative])
    for directory in sorted(
        {output_root, *(path.parent for path in output_root.rglob("*"))},
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if directory.is_dir():
            _fsync_directory(directory)
    return {
        relative.replace("/", "_").replace(".json", "_sha256"): _sha256_bytes(payload)
        for relative, payload in sorted(payloads.items())
    }
