"""Measure the anchor frames and build the camera measurement records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import hashlib
import json
import time

from so101_demo.act.head_search.camera_measurement.declarations import (
    _SHA256,
    ANGULAR_RESOLUTION_RULE,
    CAL_CAMERA_CUP_LOST,
    CAL_CAMERA_POSE_OUT_OF_CORRIDOR,
    CORRIDOR_RULE,
    FRAME_CADENCE,
    JITTER_AXIS,
    JITTER_COMBINATION,
    JITTER_DEFINITION,
    KIND,
    MIN_FRAMES_PER_POSE,
    PHASE,
    SCHEMA_VERSION,
    _interval,
    _mapping,
    _number,
    _re_raised,
    _refuse,
    _sequence,
    rad_per_px,
    spread,
)
from so101_demo.act.head_search.deadband_measurement.lock_trial import (
    motion_corridor_rad,
)
from so101_demo.act.head_search.deadband_measurement.plant import (
    _anchor_requests,
)
from so101_demo.act.head_search.timing_measurement.contracts import (
    DIGEST_CONVENTION,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
    SETTLE_RULE,
    SIMULATION_TIME_BASE,
    _digest,
    _finite,
)
from so101_demo.act.head_search.timing_measurement.control import (
    classify_stop,
    planned_stops,
    verify_simulation_time_base,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


def _pose_records(poses) -> list[dict]:
    """The declared poses, normalised, deduplicated and with at least one of them."""

    records: list[dict] = []
    seen: set[float] = set()
    for pose in _sequence("declared poses", poses):
        if isinstance(pose, Mapping):
            value = pose.get("pose_rad")
            kind = pose.get("pose_kind", "plan")
            if type(kind) is not str or not kind:
                raise ValueError("every declared pose names its kind")
        elif _finite(pose):
            value, kind = float(pose), "plan"
        else:
            raise ValueError(f"every declared pose is an angle or a pose record: {pose!r}")
        if not _finite(value):
            raise ValueError(f"every declared pose must be a finite angle: {value!r}")
        angle = float(value)
        if angle in seen:
            continue
        seen.add(angle)
        records.append({"pose_rad": angle, "pose_kind": kind})
    if not records:
        raise ValueError("the measurement needs at least one pose to hold the neck at")
    return records


def _corridor_check(*, angle_rad: float, corridor_rad, what: str) -> None:
    low, high = corridor_rad
    if not low - 1e-12 <= float(angle_rad) <= high + 1e-12:
        raise _refuse(
            CAL_CAMERA_POSE_OUT_OF_CORRIDOR,
            f"the {what} {float(angle_rad)!r} rad is outside the declared motion corridor "
            f"{[low, high]} rad, and this measurement never holds the neck at an angle the seal does not "
            f"bound",
        )


def _detections(call, image, stamp_ns) -> list:
    """The frame's detections in the production detector's own shape, or the refusal that stops it."""

    try:
        found = call(image, stamp_ns)
    except Exception as error:  # the detector's own failure is not a camera measurement
        raise _refuse(
            CAL_CAMERA_CUP_LOST,
            f"the detector failed on a frame of this measurement ({type(error).__name__}: {error}), so "
            f"the centre of that frame was never observed",
        ) from error
    detections = []
    for detection in found or ():
        detections.append(
            {
                "xyxy": tuple(float(value) for value in detection["xyxy"]),
                "confidence": float(detection["confidence"]),
                "class_id": int(detection["class_id"]),
                "track_id": str(detection["track_id"]),
            }
        )
    return detections


def _single_centre(detections, *, frame_index: int, pose_rad: float) -> list[float]:
    """The one detected cup's box centre, or the refusal that says which frame had no single cup."""

    if not detections:
        raise _refuse(
            CAL_CAMERA_CUP_LOST,
            f"the detector found no cup in frame {frame_index} of the pose {pose_rad!r} rad, and this "
            f"measurement never wrote a zero spread for a centre it did not detect",
        )
    if len(detections) > 1:
        raise _refuse(
            CAL_CAMERA_CUP_LOST,
            f"the detector resolved more than one cup ({len(detections)}) in frame {frame_index} of the "
            f"pose {pose_rad!r} rad, so that frame has no single centre whose spread could be measured",
        )
    box = detections[0]["xyxy"]
    return [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0]


