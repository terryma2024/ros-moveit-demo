"""Lossless, fail-closed ACT live physics chunk recorder.

The command owner supplies a single reset epoch and forwards immutable physics
chunks here. This module has no ROS imports or authority to move the robot.
"""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path
from typing import Any, Callable

_CHUNK_KEYS = frozenset({
    "chunk_sequence", "simulation_session_id", "reset_epoch", "first_physics_step",
    "last_physics_step", "first_simulation_time_s", "last_simulation_time_s",
    "failed_publish_attempts", "evidence_loss", "samples",
})
_STEP_KEYS = frozenset({
    "simulation_session_id", "reset_epoch", "physics_step", "simulation_time_s",
    "model_qpos", "model_qvel", "cup_position_m", "cup_velocity_m_s",
    "left_contacts", "right_contacts", "other_contacts", "truncated",
    "diagnostic_hazard_breached",
})
_CONTACT_KEYS = frozenset({
    "robot_geom", "object_body", "normal_force_n", "signed_distance_m",
})
_LIMIT_KEYS = frozenset({
    "maximum_force_n", "maximum_displacement_m", "maximum_ros_skew_s",
    "maximum_receipt_age_s",
})


def _exact(value: Any, keys: frozenset[str], name: str) -> dict:
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError(f"{name} has missing or unknown fields")
    return value


