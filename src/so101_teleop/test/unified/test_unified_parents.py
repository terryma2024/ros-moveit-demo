"""Parent-operation tests: one reservation across the whole arm/gripper sequence."""

from __future__ import annotations

import asyncio

import pytest

from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.contracts import (
    ActionKey,
    ActionTerminal,
    DispatchAck,
    Domain,
    MutationError,
    OperationSpec,
    OwnerKey,
    RequestAuthority,
)
from so101_teleop.unified.intent_store import IntentStore
from so101_teleop.unified.parents import ParentSequencer, WorkflowCheckpoint


class TwoStepWorker:
    def __init__(self) -> None:
        self.arm_done = asyncio.Event()
        self.arm_terminal_gate = asyncio.Event()
        self.arm_terminal_gate.set()
        self.gripper_sent = asyncio.Event()
        self.before_gripper = asyncio.Event()
        self.gripper_allowed = asyncio.Event()
        self.arm_result = True
        self.arm_cleanup = True
        self.gripper_result = True
        self.gripper_cleanup = True
        self.plan_home_calls = 0
        self.workflow_checkpoints: list[WorkflowCheckpoint] = []

    def _ack(self, token, child_id: str) -> DispatchAck:
        return DispatchAck(
            ActionKey(
                token.operation_id, child_id, f"g-{child_id}", OwnerKey(1, 1, 1, "a", "e"), "R1", 1
            ),
            True,
        )

    async def dispatch_arm(self, plan_id, token):
        self.arm_done.set()
        return self._ack(token, "arm")

    async def dispatch_gripper(self, target, token):
        self.before_gripper.set()
        await self.gripper_allowed.wait()
        self.gripper_sent.set()
        return self._ack(token, "gripper")

    async def wait_terminal(self, ack):
        if ack.key.child_id == "arm":
            await self.arm_done.wait()
            await self.arm_terminal_gate.wait()
            return ActionTerminal(ack.key, self.arm_result, True, self.arm_cleanup)
        return ActionTerminal(ack.key, self.gripper_result, True, self.gripper_cleanup)

    async def plan_home(self):
        self.plan_home_calls += 1
        return "home-plan-1"

    async def workflow(self, operation, run_id, token):
        checkpoint = self.workflow_checkpoints.pop(0)
        return checkpoint

    async def current_snapshot(self):
        return type("Snapshot", (), {"mode": "READY", "revision": 3})()

    async def camera_presets(self):
        return {"presets": ["top"]}

    async def command(self, name, body, reservation):
        return {"command_id": body.get("command_id", ""), "accepted": True, "succeeded": True, "code": "OK"}


def make(tmp_path, worker=None, guard=None):
    store = IntentStore.open(tmp_path / "state")
    arbiter = GlobalMutationArbiter(store, clock_ns=lambda: 1)
    worker = worker or TwoStepWorker()

    async def allow(_authority):
        return None

    sequencer = ParentSequencer(worker, arbiter, authority_guard=guard or allow)
    return store, arbiter, worker, sequencer


def authority() -> RequestAuthority:
    return RequestAuthority(Domain.TELEOP, "i", "p", 1, 1)


def execute_all_spec(command_id: str = "all-1") -> OperationSpec:
    return OperationSpec(
        command_id, Domain.TELEOP, "execute_all", {"plan_id": "p1", "gripper_target": 0.0}, "R1", 1, 10**18
    )


def test_parent_blocks_validation_between_arm_and_gripper(tmp_path):
    async def run():
        store = IntentStore.open(tmp_path / "state")
        arb = GlobalMutationArbiter(store, clock_ns=lambda: 1)
        worker = TwoStepWorker()
        authority_value = RequestAuthority(Domain.TELEOP, "i", "p", 1, 1)

        async def allow(_):
            return None

        seq = ParentSequencer(worker, arb, authority_guard=allow)
        spec = OperationSpec(
            "all-1", Domain.TELEOP, "execute_all", {"plan_id": "p1", "gripper_target": 0.0}, "R1", 1, 100
        )
        pending = asyncio.create_task(seq.execute_all(spec, authority_value))
        worker.arm_done.set()
        await asyncio.wait_for(worker.before_gripper.wait(), 1)
        with pytest.raises(MutationError):
            arb.begin(OperationSpec("v1", Domain.VALIDATION, "start", {}, "R1", 1, 100))
        worker.gripper_allowed.set()
        await worker.gripper_sent.wait()
        result = await pending
        assert len(result.children) == 2 and result.phase == "COMPLETE"
        store.close()

    asyncio.run(run())


