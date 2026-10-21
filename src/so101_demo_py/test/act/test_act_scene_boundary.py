"""Ray geometry, hard limits, the kinematic limit and the live bracket of the Teacher boundary search."""

import math

import pytest

from so101_demo.act import scene_boundary as sb


def test_eight_rays_are_45_degrees_apart_and_start_one_step_from_the_centre():
    rays = sb.ray_candidates()
    assert tuple(rays) == ("E", "NE", "N", "NW", "W", "SW", "S", "SE")
    assert rays["E"][0] == (0.01, 0.03, -0.29)
    assert rays["N"][0] == (0.01, 0.02, -0.28)
    assert rays["W"][2] == (0.03, -0.01, -0.29)
    assert rays["S"][0].y == -0.30
    for index, name in enumerate(sb.RAY_NAMES):
        point = rays[name][9]
        assert point.radius_m == 0.10
        assert math.dist((point.x, point.y), sb.DEFAULT_CENTRE_XY) == pytest.approx(0.10, abs=1e-6)
        angle = math.degrees(math.atan2(point.y - sb.DEFAULT_CENTRE_XY[1], point.x - sb.DEFAULT_CENTRE_XY[0])) % 360
        assert angle == pytest.approx(45.0 * index, abs=1e-3)
    assert len(rays["E"]) == 30
    assert all(type(value) is float and str(value) != "-0.0" for ray in rays.values() for p in ray for value in p)


@pytest.mark.parametrize("directions", [4, 16])
def test_only_eight_directions_are_supported(directions):
    with pytest.raises(ValueError, match="BOUNDARY_DIRECTIONS_UNSUPPORTED"):
        sb.ray_candidates(directions=directions)


def test_the_table_edge_keeps_the_cup_and_its_margin_on_the_table():
    # table x half extent 0.25, y -0.20 +/- 0.30; the cup radius 0.04 plus the margin 0.01 stay on top
    assert sb.hard_limit_violation(0.20, -0.30) is None
    assert sb.hard_limit_violation(0.2001, -0.30) == sb.LIMIT_TABLE_EDGE
    assert sb.hard_limit_violation(-0.2001, -0.30) == sb.LIMIT_TABLE_EDGE
    assert sb.hard_limit_violation(0.0, -0.45) is None
    assert sb.hard_limit_violation(0.0, -0.4501) == sb.LIMIT_TABLE_EDGE


def test_the_pedestal_footprint_is_grown_by_the_cup_radius_and_the_margin():
    # pedestal half extent 0.09 + 0.05 = 0.14 around the origin
    assert sb.hard_limit_violation(0.0, -0.13) == sb.LIMIT_PEDESTAL
    assert sb.hard_limit_violation(0.13, 0.0) == sb.LIMIT_PEDESTAL
    assert sb.hard_limit_violation(0.0, -0.1401) is None
    assert sb.hard_limit_violation(0.1401, -0.1) is None


def test_the_place_target_exclusion_is_60_mm_around_the_teacher_place_target():
    tx, ty = sb.PLACE_TARGET_XY
    assert sb.hard_limit_violation(tx, ty - 0.0599) == sb.LIMIT_PLACE_TARGET
    assert sb.hard_limit_violation(tx, ty - 0.0601) is None
    assert sb.hard_limit_violation(tx + 0.0601, ty) is None


def test_the_w_ray_hits_the_place_exclusion_before_the_table_edge():
    reachable = lambda x, y: True  # noqa: E731
    limit = sb.kinematic_limit(sb.ray_candidates()["W"], reachable)
    assert limit.reason == sb.LIMIT_PLACE_TARGET
    assert limit.last_feasible_m == pytest.approx(limit.first_blocked_m - 0.01)
    assert limit.first_blocked_m == pytest.approx(0.06)


def test_kinematic_limit_stops_at_the_first_unreachable_point():
    ray = sb.ray_candidates()["E"]
    seen = []

    def reachable(x, y):
        seen.append(round(x, 6))
        return x < 0.095

    limit = sb.kinematic_limit(ray, reachable)
    assert limit == sb.KinematicLimit(0.07, 0.08, sb.REASON_UNREACHABLE)
    assert seen[-1] == 0.1 and len(seen) == 8  # nothing beyond the first failure is asked


def test_kinematic_limit_does_not_ask_reachability_beyond_a_hard_limit():
    asked = []
    limit = sb.kinematic_limit(sb.ray_candidates()["S"], lambda x, y: asked.append(y) or True)
    assert limit.reason == sb.LIMIT_TABLE_EDGE
    assert min(asked) >= -0.45 - 1e-9
    assert limit.first_blocked_m == pytest.approx(0.17)


