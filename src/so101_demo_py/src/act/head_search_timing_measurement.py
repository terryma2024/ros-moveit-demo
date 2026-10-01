"""The runtime sweep timing measurement: phases 6 and 7's first two measurement documents.

Phase 6's ``search_timeout_s`` is
``max_stable_stop_points * (p99_settle_s + p99_frame_s) + max_fine_corrections * control_period_s``
(design section 7.1), so it needs the settle time and the per-frame time of the bounded sweep the search
actually performs; phase 7's ``max_age_s`` is the p99.9 of the measured end-to-end frame age plus 10 ms.
Neither number exists as a declaration anywhere - they are properties of the running pipeline - so this
module measures them once, against the sealed MuJoCo scene's neck joint, and writes the two documents the
run declares under ``--search-timing`` and ``--frame-age-measurements``.

What is measured, and how:

* :class:`SettleTracker` is the declared settle rule: the neck is settled at a stop when its joint
  velocity is at or below the production ``settle_velocity_rad_s`` **for ``settle_consecutive_steps``
  consecutive control steps** and the joint is inside the production ``goal_tolerance_rad`` of the stop.
  A single quiet sample is never a settle, and a stop the neck reaches while still moving is not settled
  either.
* :class:`MujocoNeckSweepRunner` is the only part of this module that touches MuJoCo, the detector or a
  GPU, and it imports them inside the call. It walks the bounded stop points of
  ``so101_demo.act.search.HeadSearchController`` - the same plan the production search walks - inside the
  sealed scene, commanding the scene's own ``neck_yaw_joint`` position actuator at the sealed controller
  period, and produces one frame every declared frame period of **simulation** time. Every stop records
  its step count and its settle time in simulation seconds; every frame records the simulation stamps of
  its capture and of its decision and the monotonic-wall stamps of its capture, its receipt and its
  decision.
* the sweep's time base must be the MuJoCo simulation clock itself: :func:`verify_simulation_time_base`
  refuses a settle time that is not its own step count times the sealed timestep, a declared time base
  that is not ``simulation``, and a frame without simulation stamps, with
  ``CAL_TIMING_TIME_BASE_UNVERIFIED``. Timing is never inferred from a clock the sweep does not own.
* the frame age is ``decision_monotonic_s - received_monotonic_s`` in the monotonic wall-clock base the
  production controller's freshness gate uses (``HeadSearchController`` compares ``now - received_wall_s``
  against ``max_age_s``), and the p99 frame time phase 6 reads is ``decision_monotonic_s -
  frame_monotonic_s``: the whole per-frame pipeline cost, render and inference included. The simulation
  stamps of the same samples are recorded next to them so the two bases can be checked against each other
  (``sim_age_s`` is the same interval in simulation time, the ``real_time_factor`` block records the
  mapping, and the document says which base each number is in).

What this harness cannot measure yet, and will not invent:

* **no declared detector, no frame ages.** Without weights the frames cannot be timed, so
  ``p99_frame_s`` is recorded as ``null``, the frame-age and frame-contract artefacts are not written at
  all, and the timing document says ``frame_timing.measured: false``. Phase 6 then refuses that document
  with its own ``CAL_TIMEOUT_UNBOUNDED``, which is the honest outcome: a timeout cannot be bounded without
  a frame time.
* **there is no ROS transport in this harness.** The frame is rendered by the same process that decides,
  so the receipt happens immediately after the capture and the image never crosses a topic. The measured
  age is therefore the perception cost, not the perception cost plus transport; the documents say so
  (``transport_measured: false``), and the running-topic freshness measurement remains a separate
  capability.
* **the simulation is paused while a frame is produced.** The neck does not advance in wall-clock time
  while the renderer and the detector work, so ``sim_age_s`` is zero by construction and the wall-clock age
  is the whole perception cost. The recorded ``real_time_factor`` says how fast the harness actually stepped
  the sealed scene, and it is a measurement rather than an assumption: in the one real run recorded by
  ledger HS-300 it was above one, because the sealed physics steps faster than wall clock while a frame
  costs a few milliseconds. What is measured is the cost of the perception pipeline, not the residual lag
  of a pipeline coupled to a real-time clock.

This module is written so that everything except :class:`MujocoNeckSweepRunner` is a pure, independently
testable decision layer: the sweep executor is injected into
:func:`write_head_search_timing_measurement`, so the tests exercise the settle rule, the time-base proof,
every refusal and both documents without a simulator, a detector or a GPU.
"""

