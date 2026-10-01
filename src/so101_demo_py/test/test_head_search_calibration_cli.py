"""The installed subcommands: approval verification, qualification, the run entry and no resume."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from so101_demo.cli.head_search_calibration import HEAD_SEARCH_RUN_INPUTS_INCOMPLETE, main
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


def test_qualify_refuses_an_existing_root_and_publishes_nothing_without_evidence(
    tmp_path: Path,
) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    # an existing root is a named refusal with exit code 2, not a traceback
    assert main(["qualify", "--run-root", str(run_root)]) == 2
    fresh = tmp_path / "fresh"
    with pytest.raises(ValueError, match="HEAD_SEARCH_QUALIFICATION_EVIDENCE_INCOMPLETE"):
        main(["qualify", "--run-root", str(fresh)])


def test_qualify_publishes_the_closed_report_with_evidence(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    promoted = tmp_path / "promoted"
    _bundle(promoted)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    for name in ("production_smoke", "scenarios", "restarts"):
        (evidence / f"{name}.json").write_text(json.dumps({"name": name}), encoding="utf-8")
    assert (
        main(
            [
                "qualify",
                "--run-root",
                str(run_root),
                "--promoted-config",
                str(promoted / "head-search-bundle.json"),
                "--evidence-root",
                str(evidence),
            ]
        )
        == 0
    )
    report = json.loads(
        (run_root / "head-search-qualified-report.json").read_text(encoding="utf-8")
    )
    assert report["status"] == "HEAD_SEARCH_QUALIFIED"
    assert set(report["evidence_sha256"]) == {"production_smoke", "scenarios", "restarts"}


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


def test_qualification_evidence_must_be_hexadecimal(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    promoted = tmp_path / "promoted"
    _bundle(promoted)
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    (evidence / "production_smoke.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    good = main(
        [
            "qualify",
            "--run-root",
            str(run_root),
            "--promoted-config",
            str(promoted / "head-search-bundle.json"),
            "--evidence-root",
            str(evidence),
        ]
    )
    assert good == 0

    other = tmp_path / "other"
    bad_evidence = tmp_path / "bad-evidence"
    bad_evidence.mkdir()
    (bad_evidence / "production_smoke.json").write_text("z" * 8, encoding="utf-8")
    (bad_evidence / "scenarios.json").write_text(json.dumps({"y": 2}), encoding="utf-8")
    with pytest.raises(ValueError, match="HEAD_SEARCH_QUALIFICATION_EVIDENCE_INCOMPLETE"):
        main(
            [
                "qualify",
                "--run-root",
                str(other),
                "--promoted-config",
                str(promoted / "head-search-bundle.json"),
                "--evidence-root",
                str(bad_evidence / ".."),
            ]
        )


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
