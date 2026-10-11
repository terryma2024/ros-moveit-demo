"""Phase 6's ``camera_measurements`` document: the measured centre jitter and the declared margin.

Phase 6 reads five keys off this document
(``head_search_search_params.compute_center_deadband_px`` and ``compute_vertical_bounds_px``):
``horizontal_fov_rad``, ``image_width_px``, ``image_height_px``, ``centre_jitter_rad`` and
``safety_margin_px``. They do not have the same provenance, and this module keeps them apart:

* ``horizontal_fov_rad``, ``image_width_px`` and ``image_height_px`` are **declarations**: the sealed
  geometry measured them once (``horizontal_fov_rad``, ``image_width``, ``image_height``) and this
  document copies them with ``measured_here: false`` and a ``declared_by`` block naming the artefact, its
  sha256 and the key each value came from.
* ``centre_jitter_rad`` is **measured here**: the spread of the detected cup centre across repeated frames
  at a fixed, settled pose. The neck is commanded to a pose the production controller's own bounded plan
  holds, the sealed scene's position actuator holds it while the simulation steps one declared frame
  period at a time, the head camera renders, the production head detector finds the cup, and the centre
  of its box is recorded frame by frame. The statistic is the sample standard deviation (``ddof=1``) of
  the **centre column** - the axis ``lock_run`` applies ``center_deadband_px`` to - expressed as an angle
  through the sealed angular resolution ``horizontal_fov_rad / image_width_px``, which is exactly the
  ``rad_per_px`` phase 6 divides by, so ``ceil(centre_jitter_rad / rad_per_px)`` is the pixel spread that
  was measured. The document headlines the **worst case over poses** and keeps every pose's own
  distribution, its frames and its stamps beside it; the row-axis spread is recorded too, for review.
* ``safety_margin_px`` is a **declaration**, and since HS-305 it is declared as a **fraction of the shorter
  production image edge** in the production head-camera declaration
  ``config/perception/head_camera_yolo_seg.yaml``: this producer derives
  ``safety_margin_px = ceil(image_safety_margin_fraction * min(image_width_px, image_height_px))`` from
  that declaration and records the declaring path, its sha256 and the arithmetic, because a fraction
  survives a resolution change and the ceiling keeps the bound conservative. Nothing is inferred from the
  workspace projection the margin constrains (that would be circular) and no pixel-count field such as the
  geometry contract's ``visible_pixel_minimum`` is substituted (a different quantity with a different unit).
  When no artefact declares either form the document writes ``safety_margin_px: null`` and records the
  refusal :data:`CAL_CAMERA_SAFETY_MARGIN_UNDECLARED` beside it; it never defaults a number phase 6 would
  intersect the projected workspace with. A declared fraction outside ``(0, 0.5]`` is
  :data:`CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE`, a declaration whose own image dimensions disagree with the
  sealed geometry - or that declares both forms at once - is
  :data:`CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY`, and the pre-existing direct pixel declaration
  (``safety_margin_px``) is still read and cited unchanged. Whichever form is declared, the value is read
  from an artefact and recorded with ``measured_here: false`` and the declaring path, sha256 and key.

What is measured, and what is refused instead of fabricated:

* a frame with no detection, a frame whose detection is not a single cup, and a detector that raises are
  all :data:`CAL_CAMERA_CUP_LOST`: a centre that was not detected is never written as a zero spread, and a
  spread that was not measured is never written at all.
* a pose outside the declared motion corridor (the seal's ``required_search_domain_rad`` intersected with
  its ``lock_valid_neck_rad``) is :data:`CAL_CAMERA_POSE_OUT_OF_CORRIDOR`; nothing is clamped, because a
  clamped pose would be a pose the controller never commanded.
* a stop that was reached but never held, a stop that was never reached, and a settle time that is not the
  simulation clock's are the timing module's own refusals, reused under this module's class.

The only part that touches MuJoCo, the detector or a GPU is the injected plant (the production
:class:`so101_demo.act.head_search_deadband_measurement.plant.MujocoClosedLoopPlant`, whose module imports MuJoCo
inside its constructor) and the default detector factory (the production ``HeadRgbDetector`` over
``YoloSegDetector``, ``allow_cpu_fallback=False``); the measurement itself is a pure loop over an injected
plant and detector, so every rule above is unit-tested without MuJoCo, CUDA or ROS. No ROS node is started,
no hardware is addressed, and the scene's simulated neck is the only thing this module commands.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_deadband_measurement.lock_trial import (
    detector_operating_point,
    motion_corridor_rad,
)
from so101_demo.act.head_search_deadband_measurement.plant import (
    _anchor_requests,
    _plant_request,
    build_production_head_detector,
    MujocoClosedLoopPlant,
)
from so101_demo.act.head_search_mujoco_measurements import read_mujoco_timestep
from so101_demo.act.head_search_timing_measurement.contracts import (
    _digest,
    _finite,
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    DEFAULT_MAX_SETTLE_S,
    DIGEST_CONVENTION,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
    SETTLE_CONSECUTIVE_STEPS,
    SETTLE_RULE,
    SIMULATION_TIME_BASE,
)
from so101_demo.act.head_search_timing_measurement.control import (
    classify_stop,
    planned_stops,
    read_control_period,
    verify_simulation_time_base,
)
from so101_demo.act.head_search_timing_measurement.sweep_runner import _declared_weights
from so101_demo.act.head_search_timing_measurement.documents import (
    runtime_identity as measurement_runtime_identity,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1

KIND = "head_search_calibration_camera_measurements"
RECEIPT_KIND = "head_search_calibration_camera_measurement_receipt"
PHASE = "camera_measurements"

ARTIFACT = "camera-measurements.json"
RECEIPT_ARTIFACT = "measurement-receipt.json"

#: this measurement's own refusals; every other code it can raise is the timing module's, because the
#: settle rule, the stop classification and the time-base proof are that module's and are reused here
CAL_CAMERA_CUP_LOST = "CAL_CAMERA_CUP_LOST"
CAL_CAMERA_POSE_OUT_OF_CORRIDOR = "CAL_CAMERA_POSE_OUT_OF_CORRIDOR"
CAL_CAMERA_SAFETY_MARGIN_UNDECLARED = "CAL_CAMERA_SAFETY_MARGIN_UNDECLARED"
CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE = "CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE"
CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY = "CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY"
REFUSAL_CODES = (
    CAL_CAMERA_CUP_LOST,
    CAL_CAMERA_POSE_OUT_OF_CORRIDOR,
    CAL_CAMERA_SAFETY_MARGIN_UNDECLARED,
    CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE,
    CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    CAL_TIMING_DEVICE_UNAVAILABLE,
)

#: the two declarations the image safety margin is read from: the approved fraction of the shorter
#: production image edge (`image_safety_margin_fraction`), and the direct pixel count the field was
#: declared with before. The fraction is the production form; the pixel form stays readable, and an
#: artefact that declares both is refused rather than resolved by precedence
IMAGE_SAFETY_MARGIN_FRACTION_KEY = "image_safety_margin_fraction"
SAFETY_MARGIN_PX_KEY = "safety_margin_px"

#: the declared fraction's closed upper bound: half the shorter edge, i.e. one whole edge's worth
MAX_IMAGE_SAFETY_MARGIN_FRACTION = 0.5

#: the keys a declaration may carry its own production image dimensions under, so the fraction can be
#: checked against the sealed geometry rather than trusted
DECLARED_IMAGE_WIDTH_KEYS = ("image_width_px", "image_width")
DECLARED_IMAGE_HEIGHT_KEYS = ("image_height_px", "image_height")

#: how many frames one fixed pose is observed for. A spread needs samples; three is the floor the loop
#: accepts, twelve (1.2 s of simulation time at the declared frame period) is the default
DEFAULT_FRAMES_PER_POSE = 12
MIN_FRAMES_PER_POSE = 3

#: this measurement's own controller identities: one declared attempt of one session
MEASUREMENT_ATTEMPT_ID = "head-search-camera-measurement"
MEASUREMENT_SESSION_ID = "head-search-camera-measurement"

DETECTOR_MODEL_ID = "head-search-camera-measurement"

#: the axis phase 6 applies `center_deadband_px` to is the detected box's column, so the angular jitter
#: phase 6 divides by the horizontal resolution has to be that axis's spread
JITTER_AXIS = "column"

JITTER_DEFINITION = (
    "the sample standard deviation (ddof=1) of the detected cup box centre's column over repeated frames "
    "rendered while the sealed neck actuator holds one fixed, settled pose, one frame per declared frame "
    "period"
)
JITTER_COMBINATION = (
    "the worst case over the measured poses: the largest per-pose standard deviation, because a deadband "
    "has to cover the pose that wanders most"
)
ANGULAR_RESOLUTION_RULE = (
    "horizontal_fov_rad / image_width_px, the sealed geometry's own angular resolution - the same "
    "rad_per_px phase 6 divides centre_jitter_rad by, so the round trip from pixels to radians and back "
    "is exact"
)
CORRIDOR_RULE = (
    "required_search_domain_rad intersected with lock_valid_neck_rad: every pose this measurement holds "
    "the neck at must lie inside it, and a pose outside it is refused rather than clamped"
)
FRAME_CADENCE = (
    "one frame per frame_period_s of simulation time while the pose is held; the neck is not re-commanded "
    "between frames, so the pose does not change and every frame is a repeated observation of it"
)
UNDECLARED_SAFETY_MARGIN_DETAIL = (
    "no retained artefact declares the image safety margin: the sealed head camera geometry measures the "
    "field of view and the image size only, the head-search calibration contract's seventeen parameters do "
    "not include an image margin, and the production search configuration declares values.vertical_bounds_px "
    "but no margin. The seal's minimum visible-pixel counts and the geometry contract's "
    "visible_pixel_minimum are counts of visible object pixels, not an inset from the image border, so they "
    "are not substituted. This measurement records the field as null and refuses it rather than defaulting "
    "a number phase 6 would intersect the projected workspace with; pass --safety-margin-declaration with "
    "the production head-camera declaration, which states the fraction, or with an artefact that declares "
    "the pixel count directly"
)

IMAGE_SAFETY_MARGIN_RULE = (
    "safety_margin_px = ceil(image_safety_margin_fraction * min(image_width_px, image_height_px)): the "
    "declared fraction of the shorter production image edge, rounded up so the reserved edge can only grow. "
    "The fraction is a policy value of the production camera declaration, it survives a resolution change, "
    "and it is bound to the sealed geometry's own image dimensions - a declaration whose dimensions "
    "disagree with the seal's is refused rather than believed"
)

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CalibrationCameraMeasurementRefused(CalibrationInputsRefused):
    """This measurement's refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _refuse(code: str, detail: str) -> CalibrationCameraMeasurementRefused:
    return CalibrationCameraMeasurementRefused(code, detail)


