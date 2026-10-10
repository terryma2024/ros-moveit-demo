"""The during-qualification readback: the observation shape, the mismatch, and every refusal.

Nothing here starts a stack, opens a GPU or publishes a ROS node: the live observer is injected, and the
production components the observation shape is exercised against are the installed ones constructed in
process. The point of the file is the contract the aggregate's `approved_values_readback` gate consumes
and the honesty of the producer - a value that was not observed is never the approved number restated, and
a value that was observed differently is a hard failure.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from head_search_qualification_fixtures import (
    FIXTURE_CAMERA_MEASUREMENTS,
    FIXTURE_VALUES,
    build_fixture,
)
from so101_demo.act import head_search_aggregate as aggregate
from so101_demo.act import head_search_qualification_readback as readback
from so101_demo.act.head_search_binding import _CAMERA_MEASURED, _MEASURED
from so101_demo.act.head_search_calibration_inputs import CalibrationInputsRefused
from so101_demo.act.head_search_ownership import read_runtime_identity
from so101_demo.act.head_search_timing_measurement import controller_config
from so101_demo.cli.head_search_calibration import (
    HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE,
    main,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

#: a promoted value set the installed controller can actually be constructed with, so the observation of
#: the seventeen runs through the real production component rather than a stand-in
PROMOTED_VALUES = {
    "horizontal_fov_rad": 1.3121067481206794,
    "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
    "coarse_step_rad": 0.6560533740603397,
    "search_timeout_s": 0.7089213519976479,
    "min_confidence": 0.25,
    "tracking_iou": 0.5,
    "min_bbox_aspect": 0.5,
    "min_area_px2": 64.0,
    "center_deadband_px": 3.0,
    "vertical_bounds_px": [191.699852915671, 272.6768492617673],
    "max_fine_corrections": 2,
    "max_fine_total_rad": 0.6961197054865531,
    "max_age_s": 0.014736005008453503,
    "max_skew_s": 0.010000000000001563,
    "submit_lead_s": 0.004,
    "stop_velocity_rad_s": 0.04136050464213824,
    "stop_latency_s": 0.07012353999540209,
}

#: the four camera measurements as the approved calibration recorded them
PROMOTED_CAMERA = {
    "head_intrinsics_px": [413.5, 413.5, 320.0, 240.0],
    "head_translation_m": [0.05, 0.0, 0.30],
    "head_rpy_rad": [0.0, 0.35, 0.0],
    "yaw_zero_bearing_rad": 0.12,
}

SEAL = {
    "horizontal_fov_rad": PROMOTED_VALUES["horizontal_fov_rad"],
    "lock_valid_neck_rad": list(PROMOTED_VALUES["lock_valid_neck_rad"]),
    "required_search_domain_rad": [-0.29145679447786704, 0.540419500270584],
    "in_frame_matrix": {"default": {"neck_start_rad": 0.1}},
}


class _Detector:
    """A stand-in for the loaded production detector: only the two values its own code applies."""

    def __init__(self, *, tracking_iou=0.5, min_bbox_aspect=0.5):
        self.tracking_iou = tracking_iou
        self.min_bbox_aspect = min_bbox_aspect


def _configuration(values=None) -> dict:
    return controller_config(
        production_search_config={
            "values": dict(values or PROMOTED_VALUES),
            "motion": {"goal_tolerance_rad": 0.05, "settle_velocity_rad_s": 0.05},
            "camera": {"frame_id": "head_camera_frame", "ray_origin_frame_id": "head_camera_frame"},
        },
        geometry_seal=SEAL,
        anchor="default",
        attempt_id="readback-attempt",
        session_id="readback-session",
    )


def _observed(values=None, *, detector=None) -> dict:
    return readback.observe_qualification_values(
        values=dict(values or PROMOTED_VALUES),
        configuration=_configuration(values),
        detector=detector or _Detector(),
    )


def _runtime(tmp_path: Path, values=None) -> dict:
    """A frozen runtime of record on disk, so the identity is read the way the producer reads it."""

    root = tmp_path / "final-run"
    (root / "install/so101_demo_py/share/so101_demo_py/config/mujoco/act").mkdir(parents=True)
    (root / "source-commit.txt").write_text("a" * 40 + "\n", encoding="utf-8")
    (root / "install/setup.bash").write_text("# overlay\n", encoding="utf-8")
    weights = root / "weights/best.pt"
    weights.parent.mkdir(parents=True, exist_ok=True)
    weights.write_bytes(b"weights\n")
    config = (
        root / "install/so101_demo_py/share/so101_demo_py/config/mujoco/act/head_search_v2.json"
    )
    config.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runtime_id": "head-search-v2",
                "weight_path": str(weights),
                "allow_cpu_fallback": False,
                "cuda_device": "cuda:0",
                "values": dict(values or PROMOTED_VALUES),
            }
        ),
        encoding="utf-8",
    )
    runtime = read_runtime_identity(root, production_config=config)
    runtime["weight_sha256"] = runtime["weight_sha256_declared"]
    return runtime


def _bundle(tmp_path: Path, values=None, *, digest_values=None) -> Path:
    path = tmp_path / "approved-bundle.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "kind": "head_search_calibration_bundle",
                "parameter_names": list(_MEASURED),
                "parameters": {
                    name: {"value": value} for name, value in (values or PROMOTED_VALUES).items()
                },
                "runtime_identity": {"detector_weights_sha256": "b" * 64},
            }
        ),
        encoding="utf-8",
    )
    return path


def _receipt(tmp_path: Path, *, guard, status="EXCLUSIVE_OWNERSHIP_OK", refusals=()) -> Path:
    path = tmp_path / "ownership/exclusive-ownership.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "operation": "QUALIFICATION_OWNERSHIP_CHECK",
                "status": status,
                "refusals": list(refusals),
                "planned_run_root": str(guard),
            }
        ),
        encoding="utf-8",
    )
    return path


def _live_camera(**overrides) -> dict:
    live = {
        name: {
            "value": value,
            "observation": readback.RUNNING_STACK_OBSERVATION,
            "component": "the running camera plugin",
            "source": readback.CAMERA_SOURCES[name],
        }
        for name, value in PROMOTED_CAMERA.items()
    }
    live.update(overrides)
    return live


def _document(tmp_path: Path, *, values=None, detector=None, live=None, reference=None) -> dict:
    runtime = _runtime(tmp_path, values)
    return readback.readback_document(
        run_root=tmp_path / "qualification-run",
        evidence_root=tmp_path / "evidence",
        runtime=runtime,
        approved={"values_sha256": canonical_sha256(dict(values or PROMOTED_VALUES))},
        observations=_observed(values, detector=detector),
        camera_measurements=readback.camera_measurement_records(
            live=_live_camera() if live is None else live, reference=reference
        ),
        detector={
            "count": 1,
            "device": "cuda",
            "allow_cpu_fallback": False,
            "weights_sha256": runtime["weight_sha256_declared"],
        },
        ownership={"path": "receipt.json", "sha256": "c" * 64},
        approved_bundle_path=_bundle(tmp_path, values),
        production_config_path=runtime["production_config"],
        elapsed_s=3.5,
        taken_at_utc="2026-10-02T08:00:00Z",
    )


# --- the observation shape -----------------------------------------------------------------------------


def test_the_seventeen_values_are_observed_off_the_components_that_consume_them(
    tmp_path: Path,
) -> None:
    records = _observed()

    assert list(records) == list(_MEASURED)
    for name, record in records.items():
        assert record["value"] == PROMOTED_VALUES[name], name
        assert record["approved_value"] == PROMOTED_VALUES[name], name
        assert record["observed_value"] == PROMOTED_VALUES[name], name
        assert record["matches_approved"] is True, name
        assert record["component"], name
        assert record["source"], name
        assert record["configuration_sha256"], name
    # the components are the production ones, named as the bundle's own owners name them
    assert (
        records["coarse_step_rad"]["source"]
        == "HeadSearchController(...).config['coarse_step_rad']"
    )
    assert records["horizontal_fov_rad"]["source"] == (
        "HeadSearchController(...).plan.horizontal_fov_rad"
    )
    assert records["lock_valid_neck_rad"]["source"] == (
        "HeadSearchController(...).plan.safe_interval_rad"
    )
    assert records["tracking_iou"]["observation"] == readback.LOADED_DETECTOR_OBSERVATION
    assert records["min_bbox_aspect"]["component"].endswith("_Detector")
    # the eleven measured ones are the readback ledger HS-312 wired, with its behavioural probes
    assert records["max_age_s"]["observation"] == "constructed_production_component"
    assert records["max_age_s"]["behavioural"]["probe"] == "frame_freshness"
    assert records["search_timeout_s"]["behavioural"]["probe"] == "search_deadline"
    assert records["max_skew_s"]["behavioural"]["probe"] == "frame_skew"
    assert records["submit_lead_s"]["source"] == "neck_port.lead"
    assert records["stop_latency_s"]["source"] == "neck_port.stop_timeout"
    assert records["stop_velocity_rad_s"]["source"] == "stop_criterion.stop_velocity"
    # the freshness bound is consumed by three components, and every one of them was queried
    assert records["max_age_s"]["also_observed"] == {
        "neck_port.max_age": PROMOTED_VALUES["max_age_s"],
        "stop_criterion.max_age": PROMOTED_VALUES["max_age_s"],
    }


def test_the_document_is_the_one_the_gate_reads(tmp_path: Path) -> None:
    document = _document(tmp_path)

    assert document["kind"] == aggregate.READBACK_KIND
    assert document["run_root"] == str(tmp_path / "qualification-run")
    assert document["values_count"] == 17
    assert document["values_sha256"] == canonical_sha256(dict(PROMOTED_VALUES))
    assert set(document["values"]) == set(_MEASURED)
    assert set(document["camera_measurements"]) == set(_CAMERA_MEASURED)
    assert document["detector"]["count"] == 1
    assert document["detector"]["device"] == "cuda"
    assert document["detector"]["allow_cpu_fallback"] is False
    assert document["weight_sha256_declared"] == document["detector"]["weights_sha256"]
    for name in _MEASURED:
        provenance = document["values"][name]["provenance"]
        assert provenance["run_root"] == str(tmp_path / "qualification-run")
        assert provenance["source_commit"]
        assert provenance["production_config_sha256"]
        assert provenance["values_sha256"] == document["values_sha256"]
        assert provenance["weight_sha256"] == document["weight_sha256_declared"]
        assert provenance["elapsed_s"] == 3.5


def test_the_gate_holds_against_the_readback_the_real_producer_writes(tmp_path: Path) -> None:
    """The end-to-end contract: the aggregate's own gate accepts the document, with no reasons at all."""

    fixture = build_fixture(tmp_path / "fixture")
    evidence = tmp_path / "readback-evidence"
    runtime = read_runtime_identity(fixture.paths["final_run"])
    result = readback.write_head_search_qualification_readback(
        run_root=fixture.run_root,
        evidence_root=evidence,
        ownership_receipt=fixture.paths["ownership_receipt"],
        runtime=runtime,
        approved_bundle=json.loads(Path(fixture.paths["approved_bundle"]).read_text()),
        production_config=json.loads(Path(fixture.paths["production_config"]).read_text()),
        observe=_fake_observer(FIXTURE_VALUES, runtime),
        approved_bundle_path=fixture.paths["approved_bundle"],
        production_config_path=fixture.paths["production_config"],
        camera_reference=FIXTURE_CAMERA_MEASUREMENTS,
    )
    assert result["status"] == readback.PASS
    document = json.loads(Path(result["document_path"]).read_text(encoding="utf-8"))
    assert document["run_root"] == str(fixture.run_root)
    assert (evidence / readback.TEARDOWN_ARTIFACT).is_file()

    reasons = aggregate._Reasons()
    readings = aggregate._gate_values(
        {
            "runtime_readback": result["document_path"],
            "approved_bundle": str(fixture.paths["approved_bundle"]),
        },
        fixture.run_root,
        {"runtime": runtime},
        reasons,
    )
    assert reasons.both() == []
    assert readings["values_count"] == 17
    assert readings["sha256"]


