"""The coarse-step val sweep: the raw observations, the decision, and the evidence phase 6 owns.

Design section 7.1 gives `coarse_step_rad` one rule: among the candidates at or below half the horizontal
field of view, take the **largest** step whose bounded two-way sweep covers the whole
`required_search_domain_rad` and misses no required-visible val cup, and never replace the coverage proof
with a fixed forward accumulation. Phase 2 generates the candidates, proves the coverage and issues the
per-target sweep-check receipts; this module owns the other half of the rule - the val evidence - and
turns a raw sweep into the value and the evidence block phase 6 hands to phase 8.

The raw observations are exactly that, raw: one entry per generated candidate step, per val scene, per
anchor and per bounded stop, carrying that stop's per-camera ground truth and the selected model's
detections (the recorder semantics of ledger HS-260/HS-261). **This module never trusts a declared
verdict**: it re-derives the bounded plan of every candidate from the sealed geometry (the repository's
own `bounded_search_stops` and `independent_sweep_check`), requires the recorded stops to be that plan,
matches the detections to the truth itself with the gate's greedy nearest rule, and decides from those
numbers. A cup the sweep's own stops see but never detect is a missed scene; a scene the dataset declares
empty is not required-visible; two passes that disagree are contradictory evidence rather than a result.

Four refusals, all of them fail-closed and none of them inventing a value:

* `CAL_SWEEP_EVIDENCE_MISSING` - nothing was measured at all (no raw document, no candidate, no scene);
* `CAL_SWEEP_EVIDENCE_PARTIAL` - the measurement grid is incomplete: a generated candidate step was not
  measured, a candidate was measured on a different scene set, or an anchor or a stop of its own bounded
  plan is missing;
* `CAL_SWEEP_EVIDENCE_CONTRADICTORY` - the document contradicts itself or the run: its declared digest is
  not its body, its geometry or camera domain is not the sealed one, it carries evidence of another model
  than the selected one, its stops are not the bounded plan, or two passes of the same scene disagree;
* `CAL_SWEEP_UNSTABLE` - the evidence is complete and consistent, but no candidate step both covers the
  required domain and locks every required-visible val scene. Design section 7.1 has no value to report in
  that case, so the phase reports the failure instead.

Evidence from another split is refused with phase 3's own `CAL_SPLIT_LEAK` (the val split is the only one
this parameter may be measured on), and a startup readback that disagrees with the value is refused with
phase 8's `CAL_EFFECTIVE_VALUE_MISMATCH`, both reusing the existing codes rather than inventing new ones.

The module also owns the **producer**: :func:`measure_coarse_step_val_sweep` drives the repository's
dataset renderer over the head val scenes and the selected model over every bounded stop of every
generated candidate, and writes the raw observations and the decision. That is the only place in this
module that imports MuJoCo, the detector or a GPU, and it does so inside the function, so the decision
layer stays a pure, independently testable library. The CLI only parses and validates: the measurement is
the installed program's, never an ad-hoc script's.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sys
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

from so101_demo.act.head_search_calibration_bundle import (
    CAL_EFFECTIVE_VALUE_MISMATCH,
    PARAMETER_EVIDENCE_KEYS,
)
from so101_demo.act.head_search_calibration_geometry import (
    CANDIDATE_GENERATION_RULE,
    generate_coarse_step_candidates,
)
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_measured_readback import OBSERVED_OBSERVATIONS
from so101_demo.act.head_search_domain import (
    HeadSearchDomainError,
    bounded_search_stops,
    coverage_is_complete,
    independent_sweep_check,
)
from so101_demo.act.head_search_operating_point import CAL_SPLIT_LEAK
from so101_demo.perception_benchmark.contracts import canonical_sha256

SCHEMA_VERSION = 1
#: the raw observations document: what a sweep of the head val scenes records
KIND = "head_search_coarse_step_val_sweep"
#: the decision document phase 6 consumes: the value, the verdicts and the evidence block
MEASUREMENT_KIND = "head_search_coarse_step_measurement"
PHASE = "coarse_step_measurement"
PARAMETER = "coarse_step_rad"
UNIT = "rad"
DOMAIN = "head"
SPLIT = "val"

#: the gate's matcher: one centre-to-centre radius in pixels
MATCH_RADIUS_PX = 8.0

#: a re-rendered stop is not bit-identical (the EGL renderer differs by up to one 8-bit level), so the
#: reconstruction check of a val scene compares the rendered image with the dataset's own image within
#: this bound - measured at 1 for all 200 val scenes of the head dataset (ledger HS-298)
RECONSTRUCTION_PIXEL_TOLERANCE = 1
#: the two documents a bounded stop's plan is compared at; the planner's own arithmetic is deterministic,
#: so this only absorbs a JSON round-trip
STOP_TOLERANCE_RAD = 1e-12

CAL_SWEEP_EVIDENCE_MISSING = "CAL_SWEEP_EVIDENCE_MISSING"
CAL_SWEEP_EVIDENCE_PARTIAL = "CAL_SWEEP_EVIDENCE_PARTIAL"
CAL_SWEEP_EVIDENCE_CONTRADICTORY = "CAL_SWEEP_EVIDENCE_CONTRADICTORY"
CAL_SWEEP_UNSTABLE = "CAL_SWEEP_UNSTABLE"
REFUSAL_CODES = (
    CAL_SWEEP_EVIDENCE_MISSING,
    CAL_SWEEP_EVIDENCE_PARTIAL,
    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
    CAL_SWEEP_UNSTABLE,
    CAL_SPLIT_LEAK,
    CAL_EFFECTIVE_VALUE_MISMATCH,
)

SELECTION_RULE = (
    "the largest generated candidate at or below half the horizontal field of view whose bounded "
    "two-way sweep covers the whole required_search_domain_rad and misses no required-visible val cup, "
    "with repeated passes agreeing; a tie breaks on the shortest lock time (the first stop that matched "
    "a cup), which the largest step also minimises by commanding the fewest stops"
)
SELECTION_FORMULA = (
    "the largest generated coarse_step_rad for which coverage_is_complete(bounded_search_stops(...)) and "
    "independent_sweep_check(...) hold and missed_scenes == [] on the head val split; the observed "
    "worst-case first-lock stop breaks a tie"
)
PRODUCTION_OWNER = "so101_demo.act.search.HeadSearchController (coarse_step_rad)"

#: what the raw document's own digest covers: its whole body, its `path` included
DIGEST_CONVENTION = "sha256 = canonical_sha256(body without the sha256 field)"

_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class CalibrationCoarseStepRefused(CalibrationInputsRefused):
    """A coarse-step refusal, carrying the exact code the run records and stops on.

    It is a phase-1 refusal as well, so a caller that catches `CalibrationInputsRefused` catches every
    refusal of the calibration phases and reads the code off the exception.
    """


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _refuse(code: str, detail: str) -> CalibrationCoarseStepRefused:
    return CalibrationCoarseStepRefused(code, detail)


def _mapping(name: str, value) -> Mapping:
    """A document the phase can read, or a plain `ValueError` for a malformed one."""

    if not isinstance(value, Mapping):
        raise ValueError(f"{name} must be a mapping")
    return value


def _sequence(name: str, value) -> list:
    if isinstance(value, (str, bytes)) or not isinstance(value, Sequence):
        raise ValueError(f"{name} must be a sequence")
    return list(value)


def _records(name: str, value) -> list[Mapping]:
    records = _sequence(name, value)
    for record in records:
        if not isinstance(record, Mapping):
            raise ValueError(f"every {name} record must be a mapping")
    return records


def _positive(name: str, value) -> float:
    if not _finite(value) or float(value) <= 0.0:
        raise ValueError(f"{name} must be finite and positive")
    return float(value)


def _interval(name: str, value) -> tuple[float, float]:
    bounds = _sequence(name, value)
    if len(bounds) != 2:
        raise ValueError(f"{name} must be two finite ordered bounds")
    low, high = (float(bound) for bound in bounds)
    if not math.isfinite(low) or not math.isfinite(high) or low >= high:
        raise ValueError(f"{name} must be two finite ordered bounds")
    return low, high


def _centre(record, name: str) -> tuple[float, float]:
    if not isinstance(record, Mapping):
        raise ValueError(f"every {name} must be a record carrying x and y")
    x, y = record.get("x"), record.get("y")
    if not (_finite(x) and _finite(y)):
        raise ValueError(f"a {name} record declares no finite x/y")
    return float(x), float(y)


def _confidence(record) -> float:
    if not isinstance(record, Mapping):
        raise ValueError("every detection must be a record")
    conf = record.get("conf")
    if not _finite(conf):
        raise ValueError("a detection record declares no finite conf")
    return float(conf)


def _reference(name: str, document) -> dict:
    """The path and sha256 of one measured input, as the evidence block cites it."""

    if not isinstance(document, Mapping):
        raise ValueError(f"{name} must be a document carrying its path and sha256")
    path, digest = document.get("path"), document.get("sha256")
    if type(path) is not str or not path:
        raise ValueError(f"{name} names no evidence path")
    if type(digest) is not str or _SHA256.fullmatch(digest) is None:
        raise ValueError(f"{name} carries no sha256 evidence digest")
    return {"path": path, "sha256": digest}


def _geometry(geometry) -> dict:
    """The sealed geometry this phase measures against, as phase 2 hands it over."""

    declared = _mapping("the sealed geometry", geometry)
    anchors: dict[str, float] = {}
    for name, angle in _mapping("anchors_rad", declared.get("anchors_rad")).items():
        if type(name) is not str or not name or not _finite(angle):
            raise ValueError("every anchor must be named and carry a finite neck angle")
        anchors[name] = float(angle)
    if not anchors:
        raise ValueError("the sealed geometry declares no anchors")
    return {
        "horizontal_fov_rad": _positive("horizontal_fov_rad", declared.get("horizontal_fov_rad")),
        "lock_valid_neck_rad": list(
            _interval("lock_valid_neck_rad", declared.get("lock_valid_neck_rad"))
        ),
        "required_search_domain_rad": list(
            _interval("required_search_domain_rad", declared.get("required_search_domain_rad"))
        ),
        "sealed_coarse_step_candidate_rad": declared.get("sealed_coarse_step_candidate_rad"),
        "anchors_rad": anchors,
    }


# --------------------------------------------------------------------------------------------------
# the bounded plan of one candidate, and the gate's matcher
# --------------------------------------------------------------------------------------------------


def _uncovered(reason: str) -> dict:
    return {
        "anchors": [],
        "stop_count": 0,
        "covers_required_domain": False,
        "reason": reason,
        "coverage": "horizontal_fov_union_of_stops",
        "independent_sweep_check": {"checked": False, "reason": reason},
    }


def sweep_plan(*, coarse_step_rad, geometry) -> dict:
    """The bounded two-way plan of one candidate step, per anchor, with both coverage derivations.

    The plan is the repository's planner, never a second copy of it: one `bounded_search_stops` call per
    anchor, then `coverage_is_complete` and the independent point-by-point `independent_sweep_check`. A
    domain the safe neck interval cannot reach has no plan at all - the record then carries no anchor and
    the planner's own reason, so a caller can see why the candidate could never cover.
    """

    sealed = _geometry(geometry)
    step = _positive("coarse_step_rad", coarse_step_rad)
    fov = sealed["horizontal_fov_rad"]
    if step > fov / 2.0 + 1e-12:
        raise ValueError(
            f"coarse_step_rad {step} exceeds half the field of view {fov / 2.0}; the candidates are "
            "generated at or below that bound"
        )
    required = sealed["required_search_domain_rad"]
    safe = sealed["lock_valid_neck_rad"]
    anchors = []
    for name, anchor in sealed["anchors_rad"].items():
        try:
            plan = bounded_search_stops(
                anchor_rad=anchor,
                required_domain_rad=required,
                safe_interval_rad=safe,
                horizontal_fov_rad=fov,
                coarse_step_rad=step,
            )
        except HeadSearchDomainError as error:
            return _uncovered(f"anchor {name}: {error}")
        if not coverage_is_complete(plan, required_domain_rad=required):
            return _uncovered(
                f"anchor {name}: the field-of-view union of the stops does not cover the required domain"
            )
        checked, reason = independent_sweep_check(plan, required_domain_rad=required)
        if not checked:
            return _uncovered(f"anchor {name}: the independent sweep check disagrees ({reason})")
        anchors.append(
            {
                "anchor": name,
                "anchor_rad": float(plan.anchor_rad),
                "targets_rad": [float(target) for target in plan.targets_rad],
                "stop_count": len(plan.targets_rad),
            }
        )
    return {
        "anchors": anchors,
        "stop_count": sum(anchor["stop_count"] for anchor in anchors),
        "covers_required_domain": True,
        "reason": "covered",
        "coverage": "horizontal_fov_union_of_stops",
        "independent_sweep_check": {"checked": True, "reason": "covered"},
    }


def match_stop(*, truth, detections, radius_px=MATCH_RADIUS_PX) -> dict:
    """Match one stop's detections to its truth: the gate's greedy nearest pair within the radius.

    The detections are taken in the order the gate takes them - highest confidence first - and each is
    paired with the nearest still-unmatched truth inside `radius_px`; an unmatched detection is a false
    positive and an unmatched truth is a miss. Nothing here filters or rewrites the record: the counts are
    what the recorded numbers say.
    """

    truths = _records("truth", truth)
    recorded = _records("detections", detections)
    radius = float(radius_px)
    if not math.isfinite(radius) or radius < 0.0:
        raise ValueError("radius_px must be finite and non-negative")
    matched: set[int] = set()
    offsets: list[float] = []
    false_positive = 0
    for detection in sorted(recorded, key=lambda record: -_confidence(record)):
        centre = _centre(detection, "detection")
        best, best_distance = None, None
        for index, record in enumerate(truths):
            if index in matched:
                continue
            distance = math.dist(centre, _centre(record, "truth"))
            if best_distance is None or distance < best_distance:
                best, best_distance = index, distance
        if best is not None and float(best_distance) <= radius:
            matched.add(best)
            offsets.append(float(best_distance))
        else:
            false_positive += 1
    return {
        "true_positive": len(matched),
        "false_positive": false_positive,
        "matched_truth": sorted(matched),
        "missed_truth": [index for index in range(len(truths)) if index not in matched],
        "offsets_px": offsets,
    }


# --------------------------------------------------------------------------------------------------
# validation of the raw document: missing, partial, contradictory
# --------------------------------------------------------------------------------------------------


def _verified_digest(document: Mapping) -> str:
    """The document's own digest of its body, verified rather than trusted."""

    declared = document.get("sha256")
    if type(declared) is not str or _SHA256.fullmatch(declared) is None:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            "the raw sweep declares no sha256 digest of its own body",
        )
    body = {key: value for key, value in document.items() if key != "sha256"}
    try:
        recomputed = canonical_sha256(body)
    except ValueError as error:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"the raw sweep is not a finite JSON document, so its digest cannot be recomputed: {error}",
        ) from error
    if declared != recomputed:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"the raw sweep declares the digest {declared} but its body digests to {recomputed} "
            f"({DIGEST_CONVENTION})",
        )
    return declared