def _re_raised(call, *args, **kwargs):
    """Run a reused check, re-raising its refusal as this measurement's own class.

    The settle rule, the stop classification, the time-base proof, the sealed-detector guard and the
    anchor/corridor helpers are the timing and deadband modules' own, so the refusals they raise are that
    module's type. They are this measurement's refusals too - a caller that records `camera_measurements`
    reads one class and one code vocabulary - so they are re-raised here with the same code.
    """

    try:
        return call(*args, **kwargs)
    except CalibrationInputsRefused as error:
        raise _refuse(error.code, error.detail) from error


def _positive(name: str, value) -> float:
    if not _finite(value) or float(value) <= 0.0:
        raise ValueError(f"the {name} must be a positive finite number: {value!r}")
    return float(value)


def _number(
    document, name: str, key: str, *, positive: bool = False, nonnegative: bool = False
) -> float:
    if not isinstance(document, Mapping):
        raise ValueError(f"{name} must be a mapping")
    value = document.get(key)
    if not _finite(value):
        raise ValueError(f"{name} declares no finite {key}")
    value = float(value)
    if positive and value <= 0.0:
        raise ValueError(f"{name} declares a non-positive {key}")
    if nonnegative and value < 0.0:
        raise ValueError(f"{name} declares a negative {key}")
    return value


