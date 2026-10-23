"""Teacher success boundary along eight rays: geometry, hard limits and the live bracket logic (pure, no I/O).

Design: docs/superpowers/specs/2026-10-20-so101-act-teacher-boundary-sampling-design.md (Step 1).

The search runs in two stages per ray.  The offline stage walks the ray outward in fixed steps and stops at the first
radius whose five-pose Teacher reachability fails or that hits a hard limit (``kinematic_limit``).  The live stage
brackets the radius of the last real Teacher success between a known success and that kinematic ceiling
(``bisection_next`` / ``bisection_update``), and finishes with one repeat of the found boundary.

Nothing here touches ROS, MuJoCo or a file: whether a point is reachable is the injected ``reachable(x, y) -> bool``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Callable, NamedTuple, Sequence

DECIMALS = 6
_EPS = 1e-9

#: Eight rays, 45 degrees apart in world x/y, counter-clockwise from +x (the polygon through the boundary points
#: therefore comes out counter-clockwise).
RAY_NAMES = ("E", "NE", "N", "NW", "W", "SW", "S", "SE")
#: Design Q1: between task_start (0.02, -0.28) and forward_5cm (0.02, -0.33), inside the current data.
DEFAULT_CENTRE_XY = (0.02, -0.29)
DEFAULT_STEP_M = 0.01
#: Longest ray; the policy workspace bounds (config/policies/dynamic_cup_pick/mujoco.yaml, safety.workspace_bounds_m)
#: are x in [-0.30, 0.35] and y in [-0.50, 0.20], so no ray point needs to go further than the table allows.
DEFAULT_MAX_RADIUS_M = 0.30

# --- hard limits -----------------------------------------------------------------------------------------------
#: Cup radius: the cup wall boxes of assets/common/geometry-manifest.yaml (task_scene.objects.plastic_cup) sit at 0.039 m
#: from the cup axis with 0.002 m thickness, i.e. a 0.04 m radius (design: "0.04 m cup radius").
CUP_RADIUS_M = 0.04
#: Design: the cup keeps a 0.01 m margin on the table.
EDGE_MARGIN_M = 0.01
#: Table: assets/common/geometry-manifest.yaml task_scene.objects.table, pose (0, -0.20) and a 0.50 x 0.60 m top.
TABLE_CENTRE_XY = (0.0, -0.20)
TABLE_HALF_EXTENT_XY = (0.25, 0.30)
#: Pedestal: the same manifest, task_scene.objects.pedestal, pose (0, 0) and a 0.18 x 0.18 m footprint.
PEDESTAL_CENTRE_XY = (0.0, 0.0)
PEDESTAL_HALF_EXTENT_XY = (0.09, 0.09)
#: Teacher place target (the end_target of the Teacher endpoint, (-0.0803, -0.2468), as the formal scene generator used it).
PLACE_TARGET_XY = (-0.080303, -0.246785)
#: Exclusion radius around the place target.  Design amendment 2 (2026-10-21, human): 0.045 m = the 0.04 m cup radius plus
#: 5 mm, so the starting cup never covers the target centre and stays well outside the 0.02 m placement tolerance.  The
#: earlier 0.060 m was a sampler constant of generate_w8_scenes with no recorded physical basis.  It is applied exactly,
#: with no inward margin (amendment 1).
PLACE_EXCLUSION_M = 0.045
#: The retired formal-sampler value, kept only to draw the old exclusion circle in plots and to read old evidence.
OLD_PLACE_EXCLUSION_M = 0.060

LIMIT_TABLE_EDGE = "TABLE_EDGE"
LIMIT_PEDESTAL = "PEDESTAL"
LIMIT_PLACE_TARGET = "PLACE_TARGET"
REASON_UNREACHABLE = "UNREACHABLE"
REASON_RAY_END = "RAY_END"


class RayPoint(NamedTuple):
    radius_m: float
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class KinematicLimit:
    """Where one ray stops offline.

    ``last_feasible_m`` is the largest radius that passed both the hard limits and the reachability (0.0 when even the
    first step fails: the centre itself is then the only candidate).  ``first_blocked_m`` is the radius that stopped the
    ray (None when the ray ran out of points).  ``reason`` is ``UNREACHABLE``, a hard-limit name or ``RAY_END``.
    """

    last_feasible_m: float
    first_blocked_m: float | None
    reason: str


def _plain(value: float) -> float:
    return round(value, DECIMALS) + 0.0


def point_on_ray(centre: Sequence[float], ray_name: str, radius_m: float) -> tuple[float, float]:
    """The world x/y at ``radius_m`` along ray ``ray_name`` (six decimals, no negative zero)."""

    if ray_name not in RAY_NAMES:
        raise ValueError(f"BOUNDARY_RAY_UNKNOWN: {ray_name}")
    angle = math.radians(45.0 * RAY_NAMES.index(ray_name))
    return (_plain(centre[0] + radius_m * math.cos(angle)), _plain(centre[1] + radius_m * math.sin(angle)))


def ray_candidates(
    centre: Sequence[float] = DEFAULT_CENTRE_XY,
    directions: int = 8,
    step: float = DEFAULT_STEP_M,
    max_radius: float = DEFAULT_MAX_RADIUS_M,
) -> dict[str, tuple[RayPoint, ...]]:
    """Points at ``step``, ``2 * step``, ... up to ``max_radius`` along the eight rays (E, NE, N, NW, W, SW, S, SE)."""

    if directions != len(RAY_NAMES):
        raise ValueError("BOUNDARY_DIRECTIONS_UNSUPPORTED: eight rays only")
    if not (step > 0.0 and max_radius >= step and len(centre) == 2):
        raise ValueError("BOUNDARY_RAY_PARAMETERS_INVALID")
    count = int(math.floor(max_radius / step + _EPS))
    rays = {}
    for name in RAY_NAMES:
        points = []
        for index in range(1, count + 1):
            radius = _plain(index * step)
            points.append(RayPoint(radius, *point_on_ray(centre, name, radius)))
        rays[name] = tuple(points)
    return rays


def hard_limit_violation(
    x: float,
    y: float,
    *,
    place_target: Sequence[float] = PLACE_TARGET_XY,
    place_exclusion_m: float = PLACE_EXCLUSION_M,
    cup_radius_m: float = CUP_RADIUS_M,
    edge_margin_m: float = EDGE_MARGIN_M,
) -> str | None:
    """The name of the first hard limit a cup centre at (x, y) violates, or None.

    Table edge: the whole cup plus the margin must stay on the table top.  Pedestal: the cup may not overlap the pedestal
    footprint grown by the cup radius and the margin.  Place target: the cup centre stays ``place_exclusion_m`` from the
    Teacher place target.
    """

    clearance = cup_radius_m + edge_margin_m
    if (
        abs(x - TABLE_CENTRE_XY[0]) > TABLE_HALF_EXTENT_XY[0] - clearance + _EPS
        or abs(y - TABLE_CENTRE_XY[1]) > TABLE_HALF_EXTENT_XY[1] - clearance + _EPS
    ):
        return LIMIT_TABLE_EDGE
    if (
        abs(x - PEDESTAL_CENTRE_XY[0]) < PEDESTAL_HALF_EXTENT_XY[0] + clearance - _EPS
        and abs(y - PEDESTAL_CENTRE_XY[1]) < PEDESTAL_HALF_EXTENT_XY[1] + clearance - _EPS
    ):
        return LIMIT_PEDESTAL
    if math.hypot(x - place_target[0], y - place_target[1]) < place_exclusion_m - _EPS:
        return LIMIT_PLACE_TARGET
    return None


def kinematic_limit(
    ray: Sequence[RayPoint],
    reachable: Callable[[float, float], bool],
    *,
    limit_check: Callable[[float, float], str | None] = hard_limit_violation,
) -> KinematicLimit:
    """Walk ``ray`` outward and stop at the first hard limit or the first point where ``reachable`` is False."""

    last = 0.0
    for point in ray:
        violation = limit_check(point.x, point.y)
        if violation is not None:
            return KinematicLimit(last, point.radius_m, violation)
        if not reachable(point.x, point.y):
            return KinematicLimit(last, point.radius_m, REASON_UNREACHABLE)
        last = point.radius_m
    return KinematicLimit(last, None, REASON_RAY_END)


# --- 2 mm refinement of the last 1 cm step (design amendment 1) --------------------------------------------------
#: Limit kinds of a boundary point.  ``REACH`` is a limit set by reachability or by a Teacher failure: the inward sampling
#: margin applies next to it.  Every other kind is a hard limit that the sampler applies exactly (its own margins, if any,
#: are already inside ``hard_limit_violation``), so no extra inward margin is taken there.
LIMIT_REACH = "REACH"
REFINE_STEP_M = 0.002


@dataclass(frozen=True, slots=True)
class RefinedLimit:
    """The limit of one ray after the 2 mm refinement: ``radius_m`` (>= the 1 cm ``last_feasible_m``) and its kind."""

    radius_m: float
    kind: str
    evaluated: tuple[tuple[float, str], ...]


def place_exclusion_entry_radius(
    centre: Sequence[float],
    ray_name: str,
    *,
    place_target: Sequence[float] = PLACE_TARGET_XY,
    place_exclusion_m: float = PLACE_EXCLUSION_M,
    lower_m: float = 0.0,
) -> float | None:
    """The smallest radius > ``lower_m`` at which the ray is on the exclusion circle (exact up to six decimals).

    The returned radius is rounded down until the rounded world point no longer violates the exclusion, so the point is
    outside the circle by at most a few micrometres.  None when the ray does not enter the circle beyond ``lower_m``.
    """

    angle = math.radians(45.0 * RAY_NAMES.index(ray_name))
    dx, dy = math.cos(angle), math.sin(angle)
    fx, fy = centre[0] - place_target[0], centre[1] - place_target[1]
    b = fx * dx + fy * dy
    c = fx * fx + fy * fy - place_exclusion_m * place_exclusion_m
    disc = b * b - c
    if disc < 0.0:
        return None
    root = math.sqrt(disc)
    candidates = [r for r in (-b - root, -b + root) if r > lower_m + _EPS]
    if not candidates:
        return None
    # The ray enters the circle at the smaller root: back off (never forward) until the rounded world point is outside.
    radius = math.floor(min(candidates) * 1e6) / 1e6
    for _ in range(20):
        x, y = point_on_ray(centre, ray_name, radius)
        if math.hypot(x - place_target[0], y - place_target[1]) >= place_exclusion_m - _EPS:
            return _plain(radius) if radius > lower_m + _EPS else None
        radius -= 1e-6
    raise ValueError("BOUNDARY_EXCLUSION_RADIUS_NOT_FOUND")


def refine_limit(
    ray_name: str,
    centre: Sequence[float],
    coarse: KinematicLimit,
    reachable: Callable[[float, float], bool],
    *,
    step_m: float = REFINE_STEP_M,
    limit_check: Callable[[float, float], str | None] = hard_limit_violation,
) -> RefinedLimit:
    """Search the last 1 cm step of a ray at ``step_m`` with the same five-pose reachability.

    The ray is walked outward from ``coarse.last_feasible_m`` in ``step_m`` steps, strictly before the 1 cm point that
    stopped it.  It stops at the first hard limit or unreachable point.  A ray stopped by the place-target exclusion
    ends at the exact intersection of the ray with the exclusion circle, provided that point is reachable.  The kind is
    ``REACH`` for a reachability limit and the hard-limit name otherwise.  A ray that ended without a block keeps
    its radius.
    """

    last = coarse.last_feasible_m
    kind = LIMIT_REACH
    evaluated: list[tuple[float, str]] = []
    if coarse.first_blocked_m is None:
        return RefinedLimit(last, kind, ())
    ceiling = coarse.first_blocked_m
    index = 1
    stop_kind = None
    while True:
        radius = _plain(coarse.last_feasible_m + index * step_m)
        if radius >= ceiling - _EPS:
            break
        x, y = point_on_ray(centre, ray_name, radius)
        violation = limit_check(x, y)
        if violation is not None:
            stop_kind = violation
            break
        ok = reachable(x, y)
        evaluated.append((radius, "REACHABLE" if ok else "UNREACHABLE"))
        if not ok:
            return RefinedLimit(last, LIMIT_REACH, tuple(evaluated))
        last = radius
        index += 1
    blocker = stop_kind or (coarse.reason if coarse.reason != REASON_UNREACHABLE else None)
    if blocker == LIMIT_PLACE_TARGET:
        entry = place_exclusion_entry_radius(centre, ray_name, lower_m=last)
        if entry is not None and entry <= ceiling + _EPS:
            x, y = point_on_ray(centre, ray_name, entry)
            ok = reachable(x, y)
            evaluated.append((entry, "REACHABLE" if ok else "UNREACHABLE"))
            if ok:
                return RefinedLimit(entry, LIMIT_PLACE_TARGET, tuple(evaluated))
            return RefinedLimit(last, LIMIT_REACH, tuple(evaluated))
    if blocker is not None:
        kind = blocker
    return RefinedLimit(last, kind, tuple(evaluated))


# --- live bracket ----------------------------------------------------------------------------------------------
#: Design Q3: stop at a 1 cm bracket or after three bisection rounds, then repeat the boundary once.
STOP_BRACKET_M = 0.01
MAX_BISECTION_ROUNDS = 3
REPEAT_STEP_BACK_M = 0.01

PHASE_SEARCH = "SEARCH"
PHASE_REPEAT = "REPEAT"
PHASE_FINAL = "FINAL"
PROBE_CEILING = "ceiling"
PROBE_MIDPOINT = "midpoint"
PROBE_REPEAT = "repeat"
PROBE_VERIFY = "verify"
#: A failed verification or repeat steps back to the previous 2 mm point, at most this many times; then the 1 cm result.
MAX_STEP_BACKS = 2
SOURCE_REPEAT_PASSED = "repeat_passed"
SOURCE_FALLBACK_1CM = "fallback_1cm"
SOURCE_COARSE_UNCHANGED = "coarse_unchanged"


@dataclass(frozen=True, slots=True)
class Bracket:
    """Search state of one ray.

    ``lo_m`` is the largest radius with a Teacher PASS (0.0 is the centre, which lies inside the current data and is
    taken as a success).  ``hi_m`` is the smallest radius with a Teacher failure, None while none was seen.
    ``ceiling_m`` is the offline kinematic limit, the first thing probed.  ``boundary_m`` is set once ``phase`` is FINAL;
    ``boundary_verified`` is False when the repeat failed and the boundary stepped back without a further run.
    """

    ray: str
    ceiling_m: float
    lo_m: float
    hi_m: float | None = None
    bisection_rounds: int = 0
    phase: str = PHASE_SEARCH
    boundary_m: float | None = None
    boundary_verified: bool | None = None
    #: Verification mode (design amendment 1).  ``ladder_m`` lists the refined radii to verify, best first; the 1 cm result
    #: ``coarse_m`` (Teacher PASS in the earlier rounds) is the fallback.  ``ladder_index`` is the candidate being verified,
    #: ``failures`` counts failed verifications or repeats.  Empty ``ladder_m`` means the ordinary bisection mode.
    ladder_m: tuple = ()
    ladder_index: int = 0
    failures: int = 0
    coarse_m: float | None = None
    limit_kind: str = LIMIT_REACH
    boundary_source: str | None = None


@dataclass(frozen=True, slots=True)
class Probe:
    kind: str
    radius_m: float


def initial_bracket(ray: str, ceiling_m: float, verified_m: float = 0.0, kind: str = LIMIT_REACH) -> Bracket:
    """Bisection-mode bracket.  ``verified_m`` is the largest radius with a known Teacher PASS (0.0: the centre)."""

    if ray not in RAY_NAMES or ceiling_m < 0.0 or verified_m < 0.0:
        raise ValueError("BOUNDARY_BRACKET_INVALID")
    ceiling, verified = _plain(ceiling_m), _plain(verified_m)
    if ceiling <= 0.0:
        return Bracket(ray, ceiling, 0.0, phase=PHASE_FINAL, boundary_m=0.0, boundary_verified=False, limit_kind=kind)
    if ceiling <= verified + _EPS:
        return Bracket(ray, ceiling, verified, phase=PHASE_FINAL, boundary_m=verified, boundary_verified=True,
                       limit_kind=kind, boundary_source=SOURCE_COARSE_UNCHANGED)
    return Bracket(ray, ceiling, verified, limit_kind=kind)


def refined_bracket(ray: str, coarse_m: float, refined_m: float, kind: str, step_m: float = REFINE_STEP_M) -> Bracket:
    """Verification-mode bracket: verify ``refined_m`` (then up to two 2 mm step-backs), fall back to ``coarse_m``.

    A ray whose refinement found nothing beyond the 1 cm result is final at once: that radius was verified and repeated in
    the 1 cm rounds.
    """

    if ray not in RAY_NAMES or coarse_m < 0.0 or refined_m < coarse_m - _EPS:
        raise ValueError("BOUNDARY_BRACKET_INVALID")
    ladder = [_plain(refined_m - index * step_m) for index in range(MAX_STEP_BACKS + 1)]
    ladder = tuple(r for r in ladder if r > coarse_m + _EPS)
    if not ladder:
        return Bracket(ray, _plain(coarse_m), _plain(coarse_m), phase=PHASE_FINAL, boundary_m=_plain(coarse_m),
                       boundary_verified=True, coarse_m=_plain(coarse_m), limit_kind=kind, boundary_source=SOURCE_COARSE_UNCHANGED)
    return Bracket(ray, _plain(refined_m), _plain(coarse_m), ladder_m=ladder, coarse_m=_plain(coarse_m), limit_kind=kind)


def _verify_update(bracket: Bracket, probe: Probe, passed: bool) -> Bracket:
    if probe.kind == PROBE_VERIFY and passed:
        return replace(bracket, lo_m=probe.radius_m, phase=PHASE_REPEAT)
    if probe.kind == PROBE_REPEAT and passed:
        return replace(bracket, phase=PHASE_FINAL, boundary_m=bracket.lo_m, boundary_verified=True, boundary_source=SOURCE_REPEAT_PASSED)
    failures = bracket.failures + 1
    index = bracket.ladder_index + 1
    if failures > MAX_STEP_BACKS or index >= len(bracket.ladder_m):
        return replace(bracket, phase=PHASE_FINAL, lo_m=bracket.coarse_m, failures=failures, boundary_m=bracket.coarse_m,
                       boundary_verified=True, boundary_source=SOURCE_FALLBACK_1CM)
    return replace(bracket, phase=PHASE_SEARCH, lo_m=bracket.coarse_m, failures=failures, ladder_index=index)


def _search_done(bracket: Bracket) -> bool:
    if bracket.hi_m is None:
        return bracket.lo_m >= bracket.ceiling_m - _EPS
    return bracket.hi_m - bracket.lo_m <= STOP_BRACKET_M + _EPS or bracket.bisection_rounds >= MAX_BISECTION_ROUNDS


def bisection_next(bracket: Bracket) -> Probe | None:
    """The next radius to run for this ray, or None when the ray is finished.

    The first probe is the kinematic ceiling itself (the most optimistic radius); a failure there starts the bisection
    between the last success and that failure.  Once the bracket is at most 1 cm wide, or three bisection rounds have
    run, the last success is repeated once.
    """

    if bracket.phase == PHASE_FINAL:
        return None
    if bracket.ladder_m:
        if bracket.phase == PHASE_REPEAT:
            return Probe(PROBE_REPEAT, bracket.lo_m)
        return Probe(PROBE_VERIFY, bracket.ladder_m[bracket.ladder_index])
    if bracket.phase == PHASE_REPEAT:
        return Probe(PROBE_REPEAT, bracket.lo_m)
    if bracket.hi_m is None:
        return Probe(PROBE_CEILING, bracket.ceiling_m)
    return Probe(PROBE_MIDPOINT, _plain(round((bracket.lo_m + bracket.hi_m) / 2.0, 5)))


def bisection_update(bracket: Bracket, probe: Probe, passed: bool) -> Bracket:
    """Fold the Teacher verdict of ``probe`` into the bracket.  ``probe`` must be the one ``bisection_next`` returned."""

    if probe != bisection_next(bracket):
        raise ValueError("BOUNDARY_PROBE_MISMATCH")
    if bracket.ladder_m:
        return _verify_update(bracket, probe, passed)
    if probe.kind == PROBE_REPEAT:
        if passed:
            return replace(bracket, phase=PHASE_FINAL, boundary_m=bracket.lo_m, boundary_verified=True)
        stepped = _plain(max(0.0, bracket.lo_m - REPEAT_STEP_BACK_M))
        return replace(bracket, phase=PHASE_FINAL, boundary_m=stepped, boundary_verified=False)
    rounds = bracket.bisection_rounds + (1 if probe.kind == PROBE_MIDPOINT else 0)
    if passed:
        updated = replace(bracket, lo_m=probe.radius_m, bisection_rounds=rounds)
    else:
        updated = replace(bracket, hi_m=probe.radius_m, bisection_rounds=rounds)
    if not _search_done(updated):
        return updated
    if updated.lo_m <= 0.0:
        return replace(updated, phase=PHASE_FINAL, boundary_m=0.0, boundary_verified=False)
    return replace(updated, phase=PHASE_REPEAT)


def teacher_passed(manifest: dict) -> bool:
    """Teacher PASS as the earlier analyses read it from ``dynamic-execute-manifest.json``.

    Completed execution, endpoint result PASS, final state DONE and no failure.
    """

    task = manifest.get("teacher_task_result")
    return (
        manifest.get("teacher_execution_status") == "COMPLETED"
        and isinstance(task, dict)
        and task.get("result") == "PASS"
        and manifest.get("current_state") == "DONE"
        and manifest.get("failure") is None
    )
