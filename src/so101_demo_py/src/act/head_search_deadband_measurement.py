"""The closed-loop deadband lock trials: phase 6's ``deadband_candidates`` measurement document.

Phase 6 chooses ``center_deadband_px`` as *the smallest declared candidate at or above the measured
centre jitter in pixels that locks for three consecutive frames without a left-right reversal*
(``head_search_search_params.compute_center_deadband_px``, design section 7.1). The lock and the
reversal are properties of the **closed loop** - a target, a moving neck, a rendered frame, a detection
and a correction fed back into the controller - so they cannot be read off any open-loop episode. This
module runs that loop once per declared candidate in the sealed MuJoCo scene and writes the records
phase 6 consumes, or refuses rather than inventing one.

What is measured, and how:

* :func:`run_lock_trial` is the closed loop itself, and it is pure: the plant (the neck the controller
  commands) and the detector are both injected. One iteration is one control decision - the production
  :class:`so101_demo.act.search.HeadSearchController` emits a neck target, the plant steps the sealed
  scene until the declared settle rule holds, the head camera renders, the detector finds the cup, and
  the controller consumes that frame and its feedback to emit the next target. The controller is the
  production one, not a copy: its own bounded plan, its own freshness and skew gates, its own
  three-frame lock rule and its own fine-correction budget all apply.
* ``longest_locked_run_frames`` is the longest run of **consecutive frames** in which the detected cup
  is inside the candidate deadband of the principal point *and* inside the declared vertical bounds,
  with the same detection track as the frame before it. A frame with no detection, a frame outside the
  vertical bounds, and a change of track each break the run - exactly the three ways
  ``HeadSearchController`` resets its own ``lock_count``.
* ``direction_reversals`` is how many times the controller sent the neck **back the other way**: the
  number of sign changes in the sequence of the trial's commanded target moves. A single correction
  that settles, however large, is not a reversal; two corrections in opposite directions are one.
* every commanded target - the coarse plan's and every fine correction's - must lie inside the declared
  **motion corridor**, the intersection of the seal's ``required_search_domain_rad`` and its
  ``lock_valid_neck_rad``. Nothing is clamped: a target outside the corridor refuses the trial with
  :data:`CAL_DEADBAND_OUT_OF_CORRIDOR`, because clamping would command a motion the controller never
  asked for and measure that instead.

What this module refuses instead of fabricating:

* the detector produced no cup at all over the whole trial, or failed outright: no lock run exists to
  count, so the trial refuses with :data:`CAL_DEADBAND_CUP_LOST`. A *measured* absence - the cup is in
  frame but outside the candidate deadband - is not a refusal: that is the honest record that says the
  candidate is too small, and phase 6 reads it.
* a commanded stop was reached but never held (``CAL_TIMING_STOP_UNSETTLED``), never reached
  (``CAL_TIMING_SWEEP_UNSETTLED``), or the loop ran out of frames before any verdict
  (``CAL_TIMING_SWEEP_UNSETTLED``) - the timing module's own settle rule and codes, reused.
* the settle times are not the simulation clock's (``CAL_TIMING_TIME_BASE_UNVERIFIED``), proved by the
  timing module's own :func:`verify_simulation_time_base` over this trial's stops and frames.

The only part that touches MuJoCo, the detector or a GPU is :class:`MujocoClosedLoopPlant` and the
default detector factory, and both import their dependencies inside the call. The detector is the
production head detector (``HeadRgbDetector`` over ``YoloSegDetector``: the same class filter, aspect
gate and spatial track association the running search applies) at the selected candidate's declared head
operating point, and this measurement never falls back to the CPU.
"""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
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
    SETTLE_RULE,
    SIMULATION_TIME_BASE,
    SettleTracker,
    _declared_weights,
    _digest,
    _finite,
    classify_stop,
    controller_config,
    read_control_period,
    verify_simulation_time_base,
)
from so101_demo.act.head_search_timing_measurement import (
    runtime_identity as measurement_runtime_identity,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

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


# --- the declared inputs ---------------------------------------------------------------------------


def _interval(name: str, value) -> tuple[float, float]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence) or len(value) != 2:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"{name} must be two finite bounds")
    low, high = (float(bound) for bound in value)
    if not math.isfinite(low) or not math.isfinite(high) or low > high:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"{name} must be finite and ordered")
    return low, high


def motion_corridor_rad(*, geometry_seal) -> tuple[float, float]:
    """The interval every commanded neck target has to stay inside, or the refusal that stops the trial.

    The corridor is the intersection of the seal's two declarations: ``required_search_domain_rad`` is the
    interval the bounded sweep must cover, and ``lock_valid_neck_rad`` is the interval in which a lock is
    valid at all. A seal that declares only one of them, or two that do not overlap, cannot bound the
    motion, so this measurement refuses instead of choosing one of them.
    """

    if not isinstance(geometry_seal, Mapping):
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, "the sealed geometry is not a document")
    declared = []
    for key in ("required_search_domain_rad", "lock_valid_neck_rad"):
        if key not in geometry_seal:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"the sealed geometry declares no {key}, so no motion corridor bounds this measurement",
            )
        declared.append(_interval(key, geometry_seal[key]))
    required, safe = declared
    low, high = max(required[0], safe[0]), min(required[1], safe[1])
    if low >= high:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed required search domain {list(required)} and its lock-valid neck interval "
            f"{list(safe)} do not overlap, so there is no neck angle this measurement may command",
        )
    return low, high


