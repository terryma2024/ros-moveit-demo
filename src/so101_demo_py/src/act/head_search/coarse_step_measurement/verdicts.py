"""Candidate verdicts, the coarse step choice and the measurement validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import math
from pathlib import Path

from so101_demo.act.head_search.calibration_bundle import (
    CAL_EFFECTIVE_VALUE_MISMATCH,
    PARAMETER_EVIDENCE_KEYS,
)
from so101_demo.act.head_search.calibration_geometry import (
    CANDIDATE_GENERATION_RULE,
)
from so101_demo.act.head_search.coarse_step_measurement.contracts import (
    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
    CAL_SWEEP_EVIDENCE_PARTIAL,
    CAL_SWEEP_UNSTABLE,
    DIGEST_CONVENTION,
    DOMAIN,
    MATCH_RADIUS_PX,
    MEASUREMENT_KIND,
    PARAMETER,
    PHASE,
    PRODUCTION_OWNER,
    SCHEMA_VERSION,
    SELECTION_FORMULA,
    SELECTION_RULE,
    SPLIT,
    STOP_TOLERANCE_RAD,
    UNIT,
    CalibrationCoarseStepRefused,
    _finite,
    _geometry,
    _records,
    _reference,
    _refuse,
    _sequence,
)
from so101_demo.act.head_search.coarse_step_measurement.sweep import (
    match_stop,
    sweep_plan,
    validate_raw_sweep,
)
from so101_demo.act.head_search.measured_readback import OBSERVED_OBSERVATIONS


def _scene_verdict(*, stops: Sequence[Mapping], declared_visible: int, radius: float) -> dict:
    """One pass of one scene: what the sweep saw, what it matched, and what it missed."""

    matched_bodies: set[str] = set()
    visible_bodies: set[str] = set()
    detections = 0
    false_positives = 0
    first_lock: int | None = None
    for position, stop in enumerate(stops):
        outcome = match_stop(
            truth=stop.get("truth", ()),
            detections=stop.get("detections", ()),
            radius_px=radius,
        )
        detections += len(_sequence("detections", stop.get("detections", ())))
        false_positives += outcome["false_positive"]
        for index, record in enumerate(_records("truth", stop.get("truth", ()))):
            body = record.get("body")
            if type(body) is not str or not body:
                raise ValueError("every truth record names its body")
            visible_bodies.add(body)
            if index in outcome["matched_truth"]:
                matched_bodies.add(body)
        if first_lock is None and outcome["true_positive"] > 0:
            first_lock = position
    missed = sorted(visible_bodies - matched_bodies)
    # a scene the dataset declares to hold a visible cup has to be locked somewhere, even when this
    # sweep's own stops never brought that cup into the camera's segmentation at all
    declared_unseen = bool(declared_visible > 0 and not matched_bodies)
    return {
        "required_visible": bool(visible_bodies) or bool(declared_visible > 0),
        "visible_cups": sorted(visible_bodies),
        "matched_cups": sorted(matched_bodies),
        "missed_cups": missed,
        "declared_visible_never_detected": declared_unseen,
        "missed": bool(missed) or declared_unseen,
        "detections": detections,
        "false_positives": false_positives,
        "first_lock_stop_index": first_lock,
    }


def _ineligible(step: float, plan: dict, *, reason: str) -> dict:
    return {
        "coarse_step_rad": step,
        "covers_required_domain": bool(plan["covers_required_domain"]),
        "coverage": plan["coverage"],
        "independent_sweep_check": dict(plan["independent_sweep_check"]),
        "stop_count": plan["stop_count"],
        "stops_per_anchor": {
            anchor["anchor"]: anchor["stop_count"] for anchor in plan["anchors"]
        },
        "scene_count": 0,
        "required_visible_scenes": 0,
        "missed_scenes": [],
        "missed_cups": [],
        "declared_visible_never_detected": [],
        "detections": 0,
        "false_positives": 0,
        "worst_case_first_lock_stop": None,
        "passes": 0,
        "passes_agree": True,
        "scenes": [],
        "eligible": False,
        "reason": reason,
    }


def _planned_stops(plan: Mapping) -> list[tuple[str, float]]:
    return [
        (anchor["anchor"], float(target))
        for anchor in plan["anchors"]
        for target in anchor["targets_rad"]
    ]


def _candidate_verdict(
    *, step: float, record: Mapping, plan: dict, expected_scenes: Sequence[int] | None, validated: Mapping
) -> dict:
    """One candidate's verdict: its coverage, its scenes and whether its val sweep locks them all."""

    radius = validated["match_radius_px"]
    passes = validated["passes"]
    declared_anchors = _records("anchors", record.get("anchors", ()))
    names = [anchor.get("anchor") for anchor in declared_anchors]
    if not plan["covers_required_domain"]:
        if declared_anchors or record.get("scenes"):
            raise _refuse(
                CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                f"candidate {step} declares measured stops, but its bounded plan does not exist: "
                f"{plan['reason']}",
            )
        return _ineligible(
            step, plan, reason=f"does not cover the required domain: {plan['reason']}"
        )
    planned_names = [anchor["anchor"] for anchor in plan["anchors"]]
    if names != planned_names:
        missing = [name for name in planned_names if name not in names]
        unknown = [name for name in names if name not in planned_names]
        raise _refuse(
            CAL_SWEEP_EVIDENCE_PARTIAL,
            f"candidate {step} was measured on the anchors {names} but the sealed geometry declares "
            f"{planned_names} (missing {missing}, unknown {unknown})",
        )
    for anchor in declared_anchors:
        planned = [
            float(target)
            for planned_anchor in plan["anchors"]
            if planned_anchor["anchor"] == anchor.get("anchor")
            for target in planned_anchor["targets_rad"]
        ]
        if anchor.get("targets_rad") != planned:
            raise _refuse(
                CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                f"candidate {step} anchor {anchor.get('anchor')!r} declares the stops "
                f"{anchor.get('targets_rad')!r}, but the bounded plan commands {planned!r}",
            )
    scenes = _records("scenes", record.get("scenes", ()))
    scene_ids = []
    for scene in scenes:
        scene_id = scene.get("scene_id")
        if type(scene_id) is not int or isinstance(scene_id, bool):
            raise ValueError("every measured scene declares an integer scene_id")
        scene_ids.append(int(scene_id))
    if len(set(scene_ids)) != len(scene_ids):
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"candidate {step} measures a val scene twice",
        )
    if expected_scenes is not None and sorted(scene_ids) != sorted(expected_scenes):
        missing = sorted(set(expected_scenes) - set(scene_ids))
        unknown = sorted(set(scene_ids) - set(expected_scenes))
        raise _refuse(
            CAL_SWEEP_EVIDENCE_PARTIAL,
            f"candidate {step} was measured on a different val scene set than the other candidates "
            f"(missing {missing}, unknown {unknown})",
        )

    planned = _planned_stops(plan)
    verdicts = []
    for scene in scenes:
        scene_id = int(scene["scene_id"])
        declared_visible = scene.get("dataset_visible_instances")
        if (
            type(declared_visible) is not int
            or isinstance(declared_visible, bool)
            or declared_visible < 0
        ):
            raise ValueError("every measured scene declares its dataset_visible_instances")
        seen: dict[int, Mapping] = {}
        for entry in _records("passes", scene.get("passes", ())):
            index = entry.get("pass_index")
            if type(index) is not int or isinstance(index, bool):
                raise ValueError("every pass declares an integer pass_index")
            if index in seen:
                raise _refuse(
                    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                    f"candidate {step} scene {scene_id} records pass {index} twice",
                )
            seen[int(index)] = entry
        missing_passes = [index for index in range(passes) if index not in seen]
        if missing_passes:
            raise _refuse(
                CAL_SWEEP_EVIDENCE_PARTIAL,
                f"candidate {step} scene {scene_id} records no pass {missing_passes}; the sweep declares "
                f"{passes} passes",
            )
        unknown_passes = sorted(index for index in seen if index >= passes)
        if unknown_passes:
            raise _refuse(
                CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                f"candidate {step} scene {scene_id} records the passes {unknown_passes} beyond the "
                f"{passes} the document declares",
            )
        per_pass = []
        for index in range(passes):
            stops = _records("stops", seen[index].get("stops", ()))
            if len(stops) != len(planned):
                raise _refuse(
                    CAL_SWEEP_EVIDENCE_PARTIAL,
                    f"candidate {step} scene {scene_id} pass {index} records {len(stops)} stops but its "
                    f"bounded plan commands {len(planned)}",
                )
            if [stop.get("anchor") for stop in stops] != [name for name, _ in planned]:
                raise _refuse(
                    CAL_SWEEP_EVIDENCE_PARTIAL,
                    f"candidate {step} scene {scene_id} pass {index} records the anchors "
                    f"{[stop.get('anchor') for stop in stops]} but its bounded plan commands "
                    f"{[name for name, _ in planned]}",
                )
            for position, (stop, (name, target)) in enumerate(zip(stops, planned)):
                recorded = stop.get("stop_rad")
                if not _finite(recorded) or not math.isclose(
                    float(recorded), target, rel_tol=0.0, abs_tol=STOP_TOLERANCE_RAD
                ):
                    raise _refuse(
                        CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                        f"candidate {step} scene {scene_id} pass {index} anchor {name!r} records the stop "
                        f"{recorded!r} at position {position}, but the bounded plan commands {target!r}; "
                        f"the coarse sweep is a bounded stop sequence, never an ad-hoc angle",
                    )
            per_pass.append(
                _scene_verdict(
                    stops=stops, declared_visible=int(declared_visible), radius=radius
                )
            )
        for index in range(1, passes):
            first, later = per_pass[0], per_pass[index]
            if (
                first["missed_cups"] != later["missed_cups"]
                or first["matched_cups"] != later["matched_cups"]
                or first["required_visible"] != later["required_visible"]
            ):
                raise _refuse(
                    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                    f"candidate {step} scene {scene_id}: pass 0 and pass {index} disagree on what the "
                    f"sweep locked ({first['matched_cups']}/{first['missed_cups']} against "
                    f"{later['matched_cups']}/{later['missed_cups']}); the val evidence is not "
                    f"deterministic and cannot support a lock",
                )
        first = per_pass[0]
        verdicts.append(
            {
                "scene_id": scene_id,
                "scene_group_id": scene.get("scene_group_id"),
                "scenario": scene.get("scenario"),
                "dataset_visible_instances": int(declared_visible),
                "required_visible": first["required_visible"],
                "visible_cups": first["visible_cups"],
                "matched_cups": first["matched_cups"],
                "missed_cups": first["missed_cups"],
                "declared_visible_never_detected": first["declared_visible_never_detected"],
                "missed": first["missed"],
                "detections": first["detections"],
                "false_positives": first["false_positives"],
                "first_lock_stop_index": first["first_lock_stop_index"],
                "passes_agree": True,
            }
        )
    verdicts.sort(key=lambda record: record["scene_id"])
    missed_scenes = sorted(record["scene_id"] for record in verdicts if record["missed"])
    missed_cups = sorted({body for record in verdicts for body in record["missed_cups"]})
    locks = [
        record["first_lock_stop_index"]
        for record in verdicts
        if record["first_lock_stop_index"] is not None
    ]
    return {
        "coarse_step_rad": step,
        "covers_required_domain": True,
        "coverage": plan["coverage"],
        "independent_sweep_check": dict(plan["independent_sweep_check"]),
        "stop_count": plan["stop_count"],
        "stops_per_anchor": {
            anchor["anchor"]: anchor["stop_count"] for anchor in plan["anchors"]
        },
        "scene_count": len(verdicts),
        "required_visible_scenes": sum(1 for record in verdicts if record["required_visible"]),
        "missed_scenes": missed_scenes,
        "missed_cups": missed_cups,
        "declared_visible_never_detected": sorted(
            record["scene_id"] for record in verdicts if record["declared_visible_never_detected"]
        ),
        "detections": sum(record["detections"] for record in verdicts),
        "false_positives": sum(record["false_positives"] for record in verdicts),
        "worst_case_first_lock_stop": max(locks) if locks else None,
        "passes": passes,
        "passes_agree": True,
        "scenes": verdicts,
        "eligible": not missed_scenes,
        "reason": "locks every required-visible val scene"
        if not missed_scenes
        else f"missed the val scenes {missed_scenes}",
    }


