"""Deterministic offline MuJoCo contact scenarios for ACT calibration.

This collector uses only the frozen motion policy and independent diagnostic
limits. It neither reads a proposed contact policy nor commands ROS.
"""

from __future__ import annotations

import hashlib
import math
import random
import time
from collections import deque
from pathlib import Path

import mujoco
import numpy as np
import yaml

from so101_demo.act.contact_calibration import _canonical
from so101_demo.adapters.act.physics import model_sha256

_MUJOCO_VERSION = "3.12.0"
_SCENE_SHA256 = "4db48e35df9e91fc6868d303725badd0237fb10754d1e298637f5b0e1e55ed4f"
_MODEL_SHA256 = "3c876e7bbf879dbf614abfe8ecf48ca0eb43dc179a4124467f88b7ca755fdd78"
_MOTION_SHA256 = "aa83a43c25e2fa4bf70cbaaf6bcb76742e44d7f67a83625ab428f78dc5848356"
_MAX_FORCE_N = 11.6
_MAX_DISPLACEMENT_M = .03

_SCENARIOS = {
    "no_contact": ("settle", 6),
    "table_only": ("settle", 6),
    "left_only": ("settle", 2),
    "right_only": ("close", 4),
    "bilateral_touch": ("lift", 2),
    "over_compression": ("hold", 6),
    "micro_lift_slip": ("lift", 6),
    "stable_hold": ("hold", 11),
    "post_release": ("settle_after_release", 6),
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contact_frame(model, data, *, step: int, released: bool, cup_address: int, cup_velocity_address: int):
    cup_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "plastic_cup")
    if cup_body < 0:
        raise ValueError("ACT cup body is missing")
    contacts = {"left_contacts": [], "right_contacts": [], "other_contacts": []}
    total_force = 0.0
    for index, contact in enumerate(data.contact):
        first_id, second_id = (int(value) for value in contact.geom)
        first_is_cup = model.geom_bodyid[first_id] == cup_body
        second_is_cup = model.geom_bodyid[second_id] == cup_body
        if not first_is_cup and not second_is_cup:
            continue
        if first_is_cup == second_is_cup:
            raise ValueError("cup self-contact cannot calibrate a policy")
        other_id = second_id if first_is_cup else first_id
        other = mujoco.mj_id2name(model, mujoco.mjtObj.mjOBJ_GEOM, other_id)
        if not other:
            raise ValueError("contact geometry is unnamed")
        vector = np.zeros(6)
        mujoco.mj_contactForce(model, data, index, vector)
        force = max(0.0, float(vector[0]))
        total_force += force
        item = {"robot_geom": other, "object_body": "plastic_cup",
                "normal_force_n": force, "signed_distance_m": float(contact.dist)}
        if other.startswith("fixed_fingertip_pad_collision"):
            contacts["left_contacts"].append(item)
        elif other.startswith("moving_fingertip_pad_collision"):
            contacts["right_contacts"].append(item)
        else:
            contacts["other_contacts"].append(item)
    frame = {
        "physics_step": step, "simulation_time_s": float(data.time),
        "ros_time_s": float(data.time),
        "received_monotonic_s": time.monotonic(),
        **contacts,
        "cup_position_m": data.qpos[cup_address:cup_address + 3].tolist(),
        "cup_velocity_m_s": data.qvel[cup_velocity_address:cup_velocity_address + 3].tolist(),
        "model_qpos": data.qpos.tolist(), "model_qvel": data.qvel.tolist(),
        "table_supported": any(
            item["robot_geom"] == "table_collision" for item in contacts["other_contacts"]
        ),
        "released": released,
    }
    return frame, total_force


def _qualifies(regime: str, phase: str, step: int, frame: dict, force: float) -> bool:
    if phase != _SCENARIOS[regime][0]:
        return False
    left = bool(frame["left_contacts"])
    right = bool(frame["right_contacts"])
    table = frame["table_supported"]
    speed = math.sqrt(sum(value * value for value in frame["cup_velocity_m_s"]))
    if regime in {"no_contact", "table_only"}:
        return step >= 200 and table and not left and not right
    if regime == "left_only":
        return left and not right
    if regime == "right_only":
        return step >= 1200 and right and not left and table
    if regime == "bilateral_touch":
        return left and right and table
    if regime == "over_compression":
        return step >= 2350 and left and right and not table and 2.0 <= force < _MAX_FORCE_N
    if regime == "micro_lift_slip":
        return step >= 1300 and left and right and not table and speed >= .005
    if regime == "stable_hold":
        return step >= 2350 and left and right and not table and speed < .0001
    return step >= 3550 and frame["released"] and table and not left and not right


