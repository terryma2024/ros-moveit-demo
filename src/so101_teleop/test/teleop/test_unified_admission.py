"""Admission tests: every mutation entry passes the same gateway, reads do not."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from so101_teleop.task_artifacts import ManifestArtifactStore
from so101_teleop.task_service import TaskService
from so101_teleop.unified.admission import (
    OPERATION_TABLES,
    AdmissionGateway,
    AdmissionHook,
    AdmissionGateway as _Gateway,
    MutationClass,
    classify,
)
from so101_teleop.unified.arbiter import GlobalMutationArbiter
from so101_teleop.unified.contracts import (
    Domain,
    LeaseIdentity,
    MutationError,
    OperationSpec,
)
from so101_teleop.unified.instances import InstanceRegistry
from so101_teleop.unified.intent_store import IntentStore


class Rig:
    def __init__(self, tmp_path: Path) -> None:
        self.store = IntentStore.open(tmp_path / "state")
        self.arbiter = GlobalMutationArbiter(self.store, clock_ns=lambda: 1)
        self.registry = InstanceRegistry(
            self.arbiter, service_epoch="e1", origin="http://127.0.0.1:8000", clock_ns=lambda: 1
        )
        self.gateway = AdmissionGateway(self.arbiter, self.registry)
        self.lease = LeaseIdentity("l1", "s1", 1, 10**12)

    def bind_controller(self, domain: Domain = Domain.TELEOP):
        proof = self.registry.register(domain)
        binding = self.registry.connect(proof.instance_id, proof.proof, origin="http://127.0.0.1:8000")
        authority = self.registry.claim(binding, self.lease)
        return authority, binding

    def close(self) -> None:
        self.store.close()


def test_every_teleop_mutation_has_a_class_and_unknown_operations_are_refused():
    assert classify("teleop", "execute") is MutationClass.MOTION
    assert classify("teleop", "camera_preset") is MutationClass.SHORT_WRITE
    assert classify("teleop", "snapshot") is MutationClass.READ
    assert classify("teleop", "workflow_stop") is MutationClass.SAFETY
    with pytest.raises(MutationError, match="UNKNOWN_OPERATION"):
        classify("teleop", "frobnicate")
    with pytest.raises(MutationError, match="UNKNOWN_OPERATION_TABLE"):
        classify("nonsense", "execute")
    # Every entry listed in the reviewed tables must be classified, never defaulted.
    for table, operations in OPERATION_TABLES.items():
        assert operations, table
        for name in operations:
            assert classify(table, name) in set(MutationClass)


def test_read_entries_never_take_a_reservation(tmp_path):
    rig = Rig(tmp_path)
    try:
        authority, _ = rig.bind_controller()
        assert (
            rig.gateway.admit_entry(
                domain_table="teleop",
                operation="snapshot",
                body={},
                authority=authority,
                lease=rig.lease,
                runtime_id="R1",
            )
            is None
        )
        assert rig.arbiter.is_idle()
    finally:
        rig.close()


def test_motion_without_instance_authority_is_refused(tmp_path):
    rig = Rig(tmp_path)
    try:
        with pytest.raises(MutationError, match="CONTROLLER_INSTANCE_REQUIRED"):
            rig.gateway.admit_entry(
                domain_table="teleop",
                operation="execute",
                body={"command_id": "c1"},
                authority=None,
                lease=None,
                runtime_id="R1",
            )
        assert rig.arbiter.is_idle()
    finally:
        rig.close()


def test_safety_entries_must_not_take_a_motion_reservation(tmp_path):
    rig = Rig(tmp_path)
    try:
        authority, _ = rig.bind_controller()
        with pytest.raises(MutationError, match="ADMISSION_SAFETY_OPERATION"):
            rig.gateway.admit_entry(
                domain_table="teleop",
                operation="cancel",
                body={"command_id": "c1"},
                authority=authority,
                lease=rig.lease,
                runtime_id="R1",
            )
    finally:
        rig.close()


def test_admitted_teleop_motion_blocks_validation_start(tmp_path):
    rig = Rig(tmp_path)
    try:
        authority, _ = rig.bind_controller()
        reservation = rig.gateway.admit_entry(
            domain_table="teleop",
            operation="execute",
            body={"command_id": "exec-1"},
            authority=authority,
            lease=rig.lease,
            runtime_id="R1",
        )
        assert reservation is not None
        with pytest.raises(MutationError, match="GLOBAL_MUTATION_BUSY"):
            rig.arbiter.begin(OperationSpec("v1", Domain.VALIDATION, "start", {}, "R1", 1, 10**18))
    finally:
        rig.close()


def test_admitted_validation_blocks_teleop_and_tasks(tmp_path):
    rig = Rig(tmp_path)
    try:
        validation_authority, _ = rig.bind_controller(Domain.VALIDATION)
        reservation = rig.gateway.admit_entry(
            domain_table="validation",
            operation="start",
            body={"command_id": "v-start"},
            authority=validation_authority,
            lease=rig.lease,
            runtime_id="R1",
        )
        assert reservation is not None
        for table, operation in (("teleop", "execute"), ("tasks", "start")):
            with pytest.raises(MutationError, match="GLOBAL_MUTATION_BUSY"):
                rig.arbiter.begin(
                    OperationSpec("other-1", Domain.TELEOP, operation, {}, "R1", 1, 10**18)
                )
    finally:
        rig.close()


def test_resume_cannot_be_minted_from_a_parent_id_alone(tmp_path):
    rig = Rig(tmp_path)
    try:
        authority, _ = rig.bind_controller()
        spec = OperationSpec("wf-1", Domain.TELEOP, "workflow_run", {}, "R1", 1, 10**18)
        parent = rig.arbiter.begin(spec)
        rig.arbiter.pause(parent.operation_id)
        with pytest.raises(MutationError, match="CONTROLLER_INSTANCE_REQUIRED"):
            rig.gateway.resume(parent.operation_id, None, None)
        token = rig.gateway.resume(parent.operation_id, authority, rig.lease)
        assert token.child_id == "workflow"
    finally:
        rig.close()


class AdmissionBoundTeleop:
    """The same gate shape ``server.TeleopService`` exposes to TaskService."""

    def __init__(self, hook: AdmissionHook) -> None:
        self._hook = hook
        self._task_active = lambda: False

    def bind_task_active(self, predicate) -> None:
        self._task_active = predicate

    def task_mutation_gate(self, body, capability: str):
        if self._task_active():
            return {"code": "TASK_BATCH_ACTIVE"}
        refusal = self._hook.check(body, capability)
        if refusal is None:
            return None
        code, message = refusal
        return {"code": code, "message": message}


def test_real_task_service_gate_runs_through_the_production_hook(tmp_path):
    """A real TaskService.start() is refused while another domain owns the reservation."""

    rig = Rig(tmp_path)
    try:
        authority, _ = rig.bind_controller()
        hook = AdmissionHook(
            rig.gateway,
            domain_table="tasks",
            runtime_id="R1",
            authority_provider=lambda: (authority, rig.lease),
        )
        teleop = AdmissionBoundTeleop(hook)
        artifacts = ManifestArtifactStore(tmp_path / "artifacts")
        service = TaskService(teleop, None, artifacts, presets=())

        async def run():
            validation_authority, binding = rig.bind_controller(Domain.VALIDATION)
            rig.gateway.admit_entry(
                domain_table="validation",
                operation="start",
                body={"command_id": "v-start"},
                authority=validation_authority,
                lease=rig.lease,
                runtime_id="R1",
            )
            assert hook.check({"command_id": "t1"}, "start") == (
                "GLOBAL_MUTATION_BUSY",
                "VALIDATION_ACTIVE",
            )
            assert service.is_active() is False

        asyncio.run(run())
    finally:
        rig.close()
