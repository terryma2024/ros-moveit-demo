"""Shared perception arguments and process construction for MuJoCo launches."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from pathlib import Path
import os
import platform
import re

from launch.actions import DeclareLaunchArgument
from launch.actions import ExecuteProcess
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node

DEFAULT_YOLO_INFERENCE_IMAGE = (
    "so101-yolo11n-seg-inference:"
    "ros-jazzy-torch2.13.0-cu130-ultralytics8.4.115"
)
GROUNDED_SAM_THRESHOLD_DEFAULTS = (
    ("grounding_box_threshold", "0.35"),
    ("grounding_text_threshold", "0.25"),
    ("grounding_duplicate_iou", "0.85"),
    ("grounding_max_candidates", "16"),
    ("sam_mask_quality_threshold", "0.75"),
    ("sam_min_mask_pixels", "64"),
    ("sam_max_mask_area_ratio", "0.50"),
)


@dataclass(frozen=True, slots=True)
class PerceptionLaunchOptions:
    backend: str
    startup_timeout_s: str
    weights_path: Path | None
    weights_sha256: str | None
    model_root: Path | None
    model_manifest_sha256: str | None
    device: str
    allow_cpu_fallback: bool
    runtime: str
    container_image: str
    source_root: Path | None
    grounded_thresholds: tuple[str, ...] | None


def declare_perception_arguments(*, default_backend: str) -> list[DeclareLaunchArgument]:
    """Declare perception arguments while leaving the backend default to the caller."""

    if default_backend not in {"color_geometry", "yolo_seg", "grounded_sam"}:
        raise ValueError(f"unsupported default perception backend: {default_backend}")
    return [
        DeclareLaunchArgument(
            "perception_backend",
            default_value=default_backend,
            choices=("color_geometry", "yolo_seg", "grounded_sam"),
        ),
        DeclareLaunchArgument("perception_weights", default_value=""),
        DeclareLaunchArgument("perception_weights_sha256", default_value=""),
        DeclareLaunchArgument("perception_model_root", default_value=""),
        DeclareLaunchArgument("perception_model_manifest_sha256", default_value=""),
        DeclareLaunchArgument(
            "perception_device",
            default_value="auto",
            choices=("auto", "cuda", "mps", "cpu"),
        ),
        DeclareLaunchArgument(
            "perception_allow_cpu_fallback",
            default_value="false",
            choices=("true", "false"),
        ),
        DeclareLaunchArgument(
            "perception_runtime",
            default_value="auto",
            choices=("auto", "host", "docker", "docker_dev"),
        ),
        DeclareLaunchArgument(
            "perception_container_image",
            default_value=DEFAULT_YOLO_INFERENCE_IMAGE,
        ),
        DeclareLaunchArgument("perception_source_root", default_value=""),
        *(
            DeclareLaunchArgument(name, default_value=default)
            for name, default in GROUNDED_SAM_THRESHOLD_DEFAULTS
        ),
    ]


def _value(context, name: str) -> str:
    return LaunchConfiguration(name).perform(context)


def _positive_finite_value(context, name: str) -> str:
    value = _value(context, name)
    try:
        parsed = float(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be finite and positive") from error
    if not isfinite(parsed) or parsed <= 0.0:
        raise RuntimeError(f"{name} must be finite and positive")
    return value


def _grounded_threshold_values(context) -> tuple[str, ...]:
    values: list[str] = []
    for name, default in GROUNDED_SAM_THRESHOLD_DEFAULTS:
        value = _value(context, name) or default
        if name in {"grounding_max_candidates", "sam_min_mask_pixels"}:
            try:
                parsed = int(value)
            except ValueError as error:
                raise RuntimeError(f"{name} must be a positive integer") from error
            if str(parsed) != value or parsed <= 0:
                raise RuntimeError(f"{name} must be a positive integer")
        else:
            try:
                parsed = float(value)
            except ValueError as error:
                raise RuntimeError(f"{name} must be a finite probability") from error
            if not isfinite(parsed) or not 0.0 <= parsed <= 1.0:
                raise RuntimeError(f"{name} must be a finite probability")
            if name == "sam_max_mask_area_ratio" and parsed <= 0.0:
                raise RuntimeError(f"{name} must be greater than zero")
        values.append(value)
    return tuple(values)


def _reject_values(context, names: tuple[str, ...]) -> None:
    for name in names:
        if _value(context, name):
            raise RuntimeError(f"{name} is only valid for its matching perception backend")


def _reject_nondefault_thresholds(context) -> None:
    for name, default in GROUNDED_SAM_THRESHOLD_DEFAULTS:
        if _value(context, name) != default:
            raise RuntimeError(f"{name} is only valid for the grounded_sam perception backend")


def parse_perception_options(context) -> PerceptionLaunchOptions:
    """Validate and resolve the shared perception launch arguments."""

    startup_timeout_s = _positive_finite_value(context, "perception_startup_timeout_s")
    backend = _value(context, "perception_backend")
    if backend not in {"color_geometry", "yolo_seg", "grounded_sam"}:
        raise RuntimeError("perception_backend must be color_geometry, yolo_seg, or grounded_sam")

    device = _value(context, "perception_device")
    if device not in {"auto", "cuda", "mps", "cpu"}:
        raise RuntimeError("perception_device must be auto, cuda, mps, or cpu")
    runtime = _value(context, "perception_runtime")
    if runtime not in {"auto", "host", "docker", "docker_dev"}:
        raise RuntimeError("perception_runtime must be auto, host, docker, or docker_dev")

    host_platform = platform.system()
    if runtime == "auto":
        if host_platform == "Darwin":
            runtime = "host"
            if device == "auto":
                device = "mps"
        elif host_platform == "Linux":
            runtime = "docker"
        else:
            raise RuntimeError(
                f"perception_runtime auto does not support platform {host_platform}"
            )
    if runtime in {"docker", "docker_dev"} and host_platform != "Linux":
        raise RuntimeError("YOLO inference Docker runtime is supported only on Linux")
    if runtime in {"docker", "docker_dev"} and device not in {"auto", "cuda"}:
        raise RuntimeError("YOLO inference Docker runtime requires CUDA")

    container_image = _value(context, "perception_container_image")
    if not container_image or any(character.isspace() for character in container_image):
        raise RuntimeError("perception_container_image must be a non-empty image reference")

    source_root_value = _value(context, "perception_source_root")
    source_root: Path | None = None
    if runtime == "docker_dev":
        candidate = Path(source_root_value)
        if (
            not candidate.is_absolute()
            or candidate.is_symlink()
            or not candidate.is_dir()
            or not (candidate / "__init__.py").is_file()
            or not (candidate / "runtime").is_dir()
            or "," in source_root_value
        ):
            raise RuntimeError(
                "perception_source_root must be an absolute, non-symlink Python "
                "source directory for so101_demo"
            )
        source_root = candidate.resolve(strict=True)
    elif source_root_value:
        raise RuntimeError(
            "perception_source_root is accepted only with perception_runtime=docker_dev"
        )

    allow_cpu_fallback_value = _value(context, "perception_allow_cpu_fallback")
    if allow_cpu_fallback_value not in {"true", "false"}:
        raise RuntimeError("perception_allow_cpu_fallback must be true or false")

    weights_path: Path | None = None
    weights_sha256: str | None = None
    model_root: Path | None = None
    model_manifest_sha256: str | None = None
    grounded_thresholds: tuple[str, ...] | None = None
    if backend == "color_geometry":
        _reject_values(
            context,
            (
                "perception_weights",
                "perception_weights_sha256",
                "perception_model_root",
                "perception_model_manifest_sha256",
            ),
        )
        _reject_nondefault_thresholds(context)
    elif backend == "yolo_seg":
        _reject_values(
            context,
            ("perception_model_root", "perception_model_manifest_sha256"),
        )
        _reject_nondefault_thresholds(context)
        weights_path = Path(_value(context, "perception_weights"))
        if (
            not weights_path.is_absolute()
            or weights_path.is_symlink()
            or not weights_path.is_file()
        ):
            raise RuntimeError("perception_weights must be an existing absolute file")
        weights_sha256 = _value(context, "perception_weights_sha256")
        if re.fullmatch(r"[0-9a-f]{64}", weights_sha256) is None:
            raise RuntimeError(
                "perception_weights_sha256 must be a lowercase SHA256 digest"
            )
    else:
        _reject_values(context, ("perception_weights", "perception_weights_sha256"))
        model_root = Path(_value(context, "perception_model_root"))
        if (
            not model_root.is_absolute()
            or model_root.is_symlink()
            or not model_root.is_dir()
        ):
            raise RuntimeError(
                "perception_model_root must be an existing absolute non-symlink directory"
            )
        model_manifest_sha256 = _value(context, "perception_model_manifest_sha256")
        if re.fullmatch(r"[0-9a-f]{64}", model_manifest_sha256) is None:
            raise RuntimeError(
                "perception_model_manifest_sha256 must be a lowercase SHA256 digest"
            )
        grounded_thresholds = _grounded_threshold_values(context)

    return PerceptionLaunchOptions(
        backend=backend,
        startup_timeout_s=startup_timeout_s,
        weights_path=weights_path,
        weights_sha256=weights_sha256,
        model_root=model_root,
        model_manifest_sha256=model_manifest_sha256,
        device=device,
        allow_cpu_fallback=allow_cpu_fallback_value == "true",
        runtime=runtime,
        container_image=container_image,
        source_root=source_root,
        grounded_thresholds=grounded_thresholds,
    )


def build_perception_action(
    options: PerceptionLaunchOptions,
    *,
    evidence_root: Path,
    request_id: str,
    workflow_id: str | None = None,
    child_arguments: tuple[str, ...] = (),
    profiling_root: Path | None = None,
) -> ExecuteProcess:
    """Construct one perception process from validated shared options."""

    workflow_arguments = (
        ("--emit-workflow-events", "--workflow-id", workflow_id)
        if workflow_id is not None
        else ()
    )
    if options.backend == "color_geometry":
        return Node(
            package="so101_demo_py",
            executable="rgbd_cup_pose",
            arguments=[
                "--startup-timeout-s",
                options.startup_timeout_s,
                "--output-topic",
                "/cup_pose",
                "--output-ply",
                str(evidence_root / "cup.ply"),
                "--evidence-json",
                str(evidence_root / "summary.json"),
                *workflow_arguments,
                *child_arguments,
            ],
            parameters=[{"use_sim_time": True}],
            output="both",
        )
    if options.backend == "grounded_sam":
        if (
            options.model_root is None
            or options.model_manifest_sha256 is None
            or options.grounded_thresholds is None
        ):
            raise RuntimeError("validated Grounded SAM perception artifacts are missing")
        grounded_arguments = [
            "--startup-timeout-s",
            options.startup_timeout_s,
            "--output-topic",
            "/cup_pose",
            "--detections-topic",
            "/perception/detections",
            "--overlay-topic",
            "/perception/overlay",
            "--backend",
            "grounded_sam",
            "--model-root",
            str(options.model_root),
            "--model-manifest-sha256",
            options.model_manifest_sha256,
            "--device",
            options.device,
            "--grounding-box-threshold",
            options.grounded_thresholds[0],
            "--grounding-text-threshold",
            options.grounded_thresholds[1],
            "--duplicate-iou",
            options.grounded_thresholds[2],
            "--max-candidates",
            options.grounded_thresholds[3],
            "--sam-quality-threshold",
            options.grounded_thresholds[4],
            "--min-mask-pixels",
            options.grounded_thresholds[5],
            "--max-mask-area-ratio",
            options.grounded_thresholds[6],
            "--request-id",
            request_id,
            "--evidence-root",
            str(evidence_root),
            "--require-output-subscriber",
            *workflow_arguments,
            *child_arguments,
        ]
        if options.allow_cpu_fallback:
            grounded_arguments.append("--allow-cpu-fallback")
        return Node(
            package="so101_demo_py",
            executable="rgbd_object_pose",
            arguments=grounded_arguments,
            parameters=[{"use_sim_time": True}],
            output="both",
        )
    if options.backend != "yolo_seg":
        raise RuntimeError(f"unsupported perception backend: {options.backend}")
    if options.weights_path is None or options.weights_sha256 is None:
        raise RuntimeError("validated YOLO perception weights are missing")

    arguments = [
        "--startup-timeout-s",
        options.startup_timeout_s,
        "--output-topic",
        "/cup_pose",
        "--detections-topic",
        "/perception/detections",
        "--overlay-topic",
        "/perception/overlay",
        "--weights",
        str(options.weights_path),
        "--weights-sha256",
        options.weights_sha256,
        "--device",
        options.device,
        "--request-id",
        request_id,
        "--evidence-root",
        str(evidence_root),
        "--require-output-subscriber",
        *workflow_arguments,
        *child_arguments,
    ]
    if options.allow_cpu_fallback:
        arguments.append("--allow-cpu-fallback")
    if options.runtime not in {"docker", "docker_dev"}:
        return Node(
            package="so101_demo_py",
            executable="rgbd_object_pose",
            arguments=arguments,
            parameters=[{"use_sim_time": True}],
            output="both",
        )

    container_arguments = list(arguments)
    container_arguments[container_arguments.index(str(options.weights_path))] = (
        "/models/best.pt"
    )
    container_arguments[container_arguments.index(str(evidence_root))] = "/evidence"
    if profiling_root is not None:
        container_arguments[container_arguments.index(str(profiling_root))] = "/profiling"
    device_index = container_arguments.index("--device") + 1
    container_arguments[device_index] = "cuda"
    container_command = [
        "docker",
        "run",
        "--rm",
        "--name",
        f"so101-yolo-seg-{request_id}",
        "--gpus",
        "all",
        "--network",
        "host",
        "--ipc",
        "host",
        "--user",
        f"{os.geteuid()}:{os.getegid()}",
        "--env",
        f"ROS_DOMAIN_ID={os.environ.get('ROS_DOMAIN_ID', '0')}",
        "--env",
        "RMW_IMPLEMENTATION="
        + os.environ.get("RMW_IMPLEMENTATION", "rmw_fastrtps_cpp"),
        "--env",
        f"ROS_LOCALHOST_ONLY={os.environ.get('ROS_LOCALHOST_ONLY', '0')}",
        "--env",
        "HOME=/tmp/yolo-home",
        "--env",
        "YOLO_CONFIG_DIR=/opt/ultralytics",
        "--env",
        "TORCH_HOME=/opt/torch-cache",
    ]
    if options.runtime == "docker_dev":
        container_command.extend(
            [
                "--env",
                "PYTHONPATH=/workspace/so101-source",
                "--mount",
                "type=bind,"
                f"src={options.source_root},"
                "dst=/workspace/so101-source/so101_demo,readonly",
            ]
        )
    container_command.extend(
        [
            "--mount",
            f"type=bind,src={options.weights_path},dst=/models/best.pt,readonly",
            "--mount",
            f"type=bind,src={evidence_root},dst=/evidence",
            *(
                [
                    "--mount",
                    f"type=bind,src={profiling_root},dst=/profiling",
                ]
                if profiling_root is not None
                else []
            ),
            options.container_image,
            *container_arguments,
        ]
    )
    return ExecuteProcess(cmd=container_command, output="both")
