"""Worker-side proxies that carry coordinator, broker and control calls over the batch RPC channel."""

from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import stat
import time
from types import SimpleNamespace

from so101_demo.cli.mujoco_batch.common import CliError, _jsonable, _lease_wire
from so101_demo.parallel_batch.adaptive_pool import (
    WorkerReadinessReceipt,
)
from so101_demo.parallel_batch.broker import BrokerResponse
from so101_demo.parallel_batch.contracts.common import ExecutionKind, ModelOutcome, WorkerState
from so101_demo.parallel_batch.contracts.identity import (
    InferenceRequest,
    LeaseIdentity,
    NormalizedInferenceResponseIdentity,
)
from so101_demo.parallel_batch.contracts.linux_cuda import teacher_execution_bound_s
from so101_demo.parallel_batch.resource_allocation.manifest import (
    ResourceManifest,
    StartGuardAdmission,
)
from so101_demo.parallel_batch.resource_allocation.models import WorkerResources
from so101_demo.parallel_batch.worker_parts.contracts import LeaseGrantPaused
from so101_demo.runtime.parallel_ipc.authority import UnixRpcClient
from so101_demo.runtime.parallel_ipc.broker_transport import BrokerTransport
from so101_demo.runtime.task_stack import OwnedProcessIdentity

_RPC_PAYLOAD_FIELDS = {
    "current_broker": set(),
    "startup_broker": set(),
    "register_worker": {"generation", "recovery_deadline_monotonic_s"},
    "grant_lease": {"generation"},
    "record_recovery": {
        "generation", "succeeded", "fenced", "owned_processes_stopped",
        "controllers_stopped", "readmitted", "recovery_deadline_monotonic_s",
    },
    "replace_resources": {"expected_generation"},
    "heartbeat": set(),
    "heartbeat_teacher": set(),
    "ack_lease": set(),
    "ack_attempt_started": {"gate_summary"},
    "ack_validation_started": {"gate_summary"},
    "begin_finalizing": set(),
    "commit_result": {"location"},
    "commit_validation": {"location"},
}


def _validate_rpc_payload(payload):
    if type(payload) is not dict or type(payload.get("operation")) is not str:
        raise CliError("RPC_PAYLOAD_SCHEMA")
    operation = payload["operation"]
    fields = _RPC_PAYLOAD_FIELDS.get(operation)
    if fields is None or set(payload) != {"operation", *fields}:
        raise CliError("RPC_PAYLOAD_SCHEMA")
    values = {name: payload[name] for name in fields}
    integer_fields = {"generation", "expected_generation"}
    if any(type(values[name]) is not int or values[name] <= 0 for name in fields & integer_fields):
        raise CliError("RPC_PAYLOAD_TYPE")
    if "location" in fields and (
        not isinstance(values["location"], str) or not values["location"]
    ):
        raise CliError("RPC_PAYLOAD_TYPE")
    if "gate_summary" in fields and type(values["gate_summary"]) is not dict:
        raise CliError("RPC_PAYLOAD_TYPE")
    if operation == "register_worker":
        deadline = values["recovery_deadline_monotonic_s"]
        if deadline is not None and (
            isinstance(deadline, bool) or not isinstance(deadline, (int, float))
        ):
            raise CliError("RPC_PAYLOAD_TYPE")
    if operation == "record_recovery":
        if any(type(values[name]) is not bool for name in (
            "succeeded", "fenced", "owned_processes_stopped",
            "controllers_stopped", "readmitted",
        )):
            raise CliError("RPC_PAYLOAD_TYPE")
        deadline = values["recovery_deadline_monotonic_s"]
        if isinstance(deadline, bool) or not isinstance(deadline, (int, float)):
            raise CliError("RPC_PAYLOAD_TYPE")
    return payload


