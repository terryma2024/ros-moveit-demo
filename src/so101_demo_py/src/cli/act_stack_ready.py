"""Observe one fresh ACT stack without issuing a robot command or reset."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
from collections import deque
from dataclasses import dataclass

from so101_demo.act.rig_profile import DEFAULT_RIG

# One ListControllers call that has not answered after this long is abandoned and resent.
CONTROLLER_QUERY_TIMEOUT_S = 2.0
def controllers_for(rig) -> tuple:
    """The controllers that must be active: the neck controller only for a rig that has a neck."""
    return ("joint_state_broadcaster", "arm_controller", "gripper_controller",
            *(("neck_controller",) if rig.has_neck else ()))


def actions_for(rig) -> tuple:
    return ("/execute_trajectory", "/arm_controller/follow_joint_trajectory",
            "/gripper_controller/follow_joint_trajectory",
            *(("/neck_controller/follow_joint_trajectory",) if rig.has_neck else ()))


def check_order_for(rig) -> tuple:
    """(check name, failure code) in order: the world, physics, controllers, graph and stop, then one RGB check per camera."""
    return (("mujoco_session", "ACT_STACK_WORLD_SESSION_INVALID"),
            ("advancing_physics", "ACT_STACK_PHYSICS_NOT_ADVANCING"),
            ("controller_states", "ACT_STACK_CONTROLLER_NOT_ACTIVE"),
            ("moveit_graph", "ACT_STACK_GRAPH_INCOMPLETE"),
            ("physical_stop", "ACT_STACK_NOT_PHYSICALLY_STOPPED"),
            *((f"{camera}_rgb", f"ACT_STACK_{camera.upper()}_RGB_STALE") for camera in rig.camera_names))


_CONTROLLERS = controllers_for(DEFAULT_RIG)
_SERVICES = (
    "/apply_planning_scene", "/get_planning_scene", "/plan_kinematic_path",
)
_ACTIONS = actions_for(DEFAULT_RIG)
_CHECK_ORDER = check_order_for(DEFAULT_RIG)


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
                                 stop_velocity_rad_s: float = 0.01, rig=DEFAULT_RIG) -> ActStackReadiness:
    """Require all startup axes (the seven of rig v1: five stack axes and one RGB axis per camera) from fresh observed sources at one instant."""
    controllers_required, actions_required = controllers_for(rig), actions_for(rig)
    joint_width = 7 if rig.has_neck else 6
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
    controls = all(controllers.get(name) == "active" for name in controllers_required)
    graph = (all(services.get(name) is True for name in _SERVICES)
             and all(actions.get(name) is True for name in actions_required))
    try:
        samples = joints[-8:]
        stop = (len(samples) >= 3
                and 0 <= now_s - samples[-1]["received_s"] <= 0.5
                and samples[-1]["received_s"] > samples[0]["received_s"]
                and samples[-1]["received_s"] - samples[0]["received_s"] >= 0.04
                and all(_finite(sample["stamp_s"]) and _finite(sample["received_s"])
                        and 0 <= now_s - sample["received_s"] <= 0.5
                        and (not physics or abs(sample["stamp_s"] - pair[-1]["sim_time_s"]) <= 0.25)
                        and isinstance(sample["velocity"], (tuple, list))
                        and len(sample["velocity"]) == joint_width
                        and all(_finite(speed) and abs(speed) <= stop_velocity_rad_s
                                for speed in sample["velocity"]) for sample in samples)
                and all(later["stamp_s"] > earlier["stamp_s"]
                        for earlier, later in zip(samples, samples[1:], strict=False)))
        joint_stale = (len(samples) < 3 or not _finite(samples[-1]["received_s"])
                       or not 0 <= now_s - samples[-1]["received_s"] <= 0.5)
    except (KeyError, TypeError, ValueError):
        stop, joint_stale = False, True
    world_time = pair[-1]["sim_time_s"] if physics else float("nan")
    camera_state = {camera: _camera_ok(rgb.get(camera), world_time=world_time, now_s=now_s) for camera in rig.camera_names}
    checks = {
        "mujoco_session": bool(world_scope), "advancing_physics": bool(physics),
        "controller_states": controls, "moveit_graph": graph,
        "physical_stop": bool(stop),
        **{f"{camera}_rgb": shape and fresh for camera, (shape, fresh) in camera_state.items()},
    }
    failure = next((code for name, code in check_order_for(rig) if not checks[name]), None)
    if failure == "ACT_STACK_NOT_PHYSICALLY_STOPPED" and joint_stale:
        failure = "ACT_STACK_JOINTS_STALE"
    for camera, (shape, _fresh) in camera_state.items():
        if failure == f"ACT_STACK_{camera.upper()}_RGB_STALE" and not shape:
            failure = f"ACT_STACK_{camera.upper()}_RGB_INVALID"
    if failure is not None:
        return ActStackReadiness(False, failure, None, checks)
    artifact = {
        "schema_version": 1, "session_id": session_id, "ros_domain_id": ros_domain_id,
        "captured_monotonic_ns": int(round(now_s * 1e9)), "checks": checks,
    }
    return ActStackReadiness(True, None, artifact, checks)


class _PendingQuery:
    """One in-flight service call and when it was sent; the caller treats it as an opaque handle."""

    __slots__ = ("future", "sent_s")

    def __init__(self, future, sent_s: float) -> None:
        self.future, self.sent_s = future, sent_s


def _abandon(client, future) -> None:
    """Drop a call whose response never came, so a late reply cannot be matched to it. Never raises."""
    for action in (lambda: client.remove_pending_request(future), future.cancel):
        try:
            action()
        except Exception:   # noqa: BLE001 - best effort: the abandoned future is no longer read either way
            pass


def advance_controller_query(client, pending, controllers, *, now_s: float,
                             next_query_s: float, request_factory, required=_CONTROLLERS):
    """Keep one service future alive, then stop querying after all four are active.

    A response can be lost (the controller manager logs "failed to send response ... (timeout)"), and an rclpy future for a
    lost response stays pending forever. A call pending longer than `CONTROLLER_QUERY_TIMEOUT_S` is abandoned and sent again;
    the probe's overall timeout is unchanged.
    """
    if not client.service_is_ready():
        return pending, controllers, next_query_s
    if pending is not None:
        if pending.future.done():
            response = pending.future.result()
            if response is not None:
                controllers = {item.name: item.state for item in response.controller}
            pending = None
            return pending, controllers, next_query_s
        if now_s - pending.sent_s < CONTROLLER_QUERY_TIMEOUT_S:
            return pending, controllers, next_query_s
        _abandon(client, pending.future)
        pending = None
        next_query_s = min(next_query_s, now_s)
    if (not all(controllers.get(name) == "active" for name in required)
            and now_s >= next_query_s):
        pending = _PendingQuery(client.call_async(request_factory()), now_s)
        next_query_s = now_s + 0.5
    return pending, controllers, next_query_s


@dataclass(frozen=True, slots=True)
class ReadinessCheck:
    """One check's outcome: `report` is the failure document `main` prints on stderr, None when ready."""

    ready: bool
    artifact: dict | None
    report: dict | None


