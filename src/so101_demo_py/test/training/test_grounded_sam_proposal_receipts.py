from __future__ import annotations

import hashlib
import importlib
import json
from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image
from so101_demo.core.detection import DetectionFrame
from so101_demo.perception_benchmark.adapters.base import CollectionMode
from so101_demo.training.grounded_sam_val_calibration import ValDataset, ValSample

SOURCE = "c" * 40
MODEL = "d" * 64
PROPOSALS = (((1.0, 1.0, 8.0, 8.0), 0.9, 0.8), ((2.0, 2.0, 9.0, 9.0), 0.7, 0.6))


def _module():
    return importlib.import_module("so101_demo.training.grounded_sam_proposal_receipts")


def _inputs(tmp_path):
    rgb = np.zeros((16, 16, 3), dtype=np.uint8)
    path = tmp_path / "image.png"
    Image.fromarray(rgb).save(path)
    sample = ValSample(
        0, 420000000, "two_cups", 2, path, hashlib.sha256(path.read_bytes()).hexdigest(), ()
    )
    dataset = ValDataset("a" * 64, "b" * 64, (sample,), {"two_cups": 1})
    frame = DetectionFrame(rgb, sample.seed, "synthetic_val_camera")
    return dataset, frame


def _candidate(index=1):
    bbox, score, text = PROPOSALS[index]
    return SimpleNamespace(
        candidate_id=f"grounded-sam-{index:03d}",
        label="cup",
        bbox_xyxy=bbox,
        grounding_box_score=score,
        grounding_text_score=text,
    )


def _adapter(
    tmp_path,
    *,
    proposals=PROPOSALS,
    behavior="normal",
    candidates=None,
    device="cuda",
    identity=None,
):
    module = _module()
    dataset, frame = _inputs(tmp_path)
    root = tmp_path / "raw"
    root.mkdir()
    events = []

    def factory(observer):
        def collect(actual_frame, mode):
            events.append("dino")
            if behavior != "missing":
                observer(proposals)
                # Persistence must happen before the simulated SAM forward.
                assert (root / "proposal-receipts/000000.json").is_file()
            if behavior == "duplicate":
                observer(proposals)
            if behavior == "swallowed_duplicate":
                try:
                    observer(proposals)
                except ValueError:
                    pass
            events.append("sam")
            return SimpleNamespace(
                raw_candidates=tuple([_candidate()] if candidates is None else candidates)
            )

        return SimpleNamespace(
            model_id="grounding-dino-tiny+sam2.1-hiera-tiny", runtime_device=device, collect=collect
        )

    kwargs = dict(
        dataset=dataset,
        evidence_root=root,
        source_commit=SOURCE,
        model_manifest_sha256=MODEL,
        adapter_factory=factory,
    )
    kwargs.update(identity or {})
    wrapper = module.ProposalReceiptAdapter(**kwargs)
    return module, wrapper, dataset, frame, root, events


def test_receipts_retain_proposal_rejected_by_sam_and_bind_image_identity(tmp_path):
    module, wrapper, dataset, frame, root, events = _adapter(tmp_path)
    result = wrapper.collect(frame, CollectionMode.LOW_FLOOR)
    manifest = wrapper.finalize()
    path = root / "proposal-receipts/000000.json"
    receipt = json.loads(path.read_text())
    assert [p["candidate_id"] for p in receipt["proposals"]] == [
        "grounded-sam-000",
        "grounded-sam-001",
    ]
    assert receipt["proposals"][0]["grounding_box_score"] == 0.9
    assert receipt["image_sha256"] == dataset.samples[0].image_sha256
    assert receipt["rgb_sha256"] == hashlib.sha256(bytes(16 * 16 * 3)).hexdigest()
    assert receipt["source_stamp_ns"] == 420000000
    assert receipt["prompt"] == "cup."
    assert receipt["model_manifest_sha256"] == MODEL
    assert manifest["receipt_sha256s"] == [hashlib.sha256(path.read_bytes()).hexdigest()]
    retained = module.load_verified_proposal_receipts(
        root,
        dataset=dataset,
        expected_source_commit=SOURCE,
        expected_model_manifest_sha256=MODEL,
        raw_candidates_by_sample=(result.raw_candidates,),
    )
    assert len(retained) == 1 and len(retained[0]) == 2
    assert retained[0][0].bbox_xyxy == (1.0, 1.0, 8.0, 8.0)
    assert events == ["dino", "sam"]


