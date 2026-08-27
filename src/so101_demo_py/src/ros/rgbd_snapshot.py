"""One-shot exact-stamp RGB-D artifact capture."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Protocol

import numpy as np

from ..cli.rgbd_point_cloud import RgbdPointCloudFrame, build_cup_point_cloud
from ..runtime.point_cloud_preview import render_point_cloud_preview, write_png_rgb8


class SnapshotSource(Protocol):
    def capture(self, timeout_s: float) -> tuple[Any, Any, Any]: ...


class ExactTransformSource(Protocol):
    def lookup_exact(
        self,
        target_frame: str,
        source_frame: str,
        stamp_ns: int,
        timeout_s: float,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class RgbdSnapshotResult:
    frame: RgbdPointCloudFrame
    summary: Mapping[str, object]
    artifacts: Mapping[str, Path]


def write_rgb_png(frame: RgbdPointCloudFrame, output_png: Path) -> None:
    write_png_rgb8(frame.rgb8, output_png)


def write_full_point_cloud(
    points_xyz: np.ndarray,
    colors_rgb: np.ndarray,
    output_ply: Path,
) -> None:
    points = np.asarray(points_xyz, dtype=np.float64)
    colors = np.asarray(colors_rgb, dtype=np.float64)
    if points.ndim != 2 or points.shape[1:] != (3,) or len(points) == 0:
        raise ValueError("point cloud must be a non-empty array with shape (count, 3)")
    if colors.shape != points.shape:
        raise ValueError("point cloud colors must match point shape")
    if not np.isfinite(points).all() or not np.isfinite(colors).all():
        raise ValueError("point cloud must contain finite values")
    color_bytes = np.rint(np.clip(colors, 0.0, 1.0) * 255.0).astype(np.uint8)
    header = (
        "ply\n"
        "format ascii 1.0\n"
        f"element vertex {len(points)}\n"
        "property float x\nproperty float y\nproperty float z\n"
        "property uchar red\nproperty uchar green\nproperty uchar blue\n"
        "end_header\n"
    )
    rows = [
        f"{point[0]:.9g} {point[1]:.9g} {point[2]:.9g} "
        f"{int(color[0])} {int(color[1])} {int(color[2])}\n"
        for point, color in zip(points, color_bytes, strict=True)
    ]
    output_ply.parent.mkdir(parents=True, exist_ok=True)
    output_ply.write_text(header + "".join(rows), encoding="ascii")


def _atomic_json(path: Path, document: Mapping[str, object]) -> None:
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    os.replace(temporary, path)


def capture_rgbd_snapshot(
    source: SnapshotSource,
    transform_source: ExactTransformSource,
    output_directory: Path,
    *,
    timeout_s: float = 15.0,
    tf_timeout_s: float = 0.2,
    depth_trunc_m: float = 3.0,
    cluster_eps_m: float = 0.02,
    cluster_min_points: int = 5,
    minimum_cup_points: int = 50,
    build_cloud: Callable[..., RgbdPointCloudFrame] = build_cup_point_cloud,
) -> RgbdSnapshotResult:
    if not output_directory.is_absolute():
        raise ValueError("output directory must be absolute")
    output_directory.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "rgb": output_directory / "rgb.png",
        "full_cloud": output_directory / "full-cloud.ply",
        "cup_cloud": output_directory / "cup-cloud.ply",
        "point_cloud_preview": output_directory / "point-cloud-preview.png",
        "summary": output_directory / "summary.json",
    }
    if any(path.exists() for path in artifacts.values()):
        raise FileExistsError("snapshot artifact path already exists")
    aligned = source.capture(timeout_s)
    frame = build_cloud(
        *aligned,
        depth_trunc_m=depth_trunc_m,
        cluster_eps_m=cluster_eps_m,
        cluster_min_points=cluster_min_points,
        minimum_cup_points=minimum_cup_points,
    )
    transform_source.lookup_exact("world", frame.frame_id, frame.stamp_ns, tf_timeout_s)
    write_rgb_png(frame, artifacts["rgb"])
    write_full_point_cloud(
        frame.full_points_xyz, frame.full_colors_rgb, artifacts["full_cloud"]
    )
    write_full_point_cloud(
        frame.cup_points_xyz, frame.cup_colors_rgb, artifacts["cup_cloud"]
    )
    preview = render_point_cloud_preview(
        frame.full_points_xyz,
        frame.full_colors_rgb,
        artifacts["point_cloud_preview"],
    )
    summary: dict[str, object] = {
        "status": "OK",
        "source_stamp_ns": frame.stamp_ns,
        "source_frame_id": frame.frame_id,
        "output_frame_id": "world",
        "image_width": frame.image_width,
        "image_height": frame.image_height,
        "full_point_count": frame.full_point_count,
        "color_candidate_point_count": frame.color_candidate_point_count,
        "cup_point_count": frame.cup_point_count,
        "exact_transform_confirmed": True,
        "preview": preview,
    }
    _atomic_json(artifacts["summary"], summary)
    return RgbdSnapshotResult(
        frame,
        MappingProxyType(summary),
        MappingProxyType(artifacts),
    )


class RosRgbdSnapshotSource:
    """Own subscriptions and an exact-stamp TF buffer for one snapshot."""

    def __init__(
        self,
        *,
        camera_info_topic: str = "/task_camera/camera_info",
        color_topic: str = "/task_camera/color",
        depth_topic: str = "/task_camera/depth",
    ) -> None:
        import rclpy
        from rclpy.parameter import Parameter
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import CameraInfo, Image
        from tf2_ros import Buffer, TransformListener

        from ..cli.rgbd_point_cloud import AlignedRgbdBuffer

        self._rclpy = rclpy
        self._initialized_here = not rclpy.ok()
        self._node = None
        self._tf_listener = None
        self._subscriptions: list[Any] = []
        self._closed = False
        if self._initialized_here:
            rclpy.init()
        try:
            self._node = rclpy.create_node(
                "rgbd_sensor_capture",
                parameter_overrides=[Parameter("use_sim_time", value=True)],
            )
            self._buffer = AlignedRgbdBuffer()
            self._aligned = None
            self._tf_buffer = Buffer()
            self._tf_listener = TransformListener(self._tf_buffer, self._node)
            self._subscriptions = [
                self._node.create_subscription(
                    CameraInfo,
                    camera_info_topic,
                    lambda message: self._accept(self._buffer.add_camera_info(message)),
                    qos_profile_sensor_data,
                ),
                self._node.create_subscription(
                    Image,
                    color_topic,
                    lambda message: self._accept(self._buffer.add_color(message)),
                    qos_profile_sensor_data,
                ),
                self._node.create_subscription(
                    Image,
                    depth_topic,
                    lambda message: self._accept(self._buffer.add_depth(message)),
                    qos_profile_sensor_data,
                ),
            ]
        except BaseException as primary:
            try:
                self.close()
            except BaseException as cleanup_error:
                raise RuntimeError(
                    f"RGB-D snapshot construction failed ({primary}); "
                    f"cleanup failed ({cleanup_error})"
                ) from primary
            raise

    def _accept(self, aligned) -> None:
        if aligned is not None:
            self._aligned = aligned

    def capture(self, timeout_s: float):
        deadline = time.monotonic() + timeout_s
        while self._aligned is None and time.monotonic() < deadline:
            self._rclpy.spin_once(self._node, timeout_sec=0.05)
        if self._aligned is None:
            raise TimeoutError("fresh exact-stamp RGB-D sample unavailable")
        return self._aligned

    def lookup_exact(
        self,
        target_frame: str,
        source_frame: str,
        stamp_ns: int,
        timeout_s: float,
    ):
        from rclpy.duration import Duration
        from rclpy.time import Time
        from tf2_ros import TransformException

        query = Time(nanoseconds=stamp_ns)
        deadline = time.monotonic() + timeout_s
        last_error = None
        while time.monotonic() < deadline:
            try:
                return self._tf_buffer.lookup_transform(
                    target_frame,
                    source_frame,
                    query,
                    timeout=Duration(seconds=0.0),
                )
            except TransformException as error:
                last_error = error
                self._rclpy.spin_once(self._node, timeout_sec=0.01)
        raise TimeoutError(f"exact transform unavailable: {last_error}")

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        failures: list[str] = []

        def attempt(label: str, operation: Callable[[], None]) -> None:
            try:
                operation()
            except BaseException as error:
                failures.append(f"{label}: {error}")

        unregister = getattr(self._tf_listener, "unregister", None)
        if callable(unregister):
            attempt("tf_listener", unregister)
        self._tf_listener = None
        if self._node is not None:
            for subscription in reversed(self._subscriptions):
                attempt(
                    "subscription",
                    lambda subscription=subscription: self._node.destroy_subscription(
                        subscription
                    ),
                )
            self._subscriptions.clear()
            attempt("node", self._node.destroy_node)
            self._node = None
        if self._initialized_here and self._rclpy.ok():
            attempt("rclpy_context", self._rclpy.try_shutdown)
        if failures:
            raise RuntimeError("; ".join(failures))
