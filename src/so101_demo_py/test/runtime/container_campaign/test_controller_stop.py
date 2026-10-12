"""All four ACT action lanes need actual cancellation ACK and settled status."""

import importlib
import copy
from types import SimpleNamespace

import pytest


def run_probe(monkeypatch, *, missing=None, active=None, bad_ack=None):
    mod = importlib.import_module("so101_demo.runtime.container_campaign.controller_stop")
    clock = [1_000_000_000]
    endpoints = []
    closed = []
    class Future:
        def done(self): return True
        def result(self):
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
                if missing and missing in topic: continue
                status = 2 if active and active in topic else 4
                callback(SimpleNamespace(status_list=[SimpleNamespace(status=status,
                    goal_info=SimpleNamespace(goal_id=SimpleNamespace(uuid=list(range(16))),
                                              stamp=SimpleNamespace(sec=1,nanosec=2)))]))
        def close(self): closed.append(True)
    monkeypatch.setattr(mod, "_open_owner", lambda namespace: Owner())
    monkeypatch.setattr(mod, "_ros_types", lambda: (object, SimpleNamespace(Request=lambda: object()), object()))
    result = mod.observe_act_controller_stop(ros_namespace="/act/campaign/w00", timeout_s=0.1,
                                            monotonic_ns=lambda: clock[0])
    assert closed == [True]
    return mod, result, endpoints


def test_neck_moveit_arm_and_gripper_all_have_original_status_and_ack(monkeypatch):
    mod, observation, endpoints = run_probe(monkeypatch)
    assert observation.proven
    assert len(endpoints) == 8
    assert all(name.startswith("/act/campaign/w00/") for name in endpoints)
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


@pytest.mark.parametrize("budget", [True, 0, -1, float("inf"), float("nan")])
def test_invalid_budget_refused_before_any_ros_context(budget, monkeypatch):
    mod = importlib.import_module("so101_demo.runtime.container_campaign.controller_stop")
    monkeypatch.setattr(mod, "_open_owner", lambda namespace: pytest.fail("invalid budget created ROS node"))
    with pytest.raises(ValueError, match="ACT_CONTROLLER_STOP_CONFIG_INVALID"):
        mod.observe_act_controller_stop(ros_namespace="/act/campaign/w00", timeout_s=budget)


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
