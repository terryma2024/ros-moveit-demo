from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from so101_demo.application.object_pose import ObjectPoseRequest, TargetSelector, detect_once
from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionFrame,
    DetectionQuery,
    LocalizedObject,
)
from so101_demo.ros.rgbd_cup_pose_node import FirstValidEvidencePublisher
from so101_demo.runtime.perception_evidence import PerceptionEvidenceWriter


class RecordingEmitter:
    component = "perception"

    def __init__(self, timeline: list[object] | None = None) -> None:
        self.events: list[tuple[str, dict[str, object], str | None]] = []
        self.timeline = timeline

    @property
    def last_event(self):
        if not self.events:
            return None
        return SimpleNamespace(event=self.events[-1][0])

    def emit(self, event: str, *, payload, failure_code=None):
        record = (event, dict(payload), failure_code)
        self.events.append(record)
        if self.timeline is not None:
            self.timeline.append(record)
        return SimpleNamespace(event=event)


def _candidate(instance_id: str = "cup-001") -> DetectionCandidate:
    mask = np.zeros((4, 6), dtype=np.bool_)
    mask[1:3, 2:4] = True
    return DetectionCandidate(
        instance_id=instance_id,
        class_id="plastic_cup",
        confidence=0.92,
        bbox_xyxy=(2.0, 1.0, 4.0, 3.0),
        mask=mask,
        source_stamp_ns=20,
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
        frame=DetectionFrame(
            np.zeros((4, 6, 3), dtype=np.uint8),
            source_stamp_ns=20,
            source_frame_id="task_camera_frame",
        ),
        camera_info=object(),
        depth_message=object(),
        query=DetectionQuery("plastic_cup"),
        confidence_threshold=0.5,
        run_directory=run_directory,
        cold_start_latency_ms=1.0,
    )


class Detector:
    def __init__(self, batch: DetectionBatch) -> None:
        self.batch = batch

    def detect(self, _frame, _query) -> DetectionBatch:
        return self.batch


class Localizer:
    def localize(self, selected, _camera_info, _depth, _lookup):
        return LocalizedObject(
            instance_id=selected.instance_id,
            class_id=selected.class_id,
            source_stamp_ns=selected.source_stamp_ns,
            source_frame_id=selected.source_frame_id,
            center_world_xyz=(0.02, -0.28, 0.165),
            fitted_radius_m=0.04,
            valid_depth_point_count=80,
            points_world=np.zeros((80, 3), dtype=np.float64),
        )


def test_color_publishes_one_workflow_event_after_first_successful_pose() -> None:
    timeline: list[object] = []
    emitter = RecordingEmitter(timeline)
    publisher = FirstValidEvidencePublisher(
        write_ply=lambda _frame: timeline.append("ply"),
        write_json=lambda _frame: timeline.append("json"),
        publish=lambda frame: timeline.append(("publish", frame.stamp_ns)),
        event_emitter=emitter,
    )
    frames = [
        SimpleNamespace(stamp_ns=20, source_frame_id="task_camera_frame"),
        SimpleNamespace(stamp_ns=21, source_frame_id="task_camera_frame"),
    ]

    publisher(frames[0])
    publisher(frames[1])

    assert publisher.published_count == 2
    assert emitter.events == [
        (
            "CUP_POSE_PUBLISHED",
            {"source_stamp_ns": 20, "frame_id": "task_camera_frame"},
            None,
        )
    ]
    assert timeline == [
        "ply",
        "json",
        ("publish", 20),
        emitter.events[0],
        ("publish", 21),
    ]


def test_color_evidence_failure_emits_no_publication_event() -> None:
    emitter = RecordingEmitter()

    def fail(_frame) -> None:
        raise OSError("disk full")

    publisher = FirstValidEvidencePublisher(
        write_ply=fail,
        write_json=lambda _frame: None,
        publish=lambda _frame: pytest.fail("pose must not publish"),
        event_emitter=emitter,
    )

    with pytest.raises(OSError, match="disk full"):
        publisher(SimpleNamespace(stamp_ns=20, source_frame_id="camera"))
    assert emitter.events == []