def test_kinematic_limit_of_an_open_ray_reports_the_ray_end_and_of_a_blocked_first_step_zero():
    ray = sb.ray_candidates(max_radius=0.03)["E"]
    assert sb.kinematic_limit(ray, lambda x, y: True) == sb.KinematicLimit(0.03, None, sb.REASON_RAY_END)
    assert sb.kinematic_limit(ray, lambda x, y: False) == sb.KinematicLimit(0.0, 0.01, sb.REASON_UNREACHABLE)


def _run(bracket, verdicts):
    """Feed verdicts to the bracket; return (probes in order, final bracket)."""

    probes = []
    for passed in verdicts:
        probe = sb.bisection_next(bracket)
        probes.append((probe.kind, probe.radius_m))
        bracket = sb.bisection_update(bracket, probe, passed)
    return probes, bracket


def test_a_ceiling_pass_goes_straight_to_the_repeat():
    probes, bracket = _run(sb.initial_bracket("E", 0.12), [True, True])
    assert probes == [("ceiling", 0.12), ("repeat", 0.12)]
    assert (bracket.phase, bracket.boundary_m, bracket.boundary_verified) == (sb.PHASE_FINAL, 0.12, True)
    assert sb.bisection_next(bracket) is None


def test_bisection_stops_after_three_rounds_then_repeats():
    # ceiling 0.20 fails; midpoints 0.10 pass, 0.15 fail, 0.125 pass (3 rounds, bracket 0.125..0.15 still 2.5 cm)
    probes, bracket = _run(sb.initial_bracket("N", 0.20), [False, True, False, True, True])
    assert probes == [("ceiling", 0.2), ("midpoint", 0.1), ("midpoint", 0.15), ("midpoint", 0.125), ("repeat", 0.125)]
    assert (bracket.lo_m, bracket.hi_m, bracket.bisection_rounds) == (0.125, 0.15, 3)
    assert (bracket.boundary_m, bracket.boundary_verified) == (0.125, True)


def test_bisection_stops_early_at_a_one_centimetre_bracket():
    probes, bracket = _run(sb.initial_bracket("S", 0.04), [False, True, True, True])
    # ceiling 0.04 fails; midpoints 0.02 and 0.03 pass; the bracket 0.03..0.04 is 1 cm after two rounds
    assert probes == [("ceiling", 0.04), ("midpoint", 0.02), ("midpoint", 0.03), ("repeat", 0.03)]
    assert bracket.bisection_rounds == 2 and bracket.boundary_m == 0.03


def test_a_failed_repeat_steps_back_one_centimetre():
    probes, bracket = _run(sb.initial_bracket("W", 0.08), [True, False])
    assert probes == [("ceiling", 0.08), ("repeat", 0.08)]
    assert (bracket.boundary_m, bracket.boundary_verified) == (0.07, False)
    assert bracket.phase == sb.PHASE_FINAL


def test_the_step_back_never_goes_below_the_centre():
    bracket = sb.Bracket("E", 0.04, 0.005, 0.01, 1, sb.PHASE_REPEAT)
    final = sb.bisection_update(bracket, sb.Probe(sb.PROBE_REPEAT, 0.005), False)
    assert final.boundary_m == 0.0


def test_a_ray_that_fails_everywhere_ends_at_the_centre_without_a_repeat():
    probes, bracket = _run(sb.initial_bracket("SW", 0.04), [False, False, False])
    assert [kind for kind, _ in probes] == ["ceiling", "midpoint", "midpoint"]
    assert (bracket.phase, bracket.boundary_m, bracket.boundary_verified) == (sb.PHASE_FINAL, 0.0, False)
    assert sb.initial_bracket("E", 0.0).phase == sb.PHASE_FINAL


def test_a_probe_that_is_not_the_next_one_is_refused():
    with pytest.raises(ValueError, match="BOUNDARY_PROBE_MISMATCH"):
        sb.bisection_update(sb.initial_bracket("E", 0.1), sb.Probe(sb.PROBE_MIDPOINT, 0.05), True)


def test_teacher_pass_needs_all_four_conditions():
    good = {"teacher_execution_status": "COMPLETED", "teacher_task_result": {"result": "PASS"},
            "current_state": "DONE", "failure": None}
    assert sb.teacher_passed(good)
    for key, value in (("teacher_execution_status", "FAILED"), ("teacher_task_result", {"result": "FAIL"}),
                       ("current_state", "ERROR"), ("failure", "TARGET_UNREACHABLE: x"), ("teacher_task_result", "PASS")):
        assert not sb.teacher_passed({**good, key: value})
    assert not sb.teacher_passed({})
