"""Guarded pick-place validation reset through the admitted child's sole command authority."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

import mujoco

from so101_demo.act.joints import ACT_JOINTS
from so101_demo.act.pick_place_validation_manifest import require_pick_place_validation_manifest
from so101_demo.backends.mujoco.client import (
    FreeJointResetOverride, JointResetOverride, MujocoRosClient,
)
from so101_demo.backends.mujoco.reset import MujocoResetClient
from .pick_place_readback import compiled_qpos_mapping


@dataclass(frozen=True, slots=True)
class PickPlaceResetTargets:
    case_id: str
    anchor: str
    joints_rad: tuple[float, ...]
    cup_start_m: tuple[float, float, float]


def pick_place_reset_targets(model, manifest: dict, request: dict, *, expected_model_sha256: str,
                        expected_mujoco_version: str) -> PickPlaceResetTargets:
    """Resolve one frozen case against the installed model's named keyframe."""
    require_pick_place_validation_manifest(manifest)
    joints, _ = compiled_qpos_mapping(
        model, expected_model_sha256=expected_model_sha256,
        expected_mujoco_version=expected_mujoco_version,
    )
    cases = (*manifest["prefix_cases"], *manifest["full_cases"])
    matches = [case for case in cases if case["case_id"] == request.get("scenario_id")]
    if len(matches) != 1:
        raise ValueError("TASK8_CASE_NOT_FROZEN")
    case = matches[0]
    if any(request.get(key) != case[key] for key in ("mode", "stop_after", "lifecycle")):
        raise ValueError("TASK8_CASE_MISMATCH")
    key = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_KEY, "task_start")
    if key < 0:
        raise ValueError("TASK8_RESET_KEYFRAME_MISSING")
    positions = tuple(float(model.key_qpos[key, address]) for address in joints)
    anchor = manifest["anchors"][case["anchor"]]
    positions = (*positions[:6], float(anchor["neck_start_rad"]))
    if len(positions) != len(ACT_JOINTS) or any(not math.isfinite(value) for value in positions):
        raise ValueError("TASK8_RESET_TARGET_INVALID")
    for name, value in zip(ACT_JOINTS, positions, strict=True):
        JointResetOverride(name, value)
    return PickPlaceResetTargets(
        case_id=case["case_id"], anchor=case["anchor"], joints_rad=positions,
        cup_start_m=tuple(anchor["cup_start_m"]),
    )


