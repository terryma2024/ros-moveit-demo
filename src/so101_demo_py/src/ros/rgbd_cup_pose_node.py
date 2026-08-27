"""Continuous ROS adapter for RGB-D cup-pose estimation and publication."""

from __future__ import annotations

import importlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Protocol

from so101_demo.cli.rgbd_cup_pose import estimate_world_cup_pose
from so101_demo.cli.rgbd_point_cloud import (
    AlignedRgbdBuffer,
    CupPointCloudResult,
    build_cup_point_cloud,
    message_stamp_ns,
    write_cup_point_cloud,
)
from so101_demo.ros.rgbd_snapshot import write_full_point_cloud, write_rgb_png
from so101_demo.runtime.point_cloud_preview import render_point_cloud_preview

WORLD_FRAME = "world"


def _validate_topic(name: str, value: str) -> None:
    if not value or not value.startswith("/") or value == "/" or "//" in value:
        raise ValueError(f"{name} must be a non-empty absolute ROS topic")
    if any(character.isspace() for character in value):
        raise ValueError(f"{name} must be a non-empty absolute ROS topic")


def _validate_output_path(name: str, value: Path) -> None:
    if str(value).strip() in {"", "."}:
        raise ValueError(f"{name} must be a non-empty output file path")
    if not value.is_absolute():
        raise ValueError(f"{name} must be an absolute output file path")
    if value.exists() and value.is_dir():
        raise ValueError(f"{name} must be an output file path, not a directory")


@dataclass(frozen=True, slots=True)
class RgbdCupPoseOptions:
    startup_timeout_s: float = 15.0
    tf_timeout_s: float = 0.2
    camera_info_topic: str = "/task_camera/camera_info"
    color_topic: str = "/task_camera/color"
    depth_topic: str = "/task_camera/depth"
    output_topic: str = "/cup_pose"
    table_top_z: float = 0.12
    cup_height: float = 0.09
    expected_radius: float = 0.04
    radius_tolerance: float = 0.01
    depth_trunc_m: float = 3.0
    cluster_eps_m: float = 0.02
    cluster_min_points: int = 5
    minimum_cup_points: int = 50
    output_ply: Path = Path("/tmp/v4-t006-cup-cloud.ply")
    evidence_json: Path = Path("/tmp/v4-t006-cup-pose.json")
    output_rgb: Path | None = None
    output_full_ply: Path | None = None
    output_preview: Path | None = None

    def __post_init__(self) -> None:
        numeric_values = {
            "startup_timeout_s": self.startup_timeout_s,
            "tf_timeout_s": self.tf_timeout_s,
            "table_top_z": self.table_top_z,
            "cup_height": self.cup_height,
            "expected_radius": self.expected_radius,
            "radius_tolerance": self.radius_tolerance,
            "depth_trunc_m": self.depth_trunc_m,
            "cluster_eps_m": self.cluster_eps_m,
        }
        for name, value in numeric_values.items():
            if not math.isfinite(value) or value <= 0.0:
                raise ValueError(f"{name} must be finite and positive")
        for name, value in {
            "cluster_min_points": self.cluster_min_points,
            "minimum_cup_points": self.minimum_cup_points,
        }.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        for name, value in {
            "camera_info_topic": self.camera_info_topic,
            "color_topic": self.color_topic,
            "depth_topic": self.depth_topic,
            "output_topic": self.output_topic,
        }.items():
            _validate_topic(name, value)
        _validate_output_path("output_ply", self.output_ply)
        _validate_output_path("evidence_json", self.evidence_json)
        optional_paths = {
            "output_rgb": self.output_rgb,
            "output_full_ply": self.output_full_ply,
            "output_preview": self.output_preview,
        }
        for name, path in optional_paths.items():
            if path is not None:
                _validate_output_path(name, path)
        paths = [
            self.output_ply,
            self.evidence_json,
            *(path for path in optional_paths.values() if path is not None),
        ]
        if len(set(paths)) != len(paths):
            raise ValueError("RGB-D evidence output paths must be different")


@dataclass(frozen=True, slots=True)
class CupPoseFrame:
    stamp_ns: int
    source_frame_id: str
    center_world_xyz: tuple[float, float, float]
    fitted_radius_m: float
    cloud: CupPointCloudResult

    def __post_init__(self) -> None:
        if self.stamp_ns <= 0:
            raise ValueError("RGB-D source stamp must be nonzero")
        if not self.source_frame_id:
            raise ValueError("RGB-D source frame_id must be non-empty")
        if len(self.center_world_xyz) != 3 or not all(
            math.isfinite(value) for value in self.center_world_xyz
        ):
            raise ValueError("cup pose center must contain three finite values")
        if not math.isfinite(self.fitted_radius_m) or self.fitted_radius_m <= 0.0:
            raise ValueError("fitted radius must be finite and positive")
        if self.cloud.stamp_ns != self.stamp_ns:
            raise ValueError("cup pose and point cloud stamps differ")
        if self.cloud.frame_id != self.source_frame_id:
            raise ValueError("cup pose and point cloud source frames differ")