def test_a_camera_measurement_the_stack_did_not_publish_is_recorded_not_invented() -> None:
    records = readback.camera_measurement_records(
        live=_live_camera(
            head_rpy_rad={
                "value": None,
                "observation": readback.NOT_OBSERVABLE,
                "reason": "no base -> head_camera_frame transform: LookupException: no frames",
            }
        ),
        reference=PROMOTED_CAMERA,
    )

    assert records["head_rpy_rad"]["value"] is None
    assert records["head_rpy_rad"]["observation"] == readback.NOT_OBSERVABLE
    assert records["head_rpy_rad"]["matches_approved"] is None
    assert "LookupException" in records["head_rpy_rad"]["reason"]
    assert records["head_intrinsics_px"]["value"] == PROMOTED_CAMERA["head_intrinsics_px"]
    assert records["head_intrinsics_px"]["matches_approved"] is True
    # without an approved reference the live observation is still recorded, and the comparison says so
    unreferenced = readback.camera_measurement_records(live=_live_camera())
    assert unreferenced["yaw_zero_bearing_rad"]["value"] == 0.12
    assert unreferenced["yaw_zero_bearing_rad"]["matches_approved"] is None
    assert "no approved reference" in unreferenced["yaw_zero_bearing_rad"]["reason"]


def test_the_runner_node_name_is_one_rclpy_accepts() -> None:
    """The live run refused `Node("/head_search_qualification_readback")`: a node name has no slash.

    rclpy validates the name the runtime registers, not the graph name the probes read, so the two are
    separate constants and this test keeps them from collapsing back into one.
    """

    assert readback.RUNNER_NODE == readback.RUNNER_GRAPH_NODE.lstrip("/")
    assert "/" not in readback.RUNNER_NODE
    assert re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", readback.RUNNER_NODE)
    assert readback.RUNNER_GRAPH_NODE == f"/{readback.RUNNER_NODE}"