def test_model_success_orders_ready_selected_pose_and_published(tmp_path: Path) -> None:
    timeline: list[object] = []
    emitter = RecordingEmitter(timeline)
    emitter.emit("PERCEPTION_READY", payload={})

    result = detect_once(
        request=_request(tmp_path / "success"),
        detector=Detector(_batch(_candidate())),
        selector=TargetSelector(),
        localizer=Localizer(),
        evidence_writer=PerceptionEvidenceWriter(),
        pose_publisher=lambda _localized: timeline.append("publish-pose"),
        lookup_transform=lambda *_args: object(),
        event_emitter=emitter,
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert result.status == "OK"
    assert [event[0] for event in emitter.events] == [
        "PERCEPTION_READY",
        "TARGET_SELECTED",
        "CUP_POSE_PUBLISHED",
    ]
    assert emitter.events[1][1] == {
        "target_id": "cup-001",
        "class_name": "plastic_cup",
    }
    assert timeline.index("publish-pose") < timeline.index(emitter.events[2])


@pytest.mark.parametrize(
    ("candidates", "failure"),
    [
        ((), "TARGET_NOT_FOUND"),
        ((_candidate("cup-a"), _candidate("cup-b")), "TARGET_AMBIGUOUS"),
    ],
)
def test_model_selection_failure_emits_fixed_failure_and_never_publishes(
    tmp_path: Path,
    candidates: tuple[DetectionCandidate, ...],
    failure: str,
) -> None:
    emitter = RecordingEmitter()
    emitter.emit("PERCEPTION_READY", payload={})

    result = detect_once(
        request=_request(tmp_path / failure.lower()),
        detector=Detector(_batch(*candidates)),
        selector=TargetSelector(),
        localizer=Localizer(),
        evidence_writer=PerceptionEvidenceWriter(),
        pose_publisher=lambda _localized: pytest.fail("pose must not publish"),
        lookup_transform=lambda *_args: object(),
        event_emitter=emitter,
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert result.failure == failure
    assert emitter.events[-1] == ("PERCEPTION_FAILED", {}, failure)
    assert all(event[0] != "TARGET_SELECTED" for event in emitter.events)


def test_model_evidence_failure_selects_but_never_publishes(tmp_path: Path) -> None:
    emitter = RecordingEmitter()
    emitter.emit("PERCEPTION_READY", payload={})

    class FailedEvidenceWriter(PerceptionEvidenceWriter):
        def write_selected(self, *_args, **_kwargs):
            raise OSError("disk full")

    result = detect_once(
        request=_request(tmp_path / "evidence-failed"),
        detector=Detector(_batch(_candidate())),
        selector=TargetSelector(),
        localizer=Localizer(),
        evidence_writer=FailedEvidenceWriter(),
        pose_publisher=lambda _localized: pytest.fail("pose must not publish"),
        lookup_transform=lambda *_args: object(),
        event_emitter=emitter,
        monotonic_ns=iter([0, 10_000_000]).__next__,
    )

    assert result.failure == "EVIDENCE_WRITE_FAILED"
    assert [event[0] for event in emitter.events] == [
        "PERCEPTION_READY",
        "TARGET_SELECTED",
        "PERCEPTION_FAILED",
    ]


@pytest.mark.parametrize(
    ("module_name", "base_arguments"),
    [
        ("rgbd_cup_pose", []),
        ("rgbd_object_pose", ["--evidence-root", "/tmp/perception-evidence"]),
    ],
)
@pytest.mark.parametrize(
    "workflow_arguments",
    [
        ["--emit-workflow-events"],
        ["--workflow-id", "workflow-001"],
        ["--emit-workflow-events", "--workflow-id", "unsafe/workflow"],
    ],
)
def test_perception_cli_rejects_unpaired_or_unsafe_workflow_arguments(
    module_name: str,
    base_arguments: list[str],
    workflow_arguments: list[str],
) -> None:
    module = __import__(f"so101_demo.cli.{module_name}", fromlist=["main"])
    with pytest.raises(SystemExit) as error:
        module.main([*base_arguments, *workflow_arguments])
    assert error.value.code == 2


def test_model_cli_routes_events_to_stdout_and_status_to_stderr(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    from so101_demo.cli import rgbd_object_pose
    from so101_demo.ros import rgbd_object_pose_node

    weights = tmp_path / "best.pt"
    weights.write_bytes(b"weights")
    digest = hashlib.sha256(b"weights").hexdigest()

    def run(_options, *, event_emitter) -> int:
        print("ordinary status")
        event_emitter.emit("PERCEPTION_READY", payload={})
        return 0

    monkeypatch.setattr(rgbd_object_pose_node, "run_rgbd_object_pose", run)
    result = rgbd_object_pose.main(
        [
            "--weights",
            str(weights),
            "--weights-sha256",
            digest,
            "--request-id",
            "req-001",
            "--evidence-root",
            str(tmp_path / "evidence"),
            "--emit-workflow-events",
            "--workflow-id",
            "workflow-001",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.startswith("SO101_EVENT ")
    assert "ordinary status" not in captured.out
    assert captured.err == "ordinary status\n"


def test_color_cli_routes_events_to_stdout_and_status_to_stderr(
    monkeypatch, capsys
) -> None:
    from so101_demo.cli import rgbd_cup_pose
    from so101_demo.ros import rgbd_cup_pose_node

    def run(_options, *, event_emitter) -> int:
        print("ordinary color status")
        event_emitter.emit("PERCEPTION_READY", payload={})
        return 0

    monkeypatch.setattr(rgbd_cup_pose_node, "run_rgbd_cup_pose", run)
    result = rgbd_cup_pose.main(
        [
            "--emit-workflow-events",
            "--workflow-id",
            "workflow-001",
        ]
    )

    captured = capsys.readouterr()
    assert result == 0
    assert captured.out.startswith("SO101_EVENT ")
    assert "ordinary color status" not in captured.out
    assert captured.err == "ordinary color status\n"
