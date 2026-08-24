"""Deterministic five-DOF pose IK with explicit residual validation."""

from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ...ports.evidence import PoseEvidence


class UnderactuatedIkError(RuntimeError):
    pass


def _numbers(text: str | None, count: int) -> tuple[float, ...]:
    values = tuple(float(item) for item in (text or "").split())
    if len(values) != count or any(not math.isfinite(item) for item in values):
        raise UnderactuatedIkError("DYNAMIC_IK_URDF_INVALID")
    return values


def _rotation_rpy(rpy: tuple[float, ...]) -> np.ndarray:
    roll, pitch, yaw = rpy
    cr, sr = math.cos(roll), math.sin(roll)
    cp, sp = math.cos(pitch), math.sin(pitch)
    cy, sy = math.cos(yaw), math.sin(yaw)
    return np.array(
        [
            [cy * cp, cy * sp * sr - sy * cr, cy * sp * cr + sy * sr],
            [sy * cp, sy * sp * sr + cy * cr, sy * sp * cr - cy * sr],
            [-sp, cp * sr, cp * cr],
        ],
        dtype=float,
    )


def _rotation_axis(axis: tuple[float, ...], angle: float) -> np.ndarray:
    vector = np.asarray(axis, dtype=float)
    vector /= np.linalg.norm(vector)
    x, y, z = vector
    cross = np.array([[0.0, -z, y], [z, 0.0, -x], [-y, x, 0.0]])
    return np.eye(3) + math.sin(angle) * cross + (1.0 - math.cos(angle)) * (cross @ cross)


def _transform(rotation: np.ndarray, translation: tuple[float, ...]) -> np.ndarray:
    value = np.eye(4)
    value[:3, :3] = rotation
    value[:3, 3] = translation
    return value


def _quaternion_matrix(value: tuple[float, ...]) -> np.ndarray:
    x, y, z, w = value
    norm = math.sqrt(x * x + y * y + z * z + w * w)
    x, y, z, w = x / norm, y / norm, z / norm, w / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ]
    )


def _matrix_quaternion(rotation: np.ndarray) -> tuple[float, float, float, float]:
    trace = float(np.trace(rotation))
    if trace > 0.0:
        scale = math.sqrt(trace + 1.0) * 2.0
        x = (rotation[2, 1] - rotation[1, 2]) / scale
        y = (rotation[0, 2] - rotation[2, 0]) / scale
        z = (rotation[1, 0] - rotation[0, 1]) / scale
        w = 0.25 * scale
    else:
        index = int(np.argmax(np.diag(rotation)))
        if index == 0:
            scale = math.sqrt(1.0 + rotation[0, 0] - rotation[1, 1] - rotation[2, 2]) * 2
            x, y, z, w = (
                0.25 * scale,
                (rotation[0, 1] + rotation[1, 0]) / scale,
                (rotation[0, 2] + rotation[2, 0]) / scale,
                (rotation[2, 1] - rotation[1, 2]) / scale,
            )
        elif index == 1:
            scale = math.sqrt(1.0 + rotation[1, 1] - rotation[0, 0] - rotation[2, 2]) * 2
            x, y, z, w = (
                (rotation[0, 1] + rotation[1, 0]) / scale,
                0.25 * scale,
                (rotation[1, 2] + rotation[2, 1]) / scale,
                (rotation[0, 2] - rotation[2, 0]) / scale,
            )
        else:
            scale = math.sqrt(1.0 + rotation[2, 2] - rotation[0, 0] - rotation[1, 1]) * 2
            x, y, z, w = (
                (rotation[0, 2] + rotation[2, 0]) / scale,
                (rotation[1, 2] + rotation[2, 1]) / scale,
                0.25 * scale,
                (rotation[1, 0] - rotation[0, 1]) / scale,
            )
    quaternion = np.asarray((x, y, z, w), dtype=float)
    quaternion /= np.linalg.norm(quaternion)
    return tuple(float(item) for item in quaternion)


def _rotation_vector(rotation: np.ndarray) -> np.ndarray:
    cosine = min(1.0, max(-1.0, (float(np.trace(rotation)) - 1.0) / 2.0))
    angle = math.acos(cosine)
    if angle < 1e-8:
        return 0.5 * np.array(
            [
                rotation[2, 1] - rotation[1, 2],
                rotation[0, 2] - rotation[2, 0],
                rotation[1, 0] - rotation[0, 1],
            ]
        )
    axis = np.array(
        [
            rotation[2, 1] - rotation[1, 2],
            rotation[0, 2] - rotation[2, 0],
            rotation[1, 0] - rotation[0, 1],
        ]
    ) / (2.0 * math.sin(angle))
    return axis * angle


@dataclass(frozen=True, slots=True)
class _Joint:
    name: str
    kind: str
    origin: np.ndarray
    axis: tuple[float, float, float]
    lower: float
    upper: float


