"""ROS adapter for one fresh YOLO-Seg RGB-D localization request."""

from __future__ import annotations

import json
import math
import re
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from so101_demo.application.object_pose import (
    ObjectPoseRequest,
    RgbdLocalizer,
    TargetSelector,
    detect_once,
)
from so101_demo.cli.rgbd_point_cloud import (
    AlignedRgbdBuffer,
    _decode_rgb,
    message_stamp_ns,
)
from so101_demo.core.detection import (
    DetectionBatch,
    DetectionFrame,
    DetectionQuery,
    LocalizedObject,
)
from so101_demo.adapters.perception.detector_factory import (
    DetectorFactoryOptions,
    build_detector,
)
from so101_demo.adapters.perception.grounded_sam_postprocess import GroundedSamThresholds
from so101_demo.adapters.perception.model_runtime import ModelSetupError
from so101_demo.runtime.perception_evidence import PerceptionEvidenceWriter

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_REQUEST_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _validate_topic(name: str, value: str) -> None:
    if not value.startswith("/") or value == "/" or "//" in value:
        raise ValueError(f"{name} must be a non-empty absolute ROS topic")
    if any(character.isspace() for character in value):
        raise ValueError(f"{name} must be a non-empty absolute ROS topic")


@dataclass(frozen=True, slots=True)
class RgbdObjectPoseOptions:
    request_id: str
    evidence_root: Path
    backend: str = "yolo_seg"
    weights_path: Path | None = None
    weights_sha256: str | None = None
    model_root: Path | None = None
    model_manifest_sha256: str | None = None
    device: str = "auto"
    allow_cpu_fallback: bool = False
    model_id: str | None = None
    imgsz: int | None = None
    grounding_box_threshold: float | None = None
    grounding_text_threshold: float | None = None
    duplicate_iou: float | None = None
    max_candidates: int | None = None
    sam_quality_threshold: float | None = None
    min_mask_pixels: int | None = None
    max_mask_area_ratio: float | None = None
    once: bool = False
    startup_timeout_s: float = 30.0
    tf_timeout_s: float = 0.2
    confidence_threshold: float = 0.50
    depth_trunc_m: float = 3.0
    minimum_cup_points: int = 50
    cluster_eps_m: float = 0.015
    cluster_min_points: int = 5
    table_top_z: float = 0.12
    cup_height: float = 0.09
    expected_radius: float = 0.04
    radius_tolerance: float = 0.01
    camera_info_topic: str = "/task_camera/camera_info"
    color_topic: str = "/task_camera/color"
    depth_topic: str = "/task_camera/depth"
    detections_topic: str = "/perception/detections"
    overlay_topic: str = "/perception/overlay"
    output_topic: str = "/cup_pose"

    def __post_init__(self) -> None:
        if self.backend not in {"yolo_seg", "grounded_sam"}:
            raise ValueError("backend must be yolo_seg or grounded_sam")
        if self.device not in {"auto", "cuda", "mps", "cpu"}:
            raise ValueError("device must be auto, cuda, mps, or cpu")
        if self.backend == "yolo_seg":
            if (
                self.model_root is not None
                or self.model_manifest_sha256 is not None
                or any(
                    value is not None
                    for value in (
                        self.grounding_box_threshold,
                        self.grounding_text_threshold,
                        self.duplicate_iou,
                        self.max_candidates,
                        self.sam_quality_threshold,
                        self.min_mask_pixels,
                        self.max_mask_area_ratio,
                    )
                )
            ):
                raise ValueError("backend configuration mixes YOLO and Grounded SAM artifacts")
            if self.weights_path is None:
                raise ValueError("weights_path is required for yolo_seg")
            if self.weights_sha256 is None:
                raise ValueError("weights_sha256 is required for yolo_seg")
            if not self.weights_path.is_absolute():
                raise ValueError("weights_path must be absolute")
            if self.weights_path.is_symlink() or not self.weights_path.is_file():
                raise ValueError("weights_path must be a regular file")
            if _SHA256.fullmatch(self.weights_sha256) is None:
                raise ValueError("weights_sha256 must be a lowercase SHA256 digest")
            if self.model_id is not None and not self.model_id:
                raise ValueError("model_id must be non-empty")
            if self.imgsz is not None and self.imgsz <= 0:
                raise ValueError("imgsz must be positive")
        else:
            if (
                self.weights_path is not None
                or self.weights_sha256 is not None
                or self.model_id is not None
                or self.imgsz is not None
            ):
                raise ValueError("backend configuration mixes YOLO and Grounded SAM artifacts")
            if self.model_root is None:
                raise ValueError("model_root is required for grounded_sam")
            if self.model_manifest_sha256 is None:
                raise ValueError("model_manifest_sha256 is required for grounded_sam")
            if not self.model_root.is_absolute() or self.model_root.is_symlink():
                raise ValueError("model_root must be an absolute non-symlink path")
            if _SHA256.fullmatch(self.model_manifest_sha256) is None:
                raise ValueError("model_manifest_sha256 must be a lowercase SHA256 digest")
            self._grounded_thresholds()
        if _REQUEST_ID.fullmatch(self.request_id) is None:
            raise ValueError("request_id must be path-safe")
        if not self.evidence_root.is_absolute():
            raise ValueError("evidence_root must be absolute")
        if self.evidence_root.exists() and self.evidence_root.is_symlink():
            raise ValueError("evidence_root must not be a symlink")
        positive_values = (
            self.startup_timeout_s,
            self.tf_timeout_s,
            self.depth_trunc_m,
            self.cluster_eps_m,
            self.cup_height,
            self.expected_radius,
            self.radius_tolerance,
        )
        if any(not math.isfinite(value) or value <= 0.0 for value in positive_values):
            raise ValueError("timeouts and geometry distances must be finite and positive")
        if not math.isfinite(self.table_top_z):
            raise ValueError("table_top_z must be finite")
        if not math.isfinite(self.confidence_threshold) or not (
            0.0 <= self.confidence_threshold <= 1.0
        ):
            raise ValueError("confidence_threshold must be finite and in [0, 1]")
        if (
            (self.imgsz is not None and self.imgsz <= 0)
            or self.minimum_cup_points <= 0
            or self.cluster_min_points <= 0
        ):
            raise ValueError("image size and point counts must be positive")
        topics = {
            "camera_info_topic": self.camera_info_topic,
            "color_topic": self.color_topic,
            "depth_topic": self.depth_topic,
            "detections_topic": self.detections_topic,
            "overlay_topic": self.overlay_topic,
            "output_topic": self.output_topic,
        }
        for name, value in topics.items():
            _validate_topic(name, value)
        if len(set(topics.values())) != len(topics):
            raise ValueError("RGB-D perception topics must be distinct")

    def _grounded_thresholds(self) -> GroundedSamThresholds:
        defaults = GroundedSamThresholds.defaults()
        return GroundedSamThresholds(
            box_threshold=(
                defaults.box_threshold
                if self.grounding_box_threshold is None
                else self.grounding_box_threshold
            ),
            text_threshold=(
                defaults.text_threshold
                if self.grounding_text_threshold is None
                else self.grounding_text_threshold
            ),
            duplicate_iou=(
                defaults.duplicate_iou if self.duplicate_iou is None else self.duplicate_iou
            ),
            max_candidates=(
                defaults.max_candidates if self.max_candidates is None else self.max_candidates
            ),
            sam_quality=(
                defaults.sam_quality
                if self.sam_quality_threshold is None
                else self.sam_quality_threshold
            ),
            min_mask_pixels=(
                defaults.min_mask_pixels
                if self.min_mask_pixels is None
                else self.min_mask_pixels
            ),
            max_mask_area_ratio=(
                defaults.max_mask_area_ratio
                if self.max_mask_area_ratio is None
                else self.max_mask_area_ratio
            ),
        )

    def to_detector_factory_options(self) -> DetectorFactoryOptions:
        if self.backend == "yolo_seg":
            return DetectorFactoryOptions(
                backend="yolo_seg",
                requested_device=self.device,  # type: ignore[arg-type]
                allow_cpu_fallback=self.allow_cpu_fallback,
                yolo_weights_path=self.weights_path,
                yolo_weights_sha256=self.weights_sha256,
                yolo_model_id=self.model_id or "plastic-cup-yolo11n-seg-v1",
                yolo_imgsz=640 if self.imgsz is None else self.imgsz,
            )
        return DetectorFactoryOptions(
            backend="grounded_sam",
            requested_device=self.device,  # type: ignore[arg-type]
            allow_cpu_fallback=self.allow_cpu_fallback,
            grounded_model_root=self.model_root,
            grounded_manifest_sha256=self.model_manifest_sha256,
            grounded_thresholds=self._grounded_thresholds(),
        )


