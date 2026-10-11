"""The MuJoCo dataset renderer."""

from __future__ import annotations

import math

import numpy as np

from so101_demo.adapters.perception.mujoco_dataset.config import DatasetConfig, RendererSettings
from so101_demo.adapters.perception.mujoco_dataset.models import (
    DatasetScenario,
    RawRender,
    RenderEventSink,
    _emit_render_event,
)
from so101_demo.adapters.perception.mujoco_dataset.render import select_bounded_render
from so101_demo.adapters.perception.mujoco_scene_geometry import (
    ScenePenetrationError,
    measure_task_scene_geometry,
)


class MuJoCoDatasetRenderer:
    """Lazy MuJoCo renderer; segmentation is derived only from geom/body IDs."""

    def __init__(self, config: DatasetConfig | RendererSettings) -> None:
        try:
            import mujoco
        except ImportError as error:
            raise RuntimeError("MuJoCo Python binding is required for dataset rendering") from error
        self._mujoco = mujoco
        self._config = config.renderer_settings() if isinstance(config, DatasetConfig) else config
        self._model = mujoco.MjModel.from_xml_path(str(self._config.mjcf_path))
        self._data = mujoco.MjData(self._model)
        self._renderer = mujoco.Renderer(
            self._model,
            height=self._config.image_height,
            width=self._config.image_width,
        )
        # Color IDs are categorical: resolving multisamples can invent another
        # valid geom ID at an edge. Keep RGB antialiasing in its original context.
        self._segmentation_renderer = None
        rgb_samples = self._model.vis.quality.offsamples
        try:
            try:
                self._model.vis.quality.offsamples = 0
                self._segmentation_renderer = mujoco.Renderer(
                    self._model,
                    height=self._config.image_height,
                    width=self._config.image_width,
                )
                if self._segmentation_renderer._mjr_context.offSamples != 0:
                    raise RuntimeError("CATEGORICAL_MULTISAMPLING_FORBIDDEN")
            finally:
                self._model.vis.quality.offsamples = rgb_samples
        except Exception:
            self.close()
            raise
        self._neck_rad: float | None = None
        self._arm_rad: tuple[float, ...] | None = None
        self._base_camera_position = np.array(self._model.cam_pos[self._camera_id()], copy=True)
        camera_rotation = np.asarray(self._model.cam_mat0[self._camera_id()]).reshape(3, 3)
        self._camera_local_positive_z = np.array(camera_rotation[:, 2], copy=True)
        self._camera_local_positive_z /= np.linalg.norm(self._camera_local_positive_z)

    def _camera_id(self) -> int:
        identifier = self._mujoco.mj_name2id(
            self._model,
            self._mujoco.mjtObj.mjOBJ_CAMERA,
            self._config.camera_name,
        )
        if identifier < 0:
            raise RuntimeError(f"camera not found: {self._config.camera_name}")
        return int(identifier)

    def _set_free_joint_position(self, joint_name: str, xyz: np.ndarray) -> None:
        identifier = self._mujoco.mj_name2id(
            self._model,
            self._mujoco.mjtObj.mjOBJ_JOINT,
            joint_name,
        )
        if identifier < 0:
            raise RuntimeError(f"free joint not found: {joint_name}")
        address = int(self._model.jnt_qposadr[identifier])
        self._data.qpos[address : address + 3] = xyz
        self._data.qpos[address + 3 : address + 7] = (1.0, 0.0, 0.0, 0.0)
        dof_address = int(self._model.jnt_dofadr[identifier])
        self._data.qvel[dof_address : dof_address + 6] = 0.0

    def _prepare(self, random: np.random.Generator, scenario: DatasetScenario) -> None:
        self._mujoco.mj_resetData(self._model, self._data)
        geometry = self._config.geometry
        hidden = np.array((2.0, 2.0, 2.0))
        cup_a = np.array((0.02, -0.28, 0.165))
        cup_a_jitter = (
            geometry.partial_cup_xy_jitter_m
            if scenario == DatasetScenario.PARTIALLY_OCCLUDED_CUP
            else geometry.cup_a_xy_jitter_m
        )
        cup_a[:2] += random.uniform(*cup_a_jitter, size=2)
        cup_b = np.array((-0.09, -0.31, 0.165))
        cup_b[:2] += random.uniform(*geometry.cup_b_xy_jitter_m, size=2)
        bottle = np.array((0.11, -0.22, 0.19))
        bottle[:2] += random.uniform(*geometry.bottle_xy_jitter_m, size=2)
        if scenario == DatasetScenario.CUP_NEAR_BOTTLE:
            bottle[:2] = cup_a[:2] + np.array((0.075, 0.0))
        camera_id = self._camera_id()
        jitter = (
            geometry.ordinary_camera_jitter_m
            if self._config.camera_jitter_m is None
            else self._config.camera_jitter_m
        )
        camera_position = self._base_camera_position + random.uniform(*jitter, size=3)
        if scenario == DatasetScenario.SMALL_FAR_CUP:
            camera_position += self._camera_local_positive_z * random.uniform(
                *geometry.far_camera_retreat_m
            )
        if scenario == DatasetScenario.PARTIALLY_OCCLUDED_CUP:
            toward_camera = camera_position[:2] - cup_a[:2]
            toward_camera /= np.linalg.norm(toward_camera)
            perpendicular = np.array((-toward_camera[1], toward_camera[0]))
            bottle[:2] = (
                cup_a[:2]
                + toward_camera * random.uniform(*geometry.partial_bottle_longitudinal_m)
                + perpendicular * random.uniform(*geometry.partial_bottle_perpendicular_m)
            )
        self._set_free_joint_position(
            "cup_free_joint", cup_a if scenario.cup_count >= 1 else hidden
        )
        self._set_free_joint_position(
            "cup_b_free_joint", cup_b if scenario.cup_count == 2 else hidden
        )
        self._set_free_joint_position("bottle_free_joint", bottle)
        self._neck_rad = None
        self._arm_rad = None
        if self._config.arm_pose_rad is not None:
            values = tuple(float(value) for value in self._config.arm_pose_rad)
            for index, joint_name in enumerate(("1", "2", "3", "4", "5", "6")):
                if index >= len(values):
                    break
                joint_id = self._mujoco.mj_name2id(
                    self._model, self._mujoco.mjtObj.mjOBJ_JOINT, joint_name
                )
                if joint_id < 0:
                    raise RuntimeError(f"arm joint not found: {joint_name}")
                self._data.qpos[int(self._model.jnt_qposadr[joint_id])] = values[index]
            self._arm_rad = values
        if self._config.neck_yaw_rad is not None:
            low, high = self._config.neck_yaw_rad
            neck_id = self._mujoco.mj_name2id(
                self._model, self._mujoco.mjtObj.mjOBJ_JOINT, "neck_yaw_joint"
            )
            if neck_id < 0:
                raise RuntimeError("neck joint not found: neck_yaw_joint")
            self._neck_rad = float(random.uniform(low, high))
            self._data.qpos[int(self._model.jnt_qposadr[neck_id])] = self._neck_rad
        self._model.cam_pos[camera_id] = camera_position
        for material_name in ("cup_a_material", "cup_b_material", "bottle_material"):
            material_id = self._mujoco.mj_name2id(
                self._model,
                self._mujoco.mjtObj.mjOBJ_MATERIAL,
                material_name,
            )
            if material_id >= 0:
                self._model.mat_rgba[material_id, :3] = random.uniform(0.1, 1.0, size=3)
        self._mujoco.mj_forward(self._model, self._data)

    def _geom_ids(self, segmentation: np.ndarray) -> np.ndarray:
        if segmentation.ndim != 3 or segmentation.shape[2] != 2:
            raise RuntimeError("MuJoCo segmentation render must have HxWx2 dimensions")
        geom_type = int(self._mujoco.mjtObj.mjOBJ_GEOM)
        first_is_type = segmentation[:, :, 0] == geom_type
        second_is_type = segmentation[:, :, 1] == geom_type
        result = np.full(segmentation.shape[:2], -1, dtype=np.int32)
        if int(first_is_type.sum()) >= int(second_is_type.sum()):
            result[first_is_type] = segmentation[:, :, 1][first_is_type]
        else:
            result[second_is_type] = segmentation[:, :, 0][second_is_type]
        return result

    def _segmentation(self) -> np.ndarray:
        renderer = self._segmentation_renderer
        renderer.enable_segmentation_rendering()
        try:
            renderer.update_scene(self._data, camera=self._config.camera_name)
            segmentation = np.array(renderer.render(), copy=True)
        finally:
            renderer.disable_segmentation_rendering()
        return self._geom_ids(segmentation)

    def _render_attempt(
        self,
        random: np.random.Generator,
        scenario: DatasetScenario,
        *,
        seed: int,
        attempt_index: int,
        event_sink: RenderEventSink | None = None,
    ) -> RawRender:
        self._prepare(random, scenario)
        geometry_receipt = None
        if self._config.require_nonpenetrating_scene:
            geometry_receipt = measure_task_scene_geometry(
                self._model, self._data, active_cup_count=scenario.cup_count
            )
            _emit_render_event(
                event_sink,
                "geometry_measured",
                seed,
                scenario,
                attempt_index,
                geometry_receipt,
            )
            if not geometry_receipt.accepted:
                _emit_render_event(
                    event_sink,
                    "penetration_rejected",
                    seed,
                    scenario,
                    attempt_index,
                    geometry_receipt,
                )
                raise ScenePenetrationError(
                    "intersecting task visual solids",
                    receipt=geometry_receipt,
                    seed=seed,
                    scenario=scenario,
                    attempt_index=attempt_index,
                )
        _emit_render_event(
            event_sink,
            "rgb_render_started",
            seed,
            scenario,
            attempt_index,
            geometry_receipt,
        )
        self._renderer.disable_segmentation_rendering()
        self._renderer.update_scene(self._data, camera=self._config.camera_name)
        rgb = np.array(self._renderer.render(), dtype=np.uint8, copy=True)
        _emit_render_event(
            event_sink,
            "rgb_render_finished",
            seed,
            scenario,
            attempt_index,
            geometry_receipt,
        )
        _emit_render_event(
            event_sink,
            "segmentation_render_started",
            seed,
            scenario,
            attempt_index,
            geometry_receipt,
        )
        visible_geom_ids = self._segmentation()
        _emit_render_event(
            event_sink,
            "segmentation_render_finished",
            seed,
            scenario,
            attempt_index,
            geometry_receipt,
        )
        amodal_geom_ids = None
        occluder_body_name = None
        occlusion_reference = None
        if scenario == DatasetScenario.PARTIALLY_OCCLUDED_CUP:
            self._set_free_joint_position("bottle_free_joint", np.array((2.0, 2.0, 2.0)))
            self._mujoco.mj_forward(self._model, self._data)
            _emit_render_event(
                event_sink,
                "segmentation_render_started",
                seed,
                scenario,
                attempt_index,
                geometry_receipt,
            )
            amodal_geom_ids = self._segmentation()
            _emit_render_event(
                event_sink,
                "segmentation_render_finished",
                seed,
                scenario,
                attempt_index,
                geometry_receipt,
            )
            occluder_body_name = "orange_bottle"
            occlusion_reference = "visible_union_paired_segmentation_with_declared_occluder_hidden"
        body_names = {
            body_id: name
            for body_id in range(self._model.nbody)
            if (
                name := self._mujoco.mj_id2name(
                    self._model, self._mujoco.mjtObj.mjOBJ_BODY, body_id
                )
            )
            is not None
        }
        camera_id = self._camera_id()
        camera_quaternion = np.zeros(4, dtype=np.float64)
        self._mujoco.mju_mat2Quat(camera_quaternion, self._data.cam_xmat[camera_id])
        return RawRender(
            rgb8=rgb,
            geom_ids=visible_geom_ids,
            geom_body_ids=np.asarray(self._model.geom_bodyid),
            body_names=body_names,
            amodal_geom_ids=amodal_geom_ids,
            occluder_body_name=occluder_body_name,
            occlusion_reference=occlusion_reference,
            geometry_receipt=geometry_receipt,
            camera_name=self._config.camera_name,
            neck_rad=self._neck_rad,
            camera_position_m=tuple(float(value) for value in self._data.cam_xpos[camera_id]),
            camera_quaternion_wxyz=tuple(float(value) for value in camera_quaternion),
            camera_local_position_m=tuple(float(value) for value in self._model.cam_pos[camera_id]),
            camera_local_xyaxes=_local_xyaxes(self._model.cam_mat0[camera_id]),
            camera_fovy_rad=float(self._model.cam_fovy[camera_id]) * math.pi / 180.0,
            arm_pose_rad=self._arm_rad,
        )

    def render(
        self,
        seed: int,
        scenario: DatasetScenario,
        *,
        event_sink: RenderEventSink | None = None,
    ) -> RawRender:
        attempt_index = -1

        def render_attempt(random: np.random.Generator) -> RawRender:
            nonlocal attempt_index
            attempt_index += 1
            return self._render_attempt(
                random,
                scenario,
                seed=seed,
                attempt_index=attempt_index,
                event_sink=event_sink,
            )

        return select_bounded_render(
            seed,
            scenario,
            render_attempt,
            self._config.geometry,
            require_nonpenetrating_scene=self._config.require_nonpenetrating_scene,
            event_sink=event_sink,
        )

    def close(self) -> None:
        try:
            if self._segmentation_renderer is not None:
                self._segmentation_renderer.close()
        finally:
            self._renderer.close()


def _local_xyaxes(matrix: object) -> tuple[float, ...]:
    """A camera's local frame as the MJCF's own (xaxis, yaxis) six numbers, not the 3x3 matrix."""

    values = [float(value) for value in matrix]  # type: ignore[union-attr]
    if len(values) != 9:
        raise ValueError("camera orientation matrix must hold nine numbers")
    return (
        values[0],
        values[3],
        values[6],
        values[1],
        values[4],
        values[7],
    )