class UnderactuatedPoseIk:
    """Solve a requested TCP pose and reject solutions outside explicit residual gates."""

    def __init__(self, chain: tuple[_Joint, ...], joint_names: tuple[str, ...]) -> None:
        self._chain = chain
        self._joint_names = joint_names
        movable = {joint.name: joint for joint in chain if joint.kind != "fixed"}
        if set(movable) != set(joint_names):
            raise UnderactuatedIkError("DYNAMIC_IK_CHAIN_INVALID")
        self._lower = np.array([movable[name].lower for name in joint_names])
        self._upper = np.array([movable[name].upper for name in joint_names])

    @classmethod
    def from_urdf(
        cls,
        path: Path,
        joint_names: tuple[str, ...],
        root_link: str,
        tip_link: str,
    ) -> "UnderactuatedPoseIk":
        root = ET.parse(path).getroot()
        by_child = {}
        for element in root.findall("joint"):
            child = element.find("child")
            if child is not None:
                by_child[child.attrib["link"]] = element
        elements = []
        link = tip_link
        while link != root_link:
            element = by_child.get(link)
            if element is None:
                raise UnderactuatedIkError("DYNAMIC_IK_CHAIN_INVALID")
            elements.append(element)
            link = element.find("parent").attrib["link"]
        joints = []
        for element in reversed(elements):
            origin = element.find("origin")
            xyz = _numbers(None if origin is None else origin.attrib.get("xyz", "0 0 0"), 3)
            rpy = _numbers(None if origin is None else origin.attrib.get("rpy", "0 0 0"), 3)
            axis_element = element.find("axis")
            axis = _numbers(
                "0 0 1" if axis_element is None else axis_element.attrib.get("xyz", "0 0 1"),
                3,
            )
            kind = element.attrib["type"]
            limit = element.find("limit")
            lower = 0.0 if limit is None else float(limit.attrib.get("lower", "0"))
            upper = 0.0 if limit is None else float(limit.attrib.get("upper", "0"))
            joints.append(
                _Joint(
                    element.attrib["name"],
                    kind,
                    _transform(_rotation_rpy(rpy), xyz),
                    axis,
                    lower,
                    upper,
                )
            )
        return cls(tuple(joints), joint_names)

    def _matrix(self, positions: tuple[float, ...] | np.ndarray) -> np.ndarray:
        values = dict(zip(self._joint_names, positions, strict=True))
        result = np.eye(4)
        for joint in self._chain:
            result = result @ joint.origin
            if joint.kind != "fixed":
                result = result @ _transform(_rotation_axis(joint.axis, values[joint.name]), (0, 0, 0))
        return result

    def forward(self, positions: tuple[float, ...] | np.ndarray) -> PoseEvidence:
        matrix = self._matrix(positions)
        return PoseEvidence(
            tuple(float(item) for item in matrix[:3, 3]),
            _matrix_quaternion(matrix[:3, :3]),
        )

    @staticmethod
    def orientation_error_rad(actual: PoseEvidence, target: PoseEvidence) -> float:
        dot = abs(sum(a * b for a, b in zip(actual.orientation_xyzw, target.orientation_xyzw)))
        return 2.0 * math.acos(min(1.0, max(-1.0, dot)))

    def _residual(self, positions: np.ndarray, target: PoseEvidence) -> np.ndarray:
        matrix = self._matrix(positions)
        position = np.asarray(target.position_m) - matrix[:3, 3]
        orientation = _rotation_vector(_quaternion_matrix(target.orientation_xyzw) @ matrix[:3, :3].T)
        return np.concatenate((position, 0.08 * orientation))

    def solve(
        self,
        target: PoseEvidence,
        seed: tuple[float, ...],
        *,
        position_tolerance_m: float = 0.002,
        orientation_tolerance_rad: float = 0.10,
    ) -> tuple[float, ...]:
        if len(seed) != len(self._joint_names):
            raise UnderactuatedIkError("DYNAMIC_IK_SEED_INVALID")
        positions = np.clip(np.asarray(seed, dtype=float), self._lower, self._upper)
        epsilon = 1e-5
        for _ in range(200):
            residual = self._residual(positions, target)
            actual = self.forward(positions)
            if (
                math.dist(actual.position_m, target.position_m) <= position_tolerance_m
                and self.orientation_error_rad(actual, target) <= orientation_tolerance_rad
            ):
                return tuple(float(item) for item in positions)
            jacobian = np.empty((6, len(positions)))
            for index in range(len(positions)):
                candidate = positions.copy()
                candidate[index] += epsilon
                jacobian[:, index] = (self._residual(candidate, target) - residual) / epsilon
            damping = 1e-5
            step = -np.linalg.solve(
                jacobian.T @ jacobian + damping * np.eye(len(positions)),
                jacobian.T @ residual,
            )
            norm = float(np.linalg.norm(step))
            if norm > 0.20:
                step *= 0.20 / norm
            positions = np.clip(positions + step, self._lower, self._upper)
        actual = self.forward(positions)
        raise UnderactuatedIkError(
            "DYNAMIC_IK_RESIDUAL_EXCEEDED: "
            f"position_m={math.dist(actual.position_m, target.position_m):.6f} "
            f"orientation_rad={self.orientation_error_rad(actual, target):.6f}"
        )
