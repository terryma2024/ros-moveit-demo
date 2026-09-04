from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from so101_demo.adapters.perception.mujoco_dataset import encode_binary_mask_rle
from so101_demo.perception_benchmark.codec import canonical_json_bytes, encode_mask_rle
from so101_demo.perception_benchmark.contracts import MaskRef, RawCandidate
from so101_demo.training.grounded_sam_val_calibration import (
    ValCalibrationError,
    ValDataset,
    ValSample,
    candidate_from_document,
    candidate_to_document,
    collect_val_raw,
    load_locked_val_dataset,
    load_verified_raw_records,
    select_mask_aware_sam_quality_threshold,
    select_sam_quality_threshold,
    write_calibration_evidence,
)

SHA_A = "a" * 64
SHA_B = "b" * 64


def _candidate(mask_path: str, *, quality: float = 0.8, score: float = 0.7) -> RawCandidate:
    return RawCandidate(
        candidate_id="grounded-sam-000",
        label="cup",
        bbox_xyxy=(1.0, 1.0, 9.0, 9.0),
        mask=MaskRef(
            relative_path=mask_path,
            sha256=SHA_A,
            pixel_count=64,
            image_width=16,
            image_height=16,
        ),
        ranking_score=score,
        ranking_score_source="grounding_box_score",
        class_confidence=None,
        grounding_box_score=score,
        grounding_text_score=0.6,
        sam_quality=quality,
    )


def _sample(index: int, scenario: str, boxes=()) -> ValSample:
    return ValSample(
        formal_sample_index=index,
        seed=420000000 + index,
        scenario=scenario,
        configured_cup_count=len(boxes),
        image_path=Path(f"/dataset/images/val/{420000000 + index}.png"),
        image_sha256=SHA_B,
        truths=tuple(boxes),
    )


def test_candidate_document_round_trip_preserves_stable_identity_metadata() -> None:
    candidate = _candidate("benchmark-masks/grounded-sam/collection-000000/mask.json")

    document = candidate_to_document(candidate)
    restored = candidate_from_document(document)

    assert restored == candidate
    assert set(document) == {
        "bbox_xyxy",
        "candidate_id",
        "class_confidence",
        "grounding_box_score",
        "grounding_text_score",
        "label",
        "mask",
        "ranking_score",
        "ranking_score_source",
        "sam_quality",
    }


