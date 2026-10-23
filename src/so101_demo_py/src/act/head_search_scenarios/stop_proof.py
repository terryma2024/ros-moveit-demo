"""The settle and stop proofs and the scenario declaration."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from so101_demo.act.head_search_scenarios.contracts import (
    _BOUND_TOLERANCE_RAD,
    STOP_PROOF_SAMPLES,
    _refuse,
)
from so101_demo.act.head_search_scenarios.plan import (
    SETTLE_PROOF_DEFINITION,
    declared_cup_count,
    expected_terminals,
)
from so101_demo.act.head_search_timing_measurement.contracts import (
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    _finite,
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
