"""Continuous ROS adapter for RGB-D cup-pose estimation and publication."""

from __future__ import annotations

import importlib
import json
import math
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from so101_demo.cli.rgbd_cup_pose import estimate_world_cup_pose
from so101_demo.cli.rgbd_point_cloud import (
    AlignedRgbdBuffer,
    CupPointCloudResult,
    build_cup_point_cloud,
    message_stamp_ns,
    write_cup_point_cloud,
)

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
        if self.output_ply == self.evidence_json:
            raise ValueError("output_ply and evidence_json must be different paths")


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
    ) -> None:
        self._write_ply = write_ply
        self._write_json = write_json
        self._publish = publish
        self._evidence_written = False
        self.published_count = 0

    def __call__(self, frame: CupPoseFrame) -> None:
        if not self._evidence_written:
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


def _require_open3d() -> None:
    try:
        importlib.import_module("open3d")
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Open3D is missing; install it in the ROS Python environment with "
            "python3 -m pip install open3d"
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


def _create_ros_runtime(options: RgbdCupPoseOptions) -> _Runtime:
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
        qos_profile_sensor_data,
    )
    from rclpy.time import Time
    from sensor_msgs.msg import CameraInfo, Image
    from tf2_ros import Buffer, TransformException, TransformListener

    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init()
    node = rclpy.create_node(
        "rgbd_cup_pose",
        parameter_overrides=[Parameter("use_sim_time", value=True)],
        automatically_declare_parameters_from_overrides=True,
    )
    tf_buffer = Buffer()
    tf_listener = TransformListener(tf_buffer, node)
    pose_qos = QoSProfile(
        depth=1,
        reliability=ReliabilityPolicy.RELIABLE,
        durability=DurabilityPolicy.VOLATILE,
    )
    publisher = node.create_publisher(PoseStamped, options.output_topic, pose_qos)

    class RosRuntime:
        def __init__(self) -> None:
            self._buffer = AlignedRgbdBuffer()
            self._fresh_frames = FreshFrameGate()
            self._subscriptions: list[Any] = []
            self._tf_listener = tf_listener
            self._evidence_publisher = FirstValidEvidencePublisher(
                write_ply=lambda frame: write_cup_point_cloud(
                    frame.cloud, options.output_ply
                ),
                write_json=lambda frame: _write_evidence_json(frame, options),
                publish=self._publish_pose,
            )
            self._processor = CupPoseFrameProcessor(
                estimate=self._estimate_frame,
                publish=self._evidence_publisher,
                on_error=lambda error: node.get_logger().error(
                    _status_line(
                        "ERROR", failure="RGBD_CUP_POSE_FRAME_INVALID", message=str(error)
                    )
                ),
            )
            self._subscriptions.extend(
                (
                    node.create_subscription(
                        CameraInfo,
                        options.camera_info_topic,
                        self._on_camera_info,
                        qos_profile_sensor_data,
                    ),
                    node.create_subscription(
                        Image,
                        options.color_topic,
                        self._on_color,
                        qos_profile_sensor_data,
                    ),
                    node.create_subscription(
                        Image,
                        options.depth_topic,
                        self._on_depth,
                        qos_profile_sensor_data,
                    ),
                )
            )

        @property
        def first_valid_published(self) -> bool:
            return self._evidence_publisher.published_count > 0

        def _estimate_frame(self, aligned: Any) -> CupPoseFrame:
            camera_info, color, depth = aligned
            cloud = build_cup_point_cloud(
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
            try:
                transform = tf_buffer.lookup_transform(
                    WORLD_FRAME,
                    cloud.frame_id,
                    Time.from_msg(camera_info.header.stamp),
                    timeout=Duration(seconds=options.tf_timeout_s),
                )
            except TransformException as error:
                raise RuntimeError(
                    f"exact-stamp transform {WORLD_FRAME} <- {cloud.frame_id} "
                    f"at {cloud.stamp_ns} is unavailable: {error}"
                ) from error
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

        def _publish_pose(self, frame: CupPoseFrame) -> None:
            pose = pose_message_from_frame(
                frame,
                pose_factory=PoseStamped,
                stamp_from_ns=lambda stamp_ns: Time(
                    nanoseconds=stamp_ns, clock_type=ClockType.ROS_TIME
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

        def _process_aligned(self, aligned: Any) -> None:
            stamp_ns = message_stamp_ns(aligned[0])
            if not self._fresh_frames.accept(stamp_ns):
                node.get_logger().error(
                    _status_line(
                        "ERROR",
                        failure="RGBD_CUP_POSE_STALE_FRAME",
                        message=f"source stamp {stamp_ns} is not newer than the prior frame",
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
                rclpy.spin_once(node, timeout_sec=timeout_s)
            except ExternalShutdownException:
                return
            except TransformException as error:
                node.get_logger().error(
                    _status_line(
                        "ERROR", failure="RGBD_CUP_POSE_TF_UNAVAILABLE", message=str(error)
                    )
                )

        def ok(self) -> bool:
            return rclpy.ok()

        def close(self) -> None:
            self._subscriptions.clear()
            del self._processor
            del self._evidence_publisher
            self._tf_listener = None
            node.destroy_node()
            if initialized_here and rclpy.ok():
                rclpy.shutdown()

    return RosRuntime()


def run_rgbd_cup_pose(
    options: RgbdCupPoseOptions,
    *,
    runtime_factory: Callable[[RgbdCupPoseOptions], _Runtime] = _create_ros_runtime,
    monotonic: Callable[[], float] = time.monotonic,
    open3d_preflight: Callable[[], None] = _require_open3d,
) -> int:
    """Run until orderly shutdown, failing if startup never publishes a valid frame."""
    try:
        open3d_preflight()
        runtime = runtime_factory(options)
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(
            _status_line(
                "ERROR", failure="RGBD_CUP_POSE_PREFLIGHT_FAILED", message=str(error)
            ),
            flush=True,
        )
        return 1

    deadline = monotonic() + options.startup_timeout_s
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
                return 1
            timeout_s = 0.05
            if not runtime.first_valid_published:
                timeout_s = min(timeout_s, max(0.0, deadline - now))
            runtime.spin_once(timeout_s)
        return 0
    except KeyboardInterrupt:
        print(_status_line("STOPPED", reason="SIGINT"), flush=True)
        return 0
    except (OSError, RuntimeError, TimeoutError, ValueError) as error:
        print(
            _status_line(
                "ERROR", failure="RGBD_CUP_POSE_FATAL", message=str(error)
            ),
            flush=True,
        )
        return 1
    finally:
        runtime.close()
