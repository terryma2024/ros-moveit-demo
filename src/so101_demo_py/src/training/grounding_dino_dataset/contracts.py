"""Dataset contract constants, the error type and the box helpers."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
import math
import re
from typing import Any

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


_LEGACY_SPLITS = ("train", "val", "test")


_TRAIN_VAL_SPLITS = ("train", "val")


_TRAIN_VAL_DATASET_CONTRACT = "so101-nonpenetrating-train-val-v1"


_TEST_SPLITS = ("test",)


_TEST_DATASET_CONTRACT = "so101-nonpenetrating-test-v1"


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


_TEST_SPLIT_COUNTS = {"test": 300}


_TEST_SEED_STARTS = {"test": 470_000_000}


_TEST_SEED_RANGES = {"test": [470_000_000, 470_000_299]}


_TEST_SCENARIO_QUOTAS = {
    "test": {scenario: 50 for scenario in _TRAIN_VAL_SCENARIOS},
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
