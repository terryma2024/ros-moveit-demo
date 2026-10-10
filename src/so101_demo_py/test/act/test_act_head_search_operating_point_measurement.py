"""The installed producers of phase 3's two inputs: the rule record and its measurement frames.

The rule must exist before any measurement is admitted, the measurement must be the one the rule
consumes, and both must be the documents the installed phase 3 accepts. Every test here is
detector-free and MuJoCo-free: the two heavy layers (render + detect) are the only ones a GPU can
cover, so everything that decides *what* is measured is pinned with synthetic sealed documents.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from so101_demo.act.head_search_operating_point import (
    CAL_RULE_AFTER_MEASUREMENT,
    CAL_SPLIT_LEAK,
    record_selection_rule,
    select_operating_point,
)
from so101_demo.act.head_search_operating_point_measurement import (
    CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY,
    CANDIDATE_IDS,
    RECORDING_MIN_CONFIDENCE,
    RECORDING_TRACKING_IOU,
    CAL_OPERATING_POINT_EVIDENCE_MISSING,
    DOCUMENT_NAME,
    GRID_CONFIDENCES,
    GRID_TRACKING_IOUS,
    RECEIPT_NAME,
    RECORDING_MIN_CONFIDENCE,
    RECORDING_TRACKING_IOU,
    RULE_NAME,
    TASK_RULE_NAME,
    CalibrationOperatingPointMeasurementRefused,
    episode_frame,
    operating_point_grid,
    operating_point_measurement_document,
    plan_operating_point_measurement,
    record_selection_rule_documents,
    recording_settings,
    static_frame,
    toolchain_identity,
    truth_from_instances,
)
from so101_demo.perception_benchmark.contracts import canonical_sha256

DIGESTS = {
    "A": "a" * 64,
    "B": "b" * 64,
    "C": "c" * 64,
}
SEAL_SHA = "d" * 64


def _production_config() -> dict:
    return {
        "schema_version": 2,
        "values": {
            "min_confidence": 0.4,
            "tracking_iou": 0.3,
            "min_bbox_aspect": 0.5,
            "min_area_px2": 64.0,
            "coarse_step_rad": 0.3,
        },
    }


def _geometry_seal() -> dict:
    return {
        "seal_sha256": SEAL_SHA,
        "camera_name": "head_camera",
        "horizontal_fov_rad": 1.3121067481206794,
        "lock_valid_neck_rad": [-0.2, 0.2],
        "required_search_domain_rad": [-0.3, 0.3],
        "anchors_rad": {"default": 0.0},
    }


def _sample(seed: int, domain: str, scenario: str, instances: int) -> dict:
    return {
        "seed": seed,
        "split": "val",
        "scenario": scenario,
        "scene_group_id": f"scene-{seed:09d}",
        "image": f"images/val/{seed:09d}.png",
        "label": f"labels/val/{seed:09d}.txt",
        "truth": f"truth/val/{seed:09d}.json",
        "image_sha256": "e" * 64,
        "visible_instance_count": instances,
    }


def _manifest(domain: str, camera: str, seeds) -> dict:
    samples = [_sample(seed, domain, scenario, instances) for seed, scenario, instances in seeds]
    return {
        "camera_name": camera,
        "sample_count": len(samples) + 4,
        "split_counts": {"train": 4, "val": len(samples), "test": 0},
        "samples": samples,
    }


def _head_manifest() -> dict:
    return _manifest(
        "head",
        "head_camera",
        [(4100000, "no_cup", 0), (4100001, "one_cup_distractors", 1)],
    )


def _task_manifest() -> dict:
    return _manifest(
        "task",
        "task_camera",
        [(200000, "no_cup", 0), (200001, "two_cups", 2)],
    )


def _partitions() -> dict:
    return {
        "schema_version": 1,
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
        "calibration": [700000, 700001, 700002, 700003],
        "held_out_evaluation": [800000, 800001],
        "qualification": [{"seed": 900000, "scene_group_id": "scene-000900000"}],
    }


def _frozen(candidate_id: str, digest: str | None = None) -> dict:
    return {
        "schema_version": 1,
        "kind": "head-search-frozen-candidate",
        "candidate_id": candidate_id,
        "weight_sha256": digest or DIGESTS[candidate_id],
        "operating_points": {
            "head": {"min_confidence": 0.25, "tracker": {"iou": 0.5}},
            "task": {"min_confidence": 0.25, "tracker": {"iou": 0.5}},
        },
        "postprocess": {},
        "runtime": {},
        "tracker": {},
        "promotable": True,
    }


def _plan(**overrides) -> dict:
    arguments = {
        "geometry_seal": _geometry_seal(),
        "head_dataset_manifest": _head_manifest(),
        "task_dataset_manifest": _task_manifest(),
        "partitions": _partitions(),
        "production_config": _production_config(),
        "frozen_candidates": [_frozen(name) for name in ("A", "B", "C")],
        "weights_sha256": dict(DIGESTS),
    }
    arguments.update(overrides)
    return plan_operating_point_measurement(**arguments)


def _detections(conf: float, boxes) -> dict:
    return {
        name: [
            {"x": float(x), "y": float(y), "conf": float(conf), "w": float(w), "h": float(h)}
            for x, y, w, h in boxes
        ]
        for name in ("A", "B", "C")
    }


def _truth(x: float = 10.0, y: float = 12.0) -> list[dict]:
    return [{"x": x, "y": y, "visible_px": 900, "instance_id": "plastic_cup@1"}]


def _frames_from_plan(plan: dict) -> list:
    """The frames the producer would record, from the plan alone, with declared synthetic hits."""

    domain = "head"
    description = plan["domains"][domain]
    frames = []
    for sample in description["val_samples"]:
        hit = sample["visible_instance_count"] > 0
        frames.append(
            static_frame(
                domain=domain,
                camera_name=description["camera_name"],
                sample=sample,
                truth=_truth() if hit else [],
                detections=_detections(0.9, [(10.0, 12.0, 30.0, 40.0)])
                if hit
                else _detections(0.9, []),
                latency_ms={name: 12.0 for name in ("A", "B", "C")},
            )
        )
    for episode in description["calibration_episodes"]:
        for angle in episode["neck_angles_rad"]:
            hit = episode["cup_count"] > 0
            frames.append(
                episode_frame(
                    domain=domain,
                    camera_name=description["camera_name"],
                    seed=episode["seed"],
                    neck_rad=angle,
                    scenario=episode["scenario"],
                    split="calibration",
                    truth=_truth() if hit else [],
                    detections=(
                        _detections(0.9, [(10.0, 12.0, 30.0, 40.0)])
                        if hit
                        else _detections(0.9, [])
                    ),
                    latency_ms={name: 12.0 for name in ("A", "B", "C")},
                )
            )
    return frames


def test_operating_point_grid_is_the_declared_cells_in_declared_order() -> None:
    grid = operating_point_grid(production_config=_production_config())
    assert len(grid) == len(GRID_CONFIDENCES) * len(GRID_TRACKING_IOUS) == 18
    assert [(point["min_confidence"], point["tracking_iou"]) for point in grid] == [
        (confidence, iou) for confidence in GRID_CONFIDENCES for iou in GRID_TRACKING_IOUS
    ]
    assert grid[0] == {
        "min_confidence": 0.25,
        "min_bbox_aspect": 0.5,
        "min_area_px2": 64.0,
        "tracking_iou": 0.5,
    }
    assert {point["min_area_px2"] for point in grid} == {64.0}
    assert {point["min_bbox_aspect"] for point in grid} == {0.5}


def test_operating_point_grid_refuses_a_config_without_the_geometry_values() -> None:
    config = _production_config()
    del config["values"]["min_area_px2"]
    with pytest.raises(ValueError):
        operating_point_grid(production_config=config)


def test_recording_settings_are_the_extremes_every_point_can_be_reapplied_from() -> None:
    settings = recording_settings()
    assert settings["min_confidence"] == RECORDING_MIN_CONFIDENCE == min(GRID_CONFIDENCES)
    assert settings["tracking_iou"] == RECORDING_TRACKING_IOU == max(GRID_TRACKING_IOUS)
    assert "re-appli" in settings["why"]


def test_plan_names_both_selection_splits_and_measures_both_domains() -> None:
    plan = _plan()
    assert plan["selection_splits"] == ["val", "calibration"]
    assert plan["held_out_split"] == "held_out_evaluation"
    assert sorted(plan["domains"]) == ["head", "task"]
    head = plan["domains"]["head"]
    assert head["camera_name"] == "head_camera"
    assert [sample["seed"] for sample in head["val_samples"]] == [4100000, 4100001]
    assert plan["domains"]["task"]["camera_name"] == "task_camera"
    assert len(head["calibration_episodes"]) == len(_partitions()["calibration"])
    assert head["calibration_episodes"][0]["neck_angles_rad"] == [-0.3, 0.0, 0.3]
    scenarios = [episode["scenario"] for episode in head["calibration_episodes"]]
    assert scenarios == ["nominal", "nominal", "left_anchor", "left_anchor"]
    assert [episode["cup_count"] for episode in head["calibration_episodes"]] == [1, 1, 1, 1]
    assert plan["grid"] == list(operating_point_grid(production_config=_production_config()))
    assert plan["candidates"][0]["weights_sha256"] == DIGESTS["A"]


def test_plan_refuses_a_weight_file_digest_that_is_not_the_frozen_candidates() -> None:
    with pytest.raises(CalibrationOperatingPointMeasurementRefused) as refusal:
        _plan(weights_sha256={**DIGESTS, "B": "f" * 64})
    assert refusal.value.code == CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY
    assert "B" in str(refusal.value)


def test_plan_refuses_a_candidate_set_that_is_not_the_declared_three() -> None:
    with pytest.raises(CalibrationOperatingPointMeasurementRefused) as refusal:
        _plan(frozen_candidates=[_frozen("A"), _frozen("B")])
    assert refusal.value.code == CAL_OPERATING_POINT_EVIDENCE_MISSING
    with pytest.raises(CalibrationOperatingPointMeasurementRefused) as other:
        _plan(frozen_candidates=[_frozen("A"), _frozen("B"), _frozen("C"), _frozen("C")])
    assert other.value.code == CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY


def test_plan_refuses_a_val_split_without_scenes() -> None:
    manifest = _head_manifest()
    manifest["samples"] = []
    with pytest.raises(CalibrationOperatingPointMeasurementRefused) as refusal:
        _plan(head_dataset_manifest=manifest)
    assert refusal.value.code == CAL_OPERATING_POINT_EVIDENCE_MISSING


def test_plan_refuses_a_seal_without_a_required_search_domain() -> None:
    seal = _geometry_seal()
    del seal["required_search_domain_rad"]
    with pytest.raises(CalibrationOperatingPointMeasurementRefused) as refusal:
        _plan(geometry_seal=seal)
    assert refusal.value.code == CAL_OPERATING_POINT_EVIDENCE_MISSING


def test_plan_refuses_a_partition_whose_calibration_seeds_are_absent() -> None:
    partitions = _partitions()
    partitions["calibration"] = []
    with pytest.raises(CalibrationOperatingPointMeasurementRefused) as refusal:
        _plan(partitions=partitions)
    assert refusal.value.code == CAL_OPERATING_POINT_EVIDENCE_MISSING


def test_plan_seed_limit_keeps_the_declared_order() -> None:
    plan = _plan(seed_limit=2)
    assert len(plan["domains"]["head"]["calibration_episodes"]) == 2
    assert plan["domains"]["head"]["calibration_episodes"][0]["seed"] == 700000
    assert plan["seed_limit"] == 2


def test_truth_from_instances_reads_the_published_mask_first_and_the_polygon_otherwise() -> None:
    # a 4x4 row-major mask whose only lit pixel is flat index 6 -> row 1, column 2
    counts = [6, 1, 9]
    masked = [
        {
            "body_name": "plastic_cup",
            "mask_shape_hw": [4, 4],
            "visible_mask_rle_counts": counts,
            "visible_pixel_count": 1,
            "polygon_xy": [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0]],
        },
        {
            "body_name": "plastic_cup",
            "polygon_xy": [[0.0, 0.0], [0.5, 0.0], [0.5, 0.5]],
            "visible_pixel_count": 4,
        },
    ]
    centres = truth_from_instances(masked, width=4, height=4)
    assert centres[0]["x"] == pytest.approx(2.0)
    assert centres[0]["y"] == pytest.approx(1.0)
    assert centres[0]["truth_source"] == "visible_mask_rle_counts"
    assert centres[1]["truth_source"] == "polygon_xy"
    # the triangle (0,0)-(2,0)-(2,2) in pixels: its area centroid is (4/3, 2/3)
    assert centres[1]["x"] == pytest.approx(4.0 / 3.0)
    assert centres[1]["y"] == pytest.approx(2.0 / 3.0)


def test_static_frame_is_the_record_the_phase_three_metrics_read() -> None:
    sample = _sample(4100001, "head", "one_cup_distractors", 1)
    frame = static_frame(
        domain="head",
        camera_name="head_camera",
        sample=sample,
        truth=_truth(),
        detections=_detections(0.9, [(10.0, 12.0, 30.0, 40.0)]),
        latency_ms={"A": 1.0, "B": 2.0, "C": 3.0},
    )
    assert frame["split"] == "val"
    assert frame["domain"] == "head"
    assert frame["scenario"] == "one_cup_distractors"
    assert frame["seed"] == 4100001
    assert frame["image"] == sample["image"]
    assert sorted(frame["detections"]) == ["A", "B", "C"]
    assert frame["match_radius_px"] == 8.0


def test_episode_frame_refuses_a_scenario_outside_the_declared_classes() -> None:
    with pytest.raises(ValueError):
        episode_frame(
            domain="task",
            camera_name="task_camera",
            seed=700000,
            neck_rad=0.0,
            scenario="",
            split="calibration",
            truth=[],
            detections=_detections(0.9, []),
            latency_ms={"A": 1.0, "B": 1.0, "C": 1.0},
        )
    with pytest.raises(ValueError):
        episode_frame(
            domain="task",
            camera_name="task_camera",
            seed=700000,
            neck_rad=0.0,
            scenario="no_cup",
            split="held_out_evaluation",
            truth=[],
            detections=_detections(0.9, []),
            latency_ms={"A": 1.0, "B": 1.0, "C": 1.0},
        )


def test_the_rule_producer_writes_both_rules_before_any_measurement(tmp_path: Path) -> None:
    measurements = tmp_path / "operating-point-20260101T000000Z"
    result = record_selection_rule_documents(
        production_config=_production_config(),
        measurements_output_dir=measurements,
        output_dir=tmp_path / "rules",
        generation="head-search-runtime",
    )
    head = json.loads((tmp_path / "rules" / RULE_NAME).read_text(encoding="utf-8"))
    task = json.loads((tmp_path / "rules" / TASK_RULE_NAME).read_text(encoding="utf-8"))
    assert head == result["rules"]["head"]
    assert task == result["rules"]["task"]
    for domain, rule in (("head", head), ("task", task)):
        assert rule["kind"] == "head_search_selection_rule"
        assert rule["domain"] == domain
        assert rule["selection_splits"] == ["val", "calibration"]
        assert rule["held_out_splits"] == ["held_out_evaluation"]
        assert rule["recorded_before_measurement"] is True
        assert rule["measurements_admitted"] == 0
        assert rule["points"] == list(operating_point_grid(production_config=_production_config()))
        assert rule["tie_break_chain"] == [
            "highest f1",
            "highest recall",
            "lowest min_confidence",
            "earliest declared grid point",
        ]
        assert rule["rule_sha256"] == canonical_sha256(
            {key: value for key, value in rule.items() if key != "rule_sha256"}
        )
    assert head["rule_sha256"] != task["rule_sha256"]
    receipt = json.loads((tmp_path / "rules" / RECEIPT_NAME).read_text(encoding="utf-8"))
    assert receipt["measurements_output_dir"] == str(measurements)
    assert receipt["measurements_output_dir_existed"] is False
    assert receipt["rule_sha256"] == {"head": head["rule_sha256"], "task": task["rule_sha256"]}


def test_the_rule_producer_refuses_to_write_a_rule_after_its_measurement(tmp_path: Path) -> None:
    measurements = tmp_path / "operating-point-20260101T000000Z"
    measurements.mkdir()
    with pytest.raises(CalibrationOperatingPointMeasurementRefused) as refusal:
        record_selection_rule_documents(
            production_config=_production_config(),
            measurements_output_dir=measurements,
            output_dir=tmp_path / "rules",
        )
    assert refusal.value.code == CAL_RULE_AFTER_MEASUREMENT


def test_the_rule_producer_refuses_an_existing_output_directory(tmp_path: Path) -> None:
    output = tmp_path / "rules"
    output.mkdir()
    with pytest.raises(CalibrationOperatingPointMeasurementRefused) as refusal:
        record_selection_rule_documents(
            production_config=_production_config(),
            measurements_output_dir=tmp_path / "operating-point",
            output_dir=output,
        )
    assert refusal.value.code == CAL_OPERATING_POINT_EVIDENCE_CONTRADICTORY


def test_the_phase_three_module_refuses_a_rule_recorded_after_a_measurement() -> None:
    points = operating_point_grid(production_config=_production_config())
    with pytest.raises(Exception) as refusal:
        record_selection_rule(
            points=points,
            selection_splits=["val", "calibration"],
            held_out_splits=["held_out_evaluation"],
            measurements_admitted=1,
        )
    assert CAL_RULE_AFTER_MEASUREMENT in str(refusal.value)


def test_the_measurement_document_is_what_the_installed_phase_three_consumes(
    tmp_path: Path,
) -> None:
    plan = _plan()
    rules = record_selection_rule_documents(
        production_config=_production_config(),
        measurements_output_dir=tmp_path / "operating-point",
        output_dir=tmp_path / "rules",
    )["rules"]
    frames = _frames_from_plan(plan)
    document = operating_point_measurement_document(
        plan=plan,
        frames=frames,
        rules=rules,
        static_reference={},
        provenance={"toolchain_root": "/toolchain"},
    )
    target = tmp_path / "operating-point-measurements.json"
    target.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    reread = json.loads(target.read_text(encoding="utf-8"))
    assert document["kind"] == "head_search_operating_point_measurements"
    assert len(reread["frames"]) == len(frames)
    assert reread["sha256"] == canonical_sha256(
        {key: value for key, value in reread.items() if key != "sha256"}
    )
    assert list(reread["selection_splits"]) == ["val", "calibration"]
    assert reread["held_out_split"] == "held_out_evaluation"
    # the frames are the phase-3 input, and the installed phase 3 accepts them for every candidate
    for candidate_id in ("A", "B", "C"):
        selection = select_operating_point(
            rule=rules["head"], measurements=reread["frames"], candidate_id=candidate_id
        )
        assert selection["chosen_point"] == {
            "min_confidence": 0.25,
            "min_bbox_aspect": 0.5,
            "min_area_px2": 64.0,
            "tracking_iou": 0.5,
        }
        assert selection["ties_broken_by"] in ("min_confidence", "declared_order")
        assert selection["no_cup_guard"]["clean"] is True
        assert selection["measurements_consumed"]["per_split"] == {"val": 2, "calibration": 12}


def test_the_measurement_document_refuses_frames_of_a_split_the_rule_does_not_select_on(
    tmp_path: Path,
) -> None:
    plan = _plan()
    rules = record_selection_rule_documents(
        production_config=_production_config(),
        measurements_output_dir=tmp_path / "operating-point",
        output_dir=tmp_path / "rules",
    )["rules"]
    frames = _frames_from_plan(plan)
    leaked = dict(frames[0])
    leaked["split"] = "held_out_evaluation"
    with pytest.raises(Exception) as refusal:
        select_operating_point(
            rule=rules["head"], measurements=[leaked, *frames[1:]], candidate_id="C"
        )
    assert CAL_SPLIT_LEAK in str(refusal.value)


def test_toolchain_identity_names_a_build_root_and_leaves_a_source_tree_null(tmp_path: Path) -> None:
    root = tmp_path / "head-toolchain-20260101T000000Z"
    (root / "install" / "so101_demo_py" / "lib" / "python3.12" / "site-packages" / "so101_demo").mkdir(
        parents=True
    )
    (root / "source-commit.txt").write_text("f" * 40 + "\n", encoding="utf-8")
    module = root / "install" / "so101_demo_py" / "lib" / "python3.12" / "site-packages" / "so101_demo" / "__init__.py"
    module.write_text("", encoding="utf-8")
    assert toolchain_identity(module) == {
        "toolchain_root": str(root),
        "source_commit": "f" * 40,
    }
    source = tmp_path / "worktree" / "src" / "so101_demo" / "__init__.py"
    source.parent.mkdir(parents=True)
    source.write_text("", encoding="utf-8")
    assert toolchain_identity(source) == {"toolchain_root": None, "source_commit": None}


def test_the_candidates_and_the_recording_point_are_the_declared_ones() -> None:
    assert CANDIDATE_IDS == ("A", "B", "C")
    assert RECORDING_MIN_CONFIDENCE == 0.25
    assert RECORDING_TRACKING_IOU == 0.7
    settings = recording_settings()
    assert settings["min_confidence"] == RECORDING_MIN_CONFIDENCE
    assert settings["tracking_iou"] == RECORDING_TRACKING_IOU


def test_the_measurement_document_names_the_files_the_run_is_given(tmp_path: Path) -> None:
    assert DOCUMENT_NAME == "operating-point-measurements.json"
    assert RULE_NAME == "selection-rule.json"
    assert TASK_RULE_NAME == "selection-rule-task.json"
    assert RECEIPT_NAME == "operating-point-measurement-receipt.json"
