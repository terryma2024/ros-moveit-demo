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
_SPLITS = ("train", "val", "test")
_CUP_BODY_NAMES = frozenset({"plastic_cup", "plastic_cup_b"})
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


def _dataset_contract(source_root: Path) -> None:
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
        "test": "images/test",
        "names": {0: "plastic_cup"},
    }
    if dict(document) != expected:
        raise _fail("DATASET_YAML_INVALID", "dataset contract is not the fixed cup dataset")


def _manifest(source_root: Path) -> tuple[dict[str, Any], bytes]:
    relative = PurePosixPath("dataset-manifest.json")
    payload = _read_bytes(source_root, relative)
    document = _json_mapping(payload, member=relative.as_posix())
    schema_version = document.get("schema_version")
    if schema_version not in {1, 2}:
        raise _fail("MANIFEST_INVALID", "schema_version must be 1 or 2")
    samples = document.get("samples")
    if not isinstance(samples, list):
        raise _fail("MANIFEST_INVALID", "samples must be a list")
    sample_count = _integer(document.get("sample_count"), field="sample_count")
    if sample_count != len(samples):
        raise _fail("MANIFEST_INVALID", "sample_count does not match samples")
    split_counts = document.get("split_counts")
    if not isinstance(split_counts, Mapping) or set(split_counts) != set(_SPLITS):
        raise _fail("MANIFEST_INVALID", "split_counts must contain train, val, and test")
    for split in _SPLITS:
        _integer(split_counts[split], field=f"split_counts.{split}")
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
        if not isinstance(quotas, Mapping) or set(quotas) != set(_SPLITS):
            raise _fail("MANIFEST_INVALID", "scenario_quotas must contain all splits")
        for split in _SPLITS:
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
    return document, payload


def _sample_paths(sample: Mapping[str, Any]) -> dict[str, PurePosixPath]:
    return {
        name: _relative_path(sample.get(name), field=name) for name in ("image", "label", "truth")
    }


def _validate_sample_shape(sample: object, index: int) -> dict[str, Any]:
    if not isinstance(sample, Mapping) or set(sample) != _SAMPLE_FIELDS:
        raise _fail("MANIFEST_INVALID", f"sample {index} has unsupported or missing fields")
    normalized = dict(sample)
    split = normalized["split"]
    if split not in _SPLITS:
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


def _validate_manifest_members(manifest: Mapping[str, Any], samples: list[dict[str, Any]]) -> None:
    actual_counts = Counter(sample["split"] for sample in samples)
    expected_counts = manifest["split_counts"]
    if any(actual_counts[split] != expected_counts[split] for split in _SPLITS):
        raise _fail("MANIFEST_INVALID", "split_counts do not match samples")
    if manifest["schema_version"] == 2:
        for split in _SPLITS:
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

    seen_by_split: dict[str, set[str]] = {split: set() for split in _SPLITS}
    all_members: set[str] = set()
    for sample in samples:
        for relative in _sample_paths(sample).values():
            member = relative.as_posix()
            if member in all_members:
                raise _fail("SPLIT_MEMBERS_OVERLAP", member)
            all_members.add(member)
            seen_by_split[sample["split"]].add(member)
    for left_index, left in enumerate(_SPLITS):
        for right in _SPLITS[left_index + 1 :]:
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


def _truth_instances(
    payload: bytes,
    *,
    member: str,
    sample: Mapping[str, Any],
    image_width: int,
    image_height: int,
    schema_version: int,
    scene_geometry: Mapping[str, Any] | None,
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
    instances = truth.get("instances")
    if not isinstance(instances, list) or len(instances) != sample["visible_instance_count"]:
        raise _fail("TRUTH_MISMATCH", f"{member}: instances differ from visible count")
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


def _box_document(box: BoundingBox) -> dict[str, Any]:
    return {
        "absolute_xyxy": list(box.absolute_xyxy),
        "class_name": "cup",
        "normalized_xyxy": list(box.normalized_xyxy),
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

    _dataset_contract(source_root)
    manifest, manifest_payload = _manifest(source_root)
    samples = [
        _validate_sample_shape(sample, index) for index, sample in enumerate(manifest["samples"])
    ]
    _validate_manifest_members(manifest, samples)
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
        manifest["samples"], key=lambda item: (_SPLITS.index(item["split"]), item["seed"])
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
        )
        if len(polygons) != len(truth_instances):
            raise _fail("TRUTH_MISMATCH", f"{paths['label']}: label/truth instance count differs")
        boxes: list[dict[str, Any]] = []
        for polygon, truth_instance in zip(polygons, truth_instances, strict=True):
            label_box = polygon_to_box(polygon, width, height)
            if not _boxes_match(label_box, truth_instance["box"]):
                raise _fail("TRUTH_MISMATCH", f"{paths['label']}: label/truth box differs")
            box_document = _box_document(label_box)
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
