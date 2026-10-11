"""The scenario producer: refusals, documents, receipts and interruption classes."""

from __future__ import annotations

import hashlib
import json

from head_search_scenarios_support import (
    ANCHORS,
    CONDITION_CLASSES,
    VERTICAL_BOUNDS_PX,
    FakeDetector,
    FakePlant,
    _clock,
)
import pytest

from so101_demo.act.head_search_scenarios import contracts as module_contracts
from so101_demo.act.head_search_scenarios import journal as module_journal
from so101_demo.act.head_search_scenarios import plan as module_plan
from so101_demo.act.head_search_scenarios import writer as module_writer
from so101_demo.act.head_search_scenarios.contracts import (
    CAL_SCENARIO_CUP_NOT_FOUND,
    CAL_SCENARIO_OWNERSHIP_REFUSED,
    CAL_SCENARIO_RUN_ROOT_EXISTS,
    CAL_SCENARIO_RUNTIME_UNVERIFIED,
    CAL_SCENARIO_SPLIT_LEAK,
    CalibrationScenarioRefused,
)
from so101_demo.act.head_search_timing_measurement.contracts import (
    CAL_TIMING_DEVICE_UNAVAILABLE,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
)

SCENE_XML = """<mujoco model="scenario-fixture">
  <option timestep="0.002" gravity="0 0 -9.81" integrator="implicitfast"/>
  <worldbody>
    <body name="plastic_cup">
      <joint name="cup_free_joint" type="free"/>
      <geom name="cup_geom" type="cylinder" size="0.04 0.045"/>
    </body>
    <body name="head_mount">
      <joint name="neck_yaw_joint" type="hinge" axis="0 0 1" damping="0.05" armature="0.001"/>
      <geom name="head_geom" type="box" size="0.05 0.05 0.05"/>
      <camera name="head_camera" pos="0 0 0.05" fovy="60" xyaxes="1 0 0 0 1 0"/>
    </body>
  </worldbody>
</mujoco>
"""


QUALIFICATION_PARTITIONS = {
    "schema_version": 1,
    "document": "head-search-scenario-partitions/v1",
    "condition_classes": CONDITION_CLASSES,
    "anchors": ANCHORS,
    "calibration": [700000, 700001],
    "held_out_evaluation": [800000, 800001],
    "qualification": [
        {
            "seed": 900000 + index,
            "scene_group_id": f"scene-{900000 + index:09d}",
            "condition_class": CONDITION_CLASSES[index % len(CONDITION_CLASSES)],
            "anchor": ANCHORS[index % len(ANCHORS)],
        }
        for index in range(10)
    ],
}


