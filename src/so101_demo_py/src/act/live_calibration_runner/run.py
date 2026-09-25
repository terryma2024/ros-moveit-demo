"""One bounded bilateral prefix through the sole paired ACT broker."""

import json
import os
import threading
import time
import traceback
from pathlib import Path

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.qos import qos_profile_sensor_data
from rosgraph_msgs.msg import Clock
from sensor_msgs.msg import JointState

from acquire import acquire_after_stop
from stop_proof import stable_stop
from so101_demo.act.contact_diagnostic import (
    prefix_matches_diagnostic, require_contact_diagnostic_sources,
)
from so101_demo.act.joints import ACT_JOINTS
from so101_demo.adapters.act.leased_action_client import BrokerConnection


ROOT = Path(__file__).resolve().parent
manifest = require_contact_diagnostic_sources(json.loads((ROOT / "contact-manifest.json").read_text()))
session = manifest["session_id"]
connection = BrokerConnection(str(ROOT / "ipc/a"), timeout_s=8.)
status_context = {"owner": "recovery", "session_id": session, "attempt_id": "live-motion-preflight"}
result = {"source_commit": os.environ["SO101_ACT_SOURCE_COMMIT"], "session_id": session,
          "ros_domain_id": int(os.environ["ROS_DOMAIN_ID"]),
          "gz_partition": os.environ.get("GZ_PARTITION", "NOT_ASSIGNED"),
          "manifest_sha256": manifest["manifest_sha256"], "status": [],
          "goal_status": []}
control = None
lock = threading.Lock()
latest = {"joint": None, "clock": None}


def save():
    with (ROOT / "prefix-result.json").open("w", encoding="utf-8") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def stable(context, expected, *, seconds=5.):
    return stable_stop(connection, context, result["status"],
                       expected=expected, seconds=seconds)


def accept_joint(message):
    if (len(message.name) != len(message.position) or
            len(message.name) != len(message.velocity) or
            len(set(message.name)) != len(message.name)):
        return
    positions = dict(zip(message.name, message.position, strict=True))
    velocities = dict(zip(message.name, message.velocity, strict=True))
    if not set(ACT_JOINTS) <= positions.keys():
        return
    row = {"sim_time_s": message.header.stamp.sec + message.header.stamp.nanosec * 1e-9,
           "wall_s": time.monotonic(),
           "positions": [positions[name] for name in ACT_JOINTS],
           "velocities": [velocities[name] for name in ACT_JOINTS]}
    with lock:
        latest["joint"] = row


def accept_clock(message):
    row = {"sim_time_s": message.clock.sec + message.clock.nanosec * 1e-9,
           "wall_s": time.monotonic()}
    with lock:
        latest["clock"] = row


def causal_observation(expected):
    with lock:
        joint = latest["joint"]
        clock = latest["clock"]
    assert joint is not None and clock is not None, "OBSERVATION_OR_CLOCK_MISSING"
    now = time.monotonic()
    assert now - joint["wall_s"] < .05 and now - clock["wall_s"] < .05, "OBSERVATION_WALL_STALE"
    assert -.005 <= clock["sim_time_s"] - joint["sim_time_s"] <= .03, "OBSERVATION_CLOCK_LAG"
    assert all(abs(a - b) <= .002 for a, b in zip(joint["positions"], expected, strict=True)), "RESET_START_DRIFT"
    assert all(abs(v) <= .002 for v in joint["velocities"]), "JOINTS_MOVING_BEFORE_PREFIX"
    return joint, clock


