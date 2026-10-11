"""HS-316: the 40 qualification scenarios, their per-scenario journal and the honest aggregate.

Every case here runs against an injected scene preparation, an injected plant, an injected detector and an
injected ownership gate, so the closed loop, the per-condition-class expectations, the frame cadence, the
stop proof, every refusal and the aggregate are exercised without MuJoCo, a dataset renderer, a detector,
a GPU or ROS. The detector is built as the exact inverse of the controller's own correction law, so a
"correct" fixture converges in one correction and a lagging one needs more.
"""

from __future__ import annotations

import hashlib
import json
import math

import pytest
from so101_demo.act import head_search_scenarios as module
from so101_demo.act.head_search_scenarios import (
    CAL_SCENARIO_BUDGET_EXHAUSTED,
    CAL_SCENARIO_COVERAGE_INCOMPLETE,
    CAL_SCENARIO_CUP_NOT_FOUND,
    CAL_SCENARIO_DETECTOR_FAILED,
    CAL_SCENARIO_FRAME_CADENCE,
    CAL_SCENARIO_INTERRUPTION_UNPROVEN,
    CAL_SCENARIO_NO_VERDICT,
    CAL_SCENARIO_OUT_OF_CORRIDOR,
    CAL_SCENARIO_SPLIT_LEAK,
    CAL_SCENARIO_STOP_UNPROVEN,
    CAL_SCENARIO_UNEXPECTED_LOCK,
    CAL_SCENARIO_OWNERSHIP_REFUSED,
    CAL_SCENARIO_RUNTIME_UNVERIFIED,
    CAL_SCENARIO_RUN_ROOT_EXISTS,
    EVIDENCE_DIR,
    JOURNAL_KEYS,
    QUALIFICATION_FIT_WARNING,
    CalibrationScenarioRefused,
    aggregate_scenarios,
    check_frame_cadence,
    classify_scenario,
    expected_terminals,
    qualification_scenarios,
    run_scenario,
    hold_stop_samples,
    scenario_journal_entry,
    settle_proof,
    stop_proof,
    write_head_search_scenarios,
)
from so101_demo.act.head_search_timing_measurement.contracts import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
)

WIDTH_PX = 640
HEIGHT_PX = 480
FOCAL_PX = 415.69219381653056
PRINCIPAL_X_PX = WIDTH_PX / 2.0
PRINCIPAL_Y_PX = HEIGHT_PX / 2.0
TIMESTEP_S = 0.002
CONTROL_STEPS = 5
#: the sealed head camera's optical axes in the base frame (x=image right, y=image down, z=forward)
ROTATION_OPTICAL_TO_BASE = (
    (-1.0, 0.0, 0.0),
    (0.0, 0.6, -0.8),
    (0.0, -0.8, -0.6),
)
#: the yaw-to-pixel gain of that camera's forward axis in base, px per rad near the optical axis
GAIN_PX_PER_RAD = 0.8 * FOCAL_PX
VERTICAL_BOUNDS_PX = (191.699852915671, 272.6768492617673)
#: the seal's required search domain and its lock-valid interval (the promoted head search bundle's own)
REQUIRED_DOMAIN_RAD = (-0.17559216195018026, 0.08047101126546086)
LOCK_VALID_RAD = (-6.283175307179587, 6.283175307179587)
#: the endorsed frame contract the cadence check paces itself against
FRAME_PERIOD_S = 0.1
MAX_SETTLE_S = 5.0

CONDITION_CLASSES = [
    "nominal",
    "left_anchor",
    "forward_anchor",
    "distractor_present",
    "two_cups",
    "no_cup",
    "low_light",
    "partial_occlusion",
    "fast_interruption",
    "reacquire_after_stop",
]
ANCHORS = ["default", "left", "forward"]


def _partition_items(count: int = 40) -> list[dict]:
    """The declared qualification list, built with the tracked document's own rotation of classes."""

    items = []
    for index in range(count):
        condition_class = CONDITION_CLASSES[index % len(CONDITION_CLASSES)]
        items.append(
            {
                "seed": 900000 + index,
                "scene_group_id": f"scene-{900000 + index:09d}",
                "condition_class": condition_class,
                "anchor": ANCHORS[index % len(ANCHORS)],
            }
        )
    return items