from __future__ import annotations

import json
import math
import re
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_mujoco_measurements import read_mujoco_timestep
from so101_demo.act.head_search_timing_params import (
    FRAME_CONTRACT_HZ,
    FRAME_CONTRACT_ITEM,
    nearest_rank_percentile,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

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


# --- the settle rule ------------------------------------------------------------------------------


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


# --- the declared inputs --------------------------------------------------------------------------


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


# --- the time base --------------------------------------------------------------------------------


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


# --- the documents --------------------------------------------------------------------------------


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


def frame_contract_document(*, path, command=None, startup_readback=None) -> dict:
    """The declared 10 Hz frame contract every cap of phase 7 is expressed in, as its own artefact.

    Phase 7 cites its frame contract by path and sha256, so the declaration the frame ages are timed
    against has to exist as a document rather than as a nested copy. The rate is the design's own and the
    module refuses any other, so this declaration can only ever confirm it; the startup readback that
    proves the running pipeline uses it belongs to the run and is recorded as not taken here.
    """

    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": FRAME_CONTRACT_KIND,
        "phase": FRAME_CONTRACT_PHASE,
        "path": None if path is None else str(path),
        "command": command,
        "item": FRAME_CONTRACT_ITEM,
        "frame_rate_hz": FRAME_RATE_HZ,
        "frame_period_s": FRAME_PERIOD_S,
        "declared_by": FRAME_CONTRACT_DECLARED_BY,
        "production_owner": "so101_demo.act.head_search_timing_params.FRAME_CONTRACT_HZ",
        "measured_here": False,
        "startup_readback": (
            {
                "verified": False,
                "detail": (
                    "the startup readback that proves the running pipeline uses the 10 Hz contract belongs "
                    "to the run (phase 8); this declaration is the rate the frames of this measurement "
                    "were produced at"
                ),
            }
            if startup_readback is None
            else dict(startup_readback)
        ),
        "ros_nodes_started": False,
        "motion_commanded": False,
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def build_search_timing(
    *,
    path,
    command,
    request: Mapping,
    result: Mapping,
    stops: Sequence[Mapping],
    frames: Sequence[Mapping],
    control: Mapping,
    scene_path,
    scene_sha256: str,
    geometry_seal_path,
    geometry_seal_sha256: str,
    production_search_config_path,
    production_search_config_sha256: str,
    weights_path=None,
    weights_sha256: str | None = None,
    runtime_identity: Mapping | None = None,
) -> dict:
    """The `search_timing` document: what phase 6 reads, with the sweep that measured it.

    `stable_stop_count` is how many of the controller's own bounded stops settled stably in the runtime
    sweep; the percentiles are over those stops' measured settle times and the measured per-frame pipeline
    times. Without a detector there are no frame times, so `p99_frame_s` is `None` and
    `frame_timing.measured` is false - the document never fills the gap with a number that was not
    measured.
    """

    plan_stops = [stop for stop in stops if stop.get("kind") == "plan"]
    if not plan_stops:
        raise _refuse(
            CAL_TIMING_SWEEP_UNSETTLED,
            "the sweep settled no bounded stop point of the controller's plan, so no search timeout can "
            "be bounded from it",
        )
    settles = [float(stop["settle_s"]) for stop in plan_stops]
    frame_times = [float(frame["frame_time_s"]) for frame in frames]
    p99_settle = nearest_rank_percentile(settles, PERCENTILE_QUANTILE)
    p99_frame = (
        nearest_rank_percentile(frame_times, PERCENTILE_QUANTILE) if frame_times else None
    )
    detector = result.get("detector") if isinstance(result.get("detector"), Mapping) else {}
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": SEARCH_TIMING_KIND,
        "phase": SEARCH_TIMING_PHASE,
        "path": None if path is None else str(path),
        "command": command,
        "time_base": SIMULATION_TIME_BASE,
        "simulation_timestep_s": float(result["simulation_timestep_s"]),
        "control_period_s": float(control["control_period_s"]),
        "control_period_source": dict(control),
        "settle_rule": SETTLE_RULE,
        "settle_velocity_rad_s": float(request["settle_velocity_rad_s"]),
        "goal_tolerance_rad": float(request["goal_tolerance_rad"]),
        "settle_consecutive_steps": int(request["settle_consecutive_steps"]),
        "max_settle_s": float(request["max_settle_s"]),
        "percentile_quantile": PERCENTILE_QUANTILE,
        "percentile_convention": PERCENTILE_CONVENTION,
        "stops_planned": len(plan_stops),
        "stable_stop_count": len(plan_stops),
        "p99_settle_s": p99_settle,
        "p99_frame_s": p99_frame,
        "settle_s": {
            "sample_count": len(settles),
            "min": min(settles),
            "max": max(settles),
            "plan_stops_only": True,
            "anchor_positioning_stops": sum(1 for stop in stops if stop.get("kind") == "anchor"),
        },
        "frame_timing": {
            "measured": bool(frame_times),
            "sample_count": len(frame_times),
            "time_base": AGE_TIME_BASE,
            "frame_time_definition": FRAME_TIME_DEFINITION,
            "p99_frame_time_s": p99_frame,
            "max_frame_time_s": max(frame_times) if frame_times else None,
            "warmup": dict(result.get("warmup") or {"performed": False}),
            "not_measured_because": (
                None
                if frame_times
                else "no detector was declared, so no frame of this sweep could be timed; a frame time is "
                "never inferred from the settle timing"
            ),
        },
        "stops": list(stops),
        "anchors": [
            {
                "anchor": anchor["anchor"],
                "search_start_rad": anchor["search_start_rad"],
                "targets_rad": list(anchor["targets_rad"]),
            }
            for anchor in request["anchors"]
        ],
        "sweep_sim_time_s": _optional_number(result, "sim_time_s"),
        "sweep_wall_time_s": _optional_number(result, "wall_time_s"),
        "scene_path": str(scene_path),
        "scene_sha256": scene_sha256,
        "geometry_seal": _reference("the sealed geometry", geometry_seal_path, geometry_seal_sha256),
        "production_search_config": _reference(
            "the production search configuration",
            production_search_config_path,
            production_search_config_sha256,
        ),
        "weights": (
            None
            if weights_path is None
            else _reference("the detector weights", weights_path, weights_sha256)
        ),
        "detector_loaded": bool(detector.get("loaded")),
        "cuda_used": bool(detector.get("loaded")) and str(detector.get("device", "")).startswith("cuda"),
        "transport_measured": False,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "measured_here": True,
        "motion_commanded": False,
        "runtime_identity": dict(runtime_identity or result.get("runtime_identity") or {}),
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def build_frame_age_measurements(
    *,
    path,
    command,
    frame_contract: Mapping,
    samples: Sequence[Mapping],
    result: Mapping,
    scene_sha256: str,
    weights_sha256: str | None,
    runtime_identity: Mapping | None = None,
) -> dict:
    """The `frame_age_measurements` document: phase 7's per-frame ages and the declared frame contract.

    Every sample carries the two monotonic stamps phase 7 subtracts, the simulation stamps that prove the
    sweep's own time base, and the derived age, frame time and simulation-time age. The frame contract is
    cited by path and sha256, so phase 7's `compute_max_age_s` can consume the two documents as they are.
    """

    if not samples:
        raise ValueError("the frame-age document needs at least one measured frame")
    ages = [float(sample["age_s"]) for sample in samples]
    frame_times = [float(sample["frame_time_s"]) for sample in samples]
    sim_time = _optional_number(result, "sim_time_s")
    wall_time = _optional_number(result, "wall_time_s")
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": FRAME_AGE_KIND,
        "phase": FRAME_AGE_PHASE,
        "path": None if path is None else str(path),
        "command": command,
        "time_base": AGE_TIME_BASE,
        "age_definition": AGE_DEFINITION,
        "simulation_time_base": SIMULATION_TIME_BASE,
        "simulation_time_base_verified": True,
        "frame_contract": dict(frame_contract),
        "frame_rate_hz": float(frame_contract["frame_rate_hz"]),
        "frame_period_s": float(frame_contract["frame_period_s"]),
        "percentile_quantile": AGE_PERCENTILE_QUANTILE,
        "percentile_convention": PERCENTILE_CONVENTION,
        "samples": list(samples),
        "frame_age_s": {
            "sample_count": len(ages),
            "min": min(ages),
            "max": max(ages),
            "p99_9": nearest_rank_percentile(ages, AGE_PERCENTILE_QUANTILE),
        },
        "frame_time_s": {
            "sample_count": len(frame_times),
            "min": min(frame_times),
            "max": max(frame_times),
            "p99": nearest_rank_percentile(frame_times, PERCENTILE_QUANTILE),
        },
        "clock_mapping": {
            "simulation_timestep_s": float(result["simulation_timestep_s"]),
            "frames_with_simulation_stamps": sum(
                1 for sample in samples if _finite(sample.get("frame_sim_s"))
            ),
            "real_time_factor": (
                None
                if not sim_time or not wall_time
                else sim_time / wall_time
            ),
        },
        "warmup": dict(result.get("warmup") or {"performed": False}),
        "warmup_samples_excluded": True,
        "transport_measured": False,
        "simulation_paused_while_perceiving": True,
        "scene_sha256": scene_sha256,
        "weights_sha256": weights_sha256,
        "detector_loaded": True,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "measured_here": True,
        "motion_commanded": False,
        "runtime_identity": dict(runtime_identity or result.get("runtime_identity") or {}),
        "digest_convention": DIGEST_CONVENTION,
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def _frame_samples(frames: Sequence[Mapping]) -> list[dict]:
    """The per-frame records, with the intervals this module derives from their raw stamps."""

    samples = []
    for index, frame in enumerate(frames):
        record = dict(frame)
        frame_wall = float(record["frame_monotonic_s"])
        received_wall = float(record["received_monotonic_s"])
        decision_wall = float(record["decision_monotonic_s"])
        frame_sim = float(record["frame_sim_s"])
        received_sim = float(record["received_sim_s"])
        decision_sim = float(record["decision_sim_s"])
        record["age_s"] = decision_wall - received_wall
        record["frame_time_s"] = decision_wall - frame_wall
        record["sim_age_s"] = decision_sim - received_sim
        record["sim_frame_time_s"] = decision_sim - frame_sim
        record["age_time_base"] = AGE_TIME_BASE
        record["frame_sim_time_base"] = SIMULATION_TIME_BASE
        samples.append(record)
    return samples


# --- the MuJoCo sweep -----------------------------------------------------------------------------


class MujocoNeckSweepRunner:
    """Walk the controller's bounded stops in the sealed scene, timing every stop and every frame.

    This is the only place that imports MuJoCo, the detector or a GPU, and it does so inside the call. The
    sweep steps the sealed model at its own timestep, commands the scene's `neck_yaw_joint` position
    actuator at the sealed controller period, produces one frame per declared frame period of simulation
    time, and applies the declared settle rule to the joint's own velocity and position error. It commands
    the simulated neck only: no ROS node starts, no hardware is addressed.
    """

    def __call__(self, request: Mapping) -> dict:
        return self.run(request)

    def run(self, request: Mapping) -> dict:  # noqa: C901 - one linear measurement loop
        import mujoco
        import numpy as np

        started = time.monotonic()
        scene = Path(request["scene_path"])
        model = mujoco.MjModel.from_xml_path(str(scene))
        timestep = float(model.opt.timestep)
        if not math.isclose(
            timestep, float(request["simulation_timestep_s"]), rel_tol=0.0, abs_tol=_PERIOD_TOLERANCE_S
        ):
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene steps {timestep} s but its declaration was read as "
                f"{request['simulation_timestep_s']} s",
            )
        data = mujoco.MjData(model)
        neck = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "neck_yaw_joint")
        if neck < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no neck_yaw_joint, so no bounded stop can be walked",
            )
        qpos_address = int(model.jnt_qposadr[neck])
        dof_address = int(model.jnt_dofadr[neck])
        actuator = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, "neck_yaw_joint"
        )
        if actuator < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no neck_yaw_joint actuator, so no stop can be commanded",
            )
        camera = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_CAMERA, request["camera_name"]
        )
        if camera < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no camera {request['camera_name']!r}",
            )
        mujoco.mj_forward(model, data)

        weights_path = request.get("weights_path")
        detector = None
        renderer = None
        warmup = {"performed": False, "wall_s": None, "detections": None, "declared_because": WARMUP_POLICY}
        if weights_path is not None:
            from ultralytics import YOLO

            detector = YOLO(str(weights_path))
            renderer = mujoco.Renderer(
                model, height=int(request["image_height"]), width=int(request["image_width"])
            )
            warmup_started = time.monotonic()
            renderer.update_scene(data, camera=camera)
            prediction = detector.predict(
                np.asarray(renderer.render()),
                conf=float(request["min_confidence"]),
                iou=float(request["tracking_iou"]),
                device=request.get("device"),
                verbose=False,
            )
            boxes = getattr(prediction[0], "boxes", None)
            warmup = {
                "performed": True,
                "wall_s": time.monotonic() - warmup_started,
                "detections": 0 if boxes is None else len(boxes.conf),
                "declared_because": WARMUP_POLICY,
            }

        period = float(request["control_period_s"])
        steps_per_control = int(round(period / timestep))
        frame_period = 1.0 / float(request["frame_rate_hz"])
        max_steps = int(math.ceil(float(request["max_settle_s"]) / timestep))
        stops: list[dict] = []
        frames: list[dict] = []
        next_frame_sim = frame_period

        try:
            for anchor in request["anchors"]:
                index = 0
                for kind, target in [
                    ("anchor", float(anchor["search_start_rad"])),
                    *[("plan", float(goal)) for goal in anchor["targets_rad"]],
                ]:
                    current = float(data.qpos[qpos_address])
                    if kind == "anchor" and abs(current - target) <= float(request["goal_tolerance_rad"]):
                        continue
                    data.ctrl[actuator] = target
                    tracker = SettleTracker(
                        settle_velocity_rad_s=float(request["settle_velocity_rad_s"]),
                        goal_tolerance_rad=float(request["goal_tolerance_rad"]),
                        consecutive_steps=int(request["settle_consecutive_steps"]),
                    )
                    start_sim = float(data.time)
                    start_rad = current
                    steps = 0
                    settled = False
                    reached = False
                    while steps < max_steps:
                        for _control in range(steps_per_control):
                            mujoco.mj_step(model, data)
                            steps += 1
                        error = target - float(data.qpos[qpos_address])
                        velocity = float(data.qvel[dof_address])
                        if abs(error) <= float(request["goal_tolerance_rad"]):
                            reached = True
                        if (
                            detector is not None
                            and float(data.time) >= next_frame_sim - _PERIOD_TOLERANCE_S
                        ):
                            next_frame_sim += frame_period
                            frames.append(
                                self._frame(
                                    data,
                                    renderer,
                                    detector,
                                    camera,
                                    request,
                                    np,
                                    index=len(frames),
                                    anchor=anchor["anchor"],
                                    stop_index=index if kind == "plan" else None,
                                )
                            )
                        if tracker.observe(velocity, error):
                            settled = True
                            break
                    stops.append(
                        {
                            "anchor": anchor["anchor"],
                            "index": index if kind == "plan" else None,
                            "kind": kind,
                            "target_rad": target,
                            "start_rad": start_rad,
                            "sim_start_s": start_sim,
                            "sim_end_s": float(data.time),
                            "steps": steps,
                            "settle_s": float(data.time) - start_sim,
                            "settled": settled,
                            "reached": reached,
                            "final_velocity_rad_s": float(data.qvel[dof_address]),
                            "final_position_error_rad": target - float(data.qpos[qpos_address]),
                            "quiet_steps": tracker.quiet_steps,
                            "time_base": SIMULATION_TIME_BASE,
                        }
                    )
                    if kind == "plan":
                        index += 1
        finally:
            if renderer is not None:
                renderer.close()
        return {
            "time_base": SIMULATION_TIME_BASE,
            "simulation_timestep_s": timestep,
            "control_period_s": period,
            "stops": stops,
            "frames": frames,
            "sim_time_s": float(data.time),
            "wall_time_s": time.monotonic() - started,
            "detector": {
                "loaded": detector is not None,
                "device": request.get("device") if detector is not None else None,
                "weights_path": None if weights_path is None else str(weights_path),
                "weights_sha256": request.get("weights_sha256"),
            },
            "warmup": warmup,
            "runtime_identity": runtime_identity(
                device=request.get("device"), detector_loaded=detector is not None,
                weights_sha256=request.get("weights_sha256"),
            ),
        }

    @staticmethod
    def _frame(data, renderer, detector, camera, request, np, *, index, anchor, stop_index) -> dict:
        """One frame: capture it, decide on it, and stamp both ends in both time bases."""

        frame_sim = float(data.time)
        frame_wall = time.monotonic()
        renderer.update_scene(data, camera=camera)
        image = np.asarray(renderer.render())
        received_wall = time.monotonic()
        prediction = detector.predict(
            image,
            conf=float(request["min_confidence"]),
            iou=float(request["tracking_iou"]),
            device=request["device"],
            verbose=False,
        )
        decision_wall = time.monotonic()
        boxes = getattr(prediction[0], "boxes", None)
        confidences = [] if boxes is None else [float(value) for value in boxes.conf]
        return {
            "frame_index": index,
            "anchor": anchor,
            "stop_index": stop_index,
            "frame_sim_s": frame_sim,
            "received_sim_s": frame_sim,
            "decision_sim_s": frame_sim,
            "frame_monotonic_s": frame_wall,
            "received_monotonic_s": received_wall,
            "decision_monotonic_s": decision_wall,
            "render_s": received_wall - frame_wall,
            "inference_s": decision_wall - received_wall,
            "detection_count": len(confidences),
            "max_confidence": max(confidences) if confidences else None,
        }


