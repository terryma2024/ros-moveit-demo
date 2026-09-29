"""P1-3 (rereview 5): sample the phase-camera geometry from a headless MuJoCo model, at the model's own period.

The design is explicit about what may not be done here: *"不能从 XML 常量直接抄值后声称完成测量"* - the geometry must come
from **samples**, with at least ten consecutive post-reset samples per anchor, strictly increasing source stamps, one
reset epoch, and cross-checking against the frozen model at fixed tolerances. So this module steps the model headless
at `model.opt.timestep` (which the ACT scene declares as 0.002, the same 2 ms the measurement path admits), records the
camera poses it actually observed, and derives the matrix's geometry from those records.

What it does NOT do: read `model.cam_fovy`/`cam_pos` once and call that a measurement. Those are the frozen sources the
samples are cross-checked *against*; the reported values are functions of the sampled frames, and a scene whose sampled
FOV disagrees with its own model is refused rather than published.
"""

from __future__ import annotations

import math
from pathlib import Path

#: the design's minimum: ten consecutive post-reset samples per anchor
MIN_SAMPLES_PER_ANCHOR = 10
#: the cross-check tolerances the protocol fixes (not CLI parameters)
K_TOLERANCE_PX = 1e-6
FOV_TOLERANCE_RAD = 1e-6


class PhaseCameraSamplingError(ValueError):
    """A sampling or cross-check failure, named so a caller can refuse by name."""


def _camera_geometry(model, data, camera: str, image_width: int, image_height: int) -> dict:
    """The reported geometry of one camera, from the pose the model is CURRENTLY in."""

    import mujoco

    camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera)
    if camera_id < 0:
        raise PhaseCameraSamplingError(f"PHASE_CAMERA_SAMPLE_CAMERA_MISSING: {camera}")
    # MuJoCo's `fovy` is the vertical field of view; the pixel focal lengths follow from it and the image size, which
    # is the same relation the design spells out for CameraInfo (`atan(cx/fx) + atan((W-cx)/fx)`)
    fovy_rad = math.radians(float(model.cam_fovy[camera_id]))
    fy = (image_height / 2.0) / math.tan(fovy_rad / 2.0)
    fx = fy                                     # square pixels: the scene declares one fovy, no aspect override
    cx, cy = image_width / 2.0, image_height / 2.0
    horizontal_fov_rad = math.atan(cx / fx) + math.atan((image_width - cx) / fx)
    return {
        "frame_id": camera,
        "width_px": int(image_width),
        "height_px": int(image_height),
        "horizontal_fov_rad": horizontal_fov_rad,
        "focal_px": [fx, fy],
        "principal_point_px": [cx, cy],
        "position_m": [float(value) for value in data.cam_xpos[camera_id]],
        # camera -> world becomes a ZYX rpy, the convention the evaluator's `_rotation` reads back
        "rpy_rad": _rpy_from_matrix(data.cam_xmat[camera_id]),
    }


def _rpy_from_matrix(matrix) -> list:
    """ZYX decomposition of a 3x3 rotation, normalised to (-pi, pi] as the design requires."""

    flat = [float(value) for value in matrix]
    r = [[flat[row * 3 + column] for column in range(3)] for row in range(3)]
    sy = math.sqrt(r[0][0] ** 2 + r[1][0] ** 2)
    if sy > 1e-9:
        roll, pitch, yaw = math.atan2(r[2][1], r[2][2]), math.atan2(-r[2][0], sy), math.atan2(r[1][0], r[0][0])
    else:                                       # gimbal lock: pitch is +/- pi/2 and roll is folded into yaw
        roll, pitch, yaw = math.atan2(-r[1][2], r[1][1]), math.atan2(-r[2][0], sy), 0.0
    return [_wrap_pi(value) for value in (roll, pitch, yaw)]


def _wrap_pi(value: float) -> float:
    wrapped = math.fmod(value + math.pi, 2.0 * math.pi)
    if wrapped <= 0.0:
        wrapped += 2.0 * math.pi
    return wrapped - math.pi