PARTITIONS = {
    "schema_version": 1,
    "document": "head-search-scenario-partitions/v1",
    "condition_classes": CONDITION_CLASSES,
    "anchors": ANCHORS,
    "calibration": [700000, 700001],
    "held_out_evaluation": [800000, 800001],
    "qualification": _partition_items(4),
}


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


def _project(yaw_rad: float, cup_yaw_rad: float) -> float:
    """The pixel column a cup at `cup_yaw_rad` lands on while the neck holds `yaw_rad`."""

    return PRINCIPAL_X_PX - GAIN_PX_PER_RAD * math.tan(cup_yaw_rad - yaw_rad)


class FakePlant:
    """A yaw-only plant that commands a target, moves exactly there and renders one frame per stop.

    The plant holds the neck to the declared frame boundary exactly as the sealed MuJoCo plant does, so
    every stop advances the simulation clock by one frame period and the recorded stop is settled: the
    interval between two frames is that period, which is the contract the cadence check proves.
    """

    def __init__(
        self,
        *,
        cup_yaw_rad: float,
        yaw_rad: float = 0.0,
        follow_gain: float = 1.0,
        quiet_steps: int = 5,
        frame_period_s: float = FRAME_PERIOD_S,
        settled: bool = True,
        reached: bool = True,
        hold_velocity_rad_s: float = 0.0,
    ) -> None:
        self.cup_yaw_rad = float(cup_yaw_rad)
        self.yaw_rad = float(yaw_rad)
        self.follow_gain = float(follow_gain)
        self.quiet_steps = int(quiet_steps)
        self.frame_period_s = float(frame_period_s)
        self.settled = bool(settled)
        self.reached = bool(reached)
        self.hold_velocity_rad_s = float(hold_velocity_rad_s)
        self.simulation_timestep_s = TIMESTEP_S
        self.time_s = 0.0
        self.frames_rendered = 0
        self.stops: list[dict] = []
        self.commands: list[float] = []
        self.target_rad = float(yaw_rad)

    def settle_to(self, target_rad: float) -> dict:
        self.commands.append(float(target_rad))
        start_sim, start_rad = self.time_s, self.yaw_rad
        self.target_rad = float(target_rad)
        self.yaw_rad = start_rad + self.follow_gain * (float(target_rad) - start_rad)
        self.time_s += self.frame_period_s
        steps = int(round(self.frame_period_s / TIMESTEP_S))
        stop = {
            "index": None,
            "kind": "plan",
            "target_rad": float(target_rad),
            "start_rad": start_rad,
            "sim_start_s": start_sim,
            "sim_end_s": self.time_s,
            "steps": steps,
            "settle_s": self.time_s - start_sim,
            "settled": self.settled,
            "reached": self.reached,
            "final_velocity_rad_s": (
                self.hold_velocity_rad_s
                if abs(float(target_rad) - start_rad) <= 1e-12
                else 0.0
            ),
            "final_position_error_rad": float(target_rad) - self.yaw_rad,
            "quiet_steps": self.quiet_steps,
            "time_base": "simulation",
        }
        self.stops.append(stop)
        return dict(stop)

    @property
    def velocity_rad_s(self) -> float:
        return 0.0

    @property
    def frame_stamp_ns(self) -> int:
        return int(round(self.time_s * 1e9))

    def render_frame(self):
        self.frames_rendered += 1
        return {"frame": self.frames_rendered, "yaw_rad": self.yaw_rad}

    def optical_geometry(self) -> dict:
        return {
            "k": (FOCAL_PX, 0.0, PRINCIPAL_X_PX, 0.0, FOCAL_PX, PRINCIPAL_Y_PX, 0.0, 0.0, 1.0),
            "distortion": (0.0, 0.0, 0.0, 0.0, 0.0),
            "rotation_optical_to_base": ROTATION_OPTICAL_TO_BASE,
        }