# --- the hard failures ---------------------------------------------------------------------------------


def test_an_observed_value_that_differs_is_a_hard_failure_naming_both(tmp_path: Path) -> None:
    records = _observed(detector=_Detector(tracking_iou=0.3))
    assert records["tracking_iou"]["matches_approved"] is False
    assert records["tracking_iou"]["observed_value"] == 0.3
    assert records["tracking_iou"]["value"] == 0.5

    with pytest.raises(CalibrationInputsRefused) as raised:
        _document(tmp_path, detector=_Detector(tracking_iou=0.3))
    assert raised.value.code == readback.READBACK_VALUE_MISMATCH
    assert "tracking_iou" in raised.value.detail
    assert "0.3" in raised.value.detail and "0.5" in raised.value.detail


def test_a_bundle_that_is_not_the_promotion_refuses(tmp_path: Path) -> None:
    other = dict(PROMOTED_VALUES)
    other["max_age_s"] = 0.02
    with pytest.raises(CalibrationInputsRefused) as raised:
        readback.approved_values(
            production_config={"values": dict(PROMOTED_VALUES)},
            approved_bundle={
                "parameters": {name: {"value": value} for name, value in other.items()}
            },
        )
    assert raised.value.code == readback.READBACK_BUNDLE_MISMATCH
    assert "max_age_s" in raised.value.detail


