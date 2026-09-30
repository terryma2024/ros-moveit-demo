"""The bounded head-search domain: stop plan, coverage proof and the three exact statuses."""

from __future__ import annotations

import math

import pytest
from so101_demo.act.head_search_domain import (
    TARGET_LOCKED,
    TARGET_NOT_FOUND,
    TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL,
    HeadSearchDomainError,
    bounded_search_stops,
    coverage_is_complete,
)

SAFE = (-2 * math.pi + 1e-5, 2 * math.pi - 1e-5)


def test_default_anchor_never_commands_past_safe_upper_bound() -> None:
    plan = bounded_search_stops(
        anchor_rad=0.1,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=SAFE,
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
    )

    assert max(plan.targets_rad) <= 2 * math.pi - 1e-5
    assert plan.coverage_complete


def test_the_nearer_endpoint_is_visited_first_and_the_direction_reverses_once() -> None:
    plan = bounded_search_stops(
        anchor_rad=0.1,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=SAFE,
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
    )

    # |2.5 - 0.1| < |0.1 - (-2.5)|, so the sweep's first move is upwards from the anchor
    assert plan.targets_rad[0] > 0.1
    directions = []
    previous = 0.1
    for target in plan.targets_rad:
        directions.append(1 if target > previous else -1)
        previous = target
    reversals = sum(1 for first, second in zip(directions, directions[1:]) if first != second)
    assert reversals <= 1, f"the sweep must reverse at most once, saw {reversals}"


def test_every_target_stays_inside_the_safe_interval_and_close_enough_to_cover() -> None:
    plan = bounded_search_stops(
        anchor_rad=0.1,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=SAFE,
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
    )

    assert all(SAFE[0] <= target <= SAFE[1] for target in plan.targets_rad)
    ordered = sorted(plan.targets_rad)
    for first, second in zip(ordered, ordered[1:]):
        assert second - first <= 0.5 + 1e-9, "no gap may exceed the coarse step"


def test_coverage_is_proven_by_stable_intervals_not_accumulated_angle() -> None:
    plan = bounded_search_stops(
        anchor_rad=0.1,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=SAFE,
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
    )

    assert coverage_is_complete(plan, required_domain_rad=(-2.5, 2.5))
    # a plan whose targets skip a stretch of the domain cannot claim coverage
    broken = type(plan)(
        targets_rad=(0.0,),
        coverage_complete=True,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=SAFE,
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
        anchor_rad=0.0,
    )
    assert not coverage_is_complete(broken, required_domain_rad=(-2.5, 2.5))


def test_an_uncoverable_required_domain_is_rejected_before_motion() -> None:
    with pytest.raises(HeadSearchDomainError, match="HEAD_SEARCH_DOMAIN_UNSAFE"):
        bounded_search_stops(
            anchor_rad=0.0,
            required_domain_rad=(-3.0, 3.0),
            safe_interval_rad=(-1.0, 1.0),
            horizontal_fov_rad=1.0,
            coarse_step_rad=0.5,
        )


def test_the_three_statuses_are_the_declared_ones() -> None:
    assert (TARGET_LOCKED, TARGET_NOT_FOUND, TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL) == (
        "TARGET_LOCKED",
        "TARGET_NOT_FOUND",
        "TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL",
    )
    plan = bounded_search_stops(
        anchor_rad=0.1,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=SAFE,
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
    )
    assert plan.not_found_status(reached_bound=True) == TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL
    assert plan.not_found_status(reached_bound=False) == TARGET_NOT_FOUND