def anchor_cup_start_m(*, geometry_seal, anchor: str) -> list[float]:
    """Where the seal says the anchor's cup starts; a seal that does not say refuses the trial.

    The seal records one ``workspace_matrix.key_samples`` entry per anchor carrying the anchor's
    ``point_m``, which is the cup placement the anchor's ``neck_start_rad`` and ``centre_angle_rad`` were
    measured at. Reading the placement from anything else would measure a different scene.
    """

    matrix = geometry_seal.get("workspace_matrix") if isinstance(geometry_seal, Mapping) else None
    samples = matrix.get("key_samples") if isinstance(matrix, Mapping) else None
    if isinstance(samples, Sequence) and not isinstance(samples, (str, bytes)):
        for sample in samples:
            if not isinstance(sample, Mapping) or sample.get("anchor") != anchor:
                continue
            point = sample.get("point_m")
            if isinstance(point, Sequence) and not isinstance(point, (str, bytes)) and len(point) == 3:
                return [float(value) for value in point]
    raise _refuse(
        CAL_TIMING_EVIDENCE_MISSING,
        f"the sealed geometry records no workspace_matrix.key_samples point_m for the anchor {anchor!r}, "
        f"so the cup this anchor's trial would look for is not placed anywhere",
    )


def declared_candidates(values) -> list[float]:
    """The deadband candidates the caller declared, in the order they were declared."""

    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise ValueError("the deadband candidates must be a sequence of pixel values")
    declared: list[float] = []
    for value in values:
        if not _finite(value) or float(value) <= 0.0:
            raise ValueError(f"every deadband candidate must be a positive finite pixel value: {value!r}")
        candidate = float(value)
        if candidate in declared:
            raise ValueError(f"the deadband candidate {candidate} is declared twice")
        declared.append(candidate)
    if not declared:
        raise ValueError("at least one deadband candidate has to be declared")
    return declared


def detector_operating_point(frozen_candidate) -> dict:
    """The selected candidate's declared head operating point, as the detector is configured with it.

    The frozen document carries one operating point per domain (the recorder's own convention); the head
    search is the head domain, so the head entry is the one this measurement configures the detector with.
    A frozen document that declares no head point refuses rather than defaulting to the task one.
    """

    points = frozen_candidate.get("operating_points") if isinstance(frozen_candidate, Mapping) else None
    head = points.get("head") if isinstance(points, Mapping) else None
    if not isinstance(head, Mapping):
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the frozen candidate declares no operating_points.head, so the detector this measurement "
            "would run has no declared operating point for the head domain",
        )
    tracker = head.get("tracker")
    iou = tracker.get("iou") if isinstance(tracker, Mapping) else None
    confidence = head.get("min_confidence")
    if not _finite(confidence) or not 0.0 <= float(confidence) <= 1.0:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the frozen candidate's head operating point declares the confidence {confidence!r}",
        )
    if not _finite(iou) or not 0.0 < float(iou) <= 1.0:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the frozen candidate's head operating point declares the tracker iou {iou!r}",
        )
    return {"min_confidence": float(confidence), "iou": float(iou)}


def _re_raised(call, *args, **kwargs):
    """Run a reused timing-module check, re-raising its refusal as this measurement's own class.

    The settle rule, the stop classification, the time-base proof and the sealed-detector guard are that
    module's, so the refusals they raise are that module's type. They are this measurement's refusals too,
    and a caller that records `deadband_candidates` reads one class and one code vocabulary, so they are
    re-raised here with the same code rather than leaking another module's exception type.
    """

    try:
        return call(*args, **kwargs)
    except CalibrationInputsRefused as error:
        raise _refuse(error.code, error.detail) from error


# --- the lock run and the reversals -----------------------------------------------------------------


def lock_run(frames, *, deadband_px: float, vertical_bounds_px) -> int:
    """The longest run of consecutive lockable frames, over the recorded frames of one trial."""

    if (
        isinstance(vertical_bounds_px, (str, bytes))
        or not isinstance(vertical_bounds_px, Sequence)
        or len(vertical_bounds_px) != 2
    ):
        raise ValueError("the vertical bounds must be two pixel rows")
    low, high = (float(bound) for bound in vertical_bounds_px)
    deadband = float(deadband_px)
    best = run = 0
    previous_track = None
    for frame in frames:
        if not isinstance(frame, Mapping):
            raise ValueError("every recorded frame must be a mapping")
        centre = frame.get("centre_px")
        track = frame.get("track_id")
        if centre is None:
            run, previous_track = 0, None
            continue
        if previous_track is not None and track != previous_track:
            run = 0
        previous_track = track
        principal = frame.get("principal_x_px")
        if not _finite(principal):
            raise ValueError("every recorded frame records the principal point it was measured against")
        if abs(float(centre[0]) - float(principal)) <= deadband and low <= float(centre[1]) <= high:
            run += 1
            best = max(best, run)
        else:
            run = 0
    return best


