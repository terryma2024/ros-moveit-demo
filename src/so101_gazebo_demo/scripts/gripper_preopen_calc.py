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
import math
from pathlib import Path
import sys
from typing import NamedTuple

import numpy as np
import trimesh
from ament_index_python.packages import get_package_share_directory


def default_mesh_dir() -> Path:
    """Return the installed package's SO-101 mesh directory."""
    return (
        Path(get_package_share_directory('so101_gazebo_demo'))
        / 'meshes'
        / 'so101'
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
DEFAULT_COKE_DIAMETER = 0.066
DEFAULT_PREOPEN_CLEARANCE = 0.004


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
) -> trimesh.Trimesh:
    mesh = trimesh.load(str(stl_path), force='mesh')
    mesh.apply_transform(make_transform(visual_xyz, visual_rpy))
    return mesh


# ---------------------------------------------------------------------------
# Deterministic contact geometry
# ---------------------------------------------------------------------------

def _unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 1e-12:
        raise ValueError('Direction vector must be non-zero')
    return np.asarray(vector, dtype=float) / norm


def ray_mesh_first_hit(
    mesh: trimesh.Trimesh,
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
    fixed_mesh: trimesh.Trimesh,
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
    moving_mesh_jaw: trimesh.Trimesh,
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
    moving_mesh_jaw: trimesh.Trimesh,
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
    coke_diameter: float = DEFAULT_COKE_DIAMETER,
    preopen_clearance: float = DEFAULT_PREOPEN_CLEARANCE,
) -> GripperTargets:
    """Calculate q_preopen and q_contact for the configured Coke geometry."""
    if coke_diameter <= 0.0:
        raise ValueError('coke_diameter must be positive')
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
    coke_radius = coke_diameter / 2.0
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description='SO-101 Coke gripper angle calculator at a fixed depth'
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
        '--coke-diameter-mm',
        type=float,
        default=66.0,
        help='Coke diameter (default: 66 mm)',
    )
    parser.add_argument(
        '--preopen-clearance-mm',
        type=float,
        default=4.0,
        help='Clearance placed entirely on the moving-jaw side (default: 4 mm)',
    )
    args = parser.parse_args()

    try:
        result = calculate_gripper_targets(
            mesh_dir=args.mesh_dir,
            grasp_depth=args.grasp_depth_mm / 1000.0,
            coke_diameter=args.coke_diameter_mm / 1000.0,
            preopen_clearance=args.preopen_clearance_mm / 1000.0,
        )
    except (OSError, ValueError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise SystemExit(1) from exc

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


if __name__ == '__main__':
    main()
