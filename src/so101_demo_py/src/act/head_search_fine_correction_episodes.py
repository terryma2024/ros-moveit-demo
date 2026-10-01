"""The held-out fine-correction episodes: phase 6's ``fine_correction_episodes`` measurement document.

Phase 6 chooses ``max_fine_corrections`` as *the largest count a successful held-out validation episode
needed plus one recovery allowance* and ``max_fine_total_rad`` as *the largest cumulative fine correction
of those episodes plus the largest single correction observed in them*
(``head_search_search_params.compute_max_fine_corrections`` / ``compute_max_fine_total_rad``, design
section 7.1, ledger HS-296). Both numbers are properties of the **closed loop** - a scene, a bounded
sweep, a rendered frame, a detection and a correction fed back into the controller - so no open-loop
episode can carry them: the retained `episodes8` recordings are three fixed neck angles per scene, with no
correction and no success verdict at all.

What this module measures, and how:

* one **episode per held-out seed**. The scene is prepared exactly as the recorder prepared it for the
  held-out dataset (``record_episodes7.py``): the same dataset profile, the same
  ``MuJoCoDatasetRenderer._prepare`` with ``numpy.random.default_rng(seed)`` and the same
  condition-class-to-cup-count convention, so the episode looks at the scene the held-out split was
  rendered from rather than at a scene this producer invented.
* :func:`run_fine_correction_episode` is that closed loop, and it is pure: the plant and the detector are
  injected. The production :class:`so101_demo.act.search.HeadSearchController` drives it - its own bounded
  plan, its own freshness and skew gates, its own three-frame lock rule and its own fine-correction law
  (``target = neck_yaw + correction``) - and every step is checked against a declared motion corridor
  rather than clamped.
* a **fine correction** is a move the controller made on a *visible cup*: the frame's decision status is
  ``CENTER_CUP`` and the commanded target differs from the one before it. A move to the next stop of the
  bounded plan carries ``SEARCH_CUP`` and is never counted as a correction; a decision that holds the
  neck carries the same target and is counted as neither.
* the count and the magnitudes are **not this module's opinion of what the controller did**: after the
  terminal verdict they are compared against the controller's own ``fine_count`` and ``fine_angle``
  (:func:`verify_correction_consistency`), and a disagreement refuses the episode rather than recording a
  number nobody can check.

The two corridors, declared and never clamped (this is the split HS-302's single corridor needs, and the
one thing about this document a reviewer should check first):

* the **coarse corridor** is HS-302's own rule - the intersection of the seal's
  ``required_search_domain_rad`` and its ``lock_valid_neck_rad`` - and it bounds the anchor the episode
  starts from and every stop of the bounded sweep.
* the **fine corridor** is the seal's ``lock_valid_neck_rad``: the interval the seal declares a lock
  valid in, the interval the controller's own plan clamps its stops to, and the interval
  ``compute_max_fine_total_rad`` reduces its headroom from. The production controller does **not** clamp a
  fine correction to ``required_search_domain_rad`` - that interval is the *coverage* the coarse sweep
  owes, and the seal's own ``in_frame_matrix`` says so - so bounding the fine path by the required domain
  would refuse every held-out episode of this dataset (their cup sits at the ``default`` anchor's cup
  point, which is outside the sealed pick workspace). Applying HS-302's intersection to the fine path
  would therefore not make the measurement stricter, only impossible; instead every episode records how
  far outside the required domain it locked (:func:`required_domain_excursion_rad`), and the document
  counts the excursions.

What this module refuses instead of fabricating (the codes are :data:`REFUSAL_CODES`, and the episodes
that merely did not succeed are recorded, not refused):

* a seed of a split the caller did not declare as the measured one - a calibration seed in particular -
  refuses with :data:`CAL_FINE_EPISODE_SPLIT_LEAK`, because the fine-correction path is never calibrated
  on the frames it is validated on (plan section 4 item 7; the same isolation phase 6 re-checks with
  phase 3's ``CAL_SPLIT_LEAK``);
* a commanded target or a settled neck angle outside its declared corridor
  (:data:`CAL_FINE_EPISODE_OUT_OF_CORRIDOR`), never a clamped command;
* an episode the harness's own declared measurement budget censored
  (:data:`CAL_FINE_EPISODE_BUDGET_EXHAUSTED`): an episode that hit the instrument's limit is not evidence
  that the limit was enough, so the document is refused rather than its maximum understated;
* an episode that could not run to a verdict at all - the frame budget, the controller's search timeout,
  a stale frame, a detector that raised (:data:`CAL_FINE_EPISODE_NO_VERDICT` /
  :data:`CAL_FINE_EPISODE_DETECTOR_FAILED`);
* a document in which no episode locked (:data:`CAL_FINE_EPISODE_NO_SUCCESS`), because then no
  correction count exists to bound.

The prepared scene is stepped, and the preparation is not guaranteed contact-free (the dataset profile
places the cup and the bottle by jitter and the recorder rendered without ever stepping): one held-out seed
of this campaign has its cup separated from the bottle by the solver in the first control period and pushed
out of the head camera's view. Every episode therefore records the cup's prepared position, its position at
the end of the loop and the distance between them, so such an episode is visible as a scene that moved
rather than as a search that found nothing.

An episode that *did* run to a verdict and did not lock - the cup was never found, the frame held two
cups, or the cup could not be centred - is recorded with ``succeeded: false``, its failure code and
``fine_corrections: null``. A number is never written for an episode that did not lock, and the count of
refused episodes is part of the document.

The only part that touches MuJoCo, the dataset renderer, the detector or a GPU is
:func:`prepare_episode_scene`, :class:`MujocoEpisodePlant` and the production detector factory, and all
three import their dependencies inside the call. The detector is the production head detector
(``HeadRgbDetector`` over ``YoloSegDetector``: the same class filter, aspect gate and spatial track
association the running search applies) at the selected candidate's declared head operating point, and
this measurement never falls back to the CPU.
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
    CAL_DEADBAND_CUP_LOST,
    CAL_DEADBAND_OUT_OF_CORRIDOR,
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
    DIGEST_CONVENTION,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
    SETTLE_CONSECUTIVE_STEPS,
    SIMULATION_TIME_BASE,
    _declared_weights,
    _digest,
    _finite,
    classify_stop,
    read_control_period,
    verify_simulation_time_base,
)
from so101_demo.act.head_search_timing_measurement import (
    runtime_identity as measurement_runtime_identity,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1

KIND = "head_search_calibration_fine_correction_episodes"
RECEIPT_KIND = "head_search_calibration_fine_correction_episode_measurement_receipt"
PHASE = "fine_correction_episodes"

ARTIFACT = "fine-correction-episodes.json"
RECEIPT_ARTIFACT = "measurement-receipt.json"

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


# --- the declared split ---------------------------------------------------------------------------


def _partitions_document(partitions) -> Mapping:
    if not isinstance(partitions, Mapping):
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the scenario partitions are not a document, so no held-out seed can be shown to belong to a "
            "declared split",
        )
    return partitions


def declared_split_seeds(partitions, *, split: str, seeds=None) -> list[int]:
    """The seeds of one declared split, in declaration order, or the refusal that stops the producer.

    The partitions are the single tracked source of the head-search seed partitions, so a seed that the
    declared split does not carry - a calibration seed in particular - is refused rather than measured:
    the fine-correction numbers are never calibrated on the frames they are validated on.
    """

    document = _partitions_document(partitions)
    declared = document.get(split)
    if isinstance(declared, (str, bytes)) or not isinstance(declared, Sequence) or not declared:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the scenario partitions declare no split {split!r}, so the seeds of this measurement are not "
            f"declared anywhere",
        )
    declared_seeds = [int(seed) for seed in declared]
    other = {
        name: {int(seed) for seed in value}
        for name, value in document.items()
        if name != split
        and isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and value
        and all(type(seed) is int and not isinstance(seed, bool) for seed in value)
    }
    if seeds is None:
        return declared_seeds
    chosen: list[int] = []
    for seed in seeds:
        if type(seed) is not int or isinstance(seed, bool):
            raise ValueError(f"every declared seed must be a whole number: {seed!r}")
        if seed in chosen:
            raise ValueError(f"the seed {seed} is declared twice")
        if seed not in declared_seeds:
            for name, members in other.items():
                if seed in members:
                    raise _refuse(
                        CAL_FINE_EPISODE_SPLIT_LEAK,
                        f"the seed {seed} belongs to the {name!r} split, which may never bound the "
                        f"fine-correction numbers: only the declared split {split!r} may, because the "
                        f"fine-correction path is never calibrated on the frames it is validated on",
                    )
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"the seed {seed} belongs to no split of the scenario partitions, so the scene it would "
                f"prepare is not a declared one",
            )
        chosen.append(seed)
    if not chosen:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"no seed of the declared split {split!r} was offered, so this measurement would carry no "
            f"episode at all",
        )
    return chosen


def condition_class_for_index(index: int, condition_classes) -> str:
    """The condition class `record_episodes7.py:40` assigns to the index-th seed of a split.

    The recorder walks its seed list and assigns `CLASSES[min(index // 2, len(CLASSES) - 1)]`, so the
    scene a held-out seed was rendered from follows from its *position* in the split. This measurement
    reproduces that convention rather than inventing a mapping of its own.
    """

    if (
        isinstance(condition_classes, (str, bytes))
        or not isinstance(condition_classes, Sequence)
        or not condition_classes
    ):
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the scenario partitions declare no condition classes, so no episode's scene can be prepared",
        )
    if type(index) is not int or isinstance(index, bool) or index < 0:
        raise ValueError("a condition class index must be a whole non-negative number")
    position = min(index // 2, len(condition_classes) - 1)
    return str(condition_classes[position])


def cup_count_for_condition_class(condition_class: str) -> int:
    """How many cups the recorder put in the scene of one condition class.

    `record_episodes7.py:41`: `0 if cls == "no_cup" else (2 if cls == "two_cups" else 1)`.
    """

    if condition_class == "no_cup":
        return 0
    if condition_class == "two_cups":
        return 2
    return 1


# --- the two corridors -----------------------------------------------------------------------------


def coarse_corridor_rad(*, geometry_seal) -> tuple[float, float]:
    """HS-302's corridor: the required search domain intersected with the lock-valid neck interval."""

    return _re_raised(motion_corridor_rad, geometry_seal=geometry_seal)