class _CoordinatorRpcProxy:
    """Worker-side authenticated proxy with retry-safe idempotency identities."""

    def __init__(self, socket_path, token_path, *, worker_id, generation, mode, coordinator_epoch):
        self.client = UnixRpcClient(socket_path)
        self.token_path = token_path
        self.token = self.token_path.read_text(encoding="ascii")
        self.worker_id = worker_id
        self.generation = generation
        self.mode = mode
        self.coordinator_epoch = coordinator_epoch
        self._lease = None
        self._sequence = 0

    @property
    def request(self):
        return SimpleNamespace(run_mode=self.mode)

    def _call(self, operation, *, lease=None, request_key=None, **values):
        self._sequence += 1
        key = request_key or f"{operation}-{self.worker_id}-{self.generation}-{self._sequence}"
        message = {
            "schema_version": 1,
            "kind": "coordinator_call",
            "coordinator_epoch": values.pop("coordinator_epoch", None)
            or (lease.coordinator_epoch if lease is not None else self.coordinator_epoch),
            "worker_id": self.worker_id,
            "worker_generation": self.generation,
            "lease": _lease_wire(lease),
            "request_id": f"rpc-{self.worker_id}-{self._sequence}",
            "idempotency_key": key,
            "token": self.token,
            "payload": {"operation": operation, **_jsonable(values)},
        }
        try:
            response = self.client.call(message)
        except (OSError, RuntimeError):
            # One retry with byte-identical request safely covers a dropped ACK.
            response = self.client.call(message)
        return response["payload"]

    @property
    def token_path(self):
        return getattr(self, "_token_path")

    @token_path.setter
    def token_path(self, value):
        self._token_path = Path(value)

    def register_worker(self, worker_id, *, generation, recovery_deadline_monotonic_s=None):
        value = self._call(
            "register_worker",
            generation=generation,
            recovery_deadline_monotonic_s=recovery_deadline_monotonic_s,
        )
        if generation != self.generation:
            self.generation = generation
        return _worker_ack(value)

    def grant_lease(self, worker_id, *, generation, request_key=None):
        value = self._call("grant_lease", generation=generation, request_key=request_key)
        if type(value) is not dict or set(value) != {
            "lease", "lease_grant_paused", "recovery_deadline_monotonic_s",
        }:
            raise CliError("LEASE_GRANT_OUTCOME_SCHEMA")
        lease = value["lease"]
        paused = value["lease_grant_paused"]
        deadline = value["recovery_deadline_monotonic_s"]
        if paused is True:
            if (lease is not None or isinstance(deadline, bool)
                    or not isinstance(deadline, (int, float))):
                raise CliError("LEASE_GRANT_OUTCOME_SCHEMA")
            raise LeaseGrantPaused("BROKER_RECOVERING")
        if paused is not False or deadline is not None:
            raise CliError("LEASE_GRANT_OUTCOME_SCHEMA")
        self._lease = None if lease is None else LeaseIdentity(**lease)
        return self._lease

    def ack_lease(self, lease, *, request_key):
        return _worker_ack(self._call("ack_lease", lease=lease, request_key=request_key))

    def ack_attempt_started(self, lease, *, request_key, gate_summary=None):
        return _worker_ack(self._call(
            "ack_attempt_started", lease=lease, request_key=request_key, gate_summary=gate_summary
        ))

    def ack_validation_started(self, lease, *, request_key, gate_summary=None):
        return _worker_ack(self._call(
            "ack_validation_started", lease=lease, request_key=request_key, gate_summary=gate_summary
        ))

    def begin_finalizing(self, lease, *, request_key):
        return _worker_ack(self._call("begin_finalizing", lease=lease, request_key=request_key))

    def heartbeat(self, lease):
        return LeaseIdentity(**self._call("heartbeat", lease=lease))

    def authorize_local(self, request):
        lease = self._lease
        if lease is None:
            return False
        execution_id = (
            request.attempt_id
            if request.execution_kind is ExecutionKind.ATTEMPT
            else request.validation_id
        )
        expected = (
            lease.batch_id,
            lease.coordinator_epoch,
            lease.worker_id,
            lease.worker_generation,
            lease.point_id,
            lease.lease_generation,
            lease.attempt_id,
        )
        actual = (
            request.batch_id,
            request.coordinator_epoch,
            request.worker_id,
            request.worker_generation,
            request.point_id,
            request.lease_generation,
            execution_id,
        )
        if actual != expected:
            return False
        try:
            acknowledged = self.heartbeat(lease)
        except Exception:
            return False
        return _lease_wire(acknowledged) == _lease_wire(lease)

    def commit_result(self, lease, location, *, request_key):
        value = self._call(
            "commit_result", lease=lease, request_key=request_key, location=location
        )
        from so101_demo.parallel_batch.contracts.common import AttemptStatus
        value["status"] = AttemptStatus(value["status"])
        return value

    def commit_validation(self, lease, location, *, request_key):
        value = self._call(
            "commit_validation", lease=lease, request_key=request_key, location=location
        )
        from so101_demo.parallel_batch.contracts.common import ValidationStatus
        value["status"] = ValidationStatus(value["status"])
        return value

    def record_recovery(self, worker_id, **values):
        generation = values["generation"]
        value = self._call(
            "record_recovery", lease=None, generation=generation, **{
                key: item for key, item in values.items() if key != "generation"
            }
        )
        if generation != self.generation:
            self.generation = generation
        return _worker_ack(value)

    def replace_resources(self, worker_id, *, expected_generation):
        value = self._call(
            "replace_resources",
            lease=None,
            expected_generation=expected_generation,
        )
        return _resource_from_dict(value)

    def _broker_state(self, operation, lease):
        value = self._call(operation, lease=lease)
        fields = {
            "healthy", "broker_generation", "broker_socket_path",
            "recovery_deadline_monotonic_s",
        }
        if type(value) is not dict or set(value) != fields:
            raise CliError("BROKER_AUTHORITY_SCHEMA")
        healthy = value["healthy"]
        generation = value["broker_generation"]
        endpoint = value["broker_socket_path"]
        deadline = value["recovery_deadline_monotonic_s"]
        if type(healthy) is not bool:
            raise CliError("BROKER_AUTHORITY_SCHEMA")
        if healthy:
            if (
                type(generation) is not int
                or generation <= 0
                or not isinstance(endpoint, str)
                or not Path(endpoint).is_absolute()
                or deadline is not None
            ):
                raise CliError("BROKER_AUTHORITY_SCHEMA")
        if not healthy and (
            generation is not None
            or endpoint is not None
            or isinstance(deadline, bool)
            or not isinstance(deadline, (int, float))
        ):
            raise CliError("BROKER_AUTHORITY_SCHEMA")
        return value

    def current_broker(self):
        if self._lease is None:
            raise CliError("BROKER_DISCOVERY_ACTIVE_LEASE_REQUIRED")
        return self._broker_state("current_broker", self._lease)

    def startup_broker(self):
        if self._lease is not None:
            raise CliError("STARTUP_BROKER_ACTIVE_LEASE")
        return self._broker_state("startup_broker", None)


