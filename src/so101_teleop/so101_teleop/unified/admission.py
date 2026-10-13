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
from .worker_slots import LAUNCHERS, ActWorkerSlot, ActWorkerSlotRegistry

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


def _collection_identity(payload: dict, campaign_config: dict) -> dict:
    """The controlled identity a container collection start binds, the one definition both planes compare: the qualification
    plane with its run contract, the formal plane with the qualification report's contract."""
    identity = {name: payload[name] for name in ('source_sha256', 'runtime_config_sha256',
                                                 'collection_config_sha256', 'contact_policy_fingerprint')}
    identity.update(gpu_uuid=campaign_config['gpu_uuid'], image_source_install=dict(
        inference=campaign_config['teacher_service']['image'], shard=campaign_config['shard_image']))
    return identity


_ACT_START_KINDS = frozenset({"pick_place_validation_phase", "pick_place_validation_full", "act_collection_start",
                              "act_diagnostic_episode"})
_DIAGNOSTIC_START_KIND = "act_diagnostic_episode"
_ACT_PAYLOAD_KEYS = frozenset({
    "campaign_id", "backend", "worker_count", "source_path", "source_sha256",
    "manifest_path", "manifest_sha256", "runtime_config_path", "runtime_config_sha256",
    "collection_config_path", "collection_config_sha256", "contact_policy_fingerprint",
    "proposal_path", "activation_receipt_path", "evidence_root", "service_epoch",
    "resource_binding_id", "qualification_mode", "qualification_receipt_path", "children",
    "calibration_report_path", "calibration_report_sha256",
})
# A container collection start carries neither a calibration report nor a contact proposal/activation receipt (CP-3609): the
# contact policy is bound by `contact_policy_fingerprint` alone and verified per task inside the shard.
_COLLECTION_EXCLUDED_KEYS = frozenset({
    'children', 'proposal_path', 'activation_receipt_path', 'calibration_report_path', 'calibration_report_sha256'})
_COLLECTION_PAYLOAD_KEYS = (_ACT_PAYLOAD_KEYS - _COLLECTION_EXCLUDED_KEYS) | frozenset({
    'worker_slots', 'registered_evidence_root', 'campaign_config_path', 'campaign_config_sha256',
    'qualification_receipt_sha256', 'instance_launcher'})

# a pick-place validation payload additionally names its preparation receipt; a collection payload must not
# (its expected set is _ACT_PAYLOAD_KEYS, so any receipt field there is a schema error)
_PICK_PLACE_VALIDATION_PAYLOAD_KEYS = _ACT_PAYLOAD_KEYS | frozenset({
    "preparation_receipt_path", "preparation_receipt_sha256"})

