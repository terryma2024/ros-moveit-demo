import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from so101_demo.cli.evaluate_grounded_sam_frozen_candidate import (
    main as evaluate_main,
)
from so101_demo.core.detection import DetectionBatch, DetectionCandidate
from so101_demo.perception_benchmark.codec import encode_mask_rle
from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    MaskRef,
    RawCandidate,
)
from so101_demo.training.frozen_candidate_evaluation import (
    FrozenCandidateError,
    FrozenSyntheticTest,
    evaluate_frozen_synthetic_test,
    initialize_evaluation_output,
    load_locked_synthetic_test,
    map_production_candidates,
    verify_frozen_candidate_lock,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64
COMMIT_A = "1" * 40
COMMIT_B = "2" * 40


def _canonical(document: dict) -> bytes:
    return (
        json.dumps(document, ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
    ).encode("utf-8")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def _lock_document(bundle: Path, seal: Path, source_manifest_sha: str) -> dict:
    detector_sha = _sha(bundle / "grounding-dino-tiny/model.safetensors")
    sam_sha = _sha(bundle / "sam2.1-hiera-tiny/model.safetensors")
    document = {
        "schema_version": "so101-grounded-sam-frozen-candidate/v1",
        "pipeline_id": "grounding-dino-tiny+sam2.1-hiera-tiny",
        "code": {
            "creation_commit": COMMIT_A,
            "gated_implementation_commit": COMMIT_B,
        },
        "model_bundle": {
            "root": str(bundle),
            "manifest_sha256": SHA_A,
            "detector_model_sha256": detector_sha,
            "detector_checkpoint_manifest_sha256": SHA_B,
            "sam_model_id": "facebook/sam2.1-hiera-tiny",
            "sam_revision": "de431c4043854a71d8101e17995dfe596bf101a5",
            "sam_transformers_model_sha256": sam_sha,
            "sam_source_bundle_manifest_sha256": SHA_C,
        },
        "prompt_profile": {"cup": "cup."},
        "thresholds": {
            "raw_collection": {
                "box_threshold": "0.01",
                "text_threshold": "0.01",
                "sam_quality_threshold": "0.00",
                "selector": "off",
                "maximum_candidates": 300,
            },
            "production": {
                "box_threshold": "0.25",
                "text_threshold": "0.25",
                "sam_quality_threshold": "0.90",
                "selector_minimum_confidence": "0.25",
                "duplicate_iou_threshold": "0.85",
                "minimum_mask_pixels": 64,
                "maximum_mask_area_ratio": "0.50",
                "maximum_candidates": 16,
            },
            "production_candidate_mask_iou_threshold": "0.98",
        },
        "selector": {
            "implementation": "so101_demo.application.object_pose.TargetSelector",
            "query_class": "cup",
            "eligible_cardinality": "exactly_one",
            "zero_result": "TARGET_NOT_FOUND",
            "multiple_results": "TARGET_AMBIGUOUS",
        },
        "sam_runtime_contract": {
            "weights": "frozen",
            "state": "stateless_per_frame",
            "prompt_source": "current_frame_dino_box_only",
        },
        "threshold_provenance": {
            "dino_box_text": "synthetic_val_epoch_7_checkpoint_manifest",
            "frozen_sam_geometry_filters": "unchanged_formal_grounded_sam_lock",
            "source_threshold_lock_sha256": SHA_A,
            "sealed_test_tuning": False,
            "coco100_tuning": False,
        },
        "synthetic_test_seal": {
            "source_archive_sha256": SHA_A,
            "source_manifest_sha256": source_manifest_sha,
            "converted_sealed_members_sha256": _sha(seal),
            "sample_count": 1,
            "seed_range": [300, 300],
            "scenario_quotas": {"no_cup": 1},
        },
    }
    document["lock_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    return document


def _locked_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    bundle = tmp_path / "bundle"
    _write(bundle / "manifest.json", b"bundle-manifest\n")
    _write(bundle / "grounding-dino-tiny/model.safetensors", b"detector")
    _write(bundle / "sam2.1-hiera-tiny/model.safetensors", b"sam")
    source = tmp_path / "source"
    source_manifest = source / "dataset-manifest.json"
    _write(source_manifest, b"source-manifest\n")
    seal = tmp_path / "test-sealed-members.json"
    _write(seal, _canonical({"sealed": True, "samples": []}))
    lock_path = tmp_path / "threshold-lock.json"
    _write(lock_path, _canonical(_lock_document(bundle, seal, _sha(source_manifest))))
    lock_path.chmod(0o444)
    monkeypatch.setattr(
        "so101_demo.training.frozen_candidate_evaluation.verify_model_bundle",
        lambda root, expected: SimpleNamespace(
            root=root,
            manifest_sha256=expected,
            target_class_id="cup",
            prompt="cup.",
        ),
    )
    return lock_path, source, seal


def test_candidate_lock_verifies_canonical_digest_and_external_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path, _, _ = _locked_fixture(tmp_path, monkeypatch)

    lock = verify_frozen_candidate_lock(lock_path, _sha(lock_path))

    assert lock.lock_sha256 == json.loads(lock_path.read_text())["lock_sha256"]
    assert lock.document["prompt_profile"] == {"cup": "cup."}
    tampered = json.loads(lock_path.read_text())
    tampered["thresholds"]["production"]["box_threshold"] = "0.30"
    lock_path.chmod(0o644)
    lock_path.write_bytes(_canonical(tampered))
    with pytest.raises(FrozenCandidateError, match="LOCK_FILE_SHA256_MISMATCH"):
        verify_frozen_candidate_lock(lock_path, lock.file_sha256)


def test_test_loader_rejects_member_hash_before_parsing_annotation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path, source, seal = _locked_fixture(tmp_path, monkeypatch)
    image = source / "images/test/000000300.png"
    label = source / "labels/test/000000300.txt"
    truth = source / "truth/test/000000300.json"
    _write(image, b"image")
    _write(label, b"not a label")
    _write(truth, b"not json")
    seal_document = {
        "converter_commit": COMMIT_A,
        "sample_count": 1,
        "samples": [
            {
                "image_relpath": "images/test/000000300.png",
                "label_relpath": "labels/test/000000300.txt",
                "truth_relpath": "truth/test/000000300.json",
                "image_sha256": SHA_A,
                "label_sha256": _sha(label),
                "truth_sha256": _sha(truth),
            }
        ],
        "schema_version": 1,
        "sealed": True,
        "source_archive_sha256": SHA_A,
        "source_manifest_sha256": _sha(source / "dataset-manifest.json"),
        "split": "test",
    }
    seal.write_bytes(_canonical(seal_document))
    lock_path.chmod(0o644)
    lock_path.write_bytes(
        _canonical(
            _lock_document(
                lock_path.parent / "bundle", seal, _sha(source / "dataset-manifest.json")
            )
        )
    )
    lock_path.chmod(0o444)
    lock = verify_frozen_candidate_lock(lock_path, _sha(lock_path))
    for path in (image, label, truth, source / "dataset-manifest.json", seal):
        path.chmod(0o444)
    source.chmod(0o555)

    with pytest.raises(FrozenCandidateError, match="SEALED_MEMBER_SHA256_MISMATCH"):
        load_locked_synthetic_test(
            lock=lock,
            source_root=source,
            sealed_members_path=seal,
        )


def test_test_loader_rejects_a_mutable_source_before_annotation_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path, source, seal = _locked_fixture(tmp_path, monkeypatch)
    lock = verify_frozen_candidate_lock(lock_path, _sha(lock_path))

    with pytest.raises(FrozenCandidateError, match="TEST_SOURCE_MUTABLE"):
        load_locked_synthetic_test(
            lock=lock,
            source_root=source,
            sealed_members_path=seal,
        )


def test_test_loader_accepts_a_complete_hash_bound_no_cup_sample(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path, source, seal = _locked_fixture(tmp_path, monkeypatch)
    image = source / "images/test/000000300.png"
    label = source / "labels/test/000000300.txt"
    truth = source / "truth/test/000000300.json"
    from PIL import Image

    image.parent.mkdir(parents=True)
    Image.fromarray(np.zeros((8, 8, 3), dtype=np.uint8)).save(image)
    _write(label, b"")
    _write(
        truth,
        _canonical(
            {
                "configured_cup_count": 0,
                "instances": [],
                "scenario": "no_cup",
                "seed": 300,
                "split": "test",
                "visible_instance_count": 0,
            }
        ),
    )
    _write(
        source / "dataset.yaml",
        b"path: .\ntrain: images/train\nval: images/val\ntest: images/test\n"
        b"names:\n  0: plastic_cup\n",
    )
    sample = {
        "configured_cup_count": 0,
        "image": "images/test/000000300.png",
        "label": "labels/test/000000300.txt",
        "scenario": "no_cup",
        "seed": 300,
        "split": "test",
        "truth": "truth/test/000000300.json",
        "visible_instance_count": 0,
    }
    manifest = {
        "artifacts": [
            "dataset.yaml",
            "images/test/000000300.png",
            "labels/test/000000300.txt",
            "truth/test/000000300.json",
        ],
        "camera_name": "task_camera",
        "class_instance_totals": {"plastic_cup": 0},
        "generator_commit": COMMIT_A,
        "image_height": 8,
        "image_width": 8,
        "mjcf_sha256": SHA_B,
        "sample_count": 1,
        "samples": [sample],
        "schema_version": 1,
        "seed_ranges": {"test": [300, 300], "train": [], "val": []},
        "seed_starts": {"test": 300, "train": 100, "val": 200},
        "split_counts": {"test": 1, "train": 0, "val": 0},
    }
    (source / "dataset-manifest.json").write_bytes(_canonical(manifest))
    seal_document = {
        "converter_commit": COMMIT_A,
        "sample_count": 1,
        "samples": [
            {
                "image_relpath": sample["image"],
                "image_sha256": _sha(image),
                "label_relpath": sample["label"],
                "label_sha256": _sha(label),
                "truth_relpath": sample["truth"],
                "truth_sha256": _sha(truth),
            }
        ],
        "schema_version": 1,
        "sealed": True,
        "source_archive_sha256": SHA_A,
        "source_manifest_sha256": _sha(source / "dataset-manifest.json"),
        "split": "test",
    }
    seal.write_bytes(_canonical(seal_document))
    lock_path.chmod(0o644)
    lock_path.write_bytes(
        _canonical(
            _lock_document(
                lock_path.parent / "bundle",
                seal,
                _sha(source / "dataset-manifest.json"),
            )
        )
    )
    lock_path.chmod(0o444)
    for path in (
        image,
        label,
        truth,
        source / "dataset.yaml",
        source / "dataset-manifest.json",
        seal,
    ):
        path.chmod(0o444)
    source.chmod(0o555)

    loaded = load_locked_synthetic_test(
        lock=verify_frozen_candidate_lock(lock_path, _sha(lock_path)),
        source_root=source,
        sealed_members_path=seal,
    )

    assert loaded.scenario_counts == {"no_cup": 1}
    assert len(loaded.samples) == 1
    assert loaded.samples[0]["seed"] == 300
    assert loaded.samples[0]["boxes"] == ()


def _raw_candidate(
    mask_path: Path,
    mask: np.ndarray,
    *,
    bbox_xyxy: tuple[float, float, float, float] = (1.0, 1.0, 3.0, 3.0),
) -> RawCandidate:
    _write(mask_path, _canonical({"unused": True}))
    return RawCandidate(
        candidate_id="raw-0",
        label="cup",
        bbox_xyxy=bbox_xyxy,
        mask=MaskRef(
            relative_path="raw-mask.json",
            sha256=hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest(),
            pixel_count=int(mask.sum()),
            image_width=mask.shape[1],
            image_height=mask.shape[0],
        ),
        ranking_score=0.8,
        ranking_score_source="grounding_box_score",
        class_confidence=None,
        grounding_box_score=0.8,
        grounding_text_score=0.7,
        sam_quality=0.9,
    )


def _production_candidate(
    mask: np.ndarray,
    *,
    stamp: int = 1,
    bbox_xyxy: tuple[float, float, float, float] = (1.0, 1.0, 3.0, 3.0),
) -> DetectionCandidate:
    return DetectionCandidate(
        instance_id="production-0",
        class_id="cup",
        confidence=0.8,
        bbox_xyxy=bbox_xyxy,
        mask=mask,
        source_stamp_ns=stamp,
        source_frame_id="synthetic_test_camera",
        image_width=mask.shape[1],
        image_height=mask.shape[0],
        segmentation_quality=0.9,
    )


def test_production_mapping_requires_unique_mask_iou_at_least_098(tmp_path: Path) -> None:
    raw_mask = np.ones((4, 4), dtype=bool)
    raw = _raw_candidate(tmp_path / "raw-mask.json", raw_mask)
    production = _production_candidate(raw_mask.copy())

    assert map_production_candidates(
        raw_candidates=(raw,),
        production_candidates=(production,),
        raw_mask_loader=lambda _: raw_mask,
        minimum_mask_iou=0.98,
    ) == {"production-0": "raw-0"}

    low_iou_mask = raw_mask.copy()
    low_iou_mask[0, 0] = False
    with pytest.raises(FrozenCandidateError, match="PRODUCTION_CANDIDATE_MAPPING_INVALID"):
        map_production_candidates(
            raw_candidates=(raw,),
            production_candidates=(_production_candidate(low_iou_mask),),
            raw_mask_loader=lambda _: raw_mask,
            minimum_mask_iou=0.98,
        )


def test_one_sample_evaluation_persists_production_mask_and_safety_report(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    lock_path, _, _ = _locked_fixture(tmp_path, monkeypatch)
    document = json.loads(lock_path.read_text())
    document.pop("lock_sha256")
    document["synthetic_test_seal"]["scenario_quotas"] = {"one_cup_distractors": 1}
    document["lock_sha256"] = hashlib.sha256(_canonical(document)).hexdigest()
    lock_path.chmod(0o644)
    lock_path.write_bytes(_canonical(document))
    lock_path.chmod(0o444)
    lock = verify_frozen_candidate_lock(lock_path, _sha(lock_path))
    output_root = tmp_path / "evaluation"
    access_sha = initialize_evaluation_output(
        output_root=output_root,
        lock=lock,
        run_id="synthetic-test-fixture",
        source_commit=COMMIT_A,
    )
    mask = np.zeros((16, 16), dtype=bool)
    mask[4:12, 4:12] = True
    bbox = (4.0, 4.0, 12.0, 12.0)
    raw = _raw_candidate(output_root / "raw-mask.json", mask, bbox_xyxy=bbox)
    (output_root / "raw-mask.json").write_bytes(_canonical(encode_mask_rle(mask)))
    production = _production_candidate(mask.copy(), stamp=300, bbox_xyxy=bbox)
    batch = DetectionBatch(
        model_id="grounding-dino-tiny+sam2.1-hiera-tiny",
        weights_sha256=lock.document["model_bundle"]["manifest_sha256"],
        runtime_device="cuda",
        inference_latency_ms=1.0,
        image_width=16,
        image_height=16,
        candidates=(production,),
    )
    raw_result = SimpleNamespace(
        model_id="grounding-dino-tiny+sam2.1-hiera-tiny",
        runtime_device="cuda",
        dtype="float32",
        collection_mode="LOW_FLOOR",
        fallback_used=False,
        raw_candidates=(raw,),
        irreversible_limits={
            "box_threshold": 0.01,
            "text_threshold": 0.01,
            "sam_quality_floor": 0.0,
            "min_mask_pixels": 64,
            "max_mask_area_ratio": 0.5,
        },
    )
    raw_adapter = SimpleNamespace(collect=lambda frame, mode: raw_result)
    observation = SimpleNamespace(
        decision=DecisionOutput.UNIQUE,
        batch=batch,
        selected_candidate_id="production-0",
        rejection_reason=None,
        error_type=None,
        error_summary=None,
    )
    image_path = tmp_path / "sample.png"
    from PIL import Image

    Image.fromarray(np.zeros((16, 16, 3), dtype=np.uint8)).save(image_path)
    truth_mask = mask.copy()
    truth_mask.setflags(write=False)
    dataset = FrozenSyntheticTest(
        samples=(
            {
                "seed": 300,
                "scenario": "one_cup_distractors",
                "configured_cup_count": 1,
                "visible_instance_count": 1,
                "image_path": image_path,
                "image_sha256": _sha(image_path),
                "boxes": (
                    {
                        "absolute_xyxy": bbox,
                        "normalized_xyxy": (0.25, 0.25, 0.75, 0.75),
                        "visible_pixel_count": 64,
                        "occlusion": None,
                        "mask": truth_mask,
                    },
                ),
            },
        ),
        scenario_counts={"one_cup_distractors": 1},
    )

    report = evaluate_frozen_synthetic_test(
        dataset=dataset,
        lock=lock,
        output_root=output_root,
        raw_adapter=raw_adapter,
        production_observer=lambda frame: observation,
        source_commit=COMMIT_A,
        run_id="synthetic-test-fixture",
    )

    assert access_sha == json.loads((output_root / "access-event.json").read_text())["event_sha256"]
    assert report["safety_passed"] is True
    assert report["totals"] == {"fn": 0, "fp": 0, "tp": 1}
    assert report["safety_gates"]["mapping_errors"] == 0
    assert report["safety_gates"]["missing_production_masks"] == 0
    assert report["strata_metrics"]["single_cup"]["tp"] == 1
    assert report["occlusion_recall"] == {"matched": 0, "recall": 0.0, "truth": 0}
    assert len(tuple((output_root / "production-masks").rglob("*.json"))) == 1
    assert json.loads((output_root / "manifest.json").read_text())["status"] == "VALID"


def test_evaluation_output_is_exclusive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lock_path, _, _ = _locked_fixture(tmp_path, monkeypatch)
    lock = verify_frozen_candidate_lock(lock_path, _sha(lock_path))
    output_root = tmp_path / "evaluation"
    initialize_evaluation_output(
        output_root=output_root,
        lock=lock,
        run_id="first",
        source_commit=COMMIT_A,
    )

    with pytest.raises(FrozenCandidateError, match="OUTPUT_ROOT_ALREADY_EXISTS"):
        initialize_evaluation_output(
            output_root=output_root,
            lock=lock,
            run_id="second",
            source_commit=COMMIT_A,
        )


def test_cli_initializes_access_before_loading_test_and_returns_safety_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lock_path, source, seal = _locked_fixture(tmp_path, monkeypatch)
    output_root = tmp_path / "evaluation"
    dataset = FrozenSyntheticTest(samples=(), scenario_counts={})
    events: list[str] = []

    def load_after_access(**kwargs):
        assert kwargs["source_root"] == source
        assert kwargs["sealed_members_path"] == seal
        assert (output_root / "access-event.json").is_file()
        events.append("load")
        return dataset

    monkeypatch.setattr(
        "so101_demo.cli.evaluate_grounded_sam_frozen_candidate.load_locked_synthetic_test",
        load_after_access,
    )
    monkeypatch.setattr(
        "so101_demo.cli.evaluate_grounded_sam_frozen_candidate._build_runtime",
        lambda lock, evidence_root: ("raw", "production"),
    )
    monkeypatch.setattr(
        "so101_demo.cli.evaluate_grounded_sam_frozen_candidate.run_production_detector_port",
        lambda detector, frame, selector_threshold: (detector, frame),
    )

    def evaluate(**kwargs):
        assert kwargs["dataset"] is dataset
        assert kwargs["raw_adapter"] == "raw"
        assert kwargs["production_observer"]("frame") == (
            "production",
            "frame",
        )
        events.append("evaluate")
        return {"safety_passed": True}

    monkeypatch.setattr(
        "so101_demo.cli.evaluate_grounded_sam_frozen_candidate.evaluate_frozen_synthetic_test",
        evaluate,
    )

    result = evaluate_main(
        [
            "--candidate-lock",
            str(lock_path),
            "--candidate-lock-sha256",
            _sha(lock_path),
            "--source-root",
            str(source),
            "--sealed-members",
            str(seal),
            "--output-root",
            str(output_root),
            "--source-commit",
            COMMIT_A,
            "--run-id",
            "formal-fixture",
        ]
    )

    assert result == 0
    assert events == ["load", "evaluate"]
    assert json.loads(capsys.readouterr().out)["status"] == "VALID"


def test_cli_marks_initialized_output_invalid_when_runtime_setup_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    lock_path, source, seal = _locked_fixture(tmp_path, monkeypatch)
    output_root = tmp_path / "evaluation"
    monkeypatch.setattr(
        "so101_demo.cli.evaluate_grounded_sam_frozen_candidate.load_locked_synthetic_test",
        lambda **kwargs: FrozenSyntheticTest(samples=(), scenario_counts={}),
    )

    def fail_runtime(lock, evidence_root):
        raise FrozenCandidateError("DEVICE_MISMATCH", "fixture")

    monkeypatch.setattr(
        "so101_demo.cli.evaluate_grounded_sam_frozen_candidate._build_runtime",
        fail_runtime,
    )

    result = evaluate_main(
        [
            "--candidate-lock",
            str(lock_path),
            "--candidate-lock-sha256",
            _sha(lock_path),
            "--source-root",
            str(source),
            "--sealed-members",
            str(seal),
            "--output-root",
            str(output_root),
            "--source-commit",
            COMMIT_A,
            "--run-id",
            "failed-fixture",
        ]
    )

    assert result == 1
    assert json.loads((output_root / "manifest.json").read_text())["status"] == "INVALID"
    assert json.loads((output_root / "failure.json").read_text())["code"] == ("DEVICE_MISMATCH")
    assert json.loads(capsys.readouterr().out)["status"] == "ERROR"
