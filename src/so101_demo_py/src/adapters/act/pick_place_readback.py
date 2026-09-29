"""Read-only, same-step pick-place validation physics and controller evidence join.

This boundary does not infer a phase result or create a motion permit. Callers
must supply joint addresses from the compiled, content-bound MuJoCo model.
"""

from __future__ import annotations

import copy
import math
import time

from so101_demo.act.contracts import finite, identifier, sha256
from so101_demo.act.execution import bounded_positions
from so101_demo.act.joints import ACT_JOINTS, ARM_JOINTS


def _finite(value) -> bool:
    import math

    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


class PickPlaceReadbackError(RuntimeError):
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


class PickPlacePhysicalReadback:
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
        import mujoco
        self.joint_dofs = tuple(int(model.jnt_dofadr[
            mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_JOINT, name)
        ]) for name in ACT_JOINTS)
        self.max_skew = finite(max_source_skew_s)
        self.max_wall_age = finite(max_wall_age_s)
        self.joint_tolerance = finite(joint_tolerance_rad)
        self.cup_position_tolerance = finite(cup_pose_tolerance_m)
        self.cup_orientation_tolerance = finite(cup_orientation_tolerance)
        if min(self.max_skew, self.max_wall_age, self.joint_tolerance,
               self.cup_position_tolerance, self.cup_orientation_tolerance) <= 0:
            raise ValueError("TASK8_READBACK_CONFIG_INVALID")

    def capture(self, session_id: str, attempt_id: str, reset_epoch: int, *,
                after_step: int | None = None) -> dict:
        identifier(session_id)
        identifier(attempt_id)
        if type(reset_epoch) is not int or reset_epoch < 1:
            raise PickPlaceReadbackError("SOURCE_SCOPE_MISMATCH")
        if after_step is not None and (type(after_step) is not int or after_step < 0):
            raise PickPlaceReadbackError("SOURCE_STEP_CURSOR_INVALID")
        try:
            received = self.world.recent_with_receipts()
            now = finite(self.monotonic(), nonnegative=True)
            fresh = tuple(item for item in received
                          if 0 <= now - item.received_monotonic_s <= self.max_wall_age
                          and not item.evidence.truncated)
            if not fresh:
                raise ValueError("world stale or truncated")
            scoped = tuple(item for item in fresh
                           if (item.evidence.simulation_session_id,
                               item.evidence.reset_epoch) == (session_id, reset_epoch))
            if len({item.evidence.simulation_step for item in scoped}) != len(scoped):
                raise ValueError("duplicate world step")
            worlds = {item.evidence.simulation_step: item for item in scoped}
        except (AttributeError, TypeError, ValueError, RuntimeError) as error:
            raise PickPlaceReadbackError("WORLD_READBACK_UNAVAILABLE") from error
        try:
            scene_frames = self.scene.recent_frames_with_receipts()
        except (AttributeError, TypeError, ValueError, RuntimeError) as error:
            raise PickPlaceReadbackError("SCENE_READBACK_UNAVAILABLE") from error
        try:
            contact_frames = self.contacts.recent_frames_with_receipts()
        except (AttributeError, TypeError, ValueError, RuntimeError) as error:
            raise PickPlaceReadbackError("CONTACT_READBACK_UNAVAILABLE") from error
        scenes = {frame["simulation_step"]: (frame, received) for frame, received in scene_frames
                  if (frame["simulation_session_id"], frame["reset_epoch"])
                  == (session_id, reset_epoch)}
        contacts = {frame["physics_step"]: (frame, received) for frame, received in contact_frames
                    if (frame["simulation_session_id"], frame["reset_epoch"])
                    == (session_id, reset_epoch)}
        if not worlds or not scenes or not contacts:
            raise PickPlaceReadbackError("SOURCE_SCOPE_MISMATCH")
        common = worlds.keys() & scenes.keys() & contacts.keys()
        if not common:
            raise PickPlaceReadbackError("SOURCE_STEP_MISMATCH")
        if after_step is not None:
            common = {step for step in common if step > after_step}
            if not common:
                raise PickPlaceReadbackError("SOURCE_STEP_NOT_ADVANCED")
        step = max(common)
        world_entry = worlds[step]
        world = world_entry.evidence
        scene, scene_received = scenes[step]
        contact, contact_received = contacts[step]
        if world.paused != scene["paused"]:
            raise PickPlaceReadbackError("SOURCE_STEP_MISMATCH")
        at_s = world.simulation_time_s
        if any(abs(stamp - at_s) > self.max_skew for stamp in (
            scene["simulation_time_s"], contact["simulation_time_s"],
        )):
            raise PickPlaceReadbackError("SOURCE_TIME_SKEW")
        qpos = scene["qpos"]
        if max((*self.joints, *self.cup)) >= len(qpos):
            raise PickPlaceReadbackError("QPOS_MAPPING_INVALID")
        cup_position = tuple(qpos[index] for index in self.cup[:3])
        actual_position = world.object_state.position_world
        if math.dist(cup_position, actual_position) > self.cup_position_tolerance:
            raise PickPlaceReadbackError("CUP_QPOS_DIVERGED")
        cup_quaternion = tuple(qpos[index] for index in self.cup[3:])
        x, y, z, w = world.object_state.orientation_xyzw
        expected_quaternion = (w, x, y, z)
        if min(
            math.dist(cup_quaternion, expected_quaternion),
            math.dist(cup_quaternion, tuple(-value for value in expected_quaternion)),
        ) > self.cup_orientation_tolerance:
            raise PickPlaceReadbackError("CUP_QPOS_DIVERGED")
        try:
            reference = self.broker.reference_state(at_s)
            if (not isinstance(reference, dict)
                    or set(reference) != {"positions", "velocities", "accelerations", "requested_sim_time_s"}
                    or reference["requested_sim_time_s"] != at_s
                    or any(len(reference[key]) != 6 or any(not math.isfinite(value) for value in reference[key])
                           for key in ("positions", "velocities", "accelerations"))):
                raise ValueError("reference invalid")
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
            raise PickPlaceReadbackError("REFERENCE_READBACK_UNAVAILABLE") from error
        try:
            observation, audit = self.rgb.sample_with_audit(
                session_id, attempt_id, at_s)
            if any(abs(stamp - at_s) > self.max_skew for stamp in audit["source_stamps"].values()):
                raise ValueError("RGB_SOURCE_TIME_SKEW")
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
            raise PickPlaceReadbackError("RGB_READBACK_UNAVAILABLE") from error
        try:
            source_received = dict(audit["source_received_wall_s"])
            if set(source_received) != {"head", "wrist", "arm", "neck"}:
                raise ValueError("sensor receipt keys")
            source_received.update(world=world_entry.received_monotonic_s,
                                   scene=scene_received, contact=contact_received)
            if any(not 0 <= now - finite(value, nonnegative=True) <= self.max_wall_age
                   for value in source_received.values()):
                raise ValueError("source receipt stale")
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise PickPlaceReadbackError("SOURCE_RECEIPT_INVALID") from error
        measured = (*observation["state"][:6], audit["neck_yaw_rad"])
        if any(abs(measured[index] - qpos[address]) > self.joint_tolerance
               for index, address in enumerate(self.joints)):
            raise PickPlaceReadbackError("JOINT_QPOS_DIVERGED")
        if any(abs(reference["positions"][index] - measured[index]) > self.joint_tolerance
               for index in range(6)):
            raise PickPlaceReadbackError("REFERENCE_JOINT_DIVERGED")
        return {"world": world, "scene": scene, "contact": contact,
                "observation": observation, "reference": reference,
                "source_stamps_s": dict(audit["source_stamps"]),
                "source_received_wall_s": source_received}

    def capture_held_cup_handoff(
        self, session_id: str, attempt_id: str, reset_epoch: int, *,
        after_step: int, lift_goal_ids: tuple[str, str],
        commanded_positions, paired_execution, paired_goal_id: str,
        expected_prefix_sha256: str, expected_sequence: int,
    ) -> dict:
        """Capture a stopped LIFT handoff from the live broker without command authority."""
        if (type(after_step) is not int or after_step < 0
                or not isinstance(lift_goal_ids, tuple) or len(lift_goal_ids) != 2
                or lift_goal_ids[0] == lift_goal_ids[1]):
            raise PickPlaceReadbackError("HANDOFF_LIFT_GOAL_INVALID")
        try:
            goal_ids = tuple(identifier(goal_id) for goal_id in lift_goal_ids)
            commanded = bounded_positions(commanded_positions)
        except (TypeError, ValueError) as error:
            raise PickPlaceReadbackError("HANDOFF_LIFT_GOAL_INVALID") from error

        def stopped() -> bool:
            try:
                return self.broker.stopped() is True
            except (AttributeError, RuntimeError, ValueError):
                return False

        if not stopped():
            raise PickPlaceReadbackError("HANDOFF_STOP_UNCONFIRMED")
        try:
            identifier(paired_goal_id)
            sha256(expected_prefix_sha256)
            if (type(expected_sequence) is not int or expected_sequence < 0
                    or paired_execution.broker.driver is not self.broker):
                raise ValueError("pair ownership")
            pair = paired_execution.current_handoff_state(
                paired_goal_id, session_id, attempt_id)
            if (not isinstance(pair, dict) or pair.get("current_pair") is not True
                    or pair.get("pair_goal_id") != paired_goal_id
                    or pair.get("session_id") != session_id
                    or pair.get("attempt_id") != attempt_id
                    or pair.get("reset_epoch") != reset_epoch
                    or tuple(pair.get("goal_ids", ())) != goal_ids
                    or pair["epoch"]["session_id"] != session_id
                    or pair["epoch"]["reset_epoch"] != reset_epoch):
                raise ValueError("pair scope")
            audit = pair["audit"]
            if tuple(audit["goal_ids"]) != goal_ids:
                raise ValueError("pair audit")
            accepted_sim_s = finite(audit["accepted_sim_s"], nonnegative=True)
            if (audit["prefix_sha256"] != expected_prefix_sha256
                    or len(audit["goals"]) != 2
                    or any(goal.get("session_id") != session_id
                           or goal.get("attempt_id") != attempt_id
                           or goal.get("sequence") != expected_sequence
                           or goal.get("prefix_sha256") != expected_prefix_sha256
                           for goal in audit["goals"])):
                raise ValueError("pair scope")
            endpoints = []
            trajectory_ends = []
            if (audit["goals"][0]["header_stamp_s"] != audit["goals"][1]["header_stamp_s"]
                    or tuple(audit["goals"][0]["time_from_start_s"])
                    != tuple(audit["goals"][1]["time_from_start_s"])):
                raise ValueError("controller schedules disagree")
            for submitted, names, width in zip(
                    audit["goals"], (ARM_JOINTS[:5], ARM_JOINTS[5:]), (5, 1), strict=True):
                if (tuple(submitted["joint_names"]) != names
                        or len(submitted["positions"]) != len(submitted["time_from_start_s"])
                        or len(submitted["positions"]) < 2):
                    raise ValueError("submitted trajectory")
                endpoint = tuple(finite(value) for value in submitted["positions"][-1])
                if len(endpoint) != width:
                    raise ValueError("submitted endpoint")
                endpoints.extend(endpoint)
                end_s = finite(submitted["header_stamp_s"], nonnegative=True) + finite(
                    submitted["time_from_start_s"][-1], nonnegative=True)
                if end_s <= accepted_sim_s:
                    raise ValueError("submitted end")
                trajectory_ends.append(end_s)
            if tuple(endpoints) != commanded:
                raise ValueError("command endpoint substitution")
            goals = tuple(pair["controllers"])
            if len(goals) != 2:
                raise ValueError("controller pair")
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, PermissionError) as error:
            raise PickPlaceReadbackError("HANDOFF_LIFT_PROVENANCE_INVALID") from error
        try:
            result_sim_times = []
            result_wall_times = []
            for goal, length in zip(goals, (5, 1), strict=True):
                if (not isinstance(goal, dict) or goal.get("accepted") is not True
                        or goal.get("status") != 4
                        or goal.get("driver_error") is not None
                        or not isinstance(goal.get("result"), dict)
                        or goal["result"].get("error_code") != 0):
                    raise ValueError("terminal goal")
                actual = goal["feedback"]["actual"]["positions"]
                if len(actual) != length or any(not math.isfinite(finite(value))
                                                for value in actual):
                    raise ValueError("goal feedback")
                result_sim_times.append(finite(goal["result_received_sim_s"], nonnegative=True))
                result_wall_times.append(finite(goal["result_received_wall_s"], nonnegative=True))
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
            raise PickPlaceReadbackError("HANDOFF_LIFT_GOAL_INVALID") from error
        raw = self.capture(session_id, attempt_id, reset_epoch, after_step=after_step)
        sample_s = raw["world"].simulation_time_s
        if max(accepted_sim_s, *trajectory_ends, *result_sim_times) >= sample_s:
            raise PickPlaceReadbackError("HANDOFF_LIFT_PROVENANCE_INVALID")
        try:
            proof = self.broker.stationary_reference_proof(sample_s)
            if (proof["requested_sim_time_s"] != sample_s
                    or proof["epoch"]["session_id"] != session_id
                    or proof["epoch"]["reset_epoch"] != reset_epoch
                    or finite(proof["stop_confirmed_wall_s"], nonnegative=True)
                    < max(result_wall_times)):
                raise ValueError("reference scope or stop")
            for kind, width, offset in (("arm", 5, 0), ("gripper", 1, 5)):
                row = proof["references"][kind]
                publication = finite(row["publication_sim_time_s"], nonnegative=True)
                if (not max(*trajectory_ends, *result_sim_times) < publication <= sample_s
                        or sample_s - publication > self.max_skew
                        or row["received_wall_s"] < proof["stop_confirmed_wall_s"]
                        or tuple(row["positions"]) != tuple(raw["reference"]["positions"][offset:offset + width])
                        or tuple(row["velocities"]) != tuple(raw["reference"]["velocities"][offset:offset + width])):
                    raise ValueError("reference provenance")
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError) as error:
            raise PickPlaceReadbackError("HANDOFF_REFERENCE_PROVENANCE_INVALID") from error
        try:
            end_pair = paired_execution.current_handoff_state(
                paired_goal_id, session_id, attempt_id)
            if any(end_pair[key] != pair[key] for key in (
                    "pair_goal_id", "generation", "reset_epoch", "session_id",
                    "attempt_id", "goal_ids", "audit", "controllers")):
                raise ValueError("pair changed")
            if (end_pair["epoch"]["session_id"] != session_id
                    or end_pair["epoch"]["reset_epoch"] != reset_epoch):
                raise ValueError("epoch changed")
        except (AttributeError, KeyError, TypeError, ValueError, RuntimeError, PermissionError) as error:
            raise PickPlaceReadbackError("HANDOFF_LIFT_PROVENANCE_INVALID") from error
        if not stopped():
            raise PickPlaceReadbackError("HANDOFF_STOP_UNCONFIRMED")
        try:
            qvel = raw["scene"]["qvel"]
            stop_velocity = finite(self.broker.stop_velocity)
            if (stop_velocity < 0 or max(self.joint_dofs) >= len(qvel)
                    or any(abs(finite(qvel[index])) > stop_velocity
                           for index in self.joint_dofs)):
                raise ValueError("moving measured joints")
        except (KeyError, TypeError, ValueError) as error:
            raise PickPlaceReadbackError("HANDOFF_MEASURED_MOTION") from error
        measured = tuple(raw["scene"]["qpos"][address] for address in self.joints[:6])
        if any(abs(actual - target) > self.joint_tolerance
               for actual, target in zip(measured, commanded, strict=True)):
            raise PickPlaceReadbackError("HANDOFF_COMMAND_DRIFT")
        if any(abs(actual - measured[index]) > self.joint_tolerance
               for index, actual in enumerate((
                   *goals[0]["feedback"]["actual"]["positions"],
                   *goals[1]["feedback"]["actual"]["positions"],
               ))):
            raise PickPlaceReadbackError("HANDOFF_FEEDBACK_DIVERGED")
        try:
            reference = raw["reference"]
            if (stop_velocity < 0
                    or any(abs(finite(value)) > stop_velocity
                           for value in reference["velocities"])):
                raise ValueError("moving reference")
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise PickPlaceReadbackError("HANDOFF_REFERENCE_MOVING") from error
        return {
            "session_id": session_id, "attempt_id": attempt_id,
            "reset_epoch": reset_epoch,
            "physics_step": raw["world"].simulation_step,
            "paired_goal_id": paired_goal_id,
            "lift_goal_ids": goal_ids,
            "lift_prefix_sha256": expected_prefix_sha256,
            "lift_sequence": expected_sequence,
            "lift_accepted_sim_time_s": accepted_sim_s,
            "pair_audit": copy.deepcopy(audit),
            "commanded_lift_endpoint_rad": commanded,
            "measured_positions_rad": measured,
            "controller_reference": copy.deepcopy(reference),
            "terminal_goals": copy.deepcopy(goals),
            "stationary_reference_proof": copy.deepcopy(proof),
            "physical_readback": raw,
            "controller_stop_confirmed": True,
            "command_authority": False,
        }


    def live_evidence_sample(self, *, identity, phase, physics_step, sim_time_s,
                             source_stamps_s, source_received_monotonic_s, raw_records,
                             holding_state, frame, contact, measurements):
        """Emit one canonical live-evidence sample for the frozen 10 Hz grid.

        The readback owns the values; the canonical shape lives in one place so this adapter and
        the search port cannot drift apart. Extracting the values directly from the capture path
        for CLOSE..FINAL_CHECK is the remaining wiring step.
        """

        from so101_demo.act.task8_live_evidence import build_live_evidence_sample

        return build_live_evidence_sample(
            identity=identity, phase=phase, physics_step=physics_step, sim_time_s=sim_time_s,
            source_stamps_s=source_stamps_s,
            source_received_monotonic_s=source_received_monotonic_s,
            raw_records=raw_records, holding_state=holding_state, frame=frame, contact=contact,
            measurements=measurements,
        )


    def capture_evidence_fields(self, captured, *, support_distance_max_m, raw_records,
                               end_effector_position_m=None):
        """The adapter's entry point: the module-level derivation below, which touches no adapter state."""

        return capture_evidence_fields(captured, support_distance_max_m=support_distance_max_m,
                                       raw_records=raw_records,
                                       end_effector_position_m=end_effector_position_m)