class PickPlaceResetBoundary:
    """Run one measured reset, then transfer recovery authority to the ACT attempt."""

    def __init__(self, *, node, model, manifest, sources, command_broker, connection,
                 cancelled, service_node_factory, reset_timeout_s=30.0,
                 transition_timeout_s=5.0, monotonic=time.monotonic,
                 clock_ns=time.monotonic_ns):
        if (connection.broker is not command_broker
                or sources.session_id != command_broker.simulation_session_id
                or not callable(service_node_factory)
                or not 0 < reset_timeout_s <= 60
                or not 0 < transition_timeout_s <= 30):
            raise ValueError("TASK8_RESET_AUTHORITY_INVALID")
        self.node, self.model, self.manifest = node, model, manifest
        self.sources, self.broker, self.connection = sources, command_broker, connection
        self.cancelled, self.service_node_factory = cancelled, service_node_factory
        self.reset_timeout_s, self.transition_timeout_s = reset_timeout_s, transition_timeout_s
        self.monotonic, self.clock_ns = monotonic, clock_ns
        self.act_context = None
        self.receipt = None
        self._begun = False

    def _guard(self, request):
        if (request.get("session_id") != self.sources.session_id
                or not isinstance(request.get("attempt_id"), str)
                or not request["attempt_id"]):
            raise ValueError("TASK8_RESET_SCOPE_INVALID")
        if self.cancelled.is_set():
            raise RuntimeError("ACT_TASK8_CANCELLED")
        if type(request.get("deadline_ns")) is not int or self.clock_ns() >= request["deadline_ns"]:
            raise TimeoutError("ACT_DEADLINE_EXPIRED")

    def _wait(self, predicate, request, timeout_s, error):
        deadline = self.monotonic() + timeout_s
        while True:
            self._guard(request)
            if predicate():
                return
            if self.monotonic() >= deadline:
                raise RuntimeError(error)
            time.sleep(0.005)

    def begin(self, request: dict) -> dict:
        self._guard(request)
        if self._begun:
            raise RuntimeError("TASK8_RESET_ALREADY_STARTED")
        targets = pick_place_reset_targets(
            self.model, self.manifest, request,
            expected_model_sha256=self.sources.contact_pairs.model_sha256,
            expected_mujoco_version=mujoco.mj_versionString(),
        )
        self._guard(request)
        self._begun = True
        recovery = self.connection.acquire(
            "recovery", request["session_id"], request["attempt_id"] + "-reset",
        )
        service_node = None
        try:
            self._guard(request)
            service_node = self.service_node_factory()
            services = MujocoRosClient(
                service_node, self.node, service_timeout_s=self.reset_timeout_s,
                control_context=recovery, broker_connection=self.connection,
                operation_guard=lambda: self._guard(request),
            )

            def progress():
                self._guard(request)
                time.sleep(0.005)

            def arm(reset):
                self._guard(request)
                if self.sources.arm("SEARCH") != reset.reset_epoch:
                    raise RuntimeError("TASK8_RESET_ARM_EPOCH_MISMATCH")

            resetter = MujocoResetClient(
                services, self.sources.world, simulation_session_id=request["session_id"],
                controller_names=("arm_controller", "gripper_controller", "neck_controller"),
                expected_joint_positions=targets.joints_rad, expected_joint_names=ACT_JOINTS,
                expected_object_position=targets.cup_start_m,
                timeout_s=self.reset_timeout_s, progress=progress, on_reset_snapshot=arm,
            )
            joint_overrides = tuple(JointResetOverride(name, position) for name, position in
                                    zip(ACT_JOINTS, targets.joints_rad, strict=True))
            cup_override = (FreeJointResetOverride("plastic_cup", targets.cup_start_m),)
            self._guard(request)
            receipt = resetter.reset(
                "task_start", cup_override, joint_overrides=joint_overrides,
            )
            if (self.sources.reset_epoch != receipt.new_epoch
                    or resetter.last_reset_joint_snapshot is None):
                raise RuntimeError("TASK8_RESET_EVIDENCE_MISMATCH")
            self._guard(request)
            if services.pause(False) is not True:
                raise RuntimeError("TASK8_RESUME_REJECTED")

            def running():
                try:
                    frame = self.sources.world.snapshot()
                except Exception:
                    return False
                return (frame.simulation_session_id == request["session_id"]
                        and frame.reset_epoch == receipt.new_epoch
                        and frame.simulation_step > 0 and frame.paused is False)

            self._wait(running, request, self.transition_timeout_s, "TASK8_RUNNING_EPOCH_MISSING")

            def stopped():
                self.broker.driver.refresh_stop()
                return self.broker.driver.stopped()

            self._wait(stopped, request, self.transition_timeout_s, "TASK8_RESET_STOP_MISSING")
            self._guard(request)
            self.connection.request("release", recovery)
            self._guard(request)
            self.act_context = self.connection.acquire(
                "act", request["session_id"], request["attempt_id"],
            )
            self.receipt = receipt
            return {
                "session_id": request["session_id"], "attempt_id": request["attempt_id"],
                "reset_epoch": receipt.new_epoch, "release_epoch": 0,
                "full_restart": False,
            }
        except BaseException as error:
            self.broker.ownership.revoke("TASK8_RESET_ABORT")
            stop_deadline = self.monotonic() + self.transition_timeout_s
            while True:
                self.broker.tick()
                if self.broker.ownership.state == "IDLE" and self.broker.driver.stopped():
                    break
                if self.monotonic() >= stop_deadline:
                    raise RuntimeError("TASK8_RESET_STOP_NOT_CONFIRMED") from error
                time.sleep(0.005)
            raise
        finally:
            if service_node is not None:
                service_node.destroy_node()


# Legacy Python API for version-one pick-place callers.
Task8ResetTargets = PickPlaceResetTargets
Task8ResetBoundary = PickPlaceResetBoundary
task8_reset_targets = pick_place_reset_targets