def fine_corridor_rad(*, geometry_seal) -> tuple[float, float]:
    """The interval a fine correction has to stay inside: the seal's own lock-valid neck interval.

    The seal declares this interval as the one a lock is valid in, the production controller's own plan
    clamps its stops to it, and phase 6 reduces `max_fine_total_rad`'s headroom from it. It is read here
    rather than assumed, and a seal that declares it not at all is refused.
    """

    if not isinstance(geometry_seal, Mapping):
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, "the sealed geometry is not a document")
    value = geometry_seal.get("lock_valid_neck_rad")
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the sealed geometry declares no lock_valid_neck_rad, so no interval bounds a fine correction",
        )
    low, high = (float(bound) for bound in value)
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed lock_valid_neck_rad {[low, high]} is not a finite ordered interval, so no fine "
            f"correction can be shown to stay inside it",
        )
    return low, high


def _fine_corridor_check(*, angle_rad: float, corridor_rad, what: str) -> None:
    """The deadband module's own corridor check, re-raised under this producer's code.

    The rule is the same one - nothing is ever clamped - but this measurement declares *two* corridors,
    so the refusal a caller records is this measurement's own rather than the deadband trial's.
    """

    try:
        _corridor_check(angle_rad=angle_rad, corridor_rad=corridor_rad, what=what)
    except CalibrationDeadbandMeasurementRefused as error:
        raise _refuse(CAL_FINE_EPISODE_OUT_OF_CORRIDOR, error.detail) from error


def _cup_drift_m(prepared, final) -> float | None:
    """How far the loop's own stepping moved the cup from where the preparation left it.

    The prepared scene is not necessarily contact-free (the dataset profile places the cup and the bottle
    by jitter and the recorder rendered without stepping), so the solver can separate two bodies in the
    first control periods. That is a property of the scene and not of the search, so every episode records
    the cup's prepared position, its position at the end of the loop and the distance between them: an
    episode whose cup was pushed out of the camera's view has to say so rather than look like a search that
    simply did not find it.
    """

    if prepared is None or final is None:
        return None
    if len(prepared) != 3 or len(final) != 3:
        return None
    return math.sqrt(sum((float(a) - float(b)) ** 2 for a, b in zip(prepared, final)))


def required_domain_excursion_rad(angle_rad: float, required_domain_rad) -> float:
    """How far outside the required search domain an angle lies; 0.0 when it is inside.

    This is recorded, never refused: the required domain is the coverage the coarse sweep owes, and the
    centring move is the controller's own. An episode that locks outside it measured a real lock, and the
    distance is what says how far outside the pick workspace's search domain the scene actually was.
    """

    low, high = (float(bound) for bound in required_domain_rad)
    angle = float(angle_rad)
    if angle < low:
        return low - angle
    if angle > high:
        return angle - high
    return 0.0


# --- the correction count and the controller's own --------------------------------------------------


def verify_correction_consistency(
    *, episode_id: str, count: int, magnitudes, controller_fine_count: int, controller_fine_angle_rad: float
) -> None:
    """Prove the recorded count and sum are the controller's own, or refuse to write them.

    The production controller counts its fine corrections and accumulates their travel in `fine_count` and
    `fine_angle`. A reduction that disagrees with either is not a measurement of what the controller did,
    so the episode is refused rather than recorded - this is what makes "never fabricate a correction
    count" checkable by a reviewer instead of promised.
    """

    values = [float(magnitude) for magnitude in magnitudes]
    if any(not math.isfinite(value) or value <= 0.0 for value in values):
        raise ValueError(
            f"every fine correction of the episode {episode_id!r} must be a positive finite magnitude"
        )
    if len(values) != count:
        raise ValueError(
            f"the episode {episode_id!r} records {count} corrections and {len(values)} magnitudes"
        )
    if count != int(controller_fine_count):
        raise _refuse(
            CAL_FINE_EPISODE_CORRECTION_MISMATCH,
            f"the episode {episode_id!r} reduced {count} fine corrections but the production controller "
            f"counted {int(controller_fine_count)}, so the number this document would carry is not the "
            f"one the controller made",
        )
    total = sum(values)
    if not math.isclose(
        total, float(controller_fine_angle_rad), rel_tol=0.0, abs_tol=_CORRECTION_TOLERANCE_RAD
    ):
        raise _refuse(
            CAL_FINE_EPISODE_CORRECTION_MISMATCH,
            f"the episode {episode_id!r} reduced {total} rad of fine correction but the production "
            f"controller accumulated {float(controller_fine_angle_rad)}, so the magnitudes this document "
            f"would carry are not the ones the controller commanded",
        )


