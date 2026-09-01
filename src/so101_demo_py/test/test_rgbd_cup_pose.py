from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest


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


def _camera_partial_cylinder() -> np.ndarray:
    angles = np.linspace(-1.1, 1.2, 80)
    center_xy = np.array([0.02, -0.28])
    radius = 0.04
    xy = center_xy + radius * np.column_stack((np.cos(angles), np.sin(angles)))
    return np.column_stack((xy, np.linspace(0.175, 0.210, len(xy))))


def _world_from_camera_transform():
    return _transform(
        translation=(0.10, -0.05, 0.02),
        rotation_xyzw=(0.0, 0.0, 0.0, 1.0),
    )


def _cloud(*, stamp_ns: int):
    from so101_demo.cli.rgbd_point_cloud import CupPointCloudResult

    return CupPointCloudResult(
        frame_id="task_camera_frame",
        stamp_ns=stamp_ns,
        image_width=640,
        image_height=480,
        intrinsics_fx_fy_cx_cy=(500.0, 500.0, 320.0, 240.0),
        points_xyz=_camera_partial_cylinder(),
        colors_rgb=np.ones((80, 3)),
        full_point_count=1000,
        color_candidate_point_count=100,
    )


def _valid_frame(*, stamp_ns: int = 20):
    from so101_demo.ros.rgbd_cup_pose_node import CupPoseFrame

    return CupPoseFrame(
        stamp_ns=stamp_ns,
        source_frame_id="task_camera_frame",
        center_world_xyz=(0.02, -0.28, 0.165),
        fitted_radius_m=0.04,
        cloud=_cloud(stamp_ns=stamp_ns),
    )


class _FakeRclpy:
    def __init__(self) -> None:
        self.initialized = False
        self.shutdown_calls = 0
        self.try_shutdown_calls = 0

    def ok(self) -> bool:
        return self.initialized

    def init(self) -> None:
        self.initialized = True

    def shutdown(self) -> None:
        self.shutdown_calls += 1
        if not self.initialized:
            raise RuntimeError("rclpy context is already shut down")
        self.initialized = False

    def try_shutdown(self) -> None:
        self.try_shutdown_calls += 1
        self.initialized = False

    def spin_once(self, _node, *, timeout_sec: float) -> None:
        assert timeout_sec >= 0.0


class _FakeNode:
    def __init__(self, *, fail_subscription_number: int | None = None) -> None:
        self.fail_subscription_number = fail_subscription_number
        self.publisher_calls = []
        self.subscription_calls = []
        self.destroyed_publishers = []
        self.destroyed_subscriptions = []
        self.destroyed = False
        self.info_messages = []

    def create_publisher(self, message_type, topic, qos):
        publisher = SimpleNamespace(publish=lambda _message: None)
        self.publisher_calls.append((message_type, topic, qos, publisher))
        return publisher

    def create_subscription(self, message_type, topic, callback, qos, **kwargs):
        number = len(self.subscription_calls) + 1
        if number == self.fail_subscription_number:
            raise RuntimeError("subscription construction failed")
        subscription = object()
        self.subscription_calls.append(
            (message_type, topic, callback, qos, subscription, kwargs)
        )
        return subscription

    def destroy_publisher(self, publisher) -> None:
        self.destroyed_publishers.append(publisher)

    def destroy_subscription(self, subscription) -> None:
        self.destroyed_subscriptions.append(subscription)

    def destroy_node(self) -> None:
        self.destroyed = True

    def get_logger(self):
        return SimpleNamespace(
            error=lambda _message: None,
            info=self.info_messages.append,
        )


