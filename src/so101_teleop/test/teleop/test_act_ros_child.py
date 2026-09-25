"""A ROS child routes only its own ACT work through registered methods."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import pytest

from so101_teleop.unified.child_runtime import ChildRuntime
from so101_teleop.unified.contracts import MutationError, OwnerKey
from so101_teleop.unified.ipc import decode_request
from so101_teleop.unified.ros_child import act_identity_from_environment, local_owner
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
