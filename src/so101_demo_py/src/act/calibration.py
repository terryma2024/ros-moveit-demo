"""Measured, content-bound calibration is required before data collection."""

import hashlib
from pathlib import Path
import re

from .contracts import fields, finite, integer, sha256, vector

REQUIRED_CHECKS = frozenset(("fov", "collision", "search", "synchronization", "execution", "release", "retreat"))
REQUIRED_MEASUREMENTS = {
    "head_translation_m": ("m", 3), "head_rpy_rad": ("rad", 3),
    "wrist_translation_m": ("m", 3), "wrist_rpy_rad": ("rad", 3),
    "head_intrinsics_px": ("px", 4), "wrist_intrinsics_px": ("px", 4),
    "yaw_zero_bearing_rad": ("rad", 1), "horizontal_fov_rad": ("rad", 1),
    "coarse_step_rad": ("rad", 1), "search_timeout_s": ("s", 1),
    "max_fine_corrections": ("count", 1), "max_fine_total_rad": ("rad", 1),
    "min_confidence": ("1", 1), "tracking_iou": ("1", 1), "min_bbox_aspect": ("1", 1),
    "center_deadband_px": ("px", 1), "vertical_bounds_px": ("px", 2),
    "min_area_px2": ("px^2", 1), "lock_valid_neck_rad": ("rad", 2),
    "velocity_limit_rad_s": ("rad/s", 6), "acceleration_limit_rad_s2": ("rad/s^2", 6),
    "max_age_s": ("s", 1), "max_skew_s": ("s", 1),
    "grasp_occlusion_window_s": ("s", 1), "submit_lead_s": ("s", 1),
    "stop_velocity_rad_s": ("rad/s", 1), "stop_latency_s": ("s", 1),
    "support_distance_m": ("m", 1), "release_stable_s": ("s", 1),
    "retreat_distance_m": ("m", 1), "placement_stable_s": ("s", 1),
    "path_step_s": ("s", 1), "path_clearance_m": ("m", 1),
}


def require_qualified(report):
    fields(report, ("schema_version", "status", "source_commit", "config_sha256", "measurements", "checks"))
    if (report["schema_version"] != 1 or isinstance(report["schema_version"], bool)
            or report["status"] != "QUALIFIED"
            or not isinstance(report["source_commit"], str)
            or re.fullmatch(r"[0-9a-f]{40}", report["source_commit"]) is None):
        raise ValueError("CALIBRATION_REQUIRED")
    sha256(report["config_sha256"])
    fields(report["checks"], REQUIRED_CHECKS)
    if any(value != "PASS" for value in report["checks"].values()):
        raise ValueError("CALIBRATION_REQUIRED")
    fields(report["measurements"], REQUIRED_MEASUREMENTS)
    for name, (unit, size) in REQUIRED_MEASUREMENTS.items():
        item = report["measurements"][name]
        fields(item, ("value", "unit", "sample_path", "sample_sha256"))
        if item["unit"] != unit:
            raise ValueError("CALIBRATION_UNIT_INVALID")
        if size == 1:
            finite(item["value"])
        else:
            vector(item["value"], size)
        if unit == "count": integer(item["value"], minimum=1)
        if name in ("min_confidence", "tracking_iou") and not 0 < item["value"] <= 1:
            raise ValueError("CALIBRATION_RANGE_INVALID")
        if not isinstance(item["sample_path"], str):
            raise ValueError("CALIBRATION_SAMPLE_INVALID")
        path = Path(item["sample_path"])
        if not path.is_absolute() or path.is_symlink() or not path.is_file():
            raise ValueError("CALIBRATION_SAMPLE_INVALID")
        sha256(item["sample_sha256"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != item["sample_sha256"]:
            raise ValueError("CALIBRATION_SAMPLE_HASH_INVALID")
