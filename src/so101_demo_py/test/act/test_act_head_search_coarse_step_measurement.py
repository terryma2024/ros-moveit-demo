"""The coarse-step val sweep: the raw observations, the decision and the evidence phase 6 needs.

Every fixture here is synthetic: no ROS, no MuJoCo, no detector, no GPU and no motion. The raw
observations are built the way a real sweep records them - one entry per val scene per generated
candidate step, per anchor and per bounded stop, carrying that stop's per-camera ground truth and the
selected model's detections - and the module under test derives the outcome itself. The tests pin the
choice rule of design section 7.1 (`coarse_step_rad` is the largest candidate at most half a field of
view whose bounded two-way sweep covers the required domain and misses no required-visible val cup), the
refusals (missing, partial, contradictory, unstable), the determinism of the decision, and the evidence
block phase 8 consumes.

The plan the fixture lays out is the repository's own planner, `bounded_search_stops`: the module refuses
stops that are not the bounded plan of that candidate, so a fixture that invented its stops would be
refused - which one of these tests asserts on purpose.
"""

from __future__ import annotations

import json

import pytest
from so101_demo.act.head_search_calibration_bundle import (
    CAL_EFFECTIVE_VALUE_MISMATCH,
    PARAMETER_EVIDENCE_KEYS,
)
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_coarse_step_measurement import (
    CAL_SWEEP_EVIDENCE_CONTRADICTORY,
    CAL_SWEEP_EVIDENCE_MISSING,
    CAL_SWEEP_EVIDENCE_PARTIAL,
    CAL_SWEEP_UNSTABLE,
    DOMAIN,
    KIND,
    MATCH_RADIUS_PX,
    MEASUREMENT_KIND,
    PARAMETER,
    PHASE,
    REFUSAL_CODES,
    SPLIT,
    UNIT,
    CalibrationCoarseStepRefused,
    choose_coarse_step_rad,
    load_selected_candidate,
    match_stop,
    parse_driver_version,
    plan_coarse_step_val_sweep,
    sweep_plan,
    validate_head_search_coarse_step_measurement,
)
from so101_demo.act.head_search_domain import HeadSearchDomainError, bounded_search_stops
from so101_demo.act.head_search_operating_point import CAL_SPLIT_LEAK, _metrics
from so101_demo.perception_benchmark.contracts import canonical_sha256

SHA_GEOMETRY = "1" * 64
SHA_WEIGHTS = "3" * 64
OBSERVATIONS_PATH = "/evidence/coarse-step-observations.json"
GEOMETRY_PATH = "/evidence/head-camera-geometry.json"

#: the sealed camera geometry the Task 11 campaign measured (HS-290), and its three anchors
GEOMETRY = {
    "horizontal_fov_rad": 1.3121067481206794,
    "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
    "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
    "sealed_coarse_step_candidate_rad": 0.3,
    "anchors_rad": {"default": 0.1, "left": 0.0, "forward": 0.0},
}
#: the six generated candidates of that geometry, largest first (HS-290)
CANDIDATES = (
    0.6560533740603397,
    0.32802668703016985,
    0.3,
    0.16401334351508493,
    0.08200667175754246,
    0.04100333587877123,
)
LARGEST = CANDIDATES[0]
SECOND = CANDIDATES[1]
SMALLEST = CANDIDATES[-1]

#: four val scenes: one cup, no cup, two cups and one cup beside the bottle
SCENES = (
    {
        "scene_id": 410000,
        "scene_group_id": "scene-004100000",
        "scenario": "one_cup_distractors",
        "dataset_visible_instances": 1,
        "cups": ("plastic_cup",),
    },
    {
        "scene_id": 410001,
        "scene_group_id": "scene-004100001",
        "scenario": "no_cup",
        "dataset_visible_instances": 0,
        "cups": (),
    },
    {
        "scene_id": 410002,
        "scene_group_id": "scene-004100002",
        "scenario": "two_cups",
        "dataset_visible_instances": 2,
        "cups": ("plastic_cup", "plastic_cup_b"),
    },
    {
        "scene_id": 410003,
        "scene_group_id": "scene-004100003",
        "scenario": "cup_near_bottle",
        "dataset_visible_instances": 1,
        "cups": ("plastic_cup",),
    },
)
FIRST_SCENE = SCENES[0]["scene_id"]
NO_CUP_SCENE = 410001
TWO_CUP_SCENE = 410002
LAST_SCENE = SCENES[-1]["scene_id"]

BODY_CENTRES = {"plastic_cup": (100.0, 100.0), "plastic_cup_b": (200.0, 120.0)}

