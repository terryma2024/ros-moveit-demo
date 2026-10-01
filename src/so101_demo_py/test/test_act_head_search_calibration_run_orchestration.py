"""The orchestration of the eight fixed calibration phases: entry binding, order, fail-fast, run status.

Design section 8.2 fixes one run: input validation, geometry and coverage, the perception operating
point of every candidate, the frozen-candidate evaluation, the readback of the selected values, the
search parameters, the timing and stop parameters, and the bundle. Plan section 0 gates the bounded
trajectory contract at the entry, before any neck target exists. Plan section 1 fixes the runtime
contract (one binding at the entry, one `role=calibration` flight, no release and no recorder), the
run status as `SUCCEEDED` or `FAILED` with the first failing phase, and no `--resume` anywhere.

Everything here is synthetic: the sealed inputs are ordinary files under `tmp_path`, the geometry is a
seal this file builds, the admission is the repository's own `CalibrationMeasurementAdmission`, and the
one phase that needs a detector - the frozen-candidate evaluation - is injected as a runner, because the
orchestration is what is under test and never the measurement. Phases 6 and 7 do not exist yet, so a
run that gets past phase 5 always stops at `search_parameters` with `CAL_PHASE_UNIMPLEMENTED`, and every
test of a later phase asserts exactly that.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_calibration_bundle import (
    BUNDLE_NAME,
    MANIFEST_NAME,
    RUN_STATUS_NAME,
)
from so101_demo.act.head_search_calibration_inputs import (
    CAL_ADMISSION_REFUSED,
    CAL_BINDING_REBOUND,
    CalibrationResourceBinder,
)
from so101_demo.act.head_search_calibration_readback import READBACK_NAME
from so101_demo.act.head_search_calibration_run import (
    CAL_PHASE_UNIMPLEMENTED,
    CAL_SAFE_INTERVAL_MISMATCH,
    CAL_TRAJECTORY_CONTRACT_UNSATISFIED,
    PHASES,
    RUN_ROOT_ALREADY_EXISTS,
    UNIMPLEMENTED_PHASES,
    CalibrationPhaseInputs,
    CalibrationRunRefused,
    check_trajectory_contract,
    evaluate_frozen_candidates,
    execute_calibration_run,
)
from so101_demo.act.head_search_candidate_freeze import freeze_candidate
from so101_demo.act.head_search_operating_point import record_selection_rule
from so101_demo.act.task8_calibration_admission import CalibrationMeasurementAdmission
from so101_demo.perception_benchmark.contracts import canonical_sha256

GENERATION = "g1"
PLAN_SHA = "a" * 64
#: the safe neck interval of the sealed geometry below, so binding and seal can be compared
SAFE_INTERVAL = (-2.0, 2.0)
CANDIDATE_ID = "C"
WEIGHT_SHA256 = canonical_sha256({"seed": "candidate-C-weights"})
COMMAND = "ros2 run so101_demo_py so101_head_search_calibration run --run-root /evidence/run-01"

#: the eight phases of design section 8.2, in the order the design fixes
DESIGN_PHASES = (
    "input_validation",
    "geometry_coverage",
    "perception_operating_point",
    "frozen_candidate_evaluation",
    "selected_perception_readback",
    "search_parameters",
    "timing_stop_parameters",
    "bundle_generation",
)

#: one real file per sealed controlled dependency, with the bytes the seal digests
CONTENTS = {
    "dataset_manifest": b'{"kind": "head_search_dataset", "scenes": 40}\n',
    "model_manifest": b'{"kind": "head_search_model", "candidate": "C2a"}\n',
    "scenario_partitions": b'{"kind": "scenario_partitions", "val": 12, "test": 12}\n',
    "production_config": b'{"kind": "head_search_v2", "values": {}}\n',
    "camera_config": b'{"kind": "head_camera", "width_px": 640, "height_px": 480}\n',
}

#: a sealed geometry whose required domain is wider than one field of view, so the coverage proof has to
#: be a bounded two-way sweep; three anchors, all inside the safe neck interval
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

#: the same seal and the same safe interval, with a required domain that reaches past what the bounded
#: sweep can ever cover: the safe interval [-2, 2] plus half a field of view reaches only [-2.2, 2.2]
UNCOVERABLE_GEOMETRY_BODY = {
    **GEOMETRY_BODY,
    "required_search_domain_rad": [-3.0, 3.0],
    "anchors": ["default"],
    "in_frame_matrix": {"default": {"neck_start_rad": 0.0}},
}

#: the phase-3 points: the higher confidence floor drops the one low-confidence bystander and is the
#: unique best point of the declared grid (the fixture asserts the choice below)
HIGH_POINT = {
    "min_confidence": 0.1 + 0.2,
    "tracking_iou": 0.6,
    "min_bbox_aspect": 1.25,
    "min_area_px2": 100.0,
}
LOW_POINT = {
    "min_confidence": 0.25,
    "tracking_iou": 0.5,
    "min_bbox_aspect": 1.0,
    "min_area_px2": 64.0,
}
SELECTION_SPLITS = ("val", "calibration")
HELD_OUT_SPLITS = ("held_out_evaluation",)
MATCH_RADIUS_PX = 8.0

#: the four perception values, in the order design section 7.1 lists them
PERCEPTION_PARAMETERS = ("min_confidence", "tracking_iou", "min_bbox_aspect", "min_area_px2")
PERCEPTION_UNITS = {
    "min_confidence": "1",
    "tracking_iou": "1",
    "min_bbox_aspect": "1",
    "min_area_px2": "px^2",
}


def _module():
    from so101_demo.act import head_search_calibration_run

    return head_search_calibration_run


def _seal(body: dict) -> dict:
    """One document sealed the way the campaign sealed its geometry: canonical digest of the body."""

    sealed = {key: value for key, value in body.items() if key != "seal_sha256"}
    encoded = json.dumps(
        sealed, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    sealed["seal_sha256"] = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return sealed


def _sealed_files(tmp_path: Path, geometry_document: dict) -> dict:
    """The six sealed dependencies as real files, declared with the digests they actually have."""

    declared = {}
    for name, payload in CONTENTS.items():
        path = tmp_path / f"{name}.json"
        path.write_bytes(payload)
        declared[name] = {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest()}
    geometry = (json.dumps(geometry_document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    path = tmp_path / "geometry_seal.json"
    path.write_bytes(geometry)
    declared["geometry_seal"] = {"path": str(path), "sha256": hashlib.sha256(geometry).hexdigest()}
    return declared


def _search_config(*, bounded: bool = True, required=(-0.35, 0.35), safe=(-2.0, 2.0)) -> dict:
    """The search configuration the installed controller is constructed with, as production builds it."""

    config = {
        "attempt_id": "attempt-1",
        "session_id": "session-1",
        "search_start_rad": 0.0,
        "horizontal_fov_rad": 0.4,
        "coarse_step_rad": 0.15,
        "search_timeout_s": 12.0,
        "max_age_s": 0.15,
        "max_skew_s": 0.05,
        "settle_velocity_rad_s": 0.05,
        "goal_tolerance_rad": 0.05,
        "center_deadband_px": 18.0,
        "vertical_bounds_px": [110.0, 370.0],
        "min_area_px2": 64.0,
        "min_confidence": 0.4,
        "max_fine_corrections": 4,
        "max_fine_total_rad": 0.4,
        "frame_id": "head_camera_optical_frame",
        "ray_origin_frame_id": "base_link",
    }
    if bounded:
        # the bounded trajectory contract of plan section 0: one declared required domain and one safe
        # interval, or the installed controller falls back to the cumulative 2*pi sweep
        config["required_search_domain_rad"] = [float(required[0]), float(required[1])]
        config["lock_valid_neck_rad"] = [float(safe[0]), float(safe[1])]
    return config


def _admission(*, generation: str = GENERATION) -> CalibrationMeasurementAdmission:
    return CalibrationMeasurementAdmission(
        generation=generation,
        status="CALIBRATION_REQUIRED",
        measurement_plan_sha256=PLAN_SHA,
        safe_interval_rad=SAFE_INTERVAL,
        controller_generation="ctrl-1",
        broker_generation=generation,
    )


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


#: three head frames over both selection splits: a 0.27 bystander far from every truth. The 0.25 floor
#: keeps it as a false positive; the 0.1 + 0.2 floor drops it, so the higher floor is the unique best
#: point of the declared grid.
MEASUREMENTS = (
    _frame("val", [_truth(100, 100)], [_detection(100.2, 100.2, 0.90)]),
    _frame(
        "val",
        [_truth(200, 200)],
        [_detection(200.3, 200.3, 0.55), _detection(320.0, 320.0, 0.27)],
    ),
    _frame("calibration", [_truth(400, 400)], [_detection(400.4, 400.4, 0.85)]),
)


def _rule() -> dict:
    """The phase-3 selection rule, declared before any of its grid is measured."""

    return record_selection_rule(
        points=(LOW_POINT, HIGH_POINT),
        selection_splits=SELECTION_SPLITS,
        held_out_splits=HELD_OUT_SPLITS,
        domain="head",
    )


def _evidence(name, value):
    return {
        "value": value,
        "unit": PERCEPTION_UNITS[name],
        "selection_formula": f"the {name} rule of design 7.1",
        "input_evidence": [
            {"path": f"/evidence/{name}-campaign.json", "sha256": canonical_sha256({"n": name})}
        ],
        "observed_distribution": {"p50": 1.0, "p99": 2.0, "samples": 120},
        "safety_margin": {"bound": 1.5, "observed": 1.0},
        "production_owner": "src/so101_demo_py/src/act/head_search_operating_point.py",
        "startup_readback": {"source": "ros2 param get", "observed_value": value},
    }


def _runtime_identity():
    return {
        "package_prefix": "/toolchain/install/so101_demo_py",
        "console_script_path": "/toolchain/install/so101_demo_py/lib/so101_head_search_calibration",
        "detector_weights_sha256": WEIGHT_SHA256,
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


def _bundle_inputs(values) -> dict:
    """The per-parameter evidence blocks, the runtime identity and the five also-recorded items."""

    parameters = {
        name: _evidence(name, values[name]) for name in PERCEPTION_PARAMETERS if name in values
    }
    return {
        "runtime_identity": _runtime_identity(),
        "also_recorded": {},
        "parameter_evidence": {"perception_operating_point": {"parameters": parameters}},
    }


def _frozen(tmp_path: Path) -> dict:
    """The selected candidate document, produced by the repository's own `freeze_candidate`.

    A second run in the same fixture reuses the frozen document: `freeze_candidate` writes exclusively,
    and the frozen identity of a candidate is immutable anyway.
    """

    frozen_path = tmp_path / "frozen-candidate.json"
    if frozen_path.is_file():
        return json.loads(frozen_path.read_text(encoding="utf-8"))
    return freeze_candidate(
        candidate_id=CANDIDATE_ID,
        weight_sha256=WEIGHT_SHA256,
        min_confidence=HIGH_POINT["min_confidence"],
        tracking_iou=HIGH_POINT["tracking_iou"],
        output=tmp_path / "frozen-candidate.json",
    )


def _gate_runner(tmp_path: Path, *, failure: str | None = None):
    """A synthetic stand-in for the frozen-candidate gate: it writes what it owns and returns it.

    The real gate measures with a detector, so it cannot run here; what this stands in for is the phase
    boundary the orchestration depends on - the two documents, the selected identity, and the one refusal
    path that carries a gate code.
    """

    frozen = _frozen(tmp_path)

    def runner(context):
        # the real gate owns both documents, so the synthetic one writes both as well
        (context.run_root / "model-comparison.json").write_text(
            json.dumps({"kind": "head-search-model-comparison"}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        (context.run_root / "model-selection-verdict.json").write_text(
            json.dumps(
                {"kind": "head-search-model-selection-verdict", "selected": CANDIDATE_ID},
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if failure is not None:
            raise CalibrationRunRefused(failure, "the gate refused the comparison")
        return {
            "phase": "frozen_candidate_evaluation",
            "exit_code": 0,
            "selected_candidate_id": CANDIDATE_ID,
            "frozen_candidate": frozen,
            "comparison": {"kind": "head-search-model-comparison"},
            "verdict": {"kind": "head-search-model-selection-verdict", "selected": CANDIDATE_ID},
        }

    return runner


def _inputs(
    tmp_path: Path,
    *,
    bounded: bool = True,
    geometry_body: dict | None = None,
    operation: str = "neck_target",
    admission=None,
    binder=None,
    values=None,
    required=(-0.35, 0.35),
    safe=(-2.0, 2.0),
) -> CalibrationPhaseInputs:
    geometry = _seal(GEOMETRY_BODY if geometry_body is None else geometry_body)
    return CalibrationPhaseInputs(
        production_search_config=_search_config(bounded=bounded, required=required, safe=safe),
        sealed_inputs=_sealed_files(tmp_path, geometry),
        admission=_admission() if admission is None else admission,
        generation=GENERATION,
        operation=operation,
        cpu_cores=8,
        gpu_device=0,
        binder=binder,
        selection_rule=_rule(),
        operating_point_measurements=MEASUREMENTS,
        candidate_id=CANDIDATE_ID,
        held_out_measurements=(),
        evaluation_arguments=["compare"],
        bundle_inputs=_bundle_inputs(HIGH_POINT if values is None else values),
    )


def _run(tmp_path: Path, *, run_root: Path | None = None, phase_runners=None, **overrides):
    """Execute one synthetic run; a phase runner for the gate is always injected."""

    inputs = _inputs(tmp_path, **overrides)
    runners = {"frozen_candidate_evaluation": _gate_runner(tmp_path)}
    if phase_runners:
        runners.update(phase_runners)
    return execute_calibration_run(
        run_root=tmp_path / "run-01" if run_root is None else run_root,
        phase_inputs=inputs,
        command=COMMAND,
        phase_runners=runners,
    )


def _status(root: Path) -> dict:
    return json.loads((root / RUN_STATUS_NAME).read_text(encoding="utf-8"))


def _read(root: Path, name: str) -> dict:
    return json.loads((root / name).read_text(encoding="utf-8"))


def test_the_eight_phases_are_the_designs_and_only_six_and_seven_are_unimplemented():
    assert PHASES == DESIGN_PHASES
    assert UNIMPLEMENTED_PHASES == {
        "search_parameters": CAL_PHASE_UNIMPLEMENTED,
        "timing_stop_parameters": CAL_PHASE_UNIMPLEMENTED,
    }
    assert CAL_SAFE_INTERVAL_MISMATCH == "CAL_SAFE_INTERVAL_MISMATCH"


def test_the_run_walks_the_first_five_phases_and_stops_at_search_parameters(tmp_path):
    result = _run(tmp_path)

    root = tmp_path / "run-01"
    assert result.status == "FAILED"
    assert result.run_root == root
    assert result.phases_run == DESIGN_PHASES[:5]
    assert result.first_failing_phase == "search_parameters"
    assert result.failure_code == CAL_PHASE_UNIMPLEMENTED

    status = _status(root)
    assert status["status"] == "FAILED"
    assert status["first_failing_phase"] == "search_parameters"
    assert status["failure_code"] == CAL_PHASE_UNIMPLEMENTED
    assert status["audit_only"] is True
    assert status["checkpoint"] is False
    assert status["resume_supported"] is False
    assert status["failure_command"] == COMMAND
    # the evidence already produced: the artefacts of the phases that ran, and nothing the phases that
    # did not run would own
    assert status["evidence_produced"] == [
        "calibration-inputs.json",
        "geometry-measurements.json",
        "perception-calibration.json",
        "model-comparison.json",
        "model-selection-verdict.json",
        READBACK_NAME,
    ]
    assert {path.name for path in root.iterdir()} == set(status["evidence_produced"]) | {
        RUN_STATUS_NAME
    }
    # phases 6, 7 and 8 never ran, so their artefacts must not exist and no bundle may be claimed
    for absent in (
        "search-calibration.json",
        "timing-calibration.json",
        BUNDLE_NAME,
        MANIFEST_NAME,
    ):
        assert not (root / absent).exists(), absent


def test_the_five_phases_are_the_library_modules_and_not_each_others_copies(tmp_path):
    _run(tmp_path)
    root = tmp_path / "run-01"

    # each document names the phase that produced it, and phase 2/3 consumed phase 1's binding
    assert _read(root, "calibration-inputs.json")["phase"] == "input_validation"
    assert _read(root, "geometry-measurements.json")["phase"] == "geometry_coverage"
    assert _read(root, "perception-calibration.json")["phase"] == "perception_operating_point"
    assert _read(root, READBACK_NAME)["phase"] == "selected_perception_readback"

    chosen = _read(root, "perception-calibration.json")["chosen_point"]
    assert chosen == HIGH_POINT, "the phase-3 fixture must choose the high point"
    readback = _read(root, READBACK_NAME)
    assert readback["candidate_id"] == CANDIDATE_ID
    assert readback["values_unmodified"] is True
    assert {
        name: readback["parameters"][name]["bundle_value"] for name in PERCEPTION_PARAMETERS
    } == {name: chosen[name] for name in PERCEPTION_PARAMETERS}


def test_every_neck_target_binds_one_generation_one_plan_and_one_safe_interval(tmp_path):
    admission = _admission()
    result = _run(tmp_path, admission=admission)
    root = tmp_path / "run-01"

    inputs = _read(root, "calibration-inputs.json")
    binding = inputs["resource_binding"]
    assert binding["bound_at_entry"] is True
    assert binding["generation"] == GENERATION
    assert binding["measurement_plan_sha256"] == PLAN_SHA
    assert binding["safe_interval_rad"] == list(SAFE_INTERVAL)
    assert inputs["admission"]["admitted"] is True
    assert inputs["admission"]["role"] == "calibration"

    geometry = _read(root, "geometry-measurements.json")
    assert geometry["coverage_proof"]["safe_interval_rad"] == list(SAFE_INTERVAL)
    receipts = geometry["sweep_check_receipts"]
    assert receipts, "the sweep must have issued one receipt per neck target"
    for receipt in receipts:
        assert receipt["generation"] == GENERATION
        assert receipt["measurement_plan_sha256"] == PLAN_SHA
        assert receipt["safe_interval_rad"] == list(SAFE_INTERVAL)
        assert receipt["motion_commanded"] is False
    assert result.status == "FAILED", "phases 6 and 7 do not exist yet"


def test_the_run_takes_exactly_one_role_calibration_measurement_flight(tmp_path):
    admission = _admission()

    _run(tmp_path, admission=admission)

    assert [event["admitted"] for event in admission.events] == [True]
    assert admission.events[0]["role"] == "calibration"
    assert admission.events[0]["operation"] == "neck_target"


@pytest.mark.parametrize("operation", ["release", "recorder"])
def test_a_release_or_recorder_request_is_refused_before_any_measurement(tmp_path, operation):
    admission = _admission()

    result = _run(tmp_path, operation=operation, admission=admission)

    root = tmp_path / "run-01"
    assert admission.events == [], "a refused operation must not reach the admission at all"
    assert result.phases_run == ()
    assert result.first_failing_phase == "input_validation"
    assert result.failure_code == CAL_ADMISSION_REFUSED
    status = _status(root)
    assert status["status"] == "FAILED"
    assert status["first_failing_phase"] == "input_validation"
    assert status["failure_code"] == CAL_ADMISSION_REFUSED
    assert status["evidence_produced"] == []
    assert {path.name for path in root.iterdir()} == {RUN_STATUS_NAME}


def test_a_second_resource_binding_is_refused(tmp_path):
    binder = CalibrationResourceBinder()

    first = _run(tmp_path, binder=binder)
    second = _run(tmp_path, binder=binder, run_root=tmp_path / "run-02")

    assert binder.binding["bound_at_entry"] is True
    assert first.first_failing_phase == "search_parameters"
    assert second.phases_run == ()
    assert second.first_failing_phase == "input_validation"
    assert second.failure_code == CAL_BINDING_REBOUND
    assert not (tmp_path / "run-02" / "geometry-measurements.json").exists()


def test_a_failing_phase_leaves_the_later_phases_unrun_and_the_earlier_evidence_intact(tmp_path):
    result = _run(tmp_path, geometry_body=UNCOVERABLE_GEOMETRY_BODY)
    root = tmp_path / "run-01"

    # only phase 1 completed: the refusing phase is named by `first_failing_phase`, not counted as run
    assert result.phases_run == ("input_validation",)
    assert result.first_failing_phase == "geometry_coverage"
    assert result.failure_code == "CAL_DOMAIN_UNCOVERED"
    # phase 1's evidence is on disk and complete, and nothing of phase 3 onwards exists
    inputs = _read(root, "calibration-inputs.json")
    assert inputs["phase"] == "input_validation"
    assert inputs["admission"]["admitted"] is True
    assert inputs["resource_binding"]["bound_at_entry"] is True
    assert {path.name for path in root.iterdir()} == {
        "calibration-inputs.json",
        RUN_STATUS_NAME,
    }
    status = _status(root)
    assert status["first_failing_phase"] == "geometry_coverage"
    assert status["failure_code"] == "CAL_DOMAIN_UNCOVERED"
    assert status["evidence_produced"] == ["calibration-inputs.json"]


def test_an_injected_phase_failure_names_its_phase_and_keeps_its_partial_evidence(tmp_path):
    def runner(context):
        # the real gate writes its comparison before it refuses (HS-275), so the failure records it
        (context.run_root / "model-comparison.json").write_text(
            json.dumps({"kind": "head-search-model-comparison"}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        raise CalibrationRunRefused(
            "EVALUATION_FROZEN_IDENTITY_DRIFT", "the weights are not the seal"
        )

    result = _run(tmp_path, phase_runners={"frozen_candidate_evaluation": runner})
    root = tmp_path / "run-01"

    assert result.phases_run == DESIGN_PHASES[:3]
    assert result.first_failing_phase == "frozen_candidate_evaluation"
    assert result.failure_code == "EVALUATION_FROZEN_IDENTITY_DRIFT"
    for present in (
        "calibration-inputs.json",
        "geometry-measurements.json",
        "perception-calibration.json",
    ):
        assert (root / present).is_file(), present
    assert not (root / READBACK_NAME).exists()
    assert _status(root)["evidence_produced"] == [
        "calibration-inputs.json",
        "geometry-measurements.json",
        "perception-calibration.json",
        "model-comparison.json",
    ]


def test_a_mutated_selected_value_fails_at_the_readback_phase(tmp_path):
    mutated = {**HIGH_POINT, "min_confidence": 0.25}

    result = _run(tmp_path, values=mutated)
    root = tmp_path / "run-01"

    assert result.phases_run == DESIGN_PHASES[:4]
    assert result.first_failing_phase == "selected_perception_readback"
    assert result.failure_code == "CAL_VALUE_MUTATED"
    assert not (root / READBACK_NAME).exists()
    assert _status(root)["failure_code"] == "CAL_VALUE_MUTATED"


def test_an_admission_that_binds_another_safe_interval_is_refused_at_the_geometry_phase(tmp_path):
    """One safe interval for every neck target: the admission's must be the seal's, or nothing sweeps."""

    admission = CalibrationMeasurementAdmission(
        generation=GENERATION,
        status="CALIBRATION_REQUIRED",
        measurement_plan_sha256=PLAN_SHA,
        safe_interval_rad=(-1.0, 1.0),
        controller_generation="ctrl-1",
        broker_generation=GENERATION,
    )

    result = _run(tmp_path, admission=admission)
    root = tmp_path / "run-01"

    assert result.phases_run == ("input_validation",)
    assert result.first_failing_phase == "geometry_coverage"
    assert result.failure_code == CAL_SAFE_INTERVAL_MISMATCH
    assert not (root / "geometry-measurements.json").exists()
    assert _status(root)["evidence_produced"] == ["calibration-inputs.json"]


def test_the_precondition_accepts_the_bounded_plan_and_commands_no_motion():
    receipt = check_trajectory_contract(production_search_config=_search_config())

    assert receipt["bounded_stop_plan"] is True
    assert receipt["coverage_complete"] is True
    assert receipt["motion_commanded"] is False
    assert receipt["safe_interval_rad"] == list(SAFE_INTERVAL)
    assert receipt["targets_rad"], "the check must walk the bounded stops it proves"
    assert all(SAFE_INTERVAL[0] <= target <= SAFE_INTERVAL[1] for target in receipt["targets_rad"])
    assert len(receipt["config_sha256"]) == 64


def test_a_plan_without_the_bounded_trajectory_contract_fails_at_entry_before_any_phase(tmp_path):
    calls = []

    def never(context):  # pragma: no cover - the entry refusal must prevent this from being reached
        calls.append(context)

    with pytest.raises(CalibrationRunRefused) as refused:
        _run(tmp_path, bounded=False, phase_runners={"frozen_candidate_evaluation": never})

    assert refused.value.code == CAL_TRAJECTORY_CONTRACT_UNSATISFIED
    assert calls == []
    assert not (tmp_path / "run-01").exists(), "an entry refusal must not claim a run root"


def test_the_precondition_refuses_a_domain_the_safe_interval_cannot_cover(tmp_path):
    inputs = _inputs(tmp_path, required=(-3.0, 3.0), safe=(-1.0, 1.0))

    with pytest.raises(CalibrationRunRefused) as refused:
        execute_calibration_run(
            run_root=tmp_path / "run-01",
            phase_inputs=inputs,
            command=COMMAND,
            phase_runners={"frozen_candidate_evaluation": _gate_runner(tmp_path)},
        )

    assert refused.value.code == CAL_TRAJECTORY_CONTRACT_UNSATISFIED
    assert not (tmp_path / "run-01").exists()


def test_two_runs_in_the_same_root_are_refused_without_a_fresh_run_root(tmp_path):
    _run(tmp_path)
    root = tmp_path / "run-01"
    before = {path.name: path.read_bytes() for path in root.iterdir()}

    with pytest.raises(CalibrationRunRefused) as refused:
        _run(tmp_path)

    assert refused.value.code == RUN_ROOT_ALREADY_EXISTS
    assert {path.name: path.read_bytes() for path in root.iterdir()} == before


def test_the_orchestration_offers_no_resume_or_continuation_entry(tmp_path):
    module = _module()

    assert not [name for name in dir(module) if "resume" in name.lower()]
    assert not [name for name in dir(module) if "checkpoint" in name.lower()]
    assert not [name for name in dir(module) if "continue" in name.lower()]

    result = _run(tmp_path)

    status = _status(tmp_path / "run-01")
    assert status["resume_supported"] is False
    assert status["checkpoint"] is False
    assert result.status == "FAILED", "no run may claim success while phases 6 and 7 are missing"


def test_an_uncoded_phase_error_is_not_dressed_up_as_a_design_refusal(tmp_path):
    def runner(context):  # pragma: no cover - the error is what this test asserts
        raise ValueError("a caller bug, not a refusal code")

    with pytest.raises(ValueError, match="a caller bug"):
        _run(tmp_path, phase_runners={"selected_perception_readback": runner})

    root = tmp_path / "run-01"
    assert (root / "perception-calibration.json").is_file(), (
        "the earlier evidence stays for forensics"
    )
    assert not (root / RUN_STATUS_NAME).exists(), "an uncoded bug is not a design outcome"


def test_the_phase_four_runner_reuses_the_existing_gate_and_its_documents(tmp_path):
    frozen_path = tmp_path / "frozen-C.json"
    freeze_candidate(
        candidate_id=CANDIDATE_ID,
        weight_sha256=WEIGHT_SHA256,
        min_confidence=HIGH_POINT["min_confidence"],
        tracking_iou=HIGH_POINT["tracking_iou"],
        output=frozen_path,
    )
    output = tmp_path / "evaluation"
    calls = []

    class _Gate:
        @staticmethod
        def main(argv):
            calls.append(list(argv))
            output.mkdir(parents=True, exist_ok=True)
            (output / "model-comparison.json").write_text(
                json.dumps({"kind": "head-search-model-comparison"}), encoding="utf-8"
            )
            (output / "model-selection-verdict.json").write_text(
                json.dumps({"kind": "head-search-model-selection-verdict", "selected": "C"}),
                encoding="utf-8",
            )
            return 0

    document = evaluate_frozen_candidates(
        arguments=["compare", "--candidate", str(frozen_path)],
        output_dir=output,
        gate=_Gate,
    )

    assert calls == [["compare", "--candidate", str(frozen_path), "--output", str(output)]]
    assert document["exit_code"] == 0
    assert document["selected_candidate_id"] == "C"
    assert document["frozen_candidate"]["candidate_id"] == "C"
    assert document["frozen_candidate"]["weight_sha256"] == WEIGHT_SHA256
    assert document["verdict"]["selected"] == "C"


def test_the_phase_four_runner_refuses_a_caller_chosen_output_directory(tmp_path):
    """The run root owns the gate's output; an argument that moves it is a caller bug, not a policy."""

    class _Gate:
        @staticmethod
        def main(argv):  # pragma: no cover - the caller bug is caught before the gate runs
            raise AssertionError("the gate must not run")

    with pytest.raises(ValueError, match="run root owns the gate's output"):
        evaluate_frozen_candidates(
            arguments=["compare", "--output", str(tmp_path / "elsewhere")],
            output_dir=tmp_path / "evaluation",
            gate=_Gate,
        )


def test_the_phase_four_runner_carries_the_gates_own_refusal_code(tmp_path):
    class _Gate:
        @staticmethod
        def main(argv):  # pragma: no cover - the printed failure is what this test asserts
            print(
                json.dumps(
                    {"failure": "EVALUATION_SPLIT_LEAK: the val split leaked", "status": "ERROR"}
                )
            )
            return 2

    with pytest.raises(CalibrationRunRefused) as refused:
        evaluate_frozen_candidates(
            arguments=["compare"], output_dir=tmp_path / "evaluation", gate=_Gate
        )

    assert refused.value.code == "EVALUATION_SPLIT_LEAK"


def test_the_phase_four_runner_refuses_an_unparsable_gate_failure(tmp_path):
    class _Gate:
        @staticmethod
        def main(argv):  # pragma: no cover - the printed failure is what this test asserts
            print("the gate died without a code")
            return 3

    with pytest.raises(CalibrationRunRefused) as refused:
        evaluate_frozen_candidates(
            arguments=["compare"], output_dir=tmp_path / "evaluation", gate=_Gate
        )

    assert refused.value.code == "CAL_CANDIDATE_EVALUATION_FAILED"