def _budget_binding(*, count: int, total: float, largest_single: float, budget: Mapping) -> bool:
    """Whether the declared instrument budget is what stopped the episode."""

    if count >= int(budget["max_fine_corrections"]):
        return True
    return total + largest_single > float(budget["max_fine_total_rad"]) + _CORRECTION_TOLERANCE_RAD


# --- the closed loop ---------------------------------------------------------------------------------


def run_fine_correction_episode(
    *,
    controller_config: Mapping,
    plant,
    detector,
    coarse_corridor_rad,
    fine_corridor_rad,
    episode_id: str,
    seed: int,
    split: str,
    scenario: str,
    anchor: str = "left",
    max_frames: int = DEFAULT_MAX_FRAMES,
    settle_consecutive_steps: int = SETTLE_CONSECUTIVE_STEPS,
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
    clock=time.monotonic,
) -> dict:
    """One held-out scene's closed loop, from the anchor through the plan to its terminal verdict.

    The production controller is driven frame by frame: it emits a target, the plant steps the sealed neck
    to it and settles, the head camera renders, the detector finds the cup, and the controller consumes
    that frame and its feedback to emit the next target. Every stop of the bounded plan is checked against
    the coarse corridor and every fine correction and settled angle against the fine corridor, before it
    is commanded; the settle rule and the simulation time base are the timing module's own; and the
    correction count and magnitudes are checked against the controller's own counters before they are
    returned. A verdict that is not a lock is returned as a recorded failure, and anything that stops the
    episode from reaching a verdict at all is a refusal.
    """

    from so101_demo.act.search import HeadSearchController

    if type(max_frames) is not int or isinstance(max_frames, bool) or max_frames < 1:
        raise ValueError("a fine-correction episode needs a positive whole frame budget")
    timestep = getattr(plant, "simulation_timestep_s", None)
    if not _finite(timestep) or float(timestep) <= 0.0:
        raise ValueError("the plant must declare the simulation timestep its stops were stepped at")
    config = dict(controller_config)
    coarse_low, coarse_high = (float(bound) for bound in coarse_corridor_rad)
    fine_low, fine_high = (float(bound) for bound in fine_corridor_rad)

    _fine_corridor_check(
        angle_rad=float(config["search_start_rad"]),
        corridor_rad=(coarse_low, coarse_high),
        what=f"declared search start of the episode {episode_id!r}",
    )
    controller = HeadSearchController(config)
    reset = getattr(detector, "reset", None)
    if callable(reset):
        reset()
    started = time.time()

    target = float(config["search_start_rad"])
    stops: list[dict] = []
    frames: list[dict] = []
    corrections: list[float] = []
    detection_frames = 0
    terminal = None
    verdict = None
    failure_code = None
    failure_detail = None

    def command(target_rad: float, *, kind: str) -> None:
        """Command a target inside its own corridor, step the plant, and record the stop it produced."""

        corridor = (coarse_low, coarse_high) if kind == "plan" else (fine_low, fine_high)
        _fine_corridor_check(
            angle_rad=float(target_rad),
            corridor_rad=corridor,
            what=f"{kind} target of the episode {episode_id!r}",
        )
        stop = dict(plant.settle_to(float(target_rad)))
        stop.update(anchor=anchor, index=len(stops), kind=kind, time_base=SIMULATION_TIME_BASE)
        stops.append(
            _re_raised(
                classify_stop,
                stop,
                settle_consecutive_steps=settle_consecutive_steps,
                max_settle_s=max_settle_s,
            )
        )
        _fine_corridor_check(
            angle_rad=float(plant.yaw_rad),
            corridor_rad=(fine_low, fine_high),
            what=f"settled neck angle of the episode {episode_id!r}",
        )

    command(target, kind="plan")
    while len(frames) < max_frames:
        frame_wall = clock()
        image = plant.render_frame()
        received_wall = clock()
        stamp_ns = int(plant.frame_stamp_ns)
        geometry = plant.optical_geometry()
        try:
            detections = _detections(detector, image, stamp_ns)
        except CalibrationDeadbandMeasurementRefused as error:
            raise _refuse(
                CAL_FINE_EPISODE_DETECTOR_FAILED,
                f"the detector failed on a frame of the episode {episode_id!r} ({error.detail}), so this "
                f"episode is not a measurement and no correction count is recorded for it",
            ) from error
        if detections:
            detection_frames += 1
        decision_wall = clock()
        sim_s = float(plant.time_s)
        yaw, velocity = float(plant.yaw_rad), float(plant.velocity_rad_s)
        frame = {
            "session_id": config["session_id"],
            "attempt_id": config["attempt_id"],
            "sim_time_s": sim_s,
            "received_wall_s": received_wall,
            "frame_sim_s": sim_s,
            "received_sim_s": sim_s,
            "decision_sim_s": sim_s,
            "frame_monotonic_s": frame_wall,
            "received_monotonic_s": received_wall,
            "decision_monotonic_s": decision_wall,
            "frame_id": config["frame_id"],
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
            "session_id": config["session_id"],
            "attempt_id": config["attempt_id"],
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
            anchor=anchor,
            frame={
                **frame,
                "previous_frame_sim_s": None if not frames else frames[-1]["frame_sim_s"],
            },
            decision=decision,
            detections=detections,
        )
        if "found" in decision:
            record["neck_target_rad"] = None
            record["move_kind"] = "hold"
            frames.append(record)
            terminal, verdict = dict(decision), decision["status"]
            break
        if decision.get("stop"):
            raise _refuse(
                CAL_FINE_EPISODE_NO_VERDICT,
                f"the closed loop of the episode {episode_id!r} stopped on the controller status "
                f"{decision.get('status')!r} before it reached a verdict: the frame cadence this harness "
                f"produced was not one the controller would decide on",
            )
        target = float(decision["neck_target_rad"])
        status = decision.get("status")
        if corrections_after > corrections_before:
            # the production controller's own counter is what makes a move a fine correction: it
            # increments exactly where it sets the target to `yaw + correction`, so the magnitude is that
            # correction and nothing this harness had to guess
            move_kind = "fine"
            corrections.append(target - yaw)
        elif target != previous_target and status == "SEARCH_CUP":
            move_kind = "plan"
        elif target == previous_target:
            move_kind = "hold"
        else:
            raise _refuse(
                CAL_FINE_EPISODE_NO_VERDICT,
                f"the controller of the episode {episode_id!r} moved the neck under the status {status!r} "
                f"without counting a fine correction, which this measurement cannot classify",
            )
        record["neck_target_rad"] = target
        record["move_kind"] = move_kind
        frames.append(record)
        command(target, kind=move_kind)

    if terminal is None:
        raise _refuse(
            CAL_FINE_EPISODE_NO_VERDICT,
            f"the closed loop of the episode {episode_id!r} spent its whole {max_frames}-frame budget "
            f"without a verdict, so it measured no correction count",
        )

    magnitudes = [abs(value) for value in corrections]
    succeeded = verdict == "TARGET_LOCKED" and bool(terminal.get("found"))
    if succeeded:
        _re_raised(
            verify_correction_consistency,
            episode_id=episode_id,
            count=len(magnitudes),
            magnitudes=magnitudes,
            controller_fine_count=controller.fine_count,
            controller_fine_angle_rad=controller.fine_angle,
        )
    elif verdict == "TARGET_NOT_FOUND" or verdict == "TARGET_NOT_FOUND_WITHIN_SAFE_INTERVAL":
        failure_code, failure_detail = (
            CAL_FINE_EPISODE_CUP_NOT_FOUND,
            "the bounded sweep finished without a single frame that carried the cup, so this episode "
            "records no correction count",
        )
    elif verdict == "TARGET_AMBIGUOUS":
        failure_code, failure_detail = (
            CAL_FINE_EPISODE_TARGET_AMBIGUOUS,
            "a frame of this episode carried more than one candidate cup, so the controller never had a "
            "single cup to centre and this episode records no correction count",
        )
    elif verdict == "TARGET_NOT_CENTERED":
        budget = {
            "max_fine_corrections": config["max_fine_corrections"],
            "max_fine_total_rad": config["max_fine_total_rad"],
        }
        binding = _budget_binding(
            count=controller.fine_count,
            total=controller.fine_angle,
            largest_single=max(magnitudes) if magnitudes else 0.0,
            budget=budget,
        )
        failure_code = CAL_FINE_EPISODE_BUDGET_EXHAUSTED if binding else CAL_FINE_EPISODE_NOT_CENTERED
        failure_detail = (
            f"the controller stopped centring with status TARGET_NOT_CENTERED after "
            f"{controller.fine_count} corrections and {controller.fine_angle} rad"
            + (
                f", which reached the declared budget {budget}"
                if binding
                else ", which did not reach the declared budget"
            )
        )
    elif verdict == "SEARCH_UNSAFE":
        raise _refuse(
            CAL_FINE_EPISODE_OUT_OF_CORRIDOR,
            f"the controller refused to observe the neck as safe ({verdict}) during the episode "
            f"{episode_id!r}, so the loop left the interval the seal bounds",
        )
    else:
        raise _refuse(
            CAL_FINE_EPISODE_NO_VERDICT,
            f"the episode {episode_id!r} ended on the controller status {verdict!r}, which is not a lock "
            f"and not one of the verdicts this measurement records",
        )

    budget_binding = failure_code == CAL_FINE_EPISODE_BUDGET_EXHAUSTED
    locked = float(plant.yaw_rad) if succeeded else None
    excursion = (
        None if locked is None else required_domain_excursion_rad(locked, config["required_search_domain_rad"])
    )
    result = {
        "episode_id": episode_id,
        "seed": int(seed),
        "split": split,
        "scenario": scenario,
        "anchor": anchor,
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(timestep),
        "goal_tolerance_rad": float(config["goal_tolerance_rad"]),
        "settle_velocity_rad_s": float(config["settle_velocity_rad_s"]),
        "search_start_rad": float(config["search_start_rad"]),
        "coarse_corridor_rad": [coarse_low, coarse_high],
        "fine_corridor_rad": [fine_low, fine_high],
        "required_search_domain_rad": [
            float(bound) for bound in config["required_search_domain_rad"]
        ],
        "stops": stops,
        "frames": frames,
        "terminal_status": verdict,
        "found": bool(terminal.get("found")),
        "succeeded": bool(succeeded),
        "failure_code": failure_code,
        "failure_detail": failure_detail,
        "fine_corrections": len(magnitudes) if succeeded else None,
        "fine_corrections_rad": magnitudes if succeeded else [],
        "cumulative_fine_correction_rad": sum(magnitudes) if succeeded else None,
        "largest_single_correction_rad": max(magnitudes) if (succeeded and magnitudes) else None,
        "controller_fine_count": int(controller.fine_count),
        "controller_fine_angle_rad": float(controller.fine_angle),
        "corrections_observed": len(magnitudes),
        "corrections_observed_rad": magnitudes,
        "budget_binding": bool(budget_binding),
        "detection_frames": detection_frames,
        "plan_moves": sum(1 for stop in stops[1:] if stop["kind"] == "plan"),
        "locked_neck_rad": locked,
        "required_domain_excursion_rad": excursion,
        "locked_outside_required_domain": bool(excursion),
        "correction_definition": CORRECTION_DEFINITION,
        "success_definition": SUCCESS_DEFINITION,
        "corridor_definition": CORRIDOR_DEFINITION,
        "cup_position_m": getattr(plant, "cup_position_m", None),
        "cup_prepared_m": getattr(plant, "prepared_cup_position_m", None),
        "cup_drift_m": _cup_drift_m(
            getattr(plant, "prepared_cup_position_m", None), getattr(plant, "cup_position_m", None)
        ),
        "arm_drift_rad": getattr(plant, "arm_drift_rad", None),
        "wall_time_s": time.time() - started,
        "sim_time_s": float(plant.time_s),
    }
    _re_raised(verify_simulation_time_base, result)
    return result


