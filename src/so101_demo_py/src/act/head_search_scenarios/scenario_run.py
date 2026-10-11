"""Run one scenario and classify its outcome."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import time

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_deadband_measurement.contracts import (
    CalibrationDeadbandMeasurementRefused,
)
from so101_demo.act.head_search_deadband_measurement.lock_trial import (
    _corridor_check,
    _detections,
    _frame_summary,
)
from so101_demo.act.head_search_fine_correction_episodes.episode import (
    _budget_binding,
    required_domain_excursion_rad,
    verify_correction_consistency,
)
from so101_demo.act.head_search_fine_correction_episodes.scene import (
    scenario_name_for_cup_count,
)
from so101_demo.act.head_search_scenarios.contracts import (
    CAL_SCENARIO_BUDGET_EXHAUSTED,
    CAL_SCENARIO_COVERAGE_INCOMPLETE,
    CAL_SCENARIO_CUP_NOT_FOUND,
    CAL_SCENARIO_DETECTOR_FAILED,
    CAL_SCENARIO_FRAME_CADENCE,
    CAL_SCENARIO_INTERRUPTION_UNPROVEN,
    CAL_SCENARIO_NO_VERDICT,
    CAL_SCENARIO_NOT_CENTERED,
    CAL_SCENARIO_OUT_OF_CORRIDOR,
    CAL_SCENARIO_STOP_UNPROVEN,
    CAL_SCENARIO_TARGET_AMBIGUOUS,
    CAL_SCENARIO_UNEXPECTED_LOCK,
    DEFAULT_INTERRUPTION_FRAME,
    DEFAULT_MAX_FRAMES,
    FAILED,
    INTERRUPTION_STALE_MARGIN_S,
    NOT_FOUND_STATUSES,
    NOT_FOUND_WITHIN_BOUND_STATUSES,
    PASSED,
    QUALIFICATION_SPLIT,
    REFUSED,
    STOP_PROOF_SAMPLES,
    _re_raised,
    _refuse,
)
from so101_demo.act.head_search_scenarios.plan import (
    STOP_PROOF_WINDOW,
    check_frame_cadence,
    expected_terminals,
    requires_interruption,
)
from so101_demo.act.head_search_scenarios.stop_proof import (
    _coverage_of,
    _scenario_declaration,
    settle_proof,
    stop_proof,
)
from so101_demo.act.head_search_search_params import LOCK_FRAMES
from so101_demo.act.head_search_timing_measurement.contracts import (
    DEFAULT_MAX_SETTLE_S,
    FRAME_PERIOD_S,
    FRAME_RATE_HZ,
    SETTLE_CONSECUTIVE_STEPS,
    SIMULATION_TIME_BASE,
    _finite,
)
from so101_demo.act.head_search_timing_measurement.control import (
    classify_stop,
    verify_simulation_time_base,
)


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
