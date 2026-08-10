#!/usr/bin/env python3
"""
Calculate SO-101 Coke pre-open and contact angles at a fixed grasp depth.

The fixed finger is used as the geometric reference.  At the requested
depth from its inner-face tip, a centre ray is cast along the gripper opening
axis.  The Coke centre is placed one Coke radius from the fixed finger, so
closing the moving jaw does not need to push the object toward the fixed jaw.

For a 66 mm Coke and 4 mm total pre-open clearance:

* q_preopen: fixed side 33 mm + moving side 37 mm = 70 mm
* q_contact: fixed side 33 mm + moving side 33 mm = 66 mm

No area centroid or ``tip_fraction`` is used.  Contact points are the actual
ray/triangle intersections at the configured physical depth.
"""

import argparse
import hashlib
import math
from pathlib import Path
import struct
import sys
from typing import NamedTuple
import xml.etree.ElementTree as ET

import numpy as np
from ament_index_python.packages import get_package_share_directory
import yaml


def default_mesh_dir() -> Path:
    """Return the installed package's SO-101 mesh directory."""
    return (
        Path(get_package_share_directory('so101_gazebo_demo_cpp'))
        / 'meshes'
        / 'so101'
    )


def default_urdf_path() -> Path:
    """Return the installed package's geometry-bearing xacro."""
    return (
        Path(get_package_share_directory('so101_gazebo_demo_cpp'))
        / 'urdf'
        / 'so101_base.xacro'
    )


# ---------------------------------------------------------------------------
# URDF constants (from so101_base.xacro)
# ---------------------------------------------------------------------------

# Joint 6: gripper -> jaw
J6_XYZ = np.array([0.0202, 0.0188, -0.0234])
J6_RPY = np.array([1.5708, 0.0, 0.0])

# Visual origin of wrist_roll_follower (fixed finger) in gripper link
FIXED_VISUAL_XYZ = np.array([0.0, -0.000218214, 0.000949706])
FIXED_VISUAL_RPY = np.array([-math.pi, 0.0, 0.0])

# Visual origin of moving_jaw in jaw link
MOVING_VISUAL_XYZ = np.array([0.0, 0.0, 0.0189])
MOVING_VISUAL_RPY = np.array([0.0, 0.0, 0.0])

J6_LOWER = -0.174533
J6_UPPER = 1.74533

OPENING_AXIS_GRIPPER = np.array([1.0, 0.0, 0.0])
DEFAULT_GRASP_DEPTH = 0.020
DEFAULT_TASK_OBJECT_DIAMETER = 0.066
DEFAULT_PREOPEN_CLEARANCE = 0.004
GEOMETRY_MODEL_VERSION = 'so101-gripper-d20-mesh-v1'
GEOMETRY_CONSTANTS_CANONICAL = (
    'J6_XYZ=0.0202,0.0188,-0.0234\n'
    'J6_RPY=1.5708,0,0\n'
    'FIXED_VISUAL_XYZ=0,-0.000218214,0.000949706\n'
    'FIXED_VISUAL_RPY=-pi,0,0\n'
    'MOVING_VISUAL_XYZ=0,0,0.0189\n'
    'MOVING_VISUAL_RPY=0,0,0\n'
    'OPENING_AXIS_GRIPPER=1,0,0\n'
)


class RayHit(NamedTuple):
    point: np.ndarray
    normal: np.ndarray
    distance: float
    face_index: int


class FixedContactGeometry(NamedTuple):
    inner_tip_z: float
    section_z: float
    contact_point: np.ndarray
    coke_center: np.ndarray
    inward_dot: float


class GripperTargets(NamedTuple):
    grasp_depth: float
    section_z: float
    fixed_contact_point: np.ndarray
    coke_center: np.ndarray
    q_preopen: float
    q_contact: float
    preopen_width: float
    contact_width: float
    fixed_inward_dot: float
    preopen_moving_inward_dot: float
    contact_moving_inward_dot: float


class WidthCalibration(NamedTuple):
    model_version: str
    fixed_mesh_sha256: str
    moving_mesh_sha256: str
    urdf_sha256: str
    constants_sha256: str
    model_fingerprint: str
    grasp_depth: float
    task_object_diameter: float
    samples: tuple[tuple[float, float], ...]


class FingertipPadGapCalibration(NamedTuple):
    """Exact opening-axis clearance facts for the generated native pad meshes."""
    safe_floor_q6: float
    grasp_q6: float
    preopen_q6: float
    safe_floor_gap_m: float
    grasp_gap_m: float
    preopen_gap_m: float
    cup_wall_interference_m: float
    controller_endpoint_epsilon_rad: float
    gap_samples: tuple[tuple[float, float], ...]
    input_fingerprint: str
    fixed_visual_mesh_sha256: str
    moving_visual_mesh_sha256: str
    fixed_collision_mesh_sha256: str
    moving_collision_mesh_sha256: str
    urdf_sha256: str
    j6_xyz: np.ndarray
    j6_rpy: np.ndarray
    fixed_contact_triangles: np.ndarray
    moving_contact_triangles_jaw: np.ndarray

    def gap_at(self, q6: float) -> float:
        return fingertip_pad_opening_axis_min_gap(
            self.fixed_contact_triangles, self.moving_contact_triangles_jaw, q6,
            self.j6_xyz, self.j6_rpy,
        )


class TriangleMesh(NamedTuple):
    """Minimal triangle mesh representation required by this calculator."""

    vertices: np.ndarray
    faces: np.ndarray
    face_normals: np.ndarray

    @property
    def triangles(self) -> np.ndarray:
        return self.vertices[self.faces]


# ---------------------------------------------------------------------------
# Transform helpers
# ---------------------------------------------------------------------------

def rot_x(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]])


def rot_y(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]])


def rot_z(angle: float) -> np.ndarray:
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])