#: a domain no generated candidate can reach from its anchor: the safe interval plus half a field of view
#: ends at +/- 2.2 rad, and the required domain reaches +/- 3.0
UNCOVERABLE_GEOMETRY = {
    **GEOMETRY,
    "lock_valid_neck_rad": [-2.0, 2.0],
    "required_search_domain_rad": [-3.0, 3.0],
    "anchors_rad": {"default": 0.0},
}


def plan_of(step, *, anchor, geometry=GEOMETRY):
    """The repository's own bounded plan for one candidate and one anchor."""

    return bounded_search_stops(
        anchor_rad=geometry["anchors_rad"][anchor],
        required_domain_rad=geometry["required_search_domain_rad"],
        safe_interval_rad=geometry["lock_valid_neck_rad"],
        horizontal_fov_rad=geometry["horizontal_fov_rad"],
        coarse_step_rad=step,
    )


def _stop_truth(cups):
    return [
        {
            "body": body,
            "body_id": 13 + index,
            "x": BODY_CENTRES[body][0],
            "y": BODY_CENTRES[body][1],
            "visible_px": 8000 - 100 * index,
        }
        for index, body in enumerate(cups)
    ]


def _stop_detections(cups):
    """The selected model's detections at one stop: one per truly visible cup, in reverse confidence
    order, so the module's own confidence ordering (the gate's) is what the matcher has to apply."""

    detections = [
        {"x": BODY_CENTRES[body][0] + 0.2, "y": BODY_CENTRES[body][1] + 0.2, "conf": 0.9 - 0.05 * index}
        for index, body in enumerate(cups)
    ]
    return list(reversed(detections))


def observations_document(
    *,
    geometry=GEOMETRY,
    scenes=SCENES,
    steps=CANDIDATES,
    missed=(),
    passes=1,
    split=SPLIT,
    domain=DOMAIN,
    weights_sha256=SHA_WEIGHTS,
    digest=True,
    anchor_names=None,
    visible=None,
):
    """A synthetic raw sweep: every candidate step measured on every val scene, per bounded stop.

    `missed` names `(coarse_step_rad, scene_id)` pairs whose cup is truly in the camera at that candidate's
    stops but never detected - the "missed sweep" the design's failure condition is about. `visible`
    overrides the dataset's declared visible-instance count per scene id. A candidate whose bounded plan
    cannot even be built is recorded with no anchors and no scenes, because there is nothing to measure
    there. The document self-declares its path and the canonical digest of its own body, exactly as the
    producer writes it.
    """

    anchors = list(geometry["anchors_rad"]) if anchor_names is None else list(anchor_names)
    missed = {(float(step), int(scene_id)) for step, scene_id in missed}
    visible = {} if visible is None else dict(visible)
    candidates = []
    for step in steps:
        plans = {}
        for name in anchors:
            try:
                plans[name] = plan_of(step, anchor=name, geometry=geometry)
            except HeadSearchDomainError:
                plans = {}
                break
        records = []
        for scene in scenes:
            declared = visible.get(scene["scene_id"], scene["dataset_visible_instances"])
            if not plans:
                break
            scene_passes = []
            for pass_index in range(passes):
                stops = []
                for name in anchors:
                    for index, target in enumerate(plans[name].targets_rad):
                        cups = scene["cups"]
                        if not cups and declared > 0:
                            cups = ("plastic_cup",)
                        truth = _stop_truth(cups)
                        detections = (
                            []
                            if (float(step), int(scene["scene_id"])) in missed
                            else _stop_detections(cups)
                        )
                        stops.append(
                            {
                                "anchor": name,
                                "stop_index": index,
                                "stop_rad": float(target),
                                "truth": truth,
                                "detections": detections,
                                "image_sha256": canonical_sha256(
                                    {
                                        "scene": scene["scene_id"],
                                        "pass": pass_index,
                                        "stop": float(target),
                                    }
                                ),
                            }
                        )
                scene_passes.append({"pass_index": pass_index, "stops": stops})
            records.append(
                {
                    "scene_id": int(scene["scene_id"]),
                    "scene_group_id": scene["scene_group_id"],
                    "scenario": scene["scenario"],
                    "dataset_visible_instances": int(declared),
                    "passes": scene_passes,
                }
            )
        candidates.append(
            {
                "coarse_step_rad": float(step),
                "anchors": [
                    {
                        "anchor": name,
                        "anchor_rad": float(geometry["anchors_rad"][name]),
                        "targets_rad": [float(target) for target in plans[name].targets_rad],
                    }
                    for name in plans
                ],
                "scenes": records,
            }
        )
    document = {
        "schema_version": 1,
        "kind": KIND,
        "phase": PHASE,
        "domain": domain,
        "split": split,
        "match_radius_px": MATCH_RADIUS_PX,
        "passes": passes,
        "geometry": {
            "path": GEOMETRY_PATH,
            "sha256": SHA_GEOMETRY,
            "seal_sha256": "4" * 64,
            "horizontal_fov_rad": geometry["horizontal_fov_rad"],
            "lock_valid_neck_rad": list(geometry["lock_valid_neck_rad"]),
            "required_search_domain_rad": list(geometry["required_search_domain_rad"]),
            "anchors_rad": dict(geometry["anchors_rad"]),
        },
        "model": {
            "candidate_id": "C",
            "weights_sha256": weights_sha256,
            "min_confidence": 0.25,
            "tracking_iou": 0.5,
        },
        "dataset": {
            "manifest_path": "/evidence/head-dataset/dataset-manifest.json",
            "manifest_sha256": "5" * 64,
            "split": SPLIT,
            "scene_count": len(scenes),
            "scene_limit": None,
        },
        "candidates": candidates,
        "path": OBSERVATIONS_PATH,
    }
    document["sha256"] = (
        canonical_sha256({key: value for key, value in document.items() if key != "sha256"})
        if digest
        else "0" * 64
    )
    return document


