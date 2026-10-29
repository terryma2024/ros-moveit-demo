"""The MuJoCo closed-loop plant and the production head detector."""

from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path

from so101_demo.act.head_search.deadband_measurement.contracts import DETECTOR_MODEL_ID, _refuse
from so101_demo.act.head_search.deadband_measurement.lock_trial import (
    _re_raised,
    anchor_cup_start_m,
)
from so101_demo.act.head_search.timing_measurement.contracts import (
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    FRAME_PERIOD_S,
    _digest,
)
from so101_demo.act.head_search.timing_measurement.control import (
    SettleTracker,
    controller_config,
)


class MujocoClosedLoopPlant:
    """The sealed scene's neck, commanded and settled, and its head camera, rendered.

    This is the only place in this module that imports MuJoCo, and it does so inside the call. The plant
    places the anchor's cup where the seal says it starts, commands the scene's own ``neck_yaw_joint``
    position actuator at the sealed controller period, applies the timing module's declared settle rule,
    and holds the neck at each frame boundary for one declared frame period of simulation time. It
    commands the simulated neck only: no ROS node starts and no hardware is addressed.
    """

    def __init__(self, request: Mapping) -> None:
        import mujoco
        import numpy as np

        self._mujoco = mujoco
        self.max_settle_s = float(request["max_settle_s"])
        self.frame_period_s = float(request["frame_period_s"])
        self.control_period_s = float(request["control_period_s"])
        self._flip = np.diag([1.0, -1.0, -1.0])
        scene = Path(request["scene_path"])
        self._model = mujoco.MjModel.from_xml_path(str(scene))
        self.simulation_timestep_s = float(self._model.opt.timestep)
        self._joint_name = str(request.get("neck_joint", "neck_yaw_joint"))
        camera_name = request["camera_name"]
        self._camera = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_CAMERA, camera_name)
        if self._camera < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no camera {camera_name!r}",
            )
        if not math.isclose(
            math.radians(float(self._model.cam_fovy[self._camera])),
            float(request["fovy_rad"]),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene's {camera_name} camera has a different field of view than the sealed "
                f"geometry declares, so these frames would be measured against another camera",
            )
        self._data = mujoco.MjData(self._model)
        self._neck = mujoco.mj_name2id(self._model, mujoco.mjtObj.mjOBJ_JOINT, self._joint_name)
        if self._neck < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY, f"the sealed scene {scene} has no {self._joint_name}"
            )
        self._qpos_address = int(self._model.jnt_qposadr[self._neck])
        self._dof_address = int(self._model.jnt_dofadr[self._neck])
        self._actuator = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_ACTUATOR, self._joint_name
        )
        if self._actuator < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no {self._joint_name} actuator, so no target can be "
                f"commanded",
            )
        self._cup_body = mujoco.mj_name2id(
            self._model, mujoco.mjtObj.mjOBJ_BODY, request.get("cup_body", "plastic_cup")
        )
        if self._cup_body < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no {request.get('cup_body', 'plastic_cup')} body, so where "
                f"the anchor's cup sits cannot be read back",
            )
        self._place_cup(request["cup_joint"], request["cup_start_m"])
        self._data.qpos[self._qpos_address] = float(request["start_rad"])
        mujoco.mj_forward(self._model, self._data)
        self._renderer = None
        self._steps_per_control = max(1, int(round(self.control_period_s / self.simulation_timestep_s)))
        self._max_steps = int(math.ceil(self.max_settle_s / self.simulation_timestep_s))
        self._next_frame_s = float(self._data.time)
        self._settle_velocity_rad_s = float(request["settle_velocity_rad_s"])
        self._goal_tolerance_rad = float(request["goal_tolerance_rad"])
        self._settle_consecutive_steps = int(request["settle_consecutive_steps"])
        self._image_width = int(request["image_width"])
        self._image_height = int(request["image_height"])
        self._focal_px = (self._image_height / 2.0) / math.tan(
            math.radians(float(self._model.cam_fovy[self._camera])) / 2.0
        )

    def _place_cup(self, joint_name: str, position) -> None:
        joint = self._mujoco.mj_name2id(self._model, self._mujoco.mjtObj.mjOBJ_JOINT, joint_name)
        if joint < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene has no {joint_name} joint, so the anchor's cup is not in the scene",
            )
        address = int(self._model.jnt_qposadr[joint])
        self._data.qpos[address : address + 3] = [float(value) for value in position]
        self._data.qpos[address + 3 : address + 7] = (1.0, 0.0, 0.0, 0.0)

    @property
    def time_s(self) -> float:
        return float(self._data.time)

    @property
    def yaw_rad(self) -> float:
        return float(self._data.qpos[self._qpos_address])

    @property
    def velocity_rad_s(self) -> float:
        return float(self._data.qvel[self._dof_address])

    @property
    def frame_stamp_ns(self) -> int:
        """The frame's source stamp: this frame boundary in simulation nanoseconds, never a wall clock."""

        return int(round(self._data.time * 1e9))

    def settle_to(self, target_rad: float) -> dict:
        """Command the neck, step until the declared settle rule holds, then hold to the frame boundary."""

        target = float(target_rad)
        self._data.ctrl[self._actuator] = target
        start_sim, start_rad = float(self._data.time), self.yaw_rad
        tracker = SettleTracker(
            settle_velocity_rad_s=self._settle_velocity_rad_s,
            goal_tolerance_rad=self._goal_tolerance_rad,
            consecutive_steps=self._settle_consecutive_steps,
        )
        steps = 0
        settled = reached = False
        settle_instant_s = None
        while steps < self._max_steps:
            for _ in range(self._steps_per_control):
                self._mujoco.mj_step(self._model, self._data)
                steps += 1
            error = target - self.yaw_rad
            if abs(error) <= self._goal_tolerance_rad:
                reached = True
            if tracker.observe(self.velocity_rad_s, error):
                settled = True
                settle_instant_s = self.time_s - start_sim
                break
        self._next_frame_s = max(
            self._next_frame_s + self.frame_period_s, start_sim + self.frame_period_s
        )
        while self._data.time < self._next_frame_s - 1e-12 and steps < 4 * self._max_steps:
            for _ in range(self._steps_per_control):
                self._mujoco.mj_step(self._model, self._data)
                steps += 1
        return {
            "target_rad": target,
            "start_rad": start_rad,
            "sim_start_s": start_sim,
            "sim_end_s": float(self._data.time),
            "steps": steps,
            "settle_s": float(self._data.time) - start_sim,
            "settle_instant_s": settle_instant_s,
            "settled": settled,
            "reached": reached,
            "final_velocity_rad_s": self.velocity_rad_s,
            "final_position_error_rad": target - self.yaw_rad,
            "quiet_steps": tracker.quiet_steps,
        }

    def render_frame(self):
        """One frame of the head camera, opening the GL context on the first frame that needs one."""

        if self._renderer is None:
            self._renderer = self._mujoco.Renderer(
                self._model, height=self._image_height, width=self._image_width
            )
        self._renderer.update_scene(self._data, camera=self._camera)
        return self._renderer.render()

    def optical_geometry(self) -> dict:
        """The head camera's intrinsics and its optical frame in the base frame, from the live model."""

        rotation = self._data.cam_xmat[self._camera].reshape(3, 3) @ self._flip
        return {
            "k": (
                self._focal_px,
                0.0,
                self._image_width / 2.0,
                0.0,
                self._focal_px,
                self._image_height / 2.0,
                0.0,
                0.0,
                1.0,
            ),
            "distortion": (0.0, 0.0, 0.0, 0.0, 0.0),
            "rotation_optical_to_base": tuple(
                tuple(float(value) for value in row) for row in rotation
            ),
        }

    @property
    def cup_position_m(self) -> list[float]:
        """Where the anchor's cup really is, read back out of the stepped model rather than assumed."""

        return [float(value) for value in self._data.xpos[self._cup_body]]

    def close(self) -> None:
        if self._renderer is not None:
            self._renderer.close()
            self._renderer = None


