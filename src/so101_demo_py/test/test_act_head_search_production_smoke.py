"""Task 14 Step 3: the production smoke journal, its sealed journal and the aggregator that reads it.

The plan's Step 3 requires a smoke that runs the **production path** - the real ``RosSearchAdapter`` and
``HeadSearchController`` over the real topic stream of the one owned stack - and leaves evidence the
``aggregate`` phase can consume: *"The smoke must prove producer -> sealed journal -> actual aggregator,
correct ``TARGET_LOCKED``, 10 Hz continuity, bounded commands, three-sample stop proof and exact runtime
identity. A mock/fixture-only result does not pass."*

Every fixture here is synthetic: no MuJoCo, no detector, no GPU and no ROS. The strongest case feeds the
produced journal into the aggregate module's **own** ``_gate_smoke``, so the shape this producer writes and
the shape that gate reads cannot drift apart unnoticed.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_timing_measurement import DEFAULT_MAX_SETTLE_S

#: the seventeen approved values, as the promoted production configuration declares them
VALUES = {
    "center_deadband_px": 3.0,
    "coarse_step_rad": 0.6560533740603397,
    "horizontal_fov_rad": 1.3121067481206794,
    "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
    "max_age_s": 0.014736005008453503,
    "max_fine_corrections": 2,
    "max_fine_total_rad": 0.6961197054865531,
    "max_skew_s": 0.010000000000001563,
    "min_area_px2": 64.0,
    "min_bbox_aspect": 0.5,
    "min_confidence": 0.25,
    "search_timeout_s": 0.7089213519976479,
    "stop_latency_s": 0.07012353999540209,
    "stop_velocity_rad_s": 0.04136050464213824,
    "submit_lead_s": 0.004,
    "tracking_iou": 0.5,
    "vertical_bounds_px": [191.699852915671, 272.6768492617673],
}

#: the frozen runtime of record, as the Step 1 reader returns it
RUNTIME = {
    "final_run": "/evidence/head-toolchain-frozen",
    "source_commit": "d8d1b5f8be37678f5bdbdaa92c322b4548f25504",
    "setup_bash_present": True,
    "production_config": "/evidence/head-toolchain-frozen/head_search_v2.json",
    "production_config_sha256": "3fb9f27646b6e314fc30fe2892f6b1c3d44b068f4c6614df8f7de3c5add2ffd9",
    "values_count": 17,
    "values_sha256": "3c787fd7ec402355d8a6e363a6bcbf814273ce30d98d47a3af2bc4400f568df2",
    "allow_cpu_fallback": False,
    "cuda_device": "cuda:0",
    "weight_path": "/evidence/models/best.pt",
    "weight_sha256_declared": "2" * 64,
    "weight_sha256_observed": "2" * 64,
}

CORRIDOR = (-6.283175307179587, 6.283175307179587)
REQUIRED_DOMAIN = (-0.17559216195018026, 0.08047101126546086)


def _frames(count: int = 6, *, period: float = 0.1, index_offset: int = 0) -> list[dict]:
    """The frames the production controller really consumed: one per declared 10 Hz frame period."""

    return [
        {
            "index": index_offset + position,
            "frame_sim_s": 12.0 + position * period,
            "received_monotonic_s": 100.0 + position * period,
            "decision_monotonic_s": 100.005 + position * period,
            "frame_age_s": 0.005,
            "source_skew_s": 0.001,
            "inference_s": 0.0053,
            "detections": 1,
            "lock_count": min(position, 3),
            "status": "TARGET_LOCKED" if position >= 2 else "CENTER_CUP",
        }
        for position in range(count)
    ]


def _commands(*targets: float) -> dict:
    return {
        "corridor_rad": list(CORRIDOR),
        "required_search_domain_rad": list(REQUIRED_DOMAIN),
        "corridor_definition": "the seal's own lock_valid_neck_rad",
        "targets": [
            {
                "index": index,
                "target_rad": value,
                "statuses": ["CENTER_CUP"],
                "ticks": 3,
                "first_frame_sim_s": 12.0 + index * 0.1,
                "kind": "start" if index == 0 else "fine_correction",
            }
            for index, value in enumerate(targets)
        ],
    }


def _stop_samples(count: int = 4, velocity: float = 0.001) -> list[dict]:
    return [
        {
            "sim_s": 13.0 + index * 0.02,
            "wall_s": 101.0 + index * 0.02,
            "velocity_rad_s": velocity,
            "position_error_rad": 0.0,
            "settled": True,
            "reached": True,
        }
        for index in range(count)
    ]


def _teardown(*, gpu_released: bool = True) -> dict:
    return {
        "previous_stack_stopped": True,
        "controller_owner_stopped": True,
        "children_exited": True,
        "graph_clear": True,
        "gpu_released": gpu_released,
        "gpu_compute_apps": [] if gpu_released else [{"pid": "9", "process_name": "python"}],
        "nodes": [],
    }


def _flight(
    *,
    terminal: str = "TARGET_LOCKED",
    frames: list[dict] | None = None,
    targets: tuple[float, ...] = (0.1, 0.23109066719589708),
    stop_samples: list[dict] | None = None,
    teardown: dict | None = None,
) -> dict:
    """One synthetic flight, in the shape ``head_search_restarts.run_anchor_restart`` returns."""

    rows = _frames() if frames is None else frames
    return {
        "anchor": "default",
        "declared_anchor": {
            "anchor": "default",
            "neck_start_rad": 0.1,
            "centre_angle_rad": 0.23109066719589708,
            "cup_point_m": [0.02, -0.28, 0.165],
        },
        "stack": {
            "nodes": ["controller_manager", "robot_state_publisher", "neck_controller"],
            "processes": [{"pid": "11", "argv": "lib/mujoco_ros2_control/ros2_control_node"}],
            "gpu_compute_apps": [],
        },
        "camera": {
            "frame_rate_hz": 10.0,
            "measured_rate_hz": 10.0059,
            "frames": 51,
            "rate_error_hz": 0.0059,
            "matches_declared": True,
            "published_frame_id": "head_camera_frame",
        },
        "clock": {"advancing": True, "delta_s": 5.029},
        "scene": {
            "body": "plastic_cup",
            "point_m": [0.02, -0.28, 0.165],
            "service": "/mujoco_ros2_control_node/set_free_joint_state",
        },
        "detector": {
            "loaded": True,
            "count": 1,
            "device": "cuda",
            "runtime_device": "cuda:0",
            "allow_cpu_fallback": False,
            "weights_sha256": RUNTIME["weight_sha256_observed"],
            "model_id": "head-search-v2",
        },
        "reservation": {"generation": 17, "armed_roles": ["neck"]},
        "adapter_liveness": {
            "executor_spinning": True,
            "adapter_image_count": 10,
            "probe_frames_last_second": 11,
        },
        "frames": rows,
        "timing": {},
        "search": {
            "terminal_status": terminal,
            "terminal": {"status": terminal, "neck_target_rad": None, "stop": True},
            "coverage_complete": True,
            "coverage": {
                "complete": True,
                "required_search_domain_rad": list(REQUIRED_DOMAIN),
                "planned_stop_count": 2,
                "commanded_stop_count": 0,
            },
            "fine_corrections": 1,
            "cumulative_fine_correction_rad": 0.13109066719589708,
            "wrong_locks": 0,
            "commands": _commands(*targets),
        },
        "lock": {"consecutive_frames": 3, "track_id": 7, "required_frames": 3},
        "stop": {
            "proven": True,
            "required_samples": 3,
            "longest_consecutive_run": 3,
            "qualifying_samples": 3,
            "sample_count": 4,
            "velocity_limit_rad_s": VALUES["stop_velocity_rad_s"],
            "samples": _stop_samples() if stop_samples is None else stop_samples,
            "held_at_rad": 0.23109066719589708,
        },
        "teardown": _teardown() if teardown is None else teardown,
        "reconstruction": {
            "stack_started": True,
            "one_mujoco_instance": True,
            "one_controller_owner": True,
        },
        "elapsed_s": 61.5,
        "started_at_utc": "2026-10-02T00:00:00Z",
        "finished_at_utc": "2026-10-02T00:01:01Z",
    }


def _ownership(run_root) -> dict:
    return {
        "operation": "QUALIFICATION_OWNERSHIP_CHECK",
        "status": "EXCLUSIVE_OWNERSHIP_OK",
        "refusals": [],
        "planned_run_root": str(run_root),
        "expected_runtime": {
            key: RUNTIME[key]
            for key in ("source_commit", "production_config_sha256", "values_sha256")
        },
    }


def _ownership_receipt(tmp_path, run_root) -> Path:
    path = tmp_path / "exclusive-ownership.json"
    path.write_text(json.dumps(_ownership(run_root)), encoding="utf-8")
    return path


def _seal() -> dict:
    return {
        "seal_sha256": "7d963fdc" + "0" * 56,
        "horizontal_fov_rad": 1.3121067481206794,
        "coarse_step_candidate_rad": 0.3,
        "lock_valid_neck_rad": list(CORRIDOR),
        "required_search_domain_rad": list(REQUIRED_DOMAIN),
        "in_frame_matrix": {
            "default": {"neck_start_rad": 0.1, "centre_angle_rad": 0.23109066719589708},
            "left": {"neck_start_rad": 0.0, "centre_angle_rad": -0.0587558227157227},
            "forward": {"neck_start_rad": 0.0, "centre_angle_rad": 0.18822150530477078},
        },
        "workspace_matrix": {
            "key_samples": [
                {"kind": "anchor", "anchor": "default", "point_m": [0.02, -0.28, 0.165]},
                {"kind": "anchor", "anchor": "left", "point_m": [-0.08, -0.28, 0.165]},
                {"kind": "anchor", "anchor": "forward", "point_m": [0.02, -0.36, 0.165]},
            ]
        },
    }


def _produce(tmp_path, *, flight=None, run_root=None, **overrides):
    """Run the producer with a synthetic flight and return ``(result, journal, run_root)``."""

    from so101_demo.act import head_search_production_smoke as module

    root = Path(run_root) if run_root is not None else tmp_path / "production-smoke-run"
    producer = {
        "entry": "so101_head_search_smoke",
        "command": "so101_head_search_smoke --run-root " + str(root),
        "argv_sha256": "a" * 64,
    }
    kwargs = {
        "run_root": root,
        "ownership_receipt": _ownership_receipt(tmp_path, root),
        "runtime": RUNTIME,
        "seal": _seal(),
        "workdir": tmp_path / "work",
        "values": VALUES,
        "run_flight": lambda **call: _flight() if flight is None else flight,
        "producer": producer,
        "approved_bundle_sha256": "e21899c2" + "0" * 56,
    }
    kwargs.update(overrides)
    result = module.write_head_search_production_smoke(**kwargs)
    journal = json.loads((root / module.JOURNAL_ARTIFACT).read_text(encoding="utf-8"))
    return result, journal, root


# --- the 10 Hz cadence -------------------------------------------------------------------------------


def test_the_cadence_check_accepts_a_sequence_the_declared_contract_produces() -> None:
    from so101_demo.act import head_search_production_smoke as module

    cadence = module.smoke_cadence(_frames(6))

    assert cadence["continuous"] is True
    assert cadence["duplicate_count"] == 0
    assert cadence["backward_count"] == 0
    assert cadence["undeclared_gap_count"] == 0
    assert cadence["frame_rate_hz"] == 10.0
    assert cadence["frame_period_s"] == 0.1
    assert cadence["achieved_rate_hz"] == pytest.approx(10.0)
    assert cadence["definition"]


def test_the_cadence_check_names_a_duplicate_a_backward_stamp_and_an_undeclared_gap() -> None:
    from so101_demo.act import head_search_production_smoke as module

    duplicate = _frames(6)
    duplicate[3]["frame_sim_s"] = duplicate[2]["frame_sim_s"]
    cadence = module.smoke_cadence(duplicate)
    assert cadence["duplicate_count"] == 1 and cadence["continuous"] is False

    backward = _frames(6)
    backward[4]["frame_sim_s"] = backward[3]["frame_sim_s"] - 0.2
    assert module.smoke_cadence(backward)["backward_count"] == 1

    # a gap no declared settle budget plus one frame period can produce: the loop stopped consuming
    gap = _frames(6)
    for position in range(3, 6):
        gap[position]["frame_sim_s"] = 12.0 + (position + 60) * 0.1
    cadence = module.smoke_cadence(gap)
    assert cadence["undeclared_gap_count"] == 1 and cadence["continuous"] is False

    # a frame faster than the declared period is the same violation the design refuses
    fast = _frames(6, period=0.05)
    cadence = module.smoke_cadence(fast)
    assert cadence["too_fast_count"] == 5 and cadence["continuous"] is False


def test_the_cadence_check_uses_the_declared_settle_budget_as_its_upper_bound() -> None:
    from so101_demo.act import head_search_production_smoke as module

    # one frame period plus the measured settle budget is still a declared cadence; more is not
    frames = _frames(3)
    frames[1]["frame_sim_s"] = frames[0]["frame_sim_s"] + DEFAULT_MAX_SETTLE_S + 0.1
    frames[2]["frame_sim_s"] = frames[1]["frame_sim_s"] + DEFAULT_MAX_SETTLE_S + 0.1 + 0.05
    cadence = module.smoke_cadence(frames)
    assert cadence["undeclared_gap_count"] == 1


# --- bounded commands --------------------------------------------------------------------------------


def test_the_command_check_counts_the_targets_outside_the_declared_corridor() -> None:
    from so101_demo.act import head_search_production_smoke as module

    bounded = module.smoke_commands(_commands(0.1, 0.23109066719589708))
    assert bounded["bounded"] is True
    assert bounded["outside_corridor_count"] == 0
    assert bounded["targets_rad"] == [0.1, 0.23109066719589708]
    assert bounded["max_abs_neck_rad"] == pytest.approx(0.23109066719589708)
    # the anchor start is outside the required search domain by the seal's own declaration (HS-316)
    assert bounded["outside_required_domain_count"] == 2

    outside = module.smoke_commands(_commands(0.1, 9.0))
    assert outside["bounded"] is False
    assert outside["outside_corridor_count"] == 1

    # a corridor with no commanded target at all is not a proof
    assert (
        module.smoke_commands({"corridor_rad": list(CORRIDOR), "targets": []})["bounded"] is False
    )


# --- the terminal classification (the scenario module's own rule) -------------------------------------


def test_the_terminal_classification_reuses_the_scenario_modules_own_rule() -> None:
    from so101_demo.act import head_search_production_smoke as module

    locked = module.classify_terminal("TARGET_LOCKED", coverage={"complete": True})
    assert locked["outcome"] == "PASSED" and locked["outcome_code"] is None

    ambiguous = module.classify_terminal("TARGET_AMBIGUOUS", coverage={"complete": True})
    assert ambiguous["outcome"] == "FAILED"
    assert ambiguous["outcome_code"] == "CAL_SCENARIO_TARGET_AMBIGUOUS"

    not_found = module.classify_terminal("TARGET_NOT_FOUND", coverage={"complete": True})
    assert not_found["outcome"] == "FAILED"
    assert not_found["outcome_code"] == "CAL_SCENARIO_CUP_NOT_FOUND"

    # the controller's own timeout is neither a terminal the class declares nor an outcome it records
    timeout = module.classify_terminal("SEARCH_TIMEOUT", coverage={"complete": True})
    assert timeout["outcome"] == "REFUSED"
    assert timeout["outcome_code"] == "CAL_SCENARIO_NO_VERDICT"


def test_the_terminal_classification_refuses_a_class_the_plan_does_not_declare() -> None:
    from so101_demo.act import head_search_production_smoke as module

    with pytest.raises(CalibrationInputsRefused) as refusal:
        module.classify_terminal(
            "TARGET_LOCKED", condition_class="made_up", coverage={"complete": True}
        )
    assert module.SMOKE_CLASS_UNDECLARED in str(refusal.value)


# --- producer -> sealed journal -> aggregator ---------------------------------------------------------


def test_the_producer_writes_a_sealed_journal_the_aggregator_can_re_read(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    result, journal, root = _produce(tmp_path)
    sealed_path = root / module.SEALED_ARTIFACT
    sealed = json.loads(sealed_path.read_text(encoding="utf-8"))

    assert sealed["kind"] == module.SEALED_KIND
    assert sealed["anchor"] == "default"
    assert sealed["condition_class"] == "nominal"
    assert sealed["frames"] == _flight()["frames"]
    assert sealed["sealed"]["body_sha256"]
    # the seal is the document's own body digest, so a hand-edited journal cannot pass it
    body = {key: value for key, value in sealed.items() if key != "sealed"}
    from so101_demo.perception_benchmark.contracts import canonical_sha256

    assert sealed["sealed"]["body_sha256"] == canonical_sha256(body)

    assert journal["journal"]["path"] == str(sealed_path)
    assert journal["journal"]["sha256"] == module._digest(sealed_path)
    assert journal["aggregator"]["journal_sha256"] == journal["journal"]["sha256"]
    assert journal["aggregator"]["status"] == "SUCCEEDED"
    assert journal["status"] == "PASS"
    assert result["journal"] == str(root / module.JOURNAL_ARTIFACT)
    assert (root / module.RECEIPT_ARTIFACT).is_file()
    assert (root / "default" / "stdout.log").is_file()
    assert (root / "default" / "stderr.log").is_file()


def test_the_aggregator_re_derives_every_gate_from_the_sealed_journal_on_disk(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    result, journal, root = _produce(tmp_path)
    # re-running the aggregator over the sealed journal must reproduce the same readings
    again = module.aggregate_production_smoke(
        root / module.SEALED_ARTIFACT, run_root=root, producer=journal["producer"]
    )
    assert again["terminal_status"] == journal["terminal_status"]
    assert again["frame_cadence"] == journal["frame_cadence"]
    assert again["commands"] == journal["commands"]
    assert again["stop_proof"]["proven"] is True
    assert again["stop_proof"]["qualifying_samples"] == journal["stop_proof"]["qualifying_samples"]
    assert again["sha256"] == journal["sha256"]
    assert result["gates"] == journal["gates"]


def test_the_aggregator_refuses_a_sealed_journal_whose_body_was_edited(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    _, _, root = _produce(tmp_path)
    sealed_path = root / module.SEALED_ARTIFACT
    sealed = json.loads(sealed_path.read_text(encoding="utf-8"))
    sealed["terminal_status"] = "SEARCH_TIMEOUT"
    sealed_path.write_text(json.dumps(sealed, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with pytest.raises(CalibrationInputsRefused) as refusal:
        module.aggregate_production_smoke(sealed_path, run_root=root)
    assert module.SMOKE_SEAL_MISMATCH in str(refusal.value)


def test_the_aggregator_refuses_a_sealed_journal_that_is_not_there(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    with pytest.raises(CalibrationInputsRefused) as refusal:
        module.aggregate_production_smoke(tmp_path / "absent.json", run_root=tmp_path)
    assert module.SMOKE_JOURNAL_UNREADABLE in str(refusal.value)


# --- the strongest case: the aggregate module's own gate -----------------------------------------------


def _gate_smoke(root):
    """The aggregate phase's own ``production_smoke`` gate, fed the produced journal only."""

    from so101_demo.act import head_search_aggregate as aggregate

    reasons = aggregate._Reasons()
    readings = aggregate._gate_smoke(
        {"production_smoke_root": str(root)},
        {
            "runtime": {
                key: RUNTIME.get(key)
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
    return readings, reasons


def test_the_produced_journal_satisfies_the_aggregates_own_production_smoke_gate(tmp_path) -> None:
    _, journal, root = _produce(tmp_path)

    readings, reasons = _gate_smoke(root)

    assert reasons.missing == []
    assert reasons.violations == []
    assert readings["sealed_journal"] == journal["journal"]["path"]
    assert readings["sealed_journal_sha256"] == journal["journal"]["sha256"]


def test_a_planning_coverage_proof_is_not_a_smoke_journal(tmp_path) -> None:
    """The HS-315/HS-317 defect restated: the old coverage proof must not satisfy this gate."""

    root = tmp_path / "head-search-smoke-old"
    root.mkdir()
    (root / "coverage-proof.json").write_text(
        json.dumps({"coverage_complete": True, "status": "OK"}), encoding="utf-8"
    )

    _, reasons = _gate_smoke(root)

    assert [item["gate"] for item in reasons.missing] == ["production_smoke"]
    assert reasons.missing[0]["code"] == "QUAL_AGGREGATE_SMOKE_MISSING"
    assert "coverage-proof.json" in reasons.missing[0]["detail"]


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda doc: doc.update(kind="something_else"), "QUAL_AGGREGATE_SMOKE_INCOMPLETE"),
        (lambda doc: doc.update(phase="scenarios"), "QUAL_AGGREGATE_SMOKE_INCOMPLETE"),
        (lambda doc: doc["producer"].update(stack_owned=False), "QUAL_AGGREGATE_SMOKE_INCOMPLETE"),
        (
            lambda doc: doc.update(terminal_status="SEARCH_TIMEOUT"),
            "QUAL_AGGREGATE_SMOKE_INCOMPLETE",
        ),
        (lambda doc: doc.update(zero_wrong_locks=False), "QUAL_AGGREGATE_SMOKE_INCOMPLETE"),
        (
            lambda doc: doc["frame_cadence"].update(duplicate_count=2, continuous=False),
            "QUAL_AGGREGATE_SMOKE_INCOMPLETE",
        ),
        (
            lambda doc: doc["commands"].update(bounded=False, outside_corridor_count=1),
            "QUAL_AGGREGATE_SMOKE_INCOMPLETE",
        ),
        (
            lambda doc: doc["stop_proof"].update(proven=False, qualifying_samples=2),
            "QUAL_AGGREGATE_STOP_PROOF_UNPROVEN",
        ),
        (
            lambda doc: doc["detector"].update(device="cpu", allow_cpu_fallback=True),
            "QUAL_AGGREGATE_SMOKE_INCOMPLETE",
        ),
        (
            lambda doc: doc["runtime"].update(source_commit="f" * 40),
            "QUAL_AGGREGATE_SMOKE_INCOMPLETE",
        ),
        (
            lambda doc: doc["journal"].update(sha256="f" * 64),
            "QUAL_AGGREGATE_DIGEST_MISMATCH",
        ),
    ],
)
def test_the_gate_names_the_item_a_mutated_journal_lost(tmp_path, mutate, expected) -> None:
    _, _, root = _produce(tmp_path)
    from so101_demo.act import head_search_production_smoke as module

    path = root / module.JOURNAL_ARTIFACT
    document = json.loads(path.read_text(encoding="utf-8"))
    mutate(document)
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    _, reasons = _gate_smoke(root)

    assert [item["code"] for item in reasons.missing + reasons.violations] == [expected]


