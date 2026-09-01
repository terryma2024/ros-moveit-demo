"""Atomic evidence artifacts for one object-pose request."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

import numpy as np

from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionFrame,
    LocalizedObject,
)
from so101_demo.runtime.point_cloud_preview import write_png_rgb8
from so101_demo.runtime.task_artifacts import atomic_json

if TYPE_CHECKING:
    from so101_demo.application.object_pose import ObjectPoseRequest, ObjectPoseResult


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_png(path: Path, image: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        write_png_rgb8(image, temporary)
        with temporary.open("rb") as stream:
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _atomic_ply(path: Path, points: np.ndarray) -> None:
    values = np.asarray(points, dtype=np.float64)
    if values.ndim != 2 or values.shape[1:] != (3,) or len(values) == 0:
        raise ValueError("selected cloud must contain XYZ points")
    if not np.isfinite(values).all():
        raise ValueError("selected cloud must contain finite points")
    header = (
        "ply\n"
        "format ascii 1.0\n"
        f"element vertex {len(values)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "end_header\n"
    )
    rows = "".join(f"{x:.9g} {y:.9g} {z:.9g}\n" for x, y, z in values)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write((header + rows).encode("ascii"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def render_detection_overlay(frame: DetectionFrame, batch: DetectionBatch) -> np.ndarray:
    result = np.array(frame.rgb8, copy=True)
    colors = (
        np.array([0, 255, 80], dtype=np.float64),
        np.array([80, 180, 255], dtype=np.float64),
        np.array([255, 80, 180], dtype=np.float64),
    )
    for index, candidate in enumerate(batch.candidates):
        color = colors[index % len(colors)]
        selected = candidate.mask
        result[selected] = np.rint(
            0.55 * result[selected].astype(np.float64) + 0.45 * color
        ).astype(np.uint8)
        x_min, y_min, x_max, y_max = candidate.bbox_xyxy
        left = max(0, min(candidate.image_width - 1, int(np.floor(x_min))))
        right = max(0, min(candidate.image_width - 1, int(np.ceil(x_max)) - 1))
        top = max(0, min(candidate.image_height - 1, int(np.floor(y_min))))
        bottom = max(0, min(candidate.image_height - 1, int(np.ceil(y_max)) - 1))
        byte_color = color.astype(np.uint8)
        result[top, left : right + 1] = byte_color
        result[bottom, left : right + 1] = byte_color
        result[top : bottom + 1, left] = byte_color
        result[top : bottom + 1, right] = byte_color
    from PIL import Image, ImageDraw, ImageFont

    image = Image.fromarray(result, mode="RGB")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    for index, candidate in enumerate(batch.candidates):
        color = tuple(int(value) for value in colors[index % len(colors)])
        left = max(0, min(candidate.image_width - 1, int(np.floor(candidate.bbox_xyxy[0]))))
        top = max(0, min(candidate.image_height - 1, int(np.floor(candidate.bbox_xyxy[1]))))
        label = f"{candidate.class_id} {candidate.confidence:.2f}"
        if candidate.segmentation_quality is not None:
            label += f" sam={candidate.segmentation_quality:.3f}"
        text_left, text_top, text_right, text_bottom = draw.textbbox(
            (0, 0), label, font=font
        )
        label_width = text_right - text_left + 4
        label_height = text_bottom - text_top + 4
        label_left = min(left, max(0, candidate.image_width - label_width))
        label_top = max(0, top - label_height)
        draw.rectangle(
            (
                label_left,
                label_top,
                label_left + label_width - 1,
                label_top + label_height - 1,
            ),
            fill=(16, 16, 16),
            outline=color,
        )
        draw.text(
            (label_left + 2, label_top + 2 - text_top),
            label,
            fill=(255, 255, 255),
            font=font,
        )
    return np.asarray(image, dtype=np.uint8)


def _candidate_document(
    candidate: DetectionCandidate,
    *,
    mask_artifact: Path,
) -> dict[str, object]:
    return {
        "instance_id": candidate.instance_id,
        "class_id": candidate.class_id,
        "confidence": candidate.confidence,
        "segmentation_quality": candidate.segmentation_quality,
        "bbox_xyxy": list(candidate.bbox_xyxy),
        "mask_pixel_count": int(candidate.mask.sum()),
        "mask_artifact": str(mask_artifact),
        "source_stamp_ns": candidate.source_stamp_ns,
        "source_frame_id": candidate.source_frame_id,
    }


def _atomic_json_no_replace(path: Path, document: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
    published = False
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as error:
            raise FileExistsError("model provenance path already exists") from error
        published = True
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
    if published:
        _fsync_directory(path.parent)


class PerceptionEvidenceWriter:
    def write_model_provenance(
        self, root: Path, document: Mapping[str, object]
    ) -> str:
        path = root / "model-provenance.json"
        if path.exists():
            raise FileExistsError("model provenance path already exists")
        _atomic_json_no_replace(path, document)
        return str(path)

    def write_detection(
        self,
        request: ObjectPoseRequest,
        batch: DetectionBatch,
    ) -> tuple[str, ...]:
        root = request.run_directory
        if root.exists() and root.is_symlink():
            raise OSError("run directory must not be a symlink")
        root.mkdir(parents=True, exist_ok=True)
        source = root / "source-rgb.png"
        overlay = root / "prediction-overlay.png"
        detections = root / "detections.json"
        candidate_masks = tuple(
            root / f"candidate-mask-{index:03d}.png"
            for index, _candidate in enumerate(batch.candidates)
        )
        if any(
            path.exists()
            for path in (source, overlay, detections, *candidate_masks)
        ):
            raise FileExistsError("detection evidence path already exists")
        _atomic_png(source, request.frame.rgb8)
        _atomic_png(overlay, render_detection_overlay(request.frame, batch))
        for candidate, path in zip(batch.candidates, candidate_masks, strict=True):
            pixels = np.zeros(
                (candidate.image_height, candidate.image_width, 3),
                dtype=np.uint8,
            )
            pixels[candidate.mask] = 255
            _atomic_png(path, pixels)
        atomic_json(
            detections,
            {
                "request_id": request.request_id,
                "model_id": batch.model_id,
                "weights_sha256": batch.weights_sha256,
                "runtime_device": batch.runtime_device,
                "inference_latency_ms": batch.inference_latency_ms,
                "image_width": batch.image_width,
                "image_height": batch.image_height,
                "candidates": [
                    _candidate_document(candidate, mask_artifact=mask_artifact)
                    for candidate, mask_artifact in zip(
                        batch.candidates, candidate_masks, strict=True
                    )
                ],
            },
        )
        return tuple(
            str(path) for path in (source, overlay, detections, *candidate_masks)
        )

    def write_selected(
        self,
        request: ObjectPoseRequest,
        candidate: DetectionCandidate,
    ) -> str:
        path = request.run_directory / "selected-mask.png"
        if path.exists():
            raise FileExistsError("selected mask evidence path already exists")
        pixels = np.zeros(
            (candidate.image_height, candidate.image_width, 3),
            dtype=np.uint8,
        )
        pixels[candidate.mask] = 255
        _atomic_png(path, pixels)
        return str(path)

    def write_localized(
        self,
        request: ObjectPoseRequest,
        localized: LocalizedObject,
    ) -> str:
        path = request.run_directory / "selected-cloud.ply"
        if path.exists():
            raise FileExistsError("selected cloud evidence path already exists")
        _atomic_ply(path, localized.points_world)
        return str(path)

    def write_result(self, request: ObjectPoseRequest, result: ObjectPoseResult) -> str:
        path = request.run_directory / "result.json"
        atomic_json(path, result.to_document())
        return str(path)
