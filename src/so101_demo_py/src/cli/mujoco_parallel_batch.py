"""User entry point for an isolated, dynamically leased MuJoCo validation batch."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from typing import Callable, Mapping

import yaml

from so101_demo.parallel_batch.artifacts import (
    AttemptWorkspace,
    SealedResultAdapter,
    ValidationWorkspace,
    write_recovery_receipt,
)
from so101_demo.parallel_batch.broker import BrokerResponse
from so101_demo.parallel_batch.contracts import (
    AttemptIdentity,
    BatchRequest,
    BatchSummary,
    ContractError,
    LeaseIdentity,
    ParallelRuntimeConfig,
    RunMode,
    ValidationIdentity,
    WorkerState,
    ExecutionKind,
    InferenceRequest,
    ModelOutcome,
    NormalizedInferenceResponseIdentity,
    load_parallel_runtime_config,
)
from so101_demo.parallel_batch.coordinator import BatchCoordinator
from so101_demo.parallel_batch.journal import CoordinatorJournal
from so101_demo.parallel_batch.resources import WorkerResourceAllocator, WorkerResources
from so101_demo.parallel_batch.worker import ParallelWorker
from so101_demo.runtime.parallel_ipc import (
    AuthenticatedUnixServer,
    BrokerTransport,
    UnixRpcClient,
    WorkerTokenAuthority,
    _inference_request,
    _snapshot,
)
from so101_demo.runtime.parallel_processes import ProcessSupervisor
from so101_demo.runtime.parallel_ros_runtime import (
    ParallelRosRuntimePorts as _ConcreteRosWorkerRuntimePorts,
)
from so101_demo.runtime.parallel_worker_runtime import build_worker_runtime


_CATALOG_SHA256 = "c74915477bfea979285c605a199cf524462a57d9f44b0b5f38a6ae935f298dc5"
_BROKER_IMAGE = "so101-parallel-perception:ros-jazzy-torch2.13.0-cu130-v1"


class CliError(RuntimeError):
    """Startup or batch composition failed closed."""


class _Parser(argparse.ArgumentParser):
    def error(self, message):
        raise CliError(f"ARGUMENT_ERROR: {message}")


@dataclass(frozen=True, slots=True)
class PreparedBatch:
    request: BatchRequest
    config: ParallelRuntimeConfig
    config_path: Path
    points_path: Path
    catalog: Mapping[str, Mapping[str, object]]
    catalog_sha256: str
    selection_sha256: str
    broker_image: str
    yolo_weights: Path
    yolo_weights_sha256: str
    grounded_root: Path
    grounded_manifest_sha256: str
    provenance: Mapping[str, object]
    manifest: Mapping[str, object]


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="so101_parallel_batch")
    parser.add_argument("--points", type=Path, required=True)
    parser.add_argument("--point-id", action="append", default=[])
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--batch-id", required=True)
    parser.add_argument("--worker-count", required=True)
    parser.add_argument("--max-points-per-worker", required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--broker-image", required=True)
    parser.add_argument("--yolo-weights", type=Path, required=True)
    parser.add_argument("--yolo-weights-sha256", required=True)
    parser.add_argument("--grounded-root", type=Path, required=True)
    parser.add_argument("--grounded-manifest-sha256", required=True)
    parser.add_argument("--run-mode", required=True)
    return parser


def _integer(name: str, value: str) -> int:
    if not isinstance(value, str) or not value.isascii() or not value.isdecimal():
        raise CliError(f"MALFORMED_INTEGER: {name}")
    result = int(value)
    if result <= 0:
        raise CliError(f"MALFORMED_INTEGER: {name}")
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
    except OSError as error:
        raise CliError(f"PROVENANCE_READ_FAILED: {path}") from error
    return digest.hexdigest()


def _absolute(name: str, path: Path) -> Path:
    raw = str(path)
    if not path.is_absolute() or "\0" in raw or any(part in {".", ".."} for part in raw.split("/")):
        raise CliError(f"ABSOLUTE_PATH_REQUIRED: {name}")
    return path


def _catalog(path: Path) -> tuple[dict[str, Mapping[str, object]], str]:
    path = path.resolve()
    digest = _sha256(path)
    if digest != _CATALOG_SHA256:
        raise CliError("POINT_CATALOG_HASH_MISMATCH")
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as error:
        raise CliError("POINT_CATALOG_INVALID") from error
    if type(document) is not dict or set(document) != {"schema_version", "points"}:
        raise CliError("POINT_CATALOG_SCHEMA")
    if type(document["schema_version"]) is not int or document["schema_version"] != 1:
        raise CliError("POINT_CATALOG_SCHEMA")
    points = document["points"]
    if not isinstance(points, list) or len(points) != 20:
        raise CliError("POINT_CATALOG_SCHEMA")
    catalog = {}
    for point in points:
        if type(point) is not dict or set(point) != {"id", "label", "cup_position_world_m"}:
            raise CliError("POINT_CATALOG_SCHEMA")
        point_id = point["id"]
        if not isinstance(point_id, str) or not point_id or point_id in catalog:
            raise CliError("POINT_CATALOG_DUPLICATE")
        catalog[point_id] = point
    return catalog, digest


def verify_provenance(spec: Mapping[str, object]) -> Mapping[str, object]:
    """Verify exact local model and image inputs before creating the batch root."""

    yolo = _absolute("yolo_weights", Path(spec["yolo_weights"]))
    grounded = _absolute("grounded_root", Path(spec["grounded_root"]))
    if not yolo.is_file() or yolo.is_symlink():
        raise CliError("PROVENANCE_YOLO_PATH")
    if not grounded.is_dir() or grounded.is_symlink():
        raise CliError("PROVENANCE_GROUNDED_PATH")
    manifest = grounded / "manifest.json"
    if not manifest.is_file() or manifest.is_symlink():
        raise CliError("PROVENANCE_GROUNDED_MANIFEST")
    if _sha256(yolo) != spec["yolo_weights_sha256"]:
        raise CliError("PROVENANCE_YOLO_HASH")
    if _sha256(manifest) != spec["grounded_manifest_sha256"]:
        raise CliError("PROVENANCE_GROUNDED_HASH")
    image = spec["broker_image"]
    if image != _BROKER_IMAGE:
        raise CliError("PROVENANCE_BROKER_IMAGE")
    try:
        source_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5.0,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError) as error:
        raise CliError("PROVENANCE_SOURCE_COMMIT") from error
    if len(source_commit) != 40 or any(character not in "0123456789abcdef" for character in source_commit):
        raise CliError("PROVENANCE_SOURCE_COMMIT")
    try:
        from so101_demo.cli.parallel_perception_broker import image_record

        immutable_image = image_record(image)
    except Exception as error:
        raise CliError("PROVENANCE_BROKER_IMAGE_READBACK") from error
    return {
        "source_commit": source_commit,
        "catalog_sha256": spec["catalog_sha256"],
        "yolo_weights_sha256": spec["yolo_weights_sha256"],
        "grounded_manifest_sha256": spec["grounded_manifest_sha256"],
        "broker_image": image,
        **immutable_image,
    }


def prepare_batch(argv=None, *, provenance_verifier=verify_provenance) -> PreparedBatch:
    options = build_parser().parse_args(argv)
    evidence_root = _absolute("evidence_root", options.evidence_root)
    if evidence_root.exists() or evidence_root.is_symlink():
        raise CliError("DUPLICATE_BATCH_EVIDENCE_ROOT")
    try:
        mode = RunMode(options.run_mode)
    except ValueError as error:
        raise CliError("UNKNOWN_RUN_MODE") from error
    worker_count = _integer("worker_count", options.worker_count)
    max_points = _integer("max_points_per_worker", options.max_points_per_worker)
    catalog, catalog_sha = _catalog(options.points)
    supplied = tuple(options.point_id)
    if len(supplied) != len(set(supplied)):
        raise CliError("DUPLICATE_POINT_ID")
    unknown = set(supplied) - set(catalog)
    if unknown:
        raise CliError(f"UNKNOWN_POINT_ID: {sorted(unknown)!r}")
    selected = tuple(point_id for point_id in catalog if not supplied or point_id in supplied)
    selection_payload = json.dumps(list(selected), separators=(",", ":")).encode("utf-8")
    selection_sha = hashlib.sha256(selection_payload).hexdigest()
    config_path = options.config.resolve()
    config = load_parallel_runtime_config(config_path)
    if options.yolo_weights_sha256 != config.yolo_weights_sha256:
        raise CliError("YOLO_HASH_MISMATCH")
    if options.grounded_manifest_sha256 != config.grounded_sam_manifest_sha256:
        raise CliError("GROUNDED_HASH_MISMATCH")
    if options.broker_image != _BROKER_IMAGE:
        raise CliError("BROKER_IMAGE_MISMATCH")
    try:
        request = BatchRequest(
            options.batch_id,
            mode,
            selected,
            worker_count,
            max_points,
            evidence_root,
        )
    except ContractError as error:
        message = str(error)
        if "INSUFFICIENT_CAPACITY" in message:
            raise CliError(f"INSUFFICIENT_CAPACITY: {message}") from error
        raise CliError(message) from error
    inputs = {
        "points": options.points,
        "catalog_sha256": catalog_sha,
        "broker_image": options.broker_image,
        "yolo_weights": options.yolo_weights,
        "yolo_weights_sha256": options.yolo_weights_sha256,
        "grounded_root": options.grounded_root,
        "grounded_manifest_sha256": options.grounded_manifest_sha256,
    }
    try:
        provenance = provenance_verifier(inputs)
    except CliError:
        raise
    except Exception as error:
        raise CliError("PROVENANCE_VERIFICATION_FAILED") from error
    if not isinstance(provenance, Mapping) or not provenance:
        raise CliError("PROVENANCE_VERIFICATION_FAILED")
    manifest = {
        "schema_version": 1,
        "batch_id": request.batch_id,
        "run_mode": request.run_mode.value,
        "selected_point_ids": list(selected),
        "selection_sha256": selection_sha,
        "catalog_sha256": catalog_sha,
        "worker_count": worker_count,
        "max_points_per_worker": max_points,
        "evidence_root": str(evidence_root),
        "provenance": dict(provenance),
    }
    return PreparedBatch(
        request,
        config,
        config_path,
        options.points.resolve(),
        catalog,
        catalog_sha,
        selection_sha,
        options.broker_image,
        options.yolo_weights,
        options.yolo_weights_sha256,
        options.grounded_root,
        options.grounded_manifest_sha256,
        dict(provenance),
        manifest,
    )


def _identity(lease, mode):
    value = {
        "batch_id": lease.batch_id,
        "coordinator_epoch": lease.coordinator_epoch,
        "worker_id": lease.worker_id,
        "worker_generation": lease.worker_generation,
        "point_id": lease.point_id,
        "lease_generation": lease.lease_generation,
    }
    if mode is RunMode.EXECUTE:
        return AttemptIdentity(**value, attempt_id=lease.attempt_id)
    return ValidationIdentity(**value, validation_id=lease.attempt_id)


class _ArtifactResults:
    """Produce reviewed Task 4 artifacts for the Worker and verify recovery receipts."""

    def __init__(self, worker_roots: Mapping[str, Path], mode: RunMode):
        self.worker_roots = {key: Path(value) for key, value in worker_roots.items()}
        self.mode = mode
        self._workspaces = {}

    @staticmethod
    def _key(lease):
        return tuple(getattr(lease, name) for name in (
            "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
            "point_id", "attempt_id", "lease_generation",
        ))

    def reserve_workspace(self, lease, reset_receipt):
        if self.mode is RunMode.DRY_RUN:
            raise CliError("DRY_RUN_WORKSPACE_RESERVATION")
        reset_epoch = getattr(reset_receipt, "reset_epoch", None)
        completed = getattr(reset_receipt, "reset_completed_monotonic_s", None)
        session = getattr(reset_receipt, "simulation_session_id", None)
        simulation_time = getattr(reset_receipt, "simulation_time_s", None)
        if (not isinstance(reset_epoch, str) or not reset_epoch
                or isinstance(completed, bool) or not isinstance(completed, (int, float))
                or not isinstance(session, str) or not session
                or isinstance(simulation_time, bool)
                or not isinstance(simulation_time, (int, float))):
            raise CliError("WORKSPACE_RESET_RECEIPT")
        identity = _identity(lease, self.mode)
        cls = AttemptWorkspace if self.mode is RunMode.EXECUTE else ValidationWorkspace
        workspace = cls.create(
            self.worker_roots[lease.worker_id], identity,
            reset_epoch=reset_epoch,
            source_stamp={
                "reset_completed_monotonic_s": float(completed),
                "simulation_session_id": session,
                "simulation_time_s": float(simulation_time),
            },
            run_mode=self.mode,
        )
        key = self._key(lease)
        prior = self._workspaces.setdefault(key, workspace)
        if prior.path != workspace.path or prior._metadata != workspace._metadata:
            raise CliError("WORKSPACE_IDENTITY_MISMATCH")
        return True

    def workspace(self, lease):
        try:
            return self._workspaces[self._key(lease)]
        except KeyError as error:
            raise CliError("WORKSPACE_NOT_RESERVED") from error

    def _seal(self, lease, decision):
        identity = _identity(lease, self.mode)
        if self.mode is RunMode.DRY_RUN:
            workspace = ValidationWorkspace.create(
                self.worker_roots[lease.worker_id], identity,
                reset_epoch="scheduler-only",
                source_stamp={"coordinator_epoch": lease.coordinator_epoch},
                run_mode=self.mode,
            )
        else:
            try:
                workspace = self._workspaces[self._key(lease)]
            except KeyError as error:
                raise CliError("WORKSPACE_NOT_RESERVED") from error
        name = "attempt-result.json" if self.mode is RunMode.EXECUTE else "validation-result.json"
        workspace.write_json(
            name,
            {
                "status": decision.status.value,
                "reason": decision.reason,
                "physical_action_proven_absent": decision.physical_action_proven_absent,
            },
        )
        return str(workspace.seal().path)

    def seal_attempt(self, lease, decision):
        if self.mode is not RunMode.EXECUTE:
            raise CliError("ARTIFACT_MODE")
        return self._seal(lease, decision)

    def seal_validation(self, lease, decision):
        if self.mode is RunMode.EXECUTE:
            raise CliError("ARTIFACT_MODE")
        return self._seal(lease, decision)

    def write_recovery_receipt(self, lease, *, succeeded, generation, **_kwargs):
        if generation != lease.worker_generation:
            raise CliError("RECOVERY_GENERATION")
        return write_recovery_receipt(
            self.worker_roots[lease.worker_id], _identity(lease, self.mode), succeeded=succeeded
        )

    def verify_recovery_receipt(self, location, lease, *, succeeded, generation, **_kwargs):
        try:
            path = Path(location)
            path.relative_to(self.worker_roots[lease.worker_id])
            document = json.loads(path.read_text(encoding="utf-8"))
            return (
                path.is_file()
                and not path.is_symlink()
                and document["identity"] == asdict(_identity(lease, self.mode))
                and document["succeeded"] is succeeded
                and generation == lease.worker_generation
            )
        except (OSError, ValueError, KeyError, TypeError):
            return False


class RosWorkerRuntimePorts(_ConcreteRosWorkerRuntimePorts):
    """Production F20 ports with an explicit process-free test injection seam."""

    def __init__(
        self,
        resources,
        *,
        catalog=None,
        config=None,
        mode=RunMode.PLAN_ONLY,
        side_effects: Mapping[str, Callable] | None = None,
        workspace_provider=None,
        authorize=None,
        broker_generation=None,
    ):
        supplied = dict(side_effects or {})
        unknown = set(supplied) - self.REQUIRED
        if unknown:
            raise CliError(f"UNKNOWN_RUNTIME_PORT: {sorted(unknown)!r}")
        super().__init__(
            resources,
            catalog={} if catalog is None else catalog,
            config=config,
            mode=mode,
            broker_generation=broker_generation,
            dependencies={
                "workspace_provider": workspace_provider,
                "authorize": authorize,
            },
        )
        self.side_effects = supplied

    def kwargs(self):
        concrete = super().kwargs()
        concrete.update(self.side_effects)
        return concrete


def _jsonable(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dataclass_fields__"):
        return _jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value


def _lease_wire(lease):
    if lease is None:
        return None
    return {
        name: getattr(lease, name)
        for name in (
            "batch_id", "coordinator_epoch", "worker_id", "worker_generation",
            "point_id", "attempt_id", "lease_generation",
        )
    }


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
        self._lease = None if value is None else LeaseIdentity(**value)
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
        from so101_demo.parallel_batch.contracts import AttemptStatus
        value["status"] = AttemptStatus(value["status"])
        return value

    def commit_validation(self, lease, location, *, request_key):
        value = self._call(
            "commit_validation", lease=lease, request_key=request_key, location=location
        )
        from so101_demo.parallel_batch.contracts import ValidationStatus
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


class _WorkerBrokerProxy:
    def __init__(
        self, coordinator: _CoordinatorRpcProxy, endpoint, resources, config,
        *, broker_generation, perception_runner=None,
    ):
        self.coordinator = coordinator
        self.client = UnixRpcClient(
            endpoint,
            deadline_s=config.executing_hard_timeout_s,
            max_frame_bytes=config.broker_max_frame_bytes,
        )
        self.resources = resources
        self.config = config
        if type(broker_generation) is not int or broker_generation <= 0:
            raise CliError("BROKER_GENERATION_AUTHORITY")
        self.broker_generation = broker_generation
        self.perception_runner = perception_runner
        self._sequence = 0

    def cancel_generation(self, worker_id, generation):
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
        if value.get("broker_generation") != self.broker_generation:
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


def _build_worker_from_spec(path, *, runtime_side_effects=None):
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    if type(document) is not dict or set(document) != {
        "schema_version", "batch_id", "run_mode", "config_path", "socket_path",
        "token_path", "coordinator_epoch", "resources", "broker_socket_path",
        "broker_generation", "catalog",
    } or document["schema_version"] != 1:
        raise CliError("WORKER_SPEC_INVALID")
    resources = _resource_from_dict(document["resources"])
    mode = RunMode(document["run_mode"])
    config = load_parallel_runtime_config(Path(document["config_path"]))
    coordinator = _CoordinatorRpcProxy(
        document["socket_path"],
        document["token_path"],
        worker_id=resources.worker_id,
        generation=resources.generation,
        mode=mode,
        coordinator_epoch=document["coordinator_epoch"],
    )
    results = _ArtifactResults({resources.worker_id: resources.worker_root}, mode)
    runtime_kwargs = {}
    runtime_ports = None
    if mode is not RunMode.DRY_RUN:
        runtime_ports = RosWorkerRuntimePorts(
            resources,
            catalog=document["catalog"],
            config=config,
            mode=mode,
            side_effects=runtime_side_effects,
            workspace_provider=results.workspace,
            authorize=coordinator.authorize_local,
            broker_generation=document["broker_generation"],
        )
        runtime_kwargs = runtime_ports.kwargs()
        runtime_kwargs["reserve_workspace"] = results.reserve_workspace
        # A stable slot replacement is represented by the next private Worker
        # spec generation; it never reallocates ROS domains or directories.
        runtime_kwargs["replace_resources"] = coordinator.replace_resources
    runtime = build_worker_runtime(resources, mode, **runtime_kwargs)
    worker = ParallelWorker({
        "coordinator": coordinator,
        "broker": _WorkerBrokerProxy(
            coordinator, document["broker_socket_path"], resources, config,
            broker_generation=document["broker_generation"],
            perception_runner=runtime_ports.run_perception_chain,
        ) if mode is not RunMode.DRY_RUN else SimpleNamespace(
            request_model=lambda *_args, **_kwargs: (_ for _ in ()).throw(
                CliError("DRY_RUN_BROKER_FORBIDDEN")
            ),
            cancel_generation=lambda *_args: True,
        ),
        "runtime": runtime,
        "results": results,
        "clock": time.monotonic,
        "config": config,
        "worker_id": resources.worker_id,
        "generation": resources.generation,
    })
    return worker, runtime


def _run_worker_spec(path, *, runtime_side_effects=None):
    worker, runtime = _build_worker_from_spec(
        path, runtime_side_effects=runtime_side_effects
    )
    try:
        results = worker.run()
        return int(
            not results
            or any(
                result.stopped_reason not in {"POINT_TERMINAL", "NO_POINT"}
                for result in results
            )
        )
    finally:
        runtime.shutdown_owned()


class ProductionBatchComposition:
    """Connect reviewed batch components; no result is synthesized by this layer."""

    def __init__(
        self,
        spec: PreparedBatch,
        *,
        resource_probe=None,
        claim_root: Path | None = None,
        runtime_side_effects_factory: Callable[[object], Mapping[str, Callable]] | None = None,
        broker_request_model=None,
        worker_launcher=None,
        supervisor=None,
        broker_command_builder=None,
    ):
        self.spec = spec
        self.allocator = WorkerResourceAllocator(
            spec.config,
            spec.request.evidence_root,
            probe=resource_probe,
            claim_root=claim_root,
            batch_id=spec.request.batch_id,
        )
        self.resource_manifest = self.allocator.allocate(spec.request.worker_count)
        self.allocator.write_manifest()
        worker_roots = {
            worker.worker_id: worker.worker_root for worker in self.resource_manifest.workers
        }
        self.result_verifier = SealedResultAdapter(worker_roots, spec.request.run_mode)
        self.journal = CoordinatorJournal.create(
            spec.request.evidence_root / "coordinator", spec.request.batch_id
        )
        self.coordinator = BatchCoordinator(
            self.journal,
            spec.request,
            config=spec.config,
            result_port=self.result_verifier,
        )
        self.results = _ArtifactResults(worker_roots, spec.request.run_mode)
        if broker_request_model is not None:
            raise CliError("IN_PROCESS_BROKER_FORBIDDEN")
        self.supervisor = supervisor or ProcessSupervisor(
            spec.request.batch_id,
            manifest_path=spec.request.evidence_root / "owned-processes.json",
        )
        self.authority = WorkerTokenAuthority(
            spec.request.evidence_root,
            coordinator_epoch=self.journal.coordinator_epoch,
        )
        self._broker_command_builder = broker_command_builder
        self.broker_spec_path = None
        self.broker_authority_server = None
        self.broker_socket_path = self.authority.ipc_root / "perception.sock"
        if spec.request.run_mode is not RunMode.DRY_RUN:
            broker_token_path = self.authority.issue("broker", 1)
            broker_authority_path = self.authority.ipc_root / "broker-authority.sock"
            self.broker_authority_server = AuthenticatedUnixServer(
                broker_authority_path,
                self.authority,
                self._coordinator_handler,
                deadline_s=spec.config.heartbeat_timeout_s,
                max_frame_bytes=spec.config.broker_max_frame_bytes,
            )
            config_copy = self.authority.ipc_root / "runtime-config.yaml"
            _write_bytes(config_copy, spec.config_path.read_bytes())
            self.broker_spec_path = self.authority.ipc_root / "broker-spec.json"
            _write_json(
                self.broker_spec_path,
                {
                    "schema_version": 1,
                    "kind": "so101_parallel_broker_runtime",
                    "batch_id": spec.request.batch_id,
                    "coordinator_epoch": self.journal.coordinator_epoch,
                    "broker_generation": 1,
                    "config_path": "/runtime/runtime-config.yaml",
                    "authority_endpoint": "/runtime/broker-authority.sock",
                    "authority_token_path": f"/runtime/{broker_token_path.name}",
                    "request_deadline_s": spec.config.heartbeat_timeout_s,
                    "max_frame_bytes": spec.config.broker_max_frame_bytes,
                },
            )
        self.worker_specs = []
        self.worker_servers = []
        self._server_threads = []
        self._runtime_side_effects_factory = runtime_side_effects_factory
        self._worker_launcher = worker_launcher
        for resources in self.resource_manifest.workers:
            token_path = self.authority.issue(resources.worker_id, resources.generation)
            socket_path = self.authority.ipc_root / f"{resources.worker_id}.sock"
            server = AuthenticatedUnixServer(
                socket_path,
                self.authority,
                self._coordinator_handler,
                deadline_s=spec.config.heartbeat_timeout_s,
                max_frame_bytes=spec.config.broker_max_frame_bytes,
            )
            worker_spec = {
                "schema_version": 1,
                "batch_id": spec.request.batch_id,
                "run_mode": spec.request.run_mode.value,
                "config_path": str(spec.config_path),
                "socket_path": str(socket_path),
                "token_path": str(token_path),
                "coordinator_epoch": self.journal.coordinator_epoch,
                "broker_socket_path": str(self.broker_socket_path),
                "broker_generation": 1,
                "catalog": {
                    point_id: self.spec.catalog[point_id]
                    for point_id in self.spec.request.selected_point_ids
                },
                "resources": resources.to_dict(),
            }
            worker_path = resources.worker_root / "worker-spec.json"
            _write_json(worker_path, worker_spec)
            self.worker_specs.append(worker_path)
            self.worker_servers.append(server)

    def _start_broker(self):
        if self.broker_spec_path is None:
            return None
        if self._broker_command_builder is not None:
            command = self._broker_command_builder(self)
        else:
            from so101_demo.cli.parallel_perception_broker import (
                container_run_argv,
                gpu_groups,
                image_record,
            )

            image_id = self.spec.provenance.get("image_id")
            if not isinstance(image_id, str):
                raise CliError("BROKER_IMAGE_ID_REQUIRED")
            try:
                current_image = image_record(self.spec.broker_image)
            except Exception as error:
                raise CliError("BROKER_IMAGE_READBACK_FAILED") from error
            if any(
                self.spec.provenance.get(name) != value
                for name, value in current_image.items()
            ):
                raise CliError("BROKER_IMAGE_TAG_DRIFT")
            command = container_run_argv(
                self.spec.request.evidence_root,
                image_id=image_id,
                yolo_weights=self.spec.yolo_weights.resolve(),
                grounded_root=self.spec.grounded_root.resolve(),
                gpu_groups=gpu_groups(),
                uid=os.getuid(),
                gid=os.getgid(),
            )
        return self.supervisor.start("broker", command)

    def _wait_broker_ready(self):
        if self.broker_spec_path is None:
            return True
        deadline = time.monotonic() + self.spec.config.heartbeat_timeout_s
        ready = self.authority.ipc_root / "ready.json"
        while time.monotonic() < deadline:
            self.supervisor.assert_healthy()
            if (
                self.broker_socket_path.exists()
                and not self.broker_socket_path.is_symlink()
                and ready.is_file()
                and not ready.is_symlink()
            ):
                return True
            time.sleep(0.01)
        raise CliError("BROKER_READY_TIMEOUT")

    def _cleanup_facts(self):
        snapshot = self.coordinator.snapshot()
        workers = tuple(snapshot.workers.values())
        no_leases = snapshot.terminal_reason is not None and all(
            worker.lease is None for worker in workers
        )
        no_worker_processes = all(
            process.role != "worker" for process in self.supervisor.processes
        )
        recovered = all(
            worker.state in {WorkerState.AVAILABLE, WorkerState.QUARANTINED}
            for worker in workers
        )
        return no_leases, no_worker_processes, recovered

    def _start_workers(self):
        for path, resources in zip(
            self.worker_specs, self.resource_manifest.workers, strict=True
        ):
            command = (
                sys.executable, "-m", "so101_demo.cli.mujoco_parallel_batch",
                "--internal-worker", str(path),
            )
            environment = dict(os.environ)
            environment.update(resources.environment)
            self.supervisor.start("worker", command, environment=environment)

    def _active_lease(self, message):
        worker = self.coordinator.snapshot().workers.get(message["worker_id"])
        if worker is None or worker.lease is None:
            raise CliError("RPC_ACTIVE_LEASE_REQUIRED")
        if _lease_wire(worker.lease) != message["lease"]:
            raise CliError("RPC_STALE_LEASE")
        return worker.lease

    def _coordinator_handler(self, message):
        payload = message["payload"]
        operation = payload.get("operation")
        worker_id = message["worker_id"]
        generation = message["worker_generation"]
        if worker_id == "broker":
            if generation != 1:
                raise CliError("BROKER_GENERATION")
            if operation == "authenticate_broker_message":
                inner = payload.get("message")
                self.authority.authenticate(inner)
                return {"authenticated": True}
            if operation == "authorize_inference":
                request = _inference_request(payload.get("request"))
                snapshot = _snapshot(payload.get("snapshot"))
                if snapshot.start_identity != NormalizedInferenceResponseIdentity.from_request(
                    request
                ):
                    raise CliError("BROKER_START_IDENTITY")
                worker = self.coordinator.snapshot().workers.get(request.worker_id)
                if (
                    worker is None
                    or worker.state is not WorkerState.EXECUTING
                    or worker.generation != request.worker_generation
                    or worker.lease is None
                ):
                    return {"authorized": False}
                lease = worker.lease
                if any(
                    getattr(lease, name) != getattr(request, name)
                    for name in (
                        "batch_id",
                        "coordinator_epoch",
                        "worker_id",
                        "worker_generation",
                        "point_id",
                        "lease_generation",
                    )
                ) or lease.attempt_id != (
                    request.attempt_id
                    if request.execution_kind is ExecutionKind.ATTEMPT
                    else request.validation_id
                ):
                    return {"authorized": False}
                event = next(
                    (
                        item
                        for item in self.journal.replay().events
                        if item.idempotency_key == snapshot.start_event_id
                    ),
                    None,
                )
                expected_type = (
                    "ATTEMPT_STARTED"
                    if request.execution_kind is ExecutionKind.ATTEMPT
                    else "VALIDATION_STARTED"
                )
                if (
                    event is None
                    or event.type != expected_type
                    or snapshot.start_event_type != expected_type
                    or event.coordinator_epoch != request.coordinator_epoch
                ):
                    return {"authorized": False}
                identity = event.payload.get("identity")
                if type(identity) is not dict:
                    return {"authorized": False}
                expected = {
                    "batch_id": lease.batch_id,
                    "coordinator_epoch": lease.coordinator_epoch,
                    "worker_id": lease.worker_id,
                    "worker_generation": lease.worker_generation,
                    "point_id": lease.point_id,
                    "attempt_id": lease.attempt_id,
                    "lease_generation": lease.lease_generation,
                }
                authorized = (
                    all(identity.get(name) == value for name, value in expected.items())
                    and type(identity.get("gate_summary")) is dict
                    and identity["gate_summary"].get("reset_epoch")
                    == request.reset_epoch
                )
                return {"authorized": authorized}
            raise CliError("BROKER_AUTHORITY_OPERATION")
        if operation == "register_worker":
            requested = payload.get("generation")
            ack = self.coordinator.register_worker(
                worker_id,
                generation=requested,
                recovery_deadline_monotonic_s=payload.get("recovery_deadline_monotonic_s"),
            )
            if requested != generation:
                self.authority.advance_generation(worker_id, generation, requested)
            return _jsonable(ack)
        if operation == "grant_lease":
            lease = self.coordinator.grant_lease(
                worker_id,
                generation=payload.get("generation"),
                request_key=message["idempotency_key"],
            )
            if lease is not None:
                self.authority.bind_lease(worker_id, generation, _lease_wire(lease))
            return _jsonable(lease)
        if operation == "record_recovery":
            values = {key: value for key, value in payload.items() if key != "operation"}
            return _jsonable(self.coordinator.record_recovery(worker_id, **values))
        if operation == "replace_resources":
            return self.allocator.replace(
                worker_id,
                expected_generation=payload.get("expected_generation"),
            ).to_dict()
        lease = self._active_lease(message)
        if operation == "heartbeat":
            return _jsonable(self.coordinator.heartbeat(lease))
        if operation == "ack_lease":
            return _jsonable(self.coordinator.ack_lease(
                lease, request_key=message["idempotency_key"]
            ))
        if operation in {"ack_attempt_started", "ack_validation_started"}:
            method = getattr(self.coordinator, operation)
            return _jsonable(method(
                lease,
                request_key=message["idempotency_key"],
                gate_summary=payload.get("gate_summary"),
            ))
        if operation == "begin_finalizing":
            return _jsonable(self.coordinator.begin_finalizing(
                lease, request_key=message["idempotency_key"]
            ))
        if operation in {"commit_result", "commit_validation"}:
            return _jsonable(getattr(self.coordinator, operation)(
                lease,
                payload.get("location"),
                request_key=message["idempotency_key"],
            ))
        raise CliError("RPC_UNKNOWN_OPERATION")

    def _start_servers(self):
        servers = list(self.worker_servers)
        if self.broker_authority_server is not None:
            servers.append(self.broker_authority_server)
        for server in servers:
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self._server_threads.append(thread)

    def _stop_servers(self):
        servers = list(self.worker_servers)
        if self.broker_authority_server is not None:
            servers.append(self.broker_authority_server)
        for server in servers:
            server.close()
        for thread in self._server_threads:
            thread.join(timeout=1.0)

    def _run_worker_local(self, path):
        resources = _resource_from_dict(json.loads(Path(path).read_text())["resources"])
        side_effects = (
            None if self._runtime_side_effects_factory is None
            else self._runtime_side_effects_factory(resources)
        )
        worker, runtime = _build_worker_from_spec(
            path, runtime_side_effects=side_effects
        )
        self.last_local_components = (worker, runtime)
        try:
            results = worker.run()
            return int(
                not results
                or any(
                    result.stopped_reason not in {"POINT_TERMINAL", "NO_POINT"}
                    for result in results
                )
            )
        finally:
            runtime.shutdown_owned()

    def run(self) -> BatchSummary:
        failure = False
        cleanup = False
        try:
            self._start_servers()
            self._start_broker()
            self._wait_broker_ready()
            if self._worker_launcher is not None:
                codes = [self._worker_launcher(self, path) for path in self.worker_specs]
            else:
                self._start_workers()
                codes = self.supervisor.wait_for_children(
                    deadline_monotonic_s=time.monotonic() + self.spec.config.batch_hard_timeout_s
                )
            failure = any(code != 0 for code in codes)
            snapshot = self.coordinator.snapshot()
        finally:
            try:
                cleanup = self.supervisor.shutdown(
                    stop_leases=lambda: self._cleanup_facts()[0],
                    cancel_goal=lambda: self._cleanup_facts()[1],
                    confirm_goal_cancelled=lambda: self._cleanup_facts()[1],
                    request_recovery=lambda: self._cleanup_facts()[2],
                )
                snapshot = self.coordinator.snapshot()
                if snapshot.terminal_reason and cleanup and not failure:
                    snapshot = self.coordinator.complete_cleanup(
                        owned_processes_stopped=True, controllers_stopped=True
                    )
            finally:
                self._stop_servers()
                self.journal.close()
                self.allocator.close()
        return snapshot.summary


def outcome_document(summary: BatchSummary) -> tuple[int, dict[str, object]]:
    if not isinstance(summary, BatchSummary):
        raise CliError("BATCH_SUMMARY_REQUIRED")
    document = {
        "schema_version": 1,
        "run_mode": summary.run_mode.value,
        "batch_terminal": summary.batch_terminal,
        "batch_cleanup_complete": summary.batch_cleanup_complete,
        "point_statuses": {key: value.value for key, value in summary.point_statuses.items()},
        "validation_statuses": {
            key: value.value for key, value in summary.validation_statuses.items()
        },
        "validation_complete": summary.validation_complete,
        "validation_passed": summary.validation_passed,
        "qualification_applicable": summary.qualification_applicable,
        "qualification_passed": summary.qualification_passed,
    }
    if summary.run_mode is RunMode.EXECUTE:
        passed = summary.qualification_passed
    else:
        passed = summary.validation_passed and summary.batch_cleanup_complete
    return (0 if passed else 1), document


def _write_json(path: Path, document: Mapping[str, object]) -> None:
    payload = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_bytes(path: Path, payload: bytes) -> None:
    descriptor = os.open(
        path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
    )
    try:
        os.write(descriptor, payload)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def run_cli(
    argv=None,
    *,
    provenance_verifier=verify_provenance,
    composition_factory=ProductionBatchComposition,
) -> int:
    try:
        spec = prepare_batch(argv, provenance_verifier=provenance_verifier)
        composition = composition_factory(spec)
        root = spec.request.evidence_root
        if not root.exists():
            root.mkdir(parents=True, mode=0o700)
        _write_json(root / "batch_manifest.json", spec.manifest)
        summary = composition.run()
        code, document = outcome_document(summary)
        aggregate = root / "aggregate_results.json"
        _write_json(aggregate, document)
        print(json.dumps(document, sort_keys=True))
        return code
    except (CliError, ContractError, OSError, ValueError) as error:
        print(json.dumps({"status": "ERROR", "message": str(error)}, sort_keys=True), file=sys.stderr)
        return 1


def main(argv=None) -> int:
    values = list(sys.argv[1:] if argv is None else argv)
    if values[:1] == ["--internal-worker"]:
        if len(values) != 2:
            return 1
        return _run_worker_spec(Path(values[1]))
    return run_cli(values)


if __name__ == "__main__":
    raise SystemExit(main())