def test_empty_frame_requires_explicit_receipt(tmp_path):
    _, wrapper, _, frame, root, _ = _adapter(tmp_path, proposals=(), candidates=[])
    wrapper.collect(frame, CollectionMode.LOW_FLOOR)
    assert wrapper.finalize()["receipt_count"] == 1
    assert json.loads((root / "proposal-receipts/000000.json").read_text())["proposals"] == []


@pytest.mark.parametrize("behavior", ["missing", "duplicate", "swallowed_duplicate"])
def test_missing_or_duplicate_observer_poison_run(tmp_path, behavior):
    _, wrapper, _, frame, root, _ = _adapter(tmp_path, behavior=behavior)
    with pytest.raises(ValueError, match="PROPOSAL_RECEIPT"):
        wrapper.collect(frame, CollectionMode.LOW_FLOOR)
    with pytest.raises(ValueError, match="PROPOSAL_RECEIPT"):
        wrapper.finalize()
    assert not (root / "proposal-receipts/manifest.json").exists()


@pytest.mark.parametrize("change", ["seed", "frame_id", "rgb", "image_file"])
def test_wrong_frame_rejected_before_dino(tmp_path, change):
    _, wrapper, dataset, frame, _, events = _adapter(tmp_path)
    if change == "seed":
        frame = replace(frame, source_stamp_ns=420000001)
    elif change == "frame_id":
        frame = replace(frame, source_frame_id="wrong")
    elif change == "rgb":
        frame = replace(frame, rgb8=np.ones((16, 16, 3), dtype=np.uint8))
    else:
        dataset.samples[0].image_path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="PROPOSAL_RECEIPT"):
        wrapper.collect(frame, CollectionMode.LOW_FLOOR)
    assert events == []


@pytest.mark.parametrize(
    "proposals",
    [
        (((1.0, 1.0, 8.0, 8.0), float("nan"), 0.8),),
        (((1.0, 1.0, 8.0, 8.0), 0.9, float("inf")),),
        (((1.0, 1.0, 8.0, 8.0), True, 0.8),),
        (((1.0, 1.0, 8.0, 8.0), 1.1, 0.8),),
        (((1.0, 1.0, 8.0, 8.0), 0.9, 0.001),),
        (((-1.0, 1.0, 8.0, 8.0), 0.9, 0.8),),
        (((1.0, 1.0, 18.0, 8.0), 0.9, 0.8),),
        (((8.0, 1.0, 1.0, 8.0), 0.9, 0.8),),
        tuple(reversed(PROPOSALS)),
    ],
)
def test_invalid_proposals_fail_before_sam(tmp_path, proposals):
    _, wrapper, _, frame, _, events = _adapter(tmp_path, proposals=proposals)
    with pytest.raises(ValueError, match="PROPOSAL_RECEIPT"):
        wrapper.collect(frame, CollectionMode.LOW_FLOOR)
    assert events == ["dino"]


def test_write_failure_stops_before_sam_and_preserves_collision(tmp_path):
    _, wrapper, _, frame, root, events = _adapter(tmp_path)
    path = root / "proposal-receipts/000000.json"
    path.write_bytes(b"existing evidence")
    with pytest.raises(ValueError, match="PROPOSAL_RECEIPT"):
        wrapper.collect(frame, CollectionMode.LOW_FLOOR)
    assert path.read_bytes() == b"existing evidence"
    assert events == ["dino"]


def test_survivor_not_in_observed_proposals_invalidates_run(tmp_path):
    candidate = _candidate()
    candidate.grounding_box_score = 0.95
    _, wrapper, _, frame, _, _ = _adapter(tmp_path, candidates=[candidate])
    with pytest.raises(ValueError, match="PROPOSAL_RECEIPT"):
        wrapper.collect(frame, CollectionMode.LOW_FLOOR)
    with pytest.raises(ValueError, match="PROPOSAL_RECEIPT"):
        wrapper.finalize()


@pytest.mark.parametrize(
    "device,identity",
    [
        ("cpu", None),
        ("cuda", {"source_commit": "bad"}),
        ("cuda", {"model_manifest_sha256": "bad"}),
    ],
)
def test_runtime_and_provenance_fail_closed(tmp_path, device, identity):
    with pytest.raises(ValueError, match="PROPOSAL_RECEIPT"):
        _adapter(tmp_path, device=device, identity=identity)


