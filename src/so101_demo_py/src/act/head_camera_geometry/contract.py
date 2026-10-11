"""The head camera geometry contract, its definitions, results and coverage intervals."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
import json
import math
from pathlib import Path
from typing import Any, Protocol

from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1


_EPSILON = 1e-9


ARM_JOINT_NAMES = ("1", "2", "3", "4", "5", "6")


ARM_JOINT_COUNT = len(ARM_JOINT_NAMES)


CAMERA_KEYS = (
    "camera_name",
    "width",
    "height",
    "fovy_rad",
    "distortion_model",
    "distortion",
    "parent_body",
    "local_position_m",
    "local_xyaxes",
)


DISTORTION_MODEL = "plumb_bob"


DISTORTION_COEFFICIENTS = (0.0, 0.0, 0.0, 0.0, 0.0)


ANCHOR_KEYS = ("name", "cup_start_m", "neck_start_rad")


CONTRACT_KEYS = (
    "camera",
    "neck_joint",
    "anchors",
    "workspace_x_m",
    "workspace_y_m",
    "workspace_z_m",
    "workspace_step_m",
    "neck_grid_rad",
    "validation_arm_rad",
    "coarse_step_candidate_rad",
    "safe_interval_margin_rad",
    "safe_bisection_tolerance_rad",
    "fov_tolerance_rad",
    "visible_pixel_minimum",
    "accepted_scene_sha256",
    "accepted_camera_source_sha256",
)


class HeadCameraGeometryError(ValueError):
    """A geometry fact the seal cannot accept, named so a caller can refuse by name."""


def _finite(name: str, value: object, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HeadCameraGeometryError(
            f"HEAD_CAMERA_CONTRACT_INVALID: {name} must be a finite number"
        )
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0.0):
        raise HeadCameraGeometryError(
            f"HEAD_CAMERA_CONTRACT_INVALID: {name} must be finite"
            + (" and positive" if positive else "")
        )
    return result


def _vector(name: str, value: object, size: int) -> tuple[float, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise HeadCameraGeometryError(
            f"HEAD_CAMERA_CONTRACT_INVALID: {name} must be a {size}-element sequence"
        )
    result = tuple(_finite(f"{name}[{index}]", item) for index, item in enumerate(value))
    if len(result) != size:
        raise HeadCameraGeometryError(
            f"HEAD_CAMERA_CONTRACT_INVALID: {name} must hold exactly {size} numbers"
        )
    return result


def _range(name: str, value: object) -> tuple[float, float]:
    low, high = _vector(name, value, 2)
    if low >= high:
        raise HeadCameraGeometryError(
            f"HEAD_CAMERA_CONTRACT_INVALID: {name} must be an increasing two-value range"
        )
    return (low, high)


def _digest(name: str, value: object) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise HeadCameraGeometryError(
            f"HEAD_CAMERA_CONTRACT_INVALID: {name} must be a lowercase SHA256 digest"
        )
    return value


def horizontal_fov_rad(*, fovy_rad: float, width: int, height: int) -> float:
    """The horizontal field of view MuJoCo's own definition implies for square pixels."""

    focal_px = (float(height) / 2.0) / math.tan(float(fovy_rad) / 2.0)
    return 2.0 * math.atan((float(width) / 2.0) / focal_px)


def scene_source_digests(scene_path: Path | str) -> dict[str, str]:
    """SHA256 of one scene file and of the robot file it includes.

    The camera belongs to the included robot, so a dataset scene that includes a different robot can
    carry a different camera while the scene file looks unchanged. Both digests are therefore part of
    the seal identity, and this is the one function that reads them.
    """

    import hashlib

    scene = Path(scene_path)
    if not scene.is_file():
        raise HeadCameraGeometryError(f"HEAD_CAMERA_SCENE_MISSING: {scene}")
    robot_source = scene
    for line in scene.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("<include") and "file=" in stripped:
            included = stripped.split('file="', 1)[1].split('"', 1)[0]
            candidate = (scene.parent / included).resolve()
            if candidate.is_file():
                robot_source = candidate
            break
    return {
        "scene_sha256": hashlib.sha256(scene.read_bytes()).hexdigest(),
        "camera_source_sha256": hashlib.sha256(robot_source.read_bytes()).hexdigest(),
    }


