"""Prove a held cup from one lossless physics step and the same scene state."""

from __future__ import annotations

import math
from pathlib import Path

import mujoco
import numpy as np

from so101_demo.act.contracts import fields, finite, sha256, vector
from .physics import model_sha256
from .scene_state import SCENE_KEYS


def _body_transform(data: mujoco.MjData, body: int) -> np.ndarray:
    transform = np.eye(4)
    transform[:3, :3] = data.xmat[body].reshape((3, 3))
    transform[:3, 3] = data.xpos[body]
    return transform


def _side_force(contacts: object, *, prefix: tuple[str, ...]) -> float:
    if not isinstance(contacts, list) or not contacts:
        raise ValueError("HELD_CUP_BILATERAL_CONTACT_MISSING")
    force = 0.
    for item in contacts:
        if (not isinstance(item, dict)
                or item.get("object_body") != "plastic_cup"
                or not isinstance(item.get("robot_geom"), str)
                or not item["robot_geom"].startswith(prefix)):
            raise ValueError("HELD_CUP_CONTACT_INVALID")
        force += finite(item.get("normal_force_n"), nonnegative=True)
    return force


def _held_cup_attachment(
    model: mujoco.MjModel, scene: dict, physics_step: dict, *,
    model_digest: str,
    scene_received_monotonic_s: float, now_monotonic_s: float,
    max_age_s: float, minimum_bilateral_force_n: float,
    maximum_compression_distance_m: float,
) -> list[list[float]]:
    """Return the measured gripper-to-cup transform or refuse the held state."""
    if not isinstance(model, mujoco.MjModel) or not isinstance(physics_step, dict):
        raise ValueError("HELD_CUP_MODEL_OR_STEP_INVALID")
    fields(scene, SCENE_KEYS)
    now = finite(now_monotonic_s, nonnegative=True)
    maximum_age = finite(max_age_s)
    minimum_force = finite(minimum_bilateral_force_n)
    maximum_compression = finite(maximum_compression_distance_m)
    scene_received = finite(scene_received_monotonic_s, nonnegative=True)
    physics_received = finite(physics_step["received_monotonic_s"], nonnegative=True)
    if (not 0 < maximum_age <= .5 or minimum_force <= 0 or maximum_compression <= 0
            or not 0 <= now - scene_received <= maximum_age
            or not 0 <= now - physics_received <= maximum_age):
        raise ValueError("HELD_CUP_EVIDENCE_STALE")
    digest = sha256(model_digest)
    if (scene["model_sha256"] != digest
            or physics_step.get("model_sha256") != digest
            or scene["paused"] is not False
            or physics_step.get("released") is not False
            or type(scene["reset_epoch"]) is not int
            or scene["reset_epoch"] < 1
            or type(scene["simulation_step"]) is not int
            or scene["simulation_step"] < 1
            or scene["simulation_session_id"] != physics_step.get("simulation_session_id")
            or scene["reset_epoch"] != physics_step.get("reset_epoch")
            or scene["simulation_step"] != physics_step.get("physics_step")
            or not math.isclose(finite(scene["simulation_time_s"]),
                                finite(physics_step["simulation_time_s"]),
                                rel_tol=0., abs_tol=1e-9)):
        raise ValueError("HELD_CUP_STEP_SCOPE_INVALID")
    qpos = np.array(vector(scene["qpos"], model.nq))
    qvel = np.array(vector(scene["qvel"], model.nv))
    physics_qpos = np.array(vector(physics_step["model_qpos"], model.nq))
    physics_qvel = np.array(vector(physics_step["model_qvel"], model.nv))
    if (not np.allclose(qpos, physics_qpos, atol=1e-8, rtol=0.)
            or not np.allclose(qvel, physics_qvel, atol=1e-8, rtol=0.)):
        raise ValueError("HELD_CUP_QPOS_QVEL_MISMATCH")
    cup_joint = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    gripper_body = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_BODY, "gripper")
    if (cup_joint < 0 or gripper_body < 0
            or model.jnt_type[cup_joint] != mujoco.mjtJoint.mjJNT_FREE):
        raise ValueError("HELD_CUP_MODEL_INVALID")
    address = int(model.jnt_qposadr[cup_joint])
    cup_position = np.array(vector(physics_step["cup_position_m"], 3))
    quaternion = qpos[address + 3:address + 7]
    if (not np.allclose(qpos[address:address + 3], cup_position,
                        atol=1e-8, rtol=0.)
            or not math.isclose(float(quaternion @ quaternion), 1.,
                                rel_tol=0., abs_tol=1e-6)):
        raise ValueError("HELD_CUP_POSE_MISMATCH")
    left = _side_force(physics_step.get("left_contacts"),
                       prefix=("fixed_finger_", "fixed_fingertip_"))
    right = _side_force(physics_step.get("right_contacts"),
                        prefix=("moving_jaw_", "moving_fingertip_"))
    if min(left, right) < minimum_force:
        raise ValueError("HELD_CUP_BILATERAL_FORCE_LOW")
    if max((max(0., -finite(item["signed_distance_m"]))
            for side in ("left_contacts", "right_contacts")
            for item in physics_step[side]), default=0.) > maximum_compression:
        raise ValueError("HELD_CUP_COMPRESSION_EXCEEDED")
    data = mujoco.MjData(model)
    data.qpos[:] = qpos
    data.qvel[:] = qvel
    mujoco.mj_forward(model, data)
    cup_body = int(model.jnt_bodyid[cup_joint])
    relative = np.linalg.inv(_body_transform(data, gripper_body)) @ _body_transform(data, cup_body)
    if (not np.isfinite(relative).all()
            or not np.allclose(relative[3], (0., 0., 0., 1.), atol=1e-9, rtol=0.)
            or not np.allclose(relative[:3, :3].T @ relative[:3, :3], np.eye(3),
                               atol=1e-6, rtol=0.)
            or not math.isclose(float(np.linalg.det(relative[:3, :3])), 1.,
                                rel_tol=0., abs_tol=1e-6)):
        raise ValueError("HELD_CUP_ATTACHMENT_INVALID")
    return relative.tolist()