def rpy_to_matrix(roll: float, pitch: float, yaw: float) -> np.ndarray:
    """Return a URDF-style ZYX roll/pitch/yaw rotation matrix."""
    return rot_z(yaw) @ rot_y(pitch) @ rot_x(roll)


def make_transform(xyz: np.ndarray, rpy: np.ndarray) -> np.ndarray:
    transform = np.eye(4)
    transform[:3, :3] = rpy_to_matrix(*rpy)
    transform[:3, 3] = xyz
    return transform


T_J6 = make_transform(J6_XYZ, J6_RPY)


def jaw_transform_gripper(q6: float) -> np.ndarray:
    """Return T_gripper<-jaw(q6)."""
    joint_rotation = np.eye(4)
    joint_rotation[:3, :3] = rot_z(q6)
    return T_J6 @ joint_rotation


def load_mesh_in_link_frame(
    stl_path: Path,
    visual_xyz: np.ndarray,
    visual_rpy: np.ndarray,
) -> TriangleMesh:
    """Load a binary STL and transform it into the owning link frame.

    The calculator only needs triangle vertices, faces, and geometric normals.
    Keeping that representation here avoids depending on the large ``trimesh``
    package and its optional acceleration dependencies.
    """
    payload = stl_path.read_bytes()
    if len(payload) < 84:
        raise ValueError(f'Invalid binary STL header: {stl_path}')

    triangle_count = struct.unpack_from('<I', payload, 80)[0]
    expected_size = 84 + triangle_count * 50
    if len(payload) != expected_size:
        raise ValueError(
            f'Expected binary STL with {triangle_count} triangles at '
            f'{stl_path}; file size is {len(payload)}, expected {expected_size}'
        )

    record_dtype = np.dtype(
        [
            ('stored_normal', '<f4', (3,)),
            ('vertices', '<f4', (3, 3)),
            ('attribute_byte_count', '<u2'),
        ]
    )
    records = np.frombuffer(
        payload,
        dtype=record_dtype,
        count=triangle_count,
        offset=84,
    )
    triangles = records['vertices'].astype(np.float64)
    edge1 = triangles[:, 1] - triangles[:, 0]
    edge2 = triangles[:, 2] - triangles[:, 0]
    normals = np.cross(edge1, edge2)
    normal_lengths = np.linalg.norm(normals, axis=1)
    valid_triangles = normal_lengths > 1e-12
    triangles = triangles[valid_triangles]
    normals = normals[valid_triangles]
    normal_lengths = normal_lengths[valid_triangles]
    if len(triangles) == 0:
        raise ValueError(f'STL contains no non-degenerate triangles: {stl_path}')
    normals /= normal_lengths[:, None]

    transform = make_transform(visual_xyz, visual_rpy)
    rotation = transform[:3, :3]
    translation = transform[:3, 3]
    vertices = triangles.reshape(-1, 3) @ rotation.T + translation
    normals = normals @ rotation.T
    faces = np.arange(len(triangles) * 3, dtype=np.int64).reshape(-1, 3)
    return TriangleMesh(vertices, faces, normals)


# ---------------------------------------------------------------------------
# Deterministic contact geometry
# ---------------------------------------------------------------------------

def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise ValueError('Direction vector must be non-zero')
    return np.asarray(vector, dtype=float) / norm


def ray_mesh_first_hit(
    mesh: TriangleMesh,
    origin: np.ndarray,
    direction: np.ndarray,
) -> RayHit:
    """
    Return the nearest positive Moller-Trumbore ray/triangle hit.

    This vectorised implementation avoids the optional trimesh
    ``rtree`` dependency, keeping the calculator runnable in headless CI.
    """
    origin = np.asarray(origin, dtype=float)
    direction = _unit(direction)
    triangles = mesh.triangles
    edge1 = triangles[:, 1] - triangles[:, 0]
    edge2 = triangles[:, 2] - triangles[:, 0]

    repeated_direction = np.broadcast_to(direction, edge2.shape)
    h = np.cross(repeated_direction, edge2)
    determinant = np.einsum('ij,ij->i', edge1, h)
    valid = np.abs(determinant) > 1e-10

    inverse_determinant = np.zeros_like(determinant)
    inverse_determinant[valid] = 1.0 / determinant[valid]
    offset = origin - triangles[:, 0]
    barycentric_u = inverse_determinant * np.einsum('ij,ij->i', offset, h)
    q_vector = np.cross(offset, edge1)
    barycentric_v = inverse_determinant * np.einsum(
        'ij,j->i', q_vector, direction
    )
    ray_distance = inverse_determinant * np.einsum('ij,ij->i', edge2, q_vector)

    tolerance = 1e-9
    valid &= barycentric_u >= -tolerance
    valid &= barycentric_v >= -tolerance
    valid &= barycentric_u + barycentric_v <= 1.0 + tolerance
    valid &= ray_distance > 1e-8

    face_indices = np.flatnonzero(valid)
    if len(face_indices) == 0:
        raise ValueError('Ray did not hit the mesh')

    face_index = int(face_indices[np.argmin(ray_distance[face_indices])])
    distance = float(ray_distance[face_index])
    point = origin + distance * direction
    normal = _unit(mesh.face_normals[face_index])
    return RayHit(point, normal, distance, face_index)


