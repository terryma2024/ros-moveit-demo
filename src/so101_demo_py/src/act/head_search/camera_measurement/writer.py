"""Write the camera measurement document."""

from __future__ import annotations

from collections.abc import Mapping
import json
import math
from pathlib import Path
import time

from so101_demo.act.head_search.camera_measurement.declarations import (
    ARTIFACT,
    DEFAULT_FRAMES_PER_POSE,
    MEASUREMENT_ATTEMPT_ID,
    MEASUREMENT_SESSION_ID,
    RECEIPT_ARTIFACT,
    RECEIPT_KIND,
    SCHEMA_VERSION,
    _re_raised,
    _refuse,
    declared_camera_geometry,
    read_declared_safety_margin,
    undeclared_safety_margin,
)
from so101_demo.act.head_search.camera_measurement.frames import (
    _anchor_pose_requests,
    _cuda_available,
    build_camera_measurements,
    measure_anchor_frames,
)
from so101_demo.act.head_search.deadband_measurement.lock_trial import (
    detector_operating_point,
    motion_corridor_rad,
)
from so101_demo.act.head_search.deadband_measurement.plant import (
    MujocoClosedLoopPlant,
    _plant_request,
    build_production_head_detector,
)
from so101_demo.act.head_search.mujoco_measurements import read_mujoco_timestep
from so101_demo.act.head_search.timing_measurement.contracts import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    DEFAULT_MAX_SETTLE_S,
    SETTLE_CONSECUTIVE_STEPS,
    _digest,
)
from so101_demo.act.head_search.timing_measurement.control import (
    read_control_period,
)
from so101_demo.act.head_search.timing_measurement.documents import (
    runtime_identity as measurement_runtime_identity,
)
from so101_demo.act.head_search.timing_measurement.sweep_runner import _declared_weights


def write_head_search_camera_measurement(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    frozen_candidate_path,
    weights_path,
    output_dir,
    safety_margin_declaration_path=None,
    anchors=None,
    device="cuda",
    frames_per_pose=DEFAULT_FRAMES_PER_POSE,
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    attempt_id=MEASUREMENT_ATTEMPT_ID,
    session_id=MEASUREMENT_SESSION_ID,
    command=None,
    plant=None,
    detector_factory=None,
) -> dict:
    """Hold every sealed anchor's poses in the sealed scene and write the document phase 6 reads.

    Every declared input is read and cross-checked before a single step is taken: the scene has to be the
    one the sealed geometry pins, the control period has to be a whole number of the scene's own timesteps,
    the weights have to be the ones the declared production configuration seals and the frozen candidate's
    own, the frozen candidate has to declare its head operating point, the declared device has to exist,
    and every pose has to lie inside the sealed motion corridor. The document and its receipt are the only
    files this producer creates; a field no artefact declares is written as `null` with its refusal rather
    than defaulted, and the receipt says which fields those were.
    """

    started = time.time()
    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    frozen_path = Path(frozen_candidate_path)
    for path in (scene, seal_path, production_path, controller_path, frozen_path):
        if not path.is_file():
            raise FileNotFoundError(f"the camera measurement needs {path}")
    weights = Path(weights_path)
    if not weights.is_file():
        raise FileNotFoundError(f"the camera measurement needs {weights}")
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
            f"the sealed geometry pins the scene {sealed_scene}, but the scene these frames would be "
            f"rendered in digests to {scene_sha256}",
        )
    control_period = _re_raised(read_control_period, controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s steps, so the poses could not be held at the production period",
        )
    weights_sha256 = _re_raised(_declared_weights, production, {"weights_path": weights_path})
    if str(device).startswith("cuda") and not _cuda_available():
        raise _refuse(
            CAL_TIMING_DEVICE_UNAVAILABLE,
            f"the detector was declared for {device!r} but no CUDA device is available, and this "
            f"measurement never falls back to the CPU",
        )
    operating_point = _re_raised(detector_operating_point, frozen)
    frozen_weights = frozen.get("weight_sha256")
    if isinstance(frozen_weights, str) and frozen_weights != weights_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the frozen candidate seals the weights {frozen_weights}, but the production search "
            f"configuration seals {weights_sha256}: the frames would not be the selected model's",
        )
    requests = _anchor_pose_requests(
        seal=seal,
        production=production,
        anchors=anchors,
        attempt_id=attempt_id,
        session_id=session_id,
    )
    corridor = _re_raised(motion_corridor_rad, geometry_seal=seal)
    geometry = declared_camera_geometry(
        geometry_seal=seal, seal_path=seal_path, seal_sha256=_digest(seal_path)
    )
    margin = (
        undeclared_safety_margin()
        if safety_margin_declaration_path is None
        else read_declared_safety_margin(
            safety_margin_declaration_path, image_geometry=geometry
        )
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
    measurements: list[dict] = []
    for request in requests:
        anchor_plant = (
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
            measurements.append(
                measure_anchor_frames(
                    plant=anchor_plant,
                    detector=(
                        detector
                        if detector_factory is None
                        else detector_factory(anchor_plant, request)
                    ),
                    anchor=request["anchor"],
                    poses=request["poses"],
                    frames_per_pose=frames_per_pose,
                    corridor_rad=corridor,
                    settle_consecutive_steps=settle_consecutive_steps,
                    max_settle_s=max_settle_s,
                )
            )
        finally:
            close = getattr(anchor_plant, "close", None)
            if callable(close):
                close()
    document_path = output / ARTIFACT
    document = build_camera_measurements(
        path=document_path,
        command=command,
        measurements=measurements,
        geometry=geometry,
        safety_margin=margin,
        frames_per_pose=frames_per_pose,
        corridor_rad=corridor,
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
    document_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    refusals = list(document["refusals"])
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "status": "MEASURED_WITH_REFUSED_FIELD" if refusals else "SUCCEEDED",
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
        "anchor_names": [request["anchor"] for request in requests],
        "poses_measured": [
            {
                "anchor": result["anchor"],
                "poses": [pose["pose_rad"] for pose in result["poses"]],
                "pose_kinds": [pose["pose_kind"] for pose in result["poses"]],
            }
            for result in measurements
        ],
        "frames_per_pose": int(frames_per_pose),
        "frame_count": document["frame_count"],
        "pose_count": document["pose_count"],
        "centre_jitter_rad": document["centre_jitter_rad"],
        "centre_jitter_px": document["centre_jitter_px"],
        "rad_per_px": document["angular_resolution"]["rad_per_px"],
        "horizontal_fov_rad": document["horizontal_fov_rad"],
        "image_width_px": document["image_width_px"],
        "image_height_px": document["image_height_px"],
        "safety_margin_px": document["safety_margin_px"],
        "safety_margin": dict(margin),
        "refusals": refusals,
        "fields_refused": [record["field"] for record in refusals],
        "motion_corridor_rad": [float(bound) for bound in corridor],
        "simulation_timestep_s": timestep,
        "control_period_s": control_period,
        "max_settle_s": float(max_settle_s),
        "settle_consecutive_steps": int(settle_consecutive_steps),
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
        "measurements": measurements,
        "safety_margin": margin,
        "refusals": refusals,
    }