def _decide(*, validated: Mapping) -> dict:
    """Evaluate every measured candidate and choose, or refuse the phase as unstable."""

    geometry = validated["geometry"]
    expected_scenes = None
    verdicts = []
    for step in validated["generated_candidates"]:
        record = validated["measured"][step]
        plan = sweep_plan(coarse_step_rad=step, geometry=geometry)
        verdict = _candidate_verdict(
            step=step,
            record=record,
            plan=plan,
            expected_scenes=expected_scenes,
            validated=validated,
        )
        if expected_scenes is None and verdict["scene_count"]:
            expected_scenes = [scene["scene_id"] for scene in verdict["scenes"]]
        verdicts.append(verdict)
    eligible = [verdict for verdict in verdicts if verdict["eligible"]]
    if not eligible:
        detail = "; ".join(
            f"{verdict['coarse_step_rad']}: {verdict['reason']}" for verdict in verdicts
        )
        raise _refuse(
            CAL_SWEEP_UNSTABLE,
            f"no generated coarse-step candidate at or below half the field of view covers the required "
            f"domain and locks every required-visible val scene: {detail}",
        )
    # the largest step first; the observed lock time - the first stop that matched a cup - breaks a tie,
    # so a candidate that locks sooner is preferred when two candidates are otherwise equal
    ranked = sorted(
        eligible,
        key=lambda verdict: (
            -verdict["coarse_step_rad"],
            verdict["worst_case_first_lock_stop"]
            if verdict["worst_case_first_lock_stop"] is not None
            else math.inf,
            verdict["stop_count"],
        ),
    )
    chosen = ranked[0]
    return {
        "candidates": verdicts,
        "chosen_coarse_step_rad": chosen["coarse_step_rad"],
        "chosen_index": verdicts.index(chosen),
        "measured_candidate_steps": [verdict["coarse_step_rad"] for verdict in verdicts],
        "selection_rule": SELECTION_RULE,
        "candidate_generation_rule": CANDIDATE_GENERATION_RULE,
    }


