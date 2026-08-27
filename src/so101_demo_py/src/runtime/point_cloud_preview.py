"""Deterministic dependency-free point-cloud preview rendering."""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

import numpy as np


def write_png_rgb8(image: np.ndarray, path: Path) -> None:
    if image.ndim != 3 or image.shape[2] != 3 or image.dtype != np.uint8:
        raise ValueError("PNG image must be uint8 RGB")

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return (
            struct.pack(">I", len(payload))
            + body
            + struct.pack(">I", zlib.crc32(body))
        )

    height, width, _ = image.shape
    rows = b"".join(b"\x00" + image[row].tobytes() for row in range(height))
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, level=9))
        + chunk(b"IEND", b"")
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)


def render_point_cloud_preview(
    points_xyz: np.ndarray,
    colors_rgb: np.ndarray,
    output_png: Path,
    *,
    width: int = 640,
    height: int = 480,
    point_size: int = 2,
) -> dict[str, object]:
    points = np.asarray(points_xyz, dtype=np.float64)
    colors = np.asarray(colors_rgb, dtype=np.float64)
    if points.ndim != 2 or points.shape[1:] != (3,) or len(points) == 0:
        raise ValueError("point cloud must be a non-empty array with shape (count, 3)")
    if colors.shape != points.shape:
        raise ValueError("point cloud colors must match point shape")
    if not np.isfinite(points).all() or not np.isfinite(colors).all():
        raise ValueError("point cloud values must be finite")
    if width <= 0 or height <= 0 or point_size <= 0:
        raise ValueError("preview dimensions and point size must be positive")

    center = np.median(points, axis=0)
    radius = float(np.max(np.linalg.norm(points - center, axis=1)))
    radius = max(radius, 1e-6)
    yaw = math.radians(35.0)
    pitch = math.radians(-25.0)
    yaw_matrix = np.array(
        [
            [math.cos(yaw), -math.sin(yaw), 0.0],
            [math.sin(yaw), math.cos(yaw), 0.0],
            [0, 0, 1],
        ]
    )
    pitch_matrix = np.array(
        [
            [1, 0, 0],
            [0, math.cos(pitch), -math.sin(pitch)],
            [0, math.sin(pitch), math.cos(pitch)],
        ]
    )
    camera = (points - center) @ (pitch_matrix @ yaw_matrix).T
    camera[:, 2] += 3.0 * radius
    focal = 0.8 * min(width, height)
    columns = np.rint(focal * camera[:, 0] / camera[:, 2] + width / 2.0).astype(int)
    rows = np.rint(-focal * camera[:, 1] / camera[:, 2] + height / 2.0).astype(int)
    pixels = np.full((height, width, 3), (20, 20, 24), dtype=np.uint8)
    z_buffer = np.full((height, width), np.inf)
    color_bytes = np.rint(np.clip(colors, 0.0, 1.0) * 255.0).astype(np.uint8)
    for index in np.argsort(camera[:, 2]):
        row = rows[index]
        column = columns[index]
        for dy in range(-point_size + 1, point_size):
            for dx in range(-point_size + 1, point_size):
                target_row = row + dy
                target_column = column + dx
                if (
                    0 <= target_row < height
                    and 0 <= target_column < width
                    and camera[index, 2] < z_buffer[target_row, target_column]
                ):
                    z_buffer[target_row, target_column] = camera[index, 2]
                    pixels[target_row, target_column] = color_bytes[index]
    write_png_rgb8(pixels, output_png)
    return {
        "projection": "perspective",
        "image_width": width,
        "image_height": height,
        "point_size": point_size,
        "yaw_deg": 35.0,
        "pitch_deg": -25.0,
        "background_rgb": [20, 20, 24],
        "z_buffer": True,
        "point_count": len(points),
    }