def _interval(name: str, value) -> tuple[float, float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        raise ValueError(f"the {name} must be two numbers")
    low, high = (float(bound) for bound in value)
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise ValueError(f"the {name} must be two finite numbers in ascending order")
    return low, high


def _mapping(name: str, value) -> Mapping:
    if not isinstance(value, Mapping):
        raise ValueError(f"the {name} must be a mapping")
    return value


def _sequence(name: str, value) -> list:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"the {name} must be a sequence")
    return list(value)


# --- the angular resolution and the spread ---------------------------------------------------------


def rad_per_px(*, horizontal_fov_rad, image_width_px) -> float:
    """The sealed camera's angular resolution, in radians per pixel of the image's width."""

    fov = _positive("field of view", horizontal_fov_rad)
    width = _positive("image width", image_width_px)
    return fov / width


def spread(samples) -> dict:
    """One distribution's spread: the sample standard deviation and the range it came from.

    The standard deviation is the sample one (``ddof=1``): these samples are observations of one pose, not
    the pose population, and a spread computed with ``ddof=0`` would understate the jitter phase 6 has to
    cover. Two samples are the minimum a spread exists for; a non-finite sample is a caller error, never a
    silently dropped observation.
    """

    values: list[float] = []
    for sample in _sequence("spread samples", samples):
        if not _finite(sample):
            raise ValueError(f"every sample of a spread must be a finite number: {sample!r}")
        values.append(float(sample))
    if len(values) < 2:
        raise ValueError("a spread needs at least two samples")
    count = len(values)
    mean = math.fsum(values) / count
    squares = math.fsum((value - mean) ** 2 for value in values)
    deviation = math.sqrt(squares / (count - 1))
    return {
        "count": count,
        "degrees_of_freedom": count - 1,
        "mean": mean,
        "std": deviation,
        "min": min(values),
        "max": max(values),
        "peak_to_peak": max(values) - min(values),
        "max_abs_deviation": max(abs(value - mean) for value in values),
    }


