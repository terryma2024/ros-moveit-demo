from __future__ import annotations

import json
import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

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
from so101_demo.adapters.perception.detector_factory import BuiltDetector
from so101_demo.runtime.perception_evidence import (
    PerceptionEvidenceWriter,
    render_detection_overlay,
)
from so101_demo.ros.rgbd_object_pose_node import (
    FreshFrameGate,
    RgbdObjectPoseOptions,
    _publish_and_confirm,
    _wait_for_output_subscribers,
    _wait_for_transform,
)


def _frame() -> DetectionFrame:
    rgb = np.zeros((4, 6, 3), dtype=np.uint8)
    rgb[:, :, 1] = 40
    return DetectionFrame(rgb, 7, "task_camera_frame")


def _candidate(
    instance_id: str,
    *,
    confidence: float = 0.9,
    segmentation_quality: float | None = None,
) -> DetectionCandidate:
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
        segmentation_quality=segmentation_quality,
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


def test_one_shot_outputs_wait_for_discovery_and_ack_before_cleanup() -> None:
    events: list[str] = []
    clock = [0.0]

    class Publisher:
        def __init__(self, topic: str) -> None:
            self.topic = topic
            self.discovered = False

        def get_subscription_count(self) -> int:
            return int(self.discovered)

        def publish(self, _message: object) -> None:
            events.append(f"publish:{self.topic}")

        def wait_for_all_acked(self, _timeout: object) -> bool:
            events.append(f"ack:{self.topic}")
            return True

    detections = Publisher("detections")
    overlay = Publisher("overlay")
    pose = Publisher("pose")

    def spin_once(timeout_s: float) -> None:
        events.append("spin")
        clock[0] += timeout_s
        detections.discovered = True
        overlay.discovered = True
        pose.discovered = True

    assert _wait_for_output_subscribers(
        (detections, overlay, pose),
        spin_once=spin_once,
        timeout_s=0.5,
        monotonic=lambda: clock[0],
    )
    _publish_and_confirm(detections, object(), ack_timeout=object())
    _publish_and_confirm(overlay, object(), ack_timeout=object())
    _publish_and_confirm(pose, object(), ack_timeout=object())

    assert events == [
        "spin",
        "publish:detections",
        "ack:detections",
        "publish:overlay",
        "ack:overlay",
        "publish:pose",
        "ack:pose",
    ]


def test_one_shot_waits_for_exact_source_transform_before_request() -> None:
    clock = [0.0]
    calls: list[tuple[str, str, int]] = []

    def can_transform(target: str, source: str, stamp_ns: int) -> bool:
        calls.append((target, source, stamp_ns))
        return len(calls) >= 2

    def spin_once(timeout_s: float) -> None:
        clock[0] += timeout_s

    assert _wait_for_transform(
        can_transform,
        target_frame="world",
        source_frame="task_camera_frame",
        source_stamp_ns=7,
        spin_once=spin_once,
        timeout_s=0.5,
        monotonic=lambda: clock[0],
    )
    assert calls == [
        ("world", "task_camera_frame", 7),
        ("world", "task_camera_frame", 7),
    ]


def test_overlay_draws_visible_class_and_confidence_label() -> None:
    rgb = np.full((80, 160, 3), 120, dtype=np.uint8)
    frame = DetectionFrame(rgb, 7, "task_camera_frame")
    mask = np.zeros((80, 160), dtype=bool)
    mask[30:65, 35:95] = True
    candidate = DetectionCandidate(
        instance_id="cup",
        class_id="plastic_cup",
        confidence=0.91,
        bbox_xyxy=(35.0, 30.0, 95.0, 65.0),
        mask=mask,
        source_stamp_ns=7,
        source_frame_id="task_camera_frame",
        image_width=160,
        image_height=80,
    )

    batch = DetectionBatch(
        model_id="plastic-cup-yolo11n-seg-v1",
        weights_sha256="a" * 64,
        runtime_device="mps",
        inference_latency_ms=12.0,
        image_width=160,
        image_height=80,
        candidates=(candidate,),
    )
    overlay = render_detection_overlay(frame, batch)
    label_region = overlay[16:30, 35:140]

    assert (label_region.max(axis=2) < 40).any(), "label background is missing"
    assert (label_region.min(axis=2) > 220).any(), "label glyphs are missing"


