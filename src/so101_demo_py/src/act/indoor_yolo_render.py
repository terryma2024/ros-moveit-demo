"""Render one plan entry of `indoor_yolo_dataset` with MuJoCo: RGB, cup segmentation mask (sim truth) and depth of the `task_camera`.

The scene of an entry is the indoor nominal (layout A) with the entry's scene-variant applied through `scene_variant.realize` (B and C
through `indoor_yolo_dataset.materialize_layout`), the dark nominal `scene_side_wrist.xml`, or the indoor nominal unchanged. The robot is
at the `task_start` keyframe; the cup free joint is moved to the entry's xy (the cup rests on the table at the keyframe height).
The mask is every geom of the cup body in a segmentation render, so it is exactly what the camera sees of the cup, occluders included.
Needs MuJoCo and an offscreen GL (`MUJOCO_GL=osmesa` or `egl`) and imports MuJoCo lazily.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from so101_demo.act import indoor_yolo_dataset as dataset
from so101_demo.act import scene_variant

CAMERA = "task_camera"
CUP_BODY = "plastic_cup"
CUP_JOINT = "cup_free_joint"
KEYFRAME = "task_start"
WIDTH, HEIGHT = 640, 480


@dataclass(frozen=True)
class Frame:
    rgb: np.ndarray
    mask: np.ndarray
    depth: np.ndarray
    cup_xy: list
    camera: dict
    realized_sha256: str | None
    cup_rgba: list


class IndoorFrameRenderer:
    def __init__(self, act_assets: Path, work_dir: Path, width: int = WIDTH, height: int = HEIGHT) -> None:
        import mujoco

        self._mujoco = mujoco
        self.act_assets, self.work_dir = Path(act_assets), Path(work_dir)
        self.width, self.height = width, height
        self._nominal_dirs = {}

    def close(self) -> None:
        pass

    def _nominal_dir(self, layout: str) -> Path:
        if layout not in self._nominal_dirs:
            self._nominal_dirs[layout] = dataset.materialize_layout(self.act_assets, layout, self.work_dir / f"layout-{layout}")
        return self._nominal_dirs[layout]

    def _scene_path(self, entry: dict):
        if entry["layout"] == "dark":
            return self.act_assets / dataset.DARK_SCENE, None
        if entry["variant"] is None:
            return self.act_assets / dataset.NOMINAL_SCENE, None
        realized = scene_variant.realize(self._nominal_dir(entry["layout"]), entry["variant"])
        path = self.work_dir / "realized" / f"{entry['sample_id']}.xml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(realized.xml_text, encoding="utf-8")
        return path, realized.realized_sha256

    def render(self, entry: dict) -> Frame:
        mujoco = self._mujoco
        path, realized_sha256 = self._scene_path(entry)
        model = mujoco.MjModel.from_xml_path(str(path))
        data = mujoco.MjData(model)
        mujoco.mj_resetDataKeyframe(model, data, mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, KEYFRAME))
        joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, CUP_JOINT)
        address = model.jnt_qposadr[joint]
        data.qpos[address:address + 2] = entry["cup_xy"]
        if entry.get("cup_hidden"):
            data.qpos[address + 2] = dataset.CUP_HIDDEN_Z_M          # below the room: a negative frame still has the ring and the shadows
        mujoco.mj_forward(model, data)
        body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, CUP_BODY)
        cup_geoms = np.flatnonzero(model.geom_bodyid == body)
        camera = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, CAMERA)
        renderer = mujoco.Renderer(model, self.height, self.width)
        try:
            renderer.update_scene(data, camera=CAMERA)
            rgb = np.array(renderer.render(), copy=True)
            renderer.enable_depth_rendering()
            renderer.update_scene(data, camera=CAMERA)
            depth = np.array(renderer.render(), copy=True).astype(np.float32)
            renderer.disable_depth_rendering()
            renderer.enable_segmentation_rendering()
            renderer.update_scene(data, camera=CAMERA)
            segmentation = np.array(renderer.render(), copy=True)
            renderer.disable_segmentation_rendering()
        finally:
            renderer.close()
        geom_type = int(mujoco.mjtObj.mjOBJ_GEOM)
        geom_ids = np.where(segmentation[..., 1] == geom_type, segmentation[..., 0], -1)       # channel 0: object id, channel 1: object type
        mask = np.isin(geom_ids, cup_geoms)
        material = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_MATERIAL, "cup_orange")
        return Frame(rgb=rgb, mask=mask, depth=depth, cup_xy=[float(value) for value in data.qpos[address:address + 2]],
                     camera={"pos": data.cam_xpos[camera].tolist(), "mat": data.cam_xmat[camera].tolist(),
                             "fovy": float(model.cam_fovy[camera]), "width": self.width, "height": self.height},
                     realized_sha256=realized_sha256, cup_rgba=[float(value) for value in model.mat_rgba[material]])
