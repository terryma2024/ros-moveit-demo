"""Broker metrics, the stateless dispatcher and the broker transport."""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import threading
import time

from so101_demo.runtime.parallel_ipc.authority import AuthenticatedUnixServer
from so101_demo.runtime.parallel_ipc.frames import (
    _BROKER_COMPATIBILITY_FIELDS,
    _BROKER_REQUEST_FIELDS,
    IpcError,
    _decode_payload,
    _identifier,
    _positive_int,
    canonical_json,
)


class _BrokerMetrics:
    """Bounded, payload-free timing and concurrency evidence for one Broker."""

    def __init__(self):
        self._lock = threading.RLock()
        self._events = []
        self._next_connection = 0
        self._pending_connections = 0
        self._pending_peak = 0
        self._queue_depth = {}
        self._queue_peak = 0
        self._active = {}
        self._active_peak = {}
        self._request_state = {}
        self._logical_inference_keys = set()
        self._transport_errors = {}
        self._connection_by_inference = {}
        self._phase = {}

    def _record(self, event, *, connection_id=None, message=None, error=None):
        value = {"event": event, "monotonic_s": time.monotonic()}
        if connection_id is not None:
            value["connection_id"] = connection_id
        if type(message) is dict:
            for name in ("request_id", "idempotency_key"):
                if isinstance(message.get(name), str):
                    value[name] = message[name]
        if error is not None:
            value["error"] = str(error)
        if len(self._events) < 10000:
            self._events.append(value)

    def connection_accepted(self):
        with self._lock:
            self._next_connection += 1
            connection_id = self._next_connection
            self._pending_connections += 1
            self._pending_peak = max(
                self._pending_peak, self._pending_connections
            )
            self._record("accepted", connection_id=connection_id)
            self._phase[connection_id] = ("accepted", time.monotonic())
            return connection_id

    def connection_event(self, connection_id, event, message=None, error=None):
        with self._lock:
            self._phase[connection_id] = (event, time.monotonic())
            if event == "received" and type(message) is dict:
                inference = message.get("payload", {}).get("request", {})
                if type(inference) is dict and isinstance(
                    inference.get("request_id"), str
                ):
                    self._connection_by_inference[inference["request_id"]] = (
                        connection_id
                    )
            self._record(
                event,
                connection_id=connection_id,
                message=message,
                error=error,
            )
            if error is not None:
                key = str(error)
                self._transport_errors[key] = self._transport_errors.get(key, 0) + 1

    def connection_closed(self, connection_id):
        with self._lock:
            self._pending_connections -= 1
            self._record("closed", connection_id=connection_id)

    def validated(self, message):
        with self._lock:
            connection_id = self._connection_for_message(message)
            self._phase[connection_id] = ("validated", time.monotonic())
            self._record("validated", connection_id=connection_id, message=message)
            if message.get("payload", {}).get("operation") == "infer":
                inference = message["payload"].get("request", {})
                inference_request_id = (
                    inference.get("request_id")
                    if isinstance(inference.get("request_id"), str)
                    else message["request_id"]
                )
                self._logical_inference_keys.add(inference_request_id)

    def _connection_for_message(self, message):
        payload = message.get("payload", {}) if type(message) is dict else {}
        inference = payload.get("request", {}) if type(payload) is dict else {}
        if type(inference) is dict:
            return self._connection_by_inference.get(inference.get("request_id"))
        return None

    def _request_connection(self, request):
        return self._connection_by_inference.get(request.request_id)

    def queued(self, request):
        with self._lock:
            key = request.request_id
            if key in self._request_state:
                return
            self._request_state[key] = (request.model_id, "QUEUED")
            self._queue_depth[request.model_id] = (
                self._queue_depth.get(request.model_id, 0) + 1
            )
            self._queue_peak = max(
                self._queue_peak, sum(self._queue_depth.values())
            )
            connection_id = self._request_connection(request)
            self._phase[connection_id] = ("queued", time.monotonic())
            self._record(
                "queued", connection_id=connection_id,
                message={"request_id": key},
            )

    def started(self, request, executor_index):
        with self._lock:
            key = request.request_id
            prior = self._request_state.get(key)
            if prior == (request.model_id, "QUEUED"):
                self._queue_depth[request.model_id] -= 1
            self._request_state[key] = (request.model_id, "RUNNING")
            self._active[request.model_id] = self._active.get(request.model_id, 0) + 1
            self._active_peak[request.model_id] = max(
                self._active_peak.get(request.model_id, 0),
                self._active[request.model_id],
            )
            self._record(
                "model_started",
                connection_id=self._request_connection(request),
                message={"request_id": key},
            )
            self._events[-1]["executor_index"] = executor_index

    def model_completed(self, request, outcome):
        with self._lock:
            connection_id = self._request_connection(request)
            self._phase[connection_id] = ("model_completed", time.monotonic())
            self._record(
                "model_completed", connection_id=connection_id,
                message={"request_id": request.request_id},
            )
            self._events[-1]["outcome"] = outcome

    def handler_timeout(self, connection_id, message):
        with self._lock:
            phase, phase_started = self._phase.get(
                connection_id, ("unknown", time.monotonic())
            )
            self._record(
                "handler_timeout", connection_id=connection_id, message=message,
                error="HANDLER_DEADLINE_EXCEEDED",
            )
            self._events[-1].update(
                timeout_phase=phase,
                phase_started_monotonic_s=phase_started,
            )

    def completed(self, request):
        with self._lock:
            key = request.request_id
            prior = self._request_state.pop(key, None)
            if prior == (request.model_id, "QUEUED"):
                self._queue_depth[request.model_id] -= 1
            elif prior == (request.model_id, "RUNNING"):
                self._active[request.model_id] -= 1
            if prior is not None:
                self._record("completed", message={"request_id": key})

    def snapshot(self):
        with self._lock:
            return json.loads(canonical_json({
                "pending_rpc_peak": self._pending_peak,
                "queue_depth_peak": self._queue_peak,
                "model_active_peak": self._active_peak,
                "logical_inference_count": len(self._logical_inference_keys),
                "logical_inference_keys": sorted(self._logical_inference_keys),
                "transport_errors": self._transport_errors,
                "events": self._events,
            }))


