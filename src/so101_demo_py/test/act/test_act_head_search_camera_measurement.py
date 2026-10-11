"""HS-303: the `camera_measurements` document - the measured centre jitter and the declared margin.

Every case here runs against an injected plant, an injected detector and synthetic declaration
artefacts, so the pose hold, the spread computation, the angular conversion, every refusal and both
documents are exercised without MuJoCo, a detector, a GPU or ROS.

The two fields phase 6 reads out of this document have different provenance and the tests pin that:
`centre_jitter_rad` is measured here (the spread of the detected cup centre over repeated frames at a
fixed, settled pose, through the sealed angular resolution), while `safety_margin_px` is a declaration
that no retained artefact carries - so the producer records `null` and a refusal rather than defaulting
it, and reads and cites a declaring artefact when one is passed.
"""

from __future__ import annotations

import hashlib
import json
import math

import pytest
from so101_demo.act.head_search_camera_measurement import declarations as module_declarations
from so101_demo.act.head_search_camera_measurement import frames as module_frames
from so101_demo.act.head_search_camera_measurement import writer as module_writer
from so101_demo.act.head_search_camera_measurement.declarations import (
    CAL_CAMERA_CUP_LOST,
    CAL_CAMERA_POSE_OUT_OF_CORRIDOR,
    CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY,
    CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE,
    CAL_CAMERA_SAFETY_MARGIN_UNDECLARED,
    CalibrationCameraMeasurementRefused,
    declared_camera_geometry,
    DEFAULT_FRAMES_PER_POSE,
    KIND,
    MIN_FRAMES_PER_POSE,
    rad_per_px,
    read_declared_safety_margin,
    REFUSAL_CODES,
    spread,
    undeclared_safety_margin,
)
from so101_demo.act.head_search_camera_measurement.frames import (
    build_camera_measurements,
    measure_anchor_frames,
)
from so101_demo.act.head_search_camera_measurement.writer import (
    write_head_search_camera_measurement,
)
from so101_demo.act.head_search_search_params import (
    CAL_VERTICAL_BOUNDS_UNPROJECTED,
    CalibrationSearchParamsRefused,
    compute_center_deadband_px,
    compute_vertical_bounds_px,
)
from so101_demo.act.head_search_timing_measurement.contracts import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    FRAME_PERIOD_S,
)
from so101_demo.act.head_search_timing_measurement.control import planned_stops

WIDTH_PX = 640
HEIGHT_PX = 480
FOCAL_PX = 415.69219381653056
PRINCIPAL_X_PX = WIDTH_PX / 2.0
PRINCIPAL_Y_PX = HEIGHT_PX / 2.0
TIMESTEP_S = 0.002
CONTROL_STEPS = 5
HORIZONTAL_FOV_RAD = 1.3121067481206794
RAD_PER_PX = HORIZONTAL_FOV_RAD / WIDTH_PX
#: the sealed head camera's optical axes in the base frame (x=image right, y=image down, z=forward)
ROTATION_OPTICAL_TO_BASE = (
    (-1.0, 0.0, 0.0),
    (0.0, 0.6, -0.8),
    (0.0, -0.8, -0.6),
)
#: the yaw-to-pixel gain of that camera's forward axis in base, px per rad near the optical axis
GAIN_PX_PER_RAD = 0.8 * FOCAL_PX
VERTICAL_BOUNDS_PX = (110.0, 370.0)
CORRIDOR_RAD = (-0.3, 0.3)


def _controller_config(**overrides) -> dict:
    config = {
        "attempt_id": "camera-attempt",
        "session_id": "camera-session",
        "search_start_rad": 0.0,
        "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
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
        "required_search_domain_rad": list(CORRIDOR_RAD),
        "lock_valid_neck_rad": [-3.0, 3.0],
    }
    config.update(overrides)
    return config


def _project(yaw_rad: float, cup_yaw_rad: float) -> float:
    """The pixel column a cup at `cup_yaw_rad` lands on while the neck holds `yaw_rad`."""

    return PRINCIPAL_X_PX - GAIN_PX_PER_RAD * math.tan(cup_yaw_rad - yaw_rad)


