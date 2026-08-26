"""Convert one aligned MuJoCo RGB-D sample into an Open3D cup point cloud."""

from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


def message_stamp_ns(message: Any) -> int:
    stamp = message.header.stamp
    return int(stamp.sec) * 1_000_000_000 + int(stamp.nanosec)


@dataclass(frozen=True, slots=True)
class CupPointCloudResult:
    frame_id: str
    stamp_ns: int
    image_width: int
    image_height: int
    intrinsics_fx_fy_cx_cy: tuple[float, float, float, float]
    points_xyz: np.ndarray
    colors_rgb: np.ndarray
    full_point_count: int
    color_candidate_point_count: int

    @property
    def cup_point_count(self) -> int:
        return int(self.points_xyz.shape[0])


class AlignedRgbdBuffer:
    def __init__(self, max_samples: int = 20) -> None:
        if max_samples <= 0:
            raise ValueError("max_samples must be positive")
        self._max_samples = max_samples
        self._camera_infos: dict[int, Any] = {}
        self._colors: dict[int, Any] = {}
        self._depths: dict[int, Any] = {}

    def _add(
        self,
        messages: dict[int, Any],
        message: Any,
    ) -> tuple[Any, Any, Any] | None:
        messages[message_stamp_ns(message)] = message
        while len(messages) > self._max_samples:
            messages.pop(next(iter(messages)))
        common = self._camera_infos.keys() & self._colors.keys() & self._depths.keys()
        if not common:
            return None
        stamp = max(common)
        return (
            self._camera_infos.pop(stamp),
            self._colors.pop(stamp),
            self._depths.pop(stamp),
        )

    def add_camera_info(self, message: Any) -> tuple[Any, Any, Any] | None:
        return self._add(self._camera_infos, message)

    def add_color(self, message: Any) -> tuple[Any, Any, Any] | None:
        return self._add(self._colors, message)

    def add_depth(self, message: Any) -> tuple[Any, Any, Any] | None:
        return self._add(self._depths, message)


