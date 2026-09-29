"""P1-1 (rereview 5), first half: the bottom-I/O values the formal entry must build for ITSELF.

The verdict's finding is that the formal entry reaches `SO101_TASK8_BOTTOM_IO_SEAM` for six values - the client, the
detector factory, the frame source, the phase path, the target and the occluder geometry - so with nothing set in the
environment it cannot produce the bottom I/O at all. This module starts replacing those six with the model's own
answers, beginning with the two the headless model can supply directly.

**And it starts with the one where the seam's substitute is provably not the model's answer.** The seam hands the
evaluator the same invented geometry for every occluder:

    {"fixed_fingertip_00": {"position_m": [0.02, 0.0, 0.10], "radius_m": 0.005}}

while the ACT scene's own geoms are at entirely different places - `fixed_fingertip_pad_visual` at
`[0.0204, -0.3623, 0.4491]`, `moving_fingertip_pad_visual` at `[0.0205, -0.3721, 0.4632]`. A visibility decision made
against the seam's numbers is a decision about a scene that does not exist.
"""

from __future__ import annotations

from pathlib import Path


class BottomIOError(ValueError):
    """A bottom-I/O value the composition cannot build, named so a caller can refuse by name."""


def occluder_geometry_from_model(scene_path, names=None, *, joints_rad=None) -> dict:
    """The admitted occluders' geometry, read from the model's own world poses after a forward pass.

    Returns, per occluder, the world position MuJoCo computes for that geom's centre, its half-extents, and its geom
    type - enough for `PhaseCameraMatrixEvaluator._occluded` to decide whether the geom stands between the camera and
    the target. `joints_rad` optionally poses the arm first, so the occluders that are MOUNTED on the gripper are read
    where the arm actually is rather than where it rests.
    """

    import mujoco

    from so101_demo.act.task8_measurement_schema import EXPECTED_OCCLUDERS

    wanted = tuple(EXPECTED_OCCLUDERS if names is None else names)
    scene = Path(scene_path)
    if not scene.is_file():
        raise BottomIOError(f"BOTTOM_IO_SCENE_MISSING: {scene}")
    model = mujoco.MjModel.from_xml_path(str(scene))
    data = mujoco.MjData(model)
    if joints_rad is not None:
        values = [float(value) for value in joints_rad]
        if len(values) > model.nq:
            raise BottomIOError(f"BOTTOM_IO_JOINTS_TOO_MANY: {len(values)} > {model.nq}")
        data.qpos[:len(values)] = values
    mujoco.mj_forward(model, data)

    geometry = {}
    for name in wanted:
        geom_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_GEOM, name)
        if geom_id < 0:
            raise BottomIOError(f"BOTTOM_IO_OCCLUDER_GEOM_MISSING: {name}")
        size = [float(value) for value in model.geom_size[geom_id]]
        geometry[name] = {
            "position_m": [float(value) for value in data.geom_xpos[geom_id]],
            # the evaluator's own vocabulary: one radius. The geom's largest half-extent is the conservative reading -
            # a smaller radius would under-report an occluder, which is the direction that hides a real occlusion
            "radius_m": max(size) if size else 0.0,
            "size_m": size,
            "geom_type": int(model.geom_type[geom_id]),
        }
    return geometry


class ModelFrameSource:
    """The detector's frame source: the model's own camera, rendered headless.

    P1-1 (rereview 5): the seam's `frame_source(request)` returns `object()` and records the call, so the detector is
    handed something no model produced. The composition can do better - CP-1798 proved a headless EGL context renders
    `head_camera` at the admitted 640x480 into a real image here - so this renders the camera the request names and
    returns the frame.

    Two operational facts from that probe are built in rather than rediscovered:
      * the renderer is created ONCE and reused, because each `mujoco.Renderer` allocates a GL context;
      * `close()` is explicit, because **the EGL context's destructor raises on this host** - so a caller that owns one
        of these should close it (or use the context manager) rather than let it be collected during interpreter exit.
    """

    def __init__(self, scene_path, *, camera: str = "head_camera", width: int = 640, height: int = 480,
                 joints_rad=None) -> None:
        import mujoco

        scene = Path(scene_path)
        if not scene.is_file():
            raise BottomIOError(f"BOTTOM_IO_SCENE_MISSING: {scene}")
        self.model = mujoco.MjModel.from_xml_path(str(scene))
        if mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, camera) < 0:
            raise BottomIOError(f"BOTTOM_IO_FRAME_CAMERA_MISSING: {camera}")
        self.data = mujoco.MjData(self.model)
        self.camera = camera
        self.width = int(width)
        self.height = int(height)
        self.joints_rad = None if joints_rad is None else [float(value) for value in joints_rad]
        self._renderer = None

    def pose(self, joints_rad) -> None:
        """Where the arm is when the next frame is rendered - the frames follow the run, not a constant pose."""

        self.joints_rad = None if joints_rad is None else [float(value) for value in joints_rad]

    def __call__(self, request=None) -> "object":
        import mujoco

        camera = self.camera
        if isinstance(request, dict) and request.get("camera"):
            camera = str(request["camera"])
            if mujoco.mj_name2id(self.model, mujoco.mjtObj.mjOBJ_CAMERA, camera) < 0:
                raise BottomIOError(f"BOTTOM_IO_FRAME_CAMERA_MISSING: {camera}")
        if self._renderer is None:
            self._renderer = mujoco.Renderer(self.model, height=self.height, width=self.width)
        if self.joints_rad is not None:
            values = self.joints_rad
            if len(values) > self.model.nq:
                raise BottomIOError(f"BOTTOM_IO_JOINTS_TOO_MANY: {len(values)} > {self.model.nq}")
            self.data.qpos[:len(values)] = values
        mujoco.mj_forward(self.model, self.data)
        self._renderer.update_scene(self.data, camera=camera)
        return self._renderer.render()

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None

    def __enter__(self):
        return self

    def __exit__(self, *_exception):
        self.close()
        return False
