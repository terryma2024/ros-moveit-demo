"""The production head camera's frozen geometry contract and its seal.

The Head Search gate turns on one question the runtime cannot answer later: does the production head
camera actually see the cup's support geometry at all three anchors, over a neck interval that is
provably safe? The dataset images, the search trajectory and the qualification scenes all inherit
whatever answer this module produces, so the answer is a sealed document rather than a claim.

Two layers live here. The pure layer owns the contract, the projection maths, the required search
domain and every acceptance rule; it never imports MuJoCo. The model layer is a port - the production
`MuJoCoHeadCameraScene` supplies camera poses, safe angles, target points and rendered visibility -
so the rules are testable without a GL context and the same rules run against the real scene at the
Task 11 boundary.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Protocol

from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
_EPSILON = 1e-9
#: the six arm joints, in the order the MJCF names them
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


def validate_head_camera_geometry(
    scene_path: Path | str,
    contract: HeadCameraGeometryContract,
    *,
    scene_port: HeadCameraScenePort | None = None,
) -> HeadCameraGeometryResult:
    """Decide every acceptance rule and return the sealed geometry document."""

    scene = Path(scene_path)
    port = _MuJoCoHeadCameraScene(scene, contract) if scene_port is None else scene_port

    digests = dict(port.source_digests())
    scene_sha256 = str(digests.get("scene_sha256", ""))
    camera_source_sha256 = str(digests.get("camera_source_sha256", ""))
    if camera_source_sha256 != contract.accepted_camera_source_sha256 or (
        scene_sha256 != contract.accepted_scene_sha256
    ):
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_SOURCE_DRIFT: the camera source or scene digest changed: "
            f"scene={scene_sha256[:12]} camera={camera_source_sha256[:12]}"
        )

    observed = CameraDefinition.from_document(port.camera_document())
    frozen = contract.camera
    if (
        observed.camera_name != frozen.camera_name
        or observed.width != frozen.width
        or observed.height != frozen.height
        or observed.parent_body != frozen.parent_body
        or abs(observed.fovy_rad - frozen.fovy_rad) > contract.fov_tolerance_rad
        or observed.distortion_model != frozen.distortion_model
        or any(
            abs(observed.distortion[index] - frozen.distortion[index]) > contract.fov_tolerance_rad
            for index in range(5)
        )
        or any(
            abs(observed.local_position_m[index] - frozen.local_position_m[index])
            > contract.fov_tolerance_rad
            for index in range(3)
        )
        or any(
            abs(observed.local_xyaxes[index] - frozen.local_xyaxes[index])
            > contract.fov_tolerance_rad
            for index in range(6)
        )
    ):
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_DEFINITION_DRIFT: the scene's camera definition no longer matches the "
            "contract"
        )

    horizontal_fov = observed.horizontal_fov_rad
    if abs(horizontal_fov - frozen.horizontal_fov_rad) > contract.fov_tolerance_rad:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_DEFINITION_DRIFT: the observed horizontal field of view differs from the "
            "contract"
        )

    half_fov = horizontal_fov / 2.0
    if contract.coarse_step_candidate_rad > half_fov + contract.fov_tolerance_rad:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_STEP_EXCEEDS_HALF_FOV: the candidate coarse step "
            f"{contract.coarse_step_candidate_rad} exceeds half the horizontal field of view "
            f"{half_fov}; consecutive stops would leave uncovered gaps"
        )

    support_height = float(port.support_height_m())
    resting_height = support_height + float(port.target_rest_offset_m())
    workspace_low_z, workspace_high_z = contract.workspace_z_m
    if not workspace_low_z - 1e-3 <= resting_height <= workspace_high_z + 1e-3:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_WORKSPACE_UNSUPPORTED: the declared workspace heights "
            f"[{workspace_low_z}, {workspace_high_z}] do not contain the model's resting target "
            f"height {resting_height} above the support at {support_height}"
        )

    workspace_points = _workspace_matrix_points(contract)
    bearings = [port.neck_angle_for_point(point) for point in workspace_points]
    required_domain = (min(bearings), max(bearings))

    safe_interval = _safe_interval(port, contract)
    if safe_interval is None:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_SAFE_INTERVAL_INVALID: no unique safe interval contains the zero position "
            "and all three anchor start angles"
        )
    lock_valid_neck_rad = safe_interval
    contains_domain = (
        lock_valid_neck_rad[0] <= required_domain[0] + _EPSILON
        and required_domain[1] <= lock_valid_neck_rad[1] + _EPSILON
    )
    if not contains_domain:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_REQUIRED_DOMAIN_UNCOVERED: the required search domain "
            f"{required_domain} is not inside the safe interval {lock_valid_neck_rad}"
        )

    intervals: list[tuple[float, float]] = []
    for anchor in contract.anchors:
        for stop in _coverage_stops(
            anchor_rad=anchor.neck_start_rad,
            domain=required_domain,
            step_rad=contract.coarse_step_candidate_rad,
        ):
            if not port.safe_at_neck(stop):
                raise HeadCameraGeometryError(
                    f"HEAD_CAMERA_SWEEP_UNSAFE: stop {stop} for anchor {anchor.name} is outside the "
                    "safe interval"
                )
            intervals.append((stop - half_fov, stop + half_fov))
    covers_domain = coverage_intervals_cover(intervals, required_domain)
    if not covers_domain:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_FOV_UNION_INCOMPLETE: the coarse stops' field-of-view union does not cover "
            f"the required search domain {required_domain}"
        )

    matrix: dict[str, Mapping[str, Any]] = {}
    failures: list[Mapping[str, Any]] = []
    for anchor in contract.anchors:
        centre_angle = port.neck_angle_for_point(anchor.cup_start_m)
        target_points = tuple(port.target_points_m(anchor))
        if not target_points:
            raise HeadCameraGeometryError(
                f"HEAD_CAMERA_TARGET_GEOMETRY_MISSING: anchor {anchor.name} has no target points"
            )
        samples = []
        out_of_frame: list[float] = []
        for angle in (anchor.neck_start_rad, centre_angle):
            position, rotation = port.camera_world_pose(angle)
            projected = [
                project_point(
                    point_m=point,
                    camera_position_m=position,
                    camera_rotation=rotation,
                    width=observed.width,
                    height=observed.height,
                    fovy_rad=observed.fovy_rad,
                )
                for point in target_points
            ]
            inside = all(item[2] for item in projected)
            visible = None
            if hasattr(port, "visible_pixels"):
                visible = port.visible_pixels(anchor, angle)  # type: ignore[attr-defined]
            visible_ok = visible is None or int(visible) >= contract.visible_pixel_minimum
            in_frame = bool(inside and visible_ok)
            sample = {
                "neck_rad": angle,
                "in_frame": in_frame,
                "projected_points_in_frame": sum(1 for item in projected if item[2]),
                "projected_points": len(projected),
                "visible_pixels": None if visible is None else int(visible),
            }
            if not in_frame:
                out_of_frame.append(angle)
                failures.append({"anchor": anchor.name, **sample})
            samples.append(sample)
        matrix[anchor.name] = {
            "neck_start_rad": anchor.neck_start_rad,
            "centre_angle_rad": centre_angle,
            "samples": samples,
            "out_of_frame_rad": out_of_frame,
        }

    if failures:
        first = failures[0]
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_IN_FRAME_FAILURE: anchor "
            f"{first['anchor']} does not see its target at neck {first['neck_rad']} "
            f"({first['projected_points_in_frame']}/{first['projected_points']} points in frame, "
            f"{first['visible_pixels']} visible pixels)"
        )

    mount_origin, mount_xyaxes = _camera_mount_model(port, contract)
    workspace_matrix, key_samples = _evaluate_workspace_matrix(
        port, contract, observed, workspace_points, required_domain
    )

    return HeadCameraGeometryResult(
        coarse_step_candidate_rad=contract.coarse_step_candidate_rad,
        camera_name=observed.camera_name,
        image_width=observed.width,
        image_height=observed.height,
        horizontal_fov_rad=horizontal_fov,
        camera=observed,
        validation_arm_rad=contract.validation_arm_rad,
        camera_mount_origin_m=mount_origin,
        camera_mount_xyaxes=mount_xyaxes,
        workspace_matrix=workspace_matrix,
        support_height_m=support_height,
        anchors=tuple(anchor.name for anchor in contract.anchors),
        in_frame_matrix=MappingProxyType(matrix),
        in_frame_failures=(),
        required_search_domain_rad=required_domain,
        lock_valid_neck_rad=lock_valid_neck_rad,
        safe_interval_contains_required_domain=True,
        fov_union_covers_required_domain=True,
        camera_source_sha256=camera_source_sha256,
        scene_sha256=scene_sha256,
        contract_sha256=canonical_sha256(contract.to_document()),
    )


def _safe_interval(
    port: HeadCameraScenePort, contract: HeadCameraGeometryContract
) -> tuple[float, float] | None:
    grid = contract.neck_grid()
    safe_flags = [bool(port.safe_at_neck(angle)) for angle in grid]
    starts = [0.0] + [anchor.neck_start_rad for anchor in contract.anchors]
    required_indices = {
        min(range(len(grid)), key=lambda index: abs(grid[index] - start)) for start in starts
    }
    if any(not safe_flags[index] for index in required_indices):
        return None

    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(grid):
        if not safe_flags[index]:
            index += 1
            continue
        start_index = index
        while index + 1 < len(grid) and safe_flags[index + 1]:
            index += 1
        runs.append((start_index, index))
        index += 1

    containing = [run for run in runs if all(run[0] <= item <= run[1] for item in required_indices)]
    if len(containing) != 1:
        return None
    start_index, end_index = containing[0]
    low = grid[start_index]
    high = grid[end_index]
    if start_index > 0:
        low = _refine_boundary(port, grid[start_index - 1], grid[start_index], contract)
    if end_index + 1 < len(grid):
        high = _refine_boundary(port, grid[end_index + 1], grid[end_index], contract)
    margin = contract.safe_interval_margin_rad
    return (low + margin, high - margin)


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


class _MuJoCoHeadCameraScene:
    """The production scene, read through MuJoCo: poses, safety, target points and rendered visibility."""

    def __init__(self, scene_path: Path, contract: HeadCameraGeometryContract) -> None:
        import mujoco

        scene = Path(scene_path)
        if not scene.is_file():
            raise HeadCameraGeometryError(f"HEAD_CAMERA_SCENE_MISSING: {scene}")
        self._mujoco = mujoco
        self._scene = scene
        self._contract = contract
        self._model = mujoco.MjModel.from_xml_path(str(scene))
        self._data = mujoco.MjData(self._model)
        self._camera_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_CAMERA, contract.camera_name
        )
        if self._camera_id < 0:
            raise HeadCameraGeometryError(
                f"HEAD_CAMERA_CAMERA_MISSING: {contract.camera_name} is not in {scene}"
            )
        self._neck_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_JOINT, contract.neck_joint
        )
        if self._neck_id < 0:
            raise HeadCameraGeometryError(
                f"HEAD_CAMERA_NECK_MISSING: {contract.neck_joint} is not in {scene}"
            )
        self._neck_qpos_adr = int(self._model.jnt_qposadr[self._neck_id])
        self._arm_qpos_adr = []
        for joint_name in ARM_JOINT_NAMES:
            joint_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
            if joint_id < 0:
                raise HeadCameraGeometryError(
                    f"HEAD_CAMERA_ARM_JOINT_MISSING: the scene names no joint {joint_name!r}"
                )
            limit = self._model.jnt_range[joint_id]
            value = float(contract.validation_arm_rad[len(self._arm_qpos_adr)])
            if not float(limit[0]) - 1e-9 <= value <= float(limit[1]) + 1e-9:
                raise HeadCameraGeometryError(
                    f"HEAD_CAMERA_ARM_POSE_INVALID: joint {joint_name} at {value} is outside "
                    f"[{float(limit[0])}, {float(limit[1])}]"
                )
            self._arm_qpos_adr.append(int(self._model.jnt_qposadr[joint_id]))
        self._cup_body_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_BODY, "plastic_cup")
        if self._cup_body_id < 0:
            raise HeadCameraGeometryError("HEAD_CAMERA_TARGET_GEOMETRY_MISSING: plastic_cup")
        self._cup_joint_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint"
        )
        self._cup_qpos_adr = (
            0 if self._cup_joint_id < 0 else int(self._model.jnt_qposadr[self._cup_joint_id])
        )
        self._renderer = None
        self._segmentation_renderer = None
        self._robot_bodies = self._descendants_of_robot()
        self._prepare_clearance()

    def source_digests(self) -> Mapping[str, str]:
        return scene_source_digests(self._scene)

    def camera_document(self) -> Mapping[str, Any]:
        model = self._model
        camera_id = self._camera_id
        fovy = float(model.cam_fovy[camera_id]) * math.pi / 180.0
        position = [float(value) for value in model.cam_pos[camera_id]]
        rotation = [float(value) for value in model.cam_mat0[camera_id].reshape(9)]
        axes = [
            rotation[0],
            rotation[3],
            rotation[6],
            rotation[1],
            rotation[4],
            rotation[7],
        ]
        body_name = self._mujoco.mj_id2name(
            model, self._mujoco.mjtObj.mjOBJ_BODY, int(model.cam_bodyid[camera_id])
        )
        return {
            "camera_name": self._contract.camera_name,
            "width": int(model.cam_resolution[camera_id][0]),
            "height": int(model.cam_resolution[camera_id][1]),
            "fovy_rad": fovy,
            "distortion_model": DISTORTION_MODEL,
            "distortion": list(DISTORTION_COEFFICIENTS),
            "parent_body": str(body_name),
            "local_position_m": position,
            "local_xyaxes": axes,
        }

    def _pose_neck(self, neck_rad: float) -> None:
        self._mujoco.mj_resetData(self._model, self._data)
        for index, joint_name in enumerate(ARM_JOINT_NAMES):
            self._data.qpos[self._arm_qpos_adr[index]] = float(
                self._contract.validation_arm_rad[index]
            )
        self._data.qpos[self._neck_qpos_adr] = float(neck_rad)
        if self._cup_joint_id >= 0:
            # the anchor's own cup position is set by `target_points_m`; here the model is advanced
            # with the neck exactly where the caller asked for it
            pass
        self._mujoco.mj_forward(self._model, self._data)

    def camera_world_pose(self, neck_rad: float):
        self._pose_neck(neck_rad)
        position = [float(value) for value in self._data.cam_xpos[self._camera_id]]
        rotation = [
            [float(value) for value in row]
            for row in self._data.cam_xmat[self._camera_id].reshape(3, 3)
        ]
        return (position, rotation)

    def target_points_m(self, anchor: HeadCameraAnchor) -> tuple[tuple[float, float, float], ...]:
        self._pose_neck(anchor.neck_start_rad)
        if self._cup_joint_id >= 0:
            self._data.qpos[self._cup_qpos_adr : self._cup_qpos_adr + 3] = anchor.cup_start_m
            self._data.qpos[self._cup_qpos_adr + 3 : self._cup_qpos_adr + 7] = (1.0, 0.0, 0.0, 0.0)
            self._mujoco.mj_forward(self._model, self._data)
        minima = [math.inf] * 3
        maxima = [-math.inf] * 3
        for index in range(self._model.ngeom):
            if int(self._model.geom_bodyid[index]) != self._cup_body_id:
                continue
            centre = [float(value) for value in self._data.geom_xpos[index]]
            radius = float(max(self._model.geom_size[index]))
            for axis in range(3):
                minima[axis] = min(minima[axis], centre[axis] - radius)
                maxima[axis] = max(maxima[axis], centre[axis] + radius)
        points = [tuple((minima[axis] + maxima[axis]) / 2.0 for axis in range(3))]
        for x in (minima[0], maxima[0]):
            for y in (minima[1], maxima[1]):
                for z in (minima[2], maxima[2]):
                    points.append((x, y, z))
        return tuple(points)

    def neck_angle_for_point(self, point_m: Sequence[float]) -> float:
        self._pose_neck(0.0)
        mount = self._data.xpos[self._model.cam_bodyid[self._camera_id]]
        return math.atan2(
            float(point_m[0]) - float(mount[0]), -(float(point_m[1]) - float(mount[1]))
        )

    def safe_at_neck(self, neck_rad: float) -> bool:
        self._pose_neck(neck_rad)
        data = self._data
        for index in range(int(data.ncon)):
            contact = data.contact[index]
            if self._is_head_geom(int(contact.geom1)) or self._is_head_geom(int(contact.geom2)):
                return False
        margin = 0.005
        for index in self._head_geoms:
            centre = data.geom_xpos[index]
            radius = float(self._geom_radius[index])
            for other in self._clearance_candidates[index]:
                other_centre = data.geom_xpos[other]
                reach = radius + float(self._geom_radius[other]) + margin
                if (centre[0] - other_centre[0]) ** 2 + (centre[1] - other_centre[1]) ** 2 + (
                    centre[2] - other_centre[2]
                ) ** 2 > reach * reach:
                    continue
                if (
                    self._mujoco.mj_geomDistance(self._model, data, index, other, margin, None)
                    < margin - 1e-9
                ):
                    return False
        return True

    def _descendants_of_robot(self) -> frozenset[int]:
        """Every body that belongs to the robot the head camera is mounted on."""

        base_id = self._mujoco.mj_name2id(self._model, self._mujoco.mjtObj.mjOBJ_BODY, "base")
        if base_id < 0:
            return frozenset()
        bodies = set()
        for body in range(self._model.nbody):
            ancestor = body
            while ancestor > 0 and ancestor != base_id:
                ancestor = int(self._model.body_parentid[ancestor])
            if ancestor == base_id:
                bodies.add(body)
        return frozenset(bodies)

    def _prepare_clearance(self) -> None:
        """The static candidate pairs: geoms the rotating head could come within the margin of."""

        model = self._model
        data = self._data
        self._pose_neck(0.0)
        self._geom_radius = [
            float(max(model.geom_size[index]))
            if float(max(model.geom_size[index])) > 0.0
            else 0.001
            for index in range(model.ngeom)
        ]
        self._head_geoms = [index for index in range(model.ngeom) if self._is_head_geom(index)]
        axis = data.xpos[int(model.cam_bodyid[self._camera_id])]
        head_reach = max(
            (
                float(
                    (
                        (float(data.geom_xpos[index][0]) - float(axis[0])) ** 2
                        + (float(data.geom_xpos[index][1]) - float(axis[1])) ** 2
                    )
                    ** 0.5
                )
                + self._geom_radius[index]
                for index in self._head_geoms
            ),
            default=0.05,
        )
        self._clearance_candidates = {}
        for index in self._head_geoms:
            candidates = []
            for other in range(model.ngeom):
                if other == index or self._is_head_geom(other):
                    continue
                radial = (
                    (float(data.geom_xpos[other][0]) - float(axis[0])) ** 2
                    + (float(data.geom_xpos[other][1]) - float(axis[1])) ** 2
                ) ** 0.5
                if radial <= head_reach + self._geom_radius[other] + 0.02:
                    candidates.append(other)
            self._clearance_candidates[index] = tuple(candidates)

    def _is_head_geom(self, geom_id: int) -> bool:
        body = int(self._model.geom_bodyid[geom_id])
        head_body = int(self._model.cam_bodyid[self._camera_id])
        while body != 0 and body != head_body:
            body = int(self._model.body_parentid[body])
        return body == head_body

    def camera_mount_pose(self) -> tuple[Sequence[float], Sequence[float]]:
        """The mount body's world origin and its x/y axes at neck zero: the pose model of the seal."""

        self._pose_neck(0.0)
        body_id = int(self._model.cam_bodyid[self._camera_id])
        origin = [float(value) for value in self._data.xpos[body_id]]
        matrix = self._data.xmat[body_id].reshape(3, 3)
        axes = [
            float(matrix[0][0]),
            float(matrix[1][0]),
            float(matrix[2][0]),
            float(matrix[0][1]),
            float(matrix[1][1]),
            float(matrix[2][1]),
        ]
        return (origin, axes)

    def support_height_m(self) -> float:
        """The support surface the workspace rests on, read from the scene's own table geom."""

        self._pose_neck(0.0)
        for name in ("table_visual", "table_collision"):
            geom_id = self._mujoco.mj_name2id(self._model, self._mujoco.mjtObj.mjOBJ_GEOM, name)
            if geom_id >= 0:
                return float(self._data.geom_xpos[geom_id][2]) + float(
                    self._model.geom_size[geom_id][2]
                )
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_SUPPORT_MISSING: the scene names no support geom (table_visual)"
        )

    def target_rest_offset_m(self) -> float:
        """How high the target's centre sits above that support when it rests on it."""

        self._pose_neck(0.0)
        return float(self._data.xpos[self._cup_body_id][2]) - self.support_height_m()

    def visible_pixels_for_point(self, point_m: Sequence[float], neck_rad: float) -> int:
        return self._render_cup_pixels(tuple(float(value) for value in point_m), float(neck_rad))

    def endpoint_visibility(self, point_m: Sequence[float], neck_rad: float) -> Mapping[str, Any]:
        """Is the required-domain endpoint visible to this camera, robot pose aside?

        The ray is cast from the camera to the point with the camera's own body excluded. If the first
        thing it meets is the target, the endpoint is visible; if it is the robot, then only the robot
        the camera rides on stands in the way, and whether the arm is there is a property of the
        admitted trajectory rather than of this camera. Anything else in between is a real occlusion.
        """

        import numpy as np

        self._pose_neck(neck_rad)
        origin = np.array(self._data.cam_xpos[self._camera_id], dtype=np.float64)
        target = np.array([float(value) for value in point_m], dtype=np.float64)
        direction = target - origin
        distance = float(np.linalg.norm(direction))
        if distance <= 0.0:
            return {"first_hit_body": None, "visible_to_camera": False, "robot_occluded": False}
        direction = direction / distance
        hit_geom = np.zeros(1, dtype=np.int32)
        reached = self._mujoco.mj_ray(
            self._model,
            self._data,
            origin,
            direction,
            None,
            1,
            int(self._model.cam_bodyid[self._camera_id]),
            hit_geom,
        )
        if reached <= 0.0 or reached >= distance - 1e-9:
            # the open top of a cup means a ray to its centre may meet nothing before the centre, and
            # whatever it meets beyond the centre is not between the camera and the target
            return {"first_hit_body": None, "visible_to_camera": True, "robot_occluded": False}
        geom_id = int(hit_geom[0])
        body_id = int(self._model.geom_bodyid[geom_id])
        body_name = self._mujoco.mj_id2name(self._model, self._mujoco.mjtObj.mjOBJ_BODY, body_id)
        robot_occluded = body_id in self._robot_bodies
        return {
            "first_hit_body": None if body_name is None else str(body_name),
            "visible_to_camera": body_id == self._cup_body_id or robot_occluded,
            "robot_occluded": robot_occluded,
        }

    def target_clear_of_support(self, point_m: Sequence[float]) -> bool:
        """Would the target at this point intersect what it is supposed to rest on?"""

        self._place_cup(point_m)
        for index in range(int(self._data.ncon)):
            contact = self._data.contact[index]
            for geom_id in (int(contact.geom1), int(contact.geom2)):
                if int(self._model.geom_bodyid[geom_id]) == self._cup_body_id:
                    return False
        return True

    def _place_cup(self, point_m: Sequence[float]) -> None:
        self._pose_neck(0.0)
        if self._cup_joint_id >= 0:
            self._data.qpos[self._cup_qpos_adr : self._cup_qpos_adr + 3] = [
                float(value) for value in point_m
            ]
            self._data.qpos[self._cup_qpos_adr + 3 : self._cup_qpos_adr + 7] = (1.0, 0.0, 0.0, 0.0)
            self._mujoco.mj_forward(self._model, self._data)

    def visible_pixels(self, anchor: HeadCameraAnchor, neck_rad: float) -> int:
        return self._render_cup_pixels(anchor.cup_start_m, float(neck_rad))

    def _render_cup_pixels(self, cup_position_m: Sequence[float], neck_rad: float) -> int:
        import numpy as np

        self._pose_neck(neck_rad)
        if self._cup_joint_id >= 0:
            self._data.qpos[self._cup_qpos_adr : self._cup_qpos_adr + 3] = cup_position_m
            self._data.qpos[self._cup_qpos_adr + 3 : self._cup_qpos_adr + 7] = (1.0, 0.0, 0.0, 0.0)
            self._mujoco.mj_forward(self._model, self._data)
        if self._segmentation_renderer is None:
            self._segmentation_renderer = self._mujoco.Renderer(
                self._model,
                height=self._contract.image_height,
                width=self._contract.image_width,
            )
        self._segmentation_renderer.enable_segmentation_rendering()
        try:
            self._segmentation_renderer.update_scene(self._data, camera=self._contract.camera_name)
            segmentation = np.asarray(self._segmentation_renderer.render())
        finally:
            self._segmentation_renderer.disable_segmentation_rendering()
        geom_type = int(self._mujoco.mjtObj.mjOBJ_GEOM)
        # the object-ID render puts the type in one channel and the id in the other, and which is
        # which is not fixed - the same reading the dataset renderer uses
        first_is_type = segmentation[:, :, 0] == geom_type
        second_is_type = segmentation[:, :, 1] == geom_type
        ids = np.full(segmentation.shape[:2], -1, dtype=np.int32)
        if int(first_is_type.sum()) >= int(second_is_type.sum()):
            ids[first_is_type] = segmentation[:, :, 1][first_is_type]
        else:
            ids[second_is_type] = segmentation[:, :, 0][second_is_type]
        mask = np.zeros(segmentation.shape[:2], dtype=bool)
        for index in range(self._model.ngeom):
            if int(self._model.geom_bodyid[index]) == self._cup_body_id:
                mask |= ids == index
        return int(mask.sum())