class ProductionHeadDetector:
    """The production head detector as one callable frame source, with its own track association."""

    def __init__(self, detector, *, session_id: str, attempt_id: str, frame_id: str) -> None:
        self.detector = detector
        self.session_id = session_id
        self.attempt_id = attempt_id
        self.frame_id = frame_id

    def reset(self) -> None:
        self.detector.reset()

    def __call__(self, image, stamp_ns: int):
        """One frame's detections: the production detector takes the image and its identity, not a frame."""

        return self.detector.detect(
            image,
            session_id=self.session_id,
            attempt_id=self.attempt_id,
            source_stamp_ns=int(stamp_ns),
            source_frame_id=self.frame_id,
        )


def build_production_head_detector(
    *, weights_path, operating_point, production, frame_id, device, attempt_id, session_id
):
    """The production head detector over the selected model, at its declared head operating point.

    This is the same adapter the running search uses - ``HeadRgbDetector`` over ``YoloSegDetector`` - so
    the class filter, the aspect gate, the spatial track association and the never-CPU-fallback device
    policy are the production ones rather than a harness copy.
    """

    from so101_demo.adapters.act.detector import HeadRgbDetector
    from so101_demo.adapters.perception.yolo_seg import YoloSegDetector

    values = production.get("values") if isinstance(production.get("values"), Mapping) else {}
    model_id = str(production.get("runtime_id") or DETECTOR_MODEL_ID)
    digest = _digest(weights_path)
    detector = YoloSegDetector(
        weights_path=Path(weights_path),
        expected_sha256=digest,
        requested_device=device,
        allow_cpu_fallback=False,
        model_id=model_id,
        imgsz=640,
    )
    head = HeadRgbDetector(
        detector,
        model_id=model_id,
        weights_sha256=digest,
        tracking_iou=float(operating_point["iou"]),
        min_bbox_aspect=float(values["min_bbox_aspect"]),
    )
    return ProductionHeadDetector(
        head, session_id=session_id, attempt_id=attempt_id, frame_id=frame_id
    )


