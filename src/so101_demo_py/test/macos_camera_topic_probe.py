#!/usr/bin/env python3
"""Phase-separated runtime acceptance probe for the MuJoCo task camera."""

from __future__ import annotations

import argparse
import json
import math
import os
import struct
import sys
import tempfile
import time
from collections import OrderedDict
from pathlib import Path
from typing import Callable, TypeVar

import rclpy
from rclpy.context import Context
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.signals import SignalHandlerOptions
from sensor_msgs.msg import CameraInfo, Image


MIN_COLOR_STAMPS = 30
MIN_ALIGNED_PHASE_SAMPLES = 3
MAX_RETAINED_ALIGNED_MESSAGES = 30


def stamp_ns(message: CameraInfo | Image) -> int:
    stamp = message.header.stamp
    return stamp.sec * 1_000_000_000 + stamp.nanosec


def _summarize_color_stamps(stamps: list[int], sample_count: int) -> dict:
    unique_stamps = sorted(set(stamps))
    if len(unique_stamps) < MIN_COLOR_STAMPS:
        raise RuntimeError(
            f"phase 1 requires {MIN_COLOR_STAMPS} unique color header stamps; "
            f"received {len(unique_stamps)}"
        )

    elapsed_s = (unique_stamps[-1] - unique_stamps[0]) / 1_000_000_000
    frequency_hz = 0.0
    if elapsed_s > 0.0:
        frequency_hz = (len(unique_stamps) - 1) / elapsed_s
    if frequency_hz <= 0.0:
        raise RuntimeError("color publication frequency was not observable")
    if not 8.0 <= frequency_hz <= 12.0:
        raise RuntimeError(f"unexpected color frequency: {frequency_hz}")

    return {
        "color_samples": sample_count,
        "unique_color_header_stamps": len(unique_stamps),
        "first_color_stamp_ns": unique_stamps[0],
        "last_color_stamp_ns": unique_stamps[-1],
        "color_frequency_hz": frequency_hz,
    }


def summarize_color_phase(colors: list[Image]) -> dict:
    """Validate phase 1 using only actual color-message header timestamps."""
    return _summarize_color_stamps([stamp_ns(message) for message in colors], len(colors))


MessageT = TypeVar("MessageT", CameraInfo, Image)


def _messages_by_stamp(messages: list[MessageT]) -> dict[int, MessageT]:
    return {stamp_ns(message): message for message in messages}


def summarize_aligned_phase(
    camera_infos: list[CameraInfo], colors: list[Image], depths: list[Image]
) -> dict:
    """Validate phase 2 from messages carrying one exact common timestamp."""
    counts = (len(camera_infos), len(colors), len(depths))
    if any(count < MIN_ALIGNED_PHASE_SAMPLES for count in counts):
        raise RuntimeError(
            "phase 2 requires at least 3 samples per topic: "
            f"camera_info={counts[0]} color={counts[1]} depth={counts[2]}"
        )

    infos_by_stamp = _messages_by_stamp(camera_infos)
    colors_by_stamp = _messages_by_stamp(colors)
    depths_by_stamp = _messages_by_stamp(depths)
    aligned = sorted(infos_by_stamp.keys() & colors_by_stamp.keys() & depths_by_stamp.keys())
    if not aligned:
        raise RuntimeError("no timestamp shared by camera_info, color, and depth")

    aligned_stamp = aligned[-1]
    info = infos_by_stamp[aligned_stamp]
    color = colors_by_stamp[aligned_stamp]
    depth = depths_by_stamp[aligned_stamp]
    if (info.width, info.height) != (color.width, color.height) or (
        color.width,
        color.height,
    ) != (depth.width, depth.height):
        raise RuntimeError("camera_info/color/depth dimensions differ")
    if (color.width, color.height) != (640, 480):
        raise RuntimeError(f"unexpected dimensions: {color.width}x{color.height}")
    if not (
        info.header.frame_id
        and info.header.frame_id == color.header.frame_id == depth.header.frame_id
    ):
        raise RuntimeError("camera_info/color/depth frame_id is empty or inconsistent")
    if color.header.frame_id != "task_camera_frame":
        raise RuntimeError(f"unexpected frame_id: {color.header.frame_id}")
    if color.encoding.lower() != "rgb8":
        raise RuntimeError(f"unexpected color encoding: {color.encoding}")
    if depth.encoding.upper() != "32FC1":
        raise RuntimeError(f"unexpected depth encoding: {depth.encoding}")
    if not color.data:
        raise RuntimeError("color image has no data")
    if not depth.data:
        raise RuntimeError("depth image has no data")

    depth_bytes = bytes(depth.data)
    if len(depth_bytes) % 4:
        raise RuntimeError("depth image payload is not complete 32-bit float data")
    byte_order = ">" if getattr(depth, "is_bigendian", 0) else "<"
    depth_values = 0
    finite_positive_depth = 0
    for (value,) in struct.iter_unpack(f"{byte_order}f", depth_bytes):
        depth_values += 1
        if math.isfinite(value) and value > 0.0:
            finite_positive_depth += 1
    if not depth_values or finite_positive_depth != depth_values:
        raise RuntimeError("depth image contains non-finite or non-positive values")

    return {
        "camera_info_samples": len(camera_infos),
        "color_samples": len(colors),
        "depth_samples": len(depths),
        "aligned_stamp_ns": aligned_stamp,
        "width": color.width,
        "height": color.height,
        "frame_id": color.header.frame_id,
        "color_encoding": color.encoding,
        "depth_encoding": depth.encoding,
        "color_data_bytes": len(color.data),
        "depth_data_bytes": len(depth.data),
        "depth_values": depth_values,
        "finite_positive_depth_values": finite_positive_depth,
    }