def fixed_contact_geometry(
    fixed_mesh: TriangleMesh,
    grasp_depth: float,
    coke_radius: float,
    opening_axis: np.ndarray = OPENING_AXIS_GRIPPER,
    lateral_offset: float = 0.0,
    normal_tolerance_deg: float = 30.0,
) -> FixedContactGeometry:
    """Locate the fixed contact point at ``grasp_depth`` from its inner tip."""
    if grasp_depth <= 0.0:
        raise ValueError('grasp_depth must be positive')
    if coke_radius <= 0.0:
        raise ValueError('coke_radius must be positive')

    opening_axis = _unit(opening_axis)
    normal_threshold = math.cos(math.radians(normal_tolerance_deg))
    inner_face_mask = fixed_mesh.face_normals @ opening_axis > normal_threshold
    if np.count_nonzero(inner_face_mask) < 3:
        raise ValueError('Could not identify the fixed finger inner surface')

    inner_vertex_ids = np.unique(fixed_mesh.faces[inner_face_mask])
    inner_tip_z = float(fixed_mesh.vertices[inner_vertex_ids, 2].min())
    section_z = inner_tip_z + grasp_depth
    ray_origin = np.array([0.0, lateral_offset, section_z])
    hit = ray_mesh_first_hit(fixed_mesh, ray_origin, -opening_axis)
    inward_dot = float(np.dot(hit.normal, opening_axis))
    if inward_dot <= normal_threshold:
        raise ValueError(
            'The d-section ray did not hit the fixed finger inner surface'
        )

    coke_center = hit.point + coke_radius * opening_axis
    return FixedContactGeometry(
        inner_tip_z,
        section_z,
        hit.point,
        coke_center,
        inward_dot,
    )


def moving_contact_at_q6(
    moving_mesh_jaw: TriangleMesh,
    coke_center_gripper: np.ndarray,
    q6: float,
    opening_axis: np.ndarray = OPENING_AXIS_GRIPPER,
) -> RayHit:
    """Cast from the Coke centre to the moving jaw at q6."""
    opening_axis = _unit(opening_axis)
    transform = jaw_transform_gripper(q6)
    rotation = transform[:3, :3]
    translation = transform[:3, 3]

    origin_jaw = rotation.T @ (coke_center_gripper - translation)
    direction_jaw = rotation.T @ opening_axis
    jaw_hit = ray_mesh_first_hit(moving_mesh_jaw, origin_jaw, direction_jaw)

    point_gripper = rotation @ jaw_hit.point + translation
    normal_gripper = _unit(rotation @ jaw_hit.normal)
    distance = float(
        np.dot(point_gripper - coke_center_gripper, opening_axis)
    )
    return RayHit(point_gripper, normal_gripper, distance, jaw_hit.face_index)


def find_q_for_moving_clearance(
    moving_mesh_jaw: TriangleMesh,
    coke_center_gripper: np.ndarray,
    target_distance: float,
    opening_axis: np.ndarray = OPENING_AXIS_GRIPPER,
    q_lo: float = J6_LOWER,
    q_hi: float = J6_UPPER,
    distance_tolerance: float = 1e-10,
) -> float:
    """Find the more-closed valid q6 whose moving-side gap matches target."""
    if target_distance <= 0.0:
        raise ValueError('target_distance must be positive')

    opening_axis = _unit(opening_axis)

    def residual(q6: float) -> float:
        hit = moving_contact_at_q6(
            moving_mesh_jaw, coke_center_gripper, q6, opening_axis
        )
        if np.dot(hit.normal, -opening_axis) <= 0.0:
            raise ValueError('Ray hit a moving-jaw face that points away from the gap')
        return hit.distance - target_distance

    sweep = np.linspace(q_lo, q_hi, 500)
    samples: list[tuple[float, float]] = []
    for q6 in sweep:
        try:
            samples.append((float(q6), residual(float(q6))))
        except ValueError:
            samples.append((float(q6), math.nan))

    brackets: list[tuple[float, float, float, float]] = []
    for (q_a, r_a), (q_b, r_b) in zip(samples[:-1], samples[1:]):
        if not (math.isfinite(r_a) and math.isfinite(r_b)):
            continue
        if r_a == 0.0:
            return q_a
        if r_a * r_b < 0.0:
            brackets.append((q_a, q_b, r_a, r_b))

    if not brackets:
        raise ValueError(
            f'No valid q6 reaches moving-side distance '
            f'{target_distance * 1000:.2f} mm'
        )

    roots: list[float] = []
    for q_a, q_b, r_a, _ in brackets:
        for _ in range(100):
            q_mid = (q_a + q_b) / 2.0
            r_mid = residual(q_mid)
            if abs(r_mid) <= distance_tolerance:
                q_a = q_b = q_mid
                break
            if r_a * r_mid > 0.0:
                q_a, r_a = q_mid, r_mid
            else:
                q_b = q_mid
        roots.append((q_a + q_b) / 2.0)

    return min(roots)


