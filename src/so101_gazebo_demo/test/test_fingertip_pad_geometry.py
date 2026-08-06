"""Native-fingertip TPU-pad geometry contracts.

The source STL coordinate frames are deliberately retained: the xacro applies the
same visual origin as the corresponding original finger.  This makes the pad
envelopes auditable against the Blender measurements without editing either
original visual mesh or its cached VHACD set.
"""

from __future__ import annotations

import importlib.util
import itertools
import math
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

from ament_index_python.packages import get_package_share_directory
import numpy as np
import pytest
from scipy.optimize import least_squares
import yaml


PACKAGE_DIR = Path(__file__).resolve().parents[1]
CONFIG_PATH = PACKAGE_DIR / 'config' / 'task_objects' / 'light_plastic_cup.yaml'
XACRO_PATH = PACKAGE_DIR / 'urdf' / 'so101.urdf.xacro'
GENERATOR_PATH = PACKAGE_DIR / 'scripts' / 'generate_fingertip_pad_meshes.py'
CALCULATOR_PATH = PACKAGE_DIR / 'scripts' / 'gripper_preopen_calc.py'
WORLD_PATH = PACKAGE_DIR / 'worlds' / 'so101_pick_place.sdf'
MOTION_PATH = PACKAGE_DIR / 'config' / 'motion_policies' / 'light_cup_wall_pick.yaml'
VALIDATION_PATH = PACKAGE_DIR / 'config' / 'validation_policies' / 'light_cup_wall_pick.yaml'
BUILD_ASSET_ROOT = PACKAGE_DIR.parents[1] / 'build' / 'so101_gazebo_demo' / 'fingertip_pad_assets'


MOVING_POINTS = (
    (-0.0815, 0.0036, -0.01230),
    (-0.0780, 0.0045, -0.01230),
    (-0.0730, 0.0054, -0.01230),
    (-0.0722, 0.0057, -0.0123232903),
    (-0.0718, 0.0058, -0.01030),
    (-0.0670, 0.0060, -0.01030),
    (-0.0625, 0.0060, -0.01030),
)
FIXED_POINTS = (
    (0.06622, 0.00720, -0.01160),
    (0.07500, 0.00715, -0.01160),
    (0.084875, 0.00680, -0.01160),
    (0.085875, 0.00580, -0.00990),
    (0.094875, 0.00545, -0.00990),
    (0.095875, 0.00490, -0.00790),
    (0.10000, 0.00410, -0.00790),
    (0.104875, 0.00145, -0.00790),
)


def _policy():
    return yaml.safe_load(CONFIG_PATH.read_text())


def _robot(*mappings: str) -> ET.Element:
    completed = subprocess.run(
        ['xacro', str(XACRO_PATH), *mappings],
        check=True,
        text=True,
        capture_output=True,
    )
    return ET.fromstring(completed.stdout)


