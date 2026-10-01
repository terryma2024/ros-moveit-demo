"""The installed producer of the run's `--bundle-inputs`: the declared blocks and their live readback.

Phase 8 collects the seventeen parameters from four phases. Phases 6 and 7 measure theirs in the run;
phases 2 and 3 carry theirs in the run's declared bundle inputs, each with the evidence block design
section 7.1 requires - value, unit, selection formula, input evidence with its SHA256, the observed
distribution, the safety margin, the production owner and the startup readback. This module produces those
six blocks from documents the run also declares, and it does not restate their values: it **constructs the
production components with the recorded values and records what it observes**

* the installed `HeadSearchController`, built with the recorded `horizontal_fov_rad`,
  `lock_valid_neck_rad`, `min_confidence` and `min_area_px2` - the field of view and the safe interval are
  read back off the bounded stop plan it builds, the confidence and the area floor off the configuration
  it validates and stores, and the three-consecutive-frame lock rule is *observed behaviourally* by
  driving the constructed controller until it locks;
* the production detector of the running search - `HeadRgbDetector` over `YoloSegDetector`, the same
  adapter the closed-loop flights use - built on the selected model's weights, whose digest the frozen
  candidate document seals, from which the observed `tracking_iou` and `min_bbox_aspect` are read.

A readback that cannot be taken is recorded as `verified: false` with its reason and the exception, never
as an observed value; and a value the production owner *refuses* stops the producer, because a bundle
whose running system cannot use the value is not a bundle this run may record.

The identity of the running system is read the same way: the package prefix, the console script, the
torch/ultralytics/CUDA/driver versions, the MuJoCo version, the tracker implementation and the installed
teleop web bundle are read from the process and the install tree, and the camera identity and intrinsics
digest are read from the sealed geometry and cross-checked against the declared production camera.

Nothing here commands motion, starts ROS or a simulator, and nothing is written unless the caller passes
an explicit `output_dir`; the two documents named below are the only files this module creates.
"""

from __future__ import annotations

import hashlib
import json
import math
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

from so101_demo.act.head_search_calibration_bundle import (
    ALSO_RECORDED_ITEMS,
    ALSO_RECORDED_KEYS,
    EVIDENCE_REFERENCE_KEYS,
    PARAMETER_EVIDENCE_KEYS,
    RUNTIME_IDENTITY_FIELDS,
)
from so101_demo.act.head_search_calibration_geometry import read_geometry_document
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
KIND = "head_search_calibration_bundle_inputs"
RECEIPT_KIND = "head_search_calibration_bundle_inputs_receipt"
PHASE = "bundle_inputs"

#: the two documents this producer owns
BUNDLE_INPUTS_NAME = "bundle-inputs.json"
RECEIPT_NAME = "bundle-inputs-receipt.json"
ARTIFACT_NAMES = (BUNDLE_INPUTS_NAME, RECEIPT_NAME)

#: the four owning phases of the seventeen, and the two this producer declares the evidence for
GEOMETRY_PHASE = "geometry_coverage"
PERCEPTION_PHASE = "perception_operating_point"
GEOMETRY_PARAMETERS = ("horizontal_fov_rad", "lock_valid_neck_rad")
PERCEPTION_PARAMETERS = ("min_confidence", "tracking_iou", "min_bbox_aspect", "min_area_px2")
DECLARED_PARAMETERS = GEOMETRY_PARAMETERS + PERCEPTION_PARAMETERS

#: the four also-recorded items this producer declares; the fifth - the 10 Hz frame contract - is phase
#: 7's, and declaring it here would make a measured item a declared one
ALSO_RECORDED_DECLARED = (
    "settle_velocity_rad_s",
    "goal_tolerance_rad",
    "three_consecutive_frame_lock_rule",
    "tracker_algorithm",
)
FRAME_CONTRACT_ITEM = "frame_contract_10_hz"

#: this producer refuses a declaration it cannot turn into a complete, observed set of blocks
CAL_BUNDLE_INPUTS_INCOMPLETE = "CAL_BUNDLE_INPUTS_INCOMPLETE"

#: the device policy of the production search: CUDA, never a CPU fallback
DEFAULT_DEVICE = "cuda"
#: the production detector's input size, exactly as the closed-loop flights construct it
DETECTOR_IMAGE_SIZE_PX = 640
#: the declared frame contract is 10 Hz (phase 7 measures it), so the behavioural lock probe ticks its
#: frames at that cadence. Stepping the wall clock by a whole second per tick times the constructed
#: controller out on its own `search_timeout_s` for any calibrated budget below two seconds, and the
#: probe reports SEARCH_TIMEOUT instead of observing the rule it exists to observe.
LOCK_RULE_FRAME_PERIOD_S = 0.1
#: the detector's model label when the production configuration declares no `runtime_id`
DETECTOR_MODEL_ID = "head-search-bundle-inputs-readback"
#: the installed detector adapter the running search composes
DETECTOR_MODULE = "so101_demo.adapters.act.detector"
TRACKER_CLASS = "HeadRgbDetector"

#: the identity the readback's controller is constructed under; it is not a flight, so it is not a
#: generation, and the receipt records it as the readback identity
DEFAULT_READBACK_IDENTITY = "bundle-inputs-readback"

UNITS = {
    "horizontal_fov_rad": "rad",
    "lock_valid_neck_rad": "rad",
    "min_confidence": "probability",
    "tracking_iou": "probability (IoU)",
    "min_bbox_aspect": "ratio (height/width)",
    "min_area_px2": "px^2",
}