def _fake_ros_api(*, fail_subscription_number: int | None = None):
    fake_rclpy = _FakeRclpy()
    node = _FakeNode(fail_subscription_number=fail_subscription_number)
    listener = SimpleNamespace(unregister_calls=0)

    def unregister() -> None:
        listener.unregister_calls += 1

    listener.unregister = unregister
    fake_rclpy.create_node = lambda *_args, **_kwargs: node
    api = SimpleNamespace(
        rclpy=fake_rclpy,
        PoseStamped=object,
        ClockType=SimpleNamespace(ROS_TIME="ros-time"),
        Duration=lambda *, seconds: ("duration", seconds),
        ExternalShutdownException=type("ExternalShutdownException", (Exception,), {}),
        Parameter=lambda *args, **kwargs: (args, kwargs),
        DurabilityPolicy=SimpleNamespace(VOLATILE="volatile"),
        QoSProfile=lambda **kwargs: SimpleNamespace(**kwargs),
        ReliabilityPolicy=SimpleNamespace(RELIABLE="reliable"),
        SubscriptionEventCallbacks=lambda **kwargs: SimpleNamespace(**kwargs),
        qos_profile_sensor_data=object(),
        Time=SimpleNamespace(from_msg=lambda stamp: stamp),
        CameraInfo=type("CameraInfo", (), {}),
        Image=type("Image", (), {}),
        Buffer=lambda: SimpleNamespace(lookup_transform=lambda *_args, **_kwargs: None),
        TransformException=type("TransformException", (Exception,), {}),
        TransformListener=lambda _buffer, _node: listener,
    )
    return api, fake_rclpy, node, listener


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
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        estimate_cup_pose_frame,
    )

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
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        estimate_cup_pose_frame,
    )

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
    from so101_demo.ros.rgbd_cup_pose_node import bounded_tf_timeout_s

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
    from so101_demo.ros.rgbd_cup_pose_node import CupPoseFrameProcessor

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
    from so101_demo.ros.rgbd_cup_pose_node import CupPoseFrameProcessor

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
    from so101_demo.ros.rgbd_cup_pose_node import (
        CupPoseFrameProcessor,
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

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
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        _create_ros_runtime,
    )

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
    from so101_demo.ros.rgbd_cup_pose_node import (
        CupPoseFrameProcessor,
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

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
    from so101_demo.ros.rgbd_cup_pose_node import FreshFrameGate

    gate = FreshFrameGate()

    assert gate.accept(20)
    assert not gate.accept(20)
    assert not gate.accept(19)
    assert gate.accept(21)


def test_pose_message_preserves_source_stamp_world_frame_and_identity_orientation() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import pose_message_from_frame

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
    from so101_demo.ros.rgbd_cup_pose_node import (
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
    from so101_demo.ros.rgbd_cup_pose_node import FirstValidEvidencePublisher

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


def test_open3d_absence_is_an_actionable_preflight_error(monkeypatch) -> None:
    from so101_demo.ros import rgbd_cup_pose_node

    monkeypatch.setattr(rgbd_cup_pose_node.importlib.util, "find_spec", lambda _name: None)

    with pytest.raises(RuntimeError, match="python3 -m pip install open3d"):
        rgbd_cup_pose_node._require_open3d(1.0)


def test_open3d_discoverable_but_import_broken_fails_preflight() -> None:
    from so101_demo.ros import rgbd_cup_pose_node

    def broken_import(_name: str):
        raise ImportError("dlopen native library failed")

    with pytest.raises(RuntimeError, match="Open3D is unusable.*dlopen"):
        rgbd_cup_pose_node._require_open3d(
            1.0,
            find_spec=lambda _name: object(),
            importer=broken_import,
        )


def test_startup_deadline_is_monotonic_and_fails_after_only_invalid_frames(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        CupPoseFrameProcessor,
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    errors = []

    def reject(_aligned):
        raise ValueError("fitted radius is outside tolerance")

    processor = CupPoseFrameProcessor(
        estimate=reject,
        publish=lambda _frame: pytest.fail("invalid frame was published"),
        on_error=errors.append,
    )

    class FakeRuntime:
        first_valid_published = False

        def spin_once(self, _timeout_s: float) -> None:
            assert not processor.process(object())

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            return None

    monotonic_values = iter((10.0, 10.05, 10.10, 10.15, 10.25, 10.50, 11.01))
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: FakeRuntime(),
        monotonic=lambda: next(monotonic_values),
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert len(errors) == 2
    assert "RGBD_CUP_POSE_TIMEOUT" in capsys.readouterr().out


def test_run_profiles_total_without_changing_success_result(tmp_path: Path) -> None:
    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler
    from so101_demo.ros.rgbd_cup_pose_node import RgbdCupPoseOptions, run_rgbd_cup_pose

    class FakeRuntime:
        first_valid_published = True

        def ok(self) -> bool:
            return False

        def spin_once(self, _timeout_s: float) -> None:
            raise AssertionError("stopped runtime spun")

        def close(self) -> None:
            pass

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.SUMMARY,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        )
    )
    assert profiler is not None

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(),
        runtime_factory=lambda *_args: FakeRuntime(),
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining: None,
        profiler=profiler,
    )
    profiler.close()

    assert result == 0
    complete = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/perception.events.jsonl"
        ).read_text().splitlines()
        if '"event_type":"span_complete"' in line
    ]
    assert complete[-1]["name"] == "perception.total"
    assert complete[-1]["outcome"] == "published"