def reseal(document):
    """Recompute a document's own digest after a test changed its body, as a producer would."""

    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def measurement(*, observations=None, geometry=GEOMETRY, **overrides):
    """Run the phase the way phase 6 calls it, with the references the documents declare."""

    return validate_head_search_coarse_step_measurement(
        geometry=geometry,
        observations=observations_document(geometry=geometry) if observations is None else observations,
        **overrides,
    )


# --------------------------------------------------------------------------------------------------
# the contract: what this module owns and what it refuses with
# --------------------------------------------------------------------------------------------------


def test_the_phase_owns_the_coarse_step_and_only_the_designs_val_evidence():
    assert PARAMETER == "coarse_step_rad"
    assert UNIT == "rad"
    assert DOMAIN == "head"
    assert SPLIT == "val"
    assert PHASE == "coarse_step_measurement"
    assert KIND == "head_search_coarse_step_val_sweep"
    assert MEASUREMENT_KIND == "head_search_coarse_step_measurement"
    assert MATCH_RADIUS_PX == 8.0
    assert REFUSAL_CODES == (
        CAL_SWEEP_EVIDENCE_MISSING,
        CAL_SWEEP_EVIDENCE_PARTIAL,
        CAL_SWEEP_EVIDENCE_CONTRADICTORY,
        CAL_SWEEP_UNSTABLE,
        CAL_SPLIT_LEAK,
        CAL_EFFECTIVE_VALUE_MISMATCH,
    )
    assert CalibrationCoarseStepRefused.__mro__[1] is CalibrationInputsRefused


def test_the_candidates_and_their_stops_are_the_repositorys_planner():
    plan = sweep_plan(coarse_step_rad=LARGEST, geometry=GEOMETRY)

    assert [anchor["anchor"] for anchor in plan["anchors"]] == ["default", "left", "forward"]
    for anchor in plan["anchors"]:
        planned = plan_of(LARGEST, anchor=anchor["anchor"])
        assert anchor["targets_rad"] == [float(target) for target in planned.targets_rad]
        assert anchor["anchor_rad"] == planned.anchor_rad
        assert anchor["stop_count"] == len(planned.targets_rad)
    assert plan["covers_required_domain"] is True
    assert plan["independent_sweep_check"]["checked"] is True
    assert plan["stop_count"] == sum(
        len(plan_of(LARGEST, anchor=name).targets_rad) for name in GEOMETRY["anchors_rad"]
    )


def test_a_domain_the_safe_interval_cannot_reach_has_no_plan_and_says_why():
    plan = sweep_plan(coarse_step_rad=0.2, geometry=UNCOVERABLE_GEOMETRY)

    assert plan["covers_required_domain"] is False
    assert plan["anchors"] == []
    assert plan["stop_count"] == 0
    assert "safe neck interval" in plan["reason"]


def test_the_stop_matcher_is_the_gates_greedy_nearest_rule():
    """The same frame through phase 3's own matcher agrees, so the two cannot drift apart."""

    truths = [{"x": 100.0, "y": 100.0}, {"x": 200.0, "y": 120.0}]
    # recorded in the model's order, so the matcher has to apply the gate's confidence order itself
    detections = [{"x": 260.0, "y": 120.0, "conf": 0.8}, {"x": 100.2, "y": 100.2, "conf": 0.9}]
    matched = match_stop(truth=truths, detections=detections, radius_px=MATCH_RADIUS_PX)
    cells = _metrics(
        [
            {
                "domain": "head",
                "truth": truths,
                "detections": {"C": detections},
                "match_radius_px": MATCH_RADIUS_PX,
            }
        ],
        "C",
        {"min_confidence": 0.0, "tracking_iou": 0.0, "min_bbox_aspect": 0.0, "min_area_px2": 0.0},
    )

    assert matched["true_positive"] == cells["true_positive"] == 1
    assert matched["false_positive"] == cells["false_positive"] == 1
    assert matched["matched_truth"] == [0]
    assert matched["missed_truth"] == [1]