#: the installed owner of each value, named as the running system reads it
PRODUCTION_OWNERS = {
    "horizontal_fov_rad": (
        "so101_demo.act.search.HeadSearchController: config['horizontal_fov_rad'], carried into the "
        "bounded stop plan's horizontal_fov_rad"
    ),
    "lock_valid_neck_rad": (
        "so101_demo.act.search.HeadSearchController: config['lock_valid_neck_rad'], carried into "
        "SearchStopPlan.safe_interval_rad"
    ),
    "min_confidence": (
        "so101_demo.act.search.HeadSearchController.tick: a detection is a candidate only when "
        "confidence >= config['min_confidence']"
    ),
    "min_area_px2": (
        "so101_demo.act.search.HeadSearchController.tick: a detection is a candidate only when "
        "(x2-x1)*(y2-y1) >= config['min_area_px2']"
    ),
    "tracking_iou": (
        "so101_demo.adapters.act.detector.HeadRgbDetector.detect: a track is inherited only when the "
        "candidate's overlap with it is >= tracking_iou"
    ),
    "min_bbox_aspect": (
        "so101_demo.adapters.act.detector.HeadRgbDetector.detect: a candidate is kept only when "
        "(y2-y1)/(x2-x1) >= min_bbox_aspect"
    ),
}

#: the design's own wording for the two geometry values (design section 7.1)
GEOMETRY_FORMULAS = {
    "horizontal_fov_rad": (
        "the horizontal field of view computed from the production CameraInfo as the angle between the "
        "left and right image edges, taken as the conservative minimum over the valid frames, and "
        "required to agree with the MuJoCo camera definition within tolerance; here "
        "2*atan(tan(fovy_rad/2) * width_px / height_px) over the sealed camera"
    ),
    "lock_valid_neck_rad": (
        "collision and clearance checked on a closed 0.002 rad grid over [-2*pi, 2*pi] for every declared "
        "anchor, the state boundaries bisected to 1e-5 rad, taking the unique safe connected interval that "
        "contains the zero position and the anchors' start angles, with both endpoints shrunk inward by "
        "1e-5 rad"
    ),
}

#: the three-frame rule and the tracker algorithm, as the installed code implements them
LOCK_RULE_DEFINITION = (
    "three consecutive frames whose detection centre is within center_deadband_px of the camera's "
    "principal axis column and whose vertical centre lies inside vertical_bounds_px lock the target; any "
    "other frame resets the counter (so a frame outside the deadband cannot contribute)"
)
TRACKER_DEFINITION = (
    "greedy IoU track association in so101_demo.adapters.act.detector.HeadRgbDetector: candidates are "
    "matched to the previous frame's tracks by descending overlap, a match is inherited only above "
    "tracking_iou, and the sealed production configuration's declared tracker.name ('bytetrack') is NOT "
    "the algorithm this installed production path runs"
)

_CONTROLLER_MODULE = "so101_demo.act.search"


