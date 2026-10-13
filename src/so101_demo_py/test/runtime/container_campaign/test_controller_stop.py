"""All four ACT action lanes need actual cancellation ACK and settled status."""

import importlib
import copy
from types import SimpleNamespace

import pytest


def run_probe(monkeypatch, *, missing=None, active=None, bad_ack=None,idle=False,return_on_empty_ack=False,real_messages=False):
    mod = importlib.import_module("so101_demo.runtime.container_campaign.controller_stop")
    clock = [1_000_000_000]
    endpoints = []
    closed = []
    class Future:
        def done(self): return True
        def result(self):
            if real_messages:
                from action_msgs.msg import GoalInfo
                from action_msgs.srv import CancelGoal
                info = GoalInfo(); info.goal_id.uuid = list(range(16)); info.stamp.sec = 1
                response = CancelGoal.Response(); response.return_code = bad_ack or 0; response.goals_canceling = [info]
                return response
            return SimpleNamespace(return_code=bad_ack or 0, goals_canceling=[])
    class Node:
        def __init__(self): self.callbacks = {}
        def create_subscription(self, _type, topic, callback, _qos):
            self.callbacks[topic] = callback
            endpoints.append(topic)
            return object()
        def create_client(self, _type, topic):
            endpoints.append(topic)
            return SimpleNamespace(wait_for_service=lambda **kwargs: True,
                                   call_async=lambda request: Future())
    class Owner:
        def __init__(self): self.node = Node()
        def spin_once(self, **kwargs):
            clock[0] += 10_000_000
            for topic, callback in self.node.callbacks.items():
                if idle: continue
                if missing and missing in topic: continue
                status = 2 if active and active in topic else 4
                if real_messages:
                    from action_msgs.msg import GoalInfo, GoalStatus, GoalStatusArray
                    entry = GoalStatus(); entry.status = status
                    entry.goal_info = GoalInfo(); entry.goal_info.goal_id.uuid = list(range(16)); entry.goal_info.stamp.sec = 1
                    callback(GoalStatusArray(status_list=[entry]))
                    continue
                callback(SimpleNamespace(status_list=[SimpleNamespace(status=status,
                    goal_info=SimpleNamespace(goal_id=SimpleNamespace(uuid=list(range(16))),
                                              stamp=SimpleNamespace(sec=1,nanosec=2)))]))
        def close(self): closed.append(True)
    monkeypatch.setattr(mod, "_open_owner", lambda: Owner())
    monkeypatch.setattr(mod, "_ros_types", lambda: (object, SimpleNamespace(Request=lambda: object()), object()))
    result = mod.observe_act_controller_stop(timeout_s=0.1,
                                            monotonic_ns=lambda: clock[0],return_on_empty_ack=return_on_empty_ack)
    assert closed == [True]
    return mod, result, endpoints


def test_neck_moveit_arm_and_gripper_all_have_original_status_and_ack(monkeypatch):
    mod, observation, endpoints = run_probe(monkeypatch)
    assert observation.proven
    assert len(endpoints) == 8
    assert all(name.startswith("/") and "/act/" not in name for name in endpoints)   # the fixed, un-namespaced lanes
    assert {name.rsplit("/_action/", 1)[0] for name in endpoints} == {
        "/arm_controller/follow_joint_trajectory", "/gripper_controller/follow_joint_trajectory",
        "/neck_controller/follow_joint_trajectory", "/execute_trajectory"}
    assert observation.document["schema_version"] == 2 and "ros_namespace" not in observation.document
    assert any("/neck_controller/" in name for name in endpoints)
    assert set(observation.document["lanes"]) == {"arm", "gripper", "neck", "moveit"}
    assert all(lane["cancel_return_code"] == 0 and lane["statuses"][0]["status"] == 4
               and lane["status_received_monotonic_ns"] >= lane["cancel_sent_monotonic_ns"]
               for lane in observation.document["lanes"].values())