def _load_generator():
    assert GENERATOR_PATH.exists(), 'deterministic fingertip-pad mesh generator is missing'
    spec = importlib.util.spec_from_file_location('fingertip_pad_generator', GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_calculator():
    spec = importlib.util.spec_from_file_location('fingertip_pad_calculator', CALCULATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _points(pad):
    return tuple(tuple(point) for point in pad['profile_points'])


def _xyz_rpy(origin):
    return (
        np.fromstring(origin.attrib.get('xyz', '0 0 0'), sep=' '),
        np.fromstring(origin.attrib.get('rpy', '0 0 0'), sep=' '),
    )


def _joint_transform(calculator, joint, position=0.0):
    xyz, rpy = _xyz_rpy(joint.find('origin'))
    transform = calculator.make_transform(xyz, rpy)
    if joint.attrib['type'] == 'fixed':
        return transform
    axis = np.fromstring(joint.find('axis').attrib.get('xyz', '0 0 1'), sep=' ')
    axis /= np.linalg.norm(axis)
    x, y, z = axis
    cosine, sine = math.cos(position), math.sin(position)
    one_minus_cosine = 1.0 - cosine
    rotation = np.eye(4)
    rotation[:3, :3] = np.array([
        [cosine + x * x * one_minus_cosine, x * y * one_minus_cosine - z * sine,
         x * z * one_minus_cosine + y * sine],
        [y * x * one_minus_cosine + z * sine, cosine + y * y * one_minus_cosine,
         y * z * one_minus_cosine - x * sine],
        [z * x * one_minus_cosine - y * sine, z * y * one_minus_cosine + x * sine,
         cosine + z * z * one_minus_cosine],
    ])
    return transform @ rotation


def _descend_gripper_transform(calculator, robot):
    joints = {
        joint.attrib['name']: joint
        for joint in robot.findall('joint')
        if joint.attrib.get('type') in ('fixed', 'revolute', 'continuous')
        and joint.find('parent') is not None
    }
    motion = yaml.safe_load(
        (PACKAGE_DIR / 'config' / 'motion_policies' / 'light_cup_wall_pick.yaml').read_text()
    )
    transform = _joint_transform(calculator, joints['base_joint'])
    for number, position in enumerate(motion['states']['DESCEND']['waypoints'][-1], start=1):
        transform = transform @ _joint_transform(calculator, joints[str(number)], position)
    return transform, joints


def _pad_collision_meshes(calculator, robot, link_name, name_prefix, side):
    link = robot.find(f"./link[@name='{link_name}']")
    assert link is not None
    meshes = []
    for collision in link.findall('collision'):
        name = collision.attrib.get('name', '')
        if not name.startswith(name_prefix):
            continue
        index = name.rsplit('_', 1)[1]
        xyz, rpy = _xyz_rpy(collision.find('origin'))
        meshes.append(
            calculator.load_mesh_in_link_frame(
                BUILD_ASSET_ROOT / side / f'fingertip_pad_collision_{index}.stl', xyz, rpy
            )
        )
    assert meshes
    return meshes


def _cup_wall_boxes(calculator, policy):
    root = ET.parse(WORLD_PATH).getroot()
    cup = next(model for model in root.findall('.//model') if model.attrib['name'] == 'plastic_cup')
    cup_transform = np.eye(4)
    cup_transform[:3, 3] = policy['scene']['spawn_pose_xyz_xyzw'][:3]
    walls = []
    for collision in cup.find('link').findall('collision'):
        box = collision.find('./geometry/box')
        if box is None:
            continue
        pose = np.fromstring(collision.findtext('pose'), sep=' ')
        walls.append((
            collision.attrib['name'],
            cup_transform @ calculator.make_transform(pose[:3], pose[3:]),
            np.fromstring(box.findtext('size'), sep=' ') / 2.0,
        ))
    assert len(walls) == 12
    return walls


_BOX_EDGES = ((0, 1), (0, 2), (0, 4), (1, 3), (1, 5), (2, 3),
              (2, 6), (3, 7), (4, 5), (4, 6), (5, 7), (6, 7))


def _point_to_triangle_distance(point, triangle):
    first, second, third = triangle
    edge1, edge2 = second - first, third - first
    point_from_first = point - first
    dot11, dot12 = edge1 @ point_from_first, edge2 @ point_from_first
    if dot11 <= 0.0 and dot12 <= 0.0:
        return np.linalg.norm(point_from_first)
    point_from_second = point - second
    dot21, dot22 = edge1 @ point_from_second, edge2 @ point_from_second
    if dot21 >= 0.0 and dot22 <= dot21:
        return np.linalg.norm(point_from_second)
    edge12 = dot11 * dot22 - dot21 * dot12
    if edge12 <= 0.0 and dot11 >= 0.0 and dot21 <= 0.0:
        return np.linalg.norm(point - (first + dot11 / (dot11 - dot21) * edge1))
    point_from_third = point - third
    dot31, dot32 = edge1 @ point_from_third, edge2 @ point_from_third
    if dot32 >= 0.0 and dot31 <= dot32:
        return np.linalg.norm(point_from_third)
    edge31 = dot31 * dot12 - dot11 * dot32
    if edge31 <= 0.0 and dot12 >= 0.0 and dot32 <= 0.0:
        return np.linalg.norm(point - (first + dot12 / (dot12 - dot32) * edge2))
    edge23 = dot21 * dot32 - dot31 * dot22
    if edge23 <= 0.0 and dot22 - dot21 >= 0.0 and dot31 - dot32 >= 0.0:
        return np.linalg.norm(point - (second + (dot22 - dot21) /
                                       (dot22 - dot21 + dot31 - dot32) * (third - second)))
    barycentric_denominator = 1.0 / (edge12 + edge31 + edge23)
    return np.linalg.norm(point - (first + edge1 * edge31 * barycentric_denominator +
                                   edge2 * edge23 * barycentric_denominator))


def _segment_distance(first0, first1, second0, second1):
    direction1, direction2 = first1 - first0, second1 - second0
    offset = first0 - second0
    aa, ee, ff = direction1 @ direction1, direction2 @ direction2, direction2 @ offset
    if aa <= 1e-15 and ee <= 1e-15:
        return np.linalg.norm(offset)
    if aa <= 1e-15:
        first_fraction, second_fraction = 0.0, np.clip(ff / ee, 0.0, 1.0)
    else:
        cc = direction1 @ offset
        if ee <= 1e-15:
            first_fraction, second_fraction = np.clip(-cc / aa, 0.0, 1.0), 0.0
        else:
            bb = direction1 @ direction2
            denominator = aa * ee - bb * bb
            first_fraction = np.clip((bb * ff - cc * ee) / denominator, 0.0, 1.0) \
                if abs(denominator) > 1e-15 else 0.0
            second_fraction = (bb * first_fraction + ff) / ee
            if second_fraction < 0.0:
                second_fraction, first_fraction = 0.0, np.clip(-cc / aa, 0.0, 1.0)
            elif second_fraction > 1.0:
                second_fraction, first_fraction = 1.0, np.clip((bb - cc) / aa, 0.0, 1.0)
    return np.linalg.norm(first0 + direction1 * first_fraction -
                          (second0 + direction2 * second_fraction))


def _triangle_intersects_box(triangle, half_extents):
    axes = [np.eye(3)[index] for index in range(3)]
    axes.append(np.cross(triangle[1] - triangle[0], triangle[2] - triangle[0]))
    axes.extend(
        np.cross(edge, np.eye(3)[axis])
        for edge in (triangle[1] - triangle[0], triangle[2] - triangle[1], triangle[0] - triangle[2])
        for axis in range(3)
    )
    for axis in axes:
        if np.linalg.norm(axis) <= 1e-12:
            continue
        projection = triangle @ axis
        radius = np.abs(axis) @ half_extents
        if projection.min() > radius + 1e-12 or projection.max() < -radius - 1e-12:
            return False
    return True


def _triangle_box_distance(triangle, half_extents):
    if _triangle_intersects_box(triangle, half_extents):
        return 0.0
    corners = np.array([
        [x * half_extents[0], y * half_extents[1], z * half_extents[2]]
        for x in (-1.0, 1.0) for y in (-1.0, 1.0) for z in (-1.0, 1.0)
    ])
    distance = min(np.linalg.norm(np.maximum(np.abs(point) - half_extents, 0.0))
                   for point in triangle)
    distance = min(distance, min(_point_to_triangle_distance(corner, triangle) for corner in corners))
    return min(distance, min(
        _segment_distance(triangle[first], triangle[second], corners[box_first], corners[box_second])
        for first, second in ((0, 1), (1, 2), (2, 0))
        for box_first, box_second in _BOX_EDGES
    ))


def _minimum_pad_to_cup_wall_gap(meshes, link_transform, walls):
    best = (math.inf, '')
    for mesh in meshes:
        triangles = mesh.triangles @ link_transform[:3, :3].T + link_transform[:3, 3]
        for name, wall_transform, half_extents in walls:
            inverse = np.linalg.inv(wall_transform)
            local = triangles @ inverse[:3, :3].T + inverse[:3, 3]
            for triangle in local:
                distance = _triangle_box_distance(triangle, half_extents)
                if distance < best[0]:
                    best = (distance, name)
    return best


def _fk(calculator, joints, positions):
    transform = _joint_transform(calculator, joints['base_joint'])
    for number, position in enumerate(positions, start=1):
        transform = transform @ _joint_transform(calculator, joints[str(number)], position)
    return transform


def _mesh_path(filename):
    prefix = 'package://so101_gazebo_demo/'
    assert filename.startswith(prefix)
    source = PACKAGE_DIR / filename[len(prefix):]
    if '/generated/' not in filename:
        return source
    return BUILD_ASSET_ROOT / source.relative_to(PACKAGE_DIR / 'meshes' / 'so101' / 'generated')


def _active_collision_meshes(calculator, robot, link_name):
    link = robot.find(f"./link[@name='{link_name}']")
    assert link is not None
    meshes = []
    for collision in link.findall('collision'):
        mesh = collision.find('./geometry/mesh')
        if mesh is None:
            continue
        origin = collision.find('origin')
        assert origin is not None
        xyz, rpy = _xyz_rpy(origin)
        meshes.append((
            collision.attrib['name'],
            calculator.load_mesh_in_link_frame(_mesh_path(mesh.attrib['filename']), xyz, rpy),
        ))
    return meshes


def _wall_hits(meshes, link_transform, walls):
    """Return exact active mesh/wall intersections and their vertex-z bounds."""
    hits = []
    for mesh_name, mesh in meshes:
        world_triangles = mesh.triangles @ link_transform[:3, :3].T + link_transform[:3, 3]
        for wall_name, wall_transform, half_extents in walls:
            inverse = np.linalg.inv(wall_transform)
            local_triangles = (
                world_triangles @ inverse[:3, :3].T + inverse[:3, 3]
            )
            # Reject almost every mesh/wall pair before the exact SAT pass;
            # this keeps the required 28 x 32 x 3 x 2 audit practical while
            # never turning an AABB overlap into a claimed contact.
            candidate = (
                (local_triangles.max(axis=1) >= -half_extents - 1e-12).all(axis=1) &
                (local_triangles.min(axis=1) <= half_extents + 1e-12).all(axis=1)
            )
            indexes = [
                index for index in np.flatnonzero(candidate)
                if _triangle_intersects_box(local_triangles[index], half_extents)
            ]
            if indexes:
                vertices_z = world_triangles[indexes, :, 2].reshape(-1)
                hits.append((mesh_name, wall_name, float(vertices_z.min()), float(vertices_z.max())))
    return hits


def _all_active_min_z(meshes, link_transform):
    return min(
        float((mesh.triangles.reshape(-1, 3) @ link_transform[:3, :3].T +
               link_transform[:3, 3])[:, 2].min())
        for _, mesh in meshes
    )


def _calibrated_grasp_witness(calculator, calibration, gripper_transform):
    """Return the real overlap-root face pair in world coordinates."""
    jaw_transform = calculator._jaw_transform_from_urdf(
        calibration.grasp_q6, calibration.j6_xyz, calibration.j6_rpy
    )
    moving = (
        calibration.moving_contact_triangles_jaw.reshape(-1, 3) @
        jaw_transform[:3, :3].T + jaw_transform[:3, 3]
    ).reshape(calibration.moving_contact_triangles_jaw.shape)
    witness = (math.inf, None, None)
    for fixed in calibration.fixed_contact_triangles:
        for moving_triangle in moving:
            overlap = calculator._clip_convex_polygon(
                moving_triangle[:, 1:3], fixed[:, 1:3]
            )
            for yz in overlap:
                fixed_x = calculator._x_on_triangle_at_yz(fixed, yz)
                moving_x = calculator._x_on_triangle_at_yz(moving_triangle, yz)
                if moving_x - fixed_x < witness[0]:
                    witness = (
                        moving_x - fixed_x,
                        np.array([fixed_x, *yz]),
                        np.array([moving_x, *yz]),
                    )
    assert witness[1] is not None
    fixed = witness[1] @ gripper_transform[:3, :3].T + gripper_transform[:3, 3]
    moving = witness[2] @ gripper_transform[:3, :3].T + gripper_transform[:3, 3]
    return witness[0], fixed, moving


def _signed_native_pad_wall_depths(
    calculator, calibration, gripper_transform, walls, q6=None
):
    """Return contact-face depth against wall_near, positive only inside the slab."""
    wall_name, wall_transform, half_extents = next(
        wall for wall in walls if wall[0] == 'wall_near'
    )
    assert wall_name == 'wall_near'
    # wall_near is a box whose local +Y is the configured outward normal.  A
    # fixed face must stay at or outside +half_y; a moving face approaches from
    # the inside and must stay at or inside -half_y.  This is signed support,
    # not the SAT boolean, so a zero-depth tangent remains distinguishable.
    normal = wall_transform[:3, 1]
    center_projection = float(wall_transform[:3, 3] @ normal)
    outer_face = center_projection + half_extents[1]
    inner_face = center_projection - half_extents[1]
    jaw = calculator._jaw_transform_from_urdf(
        calibration.grasp_q6 if q6 is None else q6,
        calibration.j6_xyz,
        calibration.j6_rpy,
    )
    fixed = (
        calibration.fixed_contact_triangles.reshape(-1, 3) @
        gripper_transform[:3, :3].T + gripper_transform[:3, 3]
    )
    moving_link = (
        calibration.moving_contact_triangles_jaw.reshape(-1, 3) @
        jaw[:3, :3].T + jaw[:3, 3]
    )
    moving = (
        moving_link @ gripper_transform[:3, :3].T + gripper_transform[:3, 3]
    )
    fixed_min = float((fixed @ normal).min())
    moving_max = float((moving @ normal).max())
    return {
        'fixed_signed_clearance_m': fixed_min - outer_face,
        'fixed_penetration_m': max(0.0, outer_face - fixed_min),
        'moving_signed_clearance_m': inner_face - moving_max,
        'moving_penetration_m': max(0.0, moving_max - inner_face),
        'total_penetration_m': max(0.0, outer_face - fixed_min) +
                               max(0.0, moving_max - inner_face),
    }


def _seat_walls_on_fixed_pad(calculator, calibration, gripper_transform, walls, q6):
    """Translate the free cup outward until its near wall reaches fixed-pad support."""
    preclose = _signed_native_pad_wall_depths(
        calculator, calibration, gripper_transform, walls, q6
    )
    _, wall_transform, _ = next(wall for wall in walls if wall[0] == 'wall_near')
    seating_shift = (
        wall_transform[:3, 1] * preclose['fixed_signed_clearance_m']
    )
    seated_walls = []
    for name, transform, half_extents in walls:
        seated_transform = transform.copy()
        seated_transform[:3, 3] += seating_shift
        seated_walls.append((name, seated_transform, half_extents))
    return seated_walls, seating_shift, preclose


def _yaw_aligned_fixed_tangent_witness(calculator, calibration, robot, policy):
    """Solve the CP16 yaw-aligned, full-fixed-face tangent pose from xacro FK."""
    _, joints = _descend_gripper_transform(calculator, robot)
    walls = _cup_wall_boxes(calculator, policy)
    _, wall_transform, half_extents = next(wall for wall in walls if wall[0] == 'wall_near')
    normal = wall_transform[:3, 1]
    # CP16's reviewed yaw-aligned witness is a seed, not a geometry formula:
    # every clearance/depth below is still recalculated from the current STL
    # triangles and resolved xacro.  Freezing this seed avoids circularly
    # deriving the reference from the policy that CP19 is replacing.
    cp16_joints = np.array([
        -0.000269196178500, 0.463782834311795, 0.139627875719619,
        0.967391942676754, -0.000276636480174,
    ])
    return joints, walls, normal, cp16_joints, _fk(calculator, joints, cp16_joints)


def _contact_critical_endpoint_budget(calculator, joints, normal, tangent_joints, tangent_transform,
                                      tcp_normal_allowance_m):
    """Bound contact-normal placement from all arm endpoint corners plus TCP allowance."""
    nominal_normal = float(tangent_transform[:3, 3] @ normal)
    fk_normal_errors = [
        float(_fk(calculator, joints, tangent_joints + 0.00025 * np.asarray(signs))[:3, 3] @ normal)
        - nominal_normal
        for signs in itertools.product((-1.0, 1.0), repeat=5)
    ]
    return max(abs(min(fk_normal_errors)), abs(max(fk_normal_errors))) + tcp_normal_allowance_m


def _robust_pad_clearance_interval_at_q6(
    calculator, calibration, walls, tangent_transform, target_q6, q6_tolerance,
    endpoint_budget_m, min_depth_m, max_depth_m,
):
    """Derive c bounds at a real q6 root without a nested gap-to-q6 solve."""
    open_depth = _signed_native_pad_wall_depths(
        calculator, calibration, tangent_transform, walls, target_q6 + q6_tolerance
    )['moving_penetration_m']
    closed_depth = _signed_native_pad_wall_depths(
        calculator, calibration, tangent_transform, walls, target_q6 - q6_tolerance
    )['moving_penetration_m']
    c_lower = max(endpoint_budget_m, min_depth_m - open_depth + endpoint_budget_m)
    c_upper = max_depth_m - closed_depth - endpoint_budget_m
    return {
        'gap_m': calibration.gap_at(target_q6),
        'target_q6': target_q6,
        'open_depth_m': open_depth,
        'closed_depth_m': closed_depth,
        'endpoint_budget_m': endpoint_budget_m,
        'c_lower_m': c_lower,
        'c_upper_m': c_upper,
        'equal_slack_c_m': (c_lower + c_upper) / 2.0,
        'equal_slack_m': (c_upper - c_lower) / 2.0,
    }


def _rotation_from_xyzw(xyzw):
    x, y, z, w = xyzw
    return np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])


