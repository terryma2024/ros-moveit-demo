"""Inventory capability checks, polygon rasterisation and the truth artifacts."""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
import hmac
import json
import math

import numpy as np
import PIL
from PIL import Image, ImageDraw

from so101_demo.perception_benchmark.dataset.contracts import (
    _EXPECTED_SCENARIO_COUNTS,
    _LABEL_COORDINATE_FORMAT,
    _RASTERIZER,
    DatasetInventory,
    DatasetVerificationError,
    Split,
    _capability_digest,
)


def _inventory_capability(inventory: DatasetInventory) -> str:
    return _capability_digest(
        "dataset-inventory",
        inventory.schema_version,
        inventory.split,
        inventory.archive_sha256,
        inventory.inventory_sha256,
        inventory.dataset_root.resolve(),
        inventory.sample_count,
        tuple(sorted(inventory.scenario_counts.items())),
        inventory.samples,
        inventory.test_access_event_sha256,
        inventory.access_log_path,
    )


def _issue_inventory(inventory: DatasetInventory) -> None:
    object.__setattr__(inventory, "_capability", _inventory_capability(inventory))


def _require_inventory_capability(inventory: DatasetInventory) -> None:
    if inventory._capability is None or not hmac.compare_digest(
        inventory._capability, _inventory_capability(inventory)
    ):
        raise DatasetVerificationError("INVENTORY_CAPABILITY_INVALID")


def _require_rasterizer_version() -> None:
    if PIL.__version__ != _RASTERIZER["version"]:
        raise DatasetVerificationError("RASTERIZER_VERSION_MISMATCH")


def _round_half_up(value: float) -> int:
    return int(math.floor(value + 0.5))


def rasterize_polygon(
    polygon_xy: tuple[tuple[float, float], ...], width: int, height: int
) -> np.ndarray:
    _require_rasterizer_version()
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width <= 0
        or height <= 0
        or len(polygon_xy) < 3
    ):
        raise DatasetVerificationError("POLYGON_RASTERIZATION_INPUT_INVALID")
    pixels: list[tuple[int, int]] = []
    for point in polygon_xy:
        if len(point) != 2:
            raise DatasetVerificationError("POLYGON_RASTERIZATION_INPUT_INVALID")
        x, y = point
        if not (math.isfinite(x) and math.isfinite(y) and 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
            raise DatasetVerificationError("POLYGON_RASTERIZATION_INPUT_INVALID")
        pixels.append(
            (
                min(width - 1, max(0, _round_half_up(x * (width - 1)))),
                min(height - 1, max(0, _round_half_up(y * (height - 1)))),
            )
        )
    image = Image.new("1", (width, height), 0)
    ImageDraw.Draw(image).polygon(pixels, fill=1)
    return np.asarray(image, dtype=bool)


def _read_truth_bytes(payload: bytes, split: Split) -> dict[str, object]:
    try:
        document = json.loads(payload, parse_float=Decimal)
    except (UnicodeDecodeError, json.JSONDecodeError, InvalidOperation) as error:
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID") from error
    if not isinstance(document, dict):
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    scenario = document.get("scenario")
    instances = document.get("instances")
    visible_count = document.get("visible_instance_count")
    if (
        document.get("split") != split
        or scenario not in _EXPECTED_SCENARIO_COUNTS
        or not isinstance(instances, list)
        or isinstance(visible_count, bool)
        or not isinstance(visible_count, int)
        or visible_count != len(instances)
    ):
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    expected_count = {
        "no_cup": 0,
        "one_cup_distractors": 1,
        "two_cups": 2,
        "cup_near_bottle": 1,
    }[scenario]
    if len(instances) != expected_count:
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    _truth_polygons(document)
    return document


def _truth_polygons(
    truth: Mapping[str, object],
) -> tuple[tuple[tuple[Decimal, Decimal], ...], ...]:
    instances = truth.get("instances")
    if not isinstance(instances, list):
        raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
    result: list[tuple[tuple[Decimal, Decimal], ...]] = []
    for instance in instances:
        if not isinstance(instance, dict):
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        raw_polygon = instance.get("polygon_xy")
        if not isinstance(raw_polygon, list) or len(raw_polygon) < 3:
            raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
        polygon: list[tuple[Decimal, Decimal]] = []
        for point in raw_polygon:
            if not isinstance(point, list) or len(point) != 2:
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
            try:
                x, y = (Decimal(str(point[0])), Decimal(str(point[1])))
            except InvalidOperation as error:
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID") from error
            if not (x.is_finite() and y.is_finite() and 0 <= x <= 1 and 0 <= y <= 1):
                raise DatasetVerificationError("TRUTH_DOCUMENT_INVALID")
            polygon.append((x, y))
        result.append(tuple(polygon))
    return tuple(result)


def _read_label_polygons_bytes(
    payload: bytes,
) -> tuple[tuple[tuple[Decimal, Decimal], ...], ...]:
    try:
        lines = payload.decode("utf-8").splitlines()
    except UnicodeDecodeError as error:
        raise DatasetVerificationError("LABEL_DOCUMENT_INVALID") from error
    polygons: list[tuple[tuple[Decimal, Decimal], ...]] = []
    for line in lines:
        fields = line.split()
        if len(fields) < 7 or len(fields) % 2 != 1 or fields[0] != "0":
            raise DatasetVerificationError("LABEL_DOCUMENT_INVALID")
        try:
            values = tuple(Decimal(value) for value in fields[1:])
        except InvalidOperation as error:
            raise DatasetVerificationError("LABEL_DOCUMENT_INVALID") from error
        if any(not value.is_finite() or not 0 <= value <= 1 for value in values):
            raise DatasetVerificationError("LABEL_DOCUMENT_INVALID")
        polygons.append(tuple(zip(values[::2], values[1::2], strict=True)))
    return tuple(polygons)


def _at_label_coordinate_precision(
    polygons: tuple[tuple[tuple[Decimal, Decimal], ...], ...],
) -> tuple[tuple[tuple[Decimal, Decimal], ...], ...]:
    return tuple(
        tuple(
            (
                Decimal(format(float(x), _LABEL_COORDINATE_FORMAT)),
                Decimal(format(float(y), _LABEL_COORDINATE_FORMAT)),
            )
            for x, y in polygon
        )
        for polygon in polygons
    )
