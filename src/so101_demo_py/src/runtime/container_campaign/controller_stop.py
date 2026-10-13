"""ACT's four action lanes: original cancellation ACKs and subsequent statuses."""

from dataclasses import dataclass
import json
import math
import numbers
import re
import time

from so101_demo.runtime.parallel_ipc.frames import _decode_payload, canonical_json


_LANES = dict(arm="/arm_controller/follow_joint_trajectory/_action",
              gripper="/gripper_controller/follow_joint_trajectory/_action",
              neck="/neck_controller/follow_joint_trajectory/_action",
              moveit="/execute_trajectory/_action")


def _ros_types():
    from action_msgs.msg import GoalStatusArray
    from action_msgs.srv import CancelGoal
    from rclpy.qos import qos_profile_action_status_default
    return GoalStatusArray, CancelGoal, qos_profile_action_status_default


def _open_owner(namespace):
    import rclpy
    from so101_demo.runtime.parallel_ros_ports.isolated_node import _open_isolated_ros_node
    return _open_isolated_ros_node(rclpy, "act_shard_goal_stop", namespace=namespace)


def _byte(value):
    """One uuid element. rclpy hands `uuid` over as a numpy.uint8 array, so the element is an integer by value, not by type."""
    if isinstance(value, bool) or not isinstance(value, numbers.Integral) or not 0 <= value <= 255:
        raise ValueError("ACT_CONTROLLER_STOP_MESSAGE_INVALID")
    return int(value)


def _goal(goal):
    if type(goal.stamp.sec) is not int or type(goal.stamp.nanosec) is not int:
        raise ValueError("ACT_CONTROLLER_STOP_MESSAGE_INVALID")
    uuid = bytes(_byte(value) for value in goal.goal_id.uuid)
    if len(uuid) != 16:
        raise ValueError("ACT_CONTROLLER_STOP_MESSAGE_INVALID")
    return dict(uuid=uuid.hex(), stamp=dict(sec=goal.stamp.sec, nanosec=goal.stamp.nanosec))


def _require(condition):
    if not condition:
        raise ValueError("ACT_CONTROLLER_STOP_OBSERVATION_INVALID")


def _validate_goal(goal):
    _require(type(goal) is dict and set(goal) == {"uuid", "stamp"})
    _require(type(goal["uuid"]) is str and re.fullmatch(r"[0-9a-f]{32}", goal["uuid"]) is not None)
    stamp = goal["stamp"]
    _require(type(stamp) is dict and set(stamp) == {"sec", "nanosec"}
        and type(stamp["sec"]) is int and stamp["sec"] >= 0
        and type(stamp["nanosec"]) is int and 0 <= stamp["nanosec"] < 1_000_000_000)


@dataclass(frozen=True, slots=True)
class ControllerStopObservation:
    payload: bytes

    def __post_init__(self):
        try:
            _require(type(self.payload) is bytes and 0 < len(self.payload) <= 1024*1024)
            value = _decode_payload(self.payload)
            _require(set(value) == {"schema_version", "kind", "ros_namespace", "started_monotonic_ns", "completed_monotonic_ns", "lanes"})
            _require(type(value["schema_version"]) is int and value["schema_version"] == 1
                     and value["kind"] == "ACT_CONTROLLER_STOP_OBSERVATION")
            namespace = value["ros_namespace"]
            _require(type(namespace) is str and re.fullmatch(r"(?:/[a-zA-Z_][a-zA-Z0-9_]*)+", namespace) is not None)
            start, end = value["started_monotonic_ns"], value["completed_monotonic_ns"]
            _require(type(start) is int and type(end) is int and 0 < start <= end)
            _require(type(value["lanes"]) is dict and set(value["lanes"]) == set(_LANES))
            fields = {"action_prefix", "cancel_sent_monotonic_ns", "cancel_received_monotonic_ns",
                      "cancel_return_code", "goals_canceling", "status_received_monotonic_ns", "statuses"}
            for name, lane in value["lanes"].items():
                _require(type(lane) is dict and set(lane) == fields and lane["action_prefix"] == namespace+_LANES[name])
                for field in ("cancel_sent_monotonic_ns", "cancel_received_monotonic_ns", "status_received_monotonic_ns"):
                    _require(lane[field] is None or type(lane[field]) is int and start <= lane[field] <= end)
                code = lane["cancel_return_code"]
                _require(code is None or type(code) is int and 0 <= code <= 3)
                _require((lane["cancel_received_monotonic_ns"] is None) == (code is None)
                         == (lane["goals_canceling"] is None))
                if code is not None:
                    _require(lane["cancel_sent_monotonic_ns"] is not None
                             and lane["cancel_received_monotonic_ns"] >= lane["cancel_sent_monotonic_ns"])
                    _require(type(lane["goals_canceling"]) is list)
                    for goal in lane["goals_canceling"]:
                        _validate_goal(goal)
                _require((lane["statuses"] is None) == (lane["status_received_monotonic_ns"] is None))
                if lane["statuses"] is not None:
                    _require(type(lane["statuses"]) is list)
                    ids = set()
                    for item in lane["statuses"]:
                        _require(type(item) is dict and set(item) == {"status", "goal"}
                                 and type(item["status"]) is int and 0 <= item["status"] <= 6)
                        _validate_goal(item["goal"])
                        _require(item["goal"]["uuid"] not in ids)
                        ids.add(item["goal"]["uuid"])
        except (ValueError, RuntimeError, TypeError, KeyError) as error:
            raise ValueError("ACT_CONTROLLER_STOP_OBSERVATION_INVALID") from error

    @property
    def document(self):
        return json.loads(self.payload)

    @property
    def proven(self):
        document = self.document
        for lane in document["lanes"].values():
            if (lane["cancel_return_code"] != 0 or lane["cancel_received_monotonic_ns"] is None
                    or lane["statuses"] is None or lane["status_received_monotonic_ns"] is None
                    or lane["status_received_monotonic_ns"] < lane["cancel_received_monotonic_ns"]
                    or any(status["status"] not in (4, 5, 6) for status in lane["statuses"])):
                return False
            known = {status["goal"]["uuid"] for status in lane["statuses"]}
            if any(goal["uuid"] not in known for goal in lane["goals_canceling"]):
                return False
        return True

    @property
    def empty_cancel_acknowledged(self):
        """Original empty ACKs; never standalone physical or goal-stop proof."""
        for lane in self.document['lanes'].values():
            if (lane['cancel_return_code'] != 0 or lane['cancel_received_monotonic_ns'] is None
                    or lane['goals_canceling'] != []
                    or lane['statuses'] is not None and any(item['status'] not in (4,5,6)
                                                            for item in lane['statuses'])):
                return False
        return True


