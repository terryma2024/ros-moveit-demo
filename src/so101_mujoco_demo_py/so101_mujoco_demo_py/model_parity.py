"""Compile and compare the independent URDF and MJCF kinematic models."""

from __future__ import annotations

import ctypes
import hashlib
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml

Transform = tuple[tuple[tuple[float, float, float], ...], tuple[float, float, float]]
IDENTITY: Transform = (((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)), (0.0, 0.0, 0.0))


def _numbers(text: str | None, count: int, default: tuple[float, ...]) -> tuple[float, ...]:
    values = default if text is None else tuple(float(value) for value in text.split())
    if len(values) != count:
        raise ValueError(f"expected {count} numbers, got {values}")
    return values


def _multiply(left: Transform, right: Transform) -> Transform:
    left_rotation, left_position = left
    right_rotation, right_position = right
    rotation = tuple(
        tuple(
            sum(left_rotation[row][k] * right_rotation[k][column] for k in range(3))
            for column in range(3)
        )
        for row in range(3)
    )
    position = tuple(
        left_position[row] + sum(left_rotation[row][k] * right_position[k] for k in range(3))
        for row in range(3)
    )
    return rotation, position  # type: ignore[return-value]


def _axis_angle(axis: tuple[float, float, float], angle: float) -> Transform:
    norm = math.sqrt(sum(value * value for value in axis))
    x, y, z = (value / norm for value in axis)
    cosine = math.cos(angle)
    sine = math.sin(angle)
    complement = 1.0 - cosine
    rotation = (
        (cosine + x * x * complement, x * y * complement - z * sine, x * z * complement + y * sine),
        (y * x * complement + z * sine, cosine + y * y * complement, y * z * complement - x * sine),
        (z * x * complement - y * sine, z * y * complement + x * sine, cosine + z * z * complement),
    )
    return rotation, (0.0, 0.0, 0.0)


def _rpy(rpy: tuple[float, float, float], xyz: tuple[float, float, float]) -> Transform:
    roll, pitch, yaw = rpy
    result = IDENTITY
    for axis, angle in (((0.0, 0.0, 1.0), yaw), ((0.0, 1.0, 0.0), pitch), ((1.0, 0.0, 0.0), roll)):
        result = _multiply(result, _axis_angle(axis, angle))
    return result[0], xyz


def _quaternion(
    wxyz: tuple[float, float, float, float], xyz: tuple[float, float, float]
) -> Transform:
    w, x, y, z = wxyz
    norm = math.sqrt(sum(value * value for value in wxyz))
    w, x, y, z = (value / norm for value in (w, x, y, z))
    rotation = (
        (1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)),
        (2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)),
        (2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)),
    )
    return rotation, xyz


def _orientation_error_degrees(left: Transform, right: Transform) -> float:
    left_rotation, _ = left
    right_rotation, _ = right
    trace = sum(
        left_rotation[row][column] * right_rotation[row][column]
        for row in range(3)
        for column in range(3)
    )
    cosine = max(-1.0, min(1.0, (trace - 1.0) / 2.0))
    return math.degrees(math.acos(cosine))


