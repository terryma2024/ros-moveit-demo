"""Phase 2 of the formal head-search calibration: sealed geometry, candidates and coverage proof.

The phase reads the sealed camera geometry, generates the coarse-step candidates the design allows
(`<= horizontal_fov_rad / 2`), proves that the chosen candidate covers the whole
`required_search_domain_rad` with a bounded two-way sweep, and issues one independent sweep-check
receipt per neck target. It commands no motion: the fixtures here are ordinary JSON files under
`tmp_path`, sealed with the digests they actually have.
"""

from __future__ import annotations

import hashlib
import json

import pytest

GENERATION = "g1"
MEASUREMENT_PLAN_SHA = "a" * 64

#: the five sealed dependencies this phase does not read, written so the phase-1 seal validates
OTHER_SEALED_INPUTS = {
    "dataset_manifest": b'{"kind": "head_search_dataset", "scenes": 40}\n',
    "model_manifest": b'{"kind": "head_search_model", "candidate": "C2a"}\n',
    "scenario_partitions": b'{"kind": "scenario_partitions", "val": 12, "test": 12}\n',
    "production_config": b'{"kind": "head_search_v2", "values": {}}\n',
    "camera_config": b'{"kind": "head_camera", "width_px": 640, "height_px": 480}\n',
}

#: a sealed geometry whose required domain is wider than a single field of view, so the coverage
#: proof has to be a sweep and not one stop; three anchors, all inside the safe neck interval
GEOMETRY_BODY = {
    "schema_version": 1,
    "kind": "head_camera_geometry",
    "horizontal_fov_rad": 0.4,
    "lock_valid_neck_rad": [-2.0, 2.0],
    "required_search_domain_rad": [-0.35, 0.35],
    "coarse_step_candidate_rad": 0.15,
    "anchors": ["left", "default", "right"],
    "in_frame_matrix": {
        "left": {"neck_start_rad": -0.2},
        "default": {"neck_start_rad": 0.0},
        "right": {"neck_start_rad": 0.2},
    },
}

#: the same seal except that the required domain reaches past what the sweep can ever cover: the
#: safe interval [-0.1, 0.1] plus half a field of view reaches only [-0.3, 0.3]
UNCOVERABLE_GEOMETRY_BODY = {
    **GEOMETRY_BODY,
    "lock_valid_neck_rad": [-0.1, 0.1],
    "required_search_domain_rad": [-0.5, 0.5],
    "anchors": ["default"],
    "in_frame_matrix": {"default": {"neck_start_rad": 0.0}},
}

#: the geometry the campaign sealed declares a candidate step larger than half its field of view
OVERLARGE_CANDIDATE_BODY = {**GEOMETRY_BODY, "coarse_step_candidate_rad": 0.9}


