"""Read-only, same-step Task 8 physics and controller evidence join.

This boundary does not infer a phase result or create a motion permit. Callers
must supply joint addresses from the compiled, content-bound MuJoCo model.
"""

from __future__ import annotations

import math
import time

from so101_demo.act.contracts import finite, identifier


class Task8ReadbackError(RuntimeError):
    """A required physical source is missing or disagrees with another."""


def _indices(value, length):
    if (not isinstance(value, tuple) or len(value) != length
            or any(type(index) is not int or index < 0 for index in value)
            or len(set(value)) != length):
        raise ValueError("TASK8_QPOS_INDICES_INVALID")
    return value


class Task8PhysicalReadback:
    def __init__(
        self, world, scene, contacts, rgb, broker, *, model_qpos_joint_indices,
        model_qpos_cup_indices, max_source_skew_s, max_wall_age_s,
        joint_tolerance_rad, cup_pose_tolerance_m, cup_orientation_tolerance,
        monotonic=time.monotonic,
    ) -> None:
        self.world, self.scene, self.contacts = world, scene, contacts
        self.rgb, self.broker, self.monotonic = rgb, broker, monotonic
        self.joints = _indices(model_qpos_joint_indices, 7)
        self.cup = _indices(model_qpos_cup_indices, 7)
        if set(self.joints) & set(self.cup):
            raise ValueError("TASK8_QPOS_INDICES_INVALID")
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
            received = self.world.snapshot_with_receipt()
            world = received.evidence
            now = finite(self.monotonic(), nonnegative=True)
            if not 0 <= now - received.received_monotonic_s <= self.max_wall_age or world.truncated:
                raise ValueError("world stale or truncated")
        except (AttributeError, TypeError, ValueError, RuntimeError) as error:
            raise Task8ReadbackError("WORLD_READBACK_UNAVAILABLE") from error
        try:
            scene = self.scene.snapshot()
        except (AttributeError, TypeError, ValueError, RuntimeError) as error:
            raise Task8ReadbackError("SCENE_READBACK_UNAVAILABLE") from error
        try:
            contact = self.contacts.snapshot()
        except (AttributeError, TypeError, ValueError, RuntimeError) as error:
            raise Task8ReadbackError("CONTACT_READBACK_UNAVAILABLE") from error
        expected = (session_id, reset_epoch)
        if any(actual != expected for actual in (
            (world.simulation_session_id, world.reset_epoch),
            (scene["simulation_session_id"], scene["reset_epoch"]),
            (contact["simulation_session_id"], contact["reset_epoch"]),
        )):
            raise Task8ReadbackError("SOURCE_SCOPE_MISMATCH")
        if (world.simulation_step != scene["simulation_step"]
                or world.simulation_step != contact["physics_step"]
                or world.paused != scene["paused"]):
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
        return {"world": world, "scene": scene, "contact": contact,
                "observation": observation, "reference": reference,
                "source_stamps_s": dict(audit["source_stamps"])}