def _image_digest(image) -> str:
    """A digest of one rendered frame, for evidence about frame-to-frame identity.

    It is a diagnostic, not an identity of record: a frame buffer digests its bytes, a mapping its
    canonical encoding, and anything else its representation.
    """

    to_bytes = getattr(image, "tobytes", None)
    if callable(to_bytes):
        return hashlib.sha256(to_bytes()).hexdigest()
    if isinstance(image, (bytes, bytearray)):
        return hashlib.sha256(bytes(image)).hexdigest()
    if isinstance(image, Mapping):
        payload = json.dumps(dict(image), sort_keys=True, default=str)
    else:  # pragma: no cover - the real plant always renders an array
        payload = repr(image)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def measure_anchor_frames(
    *,
    plant,
    detector,
    anchor: str,
    poses,
    frames_per_pose: int,
    corridor_rad,
    settle_consecutive_steps: int,
    max_settle_s: float,
    clock=time.monotonic,
) -> dict:
    """Hold every declared pose of one anchor and observe it frame by frame.

    One frame is one declared frame period of simulation time: the plant is commanded to the same target
    it already holds, the timing module's settle rule and stop classification decide that the pose is
    really held, the head camera renders, the production detector finds the cup, and the box centre is
    recorded with its simulation stamps, its wall-clock stamps and the rendered frame's digest. Nothing
    here moves the neck anywhere but the declared poses, and no frame is invented: a frame without exactly
    one detected cup stops the measurement.
    """

    if type(frames_per_pose) is not int or isinstance(frames_per_pose, bool):
        raise ValueError(f"a pose needs at least {MIN_FRAMES_PER_POSE} frames, as a whole number")
    if frames_per_pose < MIN_FRAMES_PER_POSE:
        raise ValueError(
            f"a pose needs at least {MIN_FRAMES_PER_POSE} frames to have a spread at all, not "
            f"{frames_per_pose}"
        )
    timestep = getattr(plant, "simulation_timestep_s", None)
    if not _finite(timestep) or float(timestep) <= 0.0:
        raise ValueError(
            "the plant must declare the simulation timestep its frames were stepped at"
        )
    pose_records = _pose_records(poses)
    low, high = _interval("motion corridor", corridor_rad)
    for record in pose_records:
        _corridor_check(
            angle_rad=record["pose_rad"],
            corridor_rad=(low, high),
            what=f"declared pose of the anchor {anchor!r}",
        )
    reset = getattr(detector, "reset", None)
    if callable(reset):
        reset()

    started = time.time()
    stops: list[dict] = []
    frames: list[dict] = []
    pose_documents: list[dict] = []
    for record in pose_records:
        centres: list[list[float]] = []
        digests: list[str] = []
        velocities: list[float] = []
        drift = 0.0
        pose_start_s = float(plant.time_s)
        for _ in range(frames_per_pose):
            stop = dict(plant.settle_to(record["pose_rad"]))
            stop.update(
                anchor=anchor,
                index=len(stops),
                kind=record["pose_kind"],
                pose_rad=record["pose_rad"],
            )
            # a plant that declares its own time base is believed and proven, never overwritten: the
            # time-base proof below refuses a stop that is not the sealed simulation clock's
            stop.setdefault("time_base", SIMULATION_TIME_BASE)
            stops.append(
                _re_raised(
                    classify_stop,
                    stop,
                    settle_consecutive_steps=settle_consecutive_steps,
                    max_settle_s=max_settle_s,
                )
            )
            held = float(plant.yaw_rad)
            _corridor_check(angle_rad=held, corridor_rad=(low, high), what="held neck angle")
            drift = max(drift, abs(held - record["pose_rad"]))
            frame_wall = clock()
            image = plant.render_frame()
            received_wall = clock()
            stamp_ns = int(plant.frame_stamp_ns)
            geometry = plant.optical_geometry()
            detections = _detections(detector, image, stamp_ns)
            centre = _single_centre(
                detections, frame_index=len(frames), pose_rad=record["pose_rad"]
            )
            decision_wall = clock()
            sim_s = float(plant.time_s)
            velocity = float(plant.velocity_rad_s)
            velocities.append(velocity)
            centres.append(centre)
            digests.append(_image_digest(image))
            frames.append(
                {
                    "frame_index": len(frames),
                    "anchor": anchor,
                    "pose_rad": record["pose_rad"],
                    "pose_kind": record["pose_kind"],
                    "frame_interval_sim_s": (
                        None if len(frames) == 0 else sim_s - float(frames[-1]["frame_sim_s"])
                    ),
                    "frame_sim_s": sim_s,
                    "received_sim_s": sim_s,
                    "decision_sim_s": sim_s,
                    "frame_monotonic_s": frame_wall,
                    "received_monotonic_s": received_wall,
                    "decision_monotonic_s": decision_wall,
                    "neck_yaw_rad": held,
                    "neck_velocity_rad_s": velocity,
                    "principal_x_px": float(geometry["k"][2]),
                    "principal_y_px": float(geometry["k"][5]),
                    "k": [float(value) for value in geometry["k"]],
                    "distortion": [float(value) for value in geometry["distortion"]],
                    "rotation_optical_to_base": [
                        [float(value) for value in row]
                        for row in geometry["rotation_optical_to_base"]
                    ],
                    "detection_count": len(detections),
                    "detections": [
                        {
                            "xyxy": list(detection["xyxy"]),
                            "confidence": detection["confidence"],
                            "class_id": detection["class_id"],
                            "track_id": detection["track_id"],
                            "centre_px": [
                                (detection["xyxy"][0] + detection["xyxy"][2]) / 2.0,
                                (detection["xyxy"][1] + detection["xyxy"][3]) / 2.0,
                            ],
                        }
                        for detection in detections
                    ],
                    "centre_px": list(centre),
                    "track_id": detections[0]["track_id"],
                    "image_sha256": digests[-1],
                    "time_base": SIMULATION_TIME_BASE,
                }
            )
        columns = [centre[0] for centre in centres]
        rows = [centre[1] for centre in centres]
        pose_documents.append(
            {
                "pose_rad": record["pose_rad"],
                "pose_kind": record["pose_kind"],
                "frame_count": len(centres),
                "sim_start_s": pose_start_s,
                "sim_end_s": float(plant.time_s),
                "pose_drift_rad": drift,
                "centre_x_px": columns,
                "centre_y_px": rows,
                "centre_px": [list(centre) for centre in centres],
                "spread_x_px": spread(columns),
                "spread_y_px": spread(rows),
                "neck_velocity_rad_s": velocities,
                "image_sha256": digests,
                "images_identical": len(set(digests)) == 1,
            }
        )
    worst = max(pose_documents, key=lambda pose: pose["spread_x_px"]["std"])
    worst_rows = max(pose_documents, key=lambda pose: pose["spread_y_px"]["std"])
    result = {
        "anchor": anchor,
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(timestep),
        "frames_per_pose": int(frames_per_pose),
        "pose_count": len(pose_documents),
        "frame_count": len(frames),
        "poses": pose_documents,
        "stops": stops,
        "frames": frames,
        "centre_jitter_px": worst["spread_x_px"]["std"],
        "row_jitter_px": worst_rows["spread_y_px"]["std"],
        "worst_pose": {
            "pose_rad": worst["pose_rad"],
            "pose_kind": worst["pose_kind"],
            "std": worst["spread_x_px"]["std"],
            "frame_count": worst["frame_count"],
        },
        "worst_row_pose": {
            "pose_rad": worst_rows["pose_rad"],
            "pose_kind": worst_rows["pose_kind"],
            "std": worst_rows["spread_y_px"]["std"],
            "frame_count": worst_rows["frame_count"],
        },
        "settle_rule": SETTLE_RULE,
        "corridor_rule": CORRIDOR_RULE,
        "motion_corridor_rad": [low, high],
        "wall_time_s": time.time() - started,
        "sim_time_s": float(plant.time_s),
    }
    _re_raised(verify_simulation_time_base, result)
    return result


