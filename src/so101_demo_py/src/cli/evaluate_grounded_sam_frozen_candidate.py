"""Evaluate one immutable Grounded-SAM candidate on its sealed synthetic test."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from so101_demo.adapters.perception.grounded_sam import GroundedSamDetector
from so101_demo.adapters.perception.grounded_sam_postprocess import (
    GroundedSamThresholds,
)
from so101_demo.adapters.perception.model_bundle import verify_model_bundle
from so101_demo.perception_benchmark.adapters import (
    GroundedSamRawAdapter,
    run_production_detector_port,
)
from so101_demo.perception_benchmark.adapters.base import _validate_detector_runtime
from so101_demo.training.frozen_candidate_evaluation import (
    FrozenCandidateError,
    FrozenCandidateLock,
    evaluate_frozen_synthetic_test,
    initialize_evaluation_output,
    load_locked_synthetic_test,
    mark_evaluation_invalid,
    verify_frozen_candidate_lock,
)


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _reuse(component: Any):
    return lambda *_args, **_kwargs: component


def _build_runtime(
    lock: FrozenCandidateLock, evidence_root: Path
) -> tuple[GroundedSamRawAdapter, GroundedSamDetector]:
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ[name] = "1"
    if any(os.environ.get(name) != "1" for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")):
        raise FrozenCandidateError("OFFLINE_MODE_REQUIRED", "Hugging Face offline flags")
    bundle_contract = lock.document["model_bundle"]
    bundle = verify_model_bundle(Path(bundle_contract["root"]), bundle_contract["manifest_sha256"])
    values = lock.document["thresholds"]["production"]
    production = GroundedSamDetector(
        bundle=bundle,
        thresholds=GroundedSamThresholds(
            box_threshold=float(values["box_threshold"]),
            text_threshold=float(values["text_threshold"]),
            duplicate_iou=float(values["duplicate_iou_threshold"]),
            max_candidates=values["maximum_candidates"],
            sam_quality=float(values["sam_quality_threshold"]),
            min_mask_pixels=values["minimum_mask_pixels"],
            max_mask_area_ratio=float(values["maximum_mask_area_ratio"]),
        ),
        requested_device="cuda",
        allow_cpu_fallback=False,
    )
    raw = GroundedSamRawAdapter.from_bundle(
        bundle.root,
        expected_manifest_sha256=bundle.manifest_sha256,
        requested_device="cuda",
        evidence_root=evidence_root,
        torch_api=production._torch,
        grounding_processor_loader=_reuse(production._grounding_processor),
        grounding_model_loader=_reuse(production._grounding_model),
        sam_processor_loader=_reuse(production._sam_processor),
        sam_model_loader=_reuse(production._sam_model),
    )
    if (
        raw._grounding_processor is not production._grounding_processor
        or raw._grounding_model is not production._grounding_model
        or raw._sam_processor is not production._sam_processor
        or raw._sam_model is not production._sam_model
    ):
        raise FrozenCandidateError("MODEL_IDENTITY_MISMATCH", "raw and production")
    _validate_detector_runtime(production, "cuda", "grounded_sam")
    return raw, production


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evaluate_grounded_sam_frozen_candidate")
    parser.add_argument("--candidate-lock", required=True, type=_absolute_path)
    parser.add_argument("--candidate-lock-sha256", required=True)
    parser.add_argument("--source-root", required=True, type=_absolute_path)
    parser.add_argument("--sealed-members", required=True, type=_absolute_path)
    parser.add_argument("--output-root", required=True, type=_absolute_path)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parsed = parser.parse_args(arguments)
    initialized = False
    try:
        lock = verify_frozen_candidate_lock(parsed.candidate_lock, parsed.candidate_lock_sha256)
        initialize_evaluation_output(
            output_root=parsed.output_root,
            lock=lock,
            run_id=parsed.run_id,
            source_commit=parsed.source_commit,
        )
        initialized = True
        dataset = load_locked_synthetic_test(
            lock=lock,
            source_root=parsed.source_root,
            sealed_members_path=parsed.sealed_members,
        )
        raw, production = _build_runtime(lock, parsed.output_root)
        report = evaluate_frozen_synthetic_test(
            dataset=dataset,
            lock=lock,
            output_root=parsed.output_root,
            raw_adapter=raw,
            production_observer=lambda frame: run_production_detector_port(
                production, frame, selector_threshold=0.25
            ),
            source_commit=parsed.source_commit,
            run_id=parsed.run_id,
        )
    except (FileNotFoundError, FrozenCandidateError, OSError, RuntimeError, ValueError) as error:
        if initialized:
            mark_evaluation_invalid(parsed.output_root, error)
        print(
            json.dumps(
                {"failure": str(error), "status": "ERROR"},
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1
    status = "VALID" if report["safety_passed"] else "FAILED_SAFETY"
    print(
        json.dumps(
            {"output_root": str(parsed.output_root), "status": status},
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0 if report["safety_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