def camera_pose_from_seal(
    seal: Mapping[str, Any], neck_rad: float
) -> tuple[tuple[float, float, float], tuple[float, ...]]:
    """The world pose the sealed camera must be at for one neck angle.

    The neck rotates the mount about the world z axis through the sealed mount origin, so the camera's
    world position and orientation follow from the sealed local definition alone. A dataset render or a
    manifest that reports any other pose is describing a camera this seal does not cover.
    """

    origin = [float(value) for value in seal["camera_mount_origin_m"]]
    mount = [float(value) for value in seal["camera_mount_xyaxes"]]
    camera = seal["camera"]
    local_position = [float(value) for value in camera["local_position_m"]]
    local_axes = [float(value) for value in camera["local_xyaxes"]]
    cosine, sine = math.cos(float(neck_rad)), math.sin(float(neck_rad))
    rotation = ((cosine, -sine, 0.0), (sine, cosine, 0.0), (0.0, 0.0, 1.0))
    mount_x = (mount[0], mount[1], mount[2])
    mount_y = (mount[3], mount[4], mount[5])
    mount_z = (
        mount_x[1] * mount_y[2] - mount_x[2] * mount_y[1],
        mount_x[2] * mount_y[0] - mount_x[0] * mount_y[2],
        mount_x[0] * mount_y[1] - mount_x[1] * mount_y[0],
    )
    mount_columns = (mount_x, mount_y, mount_z)
    offset = [
        sum(mount_columns[column][row] * local_position[column] for column in range(3))
        for row in range(3)
    ]
    position = [
        origin[row] + sum(rotation[row][column] * offset[column] for column in range(3))
        for row in range(3)
    ]
    axes = []
    for local_axis in (
        (local_axes[0], local_axes[1], local_axes[2]),
        (local_axes[3], local_axes[4], local_axes[5]),
    ):
        in_mount = [
            sum(mount_columns[column][row] * local_axis[column] for column in range(3))
            for row in range(3)
        ]
        axes.append(
            tuple(
                sum(rotation[row][column] * in_mount[column] for column in range(3))
                for row in range(3)
            )
        )
    return (
        tuple(position),
        (
            axes[0][0],
            axes[0][1],
            axes[0][2],
            axes[1][0],
            axes[1][1],
            axes[1][2],
        ),
    )


