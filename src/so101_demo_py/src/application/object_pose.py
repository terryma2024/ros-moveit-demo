"""Application rules for selecting and localizing one requested object."""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

import numpy as np

from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionQuery,
    LocalizedObject,
)


class TargetSelectionError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class TargetSelector:
    def select(
        self,
        batch: DetectionBatch,
        query: DetectionQuery,
        confidence_threshold: float,
    ) -> DetectionCandidate:
        if not math.isfinite(confidence_threshold) or not 0.0 <= confidence_threshold <= 1.0:
            raise ValueError("confidence_threshold must be finite and in [0, 1]")
        matches = tuple(
            candidate
            for candidate in batch.candidates
            if candidate.class_id == query.class_id
            and candidate.confidence >= confidence_threshold
        )
        if not matches:
            raise TargetSelectionError("TARGET_NOT_FOUND")
        if len(matches) > 1:
            raise TargetSelectionError("TARGET_AMBIGUOUS")
        return matches[0]


class LocalizationError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def _default_point_cloud_builder(
    candidate: DetectionCandidate,
    camera_info: Any,
    depth_message: Any,
    *,
    depth_trunc_m: float,
) -> np.ndarray:
    from so101_demo.cli.rgbd_point_cloud import build_mask_point_cloud

    return build_mask_point_cloud(
        candidate,
        camera_info,
        depth_message,
        depth_trunc_m=depth_trunc_m,
    )


def _default_outlier_cleaner(
    points: np.ndarray,
    cluster_eps_m: float,
    cluster_min_points: int,
) -> np.ndarray:
    from so101_demo.cli.rgbd_point_cloud import _open3d_cloud

    _, cloud = _open3d_cloud(points, np.zeros_like(points))
    labels = np.asarray(
        cloud.cluster_dbscan(
            eps=cluster_eps_m,
            min_points=cluster_min_points,
            print_progress=False,
        )
    )
    cluster_ids = np.unique(labels[labels >= 0])
    if len(cluster_ids) == 0:
        return np.empty((0, 3), dtype=np.float64)
    full_median = np.median(points, axis=0)
    selected_id = min(
        (int(cluster_id) for cluster_id in cluster_ids),
        key=lambda cluster_id: float(
            np.linalg.norm(np.median(points[labels == cluster_id], axis=0) - full_median)
        ),
    )
    return np.asarray(points[labels == selected_id], dtype=np.float64)


