"""Uniform scene sampling inside the Teacher success boundary (pure; reachability is injected).

Design: docs/superpowers/specs/2026-10-20-so101-act-teacher-boundary-sampling-design.md (Step 2).

Region: the polygon through the eight boundary points, eroded by the inward margin, minus the hard limits of
``scene_boundary`` (table edge, pedestal, place-target exclusion).  Points are drawn by seeded Poisson-disk sampling
(random sequential dart throwing) at the largest spacing that still yields the target count, never below the formal
sampler's 0.004 m.  The four rollout points must lie inside the region and keep 0.004 m from every scene.  Splits are
assigned spatially: validation and offline_test take one point from each of several k-means strata spread over the region.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache
from typing import Callable, Mapping, Sequence

from so101_demo.act import scene_boundary as boundary

Point = tuple[float, float]

MIN_SPACING_FLOOR_M = 0.004
INWARD_MARGIN_M = 0.01
DEFAULT_COUNT = 103
DEFAULT_SPLIT_COUNTS = {"train": 83, "validation": 10, "offline_test": 10}
#: The formal lists used 576002 and 576003, the rollout groups 576010 and 576011.
DEFAULT_SEED = 576020
ROLLOUT_CLEARANCE_M = 0.004
DECIMALS = 6
_EPS = 1e-9
_SPACING_DECAY = 0.97
_MAX_CONSECUTIVE_FAILURES = 3000
_MAX_DRAWS = 400_000
_AREA_GRID_M = 0.002
_KMEANS_ITERATIONS = 100


class SceneSamplingError(ValueError):
    """Base of the named sampling failures; the message starts with the failure code."""


class RegionInvalidError(SceneSamplingError):
    pass


class RolloutPointOutsideRegionError(SceneSamplingError):
    pass


class SamplingCapacityError(SceneSamplingError):
    pass


class SplitStratificationError(SceneSamplingError):
    pass


# --- polygon geometry ------------------------------------------------------------------------------------------
def polygon_area(polygon: Sequence[Point]) -> float:
    """Signed area: positive for a counter-clockwise polygon."""

    total = 0.0
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]
        total += x1 * y2 - x2 * y1
    return total / 2.0


def _segment_distance(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length_squared = dx * dx + dy * dy
    t = 0.0 if length_squared == 0.0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / length_squared))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


def distance_to_polygon_edge(p: Point, polygon: Sequence[Point]) -> float:
    return min(_segment_distance(p, polygon[i], polygon[(i + 1) % len(polygon)]) for i in range(len(polygon)))


def point_in_polygon(p: Point, polygon: Sequence[Point]) -> bool:
    """Inside or on the boundary."""

    if distance_to_polygon_edge(p, polygon) <= _EPS:
        return True
    inside = False
    for index, (x1, y1) in enumerate(polygon):
        x2, y2 = polygon[(index + 1) % len(polygon)]
        if (y1 > p[1]) != (y2 > p[1]) and p[0] < (x2 - x1) * (p[1] - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def _orientation(a: Point, b: Point, c: Point) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_cross(a: Point, b: Point, c: Point, d: Point) -> bool:
    return _orientation(a, b, c) * _orientation(a, b, d) < 0.0 and _orientation(c, d, a) * _orientation(c, d, b) < 0.0


def require_simple_polygon(polygon: Sequence[Point]) -> None:
    count = len(polygon)
    if count < 3 or abs(polygon_area(polygon)) <= _EPS:
        raise RegionInvalidError("REGION_INVALID: polygon is degenerate")
    for i in range(count):
        for j in range(i + 1, count):
            if j == i + 1 or (i == 0 and j == count - 1):
                continue
            if _segments_cross(polygon[i], polygon[(i + 1) % count], polygon[j], polygon[(j + 1) % count]):
                raise RegionInvalidError("REGION_INVALID: polygon edges cross")


def shrink_polygon(polygon: Sequence[Point], margin_m: float) -> list[Point]:
    """The polygon moved inward by ``margin_m`` (mitred offset of every edge), counter-clockwise.

    Used for the report.  Membership of the region is decided by the exact distance to the edges
    (``Region.contains``), which does not depend on the mitres staying valid.
    """

    ring = list(polygon) if polygon_area(polygon) > 0 else list(reversed(polygon))
    require_simple_polygon(ring)
    count = len(ring)
    lines = []
    for i in range(count):
        (x1, y1), (x2, y2) = ring[i], ring[(i + 1) % count]
        length = math.hypot(x2 - x1, y2 - y1)
        nx, ny = -(y2 - y1) / length, (x2 - x1) / length  # left normal, inward for a counter-clockwise ring
        lines.append(((x1 + nx * margin_m, y1 + ny * margin_m), (x2 - x1, y2 - y1)))
    shrunk = []
    for i in range(count):
        (px, py), (dx, dy) = lines[i - 1]
        (qx, qy), (ex, ey) = lines[i]
        denominator = dx * ey - dy * ex
        if abs(denominator) <= _EPS:
            raise RegionInvalidError("REGION_INVALID: parallel adjacent edges")
        t = ((qx - px) * ey - (qy - py) * ex) / denominator
        shrunk.append((round(px + t * dx, DECIMALS), round(py + t * dy, DECIMALS)))
    require_simple_polygon(shrunk)
    for i in range(count):  # an edge that flipped direction means the margin ate the polygon
        old, new = (ring[(i + 1) % count][0] - ring[i][0], ring[(i + 1) % count][1] - ring[i][1]), (
            shrunk[(i + 1) % count][0] - shrunk[i][0], shrunk[(i + 1) % count][1] - shrunk[i][1])
        if old[0] * new[0] + old[1] * new[1] <= 0.0:
            raise RegionInvalidError("REGION_INVALID: shrunk polygon collapsed")
    if not 0.0 < polygon_area(shrunk) < polygon_area(ring):
        raise RegionInvalidError("REGION_INVALID: shrunk polygon collapsed")
    return shrunk


@dataclass(frozen=True)
class Region:
    """Sampling region: inside ``polygon`` by at least ``margin_m`` and clear of every hard limit."""

    polygon: tuple[Point, ...]
    margin_m: float = INWARD_MARGIN_M
    limit_check: Callable[[float, float], str | None] = boundary.hard_limit_violation

    def contains(self, p: Point) -> bool:
        return (
            point_in_polygon(p, self.polygon)
            and distance_to_polygon_edge(p, self.polygon) >= self.margin_m - _EPS
            and self.limit_check(p[0], p[1]) is None
        )

    def bounding_box(self) -> tuple[float, float, float, float]:
        xs, ys = [p[0] for p in self.polygon], [p[1] for p in self.polygon]
        return min(xs), max(xs), min(ys), max(ys)

    @property
    def area(self) -> float:
        """Grid estimate of the usable area (deterministic; cached per region)."""

        return _usable_area(self)


@lru_cache(maxsize=16)
def _usable_area(region: Region) -> float:
    x0, x1, y0, y1 = region.bounding_box()
    columns, rows = int((x1 - x0) / _AREA_GRID_M) + 1, int((y1 - y0) / _AREA_GRID_M) + 1
    hits = sum(
        1
        for i in range(columns)
        for j in range(rows)
        if region.contains((x0 + (i + 0.5) * _AREA_GRID_M, y0 + (j + 0.5) * _AREA_GRID_M))
    )
    return hits * _AREA_GRID_M * _AREA_GRID_M


def boundary_polygon(boundary_points: Mapping[str, Point]) -> tuple[Point, ...]:
    """The polygon through B_1..B_8 in ray order (counter-clockwise)."""

    if set(boundary_points) != set(boundary.RAY_NAMES):
        raise RegionInvalidError("REGION_INVALID: need exactly the eight boundary points")
    polygon = tuple((float(boundary_points[name][0]), float(boundary_points[name][1])) for name in boundary.RAY_NAMES)
    require_simple_polygon(polygon)
    return polygon


# --- Poisson-disk sampling -------------------------------------------------------------------------------------
def _dart_throwing(
    region: Region,
    count: int,
    spacing_m: float,
    seed: int,
    keep_clear: Sequence[tuple[Point, float]],
    accept: Callable[[Point], bool],
) -> list[Point]:
    rng = random.Random(seed)
    x0, x1, y0, y1 = region.bounding_box()
    points: list[Point] = []
    failures = draws = 0
    while len(points) < count and failures < _MAX_CONSECUTIVE_FAILURES and draws < _MAX_DRAWS:
        draws += 1
        p = (round(rng.uniform(x0, x1), DECIMALS), round(rng.uniform(y0, y1), DECIMALS))
        if (
            not region.contains(p)
            or any(math.dist(p, q) < spacing_m for q in points)
            or any(math.dist(p, centre) < clearance for centre, clearance in keep_clear)
            or not accept(p)
        ):
            failures += 1
            continue
        failures = 0
        points.append(p)
    return points


def poisson_disk(
    region: Region,
    count: int,
    seed: int,
    *,
    keep_clear: Sequence[tuple[Point, float]] = (),
    accept: Callable[[Point], bool] = lambda _p: True,
    min_spacing_floor_m: float = MIN_SPACING_FLOOR_M,
) -> tuple[list[Point], float]:
    """``count`` points and the minimum spacing used: the largest of a geometric ladder that fits ``count`` points.

    The ladder starts near the densest random packing of the region area and decays by 3 % per rung down to
    ``min_spacing_floor_m``; the floor rung is tried last.  Every rung restarts the same seeded stream, so the result is a
    pure function of the arguments.  ``accept`` (reachability) is asked last, once per distinct point.
    """

    area = region.area
    if area <= 0.0:
        raise SamplingCapacityError("SAMPLING_CAPACITY: the region is empty")
    verdicts: dict[Point, bool] = {}

    def cached(p: Point) -> bool:
        if p not in verdicts:
            verdicts[p] = bool(accept(p))
        return verdicts[p]

    spacing = max(min_spacing_floor_m, 0.95 * math.sqrt(area / count))
    while True:
        points = _dart_throwing(region, count, spacing, seed, keep_clear, cached)
        if len(points) == count:
            return points, round(spacing, DECIMALS)
        if spacing <= min_spacing_floor_m + _EPS:
            raise SamplingCapacityError(
                f"SAMPLING_CAPACITY: {len(points)} of {count} points fit at the {min_spacing_floor_m} m floor"
            )
        spacing = max(min_spacing_floor_m, spacing * _SPACING_DECAY)


# --- splits ----------------------------------------------------------------------------------------------------
def _nearest_index(p: Point, centres: Sequence[Point]) -> int:
    return min(range(len(centres)), key=lambda i: (math.dist(p, centres[i]), i))


def _kmeans(points: Sequence[Point], k: int, seed: int) -> list[list[int]]:
    rng = random.Random(seed)
    centres = [points[rng.randrange(len(points))]]
    while len(centres) < k:  # farthest-first: distinct, spread-out starting centres
        centres.append(max(points, key=lambda p: (min(math.dist(p, c) for c in centres), p)))
    members: list[list[int]] = []
    for _ in range(_KMEANS_ITERATIONS):
        members = [[] for _ in range(k)]
        for index, p in enumerate(points):
            members[_nearest_index(p, centres)].append(index)
        updated = []
        for cluster, centre in zip(members, centres):
            if cluster:
                updated.append((sum(points[i][0] for i in cluster) / len(cluster), sum(points[i][1] for i in cluster) / len(cluster)))
            else:  # an emptied stratum restarts at the point farthest from its own centre
                updated.append(max(points, key=lambda p: (math.dist(p, centres[_nearest_index(p, centres)]), p)))
        if updated == centres:
            break
        centres = updated
    if any(not cluster for cluster in members):
        raise SplitStratificationError("SPLIT_STRATIFICATION: an empty stratum remained")
    return members


def stratified_splits(points: Sequence[Point], counts: Mapping[str, int], seed: int) -> list[str]:
    """A split name per point.  Validation and offline_test take one point from each of ``validation + offline_test``
    k-means strata; the strata are walked in angular order around the centroid and dealt to the two splits in proportion,
    so both splits cover the whole region.  Everything else is train.
    """

    held = counts["validation"] + counts["offline_test"]
    if sum(counts.values()) != len(points) or counts["train"] < 0 or held < 2 or min(counts.values()) < 0:
        raise SplitStratificationError("SPLIT_STRATIFICATION: split counts do not add up to the point count")
    strata = _kmeans(points, held, seed)
    centroids = [(sum(points[i][0] for i in s) / len(s), sum(points[i][1] for i in s) / len(s)) for s in strata]
    middle = (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))
    order = sorted(
        range(held),
        key=lambda s: (math.atan2(centroids[s][1] - middle[1], centroids[s][0] - middle[0]), math.dist(centroids[s], middle)),
    )
    splits = ["train"] * len(points)
    dealt = {"validation": 0, "offline_test": 0}
    for stratum in order:
        name = min(dealt, key=lambda n: ((dealt[n] + 1) / counts[n] if counts[n] else math.inf, n != "validation"))
        dealt[name] += 1
        representative = min(strata[stratum], key=lambda i: (math.dist(points[i], centroids[stratum]), i))
        splits[representative] = name
    if dealt != {"validation": counts["validation"], "offline_test": counts["offline_test"]}:
        raise SplitStratificationError("SPLIT_STRATIFICATION: strata could not be dealt to the requested counts")
    return splits


# --- the whole sample --------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class SceneSample:
    polygon: tuple[Point, ...]
    shrunk_polygon: tuple[Point, ...]
    points: tuple[Point, ...]
    splits: tuple[str, ...]
    spacing_m: float
    area_m2: float
    rollout_nearest_scene_m: dict[str, float]
    rollout_nearest_training_m: dict[str, float]


def sample_scenes(
    boundary_points: Mapping[str, Point],
    rollout_points: Mapping[str, Point],
    *,
    reachable: Callable[[float, float], bool],
    count: int = DEFAULT_COUNT,
    split_counts: Mapping[str, int] = DEFAULT_SPLIT_COUNTS,
    seed: int = DEFAULT_SEED,
    margin_m: float = INWARD_MARGIN_M,
    rollout_clearance_m: float = ROLLOUT_CLEARANCE_M,
) -> SceneSample:
    """Sample ``count`` scenes inside the boundary polygon, spread evenly and split spatially.

    Raises ``RolloutPointOutsideRegionError`` when a rollout point is outside the region (the boundary is too small for
    the standard points), ``SamplingCapacityError`` when ``count`` points do not fit at the 0.004 m floor.
    """

    polygon = boundary_polygon(boundary_points)
    region = Region(polygon, margin_m)
    for name, p in rollout_points.items():
        if not region.contains((float(p[0]), float(p[1]))):
            raise RolloutPointOutsideRegionError(f"ROLLOUT_POINT_OUTSIDE_REGION: {name}")
    keep_clear = [((float(p[0]), float(p[1])), rollout_clearance_m) for p in rollout_points.values()]
    points, spacing = poisson_disk(
        region, count, seed, keep_clear=keep_clear, accept=lambda p: reachable(p[0], p[1])
    )
    splits = stratified_splits(points, split_counts, seed)
    training = [p for p, s in zip(points, splits) if s == "train"]
    return SceneSample(
        polygon=polygon,
        shrunk_polygon=tuple(shrink_polygon(polygon, margin_m)),
        points=tuple(points),
        splits=tuple(splits),
        spacing_m=spacing,
        area_m2=round(region.area, DECIMALS),
        rollout_nearest_scene_m={
            name: round(min(math.dist((float(p[0]), float(p[1])), q) for q in points), DECIMALS)
            for name, p in rollout_points.items()
        },
        rollout_nearest_training_m={
            name: round(min(math.dist((float(p[0]), float(p[1])), q) for q in training), DECIMALS)
            for name, p in rollout_points.items()
        },
    )
