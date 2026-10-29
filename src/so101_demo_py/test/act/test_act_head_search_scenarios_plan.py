"""The qualification items, the frame cadence check and the settle and stop proofs."""

from __future__ import annotations

from head_search_scenarios_support import (
    ANCHORS,
    CONDITION_CLASSES,
    FRAME_PERIOD_S,
    _partition_items,
)
import pytest

from so101_demo.act.head_search.scenarios import plan as module_plan
from so101_demo.act.head_search.scenarios.contracts import (
    CAL_SCENARIO_SPLIT_LEAK,
    CalibrationScenarioRefused,
)
from so101_demo.act.head_search.scenarios.plan import (
    check_frame_cadence,
    expected_terminals,
    qualification_scenarios,
)
from so101_demo.act.head_search.scenarios.scenario_run import (
    hold_stop_samples,
)
from so101_demo.act.head_search.scenarios.stop_proof import settle_proof, stop_proof
from so101_demo.act.head_search.timing_measurement.contracts import (
    CAL_TIMING_EVIDENCE_MISSING,
)

MAX_SETTLE_S = 5.0


PARTITIONS = {
    "schema_version": 1,
    "document": "head-search-scenario-partitions/v1",
    "condition_classes": CONDITION_CLASSES,
    "anchors": ANCHORS,
    "calibration": [700000, 700001],
    "held_out_evaluation": [800000, 800001],
    "qualification": _partition_items(4),
}


def test_the_qualification_items_are_the_declared_list_in_declaration_order():
    items = qualification_scenarios(PARTITIONS)
    assert [item["seed"] for item in items] == [900000, 900001, 900002, 900003]
    assert items[1]["condition_class"] == "left_anchor"
    assert items[1]["anchor"] == "left"
    assert items[0]["scene_group_id"] == "scene-000900000"


def test_a_seed_of_another_split_is_refused_rather_than_qualified():
    with pytest.raises(CalibrationScenarioRefused) as refused:
        qualification_scenarios(PARTITIONS, seeds=[700000])

    assert refused.value.code == CAL_SCENARIO_SPLIT_LEAK
    assert "700000" in str(refused.value)


def test_a_seed_the_partition_does_not_carry_is_refused():
    with pytest.raises(CalibrationScenarioRefused) as refused:
        qualification_scenarios(PARTITIONS, seeds=[999999])

    assert refused.value.code == CAL_TIMING_EVIDENCE_MISSING


def test_a_duplicated_seed_is_refused_rather_than_run_twice():
    with pytest.raises(ValueError):
        qualification_scenarios(PARTITIONS, seeds=[900000, 900000])


def test_a_partition_that_declares_no_qualification_list_is_a_refusal():
    with pytest.raises(CalibrationScenarioRefused) as refused:
        qualification_scenarios({"calibration": [700000]})

    assert refused.value.code == CAL_TIMING_EVIDENCE_MISSING


def test_the_plan_step_three_terminals_are_declared_per_condition_class():
    """One cup locks, two cups are ambiguous, no cup is a clean negative."""

    assert expected_terminals("nominal") == ("TARGET_LOCKED",)
    assert expected_terminals("distractor_present") == ("TARGET_LOCKED",)
    assert expected_terminals("two_cups") == ("TARGET_AMBIGUOUS",)
    assert expected_terminals("no_cup") == ("TARGET_NOT_FOUND",)
    assert expected_terminals("fast_interruption") == ("TARGET_LOCKED",)
    assert expected_terminals("reacquire_after_stop") == ("TARGET_LOCKED",)


def test_every_declared_condition_class_has_a_declared_passing_terminal():
    for name in CONDITION_CLASSES:
        assert expected_terminals(name), name


def test_a_condition_class_the_partition_does_not_declare_is_refused():
    with pytest.raises(CalibrationScenarioRefused) as refused:
        expected_terminals("strobe_light")

    assert refused.value.code == CAL_TIMING_EVIDENCE_MISSING


def test_the_interruption_classes_declare_a_second_attempt_and_the_others_do_not():
    assert module_plan.requires_interruption("fast_interruption") is True
    assert module_plan.requires_interruption("reacquire_after_stop") is True
    assert module_plan.requires_interruption("nominal") is False


def _frames(intervals, *, start=0.0):
    frames = []
    stamp = start
    for index, interval in enumerate([None, *intervals]):
        if interval is not None:
            stamp += interval
        frames.append({"frame_index": index, "frame_sim_s": stamp})
    return frames