def compile_mjcf(path: Path) -> None:
    library = ctypes.CDLL("/opt/ros/jazzy/opt/mujoco_vendor/lib/libmujoco.so")
    library.mj_loadXML.argtypes = [ctypes.c_char_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    library.mj_loadXML.restype = ctypes.c_void_p
    library.mj_deleteModel.argtypes = [ctypes.c_void_p]
    error = ctypes.create_string_buffer(2048)
    model = library.mj_loadXML(str(path).encode(), None, error, len(error))
    if not model:
        raise ValueError(error.value.decode(errors="replace"))
    library.mj_deleteModel(model)


def _urdf_transforms(root: ET.Element, values: dict[str, float]) -> dict[str, Transform]:
    transforms = {"world": IDENTITY}
    pending = list(root.findall("joint"))
    while pending:
        progress = False
        for joint in pending[:]:
            parent = joint.find("parent").get("link")
            child = joint.find("child").get("link")
            if parent not in transforms:
                continue
            origin = joint.find("origin")
            local = _rpy(
                _numbers(origin.get("rpy"), 3, (0.0, 0.0, 0.0)),
                _numbers(origin.get("xyz"), 3, (0.0, 0.0, 0.0)),
            )
            if joint.get("type") != "fixed":
                axis = _numbers(joint.find("axis").get("xyz"), 3, (0.0, 0.0, 1.0))
                local = _multiply(local, _axis_angle(axis, values[joint.get("name")]))
            transforms[child] = _multiply(transforms[parent], local)
            pending.remove(joint)
            progress = True
        if not progress:
            raise ValueError("URDF joint tree is disconnected")
    return transforms


def _mjcf_transforms(
    root: ET.Element, values: dict[str, float]
) -> tuple[dict[str, Transform], Transform]:
    transforms: dict[str, Transform] = {}
    tcp: Transform | None = None

    def visit(body: ET.Element, parent: Transform) -> None:
        nonlocal tcp
        local = _quaternion(
            _numbers(body.get("quat"), 4, (1.0, 0.0, 0.0, 0.0)),
            _numbers(body.get("pos"), 3, (0.0, 0.0, 0.0)),
        )
        joint = body.find("joint")
        if joint is not None:
            axis = _numbers(joint.get("axis"), 3, (0.0, 0.0, 1.0))
            local = _multiply(local, _axis_angle(axis, values[joint.get("name")]))
        world = _multiply(parent, local)
        transforms[body.get("name")] = world
        site = body.find('site[@name="so101_tcp"]')
        if site is not None:
            tcp = _multiply(
                world,
                _quaternion(
                    _numbers(site.get("quat"), 4, (1.0, 0.0, 0.0, 0.0)),
                    _numbers(site.get("pos"), 3, (0.0, 0.0, 0.0)),
                ),
            )
        for child in body.findall("body"):
            visit(child, world)

    for body in root.findall("./worldbody/body"):
        visit(body, IDENTITY)
    if tcp is None:
        raise ValueError("MJCF has no so101_tcp site")
    return transforms, tcp


def check_model_parity(config_path: Path) -> dict[str, object]:
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    package_root = config_path.parent.parent
    urdf_path = package_root / config["urdf"]
    mjcf_path = package_root / config["mjcf"]
    errors: list[str] = []
    compiled = True
    try:
        compile_mjcf(mjcf_path)
    except Exception as error:
        compiled = False
        errors.append(f"MJCF compile failed: {error}")
    urdf = ET.parse(urdf_path).getroot()
    mjcf = ET.parse(mjcf_path).getroot()
    names = [str(index) for index in range(1, 7)]
    urdf_joints = {
        joint.get("name"): joint for joint in urdf.findall("joint") if joint.get("name") in names
    }
    mjcf_joints = {
        joint.get("name"): joint
        for joint in mjcf.findall("./worldbody//joint")
        if joint.get("name") is not None
    }
    joint_names_exact = list(mjcf_joints) == names and set(urdf_joints) == set(names)
    joint_axes_exact = all(
        _numbers(urdf_joints[name].find("axis").get("xyz"), 3, ())
        == _numbers(mjcf_joints[name].get("axis"), 3, ())
        for name in names
    )
    joint_limits_exact = all(
        tuple(float(urdf_joints[name].find("limit").get(field)) for field in ("lower", "upper"))
        == _numbers(mjcf_joints[name].get("range"), 2, ())
        for name in names
    )
    q6 = config["q6_semantics"]
    lower, upper = _numbers(mjcf_joints["6"].get("range"), 2, ())
    q6_direction_exact = lower <= q6["grasp"] < q6["preopen"] < q6["release"] <= upper
    mesh_hashes_exact = True
    for filename, expected in config["mesh_sha256"].items():
        path = package_root / "mjcf/assets" / filename
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            mesh_hashes_exact = False
    maximum_position = 0.0
    maximum_orientation = 0.0
    tcp_exact = True
    for sample in config["samples"]:
        values = dict(zip(names, (float(value) for value in sample), strict=True))
        urdf_transforms = _urdf_transforms(urdf, values)
        mjcf_transforms, mjcf_tcp = _mjcf_transforms(mjcf, values)
        for body in config["bodies"]:
            left = urdf_transforms[body]
            right = mjcf_transforms[body]
            position_error = math.dist(left[1], right[1])
            orientation_error = _orientation_error_degrees(left, right)
            maximum_position = max(maximum_position, position_error)
            maximum_orientation = max(maximum_orientation, orientation_error)
        urdf_tcp = urdf_transforms["so101_tcp"]
        tcp_position = math.dist(urdf_tcp[1], mjcf_tcp[1])
        tcp_orientation = _orientation_error_degrees(urdf_tcp, mjcf_tcp)
        maximum_position = max(maximum_position, tcp_position)
        maximum_orientation = max(maximum_orientation, tcp_orientation)
        tcp_exact = (
            tcp_exact
            and tcp_position <= config["position_tolerance_m"]
            and tcp_orientation <= config["orientation_tolerance_deg"]
        )
    if maximum_position > config["position_tolerance_m"]:
        errors.append("position tolerance exceeded")
    if maximum_orientation > config["orientation_tolerance_deg"]:
        errors.append("orientation tolerance exceeded")
    for field, valid in (
        ("joint names", joint_names_exact),
        ("joint axes", joint_axes_exact),
        ("joint limits", joint_limits_exact),
        ("q6 direction", q6_direction_exact),
        ("mesh hashes", mesh_hashes_exact),
        ("TCP", tcp_exact),
    ):
        if not valid:
            errors.append(f"{field} mismatch")
    return {
        "compiled": compiled,
        "joint_names_exact": joint_names_exact,
        "joint_axes_exact": joint_axes_exact,
        "joint_limits_exact": joint_limits_exact,
        "q6_direction_exact": q6_direction_exact,
        "mesh_hashes_exact": mesh_hashes_exact,
        "tcp_exact": tcp_exact,
        "sample_count": len(config["samples"]),
        "maximum_position_error_m": maximum_position,
        "maximum_orientation_error_deg": maximum_orientation,
        "validation_errors": errors,
    }
