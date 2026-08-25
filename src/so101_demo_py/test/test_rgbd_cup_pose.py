from __future__ import annotations

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

    def ok(self) -> bool:
        return self.initialized

    def init(self) -> None:
        self.initialized = True

    def shutdown(self) -> None:
        self.shutdown_calls += 1
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

    def create_publisher(self, message_type, topic, qos):
        publisher = SimpleNamespace(publish=lambda _message: None)
        self.publisher_calls.append((message_type, topic, qos, publisher))
        return publisher

    def create_subscription(self, message_type, topic, callback, qos):
        number = len(self.subscription_calls) + 1
        if number == self.fail_subscription_number:
            raise RuntimeError("subscription construction failed")
        subscription = object()
        self.subscription_calls.append((message_type, topic, callback, qos, subscription))
        return subscription

    def destroy_publisher(self, publisher) -> None:
        self.destroyed_publishers.append(publisher)

    def destroy_subscription(self, subscription) -> None:
        self.destroyed_subscriptions.append(subscription)

    def destroy_node(self) -> None:
        self.destroyed = True

    def get_logger(self):
        return SimpleNamespace(error=lambda _message: None, info=lambda _message: None)


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
    evidence_publisher = FirstValidEvidencePublisher(
        write_ply=lambda frame: ply_stamps.append(frame.stamp_ns),
        write_json=lambda frame: json_stamps.append(frame.stamp_ns),
        publish=published.append,
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


def test_ros_runtime_uses_sensor_qos_and_reliable_depth_one_publisher() -> None:
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
        assert [call[3] for call in node.subscription_calls] == [
            api.qos_profile_sensor_data,
            api.qos_profile_sensor_data,
            api.qos_profile_sensor_data,
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
    assert fake_rclpy.shutdown_calls == 1


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

    assert fake_rclpy.shutdown_calls == 1


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


def test_package_registers_rgbd_cup_pose_executable() -> None:
    package_root = Path(__file__).resolve().parents[1]
    setup_source = (package_root / "setup.py").read_text(encoding="utf-8")

    assert "rgbd_cup_pose = so101_demo.cli.rgbd_cup_pose:main" in setup_source
