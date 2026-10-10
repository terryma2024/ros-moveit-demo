"""Task 14 Step 3's 40 serial qualification scenarios, their per-scenario journal and their aggregate.

Plan Task 14 Step 3 asks for ten condition classes times four unseen seeds, run **one at a time**:
"Legal single cup ends ``TARGET_LOCKED``; two cups end ``TARGET_AMBIGUOUS``; no cup ends
``TARGET_NOT_FOUND`` only with complete coverage; interrupted input ends the old attempt fail-closed,
proves stop, clears tracker/lock state and reacquires under a new attempt. Every scenario has zero wrong
locks, zero unsafe commands, valid timing and CUDA-only evidence."

Nothing in the frozen runtime produces that: the closest closed-loop producer,
``measure-fine-correction-episodes``, refuses every qualification seed by construction
(``declared_split_seeds`` only accepts a declared split, and its document is a fine-correction measurement
of one anchor, not a per-scenario journal), and the installed smoke proves planning *coverage* rather than
a live search. This module is the installed producer of the missing phase.

What it is:

* :func:`qualification_scenarios` reads the **tracked** partition document
  (``config/act/head-search-scenario-partitions-v1.json``) and returns its ``qualification`` items in
  declaration order - seed, scene group, condition class and anchor. A seed of another split is refused
  (``CAL_SCENARIO_SPLIT_LEAK``): the qualification scenes are never the calibration scenes.
* :func:`expected_terminals` is the per-condition-class expectation, taken **verbatim** from the plan's
  own sentence above rather than invented here: a one-cup class passes on ``TARGET_LOCKED``, ``two_cups``
  passes on ``TARGET_AMBIGUOUS``, ``no_cup`` passes on ``TARGET_NOT_FOUND``.
* :func:`run_scenario` is the closed loop, and it is pure: the plant and the detector are injected. It
  drives the production ``HeadSearchController`` - its own bounded plan, its own freshness and skew gates,
  its own three-frame lock rule - from the item's own declared anchor, checks every commanded target
  against its corridor instead of clamping it, and returns one :func:`scenario_journal_entry`.
* :func:`check_frame_cadence` proves the 10 Hz frame contract: no duplicate, no backward and no
  undeclared gap, frames never faster than the declared frame period and never slower than the settle
  budget plus that period.
* :func:`stop_proof` proves the stop: at least three consecutive raw-feedback samples at or below the
  promoted ``stop_velocity_rad_s`` while the position error is at or below ``goal_tolerance_rad``.
* :func:`aggregate_scenarios` counts passed, failed and refused per condition class and per anchor, and
  **never** claims the qualification verdict - that belongs to the qualifier's ``aggregate`` phase, which
  this round does not implement.

What it refuses rather than fabricates (the codes are :data:`REFUSAL_CODES`):

* the whole run, before a single scene is prepared, when the exclusive-ownership gate refuses
  (:data:`CAL_SCENARIO_OWNERSHIP_REFUSED`) or the runtime of record does not hold
  (:data:`CAL_SCENARIO_RUNTIME_UNVERIFIED`);
* a scenario whose terminal outcome is not the one its condition class declares - including a **wrong
  lock**, a lock in a class that must not lock (:data:`CAL_SCENARIO_UNEXPECTED_LOCK`);
* a ``no_cup`` scenario that stopped at a bound before the sweep covered the required domain
  (:data:`CAL_SCENARIO_COVERAGE_INCOMPLETE`): "not found" is only a clean negative with complete coverage;
* a scenario whose frames violate the frame contract (:data:`CAL_SCENARIO_FRAME_CADENCE`) or whose
  terminal stop is unproven (:data:`CAL_SCENARIO_STOP_UNPROVEN`);
* a scenario that could not run to a verdict at all - the frame budget, a detector that raised, a target
  outside its corridor, a centring budget that ran out (:data:`CAL_SCENARIO_NO_VERDICT` /
  ``CAL_SCENARIO_DETECTOR_FAILED`` / ``CAL_SCENARIO_OUT_OF_CORRIDOR`` / ``CAL_SCENARIO_BUDGET_EXHAUSTED``).

A scenario that merely did not succeed - the cup was never found, a frame held two cups, the cup could
not be centred - is **recorded** with its own outcome and failure code, not raised: the run has to reach
all forty scenarios, and a refusal that stopped the run at scenario 7 would measure nothing about the
other thirty-three. Whole-run refusals are only the two preflight ones above.

The only part that touches MuJoCo, the dataset renderer, the detector or a GPU is the producer's scene
preparation, the plant and the production detector factory, and all three import their dependencies inside
the call. The detector is the production head detector (``HeadRgbDetector`` over ``YoloSegDetector``) at
the selected candidate's declared head operating point, and this producer never falls back to the CPU.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_deadband_measurement import (
    CalibrationDeadbandMeasurementRefused,
    MujocoClosedLoopPlant,
    _anchor_requests,
    _corridor_check,
    _detections,
    _frame_summary,
    _plant_request,
    build_production_head_detector,
    detector_operating_point,
    motion_corridor_rad,
)
from so101_demo.act.head_search_fine_correction_episodes import (
    CAL_FINE_EPISODE_BUDGET_EXHAUSTED,
    CAL_FINE_EPISODE_NO_VERDICT,
    CAL_FINE_EPISODE_NOT_CENTERED,
    CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
    CAL_FINE_EPISODE_SPLIT_LEAK,
    MujocoEpisodePlant,
    _budget_binding,
    _cup_drift_m,
    cup_count_for_condition_class,
    fine_corridor_rad,
    prepare_episode_scene,
    required_domain_excursion_rad,
    scenario_name_for_cup_count,
    scene_preparation_request,
    verify_correction_consistency,
)
from so101_demo.act.head_search_mujoco_measurements import read_mujoco_timestep
from so101_demo.act.head_search_search_params import LOCK_FRAMES
from so101_demo.act.head_search_timing_measurement import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    DEFAULT_MAX_SETTLE_S,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
    SETTLE_CONSECUTIVE_STEPS,
    SIMULATION_TIME_BASE,
    _declared_weights,
    _digest,
    _finite,
    classify_stop,
    read_control_period,
    runtime_identity as measurement_runtime_identity,
    verify_simulation_time_base,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1

KIND = "head_search_qualification_scenarios"
RECEIPT_KIND = "head_search_qualification_scenarios_receipt"
PHASE = "scenarios"

ARTIFACT = "scenarios.json"
JOURNAL_ARTIFACT = "scenario-journal.jsonl"
RECEIPT_ARTIFACT = "measurement-receipt.json"
#: one directory of per-scenario evidence documents, so a reviewer never has to slice the journal
EVIDENCE_DIR = "scenarios"

#: what this document is evidence of, and the one claim it never makes
QUALIFICATION_FIT_WARNING = (
    "these forty scenarios are the plan Task 14 Step 3 evidence and nothing more: they do not by "
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
#: the codes a recorded scenario carries when it never reached a verdict at all
CAL_SCENARIO_NO_VERDICT = "CAL_SCENARIO_NO_VERDICT"
CAL_SCENARIO_DETECTOR_FAILED = "CAL_SCENARIO_DETECTOR_FAILED"
CAL_SCENARIO_OUT_OF_CORRIDOR = "CAL_SCENARIO_OUT_OF_CORRIDOR"
CAL_SCENARIO_FRAME_CADENCE = "CAL_SCENARIO_FRAME_CADENCE"
CAL_SCENARIO_STOP_UNPROVEN = "CAL_SCENARIO_STOP_UNPROVEN"
CAL_SCENARIO_INTERRUPTION_UNPROVEN = "CAL_SCENARIO_INTERRUPTION_UNPROVEN"
CAL_SCENARIO_SCENE_CONTRADICTORY = "CAL_SCENARIO_SCENE_CONTRADICTORY"
#: the two whole-run refusals: the run never starts when either of these does not hold
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
#: the tolerance the frame cadence compares simulation intervals with
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


# --- the declared qualification list ---------------------------------------------------------------


def _partitions_document(partitions) -> Mapping:
    if not isinstance(partitions, Mapping):
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the scenario partitions are not a document, so no qualification item can be shown to be a "
            "declared one",
        )
    return partitions


def qualification_items(partitions) -> list[dict]:
    """Every declared qualification item, in declaration order, or the refusal that stops the producer."""

    document = _partitions_document(partitions)
    declared = document.get(QUALIFICATION_SPLIT)
    if (
        isinstance(declared, (str, bytes))
        or not isinstance(declared, Sequence)
        or not declared
    ):
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the scenario partitions declare no {QUALIFICATION_SPLIT!r} list, so the forty qualification "
            f"scenarios are not declared anywhere",
        )
    items: list[dict] = []
    seen: set[int] = set()
    for position, item in enumerate(declared):
        if not isinstance(item, Mapping):
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"qualification item {position} is not a document, so its seed, condition class and anchor "
                f"are not declared",
            )
        seed = item.get("seed")
        if type(seed) is not int or isinstance(seed, bool):
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"qualification item {position} declares the seed {seed!r}, which is not a whole number",
            )
        if seed in seen:
            raise ValueError(f"the qualification seed {seed} is declared twice")
        seen.add(seed)
        condition_class = item.get("condition_class")
        anchor = item.get("anchor")
        if type(condition_class) is not str or not condition_class:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"qualification item {position} (seed {seed}) declares no condition class",
            )
        if type(anchor) is not str or not anchor:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"qualification item {position} (seed {seed}) declares no anchor",
            )
        items.append(
            {
                "seed": seed,
                "scene_group_id": str(item.get("scene_group_id", "")),
                "condition_class": condition_class,
                "anchor": anchor,
            }
        )
    return items


def qualification_scenarios(partitions, *, seeds=None) -> list[dict]:
    """The declared qualification items, restricted to a declared subset, or the refusal that stops it.

    The partitions are the single tracked source of the head-search seed partitions, so a seed of another
    split - a calibration seed in particular - is refused rather than qualified: the qualification scenes
    are never the scenes the seventeen values were calibrated on.
    """

    document = _partitions_document(partitions)
    declared = qualification_items(document)
    if seeds is None:
        return declared
    by_seed = {item["seed"]: item for item in declared}
    other = {
        str(name): {int(seed) for seed in value if type(seed) is int and not isinstance(seed, bool)}
        for name, value in document.items()
        if name != QUALIFICATION_SPLIT
        and isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and value
        and all(type(seed) is int and not isinstance(seed, bool) for seed in value)
    }
    chosen: list[dict] = []
    offered: set[int] = set()
    for seed in seeds:
        if type(seed) is not int or isinstance(seed, bool):
            raise ValueError(f"every declared seed must be a whole number: {seed!r}")
        if seed in offered:
            raise ValueError(f"the seed {seed} is declared twice")
        offered.add(seed)
        if seed in by_seed:
            chosen.append(by_seed[seed])
            continue
        for name, members in other.items():
            if seed in members:
                raise _refuse(
                    CAL_SCENARIO_SPLIT_LEAK,
                    f"the seed {seed} belongs to the {name!r} split, which may never be qualified: only "
                    f"the declared {QUALIFICATION_SPLIT!r} items may, because the qualification scenes are "
                    f"never the scenes the seventeen values were calibrated on",
                )
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the seed {seed} belongs to no split of the scenario partitions, so the scene it would "
            f"prepare is not a declared one",
        )
    if not chosen:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "no declared qualification item was offered, so this producer would carry no scenario at all",
        )
    return chosen


# --- the per-condition-class expectations ----------------------------------------------------------


def expected_terminals(condition_class: str) -> tuple[str, ...]:
    """The terminal statuses the plan declares for one condition class, and nothing this module chose.

    Plan Task 14 Step 3: "Legal single cup ends ``TARGET_LOCKED``; two cups end ``TARGET_AMBIGUOUS``; no
    cup ends ``TARGET_NOT_FOUND`` only with complete coverage". A class the plan does not name refuses,
    because a scenario whose expected outcome is undeclared cannot be judged.
    """

    if type(condition_class) is not str or condition_class not in EXPECTED_TERMINALS:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the condition class {condition_class!r} declares no expected terminal status in plan Task 14 "
            f"Step 3, so a scenario of that class cannot be judged; the declared classes are "
            f"{sorted(EXPECTED_TERMINALS)}",
        )
    return tuple(EXPECTED_TERMINALS[condition_class])


def requires_interruption(condition_class: str) -> bool:
    """Whether the plan declares this class as interrupted input that has to reacquire."""

    return condition_class in INTERRUPTION_CLASSES


def declared_cup_count(condition_class: str) -> int:
    """How many cups the recorder's own convention places in one class's scene."""

    return cup_count_for_condition_class(condition_class)


# --- the 10 Hz frame cadence -----------------------------------------------------------------------


def check_frame_cadence(
    frames, *, frame_period_s: float, max_settle_s: float, tolerance_s: float = _CADENCE_TOLERANCE_S
) -> dict:
    """One attempt's frames against the declared frame contract, or the numbers that say why not.

    The contract is the design's 10 Hz: a frame is produced at most once per declared frame period of
    simulation time and never before the commanded target has settled, so the achieved interval is that
    settle time plus the remainder that carries the loop to the next frame boundary. The check therefore
    refuses a **duplicate** stamp (no interval at all), a **backward** stamp (a frame older than its
    predecessor), a frame faster than the declared period (``too_fast``), and a gap larger than the
    settle budget plus one frame period, which no declared settle can produce (``undeclared_gap``).
    """

    if not _finite(frame_period_s) or float(frame_period_s) <= 0.0:
        raise ValueError("the frame cadence needs a positive finite frame period")
    if not _finite(max_settle_s) or float(max_settle_s) <= 0.0:
        raise ValueError("the frame cadence needs a positive finite settle budget")
    period = float(frame_period_s)
    if not math.isclose(FRAME_RATE_HZ, 1.0 / period, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(
            f"the frame cadence is checked against {1.0 / period} Hz, but the design fixes the "
            f"{FRAME_RATE_HZ} Hz frame contract"
        )
    if isinstance(frames, (str, bytes)) or not isinstance(frames, Sequence):
        raise ValueError("the frames of one attempt must be a sequence")

    intervals: list[float | None] = []
    duplicate = backward = too_fast = undeclared_gap = gap = 0
    previous = None
    for index, frame in enumerate(frames):
        if not isinstance(frame, Mapping):
            raise ValueError("every recorded frame must be a mapping")
        stamp = frame.get("frame_sim_s")
        if not _finite(stamp):
            raise ValueError(f"frame {index} records no finite frame_sim_s")
        stamp = float(stamp)
        if previous is None:
            intervals.append(None)
            previous = stamp
            continue
        interval = stamp - previous
        intervals.append(interval)
        if interval < -tolerance_s:
            backward += 1
        elif abs(interval) <= tolerance_s:
            duplicate += 1
        elif interval < period - tolerance_s:
            too_fast += 1
        elif interval > max_settle_s + period + tolerance_s:
            undeclared_gap += 1
        elif interval > period + tolerance_s:
            gap += 1
        previous = stamp

    measured = [value for value in intervals if value is not None]
    span = None if len(frames) < 2 else float(frames[-1]["frame_sim_s"]) - float(frames[0]["frame_sim_s"])
    achieved = None if not span or span <= 0.0 else len(measured) / span
    continuous = not (duplicate or backward or too_fast or undeclared_gap)
    return {
        "frame_rate_hz": FRAME_RATE_HZ,
        "frame_period_s": period,
        "max_settle_s": float(max_settle_s),
        "tolerance_s": float(tolerance_s),
        "frame_count": len(frames),
        "interval_count": len(measured),
        "intervals_s": measured,
        "min_interval_s": min(measured) if measured else None,
        "max_interval_s": max(measured) if measured else None,
        "span_s": span,
        "achieved_rate_hz": achieved,
        "duplicate_count": duplicate,
        "backward_count": backward,
        "too_fast_count": too_fast,
        "gap_count": gap,
        "undeclared_gap_count": undeclared_gap,
        "continuous": continuous,
        "definition": (
            "a frame is produced at most once per declared frame period of simulation time and never "
            "before the commanded target has settled, so the achieved interval between two frames is that "
            "settle time plus the remainder that carries the loop to the next frame boundary; a duplicate, "
            "a backward stamp, an interval shorter than the frame period or one longer than the settle "
            "budget plus one frame period all violate the contract"
        ),
    }


# --- the stop proof --------------------------------------------------------------------------------


#: how many held samples the stop proof may spend before it must have three consecutive qualifying ones
STOP_PROOF_WINDOW = 6

SETTLE_PROOF_DEFINITION = (
    "a commanded stop is settled when the neck reached its target inside goal_tolerance_rad and held a "
    "velocity at or below the controller's declared settle_velocity_rad_s for settle_consecutive_steps "
    "consecutive control steps, which is the rule the plant's own settle tracker applies and the rule the "
    "timing measurement's classify_stop refuses an unsettled stop on"
)

STOP_PROOF_DEFINITION = (
    "the neck is held at the stop and the harness takes one raw feedback sample per held settle; a sample "
    "qualifies when its measured neck velocity is within the promoted stop_velocity_rad_s, and the proof is "
    "complete at the THIRD CONSECUTIVE qualifying sample (no qualifying sample skipped, and two quiet "
    "samples between two loud ones are not a proof). The samples are the MuJoCo plant's own velocity "
    "readbacks at the harness's declared settle granularity: this producer starts no ROS node "
    "(ros_nodes_started false), so the production feedback topic the phase-7 stop proof consumes is not the "
    "path these samples come from, and the journal says so"
)


def settle_proof(
    stops, *, settle_velocity_rad_s: float, goal_tolerance_rad: float, settle_consecutive_steps: int
) -> dict:
    """Every commanded stop's own settle evidence, or the stops that did not settle.

    A stop that was never reached or never held the declared settle rule cannot be observed, so a scenario
    that carries one is unmeasured rather than failed.
    """

    if not _finite(settle_velocity_rad_s) or float(settle_velocity_rad_s) <= 0.0:
        raise ValueError("the settle proof needs a positive finite settle velocity")
    if not _finite(goal_tolerance_rad) or float(goal_tolerance_rad) < 0.0:
        raise ValueError("the settle proof needs a finite non-negative position tolerance")
    if type(settle_consecutive_steps) is not int or isinstance(settle_consecutive_steps, bool) or settle_consecutive_steps < 1:
        raise ValueError("the settle proof needs a positive whole number of consecutive control steps")
    if isinstance(stops, (str, bytes)) or not isinstance(stops, Sequence):
        raise ValueError("the stops of one attempt must be a sequence")

    records = []
    unproven: list[int] = []
    for position, stop in enumerate(stops):
        if not isinstance(stop, Mapping):
            raise ValueError("every recorded stop must be a mapping")
        index = stop.get("index")
        index = position if type(index) is not int or isinstance(index, bool) else int(index)
        samples = stop.get("quiet_steps")
        samples = 0 if type(samples) is not int or isinstance(samples, bool) else samples
        velocity = stop.get("final_velocity_rad_s")
        error = stop.get("final_position_error_rad")
        proven = (
            stop.get("settled") is True
            and stop.get("reached") is True
            and samples >= int(settle_consecutive_steps)
            and _finite(velocity)
            and abs(float(velocity)) <= float(settle_velocity_rad_s) + _BOUND_TOLERANCE_RAD
            and _finite(error)
            and abs(float(error)) <= float(goal_tolerance_rad) + _BOUND_TOLERANCE_RAD
        )
        if not proven:
            unproven.append(index)
        records.append(
            {
                "index": index,
                "kind": stop.get("kind"),
                "target_rad": stop.get("target_rad"),
                "settled": stop.get("settled") is True,
                "reached": stop.get("reached") is True,
                "consecutive_samples": samples,
                "final_velocity_rad_s": None if not _finite(velocity) else float(velocity),
                "final_position_error_rad": None if not _finite(error) else float(error),
                "proven": proven,
            }
        )
    return {
        "proven": bool(records) and not unproven,
        "settle_velocity_rad_s": float(settle_velocity_rad_s),
        "goal_tolerance_rad": float(goal_tolerance_rad),
        "settle_consecutive_steps": int(settle_consecutive_steps),
        "stop_count": len(records),
        "unproven_stops": unproven,
        "stops": records,
        "definition": SETTLE_PROOF_DEFINITION,
    }


def stop_proof(
    samples,
    *,
    velocity_limit_rad_s: float,
    required_samples: int = STOP_PROOF_SAMPLES,
) -> dict:
    """The held stop proof: three consecutive raw feedback samples at or below the promoted velocity.

    A sample qualifies when its measured neck velocity is within ``stop_velocity_rad_s``; the proof is
    complete at the third **consecutive** qualifying sample, and a non-qualifying sample resets the run, so
    two quiet samples between two loud ones are not a proof. A sample list that never carried that run is
    unproven, and an empty list is unproven rather than vacuously true.
    """

    if type(required_samples) is not int or isinstance(required_samples, bool) or required_samples < 1:
        raise ValueError("the stop proof needs a positive whole number of consecutive samples")
    if not _finite(velocity_limit_rad_s) or float(velocity_limit_rad_s) <= 0.0:
        raise ValueError("the stop proof needs a positive finite velocity limit")
    if isinstance(samples, (str, bytes)) or not isinstance(samples, Sequence):
        raise ValueError("the stop proof samples must be a sequence")

    limit = float(velocity_limit_rad_s)
    records = []
    run = longest = 0
    qualifying = 0
    for position, sample in enumerate(samples):
        if not isinstance(sample, Mapping):
            raise ValueError("every stop-proof sample must be a mapping")
        velocity = sample.get("velocity_rad_s")
        measured = None if not _finite(velocity) else float(velocity)
        qualified = measured is not None and abs(measured) <= limit + _BOUND_TOLERANCE_RAD
        if qualified:
            run += 1
            qualifying += 1
            longest = max(longest, run)
        else:
            run = 0
        records.append(
            {
                "index": position,
                "velocity_rad_s": measured,
                "settled": sample.get("settled") is True,
                "reached": sample.get("reached") is True,
                "position_error_rad": (
                    None if not _finite(sample.get("position_error_rad")) else float(sample["position_error_rad"])
                ),
                "qualified": qualified,
                "consecutive_run": run,
            }
        )
    return {
        "proven": longest >= int(required_samples),
        "required_samples": int(required_samples),
        "longest_consecutive_run": longest,
        "qualifying_samples": qualifying,
        "sample_count": len(records),
        "velocity_limit_rad_s": limit,
        "samples": records,
        "held_at_rad": None,
        "definition": STOP_PROOF_DEFINITION,
    }


# --- the closed loop -------------------------------------------------------------------------------


def _scenario_declaration(scenario) -> dict:
    """One declared qualification item, with the expectation its condition class carries."""

    if not isinstance(scenario, Mapping):
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "a scenario is not a document, so its seed, condition class and anchor are not declared",
        )
    seed = scenario.get("seed")
    if type(seed) is not int or isinstance(seed, bool):
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"a scenario declares the seed {seed!r}, which is not a whole number",
        )
    condition_class = scenario.get("condition_class")
    anchor = scenario.get("anchor")
    if type(anchor) is not str or not anchor:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING, f"the scenario {seed} declares no anchor"
        )
    terminals = expected_terminals(condition_class)
    cup_count = declared_cup_count(condition_class)
    if cup_count < 0:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the condition class {condition_class!r} declares the cup count {cup_count}",
        )
    return {
        "seed": seed,
        "scene_group_id": str(scenario.get("scene_group_id", "")),
        "condition_class": str(condition_class),
        "anchor": anchor,
        "expected_terminals": list(terminals),
        "cup_count": cup_count,
    }


def _coverage_of(controller, *, required_domain_rad) -> dict:
    """How much of the required search domain the bounded plan covered before the verdict."""

    plan = getattr(controller, "plan", None)
    targets = [] if plan is None else [float(value) for value in plan.targets_rad]
    commanded = targets[: int(getattr(controller, "plan_index", 0))]
    low, high = (float(bound) for bound in required_domain_rad)
    first = min(commanded) if commanded else None
    last = max(commanded) if commanded else None
    return {
        "required_search_domain_rad": [low, high],
        "planned_stop_count": len(targets),
        "commanded_stop_count": len(commanded),
        "commanded_stop_points_rad": commanded,
        "first_stop_rad": first,
        "last_stop_rad": last,
        "reached_bound": bool(plan is not None and not plan.coverage_complete),
        "complete": bool(plan is not None and plan.coverage_complete),
        "definition": (
            "complete coverage means the sealed required search domain is covered by a sweep whose stops "
            "all lie inside the seal's lock-valid interval, so reaching the end of the plan without a "
            "candidate is a clean negative rather than a bound the sweep could not pass"
        ),
    }


def run_scenario(
    *,
    controller_config: Mapping,
    plant,
    detector,
    coarse_corridor_rad,
    fine_corridor_rad,
    scenario: Mapping,
    stop_velocity_rad_s: float,
    attempt_ids: Sequence[str] | None = None,
    interruption: bool = False,
    interruption_frame: int = DEFAULT_INTERRUPTION_FRAME,
    interruption_margin_s: float = INTERRUPTION_STALE_MARGIN_S,
    max_frames: int = DEFAULT_MAX_FRAMES,
    settle_consecutive_steps: int = SETTLE_CONSECUTIVE_STEPS,
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
    frame_period_s: float = FRAME_PERIOD_S,
    evidence: Mapping | None = None,
    clock=time.monotonic,
) -> dict:
    """One qualification scenario's closed loop, from its declared anchor to its journalled outcome.

    The production ``HeadSearchController`` is driven attempt by attempt: it emits a target, the plant
    steps the sealed neck to it and settles, the head camera renders, the detector finds the cup, and the
    controller consumes that frame and its feedback to emit the next target. Every stop of the bounded
    plan is checked against the coarse corridor and every fine correction and settled angle against the
    fine corridor, before it is commanded - nothing is ever clamped. The settle rule and the simulation
    time base are the timing module's own; the correction count and magnitudes are checked against the
    controller's own counters before they are returned.

    An ``interruption`` scenario runs two attempts: the first is stopped by a frame that misses the
    controller's own freshness gate (``INPUT_STALE``), the stop is commanded and proven, and the second
    runs under a **new** ``attempt_id`` with the detector's tracker reset. That is the plan's "interrupted
    input ends the old attempt fail-closed, proves stop, clears tracker/lock state and reacquires under a
    new attempt", and every part of it is recorded rather than asserted.

    The returned entry is the per-scenario journal entry: it carries the declared seed, condition class
    and anchor, whether the cup was found and locked, the stop proof, the frame cadence, the fine
    correction count and cumulative travel, the terminal status and the evidence that reproduces it.
    """

    from so101_demo.act.search import HeadSearchController

    if type(max_frames) is not int or isinstance(max_frames, bool) or max_frames < 1:
        raise ValueError("a scenario needs a positive whole frame budget")
    if type(interruption_frame) is not int or isinstance(interruption_frame, bool) or interruption_frame < 1:
        raise ValueError("the declared interruption frame must be a positive whole number")
    if not _finite(interruption_margin_s) or float(interruption_margin_s) <= 0.0:
        raise ValueError("the declared interruption margin must be positive and finite")
    timestep = getattr(plant, "simulation_timestep_s", None)
    if not _finite(timestep) or float(timestep) <= 0.0:
        raise ValueError("the plant must declare the simulation timestep its stops were stepped at")

    declared = _scenario_declaration(scenario)
    config = dict(controller_config)
    coarse_low, coarse_high = (float(bound) for bound in coarse_corridor_rad)
    fine_low, fine_high = (float(bound) for bound in fine_corridor_rad)
    required_domain = [float(bound) for bound in config["required_search_domain_rad"]]
    # the declared anchor is where the search *starts*, so it is bounded by the interval the seal declares
    # a lock valid in (`lock_valid_neck_rad`, this producer's fine corridor), not by the intersection the
    # *sweep stops* have to stay inside: the plan's own `default` anchor starts at 0.1 rad, outside the
    # required search domain the sweep owes, and 14 of the 40 declared scenarios start there. A start
    # outside the seal's own interval is a declaration error and stops the whole run.
    _scenario_corridor_check(
        angle_rad=float(config["search_start_rad"]),
        corridor_rad=(fine_low, fine_high),
        what=f"declared search start of the scenario {declared['seed']}",
    )
    if not _finite(stop_velocity_rad_s) or float(stop_velocity_rad_s) <= 0.0:
        raise ValueError("a scenario needs the promoted stop velocity its stop proof is judged against")
    stop_limit = float(stop_velocity_rad_s)
    goal_tolerance = float(config["goal_tolerance_rad"])

    default_attempts = [f"{config['attempt_id']}-attempt-1"]
    if interruption:
        default_attempts.append(f"{config['attempt_id']}-attempt-2")
    declared_attempts = list(attempt_ids) if attempt_ids is not None else default_attempts
    if len(declared_attempts) != (2 if interruption else 1):
        raise ValueError(
            f"a scenario declares {len(declared_attempts)} attempt ids for "
            f"interruption={interruption!r}"
        )
    if len(set(declared_attempts)) != len(declared_attempts):
        raise ValueError("every attempt of a scenario needs its own attempt id")

    started = time.time()
    attempts: list[dict] = []
    entry_refusal: dict | None = None
    terminal = None
    verdict = None
    frames_all: list[dict] = []

    for attempt_index, attempt_id in enumerate(declared_attempts):
        attempt_config = {**config, "attempt_id": attempt_id}
        controller = HeadSearchController(attempt_config)
        reset = getattr(detector, "reset", None)
        reset_before = callable(reset)
        if reset_before:
            reset()
        frames: list[dict] = []
        stops: list[dict] = []
        corrections: list[float] = []
        detection_frames = 0
        target = float(attempt_config["search_start_rad"])
        inject_at = (
            interruption_frame
            if interruption and attempt_index == 0
            else None
        )
        injected = False
        stopped = False
        stop_status = None
        interruption_status = None
        lock_count_before = None
        attempt_terminal = None
        verdict = None
        refusal = None

        def command(target_rad: float, *, kind: str) -> None:
            """Command a target inside its own corridor, step the plant, and record the stop it made.

            Three kinds share this path and each has its own bound: `anchor` is the declared start of the
            search (the seal's lock-valid interval), `plan` is a stop of the controller's bounded sweep
            (HS-302's intersection of the required search domain and that interval) and `fine` is a
            centring correction or the stop that ends an attempt (the lock-valid interval again). A target
            outside its bound refuses the scenario rather than being clamped into it.
            """

            corridor = (coarse_low, coarse_high) if kind == "plan" else (fine_low, fine_high)
            _scenario_corridor_check(
                angle_rad=float(target_rad),
                corridor_rad=corridor,
                what=f"{kind} target of the scenario {declared['seed']}",
            )
            stop = dict(plant.settle_to(float(target_rad)))
            stop.update(anchor=declared["anchor"], index=len(stops), kind=kind, time_base=SIMULATION_TIME_BASE)
            stops.append(
                _re_raised(
                    classify_stop,
                    stop,
                    settle_consecutive_steps=settle_consecutive_steps,
                    max_settle_s=max_settle_s,
                )
            )
            _scenario_corridor_check(
                angle_rad=float(plant.yaw_rad),
                corridor_rad=(fine_low, fine_high),
                what=f"settled neck angle of the scenario {declared['seed']}",
            )

        try:
            command(target, kind="anchor")
            while len(frames) < max_frames:
                frame_wall = clock()
                image = plant.render_frame()
                received_wall = clock()
                stamp_ns = int(plant.frame_stamp_ns)
                geometry = plant.optical_geometry()
                decision_wall = clock()
                injecting = inject_at is not None and len(frames) == inject_at
                if injecting:
                    # the declared interruption: the frame is produced but reaches the controller one margin
                    # past its own freshness window, which is a dropped input rather than a fabricated frame
                    received_wall = frame_wall
                    decision_wall = frame_wall + float(config["max_age_s"]) + float(interruption_margin_s)
                try:
                    detections = _detections(detector, image, stamp_ns)
                except CalibrationDeadbandMeasurementRefused as error:
                    refusal = {
                        "code": CAL_SCENARIO_DETECTOR_FAILED,
                        "detail": (
                            f"the detector failed on a frame of the scenario {declared['seed']} "
                            f"({error.detail}), so this scenario is not a measurement"
                        ),
                    }
                    break
                if detections:
                    detection_frames += 1
                sim_s = float(plant.time_s)
                yaw, velocity = float(plant.yaw_rad), float(plant.velocity_rad_s)
                frame = {
                    "session_id": attempt_config["session_id"],
                    "attempt_id": attempt_id,
                    "sim_time_s": sim_s,
                    "received_wall_s": received_wall,
                    "frame_sim_s": sim_s,
                    "received_sim_s": sim_s,
                    "decision_sim_s": sim_s,
                    "frame_monotonic_s": frame_wall,
                    "received_monotonic_s": received_wall,
                    "decision_monotonic_s": decision_wall,
                    "frame_id": attempt_config["frame_id"],
                    "k": geometry["k"],
                    "distortion": geometry["distortion"],
                    "rotation_optical_to_base": geometry["rotation_optical_to_base"],
                    "principal_x_px": float(geometry["k"][2]),
                    "principal_y_px": float(geometry["k"][5]),
                    "detections": detections,
                    "neck_yaw_rad": yaw,
                    "neck_velocity_rad_s": velocity,
                }
                feedback = {
                    "session_id": attempt_config["session_id"],
                    "attempt_id": attempt_id,
                    "sim_time_s": sim_s,
                    "received_wall_s": received_wall,
                    "neck_yaw_rad": yaw,
                    "neck_velocity_rad_s": velocity,
                    "safe_observe": True,
                }
                previous_target = target
                corrections_before = controller.fine_count
                decision = controller.tick(frame, feedback, decision_wall)
                corrections_after = controller.fine_count
                record = _frame_summary(
                    index=len(frames),
                    anchor=declared["anchor"],
                    frame={
                        **frame,
                        "previous_frame_sim_s": None if not frames else frames[-1]["frame_sim_s"],
                    },
                    decision=decision,
                    detections=detections,
                )
                record["attempt_index"] = attempt_index
                record["attempt_id"] = attempt_id
                record["injected_interruption"] = bool(injecting)
                if "found" in decision:
                    record["neck_target_rad"] = None
                    record["move_kind"] = "hold"
                    frames.append(record)
                    attempt_terminal, verdict = dict(decision), decision["status"]
                    break
                if decision.get("stop"):
                    if not injecting:
                        refusal = {
                            "code": CAL_SCENARIO_NO_VERDICT,
                            "detail": (
                                f"the closed loop of the scenario {declared['seed']} stopped on the controller "
                                f"status {decision.get('status')!r} before it reached a verdict: the frame "
                                f"cadence or the clock this harness produced was not one the controller would "
                                f"decide on"
                            ),
                        }
                        frames.append(record)
                        break
                    injected = True
                    stopped = True
                    stop_status = str(decision.get("status"))
                    interruption_status = stop_status
                    lock_count_before = int(controller.lock_count)
                    record["neck_target_rad"] = float(decision["neck_target_rad"])
                    record["move_kind"] = "stop"
                    frames.append(record)
                    # the stop is commanded and settled, so the proof is of a move the harness really made
                    command(float(decision["neck_target_rad"]), kind="stop")
                    break
                target = float(decision["neck_target_rad"])
                status = decision.get("status")
                if corrections_after > corrections_before:
                    move_kind = "fine"
                    corrections.append(target - yaw)
                elif target != previous_target and status == "SEARCH_CUP":
                    move_kind = "plan"
                elif target == previous_target:
                    move_kind = "hold"
                else:
                    refusal = {
                        "code": CAL_SCENARIO_NO_VERDICT,
                        "detail": (
                            f"the controller of the scenario {declared['seed']} moved the neck under the status "
                            f"{status!r} without counting a fine correction, which this producer cannot classify"
                        ),
                    }
                    record["neck_target_rad"] = target
                    record["move_kind"] = "unclassified"
                    frames.append(record)
                    break
                record["neck_target_rad"] = target
                record["move_kind"] = move_kind
                frames.append(record)
                command(target, kind=move_kind)

        except CalibrationInputsRefused as error:
            # the operational refusals of *this scenario* are recorded, not raised: the run has to
            # reach all forty scenarios, and a refusal that stopped the run at scenario seven would
            # measure nothing about the other thirty-three
            refusal = {"code": error.code, "detail": error.detail}
        cadence = check_frame_cadence(
            frames, frame_period_s=frame_period_s, max_settle_s=max_settle_s
        )
        settled = settle_proof(
            stops,
            settle_velocity_rad_s=float(config["settle_velocity_rad_s"]),
            goal_tolerance_rad=goal_tolerance,
            settle_consecutive_steps=settle_consecutive_steps,
        )
        # the held stop proof is taken only where a stop really ended the attempt - after a verdict, or
        # after the declared interruption's fail-closed stop - and it is of the stop the neck is at
        held = (
            hold_stop_samples(plant, velocity_limit_rad_s=stop_limit)
            if (attempt_terminal is not None or stopped) and settled["proven"]
            else None
        )
        magnitudes = [abs(value) for value in corrections]
        attempt = {
            "index": attempt_index,
            "attempt_id": attempt_id,
            "search_start_rad": float(attempt_config["search_start_rad"]),
            "detector_reset_before_attempt": bool(reset_before),
            "interruption_injected": bool(injected),
            "interruption_kind": "stale_frame" if injected else None,
            "interruption_frame_index": inject_at if injected else None,
            "interruption_margin_s": float(interruption_margin_s) if injected else None,
            "interruption_decision_status": interruption_status,
            "stop": bool(stopped),
            "stop_status": stop_status,
            "lock_count_before_interruption": lock_count_before,
            "lock_count_after_interruption": (
                int(controller.lock_count) if injected else None
            ),
            "lock_count_cleared_by_interruption": (
                bool(int(controller.lock_count) == 0) if injected else None
            ),
            "track_after_interruption": controller.track if injected else None,
            "track_cleared_by_controller": (
                controller.track is None if injected else None
            ),
            "frame_count": len(frames),
            "detection_frames": detection_frames,
            "frames": frames,
            "stops": stops,
            "terminal_status": verdict,
            "found": None if attempt_terminal is None else bool(attempt_terminal.get("found")),
            "fine_corrections": len(magnitudes) if magnitudes else 0,
            "fine_corrections_rad": magnitudes,
            "cumulative_fine_correction_rad": sum(magnitudes),
            "controller_fine_count": int(controller.fine_count),
            "controller_fine_angle_rad": float(controller.fine_angle),
            "corrections_match_controller": bool(len(magnitudes) == int(controller.fine_count)),
            "cadence": cadence,
            "settle_proof": settled,
            "stop_proof": held,
            "coverage": _coverage_of(controller, required_domain_rad=required_domain),
            "refusal": refusal,
        }
        attempts.append(attempt)
        frames_all.extend(frames)
        if refusal is not None:
            entry_refusal = refusal
            break
        if injected:
            # attempt one of an interrupted scenario ends here, on the proven stop; attempt two reacquires
            terminal = None
            verdict = None
            continue
        terminal = attempt_terminal
        break

    final = attempts[-1]
    succeeded = verdict == "TARGET_LOCKED" and bool(terminal is not None and terminal.get("found"))
    if succeeded:
        try:
            verify_correction_consistency(
                episode_id=f"{QUALIFICATION_SPLIT}-{declared['seed']}",
                count=len(final["fine_corrections_rad"]),
                magnitudes=final["fine_corrections_rad"],
                controller_fine_count=final["controller_fine_count"],
                controller_fine_angle_rad=final["controller_fine_angle_rad"],
            )
        except CalibrationInputsRefused as error:
            entry_refusal = {"code": error.code, "detail": error.detail}

    if entry_refusal is None and not final["cadence"]["continuous"]:
        entry_refusal = {
            "code": CAL_SCENARIO_FRAME_CADENCE,
            "detail": (
                f"the frames of the scenario {declared['seed']} violate the declared "
                f"{FRAME_RATE_HZ} Hz contract: {final['cadence']['duplicate_count']} duplicate, "
                f"{final['cadence']['backward_count']} backward, {final['cadence']['too_fast_count']} too "
                f"fast and {final['cadence']['undeclared_gap_count']} undeclared-gap intervals"
            ),
        }
    if entry_refusal is None and verdict is None and terminal is None:
        entry_refusal = {
            "code": CAL_SCENARIO_NO_VERDICT,
            "detail": (
                f"the closed loop of the scenario {declared['seed']} spent its whole {max_frames}-frame "
                f"budget without a verdict, so it measured no outcome"
            ),
        }
    # a scenario that never reached a verdict has no stop to prove, so its own refusal is the headline
    if entry_refusal is None and verdict is None and terminal is None:
        entry_refusal = {
            "code": CAL_SCENARIO_NO_VERDICT,
            "detail": (
                f"the closed loop of the scenario {declared['seed']} spent its whole {max_frames}-frame "
                f"budget without a verdict, so it measured no outcome and nothing to prove a stop of"
            ),
        }
    if entry_refusal is None and not final["settle_proof"]["proven"]:
        entry_refusal = {
            "code": CAL_SCENARIO_STOP_UNPROVEN,
            "detail": (
                f"the scenario {declared['seed']} did not settle every stop it commanded: the unproven "
                f"stops are {final['settle_proof']['unproven_stops']} against the controller's declared "
                f"settle velocity {config['settle_velocity_rad_s']} rad/s over "
                f"{settle_consecutive_steps} consecutive control steps and the goal tolerance "
                f"{goal_tolerance} rad"
            ),
        }
    if entry_refusal is None and (final["stop_proof"] is None or final["stop_proof"]["proven"] is not True):
        proof = final["stop_proof"] or {}
        entry_refusal = {
            "code": CAL_SCENARIO_STOP_UNPROVEN,
            "detail": (
                f"the scenario {declared['seed']} did not prove the stop at {proof.get('held_at_rad')!r} "
                f"rad: its longest run of consecutive raw feedback samples within the promoted stop "
                f"velocity {stop_limit} rad/s was {proof.get('longest_consecutive_run')} of the "
                f"{STOP_PROOF_SAMPLES} the proof requires"
            ),
        }
    if entry_refusal is None and verdict in ("SEARCH_TIMEOUT",):
        entry_refusal = {
            "code": CAL_SCENARIO_NO_VERDICT,
            "detail": (
                f"the closed loop of the scenario {declared['seed']} ran out of the promoted search "
                f"timeout {config['search_timeout_s']} s of wall time before it reached a verdict"
            ),
        }
    if entry_refusal is None and verdict == "SEARCH_UNSAFE":
        entry_refusal = {
            "code": CAL_SCENARIO_OUT_OF_CORRIDOR,
            "detail": (
                f"the controller refused to observe the neck as safe ({verdict}) during the scenario "
                f"{declared['seed']}, so the loop left the interval the seal bounds"
            ),
        }

    magnitudes = final["fine_corrections_rad"]
    locked = float(plant.yaw_rad) if succeeded else None
    excursion = (
        None if locked is None else required_domain_excursion_rad(locked, required_domain)
    )
    entry = {
        "scenario_index": None,
        "seed": declared["seed"],
        "scene_group_id": declared["scene_group_id"],
        "condition_class": declared["condition_class"],
        "anchor": declared["anchor"],
        "expected_terminals": declared["expected_terminals"],
        "cup_count": declared["cup_count"],
        "scenario_name": _scenario_name(declared["cup_count"]),
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(timestep),
        "frame_period_s": float(frame_period_s),
        "frame_rate_hz": FRAME_RATE_HZ,
        "control_thresholds": {
            "search_start_rad": float(config["search_start_rad"]),
            "goal_tolerance_rad": goal_tolerance,
            "settle_velocity_rad_s": float(config["settle_velocity_rad_s"]),
            "stop_velocity_rad_s": stop_limit,
            "coarse_step_rad": float(config["coarse_step_rad"]),
            "search_timeout_s": float(config["search_timeout_s"]),
            "max_age_s": float(config["max_age_s"]),
            "max_skew_s": float(config["max_skew_s"]),
            "max_fine_corrections": int(config["max_fine_corrections"]),
            "max_fine_total_rad": float(config["max_fine_total_rad"]),
            "center_deadband_px": float(config["center_deadband_px"]),
            "vertical_bounds_px": [float(value) for value in config["vertical_bounds_px"]],
            "min_confidence": float(config["min_confidence"]),
            "min_area_px2": float(config["min_area_px2"]),
            "lock_frames_required": int(LOCK_FRAMES),
        },
        "coarse_corridor_rad": [coarse_low, coarse_high],
        "fine_corridor_rad": [fine_low, fine_high],
        "required_search_domain_rad": required_domain,
        "attempt_ids": [attempt["attempt_id"] for attempt in attempts],
        "attempts": attempts,
        "terminal_status": verdict,
        "found": bool(terminal is not None and terminal.get("found")),
        "locked": bool(succeeded),
        "locked_neck_rad": locked,
        "required_domain_excursion_rad": excursion,
        "locked_outside_required_domain": bool(excursion),
        "cup_found": bool(final["detection_frames"] > 0),
        "detection_frames": sum(attempt["detection_frames"] for attempt in attempts),
        "frame_count": sum(attempt["frame_count"] for attempt in attempts),
        "plan_moves": sum(
            1 for stop in final["stops"] if stop.get("kind") == "plan"
        ),
        "fine_corrections": len(magnitudes) if succeeded else None,
        "fine_corrections_rad": magnitudes if succeeded else [],
        "cumulative_fine_correction_rad": sum(magnitudes) if succeeded else None,
        "largest_single_correction_rad": max(magnitudes) if (succeeded and magnitudes) else None,
        "controller_fine_count": final["controller_fine_count"],
        "controller_fine_angle_rad": final["controller_fine_angle_rad"],
        "coverage": final["coverage"],
        "settle_proof": final["settle_proof"],
        "stop_proof": final["stop_proof"],
        "frame_cadence": final["cadence"],
        "refusal": entry_refusal,
        "outcome": None,
        "outcome_code": None,
        "outcome_detail": None,
        "evidence": _scenario_evidence(
            evidence,
            declared=declared,
            config=config,
            attempt_ids=[attempt["attempt_id"] for attempt in attempts],
            coarse=(coarse_low, coarse_high),
            fine=(fine_low, fine_high),
            frame_period_s=frame_period_s,
        ),
        "wall_time_s": time.time() - started,
        "sim_time_s": float(plant.time_s),
    }
    _re_raised(verify_simulation_time_base, {**entry, "stops": final["stops"], "frames": final["frames"]})
    return classify_scenario(entry)


# --- the per-scenario judgement --------------------------------------------------------------------


def classify_scenario(entry: Mapping) -> dict:
    """One scenario's outcome against the terminal statuses its condition class declares.

    The plan's own sentence is the rule, and nothing here softens it: a class that must lock and does not
    fails; a class that must not lock and does fails as a **wrong lock**; ``TARGET_NOT_FOUND`` passes only
    with complete coverage, because a sweep that stopped at a bound never showed there was no cup; and an
    interrupted class passes only when the old attempt really stopped fail-closed and the search really
    reacquired under a new attempt.
    """

    if not isinstance(entry, Mapping):
        raise ValueError("a scenario entry must be a mapping")
    result = dict(entry)
    condition_class = result.get("condition_class")
    terminals = expected_terminals(condition_class)
    attempts = [
        attempt
        for attempt in (result.get("attempts") or [])
        if isinstance(attempt, Mapping)
    ]
    coverage = result.get("coverage") if isinstance(result.get("coverage"), Mapping) else {}
    terminal = result.get("terminal_status")
    refusal = result.get("refusal") if isinstance(result.get("refusal"), Mapping) else None

    def decide(outcome: str, code: str | None, detail: str | None) -> dict:
        result["outcome"] = outcome
        result["outcome_code"] = code
        result["outcome_detail"] = detail
        return result

    if requires_interruption(condition_class):
        injected = [attempt for attempt in attempts if attempt.get("interruption_injected") is True]
        if not injected:
            return decide(
                REFUSED,
                CAL_SCENARIO_INTERRUPTION_UNPROVEN,
                f"the condition class {condition_class!r} is a declared interrupted class, but no attempt "
                f"of the scenario {result.get('seed')} injected the interruption, so the fail-closed stop "
                f"and the reacquisition the plan requires were never exercised",
            )
        for attempt in injected:
            if attempt.get("stop") is not True:
                return decide(
                    REFUSED,
                    CAL_SCENARIO_INTERRUPTION_UNPROVEN,
                    f"the injected interruption of the scenario {result.get('seed')} did not stop the "
                    f"controller (status {attempt.get('interruption_decision_status')!r}), so the old "
                    f"attempt did not end fail-closed",
                )
            if attempt.get("lock_count_cleared_by_interruption") is not True:
                return decide(
                    REFUSED,
                    CAL_SCENARIO_INTERRUPTION_UNPROVEN,
                    f"the injected interruption of the scenario {result.get('seed')} left the lock state "
                    f"at {attempt.get('lock_count_after_interruption')!r} instead of clearing it",
                )
        if len(attempts) < 2 or attempts[-1].get("interruption_injected") is True:
            return decide(
                REFUSED,
                CAL_SCENARIO_INTERRUPTION_UNPROVEN,
                f"the scenario {result.get('seed')} did not run a second attempt after its interruption, "
                f"so the search never reacquired",
            )
        if attempts[-1].get("detector_reset_before_attempt") is not True:
            return decide(
                REFUSED,
                CAL_SCENARIO_INTERRUPTION_UNPROVEN,
                f"the reacquiring attempt of the scenario {result.get('seed')} did not reset the "
                f"detector's tracker, so the tracker was not cleared before it searched again",
            )

    if refusal is not None:
        return decide(REFUSED, str(refusal.get("code")), str(refusal.get("detail")))

    if terminal is None:
        return decide(
            REFUSED,
            CAL_SCENARIO_NO_VERDICT,
            f"the scenario {result.get('seed')} recorded no terminal status at all, so it has no outcome "
            f"to judge",
        )
    terminal = str(terminal)
    if terminal in terminals:
        if terminal in NOT_FOUND_STATUSES and coverage.get("complete") is not True:
            return decide(
                REFUSED,
                CAL_SCENARIO_COVERAGE_INCOMPLETE,
                f"the scenario {result.get('seed')} reported {terminal} without complete coverage of the "
                f"required search domain {coverage.get('required_search_domain_rad')!r}, so the negative "
                f"is not a clean one",
            )
        return decide(PASSED, None, None)
    if terminal in NOT_FOUND_WITHIN_BOUND_STATUSES:
        return decide(
            REFUSED,
            CAL_SCENARIO_COVERAGE_INCOMPLETE,
            f"the scenario {result.get('seed')} stopped at a bound before the sweep covered the required "
            f"search domain, so it never showed whether a cup was there",
        )
    if terminal == "TARGET_LOCKED":
        return decide(
            FAILED,
            CAL_SCENARIO_UNEXPECTED_LOCK,
            f"the scenario {result.get('seed')} of the condition class {condition_class!r} locked, but "
            f"that class declares the terminal statuses {list(terminals)}: a lock here is a wrong lock",
        )
    if terminal in NOT_FOUND_STATUSES:
        return decide(
            FAILED,
            CAL_SCENARIO_CUP_NOT_FOUND,
            f"the scenario {result.get('seed')} of the condition class {condition_class!r} swept the whole "
            f"required domain without a single frame that carried the cup",
        )
    if terminal == "TARGET_AMBIGUOUS":
        return decide(
            FAILED,
            CAL_SCENARIO_TARGET_AMBIGUOUS,
            f"a frame of the scenario {result.get('seed')} carried more than one candidate cup, so the "
            f"controller never had a single cup to centre",
        )
    if terminal == "TARGET_NOT_CENTERED":
        binding = _budget_binding(
            count=int(result.get("controller_fine_count") or 0),
            total=float(result.get("controller_fine_angle_rad") or 0.0),
            largest_single=float(result.get("largest_single_correction_rad") or 0.0),
            budget={
                "max_fine_corrections": int(
                    (result.get("control_thresholds") or {}).get("max_fine_corrections", 1)
                ),
                "max_fine_total_rad": float(
                    (result.get("control_thresholds") or {}).get("max_fine_total_rad", 1.0)
                ),
            },
        )
        return decide(
            FAILED,
            CAL_SCENARIO_BUDGET_EXHAUSTED if binding else CAL_SCENARIO_NOT_CENTERED,
            f"the controller stopped centring with status TARGET_NOT_CENTERED after "
            f"{result.get('controller_fine_count')} corrections"
            + (" (the declared budget is what stopped it)" if binding else ""),
        )
    return decide(
        REFUSED,
        CAL_SCENARIO_NO_VERDICT,
        f"the scenario {result.get('seed')} ended on the controller status {terminal!r}, which is neither "
        f"a terminal status its condition class declares nor one this producer records as an outcome",
    )


def _scenario_evidence(
    evidence, *, declared, config, attempt_ids, coarse, fine, frame_period_s
) -> dict:
    """What reproduces one scenario: the caller's declared digests plus the fields the loop itself owns.

    The digests, the runtime identity and the command line belong to the producer and come in as
    `evidence`; the seed, the anchor, the declared class, the attempt ids, the corridors and the frame
    contract are this loop's own and are written over whatever was passed, so an entry can never claim a
    scenario it did not run.
    """

    document = dict(evidence) if isinstance(evidence, Mapping) else {}
    document.update(
        {
            "seed": declared["seed"],
            "scene_group_id": declared["scene_group_id"],
            "condition_class": declared["condition_class"],
            "anchor": declared["anchor"],
            "expected_terminals": list(declared["expected_terminals"]),
            "cup_count": declared["cup_count"],
            "scenario_name": _scenario_name(declared["cup_count"]),
            "attempt_ids": list(attempt_ids),
            "search_start_rad": float(config["search_start_rad"]),
            "coarse_corridor_rad": [float(coarse[0]), float(coarse[1])],
            "fine_corridor_rad": [float(fine[0]), float(fine[1])],
            "required_search_domain_rad": [
                float(bound) for bound in config["required_search_domain_rad"]
            ],
            "frame_period_s": float(frame_period_s),
            "frame_rate_hz": FRAME_RATE_HZ,
            "time_base": SIMULATION_TIME_BASE,
            "reproduction": (
                "re-run the declared command against the same sealed inputs and this scenario's seed: "
                "the scene is prepared by the dataset renderer from numpy.random.default_rng(seed) with "
                "the condition class's cup count, the search starts at the declared anchor and the loop "
                "runs the promoted controller at the declared frame period"
            ),
        }
    )
    return document


def _scenario_corridor_check(*, angle_rad: float, corridor_rad, what: str) -> None:
    """The deadband module's own corridor check, re-raised under this producer's code.

    The rule is the same one - nothing is ever clamped - but a caller that records a qualification
    scenario reads this producer's code vocabulary, so the refusal is this measurement's own.
    """

    try:
        _corridor_check(angle_rad=angle_rad, corridor_rad=corridor_rad, what=what)
    except CalibrationDeadbandMeasurementRefused as error:
        raise _refuse(CAL_SCENARIO_OUT_OF_CORRIDOR, error.detail) from error


def hold_stop_samples(plant, *, velocity_limit_rad_s, required_samples=STOP_PROOF_SAMPLES, max_samples=STOP_PROOF_WINDOW):  # noqa: E501
    """Hold the neck at its stop and take raw feedback samples until the stop proof is complete.

    Each sample is one held settle of the *same* target: the plant steps the sealed neck with no new
    command and reports the velocity it measured at the end of that hold, which is the harness's raw
    feedback readback. Sampling stops at the third consecutive qualifying sample, and a hold that does not
    qualify resets the run, exactly as the declared consecutive rule says.
    """

    if type(max_samples) is not int or isinstance(max_samples, bool) or max_samples < 1:
        raise ValueError("the stop-proof window must be a positive whole number of samples")
    if max_samples < required_samples:
        raise ValueError("the stop-proof window must admit the declared consecutive samples")
    held = float(plant.yaw_rad)
    samples: list[dict] = []
    for _index in range(int(max_samples)):
        stop = dict(plant.settle_to(held))
        samples.append(
            {
                "velocity_rad_s": stop.get("final_velocity_rad_s"),
                "position_error_rad": stop.get("final_position_error_rad"),
                "settled": bool(stop.get("settled")),
                "reached": bool(stop.get("reached")),
                "settle_s": stop.get("settle_s"),
            }
        )
        proof = stop_proof(samples, velocity_limit_rad_s=velocity_limit_rad_s, required_samples=required_samples)
        if proof["proven"]:
            break
    proof = stop_proof(samples, velocity_limit_rad_s=velocity_limit_rad_s, required_samples=required_samples)
    proof["held_at_rad"] = held
    return proof


def _scenario_name(cup_count: int) -> str:
    """The dataset scenario name for a declared cup count, spelled as the renderer's own enum spells it."""

    return scenario_name_for_cup_count(int(cup_count))


#: exactly the keys one journal entry carries, and nothing else
JOURNAL_KEYS = (
    "scenario_index",
    "seed",
    "scene_group_id",
    "condition_class",
    "anchor",
    "cup_count",
    "scenario_name",
    "expected_terminals",
    "outcome",
    "outcome_code",
    "outcome_detail",
    "terminal_status",
    "found",
    "locked",
    "locked_neck_rad",
    "cup_found",
    "detection_frames",
    "frame_count",
    "plan_moves",
    "fine_corrections",
    "fine_corrections_rad",
    "cumulative_fine_correction_rad",
    "largest_single_correction_rad",
    "coverage",
    "stop_proof",
    "frame_cadence",
    "attempt_ids",
    "attempt_summaries",
    "evidence",
)


def scenario_journal_entry(entry: Mapping) -> dict:
    """One scenario's journal row: exactly :data:`JOURNAL_KEYS`, and nothing else.

    The full entry (with its frames and stops) stays in the per-scenario evidence document; the journal is
    the row a reviewer reads one scenario at a time, so it carries the outcome, the numbers and the
    evidence that reproduces it, and never a number the scenario did not measure.
    """

    if not isinstance(entry, Mapping):
        raise ValueError("a scenario entry must be a mapping")
    missing = [key for key in JOURNAL_KEYS if key != "attempt_summaries" and key not in entry]
    if missing:
        raise ValueError(f"the scenario entry carries no {missing}, so it is not a journal entry")
    summaries = []
    for attempt in entry.get("attempts") or ():
        if not isinstance(attempt, Mapping):
            continue
        summaries.append(
            {
                key: attempt.get(key)
                for key in (
                    "index",
                    "attempt_id",
                    "frame_count",
                    "detection_frames",
                    "terminal_status",
                    "found",
                    "stop",
                    "stop_status",
                    "interruption_injected",
                    "interruption_decision_status",
                    "lock_count_before_interruption",
                    "lock_count_after_interruption",
                    "lock_count_cleared_by_interruption",
                    "track_after_interruption",
                    "track_cleared_by_controller",
                    "detector_reset_before_attempt",
                    "fine_corrections",
                    "cumulative_fine_correction_rad",
                    "controller_fine_count",
                    "controller_fine_angle_rad",
                    "corrections_match_controller",
                    "refusal",
                )
            }
        )
    row = {key: entry[key] for key in JOURNAL_KEYS if key != "attempt_summaries"}
    row["attempt_summaries"] = summaries
    return {key: row[key] for key in JOURNAL_KEYS}


# --- the aggregate ---------------------------------------------------------------------------------


def aggregate_scenarios(entries) -> dict:
    """Count every outcome per condition class and per anchor, and never claim the verdict.

    The passed, failed and refused counts are the honest aggregate; the qualification verdict belongs to
    the qualifier's ``aggregate`` phase (``head_search_qualification.RUN_PHASES``), which this round does
    not implement, so this document carries ``qualification_verdict: null`` and names its owner.
    """

    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        raise ValueError("the aggregate needs the sequence of journaled scenarios")
    by_condition_class: dict[str, dict] = {}
    by_anchor: dict[str, dict] = {}
    wrong_locks: list[dict] = []
    corrections: list[int] = []
    cumulative: list[float] = []
    cadence_ok = True
    stops_ok = True
    terminals: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise ValueError("every journaled scenario must be a mapping")
        condition_class = str(entry.get("condition_class"))
        anchor = str(entry.get("anchor"))
        outcome = str(entry.get("outcome"))
        terminal = entry.get("terminal_status")
        if terminal is not None:
            terminals[str(terminal)] = terminals.get(str(terminal), 0) + 1
        for table, key in ((by_condition_class, condition_class), (by_anchor, anchor)):
            bucket = table.setdefault(
                key,
                {"total": 0, "passed": 0, "failed": 0, "refused": 0, "terminal_statuses": {}},
            )
            bucket["total"] += 1
            bucket[outcome.lower()] = bucket.get(outcome.lower(), 0) + 1
            if terminal is not None:
                bucket["terminal_statuses"][str(terminal)] = (
                    bucket["terminal_statuses"].get(str(terminal), 0) + 1
                )
        if entry.get("outcome_code") == CAL_SCENARIO_UNEXPECTED_LOCK:
            wrong_locks.append(
                {
                    "seed": entry.get("seed"),
                    "condition_class": condition_class,
                    "anchor": anchor,
                }
            )
        value = entry.get("fine_corrections")
        if type(value) is int and not isinstance(value, bool):
            corrections.append(value)
        total = entry.get("cumulative_fine_correction_rad")
        if _finite(total):
            cumulative.append(float(total))
        cadence = entry.get("frame_cadence")
        if not isinstance(cadence, Mapping) or cadence.get("continuous") is not True:
            cadence_ok = False
        proof = entry.get("stop_proof")
        if not isinstance(proof, Mapping) or proof.get("proven") is not True:
            stops_ok = False
    passed = sum(1 for entry in entries if entry.get("outcome") == PASSED)
    failed = sum(1 for entry in entries if entry.get("outcome") == FAILED)
    refused = sum(1 for entry in entries if entry.get("outcome") == REFUSED)
    return {
        "scenario_count": len(entries),
        "passed_count": passed,
        "failed_count": failed,
        "refused_count": refused,
        "by_condition_class": by_condition_class,
        "by_anchor": by_anchor,
        "terminal_statuses": terminals,
        "zero_wrong_locks": not wrong_locks,
        "wrong_locks": wrong_locks,
        "fine_corrections": {
            "min": min(corrections) if corrections else None,
            "max": max(corrections) if corrections else None,
            "observed_on": len(corrections),
        },
        "cumulative_fine_correction_rad": {
            "min": min(cumulative) if cumulative else None,
            "max": max(cumulative) if cumulative else None,
            "observed_on": len(cumulative),
        },
        "cadence_all_continuous": cadence_ok,
        "stop_proofs_all_proven": stops_ok,
        "qualification_verdict": None,
        "qualification_verdict_owner": (
            "so101_demo.act.head_search_qualification (the qualifier's `aggregate` phase), which consumes "
            "the smoke, the forty scenarios and the three anchor restarts together; this document is the "
            "`scenarios` phase's own evidence and publishes no verdict"
        ),
        "fit_warning": QUALIFICATION_FIT_WARNING,
    }


# --- the producer ----------------------------------------------------------------------------------


def _resolve_config_scene(dataset_config_path) -> Path:
    """The MuJoCo scene a dataset profile renders, resolved from the profile's own declaration."""

    path = Path(dataset_config_path)
    contents = path.read_text(encoding="utf-8")
    try:
        document = json.loads(contents)
    except json.JSONDecodeError:
        import yaml

        document = yaml.safe_load(contents)
    if not isinstance(document, Mapping) or "mjcf_path" not in document:
        raise _refuse(
            CAL_SCENARIO_SCENE_CONTRADICTORY,
            f"the dataset profile {path} declares no mjcf_path, so the scene these scenarios would be "
            f"rendered from is not declared",
        )
    declared = Path(str(document["mjcf_path"]))
    return declared if declared.is_absolute() else (path.parent / declared).resolve()


def _ownership_gate(
    *, output_dir, evidence_root, final_run, expected_runtime, expected_package_prefix,
    ownership_check, runtime_identity_reader, weights_sha256, production_path,
):
    """Claim the run root through the exclusive-ownership gate, and refuse the run when it refuses.

    The gate is Task 14 Step 1's own producer (`so101_demo.act.head_search_ownership`): it reads the fresh
    process table, the ROS graph, the GPU compute processes, tmux ownership and the evidence root, binds
    the frozen runtime identity, and writes its receipt into the brand-new root. Nothing runs before it
    passes, and a refusal stops the whole run rather than one scenario.
    """

    runtime = None
    reader = runtime_identity_reader
    if reader is None and final_run is not None:
        from so101_demo.act import head_search_ownership as ownership

        reader = lambda root: ownership.read_runtime_identity(  # noqa: E731 - one-argument adapter
            root, production_config=production_path if production_path is not None else None
        )
    if reader is not None:
        if final_run is None:
            raise _refuse(
                CAL_SCENARIO_RUNTIME_UNVERIFIED,
                "a runtime identity reader was declared without a frozen runtime root to read it from",
            )
        try:
            runtime = dict(reader(Path(final_run)))
        except ValueError as error:
            raise _refuse(CAL_SCENARIO_RUNTIME_UNVERIFIED, str(error)) from error
        declared = runtime.get("weight_sha256_declared")
        if declared != weights_sha256:
            raise _refuse(
                CAL_SCENARIO_RUNTIME_UNVERIFIED,
                f"the runtime of record seals the detector weights {declared!r}, but these scenarios would "
                f"close the loop with {weights_sha256!r}: the run is not the runtime of record",
            )
        if runtime.get("allow_cpu_fallback") is not False:
            raise _refuse(
                CAL_SCENARIO_RUNTIME_UNVERIFIED,
                f"the runtime of record declares allow_cpu_fallback="
                f"{runtime.get('allow_cpu_fallback')!r}, and this producer never falls back to the CPU",
            )

    if ownership_check is None:
        from so101_demo.act import head_search_ownership as ownership

        ownership_check = ownership.check_exclusive_ownership
    document = dict(
        ownership_check(
            run_root=Path(output_dir),
            evidence_root=Path(evidence_root),
            runtime=runtime,
            expected_runtime=expected_runtime or None,
            expected_package_prefix=expected_package_prefix,
        )
    )
    if document.get("status") != "EXCLUSIVE_OWNERSHIP_OK":
        codes = ",".join(str(item.get("code")) for item in document.get("refusals") or ())
        raise _refuse(
            CAL_SCENARIO_OWNERSHIP_REFUSED,
            f"the exclusive-ownership gate refused the run with {codes or 'no code'}: a qualifier that "
            f"does not exclusively own the machine may not measure a scenario",
        )
    receipt_path = Path(output_dir) / "exclusive-ownership.json"
    observations = document.get("observations")
    summary = {
        "status": document.get("status"),
        "checked_at_utc": document.get("checked_at_utc"),
        "refusals": list(document.get("refusals") or ()),
        "owner": dict(document.get("owner") or {}),
        "expected_runtime": document.get("expected_runtime"),
        "expected_package_prefix": document.get("expected_package_prefix"),
        "resources": {
            str(name): {
                "rc": value.get("rc"),
                "row_count": len(value.get("rows") or ()),
                "value": value.get("value"),
                "note": value.get("note"),
            }
            for name, value in sorted((observations or {}).items())
        },
        "receipt_path": str(receipt_path),
        "receipt_sha256": _digest(receipt_path) if receipt_path.is_file() else None,
    }
    return runtime, summary


def write_head_search_scenarios(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    frozen_candidate_path,
    weights_path,
    dataset_config_path,
    scenario_partitions_path,
    output_dir,
    evidence_root,
    final_run=None,
    seeds=None,
    device: str = "cuda",
    generator_commit: str = "unrecorded",
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps: int = SETTLE_CONSECUTIVE_STEPS,
    max_frames: int = DEFAULT_MAX_FRAMES,
    interruption_frame: int = DEFAULT_INTERRUPTION_FRAME,
    interruption_margin_s: float = INTERRUPTION_STALE_MARGIN_S,
    expected_runtime: Mapping | None = None,
    expected_package_prefix: str | None = None,
    ownership_check=None,
    runtime_identity_reader=None,
    command=None,
    plant=None,
    detector_factory=None,
    scene_preparer=None,
    clock=time.monotonic,
) -> dict:
    """Run the declared qualification scenarios one at a time and write the phase's own documents.

    Every declared input is read and cross-checked before a single scene is prepared: the scene has to be
    the one the sealed geometry pins, the dataset profile has to render that same scene, the control period
    has to be a whole number of the scene's own timesteps, the detector has to be the weight the sealed
    configuration declares, the frozen candidate has to declare its head operating point, and the device
    has to be a CUDA device that is really there. Then the exclusive-ownership gate claims the run root and
    binds the runtime of record, and only then does the first scenario start.

    The scenarios run **serially**, one MuJoCo plant at a time, each in its own prepared scene and from its
    own declared anchor, and every one of them is journalled - including the ones that fail or refuse. The
    documents this producer creates are `scenarios.json`, `scenario-journal.jsonl`,
    `scenarios/<seed>.json` and `measurement-receipt.json`, plus the gate's own
    `exclusive-ownership.json`.
    """

    started = time.time()
    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    frozen_path = Path(frozen_candidate_path)
    dataset_path = Path(dataset_config_path)
    partitions_path = Path(scenario_partitions_path)
    for path in (
        scene, seal_path, production_path, controller_path, frozen_path, dataset_path, partitions_path
    ):
        if not path.is_file():
            raise FileNotFoundError(f"the qualification scenarios need {path}")
    weights = Path(weights_path)
    if not weights.is_file():
        raise FileNotFoundError(f"the qualification scenarios need {weights}")

    partitions = json.loads(partitions_path.read_text(encoding="utf-8"))
    items = qualification_scenarios(partitions, seeds=seeds)

    declaration = read_mujoco_timestep(scene)
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    scene_sha256 = declaration["scene_sha256"]
    sealed_scene = (seal.get("source_digests") or {}).get("scene_sha256")
    if sealed_scene != scene_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry pins the scene {sealed_scene}, but the scene these scenarios would step "
            f"the neck in digests to {scene_sha256}",
        )
    declared_scene = _resolve_config_scene(dataset_path)
    if declared_scene.resolve() != scene.resolve():
        raise _refuse(
            CAL_SCENARIO_SCENE_CONTRADICTORY,
            f"the dataset profile {dataset_path} renders {declared_scene}, but these scenarios would step "
            f"the neck in {scene}: the scenes a scenario prepares and the scene this producer renders have "
            f"to be the same one",
        )
    control_period = _re_raised(read_control_period, controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s steps, so the scenarios could not command the neck at the production period",
        )
    weights_sha256 = _re_raised(_declared_weights, production, {"weights_path": weights_path})
    if str(device).startswith("cuda") and not _cuda_available():
        raise _refuse(
            CAL_TIMING_DEVICE_UNAVAILABLE,
            f"the detector was declared for {device!r} but no CUDA device is available, and this producer "
            f"never falls back to the CPU",
        )
    operating_point = detector_operating_point(frozen)
    frozen_weights = frozen.get("weight_sha256")
    if isinstance(frozen_weights, str) and frozen_weights != weights_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the frozen candidate seals the weights {frozen_weights}, but the production search "
            f"configuration seals {weights_sha256}: the scenarios would not close the loop with the "
            f"selected model",
        )
    values = production.get("values") if isinstance(production.get("values"), Mapping) else {}
    stop_velocity = values.get("stop_velocity_rad_s")
    if not _finite(stop_velocity) or float(stop_velocity) <= 0.0:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the production search configuration declares no positive stop_velocity_rad_s, so no scenario's "
            "stop can be proven",
        )
    coarse = _re_raised(motion_corridor_rad, geometry_seal=seal)
    fine = fine_corridor_rad(geometry_seal=seal)

    output = Path(output_dir)
    if output.exists():
        raise _refuse(
            CAL_SCENARIO_RUN_ROOT_EXISTS,
            f"{output} exists; a qualification run is never resumed, continued or overwritten",
        )

    runtime, ownership = _ownership_gate(
        output_dir=output,
        evidence_root=evidence_root,
        final_run=final_run,
        expected_runtime=expected_runtime,
        expected_package_prefix=expected_package_prefix,
        ownership_check=ownership_check,
        runtime_identity_reader=runtime_identity_reader,
        weights_sha256=weights_sha256,
        production_path=production_path,
    )

    prepared = prepare_episode_scene if scene_preparer is None else scene_preparer
    detector = (
        None
        if detector_factory is not None
        else build_production_head_detector(
            weights_path=weights,
            operating_point=operating_point,
            production=production,
            frame_id="head_camera_frame",
            device=device,
            attempt_id=f"{SCENARIO_SESSION_ID}-detector",
            session_id=SCENARIO_SESSION_ID,
        )
    )
    runtime_identity_document = (
        dict(runtime)
        if runtime is not None
        else measurement_runtime_identity(
            device=device, detector_loaded=True, weights_sha256=weights_sha256
        )
    )
    evidence_dir = output / EVIDENCE_DIR
    evidence_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict] = []
    scene_state_digests: dict[str, str] = {}
    for index, item in enumerate(items):
        seed = int(item["seed"])
        condition_class = str(item["condition_class"])
        anchor = str(item["anchor"])
        request_base = f"{SCENARIO_SESSION_ID}-{seed}"
        requests = _anchor_requests(
            seal=seal,
            production=production,
            anchors=[anchor],
            attempt_id=request_base,
            session_id=SCENARIO_SESSION_ID,
        )
        if len(requests) != 1:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"the scenario {seed} declares the anchor {anchor!r}, which the sealed geometry does not "
                f"resolve to exactly one search start",
            )
        request = requests[0]
        cup_count = declared_cup_count(condition_class)
        state = prepared(
            **scene_preparation_request(
                dataset_config_path=dataset_path,
                generator_commit=generator_commit,
                seed=seed,
                cup_count=cup_count,
                scenario=condition_class,
                scene_path=scene,
                split=QUALIFICATION_SPLIT,
            )
        )
        scene_state_digests[str(seed)] = (
            canonical_sha256(dict(state)) if isinstance(state, Mapping) and state else ""
        )
        scenario_evidence = {
            "scene_sha256": scene_sha256,
            "geometry_seal_sha256": _digest(seal_path),
            "production_search_config_sha256": _digest(production_path),
            "frozen_candidate_sha256": _digest(frozen_path),
            "weights_sha256": weights_sha256,
            "dataset_config_sha256": _digest(dataset_path),
            "scenario_partitions_sha256": _digest(partitions_path),
            "controller_config_sha256": _digest(controller_path),
            "scene_state_sha256": scene_state_digests[str(seed)],
            "runtime_identity": runtime_identity_document,
            "detector_operating_point": dict(operating_point),
            "device": str(device),
            "generator_commit": str(generator_commit),
            "command": command,
            "scene_group_id": item["scene_group_id"],
            "prepared_by": (
                "MuJoCoDatasetRenderer._prepare(numpy.random.default_rng(seed), "
                "DatasetScenario.for_cup_count(cup_count)) of the head dataset profile, exactly as the "
                "recorder prepared the split it rendered"
            ),
        }
        episode_request = dict(request)
        episode_request.update(
            {
                "scene_state": state,
                "seed": seed,
                "scenario": condition_class,
                "split": QUALIFICATION_SPLIT,
            }
        )
        episode_plant = (
            plant(episode_request)
            if plant is not None
            else MujocoEpisodePlant(
                {
                    **_plant_request(
                        request=episode_request,
                        scene=scene,
                        seal=seal,
                        camera=seal.get("camera") if isinstance(seal.get("camera"), Mapping) else {},
                        control_period_s=control_period,
                        max_settle_s=max_settle_s,
                        settle_consecutive_steps=settle_consecutive_steps,
                    ),
                    "scene_state": state,
                    "seed": seed,
                    "scenario": condition_class,
                    "split": QUALIFICATION_SPLIT,
                }
            )
        )
        try:
            entry = run_scenario(
                controller_config=request["controller_config"],
                plant=episode_plant,
                detector=(
                    detector
                    if detector_factory is None
                    else detector_factory(episode_plant, episode_request)
                ),
                coarse_corridor_rad=coarse,
                fine_corridor_rad=fine,
                scenario={**item, "scenario_index": index},
                stop_velocity_rad_s=float(stop_velocity),
                interruption=requires_interruption(condition_class),
                interruption_frame=interruption_frame,
                interruption_margin_s=interruption_margin_s,
                max_frames=max_frames,
                settle_consecutive_steps=settle_consecutive_steps,
                max_settle_s=max_settle_s,
                evidence=scenario_evidence,
                clock=clock,
            )
        finally:
            close = getattr(episode_plant, "close", None)
            if callable(close):
                close()
        entry["scenario_index"] = index
        entries.append(entry)
        row = scenario_journal_entry(entry)
        (evidence_dir / f"{seed}.json").write_text(
            json.dumps(entry, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        with (output / JOURNAL_ARTIFACT).open("a", encoding="utf-8") as journal:
            journal.write(json.dumps(row, sort_keys=True) + "\n")

    aggregate = aggregate_scenarios(entries)
    anchor_split: dict[str, int] = {}
    for item in items:
        anchor_split[str(item["anchor"])] = anchor_split.get(str(item["anchor"]), 0) + 1
    records = [scenario_journal_entry(entry) for entry in entries]
    document_path = output / ARTIFACT
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "path": str(document_path),
        "command": command,
        "split": QUALIFICATION_SPLIT,
        "seeds": [int(item["seed"]) for item in items],
        "scenario_count": aggregate["scenario_count"],
        "passed_count": aggregate["passed_count"],
        "failed_count": aggregate["failed_count"],
        "refused_count": aggregate["refused_count"],
        "by_condition_class": aggregate["by_condition_class"],
        "by_anchor": aggregate["by_anchor"],
        "anchor_split": anchor_split,
        "terminal_statuses": aggregate["terminal_statuses"],
        "zero_wrong_locks": aggregate["zero_wrong_locks"],
        "wrong_locks": aggregate["wrong_locks"],
        "fine_corrections": aggregate["fine_corrections"],
        "cumulative_fine_correction_rad": aggregate["cumulative_fine_correction_rad"],
        "cadence_all_continuous": aggregate["cadence_all_continuous"],
        "stop_proofs_all_proven": aggregate["stop_proofs_all_proven"],
        "qualification_verdict": aggregate["qualification_verdict"],
        "qualification_verdict_owner": aggregate["qualification_verdict_owner"],
        "fit_warning": aggregate["fit_warning"],
        "expected_terminals": {name: list(values) for name, values in EXPECTED_TERMINALS.items()},
        "interruption_classes": list(INTERRUPTION_CLASSES),
        "records": records,
        "outcome_codes": list(OUTCOME_CODES),
        "unmeasured_codes": list(UNMEASURED_CODES),
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": timestep,
        "control_period_s": control_period,
        "steps_per_period": int(round(steps_per_period)),
        "frame_period_s": FRAME_PERIOD_S,
        "frame_rate_hz": FRAME_RATE_HZ,
        "coarse_corridor_rad": [float(bound) for bound in coarse],
        "fine_corridor_rad": [float(bound) for bound in fine],
        "scene_path": str(scene),
        "scene_sha256": scene_sha256,
        "geometry_seal": {"path": str(seal_path), "sha256": _digest(seal_path)},
        "production_search_config": {
            "path": str(production_path),
            "sha256": _digest(production_path),
        },
        "values_sha256": canonical_sha256(dict(values)),
        "values_count": len(values),
        "frozen_candidate": {"path": str(frozen_path), "sha256": _digest(frozen_path)},
        "weights": {"path": str(weights), "sha256": weights_sha256},
        "dataset_config": {"path": str(dataset_path), "sha256": _digest(dataset_path)},
        "controller_config": {"path": str(controller_path), "sha256": _digest(controller_path)},
        "scenario_partitions": {
            "path": str(partitions_path),
            "sha256": _digest(partitions_path),
        },
        "scene_state_sha256_by_seed": scene_state_digests,
        "detector_operating_point": dict(operating_point),
        "device": str(device),
        "cuda_used": str(device).startswith("cuda"),
        "detector_loaded": detector is not None or detector_factory is not None,
        "runtime_identity": runtime_identity_document,
        "ownership_receipt": ownership,
        "evidence_dir": str(evidence_dir),
        "journal_path": str(output / JOURNAL_ARTIFACT),
        "max_frames": int(max_frames),
        "interruption_frame": int(interruption_frame),
        "interruption_stale_margin_s": float(interruption_margin_s),
        "settle_consecutive_steps": int(settle_consecutive_steps),
        "max_settle_s": float(max_settle_s),
        "scenario_preparation": {
            "dataset_config_path": str(dataset_path),
            "generator_commit": str(generator_commit),
            "condition_class_by_seed": {
                str(item["seed"]): str(item["condition_class"]) for item in items
            },
            "cup_count_by_seed": {
                str(item["seed"]): declared_cup_count(str(item["condition_class"]))
                for item in items
            },
            "anchor_by_seed": {str(item["seed"]): str(item["anchor"]) for item in items},
            "serial": (
                "one scenario at a time: each one prepares its own scene, closes its own plant before the "
                "next seed starts, and no two scenarios share a MuJoCo instance"
            ),
        },
        "measured_here": (
            "one closed-loop MuJoCo search per declared qualification seed, on the head camera, with the "
            "selected model behind the production head detector at its declared head operating point"
        ),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "motion_commanded": False,
        "elapsed_s": time.time() - started,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    document_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    receipt = {
        **aggregate,
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "phase": PHASE,
        "status": (
            "SUCCEEDED"
            if aggregate["refused_count"] == 0 and aggregate["failed_count"] == 0
            else "MEASURED_WITH_FAILED_OR_REFUSED_SCENARIOS"
        ),
        "command": command,
        "output_dir": str(output),
        "document_path": str(document_path),
        "document_sha256": document["sha256"],
        "journal_path": str(output / JOURNAL_ARTIFACT),
        "evidence_dir": str(evidence_dir),
        "seeds": [int(item["seed"]) for item in items],
        "anchor_split": anchor_split,
        "records": records,
        "scene_sha256": scene_sha256,
        "values_sha256": canonical_sha256(dict(values)),
        "weights_sha256": weights_sha256,
        "production_search_config_sha256": _digest(production_path),
        "geometry_seal_sha256": _digest(seal_path),
        "frozen_candidate_sha256": _digest(frozen_path),
        "dataset_config_sha256": _digest(dataset_path),
        "controller_config_sha256": _digest(controller_path),
        "scenario_partitions_sha256": _digest(partitions_path),
        "device": str(device),
        "cuda_used": str(device).startswith("cuda"),
        "allow_cpu_fallback": False,
        "detector_loaded": document["detector_loaded"],
        "detector_operating_point": dict(operating_point),
        "runtime_identity": runtime_identity_document,
        "ownership_receipt": ownership,
        "control_period_s": control_period,
        "simulation_timestep_s": timestep,
        "frame_period_s": FRAME_PERIOD_S,
        "frame_rate_hz": FRAME_RATE_HZ,
        "coarse_corridor_rad": [float(bound) for bound in coarse],
        "fine_corridor_rad": [float(bound) for bound in fine],
        "max_frames": int(max_frames),
        "elapsed_s": document["elapsed_s"],
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
        "entries": entries,
    }


def _cuda_available() -> bool:
    """Whether the declared CUDA device is really there; the producer never falls back to the CPU."""

    import torch

    return bool(torch.cuda.is_available())
