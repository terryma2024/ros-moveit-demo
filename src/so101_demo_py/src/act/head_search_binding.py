"""Bind the admitted head search model to its measured Task 6 sample."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
import re
import stat


_MEASURED = (
    "horizontal_fov_rad", "coarse_step_rad", "search_timeout_s",
    "max_fine_corrections", "max_fine_total_rad", "min_confidence",
    "tracking_iou", "min_bbox_aspect", "center_deadband_px",
    "vertical_bounds_px", "min_area_px2", "max_age_s", "max_skew_s",
    "lock_valid_neck_rad", "submit_lead_s", "stop_velocity_rad_s",
    "stop_latency_s",
)
_CAMERA_MEASURED = (
    "head_intrinsics_px", "head_translation_m", "head_rpy_rad",
    "yaw_zero_bearing_rad",
)
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_COMMIT = re.compile(r"[0-9a-f]{40}\Z")


@dataclass(frozen=True)
class HeadSearchBinding:
    detector: dict
    camera: dict
    motion: dict
    search_values: dict

    def neck_motion_allowed(self, current_rad: float, target_rad: float) -> bool:
        """Use the measured lock interval as the neck command guard."""
        interval = self.search_values.get("lock_valid_neck_rad")
        if not _valid_neck_interval(interval):
            return False
        if any(type(value) not in (int, float) or not math.isfinite(value)
               for value in (current_rad, target_rad)):
            return False
        return all(interval[0] <= value <= interval[1]
                   for value in (current_rad, target_rad))

    def search_config(self, *, session_id: str, attempt_id: str,
                      search_start_rad: float) -> dict:
        from .search import HeadSearchController

        if not self.neck_motion_allowed(search_start_rad, search_start_rad):
            raise ValueError("HEAD_SEARCH_NECK_OUT_OF_RANGE")

        names = ("horizontal_fov_rad", "coarse_step_rad", "search_timeout_s",
                 "max_age_s", "max_skew_s", "center_deadband_px",
                 "vertical_bounds_px", "min_area_px2", "min_confidence",
                 "max_fine_corrections", "max_fine_total_rad")
        config = {name: self.search_values[name] for name in names}
        config.update(session_id=session_id, attempt_id=attempt_id,
                      search_start_rad=search_start_rad,
                      settle_velocity_rad_s=self.motion["settle_velocity_rad_s"],
                      goal_tolerance_rad=self.motion["goal_tolerance_rad"],
                      frame_id=self.camera["frame_id"],
                      ray_origin_frame_id=self.camera["ray_origin_frame_id"])
        HeadSearchController(config)
        return config


def _finite_positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _valid_neck_interval(value) -> bool:
    return (type(value) in (list, tuple) and len(value) == 2
            and all(type(item) in (int, float) and math.isfinite(item) for item in value)
            and value[0] < value[1])


def _regular_bytes(path: Path, code: str) -> bytes:
    if not path.is_absolute() or ".." in path.parts or path.is_symlink():
        raise ValueError(code)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError(code)
            return stream.read()
    except OSError as error:
        raise ValueError(code) from error


def _regular_digest(path: Path, code: str) -> str:
    return hashlib.sha256(_regular_bytes(path, code)).hexdigest()



def validate_head_search_shape(runtime: dict) -> dict:
    """The production head-search shape, in one place, so every entry enforces the same closed document.

    Astra finding 2: the measurement bundle's shared descriptor rule checked the device policy but not the document's
    shape, so a descriptor with an unknown field or a malformed camera/motion block passed a check that the production
    binding would have refused. Both paths now call this.
    """

    if type(runtime) is not dict or set(runtime) != {"schema_version", "head_search"} or runtime["schema_version"] != 1:
        raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
    descriptor = runtime["head_search"]
    if type(descriptor) is not dict or set(descriptor) != {"schema_version", "detector", "camera", "motion"}:
        raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
    for name in ("detector", "camera", "motion"):
        if type(descriptor[name]) is not dict:
            raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
    return descriptor


def validate_head_search_binding(runtime: dict, calibration: dict) -> HeadSearchBinding:
    """Fail closed before ROS or model construction on an unqualified pairing."""
    try:
        descriptor = validate_head_search_shape(runtime)
        detector, camera, motion = (descriptor[name] for name in ("detector", "camera", "motion"))
        if (type(detector) is not dict or set(detector) != {
                "backend", "weights_path", "weights_sha256", "model_id", "image_size_px",
                "requested_device", "allow_cpu_fallback", "torch_threads",
                "torch_interop_threads", "torch_version", "ultralytics_version"} or
                detector["backend"] != "yolo_seg" or
                type(detector["weights_path"]) is not str or
                type(detector["weights_sha256"]) is not str or
                _SHA.fullmatch(detector["weights_sha256"]) is None or
                type(detector["model_id"]) is not str or not detector["model_id"] or
                type(detector["image_size_px"]) is not int or detector["image_size_px"] != 640 or
                detector["requested_device"] not in ("cuda", "cpu") or
                type(detector["allow_cpu_fallback"]) is not bool or
                type(detector["torch_threads"]) is not int or
                not 1 <= detector["torch_threads"] <= 64 or
                type(detector["torch_interop_threads"]) is not int or
                not 1 <= detector["torch_interop_threads"] <= 32 or
                any(type(detector[name]) is not str or not detector[name] or
                    len(detector[name]) > 64 for name in (
                        "torch_version", "ultralytics_version"))):
            raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
        if (type(camera) is not dict or set(camera) != {
                "frame_id", "ray_origin_frame_id", "width_px", "height_px"} or
                camera["frame_id"] != "head_camera_frame" or
                camera["ray_origin_frame_id"] != "head_camera_frame" or
                type(camera["width_px"]) is not int or camera["width_px"] != 640 or
                type(camera["height_px"]) is not int or camera["height_px"] != 480):
            raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
        if (type(motion) is not dict or set(motion) != {
                "goal_tolerance_rad", "settle_velocity_rad_s", "neck_goal_duration_s"} or
                not all(_finite_positive(value) for value in motion.values()) or
                motion["goal_tolerance_rad"] > 0.1 or
                motion["settle_velocity_rad_s"] > 0.2 or
                motion["neck_goal_duration_s"] > 5):
            raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
    except (KeyError, TypeError) as error:
        raise ValueError("HEAD_SEARCH_CONFIG_INVALID") from error

    weights = Path(detector["weights_path"])
    if _regular_digest(weights, "HEAD_SEARCH_WEIGHTS_INVALID") != detector["weights_sha256"]:
        raise ValueError("HEAD_SEARCH_WEIGHTS_INVALID")
    try:
        if calibration["status"] not in ("TASK8_READY", "QUALIFIED"):
            raise ValueError("CALIBRATION_REQUIRED")
        provenance = calibration.get("source_provenance_sha256")
        if type(provenance) is not str or _SHA.fullmatch(provenance) is None:
            raise ValueError("CALIBRATION_SOURCE_PROVENANCE_MISSING")
        measurements = calibration["measurements"]
        values = {name: measurements[name]["value"] for name in _MEASURED}
        camera_values = {name: measurements[name]["value"] for name in _CAMERA_MEASURED}
        source_commit = calibration["source_commit"]
        config_sha256 = calibration["config_sha256"]
        if (type(source_commit) is not str or _COMMIT.fullmatch(source_commit) is None or
                type(config_sha256) is not str or _SHA.fullmatch(config_sha256) is None):
            raise ValueError("HEAD_SEARCH_SAMPLE_MISMATCH")
        samples = {(measurements[name]["sample_path"], measurements[name]["sample_sha256"])
                   for name in _MEASURED}
        if len(samples) != 1:
            raise ValueError("HEAD_SEARCH_SAMPLE_MISMATCH")
        sample_path, sample_sha = samples.pop()
        if type(sample_sha) is not str or _SHA.fullmatch(sample_sha) is None:
            raise ValueError("HEAD_SEARCH_SAMPLE_MISMATCH")
        sample_path = Path(sample_path)
        sample_bytes = _regular_bytes(sample_path, "HEAD_SEARCH_SAMPLE_MISMATCH")
        if hashlib.sha256(sample_bytes).hexdigest() != sample_sha:
            raise ValueError("HEAD_SEARCH_SAMPLE_MISMATCH")
        sample = json.loads(sample_bytes)
        if (type(sample) is not dict or set(sample) != {
                "schema_version", "kind", "status", "head_search", "observed_lock_frames",
                "measurements", "camera_measurements", "source_commit", "config_sha256",
                "source_provenance_sha256"} or
                sample["source_provenance_sha256"] != provenance or
                sample["schema_version"] != 1 or sample["kind"] != "head_search_qualification" or
                sample["status"] != "PASS" or sample["head_search"] != descriptor or
                sample["measurements"] != values or
                sample["camera_measurements"] != camera_values or
                sample["source_commit"] != source_commit or
                sample["config_sha256"] != config_sha256 or
                type(sample["observed_lock_frames"]) is not int or sample["observed_lock_frames"] < 3):
            raise ValueError("HEAD_SEARCH_SAMPLE_MISMATCH")
        from .search import HeadSearchController
        config = {name: values[name] for name in (
            "horizontal_fov_rad", "coarse_step_rad", "search_timeout_s",
            "max_fine_corrections", "max_fine_total_rad", "min_confidence",
            "center_deadband_px", "vertical_bounds_px", "min_area_px2",
            "max_age_s", "max_skew_s")}
        config.update({name: motion[name] for name in (
            "goal_tolerance_rad", "settle_velocity_rad_s")})
        config.update(session_id="qualification", attempt_id="qualification",
                      search_start_rad=0.0, frame_id=camera["frame_id"],
                      ray_origin_frame_id=camera["ray_origin_frame_id"])
        HeadSearchController(config)
        if (values["min_confidence"] < 0.25 or
                not 0 < values["tracking_iou"] <= 1 or
                not _finite_positive(values["min_bbox_aspect"]) or
                not _valid_neck_interval(values["lock_valid_neck_rad"]) or
                not 0 < values["max_skew_s"] <= values["max_age_s"] or
                not 0 < values["submit_lead_s"] <= 5 or
                not 0 < values["stop_latency_s"] <= 30 or
                not _finite_positive(values["stop_velocity_rad_s"])):
            raise ValueError("HEAD_SEARCH_MEASUREMENT_INVALID")
        return HeadSearchBinding(dict(detector), dict(camera), dict(motion), values)
    except (KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        raise ValueError("HEAD_SEARCH_SAMPLE_MISMATCH") from error
