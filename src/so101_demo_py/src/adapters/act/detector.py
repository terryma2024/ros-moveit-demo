"""Reuse the lightweight RGB detector with spatial, attempt-scoped tracks."""

from so101_demo.act.contracts import fields, finite, identifier, integer, sha256
from so101_demo.core.detection import DetectionFrame, DetectionQuery


class RgbHeadModel:
    """Ultralytics accepts BGR numpy sources; public head input stays RGB."""

    def __init__(self, model):
        self.model = model
        self.names = model.names

    def predict(self, *, source, **kwargs):
        import numpy as np
        if not isinstance(source, np.ndarray) or source.ndim != 3 or source.shape[2] != 3:
            raise ValueError("HEAD_RGB_INVALID")
        return self.model.predict(source=np.ascontiguousarray(source[:, :, ::-1]), **kwargs)


def head_model_factory(path):
    from ultralytics import YOLO
    return RgbHeadModel(YOLO(path))


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