def _reference(name: str, path, digest: str | None = None) -> dict | None:
    if path is None:
        return None
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        digest = _digest(path)
    return {"path": str(path), "sha256": digest}


def build_camera_measurements(
    *,
    path,
    command,
    measurements,
    geometry: Mapping,
    safety_margin: Mapping,
    frames_per_pose: int,
    corridor_rad,
    scene_path,
    scene_sha256: str,
    geometry_seal_path=None,
    geometry_seal_sha256: str | None = None,
    production_search_config_path=None,
    production_search_config_sha256: str | None = None,
    frozen_candidate_path=None,
    frozen_candidate_sha256: str | None = None,
    weights_path=None,
    weights_sha256: str | None = None,
    detector_operating_point: Mapping | None = None,
    detector_loaded: bool = True,
    device: str = "cuda",
    runtime_identity_document: Mapping | None = None,
) -> dict:
    """The `camera_measurements` document: the measured jitter, and the declared margin or its refusal.

    `centre_jitter_rad` is computed here, from the measured per-pose spreads and the sealed angular
    resolution - never from a declared or defaulted number - and `safety_margin_px` is either the value an
    artefact declared (with ``measured_here: false`` and its declaring path and digest) or ``null`` with
    the refusal that says no artefact declares it. The document keeps every measured frame, every pose's
    distribution and every held stop beside the headline numbers, so a reviewer can recompute the jitter
    rather than trust it.
    """

    measured = _sequence("measured anchors", measurements)
    if not measured:
        raise ValueError("the document needs at least one measured anchor")
    for result in measured:
        if not isinstance(result, Mapping) or not isinstance(result.get("poses"), Sequence):
            raise ValueError("every measured anchor must carry the poses it held")
    declared = _mapping("declared camera geometry", geometry)
    fov = _number(declared, "the declared camera geometry", "horizontal_fov_rad", positive=True)
    width = _number(declared, "the declared camera geometry", "image_width_px", positive=True)
    height = _number(declared, "the declared camera geometry", "image_height_px", positive=True)
    margin = _mapping("declared safety margin", safety_margin)
    resolution = rad_per_px(horizontal_fov_rad=fov, image_width_px=width)
    low, high = _interval("motion corridor", corridor_rad)
    if type(frames_per_pose) is not int or isinstance(frames_per_pose, bool):
        raise ValueError("the document records the whole number of frames each pose was held for")

    jitter_px = max(float(result["centre_jitter_px"]) for result in measured)
    row_jitter_px = max(float(result["row_jitter_px"]) for result in measured)
    frame_count = sum(int(result["frame_count"]) for result in measured)
    pose_count = sum(int(result["pose_count"]) for result in measured)
    worst = max(
        (pose for result in measured for pose in result["poses"]),
        key=lambda pose: pose["spread_x_px"]["std"],
    )
    refusals = []
    if margin.get("refusal") is not None:
        refusals.append(
            {
                "code": margin["refusal"],
                "field": "safety_margin_px",
                "detail": margin.get("detail"),
            }
        )
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "path": None if path is None else str(path),
        "command": command,
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(measured[0]["simulation_timestep_s"]),
        "horizontal_fov_rad": fov,
        "image_width_px": width,
        "image_height_px": height,
        "centre_jitter_rad": jitter_px * resolution,
        "centre_jitter_px": jitter_px,
        "safety_margin_px": margin.get("value"),
        "angular_resolution": {
            "rad_per_px": resolution,
            "axis": JITTER_AXIS,
            "rule": ANGULAR_RESOLUTION_RULE,
            "horizontal_fov_rad": fov,
            "image_width_px": width,
        },
        "declared_fields": {
            "horizontal_fov_rad": {
                "value": fov,
                "measured_here": False,
                "declared_by": declared.get("declared_by"),
            },
            "image_width_px": {
                "value": width,
                "measured_here": False,
                "declared_by": declared.get("declared_by"),
            },
            "image_height_px": {
                "value": height,
                "measured_here": False,
                "declared_by": declared.get("declared_by"),
            },
        },
        "centre_jitter": {
            "field": "centre_jitter_rad",
            "value": jitter_px * resolution,
            "unit": "rad",
            "measured_here": True,
            "axis": JITTER_AXIS,
            "definition": JITTER_DEFINITION,
            "combination": JITTER_COMBINATION,
            "rad_per_px": resolution,
            "centre_jitter_px": jitter_px,
            "row_jitter_px": row_jitter_px,
            "row_axis_note": (
                "the row axis is recorded for review only: phase 6 applies center_deadband_px to the "
                "column, so no row angle is converted here"
            ),
            "frames_per_pose": int(frames_per_pose),
            "pose_count": pose_count,
            "frame_count": frame_count,
            "worst_pose": {
                "pose_rad": float(worst["pose_rad"]),
                "pose_kind": worst["pose_kind"],
                "std_px": float(worst["spread_x_px"]["std"]),
                "frame_count": int(worst["frame_count"]),
            },
            "anchors": [
                {
                    "anchor": result["anchor"],
                    "centre_jitter_px": float(result["centre_jitter_px"]),
                    "row_jitter_px": float(result["row_jitter_px"]),
                    "worst_pose": dict(result["worst_pose"]),
                    "poses": list(result["poses"]),
                }
                for result in measured
            ],
        },
        "safety_margin": dict(margin),
        "refusals": refusals,
        "frame_rate_hz": FRAME_RATE_HZ,
        "frame_period_s": FRAME_PERIOD_S,
        "frame_cadence": FRAME_CADENCE,
        "frames_per_pose": int(frames_per_pose),
        "frame_count": frame_count,
        "pose_count": pose_count,
        "measurements": [dict(result) for result in measured],
        "corridor_rule": CORRIDOR_RULE,
        "motion_corridor_rad": [low, high],
        "scene_path": str(scene_path),
        "scene_sha256": scene_sha256,
        "geometry_seal": _reference(
            "the sealed geometry", geometry_seal_path, geometry_seal_sha256
        ),
        "production_search_config": _reference(
            "the production search configuration",
            production_search_config_path,
            production_search_config_sha256,
        ),
        "frozen_candidate": _reference(
            "the frozen candidate", frozen_candidate_path, frozen_candidate_sha256
        ),
        "weights": _reference("the detector weights", weights_path, weights_sha256),
        "detector_operating_point": dict(detector_operating_point or {}),
        "detector_loaded": bool(detector_loaded),
        "cuda_used": bool(detector_loaded) and str(device).startswith("cuda"),
        "device": device,
        "measured_here": True,
        "tracking_measured": False,
        "tracking_detail": (
            "the frames are produced in process, so the detection identities come from the production "
            "head detector's own spatial track association over this measurement's frames and not from a "
            "running multi-object tracker across a topic"
        ),
        "transport_measured": False,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "runtime_identity": dict(
            runtime_identity_document or measured[0].get("runtime_identity") or {}
        ),
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def _anchor_pose_requests(*, seal, production, anchors, attempt_id, session_id) -> list[dict]:
    """One request per sealed anchor, with the settled poses this measurement will hold.

    The poses are the anchor's own search start - where the production search first looks at the cup - and
    the bounded plan's stop points for that anchor, which is where the search holds the neck while it
    circles the cup. Nothing else is added, and a pose the seal's corridor does not bound stops the
    measurement before the first frame is rendered.
    """

    requests = _re_raised(
        _anchor_requests,
        seal=seal,
        production=production,
        anchors=anchors,
        attempt_id=attempt_id,
        session_id=session_id,
    )
    corridor = _re_raised(motion_corridor_rad, geometry_seal=seal)
    for request in requests:
        start = float(request["search_start_rad"])
        _corridor_check(
            angle_rad=start,
            corridor_rad=corridor,
            what=f"declared search start of the anchor {request['anchor']!r}",
        )
        values = [start, *_re_raised(planned_stops, request["controller_config"])]
        poses = _pose_records(
            [
                {"pose_rad": value, "pose_kind": "anchor" if index == 0 else "plan"}
                for index, value in enumerate(values)
            ]
        )
        for pose in poses:
            _corridor_check(
                angle_rad=pose["pose_rad"],
                corridor_rad=corridor,
                what=f"planned pose of the anchor {request['anchor']!r}",
            )
        request["poses"] = poses
    return requests


def _cuda_available() -> bool:
    """Whether the declared CUDA device is really there; the measurement never falls back to the CPU."""

    import torch

    return bool(torch.cuda.is_available())