def direction_reversals(corrections) -> int:
    """How many times a commanded move went the other way than the move before it."""

    reversals = 0
    previous = 0.0
    for value in corrections:
        move = float(value)
        if move == 0.0:
            continue
        if previous != 0.0 and (move > 0.0) != (previous > 0.0):
            reversals += 1
        previous = move
    return reversals


def candidate_record(*, deadband_px: float, trials) -> dict:
    """One candidate's record for phase 6: the worst case over the anchors it was trialled on.

    `longest_locked_run_frames` is the smallest run any anchor managed and `direction_reversals` the
    largest count any anchor produced, so a candidate is only as stable as its least stable anchor.
    """

    if isinstance(trials, (str, bytes)) or not isinstance(trials, Sequence) or not trials:
        raise ValueError("a candidate record needs at least one trial")
    runs, reversals = [], []
    for trial in trials:
        if not isinstance(trial, Mapping):
            raise ValueError("every trial of a candidate record must be a mapping")
        run, count = trial.get("longest_locked_run_frames"), trial.get("direction_reversals")
        if type(run) is not int or isinstance(run, bool) or run < 0:
            raise ValueError("every trial records its longest locked run in whole frames")
        if type(count) is not int or isinstance(count, bool) or count < 0:
            raise ValueError("every trial records its direction reversal count")
        runs.append(run)
        reversals.append(count)
    record = {
        "center_deadband_px": float(deadband_px),
        "longest_locked_run_frames": min(runs),
        "direction_reversals": max(reversals),
    }
    return {key: record[key] for key in RECORD_KEYS}


# --- the closed loop ---------------------------------------------------------------------------------


def _corridor_check(*, angle_rad: float, corridor_rad, what: str) -> None:
    low, high = corridor_rad
    if not low - _BOUND_TOLERANCE_RAD <= float(angle_rad) <= high + _BOUND_TOLERANCE_RAD:
        raise _refuse(
            CAL_DEADBAND_OUT_OF_CORRIDOR,
            f"the {what} {float(angle_rad)!r} rad is outside the declared motion corridor "
            f"{[low, high]} rad, and this measurement never commands a neck angle the seal does not bound",
        )


