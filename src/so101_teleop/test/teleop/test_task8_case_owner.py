"""A Task 8 case cannot release admission before both owned processes retire."""

import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
import uuid

import pytest

from so101_teleop.unified.act_stack import ActStackLaunch
from so101_teleop.unified.bridge import ActChildLaunch
from so101_teleop.unified.contracts import MutationError, OwnerKey
from so101_teleop.unified.task8_case_owner import Task8CaseOwner
from so101_teleop.unified.task8_startup_issuer import (
    InstalledActStackReadinessProbe, Task8StartupProofIssuer,
)
from so101_teleop.unified.task8_startup_proof import Task8StartupProofConsumer


OWNER = OwnerKey(12345, 12345, 101, "a" * 64, "b" * 64)
CHILD_OWNER = OwnerKey(23456, 23456, 202, "c" * 64, "d" * 64)


def receipt(owner, **extra):
    return {"leader_pid": owner.pid, "pgid": owner.pgid,
            "started_ticks": owner.started_ticks, "argv_sha256": owner.argv_sha256,
            "group_clear": True, **extra}


def prepared(tmp_path, *, fail=None):
    events = []
    ipc_base = Path(os.environ.get("SO101_IPC_SOCKET_BASE", "/tmp"))
    ipc_root = ipc_base / f"c{uuid.uuid4().hex[:8]}"
    ipc_root.mkdir()
    child = ActChildLaunch(
        campaign_id="campaign-271", worker_id="w1", execution_generation=1,
        ros_domain_id=179, namespace="/act/w1", controller_name="arm_controller_w1",
        mujoco_session_id="session-271", socket_root=str(ipc_root),
    )
    stack_root = tmp_path / "task8-live" / child.campaign_id / "stack"
    stack_root.mkdir(parents=True)
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

        def bind_startup_owner(self, owner):
            assert owner == OWNER
            events.append("startup.bind")

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

    child_owner = ChildOwner()

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
            if child_owner.started:
                raise MutationError("GRAPH_NOT_CLEARED")
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
        Workload(), child_owner, stack_factory=stack_factory,
        final_clear_probe=final_clear,
        artifact_binding=lambda _payload, _context: "bound-artifacts",
        require_startup_proof=False,
    )
    return owner, spec, context, events


def test_case_retirement_precedes_admission_release(tmp_path):
    owner, spec, context, events = prepared(tmp_path)

    async def run():
        admitted, worker = await owner.start(spec)
        assert admitted is context and worker is not None
        await owner.finish(attempt_id="attempt-271")

    asyncio.run(run())
    assert events == ["admit", "child.start", "stack.start", "cancel", "child.stop",
                      "stack.stop", "final.clear", "release"]
    # both owned processes retired, the graph cleared, and only then admission released
    assert owner._child_retired is True
    assert owner._stack_retired is True
    assert owner._final_clear is True
    assert owner.context is None
    # the retirement receipts for both owned processes are on disk
    child_receipt = Path(spec.payload["children"][0]["socket_root"]) / "cleanup-receipt.json"
    assert child_receipt.is_file(), "the child retirement receipt is missing"
    child_document = json.loads(child_receipt.read_text())
    assert child_document["group_clear"] is True
    stack_receipts = list((tmp_path / "task8-live").rglob("cleanup-receipt.json"))
    assert stack_receipts, "the stack retirement receipt is missing"
    assert all(json.loads(item.read_text())["group_clear"] is True for item in stack_receipts)


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


def test_alternative_in_root_stack_path_is_rejected_before_stack_start(tmp_path):
    owner, spec, _, events = prepared(tmp_path)
    alternate_root = tmp_path / "alternate-stack"
    alternate_root.mkdir()
    original_factory = owner.stack_factory

    def wrong_factory(context, child):
        stack = original_factory(context, child)
        stack.launch = replace(stack.launch, evidence_root=alternate_root)
        return stack

    owner.stack_factory = wrong_factory
    with pytest.raises(MutationError, match="TASK8_CASE_STACK_SCOPE_INVALID"):
        asyncio.run(owner.start(spec))
    assert events == ["admit", "child.start", "child.stop", "release"]