def calculate_gripper_targets(
    mesh_dir: Path,
    grasp_depth: float = DEFAULT_GRASP_DEPTH,
    task_object_diameter: float = DEFAULT_TASK_OBJECT_DIAMETER,
    preopen_clearance: float = DEFAULT_PREOPEN_CLEARANCE,
) -> GripperTargets:
    """Calculate q_preopen and q_contact for the configured task object."""
    if task_object_diameter <= 0.0:
        raise ValueError('task_object_diameter must be positive')
    if preopen_clearance < 0.0:
        raise ValueError('preopen_clearance must be non-negative')

    fixed_mesh = load_mesh_in_link_frame(
        mesh_dir / 'wrist_roll_follower_so101_v1.stl',
        FIXED_VISUAL_XYZ,
        FIXED_VISUAL_RPY,
    )
    moving_mesh = load_mesh_in_link_frame(
        mesh_dir / 'moving_jaw_so101_v1.stl',
        MOVING_VISUAL_XYZ,
        MOVING_VISUAL_RPY,
    )

    opening_axis = OPENING_AXIS_GRIPPER
    coke_radius = task_object_diameter / 2.0
    fixed = fixed_contact_geometry(
        fixed_mesh,
        grasp_depth,
        coke_radius,
        opening_axis,
    )

    q_preopen = find_q_for_moving_clearance(
        moving_mesh,
        fixed.coke_center,
        coke_radius + preopen_clearance,
        opening_axis,
    )
    q_contact = find_q_for_moving_clearance(
        moving_mesh,
        fixed.coke_center,
        coke_radius,
        opening_axis,
    )

    preopen_hit = moving_contact_at_q6(
        moving_mesh, fixed.coke_center, q_preopen, opening_axis
    )
    contact_hit = moving_contact_at_q6(
        moving_mesh, fixed.coke_center, q_contact, opening_axis
    )
    preopen_width = float(
        np.dot(preopen_hit.point - fixed.contact_point, opening_axis)
    )
    contact_width = float(
        np.dot(contact_hit.point - fixed.contact_point, opening_axis)
    )
    preopen_inward_dot = float(np.dot(preopen_hit.normal, -opening_axis))
    contact_inward_dot = float(np.dot(contact_hit.normal, -opening_axis))

    if q_contact >= q_preopen:
        raise ValueError('Expected q_contact to be more closed than q_preopen')
    if preopen_inward_dot <= 0.0 or contact_inward_dot <= 0.0:
        raise ValueError('Moving-jaw contact face does not point into the gap')

    return GripperTargets(
        grasp_depth,
        fixed.section_z,
        fixed.contact_point,
        fixed.coke_center,
        q_preopen,
        q_contact,
        preopen_width,
        contact_width,
        fixed.inward_dot,
        preopen_inward_dot,
        contact_inward_dot,
    )


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _width_geometry(
    mesh_dir: Path,
    grasp_depth: float,
    task_object_diameter: float,
) -> tuple[TriangleMesh, FixedContactGeometry]:
    if task_object_diameter <= 0.0:
        raise ValueError('task_object_diameter must be positive')
    fixed_mesh = load_mesh_in_link_frame(
        mesh_dir / 'wrist_roll_follower_so101_v1.stl',
        FIXED_VISUAL_XYZ,
        FIXED_VISUAL_RPY,
    )
    moving_mesh = load_mesh_in_link_frame(
        mesh_dir / 'moving_jaw_so101_v1.stl',
        MOVING_VISUAL_XYZ,
        MOVING_VISUAL_RPY,
    )
    fixed = fixed_contact_geometry(
        fixed_mesh,
        grasp_depth,
        task_object_diameter / 2.0,
        OPENING_AXIS_GRIPPER,
    )
    return moving_mesh, fixed


def gripper_width_at_q6(
    mesh_dir: Path,
    grasp_depth: float,
    task_object_diameter: float,
    q6: float,
) -> float:
    """Evaluate the real STL ray-intersection width at one q6 value."""
    moving_mesh, fixed = _width_geometry(mesh_dir, grasp_depth, task_object_diameter)
    hit = moving_contact_at_q6(
        moving_mesh, fixed.coke_center, q6, OPENING_AXIS_GRIPPER
    )
    return float(
        np.dot(hit.point - fixed.contact_point, OPENING_AXIS_GRIPPER)
    )


def calculate_width_calibration(
    mesh_dir: Path,
    urdf_path: Path,
    grasp_depth: float,
    task_object_diameter: float,
    q_min: float,
    q_max: float,
    sample_count: int,
) -> WidthCalibration:
    """Generate a fingerprinted dense q6/width table from the real STL meshes."""
    if not (math.isfinite(q_min) and math.isfinite(q_max) and q_min < q_max):
        raise ValueError('q_min and q_max must form a finite increasing range')
    if sample_count < 2:
        raise ValueError('sample_count must be at least two')
    moving_mesh, fixed = _width_geometry(mesh_dir, grasp_depth, task_object_diameter)
    samples = []
    for q6 in np.linspace(q_min, q_max, sample_count):
        q6 = float(q6)
        hit = moving_contact_at_q6(
            moving_mesh, fixed.coke_center, q6, OPENING_AXIS_GRIPPER
        )
        width = float(
            np.dot(hit.point - fixed.contact_point, OPENING_AXIS_GRIPPER)
        )
        samples.append((q6, width))

    fixed_sha = _sha256_file(
        mesh_dir / 'wrist_roll_follower_so101_v1.stl'
    )
    moving_sha = _sha256_file(mesh_dir / 'moving_jaw_so101_v1.stl')
    urdf_sha = _sha256_file(urdf_path)
    constants_sha = hashlib.sha256(
        GEOMETRY_CONSTANTS_CANONICAL.encode('utf-8')
    ).hexdigest()
    fingerprint_payload = (
        f'version={GEOMETRY_MODEL_VERSION}\n'
        f'fixed_mesh_sha256={fixed_sha}\n'
        f'moving_mesh_sha256={moving_sha}\n'
        f'urdf_sha256={urdf_sha}\n'
        f'constants_sha256={constants_sha}\n'
        f'grasp_depth={grasp_depth:.12f}\n'
        f'task_object_diameter={task_object_diameter:.12f}\n'
    )
    model_fingerprint = hashlib.sha256(
        fingerprint_payload.encode('utf-8')
    ).hexdigest()
    return WidthCalibration(
        GEOMETRY_MODEL_VERSION,
        fixed_sha,
        moving_sha,
        urdf_sha,
        constants_sha,
        model_fingerprint,
        grasp_depth,
        task_object_diameter,
        tuple(samples),
    )


