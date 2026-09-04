"""Offline Grounding-DINO + SAM low-floor raw candidate collection."""

from __future__ import annotations

import importlib
import math
import os
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any, cast

import numpy as np
from so101_demo.adapters.perception.grounded_sam_postprocess import (
    grounding_label_matches_prompt,
)
from so101_demo.adapters.perception.model_bundle import verify_model_bundle
from so101_demo.adapters.perception.model_runtime import (
    ModelSetupError,
    select_runtime_device,
)
from so101_demo.core.detection import DetectionFrame, RuntimeDevice
from so101_demo.perception_benchmark.adapters.base import (
    CollectionMode,
    RawDetectionResult,
    ResourceSamplingError,
    _MaskArtifactStore,
    _validate_accelerated_component,
)
from so101_demo.perception_benchmark.contracts import (
    GROUNDED_SAM_MODEL_ID,
    RawCandidate,
)
from so101_demo.perception_benchmark.timing import (
    DeviceSynchronizer,
    PhaseTimer,
    ResourceSampler,
)

def _force_offline_environment() -> None:
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE"):
        os.environ[name] = "1"
    if any(os.environ.get(name) != "1" for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")):
        raise ModelSetupError(
            "OFFLINE_MODE_REQUIRED",
            "HF_HUB_OFFLINE and TRANSFORMERS_OFFLINE must equal 1",
        )


def _to_numpy(value: Any) -> np.ndarray:
    current = value
    if hasattr(current, "detach"):
        current = current.detach()
    if hasattr(current, "cpu"):
        current = current.cpu()
    if hasattr(current, "numpy"):
        current = current.numpy()
    return np.asarray(current)


def _move_inputs(inputs: Any, device: RuntimeDevice) -> Any:
    if hasattr(inputs, "to"):
        return inputs.to(device)
    if isinstance(inputs, Mapping):
        return {
            key: value.to(device) if hasattr(value, "to") else value
            for key, value in inputs.items()
        }
    return inputs


def _validate_component(component: Any, runtime_device: RuntimeDevice, name: str) -> None:
    _validate_accelerated_component(component, runtime_device, name)


def _prepare_model(model: Any, device: RuntimeDevice) -> Any:
    try:
        prepared = model.to(device)
        if hasattr(prepared, "float"):
            prepared = prepared.float()
        if hasattr(prepared, "eval"):
            prepared = prepared.eval()
    except Exception as error:
        raise ModelSetupError("MODEL_LOAD_FAILED", str(error)) from error
    _validate_component(prepared, device, "model")
    return prepared


def _sigmoid(values: np.ndarray) -> np.ndarray:
    positive = values >= 0.0
    result = np.empty(values.shape, dtype=np.float64)
    result[positive] = 1.0 / (1.0 + np.exp(-values[positive]))
    exponent = np.exp(values[~positive])
    result[~positive] = exponent / (1.0 + exponent)
    return result


def _token_strings(processor: Any, input_ids: np.ndarray) -> tuple[str, ...]:
    tokenizer = getattr(processor, "tokenizer", None)
    if tokenizer is None or not hasattr(tokenizer, "convert_ids_to_tokens"):
        raise ModelSetupError(
            "RESULT_CONTRACT_INVALID",
            "grounding tokenizer tokens are required for text-score provenance",
        )
    tokens = tokenizer.convert_ids_to_tokens([int(value) for value in input_ids])
    if not isinstance(tokens, Sequence) or len(tokens) != len(input_ids):
        raise ModelSetupError("RESULT_CONTRACT_INVALID", "grounding token conversion is invalid")
    return tuple(str(token).lower() for token in tokens)


def _phrase_positions(tokens: tuple[str, ...], prompt: str) -> tuple[tuple[int, ...], ...]:
    normalized = tuple(
        token.replace("##", "").replace("ġ", "").replace("▁", "") for token in tokens
    )
    words = tuple(
        word
        for word in prompt.casefold().replace(".", " ").split()
        if word
    )
    positions = tuple(
        tuple(index for index, token in enumerate(normalized) if word in token)
        for word in words
    )
    if not words or any(not matches for matches in positions):
        raise ModelSetupError(
            "RESULT_CONTRACT_INVALID",
            "decoded grounding tokens do not contain every prompt word",
        )
    return positions


def _query_indices(
    result: Mapping[str, object], scores: np.ndarray, probabilities: np.ndarray
) -> tuple[int, ...]:
    if "query_indices" in result:
        values = _to_numpy(result["query_indices"])
        if values.shape != scores.shape or not np.issubdtype(values.dtype, np.integer):
            raise ModelSetupError("RESULT_CONTRACT_INVALID", "grounding query_indices are invalid")
        indices = tuple(int(value) for value in values)
    else:
        query_scores = probabilities.max(axis=1)
        unused = set(range(len(query_scores)))
        matched: list[int] = []
        for score in scores:
            if not unused:
                raise ModelSetupError(
                    "RESULT_CONTRACT_INVALID", "grounding query mapping is incomplete"
                )
            index = min(unused, key=lambda item: (abs(query_scores[item] - score), item))
            if not math.isclose(
                float(query_scores[index]), float(score), rel_tol=1e-4, abs_tol=1e-4
            ):
                raise ModelSetupError(
                    "RESULT_CONTRACT_INVALID",
                    "grounding query mapping cannot be proven",
                )
            unused.remove(index)
            matched.append(index)
        indices = tuple(matched)
    if any(index < 0 or index >= probabilities.shape[0] for index in indices):
        raise ModelSetupError("RESULT_CONTRACT_INVALID", "grounding query index is out of range")
    return indices


class GroundedSamRawAdapter:
    """Collect stateless low-floor Grounding-DINO proposals and SAM masks."""

    def __init__(
        self,
        *,
        model_id: str,
        runtime_device: RuntimeDevice,
        manifest_sha256: str,
        evidence_root: Path,
        torch_api: Any,
        grounding_processor: Any,
        grounding_model: Any,
        sam_processor: Any,
        sam_model: Any,
        synchronizer: DeviceSynchronizer,
        resource_sampler: ResourceSampler,
        target_class_id: str = "plastic_cup",
        prompt: str = "plastic cup.",
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        if model_id != GROUNDED_SAM_MODEL_ID:
            raise ValueError("model_id must equal the canonical Grounded-SAM benchmark ID")
        if runtime_device not in {"mps", "cuda"}:
            raise ValueError("formal Grounded-SAM collection requires mps or cuda")
        if synchronizer.device != runtime_device or resource_sampler.device != runtime_device:
            raise ValueError("timing/resource device does not match Grounded-SAM runtime")
        if not isinstance(manifest_sha256, str) or len(manifest_sha256) != 64:
            raise ValueError("manifest_sha256 is invalid")
        if target_class_id not in {"cup", "plastic_cup"}:
            raise ValueError("target_class_id is invalid")
        if not isinstance(prompt, str) or not prompt:
            raise ValueError("prompt is invalid")
        _force_offline_environment()
        self.model_id = model_id
        self.runtime_device = runtime_device
        self._manifest_sha256 = manifest_sha256
        self.target_class_id = target_class_id
        self._prompt = prompt
        self._torch = torch_api
        self._grounding_processor = grounding_processor
        self._grounding_model = grounding_model
        self._sam_processor = sam_processor
        self._sam_model = sam_model
        self._synchronizer = synchronizer
        self._resource_sampler = resource_sampler
        self._monotonic_ns = monotonic_ns
        self._artifact_store = _MaskArtifactStore(evidence_root, "grounded-sam")
        _validate_component(self._grounding_model, runtime_device, "grounding model")
        _validate_component(self._sam_model, runtime_device, "SAM model")

    @classmethod
    def from_bundle(
        cls,
        bundle_root: Path,
        *,
        expected_manifest_sha256: str,
        requested_device: RuntimeDevice,
        evidence_root: Path,
        torch_api: Any | None = None,
        grounding_processor_loader: Callable[..., Any] | None = None,
        grounding_model_loader: Callable[..., Any] | None = None,
        sam_processor_loader: Callable[..., Any] | None = None,
        sam_model_loader: Callable[..., Any] | None = None,
        network_loader: Callable[..., Any] | None = None,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> "GroundedSamRawAdapter":
        """Verify the pinned local bundle before invoking local-only loaders."""

        del network_loader
        root = Path(bundle_root)
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            raise ModelSetupError(
                "MODEL_UNAVAILABLE", f"bundle is not a local regular directory: {root}"
            )
        if requested_device not in {"mps", "cuda"}:
            raise ModelSetupError("DEVICE_UNAVAILABLE", "formal Grounded-SAM requires mps or cuda")
        bundle = verify_model_bundle(root, expected_manifest_sha256)
        _force_offline_environment()
        if torch_api is None:
            torch_api = importlib.import_module("torch")
        runtime_device = select_runtime_device(requested_device, False, torch_api)
        transformers: Any | None = None

        def grounding_processor_default(path: Path, *, local_files_only: bool) -> Any:
            nonlocal transformers
            transformers = transformers or importlib.import_module("transformers")
            return transformers.AutoProcessor.from_pretrained(
                path, local_files_only=local_files_only
            )

        def grounding_model_default(path: Path, *, local_files_only: bool) -> Any:
            nonlocal transformers
            transformers = transformers or importlib.import_module("transformers")
            return transformers.AutoModelForZeroShotObjectDetection.from_pretrained(
                path, local_files_only=local_files_only
            )

        def sam_processor_default(path: Path, *, local_files_only: bool) -> Any:
            nonlocal transformers
            transformers = transformers or importlib.import_module("transformers")
            return transformers.Sam2Processor.from_pretrained(
                path, local_files_only=local_files_only
            )

        def sam_model_default(path: Path, *, local_files_only: bool) -> Any:
            nonlocal transformers
            transformers = transformers or importlib.import_module("transformers")
            return transformers.Sam2Model.from_pretrained(path, local_files_only=local_files_only)

        try:
            grounding_processor = (grounding_processor_loader or grounding_processor_default)(
                bundle.detector_dir, local_files_only=True
            )
            grounding_model = _prepare_model(
                (grounding_model_loader or grounding_model_default)(
                    bundle.detector_dir, local_files_only=True
                ),
                runtime_device,
            )
            sam_processor = (sam_processor_loader or sam_processor_default)(
                bundle.segmenter_dir, local_files_only=True
            )
            sam_model = _prepare_model(
                (sam_model_loader or sam_model_default)(
                    bundle.segmenter_dir, local_files_only=True
                ),
                runtime_device,
            )
        except ModelSetupError:
            raise
        except Exception as error:
            raise ModelSetupError("MODEL_LOAD_FAILED", str(error)) from error
        synchronizer = DeviceSynchronizer(torch_api, runtime_device)
        return cls(
            model_id=GROUNDED_SAM_MODEL_ID,
            runtime_device=runtime_device,
            manifest_sha256=bundle.manifest_sha256,
            evidence_root=evidence_root,
            torch_api=torch_api,
            grounding_processor=grounding_processor,
            grounding_model=grounding_model,
            sam_processor=sam_processor,
            sam_model=sam_model,
            synchronizer=synchronizer,
            resource_sampler=ResourceSampler(torch_api=torch_api, device=runtime_device),
            target_class_id=bundle.target_class_id,
            prompt=bundle.prompt,
            monotonic_ns=monotonic_ns,
        )

    def _grounding(
        self, frame: DetectionFrame, inputs: Any
    ) -> tuple[tuple[tuple[float, float, float, float], float, float], ...]:
        with self._torch.inference_mode():
            outputs = self._grounding_model(**inputs)
        try:
            input_ids = _to_numpy(inputs["input_ids"])
            logits = _to_numpy(outputs.logits)
        except (KeyError, TypeError, AttributeError) as error:
            raise ModelSetupError(
                "RESULT_CONTRACT_INVALID", "grounding inputs/outputs are incomplete"
            ) from error
        if input_ids.ndim != 2 or input_ids.shape[0] != 1:
            raise ModelSetupError("RESULT_CONTRACT_INVALID", "grounding input_ids shape is invalid")
        if logits.ndim != 3 or logits.shape[0] != 1 or logits.shape[2] < input_ids.shape[1]:
            raise ModelSetupError("RESULT_CONTRACT_INVALID", "grounding logits shape is invalid")
        if logits.dtype != np.float32:
            raise ModelSetupError(
                "NON_FP32_RUNTIME", f"grounding logits dtype is {logits.dtype.name}"
            )
        results = self._grounding_processor.post_process_grounded_object_detection(
            outputs,
            input_ids=inputs["input_ids"],
            threshold=0.01,
            text_threshold=0.01,
            target_sizes=[(frame.image_height, frame.image_width)],
        )
        if not isinstance(results, (list, tuple)) or len(results) != 1:
            raise ModelSetupError(
                "RESULT_CONTRACT_INVALID", "grounding postprocess must return one result"
            )
        result = results[0]
        if not isinstance(result, Mapping):
            raise ModelSetupError("RESULT_CONTRACT_INVALID", "grounding result must be a mapping")
        try:
            boxes = _to_numpy(result["boxes"])
            scores = _to_numpy(result["scores"])
            labels = tuple(result["text_labels"])  # type: ignore[arg-type]
        except (KeyError, TypeError) as error:
            raise ModelSetupError(
                "RESULT_CONTRACT_INVALID", "grounding result fields are incomplete"
            ) from error
        if (
            boxes.dtype != np.float32
            or scores.dtype != np.float32
            or boxes.ndim != 2
            or boxes.shape[1:] != (4,)
            or scores.shape != (len(boxes),)
            or len(labels) != len(boxes)
        ):
            raise ModelSetupError("RESULT_CONTRACT_INVALID", "grounding result arrays are invalid")
        probabilities = _sigmoid(logits[0])
        tokens = _token_strings(self._grounding_processor, input_ids[0])
        phrase_positions = _phrase_positions(tokens, self._prompt)
        query_indices = _query_indices(result, scores, probabilities)
        proposals: list[tuple[tuple[float, float, float, float], float, float]] = []
        for index, label in enumerate(labels):
            if not grounding_label_matches_prompt(label, self._prompt):
                continue
            box_score = float(scores[index])
            query_probabilities = probabilities[query_indices[index]]
            text_score = min(
                max(float(query_probabilities[position]) for position in positions)
                for positions in phrase_positions
            )
            if box_score < 0.01 or text_score < 0.01:
                continue
            raw_box = tuple(float(value) for value in boxes[index])
            clipped = (
                min(max(raw_box[0], 0.0), float(frame.image_width)),
                min(max(raw_box[1], 0.0), float(frame.image_height)),
                min(max(raw_box[2], 0.0), float(frame.image_width)),
                min(max(raw_box[3], 0.0), float(frame.image_height)),
            )
            if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
                raise ModelSetupError(
                    "RESULT_CONTRACT_INVALID", "grounding box is outside the frame"
                )
            proposals.append((clipped, box_score, text_score))
        proposals.sort(key=lambda item: (-item[1], item[0]))
        return tuple(proposals)

    def _sam(
        self,
        frame: DetectionFrame,
        proposals: tuple[tuple[tuple[float, float, float, float], float, float], ...],
    ) -> tuple[np.ndarray, np.ndarray]:
        input_boxes = np.asarray([[proposal[0] for proposal in proposals]], dtype=np.float32)
        inputs = _move_inputs(
            self._sam_processor(
                images=frame.rgb8,
                input_boxes=input_boxes,
                return_tensors="pt",
            ),
            self.runtime_device,
        )
        with self._torch.inference_mode():
            outputs = self._sam_model(**inputs, multimask_output=True)
        try:
            processed = self._sam_processor.post_process_masks(
                outputs.pred_masks, inputs["original_sizes"]
            )
            qualities = _to_numpy(outputs.iou_scores)
        except (AttributeError, KeyError, TypeError) as error:
            raise ModelSetupError(
                "RESULT_CONTRACT_INVALID", "SAM inputs/outputs are incomplete"
            ) from error
        if not isinstance(processed, (list, tuple)) or len(processed) != 1:
            raise ModelSetupError(
                "RESULT_CONTRACT_INVALID", "SAM postprocess must return one result"
            )
        masks = _to_numpy(processed[0])
        if qualities.ndim == 3 and qualities.shape[0] == 1:
            qualities = qualities[0]
        if (
            masks.dtype not in (np.dtype(np.bool_), np.dtype(np.float32))
            or qualities.dtype != np.float32
            or masks.ndim != 4
            or masks.shape[0] != len(proposals)
            or masks.shape[2:] != (frame.image_height, frame.image_width)
            or qualities.shape != masks.shape[:2]
        ):
            raise ModelSetupError("RESULT_CONTRACT_INVALID", "SAM result arrays are invalid")
        return masks, qualities

    def _candidates(
        self,
        frame: DetectionFrame,
        collection: PurePosixPath,
        proposals: tuple[tuple[tuple[float, float, float, float], float, float], ...],
        masks: np.ndarray,
        qualities: np.ndarray,
    ) -> tuple[RawCandidate, ...]:
        candidates: list[RawCandidate] = []
        frame_area = frame.image_width * frame.image_height
        for index, (bbox, box_score, text_score) in enumerate(proposals):
            mask_index = int(np.argmax(qualities[index]))
            quality = float(qualities[index, mask_index])
            selected_mask = masks[index, mask_index]
            if selected_mask.dtype == np.bool_:
                mask = np.asarray(selected_mask, dtype=bool)
            else:
                mask = np.asarray(selected_mask >= 0.5, dtype=bool)
            pixel_count = int(mask.sum())
            if quality < 0.0 or pixel_count < 64 or pixel_count / frame_area > 0.50:
                continue
            candidate_id = f"grounded-sam-{index:03d}"
            mask_ref = self._artifact_store.write_mask(
                collection / f"{candidate_id}.coco-rle.json", mask
            )
            candidates.append(
                RawCandidate(
                    candidate_id=candidate_id,
                    label=self.target_class_id,
                    bbox_xyxy=cast(tuple[float, float, float, float], bbox),
                    mask=mask_ref,
                    ranking_score=box_score,
                    ranking_score_source="grounding_box_score",
                    class_confidence=None,
                    grounding_box_score=box_score,
                    grounding_text_score=text_score,
                    sam_quality=quality,
                )
            )
        return tuple(candidates)

    def collect(self, frame: DetectionFrame, mode: CollectionMode) -> RawDetectionResult:
        if not isinstance(frame, DetectionFrame):
            raise ValueError("frame must be a DetectionFrame")
        if CollectionMode(mode) is not CollectionMode.LOW_FLOOR:
            raise ValueError("Grounded-SAM collection mode is unsupported")
        _validate_component(self._grounding_model, self.runtime_device, "grounding model")
        _validate_component(self._sam_model, self.runtime_device, "SAM model")
        collection = self._artifact_store.begin_collection()
        with PhaseTimer(self._synchronizer, monotonic_ns=self._monotonic_ns) as timer:
            grounding_inputs = _move_inputs(
                self._grounding_processor(
                    images=frame.rgb8,
                    text=self._prompt,
                    return_tensors="pt",
                ),
                self.runtime_device,
            )
            timer.mark("preprocess")
            proposals = self._grounding(frame, grounding_inputs)
            timer.mark("dino_or_yolo")
            if proposals:
                masks, qualities = self._sam(frame, proposals)
                timer.mark("sam")
                candidates = self._candidates(frame, collection, proposals, masks, qualities)
            else:
                masks = np.empty((0, 0, frame.image_height, frame.image_width))
                qualities = np.empty((0, 0))
                candidates = ()
            timer.mark("postprocess")
        try:
            resource_sample = self._resource_sampler.sample()
        except Exception as error:
            raise ResourceSamplingError("Grounded-SAM resource sampling failed") from error
        return RawDetectionResult(
            model_id=self.model_id,
            runtime_device=self.runtime_device,
            dtype="float32",
            collection_mode=CollectionMode.LOW_FLOOR,
            raw_candidates=candidates,
            phase_timings=timer.to_timings(
                sam_applicable=bool(proposals), selector_applicable=False
            ),
            resource_samples=(resource_sample,),
            fallback_used=False,
            irreversible_limits={
                "box_threshold": 0.01,
                "text_threshold": 0.01,
                "sam_quality_floor": 0.00,
                "min_mask_pixels": 64,
                "max_mask_area_ratio": 0.50,
            },
        )


__all__ = ("GroundedSamRawAdapter",)