def test_startup_budget_begins_before_preflight_and_runtime_construction(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = False
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            pytest.fail("expired startup budget reached spin")

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            self.closed = True

    times = iter((10.0, 10.4, 11.1))
    observed_preflight_budgets = []

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda *_args: pytest.fail("expired preflight reached construction"),
        monotonic=lambda: next(times),
        open3d_preflight=observed_preflight_budgets.append,
    )

    assert result != 0
    assert observed_preflight_budgets == [pytest.approx(0.6)]
    assert "RGBD_CUP_POSE_TIMEOUT" in capsys.readouterr().out


def test_runtime_construction_overrun_is_closed_before_spin(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = False
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            pytest.fail("expired construction reached spin")

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    times = iter((10.0, 10.1, 10.2, 10.3, 11.1))

    def construct(_options, _deadline, construction_clock):
        assert construction_clock() == 10.3
        return runtime

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=construct,
        monotonic=lambda: next(times),
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert runtime.closed
    assert "RGBD_CUP_POSE_TIMEOUT" in capsys.readouterr().out


def test_prevalid_spin_wait_cannot_exceed_remaining_startup_budget() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = False

        def __init__(self) -> None:
            self.running = True
            self.spin_timeouts = []

        def spin_once(self, timeout_s: float) -> None:
            self.spin_timeouts.append(timeout_s)
            self.running = False

        def ok(self) -> bool:
            return self.running

        def close(self) -> None:
            return None

    runtime = FakeRuntime()
    times = iter((10.0, 10.1, 10.2, 10.3, 10.98))
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: next(times),
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert runtime.spin_timeouts == [pytest.approx(0.02)]


def test_context_shutdown_before_first_valid_pose_is_nonzero(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = False
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            pytest.fail("stopped runtime reached spin")

        def ok(self) -> bool:
            return False

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert runtime.closed
    assert "RGBD_CUP_POSE_SHUTDOWN_BEFORE_FIRST_VALID" in capsys.readouterr().out


@pytest.mark.parametrize("interrupt_phase", ["preflight", "construction"])
def test_setup_sigint_is_actionable_nonzero_without_traceback(interrupt_phase, capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    def preflight(_remaining_s: float) -> None:
        if interrupt_phase == "preflight":
            raise KeyboardInterrupt

    def construct(_options, _deadline, _monotonic):
        if interrupt_phase == "construction":
            raise KeyboardInterrupt
        pytest.fail("preflight interrupt reached construction")

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=construct,
        monotonic=lambda: 10.0,
        open3d_preflight=preflight,
    )

    assert result != 0
    output = capsys.readouterr().out
    assert "RGBD_CUP_POSE_INTERRUPTED_BEFORE_FIRST_VALID" in output
    assert "Traceback" not in output


def test_sigint_before_first_valid_pose_is_nonzero(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = False

        def spin_once(self, _timeout_s: float) -> None:
            raise KeyboardInterrupt

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            return None

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: FakeRuntime(),
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert "RGBD_CUP_POSE_INTERRUPTED_BEFORE_FIRST_VALID" in capsys.readouterr().out


def test_sigint_after_first_valid_pose_is_orderly(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = True

        def spin_once(self, _timeout_s: float) -> None:
            raise KeyboardInterrupt

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            return None

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: FakeRuntime(),
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result == 0
    assert '"status": "STOPPED"' in capsys.readouterr().out


def test_context_shutdown_runtime_error_after_first_valid_pose_is_orderly(
    capsys,
) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = True
        running = True
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            self.running = False
            raise RuntimeError("publisher's context is invalid")

        def ok(self) -> bool:
            return self.running

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result == 0
    assert runtime.closed
    output = capsys.readouterr().out
    assert '"status": "STOPPED"' in output
    assert "RGBD_CUP_POSE_FATAL" not in output


def test_live_context_runtime_error_after_first_valid_pose_remains_fatal(
    capsys,
) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = True
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            raise RuntimeError("publisher serialization failed")

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert runtime.closed
    output = capsys.readouterr().out
    assert "RGBD_CUP_POSE_FATAL" in output
    assert "publisher serialization failed" in output


def test_ros_runtime_matches_reliable_depth_one_camera_qos() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import RgbdCupPoseOptions, _create_ros_runtime

    api, _rclpy, node, _listener = _fake_ros_api()
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
    )
    try:
        assert len(node.publisher_calls) == 1
        publisher_qos = node.publisher_calls[0][2]
        assert publisher_qos.depth == 1
        assert publisher_qos.reliability == "reliable"
        subscription_qos = [call[3] for call in node.subscription_calls]
        assert len(subscription_qos) == 3
        for qos in subscription_qos:
            assert qos.depth == 1
            assert qos.reliability == "reliable"
            assert qos.durability == "volatile"
    finally:
        runtime.close()


def test_profiled_ros_runtime_records_matched_first_callbacks_and_common_stamp(
    tmp_path: Path,
) -> None:
    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler
    from so101_demo.ros.rgbd_cup_pose_node import RgbdCupPoseOptions, _create_ros_runtime

    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.TRACE,
            output_root=tmp_path / "profiling",
            session_id="session-1",
            process_role="perception",
        )
    )
    assert profiler is not None
    api, _rclpy, node, _listener = _fake_ros_api()
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
        profiler=profiler,
    )
    runtime._process_aligned = lambda _aligned: None

    for call in node.subscription_calls:
        call[5]["event_callbacks"].matched(
            SimpleNamespace(current_count=1, current_count_change=1, total_count=1)
        )

    stamp = SimpleNamespace(sec=7, nanosec=123)
    for call in node.subscription_calls:
        call[2](SimpleNamespace(header=SimpleNamespace(stamp=stamp)))

    runtime.close()
    profiler.close()
    events = [
        json.loads(line)
        for line in (
            tmp_path / "profiling/processes/perception.events.jsonl"
        ).read_text().splitlines()
    ]
    instant_events = [event for event in events if event["event_type"] == "instant"]
    assert [event["name"] for event in instant_events] == [
        "perception.subscription_matched",
        "perception.subscription_matched",
        "perception.subscription_matched",
        "perception.first_callback",
        "perception.first_callback",
        "perception.first_callback",
        "perception.common_stamp",
    ]
    assert [event["attributes"]["topic"] for event in instant_events[:3]] == [
        "/task_camera/camera_info",
        "/task_camera/color",
        "/task_camera/depth",
    ]
    assert [event["attributes"]["topic"] for event in instant_events[3:6]] == [
        "/task_camera/camera_info",
        "/task_camera/color",
        "/task_camera/depth",
    ]
    assert all(
        event["attributes"]["source_stamp_ns"] == 7_000_000_123
        for event in instant_events[3:]
    )

    complete = [
        event for event in events if event["event_type"] == "span_complete"
    ]
    milestones = {
        event["name"]: event
        for event in complete
        if event["name"].startswith("perception.wait_all_")
        or event["name"] == "perception.wait_common_stamp"
    }
    assert set(milestones) == {
        "perception.wait_all_subscriptions_matched",
        "perception.wait_all_first_callbacks",
        "perception.wait_common_stamp",
    }
    assert all(event["outcome"] == "available" for event in milestones.values())


