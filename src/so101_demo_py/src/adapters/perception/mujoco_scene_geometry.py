"""Measured task-solid nonpenetration for offline dataset generation only.

This is not a robot reachability or runtime grasp eligibility certificate.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from itertools import combinations, product
from typing import Any

import numpy as np

_CUP_WALL_STEMS = (
    "wall_near",
    "wall_01",
    "wall_02",
    "wall_03",
    "wall_04",
    "wall_05",
    "wall_opposite",
    "wall_07",
    "wall_08",
    "wall_09",
    "wall_10",
    "wall_11",
)
_TASK_GEOMETRY_SCHEMA = {
    "plastic_cup": (
        tuple(f"cup_a_{stem}_visual" for stem in _CUP_WALL_STEMS)
        + ("cup_a_bottom_visual",),
        tuple(f"cup_a_{stem}_collision" for stem in _CUP_WALL_STEMS)
        + ("cup_a_bottom_collision",),
    ),
    "plastic_cup_b": (
        tuple(f"cup_b_{stem}_visual" for stem in _CUP_WALL_STEMS)
        + ("cup_b_bottom_visual",),
        ("cup_b_collision",),
    ),
    "orange_bottle": (
        ("bottle_visual", "bottle_neck_visual"),
        ("bottle_collision",),
    ),
    "table": (("table_visual",), ("table_collision",)),
    "neutral_block": (("neutral_block_visual",), ("neutral_block_collision",)),
    "base_pedestal": (("base_pedestal_visual",), ("base_pedestal_collision",)),
}
_DEFAULT_GEOM_RGBA = np.array((0.5, 0.5, 0.5, 1.0))


class ScenePenetrationError(RuntimeError):
    """A measured penetrating scene may be retried with a new deterministic draw."""

    def __init__(
        self,
        message: str,
        *,
        receipt: TaskSceneGeometry | None = None,
        seed: int | None = None,
        scenario: Any | None = None,
        attempt_index: int | None = None,
    ) -> None:
        super().__init__(message)
        self.receipt = receipt
        self.seed = seed
        self.scenario = scenario
        self.attempt_index = attempt_index


@dataclass(frozen=True, slots=True)
class TaskGeometryPair:
    body_names: tuple[str, str]
    geom_names: tuple[str, str]
    signed_distance_m: float
    primitive_pair_count: int

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        if not np.isfinite(self.signed_distance_m):
            raise ValueError("pair signed distance must be finite")
        if type(self.primitive_pair_count) is not int or self.primitive_pair_count <= 0:
            raise ValueError("pair primitive count must be a positive integer")
        if (
            type(self.geom_names) is not tuple
            or len(self.geom_names) != 2
            or any(type(name) is not str or not name for name in self.geom_names)
        ):
            raise ValueError("pair geom names must be exactly two nonempty strings")


@dataclass(frozen=True, slots=True)
class TaskSceneGeometry:
    state_sha256: str
    pairs: tuple[TaskGeometryPair, ...]

    def __post_init__(self) -> None:
        if not self.pairs:
            raise ValueError("geometry receipt pairs must not be empty")
        if not isinstance(self.state_sha256, str) or not re.fullmatch(
            "[0-9a-f]{64}", self.state_sha256
        ):
            raise ValueError("geometry receipt state_sha256 must be a SHA256 hex digest")
        object.__setattr__(self, "pairs", tuple(self.pairs))

    def validate_scope(self, active_cup_count: int) -> None:
        for pair in self.pairs:
            if not isinstance(pair, TaskGeometryPair):
                raise ValueError("geometry receipt pairs must contain task geometry pairs")
            pair.validate()
        dynamic = ["plastic_cup", "plastic_cup_b"][:active_cup_count] + ["orange_bottle"]
        expected = set(combinations(dynamic, 2)) | set(
            product(dynamic, ("table", "neutral_block", "base_pedestal"))
        )
        actual = [pair.body_names for pair in self.pairs]
        if len(actual) != len(expected) or set(actual) != expected:
            raise ValueError("geometry receipt has incorrect task body-pair scope")

    @property
    def accepted(self) -> bool:
        # Numeric contact guard, not a configurable physical/grasp threshold.
        return all(pair.signed_distance_m >= -1e-9 for pair in self.pairs)


def _is_descendant_body(model: Any, candidate: int, ancestor: int) -> bool:
    current = candidate
    while current > 0 and current != ancestor:
        current = int(model.body_parentid[current])
    return current == ancestor and candidate != ancestor


def _effective_geom_alpha(model: Any, identifier: int) -> float:
    geom_rgba = model.geom_rgba[identifier]
    if np.any(geom_rgba != _DEFAULT_GEOM_RGBA):
        return float(geom_rgba[3])
    material = int(model.geom_matid[identifier])
    if material >= 0:
        return float(model.mat_rgba[material, 3])
    return float(geom_rgba[3])


def _supported_visual_geoms(
    model: Any, mujoco: Any, body: int, name: str, supported: set[int]
) -> tuple[tuple[int, ...], dict[int, str]]:
    expected_visual, expected_hidden = _TASK_GEOMETRY_SCHEMA[name]
    identifiers = tuple(int(value) for value in np.flatnonzero(model.geom_bodyid == body))
    names = {
        identifier: mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, identifier)
        for identifier in identifiers
    }
    expected = set(expected_visual + expected_hidden)
    if (
        any(value is None for value in names.values())
        or len(names) != len(expected)
        or set(names.values()) != expected
    ):
        raise ValueError(f"unsupported task geometry schema for body: {name}")
    if any(
        _is_descendant_body(model, int(owner), body)
        for owner in model.geom_bodyid
        if int(owner) != body
    ):
        raise ValueError(f"unsupported descendant task geometry for body: {name}")
    by_name = {value: identifier for identifier, value in names.items()}
    visual_identifiers = tuple(by_name[visual_name] for visual_name in expected_visual)
    for identifier in visual_identifiers:
        if int(model.geom_type[identifier]) not in supported:
            raise ValueError(f"unsupported task visual primitive: {names[identifier]}")
        if int(model.geom_group[identifier]) != 0 or _effective_geom_alpha(model, identifier) <= 0:
            raise ValueError(f"task visual primitive is not visibly rendered: {names[identifier]}")
    for hidden_name in expected_hidden:
        identifier = by_name[hidden_name]
        if int(model.geom_group[identifier]) != 2 or _effective_geom_alpha(model, identifier) != 0:
            raise ValueError(f"task collision proxy is not invisibly rendered: {hidden_name}")
    return visual_identifiers, {identifier: names[identifier] for identifier in visual_identifiers}


def measure_task_scene_geometry(
    model: Any, data: Any, *, active_cup_count: int
) -> TaskSceneGeometry:
    """Measure every active task-solid pair at qpos without stepping or rendering.

    Visual primitives, not conservative collision proxies, own this receipt.
    Inactive parked cups and same-body constituent solids are intentionally absent.
    Unknown state, missing bodies and unsupported primitives fail closed.
    """
    import mujoco

    if type(active_cup_count) is not int or active_cup_count not in (0, 1, 2):
        raise ValueError("active_cup_count must be 0, 1 or 2")
    state = [
        data.qpos,
        data.qvel,
        model.cam_pos,
        model.mat_rgba,
        model.geom_pos,
        model.geom_quat,
        model.geom_size,
        model.geom_rgba,
    ]
    if any(not np.isfinite(value).all() for value in state):
        raise ValueError("scene state must be finite")
    dynamic = ["plastic_cup", "plastic_cup_b"][:active_cup_count] + ["orange_bottle"]
    static = ["table", "neutral_block", "base_pedestal"]
    geoms: dict[str, tuple[int, ...]] = {}
    geom_names: dict[int, str] = {}
    supported = {int(mujoco.mjtGeom.mjGEOM_BOX), int(mujoco.mjtGeom.mjGEOM_CYLINDER)}
    for name in dynamic + static:
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, name)
        if body < 0:
            raise ValueError(f"missing task body: {name}")
        identifiers, names = _supported_visual_geoms(model, mujoco, body, name, supported)
        geoms[name] = identifiers
        geom_names.update(names)
    # Refresh derived transforms from the actual qpos; no integrator step occurs.
    mujoco.mj_forward(model, data)
    if not np.isfinite(data.geom_xpos).all() or not np.isfinite(data.geom_xmat).all():
        raise ValueError("derived geometry must be finite")
    digest = hashlib.sha256()
    for value in state + [
        model.geom_type,
        model.geom_bodyid,
        model.geom_group,
        model.geom_matid,
        model.body_parentid,
        data.geom_xpos,
        data.geom_xmat,
    ]:
        array = np.ascontiguousarray(value)
        digest.update(str((array.dtype.str, array.shape)).encode("ascii"))
        digest.update(array.tobytes())
    digest.update(str(active_cup_count).encode("ascii"))
    pairs = []
    for a, b in list(combinations(dynamic, 2)) + list(product(dynamic, static)):
        distances = []
        for ga, gb in product(geoms[a], geoms[b]):
            distance = float(mujoco.mj_geomDistance(model, data, ga, gb, 1.0, None))
            if not np.isfinite(distance):
                raise ValueError("measured geometry distance must be finite")
            distances.append((distance, ga, gb))
        distance, ga, gb = min(distances)
        pairs.append(
            TaskGeometryPair((a, b), (geom_names[ga], geom_names[gb]), distance, len(distances))
        )
    return TaskSceneGeometry(digest.hexdigest(), tuple(pairs))