# --- the document ------------------------------------------------------------------------------------


def _reference(name: str, path, digest: str | None = None) -> dict | None:
    if path is None:
        return None
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        digest = _digest(path)
    return {"path": str(path), "sha256": digest}


def episode_record(episode: Mapping) -> dict:
    """One episode's record for phase 6: exactly the five keys the phase reads, and nothing else.

    A refused episode carries `fine_corrections: null` and no magnitudes at all, so no reader can mistake
    "this episode did not lock" for "this episode needed zero corrections".
    """

    if not isinstance(episode, Mapping):
        raise ValueError("every episode record must be a mapping")
    episode_id = episode.get("episode_id")
    if type(episode_id) is not str or not episode_id:
        raise ValueError("every episode names itself")
    split = episode.get("split")
    if type(split) is not str or not split:
        raise _refuse(
            CAL_FINE_EPISODE_SPLIT_LEAK,
            f"the episode {episode_id!r} declares no split, so it cannot be shown to belong to a "
            f"held-out validation split",
        )
    succeeded = episode.get("succeeded")
    if succeeded is True:
        count = episode.get("fine_corrections")
        magnitudes = episode.get("fine_corrections_rad")
        if type(count) is int and not isinstance(count, bool) and count == 0:
            raise _refuse(
                CAL_FINE_EPISODE_NO_CORRECTION_NEEDED,
                f"the episode {episode_id!r} locked without needing a single fine correction, so it "
                f"carries no correction count: phase 6 refuses a successful episode whose count is not "
                f"positive (head_search_search_params._episode_numbers, CAL_SWEEP_UNSTABLE), and a "
                f"document holding one could not be consumed, so this producer refuses instead of writing "
                f"a number phase 6 cannot read",
            )
        if type(count) is not int or isinstance(count, bool) or count < 1:
            raise _refuse(
                CAL_FINE_EPISODE_NO_SUCCESS,
                f"the successful episode {episode_id!r} records no positive fine-correction count",
            )
        if (
            isinstance(magnitudes, (str, bytes))
            or not isinstance(magnitudes, Sequence)
            or len(magnitudes) != count
        ):
            raise _refuse(
                CAL_FINE_EPISODE_CORRECTION_MISMATCH,
                f"the successful episode {episode_id!r} records {count} fine corrections but not one "
                f"magnitude per correction",
            )
        record = {
            "episode_id": episode_id,
            "split": split,
            "succeeded": True,
            "fine_corrections": int(count),
            "fine_corrections_rad": [float(magnitude) for magnitude in magnitudes],
        }
    elif succeeded is False:
        record = {
            "episode_id": episode_id,
            "split": split,
            "succeeded": False,
            "fine_corrections": None,
            "fine_corrections_rad": [],
        }
    else:
        raise ValueError(f"the episode {episode_id!r} declares no success verdict")
    return {key: record[key] for key in RECORD_KEYS}