class _WorkerControlProxy:
    """Parent-side authenticated control of one live Worker shutdown path."""

    def __init__(self, socket_path, token_path, *, worker_id, generation,
                 coordinator_epoch, deadline_s, orphan_manifest=None,
                 identity_probe=None, signal_process=os.kill):
        self.socket_path = Path(socket_path)
        self.client = UnixRpcClient(self.socket_path, deadline_s=deadline_s)
        self.token = Path(token_path).read_text(encoding="ascii")
        self.worker_id = worker_id
        self.generation = generation
        self.coordinator_epoch = coordinator_epoch
        self.deadline_s = deadline_s
        self.orphan_manifest = (
            None if orphan_manifest is None else Path(orphan_manifest)
        )
        if identity_probe is None:
            from so101_demo.runtime.task_stack import _linux_process_identity
            identity_probe = _linux_process_identity
        self._identity_probe = identity_probe
        self._signal_process = signal_process
        self._sequence = 0

    def _startup_call(self, operation):
        if operation not in {"readiness", "release_start"}:
            raise CliError("WORKER_CONTROL_OPERATION")
        try:
            socket_info = self.socket_path.lstat()
        except FileNotFoundError:
            return None
        if (
            not stat.S_ISSOCK(socket_info.st_mode)
            or socket_info.st_uid != os.getuid()
            or stat.S_IMODE(socket_info.st_mode) != 0o600
        ):
            raise CliError("WORKER_CONTROL_SOCKET_INVALID")
        self._sequence += 1
        message = {
            "schema_version": 1,
            "kind": "worker_call",
            "coordinator_epoch": self.coordinator_epoch,
            "worker_id": f"{self.worker_id}-control",
            "worker_generation": self.generation,
            "lease": None,
            "request_id": f"control-{self.worker_id}-{self._sequence}",
            "idempotency_key": f"control-{operation}-{self._sequence}",
            "token": self.token,
            "payload": {"operation": operation},
        }
        return self.client.call(message)["payload"]

    def readiness(self):
        value = self._startup_call("readiness")
        if value is None:
            return None
        if type(value) is not dict or set(value) != {"ready", "receipt"}:
            raise CliError("WORKER_READINESS_SCHEMA")
        if value["ready"] is not True or type(value["receipt"]) is not dict:
            return None
        try:
            return WorkerReadinessReceipt(**value["receipt"])
        except (TypeError, ValueError) as error:
            raise CliError("WORKER_READINESS_SCHEMA") from error

    def release_start(self):
        value = self._startup_call("release_start")
        return type(value) is dict and value == {"completed": True}

    def _orphan_identities(self):
        path = self.orphan_manifest
        if path is None or not path.exists():
            return ()
        if (
            path.is_symlink() or not path.is_file()
            or path.stat().st_uid != os.getuid()
            or stat.S_IMODE(path.stat().st_mode) != 0o600
        ):
            raise CliError("WORKER_CHILD_MANIFEST_IDENTITY")
        document = json.loads(path.read_text(encoding="utf-8"))
        if type(document) is not dict or set(document) != {"schema_version", "processes"}:
            raise CliError("WORKER_CHILD_MANIFEST_SCHEMA")
        if document["schema_version"] != 1 or type(document["processes"]) is not list:
            raise CliError("WORKER_CHILD_MANIFEST_SCHEMA")
        identities = []
        for value in document["processes"]:
            if type(value) is not dict or set(value) != {
                "role", "pid", "pgid", "cmdline", "start_time_ticks"
            }:
                raise CliError("WORKER_CHILD_MANIFEST_SCHEMA")
            identity = OwnedProcessIdentity(
                value["role"], value["pid"], value["pgid"],
                tuple(value["cmdline"]), value["start_time_ticks"],
            )
            identities.append(identity)
        return tuple(identities)

    def _recover_orphans(self):
        identities = self._orphan_identities()

        def matches(identity):
            try:
                return self._identity_probe(identity.pid) == (
                    identity.pgid, identity.cmdline, identity.start_time_ticks
                )
            except (OSError, ProcessLookupError, RuntimeError):
                return False

        for identity in identities:
            if not matches(identity):
                return False
        deadline = time.monotonic() + self.deadline_s / 2.0
        for identity in identities:
            try:
                self._signal_process(identity.pid, signal.SIGINT)
            except ProcessLookupError:
                continue
        while identities and time.monotonic() < deadline:
            identities = tuple(
                identity for identity in identities
                if matches(identity)
            )
            if identities:
                time.sleep(0.01)
        for identity in identities:
            if not matches(identity):
                return False
            self._signal_process(identity.pid, signal.SIGTERM)
        deadline = time.monotonic() + self.deadline_s / 2.0
        while identities and time.monotonic() < deadline:
            identities = tuple(identity for identity in identities if matches(identity))
            if identities:
                time.sleep(0.01)
        return not identities

    def call(self, operation):
        if operation not in {
            "stop", "cancel_motion", "confirm_no_controller_goal", "recover"
        }:
            raise CliError("WORKER_CONTROL_OPERATION")
        # A cleanly exited Worker has already run its own finally path.
        if not self.socket_path.exists():
            identities = self._orphan_identities()
            if not identities:
                return True
            return operation == "recover" and self._recover_orphans()
        self._sequence += 1
        message = {
            "schema_version": 1,
            "kind": "worker_call",
            "coordinator_epoch": self.coordinator_epoch,
            "worker_id": f"{self.worker_id}-control",
            "worker_generation": self.generation,
            "lease": None,
            "request_id": f"control-{self.worker_id}-{self._sequence}",
            "idempotency_key": f"control-{operation}-{self._sequence}",
            "token": self.token,
            "payload": {"operation": operation},
        }
        value = self.client.call(message)["payload"]
        return type(value) is dict and value == {"completed": True}