def validate_raw_sweep(*, geometry, observations, selected_weights_sha256=None) -> dict:
    """Check the raw sweep against the sealed geometry and return what the decision reads.

    Everything that makes the evidence *this* run's evidence is checked here: the document is the raw
    sweep kind, it holds measured candidates and scenes, its digest is its own body, its split is the
    design's val split (phase 3's `CAL_SPLIT_LEAK`), its camera domain and geometry are the sealed ones,
    its model is the selected one, and every generated candidate step was measured exactly once. The
    per-candidate stops are checked by :func:`_candidate_verdict`, against that candidate's own bounded
    plan. Missing pieces refuse as `CAL_SWEEP_EVIDENCE_PARTIAL`, contradictions as
    `CAL_SWEEP_EVIDENCE_CONTRADICTORY`.
    """

    document = observations
    if not isinstance(document, Mapping) or document.get("kind") != KIND:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_MISSING,
            f"no {KIND} document was measured, so no coarse step can be chosen from val evidence",
        )
    records = _records("candidates", document.get("candidates", ()))
    if not records:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_MISSING,
            "the raw sweep measured no candidate step at all",
        )
    digest = _verified_digest(document)
    split = document.get("split")
    if split != SPLIT:
        raise _refuse(
            CAL_SPLIT_LEAK,
            f"the coarse step is measured on the {SPLIT!r} split of the head dataset, but this sweep "
            f"records the {split!r} split; a split that may not select values cannot bound them",
        )
    domain = document.get("domain")
    if domain != DOMAIN:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"the coarse step is the {DOMAIN} camera's horizontal domain, but this sweep records the "
            f"{domain!r} domain",
        )
    sealed = _geometry(geometry)
    declared_geometry = _mapping("the sweep's geometry", document.get("geometry"))
    for name in (
        "horizontal_fov_rad",
        "lock_valid_neck_rad",
        "required_search_domain_rad",
        "anchors_rad",
    ):
        if declared_geometry.get(name) != sealed[name]:
            raise _refuse(
                CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                f"the sweep declares {name} {declared_geometry.get(name)!r} but the run's sealed geometry "
                f"is {sealed[name]!r}",
            )
    model = _mapping("the sweep's model", document.get("model"))
    if selected_weights_sha256 is not None:
        declared_weights = model.get("weights_sha256")
        if declared_weights != selected_weights_sha256:
            raise _refuse(
                CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                f"the val sweep was measured with the weights {declared_weights!r}, but the run selected "
                f"the candidate whose weights digest is {selected_weights_sha256!r}",
            )
    passes = document.get("passes")
    if type(passes) is not int or isinstance(passes, bool) or passes < 1:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_PARTIAL,
            f"the sweep declares {passes!r} passes; at least one measured pass is required",
        )
    radius = document.get("match_radius_px", MATCH_RADIUS_PX)
    if not _finite(radius) or float(radius) < 0.0:
        raise ValueError("match_radius_px must be finite and non-negative")

    generated = generate_coarse_step_candidates(
        sealed["horizontal_fov_rad"],
        sealed_candidate_rad=sealed["sealed_coarse_step_candidate_rad"],
    )
    measured: dict[float, Mapping] = {}
    for record in records:
        step = record.get("coarse_step_rad")
        if not _finite(step):
            raise ValueError("every measured candidate declares a finite coarse_step_rad")
        step = float(step)
        if step in measured:
            raise _refuse(
                CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                f"the candidate step {step} was measured twice; one candidate has one measurement",
            )
        measured[step] = record
    absent = [step for step in generated if step not in measured]
    if absent:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_PARTIAL,
            f"the generated candidate steps {absent} were never measured, so the choice would be made "
            f"on a partial sweep",
        )
    unknown = sorted(step for step in measured if step not in generated)
    if unknown:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_PARTIAL,
            f"the sweep measured {unknown}, which the sealed geometry does not generate as candidates",
        )
    coverable = [
        step for step in generated if sweep_plan(coarse_step_rad=step, geometry=sealed)[
            "covers_required_domain"
        ]
    ]
    if coverable and not any(measured[step].get("scenes") for step in coverable):
        raise _refuse(
            CAL_SWEEP_EVIDENCE_MISSING,
            f"the raw sweep holds no measured {SPLIT} scene for any candidate that could cover the "
            f"required domain",
        )
    return {
        "document": document,
        "sha256": digest,
        "geometry": sealed,
        "generated_candidates": tuple(generated),
        "measured": measured,
        "model": dict(model),
        "passes": int(passes),
        "match_radius_px": float(radius),
        "dataset": dict(document.get("dataset") or {}),
    }


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