def _camera_mount_model(
    port: HeadCameraScenePort, contract: HeadCameraGeometryContract
) -> tuple[tuple[float, float, float], tuple[float, ...]]:
    pose = getattr(port, "camera_mount_pose", None)
    if pose is None:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_MOUNT_MODEL_MISSING: the scene cannot report the mount the camera rides on"
        )
    origin, axes = pose()
    return (
        tuple(float(value) for value in origin),
        tuple(float(value) for value in axes),
    )


def _workspace_matrix_points(
    contract: HeadCameraGeometryContract,
) -> tuple[tuple[float, float, float], ...]:
    """Every declared workspace sample at every declared height, not just its mid plane."""

    x_low, x_high = contract.workspace_x_m
    y_low, y_high = contract.workspace_y_m
    z_low, z_high = contract.workspace_z_m
    heights = (z_low, (z_low + z_high) / 2.0, z_high)
    points: list[tuple[float, float, float]] = []
    for x in contract._axis_values(x_low, x_high):
        for y in contract._axis_values(y_low, y_high):
            for z in heights:
                points.append((x, y, z))
    return tuple(points)


def _evaluate_workspace_matrix(
    port: HeadCameraScenePort,
    contract: HeadCameraGeometryContract,
    camera: CameraDefinition,
    workspace_points: tuple[tuple[float, float, float], ...],
    required_domain: tuple[float, float],
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    """Every workspace sample must be inside the frame when the neck points at it.

    Projection decides the whole matrix; the samples that carry the required domain's endpoints are
    additionally rendered, so the occluders the scene actually contains are part of the evidence and
    not an assumption about them.
    """

    records = []
    embedded = []
    for point in workspace_points:
        if not bool(port.target_clear_of_support(point)):
            embedded.append({"point_m": list(point)})
            continue
        neck = port.neck_angle_for_point(point)
        position, rotation = port.camera_world_pose(neck)
        u, v, inside = project_point(
            point_m=point,
            camera_position_m=position,
            camera_rotation=rotation,
            width=camera.width,
            height=camera.height,
            fovy_rad=camera.fovy_rad,
        )
        records.append(
            {
                "point_m": list(point),
                "neck_rad": neck,
                "u": u,
                "v": v,
                "in_frame": bool(inside),
                "visible_pixels": None,
            }
        )
    endpoints = [
        min(records, key=lambda record: record["neck_rad"]),
        max(records, key=lambda record: record["neck_rad"]),
    ]
    anchor_samples = [
        {
            "point_m": list(anchor.cup_start_m),
            "neck_rad": port.neck_angle_for_point(anchor.cup_start_m),
            "anchor": anchor.name,
        }
        for anchor in contract.anchors
    ]
    key_records = []
    failures = []
    for record in endpoints + anchor_samples:
        neck = float(record["neck_rad"])
        point = tuple(record["point_m"])
        kind = "anchor" if "anchor" in record else "required_domain_endpoint"
        visible = int(port.visible_pixels_for_point(point, neck))
        # every key sample - the three anchors and both required-domain endpoints - must be rendered
        # visible in the scene as it stands, at the arm pose this contract declares. A target the
        # camera cannot put pixels on is not a target the search can find.
        sight = dict(port.endpoint_visibility(point, neck))
        key = {
            **record,
            "kind": kind,
            "visible_pixels": visible,
            "first_hit_body": sight.get("first_hit_body"),
            "in_frame": visible >= contract.visible_pixel_minimum,
        }
        key_records.append(key)
        if key["in_frame"] is False:
            failures.append(key)
    if embedded:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_WORKSPACE_EMBEDDED: "
            f"{len(embedded)} declared workspace samples put the target inside the support; first is "
            f"{embedded[0]['point_m']}"
        )
    out_of_frame = [record for record in records if not record["in_frame"]]
    if out_of_frame or failures:
        first = (out_of_frame or failures)[0]
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_WORKSPACE_MATRIX_INCOMPLETE: "
            f"{len(out_of_frame)} of {len(records)} workspace samples are outside the frame and "
            f"{len(failures)} key samples are not visibly rendered; first is {first}"
        )
    matrix = {
        "samples": len(records),
        "in_frame": len(records) - len(out_of_frame),
        "rendered_key_samples": len(key_records),
        "key_samples": key_records,
        "min_rendered_visible_pixels": min(int(record["visible_pixels"]) for record in key_records),
        "min_anchor_visible_pixels": min(
            int(record["visible_pixels"]) for record in key_records if record["kind"] == "anchor"
        ),
        "required_domain_rad": [required_domain[0], required_domain[1]],
    }
    return (MappingProxyType(matrix), key_records)


