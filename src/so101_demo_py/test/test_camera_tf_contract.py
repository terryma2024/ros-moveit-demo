from pathlib import Path
from xml.etree import ElementTree

import numpy as np
from launch_ros.actions import Node

from so101_demo.runtime.camera_tf import (
    BASE_TO_CAMERA,
    CAMERA_TO_OPTICAL,
    camera_static_transform_nodes,
)


SCENE = Path(__file__).parents[1] / "assets/mujoco/scene.xml"


def _rpy_matrix(rpy: tuple[float, float, float]) -> np.ndarray:
    roll, pitch, yaw = rpy
    cx, sx = np.cos(roll), np.sin(roll)
    cy, sy = np.cos(pitch), np.sin(pitch)
    cz, sz = np.cos(yaw), np.sin(yaw)
    return np.array(
        (
            (cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
            (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
            (-sy, cy * sx, cy * cx),
        )
    )


def test_static_tf_composes_to_mjcf_camera_and_ros_optical_axes() -> None:
    camera = next(
        item
        for item in ElementTree.parse(SCENE).iter("camera")
        if item.attrib.get("name") == "task_camera"
    )
    world_origin = np.array((0.0, 0.0, 0.1899186)) + np.array(
        BASE_TO_CAMERA.translation_xyz
    )
    np.testing.assert_allclose(world_origin, np.fromstring(camera.attrib["pos"], sep=" "))

    mj_x, mj_y = np.fromstring(camera.attrib["xyaxes"], sep=" ").reshape(2, 3)
    mj_x /= np.linalg.norm(mj_x)
    mj_y /= np.linalg.norm(mj_y)
    mj_z = np.cross(mj_x, mj_y)
    expected_optical = np.column_stack((mj_x, -mj_y, -mj_z))
    composed = _rpy_matrix(BASE_TO_CAMERA.rpy) @ _rpy_matrix(CAMERA_TO_OPTICAL.rpy)
    np.testing.assert_allclose(composed, expected_optical, atol=3e-4)


def test_static_tf_specs_and_nodes_preserve_the_exact_frame_chain() -> None:
    assert (BASE_TO_CAMERA.parent_frame, BASE_TO_CAMERA.child_frame) == (
        "base",
        "camera_link",
    )
    assert (CAMERA_TO_OPTICAL.parent_frame, CAMERA_TO_OPTICAL.child_frame) == (
        "camera_link",
        "task_camera_frame",
    )
    assert BASE_TO_CAMERA.translation_xyz == (0.65, -0.65, 0.3600814)
    assert BASE_TO_CAMERA.rpy == (0.0, 0.517, 2.35619449)
    assert CAMERA_TO_OPTICAL.translation_xyz == (0.0, 0.0, 0.0)
    assert CAMERA_TO_OPTICAL.rpy == (-1.57079633, 0.0, -1.57079633)

    nodes = camera_static_transform_nodes()
    assert len(nodes) == 2
    assert all(isinstance(node, Node) for node in nodes)
    for node, spec in zip(nodes, (BASE_TO_CAMERA, CAMERA_TO_OPTICAL)):
        assert node.node_package == "tf2_ros"
        assert node.node_executable == "static_transform_publisher"
        assert [value.text for value in node.output] == ["both"]
        assert node._Node__node_name == spec.name
        assert node._Node__arguments == spec.arguments()
