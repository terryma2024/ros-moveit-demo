"""Phase 5 of the formal head-search calibration: the selected values carried over into the bundle.

Design section 7.2 fixes the dependency order: each candidate's perception operating point is calibrated
and frozen, the frozen candidates are evaluated and one is selected, and the selected perception
parameters are then "carried over verbatim and verified". This phase is that verification. It compares
the four perception values the bundle records (`min_confidence`, `tracking_iou`, `min_bbox_aspect` and
`min_area_px2`) against the point the phase-3 rule record chose and against the frozen candidate
document phase 3/4 sealed, with no tolerance, no rounding, no clamping and no substitution, and it
checks the candidate identity the bundle carries against the one the rule selected.

The fixtures are the real producers and not a second copy of their rules: the phase-3 record comes from
`record_selection_rule` + `validate_head_search_calibration_operating_point`, the frozen candidate from
`freeze_candidate`, and the bundle from `assemble_calibration_bundle`. Everything is synthetic and in
memory - no detector, no GPU, no MuJoCo, no ROS - and the only files written are the fixtures' own under
`tmp_path`.
"""

from __future__ import annotations

import copy
import inspect
import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_calibration_bundle import assemble_calibration_bundle
from so101_demo.act.head_search_calibration_inputs import SEALED_INPUT_NAMES
from so101_demo.act.head_search_calibration_readback import (
    CAL_SELECTION_MISMATCH,
    CAL_VALUE_MUTATED,
    DEFAULT_DOMAIN,
    KIND,
    PERCEPTION_PARAMETERS,
    PHASE,
    READBACK_NAME,
    VERDICT_IDENTICAL,
    CalibrationReadbackRefused,
    compare_selected_perception_values,
    readback_selected_perception_values,
    verify_selected_candidate_identity,
)
from so101_demo.act.head_search_candidate_freeze import freeze_candidate
from so101_demo.act.head_search_operating_point import (
    record_selection_rule,
    validate_head_search_calibration_operating_point,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

CANDIDATE_ID = "C"
WEIGHT_SHA256 = canonical_sha256({"seed": "candidate-C-weights"})
SELECTION_SPLITS = ("val", "calibration")
HELD_OUT_SPLITS = ("held_out_evaluation",)
MATCH_RADIUS_PX = 8.0
COMMAND = "ros2 run so101_demo_py so101_head_search_calibration run --run-root /evidence/run-01"

#: the four perception values in the order design section 7.1 lists them: they are the
#: first four in the dependency order, and the phase-8 bundle keeps that order too
DESIGN_PERCEPTION_PARAMETERS = (
    "min_confidence",
    "tracking_iou",
    "min_bbox_aspect",
    "min_area_px2",
)

#: the best grid point: the higher confidence floor drops the one low-confidence bystander, so it has the
#: unique best f1. Its `min_confidence` is 0.1 + 0.2 = 0.30000000000000004, a value a report that rounds
#: to fewer decimals would silently change into 0.3.
HIGH_POINT = {
    "min_confidence": 0.1 + 0.2,
    "tracking_iou": 0.6,
    "min_bbox_aspect": 1.25,
    "min_area_px2": 100.0,
}

#: the other declared point: keeping the 0.27 bystander costs it the choice (f1 = 6/7 against 1.0)
LOW_POINT = {
    "min_confidence": 0.25,
    "tracking_iou": 0.5,
    "min_bbox_aspect": 1.0,
    "min_area_px2": 64.0,
}

#: the unit design section 7.1 fixes for each of the seventeen, for the bundle fixture
UNITS = {
    "horizontal_fov_rad": "rad",
    "lock_valid_neck_rad": "rad",
    "coarse_step_rad": "rad",
    "search_timeout_s": "s",
    "min_confidence": "1",
    "tracking_iou": "1",
    "min_bbox_aspect": "1",
    "min_area_px2": "px^2",
    "center_deadband_px": "px",
    "vertical_bounds_px": "px",
    "max_fine_corrections": "1",
    "max_fine_total_rad": "rad",
    "max_age_s": "s",
    "max_skew_s": "s",
    "submit_lead_s": "s",
    "stop_velocity_rad_s": "rad/s",
    "stop_latency_s": "s",
}

#: which phase hands over which parameter (plan section 3, "Parameter to phase map")
PHASE_PARAMETERS = {
    "geometry_coverage": ("horizontal_fov_rad", "lock_valid_neck_rad"),
    "perception_operating_point": DESIGN_PERCEPTION_PARAMETERS,
    "search_parameters": (
        "coarse_step_rad",
        "search_timeout_s",
        "center_deadband_px",
        "vertical_bounds_px",
        "max_fine_corrections",
        "max_fine_total_rad",
    ),
    "timing_stop_parameters": (
        "max_age_s",
        "max_skew_s",
        "submit_lead_s",
        "stop_velocity_rad_s",
        "stop_latency_s",
    ),
}

#: the thirteen parameters phase 5 does not compare - the four perception values come from phase 3
OTHER_VALUES = {
    "horizontal_fov_rad": 1.3121067481206794,
    "lock_valid_neck_rad": [-6.28, 6.28],
    "coarse_step_rad": 0.6560533740603397,
    "search_timeout_s": 18.0,
    "center_deadband_px": 12.0,
    "vertical_bounds_px": [40.0, 440.0],
    "max_fine_corrections": 12,
    "max_fine_total_rad": 0.3,
    "max_age_s": 0.15,
    "max_skew_s": 0.03,
    "submit_lead_s": 0.02,
    "stop_velocity_rad_s": 0.01,
    "stop_latency_s": 0.25,
}


def _truth(x, y):
    return {"x": x, "y": y}


def _detection(x, y, conf):
    return {"x": x, "y": y, "conf": conf}


def _frame(split, truths, detections, *, scenario="nominal", seed=0):
    return {
        "split": split,
        "domain": "head",
        "seed": seed,
        "scenario": scenario,
        "truth": list(truths),
        "detections": {CANDIDATE_ID: list(detections)},
        "match_radius_px": MATCH_RADIUS_PX,
    }


#: three head frames over both selection splits: three ground truths, and one 0.27 bystander far from
#: every truth. The 0.25 floor keeps it as a false positive (f1 = 6/7); the 0.1 + 0.2 floor drops it
#: (f1 = 1.0), so the higher floor is the unique best point of the declared grid.
MEASUREMENTS = (
    _frame("val", [_truth(100, 100)], [_detection(100.2, 100.2, 0.90)]),
    _frame(
        "val",
        [_truth(200, 200)],
        [_detection(200.3, 200.3, 0.55), _detection(320.0, 320.0, 0.27)],
    ),
    _frame("calibration", [_truth(400, 400)], [_detection(400.4, 400.4, 0.85)]),
)


def _phase_record():
    """The phase-3 document, produced by phase 3 itself rather than by a copy of its rules."""

    rule = record_selection_rule(
        points=(LOW_POINT, HIGH_POINT),
        selection_splits=SELECTION_SPLITS,
        held_out_splits=HELD_OUT_SPLITS,
        domain="head",
    )
    document = validate_head_search_calibration_operating_point(
        rule=rule, measurements=MEASUREMENTS, candidate_id=CANDIDATE_ID
    )
    assert document["chosen_point"] == HIGH_POINT, "the fixture must choose HIGH_POINT"
    return document


def _frozen_candidate(tmp_path, record):
    """The frozen candidate document, produced by the repository's own `freeze_candidate`."""

    point = record["chosen_point"]
    return freeze_candidate(
        candidate_id=record["candidate_id"],
        weight_sha256=WEIGHT_SHA256,
        min_confidence=point["min_confidence"],
        tracking_iou=point["tracking_iou"],
        output=tmp_path / "frozen-candidate.json",
    )


def _selected_values(record):
    point = record["chosen_point"]
    return {
        **OTHER_VALUES,
        "min_confidence": point["min_confidence"],
        "tracking_iou": point["tracking_iou"],
        "min_bbox_aspect": point["min_bbox_aspect"],
        "min_area_px2": point["min_area_px2"],
    }


def _evidence(name, value):
    return {
        "value": value,
        "unit": UNITS[name],
        "selection_formula": f"the {name} rule of design 7.1",
        "input_evidence": [
            {"path": f"/evidence/{name}-campaign.json", "sha256": canonical_sha256({"n": name})}
        ],
        "observed_distribution": {"p50": 1.0, "p99": 2.0, "samples": 120},
        "safety_margin": {"bound": 1.5, "observed": 1.0},
        "production_owner": "src/so101_demo_py/src/cli/head_search_calibration.py",
        "startup_readback": {"source": "ros2 param get", "observed_value": value},
    }


def _phase_inputs(values):
    return {
        phase: {"parameters": {name: _evidence(name, values[name]) for name in names}}
        for phase, names in PHASE_PARAMETERS.items()
    }


def _runtime_identity(weights):
    return {
        "package_prefix": "/toolchain/install/so101_demo_py",
        "console_script_path": "/toolchain/install/so101_demo_py/lib/so101_head_search_calibration",
        "detector_weights_sha256": weights,
        "torch_version": "2.5.1",
        "ultralytics_version": "8.3.0",
        "cuda_version": "12.4",
        "driver_version": "550.54.14",
        "mujoco_version": "3.2.3",
        "camera_id": "head-cam-0",
        "camera_intrinsics_sha256": canonical_sha256({"seed": "intrinsics"}),
        "tracker_id": "iou-tracker-v1",
        "web_bundle_id": "web-20260930",
    }


def _controlled_dependencies():
    return {
        name: {"path": f"/sealed/{name}.json", "sha256": canonical_sha256({"sealed": name})}
        for name in SEALED_INPUT_NAMES
    }


def _also_recorded():
    definitions = {
        "settle_velocity_rad_s": 0.005,
        "goal_tolerance_rad": 0.01,
        "three_consecutive_frame_lock_rule": "locked after three consecutive frames in the deadband",
        "tracker_algorithm": "greedy nearest-within-match-radius IoU tracker",
        "frame_contract_10_hz": "head camera frames arrive at 10 Hz",
    }
    return {
        item: {
            "value_or_definition": definition,
            "input_evidence": [
                {"path": "/evidence/design-7.1.md", "sha256": canonical_sha256({"n": item})}
            ],
            "startup_readback": {"source": "startup log", "observed": definition},
        }
        for item, definition in definitions.items()
    }


def _bundle(record, *, values=None, weights=WEIGHT_SHA256):
    """The phase-8 bundle, assembled by phase 8 from the documents the calibration produces."""

    selected = _selected_values(record) if values is None else values
    result = assemble_calibration_bundle(
        status="SUCCEEDED",
        command=COMMAND,
        exit_code=0,
        phase_inputs=_phase_inputs(selected),
        controlled_dependencies=_controlled_dependencies(),
        runtime_identity=_runtime_identity(weights),
        also_recorded=_also_recorded(),
    )
    return result["bundle"]


def _fixture(tmp_path):
    record = _phase_record()
    return record, _frozen_candidate(tmp_path, record), _bundle(record)


def _refuses(code, **arguments):
    with pytest.raises(CalibrationReadbackRefused) as caught:
        readback_selected_perception_values(**arguments)
    assert caught.value.code == code
    return caught.value


def test_readback_certifies_the_selected_values_entered_the_bundle_unmodified(tmp_path):
    record, frozen, bundle = _fixture(tmp_path)

    document = readback_selected_perception_values(
        bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert document["kind"] == KIND
    assert document["phase"] == PHASE
    assert document["domain"] == DEFAULT_DOMAIN
    assert document["candidate_id"] == CANDIDATE_ID
    assert tuple(document["parameter_names"]) == DESIGN_PERCEPTION_PARAMETERS
    assert PERCEPTION_PARAMETERS == DESIGN_PERCEPTION_PARAMETERS
    point = record["chosen_point"]
    for name in DESIGN_PERCEPTION_PARAMETERS:
        row = document["parameters"][name]
        assert row["selected_value"] == point[name], name
        assert row["bundle_value"] == point[name], name
        assert row["verdict"] == VERDICT_IDENTICAL, name
    for name in ("min_confidence", "tracking_iou"):
        row = document["parameters"][name]
        assert row["frozen_candidate_declares_value"] is True, name
        assert row["frozen_candidate_value"] == point[name], name
    for name in ("min_bbox_aspect", "min_area_px2"):
        row = document["parameters"][name]
        assert row["frozen_candidate_declares_value"] is False, name
        assert row["frozen_candidate_value"] is None, name
    identity = document["identity"]
    assert identity["selected_candidate_id"] == CANDIDATE_ID
    assert identity["frozen_candidate_id"] == CANDIDATE_ID
    assert identity["bundle_weights_sha256"] == WEIGHT_SHA256
    assert identity["frozen_candidate_weights_sha256"] == WEIGHT_SHA256
    assert identity["rule_sha256"] == record["rule_sha256"]
    assert identity["operating_point_sha256"] == canonical_sha256(record)
    assert identity["frozen_candidate_sha256"] == canonical_sha256(frozen)
    assert identity["verdict"] == VERDICT_IDENTICAL
    assert document["values_unmodified"] is True
    assert document["selection_identity_matches"] is True


@pytest.mark.parametrize(
    ("name", "mutated"),
    [
        ("min_confidence", 0.35),
        ("tracking_iou", 0.9),
        ("min_bbox_aspect", 1.0),
        ("min_area_px2", 81.0),
    ],
)
def test_readback_refuses_a_bundle_value_that_is_not_the_selected_one(tmp_path, name, mutated):
    record, frozen, bundle = _fixture(tmp_path)
    bundle["parameters"][name]["value"] = mutated

    refusal = _refuses(
        CAL_VALUE_MUTATED, bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert name in refusal.detail
    assert repr(mutated) in refusal.detail
    assert repr(record["chosen_point"][name]) in refusal.detail


def test_readback_refuses_a_value_rounded_to_fewer_decimals(tmp_path):
    """The selected 0.1 + 0.2 is not 0.3: a report rounded to one decimal is a modified value."""

    record, frozen, bundle = _fixture(tmp_path)
    selected = record["chosen_point"]["min_confidence"]
    rounded = round(selected, 1)
    assert selected == 0.1 + 0.2
    assert rounded == 0.3
    assert rounded != selected
    bundle["parameters"]["min_confidence"]["value"] = rounded

    refusal = _refuses(
        CAL_VALUE_MUTATED, bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert "min_confidence" in refusal.detail
    assert f"the bundle records {rounded!r} but the rule selected {selected!r}" in refusal.detail


@pytest.mark.parametrize(
    ("name", "clamped"),
    [("min_confidence", 0.0), ("min_area_px2", 1.0)],
)
def test_readback_refuses_a_value_clamped_to_the_boundary(tmp_path, name, clamped):
    """A value clamped to its documented bound is a modified value, never a tolerated one."""

    record, frozen, bundle = _fixture(tmp_path)
    bundle["parameters"][name]["value"] = clamped

    refusal = _refuses(
        CAL_VALUE_MUTATED, bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert name in refusal.detail
    assert repr(clamped) in refusal.detail
    assert repr(record["chosen_point"][name]) in refusal.detail


@pytest.mark.parametrize("name", DESIGN_PERCEPTION_PARAMETERS)
def test_readback_refuses_a_bundle_that_does_not_carry_the_selected_value(tmp_path, name):
    record, frozen, bundle = _fixture(tmp_path)
    bundle["parameters"].pop(name)

    refusal = _refuses(
        CAL_VALUE_MUTATED, bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert name in refusal.detail
    assert repr(record["chosen_point"][name]) in refusal.detail


@pytest.mark.parametrize(
    ("name", "mutated"),
    [("min_confidence", 0.35), ("tracking_iou", 0.9)],
)
def test_readback_refuses_when_the_frozen_document_disagrees_with_the_rule_record(
    tmp_path, name, mutated
):
    record, frozen, bundle = _fixture(tmp_path)
    head = frozen["operating_points"]["head"]
    if name == "min_confidence":
        head["min_confidence"] = mutated
    else:
        head["tracker"]["iou"] = mutated

    refusal = _refuses(
        CAL_VALUE_MUTATED, bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert name in refusal.detail
    assert repr(mutated) in refusal.detail
    assert repr(record["chosen_point"][name]) in refusal.detail


@pytest.mark.parametrize("form", ["no min_confidence", "no tracker"])
def test_readback_refuses_a_frozen_document_that_does_not_seal_the_gate_values(tmp_path, form):
    """The gate substitutes its own default (0.25 / 0.5) for an undeclared value; a default is not the
    selected value, so a frozen candidate that seals neither must not be certified."""

    record, frozen, bundle = _fixture(tmp_path)
    head = frozen["operating_points"]["head"]
    if form == "no min_confidence":
        head.pop("min_confidence")
        name = "min_confidence"
    else:
        head.pop("tracker")
        name = "tracking_iou"

    refusal = _refuses(
        CAL_VALUE_MUTATED, bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert name in refusal.detail
    assert repr(record["chosen_point"][name]) in refusal.detail


def test_readback_refuses_a_frozen_candidate_that_is_not_the_selected_candidate(tmp_path):
    record, frozen, bundle = _fixture(tmp_path)
    frozen["candidate_id"] = "A"

    refusal = _refuses(
        CAL_SELECTION_MISMATCH, bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert repr("A") in refusal.detail
    assert repr(CANDIDATE_ID) in refusal.detail


@pytest.mark.parametrize("side", ["bundle", "frozen_candidate"])
def test_readback_refuses_a_weight_digest_that_is_not_the_selected_candidates(tmp_path, side):
    other = canonical_sha256({"seed": "candidate-A-weights"})
    assert other != WEIGHT_SHA256
    record, frozen, bundle = _fixture(tmp_path)
    if side == "bundle":
        bundle["runtime_identity"]["detector_weights_sha256"] = other
    else:
        frozen["weight_sha256"] = other

    refusal = _refuses(
        CAL_SELECTION_MISMATCH, bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert other in refusal.detail
    assert WEIGHT_SHA256 in refusal.detail


def test_readback_refuses_a_value_rewritten_as_an_equal_number(tmp_path):
    """`100` and `100.0` are the same quantity but not the same recorded value: the design requires the
    selected value verbatim, so a rewritten number is refused rather than certified."""

    record, frozen, bundle = _fixture(tmp_path)
    selected = record["chosen_point"]["min_area_px2"]
    assert selected == 100.0
    bundle["parameters"]["min_area_px2"]["value"] = int(selected)

    refusal = _refuses(
        CAL_VALUE_MUTATED, bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert "min_area_px2" in refusal.detail
    assert repr(selected) in refusal.detail


def test_readback_is_deterministic(tmp_path):
    record, frozen, bundle = _fixture(tmp_path)

    first = readback_selected_perception_values(
        bundle=bundle, operating_point=record, frozen_candidate=frozen
    )
    second = readback_selected_perception_values(
        bundle=copy.deepcopy(bundle),
        operating_point=copy.deepcopy(record),
        frozen_candidate=copy.deepcopy(frozen),
    )
    assert first == second
    reordered = readback_selected_perception_values(
        bundle={key: bundle[key] for key in reversed(list(bundle))},
        operating_point={key: record[key] for key in reversed(list(record))},
        frozen_candidate={key: frozen[key] for key in reversed(list(frozen))},
    )
    assert reordered == first

    readback_selected_perception_values(
        bundle=bundle,
        operating_point=record,
        frozen_candidate=frozen,
        output_path=tmp_path / "first.json",
    )
    readback_selected_perception_values(
        bundle=bundle,
        operating_point=record,
        frozen_candidate=frozen,
        output_path=tmp_path / "second.json",
    )
    assert (tmp_path / "first.json").read_bytes() == (tmp_path / "second.json").read_bytes()


def test_readback_writes_nothing_without_an_output_path_and_only_it_with_one(tmp_path):
    record, frozen, bundle = _fixture(tmp_path)
    before = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")}

    document = readback_selected_perception_values(
        bundle=bundle, operating_point=record, frozen_candidate=frozen
    )
    assert {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} == before

    target = tmp_path / "run" / READBACK_NAME
    written = readback_selected_perception_values(
        bundle=bundle, operating_point=record, frozen_candidate=frozen, output_path=target
    )
    assert written == document
    created = {path.relative_to(tmp_path) for path in tmp_path.rglob("*")} - before
    assert created == {Path("run"), Path("run") / READBACK_NAME}
    assert json.loads(target.read_text(encoding="utf-8")) == document


def test_readback_does_not_modify_the_documents_it_reads(tmp_path):
    record, frozen, bundle = _fixture(tmp_path)
    snapshot = copy.deepcopy((bundle, record, frozen))

    readback_selected_perception_values(
        bundle=bundle, operating_point=record, frozen_candidate=frozen
    )

    assert (bundle, record, frozen) == snapshot


def test_readback_depends_on_the_three_documents_and_nothing_else():
    """Plan section 2 row 5: no digest of a later artefact - the readback compares against the candidate
    document and the rule record, both of phase 3/4. The signatures are pinned so a digest parameter (a
    manifest path, a run-status digest or a pre-computed bundle sha256) cannot be added unnoticed."""

    parameters = inspect.signature(readback_selected_perception_values).parameters
    assert set(parameters) == {"bundle", "operating_point", "frozen_candidate", "output_path"}
    assert parameters["output_path"].default is None
    assert all(
        parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in parameters.values()
    )
    for helper in (compare_selected_perception_values, verify_selected_candidate_identity):
        assert set(inspect.signature(helper).parameters) == {
            "bundle",
            "operating_point",
            "frozen_candidate",
        }


@pytest.mark.parametrize(
    "case",
    [
        "no bundle",
        "no bundle parameters",
        "no bundle runtime identity",
        "no phase-3 chosen point",
        "no rule digest",
        "a rule digest that does not cover the rule record",
        "no frozen operating point",
    ],
)
def test_readback_treats_a_document_that_is_not_one_as_a_caller_bug(tmp_path, case):
    record, frozen, bundle = _fixture(tmp_path)
    documents = {"bundle": bundle, "operating_point": record, "frozen_candidate": frozen}
    if case == "no bundle":
        documents["bundle"] = None
    elif case == "no bundle parameters":
        documents["bundle"] = {key: value for key, value in bundle.items() if key != "parameters"}
    elif case == "no bundle runtime identity":
        documents["bundle"] = {
            key: value for key, value in bundle.items() if key != "runtime_identity"
        }
    elif case == "no phase-3 chosen point":
        documents["operating_point"] = {
            key: value for key, value in record.items() if key != "chosen_point"
        }
    elif case == "no rule digest":
        documents["operating_point"] = {
            key: value for key, value in record.items() if key != "rule_sha256"
        }
    elif case == "a rule digest that does not cover the rule record":
        documents["operating_point"] = {
            **record,
            "rule_sha256": canonical_sha256({"tampered": True}),
        }
    else:
        documents["frozen_candidate"] = {
            key: value for key, value in frozen.items() if key != "operating_points"
        }

    with pytest.raises(ValueError) as caught:
        readback_selected_perception_values(**documents)

    assert not isinstance(caught.value, CalibrationReadbackRefused), case
