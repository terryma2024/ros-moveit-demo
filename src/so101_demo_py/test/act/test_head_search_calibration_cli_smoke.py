"""The production smoke subcommand and the smoke script entry."""

from __future__ import annotations

import json
from pathlib import Path

from head_search_calibration_cli_support import _restart_inputs

from so101_demo.cli.head_search.flags import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
)
from so101_demo.cli.head_search_calibration import main


def _production_smoke_inputs(tmp_path: Path) -> dict:
    """The declared inputs of `measure-production-smoke`: the restart fixture plus the sealed step."""

    inputs = _restart_inputs(tmp_path)
    seal = json.loads(Path(inputs["seal"]).read_text(encoding="utf-8"))
    seal["coarse_step_candidate_rad"] = 0.3
    Path(inputs["seal"]).write_text(json.dumps(seal), encoding="utf-8")
    # the Step 1 receipt guards the smoke's own run root, not the restart fixture's
    inputs["smoke_run_root"] = tmp_path / "production-smoke-run"
    Path(inputs["ownership"]).write_text(
        json.dumps(
            {
                "operation": "QUALIFICATION_OWNERSHIP_CHECK",
                "status": "EXCLUSIVE_OWNERSHIP_OK",
                "refusals": [],
                "planned_run_root": str(inputs["smoke_run_root"]),
            }
        ),
        encoding="utf-8",
    )
    return inputs