def test_unprofiled_ros_runtime_constructs_no_subscription_event_callbacks() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import RgbdCupPoseOptions, _create_ros_runtime

    api, _rclpy, node, _listener = _fake_ros_api()

    def reject_event_callbacks(**_kwargs):
        raise AssertionError("profiling-off path constructed QoS event callbacks")

    api.SubscriptionEventCallbacks = reject_event_callbacks
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
    )
    try:
        assert [call[5] for call in node.subscription_calls] == [{}, {}, {}]
    finally:
        runtime.close()


def test_first_valid_publish_releases_exact_rgbd_inputs_once_and_cleanup_is_safe(
    monkeypatch,
) -> None:
    from so101_demo.ros import rgbd_cup_pose_node
    from so101_demo.ros.rgbd_cup_pose_node import RgbdCupPoseOptions, _create_ros_runtime

    api, _rclpy, node, _listener = _fake_ros_api()
    monkeypatch.setattr(
        rgbd_cup_pose_node,
        "pose_message_from_frame",
        lambda *_args, **_kwargs: object(),
    )
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
    )
    created = [call[4] for call in node.subscription_calls]

    runtime._publish_pose(_valid_frame(stamp_ns=20))

    assert node.destroyed_subscriptions == list(reversed(created))
    assert any(
        '"released_subscription_count": 3' in message
        and '"status": "INPUT_RELEASED_AFTER_FIRST_VALID"' in message
        for message in node.info_messages
    )

    runtime._publish_pose(_valid_frame(stamp_ns=21))
    runtime.close()

    assert node.destroyed_subscriptions == list(reversed(created))