def quaternion_wxyz_from_xyaxes(xyaxes: object) -> tuple[float, float, float, float]:
    """The unit quaternion (w, x, y, z) of the rotation two frame axes describe.

    MuJoCo hands a camera's orientation around as the x and y axes of its frame; a manifest records it
    as a quaternion. This is the one conversion between them, so a recorded pose can be compared with
    the pose the seal predicts instead of merely being finite.
    """

    values = [float(value) for value in xyaxes]  # type: ignore[union-attr]
    x_axis = values[0:3]
    y_axis = values[3:6]
    z_axis = [
        x_axis[1] * y_axis[2] - x_axis[2] * y_axis[1],
        x_axis[2] * y_axis[0] - x_axis[0] * y_axis[2],
        x_axis[0] * y_axis[1] - x_axis[1] * y_axis[0],
    ]
    matrix = (
        (x_axis[0], y_axis[0], z_axis[0]),
        (x_axis[1], y_axis[1], z_axis[1]),
        (x_axis[2], y_axis[2], z_axis[2]),
    )
    trace = matrix[0][0] + matrix[1][1] + matrix[2][2]
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        quaternion = (
            0.25 * scale,
            (matrix[2][1] - matrix[1][2]) / scale,
            (matrix[0][2] - matrix[2][0]) / scale,
            (matrix[1][0] - matrix[0][1]) / scale,
        )
    elif matrix[0][0] > matrix[1][1] and matrix[0][0] > matrix[2][2]:
        scale = math.sqrt(1.0 + matrix[0][0] - matrix[1][1] - matrix[2][2]) * 2.0
        quaternion = (
            (matrix[2][1] - matrix[1][2]) / scale,
            0.25 * scale,
            (matrix[0][1] + matrix[1][0]) / scale,
            (matrix[0][2] + matrix[2][0]) / scale,
        )
    elif matrix[1][1] > matrix[2][2]:
        scale = math.sqrt(1.0 + matrix[1][1] - matrix[0][0] - matrix[2][2]) * 2.0
        quaternion = (
            (matrix[0][2] - matrix[2][0]) / scale,
            (matrix[0][1] + matrix[1][0]) / scale,
            0.25 * scale,
            (matrix[1][2] + matrix[2][1]) / scale,
        )
    else:
        scale = math.sqrt(1.0 + matrix[2][2] - matrix[0][0] - matrix[1][1]) * 2.0
        quaternion = (
            (matrix[1][0] - matrix[0][1]) / scale,
            (matrix[0][2] + matrix[2][0]) / scale,
            (matrix[1][2] + matrix[2][1]) / scale,
            0.25 * scale,
        )
    norm = math.sqrt(sum(value * value for value in quaternion))
    if not math.isfinite(norm) or norm <= 0.0:
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_ORIENTATION_INVALID: the axes are not a rotation"
        )
    return (
        quaternion[0] / norm,
        quaternion[1] / norm,
        quaternion[2] / norm,
        quaternion[3] / norm,
    )
