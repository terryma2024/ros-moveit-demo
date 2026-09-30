"""Bounded two-direction head search: the stop plan and its coverage proof.

The search visits the nearer end of the required camera domain first, reverses exactly once, and proves
coverage from the field-of-view interval each stop actually gives - not from an accumulated angle, which
would claim coverage the camera never had. Every target must sit inside the safe neck interval, so an
uncoverable required domain is refused before any motion.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

#: the three statuses a head search may end with, exactly
TARGET_LOCKED = "TARGET_LOCKED"
TARGET_NOT_FOUND = "TARGET_NOT_FOUND"
TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL = "TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL"


#: the only statuses a head search outcome may carry for qualification; anything else is a diagnostic
QUALIFICATION_STATUSES = (TARGET_LOCKED, TARGET_NOT_FOUND, TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL)


def qualification_status_of(status: str) -> str | None:
    """The search outcome a controller status maps to, or None when it is a diagnostic rather than one.

    The controller also reports operational diagnostics - a timeout, an unsafe observation, an ambiguous
    target, a target it could not centre - and those are refusals, not search outcomes: qualification only
    reads the three statuses above, so a diagnostic must never be mistaken for a completed search.
    """

    return status if status in QUALIFICATION_STATUSES else None


class HeadSearchDomainError(ValueError):
    """A domain the search must refuse, named so a caller can refuse by name."""


@dataclass(frozen=True, slots=True)
class SearchStopPlan:
    """The stops one bounded search performs, and what they provably cover."""

    targets_rad: tuple[float, ...]
    coverage_complete: bool
    required_domain_rad: tuple[float, float]
    safe_interval_rad: tuple[float, float]
    horizontal_fov_rad: float
    coarse_step_rad: float
    anchor_rad: float

    def not_found_status(self, *, reached_bound: bool) -> str:
        """A missing target is only a clean negative after complete coverage."""

        if not self.coverage_complete or reached_bound:
            return TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL
        return TARGET_NOT_FOUND


def _interval(name: str, value: Sequence[float]) -> tuple[float, float]:
    if isinstance(value, (str, bytes)) or len(tuple(value)) != 2:
        raise HeadSearchDomainError(f"HEAD_SEARCH_DOMAIN_INVALID: {name} must be two finite bounds")
    low, high = (float(bound) for bound in value)
    if not math.isfinite(low) or not math.isfinite(high) or low > high:
        raise HeadSearchDomainError(
            f"HEAD_SEARCH_DOMAIN_INVALID: {name} must be finite and ordered"
        )
    return low, high


def coverage_is_complete(plan: SearchStopPlan, *, required_domain_rad: Sequence[float]) -> bool:
    """Whether the stable field-of-view intervals of the plan's stops cover the required domain.

    A point is covered when some stop lies within half a field of view of it *and* that stop is inside the
    safe interval; the union of those intervals - never an accumulated sweep angle - is the evidence.
    """

    low, high = _interval("required_domain_rad", required_domain_rad)
    safe_low, safe_high = plan.safe_interval_rad
    half = plan.horizontal_fov_rad / 2.0
    if not plan.targets_rad:
        return False
    for target in plan.targets_rad:
        if not safe_low <= target <= safe_high:
            return False
    intervals = sorted(
        (target - half, target + half)
        for target in plan.targets_rad
        if safe_low <= target <= safe_high
    )
    reach = low
    for start, stop in intervals:
        if start > reach + 1e-9:
            return False
        reach = max(reach, min(stop, high))
        if reach >= high - 1e-9:
            return True
    return reach >= high - 1e-9


def independent_sweep_check(
    plan: SearchStopPlan,
    *,
    required_domain_rad: Sequence[float],
    samples: int = 4_001,
) -> tuple[bool, str]:
    """A second, deliberately different derivation of the plan's coverage claim.

    `coverage_is_complete` merges field-of-view intervals; this checker instead walks the required domain
    point by point and also inspects the legs between consecutive stops, so the two agree only when the
    plan really covers what it claims. It returns the reason for any disagreement.
    """

    low, high = _interval("required_domain_rad", required_domain_rad)
    safe_low, safe_high = plan.safe_interval_rad
    half = plan.horizontal_fov_rad / 2.0
    if not plan.targets_rad:
        return False, "the plan commands no stop at all"
    for target in plan.targets_rad:
        if not safe_low - 1e-9 <= target <= safe_high + 1e-9:
            return False, f"stop {target} leaves the safe interval"
    step = (high - low) / (samples - 1)
    for index in range(samples):
        point = low + index * step
        if not any(abs(point - target) <= half + 1e-9 for target in plan.targets_rad):
            return False, f"the required domain is not covered at {point}"
    moves = [plan.anchor_rad, *plan.targets_rad]
    for first, second in zip(moves, moves[1:]):
        if abs(second - first) > plan.horizontal_fov_rad + 1e-9:
            return False, f"the leg from {first} to {second} is longer than a field of view"
    directions = [1 if second > first else -1 for first, second in zip(moves, moves[1:])]
    reversals = sum(1 for first, second in zip(directions, directions[1:]) if first != second)
    if reversals > 1:
        return False, f"the sweep reverses {reversals} times"
    if plan.coarse_step_rad > half + 1e-12:
        return False, "the coarse step exceeds half a field of view"
    return True, "covered"


def bounded_search_stops(
    *,
    anchor_rad: float,
    required_domain_rad: Sequence[float],
    safe_interval_rad: Sequence[float],
    horizontal_fov_rad: float,
    coarse_step_rad: float,
) -> SearchStopPlan:
    """Visit the nearer coverage endpoint first, reverse once, and prove FOV-union coverage."""

    anchor = float(anchor_rad)
    if not math.isfinite(anchor):
        raise HeadSearchDomainError("HEAD_SEARCH_DOMAIN_INVALID: the anchor must be finite")
    low, high = _interval("required_domain_rad", required_domain_rad)
    safe_low, safe_high = _interval("safe_interval_rad", safe_interval_rad)
    fov = float(horizontal_fov_rad)
    step = float(coarse_step_rad)
    if not math.isfinite(fov) or fov <= 0.0:
        raise HeadSearchDomainError(
            "HEAD_SEARCH_DOMAIN_INVALID: the field of view must be positive"
        )
    if not math.isfinite(step) or step <= 0.0:
        raise HeadSearchDomainError("HEAD_SEARCH_DOMAIN_INVALID: the coarse step must be positive")
    if step > fov / 2.0 + 1e-12:
        raise HeadSearchDomainError(
            "HEAD_SEARCH_STEP_EXCEEDS_HALF_FOV: a coarse step larger than half the field of view cannot "
            "prove coverage"
        )
    if low < safe_low - 1e-9 or high > safe_high + 1e-9:
        # the stops may sit anywhere in the safe interval, so the domain is still reachable within half a
        # field of view of its ends; anything wider is refused before any motion
        if low < safe_low - fov / 2.0 - 1e-9 or high > safe_high + fov / 2.0 + 1e-9:
            raise HeadSearchDomainError(
                "HEAD_SEARCH_DOMAIN_UNSAFE: the safe neck interval cannot cover the required domain"
            )
    if not safe_low - 1e-9 <= anchor <= safe_high + 1e-9:
        raise HeadSearchDomainError(
            "HEAD_SEARCH_DOMAIN_UNSAFE: the search starts outside the safe neck interval"
        )
    nearer, farther = (high, low) if abs(high - anchor) <= abs(anchor - low) else (low, high)
    # the plan commands moves, so it starts at the first step away from the anchor: commanding the angle
    # the neck already holds would add a zero-length leg and a spurious direction change
    targets: list[float] = []
    current = anchor
    for endpoint in (nearer, farther):
        # never command outside the safe interval: the last stop of a leg is clamped to the bound and the
        # field of view of that stop is what covers the rest of the required domain
        endpoint = min(max(endpoint, safe_low), safe_high)
        if abs(endpoint - current) <= 1e-12:
            continue
        direction = 1.0 if endpoint > current else -1.0
        remaining = abs(endpoint - current)
        travel = 0.0
        while travel < remaining - 1e-12:
            travel = min(remaining, travel + step)
            targets.append(current + direction * travel)
        current = endpoint
    plan = SearchStopPlan(
        targets_rad=tuple(targets),
        coverage_complete=False,
        required_domain_rad=(low, high),
        safe_interval_rad=(safe_low, safe_high),
        horizontal_fov_rad=fov,
        coarse_step_rad=step,
        anchor_rad=anchor,
    )
    complete = coverage_is_complete(plan, required_domain_rad=(low, high))
    return SearchStopPlan(
        targets_rad=plan.targets_rad,
        coverage_complete=complete,
        required_domain_rad=plan.required_domain_rad,
        safe_interval_rad=plan.safe_interval_rad,
        horizontal_fov_rad=plan.horizontal_fov_rad,
        coarse_step_rad=plan.coarse_step_rad,
        anchor_rad=plan.anchor_rad,
    )
