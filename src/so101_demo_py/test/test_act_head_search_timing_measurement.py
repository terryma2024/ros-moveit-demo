"""The runtime sweep timing measurement: phases 6 and 7's first two measurement documents.

Every fixture here is synthetic: no MuJoCo, no detector, no GPU, no CUDA, no ROS and no motion. The
sweep executor is injected, so the decision layer - the settle rule, the simulation-time proof, the
refusals and the two documents - is exercised without a simulator, and the real MuJoCo runner is only
ever reached through the installed CLI's real run.

What these tests pin:

* the settle rule is a declared threshold held for a declared number of consecutive control steps, and a
  stop that is reached without settling is refused (`CAL_TIMING_STOP_UNSETTLED`) while a sweep that never
  settles at all is refused as `CAL_TIMING_SWEEP_UNSETTLED`;
* the sweep's time base has to be the MuJoCo simulation clock: a settle time that is not its own step
  count times the sealed timestep, a wall-clock time base, or a frame without simulation stamps is
  refused with `CAL_TIMING_TIME_BASE_UNVERIFIED` instead of being recorded as timing;
* the controller the sweep walks is the production one, built from the sealed documents, and its bounded
  stop points are the sweep's stops;
* the control period is the sealed controller configuration's declaration and must be a whole number of
  the sealed simulation timesteps;
* the produced `search-timing.json` is accepted by phase 6's own `compute_search_timeout_s` and the
  produced `frame-age-measurements.json` by phase 7's own `compute_max_age_s`;
* without a declared detector no frame age is invented: the frame-age document is not written at all and
  the timing document records that its frame time was not measured.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_search_params import compute_search_timeout_s
from so101_demo.act.head_search_timing_measurement import (
    AGE_TIME_BASE,
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    DIGEST_CONVENTION,
    FRAME_AGE_ARTIFACT,
    FRAME_AGE_KIND,
    FRAME_CONTRACT_ARTIFACT,
    FRAME_CONTRACT_KIND,
    FRAME_RATE_HZ,
    RECEIPT_KIND,
    REFUSAL_CODES,
    SEARCH_TIMING_ARTIFACT,
    SEARCH_TIMING_KIND,
    SETTLE_CONSECUTIVE_STEPS,
    SETTLE_RULE,
    SIMULATION_TIME_BASE,
    CalibrationTimingMeasurementRefused,
    SettleTracker,
    controller_config,
    read_control_period,
    write_head_search_timing_measurement,
)
from so101_demo.act.head_search_timing_params import compute_max_age_s
from so101_demo.perception_benchmark.contracts import canonical_sha256

TIMESTEP_S = 0.002
CONTROL_PERIOD_S = 0.002
FOV_RAD = 1.3121067481206794
DOMAIN_RAD = (-0.17559216195018026, 0.08047101126546086)
LOCK_INTERVAL_RAD = (-6.283175307179587, 6.283175307179587)
COARSE_STEP_RAD = 0.3
ANCHORS = {"default": 0.1, "left": 0.0}

SCENE = """<mujoco model="fixture">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody><body name="table"/></worldbody>
</mujoco>
"""

CONTROLLERS = """controller_manager:
  ros__parameters:
    update_rate: 500
joint_state_broadcaster:
  ros__parameters:
    update_rate: 100
