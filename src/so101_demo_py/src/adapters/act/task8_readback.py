"""Read-only, same-step Task 8 physics and controller evidence join.

This boundary does not infer a phase result or create a motion permit. Callers
must supply joint addresses from the compiled, content-bound MuJoCo model.
"""

from __future__ import annotations

import math
import time

from so101_demo.act.contracts import finite, identifier, sha256


class Task8ReadbackError(RuntimeError):
    """A required physical source is missing or disagrees with another."""


def compiled_qpos_mapping(model, *, expected_model_sha256: str,
                          expected_mujoco_version: str) -> tuple[tuple[int, ...], tuple[int, ...]]:
    """Resolve ACT joints from a verified compiled model, never numeric config."""
    import mujoco
    from so101_demo.act.joints import ACT_JOINTS
    from .physics import model_sha256

    sha256(expected_model_sha256)
    if (not isinstance(model, mujoco.MjModel)
            or not isinstance(expected_mujoco_version, str)
            or mujoco.mj_versionString() != expected_mujoco_version):
        raise ValueError("TASK8_MUJOCO_VERSION_MISMATCH")
    if model_sha256(model) != expected_model_sha256:
        raise ValueError("TASK8_MODEL_HASH_MISMATCH")
    joints = []
    for name in ACT_JOINTS:
        joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        if joint_id < 0 or model.jnt_type[joint_id] != mujoco.mjtJoint.mjJNT_HINGE:
            raise ValueError("TASK8_MODEL_JOINT_INVALID")
        joints.append(int(model.jnt_qposadr[joint_id]))
    cup_joint_id = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, "cup_free_joint")
    if cup_joint_id < 0 or model.jnt_type[cup_joint_id] != mujoco.mjtJoint.mjJNT_FREE:
        raise ValueError("TASK8_MODEL_CUP_INVALID")
    cup_start = int(model.jnt_qposadr[cup_joint_id])
    cup = tuple(range(cup_start, cup_start + 7))
    if (len(set(joints)) != 7 or min(joints) < 0 or max(joints) >= model.nq
            or cup_start < 0 or cup[-1] >= model.nq or set(joints) & set(cup)):
        raise ValueError("TASK8_MODEL_QPOS_INVALID")
    return tuple(joints), cup


