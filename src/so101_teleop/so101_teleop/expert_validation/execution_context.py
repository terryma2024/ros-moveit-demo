"""The two mutually exclusive live-execution contexts (design section 10).

This design has no resource-measurement authorization. A live run is either a *bounded candidate
run* during implementation, or an *installed production run* issued by the service:

* :class:`CandidateExecutionContext` binds the task/dispatch that authorized it, the profile and
  config hash it may execute, the runtime closure, the worker count, the batch, the evidence root,
  the owner generation, a one-time command id, an expiry and a run budget.
* :class:`ProductionExecutionContext` is issued by the installed service from one of the three
  allowed v4/v5/v6 profiles and additionally binds the current copied-install closure, the service
  session and the valid control lease that authorizes the run.

Neither carries a budget, qualification or promotion field, neither is accepted on the other's
endpoint, and neither can be replayed across a batch, profile, worker count or evidence root: every
one of those coordinates is part of the context, and the command that consumes it is one-time.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import ClassVar

from .preflight import MACOS_EXECUTION_PROFILES, ExecutionProfile


CANDIDATE_CONTEXT_KIND = "CANDIDATE"
PRODUCTION_CONTEXT_KIND = "PRODUCTION"

#: A retry is one point of the v5 W1 combination and nothing else (design section 8).
RETRY_PROFILE = "MPS_W1_FULL_RESTART_RETRY"
RETRY_SCHEMA_VERSION = 5
RETRY_WORKER_COUNT = 1
RETRY_BATCH_KIND = "FULL_RESTART_RETRY"

#: Every durable fact about the bytes a run will execute. The closure hash covers all of them, so
#: a context issued for one copied install can never authorize another one.
RUNTIME_CLOSURE_FIELDS = (
    "coordinator_executable_sha256",
    "adaptive_runner_module_sha256",
    "adaptive_pool_module_sha256",
    "adaptive_cleanup_executable_sha256",
    "adaptive_wrapper_sha256",
    "parallel_config_sha256",
    "adaptive_config_sha256",
    "yolo_weights_sha256",
    "grounded_sam_manifest_sha256",
    "broker_image_id",
    "resource_manifest_sha256",
    "source_commit",
    "install_prefix",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$")


class ExecutionContextError(RuntimeError):
    """A context cannot be issued, or does not authorize the run it is presented for."""

    def __init__(self, code: str, detail: object = "") -> None:
        self.code = code
        self.detail = str(detail)
        super().__init__(f"{code}: {self.detail}" if self.detail else code)


def _identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ExecutionContextError("CONTEXT_IDENTIFIER_INVALID", name)
    return value


def _sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ExecutionContextError("CONTEXT_SHA256_INVALID", name)
    return value


def _absolute(name: str, value: object) -> Path:
    path = Path(value)
    if not path.is_absolute() or path != path.resolve(strict=False):
        raise ExecutionContextError("CONTEXT_PATH_ABSOLUTE_NORMALIZED", name)
    return path


def _positive(name: str, value: object) -> int:
    if type(value) is not int or isinstance(value, bool) or value < 1:
        raise ExecutionContextError("CONTEXT_POSITIVE_INTEGER", name)
    return value


def _canonical_sha256(document) -> str:
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def installed_execution_profiles() -> tuple[ExecutionProfile, ...]:
    """The three allowed combinations, in support-matrix order. Never a caller's claim."""

    return MACOS_EXECUTION_PROFILES


def installed_execution_profile(profile: str, schema_version: int) -> ExecutionProfile | None:
    for row in MACOS_EXECUTION_PROFILES:
        if row.profile == profile and row.schema_version == schema_version:
            return row
    return None


def runtime_closure_sha256(request) -> str:
    """One hash over every executable and config byte a run will execute."""

    return _canonical_sha256(
        {name: getattr(request, name, None) for name in RUNTIME_CLOSURE_FIELDS}
    )


def install_binding_sha256(*, install_prefix, runtime_closure_sha256: str) -> str:
    """The current copied-install binding: its prefix plus the whole runtime closure."""

    return _canonical_sha256({
        "install_prefix": str(install_prefix),
        "runtime_closure_sha256": runtime_closure_sha256,
    })


