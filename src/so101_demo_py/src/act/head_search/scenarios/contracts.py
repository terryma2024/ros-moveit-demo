"""Kinds, outcome and refusal codes, expected terminals and small validators of the scenarios."""

from __future__ import annotations

from collections.abc import Mapping
import re

from so101_demo.act.head_search.calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search.fine_correction_episodes.contracts import (
    CAL_FINE_EPISODE_BUDGET_EXHAUSTED,
    CAL_FINE_EPISODE_NO_VERDICT,
    CAL_FINE_EPISODE_NOT_CENTERED,
    CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
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


KIND = "head_search_qualification_scenarios"


RECEIPT_KIND = "head_search_qualification_scenarios_receipt"


PHASE = "scenarios"


ARTIFACT = "scenarios.json"


JOURNAL_ARTIFACT = "scenario-journal.jsonl"


RECEIPT_ARTIFACT = "measurement-receipt.json"


EVIDENCE_DIR = "scenarios"


#: what this document is evidence of, and the one claim it never makes
QUALIFICATION_FIT_WARNING = (
    "these forty scenarios are the plan's scenario evidence and nothing more: they do not by "
    "themselves establish HEAD_SEARCH_QUALIFIED, which the qualifier's aggregate phase owns after the "
    "production smoke and the three anchor restarts have also been evidenced"
)


#: the declared partitions document names the qualification items under this key
QUALIFICATION_SPLIT = "qualification"


#: the three outcomes one scenario can be journaled with
PASSED = "PASSED"


FAILED = "FAILED"


REFUSED = "REFUSED"


#: the codes a *recorded* scenario carries when it ran to a verdict that was not the declared one. They
#: are not producer refusals: the run continues and the aggregate counts them.
CAL_SCENARIO_CUP_NOT_FOUND = "CAL_SCENARIO_CUP_NOT_FOUND"


CAL_SCENARIO_TARGET_AMBIGUOUS = "CAL_SCENARIO_TARGET_AMBIGUOUS"


CAL_SCENARIO_NOT_CENTERED = "CAL_SCENARIO_NOT_CENTERED"


CAL_SCENARIO_BUDGET_EXHAUSTED = "CAL_SCENARIO_BUDGET_EXHAUSTED"


CAL_SCENARIO_UNEXPECTED_LOCK = "CAL_SCENARIO_UNEXPECTED_LOCK"


CAL_SCENARIO_COVERAGE_INCOMPLETE = "CAL_SCENARIO_COVERAGE_INCOMPLETE"


CAL_SCENARIO_NO_VERDICT = "CAL_SCENARIO_NO_VERDICT"


CAL_SCENARIO_DETECTOR_FAILED = "CAL_SCENARIO_DETECTOR_FAILED"


CAL_SCENARIO_OUT_OF_CORRIDOR = "CAL_SCENARIO_OUT_OF_CORRIDOR"


CAL_SCENARIO_FRAME_CADENCE = "CAL_SCENARIO_FRAME_CADENCE"


CAL_SCENARIO_STOP_UNPROVEN = "CAL_SCENARIO_STOP_UNPROVEN"


CAL_SCENARIO_INTERRUPTION_UNPROVEN = "CAL_SCENARIO_INTERRUPTION_UNPROVEN"


CAL_SCENARIO_SCENE_CONTRADICTORY = "CAL_SCENARIO_SCENE_CONTRADICTORY"


CAL_SCENARIO_OWNERSHIP_REFUSED = "CAL_SCENARIO_OWNERSHIP_REFUSED"


CAL_SCENARIO_RUNTIME_UNVERIFIED = "CAL_SCENARIO_RUNTIME_UNVERIFIED"


CAL_SCENARIO_SPLIT_LEAK = "CAL_SCENARIO_SPLIT_LEAK"


CAL_SCENARIO_RUN_ROOT_EXISTS = "CAL_SCENARIO_RUN_ROOT_EXISTS"


#: the outcome codes of a scenario that reached a verdict the plan does not declare for its class
OUTCOME_CODES = (
    CAL_SCENARIO_CUP_NOT_FOUND,
    CAL_SCENARIO_TARGET_AMBIGUOUS,
    CAL_SCENARIO_NOT_CENTERED,
    CAL_SCENARIO_BUDGET_EXHAUSTED,
    CAL_SCENARIO_UNEXPECTED_LOCK,
    CAL_SCENARIO_COVERAGE_INCOMPLETE,
)


#: the codes of a scenario that never reached a verdict, and of the two whole-run refusals
UNMEASURED_CODES = (
    CAL_SCENARIO_NO_VERDICT,
    CAL_SCENARIO_DETECTOR_FAILED,
    CAL_SCENARIO_OUT_OF_CORRIDOR,
    CAL_SCENARIO_FRAME_CADENCE,
    CAL_SCENARIO_STOP_UNPROVEN,
    CAL_SCENARIO_INTERRUPTION_UNPROVEN,
    CAL_SCENARIO_SCENE_CONTRADICTORY,
)


REFUSAL_CODES = (
    CAL_SCENARIO_OWNERSHIP_REFUSED,
    CAL_SCENARIO_RUNTIME_UNVERIFIED,
    CAL_SCENARIO_SPLIT_LEAK,
    CAL_SCENARIO_RUN_ROOT_EXISTS,
    CAL_SCENARIO_COVERAGE_INCOMPLETE,
    *UNMEASURED_CODES,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
    CAL_FINE_EPISODE_BUDGET_EXHAUSTED,
    CAL_FINE_EPISODE_NO_VERDICT,
    CAL_FINE_EPISODE_NOT_CENTERED,
)


#: the plan's own per-condition-class expectation, quoted one class at a time. `left_anchor` and
#: `forward_anchor` are the two anchor-specific classes; `low_light`, `partial_occlusion`,
#: `fast_interruption` and `reacquire_after_stop` are the four that carry a single legal cup and are
#: declared to end on a lock like every other single-cup class.
EXPECTED_TERMINALS = {
    "nominal": ("TARGET_LOCKED",),
    "left_anchor": ("TARGET_LOCKED",),
    "forward_anchor": ("TARGET_LOCKED",),
    "distractor_present": ("TARGET_LOCKED",),
    "two_cups": ("TARGET_AMBIGUOUS",),
    "no_cup": ("TARGET_NOT_FOUND",),
    "low_light": ("TARGET_LOCKED",),
    "partial_occlusion": ("TARGET_LOCKED",),
    "fast_interruption": ("TARGET_LOCKED",),
    "reacquire_after_stop": ("TARGET_LOCKED",),
}


#: the two classes the plan declares as interrupted input: the old attempt ends fail-closed, the stop is
#: proven, the tracker and the lock state are cleared, and the search reacquires under a new attempt
INTERRUPTION_CLASSES = ("fast_interruption", "reacquire_after_stop")


#: `TARGET_NOT_FOUND` is the only clean negative the controller may report, and it is the one it reports
#: when the bounded plan covered the whole required domain without reaching a bound
NOT_FOUND_STATUSES = ("TARGET_NOT_FOUND",)


NOT_FOUND_WITHIN_BOUND_STATUSES = ("TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL",)


#: this producer's own controller identities: the scenarios are one declared session of several attempts
SCENARIO_SESSION_ID = "head-search-qualification-scenarios"


#: how many frames one scenario may spend per attempt before the loop must have reached a verdict
DEFAULT_MAX_FRAMES = 16


#: the try after which the declared interruption is injected: attempt one has decided on two frames, so
#: the stale frame arrives while the sweep is still walking (never after a verdict was already reached)
#: and with a lock run that has already started, so the clear it proves is a real one
DEFAULT_INTERRUPTION_FRAME = 2


#: the wall-clock margin by which the injected frame misses the controller's own freshness gate. It is a
#: harness declaration, recorded in the journal, and it is bounded by the promoted `max_age_s`
#: declaration: the run refuses a margin that does not exceed it.
INTERRUPTION_STALE_MARGIN_S = 0.001


#: the detector's declared model identity when the production configuration names no runtime of its own
DETECTOR_MODEL_ID = "head-search-qualification-scenarios"


#: how many consecutive raw-feedback samples have to sit at or below the promoted stop velocity
STOP_PROOF_SAMPLES = 3


#: one float ulp of a bound around a few radians, the allowance the bounded planner's endpoints use
_BOUND_TOLERANCE_RAD = 1e-12


_CADENCE_TOLERANCE_S = 1e-9


_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CalibrationScenarioRefused(CalibrationInputsRefused):
    """A qualification-scenario refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _refuse(code: str, detail: str) -> CalibrationScenarioRefused:
    return CalibrationScenarioRefused(code, detail)


def _re_raised(call, *args, **kwargs):
    """Run a reused check, re-raising its refusal as this producer's own class, code unchanged."""

    try:
        return call(*args, **kwargs)
    except CalibrationInputsRefused as error:
        raise _refuse(error.code, error.detail) from error


def _partitions_document(partitions) -> Mapping:
    if not isinstance(partitions, Mapping):
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the scenario partitions are not a document, so no qualification item can be shown to be a "
            "declared one",
        )
    return partitions
