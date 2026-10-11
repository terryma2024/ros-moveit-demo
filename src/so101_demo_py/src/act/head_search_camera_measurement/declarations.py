"""Kinds, refusal codes and the declared safety margin and camera geometry."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path
import re

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_timing_measurement.contracts import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    _digest,
    _finite,
)

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
