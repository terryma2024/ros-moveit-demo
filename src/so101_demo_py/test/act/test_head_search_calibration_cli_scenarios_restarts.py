"""The scenario, restart and teleop acceptance subcommands."""

from __future__ import annotations

import json
from pathlib import Path

from head_search_calibration_cli_support import _fine_correction_inputs, _restart_inputs

from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
)
from so101_demo.cli.head_search_calibration import main

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
    partitions = tmp_path / "head-search-scenario-partitions.json"
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

    from so101_demo.act.head_search_scenarios import writer as scenarios_writer

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

    monkeypatch.setattr(scenarios_writer, "write_head_search_scenarios", fake)
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
    from so101_demo.act.head_search_scenarios import contracts as scenarios_contracts
    from so101_demo.act.head_search_scenarios import writer as scenarios_writer

    inputs = _scenario_inputs(tmp_path)

    def refuse(**kwargs):
        raise CalibrationInputsRefused(
            scenarios_contracts.CAL_SCENARIO_OWNERSHIP_REFUSED,
            "the exclusive-ownership gate refused the run with DETECTOR_OWNER_ACTIVE",
        )

    monkeypatch.setattr(scenarios_writer, "write_head_search_scenarios", refuse)
    assert main(_scenario_arguments(inputs, tmp_path / "run-root")) == 2
    assert scenarios_contracts.CAL_SCENARIO_OWNERSHIP_REFUSED in capsys.readouterr().err


