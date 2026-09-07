"""Lazy, offline Grounding DINO + SAM2 detector setup."""

from __future__ import annotations

import importlib
import logging
import os
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import numpy as np

from so101_demo.adapters.perception.grounded_sam_postprocess import (
    GroundedSamResultError,
    GroundedSamThresholds,
    GroundingProposal,
    convert_grounding_results,
    convert_sam_results,
    prompt_for_query,
)
from so101_demo.adapters.perception.model_bundle import VerifiedModelBundle
from so101_demo.adapters.perception.model_runtime import (
    ModelSetupError,
    RequestedDevice,
    select_runtime_device,
)
from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionFrame,
    DetectionQuery,
    RuntimeDevice,
)


_MODEL_ID = "grounding-dino-tiny+sam2.1-hiera-tiny"
_WARMUP_RGB = np.zeros((480, 640, 3), dtype=np.uint8)
_WARMUP_BOXES = np.asarray(
    [
        [
            [
                float(column * 160 + 16),
                float(row * 120 + 12),
                float(column * 160 + 144),
                float(row * 120 + 108),
            ]
            for row in range(4)
            for column in range(4)
        ]
    ],
    dtype=np.float32,
)
_LOGGER = logging.getLogger(__name__)
_OFFLINE_ENVIRONMENT = ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")


def _force_offline_environment() -> None:
    """Make the process-wide Hugging Face loaders fail closed to local files."""

    for name in _OFFLINE_ENVIRONMENT:
        os.environ[name] = "1"
    if any(os.environ.get(name) != "1" for name in _OFFLINE_ENVIRONMENT):
        raise ModelSetupError(
            "OFFLINE_MODE_REQUIRED",
            "HF_HUB_OFFLINE and TRANSFORMERS_OFFLINE must both equal 1",
        )


def _load_grounding_processor(path: Path, *, local_files_only: bool) -> Any:
    transformers = importlib.import_module("transformers")
    return transformers.AutoProcessor.from_pretrained(path, local_files_only=local_files_only)


def _load_grounding_model(path: Path, *, local_files_only: bool) -> Any:
    transformers = importlib.import_module("transformers")
    return transformers.AutoModelForZeroShotObjectDetection.from_pretrained(
        path, local_files_only=local_files_only
    )


def _load_sam_processor(path: Path, *, local_files_only: bool) -> Any:
    transformers = importlib.import_module("transformers")
    return transformers.Sam2Processor.from_pretrained(path, local_files_only=local_files_only)


def _load_sam_model(path: Path, *, local_files_only: bool) -> Any:
    transformers = importlib.import_module("transformers")
    return transformers.Sam2Model.from_pretrained(path, local_files_only=local_files_only)


