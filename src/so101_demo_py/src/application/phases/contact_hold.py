#!/usr/bin/env python3
"""production live phase: bounded bilateral preload under the MuJoCo Noslip model."""

from __future__ import annotations

import json
import math
import os
import time
from pathlib import Path

import rclpy
from control_msgs.action import FollowJointTrajectory
from rclpy.action import ActionClient
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import JointState
from so101_demo.application.phases.grasp_strategy import seating_preload_target
from so101_demo.application.pick_place import load_live_task_policy
from so101_demo.application.staged_approach import maximum_joint_error
from so101_demo.backends.mujoco.observer import EvidenceStale, MujocoWorldObserver
from so101_demo.control.gripper.client import GripperClient

SESSION_ID = os.environ["SO101_SIMULATION_SESSION_ID"]
EXPECTED_EPOCH = int(os.environ["SO101_EXPECTED_RESET_EPOCH"])
EVIDENCE_PATH = Path(os.environ["SO101_EVIDENCE_ROOT"]) / "contact-hold.json"
ALL_JOINTS = ("1", "2", "3", "4", "5", "6")
CLOSE_READY_ARM = (
    -0.000206491845,
    0.472194274096,
    0.214652624195,
    0.854922375695,
    0.000576703465,
)
COARSE_START_Q6 = -0.040
NOMINAL_CONTACT_Q6 = -0.047608632840292
SAFE_Q6_LOWER = -0.059600220867817
COARSE_STEP_RAD = 0.0005
CONTACT_STEP_RAD = 0.00002
MAX_CUP_DISPLACEMENT_M = 0.003
STABLE_HOLD_S = 2.0