def build_fine_correction_episodes(
    *,
    path,
    command,
    episodes,
    controller_config: Mapping,
    control: Mapping,
    scene_path,
    scene_sha256: str,
    dataset_config_path,
    dataset_config_sha256: str,
    geometry_seal_path,
    geometry_seal_sha256: str,
    production_search_config_path,
    production_search_config_sha256: str,
    frozen_candidate_path,
    frozen_candidate_sha256: str,
    weights_path,
    weights_sha256: str,
    scenario_partitions_path,
    scenario_partitions_sha256: str,
    split: str,
    seeds,
    detector_operating_point: Mapping,
    coarse_corridor_rad,
    fine_corridor_rad,
    measurement_budget: Mapping,
    runtime_identity_document: Mapping | None = None,
    scene_preparation: Mapping | None = None,
    anchors=None,
    detector_loaded: bool = True,
    device: str = "cuda",
) -> dict:
    """The `fine_correction_episodes` document: one record per measured held-out episode.

    `records` carries exactly the five keys phase 6 reads, reduced from the episodes, and every episode
    itself is kept beside them with its stops, frames, corrections, controller counters, the prepared
    cup's position and its terminal verdict, so a reviewer can recompute each record rather than trust
    it. The split is recorded in full - the split name, the seeds, the partitions' digest and the
    calibration seeds that were *not* used - so the isolation rule phase 6 re-checks is checkable from
    the document alone.
    """

    if isinstance(episodes, (str, bytes)) or not isinstance(episodes, Sequence) or not episodes:
        raise ValueError("the document needs at least one measured episode")
    declared_seeds = [int(seed) for seed in seeds]
    records = []
    for episode in episodes:
        if not isinstance(episode, Mapping):
            raise ValueError("every measured episode must be a mapping")
        episode_split = episode.get("split")
        if type(episode_split) is not str or not episode_split:
            raise _refuse(
                CAL_FINE_EPISODE_SPLIT_LEAK,
                "an episode declares no split, so it cannot be shown to belong to the declared held-out "
                "validation split",
            )
        if episode_split != split:
            raise _refuse(
                CAL_FINE_EPISODE_SPLIT_LEAK,
                f"a {episode_split!r} episode was offered to this document, whose declared split is "
                f"{split!r}: the fine-correction numbers are never calibrated on the frames they are "
                f"validated on",
            )
        if episode.get("budget_binding") is True:
            raise _refuse(
                CAL_FINE_EPISODE_BUDGET_EXHAUSTED,
                f"the episode {episode.get('episode_id')!r} was censored by the harness's declared "
                f"measurement budget {dict(measurement_budget)}, so the largest correction count of this "
                f"document would not be a maximum",
            )
        records.append(episode_record(episode))
    succeeded = [record for record in records if record["succeeded"]]
    if not succeeded:
        raise _refuse(
            CAL_FINE_EPISODE_NO_SUCCESS,
            f"none of the {len(records)} held-out episodes locked, so no fine-correction count can be "
            f"bounded from them",
        )
    anchors_seen = []
    for episode in episodes:
        name = episode.get("anchor")
        if type(name) is str and name and name not in anchors_seen:
            anchors_seen.append(name)
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "path": None if path is None else str(path),
        "command": command,
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(episodes[0]["simulation_timestep_s"]),
        "control_period_s": float(control["control_period_s"]),
        "control_period_source": dict(control),
        "frame_rate_hz": FRAME_RATE_HZ,
        "frame_period_s": FRAME_PERIOD_S,
        "lock_frames_required": LOCK_FRAMES,
        "correction_definition": CORRECTION_DEFINITION,
        "success_definition": SUCCESS_DEFINITION,
        "corridor_definition": CORRIDOR_DEFINITION,
        "scene_definition": SCENE_DEFINITION,
        "budget_definition": BUDGET_DEFINITION,
        "split_declaration": {
            "split": split,
            "seeds": declared_seeds,
            "held_out_only": True,
            "calibration_seeds_used": [],
            "partitions_path": None if scenario_partitions_path is None else str(scenario_partitions_path),
            "partitions_sha256": scenario_partitions_sha256,
            "isolation_rule": (
                "the fine-correction numbers are bounded by held-out or validation episodes only; an "
                "episode of the calibration split is refused, never measured or averaged in"
            ),
        },
        "episode_count": len(records),
        "succeeded_count": len(succeeded),
        "refused_count": len(records) - len(succeeded),
        "budget_censored": False,
        "required_domain_excursions": [
            {
                "episode_id": episode.get("episode_id"),
                "locked_neck_rad": episode.get("locked_neck_rad"),
                "required_domain_excursion_rad": episode.get("required_domain_excursion_rad"),
            }
            for episode in episodes
            if episode.get("succeeded") is True
        ],
        "locked_outside_required_domain_count": sum(
            1 for episode in episodes if episode.get("locked_outside_required_domain") is True
        ),
        "coarse_corridor_rad": [float(bound) for bound in coarse_corridor_rad],
        "fine_corridor_rad": [float(bound) for bound in fine_corridor_rad],
        "measurement_budget": {
            "max_fine_corrections": int(measurement_budget["max_fine_corrections"]),
            "max_fine_total_rad": float(measurement_budget["max_fine_total_rad"]),
        },
        "records": records,
        "records_semantics": (
            "one record per measured held-out episode carrying exactly the keys phase 6 reads: "
            "fine_corrections is the number of fine corrections a successful episode needed and "
            "fine_corrections_rad one positive magnitude per correction. An episode that did not lock "
            "carries succeeded=false with a null count and no magnitudes, never a zero"
        ),
        "episodes": [dict(episode) for episode in episodes],
        "anchors": anchors_seen if anchors is None else [str(anchor) for anchor in anchors],
        "controller_thresholds": {
            "min_confidence": float(controller_config["min_confidence"]),
            "min_area_px2": float(controller_config["min_area_px2"]),
            "vertical_bounds_px": [float(bound) for bound in controller_config["vertical_bounds_px"]],
            "center_deadband_px": float(controller_config["center_deadband_px"]),
            "max_fine_corrections": controller_config["max_fine_corrections"],
            "max_fine_total_rad": float(controller_config["max_fine_total_rad"]),
            "settle_velocity_rad_s": float(controller_config["settle_velocity_rad_s"]),
            "goal_tolerance_rad": float(controller_config["goal_tolerance_rad"]),
        },
        "controller_budget": (
            "the two fine-correction bounds above are the harness's measurement budget, not the "
            "calibrated values: they are the instrument's limits, and the production declaration stands "
            "beside them in `production_declaration`"
        ),
        "detector_operating_point": dict(detector_operating_point or {}),
        "scene_preparation": dict(
            scene_preparation
            or {
                "cup_placement": (
                    "prepared by the dataset renderer of the head profile for this seed"
                )
            }
        ),
        "scene_path": str(scene_path),
        "scene_sha256": scene_sha256,
        "dataset_config": _reference(
            "the head dataset profile", dataset_config_path, dataset_config_sha256
        ),
        "geometry_seal": _reference("the sealed geometry", geometry_seal_path, geometry_seal_sha256),
        "production_search_config": _reference(
            "the production search configuration",
            production_search_config_path,
            production_search_config_sha256,
        ),
        "frozen_candidate": _reference(
            "the frozen candidate", frozen_candidate_path, frozen_candidate_sha256
        ),
        "weights": _reference("the detector weights", weights_path, weights_sha256),
        "detector_loaded": bool(detector_loaded),
        "cuda_used": bool(detector_loaded) and str(device).startswith("cuda"),
        "device": device,
        "tracking_measured": False,
        "tracking_detail": (
            "the frames are produced in process, so the detection identities come from the production head "
            "detector's own spatial track association over this episode's frames and not from a running "
            "multi-object tracker across a topic"
        ),
        "transport_measured": False,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "measured_here": True,
        "motion_commanded": False,
        "runtime_identity": dict(runtime_identity_document or {}),
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