def retry_batch_root(evidence_root, campaign_id: str, batch_id: str) -> Path:
    """The one batch root the store binds and the supervisor spawns into."""

    return (Path(evidence_root) / "campaigns" / campaign_id / batch_id).resolve()


def retry_admission_command_id(command_id: str, ordinal: int) -> str:
    """One queue entry, one one-time admission command, derived from the client's command id."""

    _identifier("command_id", command_id)
    if type(ordinal) is not int or isinstance(ordinal, bool) or ordinal < 0:
        raise ExecutionContextError("CONTEXT_POSITIVE_INTEGER", "ordinal")
    return f"{command_id}-r{ordinal + 1:03d}"


@dataclass(frozen=True, slots=True)
class CandidateExecutionContext:
    """A bounded implementation-phase run, authorized by one task and one dispatch.

    ``max_runs`` is not a resource budget: it is how many admitted runs the candidate dispatch
    authorized, and every run must still present its own one-time ``command_id``.
    """

    context_id: str
    task_id: str
    dispatch_id: str
    campaign_id: str
    batch_id: str
    manifest_id: str
    execution_profile: str
    schema_version: int
    batch_kind: str
    worker_count: int
    config_sha256: str
    runtime_closure_sha256: str
    evidence_root: Path
    owner_generation: int
    command_id: str
    issued_at_monotonic_ns: int
    expires_at_monotonic_ns: int
    max_runs: int

    kind: ClassVar[str] = CANDIDATE_CONTEXT_KIND

    def __post_init__(self) -> None:
        for name in (
            "context_id",
            "task_id",
            "dispatch_id",
            "campaign_id",
            "batch_id",
            "manifest_id",
            "execution_profile",
            "command_id",
        ):
            _identifier(name, getattr(self, name))
        for name in ("config_sha256", "runtime_closure_sha256"):
            _sha256(name, getattr(self, name))
        _positive("schema_version", self.schema_version)
        _positive("worker_count", self.worker_count)
        _positive("owner_generation", self.owner_generation)
        _positive("max_runs", self.max_runs)
        _positive("issued_at_monotonic_ns", self.issued_at_monotonic_ns)
        object.__setattr__(self, "evidence_root", _absolute("evidence_root", self.evidence_root))
        _positive("expires_at_monotonic_ns", self.expires_at_monotonic_ns)
        if self.expires_at_monotonic_ns <= self.issued_at_monotonic_ns:
            raise ExecutionContextError("CONTEXT_EXPIRY_INVALID", self.context_id)
        # A candidate run executes an installed matrix row too: the worker count, batch kind and
        # mode come from the row, never from the caller's restatement of them.
        row = installed_execution_profile(self.execution_profile, self.schema_version)
        if (
            row is None
            or row.batch_kind != self.batch_kind
            or row.worker_count != self.worker_count
        ):
            raise ExecutionContextError(
                "CONTEXT_PROFILE_INVALID", f"{self.execution_profile}/{self.schema_version}"
            )

    @property
    def scope(self) -> str:
        """The dispatch a run budget is counted against."""

        return f"{self.task_id}/{self.dispatch_id}"

    def is_expired(self, now_monotonic_ns: int) -> bool:
        return now_monotonic_ns >= self.expires_at_monotonic_ns

    def as_document(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "context_id": self.context_id,
            "task_id": self.task_id,
            "dispatch_id": self.dispatch_id,
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "manifest_id": self.manifest_id,
            "execution_profile": self.execution_profile,
            "schema_version": self.schema_version,
            "batch_kind": self.batch_kind,
            "worker_count": self.worker_count,
            "config_sha256": self.config_sha256,
            "runtime_closure_sha256": self.runtime_closure_sha256,
            "evidence_root": str(self.evidence_root),
            "owner_generation": self.owner_generation,
            "command_id": self.command_id,
            "issued_at_monotonic_ns": self.issued_at_monotonic_ns,
            "expires_at_monotonic_ns": self.expires_at_monotonic_ns,
            "max_runs": self.max_runs,
        }

    def context_sha256(self) -> str:
        return _canonical_sha256(self.as_document())


