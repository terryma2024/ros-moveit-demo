"""HS-307: the closed-loop fine-correction episodes and the `fine_correction_episodes` document.

Every case here runs against an injected scene preparation, an injected plant and an injected detector,
so the closed loop, the split isolation, the correction reduction, every refusal and both documents are
exercised without MuJoCo, a dataset renderer, a detector, a GPU or ROS. The plant is built as the exact
inverse of the controller's own correction law, so a "correct" fixture converges in one correction and a
lagging one needs more.
"""

from __future__ import annotations

import json
import math

import pytest
from so101_demo.act import head_search_fine_correction_episodes as module
from so101_demo.act.head_search_fine_correction_episodes import (
    CAL_FINE_EPISODE_BUDGET_EXHAUSTED,
    CAL_FINE_EPISODE_CORRECTION_MISMATCH,
    CAL_FINE_EPISODE_CUP_NOT_FOUND,
    CAL_FINE_EPISODE_DETECTOR_FAILED,
    CAL_FINE_EPISODE_NO_SUCCESS,
    CAL_FINE_EPISODE_NO_VERDICT,
    CAL_FINE_EPISODE_NOT_CENTERED,
    CAL_FINE_EPISODE_OUT_OF_CORRIDOR,
    CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
    CAL_FINE_EPISODE_SPLIT_LEAK,
    CAL_FINE_EPISODE_TARGET_AMBIGUOUS,
    HELD_OUT_SPLIT,
    KIND,
    RECORD_KEYS,
    REFUSAL_CODES,
    CalibrationFineCorrectionRefused,
    build_fine_correction_episodes,
    condition_class_for_index,
    cup_count_for_condition_class,
    declared_split_seeds,
    episode_record,
    fine_corridor_rad,
    required_domain_excursion_rad,
    run_fine_correction_episode,
    verify_correction_consistency,
    write_head_search_fine_correction_episodes,
)
from so101_demo.act.head_search_timing_measurement import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
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
VERTICAL_BOUNDS_PX = (110.0, 370.0)
#: the seal's required search domain and its lock-valid interval
REQUIRED_DOMAIN_RAD = (-0.17559216195018026, 0.08047101126546086)
LOCK_VALID_RAD = (-6.283175307179587, 6.283175307179587)
#: every top-level key `build_fine_correction_episodes` wrote before HS-324 declared the warm-up frame: the
#: warm-up block is added to this set and no key of it is dropped (the digest covers the new block too)
PRE_WARMUP_FINE_CORRECTION_DOCUMENT_KEYS = (
    "anchors",
    "budget_censored",
    "budget_definition",
    "coarse_corridor_rad",
    "command",
    "control_period_s",
    "control_period_source",
    "controller_budget",
    "controller_thresholds",
    "correction_definition",
    "corridor_definition",
    "cuda_used",
    "dataset_config",
    "detector_loaded",
    "detector_operating_point",
    "device",
    "digest_convention",
    "episode_count",
    "episodes",
    "fine_corridor_rad",
    "frame_period_s",
    "frame_rate_hz",
    "frozen_candidate",
    "geometry_seal",
    "hardware_motion_commanded",
    "kind",
    "lock_frames_required",
    "locked_outside_required_domain_count",
    "measured_here",
    "measurement_budget",
    "motion_commanded",
    "mujoco_neck_commanded",
    "path",
    "phase",
    "production_search_config",
    "records",
    "records_semantics",
    "refused_count",
    "required_domain_excursions",
    "ros_nodes_started",
    "runtime_identity",
    "scene_definition",
    "scene_path",
    "scene_preparation",
    "scene_sha256",
    "schema_version",
    "sha256",
    "simulation_timestep_s",
    "split_declaration",
    "succeeded_count",
    "success_definition",
    "time_base",
    "tracking_detail",
    "tracking_measured",
    "transport_measured",
    "weights",
)

PARTITIONS = {
    "schema_version": 1,
    "document": "head-search-scenario-partitions/v1",
    "condition_classes": [
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
    ],
    "anchors": ["default", "left", "forward"],
    "calibration": [700000, 700001],
    "held_out_evaluation": [800000, 800001, 800002, 800003],
}


def _controller_config(**overrides) -> dict:
    config = {
        "attempt_id": "episode-attempt",
        "session_id": "episode-session",
        "search_start_rad": 0.0,
        "horizontal_fov_rad": 1.3121067481206794,
        "coarse_step_rad": 0.3,
        "search_timeout_s": 30.0,
        "max_age_s": 0.05,
        "max_skew_s": 0.02,
        "settle_velocity_rad_s": 0.05,
        "goal_tolerance_rad": 0.05,
        "center_deadband_px": 3.0,
        "vertical_bounds_px": list(VERTICAL_BOUNDS_PX),
        "min_area_px2": 64.0,
        "min_confidence": 0.4,
        "max_fine_corrections": 8,
        "max_fine_total_rad": 2.0,
        "frame_id": "head_camera_frame",
        "ray_origin_frame_id": "head_camera_frame",
        "required_search_domain_rad": list(REQUIRED_DOMAIN_RAD),
        "lock_valid_neck_rad": list(LOCK_VALID_RAD),
    }
    config.update(overrides)
    return config


def _project(yaw_rad: float, cup_yaw_rad: float) -> float:
    """The pixel column a cup at `cup_yaw_rad` lands on while the neck holds `yaw_rad`.

    This is the exact inverse of the controller's own correction law, so a plant built on it converges in
    one correction whose magnitude is `cup_yaw_rad - yaw_rad`.
    """

    return PRINCIPAL_X_PX - GAIN_PX_PER_RAD * math.tan(cup_yaw_rad - yaw_rad)


