"""Admission for every mutation entry point.

The gateway is the only way a mutation may reach execution resources. It verifies the
request's instance authority and live lease, classifies the operation, and only then takes
the global reservation. Read-only operations never take a reservation, and an unknown
operation is refused instead of inheriting a permissive default.
"""

from __future__ import annotations

from enum import StrEnum

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import uuid

from .arbiter import GlobalMutationArbiter
from .contracts import (
    AdmittedCampaignContext,
    Domain,
    DispatchToken,
    LeaseIdentity,
    MutationError,
    OperationSpec,
    PHASE_CANCELLED,
    PHASE_COMPLETE,
    Reservation,
    RequestAuthority,
)
from .bridge import ActChildLaunch, ActChildRegistry
from .gpu_workload import ActGpuWorkloadArbiter, GpuLeaseRequest, resolve_physical_gpu
from .instances import InstanceRegistry

DEFAULT_DEADLINE_NS = 1 << 62


class MutationClass(StrEnum):
    MOTION = "motion"
    SHORT_WRITE = "short_write"
    READ = "read"
    SAFETY = "safety"


TELEOP_OPERATIONS: dict[str, MutationClass] = {
    "plan_joints": MutationClass.MOTION,
    "plan_tcp": MutationClass.MOTION,
    "execute": MutationClass.MOTION,
    "execute_plan": MutationClass.MOTION,
    "gripper": MutationClass.MOTION,
    "attachment_attach": MutationClass.MOTION,
    "attachment_detach": MutationClass.MOTION,
    "scene_repair": MutationClass.MOTION,
    "robot_home": MutationClass.MOTION,
    "simulation_reset": MutationClass.MOTION,
    "workflow_start": MutationClass.MOTION,
    "workflow_run": MutationClass.MOTION,
    "workflow_step": MutationClass.MOTION,
    "workflow_resume": MutationClass.MOTION,
    "workflow_force-continue": MutationClass.MOTION,
    "workflow_reset": MutationClass.MOTION,
    "camera_preset": MutationClass.SHORT_WRITE,
    "parameters": MutationClass.SHORT_WRITE,
    "screenshot": MutationClass.SHORT_WRITE,
    "workflow_stop": MutationClass.SAFETY,
    "cancel": MutationClass.SAFETY,
    "snapshot": MutationClass.READ,
    "telemetry": MutationClass.READ,
    "capabilities": MutationClass.READ,
    "health": MutationClass.READ,
    "camera_presets": MutationClass.READ,
}

TASKS_OPERATIONS: dict[str, MutationClass] = {
    "start": MutationClass.MOTION,
    "recovery": MutationClass.MOTION,
    "shutdown": MutationClass.MOTION,
    "cancel": MutationClass.SAFETY,
    "capture": MutationClass.SHORT_WRITE,
    "rendered_image": MutationClass.READ,
    "reachability": MutationClass.SHORT_WRITE,
    "presets": MutationClass.READ,
    "list_runs": MutationClass.READ,
    "status": MutationClass.READ,
}

VALIDATION_OPERATIONS: dict[str, MutationClass] = {
    "create_manifest": MutationClass.SHORT_WRITE,
    "preflight": MutationClass.SHORT_WRITE,
    "start": MutationClass.MOTION,
    "retry": MutationClass.MOTION,
    "cancel": MutationClass.SAFETY,
    "get_manifest": MutationClass.READ,
    "list_campaigns": MutationClass.READ,
    "get_campaign": MutationClass.READ,
    "capabilities": MutationClass.READ,
    "health": MutationClass.READ,
    "acquire_lease": MutationClass.SAFETY,
    "renew_lease": MutationClass.SAFETY,
    "release_lease": MutationClass.SAFETY,
}

OPERATION_TABLES: dict[str, dict[str, MutationClass]] = {
    "teleop": TELEOP_OPERATIONS,
    "tasks": TASKS_OPERATIONS,
    "validation": VALIDATION_OPERATIONS,
}


