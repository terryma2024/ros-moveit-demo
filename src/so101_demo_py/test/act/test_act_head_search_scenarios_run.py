"""Running a scenario, its journal entry and the aggregate."""

from __future__ import annotations

from head_search_scenarios_support import (
    FRAME_PERIOD_S,
    VERTICAL_BOUNDS_PX,
    FakeDetector,
    FakePlant,
    _clock,
    _partition_items,
)
import pytest

from so101_demo.act.head_search_scenarios.contracts import (
    CAL_SCENARIO_BUDGET_EXHAUSTED,
    CAL_SCENARIO_COVERAGE_INCOMPLETE,
    CAL_SCENARIO_CUP_NOT_FOUND,
    CAL_SCENARIO_DETECTOR_FAILED,
    CAL_SCENARIO_FRAME_CADENCE,
    CAL_SCENARIO_INTERRUPTION_UNPROVEN,
    CAL_SCENARIO_NO_VERDICT,
    CAL_SCENARIO_OUT_OF_CORRIDOR,
    CAL_SCENARIO_STOP_UNPROVEN,
    CAL_SCENARIO_UNEXPECTED_LOCK,
    QUALIFICATION_FIT_WARNING,
    CalibrationScenarioRefused,
)
from so101_demo.act.head_search_scenarios.journal import (
    JOURNAL_KEYS,
    aggregate_scenarios,
    scenario_journal_entry,
)
from so101_demo.act.head_search_scenarios.scenario_run import (
    classify_scenario,
    run_scenario,
)

REQUIRED_DOMAIN_RAD = (-0.17559216195018026, 0.08047101126546086)


LOCK_VALID_RAD = (-6.283175307179587, 6.283175307179587)


def _controller_config(**overrides) -> dict:
    config = {
        "attempt_id": "scenario-attempt",
        "session_id": "scenario-session",
        "search_start_rad": 0.0,
        "horizontal_fov_rad": 1.3121067481206794,
        "coarse_step_rad": 0.6560533740603397,
        "search_timeout_s": 30.0,
        "max_age_s": 0.05,
        "max_skew_s": 0.02,
        "settle_velocity_rad_s": 0.05,
        "goal_tolerance_rad": 0.05,
        "center_deadband_px": 3.0,
        "vertical_bounds_px": list(VERTICAL_BOUNDS_PX),
        "min_area_px2": 64.0,
        "min_confidence": 0.25,
        "max_fine_corrections": 2,
        "max_fine_total_rad": 0.6961197054865531,
        "frame_id": "head_camera_frame",
        "ray_origin_frame_id": "head_camera_frame",
        "required_search_domain_rad": list(REQUIRED_DOMAIN_RAD),
        "lock_valid_neck_rad": list(LOCK_VALID_RAD),
    }
    config.update(overrides)
    return config


def _item(index: int = 0) -> dict:
    return dict(_partition_items(40)[index])


#: the digests and the runtime identity the producer declares per scenario; a synthetic stand-in here
_EVIDENCE = {
    "scene_sha256": "0" * 64,
    "geometry_seal_sha256": "1" * 64,
    "production_search_config_sha256": "2" * 64,
    "frozen_candidate_sha256": "3" * 64,
    "weights_sha256": "4" * 64,
    "dataset_config_sha256": "5" * 64,
    "scenario_partitions_sha256": "6" * 64,
    "controller_config_sha256": "7" * 64,
    "runtime_identity": {"runtime_id": "head-search-runtime", "allow_cpu_fallback": False},
    "command": "so101_head_search_calibration measure-scenarios ...",
}


def scenario(*, plant, detector=None, config=None, item=None, coarse=None, fine=None, **kwargs):
    """One `run_scenario` call over the fake plant and detector, everything else declared."""

    declared = _item() if item is None else dict(item)
    kwargs.setdefault("evidence", _EVIDENCE)
    return run_scenario(
        controller_config=_controller_config() if config is None else config,
        plant=plant,
        detector=FakeDetector(plant) if detector is None else detector,
        coarse_corridor_rad=REQUIRED_DOMAIN_RAD if coarse is None else coarse,
        fine_corridor_rad=LOCK_VALID_RAD if fine is None else fine,
        scenario=declared,
        stop_velocity_rad_s=0.04136050464213824,
        clock=_clock(),
        **kwargs,
    )


