"""Application rules for selecting and localizing one requested object."""

from __future__ import annotations

import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np

from so101_demo.core.detection import (
    DetectionBatch,
    DetectionCandidate,
    DetectionQuery,
    LocalizedObject,
)
from so101_demo.runtime.workflow_events import EventEmitter, normalize_failure_code


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
    values = np.asarray(points, dtype=np.float64)
    if values.ndim != 2 or values.shape[1:] != (3,) or not np.isfinite(values).all():
        raise ValueError("outlier cleanup points must be finite XYZ values")
    if not math.isfinite(cluster_eps_m) or cluster_eps_m <= 0.0:
        raise ValueError("cluster_eps_m must be finite and positive")
    if cluster_min_points <= 0:
        raise ValueError("cluster_min_points must be positive")
    if len(values) == 0:
        return np.empty((0, 3), dtype=np.float64)

    voxel_coordinates = np.floor(values / cluster_eps_m).astype(np.int64)
    voxels, point_voxel_ids, voxel_counts = np.unique(
        voxel_coordinates,
        axis=0,
        return_inverse=True,
        return_counts=True,
    )
    voxel_lookup = {
        tuple(int(component) for component in coordinate): voxel_id
        for voxel_id, coordinate in enumerate(voxels)
    }
    neighbor_offsets = tuple(
        (x_offset, y_offset, z_offset)
        for x_offset in (-1, 0, 1)
        for y_offset in (-1, 0, 1)
        for z_offset in (-1, 0, 1)
    )

    def neighboring_voxels(voxel_id: int) -> set[int]:
        coordinate = voxels[voxel_id]
        return {
            neighbor_id
            for offset in neighbor_offsets
            if (
                neighbor_id := voxel_lookup.get(
                    tuple(
                        int(coordinate[axis] + offset[axis])
                        for axis in range(3)
                    )
                )
            )
            is not None
        }

    core_voxels = {
        voxel_id
        for voxel_id in range(len(voxels))
        if sum(voxel_counts[neighbor_id] for neighbor_id in neighboring_voxels(voxel_id))
        >= cluster_min_points
    }
    if not core_voxels:
        return np.empty((0, 3), dtype=np.float64)

    components: list[set[int]] = []
    unseen = set(core_voxels)
    while unseen:
        pending = [unseen.pop()]
        component: set[int] = set()
        while pending:
            voxel_id = pending.pop()
            component.add(voxel_id)
            connected = neighboring_voxels(voxel_id) & unseen
            unseen.difference_update(connected)
            pending.extend(connected)
        components.append(component)

    clusters: list[np.ndarray] = []
    for component in components:
        included_voxels: set[int] = set()
        for voxel_id in component:
            included_voxels.update(neighboring_voxels(voxel_id))
        point_indices = np.flatnonzero(
            np.isin(point_voxel_ids, tuple(sorted(included_voxels)))
        )
        if len(point_indices) >= cluster_min_points:
            clusters.append(point_indices)
    if not clusters:
        return np.empty((0, 3), dtype=np.float64)

    full_median = np.median(values, axis=0)
    selected_indices = min(
        clusters,
        key=lambda indices: float(
            np.linalg.norm(np.median(values[indices], axis=0) - full_median)
        ),
    )
    return np.asarray(values[selected_indices], dtype=np.float64)