"""


def _digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path, document) -> str:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return str(path)


def _scene(tmp_path):
    path = tmp_path / "head_search_scene.xml"
    path.write_text(SCENE, encoding="utf-8")
    return path


def _seal(tmp_path, scene, **overrides):
    document = {
        "schema_version": 1,
        "camera_name": "head_camera",
        "camera": {
            "camera_name": "head_camera",
            "parent_body": "head_mount",
            "width": 640,
            "height": 480,
            "fovy_rad": 1.0471975511965976,
            "distortion_model": "plumb_bob",
            "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
        },
        "image_width": 640,
        "image_height": 480,
        "horizontal_fov_rad": FOV_RAD,
        "required_search_domain_rad": list(DOMAIN_RAD),
        "lock_valid_neck_rad": list(LOCK_INTERVAL_RAD),
        "in_frame_matrix": {name: {"neck_start_rad": start} for name, start in ANCHORS.items()},
        "source_digests": {"scene_sha256": _digest(scene)},
    }
    document.update(overrides)
    return tmp_path / "head-camera-geometry.json", document


def _production(tmp_path, **overrides):
    document = {
        "schema_version": 2,
        "runtime_id": "head-search-v2",
        "camera": {
            "name": "head_camera",
            "width": 640,
            "height": 480,
            "frame_id": "head_camera_frame",
            "ray_origin_frame_id": "head_camera_frame",
        },
        "motion": {"settle_velocity_rad_s": 0.05, "goal_tolerance_rad": 0.05},
        "tracker": {"name": "bytetrack", "iou_threshold": 0.3},
        "weight_sha256": "f" * 64,
        "values": {
            "coarse_step_rad": COARSE_STEP_RAD,
            "horizontal_fov_rad": FOV_RAD,
            "lock_valid_neck_rad": list(LOCK_INTERVAL_RAD),
            "max_age_s": 0.05,
            "max_skew_s": 0.02,
            "search_timeout_s": 12.0,
            "center_deadband_px": 18.0,
            "vertical_bounds_px": [110.0, 370.0],
            "min_area_px2": 64.0,
            "min_confidence": 0.4,
            "tracking_iou": 0.3,
            "max_fine_corrections": 4,
            "max_fine_total_rad": 0.4,
            "stop_velocity_rad_s": 0.05,
            "min_bbox_aspect": 0.5,
            "stop_latency_s": 0.06,
            "submit_lead_s": 0.02,
        },
    }
    document.update(overrides)
    return tmp_path / "head_search_v2.json", document


def _controllers(tmp_path):
    path = tmp_path / "ros2_controllers.yaml"
    path.write_text(CONTROLLERS, encoding="utf-8")
    return path


def _fixture(tmp_path, *, seal_overrides=None, production_overrides=None):
    """The three sealed inputs a sweep is planned from, written into `tmp_path`."""

    scene = _scene(tmp_path)
    seal_path, seal = _seal(tmp_path, scene, **(seal_overrides or {}))
    _write(seal_path, seal)
    production_path, production = _production(tmp_path, **(production_overrides or {}))
    _write(production_path, production)
    return {
        "scene_path": scene,
        "geometry_seal_path": seal_path,
        "production_search_config_path": production_path,
        "controller_config_path": _controllers(tmp_path),
        "seal": seal,
        "production": production,
    }


def _weights(tmp_path, digest="f" * 64):
    payload = b"fixture-weights"
    path = tmp_path / "weights.pt"
    path.write_bytes(payload)
    return path


def _stop_record(
    *,
    anchor="default",
    index=0,
    kinds="plan",
    target_rad=0.08047101126546086,
    start_rad=0.1,
    steps=100,
    sim_start_s=0.0,
    settled=True,
    reached=True,
    settle_s=None,
    time_base=SIMULATION_TIME_BASE,
):
    return {
        "anchor": anchor,
        "index": index,
        "kind": kinds,
        "target_rad": target_rad,
        "start_rad": start_rad,
        "sim_start_s": sim_start_s,
        "sim_end_s": sim_start_s + (steps * TIMESTEP_S if settle_s is None else settle_s),
        "steps": steps,
        "settle_s": steps * TIMESTEP_S if settle_s is None else settle_s,
        "settled": settled,
        "reached": reached,
        "final_velocity_rad_s": 0.001,
        "final_position_error_rad": 0.002,
        "quiet_steps": SETTLE_CONSECUTIVE_STEPS,
        "reached_step": 60 if reached else None,
        "time_base": time_base,
    }


def _frame_record(index, *, sim_s=None, age_s=0.012, time_base=AGE_TIME_BASE):
    sim_s = index * 0.1 if sim_s is None else sim_s
    return {
        "frame_index": index,
        "anchor": "default",
        "stop_index": 0,
        "frame_sim_s": sim_s,
        "received_sim_s": sim_s,
        "decision_sim_s": sim_s,
        "frame_monotonic_s": 1000.0 + sim_s,
        "received_monotonic_s": 1000.0 + sim_s,
        "decision_monotonic_s": 1000.0 + sim_s + age_s,
        "age_s": age_s,
        "frame_time_s": age_s + 0.003,
        "sim_age_s": 0.0,
        "detection_count": 1,
        "max_confidence": 0.8,
        "render_s": 0.003,
        "inference_s": age_s,
        "time_base": time_base,
    }


def _result(
    *,
    stops=None,
    frames=None,
    time_base=SIMULATION_TIME_BASE,
    detector=True,
    weights_sha256=None,
    **overrides,
):
    stops = [_stop_record(), _stop_record(index=1, target_rad=DOMAIN_RAD[0])] if stops is None else stops
    if frames is None:
        frames = [_frame_record(0), _frame_record(1)] if detector else []
    result = {
        "time_base": time_base,
        "simulation_timestep_s": TIMESTEP_S,
        "control_period_s": CONTROL_PERIOD_S,
        "stops": stops,
        "frames": frames,
        "sim_time_s": 1.2,
        "wall_time_s": 1.4,
        "detector": (
            {
                "loaded": True,
                "device": "cuda",
                "weights_path": "/fixture/weights.pt",
                "weights_sha256": weights_sha256,
            }
            if detector
            else {"loaded": False, "device": None, "weights_path": None, "weights_sha256": None}
        ),
        "runtime_identity": {
            "python_version": "3.12",
            "mujoco_version": "3.12.0",
            "ros_nodes_started": False,
            "mujoco_neck_commanded": True,
            "hardware_motion_commanded": False,
        },
    }
    result.update(overrides)
    return result


def _produce(tmp_path, fixture, *, runner=None, weights="auto", **overrides):
    """Run the producer with a synthetic sweep; `weights="auto"` declares a weights file it seals."""

    if weights == "auto":
        weights = _weights(tmp_path)
        fixture["production"]["weight_sha256"] = _digest(weights)
        _write(fixture["production_search_config_path"], fixture["production"])
    elif weights is False:
        weights = None
    output = tmp_path / "sweep-timing"
    request = dict(
        scene_path=fixture["scene_path"],
        geometry_seal_path=fixture["geometry_seal_path"],
        production_search_config_path=fixture["production_search_config_path"],
        controller_config_path=fixture["controller_config_path"],
        weights_path=weights,
        output_dir=output,
        command="ros2 run so101_demo_py so101_head_search_calibration measure-search-timing",
    )
    request.update(overrides)
    return write_head_search_timing_measurement(runner=runner or (lambda _request: _result()), **request)


# --- the settle rule ------------------------------------------------------------------------------


def test_the_settle_rule_needs_its_consecutive_quiet_steps():
    tracker = SettleTracker(
        settle_velocity_rad_s=0.05, goal_tolerance_rad=0.05, consecutive_steps=3
    )

    observed = [
        tracker.observe(0.4, 0.2),
        tracker.observe(0.01, 0.04),
        tracker.observe(0.01, 0.03),
        tracker.observe(0.01, 0.02),
    ]

    assert observed == [False, False, False, True]
    assert SETTLE_CONSECUTIVE_STEPS == 5
    assert "consecutive" in SETTLE_RULE


def test_the_settle_rule_resets_when_the_neck_moves_again():
    tracker = SettleTracker(
        settle_velocity_rad_s=0.05, goal_tolerance_rad=0.05, consecutive_steps=2
    )

    assert tracker.observe(0.01, 0.01) is False
    assert tracker.observe(0.4, 0.01) is False
    assert tracker.observe(0.01, 0.01) is False
    assert tracker.observe(0.01, 0.01) is True


def test_a_stop_that_is_out_of_tolerance_is_not_settled_by_a_quiet_velocity():
    tracker = SettleTracker(
        settle_velocity_rad_s=0.05, goal_tolerance_rad=0.05, consecutive_steps=2
    )

    assert tracker.observe(0.01, 0.4) is False
    assert tracker.observe(0.01, 0.4) is False


def test_the_settle_tracker_refuses_thresholds_that_are_not_measurements():
    for bad in (
        dict(settle_velocity_rad_s=0.0, goal_tolerance_rad=0.05, consecutive_steps=2),
        dict(settle_velocity_rad_s=0.05, goal_tolerance_rad=-0.1, consecutive_steps=2),
        dict(settle_velocity_rad_s=0.05, goal_tolerance_rad=0.05, consecutive_steps=0),
    ):
        with pytest.raises(ValueError):
            SettleTracker(**bad)


# --- the refusals ---------------------------------------------------------------------------------


def test_a_stop_reached_without_settling_is_refused(tmp_path):
    fixture = _fixture(tmp_path)
    stopped = _stop_record(settled=False, reached=True)

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(tmp_path, fixture, runner=lambda _r: _result(stops=[stopped]))

    assert refused.value.code == CAL_TIMING_STOP_UNSETTLED
    assert isinstance(refused.value, CalibrationInputsRefused)


def test_a_sweep_that_cannot_settle_is_refused(tmp_path):
    fixture = _fixture(tmp_path)
    stopped = _stop_record(settled=False, reached=False)

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(tmp_path, fixture, runner=lambda _r: _result(stops=[stopped]))

    assert refused.value.code == CAL_TIMING_SWEEP_UNSETTLED


def test_a_settle_time_that_is_not_the_simulation_clock_is_refused(tmp_path):
    fixture = _fixture(tmp_path)
    wall_timed = _stop_record(steps=100, settle_s=0.5)

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(tmp_path, fixture, runner=lambda _r: _result(stops=[wall_timed]))

    assert refused.value.code == CAL_TIMING_TIME_BASE_UNVERIFIED


def test_a_sweep_that_is_not_run_in_simulation_time_is_refused(tmp_path):
    fixture = _fixture(tmp_path)

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(
            tmp_path,
            fixture,
            runner=lambda _r: _result(
                time_base="monotonic_wall_clock",
                stops=[_stop_record(time_base="monotonic_wall_clock")],
            ),
        )

    assert refused.value.code == CAL_TIMING_TIME_BASE_UNVERIFIED


def test_a_frame_without_simulation_stamps_is_refused(tmp_path):
    fixture = _fixture(tmp_path)
    frame = _frame_record(0)
    del frame["frame_sim_s"]

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(tmp_path, fixture, runner=lambda _r: _result(frames=[frame]))

    assert refused.value.code == CAL_TIMING_TIME_BASE_UNVERIFIED


def test_a_decision_that_precedes_its_frame_is_refused(tmp_path):
    fixture = _fixture(tmp_path)
    frame = _frame_record(0)
    frame["decision_monotonic_s"] = frame["received_monotonic_s"] - 0.001

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(tmp_path, fixture, runner=lambda _r: _result(frames=[frame]))

    assert refused.value.code == CAL_TIMING_TIME_BASE_UNVERIFIED


def test_a_sweep_without_a_single_settled_stop_is_refused(tmp_path):
    fixture = _fixture(tmp_path)

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(tmp_path, fixture, runner=lambda _r: _result(stops=[]))

    assert refused.value.code == CAL_TIMING_SWEEP_UNSETTLED


# --- the declared inputs --------------------------------------------------------------------------


def test_the_controller_config_is_built_from_the_sealed_documents(tmp_path):
    fixture = _fixture(tmp_path)

    config = controller_config(
        production_search_config=fixture["production"],
        geometry_seal=fixture["seal"],
        anchor="default",
        attempt_id="attempt",
        session_id="session",
    )

    assert config["search_start_rad"] == pytest.approx(0.1)
    assert config["coarse_step_rad"] == pytest.approx(COARSE_STEP_RAD)
    assert config["required_search_domain_rad"] == pytest.approx(list(DOMAIN_RAD))
    assert config["lock_valid_neck_rad"] == pytest.approx(list(LOCK_INTERVAL_RAD))
    assert config["settle_velocity_rad_s"] == pytest.approx(0.05)
    assert config["goal_tolerance_rad"] == pytest.approx(0.05)
    assert config["frame_id"] == "head_camera_frame"
    assert config["ray_origin_frame_id"] == "head_camera_frame"


def test_a_fov_that_disagrees_with_the_seal_is_contradictory(tmp_path):
    fixture = _fixture(tmp_path, production_overrides={
        "values": dict(_production(tmp_path)[1]["values"], horizontal_fov_rad=1.0)
    })

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        controller_config(
            production_search_config=fixture["production"],
            geometry_seal=fixture["seal"],
            anchor="default",
            attempt_id="attempt",
            session_id="session",
        )

    assert refused.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_an_anchor_the_seal_does_not_declare_is_refused(tmp_path):
    fixture = _fixture(tmp_path)

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        controller_config(
            production_search_config=fixture["production"],
            geometry_seal=fixture["seal"],
            anchor="absent",
            attempt_id="attempt",
            session_id="session",
        )

    assert refused.value.code == CAL_TIMING_EVIDENCE_MISSING


def test_the_control_period_is_the_controller_configurations_declaration(tmp_path):
    fixture = _fixture(tmp_path)

    period = read_control_period(fixture["controller_config_path"])

    assert period == pytest.approx(0.002)


def test_a_control_period_that_is_not_a_whole_number_of_timesteps_is_refused(tmp_path):
    fixture = _fixture(tmp_path)
    fixture["controller_config_path"].write_text(
        CONTROLLERS.replace("update_rate: 500", "update_rate: 300"), encoding="utf-8"
    )

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(tmp_path, fixture)

    assert refused.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_the_seal_must_pin_the_scene_the_sweep_steps(tmp_path):
    fixture = _fixture(tmp_path, seal_overrides={
        "source_digests": {"scene_sha256": "a" * 64}
    })

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(tmp_path, fixture)

    assert refused.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_the_weights_must_be_the_ones_the_production_config_declares(tmp_path):
    fixture = _fixture(tmp_path)
    weights = _weights(tmp_path)

    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(tmp_path, fixture, weights=weights)

    assert refused.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_a_device_that_would_fall_back_to_the_cpu_is_refused(tmp_path, monkeypatch):
    fixture = _fixture(tmp_path)
    weights = _weights(tmp_path)
    fixture["production"]["weight_sha256"] = _digest(weights)
    _write(fixture["production_search_config_path"], fixture["production"])

    import so101_demo.act.head_search_timing_measurement as module

    monkeypatch.setattr(module, "_cuda_available", lambda: False)
    with pytest.raises(CalibrationTimingMeasurementRefused) as refused:
        _produce(tmp_path, fixture, weights=weights, runner=None)

    assert refused.value.code == CAL_TIMING_DEVICE_UNAVAILABLE


# --- the produced documents -----------------------------------------------------------------------


def test_the_search_timing_document_carries_the_fields_phase_six_reads(tmp_path):
    fixture = _fixture(tmp_path)
    weights = _weights(tmp_path)
    fixture["production"]["weight_sha256"] = _digest(weights)
    _write(fixture["production_search_config_path"], fixture["production"])

    result = _produce(tmp_path, fixture, weights=weights)
    document = json.loads(result["search_timing_path"].read_text(encoding="utf-8"))

    assert document["kind"] == SEARCH_TIMING_KIND
    assert document["stable_stop_count"] == 2
    assert document["stops_planned"] == 2
    for key in ("p99_settle_s", "p99_frame_s", "control_period_s"):
        assert document[key] > 0.0
    assert document["time_base"] == SIMULATION_TIME_BASE
    assert document["path"] == str(result["search_timing_path"])
    block = compute_search_timeout_s(
        bounded_sweep={
            "sealed_geometry": {
                "path": str(fixture["geometry_seal_path"]),
                "sha256": _digest(fixture["geometry_seal_path"]),
            },
            "coverage_proof": {
                "anchors": [{"anchor": "default", "targets_rad": [0.08, -0.17]}]
            },
        },
        timing=document,
        max_fine_corrections=1,
    )
    assert block["value"] == pytest.approx(
        2 * (document["p99_settle_s"] + document["p99_frame_s"]) + 1 * CONTROL_PERIOD_S
    )
    assert {"path": document["path"], "sha256": document["sha256"]} in block["input_evidence"]


def test_the_frame_age_document_carries_the_fields_phase_seven_reads(tmp_path):
    fixture = _fixture(tmp_path)
    weights = _weights(tmp_path)
    fixture["production"]["weight_sha256"] = _digest(weights)
    _write(fixture["production_search_config_path"], fixture["production"])

    result = _produce(tmp_path, fixture, weights=weights)
    document = json.loads(result["frame_age_path"].read_text(encoding="utf-8"))

    assert document["kind"] == FRAME_AGE_KIND
    assert len(document["samples"]) == 2
    assert document["frame_contract"]["frame_rate_hz"] == FRAME_RATE_HZ
    assert document["time_base"] == AGE_TIME_BASE
    block = compute_max_age_s(frame_age=document, frame_contract=document["frame_contract"])
    assert block["value"] == pytest.approx(
        max(sample["age_s"] for sample in document["samples"]) + 0.010
    )


def test_the_frame_contract_declaration_is_what_phase_seven_requires(tmp_path):
    fixture = _fixture(tmp_path)
    weights = _weights(tmp_path)
    fixture["production"]["weight_sha256"] = _digest(weights)
    _write(fixture["production_search_config_path"], fixture["production"])

    result = _produce(tmp_path, fixture, weights=weights)
    document = json.loads(result["frame_contract_path"].read_text(encoding="utf-8"))

    assert document["kind"] == FRAME_CONTRACT_KIND
    assert document["frame_rate_hz"] == FRAME_RATE_HZ
    assert document["frame_period_s"] == pytest.approx(1.0 / FRAME_RATE_HZ)
    assert document["startup_readback"]["verified"] is False


def test_without_a_declared_detector_no_frame_age_is_invented(tmp_path):
    fixture = _fixture(tmp_path)

    result = _produce(tmp_path, fixture, runner=lambda _r: _result(detector=False, frames=[]))
    document = json.loads(result["search_timing_path"].read_text(encoding="utf-8"))

    assert document["p99_frame_s"] is None
    assert document["frame_timing"]["measured"] is False
    assert result["frame_age_path"] is None
    assert not (result["output_dir"] / FRAME_AGE_ARTIFACT).exists()
    assert not (result["output_dir"] / FRAME_CONTRACT_ARTIFACT).exists()
    with pytest.raises(CalibrationInputsRefused) as refused:
        compute_search_timeout_s(
            bounded_sweep={
                "sealed_geometry": {
                    "path": str(fixture["geometry_seal_path"]),
                    "sha256": _digest(fixture["geometry_seal_path"]),
                },
                "coverage_proof": {"anchors": [{"anchor": "default", "targets_rad": [0.08]}]},
            },
            timing=document,
            max_fine_corrections=1,
        )
    assert refused.value.code == "CAL_TIMEOUT_UNBOUNDED"


def test_the_producer_writes_the_documents_and_the_receipt(tmp_path):
    fixture = _fixture(tmp_path)
    weights = _weights(tmp_path)
    fixture["production"]["weight_sha256"] = _digest(weights)
    _write(fixture["production_search_config_path"], fixture["production"])

    result = _produce(tmp_path, fixture, weights=weights)

    written = sorted(path.name for path in result["output_dir"].iterdir())
    assert written == [
        "frame-age-measurements.json",
        "frame-contract.json",
        "measurement-receipt.json",
        "search-timing.json",
    ]
    receipt = json.loads((result["output_dir"] / "measurement-receipt.json").read_text())
    assert receipt["kind"] == RECEIPT_KIND
    assert receipt["status"] == "SUCCEEDED"
    assert receipt["stable_stop_count"] == 2
    assert receipt["frame_count"] == 2
    assert receipt["runtime_identity"]["ros_nodes_started"] is False
    assert receipt["mujoco_neck_commanded"] is True
    assert receipt["hardware_motion_commanded"] is False
    assert json.loads(result["search_timing_path"].read_text())["kind"] == SEARCH_TIMING_KIND


def test_the_documents_carry_a_self_digest_over_their_bodies(tmp_path):
    fixture = _fixture(tmp_path)
    weights = _weights(tmp_path)
    fixture["production"]["weight_sha256"] = _digest(weights)
    _write(fixture["production_search_config_path"], fixture["production"])

    result = _produce(tmp_path, fixture, weights=weights)

    for path in (result["search_timing_path"], result["frame_age_path"], result["frame_contract_path"]):
        document = json.loads(path.read_text(encoding="utf-8"))
        body = {key: value for key, value in document.items() if key != "sha256"}
        assert document["sha256"] == canonical_sha256(body), path.name
        assert document["digest_convention"] == DIGEST_CONVENTION


def test_the_producer_refuses_an_existing_output_directory(tmp_path):
    fixture = _fixture(tmp_path)
    output = tmp_path / "sweep-timing"
    output.mkdir()

    with pytest.raises(FileExistsError):
        write_head_search_timing_measurement(
            scene_path=fixture["scene_path"],
            geometry_seal_path=fixture["geometry_seal_path"],
            production_search_config_path=fixture["production_search_config_path"],
            controller_config_path=fixture["controller_config_path"],
            output_dir=output,
            runner=lambda _r: _result(),
        )


def test_the_sweep_is_planned_from_the_controllers_own_bounded_stops(tmp_path):
    fixture = _fixture(tmp_path)
    seen = {}

    def runner(request):
        seen.update(request)
        return _result()

    _produce(tmp_path, fixture, runner=runner)

    assert [anchor["anchor"] for anchor in seen["anchors"]] == ["default", "left"]
    first = seen["anchors"][0]
    assert first["search_start_rad"] == pytest.approx(0.1)
    assert len(first["targets_rad"]) == 2
    assert seen["control_period_s"] == pytest.approx(CONTROL_PERIOD_S)
    assert seen["simulation_timestep_s"] == pytest.approx(TIMESTEP_S)
    assert seen["settle_consecutive_steps"] == SETTLE_CONSECUTIVE_STEPS


def test_the_warmup_is_recorded_next_to_the_distribution_not_inside_it(tmp_path):
    fixture = _fixture(tmp_path)
    warmup = {"performed": True, "wall_s": 1.18, "detections": 1, "declared_because": "one frame first"}
    stops = [_stop_record(kinds="anchor"), _stop_record(), _stop_record(index=1, target_rad=DOMAIN_RAD[0])]

    result = _produce(
        tmp_path, fixture, runner=lambda _r: _result(stops=stops, warmup=warmup)
    )
    document = json.loads(result["search_timing_path"].read_text(encoding="utf-8"))

    assert document["frame_timing"]["warmup"] == warmup
    assert document["frame_timing"]["sample_count"] == 2
    assert document["settle_s"]["anchor_positioning_stops"] == 1
    assert document["settle_s"]["sample_count"] == 2
    assert document["stable_stop_count"] == 2
    assert result["receipt"]["warmup"] == warmup


def test_the_refusal_codes_are_the_declared_set():
    assert set(REFUSAL_CODES) == {
        CAL_TIMING_EVIDENCE_MISSING,
        CAL_TIMING_EVIDENCE_CONTRADICTORY,
        CAL_TIMING_SWEEP_UNSETTLED,
        CAL_TIMING_STOP_UNSETTLED,
        CAL_TIMING_TIME_BASE_UNVERIFIED,
        CAL_TIMING_DEVICE_UNAVAILABLE,
    }
    assert SEARCH_TIMING_ARTIFACT == "search-timing.json"
    assert FRAME_AGE_ARTIFACT == "frame-age-measurements.json"