class FakeDetector:
    """A detector that projects the plant's own yaw, with a declared per-frame pixel jitter."""

    def __init__(self, plant, *, jitter_px=(), cups=1, fail_at=()) -> None:
        self.plant = plant
        self.jitter_px = tuple(jitter_px)
        self.cups = int(cups)
        self.fail_at = tuple(fail_at)
        self.calls = 0
        self.resets = 0

    def reset(self) -> None:
        self.calls = 0
        self.resets += 1

    def __call__(self, image, stamp_ns):
        index = self.calls
        self.calls += 1
        if index in self.fail_at:
            raise RuntimeError("DETECTOR_FAILED")
        if self.cups == 0:
            return []
        jitter = self.jitter_px[index % len(self.jitter_px)] if self.jitter_px else 0.0
        column = _project(float(image["yaw_rad"]), self.plant.cup_yaw_rad) + jitter
        if column - 30.0 < 0.0 or column + 30.0 > WIDTH_PX:
            return []
        return [
            {
                "xyxy": (column - 30.0, PRINCIPAL_Y_PX - 30.0, column + 30.0, PRINCIPAL_Y_PX + 30.0),
                "confidence": 0.9,
                "class_id": 0,
                "track_id": f"head-cup-{cup}",
            }
            for cup in range(self.cups)
        ]


def _clock(start=1000.0, step=0.001):
    state = {"now": start}

    def clock() -> float:
        state["now"] += step
        return state["now"]

    return clock


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


# --- the declared qualification list -------------------------------------------------------------


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


# --- the per-condition-class expectations --------------------------------------------------------


def test_the_plan_step_three_terminals_are_declared_per_condition_class():
    """Plan Task 14 Step 3: one cup locks, two cups are ambiguous, no cup is a clean negative."""

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
    assert module.requires_interruption("fast_interruption") is True
    assert module.requires_interruption("reacquire_after_stop") is True
    assert module.requires_interruption("nominal") is False


# --- the 10 Hz frame cadence ---------------------------------------------------------------------


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


# --- the settle proof and the held stop proof ------------------------------------------------------


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


# --- the closed loop and its per-scenario journal --------------------------------------------------


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


# --- the interrupted classes ---------------------------------------------------------------------


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


# --- the aggregate -------------------------------------------------------------------------------


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


# --- the installed producer ------------------------------------------------------------------------


SCENE_XML = """<mujoco model="scenario-fixture">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="plastic_cup">
      <joint name="cup_free_joint" type="free"/>
      <geom name="cup_geom" type="cylinder" size="0.04 0.045"/>
    </body>
    <body name="head_mount">
      <joint name="neck_yaw_joint" type="hinge" axis="0 0 1" damping="0.05" armature="0.001"/>
      <geom name="head_geom" type="box" size="0.05 0.05 0.05"/>
      <camera name="head_camera" pos="0 0 0.05" fovy="60" xyaxes="1 0 0 0 1 0"/>
    </body>
  </worldbody>
</mujoco>
"""

QUALIFICATION_PARTITIONS = {
    "schema_version": 1,
    "document": "head-search-scenario-partitions/v1",
    "condition_classes": CONDITION_CLASSES,
    "anchors": ANCHORS,
    "calibration": [700000, 700001],
    "held_out_evaluation": [800000, 800001],
    "qualification": [
        {
            "seed": 900000 + index,
            "scene_group_id": f"scene-{900000 + index:09d}",
            "condition_class": CONDITION_CLASSES[index % len(CONDITION_CLASSES)],
            "anchor": ANCHORS[index % len(ANCHORS)],
        }
        for index in range(10)
    ],
}