def render_width_calibration_header(calibration: WidthCalibration) -> str:
    """Render the deterministic C++ table consumed by the runtime validator."""
    lines = [
        '#pragma once',
        '',
        '// DO NOT EDIT: generated from the real SO-101 STL meshes by:',
        '// python3 scripts/gripper_preopen_calc.py --mesh-dir meshes/so101 \\',
        '//   --urdf-path urdf/so101_base.xacro --print-calibration-header \\',
        f'//   --calibration-q-min {calibration.samples[0][0]:.9f} '
        f'--calibration-q-max {calibration.samples[-1][0]:.9f} \\',
        f'//   --calibration-samples {len(calibration.samples)}',
        '',
        '#include <array>',
        '#include <string_view>',
        '',
        'namespace so101_gazebo_demo::pick_place::gripper_calibration',
        '{',
        '',
        'struct CalibrationSample',
        '{',
        '  double q6;',
        '  double width;',
        '};',
        '',
        f'inline constexpr std::string_view kModelVersion{{"{calibration.model_version}"}};',
        f'inline constexpr std::string_view kFixedMeshSha256{{"{calibration.fixed_mesh_sha256}"}};',
        f'inline constexpr std::string_view kMovingMeshSha256{{"{calibration.moving_mesh_sha256}"}};',
        f'inline constexpr std::string_view kUrdfSha256{{"{calibration.urdf_sha256}"}};',
        f'inline constexpr std::string_view kConstantsSha256{{"{calibration.constants_sha256}"}};',
        f'inline constexpr std::string_view kModelFingerprint{{"{calibration.model_fingerprint}"}};',
        f'inline constexpr double kGraspDepth{{{calibration.grasp_depth:.12f}}};',
        f'inline constexpr double kTaskObjectDiameter{{{calibration.task_object_diameter:.12f}}};',
        f'inline constexpr std::array<CalibrationSample, {len(calibration.samples)}> kSamples{{{{',
    ]
    lines.extend(
        f'  CalibrationSample{{{q6:.12f}, {width:.12f}}},'
        for q6, width in calibration.samples
    )
    lines.extend([
        '}};',
        '',
        '}  // namespace so101_gazebo_demo::pick_place::gripper_calibration',
        '',
    ])
    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='SO-101 task-object gripper angle calculator at a fixed depth'
    )
    parser.add_argument(
        '--mesh-dir',
        type=Path,
        default=default_mesh_dir(),
        help='Directory containing SO-101 STL files',
    )
    parser.add_argument(
        '--grasp-depth-mm',
        type=float,
        default=20.0,
        help='Contact section depth from the fixed inner-face tip (default: 20 mm)',
    )
    parser.add_argument(
        '--task-object-diameter-mm',
        type=float,
        default=66.0,
        help='Task-object diameter (default: 66 mm)',
    )
    parser.add_argument(
        '--preopen-clearance-mm',
        type=float,
        default=4.0,
        help='Clearance placed entirely on the moving-jaw side (default: 4 mm)',
    )
    parser.add_argument(
        '--urdf-path', type=Path, default=default_urdf_path(),
        help='Geometry-bearing SO-101 xacro used for fingerprinting',
    )
    parser.add_argument('--print-calibration-header', action='store_true')
    parser.add_argument('--calibration-q-min', type=float, default=0.660818811)
    parser.add_argument('--calibration-q-max', type=float, default=0.709194871)
    parser.add_argument('--calibration-samples', type=int, default=49)
    args = parser.parse_args()

    try:
        result = calculate_gripper_targets(
            mesh_dir=args.mesh_dir,
            grasp_depth=args.grasp_depth_mm / 1000.0,
            task_object_diameter=args.task_object_diameter_mm / 1000.0,
            preopen_clearance=args.preopen_clearance_mm / 1000.0,
        )
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc

    if args.print_calibration_header:
        try:
            calibration = calculate_width_calibration(
                mesh_dir=args.mesh_dir,
                urdf_path=args.urdf_path,
                grasp_depth=args.grasp_depth_mm / 1000.0,
                task_object_diameter=args.task_object_diameter_mm / 1000.0,
                q_min=args.calibration_q_min,
                q_max=args.calibration_q_max,
                sample_count=args.calibration_samples,
            )
        except (OSError, ValueError) as exc:
            print(f'ERROR: {exc}', file=sys.stderr)
            raise SystemExit(1) from exc
        print(render_width_calibration_header(calibration), end='')
        return

    print('SO-101 Coke grasp geometry')
    print(f'  grasp depth d:       {result.grasp_depth * 1000:.2f} mm')
    print(f'  section z in gripper:{result.section_z * 1000:9.3f} mm')
    print(
        '  fixed contact point: '
        f'[{result.fixed_contact_point[0] * 1000:.3f}, '
        f'{result.fixed_contact_point[1] * 1000:.3f}, '
        f'{result.fixed_contact_point[2] * 1000:.3f}] mm'
    )
    print(
        '  Coke centre in G:    '
        f'[{result.coke_center[0] * 1000:.3f}, '
        f'{result.coke_center[1] * 1000:.3f}, '
        f'{result.coke_center[2] * 1000:.3f}] mm'
    )
    print()
    print('=' * 64)
    print(
        f'  q_preopen = {math.degrees(result.q_preopen):.6f} deg  '
        f'({result.q_preopen:.9f} rad), width={result.preopen_width * 1000:.6f} mm'
    )
    print(
        f'  q_contact = {math.degrees(result.q_contact):.6f} deg  '
        f'({result.q_contact:.9f} rad), width={result.contact_width * 1000:.6f} mm'
    )
    print(
        '  inward-normal dots: '
        f'fixed={result.fixed_inward_dot:.6f}, '
        f'preopen={result.preopen_moving_inward_dot:.6f}, '
        f'contact={result.contact_moving_inward_dot:.6f}'
    )
    print('=' * 64)


# ---------------------------------------------------------------------------
# Native fingertip-pad clearance calibration
# ---------------------------------------------------------------------------

class FingertipPadUrdfTransforms(NamedTuple):
    j6_xyz: np.ndarray
    j6_rpy: np.ndarray
    fixed_visual_xyz: np.ndarray
    fixed_visual_rpy: np.ndarray
    moving_visual_xyz: np.ndarray
    moving_visual_rpy: np.ndarray


