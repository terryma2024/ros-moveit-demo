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


class ScenePenetrationError(RuntimeError):
    """A measured penetrating scene may be retried with a new deterministic draw."""


@dataclass(frozen=True, slots=True)
class TaskGeometryPair:
    body_names: tuple[str, str]
    geom_names: tuple[str, str]
    signed_distance_m: float
    primitive_pair_count: int

    def __post_init__(self) -> None:
        if not np.isfinite(self.signed_distance_m):
            raise ValueError("pair signed distance must be finite")


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
        identifiers = []
        for identifier in np.flatnonzero(model.geom_bodyid == body):
            identifier = int(identifier)
            geom_name = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, identifier)
            if geom_name is None or not geom_name.endswith("_visual"):
                continue
            if int(model.geom_type[identifier]) not in supported:
                raise ValueError(f"unsupported task visual primitive: {geom_name}")
            identifiers.append(identifier)
            geom_names[identifier] = geom_name
        if not identifiers:
            raise ValueError(f"missing visual primitives for task body: {name}")
        geoms[name] = tuple(identifiers)
    # Refresh derived transforms from the actual qpos; no integrator step occurs.
    mujoco.mj_forward(model, data)
    if not np.isfinite(data.geom_xpos).all() or not np.isfinite(data.geom_xmat).all():
        raise ValueError("derived geometry must be finite")
    digest = hashlib.sha256()
    for value in state + [model.geom_type, model.geom_bodyid, data.geom_xpos, data.geom_xmat]:
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
