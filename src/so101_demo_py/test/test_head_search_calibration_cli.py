"""The installed subcommands: approval verification, qualification, the run entry and no resume."""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import pytest
from so101_demo.cli.head_search_calibration import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
    HEAD_SEARCH_RUN_INPUTS_INCOMPLETE,
    main,
)
from head_search_qualification_fixtures import ANCHORS, build_fixture, digest as fixture_digest
from so101_demo.act.head_search_aggregate import GATES
from so101_demo.perception_benchmark.contracts import canonical_sha256


def _bundle(root: Path) -> Path:
    """Write a promoted bundle and return the file, whose bytes are what verification hashes."""

    root.mkdir(parents=True, exist_ok=True)
    document = {"schema_version": 1, "measurements": {"max_age_s": {"value": 0.05}}}
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")
    target = root / "head-search-bundle.json"
    target.write_bytes(payload)
    return target


def test_verify_promoted_config_needs_the_approved_digest_and_a_bundle(tmp_path: Path) -> None:
    promoted = _bundle(tmp_path / "promoted")
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(tmp_path / "run"),
                "--promoted-config",
                str(promoted),
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(tmp_path / "run2"),
                "--approved-bundle-sha256",
                "a" * 64,
            ]
        )
        == 2
    )


def test_verify_promoted_config_refuses_a_drifted_bundle(tmp_path: Path) -> None:
    promoted = _bundle(tmp_path / "promoted")
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(tmp_path / "run"),
                "--promoted-config",
                str(promoted),
                "--approved-bundle-sha256",
                "0" * 64,
            ]
        )
        == 2
    )
    assert not (tmp_path / "run").exists(), "a refused approval must not create its root"


def test_verify_promoted_config_writes_an_approval_receipt(tmp_path: Path) -> None:
    promoted = _bundle(tmp_path / "promoted")
    run_root = tmp_path / "run"
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(run_root),
                "--promoted-config",
                str(promoted),
                "--approved-bundle-sha256",
                _digest(promoted),
            ]
        )
        == 0
    )
    receipt = json.loads((run_root / "approval-receipt.json").read_text(encoding="utf-8"))
    assert receipt["approved_bundle_sha256"] == _digest(promoted)
    assert receipt["hashed"] == "bytes"
    assert receipt["verified"] is True


def _qualify_argv(fixture, run_root: Path, *, omit: tuple[str, ...] = ()) -> list[str]:
    """The installed `qualify` arguments for one fixture set, minus the gates named in `omit`."""

    arguments = [
        "qualify",
        "--run-root",
        str(run_root),
        "--final-run",
        str(fixture.paths["final_run"]),
        "--promoted-config",
        str(fixture.paths["production_config"]),
        "--approved-bundle",
        str(fixture.paths["approved_bundle"]),
        "--ownership-receipt",
        str(fixture.paths["ownership_receipt"]),
        "--runtime-readback",
        str(fixture.paths["runtime_readback"]),
        "--production-smoke-root",
        str(fixture.paths["production_smoke_root"]),
        "--scenarios-root",
        str(fixture.paths["scenarios_root"]),
        "--teleop-acceptance-receipt",
        str(fixture.paths["teleop_acceptance_receipt"]),
        "--scenario-partitions",
        str(fixture.partitions),
    ]
    for anchor in ANCHORS:
        arguments += ["--restart-receipt", str(fixture.paths[f"restart_{anchor}"])]
    for name in omit:
        flag = "--" + name.replace("_", "-")
        while flag in arguments:
            position = arguments.index(flag)
            del arguments[position : position + 2]
    return arguments


