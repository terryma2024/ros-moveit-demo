"""Bind the admitted head search model to its measured synchronized-capture sample."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path

_MEASURED = (
    "horizontal_fov_rad",
    "coarse_step_rad",
    "search_timeout_s",
    "max_fine_corrections",
    "max_fine_total_rad",
    "min_confidence",
    "tracking_iou",
    "min_bbox_aspect",
    "center_deadband_px",
    "vertical_bounds_px",
    "min_area_px2",
    "max_age_s",
    "max_skew_s",
    "lock_valid_neck_rad",
    "submit_lead_s",
    "stop_velocity_rad_s",
    "stop_latency_s",
)
_CAMERA_MEASURED = (
    "head_intrinsics_px",
    "head_translation_m",
    "head_rpy_rad",
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
        if any(
            type(value) not in (int, float) or not math.isfinite(value)
            for value in (current_rad, target_rad)
        ):
            return False
        return all(interval[0] <= value <= interval[1] for value in (current_rad, target_rad))

    def search_config(self, *, session_id: str, attempt_id: str, search_start_rad: float) -> dict:
        from .search import HeadSearchController

        if not self.neck_motion_allowed(search_start_rad, search_start_rad):
            raise ValueError("HEAD_SEARCH_NECK_OUT_OF_RANGE")

        names = (
            "horizontal_fov_rad",
            "coarse_step_rad",
            "search_timeout_s",
            "max_age_s",
            "max_skew_s",
            "center_deadband_px",
            "vertical_bounds_px",
            "min_area_px2",
            "min_confidence",
            "max_fine_corrections",
            "max_fine_total_rad",
        )
        config = {name: self.search_values[name] for name in names}
        config.update(
            session_id=session_id,
            attempt_id=attempt_id,
            search_start_rad=search_start_rad,
            settle_velocity_rad_s=self.motion["settle_velocity_rad_s"],
            goal_tolerance_rad=self.motion["goal_tolerance_rad"],
            frame_id=self.camera["frame_id"],
            ray_origin_frame_id=self.camera["ray_origin_frame_id"],
        )
        HeadSearchController(config)
        return config


def _finite_positive(value):
    return type(value) in (int, float) and math.isfinite(value) and value > 0


def _valid_neck_interval(value) -> bool:
    return (
        type(value) in (list, tuple)
        and len(value) == 2
        and all(type(item) in (int, float) and math.isfinite(item) for item in value)
        and value[0] < value[1]
    )


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

    the measurement bundle's shared descriptor rule checked the device policy but not the document's
    shape, so a descriptor with an unknown field or a malformed camera/motion block passed a check that the production
    binding would have refused. Both paths now call this.
    """

    if (
        type(runtime) is not dict
        or set(runtime) != {"schema_version", "head_search"}
        or runtime["schema_version"] != 1
    ):
        raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
    descriptor = runtime["head_search"]
    if type(descriptor) is not dict or set(descriptor) != {
        "schema_version",
        "detector",
        "camera",
        "motion",
    }:
        raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
    # the CONTENTS matter, not only the closed key sets. The inner version was lost when this
    # function was extracted, and empty or incomplete blocks passed a rule the production binding refused.
    if descriptor["schema_version"] != 1:
        raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
    # presence was never enough. The same closed sets, types and value bounds the
    # production binding enforced are enforced HERE, so the measurement entry - which consumes the parsed context
    # document - cannot accept a descriptor the binding would refuse. Report pairing stays in the binding.
    detector, camera, motion = (descriptor[name] for name in ("detector", "camera", "motion"))
    if (
        type(detector) is not dict
        or set(detector)
        != {
            "backend",
            "weights_path",
            "weights_sha256",
            "model_id",
            "image_size_px",
            "requested_device",
            "allow_cpu_fallback",
            "torch_threads",
            "torch_interop_threads",
            "torch_version",
            "ultralytics_version",
        }
        or detector["backend"] != "yolo_seg"
        or type(detector["weights_path"]) is not str
        or type(detector["weights_sha256"]) is not str
        or _SHA.fullmatch(detector["weights_sha256"]) is None
        or type(detector["model_id"]) is not str
        or not detector["model_id"]
        or type(detector["image_size_px"]) is not int
        or detector["image_size_px"] != 640
        or detector["requested_device"] not in ("cuda", "cpu")
        or type(detector["allow_cpu_fallback"]) is not bool
        or type(detector["torch_threads"]) is not int
        or not 1 <= detector["torch_threads"] <= 64
        or type(detector["torch_interop_threads"]) is not int
        or not 1 <= detector["torch_interop_threads"] <= 32
        or any(
            type(detector[name]) is not str or not detector[name] or len(detector[name]) > 64
            for name in ("torch_version", "ultralytics_version")
        )
    ):
        raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
    if (
        type(camera) is not dict
        or set(camera) != {"frame_id", "ray_origin_frame_id", "width_px", "height_px"}
        or camera["frame_id"] != "head_camera_frame"
        or camera["ray_origin_frame_id"] != "head_camera_frame"
        or type(camera["width_px"]) is not int
        or camera["width_px"] != 640
        or type(camera["height_px"]) is not int
        or camera["height_px"] != 480
    ):
        raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
    if (
        type(motion) is not dict
        or set(motion) != {"goal_tolerance_rad", "settle_velocity_rad_s", "neck_goal_duration_s"}
        or not all(_finite_positive(value) for value in motion.values())
        or motion["goal_tolerance_rad"] > 0.1
        or motion["settle_velocity_rad_s"] > 0.2
        or motion["neck_goal_duration_s"] > 5
    ):
        raise ValueError("HEAD_SEARCH_CONFIG_INVALID")
    return descriptor