class CupPoseFrameProcessor:
    def __init__(
        self,
        *,
        estimate: Callable[[Any], CupPoseFrame],
        publish: Callable[[CupPoseFrame], None],
        on_error: Callable[[Exception], None],
    ) -> None:
        self._estimate = estimate
        self._publish = publish
        self._on_error = on_error

    def process(self, aligned: Any) -> bool:
        """Publish once for this valid frame, or report and skip an invalid frame."""
        try:
            frame = self._estimate(aligned)
        except (RuntimeError, TimeoutError, ValueError) as error:
            self._on_error(error)
            return False
        self._publish(frame)
        return True


class FreshFrameGate:
    """Accept only strictly newer source stamps, whether prior frames passed or failed."""

    def __init__(self) -> None:
        self._last_stamp_ns = -1

    def accept(self, stamp_ns: int) -> bool:
        if stamp_ns <= self._last_stamp_ns:
            return False
        self._last_stamp_ns = stamp_ns
        return True


class FirstValidEvidencePublisher:
    """Write evidence before the first publication, then publish every fresh frame."""

    def __init__(
        self,
        *,
        write_ply: Callable[[CupPoseFrame], None],
        write_json: Callable[[CupPoseFrame], None],
        publish: Callable[[CupPoseFrame], None],
        write_rgb: Callable[[CupPoseFrame], None] | None = None,
        write_full_ply: Callable[[CupPoseFrame], None] | None = None,
        write_preview: Callable[[CupPoseFrame], None] | None = None,
    ) -> None:
        self._write_ply = write_ply
        self._write_json = write_json
        self._publish = publish
        self._write_rgb = write_rgb
        self._write_full_ply = write_full_ply
        self._write_preview = write_preview
        self._evidence_written = False
        self.published_count = 0

    def __call__(self, frame: CupPoseFrame) -> None:
        if not self._evidence_written:
            if self._write_rgb is not None:
                self._write_rgb(frame)
            if self._write_full_ply is not None:
                self._write_full_ply(frame)
            if self._write_preview is not None:
                self._write_preview(frame)
            self._write_ply(frame)
            self._write_json(frame)
            self._evidence_written = True
        self._publish(frame)
        self.published_count += 1


class _Runtime(Protocol):
    @property
    def first_valid_published(self) -> bool: ...

    def spin_once(self, timeout_s: float) -> None: ...

    def ok(self) -> bool: ...

    def close(self) -> None: ...


def _status_line(status: str, **fields: Any) -> str:
    return json.dumps({"status": status, **fields}, sort_keys=True)


def _require_open3d(
    remaining_startup_s: float,
    *,
    find_spec: Callable[[str], Any] | None = None,
    importer: Callable[[str], Any] | None = None,
) -> None:
    if not math.isfinite(remaining_startup_s) or remaining_startup_s <= 0.0:
        raise TimeoutError("startup deadline expired before Open3D preflight")
    find_spec = find_spec or importlib.util.find_spec
    importer = importer or importlib.import_module
    try:
        spec = find_spec("open3d")
    except Exception as error:
        raise RuntimeError(f"Open3D usability check failed: {error}") from error
    if spec is None:
        raise RuntimeError(
            "Open3D is missing; install it in the ROS Python environment with "
            "python3 -m pip install open3d"
        )
    try:
        importer("open3d")
    except Exception as error:
        raise RuntimeError(
            "Open3D is unusable; import failed: "
            f"{error}. Reinstall Open3D in the active ROS Python environment"
        ) from error


def _evidence_record(frame: CupPoseFrame, options: RgbdCupPoseOptions) -> dict[str, Any]:
    points = frame.cloud.points_xyz
    return {
        "status": "OK",
        "stamp_ns": frame.stamp_ns,
        "input_frame_id": frame.source_frame_id,
        "output_frame_id": WORLD_FRAME,
        "output_topic": options.output_topic,
        "cup_pose_position_xyz": list(frame.center_world_xyz),
        "cup_pose_orientation_xyzw": [0.0, 0.0, 0.0, 1.0],
        "fitted_radius_m": frame.fitted_radius_m,
        "expected_radius_m": options.expected_radius,
        "image_width": frame.cloud.image_width,
        "image_height": frame.cloud.image_height,
        "full_point_count": frame.cloud.full_point_count,
        "color_candidate_point_count": frame.cloud.color_candidate_point_count,
        "cup_point_count": frame.cloud.cup_point_count,
        "cup_bounds_min_xyz": points.min(axis=0).tolist(),
        "cup_bounds_max_xyz": points.max(axis=0).tolist(),
        "output_ply": str(options.output_ply),
        "output_rgb": None if options.output_rgb is None else str(options.output_rgb),
        "output_full_ply": (
            None if options.output_full_ply is None else str(options.output_full_ply)
        ),
        "output_preview": (
            None if options.output_preview is None else str(options.output_preview)
        ),
    }