executor = None
node = None
thread = None
try:
    assert (ROOT / "reset-result.json").exists(), "RESET_RESULT_MISSING"
    reset = json.loads((ROOT / "reset-result.json").read_text())
    assert reset["success"] is True and reset["receipt"]["simulation_session_id"] == session
    assert stable(status_context, "IDLE"), "INITIAL_STOP_PROOF_MISSING"
    rclpy.init()
    node = rclpy.create_node("act_live_calibration_observer")
    node.create_subscription(JointState, "/joint_states", accept_joint, qos_profile_sensor_data)
    node.create_subscription(Clock, "/clock", accept_clock, qos_profile_sensor_data)
    executor = SingleThreadedExecutor()
    executor.add_node(node)
    thread = threading.Thread(target=executor.spin, daemon=True)
    thread.start()
    control = acquire_after_stop(
        connection, owner="recovery", session=session, attempt="live-resume",
        status_context=status_context, status_records=result["status"])
    result["resume_request_monotonic_s"] = time.monotonic()
    resume = connection.request("pause", control, paused=False)
    result["resume"] = resume
    assert resume["pause_result"]["success"]
    assert stable(control, "RUNNING"), "RESUME_STOP_PROOF_MISSING"
    result["resume_release"] = connection.request("release", control)
    control = None
    assert stable(status_context, "IDLE"), "POST_RESUME_IDLE_PROOF_MISSING"
    deadline = time.monotonic() + 4.
    while time.monotonic() < deadline:
        with lock:
            ready = latest["joint"] is not None and latest["clock"] is not None
        if ready:
            break
        time.sleep(.005)
    assert ready, "JOINT_OR_CLOCK_STREAM_MISSING"
    control = acquire_after_stop(
        connection, owner="act", session=session, attempt=manifest["attempt_id"],
        status_context=status_context, status_records=result["status"])
    result["segments"] = []
    rows = manifest["target_positions"]
    for sequence, start in enumerate(range(0, len(rows), manifest["segment_rows"])):
        expected = manifest["joint_start_rad"] if start == 0 else rows[start - 1]
        observation, clock = causal_observation(expected + [manifest["neck_start_rad"]])
        positions = [expected] + rows[start:start + manifest["segment_rows"]]
        origin = observation["sim_time_s"]
        prefix = {"session_id": session, "attempt_id": manifest["attempt_id"],
                  "sequence": sequence, "observation_time_s": origin,
                  "target_times_s": [origin + .1 * (index + 1) for index in range(len(positions))],
                  "positions": positions}
        assert prefix_matches_diagnostic(prefix, manifest), "SOURCE_PREFIX_MISMATCH"
        segment = {"sequence": sequence, "prefix": prefix, "observation": observation,
                   "clock": clock, "goal_status": []}
        result["segments"].append(segment)
        began = time.monotonic()
        permit = connection.request("approve_prefix", control, prefix=prefix)
        segment["approve_elapsed_wall_s"] = time.monotonic() - began
        segment["permit"] = permit
        current, current_clock = causal_observation(expected + [manifest["neck_start_rad"]])
        segment["pre_submit"] = {"joint": current, "clock": current_clock}
        assert prefix["target_times_s"][0] - current_clock["sim_time_s"] > .05, "PREFIX_WINDOW_EXPIRED"
        began = time.monotonic()
        submitted = connection.request("submit_prefix", control, prefix=prefix, permit=permit["permit"])
        segment["submit_elapsed_wall_s"] = time.monotonic() - began
        segment["submit"] = submitted
        deadline = time.monotonic() + 4.
        while time.monotonic() < deadline:
            state = connection.request("goal_status", control, goal_id=submitted["goal_id"])
            segment["goal_status"].append(state)
            if state.get("status") in (4, 5, 6):
                break
            time.sleep(.01)
        assert segment["goal_status"][-1]["status"] == 4, "PAIR_NOT_SUCCESSFUL"
        assert segment["goal_status"][-1]["action_accepted"] is True
        assert all(item["result"]["error_code"] == 0 for item in
                   segment["goal_status"][-1]["controllers"]), "CONTROLLER_RESULT_INVALID"
        segment["stop_readbacks"] = []
        deadline = time.monotonic() + 5.
        consecutive = 0
        while time.monotonic() < deadline:
            pair = connection.request("goal_status", control, goal_id=submitted["goal_id"])
            broker = connection.request("status", control)
            segment["stop_readbacks"].append({"pair": pair, "broker": broker})
            assert broker["hazard_reason"] is None, "BROKER_HAZARD"
            assert broker["state"] == "RUNNING", "BROKER_LEFT_ACT_LEASE"
            assert pair["status"] == 4, "PAIR_STOP_STATE_CHANGED"
            consecutive = consecutive + 1 if (pair["segment_stop_confirmed"] is True and
                                               broker["stop_confirmed"] is True) else 0
            if consecutive >= 3:
                break
            time.sleep(.02)
        assert consecutive >= 3, "SEGMENT_STOP_PROOF_MISSING"
    result["success"] = True
except BaseException as error:
    result["success"] = False
    result["error"] = repr(error)
    result["traceback"] = traceback.format_exc()
finally:
    if control is not None:
        try:
            result["act_revoke"] = connection.request("revoke", control)
        except Exception as stop_error:
            result["revoke_error"] = repr(stop_error)
    try:
        result["final_stop"] = stable(status_context, "IDLE")
    except Exception as stop_error:
        result["final_stop_error"] = repr(stop_error)
    save()
    if executor is not None:
        executor.shutdown()
    if thread is not None:
        thread.join(timeout=2.)
    if node is not None:
        node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()
    connection.close()
if not result["success"] or not result.get("final_stop"):
    raise SystemExit(1)