def _write_inputs(tmp_path) -> dict:
    """The eight declared inputs of the scenario flight, synthetic but complete."""

    scene = tmp_path / "head_search_scene.xml"
    scene.write_text(SCENE_XML, encoding="utf-8")
    scene_sha256 = hashlib.sha256(scene.read_bytes()).hexdigest()
    weights = tmp_path / "C.pt"
    weights.write_bytes(b"selected-model")
    weights_sha256 = hashlib.sha256(weights.read_bytes()).hexdigest()
    seal = tmp_path / "head-camera-geometry.json"
    seal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "camera_name": "head_camera",
                "camera": {"camera_name": "head_camera", "fovy_rad": 1.0471975511965976},
                "image_width": 640,
                "image_height": 480,
                "horizontal_fov_rad": 1.3121067481206794,
                "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
                "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                "in_frame_matrix": {
                    "default": {"neck_start_rad": 0.0},
                    "left": {"neck_start_rad": 0.0},
                    "forward": {"neck_start_rad": 0.0},
                },
                "workspace_matrix": {
                    "key_samples": [
                        {"anchor": name, "kind": "anchor", "point_m": [-0.08, -0.28, 0.165]}
                        for name in ANCHORS
                    ]
                },
                "source_digests": {"scene_sha256": scene_sha256},
            }
        ),
        encoding="utf-8",
    )
    production = tmp_path / "head_search_runtime.json"
    production.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runtime_id": "head-search-runtime",
                "allow_cpu_fallback": False,
                "cuda_device": "cuda:0",
                "weight_path": str(weights),
                "weight_sha256": weights_sha256,
                "camera": {
                    "name": "head_camera",
                    "frame_id": "head_camera_frame",
                    "ray_origin_frame_id": "head_camera_frame",
                },
                "motion": {"settle_velocity_rad_s": 0.05, "goal_tolerance_rad": 0.05},
                "tracker": {"name": "bytetrack", "iou_threshold": 0.5},
                "values": {
                    "coarse_step_rad": 0.6560533740603397,
                    "horizontal_fov_rad": 1.3121067481206794,
                    "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                    "max_age_s": 0.05,
                    "max_skew_s": 0.02,
                    "search_timeout_s": 30.0,
                    "center_deadband_px": 3.0,
                    "vertical_bounds_px": list(VERTICAL_BOUNDS_PX),
                    "min_area_px2": 64.0,
                    "min_confidence": 0.25,
                    "tracking_iou": 0.5,
                    "max_fine_corrections": 2,
                    "max_fine_total_rad": 0.6961197054865531,
                    "min_bbox_aspect": 0.5,
                    "stop_velocity_rad_s": 0.04136050464213824,
                },
            }
        ),
        encoding="utf-8",
    )
    frozen = tmp_path / "frozen-c.json"
    frozen.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "head-search-frozen-candidate",
                "candidate_id": "C2a",
                "weight_sha256": weights_sha256,
                "operating_points": {
                    "head": {"min_confidence": 0.25, "tracker": {"iou": 0.5}},
                    "task": {"min_confidence": 0.25, "tracker": {"iou": 0.5}},
                },
            }
        ),
        encoding="utf-8",
    )
    controllers = tmp_path / "ros2_controllers.yaml"
    controllers.write_text(
        "controller_manager:\n  ros__parameters:\n    update_rate: 500.0\n", encoding="utf-8"
    )
    dataset = tmp_path / "head_camera_yolo_seg.yaml"
    dataset.write_text(
        f"mjcf_path: {scene.name}\ncamera_name: head_camera\nimage_width: 640\nimage_height: 480\n",
        encoding="utf-8",
    )
    partitions = tmp_path / "head-search-scenario-partitions.json"
    partitions.write_text(json.dumps(QUALIFICATION_PARTITIONS), encoding="utf-8")
    return {
        "scene": scene,
        "seal": seal,
        "production": production,
        "controllers": controllers,
        "weights": weights,
        "frozen": frozen,
        "dataset": dataset,
        "partitions": partitions,
    }


def _class_aware_detector(plant, request, *, blind=()):
    """A detector that places the cup count the item's own condition class declares."""

    if int(request["seed"]) in blind:
        return FakeDetector(plant, cups=0)
    return FakeDetector(plant, cups=module.declared_cup_count(str(request["scenario"])))