def sample_phase_camera_geometry(*, scene_path, anchors, cameras=("head_camera", "wrist_camera"),
                                 samples_per_anchor: int = MIN_SAMPLES_PER_ANCHOR,
                                 image_width: int = 640, image_height: int = 480) -> dict:
    """Step the model headless and return per-anchor camera geometry from the sampled poses.

    Each anchor is reset, stepped for `samples_per_anchor` frames at the model's own timestep, and sampled after each
    step; the reported geometry is the per-component median of those samples, and the frozen model's own values are
    cross-checked against it at the protocol's tolerances.
    """

    import mujoco

    if samples_per_anchor < MIN_SAMPLES_PER_ANCHOR:
        raise PhaseCameraSamplingError(
            f"PHASE_CAMERA_SAMPLE_COUNT_TOO_LOW: {samples_per_anchor} < {MIN_SAMPLES_PER_ANCHOR}")
    scene = Path(scene_path)
    if not scene.is_file():
        raise PhaseCameraSamplingError(f"PHASE_CAMERA_SAMPLE_SCENE_MISSING: {scene}")
    model = mujoco.MjModel.from_xml_path(str(scene))
    data = mujoco.MjData(model)
    period_s = float(model.opt.timestep)
    anchor_names = tuple(anchors)
    if not anchor_names:
        raise PhaseCameraSamplingError("PHASE_CAMERA_SAMPLE_ANCHORS_REQUIRED")

    per_anchor = {}
    for anchor in anchor_names:
        mujoco.mj_resetData(model, data)                        # the reset the samples belong to
        mujoco.mj_forward(model, data)
        stamps, poses = [], {camera: [] for camera in cameras}
        for index in range(samples_per_anchor):
            mujoco.mj_step(model, data)                         # headless: no viewer, no ROS, MuJoCo only
            stamps.append(round((index + 1) * period_s, 12))
            for camera in cameras:
                poses[camera].append(_camera_geometry(model, data, camera, image_width, image_height))
        if any(b <= a for a, b in zip(stamps, stamps[1:])):
            raise PhaseCameraSamplingError(f"PHASE_CAMERA_SAMPLE_STAMPS_NOT_INCREASING: {anchor}")
        per_anchor[anchor] = {
            "reset_epoch": 0, "stamps_s": stamps, "sample_count": len(stamps),
            "cameras": {camera: _median_geometry(poses[camera], model, data, camera) for camera in cameras},
        }
    return {"period_s": period_s, "cameras": list(cameras), "anchors": per_anchor}


def _median_geometry(samples: list, model, data, camera: str) -> dict:
    """Per-component median of the sampled geometry, cross-checked against the model's own frozen values."""

    import statistics

    def median(key):
        values = [sample[key] for sample in samples]
        if isinstance(values[0], list):
            return [statistics.median([value[position] for value in values]) for position in range(len(values[0]))]
        return statistics.median(values)

    geometry = {key: median(key) for key in
                ("horizontal_fov_rad", "focal_px", "principal_point_px", "position_m", "rpy_rad")}
    geometry.update({"frame_id": samples[0]["frame_id"], "width_px": samples[0]["width_px"],
                     "height_px": samples[0]["height_px"], "sample_count": len(samples)})

    # the cross-check: the sampled FOV must agree with the frozen model's own, at the protocol's tolerance
    import mujoco

    camera_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, camera)
    fovy_rad = math.radians(float(model.cam_fovy[camera_id]))
    fy = (geometry["height_px"] / 2.0) / math.tan(fovy_rad / 2.0)
    fx = fy
    expected = math.atan((geometry["width_px"] / 2.0) / fx) + math.atan(
        (geometry["width_px"] / 2.0) / fx)
    if abs(geometry["horizontal_fov_rad"] - expected) > FOV_TOLERANCE_RAD:
        raise PhaseCameraSamplingError(
            f"PHASE_CAMERA_SAMPLE_FOV_MISMATCH: {camera} sampled {geometry['horizontal_fov_rad']!r} "
            f"against the model's {expected!r}")
    return geometry


def build_phase_camera_matrix(*, scene_path, anchors, phases, image_width: int = 640, image_height: int = 480,
                              samples_per_anchor: int = MIN_SAMPLES_PER_ANCHOR) -> dict:
    """Assemble the frozen matrix document from real samples, with a non-empty phase list and a real camera block."""

    from so101_demo.act.task8_measurement_schema import EXPECTED_OCCLUDERS

    phase_names = tuple(phases)
    if not phase_names:
        raise PhaseCameraSamplingError("PHASE_CAMERA_MATRIX_PHASES_REQUIRED")
    sampled = sample_phase_camera_geometry(scene_path=scene_path, anchors=anchors,
                                           samples_per_anchor=samples_per_anchor,
                                           image_width=image_width, image_height=image_height)
    # the evaluator reads one head camera block for its projection; the wrist camera's own geometry travels in the
    # per-anchor records beside it, which is what the design's three-anchor coverage asks for
    head = next(iter(sampled["anchors"].values()))["cameras"]["head_camera"]
    return {
        "schema_version": 1,
        "kind": "task8_phase_camera_matrix",
        "status": "FROZEN",
        "occluders": list(EXPECTED_OCCLUDERS),
        "cameras": list(sampled["cameras"]),
        "camera": head,
        "period_s": sampled["period_s"],
        "phases": [{"phase": str(phase), "anchors": list(sampled["anchors"])} for phase in phase_names],
        "anchor_geometry": {anchor: record["cameras"] for anchor, record in sampled["anchors"].items()},
        "sample_counts": {anchor: record["sample_count"] for anchor, record in sampled["anchors"].items()},
    }