def test_ros_runtime_disables_unused_default_services_without_dropping_sim_time() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import RgbdCupPoseOptions, _create_ros_runtime

    api, fake_rclpy, node, _listener = _fake_ros_api()
    create_node_calls = []

    def record_create_node(name, **kwargs):
        create_node_calls.append((name, kwargs))
        return node

    fake_rclpy.create_node = record_create_node
    runtime = _create_ros_runtime(
        RgbdCupPoseOptions(),
        startup_deadline=11.0,
        monotonic=lambda: 10.0,
        ros_api=api,
    )
    try:
        assert len(create_node_calls) == 1
        name, kwargs = create_node_calls[0]
        assert name == "rgbd_cup_pose"
        assert kwargs["start_parameter_services"] is False
        assert kwargs["enable_rosout"] is False
        assert kwargs["automatically_declare_parameters_from_overrides"] is True
        assert kwargs["parameter_overrides"] == [
            api.Parameter("use_sim_time", value=True)
        ]
    finally:
        runtime.close()


def test_partial_ros_runtime_construction_cleans_every_created_resource() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import RgbdCupPoseOptions, _create_ros_runtime

    api, fake_rclpy, node, listener = _fake_ros_api(fail_subscription_number=2)

    with pytest.raises(RuntimeError, match="subscription construction failed"):
        _create_ros_runtime(
            RgbdCupPoseOptions(),
            startup_deadline=11.0,
            monotonic=lambda: 10.0,
            ros_api=api,
        )

    assert node.destroyed_subscriptions == [node.subscription_calls[0][4]]
    assert node.destroyed_publishers == [node.publisher_calls[0][3]]
    assert listener.unregister_calls == 1
    assert node.destroyed
    assert fake_rclpy.shutdown_calls == 0
    assert fake_rclpy.try_shutdown_calls == 1