def _inference_request(document):
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    from so101_demo.parallel_batch.contracts.identity import InferenceRequest

    if type(document) is not dict:
        raise IpcError("INFERENCE_REQUEST_TYPE")
    try:
        values = dict(document)
        if values.get("execution_kind") is not None:
            values["execution_kind"] = ExecutionKind(values["execution_kind"])
        return InferenceRequest(**values)
    except (KeyError, TypeError, ValueError) as error:
        raise IpcError("INFERENCE_REQUEST_INVALID") from error


def _snapshot(document):
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    from so101_demo.parallel_batch.contracts.identity import NormalizedInferenceResponseIdentity
    from so101_demo.runtime.parallel_perception_runtime import Snapshot

    required = {"shape", "source_stamp_ns", "source_frame_id", "query_class_id"}
    compatibility = {"start_event_id", "start_event_type", "start_identity"}
    if (
        type(document) is not dict
        or not required.issubset(document)
        or not set(document).issubset(required | compatibility)
    ):
        raise IpcError("SNAPSHOT_FIELDS")
    try:
        start_identity = None
        identity = document.get("start_identity")
        if identity is not None:
            if type(identity) is not dict:
                raise ValueError("start identity")
            identity_values = dict(identity)
            identity_values["execution_kind"] = ExecutionKind(
                identity_values["execution_kind"]
            )
            start_identity = NormalizedInferenceResponseIdentity(**identity_values)
        shape = document["shape"]
        if (
            type(shape) is not list
            or len(shape) != 3
            or any(type(value) is not int or value <= 0 for value in shape)
        ):
            raise ValueError("shape")
        if type(document["source_stamp_ns"]) is not int or document["source_stamp_ns"] <= 0:
            raise ValueError("source stamp")
        for name in ("source_frame_id", "query_class_id"):
            if not isinstance(document[name], str) or not document[name]:
                raise ValueError(name)
        for name in ("start_event_id", "start_event_type"):
            if name in document and document[name] is not None and (
                not isinstance(document[name], str) or not document[name]
            ):
                raise ValueError(name)
        return Snapshot(
            shape=tuple(shape),
            source_stamp_ns=document["source_stamp_ns"],
            source_frame_id=document["source_frame_id"],
            query_class_id=document["query_class_id"],
            start_event_id=document.get("start_event_id"),
            start_event_type=document.get("start_event_type"),
            start_identity=start_identity,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise IpcError("SNAPSHOT_INVALID") from error


def _broker_response(response):
    from so101_demo.parallel_batch.broker import BrokerResponse
    from so101_demo.parallel_batch.frozen_models import (
        FROZEN_GROUNDED_SAM_MANIFEST_SHA256,
        FROZEN_YOLO_WEIGHTS_SHA256,
    )
    from so101_demo.runtime.parallel_perception_runtime import GROUNDED_ID, YOLO_ID

    if type(response) is not BrokerResponse:
        raise IpcError("BROKER_RESPONSE_REQUIRED")
    return {
        "request_id": response.request.request_id,
        "model_id": response.request.model_id,
        "model_version": (
            response.candidate.get("weights_sha256")
            if isinstance(response.candidate, dict)
            and isinstance(response.candidate.get("weights_sha256"), str)
            else {
                YOLO_ID: FROZEN_YOLO_WEIGHTS_SHA256,
                GROUNDED_ID: FROZEN_GROUNDED_SAM_MANIFEST_SHA256,
            }[response.request.model_id]
        ),
        "broker_generation": response.broker_generation,
        "outcome": response.outcome.value,
        "candidate": response.candidate,
        "reason": response.reason,
        "queued_monotonic_s": response.queued_monotonic_s,
        "queue_deadline_monotonic_s": response.queue_deadline_monotonic_s,
        "started_monotonic_s": response.started_monotonic_s,
        "inference_deadline_monotonic_s": response.inference_deadline_monotonic_s,
        "completed_monotonic_s": response.completed_monotonic_s,
    }


class _StatelessBrokerDispatcher:
    """Validate one inference envelope locally without scheduling authority."""

    def __init__(self, ipc_root, metrics=None):
        self.ipc_root = Path(ipc_root)
        self._metrics = metrics

    def dispatch(self, message, mutation):
        if type(message) is not dict:
            raise IpcError("REQUEST_FIELDS")
        fields = set(message)
        if (
            not _BROKER_REQUEST_FIELDS.issubset(fields)
            or not fields.issubset(
                _BROKER_REQUEST_FIELDS | _BROKER_COMPATIBILITY_FIELDS
            )
        ):
            raise IpcError("REQUEST_FIELDS")
        if message["schema_version"] != 1 or type(message["schema_version"]) is not int:
            raise IpcError("SCHEMA_VERSION")
        if message["kind"] != "broker_call":
            raise IpcError("UNKNOWN_MESSAGE_KIND")
        _identifier("REQUEST_ID", message["request_id"])
        _identifier("IDEMPOTENCY_KEY", message["idempotency_key"])
        if type(message["payload"]) is not dict:
            raise IpcError("PAYLOAD_TYPE")
        if self._metrics is not None:
            self._metrics.validated(message)
        return mutation(message)


class BrokerTransport:
    """Bounded request/response transport for the stateless Broker seam."""

    def __init__(
        self, *, ipc_root, config, generation, deadline_s,
        runtime_identity=None,
    ):
        self.ipc_root = Path(ipc_root)
        if not self.ipc_root.is_dir() or self.ipc_root.is_symlink():
            raise IpcError("IPC_DIRECTORY_TYPE")
        self.config = config
        self.generation = _positive_int("BROKER_GENERATION", generation)
        self.deadline_s = float(deadline_s)
        if self.deadline_s <= 0:
            raise IpcError("DEADLINE")
        self.max_frame_bytes = _positive_int(
            "FRAME_LIMIT", getattr(config, "broker_max_frame_bytes", None)
        )
        self._runtime_identity = (
            None if runtime_identity is None else canonical_json(runtime_identity)
        )
        self._ready_identity = None
        self._metrics = _BrokerMetrics()

    @property
    def runtime_identity(self):
        return (
            None
            if self._runtime_identity is None
            else _decode_payload(self._runtime_identity)
        )

    def bind_ready_identity(self, receipt) -> str:
        """Freeze the exact durable ready receipt served by health checks."""
        if type(receipt) is not dict:
            raise IpcError("BROKER_READY_IDENTITY")
        encoded = canonical_json(receipt)
        self._ready_identity = encoded
        return hashlib.sha256(encoded).hexdigest()

    def report_health_down(self, event):
        """Validate a local health event; Workers own control-plane reporting."""
        if type(event) is not dict or set(event) != {
            "outcome", "request_id", "reason"
        }:
            raise IpcError("BROKER_HEALTH_DOWN_FIELDS")
        if event["outcome"] not in {
            "INFRA_ERROR", "QUEUE_TIMEOUT", "INFERENCE_TIMEOUT"
        }:
            raise IpcError("BROKER_HEALTH_DOWN_OUTCOME")
        for name in ("request_id", "reason"):
            if not isinstance(event[name], str) or not event[name]:
                raise IpcError("BROKER_HEALTH_DOWN_TYPE")
        return True

    @staticmethod
    def serialize_request(request):
        from so101_demo.parallel_batch.contracts.identity import InferenceRequest

        if type(request) is not InferenceRequest:
            raise IpcError("INFERENCE_REQUEST_REQUIRED")
        value = asdict(request)
        value["execution_kind"] = (
            None if request.execution_kind is None else request.execution_kind.value
        )
        return value

    @staticmethod
    def serialize_snapshot(snapshot):
        from so101_demo.runtime.parallel_perception_runtime import Snapshot

        if type(snapshot) is not Snapshot:
            raise IpcError("SNAPSHOT_REQUIRED")
        value = asdict(snapshot)
        value["shape"] = list(snapshot.shape)
        if snapshot.start_identity is not None:
            value["start_identity"]["execution_kind"] = (
                snapshot.start_identity.execution_kind.value
            )
        return {name: item for name, item in value.items() if item is not None}

    def _handler(self, service, message):
        payload = message.get("payload")
        if type(payload) is not dict:
            raise IpcError("PAYLOAD_TYPE")
        operation = payload.get("operation")
        if operation == "health":
            if set(payload) != {"operation", "ready_sha256"}:
                raise IpcError("BROKER_HEALTH_FIELDS")
            if self._ready_identity is None:
                raise IpcError("BROKER_NOT_READY")
            digest = hashlib.sha256(self._ready_identity).hexdigest()
            if payload["ready_sha256"] != digest:
                raise IpcError("BROKER_READY_IDENTITY_MISMATCH")
            return {
                "ready": _decode_payload(self._ready_identity),
                "ready_sha256": digest,
            }
        if operation == "infer":
            if set(payload) != {"operation", "request", "snapshot"}:
                raise IpcError("BROKER_INFER_FIELDS")
            request = _inference_request(payload["request"])
            snapshot = _snapshot(payload["snapshot"])
            submission = service.submit(request, snapshot)
            response = submission.response
            if response is None and submission.accepted:
                response = service.wait_response(
                    request, timeout_s=self.deadline_s
                )
            if response is None:
                raise IpcError("BROKER_RESPONSE_PENDING")
            return _broker_response(response)
        if operation == "cancel_generation":
            if set(payload) != {"operation", "worker_id", "worker_generation"}:
                raise IpcError("BROKER_CANCEL_FIELDS")
            service.broker.cancel_generation(
                _identifier("WORKER_ID", payload["worker_id"]),
                _positive_int("GENERATION", payload["worker_generation"]),
            )
            return {"cancelled": True}
        raise IpcError("UNKNOWN_BROKER_OPERATION")

    def server(self, service, *, endpoint):
        authority = _StatelessBrokerDispatcher(self.ipc_root, self._metrics)
        set_metrics = getattr(service, "set_metrics", None)
        if callable(set_metrics):
            set_metrics(self._metrics)
        return AuthenticatedUnixServer(
            endpoint,
            authority,
            lambda message: self._handler(service, message),
            deadline_s=self.deadline_s,
            max_frame_bytes=self.max_frame_bytes,
            max_concurrent_connections=(self.runtime_identity or {}).get(
                "connection_handler_count", 1
            ),
            metrics=self._metrics,
        )

    def metrics_snapshot(self):
        return self._metrics.snapshot()

    def persist_metrics_summary(self):
        """Atomically retain payload-free Broker phase evidence."""
        document = {
            "schema_version": 1,
            "kind": "broker_concurrency_summary",
            **self.metrics_snapshot(),
        }
        payload = canonical_json(document)
        temporary = self.ipc_root / (
            f".broker-concurrency-summary-{os.getpid()}-{threading.get_ident()}.tmp"
        )
        descriptor = os.open(
            temporary,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
        )
        try:
            os.write(descriptor, payload)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        target = self.ipc_root / "broker-concurrency-summary.json"
        os.replace(temporary, target)
        parent = os.open(self.ipc_root, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
        return target

    def serve(self, runtime, *, endpoint):
        from so101_demo.runtime.parallel_perception_runtime import PerceptionService

        service = PerceptionService(
            runtime,
            self.config,
            generation=self.generation,
            health_down=self.report_health_down,
            queue_capacity_per_model=(self.runtime_identity or {}).get(
                "queue_capacity_per_model"
            ),
        )
        server = None
        try:
            service.start()
            server = self.server(service, endpoint=endpoint)
            server.serve_forever()
        finally:
            if server is not None:
                server.stop_accept()
            service_closed = service.close(timeout_s=self.deadline_s)
            handlers_closed = (
                True
                if server is None
                else server.wait_handlers(timeout_s=self.deadline_s)
            )
            if server is not None:
                server.close()
            summary_path = self.persist_metrics_summary()
            print(summary_path.read_text(encoding="utf-8"), file=os.sys.stderr, flush=True)
            if not service_closed or not handlers_closed:
                raise IpcError("BROKER_SHUTDOWN_TIMEOUT")


def build_broker_transport(runtime_spec):
    """Load the mounted stateless Broker runtime/config contract."""

    from so101_demo.parallel_batch.contracts.macos_single_worker import (
        load_runtime_config_any_schema,
    )

    runtime_spec = Path(runtime_spec)
    try:
        raw = runtime_spec.read_bytes()
        document = _decode_payload(raw)
    except (OSError, IpcError) as error:
        raise IpcError("BROKER_SPEC_INVALID") from error
    fields = {
        "schema_version",
        "kind",
        "batch_id",
        "coordinator_epoch",
        "broker_generation",
        "run_mode",
        "image_id",
        "yolo_weights_sha256",
        "grounded_manifest_sha256",
        "config_path",
        "request_deadline_s",
        "max_frame_bytes",
    }
    adaptive_fields = {
        "queue_capacity_per_model",
        "connection_handler_count",
        "yolo_executor_count",
        "grounded_sam_executor_count",
    }
    if (
        set(document) not in (fields, fields | adaptive_fields)
        or type(document["schema_version"]) is not int
        or document["schema_version"] != 1
        or document["kind"] != "so101_parallel_broker_runtime"
    ):
        raise IpcError("BROKER_SPEC_FIELDS")
    _identifier("BATCH_ID", document["batch_id"])
    _positive_int("EPOCH", document["coordinator_epoch"])
    generation = _positive_int("BROKER_GENERATION", document["broker_generation"])
    if adaptive_fields.issubset(document):
        capacity = _positive_int(
            "QUEUE_CAPACITY", document["queue_capacity_per_model"]
        )
        if capacity > 16:
            raise IpcError("BROKER_QUEUE_CAPACITY")
        handlers = _positive_int(
            "CONNECTION_HANDLER_COUNT", document["connection_handler_count"]
        )
        if handlers > 16:
            raise IpcError("BROKER_CONNECTION_HANDLER_COUNT")
        yolo_executors = _positive_int(
            "YOLO_EXECUTOR_COUNT", document["yolo_executor_count"]
        )
        if yolo_executors not in {1, 2, 4}:
            raise IpcError("BROKER_YOLO_EXECUTOR_COUNT")
        if (
            document["grounded_sam_executor_count"] != 1
            or type(document["grounded_sam_executor_count"]) is not int
        ):
            raise IpcError("BROKER_GROUNDED_SAM_EXECUTOR_COUNT")
    if document["run_mode"] not in {"plan_only", "execute"}:
        raise IpcError("BROKER_RUN_MODE")
    if (
        not isinstance(document["image_id"], str)
        or len(document["image_id"]) != 71
        or not document["image_id"].startswith("sha256:")
        or any(
            character not in "0123456789abcdef"
            for character in document["image_id"][7:]
        )
    ):
        raise IpcError("BROKER_IMAGE_ID")
    for name in ("yolo_weights_sha256", "grounded_manifest_sha256"):
        value = document[name]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise IpcError("BROKER_MODEL_HASH")
    config_path = Path(document["config_path"])
    if not config_path.is_absolute():
        raise IpcError("BROKER_SPEC_PATH")
    ipc_root = config_path.parent
    config = load_runtime_config_any_schema(config_path)
    if (
        document["yolo_weights_sha256"] != config.yolo_weights_sha256
        or document["grounded_manifest_sha256"]
        != config.grounded_sam_manifest_sha256
    ):
        raise IpcError("BROKER_MODEL_HASH_MISMATCH")
    max_frame_bytes = _positive_int("FRAME_LIMIT", document["max_frame_bytes"])
    if max_frame_bytes != config.broker_max_frame_bytes:
        raise IpcError("BROKER_FRAME_LIMIT_MISMATCH")
    deadline = document["request_deadline_s"]
    if (
        isinstance(deadline, bool)
        or not isinstance(deadline, (int, float))
        or deadline <= 0
        or deadline > config.batch_hard_timeout_s
    ):
        raise IpcError("BROKER_DEADLINE")
    if adaptive_fields.issubset(document):
        expected_deadline = max(
            config.yolo_queue_timeout_s + config.yolo_inference_timeout_s,
            config.grounded_sam_queue_timeout_s
            + config.grounded_sam_inference_timeout_s,
        ) + config.heartbeat_timeout_s
        if (
            capacity != handlers
            or yolo_executors > handlers
            or float(deadline) != expected_deadline
        ):
            raise IpcError("BROKER_ADAPTIVE_CONCURRENCY")
    return BrokerTransport(
        ipc_root=ipc_root,
        config=config,
        generation=generation,
        deadline_s=float(deadline),
        runtime_identity=document,
    )
