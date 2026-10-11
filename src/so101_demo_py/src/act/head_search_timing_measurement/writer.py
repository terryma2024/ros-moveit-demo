"""Write the two timing measurement documents and their receipt."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
import time

from so101_demo.act.head_search_mujoco_measurements import read_mujoco_timestep
from so101_demo.act.head_search_timing_measurement.contracts import (
    _PERIOD_TOLERANCE_S,
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    DEFAULT_MAX_SETTLE_S,
    FRAME_AGE_ARTIFACT,
    FRAME_CONTRACT_ARTIFACT,
    FRAME_RATE_HZ,
    MEASUREMENT_ATTEMPT_ID,
    MEASUREMENT_SESSION_ID,
    RECEIPT_ARTIFACT,
    RECEIPT_KIND,
    SCHEMA_VERSION,
    SEARCH_TIMING_ARTIFACT,
    SETTLE_CONSECUTIVE_STEPS,
    SETTLE_RULE,
    _cuda_available,
    _digest,
    _mapping,
    _refuse,
    _sequence,
)
from so101_demo.act.head_search_timing_measurement.control import (
    _sealed_scene_sha256,
    classify_stop,
    read_control_period,
    verify_simulation_time_base,
)
from so101_demo.act.head_search_timing_measurement.documents import (
    _frame_samples,
    build_frame_age_measurements,
    build_search_timing,
    frame_contract_document,
    runtime_identity,
)
from so101_demo.act.head_search_timing_measurement.sweep_runner import (
    MujocoNeckSweepRunner,
    _anchor_requests,
    _declared_weights,
)


def write_head_search_timing_measurement(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    output_dir,
    weights_path=None,
    anchors=None,
    device="cuda",
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    attempt_id=MEASUREMENT_ATTEMPT_ID,
    session_id=MEASUREMENT_SESSION_ID,
    startup_readback=None,
    command=None,
    runner=None,
) -> dict:
    """Measure the bounded sweep once and write the documents into a brand-new directory.

    The declared inputs are read and cross-checked before anything is stepped: the scene has to be the one
    the sealed geometry pins, the control period has to be a whole number of the scene's own timesteps, and
    the detector has to be the sealed model on an available CUDA device (`allow_cpu_fallback=false`: a
    measurement that cannot use the declared device refuses rather than falling back). Then the sweep runs,
    the simulation time base is proved, every stop is classified, and only then are the documents written.
    """

    started = time.time()
    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    for path in (scene, seal_path, production_path, controller_path):
        if not path.is_file():
            raise FileNotFoundError(f"the timing measurement needs {path}")
    if weights_path is not None and not Path(weights_path).is_file():
        raise FileNotFoundError(f"the timing measurement needs {weights_path}")
    output = Path(output_dir)
    output.mkdir(parents=True)

    declaration = read_mujoco_timestep(scene)
    seal_document = json.loads(seal_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    scene_sha256 = declaration["scene_sha256"]
    sealed_scene = _sealed_scene_sha256(seal_document)
    if sealed_scene != scene_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry pins the scene {sealed_scene}, but the scene this sweep would step "
            f"digests to {scene_sha256}: the sweep would measure a model the calibration did not seal",
        )
    control_period = read_control_period(controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(
        steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=_PERIOD_TOLERANCE_S
    ):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s simulation steps, so the sweep cannot command the neck at the period the "
            f"production controller runs at",
        )
    weights_sha256 = _declared_weights(production, {"weights_path": weights_path})
    if weights_sha256 is not None and str(device).startswith("cuda") and not _cuda_available():
        raise _refuse(
            CAL_TIMING_DEVICE_UNAVAILABLE,
            f"the detector was declared for {device!r} but no CUDA device is available, and this "
            f"measurement never falls back to the CPU",
        )
    anchor_requests = _anchor_requests(
        seal=seal_document,
        production=production,
        anchors=anchors,
        attempt_id=attempt_id,
        session_id=session_id,
    )
    camera = _mapping("sealed geometry camera", seal_document.get("camera"))
    request = {
        "scene_path": str(scene),
        "scene_sha256": scene_sha256,
        "camera_name": seal_document.get("camera_name"),
        "image_width": seal_document.get("image_width"),
        "image_height": seal_document.get("image_height"),
        "simulation_timestep_s": timestep,
        "control_period_s": control_period,
        "frame_rate_hz": FRAME_RATE_HZ,
        "settle_velocity_rad_s": anchor_requests[0]["controller_config"]["settle_velocity_rad_s"],
        "goal_tolerance_rad": anchor_requests[0]["controller_config"]["goal_tolerance_rad"],
        "settle_consecutive_steps": settle_consecutive_steps,
        "max_settle_s": max_settle_s,
        "anchors": anchor_requests,
        "weights_path": None if weights_path is None else str(weights_path),
        "weights_sha256": weights_sha256,
        "device": device,
        "min_confidence": anchor_requests[0]["controller_config"]["min_confidence"],
        "tracking_iou": production.get("tracker", {}).get("iou_threshold")
        if isinstance(production.get("tracker"), Mapping)
        else None,
        "camera_identity": dict(camera) if isinstance(camera, Mapping) else {},
    }
    result = (runner or MujocoNeckSweepRunner())(request)
    base = verify_simulation_time_base(result)
    stops = [
        classify_stop(
            stop,
            settle_consecutive_steps=int(settle_consecutive_steps),
            max_settle_s=float(max_settle_s),
        )
        for stop in result["stops"]
    ]
    detector = result.get("detector") if isinstance(result.get("detector"), Mapping) else {}
    frames = _sequence("sweep frames", result.get("frames"))
    if frames and not detector.get("loaded"):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            "the sweep records frames but reports no loaded detector, so their frame times would belong to "
            "nothing",
        )
    if frames and weights_sha256 is None:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            "the sweep timed frames but no detector weights were declared, so the frame times cannot be "
            "attributed to a sealed model",
        )
    reported = detector.get("weights_sha256")
    if frames and reported is not None and reported != weights_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sweep timed frames with the weights {reported}, but the sealed detector is "
            f"{weights_sha256}",
        )
    samples = _frame_samples(frames)
    control = {
        "control_period_s": control_period,
        "source_path": str(controller_path),
        "source_sha256": _digest(controller_path),
        "key": "controller_manager.ros__parameters.update_rate",
        "update_rate_hz": 1.0 / control_period,
        "steps_per_period": int(round(steps_per_period)),
        "declared_by": "the sealed controller configuration",
    }
    timing_path = output / SEARCH_TIMING_ARTIFACT
    identity = (
        result.get("runtime_identity")
        if runner is not None
        else runtime_identity(
            device=device, detector_loaded=bool(detector.get("loaded")), weights_sha256=weights_sha256
        )
    )
    if runner is not None and not identity:
        identity = {}
    contract_path = None
    contract = None
    if samples:
        contract_path = output / FRAME_CONTRACT_ARTIFACT
        contract = frame_contract_document(
            path=contract_path, command=command, startup_readback=startup_readback
        )
        contract_path.write_text(
            json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    timing = build_search_timing(
        path=timing_path,
        command=command,
        request=request,
        result=result,
        stops=stops,
        frames=samples,
        control=control,
        scene_path=scene,
        scene_sha256=scene_sha256,
        geometry_seal_path=seal_path,
        geometry_seal_sha256=_digest(seal_path),
        production_search_config_path=production_path,
        production_search_config_sha256=_digest(production_path),
        weights_path=weights_path,
        weights_sha256=weights_sha256,
        runtime_identity=identity,
    )
    timing_path.write_text(
        json.dumps(timing, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    frame_age_path = None
    frame_age = None
    if samples:
        frame_age_path = output / FRAME_AGE_ARTIFACT
        frame_age = build_frame_age_measurements(
            path=frame_age_path,
            command=command,
            frame_contract=contract,
            samples=samples,
            result=result,
            scene_sha256=scene_sha256,
            weights_sha256=weights_sha256,
            runtime_identity=identity,
        )
        frame_age_path.write_text(
            json.dumps(frame_age, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "status": "SUCCEEDED",
        "command": command,
        "output_dir": str(output),
        "search_timing_path": str(timing_path),
        "search_timing_sha256": timing["sha256"],
        "frame_age_path": None if frame_age_path is None else str(frame_age_path),
        "frame_age_sha256": None if frame_age is None else frame_age["sha256"],
        "frame_contract_path": None if contract_path is None else str(contract_path),
        "frame_contract_sha256": None if contract is None else contract["sha256"],
        "scene_path": str(scene),
        "scene_sha256": scene_sha256,
        "geometry_seal_path": str(seal_path),
        "geometry_seal_sha256": _digest(seal_path),
        "production_search_config_path": str(production_path),
        "production_search_config_sha256": _digest(production_path),
        "controller_config_path": str(controller_path),
        "controller_config_sha256": _digest(controller_path),
        "weights_path": None if weights_path is None else str(weights_path),
        "weights_sha256": weights_sha256,
        "control_period_s": control_period,
        "simulation_timestep_s": timestep,
        "settle_rule": SETTLE_RULE,
        "settle_consecutive_steps": int(settle_consecutive_steps),
        "max_settle_s": float(max_settle_s),
        "time_base": base["time_base"],
        "stable_stop_count": timing["stable_stop_count"],
        "frame_count": len(samples),
        "p99_settle_s": timing["p99_settle_s"],
        "p99_frame_s": timing["p99_frame_s"],
        "sweep_sim_time_s": result.get("sim_time_s"),
        "sweep_wall_time_s": result.get("wall_time_s"),
        "warmup": dict(result.get("warmup") or {"performed": False}),
        "elapsed_s": time.time() - started,
        "anchors": [anchor["anchor"] for anchor in anchor_requests],
        "runtime_identity": dict(identity or {}),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "transport_measured": False,
        "motion_commanded": False,
    }
    (output / RECEIPT_ARTIFACT).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "search_timing": timing,
        "frame_age": frame_age,
        "frame_contract": contract,
        "receipt": receipt,
        "search_timing_path": timing_path,
        "frame_age_path": frame_age_path,
        "frame_contract_path": contract_path,
        "output_dir": output,
    }