class Task8PhysicalReadback:
    def __init__(
        self, world, scene, contacts, rgb, broker, *, model,
        expected_model_sha256, expected_mujoco_version,
        max_source_skew_s, max_wall_age_s,
        joint_tolerance_rad, cup_pose_tolerance_m, cup_orientation_tolerance,
        monotonic=time.monotonic,
    ) -> None:
        self.world, self.scene, self.contacts = world, scene, contacts
        self.rgb, self.broker, self.monotonic = rgb, broker, monotonic
        self.joints, self.cup = compiled_qpos_mapping(
            model, expected_model_sha256=expected_model_sha256,
            expected_mujoco_version=expected_mujoco_version,
        )
        self.max_skew = finite(max_source_skew_s)
        self.max_wall_age = finite(max_wall_age_s)
        self.joint_tolerance = finite(joint_tolerance_rad)
        self.cup_position_tolerance = finite(cup_pose_tolerance_m)
        self.cup_orientation_tolerance = finite(cup_orientation_tolerance)
        if min(self.max_skew, self.max_wall_age, self.joint_tolerance,
               self.cup_position_tolerance, self.cup_orientation_tolerance) <= 0:
            raise ValueError("TASK8_READBACK_CONFIG_INVALID")

    def capture(self, session_id: str, attempt_id: str, reset_epoch: int) -> dict:
        identifier(session_id)
        identifier(attempt_id)
        if type(reset_epoch) is not int or reset_epoch < 1:
            raise Task8ReadbackError("SOURCE_SCOPE_MISMATCH")
        try:
            received = self.world.recent_with_receipts()
            now = finite(self.monotonic(), nonnegative=True)
            fresh = tuple(item for item in received
                          if 0 <= now - item.received_monotonic_s <= self.max_wall_age
                          and not item.evidence.truncated)
            if not fresh:
                raise ValueError("world stale or truncated")
            worlds = {item.evidence.simulation_step: item.evidence for item in fresh
                      if (item.evidence.simulation_session_id, item.evidence.reset_epoch)
                      == (session_id, reset_epoch)}
        except (AttributeError, TypeError, ValueError, RuntimeError) as error:
            raise Task8ReadbackError("WORLD_READBACK_UNAVAILABLE") from error
        try:
            scene_frames = self.scene.recent_frames()
        except (AttributeError, TypeError, ValueError, RuntimeError) as error:
            raise Task8ReadbackError("SCENE_READBACK_UNAVAILABLE") from error
        try:
            contact_frames = self.contacts.recent_frames()
        except (AttributeError, TypeError, ValueError, RuntimeError) as error:
            raise Task8ReadbackError("CONTACT_READBACK_UNAVAILABLE") from error
        scenes = {frame["simulation_step"]: frame for frame in scene_frames
                  if (frame["simulation_session_id"], frame["reset_epoch"])
                  == (session_id, reset_epoch)}
        contacts = {frame["physics_step"]: frame for frame in contact_frames
                    if (frame["simulation_session_id"], frame["reset_epoch"])
                    == (session_id, reset_epoch)}
        if not worlds or not scenes or not contacts:
            raise Task8ReadbackError("SOURCE_SCOPE_MISMATCH")
        common = worlds.keys() & scenes.keys() & contacts.keys()
        if not common:
            raise Task8ReadbackError("SOURCE_STEP_MISMATCH")
        step = max(common)
        world, scene, contact = worlds[step], scenes[step], contacts[step]
        if world.paused != scene["paused"]:
            raise Task8ReadbackError("SOURCE_STEP_MISMATCH")
        at_s = world.simulation_time_s
        if any(abs(stamp - at_s) > self.max_skew for stamp in (
            scene["simulation_time_s"], contact["simulation_time_s"],
        )):
            raise Task8ReadbackError("SOURCE_TIME_SKEW")
        qpos = scene["qpos"]
        if max((*self.joints, *self.cup)) >= len(qpos):
            raise Task8ReadbackError("QPOS_MAPPING_INVALID")
        cup_position = tuple(qpos[index] for index in self.cup[:3])
        actual_position = world.object_state.position_world
        if math.dist(cup_position, actual_position) > self.cup_position_tolerance:
            raise Task8ReadbackError("CUP_QPOS_DIVERGED")
        cup_quaternion = tuple(qpos[index] for index in self.cup[3:])
        x, y, z, w = world.object_state.orientation_xyzw
        expected_quaternion = (w, x, y, z)
        if min(
            math.dist(cup_quaternion, expected_quaternion),
            math.dist(cup_quaternion, tuple(-value for value in expected_quaternion)),
        ) > self.cup_orientation_tolerance:
            raise Task8ReadbackError("CUP_QPOS_DIVERGED")
        try:
            reference = self.broker.reference_state(at_s)
            if (not isinstance(reference, dict)
                    or set(reference) != {"positions", "velocities", "accelerations", "requested_sim_time_s"}
                    or reference["requested_sim_time_s"] != at_s
                    or any(len(reference[key]) != 6 or any(not math.isfinite(value) for value in reference[key])
                           for key in ("positions", "velocities", "accelerations"))):
                raise ValueError("reference invalid")
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
            raise Task8ReadbackError("REFERENCE_READBACK_UNAVAILABLE") from error
        try:
            observation = self.rgb.sample(session_id, attempt_id, at_s)
            audit = self.rgb.last_audit
            if any(abs(stamp - at_s) > self.max_skew for stamp in audit["source_stamps"].values()):
                raise ValueError("RGB_SOURCE_TIME_SKEW")
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
            raise Task8ReadbackError("RGB_READBACK_UNAVAILABLE") from error
        measured = (*observation["state"][:6], audit["neck_yaw_rad"])
        if any(abs(measured[index] - qpos[address]) > self.joint_tolerance
               for index, address in enumerate(self.joints)):
            raise Task8ReadbackError("JOINT_QPOS_DIVERGED")
        return {"world": world, "scene": scene, "contact": contact,
                "observation": observation, "reference": reference,
                "source_stamps_s": dict(audit["source_stamps"])}
