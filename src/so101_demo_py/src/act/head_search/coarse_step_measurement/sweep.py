"""The sweep plan, stop matching and raw sweep validation."""

from __future__ import annotations

from collections.abc import Mapping
import math

from so101_demo.act.head_search.calibration_geometry import (
    generate_coarse_step_candidates,
)
from so101_demo.act.head_search.coarse_step_measurement.contracts import (
    _SHA256,
    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
    CAL_SWEEP_EVIDENCE_MISSING,
    CAL_SWEEP_EVIDENCE_PARTIAL,
    DIGEST_CONVENTION,
    DOMAIN,
    KIND,
    MATCH_RADIUS_PX,
    SPLIT,
    _centre,
    _confidence,
    _finite,
    _geometry,
    _mapping,
    _positive,
    _records,
    _refuse,
    _uncovered,
)
from so101_demo.act.head_search.domain import (
    HeadSearchDomainError,
    bounded_search_stops,
    coverage_is_complete,
    independent_sweep_check,
)
from so101_demo.act.head_search.operating_point import CAL_SPLIT_LEAK
from so101_demo.perception_benchmark.contracts import canonical_sha256


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