def _item_for(condition_class: str, *, anchor: str = "default", seed: int = 900000) -> dict:
    return {
        "seed": seed,
        "scene_group_id": f"scene-{seed:09d}",
        "condition_class": condition_class,
        "anchor": anchor,
    }


def test_a_legal_single_cup_scenario_locks_and_journals_the_whole_story():
    plant = FakePlant(cup_yaw_rad=0.05)
    entry = scenario(plant=plant)

    assert entry["outcome"] == "PASSED"
    assert entry["outcome_code"] is None
    assert entry["terminal_status"] == "TARGET_LOCKED"
    assert entry["found"] is True
    assert entry["locked"] is True
    assert entry["seed"] == 900000
    assert entry["condition_class"] == "nominal"
    assert entry["anchor"] == "default"
    assert entry["expected_terminals"] == ["TARGET_LOCKED"]
    assert entry["cup_count"] == 1
    assert entry["fine_corrections"] == 1
    assert entry["cumulative_fine_correction_rad"] == pytest.approx(0.05, abs=0.01)
    assert entry["stop_proof"]["proven"] is True
    assert entry["frame_cadence"]["continuous"] is True
    assert entry["frame_cadence"]["frame_rate_hz"] == 10.0
    assert entry["attempt_ids"] == ["scenario-attempt-attempt-1"]
    assert entry["time_base"] == "simulation"


def test_every_journal_entry_carries_exactly_the_declared_keys():
    entry = scenario(plant=FakePlant(cup_yaw_rad=0.05))
    journal = scenario_journal_entry(entry)

    assert set(journal) == set(JOURNAL_KEYS)
    assert set(JOURNAL_KEYS) - {"attempt_summaries"} <= set(entry)


def test_the_journal_entry_carries_the_evidence_that_reproduces_it():
    entry = scenario(plant=FakePlant(cup_yaw_rad=0.05))
    evidence = entry["evidence"]

    for key in (
        "seed",
        "anchor",
        "condition_class",
        "cup_count",
        "scenario_name",
        "attempt_ids",
        "scene_sha256",
        "geometry_seal_sha256",
        "production_search_config_sha256",
        "frozen_candidate_sha256",
        "weights_sha256",
        "dataset_config_sha256",
        "scenario_partitions_sha256",
        "controller_config_sha256",
        "runtime_identity",
        "command",
    ):
        assert key in evidence, key
    assert evidence["seed"] == 900000
    assert evidence["anchor"] == "default"


def test_no_cup_ends_target_not_found_with_complete_coverage():
    entry = scenario(
        plant=FakePlant(cup_yaw_rad=0.05),
        detector=FakeDetector(FakePlant(cup_yaw_rad=0.05), cups=0),
        item=_item_for("no_cup"),
    )

    assert entry["outcome"] == "PASSED"
    assert entry["terminal_status"] == "TARGET_NOT_FOUND"
    assert entry["found"] is False
    assert entry["fine_corrections"] is None
    assert entry["cumulative_fine_correction_rad"] is None
    assert entry["coverage"]["complete"] is True


def test_two_cups_end_target_ambiguous_rather_than_a_lock():
    plant = FakePlant(cup_yaw_rad=0.0)
    entry = scenario(
        plant=plant,
        detector=FakeDetector(plant, cups=2),
        item=_item_for("two_cups"),
    )

    assert entry["outcome"] == "PASSED"
    assert entry["terminal_status"] == "TARGET_AMBIGUOUS"
    assert entry["fine_corrections"] is None


def test_a_lock_in_a_no_cup_scenario_is_a_wrong_lock_and_the_scenario_fails():
    entry = scenario(plant=FakePlant(cup_yaw_rad=0.05), item=_item_for("no_cup"))

    assert entry["outcome"] == "FAILED"
    assert entry["outcome_code"] == CAL_SCENARIO_UNEXPECTED_LOCK
    assert entry["locked"] is True