def classify(domain_table: str, operation: str) -> MutationClass:
    table = OPERATION_TABLES.get(domain_table)
    if table is None:
        raise MutationError(f"UNKNOWN_OPERATION_TABLE: {domain_table}")
    mutation_class = table.get(operation)
    if mutation_class is None:
        raise MutationError(f"UNKNOWN_OPERATION: {domain_table}/{operation} defaults to refused")
    return mutation_class


class AdmissionHook:
    """The single admission check every Teleop/Tasks entry point runs before dispatch.

    It returns a ``(code, message)`` refusal or ``None`` when the entry may proceed, so the
    calling service keeps ownership of its own DTO and error formatting.
    """

    def __init__(
        self,
        gateway: "AdmissionGateway",
        *,
        domain_table: str,
        runtime_id: str,
        authority_provider,
    ) -> None:
        self.gateway = gateway
        self.domain_table = domain_table
        self.runtime_id = runtime_id
        self.authority_provider = authority_provider

    def check(self, body: dict, operation: str) -> tuple[str, str] | None:
        try:
            authority, lease = self.authority_provider()
            reservation = self.gateway.admit_entry(
                domain_table=self.domain_table,
                operation=operation,
                body=body,
                authority=authority,
                lease=lease,
                runtime_id=self.runtime_id,
            )
        except MutationError as error:
            code, _, message = str(error).partition(": ")
            return code, message or str(error)
        if reservation is not None:
            self.gateway.arbiter.hold(reservation.operation_id)
        return None


class AdmissionGateway:
    def __init__(self, arbiter: GlobalMutationArbiter, instances: InstanceRegistry) -> None:
        self.arbiter = arbiter
        self.instances = instances

    def require_authority(
        self, authority: RequestAuthority | None, lease: LeaseIdentity | None, operation: str
    ) -> None:
        """Every mutation, including legacy entries, needs a live bound instance."""
        if authority is None or lease is None:
            raise MutationError(f"CONTROLLER_INSTANCE_REQUIRED: {operation} needs instance authority")
        self.instances.authorize(authority, lease)

    def begin(
        self,
        spec: OperationSpec,
        authority: RequestAuthority | None,
        lease: LeaseIdentity | None,
        *,
        domain_table: str | None = None,
    ) -> Reservation:
        table = domain_table or ("validation" if str(spec.domain) == "validation" else "teleop")
        mutation_class = classify(table, spec.kind)
        if mutation_class is MutationClass.READ:
            raise MutationError(f"ADMISSION_READ_OPERATION: {spec.kind} must not take a reservation")
        if mutation_class is MutationClass.SAFETY:
            raise MutationError(f"ADMISSION_SAFETY_OPERATION: {spec.kind} uses the safety lane")
        self.require_authority(authority, lease, spec.kind)
        return self.arbiter.begin(spec)

    def admit_entry(
        self,
        *,
        domain_table: str,
        operation: str,
        body: dict,
        authority: RequestAuthority | None,
        lease: LeaseIdentity | None,
        runtime_id: str,
    ) -> Reservation | None:
        """Admit one HTTP or internal entry point; returns None for read-only entries."""
        mutation_class = classify(domain_table, operation)
        if mutation_class is MutationClass.READ:
            return None
        if mutation_class is MutationClass.SAFETY:
            raise MutationError(
                f"ADMISSION_SAFETY_OPERATION: {operation} must use the safety lane, not a reservation"
            )
        self.require_authority(authority, lease, operation)
        assert authority is not None
        spec = OperationSpec(
            command_id=str(body.get("command_id") or f"{operation}-{uuid.uuid4().hex}"),
            domain=Domain.VALIDATION if domain_table == "validation" else Domain.TELEOP,
            kind=operation,
            payload=dict(body.get("payload") or {}),
            runtime_id=runtime_id,
            execution_generation=authority.execution_generation,
            deadline_ns=int(body.get("deadline_ns") or DEFAULT_DEADLINE_NS),
        )
        return self.arbiter.begin(spec)

    def resume(
        self,
        parent_id: str,
        authority: RequestAuthority | None,
        lease: LeaseIdentity | None,
        *,
        child_id: str = "workflow",
    ) -> DispatchToken:
        """Internal continuations only: a client cannot mint authority from a parent ID."""
        self.require_authority(authority, lease, "resume")
        self.arbiter.resume_parent(parent_id)
        return self.arbiter.prepare_child(parent_id, child_id)