def atomic_write(document: dict) -> None:
    EVIDENCE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = EVIDENCE_PATH.with_name(f".{EVIDENCE_PATH.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(temporary, EVIDENCE_PATH)


def contact_snapshot(evidence, q6: float) -> dict:
    left = sum(contact.normal_force_n for contact in evidence.left_fingertip_contacts)
    right = sum(contact.normal_force_n for contact in evidence.right_fingertip_contacts)
    return {
        "publisher_sequence": evidence.publisher_sequence,
        "simulation_step": evidence.simulation_step,
        "reset_epoch": evidence.reset_epoch,
        "q6_rad": q6,
        "cup_position_world_m": list(evidence.object_state.position_world),
        "minimum_signed_distance_m": evidence.minimum_signed_distance_m,
        "maximum_normal_force_n": evidence.maximum_normal_force_n,
        "left_contact_count": len(evidence.left_fingertip_contacts),
        "right_contact_count": len(evidence.right_fingertip_contacts),
        "left_normal_force_sum_n": left,
        "right_normal_force_sum_n": right,
        "other_contact_geoms": [contact.geom2 for contact in evidence.other_object_contacts],
    }


def main() -> int:
    task_policy = load_live_task_policy()
    assert task_policy.contact is not None
    contact_thresholds = task_policy.contact.thresholds
    result = {
        "schema": "so101-live-noslip-contact-hold-v1",
        "simulation_session_id": SESSION_ID,
        "reset_epoch": EXPECTED_EPOCH,
        "model_change": "scene noslip_iterations=10",
        "physics_pause_calls": 0,
        "simulator_constraint_calls": 0,
        "direct_object_state_writes": 0,
        "moveit_attach_calls": 0,
        "status": "RUNNING",
        "samples": [],
    }
    rclpy.init()
    node = rclpy.create_node("so101_live_contact_hold")
    latest_joint: dict[str, float] = {}

    def on_joints(message: JointState) -> None:
        if len(message.name) == len(message.position):
            latest_joint.update(zip(message.name, message.position, strict=True))

    subscription = node.create_subscription(
        JointState, "/joint_states", on_joints, qos_profile_sensor_data
    )
    observer = MujocoWorldObserver(node, SESSION_ID, max_age_s=0.5)
    action = ActionClient(
        node, FollowJointTrajectory, "/gripper_controller/follow_joint_trajectory"
    )

    def progress() -> None:
        rclpy.spin_once(node, timeout_sec=0.01)

    def wait_for(predicate, timeout_s: float, message: str):
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            value = predicate()
            if value is not None and value is not False:
                return value
            progress()
        raise RuntimeError(message)

    def snapshot():
        try:
            return observer.snapshot()
        except EvidenceStale:
            return None

    reference_position: tuple[float, float, float] | None = None

    def validate(evidence) -> tuple[float, float]:
        if evidence.paused or evidence.reset_epoch != EXPECTED_EPOCH:
            raise RuntimeError("pause/reset provenance changed during contact calibration")
        if evidence.maximum_normal_force_n > contact_thresholds.maximum_safe_force_n:
            raise RuntimeError(f"force boundary exceeded: {evidence.maximum_normal_force_n:.6f} N")
        if reference_position is None:
            raise RuntimeError("reference cup position unavailable")
        displacement = math.dist(evidence.object_state.position_world, reference_position)
        if displacement > MAX_CUP_DISPLACEMENT_M:
            raise RuntimeError(f"cup displacement exceeded: {displacement:.9f} m")
        left = sum(contact.normal_force_n for contact in evidence.left_fingertip_contacts)
        right = sum(contact.normal_force_n for contact in evidence.right_fingertip_contacts)
        return left, right

    def command_and_sample(gripper: GripperClient, target: float, duration_s: float):
        outcome = gripper.command(target, duration_s, 10.0)
        if outcome.failure is not None:
            raise RuntimeError(f"gripper action failed: {outcome.failure.code}")
        evidence = wait_for(snapshot, 2.0, "fresh contact evidence unavailable")
        q6 = float(latest_joint["6"])
        validate(evidence)
        result["samples"].append(contact_snapshot(evidence, q6))
        atomic_write(result)
        return evidence, q6

    try:
        if not action.wait_for_server(timeout_sec=20.0):
            raise RuntimeError("gripper action unavailable")
        wait_for(lambda: len(latest_joint) == 6, 5.0, "joint state unavailable")
        before = wait_for(snapshot, 5.0, "MuJoCo evidence unavailable")
        if before.paused or before.reset_epoch != EXPECTED_EPOCH:
            raise RuntimeError("unexpected initial MuJoCo provenance")
        start = tuple(float(latest_joint[name]) for name in ALL_JOINTS)
        if maximum_joint_error(start[:5], CLOSE_READY_ARM) > 0.01:
            raise RuntimeError("robot is not at verified Close-ready arm state")
        if abs(start[-1] - 0.465038) > 0.01:
            raise RuntimeError("gripper is not preopened")
        reference_position = tuple(before.object_state.position_world)
        result["before_joints_rad"] = list(start)
        result["before_evidence"] = contact_snapshot(before, start[-1])
        atomic_write(result)

        gripper = GripperClient(action, progress=progress)
        evidence, q6 = command_and_sample(gripper, COARSE_START_Q6, 1.5)

        target = COARSE_START_Q6
        bilateral = False
        while target > NOMINAL_CONTACT_Q6:
            target = max(NOMINAL_CONTACT_Q6, target - COARSE_STEP_RAD)
            evidence, q6 = command_and_sample(gripper, target, 0.15)
            if evidence.left_fingertip_contacts and evidence.right_fingertip_contacts:
                bilateral = True
                break

        while True:
            left, right = validate(evidence)
            if bilateral and min(left, right) >= contact_thresholds.minimum_bilateral_force_n:
                break
            if q6 <= SAFE_Q6_LOWER + CONTACT_STEP_RAD:
                raise RuntimeError("safe q6 lower bound reached without sufficient bilateral force")
            target = max(SAFE_Q6_LOWER, target - CONTACT_STEP_RAD)
            evidence, q6 = command_and_sample(gripper, target, 0.10)
            bilateral = bool(evidence.left_fingertip_contacts and evidence.right_fingertip_contacts)

        contact_detection_q6 = q6
        hold_target = seating_preload_target(contact_detection_q6)
        evidence, q6 = command_and_sample(gripper, hold_target, 0.20)
        left, right = validate(evidence)
        if not evidence.left_fingertip_contacts or not evidence.right_fingertip_contacts:
            raise RuntimeError("bilateral contact lost while applying seating preload")
        if min(left, right) < contact_thresholds.minimum_bilateral_force_n:
            raise RuntimeError("seating preload did not retain qualified bilateral contact")
        result["contact_detection_q6_rad"] = contact_detection_q6
        result["seating_preload_target_q6_rad"] = hold_target
        atomic_write(result)
        hold_samples: list[dict] = []
        deadline = time.monotonic() + STABLE_HOLD_S
        last_sequence = -1
        while time.monotonic() < deadline:
            progress()
            evidence = snapshot()
            if evidence is None or evidence.publisher_sequence == last_sequence:
                continue
            last_sequence = evidence.publisher_sequence
            left, right = validate(evidence)
            if not evidence.left_fingertip_contacts or not evidence.right_fingertip_contacts:
                raise RuntimeError("bilateral contact lost during contact-only hold")
            if min(left, right) < contact_thresholds.minimum_bilateral_force_n:
                raise RuntimeError("bilateral normal force fell below carry threshold")
            hold_samples.append(contact_snapshot(evidence, float(latest_joint["6"])))

        result.update(
            {
                "status": "CONTACT_ONLY_PROVED",
                "terminal_q6_rad": float(latest_joint["6"]),
                "hold_duration_s": STABLE_HOLD_S,
                "hold_sample_count": len(hold_samples),
                "hold_samples": hold_samples,
            }
        )
        atomic_write(result)
        print(
            f"EXP101_OK q6={result['terminal_q6_rad']:.9f} samples={len(hold_samples)}",
            flush=True,
        )
        return 0
    except Exception as error:
        result["status"] = "FAILED"
        result["error"] = f"{type(error).__name__}: {error}"
        atomic_write(result)
        print(f"EXP101_FAILED {type(error).__name__}: {error}", flush=True)
        return 1
    finally:
        del subscription
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