# --------------------------------------------------------------------------------------------------
# the choice rule of design section 7.1
# --------------------------------------------------------------------------------------------------


def test_the_largest_candidate_with_clean_val_evidence_is_chosen():
    document = measurement()

    assert document["chosen_coarse_step_rad"] == LARGEST
    assert document["coarse_step_rad"] == LARGEST
    block = document["parameter_evidence"][PARAMETER]
    assert tuple(block) == PARAMETER_EVIDENCE_KEYS
    assert block["value"] == LARGEST
    assert block["unit"] == "rad"
    assert block["value"] <= GEOMETRY["horizontal_fov_rad"] / 2.0
    assert [reference["path"] for reference in block["input_evidence"]] == [
        GEOMETRY_PATH,
        OBSERVATIONS_PATH,
    ]
    assert document["candidates"][0]["coarse_step_rad"] == LARGEST
    assert document["candidates"][0]["eligible"] is True
    assert document["candidates"][0]["missed_scenes"] == []


def test_a_missed_cup_on_the_largest_candidate_chooses_the_next_largest():
    document = measurement(observations=observations_document(missed=[(LARGEST, TWO_CUP_SCENE)]))

    assert document["chosen_coarse_step_rad"] == SECOND
    chosen = document["candidates"][0]
    assert chosen["coarse_step_rad"] == LARGEST
    assert chosen["eligible"] is False
    assert chosen["missed_scenes"] == [TWO_CUP_SCENE]
    assert chosen["missed_cups"] == ["plastic_cup", "plastic_cup_b"]
    assert document["candidates"][1]["eligible"] is True


def test_a_scene_the_dataset_declares_empty_is_not_required_visible():
    """A no-cup scene has nothing to lock: a sweep that finds nothing there missed nothing."""

    document = measurement(observations=observations_document(missed=[(LARGEST, NO_CUP_SCENE)]))

    assert document["chosen_coarse_step_rad"] == LARGEST
    no_cup = next(
        record for record in document["candidates"][0]["scenes"] if record["scene_id"] == NO_CUP_SCENE
    )
    assert no_cup["required_visible"] is False
    assert no_cup["missed_cups"] == []
    assert no_cup["detections"] == 0


def test_a_cup_visible_in_the_camera_but_never_detected_is_a_missed_scene():
    """The sweep's own stops may see a cup in a scene the dataset declares empty; that is a miss."""

    document = measurement(
        observations=observations_document(
            missed=[(LARGEST, NO_CUP_SCENE)], visible={NO_CUP_SCENE: 1}
        )
    )

    assert document["chosen_coarse_step_rad"] == SECOND
    no_cup = next(
        record for record in document["candidates"][0]["scenes"] if record["scene_id"] == NO_CUP_SCENE
    )
    assert no_cup["required_visible"] is True
    assert no_cup["missed_cups"] == ["plastic_cup"]


def test_a_cup_first_detected_at_a_later_stop_still_locks_and_records_where():
    observations = observations_document()
    scene = observations["candidates"][0]["scenes"][0]
    stops = scene["passes"][0]["stops"]
    assert len(stops) > 1
    for stop in stops[:-1]:
        stop["detections"] = []
    reseal(observations)

    document = measurement(observations=observations)

    assert document["chosen_coarse_step_rad"] == LARGEST
    record = next(
        item for item in document["candidates"][0]["scenes"] if item["scene_id"] == FIRST_SCENE
    )
    assert record["required_visible"] is True
    assert record["missed_cups"] == []
    assert record["first_lock_stop_index"] == len(stops) - 1
    assert document["candidates"][0]["worst_case_first_lock_stop"] == len(stops) - 1


def test_no_candidate_that_covers_the_domain_locks_every_val_cup_and_refuses_unstable():
    observations = observations_document(missed=[(step, TWO_CUP_SCENE) for step in CANDIDATES])

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations)

    assert refused.value.code == CAL_SWEEP_UNSTABLE
    assert "missed" in refused.value.detail
    assert str(TWO_CUP_SCENE) in refused.value.detail
    assert f"{SMALLEST}" in refused.value.detail


def test_a_domain_no_generated_candidate_can_cover_refuses_unstable_with_the_reason():
    observations = observations_document(geometry=UNCOVERABLE_GEOMETRY, anchor_names=["default"])

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations, geometry=UNCOVERABLE_GEOMETRY)

    assert refused.value.code == CAL_SWEEP_UNSTABLE
    assert "safe neck interval" in refused.value.detail