def held_cup_attachment(
    model: mujoco.MjModel, scene: dict, physics_step: dict, *,
    scene_received_monotonic_s: float, now_monotonic_s: float,
    max_age_s: float, minimum_bilateral_force_n: float,
    maximum_compression_distance_m: float,
) -> list[list[float]]:
    """Verify a supplied model's content before proving one held-cup step."""
    if not isinstance(model, mujoco.MjModel):
        raise ValueError("HELD_CUP_MODEL_OR_STEP_INVALID")
    return _held_cup_attachment(model, scene, physics_step,
        model_digest=model_sha256(model),
        scene_received_monotonic_s=scene_received_monotonic_s,
        now_monotonic_s=now_monotonic_s,max_age_s=max_age_s,
        minimum_bilateral_force_n=minimum_bilateral_force_n,
        maximum_compression_distance_m=maximum_compression_distance_m)


class HeldCupAttachmentModel:
    """Own a pristine scene model whose identity is checked once at startup."""

    def __init__(self, scene_path: str | Path, expected_model_sha256: str):
        expected=sha256(expected_model_sha256)
        model=mujoco.MjModel.from_xml_path(str(Path(scene_path).resolve()))
        digest=model_sha256(model)
        if digest!=expected:
            raise ValueError("HELD_CUP_MODEL_HASH_INVALID")
        self.model=model
        self.model_sha256=digest

    def prove(self, scene: dict, physics_step: dict, *,
              scene_received_monotonic_s: float, now_monotonic_s: float,
              max_age_s: float, minimum_bilateral_force_n: float,
              maximum_compression_distance_m: float) -> list[list[float]]:
        """Use the private, source-verified model for a fresh exact-step proof."""
        return _held_cup_attachment(self.model,scene,physics_step,
            model_digest=self.model_sha256,
            scene_received_monotonic_s=scene_received_monotonic_s,
            now_monotonic_s=now_monotonic_s,max_age_s=max_age_s,
            minimum_bilateral_force_n=minimum_bilateral_force_n,
            maximum_compression_distance_m=maximum_compression_distance_m)
