"""Shared immutable raw-adapter and real production-port boundaries."""

from __future__ import annotations

import hashlib
import importlib
import math
import os
import re
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Literal, Mapping, Protocol, cast

import numpy as np

from so101_demo.adapters.perception.detector_factory import build_detector
from so101_demo.adapters.perception.grounded_sam import GroundedSamDetector
from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamThresholds
from so101_demo.adapters.perception.model_bundle import verify_model_bundle
from so101_demo.adapters.perception.model_runtime import ModelSetupError
from so101_demo.application.object_pose import TargetSelectionError, TargetSelector
from so101_demo.core.detection import (
    DetectionBatch,
    DetectionFrame,
    DetectionQuery,
    RuntimeDevice,
)
from so101_demo.perception_benchmark.calibration import (
    GroundedSamBenchmarkThresholds,
    ThresholdLock,
    YoloThresholds,
)
from so101_demo.perception_benchmark.codec import (
    canonical_json_bytes,
    encode_mask_rle,
    sha256_bytes,
)
from so101_demo.perception_benchmark.contracts import (
    DecisionOutput,
    MaskRef,
    RawCandidate,
)
from so101_demo.perception_benchmark.timing import (
    DeviceSynchronizer,
    PhaseTimingBreakdown,
    ResourceSample,
)
from so101_demo.ports.object_detector import DetectorPort


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class CollectionMode(str, Enum):
    LOW_FLOOR = "LOW_FLOOR"


@dataclass(frozen=True, slots=True)
class VerifiedBenchmarkAssets:
    """Pinned model assets and an explicit accelerator/fallback contract."""

    model: Literal["yolo_seg", "grounded_sam"]
    asset_root: Path
    weights_sha256: str | None
    manifest_sha256: str | None
    requested_device: Literal["mps", "cuda"]
    allow_cpu_fallback: Literal[False]

    def __post_init__(self) -> None:
        if self.model not in {"yolo_seg", "grounded_sam"}:
            raise ValueError("model is unsupported")
        root = Path(self.asset_root)
        if not root.is_absolute():
            raise ValueError("asset_root must be absolute")
        object.__setattr__(self, "asset_root", root)
        if self.requested_device not in {"mps", "cuda"}:
            raise ValueError("requested_device must be mps or cuda")
        if self.allow_cpu_fallback is not False:
            raise ValueError("CPU fallback is forbidden")
        expected_weights = self.model == "yolo_seg"
        if expected_weights:
            if (
                not isinstance(self.weights_sha256, str)
                or _SHA256.fullmatch(self.weights_sha256) is None
                or self.manifest_sha256 is not None
            ):
                raise ValueError("YOLO assets require only weights_sha256")
        elif (
            self.weights_sha256 is not None
            or not isinstance(self.manifest_sha256, str)
            or _SHA256.fullmatch(self.manifest_sha256) is None
        ):
            raise ValueError("Grounded-SAM assets require only manifest_sha256")