# --- the declared safety margin --------------------------------------------------------------------


def undeclared_safety_margin(detail: str | None = None) -> dict:
    """The recorded state of a field no artefact declares: null, and the refusal that says why."""

    return {
        "field": "safety_margin_px",
        "value": None,
        "unit": "px",
        "measured_here": False,
        "declared": False,
        "declared_by": None,
        "refusal": CAL_CAMERA_SAFETY_MARGIN_UNDECLARED,
        "detail": UNDECLARED_SAFETY_MARGIN_DETAIL if detail is None else detail,
    }


def _declared_key(document: Mapping, key: str) -> tuple[str, object] | None:
    """Where the document declares `key`: at its top level, or one block down."""

    if key in document:
        return key, document[key]
    for name in sorted(document):
        block = document[name]
        if isinstance(block, Mapping) and key in block:
            return f"{name}.{key}", block[key]
    return None


def _declaration_document(artefact: Path) -> Mapping:
    """One declaration artefact, read as JSON first and YAML second, or a caller error."""

    raw = artefact.read_text(encoding="utf-8")
    try:
        document = json.loads(raw)
    except ValueError:
        import yaml

        try:
            document = yaml.safe_load(raw)
        except (
            yaml.YAMLError
        ) as error:  # pragma: no cover - a malformed declaration is a caller error
            raise ValueError(
                f"the safety margin declaration {artefact} is neither JSON nor YAML"
            ) from error
    if not isinstance(document, Mapping):
        raise ValueError(
            f"the safety margin declaration {artefact} must be a mapping of keys to values"
        )
    return document


def _declared_dimension(document: Mapping, keys) -> tuple[str, float] | None:
    """The image dimension a declaration states for itself, if it states one."""

    for key in keys:
        found = _declared_key(document, key)
        if found is not None and _finite(found[1]):
            return found[0], float(found[1])
    return None


