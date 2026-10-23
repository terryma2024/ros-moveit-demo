"""The settle rule, the controller period and configuration, planned stops and stop classification."""

from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path

from so101_demo.act.head_search_timing_measurement.contracts import (
    _PERIOD_TOLERANCE_S,
    _SHA256,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    CAL_TIMING_STOP_UNSETTLED,
    CAL_TIMING_SWEEP_UNSETTLED,
    CAL_TIMING_TIME_BASE_UNVERIFIED,
    SETTLE_RULE,
    SIMULATION_TIME_BASE,
    _digest,
    _finite,
    _interval,
    _mapping,
    _number,
    _refuse,
    _sequence,
)


class SettleTracker:
    """The declared settle rule: consecutive quiet steps *and* the goal tolerance, at the same instant.

    A quiet velocity alone is never a settle - the neck is quiet before it starts moving, too - so the
    tolerance is part of the rule rather than a later check.
    """

    def __init__(self, *, settle_velocity_rad_s, goal_tolerance_rad, consecutive_steps) -> None:
        velocity = float(settle_velocity_rad_s)
        tolerance = float(goal_tolerance_rad)
        if not math.isfinite(velocity) or velocity <= 0.0:
            raise ValueError("the settle rule needs a positive settle_velocity_rad_s")
        if not math.isfinite(tolerance) or tolerance <= 0.0:
            raise ValueError("the settle rule needs a positive goal_tolerance_rad")
        if type(consecutive_steps) is not int or isinstance(consecutive_steps, bool):
            raise ValueError("the settle rule needs a whole number of consecutive steps")
        if consecutive_steps < 1:
            raise ValueError("the settle rule needs at least one consecutive step")
        self.settle_velocity_rad_s = velocity
        self.goal_tolerance_rad = tolerance
        self.consecutive_steps = consecutive_steps
        self.quiet_steps = 0

    def observe(self, velocity_rad_s, position_error_rad) -> bool:
        """One control step's observation: True exactly when this step completes the settle."""

        velocity = float(velocity_rad_s)
        error = float(position_error_rad)
        if not math.isfinite(velocity) or not math.isfinite(error):
            raise ValueError("the settle rule observes finite velocity and position error only")
        if abs(velocity) <= self.settle_velocity_rad_s:
            self.quiet_steps += 1
        else:
            self.quiet_steps = 0
        return self.quiet_steps >= self.consecutive_steps and abs(error) <= self.goal_tolerance_rad


def read_control_period(controller_config_path) -> float:
    """The controller period the sealed controller configuration declares, in seconds.

    The sweep has to command the neck at the period the production controller runs at, so the period is
    read from the sealed `controller_manager` rate rather than assumed.
    """

    import yaml

    path = Path(controller_config_path)
    if not path.is_file():
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"the controller configuration {path} does not exist")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        rate = document["controller_manager"]["ros__parameters"]["update_rate"]
    except (KeyError, TypeError, ValueError, yaml.YAMLError) as error:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the controller configuration {path} declares no controller_manager update_rate: {error}",
        ) from error
    if not _finite(rate) or float(rate) <= 0.0:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the controller configuration {path} declares the non-positive update_rate {rate!r}",
        )
    return 1.0 / float(rate)