class RgbdLocalizer:
    def __init__(
        self,
        *,
        depth_trunc_m: float = 3.0,
        minimum_cup_points: int = 50,
        cluster_eps_m: float = 0.02,
        cluster_min_points: int = 5,
        table_top_z: float = 0.12,
        cup_height: float = 0.09,
        expected_radius_m: float = 0.04,
        radius_tolerance_m: float = 0.01,
        workspace_min_xyz: tuple[float, float, float] = (-0.2, -0.5, 0.1),
        workspace_max_xyz: tuple[float, float, float] = (0.2, -0.1, 0.3),
        point_cloud_builder: Callable[..., np.ndarray] = _default_point_cloud_builder,
        outlier_cleaner: Callable[..., np.ndarray] = _default_outlier_cleaner,
    ) -> None:
        positive_floats = {
            "depth_trunc_m": depth_trunc_m,
            "cluster_eps_m": cluster_eps_m,
            "cup_height": cup_height,
            "expected_radius_m": expected_radius_m,
            "radius_tolerance_m": radius_tolerance_m,
        }
        if any(not math.isfinite(value) or value <= 0.0 for value in positive_floats.values()):
            raise ValueError("localizer distances and dimensions must be finite and positive")
        if minimum_cup_points <= 0 or cluster_min_points <= 0:
            raise ValueError("localizer point counts must be positive")
        if not math.isfinite(table_top_z):
            raise ValueError("table_top_z must be finite")
        if len(workspace_min_xyz) != 3 or len(workspace_max_xyz) != 3:
            raise ValueError("workspace bounds must contain three values")
        if not all(
            math.isfinite(lower) and math.isfinite(upper) and lower < upper
            for lower, upper in zip(workspace_min_xyz, workspace_max_xyz, strict=True)
        ):
            raise ValueError("workspace lower bounds must be below finite upper bounds")
        self._depth_trunc_m = depth_trunc_m
        self._minimum_cup_points = minimum_cup_points
        self._cluster_eps_m = cluster_eps_m
        self._cluster_min_points = cluster_min_points
        self._table_top_z = table_top_z
        self._cup_height = cup_height
        self._expected_radius_m = expected_radius_m
        self._radius_tolerance_m = radius_tolerance_m
        self._workspace_min = np.asarray(workspace_min_xyz, dtype=np.float64)
        self._workspace_max = np.asarray(workspace_max_xyz, dtype=np.float64)
        self._point_cloud_builder = point_cloud_builder
        self._outlier_cleaner = outlier_cleaner

    def localize(
        self,
        candidate: DetectionCandidate,
        camera_info: Any,
        depth_message: Any,
        lookup_transform: Callable[[str, str, int], Any],
    ) -> LocalizedObject:
        try:
            points_camera = np.asarray(
                self._point_cloud_builder(
                    candidate,
                    camera_info,
                    depth_message,
                    depth_trunc_m=self._depth_trunc_m,
                ),
                dtype=np.float64,
            )
        except ValueError as error:
            raise LocalizationError("RGBD_INVALID", str(error)) from error
        if (
            points_camera.ndim != 2
            or points_camera.shape[1:] != (3,)
            or not np.isfinite(points_camera).all()
            or len(points_camera) < self._minimum_cup_points
        ):
            raise LocalizationError(
                "DEPTH_INVALID",
                f"selected mask produced {len(points_camera)} valid points; "
                f"required {self._minimum_cup_points}",
            )
        clean_points = np.asarray(
            self._outlier_cleaner(
                points_camera,
                self._cluster_eps_m,
                self._cluster_min_points,
            ),
            dtype=np.float64,
        )
        if (
            clean_points.ndim != 2
            or clean_points.shape[1:] != (3,)
            or not np.isfinite(clean_points).all()
            or len(clean_points) < self._minimum_cup_points
        ):
            raise LocalizationError(
                "GEOMETRY_REJECTED",
                f"instance outlier cleanup retained {len(clean_points)} points; "
                f"required {self._minimum_cup_points}",
            )
        try:
            transform = lookup_transform(
                "world",
                candidate.source_frame_id,
                candidate.source_stamp_ns,
            )
        except Exception as error:
            raise LocalizationError("TF_UNAVAILABLE", str(error)) from error

        from so101_demo.cli.rgbd_cup_pose import (
            estimate_upright_cup_pose,
            transform_points,
        )

        try:
            points_world = transform_points(clean_points, transform)
        except ValueError as error:
            raise LocalizationError("TF_UNAVAILABLE", str(error)) from error
        try:
            center, fitted_radius = estimate_upright_cup_pose(
                points_world,
                table_top_z=self._table_top_z,
                cup_height=self._cup_height,
                expected_radius=self._expected_radius_m,
                radius_tolerance=self._radius_tolerance_m,
            )
        except ValueError as error:
            raise LocalizationError("GEOMETRY_REJECTED", str(error)) from error
        if bool(np.any(center < self._workspace_min) or np.any(center > self._workspace_max)):
            raise LocalizationError(
                "GEOMETRY_REJECTED",
                f"localized center {center.tolist()} is outside the configured workspace",
            )
        return LocalizedObject(
            instance_id=candidate.instance_id,
            class_id=candidate.class_id,
            source_stamp_ns=candidate.source_stamp_ns,
            source_frame_id=candidate.source_frame_id,
            center_world_xyz=tuple(float(value) for value in center),
            fitted_radius_m=float(fitted_radius),
            valid_depth_point_count=len(points_world),
            points_world=points_world,
        )
