"""One isolated diagnostic reset through the existing ACT broker."""

import dataclasses
import json
import os
import time
import traceback
from pathlib import Path

import rclpy

from stop_proof import require_stop_proof, stable_stop
from so101_demo.act.contact_diagnostic import require_contact_diagnostic_sources
from so101_demo.act.joints import ACT_JOINTS
from so101_demo.adapters.act.leased_action_client import BrokerConnection
from so101_demo.backends.mujoco.client import (
    FreeJointResetOverride, JointResetOverride, MujocoRosClient,
)
from so101_demo.backends.mujoco.observer import MujocoWorldObserver
from so101_demo.backends.mujoco.reset import MujocoResetClient


ROOT = Path(__file__).resolve().parent
manifest = require_contact_diagnostic_sources(json.loads((ROOT / "contact-manifest.json").read_text()))
session = manifest["session_id"]
connection = BrokerConnection(str(ROOT / "ipc/a"), timeout_s=30.)
status_context = {"owner": "recovery", "session_id": session, "attempt_id": "live-reset-preflight"}
result = {"source_commit": os.environ["SO101_ACT_SOURCE_COMMIT"], "session_id": session,
          "ros_domain_id": int(os.environ["ROS_DOMAIN_ID"]),
          "gz_partition": os.environ.get("GZ_PARTITION", "NOT_ASSIGNED"),
          "manifest_sha256": manifest["manifest_sha256"], "status": []}
control = None


def save():
    path = ROOT / "reset-result.json"
    with path.open("w", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


try:
    assert stable_stop(connection, status_context, result["status"], expected="IDLE"), \
        "INITIAL_STOP_PROOF_MISSING"
    for index in range(5):
        try:
            control = connection.acquire("recovery", session, f"live-reset-retry1-{index}")
            break
        except PermissionError as error:
            if str(error) != "CONTROL_NOT_STOPPED":
                raise
            result.setdefault("acquire_refusals", []).append(str(error))
            deadline = time.monotonic() + 3.
            while time.monotonic() < deadline:
                state = connection.request("status", status_context)
                result["status"].append(state)
                if state["state"] == "IDLE" and state["stop_confirmed"] and state["hazard_reason"] is None:
                    break
                time.sleep(.05)
            else:
                raise RuntimeError("BROKER_STOP_BARRIER_MISSING")
    assert control is not None, "BOUNDED_ACQUIRE_EXHAUSTED"
    context_file = ROOT / "reset-control-context.json"
    with context_file.open("x", encoding="utf-8") as stream:
        json.dump(control, stream, sort_keys=True)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(context_file, 0o600)
    os.environ["SO101_ACT_PROFILE"] = "1"
    os.environ["SO101_ACT_CONTROL_CONTEXT"] = str(context_file)
    rclpy.init()
    service_node = rclpy.create_node("act_live_reset_services")
    joint_node = rclpy.create_node("act_live_reset_joints")
    observer_node = rclpy.create_node("act_live_reset_evidence")
    services = MujocoRosClient(service_node, joint_node, service_timeout_s=20.)
    observer = MujocoWorldObserver(observer_node, session, max_age_s=1.5)

    def progress():
        rclpy.spin_once(observer_node, timeout_sec=.002)
        services.progress()

    targets = tuple(manifest["joint_start_rad"]) + (manifest["neck_start_rad"],)
    resetter = MujocoResetClient(
        services, observer, simulation_session_id=session,
        controller_names=("arm_controller", "gripper_controller", "neck_controller"),
        expected_joint_positions=targets, expected_joint_names=ACT_JOINTS,
        expected_object_position=tuple(manifest["cup_start_m"]),
        timeout_s=30., progress=progress,
    )
    joint_overrides = tuple(
        JointResetOverride(name, value, 0.) for name, value in zip(ACT_JOINTS, targets, strict=True)
    )
    free_overrides = (FreeJointResetOverride("plastic_cup", tuple(manifest["cup_start_m"])),)
    receipt = resetter.reset("task_start", free_overrides, joint_overrides=joint_overrides)
    result["receipt"] = dataclasses.asdict(receipt)
    result["scalar"] = resetter.last_reset_joint_snapshot
    require_stop_proof(connection, control, result["status"])
    result["release"] = connection.request("release", control)
    control = None
    result["success"] = True
except BaseException as error:
    result["success"] = False
    result["error"] = repr(error)
    result["traceback"] = traceback.format_exc()
    if control is not None:
        try:
            result["revoke"] = connection.request("revoke", control)
        except Exception as stop_error:
            result["revoke_error"] = repr(stop_error)
finally:
    save()
    if rclpy.ok():
        rclpy.shutdown()
    connection.close()
if not result["success"]:
    raise SystemExit(1)
