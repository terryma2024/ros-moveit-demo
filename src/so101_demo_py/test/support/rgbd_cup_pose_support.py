"""Fakes and helpers shared by the RGB-D cup pose tests."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np


def _camera_partial_cylinder() -> np.ndarray:
    angles = np.linspace(-1.1, 1.2, 80)
    center_xy = np.array([0.02, -0.28])
    radius = 0.04
    xy = center_xy + radius * np.column_stack((np.cos(angles), np.sin(angles)))
    return np.column_stack((xy, np.linspace(0.175, 0.210, len(xy))))


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
    from so101_demo.ros.rgbd_cup_pose.frames import CupPoseFrame

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
