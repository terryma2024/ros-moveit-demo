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
    independent_sweep_check,
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


def test_the_smoke_entry_point_plans_against_a_real_seal(tmp_path) -> None:
    import json

    from so101_demo.cli.head_search_smoke import main

    seal = {
        "seal_sha256": "a" * 64,
        "horizontal_fov_rad": 1.3121067481206794,
        "lock_valid_neck_rad": list(SAFE),
        "required_search_domain_rad": [-0.29145679447786704, 0.540419500270584],
        "anchors": {"default": {"neck_rad": 0.1}},
        "camera": {"coarse_step_rad": 0.3},
    }
    path = tmp_path / "seal.json"
    path.write_text(json.dumps(seal), encoding="utf-8")

    assert (
        main(
            ["--geometry-seal", str(path), "--anchor", "default", "--output", str(tmp_path / "run")]
        )
        == 0
    )
    report = json.loads((tmp_path / "run" / "head-search-plan-default.json").read_text())
    assert report["coverage_complete"] is True and report["stop_count"] >= 2
    # a domain the safe interval cannot cover is refused before any motion
    seal["required_search_domain_rad"] = [-9.0, 9.0]
    path.write_text(json.dumps(seal), encoding="utf-8")
    assert main(["--geometry-seal", str(path), "--anchor", "default"]) == 2


def test_the_controller_walks_the_bounded_plan_instead_of_a_full_revolution() -> None:
    from so101_demo.act.search import HeadSearchController

    config = {
        "attempt_id": "attempt",
        "session_id": "session",
        "search_start_rad": 0.1,
        "horizontal_fov_rad": 1.0,
        "coarse_step_rad": 0.5,
        "search_timeout_s": 30.0,
        "max_age_s": 0.1,
        "max_skew_s": 0.05,
        "settle_velocity_rad_s": 0.1,
        "goal_tolerance_rad": 0.05,
        "center_deadband_px": 20.0,
        "vertical_bounds_px": [100.0, 380.0],
        "min_area_px2": 64.0,
        "min_confidence": 0.4,
        "max_fine_corrections": 3,
        "max_fine_total_rad": 0.5,
        "frame_id": "camera",
        "ray_origin_frame_id": "base",
        "required_domain_rad": [-2.5, 2.5],
        "lock_valid_neck_rad": list(SAFE),
    }
    controller = HeadSearchController(config)
    assert controller.plan is not None and controller.plan.coverage_complete
    walked = []
    while True:
        target = controller.next_target()
        if target is None:
            break
        walked.append(target)
    assert walked == list(controller.plan.targets_rad)
    assert max(walked) <= SAFE[1] and min(walked) >= SAFE[0]
    assert controller.plan.not_found_status(reached_bound=True) == (
        TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL
    )


def test_the_independent_sweep_checker_agrees_only_with_a_real_coverage_proof() -> None:
    from so101_demo.act.head_search_domain import independent_sweep_check

    plan = bounded_search_stops(
        anchor_rad=0.1,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=SAFE,
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
    )
    ok, reason = independent_sweep_check(plan, required_domain_rad=(-2.5, 2.5))
    assert ok, reason

    # a plan that stops short of an endpoint does not cover the domain
    short = type(plan)(
        targets_rad=tuple(target for target in plan.targets_rad if target > -2.0),
        coverage_complete=True,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=SAFE,
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
        anchor_rad=0.1,
    )
    ok, reason = independent_sweep_check(short, required_domain_rad=(-2.5, 2.5))
    assert not ok and "not covered" in reason

    # a stop outside the safe interval is refused even if the geometry would cover the domain
    unsafe = type(plan)(
        targets_rad=(*plan.targets_rad, SAFE[1] + 0.5),
        coverage_complete=True,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=SAFE,
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
        anchor_rad=0.1,
    )
    ok, reason = independent_sweep_check(unsafe, required_domain_rad=(-2.5, 2.5))
    assert not ok and "safe interval" in reason


