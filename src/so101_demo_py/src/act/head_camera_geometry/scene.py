"""The MuJoCo head camera scene used by the geometry validation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from pathlib import Path
from typing import Any

from so101_demo.act.head_camera_geometry.contract import (
    ARM_JOINT_NAMES,
    DISTORTION_COEFFICIENTS,
    DISTORTION_MODEL,
    HeadCameraAnchor,
    HeadCameraGeometryContract,
    HeadCameraGeometryError,
    HeadCameraScenePort,
    _refine_boundary,
    scene_source_digests,
)


def _safe_interval(
    port: HeadCameraScenePort, contract: HeadCameraGeometryContract
) -> tuple[float, float] | None:
    grid = contract.neck_grid()
    safe_flags = [bool(port.safe_at_neck(angle)) for angle in grid]
    starts = [0.0] + [anchor.neck_start_rad for anchor in contract.anchors]
    required_indices = {
        min(range(len(grid)), key=lambda index: abs(grid[index] - start)) for start in starts
    }
    if any(not safe_flags[index] for index in required_indices):
        return None

    runs: list[tuple[int, int]] = []
    index = 0
    while index < len(grid):
        if not safe_flags[index]:
            index += 1
            continue
        start_index = index
        while index + 1 < len(grid) and safe_flags[index + 1]:
            index += 1
        runs.append((start_index, index))
        index += 1

    containing = [run for run in runs if all(run[0] <= item <= run[1] for item in required_indices)]
    if len(containing) != 1:
        return None
    start_index, end_index = containing[0]
    low = grid[start_index]
    high = grid[end_index]
    if start_index > 0:
        low = _refine_boundary(port, grid[start_index - 1], grid[start_index], contract)
    if end_index + 1 < len(grid):
        high = _refine_boundary(port, grid[end_index + 1], grid[end_index], contract)
    margin = contract.safe_interval_margin_rad
    return (low + margin, high - margin)


class _MuJoCoHeadCameraScene:
    """The production scene, read through MuJoCo: poses, safety, target points and rendered visibility."""

    def __init__(self, scene_path: Path, contract: HeadCameraGeometryContract) -> None:
        import mujoco

        scene = Path(scene_path)
        if not scene.is_file():
            raise HeadCameraGeometryError(f"HEAD_CAMERA_SCENE_MISSING: {scene}")
        self._mujoco = mujoco
        self._scene = scene
        self._contract = contract
        self._model = mujoco.MjModel.from_xml_path(str(scene))
        self._data = mujoco.MjData(self._model)
        self._camera_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_CAMERA, contract.camera_name
        )
        if self._camera_id < 0:
            raise HeadCameraGeometryError(
                f"HEAD_CAMERA_CAMERA_MISSING: {contract.camera_name} is not in {scene}"
            )
        self._neck_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_JOINT, contract.neck_joint
        )
        if self._neck_id < 0:
            raise HeadCameraGeometryError(
                f"HEAD_CAMERA_NECK_MISSING: {contract.neck_joint} is not in {scene}"
            )
        self._neck_qpos_adr = int(self._model.jnt_qposadr[self._neck_id])
        self._arm_qpos_adr = []
        for joint_name in ARM_JOINT_NAMES:
            joint_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, joint_name)
            if joint_id < 0:
                raise HeadCameraGeometryError(
                    f"HEAD_CAMERA_ARM_JOINT_MISSING: the scene names no joint {joint_name!r}"
                )
            limit = self._model.jnt_range[joint_id]
            value = float(contract.validation_arm_rad[len(self._arm_qpos_adr)])
            if not float(limit[0]) - 1e-9 <= value <= float(limit[1]) + 1e-9:
                raise HeadCameraGeometryError(
                    f"HEAD_CAMERA_ARM_POSE_INVALID: joint {joint_name} at {value} is outside "
                    f"[{float(limit[0])}, {float(limit[1])}]"
                )
            self._arm_qpos_adr.append(int(self._model.jnt_qposadr[joint_id]))
        self._cup_body_id = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_BODY, "plastic_cup")
        if self._cup_body_id < 0:
            raise HeadCameraGeometryError("HEAD_CAMERA_TARGET_GEOMETRY_MISSING: plastic_cup")
        self._cup_joint_id = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint"
        )
        self._cup_qpos_adr = (
            0 if self._cup_joint_id < 0 else int(self._model.jnt_qposadr[self._cup_joint_id])
        )
        self._renderer = None
        self._segmentation_renderer = None
        self._robot_bodies = self._descendants_of_robot()
        self._prepare_clearance()

    def source_digests(self) -> Mapping[str, str]:
        return scene_source_digests(self._scene)

    def camera_document(self) -> Mapping[str, Any]:
        model = self._model
        camera_id = self._camera_id
        fovy = float(model.cam_fovy[camera_id]) * math.pi / 180.0
        position = [float(value) for value in model.cam_pos[camera_id]]
        rotation = [float(value) for value in model.cam_mat0[camera_id].reshape(9)]
        axes = [
            rotation[0],
            rotation[3],
            rotation[6],
            rotation[1],
            rotation[4],
            rotation[7],
        ]
        body_name = self._mujoco.mj_id2name(
            model, self._mujoco.mjtObj.mjOBJ_BODY, int(model.cam_bodyid[camera_id])
        )
        return {
            "camera_name": self._contract.camera_name,
            "width": int(model.cam_resolution[camera_id][0]),
            "height": int(model.cam_resolution[camera_id][1]),
            "fovy_rad": fovy,
            "distortion_model": DISTORTION_MODEL,
            "distortion": list(DISTORTION_COEFFICIENTS),
            "parent_body": str(body_name),
            "local_position_m": position,
            "local_xyaxes": axes,
        }

    def _pose_neck(self, neck_rad: float) -> None:
        self._mujoco.mj_resetData(self._model, self._data)
        for index, joint_name in enumerate(ARM_JOINT_NAMES):
            self._data.qpos[self._arm_qpos_adr[index]] = float(
                self._contract.validation_arm_rad[index]
            )
        self._data.qpos[self._neck_qpos_adr] = float(neck_rad)
        if self._cup_joint_id >= 0:
            # the anchor's own cup position is set by `target_points_m`; here the model is advanced
            # with the neck exactly where the caller asked for it
            pass
        self._mujoco.mj_forward(self._model, self._data)

    def camera_world_pose(self, neck_rad: float):
        self._pose_neck(neck_rad)
        position = [float(value) for value in self._data.cam_xpos[self._camera_id]]
        rotation = [
            [float(value) for value in row]
            for row in self._data.cam_xmat[self._camera_id].reshape(3, 3)
        ]
        return (position, rotation)

    def target_points_m(self, anchor: HeadCameraAnchor) -> tuple[tuple[float, float, float], ...]:
        self._pose_neck(anchor.neck_start_rad)
        if self._cup_joint_id >= 0:
            self._data.qpos[self._cup_qpos_adr : self._cup_qpos_adr + 3] = anchor.cup_start_m
            self._data.qpos[self._cup_qpos_adr + 3 : self._cup_qpos_adr + 7] = (1.0, 0.0, 0.0, 0.0)
            self._mujoco.mj_forward(self._model, self._data)
        minima = [math.inf] * 3
        maxima = [-math.inf] * 3
        for index in range(self._model.ngeom):
            if int(self._model.geom_bodyid[index]) != self._cup_body_id:
                continue
            centre = [float(value) for value in self._data.geom_xpos[index]]
            radius = float(max(self._model.geom_size[index]))
            for axis in range(3):
                minima[axis] = min(minima[axis], centre[axis] - radius)
                maxima[axis] = max(maxima[axis], centre[axis] + radius)
        points = [tuple((minima[axis] + maxima[axis]) / 2.0 for axis in range(3))]
        for x in (minima[0], maxima[0]):
            for y in (minima[1], maxima[1]):
                for z in (minima[2], maxima[2]):
                    points.append((x, y, z))
        return tuple(points)

    def neck_angle_for_point(self, point_m: Sequence[float]) -> float:
        self._pose_neck(0.0)
        mount = self._data.xpos[self._model.cam_bodyid[self._camera_id]]
        return math.atan2(
            float(point_m[0]) - float(mount[0]), -(float(point_m[1]) - float(mount[1]))
        )

    def safe_at_neck(self, neck_rad: float) -> bool:
        self._pose_neck(neck_rad)
        data = self._data
        for index in range(int(data.ncon)):
            contact = data.contact[index]
            if self._is_head_geom(int(contact.geom1)) or self._is_head_geom(int(contact.geom2)):
                return False
        margin = 0.005
        for index in self._head_geoms:
            centre = data.geom_xpos[index]
            radius = float(self._geom_radius[index])
            for other in self._clearance_candidates[index]:
                other_centre = data.geom_xpos[other]
                reach = radius + float(self._geom_radius[other]) + margin
                if (centre[0] - other_centre[0]) ** 2 + (centre[1] - other_centre[1]) ** 2 + (
                    centre[2] - other_centre[2]
                ) ** 2 > reach * reach:
                    continue
                if (
                    self._mujoco.mj_geomDistance(self._model, data, index, other, margin, None)
                    < margin - 1e-9
                ):
                    return False
        return True

    def _descendants_of_robot(self) -> frozenset[int]:
        """Every body that belongs to the robot the head camera is mounted on."""

        base_id = self._mujoco.mj_name2id(self._model, self._mujoco.mjtObj.mjOBJ_BODY, "base")
        if base_id < 0:
            return frozenset()
        bodies = set()
        for body in range(self._model.nbody):
            ancestor = body
            while ancestor > 0 and ancestor != base_id:
                ancestor = int(self._model.body_parentid[ancestor])
            if ancestor == base_id:
                bodies.add(body)
        return frozenset(bodies)

    def _prepare_clearance(self) -> None:
        """The static candidate pairs: geoms the rotating head could come within the margin of."""

        model = self._model
        data = self._data
        self._pose_neck(0.0)
        self._geom_radius = [
            float(max(model.geom_size[index]))
            if float(max(model.geom_size[index])) > 0.0
            else 0.001
            for index in range(model.ngeom)
        ]
        self._head_geoms = [index for index in range(model.ngeom) if self._is_head_geom(index)]
        axis = data.xpos[int(model.cam_bodyid[self._camera_id])]
        head_reach = max(
            (
                float(
                    (
                        (float(data.geom_xpos[index][0]) - float(axis[0])) ** 2
                        + (float(data.geom_xpos[index][1]) - float(axis[1])) ** 2
                    )
                    ** 0.5
                )
                + self._geom_radius[index]
                for index in self._head_geoms
            ),
            default=0.05,
        )
        self._clearance_candidates = {}
        for index in self._head_geoms:
            candidates = []
            for other in range(model.ngeom):
                if other == index or self._is_head_geom(other):
                    continue
                radial = (
                    (float(data.geom_xpos[other][0]) - float(axis[0])) ** 2
                    + (float(data.geom_xpos[other][1]) - float(axis[1])) ** 2
                ) ** 0.5
                if radial <= head_reach + self._geom_radius[other] + 0.02:
                    candidates.append(other)
            self._clearance_candidates[index] = tuple(candidates)

    def _is_head_geom(self, geom_id: int) -> bool:
        body = int(self._model.geom_bodyid[geom_id])
        head_body = int(self._model.cam_bodyid[self._camera_id])
        while body != 0 and body != head_body:
            body = int(self._model.body_parentid[body])
        return body == head_body

    def camera_mount_pose(self) -> tuple[Sequence[float], Sequence[float]]:
        """The mount body's world origin and its x/y axes at neck zero: the pose model of the seal."""

        self._pose_neck(0.0)
        body_id = int(self._model.cam_bodyid[self._camera_id])
        origin = [float(value) for value in self._data.xpos[body_id]]
        matrix = self._data.xmat[body_id].reshape(3, 3)
        axes = [
            float(matrix[0][0]),
            float(matrix[1][0]),
            float(matrix[2][0]),
            float(matrix[0][1]),
            float(matrix[1][1]),
            float(matrix[2][1]),
        ]
        return (origin, axes)

    def support_height_m(self) -> float:
        """The support surface the workspace rests on, read from the scene's own table geom."""

        self._pose_neck(0.0)
        for name in ("table_visual", "table_collision"):
            geom_id = self._mujoco.mj_name2id(self._model, self._mujoco.mjtObj.mjOBJ_GEOM, name)
            if geom_id >= 0:
                return float(self._data.geom_xpos[geom_id][2]) + float(
                    self._model.geom_size[geom_id][2]
                )
        raise HeadCameraGeometryError(
            "HEAD_CAMERA_SUPPORT_MISSING: the scene names no support geom (table_visual)"
        )

    def target_rest_offset_m(self) -> float:
        """How high the target's centre sits above that support when it rests on it."""

        self._pose_neck(0.0)
        return float(self._data.xpos[self._cup_body_id][2]) - self.support_height_m()

    def visible_pixels_for_point(self, point_m: Sequence[float], neck_rad: float) -> int:
        return self._render_cup_pixels(tuple(float(value) for value in point_m), float(neck_rad))

    def endpoint_visibility(self, point_m: Sequence[float], neck_rad: float) -> Mapping[str, Any]:
        """Is the required-domain endpoint visible to this camera, robot pose aside?

        The ray is cast from the camera to the point with the camera's own body excluded. If the first
        thing it meets is the target, the endpoint is visible; if it is the robot, then only the robot
        the camera rides on stands in the way, and whether the arm is there is a property of the
        admitted trajectory rather than of this camera. Anything else in between is a real occlusion.
        """

        import numpy as np

        self._pose_neck(neck_rad)
        origin = np.array(self._data.cam_xpos[self._camera_id], dtype=np.float64)
        target = np.array([float(value) for value in point_m], dtype=np.float64)
        direction = target - origin
        distance = float(np.linalg.norm(direction))
        if distance <= 0.0:
            return {"first_hit_body": None, "visible_to_camera": False, "robot_occluded": False}
        direction = direction / distance
        hit_geom = np.zeros(1, dtype=np.int32)
        reached = self._mujoco.mj_ray(
            self._model,
            self._data,
            origin,
            direction,
            None,
            1,
            int(self._model.cam_bodyid[self._camera_id]),
            hit_geom,
        )
        if reached <= 0.0 or reached >= distance - 1e-9:
            # the open top of a cup means a ray to its centre may meet nothing before the centre, and
            # whatever it meets beyond the centre is not between the camera and the target
            return {"first_hit_body": None, "visible_to_camera": True, "robot_occluded": False}
        geom_id = int(hit_geom[0])
        body_id = int(self._model.geom_bodyid[geom_id])
        body_name = self._mujoco.mj_id2name(self._model, self._mujoco.mjtObj.mjOBJ_BODY, body_id)
        robot_occluded = body_id in self._robot_bodies
        return {
            "first_hit_body": None if body_name is None else str(body_name),
            "visible_to_camera": body_id == self._cup_body_id or robot_occluded,
            "robot_occluded": robot_occluded,
        }

    def target_clear_of_support(self, point_m: Sequence[float]) -> bool:
        """Would the target at this point intersect what it is supposed to rest on?"""

        self._place_cup(point_m)
        for index in range(int(self._data.ncon)):
            contact = self._data.contact[index]
            for geom_id in (int(contact.geom1), int(contact.geom2)):
                if int(self._model.geom_bodyid[geom_id]) == self._cup_body_id:
                    return False
        return True

    def _place_cup(self, point_m: Sequence[float]) -> None:
        self._pose_neck(0.0)
        if self._cup_joint_id >= 0:
            self._data.qpos[self._cup_qpos_adr : self._cup_qpos_adr + 3] = [
                float(value) for value in point_m
            ]
            self._data.qpos[self._cup_qpos_adr + 3 : self._cup_qpos_adr + 7] = (1.0, 0.0, 0.0, 0.0)
            self._mujoco.mj_forward(self._model, self._data)

    def visible_pixels(self, anchor: HeadCameraAnchor, neck_rad: float) -> int:
        return self._render_cup_pixels(anchor.cup_start_m, float(neck_rad))

    def _render_cup_pixels(self, cup_position_m: Sequence[float], neck_rad: float) -> int:
        import numpy as np

        self._pose_neck(neck_rad)
        if self._cup_joint_id >= 0:
            self._data.qpos[self._cup_qpos_adr : self._cup_qpos_adr + 3] = cup_position_m
            self._data.qpos[self._cup_qpos_adr + 3 : self._cup_qpos_adr + 7] = (1.0, 0.0, 0.0, 0.0)
            self._mujoco.mj_forward(self._model, self._data)
        if self._segmentation_renderer is None:
            self._segmentation_renderer = self._mujoco.Renderer(
                self._model,
                height=self._contract.image_height,
                width=self._contract.image_width,
            )
        self._segmentation_renderer.enable_segmentation_rendering()
        try:
            self._segmentation_renderer.update_scene(self._data, camera=self._contract.camera_name)
            segmentation = np.asarray(self._segmentation_renderer.render())
        finally:
            self._segmentation_renderer.disable_segmentation_rendering()
        geom_type = int(self._mujoco.mjtObj.mjOBJ_GEOM)
        # the object-ID render puts the type in one channel and the id in the other, and which is
        # which is not fixed - the same reading the dataset renderer uses
        first_is_type = segmentation[:, :, 0] == geom_type
        second_is_type = segmentation[:, :, 1] == geom_type
        ids = np.full(segmentation.shape[:2], -1, dtype=np.int32)
        if int(first_is_type.sum()) >= int(second_is_type.sum()):
            ids[first_is_type] = segmentation[:, :, 1][first_is_type]
        else:
            ids[second_is_type] = segmentation[:, :, 0][second_is_type]
        mask = np.zeros(segmentation.shape[:2], dtype=bool)
        for index in range(self._model.ngeom):
            if int(self._model.geom_bodyid[index]) == self._cup_body_id:
                mask |= ids == index
        return int(mask.sum())