def test_every_candidate_step_is_verdict_recorded_even_when_it_loses():
    document = measurement(observations=observations_document(missed=[(LARGEST, TWO_CUP_SCENE)]))

    assert [record["coarse_step_rad"] for record in document["candidates"]] == list(CANDIDATES)
    assert [record["eligible"] for record in document["candidates"]] == [
        False,
        True,
        True,
        True,
        True,
        True,
    ]
    assert document["chosen_index"] == 1


def test_the_decision_is_deterministic_and_does_not_depend_on_the_scene_order():
    first = measurement()
    shuffled = observations_document()
    shuffled["candidates"][0]["scenes"] = list(reversed(shuffled["candidates"][0]["scenes"]))
    shuffled["sha256"] = canonical_sha256(
        {key: value for key, value in shuffled.items() if key != "sha256"}
    )
    second = measurement(observations=shuffled)

    assert first["chosen_coarse_step_rad"] == second["chosen_coarse_step_rad"]
    assert first["candidates"][0]["missed_scenes"] == second["candidates"][0]["missed_scenes"]


def test_repeated_passes_that_agree_are_accepted_and_counted():
    document = measurement(observations=observations_document(passes=2))

    assert document["passes"] == 2
    assert document["chosen_coarse_step_rad"] == LARGEST
    assert all(record["passes_agree"] is True for record in document["candidates"])


def test_choosing_is_the_decision_the_phase_records():
    observations = observations_document(missed=[(LARGEST, TWO_CUP_SCENE)])
    chosen = choose_coarse_step_rad(geometry=GEOMETRY, observations=observations)
    document = measurement(observations=observations)

    assert chosen["chosen_coarse_step_rad"] == SECOND
    assert chosen["candidates"] == document["candidates"]


# --------------------------------------------------------------------------------------------------
# the refusals: missing, partial, contradictory
# --------------------------------------------------------------------------------------------------


def test_evidence_that_is_absent_or_empty_is_refused_as_missing():
    for document in (
        {},
        {"kind": KIND},
        {"kind": KIND, "candidates": []},
        observations_document(scenes=()),
    ):
        with pytest.raises(CalibrationCoarseStepRefused) as refused:
            measurement(observations=document)
        assert refused.value.code == CAL_SWEEP_EVIDENCE_MISSING


def test_a_generated_candidate_step_that_was_not_measured_is_refused_as_partial():
    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations_document(steps=CANDIDATES[:-1]))

    assert refused.value.code == CAL_SWEEP_EVIDENCE_PARTIAL
    assert f"{SMALLEST}" in refused.value.detail


def test_a_candidate_measured_on_a_different_scene_set_is_refused_as_partial():
    observations = observations_document()
    observations["candidates"][1]["scenes"] = observations["candidates"][1]["scenes"][:-1]
    reseal(observations)

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations)

    assert refused.value.code == CAL_SWEEP_EVIDENCE_PARTIAL
    assert str(LAST_SCENE) in refused.value.detail


def test_a_missing_anchor_is_refused_as_partial():
    observations = observations_document()
    observations["candidates"][0]["anchors"] = observations["candidates"][0]["anchors"][:1]
    reseal(observations)

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations)

    assert refused.value.code == CAL_SWEEP_EVIDENCE_PARTIAL
    assert "forward" in refused.value.detail


def test_a_missing_stop_is_refused_as_partial():
    observations = observations_document()
    for record in observations["candidates"][0]["scenes"]:
        record["passes"][0]["stops"] = record["passes"][0]["stops"][:-1]
    reseal(observations)

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations)

    assert refused.value.code == CAL_SWEEP_EVIDENCE_PARTIAL


def test_stops_that_are_not_the_bounded_plan_are_refused_as_contradictory():
    observations = observations_document()
    observations["candidates"][0]["scenes"][0]["passes"][0]["stops"][0]["stop_rad"] += 0.01
    reseal(observations)

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations)

    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY
    assert "bounded" in refused.value.detail


def test_a_declared_plan_that_is_not_the_repositorys_planner_is_refused_as_contradictory():
    observations = observations_document()
    observations["candidates"][0]["anchors"][0]["targets_rad"] = [0.0, 0.5]
    reseal(observations)

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations)

    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY


def test_repeated_passes_that_disagree_are_refused_as_contradictory():
    observations = observations_document(passes=2)
    record = observations["candidates"][0]["scenes"][0]
    for stop in record["passes"][1]["stops"]:
        stop["detections"] = []
    reseal(observations)

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations)

    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY
    assert "pass" in refused.value.detail


def test_a_document_whose_declared_digest_is_not_its_body_is_refused_as_contradictory():
    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations_document(digest=False))

    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY
    assert "digest" in refused.value.detail


