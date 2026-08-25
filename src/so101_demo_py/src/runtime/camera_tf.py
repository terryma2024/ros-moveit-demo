"""The static camera-frame contract shared by the MuJoCo perception launch."""

from __future__ import annotations

from dataclasses import dataclass

from launch_ros.actions import Node


@dataclass(frozen=True, slots=True)
class StaticTransformSpec:
    """One immutable ``tf2_ros static_transform_publisher`` specification."""

    name: str
    parent_frame: str
    child_frame: str
    translation_xyz: tuple[float, float, float]
    rpy: tuple[float, float, float]

    def arguments(self) -> list[str]:
        x, y, z = self.translation_xyz
        roll, pitch, yaw = self.rpy
        return [
            "--x",
            str(x),
            "--y",
            str(y),
            "--z",
            str(z),
            "--roll",
            str(roll),
            "--pitch",
            str(pitch),
            "--yaw",
            str(yaw),
            "--frame-id",
            self.parent_frame,
            "--child-frame-id",
            self.child_frame,
        ]


BASE_TO_CAMERA = StaticTransformSpec(
    "so101_base_to_camera_link",
    "base",
    "camera_link",
    (0.65, -0.65, 0.3600814),
    (0.0, 0.517, 2.35619449),
)

CAMERA_TO_OPTICAL = StaticTransformSpec(
    "so101_camera_link_to_task_camera_frame",
    "camera_link",
    "task_camera_frame",
    (0.0, 0.0, 0.0),
    (-1.57079633, 0.0, -1.57079633),
)


def camera_static_transform_nodes() -> list[Node]:
    """Build the two approved static transforms for a launch description."""

    return [
        Node(
            package="tf2_ros",
            executable="static_transform_publisher",
            name=spec.name,
            arguments=spec.arguments(),
            output="both",
        )
        for spec in (BASE_TO_CAMERA, CAMERA_TO_OPTICAL)
    ]