def test_a_promoted_config_without_the_seventeen_refuses() -> None:
    short = {name: PROMOTED_VALUES[name] for name in _MEASURED[:16]}
    with pytest.raises(CalibrationInputsRefused) as raised:
        readback.approved_values(
            production_config={"values": short},
            approved_bundle={
                "parameters": {name: {"value": value} for name, value in short.items()}
            },
        )
    assert raised.value.code == readback.READBACK_VALUES_INCOMPLETE


def test_a_component_that_cannot_be_built_refuses(tmp_path: Path) -> None:
    def refuse(_configuration):
        raise ValueError("SEARCH_CONFIG_INVALID")

    with pytest.raises(CalibrationInputsRefused) as raised:
        readback.observe_qualification_values(
            values=dict(PROMOTED_VALUES),
            configuration=_configuration(),
            detector=_Detector(),
            controller_factory=refuse,
        )
    assert raised.value.code == readback.READBACK_COMPONENT_UNBUILDABLE
    assert "SEARCH_CONFIG_INVALID" in raised.value.detail


def test_a_detector_without_the_values_it_applies_refuses() -> None:
    class _Bare:
        pass

    with pytest.raises(CalibrationInputsRefused) as raised:
        _observed(detector=_Bare())
    assert raised.value.code == readback.READBACK_DETECTOR_FAILED
    assert "tracking_iou" in raised.value.detail