class StackReadinessSession:
    """The observation `main` makes, over a context, node, service and action clients that can outlive one check.

    A check creates its own world observer and its own joint and camera subscriptions and destroys them again, so every
    sample it judges was received after the check began and its state is that of a new process; only what costs a process start,
    a context and the graph discovery of the clients is kept. `main` is one check of a new session, so the command line and
    a kept session judge by the same code."""

    def __init__(self, *, session_id: str, ros_domain_id: int, rig=DEFAULT_RIG, stop_velocity_rad_s: float = 0.01) -> None:
        from so101_demo.backends.mujoco.teleop_runtime import _RosScope

        self.session_id, self.ros_domain_id = session_id, ros_domain_id
        self.rig, self.stop_velocity_rad_s = rig, stop_velocity_rad_s
        self._clients = None
        self._scope = _RosScope()
        try:
            self._node = self._scope.create_node(f"act_stack_ready_{os.getpid()}")
        except BaseException:
            self._scope.abandon()
            raise

    def close(self) -> None:
        """Release the node and the context. Never raises: it runs while a failure of the check is still propagating."""
        node, self._node = self._node, None
        clients, self._clients = self._clients, None
        # `Node.destroy_node` does not destroy an `ActionClient`, and the node handle is not released while one is alive: the
        # node would stay in the ROS graph for as long as the process lives (EXP-655, `/act_stack_ready_<pid>` at the gate).
        action_clients = () if clients is None else tuple(clients[2].values())
        releases = [(lambda client=client: client.destroy()) for client in action_clients]
        releases += [lambda: node is not None and node.destroy_node(), self._scope.close]
        for release in releases:
            try:
                release()
            except Exception:   # noqa: BLE001
                pass

    def _ensure_clients(self):
        if self._clients is None:
            from control_msgs.action import FollowJointTrajectory
            from controller_manager_msgs.srv import ListControllers
            from moveit_msgs.action import ExecuteTrajectory
            from moveit_msgs.srv import ApplyPlanningScene, GetMotionPlan, GetPlanningScene
            from rclpy.action import ActionClient

            node = self._node
            controller_client = node.create_client(ListControllers, "/controller_manager/list_controllers")
            service_types = (ApplyPlanningScene, GetPlanningScene, GetMotionPlan)
            service_clients = {name: node.create_client(kind, name)
                               for name, kind in zip(_SERVICES, service_types, strict=True)}
            required_actions = actions_for(self.rig)
            action_types = (ExecuteTrajectory, *(FollowJointTrajectory for _ in required_actions[1:]))
            action_clients = {name: ActionClient(node, kind, name)
                              for name, kind in zip(required_actions, action_types, strict=True)}
            self._clients = (controller_client, service_clients, action_clients)
        return self._clients

    def check(self, timeout_s: float) -> ReadinessCheck:
        from controller_manager_msgs.srv import ListControllers
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import Image, JointState
        from so101_demo.act.joints import ACT_JOINTS, ARM_JOINTS, ordered_positions
        from so101_demo.adapters.act.ros_observation import RGB_QOS
        from so101_demo.backends.mujoco.observer import EvidenceStale, MujocoWorldObserver

        rig, node, scope = self.rig, self._node, self._scope
        measured_joints = ACT_JOINTS if rig.has_neck else ARM_JOINTS
        world = MujocoWorldObserver(node, self.session_id, max_age_s=0.25, rebaseline_stale_join=True)
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
                                             measured_joints)
                ordered_positions(dict(zip(message.name, message.position, strict=True)),
                                  measured_joints)
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
        for camera in rig.cameras:
            subscriptions.append(node.create_subscription(
                Image, camera.image_topic,
                lambda msg, stream=camera.name: camera_callback(msg, stream), RGB_QOS,
            ))
        controller_client, service_clients, action_clients = self._ensure_clients()
        controllers: dict[str, str] = {}
        pending = None
        next_controller_query_s = 0.0
        latest = ActStackReadiness(False, "ACT_STACK_WORLD_SESSION_INVALID", None, {})
        deadline = time.monotonic() + timeout_s
        try:
            while scope.ok() and time.monotonic() < deadline:
                scope.spin_once(node, timeout_sec=0.01)
                pending, controllers, next_controller_query_s = advance_controller_query(
                    controller_client, pending, controllers, now_s=time.monotonic(),
                    next_query_s=next_controller_query_s,
                    request_factory=ListControllers.Request, required=controllers_for(rig),
                )
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
                    session_id=self.session_id, ros_domain_id=self.ros_domain_id,
                    now_s=time.monotonic(), worlds=worlds, joints=joints, rgb=rgb,
                    controllers=controllers,
                    services={name: client.service_is_ready()
                              for name, client in service_clients.items()},
                    actions={name: client.server_is_ready()
                             for name, client in action_clients.items()},
                    stop_velocity_rad_s=self.stop_velocity_rad_s, rig=rig,
                )
                if latest.ready and not bad_input and world.rejected_count == 0:
                    return ReadinessCheck(True, latest.artifact, None)
            failure = latest.failure_code
            if bad_input or world.rejected_count:
                failure = "ACT_STACK_SOURCE_REJECTED"
            recent_joints = tuple(joints)[-8:]
            joint_window = {
                "count": len(recent_joints),
                "span_s": (recent_joints[-1]["received_s"] - recent_joints[0]["received_s"]
                           if recent_joints else None),
                "latest_age_s": (time.monotonic() - recent_joints[-1]["received_s"]
                                 if recent_joints else None),
                "max_abs_velocity_rad_s": (
                    max(abs(speed) for sample in recent_joints for speed in sample["velocity"])
                    if recent_joints else None
                ),
            }
            return ReadinessCheck(False, None, {
                "ready": False, "failure_code": failure,
                "checks": latest.checks, "world_rejected": world.rejected_count,
                "world_rejection": world.last_rejection,
                "bad_input": bad_input, "joint_window": joint_window})
        finally:
            # this check's own subscriptions and an unanswered query go; the clients and the node stay for the next check
            for subscription in (*subscriptions, getattr(world, "_subscription", None)):
                if subscription is not None:
                    try:
                        node.destroy_subscription(subscription)
                    except Exception:   # noqa: BLE001 - the node's own destruction follows
                        pass
            if pending is not None:
                _abandon(controller_client, pending.future)


