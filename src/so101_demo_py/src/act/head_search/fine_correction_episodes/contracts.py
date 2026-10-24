"""Kinds, refusal codes, definitions and validators of the fine-correction episodes."""

from __future__ import annotations

from collections.abc import Mapping
import re

from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search.deadband_measurement.contracts import (
    CAL_DEADBAND_CUP_LOST,
    CAL_DEADBAND_OUT_OF_CORRIDOR,
)
from so101_demo.act.head_search.deadband_measurement.contracts import (
    WARMUP_POLICY as _DEADBAND_WARMUP_POLICY,
)
from so101_demo.act.head_search.timing_measurement.contracts import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
)

SCHEMA_VERSION = 1


KIND = "head_search_calibration_fine_correction_episodes"


RECEIPT_KIND = "head_search_calibration_fine_correction_episode_measurement_receipt"


PHASE = "fine_correction_episodes"


ARTIFACT = "fine-correction-episodes.json"


RECEIPT_ARTIFACT = "measurement-receipt.json"


#: the warm-up both closed-loop producers declare and exclude: the deadband measurement's own policy text,
#: so the three producers that pay the one-off start-up cost declare it in the same words
WARMUP_POLICY = _DEADBAND_WARMUP_POLICY


#: the split whose seeds may bound the fine-correction numbers, and the split that may never do so
HELD_OUT_SPLIT = "held_out_evaluation"


CALIBRATION_SPLIT = "calibration"


#: the codes this producer raises when it refuses to write a document at all
CAL_FINE_EPISODE_SPLIT_LEAK = "CAL_FINE_EPISODE_SPLIT_LEAK"


CAL_FINE_EPISODE_OUT_OF_CORRIDOR = "CAL_FINE_EPISODE_OUT_OF_CORRIDOR"


CAL_FINE_EPISODE_BUDGET_EXHAUSTED = "CAL_FINE_EPISODE_BUDGET_EXHAUSTED"


CAL_FINE_EPISODE_CORRECTION_MISMATCH = "CAL_FINE_EPISODE_CORRECTION_MISMATCH"


CAL_FINE_EPISODE_NO_VERDICT = "CAL_FINE_EPISODE_NO_VERDICT"


CAL_FINE_EPISODE_DETECTOR_FAILED = "CAL_FINE_EPISODE_DETECTOR_FAILED"


CAL_FINE_EPISODE_SCENE_CONTRADICTORY = "CAL_FINE_EPISODE_SCENE_CONTRADICTORY"


CAL_FINE_EPISODE_NO_SUCCESS = "CAL_FINE_EPISODE_NO_SUCCESS"


CAL_FINE_EPISODE_NO_CORRECTION_NEEDED = "CAL_FINE_EPISODE_NO_CORRECTION_NEEDED"


#: the codes a *recorded* episode carries when it ran to a verdict that was not a lock; they are not
#: producer refusals (the document still exists), but two of them (`BUDGET_EXHAUSTED`, and any recorded
#: episode whose motion left its corridor) make the whole document unmeasurable
CAL_FINE_EPISODE_CUP_NOT_FOUND = "CAL_FINE_EPISODE_CUP_NOT_FOUND"


CAL_FINE_EPISODE_TARGET_AMBIGUOUS = "CAL_FINE_EPISODE_TARGET_AMBIGUOUS"


CAL_FINE_EPISODE_NOT_CENTERED = "CAL_FINE_EPISODE_NOT_CENTERED"


EPISODE_FAILURE_CODES = (
    CAL_FINE_EPISODE_CUP_NOT_FOUND,
    CAL_FINE_EPISODE_TARGET_AMBIGUOUS,
    CAL_FINE_EPISODE_NOT_CENTERED,
    CAL_FINE_EPISODE_BUDGET_EXHAUSTED,
)


#: every code this producer can raise, its own and the three modules it reuses (the timing module's settle
#: and time-base rules, the deadband module's detector and corridor checks)
REFUSAL_CODES = (
    CAL_FINE_EPISODE_SPLIT_LEAK,
    CAL_FINE_EPISODE_OUT_OF_CORRIDOR,
    CAL_FINE_EPISODE_BUDGET_EXHAUSTED,
    CAL_FINE_EPISODE_CORRECTION_MISMATCH,
    CAL_FINE_EPISODE_NO_VERDICT,
    CAL_FINE_EPISODE_DETECTOR_FAILED,
    CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
    CAL_FINE_EPISODE_NO_SUCCESS,
    CAL_FINE_EPISODE_NO_CORRECTION_NEEDED,
    CAL_FINE_EPISODE_CUP_NOT_FOUND,
    CAL_FINE_EPISODE_TARGET_AMBIGUOUS,
    CAL_FINE_EPISODE_NOT_CENTERED,
    CAL_DEADBAND_CUP_LOST,
    CAL_DEADBAND_OUT_OF_CORRIDOR,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    CAL_TIMING_DEVICE_UNAVAILABLE,
)