def test_overlay_writes_exact_yolo_and_sam_quality_labels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from PIL import ImageDraw

    rgb = np.full((80, 160, 3), 120, dtype=np.uint8)
    frame = DetectionFrame(rgb, 7, "task_camera_frame")
    mask = np.zeros((80, 160), dtype=bool)
    mask[30:65, 35:95] = True
    labels: list[str] = []
    original_draw = ImageDraw.Draw

    class CapturingDraw:
        def __init__(self, image: object) -> None:
            self._draw = original_draw(image)

        def __getattr__(self, name: str) -> object:
            return getattr(self._draw, name)

        def text(self, xy: object, text: str, **kwargs: object) -> None:
            labels.append(text)
            self._draw.text(xy, text, **kwargs)

    monkeypatch.setattr(ImageDraw, "Draw", CapturingDraw)

    def batch_for(quality: float | None) -> DetectionBatch:
        return DetectionBatch(
            model_id="plastic-cup-yolo11n-seg-v1",
            weights_sha256="a" * 64,
            runtime_device="mps",
            inference_latency_ms=12.0,
            image_width=160,
            image_height=80,
            candidates=(
                DetectionCandidate(
                    instance_id="cup",
                    class_id="plastic_cup",
                    confidence=0.91,
                    bbox_xyxy=(35.0, 30.0, 95.0, 65.0),
                    mask=mask,
                    source_stamp_ns=7,
                    source_frame_id="task_camera_frame",
                    image_width=160,
                    image_height=80,
                    segmentation_quality=quality,
                ),
            ),
        )

    render_detection_overlay(frame, batch_for(None))
    render_detection_overlay(frame, batch_for(0.82))

    assert labels == ["plastic_cup 0.91", "plastic_cup 0.91 sam=0.820"]


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


def test_detection_evidence_records_segmentation_quality(tmp_path: Path) -> None:
    writer = PerceptionEvidenceWriter()
    artifacts = writer.write_detection(
        _request(tmp_path), _batch(_candidate("cup", segmentation_quality=0.82))
    )
    document = json.loads((tmp_path / "detections.json").read_text())

    assert document["candidates"][0]["segmentation_quality"] == 0.82
    assert artifacts


def test_detection_evidence_normalizes_numpy_quality_to_json_float(tmp_path: Path) -> None:
    PerceptionEvidenceWriter().write_detection(
        _request(tmp_path),
        _batch(_candidate("cup", segmentation_quality=np.float32(0.82))),
    )
    document = json.loads((tmp_path / "detections.json").read_text())

    assert document["candidates"][0]["segmentation_quality"] == pytest.approx(0.82)
    assert type(document["candidates"][0]["segmentation_quality"]) is float


def test_detection_evidence_records_null_quality_for_yolo_candidates(
    tmp_path: Path,
) -> None:
    PerceptionEvidenceWriter().write_detection(_request(tmp_path), _batch(_candidate("cup")))
    document = json.loads((tmp_path / "detections.json").read_text())

    assert document["candidates"][0]["segmentation_quality"] is None


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
        detection_publisher=lambda _batch, _overlay: calls.append("publish-detections"),
        lookup_transform=lambda *_args: object(),
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert result.status == "ERROR"
    assert result.failure == "TARGET_AMBIGUOUS"
    assert result.matching_candidate_count == 2
    assert calls == ["publish-detections"]
    assert (run_directory / "source-rgb.png").is_file()
    assert (run_directory / "prediction-overlay.png").is_file()
    assert (run_directory / "detections.json").is_file()
    candidate_masks = [
        run_directory / "candidate-mask-000.png",
        run_directory / "candidate-mask-001.png",
    ]
    assert all(path.is_file() for path in candidate_masks)
    detections = json.loads((run_directory / "detections.json").read_text())
    assert [item["mask_artifact"] for item in detections["candidates"]] == [
        str(path) for path in candidate_masks
    ]
    assert all(str(path) in result.artifact_paths for path in candidate_masks)
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
        detection_publisher=lambda _batch, _overlay: calls.append("publish-detections"),
        lookup_transform=lambda *_args: SimpleNamespace(transform=True),
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert calls == ["publish-detections", "localize", "publish"]
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
        detection_publisher=lambda _batch, _overlay: calls.append("publish-detections"),
        lookup_transform=lambda *_args: object(),
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert result.failure == "GEOMETRY_REJECTED"
    assert calls == ["publish-detections", "localize"]
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
        detection_publisher=lambda _batch, _overlay: calls.append("publish-detections"),
        lookup_transform=lambda *_args: object(),
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert result.failure == "EVIDENCE_WRITE_FAILED"
    assert calls == ["publish-detections"]


def _stamped(stamp_ns: int):
    return SimpleNamespace(
        header=SimpleNamespace(
            stamp=SimpleNamespace(
                sec=stamp_ns // 1_000_000_000,
                nanosec=stamp_ns % 1_000_000_000,
            )
        )
    )