def test_evidence_measured_on_another_split_is_refused_with_phase_threes_split_leak():
    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations_document(split="calibration"))

    assert refused.value.code == CAL_SPLIT_LEAK
    assert "val" in refused.value.detail


def test_evidence_measured_for_another_model_than_the_selected_one_is_refused():
    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(
            observations=observations_document(weights_sha256="9" * 64),
            selected_weights_sha256=SHA_WEIGHTS,
        )

    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY
    assert SHA_WEIGHTS in refused.value.detail


def test_an_unknown_candidate_step_is_refused_as_partial_and_a_duplicate_as_contradictory():
    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations_document(steps=(*CANDIDATES, 0.02)))
    assert refused.value.code == CAL_SWEEP_EVIDENCE_PARTIAL
    assert "0.02" in refused.value.detail

    duplicate = observations_document()
    duplicate["candidates"].append(json.loads(json.dumps(duplicate["candidates"][0])))
    reseal(duplicate)
    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=duplicate)
    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY


def test_evidence_for_another_camera_domain_is_refused_as_contradictory():
    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations_document(domain="task"))

    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY
    assert "task" in refused.value.detail


def test_the_two_documents_geometry_must_be_the_one_the_run_sealed():
    observations = observations_document()
    observations["geometry"]["horizontal_fov_rad"] = 0.4
    reseal(observations)

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(observations=observations)

    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY
    assert "horizontal_fov_rad" in refused.value.detail


def test_a_malformed_record_is_a_caller_error_without_a_refusal_code():
    observations = observations_document()
    observations["candidates"][0]["scenes"][0]["passes"][0]["stops"][0]["truth"] = "not-a-list"
    reseal(observations)

    with pytest.raises(ValueError) as refused:
        measurement(observations=observations)

    assert not isinstance(refused.value, CalibrationCoarseStepRefused)


# --------------------------------------------------------------------------------------------------
# the evidence block phase 8 consumes and the document this phase writes
# --------------------------------------------------------------------------------------------------


def test_the_block_cites_the_sealed_geometry_and_the_observations_file_with_their_digests():
    observations = observations_document()
    block = measurement(observations=observations)["parameter_evidence"][PARAMETER]

    assert {reference["path"]: reference["sha256"] for reference in block["input_evidence"]} == {
        GEOMETRY_PATH: SHA_GEOMETRY,
        OBSERVATIONS_PATH: observations["sha256"],
    }


def test_the_startup_readback_is_verified_when_reported_and_unverified_when_absent():
    absent = measurement()["parameter_evidence"][PARAMETER]["startup_readback"]
    assert absent["verified"] is False
    assert absent["observed_value"] == LARGEST

    reported = measurement(
        startup_readback={"source": "ros2 param get", "observed_value": LARGEST}
    )
    verified = reported["parameter_evidence"][PARAMETER]["startup_readback"]
    assert verified["verified"] is True
    assert verified["source"] == "ros2 param get"

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        measurement(startup_readback={"source": "ros2 param get", "observed_value": SECOND})
    assert refused.value.code == CAL_EFFECTIVE_VALUE_MISMATCH


def test_the_document_records_the_observed_distribution_and_the_margin():
    block = measurement()["parameter_evidence"][PARAMETER]

    distribution = block["observed_distribution"]
    assert distribution["scene_count"] == len(SCENES)
    assert distribution["candidate_count"] == len(CANDIDATES)
    assert distribution["measured_candidate_steps"] == list(CANDIDATES)
    assert distribution["passes"] == 1
    assert distribution["required_visible_scenes"] >= 1
    assert block["safety_margin"]["half_fov_rad"] == GEOMETRY["horizontal_fov_rad"] / 2.0
    assert block["safety_margin"]["missed_cups"] == 0
    assert block["production_owner"].startswith("so101_demo.act.search.HeadSearchController")


def test_the_phase_writes_its_document_only_where_the_caller_asks(tmp_path):
    target = tmp_path / "coarse-step-measurement.json"

    document = measurement()
    assert not target.exists()
    written = measurement(output_path=target)

    assert written == document
    assert json.loads(target.read_text(encoding="utf-8")) == document
    assert {path.name for path in tmp_path.iterdir()} == {target.name}


def test_the_module_measures_nothing_of_its_own_and_commands_no_motion():
    document = measurement()

    assert document["motion_commanded"] is False
    assert document["measured_here"] is False
    assert document["kind"] == MEASUREMENT_KIND
    assert document["observations"]["kind"] == KIND
    assert document["observations"]["sha256"] == observations_document()["sha256"]
    assert document["selection_rule"].startswith("the largest generated candidate")