def _write_inputs(tmp_path) -> dict:
    """The eight declared inputs of the scenario flight, synthetic but complete."""

    scene = tmp_path / "head_search_scene.xml"
    scene.write_text(SCENE_XML, encoding="utf-8")
    scene_sha256 = hashlib.sha256(scene.read_bytes()).hexdigest()
    weights = tmp_path / "C.pt"
    weights.write_bytes(b"selected-model")
    weights_sha256 = hashlib.sha256(weights.read_bytes()).hexdigest()
    seal = tmp_path / "head-camera-geometry.json"
    seal.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "camera_name": "head_camera",
                "camera": {"camera_name": "head_camera", "fovy_rad": 1.0471975511965976},
                "image_width": 640,
                "image_height": 480,
                "horizontal_fov_rad": 1.3121067481206794,
                "required_search_domain_rad": [-0.17559216195018026, 0.08047101126546086],
                "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                "in_frame_matrix": {
                    "default": {"neck_start_rad": 0.0},
                    "left": {"neck_start_rad": 0.0},
                    "forward": {"neck_start_rad": 0.0},
                },
                "workspace_matrix": {
                    "key_samples": [
                        {"anchor": name, "kind": "anchor", "point_m": [-0.08, -0.28, 0.165]}
                        for name in ANCHORS
                    ]
                },
                "source_digests": {"scene_sha256": scene_sha256},
            }
        ),
        encoding="utf-8",
    )
    production = tmp_path / "head_search_runtime.json"
    production.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "runtime_id": "head-search-runtime",
                "allow_cpu_fallback": False,
                "cuda_device": "cuda:0",
                "weight_path": str(weights),
                "weight_sha256": weights_sha256,
                "camera": {
                    "name": "head_camera",
                    "frame_id": "head_camera_frame",
                    "ray_origin_frame_id": "head_camera_frame",
                },
                "motion": {"settle_velocity_rad_s": 0.05, "goal_tolerance_rad": 0.05},
                "tracker": {"name": "bytetrack", "iou_threshold": 0.5},
                "values": {
                    "coarse_step_rad": 0.6560533740603397,
                    "horizontal_fov_rad": 1.3121067481206794,
                    "lock_valid_neck_rad": [-6.283175307179587, 6.283175307179587],
                    "max_age_s": 0.05,
                    "max_skew_s": 0.02,
                    "search_timeout_s": 30.0,
                    "center_deadband_px": 3.0,
                    "vertical_bounds_px": list(VERTICAL_BOUNDS_PX),
                    "min_area_px2": 64.0,
                    "min_confidence": 0.25,
                    "tracking_iou": 0.5,
                    "max_fine_corrections": 2,
                    "max_fine_total_rad": 0.6961197054865531,
                    "min_bbox_aspect": 0.5,
                    "stop_velocity_rad_s": 0.04136050464213824,
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
                "candidate_id": "C2a",
                "weight_sha256": weights_sha256,
                "operating_points": {
                    "head": {"min_confidence": 0.25, "tracker": {"iou": 0.5}},
                    "task": {"min_confidence": 0.25, "tracker": {"iou": 0.5}},
                },
            }
        ),
        encoding="utf-8",
    )
    controllers = tmp_path / "ros2_controllers.yaml"
    controllers.write_text(
        "controller_manager:\n  ros__parameters:\n    update_rate: 500.0\n", encoding="utf-8"
    )
    dataset = tmp_path / "head_camera_yolo_seg.yaml"
    dataset.write_text(
        f"mjcf_path: {scene.name}\ncamera_name: head_camera\nimage_width: 640\nimage_height: 480\n",
        encoding="utf-8",
    )
    partitions = tmp_path / "head-search-scenario-partitions.json"
    partitions.write_text(json.dumps(QUALIFICATION_PARTITIONS), encoding="utf-8")
    return {
        "scene": scene,
        "seal": seal,
        "production": production,
        "controllers": controllers,
        "weights": weights,
        "frozen": frozen,
        "dataset": dataset,
        "partitions": partitions,
    }


def _class_aware_detector(plant, request, *, blind=()):
    """A detector that places the cup count the item's own condition class declares."""

    if int(request["seed"]) in blind:
        return FakeDetector(plant, cups=0)
    return FakeDetector(plant, cups=module_plan.declared_cup_count(str(request["scenario"])))


def _patch_flight(monkeypatch, *, ownership_status="EXCLUSIVE_OWNERSHIP_OK", cuda=True):
    """Stub the four heavy seams: the ownership gate, CUDA, the scene preparation and the plant."""

    from so101_demo.act.head_search_scenarios import writer as scenarios_module

    monkeypatch.setattr(scenarios_module, "_cuda_available", lambda: cuda)
    monkeypatch.setattr(
        scenarios_module, "prepare_episode_scene", lambda **request: {"prepared": True}
    )
    state: dict = {}

    class Plant(FakePlant):
        def __init__(self, request) -> None:
            super().__init__(cup_yaw_rad=0.05)
            self.request = request
            state["plant"] = self

        def close(self) -> None:
            state["closed"] = state.get("closed", 0) + 1

    monkeypatch.setattr(scenarios_module, "MujocoEpisodePlant", Plant)
    gate_calls: list = []

    def ownership_check(**kwargs):
        gate_calls.append(kwargs)
        if ownership_status != "EXCLUSIVE_OWNERSHIP_OK":
            return {
                "status": ownership_status,
                "run_root": str(kwargs["run_root"]),
                "refusals": [{"code": "DETECTOR_OWNER_ACTIVE", "resource": "process_table", "detail": "pid 5"}],
            }
        kwargs["run_root"].mkdir(parents=True, exist_ok=True)
        return {"status": ownership_status, "run_root": str(kwargs["run_root"]), "refusals": []}

    return scenarios_module, ownership_check, gate_calls, state