def test_the_cadence_check_accepts_frames_paced_at_the_declared_period():
    cadence = check_frame_cadence(
        _frames([FRAME_PERIOD_S] * 3, start=0.0),
        frame_period_s=FRAME_PERIOD_S,
        max_settle_s=MAX_SETTLE_S,
    )

    assert cadence["continuous"] is True
    assert cadence["frame_rate_hz"] == 10.0
    assert cadence["frame_count"] == 4
    assert cadence["interval_count"] == 3
    assert cadence["duplicate_count"] == 0
    assert cadence["backward_count"] == 0
    assert cadence["too_fast_count"] == 0
    assert cadence["undeclared_gap_count"] == 0
    assert cadence["achieved_rate_hz"] == pytest.approx(10.0)


def test_the_cadence_check_accepts_a_longer_interval_inside_the_settle_budget():
    cadence = check_frame_cadence(
        _frames([FRAME_PERIOD_S, MAX_SETTLE_S + FRAME_PERIOD_S], start=0.0),
        frame_period_s=FRAME_PERIOD_S,
        max_settle_s=MAX_SETTLE_S,
    )

    assert cadence["continuous"] is True
    assert cadence["gap_count"] == 1
    assert cadence["undeclared_gap_count"] == 0
    assert cadence["achieved_rate_hz"] < cadence["frame_rate_hz"]


def test_the_cadence_check_refuses_a_duplicate_frame_stamp():
    cadence = check_frame_cadence(
        _frames([FRAME_PERIOD_S, 0.0], start=0.0),
        frame_period_s=FRAME_PERIOD_S,
        max_settle_s=MAX_SETTLE_S,
    )

    assert cadence["continuous"] is False
    assert cadence["duplicate_count"] == 1


def test_the_cadence_check_refuses_a_frame_faster_than_the_contract():
    cadence = check_frame_cadence(
        _frames([FRAME_PERIOD_S / 2.0], start=0.0),
        frame_period_s=FRAME_PERIOD_S,
        max_settle_s=MAX_SETTLE_S,
    )

    assert cadence["continuous"] is False
    assert cadence["too_fast_count"] == 1


def test_the_cadence_check_refuses_a_gap_beyond_the_settle_budget():
    cadence = check_frame_cadence(
        _frames([MAX_SETTLE_S + 2.0 * FRAME_PERIOD_S], start=0.0),
        frame_period_s=FRAME_PERIOD_S,
        max_settle_s=MAX_SETTLE_S,
    )

    assert cadence["continuous"] is False
    assert cadence["undeclared_gap_count"] == 1


def test_the_cadence_check_refuses_a_backward_frame_stamp():
    cadence = check_frame_cadence(
        [
            {"frame_index": 0, "frame_sim_s": 0.2},
            {"frame_index": 1, "frame_sim_s": 0.1},
        ],
        frame_period_s=FRAME_PERIOD_S,
        max_settle_s=MAX_SETTLE_S,
    )

    assert cadence["continuous"] is False
    assert cadence["backward_count"] == 1


def test_a_cadence_below_the_ten_hertz_contract_is_refused_rather_than_accepted():
    with pytest.raises(ValueError):
        check_frame_cadence(
            _frames([FRAME_PERIOD_S], start=0.0), frame_period_s=0.2, max_settle_s=MAX_SETTLE_S
        )


def _stop(**overrides) -> dict:
    stop = {
        "index": 0,
        "anchor": "default",
        "kind": "plan",
        "target_rad": 0.0,
        "settled": True,
        "reached": True,
        "quiet_steps": 5,
        "final_velocity_rad_s": 0.0,
        "final_position_error_rad": 0.0,
        "time_base": "simulation",
    }
    stop.update(overrides)
    return stop


def _sample(velocity, **overrides) -> dict:
    sample = {
        "velocity_rad_s": velocity,
        "settled": True,
        "reached": True,
        "position_error_rad": 0.0,
    }
    sample.update(overrides)
    return sample


def test_the_settle_proof_accepts_a_stop_that_held_the_controllers_own_settle_rule():
    proof = settle_proof(
        [_stop(quiet_steps=5, final_velocity_rad_s=0.05)],
        settle_velocity_rad_s=0.05,
        goal_tolerance_rad=0.05,
        settle_consecutive_steps=5,
    )

    assert proof["proven"] is True
    assert proof["stop_count"] == 1
    assert proof["unproven_stops"] == []


def test_the_settle_proof_refuses_a_stop_with_two_consecutive_quiet_steps():
    proof = settle_proof(
        [_stop(quiet_steps=2)],
        settle_velocity_rad_s=0.05,
        goal_tolerance_rad=0.05,
        settle_consecutive_steps=5,
    )

    assert proof["proven"] is False
    assert proof["unproven_stops"] == [0]