@pytest.mark.parametrize("lane", ["arm", "gripper", "neck", "moveit"])
def test_missing_or_active_lane_does_not_prove_stop(monkeypatch, lane):
    search = "execute_trajectory" if lane == "moveit" else lane+"_controller"
    _, missing, _ = run_probe(monkeypatch, missing=search)
    assert not missing.proven
    _, active, _ = run_probe(monkeypatch, active=search)
    assert not active.proven


def test_cancel_rejection_does_not_become_empty_goal_success(monkeypatch):
    _, observation, _ = run_probe(monkeypatch, bad_ack=1)
    assert not observation.proven


def test_idle_ack_can_return_for_retirement_but_never_claims_standalone_stop(monkeypatch):
    _,observation,_ = run_probe(monkeypatch,idle=True,return_on_empty_ack=True)
    assert observation.empty_cancel_acknowledged is True
    assert observation.proven is False
    assert all(lane['statuses'] is None for lane in observation.document['lanes'].values())
    _,rejected,_ = run_probe(monkeypatch,idle=True,bad_ack=1,return_on_empty_ack=True)
    assert rejected.empty_cancel_acknowledged is False and rejected.proven is False


@pytest.mark.parametrize("budget", [True, 0, -1, float("inf"), float("nan")])
def test_invalid_budget_refused_before_any_ros_context(budget, monkeypatch):
    mod = importlib.import_module("so101_demo.runtime.container_campaign.controller_stop")
    monkeypatch.setattr(mod, "_open_owner", lambda: pytest.fail("invalid budget created ROS node"))
    with pytest.raises(ValueError, match="ACT_CONTROLLER_STOP_CONFIG_INVALID"):
        mod.observe_act_controller_stop(timeout_s=budget)


@pytest.mark.parametrize("problem", ["empty", "missing_neck", "bool_ack", "bool_status", "extra_lane", "extra_field", "wrong_kind", "future_status"])
def test_malformed_original_observation_cannot_claim_proven(monkeypatch, problem):
    from so101_demo.runtime.parallel_ipc.frames import canonical_json

    mod, valid, _ = run_probe(monkeypatch)
    document = copy.deepcopy(valid.document)
    if problem == "empty": document["lanes"] = {}
    elif problem == "missing_neck": document["lanes"].pop("neck")
    elif problem == "bool_ack": document["lanes"]["neck"]["cancel_return_code"] = False
    elif problem == "bool_status": document["lanes"]["neck"]["statuses"][0]["status"] = True
    elif problem == "extra_lane": document["lanes"]["other"] = document["lanes"]["neck"]
    elif problem == "extra_field": document["PASS"] = True
    elif problem == "wrong_kind": document["kind"] = "other"
    elif problem == "future_status": document["lanes"]["neck"]["status_received_monotonic_ns"] = document["completed_monotonic_ns"]+1
    with pytest.raises(ValueError, match="ACT_CONTROLLER_STOP_OBSERVATION_INVALID"):
        mod.ControllerStopObservation(canonical_json(document))


def test_real_ros_goal_messages_with_numpy_uuid_prove_a_stop_after_a_real_episode(monkeypatch):
    """rclpy hands uuid as numpy.uint8 elements; a stop with real goal records in the status lists must still be provable."""
    _, observation, _ = run_probe(monkeypatch, real_messages=True)
    assert observation.proven
    lane = observation.document["lanes"]["arm"]
    assert lane["statuses"][0]["goal"]["uuid"] == bytes(range(16)).hex()
    assert lane["goals_canceling"][0]["uuid"] == bytes(range(16)).hex()
    _, active, _ = run_probe(monkeypatch, real_messages=True, active="arm_controller")
    assert not active.proven


@pytest.mark.parametrize("bad", [[1.5]+[0]*15, [True]+[0]*15, [256]+[0]*15, list(range(15)), [-1]+[0]*15])
def test_malformed_goal_uuid_is_still_refused(bad):
    mod = importlib.import_module("so101_demo.runtime.container_campaign.controller_stop")
    goal = SimpleNamespace(goal_id=SimpleNamespace(uuid=bad), stamp=SimpleNamespace(sec=1, nanosec=2))
    with pytest.raises(ValueError, match="ACT_CONTROLLER_STOP_MESSAGE_INVALID"):
        mod._goal(goal)
