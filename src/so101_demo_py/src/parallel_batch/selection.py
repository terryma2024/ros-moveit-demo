"""Immutable selection bindings for one macOS service campaign (design section 8).

The service writes exactly one binding before it starts a campaign, and the adapter accepts only
that binding. Nothing here generates points, defaults to the first catalog entries, or lets a
Worker walk the installed catalog: a `FirstPassSelectionBinding` carries 4-20 ordered points and
must contain the four fixed anchors, while a `RetrySelectionBinding` carries exactly one point and
must reference the original catalog, selection and result hashes of a committed business `FAILED`
point.

Every field is validated in `__post_init__` and the selection digest is recomputed from the
content, so a binding that was edited after it was written cannot be used. Missing or drifted
inputs raise `SelectionError` with a stable code.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

import yaml

from .resource_identity import canonical_sha256

#: The four fixed anchors the upstream catalog starts with. They identify the frozen start pose
#: and its three immediate neighbours, so every first-pass selection has to contain them.
ANCHOR_IDS: tuple[str, ...] = (
    "task_start",
    "cup_test_forward_5cm",
    "cup_test_left_5cm",
    "cup_test_right_5cm",
)

FIRST_PASS_MIN_POINTS = 4
FIRST_PASS_MAX_POINTS = 20
SUPPORTED_CATALOG_SCHEMA_VERSIONS = (1,)
DEFAULT_COORDINATE_FRAME = "world"
BUSINESS_FAILED = "FAILED"


class SelectionError(ValueError):
    """A selection binding or catalog violated its contract."""

    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}" if detail else code)


def _require_sha256(name: str, value: object, *, code: str = "SELECTION_HASH_INVALID") -> str:
    if not isinstance(value, str) or len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise SelectionError(code, f"{name}={value!r}")
    return value


def _require_id(name: str, value: object) -> str:
    if not isinstance(value, str) or not value:
        raise SelectionError("SELECTION_ID_INVALID", f"{name}={value!r}")
    return value


def _position(value: object, *, point_id: str) -> tuple[float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise SelectionError("SELECTION_CATALOG_INVALID", f"{point_id}: position")
    numbers = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise SelectionError("SELECTION_CATALOG_INVALID", f"{point_id}: position")
        numbers.append(float(item))
    return (numbers[0], numbers[1], numbers[2])


@dataclass(frozen=True, slots=True)
class SelectedPoint:
    """One selected catalog point, addressed by id and pinned by its own digest."""

    point_id: str
    position_xyz_m: tuple[float, float, float]
    point_sha256: str

    def __post_init__(self) -> None:
        _require_id("point_id", self.point_id)
        _require_sha256("point_sha256", self.point_sha256)
        if not isinstance(self.position_xyz_m, tuple) or len(self.position_xyz_m) != 3:
            raise SelectionError("SELECTION_CATALOG_INVALID", f"{self.point_id}: position")

    def as_document(self) -> dict[str, object]:
        return {
            "point_id": self.point_id,
            "position_xyz_m": list(self.position_xyz_m),
            "point_sha256": self.point_sha256,
        }


@dataclass(frozen=True, slots=True)
class PointCatalog:
    """The immutable catalog one binding was built from."""

    schema_version: int
    sha256: str
    points: tuple[SelectedPoint, ...]

    def __post_init__(self) -> None:
        if self.schema_version not in SUPPORTED_CATALOG_SCHEMA_VERSIONS:
            raise SelectionError("SELECTION_CATALOG_INVALID", f"schema={self.schema_version}")
        _require_sha256("catalog_sha256", self.sha256)
        if not self.points:
            raise SelectionError("SELECTION_CATALOG_INVALID", "no points")
        if len({point.point_id for point in self.points}) != len(self.points):
            raise SelectionError("SELECTION_CATALOG_INVALID", "duplicate point ids")

    @property
    def point_ids(self) -> tuple[str, ...]:
        return tuple(point.point_id for point in self.points)

    def point(self, point_id: str) -> SelectedPoint:
        for point in self.points:
            if point.point_id == point_id:
                return point
        raise SelectionError("SELECTION_POINT_UNKNOWN", point_id)


def _point_sha256(point_id: str, position_xyz_m: tuple[float, float, float]) -> str:
    return canonical_sha256(
        {"point_id": point_id, "position_xyz_m": list(position_xyz_m)}
    )


def load_point_catalog(path: Path) -> PointCatalog:
    """Parse the closed catalog schema; unknown keys, shapes or duplicates fail closed."""

    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise SelectionError("SELECTION_CATALOG_UNREADABLE", str(path)) from error
    try:
        document = yaml.safe_load(raw)
    except yaml.YAMLError as error:
        raise SelectionError("SELECTION_CATALOG_INVALID", f"{path}: {error}") from error
    if not isinstance(document, Mapping):
        raise SelectionError("SELECTION_CATALOG_INVALID", "not a mapping")
    schema_version = document.get("schema_version")
    if schema_version not in SUPPORTED_CATALOG_SCHEMA_VERSIONS:
        raise SelectionError("SELECTION_CATALOG_INVALID", f"schema={schema_version!r}")
    entries = document.get("points")
    if not isinstance(entries, Sequence) or isinstance(entries, (str, bytes)) or not entries:
        raise SelectionError("SELECTION_CATALOG_INVALID", "points")
    points: list[SelectedPoint] = []
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise SelectionError("SELECTION_CATALOG_INVALID", "point entry")
        point_id = _require_id("point_id", entry.get("id"))
        position = _position(entry.get("cup_position_world_m"), point_id=point_id)
        points.append(
            SelectedPoint(
                point_id=point_id,
                position_xyz_m=position,
                point_sha256=_point_sha256(point_id, position),
            )
        )
    return PointCatalog(
        schema_version=int(schema_version),
        sha256=hashlib.sha256(raw).hexdigest(),
        points=tuple(points),
    )


def _verified_catalog(
    catalog_path: Path, expected_catalog_sha256: str | None
) -> PointCatalog:
    catalog = load_point_catalog(catalog_path)
    if expected_catalog_sha256 is not None:
        expected = _require_sha256("expected_catalog_sha256", expected_catalog_sha256)
        if catalog.sha256 != expected:
            raise SelectionError(
                "SELECTION_CATALOG_DRIFT",
                f"{catalog.sha256} != expected {expected}",
            )
    return catalog


def _selection_document(
    *,
    catalog_schema_version: int,
    catalog_sha256: str,
    coordinate_frame: str,
    points: Sequence[SelectedPoint],
    campaign_id: str,
    batch_id: str,
    config_sha256: str,
    runtime_closure_sha256: str,
) -> dict[str, object]:
    return {
        "catalog_schema_version": catalog_schema_version,
        "catalog_sha256": catalog_sha256,
        "coordinate_frame": coordinate_frame,
        "points": [point.as_document() for point in points],
        "campaign_id": campaign_id,
        "batch_id": batch_id,
        "config_sha256": config_sha256,
        "runtime_closure_sha256": runtime_closure_sha256,
    }


@dataclass(frozen=True, slots=True)
class FirstPassSelectionBinding:
    """The immutable first-pass selection: 4-20 ordered points including the four anchors."""

    catalog_schema_version: int
    catalog_sha256: str
    coordinate_frame: str
    points: tuple[SelectedPoint, ...]
    selection_sha256: str
    campaign_id: str
    batch_id: str
    config_sha256: str
    runtime_closure_sha256: str

    def __post_init__(self) -> None:
        if self.catalog_schema_version not in SUPPORTED_CATALOG_SCHEMA_VERSIONS:
            raise SelectionError(
                "SELECTION_CATALOG_INVALID", f"schema={self.catalog_schema_version!r}"
            )
        _require_sha256("catalog_sha256", self.catalog_sha256)
        _require_sha256("selection_sha256", self.selection_sha256)
        _require_sha256("config_sha256", self.config_sha256)
        _require_sha256("runtime_closure_sha256", self.runtime_closure_sha256)
        _require_id("coordinate_frame", self.coordinate_frame)
        _require_id("campaign_id", self.campaign_id)
        _require_id("batch_id", self.batch_id)
        if not isinstance(self.points, tuple) or any(
            not isinstance(point, SelectedPoint) for point in self.points
        ):
            raise SelectionError("SELECTION_POINT_COUNT", "points must be SelectedPoint entries")
        if not FIRST_PASS_MIN_POINTS <= len(self.points) <= FIRST_PASS_MAX_POINTS:
            raise SelectionError(
                "SELECTION_POINT_COUNT",
                f"{len(self.points)} points outside "
                f"{FIRST_PASS_MIN_POINTS}..{FIRST_PASS_MAX_POINTS}",
            )
        if len({point.point_id for point in self.points}) != len(self.points):
            raise SelectionError("SELECTION_POINT_DUPLICATE", "duplicate selected point")
        selected = {point.point_id for point in self.points}
        missing = [anchor for anchor in ANCHOR_IDS if anchor not in selected]
        if missing:
            raise SelectionError("SELECTION_ANCHOR_MISSING", ", ".join(missing))
        if self.selection_sha256 != self.compute_sha256():
            raise SelectionError(
                "SELECTION_HASH_MISMATCH",
                f"{self.selection_sha256} != {self.compute_sha256()}",
            )

    @property
    def selected_point_ids(self) -> tuple[str, ...]:
        return tuple(point.point_id for point in self.points)

    def compute_sha256(self) -> str:
        return canonical_sha256(
            _selection_document(
                catalog_schema_version=self.catalog_schema_version,
                catalog_sha256=self.catalog_sha256,
                coordinate_frame=self.coordinate_frame,
                points=self.points,
                campaign_id=self.campaign_id,
                batch_id=self.batch_id,
                config_sha256=self.config_sha256,
                runtime_closure_sha256=self.runtime_closure_sha256,
            )
        )

    def as_document(self) -> dict[str, object]:
        return {
            "kind": "FIRST_PASS",
            **_selection_document(
                catalog_schema_version=self.catalog_schema_version,
                catalog_sha256=self.catalog_sha256,
                coordinate_frame=self.coordinate_frame,
                points=self.points,
                campaign_id=self.campaign_id,
                batch_id=self.batch_id,
                config_sha256=self.config_sha256,
                runtime_closure_sha256=self.runtime_closure_sha256,
            ),
            "selected_point_ids": list(self.selected_point_ids),
            "selection_sha256": self.selection_sha256,
        }


def _retry_document(binding: "RetrySelectionBinding") -> dict[str, object]:
    return {
        "kind": "FULL_RESTART_RETRY",
        "original_catalog_sha256": binding.original_catalog_sha256,
        "original_selection_sha256": binding.original_selection_sha256,
        "original_result_sha256": binding.original_result_sha256,
        "original_outcome": binding.original_outcome,
        "point": binding.point.as_document(),
        "campaign_id": binding.campaign_id,
        "batch_id": binding.batch_id,
        "config_sha256": binding.config_sha256,
        "runtime_closure_sha256": binding.runtime_closure_sha256,
    }


@dataclass(frozen=True, slots=True)
class RetrySelectionBinding:
    """The immutable retry selection: exactly one committed business `FAILED` point."""

    original_catalog_sha256: str
    original_selection_sha256: str
    original_result_sha256: str
    original_outcome: str
    point: SelectedPoint
    campaign_id: str
    batch_id: str
    config_sha256: str
    runtime_closure_sha256: str
    selection_sha256: str

    def __post_init__(self) -> None:
        _require_sha256("original_catalog_sha256", self.original_catalog_sha256)
        _require_sha256("original_selection_sha256", self.original_selection_sha256)
        _require_sha256("original_result_sha256", self.original_result_sha256)
        _require_sha256("config_sha256", self.config_sha256)
        _require_sha256("runtime_closure_sha256", self.runtime_closure_sha256)
        _require_sha256("selection_sha256", self.selection_sha256)
        _require_id("campaign_id", self.campaign_id)
        _require_id("batch_id", self.batch_id)
        if not isinstance(self.point, SelectedPoint):
            raise SelectionError("SELECTION_POINT_UNKNOWN", repr(self.point))
        if self.original_outcome != BUSINESS_FAILED:
            raise SelectionError(
                "RETRY_ORIGINAL_NOT_FAILED", f"outcome={self.original_outcome!r}"
            )
        if self.selection_sha256 != self.compute_sha256():
            raise SelectionError(
                "SELECTION_HASH_MISMATCH",
                f"{self.selection_sha256} != {self.compute_sha256()}",
            )

    @property
    def selected_point_ids(self) -> tuple[str, ...]:
        return (self.point.point_id,)

    def compute_sha256(self) -> str:
        return canonical_sha256(_retry_document(self))

    def as_document(self) -> dict[str, object]:
        return {**_retry_document(self), "selection_sha256": self.selection_sha256}


def build_first_pass_selection(
    *,
    catalog_path: Path,
    point_ids: Sequence[str],
    campaign_id: str,
    batch_id: str,
    config_sha256: str,
    runtime_closure_sha256: str,
    coordinate_frame: str = DEFAULT_COORDINATE_FRAME,
    expected_catalog_sha256: str | None = None,
) -> FirstPassSelectionBinding:
    """Freeze one ordered first-pass selection from the immutable catalog."""

    catalog = _verified_catalog(Path(catalog_path), expected_catalog_sha256)
    identifiers = tuple(point_ids)
    if not FIRST_PASS_MIN_POINTS <= len(identifiers) <= FIRST_PASS_MAX_POINTS:
        raise SelectionError(
            "SELECTION_POINT_COUNT",
            f"{len(identifiers)} points outside "
            f"{FIRST_PASS_MIN_POINTS}..{FIRST_PASS_MAX_POINTS}",
        )
    if len(set(identifiers)) != len(identifiers):
        raise SelectionError("SELECTION_POINT_DUPLICATE", "duplicate selected point")
    points = tuple(catalog.point(point_id) for point_id in identifiers)
    _require_sha256("config_sha256", config_sha256)
    _require_sha256("runtime_closure_sha256", runtime_closure_sha256)
    document = _selection_document(
        catalog_schema_version=catalog.schema_version,
        catalog_sha256=catalog.sha256,
        coordinate_frame=coordinate_frame,
        points=points,
        campaign_id=_require_id("campaign_id", campaign_id),
        batch_id=_require_id("batch_id", batch_id),
        config_sha256=config_sha256,
        runtime_closure_sha256=runtime_closure_sha256,
    )
    return FirstPassSelectionBinding(
        catalog_schema_version=catalog.schema_version,
        catalog_sha256=catalog.sha256,
        coordinate_frame=coordinate_frame,
        points=points,
        selection_sha256=canonical_sha256(document),
        campaign_id=campaign_id,
        batch_id=batch_id,
        config_sha256=config_sha256,
        runtime_closure_sha256=runtime_closure_sha256,
    )


def build_retry_selection(
    *,
    catalog_path: Path,
    point_id: str,
    original_selection_sha256: str,
    original_result_sha256: str,
    original_outcome: str,
    campaign_id: str,
    batch_id: str,
    config_sha256: str,
    runtime_closure_sha256: str,
    expected_catalog_sha256: str | None = None,
) -> RetrySelectionBinding:
    """Freeze the single business-failed point one retry batch may execute."""

    catalog = _verified_catalog(Path(catalog_path), expected_catalog_sha256)
    if original_outcome != BUSINESS_FAILED:
        raise SelectionError("RETRY_ORIGINAL_NOT_FAILED", f"outcome={original_outcome!r}")
    for name, value in (
        ("original_selection_sha256", original_selection_sha256),
        ("original_result_sha256", original_result_sha256),
    ):
        if not isinstance(value, str) or len(value) != 64 or any(
            character not in "0123456789abcdef" for character in value
        ):
            raise SelectionError("RETRY_SOURCE_CHAIN_REQUIRED", f"{name}={value!r}")
    point = catalog.point(_require_id("point_id", point_id))
    _require_sha256("config_sha256", config_sha256)
    _require_sha256("runtime_closure_sha256", runtime_closure_sha256)
    selection_sha256 = canonical_sha256(
        {
            "kind": "FULL_RESTART_RETRY",
            "original_catalog_sha256": catalog.sha256,
            "original_selection_sha256": original_selection_sha256,
            "original_result_sha256": original_result_sha256,
            "original_outcome": original_outcome,
            "point": point.as_document(),
            "campaign_id": campaign_id,
            "batch_id": batch_id,
            "config_sha256": config_sha256,
            "runtime_closure_sha256": runtime_closure_sha256,
        }
    )
    return RetrySelectionBinding(
        original_catalog_sha256=catalog.sha256,
        original_selection_sha256=original_selection_sha256,
        original_result_sha256=original_result_sha256,
        original_outcome=original_outcome,
        point=point,
        campaign_id=_require_id("campaign_id", campaign_id),
        batch_id=_require_id("batch_id", batch_id),
        config_sha256=config_sha256,
        runtime_closure_sha256=runtime_closure_sha256,
        selection_sha256=selection_sha256,
    )