def _detections(call, image, stamp_ns) -> list:
    """The frame's detections in the controller's own shape, or the refusal that stops the trial."""

    try:
        found = call(image, stamp_ns)
    except Exception as error:  # the detector's own failure is not a deadband measurement
        raise _refuse(
            CAL_DEADBAND_CUP_LOST,
            f"the detector failed on a frame of this trial ({type(error).__name__}: {error}), so no lock "
            f"run can be counted from it",
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


def _frame_summary(*, index, anchor, frame, decision, detections) -> dict:
    """What one trial frame contributed, with its detections summarised in JSON-safe numbers."""

    boxes = []
    for detection in detections:
        box = list(detection["xyxy"])
        boxes.append(
            {
                "xyxy": box,
                "confidence": detection["confidence"],
                "class_id": detection["class_id"],
                "track_id": detection["track_id"],
                "centre_px": [(box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0],
            }
        )
    previous = frame.get("previous_frame_sim_s")
    return {
        "frame_index": index,
        "anchor": anchor,
        "frame_interval_sim_s": None if previous is None else float(frame["frame_sim_s"]) - float(previous),
        "frame_sim_s": float(frame["frame_sim_s"]),
        "received_sim_s": float(frame["received_sim_s"]),
        "decision_sim_s": float(frame["decision_sim_s"]),
        "frame_monotonic_s": float(frame["frame_monotonic_s"]),
        "received_monotonic_s": float(frame["received_monotonic_s"]),
        "decision_monotonic_s": float(frame["decision_monotonic_s"]),
        "neck_yaw_rad": float(frame["neck_yaw_rad"]),
        "neck_velocity_rad_s": float(frame["neck_velocity_rad_s"]),
        "principal_x_px": float(frame["principal_x_px"]),
        "principal_y_px": float(frame["principal_y_px"]),
        "detection_count": len(boxes),
        "detections": boxes,
        "centre_px": (
            None if not boxes else [float(value) for value in boxes[0]["centre_px"]]
        ),
        "track_id": None if not boxes else boxes[0]["track_id"],
        "decision_status": decision.get("status") if isinstance(decision, Mapping) else None,
        "time_base": SIMULATION_TIME_BASE,
    }


def run_lock_trial(
    *,
    controller_config: Mapping,
    deadband_px: float,
    plant,
    detector,
    corridor_rad,
    anchor: str = "trial",
    max_frames: int = DEFAULT_MAX_FRAMES,
    settle_consecutive_steps: int = SETTLE_CONSECUTIVE_STEPS,
    max_settle_s: float = DEFAULT_MAX_SETTLE_S,
    clock=time.monotonic,
) -> dict:
    """One candidate's closed loop, from the anchor to its terminal verdict.

    The production controller is driven frame by frame: it emits a target, the plant steps the sealed neck
    to it and settles, the head camera renders, the detector finds the cup, and the controller consumes
    that frame and its feedback to emit the next target. Every commanded target is checked against the
    motion corridor before it is commanded, the settle rule and the simulation time base are the timing
    module's own, and the trial's lock run and reversals are reduced from the recorded frames.
    """

    from so101_demo.act.search import HeadSearchController

    if type(max_frames) is not int or isinstance(max_frames, bool) or max_frames < 1:
        raise ValueError("a lock trial needs a positive whole frame budget")
    timestep = getattr(plant, "simulation_timestep_s", None)
    if not _finite(timestep) or float(timestep) <= 0.0:
        raise ValueError("the plant must declare the simulation timestep its stops were stepped at")
    low, high = corridor_rad
    config = {**dict(controller_config), "center_deadband_px": float(deadband_px)}
    controller = HeadSearchController(config)
    vertical_bounds = [float(bound) for bound in config["vertical_bounds_px"]]
    started = time.time()

    _corridor_check(
        angle_rad=float(config["search_start_rad"]),
        corridor_rad=(low, high),
        what="declared search start",
    )
    reset = getattr(detector, "reset", None)
    if callable(reset):
        reset()

    target = float(config["search_start_rad"])
    stops: list[dict] = []
    frames: list[dict] = []
    corrections: list[float] = []
    detection_frames = 0
    terminal = None
    verdict = None

    def command(target_rad: float) -> None:
        """Command a target, step the plant to the frame boundary, and record the stop it produced."""

        _corridor_check(angle_rad=float(target_rad), corridor_rad=(low, high), what="commanded neck target")
        stop = dict(plant.settle_to(float(target_rad)))
        stop.update(anchor=anchor, index=len(stops), kind="plan", time_base=SIMULATION_TIME_BASE)
        stops.append(
            _re_raised(
                classify_stop,
                stop,
                settle_consecutive_steps=settle_consecutive_steps,
                max_settle_s=max_settle_s,
            )
        )
        _corridor_check(angle_rad=float(plant.yaw_rad), corridor_rad=(low, high), what="settled neck angle")

    command(target)
    while len(frames) < max_frames:
        frame_wall = clock()
        image = plant.render_frame()
        received_wall = clock()
        stamp_ns = int(plant.frame_stamp_ns)
        geometry = plant.optical_geometry()
        detections = _detections(detector, image, stamp_ns)
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
        decision = controller.tick(frame, feedback, decision_wall)
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
        frames.append(record)
        if "found" in decision:
            terminal, verdict = dict(decision), decision["status"]
            break
        if decision.get("stop"):
            raise _refuse(
                CAL_TIMING_SWEEP_UNSETTLED,
                f"the closed loop of the candidate {float(deadband_px)} px stopped on the controller "
                f"status {decision.get('status')!r} before it reached a verdict, so the trial measured no "
                f"lock run",
            )
        previous, target = target, float(decision["neck_target_rad"])
        if record["detection_count"] and target != previous:
            corrections.append(target - previous)
        command(target)

    if terminal is None:
        raise _refuse(
            CAL_TIMING_SWEEP_UNSETTLED,
            f"the closed loop of the candidate {float(deadband_px)} px spent its whole {max_frames}-frame "
            f"budget without a verdict, so it never settled into a measurable lock run",
        )
    if verdict == "SEARCH_UNSAFE":
        raise _refuse(
            CAL_DEADBAND_OUT_OF_CORRIDOR,
            f"the controller refused to observe the neck as safe ({verdict}), so no lock run of the "
            f"candidate {float(deadband_px)} px can be measured",
        )
    if verdict == "TARGET_AMBIGUOUS":
        raise _refuse(
            CAL_DEADBAND_CUP_LOST,
            f"the detector resolved more than one cup for the candidate {float(deadband_px)} px, so the "
            f"trial has no single cup whose lock run it could count",
        )
    if verdict == "SEARCH_TIMEOUT":
        raise _refuse(
            CAL_TIMING_SWEEP_UNSETTLED,
            f"the closed loop of the candidate {float(deadband_px)} px reached the controller's search "
            f"timeout before it reached a verdict",
        )
    if detection_frames == 0:
        raise _refuse(
            CAL_DEADBAND_CUP_LOST,
            f"the detector found no cup in any of the {len(frames)} frames of the candidate "
            f"{float(deadband_px)} px trial, so the trial records no lock run rather than a zero it never "
            f"measured",
        )
    result = {
        "deadband_px": float(deadband_px),
        "anchor": anchor,
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(timestep),
        "stops": stops,
        "frames": frames,
        "terminal_status": verdict,
        "found": bool(terminal.get("found")),
        "neck_yaw_rad": terminal.get("neck_yaw_rad"),
        "detection_frames": detection_frames,
        "correction_count": len(corrections),
        "corrections_rad": corrections,
        "direction_reversals": direction_reversals(corrections),
        "longest_locked_run_frames": lock_run(
            frames, deadband_px=float(deadband_px), vertical_bounds_px=vertical_bounds
        ),
        "settle_rule": SETTLE_RULE,
        "lock_rule": LOCK_RULE,
        "reversal_definition": REVERSAL_DEFINITION,
        "corridor_rule": CORRIDOR_RULE,
        "motion_corridor_rad": [low, high],
        "wall_time_s": time.time() - started,
        "sim_time_s": float(plant.time_s),
        "goal_tolerance_rad": float(config["goal_tolerance_rad"]),
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


def _anchor_records(anchors) -> list[dict]:
    """The declared anchors, normalised to the records the document carries."""

    if isinstance(anchors, (str, bytes)) or not isinstance(anchors, Sequence) or not anchors:
        raise ValueError("the document needs at least one declared anchor")
    records = []
    for anchor in anchors:
        if isinstance(anchor, Mapping):
            name = anchor.get("anchor")
            if type(name) is not str or not name:
                raise ValueError("every declared anchor names itself")
            records.append(dict(anchor))
        elif type(anchor) is str and anchor:
            records.append({"anchor": anchor})
        else:
            raise ValueError("every declared anchor is a name or an anchor record")
    return records


def build_deadband_candidates(
    *,
    path,
    command,
    trials,
    candidates_px,
    control: Mapping,
    controller_config: Mapping,
    scene_path,
    scene_sha256: str,
    geometry_seal_path,
    geometry_seal_sha256: str,
    production_search_config_path,
    production_search_config_sha256: str,
    corridor_rad,
    anchors,
    frozen_candidate_path=None,
    frozen_candidate_sha256: str | None = None,
    weights_path=None,
    weights_sha256: str | None = None,
    detector_operating_point: Mapping | None = None,
    detector_loaded: bool = True,
    device: str = "cuda",
    runtime_identity_document: Mapping | None = None,
) -> dict:
    """The `deadband_candidates` document: one record per declared candidate, in the order declared.

    `records` carries exactly the three keys phase 6 reads, reduced from the per-anchor trials, and the
    trials themselves are kept beside them with every frame, stop, correction and terminal verdict, so a
    reviewer can recompute each record rather than trust it. The document never carries a value that was
    not measured: a candidate without a trial, and a trial of a candidate that was not declared, are both
    caller errors.
    """

    candidates = declared_candidates(candidates_px)
    if isinstance(trials, (str, bytes)) or not isinstance(trials, Sequence) or not trials:
        raise ValueError("the document needs at least one measured trial")
    records = _anchor_records(anchors)
    by_candidate: dict[float, list[Mapping]] = {candidate: [] for candidate in candidates}
    for trial in trials:
        if not isinstance(trial, Mapping):
            raise ValueError("every measured trial must be a mapping")
        measured = float(trial.get("deadband_px"))
        if measured not in by_candidate:
            raise ValueError(
                f"a trial measured the deadband candidate {measured} which the run never declared"
            )
        by_candidate[measured].append(trial)
    missing = [candidate for candidate in candidates if not by_candidate[candidate]]
    if missing:
        raise ValueError(f"the declared deadband candidates {missing} were never trialled")
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "path": None if path is None else str(path),
        "command": command,
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(trials[0]["simulation_timestep_s"]),
        "control_period_s": float(control["control_period_s"]),
        "control_period_source": dict(control),
        "frame_rate_hz": FRAME_RATE_HZ,
        "frame_period_s": FRAME_PERIOD_S,
        "frame_cadence": FRAME_CADENCE,
        "lock_frames_required": LOCK_FRAMES,
        "lock_rule": LOCK_RULE,
        "reversal_definition": REVERSAL_DEFINITION,
        "corridor_rule": CORRIDOR_RULE,
        "motion_corridor_rad": [float(bound) for bound in corridor_rad],
        "candidates_px": candidates,
        "records": [
            candidate_record(deadband_px=candidate, trials=by_candidate[candidate])
            for candidate in candidates
        ],
        "records_semantics": (
            "one record per declared candidate, worst case over the anchors it was trialled on: the "
            "smallest longest_locked_run_frames and the largest direction_reversals any anchor produced"
        ),
        "trials": [dict(trial) for trial in trials],
        "anchors": records,
        "controller_thresholds": {
            "min_confidence": float(controller_config["min_confidence"]),
            "min_area_px2": float(controller_config["min_area_px2"]),
            "vertical_bounds_px": [float(bound) for bound in controller_config["vertical_bounds_px"]],
            "max_fine_corrections": controller_config["max_fine_corrections"],
            "max_fine_total_rad": float(controller_config["max_fine_total_rad"]),
            "settle_velocity_rad_s": float(controller_config["settle_velocity_rad_s"]),
            "goal_tolerance_rad": float(controller_config["goal_tolerance_rad"]),
        },
        "detector_operating_point": dict(detector_operating_point or {}),
        "scene_path": str(scene_path),
        "scene_sha256": scene_sha256,
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
            "detector's own spatial track association over this trial's frames and not from a running "
            "multi-object tracker across a topic"
        ),
        "transport_measured": False,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "measured_here": True,
        "motion_commanded": False,
        "runtime_identity": dict(runtime_identity_document or trials[0].get("runtime_identity") or {}),
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


# --- the MuJoCo plant and the production detector ----------------------------------------------------


class MujocoClosedLoopPlant:
    """The sealed scene's neck, commanded and settled, and its head camera, rendered.

    This is the only place in this module that imports MuJoCo, and it does so inside the call. The plant
    places the anchor's cup where the seal says it starts, commands the scene's own ``neck_yaw_joint``
    position actuator at the sealed controller period, applies the timing module's declared settle rule,
    and holds the neck at each frame boundary for one declared frame period of simulation time. It
    commands the simulated neck only: no ROS node starts and no hardware is addressed.
    """

    def __init__(self, request: Mapping) -> None:
        import mujoco
        import numpy as np

        self._mujoco = mujoco
        self.max_settle_s = float(request["max_settle_s"])
        self.frame_period_s = float(request["frame_period_s"])
        self.control_period_s = float(request["control_period_s"])
        self._flip = np.diag([1.0, -1.0, -1.0])
        scene = Path(request["scene_path"])
        self._model = mujoco.MjModel.from_xml_path(str(scene))
        self.simulation_timestep_s = float(self._model.opt.timestep)
        self._joint_name = str(request.get("neck_joint", "neck_yaw_joint"))
        camera_name = request["camera_name"]
        self._camera = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
        if self._camera < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no camera {camera_name!r}",
            )
        if not math.isclose(
            math.radians(float(self._model.cam_fovy[self._camera])),
            float(request["fovy_rad"]),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene's {camera_name} camera has a different field of view than the sealed "
                f"geometry declares, so these frames would be measured against another camera",
            )
        self._data = mujoco.MjData(self._model)
        self._neck = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, self._joint_name)
        if self._neck < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY, f"the sealed scene {scene} has no {self._joint_name}"
            )
        self._qpos_address = int(self._model.jnt_qposadr[self._neck])
        self._dof_address = int(self._model.jnt_dofadr[self._neck])
        self._actuator = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_ACTUATOR, self._joint_name
        )
        if self._actuator < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no {self._joint_name} actuator, so no target can be "
                f"commanded",
            )
        self._cup_body = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_BODY, request.get("cup_body", "plastic_cup")
        )
        if self._cup_body < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no {request.get('cup_body', 'plastic_cup')} body, so where "
                f"the anchor's cup sits cannot be read back",
            )
        self._place_cup(request["cup_joint"], request["cup_start_m"])
        self._data.qpos[self._qpos_address] = float(request["start_rad"])
        mujoco.mj_forward(self._model, self._data)
        self._renderer = None
        self._steps_per_control = max(1, int(round(self.control_period_s / self.simulation_timestep_s)))
        self._max_steps = int(math.ceil(self.max_settle_s / self.simulation_timestep_s))
        self._next_frame_s = float(self._data.time)
        self._settle_velocity_rad_s = float(request["settle_velocity_rad_s"])
        self._goal_tolerance_rad = float(request["goal_tolerance_rad"])
        self._settle_consecutive_steps = int(request["settle_consecutive_steps"])
        self._image_width = int(request["image_width"])
        self._image_height = int(request["image_height"])
        self._focal_px = (self._image_height / 2.0) / math.tan(
            math.radians(float(self._model.cam_fovy[self._camera])) / 2.0
        )

    def _place_cup(self, joint_name: str, position) -> None:
        joint = self._mujoco.mj_name2id(self._model, self._mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if joint < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene has no {joint_name} joint, so the anchor's cup is not in the scene",
            )
        address = int(self._model.jnt_qposadr[joint])
        self._data.qpos[address : address + 3] = [float(value) for value in position]
        self._data.qpos[address + 3 : address + 7] = (1.0, 0.0, 0.0, 0.0)

    @property
    def time_s(self) -> float:
        return float(self._data.time)

    @property
    def yaw_rad(self) -> float:
        return float(self._data.qpos[self._qpos_address])

    @property
    def velocity_rad_s(self) -> float:
        return float(self._data.qvel[self._dof_address])

    @property
    def frame_stamp_ns(self) -> int:
        """The frame's source stamp: this frame boundary in simulation nanoseconds, never a wall clock."""

        return int(round(self._data.time * 1e9))

    def settle_to(self, target_rad: float) -> dict:
        """Command the neck, step until the declared settle rule holds, then hold to the frame boundary."""

        target = float(target_rad)
        self._data.ctrl[self._actuator] = target
        start_sim, start_rad = float(self._data.time), self.yaw_rad
        tracker = SettleTracker(
            settle_velocity_rad_s=self._settle_velocity_rad_s,
            goal_tolerance_rad=self._goal_tolerance_rad,
            consecutive_steps=self._settle_consecutive_steps,
        )
        steps = 0
        settled = reached = False
        settle_instant_s = None
        while steps < self._max_steps:
            for _ in range(self._steps_per_control):
                self._mujoco.mj_step(self._model, self._data)
                steps += 1
            error = target - self.yaw_rad
            if abs(error) <= self._goal_tolerance_rad:
                reached = True
            if tracker.observe(self.velocity_rad_s, error):
                settled = True
                settle_instant_s = self.time_s - start_sim
                break
        self._next_frame_s = max(
            self._next_frame_s + self.frame_period_s, start_sim + self.frame_period_s
        )
        while self._data.time < self._next_frame_s - 1e-12 and steps < 4 * self._max_steps:
            for _ in range(self._steps_per_control):
                self._mujoco.mj_step(self._model, self._data)
                steps += 1
        return {
            "target_rad": target,
            "start_rad": start_rad,
            "sim_start_s": start_sim,
            "sim_end_s": float(self._data.time),
            "steps": steps,
            "settle_s": float(self._data.time) - start_sim,
            "settle_instant_s": settle_instant_s,
            "settled": settled,
            "reached": reached,
            "final_velocity_rad_s": self.velocity_rad_s,
            "final_position_error_rad": target - self.yaw_rad,
            "quiet_steps": tracker.quiet_steps,
        }

    def render_frame(self):
        """One frame of the head camera, opening the GL context on the first frame that needs one."""

        if self._renderer is None:
            self._renderer = self._mujoco.Renderer(
                self._model, height=self._image_height, width=self._image_width
            )
        self._renderer.update_scene(self._data, camera=self._camera)
        return self._renderer.render()

    def optical_geometry(self) -> dict:
        """The head camera's intrinsics and its optical frame in the base frame, from the live model."""

        rotation = self._data.cam_xmat[self._camera].reshape(3, 3) @ self._flip
        return {
            "k": (
                self._focal_px,
                0.0,
                self._image_width / 2.0,
                0.0,
                self._focal_px,
                self._image_height / 2.0,
                0.0,
                0.0,
                1.0,
            ),
            "distortion": (0.0, 0.0, 0.0, 0.0, 0.0),
            "rotation_optical_to_base": tuple(
                tuple(float(value) for value in row) for row in rotation
            ),
        }

    @property
    def cup_position_m(self) -> list[float]:
        """Where the anchor's cup really is, read back out of the stepped model rather than assumed."""

        return [float(value) for value in self._data.xpos[self._cup_body]]

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