def test_a_single_cup_scenario_that_never_finds_the_cup_fails_with_cup_not_found():
    plant = FakePlant(cup_yaw_rad=0.05)
    entry = scenario(plant=plant, detector=FakeDetector(plant, cups=0))

    assert entry["outcome"] == "FAILED"
    assert entry["outcome_code"] == CAL_SCENARIO_CUP_NOT_FOUND
    assert entry["fine_corrections"] is None


def test_a_clean_negative_that_stopped_at_a_bound_is_refused_not_passed():
    entry = classify_scenario(
        {
            "condition_class": "no_cup",
            "terminal_status": "TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL",
            "found": False,
            "coverage": {"complete": False, "reached_bound": True},
        }
    )

    assert entry["outcome"] == "REFUSED"
    assert entry["outcome_code"] == CAL_SCENARIO_COVERAGE_INCOMPLETE


def test_a_detector_that_raises_refuses_that_one_scenario():
    plant = FakePlant(cup_yaw_rad=0.05)
    entry = scenario(plant=plant, detector=FakeDetector(plant, fail_at=(0,)))

    assert entry["outcome"] == "REFUSED"
    assert entry["outcome_code"] == CAL_SCENARIO_DETECTOR_FAILED
    assert entry["terminal_status"] is None


def test_a_centring_budget_that_runs_out_is_a_failure_not_an_unmeasured_scenario():
    """The promoted budget is the controller's own, so hitting it is a judged failure, not a refusal."""

    plant = FakePlant(cup_yaw_rad=0.05)
    entry = scenario(
        plant=plant,
        detector=FakeDetector(plant, jitter_px=(100.0, -100.0)),
        config=_controller_config(max_fine_corrections=1, max_fine_total_rad=5.0),
    )

    assert entry["outcome"] == "FAILED"
    assert entry["outcome_code"] == CAL_SCENARIO_BUDGET_EXHAUSTED
    assert entry["terminal_status"] == "TARGET_NOT_CENTERED"


def test_a_correction_outside_the_declared_corridor_is_refused_rather_than_clamped():
    plant = FakePlant(cup_yaw_rad=0.4)
    entry = scenario(plant=plant, fine=(0.0, 0.01))

    assert entry["outcome"] == "REFUSED"
    assert entry["outcome_code"] == CAL_SCENARIO_OUT_OF_CORRIDOR
    assert plant.commands[-1] <= 0.01


def test_a_scenario_that_never_reaches_a_verdict_is_refused():
    plant = FakePlant(cup_yaw_rad=0.05, follow_gain=0.0)
    entry = scenario(
        plant=plant,
        config=_controller_config(max_fine_corrections=100, max_fine_total_rad=5.0),
        max_frames=4,
    )

    assert entry["outcome"] == "REFUSED"
    assert entry["outcome_code"] == CAL_SCENARIO_NO_VERDICT
    assert entry["attempts"][0]["frame_count"] == 4


def test_a_stop_that_never_held_the_settle_rule_refuses_the_scenario():
    plant = FakePlant(cup_yaw_rad=0.05, quiet_steps=2)
    entry = scenario(plant=plant)

    assert entry["outcome"] == "REFUSED"
    assert entry["outcome_code"] == CAL_SCENARIO_STOP_UNPROVEN
    assert entry["attempts"][-1]["settle_proof"]["proven"] is False


def test_a_scenario_whose_stop_proof_never_completes_is_refused():
    plant = FakePlant(cup_yaw_rad=0.05, hold_velocity_rad_s=0.5)
    entry = scenario(plant=plant)

    assert entry["outcome"] == "REFUSED"
    assert entry["outcome_code"] == CAL_SCENARIO_STOP_UNPROVEN
    assert entry["stop_proof"] is None or entry["stop_proof"]["proven"] is False