def _finite(value: Any, name: str, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError(f"{name} is not finite")
    result = float(value)
    if not math.isfinite(result) or (minimum is not None and result < minimum):
        raise ValueError(f"{name} is not finite or below limit")
    return result


def _integer(value: Any, name: str, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} is not an admissible integer")
    return value


def _vector(value: Any, length: int, name: str) -> list[float]:
    if not isinstance(value, list) or len(value) != length:
        raise ValueError(f"{name} length mismatch")
    return [_finite(item, name) for item in value]


def chunk_from_ros(
    message: Any, *, cup_qpos_address: int, cup_qvel_address: int,
) -> dict:
    """Convert the actual 500 Hz ROS message without inventing per-step state."""

    def contacts(items: Any, category: str) -> list[dict]:
        converted = []
        for contact in items:
            geom = contact.geom2
            if contact.body1 != "plastic_cup" or not contact.geom1:
                raise ValueError("live contact is not bound to the cup")
            if category == "left_contacts":
                allowed = geom.startswith((
                    "fixed_fingertip_pad_collision_", "fixed_finger_contact_convex_",
                ))
            elif category == "right_contacts":
                allowed = geom.startswith((
                    "moving_fingertip_pad_collision_", "moving_jaw_contact_convex_",
                ))
            else:
                allowed = geom == "table_collision"
            if not allowed:
                raise ValueError("live contact category/geometry mismatch")
            converted.append({
                "robot_geom": geom, "object_body": contact.body1,
                "normal_force_n": _finite(contact.normal_force_n, "normal_force_n", 0),
                "signed_distance_m": _finite(contact.signed_distance_m, "signed_distance_m"),
            })
        return converted

    try:
        _integer(cup_qpos_address, "cup_qpos_address")
        _integer(cup_qvel_address, "cup_qvel_address")
        samples = []
        for sample in message.samples:
            qpos = [_finite(value, "model_qpos") for value in sample.model_qpos]
            qvel = [_finite(value, "model_qvel") for value in sample.model_qvel]
            cup = qpos[cup_qpos_address:cup_qpos_address + 3]
            velocity = qvel[cup_qvel_address:cup_qvel_address + 3]
            if len(cup) != 3 or len(velocity) != 3:
                raise ValueError("live MuJoCo state is incomplete")
            pose = sample.object_pose_world.position
            if any(abs(a - _finite(getattr(pose, axis), axis)) > 1e-8
                   for a, axis in zip(cup, ("x", "y", "z"), strict=True)):
                raise ValueError("live object pose disagrees with MuJoCo state")
            grouped = {
                "left_contacts": contacts(sample.left_fingertip_contacts, "left_contacts"),
                "right_contacts": contacts(sample.right_fingertip_contacts, "right_contacts"),
                "other_contacts": contacts(sample.other_object_contacts, "other_contacts"),
            }
            maximum = max((item["normal_force_n"] for group in grouped.values()
                           for item in group), default=0.0)
            total = sum(item["normal_force_n"] for group in grouped.values()
                        for item in group)
            if (abs(maximum - _finite(sample.maximum_normal_force_n,
                                     "maximum_normal_force_n", 0)) > 1e-8
                    or abs(maximum - _finite(sample.global_max_single_contact_force_n,
                                             "global_max_single_contact_force_n", 0)) > 1e-8
                    or abs(total - _finite(sample.total_normal_force_n,
                                           "total_normal_force_n", 0)) > 1e-8):
                raise ValueError("live reported force disagrees with contacts")
            samples.append({
                "simulation_session_id": sample.simulation_session_id,
                "reset_epoch": sample.reset_epoch,
                "physics_step": sample.physics_step,
                "simulation_time_s": sample.simulation_time_s,
                "model_qpos": qpos, "model_qvel": qvel,
                "cup_position_m": cup, "cup_velocity_m_s": velocity,
                **grouped,
                "truncated": sample.truncated,
                "diagnostic_hazard_breached": sample.diagnostic_hazard_breached,
            })
        return {
            "chunk_sequence": message.chunk_sequence,
            "simulation_session_id": message.simulation_session_id,
            "reset_epoch": message.reset_epoch,
            "first_physics_step": message.first_physics_step,
            "last_physics_step": message.last_physics_step,
            "first_simulation_time_s": message.first_simulation_time_s,
            "last_simulation_time_s": message.last_simulation_time_s,
            "failed_publish_attempts": message.failed_publish_attempts,
            "evidence_loss": message.evidence_loss,
            "samples": samples,
        }
    except (AttributeError, IndexError, TypeError) as error:
        raise ValueError("live ROS physics message is incomplete") from error


class LivePhysicsStream:
    """Append verified per-step evidence, fsync each chunk, latch every hazard."""

    def __init__(
        self, *, session_id: str, reset_epoch: int, model_sha256: str,
        model_nq: int, model_nv: int, cup_qpos_address: int,
        cup_qvel_address: int, diagnostic_limits: dict,
        output_path: Path, release_qpos_address: int | None = None,
        release_qvel_address: int | None = None,
        release_open_q6: float | None = None,
        release_stop_velocity_rad_s: float = .002,
        monotonic: Callable[[], float] = time.monotonic,
        startup_receipt_grace_s: float | None = None,
    ) -> None:
        if not isinstance(session_id, str) or not session_id:
            raise ValueError("live session identity is missing")
        _integer(reset_epoch, "reset_epoch", 1)
        if (not isinstance(model_sha256, str) or len(model_sha256) != 64
                or any(character not in "0123456789abcdef" for character in model_sha256)):
            raise ValueError("model hash is invalid")
        self.model_nq = _integer(model_nq, "model_nq", 3)
        self.model_nv = _integer(model_nv, "model_nv", 3)
        self.cup_qpos_address = _integer(cup_qpos_address, "cup_qpos_address")
        self.cup_qvel_address = _integer(cup_qvel_address, "cup_qvel_address")
        if self.cup_qpos_address + 3 > model_nq or self.cup_qvel_address + 3 > model_nv:
            raise ValueError("cup state addresses exceed model")
        release_values = (release_qpos_address, release_qvel_address, release_open_q6)
        if any(value is not None for value in release_values):
            if any(value is None for value in release_values):
                raise ValueError("release state binding is incomplete")
            if (_integer(release_qpos_address, "release_qpos_address") >= model_nq or
                    _integer(release_qvel_address, "release_qvel_address") >= model_nv):
                raise ValueError("release state address exceeds model")
            _finite(release_open_q6, "release_open_q6")
        self.release_qpos_address = release_qpos_address
        self.release_qvel_address = release_qvel_address
        self.release_open_q6 = release_open_q6
        self.release_stop_velocity = _finite(
            release_stop_velocity_rad_s, "release_stop_velocity_rad_s", 0)
        if self.release_stop_velocity == 0:
            raise ValueError("release stop velocity must be positive")
        limits = _exact(diagnostic_limits, _LIMIT_KEYS, "diagnostic limits")
        self.limits = {key: _finite(value, key, 0) for key, value in limits.items()}
        if any(value == 0 for value in self.limits.values()):
            raise ValueError("diagnostic limits must be positive")
        self.startup_receipt_grace_s = (
            self.limits["maximum_receipt_age_s"] if startup_receipt_grace_s is None
            else _finite(startup_receipt_grace_s, "startup receipt grace", 0)
        )
        if self.startup_receipt_grace_s < self.limits["maximum_receipt_age_s"]:
            raise ValueError("startup receipt grace is too short")
        self.session_id, self.reset_epoch = session_id, reset_epoch
        self.model_sha256 = model_sha256
        self.monotonic = monotonic
        self.output_path = Path(output_path)
        descriptor = os.open(self.output_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o640)
        self._stream = os.fdopen(descriptor, "wb")
        self._closed = False
        self.hazard: str | None = None
        self.recorded_steps = 0
        self._last_chunk_sequence: int | None = None
        self._last_step = 0
        self._last_time = 0.0
        self._last_receipt = -math.inf
        self._receipt_age_anchor = -math.inf
        self._receipt_deadline_suspended = False
        self._initial_cup: list[float] | None = None
        self._seen_bilateral = False
        directory = os.open(self.output_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def suspend_receipt_deadline(self) -> None:
        self._receipt_deadline_suspended = True

    def resume_receipt_deadline(self) -> None:
        if self._receipt_deadline_suspended:
            self._receipt_age_anchor = _finite(self.monotonic(), "receipt resume", 0)
            self._receipt_deadline_suspended = False


    def _validated_step(
        self, value: Any, expected_step: int, previous_time: float,
        initial_cup: list[float] | None, ros_time_s: float,
    ) -> dict:
        step = _exact(value, _STEP_KEYS, "live physics step")
        if (step["simulation_session_id"], step["reset_epoch"]) != (
            self.session_id, self.reset_epoch
        ):
            raise ValueError("live step identity mismatch")
        if _integer(step["physics_step"], "physics_step", 1) != expected_step:
            raise ValueError("live physics step gap")
        simulation_time = _finite(step["simulation_time_s"], "simulation_time_s", 0)
        if simulation_time <= previous_time:
            raise ValueError("live physics clock is stale")
        qpos = _vector(step["model_qpos"], self.model_nq, "model_qpos")
        qvel = _vector(step["model_qvel"], self.model_nv, "model_qvel")
        cup = _vector(step["cup_position_m"], 3, "cup_position_m")
        velocity = _vector(step["cup_velocity_m_s"], 3, "cup_velocity_m_s")
        if any(abs(a-b) > 1e-8 for a, b in zip(
            qpos[self.cup_qpos_address:self.cup_qpos_address+3], cup, strict=True
        )) or any(abs(a-b) > 1e-8 for a, b in zip(
            qvel[self.cup_qvel_address:self.cup_qvel_address+3], velocity, strict=True
        )):
            raise ValueError("cup state disagrees with same-step MuJoCo state")
        if step["truncated"] is not False or step["diagnostic_hazard_breached"] is not False:
            raise ValueError("live physics contact stream is truncated or hazardous")
        initial = initial_cup if initial_cup is not None else cup
        if math.dist(cup, initial) > self.limits["maximum_displacement_m"]:
            raise ValueError("live diagnostic displacement hard stop")
        total_force = 0.0
        contacts = {}
        for field in ("left_contacts", "right_contacts", "other_contacts"):
            items = step[field]
            if not isinstance(items, list):
                raise ValueError("live contact field is not a list")
            checked = []
            for item in items:
                contact = _exact(item, _CONTACT_KEYS, "live contact")
                if (not isinstance(contact["robot_geom"], str) or not contact["robot_geom"]
                        or contact["object_body"] != "plastic_cup"):
                    raise ValueError("live contact geometry/body mismatch")
                force = _finite(contact["normal_force_n"], "normal_force_n", 0)
                _finite(contact["signed_distance_m"], "signed_distance_m")
                total_force += force
                checked.append(contact)
            contacts[field] = checked
        if total_force > self.limits["maximum_force_n"]:
            raise ValueError("live diagnostic force hard stop")
        return {
            "simulation_session_id": self.session_id,
            "reset_epoch": self.reset_epoch,
            "model_sha256": self.model_sha256,
            "physics_step": expected_step,
            "simulation_time_s": simulation_time,
            "ros_time_s": ros_time_s,
            "received_monotonic_s": _finite(self.monotonic(), "receipt", 0),
            "left_contacts": contacts["left_contacts"],
            "right_contacts": contacts["right_contacts"],
            "other_contacts": contacts["other_contacts"],
            "cup_position_m": cup, "cup_velocity_m_s": velocity,
            "model_qpos": qpos, "model_qvel": qvel,
            "table_supported": any(
                contact["robot_geom"] == "table_collision"
                for contact in contacts["other_contacts"]
            ),
            "released": False,
        }

    def accept_chunk(self, value: Any, *, ros_time_s: float | None = None) -> None:
        if self._closed or self.hazard is not None:
            raise ValueError(self.hazard or "live physics recorder closed")
        try:
            chunk = _exact(value, _CHUNK_KEYS, "live physics chunk")
            sequence = _integer(chunk["chunk_sequence"], "chunk_sequence")
            if self._last_chunk_sequence is not None and sequence != self._last_chunk_sequence + 1:
                raise ValueError("live chunk sequence gap")
            if (chunk["simulation_session_id"], chunk["reset_epoch"]) != (
                self.session_id, self.reset_epoch
            ):
                raise ValueError("live chunk identity mismatch")
            if chunk["evidence_loss"] is not False or _integer(
                chunk["failed_publish_attempts"], "failed_publish_attempts"
            ) != 0:
                raise ValueError("lossless live evidence guarantee failed")
            samples = chunk["samples"]
            if not isinstance(samples, list) or not samples:
                raise ValueError("live chunk has no samples")
            first = _integer(chunk["first_physics_step"], "first_physics_step", 1)
            last = _integer(chunk["last_physics_step"], "last_physics_step", 1)
            if first != self._last_step + 1 or last != first + len(samples) - 1:
                raise ValueError("live chunk physics step gap")
            if ros_time_s is None:
                raise ValueError("live ROS clock is missing")
            ros_time_s = _finite(ros_time_s, "ros_time_s", 0)
            last_simulation_time = _finite(
                chunk["last_simulation_time_s"], "last_simulation_time_s", 0
            )
            if abs(ros_time_s - last_simulation_time) > self.limits["maximum_ros_skew_s"]:
                raise ValueError("live ROS/MuJoCo clock skew")
            receipt_limit = (self.startup_receipt_grace_s if self.recorded_steps == 0
                             else self.limits["maximum_receipt_age_s"])
            if not self._receipt_deadline_suspended and self._receipt_age_anchor != -math.inf and (
                self.monotonic() - self._receipt_age_anchor > receipt_limit
            ):
                raise ValueError("live physics evidence is stale")
            parsed = []
            previous_time = self._last_time
            initial_cup = self._initial_cup
            seen_bilateral = self._seen_bilateral
            for index, sample in enumerate(samples):
                row = self._validated_step(
                    sample, first + index, previous_time, initial_cup,
                    ros_time_s - (last_simulation_time - sample["simulation_time_s"]),
                )
                if row["left_contacts"] and row["right_contacts"]:
                    seen_bilateral = True
                if (self.release_qpos_address is not None and seen_bilateral and
                        row["table_supported"] and not row["left_contacts"] and
                        not row["right_contacts"] and
                        abs(row["model_qpos"][self.release_qpos_address] - self.release_open_q6) <= .002 and
                        abs(row["model_qvel"][self.release_qvel_address]) <= self.release_stop_velocity):
                    row["released"] = True
                if row["received_monotonic_s"] <= self._last_receipt or (
                    parsed and row["received_monotonic_s"] <= parsed[-1]["received_monotonic_s"]
                ):
                    raise ValueError("live monotonic receipt did not advance")
                parsed.append(row)
                if initial_cup is None:
                    initial_cup = row["cup_position_m"]
                previous_time = row["simulation_time_s"]
            if (parsed[0]["simulation_time_s"] != _finite(
                chunk["first_simulation_time_s"], "first_simulation_time_s", 0
            ) or parsed[-1]["simulation_time_s"] != _finite(
                chunk["last_simulation_time_s"], "last_simulation_time_s", 0
            )):
                raise ValueError("live chunk time envelope mismatch")
            payload = b"".join(
                json.dumps(row, sort_keys=True, separators=(",", ":"),
                           allow_nan=False).encode() + b"\n" for row in parsed
            )
            self._stream.write(payload)
            self._stream.flush()
            os.fsync(self._stream.fileno())
            self._last_chunk_sequence = sequence
            self._last_step = last
            self._last_time = previous_time
            self._last_receipt = parsed[-1]["received_monotonic_s"]
            self._receipt_age_anchor = self._last_receipt
            self._initial_cup = self._initial_cup or parsed[0]["cup_position_m"]
            self._seen_bilateral = seen_bilateral
            self.recorded_steps += len(parsed)
        except (OSError, TypeError, ValueError) as error:
            self.hazard = str(error)
            raise ValueError(self.hazard) from error

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._stream.flush()
        os.fsync(self._stream.fileno())
        self._stream.close()
        directory = os.open(self.output_path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)


class LiveContactObserver:
    """Bind live ROS evidence to a single stop callback and recorder epoch."""

    def __init__(
        self, recorder: LivePhysicsStream, *, ros_clock: Callable[[], float],
        monotonic: Callable[[], float], on_abort: Callable[[str], None],
        startup_receipt_grace_s: float | None = None,
    ) -> None:
        self.recorder = recorder
        self.ros_clock = ros_clock
        self.monotonic = monotonic
        self.on_abort = on_abort
        self.startup_receipt_grace_s = (
            recorder.limits["maximum_receipt_age_s"] if startup_receipt_grace_s is None
            else _finite(startup_receipt_grace_s, "startup receipt grace", 0)
        )
        if self.startup_receipt_grace_s < recorder.limits["maximum_receipt_age_s"]:
            raise ValueError("startup receipt grace is too short")
        self.hazard: str | None = None
        self._last_received = _finite(monotonic(), "observer start", 0)
        self.active = False
        self._suspended = False

    def start(self) -> None:
        if self.hazard is not None:
            raise ValueError(self.hazard)
        if self._suspended:
            self.recorder.resume_receipt_deadline()
            self._suspended = False
            self._last_received = _finite(self.monotonic(), "observer start", 0)
            self.active = True
        elif not self.active:
            self._last_received = _finite(self.monotonic(), "observer start", 0)
            self.active = True

    def suspend(self) -> None:
        self.recorder.suspend_receipt_deadline()
        self._suspended = True
        self.active = False

    def _abort(self, reason: str) -> None:
        if self.hazard is None:
            self.hazard = reason
            self.on_abort(reason)

    def accept_chunk(self, message: Any) -> None:
        if self.hazard is not None:
            return
        try:
            converted = chunk_from_ros(
                message, cup_qpos_address=self.recorder.cup_qpos_address,
                cup_qvel_address=self.recorder.cup_qvel_address,
            )
            self.recorder.accept_chunk(converted, ros_time_s=self.ros_clock())
            self._last_received = _finite(self.monotonic(), "observer receipt", 0)
            self.active = True
        except (AttributeError, OSError, TypeError, ValueError) as error:
            self._abort(f"LIVE_CONTACT_EVIDENCE_INVALID:{error}")

    def accept_hazard(self, message: Any) -> None:
        if self.hazard is not None:
            return
        try:
            if (message.simulation_session_id != self.recorder.session_id
                    or message.reset_epoch != self.recorder.reset_epoch
                    or _integer(message.physics_step, "hazard physics_step", 1) < 1
                    or _finite(message.force_n, "hazard force", 0) <
                    _finite(message.threshold_n, "hazard threshold", 0)
                    or type(message.evidence_loss) is not bool):
                raise ValueError("hazard identity or force is invalid")
            self._abort("LIVE_CONTACT_DIAGNOSTIC_HAZARD")
        except (AttributeError, TypeError, ValueError) as error:
            self._abort(f"LIVE_CONTACT_HAZARD_INVALID:{error}")

    def poll(self) -> None:
        deadline = (self.startup_receipt_grace_s if self.recorder.recorded_steps == 0
                    else self.recorder.limits["maximum_receipt_age_s"])
        if self.active and self.hazard is None and (
            self.monotonic() - self._last_received > deadline
        ):
            self._abort("LIVE_CONTACT_EVIDENCE_STALE")

    def close(self) -> None:
        self.recorder.close()


class RosLiveContactAdapter:
    """Attach one read-only live observer to the existing MuJoCo evidence topics."""

    def __init__(self, node: Any, observer: LiveContactObserver) -> None:
        from rclpy.qos import DurabilityPolicy, QoSProfile, ReliabilityPolicy
        from so101_mujoco_support.msg import PhysicsHazardLatch, PhysicsStepEvidenceChunk

        self.node = node
        self.observer = observer
        self.subscriptions: list[Any] = []
        self.timer: Any | None = None
        chunks = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE)
        hazards = QoSProfile(
            depth=1, reliability=ReliabilityPolicy.RELIABLE,
            durability=DurabilityPolicy.TRANSIENT_LOCAL,
        )
        try:
            self.subscriptions.append(node.create_subscription(
                PhysicsStepEvidenceChunk, "/so101/simulation/physics_step_chunks",
                observer.accept_chunk, chunks,
            ))
            self.subscriptions.append(node.create_subscription(
                PhysicsHazardLatch, "/so101/simulation/physics_hazard",
                observer.accept_hazard, hazards,
            ))
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        if self.timer is not None:
            self.node.destroy_timer(self.timer)
            self.timer = None
        for handle in self.subscriptions:
            self.node.destroy_subscription(handle)
        self.subscriptions.clear()
        self.observer.close()
