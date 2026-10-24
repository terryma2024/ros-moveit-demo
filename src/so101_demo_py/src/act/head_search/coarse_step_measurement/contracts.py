"""Kinds, refusal codes and small validators of the coarse step measurement."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import re

from so101_demo.act.head_search.calibration_bundle import (
    CAL_EFFECTIVE_VALUE_MISMATCH,
)
from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search.operating_point import CAL_SPLIT_LEAK

SCHEMA_VERSION = 1


KIND = "head_search_coarse_step_val_sweep"


MEASUREMENT_KIND = "head_search_coarse_step_measurement"


PHASE = "coarse_step_measurement"


PARAMETER = "coarse_step_rad"


UNIT = "rad"


DOMAIN = "head"


SPLIT = "val"


#: the gate's matcher: one centre-to-centre radius in pixels
MATCH_RADIUS_PX = 8.0


#: a re-rendered stop is not bit-identical (the EGL renderer differs by up to one 8-bit level), so the
#: reconstruction check of a val scene compares the rendered image with the dataset's own image within
#: this bound - measured at 1 for all 200 val scenes of the head dataset
RECONSTRUCTION_PIXEL_TOLERANCE = 1


#: so this only absorbs a JSON round-trip
STOP_TOLERANCE_RAD = 1e-12


CAL_SWEEP_EVIDENCE_MISSING = "CAL_SWEEP_EVIDENCE_MISSING"


CAL_SWEEP_EVIDENCE_PARTIAL = "CAL_SWEEP_EVIDENCE_PARTIAL"


CAL_SWEEP_EVIDENCE_CONTRADICTORY = "CAL_SWEEP_EVIDENCE_CONTRADICTORY"


CAL_SWEEP_UNSTABLE = "CAL_SWEEP_UNSTABLE"


REFUSAL_CODES = (
    CAL_SWEEP_EVIDENCE_MISSING,
    CAL_SWEEP_EVIDENCE_PARTIAL,
    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
    CAL_SWEEP_UNSTABLE,
    CAL_SPLIT_LEAK,
    CAL_EFFECTIVE_VALUE_MISMATCH,
)


SELECTION_RULE = (
    "the largest generated candidate at or below half the horizontal field of view whose bounded "
    "two-way sweep covers the whole required_search_domain_rad and misses no required-visible val cup, "
    "with repeated passes agreeing; a tie breaks on the shortest lock time (the first stop that matched "
    "a cup), which the largest step also minimises by commanding the fewest stops"
)


SELECTION_FORMULA = (
    "the largest generated coarse_step_rad for which coverage_is_complete(bounded_search_stops(...)) and "
    "independent_sweep_check(...) hold and missed_scenes == [] on the head val split; the observed "
    "worst-case first-lock stop breaks a tie"
)


PRODUCTION_OWNER = "so101_demo.act.search.HeadSearchController (coarse_step_rad)"


#: what the raw document's own digest covers: its whole body, its `path` included
DIGEST_CONVENTION = "sha256 = canonical_sha256(body without the sha256 field)"


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CalibrationCoarseStepRefused(CalibrationInputsRefused):
    """A coarse-step refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _refuse(code: str, detail: str) -> CalibrationCoarseStepRefused:
    return CalibrationCoarseStepRefused(code, detail)


def _mapping(name: str, value) -> Mapping:
    """A document the phase can read, or a plain `ValueError` for a malformed one."""

    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _sequence(name: str, value) -> list:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence")
    return list(value)


def _records(name: str, value) -> list[Mapping]:
    records = _sequence(name, value)
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError(f"every {name} record must be a mapping")
    return records


def _positive(name: str, value) -> float:
    if not _finite(value) or float(value) <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _interval(name: str, value) -> tuple[float, float]:
    bounds = _sequence(name, value)
    if len(bounds) != 2:
        raise ValueError(f"{name} must be two finite ordered bounds")
    low, high = (float(bound) for bound in bounds)
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise ValueError(f"{name} must be two finite ordered bounds")
    return low, high


def _centre(record, name: str) -> tuple[float, float]:
    if not isinstance(record, Mapping):
        raise ValueError(f"every {name} must be a record carrying x and y")
    x, y = record.get("x"), record.get("y")
    if not (_finite(x) and _finite(y)):
        raise ValueError(f"a {name} record declares no finite x/y")
    return float(x), float(y)


def _confidence(record) -> float:
    if not isinstance(record, Mapping):
        raise ValueError("every detection must be a record")
    conf = record.get("conf")
    if not _finite(conf):
        raise ValueError("a detection record declares no finite conf")
    return float(conf)


def _reference(name: str, document) -> dict:
    """The path and sha256 of one measured input, as the evidence block cites it."""

    if not isinstance(document, Mapping):
        raise ValueError(f"{name} must be a document carrying its path and sha256")
    path, digest = document.get("path"), document.get("sha256")
    if type(path) is not str or not path:
        raise ValueError(f"{name} names no evidence path")
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        raise ValueError(f"{name} carries no sha256 evidence digest")
    return {"path": path, "sha256": digest}


def _geometry(geometry) -> dict:
    """The sealed geometry this phase measures against, as phase 2 hands it over."""

    declared = _mapping("the sealed geometry", geometry)
    anchors: dict[str, float] = {}
    for name, angle in _mapping("anchors_rad", declared.get("anchors_rad")).items():
        if type(name) is not str or not name or not _finite(angle):
            raise ValueError("every anchor must be named and carry a finite neck angle")
        anchors[name] = float(angle)
    if not anchors:
        raise ValueError("the sealed geometry declares no anchors")
    return {
        "horizontal_fov_rad": _positive("horizontal_fov_rad", declared.get("horizontal_fov_rad")),
        "lock_valid_neck_rad": list(
            _interval("lock_valid_neck_rad", declared.get("lock_valid_neck_rad"))
        ),
        "required_search_domain_rad": list(
            _interval("required_search_domain_rad", declared.get("required_search_domain_rad"))
        ),
        "sealed_coarse_step_candidate_rad": declared.get("sealed_coarse_step_candidate_rad"),
        "anchors_rad": anchors,
    }


def _uncovered(reason: str) -> dict:
    return {
        "anchors": [],
        "stop_count": 0,
        "covers_required_domain": False,
        "reason": reason,
        "coverage": "horizontal_fov_union_of_stops",
        "independent_sweep_check": {"checked": False, "reason": reason},
    }
