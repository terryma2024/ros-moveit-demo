"""The MuJoCo neck sweep that produces the timing samples."""

from __future__ import annotations

from collections.abc import Mapping
import math
from pathlib import Path
import time

from so101_demo.act.head_search_timing_measurement.contracts import (
    _PERIOD_TOLERANCE_S,
    _SHA256,
    CAL_TIMING_EVIDENCE_CONTRADICTORY,
    CAL_TIMING_EVIDENCE_MISSING,
    SIMULATION_TIME_BASE,
    WARMUP_POLICY,
    _digest,
    _mapping,
    _refuse,
)
from so101_demo.act.head_search_timing_measurement.control import (
    SettleTracker,
    controller_config,
    planned_stops,
)
from so101_demo.act.head_search_timing_measurement.documents import runtime_identity


class MujocoNeckSweepRunner:
    """Walk the controller's bounded stops in the sealed scene, timing every stop and every frame.

    This is the only place that imports MuJoCo, the detector or a GPU, and it does so inside the call. The
    sweep steps the sealed model at its own timestep, commands the scene's `neck_yaw_joint` position
    actuator at the sealed controller period, produces one frame per declared frame period of simulation
    time, and applies the declared settle rule to the joint's own velocity and position error. It commands
    the simulated neck only: no ROS node starts, no hardware is addressed.
    """

    def __call__(self, request: Mapping) -> dict:
        return self.run(request)

    def run(self, request: Mapping) -> dict:  # noqa: C901 - one linear measurement loop
        import mujoco
        import numpy as np

        started = time.monotonic()
        scene = Path(request["scene_path"])
        model = mujoco.MjModel.from_xml_path(str(scene))
        timestep = float(model.opt.timestep)
        if not math.isclose(
            timestep, float(request["simulation_timestep_s"]), rel_tol=0.0, abs_tol=_PERIOD_TOLERANCE_S
        ):
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene steps {timestep} s but its declaration was read as "
                f"{request['simulation_timestep_s']} s",
            )
        data = mujoco.MjData(model)
        neck = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "neck_yaw_joint")
        if neck < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no neck_yaw_joint, so no bounded stop can be walked",
            )
        qpos_address = int(model.jnt_qposadr[neck])
        dof_address = int(model.jnt_dofadr[neck])
        actuator = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_ACTUATOR, "neck_yaw_joint"
        )
        if actuator < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no neck_yaw_joint actuator, so no stop can be commanded",
            )
        camera = mujoco.mj_name2id(
            model, mujoco.mjtObj.mjOBJ_CAMERA, request["camera_name"]
        )
        if camera < 0:
            raise _refuse(
                CAL_TIMING_EVIDENCE_CONTRADICTORY,
                f"the sealed scene {scene} has no camera {request['camera_name']!r}",
            )
        mujoco.mj_forward(model, data)

        weights_path = request.get("weights_path")
        detector = None
        renderer = None
        warmup = {"performed": False, "wall_s": None, "detections": None, "declared_because": WARMUP_POLICY}
        if weights_path is not None:
            from ultralytics import YOLO

            detector = YOLO(str(weights_path))
            renderer = mujoco.Renderer(
                model, height=int(request["image_height"]), width=int(request["image_width"])
            )
            warmup_started = time.monotonic()
            renderer.update_scene(data, camera=camera)
            prediction = detector.predict(
                np.asarray(renderer.render()),
                conf=float(request["min_confidence"]),
                iou=float(request["tracking_iou"]),
                device=request.get("device"),
                verbose=False,
            )
            boxes = getattr(prediction[0], "boxes", None)
            warmup = {
                "performed": True,
                "wall_s": time.monotonic() - warmup_started,
                "detections": 0 if boxes is None else len(boxes.conf),
                "declared_because": WARMUP_POLICY,
            }

        period = float(request["control_period_s"])
        steps_per_control = int(round(period / timestep))
        frame_period = 1.0 / float(request["frame_rate_hz"])
        max_steps = int(math.ceil(float(request["max_settle_s"]) / timestep))
        stops: list[dict] = []
        frames: list[dict] = []
        next_frame_sim = frame_period

        try:
            for anchor in request["anchors"]:
                index = 0
                for kind, target in [
                    ("anchor", float(anchor["search_start_rad"])),
                    *[("plan", float(goal)) for goal in anchor["targets_rad"]],
                ]:
                    current = float(data.qpos[qpos_address])
                    if kind == "anchor" and abs(current - target) <= float(request["goal_tolerance_rad"]):
                        continue
                    data.ctrl[actuator] = target
                    tracker = SettleTracker(
                        settle_velocity_rad_s=float(request["settle_velocity_rad_s"]),
                        goal_tolerance_rad=float(request["goal_tolerance_rad"]),
                        consecutive_steps=int(request["settle_consecutive_steps"]),
                    )
                    start_sim = float(data.time)
                    start_rad = current
                    steps = 0
                    settled = False
                    reached = False
                    while steps < max_steps:
                        for _control in range(steps_per_control):
                            mujoco.mj_step(model, data)
                            steps += 1
                        error = target - float(data.qpos[qpos_address])
                        velocity = float(data.qvel[dof_address])
                        if abs(error) <= float(request["goal_tolerance_rad"]):
                            reached = True
                        if (
                            detector is not None
                            and float(data.time) >= next_frame_sim - _PERIOD_TOLERANCE_S
                        ):
                            next_frame_sim += frame_period
                            frames.append(
                                self._frame(
                                    data,
                                    renderer,
                                    detector,
                                    camera,
                                    request,
                                    np,
                                    index=len(frames),
                                    anchor=anchor["anchor"],
                                    stop_index=index if kind == "plan" else None,
                                )
                            )
                        if tracker.observe(velocity, error):
                            settled = True
                            break
                    stops.append(
                        {
                            "anchor": anchor["anchor"],
                            "index": index if kind == "plan" else None,
                            "kind": kind,
                            "target_rad": target,
                            "start_rad": start_rad,
                            "sim_start_s": start_sim,
                            "sim_end_s": float(data.time),
                            "steps": steps,
                            "settle_s": float(data.time) - start_sim,
                            "settled": settled,
                            "reached": reached,
                            "final_velocity_rad_s": float(data.qvel[dof_address]),
                            "final_position_error_rad": target - float(data.qpos[qpos_address]),
                            "quiet_steps": tracker.quiet_steps,
                            "time_base": SIMULATION_TIME_BASE,
                        }
                    )
                    if kind == "plan":
                        index += 1
        finally:
            if renderer is not None:
                renderer.close()
        return {
            "time_base": SIMULATION_TIME_BASE,
            "simulation_timestep_s": timestep,
            "control_period_s": period,
            "stops": stops,
            "frames": frames,
            "sim_time_s": float(data.time),
            "wall_time_s": time.monotonic() - started,
            "detector": {
                "loaded": detector is not None,
                "device": request.get("device") if detector is not None else None,
                "weights_path": None if weights_path is None else str(weights_path),
                "weights_sha256": request.get("weights_sha256"),
            },
            "warmup": warmup,
            "runtime_identity": runtime_identity(
                device=request.get("device"), detector_loaded=detector is not None,
                weights_sha256=request.get("weights_sha256"),
            ),
        }

    @staticmethod
    def _frame(data, renderer, detector, camera, request, np, *, index, anchor, stop_index) -> dict:
        """One frame: capture it, decide on it, and stamp both ends in both time bases."""

        frame_sim = float(data.time)
        frame_wall = time.monotonic()
        renderer.update_scene(data, camera=camera)
        image = np.asarray(renderer.render())
        received_wall = time.monotonic()
        prediction = detector.predict(
            image,
            conf=float(request["min_confidence"]),
            iou=float(request["tracking_iou"]),
            device=request["device"],
            verbose=False,
        )
        decision_wall = time.monotonic()
        boxes = getattr(prediction[0], "boxes", None)
        confidences = [] if boxes is None else [float(value) for value in boxes.conf]
        return {
            "frame_index": index,
            "anchor": anchor,
            "stop_index": stop_index,
            "frame_sim_s": frame_sim,
            "received_sim_s": frame_sim,
            "decision_sim_s": frame_sim,
            "frame_monotonic_s": frame_wall,
            "received_monotonic_s": received_wall,
            "decision_monotonic_s": decision_wall,
            "render_s": received_wall - frame_wall,
            "inference_s": decision_wall - received_wall,
            "detection_count": len(confidences),
            "max_confidence": max(confidences) if confidences else None,
        }