def test_qualify_refuses_an_existing_root_and_never_resumes_it(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    # an existing root is a named refusal with exit code 2, not a traceback
    assert main(["qualify", "--run-root", str(run_root)]) == 2


def test_qualify_without_evidence_refuses_every_gate_by_name(tmp_path: Path, capsys) -> None:
    """No evidence at all is a REFUSED verdict that names every gate; it is not a traceback."""

    run_root = tmp_path / "fresh"
    assert main(["qualify", "--run-root", str(run_root)]) == 2
    verdict = json.loads((run_root / "qualification-verdict.json").read_text(encoding="utf-8"))
    assert verdict["status"] == "HEAD_SEARCH_QUALIFICATION_REFUSED"
    assert {reason["gate"] for reason in verdict["missing"]} == set(GATES)
    assert not (run_root / "head-search-qualification.json").exists()
    assert not (run_root / "head-search-qualified-report.json").exists()
    stderr = capsys.readouterr().err
    assert "HEAD_SEARCH_QUALIFICATION_REFUSED" in stderr
    assert "HEAD_SEARCH_QUALIFICATION_EVIDENCE_INCOMPLETE" in stderr


def test_qualify_publishes_the_plan_documents_only_with_the_declared_citations(
    tmp_path: Path,
) -> None:
    fixture = build_fixture(tmp_path / "evidence", run_root=tmp_path / "qualification-run")
    assert main(_qualify_argv(fixture, fixture.run_root)) == 0
    report = json.loads(
        (fixture.run_root / "head-search-qualified-report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "HEAD_SEARCH_QUALIFIED"
    assert report["bundle_sha256"] == fixture_digest(fixture.paths["approved_bundle"])
    for phase in (
        "production_smoke",
        "scenarios",
        "restart_default",
        "restart_left",
        "restart_forward",
        "teleop_acceptance",
    ):
        assert report["citations"][phase]["root"], phase
    qualification = json.loads(
        (fixture.run_root / "head-search-qualification.json").read_text(encoding="utf-8")
    )
    sample = qualification["samples"][0]
    assert sample["status"] == "PASS"
    assert len(sample["values"]) == 17
    assert len(sample["camera_measurements"]) == 4


def test_qualify_refuses_and_names_a_single_missing_phase_root(tmp_path: Path, capsys) -> None:
    """One missing gate is one named refusal and no pass documents, whatever else is present."""

    fixture = build_fixture(tmp_path / "evidence", run_root=tmp_path / "qualification-run")
    assert main(_qualify_argv(fixture, fixture.run_root, omit=("production-smoke-root",))) == 2
    stderr = capsys.readouterr().err
    assert "production_smoke" in stderr and "production_smoke_root" in stderr
    assert not (fixture.run_root / "head-search-qualified-report.json").exists()
    assert not (fixture.run_root / "head-search-qualification.json").exists()
    verdict = json.loads((fixture.run_root / "qualification-verdict.json").read_text(encoding="utf-8"))
    assert verdict["gates"]["production_smoke"]["status"] == "MISSING"
    assert verdict["gates"]["scenario_journal"]["status"] == "HOLDS"


def test_qualify_has_no_digest_only_surface_any_more(tmp_path: Path) -> None:
    """The HS-233/HS-315 defect: a directory of hex digests used to be enough to publish a pass."""

    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "production_smoke.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    with pytest.raises(SystemExit):
        main(["qualify", "--run-root", str(tmp_path / "run"), "--evidence-root", str(evidence)])


#: the synthetic run's sealed controlled dependencies, one real file each
RUN_SEALED_CONTENTS = {
    "dataset_manifest": b'{"kind": "head_search_dataset", "scenes": 40}\n',
    "model_manifest": b'{"kind": "head_search_model", "candidate": "C"}\n',
    "scenario_partitions": b'{"kind": "scenario_partitions", "val": 12, "test": 12}\n',
    "production_config": b'{"kind": "head_search_v2", "values": {}}\n',
    "camera_config": b'{"kind": "head_camera", "width_px": 640, "height_px": 480}\n',
}
RUN_GEOMETRY_BODY = {
    "schema_version": 1,
    "kind": "head_camera_geometry",
    "horizontal_fov_rad": 0.4,
    "lock_valid_neck_rad": [-2.0, 2.0],
    "required_search_domain_rad": [-0.35, 0.35],
    "coarse_step_candidate_rad": 0.15,
    "anchors": ["default"],
    "in_frame_matrix": {"default": {"neck_start_rad": 0.0}},
}
RUN_PLAN_SHA = "a" * 64
RUN_SELECTION_SPLITS = ("val", "calibration")
RUN_HELD_OUT_SPLITS = ("held_out_evaluation",)
RUN_HIGH_POINT = {
    "min_confidence": 0.1 + 0.2,
    "tracking_iou": 0.6,
    "min_bbox_aspect": 1.25,
    "min_area_px2": 100.0,
}
RUN_LOW_POINT = {
    "min_confidence": 0.25,
    "tracking_iou": 0.5,
    "min_bbox_aspect": 1.0,
    "min_area_px2": 64.0,
}
RUN_WEIGHT_SHA256 = canonical_sha256({"seed": "candidate-C-weights"})
RUN_MEASUREMENTS = (
    {
        "split": "val",
        "domain": "head",
        "seed": 0,
        "scenario": "nominal",
        "truth": [{"x": 100, "y": 100}],
        "detections": {"C": [{"x": 100.2, "y": 100.2, "conf": 0.90}]},
        "match_radius_px": 8.0,
    },
    {
        "split": "calibration",
        "domain": "head",
        "seed": 1,
        "scenario": "nominal",
        "truth": [{"x": 400, "y": 400}],
        "detections": {"C": [{"x": 400.4, "y": 400.4, "conf": 0.85}]},
        "match_radius_px": 8.0,
    },
)


def _write_json(path: Path, document) -> Path:
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _sealed(body: dict) -> dict:
    """One document sealed the way the campaign sealed its geometry: canonical digest of the body."""

    sealed = {key: value for key, value in body.items() if key != "seal_sha256"}
    return {**sealed, "seal_sha256": canonical_sha256(sealed)}


def _run_arguments(
    tmp_path: Path,
    *,
    bounded: bool = True,
    seal: str | None = None,
    omit: tuple[str, ...] = (),
) -> list[str]:
    """A complete synthetic argument set for `run`, with every declared input written under tmp_path.

    The sealed documents, the search configuration the entry preconditions read, the admission, the
    phase-3 rule and measurements, the frozen candidate, the bundle inputs and the phase-6/phase-7
    measurement documents are all real files produced by the repository's own writers or declared as
    plainly as the phases read them; no detector, GPU or simulator is involved, because what this
    exercises is the CLI's parsing, validation and orchestration. `omit` drops a flag and its value, so
    a test can show what a run that fails to declare one of its inputs does.
    """

    from so101_demo.act.head_search_candidate_freeze import freeze_candidate
    from so101_demo.act.head_search_operating_point import record_selection_rule

    declared = {}
    for name, payload in RUN_SEALED_CONTENTS.items():
        path = tmp_path / f"{name}.json"
        path.write_bytes(payload)
        declared[name] = {"path": str(path), "sha256": hashlib.sha256(payload).hexdigest()}
    geometry_path = _write_json(tmp_path / "geometry-seal.json", _sealed(RUN_GEOMETRY_BODY))
    declared["geometry_seal"] = {
        "path": str(geometry_path),
        "sha256": _digest(geometry_path),
    }

    search_config = {
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
        search_config["required_search_domain_rad"] = list(
            RUN_GEOMETRY_BODY["required_search_domain_rad"]
        )
        search_config["lock_valid_neck_rad"] = list(RUN_GEOMETRY_BODY["lock_valid_neck_rad"])
    search_path = _write_json(tmp_path / "production-search-config.json", search_config)

    admission_path = _write_json(
        tmp_path / "admission.json",
        {
            "generation": "g1",
            "status": "CALIBRATION_REQUIRED",
            "measurement_plan_sha256": RUN_PLAN_SHA,
            "safe_interval_rad": list(RUN_GEOMETRY_BODY["lock_valid_neck_rad"]),
            "controller_generation": "ctrl-1",
            "broker_generation": "g1",
        },
    )
    rule = record_selection_rule(
        points=(RUN_LOW_POINT, RUN_HIGH_POINT),
        selection_splits=RUN_SELECTION_SPLITS,
        held_out_splits=RUN_HELD_OUT_SPLITS,
        domain="head",
    )
    rule_path = _write_json(tmp_path / "selection-rule.json", rule)
    measurements_path = _write_json(tmp_path / "measurements.json", list(RUN_MEASUREMENTS))
    frozen_path = tmp_path / "frozen-C.json"
    freeze_candidate(
        candidate_id="C",
        weight_sha256=RUN_WEIGHT_SHA256,
        min_confidence=RUN_HIGH_POINT["min_confidence"],
        tracking_iou=RUN_HIGH_POINT["tracking_iou"],
        output=frozen_path,
    )
    task_dataset = _write_json(tmp_path / "task-dataset.json", {"kind": "task_dataset"})
    bundle_inputs = _write_json(
        tmp_path / "bundle-inputs.json",
        {
            "runtime_identity": {
                "package_prefix": "/toolchain/install/so101_demo_py",
                "console_script_path": "/toolchain/install/so101_head_search_calibration",
                "detector_weights_sha256": RUN_WEIGHT_SHA256,
                "torch_version": "2.5.1",
                "ultralytics_version": "8.3.0",
                "cuda_version": "12.4",
                "driver_version": "550.54.14",
                "mujoco_version": "3.2.3",
                "camera_id": "head-cam-0",
                "camera_intrinsics_sha256": canonical_sha256({"seed": "intrinsics"}),
                "tracker_id": "iou-tracker-v1",
                "web_bundle_id": "web-20260930",
            },
            "also_recorded": {},
            "parameter_evidence": {"perception_operating_point": {"parameters": {}}},
        },
    )

    arguments = [
        "run",
        "--run-root",
        str(tmp_path / "run"),
        "--dataset",
        declared["dataset_manifest"]["path"],
        "--candidate",
        declared["model_manifest"]["path"],
        "--geometry-seal",
        str(geometry_path),
        "--episode-partitions",
        declared["scenario_partitions"]["path"],
        "--production-config",
        declared["production_config"]["path"],
        "--camera-config",
        declared["camera_config"]["path"],
        "--production-search-config",
        str(search_path),
        "--admission",
        str(admission_path),
        "--selection-rule",
        str(rule_path),
        "--operating-point-measurements",
        str(measurements_path),
        "--candidate-id",
        "C",
        "--frozen-candidate",
        str(frozen_path),
        "--task-dataset",
        str(task_dataset),
        "--bundle-inputs",
        str(bundle_inputs),
    ]
    # the phase-6 and phase-7 measurement documents this run declares. The synthetic candidate set
    # makes the frozen-candidate gate refuse before either phase reads its measurements, so what these
    # files have to be here is what the CLI validates: a declared input that exists. The phases that
    # consume them are covered, with their own measurement documents, by their own tests.
    measurements = {
        "--search-timing": (
            "search-timing.json",
            {"p99_settle_s": 0.5, "p99_frame_s": 0.1, "control_period_s": 0.05},
        ),
        "--camera-measurements": (
            "camera-measurements.json",
            {
                "horizontal_fov_rad": 0.4,
                "image_width_px": 640,
                "image_height_px": 480,
                "safety_margin_px": 10.0,
                "centre_jitter_rad": 0.002,
            },
        ),
        "--deadband-candidates": (
            "deadband-candidates.json",
            [
                {
                    "center_deadband_px": 18.0,
                    "longest_locked_run_frames": 3,
                    "direction_reversals": 0,
                }
            ],
        ),
        "--workspace-projection": (
            "workspace-projection.json",
            {"top_px": 110.0, "bottom_px": 370.0},
        ),
        "--coarse-step-observations": (
            "coarse-step-observations.json",
            {
                "schema_version": 1,
                "kind": "head_search_coarse_step_val_sweep",
                "phase": "coarse_step_measurement",
                "domain": "head",
                "split": "val",
                "match_radius_px": 8.0,
                "passes": 1,
                "geometry": {
                    "path": str(geometry_path),
                    "sha256": _digest(geometry_path),
                    "seal_sha256": canonical_sha256(RUN_GEOMETRY_BODY),
                    "horizontal_fov_rad": RUN_GEOMETRY_BODY["horizontal_fov_rad"],
                    "lock_valid_neck_rad": list(RUN_GEOMETRY_BODY["lock_valid_neck_rad"]),
                    "required_search_domain_rad": list(
                        RUN_GEOMETRY_BODY["required_search_domain_rad"]
                    ),
                    "anchors_rad": {"default": 0.0},
                },
                "model": {
                    "candidate_id": "C",
                    "weights_sha256": RUN_WEIGHT_SHA256,
                    "min_confidence": RUN_HIGH_POINT["min_confidence"],
                    "tracking_iou": RUN_HIGH_POINT["tracking_iou"],
                },
                "dataset": {
                    "manifest_path": declared["dataset_manifest"]["path"],
                    "manifest_sha256": declared["dataset_manifest"]["sha256"],
                    "split": "val",
                    "scene_count": 2,
                    "scene_limit": None,
                },
                "candidates": [],
                "path": str(tmp_path / "coarse-step-observations.json"),
            },
        ),
        "--fine-correction-episodes": (
            "fine-correction-episodes.json",
            [
                {
                    "split": "held_out_evaluation",
                    "episode_id": "episode-1",
                    "succeeded": True,
                    "fine_corrections": 1,
                    "fine_corrections_rad": [0.01],
                }
            ],
        ),
        "--frame-age-measurements": (
            "frame-age.json",
            {"samples": [{"received_monotonic_s": 0.0, "decision_monotonic_s": 0.02}]},
        ),
        "--skew-measurements": (
            "skew.json",
            {"clock_resolution_s": 0.001, "samples": [{"stamps": [0.0, 0.005, 0.008]}]},
        ),
        "--frame-contract": ("frame-contract.json", {"frame_rate_hz": 10.0}),
        "--controller-submissions": (
            "controller-submissions.json",
            {
                "samples": [
                    {
                        "time_base": "simulation",
                        "submit_snapshot_sim_s": 1.0,
                        "first_target_sim_s": 1.02,
                    }
                ]
            },
        ),
        "--mujoco-measurements": ("mujoco.json", {"simulation_timestep_s": 0.002}),
        "--stationary-measurements": (
            "stationary.json",
            {"samples": [{"velocity_rad_s": [0.0, 0.001]}]},
        ),
        "--feedback-measurements": (
            "feedback.json",
            {"quantisation_rad": 0.0001, "period_s": 0.01},
        ),
        "--controller-stop-config": (
            "controller-stop-config.json",
            {"stopped_tolerance_rad_s": 0.01},
        ),
        "--stop-proofs": (
            "stop-proofs.json",
            {
                "samples": [
                    {
                        "stop_request_monotonic_s": 0.0,
                        "third_confirming_receive_monotonic_s": 0.02,
                    }
                ]
            },
        ),
    }
    for flag, (name, document) in measurements.items():
        arguments.append(flag)
        arguments.append(str(_write_json(tmp_path / name, document)))

    if seal is not None:
        sealed = {name: dict(record) for name, record in declared.items()}
        if seal == "broken":
            sealed["camera_config"]["sha256"] = "0" * 64
        arguments += ["--seal", str(_write_json(tmp_path / "seal.json", sealed))]
    return _without(arguments, omit)


def _without(arguments: list[str], flags: tuple[str, ...]) -> list[str]:
    """The same argument list without the named flags and their single values."""

    remaining: list[str] = []
    index = 0
    while index < len(arguments):
        if arguments[index] in flags:
            index += 2
            continue
        remaining.append(arguments[index])
        index += 1
    return remaining


def test_run_needs_its_declared_inputs_and_claims_no_root(tmp_path: Path, capsys) -> None:
    assert main(["run", "--run-root", str(tmp_path / "run")]) == 2

    assert HEAD_SEARCH_RUN_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "run").exists(), "a refused run must not create its root"


def test_run_refuses_a_controller_without_the_bounded_trajectory_contract(
    tmp_path: Path, capsys
) -> None:
    assert main(_run_arguments(tmp_path, bounded=False)) == 2

    assert "CAL_TRAJECTORY_CONTRACT_UNSATISFIED" in capsys.readouterr().err
    assert not (tmp_path / "run").exists(), "the entry precondition claims no run root"


def test_run_stops_at_the_first_refusing_phase_and_writes_only_the_run_status(
    tmp_path: Path, capsys
) -> None:
    assert main(_run_arguments(tmp_path, seal="broken")) == 2

    root = tmp_path / "run"
    status = json.loads((root / "run-status.json").read_text(encoding="utf-8"))
    assert status["status"] == "FAILED"
    assert status["first_failing_phase"] == "input_validation"
    assert status["failure_code"] == "CAL_INPUT_UNSEALED"
    # HS-233: the run used to write a receipt and a state file that claimed six phases had happened
    assert not (root / "run-receipt.json").exists()
    assert not (root / "calibration-state.json").exists()
    assert not (root / "head-search-calibration-bundle.json").exists()
    assert "RUN_FAILED" in capsys.readouterr().err


def test_run_walks_the_real_phases_and_records_the_gates_own_refusal_code(
    tmp_path: Path, capsys
) -> None:
    """Phases 1-3 are the library modules; phase 4 is the repository's existing gate, not a copy.

    The synthetic inputs name one candidate, so the gate refuses the candidate set before it measures
    anything. That refusal is the gate's own code, and the run records the phase it came from together
    with the evidence the three phases before it produced.
    """

    assert main(_run_arguments(tmp_path)) == 2

    root = tmp_path / "run"
    status = json.loads((root / "run-status.json").read_text(encoding="utf-8"))
    assert status["status"] == "FAILED"
    assert status["first_failing_phase"] == "frozen_candidate_evaluation"
    assert status["failure_code"] == "EVALUATION_CANDIDATE_SET_INVALID"
    assert status["evidence_produced"] == [
        "calibration-inputs.json",
        "geometry-measurements.json",
        "perception-calibration.json",
    ]
    assert "EVALUATION_CANDIDATE_SET_INVALID" in capsys.readouterr().err
    assert not (root / "head-search-calibration-bundle.json").exists()


def test_a_run_root_that_exists_is_not_resumed(tmp_path: Path, capsys) -> None:
    arguments = _run_arguments(tmp_path)
    root = tmp_path / "run"
    root.mkdir()
    (root / "previous.json").write_text("{}\n", encoding="utf-8")

    assert main(arguments) == 2

    assert "RUN_ROOT_ALREADY_EXISTS" in capsys.readouterr().err
    assert {path.name for path in root.iterdir()} == {"previous.json"}


def test_the_run_subcommand_has_no_resume_or_continuation_flag(tmp_path: Path) -> None:
    with pytest.raises(SystemExit) as exited:
        main(["run", "--run-root", str(tmp_path / "run"), "--resume"])

    assert exited.value.code == 2


def test_the_approval_receipt_is_immutable(tmp_path: Path) -> None:
    promoted = _bundle(tmp_path / "promoted")
    run_root = tmp_path / "run"
    arguments = [
        "verify-promoted-config",
        "--run-root",
        str(run_root),
        "--promoted-config",
        str(promoted),
        "--approved-bundle-sha256",
        _digest(promoted),
    ]
    assert main(arguments) == 0
    receipt = run_root / "approval-receipt.json"
    first = receipt.read_text(encoding="utf-8")
    assert main(arguments) == 2, "an approval must not be rewritten"
    assert receipt.read_text(encoding="utf-8") == first


def _digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def test_a_formatting_only_change_is_caught_because_bytes_are_hashed(tmp_path: Path) -> None:
    """Canonical JSON would hide this; hashing the bytes does not."""

    promoted = _bundle(tmp_path / "promoted")
    approved = _digest(promoted)
    reformatted = tmp_path / "promoted" / "reformatted.json"
    reformatted.write_text(
        json.dumps(json.loads(promoted.read_text(encoding="utf-8")), sort_keys=False, indent=4),
        encoding="utf-8",
    )
    assert _digest(reformatted) != approved
    assert (
        main(
            [
                "verify-promoted-config",
                "--run-root",
                str(tmp_path / "run-reformat"),
                "--promoted-config",
                str(reformatted),
                "--approved-bundle-sha256",
                approved,
            ]
        )
        == 2
    )


# --------------------------------------------------------------------------------------------------
# the measurement flight: the installed entry that produces the raw coarse-step val sweep
# --------------------------------------------------------------------------------------------------


def test_the_run_declares_the_coarse_step_sweep_as_its_fifteenth_measurement(tmp_path, capsys) -> None:
    from so101_demo.cli.head_search_calibration import RUN_PHASE_SIX_MEASUREMENTS

    assert ("coarse_step_observations", "--coarse-step-observations", "document") in (
        RUN_PHASE_SIX_MEASUREMENTS
    )
    # a run that declares no sweep is refused at the entry, before it claims a root
    assert main(_run_arguments(tmp_path, omit=("--coarse-step-observations",))) == 2
    assert HEAD_SEARCH_RUN_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "run").exists()


def test_the_run_takes_the_gates_episode_records_as_a_directory(tmp_path, capsys) -> None:
    """Phase 4's gate reads `--episode-records` as a directory of per-seed documents, so the run does."""

    from so101_demo.cli.head_search_calibration import (
        RUN_OPTIONAL_DIRECTORY_FLAGS,
        RUN_OPTIONAL_FILE_FLAGS,
    )

    assert "episode_records" in RUN_OPTIONAL_DIRECTORY_FLAGS
    assert "episode_records" not in RUN_OPTIONAL_FILE_FLAGS
    records = tmp_path / "episodes" / "calibration"
    records.mkdir(parents=True)
    (records / "seed-700000.json").write_text(
        json.dumps({"seed": 700000, "frames": []}) + "\n", encoding="utf-8"
    )
    # the declared directory passes the entry's own path check; the synthetic candidate set then makes
    # the gate refuse at phase 4, which is where this argument set always stops
    arguments = _run_arguments(tmp_path)
    assert main(arguments + ["--episode-records", str(records)]) == 2
    printed = capsys.readouterr().err
    assert "no such input" not in printed
    assert not printed.startswith(HEAD_SEARCH_RUN_INPUTS_INCOMPLETE)
    # a directory that is not there is still refused by name, before any root is claimed
    assert main(arguments + ["--episode-records", str(tmp_path / "absent")]) == 2
    printed = capsys.readouterr().err
    assert printed.startswith(HEAD_SEARCH_RUN_INPUTS_INCOMPLETE)
    assert "no such input" in printed


def test_measure_coarse_step_needs_its_declared_inputs(tmp_path, capsys) -> None:
    assert main(["measure-coarse-step"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "measurement").exists()


def test_measure_coarse_step_refuses_a_missing_input_and_an_existing_output(tmp_path, capsys) -> None:
    declared = {
        "--geometry-seal": tmp_path / "geometry-seal.json",
        "--head-dataset": tmp_path / "head-dataset.json",
        "--dataset-config": tmp_path / "head_camera_yolo_seg.yaml",
        "--weights": tmp_path / "C.pt",
        "--frozen-candidate": tmp_path / "frozen-c.json",
        "--output-dir": tmp_path / "measurement",
    }
    arguments = ["measure-coarse-step"]
    for flag, path in declared.items():
        arguments += [flag, str(path)]
    assert main(arguments) == 2
    assert "no such input" in capsys.readouterr().err

    for flag, path in declared.items():
        if flag == "--output-dir":
            continue
        path.write_text("{}", encoding="utf-8")
    declared["--output-dir"].mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_coarse_step_parses_and_hands_the_flight_to_the_library(tmp_path, monkeypatch, capsys) -> None:
    """The CLI is a parser and a validator: the measurement itself is the library module's."""

    from so101_demo.act import head_search_coarse_step_measurement

    input_paths = {}
    for flag, name in (
        ("--geometry-seal", "geometry-seal.json"),
        ("--head-dataset", "head-dataset.json"),
        ("--dataset-config", "head_camera_yolo_seg.yaml"),
        ("--weights", "C.pt"),
        ("--frozen-candidate", "frozen-c.json"),
    ):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        input_paths[flag] = path
    output = tmp_path / "measurement"
    seen = {}

    def fake_measure(**arguments):
        seen.update(arguments)
        return {"receipt": {"chosen_coarse_step_rad": 0.6560533740603397, "scene_count": 200,
                            "candidate_count": 6, "passes": 2}}

    monkeypatch.setattr(
        head_search_coarse_step_measurement, "measure_coarse_step_val_sweep", fake_measure
    )
    arguments = ["measure-coarse-step"]
    for flag, path in input_paths.items():
        arguments += [flag, str(path)]
    arguments += ["--output-dir", str(output), "--passes", "2", "--scene-limit", "8"]

    assert main(arguments) == 0

    assert seen["geometry_seal_path"] == input_paths["--geometry-seal"]
    assert seen["dataset_manifest_path"] == input_paths["--head-dataset"]
    assert seen["dataset_config_path"] == input_paths["--dataset-config"]
    assert seen["weights_path"] == input_paths["--weights"]
    assert seen["frozen_candidate_path"] == input_paths["--frozen-candidate"]
    assert seen["output_dir"] == output
    assert seen["passes"] == 2
    assert seen["scene_limit"] == 8
    assert seen["command"].startswith(
        "ros2 run so101_demo_py so101_head_search_calibration measure-coarse-step"
    )
    assert "COARSE_STEP_MEASURED 0.6560533740603397" in capsys.readouterr().out


# --------------------------------------------------------------------------------------------------
# the sealed scene's simulation timestep: the installed entry that produces the phase-7 document
# --------------------------------------------------------------------------------------------------


def _mujoco_inputs(tmp_path: Path) -> dict:
    """A tiny sealed scene and the geometry seal that pins it: the CLI's own end-to-end fixtures."""

    import hashlib

    scene = tmp_path / "head_search_scene.xml"
    scene.write_text(
        '<mujoco model="fixture">\n  <option timestep="0.002" gravity="0 0 -9.81"/>\n</mujoco>\n',
        encoding="utf-8",
    )
    seal = tmp_path / "head-camera-geometry.json"
    seal.write_text(
        json.dumps({"source_digests": {"scene_sha256": hashlib.sha256(scene.read_bytes()).hexdigest()}}),
        encoding="utf-8",
    )
    return {"scene": scene, "seal": seal}


def test_measure_mujoco_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-mujoco"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "measurement").exists()


def test_measure_mujoco_refuses_a_missing_input_and_an_existing_output(tmp_path: Path, capsys) -> None:
    inputs = _mujoco_inputs(tmp_path)
    arguments = [
        "measure-mujoco",
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--output-dir",
        str(tmp_path / "measurement"),
    ]
    assert main([arguments[0], "--scene", str(tmp_path / "absent.xml"), *arguments[3:]]) == 2
    assert "no such input" in capsys.readouterr().err

    (tmp_path / "measurement").mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_mujoco_refuses_a_scene_nothing_seals(tmp_path: Path, capsys) -> None:
    inputs = _mujoco_inputs(tmp_path)

    assert (
        main(
            [
                "measure-mujoco",
                "--scene",
                str(inputs["scene"]),
                "--output-dir",
                str(tmp_path / "measurement"),
            ]
        )
        == 2
    )
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "measurement").exists()


def test_measure_mujoco_produces_the_document_the_run_declares(tmp_path: Path, capsys) -> None:
    inputs = _mujoco_inputs(tmp_path)
    output = tmp_path / "measurement"

    assert (
        main(
            [
                "measure-mujoco",
                "--scene",
                str(inputs["scene"]),
                "--geometry-seal",
                str(inputs["seal"]),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )

    printed = capsys.readouterr().out
    assert "MUJOCO_TIMESTEP_PRODUCED 0.002" in printed
    document = json.loads((output / "mujoco-measurements.json").read_text(encoding="utf-8"))
    assert document["simulation_timestep_s"] == pytest.approx(0.002)
    assert document["path"] == str(output / "mujoco-measurements.json")
    assert document["mujoco_readback"] is False
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["measurement_sha256"] == document["sha256"]
    assert receipt["runtime_identity"]["motion_commanded"] is False


# --- measure-search-timing ------------------------------------------------------------------------

#: a minimal sealed-scene stand-in: a yaw hinge with a position actuator and the head camera, so the
#: installed entry's own sweep runs against a real MuJoCo model without a detector, a GPU or a renderer
TIMING_SCENE = """<mujoco model="timing-fixture">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="head_mount">
      <joint name="neck_yaw_joint" type="hinge" axis="0 0 1" damping="0.05" armature="0.001"/>
      <geom name="head_geom" type="box" size="0.05 0.05 0.05"/>
      <camera name="head_camera" pos="0 0 0.05" fovy="60" xyaxes="1 0 0 0 1 0"/>
    </body>
  </worldbody>
  <actuator>
    <position name="neck_yaw_joint" joint="neck_yaw_joint" kp="8" kv="0.6"
              forcelimited="false" ctrllimited="false"/>
  </actuator>
</mujoco>
"""

TIMING_CONTROLLERS = """controller_manager:
  ros__parameters:
    update_rate: 500
"""


def _timing_inputs(tmp_path: Path) -> dict:
    """The four declared inputs of the sweep-timing measurement, with one sealed anchor."""

    scene = tmp_path / "head_search_scene.xml"
    scene.write_text(TIMING_SCENE, encoding="utf-8")
    seal = tmp_path / "head-camera-geometry.json"
    seal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "camera_name": "head_camera",
                "camera": {"camera_name": "head_camera", "parent_body": "head_mount", "width": 64, "height": 48},
                "image_width": 64,
                "image_height": 48,
                "horizontal_fov_rad": 1.3121067481206794,
                "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
                "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                "in_frame_matrix": {"default": {"neck_start_rad": 0.1}},
                "source_digests": {"scene_sha256": hashlib.sha256(scene.read_bytes()).hexdigest()},
            }
        ),
        encoding="utf-8",
    )
    production = tmp_path / "head_search_v2.json"
    production.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "camera": {
                    "name": "head_camera",
                    "frame_id": "head_camera_optical_frame",
                    "ray_origin_frame_id": "base_link",
                },
                "motion": {"settle_velocity_rad_s": 0.05, "goal_tolerance_rad": 0.05},
                "tracker": {"name": "bytetrack", "iou_threshold": 0.3},
                "values": {
                    "coarse_step_rad": 0.3,
                    "horizontal_fov_rad": 1.3121067481206794,
                    "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                    "max_age_s": 0.05,
                    "max_skew_s": 0.02,
                    "search_timeout_s": 12.0,
                    "center_deadband_px": 18.0,
                    "vertical_bounds_px": [11.0, 37.0],
                    "min_area_px2": 64.0,
                    "min_confidence": 0.4,
                    "tracking_iou": 0.3,
                    "max_fine_corrections": 4,
                    "max_fine_total_rad": 0.4,
                    "stop_velocity_rad_s": 0.05,
                    "min_bbox_aspect": 0.5,
                    "stop_latency_s": 0.06,
                    "submit_lead_s": 0.02,
                },
            }
        ),
        encoding="utf-8",
    )
    controllers = tmp_path / "ros2_controllers.yaml"
    controllers.write_text(TIMING_CONTROLLERS, encoding="utf-8")
    return {
        "scene": scene,
        "seal": seal,
        "production": production,
        "controllers": controllers,
    }