def validate_head_search_binding(runtime: dict, calibration: dict) -> HeadSearchBinding:
    """Fail closed before ROS or model construction on an unqualified pairing.

    Two shapes reach startup: the promoted-config/qualified-report pair, which is compared value by value,
    and the older runtime/calibration shape, which keeps its own validation.
    """

    if (
        isinstance(runtime, dict)
        and isinstance(calibration, dict)
        and ("values" in runtime and "values" in calibration)
    ):
        validate_promoted_pair(runtime, calibration)
        values = dict(runtime["values"])
        return HeadSearchBinding(
            detector=_freeze(
                {
                    "weight_path": runtime.get("weight_path"),
                    "weight_sha256": runtime.get("weight_sha256"),
                    "detector_sha256": runtime.get("candidate_identity_sha256"),
                    "device": runtime.get("cuda_device"),
                    "allow_cpu_fallback": runtime.get("allow_cpu_fallback"),
                }
            ),
            camera=_freeze(runtime.get("camera") or {}),
            motion=_freeze(
                {
                    "tracker": runtime.get("tracker") or {},
                    **(runtime.get("motion") or {}),
                    "settle_velocity_rad_s": (runtime.get("motion") or {}).get(
                        "settle_velocity_rad_s", runtime["values"]["stop_velocity_rad_s"]
                    ),
                    "goal_tolerance_rad": (runtime.get("motion") or {}).get(
                        "goal_tolerance_rad", 0.05
                    ),
                }
            ),
            search_values=_freeze(values),
        )
    try:
        descriptor = validate_head_search_shape(runtime)
        detector, camera, motion = (descriptor[name] for name in ("detector", "camera", "motion"))
    except (KeyError, TypeError) as error:
        raise ValueError("HEAD_SEARCH_CONFIG_INVALID") from error

    weights = Path(detector["weights_path"])
    if _regular_digest(weights, "HEAD_SEARCH_WEIGHTS_INVALID") != detector["weights_sha256"]:
        raise ValueError("HEAD_SEARCH_WEIGHTS_INVALID")
    try:
        if calibration["status"] not in ("PICK_PLACE_CALIBRATION_READY", "QUALIFIED"):
            raise ValueError("CALIBRATION_REQUIRED")
        provenance = calibration.get("source_provenance_sha256")
        if type(provenance) is not str or _SHA.fullmatch(provenance) is None:
            raise ValueError("CALIBRATION_SOURCE_PROVENANCE_MISSING")
        measurements = calibration["measurements"]
        values = {name: measurements[name]["value"] for name in _MEASURED}
        camera_values = {name: measurements[name]["value"] for name in _CAMERA_MEASURED}
        source_commit = calibration["source_commit"]
        config_sha256 = calibration["config_sha256"]
        if (
            type(source_commit) is not str
            or _COMMIT.fullmatch(source_commit) is None
            or type(config_sha256) is not str
            or _SHA.fullmatch(config_sha256) is None
        ):
            raise ValueError("HEAD_SEARCH_SAMPLE_MISMATCH")
        samples = {
            (measurements[name]["sample_path"], measurements[name]["sample_sha256"])
            for name in _MEASURED
        }
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
        if (
            type(sample) is not dict
            or set(sample)
            != {
                "schema_version",
                "kind",
                "status",
                "head_search",
                "observed_lock_frames",
                "measurements",
                "camera_measurements",
                "source_commit",
                "config_sha256",
                "source_provenance_sha256",
            }
            or sample["source_provenance_sha256"] != provenance
            or sample["schema_version"] != 1
            or sample["kind"] != "head_search_qualification"
            or sample["status"] != "PASS"
            or sample["head_search"] != descriptor
            or sample["measurements"] != values
            or sample["camera_measurements"] != camera_values
            or sample["source_commit"] != source_commit
            or sample["config_sha256"] != config_sha256
            or type(sample["observed_lock_frames"]) is not int
            or sample["observed_lock_frames"] < 3
        ):
            raise ValueError("HEAD_SEARCH_SAMPLE_MISMATCH")
        from .search import HeadSearchController

        config = {
            name: values[name]
            for name in (
                "horizontal_fov_rad",
                "coarse_step_rad",
                "search_timeout_s",
                "max_fine_corrections",
                "max_fine_total_rad",
                "min_confidence",
                "center_deadband_px",
                "vertical_bounds_px",
                "min_area_px2",
                "max_age_s",
                "max_skew_s",
            )
        }
        config.update(
            {name: motion[name] for name in ("goal_tolerance_rad", "settle_velocity_rad_s")}
        )
        config.update(
            session_id="qualification",
            attempt_id="qualification",
            search_start_rad=0.0,
            frame_id=camera["frame_id"],
            ray_origin_frame_id=camera["ray_origin_frame_id"],
        )
        HeadSearchController(config)
        if (
            values["min_confidence"] < 0.25
            or not 0 < values["tracking_iou"] <= 1
            or not _finite_positive(values["min_bbox_aspect"])
            or not _valid_neck_interval(values["lock_valid_neck_rad"])
            or not 0 < values["max_skew_s"] <= values["max_age_s"]
            or not 0 < values["submit_lead_s"] <= 5
            or not 0 < values["stop_latency_s"] <= 30
            or not _finite_positive(values["stop_velocity_rad_s"])
        ):
            raise ValueError("HEAD_SEARCH_MEASUREMENT_INVALID")
        return HeadSearchBinding(dict(detector), dict(camera), dict(motion), values)
    except (KeyError, TypeError, OSError, json.JSONDecodeError) as error:
        raise ValueError("HEAD_SEARCH_SAMPLE_MISMATCH") from error


