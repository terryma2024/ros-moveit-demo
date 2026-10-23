"""ROS API loading, cleanup of the node resources and the runtime construction."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

from so101_demo.cli.rgbd_point_cloud import (
    AlignedRgbdBuffer,
    message_stamp_ns,
    write_cup_point_cloud,
)
from so101_demo.profiling.session import SemanticProfiler
from so101_demo.ros.rgbd_cup_pose.frames import (
    WORLD_FRAME,
    CupPoseFrame,
    CupPoseFrameProcessor,
    FirstValidEvidencePublisher,
    FreshFrameGate,
    RgbdCupPoseOptions,
    RgbdSubscriptionMilestones,
    _Runtime,
    _status_line,
    _write_evidence_json,
    bounded_tf_timeout_s,
    estimate_cup_pose_frame,
    pose_message_from_frame,
)
from so101_demo.ros.rgbd_snapshot import write_full_point_cloud, write_rgb_png
from so101_demo.runtime.point_cloud_preview import render_point_cloud_preview
from so101_demo.runtime.workflow_events import EventEmitter


def _load_ros_api() -> Any:
    from geometry_msgs.msg import PoseStamped
    import rclpy
    from rclpy.clock import ClockType
    from rclpy.duration import Duration
    from rclpy.executors import ExternalShutdownException
    from rclpy.parameter import Parameter
    from rclpy.qos import (
        DurabilityPolicy,
        QoSProfile,
        ReliabilityPolicy,
    )
    from rclpy.time import Time
    from sensor_msgs.msg import CameraInfo, Image
    from tf2_ros import Buffer, TransformException, TransformListener

    return SimpleNamespace(
        rclpy=rclpy,
        PoseStamped=PoseStamped,
        ClockType=ClockType,
        Duration=Duration,
        ExternalShutdownException=ExternalShutdownException,
        Parameter=Parameter,
        DurabilityPolicy=DurabilityPolicy,
        QoSProfile=QoSProfile,
        ReliabilityPolicy=ReliabilityPolicy,
        Time=Time,
        CameraInfo=CameraInfo,
        Image=Image,
        Buffer=Buffer,
        TransformException=TransformException,
        TransformListener=TransformListener,
    )


def _load_subscription_event_callbacks() -> Any:
    """Import QoS event support only when profiling is enabled."""
    from rclpy.event_handler import SubscriptionEventCallbacks

    return SubscriptionEventCallbacks


@dataclass(frozen=True, slots=True)
class CleanupFailure:
    resource: str
    error: BaseException


class CleanupError(RuntimeError):
    def __init__(self, failures: list[CleanupFailure]) -> None:
        self.failures = tuple(failures)
        details = "; ".join(
            f"{failure.resource}: {failure.error}" for failure in self.failures
        )
        super().__init__(f"ROS resource cleanup failed: {details}")


class ResourceConstructionError(RuntimeError):
    def __init__(self, primary: BaseException, cleanup_error: CleanupError) -> None:
        self.primary = primary
        self.cleanup_error = cleanup_error
        super().__init__(f"construction failed ({primary}); {cleanup_error}")


class RosResourceCleanup:
    """Idempotently unwind every owned ROS resource in reverse creation order."""

    def __init__(
        self,
        *,
        ros_api: Any,
        initialized_here: bool,
        node: Any | None = None,
        tf_listener: Any | None = None,
        publisher: Any | None = None,
        subscriptions: list[Any] | None = None,
    ) -> None:
        self.ros_api = ros_api
        self.initialized_here = initialized_here
        self.node = node
        self.tf_listener = tf_listener
        self.publisher = publisher
        self.subscriptions = subscriptions if subscriptions is not None else []
        self._completed = False
        self._error: CleanupError | None = None

    def close(self) -> None:
        if self._completed:
            if self._error is not None:
                raise self._error
            return
        self._completed = True
        failures: list[CleanupFailure] = []

        def attempt(resource: str, operation: Callable[[], None]) -> None:
            try:
                operation()
            except BaseException as error:
                failures.append(CleanupFailure(resource, error))

        if self.node is not None:
            for index, subscription in reversed(list(enumerate(self.subscriptions))):
                attempt(
                    f"subscription[{index}]",
                    lambda subscription=subscription: self.node.destroy_subscription(
                        subscription
                    ),
                )
            if self.publisher is not None:
                attempt(
                    "publisher",
                    lambda: self.node.destroy_publisher(self.publisher),
                )
        if self.tf_listener is not None:
            unregister = getattr(self.tf_listener, "unregister", None)
            if unregister is not None:
                attempt("tf_listener", unregister)
        if self.node is not None:
            attempt("node", self.node.destroy_node)
        if self.initialized_here:
            attempt("rclpy_context", self.ros_api.rclpy.try_shutdown)

        if failures:
            self._error = CleanupError(failures)
            raise self._error


def _create_ros_runtime(
    options: RgbdCupPoseOptions,
    startup_deadline: float,
    monotonic: Callable[[], float],
    *,
    ros_api: Any | None = None,
    profiler: SemanticProfiler | None = None,
    event_emitter: EventEmitter | None = None,
) -> _Runtime:
    if startup_deadline - monotonic() <= 0.0:
        raise TimeoutError("startup deadline expired before ROS runtime construction")
    ros = ros_api or _load_ros_api()

    initialized_here = not ros.rclpy.ok()
    node = None
    tf_listener = None
    publisher = None
    subscriptions: list[Any] = []
    frame_processor: CupPoseFrameProcessor | None = None
    subscription_milestones: RgbdSubscriptionMilestones | None = None
    cleanup = RosResourceCleanup(
        ros_api=ros,
        initialized_here=initialized_here,
        subscriptions=subscriptions,
    )
    try:
        if initialized_here:
            ros.rclpy.init()
        node = ros.rclpy.create_node(
            "rgbd_cup_pose",
            parameter_overrides=[ros.Parameter("use_sim_time", value=True)],
            automatically_declare_parameters_from_overrides=True,
            start_parameter_services=False,
            enable_rosout=False,
        )
        cleanup.node = node
        tf_buffer = ros.Buffer()
        tf_listener = ros.TransformListener(tf_buffer, node)
        cleanup.tf_listener = tf_listener
        pose_qos = ros.QoSProfile(
            depth=1,
            reliability=ros.ReliabilityPolicy.RELIABLE,
            durability=ros.DurabilityPolicy.VOLATILE,
        )
        camera_qos = ros.QoSProfile(
            depth=1,
            reliability=ros.ReliabilityPolicy.RELIABLE,
            durability=ros.DurabilityPolicy.VOLATILE,
        )
        publisher = node.create_publisher(
            ros.PoseStamped, options.output_topic, pose_qos
        )
        cleanup.publisher = publisher
        if profiler is not None:
            subscription_milestones = RgbdSubscriptionMilestones(
                profiler,
                (
                    options.camera_info_topic,
                    options.color_topic,
                    options.depth_topic,
                ),
            )

        class RosRuntime:
            def __init__(self) -> None:
                nonlocal frame_processor
                self._buffer = AlignedRgbdBuffer()
                self._fresh_frames = FreshFrameGate()
                self._subscriptions = subscriptions
                self._inputs_released = False
                self._ready_emitted = False
                self._evidence_publisher = FirstValidEvidencePublisher(
                    write_ply=lambda frame: write_cup_point_cloud(
                        frame.cloud, options.output_ply
                    ),
                    write_json=lambda frame: _write_evidence_json(frame, options),
                    publish=self._publish_pose,
                    write_rgb=(
                        None
                        if options.output_rgb is None
                        else lambda frame: write_rgb_png(frame.cloud, options.output_rgb)
                    ),
                    write_full_ply=(
                        None
                        if options.output_full_ply is None
                        else lambda frame: write_full_point_cloud(
                            frame.cloud.full_points_xyz,
                            frame.cloud.full_colors_rgb,
                            options.output_full_ply,
                        )
                    ),
                    write_preview=(
                        None
                        if options.output_preview is None
                        else lambda frame: render_point_cloud_preview(
                            frame.cloud.full_points_xyz,
                            frame.cloud.full_colors_rgb,
                            options.output_preview,
                        )
                    ),
                    event_emitter=event_emitter,
                )
                self._processor = CupPoseFrameProcessor(
                    estimate=self._estimate_frame,
                    publish=self._evidence_publisher,
                    on_error=lambda error: node.get_logger().error(
                        _status_line(
                            "ERROR",
                            failure="RGBD_CUP_POSE_FRAME_INVALID",
                            message=str(error),
                        )
                    ),
                    profiler=profiler,
                )
                frame_processor = self._processor

                if subscription_milestones is None:
                    self._subscriptions.append(
                        node.create_subscription(
                            ros.CameraInfo,
                            options.camera_info_topic,
                            self._on_camera_info,
                            camera_qos,
                        )
                    )
                    self._subscriptions.append(
                        node.create_subscription(
                            ros.Image,
                            options.color_topic,
                            self._on_color,
                            camera_qos,
                        )
                    )
                    self._subscriptions.append(
                        node.create_subscription(
                            ros.Image,
                            options.depth_topic,
                            self._on_depth,
                            camera_qos,
                        )
                    )
                else:
                    event_callbacks = getattr(
                        ros, "SubscriptionEventCallbacks", None
                    ) or _load_subscription_event_callbacks()
                    self._subscriptions.append(
                        node.create_subscription(
                            ros.CameraInfo,
                            options.camera_info_topic,
                            self._profiled_on_camera_info,
                            camera_qos,
                            event_callbacks=event_callbacks(
                                matched=lambda status: subscription_milestones.subscription_matched(
                                    options.camera_info_topic, status
                                )
                            ),
                        )
                    )
                    self._subscriptions.append(
                        node.create_subscription(
                            ros.Image,
                            options.color_topic,
                            self._profiled_on_color,
                            camera_qos,
                            event_callbacks=event_callbacks(
                                matched=lambda status: subscription_milestones.subscription_matched(
                                    options.color_topic, status
                                )
                            ),
                        )
                    )
                    self._subscriptions.append(
                        node.create_subscription(
                            ros.Image,
                            options.depth_topic,
                            self._profiled_on_depth,
                            camera_qos,
                            event_callbacks=event_callbacks(
                                matched=lambda status: subscription_milestones.subscription_matched(
                                    options.depth_topic, status
                                )
                            ),
                        )
                    )

            @property
            def first_valid_published(self) -> bool:
                return self._evidence_publisher.published_count > 0

            def _tf_timeout_budget(self) -> float:
                return bounded_tf_timeout_s(
                    options.tf_timeout_s,
                    first_valid_published=self.first_valid_published,
                    startup_deadline=startup_deadline,
                    monotonic=monotonic,
                )

            def _lookup_transform(
                self, target_frame: str, source_frame: str, query_time: Any, timeout_s: float
            ) -> Any:
                try:
                    return tf_buffer.lookup_transform(
                        target_frame,
                        source_frame,
                        query_time,
                        timeout=ros.Duration(seconds=timeout_s),
                    )
                except ros.TransformException as error:
                    raise RuntimeError(
                        f"exact-stamp transform {target_frame} <- {source_frame} "
                        f"is unavailable: {error}"
                    ) from error

            def _estimate_frame(self, aligned: Any) -> CupPoseFrame:
                return estimate_cup_pose_frame(
                    aligned,
                    options,
                    lookup_transform=self._lookup_transform,
                    stamp_to_time=ros.Time.from_msg,
                    tf_timeout_budget=self._tf_timeout_budget,
                    profiler=profiler,
                )

            def _publish_pose(self, frame: CupPoseFrame) -> None:
                pose = pose_message_from_frame(
                    frame,
                    pose_factory=ros.PoseStamped,
                    stamp_from_ns=lambda stamp_ns: ros.Time(
                        nanoseconds=stamp_ns, clock_type=ros.ClockType.ROS_TIME
                    ).to_msg(),
                )
                publisher.publish(pose)
                node.get_logger().info(
                    _status_line(
                        "OK",
                        stamp_ns=frame.stamp_ns,
                        output_frame_id=WORLD_FRAME,
                        output_topic=options.output_topic,
                        position_xyz=list(frame.center_world_xyz),
                        fitted_radius_m=frame.fitted_radius_m,
                    )
                )
                self._release_rgbd_inputs()

            def _release_rgbd_inputs(self) -> None:
                if self._inputs_released:
                    return
                expected_count = 3
                if len(self._subscriptions) != expected_count:
                    raise RuntimeError(
                        "RGB-D input ownership changed before first valid pose: "
                        f"expected {expected_count} subscriptions, found "
                        f"{len(self._subscriptions)}"
                    )
                released_count = 0
                while self._subscriptions:
                    subscription = self._subscriptions[-1]
                    destroyed = node.destroy_subscription(subscription)
                    if destroyed is False:
                        raise RuntimeError(
                            "failed to release an RGB-D input subscription after "
                            "the first valid pose"
                        )
                    self._subscriptions.pop()
                    released_count += 1
                self._inputs_released = True
                node.get_logger().info(
                    _status_line(
                        "INPUT_RELEASED_AFTER_FIRST_VALID",
                        released_subscription_count=released_count,
                    )
                )

            def _process_aligned(self, aligned: Any) -> None:
                stamp_ns = message_stamp_ns(aligned[0])
                if not self._fresh_frames.accept(stamp_ns):
                    node.get_logger().error(
                        _status_line(
                            "ERROR",
                            failure="RGBD_CUP_POSE_STALE_FRAME",
                            message=(
                                f"source stamp {stamp_ns} is not newer than the prior frame"
                            ),
                        )
                    )
                    return
                if not self._ready_emitted and event_emitter is not None:
                    event_emitter.emit("PERCEPTION_READY", payload={})
                    self._ready_emitted = True
                self._processor.process(aligned)

            def _on_camera_info(self, message: Any) -> None:
                aligned = self._buffer.add_camera_info(message)
                if aligned is not None:
                    self._process_aligned(aligned)

            def _on_color(self, message: Any) -> None:
                aligned = self._buffer.add_color(message)
                if aligned is not None:
                    self._process_aligned(aligned)

            def _on_depth(self, message: Any) -> None:
                aligned = self._buffer.add_depth(message)
                if aligned is not None:
                    self._process_aligned(aligned)

            def _profiled_on_camera_info(self, message: Any) -> None:
                assert subscription_milestones is not None
                subscription_milestones.first_callback(
                    options.camera_info_topic, message
                )
                aligned = self._buffer.add_camera_info(message)
                if aligned is not None:
                    subscription_milestones.common_stamp(message_stamp_ns(aligned[0]))
                    self._process_aligned(aligned)

            def _profiled_on_color(self, message: Any) -> None:
                assert subscription_milestones is not None
                subscription_milestones.first_callback(options.color_topic, message)
                aligned = self._buffer.add_color(message)
                if aligned is not None:
                    subscription_milestones.common_stamp(message_stamp_ns(aligned[0]))
                    self._process_aligned(aligned)

            def _profiled_on_depth(self, message: Any) -> None:
                assert subscription_milestones is not None
                subscription_milestones.first_callback(options.depth_topic, message)
                aligned = self._buffer.add_depth(message)
                if aligned is not None:
                    subscription_milestones.common_stamp(message_stamp_ns(aligned[0]))
                    self._process_aligned(aligned)

            def spin_once(self, timeout_s: float) -> None:
                try:
                    ros.rclpy.spin_once(node, timeout_sec=timeout_s)
                except ros.ExternalShutdownException:
                    return
                except ros.TransformException as error:
                    node.get_logger().error(
                        _status_line(
                            "ERROR",
                            failure="RGBD_CUP_POSE_TF_UNAVAILABLE",
                            message=str(error),
                        )
                    )

            def ok(self) -> bool:
                return ros.rclpy.ok()

            def finish_wait_span(self, outcome: str) -> None:
                self._processor.finish_wait(outcome)
                if subscription_milestones is not None:
                    subscription_milestones.finish_pending(outcome)

            def close(self) -> None:
                self.finish_wait_span("interrupted")
                cleanup.close()

        return RosRuntime()
    except BaseException as primary:
        if frame_processor is not None:
            frame_processor.finish_wait("error")
        if subscription_milestones is not None:
            subscription_milestones.finish_pending("error")
        try:
            cleanup.close()
        except CleanupError as cleanup_error:
            raise ResourceConstructionError(primary, cleanup_error) from primary
        raise