def test_the_shape_check_names_every_field_the_gate_reads(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    _, journal, _ = _produce(tmp_path)
    assert module.validate_smoke_journal(journal) == []

    problems = module.validate_smoke_journal({"kind": module.KIND})
    assert problems and all(isinstance(problem, str) for problem in problems)
    assert any("phase" in problem for problem in problems)


# --- the refusals ------------------------------------------------------------------------------------


def test_the_producer_refuses_a_run_root_that_already_exists(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    existing = tmp_path / "already-there"
    existing.mkdir()
    with pytest.raises(CalibrationInputsRefused) as refusal:
        _produce(tmp_path, run_root=existing)
    assert module.SMOKE_RUN_ROOT_EXISTS in str(refusal.value)


def test_the_producer_refuses_an_ownership_receipt_that_guards_another_root(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    root = tmp_path / "production-smoke-run"
    receipt = tmp_path / "other-ownership.json"
    receipt.write_text(json.dumps(_ownership(tmp_path / "some-other-root")), encoding="utf-8")
    with pytest.raises(CalibrationInputsRefused) as refusal:
        _produce(tmp_path, run_root=root, ownership_receipt=receipt)
    assert module.SMOKE_OWNERSHIP_MISMATCH in str(refusal.value)
    assert not root.exists()


def test_the_producer_refuses_a_runtime_that_is_not_the_cuda_only_runtime_of_record(
    tmp_path,
) -> None:
    from so101_demo.act import head_search_production_smoke as module

    for key, value in (("allow_cpu_fallback", True), ("cuda_device", "cpu"), ("values_count", 16)):
        runtime = dict(RUNTIME)
        runtime[key] = value
        with pytest.raises(CalibrationInputsRefused) as refusal:
            _produce(tmp_path, run_root=tmp_path / f"root-{key}", runtime=runtime)
        assert module.SMOKE_RUNTIME_UNVERIFIED in str(refusal.value)


def test_the_producer_refuses_a_flight_that_does_not_lock_the_cup(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    _, journal, root = _produce(tmp_path, flight=_flight(terminal="TARGET_AMBIGUOUS"))

    assert journal["status"] == "REFUSED"
    assert module.SMOKE_LOCK_UNPROVEN in [item["code"] for item in journal["refusals"]]
    assert journal["gates"]["search"] == "FAIL"
    assert journal["outcome_code"] == "CAL_SCENARIO_TARGET_AMBIGUOUS"
    # the sealed journal and the journal are both on disk: the run is readable, not silent
    assert (root / module.SEALED_ARTIFACT).is_file()
    assert (root / module.JOURNAL_ARTIFACT).is_file()


def test_the_producer_refuses_a_cadence_outside_the_declared_contract(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    frames = _frames(6)
    frames[4]["frame_sim_s"] = frames[3]["frame_sim_s"]
    _, journal, _ = _produce(tmp_path, flight=_flight(frames=frames))

    assert journal["status"] == "REFUSED"
    assert module.SMOKE_CADENCE_BROKEN in [item["code"] for item in journal["refusals"]]
    assert journal["frame_cadence"]["continuous"] is False
    assert journal["frame_cadence"]["duplicate_count"] == 1


def test_the_producer_refuses_commands_outside_the_declared_corridor(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    _, journal, _ = _produce(tmp_path, flight=_flight(targets=(0.1, 9.0)))

    assert journal["status"] == "REFUSED"
    assert module.SMOKE_COMMANDS_UNBOUNDED in [item["code"] for item in journal["refusals"]]
    assert journal["commands"]["outside_corridor_count"] == 1


def test_the_producer_refuses_an_unproven_stop(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    loud = _stop_samples(4, velocity=1.0)
    _, journal, _ = _produce(tmp_path, flight=_flight(stop_samples=loud))

    assert journal["status"] == "REFUSED"
    assert module.SMOKE_STOP_UNPROVEN in [item["code"] for item in journal["refusals"]]
    assert journal["stop_proof"]["proven"] is False


def test_the_producer_refuses_a_gpu_that_was_not_released(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    _, journal, _ = _produce(tmp_path, flight=_flight(teardown=_teardown(gpu_released=False)))

    assert journal["status"] == "REFUSED"
    codes = [item["code"] for item in journal["refusals"]]
    assert module.SMOKE_GPU_NOT_RELEASED in codes
    assert journal["gates"]["gpu"] == "FAIL"
    # the four teardown facts are separately proven and separately named
    assert journal["gates"]["teardown"] == "PASS"
    assert module.SMOKE_TEARDOWN_UNPROVEN not in codes


@pytest.mark.parametrize(
    "field",
    ["previous_stack_stopped", "controller_owner_stopped", "children_exited", "graph_clear"],
)
def test_the_producer_refuses_a_teardown_that_did_not_prove_one_fact(tmp_path, field) -> None:
    from so101_demo.act import head_search_production_smoke as module

    teardown = _teardown()
    teardown[field] = False
    _, journal, _ = _produce(tmp_path, flight=_flight(teardown=teardown))

    assert journal["status"] == "REFUSED"
    assert journal["gates"]["teardown"] == "FAIL"
    assert module.SMOKE_TEARDOWN_UNPROVEN in [item["code"] for item in journal["refusals"]]


def test_the_producer_leaves_a_named_refusal_when_the_flight_itself_refuses(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    def refuse(**call):
        raise CalibrationInputsRefused(
            "RESTART_STACK_START_FAILED", "the stack published no node within 60 s"
        )

    _, journal, root = _produce(tmp_path, flight=None, run_flight=refuse)

    assert journal["status"] == "REFUSED"
    codes = [item["code"] for item in journal["refusals"]]
    assert module.SMOKE_STACK_START_FAILED in codes
    assert "RESTART_STACK_START_FAILED" in json.dumps(journal["refusals"])
    assert (root / module.JOURNAL_ARTIFACT).is_file()


def test_the_producer_refuses_a_condition_class_the_plan_does_not_declare(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    with pytest.raises(CalibrationInputsRefused) as refusal:
        _produce(tmp_path, condition_class="made_up")
    assert module.SMOKE_CLASS_UNDECLARED in str(refusal.value)


def test_the_producer_refuses_a_cup_that_was_never_placed(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    flight = _flight()
    flight["scene"] = {"body": "plastic_cup", "point_m": None, "service": "/service"}
    _, journal, _ = _produce(tmp_path, flight=flight)

    assert journal["status"] == "REFUSED"
    assert module.SMOKE_CUP_NOT_PLACED in [item["code"] for item in journal["refusals"]]


def test_the_seal_the_producer_reads_declares_the_anchors_it_may_run(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    seal = _seal()
    seal["in_frame_matrix"].pop("left")
    with pytest.raises(CalibrationInputsRefused):
        _produce(tmp_path, seal=seal, anchor="left")
    assert module.ANCHORS == ("default", "left", "forward")


def test_the_journal_carries_the_provenance_step_3_asks_for(tmp_path) -> None:
    _, journal, _ = _produce(tmp_path)

    provenance = journal["provenance"]
    assert provenance["final_run"] == RUNTIME["final_run"]
    assert provenance["source_commit"] == RUNTIME["source_commit"]
    assert provenance["production_config_sha256"] == RUNTIME["production_config_sha256"]
    assert provenance["weight_sha256"] == RUNTIME["weight_sha256_observed"]
    assert provenance["nodes"] == ["controller_manager", "robot_state_publisher", "neck_controller"]
    assert provenance["measured_rate_hz"] == pytest.approx(10.0059)
    assert provenance["elapsed_s"] == pytest.approx(61.5)
    assert provenance["producer_elapsed_s"] is not None
    assert provenance["teardown_proof"]["graph_clear"] is True


def test_the_coverage_proof_stays_available_beside_the_journal(tmp_path) -> None:
    """Requirement (b): the old coverage proof is still produced; it is just not the success condition."""

    from so101_demo.act import head_search_production_smoke as module

    _, journal, root = _produce(tmp_path)
    proof = json.loads((root / module.COVERAGE_PROOF_ARTIFACT).read_text(encoding="utf-8"))

    assert proof["coverage_complete"] is True
    assert proof["anchor"] == "default"
    assert proof["coarse_step_rad"] == 0.3
    assert (root / module.PLAN_ARTIFACT.format(anchor="default")).is_file()
    assert journal["coverage_proof"]["document"] == proof
    assert journal["coverage_proof"]["sha256"] == module._digest(
        root / module.COVERAGE_PROOF_ARTIFACT
    )
    assert "not this phase's success condition" in journal["coverage_proof"]["role"]


def test_the_producer_refuses_a_seal_that_declares_no_coarse_step(tmp_path) -> None:
    from so101_demo.act import head_search_production_smoke as module

    seal = _seal()
    seal.pop("coarse_step_candidate_rad")
    with pytest.raises(CalibrationInputsRefused) as refusal:
        _produce(tmp_path, seal=seal)
    assert module.SMOKE_COVERAGE_UNPROVEN in str(refusal.value)


def test_legacy_flight_refuses_before_calling_restart(tmp_path, monkeypatch) -> None:
    from so101_demo.act import head_search_production_smoke as module
    from so101_demo.act import head_search_restarts as restarts

    def forbidden_restart(**kwargs):
        pytest.fail('legacy smoke attempted to enter restart execution')

    monkeypatch.setattr(restarts, 'run_anchor_restart', forbidden_restart)
    with pytest.raises(module.SmokeRefused, match='HEAD_LEGACY_EXECUTION_REMOVED'):
        module.run_smoke_flight(anchor='default', root=tmp_path / 'unclaimed',
                               declared={'anchor': 'default'})
    assert not (tmp_path / 'unclaimed').exists()


@pytest.mark.parametrize('business_return_code', [0, 1])
def test_development_smoke_uses_the_formal_provider_and_one_composition(
        tmp_path, monkeypatch, business_return_code):
    from test_head_execution_run_cli import build_inputs, fake_provider
    from so101_demo.cli import head_execution_run
    from so101_demo.act.head_search_production_smoke import run_smoke_flight
    inputs, _ = build_inputs(tmp_path)
    calls = []
    provider = fake_provider(monkeypatch, calls, outcome=business_return_code)
    monkeypatch.setattr(head_execution_run, 'resolve_provider', lambda supplied=None: provider)
    result = run_smoke_flight(execution_inputs=inputs.document_path)
    assert result['operation'] == 'HEAD_FILE_STAGE1_DEVELOPMENT'
    assert result['qualification_status'] == 'NOT_QUALIFIED'
    assert result['business_return_code'] == business_return_code
    assert [name for name, _ in calls] == ['provide']
    assert result['run_root'] == str(inputs.run_root)
    completion = json.loads((inputs.run_root/'completion.json').read_text())
    assert completion['execution'] == ('SUCCEEDED' if business_return_code == 0 else 'FAILED')
    assert (inputs.run_root/'seal.json').is_file()


def test_development_smoke_refuses_mixed_qualification_arguments_before_provider(tmp_path, monkeypatch):
    from so101_demo.cli import head_execution_run
    from so101_demo.act.head_search_production_smoke import run_smoke_flight, SmokeRefused
    calls = []
    monkeypatch.setattr(head_execution_run, 'resolve_provider', lambda supplied=None: calls.append('resolve'))
    with pytest.raises(SmokeRefused, match='SMOKE_EXECUTION_INPUTS_MIXED'):
        run_smoke_flight(execution_inputs=tmp_path/'inputs.json', anchor='default')
    assert calls == []
