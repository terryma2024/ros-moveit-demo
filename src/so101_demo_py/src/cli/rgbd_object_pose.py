"""Run one YOLO-Seg RGB-D object-pose request."""

from __future__ import annotations

import argparse
from contextlib import redirect_stdout
import math
import re
import sys
import time
import uuid
from pathlib import Path


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


def _probability(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or not 0.0 <= parsed <= 1.0:
        raise argparse.ArgumentTypeError("must be finite and in [0, 1]")
    return parsed


def _absolute_path(value: str) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise argparse.ArgumentTypeError("must be an absolute path")
    return path


def _absolute_topic(value: str) -> str:
    if not value.startswith("/") or value == "/" or "//" in value:
        raise argparse.ArgumentTypeError("must be a non-empty absolute ROS topic")
    if any(character.isspace() for character in value):
        raise argparse.ArgumentTypeError("must be a non-empty absolute ROS topic")
    return value


def _application_arguments(arguments: list[str] | None) -> list[str]:
    raw_arguments = list(sys.argv[1:] if arguments is None else arguments)
    if "--ros-args" not in raw_arguments:
        return raw_arguments
    from rclpy.utilities import remove_ros_args

    return remove_ros_args(args=["rgbd_object_pose", *raw_arguments])[1:]


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rgbd_object_pose",
        description="Detect one plastic_cup instance and localize it from aligned RGB-D",
    )
    parser.add_argument("--backend", choices=("yolo_seg", "grounded_sam"), default="yolo_seg")
    parser.add_argument("--weights", type=_absolute_path)
    parser.add_argument("--weights-sha256")
    parser.add_argument("--model-root", type=_absolute_path)
    parser.add_argument("--model-manifest-sha256")
    parser.add_argument("--device", choices=("auto", "cuda", "mps", "cpu"), default="auto")
    parser.add_argument("--allow-cpu-fallback", action="store_true")
    parser.add_argument("--model-id")
    parser.add_argument("--imgsz", type=_positive_integer)
    parser.add_argument("--grounding-box-threshold", type=_probability)
    parser.add_argument("--grounding-text-threshold", type=_probability)
    parser.add_argument("--duplicate-iou", type=_probability)
    parser.add_argument("--max-candidates", type=_positive_integer)
    parser.add_argument("--sam-quality-threshold", type=_probability)
    parser.add_argument("--min-mask-pixels", type=_positive_integer)
    parser.add_argument("--max-mask-area-ratio", type=_probability)
    parser.add_argument("--request-id", default=f"request-{uuid.uuid4().hex}")
    parser.add_argument("--evidence-root", required=True, type=_absolute_path)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--startup-timeout-s", type=_positive_finite, default=30.0)
    parser.add_argument("--tf-timeout-s", type=_positive_finite, default=0.2)
    parser.add_argument("--confidence-threshold", type=_probability, default=0.50)
    parser.add_argument("--depth-trunc-m", type=_positive_finite, default=3.0)
    parser.add_argument("--minimum-cup-points", type=_positive_integer, default=50)
    parser.add_argument("--cluster-eps-m", type=_positive_finite, default=0.015)
    parser.add_argument("--cluster-min-points", type=_positive_integer, default=5)
    parser.add_argument("--table-top-z", type=float, default=0.12)
    parser.add_argument("--cup-height", type=_positive_finite, default=0.09)
    parser.add_argument("--expected-radius", type=_positive_finite, default=0.04)
    parser.add_argument("--radius-tolerance", type=_positive_finite, default=0.01)
    parser.add_argument(
        "--camera-info-topic",
        type=_absolute_topic,
        default="/task_camera/camera_info",
    )
    parser.add_argument("--color-topic", type=_absolute_topic, default="/task_camera/color")
    parser.add_argument("--depth-topic", type=_absolute_topic, default="/task_camera/depth")
    parser.add_argument(
        "--detections-topic",
        type=_absolute_topic,
        default="/perception/detections",
    )
    parser.add_argument(
        "--overlay-topic",
        type=_absolute_topic,
        default="/perception/overlay",
    )
    parser.add_argument("--output-topic", type=_absolute_topic, default="/cup_pose")
    parser.add_argument("--require-output-subscriber", action="store_true")
    parser.add_argument(
        "--profiling",
        choices=("off", "summary", "trace"),
        default="off",
    )
    parser.add_argument("--profiling-output-root", type=_absolute_path)
    parser.add_argument("--profiling-session-id")
    parser.add_argument("--emit-workflow-events", action="store_true")
    parser.add_argument("--workflow-id")
    parsed = parser.parse_args(_application_arguments(arguments))

    workflow_enabled = (
        parsed.emit_workflow_events
        and isinstance(parsed.workflow_id, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", parsed.workflow_id)
        is not None
    )
    if workflow_enabled != (
        parsed.emit_workflow_events or parsed.workflow_id is not None
    ):
        parser.error(
            "--emit-workflow-events and a safe --workflow-id must be provided together"
        )

    from so101_demo.ros.rgbd_object_pose_node import (
        RgbdObjectPoseOptions,
        run_rgbd_object_pose,
    )
    from so101_demo.runtime.workflow_events import EventEmitter

    event_emitter = (
        EventEmitter(
            parsed.workflow_id,
            "perception",
            sys.stdout.write,
            time.time_ns,
        )
        if workflow_enabled
        else None
    )

    def run(*, profiler=None) -> int:
        keyword_arguments = {}
        if profiler is not None:
            keyword_arguments["profiler"] = profiler
        if event_emitter is not None:
            keyword_arguments["event_emitter"] = event_emitter
        if event_emitter is None:
            return run_rgbd_object_pose(options, **keyword_arguments)
        with redirect_stdout(sys.stderr):
            return run_rgbd_object_pose(options, **keyword_arguments)

    try:
        options = RgbdObjectPoseOptions(
            backend=parsed.backend,
            weights_path=parsed.weights,
            weights_sha256=parsed.weights_sha256,
            model_root=parsed.model_root,
            model_manifest_sha256=parsed.model_manifest_sha256,
            device=parsed.device,
            allow_cpu_fallback=parsed.allow_cpu_fallback,
            model_id=parsed.model_id,
            imgsz=parsed.imgsz,
            grounding_box_threshold=parsed.grounding_box_threshold,
            grounding_text_threshold=parsed.grounding_text_threshold,
            duplicate_iou=parsed.duplicate_iou,
            max_candidates=parsed.max_candidates,
            sam_quality_threshold=parsed.sam_quality_threshold,
            min_mask_pixels=parsed.min_mask_pixels,
            max_mask_area_ratio=parsed.max_mask_area_ratio,
            request_id=parsed.request_id,
            evidence_root=parsed.evidence_root,
            once=parsed.once,
            startup_timeout_s=parsed.startup_timeout_s,
            tf_timeout_s=parsed.tf_timeout_s,
            confidence_threshold=parsed.confidence_threshold,
            depth_trunc_m=parsed.depth_trunc_m,
            minimum_cup_points=parsed.minimum_cup_points,
            cluster_eps_m=parsed.cluster_eps_m,
            cluster_min_points=parsed.cluster_min_points,
            table_top_z=parsed.table_top_z,
            cup_height=parsed.cup_height,
            expected_radius=parsed.expected_radius,
            radius_tolerance=parsed.radius_tolerance,
            camera_info_topic=parsed.camera_info_topic,
            color_topic=parsed.color_topic,
            depth_topic=parsed.depth_topic,
            detections_topic=parsed.detections_topic,
            overlay_topic=parsed.overlay_topic,
            output_topic=parsed.output_topic,
            require_output_subscriber=parsed.require_output_subscriber,
        )
    except ValueError as error:
        parser.error(str(error))
    if parsed.profiling == "off":
        return run()

    from so101_demo.profiling.model import ProfilingConfig, ProfilingMode
    from so101_demo.profiling.session import build_profiler

    if parsed.profiling_output_root is None:
        parser.error("enabled profiling requires --profiling-output-root")
    if not parsed.profiling_session_id or not parsed.profiling_session_id.strip():
        parser.error("enabled profiling requires --profiling-session-id")
    try:
        profiler = build_profiler(
            ProfilingConfig(
                mode=ProfilingMode.parse(parsed.profiling),
                output_root=parsed.profiling_output_root,
                session_id=parsed.profiling_session_id.strip(),
                process_role="perception",
                request_id=options.request_id,
            )
        )
    except OSError:
        return run()
    assert profiler is not None
    try:
        return run(profiler=profiler)
    finally:
        profiler.close()


if __name__ == "__main__":
    raise SystemExit(main())