def _timing_arguments(inputs: dict, output: Path) -> list:
    return [
        "measure-search-timing",
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--production-search-config",
        str(inputs["production"]),
        "--controller-config",
        str(inputs["controllers"]),
        "--output-dir",
        str(output),
    ]


def test_measure_search_timing_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-search-timing"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "sweep-timing").exists()


def test_measure_search_timing_refuses_a_missing_input_and_an_existing_output(
    tmp_path: Path, capsys
) -> None:
    inputs = _timing_inputs(tmp_path)
    output = tmp_path / "sweep-timing"
    arguments = _timing_arguments(inputs, output)

    assert main([arguments[0], "--scene", str(tmp_path / "absent.xml"), *arguments[3:]]) == 2
    assert "no such input" in capsys.readouterr().err

    output.mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_search_timing_sweeps_without_a_detector_and_invents_no_frame_age(
    tmp_path: Path, capsys
) -> None:
    inputs = _timing_inputs(tmp_path)
    output = tmp_path / "sweep-timing"

    assert main(_timing_arguments(inputs, output)) == 0

    printed = capsys.readouterr().out
    assert "SEARCH_TIMING_MEASURED" in printed
    assert "p99_frame_s=None" in printed
    document = json.loads((output / "search-timing.json").read_text(encoding="utf-8"))
    assert document["p99_settle_s"] > 0.0
    assert document["p99_frame_s"] is None
    assert document["stable_stop_count"] == 2
    assert document["time_base"] == "simulation"
    assert not (output / "frame-age-measurements.json").exists()
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["search_timing_sha256"] == document["sha256"]
    assert receipt["ros_nodes_started"] is False


# --- measure-deadband-candidates --------------------------------------------------------------------

#: the sealed scene stand-in of the deadband entry: the same yaw hinge and head camera, plus the cup the
#: anchor places. The trials themselves are handed to a declared plant and detector in these tests, so no
#: detector, GPU, renderer or ROS is needed to exercise the entry end to end
DEADBAND_SCENE = """<mujoco model="deadband-fixture">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="cup">
      <joint name="cup_free_joint" type="free"/>
      <geom name="cup_geom" type="cylinder" size="0.04 0.045"/>
    </body>
    <body name="head_mount">
      <joint name="neck_yaw_joint" type="hinge" axis="0 0 1" damping="0.05" armature="0.001"/>
      <geom name="head_geom" type="box" size="0.05 0.05 0.05"/>
      <camera name="head_camera" pos="0 0 0.05" fovy="60" xyaxes="1 0 0 0 1 0"/>
    </body>
  </worldbody>
  <actuator>
    <position name="neck_yaw_joint" joint="neck_yaw_joint" kp="8" kv="0.6"
              forcelimited="false" ctrllimited="false"/>
  </actuator>
</mujoco>
"""


def _deadband_inputs(tmp_path: Path) -> dict:
    """The six declared inputs of the lock-trial measurement, with one sealed anchor."""

    scene = tmp_path / "head_search_scene.xml"
    scene.write_text(DEADBAND_SCENE, encoding="utf-8")
    scene_sha256 = hashlib.sha256(scene.read_bytes()).hexdigest()
    seal = tmp_path / "head-camera-geometry.json"
    seal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "camera_name": "head_camera",
                "camera": {
                    "camera_name": "head_camera",
                    "parent_body": "head_mount",
                    "width": 640,
                    "height": 480,
                    "fovy_rad": 1.0471975511965976,
                },
                "image_width": 640,
                "image_height": 480,
                "horizontal_fov_rad": 1.3121067481206794,
                "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
                "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                "in_frame_matrix": {"left": {"neck_start_rad": 0.0}},
                "workspace_matrix": {
                    "key_samples": [
                        {"anchor": "left", "kind": "anchor", "point_m": [-0.08, -0.28, 0.165]}
                    ]
                },
                "source_digests": {"scene_sha256": scene_sha256},
            }
        ),
        encoding="utf-8",
    )
    weights = tmp_path / "C.pt"
    weights.write_bytes(b"selected-model")
    production = tmp_path / "head_search_v2.json"
    production.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runtime_id": "head-search-v2",
                "weight_path": "models/head-search/yolo11n-seg-best.pt",
                "weight_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
                "camera": {
                    "name": "head_camera",
                    "frame_id": "head_camera_optical_frame",
                    "ray_origin_frame_id": "base_link",
                },
                "motion": {"settle_velocity_rad_s": 0.05, "goal_tolerance_rad": 0.05},
                "tracker": {"name": "bytetrack", "iou_threshold": 0.3},
                "values": {
                    "coarse_step_rad": 0.3,
                    "horizontal_fov_rad": 1.3121067481206794,
                    "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                    "max_age_s": 0.05,
                    "max_skew_s": 0.02,
                    "search_timeout_s": 12.0,
                    "center_deadband_px": 18.0,
                    "vertical_bounds_px": [110.0, 370.0],
                    "min_area_px2": 64.0,
                    "min_confidence": 0.4,
                    "tracking_iou": 0.3,
                    "max_fine_corrections": 4,
                    "max_fine_total_rad": 0.4,
                    "min_bbox_aspect": 0.5,
                },
            }
        ),
        encoding="utf-8",
    )
    frozen = tmp_path / "frozen-c.json"
    frozen.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "head-search-frozen-candidate",
                "candidate_id": "C",
                "weight_sha256": hashlib.sha256(weights.read_bytes()).hexdigest(),
                "operating_points": {
                    "head": {"min_confidence": 0.25, "tracker": {"iou": 0.5}},
                    "task": {"min_confidence": 0.25, "tracker": {"iou": 0.5}},
                },
            }
        ),
        encoding="utf-8",
    )
    controllers = tmp_path / "ros2_controllers.yaml"
    controllers.write_text(TIMING_CONTROLLERS, encoding="utf-8")
    return {
        "scene": scene,
        "seal": seal,
        "production": production,
        "controllers": controllers,
        "weights": weights,
        "frozen": frozen,
    }