def _worker_ack(value):
    lease = value.get("lease")
    return SimpleNamespace(
        state=WorkerState(value["state"]),
        generation=value["generation"],
        lease=None if lease is None else LeaseIdentity(**lease),
    )


def _resource_from_dict(value):
    paths = {
        "render_context_namespace", "ros_home", "ros_log_dir", "temp_dir",
        "socket_namespace", "socket_path", "worker_root",
    }
    normalized = dict(value)
    for name in paths:
        normalized[name] = Path(normalized[name])
    return WorkerResources(**normalized)


def _resource_manifest_from_dict(value):
    fields = {
        "schema_version", "mode", "backend", "evidence_root",
        "requested_worker_count", "worker_count", "admission",
        "domain_claim_scope", "domain_claims", "process_scan",
        "start_guard", "workers",
    }
    if type(value) is not dict or set(value) != fields:
        raise CliError("RECOVERY_RESOURCE_MANIFEST_SCHEMA")
    admission = value["admission"]
    if type(admission) is not dict or set(admission) != {
        "status", "reason", "checks", "observed_monotonic_s", "gpu_uuid", "cleanup_state",
    }:
        raise CliError("RECOVERY_RESOURCE_MANIFEST_SCHEMA")
    try:
        restored_admission = StartGuardAdmission(
            status=admission["status"],
            reason=admission["reason"],
            checks=dict(admission["checks"]),
            observed_monotonic_s=float(admission["observed_monotonic_s"]),
            gpu_uuid=admission["gpu_uuid"],
            cleanup_state=admission["cleanup_state"],
        )
        return ResourceManifest(
            schema_version=value["schema_version"],
            mode=value["mode"],
            backend=value["backend"],
            evidence_root=Path(value["evidence_root"]),
            requested_worker_count=value["requested_worker_count"],
            worker_count=value["worker_count"],
            admission=restored_admission,
            domain_claim_scope=value["domain_claim_scope"],
            domain_claims=tuple(value["domain_claims"]),
            process_scan=value["process_scan"],
            start_guard=value["start_guard"],
            workers=tuple(_resource_from_dict(item) for item in value["workers"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise CliError("RECOVERY_RESOURCE_MANIFEST_SCHEMA") from error


class _WorkerBrokerProxy:
    def __init__(
        self, coordinator: _CoordinatorRpcProxy, endpoint, resources, config,
        *, broker_generation, broker_generation_consumer=None,
        perception_runner=None,
        client_factory=UnixRpcClient, clock=time.monotonic, sleep=time.sleep,
    ):
        self.coordinator = coordinator
        self._client_factory = client_factory
        self.client = client_factory(
            endpoint,
            deadline_s=teacher_execution_bound_s(config),
            max_frame_bytes=config.broker_max_frame_bytes,
        )
        self.resources = resources
        self.config = config
        if type(broker_generation) is not int or broker_generation <= 0:
            raise CliError("BROKER_GENERATION_AUTHORITY")
        if (
            broker_generation_consumer is not None
            and not callable(broker_generation_consumer)
        ):
            raise CliError("BROKER_GENERATION_CONSUMER")
        self.broker_generation = broker_generation
        self._broker_generation_consumer = broker_generation_consumer
        self.perception_runner = perception_runner
        self._clock = clock
        self._sleep = sleep
        self._sequence = 0

    def cancel_generation(self, worker_id, generation):
        self._refresh_broker(wait_until_healthy=True)
        self._sequence += 1
        key = f"broker-cancel-{worker_id}-{generation}"
        message = self._message(
            key,
            None,
            {
                "operation": "cancel_generation",
                "worker_id": worker_id,
                "worker_generation": generation,
            },
        )
        return self._call(message)["cancelled"]

    def _refresh_broker(self, *, wait_until_healthy, startup=False):
        deadline = self._clock() + self.config.broker_recovery_timeout_s
        while True:
            authority = (
                self.coordinator.startup_broker()
                if startup
                else self.coordinator.current_broker()
            )
            if authority["healthy"]:
                generation = authority["broker_generation"]
                if generation < self.broker_generation:
                    raise CliError("BROKER_GENERATION_ROLLBACK")
                client = self._client_factory(
                    authority["broker_socket_path"],
                    deadline_s=teacher_execution_bound_s(self.config),
                    max_frame_bytes=self.config.broker_max_frame_bytes,
                )
                if self._broker_generation_consumer is not None:
                    self._broker_generation_consumer(generation)
                self.broker_generation = generation
                self.client = client
                return generation
            recovery_deadline = authority["recovery_deadline_monotonic_s"]
            deadline = min(deadline, recovery_deadline)
            if not wait_until_healthy or self._clock() >= deadline:
                raise CliError("BROKER_UNHEALTHY")
            self._sleep(min(0.01, max(0.0, deadline - self._clock())))

    def _message(self, key, lease, payload):
        return {
            "schema_version": 1,
            "kind": "broker_call",
            "coordinator_epoch": self.coordinator.coordinator_epoch,
            "worker_id": self.coordinator.worker_id,
            "worker_generation": self.coordinator.generation,
            "lease": _lease_wire(lease),
            "request_id": key,
            "idempotency_key": key,
            "token": self.coordinator.token,
            "payload": payload,
        }

    def _call(self, message):
        try:
            return self.client.call(message)["payload"]
        except (OSError, RuntimeError):
            return self.client.call(message)["payload"]

    def request_model(
        self,
        lease,
        execution_kind,
        *,
        snapshot,
        start_event_id,
        start_event_type,
        reset_epoch,
    ):
        if self.perception_runner is not None:
            self._refresh_broker(wait_until_healthy=False)
            return self.perception_runner(
                lease,
                execution_kind,
                snapshot,
                lambda model_id, before_send: self._request_one(
                    lease,
                    execution_kind,
                    model_id=model_id,
                    snapshot=snapshot,
                    start_event_id=start_event_id,
                    start_event_type=start_event_type,
                    reset_epoch=reset_epoch,
                    before_send=before_send,
                ),
            )
        return self._request_one(
            lease,
            execution_kind,
            model_id=self.config.yolo_model_id,
            snapshot=snapshot,
            start_event_id=start_event_id,
            start_event_type=start_event_type,
            reset_epoch=reset_epoch,
        )

    def _request_one(
        self, lease, execution_kind, *, model_id, snapshot, start_event_id,
        start_event_type, reset_epoch, before_send=None,
    ):
        request_generation = self._refresh_broker(wait_until_healthy=False)
        self._sequence += 1
        request_id = f"{lease.attempt_id}-{model_id}"
        identity = {
            "request_id": request_id,
            "model_id": model_id,
            "execution_kind": execution_kind,
            "batch_id": lease.batch_id,
            "coordinator_epoch": lease.coordinator_epoch,
            "worker_id": lease.worker_id,
            "worker_generation": lease.worker_generation,
            "point_id": lease.point_id,
            "lease_generation": lease.lease_generation,
            "reset_epoch": reset_epoch,
            "image_timestamp_s": snapshot.source_stamp_ns / 1_000_000_000.0,
            "input_relative_path": str(
                snapshot.path.relative_to(self.resources.worker_root.parent)
            ),
            "input_sha256": snapshot.input_sha256,
            "deadline_s": getattr(
                self.client,
                "deadline_s",
                teacher_execution_bound_s(self.config),
            ),
        }
        if execution_kind is ExecutionKind.ATTEMPT:
            identity["attempt_id"] = lease.attempt_id
        else:
            identity["validation_id"] = lease.attempt_id
        request = InferenceRequest(**identity)
        if before_send is not None:
            before_send(request)
        from so101_demo.runtime.parallel_perception_runtime import Snapshot

        broker_snapshot = Snapshot(
            snapshot.shape,
            snapshot.source_stamp_ns,
            snapshot.source_frame_id,
            start_event_id,
            start_event_type,
            NormalizedInferenceResponseIdentity.from_request(request),
        )
        key = f"broker-{request_id}"
        message = self._message(
            key,
            lease,
            {
                "operation": "infer",
                "request": BrokerTransport.serialize_request(request),
                "snapshot": BrokerTransport.serialize_snapshot(broker_snapshot),
            },
        )
        value = self._call(message)
        expected_model_version = (
            self.config.yolo_weights_sha256
            if model_id == self.config.yolo_model_id
            else self.config.grounded_sam_manifest_sha256
        )
        if (
            value.get("request_id") != request.request_id
            or value.get("model_id") != request.model_id
            or value.get("model_version") != expected_model_version
        ):
            raise CliError("BROKER_RESPONSE_IDENTITY")
        current_generation = self._refresh_broker(wait_until_healthy=False)
        if (
            value.get("broker_generation") != request_generation
            or value.get("broker_generation") != current_generation
        ):
            raise CliError("BROKER_GENERATION_CHANGED")
        return BrokerResponse(
            request,
            value["broker_generation"],
            ModelOutcome(value["outcome"]),
            value["candidate"],
            value["reason"],
            value["queued_monotonic_s"],
            value["queue_deadline_monotonic_s"],
            value["started_monotonic_s"],
            value["inference_deadline_monotonic_s"],
            value["completed_monotonic_s"],
        )