def _write_json_atomic(output: Path, result: dict) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=output.parent,
            prefix=f".{output.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary_path = Path(temporary.name)
            json.dump(result, temporary, indent=2, sort_keys=True)
            temporary.write("\n")
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_path, output)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def qualify_and_write(
    output: Path,
    phase1_colors: list[Image],
    camera_infos: list[CameraInfo],
    phase2_colors: list[Image],
    depths: list[Image],
) -> dict:
    """Validate both phases before atomically publishing one success record."""
    output.unlink(missing_ok=True)
    result = {
        "phase1": summarize_color_phase(phase1_colors),
        "phase2": summarize_aligned_phase(camera_infos, phase2_colors, depths),
    }
    _write_json_atomic(output, result)
    return result


class ColorPhaseProbe(Node):
    def __init__(self, context: Context) -> None:
        super().__init__("task_camera_probe_color_phase", context=context)
        self.color_samples = 0
        self.color_stamps: set[int] = set()
        self.create_subscription(Image, "/task_camera/color", self._on_color, 10)

    def _on_color(self, message: Image) -> None:
        self.color_samples += 1
        self.color_stamps.add(stamp_ns(message))


class AlignedPhaseProbe(Node):
    def __init__(self, context: Context) -> None:
        super().__init__("task_camera_probe_aligned_phase", context=context)
        self.camera_info_samples = 0
        self.color_samples = 0
        self.depth_samples = 0
        self.camera_infos: OrderedDict[int, CameraInfo] = OrderedDict()
        self.colors: OrderedDict[int, Image] = OrderedDict()
        self.depths: OrderedDict[int, Image] = OrderedDict()
        self.create_subscription(
            CameraInfo, "/task_camera/camera_info", self._on_camera_info, 10
        )
        self.create_subscription(Image, "/task_camera/color", self._on_color, 10)
        self.create_subscription(Image, "/task_camera/depth", self._on_depth, 10)

    @staticmethod
    def _retain(messages: OrderedDict, message: CameraInfo | Image) -> None:
        message_stamp = stamp_ns(message)
        messages[message_stamp] = message
        messages.move_to_end(message_stamp)
        while len(messages) > MAX_RETAINED_ALIGNED_MESSAGES:
            messages.popitem(last=False)

    def _on_camera_info(self, message: CameraInfo) -> None:
        self.camera_info_samples += 1
        self._retain(self.camera_infos, message)

    def _on_color(self, message: Image) -> None:
        self.color_samples += 1
        self._retain(self.colors, message)

    def _on_depth(self, message: Image) -> None:
        self.depth_samples += 1
        self._retain(self.depths, message)

    def ready(self) -> bool:
        enough_samples = min(
            self.camera_info_samples, self.color_samples, self.depth_samples
        ) >= MIN_ALIGNED_PHASE_SAMPLES
        common_stamp = bool(
            self.camera_infos.keys() & self.colors.keys() & self.depths.keys()
        )
        return enough_samples and common_stamp


def _run_node_phase(
    node_factory: Callable[[Context], Node],
    ready: Callable[[Node], bool],
    timeout_s: float,
) -> Node:
    context = Context()
    rclpy.init(context=context, signal_handler_options=SignalHandlerOptions.NO)
    executor = SingleThreadedExecutor(context=context)
    node = node_factory(context)
    executor.add_node(node)
    deadline = time.monotonic() + timeout_s
    try:
        while time.monotonic() < deadline and not ready(node):
            executor.spin_once(timeout_sec=min(0.2, max(0.0, deadline - time.monotonic())))
        if not ready(node):
            raise RuntimeError(f"camera probe phase timed out after {timeout_s} seconds")
        return node
    finally:
        executor.remove_node(node)
        executor.shutdown(timeout_sec=2.0)
        node.destroy_node()
        rclpy.shutdown(context=context, uninstall_handlers=False)


def collect_color_phase(timeout_s: float) -> dict:
    probe = _run_node_phase(
        ColorPhaseProbe,
        lambda node: len(node.color_stamps) >= MIN_COLOR_STAMPS,
        timeout_s,
    )
    return _summarize_color_stamps(sorted(probe.color_stamps), probe.color_samples)


def collect_aligned_phase(timeout_s: float) -> dict:
    probe = _run_node_phase(AlignedPhaseProbe, lambda node: node.ready(), timeout_s)
    return summarize_aligned_phase(
        list(probe.camera_infos.values()),
        list(probe.colors.values()),
        list(probe.depths.values()),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-s", type=float, default=15.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    args.output.unlink(missing_ok=True)
    try:
        phase1 = collect_color_phase(args.timeout_s)
        phase2 = collect_aligned_phase(args.timeout_s)
        result = {"phase1": phase1, "phase2": phase2}
        _write_json_atomic(args.output, result)
    except Exception as error:  # noqa: BLE001 - probe must turn every failure into exit 1
        args.output.unlink(missing_ok=True)
        print(f"camera probe failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