def test_native_fingertip_pad_config_replaces_retired_direct_tongues():
    policy = _policy()
    assert 'fingertip_adapters' not in policy
    pads = policy['fingertip_pads']
    assert pads['enabled'] is True
    assert pads['material'] == 'TPU_95A'
    assert pads['contact_model'] == 'rigid_link_local_mesh'
    assert pads['fixed_pad']['opening_axis_thickness_m'] == pytest.approx(0.005)
    assert pads['moving_pad']['opening_axis_thickness_m'] == pytest.approx(0.005)
    for actual, expected in zip(_points(pads['moving_pad']), MOVING_POINTS):
        assert actual == pytest.approx(expected, abs=1e-12)
    for actual, expected in zip(_points(pads['fixed_pad']), FIXED_POINTS):
        assert actual == pytest.approx(expected, abs=1e-12)
    assert max(point[0] for point in _points(pads['moving_pad'])) == pytest.approx(-0.0625)
    assert max(point[0] for point in _points(pads['fixed_pad'])) == pytest.approx(0.104875)
    assert all('stem' not in key and 'tongue' not in key for key in pads)


def test_generated_pad_meshes_are_one_logical_native_only_pad_per_finger(tmp_path):
    policy = _policy()
    generator = _load_generator()
    output = tmp_path / 'generated'
    generator.generate(CONFIG_PATH, output)

    for name, expected_points, expected_direction in (
        ('moving', MOVING_POINTS, -1.0),
        ('fixed', FIXED_POINTS, 1.0),
    ):
        manifest = yaml.safe_load((output / name / 'manifest.yaml').read_text())
        assert manifest['logical_pad_count'] == 1
        assert manifest['mounting_stem_count'] == 0
        assert manifest['opening_axis_thickness_m'] == pytest.approx(0.005)
        assert manifest['contact_direction_x'] == pytest.approx(expected_direction)
        for actual, expected in zip(manifest['profile_points'], expected_points):
            assert actual == pytest.approx(expected, abs=1e-12)
        assert manifest['axial_bounds_m'] == pytest.approx(
            [expected_points[0][0], expected_points[-1][0]], abs=1e-12
        )
        assert (output / name / 'fingertip_pad.stl').is_file()
        assert len(manifest['collision_meshes']) == len(expected_points) - 1
        assert all((output / name / mesh).is_file() for mesh in manifest['collision_meshes'])

    assert policy['fingertip_pads']['moving_pad']['native_axial_bounds_m'] == pytest.approx(
        [-0.082000002, -0.061999999], abs=1e-9
    )
    assert policy['fingertip_pads']['fixed_pad']['native_axial_bounds_m'] == pytest.approx(
        [0.065720335, 0.105374999], abs=1e-9
    )


def test_installed_native_pad_collision_assets_match_the_generated_build_assets():
    """A live package must not silently fall back to legacy fingertip collisions."""
    installed = (
        Path(get_package_share_directory('so101_gazebo_demo'))
        / 'meshes' / 'so101' / 'generated'
    )
    for side, count in (('fixed', 7), ('moving', 6)):
        for filename in ['fingertip_pad.stl'] + [
            f'fingertip_pad_collision_{index:03d}.stl' for index in range(count)
        ]:
            assert (installed / side / filename).read_bytes() == (
                BUILD_ASSET_ROOT / side / filename
            ).read_bytes()