class CalibrationBundleInputsRefused(CalibrationInputsRefused):
    """A producer refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _refuse(detail: str) -> CalibrationBundleInputsRefused:
    return CalibrationBundleInputsRefused(CAL_BUNDLE_INPUTS_INCOMPLETE, detail)


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _digest(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _read_json(path) -> Mapping:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(document, Mapping):
        raise _refuse(f"{path} is not a JSON object")
    return document


def _declared(where: str, document: Mapping, name: str):
    if name not in document:
        raise _refuse(f"{where} declares no {name}")
    return document[name]


def _evidence(*references) -> list:
    """One input-evidence list: every reference names a file and the digest it was read at."""

    evidence = []
    for path in references:
        if path is None:
            continue
        evidence.append({"path": str(path), "sha256": _digest(path)})
    if not evidence:
        raise _refuse("a parameter block would carry no input evidence at all")
    return evidence


def _geometry_block(*, name, value, geometry_document, references, readback) -> dict:
    camera = geometry_document.get("camera") or {}
    matrix = geometry_document.get("in_frame_matrix") or {}
    fovy = camera.get("fovy_rad")
    width = camera.get("width")
    height = camera.get("height")
    derived = (
        2.0 * math.atan(math.tan(float(fovy) / 2.0) * float(width) / float(height))
        if all(_finite(item) for item in (fovy, width, height)) and fovy and width and height
        else None
    )
    anchors = geometry_document.get("anchors") or []
    if name == "horizontal_fov_rad":
        distribution = {
            "derivation": "2*atan(tan(fovy_rad/2) * width_px / height_px) over the sealed camera",
            "derived_rad": derived,
            "sealed_rad": float(value),
            "camera_name": geometry_document.get("camera_name"),
            "width_px": width,
            "height_px": height,
            "valid_frames": [
                {"anchor": anchor, "neck_start_rad": entry.get("neck_start_rad"),
                 "samples": len(entry.get("samples") or [])}
                for anchor, entry in sorted(matrix.items())
                if isinstance(entry, Mapping)
            ],
            "invalid_frames": list(geometry_document.get("in_frame_failures") or []),
        }
        margin = {
            "derived_from_camera_intrinsics_rad": derived,
            "difference_rad": None if derived is None else abs(derived - float(value)),
            "every_valid_frame_stayed_in_frame": not geometry_document.get("in_frame_failures"),
        }
    else:
        low, high = (float(bound) for bound in value)
        domain = [float(item) for item in geometry_document.get("required_search_domain_rad", [])]
        distribution = {
            "anchors": list(anchors),
            "in_frame_matrix": {
                anchor: {
                    "neck_start_rad": entry.get("neck_start_rad"),
                    "centre_angle_rad": entry.get("centre_angle_rad"),
                    "out_of_frame_rad": list(entry.get("out_of_frame_rad") or []),
                }
                for anchor, entry in sorted(matrix.items())
                if isinstance(entry, Mapping)
            },
            "validation_arm_rad": list(geometry_document.get("validation_arm_rad") or []),
            "support_height_m": geometry_document.get("support_height_m"),
            "required_search_domain_rad": domain,
            "safe_interval_contains_required_domain": geometry_document.get(
                "safe_interval_contains_required_domain"
            ),
            "fov_union_covers_required_domain": geometry_document.get(
                "fov_union_covers_required_domain"
            ),
            "invalid_frames": list(geometry_document.get("in_frame_failures") or []),
        }
        margin = {
            "endpoint_inset_rad": 2.0 * math.pi - max(abs(low), abs(high)),
            "domain_margin_low_rad": (domain[0] - low) if len(domain) == 2 else None,
            "domain_margin_high_rad": (high - domain[1]) if len(domain) == 2 else None,
            "grid_step_rad": 0.002,
            "bisection_tolerance_rad": 1e-05,
        }
    return {
        "value": value,
        "unit": UNITS[name],
        "selection_formula": GEOMETRY_FORMULAS[name],
        "input_evidence": _evidence(*references),
        "observed_distribution": distribution,
        "safety_margin": margin,
        "production_owner": PRODUCTION_OWNERS[name],
        "startup_readback": readback,
    }


def _perception_block(*, name, value, operating_point, production_config, references, readback) -> dict:
    cell = operating_point.get("chosen_cell") or {}
    grid = [
        {
            "grid_index": entry.get("grid_index"),
            "min_confidence": (entry.get("point") or {}).get("min_confidence"),
            "tracking_iou": (entry.get("point") or {}).get("tracking_iou"),
            "min_bbox_aspect": (entry.get("point") or {}).get("min_bbox_aspect"),
            "min_area_px2": (entry.get("point") or {}).get("min_area_px2"),
            "f1": entry.get("f1"),
            "recall": entry.get("recall"),
            "precision": entry.get("precision"),
            "false_positive": entry.get("false_positive"),
            "false_negative": entry.get("false_negative"),
        }
        for entry in operating_point.get("grid") or []
        if isinstance(entry, Mapping)
    ]
    values = production_config.get("values") or {}
    sealed_value = values.get(name)
    frozen = operating_point.get("frozen_declaration") or {}
    distribution = {
        "searched_grid": grid,
        "grid_sha256": operating_point.get("grid_sha256"),
        "chosen_index": operating_point.get("chosen_index"),
        "selection_splits": list(operating_point.get("rule", {}).get("selection_splits") or []),
        "measurements_consumed": dict(operating_point.get("measurements_consumed") or {}),
        "split_isolation": dict(operating_point.get("split_isolation") or {}),
        "chosen_cell_splits": dict(cell.get("splits") or {}),
        "chosen_cell": {
            "frame_count": cell.get("frame_count"),
            "detections_kept": cell.get("detections_kept"),
            "frames_checked": cell.get("frames_checked"),
            "detections_without_geometry": cell.get("detections_without_geometry"),
        },
    }
    margin = {
        "false_positive": cell.get("false_positive"),
        "false_negative": cell.get("false_negative"),
        "precision": cell.get("precision"),
        "recall": cell.get("recall"),
        "f1": cell.get("f1"),
        "bbox_center_p95_px": cell.get("bbox_center_p95_px"),
        "no_cup_false_candidates": (operating_point.get("no_cup_guard") or {}).get(
            "no_cup_false_candidates"
        ),
        "no_cup_frames_checked": (operating_point.get("no_cup_guard") or {}).get("frames_checked"),
        "clean_on_empty_scenes": cell.get("clean_on_empty_scenes"),
        "frozen_candidate_declares_it": frozen.get(name, {}).get("declared"),
        "frozen_candidate_value": frozen.get(name, {}).get("value"),
        "sealed_production_value": sealed_value,
        "agrees_with_sealed_production_value": None if sealed_value is None else sealed_value == value,
    }
    formula = str(operating_point.get("selection_rule") or "")
    if name in ("min_confidence", "tracking_iou"):
        formula = (
            f"{formula} The value is the chosen point's {name}; the frozen candidate document seals it, "
            "and the gate applies it."
        )
    else:
        formula = (
            f"{formula} {name} is not searched: every point of the declared grid fixes it, which is why "
            "the rule's choice carries it unchanged."
        )
    return {
        "value": value,
        "unit": UNITS[name],
        "selection_formula": formula,
        "input_evidence": _evidence(*references),
        "observed_distribution": distribution,
        "safety_margin": margin,
        "production_owner": PRODUCTION_OWNERS[name],
        "startup_readback": readback,
    }


def _readback_configuration(*, production_config, geometry, values, identity) -> dict:
    """The flat configuration the installed controller is constructed with, at the recorded values."""

    configuration = {
        name: (values[name] if name in values else (production_config["values"])[name])
        for name in (
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
    }
    configuration["horizontal_fov_rad"] = values["horizontal_fov_rad"]
    configuration["lock_valid_neck_rad"] = list(values["lock_valid_neck_rad"])
    configuration["required_search_domain_rad"] = list(geometry["required_search_domain_rad"])
    configuration["settle_velocity_rad_s"] = production_config["motion"]["settle_velocity_rad_s"]
    configuration["goal_tolerance_rad"] = production_config["motion"]["goal_tolerance_rad"]
    configuration["frame_id"] = production_config["camera"]["frame_id"]
    configuration["ray_origin_frame_id"] = production_config["camera"]["ray_origin_frame_id"]
    configuration["session_id"] = identity
    configuration["attempt_id"] = identity
    configuration["search_start_rad"] = 0.0
    return configuration


def _controller_readback(configuration, *, controller_factory=None) -> tuple[dict, dict]:
    """Construct the installed controller with the recorded values and read them off the object."""

    if controller_factory is None:
        from so101_demo.act.search import HeadSearchController

        controller_factory = HeadSearchController
    try:
        controller = controller_factory(dict(configuration))
    except (KeyError, TypeError, ValueError) as error:
        raise _refuse(
            f"the installed controller refuses the recorded values: {type(error).__name__}: {error}"
        ) from error
    plan = controller.plan
    if plan is None:
        raise _refuse(
            "the installed controller exposes the cumulative 2*pi sweep for the recorded values, so no "
            "bounded stop plan can be read back"
        )
    observed = {
        "horizontal_fov_rad": float(plan.horizontal_fov_rad),
        "lock_valid_neck_rad": [float(bound) for bound in plan.safe_interval_rad],
        "min_confidence": controller.config["min_confidence"],
        "min_area_px2": controller.config["min_area_px2"],
    }
    return controller, {
        "module": _CONTROLLER_MODULE,
        "configuration": dict(configuration),
        "configuration_sha256": canonical_sha256(configuration),
        "observed": observed,
        "bounded_plan": {
            "coverage_complete": bool(plan.coverage_complete),
            "targets_rad": [float(target) for target in plan.targets_rad],
            "safe_interval_rad": [float(bound) for bound in plan.safe_interval_rad],
            "required_domain_rad": [float(bound) for bound in plan.required_domain_rad],
            "horizontal_fov_rad": float(plan.horizontal_fov_rad),
            "coarse_step_rad": float(plan.coarse_step_rad),
            "anchor_rad": float(plan.anchor_rad),
        },
    }


def _frame(*, configuration, centre_px, stamp_s, received_wall_s) -> dict:
    half = 10.0
    cx, cy = centre_px
    return {
        "session_id": configuration["session_id"],
        "attempt_id": configuration["attempt_id"],
        "frame_id": configuration["frame_id"],
        "sim_time_s": stamp_s,
        "received_wall_s": received_wall_s,
        "k": [600.0, 0.0, 320.0, 0.0, 600.0, 240.0, 0.0, 0.0, 1.0],
        "distortion": [0.0, 0.0, 0.0, 0.0, 0.0],
        # the controller's own contract takes a right-handed 3x3 rotation, not a flat nine-vector, and
        # the optical axis has to leave the image plane: this is the head camera's own optical-to-base
        # rotation, whose third column carries the optical axis into the base frame's -y
        "rotation_optical_to_base": [[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]],
        "detections": [
            {
                "xyxy": [cx - half, cy - half, cx + half, cy + half],
                "confidence": 0.9,
                "class_id": 0,
                "track_id": "head-cup-0",
            }
        ],
    }


def _feedback(*, configuration, stamp_s, received_wall_s) -> dict:
    return {
        "session_id": configuration["session_id"],
        "attempt_id": configuration["attempt_id"],
        "sim_time_s": stamp_s,
        "received_wall_s": received_wall_s,
        "neck_yaw_rad": configuration["search_start_rad"],
        "neck_velocity_rad_s": 0.0,
        "safe_observe": True,
    }


def _ticks(configuration, *, offsets_px, controller_factory=None) -> list:
    if controller_factory is None:
        from so101_demo.act.search import HeadSearchController

        controller_factory = HeadSearchController
    controller = controller_factory(dict(configuration))
    results = []
    for index, offset in enumerate(offsets_px):
        stamp = 1.0 + LOCK_RULE_FRAME_PERIOD_S * index
        now_wall_s = 100.0 + LOCK_RULE_FRAME_PERIOD_S * index
        results.append(
            controller.tick(
                _frame(
                    configuration=configuration,
                    centre_px=(320.0 + offset, 240.0),
                    stamp_s=stamp,
                    received_wall_s=now_wall_s,
                ),
                _feedback(configuration=configuration, stamp_s=stamp, received_wall_s=now_wall_s),
                now_wall_s,
            )
        )
    return results


def _lock_rule_readback(configuration, *, controller_factory=None) -> dict:
    """Observe the three-consecutive-frame rule by driving the constructed controller until it locks."""

    offsets = [2.0, 2.0, 2.0]
    results = _ticks(configuration, offsets_px=offsets, controller_factory=controller_factory)
    locked = [index + 1 for index, result in enumerate(results) if result.get("found") is True]
    two = _ticks(configuration, offsets_px=[2.0, 2.0], controller_factory=controller_factory)
    interrupted = _ticks(
        configuration, offsets_px=[2.0, 2.0, 25.0, 2.0, 2.0], controller_factory=controller_factory
    )
    return {
        "observation": "behavioural",
        "ticks_to_lock": locked[0] if locked else None,
        "status_after_three_ticks": results[-1].get("status"),
        "locked_after_two_ticks": any(result.get("found") is True for result in two),
        "locked_with_one_frame_outside_the_deadband": any(
            result.get("found") is True for result in interrupted
        ),
        "deadband_px": configuration["center_deadband_px"],
        "vertical_bounds_px": configuration["vertical_bounds_px"],
    }


def _detector_readback(
    *,
    production_config,
    values,
    weights,
    frozen_candidate,
    device,
    snapshot_root,
    detector_builder=None,
) -> tuple[dict, dict]:
    """Construct the production detector on the selected model and read the two values off it.

    The composition is the running search's own: `build_bound_head_detector` loads the admitted model
    from a verified private snapshot of the declared weights and wraps it in `HeadRgbDetector`, which
    reads `tracking_iou` and `min_bbox_aspect` from the binding it was handed. The observed values are
    therefore read off the object whose `detect` applies them.
    """

    import torch
    import ultralytics

    from so101_demo.act.head_search_binding import HeadSearchBinding

    if detector_builder is None:
        from so101_demo.adapters.act.detector import build_bound_head_detector

        detector_builder = build_bound_head_detector
    model_id = str(production_config.get("runtime_id") or DETECTOR_MODEL_ID)
    weight_sha256 = frozen_candidate["weight_sha256"]
    camera = production_config["camera"]
    motion = production_config["motion"]
    binding = HeadSearchBinding(
        detector={
            "backend": "yolo_seg",
            "weights_path": str(weights),
            "weights_sha256": weight_sha256,
            "model_id": model_id,
            "image_size_px": DETECTOR_IMAGE_SIZE_PX,
            "requested_device": device,
            "allow_cpu_fallback": False,
            "torch_threads": int(torch.get_num_threads()),
            "torch_interop_threads": int(torch.get_num_interop_threads()),
            "torch_version": str(torch.__version__),
            "ultralytics_version": str(ultralytics.__version__),
        },
        camera={
            "frame_id": camera["frame_id"],
            "ray_origin_frame_id": camera["ray_origin_frame_id"],
            "width_px": int(camera["width"]),
            "height_px": int(camera["height"]),
        },
        motion={
            "tracker": dict(production_config.get("tracker") or {}),
            "goal_tolerance_rad": motion["goal_tolerance_rad"],
            "settle_velocity_rad_s": motion["settle_velocity_rad_s"],
        },
        search_values={**dict(production_config["values"]), **{
            name: values[name] for name in DECLARED_PARAMETERS
        }},
    )
    built = detector_builder(binding, snapshot_root=Path(snapshot_root))
    runtime = built.runtime
    observed = {
        "tracking_iou": runtime.tracking_iou,
        "min_bbox_aspect": runtime.min_bbox_aspect,
    }
    record = {
        "constructed": True,
        "module": DETECTOR_MODULE,
        "composition": "so101_demo.adapters.act.detector.build_bound_head_detector",
        "adapter": f"{DETECTOR_MODULE}.{TRACKER_CLASS}",
        "detector_class": f"{type(runtime.detector).__module__}.{type(runtime.detector).__qualname__}",
        "model_id": model_id,
        "device": {"requested": device, "runtime": getattr(runtime.detector, "runtime_device", None)},
        "image_size_px": DETECTOR_IMAGE_SIZE_PX,
        "weights_path": str(weights),
        "weights_sha256": weight_sha256,
        "snapshot_path": str(getattr(built, "snapshot_path", "")),
        "observed": observed,
        "declared_in_production_config": dict(production_config.get("tracker") or {}),
    }
    return observed, record


def _readback_for(*, value, observed, source) -> dict:
    """One parameter's startup readback: the observed value, or an unverified record with its reason."""

    if observed is None:
        return {
            "observed_value": value,
            "observation": "not_observable",
            "verified": False,
            "source": source,
            "reason": source,
        }
    verified = observed == value
    return {
        "observed_value": observed,
        "observation": "constructed_production_component",
        "verified": verified,
        "source": source,
    }