def test_cancel_between_steps_never_dispatches_the_gripper(tmp_path):
    async def run():
        store, arbiter, worker, sequencer = make(tmp_path)
        try:
            worker.arm_terminal_gate.clear()
            pending = asyncio.create_task(sequencer.execute_all(execute_all_spec(), authority()))
            await asyncio.wait_for(worker.arm_done.wait(), 1)
            arbiter.cancel_parent(_operation_id(arbiter))
            worker.arm_terminal_gate.set()
            with pytest.raises(MutationError, match="INTENT_REVOKED"):
                await pending
            assert not worker.before_gripper.is_set(), "a cancelled parent never dispatches the gripper"
            assert not worker.gripper_sent.is_set()
            assert not arbiter.is_idle(), "a cancelled parent keeps its reservation"
        finally:
            store.close()

    asyncio.run(run())


def _operation_id(arbiter: GlobalMutationArbiter) -> str:
    row = arbiter.store._query_one("SELECT operation_id FROM parents ORDER BY created_ns DESC LIMIT 1")
    assert row is not None
    return row["operation_id"]


def test_failed_arm_never_dispatches_the_gripper(tmp_path):
    async def run():
        store, arbiter, worker, sequencer = make(tmp_path)
        try:
            worker.arm_result = False
            result = await sequencer.execute_all(execute_all_spec("all-fail"), authority())
            assert [child.key.child_id for child in result.children] == ["arm"]
            assert result.phase == "COMPLETE"
            assert not worker.before_gripper.is_set()
        finally:
            store.close()

    asyncio.run(run())


def test_arm_without_cleanup_proof_blocks_the_parent(tmp_path):
    async def run():
        store, arbiter, worker, sequencer = make(tmp_path)
        try:
            worker.arm_result = False
            worker.arm_cleanup = False
            with pytest.raises(MutationError, match="CLEANUP_NOT_CONFIRMED"):
                await sequencer.execute_all(execute_all_spec("all-unclean"), authority())
            assert not arbiter.is_idle()
        finally:
            store.close()

    asyncio.run(run())


def test_home_is_one_parent_across_planning_arm_and_gripper(tmp_path):
    async def run():
        store, arbiter, worker, sequencer = make(tmp_path)
        try:
            spec = OperationSpec("home-1", Domain.TELEOP, "robot_home", {"gripper_target": 0.2}, "R1", 1, 10**18)
            pending = asyncio.create_task(sequencer.home(spec, authority()))
            await asyncio.wait_for(worker.before_gripper.wait(), 1)
            assert worker.plan_home_calls == 1
            with pytest.raises(MutationError, match="GLOBAL_MUTATION_BUSY"):
                arbiter.begin(OperationSpec("v1", Domain.VALIDATION, "start", {}, "R1", 1, 10**18))
            worker.gripper_allowed.set()
            result = await pending
            assert len(result.children) == 2 and result.phase == "COMPLETE"
        finally:
            store.close()

    asyncio.run(run())


def test_workflow_pause_keeps_the_reservation_and_resume_needs_authority(tmp_path):
    async def run():
        store, arbiter, worker, sequencer = make(tmp_path)
        try:
            worker.workflow_checkpoints.append(
                WorkflowCheckpoint("run-1", "PAUSED_CHECKPOINT", True, False, False)
            )
            spec = OperationSpec("wf-1", Domain.TELEOP, "workflow_run", {"run_id": "run-1"}, "R1", 1, 10**18)
            result = await sequencer.workflow(spec, authority())
            assert result.phase == "PAUSED"
            assert not arbiter.is_idle(), "a resumable pause is not a parent terminal state"
            with pytest.raises(MutationError, match="GLOBAL_MUTATION_BUSY"):
                arbiter.begin(OperationSpec("v1", Domain.VALIDATION, "start", {}, "R1", 1, 10**18))
            token = await sequencer.resume(result.operation_id, authority(), operation="resume")
            assert token.child_id == "workflow"
            assert arbiter.projection(result.operation_id).phase == "ACTIVE"
        finally:
            store.close()

    asyncio.run(run())


def test_workflow_physical_terminal_settles_the_parent(tmp_path):
    async def run():
        store, arbiter, worker, sequencer = make(tmp_path)
        try:
            worker.workflow_checkpoints.append(WorkflowCheckpoint("run-2", "DONE", False, True, True))
            spec = OperationSpec("wf-2", Domain.TELEOP, "workflow_run", {"run_id": "run-2"}, "R1", 1, 10**18)
            result = await sequencer.workflow(spec, authority())
            assert result.phase == "COMPLETE"
            assert arbiter.is_idle()
        finally:
            store.close()

    asyncio.run(run())


def test_failing_authority_guard_blocks_instead_of_releasing(tmp_path):
    async def run():
        calls = {"n": 0}

        async def guard(_authority):
            calls["n"] += 1
            if calls["n"] > 1:
                raise MutationError("CONTROLLER_INSTANCE_MISMATCH: instance moved")

        store, arbiter, worker, sequencer = make(tmp_path, guard=guard)
        try:
            with pytest.raises(MutationError, match="CONTROLLER_INSTANCE_MISMATCH"):
                await sequencer.execute_all(execute_all_spec("all-guard"), authority())
            assert not arbiter.is_idle()
            assert not worker.before_gripper.is_set()
        finally:
            store.close()

    asyncio.run(run())