class FreshFrameGate:
    def __init__(self, minimum_source_stamp_ns: int) -> None:
        if minimum_source_stamp_ns < 0:
            raise ValueError("minimum_source_stamp_ns must be nonnegative")
        self._minimum = minimum_source_stamp_ns
        self._accepted: tuple[Any, Any, Any] | None = None

    def accept(self, aligned: tuple[Any, Any, Any]) -> tuple[Any, Any, Any] | None:
        if self._accepted is not None:
            return self._accepted
        stamps = tuple(message_stamp_ns(message) for message in aligned)
        if len(set(stamps)) != 1 or stamps[0] <= self._minimum:
            return None
        self._accepted = aligned
        return aligned


def _pose_message(localized: LocalizedObject, pose_type: type) -> Any:
    message = pose_type()
    message.header.frame_id = "world"
    message.header.stamp.sec = localized.source_stamp_ns // 1_000_000_000
    message.header.stamp.nanosec = localized.source_stamp_ns % 1_000_000_000
    message.pose.position.x, message.pose.position.y, message.pose.position.z = (
        localized.center_world_xyz
    )
    message.pose.orientation.w = 1.0
    return message


def _image_message(image: np.ndarray, header: Any, image_type: type) -> Any:
    message = image_type()
    message.header = header
    message.height, message.width = image.shape[:2]
    message.encoding = "rgb8"
    message.is_bigendian = False
    message.step = int(message.width) * 3
    message.data = image.tobytes()
    return message