class ProductionHeadDetector:
    """The production head detector as one callable frame source, with its own track association."""

    def __init__(self, detector, *, session_id: str, attempt_id: str, frame_id: str) -> None:
        self.detector = detector
        self.session_id = session_id
        self.attempt_id = attempt_id
        self.frame_id = frame_id

    def reset(self) -> None:
        self.detector.reset()

    def __call__(self, image, stamp_ns: int):
        """One frame's detections: the production detector takes the image and its identity, not a frame."""

        return self.detector.detect(
            image,
            session_id=self.session_id,
            attempt_id=self.attempt_id,
            source_stamp_ns=int(stamp_ns),
            source_frame_id=self.frame_id,
        )


def build_production_head_detector(
    *, weights_path, operating_point, production, frame_id, device, attempt_id, session_id
):
    """The production head detector over the selected model, at its declared head operating point.

    This is the same adapter the running search uses - ``HeadRgbDetector`` over ``YoloSegDetector`` - so
    the class filter, the aspect gate, the spatial track association and the never-CPU-fallback device
    policy are the production ones rather than a harness copy.
    """

    from so101_demo.adapters.act.detector import HeadRgbDetector
    from so101_demo.adapters.perception.yolo_seg import YoloSegDetector

    values = production.get("values") if isinstance(production.get("values"), Mapping) else {}
    model_id = str(production.get("runtime_id") or DETECTOR_MODEL_ID)
    digest = _digest(weights_path)
    detector = YoloSegDetector(
        weights_path=Path(weights_path),
        expected_sha256=digest,
        requested_device=device,
        allow_cpu_fallback=False,
        model_id=model_id,
        imgsz=640,
    )
    head = HeadRgbDetector(
        detector,
        model_id=model_id,
        weights_sha256=digest,
        tracking_iou=float(operating_point["iou"]),
        min_bbox_aspect=float(values["min_bbox_aspect"]),
    )
    return ProductionHeadDetector(
        head, session_id=session_id, attempt_id=attempt_id, frame_id=frame_id
    )