def test_frames_faster_than_the_frame_contract_refuse_the_scenario():
    plant = FakePlant(cup_yaw_rad=0.05, frame_period_s=FRAME_PERIOD_S / 10.0)
    entry = scenario(plant=plant)

    assert entry["outcome"] == "REFUSED"
    assert entry["outcome_code"] == CAL_SCENARIO_FRAME_CADENCE
    assert entry["frame_cadence"]["too_fast_count"] > 0


def test_the_declared_anchor_start_is_bounded_by_the_lock_valid_interval_not_the_sweep_domain():
    """The `default` anchor starts at 0.1 rad, outside the required search domain the sweep owes.

    HS-302's corridor is the intersection the *sweep stops* have to stay inside; the anchor is where the
    search starts, and the seal declares `lock_valid_neck_rad` as the interval a lock is valid in, which is
    where a legal start anchor lives. Refusing the declared anchor would refuse the plan's own `default`
    restart anchor and 14 of the 40 declared scenarios with it.
    """

    plant = FakePlant(cup_yaw_rad=0.05, yaw_rad=0.1)
    entry = scenario(plant=plant, config=_controller_config(search_start_rad=0.1))

    assert entry["outcome"] == "PASSED"
    assert entry["attempts"][0]["stops"][0]["kind"] == "anchor"
    assert entry["attempts"][0]["stops"][0]["target_rad"] == pytest.approx(0.1)
    assert entry["coverage"]["complete"] is True
    assert entry["plan_moves"] == 0 or entry["attempts"][0]["stops"][0]["kind"] == "anchor"


def test_an_anchor_start_outside_the_seals_lock_valid_interval_is_refused():
    plant = FakePlant(cup_yaw_rad=0.05)
    with pytest.raises(CalibrationScenarioRefused) as refused:
        scenario(plant=plant, fine=(0.05, 1.0))

    assert refused.value.code == CAL_SCENARIO_OUT_OF_CORRIDOR
    assert "search start" in str(refused.value)


def test_an_interrupted_scenario_proves_the_stop_clears_the_lock_and_reacquires():
    plant = FakePlant(cup_yaw_rad=0.05)
    entry = scenario(plant=plant, item=_item_for("fast_interruption"), interruption=True)

    assert entry["outcome"] == "PASSED"
    assert entry["terminal_status"] == "TARGET_LOCKED"
    assert entry["attempt_ids"] == [
        "scenario-attempt-attempt-1",
        "scenario-attempt-attempt-2",
    ]
    first = entry["attempts"][0]
    assert first["interruption_injected"] is True
    assert first["interruption_kind"] == "stale_frame"
    assert first["interruption_decision_status"] == "INPUT_STALE"
    assert first["stop"] is True
    assert first["stop_proof"]["proven"] is True
    assert first["lock_count_cleared_by_interruption"] is True
    second = entry["attempts"][1]
    assert second["detector_reset_before_attempt"] is True
    assert second["interruption_injected"] is False


def test_an_interruption_class_that_was_not_interrupted_is_refused():
    plant = FakePlant(cup_yaw_rad=0.05)
    entry = scenario(plant=plant, item=_item_for("fast_interruption"))

    assert entry["outcome"] == "REFUSED"
    assert entry["outcome_code"] == CAL_SCENARIO_INTERRUPTION_UNPROVEN
    assert entry["attempt_ids"] == ["scenario-attempt-attempt-1"]


def test_reacquire_after_stop_is_the_second_declared_interruption_class():
    plant = FakePlant(cup_yaw_rad=0.05)
    entry = scenario(plant=plant, item=_item_for("reacquire_after_stop"), interruption=True)

    assert entry["outcome"] == "PASSED"
    assert len(entry["attempts"]) == 2