# --------------------------------------------------------------------------------------------------
# the producer's preflight: what the real sweep is allowed to measure
# --------------------------------------------------------------------------------------------------


def sealed_geometry_document(*, camera_name="head_camera", **overrides):
    """A geometry seal sealed the way the campaign seals one: canonical digest of the body."""

    body = {
        "schema_version": 1,
        "kind": "head_camera_geometry",
        "camera_name": camera_name,
        "horizontal_fov_rad": GEOMETRY["horizontal_fov_rad"],
        "lock_valid_neck_rad": list(GEOMETRY["lock_valid_neck_rad"]),
        "required_search_domain_rad": list(GEOMETRY["required_search_domain_rad"]),
        "coarse_step_candidate_rad": GEOMETRY["sealed_coarse_step_candidate_rad"],
        "anchors": list(GEOMETRY["anchors_rad"]),
        "in_frame_matrix": {
            name: {"neck_start_rad": angle} for name, angle in GEOMETRY["anchors_rad"].items()
        },
    }
    body.update(overrides)
    return {**body, "seal_sha256": canonical_sha256(body)}


def dataset_manifest_document(*, seal=None, split=SPLIT, scenes=SCENES, camera_name="head_camera", **overrides):
    """The head dataset manifest as the generator writes it, cut down to the scenes that matter here."""

    seal = sealed_geometry_document() if seal is None else seal
    samples = [
        {
            "split": split,
            "seed": scene["scene_id"],
            "scenario": scene["scenario"],
            "scene_group_id": scene["scene_group_id"],
            "visible_instance_count": scene["dataset_visible_instances"],
            "camera": {"neck_rad": 0.1, "frame_id": camera_name},
            "image": f"images/{split}/{scene['scene_id']}.png",
        }
        for scene in scenes
    ]
    document = {
        "dataset_contract": "so101-head-search-yolo-seg-v1",
        "camera_name": camera_name,
        "geometry_seal_sha256": seal["seal_sha256"],
        "split_counts": {"train": 4, "val": len(samples), "test": 4},
        "generator_commit": "a" * 40,
        "samples": samples,
    }
    document.update(overrides)
    return document


def frozen_candidate_document(*, weight_sha256=SHA_WEIGHTS, domain=DOMAIN, **overrides):
    document = {
        "candidate_id": "C",
        "kind": "head-search-frozen-candidate",
        "promotable": True,
        "weight_sha256": weight_sha256,
        "operating_points": {domain: {"min_confidence": 0.25, "tracker": {"iou": 0.5}}},
    }
    document.update(overrides)
    return document


def test_the_producer_preflight_plans_every_candidate_over_the_val_scenes():
    seal = sealed_geometry_document()
    plan = plan_coarse_step_val_sweep(
        geometry_seal=seal,
        dataset_manifest=dataset_manifest_document(seal=seal),
        frozen_candidate=frozen_candidate_document(),
        weights_sha256=SHA_WEIGHTS,
    )

    assert [candidate["coarse_step_rad"] for candidate in plan["candidates"]] == list(CANDIDATES)
    assert all(candidate["covers_required_domain"] for candidate in plan["candidates"])
    assert plan["candidates"][0]["anchors"][0]["targets_rad"] == [
        float(target) for target in plan_of(LARGEST, anchor="default").targets_rad
    ]
    assert [scene["scene_id"] for scene in plan["scenes"]] == [
        scene["scene_id"] for scene in SCENES
    ]
    assert plan["scenes"][0]["neck_rad"] == 0.1
    assert plan["scenes"][0]["image"] == f"images/{SPLIT}/{FIRST_SCENE}.png"
    assert plan["model"] == {
        "candidate_id": "C",
        "weights_sha256": SHA_WEIGHTS,
        "min_confidence": 0.25,
        "tracking_iou": 0.5,
    }
    assert plan["split"] == SPLIT and plan["domain"] == DOMAIN


def test_the_producer_preflight_refuses_weights_that_are_not_the_frozen_digest():
    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        plan_coarse_step_val_sweep(
            geometry_seal=sealed_geometry_document(),
            dataset_manifest=dataset_manifest_document(),
            frozen_candidate=frozen_candidate_document(weight_sha256="9" * 64),
            weights_sha256=SHA_WEIGHTS,
        )

    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY
    assert "frozen candidate" in refused.value.detail