def test_the_settle_proof_refuses_a_stop_that_was_never_reached_or_settled():
    proof = settle_proof(
        [_stop(reached=False), _stop(index=1, settled=False)],
        settle_velocity_rad_s=0.05,
        goal_tolerance_rad=0.05,
        settle_consecutive_steps=5,
    )

    assert proof["proven"] is False
    assert proof["unproven_stops"] == [0, 1]


def test_the_settle_proof_refuses_a_stop_left_outside_the_goal_tolerance():
    proof = settle_proof(
        [_stop(final_position_error_rad=0.2)],
        settle_velocity_rad_s=0.05,
        goal_tolerance_rad=0.05,
        settle_consecutive_steps=5,
    )

    assert proof["proven"] is False
    assert proof["unproven_stops"] == [0]


def test_the_settle_proof_of_an_empty_stop_list_is_unproven_rather_than_vacuously_true():
    proof = settle_proof(
        [], settle_velocity_rad_s=0.05, goal_tolerance_rad=0.05, settle_consecutive_steps=5
    )
    assert proof["proven"] is False
    assert proof["stop_count"] == 0


def test_the_stop_proof_is_complete_at_the_third_consecutive_qualifying_sample():
    proof = stop_proof(
        [_sample(0.05), _sample(0.04136050464213824), _sample(0.04136050464213824), _sample(0.0)],
        velocity_limit_rad_s=0.04136050464213824,
    )

    assert proof["proven"] is True
    assert proof["required_samples"] == 3
    assert proof["longest_consecutive_run"] == 3
    assert proof["qualifying_samples"] == 3
    assert [row["consecutive_run"] for row in proof["samples"]] == [0, 1, 2, 3]


def test_two_quiet_samples_between_two_loud_ones_are_not_a_stop_proof():
    proof = stop_proof(
        [_sample(0.0), _sample(0.0), _sample(0.5), _sample(0.0), _sample(0.0)],
        velocity_limit_rad_s=0.04136050464213824,
    )

    assert proof["proven"] is False
    assert proof["longest_consecutive_run"] == 2


def test_the_stop_proof_of_an_empty_sample_list_is_unproven_rather_than_vacuously_true():
    proof = stop_proof([], velocity_limit_rad_s=0.05)
    assert proof["proven"] is False
    assert proof["sample_count"] == 0


def test_a_sample_without_a_finite_velocity_never_qualifies():
    proof = stop_proof(
        [_sample(None), _sample(None), _sample(None)], velocity_limit_rad_s=0.05
    )
    assert proof["proven"] is False
    assert proof["qualifying_samples"] == 0


class _HoldPlant:
    """A plant whose holds are always loud: the stop proof can never complete on it."""

    def __init__(self, velocity: float, *, yaw_rad: float = 0.0) -> None:
        self.yaw_rad = float(yaw_rad)
        self.velocity = float(velocity)
        self.holds = 0

    def settle_to(self, target_rad: float) -> dict:
        self.holds += 1
        return {
            "target_rad": float(target_rad),
            "settled": True,
            "reached": True,
            "final_velocity_rad_s": self.velocity,
            "final_position_error_rad": 0.0,
            "settle_s": 0.01,
        }


def test_the_held_stop_proof_samples_until_three_consecutive_samples_qualify():
    plant = _HoldPlant(0.0)
    proof = hold_stop_samples(plant, velocity_limit_rad_s=0.04136050464213824)

    assert proof["proven"] is True
    assert proof["sample_count"] == 3
    assert plant.holds == 3
    assert proof["held_at_rad"] == 0.0


def test_the_held_stop_proof_spends_its_declared_window_and_refuses_a_loud_hold():
    plant = _HoldPlant(0.5)
    proof = hold_stop_samples(plant, velocity_limit_rad_s=0.04136050464213824)

    assert proof["proven"] is False
    assert proof["longest_consecutive_run"] == 0
    assert proof["sample_count"] == 6


def test_the_held_stop_proof_completes_after_one_loud_hold_and_three_quiet_ones():
    class Plant(_HoldPlant):
        def settle_to(self, target_rad):
            stop = super().settle_to(target_rad)
            stop["final_velocity_rad_s"] = 0.5 if self.holds == 1 else 0.0
            return stop

    proof = hold_stop_samples(Plant(0.0), velocity_limit_rad_s=0.04136050464213824)
    assert proof["proven"] is True
    assert proof["sample_count"] == 4
