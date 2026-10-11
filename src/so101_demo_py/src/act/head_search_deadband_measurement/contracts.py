"""Kinds, refusal codes, lock rules and constants of the deadband measurement."""

from __future__ import annotations

from collections.abc import Sequence
import math
import re

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_timing_measurement.contracts import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
)

SCHEMA_VERSION = 1


KIND = "head_search_calibration_deadband_candidates"


RECEIPT_KIND = "head_search_calibration_deadband_measurement_receipt"


PHASE = "deadband_candidates"


ARTIFACT = "deadband-candidates.json"


RECEIPT_ARTIFACT = "measurement-receipt.json"


#: this measurement's own refusals; every other code it can raise is the timing module's, because the
#: settle rule, the stop classification and the time-base proof are that module's and are reused here
CAL_DEADBAND_CUP_LOST = "CAL_DEADBAND_CUP_LOST"


CAL_DEADBAND_OUT_OF_CORRIDOR = "CAL_DEADBAND_OUT_OF_CORRIDOR"


REFUSAL_CODES = (
    CAL_DEADBAND_CUP_LOST,
    CAL_DEADBAND_OUT_OF_CORRIDOR,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    CAL_TIMING_DEVICE_UNAVAILABLE,
)


#: the keys phase 6 reads off every candidate record, and nothing else
RECORD_KEYS = ("center_deadband_px", "longest_locked_run_frames", "direction_reversals")


#: this measurement's own controller identities: the trials are one declared attempt of one session
MEASUREMENT_ATTEMPT_ID = "head-search-deadband-measurement"


MEASUREMENT_SESSION_ID = "head-search-deadband-measurement"


#: how many frames one trial may spend before the loop must have reached a verdict
DEFAULT_MAX_FRAMES = 12


#: the detector's declared model identity when the production configuration names no runtime of its own
DETECTOR_MODEL_ID = "head-search-deadband-measurement"


LOCK_RULE = (
    "the longest run of consecutive frames in which the detected cup's centre column is within "
    "center_deadband_px of the camera's principal point and its centre row is inside vertical_bounds_px, "
    "with the same detection track as the frame before it: a frame without a detection, a frame outside "
    "the vertical bounds and a change of track each break the run, exactly as HeadSearchController resets "
    "its own lock count. A candidate that locks for three consecutive frames is the lock phase 6 requires"
)


REVERSAL_DEFINITION = (
    "the number of sign changes in the sequence of the trial's commanded neck moves "
    "(new target - previous target), counting only the moves the controller made after it had seen a "
    "detection: one correction that settles, however large, is not a reversal, while two corrections in "
    "opposite directions are one. This is the left-right reversal of the commanded correction, not the "
    "sign of the measured error, which flips once on any single overshoot"
)


CORRIDOR_RULE = (
    "every commanded neck target and every settled neck angle lies inside the intersection of the seal's "
    "required_search_domain_rad and its lock_valid_neck_rad; a target outside it refuses the trial and is "
    "never clamped, because clamping would command a motion the controller did not ask for"
)


FRAME_CADENCE = (
    "a frame is produced at most once per declared frame period of simulation time and never before the "
    "commanded target has settled, so the achieved interval between two frames is that settle time plus "
    "the remainder that carries the loop to the next frame boundary: every frame records its own "
    "frame_interval_sim_s (null for a trial's first frame, which has no predecessor), and frame_rate_hz "
    "names the frame contract this measurement paces itself against rather than a rate it achieved"
)


WARMUP_POLICY = (
    "one frame is rendered and detected before the measured frames begin, at the same plant state as the "
    "first measured frame: the production detector's own constructor warm-up runs on a zeros image that "
    "carries no box and no mask, so the first predict that really resolves a detection pays the one-time "
    "CUDA and mask initialisation instead - inside the very age HeadSearchController's freshness gate "
    "compares against max_age_s. The warm-up is recorded next to the frames instead of being hidden in "
    "them, the detector is reset after it so the measured frames begin the attempt state they would have "
    "begun without it, and every frame in the measurement is a frame the flight really measured"
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


#: one float ulp of a bound around a few radians, the allowance the bounded planner's endpoints use
_BOUND_TOLERANCE_RAD = 1e-12


class CalibrationDeadbandMeasurementRefused(CalibrationInputsRefused):
    """A closed-loop lock-trial refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _refuse(code: str, detail: str) -> CalibrationDeadbandMeasurementRefused:
    return CalibrationDeadbandMeasurementRefused(code, detail)


def _interval(name: str, value) -> tuple[float, float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"{name} must be two finite bounds")
    low, high = (float(bound) for bound in value)
    if not math.isfinite(low) or not math.isfinite(high) or low > high:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"{name} must be finite and ordered")
    return low, high