def observe_act_controller_stop(*, ros_namespace, timeout_s, monotonic_ns=time.monotonic_ns,
                                return_on_empty_ack=False):
    if (type(ros_namespace) is not str
            or re.fullmatch(r"(?:/[a-zA-Z_][a-zA-Z0-9_]*)+", ros_namespace) is None
            or type(timeout_s) not in (int, float) or not math.isfinite(timeout_s)
            or timeout_s <= 0 or int(timeout_s*1e9) <= 0 or type(return_on_empty_ack) is not bool):
        raise ValueError("ACT_CONTROLLER_STOP_CONFIG_INVALID")
    last = monotonic_ns()
    if type(last) is not int or last <= 0:
        raise ValueError("ACT_CONTROLLER_STOP_CLOCK_INVALID")
    def clock():
        nonlocal last
        now = monotonic_ns()
        if type(now) is not int or now < last:
            raise ValueError("ACT_CONTROLLER_STOP_CLOCK_INVALID")
        last = now
        return now
    started = last
    deadline = started+int(timeout_s*1e9)
    message_type, cancel_type, qos = _ros_types()
    owner = _open_owner(ros_namespace)
    lanes = {name: dict(action_prefix=ros_namespace+prefix, cancel_sent_monotonic_ns=None,
        cancel_received_monotonic_ns=None, cancel_return_code=None, goals_canceling=None,
        status_received_monotonic_ns=None, statuses=None) for name,prefix in _LANES.items()}
    subscriptions, clients, futures = [], {}, {}
    try:
        for name, lane in lanes.items():
            def callback(message, name=name):
                lanes[name]["statuses"] = [dict(status=value.status, goal=_goal(value.goal_info))
                                           for value in message.status_list]
                lanes[name]["status_received_monotonic_ns"] = clock()
            subscriptions.append(owner.node.create_subscription(message_type, lane["action_prefix"]+"/status", callback, qos))
            clients[name] = owner.node.create_client(cancel_type, lane["action_prefix"]+"/cancel_goal")
        for name, client in clients.items():
            remaining = (deadline-clock())/1e9
            if remaining <= 0 or not client.wait_for_service(timeout_sec=remaining):
                break
            lanes[name]["cancel_sent_monotonic_ns"] = clock()
            futures[name] = client.call_async(cancel_type.Request())
        while clock() < deadline:
            for name, future in futures.items():
                lane = lanes[name]
                if lane["cancel_received_monotonic_ns"] is None and future.done():
                    response = future.result()
                    if response is not None:
                        lane["cancel_return_code"] = response.return_code
                        lane["goals_canceling"] = [_goal(goal) for goal in response.goals_canceling]
                        lane["cancel_received_monotonic_ns"] = clock()
            document = dict(schema_version=1, kind="ACT_CONTROLLER_STOP_OBSERVATION",
                ros_namespace=ros_namespace, started_monotonic_ns=started,
                completed_monotonic_ns=clock(), lanes=lanes)
            observation = ControllerStopObservation(canonical_json(document))
            if observation.proven or return_on_empty_ack and observation.empty_cancel_acknowledged:
                return observation
            owner.spin_once(timeout_sec=min(0.01,max(0,(deadline-clock())/1e9)))
        return ControllerStopObservation(canonical_json(dict(schema_version=1,
            kind="ACT_CONTROLLER_STOP_OBSERVATION", ros_namespace=ros_namespace,
            started_monotonic_ns=started, completed_monotonic_ns=clock(), lanes=lanes)))
    finally:
        del subscriptions
        owner.close()