def _patch_flight(monkeypatch, *, ownership_status="EXCLUSIVE_OWNERSHIP_OK", cuda=True):
    """Stub the four heavy seams: the ownership gate, CUDA, the scene preparation and the plant."""

    from so101_demo.act import head_search_scenarios as scenarios_module

    monkeypatch.setattr(scenarios_module, "_cuda_available", lambda: cuda)
    monkeypatch.setattr(
        scenarios_module, "prepare_episode_scene", lambda **request: {"prepared": True}
    )
    state: dict = {}

    class Plant(FakePlant):
        def __init__(self, request) -> None:
            super().__init__(cup_yaw_rad=0.05)
            self.request = request
            state["plant"] = self

        def close(self) -> None:
            state["closed"] = state.get("closed", 0) + 1

    monkeypatch.setattr(scenarios_module, "MujocoEpisodePlant", Plant)
    gate_calls: list = []

    def ownership_check(**kwargs):
        gate_calls.append(kwargs)
        if ownership_status != "EXCLUSIVE_OWNERSHIP_OK":
            return {
                "status": ownership_status,
                "run_root": str(kwargs["run_root"]),
                "refusals": [{"code": "DETECTOR_OWNER_ACTIVE", "resource": "process_table", "detail": "pid 5"}],
            }
        kwargs["run_root"].mkdir(parents=True, exist_ok=True)
        return {"status": ownership_status, "run_root": str(kwargs["run_root"]), "refusals": []}

    return scenarios_module, ownership_check, gate_calls, state


def _produce(tmp_path, monkeypatch, *, status="EXCLUSIVE_OWNERSHIP_OK", cuda=True, **overrides):
    inputs = _write_inputs(tmp_path)
    module_, gate, calls, state = _patch_flight(monkeypatch, ownership_status=status, cuda=cuda)
    output = overrides.pop("output_dir", tmp_path / "run-root")
    kwargs = {
        "scene_path": inputs["scene"],
        "geometry_seal_path": inputs["seal"],
        "production_search_config_path": inputs["production"],
        "controller_config_path": inputs["controllers"],
        "frozen_candidate_path": inputs["frozen"],
        "weights_path": inputs["weights"],
        "dataset_config_path": inputs["dataset"],
        "scenario_partitions_path": inputs["partitions"],
        "output_dir": output,
        "evidence_root": tmp_path,
        "ownership_check": gate,
        "plant": None,
        "detector_factory": _class_aware_detector,
        "command": "so101_head_search_calibration measure-scenarios",
        "clock": _clock(),
    }
    kwargs.update(overrides)
    return module_.write_head_search_scenarios(**kwargs), calls, state, inputs, output


def test_the_producer_refuses_the_whole_run_when_the_ownership_gate_refuses(tmp_path, monkeypatch):
    with pytest.raises(CalibrationScenarioRefused) as refused:
        _produce(tmp_path, monkeypatch, status="EXCLUSIVE_OWNERSHIP_REFUSED")

    assert refused.value.code == CAL_SCENARIO_OWNERSHIP_REFUSED
    assert "DETECTOR_OWNER_ACTIVE" in str(refused.value)
    assert not (tmp_path / "scenarios.json").exists()


def test_the_producer_refuses_the_whole_run_when_the_runtime_identity_does_not_hold(tmp_path, monkeypatch):
    inputs = _write_inputs(tmp_path)
    module_, gate, _calls, _state = _patch_flight(monkeypatch)

    def reader(final_run):
        return {
            "final_run": str(final_run),
            "source_commit": "0" * 40,
            "production_config_sha256": "1" * 64,
            "values_sha256": "2" * 64,
            "allow_cpu_fallback": False,
            "weight_sha256_declared": "9" * 64,
            "weight_sha256_observed": "9" * 64,
        }

    with pytest.raises(CalibrationScenarioRefused) as refused:
        module_.write_head_search_scenarios(
            scene_path=inputs["scene"],
            geometry_seal_path=inputs["seal"],
            production_search_config_path=inputs["production"],
            controller_config_path=inputs["controllers"],
            frozen_candidate_path=inputs["frozen"],
            weights_path=inputs["weights"],
            dataset_config_path=inputs["dataset"],
            scenario_partitions_path=inputs["partitions"],
            output_dir=tmp_path / "run-root",
            evidence_root=tmp_path,
            ownership_check=gate,
            runtime_identity_reader=reader,
            final_run=tmp_path / "frozen-root",
            detector_factory=lambda plant, request: FakeDetector(plant),
        )

    assert refused.value.code == CAL_SCENARIO_RUNTIME_UNVERIFIED
    assert "9" * 64 in str(refused.value)