def _produce(tmp_path, monkeypatch, *, status="EXCLUSIVE_OWNERSHIP_OK", cuda=True, **overrides):
    inputs = _write_inputs(tmp_path)
    module_, gate, calls, state = _patch_flight(monkeypatch, ownership_status=status, cuda=cuda)
    output = overrides.pop("output_dir", tmp_path / "run-root")
    kwargs = {
        "scene_path": inputs["scene"],
        "geometry_seal_path": inputs["seal"],
        "production_search_config_path": inputs["production"],
        "controller_config_path": inputs["controllers"],
        "frozen_candidate_path": inputs["frozen"],
        "weights_path": inputs["weights"],
        "dataset_config_path": inputs["dataset"],
        "scenario_partitions_path": inputs["partitions"],
        "output_dir": output,
        "evidence_root": tmp_path,
        "ownership_check": gate,
        "plant": None,
        "detector_factory": _class_aware_detector,
        "command": "so101_head_search_calibration measure-scenarios",
        "clock": _clock(),
    }
    kwargs.update(overrides)
    return module_.write_head_search_scenarios(**kwargs), calls, state, inputs, output


def test_the_producer_refuses_the_whole_run_when_the_ownership_gate_refuses(tmp_path, monkeypatch):
    with pytest.raises(CalibrationScenarioRefused) as refused:
        _produce(tmp_path, monkeypatch, status="EXCLUSIVE_OWNERSHIP_REFUSED")

    assert refused.value.code == CAL_SCENARIO_OWNERSHIP_REFUSED
    assert "DETECTOR_OWNER_ACTIVE" in str(refused.value)
    assert not (tmp_path / "scenarios.json").exists()


def test_the_producer_refuses_the_whole_run_when_the_runtime_identity_does_not_hold(tmp_path, monkeypatch):
    inputs = _write_inputs(tmp_path)
    module_, gate, _calls, _state = _patch_flight(monkeypatch)

    def reader(final_run):
        return {
            "final_run": str(final_run),
            "source_commit": "0" * 40,
            "production_config_sha256": "1" * 64,
            "values_sha256": "2" * 64,
            "allow_cpu_fallback": False,
            "weight_sha256_declared": "9" * 64,
            "weight_sha256_observed": "9" * 64,
        }

    with pytest.raises(CalibrationScenarioRefused) as refused:
        module_.write_head_search_scenarios(
            scene_path=inputs["scene"],
            geometry_seal_path=inputs["seal"],
            production_search_config_path=inputs["production"],
            controller_config_path=inputs["controllers"],
            frozen_candidate_path=inputs["frozen"],
            weights_path=inputs["weights"],
            dataset_config_path=inputs["dataset"],
            scenario_partitions_path=inputs["partitions"],
            output_dir=tmp_path / "run-root",
            evidence_root=tmp_path,
            ownership_check=gate,
            runtime_identity_reader=reader,
            final_run=tmp_path / "frozen-root",
            detector_factory=lambda plant, request: FakeDetector(plant),
        )

    assert refused.value.code == CAL_SCENARIO_RUNTIME_UNVERIFIED
    assert "9" * 64 in str(refused.value)


def test_the_producer_refuses_a_device_without_cuda_instead_of_falling_back(tmp_path, monkeypatch):
    with pytest.raises(CalibrationScenarioRefused) as refused:
        _produce(tmp_path, monkeypatch, cuda=False)

    assert refused.value.code == CAL_TIMING_DEVICE_UNAVAILABLE


