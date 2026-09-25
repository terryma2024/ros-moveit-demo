"""Reuse the lightweight RGB detector with spatial, attempt-scoped tracks."""

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import tempfile

from so101_demo.act.contracts import fields, finite, identifier, integer, sha256
from so101_demo.core.detection import DetectionFrame, DetectionQuery


@dataclass(frozen=True, slots=True)
class BoundHeadDetector:
    runtime: "HeadRgbDetector"
    snapshot_path: Path


def build_bound_head_detector(binding, *, snapshot_root, yolo_detector_factory=None,
                              torch_api=None, ultralytics_version=None):
    """Load the admitted model from a verified owned snapshot, once per child."""
    from so101_demo.adapters.perception.detector_factory import (
        DetectorFactoryOptions, build_detector,
    )
    from so101_demo.adapters.perception.yolo_seg import YoloSegDetector, verify_weights

    detector = binding.detector
    if torch_api is None:
        import torch
        torch_api = torch
    if ultralytics_version is None:
        import ultralytics
        ultralytics_version = ultralytics.__version__
    if (torch_api.__version__ != detector["torch_version"] or
            ultralytics_version != detector["ultralytics_version"]):
        raise ValueError("HEAD_SEARCH_RUNTIME_VERSION_DRIFT")
    torch_api.set_num_threads(detector["torch_threads"])
    torch_api.set_num_interop_threads(detector["torch_interop_threads"])
    if (torch_api.get_num_threads() != detector["torch_threads"] or
            torch_api.get_num_interop_threads() != detector["torch_interop_threads"]):
        raise ValueError("HEAD_SEARCH_THREAD_DRIFT")
    weights = Path(detector["weights_path"])
    root = Path(snapshot_root)
    if not root.is_absolute() or ".." in root.parts or root.is_symlink() or not root.is_dir():
        raise ValueError("HEAD_SEARCH_SNAPSHOT_ROOT_INVALID")
    try:
        fd = os.open(weights, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ValueError("HEAD_SEARCH_WEIGHTS_INVALID")
            data = source.read(128 * 1024 * 1024 + 1)
    except OSError as error:
        raise ValueError("HEAD_SEARCH_WEIGHTS_INVALID") from error
    if (len(data) > 128 * 1024 * 1024 or
            hashlib.sha256(data).hexdigest() != detector["weights_sha256"]):
        raise ValueError("HEAD_SEARCH_WEIGHTS_INVALID")
    private = Path(tempfile.mkdtemp(prefix="head-model-", dir=root))
    snapshot = private / "best.pt"
    fd = os.open(snapshot, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "wb") as target:
        target.write(data)
        target.flush()
        os.fsync(target.fileno())
    snapshot.chmod(0o400)
    directory = os.open(private, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    options = DetectorFactoryOptions(
        backend="yolo_seg", requested_device=detector["requested_device"],
        allow_cpu_fallback=detector["allow_cpu_fallback"],
        yolo_weights_path=snapshot, yolo_weights_sha256=detector["weights_sha256"],
        yolo_model_id=detector["model_id"], yolo_imgsz=detector["image_size_px"],
    )
    built = build_detector(options, yolo_detector_factory=(
        YoloSegDetector if yolo_detector_factory is None else yolo_detector_factory))
    verify_weights(snapshot, detector["weights_sha256"])
    if (torch_api.get_num_threads() != detector["torch_threads"] or
            torch_api.get_num_interop_threads() != detector["torch_interop_threads"]):
        raise ValueError("HEAD_SEARCH_THREAD_DRIFT")
    if (not detector["allow_cpu_fallback"] and
            built.detector.runtime_device != detector["requested_device"]):
        raise ValueError("HEAD_SEARCH_DEVICE_DRIFT")
    runtime = HeadRgbDetector(
        built.detector, model_id=detector["model_id"],
        weights_sha256=detector["weights_sha256"],
        tracking_iou=binding.search_values["tracking_iou"],
        min_bbox_aspect=binding.search_values["min_bbox_aspect"],
    )
    return BoundHeadDetector(runtime, snapshot)


def head_model_factory(path):
    """Create the model; YoloSegDetector owns RGB-to-BGR conversion."""
    from ultralytics import YOLO
    return YOLO(path)


def overlap(a, b):
    width = max(0., min(a[2], b[2]) - max(a[0], b[0]))
    height = max(0., min(a[3], b[3]) - max(a[1], b[1]))
    intersection = width * height
    union = (a[2]-a[0])*(a[3]-a[1]) + (b[2]-b[0])*(b[3]-b[1]) - intersection
    return intersection / union if union > 0 else 0.


class HeadRgbDetector:
    def __init__(self, detector, *, model_id, weights_sha256, tracking_iou, min_bbox_aspect):
        self.detector = detector
        self.model_id = identifier(model_id)
        self.weights_sha256 = sha256(weights_sha256)
        self.tracking_iou = finite(tracking_iou)
        self.min_bbox_aspect = finite(min_bbox_aspect)
        if not 0 < self.tracking_iou <= 1:
            raise ValueError("TRACKING_CONFIG_INVALID")
        if self.min_bbox_aspect <= 0:
            raise ValueError("HEAD_SHAPE_CONFIG_INVALID")
        self.reset()

    def reset(self):
        self.identity = None
        self.last_stamp_ns = None
        self.tracks = {}
        self.next_track = 0

    def detect(self, rgb, *, session_id, attempt_id, source_stamp_ns, source_frame_id):
        import numpy as np
        identifier(session_id); identifier(attempt_id); identifier(source_frame_id)
        integer(source_stamp_ns, minimum=1)
        if not isinstance(rgb, np.ndarray) or rgb.shape != (480,640,3) or rgb.dtype != np.uint8:
            raise ValueError("HEAD_RGB_INVALID")
        identity = (session_id, attempt_id)
        if self.identity is None: self.identity = identity
        if self.identity != identity:
            raise ValueError("DETECTOR_RESET_REQUIRED")
        if self.last_stamp_ns is not None and source_stamp_ns <= self.last_stamp_ns:
            raise ValueError("DETECTOR_TIMESTAMP_INVALID")
        batch = self.detector.detect(DetectionFrame(rgb, source_stamp_ns, source_frame_id),
                                     DetectionQuery("plastic_cup"))
        if batch.model_id != self.model_id or batch.weights_sha256 != self.weights_sha256:
            raise ValueError("DETECTOR_PROVENANCE_CHANGED")
        result = []; unused = set(self.tracks); current = {}
        for candidate in sorted(batch.candidates, key=lambda value: (value.bbox_xyxy, value.instance_id)):
            if candidate.class_id not in ("plastic_cup", "cup"): continue
            x1, y1, x2, y2 = candidate.bbox_xyxy
            if (y2-y1) / (x2-x1) < self.min_bbox_aspect: continue
            scores = sorted(((overlap(candidate.bbox_xyxy, self.tracks[track]), track)
                             for track in unused), reverse=True)
            # Tied spatial association cannot inherit a claimed target identity.
            if scores and scores[0][0] >= self.tracking_iou and (
                    len(scores) == 1 or scores[0][0] > scores[1][0] + 1e-9):
                track = scores[0][1]; unused.remove(track)
            else:
                track = f"head-cup-{self.next_track}"; self.next_track += 1
            current[track] = candidate.bbox_xyxy
            result.append(dict(xyxy=candidate.bbox_xyxy, confidence=candidate.confidence,
                               class_id=0, track_id=track))
        self.tracks, self.last_stamp_ns = current, source_stamp_ns
        return result


def detect_head(rgb, bundle):
    fields(bundle, ("runtime", "session_id", "attempt_id", "source_stamp_ns", "source_frame_id"))
    if not isinstance(bundle["runtime"], HeadRgbDetector):
        raise ValueError("DETECTOR_BUNDLE_INVALID")
    return bundle["runtime"].detect(rgb, **{key: value for key, value in bundle.items() if key != "runtime"})