def choose_coarse_step_rad(*, geometry, observations, selected_weights_sha256=None) -> dict:
    """Evaluate every measured candidate step and choose the design's largest locking step.

    The returned document carries one verdict per generated candidate - coverage, stops, required-visible
    scenes, the cups it missed and where it first locked - and the choice itself. Refusals are the
    module's own: missing, partial or contradictory evidence never produces a value, and a complete sweep
    in which no candidate locks every required-visible val scene refuses as `CAL_SWEEP_UNSTABLE`.
    """

    validated = validate_raw_sweep(
        geometry=geometry,
        observations=observations,
        selected_weights_sha256=selected_weights_sha256,
    )
    decision = _decide(validated=validated)
    return {
        **decision,
        "passes": validated["passes"],
        "match_radius_px": validated["match_radius_px"],
    }


def _readback(name: str, value, startup_readback):
    """The startup readback of the value: a reported one is checked, an absent one stays unverified.

    A readback taken off the running controller keeps its own observation and verdict, exactly as phase
    6 does for the five values it computes itself; a readback the caller merely reports is checked here
    and marked as reported.
    """

    if startup_readback is None:
        return {
            "observed_value": value,
            "observation": "declared_by_coarse_step_measurement",
            "verified": False,
            "detail": (
                "the val sweep computes the value; the run records the startup readback that proves the "
                "production controller uses it"
            ),
        }
    if not isinstance(startup_readback, Mapping) or "observed_value" not in startup_readback:
        raise ValueError(f"the startup readback of {name} records no observed value")
    observed = startup_readback["observed_value"]
    if observed != value:
        raise CalibrationCoarseStepRefused(
            CAL_EFFECTIVE_VALUE_MISMATCH,
            f"{name}: the startup readback observed {observed!r} but the val sweep chose {value!r}; the "
            f"running system has to use the chosen value",
        )
    readback = dict(startup_readback)
    if readback.get("observation") not in OBSERVED_OBSERVATIONS:
        # the caller reported the value rather than observing the controller that uses it
        readback["observation"] = "reported_by_caller"
        readback["verified"] = True
    return readback


