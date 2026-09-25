"""A ROS child routes only its own ACT work through registered methods."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from so101_teleop.unified.child_runtime import ChildRuntime
from so101_teleop.unified.contracts import DispatchToken, MutationError, OwnerKey, PendingChildKey
from so101_teleop.unified.ipc import decode_request
from so101_teleop.unified.ros_child import RclpyActionDriver, act_identity_from_environment, local_owner
from so101_teleop.process_identity import read_identity
from so101_teleop.unified.bridge import BridgeLaunch, BridgeProcessOwner


class ActDriver:
    def __init__(self):
        self.seen = []
        self.fail = False

    async def task8_phase(self, request):
        if self.fail:
            raise RuntimeError("child crashed")
        self.seen.append((request.worker_id, request.payload["scenario_id"]))
        return {"status": "PASSED", "scenario_id": request.payload["scenario_id"]}

    async def cancel_act(self, request):
        return {"stopped_confirmed": True, "reason": request.payload["reason"]}


def request(*, worker_id="w00", generation=3, operation="task8_phase"):
    deadline = time.monotonic_ns() + 10**9
    payload = (
        {"reason": "operator"} if operation == "cancel" else
        {"scenario_id": "scene-1", "stop_after": "MICRO_LIFT", "manifest_sha256": "a" * 64,
         "runtime_config_sha256": "b" * 64, "contact_policy_fingerprint": "c" * 64}
    )
    document = {
        "version": 1, "operation": operation, "command_id": "command-1",
        "deadline_ns": deadline, "service_epoch": "epoch-1", "runtime_id": "runtime-w00",
        "service_token": "private", "campaign_id": "campaign-1", "worker_id": worker_id,
        "session_id": "session-0", "attempt_id": "attempt-0", "execution_generation": generation,
        "token": {"operation_id": "operation-1", "child_id": worker_id,
                  "runtime_id": "runtime-w00", "execution_generation": generation,
                  "deadline_ns": deadline, "revocation_revision": 0},
        "payload": payload,
    }
    return decode_request(json.dumps(document).encode(), now_ns=time.monotonic_ns())


def runtime(driver):
    return ChildRuntime(
        driver, owner=OwnerKey(1, 1, 1, "a" * 64, "b" * 64),
        service_epoch="epoch-1", runtime_id="runtime-w00", normal_queue_limit=2,
        act_campaign_id="campaign-1", act_worker_id="w00", act_generation=3,
    )


def test_child_routes_only_its_own_worker_and_generation():
    driver = ActDriver()
    child = runtime(driver)
    assert asyncio.run(child.dispatch_act(request()))["scenario_id"] == "scene-1"
    assert driver.seen == [("w00", "scene-1")]
    with pytest.raises(MutationError, match="ACT_WORKER_MISMATCH"):
        asyncio.run(child.dispatch_act(request(worker_id="w01")))
    with pytest.raises(MutationError, match="ACT_GENERATION_STALE"):
        asyncio.run(child.dispatch_act(request(generation=4)))
    assert driver.seen == [("w00", "scene-1")]


def test_child_crash_fences_following_work_but_cancel_remains_available():
    driver = ActDriver()
    child = runtime(driver)
    driver.fail = True
    with pytest.raises(MutationError, match="ACT_CHILD_FAILED"):
        asyncio.run(child.dispatch_act(request()))
    driver.fail = False
    with pytest.raises(MutationError, match="ACT_CHILD_FENCED"):
        asyncio.run(child.dispatch_act(request()))
    stopped = asyncio.run(child.dispatch_act(request(operation="cancel")))
    assert stopped == {"stopped_confirmed": True, "reason": "operator"}
    assert driver.seen == []


def test_child_fences_action_uncertainty_even_when_driver_raises_mutation_error():
    class UncertainDriver(ActDriver):
        async def task8_phase(self, request):
            raise MutationError("ROS_GOAL_RESPONSE_UNKNOWN")

    child = runtime(UncertainDriver())
    with pytest.raises(MutationError, match="ROS_GOAL_RESPONSE_UNKNOWN"):
        asyncio.run(child.dispatch_act(request()))
    with pytest.raises(MutationError, match="ACT_CHILD_FENCED"):
        asyncio.run(child.dispatch_act(request()))


def test_web_death_asks_act_driver_to_stop_all_owned_goals():
    class StopDriver(ActDriver):
        def __init__(self):
            super().__init__()
            self.stop_reasons = []

        async def stop_act(self, reason):
            self.stop_reasons.append(reason)
            return True

    driver = StopDriver()
    child = runtime(driver)
    asyncio.run(child.mark_web_dead("web owner lost"))
    assert driver.stop_reasons == ["web owner lost"]
    with pytest.raises(MutationError, match="ACT_CHILD_FENCED"):
        asyncio.run(child.dispatch_act(request()))


def test_ros_child_requires_complete_admitted_act_identity():
    environment = {
        "SO101_ACT_CAMPAIGN_ID": "campaign-1",
        "SO101_ACT_WORKER_ID": "w00",
        "SO101_ACT_GENERATION": "3",
    }
    assert act_identity_from_environment(environment) == ("campaign-1", "w00", 3)
    assert act_identity_from_environment({}) == (None, None, None)
    with pytest.raises(MutationError, match="ACT_CHILD_IDENTITY_INCOMPLETE"):
        act_identity_from_environment({"SO101_ACT_WORKER_ID": "w00"})
    with pytest.raises(MutationError, match="ACT_CHILD_GENERATION_INVALID"):
        act_identity_from_environment(dict(environment, SO101_ACT_GENERATION="-1"))


def test_ros_child_reports_exact_kernel_owner_for_safety_channel():
    observed = read_identity(os.getpid())
    owner = local_owner("runtime-test")
    assert owner.pid == observed.pid
    assert owner.pgid == observed.pgid
    assert owner.started_ticks == observed.start_marker
    assert owner.argv_sha256 == observed.command_sha256


def test_act_bridge_ready_rejects_wrong_epoch_and_worker_identity(tmp_path):
    launch = BridgeLaunch(
        Path(sys.executable), tmp_path, "runtime-w00",
        {"SO101_CHILD_SERVICE_EPOCH": "epoch-1", "SO101_ACT_CAMPAIGN_ID": "campaign-1",
         "SO101_ACT_WORKER_ID": "w00", "SO101_ACT_GENERATION": "3"},
        tmp_path / "socket",
    )
    owner = BridgeProcessOwner(launch, object(), object())
    owner.process = SimpleNamespace(poll=lambda: None)
    owner._ready_document = {"service_epoch": "epoch-old", "runtime_id": "runtime-w00",
                             "campaign_id": "campaign-1", "worker_id": "w00",
                             "execution_generation": 3}
    assert not owner.ready()
    owner._ready_document["service_epoch"] = "epoch-1"
    owner._ready_document["worker_id"] = "w01"
    assert not owner.ready()


def test_ros_action_driver_preserves_real_acceptance_terminal_and_stop():
    owner = OwnerKey(1, 1, 1, "a" * 64, "b" * 64)
    deadline = time.monotonic_ns() + 10**9
    token = DispatchToken("operation-1", "w00", "runtime-w00", 3, deadline, 0)

    class Broker:
        def __init__(self):
            self.goal_uuid = None
            self.cancelled = []

        def submit(self, kind, goal, *, goal_uuid):
            assert kind == "arm" and goal == {"trajectory": "test-goal"}
            self.goal_uuid = goal_uuid
            return "internal-1"

        def goal_state(self, gid):
            assert gid == "internal-1"
            return {"accepted": True, "status": 4, "result": {"error_code": 0},
                    "driver_error": None, "ros_goal_uuid": self.goal_uuid.replace("-", "")}

        def refresh_idle(self):
            pass

        def stopped(self):
            return True

        def cancel(self, gid):
            self.cancelled.append(gid)

        def refresh_stop(self):
            pass

    broker = Broker()
    driver = RclpyActionDriver(broker=broker, owner=owner, stop_timeout_s=0.05)
    goal_uuid = driver.allocate_goal_uuid(PendingChildKey("operation-1", "w00", "runtime-w00", 3))
    driver.register_action(token, goal_uuid, "arm", {"trajectory": "test-goal"})
    ack = asyncio.run(driver.submit(token, goal_uuid))
    assert ack.accepted and ack.key.goal_uuid == goal_uuid
    terminal = asyncio.run(driver.terminal(goal_uuid))
    assert terminal.succeeded and terminal.stopped_confirmed and terminal.cleanup_confirmed
    assert asyncio.run(driver.cancel(goal_uuid)) is True
    assert broker.cancelled == ["internal-1"]


def test_ros_action_driver_requests_physical_stop_on_unknown_acceptance():
    owner = OwnerKey(1, 1, 1, "a" * 64, "b" * 64)
    token = DispatchToken("operation-1", "w00", "runtime-w00", 3,
                          time.monotonic_ns() + 10**9, 0)

    class Broker:
        def __init__(self):
            self.stop_reasons = []

        def submit(self, kind, goal, *, goal_uuid):
            return "internal-1"

        def goal_state(self, gid):
            return {"accepted": None, "driver_error": "GOAL_RESPONSE_LOST"}

        def stop_all(self, reason):
            self.stop_reasons.append(reason)

    broker = Broker()
    driver = RclpyActionDriver(broker=broker, owner=owner)
    goal_uuid = driver.allocate_goal_uuid(PendingChildKey("operation-1", "w00", "runtime-w00", 3))
    driver.register_action(token, goal_uuid, "arm", object())
    with pytest.raises(MutationError, match="ROS_GOAL_RESPONSE_UNKNOWN"):
        asyncio.run(driver.submit(token, goal_uuid))
    assert broker.stop_reasons == ["ROS_GOAL_RESPONSE_UNKNOWN"]


def test_ros_action_driver_requests_stop_when_send_result_is_unknown():
    owner = OwnerKey(1, 1, 1, "a" * 64, "b" * 64)
    token = DispatchToken("operation-1", "w00", "runtime-w00", 3,
                          time.monotonic_ns() + 10**9, 0)

    class Broker:
        def __init__(self):
            self.stop_reasons = []

        def submit(self, kind, goal, *, goal_uuid):
            raise RuntimeError("goal send uncertain")

        def stop_all(self, reason):
            self.stop_reasons.append(reason)

    broker = Broker()
    driver = RclpyActionDriver(broker=broker, owner=owner)
    goal_uuid = driver.allocate_goal_uuid(PendingChildKey("operation-1", "w00", "runtime-w00", 3))
    driver.register_action(token, goal_uuid, "arm", object())
    with pytest.raises(MutationError, match="ROS_GOAL_SEND_UNKNOWN"):
        asyncio.run(driver.submit(token, goal_uuid))
    assert broker.stop_reasons == ["ROS_GOAL_SEND_UNKNOWN"]


def test_act_task8_child_refuses_missing_phase_port_before_motion():
    driver = RclpyActionDriver(broker=object())
    with pytest.raises(MutationError, match="ACT_TASK8_PORT_NOT_PROVISIONED"):
        asyncio.run(driver.task8_phase(request()))


def test_act_task8_child_routes_closed_hashes_to_runner_and_confirms_stop():
    class Broker:
        def __init__(self):
            self.reasons = []

        def stop_all(self, reason):
            self.reasons.append(reason)

        def refresh_stop(self):
            pass

        def stopped(self):
            return True

    class Port:
        def __init__(self):
            self.phases = []
            self.stops = []

        def begin(self, req):
            return {"session_id": req["session_id"], "attempt_id": req["attempt_id"],
                    "reset_epoch": 1, "release_epoch": 0, "full_restart": True}

        def run_phase(self, phase, req):
            self.phases.append(phase)
            return {
                "phase": phase, "session_id": req["session_id"], "attempt_id": req["attempt_id"],
                "reset_epoch": 1, "release_epoch": 0,
                "planning_ok": True, "controller_reference_ok": True,
                "joint_feedback_ok": True, "contact_ok": True, "mujoco_ok": True,
                "planning_scene_ok": True, "head_rgb_ok": True, "wrist_rgb_ok": True,
                "manual_intervention": False, "moveit_recovery": False,
                "holding_state": "EMPTY", "bilateral_contact": phase == "CLOSE",
                "micro_lift_confirmed": False, "cup_off_table": False,
                "cup_supported": True, "released": False,
                "no_fingertip_contact": True, "placement_stable": False, "retreat_stable": False,
            }

        def safe_stop(self, reason, req):
            self.stops.append(reason)
            return True

    broker, port = Broker(), Port()
    driver = RclpyActionDriver(
        broker=broker, task8_port=port,
        act_hashes={"manifest_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                    "contact_policy_fingerprint": "c" * 64},
    )
    child_request = request()
    with pytest.raises(MutationError, match="ACT_TASK8_HASH_MISMATCH"):
        bad = child_request.model_copy(update={"payload": {**child_request.payload,
            "contact_policy_fingerprint": "d" * 64}})
        asyncio.run(driver.task8_phase(bad))
    assert port.phases == []
    # Prefix through CLOSE needs only three phases, then a physical stop.
    close_request = child_request.model_copy(update={"payload": {**child_request.payload,
        "stop_after": "CLOSE"}})
    result = asyncio.run(driver.task8_phase(close_request))
    assert result["completed_phases"] == ["SEARCH", "APPROACH", "CLOSE"]
    assert result["formal_episode_eligible"] is False
    assert port.stops == ["PHASE_PREFIX_COMPLETE"]
    assert broker.reasons == ["TASK8_COMPLETED"]
    assert asyncio.run(driver.cancel_act(request(operation="cancel"))) == {
        "stopped_confirmed": True, "reason": "operator"}


def test_act_cancel_interrupts_next_phase_while_runner_thread_is_busy():
    entered, release = threading.Event(), threading.Event()

    class Broker:
        def __init__(self):
            self.reasons = []

        def stop_all(self, reason):
            self.reasons.append(reason)

        def refresh_stop(self):
            pass

        def stopped(self):
            return True

    class BlockingPort:
        def __init__(self):
            self.phases = []
            self.stops = []

        def begin(self, req):
            return {"session_id": req["session_id"], "attempt_id": req["attempt_id"],
                    "reset_epoch": 1, "release_epoch": 0, "full_restart": True}

        def run_phase(self, phase, req):
            self.phases.append(phase)
            entered.set()
            assert release.wait(2)
            return {}

        def safe_stop(self, reason, req):
            self.stops.append(reason)
            return True

    broker, port = Broker(), BlockingPort()
    driver = RclpyActionDriver(
        broker=broker, task8_port=port,
        act_hashes={"manifest_sha256": "a" * 64, "runtime_config_sha256": "b" * 64,
                    "contact_policy_fingerprint": "c" * 64},
    )

    async def run():
        pending = asyncio.create_task(driver.task8_phase(request()))
        assert await asyncio.to_thread(entered.wait, 1)
        canceled = await driver.cancel_act(request(operation="cancel"))
        release.set()
        with pytest.raises(MutationError, match="ACT_TASK8_FAILED"):
            await pending
        return canceled

    assert asyncio.run(run())["stopped_confirmed"] is True
    assert port.phases == ["SEARCH"]
    assert port.stops == ["TASK8_ABORT"]
    assert broker.reasons == ["operator", "TASK8_FAILED"]