_ACT_START_KINDS = frozenset({"task8_phase", "task8_full", "act_collection_start", "act_collection_resume"})
_ACT_PAYLOAD_KEYS = frozenset({
    "campaign_id", "backend", "worker_count", "source_path", "source_sha256",
    "manifest_path", "manifest_sha256", "runtime_config_path", "runtime_config_sha256",
    "collection_config_path", "collection_config_sha256", "contact_policy_fingerprint",
    "proposal_path", "activation_receipt_path", "evidence_root", "service_epoch",
    "resource_binding_id", "qualification_mode", "qualification_receipt_path", "children",
})


def _real_owner(pid: int, started_ticks: int) -> bool:
    from ..process_identity import ProcessIdentityError, read_identity

    try:
        identity = read_identity(pid)
    except ProcessIdentityError:
        return False
    return identity.live and identity.start_marker == started_ticks and pid == os.getpid()


class UnifiedWorkloadService:
    """Single owner admission for ACT, before Worker/Recorder/ROS child composition."""

    def __init__(
        self, *, arbiter: GlobalMutationArbiter, gpu_arbiter: ActGpuWorkloadArbiter,
        child_registry: ActChildRegistry, service_epoch: str, runtime_id: str,
        stable_host_id: str, gpu_selector: str, visible_physical_uuids: tuple[str, ...],
        resource_binding_id: str, owner_pid: int, owner_started_ticks: int,
        clock_ns, owner_identity_valid=_real_owner,
    ) -> None:
        if gpu_arbiter.store is not arbiter.store:
            raise ValueError("WORKLOAD_STORE_MISMATCH")
        self.arbiter = arbiter
        self.gpu_arbiter = gpu_arbiter
        self.child_registry = child_registry
        self.service_epoch = service_epoch
        self.runtime_id = runtime_id
        self.stable_host_id = stable_host_id
        self.gpu_selector = gpu_selector
        self.visible_physical_uuids = tuple(visible_physical_uuids)
        self.resource_binding_id = resource_binding_id
        self.owner_pid = owner_pid
        self.owner_started_ticks = owner_started_ticks
        self.owner_identity_valid = owner_identity_valid
        self.clock_ns = clock_ns
        self._start_lock = threading.RLock()

    @staticmethod
    def _read_json(path_value: str, root: Path) -> dict:
        path = Path(path_value)
        if not path.is_absolute() or not path.is_relative_to(root) or not path.is_file():
            raise ValueError("POLICY_NOT_ACTIVATED")
        try:
            document = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("POLICY_NOT_ACTIVATED") from error
        if not isinstance(document, dict):
            raise ValueError("POLICY_NOT_ACTIVATED")
        return document

    @staticmethod
    def _verify_artifact(path_value: str, expected_sha256: str) -> None:
        """Read the exact artifact bytes once before acquiring campaign resources."""
        if (
            not isinstance(path_value, str)
            or not Path(path_value).is_absolute()
            or ".." in Path(path_value).parts
            or not isinstance(expected_sha256, str)
            or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        ):
            raise ValueError("CAMPAIGN_ARTIFACT_INVALID")
        try:
            fd = os.open(path_value, os.O_RDONLY | os.O_NOFOLLOW)
            with os.fdopen(fd, "rb") as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise ValueError("CAMPAIGN_ARTIFACT_INVALID")
                digest = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as error:
            raise ValueError("CAMPAIGN_ARTIFACT_INVALID") from error
        if digest != expected_sha256:
            raise ValueError("CAMPAIGN_ARTIFACT_HASH_MISMATCH")

    def _validate_start(self, spec: OperationSpec) -> tuple[dict, tuple[ActChildLaunch, ...], str]:
        if spec.domain is not Domain.VALIDATION or spec.kind not in _ACT_START_KINDS:
            raise ValueError("UNKNOWN_OPERATION")
        if spec.runtime_id != self.runtime_id or spec.deadline_ns <= self.clock_ns():
            raise ValueError("CAMPAIGN_RUNTIME_OR_DEADLINE_INVALID")
        payload = spec.payload
        if not isinstance(payload, dict) or set(payload) != _ACT_PAYLOAD_KEYS:
            raise ValueError("CAMPAIGN_START_SCHEMA")
        if payload["backend"] != "mujoco":
            raise ValueError("MUJOCO_ONLY")
        if payload["service_epoch"] != self.service_epoch or payload["resource_binding_id"] != self.resource_binding_id:
            raise ValueError("CAMPAIGN_AUTHORITY_STALE")
        if not self.owner_identity_valid(self.owner_pid, self.owner_started_ticks):
            raise ValueError("CAMPAIGN_OWNER_IDENTITY_DRIFT")
        if type(payload["worker_count"]) is not int or payload["worker_count"] < 1:
            raise ValueError("CAMPAIGN_WORKER_COUNT_INVALID")
        if type(payload["qualification_mode"]) is not bool:
            raise ValueError("QUALIFICATION_MODE_INVALID")
        if spec.kind.startswith("act_collection"):
            if payload["qualification_mode"]:
                if payload["worker_count"] not in (1, 2, 8):
                    raise ValueError("QUALIFICATION_WORKER_COUNT_INVALID")
            elif payload["worker_count"] != 8:
                raise ValueError("FORMAL_W8_REQUIRED")
        root = Path(payload["evidence_root"])
        if not root.is_absolute() or ".." in root.parts or not root.is_dir():
            raise ValueError("CAMPAIGN_EVIDENCE_ROOT_INVALID")
        for name in ("source", "manifest", "runtime_config", "collection_config"):
            self._verify_artifact(payload[f"{name}_path"], payload[f"{name}_sha256"])
        proposal = self._read_json(payload["proposal_path"], root)
        receipt = self._read_json(payload["activation_receipt_path"], root)
        try:
            from so101_demo.act.contact_calibration import verify_disabled_proposal
            from so101_demo.act.contact_policy import verify_activation

            verify_disabled_proposal(proposal)
            verify_activation(proposal["payload"], receipt)
        except (ImportError, KeyError, TypeError, ValueError) as error:
            raise ValueError("POLICY_NOT_ACTIVATED") from error
        if (
            proposal["policy_fingerprint"] != payload["contact_policy_fingerprint"]
            or receipt["policy_fingerprint"] != payload["contact_policy_fingerprint"]
            or receipt["evidence_root"] != str(root)
        ):
            raise ValueError("POLICY_NOT_ACTIVATED")
        if spec.kind.startswith("act_collection") and not payload["qualification_mode"]:
            qualified_path = payload["qualification_receipt_path"]
            if not isinstance(qualified_path, str):
                raise ValueError("W8_QUALIFICATION_REQUIRED")
            try:
                qualification = self._read_json(qualified_path, root)
            except ValueError as error:
                raise ValueError("W8_QUALIFICATION_REQUIRED") from error
            required = {
                "status": "PASSED", "worker_count": 8,
                "source_sha256": payload["source_sha256"],
                "runtime_config_sha256": payload["runtime_config_sha256"],
                "collection_config_sha256": payload["collection_config_sha256"],
                "contact_policy_fingerprint": payload["contact_policy_fingerprint"],
            }
            if any(qualification.get(key) != value for key, value in required.items()):
                raise ValueError("W8_QUALIFICATION_MISMATCH")
            # A self-declared PASSED document is not physical qualification.
            # Task 11A must provide an independent verifier of the frozen
            # contract, two committed 20-scene waves and actual per-Worker
            # terminal leases before formal admission can become reachable.
            try:
                from so101_demo.act.w8_qualification import verify_w8_qualification
            except ImportError as error:
                raise ValueError("W8_QUALIFICATION_VERIFIER_UNAVAILABLE") from error
            try:
                verified = verify_w8_qualification(Path(qualified_path), payload)
            except (OSError, KeyError, TypeError, ValueError) as error:
                raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID") from error
            if verified is not True:
                raise ValueError("W8_QUALIFICATION_EVIDENCE_INVALID")
        elif payload["qualification_receipt_path"] is not None:
            raise ValueError("QUALIFICATION_RECEIPT_UNEXPECTED")
        if not isinstance(payload["children"], list) or len(payload["children"]) != payload["worker_count"]:
            raise ValueError("CHILD_COUNT_MISMATCH")
        proposed = ActChildRegistry()
        for item in self.child_registry.launches():
            proposed.register(item)
        for item in payload["children"]:
            if not isinstance(item, dict) or set(item) != set(ActChildLaunch.__dataclass_fields__):
                raise ValueError("CHILD_LAUNCH_SCHEMA")
            child = ActChildLaunch(**item)
            if child.campaign_id != payload["campaign_id"] or child.execution_generation != spec.execution_generation:
                raise ValueError("CHILD_CAMPAIGN_MISMATCH")
            proposed.register(child)
        children = tuple(ActChildLaunch(**item) for item in payload["children"])
        physical_uuid = resolve_physical_gpu(self.gpu_selector, self.visible_physical_uuids)
        return payload, children, physical_uuid

    def start(self, spec: OperationSpec) -> AdmittedCampaignContext:
        """Validate everything, acquire resources and persist one context atomically."""
        with self._start_lock:
            payload, children, physical_uuid = self._validate_start(spec)
            store = self.arbiter.store
            with store.immediate_transaction():
                repeated = store.repeat(spec.command_id, store.fingerprint(spec))
                if repeated is not None:
                    row = store._query_one(
                        "SELECT context_json FROM act_campaign_contexts WHERE operation_id=?",
                        (repeated.operation_id,),
                    )
                    if row is None:
                        raise ValueError("CAMPAIGN_CONTEXT_MISSING")
                    return AdmittedCampaignContext.from_dict(json.loads(row[0]))
            # Reserve the complete child map before taking either durable resource.
            # Another registry user cannot create a collision between validation and
            # persistence, and a failed database/lease step rolls this map back.
            with self.child_registry.reserve_many(children):
                operation_id = uuid.uuid4().hex
                lease = GpuLeaseRequest(
                    stable_host_id=self.stable_host_id, physical_gpu_uuid=physical_uuid,
                    operation_id=operation_id, service_epoch=self.service_epoch,
                    owner_pid=self.owner_pid, owner_started_ticks=self.owner_started_ticks,
                    workload=spec.kind, execution_generation=spec.execution_generation,
                    deadline_ns=spec.deadline_ns,
                )
                self.gpu_arbiter.acquire(lease)
                try:
                    with store.immediate_transaction():
                        store.require_idle()
                        reservation = store.insert_parent(spec, operation_id=operation_id)
                        child_map = [item.__dict__ for item in children]
                        child_map_sha256 = hashlib.sha256(json.dumps(
                            child_map, sort_keys=True, separators=(",", ":"), allow_nan=False,
                        ).encode()).hexdigest()
                        context = AdmittedCampaignContext(
                            campaign_id=payload["campaign_id"], operation_id=reservation.operation_id,
                            workload_kind=spec.kind, service_epoch=self.service_epoch,
                            execution_generation=spec.execution_generation,
                            stable_host_id=self.stable_host_id, physical_gpu_uuid=physical_uuid,
                            worker_count=payload["worker_count"], source_sha256=payload["source_sha256"],
                            manifest_sha256=payload["manifest_sha256"],
                            runtime_config_sha256=payload["runtime_config_sha256"],
                            collection_config_sha256=payload["collection_config_sha256"],
                            contact_policy_fingerprint=payload["contact_policy_fingerprint"],
                            domain_session_map_sha256=child_map_sha256,
                            resource_binding_id=self.resource_binding_id,
                            evidence_root=str(Path(payload["evidence_root"])),
                            admitted_at_monotonic_s=self.clock_ns() / 1e9,
                            deadline_monotonic_s=spec.deadline_ns / 1e9,
                        )
                        store._connection.execute(
                            "INSERT INTO act_campaign_contexts VALUES (?,?,?)",
                            (operation_id, context.campaign_id, json.dumps(context.to_dict(), sort_keys=True)),
                        )
                except BaseException:
                    self.gpu_arbiter.release(lease)
                    raise
                return context

    def finish(self, context: AdmittedCampaignContext, *, cleanup_confirmed: bool):
        """Settle only this admitted campaign after its child owner proves cleanup.

        The context and physical lease are matched to durable rows before any
        resource is released. An unconverged action keeps the global fence and
        GPU lease. The context record remains for readback and replay audit.
        """
        if cleanup_confirmed is not True:
            raise ValueError("ACT_CHILD_CLEANUP_NOT_CONFIRMED")
        if not isinstance(context, AdmittedCampaignContext):
            raise ValueError("CAMPAIGN_CONTEXT_MISMATCH")
        with self._start_lock:
            if not self.owner_identity_valid(self.owner_pid, self.owner_started_ticks):
                raise ValueError("CAMPAIGN_OWNER_IDENTITY_DRIFT")
            store = self.arbiter.store
            row = store._query_one(
                "SELECT context_json FROM act_campaign_contexts WHERE operation_id=?",
                (context.operation_id,),
            )
            if row is None or AdmittedCampaignContext.from_dict(json.loads(row[0])) != context:
                raise ValueError("CAMPAIGN_CONTEXT_MISMATCH")
            launches = tuple(item for item in self.child_registry.launches()
                             if item.campaign_id == context.campaign_id
                             and item.execution_generation == context.execution_generation)
            if not launches:
                lease_row = store._query_one(
                    "SELECT * FROM gpu_workload_leases WHERE stable_host_id=? AND physical_gpu_uuid=?",
                    (context.stable_host_id, context.physical_gpu_uuid),
                )
                projection = store.projection(context.operation_id)
                if (lease_row is None and projection.phase in (PHASE_COMPLETE, PHASE_CANCELLED)
                        and self.arbiter.is_idle()):
                    return projection
            child_map = [item.__dict__ for item in launches]
            child_map_sha256 = hashlib.sha256(json.dumps(
                child_map, sort_keys=True, separators=(",", ":"), allow_nan=False,
            ).encode()).hexdigest()
            if len(launches) != context.worker_count or child_map_sha256 != context.domain_session_map_sha256:
                raise ValueError("CHILD_RELEASE_MISMATCH")
            with store.immediate_transaction():
                gpu_row = store._query_one(
                    "SELECT * FROM gpu_workload_leases WHERE stable_host_id=? AND physical_gpu_uuid=?",
                    (context.stable_host_id, context.physical_gpu_uuid),
                )
                if gpu_row is None:
                    raise ValueError("GPU_LEASE_OWNER_MISMATCH")
                lease = GpuLeaseRequest(*tuple(gpu_row))
                if (lease.operation_id != context.operation_id
                        or lease.service_epoch != context.service_epoch
                        or lease.owner_pid != self.owner_pid
                        or lease.owner_started_ticks != self.owner_started_ticks
                        or lease.workload != context.workload_kind
                        or lease.execution_generation != context.execution_generation):
                    raise ValueError("GPU_LEASE_OWNER_MISMATCH")
                outcome = store.settle_locked(context.operation_id, cleanup_confirmed=True)
                if outcome.code is None:
                    store._connection.execute(
                        "DELETE FROM gpu_workload_leases WHERE stable_host_id=? AND physical_gpu_uuid=?",
                        (context.stable_host_id, context.physical_gpu_uuid),
                    )
            if outcome.code:
                raise MutationError(outcome.code)
            self.child_registry.release_many(launches)
            return outcome.projection