def test_the_producer_refuses_weights_the_sealed_configuration_does_not_declare(tmp_path, monkeypatch):
    inputs = _write_inputs(tmp_path)
    inputs["weights"].write_bytes(b"another-model")
    module_, gate, _calls, _state = _patch_flight(monkeypatch)
    with pytest.raises(CalibrationScenarioRefused) as refused:
        module_.write_head_search_scenarios(
            scene_path=inputs["scene"],
            geometry_seal_path=inputs["seal"],
            production_search_config_path=inputs["production"],
            controller_config_path=inputs["controllers"],
            frozen_candidate_path=inputs["frozen"],
            weights_path=inputs["weights"],
            dataset_config_path=inputs["dataset"],
            scenario_partitions_path=inputs["partitions"],
            output_dir=tmp_path / "run-root",
            evidence_root=tmp_path,
            ownership_check=gate,
            detector_factory=lambda plant, request: FakeDetector(plant),
        )

    assert refused.value.code == CAL_TIMING_EVIDENCE_CONTRADICTORY


def test_the_producer_refuses_an_output_directory_that_already_exists(tmp_path, monkeypatch):
    output = tmp_path / "run-root"
    output.mkdir()
    with pytest.raises(CalibrationScenarioRefused) as refused:
        _produce(tmp_path, monkeypatch, output_dir=output)

    assert refused.value.code == CAL_SCENARIO_RUN_ROOT_EXISTS


