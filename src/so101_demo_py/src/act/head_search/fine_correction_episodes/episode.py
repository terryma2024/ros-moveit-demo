"""Split seeds, corridor checks, one fine-correction episode and its record."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
import time

from so101_demo.act.head_search.deadband_measurement.contracts import (
    CalibrationDeadbandMeasurementRefused,
)
from so101_demo.act.head_search.deadband_measurement.lock_trial import (
    _corridor_check,
    _detections,
    _frame_summary,
    declared_warmup,
    motion_corridor_rad,
    perform_warmup_frame,
)
from so101_demo.act.head_search.fine_correction_episodes.contracts import (
    _CORRECTION_TOLERANCE_RAD,
    _SHA256,
    BUDGET_DEFINITION,
    CAL_FINE_EPISODE_BUDGET_EXHAUSTED,
    CAL_FINE_EPISODE_CORRECTION_MISMATCH,
    CAL_FINE_EPISODE_CUP_NOT_FOUND,
    CAL_FINE_EPISODE_DETECTOR_FAILED,
    CAL_FINE_EPISODE_NO_CORRECTION_NEEDED,
    CAL_FINE_EPISODE_NO_SUCCESS,
    CAL_FINE_EPISODE_NO_VERDICT,
    CAL_FINE_EPISODE_NOT_CENTERED,
    CAL_FINE_EPISODE_OUT_OF_CORRIDOR,
    CAL_FINE_EPISODE_SPLIT_LEAK,
    CAL_FINE_EPISODE_TARGET_AMBIGUOUS,
    CORRECTION_DEFINITION,
    CORRIDOR_DEFINITION,
    DEFAULT_MAX_FRAMES,
    KIND,
    PHASE,
    RECORD_KEYS,
    SCENE_DEFINITION,
    SCHEMA_VERSION,
    SUCCESS_DEFINITION,
    _partitions_document,
    _re_raised,
    _refuse,
)
from so101_demo.act.head_search.search_params import LOCK_FRAMES
from so101_demo.act.head_search.timing_measurement.contracts import (
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    DEFAULT_MAX_SETTLE_S,
    DIGEST_CONVENTION,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
    SETTLE_CONSECUTIVE_STEPS,
    SIMULATION_TIME_BASE,
    _digest,
    _finite,
)
from so101_demo.act.head_search.timing_measurement.control import (
    classify_stop,
    verify_simulation_time_base,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256


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


def coarse_corridor_rad(*, geometry_seal) -> tuple[float, float]:
    """The coarse corridor: the required search domain intersected with the lock-valid neck interval."""

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
    episode from reaching a verdict at all is a refusal. One frame is rendered and detected before the
    measured ones and declared as the episode's warm-up (`WARMUP_POLICY`): it is excluded from every frame,
    age and reduction this episode records.
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
    # the one-off cost of the process's first detection-bearing predict belongs to the start-up, not to the
    # episode: pay it on a frame that is declared and excluded, and reset the detector so the measured
    # frames begin the attempt state they would have begun without it
    try:
        warmup = perform_warmup_frame(plant=plant, detector=detector, clock=clock)
    except CalibrationDeadbandMeasurementRefused as error:
        raise _refuse(
            CAL_FINE_EPISODE_DETECTOR_FAILED,
            f"the detector failed on the warm-up frame of the episode {episode_id!r} ({error.detail}), so "
            f"this episode is not a measurement and no correction count is recorded for it",
        ) from error
    if callable(reset):
        reset()
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
        "warmup": warmup,
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
    the document alone. `warmup` declares the frame each episode rendered and detected before its measured
    ones and `warmup_samples_excluded` records that it is in none of the frames, ages or reductions above;
    the block is the first episode's own warm-up, the one that paid the process's one-off start-up cost,
    and every episode's own block sits in `episodes`.
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
        "warmup": dict(episodes[0].get("warmup") or declared_warmup(performed=False)),
        "warmup_samples_excluded": True,
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