def test_node_construction_failure_after_init_shuts_down_owned_context() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import RgbdCupPoseOptions, _create_ros_runtime

    api, fake_rclpy, _node, _listener = _fake_ros_api()

    def fail_node(*_args, **_kwargs):
        raise RuntimeError("node construction failed")

    fake_rclpy.create_node = fail_node

    with pytest.raises(RuntimeError, match="node construction failed"):
        _create_ros_runtime(
            RgbdCupPoseOptions(),
            startup_deadline=11.0,
            monotonic=lambda: 10.0,
            ros_api=api,
        )

    assert fake_rclpy.shutdown_calls == 0
    assert fake_rclpy.try_shutdown_calls == 1


def test_cleanup_attempts_every_resource_in_reverse_order_and_aggregates_failures() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import CleanupError, RosResourceCleanup

    calls = []

    def fail(name):
        def operation(_resource=None):
            calls.append(name)
            raise RuntimeError(f"{name} failed")

        return operation

    node = SimpleNamespace(
        destroy_subscription=lambda subscription: fail(f"subscription-{subscription}")(),
        destroy_publisher=fail("publisher"),
        destroy_node=fail("node"),
    )
    listener = SimpleNamespace(unregister=fail("listener"))
    rclpy = SimpleNamespace(ok=lambda: True, try_shutdown=fail("context"))
    cleanup = RosResourceCleanup(
        ros_api=SimpleNamespace(rclpy=rclpy),
        node=node,
        tf_listener=listener,
        publisher="pose-publisher",
        subscriptions=["first", "second"],
        initialized_here=True,
    )

    with pytest.raises(CleanupError) as captured:
        cleanup.close()

    assert calls == [
        "subscription-second",
        "subscription-first",
        "publisher",
        "listener",
        "node",
        "context",
    ]
    assert len(captured.value.failures) == 6


def test_cleanup_is_idempotent_and_preserves_external_context() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import RosResourceCleanup

    calls = []
    node = SimpleNamespace(
        destroy_subscription=lambda subscription: calls.append(f"subscription-{subscription}"),
        destroy_publisher=lambda _publisher: calls.append("publisher"),
        destroy_node=lambda: calls.append("node"),
    )
    listener = SimpleNamespace(unregister=lambda: calls.append("listener"))
    rclpy = SimpleNamespace(
        ok=lambda: True,
        shutdown=lambda: calls.append("context"),
    )
    cleanup = RosResourceCleanup(
        ros_api=SimpleNamespace(rclpy=rclpy),
        node=node,
        tf_listener=listener,
        publisher="pose-publisher",
        subscriptions=["only"],
        initialized_here=False,
    )

    cleanup.close()
    cleanup.close()

    assert calls == ["subscription-only", "publisher", "listener", "node"]


def test_failed_cleanup_is_idempotent_and_rethrows_without_repeating_actions() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import CleanupError, RosResourceCleanup

    calls = []

    def fail_node() -> None:
        calls.append("node")
        raise RuntimeError("node cleanup failed")

    cleanup = RosResourceCleanup(
        ros_api=SimpleNamespace(rclpy=SimpleNamespace(shutdown=lambda: None)),
        node=SimpleNamespace(destroy_node=fail_node),
        initialized_here=False,
    )

    with pytest.raises(CleanupError) as first:
        cleanup.close()
    with pytest.raises(CleanupError) as second:
        cleanup.close()

    assert first.value is second.value
    assert calls == ["node"]


def test_partial_construction_cleanup_failure_is_actionable_and_continues(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        _create_ros_runtime,
        run_rgbd_cup_pose,
    )

    api, fake_rclpy, node, listener = _fake_ros_api(fail_subscription_number=2)

    def fail_subscription_cleanup(subscription) -> None:
        node.destroyed_subscriptions.append(subscription)
        raise RuntimeError("subscription cleanup failed")

    node.destroy_subscription = fail_subscription_cleanup
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda options, deadline, clock: _create_ros_runtime(
            options,
            deadline,
            clock,
            ros_api=api,
        ),
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert "RGBD_CUP_POSE_CLEANUP_FAILED" in capsys.readouterr().out
    assert node.destroyed_publishers == [node.publisher_calls[0][3]]
    assert listener.unregister_calls == 1
    assert node.destroyed
    assert fake_rclpy.shutdown_calls == 0
    assert fake_rclpy.try_shutdown_calls == 1