def _deadband_arguments(inputs: dict, output: Path) -> list:
    return [
        "measure-deadband-candidates",
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--production-search-config",
        str(inputs["production"]),
        "--controller-config",
        str(inputs["controllers"]),
        "--frozen-candidate",
        str(inputs["frozen"]),
        "--weights",
        str(inputs["weights"]),
        "--output-dir",
        str(output),
        "--candidate",
        "18",
        "--candidate",
        "2",
    ]


def test_the_deadband_detector_wrapper_drives_the_production_head_detector() -> None:
    """The wrapper is called against the real `HeadRgbDetector`, with only its model port stubbed.

    `HeadRgbDetector.detect` takes the RGB array and its identity as keyword arguments and builds the
    detection frame itself; a wrapper that passed a frame positionally would only fail once a real model
    was loaded. This pins the call convention without a detector, a GPU or a weights file.
    """

    import numpy as np
    from so101_demo.act.head_search_deadband_measurement import ProductionHeadDetector
    from so101_demo.adapters.act.detector import HeadRgbDetector
    from so101_demo.core.detection import DetectionBatch, DetectionCandidate

    def _cup_mask():
        mask = np.zeros((480, 640), dtype=bool)
        mask[190:290, 270:370] = True
        return mask

    class Port:
        """The model port `HeadRgbDetector` wraps: one cup, one instance, one frame."""

        def detect(self, frame, query):
            assert query.class_id == "plastic_cup"
            return DetectionBatch(
                model_id="selected",
                weights_sha256="a" * 64,
                runtime_device="cuda",
                inference_latency_ms=1.0,
                image_width=640,
                image_height=480,
                candidates=(
                    DetectionCandidate(
                        instance_id="i0",
                        class_id="plastic_cup",
                        confidence=0.9,
                        bbox_xyxy=(270.0, 190.0, 370.0, 290.0),
                        mask=_cup_mask(),
                        source_stamp_ns=frame.source_stamp_ns,
                        source_frame_id=frame.source_frame_id,
                        image_width=640,
                        image_height=480,
                    ),
                ),
            )

    head = HeadRgbDetector(
        Port(),
        model_id="selected",
        weights_sha256="a" * 64,
        tracking_iou=0.5,
        min_bbox_aspect=0.5,
    )
    wrapper = ProductionHeadDetector(
        head,
        session_id="session",
        attempt_id="attempt",
        frame_id="head_camera_optical_frame",
    )
    image = np.zeros((480, 640, 3), dtype=np.uint8)

    found = wrapper(image, 1_000_000)
    assert [detection["track_id"] for detection in found] == ["head-cup-0"]
    assert tuple(found[0]["xyxy"]) == (270.0, 190.0, 370.0, 290.0)
    assert found[0]["confidence"] == 0.9
    assert found[0]["class_id"] == 0

    # the same cup in the next frame keeps its track, and a reset starts a new one
    assert [detection["track_id"] for detection in wrapper(image, 2_000_000)] == ["head-cup-0"]
    wrapper.reset()
    assert [detection["track_id"] for detection in wrapper(image, 3_000_000)] == ["head-cup-0"]


def test_the_real_mujoco_plant_places_the_anchor_cup_and_settles(tmp_path: Path) -> None:
    """The entry's own plant is built for real here, so a typo in its MuJoCo calls cannot hide.

    Only the plant is exercised - the renderer is not opened and no detector is loaded - but this is the
    code path the installed entry really runs, and it constructs the model, places the anchor's cup,
    commands the neck actuator, applies the declared settle rule and reads the camera's own geometry.
    """

    from so101_demo.act import head_search_deadband_measurement as measurement

    inputs = _deadband_inputs(tmp_path)
    plant = measurement.MujocoClosedLoopPlant(
        {
            "scene_path": str(inputs["scene"]),
            "camera_name": "head_camera",
            "image_width": 640,
            "image_height": 48,
            "fovy_rad": 1.0471975511965976,
            "control_period_s": 0.002,
            "frame_period_s": 0.1,
            "max_settle_s": 5.0,
            "settle_consecutive_steps": 5,
            "settle_velocity_rad_s": 0.05,
            "goal_tolerance_rad": 0.05,
            "start_rad": 0.0,
            "cup_start_m": [-0.08, -0.28, 0.165],
            "cup_joint": "cup_free_joint",
            "cup_body": "cup",
        }
    )
    assert plant.simulation_timestep_s == 0.002
    assert plant.yaw_rad == 0.0
    assert plant.cup_position_m == [-0.08, -0.28, 0.165]

    stop = plant.settle_to(0.0)
    assert stop["settled"] is True and stop["reached"] is True
    assert math.isclose(stop["settle_s"], stop["steps"] * 0.002, rel_tol=0.0, abs_tol=1e-12)
    assert plant.time_s > 0.0
    assert plant.frame_stamp_ns == int(round(plant.time_s * 1e9))

    geometry = plant.optical_geometry()
    assert geometry["k"][2] == 320.0 and geometry["k"][5] == 24.0
    assert geometry["k"][0] > 0.0
    rotation = geometry["rotation_optical_to_base"]
    assert len(rotation) == 3 and all(len(row) == 3 for row in rotation)
    plant.close()