def validate_head_only_admission(admission):
    """Accept only admission the restricted issuer created for a head-only operation.

    The four operations are the whole surface: a release, a recorder, a retreat or a pick-place readiness probe
    cannot be smuggled in through an admission document, and a Teleop acceptance admission must be the
    Teleop head-camera one.
    """

    from collections.abc import Mapping

    from so101_demo.act.head_search_qualification import HEAD_ONLY_OPERATIONS

    if not isinstance(admission, Mapping):
        # the pick-place measurement protocol issues its own typed admission; a caller's plain object is not one
        if type(admission).__name__ == "CalibrationMeasurementAdmission":
            return admission
        raise ValueError("HEAD_ONLY_OPERATION_REFUSED: the admission is not a document")
    operation = admission.get("operation")
    if operation not in HEAD_ONLY_OPERATIONS:
        raise ValueError(
            f"HEAD_ONLY_OPERATION_REFUSED: {operation!r} is not one of {HEAD_ONLY_OPERATIONS}"
        )
    if operation == "TELEOP_ACCEPTANCE":
        if admission.get("consumer") != "teleop_head_camera":
            raise ValueError(
                "HEAD_ONLY_OPERATION_REFUSED: TELEOP_ACCEPTANCE may expose only the Teleop head camera"
            )
        return dict(admission)
    for consumer in admission.get("consumers") or ():
        if consumer not in ("head_search_controller", "teleop_head_camera"):
            raise ValueError(
                f"HEAD_ONLY_OPERATION_REFUSED: {consumer!r} is not a head-only consumer"
            )
    if admission.get("one_stack") is not True or admission.get("one_detector") is not True:
        raise ValueError(
            "HEAD_ONLY_OPERATION_REFUSED: head-only admission binds exactly one stack and one detector"
        )
    return dict(admission)