class RgbdLocalizer:
    def __init__(
        self,
        *,
        depth_trunc_m: float = 3.0,
        minimum_cup_points: int = 50,
        cluster_eps_m: float = 0.015,
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
        self._warm_up_latency_ms: float | None = None

    def warm_up(
        self,
        *,
        monotonic_ns: Callable[[], int] = time.monotonic_ns,
    ) -> float:
        """Prime lazy localization dependencies before accepting a request."""
        if self._warm_up_latency_ms is not None:
            return self._warm_up_latency_ms
        started_ns = monotonic_ns()
        offsets = np.linspace(-0.0035, 0.0035, 8, dtype=np.float64)
        probe_points = np.column_stack(
            (
                offsets,
                np.zeros_like(offsets),
                np.full_like(offsets, 0.5),
            )
        )
        cleaned = np.asarray(
            self._outlier_cleaner(
                probe_points,
                self._cluster_eps_m,
                self._cluster_min_points,
            ),
            dtype=np.float64,
        )
        if cleaned.ndim != 2 or cleaned.shape[1:] != (3,) or len(cleaned) == 0:
            raise RuntimeError("localization warm-up produced no valid cluster")
        from so101_demo.cli.rgbd_cup_pose import (
            estimate_upright_cup_pose as _estimate_upright_cup_pose,
            transform_points as _transform_points,
        )

        if not callable(_estimate_upright_cup_pose) or not callable(_transform_points):
            raise RuntimeError("localization geometry helpers are unavailable")
        self._warm_up_latency_ms = (monotonic_ns() - started_ns) / 1_000_000.0
        return self._warm_up_latency_ms

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


_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True, slots=True)
class ObjectPoseRequest:
    request_id: str
    frame: Any
    camera_info: Any
    depth_message: Any
    query: DetectionQuery
    confidence_threshold: float
    run_directory: Path
    cold_start_latency_ms: float

    def __post_init__(self) -> None:
        from so101_demo.core.detection import DetectionFrame

        if _REQUEST_ID.fullmatch(self.request_id) is None:
            raise ValueError("request_id must be path-safe")
        if not isinstance(self.frame, DetectionFrame):
            raise ValueError("frame must be a DetectionFrame")
        if not math.isfinite(self.confidence_threshold) or not (
            0.0 <= self.confidence_threshold <= 1.0
        ):
            raise ValueError("confidence_threshold must be finite and in [0, 1]")
        if not self.run_directory.is_absolute():
            raise ValueError("run_directory must be absolute")
        if not math.isfinite(self.cold_start_latency_ms) or self.cold_start_latency_ms < 0.0:
            raise ValueError("cold_start_latency_ms must be finite and nonnegative")


@dataclass(frozen=True, slots=True)
class ObjectPoseResult:
    status: str
    failure: str | None
    request_id: str
    source_stamp_ns: int
    source_frame_id: str
    model_id: str | None
    weights_sha256: str | None
    runtime_device: str | None
    cold_start_latency_ms: float
    inference_latency_ms: float | None
    request_latency_ms: float
    candidate_count: int
    matching_candidate_count: int
    published_cup_pose: bool
    artifact_paths: tuple[str, ...]
    center_world_xyz: tuple[float, float, float] | None = None

    def to_document(self) -> dict[str, object]:
        return {
            "status": self.status,
            "failure": self.failure,
            "request_id": self.request_id,
            "source_stamp_ns": self.source_stamp_ns,
            "source_frame_id": self.source_frame_id,
            "model_id": self.model_id,
            "weights_sha256": self.weights_sha256,
            "runtime_device": self.runtime_device,
            "cold_start_latency_ms": self.cold_start_latency_ms,
            "inference_latency_ms": self.inference_latency_ms,
            "request_latency_ms": self.request_latency_ms,
            "candidate_count": self.candidate_count,
            "matching_candidate_count": self.matching_candidate_count,
            "published_cup_pose": self.published_cup_pose,
            "artifact_paths": list(self.artifact_paths),
            "center_world_xyz": (
                None if self.center_world_xyz is None else list(self.center_world_xyz)
            ),
        }


def _matching_count(
    batch: DetectionBatch,
    query: DetectionQuery,
    confidence_threshold: float,
) -> int:
    return sum(
        candidate.class_id == query.class_id
        and candidate.confidence >= confidence_threshold
        for candidate in batch.candidates
    )


def _result(
    request: ObjectPoseRequest,
    *,
    start_ns: int,
    monotonic_ns: Callable[[], int],
    status: str,
    failure: str | None,
    batch: DetectionBatch | None,
    matching_candidate_count: int,
    published_cup_pose: bool,
    artifact_paths: tuple[str, ...],
    localized: LocalizedObject | None = None,
) -> ObjectPoseResult:
    return ObjectPoseResult(
        status=status,
        failure=failure,
        request_id=request.request_id,
        source_stamp_ns=request.frame.source_stamp_ns,
        source_frame_id=request.frame.source_frame_id,
        model_id=None if batch is None else batch.model_id,
        weights_sha256=None if batch is None else batch.weights_sha256,
        runtime_device=None if batch is None else batch.runtime_device,
        cold_start_latency_ms=request.cold_start_latency_ms,
        inference_latency_ms=None if batch is None else batch.inference_latency_ms,
        request_latency_ms=(monotonic_ns() - start_ns) / 1_000_000.0,
        candidate_count=0 if batch is None else len(batch.candidates),
        matching_candidate_count=matching_candidate_count,
        published_cup_pose=published_cup_pose,
        artifact_paths=artifact_paths,
        center_world_xyz=(
            None if localized is None else localized.center_world_xyz
        ),
    )


