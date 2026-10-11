"""Point transforms, cup pose fitting, the frame estimator and the frame processor."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest
from rgbd_cup_pose_support import _camera_partial_cylinder, _cloud, _fake_ros_api, _valid_frame


def _transform(*, translation, rotation_xyzw):
    return SimpleNamespace(
        transform=SimpleNamespace(
            translation=SimpleNamespace(
                x=translation[0], y=translation[1], z=translation[2]
            ),
            rotation=SimpleNamespace(
                x=rotation_xyzw[0],
                y=rotation_xyzw[1],
                z=rotation_xyzw[2],
                w=rotation_xyzw[3],
            ),
        )
    )


def _world_from_camera_transform():
    return _transform(
        translation=(0.10, -0.05, 0.02),
        rotation_xyzw=(0.0, 0.0, 0.0, 1.0),
    )


def test_transform_points_applies_rotation_before_translation() -> None:
    from so101_demo.cli.rgbd_cup_pose import transform_points

    points = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 2.0]])
    half_sqrt_two = np.sqrt(0.5)
    transform = _transform(
        translation=(1.0, 2.0, 3.0),
        rotation_xyzw=(0.0, 0.0, half_sqrt_two, half_sqrt_two),
    )

    np.testing.assert_allclose(
        transform_points(points, transform),
        np.array([[1.0, 3.0, 3.0], [0.0, 2.0, 5.0]]),
        atol=1e-12,
    )


def test_estimate_upright_cup_pose_fits_partial_cylinder_surface() -> None:
    from so101_demo.cli.rgbd_cup_pose import estimate_upright_cup_pose

    center, fitted_radius = estimate_upright_cup_pose(
        _camera_partial_cylinder(),
        table_top_z=0.12,
        cup_height=0.09,
        expected_radius=0.04,
        radius_tolerance=0.005,
    )

    np.testing.assert_allclose(center, np.array([0.02, -0.28, 0.165]), atol=1e-10)
    assert fitted_radius == pytest.approx(0.04, abs=1e-10)


def test_estimate_upright_cup_pose_rejects_wrong_radius() -> None:
    from so101_demo.cli.rgbd_cup_pose import estimate_upright_cup_pose

    angles = np.linspace(0.0, 2.0, 30)
    points = np.column_stack(
        (0.10 * np.cos(angles), 0.10 * np.sin(angles), np.full(len(angles), 0.2))
    )

    with pytest.raises(ValueError, match="fitted radius"):
        estimate_upright_cup_pose(
            points,
            table_top_z=0.12,
            cup_height=0.09,
            expected_radius=0.04,
            radius_tolerance=0.005,
        )


def test_estimate_world_cup_pose_transforms_points_before_circle_fit() -> None:
    from so101_demo.cli.rgbd_cup_pose import estimate_world_cup_pose

    estimate = estimate_world_cup_pose(
        _camera_partial_cylinder() - np.array([0.10, -0.05, 0.02]),
        _world_from_camera_transform(),
        table_top_z=0.12,
        cup_height=0.09,
        expected_radius=0.04,
        radius_tolerance=0.005,
    )

    np.testing.assert_allclose(estimate.center_world_xyz, (0.02, -0.28, 0.165), atol=1e-6)
    assert estimate.fitted_radius_m == pytest.approx(0.04, abs=1e-6)


def test_frame_estimator_uses_exact_source_stamp_and_bounded_tf_lookup() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions, estimate_cup_pose_frame

    cloud = _cloud(stamp_ns=20_000_000)
    source_stamp = SimpleNamespace(sec=0, nanosec=20_000_000)
    aligned = (
        SimpleNamespace(header=SimpleNamespace(stamp=source_stamp)),
        object(),
        object(),
    )
    lookup_calls = []

    def lookup(target_frame, source_frame, query_time, timeout_s):
        lookup_calls.append((target_frame, source_frame, query_time, timeout_s))
        return _transform(translation=(0.0, 0.0, 0.0), rotation_xyzw=(0.0, 0.0, 0.0, 1.0))

    frame = estimate_cup_pose_frame(
        aligned,
        RgbdCupPoseOptions(),
        build_cloud=lambda *_args, **_kwargs: cloud,
        lookup_transform=lookup,
        stamp_to_time=lambda stamp: (stamp.sec, stamp.nanosec),
        tf_timeout_budget=lambda: 0.07,
    )

    assert lookup_calls == [("world", "task_camera_frame", (0, 20_000_000), 0.07)]
    assert frame.stamp_ns == 20_000_000


def test_frame_estimator_profiles_exact_stamp_world_transform(tmp_path: Path) -> None:
    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions, estimate_cup_pose_frame

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        )
    )
    assert profiler is not None
    source_stamp = SimpleNamespace(sec=0, nanosec=20_000_000)
    aligned = (
        SimpleNamespace(header=SimpleNamespace(stamp=source_stamp)),
        object(),
        object(),
    )

    estimate_cup_pose_frame(
        aligned,
        RgbdCupPoseOptions(),
        build_cloud=lambda *_args, **_kwargs: _cloud(stamp_ns=20_000_000),
        lookup_transform=lambda *_args: _transform(
            translation=(0.0, 0.0, 0.0),
            rotation_xyzw=(0.0, 0.0, 0.0, 1.0),
        ),
        stamp_to_time=lambda stamp: (stamp.sec, stamp.nanosec),
        tf_timeout_budget=lambda: 0.07,
        profiler=profiler,
    )
    profiler.close()

    complete = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/perception.events.jsonl"
        ).read_text().splitlines()
        if '"event_type":"span_complete"' in line
    ]
    assert [event["name"] for event in complete] == ["perception.transform_world"]
    assert complete[0]["outcome"] == "accepted"


def test_prevalid_tf_timeout_is_capped_by_remaining_startup_budget() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import bounded_tf_timeout_s

    assert bounded_tf_timeout_s(
        0.2,
        first_valid_published=False,
        startup_deadline=10.05,
        monotonic=lambda: 10.0,
    ) == pytest.approx(0.05)
    assert bounded_tf_timeout_s(
        0.2,
        first_valid_published=True,
        startup_deadline=10.05,
        monotonic=lambda: 20.0,
    ) == 0.2


def test_failed_frame_never_republishes_last_valid_pose() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import CupPoseFrameProcessor

    published = []
    errors = []
    valid = object()

    def estimate(aligned):
        if aligned is valid:
            return _valid_frame()
        raise ValueError("fitted radius is outside tolerance")

    processor = CupPoseFrameProcessor(
        estimate=estimate,
        publish=published.append,
        on_error=errors.append,
    )
    assert processor.process(valid)
    assert not processor.process(object())
    assert len(published) == 1
    assert [str(error) for error in errors] == ["fitted radius is outside tolerance"]


def test_frame_processor_profiles_first_frame_wait_and_each_estimate(
    tmp_path: Path,
) -> None:
    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler
    from so101_demo.ros.rgbd_cup_pose.frames import CupPoseFrameProcessor

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        )
    )
    assert profiler is not None
    valid = object()

    def estimate(aligned):
        if aligned is valid:
            return _valid_frame()
        raise ValueError("bad radius")

    processor = CupPoseFrameProcessor(
        estimate=estimate,
        publish=lambda _frame: None,
        on_error=lambda _error: None,
        profiler=profiler,
    )

    assert processor.process(valid)
    assert not processor.process(object())
    profiler.close()

    complete = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/perception.events.jsonl"
        ).read_text().splitlines()
        if '"event_type":"span_complete"' in line
    ]
    assert [event["name"] for event in complete] == [
        "perception.wait_synchronized_frame",
        "perception.estimate_cup_pose",
        "perception.estimate_cup_pose",
    ]
    assert [event["outcome"] for event in complete] == [
        "available",
        "accepted",
        "rejected",
    ]


def test_profiled_startup_timeout_finishes_frame_wait_as_timeout(
    tmp_path: Path,
) -> None:
    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler
    from so101_demo.ros.rgbd_cup_pose.frames import CupPoseFrameProcessor, RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        )
    )
    assert profiler is not None
    processor = CupPoseFrameProcessor(
        estimate=lambda _aligned: _valid_frame(),
        publish=lambda _frame: None,
        on_error=lambda _error: None,
        profiler=profiler,
    )

    class Runtime:
        first_valid_published = False

        def ok(self) -> bool:
            return True

        def spin_once(self, _timeout_s: float) -> None:
            return None

        def finish_wait_span(self, outcome: str) -> None:
            processor.finish_wait(outcome)

        def close(self) -> None:
            return None

    runtime = Runtime()
    monotonic_values = iter((0.0, 0.0, 0.0, 0.0, 1.0))

    assert run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda *_args: runtime,
        monotonic=lambda: next(monotonic_values),
        open3d_preflight=lambda _remaining: None,
        profiler=profiler,
    ) == 1
    profiler.close()

    complete = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/perception.events.jsonl"
        ).read_text().splitlines()
        if '"event_type":"span_complete"' in line
        and '"name":"perception.wait_synchronized_frame"' in line
    ]
    assert [event["outcome"] for event in complete] == ["timeout"]


def test_profiled_runtime_construction_failure_finishes_frame_wait_as_error(
    tmp_path: Path,
) -> None:
    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler
    from so101_demo.ros.rgbd_cup_pose.frames import RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose.ros_runtime import _create_ros_runtime

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        )
    )
    assert profiler is not None
    ros_api, _rclpy, _node, _listener = _fake_ros_api(
        fail_subscription_number=1
    )

    with pytest.raises(RuntimeError, match="subscription construction failed"):
        _create_ros_runtime(
            RgbdCupPoseOptions(),
            startup_deadline=1.0,
            monotonic=lambda: 0.0,
            ros_api=ros_api,
            profiler=profiler,
        )
    profiler.close()

    complete = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/perception.events.jsonl"
        ).read_text().splitlines()
        if '"event_type":"span_complete"' in line
        and '"name":"perception.wait_synchronized_frame"' in line
    ]
    assert [event["outcome"] for event in complete] == ["error"]


def test_profiled_shutdown_before_first_frame_finishes_wait_as_interrupted(
    tmp_path: Path,
) -> None:
    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler
    from so101_demo.ros.rgbd_cup_pose.frames import CupPoseFrameProcessor, RgbdCupPoseOptions
    from so101_demo.ros.rgbd_cup_pose_node import run_rgbd_cup_pose

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        )
    )
    assert profiler is not None
    processor = CupPoseFrameProcessor(
        estimate=lambda _aligned: _valid_frame(),
        publish=lambda _frame: None,
        on_error=lambda _error: None,
        profiler=profiler,
    )

    class Runtime:
        first_valid_published = False

        def ok(self) -> bool:
            return False

        def spin_once(self, _timeout_s: float) -> None:
            raise AssertionError("shutdown runtime must not spin")

        def finish_wait_span(self, outcome: str) -> None:
            processor.finish_wait(outcome)

        def close(self) -> None:
            return None

    runtime = Runtime()
    monotonic_values = iter((0.0, 0.0, 0.0, 0.0))

    assert run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda *_args: runtime,
        monotonic=lambda: next(monotonic_values),
        open3d_preflight=lambda _remaining: None,
        profiler=profiler,
    ) == 1
    profiler.close()

    complete = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/perception.events.jsonl"
        ).read_text().splitlines()
        if '"event_type":"span_complete"' in line
        and '"name":"perception.wait_synchronized_frame"' in line
    ]
    assert [event["outcome"] for event in complete] == ["interrupted"]


def test_fresh_frame_gate_rejects_duplicate_and_out_of_order_stamps() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import FreshFrameGate

    gate = FreshFrameGate()

    assert gate.accept(20)
    assert not gate.accept(20)
    assert not gate.accept(19)
    assert gate.accept(21)


def test_pose_message_preserves_source_stamp_world_frame_and_identity_orientation() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import pose_message_from_frame

    message = SimpleNamespace(
        header=SimpleNamespace(stamp=None, frame_id=""),
        pose=SimpleNamespace(
            position=SimpleNamespace(x=0.0, y=0.0, z=0.0),
            orientation=SimpleNamespace(x=1.0, y=1.0, z=1.0, w=0.0),
        ),
    )

    result = pose_message_from_frame(
        _valid_frame(stamp_ns=20_000_000),
        pose_factory=lambda: message,
        stamp_from_ns=lambda stamp_ns: (stamp_ns // 1_000_000_000, stamp_ns % 1_000_000_000),
    )

    assert result.header.stamp == (0, 20_000_000)
    assert result.header.frame_id == "world"
    assert (result.pose.position.x, result.pose.position.y, result.pose.position.z) == (
        0.02,
        -0.28,
        0.165,
    )
    assert (
        result.pose.orientation.x,
        result.pose.orientation.y,
        result.pose.orientation.z,
        result.pose.orientation.w,
    ) == (0.0, 0.0, 0.0, 1.0)


def test_first_valid_evidence_is_written_once_while_fresh_frames_publish() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import (
        CupPoseFrameProcessor,
        FirstValidEvidencePublisher,
    )

    published = []
    ply_stamps = []
    json_stamps = []
    rgb_stamps = []
    full_stamps = []
    preview_stamps = []
    evidence_publisher = FirstValidEvidencePublisher(
        write_ply=lambda frame: ply_stamps.append(frame.stamp_ns),
        write_json=lambda frame: json_stamps.append(frame.stamp_ns),
        publish=published.append,
        write_rgb=lambda frame: rgb_stamps.append(frame.stamp_ns),
        write_full_ply=lambda frame: full_stamps.append(frame.stamp_ns),
        write_preview=lambda frame: preview_stamps.append(frame.stamp_ns),
    )
    frames = iter((_valid_frame(stamp_ns=20), _valid_frame(stamp_ns=21)))
    processor = CupPoseFrameProcessor(
        estimate=lambda _aligned: next(frames),
        publish=evidence_publisher,
        on_error=lambda error: pytest.fail(str(error)),
    )

    assert processor.process(object())
    assert processor.process(object())
    assert [frame.stamp_ns for frame in published] == [20, 21]
    assert ply_stamps == [20]
    assert json_stamps == [20]
    assert rgb_stamps == [20]
    assert full_stamps == [20]
    assert preview_stamps == [20]


def test_evidence_failure_is_fatal_and_prevents_publication() -> None:
    from so101_demo.ros.rgbd_cup_pose.frames import FirstValidEvidencePublisher

    published = []

    def fail(_frame) -> None:
        raise RuntimeError("evidence disk is full")

    publisher = FirstValidEvidencePublisher(
        write_ply=fail,
        write_json=lambda _frame: None,
        publish=published.append,
    )

    with pytest.raises(RuntimeError, match="evidence disk is full"):
        publisher(_valid_frame())
    assert published == []