def test_fresh_frame_gate_rejects_cached_or_misaligned_samples() -> None:
    gate = FreshFrameGate(minimum_source_stamp_ns=10)

    assert gate.accept((_stamped(10), _stamped(10), _stamped(10))) is None
    assert gate.accept((_stamped(11), _stamped(12), _stamped(11))) is None
    fresh = (_stamped(13), _stamped(13), _stamped(13))
    assert gate.accept(fresh) is fresh
    assert gate.accept((_stamped(14), _stamped(14), _stamped(14))) is fresh


def test_rgbd_object_pose_options_require_local_weight_and_absolute_evidence(
    tmp_path: Path,
) -> None:
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    digest = hashlib.sha256(b"weights-v1").hexdigest()

    options = RgbdObjectPoseOptions(
        weights_path=weights,
        weights_sha256=digest,
        request_id="req-001",
        evidence_root=tmp_path / "evidence",
        once=True,
        device="mps",
    )

    assert options.weights_path == weights
    assert options.once
    for invalid_path, message in [
        (Path("relative.pt"), "weights_path"),
        (tmp_path / "missing.pt", "regular file"),
    ]:
        with pytest.raises(ValueError, match=message):
            RgbdObjectPoseOptions(
                weights_path=invalid_path,
                weights_sha256=digest,
                request_id="req-001",
                evidence_root=tmp_path / "evidence",
            )
    linked_weights = tmp_path / "linked.pt"
    linked_weights.symlink_to(weights)
    with pytest.raises(ValueError, match="regular file"):
        RgbdObjectPoseOptions(
            weights_path=linked_weights,
            weights_sha256=digest,
            request_id="req-001",
            evidence_root=tmp_path / "evidence",
        )
    with pytest.raises(ValueError, match="evidence_root"):
        RgbdObjectPoseOptions(
            weights_path=weights,
            weights_sha256=digest,
            request_id="req-001",
            evidence_root=Path("relative"),
        )


def test_rgbd_object_pose_cli_constructs_explicit_once_request(
    tmp_path: Path, monkeypatch
) -> None:
    from so101_demo.cli import rgbd_object_pose
    from so101_demo.ros import rgbd_object_pose_node

    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights-v1")
    digest = hashlib.sha256(b"weights-v1").hexdigest()
    calls: list[RgbdObjectPoseOptions] = []
    monkeypatch.setattr(
        rgbd_object_pose_node,
        "run_rgbd_object_pose",
        lambda options: calls.append(options) or 17,
    )

    assert (
        rgbd_object_pose.main(
            [
                "--weights",
                str(weights),
                "--weights-sha256",
                digest,
                "--device",
                "mps",
                "--request-id",
                "req-001",
                "--evidence-root",
                str(tmp_path / "evidence"),
                "--once",
            ]
        )
        == 17
    )
    assert len(calls) == 1
    assert calls[0].device == "mps"
    assert calls[0].once