def test_post_success_cleanup_failure_forces_actionable_nonzero(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = True

        def spin_once(self, _timeout_s: float) -> None:
            pytest.fail("stopped runtime reached spin")

        def ok(self) -> bool:
            return False

        def close(self) -> None:
            raise RuntimeError("publisher cleanup failed")

    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: FakeRuntime(),
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    output = capsys.readouterr().out
    assert "RGBD_CUP_POSE_CLEANUP_FAILED" in output
    assert "publisher cleanup failed" in output


def test_post_success_close_accepts_owned_context_already_shut_down(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        RosResourceCleanup,
        run_rgbd_cup_pose,
    )

    api, fake_rclpy, node, listener = _fake_ros_api()
    subscription = object()
    publisher = object()
    cleanup = RosResourceCleanup(
        ros_api=api,
        initialized_here=True,
        node=node,
        tf_listener=listener,
        publisher=publisher,
        subscriptions=[subscription],
    )
    fake_rclpy.initialized = False

    runtime = SimpleNamespace(
        first_valid_published=True,
        ok=lambda: False,
        close=cleanup.close,
    )
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result == 0
    assert "RGBD_CUP_POSE_CLEANUP_FAILED" not in capsys.readouterr().out
    assert node.destroyed_subscriptions == [subscription]
    assert node.destroyed_publishers == [publisher]
    assert listener.unregister_calls == 1
    assert node.destroyed
    assert fake_rclpy.shutdown_calls == 0
    assert fake_rclpy.try_shutdown_calls == 1


def test_run_continues_after_first_valid_frame_until_orderly_shutdown() -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        def __init__(self) -> None:
            self.spins = 0
            self.closed = False

        @property
        def first_valid_published(self) -> bool:
            return self.spins >= 1

        def spin_once(self, _timeout_s: float) -> None:
            self.spins += 1

        def ok(self) -> bool:
            return self.spins < 3

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result == 0
    assert runtime.spins == 3
    assert runtime.closed


def test_runtime_evidence_io_failure_returns_explicit_nonzero(capsys) -> None:
    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    class FakeRuntime:
        first_valid_published = False
        closed = False

        def spin_once(self, _timeout_s: float) -> None:
            raise OSError("evidence disk is full")

        def ok(self) -> bool:
            return True

        def close(self) -> None:
            self.closed = True

    runtime = FakeRuntime()
    result = run_rgbd_cup_pose(
        RgbdCupPoseOptions(startup_timeout_s=1.0),
        runtime_factory=lambda _options, _deadline, _monotonic: runtime,
        monotonic=lambda: 10.0,
        open3d_preflight=lambda _remaining_s: None,
    )

    assert result != 0
    assert runtime.closed
    output = capsys.readouterr().out
    assert "RGBD_CUP_POSE_FATAL" in output
    assert "evidence disk is full" in output


@pytest.mark.parametrize(
    ("arguments", "message"),
    [
        (["--startup-timeout-s", "nan"], "finite and positive"),
        (["--output-topic", "cup_pose"], "absolute ROS topic"),
        (["--output-ply", ""], "non-empty path"),
        (["--evidence-json", "relative.json"], "absolute output file path"),
    ],
)
def test_cli_rejects_invalid_options(arguments, message, capsys) -> None:
    from so101_demo.cli.rgbd_cup_pose import main

    with pytest.raises(SystemExit) as error:
        main(arguments)
    assert error.value.code == 2
    assert message in capsys.readouterr().err


def test_cli_removes_launch_injected_ros_parameter_arguments(monkeypatch, tmp_path) -> None:
    from so101_demo.cli import rgbd_cup_pose
    from so101_demo.ros import rgbd_cup_pose_node

    params = tmp_path / "params.yaml"
    params.write_text(
        "/**:\n  ros__parameters:\n    use_sim_time: true\n",
        encoding="utf-8",
    )
    calls = []
    monkeypatch.setattr(
        rgbd_cup_pose_node,
        "run_rgbd_cup_pose",
        lambda options: calls.append(options) or 23,
    )

    assert (
        rgbd_cup_pose.main(
            [
                "--startup-timeout-s",
                "30",
                "--output-topic",
                "/cup_pose",
                "--ros-args",
                "--params-file",
                str(params),
            ]
        )
        == 23
    )
    assert len(calls) == 1
    assert calls[0].startup_timeout_s == 30.0
    assert calls[0].output_topic == "/cup_pose"


def test_cli_still_rejects_unknown_application_argument(capsys) -> None:
    from so101_demo.cli.rgbd_cup_pose import main

    with pytest.raises(SystemExit) as error:
        main(["--unknown-application-option"])
    assert error.value.code == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_cli_enabled_profiling_passes_and_closes_perception_profiler(
    monkeypatch,
    tmp_path: Path,
) -> None:
    from so101_demo.cli import rgbd_cup_pose
    from so101_demo.ros import rgbd_cup_pose_node

    calls = []

    def run(options, *, profiler) -> int:
        calls.append((options, profiler))
        return 0

    monkeypatch.setattr(rgbd_cup_pose_node, "run_rgbd_cup_pose", run)
    profiling_root = tmp_path / "profiling"

    assert rgbd_cup_pose.main(
        [
            "--profiling",
            "trace",
            "--profiling-output-root",
            str(profiling_root),
            "--profiling-session-id",
            "session-1",
        ]
    ) == 0

    assert len(calls) == 1
    assert calls[0][1].config.process_role == "perception"
    events = [
        json.loads(line)
        for line in (
            profiling_root / "processes/perception.events.jsonl"
        ).read_text().splitlines()
    ]
    assert events[-1]["event_type"] == "process_close"


def test_cli_profiling_sink_initialization_error_runs_perception_unprofiled(
    monkeypatch,
) -> None:
    from so101_demo.cli import rgbd_cup_pose
    from so101_demo.profiling import session as profiling_session
    from so101_demo.ros import rgbd_cup_pose_node

    calls = []

    def run(options, **kwargs) -> int:
        calls.append((options, kwargs))
        return 23

    monkeypatch.setattr(rgbd_cup_pose_node, "run_rgbd_cup_pose", run)
    monkeypatch.setattr(
        profiling_session,
        "build_profiler",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )

    assert rgbd_cup_pose.main(
        [
            "--profiling",
            "summary",
            "--profiling-output-root",
            "/tmp/profiling",
            "--profiling-session-id",
            "session-1",
        ]
    ) == 23

    assert len(calls) == 1
    assert calls[0][1] == {}


def test_cli_invalid_profiling_configuration_still_exits_before_perception(
    monkeypatch,
) -> None:
    from so101_demo.cli import rgbd_cup_pose
    from so101_demo.ros import rgbd_cup_pose_node

    calls = []
    monkeypatch.setattr(
        rgbd_cup_pose_node,
        "run_rgbd_cup_pose",
        lambda options, **kwargs: calls.append((options, kwargs)) or 0,
    )

    with pytest.raises(SystemExit) as error:
        rgbd_cup_pose.main(["--profiling", "summary"])

    assert error.value.code == 2
    assert calls == []


def test_package_registers_rgbd_cup_pose_executable() -> None:
    package_root = Path(__file__).resolve().parents[1]
    setup_source = (package_root / "setup.py").read_text(encoding="utf-8")

    assert "rgbd_cup_pose = so101_demo.cli.rgbd_cup_pose:main" in setup_source