# the diagnostic payload additionally binds the frozen inputs and the explicit mode record; the
# formal and pick-place validation schemas above are unchanged, so neither can smuggle these fields in
_DIAGNOSTIC_PAYLOAD_KEYS = _ACT_PAYLOAD_KEYS | frozenset({
    "collection_scope_path", "collection_scope_sha256",
    "inputs_manifest_path", "inputs_manifest_sha256"})


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
        clock_ns, owner_identity_valid=_real_owner, gpu_inventory_probe=None,
        calibration_identity_probe=None, root_registration=None, container_inspect=None,
    ) -> None:
        if gpu_arbiter.store is not arbiter.store:
            raise ValueError("WORKLOAD_STORE_MISMATCH")
        self.arbiter = arbiter
        self.gpu_arbiter = gpu_arbiter
        self.child_registry = child_registry
        self.slot_registry = ActWorkerSlotRegistry(arbiter.store, child_registry=child_registry)
        self.root_registration = root_registration
        self.container_inspect = container_inspect or self._inspect_container
        self.service_epoch = service_epoch
        self.runtime_id = runtime_id
        self.stable_host_id = stable_host_id
        self.gpu_selector = gpu_selector
        self.visible_physical_uuids = tuple(visible_physical_uuids)
        self.gpu_inventory_probe = gpu_inventory_probe or (lambda: self.visible_physical_uuids)
        self.calibration_identity_probe = calibration_identity_probe
        self.resource_binding_id = resource_binding_id
        self.owner_pid = owner_pid
        self.owner_started_ticks = owner_started_ticks
        self.owner_identity_valid = owner_identity_valid
        self.clock_ns = clock_ns
        self._start_lock = threading.RLock()

    @staticmethod
    def _inspect_container(container_id):
        from .bridge import ContainerBridgeProcessOwner
        return ContainerBridgeProcessOwner._docker_inspect(container_id)

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
    def _verify_artifact(path_value: str, expected_sha256: str, *, read_bytes: bool = False) -> bytes | None:
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
                if read_bytes:
                    data = stream.read((1 << 20) + 1)
                    if len(data) > (1 << 20):
                        raise ValueError("CAMPAIGN_ARTIFACT_TOO_LARGE")
                    digest = hashlib.sha256(data).hexdigest()
                else:
                    data = None
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
        except OSError as error:
            raise ValueError("CAMPAIGN_ARTIFACT_INVALID") from error
        if digest != expected_sha256:
            raise ValueError("CAMPAIGN_ARTIFACT_HASH_MISMATCH")
        return data

    def _validate_start(self, spec: OperationSpec) -> tuple[dict, tuple, str]:
        if spec.kind == 'act_collection_resume':
            raise ValueError('ACT_CONTAINER_RESUME_FORBIDDEN')
        if spec.domain is not Domain.VALIDATION or spec.kind not in _ACT_START_KINDS:
            raise ValueError("UNKNOWN_OPERATION")
        if spec.runtime_id != self.runtime_id or spec.deadline_ns <= self.clock_ns():
            raise ValueError("CAMPAIGN_RUNTIME_OR_DEADLINE_INVALID")
        payload = spec.payload
        if not isinstance(payload, dict):
            raise ValueError("CAMPAIGN_START_SCHEMA")
        pick_place_validation = spec.kind in ("pick_place_validation_phase", "pick_place_validation_full")
        diagnostic = spec.kind == _DIAGNOSTIC_START_KIND
        container_collection = spec.kind == 'act_collection_start'
        expected = (_PICK_PLACE_VALIDATION_PAYLOAD_KEYS if pick_place_validation else
                    _DIAGNOSTIC_PAYLOAD_KEYS if diagnostic else _COLLECTION_PAYLOAD_KEYS)
        if set(payload) != expected:
            # a payload missing only the calibration pair is a calibration problem, not a schema one
            if set(payload) == expected - {"calibration_report_path",
                                           "calibration_report_sha256"}:
                raise ValueError("CALIBRATION_REQUIRED")
            raise ValueError("CAMPAIGN_START_SCHEMA")
        if pick_place_validation:
            # the receipt is verified before any mutation/GPU acquisition, and the verified bundle is
            # the only object an ActArtifactBinding may be built from
            from so101_demo.act.pick_place_validation_artifact_bundle import verify_pick_place_validation_startup_receipt
            verify_pick_place_validation_startup_receipt(payload)
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
        if container_collection:
            # `native` runs the instance as a Host process group with no isolation: exactly one worker, refused before anything else
            if payload['instance_launcher'] not in LAUNCHERS:
                raise ValueError('INSTANCE_LAUNCHER_INVALID')
            if payload['instance_launcher'] == 'native' and payload['worker_count'] != 1:
                raise ValueError('NATIVE_INSTANCE_SINGLE_WORKER_ONLY')
        if diagnostic:
            # one Worker, no resume and no qualification claim: the diagnostic scope replaces the
            # Head Search prerequisite only, so it must not borrow the qualification lane either
            if payload["qualification_mode"] is not False:
                raise ValueError("DIAGNOSTIC_QUALIFICATION_INVALID")
            if payload["worker_count"] != 1:
                raise ValueError("DIAGNOSTIC_SCOPE_INVALID")
            if payload["qualification_receipt_path"] is not None:
                raise ValueError("QUALIFICATION_RECEIPT_UNEXPECTED")
        if spec.kind.startswith("act_collection"):
            if payload["qualification_mode"]:
                if payload["worker_count"] not in (1, 2, 8):
                    raise ValueError("QUALIFICATION_WORKER_COUNT_INVALID")
            elif payload["worker_count"] != 8:
                raise ValueError("FORMAL_EIGHT_WORKER_REQUIRED")
        root = Path(payload["evidence_root"])
        if not root.is_absolute() or ".." in root.parts or not root.is_dir():
            raise ValueError("CAMPAIGN_EVIDENCE_ROOT_INVALID")
        campaign_config = None
        if container_collection:
            from so101_demo.runtime.inference.config import load_campaign_config
            from so101_demo.runtime.container_campaign.paths import validate_registered_evidence_root
            self._verify_artifact(payload['campaign_config_path'], payload['campaign_config_sha256'])
            campaign_config = load_campaign_config(payload['campaign_config_path'], roles=('teacher',),
                                                  expected_sha256=payload['campaign_config_sha256'])
            registered = validate_registered_evidence_root(campaign_config['evidence_root'],
                payload['registered_evidence_root'], registration=self.root_registration)
            if (root.resolve(strict=True) != root or root == registered or not root.is_relative_to(registered)
                    or campaign_config['controlled_runtime'] != dict(
                        path=payload['runtime_config_path'], sha256=payload['runtime_config_sha256'])):
                raise ValueError('CAMPAIGN_CONFIG_BINDING_MISMATCH')
        runtime_bytes = None
        for name in ("source", "runtime_config", "collection_config"):
            verified = self._verify_artifact(
                payload[f"{name}_path"], payload[f"{name}_sha256"],
                read_bytes=name == "runtime_config" and pick_place_validation,
            )
            if name == "runtime_config":
                runtime_bytes = verified
        manifest_bytes = self._verify_artifact(
            payload["manifest_path"], payload["manifest_sha256"],
            read_bytes=pick_place_validation or container_collection,
        )
        if spec.kind in ("pick_place_validation_phase", "pick_place_validation_full"):
            from so101_demo.act.pick_place_validation_manifest import require_pick_place_validation_manifest

            try:
                manifest = require_pick_place_validation_manifest(json.loads(manifest_bytes))
            except (TypeError, ValueError, UnicodeDecodeError) as error:
                raise ValueError("PICK_PLACE_VALIDATION_MANIFEST_INVALID") from error
            if any(manifest[name] != payload[name] for name in (
                "source_sha256", "runtime_config_sha256", "collection_config_sha256",
                "contact_policy_fingerprint",
            )):
                raise ValueError("PICK_PLACE_VALIDATION_MANIFEST_BINDING_MISMATCH")
        if container_collection and payload['qualification_mode']:
            from so101_demo.act.parallel_collection_contracts import (
                validate_functional_contract, validate_qualification_contract)
            from so101_demo.runtime.parallel_ipc.frames import _pairs
            manifest = json.loads(manifest_bytes,object_pairs_hook=_pairs,
                parse_constant=lambda name: (_ for _ in ()).throw(ValueError(name)))
            contract = (validate_functional_contract(manifest) if payload['worker_count'] in (1,2)
                        else validate_qualification_contract(manifest))
            if (contract['worker_count'] != payload['worker_count']
                    or contract['controlled_identity'] != _collection_identity(payload, campaign_config)):
                raise ValueError('COLLECTION_RUN_CONTRACT_BINDING_MISMATCH')
            expected_ref = (dict(path=payload['manifest_path'],sha256=payload['manifest_sha256'])
                            if payload['worker_count'] == 8 else None)
            if campaign_config['qualification_contract'] != expected_ref:
                raise ValueError('COLLECTION_RUN_CONTRACT_BINDING_MISMATCH')
        if container_collection:
            # no calibration report: only the installed ACT profile must still exist and be readable
            try:
                from so101_demo.act.calibration import installed_calibration_identity

                (self.calibration_identity_probe or installed_calibration_identity)()
            except (OSError, TypeError, json.JSONDecodeError, ValueError) as error:
                raise ValueError("CALIBRATION_REQUIRED") from error
        else:
            try:
                calibration_path = Path(payload["calibration_report_path"])
                if (not calibration_path.is_absolute() or ".." in calibration_path.parts
                        or not calibration_path.resolve().is_relative_to(root.resolve())):
                    raise ValueError("CALIBRATION_REQUIRED")
                self._verify_artifact(str(calibration_path), payload["calibration_report_sha256"])
                calibration_bytes = calibration_path.read_bytes()
                if hashlib.sha256(calibration_bytes).hexdigest() != payload["calibration_report_sha256"]:
                    raise ValueError("CALIBRATION_REQUIRED")
                calibration = json.loads(calibration_bytes)
                from so101_demo.act.calibration import installed_calibration_identity, require_gate

                if not diagnostic:
                    require_gate(calibration,
                                 "formal_collection" if spec.kind.startswith("act_collection")
                                 else "pick_place_validation")
                # the installed ACT profile must still exist and be readable; the
                # comparison of that identity with the report's recorded one
                (self.calibration_identity_probe or installed_calibration_identity)()
            except (OSError, TypeError, json.JSONDecodeError, ValueError) as error:
                raise ValueError("CALIBRATION_REQUIRED") from error
            # Per the owner's amendment the report's own recorded identity is not
            # compared with the tree that is running; the probe above still refuses a missing profile.
            if diagnostic:
                # the Head Search prerequisite is the only thing this scope removes: every non-Head
                # check and its measured values must still be present
                from so101_demo.act.diagnostic_episode_inputs import require_nonhead_gate

                require_nonhead_gate(calibration)
            if pick_place_validation:
                from so101_demo.act.head_search_binding import validate_head_search_binding
                try:
                    validate_head_search_binding(json.loads(runtime_bytes), calibration)
                except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as error:
                    raise ValueError("HEAD_SEARCH_CONFIG_INVALID") from error
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
        if diagnostic:
            self._require_diagnostic_scope(payload, root)
        if container_collection and not payload['qualification_mode']:
            # formal collection: a verified exact-eight qualification report of ANOTHER run of the registered root
            path, digest = payload['qualification_receipt_path'], payload['qualification_receipt_sha256']
            if type(path) is not str or type(digest) is not str:
                raise ValueError('EIGHT_WORKER_QUALIFICATION_REQUIRED')
            if Path(path).is_relative_to(root) or campaign_config['qualification_contract'] is not None:
                raise ValueError('EIGHT_WORKER_QUALIFICATION_MISMATCH')
            try:
                from so101_demo.act.parallel_qualification_verifier import verify_collection_qualification
            except ImportError as error:
                raise ValueError('EIGHT_WORKER_QUALIFICATION_VERIFIER_UNAVAILABLE') from error
            try:
                proof = verify_collection_qualification(Path(path), registered_root=registered,
                    expected_identity=_collection_identity(payload, campaign_config))
            except (OSError, KeyError, TypeError, ValueError) as error:
                raise ValueError('EIGHT_WORKER_QUALIFICATION_EVIDENCE_INVALID') from error
            if (proof.get('status') != 'PASS' or proof['report_sha256'] != digest
                    or proof['formal_split_manifest_sha256'] != payload['manifest_sha256']):
                raise ValueError('EIGHT_WORKER_QUALIFICATION_MISMATCH')
        elif payload['qualification_receipt_path'] is not None or (
                container_collection and payload['qualification_receipt_sha256'] is not None):
            raise ValueError('QUALIFICATION_RECEIPT_UNEXPECTED')
        if container_collection:
            documents = payload['worker_slots']
            if type(documents) is not list or len(documents) != payload['worker_count']:
                raise ValueError('WORKER_SLOT_COUNT_MISMATCH')
            children = []
            for index, document in enumerate(documents):
                if type(document) is not dict or set(document) != set(ActWorkerSlot.__dataclass_fields__):
                    raise ValueError('WORKER_SLOT_SCHEMA')
                slot = ActWorkerSlot(**document)
                if (slot.campaign_id != payload['campaign_id'] or slot.execution_generation != spec.execution_generation
                        or slot.worker_id != f'w{index:02d}'):
                    raise ValueError('WORKER_SLOT_CAMPAIGN_MISMATCH')
                children.append(slot)
            children = tuple(children)
            self.slot_registry.validate(children, launcher=payload['instance_launcher'])
        else:
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
                if self.slot_registry.slots():
                    # A slot has no ROS names to compare with this child's, because its container is isolated. Without
                    # one, the only safe reading of "do not collide" is that no native child starts while a container
                    # campaign still holds a slot. (The native-instance exclusivity rule is separate.)
                    raise ValueError('WORKER_SLOT_RESOURCE_SHARED')
                proposed.register(child)
            children = tuple(ActChildLaunch(**item) for item in payload["children"])
        try:
            current_visible = tuple(self.gpu_inventory_probe())
        except Exception as error:
            raise ValueError("GPU_MAPPING_UNVERIFIABLE") from error
        if current_visible != self.visible_physical_uuids:
            raise ValueError("GPU_MAPPING_DRIFT")
        physical_uuid = resolve_physical_gpu(self.gpu_selector, current_visible)
        if container_collection and physical_uuid != campaign_config['gpu_uuid']:
            raise ValueError('CAMPAIGN_GPU_BINDING_MISMATCH')
        return payload, children, physical_uuid

    # every runtime artifact a diagnostic payload names must be the frozen copy of this role; the
    # second element says whether the closed payload also carries that artifact's digest
    _DIAGNOSTIC_FROZEN_BINDINGS = {
        "source": ("reset_recipe", True), "manifest": ("anchor_scene", True),
        "runtime_config": ("runtime_config", True), "collection_config": ("collection_config", True),
        "calibration_report": ("path_policy", True),
        "proposal": ("contact_proposal", False),
        "activation_receipt": ("contact_activation", False)}

    def _require_diagnostic_scope(self, payload: dict, root: Path) -> dict:
        """Bind one diagnostic episode to its frozen inputs and its explicit mode record.

        The scope names the mode, the manifest names the frozen bytes, and every runtime artifact
        the payload carries must be the frozen copy of its role: a caller cannot keep a valid
        manifest while pointing the run at a different config, report or activation pair. The
        scope's `inputs_sha256` must equal the manifest's frozen digest and its scene and seed must
        equal the frozen anchor, so neither the mode, the inputs nor the initial state can be
        swapped after admission.
        """

        from so101_demo.act.collection_scope import CollectionMode, read_collection_scope
        from so101_demo.act.diagnostic_episode_inputs import (anchor_identity_from_bytes,
                                                         require_nonhead_gate,
                                                         resource_policy_identity,
                                                         verify_frozen_inputs)

        for name in ("collection_scope", "inputs_manifest"):
            path = Path(payload[f"{name}_path"])
            if (not path.is_absolute() or ".." in path.parts
                    or not path.resolve().is_relative_to(root.resolve())):
                raise ValueError("DIAGNOSTIC_SCOPE_UNBOUND")
            self._verify_artifact(str(path), payload[f"{name}_sha256"])
        manifest_path = Path(payload["inputs_manifest_path"])
        try:
            manifest = verify_frozen_inputs(manifest_path)
            frozen_root = manifest_path.parent.resolve()
            frozen = lambda role: (frozen_root / manifest["roles"][role]["path"]).read_bytes()
            for key, (role, digest_declared) in self._DIAGNOSTIC_FROZEN_BINDINGS.items():
                entry = manifest["roles"][role]
                expected = (frozen_root / entry["path"]).resolve()
                if Path(payload[f"{key}_path"]).resolve() != expected:
                    raise ValueError("DIAGNOSTIC_SCOPE_UNBOUND")
                if digest_declared and payload[f"{key}_sha256"] != entry["sha256"]:
                    raise ValueError("DIAGNOSTIC_SCOPE_UNBOUND")
            scope = read_collection_scope(Path(payload["collection_scope_path"]),
                                          expected_mode=CollectionMode.DIAGNOSTIC,
                                          expected_inputs_sha256=manifest["inputs_sha256"])
            # every frozen calibration report carries its own structural contract: all five
            # non-Head checks, complete measurements with matching sample digests. Distinct reports
            # are allowed, so each one is validated instead of relying on equality
            # with the payload's report.
            for role in ("path_policy", "placement_qc", "rgb_skew"):
                require_nonhead_gate(json.loads(frozen(role)))
            # the anchor identity is derived from the frozen anchor bytes, so neither the manifest
            # nor the scope can assert a scene or seed the bytes do not describe
            derived_anchor = anchor_identity_from_bytes(frozen("anchor_scene"))
            anchor = manifest["roles"]["anchor_scene"]["identity"]
            if (not isinstance(anchor, dict)
                    or any(anchor.get(key) != value for key, value in derived_anchor.items())
                    or scope["scene_id"] != derived_anchor["scene_id"]
                    or scope["seed"] != derived_anchor["seed"]
                    or manifest["evidence_root"] != payload["evidence_root"]):
                raise ValueError("DIAGNOSTIC_SCOPE_UNBOUND")
            # the resource policy is re-derived from the frozen config bytes rather than trusted
            # from the manifest's own summary. Per the owner's amendment the manifest's recorded source and config
            # identity is provenance, not a claim about the tree that is running now.
            derived_resource = resource_policy_identity(frozen("runtime_config"),
                                                        frozen("collection_config"))
            if manifest["roles"]["resource_thresholds"]["identity"] != derived_resource:
                raise ValueError("DIAGNOSTIC_SCOPE_UNBOUND")
        except (OSError, KeyError, TypeError, ValueError) as error:
            raise ValueError("DIAGNOSTIC_SCOPE_UNBOUND") from error
        return scope

    def start(self, spec: OperationSpec, *, allow_existing: bool = True) -> AdmittedCampaignContext:
        """Validate everything, acquire resources and persist one context atomically."""
        with self._start_lock:
            payload, children, physical_uuid = self._validate_start(spec)
            if spec.kind == 'act_collection_start' and allow_existing is not False:
                raise ValueError('ACT_CONTAINER_NEW_CAMPAIGN_REQUIRED')
            store = self.arbiter.store
            with store.immediate_transaction():
                repeated = store.repeat(spec.command_id, store.fingerprint(spec))
                if repeated is not None:
                    if not allow_existing:
                        raise ValueError("CAMPAIGN_ALREADY_ADMITTED")
                    row = store._query_one(
                        "SELECT context_json FROM act_campaign_contexts WHERE operation_id=?",
                        (repeated.operation_id,),
                    )
                    if row is None:
                        raise ValueError("CAMPAIGN_CONTEXT_MISSING")
                    return AdmittedCampaignContext.from_dict(json.loads(row[0]))
                if (spec.kind == 'act_collection_start'
                        and spec.execution_generation != store.execution_generation(Domain.VALIDATION)+1):
                    raise ValueError('ACT_CONTAINER_GENERATION_STALE')
            # Reserve the complete child map before taking either durable resource.
            # Another registry user cannot create a collision between validation and
            # persistence, and a failed database/lease step rolls this map back.
            reservation_registry = self.slot_registry if spec.kind == 'act_collection_start' else self.child_registry
            with (reservation_registry.reserve_many(children, launcher=payload['instance_launcher'])
                  if spec.kind == 'act_collection_start' else reservation_registry.reserve_many(children)):
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
                        if spec.kind == 'act_collection_start':
                            if spec.execution_generation != store.execution_generation(Domain.VALIDATION)+1:
                                raise ValueError('ACT_CONTAINER_GENERATION_STALE')
                            store.bump_execution_generation_locked(Domain.VALIDATION)
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
                            registered_evidence_root=payload.get('registered_evidence_root'),
                            campaign_config_path=payload.get('campaign_config_path'),
                            campaign_config_sha256=payload.get('campaign_config_sha256'),
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
            container_collection = context.workload_kind == 'act_collection_start'
            resources = self.slot_registry.slots() if container_collection else self.child_registry.launches()
            launches = tuple(item for item in resources
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
            if container_collection:
                self._verify_container_cleanup(context, launches)
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
                    if container_collection:
                        self.slot_registry.release_many_locked(launches)
                    store._connection.execute(
                        "DELETE FROM gpu_workload_leases WHERE stable_host_id=? AND physical_gpu_uuid=?",
                        (context.stable_host_id, context.physical_gpu_uuid),
                    )
            if outcome.code:
                raise MutationError(outcome.code)
            if not container_collection:
                self.child_registry.release_many(launches)
            return outcome.projection

    @staticmethod
    def _observe_native_exit(record):
        """A native instance's exit read again from the Host now; its ROS graph reading is the one its owner stored.

        The leader, its process group and every process still carrying its instance marker are read live. The graph needs
        the instance's ROS installation, so it is taken from the owner's own stored observation."""
        from so101_demo.runtime.container_campaign.native_stop import observe_native_exit
        from so101_demo.runtime.container_campaign.process_identity import NativeOwnerKey

        stored = record['exit_inspect']
        return observe_native_exit(NativeOwnerKey(**record['owner']), record['launch']['owned_root'],
            graph_probe=lambda: type(stored) is dict and stored.get('graph_clear') is True)

    def _verify_container_cleanup(self, context, slots):
        import sqlite3
        from so101_demo.runtime.container_campaign.registry import ContainerLaunchRegistry
        registry = None
        try:
            root = Path(context.evidence_root)
            registry = ContainerLaunchRegistry(root/'host/launches.sqlite3', create=False)
            by_worker = {slot.worker_id:slot for slot in slots}
            for record in registry.records():
                item = record['launch']
                if item['role'] in ('head','teacher'):
                    if Path(item['owned_root']) != root/'services'/item['role']:
                        raise ValueError('foreign service root')
                elif item['role'] == 'shard':
                    slot = by_worker[item['worker_id']]
                    owned = Path(item['owned_root'])
                    if (owned != root/item['wave_id']/slot.worker_id/f"g{item['launch_generation']}"
                            or not item['wave_id'].startswith('wave-')):
                        raise ValueError('foreign shard scope')
                else:
                    raise ValueError('unknown role')
            if not registry.all_terminated(self.container_inspect, inspect_native=self._observe_native_exit):
                raise ValueError('owned launch stop not proven')
        except (OSError, ValueError, TypeError, KeyError, RuntimeError, sqlite3.Error) as error:
            raise ValueError('ACT_CONTAINER_CLEANUP_NOT_CONFIRMED') from error
        finally:
            if registry is not None:
                registry.close()