def project_point(
    *,
    point_m: Sequence[float],
    camera_position_m: Sequence[float],
    camera_rotation: Sequence[Sequence[float]],
    width: int,
    height: int,
    fovy_rad: float,
) -> tuple[float, float, bool]:
    """Project one world point with MuJoCo's camera convention: x right, y up, looking along -z."""

    relative = [float(point_m[index]) - float(camera_position_m[index]) for index in range(3)]
    local = [
        sum(float(camera_rotation[row][column]) * relative[row] for row in range(3))
        for column in range(3)
    ]
    if local[2] >= -_EPSILON:
        return (math.nan, math.nan, False)
    focal_px = (float(height) / 2.0) / math.tan(float(fovy_rad) / 2.0)
    u = float(width) / 2.0 + focal_px * local[0] / (-local[2])
    v = float(height) / 2.0 - focal_px * local[1] / (-local[2])
    in_frame = 0.0 <= u < float(width) and 0.0 <= v < float(height)
    return (u, v, in_frame)


@dataclass(frozen=True, slots=True)
class CameraDefinition:
    camera_name: str
    width: int
    height: int
    fovy_rad: float
    distortion_model: str = DISTORTION_MODEL
    distortion: tuple[float, float, float, float, float] = DISTORTION_COEFFICIENTS
    parent_body: str = ""
    local_position_m: tuple[float, float, float, float] = (0.0, 0.0, 0.0)
    local_xyaxes: tuple[float, ...] = (1.0, 0.0, 0.0, 0.0, 1.0, 0.0)

    def __post_init__(self) -> None:
        if not isinstance(self.camera_name, str) or not self.camera_name:
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: camera_name must be a non-empty string"
            )
        for name in ("width", "height"):
            value = getattr(self, name)
            if type(value) is not int or value <= 0:
                raise HeadCameraGeometryError(
                    f"HEAD_CAMERA_CONTRACT_INVALID: {name} must be a positive integer"
                )
        fovy = _finite("fovy_rad", self.fovy_rad, positive=True)
        if not 0.0 < fovy < math.pi:
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: fovy_rad must be inside (0, pi)"
            )
        object.__setattr__(self, "fovy_rad", fovy)
        if self.distortion_model != DISTORTION_MODEL:
            raise HeadCameraGeometryError(
                f"HEAD_CAMERA_CONTRACT_INVALID: distortion_model must be {DISTORTION_MODEL!r}, the "
                "only model MuJoCo's pinhole camera implements"
            )
        object.__setattr__(self, "distortion", _vector("distortion", self.distortion, 5))
        if not isinstance(self.parent_body, str) or not self.parent_body:
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: parent_body must be a non-empty string"
            )
        object.__setattr__(
            self, "local_position_m", _vector("local_position_m", self.local_position_m, 3)
        )
        object.__setattr__(self, "local_xyaxes", _vector("local_xyaxes", self.local_xyaxes, 6))

    @property
    def horizontal_fov_rad(self) -> float:
        return horizontal_fov_rad(fovy_rad=self.fovy_rad, width=self.width, height=self.height)

    def to_document(self) -> dict[str, Any]:
        return {
            "camera_name": self.camera_name,
            "width": self.width,
            "height": self.height,
            "fovy_rad": self.fovy_rad,
            "distortion_model": self.distortion_model,
            "distortion": list(self.distortion),
            "parent_body": self.parent_body,
            "local_position_m": list(self.local_position_m),
            "local_xyaxes": list(self.local_xyaxes),
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> CameraDefinition:
        if not isinstance(document, Mapping) or set(document) != set(CAMERA_KEYS):
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: camera must hold exactly " + ", ".join(CAMERA_KEYS)
            )
        return cls(**{key: document[key] for key in CAMERA_KEYS})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class HeadCameraAnchor:
    name: str
    cup_start_m: tuple[float, float, float]
    neck_start_rad: float

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: anchor name must be a non-empty string"
            )
        object.__setattr__(self, "cup_start_m", _vector("cup_start_m", self.cup_start_m, 3))
        object.__setattr__(self, "neck_start_rad", _finite("neck_start_rad", self.neck_start_rad))

    def to_document(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cup_start_m": list(self.cup_start_m),
            "neck_start_rad": self.neck_start_rad,
        }

    @classmethod
    def from_document(cls, document: Mapping[str, Any]) -> HeadCameraAnchor:
        if not isinstance(document, Mapping) or set(document) != set(ANCHOR_KEYS):
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: an anchor must hold exactly "
                + ", ".join(ANCHOR_KEYS)
            )
        return cls(**{key: document[key] for key in ANCHOR_KEYS})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class HeadCameraGeometryContract:
    camera: CameraDefinition
    neck_joint: str
    anchors: tuple[HeadCameraAnchor, ...]
    workspace_x_m: tuple[float, float]
    workspace_y_m: tuple[float, float]
    workspace_z_m: tuple[float, float]
    workspace_step_m: float
    neck_grid_rad: tuple[float, float, float]
    validation_arm_rad: tuple[float, ...]
    coarse_step_candidate_rad: float
    safe_interval_margin_rad: float
    safe_bisection_tolerance_rad: float
    fov_tolerance_rad: float
    visible_pixel_minimum: int
    accepted_scene_sha256: str
    accepted_camera_source_sha256: str
    scene_path: Path | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.camera, CameraDefinition):
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: camera must be a camera definition"
            )
        if not isinstance(self.neck_joint, str) or not self.neck_joint:
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: neck_joint must be a non-empty string"
            )
        anchors = tuple(self.anchors)
        if not anchors or any(not isinstance(anchor, HeadCameraAnchor) for anchor in anchors):
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: anchors must be a non-empty sequence of anchors"
            )
        if len({anchor.name for anchor in anchors}) != len(anchors):
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: anchor names must be unique"
            )
        object.__setattr__(self, "anchors", anchors)
        object.__setattr__(self, "workspace_x_m", _range("workspace_x_m", self.workspace_x_m))
        object.__setattr__(self, "workspace_y_m", _range("workspace_y_m", self.workspace_y_m))
        object.__setattr__(self, "workspace_z_m", _range("workspace_z_m", self.workspace_z_m))
        object.__setattr__(
            self,
            "workspace_step_m",
            _finite("workspace_step_m", self.workspace_step_m, positive=True),
        )
        grid = _vector("neck_grid_rad", self.neck_grid_rad, 3)
        if grid[2] <= 0.0 or grid[0] >= grid[1]:
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: neck_grid_rad must be (min, max, step) with min < max "
                "and a positive step"
            )
        object.__setattr__(self, "neck_grid_rad", grid)
        arm = tuple(
            _finite(f"validation_arm_rad[{index}]", value)
            for index, value in enumerate(self.validation_arm_rad)
        )
        if len(arm) != ARM_JOINT_COUNT:
            raise HeadCameraGeometryError(
                f"HEAD_CAMERA_CONTRACT_INVALID: validation_arm_rad must hold exactly "
                f"{ARM_JOINT_COUNT} joint angles"
            )
        object.__setattr__(self, "validation_arm_rad", arm)
        for name in (
            "coarse_step_candidate_rad",
            "safe_interval_margin_rad",
            "safe_bisection_tolerance_rad",
            "fov_tolerance_rad",
        ):
            object.__setattr__(self, name, _finite(name, getattr(self, name), positive=True))
        if type(self.visible_pixel_minimum) is not int or self.visible_pixel_minimum <= 0:
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: visible_pixel_minimum must be a positive integer"
            )
        object.__setattr__(
            self,
            "accepted_scene_sha256",
            _digest("accepted_scene_sha256", self.accepted_scene_sha256),
        )
        object.__setattr__(
            self,
            "accepted_camera_source_sha256",
            _digest("accepted_camera_source_sha256", self.accepted_camera_source_sha256),
        )
        if self.scene_path is not None:
            object.__setattr__(self, "scene_path", Path(self.scene_path))

    @property
    def camera_name(self) -> str:
        return self.camera.camera_name

    @property
    def image_width(self) -> int:
        return self.camera.width

    @property
    def image_height(self) -> int:
        return self.camera.height

    def horizontal_fov_rad(self) -> float:
        return self.camera.horizontal_fov_rad

    def neck_grid(self) -> tuple[float, ...]:
        """The closed grid over the approved envelope: both declared endpoints are in it."""

        low, high, step = self.neck_grid_rad
        count = int(math.floor((high - low) / step + _EPSILON))
        values = [low + step * index for index in range(count + 1)]
        if abs(values[-1] - high) > _EPSILON:
            values.append(high)
        return tuple(values)

    def workspace_points_m(self) -> tuple[tuple[float, float, float], ...]:
        x_low, x_high = self.workspace_x_m
        y_low, y_high = self.workspace_y_m
        z_low, z_high = self.workspace_z_m
        points: list[tuple[float, float, float]] = []
        for x in self._axis_values(x_low, x_high):
            for y in self._axis_values(y_low, y_high):
                points.append((x, y, (z_low + z_high) / 2.0))
        return tuple(points)

    def _axis_values(self, low: float, high: float) -> tuple[float, ...]:
        """Every sampled coordinate, always including both declared edges of the workspace."""

        count = int(math.floor((high - low) / self.workspace_step_m + _EPSILON))
        values = [low + self.workspace_step_m * index for index in range(count + 1)]
        if abs(values[-1] - high) > _EPSILON:
            values.append(high)
        return tuple(values)

    def to_document(self) -> dict[str, Any]:
        return {
            "scene_path": None if self.scene_path is None else str(self.scene_path),
            "camera": self.camera.to_document(),
            "neck_joint": self.neck_joint,
            "anchors": [anchor.to_document() for anchor in self.anchors],
            "workspace_x_m": list(self.workspace_x_m),
            "workspace_y_m": list(self.workspace_y_m),
            "workspace_z_m": list(self.workspace_z_m),
            "workspace_step_m": self.workspace_step_m,
            "neck_grid_rad": list(self.neck_grid_rad),
            "validation_arm_rad": list(self.validation_arm_rad),
            "coarse_step_candidate_rad": self.coarse_step_candidate_rad,
            "safe_interval_margin_rad": self.safe_interval_margin_rad,
            "safe_bisection_tolerance_rad": self.safe_bisection_tolerance_rad,
            "fov_tolerance_rad": self.fov_tolerance_rad,
            "visible_pixel_minimum": self.visible_pixel_minimum,
            "accepted_scene_sha256": self.accepted_scene_sha256,
            "accepted_camera_source_sha256": self.accepted_camera_source_sha256,
        }

    @classmethod
    def from_document(
        cls, document: Mapping[str, Any], *, scene_path: Path | None = None
    ) -> HeadCameraGeometryContract:
        allowed = set(CONTRACT_KEYS) | {"scene_path", "geometry_seal_digest"}
        if not isinstance(document, Mapping) or not set(document) <= allowed:
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: unknown keys in the geometry contract: "
                + ", ".join(sorted(set(document) - allowed))
            )
        missing = set(CONTRACT_KEYS) - set(document)
        if missing:
            raise HeadCameraGeometryError(
                "HEAD_CAMERA_CONTRACT_INVALID: missing keys in the geometry contract: "
                + ", ".join(sorted(missing))
            )
        return cls(
            camera=CameraDefinition.from_document(document["camera"]),
            neck_joint=document["neck_joint"],
            anchors=tuple(HeadCameraAnchor.from_document(item) for item in document["anchors"]),
            workspace_x_m=document["workspace_x_m"],
            workspace_y_m=document["workspace_y_m"],
            workspace_z_m=document["workspace_z_m"],
            workspace_step_m=document["workspace_step_m"],
            neck_grid_rad=document["neck_grid_rad"],
            validation_arm_rad=document["validation_arm_rad"],
            coarse_step_candidate_rad=document["coarse_step_candidate_rad"],
            safe_interval_margin_rad=document["safe_interval_margin_rad"],
            safe_bisection_tolerance_rad=document["safe_bisection_tolerance_rad"],
            fov_tolerance_rad=document["fov_tolerance_rad"],
            visible_pixel_minimum=document["visible_pixel_minimum"],
            accepted_scene_sha256=document["accepted_scene_sha256"],
            accepted_camera_source_sha256=document["accepted_camera_source_sha256"],
            scene_path=scene_path if scene_path is not None else document.get("scene_path"),
        )

    @classmethod
    def from_path(cls, path: Path) -> HeadCameraGeometryContract:
        contract_path = Path(path)
        if contract_path.is_symlink() or not contract_path.is_file():
            raise HeadCameraGeometryError(
                f"HEAD_CAMERA_CONTRACT_INVALID: contract must be a regular file: {contract_path}"
            )
        document = json.loads(contract_path.read_text(encoding="utf-8"))
        scene_path = None
        if isinstance(document, Mapping) and document.get("scene_path"):
            scene_path = (contract_path.parent / str(document["scene_path"])).resolve()
        return cls.from_document(document, scene_path=scene_path)