def test_a_domain_reaching_past_the_safe_interval_is_still_served_by_the_field_of_view() -> None:
    """The reviewer's finding: a coverable domain must not be refused just because its ends exceed the bound."""

    plan = bounded_search_stops(
        anchor_rad=0.0,
        required_domain_rad=(-2.5, 2.5),
        safe_interval_rad=(-2.0, 2.0),
        horizontal_fov_rad=1.0,
        coarse_step_rad=0.5,
    )
    assert plan.coverage_complete
    assert max(plan.targets_rad) <= 2.0 and min(plan.targets_rad) >= -2.0
    ok, reason = independent_sweep_check(plan, required_domain_rad=(-2.5, 2.5))
    assert ok, reason
    # a domain the field of view cannot reach from the bound is still refused before motion
    with pytest.raises(HeadSearchDomainError, match="HEAD_SEARCH_DOMAIN_UNSAFE"):
        bounded_search_stops(
            anchor_rad=0.0,
            required_domain_rad=(-2.9, 2.9),
            safe_interval_rad=(-2.0, 2.0),
            horizontal_fov_rad=1.0,
            coarse_step_rad=0.5,
        )


def test_the_smoke_refuses_when_no_sealed_step_exists(tmp_path) -> None:
    import json

    from so101_demo.cli.head_search_smoke import main

    seal = {
        "horizontal_fov_rad": 1.0,
        "lock_valid_neck_rad": list(SAFE),
        "required_search_domain_rad": [-0.2, 0.5],
        "anchors": {"default": {"neck_rad": 0.1}},
    }
    path = tmp_path / "seal.json"
    path.write_text(json.dumps(seal), encoding="utf-8")
    assert main(["--geometry-seal", str(path), "--anchor", "default"]) == 2
    contract = tmp_path / "contract.json"
    contract.write_text(json.dumps({"coarse_step_candidate_rad": 0.3}), encoding="utf-8")
    contract = tmp_path / "contract.json"
    # a contract that does not name this seal cannot supply the step
    contract.write_text(json.dumps({"coarse_step_candidate_rad": 0.3}), encoding="utf-8")
    assert (
        main(["--geometry-seal", str(path), "--anchor", "default", "--contract", str(contract)])
        == 2
    )
    seal["seal_sha256"] = "b" * 64
    path.write_text(json.dumps(seal), encoding="utf-8")
    # the step is applied only when a supplied document names this very seal
    contract.write_text(
        json.dumps({"coarse_step_candidate_rad": 0.3, "accepted_seal_sha256": "c" * 64}),
        encoding="utf-8",
    )
    assert (
        main(["--geometry-seal", str(path), "--anchor", "default", "--contract", str(contract)]) == 2
    ), "a document naming another seal cannot supply the step"
    contract.write_text(
        json.dumps({"coarse_step_candidate_rad": 0.3, "accepted_seal_sha256": "b" * 64}),
        encoding="utf-8",
    )
    assert (
        main(["--geometry-seal", str(path), "--anchor", "default", "--contract", str(contract)])
        == 0
    )


def test_only_the_three_statuses_are_search_outcomes() -> None:
    from so101_demo.act.head_search_domain import (
        QUALIFICATION_STATUSES,
        qualification_status_of,
    )

    assert QUALIFICATION_STATUSES == (
        TARGET_LOCKED,
        TARGET_NOT_FOUND,
        TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL,
    )
    assert qualification_status_of(TARGET_LOCKED) == TARGET_LOCKED
    assert qualification_status_of(TARGET_NOT_FOUND) == TARGET_NOT_FOUND
    for diagnostic in (
        "SEARCH_TIMEOUT",
        "SEARCH_UNSAFE",
        "TARGET_AMBIGUOUS",
        "TARGET_NOT_CENTERED",
    ):
        assert qualification_status_of(diagnostic) is None, (
            f"{diagnostic} is a diagnostic, not a search outcome"
        )