def coarse_step_evidence(
    *,
    decision,
    geometry_reference,
    observations_reference,
    geometry,
    passes,
    match_radius_px=MATCH_RADIUS_PX,
    scene_count=None,
    startup_readback=None,
) -> dict:
    """The `coarse_step_rad` evidence block phase 8 requires, built from the decision."""

    value = decision["chosen_coarse_step_rad"]
    chosen = decision["candidates"][decision["chosen_index"]]
    sealed = _geometry(geometry)
    half = sealed["horizontal_fov_rad"] / 2.0
    distribution = {
        "measured_candidate_steps": list(decision["measured_candidate_steps"]),
        "candidate_count": len(decision["candidates"]),
        "candidate_verdicts": {
            f"{verdict['coarse_step_rad']}": {
                "eligible": verdict["eligible"],
                "covers_required_domain": verdict["covers_required_domain"],
                "missed_scenes": verdict["missed_scenes"],
                "reason": verdict["reason"],
            }
            for verdict in decision["candidates"]
        },
        "scene_count": chosen["scene_count"] if scene_count is None else scene_count,
        "required_visible_scenes": chosen["required_visible_scenes"],
        "stop_count": chosen["stop_count"],
        "stops_per_anchor": dict(chosen["stops_per_anchor"]),
        "worst_case_first_lock_stop": chosen["worst_case_first_lock_stop"],
        "detections": chosen["detections"],
        "false_positives": chosen["false_positives"],
        "missed_scenes": list(chosen["missed_scenes"]),
        "passes": passes,
    }
    margin = {
        "half_fov_rad": half,
        "value_over_half_fov": value / half,
        "required_search_domain_rad": list(sealed["required_search_domain_rad"]),
        "coverage": "bounded two-way sweep, horizontal field-of-view union of the stops",
        "match_radius_px": match_radius_px,
        "missed_cups": len(chosen["missed_cups"]),
        "required_visible_scenes": chosen["required_visible_scenes"],
        "passes": passes,
    }
    block = {
        "value": value,
        "unit": UNIT,
        "selection_formula": SELECTION_FORMULA,
        "input_evidence": [dict(geometry_reference), dict(observations_reference)],
        "observed_distribution": distribution,
        "safety_margin": margin,
        "production_owner": PRODUCTION_OWNER,
        "startup_readback": _readback(PARAMETER, value, startup_readback),
    }
    return {key: block[key] for key in PARAMETER_EVIDENCE_KEYS}