def _detection_message(
    batch: DetectionBatch,
    header: Any,
    array_type: type,
    detection_type: type,
    hypothesis_type: type,
) -> Any:
    array = array_type()
    array.header = header
    for candidate in batch.candidates:
        detection = detection_type()
        detection.header = header
        x_min, y_min, x_max, y_max = candidate.bbox_xyxy
        center = detection.bbox.center
        if hasattr(center, "position"):
            center.position.x = (x_min + x_max) / 2.0
            center.position.y = (y_min + y_max) / 2.0
        else:
            center.x = (x_min + x_max) / 2.0
            center.y = (y_min + y_max) / 2.0
        detection.bbox.size_x = x_max - x_min
        detection.bbox.size_y = y_max - y_min
        hypothesis = hypothesis_type()
        hypothesis.hypothesis.class_id = candidate.class_id
        hypothesis.hypothesis.score = candidate.confidence
        detection.results.append(hypothesis)
        detection.id = candidate.instance_id
        array.detections.append(detection)
    return array


def _wait_for_output_subscribers(
    publishers: tuple[Any, ...],
    *,
    spin_once: Callable[[float], None],
    timeout_s: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    if not math.isfinite(timeout_s) or timeout_s <= 0.0:
        raise ValueError("output subscriber timeout must be finite and positive")
    deadline = monotonic() + timeout_s
    while True:
        if all(publisher.get_subscription_count() > 0 for publisher in publishers):
            return True
        remaining = deadline - monotonic()
        if remaining <= 0.0:
            return False
        spin_once(min(0.05, remaining))


def _wait_for_transform(
    can_transform: Callable[[str, str, int], bool],
    *,
    target_frame: str,
    source_frame: str,
    source_stamp_ns: int,
    spin_once: Callable[[float], None],
    timeout_s: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> bool:
    if not math.isfinite(timeout_s) or timeout_s <= 0.0:
        raise ValueError("transform readiness timeout must be finite and positive")
    if source_stamp_ns <= 0:
        raise ValueError("transform source stamp must be positive")
    deadline = monotonic() + timeout_s
    while True:
        if can_transform(target_frame, source_frame, source_stamp_ns):
            return True
        remaining = deadline - monotonic()
        if remaining <= 0.0:
            return False
        spin_once(min(0.05, remaining))


def _wait_for_positive_clock(
    *,
    now_ns: Callable[[], int],
    spin_once: Callable[[float], None],
    timeout_s: float,
    monotonic: Callable[[], float] = time.monotonic,
) -> int | None:
    """Return a nonzero simulation-time watermark or fail closed at timeout."""

    if not math.isfinite(timeout_s) or timeout_s <= 0.0:
        raise ValueError("simulation clock timeout must be finite and positive")
    deadline = monotonic() + timeout_s
    while True:
        current_ns = int(now_ns())
        if current_ns > 0:
            return current_ns
        remaining = deadline - monotonic()
        if remaining <= 0.0:
            return None
        spin_once(min(0.05, remaining))


def _publish_and_confirm(publisher: Any, message: Any, *, ack_timeout: Any) -> None:
    publisher.publish(message)
    if (
        publisher.get_subscription_count() > 0
        and not publisher.wait_for_all_acked(ack_timeout)
    ):
        raise RuntimeError("perception output publication was not acknowledged")


def run_rgbd_object_pose(options: RgbdObjectPoseOptions) -> int:
    try:
        built = build_detector(options.to_detector_factory_options())
        detector = built.detector
        localizer = RgbdLocalizer(
            depth_trunc_m=options.depth_trunc_m,
            minimum_cup_points=options.minimum_cup_points,
            cluster_eps_m=options.cluster_eps_m,
            cluster_min_points=options.cluster_min_points,
            table_top_z=options.table_top_z,
            cup_height=options.cup_height,
            expected_radius_m=options.expected_radius,
            radius_tolerance_m=options.radius_tolerance,
        )
        localization_warm_up_ms = localizer.warm_up()
        evidence_writer = PerceptionEvidenceWriter()
        evidence_writer.write_model_provenance(
            options.evidence_root, built.provenance_document
        )
    except (ImportError, ModelSetupError, RuntimeError, ValueError, OSError) as error:
        print(json.dumps({"status": "ERROR", "failure": str(error)}, sort_keys=True))
        return 1

    import rclpy
    from geometry_msgs.msg import PoseStamped
    from rclpy.duration import Duration
    from rclpy.parameter import Parameter
    from rclpy.time import Time
    from sensor_msgs.msg import CameraInfo, Image
    from tf2_ros import Buffer, TransformException, TransformListener
    from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose

    initialized_here = not rclpy.ok()
    node = None
    listener = None
    subscriptions: list[Any] = []
    publishers: list[Any] = []
    result_code = 1
    cleanup_failed = False
    if initialized_here:
        rclpy.init()
    try:
        node = rclpy.create_node(
            "rgbd_object_pose",
            parameter_overrides=[Parameter("use_sim_time", value=True)],
        )
        source_watermark_ns = _wait_for_positive_clock(
            now_ns=lambda: int(node.get_clock().now().nanoseconds),
            spin_once=lambda timeout_s: rclpy.spin_once(
                node, timeout_sec=timeout_s
            ),
            timeout_s=options.startup_timeout_s,
        )
        if source_watermark_ns is None:
            print(
                json.dumps(
                    {"status": "ERROR", "failure": "SIM_CLOCK_UNAVAILABLE"},
                    sort_keys=True,
                )
            )
            return 1
        detections_publisher = node.create_publisher(
            Detection2DArray, options.detections_topic, 10
        )
        overlay_publisher = node.create_publisher(Image, options.overlay_topic, 10)
        pose_publisher = node.create_publisher(PoseStamped, options.output_topic, 10)
        publishers = [detections_publisher, overlay_publisher, pose_publisher]
        tf_buffer = Buffer()
        listener = TransformListener(tf_buffer, node)
        buffer = AlignedRgbdBuffer()
        gate = FreshFrameGate(source_watermark_ns)
        aligned: tuple[Any, Any, Any] | None = None

        def accept(value: tuple[Any, Any, Any] | None) -> None:
            nonlocal aligned
            if value is not None:
                aligned = gate.accept(value) or aligned

        subscriptions = [
            node.create_subscription(
                CameraInfo,
                options.camera_info_topic,
                lambda message: accept(buffer.add_camera_info(message)),
                10,
            ),
            node.create_subscription(
                Image,
                options.color_topic,
                lambda message: accept(buffer.add_color(message)),
                10,
            ),
            node.create_subscription(
                Image,
                options.depth_topic,
                lambda message: accept(buffer.add_depth(message)),
                10,
            ),
        ]
        node.get_logger().info(
            f"status=READY request_id={options.request_id} "
            f"runtime_device={detector.runtime_device}"
        )
        deadline = time.monotonic() + options.startup_timeout_s
        while aligned is None and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
        if aligned is None:
            print(json.dumps({"status": "ERROR", "failure": "RGBD_TIMEOUT"}, sort_keys=True))
            return 1
        camera_info, color_message, depth_message = aligned
        frame = DetectionFrame(
            _decode_rgb(color_message),
            message_stamp_ns(color_message),
            color_message.header.frame_id,
        )
        _wait_for_output_subscribers(
            (detections_publisher, overlay_publisher, pose_publisher),
            spin_once=lambda timeout_s: rclpy.spin_once(
                node, timeout_sec=timeout_s
            ),
            timeout_s=1.0,
        )
        if not _wait_for_transform(
            lambda target, source, stamp_ns: bool(
                tf_buffer.can_transform(
                    target,
                    source,
                    Time(nanoseconds=stamp_ns),
                    timeout=Duration(seconds=0.0),
                )
            ),
            target_frame="world",
            source_frame=frame.source_frame_id,
            source_stamp_ns=frame.source_stamp_ns,
            spin_once=lambda timeout_s: rclpy.spin_once(
                node, timeout_sec=timeout_s
            ),
            timeout_s=options.startup_timeout_s,
        ):
            print(
                json.dumps(
                    {"status": "ERROR", "failure": "TF_UNAVAILABLE"},
                    sort_keys=True,
                )
            )
            return 1

        def lookup(target: str, source: str, stamp_ns: int) -> Any:
            try:
                return tf_buffer.lookup_transform(
                    target,
                    source,
                    Time(nanoseconds=stamp_ns),
                    timeout=Duration(seconds=options.tf_timeout_s),
                )
            except TransformException as error:
                raise RuntimeError(str(error)) from error

        def publish_detections(batch: DetectionBatch, overlay: np.ndarray) -> None:
            ack_timeout = Duration(seconds=0.5)
            _publish_and_confirm(
                detections_publisher,
                _detection_message(
                    batch,
                    color_message.header,
                    Detection2DArray,
                    Detection2D,
                    ObjectHypothesisWithPose,
                ),
                ack_timeout=ack_timeout,
            )
            _publish_and_confirm(
                overlay_publisher,
                _image_message(overlay, color_message.header, Image),
                ack_timeout=ack_timeout,
            )

        result = detect_once(
            request=ObjectPoseRequest(
                request_id=options.request_id,
                frame=frame,
                camera_info=camera_info,
                depth_message=depth_message,
                query=DetectionQuery("plastic_cup"),
                confidence_threshold=options.confidence_threshold,
                run_directory=options.evidence_root,
                cold_start_latency_ms=(
                    built.cold_start_latency_ms + localization_warm_up_ms
                ),
            ),
            detector=detector,
            selector=TargetSelector(),
            localizer=localizer,
            evidence_writer=evidence_writer,
            pose_publisher=lambda localized: _publish_and_confirm(
                pose_publisher,
                _pose_message(localized, PoseStamped),
                ack_timeout=Duration(seconds=0.5),
            ),
            detection_publisher=publish_detections,
            lookup_transform=lookup,
        )
        print(json.dumps(result.to_document(), sort_keys=True))
        result_code = 0 if result.status == "OK" else 1
        if result_code == 0 and not options.once:
            while rclpy.ok():
                rclpy.spin_once(node, timeout_sec=0.2)
    except Exception as error:
        print(
            json.dumps(
                {"status": "ERROR", "failure": "INFERENCE_FAILED", "detail": str(error)},
                sort_keys=True,
            )
        )
        result_code = 1
    finally:
        if node is not None:
            for subscription in subscriptions:
                try:
                    node.destroy_subscription(subscription)
                except Exception:
                    cleanup_failed = True
            for publisher in publishers:
                try:
                    node.destroy_publisher(publisher)
                except Exception:
                    cleanup_failed = True
            if listener is not None and hasattr(listener, "unregister"):
                try:
                    listener.unregister()
                except Exception:
                    cleanup_failed = True
            try:
                node.destroy_node()
            except Exception:
                cleanup_failed = True
        if initialized_here and rclpy.ok():
            try:
                rclpy.try_shutdown()
            except Exception:
                cleanup_failed = True
    if cleanup_failed:
        print(json.dumps({"status": "ERROR", "failure": "CLEANUP_FAILED"}, sort_keys=True))
        return 1
    return result_code