def test_the_real_episode_plant_captures_the_prepared_cup_after_it_enters_the_scene(
    tmp_path: Path,
) -> None:
    """The prepared-cup capture has to happen *after* the prepared state is in the model.

    The real run's first document reported a 0.066-0.140 m drift for every episode: the capture was taken
    before `mj_forward`, so it recorded the anchor placement the base plant had put the cup at instead of
    the one the dataset preparation had. This builds the real plant on the fixture scene, hands it a
    prepared state that moves the cup, and pins which position is reported as the prepared one.
    """

    import mujoco
    from so101_demo.act.head_search_fine_correction_episodes import MujocoEpisodePlant

    inputs = _fine_correction_inputs(tmp_path)
    request = {
        "scene_path": str(inputs["scene"]),
        "camera_name": "head_camera",
        "image_width": 640,
        "image_height": 480,
        "fovy_rad": 1.0471975511965976,
        "control_period_s": 0.002,
        "frame_period_s": 0.1,
        "max_settle_s": 5.0,
        "settle_consecutive_steps": 5,
        "settle_velocity_rad_s": 0.05,
        "goal_tolerance_rad": 0.05,
        "start_rad": 0.0,
        "cup_start_m": [-0.08, -0.28, 0.165],
        "cup_joint": "cup_free_joint",
        "cup_body": "cup",
    }
    plain = MujocoEpisodePlant(request)
    assert plain.prepared_cup_position_m == [-0.08, -0.28, 0.165]
    prepared_cup = [0.05, -0.30, 0.165]
    joint = mujoco.mj_name2id(plain._model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    address = int(plain._model.jnt_qposadr[joint])
    state = {
        "qpos": [float(value) for value in plain._data.qpos],
        "qvel": [0.0] * int(plain._model.nq),
        "cam_pos": [[float(value) for value in row] for row in plain._model.cam_pos],
        "mat_rgba": [[float(value) for value in row] for row in plain._model.mat_rgba],
    }
    state["qpos"][address : address + 3] = prepared_cup
    plain.close()

    plant = MujocoEpisodePlant({**request, "scene_state": state})

    assert plant.prepared_cup_position_m == pytest.approx(prepared_cup)
    assert plant.cup_position_m == pytest.approx(prepared_cup)
    assert plant.prepared_cup_position_m != request["cup_start_m"]
    plant.close()


def test_measure_deadband_candidates_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-deadband-candidates"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "deadband").exists()


def test_measure_deadband_candidates_refuses_a_missing_input_an_existing_output_and_no_candidate(
    tmp_path: Path, capsys
) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "deadband"
    arguments = _deadband_arguments(inputs, output)

    assert main([arguments[0], "--scene", str(tmp_path / "absent.xml"), *arguments[3:]]) == 2
    assert "no such input" in capsys.readouterr().err

    output.mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err

    output.rmdir()
    assert main(arguments[:-4]) == 2  # the two declared candidates are the last four arguments
    assert "--candidate" in capsys.readouterr().err


def test_measure_deadband_candidates_hands_the_flight_to_the_library(tmp_path: Path, capsys, monkeypatch) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "deadband"
    from so101_demo.act import head_search_deadband_measurement as measurement

    class Plant:
        """A yaw-only plant whose cup sits at the principal point once the neck reaches the anchor."""

        def __init__(self, request) -> None:
            self.request = request
            self.simulation_timestep_s = 0.002
            self.yaw_rad = 0.0
            self.velocity_rad_s = 0.0
            self.time_s = 0.0
            self.stops = 0

        @property
        def frame_stamp_ns(self) -> int:
            return int(round(self.time_s * 1e9))

        def settle_to(self, target_rad: float) -> dict:
            start, rad = self.time_s, self.yaw_rad
            self.yaw_rad, self.time_s = float(target_rad), self.time_s + 0.01
            self.stops += 1
            return {
                "target_rad": float(target_rad),
                "start_rad": rad,
                "sim_start_s": start,
                "sim_end_s": self.time_s,
                "steps": 5,
                "settle_s": self.time_s - start,
                "settled": True,
                "reached": True,
                "final_velocity_rad_s": 0.0,
                "final_position_error_rad": 0.0,
                "quiet_steps": 5,
            }

        def render_frame(self):
            return {"yaw_rad": self.yaw_rad}

        def optical_geometry(self) -> dict:
            return {
                "k": (415.69219381653056, 0.0, 320.0, 0.0, 415.69219381653056, 240.0, 0.0, 0.0, 1.0),
                "distortion": (0.0, 0.0, 0.0, 0.0, 0.0),
                "rotation_optical_to_base": (
                    (-1.0, 0.0, 0.0),
                    (0.0, 0.6, -0.8),
                    (0.0, -0.8, -0.6),
                ),
            }

    class Detector:
        """A cup that sits on the principal point: every candidate locks on the first frame."""

        def __init__(self, plant) -> None:
            self.plant = plant

        def reset(self) -> None:
            pass

        def __call__(self, image, stamp_ns):
            return [
                {
                    "xyxy": (270.0, 190.0, 370.0, 290.0),
                    "confidence": 0.9,
                    "class_id": 0,
                    "track_id": "head-cup-0",
                }
            ]

    monkeypatch.setattr(measurement, "MujocoClosedLoopPlant", Plant)
    monkeypatch.setattr(
        measurement,
        "build_production_head_detector",
        lambda **kwargs: Detector(None),
    )

    assert main(_deadband_arguments(inputs, output)) == 0

    printed = capsys.readouterr().out
    assert "DEADBAND_CANDIDATES_MEASURED" in printed
    assert "candidates=2" in printed
    assert f"output_dir={output}" in printed
    document = json.loads((output / "deadband-candidates.json").read_text(encoding="utf-8"))
    assert [record["center_deadband_px"] for record in document["records"]] == [18.0, 2.0]
    assert all(record["longest_locked_run_frames"] >= 3 for record in document["records"])
    assert all(record["direction_reversals"] == 0 for record in document["records"])
    assert document["detector_operating_point"] == {"min_confidence": 0.25, "iou": 0.5}
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["document_sha256"] == document["sha256"]
    assert receipt["anchor_names"] == ["left"]
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False


def test_measure_deadband_candidates_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "deadband"
    from so101_demo.act import head_search_deadband_measurement as measurement

    def refuse(request):
        raise measurement.CalibrationDeadbandMeasurementRefused(
            measurement.CAL_DEADBAND_CUP_LOST, "the detector found no cup at all"
        )

    monkeypatch.setattr(measurement, "MujocoClosedLoopPlant", refuse)
    monkeypatch.setattr(measurement, "build_production_head_detector", lambda **kwargs: None)

    assert main(_deadband_arguments(inputs, output)) == 2
    assert measurement.CAL_DEADBAND_CUP_LOST in capsys.readouterr().err


# --- measure-camera ---------------------------------------------------------------------------------


def _camera_arguments(inputs: dict, output: Path, *, safety_margin=None) -> list:
    arguments = [
        "measure-camera",
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--production-search-config",
        str(inputs["production"]),
        "--controller-config",
        str(inputs["controllers"]),
        "--frozen-candidate",
        str(inputs["frozen"]),
        "--weights",
        str(inputs["weights"]),
        "--output-dir",
        str(output),
        "--anchor",
        "left",
        "--device",
        "cuda",
    ]
    if safety_margin is not None:
        arguments += ["--safety-margin-declaration", str(safety_margin)]
    return arguments


class _CameraPlant:
    """A yaw-only plant that holds every commanded pose; the entry's own plant is stubbed in here."""

    def __init__(self, request) -> None:
        self.request = request
        self.simulation_timestep_s = 0.002
        self.yaw_rad = float(request["start_rad"])
        self.velocity_rad_s = 0.0
        self.time_s = 0.0
        self.commands: list[float] = []

    def settle_to(self, target_rad: float) -> dict:
        start, rad = self.time_s, self.yaw_rad
        self.commands.append(float(target_rad))
        self.yaw_rad, self.time_s = float(target_rad), self.time_s + 0.01
        return {
            "target_rad": float(target_rad),
            "start_rad": rad,
            "sim_start_s": start,
            "sim_end_s": self.time_s,
            "steps": 5,
            "settle_s": self.time_s - start,
            "settled": True,
            "reached": True,
            "final_velocity_rad_s": 0.0,
            "final_position_error_rad": 0.0,
            "quiet_steps": 5,
        }

    @property
    def frame_stamp_ns(self) -> int:
        return int(round(self.time_s * 1e9))

    def render_frame(self):
        return {"yaw_rad": self.yaw_rad, "frame": self.time_s}

    def optical_geometry(self) -> dict:
        return {
            "k": (415.69219381653056, 0.0, 320.0, 0.0, 415.69219381653056, 240.0, 0.0, 0.0, 1.0),
            "distortion": (0.0, 0.0, 0.0, 0.0, 0.0),
            "rotation_optical_to_base": ((-1.0, 0.0, 0.0), (0.0, 0.6, -0.8), (0.0, -0.8, -0.6)),
        }

    def close(self) -> None:
        pass


class _CameraDetector:
    """One cup whose centre wobbles by a declared pixel offset: a real, non-zero spread."""

    #: every pose is held for three whole periods of this cycle, so every pose measures the same spread
    OFFSETS_PX = (0.0, 1.0, 1.0, 0.0)

    def __init__(self, plant) -> None:
        self.plant = plant
        self.calls = 0

    def reset(self) -> None:
        self.calls = 0

    def __call__(self, image, stamp_ns):
        column = 320.0 + self.OFFSETS_PX[self.calls % len(self.OFFSETS_PX)]
        self.calls += 1
        return [
            {
                "xyxy": (column - 50.0, 190.0, column + 50.0, 290.0),
                "confidence": 0.9,
                "class_id": 0,
                "track_id": "head-cup-0",
            }
        ]


def test_measure_camera_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-camera"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "camera").exists()


def test_measure_camera_refuses_a_missing_input_and_an_existing_output(tmp_path: Path, capsys) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "camera"
    arguments = _camera_arguments(inputs, output)

    assert main([arguments[0], "--scene", str(tmp_path / "absent.xml"), *arguments[3:]]) == 2
    assert "no such input" in capsys.readouterr().err

    output.mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_camera_hands_the_flight_to_the_library_and_refuses_an_undeclared_margin(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """The measured jitter is written; the undeclared safety margin is recorded and refused, never made up."""

    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "camera"
    from so101_demo.act import head_search_camera_measurement as measurement

    monkeypatch.setattr(measurement, "MujocoClosedLoopPlant", _CameraPlant)
    monkeypatch.setattr(
        measurement, "build_production_head_detector", lambda **kwargs: _CameraDetector(None)
    )

    assert main(_camera_arguments(inputs, output)) == 2

    captured = capsys.readouterr()
    assert measurement.CAL_CAMERA_SAFETY_MARGIN_UNDECLARED in captured.err
    assert "CAMERA_MEASUREMENTS_MEASURED" in captured.out

    document = json.loads((output / "camera-measurements.json").read_text(encoding="utf-8"))
    assert document["safety_margin_px"] is None
    assert document["horizontal_fov_rad"] == 1.3121067481206794
    assert document["image_width_px"] == 640
    assert document["image_height_px"] == 480
    # twelve frames per pose is three whole periods of the wobble cycle
    assert document["centre_jitter_px"] == pytest.approx(
        measurement.spread(_CameraDetector.OFFSETS_PX * 3)["std"]
    )
    assert document["centre_jitter_rad"] == pytest.approx(
        document["centre_jitter_px"] * 1.3121067481206794 / 640
    )
    assert document["frames_per_pose"] == 12
    assert document["pose_count"] == 3
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["document_sha256"] == document["sha256"]
    assert receipt["status"] == "MEASURED_WITH_REFUSED_FIELD"
    assert receipt["fields_refused"] == ["safety_margin_px"]
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False


def test_measure_camera_accepts_a_declared_safety_margin_and_returns_zero(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "camera"
    declaration = tmp_path / "camera-safety.json"
    declaration.write_text(json.dumps({"safety_margin_px": 4.0}), encoding="utf-8")
    from so101_demo.act import head_search_camera_measurement as measurement

    monkeypatch.setattr(measurement, "MujocoClosedLoopPlant", _CameraPlant)
    monkeypatch.setattr(
        measurement, "build_production_head_detector", lambda **kwargs: _CameraDetector(None)
    )

    assert main(_camera_arguments(inputs, output, safety_margin=declaration)) == 0

    captured = capsys.readouterr()
    assert "CAMERA_MEASUREMENTS_MEASURED" in captured.out
    assert measurement.CAL_CAMERA_SAFETY_MARGIN_UNDECLARED not in captured.err

    document = json.loads((output / "camera-measurements.json").read_text(encoding="utf-8"))
    assert document["safety_margin_px"] == 4.0
    assert document["safety_margin"]["measured_here"] is False
    assert document["safety_margin"]["declared_by"]["path"] == str(declaration)
    assert document["refusals"] == []


def test_measure_camera_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _deadband_inputs(tmp_path)
    output = tmp_path / "camera"
    from so101_demo.act import head_search_camera_measurement as measurement

    def refuse(request):
        raise measurement.CalibrationCameraMeasurementRefused(
            measurement.CAL_CAMERA_CUP_LOST, "the detector found no cup in any frame"
        )

    monkeypatch.setattr(measurement, "MujocoClosedLoopPlant", refuse)
    monkeypatch.setattr(measurement, "build_production_head_detector", lambda **kwargs: None)

    assert main(_camera_arguments(inputs, output)) == 2
    assert measurement.CAL_CAMERA_CUP_LOST in capsys.readouterr().err


# --- the stop, feedback, submission and stop-proof measurement entries --------------------------------

#: the installed controller's own stopped tolerance, as its header declares it
STOP_DECLARATION = """class ControllerStopWitness final
{
public:
  static constexpr size_t required_samples = 51;
  static constexpr int64_t step_ns = 2000000;
  static constexpr int64_t max_age_ns = 200000000;
  static constexpr double stop_velocity_rad_s = 0.002;
};
"""


#: the shared fixture declares the controller manager's rate only; the stop path's feedback period is the
#: broadcaster's rate, so the stop measurements declare both rates the way the installed configuration does
STOP_CONTROLLERS = """controller_manager:
  ros__parameters:
    update_rate: 500
joint_state_broadcaster:
  ros__parameters:
    update_rate: 100
"""


def _stop_inputs(tmp_path: Path) -> dict:
    """The declared inputs of the stop measurements: the shared fixture plus the declared stop values."""

    inputs = _deadband_inputs(tmp_path)
    controllers = tmp_path / "stop_ros2_controllers.yaml"
    controllers.write_text(STOP_CONTROLLERS, encoding="utf-8")
    inputs["controllers"] = controllers
    production = json.loads(inputs["production"].read_text(encoding="utf-8"))
    production["values"].update(
        {"stop_velocity_rad_s": 0.05, "stop_latency_s": 0.06, "submit_lead_s": 0.02}
    )
    declared = tmp_path / "head_search_v2_stop.json"
    declared.write_text(json.dumps(production), encoding="utf-8")
    inputs["production"] = declared
    inputs["declaration"] = tmp_path / "controller_stop_witness.hpp"
    inputs["declaration"].write_text(STOP_DECLARATION, encoding="utf-8")
    return inputs


class _StopPlant:
    """A plant that admits every goal at the next control cycle and then reports stopped feedback."""

    def __init__(self, request) -> None:
        self.request = request
        self.simulation_timestep_s = 0.002
        self.control_period_s = float(request.get("control_period_s") or 0.002)
        self.feedback_period_s = float(request.get("feedback_period_s") or 0.01)
        self.time_s = 0.0
        self.reference_rad = float(request["start_rad"])
        self.admissions: list[dict] = []
        self.holds: list[float] = []

    @property
    def yaw_rad(self) -> float:
        return self.reference_rad

    def command_through_admission(self, target_rad, *, purpose, max_cycles=None):
        snapshot = self.time_s
        cycles = 4 if max_cycles is None else int(max_cycles)
        self.admissions.append({"purpose": purpose, "target_rad": float(target_rad)})
        reference_before = self.reference_rad
        for _ in range(cycles):
            self.step_control_cycle()
        return {
            "purpose": purpose,
            "target_rad": float(target_rad),
            "reference_before_rad": reference_before,
            "submit_snapshot_sim_s": snapshot,
            "first_target_sim_s": snapshot + self.simulation_timestep_s,
            "plant_consumed_sim_s": snapshot + self.simulation_timestep_s,
            "lead_s": self.simulation_timestep_s,
            "steps": cycles,
            "control_cycles": cycles,
            "settled": max_cycles is None,
            "reached": True,
            "final_velocity_rad_s": 0.0,
            "final_position_error_rad": 0.0,
            "quiet_steps": 5,
        }

    def hold_command(self, rad: float) -> None:
        self.holds.append(float(rad))
        self.reference_rad = float(rad)

    def step_control_cycle(self) -> None:
        self.time_s += self.control_period_s

    def feedback_sample(self) -> dict:
        return {
            "sim_s": self.time_s,
            "monotonic_s": 0.0,
            "yaw_rad": self.yaw_rad,
            "reference_rad": self.reference_rad,
            "position_error_rad": 0.0,
            "velocity_rad_s": [0.0] * 6 + [0.001],
            "joint_positions": [0.0] * 7,
            "joint_velocities": [0.0] * 6 + [0.001],
        }

    def real_time_factor(self) -> float:
        return 1.0

    def close(self) -> None:
        pass


def _stop_flight_arguments(subcommand: str, inputs: dict, output: Path) -> list:
    return [
        subcommand,
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--production-search-config",
        str(inputs["production"]),
        "--controller-config",
        str(inputs["controllers"]),
        "--output-dir",
        str(output),
        "--anchor",
        "left",
    ]


def test_measure_controller_stop_config_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-controller-stop-config"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
    assert not (tmp_path / "stop-config").exists()


def test_measure_controller_stop_config_writes_the_declared_tolerance(tmp_path: Path, capsys) -> None:
    inputs = _stop_inputs(tmp_path)
    output = tmp_path / "stop-config"

    assert (
        main(
            [
                "measure-controller-stop-config",
                "--controller-declaration",
                str(inputs["declaration"]),
                "--source-declaration",
                str(inputs["declaration"]),
                "--controller-config",
                str(inputs["controllers"]),
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    assert "CONTROLLER_STOP_CONFIG_DECLARED" in capsys.readouterr().out
    document = json.loads((output / "controller-stop-config.json").read_text(encoding="utf-8"))
    assert document["stopped_tolerance_rad_s"] == 0.002
    assert document["measured_here"] is False
    assert document["declared_by"]["path"] == str(inputs["declaration"])
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["document_sha256"] == document["sha256"]


def test_measure_controller_stop_config_refuses_a_header_without_the_tolerance(
    tmp_path: Path, capsys
) -> None:
    inputs = _stop_inputs(tmp_path)
    bare = tmp_path / "no-tolerance.hpp"
    bare.write_text(
        STOP_DECLARATION.replace("  static constexpr double stop_velocity_rad_s = 0.002;\n", ""),
        encoding="utf-8",
    )
    from so101_demo.act.head_search_stop_measurement import (
        CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED,
    )

    assert (
        main(
            [
                "measure-controller-stop-config",
                "--controller-declaration",
                str(bare),
                "--source-declaration",
                str(bare),
                "--controller-config",
                str(inputs["controllers"]),
                "--output-dir",
                str(tmp_path / "stop-config"),
            ]
        )
        == 2
    )
    assert CAL_CONTROLLER_STOP_TOLERANCE_UNDECLARED in capsys.readouterr().err


def test_measure_feedback_refuses_an_undeclared_quantisation_and_accepts_a_declared_one(
    tmp_path: Path, capsys
) -> None:
    inputs = _stop_inputs(tmp_path)
    from so101_demo.act.head_search_stop_measurement import CAL_FEEDBACK_QUANTISATION_UNDECLARED

    output = tmp_path / "feedback"
    assert (
        main(
            [
                "measure-feedback",
                "--controller-config",
                str(inputs["controllers"]),
                "--output-dir",
                str(output),
            ]
        )
        == 2
    )
    captured = capsys.readouterr()
    assert CAL_FEEDBACK_QUANTISATION_UNDECLARED in captured.err
    assert "FEEDBACK_MEASUREMENTS_MEASURED" in captured.out
    document = json.loads((output / "feedback-measurements.json").read_text(encoding="utf-8"))
    assert document["period_s"] == 0.01
    assert document["quantisation_rad"] is None
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["fields_refused"] == ["quantisation_rad"]

    declaration = tmp_path / "encoder.json"
    declaration.write_text(json.dumps({"quantisation_rad": 0.0001}), encoding="utf-8")
    second = tmp_path / "feedback-declared"
    assert (
        main(
            [
                "measure-feedback",
                "--controller-config",
                str(inputs["controllers"]),
                "--quantisation-declaration",
                str(declaration),
                "--output-dir",
                str(second),
            ]
        )
        == 0
    )
    document = json.loads((second / "feedback-measurements.json").read_text(encoding="utf-8"))
    assert document["quantisation_rad"] == 0.0001
    assert document["refusals"] == []


def test_measure_stationary_hands_the_flight_to_the_library(tmp_path: Path, capsys, monkeypatch) -> None:
    inputs = _stop_inputs(tmp_path)
    output = tmp_path / "stationary"
    from so101_demo.act import head_search_stop_measurement as measurement

    monkeypatch.setattr(measurement, "MujocoStopFlight", _StopPlant)

    assert (
        main(_stop_flight_arguments("measure-stationary", inputs, output) + ["--samples-per-pose", "3"])
        == 0
    )
    captured = capsys.readouterr()
    assert "STATIONARY_MEASUREMENTS_MEASURED" in captured.out
    document = json.loads((output / "stationary-measurements.json").read_text(encoding="utf-8"))
    assert document["samples_per_pose"] == 3
    assert document["pose_count"] == 3
    assert len(document["samples"]) == 9
    assert document["monitored_joints"] == list(measurement.MONITORED_JOINTS)
    assert document["samples"][0]["velocity_rad_s"][-1] == 0.001
    assert document["path"] == str(output / "stationary-measurements.json")
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["document_sha256"] == document["sha256"]
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False


def test_measure_controller_submissions_hands_the_flight_to_the_library(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _stop_inputs(tmp_path)
    output = tmp_path / "submissions"
    from so101_demo.act import head_search_stop_measurement as measurement

    monkeypatch.setattr(measurement, "MujocoStopFlight", _StopPlant)

    assert main(_stop_flight_arguments("measure-controller-submissions", inputs, output)) == 0
    assert "CONTROLLER_SUBMISSIONS_MEASURED" in capsys.readouterr().out
    document = json.loads((output / "controller-submissions.json").read_text(encoding="utf-8"))
    assert document["time_base"] == "simulation"
    assert document["samples"]
    for sample in document["samples"]:
        assert sample["time_base"] == "simulation"
        assert sample["first_target_sim_s"] - sample["submit_snapshot_sim_s"] == pytest.approx(
            document["simulation_timestep_s"]
        )


def test_measure_stop_proofs_hands_the_flight_to_the_library(tmp_path: Path, capsys, monkeypatch) -> None:
    inputs = _stop_inputs(tmp_path)
    output = tmp_path / "stop-proofs"
    from so101_demo.act import head_search_stop_measurement as measurement

    monkeypatch.setattr(measurement, "MujocoStopFlight", _StopPlant)

    assert (
        main(
            _stop_flight_arguments("measure-stop-proofs", inputs, output)
            + ["--revoke-offset-s", "0.02", "--stop-budget-s", "0.5"]
        )
        == 0
    )
    assert "STOP_PROOFS_MEASURED" in capsys.readouterr().out
    document = json.loads((output / "stop-proofs.json").read_text(encoding="utf-8"))
    assert document["feedback_period_s"] == 0.01
    assert len(document["samples"]) == 2
    for sample in document["samples"]:
        assert sample["third_confirming_receive_monotonic_s"] > sample["stop_request_monotonic_s"]
        assert len(sample["feedback_samples"]) >= 3


def test_the_stop_measurements_refuse_an_existing_output_directory(tmp_path: Path, capsys) -> None:
    inputs = _stop_inputs(tmp_path)
    output = tmp_path / "stationary"
    output.mkdir()

    assert main(_stop_flight_arguments("measure-stationary", inputs, output)) == 2
    assert "never resumed" in capsys.readouterr().err


def test_the_stop_flight_entries_need_a_scene_and_a_seal(tmp_path: Path, capsys) -> None:
    inputs = _stop_inputs(tmp_path)
    for subcommand in ("measure-stationary", "measure-controller-submissions", "measure-stop-proofs"):
        assert main([subcommand]) == 2
        assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err
        arguments = _stop_flight_arguments(subcommand, inputs, tmp_path / subcommand)
        arguments[2] = str(tmp_path / "absent.xml")
        assert main(arguments) == 2
        assert "no such input" in capsys.readouterr().err


# --- measure-workspace-projection ------------------------------------------------------------------


def test_measure_workspace_projection_needs_its_declared_inputs(capsys) -> None:
    assert main(["measure-workspace-projection"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_workspace_projection_refuses_a_missing_input_and_an_existing_output(
    tmp_path: Path, capsys
) -> None:
    declared = {
        "--scene": tmp_path / "head_search_scene.xml",
        "--geometry-seal": tmp_path / "head-camera-geometry.json",
        "--geometry-contract": tmp_path / "head-camera-geometry-contract-v1.json",
        "--output-dir": tmp_path / "measurement",
    }
    arguments = ["measure-workspace-projection"]
    for flag, path in declared.items():
        arguments += [flag, str(path)]
    assert main(arguments) == 2
    assert "no such input" in capsys.readouterr().err

    for flag, path in declared.items():
        if flag != "--output-dir":
            path.write_text("{}", encoding="utf-8")
    declared["--output-dir"].mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_workspace_projection_hands_the_flight_to_the_library(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The CLI is a parser and a validator: the projection itself is the library module's."""

    from so101_demo.act import head_search_workspace_projection

    inputs = {}
    for flag, name in (
        ("--scene", "head_search_scene.xml"),
        ("--geometry-seal", "head-camera-geometry.json"),
        ("--geometry-contract", "head-camera-geometry-contract-v1.json"),
    ):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        inputs[flag] = path
    output = tmp_path / "measurement"
    seen = {}

    def fake_write(**arguments):
        seen.update(arguments)
        return {
            "receipt": {
                "top_px": 191.699852915671,
                "bottom_px": 272.6768492617673,
                "pose_count": 3,
                "point_count": 120,
                "union_px": [191.699852915671, 272.6768492617673],
                "intersection_px": [192.79306238636892, 266.49194356287984],
                "chosen_step_rad": 0.6560533740603397,
                "step_source": "phase_2_selection_rule",
            }
        }

    monkeypatch.setattr(
        head_search_workspace_projection, "write_head_search_workspace_projection", fake_write
    )
    arguments = ["measure-workspace-projection"]
    for flag, path in inputs.items():
        arguments += [flag, str(path)]
    arguments += ["--output-dir", str(output)]

    assert main(arguments) == 0

    printed = capsys.readouterr().out
    assert "WORKSPACE_PROJECTION_PRODUCED top_px=191.699852915671" in printed
    assert "poses=3" in printed and "points=120" in printed
    assert "step=0.6560533740603397 (phase_2_selection_rule)" in printed
    assert seen["coarse_step_rad"] is None, "the step is phase 2's own choice unless it is declared"
    assert seen["scene_path"] == inputs["--scene"]
    assert seen["geometry_seal_path"] == inputs["--geometry-seal"]
    assert seen["geometry_contract_path"] == inputs["--geometry-contract"]
    assert seen["output_dir"] == output
    assert "measure-workspace-projection" in seen["command"]

    # a run that holds its own plan declares the step it was receipted at, and the entry passes it on
    output_declared = tmp_path / "measurement-declared"
    arguments_declared = [*arguments[:-2], "--coarse-step-rad", "0.3", "--output-dir", str(output_declared)]
    assert main(arguments_declared) == 0
    assert seen["coarse_step_rad"] == 0.3
    assert seen["output_dir"] == output_declared


def test_measure_workspace_projection_reports_the_library_refusal(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.act import head_search_workspace_projection
    from so101_demo.act.head_search_workspace_projection import (
        CAL_PROJECTION_POSE_SET_AMBIGUOUS,
        CalibrationWorkspaceProjectionRefused,
    )

    inputs = {}
    for flag, name in (
        ("--scene", "head_search_scene.xml"),
        ("--geometry-seal", "head-camera-geometry.json"),
        ("--geometry-contract", "head-camera-geometry-contract-v1.json"),
    ):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        inputs[flag] = path

    def fake_write(**_arguments):
        raise CalibrationWorkspaceProjectionRefused(
            CAL_PROJECTION_POSE_SET_AMBIGUOUS, "the in-domain stop set depends on the coarse step"
        )

    monkeypatch.setattr(
        head_search_workspace_projection, "write_head_search_workspace_projection", fake_write
    )
    arguments = ["measure-workspace-projection"]
    for flag, path in inputs.items():
        arguments += [flag, str(path)]
    arguments += ["--output-dir", str(tmp_path / "measurement")]

    assert main(arguments) == 2
    assert CAL_PROJECTION_POSE_SET_AMBIGUOUS in capsys.readouterr().err


# --- measure-fine-correction-episodes ----------------------------------------------------------------

#: the held-out seeds this entry's fixture declares, with the recorder's own condition-class convention
#: (`record_episodes7.py:40`): positions 0 and 1 are `nominal`, so both seeds prepare a one-cup scene
FINE_CORRECTION_PARTITIONS = {
    "schema_version": 1,
    "document": "head-search-scenario-partitions/v1",
    "condition_classes": [
        "nominal",
        "left_anchor",
        "two_cups",
        "no_cup",
    ],
    "anchors": ["default", "left", "forward"],
    "calibration": [700000, 700001],
    "held_out_evaluation": [800000, 800001],
}


def _fine_correction_inputs(tmp_path: Path) -> dict:
    """The eight declared inputs of the episode measurement: the deadband fixture plus two."""

    inputs = _deadband_inputs(tmp_path)
    dataset_config = tmp_path / "head_camera_yolo_seg.yaml"
    dataset_config.write_text(
        f"mjcf_path: {inputs['scene'].name}\ncamera_name: head_camera\n"
        f"image_width: 640\nimage_height: 480\n",
        encoding="utf-8",
    )
    partitions = tmp_path / "head-search-scenario-partitions-v1.json"
    partitions.write_text(json.dumps(FINE_CORRECTION_PARTITIONS), encoding="utf-8")
    inputs["dataset_config"] = dataset_config
    inputs["partitions"] = partitions
    return inputs


def _fine_correction_arguments(inputs: dict, output: Path, *extra: str) -> list:
    return [
        "measure-fine-correction-episodes",
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--production-search-config",
        str(inputs["production"]),
        "--controller-config",
        str(inputs["controllers"]),
        "--frozen-candidate",
        str(inputs["frozen"]),
        "--weights",
        str(inputs["weights"]),
        "--dataset-config",
        str(inputs["dataset_config"]),
        "--scenario-partitions",
        str(inputs["partitions"]),
        "--output-dir",
        str(output),
        *extra,
    ]


class _FineCorrectionPlant:
    """A yaw-only plant whose cup sits on the principal point: every episode locks immediately."""

    def __init__(self, request) -> None:
        self.request = request
        self.simulation_timestep_s = 0.002
        self.yaw_rad = 0.0
        self.velocity_rad_s = 0.0
        self.time_s = 0.0
        self.cup_position_m = [-0.08, -0.28, 0.165]
        self.arm_drift_rad = 0.0

    @property
    def frame_stamp_ns(self) -> int:
        return int(round(self.time_s * 1e9))

    def settle_to(self, target_rad: float) -> dict:
        start, rad = self.time_s, self.yaw_rad
        self.yaw_rad, self.time_s = float(target_rad), self.time_s + 0.01
        return {
            "target_rad": float(target_rad),
            "start_rad": rad,
            "sim_start_s": start,
            "sim_end_s": self.time_s,
            "steps": 5,
            "settle_s": self.time_s - start,
            "settled": True,
            "reached": True,
            "final_velocity_rad_s": 0.0,
            "final_position_error_rad": 0.0,
            "quiet_steps": 5,
        }

    def render_frame(self):
        return {"yaw_rad": self.yaw_rad}

    def optical_geometry(self) -> dict:
        return {
            "k": (415.69219381653056, 0.0, 320.0, 0.0, 415.69219381653056, 240.0, 0.0, 0.0, 1.0),
            "distortion": (0.0, 0.0, 0.0, 0.0, 0.0),
            "rotation_optical_to_base": (
                (-1.0, 0.0, 0.0),
                (0.0, 0.6, -0.8),
                (0.0, -0.8, -0.6),
            ),
        }


def _patch_fine_correction_flight(monkeypatch, *, blind_seeds=()):
    """Stub the three heavy seams of the flight: the scene preparation, the plant and the detector.

    The flight builds its detector once, before any plant exists, so the stubbed detector reads the plant
    the stubbed plant factory last produced rather than being handed one.
    """

    from so101_demo.act import head_search_fine_correction_episodes as measurement

    state = {"plant": None}

    class Plant(_FineCorrectionPlant):
        def __init__(self, request) -> None:
            super().__init__(request)
            state["plant"] = self

    class Detector:
        """One frame with the cup 30 px right of the principal point, then the cup held centred.

        The first frame makes the production controller perform exactly one fine correction; the frames
        after it are the three consecutive centred frames the lock rule needs.
        """

        def __init__(self) -> None:
            self.calls = 0

        def reset(self) -> None:
            self.calls = 0

        def __call__(self, image, stamp_ns):
            plant = state["plant"]
            if int(plant.request["seed"]) in blind_seeds:
                return []
            self.calls += 1
            column = 350.0 if self.calls == 1 else 320.0
            return [
                {
                    "xyxy": (column - 50.0, 190.0, column + 50.0, 290.0),
                    "confidence": 0.9,
                    "class_id": 0,
                    "track_id": "head-cup-0",
                }
            ]

    monkeypatch.setattr(measurement, "prepare_episode_scene", lambda **request: {"prepared": True})
    monkeypatch.setattr(measurement, "MujocoEpisodePlant", Plant)
    monkeypatch.setattr(measurement, "build_production_head_detector", lambda **kwargs: Detector())
    return measurement


def test_measure_fine_correction_episodes_needs_its_declared_inputs(capsys) -> None:
    assert main(["measure-fine-correction-episodes"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_fine_correction_episodes_refuses_a_missing_input_and_an_existing_output(
    tmp_path: Path, capsys
) -> None:
    inputs = _fine_correction_inputs(tmp_path)
    output = tmp_path / "episodes"
    arguments = _fine_correction_arguments(inputs, output)

    missing = list(arguments)
    missing[missing.index("--weights") + 1] = str(tmp_path / "absent.pt")
    assert main(missing) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err

    output.mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_fine_correction_episodes_hands_the_flight_to_the_library(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _fine_correction_inputs(tmp_path)
    output = tmp_path / "episodes"
    _patch_fine_correction_flight(monkeypatch)

    assert main(_fine_correction_arguments(inputs, output)) == 0

    printed = capsys.readouterr().out
    assert "FINE_CORRECTION_EPISODES_MEASURED" in printed
    assert "episodes=2" in printed
    assert "succeeded=2" in printed
    assert "refused=0" in printed
    assert "split=held_out_evaluation" in printed
    assert f"output_dir={output}" in printed
    document = json.loads(
        (output / "fine-correction-episodes.json").read_text(encoding="utf-8")
    )
    assert [record["episode_id"] for record in document["records"]] == [
        "held_out_evaluation-800000",
        "held_out_evaluation-800001",
    ]
    assert all(record["split"] == "held_out_evaluation" for record in document["records"])
    assert document["succeeded_count"] == 2
    assert document["refused_count"] == 0
    assert document["split_declaration"]["calibration_seeds_used"] == []
    assert document["anchors"] == ["left"]
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    assert receipt["document_sha256"] == document["sha256"]
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False
    assert receipt["mujoco_neck_commanded"] is True


def test_measure_fine_correction_episodes_reports_a_refused_episode_and_still_writes_the_document(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    inputs = _fine_correction_inputs(tmp_path)
    output = tmp_path / "episodes"
    _patch_fine_correction_flight(monkeypatch, blind_seeds=(800001,))

    assert main(_fine_correction_arguments(inputs, output)) == 0

    captured = capsys.readouterr()
    assert "succeeded=1" in captured.out
    assert "refused=1" in captured.out
    assert "CAL_FINE_EPISODE_CUP_NOT_FOUND" in captured.err


def test_measure_fine_correction_episodes_refuses_a_calibration_seed(tmp_path: Path, capsys) -> None:
    inputs = _fine_correction_inputs(tmp_path)
    output = tmp_path / "episodes"

    assert main(_fine_correction_arguments(inputs, output, "--seed", "700000")) == 2
    assert "CAL_FINE_EPISODE_SPLIT_LEAK" in capsys.readouterr().err
    assert not output.exists()


def test_measure_fine_correction_episodes_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    from so101_demo.act import head_search_fine_correction_episodes as measurement

    inputs = _fine_correction_inputs(tmp_path)
    output = tmp_path / "episodes"
    _patch_fine_correction_flight(monkeypatch)

    def refuse(**request):
        raise measurement.CalibrationFineCorrectionRefused(
            measurement.CAL_FINE_EPISODE_OUT_OF_CORRIDOR, "the loop left the declared corridor"
        )

    monkeypatch.setattr(measurement, "prepare_episode_scene", refuse)

    assert main(_fine_correction_arguments(inputs, output)) == 2
    assert measurement.CAL_FINE_EPISODE_OUT_OF_CORRIDOR in capsys.readouterr().err


# --- measure-frame-contract and measure-skew --------------------------------------------------------

TRANSPORT_PLUGIN_CONFIG = {
    "/**": {
        "ros__parameters": {
            "mujoco_plugins": {
                "mujoco_camera_plugin": {
                    "type": "mujoco_ros2_control_plugins/CameraPlugin",
                    "camera_publish_rate": 10.0,
                    "head_camera": {
                        "policy": "streaming",
                        "frame_name": "head_camera_frame",
                        "image_topic": "/head_camera/color",
                        "info_topic": "/head_camera/camera_info",
                    },
                }
            }
        }
    }
}


def _transport_inputs(tmp_path: Path, *, rate: float = 10.0) -> dict:
    import yaml

    document = json.loads(json.dumps(TRANSPORT_PLUGIN_CONFIG))
    camera = document["/**"]["ros__parameters"]["mujoco_plugins"]["mujoco_camera_plugin"]
    camera["camera_publish_rate"] = rate
    plugin = tmp_path / "mujoco_plugins.yaml"
    plugin.write_text(yaml.safe_dump(document, sort_keys=True), encoding="utf-8")
    inputs = {"--plugin-config": plugin, "--output-dir": tmp_path / "measurement"}
    for flag, name in (
        ("--scene", "head_search_scene.xml"),
        ("--geometry-seal", "head-camera-geometry.json"),
        ("--controller-config", "ros2_controllers.yaml"),
        ("--urdf", "so101.urdf"),
        ("--frame-contract", "frame-contract.json"),
    ):
        path = tmp_path / name
        path.write_text("{}", encoding="utf-8")
        inputs[flag] = path
    return inputs


def test_measure_frame_contract_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-frame-contract"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_frame_contract_refuses_a_missing_input_and_an_existing_output(
    tmp_path: Path, capsys
) -> None:
    import yaml

    plugin = tmp_path / "mujoco_plugins.yaml"
    output = tmp_path / "measurement"
    arguments = [
        "measure-frame-contract",
        "--plugin-config",
        str(plugin),
        "--output-dir",
        str(output),
    ]
    assert main(arguments) == 2
    assert "no such input" in capsys.readouterr().err

    plugin.write_text(yaml.safe_dump(TRANSPORT_PLUGIN_CONFIG, sort_keys=True), encoding="utf-8")
    output.mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_frame_contract_refuses_a_skew_document_that_is_not_there(
    tmp_path: Path, capsys
) -> None:
    inputs = _transport_inputs(tmp_path)
    rc = main(
        [
            "measure-frame-contract",
            "--plugin-config",
            str(inputs["--plugin-config"]),
            "--output-dir",
            str(inputs["--output-dir"]),
            "--skew-measurements",
            str(tmp_path / "absent.json"),
        ]
    )
    assert rc == 2
    assert "no such input" in capsys.readouterr().err


def test_measure_frame_contract_writes_the_declaration_and_returns_zero(
    tmp_path: Path, capsys
) -> None:
    inputs = _transport_inputs(tmp_path)
    rc = main(
        [
            "measure-frame-contract",
            "--plugin-config",
            str(inputs["--plugin-config"]),
            "--output-dir",
            str(inputs["--output-dir"]),
        ]
    )

    assert rc == 0
    document = json.loads((inputs["--output-dir"] / "frame-contract.json").read_text("utf-8"))
    assert document["frame_rate_hz"] == 10.0
    assert document["measured_here"] is False
    assert document["declared_by"]["sha256"]
    assert "FRAME_CONTRACT_DECLARED" in capsys.readouterr().out


def test_measure_frame_contract_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, capsys
) -> None:
    inputs = _transport_inputs(tmp_path, rate=5.0)
    rc = main(
        [
            "measure-frame-contract",
            "--plugin-config",
            str(inputs["--plugin-config"]),
            "--output-dir",
            str(inputs["--output-dir"]),
        ]
    )

    assert rc == 2
    assert "CAL_FRAME_CONTRACT_CONTRADICTORY" in capsys.readouterr().err


def test_measure_skew_needs_its_declared_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-skew"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_skew_refuses_a_missing_input_and_an_existing_output(tmp_path: Path, capsys) -> None:
    arguments = ["measure-skew"]
    for flag, name in (
        ("--scene", "scene.xml"),
        ("--geometry-seal", "seal.json"),
        ("--plugin-config", "mujoco_plugins.yaml"),
        ("--controller-config", "ros2_controllers.yaml"),
        ("--urdf", "so101.urdf"),
        ("--frame-contract", "frame-contract.json"),
        ("--output-dir", "measurement"),
    ):
        arguments += [flag, str(tmp_path / name)]
    assert main(arguments) == 2
    assert "no such input" in capsys.readouterr().err

    for flag, name in (
        ("--scene", "scene.xml"),
        ("--geometry-seal", "seal.json"),
        ("--plugin-config", "mujoco_plugins.yaml"),
        ("--controller-config", "ros2_controllers.yaml"),
        ("--urdf", "so101.urdf"),
        ("--frame-contract", "frame-contract.json"),
    ):
        (tmp_path / name).write_text("{}", encoding="utf-8")
    (tmp_path / "measurement").mkdir()
    assert main(arguments) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_skew_hands_the_flight_to_the_library(tmp_path: Path, monkeypatch, capsys) -> None:
    """The CLI parses and validates; the capture itself belongs to the library module."""

    from so101_demo.act import head_search_transport_measurement as measurement

    inputs = _transport_inputs(tmp_path)
    arguments = ["measure-skew"]
    for flag, path in inputs.items():
        arguments += [flag, str(path)]
    arguments += ["--frames", "5", "--timeout-s", "3.5"]
    seen = {}

    def fake_write(**request):
        seen.update(request)
        return {
            "measurement": {
                "phase": "skew_measurements",
                "sha256": "0" * 64,
                "clock_resolution_s": 0.002,
                "samples": [{}] * 5,
                "observed": {"max_skew_s": 0.004, "inside_cap": True},
                "capture": {"achieved_rate_hz": 9.98},
            },
            "receipt": {
                "status": "MEASURED",
                "sample_count": 5,
                "measurement_sha256": "0" * 64,
                "observed": {"max_skew_s": 0.004},
            },
        }

    monkeypatch.setattr(measurement, "write_transport_measurements", fake_write)
    rc = main(arguments)

    assert rc == 0
    assert seen["mode"] == "skew"
    assert seen["frames"] == 5
    assert seen["timeout_s"] == 3.5
    assert seen["frame_contract_path"] == inputs["--frame-contract"]
    assert seen["transport"] is not None
    assert "SKEW_MEASURED" in capsys.readouterr().out


def test_measure_skew_prints_the_librarys_refusal_and_returns_two(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.act import head_search_transport_measurement as measurement

    inputs = _transport_inputs(tmp_path)
    arguments = ["measure-skew"]
    for flag, path in inputs.items():
        arguments += [flag, str(path)]

    def refuse(**request):
        raise measurement.CalibrationInputsRefused(
            measurement.CAL_SKEW_TRANSPORT_UNREACHABLE, "the transport never published a frame"
        )

    monkeypatch.setattr(measurement, "write_transport_measurements", refuse)

    assert main(arguments) == 2
    assert "CAL_SKEW_TRANSPORT_UNREACHABLE" in capsys.readouterr().err


def _rule_inputs(tmp_path: Path) -> dict:
    """The sealed production config the rule's grid comes from, and two brand-new directories."""

    config = tmp_path / "head_search_v2.json"
    config.write_text(
        json.dumps(
            {
                "values": {
                    "min_confidence": 0.4,
                    "tracking_iou": 0.3,
                    "min_bbox_aspect": 0.5,
                    "min_area_px2": 64.0,
                }
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "--production-search-config": config,
        "--measurements-output-dir": tmp_path / "operating-point-20260101T000000Z",
        "--output-dir": tmp_path / "rules",
    }


def test_measure_selection_rule_refuses_missing_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-selection-rule", "--output-dir", str(tmp_path / "rules")]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_selection_rule_refuses_a_measurement_directory_that_already_exists(
    tmp_path: Path, capsys
) -> None:
    inputs = _rule_inputs(tmp_path)
    Path(inputs["--measurements-output-dir"]).mkdir()
    arguments = ["measure-selection-rule"]
    for flag, value in inputs.items():
        arguments += [flag, str(value)]
    assert main(arguments) == 2
    assert "CAL_RULE_AFTER_MEASUREMENT" in capsys.readouterr().err


def test_measure_selection_rule_writes_the_two_rule_records(tmp_path: Path, capsys) -> None:
    inputs = _rule_inputs(tmp_path)
    arguments = ["measure-selection-rule"]
    for flag, value in inputs.items():
        arguments += [flag, str(value)]
    assert main(arguments) == 0
    output = capsys.readouterr().out
    assert "SELECTION_RULE_RECORDED" in output
    assert "points=18" in output
    head = json.loads((Path(inputs["--output-dir"]) / "selection-rule.json").read_text())
    task = json.loads((Path(inputs["--output-dir"]) / "selection-rule-task.json").read_text())
    assert head["domain"] == "head"
    assert task["domain"] == "task"
    assert head["measurements_admitted"] == 0
    assert head["selection_splits"] == ["val", "calibration"]


def _operating_point_inputs(tmp_path: Path) -> dict:
    """Every path the measurement entry requires, written as the sealed shape it verifies."""

    geometry = tmp_path / "head-camera-geometry.json"
    geometry.write_text(
        json.dumps(
            {
                "seal_sha256": "d" * 64,
                "camera_name": "head_camera",
                "horizontal_fov_rad": 1.31,
                "required_search_domain_rad": [-0.3, 0.3],
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    config = tmp_path / "head_camera_yolo_seg.yaml"
    config.write_text("scene: {}\n", encoding="utf-8")
    inputs = {
        "--geometry-seal": geometry,
        "--head-dataset": tmp_path / "head-dataset" / "dataset-manifest.json",
        "--task-dataset": tmp_path / "task-dataset" / "dataset-manifest.json",
        "--dataset-config": config,
        "--production-search-config": _rule_inputs(tmp_path)["--production-search-config"],
        "--episode-partitions": tmp_path / "head-search-scenario-partitions-v1.json",
        "--selection-rule": tmp_path / "rules" / "selection-rule.json",
        "--task-selection-rule": tmp_path / "rules" / "selection-rule-task.json",
        "--frozen-candidate": tmp_path / "frozen-a.json",
        "--output-dir": tmp_path / "operating-point-20260101T000000Z",
    }
    for flag, value in inputs.items():
        if flag == "--output-dir":
            continue
        Path(value).parent.mkdir(parents=True, exist_ok=True)
        if not Path(value).exists():
            Path(value).write_text("{}\n", encoding="utf-8")
    return inputs


def _operating_point_arguments(tmp_path: Path, inputs: dict, *, weights: Path) -> list[str]:
    arguments = ["measure-operating-point"]
    for flag, value in inputs.items():
        arguments += [flag, str(value)]
    arguments += ["--weights-dir", str(weights)]
    return arguments


def test_measure_operating_point_refuses_missing_inputs(tmp_path: Path, capsys) -> None:
    assert main(["measure-operating-point", "--output-dir", str(tmp_path / "out")]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_operating_point_refuses_an_input_that_does_not_exist(
    tmp_path: Path, capsys
) -> None:
    inputs = _operating_point_inputs(tmp_path)
    arguments = _operating_point_arguments(tmp_path, inputs, weights=tmp_path / "absent-weights")
    assert main(arguments) == 2
    assert "no such input" in capsys.readouterr().err


def test_measure_operating_point_refuses_an_existing_output_directory(
    tmp_path: Path, capsys
) -> None:
    inputs = _operating_point_inputs(tmp_path)
    Path(inputs["--output-dir"]).mkdir()
    weights = tmp_path / "weights"
    weights.mkdir()
    arguments = _operating_point_arguments(tmp_path, inputs, weights=weights)
    assert main(arguments) == 2
    assert "exists; a measurement is never resumed" in capsys.readouterr().err


def test_measure_operating_point_prints_the_librarys_selection(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    from so101_demo.act import head_search_operating_point_measurement as measurement

    inputs = _operating_point_inputs(tmp_path)
    weights = tmp_path / "weights"
    weights.mkdir()
    arguments = _operating_point_arguments(tmp_path, inputs, weights=weights)
    seen = {}

    def fake_measure(**request):
        seen.update(request)
        return {
            "document": {"frames": [{}, {}], "sha256": "0" * 64},
            "receipt": {
                "status": "MEASURED",
                "frame_count": 2,
                "candidate_count": 3,
                "grid_point_count": 18,
                "chosen": {
                    "head": {"A": {"min_confidence": 0.25, "tracking_iou": 0.5}},
                    "task": {"A": {"min_confidence": 0.25, "tracking_iou": 0.5}},
                },
            },
        }

    monkeypatch.setattr(measurement, "measure_operating_point_measurements", fake_measure)
    rc = main(arguments)

    assert rc == 0
    assert seen["device"] == "cuda"
    assert seen["weights_dir"] == weights
    assert seen["selection_rule_path"] == inputs["--selection-rule"]
    assert seen["task_selection_rule_path"] == inputs["--task-selection-rule"]
    assert seen["output_dir"] == inputs["--output-dir"]
    assert "OPERATING_POINTS_MEASURED" in capsys.readouterr().out


def test_the_run_entry_observes_the_measured_values_off_the_running_components(tmp_path: Path) -> None:
    """The run's phase inputs carry the observer, so phases 6 and 7 record proof rather than a restatement."""

    from so101_demo.act.head_search_measured_readback import observe_measured_readbacks
    from so101_demo.cli.head_search_calibration import _phase_inputs, _run_parser

    parsed = _run_parser().parse_args(_run_arguments(tmp_path)[1:])
    phase_inputs = _phase_inputs(parsed)

    assert phase_inputs.readback_observer is observe_measured_readbacks
    assert phase_inputs.startup_readbacks is None


def test_check_ownership_publishes_a_stack_free_receipt(tmp_path: Path, monkeypatch) -> None:
    """Step 1's gate is an installed entry: a clean machine is recorded, a second owner is refused."""

    from so101_demo.act import head_search_ownership as ownership

    evidence = tmp_path / "evidence"
    evidence.mkdir()

    def observation(name: str, **overrides):
        fields = {"command": (), "rc": 0, "rows": (), "value": None, "note": ""}
        fields.update(overrides)
        return ownership.ResourceObservation(name=name, **fields)

    def clean_observers(**kwargs):
        return {
            "process_table": lambda: observation("process_table"),
            "ros_graph": lambda: observation("ros_graph", value="clean"),
            "gpu_processes": lambda: observation("gpu_processes"),
            "tmux_panes": lambda: observation("tmux_panes"),
            "evidence_root": lambda: observation("evidence_root", value="usable"),
            "planned_run_root": lambda: observation("planned_run_root", value="absent"),
            "ament_prefix": lambda: observation("ament_prefix", value="/frozen/so101_demo_py"),
        }

    monkeypatch.setattr(ownership, "default_observers", clean_observers)
    run_root = tmp_path / "gate"
    assert (
        main(
            [
                "check-ownership",
                "--run-root",
                str(run_root),
                "--evidence-root",
                str(evidence),
                "--expected-package-prefix",
                "/frozen/so101_demo_py",
            ]
        )
        == 0
    )
    receipt = json.loads((run_root / ownership.RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt["status"] == ownership.EXCLUSIVE_OWNERSHIP_OK
    assert receipt["refusals"] == []

    def busy_observers(**kwargs):
        observers = clean_observers(**kwargs)
        observers["process_table"] = lambda: observation(
            "process_table", rows=({"pid": 5, "kind": "stack", "command": "move_group"},)
        )
        return observers

    monkeypatch.setattr(ownership, "default_observers", busy_observers)
    other = tmp_path / "gate-busy"
    assert (
        main(
            [
                "check-ownership",
                "--run-root",
                str(other),
                "--evidence-root",
                str(evidence),
            ]
        )
        == 2
    )
    refused = json.loads((other / ownership.RECEIPT_NAME).read_text(encoding="utf-8"))
    assert refused["status"] == ownership.EXCLUSIVE_OWNERSHIP_REFUSED
    assert [item["code"] for item in refused["refusals"]] == ["STACK_OWNER_ACTIVE"]


def test_check_ownership_refuses_a_reused_gate_root_and_an_unreadable_runtime(
    tmp_path: Path,
) -> None:
    existing = tmp_path / "gate"
    existing.mkdir()
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    assert (
        main(
            [
                "check-ownership",
                "--run-root",
                str(existing),
                "--evidence-root",
                str(evidence),
            ]
        )
        == 2
    )
    assert (
        main(
            [
                "check-ownership",
                "--run-root",
                str(tmp_path / "fresh"),
                "--evidence-root",
                str(evidence),
                "--final-run",
                str(tmp_path / "missing-toolchain"),
            ]
        )
        == 2
    )
    assert not (tmp_path / "fresh").exists(), "a refused identity must not leave a half-claimed root"


SCENARIO_PARTITIONS = {
    "schema_version": 1,
    "document": "head-search-scenario-partitions/v1",
    "condition_classes": [
        "nominal",
        "left_anchor",
        "forward_anchor",
        "distractor_present",
        "two_cups",
        "no_cup",
        "low_light",
        "partial_occlusion",
        "fast_interruption",
        "reacquire_after_stop",
    ],
    "anchors": ["default", "left", "forward"],
    "calibration": [700000, 700001],
    "held_out_evaluation": [800000, 800001],
    "qualification": [
        {
            "seed": 900000 + index,
            "scene_group_id": f"scene-{900000 + index:09d}",
            "condition_class": [
                "nominal",
                "left_anchor",
                "forward_anchor",
                "distractor_present",
                "two_cups",
                "no_cup",
                "low_light",
                "partial_occlusion",
                "fast_interruption",
                "reacquire_after_stop",
            ][index],
            "anchor": ["default", "left", "forward"][index % 3],
        }
        for index in range(10)
    ],
}


def _scenario_inputs(tmp_path: Path) -> dict:
    """The nine declared inputs of the qualification scenarios: the episode fixture plus two."""

    inputs = _fine_correction_inputs(tmp_path)
    partitions = tmp_path / "head-search-scenario-partitions-v1.json"
    partitions.write_text(json.dumps(SCENARIO_PARTITIONS), encoding="utf-8")
    evidence = tmp_path / "evidence"
    evidence.mkdir(exist_ok=True)
    inputs["partitions"] = partitions
    inputs["evidence_root"] = evidence
    return inputs


def _scenario_arguments(inputs: dict, output: Path, *extra: str) -> list:
    return [
        "measure-scenarios",
        "--scene",
        str(inputs["scene"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--production-search-config",
        str(inputs["production"]),
        "--controller-config",
        str(inputs["controllers"]),
        "--frozen-candidate",
        str(inputs["frozen"]),
        "--weights",
        str(inputs["weights"]),
        "--dataset-config",
        str(inputs["dataset_config"]),
        "--scenario-partitions",
        str(inputs["partitions"]),
        "--output-dir",
        str(output),
        "--evidence-root",
        str(inputs["evidence_root"]),
        *extra,
    ]


def _patch_scenario_flight(monkeypatch, *, status="PASSED"):
    """Stub the flight's heavy seams, so the CLI case needs no MuJoCo, detector, GPU or gate."""

    from so101_demo.act import head_search_scenarios as scenarios

    seen: dict = {}

    def fake(**kwargs):
        seen.update(kwargs)
        rows = [
            {
                "seed": seed,
                "condition_class": "nominal",
                "anchor": "default",
                "outcome": status,
                "outcome_code": None if status == "PASSED" else "CAL_SCENARIO_CUP_NOT_FOUND",
            }
            for seed in kwargs.get("seeds") or [900000, 900001]
        ]
        document = {
            "scenario_count": len(rows),
            "passed_count": sum(1 for row in rows if row["outcome"] == "PASSED"),
            "failed_count": sum(1 for row in rows if row["outcome"] == "FAILED"),
            "refused_count": sum(1 for row in rows if row["outcome"] == "REFUSED"),
            "anchor_split": {"default": len(rows)},
            "zero_wrong_locks": True,
            "cadence_all_continuous": True,
            "stop_proofs_all_proven": True,
            "records": rows,
            "sha256": "0" * 64,
        }
        # the real receipt is the aggregate plus the identity: the CLI reads the aggregate off it
        return {
            "document": document,
            "receipt": {**document, "kind": "head_search_qualification_scenarios_receipt"},
            "output_dir": kwargs["output_dir"],
        }

    monkeypatch.setattr(scenarios, "write_head_search_scenarios", fake)
    return seen


def test_measure_scenarios_needs_its_declared_inputs(capsys) -> None:
    assert main(["measure-scenarios"]) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err


def test_measure_scenarios_refuses_a_missing_input_and_an_existing_output(
    tmp_path: Path, capsys
) -> None:
    inputs = _scenario_inputs(tmp_path)
    missing = _scenario_arguments(inputs, tmp_path / "run")
    missing[missing.index("--scene") + 1] = str(tmp_path / "absent.xml")
    assert main(missing) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err

    existing = tmp_path / "already-there"
    existing.mkdir()
    assert main(_scenario_arguments(inputs, existing)) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_scenarios_hands_the_flight_to_the_library(tmp_path: Path, monkeypatch, capsys) -> None:
    inputs = _scenario_inputs(tmp_path)
    seen = _patch_scenario_flight(monkeypatch)
    output = tmp_path / "run-root"

    assert main(_scenario_arguments(inputs, output, "--seed", "900000", "--seed", "900001")) == 0
    assert seen["seeds"] == [900000, 900001]
    assert seen["evidence_root"] == inputs["evidence_root"]
    assert seen["device"] == "cuda"
    assert "so101_head_search_calibration measure-scenarios" in seen["command"]
    assert "--seed 900000 --seed 900001" in seen["command"]
    printed = capsys.readouterr().out
    assert "HEAD_SEARCH_SCENARIOS_MEASURED" in printed
    assert "scenarios=2" in printed
    assert "passed=2" in printed


def test_measure_scenarios_reports_the_librarys_refusal_and_returns_two(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused

    from so101_demo.act import head_search_scenarios as scenarios

    inputs = _scenario_inputs(tmp_path)

    def refuse(**kwargs):
        raise CalibrationInputsRefused(
            scenarios.CAL_SCENARIO_OWNERSHIP_REFUSED,
            "the exclusive-ownership gate refused the run with DETECTOR_OWNER_ACTIVE",
        )

    monkeypatch.setattr(scenarios, "write_head_search_scenarios", refuse)
    assert main(_scenario_arguments(inputs, tmp_path / "run-root")) == 2
    assert scenarios.CAL_SCENARIO_OWNERSHIP_REFUSED in capsys.readouterr().err


def test_measure_scenarios_prints_every_failed_and_refused_scenario(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    inputs = _scenario_inputs(tmp_path)
    _patch_scenario_flight(monkeypatch, status="FAILED")

    assert main(_scenario_arguments(inputs, tmp_path / "run-root")) == 0
    printed = capsys.readouterr()
    assert "CAL_SCENARIO_CUP_NOT_FOUND" in printed.err
    assert "failed=2" in printed.out