def controller_config(
    *, production_search_config, geometry_seal, anchor: str, attempt_id: str, session_id: str
) -> dict:
    """The production controller's configuration for one sealed anchor, and nothing invented.

    Every number comes from the sealed geometry or the production search configuration; the two documents
    have to agree on the geometry they both describe, so a disagreement is refused rather than resolved.
    """

    production = _mapping("production search configuration", production_search_config)
    seal = _mapping("sealed geometry", geometry_seal)
    values = _mapping("production search values", production.get("values"))
    required = (
        "coarse_step_rad",
        "search_timeout_s",
        "max_age_s",
        "max_skew_s",
        "center_deadband_px",
        "vertical_bounds_px",
        "min_area_px2",
        "min_confidence",
        "max_fine_corrections",
        "max_fine_total_rad",
    )
    missing = [key for key in required if key not in values]
    if missing:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the production search configuration declares no {missing}, so the controller the sweep walks "
            f"cannot be built",
        )
    fov = _number(seal, "the sealed geometry", "horizontal_fov_rad", positive=True)
    declared_fov = _number(values, "the production search values", "horizontal_fov_rad", positive=True)
    if not math.isclose(fov, declared_fov, rel_tol=0.0, abs_tol=1e-12):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry measures a horizontal_fov_rad of {fov} but the production search "
            f"configuration declares {declared_fov}; the sweep would plan against another camera",
        )
    lock = _interval("lock_valid_neck_rad", seal.get("lock_valid_neck_rad"))
    declared_lock = _interval("values.lock_valid_neck_rad", values.get("lock_valid_neck_rad"))
    if any(
        not math.isclose(left, right, rel_tol=0.0, abs_tol=1e-12)
        for left, right in zip(lock, declared_lock)
    ):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry locks the neck to {list(lock)} but the production search configuration "
            f"declares {list(declared_lock)}",
        )
    domain = _interval(
        "required_search_domain_rad", seal.get("required_search_domain_rad")
    )
    anchors = seal.get("in_frame_matrix")
    if not isinstance(anchors, Mapping) or anchor not in anchors:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            f"the sealed geometry declares no anchor {anchor!r}, so the search start of this sweep is not "
            f"measured anywhere",
        )
    start = _number(anchors[anchor], f"the sealed anchor {anchor!r}", "neck_start_rad")
    motion = _mapping("production motion thresholds", production.get("motion"))
    camera = _mapping("production camera identity", production.get("camera"))
    frame_id = camera.get("frame_id")
    ray_origin_frame_id = camera.get("ray_origin_frame_id")
    for name, value in (("camera.frame_id", frame_id), ("camera.ray_origin_frame_id", ray_origin_frame_id)):
        if type(value) is not str or not value.strip():
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"the production search configuration declares no {name}, so the controller has no frame "
                f"identity",
            )
    return {
        "attempt_id": attempt_id,
        "session_id": session_id,
        "search_start_rad": start,
        "horizontal_fov_rad": fov,
        "coarse_step_rad": _number(values, "the production search values", "coarse_step_rad", positive=True),
        "search_timeout_s": _number(values, "the production search values", "search_timeout_s", positive=True),
        "max_age_s": _number(values, "the production search values", "max_age_s", positive=True),
        "max_skew_s": _number(values, "the production search values", "max_skew_s", positive=True),
        "settle_velocity_rad_s": _number(
            motion, "the production motion thresholds", "settle_velocity_rad_s", positive=True
        ),
        "goal_tolerance_rad": _number(
            motion, "the production motion thresholds", "goal_tolerance_rad", positive=True
        ),
        "center_deadband_px": _number(values, "the production search values", "center_deadband_px"),
        "vertical_bounds_px": [
            float(bound)
            for bound in _sequence("values.vertical_bounds_px", values.get("vertical_bounds_px"))
        ],
        "min_area_px2": _number(values, "the production search values", "min_area_px2"),
        "min_confidence": _number(values, "the production search values", "min_confidence"),
        "max_fine_corrections": values.get("max_fine_corrections"),
        "max_fine_total_rad": _number(values, "the production search values", "max_fine_total_rad"),
        "frame_id": frame_id,
        "ray_origin_frame_id": ray_origin_frame_id,
        "required_search_domain_rad": list(domain),
        "lock_valid_neck_rad": list(lock),
    }


def planned_stops(config) -> tuple[float, ...]:
    """The bounded stop points the production controller's own plan commands, in order.

    This is the same object the search walks: the sweep never invents a stop the controller would not
    command, and a configuration the controller refuses is a caller error rather than a measurement.
    """

    from so101_demo.act.search import HeadSearchController

    controller = HeadSearchController(dict(config))
    if controller.plan is None:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the controller built no bounded stop plan: the configuration carries no required search "
            "domain, so there is no stop-point sweep to measure",
        )
    return tuple(float(target) for target in controller.plan.targets_rad)


def _stamp(name: str, record: Mapping, key: str) -> float:
    value = record.get(key)
    if not _finite(value) or float(value) < 0.0:
        raise _refuse(
            CAL_TIMING_TIME_BASE_UNVERIFIED,
            f"{name} records no finite non-negative {key}, so its time base cannot be verified",
        )
    return float(value)