def _seal(body: dict) -> dict:
    """One document sealed the way the campaign sealed its geometry: canonical digest of the body."""

    sealed = {key: value for key, value in body.items() if key != "seal_sha256"}
    encoded = json.dumps(
        sealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    sealed["seal_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return sealed


def _module():
    from so101_demo.act import head_search_calibration_geometry

    return head_search_calibration_geometry


def _sealed_files(tmp_path, document: dict) -> dict:
    """The six sealed dependencies as real files, declared with the digests they actually have."""

    declared = {}
    for name, payload in OTHER_SEALED_INPUTS.items():
        path = tmp_path / f"{name}.json"
        path.write_bytes(payload)
        declared[name] = {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest()}
    geometry = json.dumps(document, indent=2, sort_keys=True).encode("utf-8") + b"\n"
    path = tmp_path / "geometry_seal.json"
    path.write_bytes(geometry)
    declared["geometry_seal"] = {"path": str(path), "sha256": hashlib.sha256(geometry).hexdigest()}
    return declared


def _run_phase(tmp_path, *, document=None, **overrides) -> dict:
    """Run phase 2 over the sealed fixture; an override replaces one argument."""

    module = _module()
    arguments = {
        "sealed_inputs": _sealed_files(
            tmp_path, _seal(GEOMETRY_BODY) if document is None else document
        )
    }
    arguments.update(overrides)
    return module.validate_head_search_calibration_geometry(**arguments)


def _coverage_of(targets, *, required_domain_rad, horizontal_fov_rad) -> tuple[float, float]:
    """Independently re-derive the covered part of the domain from the stops' field of view."""

    low, high = required_domain_rad
    half = horizontal_fov_rad / 2.0
    reach = low
    for start, stop in sorted((target - half, target + half) for target in targets):
        if start > reach + 1e-9:
            break
        reach = max(reach, min(stop, high))
    return reach, high


def test_the_three_refusal_codes_are_exactly_the_planned_codes():
    module = _module()
    from so101_demo.act import head_search_calibration_inputs

    assert module.REFUSAL_CODES == (
        "CAL_INPUT_UNSEALED",
        "CAL_DOMAIN_UNCOVERED",
        "CAL_SWEEP_RECEIPT_MISSING",
    )
    # the unsealed code is phase 1's own, not a second spelling of it
    assert module.CAL_INPUT_UNSEALED == head_search_calibration_inputs.CAL_INPUT_UNSEALED
    assert issubclass(module.CalibrationGeometryRefused, head_search_calibration_inputs.CalibrationInputsRefused)


def test_the_geometry_values_come_from_the_sealed_document(tmp_path):
    document = _seal(GEOMETRY_BODY)

    phase = _run_phase(tmp_path, document=document)

    geometry = phase["geometry"]
    assert geometry["horizontal_fov_rad"] == GEOMETRY_BODY["horizontal_fov_rad"]
    assert geometry["lock_valid_neck_rad"] == list(GEOMETRY_BODY["lock_valid_neck_rad"])
    assert geometry["required_search_domain_rad"] == list(GEOMETRY_BODY["required_search_domain_rad"])
    assert geometry["sealed_coarse_step_candidate_rad"] == 0.15
    assert geometry["anchors_rad"] == {"left": -0.2, "default": 0.0, "right": 0.2}
    sealed = phase["sealed_geometry"]
    assert sealed["path"] == str(tmp_path / "geometry_seal.json")
    assert sealed["sha256"] == hashlib.sha256(
        (tmp_path / "geometry_seal.json").read_bytes()
    ).hexdigest()
    # the document's own seal identity is carried through, so later phases can compare it
    assert sealed["seal_sha256"] == document["seal_sha256"]
    assert len(sealed["manifest_sha256"]) == 64


def test_the_candidates_are_generated_from_the_sealed_half_field_of_view(tmp_path):
    module = _module()

    candidates = module.generate_coarse_step_candidates(0.4, sealed_candidate_rad=0.15)

    half = 0.2
    assert candidates == (0.2, 0.15, 0.1, 0.05, 0.025, 0.0125)
    assert all(0.0 < candidate <= half for candidate in candidates)
    assert list(candidates) == sorted(candidates, reverse=True)

    phase = _run_phase(tmp_path)
    assert [record["coarse_step_rad"] for record in phase["candidates"]] == list(candidates)
    assert {record["source"] for record in phase["candidates"]} == {"generated", "sealed"}
    assert phase["candidate_generation"]["half_fov_rad"] == half


def test_a_candidate_above_half_the_field_of_view_is_never_generated(tmp_path):
    module = _module()

    candidates = module.generate_coarse_step_candidates(0.4, sealed_candidate_rad=0.9)

    assert 0.9 not in candidates
    assert all(candidate <= 0.2 for candidate in candidates)
    assert module.generate_coarse_step_candidates(0.4) == tuple(
        candidate for candidate in candidates if candidate != 0.9
    )

    phase = _run_phase(tmp_path, document=_seal(OVERLARGE_CANDIDATE_BODY))
    assert all(
        record["coarse_step_rad"] <= 0.2 for record in phase["candidates"]
    )
    assert phase["chosen_candidate_rad"] <= 0.2


def test_the_largest_covering_candidate_is_chosen_and_its_sweep_proves_coverage(tmp_path):
    phase = _run_phase(tmp_path)

    covering = [
        record["coarse_step_rad"]
        for record in phase["candidates"]
        if record["covers_required_domain"]
    ]
    assert covering, "no candidate covers the fixture's required domain"
    assert phase["chosen_candidate_rad"] == max(covering)
    assert phase["chosen_candidate_rad"] == phase["candidates"][0]["coarse_step_rad"]
    assert phase["chosen_candidate_rad"] <= phase["geometry"]["horizontal_fov_rad"] / 2

    proof = phase["coverage_proof"]
    assert proof["coverage_complete"] is True
    assert proof["sweep"] == "bounded_two_way"
    assert proof["coverage"] == "horizontal_fov_union_of_stops"
    assert proof["coarse_step_candidate_rad"] == phase["chosen_candidate_rad"]
    assert proof["required_search_domain_rad"] == list(GEOMETRY_BODY["required_search_domain_rad"])

    safe_low, safe_high = phase["geometry"]["lock_valid_neck_rad"]
    required = phase["geometry"]["required_search_domain_rad"]
    fov = phase["geometry"]["horizontal_fov_rad"]
    assert [anchor["anchor"] for anchor in proof["anchors"]] == ["left", "default", "right"]
    for anchor in proof["anchors"]:
        targets = anchor["targets_rad"]
        assert anchor["coverage_complete"] is True
        assert anchor["independent_sweep_check"] == {"checked": True, "reason": "covered"}
        assert anchor["stop_count"] == len(targets) > 0
        assert all(safe_low <= target <= safe_high for target in targets)
        # the domain is wider than one field of view and the stops span it, so this is a sweep
        assert max(targets) - min(targets) > fov / 2
        # at most one direction change: the sweep is the bounded two-way one the design fixes
        moves = [anchor["anchor_rad"], *targets]
        directions = [1 if second > first else -1 for first, second in zip(moves, moves[1:])]
        assert sum(
            1 for first, second in zip(directions, directions[1:]) if first != second
        ) <= 1
        # the module's claim, re-derived here from the stop angles alone
        reach, high = _coverage_of(targets, required_domain_rad=required, horizontal_fov_rad=fov)
        assert reach >= high - 1e-9


def test_every_neck_target_carries_its_own_independent_sweep_check_receipt(tmp_path):
    phase = _run_phase(tmp_path, generation=GENERATION, measurement_plan_sha256=MEASUREMENT_PLAN_SHA)

    proof = phase["coverage_proof"]
    receipts = phase["sweep_check_receipts"]
    expected = [
        (anchor["anchor"], target)
        for anchor in proof["anchors"]
        for target in anchor["targets_rad"]
    ]
    assert len(receipts) == len(expected) == sum(
        anchor["stop_count"] for anchor in proof["anchors"]
    )
    assert [(receipt["anchor"], receipt["target_rad"]) for receipt in receipts] == expected
    assert len({receipt["receipt_sha256"] for receipt in receipts}) == len(receipts)
    for receipt in receipts:
        assert receipt["checked"] is True
        assert receipt["reason"] == "covered"
        assert receipt["checker"] == "independent_sweep_check"
        assert receipt["coarse_step_candidate_rad"] == phase["chosen_candidate_rad"]
        assert receipt["safe_interval_rad"] == list(GEOMETRY_BODY["lock_valid_neck_rad"])
        assert receipt["required_search_domain_rad"] == list(GEOMETRY_BODY["required_search_domain_rad"])
        # one generation, one measurement plan and one safe interval for every neck target
        assert receipt["generation"] == GENERATION
        assert receipt["measurement_plan_sha256"] == MEASUREMENT_PLAN_SHA
        assert len(receipt["receipt_sha256"]) == 64
        assert receipt["motion_commanded"] is False
    assert phase["sweep_check_receipts_complete"] is True
    # the phase's own completeness check accepts exactly what it built
    module = _module()
    assert module.require_sweep_check_receipts(coverage_proof=proof, receipts=receipts) is None


def test_a_target_without_its_own_receipt_is_refused(tmp_path):
    module = _module()
    phase = _run_phase(tmp_path)
    proof = phase["coverage_proof"]
    receipts = phase["sweep_check_receipts"]
    dropped = receipts[0]

    with pytest.raises(module.CalibrationGeometryRefused) as raised:
        module.require_sweep_check_receipts(coverage_proof=proof, receipts=receipts[1:])

    assert raised.value.code == "CAL_SWEEP_RECEIPT_MISSING"
    assert dropped["anchor"] in str(raised.value)
    assert repr(dropped["target_rad"]) in str(raised.value)


def test_a_receipt_whose_check_did_not_pass_cannot_vouch_for_its_target(tmp_path):
    module = _module()
    phase = _run_phase(tmp_path)
    proof = phase["coverage_proof"]
    receipts = [
        {**receipt, "checked": False, "reason": "the required domain is not covered at 0.3"}
        if index == 0
        else receipt
        for index, receipt in enumerate(phase["sweep_check_receipts"])
    ]

    with pytest.raises(module.CalibrationGeometryRefused) as raised:
        module.require_sweep_check_receipts(coverage_proof=proof, receipts=receipts)

    assert raised.value.code == "CAL_SWEEP_RECEIPT_MISSING"


def test_an_absent_sealed_geometry_is_refused_with_phase_ones_code(tmp_path):
    module = _module()
    from so101_demo.act import head_search_calibration_inputs

    declared = _sealed_files(tmp_path, _seal(GEOMETRY_BODY))
    (tmp_path / "geometry_seal.json").unlink()

    with pytest.raises(module.CalibrationGeometryRefused) as raised:
        module.validate_head_search_calibration_geometry(sealed_inputs=declared)

    assert raised.value.code == "CAL_INPUT_UNSEALED"
    assert "geometry_seal" in str(raised.value)
    # the refusal itself is phase 1's: this phase re-raises the validation phase 1 performed
    assert isinstance(raised.value.__cause__, head_search_calibration_inputs.CalibrationInputsRefused)


def test_a_rewritten_sealed_geometry_is_refused_with_phase_ones_code(tmp_path):
    module = _module()
    declared = _sealed_files(tmp_path, _seal(GEOMETRY_BODY))
    (tmp_path / "geometry_seal.json").write_bytes(b'{"horizontal_fov_rad": 3.0}\n')

    with pytest.raises(module.CalibrationGeometryRefused) as raised:
        module.validate_head_search_calibration_geometry(sealed_inputs=declared)

    assert raised.value.code == "CAL_INPUT_UNSEALED"
    assert "geometry_seal" in str(raised.value)


def test_a_geometry_whose_own_seal_does_not_match_is_refused(tmp_path):
    module = _module()
    document = _seal(GEOMETRY_BODY)
    document["seal_sha256"] = "c" * 64

    with pytest.raises(module.CalibrationGeometryRefused) as raised:
        _run_phase(tmp_path, document=document)

    assert raised.value.code == "CAL_INPUT_UNSEALED"
    assert "seal_sha256" in str(raised.value)


@pytest.mark.parametrize(
    "missing", ["horizontal_fov_rad", "lock_valid_neck_rad", "required_search_domain_rad", "anchors"]
)
def test_a_geometry_without_its_sealed_fields_is_refused(tmp_path, missing):
    module = _module()
    body = {key: value for key, value in GEOMETRY_BODY.items() if key != missing}

    with pytest.raises(module.CalibrationGeometryRefused) as raised:
        _run_phase(tmp_path, document=_seal(body))

    assert raised.value.code == "CAL_INPUT_UNSEALED"
    assert missing in str(raised.value)


def test_a_required_domain_the_candidate_cannot_cover_is_refused(tmp_path):
    module = _module()

    with pytest.raises(module.CalibrationGeometryRefused) as raised:
        _run_phase(tmp_path, document=_seal(UNCOVERABLE_GEOMETRY_BODY))

    assert raised.value.code == "CAL_DOMAIN_UNCOVERED"
    # every generated candidate was tried and each names why it cannot cover the sweep
    for fraction in ("0.5", "0.25", "0.125"):
        assert fraction in str(raised.value)
    assert "HEAD_SEARCH_DOMAIN_UNSAFE" in str(raised.value)


def test_the_same_sealed_input_yields_identical_candidates_choice_and_receipts(tmp_path):
    declared = _sealed_files(tmp_path, _seal(GEOMETRY_BODY))
    module = _module()
    arguments = {"sealed_inputs": declared, "generation": GENERATION}

    first = module.validate_head_search_calibration_geometry(**arguments)
    second = module.validate_head_search_calibration_geometry(**arguments)

    assert first == second
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert [record["coarse_step_rad"] for record in first["candidates"]] == [
        record["coarse_step_rad"] for record in second["candidates"]
    ]
    assert first["chosen_candidate_rad"] == second["chosen_candidate_rad"]
    assert first["sweep_check_receipts"] == second["sweep_check_receipts"]
    assert [receipt["receipt_sha256"] for receipt in first["sweep_check_receipts"]] == [
        receipt["receipt_sha256"] for receipt in second["sweep_check_receipts"]
    ]


def test_the_phase_commands_no_motion_and_writes_nothing_outside_an_output_path(tmp_path):
    module = _module()
    declared = _sealed_files(tmp_path, _seal(GEOMETRY_BODY))
    before = sorted(path.name for path in tmp_path.iterdir())

    document = module.validate_head_search_calibration_geometry(sealed_inputs=declared)

    assert sorted(path.name for path in tmp_path.iterdir()) == before
    assert document["motion_commanded"] is False
    assert all(receipt["motion_commanded"] is False for receipt in document["sweep_check_receipts"])

    output = tmp_path / "phase-2" / "head-search-calibration-geometry.json"
    written = module.validate_head_search_calibration_geometry(
        sealed_inputs=declared, output_path=output
    )
    assert written == document
    assert json.loads(output.read_text(encoding="utf-8")) == document
    assert sorted(path.name for path in output.parent.iterdir()) == [output.name]
