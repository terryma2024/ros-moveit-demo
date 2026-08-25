#!/usr/bin/env python3
"""Bounded runtime acceptance probe for the MuJoCo task-camera topics.

The probe is intentionally independent of the launch source tree: it only
uses ROS graph messages and writes a compact JSON summary suitable for an
experiment ledger.
"""

from __future__ import annotations

import argparse
import json
import math
import struct
import time
from pathlib import Path

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CameraInfo, Image


def stamp_ns(message: CameraInfo | Image) -> int:
    stamp = message.header.stamp
    return stamp.sec * 1_000_000_000 + stamp.nanosec


class CameraTopicProbe(Node):
    def __init__(self) -> None:
        super().__init__("macos_camera_topic_probe")
        self.camera_infos: list[CameraInfo] = []
        self.colors: list[Image] = []
        self.depths: list[Image] = []
        self.create_subscription(CameraInfo, "/task_camera/camera_info", self.camera_infos.append, 10)
        self.create_subscription(Image, "/task_camera/color", self.colors.append, 10)
        self.create_subscription(Image, "/task_camera/depth", self.depths.append, 10)


def summarize(probe: CameraTopicProbe) -> dict:
    if not probe.camera_infos or not probe.colors or not probe.depths:
        raise RuntimeError(
            "missing samples: "
            f"camera_info={len(probe.camera_infos)} color={len(probe.colors)} "
            f"depth={len(probe.depths)}"
        )

    info = probe.camera_infos[-1]
    color = probe.colors[-1]
    depth = probe.depths[-1]
    if color.encoding.lower() != "rgb8":
        raise RuntimeError(f"unexpected color encoding: {color.encoding}")
    if depth.encoding.upper() != "32FC1":
        raise RuntimeError(f"unexpected depth encoding: {depth.encoding}")
    if not color.data:
        raise RuntimeError("color image has no data")
    if not depth.data:
        raise RuntimeError("depth image has no data")
    if (info.width, info.height) != (color.width, color.height) or (
        color.width,
        color.height,
    ) != (depth.width, depth.height):
        raise RuntimeError("camera_info/color/depth dimensions differ")
    if (color.width, color.height) != (640, 480):
        raise RuntimeError(f"unexpected dimensions: {color.width}x{color.height}")
    if not (info.header.frame_id and info.header.frame_id == color.header.frame_id == depth.header.frame_id):
        raise RuntimeError("camera_info/color/depth frame_id is empty or inconsistent")
    if color.header.frame_id != "task_camera_frame":
        raise RuntimeError(f"unexpected frame_id: {color.header.frame_id}")

    depth_values = struct.iter_unpack("<f", bytes(depth.data))
    finite_positive_depth = sum(1 for (value,) in depth_values if math.isfinite(value) and value > 0.0)
    if not finite_positive_depth:
        raise RuntimeError("depth image has no finite positive values")

    info_stamps = {stamp_ns(message) for message in probe.camera_infos}
    color_stamps = {stamp_ns(message) for message in probe.colors}
    depth_stamps = {stamp_ns(message) for message in probe.depths}
    aligned = sorted(info_stamps & color_stamps & depth_stamps)
    if not aligned:
        raise RuntimeError("no timestamp shared by camera_info, color, and depth")

    color_stamps_sorted = sorted(color_stamps)
    frequency_hz = 0.0
    if len(color_stamps_sorted) >= 2:
        elapsed_s = (color_stamps_sorted[-1] - color_stamps_sorted[0]) / 1_000_000_000
        if elapsed_s > 0.0:
            frequency_hz = (len(color_stamps_sorted) - 1) / elapsed_s
    if frequency_hz <= 0.0:
        raise RuntimeError("color publication frequency was not observable")
    if not 8.0 <= frequency_hz <= 12.0:
        raise RuntimeError(f"unexpected color frequency: {frequency_hz}")

    return {
        "camera_info_samples": len(probe.camera_infos),
        "color_samples": len(probe.colors),
        "depth_samples": len(probe.depths),
        "width": color.width,
        "height": color.height,
        "frame_id": color.header.frame_id,
        "color_encoding": color.encoding,
        "depth_encoding": depth.encoding,
        "color_data_bytes": len(color.data),
        "depth_data_bytes": len(depth.data),
        "finite_positive_depth_values": finite_positive_depth,
        "aligned_stamp_ns": aligned[-1],
        "color_frequency_hz": frequency_hz,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout-s", type=float, default=15.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    rclpy.init()
    probe = CameraTopicProbe()
    deadline = time.monotonic() + args.timeout_s
    try:
        while time.monotonic() < deadline:
            rclpy.spin_once(probe, timeout_sec=0.2)
            if len(probe.camera_infos) >= 3 and len(probe.colors) >= 3 and len(probe.depths) >= 3:
                break
        result = summarize(probe)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
        return 0
    finally:
        probe.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
