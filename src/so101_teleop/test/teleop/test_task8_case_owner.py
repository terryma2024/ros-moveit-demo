"""A Task 8 case cannot release admission before both owned processes retire."""

import asyncio
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace
import uuid

import pytest

from so101_teleop.unified.act_stack import ActStackLaunch
from so101_teleop.unified.bridge import ActChildLaunch
from so101_teleop.unified.contracts import MutationError, OwnerKey
from so101_teleop.unified.task8_case_owner import Task8CaseOwner


OWNER = OwnerKey(12345, 12345, 101, "a" * 64, "b" * 64)
CHILD_OWNER = OwnerKey(23456, 23456, 202, "c" * 64, "d" * 64)


def receipt(owner, **extra):
    return {"leader_pid": owner.pid, "pgid": owner.pgid,
            "started_ticks": owner.started_ticks, "argv_sha256": owner.argv_sha256,
            "group_clear": True, **extra}


def prepared(tmp_path, *, fail=None):
    events = []
    stack_root = tmp_path / "stack"
    stack_root.mkdir()
    ipc_base = Path(os.environ.get("SO101_IPC_SOCKET_BASE", "/tmp"))
    ipc_root = ipc_base / f"c{uuid.uuid4().hex[:8]}"
    ipc_root.mkdir()
    child = ActChildLaunch(
        campaign_id="campaign-271", worker_id="w1", execution_generation=1,
        ros_domain_id=179, namespace="/act/w1", controller_name="arm_controller_w1",
        mujoco_session_id="session-271", socket_root=str(ipc_root),
    )
    context = SimpleNamespace(
        campaign_id=child.campaign_id, execution_generation=1,
        workload_kind="task8_full", worker_count=1, evidence_root=str(tmp_path),
    )
    spec = SimpleNamespace(kind="task8_full", payload={"children": [child.__dict__],
                                         "evidence_root": str(tmp_path)})

    class Workload:
        def start(self, request, *, allow_existing):
            events.append("admit")
            assert request is spec and allow_existing is False
            if fail == "admission":
                raise MutationError("CALIBRATION_REQUIRED")
            return context

        def finish(self, value, *, cleanup_confirmed):
            events.append("release")
            assert value is context and cleanup_confirmed is True

    class Port:
        def __init__(self):
            self.client = SimpleNamespace(owner=CHILD_OWNER)
            self.launch = child

        async def cancel(self, request):
            events.append("cancel")
            assert request["session_id"] == child.mujoco_session_id
            assert request["attempt_id"] == "attempt-271"
            if fail == "cancel":
                raise MutationError("ACT_STOP_NOT_CONFIRMED")
            return {"stopped_confirmed": True}

    class ChildOwner:
        def __init__(self):
            self.port = Port()
            self.started = False

        async def start(self, value, launches, *, artifacts):
            events.append("child.start")
            assert value is context and launches == (child,)
            assert artifacts == "bound-artifacts"
            if fail == "child.start":
                raise MutationError("CHILD_START_FAILED")
            self.started = True
            return (self.port,)

        async def stop_owned(self):
            events.append("child.stop")
            if fail == "child.stop":
                raise MutationError("ACT_CHILD_CLEANUP_NOT_CONFIRMED")
            if self.started:
                (ipc_root / "cleanup-receipt.json").write_text(json.dumps(receipt(CHILD_OWNER)))
                if fail == "child.socket":
                    (ipc_root / "normal.sock").write_text("leftover")
                self.started = False

    class Stack:
        def __init__(self, launch):
            self.launch = launch
            self.owner = None
            self.process = None

        async def start(self):
            events.append("stack.start")
            self.owner = OWNER
            self.process = object()
            if fail == "stack.start":
                raise MutationError("ACT_STACK_READINESS_UNPROVED")
            return OWNER

        async def stop(self):
            events.append("stack.stop")
            if fail == "stack.stop":
                raise MutationError("STOP_NOT_CONFIRMED")
            proof = receipt(OWNER, physical_stop_confirmed=True, graph_clear=True,
                            session_id=child.mujoco_session_id,
                            ros_domain_id=child.ros_domain_id)
            if fail == "stack.receipt":
                proof["physical_stop_confirmed"] = False
            if fail == "stack.scope":
                proof["session_id"] = "other-session"
            (stack_root / "cleanup-receipt.json").write_text(json.dumps(proof))
            self.process = self.owner = None

    def stack_factory(value, launch):
        assert value is context and launch == child
        stack_launch = ActStackLaunch(
            ros2_executable=Path(sys.executable), session_id=child.mujoco_session_id,
            evidence_root=stack_root, ros_domain_id=child.ros_domain_id,
            environment={},
        )
        return Stack(stack_launch)

    async def final_clear(_domain_id):
        events.append("final.clear")
        return fail != "final.clear"

    owner = Task8CaseOwner(
        Workload(), ChildOwner(), stack_factory=stack_factory,
        final_clear_probe=final_clear,
        artifact_binding=lambda _payload, _context: "bound-artifacts",
    )
    return owner, spec, context, events


def test_case_retirement_precedes_admission_release(tmp_path):
    owner, spec, context, events = prepared(tmp_path)

    async def run():
        admitted, worker = await owner.start(spec)
        assert admitted is context and worker is not None
        await owner.finish(attempt_id="attempt-271")

    asyncio.run(run())
    assert events == ["admit", "child.start", "stack.start", "cancel", "stack.stop",
                      "child.stop", "final.clear", "release"]
    assert owner.context is None


def test_finished_case_owner_cannot_start_a_second_case(tmp_path):
    owner, spec, _, events = prepared(tmp_path)

    async def run():
        await owner.start(spec)
        await owner.finish(attempt_id="attempt-271")
        completed = tuple(events)
        with pytest.raises(MutationError, match="TASK8_CASE_OWNER_REUSED"):
            await owner.start(spec)
        assert tuple(events) == completed

    asyncio.run(run())


def test_admission_failure_spawns_nothing(tmp_path):
    owner, spec, _, events = prepared(tmp_path, fail="admission")
    with pytest.raises(MutationError, match="CALIBRATION_REQUIRED"):
        asyncio.run(owner.start(spec))
    assert events == ["admit"]


def test_child_start_failure_releases_without_starting_stack(tmp_path):
    owner, spec, _, events = prepared(tmp_path, fail="child.start")
    with pytest.raises(MutationError, match="CHILD_START_FAILED"):
        asyncio.run(owner.start(spec))
    assert events == ["admit", "child.start", "child.stop", "release"]
    assert owner.context is None


def test_failed_stack_start_after_spawn_keeps_child_and_admission_owned(tmp_path):
    owner, spec, context, events = prepared(tmp_path, fail="stack.start")
    with pytest.raises(MutationError, match="ACT_STACK_READINESS_UNPROVED"):
        asyncio.run(owner.start(spec))
    assert owner.context is context
    assert events == ["admit", "child.start", "stack.start"]


@pytest.mark.parametrize("failure", ["cancel", "stack.stop", "stack.receipt",
                                           "stack.scope", "child.stop", "child.socket",
                                           "final.clear"])
def test_uncertain_retirement_keeps_admission_fence(tmp_path, failure):
    owner, spec, context, events = prepared(tmp_path, fail=failure)

    async def run():
        await owner.start(spec)
        with pytest.raises(MutationError):
            await owner.finish(attempt_id="attempt-271")

    asyncio.run(run())
    assert owner.context is context
    assert "release" not in events