def collect_offline_sample(
    scene_path: Path, motion_policy_path: Path, *, regime: str, seed: int,
    sample_id: str, config_sha256: str,
) -> dict:
    """Run a fresh deterministic physical session and return its lossless window."""

    if regime not in _SCENARIOS or type(seed) is not int or seed < 0 or not sample_id:
        raise ValueError("offline scenario identity is invalid")
    scene_path, motion_policy_path = Path(scene_path), Path(motion_policy_path)
    if mujoco.mj_versionString() != _MUJOCO_VERSION:
        raise ValueError("MuJoCo runtime version mismatch")
    if _sha(scene_path) != _SCENE_SHA256 or _sha(motion_policy_path) != _MOTION_SHA256:
        raise ValueError("ACT scene or motion policy hash mismatch")
    model = mujoco.MjModel.from_xml_path(str(scene_path.resolve()))
    if model_sha256(model) != _MODEL_SHA256 or model.opt.timestep != .002:
        raise ValueError("ACT compiled model or timestep mismatch")
    policy = yaml.safe_load(motion_policy_path.read_bytes())
    preopen = policy["gripper_actions"]["preopen_q6"]
    close = -.049 if regime == "over_compression" else policy["gripper_actions"]["grasp_close_q6"]
    start = np.array(policy["states"]["DESCEND"]["waypoints"][-1] + [preopen])
    closed = start.copy(); closed[5] = close
    lift = np.array(policy["states"]["LIFT"]["waypoints"][0] + [close])
    opened = lift.copy(); opened[5] = preopen
    arm_addresses = [
        int(model.jnt_qposadr[mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, str(index))])
        for index in range(1, 7)
    ]
    cup_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    if cup_joint < 0:
        raise ValueError("ACT cup free joint is missing")
    cup_address = int(model.jnt_qposadr[cup_joint])
    cup_velocity_address = int(model.jnt_dofadr[cup_joint])
    jitter = 0.0 if regime == "left_only" else round(
        random.Random(seed).uniform(-.000008, .000008), 12
    )
    cup_start = [.02 + jitter, -.28 + (.001 if regime == "left_only" else 0.), .165]
    data = mujoco.MjData(model)
    mujoco.mj_resetDataKeyframe(model, data, 0)
    data.qpos[arm_addresses] = start
    data.qpos[cup_address:cup_address + 3] = cup_start
    data.qpos[cup_address + 3:cup_address + 7] = [1., 0., 0., 0.]
    data.ctrl[:6] = start
    mujoco.mj_forward(model, data)
    schedule = [("settle", .5, start, start), ("close", 2., start, closed),
                ("lift", 2., closed, lift), ("hold", .5, lift, lift),
                ("release", 2., lift, opened),
                ("settle_after_release", .5, opened, opened)]
    chosen_phase, length = _SCENARIOS[regime]
    window = deque(maxlen=length)
    step = 0
    peak_route_force = 0.0
    peak_route_displacement = 0.0
    if regime == "left_only":
        reset_frame, reset_force = _contact_frame(
            model, data, step=0, released=False,
            cup_address=cup_address, cup_velocity_address=cup_velocity_address,
        )
        if reset_force > _MAX_FORCE_N or not _qualifies(regime, "settle", 0, reset_frame, reset_force):
            raise ValueError("left-only reset diagnostic is invalid")
        window.append(reset_frame)
        peak_route_force = reset_force
    for phase, duration, first, last in schedule:
        number = round(duration / model.opt.timestep)
        for index in range(number):
            data.ctrl[:6] = first + (last - first) * (index + 1) / number
            mujoco.mj_step(model, data)
            step += 1
            if not np.isfinite(data.qpos).all() or not np.isfinite(data.qvel).all():
                raise ValueError("nonfinite ACT physics")
            frame, force = _contact_frame(
                model, data, step=step, released=phase == "settle_after_release",
                cup_address=cup_address, cup_velocity_address=cup_velocity_address,
            )
            displacement = math.dist(frame["cup_position_m"], cup_start)
            peak_route_force = max(peak_route_force, force)
            peak_route_displacement = max(peak_route_displacement, displacement)
            if force > _MAX_FORCE_N or displacement > _MAX_DISPLACEMENT_M:
                raise ValueError("independent diagnostic hard stop")
            if _qualifies(regime, phase, step, frame, force):
                window.append(frame)
                if len(window) == length and all(
                    b["physics_step"] == a["physics_step"] + 1
                    for a, b in zip(window, list(window)[1:])
                ):
                    frames = list(window)
                    scenario = {
                        "regime": regime, "seed": seed, "cup_start_m": cup_start,
                        "gripper_close_q6": float(close),
                        "window_first_step": frames[0]["physics_step"],
                        "window_last_step": frames[-1]["physics_step"],
                    }
                    peak_window_force = max(
                        sum(item["normal_force_n"] for key in
                            ("left_contacts", "right_contacts", "other_contacts")
                            for item in row[key]) for row in frames
                    )
                    peak_window_displacement = max(
                        math.dist(row["cup_position_m"], frames[0]["cup_position_m"])
                        for row in frames
                    )
                    return {
                        "sample_id": sample_id, "source": "offline", "regime": regime,
                        "simulation_session_id": f"offline-{sample_id}", "reset_epoch": 1,
                        "scenario": scenario,
                        "scenario_sha256": hashlib.sha256(_canonical(scenario)).hexdigest(),
                        "model_sha256": _MODEL_SHA256,
                        "scene_sha256": _SCENE_SHA256,
                        "motion_policy_sha256": _MOTION_SHA256,
                        "collector_sha256": _sha(Path(__file__)),
                        "config_sha256": config_sha256,
                        "clock_origin": "mujoco_simulated_ros",
                        "frames": frames,
                        "collected_monotonic_s": time.monotonic(),
                        "diagnostic_result": {
                            "status": "PASS", "peak_force_n": peak_window_force,
                            "peak_displacement_m": peak_window_displacement,
                        },
                    }
            else:
                window.clear()
        if phase == chosen_phase:
            break
    raise ValueError(f"physical regime {regime} was not reached")
