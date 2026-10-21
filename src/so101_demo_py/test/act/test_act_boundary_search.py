"""State documents of the live search: scene ids, the sidecar probes and a whole simulated search."""

import json

import pytest

from so101_demo.act import boundary_search as bs
from so101_demo.act import scene_boundary as sb

TRUE_RADIUS = {"E": 0.115, "NE": 0.06, "N": 0.02, "NW": 0.0, "W": 0.05, "SW": 0.083, "S": 0.14, "SE": 0.09}


def limits(ceiling=0.15):
    rays = {name: {"last_feasible_m": ceiling, "first_blocked_m": ceiling + 0.01, "reason": "UNREACHABLE"} for name in sb.RAY_NAMES}
    return {"kind": bs.LIMITS_KIND, "centre_xy": list(sb.DEFAULT_CENTRE_XY), "rays": rays}


def teacher(pending):
    """A Teacher whose success region along each ray ends at TRUE_RADIUS."""

    return {probe["scene_id"]: {"teacher_pass": probe["radius_m"] <= TRUE_RADIUS[name] + 1e-9} for name, probe in pending["probes"].items()}


def test_the_first_round_probes_every_ray_at_its_ceiling_with_named_scene_ids():
    pending, scenes = bs.round_state(bs.initial_state(limits()))
    rows = scenes["scenarios"]
    assert [row["scene_id"] for row in rows] == [f"bnd-{name}-r1" for name in sb.RAY_NAMES]
    assert {row["split"] for row in rows} == {"functional"} and len({row["seed"] for row in rows}) == 8
    assert rows[0]["cup_position_world_m"] == [0.17, -0.29, 0.165]
    assert pending["status"] == bs.STATUS_PENDING and pending["round"] == 1
    assert pending["probes"]["N"] == {"kind": "ceiling", "radius_m": 0.15, "scene_id": "bnd-N-r1", "xy": [0.02, -0.14]}


def test_a_state_must_be_updated_before_the_next_round_and_pending_before_the_update():
    state = bs.initial_state(limits())
    pending, _ = bs.round_state(state)
    with pytest.raises(ValueError, match="BOUNDARY_STATE_NOT_UPDATED"):
        bs.round_state(pending)
    with pytest.raises(ValueError, match="BOUNDARY_STATE_NOT_PENDING"):
        bs.apply_verdicts(state, {})


def test_a_probe_without_a_verdict_is_an_error_not_a_failure():
    pending, _ = bs.round_state(bs.initial_state(limits()))
    verdicts = teacher(pending)
    del verdicts["bnd-E-r1"]
    with pytest.raises(ValueError, match="BOUNDARY_VERDICT_MISSING: bnd-E-r1"):
        bs.apply_verdicts(pending, verdicts)


def test_a_whole_search_converges_on_the_teacher_boundary_of_every_ray():
    state, rounds = bs.initial_state(limits()), 0
    while True:
        pending, scenes = bs.round_state(state)
        if scenes is None:
            break
        rounds += 1
        assert rounds <= 6  # ceiling + 3 bisection rounds + repeat, plus the step-back case
        state = bs.apply_verdicts(pending, teacher(pending))
        json.dumps(state)
    assert bs.is_finished(state)
    for name, bracket in state["brackets"].items():
        boundary_m = bracket["boundary_m"]
        assert boundary_m <= TRUE_RADIUS[name] + 1e-9, name
        assert TRUE_RADIUS[name] - boundary_m < 0.0501, name  # bisection ends within the last (up to 3 rounds) bracket
    assert state["brackets"]["E"]["boundary_verified"] is True
    assert state["brackets"]["NW"]["boundary_m"] == 0.0
    assert set(state["boundary_points"]) == set(sb.RAY_NAMES)
    assert state["boundary_points"]["E"] == list(sb.point_on_ray(sb.DEFAULT_CENTRE_XY, "E", state["brackets"]["E"]["boundary_m"]))
    assert [h["round"] for h in state["history"]["S"]] == list(range(1, len(state["history"]["S"]) + 1))


def test_a_finished_ray_runs_a_filler_so_every_round_keeps_eight_scenes():
    state = bs.initial_state(limits(0.04))
    state["brackets"]["NW"] = {**state["brackets"]["NW"], "phase": "FINAL", "boundary_m": 0.02, "boundary_verified": True}
    pending, scenes = bs.round_state(state)
    assert len(scenes["scenarios"]) == 8 and pending["probes"]["NW"]["kind"] == "filler"
    assert pending["probes"]["NW"]["radius_m"] == 0.02
    verdicts = {p["scene_id"]: {"teacher_pass": name != "NW"} for name, p in pending["probes"].items()}
    state = bs.apply_verdicts(pending, verdicts)
    assert state["brackets"]["NW"]["boundary_m"] == 0.02 and state["brackets"]["NW"]["phase"] == "FINAL"  # unchanged
    assert state["history"]["NW"][0]["teacher_pass"] is False and state["history"]["NW"][0]["kind"] == "filler"