def _write_evidence_json(frame: CupPoseFrame, options: RgbdCupPoseOptions) -> None:
    options.evidence_json.parent.mkdir(parents=True, exist_ok=True)
    options.evidence_json.write_text(
        json.dumps(_evidence_record(frame, options), sort_keys=True) + "\n",
        encoding="utf-8",
    )


def pose_message_from_frame(
    frame: CupPoseFrame,
    *,
    pose_factory: Callable[[], Any],
    stamp_from_ns: Callable[[int], Any],
) -> Any:
    """Create the exact-stamp identity-orientation world PoseStamped payload."""
    pose = pose_factory()
    pose.header.stamp = stamp_from_ns(frame.stamp_ns)
    pose.header.frame_id = WORLD_FRAME
    pose.pose.position.x = frame.center_world_xyz[0]
    pose.pose.position.y = frame.center_world_xyz[1]
    pose.pose.position.z = frame.center_world_xyz[2]
    pose.pose.orientation.x = 0.0
    pose.pose.orientation.y = 0.0
    pose.pose.orientation.z = 0.0
    pose.pose.orientation.w = 1.0
    return pose


def estimate_cup_pose_frame(
    aligned: tuple[Any, Any, Any],
    options: RgbdCupPoseOptions,
    *,
    build_cloud: Callable[..., CupPointCloudResult] = build_cup_point_cloud,
    lookup_transform: Callable[[str, str, Any, float], Any],
    stamp_to_time: Callable[[Any], Any],
    tf_timeout_budget: Callable[[], float],
) -> CupPoseFrame:
    """Build, exactly transform, and fit one aligned RGB-D sample in memory."""
    camera_info, color, depth = aligned
    cloud = build_cloud(
        camera_info,
        color,
        depth,
        depth_trunc_m=options.depth_trunc_m,
        cluster_eps_m=options.cluster_eps_m,
        cluster_min_points=options.cluster_min_points,
        minimum_cup_points=options.minimum_cup_points,
    )
    if cloud.stamp_ns <= 0:
        raise ValueError("RGB-D source stamp must be nonzero")
    timeout_s = tf_timeout_budget()
    if not math.isfinite(timeout_s) or timeout_s <= 0.0:
        raise TimeoutError("startup deadline expired before exact-stamp TF lookup")
    transform = lookup_transform(
        WORLD_FRAME,
        cloud.frame_id,
        stamp_to_time(camera_info.header.stamp),
        timeout_s,
    )
    estimate = estimate_world_cup_pose(
        cloud.points_xyz,
        transform,
        table_top_z=options.table_top_z,
        cup_height=options.cup_height,
        expected_radius=options.expected_radius,
        radius_tolerance=options.radius_tolerance,
    )
    return CupPoseFrame(
        stamp_ns=cloud.stamp_ns,
        source_frame_id=cloud.frame_id,
        center_world_xyz=estimate.center_world_xyz,
        fitted_radius_m=estimate.fitted_radius_m,
        cloud=cloud,
    )


def bounded_tf_timeout_s(
    configured_timeout_s: float,
    *,
    first_valid_published: bool,
    startup_deadline: float,
    monotonic: Callable[[], float],
) -> float:
    """Cap pre-success TF blocking at the remaining monotonic startup budget."""
    if first_valid_published:
        return configured_timeout_s
    return min(configured_timeout_s, startup_deadline - monotonic())


def _load_ros_api() -> Any:
    import rclpy
    from geometry_msgs.msg import PoseStamped
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
) -> _Runtime:
    if startup_deadline - monotonic() <= 0.0:
        raise TimeoutError("startup deadline expired before ROS runtime construction")
    ros = ros_api or _load_ros_api()

    initialized_here = not ros.rclpy.ok()
    node = None
    tf_listener = None
    publisher = None
    subscriptions: list[Any] = []
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

        class RosRuntime:
            def __init__(self) -> None:
                self._buffer = AlignedRgbdBuffer()
                self._fresh_frames = FreshFrameGate()
                self._subscriptions = subscriptions
                self._inputs_released = False
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
                )

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

            def close(self) -> None:
                cleanup.close()

        return RosRuntime()
    except BaseException as primary:
        try:
            cleanup.close()
        except CleanupError as cleanup_error:
            raise ResourceConstructionError(primary, cleanup_error) from primary
        raise