#: the seventeen fields a promoted head search config and its qualified report must agree on exactly
HEAD_SEARCH_VALUE_FIELDS = (
    "horizontal_fov_rad",
    "lock_valid_neck_rad",
    "coarse_step_rad",
    "search_timeout_s",
    "min_confidence",
    "tracking_iou",
    "min_bbox_aspect",
    "min_area_px2",
    "center_deadband_px",
    "vertical_bounds_px",
    "max_fine_corrections",
    "max_fine_total_rad",
    "max_age_s",
    "max_skew_s",
    "submit_lead_s",
    "stop_velocity_rad_s",
    "stop_latency_s",
)
#: the identities that must match between the promoted config and the qualified report
HEAD_SEARCH_IDENTITY_FIELDS = ("weight_sha256", "candidate_identity_sha256", "runtime_id")
#: the context that must match as well, so a swapped camera or tracker cannot pass on equal values alone
HEAD_SEARCH_CONTEXT_FIELDS = (
    "weight_path",
    "camera",
    "tracker",
    "motion",
    "cuda_device",
    "controlled_dependencies",
)
#: every key a promoted config or qualified report may carry; anything else is unconsumed
HEAD_SEARCH_DOCUMENT_KEYS = frozenset(
    {
        "schema_version",
        "runtime_id",
        "weight_path",
        "weight_sha256",
        "candidate_identity_sha256",
        "camera",
        "tracker",
        "motion",
        "cuda_device",
        "allow_cpu_fallback",
        "controlled_dependencies",
        "values",
        "unused_values",
    }
)


def validate_promoted_pair(config, report):
    """Fail closed before ROS or model construction when the promoted config and report disagree.

    Every one of the seventeen values is compared, not sampled, and the weight, candidate and runtime
    identities must match too: a single drifted field is enough to refuse startup.
    """

    from collections.abc import Mapping

    def refuse(what: str) -> None:
        raise ValueError(f"HEAD_SEARCH_SAMPLE_MISMATCH: {what}")

    for name, document in (("config", config), ("report", report)):
        if not isinstance(document, Mapping):
            refuse(f"the {name} is not a document")
    configured = config.get("values")
    reported = report.get("values")
    if not isinstance(configured, Mapping) or not isinstance(reported, Mapping):
        refuse("a document declares no values")
    if set(configured) != set(HEAD_SEARCH_VALUE_FIELDS):
        refuse("the promoted config does not declare exactly the seventeen values")
    if set(reported) != set(HEAD_SEARCH_VALUE_FIELDS):
        refuse("the qualified report does not declare exactly the seventeen values")
    for field in HEAD_SEARCH_VALUE_FIELDS:
        if configured[field] != reported[field]:
            refuse(f"{field} differs between the promoted config and the report")
    for field in HEAD_SEARCH_IDENTITY_FIELDS:
        if not config.get(field) or not report.get(field):
            refuse(f"{field} is missing, so an absent identity cannot pass as agreement")
        if config[field] != report[field]:
            refuse(f"{field} differs between the promoted config and the report")
    # the camera, tracker, device and dependency identities are compared too, not just the three digests
    for field in HEAD_SEARCH_CONTEXT_FIELDS:
        if not config.get(field) or not report.get(field):
            refuse(f"{field} is missing from one of the documents")
        if config[field] != report[field]:
            refuse(f"{field} differs between the promoted config and the report")
    for name, document in (("config", config), ("report", report)):
        if document.get("allow_cpu_fallback") is not False:
            raise ValueError(
                f"HEAD_SEARCH_CUDA_REQUIRED: the {name} must forbid CPU fallback explicitly"
            )
    device = str(config.get("cuda_device"))
    if not device.startswith("cuda"):
        raise ValueError(
            f"HEAD_SEARCH_CUDA_REQUIRED: the promoted config names {device!r} rather than a CUDA device"
        )
    for name, document in (("config", config), ("report", report)):
        undeclared = set(document) - HEAD_SEARCH_DOCUMENT_KEYS
        if undeclared:
            raise ValueError(
                f"HEAD_SEARCH_UNUSED_VALUE: the {name} carries unconsumed keys {sorted(undeclared)}"
            )
    unused = list(config.get("unused_values") or []) + list(report.get("unused_values") or [])
    if unused:
        raise ValueError(f"HEAD_SEARCH_UNUSED_VALUE: nothing consumes {sorted(unused)}")
    return config


def load_promoted_head_search(config_path, report_path=None):
    """Read the promoted config, and when a report is given validate the pair before construction.

    Startup calls this before it builds any ROS node, camera or model: the config alone is not proof that
    the qualified run agreed with it, so the pair is compared whenever both are present.
    """

    import json
    from pathlib import Path as _Path

    config = json.loads(_Path(config_path).read_text(encoding="utf-8"))
    if report_path is None:
        return config
    report = json.loads(_Path(report_path).read_text(encoding="utf-8"))
    validate_promoted_pair(config, report)
    return config


def _freeze(value):
    """Return a deeply immutable copy, so a bound value cannot be changed after startup agreed to it."""

    from types import MappingProxyType

    if isinstance(value, dict):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value