def test_an_interruption_that_does_not_stop_fail_closed_is_refused():
    """A scenario whose declared interruption never produced a stop is not evidence of a reacquire."""

    plant = FakePlant(cup_yaw_rad=0.05)
    entry = classify_scenario(
        {
            "condition_class": "fast_interruption",
            "terminal_status": "TARGET_LOCKED",
            "found": True,
            "coverage": {"complete": True, "reached_bound": False},
            "attempts": [
                {"index": 0, "interruption_injected": True, "stop": False},
                {"index": 1, "interruption_injected": False},
            ],
        }
    )

    assert entry["outcome"] == "REFUSED"
    assert entry["outcome_code"] == CAL_SCENARIO_INTERRUPTION_UNPROVEN


def _fake_entry(condition_class, anchor, outcome, *, terminal=None, code=None):
    return {
        "seed": 900000,
        "condition_class": condition_class,
        "anchor": anchor,
        "outcome": outcome,
        "outcome_code": code,
        "terminal_status": terminal,
        "fine_corrections": 1 if outcome == "PASSED" else None,
        "cumulative_fine_correction_rad": 0.1 if outcome == "PASSED" else None,
        "frame_cadence": {"continuous": True},
        "stop_proof": {"proven": True},
    }


def test_the_aggregate_counts_every_outcome_per_condition_class_and_anchor():
    entries = [
        _fake_entry("nominal", "default", "PASSED", terminal="TARGET_LOCKED"),
        _fake_entry("nominal", "left", "FAILED", terminal="TARGET_NOT_FOUND", code="X"),
        _fake_entry("no_cup", "forward", "PASSED", terminal="TARGET_NOT_FOUND"),
        _fake_entry("no_cup", "default", "REFUSED", terminal=None, code="Y"),
    ]
    aggregate = aggregate_scenarios(entries)

    assert aggregate["scenario_count"] == 4
    assert aggregate["passed_count"] == 2
    assert aggregate["failed_count"] == 1
    assert aggregate["refused_count"] == 1
    assert aggregate["by_condition_class"]["nominal"] == {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "refused": 0,
        "terminal_statuses": {"TARGET_LOCKED": 1, "TARGET_NOT_FOUND": 1},
    }
    assert aggregate["by_anchor"]["default"]["total"] == 2
    assert aggregate["by_anchor"]["forward"]["passed"] == 1


def test_the_aggregate_reports_zero_wrong_locks_only_when_there_are_none():
    clean = aggregate_scenarios([_fake_entry("no_cup", "default", "PASSED", terminal="TARGET_NOT_FOUND")])
    dirty = aggregate_scenarios(
        [
            _fake_entry(
                "no_cup",
                "default",
                "FAILED",
                terminal="TARGET_LOCKED",
                code=CAL_SCENARIO_UNEXPECTED_LOCK,
            )
        ]
    )

    assert clean["zero_wrong_locks"] is True
    assert clean["wrong_locks"] == []
    assert dirty["zero_wrong_locks"] is False
    assert dirty["wrong_locks"] == [{"seed": 900000, "condition_class": "no_cup", "anchor": "default"}]


def test_the_aggregate_never_claims_the_qualification_verdict():
    aggregate = aggregate_scenarios([_fake_entry("nominal", "default", "PASSED", terminal="TARGET_LOCKED")])

    assert aggregate["qualification_verdict"] is None
    assert "aggregate" in aggregate["qualification_verdict_owner"]
    assert aggregate["fit_warning"] == QUALIFICATION_FIT_WARNING


def test_the_aggregate_reports_the_correction_and_cadence_ranges():
    entries = [
        _fake_entry("nominal", "default", "PASSED", terminal="TARGET_LOCKED"),
        _fake_entry("left_anchor", "left", "PASSED", terminal="TARGET_LOCKED"),
    ]
    entries[1]["fine_corrections"] = 2
    entries[1]["cumulative_fine_correction_rad"] = 0.3
    aggregate = aggregate_scenarios(entries)

    assert aggregate["fine_corrections"] == {"min": 1, "max": 2, "observed_on": 2}
    assert aggregate["cumulative_fine_correction_rad"] == {"min": 0.1, "max": 0.3, "observed_on": 2}
    assert aggregate["cadence_all_continuous"] is True
    assert aggregate["stop_proofs_all_proven"] is True