def installed_environment(*, web_bundle_root=None, package_prefix=None) -> dict:
    """The running system's own identity, read from the process and the install tree.

    Nine fields, none of them taken from a document: the package prefix the console script resolves
    through, that console script, the torch/ultralytics/CUDA/driver versions of the interpreter that
    imports them, the MuJoCo version, the installed tracker adapter and the digest of the installed
    teleop web bundle. The camera identity and the intrinsics digest come from the sealed documents and
    are assembled by `runtime_identity`.
    """

    import torch
    import ultralytics

    if package_prefix is None:
        try:
            from ament_index_python.packages import get_package_prefix

            prefix = Path(get_package_prefix("so101_demo_py"))
        except Exception as error:  # noqa: BLE001 - the prefix is provenance: an absent one is refused
            raise _refuse(
                f"the running system's package prefix cannot be resolved "
                f"({type(error).__name__}: {error})"
            ) from error
    else:
        prefix = Path(package_prefix)
    script = prefix / "lib" / "so101_demo_py" / "so101_head_search_calibration"
    if not script.is_file():
        raise _refuse(f"the console script {script} of the running package prefix is not a file")
    cuda_version = torch.version.cuda
    if not cuda_version:
        raise _refuse("the running torch reports no CUDA version, so no CUDA runtime was measured")
    import mujoco

    from so101_demo.adapters.act.detector import HeadRgbDetector

    if web_bundle_root is None:
        try:
            from ament_index_python.packages import get_package_share_directory

            web_bundle_root = Path(get_package_share_directory("so101_teleop")) / "web"
        except Exception as error:  # noqa: BLE001 - an absent bundle is refused, never invented
            raise _refuse(
                f"the installed teleop web bundle cannot be resolved ({type(error).__name__}: {error})"
            ) from error
    return {
        "package_prefix": str(prefix),
        "console_script_path": str(script),
        "torch_version": str(torch.__version__),
        "ultralytics_version": str(ultralytics.__version__),
        "cuda_version": str(cuda_version),
        "driver_version": _driver_version(),
        "mujoco_version": str(mujoco.__version__),
        "tracker_id": f"{HeadRgbDetector.__module__}.{HeadRgbDetector.__qualname__}",
        "web_bundle_id": _web_bundle_digest(Path(web_bundle_root)),
    }