def _derived_safety_margin(
    *, artefact: Path, document: Mapping, fraction_key: str, fraction, image_geometry
) -> dict:
    """Turn a declared fraction into the integer pixel margin, bound to the sealed image dimensions.

    The fraction has to be a finite number inside ``(0, 0.5]``; a declaration that states its own image
    dimensions has to agree with the sealed geometry, because a fraction of a different image is a different
    margin; and the derivation is recorded key by key so a reviewer can recompute
    ``ceil(fraction * min(width, height))`` from the document alone.
    """

    if not _finite(fraction):
        raise _refuse(
            CAL_CAMERA_SAFETY_MARGIN_UNDECLARED,
            f"the artefact {artefact} declares {fraction_key} = {fraction!r}; an image safety margin "
            f"fraction is a finite number of the shorter image edge",
        )
    if not isinstance(image_geometry, Mapping):
        raise ValueError(
            f"a declared {IMAGE_SAFETY_MARGIN_FRACTION_KEY} needs the image geometry it is a fraction "
            f"of, so the sealed camera geometry has to be offered"
        )
    width = _number(image_geometry, "the sealed camera geometry", "image_width_px", positive=True)
    height = _number(
        image_geometry, "the sealed camera geometry", "image_height_px", positive=True
    )
    declared_width = _declared_dimension(document, DECLARED_IMAGE_WIDTH_KEYS)
    declared_height = _declared_dimension(document, DECLARED_IMAGE_HEIGHT_KEYS)
    for name, declared, sealed in (
        ("width", declared_width, width),
        ("height", declared_height, height),
    ):
        if declared is not None and declared[1] != sealed:
            raise _refuse(
                CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY,
                f"the artefact {artefact} declares {declared[0]} = {declared[1]!r}, but the sealed head "
                f"camera geometry's image {name} is {sealed!r}: a fraction of a different image is not "
                f"this camera's safety margin",
            )
    value = float(fraction)
    if not 0.0 < value <= MAX_IMAGE_SAFETY_MARGIN_FRACTION:
        raise _refuse(
            CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE,
            f"the artefact {artefact} declares {fraction_key} = {value!r}; the fraction of the shorter "
            f"image edge has to lie inside (0, {MAX_IMAGE_SAFETY_MARGIN_FRACTION}], because a margin of "
            f"zero reserves no edge and a margin of more than half the shorter edge leaves no image",
        )
    shorter_edge = min(width, height)
    margin_px = int(math.ceil(value * shorter_edge))
    derivation = f"ceil({value!r} * min({width!r}, {height!r})) = {margin_px} px"
    return {
        "field": "safety_margin_px",
        "value": float(margin_px),
        "unit": "px",
        "measured_here": False,
        "declared": True,
        "declared_by": {
            "path": str(artefact),
            "sha256": _digest(artefact),
            "key": fraction_key,
            "fraction": value,
            "shorter_edge_px": shorter_edge,
            "bound_to": "the sealed head camera geometry",
            "rule": IMAGE_SAFETY_MARGIN_RULE,
            "derivation": derivation,
        },
        "refusal": None,
        "detail": (
            f"{fraction_key} is declared by {artefact} and derived here into a pixel margin; the fraction "
            f"itself is not measured by this flight"
        ),
        "fraction": value,
        "image_width_px": width,
        "image_height_px": height,
        "shorter_edge_px": shorter_edge,
        "derivation": derivation,
    }