# --- the producer ------------------------------------------------------------------------------------


def _anchor_requests(*, seal, production, anchors, attempt_id, session_id) -> list[dict]:
    declared = seal.get("in_frame_matrix")
    if not isinstance(declared, Mapping) or not declared:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the sealed geometry declares no in_frame_matrix anchors, so no lock trial has a search start",
        )
    names = list(declared) if anchors is None else list(anchors)
    if not names:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, "no anchor was declared for the lock trials")
    requests = []
    for name in names:
        if type(name) is not str or name not in declared:
            raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"the sealed geometry declares no anchor {name!r}")
        config = _re_raised(
            controller_config,
            production_search_config=production,
            geometry_seal=seal,
            anchor=name,
            attempt_id=attempt_id,
            session_id=session_id,
        )
        requests.append(
            {
                "anchor": name,
                "search_start_rad": config["search_start_rad"],
                "cup_start_m": anchor_cup_start_m(geometry_seal=seal, anchor=name),
                "controller_config": config,
            }
        )
    return requests


def _plant_request(*, request, scene, seal, camera, control_period_s, max_settle_s,
                   settle_consecutive_steps) -> dict:
    config = request["controller_config"]
    return {
        "scene_path": str(scene),
        "camera_name": seal.get("camera_name"),
        "image_width": seal.get("image_width"),
        "image_height": seal.get("image_height"),
        "fovy_rad": (camera or {}).get("fovy_rad"),
        "control_period_s": control_period_s,
        "frame_period_s": FRAME_PERIOD_S,
        "max_settle_s": max_settle_s,
        "settle_consecutive_steps": settle_consecutive_steps,
        "settle_velocity_rad_s": config["settle_velocity_rad_s"],
        "goal_tolerance_rad": config["goal_tolerance_rad"],
        "start_rad": config["search_start_rad"],
        "cup_start_m": request["cup_start_m"],
        "cup_joint": "cup_free_joint",
        "cup_body": "plastic_cup",
    }