#: exactly the keys phase 6 reads off every recorded episode, and nothing else
RECORD_KEYS = ("episode_id", "split", "succeeded", "fine_corrections", "fine_corrections_rad")


#: this measurement's own controller identities: the episodes are one declared attempt of one session
MEASUREMENT_ATTEMPT_ID = "head-search-fine-correction-episodes"


MEASUREMENT_SESSION_ID = "head-search-fine-correction-episodes"


#: how many frames one episode may spend before the loop must have reached a verdict
DEFAULT_MAX_FRAMES = 16


#: the harness's own measurement budget. It is an *instrument* limit, not a calibrated value: it has to be
#: generous enough that no episode is censored by it (a censored episode refuses the whole document), and
#: the production declaration it stands in for is `values.max_fine_corrections` / `max_fine_total_rad` of
#: the production search configuration, recorded beside it in the document
DEFAULT_MEASUREMENT_BUDGET = {"max_fine_corrections": 8, "max_fine_total_rad": 2.0}


#: the detector's declared model identity when the production configuration names no runtime of its own
DETECTOR_MODEL_ID = "head-search-fine-correction-episodes"


#: one float ulp of a bound around a few radians, the allowance the bounded planner's endpoints use
_BOUND_TOLERANCE_RAD = 1e-12


#: the absolute tolerance the recorded magnitudes are compared against the controller's own total with
_CORRECTION_TOLERANCE_RAD = 1e-12


CORRECTION_DEFINITION = (
    "a fine correction is a move the production controller made while a single cup was visible and whose "
    "decision status is CENTER_CUP: the controller's own law sets the target to the settled neck angle "
    "plus the bearing correction, so the magnitude is |target - neck_yaw_rad| of that frame. A move to the "
    "next stop of the bounded plan carries the status SEARCH_CUP and is a coarse move, never a correction; "
    "a decision that keeps the target is a hold. The count and the sum are checked against the "
    "controller's own fine_count and fine_angle before they are written"
)


SUCCESS_DEFINITION = (
    "an episode succeeded when the production controller returned found=True with the terminal status "
    "TARGET_LOCKED, which is three consecutive frames with the detected cup's centre inside "
    "center_deadband_px of the principal point and inside vertical_bounds_px, on one detection track. "
    "Every other terminal verdict is recorded with its own failure code and no correction count"
)


CORRIDOR_DEFINITION = (
    "two declared corridors, and nothing is ever clamped. The coarse corridor is the intersection of the "
    "seal's required_search_domain_rad and its lock_valid_neck_rad and bounds the anchor the episode "
    "starts from and every stop of the bounded sweep. The fine corridor is the seal's lock_valid_neck_rad "
    "- the interval the seal declares a lock valid in and the interval the controller's own plan clamps "
    "its stops to - and bounds every fine correction and every settled neck angle. The required domain is "
    "the coverage the coarse sweep owes, not a bound on the centring move: a fine correction outside it "
    "is recorded as an excursion and never refused for that reason alone"
)


SCENE_DEFINITION = (
    "the scene of an episode is prepared by the head dataset's own renderer from the seed the held-out "
    "split declares: the same dataset profile, the same MuJoCoDatasetRenderer._prepare and the same "
    "condition-class-to-cup-count convention the retained episodes8 recording used, with "
    "numpy.random.default_rng(seed). The cup is therefore where the dataset put it and not where the "
    "seal's anchor sample is, and every episode records the prepared cup's position read back out of the "
    "stepped model"
)


BUDGET_DEFINITION = (
    "the harness's own measurement budget for one episode (max_fine_corrections, max_fine_total_rad). It "
    "is an instrument limit: an episode that reached it is recorded as BUDGET_EXHAUSTED and refuses the "
    "whole document, because an episode that hit the instrument's limit is no evidence that the limit was "
    "enough. The budget is never the calibrated value; the production declaration stands beside it"
)


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CalibrationFineCorrectionRefused(CalibrationInputsRefused):
    """A fine-correction episode refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _refuse(code: str, detail: str) -> CalibrationFineCorrectionRefused:
    return CalibrationFineCorrectionRefused(code, detail)


def _re_raised(call, *args, **kwargs):
    """Run a reused check, re-raising its refusal as this producer's own class, code unchanged.

    The settle rule, the stop classification, the time-base proof, the detector guard and the corridor
    check belong to the timing and deadband modules; a caller that records `fine_correction_episodes`
    reads one class and one code vocabulary, so they are re-raised here with the same code rather than
    leaking another module's exception type.
    """

    try:
        return call(*args, **kwargs)
    except CalibrationInputsRefused as error:
        raise _refuse(error.code, error.detail) from error


def _partitions_document(partitions) -> Mapping:
    if not isinstance(partitions, Mapping):
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the scenario partitions are not a document, so no held-out seed can be shown to belong to a "
            "declared split",
        )
    return partitions