def test_exact_native_pad_to_cup_wall_diagnostic_at_descend_and_close_samples():
    """Keep the static cup diagnostic separate from runtime contact evidence."""
    calculator = _load_calculator()
    policy = _policy()
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    gripper_transform, joints = _descend_gripper_transform(calculator, robot)
    attachment = np.array(policy['grasp_frame']['attachment_relative_pose_xyz_xyzw'])
    x, y, z, w = attachment[3:]
    attachment_transform = np.eye(4)
    attachment_transform[:3, :3] = np.array([
        [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
        [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
        [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
    ])
    attachment_transform[:3, 3] = attachment[:3]
    # The calibrated attachment is the nominal pre-close object pose.  The
    # free cup then translates onto the fixed support during the bounded
    # regrasp; derive that translation from the real pad and wall faces rather
    # than treating the nominal attachment pose as a seated-contact witness.
    spawn = np.asarray(policy['scene']['spawn_pose_xyz_xyzw'][:3], dtype=float)
    nominal_attachment_shift = (gripper_transform @ attachment_transform)[:3, 3] - spawn
    assert nominal_attachment_shift == pytest.approx(np.zeros(3), abs=5e-9)

    fixed = _pad_collision_meshes(
        calculator, robot, 'gripper', 'fixed_fingertip_pad_collision_', 'fixed'
    )
    moving = _pad_collision_meshes(
        calculator, robot, 'jaw', 'moving_fingertip_pad_collision_', 'moving'
    )
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    walls, seating_shift, preclose = _seat_walls_on_fixed_pad(
        calculator, calibration, gripper_transform,
        _cup_wall_boxes(calculator, policy), calibration.grasp_q6,
    )
    assert 0.0012 <= np.linalg.norm(seating_shift) <= 0.0015
    assert np.linalg.norm(seating_shift - nominal_attachment_shift) < 0.003
    assert preclose['fixed_signed_clearance_m'] == pytest.approx(
        np.linalg.norm(seating_shift), abs=2e-9
    )
    samples = {}
    for q6 in (calibration.preopen_q6, calibration.grasp_q6 + 0.001,
               calibration.grasp_q6, calibration.grasp_q6 - 0.001):
        jaw_transform = gripper_transform @ _joint_transform(calculator, joints['6'], q6)
        samples[q6] = (
            _minimum_pad_to_cup_wall_gap(fixed, gripper_transform, walls),
            _minimum_pad_to_cup_wall_gap(moving, jaw_transform, walls),
        )

    # At the attachment contract pose the fixed face is tangent to the outside
    # and the moving face reaches the inside of the same near-wall slab.
    fixed_gap, fixed_wall = samples[calibration.grasp_q6][0]
    assert fixed_gap == pytest.approx(0.0, abs=2e-9)
    assert fixed_wall == 'wall_near'
    assert samples[calibration.preopen_q6][1][0] > 0.0
    assert samples[calibration.preopen_q6][1][1] != 'wall_near'
    open_q6 = calibration.grasp_q6 + 0.001
    assert 0.0 < samples[open_q6][1][0] <= 0.00005
    assert samples[open_q6][1][1] == 'wall_near'
    for q6 in (calibration.grasp_q6, calibration.grasp_q6 - 0.001):
        assert samples[q6][1][0] == pytest.approx(0.0, abs=2e-12)
        assert samples[q6][1][1] == 'wall_near'


def test_pick_ladder_diagnoses_preopen_and_fixed_pad_contact_as_infeasible():
    """Keep the q6-only preopen/close contradiction fail-closed and reproducible."""
    calculator = _load_calculator()
    policy = _policy()
    motion = yaml.safe_load(MOTION_PATH.read_text())
    validation = yaml.safe_load(VALIDATION_PATH.read_text())
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    _, joints = _descend_gripper_transform(calculator, robot)

    # This is the independently measured pre-Checkpoint-16 DESCEND endpoint,
    # not the policy under test.  A configuration which reverts to it must fail.
    old_descend = np.array([
        -0.000284277, 0.269004594, 0.230332947, 1.071465112, -0.052255557,
    ])
    old_transform = _fk(calculator, joints, old_descend)
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    installed_grasp_q6 = calibration.grasp_q6
    legacy_q6 = calculator._find_q6_for_fingertip_pad_gap(
        calibration.fixed_contact_triangles, calibration.moving_contact_triangles_jaw, 0.0012,
        j6_xyz=calibration.j6_xyz, j6_rpy=calibration.j6_rpy,
    )
    calibration = calibration._replace(grasp_q6=legacy_q6, grasp_gap_m=0.0012)
    gap, old_fixed, _ = _calibrated_grasp_witness(
        calculator, calibration, old_transform
    )
    assert gap == pytest.approx(0.0012, abs=2e-12)

    walls = _cup_wall_boxes(calculator, policy)
    _, wall_transform, half_extents = next(wall for wall in walls if wall[0] == 'wall_near')
    outward = wall_transform[:3, 1]
    outer_face = float(wall_transform[:3, 3] @ outward + half_extents[1])
    # The support-gap maximum in the permitted 5-degree cone occurs when the
    # opening axis is exactly anti-parallel to the outward normal.  Tool Z
    # stays vertical, so this is a 2.9773-degree yaw correction, not a change
    # to the approach-axis contract.
    desired_rotation = np.array([
        [0.0, 1.0, 0.0],
        [-1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0],
    ])
    fixed_faces = calibration.fixed_contact_triangles.reshape(-1, 3)
    # Fixed-pad support, not a gap-root witness, is tangent at preopen.  This
    # preserves the preopen no-positive-penetration contract; q6 cannot move
    # the fixed pad afterwards.
    desired_position = np.array([
        old_transform[0, 3],
        outer_face - float((fixed_faces @ (desired_rotation.T @ outward)).min()),
        old_transform[2, 3] + 0.190 - old_fixed[2],
    ])
    limits = (
        np.array([-1.91986, -1.74533, -1.74533, -1.65806, -2.79253]),
        np.array([1.91986, 1.74533, 1.5708, 1.65806, 2.79253]),
    )

    def residual(positions):
        transform = _fk(calculator, joints, positions)
        return np.r_[
            (transform[:3, 3] - desired_position) / 0.001,
            (transform[:3, 0] - desired_rotation[:, 0]) / 0.002,
            (transform[:3, 2] - desired_rotation[:, 2]) / 0.002,
            0.02 * (positions - old_descend),
        ]

    solution = least_squares(
        residual, old_descend, bounds=limits, max_nfev=5000,
        xtol=1e-13, ftol=1e-13, gtol=1e-13,
    )
    assert solution.success

    # The candidate uses a full-face fixed-pad tangent, not a SAT hit boolean.
    # It is the most favorable possible static pose for preopen: any movement
    # farther inward creates positive fixed-pad penetration before CLOSE.
    candidate_transform = _fk(calculator, joints, solution.x)
    assert candidate_transform[:3, 3] == pytest.approx(desired_position, abs=2e-6)
    assert np.dot(candidate_transform[:3, 0], desired_rotation[:, 0]) > 1.0 - 1e-9
    assert np.dot(candidate_transform[:3, 2], desired_rotation[:, 2]) > 1.0 - 1e-9
    assert np.dot(candidate_transform[:3, 0], old_transform[:3, 0]) > math.cos(0.0872664626)
    assert np.dot(candidate_transform[:3, 2], old_transform[:3, 2]) > math.cos(0.0872664626)

    fixed = _active_collision_meshes(calculator, robot, 'gripper')
    moving = _active_collision_meshes(calculator, robot, 'jaw')
    signed_depths = _signed_native_pad_wall_depths(
        calculator, calibration, candidate_transform, walls
    )
    # A preopen fixed pad may only be tangent at the outer face, never inside.
    assert signed_depths['fixed_penetration_m'] <= 2e-9
    # At the exact generated grasp root, the static solution is a zero-margin
    # boundary: nanometre-level solver/STL rounding is not a relaxed safety
    # limit.  The existing 1-mrad endpoint tolerance is tested below.
    assert signed_depths['moving_penetration_m'] <= 0.0008 + 2e-9
    assert signed_depths['total_penetration_m'] <= 0.0008 + 2e-9
    closer_depths = _signed_native_pad_wall_depths(
        calculator,
        calibration,
        candidate_transform,
        walls,
        calibration.grasp_q6 - validation['runtime']['q6_position_tolerance_rad'],
    )
    assert closer_depths['fixed_penetration_m'] <= 2e-9
    # A q6 endpoint accepted by the unchanged contract is 0.080376 mm above
    # the ceiling.  Hence the exact-boundary pose is not a valid static policy.
    assert closer_depths['moving_penetration_m'] == pytest.approx(
        0.000879970423, abs=2e-9
    )
    assert closer_depths['total_penetration_m'] > 0.0008
    preopen_jaw = candidate_transform @ _joint_transform(
        calculator, joints['6'], motion['gripper_actions']['preopen_q6']
    )
    fixed_preopen_hits = _wall_hits(fixed, candidate_transform, walls)
    assert _wall_hits(moving, preopen_jaw, walls) == []

    grasp_jaw = candidate_transform @ _joint_transform(calculator, joints['6'], legacy_q6)
    grasp_hits = _wall_hits(fixed, candidate_transform, walls) + _wall_hits(moving, grasp_jaw, walls)
    # SAT reports no positive-volume contact for the tangent fixed support.
    # The signed support assertions above, rather than this boolean result,
    # establish the zero-depth fixed contact contract.
    assert fixed_preopen_hits == []
    assert {(mesh, wall) for mesh, wall, _, _ in grasp_hits} == {
        ('moving_fingertip_pad_collision_000', 'wall_near'),
        ('moving_fingertip_pad_collision_001', 'wall_near'),
        ('moving_fingertip_pad_collision_002', 'wall_near'),
        ('moving_fingertip_pad_collision_003', 'wall_near'),
    }
    assert all('contact_convex' not in mesh for mesh, _, _, _ in grasp_hits)
    assert min(z_min for _, _, z_min, _ in grasp_hits) >= 0.175 - 2e-6
    assert max(z_max for _, _, _, z_max in grasp_hits) <= 0.202 + 2e-6
    assert _all_active_min_z(fixed, candidate_transform) >= 0.142
    assert _all_active_min_z(moving, grasp_jaw) >= 0.142

    assert signed_depths['fixed_signed_clearance_m'] == pytest.approx(0.0, abs=2e-9)
    assert signed_depths['moving_signed_clearance_m'] == pytest.approx(
        -0.000800000827, abs=2e-9
    )
    assert motion['gripper_actions']['preopen_q6'] == pytest.approx(0.465038)
    assert motion['gripper_actions']['grasp_close_q6'] == pytest.approx(
        installed_grasp_q6, abs=2e-12
    )


def test_contact_critical_arm_endpoint_contract_brackets_the_measured_contact_platform():
    """The 1-mrad q6 band must cross contact without exceeding its depth ceiling."""
    calculator = _load_calculator()
    policy = _policy()
    validation = yaml.safe_load(VALIDATION_PATH.read_text())
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    _, joints = _descend_gripper_transform(calculator, robot)
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    wide_q6 = calculator._find_q6_for_fingertip_pad_gap(
        calibration.fixed_contact_triangles, calibration.moving_contact_triangles_jaw, 0.0016,
        j6_xyz=calibration.j6_xyz, j6_rpy=calibration.j6_rpy,
    )
    descend = np.array([
        -0.000269196177, 0.463782833666, 0.139627874859, 0.967391944251, -0.000276636396,
    ])
    transform = _fk(calculator, joints, descend)
    walls = _cup_wall_boxes(calculator, policy)
    closed_depth = _signed_native_pad_wall_depths(
        calculator, calibration, transform, walls,
        wide_q6 - validation['runtime']['q6_position_tolerance_rad'],
    )['moving_penetration_m']
    assert closed_depth == pytest.approx(0.000480079037, abs=2e-9)

    # The former 5 mrad arm contract admits more than a millimetre of normal
    # motion and therefore cannot protect a 0.8 mm contact ceiling.
    normal = next(wall for wall in walls if wall[0] == 'wall_near')[1][:3, 1]
    nominal_projection = float(transform[:3, 3] @ normal)
    legacy_deltas = [
        float(_fk(calculator, joints, descend + 0.005 * np.array(signs))[:3, 3] @ normal) -
        nominal_projection
        for signs in itertools.product((-1.0, 1.0), repeat=5)
    ]
    inward_error = max(0.0, -min(legacy_deltas))
    outward_error = max(0.0, max(legacy_deltas))
    assert inward_error == pytest.approx(0.001189542560, abs=2e-9)
    assert outward_error == pytest.approx(0.001208328967, abs=2e-9)

    # Let c be the positive fixed-pad preopen clearance.  It must cover the
    # inward FK error, while moving-wall depth at the closed q6 endpoint bounds
    # it above.  The interval is empty before considering the still-looser 5 mm
    # TCP endpoint acceptance, so neither a seated-cup drift <=3 mm nor a
    # metadata change can repair this static contract.
    max_penetration = validation['grasp_contact']['max_penetration_m']
    clearance_upper = max_penetration - closed_depth - outward_error
    assert clearance_upper == pytest.approx(-0.000388408004, abs=2e-9)
    assert inward_error > clearance_upper
    for state in ('DESCEND', 'RECOVER_DESCEND_TO_PICK'):
        assert validation['states'][state]['joint_endpoint_tolerance_rad'] == pytest.approx(
            0.00025
        )
        assert validation['states'][state][
            'contact_wall_normal_endpoint_tolerance_m'
        ] == pytest.approx(0.0001)

    # Propagate all 32 joint-endpoint corners through the same URDF FK used by
    # the geometry audit.  WorldObserver obtains the raw /joint_states sample
    # and the MoveIt current-RobotState TCP through separate observations; it
    # rejects changes across the raw samples but does not prove the two source
    # snapshots have identical stamps.  Sum the bounds conservatively for
    # that possible observation skew, not as independent FK error.
    contract_deltas = [
        float(_fk(calculator, joints, descend + 0.00025 * np.array(signs))[:3, 3] @ normal) -
        nominal_projection
        for signs in itertools.product((-1.0, 1.0), repeat=5)
    ]
    worst_fk_normal_error = max(abs(min(contract_deltas)), abs(max(contract_deltas)))
    assert worst_fk_normal_error == pytest.approx(0.000059973242, abs=2e-9)
    combined_normal_error = worst_fk_normal_error + 0.0001
    assert combined_normal_error == pytest.approx(0.000159973242, abs=2e-9)
    gap_1600_budget = 0.000159758000
    assert combined_normal_error > gap_1600_budget

    # CP19 installs the minimum gap at which the c lower bound changes from
    # fixed-pad endpoint clearance to seated-compression clearance.  Derive
    # both the gap and equal-slack clearance from this exact mesh q6 root.
    platform_gap_m = calibration.gap_at(calibration.grasp_q6)
    platform_open = _signed_native_pad_wall_depths(
        calculator, calibration, transform, walls,
        calibration.grasp_q6 + validation['runtime']['q6_position_tolerance_rad'],
    )
    platform_target = _signed_native_pad_wall_depths(
        calculator, calibration, transform, walls, calibration.grasp_q6,
    )
    platform_closed = _signed_native_pad_wall_depths(
        calculator, calibration, transform, walls,
        calibration.grasp_q6 - validation['runtime']['q6_position_tolerance_rad'],
    )
    assert policy['fingertip_pads']['grasp_gap_m'] == pytest.approx(platform_gap_m, abs=2e-12)
    assert platform_open['fixed_signed_clearance_m'] == pytest.approx(0.0, abs=2e-9)
    assert 0.0 <= platform_open['moving_signed_clearance_m'] <= 0.00005
    assert platform_target['moving_penetration_m'] == pytest.approx(0.000040000786, abs=2e-9)
    assert 0.0 < platform_closed['moving_penetration_m'] <= max_penetration


def test_measured_contact_target_stays_inside_the_mesh_bounded_q6_band():
    """The measured live target must retain fixed support and bounded moving contact."""
    calculator = _load_calculator()
    policy = _policy()
    validation = yaml.safe_load(VALIDATION_PATH.read_text())
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    joints, walls, normal, tangent_joints, tangent_transform = \
        _yaw_aligned_fixed_tangent_witness(calculator, calibration, robot, policy)
    q6_tolerance = validation['runtime']['q6_position_tolerance_rad']
    assert validation['grasp_contact']['max_penetration_m'] == pytest.approx(0.0013)
    # The extra 0.5 mm in the runtime limit covers Bullet solver depth.  This
    # exact-mesh interval remains bounded by the nominal 0.8-mm overlap.
    max_depth = 0.0008
    min_depth = 0.0001
    tcp_allowance = validation['states']['DESCEND'][
        'contact_wall_normal_endpoint_tolerance_m'
    ]

    endpoint_budget = _contact_critical_endpoint_budget(
        calculator, joints, normal, tangent_joints, tangent_transform, tcp_allowance
    )

    def open_depth_minus_minimum(target_q6):
        return _signed_native_pad_wall_depths(
            calculator, calibration, tangent_transform, walls, target_q6 + q6_tolerance
        )['moving_penetration_m'] - min_depth

    lower, upper = -0.06, -0.04
    assert open_depth_minus_minimum(lower) > 0.0
    assert open_depth_minus_minimum(upper) < 0.0
    for _ in range(80):
        middle = (lower + upper) / 2.0
        if open_depth_minus_minimum(middle) >= 0.0:
            lower = middle
        else:
            upper = middle
    platform = _robust_pad_clearance_interval_at_q6(
        calculator, calibration, walls, tangent_transform, lower, q6_tolerance,
        endpoint_budget, min_depth, max_depth,
    )
    # At the platform entry c_lower switches from endpoint-only fixed-pad
    # clearance to the seated-compression bound.  This is why a larger 1.9-mm
    # gap is not "more robust": its lower bound must grow to retain 0.1 mm.
    wider_q6 = calculator._find_q6_for_fingertip_pad_gap(
        calibration.fixed_contact_triangles, calibration.moving_contact_triangles_jaw, 0.0019,
        j6_xyz=calibration.j6_xyz, j6_rpy=calibration.j6_rpy,
    )
    wider = _robust_pad_clearance_interval_at_q6(
        calculator, calibration, walls, tangent_transform, wider_q6, q6_tolerance,
        endpoint_budget, min_depth, max_depth,
    )
    assert platform['endpoint_budget_m'] == pytest.approx(0.000159973242, abs=2e-12)
    assert platform['equal_slack_c_m'] == pytest.approx(0.000269852305, abs=2e-12)
    assert platform['equal_slack_m'] == pytest.approx(0.000109879063, abs=5e-11)
    assert platform['c_lower_m'] == pytest.approx(platform['endpoint_budget_m'], abs=2e-12)
    assert wider['c_lower_m'] == pytest.approx(0.000240151949, abs=2e-9)
    assert wider['c_lower_m'] > wider['endpoint_budget_m']
    assert wider['equal_slack_m'] == pytest.approx(platform['equal_slack_m'], abs=2e-7)

    # The former equal-slack knee remains a useful diagnostic lower bound, but
    # live contact stopped 0.471 mrad outside the old 1.900-mm target.  The
    # installed mesh root is deliberately just inside that measured platform.
    installed = _robust_pad_clearance_interval_at_q6(
        calculator, calibration, walls, tangent_transform, calibration.grasp_q6,
        q6_tolerance, endpoint_budget, 0.0, max_depth,
    )
    assert policy['fingertip_pads']['grasp_gap_m'] == pytest.approx(
        calibration.gap_at(calibration.grasp_q6), abs=2e-12
    )
    assert policy['fingertip_pads']['grasp_gap_m'] > platform['gap_m']
    open_depths = _signed_native_pad_wall_depths(
        calculator, calibration, tangent_transform, walls,
        calibration.grasp_q6 + q6_tolerance,
    )
    target_depths = _signed_native_pad_wall_depths(
        calculator, calibration, tangent_transform, walls, calibration.grasp_q6,
    )
    closed_depths = _signed_native_pad_wall_depths(
        calculator, calibration, tangent_transform, walls,
        calibration.grasp_q6 - q6_tolerance,
    )
    assert abs(open_depths['fixed_signed_clearance_m']) <= 2e-9
    assert 0.0 <= open_depths['moving_signed_clearance_m'] <= 0.00005
    assert target_depths['moving_penetration_m'] > 0.0
    assert closed_depths['moving_penetration_m'] <= max_depth
    assert installed['equal_slack_m'] > 0.0


def test_full_active_mesh_contact_and_preopen_swept_audit():
    """Audit every active mesh, not just the two pad contact-face envelopes."""
    calculator = _load_calculator()
    policy = _policy()
    motion = yaml.safe_load(MOTION_PATH.read_text())
    validation = yaml.safe_load(VALIDATION_PATH.read_text())
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    _, joints = _descend_gripper_transform(calculator, robot)
    approach_walls = _cup_wall_boxes(calculator, policy)
    normal = next(wall for wall in approach_walls if wall[0] == 'wall_near')[1][:3, 1]
    fixed = _active_collision_meshes(calculator, robot, 'gripper')
    moving = _active_collision_meshes(calculator, robot, 'jaw')
    assert len(fixed) == 14
    assert len(moving) == 14
    assert len({name for name, _ in fixed + moving}) == 28

    q6_tolerance = validation['runtime']['q6_position_tolerance_rad']
    contact_q6 = calibration.grasp_q6
    descend = np.asarray(motion['states']['DESCEND']['waypoints'][-1])
    nominal_gripper = _fk(calculator, joints, descend)
    walls, seating_shift, _ = _seat_walls_on_fixed_pad(
        calculator, calibration, nominal_gripper, approach_walls, contact_q6
    )
    assert 0.0012 <= np.linalg.norm(seating_shift) <= 0.0015
    rim_z = max(transform[2, 3] + half[2] for _, transform, half in walls)
    table_top_z = 0.12
    cup_bottom_top_z = policy['scene']['spawn_pose_xyz_xyzw'][2] - 0.044 + 0.001

    # This is the full CP19 extremum set: every arm endpoint corner, both
    # independent TCP normal observations, and the target/open/closed q6
    # values.  Both sides must remain in the runtime contract band around the
    # same seated near wall; any actual triangle overlap may only involve the
    # corresponding native pad pieces.
    for signs in itertools.product((-1.0, 1.0), repeat=5):
        corner = descend + 0.00025 * np.asarray(signs)
        for tcp_normal_error in (-0.0001, 0.0001):
            gripper = _fk(calculator, joints, corner)
            gripper[:3, 3] += normal * tcp_normal_error
            for q6 in (contact_q6, contact_q6 + q6_tolerance, contact_q6 - q6_tolerance):
                jaw = gripper @ _joint_transform(calculator, joints['6'], q6)
                depths = _signed_native_pad_wall_depths(
                    calculator, calibration, gripper, walls, q6
                )
                assert abs(depths['fixed_signed_clearance_m']) <= 0.0008 + 2e-9
                assert abs(depths['moving_signed_clearance_m']) <= 0.0008 + 2e-9
                assert depths['fixed_penetration_m'] <= 0.0008 + 2e-9
                assert depths['moving_penetration_m'] <= 0.0008 + 2e-9
                fixed_hits = _wall_hits(fixed, gripper, walls)
                moving_hits = _wall_hits(moving, jaw, walls)
                assert all(
                    name.startswith('fixed_fingertip_pad_collision_') and wall == 'wall_near'
                    for name, wall, _, _ in fixed_hits
                )
                assert all(
                    name.startswith('moving_fingertip_pad_collision_') and wall == 'wall_near'
                    for name, wall, _, _ in moving_hits
                )
                assert all(
                    'contact_convex' not in name
                    for name, _, _, _ in fixed_hits + moving_hits
                )
                hits = fixed_hits + moving_hits
                if hits:
                    assert min(z_min for _, _, z_min, _ in hits) >= rim_z - 0.035 - 2e-6
                    assert max(z_max for _, _, _, z_max in hits) <= rim_z - 0.008 + 2e-6
                assert _all_active_min_z(fixed, gripper) > table_top_z
                assert _all_active_min_z(moving, jaw) > table_top_z
                assert _all_active_min_z(fixed, gripper) > cup_bottom_top_z
                assert _all_active_min_z(moving, jaw) > cup_bottom_top_z

    # Before the final contact endpoint, linearly sample every MOVE_ABOVE and
    # DESCEND segment at preopen.  This uses all 28 actual triangles against
    # all twelve wall boxes; neither legacy convex bodies nor pad meshes may
    # touch the cup, bottom, or table during approach.
    approach = [[0.0] * 5] + motion['states']['MOVE_ABOVE_OBJECT']['waypoints'] + \
        motion['states']['DESCEND']['waypoints']
    for start, finish in zip(approach, approach[1:]):
        for fraction in np.linspace(0.0, 1.0, 11):
            gripper = _fk(calculator, joints,
                          (1.0 - fraction) * np.asarray(start) + fraction * np.asarray(finish))
            jaw = gripper @ _joint_transform(
                calculator, joints['6'], motion['gripper_actions']['preopen_q6']
            )
            assert _wall_hits(fixed, gripper, approach_walls) == []
            assert _wall_hits(moving, jaw, approach_walls) == []
            assert _all_active_min_z(fixed, gripper) > table_top_z
            assert _all_active_min_z(moving, jaw) > table_top_z
            assert _all_active_min_z(fixed, gripper) > cup_bottom_top_z
            assert _all_active_min_z(moving, jaw) > cup_bottom_top_z


def test_moveit_and_gazebo_receive_identical_named_fingertip_pad_envelopes():
    mappings = [f'object_config:={CONFIG_PATH}']
    expected = {
        'gripper': ('fixed_fingertip_pad', len(FIXED_POINTS) - 1),
        'jaw': ('moving_fingertip_pad', len(MOVING_POINTS) - 1),
    }
    for primitives in ('false', 'true'):
        robot = _robot(*mappings, f'gazebo_collision_primitives:={primitives}')
        all_collision_names = [node.attrib.get('name', '') for node in robot.findall('.//collision')]
        assert not any('direct_tongue' in name or 'stem' in name for name in all_collision_names)
        for link_name, (pad_name, segment_count) in expected.items():
            link = robot.find(f"./link[@name='{link_name}']")
            assert link is not None
            visual = link.find(f"./visual[@name='{pad_name}_visual']")
            assert visual is not None
            assert visual.find('./geometry/mesh') is not None
            collisions = [
                node for node in link.findall('./collision')
                if node.attrib.get('name', '').startswith(f'{pad_name}_collision_')
            ]
            assert len(collisions) == segment_count
            assert all(node.find('./geometry/mesh') is not None for node in collisions)
            assert all('/generated/' in node.find('./geometry/mesh').attrib['filename'] for node in collisions)


def test_pick_motion_policy_preserves_state_continuity():
    """Keep every pick, lift, and recovery boundary on one joint endpoint."""
    calculator = _load_calculator()
    motion = yaml.safe_load(MOTION_PATH.read_text())
    validation = yaml.safe_load(VALIDATION_PATH.read_text())
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    _, joints = _descend_gripper_transform(calculator, robot)

    above_last = motion['states']['MOVE_ABOVE_OBJECT']['waypoints'][-1]
    descend_last = motion['states']['DESCEND']['waypoints'][-1]
    tcp_offset = _joint_transform(calculator, joints['so101_tcp_joint'])
    above = (_fk(calculator, joints, np.asarray(above_last)) @ tcp_offset)[:3, 3]
    descend = (_fk(calculator, joints, np.asarray(descend_last)) @ tcp_offset)[:3, 3]
    for state in ('MOVE_ABOVE_OBJECT', 'LIFT', 'RECOVER_MOVE_ABOVE_PICK'):
        assert np.linalg.norm(
            np.asarray(validation['states'][state]['endpoint_position']) - above
        ) <= 0.0001
    for state in ('DESCEND', 'RECOVER_DESCEND_TO_PICK'):
        assert np.linalg.norm(
            np.asarray(validation['states'][state]['endpoint_position']) - descend
        ) <= 0.0001

    assert motion['states']['DESCEND']['logical_start'] == pytest.approx(above_last)
    assert motion['states']['LIFT']['logical_start'] == pytest.approx(descend_last)
    assert motion['states']['LIFT']['waypoints'][-1] == pytest.approx(above_last)
    assert motion['states']['RECOVER_MOVE_ABOVE_PICK']['waypoints'][-1] == pytest.approx(
        above_last
    )
    assert motion['states']['RECOVER_DESCEND_TO_PICK']['logical_start'] == pytest.approx(
        above_last
    )
    assert motion['states']['RECOVER_DESCEND_TO_PICK']['waypoints'][-1] == pytest.approx(
        descend_last
    )


def test_fixed_pad_pick_lane_has_live_margin_and_no_cup_contact_through_descend():
    """Verify live-derived approach margin and bilateral seated geometry."""
    calculator = _load_calculator()
    policy = _policy()
    motion = yaml.safe_load(MOTION_PATH.read_text())
    validation = yaml.safe_load(VALIDATION_PATH.read_text())
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    _, joints = _descend_gripper_transform(calculator, robot)
    walls = _cup_wall_boxes(calculator, policy)
    normal = next(wall for wall in walls if wall[0] == 'wall_near')[1][:3, 1]
    fixed = _active_collision_meshes(calculator, robot, 'gripper')
    moving = _active_collision_meshes(calculator, robot, 'jaw')

    selected_lane = np.asarray(motion['states']['DESCEND']['waypoints'][-1])
    first_live_clear_lane = np.array([
        -0.000270175525, 0.458388505389, 0.149004377192,
        0.963409770127, -0.000277615827,
    ])
    selected_transform = _fk(calculator, joints, selected_lane)
    boundary_transform = _fk(calculator, joints, first_live_clear_lane)
    selected_margin = float(
        (selected_transform[:3, 3] - boundary_transform[:3, 3]) @ normal
    )
    assert selected_margin >= 0.0005 - 2e-9

    # Fresh raw Gazebo manifold evidence at the lowered contact band showed
    # that the previous selected endpoint was not clear: fixed piece _005
    # reached 1.196--1.199 mm while q6 was still at preopen.  The replacement
    # lane must move the TCP outward by the measured 1.20 mm envelope plus a
    # 0.25 mm live margin; CLOSE parameters cannot mask a DESCEND collision.
    penetrating_down5_lane = np.array([
        -0.000270871118, 0.478733727231, 0.159363576598,
        0.932705348876, -0.000278311420,
    ])
    penetrating_transform = _fk(calculator, joints, penetrating_down5_lane)
    down5_live_margin = float(
        (selected_transform[:3, 3] - penetrating_transform[:3, 3]) @ normal
    )
    assert down5_live_margin >= 0.00145 - 2e-9

    approach = [[0.0] * 5] + motion['states']['MOVE_ABOVE_OBJECT']['waypoints'] + \
        motion['states']['DESCEND']['waypoints']
    for start, finish in zip(approach, approach[1:]):
        for fraction in np.linspace(0.0, 1.0, 21):
            gripper = _fk(
                calculator, joints,
                (1.0 - fraction) * np.asarray(start) + fraction * np.asarray(finish),
            )
            jaw = gripper @ _joint_transform(
                calculator, joints['6'], motion['gripper_actions']['preopen_q6']
            )
            assert _wall_hits(fixed, gripper, walls) == []
            assert _wall_hits(moving, jaw, walls) == []

    gripper = _fk(
        calculator, joints, np.asarray(motion['states']['DESCEND']['waypoints'][-1])
    )
    seated_walls, seating_shift, _ = _seat_walls_on_fixed_pad(
        calculator, calibration, gripper, walls, calibration.grasp_q6
    )
    assert 0.0012 <= np.linalg.norm(seating_shift) <= 0.0015
    q6_tolerance = validation['runtime']['q6_position_tolerance_rad']
    for q6 in (
        calibration.grasp_q6 + q6_tolerance,
        calibration.grasp_q6,
        calibration.grasp_q6 - q6_tolerance,
    ):
        depths = _signed_native_pad_wall_depths(
            calculator, calibration, gripper, seated_walls, q6
        )
        assert abs(depths['fixed_signed_clearance_m']) <= 2e-9
        assert depths['moving_signed_clearance_m'] <= 0.00005
        assert depths['moving_penetration_m'] <= 0.0008 + 2e-9
    target_depths = _signed_native_pad_wall_depths(
        calculator, calibration, gripper, seated_walls, calibration.grasp_q6
    )
    assert target_depths['moving_penetration_m'] > 0.0


def test_actual_sdf_fixed_005_outer_face_matches_calibration_face(tmp_path, monkeypatch):
    """The live SDF must use the calibrated STL face through Bullet's convex path."""
    monkeypatch.setenv('XDG_CACHE_HOME', str(tmp_path / 'cache'))
    output = tmp_path / 'so101.sdf'
    subprocess.run([
        'python3', str(PACKAGE_DIR / 'scripts' / 'prepare_simulation_model.py'),
        '--xacro', str(XACRO_PATH), '--output', str(output),
        '--base-height', '0.1899186',
        '--manifest', str(PACKAGE_DIR / 'meshes' / 'so101' / 'collision' /
                          'fixed_finger_contact' / 'manifest.json'),
        '--manifest', str(PACKAGE_DIR / 'meshes' / 'so101' / 'collision' /
                          'moving_jaw_contact' / 'manifest.json'),
        '--object-config', str(CONFIG_PATH),
    ], check=True)
    root = ET.parse(output).getroot()
    collision = next(
        item for item in root.iter('collision')
        if 'fixed_fingertip_pad_collision_005' in item.attrib.get('name', '')
    )
    mesh = collision.find('geometry/mesh')
    assert mesh is not None
    assert mesh.attrib.get('optimization') == 'convex_hull'
    assert mesh.findtext('uri').endswith(
        '/fixed/fingertip_pad_collision_005.stl'
    )

    calculator = _load_calculator()
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    pose = np.fromstring(collision.findtext('pose'), sep=' ')
    piece = calculator.load_mesh_in_link_frame(
        BUILD_ASSET_ROOT / 'fixed' / 'fingertip_pad_collision_005.stl',
        pose[:3], pose[3:],
    )
    intended = calculator._contact_face_triangles(piece, 1.0)
    calibrated = calibration.fixed_contact_triangles
    canonical = lambda triangle: tuple(sorted(
        tuple(np.round(vertex, 9)) for vertex in triangle
    ))
    assert {canonical(face) for face in intended} <= {
        canonical(face) for face in calibrated
    }


def test_close_entry_geometry_caps_first_contact_and_retains_bilateral_seating():
    """Bound the real rigid-wall CLOSE sweep before the cup can translate."""
    calculator = _load_calculator()
    policy = _policy()
    motion = yaml.safe_load(MOTION_PATH.read_text())
    validation = yaml.safe_load(VALIDATION_PATH.read_text())
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    _, joints = _descend_gripper_transform(calculator, robot)
    gripper = _fk(
        calculator, joints, np.asarray(motion['states']['DESCEND']['waypoints'][-1])
    )
    spawn_walls = _cup_wall_boxes(calculator, policy)
    max_depth = validation['grasp_contact']['max_penetration_m']
    q6_tolerance = validation['runtime']['q6_position_tolerance_rad']
    contact_stop_tolerance = validation['runtime']['q6_contact_stop_tolerance_rad']

    # Rigidly extrapolating the final q6 against the unshifted spawn wall exceeds
    # the dynamic depth limit.  The cup is free at this phase, so this proves
    # why attachment must wait for the cup to translate and settle onto the
    # fixed support; it is not an admissible attached-contact pose.
    for q6 in (calibration.grasp_q6, calibration.grasp_q6 - q6_tolerance):
        entry = _signed_native_pad_wall_depths(
            calculator, calibration, gripper, spawn_walls, q6
        )
        assert 0.0 < entry['fixed_signed_clearance_m'] < 0.003
        assert entry['moving_penetration_m'] > max_depth

    seated_walls, seating_shift, _ = _seat_walls_on_fixed_pad(
        calculator, calibration, gripper, spawn_walls, calibration.grasp_q6
    )
    assert np.linalg.norm(seating_shift) <= 0.003

    # The controller reached the commanded target and the compliant contact
    # subsequently settled 1.158458 mrad open of it.  Attached arm motions use
    # this separately proven contact-context window; ordinary q6 contexts keep
    # the controller's 1 mrad endpoint tolerance.  The opposite (deeper-close)
    # edge is the exact-mesh worst case and must retain the physical 0.8-mm cap.
    assert contact_stop_tolerance == pytest.approx(0.00125)
    assert contact_stop_tolerance > q6_tolerance
    worst_contact_context = _signed_native_pad_wall_depths(
        calculator, calibration, gripper, seated_walls,
        calibration.grasp_q6 - contact_stop_tolerance,
    )
    assert worst_contact_context['fixed_penetration_m'] <= max_depth
    assert 0.0 < worst_contact_context['moving_penetration_m'] <= max_depth
    assert worst_contact_context['total_penetration_m'] <= max_depth

    seated = _signed_native_pad_wall_depths(
        calculator, calibration, gripper, seated_walls, calibration.grasp_q6
    )
    assert abs(seated['fixed_signed_clearance_m']) <= 2e-9
    assert 0.0 < seated['moving_penetration_m'] <= max_depth


def test_descend_precontact_reduces_fixed_pad_clearance_without_static_penetration():
    """DESCEND must move the fixed finger toward the wall before q6 closes."""
    calculator = _load_calculator()
    policy = _policy()
    motion = yaml.safe_load(MOTION_PATH.read_text())
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    _, joints = _descend_gripper_transform(calculator, robot)
    spawn_walls = _cup_wall_boxes(calculator, policy)

    previous_endpoint = np.asarray([
        -0.000182194999,
        0.469727784396,
        0.217642530798,
        0.859256029129,
        0.000398028351,
    ])
    selected_endpoint = np.asarray(motion['states']['DESCEND']['waypoints'][-1])
    previous = _signed_native_pad_wall_depths(
        calculator, calibration, _fk(calculator, joints, previous_endpoint), spawn_walls,
        calibration.preopen_q6,
    )
    selected = _signed_native_pad_wall_depths(
        calculator, calibration, _fk(calculator, joints, selected_endpoint), spawn_walls,
        calibration.preopen_q6,
    )

    # The live no-load trial kept the cup at its canonical spawn pose while
    # reducing the visible fixed-side gap by about 0.56 mm.  Keep a bounded
    # positive analytical margin because Bullet's convex margin reports
    # contact before the rendered mesh reaches the wall.
    assert selected['fixed_signed_clearance_m'] <= 0.0015
    assert selected['fixed_signed_clearance_m'] >= 0.0012
    assert previous['fixed_signed_clearance_m'] - selected['fixed_signed_clearance_m'] >= 0.0005
    assert selected['fixed_penetration_m'] == pytest.approx(0.0, abs=2e-9)


def test_close_geometry_brackets_the_near_wall_with_bilateral_pad_contact():
    """CLOSE must establish a fixed support and an inside moving-pad contact."""
    calculator = _load_calculator()
    policy = _policy()
    motion = yaml.safe_load(MOTION_PATH.read_text())
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    _, joints = _descend_gripper_transform(calculator, robot)
    gripper = _fk(
        calculator, joints, np.asarray(motion['states']['DESCEND']['waypoints'][-1])
    )
    preclose_walls = _cup_wall_boxes(calculator, policy)
    preclose_depths = _signed_native_pad_wall_depths(
        calculator, calibration, gripper, preclose_walls, calibration.grasp_q6
    )

    walls, seating_shift, preclose_depths = _seat_walls_on_fixed_pad(
        calculator, calibration, gripper, preclose_walls, calibration.grasp_q6
    )
    outward = np.asarray(policy['grasp_frame']['near_wall_outward_world'], dtype=float)
    seating_distance = float(seating_shift @ outward)
    # The fixed-finger precontact lane leaves roughly 1.39 mm for the bounded
    # regrasp to seat the free cup onto the fixed pad.  This is smaller than the
    # previous 1.95-mm lane and remains inside the 3-mm drift budget.
    assert 0.0012 <= seating_distance <= 0.0015
    assert seating_shift == pytest.approx(outward * seating_distance, abs=5e-9)
    assert np.linalg.norm(seating_shift) < 0.003
    assert preclose_depths['fixed_signed_clearance_m'] == pytest.approx(
        seating_distance, abs=2e-9
    )
    depths = _signed_native_pad_wall_depths(
        calculator, calibration, gripper, walls, calibration.grasp_q6
    )

    assert abs(depths['fixed_signed_clearance_m']) <= 2e-9
    assert 0.0 < depths['moving_penetration_m'] <= 0.0008
    wall_interference = (
        policy['model']['wall_thickness_m'] - calibration.gap_at(calibration.grasp_q6)
    )
    assert wall_interference > 0.0
    # The 40-um calibrated face gap stays within 15 um after projection onto
    # the selected lane's slightly tilted cup-wall normal and extended axial edge.
    assert depths['moving_penetration_m'] <= 0.00006
    assert abs(depths['moving_penetration_m'] - wall_interference) < 0.000015


def test_selected_close_contact_band_stays_below_the_rim_leverage_zone():
    """The actual pad meshes must pinch below the live high-torque rim band."""
    calculator = _load_calculator()
    policy = _policy()
    motion = yaml.safe_load(MOTION_PATH.read_text())
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    _, joints = _descend_gripper_transform(calculator, robot)
    gripper = _fk(
        calculator, joints, np.asarray(motion['states']['DESCEND']['waypoints'][-1])
    )
    outward = np.asarray(policy['grasp_frame']['near_wall_outward_world'], dtype=float)
    walls, seating_shift, _ = _seat_walls_on_fixed_pad(
        calculator, calibration, gripper, _cup_wall_boxes(calculator, policy),
        calibration.grasp_q6,
    )
    assert 0.0012 <= np.linalg.norm(seating_shift) <= 0.0015
    probed_walls = []
    for name, transform, half_extents in walls:
        seated_transform = transform.copy()
        # The fixed face is intentionally tangent.  Probe one micrometre into
        # the allowed contact band so SAT returns its participating pieces.
        seated_transform[:3, 3] += outward * 1e-6
        probed_walls.append((name, seated_transform, half_extents))
    fixed = _active_collision_meshes(calculator, robot, 'gripper')
    moving = _active_collision_meshes(calculator, robot, 'jaw')
    jaw = gripper @ _joint_transform(calculator, joints['6'], calibration.grasp_q6)
    hits = _wall_hits(fixed, gripper, probed_walls) + _wall_hits(moving, jaw, probed_walls)
    rim_z = max(transform[2, 3] + half[2] for _, transform, half in probed_walls)

    assert any(name.startswith('fixed_fingertip_pad_collision_') for name, *_ in hits)
    assert any(name.startswith('moving_fingertip_pad_collision_') for name, *_ in hits)
    assert max(z_max for _, _, _, z_max in hits) <= rim_z - 0.013 + 2e-6


def test_moving_pad_load_face_is_horizontal_at_runtime_preload():
    """The segment carrying the cup must not inject vertical slip force."""
    calculator = _load_calculator()
    robot = _robot(
        f'object_config:={CONFIG_PATH}',
        'gazebo_collision_primitives:=true',
    )
    gripper, joints = _descend_gripper_transform(calculator, robot)
    calibration = calculator.calculate_fingertip_pad_gap_calibration(
        CONFIG_PATH, BUILD_ASSET_ROOT, PACKAGE_DIR / 'urdf' / 'so101_base.xacro'
    )
    # The runtime's canonical regrasp squeeze is locked independently by the
    # SO101Profile tests.  Validate the geometry at that actual load-bearing q6.
    runtime_preload_q6 = calibration.grasp_q6 - 0.0060
    jaw = gripper @ _joint_transform(calculator, joints['6'], runtime_preload_q6)
    moving = dict(_active_collision_meshes(calculator, robot, 'jaw'))
    mesh = moving['moving_fingertip_pad_collision_002']
    triangles = mesh.triangles
    cross = np.cross(triangles[:, 1] - triangles[:, 0],
                     triangles[:, 2] - triangles[:, 0])
    double_areas = np.linalg.norm(cross, axis=1)
    normals = cross / double_areas[:, np.newaxis]
    world_normals = normals @ jaw[:3, :3].T
    # The native short load face is not the segment's largest face; select the
    # outward contact pair by its link-local -X normal instead of triangle area.
    load_faces = world_normals[mesh.face_normals[:, 0] <= -0.99]

    assert load_faces.shape == (2, 3)
    assert np.min(np.abs(load_faces[:, 1])) >= 0.99
    assert np.max(np.abs(load_faces[:, 2])) <= 0.01