def read_declared_safety_margin(path, *, image_geometry=None) -> dict:
    """The image safety margin an artefact declares, with the path and digest that declare it.

    Two declarations are read. The production form is ``image_safety_margin_fraction``: a policy fraction of
    the **shorter production image edge**, which this function derives into pixels with ``ceil`` and binds to
    the sealed image dimensions (`image_geometry`); a fraction outside ``(0, 0.5]`` is
    :data:`CAL_CAMERA_SAFETY_MARGIN_OUT_OF_RANGE` and a declaration whose own dimensions disagree with the
    seal is :data:`CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY`. The other form is a direct non-negative finite
    ``safety_margin_px`` count, read and cited exactly as before. An artefact that declares neither refuses
    with :data:`CAL_CAMERA_SAFETY_MARGIN_UNDECLARED` rather than being read as a default, and one that
    declares both is :data:`CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY` instead of resolved by precedence. JSON
    is tried first and YAML second, so one artefact format is not privileged over the other.
    """

    artefact = Path(path)
    if not artefact.is_file():
        raise FileNotFoundError(f"the safety margin declaration {artefact} does not exist")
    document = _declaration_document(artefact)
    fraction = _declared_key(document, IMAGE_SAFETY_MARGIN_FRACTION_KEY)
    pixels = _declared_key(document, SAFETY_MARGIN_PX_KEY)
    if fraction is not None and pixels is not None:
        raise _refuse(
            CAL_CAMERA_SAFETY_MARGIN_CONTRADICTORY,
            f"the artefact {artefact} declares both {fraction[0]} = {fraction[1]!r} and "
            f"{pixels[0]} = {pixels[1]!r}; the image safety margin is declared one way, and this "
            f"measurement refuses to choose between two declarations",
        )
    if fraction is not None:
        return _derived_safety_margin(
            artefact=artefact,
            document=document,
            fraction_key=fraction[0],
            fraction=fraction[1],
            image_geometry=image_geometry,
        )
    if pixels is None:
        raise _refuse(
            CAL_CAMERA_SAFETY_MARGIN_UNDECLARED,
            f"the artefact {artefact} declares neither {IMAGE_SAFETY_MARGIN_FRACTION_KEY} nor "
            f"{SAFETY_MARGIN_PX_KEY}, so it declares no image safety margin",
        )
    key, value = pixels
    if not _finite(value) or float(value) < 0.0:
        raise _refuse(
            CAL_CAMERA_SAFETY_MARGIN_UNDECLARED,
            f"the artefact {artefact} declares {key} = {value!r}; an image safety margin is a "
            f"non-negative finite number of pixels",
        )
    return {
        "field": "safety_margin_px",
        "value": float(value),
        "unit": "px",
        "measured_here": False,
        "declared": True,
        "declared_by": {"path": str(artefact), "sha256": _digest(artefact), "key": key},
        "refusal": None,
        "detail": f"{key} is declared by {artefact} and is not measured by this flight",
    }


# --- the declared camera geometry ------------------------------------------------------------------


def declared_camera_geometry(
    *, geometry_seal, seal_path=None, seal_sha256: str | None = None
) -> dict:
    """The three camera numbers the seal measured, as declarations this document cites.

    The seal names them ``horizontal_fov_rad``, ``image_width`` and ``image_height``; phase 6 reads
    ``horizontal_fov_rad``, ``image_width_px`` and ``image_height_px``. The rename is recorded key by key
    in `declared_by.keys` so a reviewer can trace every number back to the seal's own field.
    """

    seal = _mapping("sealed geometry", geometry_seal)
    digest = seal_sha256
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        digest = None if seal_path is None else _digest(seal_path)
    return {
        "horizontal_fov_rad": _number(
            seal, "the sealed geometry", "horizontal_fov_rad", positive=True
        ),
        "image_width_px": _number(seal, "the sealed geometry", "image_width", positive=True),
        "image_height_px": _number(seal, "the sealed geometry", "image_height", positive=True),
        "measured_here": False,
        "declared_by": {
            "path": None if seal_path is None else str(seal_path),
            "sha256": digest,
            "keys": {
                "horizontal_fov_rad": "horizontal_fov_rad",
                "image_width_px": "image_width",
                "image_height_px": "image_height",
            },
        },
    }


# --- the pose hold ---------------------------------------------------------------------------------


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


# --- the document ----------------------------------------------------------------------------------


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


# --- the producer ----------------------------------------------------------------------------------


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


def _cuda_available() -> bool:
    """Whether the declared CUDA device is really there; the measurement never falls back to the CPU."""

    import torch

    return bool(torch.cuda.is_available())