def runtime_identity(*, device=None, detector_loaded=False, weights_sha256=None) -> dict:
    """What the measurement ran as: the interpreter, the module, the tools and what it never started."""

    import mujoco
    import so101_demo
    import torch

    ultralytics_version = None
    try:
        import ultralytics

        ultralytics_version = getattr(ultralytics, "__version__", None)
    except ImportError:  # pragma: no cover - the detector is an optional declaration
        ultralytics_version = None
    cuda_available = bool(torch.cuda.is_available())
    return {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
        "so101_demo_module_path": str(Path(so101_demo.__file__).resolve()),
        "mujoco_version": mujoco.__version__,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "ultralytics_version": ultralytics_version,
        "cuda_available": cuda_available,
        "cuda_device_name": torch.cuda.get_device_name(0) if cuda_available else None,
        "device": device,
        "detector_loaded": bool(detector_loaded),
        "weights_sha256": weights_sha256,
        "mujoco_only": not detector_loaded,
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
    }


# --- the producer ---------------------------------------------------------------------------------


def _declared_weights(production: Mapping, request) -> str | None:
    """The detector weights the production configuration declares, checked against the file it names."""

    path = request.get("weights_path")
    if path is None:
        return None
    weights = Path(path)
    if not weights.is_file():
        raise FileNotFoundError(f"the timing measurement needs {weights}")
    declared = production.get("weight_sha256")
    measured = _digest(weights)
    if type(declared) is not str or _SHA256.fullmatch(declared) is None:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the production search configuration declares no weight_sha256, so the detector this "
            "measurement would time frames with is not the sealed model",
        )
    if declared != measured:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the declared detector {weights} digests to {measured}, but the production search "
            f"configuration seals {declared}: the frame times would belong to a model the calibration did "
            f"not select",
        )
    return measured