def _anchor_requests(*, seal, production, anchors, attempt_id, session_id) -> list[dict]:
    declared = seal.get("in_frame_matrix")
    if not isinstance(declared, Mapping) or not declared:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the sealed geometry declares no in_frame_matrix anchors, so no lock trial has a search start",
        )
    names = list(declared) if anchors is None else list(anchors)
    if not names:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, "no anchor was declared for the lock trials")
    requests = []
    for name in names:
        if type(name) is not str or name not in declared:
            raise _refuse(CAL_TIMING_EVIDENCE_MISSING, f"the sealed geometry declares no anchor {name!r}")
        config = _re_raised(
            controller_config,
            production_search_config=production,
            geometry_seal=seal,
            anchor=name,
            attempt_id=attempt_id,
            session_id=session_id,
        )
        requests.append(
            {
                "anchor": name,
                "search_start_rad": config["search_start_rad"],
                "cup_start_m": anchor_cup_start_m(geometry_seal=seal, anchor=name),
                "controller_config": config,
            }
        )
    return requests


def _plant_request(*, request, scene, seal, camera, control_period_s, max_settle_s,
                   settle_consecutive_steps) -> dict:
    config = request["controller_config"]
    return {
        "scene_path": str(scene),
        "camera_name": seal.get("camera_name"),
        "image_width": seal.get("image_width"),
        "image_height": seal.get("image_height"),
        "fovy_rad": (camera or {}).get("fovy_rad"),
        "control_period_s": control_period_s,
        "frame_period_s": FRAME_PERIOD_S,
        "max_settle_s": max_settle_s,
        "settle_consecutive_steps": settle_consecutive_steps,
        "settle_velocity_rad_s": config["settle_velocity_rad_s"],
        "goal_tolerance_rad": config["goal_tolerance_rad"],
        "start_rad": config["search_start_rad"],
        "cup_start_m": request["cup_start_m"],
        "cup_joint": "cup_free_joint",
        "cup_body": "plastic_cup",
    }


def _cuda_available() -> bool:
    """Whether the declared CUDA device is really there; the measurement never falls back to the CPU."""

    import torch

    return bool(torch.cuda.is_available())