def test_measure_scenarios_prints_every_failed_and_refused_scenario(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    inputs = _scenario_inputs(tmp_path)
    _patch_scenario_flight(monkeypatch, status="FAILED")

    assert main(_scenario_arguments(inputs, tmp_path / "run-root")) == 0
    printed = capsys.readouterr()
    assert "CAL_SCENARIO_CUP_NOT_FOUND" in printed.err
    assert "failed=2" in printed.out


def _restart_arguments(inputs: dict, output: Path, *extra: str) -> list:
    return [
        "measure-restarts",
        "--run-root",
        str(output),
        "--ownership-receipt",
        str(inputs["ownership"]),
        "--final-run",
        str(inputs["final_run"]),
        "--production-config",
        str(inputs["production"]),
        "--approved-bundle",
        str(inputs["production"]),
        "--geometry-seal",
        str(inputs["seal"]),
        "--scene",
        str(inputs["scene"]),
        "--urdf",
        str(inputs["urdf"]),
        "--plugin-config",
        str(inputs["plugins"]),
        "--controller-config",
        str(inputs["controllers"]),
        "--weights",
        str(inputs["weights"]),
        "--frozen-candidate",
        str(inputs["frozen"]),
        "--workdir",
        str(inputs["workdir"]),
        *extra,
    ]


def _patch_restart_flight(monkeypatch, *, status="PASS"):
    """Stub the two heavy seams: the runtime readback and the per-anchor flight itself."""

    from so101_demo.act.head_search_restarts import contracts as restarts_contracts
    from so101_demo.act.head_search_restarts import observation as restarts_observation
    from so101_demo.act.head_search_restarts import restart_run as restarts_restart_run

    seen: dict = {}

    def fake_runtime(final_run, production_config=None):
        return {
            "final_run": str(final_run),
            "source_commit": "9" * 40,
            "setup_bash_present": True,
            "production_config": str(production_config),
            "production_config_sha256": "d" * 64,
            "values_count": 17,
            "values_sha256": "3" * 64,
            "allow_cpu_fallback": False,
            "cuda_device": "cuda:0",
            "weight_path": "/evidence/weights/best.pt",
            "weight_sha256_declared": "2" * 64,
            "weight_sha256_observed": "2" * 64,
        }

    def fake(**kwargs):
        seen.update(kwargs)
        anchor = kwargs["anchor"]
        row = {
            "anchor": anchor,
            "declared_anchor": dict(kwargs["declared"]),
            "stack": {
                "nodes": list(restarts_contracts.STACK_OWNED_NODES),
                "processes": [
                    {"pid": 11, "argv": "lib/mujoco_ros2_control/ros2_control_node"},
                    {"pid": 12, "argv": "lib/robot_state_publisher/robot_state_publisher"},
                ],
                "gpu_compute_apps": [],
            },
            "camera": {
                "frame_rate_hz": 10.0,
                "declared_rate_hz": 10.0,
                "frames": 40,
                "measured_rate_hz": 10.0,
                "rate_error_hz": 0.0,
                "duplicate_count": 0,
                "backward_count": 0,
                "matches_declared": True,
            },
            "clock": {"advancing": True, "delta_s": 3.0},
            "detector": {
                "loaded": True,
                "count": 1,
                "device": "cuda",
                "runtime_device": "cuda:0",
                "allow_cpu_fallback": False,
                "weights_sha256": "2" * 64,
            },
            "search": {
                "terminal_status": "TARGET_LOCKED",
                "coverage_complete": True,
                "wrong_locks": 0,
            },
            "lock": {"consecutive_frames": 3},
            "frames": [
                {
                    "index": index,
                    "frame_sim_s": 100.0 + index * 0.1,
                    "received_monotonic_s": index * 0.1,
                    "frame_age_s": 0.002,
                    "source_skew_s": 0.004,
                    "inference_s": 0.02,
                    "detections": 1,
                    "lock_count": index,
                }
                for index in range(12)
            ],
            "stop": {"proven": True, "qualifying_samples": 3},
            "teardown": {
                "previous_stack_stopped": True,
                "controller_owner_stopped": True,
                "children_exited": True,
                "graph_clear": True,
                "gpu_released": True,
            },
            "elapsed_s": 42.0,
            "started_at_utc": "2026-10-01T15:00:00Z",
            "finished_at_utc": "2026-10-01T15:00:42Z",
        }
        if status != "PASS":
            row["search"] = {"terminal_status": "TARGET_NOT_FOUND", "coverage_complete": True,
                             "wrong_locks": 0}
        return row

    monkeypatch.setattr(restarts_observation, "read_runtime_of_record", fake_runtime)
    monkeypatch.setattr(restarts_restart_run, "run_anchor_restart", fake)
    return seen


def test_measure_restarts_refuses_missing_inputs_and_an_existing_root(
    tmp_path: Path, capsys
) -> None:
    inputs = _restart_inputs(tmp_path)
    missing = _restart_arguments(inputs, tmp_path / "restart-run")
    missing[missing.index("--scene") + 1] = str(tmp_path / "absent.xml")
    assert main(missing) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err

    existing = tmp_path / "already-there"
    existing.mkdir()
    assert main(_restart_arguments(inputs, existing)) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_restarts_runs_the_three_anchors_and_writes_three_receipts(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    inputs = _restart_inputs(tmp_path)
    seen = _patch_restart_flight(monkeypatch)
    run_root = tmp_path / "restart-run"
    rc = main(_restart_arguments(inputs, run_root))

    assert rc == 0
    assert seen["anchor"] == "forward"
    assert seen["anchors"][0]["anchor"] == "default"
    assert seen["device"] == "cuda"
    printed = capsys.readouterr().out
    assert "HEAD_SEARCH_RESTARTS_MEASURED" in printed
    assert "status=PASS" in printed
    from so101_demo.act.head_search_restarts import contracts as restarts_contracts

    for anchor in restarts_contracts.ANCHORS:
        document = json.loads(
            (run_root / anchor / restarts_contracts.ARTIFACT_BY_ANCHOR[anchor]).read_text(encoding="utf-8")
        )
        assert document["anchor"] == anchor
        assert document["kind"] == "head_search_full_restart_receipt"
        assert document["lifecycle"] == "FULL_RESTART"
        assert document["gates"] == {
            "graph": "PASS",
            "detector": "PASS",
            "search": "PASS",
            "lock": "PASS",
            "timing": "PASS",
            "stop": "PASS",
        }
        assert (run_root / anchor / "stdout.log").is_file()
        assert (run_root / anchor / "stderr.log").is_file()
    aggregate = json.loads((run_root / restarts_contracts.AGGREGATE_ARTIFACT).read_text(encoding="utf-8"))
    assert aggregate["anchors"] == list(restarts_contracts.ANCHORS)
    assert aggregate["status"] == "PASS"


def test_measure_restarts_returns_two_when_an_anchor_refuses(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    inputs = _restart_inputs(tmp_path)
    _patch_restart_flight(monkeypatch, status="REFUSED")
    rc = main(_restart_arguments(inputs, tmp_path / "restart-run"))
    assert rc == 2
    printed = capsys.readouterr()
    assert "RESTART_SEARCH_UNPROVEN" in printed.err or "RESTART_SEARCH_UNPROVEN" in printed.out


def test_measure_restarts_reports_the_librarys_refusal_and_returns_two(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
    from so101_demo.act.head_search_restarts import contracts as restarts_contracts
    from so101_demo.act.head_search_restarts import writer as restarts_writer

    inputs = _restart_inputs(tmp_path)
    _patch_restart_flight(monkeypatch)

    def refuse(**kwargs):
        raise CalibrationInputsRefused(
            restarts_contracts.RESTART_OWNERSHIP_REFUSED,
            "the exclusive-ownership gate refused with STACK_OWNER_ACTIVE",
        )

    monkeypatch.setattr(restarts_writer, "write_head_search_restarts", refuse)
    assert main(_restart_arguments(inputs, tmp_path / "restart-run")) == 2
    assert restarts_contracts.RESTART_OWNERSHIP_REFUSED in capsys.readouterr().err


def test_serve_teleop_runs_the_owned_acceptance_with_the_plans_declarations(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    """The installed entry must reach the acceptance with every declaration the plan names.

    Before HS-325 this handler wrote a descriptor from a `--report` it had to be handed and returned 0
    without starting, probing or tearing anything down.
    """

    from so101_demo.act.head_search_teleop_acceptance import acceptance as acceptance_acceptance

    recorded: dict = {}

    def fake_accept(**kwargs):
        recorded.update(kwargs)
        return {"status": "REFUSED", "refusals": [{"code": "X", "detail": "y"}]}

    monkeypatch.setattr(acceptance_acceptance, "accept_teleop", fake_accept)
    final_run = tmp_path / "frozen"
    (final_run / "install/so101_demo_py/share/so101_demo_py/config/mujoco/act").mkdir(parents=True)
    (
        final_run / "install/so101_demo_py/share/so101_demo_py/config/mujoco/act/head_search_runtime.json"
    ).write_text(json.dumps({"values": {}}), encoding="utf-8")
    acceptance_root = tmp_path / "teleop-acceptance"
    rc = main(
        [
            "serve-teleop",
            "--run-root",
            str(acceptance_root / "runtime"),
            "--final-run",
            str(final_run),
            "--bundle",
            str(tmp_path / "head-search-calibration-bundle.json"),
            "--qualification-report",
            str(tmp_path / "head-search-qualified-report.json"),
            "--approval-receipt",
            str(tmp_path / "approval-receipt.json"),
            "--production-config",
            str(tmp_path / "promoted.json"),
            "--profile",
            "mujoco",
            "--runtime-id",
            "head-teleop-956b5b74b",
            "--bridge-socket-root",
            str(tmp_path / "sock"),
            "--ready-file",
            str(acceptance_root / "runtime-connection.json"),
            "--expected-source-commit",
            "956b5b74b",
        ]
    )

    assert rc == 2, "a refused acceptance is not a pass"
    assert recorded["final_run"] == final_run
    assert recorded["acceptance_root"] == acceptance_root, "the ready file's own directory is the root"
    assert recorded["socket_root"] == tmp_path / "sock"
    assert recorded["runtime_id"] == "head-teleop-956b5b74b"
    assert recorded["profile"] == "mujoco"
    assert recorded["expected"] == {"source_commit": "956b5b74b"}
    assert "HEAD_SEARCH_QUALIFIED_REQUIRED" not in capsys.readouterr().err


def test_serve_teleop_refuses_without_the_acceptance_declarations(tmp_path: Path, capsys) -> None:
    """No descriptor is written without the bundle the acceptance must be bound to."""

    rc = main(["serve-teleop", "--run-root", str(tmp_path / "runtime"), "--runtime-id", "x"])

    assert rc == 2
    assert "TELEOP_ACCEPTANCE_INPUTS_INCOMPLETE" in capsys.readouterr().err


def test_serve_teleop_reports_a_library_refusal_by_name(tmp_path: Path, monkeypatch, capsys) -> None:
    from so101_demo.act.head_search_teleop_acceptance import acceptance as acceptance_acceptance
    from so101_demo.act.head_search_teleop_acceptance import receipts as acceptance_receipts
    from so101_demo.act.head_search_teleop_acceptance import runners as acceptance_runners

    def refuse(**kwargs):
        raise acceptance_runners.TeleopAcceptanceRefused(
            acceptance_receipts.TELEOP_SOCKET_PATH_TOO_LONG, "the socket path is 158 bytes"
        )

    monkeypatch.setattr(acceptance_acceptance, "accept_teleop", refuse)
    final_run = tmp_path / "frozen"
    final_run.mkdir()
    rc = main(
        [
            "serve-teleop",
            "--run-root",
            str(tmp_path / "runtime"),
            "--final-run",
            str(final_run),
            "--bundle",
            str(tmp_path / "b.json"),
            "--runtime-id",
            "x",
        ]
    )

    assert rc == 2
    assert acceptance_receipts.TELEOP_SOCKET_PATH_TOO_LONG in capsys.readouterr().err