class HeadCameraScenePort(Protocol):
    """What the production MuJoCo scene must answer for the seal to be decided."""

    def camera_document(self) -> Mapping[str, Any]: ...

    def camera_world_pose(
        self, neck_rad: float
    ) -> tuple[Sequence[float], Sequence[Sequence[float]]]: ...

    def target_points_m(
        self, anchor: HeadCameraAnchor
    ) -> tuple[tuple[float, float, float], ...]: ...

    def neck_angle_for_point(self, point_m: Sequence[float]) -> float: ...

    def safe_at_neck(self, neck_rad: float) -> bool: ...

    def source_digests(self) -> Mapping[str, str]: ...

    def camera_mount_pose(self) -> tuple[Sequence[float], Sequence[float]]: ...

    def support_height_m(self) -> float: ...

    def target_rest_offset_m(self) -> float: ...

    def visible_pixels_for_point(self, point_m: Sequence[float], neck_rad: float) -> int: ...

    def endpoint_visibility(
        self, point_m: Sequence[float], neck_rad: float
    ) -> Mapping[str, Any]: ...

    def target_clear_of_support(self, point_m: Sequence[float]) -> bool: ...


@dataclass(frozen=True, slots=True)
class HeadCameraGeometryResult:
    camera_name: str
    image_width: int
    image_height: int
    horizontal_fov_rad: float
    camera: CameraDefinition
    validation_arm_rad: tuple[float, ...]
    camera_mount_origin_m: tuple[float, float, float]
    camera_mount_xyaxes: tuple[float, ...]
    anchors: tuple[str, ...]
    in_frame_matrix: Mapping[str, Mapping[str, Any]]
    in_frame_failures: tuple[Mapping[str, Any], ...]
    workspace_matrix: Mapping[str, Any]
    support_height_m: float
    required_search_domain_rad: tuple[float, float]
    lock_valid_neck_rad: tuple[float, float]
    safe_interval_contains_required_domain: bool
    fov_union_covers_required_domain: bool
    camera_source_sha256: str
    scene_sha256: str
    contract_sha256: str
    coarse_step_candidate_rad: float

    def to_document(self) -> dict[str, Any]:
        document = {
            "schema_version": SCHEMA_VERSION,
            "camera_name": self.camera_name,
            "image_width": self.image_width,
            "image_height": self.image_height,
            "horizontal_fov_rad": self.horizontal_fov_rad,
            "camera": self.camera.to_document(),
            "validation_arm_rad": list(self.validation_arm_rad),
            "camera_mount_origin_m": list(self.camera_mount_origin_m),
            "camera_mount_xyaxes": list(self.camera_mount_xyaxes),
            "anchors": list(self.anchors),
            "in_frame_matrix": {
                name: dict(record) for name, record in self.in_frame_matrix.items()
            },
            "in_frame_failures": [dict(record) for record in self.in_frame_failures],
            "workspace_matrix": dict(self.workspace_matrix),
            "support_height_m": self.support_height_m,
            "coarse_step_candidate_rad": self.coarse_step_candidate_rad,
            "required_search_domain_rad": list(self.required_search_domain_rad),
            "lock_valid_neck_rad": list(self.lock_valid_neck_rad),
            "safe_interval_contains_required_domain": self.safe_interval_contains_required_domain,
            "fov_union_covers_required_domain": self.fov_union_covers_required_domain,
            "source_digests": {
                "scene_sha256": self.scene_sha256,
                "camera_source_sha256": self.camera_source_sha256,
                "contract_sha256": self.contract_sha256,
            "coarse_step_candidate_rad": self.coarse_step_candidate_rad,
            },
        }
        document["seal_sha256"] = canonical_sha256(document)
        return document

    @property
    def sha256(self) -> str:
        return canonical_sha256(
            {key: value for key, value in self.to_document().items() if key != "seal_sha256"}
        )