def validate_head_search_coarse_step_measurement(
    *,
    geometry,
    observations,
    selected_weights_sha256=None,
    startup_readback=None,
    geometry_reference=None,
    observations_reference=None,
    output_path=None,
) -> dict:
    """Produce this phase's document: the chosen `coarse_step_rad`, its verdicts and its evidence block.

    Phase 6 calls this with the geometry document phase 2 produced in this run and the raw sweep the run
    declared. The raw document is validated against the seal, every candidate is evaluated, the largest
    locking candidate is chosen, and the evidence block phase 8 consumes is built and cited. The
    references default to the ones the two documents declare themselves (the sealed geometry block and the
    sweep's own path and digest), so the block always cites the bytes the decision was made from. When
    `output_path` is given the phase document is written there and nowhere else; without it the phase
    writes nothing at all.
    """

    validated = validate_raw_sweep(
        geometry=geometry,
        observations=observations,
        selected_weights_sha256=selected_weights_sha256,
    )
    decision = _decide(validated=validated)
    geometry_reference = (
        _reference("the sealed geometry", validated["document"]["geometry"])
        if geometry_reference is None
        else _reference("the sealed geometry", geometry_reference)
    )
    observations_reference = (
        _reference("the raw sweep", validated["document"])
        if observations_reference is None
        else _reference("the raw sweep", observations_reference)
    )
    dataset = validated["dataset"]
    chosen = decision["candidates"][decision["chosen_index"]]
    block = coarse_step_evidence(
        decision=decision,
        geometry_reference=geometry_reference,
        observations_reference=observations_reference,
        geometry=validated["geometry"],
        passes=validated["passes"],
        match_radius_px=validated["match_radius_px"],
        scene_count=chosen["scene_count"],
        startup_readback=startup_readback,
    )
    document = {
        "schema_version": SCHEMA_VERSION,
        "kind": MEASUREMENT_KIND,
        "phase": PHASE,
        "split": SPLIT,
        "domain": DOMAIN,
        "geometry": {
            "reference": geometry_reference,
            "horizontal_fov_rad": validated["geometry"]["horizontal_fov_rad"],
            "lock_valid_neck_rad": list(validated["geometry"]["lock_valid_neck_rad"]),
            "required_search_domain_rad": list(
                validated["geometry"]["required_search_domain_rad"]
            ),
            "anchors_rad": dict(validated["geometry"]["anchors_rad"]),
        },
        "observations": {
            "path": observations_reference["path"],
            "sha256": observations_reference["sha256"],
            "kind": validated["document"].get("kind"),
            "schema_version": validated["document"].get("schema_version"),
            "split": validated["document"].get("split"),
            "domain": validated["document"].get("domain"),
            "passes": validated["passes"],
            "match_radius_px": validated["match_radius_px"],
            "scene_count": dataset.get("scene_count"),
            "scene_limit": dataset.get("scene_limit"),
            "digest_convention": DIGEST_CONVENTION,
            "model": dict(validated["model"]),
            "dataset": dict(dataset),
        },
        "candidate_generation": {
            "rule": CANDIDATE_GENERATION_RULE,
            "half_fov_rad": validated["geometry"]["horizontal_fov_rad"] / 2.0,
            "generated_candidates": list(validated["generated_candidates"]),
        },
        "candidates": decision["candidates"],
        "chosen_coarse_step_rad": decision["chosen_coarse_step_rad"],
        "chosen_index": decision["chosen_index"],
        "coarse_step_rad": decision["chosen_coarse_step_rad"],
        "selection_rule": decision["selection_rule"],
        "passes": validated["passes"],
        "parameter_evidence": {PARAMETER: block},
        "measured_here": False,
        "motion_commanded": False,
    }
    if output_path is not None:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return document


def load_selected_candidate(path) -> dict:
    """The selected model's frozen candidate document, through the repository's own loader.

    The frozen document is what names the operating point the sweep measures at and the weight digest the
    sweep must be shown to have used, so it is read by the repository's existing
    `perception_benchmark.head_search_models.load_frozen_candidate` - which also refuses a candidate that
    is not promotable - rather than by a second reader here.
    """

    from so101_demo.perception_benchmark.head_search_models import load_frozen_candidate

    return dict(load_frozen_candidate(path).document)