def test_a_detector_that_is_not_one_cuda_instance_refuses(tmp_path: Path) -> None:
    runtime = _runtime(tmp_path)
    readings = {
        "run_root": tmp_path / "qualification-run",
        "evidence_root": tmp_path / "evidence",
        "runtime": runtime,
        "approved": {"values_sha256": canonical_sha256(dict(PROMOTED_VALUES))},
        "observations": _observed(),
        "camera_measurements": readback.camera_measurement_records(live=_live_camera()),
        "detector": {
            "count": 2,
            "device": "cuda",
            "allow_cpu_fallback": False,
            "weights_sha256": runtime["weight_sha256_declared"],
        },
        "ownership": {},
        "approved_bundle_path": _bundle(tmp_path),
        "production_config_path": runtime["production_config"],
        "elapsed_s": 1.0,
        "taken_at_utc": "2026-10-02T08:00:00Z",
    }
    with pytest.raises(CalibrationInputsRefused) as raised:
        readback.readback_document(**readings)
    assert raised.value.code == readback.READBACK_DETECTOR_FAILED

    readings["detector"] = {
        "count": 1,
        "device": "cpu",
        "allow_cpu_fallback": True,
        "weights_sha256": runtime["weight_sha256_declared"],
    }
    with pytest.raises(CalibrationInputsRefused) as raised:
        readback.readback_document(**readings)
    assert raised.value.code == readback.READBACK_DETECTOR_FAILED

    readings["detector"] = {
        "count": 1,
        "device": "cuda",
        "allow_cpu_fallback": False,
        "weights_sha256": "d" * 64,
    }
    with pytest.raises(CalibrationInputsRefused) as raised:
        readback.readback_document(**readings)
    assert raised.value.code == readback.READBACK_DETECTOR_FAILED


# --- the producer's own refusals -----------------------------------------------------------------------


def _fake_observer(values, runtime, *, teardown=None):
    """An injected observation: everything the live observer returns, none of the stack."""

    def observe(**_kwargs):
        return {
            "values": {
                name: {
                    "value": values[name],
                    "approved_value": values[name],
                    "observed_value": values[name],
                    "observation": "constructed_production_component",
                    "component": "so101_demo.act.search.HeadSearchController",
                    "source": f"config[{name!r}]",
                    "configuration": {},
                    "configuration_sha256": "e" * 64,
                    "matches_approved": True,
                    "verified": True,
                }
                for name in _MEASURED
            },
            "camera_measurements": {
                name: {"value": value, "observation": readback.RUNNING_STACK_OBSERVATION}
                for name, value in FIXTURE_CAMERA_MEASUREMENTS.items()
            },
            "detector": {
                "count": 1,
                "device": "cuda",
                "allow_cpu_fallback": False,
                "weights_sha256": runtime["weight_sha256_declared"],
            },
            "teardown": teardown
            if teardown is not None
            else {
                "previous_stack_stopped": True,
                "controller_owner_stopped": True,
                "children_exited": True,
                "graph_clear": True,
                "gpu_released": True,
            },
        }

    return observe


def _producer(tmp_path: Path, *, observe, receipt=None, runtime=None, run_root=None):
    fixture = build_fixture(tmp_path / "fixture")
    runtime = runtime or read_runtime_identity(fixture.paths["final_run"])
    return readback.write_head_search_qualification_readback(
        run_root=run_root or fixture.run_root,
        evidence_root=tmp_path / "evidence",
        ownership_receipt=receipt or fixture.paths["ownership_receipt"],
        runtime=runtime,
        approved_bundle=json.loads(Path(fixture.paths["approved_bundle"]).read_text()),
        production_config=json.loads(Path(fixture.paths["production_config"]).read_text()),
        observe=observe,
        approved_bundle_path=fixture.paths["approved_bundle"],
        production_config_path=fixture.paths["production_config"],
    )


def test_the_producer_refuses_an_existing_qualification_run_root(tmp_path: Path) -> None:
    existing = tmp_path / "already-claimed"
    existing.mkdir()
    with pytest.raises(CalibrationInputsRefused) as raised:
        _producer(tmp_path, observe=_fake_observer(FIXTURE_VALUES, {}), run_root=existing)
    assert raised.value.code == readback.READBACK_RUN_ROOT_EXISTS


def test_the_producer_refuses_a_receipt_that_guards_another_run_root(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "fixture")
    receipt = _receipt(tmp_path, guard=tmp_path / "some-other-run")
    runtime = read_runtime_identity(fixture.paths["final_run"])
    with pytest.raises(CalibrationInputsRefused) as raised:
        _producer(
            tmp_path,
            observe=_fake_observer(FIXTURE_VALUES, runtime),
            receipt=receipt,
            runtime=runtime,
        )
    assert raised.value.code == readback.READBACK_OWNERSHIP_MISMATCH
    assert str(tmp_path / "some-other-run") in raised.value.detail