def test_the_producer_writes_the_document_the_journal_and_the_receipt_with_provenance(tmp_path, monkeypatch):
    result, _calls, state, inputs, output = _produce(tmp_path, monkeypatch)
    document = json.loads((output / "scenarios.json").read_text(encoding="utf-8"))
    receipt = json.loads((output / "measurement-receipt.json").read_text(encoding="utf-8"))
    journal = [
        json.loads(line)
        for line in (output / "scenario-journal.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    assert document["kind"] == module_contracts.KIND
    assert document["phase"] == "scenarios"
    assert document["scenario_count"] == 10
    assert document["passed_count"] == 10
    assert document["seeds"] == list(range(900000, 900010))
    assert document["anchor_split"] == {"default": 4, "forward": 3, "left": 3}
    assert document["qualification_verdict"] is None
    assert document["scene_sha256"] == json.loads(
        (inputs["seal"]).read_text(encoding="utf-8")
    )["source_digests"]["scene_sha256"]
    assert document["weights"]["sha256"] == json.loads(
        inputs["production"].read_text(encoding="utf-8")
    )["weight_sha256"]
    assert document["production_search_config"]["sha256"]
    assert document["values_sha256"]
    assert document["runtime_identity"]
    assert document["ownership_receipt"]["status"] == "EXCLUSIVE_OWNERSHIP_OK"
    assert document["sha256"] == module_writer.canonical_sha256(
        {key: value for key, value in document.items() if key != "sha256"}
    )
    assert len(journal) == 10
    assert [row["seed"] for row in journal] == list(range(900000, 900010))
    assert all(set(row) == set(module_journal.JOURNAL_KEYS) for row in journal)
    assert receipt["kind"] == module_contracts.RECEIPT_KIND
    assert receipt["scenario_count"] == 10
    assert receipt["document_sha256"] == document["sha256"]
    assert state["closed"] == 10, "every scenario's plant is closed"


def test_every_scenario_gets_its_own_evidence_document(tmp_path, monkeypatch):
    _result, _calls, _state, _inputs, output = _produce(tmp_path, monkeypatch)
    directory = output / module_contracts.EVIDENCE_DIR
    files = sorted(path.name for path in directory.glob("*.json"))

    assert len(files) == 10
    assert files[0] == "900000.json"
    assert files[-1] == "900009.json"
    entry = json.loads((directory / "900000.json").read_text(encoding="utf-8"))
    assert entry["seed"] == 900000
    assert entry["outcome"] == "PASSED"
    assert entry["evidence"]["command"] == "so101_head_search_calibration measure-scenarios"
    assert entry["attempts"], "the full attempt evidence is in the per-scenario document"


def test_the_producer_runs_a_declared_subset_and_says_which_seeds_ran(tmp_path, monkeypatch):
    result, _calls, _state, _inputs, output = _produce(tmp_path, monkeypatch, seeds=[900002])
    document = result["document"]

    assert document["scenario_count"] == 1
    assert document["seeds"] == [900002]
    assert document["records"][0]["seed"] == 900002


def test_the_producer_refuses_a_calibration_seed_rather_than_qualifying_it(tmp_path, monkeypatch):
    with pytest.raises(CalibrationScenarioRefused) as refused:
        _produce(tmp_path, monkeypatch, seeds=[700000])

    assert refused.value.code == CAL_SCENARIO_SPLIT_LEAK


def test_the_receipt_records_every_outcome_and_the_anchor_split(tmp_path, monkeypatch):
    result, _calls, _state, _inputs, _output = _produce(tmp_path, monkeypatch)
    receipt = result["receipt"]

    assert receipt["passed_count"] == 10
    assert receipt["failed_count"] == 0
    assert receipt["refused_count"] == 0
    assert receipt["by_condition_class"]["nominal"]["passed"] == 1
    assert receipt["by_condition_class"]["two_cups"]["passed"] == 1
    assert receipt["by_condition_class"]["no_cup"]["passed"] == 1
    assert receipt["anchor_split"] == {"default": 4, "forward": 3, "left": 3}
    assert receipt["records"][0]["outcome"] in ("PASSED", "FAILED", "REFUSED")
    assert receipt["cuda_used"] is True
    assert receipt["allow_cpu_fallback"] is False
    assert receipt["ros_nodes_started"] is False
    assert receipt["hardware_motion_commanded"] is False


def test_the_producer_journals_a_refusal_per_scenario_and_still_reaches_the_last_one(
    tmp_path, monkeypatch
):
    inputs = _write_inputs(tmp_path)
    module_, gate, _calls, _state = _patch_flight(monkeypatch)
    blind = {900000, 900001}

    def detector_factory(plant, request):
        return _class_aware_detector(plant, request, blind=blind)

    result = module_.write_head_search_scenarios(
        scene_path=inputs["scene"],
        geometry_seal_path=inputs["seal"],
        production_search_config_path=inputs["production"],
        controller_config_path=inputs["controllers"],
        frozen_candidate_path=inputs["frozen"],
        weights_path=inputs["weights"],
        dataset_config_path=inputs["dataset"],
        scenario_partitions_path=inputs["partitions"],
        output_dir=tmp_path / "run-root",
        evidence_root=tmp_path,
        ownership_check=gate,
        detector_factory=detector_factory,
    )
    records = result["document"]["records"]

    assert len(records) == 10
    assert [row["outcome"] for row in records[:2]] == ["FAILED", "FAILED"]
    assert records[0]["outcome_code"] == CAL_SCENARIO_CUP_NOT_FOUND
    assert {row["outcome"] for row in records[2:]} == {"PASSED"}


def test_the_producer_reports_the_two_interruption_classes_as_two_attempts(tmp_path, monkeypatch):
    inputs = _write_inputs(tmp_path)
    module_, gate, _calls, _state = _patch_flight(monkeypatch)
    result = module_.write_head_search_scenarios(
        scene_path=inputs["scene"],
        geometry_seal_path=inputs["seal"],
        production_search_config_path=inputs["production"],
        controller_config_path=inputs["controllers"],
        frozen_candidate_path=inputs["frozen"],
        weights_path=inputs["weights"],
        dataset_config_path=inputs["dataset"],
        scenario_partitions_path=inputs["partitions"],
        output_dir=tmp_path / "run-root",
        evidence_root=tmp_path,
        ownership_check=gate,
        detector_factory=_class_aware_detector,
        seeds=[900008, 900009],
    )
    records = result["document"]["records"]

    assert [row["seed"] for row in records] == [900008, 900009]
    assert all(row["condition_class"] in ("fast_interruption", "reacquire_after_stop") for row in records)
    assert all(len(row["attempt_ids"]) == 2 for row in records)
    assert all(row["outcome"] == "PASSED" for row in records)