def _parse_xyz_rpy(origin: ET.Element, context: str) -> tuple[np.ndarray, np.ndarray]:
    try:
        xyz = np.fromstring(origin.attrib['xyz'], sep=' ', dtype=float)
        rpy = np.fromstring(origin.attrib['rpy'], sep=' ', dtype=float)
    except KeyError as error:
        raise ValueError(f'{context} is missing xyz or rpy') from error
    if xyz.shape != (3,) or rpy.shape != (3,) or not np.all(np.isfinite(np.r_[xyz, rpy])):
        raise ValueError(f'{context} has invalid xyz/rpy')
    return xyz, rpy


def parse_fingertip_pad_urdf_transforms(urdf_path: Path) -> FingertipPadUrdfTransforms:
    """Parse the actual xacro source values used by the pad kinematic model."""
    root = ET.parse(urdf_path).getroot()
    joint = root.find("./joint[@name='6']/origin")
    if joint is None:
        raise ValueError('URDF is missing joint 6 origin')
    j6_xyz, j6_rpy = _parse_xyz_rpy(joint, 'joint 6 origin')

    def visual_transform(link_name: str, mesh_suffix: str):
        link = root.find(f"./link[@name='{link_name}']")
        if link is None:
            raise ValueError(f'URDF is missing {link_name} link')
        for visual in link.findall('./visual'):
            mesh = visual.find('./geometry/mesh')
            if mesh is not None and mesh.attrib.get('filename', '').endswith(mesh_suffix):
                origin = visual.find('./origin')
                if origin is None:
                    raise ValueError(f'URDF {mesh_suffix} visual is missing origin')
                return _parse_xyz_rpy(origin, f'{mesh_suffix} visual origin')
        raise ValueError(f'URDF is missing {mesh_suffix} visual')

    fixed_xyz, fixed_rpy = visual_transform('gripper', 'wrist_roll_follower_so101_v1.stl')
    moving_xyz, moving_rpy = visual_transform('jaw', 'moving_jaw_so101_v1.stl')
    return FingertipPadUrdfTransforms(
        j6_xyz, j6_rpy, fixed_xyz, fixed_rpy, moving_xyz, moving_rpy
    )


def _jaw_transform_from_urdf(q6: float, j6_xyz: np.ndarray, j6_rpy: np.ndarray) -> np.ndarray:
    joint_rotation = np.eye(4)
    joint_rotation[:3, :3] = rot_z(q6)
    return make_transform(j6_xyz, j6_rpy) @ joint_rotation

def _contact_face_triangles(mesh: TriangleMesh, contact_direction_x: float) -> np.ndarray:
    """Select the generated mesh's planar pad contact faces in link coordinates."""
    direction = np.array([contact_direction_x, 0.0, 0.0])
    mask = mesh.face_normals @ direction > 0.999999
    triangles = mesh.triangles[mask]
    if len(triangles) == 0:
        raise ValueError('generated fingertip pad has no identifiable contact faces')
    return triangles


def _signed_area_2d(polygon: np.ndarray) -> float:
    return float(np.sum(
        polygon[:, 0] * np.roll(polygon[:, 1], -1) -
        polygon[:, 1] * np.roll(polygon[:, 0], -1)
    ) / 2.0)


def _clip_convex_polygon(subject: np.ndarray, clip: np.ndarray) -> np.ndarray:
    """Intersect two convex yz polygons using deterministic Sutherland-Hodgman clipping."""
    if len(subject) == 0:
        return subject
    orientation = 1.0 if _signed_area_2d(clip) >= 0.0 else -1.0
    output = subject
    for index, start in enumerate(clip):
        end = clip[(index + 1) % len(clip)]
        edge = end - start
        input_polygon = output
        output = []
        if len(input_polygon) == 0:
            break
        previous = input_polygon[-1]
        previous_side = orientation * np.cross(edge, previous - start)
        for current in input_polygon:
            current_side = orientation * np.cross(edge, current - start)
            current_inside = current_side >= -1e-12
            previous_inside = previous_side >= -1e-12
            if current_inside != previous_inside:
                denominator = previous_side - current_side
                if abs(denominator) > 1e-15:
                    ratio = previous_side / denominator
                    output.append(previous + ratio * (current - previous))
            if current_inside:
                output.append(current)
            previous = current
            previous_side = current_side
        output = np.asarray(output, dtype=float)
    return np.asarray(output, dtype=float)


def _x_on_triangle_at_yz(triangle: np.ndarray, yz: np.ndarray) -> float:
    first, second, third = triangle
    normal = np.cross(second - first, third - first)
    if abs(normal[0]) <= 1e-12:
        raise ValueError('pad contact face is not an opening-axis graph')
    return float(first[0] - (normal[1] * (yz[0] - first[1]) +
                             normal[2] * (yz[1] - first[2])) / normal[0])


def fingertip_pad_opening_axis_min_gap(
    fixed_contact_triangles: np.ndarray,
    moving_contact_triangles_jaw: np.ndarray,
    q6: float,
    j6_xyz: np.ndarray,
    j6_rpy: np.ndarray,
) -> float:
    """Return the exact minimum x gap over projected, physically overlapping contact faces.

    Each generated contact face is triangular and affine in `(y, z)`.  For every
    pair, clipping their yz projections yields the true overlap polygon; a
    linear x-gap reaches its minimum at a polygon vertex.  This avoids an
    empirical slope or a sampling-dependent closest-point approximation.
    """
    if not math.isfinite(q6) or not J6_LOWER <= q6 <= J6_UPPER:
        raise ValueError('fingertip-pad gap q6 must be finite and within joint limits')
    transform = _jaw_transform_from_urdf(q6, j6_xyz, j6_rpy)
    moving = (
        moving_contact_triangles_jaw.reshape(-1, 3) @ transform[:3, :3].T +
        transform[:3, 3]
    ).reshape(-1, 3, 3)
    minimum = math.inf
    for fixed_triangle in fixed_contact_triangles:
        fixed_yz = fixed_triangle[:, 1:3]
        for moving_triangle in moving:
            overlap = _clip_convex_polygon(moving_triangle[:, 1:3], fixed_yz)
            if len(overlap) == 0:
                continue
            for yz in overlap:
                gap = _x_on_triangle_at_yz(moving_triangle, yz) - \
                    _x_on_triangle_at_yz(fixed_triangle, yz)
                minimum = min(minimum, gap)
    if not math.isfinite(minimum):
        raise ValueError('native fingertip pads have no projected contact overlap')
    return minimum