# --- the scene the held-out split was rendered from --------------------------------------------------


def _resolve_config_scene(dataset_config_path) -> Path:
    """The MuJoCo scene a dataset profile renders, resolved from the profile's own declaration."""

    path = Path(dataset_config_path)
    if not path.is_file():
        raise FileNotFoundError(f"the fine-correction episodes need {path}")
    contents = path.read_text(encoding="utf-8")
    try:
        document = json.loads(contents)
    except json.JSONDecodeError:
        import yaml

        document = yaml.safe_load(contents)
    if not isinstance(document, Mapping) or "mjcf_path" not in document:
        raise _refuse(
            CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
            f"the dataset profile {path} declares no mjcf_path, so the scene these episodes would be "
            f"rendered from is not declared",
        )
    declared = Path(str(document["mjcf_path"]))
    return declared if declared.is_absolute() else (path.parent / declared).resolve()


def scene_preparation_request(
    *, dataset_config_path, generator_commit, seed, cup_count, scenario, scene_path, split
) -> dict:
    """The one request :func:`prepare_episode_scene` is called with, built in one place.

    The producer and the preparer have to agree on this mapping exactly - the preparer's signature is the
    contract - so it is built here rather than inline, and both are checked against each other by the
    tests. `scenario` and `split` are carried for the record: the scene a seed prepares depends on its cup
    count and its seed, and the condition class is the recorder's own name for that count.
    """

    return {
        "dataset_config_path": dataset_config_path,
        "generator_commit": generator_commit,
        "seed": int(seed),
        "cup_count": int(cup_count),
        "scenario": scenario,
        "scene_path": scene_path,
        "split": split,
    }


def prepare_episode_scene(
    *,
    dataset_config_path,
    generator_commit,
    seed,
    cup_count,
    scenario=None,
    scene_path=None,
    split=None,
) -> dict:
    """Prepare one held-out seed's scene exactly as the recorder prepared it, and snapshot it.

    The recorder (`record_episodes7.py`) built a `MuJoCoDatasetRenderer` from the head dataset profile and
    called `_prepare(numpy.random.default_rng(seed), DatasetScenario.for_cup_count(cups))` before it
    rendered a frame. This does the same and returns the state that preparation produced - the free joints,
    the camera position and the materials - so the plant can be put into that very scene rather than into
    a scene of its own.

    Every keyword :func:`scene_preparation_request` builds is accepted here, including the ones the scene
    does not depend on (`scenario`, `split`): the call has to be one call with one mapping, and a
    signature that silently dropped a key would prepare a scene nobody asked for.
    """

    import numpy as np
    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetScenario,
        MuJoCoDatasetRenderer,
        load_dataset_config,
    )

    config = load_dataset_config(Path(dataset_config_path), generator_commit=generator_commit)
    renderer = MuJoCoDatasetRenderer(config)
    try:
        renderer._prepare(
            np.random.default_rng(int(seed)), DatasetScenario.for_cup_count(int(cup_count))
        )
        model, data = renderer._model, renderer._data
        state = {
            "qpos": [float(value) for value in data.qpos],
            "qvel": [float(value) for value in data.qvel],
            "cam_pos": [[float(value) for value in row] for row in model.cam_pos],
            "mat_rgba": [[float(value) for value in row] for row in model.mat_rgba],
            "scene_path": str(scene_path),
            "dataset_config_path": str(dataset_config_path),
            "generator_commit": str(generator_commit),
            "seed": int(seed),
            "cup_count": int(cup_count),
        }
    finally:
        renderer.close()
    return state


class MujocoEpisodePlant(MujocoClosedLoopPlant):
    """The sealed scene's neck, put into one held-out seed's prepared scene and commanded.

    This is the only place in this module that imports MuJoCo, and it does so through the deadband
    measurement's own plant, which commands the scene's ``neck_yaw_joint`` position actuator at the sealed
    controller period, applies the timing module's declared settle rule and renders the head camera. What
    this subclass adds is the prepared scene: the free joints, the camera position and the materials of the
    snapshot the dataset renderer produced are copied in, every *other* actuator is held at the position
    that preparation left it in (so the arm does not drift toward the actuators' unset targets while the
    neck moves), and the neck starts where the sealed anchor says.
    """

    def __init__(self, request: Mapping) -> None:
        super().__init__(request)
        self._start_rad = float(request["start_rad"])
        self._prepared_qpos = None
        self._arm_joints: list[int] = []
        self._prepared_cup_position_m = list(self.cup_position_m)
        self.apply_prepared_scene(request.get("scene_state"))

    def apply_prepared_scene(self, state) -> None:
        """Put this plant into the prepared scene, or leave the anchor's own placement standing."""

        if not isinstance(state, Mapping) or not state:
            return
        mujoco = self._mujoco
        qpos = [float(value) for value in state["qpos"]]
        if len(qpos) != self._model.nq:
            raise _refuse(
                CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
                f"the prepared scene carries {len(qpos)} positions and the sealed scene {self._model.nq}, "
                f"so these frames would be rendered from another model",
            )
        self._data.qpos[:] = qpos
        self._data.qvel[:] = 0.0
        # a scene may declare no material at all (`nmat` 0), so an empty snapshot is copied as nothing
        # rather than broadcast into a (0, 4) array; a non-empty one that does not fit is a refusal
        for name, values, count in (
            ("cam_pos", state["cam_pos"], int(self._model.ncam)),
            ("mat_rgba", state["mat_rgba"], int(self._model.nmat)),
        ):
            snapshot = [[float(value) for value in row] for row in values]
            if not snapshot and count == 0:
                continue
            if len(snapshot) != count:
                raise _refuse(
                    CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
                    f"the prepared scene carries {len(snapshot)} {name} rows and the sealed scene "
                    f"{count}, so these frames would be rendered from another model",
                )
            getattr(self._model, name)[:] = snapshot
        self._data.qpos[self._qpos_address] = float(self._start_rad)
        self._prepared_qpos = [float(value) for value in self._data.qpos]
        self._arm_joints = [
            int(self._model.actuator_trnid[actuator, 0])
            for actuator in range(self._model.nu)
            if int(self._model.actuator_trntype[actuator]) == int(mujoco.mjtTrn.mjTRN_JOINT)
            and int(self._model.actuator_trnid[actuator, 0]) != self._neck
        ]
        for actuator in range(self._model.nu):
            if int(self._model.actuator_trntype[actuator]) != int(mujoco.mjtTrn.mjTRN_JOINT):
                continue
            joint = int(self._model.actuator_trnid[actuator, 0])
            if joint == self._neck:
                continue
            value = float(self._data.qpos[int(self._model.jnt_qposadr[joint])])
            if bool(self._model.actuator_ctrllimited[actuator]):
                low, high = (float(bound) for bound in self._model.actuator_ctrlrange[actuator])
                value = min(max(value, low), high)
            self._data.ctrl[actuator] = value
        mujoco.mj_forward(self._model, self._data)
        # the capture has to follow `mj_forward`: `xpos` only holds the prepared scene once the model has
        # been forwarded with it, and a capture taken before that records the anchor placement instead
        self._prepared_cup_position_m = list(self.cup_position_m)

    @property
    def prepared_cup_position_m(self) -> list[float] | None:
        """Where the preparation left the cup, before the loop stepped the scene at all."""

        return None if self._prepared_cup_position_m is None else list(self._prepared_cup_position_m)

    @property
    def arm_drift_rad(self) -> float | None:
        """How far the held joints moved from the prepared scene, in radians (None before preparing)."""

        if self._prepared_qpos is None:
            return None
        return max(
            (
                abs(float(self._data.qpos[int(self._model.jnt_qposadr[joint])]) - self._prepared_qpos[
                    int(self._model.jnt_qposadr[joint])
                ])
                for joint in self._arm_joints
            ),
            default=0.0,
        )