def test_raw_record_loader_rejects_a_tampered_referenced_mask(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    records = root / "records"
    masks = root / "benchmark-masks/grounded-sam/collection-000000"
    records.mkdir(parents=True)
    masks.mkdir(parents=True)
    mask = np.zeros((16, 16), dtype=bool)
    mask[1:9, 1:9] = True
    mask_path = masks / "grounded-sam-000.coco-rle.json"
    mask_payload = canonical_json_bytes(encode_mask_rle(mask))
    mask_path.write_bytes(mask_payload)
    candidate = _candidate(
        mask_path.relative_to(root).as_posix(),
    )
    record = {
        "schema_version": "so101-grounded-sam-val-raw-record/v1",
        "formal_sample_index": 0,
        "seed": 420000000,
        "scenario": "one_cup_distractors",
        "image_sha256": SHA_B,
        "raw_candidates": [candidate_to_document(candidate)],
        "runtime": {"device": "cuda", "dtype": "float32", "fallback_used": False},
        "irreversible_limits": {
            "box_threshold": 0.01,
            "max_mask_area_ratio": 0.5,
            "min_mask_pixels": 64,
            "sam_quality_floor": 0.0,
            "text_threshold": 0.01,
        },
    }
    payload = canonical_json_bytes(record)
    (records / "000000.json").write_bytes(payload)
    inventory_sha = hashlib.sha256(
        canonical_json_bytes({"record_sha256s": [hashlib.sha256(payload).hexdigest()]})
    ).hexdigest()
    manifest = {
        "schema_version": "so101-grounded-sam-val-raw-run/v1",
        "status": "VALID",
        "run_id": "fixture",
        "source_commit": "c" * 40,
        "val_inventory_sha256": SHA_A,
        "source_manifest_sha256": SHA_B,
        "model_manifest_sha256": "d" * 64,
        "expected_sample_count": 1,
        "record_count": 1,
        "record_inventory_sha256": inventory_sha,
        "inference_error_count": 0,
    }
    (root / "manifest.json").write_bytes(canonical_json_bytes(manifest))
    dataset = ValDataset(
        inventory_sha256=SHA_A,
        source_manifest_sha256=SHA_B,
        samples=(_sample(0, "one_cup_distractors"),),
        scenario_counts={"one_cup_distractors": 1},
    )
    mask_path.write_bytes(canonical_json_bytes(encode_mask_rle(~mask)))

    with pytest.raises(ValCalibrationError, match="RAW_MASK_INVALID"):
        load_verified_raw_records(
            root,
            dataset=dataset,
            expected_model_manifest_sha256="d" * 64,
            expected_source_commit="c" * 40,
        )


def test_frozen_grid_selection_uses_full_pipeline_metrics_and_safety_order() -> None:
    truth = {
        "absolute_xyxy": (1.0, 1.0, 9.0, 9.0),
        "visible_pixel_count": 64,
        "occlusion": None,
    }
    dataset = ValDataset(
        inventory_sha256=SHA_A,
        source_manifest_sha256=SHA_B,
        samples=(
            _sample(0, "small_far_cup", (truth,)),
            _sample(1, "no_cup"),
        ),
        scenario_counts={"no_cup": 1, "small_far_cup": 1},
    )
    records = (
        (_candidate("masks/0.json", quality=0.79),),
        (_candidate("masks/1.json", quality=0.74),),
    )

    selected, points = select_sam_quality_threshold(
        dataset=dataset,
        raw_candidates_by_sample=records,
        quality_grid=("0.70", "0.75", "0.80"),
    )

    assert selected["sam_quality"] == "0.75"
    assert selected["safety_gates"]["no_cup_unique_count"] == 0
    assert selected["totals"] == {"fn": 0, "fp": 0, "tp": 1}
    assert [point["sam_quality"] for point in points] == ["0.70", "0.75", "0.80"]


def test_grid_selection_rejects_unregistered_thresholds() -> None:
    dataset = ValDataset(
        inventory_sha256=SHA_A,
        source_manifest_sha256=SHA_B,
        samples=(_sample(0, "no_cup"),),
        scenario_counts={"no_cup": 1},
    )

    with pytest.raises(ValCalibrationError, match="CALIBRATION_GRID_INVALID"):
        select_sam_quality_threshold(
            dataset=dataset,
            raw_candidates_by_sample=((),),
            quality_grid=("0.51",),
        )


def test_low_grid_selection_requires_truth_mask_iou_and_counts_mask_failure(
    tmp_path: Path,
) -> None:
    truth_mask = np.zeros((16, 16), dtype=bool)
    truth_mask[1:9, 1:9] = True
    failed_mask = np.zeros((16, 16), dtype=bool)
    failed_mask[8:16, 8:16] = True
    truth = {
        "absolute_xyxy": (1.0, 1.0, 9.0, 9.0),
        "visible_pixel_count": 64,
        "occlusion": None,
        "mask": truth_mask,
    }
    dataset = ValDataset(
        inventory_sha256=SHA_A,
        source_manifest_sha256=SHA_B,
        samples=(
            _sample(0, "small_far_cup", (truth,)),
            _sample(1, "two_cups", (truth,)),
        ),
        scenario_counts={"small_far_cup": 1, "two_cups": 1},
    )

    def stored_candidate(name: str, mask: np.ndarray) -> RawCandidate:
        path = tmp_path / name
        path.write_bytes(canonical_json_bytes(encode_mask_rle(mask)))
        return replace(
            _candidate(name, quality=0.15),
            mask=MaskRef(
                relative_path=name,
                sha256=hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest(),
                pixel_count=int(mask.sum()),
                image_width=16,
                image_height=16,
            ),
        )

    selected, points = select_mask_aware_sam_quality_threshold(
        dataset=dataset,
        raw_candidates_by_sample=(
            (stored_candidate("good.json", truth_mask),),
            (stored_candidate("bad.json", failed_mask),),
        ),
        raw_evidence_root=tmp_path,
        quality_grid=("0.00", "0.10", "0.20"),
    )

    assert selected["sam_quality"] == "0.10"
    assert selected["totals"] == {"fn": 1, "fp": 1, "tp": 1}
    assert selected["mask_metrics"]["pass_count"] == 1
    assert selected["mask_metrics"]["fail_count"] == 1
    assert selected["small_far_recall"] == 1.0
    assert selected["multi_cup_recall"] == 0.0
    assert [point["sam_quality"] for point in points] == ["0.00", "0.10", "0.20"]


def test_val_loader_binds_inventory_and_only_val_members(tmp_path: Path) -> None:
    source = tmp_path / "source"
    inventory_root = tmp_path / "converted/val"
    image = source / "images/val/420000000.png"
    label = source / "labels/val/420000000.txt"
    truth = source / "truth/val/420000000.json"
    image.parent.mkdir(parents=True)
    label.parent.mkdir(parents=True)
    truth.parent.mkdir(parents=True)
    from PIL import Image

    Image.fromarray(np.zeros((16, 16, 3), dtype=np.uint8)).save(image)
    label.write_text("0 0.133333333 0.133333333 0.6 0.133333333 0.6 0.6 0.133333333 0.6\n")
    visible_mask = np.zeros((16, 16), dtype=bool)
    visible_mask[2:6, 2:6] = True
    visible_mask[8:10, 8:10] = True
    truth.write_bytes(
        canonical_json_bytes(
            {
                "configured_cup_count": 1,
                "instances": [
                    {
                        "body_id": 4,
                        "body_name": "plastic_cup",
                        "mask_shape_hw": [16, 16],
                        "occlusion_measured": False,
                        "occlusion_state": "unmeasured",
                        "polygon_xy": [
                            [2.0 / 15.0, 2.0 / 15.0],
                            [0.6, 2.0 / 15.0],
                            [0.6, 0.6],
                            [2.0 / 15.0, 0.6],
                        ],
                        "visible_mask_rle_counts": list(encode_binary_mask_rle(visible_mask)),
                        "visible_mask_sha256": hashlib.sha256(
                            visible_mask.astype(np.uint8).tobytes(order="C")
                        ).hexdigest(),
                        "visible_pixel_count": 20,
                    }
                ],
                "scenario": "small_far_cup",
                "seed": 420000000,
                "split": "val",
                "visible_instance_count": 1,
            }
        )
    )
    manifest = source / "dataset-manifest.json"
    manifest.write_bytes(b"immutable-source-manifest\n")
    inventory_root.mkdir(parents=True)
    inventory = {
        "class_name": "cup",
        "converter_commit": "c" * 40,
        "image_height": 16,
        "image_width": 16,
        "prompt": "cup.",
        "sample_count": 1,
        "samples": [
            {
                "boxes": [
                    {
                        "absolute_xyxy": [2.0, 2.0, 9.0, 9.0],
                        "class_name": "cup",
                        "normalized_xyxy": [2.0 / 15.0, 2.0 / 15.0, 0.6, 0.6],
                        "occlusion": None,
                        "text": "cup.",
                        "visible_pixel_count": 20,
                    }
                ],
                "configured_cup_count": 1,
                "image_relpath": "images/val/420000000.png",
                "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                "label_relpath": "labels/val/420000000.txt",
                "label_sha256": hashlib.sha256(label.read_bytes()).hexdigest(),
                "scenario": "small_far_cup",
                "seed": 420000000,
                "truth_relpath": "truth/val/420000000.json",
                "truth_sha256": hashlib.sha256(truth.read_bytes()).hexdigest(),
                "visible_instance_count": 1,
            }
        ],
        "schema_version": 1,
        "source_archive_sha256": "a" * 64,
        "source_generator_commit": "d" * 40,
        "source_manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
        "source_mjcf_sha256": "b" * 64,
        "split": "val",
    }
    inventory_path = inventory_root / "inventory.json"
    inventory_path.write_bytes(canonical_json_bytes(inventory))
    expected_inventory_sha = hashlib.sha256(inventory_path.read_bytes()).hexdigest()
    for path in (image, label, truth, manifest, inventory_path):
        path.chmod(0o444)
    for path in sorted(source.rglob("*"), reverse=True):
        if path.is_dir():
            path.chmod(0o555)
    source.chmod(0o555)
    inventory_root.chmod(0o555)

    loaded = load_locked_val_dataset(
        inventory_path=inventory_path,
        expected_inventory_sha256=expected_inventory_sha,
        source_root=source,
        expected_source_manifest_sha256=inventory["source_manifest_sha256"],
    )

    assert len(loaded.samples) == 1
    assert loaded.samples[0].scenario == "small_far_cup"
    assert loaded.samples[0].truths[0]["visible_pixel_count"] == 20
    assert np.array_equal(loaded.samples[0].truths[0]["mask"], visible_mask)
    assert loaded.samples[0].truths[0]["absolute_xyxy"] == (2.0, 2.0, 9.0, 9.0)


def test_calibration_evidence_is_exclusive_and_hash_bound(tmp_path: Path) -> None:
    dataset = ValDataset(
        inventory_sha256=SHA_A,
        source_manifest_sha256=SHA_B,
        samples=(_sample(0, "no_cup"),),
        scenario_counts={"no_cup": 1},
    )
    output = tmp_path / "calibration"

    report = write_calibration_evidence(
        output_root=output,
        dataset=dataset,
        raw_run_root=tmp_path / "raw",
        raw_manifest_sha256="c" * 64,
        source_commit="d" * 40,
        selected={
            "sam_quality": "0.90",
            "totals": {"fn": 0, "fp": 0, "tp": 0},
            "precision": 0.0,
            "recall": 0.0,
            "f1": 0.0,
            "small_far_recall": 0.0,
            "multi_cup_recall": 0.0,
            "decision_counts": {"NOT_FOUND": 1},
            "scenario_metrics": {"no_cup": {"fn": 0, "fp": 0, "images": 1, "tp": 0}},
            "safety_gates": {"no_cup_unique_count": 0},
        },
        points=(),
    )

    assert report["selected_sam_quality"] == "0.90"
    assert json.loads((output / "manifest.json").read_text())["status"] == "VALID"
    with pytest.raises(ValCalibrationError, match="OUTPUT_ROOT_ALREADY_EXISTS"):
        write_calibration_evidence(
            output_root=output,
            dataset=dataset,
            raw_run_root=tmp_path / "raw",
            raw_manifest_sha256="c" * 64,
            source_commit="d" * 40,
            selected=report,
            points=(),
        )


def test_raw_collection_persists_complete_candidate_metadata(tmp_path: Path) -> None:
    image = tmp_path / "sample.png"
    from PIL import Image

    Image.fromarray(np.zeros((16, 16, 3), dtype=np.uint8)).save(image)
    sample = ValSample(
        formal_sample_index=0,
        seed=420000000,
        scenario="small_far_cup",
        configured_cup_count=1,
        image_path=image,
        image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(),
        truths=(),
    )
    dataset = ValDataset(
        inventory_sha256=SHA_A,
        source_manifest_sha256=SHA_B,
        samples=(sample,),
        scenario_counts={"small_far_cup": 1},
    )
    output = tmp_path / "raw"
    mask = np.zeros((16, 16), dtype=bool)
    mask[1:9, 1:9] = True

    class FakeAdapter:
        model_id = "grounding-dino-tiny+sam2.1-hiera-tiny"
        runtime_device = "cuda"

        def collect(self, frame, mode):
            target = output / "benchmark-masks/grounded-sam/collection-000000/mask.json"
            target.parent.mkdir(parents=True)
            target.write_bytes(canonical_json_bytes(encode_mask_rle(mask)))
            candidate = _candidate(target.relative_to(output).as_posix())
            candidate = replace(
                candidate,
                mask=replace(
                    candidate.mask,
                    sha256=hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest(),
                ),
            )
            return SimpleNamespace(
                model_id=self.model_id,
                runtime_device="cuda",
                dtype="float32",
                collection_mode=mode,
                fallback_used=False,
                raw_candidates=(candidate,),
                irreversible_limits={
                    "box_threshold": 0.01,
                    "text_threshold": 0.01,
                    "sam_quality_floor": 0.0,
                    "min_mask_pixels": 64,
                    "max_mask_area_ratio": 0.5,
                },
            )

    manifest = collect_val_raw(
        dataset=dataset,
        adapter=FakeAdapter(),
        output_root=output,
        run_id="fixture-raw",
        source_commit="c" * 40,
        model_manifest_sha256="d" * 64,
    )

    assert manifest["status"] == "VALID"
    assert manifest["record_count"] == 1
    record = json.loads((output / "records/000000.json").read_text())
    assert record["raw_candidates"][0]["grounding_box_score"] == 0.7
    assert load_verified_raw_records(
        output,
        dataset=dataset,
        expected_model_manifest_sha256="d" * 64,
        expected_source_commit="c" * 40,
    )[0][0].candidate_id == "grounded-sam-000"