# --------------------------------------------------------------------------------------------------
# the evidence block and the phase document phase 6 consumes
# --------------------------------------------------------------------------------------------------


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


# --------------------------------------------------------------------------------------------------
# the producer: the real sweep of the head val scenes with the selected model
# --------------------------------------------------------------------------------------------------


def load_selected_candidate(path) -> dict:
    """The selected model's frozen candidate document, through the repository's own loader.

    The frozen document is what names the operating point the sweep measures at and the weight digest the
    sweep must be shown to have used, so it is read by the repository's existing
    `perception_benchmark.head_search_models.load_frozen_candidate` - which also refuses a candidate that
    is not promotable - rather than by a second reader here.
    """

    from so101_demo.perception_benchmark.head_search_models import load_frozen_candidate

    return dict(load_frozen_candidate(path).document)


def plan_coarse_step_val_sweep(
    *,
    geometry_seal,
    dataset_manifest,
    frozen_candidate,
    weights_sha256,
    split=SPLIT,
    domain=DOMAIN,
    scene_limit=None,
    match_radius_px=MATCH_RADIUS_PX,
) -> dict:
    """Plan the real sweep: the val scenes, the operating point and the bounded plan per candidate.

    Pure and detector-free, so the plan can be checked without a GPU: it verifies that the weights really
    are the frozen candidate's own bytes, that the manifest is the sealed head dataset's, that the split
    holds measurable scenes, that the frozen candidate carries the domain's operating point, and it lays
    out every generated candidate's bounded plan per anchor. The heavy producer then renders exactly these
    scenes at exactly these stops.
    """

    from so101_demo.act.head_search_calibration_geometry import read_geometry_document

    seal = read_geometry_document(geometry_seal)
    manifest = _mapping("the dataset manifest", dataset_manifest)
    frozen = _mapping("the frozen candidate", frozen_candidate)
    if type(weights_sha256) is not str or _SHA256.fullmatch(weights_sha256) is None:
        raise ValueError("the weights digest must be a sha256 digest")
    frozen_digest = frozen.get("weight_sha256")
    if frozen_digest != weights_sha256:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"the weights digest to measure is {weights_sha256} but the frozen candidate records "
            f"{frozen_digest!r}; the val sweep must measure the selected model's own bytes",
        )
    seal_digest = geometry_seal.get("seal_sha256")
    if manifest.get("geometry_seal_sha256") != seal_digest:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"the dataset manifest was generated under the seal {manifest.get('geometry_seal_sha256')!r}, "
            f"not the sealed geometry's own {seal_digest!r}",
        )
    if manifest.get("camera_name") != geometry_seal.get("camera_name"):
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"the dataset manifest renders {manifest.get('camera_name')!r} but the seal names "
            f"{geometry_seal.get('camera_name')!r}",
        )
    points = _mapping("the frozen candidate's operating points", frozen.get("operating_points"))
    point = points.get(domain)
    if not isinstance(point, Mapping):
        raise _refuse(
            CAL_SWEEP_EVIDENCE_PARTIAL,
            f"the frozen candidate declares no {domain!r} operating point, so the sweep has no "
            f"confidence floor to measure at",
        )
    tracker = point.get("tracker")
    min_confidence = point.get("min_confidence")
    tracking_iou = tracker.get("iou") if isinstance(tracker, Mapping) else None
    if not (_finite(min_confidence) and _finite(tracking_iou)):
        raise _refuse(
            CAL_SWEEP_EVIDENCE_PARTIAL,
            f"the frozen candidate's {domain!r} operating point declares no finite min_confidence and "
            f"tracker.iou",
        )
    scenes = []
    for sample in _records("samples", manifest.get("samples", ())):
        if sample.get("split") != split:
            continue
        seed = sample.get("seed")
        scenario = sample.get("scenario")
        camera = sample.get("camera")
        if type(seed) is not int or isinstance(seed, bool):
            raise ValueError(f"every {split} sample declares an integer seed")
        if type(scenario) is not str or not scenario:
            raise ValueError(f"the {split} sample {seed} declares no scenario")
        neck = camera.get("neck_rad") if isinstance(camera, Mapping) else None
        if not _finite(neck):
            raise ValueError(f"the {split} sample {seed} declares no finite camera neck_rad")
        visible = sample.get("visible_instance_count")
        if type(visible) is not int or isinstance(visible, bool) or visible < 0:
            raise ValueError(f"the {split} sample {seed} declares no visible_instance_count")
        scenes.append(
            {
                "scene_id": int(seed),
                "scene_group_id": sample.get("scene_group_id"),
                "scenario": scenario,
                "neck_rad": float(neck),
                "visible_instance_count": int(visible),
                "image": sample.get("image"),
            }
        )
    if not scenes:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_MISSING,
            f"the sealed head dataset holds no {split} scene, so there is no val evidence to measure",
        )
    if scene_limit is not None:
        if type(scene_limit) is not int or isinstance(scene_limit, bool) or scene_limit < 1:
            raise ValueError("scene_limit must be a positive integer when it is given")
        scenes = scenes[:scene_limit]
    if not (_finite(match_radius_px) and float(match_radius_px) >= 0.0):
        raise ValueError("match_radius_px must be finite and non-negative")
    candidates = generate_coarse_step_candidates(
        seal["horizontal_fov_rad"],
        sealed_candidate_rad=seal.get("sealed_coarse_step_candidate_rad"),
    )
    return {
        "geometry": seal,
        "scenes": scenes,
        "scene_limit": scene_limit,
        "candidates": [
            {"coarse_step_rad": float(step), **sweep_plan(coarse_step_rad=step, geometry=seal)}
            for step in candidates
        ],
        "model": {
            "candidate_id": frozen.get("candidate_id"),
            "weights_sha256": weights_sha256,
            "min_confidence": float(min_confidence),
            "tracking_iou": float(tracking_iou),
        },
        "split": split,
        "domain": domain,
        "match_radius_px": float(match_radius_px),
    }