def _find_q6_for_fingertip_pad_gap(
    fixed_contact_triangles: np.ndarray,
    moving_contact_triangles_jaw: np.ndarray,
    target_gap_m: float,
    *,
    q_lo: float = -0.16,
    q_hi: float = 0.20,
    j6_xyz: np.ndarray,
    j6_rpy: np.ndarray,
) -> float:
    if target_gap_m <= 0.0:
        raise ValueError('target pad gap must be positive')
    low_gap = fingertip_pad_opening_axis_min_gap(
        fixed_contact_triangles, moving_contact_triangles_jaw, q_lo, j6_xyz, j6_rpy
    )
    high_gap = fingertip_pad_opening_axis_min_gap(
        fixed_contact_triangles, moving_contact_triangles_jaw, q_hi, j6_xyz, j6_rpy
    )
    if not low_gap < target_gap_m < high_gap:
        raise ValueError('target pad gap is outside the monotonic calibration bracket')
    lower, upper = q_lo, q_hi
    for _ in range(80):
        middle = (lower + upper) / 2.0
        if fingertip_pad_opening_axis_min_gap(
                fixed_contact_triangles, moving_contact_triangles_jaw, middle, j6_xyz, j6_rpy) < target_gap_m:
            lower = middle
        else:
            upper = middle
    return upper


def calculate_fingertip_pad_gap_calibration(
    config_path: Path,
    asset_root: Path,
    urdf_path: Path,
) -> FingertipPadGapCalibration:
    """Bind q6 floor/grasp clearance to profile, generated assets, and URDF transforms."""
    policy = yaml.safe_load(config_path.read_text(encoding='utf-8'))
    pads = policy['fingertip_pads']
    fixed = asset_root / 'fixed'
    moving = asset_root / 'moving'
    fixed_visual = fixed / 'fingertip_pad.stl'
    moving_visual = moving / 'fingertip_pad.stl'
    fixed_collisions = sorted(fixed.glob('fingertip_pad_collision_*.stl'))
    moving_collisions = sorted(moving.glob('fingertip_pad_collision_*.stl'))
    if len(fixed_collisions) != 7 or len(moving_collisions) != 6:
        raise ValueError('generated fingertip-pad collision asset count is not canonical')
    transforms = parse_fingertip_pad_urdf_transforms(urdf_path)
    fixed_manifest = yaml.safe_load((fixed / 'manifest.yaml').read_text(encoding='utf-8'))
    moving_manifest = yaml.safe_load((moving / 'manifest.yaml').read_text(encoding='utf-8'))
    for name, pad, manifest, visual, collisions in (
        ('fixed', pads['fixed_pad'], fixed_manifest, fixed_visual, fixed_collisions),
        ('moving', pads['moving_pad'], moving_manifest, moving_visual, moving_collisions),
    ):
        profile_fingerprint = hashlib.sha256(
            yaml.safe_dump(pad, sort_keys=True).encode('utf-8')
        ).hexdigest()
        if manifest.get('profile_fingerprint') != profile_fingerprint:
            raise ValueError(f'{name} fingertip-pad assets do not match the configured profile')
        if manifest.get('visual_mesh_sha256') != _sha256_file(visual):
            raise ValueError(f'{name} fingertip-pad visual mesh checksum does not match its manifest')
        if manifest.get('collision_mesh_sha256') != [_sha256_file(path) for path in collisions]:
            raise ValueError(f'{name} fingertip-pad collision mesh checksums do not match its manifest')
    fixed_mesh = load_mesh_in_link_frame(
        fixed_visual, transforms.fixed_visual_xyz, transforms.fixed_visual_rpy
    )
    moving_mesh = load_mesh_in_link_frame(
        moving_visual, transforms.moving_visual_xyz, transforms.moving_visual_rpy
    )
    fixed_faces = _contact_face_triangles(fixed_mesh, 1.0)
    moving_faces = _contact_face_triangles(moving_mesh, -1.0)
    fixed_sha = _sha256_file(fixed_visual)
    moving_sha = _sha256_file(moving_visual)
    fixed_collision_sha = hashlib.sha256(
        ''.join(_sha256_file(path) + '\n' for path in fixed_collisions).encode('utf-8')).hexdigest()
    moving_collision_sha = hashlib.sha256(
        ''.join(_sha256_file(path) + '\n' for path in moving_collisions).encode('utf-8')).hexdigest()
    urdf_sha = _sha256_file(urdf_path)
    profile_canonical = yaml.safe_dump(
        {'fixed_pad': pads['fixed_pad'], 'moving_pad': pads['moving_pad']}, sort_keys=True
    )
    fingerprint = hashlib.sha256(
        (profile_canonical +
         f'fixed_visual_mesh_sha256={fixed_sha}\n'
         f'moving_visual_mesh_sha256={moving_sha}\n'
         f'fixed_collision_mesh_sha256={fixed_collision_sha}\n'
         f'moving_collision_mesh_sha256={moving_collision_sha}\n'
         f'urdf_sha256={urdf_sha}\n'
         f'J6_XYZ={transforms.j6_xyz.tolist()}\nJ6_RPY={transforms.j6_rpy.tolist()}\n'
         f'FIXED_VISUAL_XYZ={transforms.fixed_visual_xyz.tolist()}\n'
         f'FIXED_VISUAL_RPY={transforms.fixed_visual_rpy.tolist()}\n'
         f'MOVING_VISUAL_XYZ={transforms.moving_visual_xyz.tolist()}\n'
         f'MOVING_VISUAL_RPY={transforms.moving_visual_rpy.tolist()}\n').encode('utf-8')
    ).hexdigest()
    safe_q6 = _find_q6_for_fingertip_pad_gap(
        fixed_faces, moving_faces, 0.001, j6_xyz=transforms.j6_xyz, j6_rpy=transforms.j6_rpy
    )
    grasp_gap_m = float(pads['grasp_gap_m'])
    grasp_q6 = _find_q6_for_fingertip_pad_gap(
        fixed_faces, moving_faces, grasp_gap_m,
        j6_xyz=transforms.j6_xyz, j6_rpy=transforms.j6_rpy,
    )
    preopen_q6 = float(policy.get('gripper_actions', {}).get('preopen_q6', 0.465038))
    # Motion policy is separate; use the retained conservative open command.
    preopen_q6 = 0.465038
    preopen_gap = fingertip_pad_opening_axis_min_gap(
        fixed_faces, moving_faces, preopen_q6, transforms.j6_xyz, transforms.j6_rpy
    )
    # The table is a generated lookup of the same triangle-overlap calculation
    # used for the roots.  It spans the small controller endpoint allowance below
    # the safe floor and the configured position tolerance above preopen; the three
    # semantic roots are inserted exactly so runtime evaluation never rounds them
    # into an adjacent interpolation segment.
    controller_endpoint_epsilon_rad = 0.0001
    runtime_position_tolerance_rad = 0.001
    table_low = safe_q6 - controller_endpoint_epsilon_rad
    table_high = preopen_q6 + runtime_position_tolerance_rad
    uniform_count = 129
    table_q6 = {
        table_low + (table_high - table_low) * index / (uniform_count - 1)
        for index in range(uniform_count)
    }
    table_q6.update((safe_q6, grasp_q6, preopen_q6))
    gap_samples = tuple(
        (q6, fingertip_pad_opening_axis_min_gap(
            fixed_faces, moving_faces, q6, transforms.j6_xyz, transforms.j6_rpy))
        for q6 in sorted(table_q6)
    )
    return FingertipPadGapCalibration(
        safe_q6, grasp_q6, preopen_q6,
        fingertip_pad_opening_axis_min_gap(
            fixed_faces, moving_faces, safe_q6, transforms.j6_xyz, transforms.j6_rpy),
        fingertip_pad_opening_axis_min_gap(
            fixed_faces, moving_faces, grasp_q6, transforms.j6_xyz, transforms.j6_rpy),
        preopen_gap, max(0.0, float(policy['model']['wall_thickness_m']) -
        fingertip_pad_opening_axis_min_gap(
            fixed_faces, moving_faces, grasp_q6, transforms.j6_xyz, transforms.j6_rpy)),
        controller_endpoint_epsilon_rad, gap_samples,
        fingerprint, fixed_sha, moving_sha, fixed_collision_sha, moving_collision_sha, urdf_sha,
        transforms.j6_xyz, transforms.j6_rpy, fixed_faces, moving_faces,
    )


