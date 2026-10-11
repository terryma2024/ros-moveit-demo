"""Node options, cup pose frames, the frame processor, subscription milestones and pose estimation."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import importlib
import json
import math
from pathlib import Path
from typing import Any, Protocol

from so101_demo.cli.rgbd_cup_pose import estimate_world_cup_pose
from so101_demo.cli.rgbd_point_cloud import (
    CupPointCloudResult,
    build_cup_point_cloud,
    message_stamp_ns,
)
from so101_demo.profiling.session import SemanticProfiler
from so101_demo.runtime.workflow_events import EventEmitter

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
        profiler: SemanticProfiler | None = None,
    ) -> None:
        self._estimate = estimate
        self._publish = publish
        self._on_error = on_error
        self._profiler = profiler
        self._wait_token = (
            profiler.start_span("perception.wait_synchronized_frame")
            if profiler is not None
            else None
        )

    def process(self, aligned: Any) -> bool:
        """Publish once for this valid frame, or report and skip an invalid frame."""
        self.finish_wait("available")
        estimate_token = (
            self._profiler.start_span("perception.estimate_cup_pose")
            if self._profiler is not None
            else None
        )
        try:
            frame = self._estimate(aligned)
        except (RuntimeError, TimeoutError, ValueError) as error:
            if estimate_token is not None:
                self._profiler.finish_span(
                    estimate_token,
                    outcome="rejected",
                    attributes={"reason_code": type(error).__name__},
                )
            self._on_error(error)
            return False
        if estimate_token is not None:
            self._profiler.finish_span(estimate_token, outcome="accepted")
        self._publish(frame)
        return True

    def finish_wait(self, outcome: str) -> None:
        """Finish the first-frame wait once without overriding its first outcome."""
        if self._wait_token is None:
            return
        self._profiler.finish_span(self._wait_token, outcome=outcome)
        self._wait_token = None


class RgbdSubscriptionMilestones:
    """Record first-sample DDS milestones only for an enabled profiler."""

    def __init__(self, profiler: SemanticProfiler, topics: tuple[str, ...]) -> None:
        self._profiler = profiler
        self._topic_count = len(topics)
        self._unmatched_topics = set(topics)
        self._topics_without_callback = set(topics)
        self._common_stamp_recorded = False
        self._matched_token = profiler.start_span(
            "perception.wait_all_subscriptions_matched"
        )
        self._callback_token = profiler.start_span(
            "perception.wait_all_first_callbacks"
        )
        self._common_stamp_token = profiler.start_span(
            "perception.wait_common_stamp"
        )

    def subscription_matched(self, topic: str, status: Any) -> None:
        if topic not in self._unmatched_topics:
            return
        current_count = int(getattr(status, "current_count", 0))
        if current_count <= 0:
            return
        self._unmatched_topics.remove(topic)
        self._profiler.instant(
            "perception.subscription_matched",
            {"topic": topic, "current_count": current_count},
        )
        if not self._unmatched_topics:
            self._profiler.finish_span(
                self._matched_token,
                outcome="available",
                attributes={"topic_count": self._topic_count},
            )
            self._matched_token = None

    def first_callback(self, topic: str, message: Any) -> None:
        if topic not in self._topics_without_callback:
            return
        self._topics_without_callback.remove(topic)
        self._profiler.instant(
            "perception.first_callback",
            {"topic": topic, "source_stamp_ns": message_stamp_ns(message)},
        )
        if not self._topics_without_callback:
            self._profiler.finish_span(
                self._callback_token,
                outcome="available",
                attributes={"topic_count": self._topic_count},
            )
            self._callback_token = None

    def common_stamp(self, stamp_ns: int) -> None:
        if self._common_stamp_recorded:
            return
        self._common_stamp_recorded = True
        self._profiler.instant(
            "perception.common_stamp", {"source_stamp_ns": stamp_ns}
        )
        self._profiler.finish_span(
            self._common_stamp_token,
            outcome="available",
            attributes={"source_stamp_ns": stamp_ns},
        )
        self._common_stamp_token = None

    def finish_pending(self, outcome: str) -> None:
        pending = (
            (self._matched_token, len(self._unmatched_topics)),
            (self._callback_token, len(self._topics_without_callback)),
            (self._common_stamp_token, int(not self._common_stamp_recorded)),
        )
        for token, pending_count in pending:
            if token is not None:
                self._profiler.finish_span(
                    token,
                    outcome=outcome,
                    attributes={"pending_count": pending_count},
                )
        self._matched_token = None
        self._callback_token = None
        self._common_stamp_token = None


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
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self._write_ply = write_ply
        self._write_json = write_json
        self._publish = publish
        self._write_rgb = write_rgb
        self._write_full_ply = write_full_ply
        self._write_preview = write_preview
        self._event_emitter = event_emitter
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
        if self.published_count == 1 and self._event_emitter is not None:
            self._event_emitter.emit(
                "CUP_POSE_PUBLISHED",
                payload={
                    "source_stamp_ns": frame.stamp_ns,
                    "frame_id": "world",
                },
            )


class _Runtime(Protocol):
    @property
    def first_valid_published(self) -> bool: ...

    def spin_once(self, timeout_s: float) -> None: ...

    def ok(self) -> bool: ...

    def finish_wait_span(self, outcome: str) -> None: ...

    def close(self) -> None: ...


def _finish_runtime_wait(
    runtime: _Runtime | None,
    profiler: SemanticProfiler | None,
    outcome: str,
) -> None:
    if runtime is None or profiler is None:
        return
    finish = getattr(runtime, "finish_wait_span", None)
    if callable(finish):
        finish(outcome)


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
    profiler: SemanticProfiler | None = None,
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
    transform_token = (
        profiler.start_span(
            "perception.transform_world",
            {"source_frame": cloud.frame_id, "target_frame": WORLD_FRAME},
        )
        if profiler is not None
        else None
    )
    try:
        timeout_s = tf_timeout_budget()
        if not math.isfinite(timeout_s) or timeout_s <= 0.0:
            raise TimeoutError("startup deadline expired before exact-stamp TF lookup")
        transform = lookup_transform(
            WORLD_FRAME,
            cloud.frame_id,
            stamp_to_time(camera_info.header.stamp),
            timeout_s,
        )
    except (RuntimeError, TimeoutError, ValueError) as error:
        if transform_token is not None:
            profiler.finish_span(
                transform_token,
                outcome="rejected",
                attributes={"reason_code": type(error).__name__},
            )
        raise
    if transform_token is not None:
        profiler.finish_span(transform_token, outcome="accepted")
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