def test_the_producer_refuses_a_device_without_cuda_instead_of_falling_back(tmp_path, monkeypatch):
    with pytest.raises(CalibrationScenarioRefused) as refused:
        _produce(tmp_path, monkeypatch, cuda=False)

    assert refused.value.code == CAL_TIMING_DEVICE_UNAVAILABLE


def test_the_producer_refuses_weights_the_sealed_configuration_does_not_declare(tmp_path, monkeypatch):
    inputs = _write_inputs(tmp_path)
    inputs["weights"].write_bytes(b"another-model")
    module_, gate, _calls, _state = _patch_flight(monkeypatch)
    with pytest.raises(CalibrationScenarioRefused) as refused:
        module_.write_head_search_scenarios(
            scene_path=inputs["scene"],
            geometry_seal_path=inputs["seal"],
            production_search_config_path=inputs["production"],
            controller_config_path=inputs["controllers"],
            frozen_candidate_path=inputs["frozen"],
            weights_path=inputs["weights"],
            dataset_config_path=inputs["dataset"],
            scenario_partitions_path=inputs["partitions"],
            output_dir=tmp_path / "run-root",
            evidence_root=tmp_path,
            ownership_check=gate,
            detector_factory=lambda plant, request: FakeDetector(plant),
        )

    assert refused.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_the_producer_refuses_an_output_directory_that_already_exists(tmp_path, monkeypatch):
    output = tmp_path / "run-root"
    output.mkdir()
    with pytest.raises(CalibrationScenarioRefused) as refused:
        _produce(tmp_path, monkeypatch, output_dir=output)

    assert refused.value.code == CAL_SCENARIO_RUN_ROOT_EXISTS


