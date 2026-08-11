"""Frame-correct TCP pose stepping using normalized quaternions."""

from __future__ import annotations

import math
from typing import Tuple

from .models import Pose6D, StepFrame

Quaternion = Tuple[float, float, float, float]


def _normalize(quaternion: Quaternion) -> Quaternion:
    norm = math.sqrt(sum(component * component for component in quaternion))
    if norm == 0.0:
        raise ValueError("ZERO_QUATERNION")
    return tuple(component / norm for component in quaternion)  # type: ignore[return-value]


def _multiply(left: Quaternion, right: Quaternion) -> Quaternion:
    lx, ly, lz, lw = left
    rx, ry, rz, rw = right
    return (
        lw * rx + lx * rw + ly * rz - lz * ry,
        lw * ry - lx * rz + ly * rw + lz * rx,
        lw * rz + lx * ry - ly * rx + lz * rw,
        lw * rw - lx * rx - ly * ry - lz * rz,
    )


def quaternion_from_rpy(roll: float, pitch: float, yaw: float) -> Quaternion:
    cr, sr = math.cos(roll / 2.0), math.sin(roll / 2.0)
    cp, sp = math.cos(pitch / 2.0), math.sin(pitch / 2.0)
    cy, sy = math.cos(yaw / 2.0), math.sin(yaw / 2.0)
    return _normalize((sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
                       cr * cp * sy - sr * sp * cy, cr * cp * cy + sr * sp * sy))


def rpy_from_quaternion(quaternion: Quaternion) -> Tuple[float, float, float]:
    x, y, z, w = _normalize(quaternion)
    roll = math.atan2(2.0 * (w * x + y * z), 1.0 - 2.0 * (x * x + y * y))
    pitch_term = 2.0 * (w * y - z * x)
    pitch = math.asin(max(-1.0, min(1.0, pitch_term)))
    yaw = math.atan2(2.0 * (w * z + x * y), 1.0 - 2.0 * (y * y + z * z))
    return roll, pitch, yaw


def _rotation_matrix(quaternion: Quaternion) -> Tuple[Tuple[float, float, float], ...]:
    x, y, z, w = _normalize(quaternion)
    return (
        (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y - z * w), 2.0 * (x * z + y * w)),
        (2.0 * (x * y + z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z - x * w)),
        (2.0 * (x * z - y * w), 2.0 * (y * z + x * w), 1.0 - 2.0 * (x * x + y * y)),
    )


def apply_translation_step(pose: Pose6D, axis: str, distance_m: float, frame: StepFrame) -> Pose6D:
    if axis not in {"x", "y", "z"}:
        raise ValueError("INVALID_TRANSLATION_AXIS")
    delta = {"x": (distance_m, 0.0, 0.0), "y": (0.0, distance_m, 0.0),
             "z": (0.0, 0.0, distance_m)}[axis]
    if frame is StepFrame.TOOL:
        matrix = _rotation_matrix(quaternion_from_rpy(pose.roll_rad, pose.pitch_rad, pose.yaw_rad))
        delta = tuple(sum(matrix[row][column] * delta[column] for column in range(3))
                      for row in range(3))
    return pose.copy(update={"x_m": pose.x_m + delta[0], "y_m": pose.y_m + delta[1],
                             "z_m": pose.z_m + delta[2]})


def apply_rotation_step(pose: Pose6D, axis: str, angle_rad: float, frame: StepFrame) -> Pose6D:
    if axis not in {"x", "y", "z"}:
        raise ValueError("INVALID_ROTATION_AXIS")
    half = angle_rad / 2.0
    delta = {"x": (math.sin(half), 0.0, 0.0, math.cos(half)),
             "y": (0.0, math.sin(half), 0.0, math.cos(half)),
             "z": (0.0, 0.0, math.sin(half), math.cos(half))}[axis]
    current = quaternion_from_rpy(pose.roll_rad, pose.pitch_rad, pose.yaw_rad)
    rotated = _multiply(delta, current) if frame is StepFrame.WORLD else _multiply(current, delta)
    roll, pitch, yaw = rpy_from_quaternion(rotated)
    return pose.copy(update={"roll_rad": roll, "pitch_rad": pitch, "yaw_rad": yaw})
