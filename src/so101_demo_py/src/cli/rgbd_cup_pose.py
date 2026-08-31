"""Estimate an upright cup body pose from an in-memory RGB-D point cloud."""

from __future__ import annotations

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np


def transform_points(points: np.ndarray, transform_stamped: Any) -> np.ndarray:
    """Apply target<-source TransformStamped to source-frame XYZ points."""
    if points.ndim != 2 or points.shape[1] != 3 or len(points) == 0:
        raise ValueError("points must be a non-empty array with shape (count, 3)")
    if not np.isfinite(points).all():
        raise ValueError("points must be finite")

    transform = transform_stamped.transform
    quaternion = np.array(
        [
            transform.rotation.x,
            transform.rotation.y,
            transform.rotation.z,
            transform.rotation.w,
        ],
        dtype=np.float64,
    )
    norm = float(np.linalg.norm(quaternion))
    if not math.isfinite(norm) or norm <= 0.0:
        raise ValueError("transform quaternion must be finite and non-zero")
    x, y, z, w = quaternion / norm
    rotation = np.array(
        [
            [1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)],
            [2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)],
            [2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)],
        ]
    )
    translation = np.array(
        [transform.translation.x, transform.translation.y, transform.translation.z],
        dtype=np.float64,
    )
    if not np.isfinite(translation).all():
        raise ValueError("transform translation must be finite")
    return points.astype(np.float64, copy=False) @ rotation.T + translation


def fit_circle_xy(points: np.ndarray) -> tuple[np.ndarray, float]:
    """Fit an algebraic circle to the XY projection of upright-cylinder points."""
    if points.ndim != 2 or points.shape[1] != 3 or len(points) < 3:
        raise ValueError("points must contain at least three XYZ samples")
    if not np.isfinite(points).all():
        raise ValueError("points must be finite")

    xy = points[:, :2].astype(np.float64, copy=False)
    design = np.column_stack((2.0 * xy[:, 0], 2.0 * xy[:, 1], np.ones(len(xy))))
    squared_radius_terms = np.sum(xy * xy, axis=1)
    solution, _, rank, _ = np.linalg.lstsq(design, squared_radius_terms, rcond=None)
    if rank < 3:
        raise ValueError("cup XY samples are degenerate for circle fitting")
    center = solution[:2]
    radius_squared = float(solution[2] + np.dot(center, center))
    if not math.isfinite(radius_squared) or radius_squared <= 0.0:
        raise ValueError("circle fit produced an invalid radius")
    return center, math.sqrt(radius_squared)


def estimate_upright_cup_pose(
    points_world: np.ndarray,
    *,
    table_top_z: float,
    cup_height: float,
    expected_radius: float,
    radius_tolerance: float,
) -> tuple[np.ndarray, float]:
    """Estimate the upright cup body origin from its wall and table support."""
    values = (table_top_z, cup_height, expected_radius, radius_tolerance)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("cup geometry parameters must be finite")
    if cup_height <= 0.0 or expected_radius <= 0.0 or radius_tolerance <= 0.0:
        raise ValueError("cup dimensions and radius_tolerance must be positive")

    center_xy, fitted_radius = fit_circle_xy(points_world)
    radius_error = abs(fitted_radius - expected_radius)
    if radius_error > radius_tolerance:
        raise ValueError(
            f"fitted radius {fitted_radius:.6f} differs from expected "
            f"{expected_radius:.6f} by more than {radius_tolerance:.6f} m"
        )
    center = np.array(
        [center_xy[0], center_xy[1], table_top_z + cup_height / 2.0],
        dtype=np.float64,
    )
    return center, fitted_radius


@dataclass(frozen=True, slots=True)
class CupPoseEstimate:
    center_world_xyz: tuple[float, float, float]
    fitted_radius_m: float


def estimate_world_cup_pose(
    points_camera: np.ndarray,
    transform_stamped: Any,
    *,
    table_top_z: float,
    cup_height: float,
    expected_radius: float,
    radius_tolerance: float,
) -> CupPoseEstimate:
    """Transform camera points to world, then fit the upright cup there."""
    points_world = transform_points(points_camera, transform_stamped)
    center, radius = estimate_upright_cup_pose(
        points_world,
        table_top_z=table_top_z,
        cup_height=cup_height,
        expected_radius=expected_radius,
        radius_tolerance=radius_tolerance,
    )
    return CupPoseEstimate(
        center_world_xyz=tuple(float(value) for value in center),
        fitted_radius_m=float(radius),
    )