@pytest.mark.parametrize("corruption", ["receipt", "missing", "extra", "model", "raw"])
def test_readback_rejects_corruption_and_wrong_binding(tmp_path, corruption):
    module, wrapper, dataset, frame, root, _ = _adapter(tmp_path)
    result = wrapper.collect(frame, CollectionMode.LOW_FLOOR)
    wrapper.finalize()
    path = root / "proposal-receipts/000000.json"
    if corruption == "receipt":
        path.write_bytes(path.read_bytes() + b" ")
    elif corruption == "missing":
        path.rename(path.with_suffix(".retained"))
    elif corruption == "extra":
        (path.parent / "000001.json").write_bytes(path.read_bytes())
    candidates = result.raw_candidates if corruption != "raw" else (_candidate(0), _candidate(0))
    with pytest.raises(ValueError, match="PROPOSAL_RECEIPT"):
        module.load_verified_proposal_receipts(
            root,
            dataset=dataset,
            expected_source_commit=SOURCE,
            expected_model_manifest_sha256="e" * 64 if corruption == "model" else MODEL,
            raw_candidates_by_sample=(candidates,),
        )


def test_finalize_rechecks_image_before_publishing_valid_manifest(tmp_path):
    _, wrapper, dataset, frame, root, _ = _adapter(tmp_path)
    wrapper.collect(frame, CollectionMode.LOW_FLOOR)
    dataset.samples[0].image_path.write_bytes(b"changed after inference")
    with pytest.raises(ValueError, match="PROPOSAL_RECEIPT"):
        wrapper.finalize()
    assert not (root / "proposal-receipts/manifest.json").exists()


def test_real_val_collector_keeps_masks_and_complete_proposals(tmp_path):
    from so101_demo.perception_benchmark.codec import canonical_json_bytes, encode_mask_rle
    from so101_demo.perception_benchmark.contracts import MaskRef, RawCandidate
    from so101_demo.training.grounded_sam_val_calibration import (
        collect_val_raw,
        load_verified_raw_records,
    )

    module = _module()
    dataset, _ = _inputs(tmp_path)
    root = tmp_path / "integration"
    wrappers = []

    def factory(output_root):
        def raw_factory(observer):
            def collect(frame, mode):
                observer(PROPOSALS)
                mask = np.zeros((16, 16), dtype=bool)
                mask[2:10, 2:10] = True
                (output_root / "mask.json").write_bytes(canonical_json_bytes(encode_mask_rle(mask)))
                candidate = RawCandidate(
                    candidate_id="grounded-sam-001",
                    label="cup",
                    bbox_xyxy=(2.0, 2.0, 9.0, 9.0),
                    mask=MaskRef(
                        "mask.json",
                        hashlib.sha256(mask.astype(np.uint8).tobytes()).hexdigest(),
                        64,
                        16,
                        16,
                    ),
                    ranking_score=0.7,
                    ranking_score_source="grounding_box_score",
                    class_confidence=None,
                    grounding_box_score=0.7,
                    grounding_text_score=0.6,
                    sam_quality=0.8,
                )
                return SimpleNamespace(
                    model_id="grounding-dino-tiny+sam2.1-hiera-tiny",
                    runtime_device="cuda",
                    dtype="float32",
                    collection_mode=mode,
                    fallback_used=False,
                    irreversible_limits=dict(
                        box_threshold=0.01,
                        text_threshold=0.01,
                        sam_quality_floor=0.0,
                        min_mask_pixels=64,
                        max_mask_area_ratio=0.5,
                    ),
                    raw_candidates=(candidate,),
                )

            return SimpleNamespace(
                model_id="grounding-dino-tiny+sam2.1-hiera-tiny",
                runtime_device="cuda",
                collect=collect,
            )

        wrapper = module.ProposalReceiptAdapter(
            dataset=dataset,
            evidence_root=output_root,
            source_commit=SOURCE,
            model_manifest_sha256=MODEL,
            adapter_factory=raw_factory,
        )
        wrappers.append(wrapper)
        return wrapper

    manifest = collect_val_raw(
        dataset=dataset,
        adapter_factory=factory,
        output_root=root,
        run_id="receipt-integration",
        source_commit=SOURCE,
        model_manifest_sha256=MODEL,
    )
    wrappers[0].finalize()
    raw = load_verified_raw_records(
        root, dataset=dataset, expected_model_manifest_sha256=MODEL, expected_source_commit=SOURCE
    )
    receipts = module.load_verified_proposal_receipts(
        root,
        dataset=dataset,
        expected_source_commit=SOURCE,
        expected_model_manifest_sha256=MODEL,
        raw_candidates_by_sample=raw,
    )
    assert manifest["status"] == "VALID" and manifest["record_count"] == 1
    assert len(raw[0]) == 1 and raw[0][0].mask.pixel_count == 64
    assert len(receipts[0]) == 2