def test_the_producer_preflight_refuses_a_manifest_of_another_seal_or_camera():
    seal = sealed_geometry_document()
    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        plan_coarse_step_val_sweep(
            geometry_seal=seal,
            dataset_manifest=dataset_manifest_document(seal=seal, geometry_seal_sha256="7" * 64),
            frozen_candidate=frozen_candidate_document(),
            weights_sha256=SHA_WEIGHTS,
        )
    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY
    assert "seal" in refused.value.detail

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        plan_coarse_step_val_sweep(
            geometry_seal=seal,
            dataset_manifest=dataset_manifest_document(seal=seal, camera_name="task_camera"),
            frozen_candidate=frozen_candidate_document(),
            weights_sha256=SHA_WEIGHTS,
        )
    assert refused.value.code == CAL_SWEEP_EVIDENCE_CONTRADICTORY
    assert "task_camera" in refused.value.detail


def test_the_producer_preflight_refuses_a_split_with_no_scene():
    seal = sealed_geometry_document()
    manifest = dataset_manifest_document(seal=seal, split="calibration")

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        plan_coarse_step_val_sweep(
            geometry_seal=seal,
            dataset_manifest=manifest,
            frozen_candidate=frozen_candidate_document(),
            weights_sha256=SHA_WEIGHTS,
        )

    assert refused.value.code == CAL_SWEEP_EVIDENCE_MISSING
    assert SPLIT in refused.value.detail


def test_the_producer_preflight_refuses_a_frozen_candidate_without_the_domains_point():
    seal = sealed_geometry_document()

    with pytest.raises(CalibrationCoarseStepRefused) as refused:
        plan_coarse_step_val_sweep(
            geometry_seal=seal,
            dataset_manifest=dataset_manifest_document(seal=seal),
            frozen_candidate=frozen_candidate_document(domain="task"),
            weights_sha256=SHA_WEIGHTS,
        )

    assert refused.value.code == CAL_SWEEP_EVIDENCE_PARTIAL
    assert "operating point" in refused.value.detail


def test_the_producer_preflight_refuses_a_geometry_whose_seal_is_not_its_body():
    with pytest.raises(CalibrationInputsRefused) as refused:
        plan_coarse_step_val_sweep(
            geometry_seal={**sealed_geometry_document(), "seal_sha256": "0" * 64},
            dataset_manifest=dataset_manifest_document(),
            frozen_candidate=frozen_candidate_document(),
            weights_sha256=SHA_WEIGHTS,
        )

    assert refused.value.code == "CAL_INPUT_UNSEALED"


def test_the_producer_preflight_measures_only_the_scenes_the_caller_limited_it_to():
    seal = sealed_geometry_document()
    plan = plan_coarse_step_val_sweep(
        geometry_seal=seal,
        dataset_manifest=dataset_manifest_document(seal=seal),
        frozen_candidate=frozen_candidate_document(),
        weights_sha256=SHA_WEIGHTS,
        scene_limit=2,
    )

    assert [scene["scene_id"] for scene in plan["scenes"]] == [
        SCENES[0]["scene_id"],
        SCENES[1]["scene_id"],
    ]
    assert plan["scene_limit"] == 2


def test_the_producer_loads_the_selected_frozen_candidate_through_the_repositorys_loader(tmp_path):
    """The frozen document reaches the sweep through the repository's own loader, not a copy of it."""

    from so101_demo.act.head_search_candidate_freeze import freeze_candidate

    frozen_path = tmp_path / "frozen-c.json"
    freeze_candidate(
        candidate_id="C",
        weight_sha256=SHA_WEIGHTS,
        min_confidence=0.25,
        tracking_iou=0.5,
        output=frozen_path,
    )
    frozen = load_selected_candidate(frozen_path)

    assert frozen["candidate_id"] == "C"
    assert frozen["weight_sha256"] == SHA_WEIGHTS
    assert frozen["operating_points"][DOMAIN]["min_confidence"] == 0.25
    # and the plan the producer runs on is built from exactly this document
    seal = sealed_geometry_document()
    plan = plan_coarse_step_val_sweep(
        geometry_seal=seal,
        dataset_manifest=dataset_manifest_document(seal=seal),
        frozen_candidate=frozen,
        weights_sha256=SHA_WEIGHTS,
    )
    assert plan["model"]["min_confidence"] == 0.25
    assert plan["model"]["tracking_iou"] == 0.5


def test_the_driver_version_reader_understands_the_hosts_own_version_file():
    """The runtime identity records the driver the detector ran on, not an empty field."""

    line = (
        "NVRM version: NVIDIA UNIX Open Kernel Module for x86_64  595.84  Release Build  "
        "(dvs-builder@U22-I3-AM25-26-2)  Wed Jun 10 21:06:37 UTC 2026\n"
        "GCC version:  gcc version 13.3.0 (Ubuntu 13.3.0-6ubuntu2~24.04.1)\n"
    )
    assert parse_driver_version(line) == "595.84"
    assert parse_driver_version("Kernel Module  550.54.14\n") == "550.54.14"
    assert parse_driver_version("") is None
    assert parse_driver_version("no version here") is None