# --- the producer ------------------------------------------------------------------------------------


def _measurement_budget(budget, *, start_rad: float, fine_corridor_rad) -> dict:
    """The declared instrument budget, checked against the interval a fine correction may travel in."""

    declared = dict(DEFAULT_MEASUREMENT_BUDGET if budget is None else budget)
    count = declared.get("max_fine_corrections")
    total = declared.get("max_fine_total_rad")
    if type(count) is not int or isinstance(count, bool) or count < 1:
        raise ValueError("the measurement budget needs a positive whole max_fine_corrections")
    if not _finite(total) or float(total) <= 0.0:
        raise ValueError("the measurement budget needs a positive finite max_fine_total_rad")
    low, high = (float(bound) for bound in fine_corridor_rad)
    if (
        start_rad - float(total) < low - _BOUND_TOLERANCE_RAD
        or start_rad + float(total) > high + _BOUND_TOLERANCE_RAD
    ):
        raise _refuse(
            CAL_FINE_EPISODE_OUT_OF_CORRIDOR,
            f"the declared measurement budget could command {float(total)} rad of fine correction from "
            f"the search start {start_rad}, which leaves the seal's lock-valid interval {[low, high]}",
        )
    return {"max_fine_corrections": int(count), "max_fine_total_rad": float(total)}