def test_the_producer_writes_the_document_the_journal_and_the_receipt_with_provenance(tmp_path, monkeypatch):
    result, _calls, state, inputs, output = _produce(tmp_path, monkeypatch)
    document = json.loads((output / "scenarios.json").read_text(encoding="utf-8"))
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    journal = [
        json.loads(line)
        for line in (output / "scenario-journal.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert document["kind"] == module.KIND
    assert document["phase"] == "scenarios"
    assert document["scenario_count"] == 10
    assert document["passed_count"] == 10
    assert document["seeds"] == list(range(900000, 900010))
    assert document["anchor_split"] == {"default": 4, "forward": 3, "left": 3}
    assert document["qualification_verdict"] is None
    assert document["scene_sha256"] == json.loads(
        (inputs["seal"]).read_text(encoding="utf-8")
    )["source_digests"]["scene_sha256"]
    assert document["weights"]["sha256"] == json.loads(
        inputs["production"].read_text(encoding="utf-8")
    )["weight_sha256"]
    assert document["production_search_config"]["sha256"]
    assert document["values_sha256"]
    assert document["runtime_identity"]
    assert document["ownership_receipt"]["status"] == "EXCLUSIVE_OWNERSHIP_OK"
    assert document["sha256"] == module.canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    assert len(journal) == 10
    assert [row["seed"] for row in journal] == list(range(900000, 900010))
    assert all(set(row) == set(module.JOURNAL_KEYS) for row in journal)
    assert receipt["kind"] == module.RECEIPT_KIND
    assert receipt["scenario_count"] == 10
    assert receipt["document_sha256"] == document["sha256"]
    assert state["closed"] == 10, "every scenario's plant is closed"


def test_every_scenario_gets_its_own_evidence_document(tmp_path, monkeypatch):
    _result, _calls, _state, _inputs, output = _produce(tmp_path, monkeypatch)
    directory = output / module.EVIDENCE_DIR
    files = sorted(path.name for path in directory.glob("*.json"))

    assert len(files) == 10
    assert files[0] == "900000.json"
    assert files[-1] == "900009.json"
    entry = json.loads((directory / "900000.json").read_text(encoding="utf-8"))
    assert entry["seed"] == 900000
    assert entry["outcome"] == "PASSED"
    assert entry["evidence"]["command"] == "so101_head_search_calibration measure-scenarios"
    assert entry["attempts"], "the full attempt evidence is in the per-scenario document"


def test_the_producer_runs_a_declared_subset_and_says_which_seeds_ran(tmp_path, monkeypatch):
    result, _calls, _state, _inputs, output = _produce(tmp_path, monkeypatch, seeds=[900002])
    document = result["document"]

    assert document["scenario_count"] == 1
    assert document["seeds"] == [900002]
    assert document["records"][0]["seed"] == 900002


def test_the_producer_refuses_a_calibration_seed_rather_than_qualifying_it(tmp_path, monkeypatch):
    with pytest.raises(CalibrationScenarioRefused) as refused:
        _produce(tmp_path, monkeypatch, seeds=[700000])

    assert refused.value.code == CAL_SCENARIO_SPLIT_LEAK


def test_the_receipt_records_every_outcome_and_the_anchor_split(tmp_path, monkeypatch):
    result, _calls, _state, _inputs, _output = _produce(tmp_path, monkeypatch)
    receipt = result["receipt"]

    assert receipt["passed_count"] == 10
    assert receipt["failed_count"] == 0
    assert receipt["refused_count"] == 0
    assert receipt["by_condition_class"]["nominal"]["passed"] == 1
    assert receipt["by_condition_class"]["two_cups"]["passed"] == 1
    assert receipt["by_condition_class"]["no_cup"]["passed"] == 1
    assert receipt["anchor_split"] == {"default": 4, "forward": 3, "left": 3}
    assert receipt["records"][0]["outcome"] in ("PASSED", "FAILED", "REFUSED")
    assert receipt["cuda_used"] is True
    assert receipt["allow_cpu_fallback"] is False
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False


def test_the_producer_journals_a_refusal_per_scenario_and_still_reaches_the_last_one(
    tmp_path, monkeypatch
):
    inputs = _write_inputs(tmp_path)
    module_, gate, _calls, _state = _patch_flight(monkeypatch)
    blind = {900000, 900001}

    def detector_factory(plant, request):
        return _class_aware_detector(plant, request, blind=blind)

    result = module_.write_head_search_scenarios(
        scene_path=inputs["scene"],
        geometry_seal_path=inputs["seal"],
        production_search_config_path=inputs["production"],
        controller_config_path=inputs["controllers"],
        frozen_candidate_path=inputs["frozen"],
        weights_path=inputs["weights"],
        dataset_config_path=inputs["dataset"],
        scenario_partitions_path=inputs["partitions"],
        output_dir=tmp_path / "run-root",
        evidence_root=tmp_path,
        ownership_check=gate,
        detector_factory=detector_factory,
    )
    records = result["document"]["records"]

    assert len(records) == 10
    assert [row["outcome"] for row in records[:2]] == ["FAILED", "FAILED"]
    assert records[0]["outcome_code"] == CAL_SCENARIO_CUP_NOT_FOUND
    assert {row["outcome"] for row in records[2:]} == {"PASSED"}


def test_the_producer_reports_the_two_interruption_classes_as_two_attempts(tmp_path, monkeypatch):
    inputs = _write_inputs(tmp_path)
    module_, gate, _calls, _state = _patch_flight(monkeypatch)
    result = module_.write_head_search_scenarios(
        scene_path=inputs["scene"],
        geometry_seal_path=inputs["seal"],
        production_search_config_path=inputs["production"],
        controller_config_path=inputs["controllers"],
        frozen_candidate_path=inputs["frozen"],
        weights_path=inputs["weights"],
        dataset_config_path=inputs["dataset"],
        scenario_partitions_path=inputs["partitions"],
        output_dir=tmp_path / "run-root",
        evidence_root=tmp_path,
        ownership_check=gate,
        detector_factory=_class_aware_detector,
        seeds=[900008, 900009],
    )
    records = result["document"]["records"]

    assert [row["seed"] for row in records] == [900008, 900009]
    assert all(row["condition_class"] in ("fast_interruption", "reacquire_after_stop") for row in records)
    assert all(len(row["attempt_ids"]) == 2 for row in records)
    assert all(row["outcome"] == "PASSED" for row in records)
