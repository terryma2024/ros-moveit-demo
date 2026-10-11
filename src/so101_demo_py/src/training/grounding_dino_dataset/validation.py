"""Manifest, sample, geometry and truth validation of a Grounding DINO dataset."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

from so101_demo.adapters.perception.mujoco_dataset.render import decode_binary_mask_rle
from so101_demo.training.grounding_dino_dataset.contracts import (
    _COMMIT,
    _CUP_BODY_NAMES,
    _LEGACY_SPLITS,
    _SAMPLE_FIELDS,
    _SCENARIO_CUPS,
    _SCENE_GEOMETRY_POLICY,
    _SHA256,
    _TEST_DATASET_CONTRACT,
    _TEST_SCENARIO_QUOTAS,
    _TEST_SEED_RANGES,
    _TEST_SEED_STARTS,
    _TEST_SPLIT_COUNTS,
    _TEST_SPLITS,
    _TRAIN_VAL_DATASET_CONTRACT,
    _TRAIN_VAL_SCENARIO_QUOTAS,
    _TRAIN_VAL_SCENARIOS,
    _TRAIN_VAL_SCENE_GEOMETRY,
    _TRAIN_VAL_SEED_RANGES,
    _TRAIN_VAL_SEED_STARTS,
    _TRAIN_VAL_SPLIT_COUNTS,
    _TRAIN_VAL_SPLITS,
    _TRAIN_VAL_TRUTH_CONTRACT,
    _VISUAL_GEOMS,
    BoundingBox,
    GroundingDinoDatasetError,
    _fail,
    _positive_dimension,
    binary_mask_to_box,
    polygon_to_box,
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
        **{split: f"images/{split}" for split in splits},
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
    elif dataset_contract == _TEST_DATASET_CONTRACT:
        splits = _TEST_SPLITS
        if document.get("member_splits") != list(splits):
            raise _fail("MANIFEST_INVALID", "member_splits must be exactly test")
    else:
        raise _fail("MANIFEST_INVALID", "unknown dataset_contract")
    schema_version = document.get("schema_version")
    if splits != _LEGACY_SPLITS:
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
            minimum=1 if splits != _LEGACY_SPLITS else 0,
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
    if splits != _LEGACY_SPLITS:
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
        for left_index, left in enumerate(occupied):
            for right in occupied[left_index + 1 :]:
                if left[1] >= right[0] and right[1] >= left[0]:
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
            else _TEST_SPLITS
            if manifest.get("dataset_contract") == _TEST_DATASET_CONTRACT
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
    if splits != _LEGACY_SPLITS:
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


def _validate_official_test_version(manifest: Mapping[str, Any]) -> None:
    if manifest.get("dataset_contract") != _TEST_DATASET_CONTRACT:
        raise _fail("MANIFEST_INVALID", "official test dataset discriminator is invalid")
    if manifest.get("member_splits") != list(_TEST_SPLITS):
        raise _fail("MANIFEST_INVALID", "official test dataset member splits are invalid")
    if manifest.get("split_counts") != _TEST_SPLIT_COUNTS:
        raise _fail("MANIFEST_INVALID", "official test dataset split counts are invalid")
    if manifest.get("seed_starts") != _TEST_SEED_STARTS:
        raise _fail("MANIFEST_INVALID", "official test dataset seed starts are invalid")
    if manifest.get("seed_ranges") != _TEST_SEED_RANGES:
        raise _fail("MANIFEST_INVALID", "official test dataset seed ranges are invalid")
    quotas = manifest.get("scenario_quotas")
    if (
        not isinstance(quotas, Mapping)
        or set(quotas) != set(_TEST_SPLITS)
        or not isinstance(quotas["test"], Mapping)
        or dict(quotas["test"]) != _TEST_SCENARIO_QUOTAS["test"]
    ):
        raise _fail("MANIFEST_INVALID", "official test dataset scenario quotas are invalid")
    samples = manifest.get("samples")
    if not isinstance(samples, list) or len(samples) != _TEST_SPLIT_COUNTS["test"]:
        raise _fail("MANIFEST_INVALID", "official test dataset sample population is invalid")
    for offset, sample in enumerate(samples):
        scenario = _TRAIN_VAL_SCENARIOS[offset % len(_TRAIN_VAL_SCENARIOS)]
        if not isinstance(sample, Mapping) or (
            sample.get("split") != "test"
            or sample.get("seed") != _TEST_SEED_STARTS["test"] + offset
            or sample.get("scenario") != scenario
            or sample.get("configured_cup_count") != len(_SCENARIO_CUPS[scenario])
        ):
            raise _fail("MANIFEST_INVALID", "official test dataset sample schedule is invalid")


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