def _production_smoke_arguments(inputs: dict, run_root: Path, *extra: str) -> list:
    return [
        "measure-production-smoke",
        "--run-root",
        str(run_root),
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


def _patch_production_smoke_flight(monkeypatch, *, terminal="TARGET_LOCKED", teardown=None):
    """Stub the two heavy seams: the runtime readback and the one smoke flight itself."""

    from so101_demo.act.head_search_production_smoke import aggregate as smoke_aggregate
    from so101_demo.act.head_search_restarts import contracts as restarts_contracts
    from so101_demo.act.head_search_restarts import observation as restarts_observation

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
        frames = [
            {
                "index": index,
                "frame_sim_s": 12.0 + index * 0.1,
                "received_monotonic_s": 100.0 + index * 0.1,
                "decision_monotonic_s": 100.005 + index * 0.1,
                "frame_age_s": 0.005,
                "source_skew_s": 0.001,
                "inference_s": 0.0053,
                "detections": 1,
                "lock_count": index,
                "status": "TARGET_LOCKED" if index >= 2 else "CENTER_CUP",
            }
            for index in range(5)
        ]
        return {
            "anchor": anchor,
            "declared_anchor": dict(kwargs["declared"]),
            "stack": {
                "nodes": list(restarts_contracts.STACK_OWNED_NODES),
                "processes": [{"pid": "11", "argv": "lib/mujoco_ros2_control/ros2_control_node"}],
                "gpu_compute_apps": [],
            },
            "camera": {
                "measured_rate_hz": 10.0,
                "frames": 40,
                "published_frame_id": "head_camera_frame",
            },
            "clock": {"advancing": True, "delta_s": 3.0},
            "scene": {"body": "plastic_cup", "point_m": [0.02, -0.28, 0.165], "service": "/s"},
            "detector": {
                "loaded": True,
                "count": 1,
                "device": "cuda",
                "runtime_device": "cuda:0",
                "allow_cpu_fallback": False,
                "weights_sha256": "2" * 64,
                "model_id": "head-search-runtime",
            },
            "frames": frames,
            "search": {
                "terminal_status": terminal,
                "terminal": {"status": terminal, "stop": True},
                "coverage_complete": True,
                "coverage": {
                    "complete": True,
                    "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
                },
                "wrong_locks": 0,
                "commands": {
                    "corridor_rad": [-6.283175307179587, 6.283175307179587],
                    "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
                    "targets": [
                        {"index": 0, "target_rad": 0.1, "statuses": ["SEARCH_START"], "ticks": 1},
                        {"index": 1, "target_rad": 0.231, "statuses": ["CENTER_CUP"], "ticks": 4},
                    ],
                },
            },
            "lock": {"consecutive_frames": 3, "track_id": 7},
            "stop": {
                "proven": True,
                "qualifying_samples": 3,
                "sample_count": 3,
                "velocity_limit_rad_s": 0.04136050464213824,
                "samples": [
                    {"velocity_rad_s": 0.0, "settled": True, "reached": True} for _ in range(3)
                ],
                "held_at_rad": 0.231,
            },
            "teardown": teardown
            or {
                "previous_stack_stopped": True,
                "controller_owner_stopped": True,
                "children_exited": True,
                "graph_clear": True,
                "gpu_released": True,
                "gpu_compute_apps": [],
            },
            "reconstruction": {
                "stack_started": True,
                "one_mujoco_instance": True,
                "one_controller_owner": True,
            },
            "elapsed_s": 61.5,
            "started_at_utc": "2026-10-02T00:00:00Z",
            "finished_at_utc": "2026-10-02T00:01:01Z",
        }

    monkeypatch.setattr(restarts_observation, "read_runtime_of_record", fake_runtime)
    monkeypatch.setattr(smoke_aggregate, "run_smoke_flight", fake)
    return seen


def test_measure_production_smoke_refuses_missing_inputs_and_an_existing_root(
    tmp_path: Path, capsys
) -> None:
    inputs = _production_smoke_inputs(tmp_path)
    missing = _production_smoke_arguments(inputs, tmp_path / "smoke-run")
    missing[missing.index("--scene") + 1] = str(tmp_path / "absent.xml")
    assert main(missing) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err

    existing = tmp_path / "already-there"
    existing.mkdir()
    assert main(_production_smoke_arguments(inputs, existing)) == 2
    assert "never resumed" in capsys.readouterr().err


def test_measure_production_smoke_writes_the_journal_the_gate_consumes(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.act.head_search_aggregate import contracts as aggregate_contracts
    from so101_demo.act.head_search_aggregate import (
        measurement_gates as aggregate_measurement_gates,
    )
    from so101_demo.act.head_search_production_smoke import journal as smoke_journal

    inputs = _production_smoke_inputs(tmp_path)
    seen = _patch_production_smoke_flight(monkeypatch)
    run_root = inputs["smoke_run_root"]

    rc = main(_production_smoke_arguments(inputs, run_root, "--scenario", "nominal"))

    assert rc == 0
    assert seen["anchor"] == "default"
    assert seen["device"] == "cuda"
    printed = capsys.readouterr().out
    assert "SMOKE_MEASURED status=PASS" in printed
    document = json.loads((run_root / smoke_journal.JOURNAL_ARTIFACT).read_text(encoding="utf-8"))
    assert document["kind"] == aggregate_contracts.SMOKE_KIND
    assert document["phase"] == "production_smoke"
    assert document["terminal_status"] == "TARGET_LOCKED"
    assert document["condition_class"] == "nominal"
    assert set(document["gates"].values()) == {"PASS"}
    assert document["producer"]["entry"] == "so101_head_search_calibration measure-production-smoke"
    assert (run_root / smoke_journal.SEALED_ARTIFACT).is_file()
    assert (run_root / smoke_journal.RECEIPT_ARTIFACT).is_file()
    # the coverage proof is still produced, and it is still not the success condition
    assert (run_root / smoke_journal.COVERAGE_PROOF_ARTIFACT).is_file()
    assert (run_root / "default" / "stdout.log").is_file()
    assert (run_root / "default" / "stderr.log").is_file()

    reasons = aggregate_contracts._Reasons()
    aggregate_measurement_gates._gate_smoke(
        {"production_smoke_root": str(run_root)},
        {
            "runtime": {
                key: json.loads((run_root / smoke_journal.JOURNAL_ARTIFACT).read_text(encoding="utf-8"))[
                    "runtime"
                ].get(key)
                for key in (
                    "source_commit",
                    "production_config_sha256",
                    "values_sha256",
                    "weight_sha256_declared",
                    "weight_sha256_observed",
                )
            }
        },
        reasons,
    )
    assert reasons.missing == [] and reasons.violations == []


def test_measure_production_smoke_returns_two_when_the_cup_is_not_locked(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.act.head_search_production_smoke import journal as smoke_journal

    inputs = _production_smoke_inputs(tmp_path)
    _patch_production_smoke_flight(monkeypatch, terminal="TARGET_AMBIGUOUS")
    run_root = inputs["smoke_run_root"]

    assert main(_production_smoke_arguments(inputs, run_root)) == 2
    printed = capsys.readouterr()
    assert "SMOKE_LOCK_UNPROVEN" in printed.err
    document = json.loads((run_root / smoke_journal.JOURNAL_ARTIFACT).read_text(encoding="utf-8"))
    assert document["status"] == "REFUSED"
    assert document["gates"]["search"] == "FAIL"


def test_measure_production_smoke_reports_the_librarys_refusal_and_returns_two(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.act.head_search_production_smoke import aggregate as smoke_aggregate
    from so101_demo.act.head_search_production_smoke import journal as smoke_journal

    inputs = _production_smoke_inputs(tmp_path)
    _patch_production_smoke_flight(monkeypatch)

    def refuse(**kwargs):
        raise smoke_journal.SmokeRefused(
            smoke_journal.SMOKE_OWNERSHIP_REFUSED, "the gate refused with STACK_OWNER_ACTIVE"
        )

    monkeypatch.setattr(smoke_aggregate, "write_head_search_production_smoke", refuse)
    assert main(_production_smoke_arguments(inputs, inputs["smoke_run_root"])) == 2
    assert smoke_journal.SMOKE_OWNERSHIP_REFUSED in capsys.readouterr().err


def test_the_plan_smoke_entry_runs_the_production_smoke_when_given_a_run_root(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.cli import head_search_smoke
    from so101_demo.cli.head_search import flags as calibration_flags
    from so101_demo.cli.head_search import smoke_readback as calibration_head_search_calibration

    seen: dict = {}

    def fake(arguments, *, entry=None):
        seen["arguments"] = list(arguments)
        seen["entry"] = entry
        return 7

    monkeypatch.setattr(calibration_head_search_calibration, "_measure_production_smoke", fake)
    rc = head_search_smoke.main(
        [
            "--run-root",
            str(tmp_path / "smoke-run"),
            "--geometry-seal",
            "seal.json",
            "--scenario",
            "nominal",
        ]
    )

    assert rc == 7
    assert seen["arguments"] == [
        "--run-root",
        str(tmp_path / "smoke-run"),
        "--geometry-seal",
        "seal.json",
        "--scenario",
        "nominal",
    ]
    assert seen["entry"] == calibration_flags.PRODUCTION_SMOKE_SCRIPT_ENTRY


def test_the_plan_smoke_entry_still_plans_coverage_without_a_run_root(
    tmp_path: Path, capsys
) -> None:
    """Requirement (b): the coverage proof stays available through the plan's own entry name."""

    from so101_demo.cli.head_search_smoke import main as smoke_main

    seal = tmp_path / "seal.json"
    seal.write_text(
        json.dumps(
            {
                "seal_sha256": "a" * 64,
                "horizontal_fov_rad": 1.3121067481206794,
                "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                "required_search_domain_rad": [-0.29145679447786704, 0.540419500270584],
                "anchors": {"default": {"neck_rad": 0.1}},
                "camera": {"coarse_step_rad": 0.3},
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "coverage-run"
    assert (
        smoke_main(["--geometry-seal", str(seal), "--anchor", "default", "--output", str(output)])
        == 0
    )
    proof = json.loads((output / "coverage-proof.json").read_text(encoding="utf-8"))
    assert proof["coverage_complete"] is True
    assert proof["seal_sha256"] == "a" * 64
    assert not (output / "production-smoke-journal.json").exists()
