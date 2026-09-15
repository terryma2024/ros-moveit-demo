"""Strict adapter for the upstream fixed parallel-validation point catalog."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from typing import Mapping, Sequence

from ament_index_python.packages import get_package_share_directory
import yaml

from so101_demo.cli.mujoco_parallel_batch import CliError, _catalog


CATALOG_ID = "ai_station_baseline_v1"
CATALOG_SEED = 20260911
CATALOG_SHA256 = "c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5"
CATALOG_RELATIVE_PATH = Path("config/mujoco/moveit_expert_validation_points_v1.yaml")
ANCHOR_IDS = (
    "task_start",
    "cup_test_forward_5cm",
    "cup_test_left_5cm",
    "cup_test_right_5cm",
)
STRATUM_SCHEDULE = (
    "near/left",
    "near/center",
    "near/right",
    "near/left",
    "near/center",
    "mid/left",
    "mid/center",
    "mid/right",
    "mid/left",
    "mid/center",
    "mid/right",
    "far/left",
    "far/center",
    "far/right",
    "far/center",
    "far/right",
)


class CatalogError(ValueError):
    """The installed immutable validation catalog violated its contract."""


@dataclass(frozen=True, slots=True)
class CatalogPoint:
    id: str
    label: str
    source: str
    stratum: str
    position_world_m: tuple[float, float, float]
    display_id: str = ""


@dataclass(frozen=True, slots=True)
class PointSelection:
    catalog_id: str
    catalog_seed: int
    catalog_sha256: str
    points: tuple[CatalogPoint, ...]
    point_ids: tuple[str, ...]
    selection_sha256: str


def _catalog_path() -> Path:
    return (
        Path(get_package_share_directory("so101_demo_py"))
        / CATALOG_RELATIVE_PATH
    )


def _point_stratum(point_id: str, index: int) -> tuple[str, str]:
    if index < len(ANCHOR_IDS):
        return "anchor", "anchor"
    parts = point_id.split("_")
    if (
        len(parts) != 4
        or parts[0] != "sample"
        or not parts[1].isdigit()
        or parts[2] not in {"near", "mid", "far"}
        or parts[3] not in {"left", "center", "right"}
    ):
        raise CatalogError("POINT_CATALOG_STRATUM")
    return "generated", f"{parts[2]}/{parts[3]}"


def _parse_catalog_bytes(
    raw: bytes,
    *,
    expected_sha256: str = CATALOG_SHA256,
) -> tuple[CatalogPoint, ...]:
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise CatalogError("POINT_CATALOG_HASH_MISMATCH")
    try:
        document = yaml.safe_load(raw.decode("utf-8", errors="strict"))
    except (UnicodeError, yaml.YAMLError) as error:
        raise CatalogError("POINT_CATALOG_SCHEMA") from error
    if type(document) is not dict or set(document) != {"schema_version", "points"}:
        raise CatalogError("POINT_CATALOG_SCHEMA")
    if document["schema_version"] != 1 or type(document["points"]) is not list:
        raise CatalogError("POINT_CATALOG_SCHEMA")
    if len(document["points"]) != 20:
        raise CatalogError("POINT_CATALOG_SCHEMA")

    result: list[CatalogPoint] = []
    seen_ids: set[str] = set()
    seen_positions: set[tuple[float, float, float]] = set()
    for index, raw_point in enumerate(document["points"]):
        if type(raw_point) is not dict or set(raw_point) != {
            "id",
            "label",
            "cup_position_world_m",
        }:
            raise CatalogError("POINT_CATALOG_SCHEMA")
        point_id = raw_point["id"]
        label = raw_point["label"]
        if not isinstance(point_id, str) or not point_id or point_id in seen_ids:
            raise CatalogError("POINT_CATALOG_DUPLICATE")
        if not isinstance(label, str) or not label:
            raise CatalogError("POINT_CATALOG_SCHEMA")
        raw_position = raw_point["cup_position_world_m"]
        if (
            type(raw_position) is not list
            or len(raw_position) != 3
            or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in raw_position)
        ):
            raise CatalogError("POINT_CATALOG_COORDINATE")
        position = tuple(float(value) for value in raw_position)
        if not all(math.isfinite(value) for value in position):
            raise CatalogError("POINT_CATALOG_COORDINATE")
        if position in seen_positions:
            raise CatalogError("POINT_CATALOG_COORDINATE")
        source, stratum = _point_stratum(point_id, index)
        result.append(
            CatalogPoint(
                id=point_id,
                label=label,
                source=source,
                stratum=stratum,
                position_world_m=position,
            )
        )
        seen_ids.add(point_id)
        seen_positions.add(position)

    if tuple(point.id for point in result[:4]) != ANCHOR_IDS:
        raise CatalogError("POINT_CATALOG_ANCHORS")
    if tuple(point.stratum for point in result[4:]) != STRATUM_SCHEDULE:
        raise CatalogError("POINT_CATALOG_STRATUM")
    return tuple(result)


def load_baseline_catalog() -> tuple[CatalogPoint, ...]:
    """Load and verify the exact installed catalog consumed by the coordinator."""

    path = _catalog_path()
    try:
        upstream_catalog, digest = _catalog(path)
        raw = path.read_bytes()
    except (CliError, OSError) as error:
        reason = str(error) if isinstance(error, CliError) else "POINT_CATALOG_MISSING"
        raise CatalogError(reason) from error
    if digest != CATALOG_SHA256:
        raise CatalogError("POINT_CATALOG_HASH_MISMATCH")
    points = _parse_catalog_bytes(raw)
    if tuple(upstream_catalog) != tuple(point.id for point in points):
        raise CatalogError("POINT_CATALOG_UPSTREAM_ORDER")
    return points


def selection_sha256(point_ids: Sequence[str]) -> str:
    if isinstance(point_ids, (str, bytes)):
        raise CatalogError("POINT_IDS_SEQUENCE")
    values = list(point_ids)
    if not values or any(not isinstance(value, str) or not value for value in values):
        raise CatalogError("POINT_IDS_SEQUENCE")
    if len(values) != len(set(values)):
        raise CatalogError("POINT_IDS_DUPLICATE")
    payload = json.dumps(values, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _stratum_allocations(generated_count: int) -> Mapping[str, int]:
    quotas = Counter(STRATUM_SCHEDULE)
    first_index = {
        stratum: STRATUM_SCHEDULE.index(stratum) for stratum in quotas
    }
    allocation = {
        stratum: generated_count * count // len(STRATUM_SCHEDULE)
        for stratum, count in quotas.items()
    }
    remaining = generated_count - sum(allocation.values())
    ranking = sorted(
        quotas,
        key=lambda stratum: (
            -(generated_count * quotas[stratum] % len(STRATUM_SCHEDULE)),
            first_index[stratum],
        ),
    )
    for stratum in ranking[:remaining]:
        allocation[stratum] += 1
    return allocation


def _select_catalog_points(
    catalog: Sequence[CatalogPoint], total_points: int
) -> PointSelection:
    if isinstance(total_points, bool) or not isinstance(total_points, int) or not 4 <= total_points <= 20:
        raise CatalogError("TOTAL_POINTS_RANGE")
    if len(catalog) != 20:
        raise CatalogError("POINT_CATALOG_SCHEMA")
    generated_count = total_points - len(ANCHOR_IDS)
    allocations = _stratum_allocations(generated_count)
    selected: list[CatalogPoint] = list(catalog[: len(ANCHOR_IDS)])
    used = Counter()
    for point in catalog[len(ANCHOR_IDS) :]:
        if used[point.stratum] < allocations[point.stratum]:
            selected.append(point)
            used[point.stratum] += 1
    if len(selected) != total_points:
        raise CatalogError("POINT_SELECTION_INCOMPLETE")
    displayed = tuple(
        replace(point, display_id=f"P{index:02d}")
        for index, point in enumerate(selected, start=1)
    )
    point_ids = tuple(point.id for point in displayed)
    return PointSelection(
        catalog_id=CATALOG_ID,
        catalog_seed=CATALOG_SEED,
        catalog_sha256=CATALOG_SHA256,
        points=displayed,
        point_ids=point_ids,
        selection_sha256=selection_sha256(point_ids),
    )


def select_catalog_points(total_points: int) -> PointSelection:
    """Select 4–20 points with the frozen largest-remainder stratum policy."""

    return _select_catalog_points(load_baseline_catalog(), total_points)
