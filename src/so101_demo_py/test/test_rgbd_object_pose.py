from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from so101_demo.application.object_pose import (
    LocalizationError,
    ObjectPoseRequest,
    TargetSelector,
    detect_once,
)
from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionFrame,
    DetectionQuery,
    LocalizedObject,
)
from so101_demo.runtime.perception_evidence import PerceptionEvidenceWriter


def _frame() -> DetectionFrame:
    rgb = np.zeros((4, 6, 3), dtype=np.uint8)
    rgb[:, :, 1] = 40
    return DetectionFrame(rgb, 7, "task_camera_frame")


def _candidate(instance_id: str, *, confidence: float = 0.9) -> DetectionCandidate:
    mask = np.zeros((4, 6), dtype=bool)
    mask[1:3, 2:5] = True
    return DetectionCandidate(
        instance_id=instance_id,
        class_id="plastic_cup",
        confidence=confidence,
        bbox_xyxy=(2.0, 1.0, 5.0, 3.0),
        mask=mask,
        source_stamp_ns=7,
        source_frame_id="task_camera_frame",
        image_width=6,
        image_height=4,
    )


def _batch(*candidates: DetectionCandidate) -> DetectionBatch:
    return DetectionBatch(
        model_id="plastic-cup-yolo11n-seg-v1",
        weights_sha256="a" * 64,
        runtime_device="mps",
        inference_latency_ms=12.0,
        image_width=6,
        image_height=4,
        candidates=tuple(candidates),
    )


def _request(run_directory: Path) -> ObjectPoseRequest:
    return ObjectPoseRequest(
        request_id="req-001",
        frame=_frame(),
        camera_info=object(),
        depth_message=object(),
        query=DetectionQuery("plastic_cup"),
        confidence_threshold=0.50,
        run_directory=run_directory,
        cold_start_latency_ms=25.0,
    )


class _Detector:
    def __init__(self, batch: DetectionBatch) -> None:
        self.batch = batch

    def detect(self, frame: DetectionFrame, query: DetectionQuery) -> DetectionBatch:
        assert frame.source_stamp_ns == 7
        assert query.class_id == "plastic_cup"
        return self.batch


class _Localizer:
    def __init__(self, calls: list[str], *, failure: str | None = None) -> None:
        self.calls = calls
        self.failure = failure

    def localize(self, candidate, camera_info, depth_message, lookup_transform):
        self.calls.append("localize")
        if self.failure is not None:
            raise LocalizationError(self.failure, "rejected by test")
        assert candidate.instance_id == "cup"
        assert camera_info is not None and depth_message is not None
        assert lookup_transform("world", "task_camera_frame", 7) is not None
        angles = np.linspace(-1.0, 1.0, 60)
        points = np.column_stack(
            (
                0.02 + 0.04 * np.cos(angles),
                -0.28 + 0.04 * np.sin(angles),
                np.linspace(0.13, 0.21, len(angles)),
            )
        )
        return LocalizedObject(
            instance_id="cup",
            class_id="plastic_cup",
            source_stamp_ns=7,
            source_frame_id="task_camera_frame",
            center_world_xyz=(0.02, -0.28, 0.165),
            fitted_radius_m=0.04,
            valid_depth_point_count=len(points),
            points_world=points,
        )


def test_ambiguous_result_writes_candidates_but_never_localizes_or_publishes(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    run_directory = tmp_path / "ambiguous"

    result = detect_once(
        request=_request(run_directory),
        detector=_Detector(_batch(_candidate("cup-a"), _candidate("cup-b"))),
        selector=TargetSelector(),
        localizer=_Localizer(calls),
        evidence_writer=PerceptionEvidenceWriter(),
        pose_publisher=lambda _localized: calls.append("publish"),
        lookup_transform=lambda *_args: object(),
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert result.status == "ERROR"
    assert result.failure == "TARGET_AMBIGUOUS"
    assert result.matching_candidate_count == 2
    assert calls == []
    assert (run_directory / "source-rgb.png").is_file()
    assert (run_directory / "prediction-overlay.png").is_file()
    assert (run_directory / "detections.json").is_file()
    assert not (run_directory / "selected-mask.png").exists()
    assert not (run_directory / "selected-cloud.ply").exists()
    assert json.loads((run_directory / "result.json").read_text())["failure"] == (
        "TARGET_AMBIGUOUS"
    )


def test_success_writes_all_stage_evidence_before_publishing_pose(tmp_path: Path) -> None:
    calls: list[str] = []
    run_directory = tmp_path / "success"

    def publish(localized: LocalizedObject) -> None:
        for name in (
            "source-rgb.png",
            "prediction-overlay.png",
            "detections.json",
            "selected-mask.png",
            "selected-cloud.ply",
            "result.json",
        ):
            assert (run_directory / name).is_file()
        assert localized.center_world_xyz == (0.02, -0.28, 0.165)
        calls.append("publish")

    result = detect_once(
        request=_request(run_directory),
        detector=_Detector(_batch(_candidate("cup"))),
        selector=TargetSelector(),
        localizer=_Localizer(calls),
        evidence_writer=PerceptionEvidenceWriter(),
        pose_publisher=publish,
        lookup_transform=lambda *_args: SimpleNamespace(transform=True),
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert calls == ["localize", "publish"]
    assert result.status == "OK"
    assert result.failure is None
    assert result.published_cup_pose
    document = json.loads((run_directory / "result.json").read_text())
    assert document["published_cup_pose"] is True
    assert document["candidate_count"] == 1
    assert document["matching_candidate_count"] == 1
    assert document["request_latency_ms"] == 10.0


def test_localization_failure_keeps_selected_mask_but_never_publishes(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    run_directory = tmp_path / "geometry-rejected"

    result = detect_once(
        request=_request(run_directory),
        detector=_Detector(_batch(_candidate("cup"))),
        selector=TargetSelector(),
        localizer=_Localizer(calls, failure="GEOMETRY_REJECTED"),
        evidence_writer=PerceptionEvidenceWriter(),
        pose_publisher=lambda _localized: calls.append("publish"),
        lookup_transform=lambda *_args: object(),
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert result.failure == "GEOMETRY_REJECTED"
    assert calls == ["localize"]
    assert (run_directory / "selected-mask.png").is_file()
    assert not (run_directory / "selected-cloud.ply").exists()


def test_evidence_failure_prevents_pose_publication(tmp_path: Path) -> None:
    calls: list[str] = []

    class FailedEvidenceWriter(PerceptionEvidenceWriter):
        def write_selected(self, *_args, **_kwargs):
            raise OSError("disk full")

    result = detect_once(
        request=_request(tmp_path / "evidence-failed"),
        detector=_Detector(_batch(_candidate("cup"))),
        selector=TargetSelector(),
        localizer=_Localizer(calls),
        evidence_writer=FailedEvidenceWriter(),
        pose_publisher=lambda _localized: calls.append("publish"),
        lookup_transform=lambda *_args: object(),
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert result.failure == "EVIDENCE_WRITE_FAILED"
    assert calls == []
