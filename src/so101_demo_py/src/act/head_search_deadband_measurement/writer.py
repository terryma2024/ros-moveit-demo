"""Write the deadband measurement document."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
import time

from so101_demo.act.head_search_deadband_measurement.contracts import (
    ARTIFACT,
    DEFAULT_MAX_FRAMES,
    MEASUREMENT_ATTEMPT_ID,
    MEASUREMENT_SESSION_ID,
    RECEIPT_ARTIFACT,
    RECEIPT_KIND,
    SCHEMA_VERSION,
    _refuse,
)
from so101_demo.act.head_search_deadband_measurement.lock_trial import (
    _corridor_check,
    _re_raised,
    build_deadband_candidates,
    declared_candidates,
    detector_operating_point,
    motion_corridor_rad,
    run_lock_trial,
)
from so101_demo.act.head_search_deadband_measurement.plant import (
    MujocoClosedLoopPlant,
    _anchor_requests,
    _cuda_available,
    _plant_request,
    build_production_head_detector,
)
from so101_demo.act.head_search_mujoco_measurements import read_mujoco_timestep
from so101_demo.act.head_search_search_params import LOCK_FRAMES
from so101_demo.act.head_search_timing_measurement.contracts import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    DEFAULT_MAX_SETTLE_S,
    SETTLE_CONSECUTIVE_STEPS,
    _digest,
)
from so101_demo.act.head_search_timing_measurement.control import (
    read_control_period,
)
from so101_demo.act.head_search_timing_measurement.documents import (
    runtime_identity as measurement_runtime_identity,
)
from so101_demo.act.head_search_timing_measurement.sweep_runner import _declared_weights


def write_head_search_deadband_measurement(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    frozen_candidate_path,
    weights_path,
    output_dir,
    candidates,
    anchors=None,
    device="cuda",
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    max_frames=DEFAULT_MAX_FRAMES,
    attempt_id=MEASUREMENT_ATTEMPT_ID,
    session_id=MEASUREMENT_SESSION_ID,
    command=None,
    plant=None,
    detector_factory=None,
) -> dict:
    """Run one closed-loop lock trial per declared candidate and write the document phase 6 reads.

    Every declared input is read and cross-checked before anything is stepped: the scene has to be the one
    the sealed geometry pins, the control period has to be a whole number of the scene's own timesteps, the
    detector has to be the weight the sealed configuration declares, the frozen candidate has to declare
    its head operating point, and each anchor's search start has to lie inside the motion corridor. The
    trials then run one candidate at a time, and the document and its receipt are the only files this
    producer creates.
    """

    started = time.time()
    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    frozen_path = Path(frozen_candidate_path)
    for path in (scene, seal_path, production_path, controller_path, frozen_path):
        if not path.is_file():
            raise FileNotFoundError(f"the deadband measurement needs {path}")
    weights = Path(weights_path)
    if not weights.is_file():
        raise FileNotFoundError(f"the deadband measurement needs {weights}")
    declared = declared_candidates(candidates)
    output = Path(output_dir)
    output.mkdir(parents=True)

    declaration = read_mujoco_timestep(scene)
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    scene_sha256 = declaration["scene_sha256"]
    sealed_scene = (seal.get("source_digests") or {}).get("scene_sha256")
    if sealed_scene != scene_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry pins the scene {sealed_scene}, but the scene these lock trials would "
            f"step the neck in digests to {scene_sha256}",
        )
    control_period = _re_raised(read_control_period, controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s steps, so the trials could not command the neck at the production period",
        )
    weights_sha256 = _re_raised(
        _declared_weights, production, {"weights_path": weights_path}
    )
    if str(device).startswith("cuda") and not _cuda_available():
        raise _refuse(
            CAL_TIMING_DEVICE_UNAVAILABLE,
            f"the detector was declared for {device!r} but no CUDA device is available, and this "
            f"measurement never falls back to the CPU",
        )
    operating_point = detector_operating_point(frozen)
    frozen_weights = frozen.get("weight_sha256")
    if isinstance(frozen_weights, str) and frozen_weights != weights_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the frozen candidate seals the weights {frozen_weights}, but the production search "
            f"configuration seals {weights_sha256}: the trials would not run the selected model",
        )
    corridor = motion_corridor_rad(geometry_seal=seal)
    requests = _anchor_requests(
        seal=seal,
        production=production,
        anchors=anchors,
        attempt_id=attempt_id,
        session_id=session_id,
    )
    for request in requests:
        _corridor_check(
            angle_rad=request["search_start_rad"],
            corridor_rad=corridor,
            what=f"declared search start of the anchor {request['anchor']!r}",
        )
    camera = seal.get("camera") if isinstance(seal.get("camera"), Mapping) else {}
    detector = (
        None
        if detector_factory is not None
        else build_production_head_detector(
            weights_path=weights,
            operating_point=operating_point,
            production=production,
            frame_id=requests[0]["controller_config"]["frame_id"],
            device=device,
            attempt_id=attempt_id,
            session_id=session_id,
        )
    )
    trials: list[dict] = []
    for request in requests:
        for candidate in declared:
            trial_plant = (
                plant(request)
                if plant is not None
                else MujocoClosedLoopPlant(
                    _plant_request(
                        request=request,
                        scene=scene,
                        seal=seal,
                        camera=camera,
                        control_period_s=control_period,
                        max_settle_s=max_settle_s,
                        settle_consecutive_steps=settle_consecutive_steps,
                    )
                )
            )
            try:
                trials.append(
                    run_lock_trial(
                        controller_config=request["controller_config"],
                        deadband_px=candidate,
                        plant=trial_plant,
                        detector=(
                            detector
                            if detector_factory is None
                            else detector_factory(trial_plant, request)
                        ),
                        corridor_rad=corridor,
                        anchor=request["anchor"],
                        max_frames=max_frames,
                        settle_consecutive_steps=settle_consecutive_steps,
                        max_settle_s=max_settle_s,
                    )
                )
            finally:
                close = getattr(trial_plant, "close", None)
                if callable(close):
                    close()
    document_path = output / ARTIFACT
    document = build_deadband_candidates(
        path=document_path,
        command=command,
        trials=trials,
        candidates_px=declared,
        control={
            "control_period_s": control_period,
            "source_path": str(controller_path),
            "source_sha256": _digest(controller_path),
            "key": "controller_manager.ros__parameters.update_rate",
            "update_rate_hz": 1.0 / control_period,
            "steps_per_period": int(round(steps_per_period)),
            "declared_by": "the sealed controller configuration",
        },
        controller_config=requests[0]["controller_config"],
        scene_path=scene,
        scene_sha256=scene_sha256,
        geometry_seal_path=seal_path,
        geometry_seal_sha256=_digest(seal_path),
        production_search_config_path=production_path,
        production_search_config_sha256=_digest(production_path),
        frozen_candidate_path=frozen_path,
        frozen_candidate_sha256=_digest(frozen_path),
        weights_path=weights,
        weights_sha256=weights_sha256,
        detector_operating_point=operating_point,
        corridor_rad=corridor,
        anchors=[
            {
                "anchor": request["anchor"],
                "search_start_rad": request["search_start_rad"],
                "cup_start_m": list(request["cup_start_m"]),
            }
            for request in requests
        ],
        detector_loaded=detector is not None or detector_factory is not None,
        device=device,
        runtime_identity_document=(
            {}
            if plant is not None
            else measurement_runtime_identity(
                device=device, detector_loaded=True, weights_sha256=weights_sha256
            )
        ),
    )
    document_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "status": "SUCCEEDED",
        "command": command,
        "output_dir": str(output),
        "document_path": str(document_path),
        "document_sha256": document["sha256"],
        "scene_path": str(scene),
        "scene_sha256": scene_sha256,
        "geometry_seal_path": str(seal_path),
        "geometry_seal_sha256": _digest(seal_path),
        "production_search_config_path": str(production_path),
        "production_search_config_sha256": _digest(production_path),
        "frozen_candidate_path": str(frozen_path),
        "frozen_candidate_sha256": _digest(frozen_path),
        "weights_path": str(weights),
        "weights_sha256": weights_sha256,
        "detector_operating_point": dict(operating_point),
        "candidate_count": len(declared),
        "candidates_px": declared,
        "anchor_names": [request["anchor"] for request in requests],
        "trial_count": len(trials),
        "records": document["records"],
        "warmup": dict(document["warmup"]),
        "motion_corridor_rad": [float(bound) for bound in corridor],
        "lock_frames_required": LOCK_FRAMES,
        "simulation_timestep_s": timestep,
        "control_period_s": control_period,
        "max_settle_s": float(max_settle_s),
        "settle_consecutive_steps": int(settle_consecutive_steps),
        "max_frames": int(max_frames),
        "elapsed_s": time.time() - started,
        "runtime_identity": dict(document["runtime_identity"]),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "transport_measured": False,
        "tracking_measured": False,
        "motion_commanded": False,
    }
    (output / RECEIPT_ARTIFACT).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "document": document,
        "receipt": receipt,
        "document_path": document_path,
        "output_dir": output,
        "trials": trials,
    }
