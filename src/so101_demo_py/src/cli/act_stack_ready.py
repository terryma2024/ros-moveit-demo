"""Observe one fresh ACT stack without issuing a robot command or reset."""

from __future__ import annotations

import argparse
from collections import deque
from dataclasses import dataclass
import json
import math
import os
import sys
import time


_CONTROLLERS = (
    "joint_state_broadcaster", "arm_controller", "gripper_controller", "neck_controller",
)
_SERVICES = (
    "/apply_planning_scene", "/get_planning_scene", "/plan_kinematic_path",
)
_ACTIONS = (
    "/execute_trajectory", "/arm_controller/follow_joint_trajectory",
    "/gripper_controller/follow_joint_trajectory",
    "/neck_controller/follow_joint_trajectory",
)
_CHECK_ORDER = (
    ("mujoco_session", "ACT_STACK_WORLD_SESSION_INVALID"),
    ("advancing_physics", "ACT_STACK_PHYSICS_NOT_ADVANCING"),
    ("controller_states", "ACT_STACK_CONTROLLER_NOT_ACTIVE"),
    ("moveit_graph", "ACT_STACK_GRAPH_INCOMPLETE"),
    ("physical_stop", "ACT_STACK_NOT_PHYSICALLY_STOPPED"),
    ("head_rgb", "ACT_STACK_HEAD_RGB_STALE"),
    ("wrist_rgb", "ACT_STACK_WRIST_RGB_STALE"),
)


@dataclass(frozen=True, slots=True)
class ActStackReadiness:
    ready: bool
    failure_code: str | None
    artifact: dict | None
    checks: dict[str, bool]