def main(arguments: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="act_stack_ready")
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--ros-domain-id", type=int, required=True)
    parser.add_argument("--timeout-s", type=float, default=60.0)
    parser.add_argument("--stop-velocity-rad-s", type=float, default=0.01)
    parser.add_argument("--rig-profile", default=None,
                        help="rig profile (config/act/rig-v*.yaml); default: rig v1 (head and wrist cameras, neck)")
    options = parser.parse_args(arguments)
    from so101_demo.act.rig_profile import load_rig_profile
    rig = DEFAULT_RIG if options.rig_profile is None else load_rig_profile(options.rig_profile)
    if not 0 < options.timeout_s <= 120:
        parser.error("--timeout-s must be in (0, 120]")
    if os.environ.get("ROS_DOMAIN_ID") != str(options.ros_domain_id):
        parser.error("--ros-domain-id must match ROS_DOMAIN_ID")

    session = StackReadinessSession(session_id=options.session_id, ros_domain_id=options.ros_domain_id, rig=rig,
                                    stop_velocity_rad_s=options.stop_velocity_rad_s)
    try:
        outcome = session.check(options.timeout_s)
    finally:
        session.close()
    if outcome.ready:
        print(json.dumps(outcome.artifact, sort_keys=True), flush=True)
        return 0
    print(json.dumps(outcome.report, sort_keys=True), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

def verify_head_search_startup(*, environment) -> dict | None:
    """Verify the promoted head search pair before the stack is considered ready.

    When the environment names a promoted config, its qualified report must agree with it field by field -
    a drifted value, identity, camera, tracker, motion block or an unconsumed key refuses startup here, before
    any ROS node, camera or model is touched. No named config means this stack carries no head search.
    """

    from so101_demo.act.head_search_binding import load_promoted_head_search

    config_path = environment.get("SO101_HEAD_SEARCH_CONFIG")
    if not config_path:
        return None
    return load_promoted_head_search(config_path, environment.get("SO101_HEAD_SEARCH_REPORT"))