def test_the_producer_refuses_a_receipt_that_refused(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "fixture")
    receipt = _receipt(
        tmp_path,
        guard=fixture.run_root,
        status="EXCLUSIVE_OWNERSHIP_REFUSED",
        refusals=[
            {"code": "GPU_COMPUTE_APP_ACTIVE", "resource": "gpu_processes", "detail": "pid 7"}
        ],
    )
    runtime = read_runtime_identity(fixture.paths["final_run"])
    with pytest.raises(CalibrationInputsRefused) as raised:
        _producer(
            tmp_path,
            observe=_fake_observer(FIXTURE_VALUES, runtime),
            receipt=receipt,
            runtime=runtime,
        )
    assert raised.value.code == readback.READBACK_OWNERSHIP_REFUSED
    assert "GPU_COMPUTE_APP_ACTIVE" in raised.value.detail
    assert not (tmp_path / "evidence" / readback.ARTIFACT).exists()


def test_the_producer_refuses_a_runtime_that_is_not_the_cuda_one(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "fixture")
    runtime = read_runtime_identity(fixture.paths["final_run"])
    runtime["allow_cpu_fallback"] = True
    with pytest.raises(CalibrationInputsRefused) as raised:
        _producer(tmp_path, observe=_fake_observer(FIXTURE_VALUES, runtime), runtime=runtime)
    assert raised.value.code == readback.READBACK_RUNTIME_UNVERIFIED


def test_the_producer_refuses_an_unproven_teardown_and_records_the_refusal(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "fixture")
    runtime = read_runtime_identity(fixture.paths["final_run"])

    def observe(**_kwargs):
        raise readback.QualificationReadbackRefused(
            readback.READBACK_TEARDOWN_UNPROVEN, "one stack process was still alive"
        )

    with pytest.raises(CalibrationInputsRefused) as raised:
        _producer(tmp_path, observe=observe, runtime=runtime)
    assert raised.value.code == readback.READBACK_TEARDOWN_UNPROVEN
    refusal = json.loads(
        (tmp_path / "evidence" / "readback-refusal.json").read_text(encoding="utf-8")
    )
    assert refusal["code"] == readback.READBACK_TEARDOWN_UNPROVEN
    assert refusal["run_root"] == str(fixture.run_root)
    assert refusal["provenance"]["values_sha256"]
    assert not (tmp_path / "evidence" / readback.ARTIFACT).exists()


def test_the_producer_writes_the_document_and_the_teardown_proof(tmp_path: Path) -> None:
    fixture = build_fixture(tmp_path / "fixture")
    runtime = read_runtime_identity(fixture.paths["final_run"])
    seen = {}

    def observe(**kwargs):
        seen.update(kwargs)
        return _fake_observer(FIXTURE_VALUES, runtime)(**kwargs)

    result = _producer(tmp_path, observe=observe, runtime=runtime)

    assert result["status"] == readback.PASS
    assert seen["run_root"] == fixture.run_root
    assert seen["values"] == FIXTURE_VALUES
    assert seen["stdout"] is not None and seen["stderr"] is not None
    proof = json.loads(Path(result["teardown_proof"]).read_text(encoding="utf-8"))
    assert proof["gpu_released"] is True
    assert (tmp_path / "evidence" / readback.STDOUT_LOG).is_file()
    assert (tmp_path / "evidence" / readback.STDERR_LOG).is_file()
    # the qualification run root stays unclaimed: the aggregate owns it, and it never resumes one
    assert not fixture.run_root.exists()


# --- the installed entry -------------------------------------------------------------------------------


def _cli_arguments(tmp_path: Path, run_root: Path, evidence: Path, *extra: str) -> list:
    fixture_source = tmp_path / "fixture"
    return [
        "measure-qualification-readback",
        "--run-root",
        str(run_root),
        "--evidence-root",
        str(evidence),
        "--ownership-receipt",
        str(fixture_source / "ownership/exclusive-ownership.json"),
        "--final-run",
        str(fixture_source / "final-run"),
        "--production-config",
        str(
            fixture_source
            / "final-run/install/so101_demo_py/share/so101_demo_py/config/mujoco/act/head_search_v2.json"
        ),
        "--approved-bundle",
        str(fixture_source / "approved-bundle.json"),
        "--geometry-seal",
        str(fixture_source / "approved-bundle.json"),
        "--scene",
        str(fixture_source / "approved-bundle.json"),
        "--urdf",
        str(fixture_source / "approved-bundle.json"),
        "--plugin-config",
        str(fixture_source / "approved-bundle.json"),
        "--controller-config",
        str(fixture_source / "approved-bundle.json"),
        "--weights",
        str(fixture_source / "final-run/weights/best.pt"),
        "--workdir",
        str(tmp_path / "work"),
        *extra,
    ]