class FakePlant:
    """A yaw-only plant: command a target, settle, render a frame, and hold it between frames."""

    def __init__(
        self,
        *,
        cup_yaw_rad: float,
        yaw_rad: float = 0.0,
        static_error_rad: float = 0.0,
        settle: bool = True,
        reached: bool = True,
        time_base: str = "simulation",
    ) -> None:
        self.cup_yaw_rad = float(cup_yaw_rad)
        self.yaw_rad = float(yaw_rad)
        self.static_error_rad = float(static_error_rad)
        self.settle = settle
        self.reached = reached
        self.time_base = time_base
        self.simulation_timestep_s = TIMESTEP_S
        self.time_s = 0.0
        self.frames_rendered = 0
        self.stops: list[dict] = []
        self.commands: list[float] = []
        self.closed = False
        #: a deterministic per-frame image, so its digest is a real one and changes with the frame
        self.image_counter = 0

    def settle_to(self, target_rad: float) -> dict:
        self.commands.append(float(target_rad))
        start_sim, start_rad = self.time_s, self.yaw_rad
        self.yaw_rad = float(target_rad) + self.static_error_rad
        steps = CONTROL_STEPS
        self.time_s += steps * TIMESTEP_S
        stop = {
            "index": len(self.stops),
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
            "time_base": self.time_base,
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
        self.image_counter += 1
        return {
            "frame": self.frames_rendered,
            "yaw_rad": self.yaw_rad,
            "bytes": (self.image_counter % 4).to_bytes(1, "little") * 8,
        }

    def optical_geometry(self) -> dict:
        return {
            "k": (FOCAL_PX, 0.0, PRINCIPAL_X_PX, 0.0, FOCAL_PX, PRINCIPAL_Y_PX, 0.0, 0.0, 1.0),
            "distortion": (0.0, 0.0, 0.0, 0.0, 0.0),
            "rotation_optical_to_base": ROTATION_OPTICAL_TO_BASE,
        }

    def close(self) -> None:
        self.closed = True


class FakeDetector:
    """A detector that reads the plant's own yaw and applies a declared per-frame pixel offset."""

    def __init__(
        self, plant: FakePlant, *, offsets_px=(), row_px=0.0, boxes_per_frame=1, fail_at=()
    ) -> None:
        self.plant = plant
        self.offsets_px = tuple(offsets_px)
        self.row_px = float(row_px)
        self.boxes_per_frame = int(boxes_per_frame)
        self.fail_at = tuple(fail_at)
        self.calls = 0

    def __call__(self, image, stamp_ns):
        index = self.calls
        self.calls += 1
        if index in self.fail_at:
            raise RuntimeError("DETECTOR_FAILED")
        if self.boxes_per_frame == 0:
            return []
        offset = self.offsets_px[index % len(self.offsets_px)] if self.offsets_px else 0.0
        column = _project(float(image["yaw_rad"]), self.plant.cup_yaw_rad) + offset
        row = PRINCIPAL_Y_PX + self.row_px
        return [
            {
                "xyxy": (
                    column - 50.0 + 10.0 * box,
                    row - 50.0,
                    column + 50.0 + 10.0 * box,
                    row + 50.0,
                ),
                "confidence": 0.9,
                "class_id": 0,
                "track_id": f"cup-{box}",
            }
            for box in range(self.boxes_per_frame)
        ]


def _clock(start=1000.0, step=0.001):
    state = {"now": start}

    def clock() -> float:
        state["now"] += step
        return state["now"]

    return clock


def _poses(config=None):
    config = _controller_config() if config is None else config
    values = [float(config["search_start_rad"]), *(float(v) for v in planned_stops(config))]
    unique: list[float] = []
    for value in values:
        if value not in unique:
            unique.append(value)
    return [
        {"pose_rad": value, "pose_kind": "anchor" if index == 0 else "plan"}
        for index, value in enumerate(unique)
    ]


def measure(
    *,
    plant=None,
    detector=None,
    poses=None,
    frames_per_pose=4,
    corridor=CORRIDOR_RAD,
    config=None,
    **kwargs,
):
    config = _controller_config() if config is None else config
    plant = FakePlant(cup_yaw_rad=-0.0588) if plant is None else plant
    detector = FakeDetector(plant) if detector is None else detector
    return measure_anchor_frames(
        anchor="left",
        plant=plant,
        detector=detector,
        poses=_poses(config) if poses is None else poses,
        frames_per_pose=frames_per_pose,
        corridor_rad=corridor,
        settle_consecutive_steps=CONTROL_STEPS,
        max_settle_s=5.0,
        clock=_clock(),
        **kwargs,
    )


# --- the angular resolution and the spread --------------------------------------------------------


def test_rad_per_px_is_the_sealed_angular_resolution():
    assert rad_per_px(horizontal_fov_rad=HORIZONTAL_FOV_RAD, image_width_px=WIDTH_PX) == (
        HORIZONTAL_FOV_RAD / WIDTH_PX
    )

    with pytest.raises(ValueError, match="field of view"):
        rad_per_px(horizontal_fov_rad=0.0, image_width_px=WIDTH_PX)

    with pytest.raises(ValueError, match="image width"):
        rad_per_px(horizontal_fov_rad=HORIZONTAL_FOV_RAD, image_width_px=0)


def test_spread_is_the_sample_standard_deviation_with_its_range():
    result = spread([319.5, 320.5, 320.0])

    assert result["count"] == 3
    assert result["mean"] == pytest.approx(320.0)
    assert result["std"] == pytest.approx(0.5)
    assert result["min"] == 319.5
    assert result["max"] == 320.5
    assert result["peak_to_peak"] == pytest.approx(1.0)
    assert result["max_abs_deviation"] == pytest.approx(0.5)
    assert result["degrees_of_freedom"] == 2


def test_spread_of_a_perfectly_repeated_centre_is_a_measured_zero():
    result = spread([340.959, 340.959, 340.959])

    assert result["std"] == 0.0
    assert result["peak_to_peak"] == 0.0
    assert result["count"] == 3


def test_spread_needs_at_least_two_samples_and_only_finite_ones():
    with pytest.raises(ValueError, match="two samples"):
        spread([320.0])

    with pytest.raises(ValueError, match="finite"):
        spread([320.0, float("nan")])

    with pytest.raises(ValueError, match="finite"):
        spread([320.0, True])


# --- the declared safety margin -------------------------------------------------------------------


def test_a_declared_safety_margin_is_read_with_its_declaring_path_and_digest(tmp_path):
    artefact = tmp_path / "camera-safety.json"
    artefact.write_text(json.dumps({"safety_margin_px": 12.5}), encoding="utf-8")

    declaration = read_declared_safety_margin(artefact)

    assert declaration["value"] == 12.5
    assert declaration["measured_here"] is False
    assert declaration["declared"] is True
    assert declaration["refusal"] is None
    assert declaration["declared_by"] == {
        "path": str(artefact),
        "sha256": hashlib.sha256(artefact.read_bytes()).hexdigest(),
        "key": "safety_margin_px",
    }


def test_a_declared_safety_margin_is_found_under_the_values_block(tmp_path):
    artefact = tmp_path / "head_search_runtime.json"
    artefact.write_text(json.dumps({"values": {"safety_margin_px": 8}}), encoding="utf-8")

    declaration = read_declared_safety_margin(artefact)

    assert declaration["value"] == 8.0
    assert declaration["declared_by"]["key"] == "values.safety_margin_px"


def test_a_yaml_declaration_is_read_too(tmp_path):
    artefact = tmp_path / "camera.yaml"
    artefact.write_text("camera:\n  safety_margin_px: 4.0\n", encoding="utf-8")

    declaration = read_declared_safety_margin(artefact)

    assert declaration["value"] == 4.0
    assert declaration["declared_by"]["key"] == "camera.safety_margin_px"


def test_an_artefact_that_declares_no_safety_margin_is_refused(tmp_path):
    artefact = tmp_path / "geometry-seal.json"
    artefact.write_text(json.dumps({"horizontal_fov_rad": HORIZONTAL_FOV_RAD}), encoding="utf-8")

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        read_declared_safety_margin(artefact)

    assert refused.value.code == CAL_CAMERA_SAFETY_MARGIN_UNDECLARED
    assert str(artefact) in refused.value.detail


def test_a_negative_or_non_finite_declared_safety_margin_is_refused(tmp_path):
    for bad in (-1.0, float("inf"), "ten"):
        artefact = tmp_path / f"bad-{bad}.json"
        artefact.write_text(json.dumps({"safety_margin_px": bad}), encoding="utf-8")

        with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
            read_declared_safety_margin(artefact)

        assert refused.value.code == CAL_CAMERA_SAFETY_MARGIN_UNDECLARED


def test_an_artefact_that_is_not_a_mapping_is_a_caller_error(tmp_path):
    artefact = tmp_path / "list.json"
    artefact.write_text(json.dumps([1, 2, 3]), encoding="utf-8")

    with pytest.raises(ValueError, match="mapping"):
        read_declared_safety_margin(artefact)


def test_an_undeclared_safety_margin_is_recorded_as_null_never_defaulted():
    record = undeclared_safety_margin()

    assert record["value"] is None
    assert record["declared"] is False
    assert record["measured_here"] is False
    assert record["declared_by"] is None
    assert record["refusal"] == CAL_CAMERA_SAFETY_MARGIN_UNDECLARED
    assert record["detail"]


def test_a_missing_declaration_file_is_a_caller_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_declared_safety_margin(tmp_path / "absent.json")


# --- HS-305: the declared image safety margin fraction (approved Proposal A) -----------------------


def _image_geometry() -> dict:
    """The sealed camera geometry phase 6 derives the shorter edge from: 640 x 480."""

    return declared_camera_geometry(
        geometry_seal={
            "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
            "image_width": WIDTH_PX,
            "image_height": HEIGHT_PX,
        },
        seal_path=None,
        seal_sha256="a" * 64,
    )


def _margin_profile(tmp_path, body: str):
    artefact = tmp_path / "head_camera_yolo_seg.yaml"
    artefact.write_text(body, encoding="utf-8")
    return artefact


def test_a_declared_fraction_is_derived_into_pixels_with_ceil_and_cited(tmp_path):
    """Proposal A: the production camera declaration states a fraction; the producer applies ceil."""

    artefact = _margin_profile(
        tmp_path,
        "camera_name: head_camera\n"
        "image_width: 640\n"
        "image_height: 480\n"
        "image_safety_margin_fraction: 0.25\n",
    )

    declaration = read_declared_safety_margin(artefact, image_geometry=_image_geometry())

    assert declaration["value"] == 120.0  # ceil(0.25 * min(640, 480))
    assert declaration["unit"] == "px"
    assert declaration["field"] == "safety_margin_px"
    assert declaration["declared"] is True
    assert declaration["measured_here"] is False
    assert declaration["refusal"] is None
    assert declaration["fraction"] == 0.25
    assert declaration["image_width_px"] == WIDTH_PX
    assert declaration["image_height_px"] == HEIGHT_PX
    assert declaration["shorter_edge_px"] == HEIGHT_PX
    declared_by = declaration["declared_by"]
    assert declared_by["path"] == str(artefact)
    assert declared_by["sha256"] == hashlib.sha256(artefact.read_bytes()).hexdigest()
    assert declared_by["key"] == "image_safety_margin_fraction"
    assert declared_by["fraction"] == 0.25
    assert declared_by["derivation"] == "ceil(0.25 * min(640.0, 480.0)) = 120 px"


def test_a_fraction_without_declared_dimensions_is_bound_to_the_sealed_geometry(tmp_path):
    artefact = _margin_profile(tmp_path, "image_safety_margin_fraction: 0.125\n")

    declaration = read_declared_safety_margin(artefact, image_geometry=_image_geometry())

    assert declaration["value"] == 60.0  # ceil(0.125 * 480)
    assert declaration["image_width_px"] == WIDTH_PX
    assert declaration["image_height_px"] == HEIGHT_PX
    assert declaration["declared_by"]["bound_to"] == "the sealed head camera geometry"


def test_a_fraction_whose_declared_dimensions_contradict_the_sealed_geometry_is_refused(tmp_path):
    artefact = _margin_profile(
        tmp_path,
        "image_width: 640\nimage_height: 481\nimage_safety_margin_fraction: 0.25\n",
    )

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        read_declared_safety_margin(artefact, image_geometry=_image_geometry())

    assert refused.value.code == CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY
    assert "481" in refused.value.detail


def test_a_fraction_outside_the_open_zero_to_a_half_range_is_refused(tmp_path):
    for bad in (0.0, -0.25, 0.5000001, 1.0, 12.0):
        artefact = tmp_path / f"out-of-range-{bad}.json"
        artefact.write_text(json.dumps({"image_safety_margin_fraction": bad}), encoding="utf-8")

        with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
            read_declared_safety_margin(artefact, image_geometry=_image_geometry())

        assert refused.value.code == CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE

    # the upper bound itself is inside the closed end: half the shorter edge, one edge's worth
    half = tmp_path / "exactly-half.json"
    half.write_text(json.dumps({"image_safety_margin_fraction": 0.5}), encoding="utf-8")
    assert read_declared_safety_margin(half, image_geometry=_image_geometry())["value"] == 240.0


def test_a_fraction_that_is_not_a_finite_number_is_undeclared(tmp_path):
    for bad in ("a quarter", None, float("inf")):
        artefact = tmp_path / "not-a-fraction.json"
        artefact.write_text(json.dumps({"image_safety_margin_fraction": bad}), encoding="utf-8")

        with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
            read_declared_safety_margin(artefact, image_geometry=_image_geometry())

        assert refused.value.code == CAL_CAMERA_SAFETY_MARGIN_UNDECLARED


def test_an_artefact_declaring_both_margin_forms_is_refused(tmp_path):
    artefact = tmp_path / "both-forms.json"
    artefact.write_text(
        json.dumps({"image_safety_margin_fraction": 0.25, "safety_margin_px": 110.0}),
        encoding="utf-8",
    )

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        read_declared_safety_margin(artefact, image_geometry=_image_geometry())

    assert refused.value.code == CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY


def test_a_fraction_declaration_without_the_sealed_geometry_is_a_caller_error(tmp_path):
    artefact = _margin_profile(tmp_path, "image_safety_margin_fraction: 0.25\n")

    with pytest.raises(ValueError, match="image geometry"):
        read_declared_safety_margin(artefact)


def test_the_pixel_form_is_still_read_when_the_geometry_is_not_offered(tmp_path):
    """The pre-existing pixel declaration keeps working, and its cited block keeps its exact shape."""

    artefact = tmp_path / "camera-safety.json"
    artefact.write_text(json.dumps({"safety_margin_px": 12.5}), encoding="utf-8")

    declaration = read_declared_safety_margin(artefact)

    assert declaration["value"] == 12.5
    assert declaration["declared_by"] == {
        "path": str(artefact),
        "sha256": hashlib.sha256(artefact.read_bytes()).hexdigest(),
        "key": "safety_margin_px",
    }


def test_the_two_fraction_refusals_are_registered_and_the_old_one_survives():
    assert CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE in REFUSAL_CODES
    assert CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY in REFUSAL_CODES
    assert CAL_CAMERA_SAFETY_MARGIN_UNDECLARED in REFUSAL_CODES


# --- HS-305: what phase 6 does with the derived margin ---------------------------------------------


def test_the_document_carries_the_derived_margin_and_no_refusal(tmp_path):
    artefact = _margin_profile(
        tmp_path,
        "image_width: 640\nimage_height: 480\nimage_safety_margin_fraction: 0.25\n",
    )
    margin = read_declared_safety_margin(artefact, image_geometry=_image_geometry())

    document = _document(tmp_path, safety_margin=margin)

    assert document["safety_margin_px"] == 120.0
    assert document["refusals"] == []
    assert document["safety_margin"]["declared_by"]["key"] == "image_safety_margin_fraction"
    assert (
        document["safety_margin"]["declared_by"]["sha256"]
        == hashlib.sha256(artefact.read_bytes()).hexdigest()
    )


def test_phase_six_intersects_the_projection_with_the_derived_margin(tmp_path):
    artefact = _margin_profile(
        tmp_path,
        "image_width: 640\nimage_height: 480\nimage_safety_margin_fraction: 0.25\n",
    )
    document = _document(
        tmp_path,
        safety_margin=read_declared_safety_margin(artefact, image_geometry=_image_geometry()),
    )
    projection = {
        "path": str(tmp_path / "workspace-projection.json"),
        "sha256": "c" * 64,
        "top_px": 96.0,
        "bottom_px": 470.0,
    }

    block = compute_vertical_bounds_px(camera=document, workspace_projection=projection)

    assert block["value"] == [120.0, 360.0]
    assert block["observed_distribution"]["image_safety_margin_px"] == 120.0


def test_phase_six_refuses_an_empty_intersection_under_the_derived_margin(tmp_path):
    artefact = _margin_profile(
        tmp_path,
        "image_width: 640\nimage_height: 480\nimage_safety_margin_fraction: 0.25\n",
    )
    document = _document(
        tmp_path,
        safety_margin=read_declared_safety_margin(artefact, image_geometry=_image_geometry()),
    )
    projection = {
        "path": str(tmp_path / "workspace-projection.json"),
        "sha256": "c" * 64,
        "top_px": 0.0,
        "bottom_px": 100.0,
    }

    with pytest.raises(CalibrationSearchParamsRefused) as refused:
        compute_vertical_bounds_px(camera=document, workspace_projection=projection)

    assert refused.value.code == CAL_VERTICAL_BOUNDS_UNPROJECTED
    assert "image safety" in refused.value.detail


# --- the declared geometry ------------------------------------------------------------------------


def test_declared_camera_geometry_renames_the_seals_own_keys_and_cites_it(tmp_path):
    seal_path = tmp_path / "head-camera-geometry.json"
    seal_path.write_text(json.dumps({"horizontal_fov_rad": HORIZONTAL_FOV_RAD}), encoding="utf-8")
    seal = {
        "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
        "image_width": WIDTH_PX,
        "image_height": HEIGHT_PX,
    }

    declaration = declared_camera_geometry(
        geometry_seal=seal, seal_path=seal_path, seal_sha256=module_declarations._digest(seal_path)
    )

    assert declaration["horizontal_fov_rad"] == HORIZONTAL_FOV_RAD
    assert declaration["image_width_px"] == WIDTH_PX
    assert declaration["image_height_px"] == HEIGHT_PX
    assert declaration["measured_here"] is False
    assert declaration["declared_by"]["sha256"] == module_declarations._digest(seal_path)
    assert declaration["declared_by"]["keys"] == {
        "horizontal_fov_rad": "horizontal_fov_rad",
        "image_width_px": "image_width",
        "image_height_px": "image_height",
    }


def test_declared_camera_geometry_refuses_a_seal_without_the_camera_it_measured():
    with pytest.raises(ValueError, match="image_width"):
        declared_camera_geometry(geometry_seal={"horizontal_fov_rad": HORIZONTAL_FOV_RAD})


# --- the pose hold and the spread it measures -----------------------------------------------------


def test_every_frame_of_a_pose_is_held_at_the_same_target():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    poses = [{"pose_rad": 0.08047101126546086, "pose_kind": "plan"}]

    result = measure(plant=plant, poses=poses, frames_per_pose=5)

    assert plant.commands == [0.08047101126546086] * 5
    assert result["poses"][0]["pose_drift_rad"] == pytest.approx(0.0)
    assert result["poses"][0]["frame_count"] == 5


def test_the_frame_records_carry_the_detected_centre_and_both_clock_stamps():
    result = measure(frames_per_pose=3)

    assert len(result["frames"]) == 3 * len(_poses())
    frame = result["frames"][0]

    assert frame["detection_count"] == 1
    assert frame["centre_px"][0] == pytest.approx(_project(0.0, -0.0588))
    assert frame["centre_px"][1] == pytest.approx(PRINCIPAL_Y_PX)
    assert frame["track_id"] == "cup-0"
    assert frame["principal_x_px"] == PRINCIPAL_X_PX
    assert frame["frame_sim_s"] == frame["received_sim_s"] == frame["decision_sim_s"]
    assert (
        frame["frame_monotonic_s"] <= frame["received_monotonic_s"] <= frame["decision_monotonic_s"]
    )
    assert len(frame["image_sha256"]) == 64


def test_the_measured_spread_is_the_jitter_the_detector_produced():
    offsets = (0.5, -0.5, 0.0, 0.0)
    plant = FakePlant(cup_yaw_rad=-0.0588)
    poses = [{"pose_rad": 0.0, "pose_kind": "anchor"}]

    result = measure(
        plant=plant,
        detector=FakeDetector(plant, offsets_px=offsets),
        poses=poses,
        frames_per_pose=len(offsets),
    )

    pose = result["poses"][0]
    expected = spread([_project(0.0, -0.0588) + offset for offset in offsets])
    assert pose["spread_x_px"]["std"] == pytest.approx(expected["std"])
    assert pose["spread_x_px"]["mean"] == pytest.approx(expected["mean"])
    assert result["centre_jitter_px"] == pytest.approx(expected["std"])


def test_the_headline_spread_is_the_worst_pose_of_the_anchor():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    poses = [
        {"pose_rad": 0.0, "pose_kind": "anchor"},
        {"pose_rad": 0.3, "pose_kind": "plan"},
    ]
    quiet = FakeDetector(plant, offsets_px=(0.0, 0.0, 0.0, 0.0))
    noisy = FakeDetector(plant, offsets_px=(0.0, 0.0, 3.0, 0.0))
    state = {"calls": 0}

    def detector(image, stamp_ns):
        use = quiet if state["calls"] < 4 else noisy
        state["calls"] += 1
        return use(image, stamp_ns)

    result = measure(plant=plant, detector=detector, poses=poses, frames_per_pose=4)

    worst = max(pose["spread_x_px"]["std"] for pose in result["poses"])
    assert result["centre_jitter_px"] == pytest.approx(worst)
    assert result["worst_pose"]["std"] == pytest.approx(worst)
    assert result["worst_pose"]["pose_rad"] == 0.3


def test_a_frame_without_a_detection_refuses_the_measurement():
    plant = FakePlant(cup_yaw_rad=-0.0588)

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        measure(plant=plant, detector=FakeDetector(plant, boxes_per_frame=0), frames_per_pose=3)

    assert refused.value.code == CAL_CAMERA_CUP_LOST
    assert "never wrote a zero spread" in refused.value.detail


def test_a_frame_with_two_detections_refuses_the_measurement():
    plant = FakePlant(cup_yaw_rad=-0.0588)

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        measure(plant=plant, detector=FakeDetector(plant, boxes_per_frame=2), frames_per_pose=3)

    assert refused.value.code == CAL_CAMERA_CUP_LOST
    assert "more than one" in refused.value.detail


def test_a_detector_that_fails_refuses_the_measurement():
    plant = FakePlant(cup_yaw_rad=-0.0588)

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        measure(plant=plant, detector=FakeDetector(plant, fail_at=(1,)), frames_per_pose=3)

    assert refused.value.code == CAL_CAMERA_CUP_LOST
    assert "DETECTOR_FAILED" in refused.value.detail


def test_a_pose_outside_the_corridor_is_refused_and_never_clamped():
    plant = FakePlant(cup_yaw_rad=-0.0588)
    poses = [{"pose_rad": 0.5, "pose_kind": "plan"}]

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        measure(plant=plant, poses=poses, frames_per_pose=3)

    assert refused.value.code == CAL_CAMERA_POSE_OUT_OF_CORRIDOR
    assert plant.commands == []


def test_a_stop_that_is_reached_but_never_settled_refuses_the_measurement():
    plant = FakePlant(cup_yaw_rad=-0.0588, settle=False)

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        measure(plant=plant, frames_per_pose=3)

    assert refused.value.code == CAL_TIMING_STOP_UNSETTLED


def test_a_stop_that_was_never_reached_refuses_the_measurement():
    plant = FakePlant(cup_yaw_rad=-0.0588, settle=False, reached=False)

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        measure(plant=plant, frames_per_pose=3)

    assert refused.value.code == CAL_TIMING_SWEEP_UNSETTLED


def test_a_settle_time_that_is_not_the_simulation_clocks_is_refused():
    plant = FakePlant(cup_yaw_rad=-0.0588, time_base="wall")

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        measure(plant=plant, frames_per_pose=3)

    assert refused.value.code == CAL_TIMING_TIME_BASE_UNVERIFIED


def test_frames_per_pose_must_be_a_whole_number_of_at_least_three():
    for bad in (2, 0, -1, 2.5, True):
        with pytest.raises(ValueError, match="at least"):
            measure(frames_per_pose=bad)


def test_the_measurement_needs_at_least_one_pose():
    with pytest.raises(ValueError, match="pose"):
        measure(poses=[], frames_per_pose=3)


def test_the_pose_hold_records_whether_the_rendered_frames_were_identical():
    result = measure(frames_per_pose=4)

    pose = result["poses"][0]
    assert pose["images_identical"] is False
    assert len(set(pose["image_sha256"])) == 4


# --- the document phase 6 reads -------------------------------------------------------------------


def _sealed_inputs(tmp_path):
    seal = {
        "required_search_domain_rad": list(CORRIDOR_RAD),
        "lock_valid_neck_rad": [-3.0, 3.0],
        "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
        "image_width": WIDTH_PX,
        "image_height": HEIGHT_PX,
        "camera_name": "head_camera",
        "in_frame_matrix": {"left": {"neck_start_rad": 0.0}},
        "workspace_matrix": {
            "key_samples": [{"anchor": "left", "kind": "anchor", "point_m": [-0.08, -0.28, 0.165]}]
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
            "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
            "lock_valid_neck_rad": [-3.0, 3.0],
        },
    }
    weights_path = tmp_path / "C.pt"
    weights_path.write_bytes(b"weights")
    frozen = {
        "candidate_id": "C",
        "weight_sha256": module_declarations._digest(weights_path),
        "operating_points": {"head": {"min_confidence": 0.25, "tracker": {"iou": 0.5}}},
    }
    scene = tmp_path / "head_search_scene.xml"
    scene.write_text("<mujoco/>\n", encoding="utf-8")
    seal_path = tmp_path / "seal.json"
    seal_path.write_text(json.dumps(seal), encoding="utf-8")
    production_path = tmp_path / "head_search_runtime.json"
    production_path.write_text(json.dumps(production), encoding="utf-8")
    frozen_path = tmp_path / "frozen-c.json"
    frozen_path.write_text(json.dumps(frozen), encoding="utf-8")
    controllers_path = tmp_path / "ros2_controllers.yaml"
    controllers_path.write_text(
        "controller_manager:\n  ros__parameters:\n    update_rate: 500\n", encoding="utf-8"
    )
    return scene, seal_path, production_path, frozen_path, controllers_path, weights_path


def _measurements(*, jitter_offsets=((0.5, -0.5, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0))):
    plant = FakePlant(cup_yaw_rad=-0.0588)
    poses = [{"pose_rad": 0.0, "pose_kind": "anchor"}]
    results = []
    for offsets in jitter_offsets:
        results.append(
            measure(
                plant=plant,
                detector=FakeDetector(plant, offsets_px=offsets),
                poses=poses,
                frames_per_pose=len(offsets),
            )
        )
    return results


def _document(tmp_path, *, safety_margin=None, geometry=None):
    measurements = _measurements()
    seal_path = tmp_path / "seal.json"
    seal_path.write_text(json.dumps({"horizontal_fov_rad": HORIZONTAL_FOV_RAD}), encoding="utf-8")
    return build_camera_measurements(
        path=tmp_path / "camera-measurements.json",
        command="measure-camera",
        measurements=measurements,
        geometry=geometry
        or declared_camera_geometry(
            geometry_seal={
                "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
                "image_width": WIDTH_PX,
                "image_height": HEIGHT_PX,
            },
            seal_path=seal_path,
            seal_sha256=module_declarations._digest(seal_path),
        ),
        safety_margin=undeclared_safety_margin() if safety_margin is None else safety_margin,
        frames_per_pose=4,
        corridor_rad=list(CORRIDOR_RAD),
        scene_path=tmp_path / "scene.xml",
        scene_sha256="a" * 64,
        geometry_seal_path=seal_path,
        geometry_seal_sha256=module_declarations._digest(seal_path),
        production_search_config_path=tmp_path / "head_search_runtime.json",
        production_search_config_sha256="b" * 64,
        runtime_identity_document={"python_version": "3.12.3"},
    )


def test_the_document_carries_every_key_phase_six_reads(tmp_path):
    document = _document(tmp_path)

    for key in (
        "horizontal_fov_rad",
        "image_width_px",
        "image_height_px",
        "centre_jitter_rad",
        "safety_margin_px",
    ):
        assert key in document, key
    assert document["kind"] == KIND
    assert document["phase"] == "camera_measurements"


def test_the_headline_jitter_is_the_worst_pose_and_the_round_trip_holds(tmp_path):
    document = _document(tmp_path)
    resolution = document["angular_resolution"]["rad_per_px"]
    worst = max(
        pose["spread_x_px"]["std"]
        for measurement in document["measurements"]
        for pose in measurement["poses"]
    )

    assert worst > 0.0
    assert resolution == pytest.approx(RAD_PER_PX)
    assert document["centre_jitter_px"] == pytest.approx(worst)
    assert document["centre_jitter_rad"] == pytest.approx(worst * RAD_PER_PX)
    # the round trip phase 6 performs: the pixel start it derives is the pixel spread measured here
    assert math.ceil(document["centre_jitter_rad"] / resolution) == math.ceil(worst)

    block = compute_center_deadband_px(
        camera=document,
        candidates=[
            {"center_deadband_px": 3.0, "longest_locked_run_frames": 3, "direction_reversals": 0},
            {"center_deadband_px": 18.0, "longest_locked_run_frames": 3, "direction_reversals": 0},
        ],
    )
    assert block["observed_distribution"]["start_deadband_px"] == math.ceil(worst)
    assert block["value"] == 3.0


def test_the_document_declares_the_geometry_it_did_not_measure_as_a_declaration(tmp_path):
    document = _document(tmp_path)

    declared = document["declared_fields"]
    for key in ("horizontal_fov_rad", "image_width_px", "image_height_px"):
        assert declared[key]["measured_here"] is False
        assert declared[key]["declared_by"]["sha256"]
    assert declared["image_width_px"]["value"] == WIDTH_PX
    assert document["centre_jitter"]["measured_here"] is True


def test_an_undeclared_safety_margin_is_null_and_carries_its_refusal(tmp_path):
    document = _document(tmp_path)

    assert document["safety_margin_px"] is None
    assert document["refusals"] == [
        {
            "code": CAL_CAMERA_SAFETY_MARGIN_UNDECLARED,
            "field": "safety_margin_px",
            "detail": document["safety_margin"]["detail"],
        }
    ]
    assert document["safety_margin"]["declared_by"] is None
    # phase 6's own reader finds no number here, and never a defaulted one: the vertical bounds it would
    # intersect the projected workspace with cannot be computed from this document
    with pytest.raises(ValueError, match="safety_margin_px"):
        compute_vertical_bounds_px(
            camera=document, workspace_projection={"top_px": 110.0, "bottom_px": 370.0}
        )


def test_a_declared_safety_margin_is_carried_with_its_declaring_artefact(tmp_path):
    artefact = tmp_path / "camera-safety.json"
    artefact.write_text(json.dumps({"safety_margin_px": 12.5}), encoding="utf-8")
    document = _document(tmp_path, safety_margin=read_declared_safety_margin(artefact))

    assert document["safety_margin_px"] == 12.5
    assert document["refusals"] == []
    assert document["safety_margin"]["measured_here"] is False
    assert document["safety_margin"]["declared_by"]["path"] == str(artefact)
    assert document["safety_margin"]["declared_by"]["sha256"] == module_declarations._digest(artefact)


def test_the_document_digest_covers_every_field_but_itself(tmp_path):
    document = _document(tmp_path)
    body = {key: value for key, value in document.items() if key != "sha256"}

    assert document["sha256"] == module_frames.canonical_sha256(body)
    assert document["digest_convention"] == module_frames.DIGEST_CONVENTION


def test_the_document_records_the_pose_set_the_frames_and_the_cadence(tmp_path):
    document = _document(tmp_path)

    assert document["frames_per_pose"] == 4
    assert document["frame_rate_hz"] == 10.0
    assert document["frame_period_s"] == pytest.approx(FRAME_PERIOD_S)
    assert document["corridor_rule"]
    assert document["motion_corridor_rad"] == list(CORRIDOR_RAD)
    assert document["measurements"][0]["poses"][0]["pose_kind"] == "anchor"
    assert document["frame_count"] == 8
    assert document["pose_count"] == 2


def test_the_document_needs_at_least_one_measured_anchor(tmp_path):
    seal_path = tmp_path / "seal.json"
    seal_path.write_text(json.dumps({"horizontal_fov_rad": HORIZONTAL_FOV_RAD}), encoding="utf-8")

    with pytest.raises(ValueError, match="at least one measured"):
        build_camera_measurements(
            path=None,
            command=None,
            measurements=[],
            geometry=declared_camera_geometry(
                geometry_seal={
                    "horizontal_fov_rad": HORIZONTAL_FOV_RAD,
                    "image_width": WIDTH_PX,
                    "image_height": HEIGHT_PX,
                },
                seal_path=seal_path,
                seal_sha256=module_declarations._digest(seal_path),
            ),
            safety_margin=undeclared_safety_margin(),
            frames_per_pose=4,
            corridor_rad=list(CORRIDOR_RAD),
            scene_path="scene.xml",
            scene_sha256="a" * 64,
            geometry_seal_path=seal_path,
            geometry_seal_sha256=module_declarations._digest(seal_path),
            production_search_config_path=None,
            production_search_config_sha256=None,
        )


# --- the producer ---------------------------------------------------------------------------------


def _patch_scene_declaration(monkeypatch, *, scene_sha256=None):
    monkeypatch.setattr(
        module_writer,
        "read_mujoco_timestep",
        lambda path: {
            "simulation_timestep_s": TIMESTEP_S,
            "scene_sha256": module_declarations._digest(path) if scene_sha256 is None else scene_sha256,
        },
    )
    monkeypatch.setattr(module_writer, "_cuda_available", lambda: True)


def _producer(
    tmp_path,
    *,
    plant_factory=None,
    detector_factory=None,
    seal_overrides=None,
    anchors=("left",),
    device="cpu",
    **kwargs,
):
    scene, seal, production, frozen, controllers, weights = _sealed_inputs(tmp_path)
    seal_document = json.loads(seal.read_text(encoding="utf-8"))
    seal_document["source_digests"]["scene_sha256"] = module_declarations._digest(scene)
    seal_document.update(seal_overrides or {})
    seal.write_text(json.dumps(seal_document), encoding="utf-8")
    production_document = json.loads(production.read_text(encoding="utf-8"))
    production_document["weight_sha256"] = module_declarations._digest(weights)
    production.write_text(json.dumps(production_document), encoding="utf-8")

    def default_plant(request):
        return FakePlant(cup_yaw_rad=-0.0588)

    return write_head_search_camera_measurement(
        scene_path=scene,
        geometry_seal_path=seal,
        production_search_config_path=production,
        controller_config_path=controllers,
        frozen_candidate_path=frozen,
        weights_path=weights,
        output_dir=tmp_path / "out",
        anchors=None if anchors is None else list(anchors),
        device=device,
        frames_per_pose=4,
        plant=plant_factory or default_plant,
        detector_factory=detector_factory or (lambda plant, request: FakeDetector(plant)),
        command="measure-camera",
        **kwargs,
    )


def test_the_producer_writes_the_document_the_receipt_and_the_refused_field(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch)
    result = _producer(tmp_path)

    document = json.loads((tmp_path / "out" / module_declarations.ARTIFACT).read_text(encoding="utf-8"))
    receipt = json.loads((tmp_path / "out" / module_declarations.RECEIPT_ARTIFACT).read_text(encoding="utf-8"))

    assert document["sha256"] == result["document"]["sha256"]
    assert document["safety_margin_px"] is None
    assert [record["code"] for record in document["refusals"]] == [
        CAL_CAMERA_SAFETY_MARGIN_UNDECLARED
    ]
    assert receipt["status"] == "MEASURED_WITH_REFUSED_FIELD"
    assert receipt["fields_refused"] == ["safety_margin_px"]
    assert receipt["document_path"] == str(tmp_path / "out" / module_declarations.ARTIFACT)
    assert receipt["frame_count"] == 4 * document["pose_count"]
    assert receipt["weights_sha256"] == module_declarations._digest(tmp_path / "C.pt")
    assert receipt["frames_per_pose"] == 4
    # the plant is injected here, so no runtime identity is claimed: the real flight records its own
    assert receipt["runtime_identity"] == {}
    assert receipt["centre_jitter_px"] == document["centre_jitter_px"]


def test_the_producer_records_a_declared_margin_with_its_declaring_artefact(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch)
    artefact = tmp_path / "camera-safety.json"
    artefact.write_text(json.dumps({"safety_margin_px": 10.0}), encoding="utf-8")

    result = _producer(tmp_path, safety_margin_declaration_path=artefact)

    document = result["document"]
    assert document["safety_margin_px"] == 10.0
    assert document["refusals"] == []
    assert document["safety_margin"]["declared_by"]["path"] == str(artefact)
    assert result["receipt"]["status"] == "SUCCEEDED"
    assert result["receipt"]["fields_refused"] == []


def test_the_producer_walks_the_anchor_start_and_the_bounded_plan_stops(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch)
    requests: list[dict] = []

    def detector_factory(plant, request):
        requests.append(request)
        return FakeDetector(plant)

    result = _producer(tmp_path, detector_factory=detector_factory)

    config = requests[0]["controller_config"]
    expected = [float(config["search_start_rad"]), *(float(v) for v in planned_stops(config))]
    unique = []
    for value in expected:
        if value not in unique:
            unique.append(value)
    assert [pose["pose_rad"] for pose in result["measurements"][0]["poses"]] == unique
    assert [pose["pose_kind"] for pose in result["measurements"][0]["poses"]] == [
        "anchor",
        "plan",
        "plan",
    ]
    assert [pose["pose_rad"] for pose in requests[0]["poses"]] == unique


def test_the_producer_refuses_weights_the_sealed_configuration_does_not_declare(
    tmp_path, monkeypatch
):
    _patch_scene_declaration(monkeypatch)
    scene, seal, production, frozen, controllers, weights = _sealed_inputs(tmp_path)
    seal_document = json.loads(seal.read_text(encoding="utf-8"))
    seal_document["source_digests"]["scene_sha256"] = module_declarations._digest(scene)
    seal.write_text(json.dumps(seal_document), encoding="utf-8")
    production.write_text(
        json.dumps(
            {**json.loads(production.read_text(encoding="utf-8")), "weight_sha256": "c" * 64}
        ),
        encoding="utf-8",
    )

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        write_head_search_camera_measurement(
            scene_path=scene,
            geometry_seal_path=seal,
            production_search_config_path=production,
            controller_config_path=controllers,
            frozen_candidate_path=frozen,
            weights_path=weights,
            output_dir=tmp_path / "out",
            anchors=["left"],
            device="cpu",
            plant=lambda request: FakePlant(cup_yaw_rad=-0.0588),
            detector_factory=lambda plant, request: FakeDetector(plant),
        )

    assert refused.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_the_producer_refuses_a_scene_the_sealed_geometry_does_not_pin(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch, scene_sha256="d" * 64)

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        _producer(tmp_path)

    assert refused.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_the_producer_refuses_an_output_directory_that_already_exists(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch)
    (tmp_path / "out").mkdir()

    with pytest.raises(FileExistsError):
        _producer(tmp_path)


def test_the_producer_refuses_an_anchor_the_seal_does_not_declare(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch)

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        _producer(tmp_path, anchors=["nope"])

    assert refused.value.code == CAL_TIMING_EVIDENCE_MISSING


def test_the_producer_refuses_an_anchor_start_outside_the_motion_corridor(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch)

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        _producer(tmp_path, seal_overrides={"required_search_domain_rad": [0.05, 0.2]})

    assert refused.value.code == CAL_CAMERA_POSE_OUT_OF_CORRIDOR


def test_the_producer_refuses_a_declared_cuda_device_without_one(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch)
    monkeypatch.setattr(module_writer, "_cuda_available", lambda: False)

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        _producer(tmp_path, device="cuda")

    assert refused.value.code == CAL_TIMING_DEVICE_UNAVAILABLE


def test_the_producer_needs_at_least_one_declared_anchor(tmp_path, monkeypatch):
    _patch_scene_declaration(monkeypatch)

    with pytest.raises(CalibrationCameraMeasurementRefused) as refused:
        _producer(tmp_path, anchors=[])

    assert refused.value.code == CAL_TIMING_EVIDENCE_MISSING


def test_the_producer_declares_the_refusal_vocabulary_it_can_raise():
    assert set(REFUSAL_CODES) == {
        CAL_CAMERA_CUP_LOST,
        CAL_CAMERA_POSE_OUT_OF_CORRIDOR,
        CAL_CAMERA_SAFETY_MARGIN_UNDECLARED,
        CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE,
        CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY,
        CAL_TIMING_EVIDENCE_MISSING,
        CAL_TIMING_EVIDENCE_CONTRADICTORY,
        CAL_TIMING_STOP_UNSETTLED,
        CAL_TIMING_SWEEP_UNSETTLED,
        CAL_TIMING_TIME_BASE_UNVERIFIED,
        CAL_TIMING_DEVICE_UNAVAILABLE,
    }
    assert DEFAULT_FRAMES_PER_POSE >= MIN_FRAMES_PER_POSE >= 3