def back_project_depth(
    depth: np.ndarray,
    *,
    fx: float,
    fy: float,
    cx: float,
    cy: float,
    depth_trunc_m: float,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Back-project valid depth pixels into optical-style XYZ coordinates."""
    if depth.ndim != 2:
        raise ValueError("depth must be a two-dimensional array")
    if not all(math.isfinite(value) and value > 0.0 for value in (fx, fy)):
        raise ValueError("fx and fy must be finite and positive")
    if not math.isfinite(depth_trunc_m) or depth_trunc_m <= 0.0:
        raise ValueError("depth_trunc_m must be finite and positive")

    valid = np.isfinite(depth) & (depth > 0.0) & (depth <= depth_trunc_m)
    pixel_rows, pixel_columns = np.nonzero(valid)
    z = depth[pixel_rows, pixel_columns].astype(np.float64, copy=False)
    x = (pixel_columns.astype(np.float64) - cx) * z / fx
    y = (pixel_rows.astype(np.float64) - cy) * z / fy
    return np.column_stack((x, y, z)), pixel_rows, pixel_columns


def orange_cup_mask(rgb: np.ndarray) -> np.ndarray:
    """Select the orange MuJoCo cup while rejecting the brown table and red target."""
    if rgb.ndim != 3 or rgb.shape[2] != 3:
        raise ValueError("rgb must have shape (height, width, 3)")
    channels = rgb.astype(np.int16, copy=False)
    red = channels[:, :, 0]
    green = channels[:, :, 1]
    blue = channels[:, :, 2]
    return (
        (red >= 140)
        & (green >= 50)
        & (green <= 210)
        & (blue <= 110)
        & ((red - green) >= 35)
        & ((green - blue) >= 20)
    )


def robust_center(points: np.ndarray) -> np.ndarray:
    """Estimate a point-set center without allowing a few outliers to dominate."""
    if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
        raise ValueError("points must be a non-empty array with shape (count, 3)")
    if not np.isfinite(points).all():
        raise ValueError("points must be finite")
    return np.median(points, axis=0)


def largest_cluster_indices(labels: np.ndarray) -> np.ndarray:
    """Return indices belonging to the largest non-noise DBSCAN cluster."""
    if labels.ndim != 1:
        raise ValueError("labels must be a one-dimensional array")
    cluster_labels, counts = np.unique(labels[labels >= 0], return_counts=True)
    if len(cluster_labels) == 0:
        raise ValueError("DBSCAN found no cup cluster")
    largest_label = cluster_labels[np.argmax(counts)]
    return np.flatnonzero(labels == largest_label)


def _decode_rgb(message: Any) -> np.ndarray:
    if message.encoding.lower() != "rgb8":
        raise ValueError(f"expected rgb8 color image, got {message.encoding}")
    expected_step = int(message.width) * 3
    if int(message.step) != expected_step:
        raise ValueError(f"rgb step is {message.step}, expected {expected_step}")
    expected = int(message.height) * int(message.width) * 3
    if len(message.data) != expected:
        raise ValueError(f"rgb data has {len(message.data)} bytes, expected {expected}")
    return np.frombuffer(message.data, dtype=np.uint8).reshape(
        int(message.height), int(message.width), 3
    )


def _decode_depth(message: Any) -> np.ndarray:
    if message.encoding.upper() != "32FC1":
        raise ValueError(f"expected 32FC1 depth image, got {message.encoding}")
    expected_step = int(message.width) * 4
    if int(message.step) != expected_step:
        raise ValueError(f"depth step is {message.step}, expected {expected_step}")
    expected = int(message.height) * int(message.width) * 4
    if len(message.data) != expected:
        raise ValueError(f"depth data has {len(message.data)} bytes, expected {expected}")
    byte_order = ">f4" if bool(message.is_bigendian) else "<f4"
    return np.frombuffer(message.data, dtype=byte_order).reshape(
        int(message.height), int(message.width)
    ).astype(np.float32, copy=True)


def _capture_aligned_rgbd(timeout_s: float) -> tuple[Any, Any, Any]:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import CameraInfo, Image

    class AlignedRgbdCapture(Node):
        def __init__(self) -> None:
            super().__init__("rgbd_point_cloud_capture")
            self.buffer = AlignedRgbdBuffer()
            self.aligned: tuple[CameraInfo, Image, Image] | None = None
            self.create_subscription(
                CameraInfo, "/task_camera/camera_info", self._on_camera_info, 10
            )
            self.create_subscription(Image, "/task_camera/color", self._on_color, 10)
            self.create_subscription(Image, "/task_camera/depth", self._on_depth, 10)

        def _on_camera_info(self, message: CameraInfo) -> None:
            self.aligned = self.buffer.add_camera_info(message) or self.aligned

        def _on_color(self, message: Image) -> None:
            self.aligned = self.buffer.add_color(message) or self.aligned

        def _on_depth(self, message: Image) -> None:
            self.aligned = self.buffer.add_depth(message) or self.aligned

    initialized_here = not rclpy.ok()
    if initialized_here:
        rclpy.init()
    node = AlignedRgbdCapture()
    deadline = time.monotonic() + timeout_s
    try:
        while node.aligned is None and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
        if node.aligned is None:
            raise TimeoutError(f"no aligned /task_camera RGB-D sample within {timeout_s:.1f}s")
        return node.aligned
    finally:
        node.destroy_node()
        if initialized_here and rclpy.ok():
            rclpy.shutdown()


def _open3d_cloud(points: np.ndarray, colors: np.ndarray):
    try:
        import open3d as o3d
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Open3D is missing; install it in the ROS Python environment with "
            "python3 -m pip install open3d"
        ) from error
    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points.astype(np.float64, copy=False))
    cloud.colors = o3d.utility.Vector3dVector(colors.astype(np.float64, copy=False))
    return o3d, cloud


def build_cup_point_cloud(
    camera_info: Any,
    color_message: Any,
    depth_message: Any,
    *,
    depth_trunc_m: float,
    cluster_eps_m: float,
    cluster_min_points: int,
    minimum_cup_points: int,
) -> CupPointCloudResult:
    if not (
        camera_info.header.frame_id
        == color_message.header.frame_id
        == depth_message.header.frame_id
    ):
        raise ValueError("CameraInfo, RGB, and depth frame_id values differ")
    if not (
        (camera_info.width, camera_info.height)
        == (color_message.width, color_message.height)
        == (depth_message.width, depth_message.height)
    ):
        raise ValueError("CameraInfo, RGB, and depth dimensions differ")
    if not (
        message_stamp_ns(camera_info)
        == message_stamp_ns(color_message)
        == message_stamp_ns(depth_message)
    ):
        raise ValueError("CameraInfo, RGB, and depth stamps differ")
    if minimum_cup_points <= 0:
        raise ValueError("minimum_cup_points must be positive")

    rgb = _decode_rgb(color_message)
    depth = _decode_depth(depth_message)
    fx, fy, cx, cy = (
        float(camera_info.k[0]),
        float(camera_info.k[4]),
        float(camera_info.k[2]),
        float(camera_info.k[5]),
    )
    points, pixel_rows, pixel_columns = back_project_depth(
        depth,
        fx=fx,
        fy=fy,
        cx=cx,
        cy=cy,
        depth_trunc_m=depth_trunc_m,
    )
    if len(points) == 0:
        raise ValueError("depth image produced no valid 3D points")
    if not np.isfinite(points).all():
        raise ValueError("depth image produced non-finite 3D points")
    colors = rgb[pixel_rows, pixel_columns].astype(np.float64) / 255.0
    _, full_cloud = _open3d_cloud(points, colors)

    cup_pixels = orange_cup_mask(rgb)[pixel_rows, pixel_columns]
    color_candidate_indices = np.flatnonzero(cup_pixels)
    if len(color_candidate_indices) < minimum_cup_points:
        raise ValueError(
            f"orange crop produced {len(color_candidate_indices)} points, "
            f"fewer than required {minimum_cup_points}"
        )
    if not math.isfinite(cluster_eps_m) or cluster_eps_m <= 0.0:
        raise ValueError("cluster_eps_m must be finite and positive")
    if cluster_min_points <= 0:
        raise ValueError("cluster_min_points must be positive")
    color_candidate_cloud = full_cloud.select_by_index(color_candidate_indices.tolist())
    labels = np.asarray(
        color_candidate_cloud.cluster_dbscan(
            eps=cluster_eps_m,
            min_points=cluster_min_points,
            print_progress=False,
        )
    )
    cup_cluster_indices = largest_cluster_indices(labels)
    cup_cloud = color_candidate_cloud.select_by_index(cup_cluster_indices.tolist())
    cup_points = np.asarray(cup_cloud.points)
    if len(cup_points) < minimum_cup_points:
        raise ValueError(
            f"largest orange cluster contains {len(cup_points)} points, "
            f"fewer than required {minimum_cup_points}"
        )
    cup_colors = np.asarray(cup_cloud.colors)
    if cup_points.ndim != 2 or cup_points.shape[1] != 3 or not np.isfinite(cup_points).all():
        raise ValueError("selected cup points must be finite XYZ values")
    if cup_colors.shape != cup_points.shape or not np.isfinite(cup_colors).all():
        raise ValueError("selected cup colors must be finite RGB values")

    return CupPointCloudResult(
        frame_id=camera_info.header.frame_id,
        stamp_ns=message_stamp_ns(camera_info),
        image_width=int(camera_info.width),
        image_height=int(camera_info.height),
        intrinsics_fx_fy_cx_cy=(fx, fy, cx, cy),
        points_xyz=cup_points,
        colors_rgb=cup_colors,
        full_point_count=len(points),
        color_candidate_point_count=len(color_candidate_indices),
    )


def write_cup_point_cloud(result: CupPointCloudResult, output_ply: Path) -> None:
    o3d, cup_cloud = _open3d_cloud(result.points_xyz, result.colors_rgb)

    output_ply.parent.mkdir(parents=True, exist_ok=True)
    if not o3d.io.write_point_cloud(str(output_ply), cup_cloud):
        raise RuntimeError(f"failed to write point cloud to {output_ply}")



def build_point_cloud_report(
    camera_info: Any,
    color_message: Any,
    depth_message: Any,
    *,
    depth_trunc_m: float,
    cluster_eps_m: float,
    cluster_min_points: int,
    minimum_cup_points: int,
    output_ply: Path,
) -> dict[str, Any]:
    result = build_cup_point_cloud(
        camera_info,
        color_message,
        depth_message,
        depth_trunc_m=depth_trunc_m,
        cluster_eps_m=cluster_eps_m,
        cluster_min_points=cluster_min_points,
        minimum_cup_points=minimum_cup_points,
    )
    write_cup_point_cloud(result, output_ply)
    center = robust_center(result.points_xyz)
    bounds_min = result.points_xyz.min(axis=0)
    bounds_max = result.points_xyz.max(axis=0)

    return {
        "status": "OK",
        "frame_id": result.frame_id,
        "stamp_ns": result.stamp_ns,
        "image_width": result.image_width,
        "image_height": result.image_height,
        "intrinsics_fx_fy_cx_cy": list(result.intrinsics_fx_fy_cx_cy),
        "full_point_count": result.full_point_count,
        "color_candidate_point_count": result.color_candidate_point_count,
        "cup_point_count": result.cup_point_count,
        "cup_center_xyz": center.tolist(),
        "cup_bounds_min_xyz": bounds_min.tolist(),
        "cup_bounds_max_xyz": bounds_max.tolist(),
        "output_ply": str(output_ply),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert aligned MuJoCo RGB-D topics into an Open3D cup point cloud"
    )
    parser.add_argument("--timeout-s", type=float, default=15.0)
    parser.add_argument("--depth-trunc-m", type=float, default=3.0)
    parser.add_argument("--cluster-eps-m", type=float, default=0.02)
    parser.add_argument("--cluster-min-points", type=int, default=5)
    parser.add_argument("--minimum-cup-points", type=int, default=50)
    parser.add_argument(
        "--output-ply", type=Path, default=Path("/tmp/v4-t005-cup-cloud.ply")
    )
    args = parser.parse_args()
    try:
        camera_info, color, depth = _capture_aligned_rgbd(args.timeout_s)
        report = build_point_cloud_report(
            camera_info,
            color,
            depth,
            depth_trunc_m=args.depth_trunc_m,
            cluster_eps_m=args.cluster_eps_m,
            cluster_min_points=args.cluster_min_points,
            minimum_cup_points=args.minimum_cup_points,
            output_ply=args.output_ply,
        )
    except (RuntimeError, TimeoutError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "message": str(error)}, sort_keys=True))
        return 1
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