def write_head_search_deadband_measurement(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    frozen_candidate_path,
    weights_path,
    output_dir,
    candidates,
    anchors=None,
    device="cuda",
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    max_frames=DEFAULT_MAX_FRAMES,
    attempt_id=MEASUREMENT_ATTEMPT_ID,
    session_id=MEASUREMENT_SESSION_ID,
    command=None,
    plant=None,
    detector_factory=None,
) -> dict:
    """Run one closed-loop lock trial per declared candidate and write the document phase 6 reads.

    Every declared input is read and cross-checked before anything is stepped: the scene has to be the one
    the sealed geometry pins, the control period has to be a whole number of the scene's own timesteps, the
    detector has to be the weight the sealed configuration declares, the frozen candidate has to declare
    its head operating point, and each anchor's search start has to lie inside the motion corridor. The
    trials then run one candidate at a time, and the document and its receipt are the only files this
    producer creates.
    """

    started = time.time()
    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    frozen_path = Path(frozen_candidate_path)
    for path in (scene, seal_path, production_path, controller_path, frozen_path):
        if not path.is_file():
            raise FileNotFoundError(f"the deadband measurement needs {path}")
    weights = Path(weights_path)
    if not weights.is_file():
        raise FileNotFoundError(f"the deadband measurement needs {weights}")
    declared = declared_candidates(candidates)
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
            f"the sealed geometry pins the scene {sealed_scene}, but the scene these lock trials would "
            f"step the neck in digests to {scene_sha256}",
        )
    control_period = _re_raised(read_control_period, controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s steps, so the trials could not command the neck at the production period",
        )
    weights_sha256 = _re_raised(
        _declared_weights, production, {"weights_path": weights_path}
    )
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
            f"configuration seals {weights_sha256}: the trials would not run the selected model",
        )
    corridor = motion_corridor_rad(geometry_seal=seal)
    requests = _anchor_requests(
        seal=seal,
        production=production,
        anchors=anchors,
        attempt_id=attempt_id,
        session_id=session_id,
    )
    for request in requests:
        _corridor_check(
            angle_rad=request["search_start_rad"],
            corridor_rad=corridor,
            what=f"declared search start of the anchor {request['anchor']!r}",
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
    trials: list[dict] = []
    for request in requests:
        for candidate in declared:
            trial_plant = (
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
                trials.append(
                    run_lock_trial(
                        controller_config=request["controller_config"],
                        deadband_px=candidate,
                        plant=trial_plant,
                        detector=(
                            detector
                            if detector_factory is None
                            else detector_factory(trial_plant, request)
                        ),
                        corridor_rad=corridor,
                        anchor=request["anchor"],
                        max_frames=max_frames,
                        settle_consecutive_steps=settle_consecutive_steps,
                        max_settle_s=max_settle_s,
                    )
                )
            finally:
                close = getattr(trial_plant, "close", None)
                if callable(close):
                    close()
    document_path = output / ARTIFACT
    document = build_deadband_candidates(
        path=document_path,
        command=command,
        trials=trials,
        candidates_px=declared,
        control={
            "control_period_s": control_period,
            "source_path": str(controller_path),
            "source_sha256": _digest(controller_path),
            "key": "controller_manager.ros__parameters.update_rate",
            "update_rate_hz": 1.0 / control_period,
            "steps_per_period": int(round(steps_per_period)),
            "declared_by": "the sealed controller configuration",
        },
        controller_config=requests[0]["controller_config"],
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
        corridor_rad=corridor,
        anchors=[
            {
                "anchor": request["anchor"],
                "search_start_rad": request["search_start_rad"],
                "cup_start_m": list(request["cup_start_m"]),
            }
            for request in requests
        ],
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
    document_path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "status": "SUCCEEDED",
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
        "candidate_count": len(declared),
        "candidates_px": declared,
        "anchor_names": [request["anchor"] for request in requests],
        "trial_count": len(trials),
        "records": document["records"],
        "motion_corridor_rad": [float(bound) for bound in corridor],
        "lock_frames_required": LOCK_FRAMES,
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
    }
    (output / RECEIPT_ARTIFACT).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "document": document,
        "receipt": receipt,
        "document_path": document_path,
        "output_dir": output,
        "trials": trials,
    }


def _cuda_available() -> bool:
    """Whether the declared CUDA device is really there; the measurement never falls back to the CPU."""

    import torch

    return bool(torch.cuda.is_available())
