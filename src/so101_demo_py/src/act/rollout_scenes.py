"""Closed-loop rollout scenes: pure sampling with an injected reachability verdict, and the separation rules.

Four groups are reported on their own (design 2026-10-18-so101-act-native-rollout-design.md, Scenes):

* ``rollout_standard`` - the four points of ``config/mujoco/rgbd_task_points.yaml``, in file order;
* ``rollout_validation`` and ``rollout_test`` - sampled from new seeds inside the triangle of the three approved anchors, at least
  ``PLACE_EXCLUSION_M`` from the Teacher place target, ``MIN_GAP_WITHIN_M`` from every other rollout scene and
  ``MIN_GAP_TO_TAKEN_M`` from every training scene (a rollout-only scene is never trained on, so the training gap is relaxed; the
  actual distance to the nearest training scene is recorded on each scene);
* ``rollout_extrapolation`` - optional reachable points outside the triangle.

This module touches no ROS, MuJoCo or file other than the two small config files it is handed. Whether a point is reachable is
answered by the injected ``reachable(xy)`` (the evidence-side generator runs ``task_reachability`` against the native stack).
It returns ``True``, or a mapping of pose name to bool (the five-pose Teacher filter), and a point is kept only when every
verdict is exactly ``True``.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from pathlib import Path

import yaml

GROUP_STANDARD = "rollout_standard"
GROUP_VALIDATION = "rollout_validation"
GROUP_TEST = "rollout_test"
GROUP_EXTRAPOLATION = "rollout_extrapolation"
GROUPS = (GROUP_STANDARD, GROUP_VALIDATION, GROUP_TEST, GROUP_EXTRAPOLATION)
SAMPLED_GROUPS = (GROUP_VALIDATION, GROUP_TEST, GROUP_EXTRAPOLATION)
#: The sampler seeds of the two held-out groups (design: new seeds, disjoint from the collection lists).
SEEDS = {GROUP_VALIDATION: 576010, GROUP_TEST: 576011}
KIND = "ACT_ROLLOUT_SCENES"
PLACE_EXCLUSION_M = 0.060
MIN_GAP_WITHIN_M = 0.004
MIN_GAP_TO_TAKEN_M = 0.002
DECIMALS = 6
DEFAULT_MAX_DRAWS = 200_000
_EPS = 1e-9
_ANCHORS = ("default", "left", "forward")


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def _real(value) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value)


def _xy(value, code: str) -> tuple:
    if not isinstance(value, (list, tuple)) or len(value) != 2 or not all(_real(item) for item in value):
        raise ValueError(code)
    return (float(value[0]), float(value[1]))


def in_triangle(xy, triangle, *, tolerance: float = _EPS) -> bool:
    """Whether ``xy`` is inside the triangle or on its boundary (within ``tolerance``)."""

    (ax, ay), (bx, by), (cx, cy) = triangle
    px, py = xy

    def side(x1, y1, x2, y2):
        return (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1)

    signs = (side(ax, ay, bx, by), side(bx, by, cx, cy), side(cx, cy, ax, ay))
    return all(value >= -tolerance for value in signs) or all(value <= tolerance for value in signs)


def anchor_triangle(path) -> tuple:
    """The xy of the three approved anchors (default, left, forward) of ``pick-place-live-anchors.yaml``."""

    document = yaml.safe_load(Path(path).read_bytes())
    anchors = document.get("anchors") if isinstance(document, dict) else None
    if not isinstance(anchors, dict) or not set(_ANCHORS) <= set(anchors):
        raise ValueError("ROLLOUT_ANCHORS_INVALID")
    vertices = []
    for name in _ANCHORS:
        start = anchors[name].get("cup_start_m") if isinstance(anchors[name], dict) else None
        if not isinstance(start, list) or len(start) != 3 or not all(_real(item) for item in start):
            raise ValueError("ROLLOUT_ANCHORS_INVALID")
        vertices.append((float(start[0]), float(start[1])))
    return tuple(vertices)


def _nearest(xy, others):
    others = list(others)
    return round(min(math.dist(xy, other) for other in others), DECIMALS) if others else None


def load_standard_points(path, *, triangle=None, taken_xy=()) -> list:
    """The standard group: the task points of the file in file order, one scene each, never sampled."""

    code = "ROLLOUT_STANDARD_POINTS_INVALID"
    try:
        document = yaml.safe_load(Path(path).read_bytes())
    except (OSError, yaml.YAMLError) as error:
        raise ValueError(code) from error
    points = document.get("points") if isinstance(document, dict) and document.get("schema_version") == 1 else None
    if not isinstance(points, list) or not points:
        raise ValueError(code)
    scenes, seen = [], set()
    for point in points:
        if not isinstance(point, dict) or not isinstance(point.get("id"), str) or not point["id"] \
                or point["id"] in seen:
            raise ValueError(code)
        seen.add(point["id"])
        position = point.get("cup_position_world_m")
        if not isinstance(position, list) or len(position) != 3 or not all(_real(item) for item in position):
            raise ValueError(code)
        xy = [float(position[0]), float(position[1])]
        scenes.append({
            "scene_id": "rollout-standard-" + point["id"], "group": GROUP_STANDARD, "index": len(scenes) + 1,
            "point_id": point["id"], "xy": xy, "cup_position_world_m": [xy[0], xy[1], float(position[2])],
            "seed": None, "nearest_training_m": _nearest(xy, taken_xy),
            "inside_triangle": None if triangle is None else in_triangle(xy, triangle), "reachability": None})
    return scenes


def _verdict(answer):
    """(kept, recorded verdict): exactly True, or a non-empty mapping of bool, else the verdict is refused as malformed."""

    if answer is True:
        return True, True
    if answer is False:
        return False, False
    if isinstance(answer, dict) and answer and all(type(item) is bool for item in answer.values()):
        return all(answer.values()), dict(answer)
    raise ValueError("ROLLOUT_REACHABILITY_VERDICT_INVALID")


def _region_draw(rng: random.Random, region: dict):
    if region["kind"] == "triangle":
        (ax, ay), (bx, by), (cx, cy) = region["vertices"]
        r1, r2 = math.sqrt(rng.random()), rng.random()
        weights = (1 - r1, r1 * (1 - r2), r1 * r2)
        return (weights[0] * ax + weights[1] * bx + weights[2] * cx, weights[0] * ay + weights[1] * by + weights[2] * cy)
    (x0, x1), (y0, y1) = region["x"], region["y"]
    return (rng.uniform(x0, x1), rng.uniform(y0, y1))


def _region_ok(region: dict) -> bool:
    if not isinstance(region, dict):
        return False
    if region.get("kind") == "triangle":
        vertices = region.get("vertices")
        return isinstance(vertices, (list, tuple)) and len(vertices) == 3 and all(
            isinstance(v, (list, tuple)) and len(v) == 2 and all(_real(c) for c in v) for v in vertices)
    if region.get("kind") == "box":
        return all(isinstance(region.get(axis), (list, tuple)) and len(region[axis]) == 2
                   and all(_real(c) for c in region[axis]) and region[axis][0] < region[axis][1] for axis in ("x", "y"))
    return False


def sample_group(*, group, seed, count, region, place_xy, reachable, taken_xy, rollout_xy, reset_z_m,
                 max_draws: int = DEFAULT_MAX_DRAWS, place_exclusion_m: float = PLACE_EXCLUSION_M,
                 min_gap_within_m: float = MIN_GAP_WITHIN_M, min_gap_to_taken_m: float = MIN_GAP_TO_TAKEN_M) -> list:
    """``count`` scenes of one sampled group, deterministic in ``seed``.

    ``rollout_xy`` are the scenes of the other groups (and the standard points) this group must keep ``min_gap_within_m`` from.
    Cheap rules are applied before ``reachable`` is asked, so the expensive verdict runs only for candidate points. A region
    that cannot supply ``count`` points in ``max_draws`` draws raises ``ROLLOUT_GENERATOR_EXHAUSTED`` and returns nothing.
    """

    if group not in SAMPLED_GROUPS:
        raise ValueError("ROLLOUT_GROUP_INVALID")
    if (type(seed) is not int or type(count) is not int or count < 1 or type(max_draws) is not int or max_draws < 1
            or not _region_ok(region) or not callable(reachable) or not _real(reset_z_m)
            or not all(_real(value) and value >= 0 for value in (place_exclusion_m, min_gap_within_m, min_gap_to_taken_m))):
        raise ValueError("ROLLOUT_SAMPLING_PARAMETERS_INVALID")
    place = _xy(place_xy, "ROLLOUT_SAMPLING_PARAMETERS_INVALID")
    taken = [_xy(point, "ROLLOUT_SAMPLING_PARAMETERS_INVALID") for point in taken_xy]
    others = [_xy(point, "ROLLOUT_SAMPLING_PARAMETERS_INVALID") for point in rollout_xy]
    rng = random.Random(seed)
    scenes, draws = [], 0
    while len(scenes) < count:
        if draws >= max_draws:
            raise ValueError(f"ROLLOUT_GENERATOR_EXHAUSTED: {len(scenes)} of {count} after {draws} draws")
        draws += 1
        raw = _region_draw(rng, region)
        xy = (round(raw[0], DECIMALS), round(raw[1], DECIMALS))
        if region["kind"] == "triangle" and not in_triangle(xy, region["vertices"]):
            continue
        if region["kind"] == "box" and "exclude_triangle" in region and in_triangle(xy, region["exclude_triangle"]):
            continue
        if math.dist(xy, place) < place_exclusion_m:
            continue
        if taken and min(math.dist(xy, point) for point in taken) < min_gap_to_taken_m:
            continue
        if any(math.dist(xy, point) < min_gap_within_m for point in (*others, *(tuple(s["xy"]) for s in scenes))):
            continue
        kept, verdict = _verdict(reachable(xy))
        if not kept:
            continue
        index = len(scenes) + 1
        scenes.append({
            "scene_id": f"rollout-{group.removeprefix('rollout_')}-{index:03d}", "group": group, "index": index,
            "point_id": None, "xy": [xy[0], xy[1]], "cup_position_world_m": [xy[0], xy[1], float(reset_z_m)],
            "seed": seed, "nearest_training_m": _nearest(xy, taken),
            "inside_triangle": in_triangle(xy, region["vertices"]) if region["kind"] == "triangle"
            else (False if "exclude_triangle" in region else None),
            "reachability": verdict})
    return scenes


def build_scene_document(groups: dict, *, parameters: dict) -> dict:
    """The sealed scene list: the groups in the fixed order, with the parameters they were generated under."""

    if not isinstance(groups, dict) or not groups or not set(groups) <= set(GROUPS) or not isinstance(parameters, dict):
        raise ValueError("ROLLOUT_SCENES_INVALID")
    ordered = {name: list(groups[name]) for name in GROUPS if name in groups}
    ids = [scene["scene_id"] for scenes in ordered.values() for scene in scenes]
    if len(set(ids)) != len(ids):
        raise ValueError("ROLLOUT_SCENES_INVALID")
    document = {"schema_version": 1, "kind": KIND, "parameters": dict(parameters), "groups": ordered}
    document["manifest_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    return document


def verify_scene_document(document: dict, *, taken_xy, place_xy,
                          place_exclusion_m: float = PLACE_EXCLUSION_M,
                          min_gap_within_m: float = MIN_GAP_WITHIN_M,
                          min_gap_to_taken_m: float = MIN_GAP_TO_TAKEN_M) -> None:
    """Re-check a scene list against the rules, from the scenes' own coordinates (recorded distances are not trusted).

    ``taken_xy`` or ``place_xy`` of None skips the rule that needs it (a run that only has the list checks its hash, its
    structure and the within-list gap)."""

    if not isinstance(document, dict) or document.get("kind") != KIND or document.get("schema_version") != 1 \
            or not isinstance(document.get("groups"), dict) or not set(document["groups"]) <= set(GROUPS):
        raise ValueError("ROLLOUT_SCENES_INVALID")
    body = {key: value for key, value in document.items() if key != "manifest_sha256"}
    if document.get("manifest_sha256") != hashlib.sha256(_canonical(body)).hexdigest():
        raise ValueError("ROLLOUT_SCENES_HASH_INVALID")
    place = None if place_xy is None else _xy(place_xy, "ROLLOUT_SCENES_INVALID")
    taken = None if taken_xy is None else [_xy(point, "ROLLOUT_SCENES_INVALID") for point in taken_xy]
    flat = [(name, scene) for name, scenes in document["groups"].items() for scene in scenes]
    for name, scene in flat:
        xy = _xy(scene.get("xy"), "ROLLOUT_SCENES_INVALID")
        if scene.get("group") != name or scene.get("cup_position_world_m", [None])[:2] != list(xy):
            raise ValueError("ROLLOUT_SCENES_INVALID")
        if name == GROUP_STANDARD:
            continue
        if place is not None and math.dist(xy, place) < place_exclusion_m - 1e-12:
            raise ValueError("ROLLOUT_SCENE_PLACE_EXCLUSION: " + scene["scene_id"])
        if taken and min(math.dist(xy, point) for point in taken) < min_gap_to_taken_m - 1e-12:
            raise ValueError("ROLLOUT_SCENE_GAP_TO_TAKEN: " + scene["scene_id"])
    for index, (name, scene) in enumerate(flat):
        for other_name, other in flat[index + 1:]:
            if GROUP_STANDARD == name == other_name:
                continue
            if math.dist(scene["xy"], other["xy"]) < min_gap_within_m - 1e-12:
                raise ValueError(f"ROLLOUT_SCENE_GAP_WITHIN: {scene['scene_id']} {other['scene_id']}")