def capture_evidence_fields(captured, *, support_distance_max_m, raw_records,
                           end_effector_position_m=None):
    """The canonical per-frame fields one capture() can supply, for CLOSE..FINAL_CHECK.

    The physics aggregates come from the world evidence (never from a label); the step, sim time,
    both stamp maps and the caller's dereferenceable raw records complete the frame. The
    release-epoch-relative fields are the phase sequence's business, not this method's.
    """

    from so101_demo.act.task8_live_evidence import derive_frame_aggregates

    if type(captured) is not dict or set(captured) != {
            "world", "scene", "contact", "observation", "reference", "source_stamps_s",
            "source_received_wall_s"}:
        raise PickPlaceReadbackError("READBACK_CAPTURE_INVALID")
    world = captured["world"]
    aggregates = derive_frame_aggregates(world, support_distance_max_m=support_distance_max_m)
    step = getattr(world, "simulation_step", None)
    at_s = getattr(world, "simulation_time_s", None)
    if type(step) is not int or step < 0 or not math.isfinite(at_s) or at_s < 0:
        raise PickPlaceReadbackError("READBACK_CAPTURE_INVALID")
    # the end-effector position is MuJoCo output, so the caller that holds the model supplies it; the recorder
    # requires it, and a frame without it must not be recorded as if it had one
    position = end_effector_position_m
    if (not isinstance(position, (list, tuple)) or len(position) != 3
            or any(not _finite(value) for value in position)):
        raise PickPlaceReadbackError("READBACK_END_EFFECTOR_REQUIRED")
    # the recorder's canonical vocabulary is seven sources, while the synchronizer's audit covers the four sensor
    # streams - so the three physics sources are stamped from their OWN documents here, which the capture already
    # validated against each other. For their receive time the capture records none: the scene carries its own
    # monotonic bounds, and world/contact are validated to be within the readback skew of it, so the scene's receipt
    # is used for all three and named as such rather than invented per source.
    scene_document = captured["scene"]
    contact_document = captured["contact"]
    scene_receipt_ns = scene_document["clock_interval_end_monotonic_ns"]
    # the scene's monotonic bound is nanoseconds: an int in the real capture, and accepted as a finite number here
    # rather than pinned to one Python type
    if (not isinstance(scene_receipt_ns, (int, float)) or isinstance(scene_receipt_ns, bool)
            or not _finite(float(scene_receipt_ns)) or float(scene_receipt_ns) <= 0):
        # the refusal names what it saw: "invalid" alone cost a diagnostic round when this was first hit
        raise PickPlaceReadbackError(
            f"READBACK_CAPTURE_INVALID: scene clock {type(scene_receipt_ns).__name__}={scene_receipt_ns!r}")
    physics_stamps = {"world": float(getattr(world, "simulation_time_s")),
                      "scene": float(scene_document["simulation_time_s"]),
                      "contact": float(contact_document["simulation_time_s"])}
    if len(set(physics_stamps.values())) > 1 and \
            max(physics_stamps.values()) - min(physics_stamps.values()) > 0:
        pass                                  # their agreement is _search_evidence's rule, not this function's
    stamps = {**dict(captured["source_stamps_s"]), **physics_stamps}
    received = {**dict(captured["source_received_wall_s"]),
                **{name: scene_receipt_ns / 1e9 for name in physics_stamps}}
    return {**aggregates, "physics_step": step, "sim_time_s": at_s,
            "end_effector_position_m": list(position),
            "source_stamps_s": stamps,
            "source_received_monotonic_s": received,
            "raw_records": dict(raw_records)}




# Legacy Python API for version-one pick-place callers.
Task8ReadbackError = PickPlaceReadbackError
Task8PhysicalReadback = PickPlacePhysicalReadback