def run_rgbd_cup_pose(
    options: RgbdCupPoseOptions,
    *,
    runtime_factory: Callable[
        [RgbdCupPoseOptions, float, Callable[[], float]], _Runtime
    ] = _create_ros_runtime,
    monotonic: Callable[[], float] = time.monotonic,
    open3d_preflight: Callable[[float], None] = _require_open3d,
) -> int:
    """Run until orderly shutdown, failing if startup never publishes a valid frame."""
    deadline = monotonic() + options.startup_timeout_s
    runtime: _Runtime | None = None
    setup_failed = False
    try:
        remaining_startup_s = deadline - monotonic()
        if remaining_startup_s <= 0.0:
            raise TimeoutError("startup deadline expired before Open3D preflight")
        open3d_preflight(remaining_startup_s)
        if deadline - monotonic() <= 0.0:
            raise TimeoutError("startup deadline expired during Open3D preflight")
        runtime = runtime_factory(options, deadline, monotonic)
        if not runtime.first_valid_published and deadline - monotonic() <= 0.0:
            raise TimeoutError("startup deadline expired during ROS runtime construction")
    except TimeoutError as error:
        print(
            _status_line(
                "ERROR", failure="RGBD_CUP_POSE_TIMEOUT", message=str(error)
            ),
            flush=True,
        )
        setup_failed = True
    except KeyboardInterrupt:
        print(
            _status_line(
                "ERROR",
                failure="RGBD_CUP_POSE_INTERRUPTED_BEFORE_FIRST_VALID",
                message="SIGINT arrived during RGB-D cup-pose setup",
            ),
            flush=True,
        )
        setup_failed = True
    except ResourceConstructionError as error:
        print(
            _status_line(
                "ERROR",
                failure="RGBD_CUP_POSE_CLEANUP_FAILED",
                message=str(error),
            ),
            flush=True,
        )
        setup_failed = True
    except (OSError, RuntimeError, ValueError) as error:
        print(
            _status_line(
                "ERROR", failure="RGBD_CUP_POSE_PREFLIGHT_FAILED", message=str(error)
            ),
            flush=True,
        )
        setup_failed = True

    if setup_failed:
        if runtime is not None:
            try:
                runtime.close()
            except BaseException as cleanup_error:
                print(
                    _status_line(
                        "ERROR",
                        failure="RGBD_CUP_POSE_CLEANUP_FAILED",
                        message=str(cleanup_error),
                    ),
                    flush=True,
                )
        return 1

    result = 1
    try:
        while runtime.ok():
            now = monotonic()
            if not runtime.first_valid_published and now >= deadline:
                print(
                    _status_line(
                        "ERROR",
                        failure="RGBD_CUP_POSE_TIMEOUT",
                        message=(
                            "no valid RGB-D cup pose was published within "
                            f"{options.startup_timeout_s:.3f} seconds"
                        ),
                    ),
                    flush=True,
                )
                result = 1
                break
            timeout_s = 0.05
            if not runtime.first_valid_published:
                timeout_s = min(timeout_s, max(0.0, deadline - now))
            runtime.spin_once(timeout_s)
        else:
            if runtime.first_valid_published:
                result = 0
            else:
                print(
                    _status_line(
                        "ERROR",
                        failure="RGBD_CUP_POSE_SHUTDOWN_BEFORE_FIRST_VALID",
                        message=(
                            "ROS context shut down before a valid RGB-D cup pose was published"
                        ),
                    ),
                    flush=True,
                )
                result = 1
    except KeyboardInterrupt:
        if runtime.first_valid_published:
            print(_status_line("STOPPED", reason="SIGINT"), flush=True)
            result = 0
        else:
            print(
                _status_line(
                    "ERROR",
                    failure="RGBD_CUP_POSE_INTERRUPTED_BEFORE_FIRST_VALID",
                    message="SIGINT arrived before a valid RGB-D cup pose was published",
                ),
                flush=True,
            )
            result = 1
    except RuntimeError as error:
        if runtime.first_valid_published and not runtime.ok():
            print(
                _status_line("STOPPED", reason="ROS_CONTEXT_SHUTDOWN"),
                flush=True,
            )
            result = 0
        else:
            print(
                _status_line(
                    "ERROR", failure="RGBD_CUP_POSE_FATAL", message=str(error)
                ),
                flush=True,
            )
            result = 1
    except (OSError, TimeoutError, ValueError) as error:
        print(
            _status_line(
                "ERROR", failure="RGBD_CUP_POSE_FATAL", message=str(error)
            ),
            flush=True,
        )
        result = 1
    finally:
        try:
            runtime.close()
        except BaseException as cleanup_error:
            print(
                _status_line(
                    "ERROR",
                    failure="RGBD_CUP_POSE_CLEANUP_FAILED",
                    message=str(cleanup_error),
                ),
                flush=True,
            )
            result = 1
    return result