def test_grounded_sam_cli_constructs_backend_specific_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Catch CLI forwarding Grounded SAM arguments into the legacy YOLO fields."""

    from so101_demo.cli import rgbd_object_pose
    from so101_demo.ros import rgbd_object_pose_node

    calls: list[RgbdObjectPoseOptions] = []
    monkeypatch.setattr(
        rgbd_object_pose_node,
        "run_rgbd_object_pose",
        lambda options: calls.append(options) or 17,
    )

    result = rgbd_object_pose.main(
        [
            "--backend",
            "grounded_sam",
            "--model-root",
            str(tmp_path / "bundle"),
            "--model-manifest-sha256",
            "a" * 64,
            "--grounding-box-threshold",
            "0.40",
            "--grounding-text-threshold",
            "0.30",
            "--duplicate-iou",
            "0.80",
            "--max-candidates",
            "8",
            "--sam-quality-threshold",
            "0.70",
            "--min-mask-pixels",
            "80",
            "--max-mask-area-ratio",
            "0.45",
            "--device",
            "mps",
            "--request-id",
            "req-001",
            "--evidence-root",
            str(tmp_path / "evidence"),
            "--once",
        ]
    )

    assert result == 17
    assert calls[0].backend == "grounded_sam"
    assert calls[0].model_root == tmp_path / "bundle"
    assert calls[0].weights_path is None
    factory_options = calls[0].to_detector_factory_options()
    assert factory_options.backend == "grounded_sam"
    assert factory_options.grounded_model_root == tmp_path / "bundle"
    assert factory_options.grounded_thresholds is not None
    assert factory_options.grounded_thresholds.box_threshold == 0.40
    assert factory_options.grounded_thresholds.text_threshold == 0.30
    assert factory_options.grounded_thresholds.duplicate_iou == 0.80
    assert factory_options.grounded_thresholds.max_candidates == 8
    assert factory_options.grounded_thresholds.sam_quality == 0.70
    assert factory_options.grounded_thresholds.min_mask_pixels == 80
    assert factory_options.grounded_thresholds.max_mask_area_ratio == 0.45


@pytest.mark.parametrize(
    ("flag", "value"),
    [("--model-id", "yolo-only-id"), ("--imgsz", "512")],
)
def test_grounded_sam_cli_rejects_explicit_yolo_only_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, flag: str, value: str
) -> None:
    """Catch Grounded SAM silently accepting a caller's YOLO-only setting."""

    from so101_demo.cli import rgbd_object_pose
    from so101_demo.ros import rgbd_object_pose_node

    monkeypatch.setattr(
        rgbd_object_pose_node,
        "run_rgbd_object_pose",
        lambda _options: pytest.fail("invalid Grounded-SAM options reached the runner"),
    )
    with pytest.raises(SystemExit, match="2"):
        rgbd_object_pose.main(
            [
                "--backend",
                "grounded_sam",
                "--model-root",
                str(tmp_path / "bundle"),
                "--model-manifest-sha256",
                "a" * 64,
                flag,
                value,
                "--request-id",
                "req-001",
                "--evidence-root",
                str(tmp_path / "evidence"),
            ]
        )


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--backend", "grounded_sam"], "model_root"),
        (["--backend", "yolo_seg"], "weights_path"),
        (
            [
                "--backend",
                "grounded_sam",
                "--weights",
                "/tmp/best.pt",
                "--weights-sha256",
                "a" * 64,
                "--model-root",
                "/tmp/bundle",
                "--model-manifest-sha256",
                "a" * 64,
            ],
            "backend configuration",
        ),
    ],
)
def test_options_reject_missing_and_cross_backend_artifacts(
    tmp_path: Path, arguments: list[str], message: str
) -> None:
    """Catch a request reaching ROS setup with incomplete backend selection."""

    del tmp_path
    with pytest.raises(ValueError, match=message):
        RgbdObjectPoseOptions(
            backend="grounded_sam" if "grounded_sam" in arguments else "yolo_seg",
            weights_path=Path("/tmp/best.pt") if "--weights" in arguments else None,
            weights_sha256="a" * 64 if "--weights" in arguments else None,
            model_root=Path("/tmp/bundle") if "--model-root" in arguments else None,
            model_manifest_sha256=("a" * 64 if "--model-manifest-sha256" in arguments else None),
            request_id="req-001",
            evidence_root=Path("/tmp/evidence"),
        )


def test_yolo_options_reject_grounded_sam_thresholds(tmp_path: Path) -> None:
    """Catch activating a Grounded-SAM-only threshold in the YOLO request path."""

    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    with pytest.raises(ValueError, match="backend configuration"):
        RgbdObjectPoseOptions(
            weights_path=weights,
            weights_sha256=hashlib.sha256(b"weights").hexdigest(),
            grounding_box_threshold=0.35,
            request_id="req-001",
            evidence_root=tmp_path / "evidence",
        )


def test_run_refuses_evidence_failure_before_ros_setup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catch opening ROS subscriptions after immutable model provenance cannot be retained."""

    from so101_demo.ros import rgbd_object_pose_node

    class Detector:
        runtime_device = "mps"
        cold_start_latency_ms = 1.0

    class FailedWriter:
        def write_model_provenance(self, _root: Path, _document: object) -> str:
            raise OSError("disk full")

    monkeypatch.setattr(
        rgbd_object_pose_node,
        "build_detector",
        lambda _options: BuiltDetector(
            detector=Detector(),
            cold_start_latency_ms=1.0,
            provenance_document={"backend": "yolo_seg"},
        ),
    )
    monkeypatch.setattr(rgbd_object_pose_node, "PerceptionEvidenceWriter", FailedWriter)
    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")

    result = rgbd_object_pose_node.run_rgbd_object_pose(
        RgbdObjectPoseOptions(
            weights_path=weights,
            weights_sha256=hashlib.sha256(b"weights").hexdigest(),
            request_id="req-001",
            evidence_root=tmp_path / "evidence",
        )
    )

    assert result == 1
    assert json.loads(capsys.readouterr().out)["status"] == "ERROR"