def _anchor_requests(*, seal, production, anchors, attempt_id, session_id) -> list[dict]:
    """One request per sealed anchor, with the bounded stops the controller plans for it."""

    declared = _mapping("sealed geometry", seal).get("in_frame_matrix")
    if not isinstance(declared, Mapping) or not declared:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the sealed geometry declares no in_frame_matrix anchors, so the sweep has no search start",
        )
    names = list(declared) if anchors is None else list(anchors)
    if not names:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, "no anchor was declared for the sweep")
    requests = []
    for name in names:
        if type(name) is not str or name not in declared:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"the sealed geometry declares no anchor {name!r}",
            )
        config = controller_config(
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
                "targets_rad": list(planned_stops(config)),
                "controller_config": config,
            }
        )
    return requests


def write_head_search_timing_measurement(
    *,
    scene_path,
    geometry_seal_path,
    production_search_config_path,
    controller_config_path,
    output_dir,
    weights_path=None,
    anchors=None,
    device="cuda",
    max_settle_s=DEFAULT_MAX_SETTLE_S,
    settle_consecutive_steps=SETTLE_CONSECUTIVE_STEPS,
    attempt_id=MEASUREMENT_ATTEMPT_ID,
    session_id=MEASUREMENT_SESSION_ID,
    startup_readback=None,
    command=None,
    runner=None,
) -> dict:
    """Measure the bounded sweep once and write the documents into a brand-new directory.

    The declared inputs are read and cross-checked before anything is stepped: the scene has to be the one
    the sealed geometry pins, the control period has to be a whole number of the scene's own timesteps, and
    the detector has to be the sealed model on an available CUDA device (`allow_cpu_fallback=false`: a
    measurement that cannot use the declared device refuses rather than falling back). Then the sweep runs,
    the simulation time base is proved, every stop is classified, and only then are the documents written.
    """

    started = time.time()
    scene = Path(scene_path)
    seal_path = Path(geometry_seal_path)
    production_path = Path(production_search_config_path)
    controller_path = Path(controller_config_path)
    for path in (scene, seal_path, production_path, controller_path):
        if not path.is_file():
            raise FileNotFoundError(f"the timing measurement needs {path}")
    if weights_path is not None and not Path(weights_path).is_file():
        raise FileNotFoundError(f"the timing measurement needs {weights_path}")
    output = Path(output_dir)
    output.mkdir(parents=True)

    declaration = read_mujoco_timestep(scene)
    seal_document = json.loads(seal_path.read_text(encoding="utf-8"))
    production = json.loads(production_path.read_text(encoding="utf-8"))
    scene_sha256 = declaration["scene_sha256"]
    sealed_scene = _sealed_scene_sha256(seal_document)
    if sealed_scene != scene_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed geometry pins the scene {sealed_scene}, but the scene this sweep would step "
            f"digests to {scene_sha256}: the sweep would measure a model the calibration did not seal",
        )
    control_period = read_control_period(controller_path)
    timestep = float(declaration["simulation_timestep_s"])
    steps_per_period = control_period / timestep
    if not math.isclose(
        steps_per_period, round(steps_per_period), rel_tol=0.0, abs_tol=_PERIOD_TOLERANCE_S
    ):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sealed controller period {control_period} s is not a whole number of the sealed scene's "
            f"{timestep} s simulation steps, so the sweep cannot command the neck at the period the "
            f"production controller runs at",
        )
    weights_sha256 = _declared_weights(production, {"weights_path": weights_path})
    if weights_sha256 is not None and str(device).startswith("cuda") and not _cuda_available():
        raise _refuse(
            CAL_TIMING_DEVICE_UNAVAILABLE,
            f"the detector was declared for {device!r} but no CUDA device is available, and this "
            f"measurement never falls back to the CPU",
        )
    anchor_requests = _anchor_requests(
        seal=seal_document,
        production=production,
        anchors=anchors,
        attempt_id=attempt_id,
        session_id=session_id,
    )
    camera = _mapping("sealed geometry camera", seal_document.get("camera"))
    request = {
        "scene_path": str(scene),
        "scene_sha256": scene_sha256,
        "camera_name": seal_document.get("camera_name"),
        "image_width": seal_document.get("image_width"),
        "image_height": seal_document.get("image_height"),
        "simulation_timestep_s": timestep,
        "control_period_s": control_period,
        "frame_rate_hz": FRAME_RATE_HZ,
        "settle_velocity_rad_s": anchor_requests[0]["controller_config"]["settle_velocity_rad_s"],
        "goal_tolerance_rad": anchor_requests[0]["controller_config"]["goal_tolerance_rad"],
        "settle_consecutive_steps": settle_consecutive_steps,
        "max_settle_s": max_settle_s,
        "anchors": anchor_requests,
        "weights_path": None if weights_path is None else str(weights_path),
        "weights_sha256": weights_sha256,
        "device": device,
        "min_confidence": anchor_requests[0]["controller_config"]["min_confidence"],
        "tracking_iou": production.get("tracker", {}).get("iou_threshold")
        if isinstance(production.get("tracker"), Mapping)
        else None,
        "camera_identity": dict(camera) if isinstance(camera, Mapping) else {},
    }
    result = (runner or MujocoNeckSweepRunner())(request)
    base = verify_simulation_time_base(result)
    stops = [
        classify_stop(
            stop,
            settle_consecutive_steps=int(settle_consecutive_steps),
            max_settle_s=float(max_settle_s),
        )
        for stop in result["stops"]
    ]
    detector = result.get("detector") if isinstance(result.get("detector"), Mapping) else {}
    frames = _sequence("sweep frames", result.get("frames"))
    if frames and not detector.get("loaded"):
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            "the sweep records frames but reports no loaded detector, so their frame times would belong to "
            "nothing",
        )
    if frames and weights_sha256 is None:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            "the sweep timed frames but no detector weights were declared, so the frame times cannot be "
            "attributed to a sealed model",
        )
    reported = detector.get("weights_sha256")
    if frames and reported is not None and reported != weights_sha256:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the sweep timed frames with the weights {reported}, but the sealed detector is "
            f"{weights_sha256}",
        )
    samples = _frame_samples(frames)
    control = {
        "control_period_s": control_period,
        "source_path": str(controller_path),
        "source_sha256": _digest(controller_path),
        "key": "controller_manager.ros__parameters.update_rate",
        "update_rate_hz": 1.0 / control_period,
        "steps_per_period": int(round(steps_per_period)),
        "declared_by": "the sealed controller configuration",
    }
    timing_path = output / SEARCH_TIMING_ARTIFACT
    identity = (
        result.get("runtime_identity")
        if runner is not None
        else runtime_identity(
            device=device, detector_loaded=bool(detector.get("loaded")), weights_sha256=weights_sha256
        )
    )
    if runner is not None and not identity:
        identity = {}
    contract_path = None
    contract = None
    if samples:
        contract_path = output / FRAME_CONTRACT_ARTIFACT
        contract = frame_contract_document(
            path=contract_path, command=command, startup_readback=startup_readback
        )
        contract_path.write_text(
            json.dumps(contract, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    timing = build_search_timing(
        path=timing_path,
        command=command,
        request=request,
        result=result,
        stops=stops,
        frames=samples,
        control=control,
        scene_path=scene,
        scene_sha256=scene_sha256,
        geometry_seal_path=seal_path,
        geometry_seal_sha256=_digest(seal_path),
        production_search_config_path=production_path,
        production_search_config_sha256=_digest(production_path),
        weights_path=weights_path,
        weights_sha256=weights_sha256,
        runtime_identity=identity,
    )
    timing_path.write_text(
        json.dumps(timing, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    frame_age_path = None
    frame_age = None
    if samples:
        frame_age_path = output / FRAME_AGE_ARTIFACT
        frame_age = build_frame_age_measurements(
            path=frame_age_path,
            command=command,
            frame_contract=contract,
            samples=samples,
            result=result,
            scene_sha256=scene_sha256,
            weights_sha256=weights_sha256,
            runtime_identity=identity,
        )
        frame_age_path.write_text(
            json.dumps(frame_age, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": RECEIPT_KIND,
        "status": "SUCCEEDED",
        "command": command,
        "output_dir": str(output),
        "search_timing_path": str(timing_path),
        "search_timing_sha256": timing["sha256"],
        "frame_age_path": None if frame_age_path is None else str(frame_age_path),
        "frame_age_sha256": None if frame_age is None else frame_age["sha256"],
        "frame_contract_path": None if contract_path is None else str(contract_path),
        "frame_contract_sha256": None if contract is None else contract["sha256"],
        "scene_path": str(scene),
        "scene_sha256": scene_sha256,
        "geometry_seal_path": str(seal_path),
        "geometry_seal_sha256": _digest(seal_path),
        "production_search_config_path": str(production_path),
        "production_search_config_sha256": _digest(production_path),
        "controller_config_path": str(controller_path),
        "controller_config_sha256": _digest(controller_path),
        "weights_path": None if weights_path is None else str(weights_path),
        "weights_sha256": weights_sha256,
        "control_period_s": control_period,
        "simulation_timestep_s": timestep,
        "settle_rule": SETTLE_RULE,
        "settle_consecutive_steps": int(settle_consecutive_steps),
        "max_settle_s": float(max_settle_s),
        "time_base": base["time_base"],
        "stable_stop_count": timing["stable_stop_count"],
        "frame_count": len(samples),
        "p99_settle_s": timing["p99_settle_s"],
        "p99_frame_s": timing["p99_frame_s"],
        "sweep_sim_time_s": result.get("sim_time_s"),
        "sweep_wall_time_s": result.get("wall_time_s"),
        "warmup": dict(result.get("warmup") or {"performed": False}),
        "elapsed_s": time.time() - started,
        "anchors": [anchor["anchor"] for anchor in anchor_requests],
        "runtime_identity": dict(identity or {}),
        "ros_nodes_started": False,
        "mujoco_neck_commanded": True,
        "hardware_motion_commanded": False,
        "transport_measured": False,
        "motion_commanded": False,
    }
    (output / RECEIPT_ARTIFACT).write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {
        "search_timing": timing,
        "frame_age": frame_age,
        "frame_contract": contract,
        "receipt": receipt,
        "search_timing_path": timing_path,
        "frame_age_path": frame_age_path,
        "frame_contract_path": contract_path,
        "output_dir": output,
    }