def _finite(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def _camera_ok(value, *, world_time: float, now_s: float) -> tuple[bool, bool]:
    if not isinstance(value, dict):
        return False, False
    shape = (value.get("width"), value.get("height"), value.get("encoding"),
             value.get("step"), value.get("byte_count"))
    if shape != (640, 480, "rgb8", 1920, 640 * 480 * 3):
        return False, False
    stamp, receipt = value.get("stamp_s"), value.get("received_s")
    fresh = (_finite(stamp) and _finite(receipt) and stamp > 0
             and 0 <= now_s - receipt <= 1.0
             and abs(stamp - world_time) <= 0.25)
    return True, bool(fresh)


def evaluate_act_stack_readiness(*, session_id: str, ros_domain_id: int, now_s: float,
                                 worlds, joints, rgb, controllers, services, actions,
                                 stop_velocity_rad_s: float = 0.01) -> ActStackReadiness:
    """Require all seven startup axes from fresh observed sources at one instant."""
    if (not isinstance(session_id, str) or not session_id
            or type(ros_domain_id) is not int or not 0 <= ros_domain_id <= 232
            or not _finite(now_s) or now_s <= 0
            or not _finite(stop_velocity_rad_s) or not 0 < stop_velocity_rad_s <= 0.05):
        return ActStackReadiness(False, "ACT_STACK_SCOPE_INVALID", None, {})
    worlds = tuple(worlds) if isinstance(worlds, (tuple, list, deque)) else ()
    joints = tuple(joints) if isinstance(joints, (tuple, list, deque)) else ()
    rgb = rgb if isinstance(rgb, dict) else {}
    controllers = controllers if isinstance(controllers, dict) else {}
    services = services if isinstance(services, dict) else {}
    actions = actions if isinstance(actions, dict) else {}
    try:
        pair = worlds[-2:]
        world_scope = (len(pair) == 2 and all(
            value["session_id"] == session_id and type(value["reset_epoch"]) is int
            and value["reset_epoch"] >= 0 and value["paused"] is False
            and type(value["step"]) is int and value["step"] > 0
            and _finite(value["sim_time_s"]) and _finite(value["received_s"])
            for value in pair))
        physics = (world_scope and pair[0]["reset_epoch"] == pair[1]["reset_epoch"]
                   and pair[1]["step"] > pair[0]["step"]
                   and pair[1]["sim_time_s"] > pair[0]["sim_time_s"]
                   and pair[1]["received_s"] > pair[0]["received_s"]
                   and 0 <= now_s - pair[1]["received_s"] <= 0.25)
    except (KeyError, TypeError, ValueError):
        world_scope = physics = False
    controls = all(controllers.get(name) == "active" for name in _CONTROLLERS)
    graph = (all(services.get(name) is True for name in _SERVICES)
             and all(actions.get(name) is True for name in _ACTIONS))
    try:
        samples = joints[-3:]
        stop = (len(samples) == 3
                and 0 <= now_s - samples[-1]["received_s"] <= 0.5
                and samples[-1]["received_s"] > samples[0]["received_s"]
                and samples[-1]["received_s"] - samples[0]["received_s"] >= 0.04
                and all(_finite(sample["stamp_s"]) and _finite(sample["received_s"])
                        and 0 <= now_s - sample["received_s"] <= 0.5
                        and (not physics or abs(sample["stamp_s"] - pair[-1]["sim_time_s"]) <= 0.25)
                        and isinstance(sample["velocity"], (tuple, list))
                        and len(sample["velocity"]) == 7
                        and all(_finite(speed) and abs(speed) <= stop_velocity_rad_s
                                for speed in sample["velocity"]) for sample in samples)
                and all(later["stamp_s"] > earlier["stamp_s"]
                        for earlier, later in zip(samples, samples[1:], strict=False)))
        joint_stale = (len(samples) < 3 or not _finite(samples[-1]["received_s"])
                       or not 0 <= now_s - samples[-1]["received_s"] <= 0.5)
    except (KeyError, TypeError, ValueError):
        stop, joint_stale = False, True
    world_time = pair[-1]["sim_time_s"] if physics else float("nan")
    head_shape, head_fresh = _camera_ok(rgb.get("head"), world_time=world_time, now_s=now_s)
    wrist_shape, wrist_fresh = _camera_ok(rgb.get("wrist"), world_time=world_time, now_s=now_s)
    checks = {
        "mujoco_session": bool(world_scope), "advancing_physics": bool(physics),
        "controller_states": controls, "moveit_graph": graph,
        "physical_stop": bool(stop), "head_rgb": head_shape and head_fresh,
        "wrist_rgb": wrist_shape and wrist_fresh,
    }
    failure = next((code for name, code in _CHECK_ORDER if not checks[name]), None)
    if failure == "ACT_STACK_NOT_PHYSICALLY_STOPPED" and joint_stale:
        failure = "ACT_STACK_JOINTS_STALE"
    if failure == "ACT_STACK_HEAD_RGB_STALE" and not head_shape:
        failure = "ACT_STACK_HEAD_RGB_INVALID"
    if failure == "ACT_STACK_WRIST_RGB_STALE" and not wrist_shape:
        failure = "ACT_STACK_WRIST_RGB_INVALID"
    if failure is not None:
        return ActStackReadiness(False, failure, None, checks)
    artifact = {
        "schema_version": 1, "session_id": session_id, "ros_domain_id": ros_domain_id,
        "captured_monotonic_ns": int(round(now_s * 1e9)), "checks": checks,
    }
    return ActStackReadiness(True, None, artifact, checks)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="act_stack_ready")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--ros-domain-id", type=int, required=True)
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--stop-velocity-rad-s", type=float, default=0.01)
    options = parser.parse_args(arguments)
    if not 0 < options.timeout_s <= 120:
        parser.error("--timeout-s must be in (0, 120]")
    if os.environ.get("ROS_DOMAIN_ID") != str(options.ros_domain_id):
        parser.error("--ros-domain-id must match ROS_DOMAIN_ID")

    import rclpy
    from control_msgs.action import FollowJointTrajectory
    from controller_manager_msgs.srv import ListControllers
    from moveit_msgs.action import ExecuteTrajectory
    from moveit_msgs.srv import ApplyPlanningScene, GetMotionPlan, GetPlanningScene
    from rclpy.action import ActionClient
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image, JointState
    from so101_demo.act.joints import ACT_JOINTS, ordered_positions
    from so101_demo.adapters.act.ros_observation import RGB_QOS
    from so101_demo.backends.mujoco.observer import MujocoWorldObserver, EvidenceStale

    rclpy.init()
    node = rclpy.create_node(f"act_stack_ready_{os.getpid()}")
    world = MujocoWorldObserver(node, options.session_id, max_age_s=0.25)
    worlds: deque[dict] = deque(maxlen=2)
    joints: deque[dict] = deque(maxlen=8)
    rgb: dict[str, dict] = {}
    bad_input = False

    def joint_callback(message):
        nonlocal bad_input
        try:
            if (len(message.name) != len(message.position)
                    or len(message.name) != len(message.velocity)
                    or len(set(message.name)) != len(message.name)):
                raise ValueError("joint shape")
            stamp = message.header.stamp.sec + message.header.stamp.nanosec * 1e-9
            velocity = ordered_positions(dict(zip(message.name, message.velocity, strict=True)),
                                         ACT_JOINTS)
            ordered_positions(dict(zip(message.name, message.position, strict=True)),
                              ACT_JOINTS)
            joints.append({"stamp_s": stamp, "received_s": time.monotonic(),
                           "velocity": velocity})
        except (TypeError, ValueError):
            bad_input = True

    def camera_callback(message, stream):
        rgb[stream] = {
            "stamp_s": message.header.stamp.sec + message.header.stamp.nanosec * 1e-9,
            "received_s": time.monotonic(), "width": message.width,
            "height": message.height, "encoding": message.encoding,
            "step": message.step, "byte_count": len(message.data),
        }

    subscriptions = [node.create_subscription(
        JointState, "/joint_states", joint_callback, qos_profile_sensor_data,
    )]
    for stream in ("head", "wrist"):
        subscriptions.append(node.create_subscription(
            Image, f"/{stream}_camera/color",
            lambda msg, stream=stream: camera_callback(msg, stream), RGB_QOS,
        ))
    controller_client = node.create_client(ListControllers, "/controller_manager/list_controllers")
    service_types = (ApplyPlanningScene, GetPlanningScene, GetMotionPlan)
    service_clients = {name: node.create_client(kind, name)
                       for name, kind in zip(_SERVICES, service_types, strict=True)}
    action_types = (ExecuteTrajectory, FollowJointTrajectory,
                    FollowJointTrajectory, FollowJointTrajectory)
    action_clients = {name: ActionClient(node, kind, name)
                      for name, kind in zip(_ACTIONS, action_types, strict=True)}
    controllers: dict[str, str] = {}
    pending = None
    next_controller_query_s = 0.0
    latest = ActStackReadiness(False, "ACT_STACK_WORLD_SESSION_INVALID", None, {})
    deadline = time.monotonic() + options.timeout_s
    try:
        while rclpy.ok() and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.01)
            if controller_client.service_is_ready():
                if (pending is None and not all(controllers.get(name) == "active"
                                                for name in _CONTROLLERS)
                        and time.monotonic() >= next_controller_query_s):
                    pending = controller_client.call_async(ListControllers.Request())
                    next_controller_query_s = time.monotonic() + 0.5
                elif pending.done():
                    response = pending.result()
                    if response is not None:
                        controllers = {item.name: item.state for item in response.controller}
                    pending = None
            try:
                current = world.snapshot_with_receipt()
                sample = current.evidence
                if not worlds or sample.simulation_step != worlds[-1]["step"]:
                    worlds.append({
                        "session_id": sample.simulation_session_id,
                        "reset_epoch": sample.reset_epoch, "step": sample.simulation_step,
                        "sim_time_s": sample.simulation_time_s, "paused": sample.paused,
                        "received_s": current.received_monotonic_s,
                    })
            except EvidenceStale:
                pass
            latest = evaluate_act_stack_readiness(
                session_id=options.session_id, ros_domain_id=options.ros_domain_id,
                now_s=time.monotonic(), worlds=worlds, joints=joints, rgb=rgb,
                controllers=controllers,
                services={name: client.service_is_ready()
                          for name, client in service_clients.items()},
                actions={name: client.server_is_ready()
                         for name, client in action_clients.items()},
                stop_velocity_rad_s=options.stop_velocity_rad_s,
            )
            if latest.ready and not bad_input and world.rejected_count == 0:
                print(json.dumps(latest.artifact, sort_keys=True), flush=True)
                return 0
        failure = latest.failure_code
        if bad_input or world.rejected_count:
            failure = "ACT_STACK_SOURCE_REJECTED"
        print(json.dumps({"ready": False, "failure_code": failure,
                          "checks": latest.checks, "world_rejected": world.rejected_count,
                          "world_rejection": world.last_rejection,
                          "bad_input": bad_input}, sort_keys=True), file=sys.stderr)
        return 1
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