def render_fingertip_pad_gap_calibration_header(
    calibration: FingertipPadGapCalibration,
) -> str:
    """Render the checked-in C++ artifact consumed by native-pad runtime gates."""
    sample_lines = '\n'.join(
        '  ' + ', '.join(
            f'{{{q6:.15f}, {gap:.15f}}}'
            for q6, gap in calibration.gap_samples[index:index + 2]
        ) + ','
        for index in range(0, len(calibration.gap_samples), 2)
    )
    return f'''#pragma once

// DO NOT EDIT: generated by gripper_preopen_calc.py from native fingertip-pad
// profile points, generated visual/collision mesh assets, and so101_base.xacro.

#include <array>
#include <string_view>

namespace so101_gazebo_demo::pick_place::fingertip_pad_calibration
{{
inline constexpr std::string_view kInputFingerprint{{"{calibration.input_fingerprint}"}};
inline constexpr std::string_view kFixedVisualMeshSha256{{"{calibration.fixed_visual_mesh_sha256}"}};
inline constexpr std::string_view kMovingVisualMeshSha256{{"{calibration.moving_visual_mesh_sha256}"}};
inline constexpr std::string_view kFixedCollisionMeshSha256{{"{calibration.fixed_collision_mesh_sha256}"}};
inline constexpr std::string_view kMovingCollisionMeshSha256{{"{calibration.moving_collision_mesh_sha256}"}};
inline constexpr std::string_view kUrdfSha256{{"{calibration.urdf_sha256}"}};
inline constexpr double kSafeFloorQ6{{{calibration.safe_floor_q6:.15f}}};
inline constexpr double kGraspQ6{{{calibration.grasp_q6:.15f}}};
inline constexpr double kPreopenQ6{{{calibration.preopen_q6:.15f}}};
inline constexpr double kSafeFloorGapM{{{calibration.safe_floor_gap_m:.15f}}};
inline constexpr double kGraspGapM{{{calibration.grasp_gap_m:.15f}}};
inline constexpr double kPreopenGapM{{{calibration.preopen_gap_m:.15f}}};
inline constexpr double kCupWallInterferenceM{{{calibration.cup_wall_interference_m:.15f}}};
inline constexpr double kControllerEndpointEpsilonRad{{{calibration.controller_endpoint_epsilon_rad:.15f}}};
struct GapSample {{ double q6; double minimum_pad_gap_m; }};
inline constexpr std::array<GapSample, {len(calibration.gap_samples)}> kGapSamples{{{{
{sample_lines}
}}}};
}}  // namespace so101_gazebo_demo::pick_place::fingertip_pad_calibration
'''


if __name__ == '__main__':
    main()