def _positive_finite(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0.0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return parsed


def _positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be positive")
    return parsed


def _absolute_topic(value: str) -> str:
    if not value or not value.startswith("/") or value == "/" or "//" in value:
        raise argparse.ArgumentTypeError("must be a non-empty absolute ROS topic")
    if any(character.isspace() for character in value):
        raise argparse.ArgumentTypeError("must be a non-empty absolute ROS topic")
    return value


def _output_path(value: str) -> Path:
    if not value.strip():
        raise argparse.ArgumentTypeError("must be a non-empty path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute output file path")
    if path.exists() and path.is_dir():
        raise argparse.ArgumentTypeError("must be an output file path, not a directory")
    return path


def _output_root(value: str) -> Path:
    if not value.strip():
        raise argparse.ArgumentTypeError("must be a non-empty absolute directory path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute directory path")
    if path.exists() and not path.is_dir():
        raise argparse.ArgumentTypeError("must be a directory path")
    return path


def _application_arguments(arguments: list[str] | None) -> list[str]:
    raw_arguments = list(sys.argv[1:] if arguments is None else arguments)
    if "--ros-args" not in raw_arguments:
        return raw_arguments
    from rclpy.utilities import remove_ros_args

    return remove_ros_args(args=["rgbd_cup_pose", *raw_arguments])[1:]


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rgbd_cup_pose",
        description="Continuously publish world cup poses from aligned MuJoCo RGB-D",
    )
    parser.add_argument("--startup-timeout-s", type=_positive_finite, default=15.0)
    parser.add_argument("--tf-timeout-s", type=_positive_finite, default=0.2)
    parser.add_argument(
        "--camera-info-topic", type=_absolute_topic, default="/task_camera/camera_info"
    )
    parser.add_argument("--color-topic", type=_absolute_topic, default="/task_camera/color")
    parser.add_argument("--depth-topic", type=_absolute_topic, default="/task_camera/depth")
    parser.add_argument("--output-topic", type=_absolute_topic, default="/cup_pose")
    parser.add_argument("--table-top-z", type=_positive_finite, default=0.12)
    parser.add_argument("--cup-height", type=_positive_finite, default=0.09)
    parser.add_argument("--expected-radius", type=_positive_finite, default=0.04)
    parser.add_argument("--radius-tolerance", type=_positive_finite, default=0.01)
    parser.add_argument("--depth-trunc-m", type=_positive_finite, default=3.0)
    parser.add_argument("--cluster-eps-m", type=_positive_finite, default=0.02)
    parser.add_argument("--cluster-min-points", type=_positive_integer, default=5)
    parser.add_argument("--minimum-cup-points", type=_positive_integer, default=50)
    parser.add_argument(
        "--output-ply", type=_output_path, default=Path("/tmp/v4-t006-cup-cloud.ply")
    )
    parser.add_argument(
        "--evidence-json",
        type=_output_path,
        default=Path("/tmp/v4-t006-cup-pose.json"),
    )
    parser.add_argument("--output-rgb", type=_output_path)
    parser.add_argument("--output-full-ply", type=_output_path)
    parser.add_argument("--output-preview", type=_output_path)
    parser.add_argument(
        "--profiling",
        choices=("off", "summary", "trace"),
        default="off",
    )
    parser.add_argument("--profiling-output-root", type=_output_root)
    parser.add_argument("--profiling-session-id")
    parsed = parser.parse_args(_application_arguments(arguments))

    from so101_demo.ros.rgbd_cup_pose_node import (
        RgbdCupPoseOptions,
        run_rgbd_cup_pose,
    )

    try:
        options = RgbdCupPoseOptions(
            startup_timeout_s=parsed.startup_timeout_s,
            tf_timeout_s=parsed.tf_timeout_s,
            camera_info_topic=parsed.camera_info_topic,
            color_topic=parsed.color_topic,
            depth_topic=parsed.depth_topic,
            output_topic=parsed.output_topic,
            table_top_z=parsed.table_top_z,
            cup_height=parsed.cup_height,
            expected_radius=parsed.expected_radius,
            radius_tolerance=parsed.radius_tolerance,
            depth_trunc_m=parsed.depth_trunc_m,
            cluster_eps_m=parsed.cluster_eps_m,
            cluster_min_points=parsed.cluster_min_points,
            minimum_cup_points=parsed.minimum_cup_points,
            output_ply=parsed.output_ply,
            evidence_json=parsed.evidence_json,
            output_rgb=parsed.output_rgb,
            output_full_ply=parsed.output_full_ply,
            output_preview=parsed.output_preview,
        )
    except ValueError as error:
        parser.error(str(error))
    if parsed.profiling == "off":
        return run_rgbd_cup_pose(options)

    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler

    if parsed.profiling_output_root is None:
        parser.error("enabled profiling requires --profiling-output-root")
    if not parsed.profiling_session_id or not parsed.profiling_session_id.strip():
        parser.error("enabled profiling requires --profiling-session-id")
    profiler = build_profiler(
        ProfilingConfig(
            mode=ProfilingMode.parse(parsed.profiling),
            output_root=parsed.profiling_output_root,
            session_id=parsed.profiling_session_id.strip(),
            process_role="perception",
        )
    )
    assert profiler is not None
    try:
        return run_rgbd_cup_pose(options, profiler=profiler)
    finally:
        profiler.close()


if __name__ == "__main__":
    raise SystemExit(main())