def write_head_search_fine_correction_episodes(
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
    seeds=None,
    split: str = HELD_OUT_SPLIT,
    anchors=None,
    device: str = "cuda",
    generator_commit: str = "unrecorded",
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps: int = SETTLE_CONSECUTIVE_STEPS,
    max_frames: int = DEFAULT_MAX_FRAMES,
    measurement_budget: Mapping | None = None,
    attempt_id: str = MEASUREMENT_ATTEMPT_ID,
    session_id: str = MEASUREMENT_SESSION_ID,
    command=None,
    plant=None,
    detector_factory=None,
    scene_preparer=None,
) -> dict:
    """Run one closed-loop episode per declared held-out seed and write the document phase 6 reads.

    Every declared input is read and cross-checked before a single scene is prepared: the scene has to be
    the one the sealed geometry pins, the dataset profile has to render that same scene, the control period
    has to be a whole number of the scene's own timesteps, the detector has to be the weight the sealed
    configuration declares, the frozen candidate has to declare its head operating point, the seeds have to
    belong to the declared held-out split, and the anchor's start and the instrument budget have to lie
    inside their corridors. The episodes then run one seed at a time, and the document and its receipt are
    the only files this producer creates.
    """

    started = time.time()
    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    frozen_path = Path(frozen_candidate_path)
    dataset_path = Path(dataset_config_path)
    partitions_path = Path(scenario_partitions_path)
    for path in (scene, seal_path, production_path, controller_path, frozen_path, dataset_path,
                 partitions_path):
        if not path.is_file():
            raise FileNotFoundError(f"the fine-correction episodes need {path}")
    weights = Path(weights_path)
    if not weights.is_file():
        raise FileNotFoundError(f"the fine-correction episodes need {weights}")

    partitions = json.loads(partitions_path.read_text(encoding="utf-8"))
    declared_seeds = declared_split_seeds(partitions, split=split, seeds=seeds)
    condition_classes = partitions.get("condition_classes")
    scenarios = [
        condition_class_for_index(index, condition_classes) for index in range(len(declared_seeds))
    ]

    declaration = read_mujoco_timestep(scene)
    seal = json.loads(seal_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    frozen = json.loads(frozen_path.read_text(encoding="utf-8"))
    scene_sha256 = declaration["scene_sha256"]
    sealed_scene = (seal.get("source_digests") or {}).get("scene_sha256")
    if sealed_scene != scene_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry pins the scene {sealed_scene}, but the scene these episodes would step "
            f"the neck in digests to {scene_sha256}",
        )
    declared_scene = _resolve_config_scene(dataset_path)
    if declared_scene.resolve() != scene.resolve():
        raise _refuse(
            CAL_FINE_EPISODE_SCENE_CONTRADICTORY,
            f"the dataset profile {dataset_path} renders {declared_scene}, but these episodes would step "
            f"the neck in {scene}: the scenes a held-out seed prepares and the scene this measurement "
            f"renders have to be the same one",
        )
    control_period = _re_raised(read_control_period, controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s steps, so the episodes could not command the neck at the production period",
        )
    weights_sha256 = _re_raised(_declared_weights, production, {"weights_path": weights_path})
    if str(device).startswith("cuda") and not _cuda_available():
        raise _refuse(
            CAL_TIMING_DEVICE_UNAVAILABLE,
            f"the detector was declared for {device!r} but no CUDA device is available, and this "
            f"measurement never falls back to the CPU",
        )
    operating_point = detector_operating_point(frozen)
    frozen_weights = frozen.get("weight_sha256")
    if isinstance(frozen_weights, str) and frozen_weights != weights_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the frozen candidate seals the weights {frozen_weights}, but the production search "
            f"configuration seals {weights_sha256}: the episodes would not close the loop with the "
            f"selected model",
        )
    coarse = coarse_corridor_rad(geometry_seal=seal)
    fine = fine_corridor_rad(geometry_seal=seal)
    requests = _anchor_requests(
        seal=seal,
        production=production,
        anchors=anchors,
        attempt_id=attempt_id,
        session_id=session_id,
    )
    if len(requests) != 1:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"this measurement runs one episode per held-out seed from exactly one sealed anchor, but "
            f"{len(requests)} were declared: the anchor is the search start every episode shares, and the "
            f"HS-302 corridor admits only the anchors whose start lies inside the required search domain",
        )
    request = requests[0]
    _fine_corridor_check(
        angle_rad=request["search_start_rad"],
        corridor_rad=coarse,
        what=f"declared search start of the anchor {request['anchor']!r}",
    )
    budget = _measurement_budget(
        measurement_budget, start_rad=float(request["search_start_rad"]), fine_corridor_rad=fine
    )
    controller = dict(request["controller_config"])
    controller["max_fine_corrections"] = budget["max_fine_corrections"]
    controller["max_fine_total_rad"] = budget["max_fine_total_rad"]
    camera = seal.get("camera") if isinstance(seal.get("camera"), Mapping) else {}
    output = Path(output_dir)
    output.mkdir(parents=True)

    prepare = prepare_episode_scene if scene_preparer is None else scene_preparer
    detector = (
        None
        if detector_factory is not None
        else build_production_head_detector(
            weights_path=weights,
            operating_point=operating_point,
            production=production,
            frame_id=controller["frame_id"],
            device=device,
            attempt_id=attempt_id,
            session_id=session_id,
        )
    )
    episodes: list[dict] = []
    scene_state_digests: dict[str, str] = {}
    for seed, scenario in zip(declared_seeds, scenarios):
        cup_count = cup_count_for_condition_class(scenario)
        state = prepare(
            **scene_preparation_request(
                dataset_config_path=dataset_path,
                generator_commit=generator_commit,
                seed=seed,
                cup_count=cup_count,
                scenario=scenario,
                scene_path=scene,
                split=split,
            )
        )
        episode_request = dict(request)
        episode_request["controller_config"] = controller
        episode_request["scene_state"] = state
        episode_request["seed"] = int(seed)
        scene_state_digests[str(seed)] = (
            canonical_sha256(dict(state)) if isinstance(state, Mapping) and state else ""
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
                        camera=camera,
                        control_period_s=control_period,
                        max_settle_s=max_settle_s,
                        settle_consecutive_steps=settle_consecutive_steps,
                    ),
                    "scene_state": state,
                    "seed": int(seed),
                    "scenario": scenario,
                    "split": split,
                }
            )
        )
        try:
            episodes.append(
                run_fine_correction_episode(
                    controller_config=controller,
                    plant=episode_plant,
                    detector=(
                        detector
                        if detector_factory is None
                        else detector_factory(episode_plant, episode_request)
                    ),
                    coarse_corridor_rad=coarse,
                    fine_corridor_rad=fine,
                    episode_id=f"{split}-{int(seed)}",
                    seed=int(seed),
                    split=split,
                    scenario=scenario,
                    anchor=request["anchor"],
                    max_frames=max_frames,
                    settle_consecutive_steps=settle_consecutive_steps,
                    max_settle_s=max_settle_s,
                )
            )
        finally:
            close = getattr(episode_plant, "close", None)
            if callable(close):
                close()
    document_path = output / ARTIFACT
    document = build_fine_correction_episodes(
        path=document_path,
        command=command,
        episodes=episodes,
        controller_config=controller,
        control={
            "control_period_s": control_period,
            "source_path": str(controller_path),
            "source_sha256": _digest(controller_path),
            "key": "controller_manager.ros__parameters.update_rate",
            "update_rate_hz": 1.0 / control_period,
            "steps_per_period": int(round(steps_per_period)),
            "declared_by": "the sealed controller configuration",
        },
        scene_path=scene,
        scene_sha256=scene_sha256,
        dataset_config_path=dataset_path,
        dataset_config_sha256=_digest(dataset_path),
        geometry_seal_path=seal_path,
        geometry_seal_sha256=_digest(seal_path),
        production_search_config_path=production_path,
        production_search_config_sha256=_digest(production_path),
        frozen_candidate_path=frozen_path,
        frozen_candidate_sha256=_digest(frozen_path),
        weights_path=weights,
        weights_sha256=weights_sha256,
        scenario_partitions_path=partitions_path,
        scenario_partitions_sha256=_digest(partitions_path),
        split=split,
        seeds=declared_seeds,
        detector_operating_point=operating_point,
        coarse_corridor_rad=coarse,
        fine_corridor_rad=fine,
        measurement_budget=budget,
        runtime_identity_document=(
            {}
            if plant is not None
            else measurement_runtime_identity(
                device=device, detector_loaded=True, weights_sha256=weights_sha256
            )
        ),
        scene_preparation={
            "cup_placement": (
                "prepared by the dataset renderer of the head profile for this seed "
                "(MuJoCoDatasetRenderer._prepare with numpy.random.default_rng(seed)), not the seal's "
                "anchor sample: the held-out scenes place their cup where the dataset put it"
            ),
            "dataset_config_path": str(dataset_path),
            "generator_commit": str(generator_commit),
            "condition_class_by_seed": {
                str(seed): scenario for seed, scenario in zip(declared_seeds, scenarios)
            },
            "scenario_by_seed": {
                str(seed): scenario_name_for_cup_count(cup_count_for_condition_class(scenario))
                for seed, scenario in zip(declared_seeds, scenarios)
            },
            "cup_count_by_seed": {
                str(seed): cup_count_for_condition_class(scenario)
                for seed, scenario in zip(declared_seeds, scenarios)
            },
            "scene_state_sha256_by_seed": scene_state_digests,
            "held_actuators": (
                "every actuator except the neck holds the position the dataset preparation left it in, so "
                "the frames are rendered from the prepared scene rather than from one whose arm drifted "
                "toward the actuators' unset targets; each episode records the residual drift"
            ),
        },
        anchors=[request["anchor"]],
        detector_loaded=detector is not None or detector_factory is not None,
        device=device,
    )
    document["production_declaration"] = {
        "max_fine_corrections": production.get("values", {}).get("max_fine_corrections"),
        "max_fine_total_rad": production.get("values", {}).get("max_fine_total_rad"),
        "center_deadband_px": production.get("values", {}).get("center_deadband_px"),
        "vertical_bounds_px": production.get("values", {}).get("vertical_bounds_px"),
        "path": str(production_path),
        "sha256": _digest(production_path),
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    document_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "status": "SUCCEEDED" if document["refused_count"] == 0 else "MEASURED_WITH_REFUSED_EPISODES",
        "command": command,
        "output_dir": str(output),
        "document_path": str(document_path),
        "document_sha256": document["sha256"],
        "scene_path": str(scene),
        "scene_sha256": scene_sha256,
        "dataset_config_path": str(dataset_path),
        "dataset_config_sha256": _digest(dataset_path),
        "geometry_seal_path": str(seal_path),
        "geometry_seal_sha256": _digest(seal_path),
        "production_search_config_path": str(production_path),
        "production_search_config_sha256": _digest(production_path),
        "frozen_candidate_path": str(frozen_path),
        "frozen_candidate_sha256": _digest(frozen_path),
        "scenario_partitions_path": str(partitions_path),
        "scenario_partitions_sha256": _digest(partitions_path),
        "weights_path": str(weights),
        "weights_sha256": weights_sha256,
        "detector_operating_point": dict(operating_point),
        "split": split,
        "seeds": declared_seeds,
        "scenario_by_seed": {
            str(seed): scenario for seed, scenario in zip(declared_seeds, scenarios)
        },
        "episode_count": document["episode_count"],
        "succeeded_count": document["succeeded_count"],
        "refused_count": document["refused_count"],
        "records": document["records"],
        "refused_episodes": [
            {
                "episode_id": record["episode_id"],
                "failure_code": episode.get("failure_code"),
                "failure_detail": episode.get("failure_detail"),
            }
            for record, episode in zip(document["records"], episodes)
            if record["succeeded"] is False
        ],
        "coarse_corridor_rad": [float(bound) for bound in coarse],
        "fine_corridor_rad": [float(bound) for bound in fine],
        "measurement_budget": dict(budget),
        "anchor_names": [request["anchor"]],
        "simulation_timestep_s": timestep,
        "control_period_s": control_period,
        "max_settle_s": float(max_settle_s),
        "settle_consecutive_steps": int(settle_consecutive_steps),
        "max_frames": int(max_frames),
        "elapsed_s": time.time() - started,
        "runtime_identity": dict(document["runtime_identity"]),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "transport_measured": False,
        "tracking_measured": False,
        "motion_commanded": False,
        "detector_loaded": document["detector_loaded"],
    }
    (output / RECEIPT_ARTIFACT).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "document": document,
        "receipt": receipt,
        "document_path": document_path,
        "output_dir": output,
        "episodes": episodes,
    }


def scenario_name_for_cup_count(cup_count: int) -> str:
    """The dataset scenario name for a cup count, spelled as the renderer's own enum spells it."""

    from so101_demo.adapters.perception.mujoco_dataset import DatasetScenario

    return DatasetScenario.for_cup_count(int(cup_count)).value


def _cuda_available() -> bool:
    """Whether the declared CUDA device is really there; the measurement never falls back to the CPU."""

    import torch

    return bool(torch.cuda.is_available())