def detect_once(
    *,
    request: ObjectPoseRequest,
    detector: Any,
    selector: TargetSelector,
    localizer: Any,
    evidence_writer: Any,
    pose_publisher: Callable[[LocalizedObject], None],
    lookup_transform: Callable[[str, str, int], Any],
    detection_publisher: Callable[[DetectionBatch, np.ndarray], None] | None = None,
    event_emitter: EventEmitter | None = None,
    monotonic_ns: Callable[[], int] = time.monotonic_ns,
) -> ObjectPoseResult:
    start_ns = monotonic_ns()
    batch: DetectionBatch | None = None
    artifacts: tuple[str, ...] = ()
    matching_count = 0

    def finish(
        failure: str,
        *,
        localized: LocalizedObject | None = None,
    ) -> ObjectPoseResult:
        result = _result(
            request,
            start_ns=start_ns,
            monotonic_ns=monotonic_ns,
            status="ERROR",
            failure=failure,
            batch=batch,
            matching_candidate_count=matching_count,
            published_cup_pose=False,
            artifact_paths=artifacts,
            localized=localized,
        )
        try:
            result_path = evidence_writer.write_result(request, result)
        except (OSError, ValueError):
            if failure == "EVIDENCE_WRITE_FAILED":
                completed = result
            else:
                completed = replace(result, failure="EVIDENCE_WRITE_FAILED")
        else:
            completed = replace(result, artifact_paths=(*artifacts, result_path))
        if event_emitter is not None:
            event_emitter.emit(
                "PERCEPTION_FAILED",
                payload={},
                failure_code=normalize_failure_code(
                    "PERCEPTION_FAILED", completed.failure
                ),
            )
        return completed

    try:
        batch = detector.detect(request.frame, request.query)
    except Exception:
        return finish("INFERENCE_FAILED")
    matching_count = _matching_count(
        batch,
        request.query,
        request.confidence_threshold,
    )
    try:
        artifacts = evidence_writer.write_detection(request, batch)
    except (OSError, ValueError):
        return finish("EVIDENCE_WRITE_FAILED")
    if detection_publisher is not None:
        from so101_demo.runtime.perception_evidence import render_detection_overlay

        try:
            detection_publisher(
                batch,
                render_detection_overlay(request.frame, batch),
            )
        except Exception:
            return finish("CLEANUP_FAILED")
    try:
        selected = selector.select(
            batch,
            request.query,
            request.confidence_threshold,
        )
    except TargetSelectionError as error:
        return finish(error.code)
    if event_emitter is not None:
        event_emitter.emit(
            "TARGET_SELECTED",
            payload={
                "target_id": selected.instance_id,
                "class_name": selected.class_id,
            },
        )
    try:
        selected_path = evidence_writer.write_selected(request, selected)
    except (OSError, ValueError):
        return finish("EVIDENCE_WRITE_FAILED")
    artifacts = (*artifacts, selected_path)
    try:
        localized = localizer.localize(
            selected,
            request.camera_info,
            request.depth_message,
            lookup_transform,
        )
    except LocalizationError as error:
        return finish(error.code)
    try:
        cloud_path = evidence_writer.write_localized(request, localized)
    except (OSError, ValueError):
        return finish("EVIDENCE_WRITE_FAILED", localized=localized)
    artifacts = (*artifacts, cloud_path)
    staged = _result(
        request,
        start_ns=start_ns,
        monotonic_ns=monotonic_ns,
        status="OK",
        failure=None,
        batch=batch,
        matching_candidate_count=matching_count,
        published_cup_pose=False,
        artifact_paths=artifacts,
        localized=localized,
    )
    try:
        result_path = evidence_writer.write_result(request, staged)
    except (OSError, ValueError):
        return finish("EVIDENCE_WRITE_FAILED", localized=localized)
    artifacts = (*artifacts, result_path)
    try:
        pose_publisher(localized)
    except Exception:
        return finish("CLEANUP_FAILED", localized=localized)
    completed = replace(
        staged,
        published_cup_pose=True,
        artifact_paths=artifacts,
    )
    try:
        evidence_writer.write_result(request, completed)
    except (OSError, ValueError):
        failed = replace(completed, status="ERROR", failure="EVIDENCE_WRITE_FAILED")
        if event_emitter is not None:
            event_emitter.emit(
                "PERCEPTION_FAILED",
                payload={},
                failure_code="EVIDENCE_WRITE_FAILED",
            )
        return failed
    if event_emitter is not None:
        event_emitter.emit(
            "CUP_POSE_PUBLISHED",
            payload={
                "source_stamp_ns": request.frame.source_stamp_ns,
                "frame_id": "world",
            },
        )
    return completed