def _unique_stops(candidates: Sequence[Mapping]) -> list[float]:
    """Every stop angle the candidates command, once, in a stable order."""

    angles: list[float] = []
    for candidate in candidates:
        for anchor in candidate["anchors"]:
            for target in anchor["targets_rad"]:
                if not any(
                    math.isclose(target, known, rel_tol=0.0, abs_tol=STOP_TOLERANCE_RAD)
                    for known in angles
                ):
                    angles.append(float(target))
    return angles


def _cached(cache: Mapping[float, Mapping], angle: float) -> Mapping:
    for known, record in cache.items():
        if math.isclose(float(angle), float(known), rel_tol=0.0, abs_tol=STOP_TOLERANCE_RAD):
            return record
    raise ValueError(f"the stop {angle} was never measured")


def measure_coarse_step_val_sweep(
    *,
    geometry_seal_path,
    dataset_manifest_path,
    dataset_config_path,
    weights_path,
    frozen_candidate_path,
    output_dir,
    split=SPLIT,
    domain=DOMAIN,
    scene_limit=None,
    passes=1,
    device="cuda",
    command=None,
) -> dict:
    """Measure the real val sweep and write the raw observations and the decision.

    This is the only measuring code in the calibration: it rebuilds every head val scene the way the
    dataset generator did (the accepted deterministic attempt, checked against the dataset's own image),
    walks the bounded stop points of every generated candidate step with the selected model's operating
    point, and records the per-camera ground truth and the detections of every stop. It commands no
    motion: the neck angle is a simulated scene state, not a controller target. The caller's brand-new
    output directory is claimed before anything is measured, and the three documents are written into it
    only once the whole sweep succeeded: the raw observations, the decision, and the receipt that records
    what ran and what it consumed.
    """

    import mujoco
    import numpy as np
    from so101_demo.act.head_search_calibration_geometry import read_geometry_document
    from ultralytics import YOLO

    started = time.time()
    geometry_path = Path(geometry_seal_path)
    manifest_path = Path(dataset_manifest_path)
    config_path = Path(dataset_config_path)
    weights = Path(weights_path)
    output = Path(output_dir)
    for path in (geometry_path, manifest_path, config_path, weights):
        if not path.is_file():
            raise FileNotFoundError(f"the sweep needs {path}")
    try:
        output.mkdir(parents=True)
    except FileExistsError as error:
        raise _refuse(
            CAL_SWEEP_EVIDENCE_CONTRADICTORY,
            f"{output} exists; a measurement is never resumed, continued or overwritten",
        ) from error

    seal_document = json.loads(geometry_path.read_text(encoding="utf-8"))
    read_geometry_document(seal_document)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    frozen_document = load_selected_candidate(frozen_candidate_path)
    weights_digest = hashlib.sha256(weights.read_bytes()).hexdigest()

    from so101_demo.adapters.perception.mujoco_dataset import (
        DatasetScenario,
        MuJoCoDatasetRenderer,
        load_dataset_config,
        verify_head_search_manifest,
    )

    config = load_dataset_config(
        config_path,
        generator_commit=manifest.get("generator_commit"),
        sample_limit=None,
    )
    counted = dict(config.split_counts)
    verify_head_search_manifest(
        manifest,
        dataset_root=manifest_path.parent,
        geometry_seal=seal_document,
        expected_train=counted["train"],
        expected_val=counted["val"],
        expected_test=counted["test"],
    )
    plan = plan_coarse_step_val_sweep(
        geometry_seal=seal_document,
        dataset_manifest=manifest,
        frozen_candidate=frozen_document,
        weights_sha256=weights_digest,
        split=split,
        domain=domain,
        scene_limit=scene_limit,
    )
    samples = {
        int(sample["seed"]): sample
        for sample in manifest["samples"]
        if sample.get("split") == split
    }
    candidates = plan["candidates"]
    angles = _unique_stops(candidates)
    camera_name = seal_document.get("camera_name")
    renderer = MuJoCoDatasetRenderer(config)
    try:
        neck = mujoco.mj_name2id(renderer._model, mujoco.mjtObj.mjOBJ_JOINT, "neck_yaw_joint")
        if neck < 0:
            raise _refuse(
                CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                "the sealed scene has no neck_yaw_joint, so no bounded stop can be measured",
            )
        address = int(renderer._model.jnt_qposadr[neck])
        camera = mujoco.mj_name2id(renderer._model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
        if camera < 0:
            raise _refuse(
                CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                f"the sealed scene has no camera {camera_name!r}",
            )
        body_of_geom = {
            geom: int(renderer._model.geom_bodyid[geom]) for geom in range(renderer._model.ngeom)
        }
        body_name = {
            body: mujoco.mj_id2name(renderer._model, mujoco.mjtObj.mjOBJ_BODY, body)
            for body in set(body_of_geom.values())
        }
        cup_bodies = sorted(
            body for body, name in body_name.items() if name and "cup" in name.lower()
        )
        geoms_of_body = {
            body: [geom for geom, owner in body_of_geom.items() if owner == body]
            for body in cup_bodies
        }

        def segmentation() -> np.ndarray:
            segmentation_renderer = renderer._segmentation_renderer
            segmentation_renderer.enable_segmentation_rendering()
            try:
                segmentation_renderer.update_scene(renderer._data, camera=camera)
                return renderer._geom_ids(np.array(segmentation_renderer.render(), copy=True))
            finally:
                segmentation_renderer.disable_segmentation_rendering()

        def truth_of(segmentation_image) -> list[dict]:
            records = []
            for body in cup_bodies:
                ys, xs = np.nonzero(np.isin(segmentation_image, geoms_of_body[body]))
                if xs.size:
                    records.append(
                        {
                            "body": body_name[body],
                            "body_id": int(body),
                            "x": float(xs.mean()),
                            "y": float(ys.mean()),
                            "visible_px": int(xs.size),
                        }
                    )
            return records

        model = YOLO(str(weights))
        min_confidence = plan["model"]["min_confidence"]
        tracking_iou = plan["model"]["tracking_iou"]
        measured: dict[int, dict] = {}
        reconstructions = []
        predictions = 0
        for scene in plan["scenes"]:
            sample = samples[scene["scene_id"]]
            renderer.render(int(scene["scene_id"]), DatasetScenario(scene["scenario"]))
            if renderer._neck_rad != scene["neck_rad"]:
                raise _refuse(
                    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                    f"the val scene {scene['scene_id']} reconstructs at the neck angle "
                    f"{renderer._neck_rad!r} but the dataset rendered it at {scene['neck_rad']!r}; the "
                    f"sweep would measure a scene the dataset never held",
                )
            renderer._data.qpos[address] = float(scene["neck_rad"])
            mujoco.mj_forward(renderer._model, renderer._data)
            renderer._renderer.update_scene(renderer._data, camera=camera)
            reference = np.array(renderer._renderer.render(), copy=True)
            difference = _image_difference(reference, manifest_path.parent / sample["image"])
            reconstructions.append(
                {"scene_id": scene["scene_id"], "max_abs_pixel_difference": difference}
            )
            if difference is None or difference > RECONSTRUCTION_PIXEL_TOLERANCE:
                raise _refuse(
                    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
                    f"the val scene {scene['scene_id']} does not reconstruct to the dataset's own image "
                    f"(max abs pixel difference {difference!r} > {RECONSTRUCTION_PIXEL_TOLERANCE}); the "
                    f"sweep would measure a scene the dataset does not hold",
                )
            per_pass = []
            for _index in range(passes):
                cache: dict[float, dict] = {}
                for angle in angles:
                    renderer._data.qpos[address] = float(angle)
                    mujoco.mj_forward(renderer._model, renderer._data)
                    truth = truth_of(segmentation())
                    renderer._renderer.update_scene(renderer._data, camera=camera)
                    image = np.array(renderer._renderer.render(), copy=True)
                    result = model.predict(
                        image,
                        conf=float(min_confidence),
                        iou=float(tracking_iou),
                        device=device,
                        verbose=False,
                    )
                    predictions += 1
                    boxes = getattr(result[0], "boxes", None)
                    cache[float(angle)] = {
                        "truth": truth,
                        "detections": [
                            {
                                "x": float(box.xywh[0][0]),
                                "y": float(box.xywh[0][1]),
                                "conf": float(box.conf),
                            }
                            for box in (boxes if boxes is not None else [])
                        ],
                        "image_sha256": hashlib.sha256(image.tobytes()).hexdigest(),
                    }
                per_pass.append(cache)
            measured[int(scene["scene_id"])] = {
                "declared_visible_instances": int(scene["visible_instance_count"]),
                "passes": per_pass,
            }
    finally:
        renderer.close()

    raw_candidates = []
    for candidate in candidates:
        if not candidate["covers_required_domain"]:
            raw_candidates.append(
                {
                    "coarse_step_rad": candidate["coarse_step_rad"],
                    "anchors": [],
                    "scenes": [],
                }
            )
            continue
        scenes = []
        for scene in plan["scenes"]:
            record = measured[scene["scene_id"]]
            scene_passes = []
            for index, cache in enumerate(record["passes"]):
                stops = []
                for anchor in candidate["anchors"]:
                    for stop_index, target in enumerate(anchor["targets_rad"]):
                        outcome = _cached(cache, target)
                        stops.append(
                            {
                                "anchor": anchor["anchor"],
                                "stop_index": stop_index,
                                "stop_rad": float(target),
                                "truth": outcome["truth"],
                                "detections": outcome["detections"],
                                "image_sha256": outcome["image_sha256"],
                            }
                        )
                scene_passes.append({"pass_index": index, "stops": stops})
            scenes.append(
                {
                    "scene_id": scene["scene_id"],
                    "scene_group_id": scene["scene_group_id"],
                    "scenario": scene["scenario"],
                    "dataset_visible_instances": record["declared_visible_instances"],
                    "passes": scene_passes,
                }
            )
        raw_candidates.append(
            {
                "coarse_step_rad": candidate["coarse_step_rad"],
                "anchors": [
                    {
                        "anchor": anchor["anchor"],
                        "anchor_rad": anchor["anchor_rad"],
                        "targets_rad": list(anchor["targets_rad"]),
                    }
                    for anchor in candidate["anchors"]
                ],
                "scenes": scenes,
            }
        )
    differences = [record["max_abs_pixel_difference"] for record in reconstructions]
    raw_document = {
        "schema_version": SCHEMA_VERSION,
        "kind": KIND,
        "phase": PHASE,
        "domain": domain,
        "split": split,
        "match_radius_px": plan["match_radius_px"],
        "passes": passes,
        "geometry": {
            "path": str(geometry_path),
            "sha256": hashlib.sha256(geometry_path.read_bytes()).hexdigest(),
            "seal_sha256": seal_document.get("seal_sha256"),
            "horizontal_fov_rad": plan["geometry"]["horizontal_fov_rad"],
            "lock_valid_neck_rad": list(plan["geometry"]["lock_valid_neck_rad"]),
            "required_search_domain_rad": list(
                plan["geometry"]["required_search_domain_rad"]
            ),
            "anchors_rad": dict(plan["geometry"]["anchors_rad"]),
        },
        "model": {
            "candidate_id": frozen_document.get("candidate_id"),
            "frozen_candidate_path": str(Path(frozen_candidate_path)),
            "frozen_candidate_sha256": hashlib.sha256(
                Path(frozen_candidate_path).read_bytes()
            ).hexdigest(),
            "weights_path": str(weights),
            "weights_sha256": weights_digest,
            "min_confidence": plan["model"]["min_confidence"],
            "tracking_iou": plan["model"]["tracking_iou"],
        },
        "dataset": {
            "manifest_path": str(manifest_path),
            "manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
            "generator_commit": manifest.get("generator_commit"),
            "geometry_seal_sha256": manifest.get("geometry_seal_sha256"),
            "camera_name": manifest.get("camera_name"),
            "split": split,
            "scene_count": len(plan["scenes"]),
            "scene_limit": plan["scene_limit"],
            "scene_ids": [scene["scene_id"] for scene in plan["scenes"]],
            "scenes_verified_against_the_dataset_images": len(reconstructions),
            "max_abs_pixel_difference": max(differences) if differences else None,
            "reconstruction_pixel_tolerance": RECONSTRUCTION_PIXEL_TOLERANCE,
        },
        "candidates": raw_candidates,
        "path": str(output / "coarse-step-observations.json"),
    }
    raw_document["sha256"] = canonical_sha256(
        {key: value for key, value in raw_document.items() if key != "sha256"}
    )
    raw_path = output / "coarse-step-observations.json"
    raw_path.write_text(json.dumps(raw_document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    decision = validate_head_search_coarse_step_measurement(
        geometry=plan["geometry"],
        observations=raw_document,
        selected_weights_sha256=weights_digest,
        output_path=output / "coarse-step-measurement.json",
    )
    receipt = {
        "schema_version": SCHEMA_VERSION,
        "kind": "head_search_coarse_step_measurement_receipt",
        "phase": PHASE,
        "status": "SUCCEEDED",
        "command": command,
        "split": split,
        "domain": domain,
        "scene_count": len(plan["scenes"]),
        "scene_limit": plan["scene_limit"],
        "candidate_count": len(candidates),
        "stop_angles": len(angles),
        "passes": passes,
        "detector_predictions": predictions,
        "scenes_verified_against_the_dataset_images": len(reconstructions),
        "max_abs_pixel_difference": max(differences) if differences else None,
        "chosen_coarse_step_rad": decision["chosen_coarse_step_rad"],
        "observations_path": str(raw_path),
        "observations_sha256": raw_document["sha256"],
        "measurement_path": str(output / "coarse-step-measurement.json"),
        "elapsed_s": time.time() - started,
        "runtime_identity": runtime_identity(
            weights=weights, weights_sha256=weights_digest, output_dir=output, device=device
        ),
        "motion_commanded": False,
    }
    (output / "measurement-receipt.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return {"observations": raw_document, "measurement": decision, "receipt": receipt}


def _image_difference(rendered, image_path) -> int | None:
    """The largest per-channel difference between a rendered frame and the dataset's own image."""

    import cv2
    import numpy as np

    path = Path(image_path)
    if not path.is_file():
        return None
    stored = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if stored is None:
        return None
    stored = cv2.cvtColor(stored, cv2.COLOR_BGR2RGB)
    if stored.shape != rendered.shape:
        return None
    return int(np.abs(rendered.astype(int) - stored.astype(int)).max())


def runtime_identity(*, weights, weights_sha256, output_dir, device) -> dict:
    """What the measurement ran as: versions, module path and the weights it measured."""

    import mujoco
    import so101_demo
    import torch
    import ultralytics

    properties = None
    if torch.cuda.is_available():
        properties = torch.cuda.get_device_properties(0)
    return {
        "python_executable": sys.executable,
        "so101_demo_module_path": str(Path(so101_demo.__file__).resolve()),
        "mujoco_version": mujoco.__version__,
        "torch_version": torch.__version__,
        "cuda_version": torch.version.cuda,
        "driver_version": _driver_version(),
        "gpu_name": properties.name if properties is not None else None,
        "ultralytics_version": ultralytics.__version__,
        "device": device,
        "weights_path": str(weights),
        "weights_sha256": weights_sha256,
        "output_dir": str(output_dir),
        "mujoco_only": True,
        "ros_nodes_started": False,
        "motion_commanded": False,
    }


def parse_driver_version(text: str) -> str | None:
    """The NVIDIA driver version out of `/proc/driver/nvidia/version`, or None when it names none.

    The kernel module line reads `NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  595.84
    Release Build ...` on this host, so the version is the first dotted number after the `NVRM version:`
    label; the older `Kernel Module  <version>` spelling is read too. A file that names no version leaves
    the identity field None rather than inventing one.
    """

    for pattern in (
        r"NVRM version:.*?\b(\d+\.\d+(?:\.\d+)?)\b",
        r"Kernel Module\s+(\d+\.\d+(?:\.\d+)?)",
    ):
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    return None


def _driver_version() -> str | None:
    """The NVIDIA kernel module version, read from the host; None when it cannot be read."""

    path = Path("/proc/driver/nvidia/version")
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    return parse_driver_version(text)
