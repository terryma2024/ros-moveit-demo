"""HS-302: the closed-loop deadband lock trials and the `deadband_candidates` document.

Every case here runs against an injected plant and an injected detector, so the closed loop, the
lock-run rule, the reversal rule, every refusal and both documents are exercised without MuJoCo, a
detector, a GPU or ROS. The plant is built as the exact inverse of the controller's own correction
law, so a "correct" fixture converges in one correction and a perturbed one does not.
"""

from __future__ import annotations

import json
import math

import pytest
from so101_demo.act import head_search_deadband_measurement as module
from so101_demo.act.head_search_deadband_measurement import (
    CAL_DEADBAND_CUP_LOST,
    CAL_DEADBAND_OUT_OF_CORRIDOR,
    KIND,
    LOCK_FRAMES,
    RECORD_KEYS,
    REFUSAL_CODES,
    CalibrationDeadbandMeasurementRefused,
    build_deadband_candidates,
    candidate_record,
    declared_candidates,
    direction_reversals,
    lock_run,
    motion_corridor_rad,
    run_lock_trial,
    write_head_search_deadband_measurement,
)
from so101_demo.act.head_search_timing_measurement import (
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_SWEEP_UNSETTLED,
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


def _controller_config(**overrides) -> dict:
    config = {
        "attempt_id": "trial-attempt",
        "session_id": "trial-session",
        "search_start_rad": 0.0,
        "horizontal_fov_rad": 1.3121067481206794,
        "coarse_step_rad": 0.3,
        "search_timeout_s": 30.0,
        "max_age_s": 0.05,
        "max_skew_s": 0.02,
        "settle_velocity_rad_s": 0.05,
        "goal_tolerance_rad": 0.05,
        "center_deadband_px": 18.0,
        "vertical_bounds_px": list(VERTICAL_BOUNDS_PX),
        "min_area_px2": 64.0,
        "min_confidence": 0.4,
        "max_fine_corrections": 4,
        "max_fine_total_rad": 0.4,
        "frame_id": "head_camera_frame",
        "ray_origin_frame_id": "head_camera_frame",
        "required_search_domain_rad": [-0.3, 0.3],
        "lock_valid_neck_rad": [-3.0, 3.0],
    }
    config.update(overrides)
    return config


def _project(yaw_rad: float, cup_yaw_rad: float) -> float:
    """The pixel column a cup at `cup_yaw_rad` lands on while the neck holds `yaw_rad`.

    This is the exact inverse of the controller's own correction law
    (`correction = bearing(ray) - bearing(optical axis)`), so a plant built on it converges in one
    correction and the fixture is a correct system rather than a convenient one.
    """

    return PRINCIPAL_X_PX - GAIN_PX_PER_RAD * math.tan(cup_yaw_rad - yaw_rad)


class FakePlant:
    """A yaw-only plant: command a target, settle with a declared static error, render a frame."""

    def __init__(
        self,
        *,
        cup_yaw_rad: float,
        yaw_rad: float = 0.0,
        static_error_rad: float = 0.0,
        settle: bool = True,
        reached: bool = True,
        control_period_s: float = CONTROL_STEPS * TIMESTEP_S,
    ) -> None:
        self.cup_yaw_rad = float(cup_yaw_rad)
        self.yaw_rad = float(yaw_rad)
        self.static_error_rad = float(static_error_rad)
        self.settle = settle
        self.reached = reached
        self.control_period_s = control_period_s
        self.simulation_timestep_s = TIMESTEP_S
        self.time_s = 0.0
        self.frames_rendered = 0
        self.stops: list[dict] = []
        self.commands: list[float] = []

    def settle_to(self, target_rad: float) -> dict:
        self.commands.append(float(target_rad))
        start_sim, start_rad = self.time_s, self.yaw_rad
        self.yaw_rad = float(target_rad) + self.static_error_rad
        steps = CONTROL_STEPS
        self.time_s += steps * TIMESTEP_S
        stop = {
            "index": None,
            "kind": "plan",
            "target_rad": float(target_rad),
            "start_rad": start_rad,
            "sim_start_s": start_sim,
            "sim_end_s": self.time_s,
            "steps": steps,
            "settle_s": self.time_s - start_sim,
            "settled": self.settle,
            "reached": self.reached,
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
    """A detector that reads the plant's own yaw, with a declared per-frame pixel jitter."""

    def __init__(self, plant: FakePlant, *, jitter_px=(), cup_yaw_rad=None, fail_at=()) -> None:
        self.plant = plant
        self.jitter_px = tuple(jitter_px)
        self.cup_yaw_rad = plant.cup_yaw_rad if cup_yaw_rad is None else float(cup_yaw_rad)
        self.fail_at = tuple(fail_at)
        self.calls = 0

    def __call__(self, image, stamp_ns):
        index = self.calls
        self.calls += 1
        if index in self.fail_at:
            raise RuntimeError("DETECTOR_FAILED")
        jitter = self.jitter_px[index % len(self.jitter_px)] if self.jitter_px else 0.0
        column = _project(float(image["yaw_rad"]), self.cup_yaw_rad) + jitter
        if not 0.0 <= column - 50.0 or column + 50.0 > WIDTH_PX:
            return []
        return [
            {
                "xyxy": (column - 50.0, PRINCIPAL_Y_PX - 50.0, column + 50.0, PRINCIPAL_Y_PX + 50.0),
                "confidence": 0.9,
                "class_id": 0,
                "track_id": "cup",
            }
        ]


def _clock(start=1000.0, step=0.001):
    state = {"now": start}

    def clock() -> float:
        state["now"] += step
        return state["now"]

    return clock


def trial(*, deadband_px, plant, detector=None, corridor=(-0.3, 0.3), config=None, **kwargs):
    plant = plant
    detector = FakeDetector(plant) if detector is None else detector
    return run_lock_trial(
        controller_config=_controller_config() if config is None else config,
        deadband_px=deadband_px,
        plant=plant,
        detector=detector,
        corridor_rad=corridor,
        clock=_clock(),
        **kwargs,
    )


# --- the declared candidates ------------------------------------------------------------------


def test_declared_candidates_keeps_the_declaration_order_and_rejects_a_repeat():
    assert declared_candidates([18, 2, 4.5]) == [18.0, 2.0, 4.5]

    with pytest.raises(ValueError, match="twice"):
        declared_candidates([4.0, 4.0])


def test_declared_candidates_refuses_an_empty_or_non_positive_declaration():
    with pytest.raises(ValueError, match="at least one"):
        declared_candidates([])
    with pytest.raises(ValueError, match="positive"):
        declared_candidates([0.0])
    with pytest.raises(ValueError, match="positive"):
        declared_candidates([-3.0])


# --- the lock run and the reversals -----------------------------------------------------------


def _frame(*, cx, cy, track="cup", sim_s=0.0, k_principal=PRINCIPAL_X_PX):
    return {
        "frame_sim_s": sim_s,
        "principal_x_px": k_principal,
        "centre_px": [cx, cy],
        "track_id": track,
    }


def test_lock_run_counts_only_consecutive_frames_inside_the_deadband():
    frames = [
        _frame(cx=340.0, cy=240.0),  # 20 px out
        _frame(cx=321.0, cy=240.0),  # in for 18.0
        _frame(cx=319.0, cy=240.0),
        _frame(cx=318.0, cy=240.0),
        _frame(cx=340.0, cy=240.0),  # out again
        _frame(cx=319.0, cy=240.0),
        _frame(cx=319.0, cy=240.0),
    ]

    assert lock_run(frames, deadband_px=18.0, vertical_bounds_px=VERTICAL_BOUNDS_PX) == 3


def test_lock_run_breaks_on_a_missing_detection_a_track_change_and_a_vertical_miss():
    inside = _frame(cx=319.0, cy=240.0)
    missing = {"frame_sim_s": 1.0, "principal_x_px": PRINCIPAL_X_PX, "centre_px": None, "track_id": None}
    assert (
        lock_run(
            [inside, inside, missing, inside, inside],
            deadband_px=18.0,
            vertical_bounds_px=VERTICAL_BOUNDS_PX,
        )
        == 2
    )
    assert (
        lock_run(
            [inside, inside, _frame(cx=319.0, cy=240.0, track="other"), inside, inside],
            deadband_px=18.0,
            vertical_bounds_px=VERTICAL_BOUNDS_PX,
        )
        == 2
    )
    assert (
        lock_run(
            [inside, _frame(cx=319.0, cy=400.0), inside, inside, inside],
            deadband_px=18.0,
            vertical_bounds_px=VERTICAL_BOUNDS_PX,
        )
        == 3
    )


def test_lock_run_of_no_frame_at_all_is_zero_and_never_a_lock():
    assert lock_run([], deadband_px=18.0, vertical_bounds_px=VERTICAL_BOUNDS_PX) == 0
    assert LOCK_FRAMES == 3


def test_direction_reversals_counts_the_times_the_neck_was_sent_back_the_other_way():
    assert direction_reversals([-0.06, -0.001]) == 0
    assert direction_reversals([-0.06, 0.004, -0.002]) == 2
    assert direction_reversals([]) == 0
    assert direction_reversals([0.0, -0.06, 0.0]) == 0


# --- the closed loop --------------------------------------------------------------------------


def test_a_correct_loop_converges_in_one_correction_and_locks_without_reversing():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    result = trial(deadband_px=18.0, plant=plant)

    assert result["terminal_status"] == "TARGET_LOCKED"
    assert result["corrections_rad"] == pytest.approx([-0.0588], abs=1e-9)
    assert result["direction_reversals"] == 0
    assert result["longest_locked_run_frames"] >= LOCK_FRAMES
    assert len(result["frames"]) >= LOCK_FRAMES
    # the loop really rendered a frame per iteration and commanded the plant at least twice
    assert plant.frames_rendered == len(result["frames"])
    assert plant.commands[0] == 0.0
    assert plant.commands[1] == pytest.approx(-0.0588, abs=1e-9)


def test_a_hunting_loop_reverses_and_never_locks_three_consecutive_frames():
    # the detector alternates either side of the centre by more than the declared deadband, so the
    # controller keeps correcting, the target keeps flipping and no run of three can survive
    plant = FakePlant(cup_yaw_rad=-0.0588)
    detector = FakeDetector(plant, jitter_px=(9.0, -9.0))
    result = trial(deadband_px=2.0, plant=plant, detector=detector)

    assert result["direction_reversals"] >= 1
    assert result["longest_locked_run_frames"] < LOCK_FRAMES


def test_the_loop_refuses_when_the_detector_never_sees_the_cup():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    detector = FakeDetector(plant, cup_yaw_rad=1.5)  # far outside the field of view

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        trial(deadband_px=18.0, plant=plant, detector=detector)
    assert refusal.value.code == CAL_DEADBAND_CUP_LOST


def test_the_loop_refuses_when_the_detector_fails_rather_than_a_measurement():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    detector = FakeDetector(plant, fail_at=(1,))

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        trial(deadband_px=18.0, plant=plant, detector=detector)
    assert refusal.value.code == CAL_DEADBAND_CUP_LOST
    assert "DETECTOR_FAILED" in refusal.value.detail


def test_the_loop_refuses_a_command_that_would_leave_the_declared_corridor():
    plant = FakePlant(cup_yaw_rad=-0.0588)

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        trial(deadband_px=18.0, plant=plant, corridor=(-0.02, 0.02))
    assert refusal.value.code == CAL_DEADBAND_OUT_OF_CORRIDOR
    assert "[-0.02, 0.02]" in refusal.value.detail


def test_the_loop_refuses_a_start_outside_the_corridor_before_it_commands_anything():
    plant = FakePlant(cup_yaw_rad=-0.0588)

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        trial(deadband_px=18.0, plant=plant, corridor=(0.5, 1.0))
    assert refusal.value.code == CAL_DEADBAND_OUT_OF_CORRIDOR
    assert plant.commands == []


def test_the_loop_refuses_a_stop_that_is_reached_but_never_settled():
    plant = FakePlant(cup_yaw_rad=-0.0588, settle=False)

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        trial(deadband_px=18.0, plant=plant)
    assert refusal.value.code == CAL_TIMING_STOP_UNSETTLED


def test_the_loop_refuses_a_stop_that_was_never_reached():
    plant = FakePlant(cup_yaw_rad=-0.0588, reached=False, settle=False)

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        trial(deadband_px=18.0, plant=plant)
    assert refusal.value.code == CAL_TIMING_SWEEP_UNSETTLED


def test_the_loop_refuses_a_settle_time_that_is_not_the_simulation_clocks():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    original = plant.settle_to

    def wall_clock_settle(target_rad):
        stop = original(target_rad)
        stop["settle_s"] = stop["settle_s"] + 1e-6
        return stop

    plant.settle_to = wall_clock_settle

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        trial(deadband_px=18.0, plant=plant)
    assert refusal.value.code == CAL_TIMING_TIME_BASE_UNVERIFIED


def test_the_loop_refuses_when_it_never_reaches_a_verdict_inside_its_frame_budget():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    detector = FakeDetector(plant, jitter_px=(9.0, -9.0))

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        trial(deadband_px=2.0, plant=plant, detector=detector, max_frames=2)
    assert refusal.value.code == CAL_TIMING_SWEEP_UNSETTLED
    assert "2" in refusal.value.detail


# --- the candidate record and the corridor ------------------------------------------------------


def test_candidate_record_is_the_worst_case_over_the_declared_anchors():
    record = candidate_record(
        deadband_px=4.0,
        trials=[
            {"anchor": "left", "longest_locked_run_frames": 7, "direction_reversals": 0},
            {"anchor": "default", "longest_locked_run_frames": 3, "direction_reversals": 2},
        ],
    )

    assert tuple(record) == RECORD_KEYS
    assert record == {
        "center_deadband_px": 4.0,
        "longest_locked_run_frames": 3,
        "direction_reversals": 2,
    }


def test_candidate_record_needs_at_least_one_trial():
    with pytest.raises(ValueError, match="at least one"):
        candidate_record(deadband_px=4.0, trials=[])


def test_motion_corridor_is_the_intersection_of_the_required_domain_and_the_safe_interval():
    seal = {
        "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
        "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
    }

    assert motion_corridor_rad(geometry_seal=seal) == (
        -0.17559216195018026,
        0.08047101126546086,
    )
    assert motion_corridor_rad(
        geometry_seal={"required_search_domain_rad": [-1.0, 1.0], "lock_valid_neck_rad": [-0.5, 2.0]}
    ) == (-0.5, 1.0)


def test_motion_corridor_refuses_a_disjoint_or_unsealed_declaration():
    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        motion_corridor_rad(
            geometry_seal={"required_search_domain_rad": [-1.0, -0.5], "lock_valid_neck_rad": [0.0, 2.0]}
        )
    assert refusal.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as missing:
        motion_corridor_rad(geometry_seal={"lock_valid_neck_rad": [0.0, 2.0]})
    assert missing.value.code == CAL_TIMING_EVIDENCE_MISSING


# --- the document -------------------------------------------------------------------------------


def _trials_for_document():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    locking = trial(deadband_px=18.0, plant=plant)
    hunting_plant = FakePlant(cup_yaw_rad=-0.0588)
    hunting = trial(
        deadband_px=2.0,
        plant=hunting_plant,
        detector=FakeDetector(hunting_plant, jitter_px=(9.0, -9.0)),
    )
    return [locking, hunting]


def _document(tmp_path, *, candidates=(18.0, 2.0)):
    trials = _trials_for_document()
    seal = tmp_path / "seal.json"
    seal.write_text("{}\n", encoding="utf-8")
    weights = tmp_path / "C.pt"
    weights.write_bytes(b"weights")
    return build_deadband_candidates(
        path=tmp_path / "deadband-candidates.json",
        command="ros2 run so101_demo_py so101_head_search_calibration measure-deadband-candidates",
        trials=trials,
        candidates_px=list(candidates),
        control={
            "control_period_s": 0.002,
            "source_path": "/sealed/ros2_controllers.yaml",
            "source_sha256": "a" * 64,
            "key": "controller_manager.ros__parameters.update_rate",
            "update_rate_hz": 500.0,
            "steps_per_period": 1,
            "declared_by": "the sealed controller configuration",
        },
        controller_config=_controller_config(),
        scene_path=tmp_path / "head_search_scene.xml",
        scene_sha256="b" * 64,
        geometry_seal_path=seal,
        geometry_seal_sha256="c" * 64,
        production_search_config_path=tmp_path / "head_search_v2.json",
        production_search_config_sha256="d" * 64,
        frozen_candidate_path=tmp_path / "frozen-c.json",
        frozen_candidate_sha256="e" * 64,
        weights_path=weights,
        weights_sha256="f" * 64,
        detector_operating_point={"min_confidence": 0.25, "iou": 0.5},
        corridor_rad=(-0.17559216195018026, 0.08047101126546086),
        anchors=["left"],
        runtime_identity_document={"python_executable": "/usr/bin/python3", "cuda_available": True},
    )


def test_the_document_carries_the_records_phase_six_reads(tmp_path):
    document = _document(tmp_path)

    assert document["kind"] == KIND
    assert document["phase"] == "deadband_candidates"
    assert [tuple(record) for record in document["records"]] == [RECORD_KEYS] * 2
    assert document["records"][0]["center_deadband_px"] == 18.0
    assert document["records"][1]["center_deadband_px"] == 2.0
    assert document["motion_corridor_rad"] == [
        -0.17559216195018026,
        0.08047101126546086,
    ]
    assert document["ros_nodes_started"] is False
    assert document["hardware_motion_commanded"] is False
    assert document["mujoco_neck_commanded"] is True
    assert document["measured_here"] is True
    assert document["cuda_used"] is True
    assert document["weights"]["sha256"] == "f" * 64
    assert [anchor["anchor"] for anchor in document["anchors"]] == ["left"]


def test_the_document_digest_covers_every_field_but_itself(tmp_path):
    from so101_demo.perception_benchmark.contracts import canonical_sha256

    document = _document(tmp_path)

    assert document["sha256"] == canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    assert len(document["sha256"]) == 64


def test_the_document_declares_the_frame_cadence_the_trials_really_ran_at(tmp_path):
    """`frame_rate_hz` names the contract; the achieved interval is the settle time plus its remainder."""

    document = _document(tmp_path)

    assert document["frame_cadence"] == module.FRAME_CADENCE
    assert "settle" in document["frame_cadence"]
    intervals = [
        frame["frame_interval_sim_s"] for trial in document["trials"] for frame in trial["frames"]
    ]
    assert intervals[0] is None
    assert all(value is None or value > 0.0 for value in intervals)
    assert any(value is not None for value in intervals)


def test_the_document_refuses_a_trial_whose_deadband_was_not_declared(tmp_path):
    trials = _trials_for_document()

    with pytest.raises(ValueError, match="candidate"):
        build_deadband_candidates(
            path=tmp_path / "deadband-candidates.json",
            command="c",
            trials=trials,
            candidates_px=[18.0],
            control={"control_period_s": 0.002},
            controller_config=_controller_config(),
            scene_path=tmp_path / "scene.xml",
            scene_sha256="b" * 64,
            geometry_seal_path=tmp_path / "seal.json",
            geometry_seal_sha256="c" * 64,
            production_search_config_path=tmp_path / "p.json",
            production_search_config_sha256="d" * 64,
            frozen_candidate_path=tmp_path / "f.json",
            frozen_candidate_sha256="e" * 64,
            weights_path=None,
            weights_sha256=None,
            detector_operating_point={},
            corridor_rad=(0.0, 1.0),
            anchors=["left"],
            runtime_identity_document={},
        )


def test_the_producer_declares_the_refusal_vocabulary_it_can_raise():
    assert CAL_DEADBAND_CUP_LOST in REFUSAL_CODES
    assert CAL_DEADBAND_OUT_OF_CORRIDOR in REFUSAL_CODES
    for code in (
        CAL_TIMING_EVIDENCE_MISSING,
        CAL_TIMING_EVIDENCE_CONTRADICTORY,
        CAL_TIMING_STOP_UNSETTLED,
        CAL_TIMING_SWEEP_UNSETTLED,
        CAL_TIMING_TIME_BASE_UNVERIFIED,
    ):
        assert code in REFUSAL_CODES


# --- the producer -------------------------------------------------------------------------------


def _sealed_inputs(tmp_path):
    seal = {
        "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
        "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
        "horizontal_fov_rad": 1.3121067481206794,
        "image_width": WIDTH_PX,
        "image_height": HEIGHT_PX,
        "camera_name": "head_camera",
        "in_frame_matrix": {"left": {"neck_start_rad": 0.0}},
        "workspace_matrix": {
            "key_samples": [
                {"anchor": "left", "kind": "anchor", "point_m": [-0.08, -0.28, 0.165]}
            ]
        },
        "source_digests": {"scene_sha256": "a" * 64},
    }
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
            "vertical_bounds_px": [110.0, 370.0],
            "min_area_px2": 64.0,
            "min_confidence": 0.4,
            "max_fine_corrections": 4,
            "max_fine_total_rad": 0.4,
            "horizontal_fov_rad": 1.3121067481206794,
            "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
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
    seal_path = tmp_path / "seal.json"
    seal_path.write_text(json.dumps(seal), encoding="utf-8")
    production_path = tmp_path / "head_search_v2.json"
    production_path.write_text(json.dumps(production), encoding="utf-8")
    frozen_path = tmp_path / "frozen-c.json"
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    controllers_path = tmp_path / "ros2_controllers.yaml"
    controllers_path.write_text(
        "controller_manager:\n  ros__parameters:\n    update_rate: 500\n", encoding="utf-8"
    )
    return scene, seal_path, production_path, frozen_path, controllers_path, weights_path


def _producer(tmp_path, *, candidates=(18.0, 2.0), plant_factory=None, detector_factory=None, **kwargs):
    scene, seal, production, frozen, controllers, weights = _sealed_inputs(tmp_path)
    seal_document = json.loads(seal.read_text(encoding="utf-8"))
    seal_document["source_digests"]["scene_sha256"] = module._digest(scene)
    seal.write_text(json.dumps(seal_document), encoding="utf-8")
    production_document = json.loads(production.read_text(encoding="utf-8"))
    production_document["weight_sha256"] = module._digest(weights)
    production.write_text(json.dumps(production_document), encoding="utf-8")

    def default_plant(request):
        return FakePlant(cup_yaw_rad=-0.0588)

    return write_head_search_deadband_measurement(
        scene_path=scene,
        geometry_seal_path=seal,
        production_search_config_path=production,
        controller_config_path=controllers,
        frozen_candidate_path=frozen,
        weights_path=weights,
        output_dir=tmp_path / "out",
        candidates=list(candidates),
        device="cpu",
        plant=plant_factory or default_plant,
        detector_factory=detector_factory or (lambda plant, request: FakeDetector(plant)),
        command="measure-deadband-candidates",
        **kwargs,
    )


def _patch_scene_declaration(monkeypatch, tmp_path):
    """The sealed scene is a stub here: the declaration reader is the MuJoCo module's own."""

    monkeypatch.setattr(
        module,
        "read_mujoco_timestep",
        lambda path: {"simulation_timestep_s": TIMESTEP_S, "scene_sha256": module._digest(path)},
    )
    monkeypatch.setattr(module, "_cuda_available", lambda: True)


def test_the_producer_writes_the_document_the_receipt_and_every_trial(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch, tmp_path)
    result = _producer(tmp_path)

    document = json.loads((tmp_path / "out" / module.ARTIFACT).read_text(encoding="utf-8"))
    receipt = json.loads((tmp_path / "out" / module.RECEIPT_ARTIFACT).read_text(encoding="utf-8"))

    assert document["sha256"] == result["document"]["sha256"]
    assert document["records"] == result["document"]["records"]
    assert [record["center_deadband_px"] for record in document["records"]] == [18.0, 2.0]
    assert len(document["trials"]) == 2
    assert all(trial["anchor"] == "left" for trial in document["trials"])
    assert receipt["status"] == "SUCCEEDED"
    assert receipt["document_path"] == str(tmp_path / "out" / module.ARTIFACT)
    assert receipt["document_sha256"] == document["sha256"]
    assert receipt["candidate_count"] == 2
    assert receipt["anchor_names"] == ["left"]
    assert receipt["detector_operating_point"] == {"min_confidence": 0.25, "iou": 0.5}
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False


def test_the_producer_reads_the_detector_operating_point_from_the_frozen_candidate(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch, tmp_path)
    result = _producer(tmp_path)

    assert result["document"]["detector_operating_point"] == {
        "min_confidence": 0.25,
        "iou": 0.5,
    }
    assert result["document"]["controller_thresholds"]["min_confidence"] == 0.4
    assert result["document"]["controller_thresholds"]["vertical_bounds_px"] == [110.0, 370.0]


def test_the_producer_refuses_weights_the_sealed_configuration_does_not_declare(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch, tmp_path)
    scene, seal, production, frozen, controllers, weights = _sealed_inputs(tmp_path)
    # the scene and the frozen candidate are pinned correctly, so the only thing left to disagree is
    # the weight the sealed production configuration declares
    seal_document = json.loads(seal.read_text(encoding="utf-8"))
    seal_document["source_digests"]["scene_sha256"] = module._digest(scene)
    seal.write_text(json.dumps(seal_document), encoding="utf-8")

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        write_head_search_deadband_measurement(
            scene_path=scene,
            geometry_seal_path=seal,
            production_search_config_path=production,
            controller_config_path=controllers,
            frozen_candidate_path=frozen,
            weights_path=weights,
            output_dir=tmp_path / "out",
            candidates=[18.0],
            device="cpu",
        )
    assert refusal.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_the_producer_refuses_a_scene_the_sealed_geometry_does_not_pin(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch, tmp_path)
    scene, seal, production, frozen, controllers, weights = _sealed_inputs(tmp_path)
    production_document = json.loads(production.read_text(encoding="utf-8"))
    production_document["weight_sha256"] = module._digest(weights)
    production.write_text(json.dumps(production_document), encoding="utf-8")

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        write_head_search_deadband_measurement(
            scene_path=scene,
            geometry_seal_path=seal,
            production_search_config_path=production,
            controller_config_path=controllers,
            frozen_candidate_path=frozen,
            weights_path=weights,
            output_dir=tmp_path / "out",
            candidates=[18.0],
            device="cpu",
        )
    assert refusal.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY
    assert "scene" in refusal.value.detail


def test_the_producer_refuses_an_output_directory_that_already_exists(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch, tmp_path)
    (tmp_path / "out").mkdir()

    with pytest.raises(FileExistsError):
        _producer(tmp_path)


def test_the_producer_refuses_an_anchor_the_seal_does_not_declare(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch, tmp_path)

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        _producer(tmp_path, anchors=["nose"])
    assert refusal.value.code == CAL_TIMING_EVIDENCE_MISSING
    assert "nose" in refusal.value.detail


def test_the_producer_refuses_an_anchor_whose_start_is_outside_the_motion_corridor(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch, tmp_path)
    scene, seal, production, frozen, controllers, weights = _sealed_inputs(tmp_path)
    seal_document = json.loads(seal.read_text(encoding="utf-8"))
    seal_document["source_digests"]["scene_sha256"] = module._digest(scene)
    seal_document["in_frame_matrix"]["left"]["neck_start_rad"] = 1.5
    seal.write_text(json.dumps(seal_document), encoding="utf-8")
    production_document = json.loads(production.read_text(encoding="utf-8"))
    production_document["weight_sha256"] = module._digest(weights)
    production.write_text(json.dumps(production_document), encoding="utf-8")

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        write_head_search_deadband_measurement(
            scene_path=scene,
            geometry_seal_path=seal,
            production_search_config_path=production,
            controller_config_path=controllers,
            frozen_candidate_path=frozen,
            weights_path=weights,
            output_dir=tmp_path / "out",
            candidates=[18.0],
            device="cpu",
        )
    assert refusal.value.code == CAL_DEADBAND_OUT_OF_CORRIDOR
    assert not (tmp_path / "out").exists() or not list((tmp_path / "out").iterdir())


def test_the_producer_refuses_a_declared_cuda_device_without_one(tmp_path, monkeypatch):
    monkeypatch.setattr(
        module,
        "read_mujoco_timestep",
        lambda path: {"simulation_timestep_s": TIMESTEP_S, "scene_sha256": module._digest(path)},
    )
    monkeypatch.setattr(module, "_cuda_available", lambda: False)
    scene, seal, production, frozen, controllers, weights = _sealed_inputs(tmp_path)
    seal_document = json.loads(seal.read_text(encoding="utf-8"))
    seal_document["source_digests"]["scene_sha256"] = module._digest(scene)
    seal.write_text(json.dumps(seal_document), encoding="utf-8")
    production_document = json.loads(production.read_text(encoding="utf-8"))
    production_document["weight_sha256"] = module._digest(weights)
    production.write_text(json.dumps(production_document), encoding="utf-8")

    with pytest.raises(CalibrationDeadbandMeasurementRefused) as refusal:
        write_head_search_deadband_measurement(
            scene_path=scene,
            geometry_seal_path=seal,
            production_search_config_path=production,
            controller_config_path=controllers,
            frozen_candidate_path=frozen,
            weights_path=weights,
            output_dir=tmp_path / "out",
            candidates=[18.0],
            device="cuda",
        )
    assert refusal.value.code == "CAL_TIMING_DEVICE_UNAVAILABLE"


def test_the_producer_needs_at_least_one_declared_candidate(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="at least one"):
        _producer(tmp_path, candidates=())


def test_the_lock_rule_is_declared_with_its_reversal_definition(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch, tmp_path)
    document = _producer(tmp_path)["document"]

    assert document["lock_frames_required"] == LOCK_FRAMES
    assert "three consecutive frames" in document["lock_rule"]
    assert "correction" in document["reversal_definition"]
    assert document["reversal_definition"] == module.REVERSAL_DEFINITION
    assert document["frame_rate_hz"] == module.FRAME_RATE_HZ