@dataclass(frozen=True, slots=True)
class ProductionExecutionContext:
    """An installed production run, issued by the service for one live lease generation."""

    context_id: str
    service_session_id: str
    lease_id: str
    lease_generation: int
    install_prefix: Path
    install_binding_sha256: str
    execution_profile: str
    schema_version: int
    batch_kind: str
    worker_count: int
    campaign_id: str
    batch_id: str
    manifest_id: str
    config_sha256: str
    runtime_closure_sha256: str
    evidence_root: Path
    owner_generation: int
    command_id: str
    issued_at_monotonic_ns: int
    expires_at_monotonic_ns: int

    kind: ClassVar[str] = PRODUCTION_CONTEXT_KIND

    def __post_init__(self) -> None:
        for name in (
            "context_id",
            "service_session_id",
            "lease_id",
            "campaign_id",
            "batch_id",
            "manifest_id",
            "execution_profile",
            "command_id",
        ):
            _identifier(name, getattr(self, name))
        for name in ("config_sha256", "runtime_closure_sha256", "install_binding_sha256"):
            _sha256(name, getattr(self, name))
        _positive("lease_generation", self.lease_generation)
        _positive("schema_version", self.schema_version)
        _positive("worker_count", self.worker_count)
        _positive("owner_generation", self.owner_generation)
        _positive("issued_at_monotonic_ns", self.issued_at_monotonic_ns)
        object.__setattr__(self, "install_prefix", _absolute("install_prefix", self.install_prefix))
        object.__setattr__(self, "evidence_root", _absolute("evidence_root", self.evidence_root))
        row = installed_execution_profile(self.execution_profile, self.schema_version)
        # Only an installed v4/v5/v6 combination may be issued, and the row decides the shape:
        # a context that restates one field of it differently is not a row of the matrix.
        if (
            row is None
            or row.batch_kind != self.batch_kind
            or row.worker_count != self.worker_count
        ):
            raise ExecutionContextError(
                "CONTEXT_PROFILE_INVALID", f"{self.execution_profile}/{self.schema_version}"
            )
        _positive("expires_at_monotonic_ns", self.expires_at_monotonic_ns)
        if self.expires_at_monotonic_ns <= self.issued_at_monotonic_ns:
            raise ExecutionContextError("CONTEXT_EXPIRY_INVALID", self.context_id)

    @property
    def scope(self) -> str:
        """The service session a run is authorized for."""

        return self.service_session_id

    def is_expired(self, now_monotonic_ns: int) -> bool:
        return now_monotonic_ns >= self.expires_at_monotonic_ns

    def install_binding(self) -> str:
        return install_binding_sha256(
            install_prefix=self.install_prefix,
            runtime_closure_sha256=self.runtime_closure_sha256,
        )

    def as_document(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "context_id": self.context_id,
            "service_session_id": self.service_session_id,
            "lease_id": self.lease_id,
            "lease_generation": self.lease_generation,
            "install_prefix": str(self.install_prefix),
            "install_binding_sha256": self.install_binding_sha256,
            "execution_profile": self.execution_profile,
            "schema_version": self.schema_version,
            "batch_kind": self.batch_kind,
            "worker_count": self.worker_count,
            "campaign_id": self.campaign_id,
            "batch_id": self.batch_id,
            "manifest_id": self.manifest_id,
            "config_sha256": self.config_sha256,
            "runtime_closure_sha256": self.runtime_closure_sha256,
            "evidence_root": str(self.evidence_root),
            "owner_generation": self.owner_generation,
            "command_id": self.command_id,
            "issued_at_monotonic_ns": self.issued_at_monotonic_ns,
            "expires_at_monotonic_ns": self.expires_at_monotonic_ns,
        }

    def context_sha256(self) -> str:
        return _canonical_sha256(self.as_document())


#: The only two context types this design has.
ExecutionContext = CandidateExecutionContext | ProductionExecutionContext
CONTEXT_TYPES: tuple[type, ...] = (CandidateExecutionContext, ProductionExecutionContext)