def test_the_cli_refuses_missing_inputs_an_existing_root_and_an_unclaimed_receipt(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = build_fixture(tmp_path / "fixture")
    run_root = fixture.run_root
    evidence = tmp_path / "evidence"
    (tmp_path / "ipc").mkdir()
    missing = _cli_arguments(tmp_path, run_root, evidence)
    missing[missing.index("--weights") + 1] = str(tmp_path / "absent.pt")
    assert main(missing) == 2
    assert HEAD_SEARCH_MEASUREMENT_INPUTS_INCOMPLETE in capsys.readouterr().err

    existing = tmp_path / "claimed"
    existing.mkdir()
    assert main(_cli_arguments(tmp_path, existing, evidence)) == 2
    assert "has not claimed yet" in capsys.readouterr().err

    evidence.mkdir()
    (evidence / "half-written.json").write_text("{}", encoding="utf-8")
    assert main(_cli_arguments(tmp_path, run_root, evidence)) == 2
    assert "never resumed or overwritten" in capsys.readouterr().err


def test_the_cli_runs_the_readback_and_prints_the_measured_values(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    fixture = build_fixture(tmp_path / "fixture")
    runtime = read_runtime_identity(fixture.paths["final_run"])

    def observe(**kwargs):
        return _fake_observer(FIXTURE_VALUES, runtime)(**kwargs)

    monkeypatch.setattr(readback, "run_readback_observation", observe)
    (tmp_path / "ipc").mkdir()
    run_root = fixture.run_root
    evidence = tmp_path / "evidence"

    rc = main(_cli_arguments(tmp_path, run_root, evidence, "--anchor", "default"))

    assert rc == 0
    printed = capsys.readouterr().out
    assert "READBACK_MEASURED status=PASS" in printed
    assert "observed coarse_step_rad=" in printed
    assert "camera_measurements=" in printed
    document = json.loads((evidence / readback.ARTIFACT).read_text(encoding="utf-8"))
    assert document["values_count"] == 17
    assert document["kind"] == aggregate.READBACK_KIND
    assert document["command"].startswith(
        "so101_head_search_calibration measure-qualification-readback"
    )
    assert not run_root.exists()


def _controllers_yaml(tmp_path, directory):
    path = tmp_path / "controllers.yaml"
    path.write_text(
        "controller_manager:\n  ros__parameters:\n    update_rate: 500\n"
        "neck_controller:\n  ros__parameters:\n    head_deadman_directory: " + str(directory) + "\n",
        encoding="utf-8",
    )
    return path


def test_the_readback_creates_the_declared_private_deadman_directory(tmp_path):
    import os
    import shutil
    import stat
    import tempfile

    # a short base: the socket path inside it must fit the AF_UNIX bound
    base = Path(tempfile.mkdtemp(prefix="dm", dir="/tmp"))
    directory = base / "dm"
    try:
        got = readback.prepare_deadman_directory(_controllers_yaml(tmp_path, directory))
        assert got == str(directory)
        assert stat.S_IMODE(os.stat(directory).st_mode) == 0o700 and os.stat(directory).st_uid == os.getuid()
    finally:
        shutil.rmtree(base, ignore_errors=True)


def test_the_readback_refuses_a_controller_file_that_declares_no_deadman_directory(tmp_path):
    path = tmp_path / "controllers.yaml"
    path.write_text("neck_controller:\n  ros__parameters:\n    joints: [neck_yaw_joint]\n", encoding="utf-8")
    with pytest.raises(readback.QualificationReadbackRefused) as refused:
        readback.prepare_deadman_directory(path)
    assert refused.value.code == readback.READBACK_PROBE_FAILED


def test_the_readback_refuses_a_deadman_directory_whose_socket_path_is_too_long(tmp_path):
    directory = tmp_path / ("d" * 90)
    with pytest.raises(readback.QualificationReadbackRefused) as refused:
        readback.prepare_deadman_directory(_controllers_yaml(tmp_path, directory))
    assert refused.value.code == readback.READBACK_PROBE_FAILED
