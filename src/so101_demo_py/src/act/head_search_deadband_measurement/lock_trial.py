"""The corridor, the lock trial and the deadband candidate records."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import time

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_deadband_measurement.contracts import (
    _BOUND_TOLERANCE_RAD,
    _SHA256,
    CAL_DEADBAND_CUP_LOST,
    CAL_DEADBAND_OUT_OF_CORRIDOR,
    CORRIDOR_RULE,
    DEFAULT_MAX_FRAMES,
    FRAME_CADENCE,
    KIND,
    LOCK_RULE,
    PHASE,
    RECORD_KEYS,
    REVERSAL_DEFINITION,
    SCHEMA_VERSION,
    WARMUP_POLICY,
    _interval,
    _refuse,
)
from so101_demo.act.head_search_search_params import LOCK_FRAMES
from so101_demo.act.head_search_timing_measurement.contracts import (
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_SWEEP_UNSETTLED,
    DEFAULT_MAX_SETTLE_S,
    DIGEST_CONVENTION,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
    SETTLE_CONSECUTIVE_STEPS,
    SETTLE_RULE,
    SIMULATION_TIME_BASE,
    _digest,
    _finite,
)
from so101_demo.act.head_search_timing_measurement.control import (
    classify_stop,
    verify_simulation_time_base,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


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


def declared_warmup(*, performed: bool, detections=None, wall_s=None) -> dict:
    """The declared warm-up block: the same four keys the timing measurement records, and nothing else.

    `performed` says whether a warm-up frame was really rendered and detected, `detections` how many
    detections that frame carried (so a warm-up that resolved nothing cannot be mistaken for one that paid
    the one-off cost), `wall_s` how long it took, and `declared_because` why it is excluded rather than
    hidden in the distribution.
    """

    return {
        "performed": bool(performed),
        "detections": None if detections is None else int(detections),
        "wall_s": None if wall_s is None else float(wall_s),
        "declared_because": WARMUP_POLICY,
    }


def perform_warmup_frame(*, plant, detector, clock=time.monotonic) -> dict:
    """Render and detect one frame before the measured frames, and declare it as the warm-up.

    The frame is rendered at the same plant state as the flight's first measured frame, so the detection it
    pays the one-off cost for is the detection that frame would have produced. It is not appended to the
    flight's frames, not ticked to the controller and not counted in any reduction of them; the flight
    resets the detector after it, which is what makes the exclusion exact rather than approximate.
    """

    started = clock()
    image = plant.render_frame()
    detections = _detections(detector, image, int(plant.frame_stamp_ns))
    return declared_warmup(
        performed=True, detections=len(detections), wall_s=clock() - started
    )


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
    module's own, and the trial's lock run and reversals are reduced from the recorded frames. One frame is
    rendered and detected before the measured ones and declared as the trial's warm-up (`WARMUP_POLICY`):
    it is excluded from every frame, age and reduction this trial records.
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
    # the one-off cost of the process's first detection-bearing predict belongs to the start-up, not to the
    # trial: pay it on a frame that is declared and excluded, and reset the detector so the measured frames
    # begin the attempt state they would have begun without it
    warmup = perform_warmup_frame(plant=plant, detector=detector, clock=clock)
    if callable(reset):
        reset()
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
        "warmup": warmup,
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
    caller errors. `warmup` declares the frame each trial rendered and detected before its measured ones
    and `warmup_samples_excluded` records that it is in none of the frames, ages or reductions above; the
    block is the first trial's own warm-up, the one that paid the process's one-off start-up cost, and
    every trial's own block sits in `trials`.
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
        "warmup": dict(trials[0].get("warmup") or declared_warmup(performed=False)),
        "warmup_samples_excluded": True,
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
