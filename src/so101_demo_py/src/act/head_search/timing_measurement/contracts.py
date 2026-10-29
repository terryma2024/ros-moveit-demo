"""Kinds, refusal codes, constants and number validators of the search timing measurement."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from pathlib import Path
import re

from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search.timing_params import (
    FRAME_CONTRACT_HZ,
    FRAME_CONTRACT_ITEM,
)

SCHEMA_VERSION = 1


SEARCH_TIMING_KIND = "head_search_calibration_search_timing"


FRAME_AGE_KIND = "head_search_calibration_frame_age_measurements"


FRAME_CONTRACT_KIND = "head_search_calibration_frame_contract"


RECEIPT_KIND = "head_search_calibration_timing_measurement_receipt"


SEARCH_TIMING_PHASE = "search_timing"


FRAME_AGE_PHASE = "frame_age_measurements"


FRAME_CONTRACT_PHASE = "frame_contract"


SEARCH_TIMING_ARTIFACT = "search-timing.json"


FRAME_AGE_ARTIFACT = "frame-age-measurements.json"


FRAME_CONTRACT_ARTIFACT = "frame-contract.json"


RECEIPT_ARTIFACT = "measurement-receipt.json"


#: this measurement's own refusals
CAL_TIMING_EVIDENCE_MISSING = "CAL_TIMING_EVIDENCE_MISSING"


CAL_TIMING_EVIDENCE_CONTRADICTORY = "CAL_TIMING_EVIDENCE_CONTRADICTORY"


CAL_TIMING_SWEEP_UNSETTLED = "CAL_TIMING_SWEEP_UNSETTLED"


CAL_TIMING_STOP_UNSETTLED = "CAL_TIMING_STOP_UNSETTLED"


CAL_TIMING_TIME_BASE_UNVERIFIED = "CAL_TIMING_TIME_BASE_UNVERIFIED"


CAL_TIMING_DEVICE_UNAVAILABLE = "CAL_TIMING_DEVICE_UNAVAILABLE"


REFUSAL_CODES = (
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    CAL_TIMING_DEVICE_UNAVAILABLE,
)


#: the sweep's time base is the MuJoCo simulation clock, never a wall clock
SIMULATION_TIME_BASE = "simulation"


TIME_BASE = SIMULATION_TIME_BASE


#: the base the frame age is expressed in: the monotonic wall clock the controller's freshness gate uses
AGE_TIME_BASE = "monotonic_wall_clock"


#: what the documents' own digests cover, the convention the run's other measurement documents use
DIGEST_CONVENTION = "sha256 = canonical_sha256(body without the sha256 field)"


#: the settle rule as the documents declare it, threshold by threshold
SETTLE_RULE = (
    "a stop is settled when the neck joint's |velocity| is at or below settle_velocity_rad_s for "
    "settle_consecutive_steps consecutive control steps and its |position - target| is at or below "
    "goal_tolerance_rad at that instant; the settle time is that instant minus the step that commanded "
    "the target, in simulation seconds, and it is always steps * simulation_timestep_s"
)


SETTLE_CONSECUTIVE_STEPS = 5


DEFAULT_MAX_SETTLE_S = 5.0


#: the design's declared frame contract (phase 7 accepts no other rate)
FRAME_RATE_HZ = FRAME_CONTRACT_HZ


FRAME_PERIOD_S = 1.0 / FRAME_RATE_HZ


#: the percentile convention phase 7 already uses: the nearest-rank order statistic, never interpolated
PERCENTILE_QUANTILE = 0.99


PERCENTILE_CONVENTION = (
    "nearest rank: the ceil(0.99 * n)-th smallest measured sample, never an interpolated value"
)


AGE_PERCENTILE_QUANTILE = 0.999


#: the measurement's own controller identities: the sweep is one declared attempt of one declared session
MEASUREMENT_ATTEMPT_ID = "head-search-timing-measurement"


MEASUREMENT_SESSION_ID = "head-search-timing-measurement"


AGE_DEFINITION = (
    "decision_monotonic_s - received_monotonic_s: the monotonic wall-clock interval between the frame's "
    "arrival at the decision loop and the decision that consumed it, which is the base "
    "HeadSearchController's freshness gate compares against max_age_s"
)


FRAME_TIME_DEFINITION = (
    "decision_monotonic_s - frame_monotonic_s: the whole per-frame pipeline cost, from the capture the "
    "frame is stamped with to the decision that consumes it"
)


WARMUP_POLICY = (
    "one frame is rendered and decided before the sweep begins: the first inference of a run pays the "
    "one-time CUDA context and detector initialisation, so a per-frame distribution that included it would "
    "describe the start-up rather than the running pipeline. The warm-up is recorded next to the "
    "distribution instead of being hidden in it, and every sample that is in the distribution is a frame "
    "the sweep really produced"
)


FRAME_CONTRACT_DECLARED_BY = (
    "the design's head search frame contract (plan section 2b records the 10 Hz frame contract among the "
    f"additionally-recorded items as {FRAME_CONTRACT_ITEM}); phase 7's module fixes the rate and refuses "
    "any other, so this declaration cannot widen a cap"
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


#: a whole-number-of-steps check tolerance: one float ulp of a period around 2 ms
_PERIOD_TOLERANCE_S = 1e-12


class CalibrationTimingMeasurementRefused(CalibrationInputsRefused):
    """A sweep-timing refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _refuse(code: str, detail: str) -> CalibrationTimingMeasurementRefused:
    return CalibrationTimingMeasurementRefused(code, detail)


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _number(document, name: str, key: str, *, positive=False, nonnegative=False) -> float:
    """One measured number, or a plain `ValueError` for a caller that passed something else."""

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


def _optional_number(document, key: str) -> float | None:
    if not isinstance(document, Mapping):
        return None
    value = document.get(key)
    return float(value) if _finite(value) else None


def _mapping(name: str, value) -> Mapping:
    if not isinstance(value, Mapping):
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"the declared {name} is not a JSON object")
    return value


def _sequence(name: str, value) -> list:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"the declared {name} is not a list")
    return list(value)


def _interval(name: str, value) -> tuple[float, float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"{name} must be two finite bounds")
    low, high = (float(bound) for bound in value)
    if not math.isfinite(low) or not math.isfinite(high) or low > high:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"{name} must be finite and ordered")
    return low, high


def _digest(path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _cuda_available() -> bool:
    """Whether the declared CUDA device is really there; the measurement never falls back to the CPU."""

    import torch

    return bool(torch.cuda.is_available())