def test_symlinked_stack_parent_is_rejected_before_stack_start(tmp_path):
    owner, spec, _, events = prepared(tmp_path)
    scope = tmp_path / "task8-live"
    relocated = tmp_path / "relocated"
    scope.rename(relocated)
    scope.symlink_to(relocated, target_is_directory=True)

    with pytest.raises(MutationError, match="TASK8_CASE_STACK_SCOPE_INVALID"):
        asyncio.run(owner.start(spec))
    assert events == ["admit", "child.start", "child.stop", "release"]


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


def test_failed_stack_start_retires_only_after_stop_and_both_receipts(tmp_path):
    owner, spec, _, events = prepared(tmp_path, fail="stack.start")

    async def run():
        with pytest.raises(MutationError, match="ACT_STACK_READINESS_UNPROVED"):
            await owner.start(spec)
        await owner.retire_failed_start(attempt_id="attempt-271")

    asyncio.run(run())
    assert events == ["admit", "child.start", "stack.start", "cancel",
                      "child.stop", "stack.stop", "final.clear", "release"]
    assert owner.context is None


def test_failed_stack_start_with_unknown_owner_remains_fenced(tmp_path):
    owner, spec, context, events = prepared(tmp_path, fail="stack.start")

    async def run():
        with pytest.raises(MutationError, match="ACT_STACK_READINESS_UNPROVED"):
            await owner.start(spec)
        owner.stack.owner = None
        with pytest.raises(MutationError, match="PICK_PLACE_CASE_STACK_OWNER_INVALID"):
            await owner.retire_failed_start(attempt_id="attempt-271")

    asyncio.run(run())
    assert owner.context is context
    assert events == ["admit", "child.start", "stack.start"]


def test_live_case_cannot_be_ready_without_installed_startup_proof(tmp_path):
    owner, spec, context, events = prepared(tmp_path)
    owner.require_startup_proof = True
    with pytest.raises(MutationError, match="TASK8_STARTUP_PROOF_UNAVAILABLE"):
        asyncio.run(owner.start(spec))
    assert owner.context is context
    assert events == ["admit", "child.start", "stack.start"]


def test_case_owner_issues_bound_proof_before_returning_ready(tmp_path):
    owner, spec, context, events = prepared(tmp_path)
    context.operation_id = "operation-289"
    for key, digit in (
        ("source_sha256", "1"), ("manifest_sha256", "2"),
        ("runtime_config_sha256", "3"), ("collection_config_sha256", "4"),
        ("contact_policy_fingerprint", "5"),
    ):
        setattr(context, key, digit * 64)
    binary = tmp_path / "act_stack_ready"
    binary.write_text("#!/usr/bin/env python3\n")
    binary.chmod(0o700)
    original_factory = owner.stack_factory
    child = ActChildLaunch(**spec.payload["children"][0])

    def factory(value, launch):
        stack = original_factory(value, launch)
        stack.launch = replace(stack.launch,
                               environment={"GZ_PARTITION": "act-data-exp289-179"})
        artifact = {
            "schema_version": 1, "session_id": child.mujoco_session_id,
            "ros_domain_id": child.ros_domain_id,
            "captured_monotonic_ns": time.monotonic_ns(),
            "checks": {name: True for name in (
                "mujoco_session", "advancing_physics", "controller_states",
                "moveit_graph", "physical_stop", "head_rgb", "wrist_rgb",
            )},
        }

        def runner(argv, **_kwargs):
            return subprocess.CompletedProcess(argv, 0,
                                               (json.dumps(artifact) + "\n").encode(), b"")

        stack.ready_probe = InstalledActStackReadinessProbe(
            stack.launch, binary, run=runner,
        )
        original_start = stack.start

        async def start():
            assert stack.ready_probe() is True
            return await original_start()

        stack.start = start
        return stack

    owner.stack_factory = factory
    owner.require_startup_proof = True
    owner.startup_proof_issuer = lambda *args: Task8StartupProofIssuer(
        *args, live_probe=lambda _owner: True,
    )

    async def run():
        await owner.start(spec)
        receipt = Task8StartupProofConsumer(
            context, child, stack_owner=OWNER, child_owner=CHILD_OWNER,
            live_probe=lambda _owner: True,
        ).consume()
        assert receipt["operation_id"] == context.operation_id
        assert events == ["admit", "child.start", "stack.start", "startup.bind"]
        await owner.finish(attempt_id="attempt-271")

    asyncio.run(run())


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