def _driver_version() -> str:
    """The GPU driver the CUDA runtime runs on, from nvidia-smi or the kernel module's own version."""

    try:
        completed = subprocess.run(
            ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        completed = None
    if completed is not None and completed.returncode == 0:
        version = completed.stdout.strip().splitlines()
        if version and version[0].strip():
            return version[0].strip()
    version_file = Path("/proc/driver/nvidia/version")
    if version_file.is_file():
        for line in version_file.read_text(encoding="utf-8").splitlines():
            fields = line.split()
            if "Module" in fields:
                index = fields.index("Module")
                if index + 1 < len(fields):
                    return fields[index + 1]
    raise _refuse("the GPU driver version cannot be read, so the CUDA runtime cannot be identified")


def _web_bundle_digest(root: Path) -> str:
    """The digest of the installed web bundle: every file it serves, by relative path and content."""

    if not root.is_dir():
        raise _refuse(f"the installed teleop web bundle {root} is not a directory")
    entries = sorted(
        (path for path in root.rglob("*") if path.is_file()), key=lambda path: str(path.relative_to(root))
    )
    if not entries:
        raise _refuse(f"the installed teleop web bundle {root} holds no file")
    digest = hashlib.sha256()
    for path in entries:
        digest.update(str(path.relative_to(root)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def runtime_identity(*, environment, geometry_document, production_config) -> dict:
    """Assemble and check the twelve identity fields of plan section 2b, in their fixed order.

    The nine system-side readings come from `environment`; the camera identity comes from the declared
    production camera and is required to be the camera the seal measured, and the intrinsics digest is
    the canonical digest of the sealed camera block - so a bundle cannot name a camera or intrinsics the
    seal did not freeze.
    """

    camera_id = (production_config.get("camera") or {}).get("name")
    if camera_id != geometry_document.get("camera_name"):
        raise _refuse(
            f"the declared production camera {camera_id!r} is not the camera the seal measured "
            f"({geometry_document.get('camera_name')!r})"
        )
    sealed_camera = geometry_document.get("camera")
    if not isinstance(sealed_camera, Mapping):
        raise _refuse("the sealed geometry carries no camera block, so no intrinsics can be identified")
    identity = {
        **dict(environment),
        "camera_id": camera_id,
        "camera_intrinsics_sha256": canonical_sha256(sealed_camera),
    }
    missing = [field for field in RUNTIME_IDENTITY_FIELDS if field not in identity]
    if missing:
        raise _refuse(f"the running system's identity omits {missing}")
    for field in RUNTIME_IDENTITY_FIELDS:
        value = identity[field]
        if value is None or (type(value) is str and not value):
            raise _refuse(f"the running system's identity records no {field}")
    for field in ("detector_weights_sha256", "camera_intrinsics_sha256"):
        value = identity[field]
        if type(value) is not str or len(value) != 64:
            raise _refuse(f"the running system's identity records no sha256 digest for {field}")
    return {field: identity[field] for field in RUNTIME_IDENTITY_FIELDS}


def _perception_values(*, operating_point, frozen_candidate, production_config, weights) -> dict:
    """The four selected values, the rule that selected them and the frozen document that seals them."""

    chosen = operating_point.get("chosen_point")
    if not isinstance(chosen, Mapping):
        raise _refuse(
            "the operating point records no chosen point, so the four perception values have no source"
        )
    values = {}
    for name in PERCEPTION_PARAMETERS:
        if name not in chosen:
            raise _refuse(f"the operating point's chosen point declares no {name}")
        value = chosen[name]
        if not _finite(value):
            raise _refuse(f"the operating point's {name} is not one finite number")
        values[name] = value
    rule = operating_point.get("rule")
    digest = operating_point.get("rule_sha256")
    if not isinstance(rule, Mapping) or type(digest) is not str or len(digest) != 64:
        raise _refuse("the operating point carries no rule record with its own digest")
    body = {key: value for key, value in rule.items() if key != "rule_sha256"}
    if rule.get("rule_sha256") != digest or canonical_sha256(body) != digest:
        raise _refuse(
            "the operating point's rule digest does not cover the rule record it carries, so the rule "
            "that selected the point cannot be identified"
        )
    if not operating_point.get("candidate_id"):
        raise _refuse("the operating point names no candidate")
    digest = frozen_candidate.get("weight_sha256")
    if type(digest) is not str or len(digest) != 64:
        raise _refuse("the frozen candidate document seals no weight digest")
    if _digest(weights) != digest:
        raise _refuse(
            f"the declared weights {weights} digest to {_digest(weights)} but the frozen candidate "
            f"seals {digest}"
        )
    point = (frozen_candidate.get("operating_points") or {}).get(
        operating_point.get("domain", "head")
    )
    if not isinstance(point, Mapping):
        raise _refuse("the frozen candidate document seals no operating point for this domain")
    if point.get("min_confidence") != values["min_confidence"]:
        raise _refuse(
            f"the selected min_confidence {values['min_confidence']!r} is not the frozen candidate's "
            f"{point.get('min_confidence')!r}"
        )
    tracker = point.get("tracker")
    if not isinstance(tracker, Mapping) or tracker.get("iou") != values["tracking_iou"]:
        raise _refuse(
            f"the selected tracking_iou {values['tracking_iou']!r} is not the frozen candidate's "
            f"{(tracker or {}).get('iou')!r}"
        )
    values["frozen_declaration"] = {
        name: {"declared": True, "value": point[name]} if name in point else {"declared": False, "value": None}
        for name in PERCEPTION_PARAMETERS
    }
    values["frozen_declaration"]["tracking_iou"] = {"declared": True, "value": tracker["iou"]}
    sealed = production_config.get("values") or {}
    for name in ("min_bbox_aspect", "min_area_px2"):
        if sealed.get(name) is not None and not _finite(sealed[name]):
            raise _refuse(f"the declared production value {name} is not one finite number")
    return values


def record_bundle_inputs(
    *,
    geometry_seal,
    production_config,
    operating_point,
    frozen_candidate,
    weights,
    output_dir,
    operating_point_measurements=None,
    device: str = DEFAULT_DEVICE,
    readback_identity: str = DEFAULT_READBACK_IDENTITY,
    web_bundle_root=None,
    environment=None,
    detector_builder=None,
    controller_factory=None,
    command=None,
) -> dict:
    """Produce `bundle-inputs.json` and the receipt that records how every value was observed.

    Everything is validated and observed before the output directory is created, so a refusal leaves no
    document behind. The four perception values come from the phase-3 selection document and are required
    to be the ones the frozen candidate seals; the two geometry values come from the sealed geometry,
    whose own digest has to cover its body. The startup readback then constructs the installed controller
    and the production detector *with those values* and records what it observes - an observation it
    cannot take is recorded as unverified with its reason.
    """

    output = Path(output_dir)
    if output.exists():
        raise _refuse(f"{output} exists; the producer's documents are never resumed or overwritten")
    if type(readback_identity) is not str or not readback_identity:
        raise _refuse("the readback needs the identity it is constructed under")
    geometry_document = _read_json(geometry_seal)
    geometry = read_geometry_document(geometry_document)
    production = _read_json(production_config)
    operating = _read_json(operating_point)
    frozen = _read_json(frozen_candidate)
    if not isinstance(production.get("values"), Mapping) or not isinstance(production.get("motion"), Mapping):
        raise _refuse(
            "the declared production configuration carries no values/motion block, so no configuration "
            "can be constructed from it"
        )
    if not isinstance(production.get("camera"), Mapping):
        raise _refuse("the declared production configuration carries no camera block")

    values = {
        "horizontal_fov_rad": float(geometry["horizontal_fov_rad"]),
        "lock_valid_neck_rad": [float(bound) for bound in geometry["lock_valid_neck_rad"]],
    }
    values.update(_perception_values(
        operating_point=operating,
        frozen_candidate=frozen,
        production_config=production,
        weights=weights,
    ))
    frozen_declaration = values.pop("frozen_declaration")
    operating = {**operating, "frozen_declaration": frozen_declaration}

    reader = installed_environment if environment is None else environment
    reading = dict(reader(web_bundle_root=web_bundle_root))
    identity = runtime_identity(
        environment={**reading, "detector_weights_sha256": frozen["weight_sha256"]},
        geometry_document=geometry_document,
        production_config=production,
    )

    configuration = _readback_configuration(
        production_config=production, geometry=geometry, values=values, identity=readback_identity
    )
    controller, controller_record = _controller_readback(
        configuration, controller_factory=controller_factory
    )
    lock_rule = _lock_rule_readback(configuration, controller_factory=controller_factory)
    if lock_rule["ticks_to_lock"] != 3 or lock_rule["locked_after_two_ticks"] is not False:
        raise _refuse(
            "the constructed controller does not lock on the third consecutive in-deadband frame, so the "
            f"three-frame rule cannot be recorded as observed: {lock_rule}"
        )
    detector_observed = None
    detector_record: dict = {
        "constructed": False,
        "module": DETECTOR_MODULE,
        "adapter": f"{DETECTOR_MODULE}.{TRACKER_CLASS}",
        "device": {"requested": device, "runtime": None},
        "observed": {},
        "declared_in_production_config": dict(production.get("tracker") or {}),
    }
    detector_reason = None
    snapshot_root = Path(tempfile.mkdtemp(prefix="head-search-readback-model-"))
    try:
        detector_observed, detector_record = _detector_readback(
            production_config=production,
            values=values,
            weights=weights,
            frozen_candidate=frozen,
            device=device,
            snapshot_root=snapshot_root,
            detector_builder=detector_builder,
        )
    except Exception as error:  # noqa: BLE001 - an unobservable readback is recorded, never faked
        detector_reason = f"{type(error).__name__}: {error}"
        detector_record["reason"] = detector_reason
    finally:
        shutil.rmtree(snapshot_root, ignore_errors=True)
    detector_record["snapshot_root_removed"] = not snapshot_root.exists()

    sources = {
        "horizontal_fov_rad": (
            "HeadSearchController(...).plan.horizontal_fov_rad, read off the bounded stop plan the "
            "installed controller built with the recorded field of view"
        ),
        "lock_valid_neck_rad": (
            "HeadSearchController(...).plan.safe_interval_rad, read off the bounded stop plan the "
            "installed controller built with the recorded interval"
        ),
        "min_confidence": (
            "HeadSearchController(...).config['min_confidence'], read off the constructed controller "
            "that applies it to every detection"
        ),
        "min_area_px2": (
            "HeadSearchController(...).config['min_area_px2'], read off the constructed controller that "
            "applies it to every detection"
        ),
        "tracking_iou": (
            "HeadRgbDetector(...).tracking_iou, read off the constructed production detector that "
            "associates tracks with it"
        ),
        "min_bbox_aspect": (
            "HeadRgbDetector(...).min_bbox_aspect, read off the constructed production detector that "
            "filters candidates with it"
        ),
    }
    observed_values = {
        **controller_record["observed"],
        **(detector_observed or {}),
    }
    unavailable = (
        {
            name: f"{DETECTOR_MODULE}.{TRACKER_CLASS} could not be constructed: {detector_reason}"
            for name in ("tracking_iou", "min_bbox_aspect")
        }
        if detector_observed is None
        else {}
    )
    readbacks = {
        name: _readback_for(
            value=values[name],
            observed=None if name in unavailable else observed_values[name],
            source=unavailable.get(name, sources[name]),
        )
        for name in DECLARED_PARAMETERS
    }

    from so101_demo.act import search as search_module

    owner_module = Path(search_module.__file__)
    detector_module_path = Path(
        __import__(DETECTOR_MODULE, fromlist=["__file__"]).__file__
    )
    perception_references = [
        Path(operating_point),
        Path(frozen_candidate),
        Path(weights),
        Path(production_config),
        owner_module,
        None if operating_point_measurements is None else Path(operating_point_measurements),
    ]
    geometry_references = [Path(geometry_seal), Path(production_config), owner_module]
    blocks = {}
    blocks[GEOMETRY_PHASE] = {"parameters": {
        name: _geometry_block(
            name=name,
            value=values[name],
            geometry_document=geometry_document,
            references=geometry_references,
            readback=readbacks[name],
        )
        for name in GEOMETRY_PARAMETERS
    }}
    blocks[PERCEPTION_PHASE] = {"parameters": {
        name: _perception_block(
            name=name,
            value=values[name],
            operating_point=operating,
            production_config=production,
            references=perception_references,
            readback=readbacks[name],
        )
        for name in PERCEPTION_PARAMETERS
    }}
    also_recorded = {
        "settle_velocity_rad_s": {
            "value_or_definition": controller.config["settle_velocity_rad_s"],
            "input_evidence": _evidence(Path(production_config), owner_module),
            "production_owner": (
                "so101_demo.act.search.HeadSearchController.tick: the stop condition "
                "abs(neck_velocity_rad_s) <= config['settle_velocity_rad_s']"
            ),
            "startup_readback": {
                "observed_value": controller.config["settle_velocity_rad_s"],
                "observation": "constructed_production_component",
                "verified": controller.config["settle_velocity_rad_s"]
                == production["motion"]["settle_velocity_rad_s"],
                "source": "HeadSearchController(...).config['settle_velocity_rad_s']",
            },
        },
        "goal_tolerance_rad": {
            "value_or_definition": controller.config["goal_tolerance_rad"],
            "input_evidence": _evidence(Path(production_config), owner_module),
            "production_owner": (
                "so101_demo.act.search.HeadSearchController.tick: the arrival condition "
                "abs(neck_yaw_rad - target) <= config['goal_tolerance_rad']"
            ),
            "startup_readback": {
                "observed_value": controller.config["goal_tolerance_rad"],
                "observation": "constructed_production_component",
                "verified": controller.config["goal_tolerance_rad"]
                == production["motion"]["goal_tolerance_rad"],
                "source": "HeadSearchController(...).config['goal_tolerance_rad']",
            },
        },
        "three_consecutive_frame_lock_rule": {
            "value_or_definition": LOCK_RULE_DEFINITION,
            "input_evidence": _evidence(owner_module),
            "production_owner": "so101_demo.act.search.HeadSearchController.tick (lock_count >= 3)",
            "startup_readback": {
                **lock_rule,
                "verified": True,
                "source": "HeadSearchController(...).tick driven to its lock verdict",
            },
        },
        "tracker_algorithm": {
            "value_or_definition": TRACKER_DEFINITION,
            "input_evidence": _evidence(Path(production_config), detector_module_path, Path(frozen_candidate)),
            "production_owner": f"{DETECTOR_MODULE}.{TRACKER_CLASS}.detect",
            "startup_readback": {
                "observation": "constructed_production_component",
                "verified": detector_observed is not None,
                "observed": dict(detector_observed or {}),
                "declared_in_production_config": dict(production.get("tracker") or {}),
                "source": f"{DETECTOR_MODULE}.{TRACKER_CLASS}(...).tracking_iou",
                **({} if detector_observed is not None else {"reason": detector_reason}),
            },
        },
    }
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "readback_identity": readback_identity,
        "parameter_evidence": blocks,
        "also_recorded": also_recorded,
        "runtime_identity": identity,
    }
    _check_declared_document(document)

    output.mkdir(parents=True)
    document_path = output / BUNDLE_INPUTS_NAME
    receipt_path = output / RECEIPT_NAME
    document_path.write_text(
        json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    unverified = sorted(name for name, readback in readbacks.items() if not readback["verified"])
    if detector_observed is None:
        unverified = sorted(set(unverified) | {"tracking_iou", "min_bbox_aspect"})
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": PHASE,
        "status": "RECORDED",
        "values": {name: values[name] for name in DECLARED_PARAMETERS},
        "observed": observed_values,
        "unverified": unverified,
        "bundle_inputs": {"path": str(document_path), "sha256": _digest(document_path)},
        "runtime_identity": identity,
        "effective_value_readback": {
            "controller": controller_record,
            "detector": detector_record,
            "three_consecutive_frame_lock_rule": lock_rule,
            "also_recorded": {
                item: also_recorded[item]["startup_readback"]["verified"]
                for item in ALSO_RECORDED_DECLARED
            },
        },
        "cpu_fallback": False,
        "motion_commanded": False,
        "provenance": {
            "command": command,
            "inputs": {
                "geometry_seal": {"path": str(geometry_seal), "sha256": _digest(geometry_seal)},
                "production_config": {
                    "path": str(production_config),
                    "sha256": _digest(production_config),
                },
                "operating_point": {"path": str(operating_point), "sha256": _digest(operating_point)},
                "frozen_candidate": {
                    "path": str(frozen_candidate),
                    "sha256": _digest(frozen_candidate),
                },
                "weights": {"path": str(weights), "sha256": _digest(weights)},
                "operating_point_measurements": (
                    None
                    if operating_point_measurements is None
                    else {
                        "path": str(operating_point_measurements),
                        "sha256": _digest(operating_point_measurements),
                    }
                ),
                "owner_module": {"path": str(owner_module), "sha256": _digest(owner_module)},
                "detector_module": {
                    "path": str(detector_module_path),
                    "sha256": _digest(detector_module_path),
                },
            },
            "geometry_seal_sha256": geometry_document.get("seal_sha256"),
            "readback_identity": readback_identity,
            "device": device,
        },
    }
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "document": document,
        "receipt": receipt,
        "document_path": document_path,
        "receipt_path": receipt_path,
    }


def _check_declared_document(document) -> None:
    """The declared document is checked against phase 8's own key contracts before it is written."""

    for phase in (GEOMETRY_PHASE, PERCEPTION_PHASE):
        parameters = document["parameter_evidence"][phase]["parameters"]
        for name, block in parameters.items():
            missing = [key for key in PARAMETER_EVIDENCE_KEYS if key not in block]
            if missing:
                raise _refuse(f"{name}: the evidence block omits {missing}")
            for reference in block["input_evidence"]:
                if set(reference) != set(EVIDENCE_REFERENCE_KEYS):
                    raise _refuse(f"{name}: an input evidence reference is exactly {EVIDENCE_REFERENCE_KEYS}")
            if block["startup_readback"]["observed_value"] != block["value"]:
                raise _refuse(
                    f"{name}: the startup readback observed "
                    f"{block['startup_readback']['observed_value']!r} but the block records "
                    f"{block['value']!r}"
                )
    if set(document["also_recorded"]) != set(ALSO_RECORDED_DECLARED):
        raise _refuse(f"the declared also-recorded items are exactly {list(ALSO_RECORDED_DECLARED)}")
    for item, record in document["also_recorded"].items():
        missing = [key for key in ALSO_RECORDED_KEYS if key not in record]
        if missing:
            raise _refuse(f"{item}: the record omits {missing}")
        if item in ALSO_RECORDED_ITEMS and record["startup_readback"] is None:
            raise _refuse(f"{item}: the record carries no startup readback")
    if set(document["runtime_identity"]) != set(RUNTIME_IDENTITY_FIELDS):
        raise _refuse(f"the runtime identity is exactly {list(RUNTIME_IDENTITY_FIELDS)}")