def test_duplicate_execute_all_command_returns_the_recorded_parent(tmp_path):
    async def run():
        store, arbiter, worker, sequencer = make(tmp_path)
        try:
            worker.gripper_allowed.set()
            first = await sequencer.execute_all(execute_all_spec("all-dup"), authority())
            second = await sequencer.execute_all(execute_all_spec("all-dup"), authority())
            assert first.operation_id == second.operation_id
            with pytest.raises(MutationError, match="COMMAND_ID_REUSED"):
                await sequencer.execute_all(
                    OperationSpec(
                        "all-dup",
                        Domain.TELEOP,
                        "execute_all",
                        {"plan_id": "p2", "gripper_target": 0.0},
                        "R1",
                        1,
                        10**18,
                    ),
                    authority(),
                )
        finally:
            store.close()

    asyncio.run(run())


def production_service(tmp_path, worker, gateway_rig):
    from so101_teleop.unified.instances import InstanceRegistry
    from so101_teleop.unified.admission import AdmissionGateway
    from so101_teleop.unified.safety import SafetyLane, SafetyLimits
    from so101_teleop.unified.goals import GoalRegistry
    from so101_teleop.unified.teleop_service import BackendView, ProductionTeleopService

    store = gateway_rig["store"]
    arbiter = gateway_rig["arbiter"]
    registry = InstanceRegistry(arbiter, service_epoch="e1", origin="http://x", clock_ns=lambda: 1)
    gateway = AdmissionGateway(arbiter, registry)
    lane = SafetyLane(GoalRegistry(), arbiter, limits=SafetyLimits(0.2, 0.2, 2), authorize=lambda a, k: None)

    async def allow(_authority):
        return None

    sequencer = ParentSequencer(worker, arbiter, authority_guard=allow)
    service = ProductionTeleopService(
        worker,
        admission=gateway,
        parents=sequencer,
        safety=lane,
        arbiter=arbiter,
        backend_view=BackendView("mujoco", "so101", "run", {"manual_joint_execute": True}),
        runtime_id="R1",
    )
    proof = registry.register(Domain.TELEOP)
    binding = registry.connect(proof.instance_id, proof.proof, origin="http://x")
    from so101_teleop.unified.contracts import LeaseIdentity

    lease = LeaseIdentity("l1", "s1", 1, 10**12)
    authorities = [registry.claim(binding, lease), lease]
    return service, authorities, arbiter, store, lane


def test_production_service_runs_execute_all_as_one_parent(tmp_path):
    async def run():
        worker = TwoStepWorker()
        worker.gripper_allowed.set()
        store = IntentStore.open(tmp_path / "state")
        rig = {"store": store, "arbiter": GlobalMutationArbiter(store, clock_ns=lambda: 1)}
        service, (authority, lease), arbiter, store, lane = production_service(tmp_path, worker, rig)
        try:
            result = await service.execute_all(
                {"command_id": "all-1", "plan_id": "p1", "gripper_target": 0.0},
                authority=authority,
                lease=lease,
            )
            assert result.phase == "COMPLETE"
            assert [child.key.child_id for child in result.children] == ["arm", "gripper"]
            assert arbiter.is_idle()
        finally:
            await lane.close()
            store.close()

    asyncio.run(run())


def test_production_service_refuses_capability_missing_operations(tmp_path):
    async def run():
        worker = TwoStepWorker()
        worker.gripper_allowed.set()
        store = IntentStore.open(tmp_path / "state")
        rig = {"store": store, "arbiter": GlobalMutationArbiter(store, clock_ns=lambda: 1)}
        service, (authority, lease), arbiter, store, lane = production_service(tmp_path, worker, rig)
        try:
            service.backend_view = type(service.backend_view)("mujoco", "so101", "run", {})
            result = await service.command("plan_joints", {"command_id": "p-1"}, authority=authority, lease=lease)
            assert result["code"] == "BACKEND_CAPABILITY_UNAVAILABLE"
            assert arbiter.is_idle(), "a refused capability must not keep a reservation"
        finally:
            await lane.close()
            store.close()

    asyncio.run(run())


def test_production_service_read_only_command_takes_no_reservation(tmp_path):
    async def run():
        worker = TwoStepWorker()
        store = IntentStore.open(tmp_path / "state")
        rig = {"store": store, "arbiter": GlobalMutationArbiter(store, clock_ns=lambda: 1)}
        service, (authority, lease), arbiter, store, lane = production_service(tmp_path, worker, rig)
        try:
            result = await service.command("capabilities", {}, authority=None, lease=None)
            assert result["backend"] == "mujoco"
            assert arbiter.is_idle()
        finally:
            await lane.close()
            store.close()

    asyncio.run(run())
