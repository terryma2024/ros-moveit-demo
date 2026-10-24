"""Synthetic head-search qualification fixtures: one complete, self-consistent evidence set on disk.

Nothing here measures anything and nothing here starts a stack, a detector or a GPU: every document is
written by this builder so that the `aggregate` phase's declared gates can be exercised one at a time.
The set is deliberately *self-consistent* - the scenarios document's own canonical digest, the journal
rows and the per-scenario evidence documents all agree - so that a test which tampers with exactly one
document can only be refused because of that document.

The builder is the fixture half of `test_act_head_search_aggregate.py`; the CLI test file imports it too,
so both the library entry and the installed entry are exercised against the same bytes.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from so101_demo.act.head_search.scenarios.contracts import (
    ARTIFACT,
    EVIDENCE_DIR,
    EXPECTED_TERMINALS,
    JOURNAL_ARTIFACT,
    KIND,
    PHASE,
    QUALIFICATION_SPLIT,
)
from so101_demo.act.head_search.scenarios.journal import aggregate_scenarios, scenario_journal_entry
from so101_demo.act.head_search.scenarios.plan import (
    check_frame_cadence,
    declared_cup_count,
    expected_terminals,
    requires_interruption,
)
from so101_demo.act.head_search.scenarios.scenario_run import classify_scenario
from so101_demo.act.head_search.scenarios.stop_proof import stop_proof
from so101_demo.act.head_search.timing_measurement.contracts import FRAME_PERIOD_S
from so101_demo.act.head_search.binding import _CAMERA_MEASURED, _MEASURED
from so101_demo.act.head_search.ownership import OPERATION as OWNERSHIP_OPERATION
from so101_demo.act.head_search.ownership import read_runtime_identity
from so101_demo.perception_benchmark.contracts import canonical_sha256

SOURCE_COMMIT = "9" * 40
STOP_VELOCITY_RAD_S = 0.04
FRAME_RATE_HZ = 10.0
ANCHORS = ("default", "left", "forward")
CONDITION_CLASSES = tuple(EXPECTED_TERMINALS)
#: the promoted values the fixture pretends were approved, one per `_MEASURED` name
FIXTURE_VALUES = {
    name: (float(index) + 0.25 if name not in ("max_fine_corrections",) else 2)
    for index, name in enumerate(_MEASURED)
}
FIXTURE_VALUES["lock_valid_neck_rad"] = [-1.5, 1.5]
FIXTURE_VALUES["vertical_bounds_px"] = [180.0, 300.0]
FIXTURE_CAMERA_MEASUREMENTS = {
    "head_intrinsics_px": {"fx": 480.0, "fy": 480.0, "cx": 320.0, "cy": 240.0},
    "head_translation_m": [0.05, 0.0, 0.30],
    "head_rpy_rad": [0.0, 0.35, 0.0],
    "yaw_zero_bearing_rad": 0.12,
}


def _write(path: Path, document) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def digest(path: Path) -> str:
    import hashlib

    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bare(value):
    """`{name: {value: v}}` and `{name: v}` are the same declaration; this is the bare value."""

    if isinstance(value, dict) and "value" in value:
        return value["value"]
    return value


@dataclass
class Fixture:
    """The written evidence set, the declared inputs, and the paths a test may tamper with."""

    root: Path
    run_root: Path
    partitions: Path
    paths: dict = field(default_factory=dict)

    def inputs(self, **overrides) -> dict:
        declared = {
            "ownership_receipt": self.paths["ownership_receipt"],
            "final_run": self.paths["final_run"],
            "production_config": self.paths["production_config"],
            "approved_bundle": self.paths["approved_bundle"],
            "runtime_readback": self.paths["runtime_readback"],
            "production_smoke_root": self.paths["production_smoke_root"],
            "scenarios_root": self.paths["scenarios_root"],
            "restart_receipts": [
                self.paths[f"restart_{anchor}"] for anchor in ANCHORS
            ],
            "teleop_acceptance_receipt": self.paths["teleop_acceptance_receipt"],
            "scenario_partitions": self.partitions,
        }
        declared.update(overrides)
        return declared

    def inputs_without(self, *names: str) -> dict:
        declared = self.inputs()
        for name in names:
            declared.pop(name, None)
        return declared


def fixture_partitions(seed_base: int = 900000) -> dict:
    """Forty declared qualification items, ten classes by four seeds, spread over the three anchors."""

    items = []
    for index in range(40):
        condition_class = CONDITION_CLASSES[index % len(CONDITION_CLASSES)]
        items.append(
            {
                "seed": seed_base + index,
                "scene_group_id": f"scene-{seed_base + index:09d}",
                "condition_class": condition_class,
                "anchor": ANCHORS[index % len(ANCHORS)],
            }
        )
    return {
        "schema_version": 1,
        QUALIFICATION_SPLIT: items,
        "calibration": [700000 + index for index in range(20)],
        "held_out_evaluation": [800000 + index for index in range(20)],
    }


def _synthetic_attempt(*, seed: int, index: int, injected: bool, terminal) -> dict:
    return {
        "index": index,
        "attempt_id": f"head-search-qualification-fixture-{seed}-attempt-{index + 1}",
        "frame_count": 3,
        "detection_frames": 3,
        "terminal_status": None if injected else terminal,
        "found": False if injected else terminal == "TARGET_LOCKED",
        "stop": True,
        "stop_status": "STOPPED",
        "interruption_injected": injected,
        "interruption_decision_status": "STOPPED" if injected else None,
        "lock_count_before_interruption": 0 if injected else None,
        "lock_count_after_interruption": 0 if injected else None,
        "lock_count_cleared_by_interruption": True if injected else None,
        "track_after_interruption": None,
        "track_cleared_by_controller": True,
        "detector_reset_before_attempt": True,
        "fine_corrections": 0,
        "cumulative_fine_correction_rad": 0.0,
        "controller_fine_count": 0,
        "controller_fine_angle_rad": 0.0,
        "corrections_match_controller": True,
        "refusal": None,
    }


def _synthetic_entry(item: dict, index: int, *, terminal=None) -> dict:
    condition_class = item["condition_class"]
    seed = int(item["seed"])
    chosen = terminal or expected_terminals(condition_class)[0]
    interrupted = requires_interruption(condition_class)
    pre_terminal = expected_terminals(condition_class)[0] if not interrupted else None
    attempts = []
    if interrupted:
        attempts.append(_synthetic_attempt(seed=seed, index=0, injected=True, terminal=pre_terminal))
    attempts.append(
        _synthetic_attempt(
            seed=seed, index=len(attempts), injected=False, terminal=chosen if not interrupted else chosen
        )
    )
    if interrupted:
        # the reacquiring attempt is the one that reaches the terminal status
        attempts[-1]["terminal_status"] = chosen
        attempts[-1]["found"] = chosen == "TARGET_LOCKED"
    entry = {
        "scenario_index": index,
        "seed": seed,
        "scene_group_id": item["scene_group_id"],
        "condition_class": condition_class,
        "anchor": item["anchor"],
        "cup_count": declared_cup_count(condition_class),
        "scenario_name": f"scenario-{seed}",
        "expected_terminals": list(expected_terminals(condition_class)),
        "terminal_status": chosen,
        "found": chosen == "TARGET_LOCKED",
        "locked": chosen == "TARGET_LOCKED",
        "locked_neck_rad": 0.0 if chosen == "TARGET_LOCKED" else None,
        "cup_found": chosen in ("TARGET_LOCKED", "TARGET_AMBIGUOUS"),
        "detection_frames": 3,
        "frame_count": 3,
        "plan_moves": 0 if chosen == "TARGET_NOT_FOUND" else 1,
        "fine_corrections": 0,
        "fine_corrections_rad": [],
        "cumulative_fine_correction_rad": 0.0,
        "largest_single_correction_rad": 0.0,
        "controller_fine_count": 0,
        "controller_fine_angle_rad": 0.0,
        "control_thresholds": {"max_fine_corrections": 2, "max_fine_total_rad": 0.7},
        "coverage": {
            "complete": True,
            "required_search_domain_rad": [-1.5, 1.5],
            "covered_rad": [[-1.5, 1.5]],
        },
        "stop_proof": stop_proof(
            [
                {"velocity_rad_s": 0.0, "settled": True, "reached": True, "position_error_rad": 0.0}
                for _ in range(3)
            ],
            velocity_limit_rad_s=STOP_VELOCITY_RAD_S,
        ),
        "frame_cadence": check_frame_cadence(
            [{"frame_sim_s": round(FRAME_PERIOD_S * step, 6)} for step in range(3)],
            frame_period_s=FRAME_PERIOD_S,
            max_settle_s=5.0,
        ),
        "attempt_ids": [attempt["attempt_id"] for attempt in attempts],
        "attempts": attempts,
        "evidence": {
            "seed": seed,
            "anchor": item["anchor"],
            "condition_class": condition_class,
            "scene_group_id": item["scene_group_id"],
            "frame_period_s": FRAME_PERIOD_S,
            "frame_rate_hz": FRAME_RATE_HZ,
            "device": "cuda",
        },
    }
    return classify_scenario(entry)


def _scenarios_document(
    entries: list[dict],
    *,
    seeds: list[int],
    partitions_path: Path,
    final_run: Path,
    runtime_identity: dict,
    production_config: Path,
    weights: Path,
    weights_sha256: str,
) -> dict:
    aggregate = aggregate_scenarios(entries)
    anchor_split: dict[str, int] = {}
    for entry in entries:
        anchor_split[str(entry["anchor"])] = anchor_split.get(str(entry["anchor"]), 0) + 1
    document = {
        "schema_version": 1,
        "kind": KIND,
        "phase": PHASE,
        "split": QUALIFICATION_SPLIT,
        "command": "fixture",
        "seeds": list(seeds),
        "scenario_count": aggregate["scenario_count"],
        "passed_count": aggregate["passed_count"],
        "failed_count": aggregate["failed_count"],
        "refused_count": aggregate["refused_count"],
        "by_condition_class": aggregate["by_condition_class"],
        "by_anchor": aggregate["by_anchor"],
        "anchor_split": anchor_split,
        "terminal_statuses": aggregate["terminal_statuses"],
        "zero_wrong_locks": aggregate["zero_wrong_locks"],
        "wrong_locks": aggregate["wrong_locks"],
        "fine_corrections": aggregate["fine_corrections"],
        "cumulative_fine_correction_rad": aggregate["cumulative_fine_correction_rad"],
        "cadence_all_continuous": aggregate["cadence_all_continuous"],
        "stop_proofs_all_proven": aggregate["stop_proofs_all_proven"],
        "records": [scenario_journal_entry(entry) for entry in entries],
        "qualification_verdict": None,
        "qualification_verdict_owner": (
            "so101_demo.act.head_search.qualification (the qualifier's `aggregate` phase)"
        ),
        "fit_warning": "fixture",
        "runtime_identity": dict(runtime_identity),
        "values_count": len(FIXTURE_VALUES),
        "values_sha256": canonical_sha256(dict(FIXTURE_VALUES)),
        "frame_period_s": FRAME_PERIOD_S,
        "frame_rate_hz": FRAME_RATE_HZ,
        "device": "cuda",
        "cuda_used": True,
        "detector_loaded": True,
        "production_search_config": {
            "path": str(production_config),
            "sha256": digest(production_config),
        },
        "weights": {"path": str(weights), "sha256": weights_sha256},
        "scenario_partitions": {
            "path": str(partitions_path),
            "sha256": digest(partitions_path),
        },
        "final_run": str(final_run),
    }
    document["sha256"] = canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    return document


def _smoke_journal(path: Path) -> dict:
    frames = [{"frame_sim_s": round(FRAME_PERIOD_S * index, 6)} for index in range(4)]
    path.write_text(
        "".join(json.dumps(frame, sort_keys=True) + "\n" for frame in frames), encoding="utf-8"
    )
    return check_frame_cadence(frames, frame_period_s=FRAME_PERIOD_S, max_settle_s=5.0)


def _restart_receipt(anchor: str, runtime: dict, bundle_sha256: str) -> dict:
    return {
        "schema_version": 1,
        "kind": "head_search_full_restart_receipt",
        "phase": f"restart_{anchor}",
        "anchor": anchor,
        "lifecycle": "FULL_RESTART",
        "runtime": {
            "final_run": runtime["final_run"],
            "source_commit": runtime["source_commit"],
            "production_config_sha256": runtime["production_config_sha256"],
            "values_sha256": runtime["values_sha256"],
            "weight_sha256_declared": runtime["weight_sha256_declared"],
            "weight_sha256_observed": runtime["weight_sha256_observed"],
            "allow_cpu_fallback": runtime["allow_cpu_fallback"],
            "cuda_device": runtime["cuda_device"],
        },
        "approved_bundle_sha256": bundle_sha256,
        "teardown": {
            "previous_stack_stopped": True,
            "controller_owner_stopped": True,
            "children_exited": True,
            "graph_clear": True,
        },
        "reconstruction": {
            "stack_started": True,
            "one_mujoco_instance": True,
            "one_controller_owner": True,
            "ros_graph_clear_before_start": True,
        },
        "detector": {"loaded": True, "count": 1, "device": "cuda", "weights_sha256": runtime["weights"]},
        "search": {"terminal_status": "TARGET_LOCKED", "coverage_complete": True, "wrong_locks": 0},
        "lock": {"consecutive_frames": 3, "centred_inside_deadband": True},
        "timing": {
            "frame_rate_hz": FRAME_RATE_HZ,
            "cadence_continuous": True,
            "within_thresholds": True,
        },
        "stop": {"proven": True, "qualifying_samples": 3, "required_samples": 3},
        "gates": {
            "graph": "PASS",
            "detector": "PASS",
            "search": "PASS",
            "lock": "PASS",
            "timing": "PASS",
            "stop": "PASS",
        },
    }


def build_fixture(root: Path, *, run_root: Path | None = None, seed_base: int = 900000) -> Fixture:
    """Write one complete, consistent evidence set under `root` and return its declared inputs."""

    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    run_root = Path(run_root) if run_root is not None else root / "qualification-run"
    partitions_path = _write(root / "partitions.json", fixture_partitions(seed_base))
    paths: dict = {"partitions": partitions_path}

    # the frozen runtime root: commit stamp, overlay marker, promoted config and the weights it seals
    final_run = root / "final-run"
    (final_run / "install/so101_demo_py/share/so101_demo_py/config/mujoco/act").mkdir(
        parents=True, exist_ok=True
    )
    (final_run / "source-commit.txt").write_text(SOURCE_COMMIT + "\n", encoding="utf-8")
    (final_run / "install/setup.bash").write_text("# fixture\n", encoding="utf-8")
    weights = final_run / "weights/best.pt"
    weights.parent.mkdir(parents=True, exist_ok=True)
    weights.write_bytes(b"fixture-weights\n")
    weights_sha256 = digest(weights)
    production_config = (
        final_run / "install/so101_demo_py/share/so101_demo_py/config/mujoco/act/head_search_runtime.json"
    )
    _write(
        production_config,
        {
            "schema_version": 1,
            "kind": "head_search_v2",
            "weight_path": str(weights),
            "weight_sha256": weights_sha256,
            "allow_cpu_fallback": False,
            "cuda_device": "cuda:0",
            "values": dict(FIXTURE_VALUES),
        },
    )
    runtime = read_runtime_identity(final_run)
    runtime["weights"] = weights_sha256
    paths["final_run"] = final_run
    paths["production_config"] = production_config

    approved_bundle = _write(
        root / "approved-bundle.json",
        {
            "schema_version": 1,
            "kind": "head_search_calibration_bundle",
            "parameter_names": list(_MEASURED),
            "parameters": {name: {"value": FIXTURE_VALUES[name]} for name in _MEASURED},
            "runtime_identity": {"detector_weights_sha256": weights_sha256},
        },
    )
    bundle_sha256 = digest(approved_bundle)
    paths["approved_bundle"] = approved_bundle

    # the Step 1 exclusive-ownership receipt, taken for exactly this run root
    paths["ownership_receipt"] = _write(
        root / "ownership/exclusive-ownership.json",
        {
            "schema_version": 1,
            "operation": OWNERSHIP_OPERATION,
            "status": "EXCLUSIVE_OWNERSHIP_OK",
            "run_root": str(root / "ownership"),
            "evidence_root": str(root),
            "planned_run_root": str(run_root),
            "expected_runtime": {
                "source_commit": runtime["source_commit"],
                "production_config_sha256": runtime["production_config_sha256"],
                "values_sha256": runtime["values_sha256"],
                "weight_sha256_declared": runtime["weight_sha256_declared"],
            },
            "refusals": [],
        },
    )

    # the during-qualification readback: all 17 effective values and the four camera measurements
    paths["runtime_readback"] = _write(
        root / "runtime-readback.json",
        {
            "schema_version": 1,
            "kind": "head_search_qualification_runtime_readback",
            "phase": "production_smoke",
            "run_root": str(run_root),
            "final_run": str(final_run),
            "source_commit": runtime["source_commit"],
            "production_config_sha256": runtime["production_config_sha256"],
            "values_count": len(FIXTURE_VALUES),
            "values_sha256": canonical_sha256(dict(FIXTURE_VALUES)),
            "values": {
                name: {"value": FIXTURE_VALUES[name], "effective_value": FIXTURE_VALUES[name]}
                for name in _MEASURED
            },
            "camera_measurements": {
                name: {"value": FIXTURE_CAMERA_MEASUREMENTS[name]} for name in _CAMERA_MEASURED
            },
            "weight_path": str(weights),
            "weight_sha256_declared": weights_sha256,
            "weight_sha256_observed": weights_sha256,
            "allow_cpu_fallback": False,
            "cuda_device": "cuda:0",
            "device": "cuda",
            "cuda_used": True,
            "detector": {
                "count": 1,
                "device": "cuda",
                "allow_cpu_fallback": False,
                "weights_sha256": weights_sha256,
            },
        },
    )

    # the production smoke: a sealed journal, its producer and the aggregator that consumed it
    smoke_root = root / "smoke"
    smoke_root.mkdir(parents=True, exist_ok=True)
    journal_path = smoke_root / "search-journal.jsonl"
    cadence = _smoke_journal(journal_path)
    paths["production_smoke_root"] = smoke_root
    paths["smoke_journal"] = _write(
        smoke_root / "production-smoke-journal.json",
        {
            "schema_version": 1,
            "kind": "head_search_production_smoke_journal",
            "phase": "production_smoke",
            "runtime": {
                "final_run": runtime["final_run"],
                "source_commit": runtime["source_commit"],
                "production_config_sha256": runtime["production_config_sha256"],
                "values_sha256": runtime["values_sha256"],
                "weight_sha256_declared": runtime["weight_sha256_declared"],
                "weight_sha256_observed": runtime["weight_sha256_observed"],
            },
            "producer": {
                "entry": "so101_head_search_smoke",
                "argv_sha256": "a" * 64,
                "stack_owned": True,
            },
            "journal": {"path": str(journal_path), "sha256": digest(journal_path)},
            "aggregator": {
                "entry": "so101_demo.act.head_search.qualification",
                "journal_sha256": digest(journal_path),
                "status": "SUCCEEDED",
            },
            "terminal_status": "TARGET_LOCKED",
            "frame_cadence": cadence,
            "commands": {
                "bounded": True,
                "outside_corridor_count": 0,
                "corridor_rad": [-1.5, 1.5],
                "max_abs_neck_rad": 0.5,
            },
            "stop_proof": stop_proof(
                [
                    {"velocity_rad_s": 0.0, "settled": True, "reached": True}
                    for _ in range(3)
                ],
                velocity_limit_rad_s=STOP_VELOCITY_RAD_S,
            ),
            "detector": {
                "count": 1,
                "device": "cuda",
                "allow_cpu_fallback": False,
                "weights_sha256": weights_sha256,
            },
            "zero_wrong_locks": True,
        },
    )

    # the forty serial scenarios: journal rows, per-scenario evidence and the honest aggregate
    scenarios_root = root / "scenarios-run"
    evidence_dir = scenarios_root / EVIDENCE_DIR
    evidence_dir.mkdir(parents=True, exist_ok=True)
    items = fixture_partitions(seed_base)[QUALIFICATION_SPLIT]
    entries = [_synthetic_entry(item, index) for index, item in enumerate(items)]
    rows = [scenario_journal_entry(entry) for entry in entries]
    (scenarios_root / JOURNAL_ARTIFACT).write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8"
    )
    for entry in entries:
        _write(evidence_dir / f"{entry['seed']}.json", entry)
    document = _scenarios_document(
        entries,
        seeds=[int(item["seed"]) for item in items],
        partitions_path=partitions_path,
        final_run=final_run,
        runtime_identity=runtime,
        production_config=production_config,
        weights=weights,
        weights_sha256=weights_sha256,
    )
    _write(scenarios_root / ARTIFACT, document)
    paths["scenarios_root"] = scenarios_root
    paths["scenarios_document"] = scenarios_root / ARTIFACT
    paths["scenarios_journal"] = scenarios_root / JOURNAL_ARTIFACT
    paths["scenario_evidence_dir"] = evidence_dir

    # one independent FULL_RESTART per anchor
    for anchor in ANCHORS:
        paths[f"restart_{anchor}"] = _write(
            root / f"restarts/restart-{anchor}-receipt.json",
            _restart_receipt(anchor, runtime, bundle_sha256),
        )

    # a closed head-only report of the same bundle and runtime, and the acceptance that consumed it
    prior_report = _write(
        root / "prior-qualification/head-search-qualified-report.json",
        {
            "status": "HEAD_SEARCH_QUALIFIED",
            "operation": "QUALIFICATION_RUN",
            "runtime_id": f"{final_run.name}@{SOURCE_COMMIT[:12]}",
            "bundle_sha256": bundle_sha256,
        },
    )
    paths["prior_report"] = prior_report
    # AF_UNIX endpoints are capped at 103 bytes, so the fixture's socket root is deliberately short:
    # a pytest tmp_path under the NVMe scratch directory is already longer than the whole budget
    socket_root = Path("/tmp") / f"head-search-ipc-{os.getpid()}"
    socket_root.mkdir(parents=True, exist_ok=True)
    cleanup_receipt = _write(
        socket_root / "cleanup-receipt.json",
        {"controller_stopped": True, "graph_clear": True, "process_groups_exited": 2},
    )
    screenshots = []
    for name in (
        "raw-light-desktop.png",
        "raw-dark-narrow.png",
        "overlay-light-desktop.png",
        "overlay-dark-narrow.png",
        "stopped-light-desktop.png",
        "conflict-dark-narrow.png",
    ):
        shot = root / "teleop/screenshots" / name
        shot.parent.mkdir(parents=True, exist_ok=True)
        shot.write_bytes(b"\x89PNG\r\n\x1a\nfixture\n")
        screenshots.append(str(shot))
    paths["teleop_acceptance_receipt"] = _write(
        root / "teleop/acceptance-receipt.json",
        {
            "schema_version": 1,
            "kind": "head_search_teleop_acceptance_receipt",
            "operation": "TELEOP_ACCEPTANCE",
            "runtime_id": f"{final_run.name}@{SOURCE_COMMIT[:12]}",
            "source_commit": SOURCE_COMMIT,
            "bundle_sha256": bundle_sha256,
            "qualification_report": {
                "path": str(prior_report),
                "sha256": digest(prior_report),
                "status": "HEAD_SEARCH_QUALIFIED",
            },
            "detector": {"count": 1, "device": "cuda", "teleop_detector_factory_count": 0},
            "teardown": {
                "controller_stopped": True,
                "process_groups_exited": 2,
                "graph_clear": True,
            },
            "bridge": {
                "socket_paths": [
                    str(socket_root / "normal.sock"),
                    str(socket_root / "safety.sock"),
                ],
                "max_path_bytes": 103,
                "cleanup_receipt": {
                    "path": str(cleanup_receipt),
                    "sha256": digest(cleanup_receipt),
                },
            },
            "e2e": {
                "case": "e2e/head-camera.spec.ts",
                "status": "PASSED",
                "raw_overlay_pairs": 2,
                "screenshots": screenshots,
            },
        },
    )
    return Fixture(root=root, run_root=run_root, partitions=partitions_path, paths=paths)