def _declared_weights(production: Mapping, request) -> str | None:
    """The detector weights the production configuration declares, checked against the file it names."""

    path = request.get("weights_path")
    if path is None:
        return None
    weights = Path(path)
    if not weights.is_file():
        raise FileNotFoundError(f"the timing measurement needs {weights}")
    declared = production.get("weight_sha256")
    measured = _digest(weights)
    if type(declared) is not str or _SHA256.fullmatch(declared) is None:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the production search configuration declares no weight_sha256, so the detector this "
            "measurement would time frames with is not the sealed model",
        )
    if declared != measured:
        raise _refuse(
            CAL_TIMING_EVIDENCE_CONTRADICTORY,
            f"the declared detector {weights} digests to {measured}, but the production search "
            f"configuration seals {declared}: the frame times would belong to a model the calibration did "
            f"not select",
        )
    return measured


def _anchor_requests(*, seal, production, anchors, attempt_id, session_id) -> list[dict]:
    """One request per sealed anchor, with the bounded stops the controller plans for it."""

    declared = _mapping("sealed geometry", seal).get("in_frame_matrix")
    if not isinstance(declared, Mapping) or not declared:
        raise _refuse(
            CAL_TIMING_EVIDENCE_MISSING,
            "the sealed geometry declares no in_frame_matrix anchors, so the sweep has no search start",
        )
    names = list(declared) if anchors is None else list(anchors)
    if not names:
        raise _refuse(CAL_TIMING_EVIDENCE_MISSING, "no anchor was declared for the sweep")
    requests = []
    for name in names:
        if type(name) is not str or name not in declared:
            raise _refuse(
                CAL_TIMING_EVIDENCE_MISSING,
                f"the sealed geometry declares no anchor {name!r}",
            )
        config = controller_config(
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
                "targets_rad": list(planned_stops(config)),
                "controller_config": config,
            }
        )
    return requests