def test_repeat_failure_steps_back_and_a_finished_search_has_no_round():
    state = bs.initial_state(limits(0.04))
    pending, _ = bs.round_state(state)
    state = bs.apply_verdicts(pending, {p["scene_id"]: {"teacher_pass": True} for p in pending["probes"].values()})
    pending, scenes = bs.round_state(state)  # round 2 is the repeat at 0.04
    assert [p["kind"] for p in pending["probes"].values()] == ["repeat"] * 8 and len(scenes["scenarios"]) == 8
    state = bs.apply_verdicts(pending, {p["scene_id"]: {"teacher_pass": name != "E"} for name, p in pending["probes"].items()})
    assert state["brackets"]["E"]["boundary_m"] == 0.03 and state["brackets"]["E"]["boundary_verified"] is False
    assert bs.round_state(state)[1] is None


def test_limits_of_the_wrong_kind_are_refused():
    with pytest.raises(ValueError, match="BOUNDARY_LIMITS_INVALID"):
        bs.initial_state({"kind": "other", "rays": {}})


def refined_limits():
    rays = {name: {"last_feasible_m": 0.058, "limit_kind": "REACH"} for name in sb.RAY_NAMES}
    rays["W"] = {"last_feasible_m": 0.087, "limit_kind": "PLACE_TARGET"}
    rays["S"] = {"last_feasible_m": 0.05, "limit_kind": "REACH"}
    return {"kind": bs.LIMITS_KIND, "centre_xy": list(sb.DEFAULT_CENTRE_XY), "rays": rays}


VERIFIED = {name: 0.05 for name in sb.RAY_NAMES}


def test_the_initial_state_picks_a_mode_per_ray_from_the_earlier_verified_radius():
    state = bs.initial_state(refined_limits(), VERIFIED)
    assert state["brackets"]["E"]["ladder_m"] == [0.058, 0.056, 0.054] or tuple(state["brackets"]["E"]["ladder_m"]) == (0.058, 0.056, 0.054)
    assert state["brackets"]["W"]["ladder_m"] in ([], ()) and state["brackets"]["W"]["lo_m"] == 0.05  # bisection from 0.05
    assert state["brackets"]["S"]["phase"] == "FINAL" and state["brackets"]["S"]["boundary_m"] == 0.05
    with pytest.raises(ValueError, match="BOUNDARY_LIMIT_BELOW_VERIFIED: S"):
        bs.initial_state(refined_limits(), {**VERIFIED, "S": 0.06})


def test_a_verification_search_ends_with_boundary_points_and_their_limit_kinds():
    state = bs.initial_state(refined_limits(), VERIFIED)
    truth = {name: 0.058 for name in sb.RAY_NAMES}
    truth["N"], truth["W"] = 0.055, 0.0685
    rounds = 0
    while True:
        pending, scenes = bs.round_state(state)
        if scenes is None:
            break
        rounds += 1
        assert rounds <= 7
        state = bs.apply_verdicts(pending, {p["scene_id"]: {"teacher_pass": p["radius_m"] <= truth[name] + 1e-9}
                                            for name, p in pending["probes"].items()})
        json.dumps(state)
    brackets = state["brackets"]
    assert brackets["E"]["boundary_m"] == 0.058 and state["boundary_kinds"]["E"] == "REACH"
    assert brackets["N"]["boundary_m"] == 0.054 and brackets["N"]["boundary_source"] == "repeat_passed"
    assert state["boundary_kinds"]["N"] == "REACH"  # a Teacher failure set it
    assert brackets["W"]["boundary_m"] == 0.0685 and state["boundary_kinds"]["W"] == "REACH"
    assert brackets["S"]["boundary_source"] == "coarse_unchanged"
    assert set(state["boundary_points"]) == set(sb.RAY_NAMES) == set(state["boundary_kinds"])


def test_a_ray_at_its_hard_limit_keeps_the_hard_limit_kind_when_the_teacher_passes():
    state = bs.initial_state({**refined_limits(), "rays": {**refined_limits()["rays"], "W": {"last_feasible_m": 0.055, "limit_kind": "PLACE_TARGET"}}}, VERIFIED)
    while True:
        pending, scenes = bs.round_state(state)
        if scenes is None:
            break
        state = bs.apply_verdicts(pending, {p["scene_id"]: {"teacher_pass": True} for p in pending["probes"].values()})
    assert state["boundary_kinds"]["W"] == "PLACE_TARGET" and state["brackets"]["W"]["boundary_m"] == 0.055