class FakePlant:
    """A yaw-only plant: command a target, move a declared fraction of the way, render a frame."""

    def __init__(self, *, cup_yaw_rad: float, yaw_rad: float = 0.0, follow_gain: float = 1.0) -> None:
        self.cup_yaw_rad = float(cup_yaw_rad)
        self.yaw_rad = float(yaw_rad)
        self.follow_gain = float(follow_gain)
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
        self.time_s += CONTROL_STEPS * TIMESTEP_S
        stop = {
            "index": None,
            "kind": "plan",
            "target_rad": float(target_rad),
            "start_rad": start_rad,
            "sim_start_s": start_sim,
            "sim_end_s": self.time_s,
            "steps": CONTROL_STEPS,
            "settle_s": self.time_s - start_sim,
            "settled": True,
            "reached": True,
            "final_velocity_rad_s": 0.0,
            "final_position_error_rad": float(target_rad) - self.yaw_rad,
            "quiet_steps": CONTROL_STEPS,
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

    def reset(self) -> None:
        self.calls = 0

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


def episode(*, plant, detector=None, coarse=None, fine=None, config=None, clock=None, **kwargs):
    return run_fine_correction_episode(
        controller_config=_controller_config() if config is None else config,
        plant=plant,
        detector=FakeDetector(plant) if detector is None else detector,
        coarse_corridor_rad=REQUIRED_DOMAIN_RAD if coarse is None else coarse,
        fine_corridor_rad=LOCK_VALID_RAD if fine is None else fine,
        episode_id=f"{HELD_OUT_SPLIT}-800000",
        seed=800000,
        split=HELD_OUT_SPLIT,
        scenario="one_cup_distractors",
        anchor="left",
        clock=_clock() if clock is None else clock,
        **kwargs,
    )


# --- the declared split and the scene convention ------------------------------------------------


def test_the_held_out_seeds_are_the_declared_partition_and_the_order_is_kept():
    assert declared_split_seeds(PARTITIONS, split=HELD_OUT_SPLIT) == [800000, 800001, 800002, 800003]
    assert declared_split_seeds(PARTITIONS, split=HELD_OUT_SPLIT, seeds=[800002, 800000]) == [
        800002,
        800000,
    ]


def test_the_declared_seed_list_refuses_a_calibration_seed():
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        declared_split_seeds(PARTITIONS, split=HELD_OUT_SPLIT, seeds=[700000])

    assert refused.value.code == CAL_FINE_EPISODE_SPLIT_LEAK
    assert "700000" in str(refused.value)


def test_the_producer_refuses_a_held_out_seed_offered_as_a_calibration_episode():
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        declared_split_seeds(PARTITIONS, split="calibration", seeds=[800000])

    assert refused.value.code == CAL_FINE_EPISODE_SPLIT_LEAK


def test_a_split_the_partitions_do_not_declare_is_a_refusal_rather_than_an_empty_measurement():
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        declared_split_seeds(PARTITIONS, split="validation")

    assert refused.value.code == CAL_TIMING_EVIDENCE_MISSING


def test_an_empty_seed_declaration_is_a_refusal_rather_than_an_empty_document():
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        declared_split_seeds(PARTITIONS, split=HELD_OUT_SPLIT, seeds=[])

    assert refused.value.code == CAL_TIMING_EVIDENCE_MISSING


def test_the_episode_condition_classes_follow_the_recorders_own_convention():
    """`record_episodes7.py:40` assigns `CLASSES[min(index // 2, len(classes) - 1)]`."""

    classes = PARTITIONS["condition_classes"]
    assert [condition_class_for_index(index, classes) for index in range(6)] == [
        "nominal",
        "nominal",
        "left_anchor",
        "left_anchor",
        "forward_anchor",
        "forward_anchor",
    ]
    assert cup_count_for_condition_class("no_cup") == 0
    assert cup_count_for_condition_class("two_cups") == 2
    assert cup_count_for_condition_class("nominal") == 1


def test_the_cup_count_of_every_declared_class_is_one_of_the_three_dataset_scenarios():
    for name in PARTITIONS["condition_classes"]:
        assert cup_count_for_condition_class(name) in (0, 1, 2)


# --- the two corridors --------------------------------------------------------------------------


def test_the_fine_corridor_is_the_seals_lock_valid_interval_and_not_the_required_domain():
    """The required domain is the coverage the coarse sweep owes; the fine path is bounded by the seal."""

    seal = {
        "lock_valid_neck_rad": list(LOCK_VALID_RAD),
        "required_search_domain_rad": list(REQUIRED_DOMAIN_RAD),
    }

    assert fine_corridor_rad(geometry_seal=seal) == pytest.approx(LOCK_VALID_RAD)
    assert REQUIRED_DOMAIN_RAD[1] < 0.2 < LOCK_VALID_RAD[1]


def test_the_fine_corridor_refuses_a_seal_that_declares_no_lock_valid_interval():
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        fine_corridor_rad(geometry_seal={"required_search_domain_rad": list(REQUIRED_DOMAIN_RAD)})

    assert refused.value.code == CAL_TIMING_EVIDENCE_MISSING


def test_the_required_domain_excursion_is_zero_inside_and_positive_outside():
    assert required_domain_excursion_rad(0.0, REQUIRED_DOMAIN_RAD) == 0.0
    assert required_domain_excursion_rad(REQUIRED_DOMAIN_RAD[0], REQUIRED_DOMAIN_RAD) == 0.0
    assert required_domain_excursion_rad(0.2, REQUIRED_DOMAIN_RAD) == pytest.approx(
        0.2 - REQUIRED_DOMAIN_RAD[1]
    )
    assert required_domain_excursion_rad(-0.5, REQUIRED_DOMAIN_RAD) == pytest.approx(
        REQUIRED_DOMAIN_RAD[0] + 0.5
    )


# --- the closed loop ----------------------------------------------------------------------------


def test_a_locked_episode_records_one_correction_whose_magnitude_is_the_cups_bearing():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    result = episode(plant=plant)

    assert result["succeeded"] is True
    assert result["terminal_status"] == "TARGET_LOCKED"
    assert result["fine_corrections"] == 1
    assert result["fine_corrections_rad"] == pytest.approx([0.0588], abs=1e-9)
    assert result["cumulative_fine_correction_rad"] == pytest.approx(0.0588, abs=1e-9)
    assert result["largest_single_correction_rad"] == pytest.approx(0.0588, abs=1e-9)
    assert result["failure_code"] is None
    # the controller's own counters agree with the reduction, which is what makes the count checkable
    assert result["controller_fine_count"] == 1
    assert result["controller_fine_angle_rad"] == pytest.approx(0.0588, abs=1e-9)
    # the loop rendered a frame per iteration plus its declared warm-up frame, and commanded the plant
    assert plant.frames_rendered == len(result["frames"]) + 1
    assert result["warmup"]["performed"] is True
    assert plant.commands[0] == 0.0


def test_a_lagging_loop_records_every_correction_in_order_and_the_controllers_own_total():
    plant = FakePlant(cup_yaw_rad=-0.10, follow_gain=0.6)
    result = episode(plant=plant)

    assert result["succeeded"] is True
    assert result["fine_corrections"] == 3
    magnitudes = result["fine_corrections_rad"]
    assert magnitudes == pytest.approx([0.10, 0.04, 0.016], abs=1e-6)
    assert result["cumulative_fine_correction_rad"] == pytest.approx(sum(magnitudes))
    assert result["largest_single_correction_rad"] == pytest.approx(magnitudes[0])
    assert result["controller_fine_count"] == 3
    assert result["controller_fine_angle_rad"] == pytest.approx(sum(magnitudes), abs=1e-12)


def test_a_plan_advance_is_never_counted_as_a_fine_correction():
    # the cup is off the image until the second plan stop, so the first two moves are the bounded sweep's
    plant = FakePlant(cup_yaw_rad=-0.80)
    result = episode(plant=plant)

    moves = [frame["move_kind"] for frame in result["frames"] if frame["move_kind"] != "hold"]
    assert moves == ["plan", "plan", "fine"]
    assert result["fine_corrections"] == 1
    assert result["fine_corrections_rad"] == pytest.approx([0.6244], abs=1e-3)
    assert result["succeeded"] is True


def test_the_locked_neck_angle_outside_the_required_domain_is_recorded_as_an_excursion():
    result = episode(plant=FakePlant(cup_yaw_rad=-0.80))

    assert result["locked_neck_rad"] == pytest.approx(-0.80, abs=1e-6)
    assert result["required_domain_excursion_rad"] == pytest.approx(
        0.80 - 0.17559216195018026, abs=1e-6
    )
    assert result["locked_outside_required_domain"] is True


def test_an_episode_locked_inside_the_required_domain_records_no_excursion():
    result = episode(plant=FakePlant(cup_yaw_rad=-0.0588))

    assert result["required_domain_excursion_rad"] == 0.0
    assert result["locked_outside_required_domain"] is False


# --- every honest refusal of a single episode ----------------------------------------------------


def test_an_episode_whose_cup_is_never_found_records_a_refusal_and_no_count():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    result = episode(plant=plant, detector=FakeDetector(plant, cups=0))

    assert result["succeeded"] is False
    assert result["failure_code"] == CAL_FINE_EPISODE_CUP_NOT_FOUND
    assert result["fine_corrections"] is None
    assert result["fine_corrections_rad"] == []
    assert result["cumulative_fine_correction_rad"] is None
    assert result["terminal_status"] == "TARGET_NOT_FOUND"
    assert result["budget_binding"] is False


def test_a_two_cup_frame_is_a_refusal_and_never_one_of_the_two_counted():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    result = episode(plant=plant, detector=FakeDetector(plant, cups=2))

    assert result["succeeded"] is False
    assert result["failure_code"] == CAL_FINE_EPISODE_TARGET_AMBIGUOUS
    assert result["terminal_status"] == "TARGET_AMBIGUOUS"
    assert result["fine_corrections"] is None


def test_an_episode_that_exhausts_its_own_declared_budget_records_the_binding_budget():
    plant = FakePlant(cup_yaw_rad=-0.80)
    config = _controller_config(max_fine_corrections=1, max_fine_total_rad=2.0)
    detector = FakeDetector(plant, jitter_px=(0.0, 9.0))
    result = episode(plant=plant, detector=detector, config=config)

    assert result["succeeded"] is False
    assert result["fine_corrections"] is None
    assert result["terminal_status"] == "TARGET_NOT_CENTERED"
    assert result["failure_code"] in (CAL_FINE_EPISODE_BUDGET_EXHAUSTED, CAL_FINE_EPISODE_NOT_CENTERED)
    assert result["budget_binding"] is True


def test_a_fine_correction_that_leaves_the_fine_corridor_is_a_refusal_not_a_clamped_command():
    plant = FakePlant(cup_yaw_rad=-0.80)
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        episode(plant=plant, fine=(-0.3, 0.3))

    assert refused.value.code == CAL_FINE_EPISODE_OUT_OF_CORRIDOR
    assert all(abs(command) <= 0.3 for command in plant.commands)


def test_a_plan_stop_outside_the_coarse_corridor_is_a_refusal_not_a_clamped_command():
    plant = FakePlant(cup_yaw_rad=-0.80)
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        episode(plant=plant, coarse=(-0.05, 0.05))

    assert refused.value.code == CAL_FINE_EPISODE_OUT_OF_CORRIDOR


def test_a_search_start_outside_the_coarse_corridor_is_refused_before_anything_is_commanded():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        episode(plant=plant, coarse=(0.05, 0.2))

    assert refused.value.code == CAL_FINE_EPISODE_OUT_OF_CORRIDOR
    assert plant.commands == []


def test_a_detector_that_fails_is_a_refusal_of_the_document_and_not_a_zero_count():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        episode(plant=plant, detector=FakeDetector(plant, fail_at=(0,)))

    assert refused.value.code == CAL_FINE_EPISODE_DETECTOR_FAILED
    assert "DETECTOR_FAILED" in str(refused.value)


def test_a_loop_that_never_reaches_a_verdict_refuses_rather_than_recording_no_corrections():
    plant = FakePlant(cup_yaw_rad=-0.10)
    detector = FakeDetector(plant, jitter_px=(9.0, -9.0))
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        episode(plant=plant, detector=detector, max_frames=6)

    assert refused.value.code == CAL_FINE_EPISODE_NO_VERDICT
    assert len(plant.stops) <= 7


def test_a_settle_time_that_is_not_the_simulation_clocks_refuses_the_episode():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    honest = plant.settle_to

    def broken(target_rad: float) -> dict:
        stop = honest(target_rad)
        stop["sim_end_s"] = stop["sim_start_s"] + 0.5 * stop["steps"]
        plant.time_s = stop["sim_end_s"]
        return stop

    plant.settle_to = broken  # type: ignore[method-assign]
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        episode(plant=plant)

    assert refused.value.code == CAL_TIMING_TIME_BASE_UNVERIFIED


# --- the declared warm-up frame (HS-324) --------------------------------------------------------


#: the promoted `max_age_s` (HS-296: p99.9 of the frame age + 10 ms) that refused this episode's frame 0
PROMOTED_MAX_AGE_S = 0.014736005008453503
#: the one-off cost HS-323 measured for the process's first detection-bearing predict (31-37 ms)
FIRST_DETECTION_COST_S = 0.035


class StepClock:
    """A monotonic clock the fixture can advance, so a detector call can pay a declared one-off cost."""

    def __init__(self, start: float = 1000.0, step: float = 0.001) -> None:
        self.now = float(start)
        self.step = float(step)

    def __call__(self) -> float:
        self.now += self.step
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += float(seconds)


class OneOffDetectionCostDetector:
    """The production detector's measured one-off cost (HS-323 section 2.2).

    `YoloSegDetector`'s constructor warms the model up on a zeros image, which carries no box and no mask
    and costs 5.3 ms; the first predict that really resolves a detection costs 34.2 ms and every later one
    4.2-5.4 ms. `paid_on_detection_call` selects which detection-bearing call pays that cost, so a fixture
    can put it on the warm-up frame or inside a measured frame.
    """

    def __init__(
        self,
        plant: FakePlant,
        clock: StepClock,
        *,
        cost_s: float = FIRST_DETECTION_COST_S,
        paid_on_detection_call: int = 1,
    ) -> None:
        self.plant = plant
        self.clock = clock
        self.cost_s = float(cost_s)
        self.paid_on_detection_call = int(paid_on_detection_call)
        self.calls = 0
        self.detection_calls = 0
        self.paid = False

    def reset(self) -> None:
        """The production reset clears the attempt's own state; it never re-colds a warm model."""

        self.calls = 0

    def __call__(self, image, stamp_ns):
        self.calls += 1
        column = _project(float(image["yaw_rad"]), self.plant.cup_yaw_rad)
        if column - 30.0 < 0.0 or column + 30.0 > WIDTH_PX:
            return []
        self.detection_calls += 1
        if not self.paid and self.detection_calls == self.paid_on_detection_call:
            self.paid = True
            self.clock.advance(self.cost_s)
        return [
            {
                "xyxy": (column - 30.0, PRINCIPAL_Y_PX - 30.0, column + 30.0, PRINCIPAL_Y_PX + 30.0),
                "confidence": 0.9,
                "class_id": 0,
                "track_id": "head-cup-0",
            }
        ]


def test_the_warm_up_frame_is_performed_and_recorded_before_the_measured_frames():
    clock = StepClock()
    plant = FakePlant(cup_yaw_rad=-0.0588)
    detector = OneOffDetectionCostDetector(plant, clock)

    result = episode(
        plant=plant,
        detector=detector,
        config=_controller_config(max_age_s=PROMOTED_MAX_AGE_S),
        clock=clock,
    )

    warmup = result["warmup"]
    assert set(warmup) == {"performed", "detections", "wall_s", "declared_because"}
    assert warmup["performed"] is True
    assert warmup["detections"] == 1  # a real frame with a box, not the constructor's zeros
    assert warmup["wall_s"] >= FIRST_DETECTION_COST_S
    assert warmup["declared_because"] == module.WARMUP_POLICY
    # the warm-up is the detection-bearing call before the first measured frame, and it is not measured
    assert detector.detection_calls == len(result["frames"]) + 1
    assert result["detection_frames"] == len(result["frames"])
    assert [frame["frame_index"] for frame in result["frames"]] == list(range(len(result["frames"])))


def test_the_warm_up_frame_is_excluded_from_the_measured_ages_under_the_promoted_max_age():
    """HS-323: this is the fixture whose first measured frame refused both flights (`INPUT_STALE`)."""

    clock = StepClock()
    plant = FakePlant(cup_yaw_rad=-0.0588)
    detector = OneOffDetectionCostDetector(plant, clock)

    result = episode(
        plant=plant,
        detector=detector,
        config=_controller_config(max_age_s=PROMOTED_MAX_AGE_S),
        clock=clock,
    )

    ages = [
        frame["decision_monotonic_s"] - frame["received_monotonic_s"] for frame in result["frames"]
    ]
    assert result["succeeded"] is True
    assert result["terminal_status"] == "TARGET_LOCKED"
    assert result["fine_corrections"] >= 1
    assert detector.paid is True
    assert 0.0 < min(ages) and max(ages) <= PROMOTED_MAX_AGE_S
    assert result["warmup"]["wall_s"] >= FIRST_DETECTION_COST_S > max(ages)


def test_a_one_off_cost_inside_a_measured_frame_is_still_refused_by_the_freshness_gate():
    """The fix declares and excludes a warm-up frame; it never widens `max_age_s`."""

    clock = StepClock()
    plant = FakePlant(cup_yaw_rad=-0.0588)
    detector = OneOffDetectionCostDetector(plant, clock, paid_on_detection_call=2)

    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        episode(
            plant=plant,
            detector=detector,
            config=_controller_config(max_age_s=PROMOTED_MAX_AGE_S),
            clock=clock,
        )

    assert refused.value.code == CAL_FINE_EPISODE_NO_VERDICT
    assert "INPUT_STALE" in refused.value.detail


# --- the count the controller itself reports -----------------------------------------------------


def test_a_correction_count_the_controller_did_not_make_is_refused():
    verify_correction_consistency(
        episode_id="e", count=1, magnitudes=[0.1], controller_fine_count=1, controller_fine_angle_rad=0.1
    )

    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        verify_correction_consistency(
            episode_id="e",
            count=2,
            magnitudes=[0.1, 0.1],
            controller_fine_count=1,
            controller_fine_angle_rad=0.1,
        )
    assert refused.value.code == CAL_FINE_EPISODE_CORRECTION_MISMATCH

    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        verify_correction_consistency(
            episode_id="e",
            count=1,
            magnitudes=[0.1],
            controller_fine_count=1,
            controller_fine_angle_rad=0.2,
        )
    assert refused.value.code == CAL_FINE_EPISODE_CORRECTION_MISMATCH


def test_a_negative_or_non_finite_magnitude_is_a_caller_error():
    with pytest.raises(ValueError, match="positive"):
        verify_correction_consistency(
            episode_id="e",
            count=1,
            magnitudes=[-0.1],
            controller_fine_count=1,
            controller_fine_angle_rad=0.1,
        )


# --- the document -------------------------------------------------------------------------------


def _locked_episode():
    return episode(plant=FakePlant(cup_yaw_rad=-0.0588))


def _missing_episode():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    return episode(plant=plant, detector=FakeDetector(plant, cups=0))


def _two_episodes():
    return [_locked_episode(), _missing_episode()]


def _seal():
    return {
        "required_search_domain_rad": list(REQUIRED_DOMAIN_RAD),
        "lock_valid_neck_rad": list(LOCK_VALID_RAD),
        "horizontal_fov_rad": 1.3121067481206794,
        "image_width": WIDTH_PX,
        "image_height": HEIGHT_PX,
        "camera_name": "head_camera",
        "camera": {"fovy_rad": 1.0471975511965976},
        "in_frame_matrix": {"left": {"neck_start_rad": 0.0}},
        "workspace_matrix": {
            "key_samples": [{"anchor": "left", "kind": "anchor", "point_m": [-0.08, -0.28, 0.165]}]
        },
        "source_digests": {"scene_sha256": "a" * 64},
    }


def _document(tmp_path, *, episodes=None):
    return build_fine_correction_episodes(
        path=tmp_path / "fine-correction-episodes.json",
        command="ros2 run so101_demo_py so101_head_search_calibration measure-fine-correction-episodes",
        episodes=_two_episodes() if episodes is None else episodes,
        controller_config=_controller_config(),
        control={"control_period_s": 0.002, "source_path": "/sealed/ros2_controllers.yaml"},
        scene_path=tmp_path / "head_search_scene.xml",
        scene_sha256="b" * 64,
        dataset_config_path=tmp_path / "head_camera_yolo_seg.yaml",
        dataset_config_sha256="9" * 64,
        geometry_seal_path=tmp_path / "head-camera-geometry.json",
        geometry_seal_sha256="c" * 64,
        production_search_config_path=tmp_path / "head_search_v2.json",
        production_search_config_sha256="d" * 64,
        frozen_candidate_path=tmp_path / "frozen-c.json",
        frozen_candidate_sha256="e" * 64,
        weights_path=tmp_path / "C.pt",
        weights_sha256="f" * 64,
        scenario_partitions_path=tmp_path / "head-search-scenario-partitions-v1.json",
        scenario_partitions_sha256="1" * 64,
        split=HELD_OUT_SPLIT,
        seeds=[800000, 800001],
        detector_operating_point={"min_confidence": 0.25, "iou": 0.5},
        coarse_corridor_rad=REQUIRED_DOMAIN_RAD,
        fine_corridor_rad=LOCK_VALID_RAD,
        measurement_budget={"max_fine_corrections": 8, "max_fine_total_rad": 2.0},
        runtime_identity_document={"python_executable": "/usr/bin/python3", "cuda_available": True},
    )


def test_the_document_carries_the_records_phase_six_reads(tmp_path):
    document = _document(tmp_path)

    assert document["kind"] == KIND
    assert document["phase"] == "fine_correction_episodes"
    assert tuple(document["records"][0]) == RECORD_KEYS
    assert [record["episode_id"] for record in document["records"]] == [
        document["episodes"][0]["episode_id"],
        document["episodes"][1]["episode_id"],
    ]
    assert document["records"][0]["succeeded"] is True
    assert document["records"][0]["fine_corrections"] == 1
    assert document["records"][0]["fine_corrections_rad"] == pytest.approx([0.0588], abs=1e-9)
    assert document["records"][1]["succeeded"] is False
    assert document["records"][1]["fine_corrections"] is None
    assert document["records"][1]["fine_corrections_rad"] == []
    assert all(record["split"] == HELD_OUT_SPLIT for record in document["records"])
    assert document["ros_nodes_started"] is False
    assert document["hardware_motion_commanded"] is False
    assert document["mujoco_neck_commanded"] is True
    assert document["measured_here"] is True
    assert document["cuda_used"] is True


def test_the_document_records_the_split_so_the_isolation_rule_is_checkable(tmp_path):
    document = _document(tmp_path)

    declared = document["split_declaration"]
    assert declared["split"] == HELD_OUT_SPLIT
    assert declared["seeds"] == [800000, 800001]
    assert declared["calibration_seeds_used"] == []
    assert declared["held_out_only"] is True
    assert declared["partitions_sha256"] == "1" * 64
    assert document["episode_count"] == 2
    assert document["succeeded_count"] == 1
    assert document["refused_count"] == 1


def test_the_document_digest_covers_every_field_but_itself(tmp_path):
    from so101_demo.perception_benchmark.contracts import canonical_sha256

    document = _document(tmp_path)

    assert document["sha256"] == canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    assert len(document["sha256"]) == 64


def test_the_document_gains_the_warm_up_block_without_losing_a_key(tmp_path):
    """HS-324: the whole key set this producer wrote before the warm-up was declared, plus the block."""

    document = _document(tmp_path)

    assert set(document) == set(PRE_WARMUP_FINE_CORRECTION_DOCUMENT_KEYS) | {
        "warmup",
        "warmup_samples_excluded",
    }
    assert set(document["warmup"]) == {"performed", "detections", "wall_s", "declared_because"}
    assert document["warmup"]["performed"] is True
    assert document["warmup"]["detections"] == 1
    assert document["warmup"]["declared_because"] == module.WARMUP_POLICY
    assert document["warmup_samples_excluded"] is True
    # the block is the first flight's own warm-up, and every flight declares the one it performed
    assert document["warmup"] == document["episodes"][0]["warmup"]
    assert all(episode["warmup"]["performed"] is True for episode in document["episodes"])
    assert document["warmup"] not in [
        frame for episode in document["episodes"] for frame in episode["frames"]
    ]


def test_the_document_refuses_an_episode_of_a_split_the_caller_did_not_declare(tmp_path):
    leaked = dict(_locked_episode())
    leaked["split"] = "calibration"

    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        _document(tmp_path, episodes=[leaked])

    assert refused.value.code == CAL_FINE_EPISODE_SPLIT_LEAK


def test_the_document_refuses_a_budget_censored_episode_instead_of_understating_the_maximum(tmp_path):
    censored = dict(_locked_episode())
    censored["budget_binding"] = True

    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        _document(tmp_path, episodes=[censored])

    assert refused.value.code == CAL_FINE_EPISODE_BUDGET_EXHAUSTED


def test_a_document_with_no_successful_episode_refuses_rather_than_inventing_a_count(tmp_path):
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        _document(tmp_path, episodes=[_missing_episode()])

    assert refused.value.code == CAL_FINE_EPISODE_NO_SUCCESS


def test_episode_record_keeps_exactly_the_keys_phase_six_reads():
    record = episode_record(_missing_episode())

    assert tuple(record) == RECORD_KEYS
    assert record["fine_corrections"] is None
    assert record["succeeded"] is False
    assert record["split"] == HELD_OUT_SPLIT


def test_the_producer_declares_the_refusal_vocabulary_it_can_raise():
    for code in (
        CAL_FINE_EPISODE_SPLIT_LEAK,
        CAL_FINE_EPISODE_OUT_OF_CORRIDOR,
        CAL_FINE_EPISODE_BUDGET_EXHAUSTED,
        CAL_FINE_EPISODE_CORRECTION_MISMATCH,
        CAL_FINE_EPISODE_NO_VERDICT,
        CAL_FINE_EPISODE_NO_SUCCESS,
        CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
        CAL_TIMING_EVIDENCE_MISSING,
        CAL_TIMING_EVIDENCE_CONTRADICTORY,
        CAL_TIMING_TIME_BASE_UNVERIFIED,
    ):
        assert code in REFUSAL_CODES


# --- the producer -------------------------------------------------------------------------------


def _sealed_inputs(tmp_path):
    seal = _seal()
    production = {
        "weight_path": "models/head-search/yolo11n-seg-best.pt",
        "weight_sha256": "b" * 64,
        "tracker": {"iou_threshold": 0.3},
        "camera": {
            "frame_id": "head_camera_frame",
            "ray_origin_frame_id": "head_camera_frame",
        },
        "motion": {"goal_tolerance_rad": 0.05, "settle_velocity_rad_s": 0.05},
        "values": {
            "coarse_step_rad": 0.3,
            "search_timeout_s": 12.0,
            "max_age_s": 0.05,
            "max_skew_s": 0.02,
            "center_deadband_px": 18.0,
            "vertical_bounds_px": list(VERTICAL_BOUNDS_PX),
            "min_area_px2": 64.0,
            "min_confidence": 0.4,
            "max_fine_corrections": 4,
            "max_fine_total_rad": 0.4,
            "horizontal_fov_rad": 1.3121067481206794,
            "lock_valid_neck_rad": list(LOCK_VALID_RAD),
        },
    }
    weights_path = tmp_path / "C.pt"
    weights_path.write_bytes(b"weights")
    frozen = {
        "candidate_id": "C",
        "weight_sha256": module._digest(weights_path),
        "operating_points": {"head": {"min_confidence": 0.25, "tracker": {"iou": 0.5}}},
    }
    scene = tmp_path / "head_search_scene.xml"
    scene.write_text("<mujoco/>\n", encoding="utf-8")
    # the fixture pins itself: the sealed geometry records the scene it was measured against and the
    # production configuration the weights it declares, so a test that tampers with either still refuses
    seal["source_digests"]["scene_sha256"] = module._digest(scene)
    seal_path = tmp_path / "head-camera-geometry.json"
    seal_path.write_text(json.dumps(seal), encoding="utf-8")
    production["weight_sha256"] = module._digest(weights_path)
    production_path = tmp_path / "head_search_v2.json"
    production_path.write_text(json.dumps(production), encoding="utf-8")
    frozen_path = tmp_path / "frozen-c.json"
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    controllers_path = tmp_path / "ros2_controllers.yaml"
    controllers_path.write_text(
        "controller_manager:\n  ros__parameters:\n    update_rate: 500\n", encoding="utf-8"
    )
    partitions_path = tmp_path / "head-search-scenario-partitions-v1.json"
    partitions_path.write_text(json.dumps(PARTITIONS), encoding="utf-8")
    dataset_config_path = tmp_path / "head_camera_yolo_seg.yaml"
    dataset_config_path.write_text(
        "mjcf_path: head_search_scene.xml\ncamera_name: head_camera\n"
        "image_width: 640\nimage_height: 480\n",
        encoding="utf-8",
    )
    return {
        "scene": scene,
        "seal": seal_path,
        "production": production_path,
        "frozen": frozen_path,
        "controllers": controllers_path,
        "weights": weights_path,
        "partitions": partitions_path,
        "dataset_config": dataset_config_path,
    }


def _patch_scene_declaration(monkeypatch):
    """The sealed scene is a stub here: the declaration reader is the MuJoCo module's own."""

    monkeypatch.setattr(
        module,
        "read_mujoco_timestep",
        lambda path: {"simulation_timestep_s": TIMESTEP_S, "scene_sha256": module._digest(path)},
    )


def _producer(
    tmp_path,
    monkeypatch,
    *,
    inputs=None,
    seeds=(800000, 800001),
    weights=None,
    device="cpu",
    plant_factory=None,
    detector_factory=None,
    scene_preparer=None,
):
    _patch_scene_declaration(monkeypatch)
    inputs = _sealed_inputs(tmp_path) if inputs is None else inputs

    return write_head_search_fine_correction_episodes(
        scene_path=inputs["scene"],
        geometry_seal_path=inputs["seal"],
        production_search_config_path=inputs["production"],
        controller_config_path=inputs["controllers"],
        frozen_candidate_path=inputs["frozen"],
        weights_path=inputs["weights"] if weights is None else weights,
        dataset_config_path=inputs["dataset_config"],
        scenario_partitions_path=inputs["partitions"],
        output_dir=tmp_path / "out",
        device=device,
        seeds=list(seeds),
        scene_preparer=(lambda **request: {}) if scene_preparer is None else scene_preparer,
        plant=plant_factory or (lambda request: FakePlant(cup_yaw_rad=-0.0588)),
        detector_factory=detector_factory or (lambda plant, request: FakeDetector(plant)),
    )


def test_the_producer_writes_the_document_the_receipt_and_every_episode(tmp_path, monkeypatch):
    result = _producer(tmp_path, monkeypatch)

    document = result["document"]
    assert [record["episode_id"] for record in document["records"]] == [
        f"{HELD_OUT_SPLIT}-800000",
        f"{HELD_OUT_SPLIT}-800001",
    ]
    assert len(result["episodes"]) == 2
    assert (tmp_path / "out" / "fine-correction-episodes.json").is_file()
    receipt = result["receipt"]
    assert receipt["document_sha256"] == document["sha256"]
    assert receipt["episode_count"] == 2
    assert receipt["succeeded_count"] == 2
    assert receipt["split"] == HELD_OUT_SPLIT
    assert receipt["seeds"] == [800000, 800001]
    assert receipt["ros_nodes_started"] is False
    assert receipt["mujoco_neck_commanded"] is True
    assert receipt["hardware_motion_commanded"] is False


def test_the_producer_records_the_warm_up_frame_it_excluded(tmp_path, monkeypatch):
    result = _producer(tmp_path, monkeypatch)

    document = result["document"]
    receipt = result["receipt"]

    assert receipt["warmup"] == document["warmup"]
    assert receipt["warmup"]["performed"] is True
    assert receipt["warmup"]["detections"] == 1
    assert document["warmup_samples_excluded"] is True


def test_the_producer_refuses_a_scene_the_sealed_geometry_does_not_pin(tmp_path, monkeypatch):
    inputs = _sealed_inputs(tmp_path)
    _producer(tmp_path, monkeypatch, inputs=inputs)
    tampered = json.loads(inputs["seal"].read_text(encoding="utf-8"))
    tampered["source_digests"]["scene_sha256"] = "0" * 64
    inputs["seal"].write_text(json.dumps(tampered), encoding="utf-8")

    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        _producer(tmp_path / "second", monkeypatch, inputs=inputs)

    assert refused.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_the_producer_refuses_weights_the_sealed_configuration_does_not_declare(tmp_path, monkeypatch):
    inputs = _sealed_inputs(tmp_path)
    _producer(tmp_path, monkeypatch, inputs=inputs)
    other = tmp_path / "other.pt"
    other.write_bytes(b"other weights")

    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        _producer(tmp_path / "second", monkeypatch, inputs=inputs, weights=other)

    assert refused.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_the_producer_refuses_an_output_directory_that_already_exists(tmp_path, monkeypatch):
    _producer(tmp_path, monkeypatch)

    with pytest.raises(FileExistsError):
        _producer(tmp_path, monkeypatch, inputs=_sealed_inputs(tmp_path))


def test_the_producer_refuses_a_calibration_seed_offered_as_a_held_out_episode(tmp_path, monkeypatch):
    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        _producer(tmp_path, monkeypatch, seeds=[700000])

    assert refused.value.code == CAL_FINE_EPISODE_SPLIT_LEAK
    assert not (tmp_path / "out").exists()


def test_the_producer_refuses_a_declared_cuda_device_without_one(tmp_path, monkeypatch):
    monkeypatch.setattr(module, "_cuda_available", lambda: False)

    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        _producer(tmp_path, monkeypatch, device="cuda")

    assert refused.value.code == CAL_TIMING_DEVICE_UNAVAILABLE


def test_the_producer_refuses_a_dataset_config_whose_scene_is_not_the_sealed_one(tmp_path, monkeypatch):
    inputs = _sealed_inputs(tmp_path)
    _producer(tmp_path / "first", monkeypatch, inputs=inputs)
    inputs["dataset_config"].write_text(
        "mjcf_path: another_scene.xml\ncamera_name: head_camera\n"
        "image_width: 640\nimage_height: 480\n",
        encoding="utf-8",
    )

    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        _producer(tmp_path / "second", monkeypatch, inputs=inputs)

    assert refused.value.code == CAL_FINE_EPISODE_SCENE_CONTRADICTORY


def test_the_producer_declares_what_it_prepared_and_what_it_never_started(tmp_path, monkeypatch):
    document = _producer(tmp_path, monkeypatch)["document"]

    assert document["scene_preparation"]["cup_placement"].startswith(
        "prepared by the dataset renderer"
    )
    assert document["scene_preparation"]["scenario_by_seed"]["800000"] == "one_cup_distractors"
    assert document["fine_corridor_rad"] == pytest.approx(list(LOCK_VALID_RAD))
    assert document["coarse_corridor_rad"] == pytest.approx(list(REQUIRED_DOMAIN_RAD))
    assert document["measurement_budget"] == {"max_fine_corrections": 8, "max_fine_total_rad": 2.0}
    assert document["budget_censored"] is False
    assert document["ros_nodes_started"] is False
    assert document["hardware_motion_commanded"] is False


def test_a_lock_that_needed_no_correction_is_refused_rather_than_written_as_a_zero():
    """Phase 6 refuses a successful episode whose count is not positive, so this producer refuses first."""

    from so101_demo.act.head_search_fine_correction_episodes import (
        CAL_FINE_EPISODE_NO_CORRECTION_NEEDED,
    )

    zero = dict(_locked_episode())
    zero["fine_corrections"] = 0
    zero["fine_corrections_rad"] = []

    with pytest.raises(CalibrationFineCorrectionRefused) as refused:
        episode_record(zero)

    assert refused.value.code == CAL_FINE_EPISODE_NO_CORRECTION_NEEDED
    assert CAL_FINE_EPISODE_NO_CORRECTION_NEEDED in REFUSAL_CODES


def test_the_scene_preparer_signature_accepts_every_key_the_producer_passes():
    """The real run found this boundary: the producer passed `scenario`, the preparer did not declare it.

    The request is built by one named function and the preparer's own signature is the contract, so a key
    added on one side without the other fails here instead of after a MuJoCo scene has been loaded.
    """

    import inspect

    request = module.scene_preparation_request(
        dataset_config_path="profile.yaml",
        generator_commit="0" * 40,
        seed=800000,
        cup_count=1,
        scenario="nominal",
        scene_path="scene.xml",
        split=HELD_OUT_SPLIT,
    )

    parameters = inspect.signature(module.prepare_episode_scene).parameters
    assert set(request) <= set(parameters), sorted(set(request) - set(parameters))
    assert parameters["seed"].kind is inspect.Parameter.KEYWORD_ONLY
    assert request["cup_count"] == 1
    assert request["split"] == HELD_OUT_SPLIT


def test_the_episode_records_the_cup_the_preparation_left_and_how_far_the_loop_moved_it():
    """A preparation that is not contact-free moves the cup; the episode has to say so."""

    plant = FakePlant(cup_yaw_rad=-0.0588)
    plant.prepared_cup_position_m = [0.063, -0.270, 0.165]
    plant.cup_position_m = [0.157, -0.358, 0.168]
    result = episode(plant=plant)

    assert result["cup_prepared_m"] == [0.063, -0.270, 0.165]
    assert result["cup_position_m"] == [0.157, -0.358, 0.168]
    assert result["cup_drift_m"] == pytest.approx(
        math.dist([0.063, -0.270, 0.165], [0.157, -0.358, 0.168])
    )
    assert result["cup_drift_m"] > 0.1


def test_an_episode_whose_plant_reports_no_cup_position_records_no_drift():
    result = episode(plant=FakePlant(cup_yaw_rad=-0.0588))

    assert result["cup_prepared_m"] is None
    assert result["cup_drift_m"] is None