def verify_simulation_time_base(result) -> dict:
    """Prove every timing number is the simulation clock's, or refuse rather than record it.

    The proof is exact: a stop's settle time has to be its own step count times the sealed simulation
    timestep, its simulation interval has to be that same number, and every frame has to carry finite
    simulation stamps that do not run backwards. A wall-clock settle time, a declared time base that is
    not `simulation`, or a frame without simulation stamps is refused.
    """

    if not isinstance(result, Mapping):
        raise ValueError("the sweep result must be a mapping")
    if result.get("time_base") != SIMULATION_TIME_BASE:
        raise _refuse(
            CAL_TIMING_TIME_BASE_UNVERIFIED,
            f"the sweep declares the time base {result.get('time_base')!r}; the settle timing of this "
            f"measurement is the MuJoCo simulation clock ({SIMULATION_TIME_BASE!r}) and nothing else",
        )
    timestep = _number(result, "the sweep result", "simulation_timestep_s", positive=True)
    stops = _sequence("sweep stops", result.get("stops"))
    if not stops:
        raise _refuse(
            CAL_TIMING_SWEEP_UNSETTLED,
            "the sweep records no stop at all, so it cannot have settled anywhere",
        )
    for index, stop in enumerate(stops):
        stop = _mapping("sweep stop", stop)
        if stop.get("time_base") != SIMULATION_TIME_BASE:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"sweep stop {index} declares the time base {stop.get('time_base')!r} instead of the "
                f"simulation clock",
            )
        steps = stop.get("steps")
        if type(steps) is not int or isinstance(steps, bool) or steps < 1:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"sweep stop {index} records no positive whole number of simulated steps",
            )
        settle_s = _stamp(f"sweep stop {index}", stop, "settle_s")
        expected = steps * timestep
        if not math.isclose(settle_s, expected, rel_tol=0.0, abs_tol=_PERIOD_TOLERANCE_S):
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"sweep stop {index} records a settle time of {settle_s} s for {steps} steps of "
                f"{timestep} s, which is {expected} s: the settle time is not the simulation clock's, so "
                f"it is not recorded as timing",
            )
        start = _stamp(f"sweep stop {index}", stop, "sim_start_s")
        end = _stamp(f"sweep stop {index}", stop, "sim_end_s")
        if not math.isclose(end - start, settle_s, rel_tol=0.0, abs_tol=_PERIOD_TOLERANCE_S):
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"sweep stop {index} spans {end - start} s of simulation time but records a settle time "
                f"of {settle_s} s",
            )
    frames = _sequence("sweep frames", result.get("frames"))
    previous_sim = None
    for index, frame in enumerate(frames):
        frame = _mapping("sweep frame", frame)
        frame_sim = _stamp(f"sweep frame {index}", frame, "frame_sim_s")
        received_sim = _stamp(f"sweep frame {index}", frame, "received_sim_s")
        decision_sim = _stamp(f"sweep frame {index}", frame, "decision_sim_s")
        if decision_sim < frame_sim or received_sim < frame_sim or decision_sim < received_sim:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"sweep frame {index} puts its decision before its frame or its receipt in simulation "
                f"time ({frame_sim} -> {received_sim} -> {decision_sim})",
            )
        if previous_sim is not None and frame_sim < previous_sim:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"sweep frame {index} is stamped {frame_sim} s of simulation time after frame {index - 1} "
                f"at {previous_sim} s",
            )
        previous_sim = frame_sim
        frame_wall = _stamp(f"sweep frame {index}", frame, "frame_monotonic_s")
        received_wall = _stamp(f"sweep frame {index}", frame, "received_monotonic_s")
        decision_wall = _stamp(f"sweep frame {index}", frame, "decision_monotonic_s")
        if not frame_wall <= received_wall <= decision_wall:
            raise _refuse(
                CAL_TIMING_TIME_BASE_UNVERIFIED,
                f"sweep frame {index} puts its decision before its receipt in the monotonic wall clock "
                f"({frame_wall} -> {received_wall} -> {decision_wall})",
            )
    return {
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": timestep,
        "stop_count": len(stops),
        "frame_count": len(frames),
    }


def classify_stop(stop, *, settle_consecutive_steps, max_settle_s) -> dict:
    """One stop's verdict: stable, reached without settling, or never settled at all.

    A stop the neck never reached inside its settle budget refuses the whole sweep
    (`CAL_TIMING_SWEEP_UNSETTLED`); a stop it reached while still moving refuses it too
    (`CAL_TIMING_STOP_UNSETTLED`), because a stop that is not held cannot be observed.
    """

    record = _mapping("sweep stop", stop)
    label = f"stop {record.get('index')!r} of anchor {record.get('anchor')!r}"
    settled = record.get("settled") is True
    reached = record.get("reached") is True
    if settled and reached:
        return {
            **record,
            "stable": True,
            "settle_rule": SETTLE_RULE,
            "settle_consecutive_steps": settle_consecutive_steps,
            "max_settle_s": max_settle_s,
        }
    if reached:
        raise _refuse(
            CAL_TIMING_STOP_UNSETTLED,
            f"{label} was reached within goal_tolerance_rad but the neck never held a velocity at or "
            f"below settle_velocity_rad_s for {settle_consecutive_steps} consecutive control steps inside "
            f"the {max_settle_s} s settle budget: a stop that is not settled cannot be observed",
        )
    raise _refuse(
        CAL_TIMING_SWEEP_UNSETTLED,
        f"{label} was never reached within goal_tolerance_rad inside the {max_settle_s} s settle budget "
        f"(the last recorded velocity was {record.get('final_velocity_rad_s')!r} rad/s at a position "
        f"error of {record.get('final_position_error_rad')!r} rad), so the sweep cannot settle",
    )


def _reference(name: str, path, digest: str | None = None) -> dict:
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        digest = _digest(path)
    return {"path": str(path), "sha256": digest}


def _sealed_scene_sha256(geometry_seal) -> str:
    seal = _mapping("sealed geometry", geometry_seal)
    digests = seal.get("source_digests")
    digest = digests.get("scene_sha256") if isinstance(digests, Mapping) else None
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the sealed geometry records no source_digests.scene_sha256, so nothing pins the scene this "
            "sweep would step the neck in",
        )
    return digest