def _move_inputs(inputs: Any, device: RuntimeDevice) -> Any:
    if hasattr(inputs, "to"):
        return inputs.to(device)
    if isinstance(inputs, Mapping):
        return {
            key: value.to(device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }
    return inputs


def _to_numpy(value: Any) -> np.ndarray:
    current = value
    if hasattr(current, "detach"):
        current = current.detach()
    if hasattr(current, "cpu"):
        current = current.cpu()
    if hasattr(current, "numpy"):
        current = current.numpy()
    return np.asarray(current)


def _contract_error(detail: str) -> GroundedSamResultError:
    return GroundedSamResultError("RESULT_CONTRACT_INVALID", detail)


class GroundedSamDetector:
    """Load immutable local models and exercise both once before use."""

    model_id = _MODEL_ID

    def __init__(
        self,
        *,
        bundle: VerifiedModelBundle,
        thresholds: GroundedSamThresholds,
        requested_device: RequestedDevice,
        allow_cpu_fallback: bool,
        torch_api: Any | None = None,
        grounding_processor_loader: Callable[..., Any] | None = None,
        grounding_model_loader: Callable[..., Any] | None = None,
        sam_processor_loader: Callable[..., Any] | None = None,
        sam_model_loader: Callable[..., Any] | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._monotonic_ns = monotonic_ns
        start_ns = monotonic_ns()
        _force_offline_environment()
        if torch_api is None:
            torch_api = importlib.import_module("torch")
        self._torch = torch_api
        self.runtime_device = select_runtime_device(
            requested_device, allow_cpu_fallback, torch_api
        )
        self._bundle = bundle
        self._thresholds = thresholds
        self.target_class_id = bundle.target_class_id
        self._prompt_profile = dict(bundle.manifest["prompt_profile"])
        self._prompt = bundle.prompt
        try:
            self._grounding_processor = (grounding_processor_loader or _load_grounding_processor)(
                bundle.detector_dir, local_files_only=True
            )
            self._grounding_model = (grounding_model_loader or _load_grounding_model)(
                bundle.detector_dir, local_files_only=True
            ).to(self.runtime_device).eval()
            self._sam_processor = (sam_processor_loader or _load_sam_processor)(
                bundle.segmenter_dir, local_files_only=True
            )
            self._sam_model = (sam_model_loader or _load_sam_model)(
                bundle.segmenter_dir, local_files_only=True
            ).to(self.runtime_device).eval()
        except Exception as error:
            raise ModelSetupError("MODEL_LOAD_FAILED", str(error)) from error
        try:
            self._warmup()
        except Exception as error:
            raise ModelSetupError("WARMUP_FAILED", str(error)) from error
        self.cold_start_latency_ms = (monotonic_ns() - start_ns) / 1_000_000.0

    def _warmup(self) -> None:
        grounding_inputs = _move_inputs(
            self._grounding_processor(
                images=_WARMUP_RGB,
                text=self._prompt,
                return_tensors="pt",
            ),
            self.runtime_device,
        )
        with self._torch.inference_mode():
            grounding_outputs = self._grounding_model(**grounding_inputs)
        self._grounding_processor.post_process_grounded_object_detection(
            grounding_outputs,
            input_ids=grounding_inputs["input_ids"],
            threshold=self._thresholds.box_threshold,
            text_threshold=self._thresholds.text_threshold,
            target_sizes=[(_WARMUP_RGB.shape[0], _WARMUP_RGB.shape[1])],
        )
        sam_inputs = _move_inputs(
            self._sam_processor(
                images=_WARMUP_RGB,
                input_boxes=_WARMUP_BOXES,
                return_tensors="pt",
            ),
            self.runtime_device,
        )
        with self._torch.inference_mode():
            sam_outputs = self._sam_model(**sam_inputs, multimask_output=True)
        self._sam_processor.post_process_masks(
            sam_outputs.pred_masks,
            sam_inputs["original_sizes"],
        )

    def _grounding_proposals(
        self, frame: DetectionFrame, query: DetectionQuery
    ) -> tuple[GroundingProposal, ...]:
        prompt = prompt_for_query(query, self._prompt_profile)
        grounding_inputs = _move_inputs(
            self._grounding_processor(
                images=frame.rgb8,
                text=prompt,
                return_tensors="pt",
            ),
            self.runtime_device,
        )
        try:
            input_ids = grounding_inputs["input_ids"]
        except (KeyError, TypeError) as error:
            raise _contract_error("grounding processor inputs must include input_ids") from error
        with self._torch.inference_mode():
            grounding_outputs = self._grounding_model(**grounding_inputs)
        results = self._grounding_processor.post_process_grounded_object_detection(
            grounding_outputs,
            input_ids=input_ids,
            threshold=self._thresholds.box_threshold,
            text_threshold=self._thresholds.text_threshold,
            target_sizes=[(frame.image_height, frame.image_width)],
        )
        if not isinstance(results, (list, tuple)) or len(results) != 1:
            raise _contract_error("grounding postprocess must return one image result")
        result = results[0]
        if not isinstance(result, Mapping):
            raise _contract_error("grounding result must be a mapping")
        try:
            boxes = result["boxes"]
            scores = result["scores"]
            labels = result["text_labels"]
        except KeyError as error:
            raise _contract_error(
                "grounding result requires boxes, scores, and text_labels"
            ) from error
        return convert_grounding_results(
            _to_numpy(boxes),
            _to_numpy(scores),
            labels,
            frame,
            query,
            self._thresholds,
            self._prompt_profile,
        )

    def _sam_results(
        self,
        frame: DetectionFrame,
        proposals: tuple[GroundingProposal, ...],
    ) -> tuple[Any, np.ndarray]:
        input_boxes = np.asarray(
            [[proposal.bbox_xyxy for proposal in proposals]], dtype=np.float32
        )
        sam_inputs = _move_inputs(
            self._sam_processor(
                images=frame.rgb8,
                input_boxes=input_boxes,
                return_tensors="pt",
            ),
            self.runtime_device,
        )
        try:
            original_sizes = sam_inputs["original_sizes"]
        except (KeyError, TypeError) as error:
            raise _contract_error("SAM processor inputs must include original_sizes") from error
        with self._torch.inference_mode():
            sam_outputs = self._sam_model(**sam_inputs, multimask_output=True)
        try:
            masks = self._sam_processor.post_process_masks(
                sam_outputs.pred_masks,
                original_sizes,
            )
            quality_scores = _to_numpy(sam_outputs.iou_scores)
        except AttributeError as error:
            raise _contract_error("SAM output requires pred_masks and iou_scores") from error
        if not isinstance(masks, (list, tuple)) or len(masks) != 1:
            raise _contract_error("SAM postprocess must return one image mask result")
        if quality_scores.ndim == 3 and quality_scores.shape[0] == 1:
            quality_scores = quality_scores[0]
        return _to_numpy(masks[0]), quality_scores

    def _log_mask_rejections(
        self,
        proposals: tuple[GroundingProposal, ...],
        candidates: tuple[DetectionCandidate, ...],
        quality_scores: np.ndarray,
    ) -> None:
        accepted = {
            (candidate.bbox_xyxy, candidate.confidence) for candidate in candidates
        }
        for proposal_index, proposal in enumerate(proposals):
            if (proposal.bbox_xyxy, proposal.confidence) in accepted:
                continue
            _LOGGER.warning(
                "MASK_REJECTED proposal_index=%d dino_score=%.6f max_sam_quality=%.6f "
                "sam_quality=%.6f min_mask_pixels=%d max_mask_area_ratio=%.6f "
                "mask_inside_box_ratio=0.800000",
                proposal_index,
                proposal.confidence,
                float(np.max(quality_scores[proposal_index])),
                self._thresholds.sam_quality,
                self._thresholds.min_mask_pixels,
                self._thresholds.max_mask_area_ratio,
            )

    def detect(self, frame: DetectionFrame, query: DetectionQuery) -> DetectionBatch:
        """Run stateless Grounding DINO followed by one batched SAM2 inference."""

        start_ns = self._monotonic_ns()
        try:
            proposals = self._grounding_proposals(frame, query)
            if not proposals:
                candidates: tuple[DetectionCandidate, ...] = ()
            else:
                masks, quality_scores = self._sam_results(frame, proposals)
                candidates = convert_sam_results(
                    proposals,
                    masks,
                    quality_scores,
                    frame,
                    self._thresholds,
                    self.target_class_id,
                )
                self._log_mask_rejections(proposals, candidates, quality_scores)
        except GroundedSamResultError:
            raise
        except Exception as error:
            raise GroundedSamResultError("INFERENCE_FAILED", str(error)) from error
        return DetectionBatch(
            model_id=self.model_id,
            weights_sha256=self._bundle.manifest_sha256,
            runtime_device=self.runtime_device,
            inference_latency_ms=(self._monotonic_ns() - start_ns) / 1_000_000.0,
            image_width=frame.image_width,
            image_height=frame.image_height,
            candidates=candidates,
        )