@dataclass(frozen=True, slots=True)
class RawDetectionResult:
    """One immutable, lossless candidate collection result."""

    model_id: str
    runtime_device: RuntimeDevice
    dtype: Literal["float32"]
    collection_mode: CollectionMode
    raw_candidates: tuple[RawCandidate, ...]
    phase_timings: PhaseTimingBreakdown
    resource_samples: tuple[ResourceSample, ...]
    fallback_used: bool
    irreversible_limits: Mapping[str, int | float | str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.model_id, str) or not self.model_id:
            raise ValueError("model_id must be non-empty")
        if self.runtime_device not in {"mps", "cuda"}:
            raise ValueError("runtime_device must be mps or cuda")
        if self.dtype != "float32":
            raise ValueError("formal benchmark dtype must be float32")
        try:
            object.__setattr__(self, "collection_mode", CollectionMode(self.collection_mode))
        except ValueError as error:
            raise ValueError("collection_mode is unsupported") from error
        candidates = tuple(self.raw_candidates)
        if not all(isinstance(candidate, RawCandidate) for candidate in candidates):
            raise ValueError("raw_candidates must contain RawCandidate values")
        candidate_ids = [candidate.candidate_id for candidate in candidates]
        if len(candidate_ids) != len(set(candidate_ids)):
            raise ValueError("raw candidate IDs must be unique")
        if "yolo" in self.model_id.lower() and any(
            candidate.ranking_score_source != "class_confidence"
            or candidate.class_confidence != candidate.ranking_score
            or candidate.grounding_box_score is not None
            or candidate.grounding_text_score is not None
            or candidate.sam_quality is not None
            for candidate in candidates
        ):
            raise ValueError("YOLO raw candidate score provenance is invalid")
        if "ground" in self.model_id.lower() and any(
            candidate.ranking_score_source != "grounding_box_score"
            or candidate.class_confidence is not None
            or candidate.grounding_box_score != candidate.ranking_score
            or candidate.grounding_text_score is None
            or candidate.sam_quality is None
            for candidate in candidates
        ):
            raise ValueError("Grounded-SAM raw candidate score provenance is invalid")
        object.__setattr__(self, "raw_candidates", candidates)
        if not isinstance(self.phase_timings, PhaseTimingBreakdown):
            raise ValueError("phase_timings must be a synchronized timing breakdown")
        resources = tuple(self.resource_samples)
        if not all(isinstance(sample, ResourceSample) for sample in resources):
            raise ValueError("resource_samples must contain ResourceSample values")
        object.__setattr__(self, "resource_samples", resources)
        if self.fallback_used is not False:
            raise ValueError("fallback execution is forbidden")
        limits = dict(self.irreversible_limits)
        if not all(
            isinstance(name, str)
            and name
            and isinstance(value, (int, float, str))
            and not isinstance(value, bool)
            and (not isinstance(value, float) or math.isfinite(value))
            for name, value in limits.items()
        ):
            raise ValueError("irreversible_limits are invalid")
        object.__setattr__(self, "irreversible_limits", MappingProxyType(limits))


class RawDetectorAdapter(Protocol):
    model_id: str
    runtime_device: RuntimeDevice

    def collect(
        self, frame: DetectionFrame, mode: CollectionMode
    ) -> RawDetectionResult: ...


@dataclass(frozen=True, slots=True)
class ProductionObservation:
    """The four-state output of the real detector port and real selector."""

    decision: DecisionOutput
    batch: DetectionBatch | None
    selected_candidate_id: str | None
    rejection_reason: str | None
    error_type: str | None
    error_summary: str | None
    selector_ms: float | None

    def __post_init__(self) -> None:
        try:
            object.__setattr__(self, "decision", DecisionOutput(self.decision))
        except ValueError as error:
            raise ValueError("decision must use the four-state contract") from error
        if self.selector_ms is not None and (
            not math.isfinite(self.selector_ms) or self.selector_ms < 0.0
        ):
            raise ValueError("selector_ms must be null or finite and nonnegative")
        if self.decision is DecisionOutput.UNIQUE:
            if (
                self.batch is None
                or self.selected_candidate_id is None
                or self.rejection_reason is not None
                or self.error_type is not None
                or self.error_summary is not None
            ):
                raise ValueError("UNIQUE observation fields are inconsistent")
            if self.selected_candidate_id not in {
                candidate.instance_id for candidate in self.batch.candidates
            }:
                raise ValueError("selected candidate identity is not in the batch")
        elif self.decision in {DecisionOutput.NOT_FOUND, DecisionOutput.AMBIGUOUS}:
            expected = (
                "TARGET_NOT_FOUND"
                if self.decision is DecisionOutput.NOT_FOUND
                else "TARGET_AMBIGUOUS"
            )
            if (
                self.batch is None
                or self.selected_candidate_id is not None
                or self.rejection_reason != expected
                or self.error_type is not None
                or self.error_summary is not None
            ):
                raise ValueError("selector rejection observation fields are inconsistent")
        elif (
            self.selected_candidate_id is not None
            or self.rejection_reason is not None
            or not self.error_type
            or not self.error_summary
        ):
            raise ValueError("ERROR observation fields are inconsistent")