def coverage_intervals_cover(
    intervals: Iterable[tuple[float, float]], domain: tuple[float, float]
) -> bool:
    low, high = domain
    merged: list[list[float]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1] + _EPSILON:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    for start, end in merged:
        if start <= low + _EPSILON and end >= high - _EPSILON:
            return True
    return False


def _coverage_stops(
    *, anchor_rad: float, domain: tuple[float, float], step_rad: float
) -> tuple[float, ...]:
    """The bounded two-way stop sequence: nearer endpoint first, one reversal, both endpoints hit."""

    low, high = domain
    anchor = min(max(anchor_rad, low), high)
    nearer = low if anchor - low <= high - anchor else high
    farther = high if nearer == low else low
    stops = [anchor]
    for target in (nearer, farther):
        direction = 1.0 if target >= stops[-1] else -1.0
        while abs(target - stops[-1]) > step_rad + _EPSILON:
            stops.append(stops[-1] + direction * step_rad)
        stops.append(target)
    return tuple(stops)


def _refine_boundary(
    port: HeadCameraScenePort, unsafe: float, safe: float, contract: HeadCameraGeometryContract
) -> float:
    tolerance = contract.safe_bisection_tolerance_rad
    low, high = (unsafe, safe) if unsafe < safe else (safe, unsafe)
    while high - low > tolerance:
        middle = (low + high) / 2.0
        if port.safe_at_neck(middle):
            if unsafe < safe:
                high = middle
            else:
                low = middle
        elif unsafe < safe:
            low = middle
        else:
            high = middle
    return high if unsafe < safe else low