class _MaskArtifactStore:
    """Own exclusive, lossless mask files below one evidence root."""

    def __init__(self, evidence_root: Path, namespace: str) -> None:
        root = Path(evidence_root)
        if not root.is_absolute():
            raise ValueError("evidence_root must be absolute")
        if root.is_symlink():
            raise ValueError("evidence_root must not be a symlink")
        if not root.is_dir():
            raise ValueError("evidence_root must be an existing directory")
        self.root = root.resolve(strict=True)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", namespace):
            raise ValueError("mask artifact namespace is invalid")
        self._namespace = PurePosixPath("benchmark-masks", namespace)
        benchmark_root = self.root / "benchmark-masks"
        _create_owned_directory(benchmark_root, self.root)
        self._namespace_path = benchmark_root / namespace
        _create_owned_directory(self._namespace_path, self.root)
        existing: list[int] = []
        for entry in os.scandir(self._namespace_path):
            match = re.fullmatch(r"collection-(\d{6})", entry.name)
            if match is not None:
                if entry.is_symlink() or not entry.is_dir(follow_symlinks=False):
                    raise ValueError("mask collection must not be a symlink")
                _require_owned_directory(Path(entry.path), self.root)
                existing.append(int(match.group(1)))
        self._next_collection = max(existing, default=-1) + 1
        self._lock = threading.Lock()

    def begin_collection(self) -> PurePosixPath:
        with self._lock:
            while True:
                relative = self._namespace / f"collection-{self._next_collection:06d}"
                self._next_collection += 1
                try:
                    created = _create_owned_directory(self.root / relative, self.root)
                except FileExistsError:
                    continue
                if not created:
                    continue
                return relative

    def write_mask(self, relative_path: str | PurePosixPath, mask: np.ndarray) -> MaskRef:
        relative = PurePosixPath(relative_path)
        if (
            relative.is_absolute()
            or any(part in {"", ".", ".."} for part in relative.parts)
            or not relative.is_relative_to(self._namespace)
        ):
            raise ValueError("mask path must stay in the adapter namespace")
        value = np.asarray(mask, dtype=bool)
        if value.ndim != 2 or not bool(value.any()):
            raise ValueError("candidate mask must be non-empty and two-dimensional")
        target = self.root / relative
        _require_owned_directory_chain(target.parent, self.root)
        if target.is_symlink():
            raise ValueError("mask target must not be a symlink")
        if target.exists():
            raise FileExistsError(target)
        payload = canonical_json_bytes(encode_mask_rle(value))
        parent_descriptor = _open_directory_no_follow(target.parent)
        try:
            flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
            flags |= getattr(os, "O_NOFOLLOW", 0)
            file_descriptor = os.open(
                target.name,
                flags,
                0o600,
                dir_fd=parent_descriptor,
            )
            with os.fdopen(file_descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.fsync(parent_descriptor)
        finally:
            os.close(parent_descriptor)
        _fsync_directory(target.parent)
        mask_sha = sha256_bytes(
            value.astype(np.uint8, copy=False).tobytes(order="C")
        )
        return MaskRef(
            relative_path=relative.as_posix(),
            sha256=mask_sha,
            pixel_count=int(value.sum()),
            image_width=int(value.shape[1]),
            image_height=int(value.shape[0]),
        )


def _open_directory_no_follow(path: Path) -> int:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    return os.open(path, flags)


def _fsync_directory(path: Path) -> None:
    descriptor = _open_directory_no_follow(path)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _require_owned_directory(path: Path, root: Path) -> None:
    if path.is_symlink():
        raise ValueError("mask artifact directory must not be a symlink")
    if not path.is_dir():
        raise ValueError("mask artifact parent must be a directory")
    try:
        path.resolve(strict=True).relative_to(root)
    except ValueError as error:
        raise ValueError("mask artifact directory escapes evidence_root") from error


def _require_owned_directory_chain(path: Path, root: Path) -> None:
    try:
        relative = path.relative_to(root)
    except ValueError as error:
        raise ValueError("mask artifact directory escapes evidence_root") from error
    current = root
    _require_owned_directory(current, root)
    for part in relative.parts:
        current = current / part
        _require_owned_directory(current, root)


def _create_owned_directory(path: Path, root: Path) -> bool:
    _require_owned_directory_chain(path.parent, root)
    parent_descriptor = _open_directory_no_follow(path.parent)
    try:
        try:
            os.mkdir(path.name, 0o700, dir_fd=parent_descriptor)
        except FileExistsError:
            _require_owned_directory(path, root)
            return False
        os.fsync(parent_descriptor)
    finally:
        os.close(parent_descriptor)
    _require_owned_directory(path, root)
    _fsync_directory(path)
    _fsync_directory(path.parent)
    return True


def _candidate_snapshot(batch: DetectionBatch) -> str:
    document = {
        "model_id": batch.model_id,
        "weights_sha256": batch.weights_sha256,
        "runtime_device": batch.runtime_device,
        "image_width": batch.image_width,
        "image_height": batch.image_height,
        "candidates": [
            {
                "instance_id": candidate.instance_id,
                "class_id": candidate.class_id,
                "confidence": candidate.confidence,
                "bbox_xyxy": list(candidate.bbox_xyxy),
                "source_stamp_ns": candidate.source_stamp_ns,
                "source_frame_id": candidate.source_frame_id,
                "image_width": candidate.image_width,
                "image_height": candidate.image_height,
                "segmentation_quality": candidate.segmentation_quality,
                "mask_sha256": hashlib.sha256(
                    candidate.mask.astype(np.uint8, copy=False).tobytes(order="C")
                ).hexdigest(),
            }
            for candidate in batch.candidates
        ],
    }
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()


def run_production_detector_port(
    detector: DetectorPort,
    frame: DetectionFrame,
    selector_threshold: float,
    *,
    synchronizer: DeviceSynchronizer | None = None,
) -> ProductionObservation:
    """Run the actual object-detector port followed by the actual TargetSelector."""

    query = DetectionQuery("plastic_cup")
    try:
        batch = detector.detect(frame, query)
        if not isinstance(batch, DetectionBatch):
            raise TypeError("detector did not return DetectionBatch")
    except Exception as error:
        return ProductionObservation(
            DecisionOutput.ERROR,
            None,
            None,
            None,
            "DETECTOR_ERROR",
            f"{type(error).__name__}: {error}",
            None,
        )

    before = _candidate_snapshot(batch)
    active_synchronizer = synchronizer
    if active_synchronizer is None:
        active_synchronizer = getattr(detector, "_benchmark_synchronizer", None)
    if active_synchronizer is None:
        active_synchronizer = getattr(detector, "_synchronizer", None)
    if active_synchronizer is None and hasattr(detector, "_torch"):
        active_synchronizer = DeviceSynchronizer(
            getattr(detector, "_torch"), batch.runtime_device
        )
    if active_synchronizer is not None:
        active_synchronizer.synchronize()
    started_ns = time.monotonic_ns()
    try:
        selected = TargetSelector().select(batch, query, selector_threshold)
    except TargetSelectionError as error:
        if active_synchronizer is not None:
            active_synchronizer.synchronize()
        selector_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        if _candidate_snapshot(batch) != before:
            raise RuntimeError("DETECTION_BATCH_MUTATED")
        mapping = {
            "TARGET_NOT_FOUND": DecisionOutput.NOT_FOUND,
            "TARGET_AMBIGUOUS": DecisionOutput.AMBIGUOUS,
        }
        decision = mapping.get(error.code)
        if decision is None:
            return ProductionObservation(
                DecisionOutput.ERROR,
                batch,
                None,
                None,
                "SELECTOR_ERROR",
                error.code,
                selector_ms,
            )
        return ProductionObservation(
            decision,
            batch,
            None,
            error.code,
            None,
            None,
            selector_ms,
        )
    except Exception as error:
        if active_synchronizer is not None:
            active_synchronizer.synchronize()
        selector_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
        if _candidate_snapshot(batch) != before:
            raise RuntimeError("DETECTION_BATCH_MUTATED")
        return ProductionObservation(
            DecisionOutput.ERROR,
            batch,
            None,
            None,
            "SELECTOR_ERROR",
            f"{type(error).__name__}: {error}",
            selector_ms,
        )
    if active_synchronizer is not None:
        active_synchronizer.synchronize()
    selector_ms = (time.monotonic_ns() - started_ns) / 1_000_000.0
    if _candidate_snapshot(batch) != before:
        raise RuntimeError("DETECTION_BATCH_MUTATED")
    if not any(selected is candidate for candidate in batch.candidates):
        raise RuntimeError("SELECTED_CANDIDATE_IDENTITY_INVALID")
    return ProductionObservation(
        DecisionOutput.UNIQUE,
        batch,
        selected.instance_id,
        None,
        None,
        None,
        selector_ms,
    )


def build_production_detector_port(factory_options: Any) -> DetectorPort:
    """Build with the production factory, then require the real detect port."""

    requested_device = getattr(factory_options, "requested_device", None)
    if requested_device not in {"mps", "cuda"}:
        raise ModelSetupError(
            "DEVICE_UNAVAILABLE", "formal production collection requires mps or cuda"
        )
    if getattr(factory_options, "allow_cpu_fallback", None) is not False:
        raise ModelSetupError("CPU_FALLBACK_FORBIDDEN", "CPU fallback is forbidden")
    built = build_detector(factory_options)
    if not callable(getattr(built.detector, "detect", None)):
        raise TypeError("factory detector does not implement DetectorPort.detect")
    backend = getattr(factory_options, "backend", None)
    _validate_detector_runtime(built.detector, requested_device, backend)
    if backend == "yolo_seg":
        from so101_demo.perception_benchmark.adapters.yolo import (
            resolve_yolo_production_config,
        )

        model = getattr(built.detector, "_model", None)
        if model is None:
            raise ModelSetupError(
                "PRODUCTION_CONFIG_UNAVAILABLE", "YOLO model is unavailable"
            )
        resolve_yolo_production_config(model)
    try:
        setattr(
            built.detector,
            "_benchmark_synchronizer",
            DeviceSynchronizer(
                importlib.import_module("torch"), cast(RuntimeDevice, requested_device)
            ),
        )
    except (AttributeError, ImportError) as error:
        raise ModelSetupError(
            "SYNCHRONIZER_UNAVAILABLE",
            "production detector cannot own a formal device synchronizer",
        ) from error
    return cast(DetectorPort, built.detector)


def _runtime_dtype(value: object) -> str | None:
    if value is None:
        return None
    try:
        return np.dtype(value).name
    except TypeError:
        normalized = str(value).lower()
        if "float32" in normalized:
            return "float32"
        if "float16" in normalized or "half" in normalized:
            return "float16"
        return normalized


def _runtime_device(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).lower()
    for device in ("cuda", "mps", "cpu"):
        if normalized.startswith(device):
            return device
    return normalized


def _runtime_parameter_module(component: Any) -> Any:
    nested = getattr(component, "model", None)
    for candidate in (nested, component):
        if candidate is not None and callable(getattr(candidate, "parameters", None)):
            return candidate
    raise ModelSetupError(
        "RUNTIME_PROVENANCE_UNAVAILABLE",
        "loaded component exposes no model parameters",
    )


def _validate_accelerated_component(
    component: Any, requested_device: str, name: str
) -> None:
    module = _runtime_parameter_module(component)
    try:
        parameters = tuple(module.parameters())
    except Exception as error:
        raise ModelSetupError(
            "RUNTIME_PROVENANCE_UNAVAILABLE",
            f"{name} parameters cannot be inspected",
        ) from error
    if not parameters:
        raise ModelSetupError(
            "RUNTIME_PROVENANCE_UNAVAILABLE",
            f"{name} exposes no parameters",
        )
    devices = {
        _runtime_device(getattr(parameter, "device", None))
        for parameter in parameters
    }
    if None in devices or any(
        device not in {"cuda", "mps", "cpu"} for device in devices
    ):
        raise ModelSetupError(
            "RUNTIME_PROVENANCE_UNAVAILABLE",
            f"{name} parameter device is missing or unknown",
        )
    if devices != {requested_device}:
        observed = ",".join(sorted(cast(set[str], devices)))
        raise ModelSetupError(
            "DEVICE_MISMATCH",
            f"{name} requested {requested_device}, observed {observed}",
        )
    dtypes = {
        _runtime_dtype(getattr(parameter, "dtype", None))
        for parameter in parameters
    }
    if None in dtypes or any(dtype is None or not dtype for dtype in dtypes):
        raise ModelSetupError(
            "RUNTIME_PROVENANCE_UNAVAILABLE",
            f"{name} parameter dtype is missing or unknown",
        )
    if dtypes != {"float32"}:
        observed = ",".join(sorted(cast(set[str], dtypes)))
        raise ModelSetupError(
            "NON_FP32_RUNTIME", f"{name} observed parameter dtypes {observed}"
        )


def _validate_detector_runtime(
    detector: Any, requested_device: str, backend: object
) -> None:
    observed_device = str(getattr(detector, "runtime_device", "")).lower()
    if observed_device != requested_device:
        raise ModelSetupError(
            "DEVICE_MISMATCH",
            f"requested {requested_device}, observed {observed_device or 'unknown'}",
        )
    if backend == "yolo_seg":
        component_names = (("_model", "YOLO model"),)
    elif backend == "grounded_sam":
        component_names = (
            ("_grounding_model", "grounding model"),
            ("_sam_model", "SAM model"),
        )
    else:
        raise ModelSetupError(
            "RUNTIME_PROVENANCE_UNAVAILABLE", "detector backend is unknown"
        )
    for attribute, name in component_names:
        component = getattr(detector, attribute, None)
        if component is None:
            raise ModelSetupError(
                "RUNTIME_PROVENANCE_UNAVAILABLE", f"{name} is unavailable"
            )
        _validate_accelerated_component(component, requested_device, name)


def _validated_lock(model: str, lock: ThresholdLock) -> ThresholdLock:
    if not isinstance(lock, ThresholdLock) or lock.model != model:
        raise ValueError("threshold lock does not match model")
    if lock.with_recomputed_sha256().lock_sha256 != lock.lock_sha256:
        raise ValueError("threshold lock digest is invalid")
    if not lock.formal or not lock.deployable:
        raise ValueError("calibrated detector requires a formal deployable lock")
    return lock


def _yolo_weights_path(root: Path) -> Path:
    return root if root.is_file() else root / "best.pt"


def build_calibrated_detector_port(
    model: Literal["yolo_seg", "grounded_sam"],
    lock: ThresholdLock,
    assets: VerifiedBenchmarkAssets,
) -> DetectorPort:
    """Build a real calibrated detector; raw candidate replay is not accepted."""

    validated = _validated_lock(model, lock)
    if not isinstance(assets, VerifiedBenchmarkAssets) or assets.model != model:
        raise ValueError("verified assets do not match model")
    if model == "yolo_seg":
        from so101_demo.perception_benchmark.adapters.yolo import (
            YoloCalibratedDetector,
        )

        selected = cast(YoloThresholds, validated.selected)
        detector: DetectorPort = YoloCalibratedDetector(
            weights_path=_yolo_weights_path(assets.asset_root),
            expected_sha256=cast(str, assets.weights_sha256),
            requested_device=assets.requested_device,
            model_id="plastic-cup-yolo11s-seg-v2",
            thresholds=selected,
        )
    else:
        selected = cast(GroundedSamBenchmarkThresholds, validated.selected)
        bundle = verify_model_bundle(
            assets.asset_root, cast(str, assets.manifest_sha256)
        )
        detector = GroundedSamDetector(
            bundle=bundle,
            thresholds=GroundedSamThresholds(
                box_threshold=float(selected.box_threshold),
                text_threshold=float(selected.text_threshold),
                duplicate_iou=float(selected.duplicate_iou),
                max_candidates=300,
                sam_quality=float(selected.sam_quality),
                min_mask_pixels=selected.min_mask_pixels,
                max_mask_area_ratio=float(selected.max_mask_area_ratio),
            ),
            requested_device=assets.requested_device,
            allow_cpu_fallback=False,
        )
    if not callable(getattr(detector, "detect", None)):
        raise TypeError("calibrated detector does not implement DetectorPort.detect")
    _validate_detector_runtime(detector, assets.requested_device, model)
    return detector


__all__ = (
    "CollectionMode",
    "ProductionObservation",
    "RawDetectionResult",
    "RawDetectorAdapter",
    "VerifiedBenchmarkAssets",
    "build_calibrated_detector_port",
    "build_production_detector_port",
    "run_production_detector_port",
)
