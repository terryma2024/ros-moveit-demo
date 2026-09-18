"""Exact-N resource admission: closed contexts, arithmetic, profiles and authorities.

This module is the single resource gate shared by the production consumers. It
never computes headroom from a per-consumer formula and never turns a factory
token into an approval: every issuance re-reads the external authority bytes.
"""

from __future__ import annotations

import ctypes
import hashlib
import json
import math
import os
import platform
import re
import stat
import time
from dataclasses import dataclass, field, fields, replace
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping, Sequence

from .contracts import ContractError
from .resource_identity import RuntimeFingerprint, canonical_sha256

DIMENSIONS = ("cpu_core_equivalent", "gpu_bytes", "ram_bytes")
_HEADROOM_CODES = {
    "cpu_core_equivalent": "CPU_HEADROOM",
    "gpu_bytes": "GPU_HEADROOM",
    "ram_bytes": "RAM_HEADROOM",
}
_ALLOCATION_KINDS = ("FIXED_PRODUCTION", "MEASUREMENT", "ADAPTIVE")
_PROFILE_STATUSES = ("UNKNOWN", "CANDIDATE", "REJECTED", "APPROVED")
_STAGES = ("startup", "steady", "recovery", "finalization")
_COVERAGE_CELLS = (
    "COLD_START", "STEADY_YOLO", "STEADY_GROUNDED_SAM", "STEADY_MIXED", "MOTION_RELEASE",
    "BROKER_RELOAD_WITH_N_RESIDENT", "WORKER_RECOVERY_WITH_N_RESIDENT", "FINALIZATION_CLEANUP",
)
_MAXIMUM_OBSERVATION_AGE_S = 2.0
_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_ISSUER = object()


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ContractError(f"SHA256: {name}")
    return value


def _require_nonnegative_finite(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"NONFINITE: {name}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ContractError(f"NONFINITE: {name}")
    return result


def _require_dimensions(name: str, value: object) -> Mapping[str, float]:
    if not isinstance(value, Mapping) or set(value) != set(DIMENSIONS):
        raise ContractError(f"DIMENSIONS: {name}")
    return MappingProxyType(
        {key: _require_nonnegative_finite(f"{name}.{key}", value[key]) for key in DIMENSIONS}
    )


def headroom_ok(capacity: float, observed: float, remaining: float, error: float) -> bool:
    """The frozen 20% envelope: observed + remaining + error <= 0.8 * capacity."""

    values = (capacity, observed, remaining, error)
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        return False
    if any(not math.isfinite(float(value)) for value in values):
        return False
    if float(capacity) <= 0 or float(observed) < 0 or float(remaining) < 0 or float(error) < 0:
        return False
    return float(observed) + float(remaining) + float(error) <= 0.8 * float(capacity)


@dataclass(frozen=True, slots=True)
class AllocationScope:
    batch_id: str
    epoch: int
    worker_count: int
    request_kind: str
    execution_identity_sha256: str

    def __post_init__(self) -> None:
        if not isinstance(self.batch_id, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]*", self.batch_id
        ):
            raise ContractError("BATCH_ID")
        if type(self.epoch) is not int or self.epoch < 1:
            raise ContractError("EPOCH")
        if type(self.worker_count) is not int or not 1 <= self.worker_count <= 8:
            raise ContractError("WORKER_COUNT")
        if self.request_kind not in _ALLOCATION_KINDS:
            raise ContractError("REQUEST_KIND")
        _require_sha256("execution_identity_sha256", self.execution_identity_sha256)

    @property
    def sha256(self) -> str:
        return canonical_sha256(
            {
                "batch_id": self.batch_id,
                "epoch": self.epoch,
                "worker_count": self.worker_count,
                "request_kind": self.request_kind,
                "execution_identity_sha256": self.execution_identity_sha256,
            }
        )


@dataclass(frozen=True, slots=True)
class FixedProductionContext:
    scope: AllocationScope
    authority_sha256: str
    profile_sha256: str
    qualification_sha256: str
    control_binding_sha256: str
    _issuer: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._issuer is not _ISSUER:
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if self.scope.request_kind != "FIXED_PRODUCTION":
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        for name in ("authority_sha256", "profile_sha256", "qualification_sha256",
                     "control_binding_sha256"):
            _require_sha256(name, getattr(self, name))

    @property
    def kind(self) -> str:
        return "FIXED_PRODUCTION"

    @property
    def sha256(self) -> str:
        return canonical_sha256(
            {
                "kind": self.kind,
                "scope": self.scope.sha256,
                "authority_sha256": self.authority_sha256,
                "profile_sha256": self.profile_sha256,
                "qualification_sha256": self.qualification_sha256,
                "control_binding_sha256": self.control_binding_sha256,
            }
        )


@dataclass(frozen=True, slots=True)
class MeasurementContext:
    scope: AllocationScope
    authority_sha256: str
    authorization_sha256: str
    owned_scope_sha256: str
    _issuer: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._issuer is not _ISSUER:
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if self.scope.request_kind != "MEASUREMENT":
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        for name in ("authority_sha256", "authorization_sha256", "owned_scope_sha256"):
            _require_sha256(name, getattr(self, name))

    @property
    def kind(self) -> str:
        return "MEASUREMENT"

    @property
    def sha256(self) -> str:
        return canonical_sha256(
            {
                "kind": self.kind,
                "scope": self.scope.sha256,
                "authority_sha256": self.authority_sha256,
                "authorization_sha256": self.authorization_sha256,
                "owned_scope_sha256": self.owned_scope_sha256,
            }
        )


@dataclass(frozen=True, slots=True)
class AdaptiveAllocationContext:
    scope: AllocationScope
    authority_sha256: str
    pool_token_sha256: str
    pool_generation: int
    _issuer: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._issuer is not _ISSUER:
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if self.scope.request_kind != "ADAPTIVE":
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        for name in ("authority_sha256", "pool_token_sha256"):
            _require_sha256(name, getattr(self, name))
        if type(self.pool_generation) is not int or self.pool_generation < 1:
            raise ContractError("POOL_GENERATION")

    @property
    def kind(self) -> str:
        return "ADAPTIVE"

    @property
    def sha256(self) -> str:
        return canonical_sha256(
            {
                "kind": self.kind,
                "scope": self.scope.sha256,
                "authority_sha256": self.authority_sha256,
                "pool_token_sha256": self.pool_token_sha256,
                "pool_generation": self.pool_generation,
            }
        )


@dataclass(frozen=True, slots=True)
class LiveResourceObservation:
    monotonic_s: float
    capacity: Mapping[str, float]
    observed: Mapping[str, float]
    background: Mapping[str, float]
    tool_overhead: Mapping[str, float]
    remaining: Mapping[str, float]
    error: Mapping[str, float]
    attribution_complete: bool
    swap_delta: int
    psi_full_delta: float
    throttled: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "monotonic_s", _require_nonnegative_finite("monotonic_s", self.monotonic_s)
        )
        for name in ("capacity", "observed", "background", "tool_overhead", "remaining", "error"):
            object.__setattr__(
                self, name, _require_dimensions(name, getattr(self, name))
            )
        if any(value <= 0 for value in self.capacity.values()):
            raise ContractError("CAPACITY")
        if not isinstance(self.attribution_complete, bool):
            raise ContractError("ATTRIBUTION")
        if type(self.swap_delta) is not int or self.swap_delta < 0:
            raise ContractError("SWAP_DELTA")
        object.__setattr__(
            self, "psi_full_delta", _require_nonnegative_finite("psi_full_delta", self.psi_full_delta)
        )
        if not isinstance(self.throttled, bool):
            raise ContractError("THROTTLED")


@dataclass(frozen=True, slots=True)
class QualificationDecision:
    qualified: bool
    reason_codes: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.qualified, bool):
            raise ContractError("QUALIFICATION_DECISION")
        codes = tuple(self.reason_codes)
        if self.qualified and codes:
            raise ContractError("QUALIFICATION_DECISION")
        object.__setattr__(self, "reason_codes", codes)


@dataclass(frozen=True, slots=True)
class ResourceBudgetAdmission:
    admitted: bool
    reason_codes: tuple[str, ...]
    worker_count: int
    profile_sha256: str | None
    qualification_sha256: str | None
    execution_identity_sha256: str
    observation_monotonic_s: float

    def __post_init__(self) -> None:
        if not isinstance(self.admitted, bool):
            raise ContractError("ADMISSION")
        codes = tuple(self.reason_codes)
        if self.admitted and codes:
            raise ContractError("ADMISSION")
        object.__setattr__(self, "reason_codes", codes)


_QUALIFICATION_FIELDS = (
    "schema_version", "execution_identity_sha256", "worker_count", "coverage_policy_sha256",
    "sealed_manifest_sha256s", "normal_valid_runs", "normal_required_runs", "coverage_complete",
    "cleanup_verified", "independent_physics_verified", "resource_contract_verified",
)


@dataclass(frozen=True, slots=True)
class ExactNQualification:
    schema_version: int
    execution_identity_sha256: str
    worker_count: int
    coverage_policy_sha256: str
    sealed_manifest_sha256s: tuple[str, ...]
    normal_valid_runs: int
    normal_required_runs: int
    coverage_complete: bool
    cleanup_verified: bool
    independent_physics_verified: bool
    resource_contract_verified: bool
    raw_sha256: str

    @classmethod
    def from_document(cls, document: object, *, raw_sha256: str) -> "ExactNQualification":
        if not isinstance(document, Mapping):
            raise ContractError("QUALIFICATION_MAPPING")
        unknown = set(document) - set(_QUALIFICATION_FIELDS)
        if unknown:
            raise ContractError(f"QUALIFICATION_UNKNOWN_FIELD: {sorted(unknown)!r}")
        missing = set(_QUALIFICATION_FIELDS) - set(document)
        if missing:
            raise ContractError(f"QUALIFICATION_MISSING_FIELD: {sorted(missing)!r}")
        if type(document["schema_version"]) is not int or document["schema_version"] != 2:
            raise ContractError("QUALIFICATION_SCHEMA_VERSION")
        manifests = document["sealed_manifest_sha256s"]
        if not isinstance(manifests, (list, tuple)) or not manifests:
            raise ContractError("QUALIFICATION_MANIFESTS")
        for manifest in manifests:
            _require_sha256("sealed_manifest_sha256", manifest)
        for name in ("coverage_complete", "cleanup_verified", "independent_physics_verified",
                     "resource_contract_verified"):
            if not isinstance(document[name], bool):
                raise ContractError(f"QUALIFICATION_BOOLEAN: {name}")
        for name in ("worker_count", "normal_valid_runs", "normal_required_runs"):
            if type(document[name]) is not int or document[name] < 0:
                raise ContractError(f"QUALIFICATION_INTEGER: {name}")
        return cls(
            schema_version=2,
            execution_identity_sha256=_require_sha256(
                "execution_identity_sha256", document["execution_identity_sha256"]),
            worker_count=document["worker_count"],
            coverage_policy_sha256=_require_sha256(
                "coverage_policy_sha256", document["coverage_policy_sha256"]),
            sealed_manifest_sha256s=tuple(manifests),
            normal_valid_runs=document["normal_valid_runs"],
            normal_required_runs=document["normal_required_runs"],
            coverage_complete=document["coverage_complete"],
            cleanup_verified=document["cleanup_verified"],
            independent_physics_verified=document["independent_physics_verified"],
            resource_contract_verified=document["resource_contract_verified"],
            raw_sha256=_require_sha256("raw_sha256", raw_sha256),
        )

    def as_document(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "execution_identity_sha256": self.execution_identity_sha256,
            "worker_count": self.worker_count,
            "coverage_policy_sha256": self.coverage_policy_sha256,
            "sealed_manifest_sha256s": list(self.sealed_manifest_sha256s),
            "normal_valid_runs": self.normal_valid_runs,
            "normal_required_runs": self.normal_required_runs,
            "coverage_complete": self.coverage_complete,
            "cleanup_verified": self.cleanup_verified,
            "independent_physics_verified": self.independent_physics_verified,
            "resource_contract_verified": self.resource_contract_verified,
        }


class ExactNQualificationProvider:
    """Verifies one exact-N record; it cannot reference a profile or receipt."""

    def verify(
        self,
        *,
        record: ExactNQualification,
        worker_count: int,
        execution_identity_sha256: str,
        coverage_policy_sha256: str,
    ) -> QualificationDecision:
        if not isinstance(record, ExactNQualification):
            return QualificationDecision(False, ("QUALIFICATION_EVIDENCE_INVALID",))
        if record.schema_version != 2:
            return QualificationDecision(False, ("QUALIFICATION_EVIDENCE_INVALID",))
        if record.worker_count != worker_count:
            return QualificationDecision(False, ("EXACT_N_UNQUALIFIED",))
        if record.execution_identity_sha256 != execution_identity_sha256:
            return QualificationDecision(False, ("RUNTIME_FINGERPRINT_MISMATCH",))
        if record.coverage_policy_sha256 != coverage_policy_sha256:
            return QualificationDecision(False, ("QUALIFICATION_EVIDENCE_INVALID",))
        if (
            record.normal_valid_runs < record.normal_required_runs
            or record.normal_required_runs < 5
            or not record.coverage_complete
            or not record.cleanup_verified
            or not record.independent_physics_verified
            or not record.resource_contract_verified
            or not record.sealed_manifest_sha256s
        ):
            return QualificationDecision(False, ("EXACT_N_UNQUALIFIED",))
        return QualificationDecision(True, ())


_STAGE_FIELDS = ("demand", "uncertainty", "background", "tool_overhead", "available_headroom")
_ENTRY_FIELDS = (
    "worker_count", "status", "qualification_sha256", "raw_manifest_sha256s", "coverage",
    "stages", "review_reference",
)


@dataclass(frozen=True, slots=True)
class StageEnvelope:
    stage: str
    demand: Mapping[str, float]
    uncertainty: Mapping[str, float]
    background: Mapping[str, float]
    tool_overhead: Mapping[str, float]
    available_headroom: Mapping[str, float]

    @classmethod
    def from_document(cls, stage: str, document: object) -> "StageEnvelope":
        if not isinstance(document, Mapping):
            raise ContractError("STAGE_MAPPING")
        unknown = set(document) - set(_STAGE_FIELDS)
        missing = set(_STAGE_FIELDS) - set(document)
        if unknown:
            raise ContractError(f"STAGE_UNKNOWN_FIELD: {sorted(unknown)!r}")
        if missing:
            raise ContractError(f"STAGE_MISSING_FIELD: {sorted(missing)!r}")
        return cls(
            stage=stage,
            demand=_require_dimensions("demand", document["demand"]),
            uncertainty=_require_dimensions("uncertainty", document["uncertainty"]),
            background=_require_dimensions("background", document["background"]),
            tool_overhead=_require_dimensions("tool_overhead", document["tool_overhead"]),
            available_headroom=_require_dimensions(
                "available_headroom", document["available_headroom"]),
        )

    def as_document(self) -> dict[str, object]:
        return {
            "demand": dict(self.demand),
            "uncertainty": dict(self.uncertainty),
            "background": dict(self.background),
            "tool_overhead": dict(self.tool_overhead),
            "available_headroom": dict(self.available_headroom),
        }


@dataclass(frozen=True, slots=True)
class ExactNProfileEntry:
    worker_count: int
    status: str
    qualification_sha256: str | None
    raw_manifest_sha256s: tuple[str, ...]
    coverage: Mapping[str, tuple[str, ...]]
    stages: Mapping[str, StageEnvelope]
    review_reference: str | None

    @classmethod
    def from_document(cls, document: object) -> "ExactNProfileEntry":
        if not isinstance(document, Mapping):
            raise ContractError("PROFILE_ENTRY_MAPPING")
        unknown = set(document) - set(_ENTRY_FIELDS)
        missing = set(_ENTRY_FIELDS) - set(document)
        if unknown:
            raise ContractError(f"PROFILE_ENTRY_UNKNOWN_FIELD: {sorted(unknown)!r}")
        if missing:
            raise ContractError(f"PROFILE_ENTRY_MISSING_FIELD: {sorted(missing)!r}")
        worker_count = document["worker_count"]
        if type(worker_count) is not int or not 1 <= worker_count <= 8:
            raise ContractError("PROFILE_ENTRY_WORKER_COUNT")
        status = document["status"]
        if status not in _PROFILE_STATUSES:
            raise ContractError("PROFILE_ENTRY_STATUS")
        coverage = document["coverage"]
        if not isinstance(coverage, Mapping):
            raise ContractError("PROFILE_ENTRY_COVERAGE")
        parsed_coverage = {}
        for cell, outcomes in coverage.items():
            if cell not in _COVERAGE_CELLS:
                raise ContractError(f"PROFILE_ENTRY_COVERAGE_CELL: {cell}")
            if not isinstance(outcomes, (list, tuple)) or not outcomes:
                raise ContractError(f"PROFILE_ENTRY_COVERAGE_VALUES: {cell}")
            parsed_coverage[cell] = tuple(str(outcome) for outcome in outcomes)
        stages = document["stages"]
        if not isinstance(stages, Mapping):
            raise ContractError("PROFILE_ENTRY_STAGES")
        parsed_stages = {}
        for stage, payload in stages.items():
            if stage not in _STAGES:
                raise ContractError(f"PROFILE_ENTRY_STAGE: {stage}")
            parsed_stages[stage] = StageEnvelope.from_document(stage, payload)
        manifests = document["raw_manifest_sha256s"]
        if not isinstance(manifests, (list, tuple)):
            raise ContractError("PROFILE_ENTRY_MANIFESTS")
        for manifest in manifests:
            _require_sha256("raw_manifest_sha256", manifest)
        qualification = document["qualification_sha256"]
        if qualification is not None:
            _require_sha256("qualification_sha256", qualification)
        review = document["review_reference"]
        if review is not None and (not isinstance(review, str) or not review):
            raise ContractError("PROFILE_ENTRY_REVIEW")
        entry = cls(
            worker_count=worker_count, status=status, qualification_sha256=qualification,
            raw_manifest_sha256s=tuple(manifests),
            coverage=MappingProxyType(parsed_coverage),
            stages=MappingProxyType(parsed_stages), review_reference=review,
        )
        entry._require_measurement_completeness()
        return entry

    def _require_measurement_completeness(self) -> None:
        if self.status == "UNKNOWN":
            if (
                self.qualification_sha256 is not None
                or self.raw_manifest_sha256s
                or self.stages
                or self.coverage
            ):
                raise ContractError("UNKNOWN_ENTRY_HAS_MEASUREMENTS")
            return
        if self.status in ("CANDIDATE", "APPROVED"):
            if not self.raw_manifest_sha256s or not self.stages:
                raise ContractError("ENTRY_MISSING_MEASUREMENTS")
        if self.status == "APPROVED":
            if self.qualification_sha256 is None or self.review_reference is None:
                raise ContractError("APPROVED_ENTRY_INCOMPLETE")
            if set(self.stages) != set(_STAGES):
                raise ContractError("APPROVED_ENTRY_STAGE_COVERAGE")
            if set(self.coverage) != set(_COVERAGE_CELLS):
                raise ContractError("APPROVED_ENTRY_COVERAGE")

    def as_document(self) -> dict[str, object]:
        return {
            "worker_count": self.worker_count,
            "status": self.status,
            "qualification_sha256": self.qualification_sha256,
            "raw_manifest_sha256s": list(self.raw_manifest_sha256s),
            "coverage": {cell: list(values) for cell, values in self.coverage.items()},
            "stages": {stage: envelope.as_document() for stage, envelope in self.stages.items()},
            "review_reference": self.review_reference,
        }


_PROFILE_FIELDS = ("schema_version", "execution_identity_sha256", "coverage_policy_sha256",
                   "entries")


@dataclass(frozen=True, slots=True)
class ApprovedBudgetProfile:
    schema_version: int
    execution_identity_sha256: str
    coverage_policy_sha256: str
    entries: Mapping[int, ExactNProfileEntry]
    raw_sha256: str

    @classmethod
    def from_document(cls, document: object, *, raw_sha256: str) -> "ApprovedBudgetProfile":
        if not isinstance(document, Mapping):
            raise ContractError("PROFILE_MAPPING")
        unknown = set(document) - set(_PROFILE_FIELDS)
        missing = set(_PROFILE_FIELDS) - set(document)
        if unknown:
            raise ContractError(f"PROFILE_UNKNOWN_FIELD: {sorted(unknown)!r}")
        if missing:
            raise ContractError(f"PROFILE_MISSING_FIELD: {sorted(missing)!r}")
        if type(document["schema_version"]) is not int or document["schema_version"] != 2:
            raise ContractError("PROFILE_SCHEMA_VERSION")
        raw_entries = document["entries"]
        if not isinstance(raw_entries, Mapping) or not raw_entries:
            raise ContractError("PROFILE_ENTRIES")
        entries = {}
        for key, payload in raw_entries.items():
            if not isinstance(key, str) or not key.isdigit():
                raise ContractError("PROFILE_ENTRY_KEY")
            entry = ExactNProfileEntry.from_document(payload)
            if int(key) != entry.worker_count:
                raise ContractError("PROFILE_ENTRY_KEY_MISMATCH")
            entries[entry.worker_count] = entry
        return cls(
            schema_version=2,
            execution_identity_sha256=_require_sha256(
                "execution_identity_sha256", document["execution_identity_sha256"]),
            coverage_policy_sha256=_require_sha256(
                "coverage_policy_sha256", document["coverage_policy_sha256"]),
            entries=MappingProxyType(entries),
            raw_sha256=_require_sha256("raw_sha256", raw_sha256),
        )

    def entry(self, worker_count: int) -> ExactNProfileEntry | None:
        return self.entries.get(worker_count)


def read_private_document(path: Path, *, expected_sha256: str | None = None) -> tuple[dict, str]:
    """Secure fd-based read: no symlink, owner/mode checked, size/hash stable."""

    descriptor = os.open(Path(path), os.O_RDONLY | os.O_NOFOLLOW)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ContractError("UNSAFE_FILE")
        if before.st_uid != os.getuid():
            raise ContractError("UNSAFE_OWNER")
        if stat.S_IMODE(before.st_mode) & 0o022:
            raise ContractError("UNSAFE_MODE")
        chunks = []
        while True:
            chunk = os.read(descriptor, 1 << 20)
            if not chunk:
                break
            chunks.append(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (
        after.st_size, after.st_mtime_ns, after.st_ino
    ):
        raise ContractError("UNSTABLE_FILE")
    data = b"".join(chunks)
    digest = hashlib.sha256(data).hexdigest()
    if expected_sha256 is not None and digest != expected_sha256:
        raise ContractError("HASH_MISMATCH")
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        raise ContractError("DOCUMENT_JSON") from error
    if not isinstance(document, dict):
        raise ContractError("DOCUMENT_MAPPING")
    return document, digest


def _live_reasons(
    live: LiveResourceObservation, *, now_monotonic_s: float | None,
    require_qualified_headroom: bool = True,
) -> list[str]:
    reasons = []
    if not live.attribution_complete:
        reasons.append("BACKGROUND_ENVELOPE_EXCEEDED")
    if now_monotonic_s is not None:
        age = float(now_monotonic_s) - live.monotonic_s
        if not math.isfinite(age) or age < 0 or age > _MAXIMUM_OBSERVATION_AGE_S:
            reasons.append("RESOURCE_PROBE_FAILED")
    if live.swap_delta > 0 or live.psi_full_delta > 0:
        reasons.append("SWAP_PRESSURE")
    if live.throttled:
        reasons.append("CPU_HEADROOM")
    if any(value <= 0 for value in live.capacity.values()):
        reasons.append("RESOURCE_PROBE_FAILED")
    for dimension in DIMENSIONS:
        capacity = live.capacity[dimension]
        observed = live.observed[dimension]
        if capacity - observed < 0.2 * capacity:
            reasons.append(_HEADROOM_CODES[dimension])
        if require_qualified_headroom and not headroom_ok(
            capacity, observed, live.remaining[dimension], live.error[dimension]
        ):
            reasons.append(_HEADROOM_CODES[dimension])
    return sorted(set(reasons))


class ResourceBudgetProvider:
    """Loads one approved profile and admits only exact-N qualified work."""

    def __init__(self) -> None:
        self._profile: ApprovedBudgetProfile | None = None
        self._profile_sha256: str | None = None
        self._qualifications: dict[str, ExactNQualification] = {}
        self._qualification_provider = ExactNQualificationProvider()

    @property
    def profile_sha256(self) -> str | None:
        return self._profile_sha256

    def load(self, path: Path, *, expected_sha256: str) -> ApprovedBudgetProfile:
        _require_sha256("expected_sha256", expected_sha256)
        document, digest = read_private_document(path, expected_sha256=expected_sha256)
        if digest != expected_sha256:
            raise ContractError("HASH_MISMATCH")
        profile = ApprovedBudgetProfile.from_document(document, raw_sha256=digest)
        self._profile = profile
        self._profile_sha256 = digest
        return profile

    def record_qualification(self, record: ExactNQualification) -> None:
        if not isinstance(record, ExactNQualification):
            raise ContractError("QUALIFICATION_TYPE")
        self._qualifications[record.raw_sha256] = record

    def _required_profile(self) -> ApprovedBudgetProfile:
        if self._profile is None or self._profile_sha256 is None:
            raise ContractError("BUDGET_PROFILE_UNAVAILABLE")
        return self._profile

    def admit_production(
        self,
        *,
        context: FixedProductionContext,
        current: RuntimeFingerprint,
        live: LiveResourceObservation,
        now_monotonic_s: float | None = None,
        stage: str = "startup",
    ) -> ResourceBudgetAdmission:
        if not isinstance(context, FixedProductionContext):
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        profile = self._required_profile()
        if context.profile_sha256 != self._profile_sha256:
            raise ContractError("BUDGET_PROFILE_UNAVAILABLE")
        if context.scope.execution_identity_sha256 != current.sha256:
            raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")
        if profile.execution_identity_sha256 != current.sha256:
            raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")
        if context.scope.execution_identity_sha256 != profile.execution_identity_sha256:
            raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")
        reasons: list[str] = []
        entry = profile.entry(context.scope.worker_count)
        if entry is None or entry.status != "APPROVED" or entry.qualification_sha256 is None:
            reasons.append("EXACT_N_UNQUALIFIED")
        elif stage not in entry.stages:
            reasons.append("EXACT_N_UNQUALIFIED")
        else:
            # D and J are the profile's qualified numbers for this exact N and stage;
            # the measured B and H can only be raised by the declared envelope.
            live = _conservative_stage_envelope(live, entry.stages[stage])
            if entry.qualification_sha256 != context.qualification_sha256:
                reasons.append("QUALIFICATION_EVIDENCE_INVALID")
            record = self._qualifications.get(entry.qualification_sha256)
            if record is None:
                reasons.append("QUALIFICATION_EVIDENCE_INVALID")
            else:
                decision = self._qualification_provider.verify(
                    record=record,
                    worker_count=context.scope.worker_count,
                    execution_identity_sha256=profile.execution_identity_sha256,
                    coverage_policy_sha256=profile.coverage_policy_sha256,
                )
                reasons.extend(decision.reason_codes)
        reasons.extend(_live_reasons(live, now_monotonic_s=now_monotonic_s))
        codes = tuple(sorted(set(reasons)))
        return ResourceBudgetAdmission(
            admitted=not codes,
            reason_codes=codes,
            worker_count=context.scope.worker_count,
            profile_sha256=self._profile_sha256,
            qualification_sha256=context.qualification_sha256,
            execution_identity_sha256=context.scope.execution_identity_sha256,
            observation_monotonic_s=live.monotonic_s,
        )

    def admit_measurement(
        self,
        *,
        context: MeasurementContext,
        current: RuntimeFingerprint,
        live: LiveResourceObservation,
        now_monotonic_s: float | None = None,
        stage: str = "startup",
    ) -> ResourceBudgetAdmission:
        if not isinstance(context, MeasurementContext):
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if context.scope.execution_identity_sha256 != current.sha256:
            raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")
        if stage not in _STAGES:
            raise ContractError("STAGE")
        # A candidate has no qualified D/J yet, so this safety admission claims none:
        # it requires the whole 80% envelope minus the measured background and tool
        # overhead, and the run itself is capped by the owned cgroup limits.
        codes = tuple(sorted(set(_live_reasons(
            live, now_monotonic_s=now_monotonic_s, require_qualified_headroom=False))))
        return ResourceBudgetAdmission(
            admitted=not codes,
            reason_codes=codes,
            worker_count=context.scope.worker_count,
            profile_sha256=None,
            qualification_sha256=None,
            execution_identity_sha256=current.sha256,
            observation_monotonic_s=live.monotonic_s,
        )


def issue_production_context(
    *,
    provider: ResourceBudgetProvider,
    scope: AllocationScope,
    profile_path: Path | None,
    expected_profile_sha256: str | None,
    promotion_path: Path | None,
    deployment_receipt_path: Path | None,
    control_binding: Mapping[str, object],
    authority: PromotionAuthority,
    installed_audit,
    current_identity_sha256: str,
    location_binding: Mapping[str, object],
) -> FixedProductionContext:
    """Issue the production context only from a fully verified external chain.

    M is re-read through the independent authority together with its operator and
    both review documents, and D's A1 audit, R identity and location binding must
    equal the trusted values presented here; a well-shaped hash is not authority.
    """

    from .resource_identity import FullByteAudit

    if not isinstance(provider, ResourceBudgetProvider):
        raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
    if scope.request_kind != "FIXED_PRODUCTION":
        raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
    if not isinstance(authority, PromotionAuthority):
        raise ContractError("PROMOTION_AUTHORITY_INVALID")
    if not isinstance(installed_audit, FullByteAudit):
        raise ContractError("INSTALLED_AUDIT")
    _require_sha256("current_identity_sha256", current_identity_sha256)
    if not isinstance(location_binding, Mapping) or not location_binding:
        raise ContractError("LOCATION_BINDING")
    if current_identity_sha256 != scope.execution_identity_sha256:
        raise ContractError("DEPLOYMENT_RECEIPT_IDENTITY_MISMATCH")
    if (
        profile_path is None
        or promotion_path is None
        or deployment_receipt_path is None
        or expected_profile_sha256 is None
        or not isinstance(control_binding, Mapping)
        or not control_binding
    ):
        raise ContractError("BUDGET_PROFILE_UNAVAILABLE")
    _require_sha256("expected_profile_sha256", expected_profile_sha256)
    profile = provider.load(profile_path, expected_sha256=expected_profile_sha256)
    entry = profile.entry(scope.worker_count)
    if entry is None or entry.status != "APPROVED" or entry.qualification_sha256 is None:
        raise ContractError("EXACT_N_UNQUALIFIED")
    record = provider._qualifications.get(entry.qualification_sha256)
    if record is None:
        raise ContractError("QUALIFICATION_EVIDENCE_INVALID")
    decision = provider._qualification_provider.verify(
        record=record, worker_count=scope.worker_count,
        execution_identity_sha256=profile.execution_identity_sha256,
        coverage_policy_sha256=profile.coverage_policy_sha256,
    )
    if not decision.qualified:
        raise ContractError(decision.reason_codes[0])
    promotion_path = Path(promotion_path)
    if promotion_path.resolve().is_relative_to(Path(profile_path).resolve().parent):
        raise ContractError("PROMOTION_NOT_INDEPENDENT")
    promotion, promotion_sha = read_private_document(promotion_path)
    _require_closed_promotion(
        promotion, authority=authority, profile_sha256=expected_profile_sha256,
        exact_worker_count=scope.worker_count)
    receipt, receipt_sha = read_private_document(deployment_receipt_path)
    _require_closed_deployment_receipt(receipt)
    if receipt["profile_sha256"] != expected_profile_sha256:
        raise ContractError("DEPLOYMENT_RECEIPT_PROFILE_MISMATCH")
    if receipt["promotion_sha256"] != promotion_sha:
        raise ContractError("DEPLOYMENT_RECEIPT_PROMOTION_MISMATCH")
    if receipt["installed_audit_sha256"] != installed_audit.sha256:
        raise ContractError("DEPLOYMENT_RECEIPT_AUDIT_MISMATCH")
    if receipt["execution_identity_sha256"] != current_identity_sha256:
        raise ContractError("DEPLOYMENT_RECEIPT_IDENTITY_MISMATCH")
    if canonical_sha256(dict(receipt["location_binding"])) != canonical_sha256(
        dict(location_binding)
    ):
        raise ContractError("DEPLOYMENT_RECEIPT_LOCATION_MISMATCH")
    if canonical_sha256(dict(control_binding)) != canonical_sha256(dict(location_binding)):
        raise ContractError("CONTROL_BINDING_MISMATCH")
    prefix = location_binding.get("prefix")
    if prefix is not None and str(installed_audit.prefix) != str(prefix):
        raise ContractError("AUDIT_LOCATION_MISMATCH")
    authority_sha256 = canonical_sha256(
        {
            "profile_sha256": expected_profile_sha256,
            "promotion_sha256": promotion_sha,
            "deployment_receipt_sha256": receipt_sha,
            "control_binding_sha256": canonical_sha256(dict(control_binding)),
        }
    )
    return FixedProductionContext(
        scope=scope,
        authority_sha256=authority_sha256,
        profile_sha256=expected_profile_sha256,
        qualification_sha256=entry.qualification_sha256,
        control_binding_sha256=canonical_sha256(dict(control_binding)),
        _issuer=_ISSUER,
    )


def issue_measurement_context(
    *,
    provider: ResourceBudgetProvider,
    scope: AllocationScope,
    authorization_path: Path,
    owner_binding: object,
) -> MeasurementContext:
    """Issue the one-shot measurement context; no approved profile is required."""

    if not isinstance(provider, ResourceBudgetProvider):
        raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
    if scope.request_kind != "MEASUREMENT":
        raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
    authorization_sha256 = hashlib.sha256(Path(authorization_path).read_bytes()).hexdigest()
    if isinstance(owner_binding, Mapping):
        owner_authorization = owner_binding.get("authorization_sha256")
        owned_scope = owner_binding.get("owned_scope_sha256")
    else:
        owner_authorization = getattr(owner_binding, "authorization_sha256", None)
        owned_scope = getattr(owner_binding, "owned_scope_sha256", None)
    if owner_authorization != authorization_sha256:
        raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
    _require_sha256("owned_scope_sha256", owned_scope)
    authority_sha256 = canonical_sha256(
        {"authorization_sha256": authorization_sha256, "owned_scope_sha256": owned_scope}
    )
    return MeasurementContext(
        scope=scope,
        authority_sha256=authority_sha256,
        authorization_sha256=authorization_sha256,
        owned_scope_sha256=owned_scope,
        _issuer=_ISSUER,
    )


def _issue_adaptive_context(
    *,
    scope: AllocationScope,
    pool_token_sha256: str,
    pool_generation: int,
    authority_sha256: str,
) -> AdaptiveAllocationContext:
    """Private issuer reserved for ProductionAdaptivePoolFactory (Task 8)."""

    if scope.request_kind != "ADAPTIVE":
        raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
    return AdaptiveAllocationContext(
        scope=scope,
        authority_sha256=_require_sha256("authority_sha256", authority_sha256),
        pool_token_sha256=_require_sha256("pool_token_sha256", pool_token_sha256),
        pool_generation=pool_generation,
        _issuer=_ISSUER,
    )


@dataclass(frozen=True, slots=True)
class FixedAdmissionRequest:
    """One exact-N admission question asked by any consumer adapter."""

    worker_count: int
    batch_id: str
    epoch: int
    execution_identity_sha256: str
    request_kind: str
    stage: str = "startup"

    def __post_init__(self) -> None:
        if type(self.worker_count) is not int or not 1 <= self.worker_count <= 8:
            raise ContractError("WORKER_COUNT")
        if not isinstance(self.batch_id, str) or not self.batch_id:
            raise ContractError("BATCH_ID")
        if type(self.epoch) is not int or self.epoch < 1:
            raise ContractError("EPOCH")
        _require_sha256("execution_identity_sha256", self.execution_identity_sha256)
        if self.request_kind not in _ALLOCATION_KINDS:
            raise ContractError("REQUEST_KIND")
        if self.stage not in _STAGES:
            raise ContractError("STAGE")


class FixedAdmissionGate:
    """The single provider seam shared by the Web probe, CLI prepare and the allocator."""

    def __init__(
        self,
        provider: ResourceBudgetProvider,
        *,
        context: FixedProductionContext | MeasurementContext | None = None,
        context_factory=None,
        current: RuntimeFingerprint | None = None,
        live: LiveResourceObservation | None = None,
        observation_source=None,
        fingerprint_source=None,
        now_monotonic_s: float | None = None,
        request_kind: str = "FIXED_PRODUCTION",
    ) -> None:
        if not isinstance(provider, ResourceBudgetProvider):
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if context is not None and not isinstance(
            context, (FixedProductionContext, MeasurementContext)
        ):
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if context_factory is not None and not callable(context_factory):
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if observation_source is not None and not callable(observation_source):
            raise ContractError("RESOURCE_PROBE_FAILED")
        if fingerprint_source is not None and not callable(fingerprint_source):
            raise ContractError("RESOURCE_PROBE_FAILED")
        if request_kind not in _ALLOCATION_KINDS:
            raise ContractError("REQUEST_KIND")
        self.provider = provider
        self.context = context
        self.context_factory = context_factory
        self.current = current
        self.live = live
        self.observation_source = observation_source
        self.fingerprint_source = fingerprint_source
        self.now_monotonic_s = now_monotonic_s
        self.request_kind = request_kind

    @property
    def execution_identity_sha256(self) -> str | None:
        return None if self.current is None else self.current.sha256

    def _fresh_current(self, request: FixedAdmissionRequest) -> RuntimeFingerprint | None:
        """Re-derive runtime bytes before every spawn/adopt; drift is a refusal."""

        if self.fingerprint_source is None:
            return self.current
        try:
            fresh = self.fingerprint_source()
        except ContractError:
            raise
        except Exception as error:  # noqa: BLE001 - an unreadable identity is not a pass
            raise ContractError("RESOURCE_PROBE_FAILED") from error
        if not isinstance(fresh, RuntimeFingerprint):
            raise ContractError("RUNTIME_FINGERPRINT")
        if fresh.sha256 != request.execution_identity_sha256:
            raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")
        if self.current is not None and fresh.sha256 != self.current.sha256:
            raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")
        return fresh

    def admit(self, request: FixedAdmissionRequest) -> ResourceBudgetAdmission:
        """Answer one admission question; a missing probe is never a pass."""

        live = self.observation_source() if self.observation_source is not None else self.live
        current = None
        if self.current is not None or self.fingerprint_source is not None:
            try:
                current = self._fresh_current(request)
            except ContractError as error:
                return ResourceBudgetAdmission(
                    admitted=False,
                    reason_codes=(error.code,),
                    worker_count=request.worker_count,
                    profile_sha256=self.provider.profile_sha256,
                    qualification_sha256=None,
                    execution_identity_sha256=request.execution_identity_sha256,
                    observation_monotonic_s=0.0 if live is None else live.monotonic_s,
                )
        self.current = current
        if self.current is None or live is None:
            return ResourceBudgetAdmission(
                admitted=False,
                reason_codes=("RESOURCE_PROBE_FAILED",),
                worker_count=request.worker_count,
                profile_sha256=self.provider.profile_sha256,
                qualification_sha256=None,
                execution_identity_sha256=request.execution_identity_sha256,
                observation_monotonic_s=0.0,
            )
        context = self.context
        if context is None and self.context_factory is not None:
            try:
                context = self.context_factory(request)
            except ContractError as error:
                # Exact-N/profile refusals are decisions, not crashes; a tampered
                # authority still raises from composition time.
                return ResourceBudgetAdmission(
                    admitted=False,
                    reason_codes=(error.code,),
                    worker_count=request.worker_count,
                    profile_sha256=self.provider.profile_sha256,
                    qualification_sha256=None,
                    execution_identity_sha256=request.execution_identity_sha256,
                    observation_monotonic_s=live.monotonic_s,
                )
        if request.request_kind == "MEASUREMENT":
            if not isinstance(context, MeasurementContext):
                raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
            if context.scope.worker_count != request.worker_count:
                raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
            return self.provider.admit_measurement(
                context=context, current=self.current, live=live,
                now_monotonic_s=self.now_monotonic_s, stage=request.stage)
        if not isinstance(context, FixedProductionContext):
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if context.scope.worker_count != request.worker_count:
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        return self.provider.admit_production(
            context=context, current=self.current, live=live,
            now_monotonic_s=self.now_monotonic_s, stage=request.stage)


# --- Independent promotion and deployment receipts (Task 14, offline) ---------------


def _write_private(path: Path, data: bytes) -> str:
    """Create one immutable private file and fsync it and its directory."""

    descriptor = os.open(Path(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(Path(path).parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return hashlib.sha256(data).hexdigest()


class PromotionAuthority:
    """Reads approvals only from an independent trusted directory, never a candidate tree."""

    def __init__(self, root: Path) -> None:
        root = Path(root)
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            raise ContractError("PROMOTION_AUTHORITY_INVALID")
        metadata = root.stat()
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) != 0o700:
            raise ContractError("PROMOTION_AUTHORITY_INVALID")
        self.root = root.resolve()

    def contains(self, path: Path) -> bool:
        try:
            return Path(path).resolve().is_relative_to(self.root)
        except OSError:
            return False

    def read_document(self, path: Path) -> tuple[dict, str]:
        if not self.contains(path):
            raise ContractError("PROMOTION_AUTHORITY_INVALID")
        return read_private_document(path)

    def read_named(self, name: str) -> tuple[dict, str]:
        """Resolve one recorded document by its single path name inside the root."""

        if not isinstance(name, str) or PATH_NAME_INVALID(name):
            raise ContractError(f"PROMOTION_DOCUMENTS: {name!r}")
        return self.read_document(self.root / name)


def _inside(directory: Path, path: Path) -> bool:
    try:
        return Path(path).resolve().is_relative_to(Path(directory).resolve())
    except OSError:
        return False


def publish_promotion(
    *,
    profile_path: Path,
    profile_sha256: str,
    operator_approval: Path,
    sol_result_review: Path,
    astra_profile_review: Path,
    measurement_audit,
    destination: Path,
    authority: PromotionAuthority,
) -> Path:
    """Append-only promotion record M: P + A0 + independent reviews + operator approval.

    Every document is re-read from the independent authority root and must carry the
    profile, A0 and target bindings; M records the authority names so the verifier can
    re-read the same bytes instead of trusting self-described hashes.
    """

    from .resource_identity import FullByteAudit

    _require_sha256("profile_sha256", profile_sha256)
    if not isinstance(measurement_audit, FullByteAudit):
        raise ContractError("MEASUREMENT_AUDIT")
    if not isinstance(authority, PromotionAuthority):
        raise ContractError("PROMOTION_AUTHORITY_INVALID")
    candidate_tree = Path(profile_path).parent
    documents = {}
    for name, path in (
        ("operator_approval", operator_approval),
        ("sol_result_review", sol_result_review),
        ("astra_profile_review", astra_profile_review),
    ):
        if _inside(candidate_tree, path):
            raise ContractError("PROMOTION_AUTHORITY_INVALID")
        if not authority.contains(path):
            raise ContractError("PROMOTION_AUTHORITY_INVALID")
        relative = Path(path).resolve().relative_to(authority.root)
        if PATH_NAME_INVALID(relative.as_posix()):
            raise ContractError("PROMOTION_DOCUMENTS")
        documents[name] = relative.as_posix()
    if not authority.contains(destination):
        raise ContractError("PROMOTION_AUTHORITY_INVALID")
    approval, approval_sha = authority.read_named(documents["operator_approval"])
    sol, sol_sha = authority.read_named(documents["sol_result_review"])
    astra, astra_sha = authority.read_named(documents["astra_profile_review"])
    audit_sha = measurement_audit.sha256
    _require_closed_fields(approval, _APPROVAL_FIELDS, "OPERATOR_APPROVAL")
    if approval["decision"] != "APPROVED" or approval["target"] != _APPROVAL_TARGET:
        raise ContractError("OPERATOR_APPROVAL_REQUIRED")
    if approval["profile_sha256"] != profile_sha256:
        raise ContractError("OPERATOR_APPROVAL_PROFILE_MISMATCH")
    if approval["measurement_audit_sha256"] != audit_sha:
        raise ContractError("OPERATOR_APPROVAL_AUDIT_MISMATCH")
    operator_uid = approval["operator_uid"]
    exact_n = approval["exact_worker_count"]
    if type(operator_uid) is not int or type(exact_n) is not int:
        raise ContractError("OPERATOR_APPROVAL_INCOMPLETE")
    for reviewer, document in (("sol", sol), ("astra", astra)):
        _require_closed_fields(document, _REVIEW_FIELDS, "PROMOTION_REVIEW")
        if document["result"] != "PASS":
            raise ContractError("INDEPENDENT_REVIEW_REQUIRED")
        if document["reviewer"] != reviewer or document["target"] != _REVIEW_TARGETS[reviewer]:
            raise ContractError("INDEPENDENT_REVIEW_TARGET")
        if document["profile_sha256"] != profile_sha256:
            raise ContractError("INDEPENDENT_REVIEW_PROFILE_MISMATCH")
        if document["measurement_audit_sha256"] != audit_sha:
            raise ContractError("INDEPENDENT_REVIEW_AUDIT_MISMATCH")
    promotion = {
        "schema_version": 2,
        "kind": "PROMOTION",
        "profile_sha256": profile_sha256,
        "exact_worker_count": exact_n,
        "operator_approval_uid": operator_uid,
        "operator_approval_sha256": approval_sha,
        "reviews": [
            {"reviewer": "sol", "result": "PASS", "sha256": sol_sha},
            {"reviewer": "astra", "result": "PASS", "sha256": astra_sha},
        ],
        "sol_result_review_sha256": sol_sha,
        "astra_profile_review_sha256": astra_sha,
        "measurement_audit": measurement_audit.as_document(),
        "measurement_audit_sha256": audit_sha,
        "documents": documents,
        "created_at_ns": time.time_ns(),
    }
    encoded = json.dumps(promotion, sort_keys=True, separators=(",", ":")).encode("utf-8")
    target = Path(destination)
    target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    _write_private(target, encoded)
    return target


_PROMOTION_FIELDS = (
    "schema_version", "kind", "profile_sha256", "exact_worker_count", "operator_approval_uid",
    "operator_approval_sha256", "reviews", "sol_result_review_sha256",
    "astra_profile_review_sha256", "measurement_audit", "measurement_audit_sha256",
    "documents", "created_at_ns",
)
_PROMOTION_DOCUMENT_KEYS = {
    "operator_approval": "operator_approval_sha256",
    "sol_result_review": "sol_result_review_sha256",
    "astra_profile_review": "astra_profile_review_sha256",
}
_REVIEW_FIELDS = (
    "schema_version", "kind", "reviewer", "result", "target", "profile_sha256",
    "measurement_audit_sha256",
)
_REVIEW_TARGETS = {"sol": "EXECUTION_RESULT", "astra": "PROFILE"}
_APPROVAL_FIELDS = (
    "schema_version", "kind", "operator_uid", "decision", "target", "exact_worker_count",
    "profile_sha256", "measurement_audit_sha256",
)
_APPROVAL_TARGET = "EXACT_N_PRODUCTION"
_DEPLOYMENT_RECEIPT_FIELDS = (
    "schema_version", "kind", "profile_sha256", "promotion_sha256", "installed_audit_sha256",
    "execution_identity_sha256", "location_binding", "created_at_ns",
)


def _require_closed_fields(
    document: Mapping[str, object], fields: Sequence[str], code: str
) -> None:
    unknown = set(document) - set(fields)
    missing = set(fields) - set(document)
    if unknown:
        raise ContractError(f"{code}_UNKNOWN_FIELD: {sorted(unknown)!r}")
    if missing:
        raise ContractError(f"{code}_MISSING_FIELD: {sorted(missing)!r}")


def _require_closed_deployment_receipt(document: Mapping[str, object]) -> None:
    if not isinstance(document, Mapping):
        raise ContractError("DEPLOYMENT_RECEIPT_INVALID")
    _require_closed_fields(document, _DEPLOYMENT_RECEIPT_FIELDS, "DEPLOYMENT_RECEIPT")
    if document["schema_version"] != 2 or document["kind"] != "DEPLOYMENT_RECEIPT":
        raise ContractError("DEPLOYMENT_RECEIPT_SCHEMA_VERSION")
    for name in ("profile_sha256", "promotion_sha256", "installed_audit_sha256",
                 "execution_identity_sha256"):
        _require_sha256(name, document[name])
    if not isinstance(document["location_binding"], Mapping) or not document["location_binding"]:
        raise ContractError("LOCATION_BINDING")


def _require_authority_document(
    *, authority: PromotionAuthority, name: str, expected_sha256: str, fields: Sequence[str],
    code: str, bindings: Mapping[str, object]
) -> dict:
    """Re-read one authority document and check every binding it must carry."""

    if not isinstance(name, str) or not name or PATH_NAME_INVALID(name):
        raise ContractError(f"PROMOTION_DOCUMENTS: {code}")
    document, digest = authority.read_named(name)
    if digest != expected_sha256:
        raise ContractError(f"{code}_HASH: {name}")
    if not isinstance(document, Mapping):
        raise ContractError(f"{code}_MAPPING: {name}")
    _require_closed_fields(document, fields, code)
    if document.get("schema_version") != 2:
        raise ContractError(f"{code}_SCHEMA_VERSION: {name}")
    for field_name, expected in bindings.items():
        if document.get(field_name) != expected:
            raise ContractError(f"{code}_BINDING: {name}.{field_name}")
    return dict(document)


def PATH_NAME_INVALID(name: str) -> bool:
    return name.startswith("/") or ".." in Path(name).parts or len(Path(name).parts) != 1


def _require_closed_promotion(
    document: Mapping[str, object], *, authority: PromotionAuthority,
    profile_sha256: str | None = None, exact_worker_count: int | None = None,
) -> None:
    """One closed schema2 validation shared by the verifier and the context issuer."""

    from .resource_identity import FullByteAudit

    if not isinstance(document, Mapping):
        raise ContractError("PROMOTION_INVALID")
    _require_closed_fields(document, _PROMOTION_FIELDS, "PROMOTION")
    if document["kind"] != "PROMOTION":
        raise ContractError("PROMOTION_INVALID")
    if document["schema_version"] != 2:
        raise ContractError("PROMOTION_SCHEMA_VERSION")
    if type(document["operator_approval_uid"]) is not int:
        raise ContractError("OPERATOR_APPROVAL_REQUIRED")
    if type(document["exact_worker_count"]) is not int or not (
        1 <= document["exact_worker_count"] <= 8
    ):
        raise ContractError("PROMOTION_EXACT_N")
    if profile_sha256 is not None and document["profile_sha256"] != profile_sha256:
        raise ContractError("PROMOTION_PROFILE_MISMATCH")
    if exact_worker_count is not None and document["exact_worker_count"] != exact_worker_count:
        raise ContractError("PROMOTION_EXACT_N_MISMATCH")
    if not isinstance(authority, PromotionAuthority):
        raise ContractError("PROMOTION_AUTHORITY_INVALID")
    reviews = document["reviews"]
    if not isinstance(reviews, (list, tuple)) or not reviews:
        raise ContractError("PROMOTION_REVIEWS")
    summary: dict[str, str] = {}
    for review in reviews:
        if not isinstance(review, Mapping) or review.get("result") != "PASS":
            raise ContractError("INDEPENDENT_REVIEW_REQUIRED")
        _require_sha256("review_sha256", review.get("sha256"))
        reviewer = str(review.get("reviewer", ""))
        if reviewer not in _REVIEW_TARGETS:
            raise ContractError("PROMOTION_REVIEWS")
        summary[reviewer] = str(review["sha256"])
    if set(summary) != set(_REVIEW_TARGETS):
        raise ContractError("PROMOTION_REVIEWS")
    documents = document["documents"]
    if not isinstance(documents, Mapping):
        raise ContractError("PROMOTION_DOCUMENTS")
    _require_closed_fields(documents, tuple(_PROMOTION_DOCUMENT_KEYS), "PROMOTION_DOCUMENTS")
    audit_document = document["measurement_audit"]
    audit = FullByteAudit.from_document(audit_document)
    audit_sha = _require_sha256("measurement_audit_sha256", document["measurement_audit_sha256"])
    if audit.sha256 != audit_sha:
        raise ContractError("PROMOTION_AUDIT_MISMATCH")
    for reviewer, target in _REVIEW_TARGETS.items():
        key = "sol_result_review" if reviewer == "sol" else "astra_profile_review"
        recorded = _require_sha256(f"{key}_sha256", document[_PROMOTION_DOCUMENT_KEYS[key]])
        if recorded != summary[reviewer]:
            raise ContractError("PROMOTION_REVIEWS")
        _require_authority_document(
            authority=authority, name=str(documents[key]), expected_sha256=recorded,
            fields=_REVIEW_FIELDS, code="PROMOTION_REVIEW",
            bindings={
                "reviewer": reviewer, "result": "PASS", "target": target,
                "profile_sha256": document["profile_sha256"],
                "measurement_audit_sha256": audit_sha,
            })
    _require_authority_document(
        authority=authority, name=str(documents["operator_approval"]),
        expected_sha256=_require_sha256(
            "operator_approval_sha256", document["operator_approval_sha256"]),
        fields=_APPROVAL_FIELDS, code="OPERATOR_APPROVAL",
        bindings={
            "decision": "APPROVED", "target": _APPROVAL_TARGET,
            "operator_uid": document["operator_approval_uid"],
            "exact_worker_count": document["exact_worker_count"],
            "profile_sha256": document["profile_sha256"],
            "measurement_audit_sha256": audit_sha,
        })


def verify_promotion(
    *, profile: ApprovedBudgetProfile, promotion_path: Path | None, authority: PromotionAuthority,
    execution_identity_sha256: str | None = None, exact_worker_count: int | None = None,
) -> None:
    """Verify M through the independent authority; a path alone is never approval."""

    if promotion_path is None:
        raise ContractError("BUDGET_PROFILE_UNAVAILABLE")
    if not isinstance(authority, PromotionAuthority):
        raise ContractError("PROMOTION_AUTHORITY_INVALID")
    document, _ = authority.read_document(Path(promotion_path))
    _require_closed_promotion(
        document, authority=authority, profile_sha256=profile.raw_sha256,
        exact_worker_count=exact_worker_count)
    if execution_identity_sha256 is not None:
        _require_sha256("execution_identity_sha256", execution_identity_sha256)
        if profile.execution_identity_sha256 != execution_identity_sha256:
            raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")


def build_deployment_receipt(
    *,
    promotion_path: Path,
    profile_sha256: str,
    installed_audit,
    execution_identity_sha256: str,
    location_binding: Mapping[str, object],
) -> Path:
    """Deployment receipt D binds M/P/A1/location; M itself never references D."""

    _require_sha256("profile_sha256", profile_sha256)
    _require_sha256("execution_identity_sha256", execution_identity_sha256)
    if not isinstance(location_binding, Mapping) or not location_binding:
        raise ContractError("LOCATION_BINDING")
    _, promotion_sha = read_private_document(Path(promotion_path), expected_sha256=None)
    document = {
        "schema_version": 2,
        "kind": "DEPLOYMENT_RECEIPT",
        "profile_sha256": profile_sha256,
        "promotion_sha256": promotion_sha,
        "installed_audit_sha256": installed_audit.sha256,
        "execution_identity_sha256": execution_identity_sha256,
        "location_binding": dict(location_binding),
        "created_at_ns": time.time_ns(),
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    target = Path(promotion_path).parent / "deployment-receipt.json"
    _write_private(target, encoded)
    return target


# --- Installed production composition (F2) -------------------------------------------

_AUTHORITY_ENV = {
    "profile": "SO101_VALIDATION_BUDGET_PROFILE",
    "profile_sha256": "SO101_VALIDATION_BUDGET_PROFILE_SHA256",
    "promotion": "SO101_VALIDATION_PROMOTION_RECORD",
    "promotion_root": "SO101_VALIDATION_PROMOTION_ROOT",
    "deployment_receipt": "SO101_VALIDATION_DEPLOYMENT_RECEIPT",
    "installed_audit": "SO101_VALIDATION_INSTALLED_AUDIT",
    "location_binding": "SO101_VALIDATION_LOCATION_BINDING",
    "qualifications": "SO101_VALIDATION_QUALIFICATION_PATHS",
    "identity": "SO101_VALIDATION_EXECUTION_IDENTITY",
    "runtime_config": "SO101_PARALLEL_RUNTIME_CONFIG",
    "provenance_binding": "SO101_VALIDATION_PROVENANCE_BINDING",
}


def compose_production_admission(
    *,
    environment: Mapping[str, str],
    live_observation: LiveResourceObservation | None = None,
    observation_source=None,
    current: RuntimeFingerprint | None = None,
    fingerprint_source=None,
    now_monotonic_s: float | None = None,
    control_binding: Mapping[str, object] | None = None,
    installed_audit=None,
    location_binding: Mapping[str, object] | None = None,
    authority: PromotionAuthority | None = None,
    config_path: Path | None = None,
    source_root: Path | None = None,
    install_prefix: Path | None = None,
    host_probe=None,
    inventory_reader=None,
) -> FixedAdmissionGate | None:
    """Compose the shared gate from the full installed P/Q/M/D authority.

    Returns None only when the environment declares no authority at all, which the
    consumers report as BUDGET_PROFILE_UNAVAILABLE. A partially declared, unreadable
    or mismatching authority raises instead of silently degrading; the current runtime
    identity is recomputed from real bytes and refreshed before every admission.
    """

    from .resource_identity import FullByteAudit, verify_runtime_identity

    values = {key: environment.get(name) for key, name in _AUTHORITY_ENV.items()}
    if not any(values.values()):
        return None
    missing = sorted(key for key, value in values.items() if not value)
    if missing:
        raise ContractError(f"BUDGET_PROFILE_UNAVAILABLE: incomplete authority {missing}")
    identity = _require_sha256("execution_identity_sha256", values["identity"])
    if authority is None:
        authority = PromotionAuthority(Path(values["promotion_root"]))
    if installed_audit is None:
        document, _ = read_private_document(Path(values["installed_audit"]))
        installed_audit = FullByteAudit.from_document(document)
    if not isinstance(installed_audit, FullByteAudit):
        raise ContractError("INSTALLED_AUDIT")
    if location_binding is None:
        location_binding, _ = read_private_document(Path(values["location_binding"]))
    if not isinstance(location_binding, Mapping) or not location_binding:
        raise ContractError("LOCATION_BINDING")
    if config_path is None:
        config_path = Path(values["runtime_config"])
    binding = dict(control_binding or location_binding)

    def derive_identity() -> RuntimeFingerprint:
        fingerprint = build_runtime_fingerprint_from_environment(
            environment, identity=identity, config_path=config_path, source_root=source_root,
            install_prefix=install_prefix, host_probe=host_probe,
            inventory_reader=inventory_reader)
        return fingerprint

    if current is None:
        current = derive_identity()
    else:
        verify_runtime_identity(current, identity)
    if fingerprint_source is None:
        fingerprint_source = derive_identity

    provider = ResourceBudgetProvider()
    provider.load(Path(values["profile"]), expected_sha256=values["profile_sha256"])
    try:
        qualifications = json.loads(values["qualifications"])
    except ValueError as error:
        raise ContractError("QUALIFICATION_EVIDENCE_INVALID") from error
    if not isinstance(qualifications, Mapping) or not qualifications:
        raise ContractError("QUALIFICATION_EVIDENCE_INVALID")
    for count, qualification_path in qualifications.items():
        if not str(count).isdigit():
            raise ContractError("QUALIFICATION_EVIDENCE_INVALID")
        document, digest = read_private_document(Path(qualification_path))
        provider.record_qualification(
            ExactNQualification.from_document(document, raw_sha256=digest))

    def context_factory(request: FixedAdmissionRequest) -> FixedProductionContext:
        scope = AllocationScope(
            batch_id=request.batch_id,
            epoch=request.epoch,
            worker_count=request.worker_count,
            request_kind="FIXED_PRODUCTION",
            execution_identity_sha256=request.execution_identity_sha256,
        )
        current_identity = verify_runtime_identity(derive_identity(), identity)
        if current_identity != request.execution_identity_sha256:
            raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")
        return issue_production_context(
            provider=provider,
            scope=scope,
            profile_path=Path(values["profile"]),
            expected_profile_sha256=values["profile_sha256"],
            promotion_path=Path(values["promotion"]),
            deployment_receipt_path=Path(values["deployment_receipt"]),
            control_binding=binding,
            authority=authority,
            installed_audit=installed_audit,
            current_identity_sha256=current_identity,
            location_binding=location_binding,
        )

    return FixedAdmissionGate(
        provider,
        context_factory=context_factory,
        current=current,
        live=live_observation,
        observation_source=observation_source,
        fingerprint_source=fingerprint_source,
        now_monotonic_s=now_monotonic_s,
        request_kind="FIXED_PRODUCTION",
    )


def worker_count_availability(
    gate: FixedAdmissionGate | None,
    *,
    worker_counts: Sequence[int],
    batch_id: str,
    execution_identity_sha256: str,
) -> tuple[dict[str, object], ...]:
    """Derive per-N availability from provider decisions, never from literals."""

    entries = []
    for worker_count in worker_counts:
        if gate is None:
            entries.append({
                "worker_count": worker_count, "selectable": False,
                "status": "NOT_MEASURED",
                "reason_codes": ("BUDGET_PROFILE_UNAVAILABLE",),
                "profile_sha256": None, "qualification_sha256": None,
            })
            continue
        decision = gate.admit(FixedAdmissionRequest(
            worker_count=worker_count, batch_id=batch_id, epoch=1,
            execution_identity_sha256=execution_identity_sha256,
            request_kind=gate.request_kind))
        status = "APPROVED" if decision.admitted else (
            "NOT_MEASURED" if "BUDGET_PROFILE_UNAVAILABLE" in decision.reason_codes
            else "REJECTED")
        entries.append({
            "worker_count": worker_count,
            "selectable": decision.admitted,
            "status": status,
            "reason_codes": decision.reason_codes,
            "profile_sha256": decision.profile_sha256,
            "qualification_sha256": decision.qualification_sha256,
        })
    return tuple(entries)


# --- Effective host observation and derived runtime identity (R3) --------------------

_CGROUP_ROOT = Path("/sys/fs/cgroup")
_NVML_DEVICE_LIMIT = 16
_RUNTIME_FACT_FIELDS = (
    "cgroup", "container_marker", "cpu_model", "cpu_host_cores", "cpuset",
    "cpu_quota_core_equivalent", "cuda_visible_devices", "gpu_index", "gpu_name",
    "gpu_total_bytes", "gpu_uuid", "install_kind", "install_prefix", "kernel",
    "mem_total_bytes", "mujoco_gl", "provenance_binding_sha256", "python",
    "ros_domain_id", "source_commit", "swap_total_bytes", "thread_environment",
)


@dataclass(frozen=True, slots=True)
class HostFacts:
    """Typed low-level host/container facts; the only replaceable port in tests.

    Every field is read from the kernel, the container cgroup tree or NVML. Nothing
    here is a policy literal: `attributed` reports whether the probe could enumerate
    the consumers it needs, and the capacities are effective (cpuset/quota) values.
    """

    mem_total_bytes: int
    mem_available_bytes: int
    swap_total_bytes: int
    swap_pages: int
    psi_full_s: float
    cpu_capacity: float
    cpu_host_cores: int
    cpu_set_used_core_equivalent: float
    cpu_host_used_core_equivalent: float
    cpu_quota_core_equivalent: float | None
    cpuset: str
    nr_throttled: int
    gpu_index: int
    gpu_name: str
    gpu_uuid: str
    gpu_total_bytes: float
    gpu_used_bytes: float
    gpu_consumers: tuple[int, ...]
    same_uid_pids: tuple[int, ...]
    own_tree_rss_bytes: int
    own_tree_gpu_bytes: float
    attributed: bool
    facts: Mapping[str, object]

    def __post_init__(self) -> None:
        for name in ("mem_total_bytes", "mem_available_bytes", "swap_total_bytes",
                     "cpu_host_cores", "nr_throttled", "own_tree_rss_bytes"):
            value = getattr(self, name)
            if type(value) is not int or value < 0:
                raise ContractError(f"HOST_FACT_INTEGER: {name}")
        if self.mem_total_bytes <= 0:
            raise ContractError("HOST_FACT_INTEGER: mem_total_bytes")
        for name in ("psi_full_s", "cpu_capacity", "cpu_set_used_core_equivalent",
                     "cpu_host_used_core_equivalent", "gpu_total_bytes", "gpu_used_bytes",
                     "own_tree_gpu_bytes"):
            value = getattr(self, name)
            if not isinstance(value, (int, float)) or not math.isfinite(float(value)) \
                    or float(value) < 0:
                raise ContractError(f"HOST_FACT_FINITE: {name}")
        if not isinstance(self.attributed, bool):
            raise ContractError("HOST_FACT_ATTRIBUTION")
        if not isinstance(self.facts, Mapping) or not self.facts:
            raise ContractError("RUNTIME_FACTS")
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))
        object.__setattr__(self, "gpu_consumers", tuple(int(item) for item in self.gpu_consumers))
        object.__setattr__(self, "same_uid_pids", tuple(int(item) for item in self.same_uid_pids))


def _read_meminfo_values() -> dict[str, int]:
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        if rest.strip().endswith("kB"):
            values[key] = int(rest.split()[0]) * 1024
    if "MemTotal" not in values or "MemAvailable" not in values:
        raise ContractError("RESOURCE_PROBE_FAILED")
    return values


def _read_swap_pages() -> int:
    total = 0
    for line in Path("/proc/vmstat").read_text().splitlines():
        name, _, value = line.partition(" ")
        if name in ("pswpin", "pswpout"):
            total += int(value)
    return total


def _read_psi_full_s() -> float:
    try:
        for line in Path("/proc/pressure/memory").read_text().splitlines():
            if line.startswith("full "):
                for token in line.split()[1:]:
                    if token.startswith("total="):
                        return float(token.split("=", 1)[1]) / 1_000_000.0
    except OSError:
        return 0.0
    return 0.0


def _cgroup_ancestors() -> tuple[Path, ...]:
    """Every ancestor cgroup of this process, nearest first (no sudo, no tmpfs)."""

    try:
        entry = next(
            line.split("::", 1)[1]
            for line in Path("/proc/self/cgroup").read_text().splitlines()
            if line.startswith("0::")
        )
    except (OSError, StopIteration) as error:
        raise ContractError("RESOURCE_PROBE_FAILED") from error
    node = _CGROUP_ROOT / entry.strip().lstrip("/")
    ancestors = []
    while node.is_dir() and node != _CGROUP_ROOT.parent:
        ancestors.append(node)
        if node == _CGROUP_ROOT:
            break
        node = node.parent
    if not ancestors:
        raise ContractError("RESOURCE_PROBE_FAILED")
    return tuple(ancestors)


def _parse_cpu_range(value: str) -> set[int]:
    cpus: set[int] = set()
    for part in value.strip().split(","):
        if not part:
            continue
        if "-" in part:
            low, _, high = part.partition("-")
            cpus.update(range(int(low), int(high) + 1))
        else:
            cpus.add(int(part))
    return cpus


def _effective_cpuset(ancestors: Sequence[Path]) -> set[int]:
    allowed = set(os.sched_getaffinity(0))
    for node in ancestors:
        try:
            text = (node / "cpuset.cpus.effective").read_text().strip()
        except OSError:
            continue
        if text:
            allowed &= _parse_cpu_range(text)
    return allowed


def _quota_core_equivalent(ancestors: Sequence[Path]) -> float | None:
    core_equivalent: float | None = None
    for node in ancestors:
        try:
            quota, _, period = (node / "cpu.max").read_text().split()
        except (OSError, ValueError):
            continue
        if quota == "max":
            continue
        share = float(quota) / float(period)
        core_equivalent = share if core_equivalent is None else min(core_equivalent, share)
    return core_equivalent


def _cgroup_counters(ancestors: Sequence[Path]) -> tuple[int, int]:
    """Cumulative (usage_usec, nr_throttled) of the nearest readable cgroup."""

    for node in ancestors:
        try:
            values = dict(
                line.split()[:2] for line in (node / "cpu.stat").read_text().splitlines()
                if len(line.split()) == 2
            )
        except OSError:
            continue
        return int(values.get("usage_usec", 0)), int(values.get("nr_throttled", 0))
    raise ContractError("RESOURCE_PROBE_FAILED")


def _cpu_ticks() -> tuple[dict[int, int], int]:
    """Per-CPU busy ticks plus the whole-host busy total from /proc/stat."""

    per_cpu: dict[int, int] = {}
    host_total = 0
    for line in Path("/proc/stat").read_text().splitlines():
        if not line.startswith("cpu"):
            continue
        name, _, rest = line.partition(" ")
        fields = [int(value) for value in rest.split()]
        if len(fields) < 5:
            continue
        busy = sum(fields[:3]) + sum(fields[5:8]) if len(fields) >= 8 else sum(fields[:3])
        if name == "cpu":
            host_total = busy
        else:
            per_cpu[int(name[3:])] = busy
    if not per_cpu:
        raise ContractError("RESOURCE_PROBE_FAILED")
    return per_cpu, host_total


def _cpu_window(cpus: set[int], window_s: float) -> tuple[float, float]:
    if window_s <= 0:
        return 0.0, 0.0
    ticks = os.sysconf("SC_CLK_TCK")
    before_cpu, before_host = _cpu_ticks()
    before_monotonic = time.monotonic()
    time.sleep(window_s)
    after_cpu, after_host = _cpu_ticks()
    elapsed = time.monotonic() - before_monotonic
    if elapsed <= 0:
        raise ContractError("RESOURCE_PROBE_FAILED")
    scale = float(ticks) * elapsed
    set_delta = sum(
        max(0, after_cpu.get(cpu, 0) - before_cpu.get(cpu, 0)) for cpu in sorted(cpus))
    return set_delta / scale, max(0, after_host - before_host) / scale


def _same_uid_consumers(uid: int) -> tuple[tuple[int, ...], int]:
    page = os.sysconf("SC_PAGE_SIZE")
    pids = []
    rss = 0
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            status = (entry / "status").read_text()
            fields = dict(
                line.split(":", 1) for line in status.splitlines() if ":" in line)
            if int(fields["Uid"].split()[0]) != uid:
                continue
            resident = int((entry / "statm").read_text().split()[1])
        except (OSError, KeyError, ValueError, IndexError):
            continue
        pids.append(int(entry.name))
        rss += resident * page
    return tuple(sorted(pids)), rss


class _NvmlMemory(ctypes.Structure):
    _fields_ = [
        ("total", ctypes.c_ulonglong),
        ("free", ctypes.c_ulonglong),
        ("used", ctypes.c_ulonglong),
    ]


class _NvmlProcess(ctypes.Structure):
    _fields_ = [
        ("pid", ctypes.c_uint),
        ("gpu_instance_id", ctypes.c_uint),
        ("compute_instance_id", ctypes.c_uint),
        ("used_gpu_memory", ctypes.c_ulonglong),
    ]


def _nvml_binding():
    """The system NVML library directly; no extra dependency and no shell-out."""

    for name in ("libnvidia-ml.so.1", "libnvidia-ml.so"):
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
    return None


def _nvml_device(device_index: int, uid: int):
    """Whole-device NVML facts including every consumer, or None when unreadable."""

    del uid
    library = _nvml_binding()
    if library is None:
        return None
    try:
        if library.nvmlInit_v2() != 0:
            return None
        count = ctypes.c_uint()
        if library.nvmlDeviceGetCount_v2(ctypes.byref(count)) != 0 or count.value <= 0:
            return None
        if device_index >= count.value:
            return None
        handle = ctypes.c_void_p()
        if library.nvmlDeviceGetHandleByIndex_v2(device_index, ctypes.byref(handle)) != 0:
            return None
        memory = _NvmlMemory()
        if library.nvmlDeviceGetMemoryInfo(handle, ctypes.byref(memory)) != 0:
            return None
        name = ctypes.create_string_buffer(96)
        library.nvmlDeviceGetName(handle, name, len(name))
        uuid = ctypes.create_string_buffer(96)
        library.nvmlDeviceGetUUID(handle, uuid, len(uuid))
        consumers: set[int] = set()
        for symbol, structure in (
            ("nvmlDeviceGetComputeRunningProcesses_v2", _NvmlProcess),
            ("nvmlDeviceGetGraphicsRunningProcesses_v2", _NvmlProcess),
        ):
            query = getattr(library, symbol, None)
            if query is None:
                continue
            capacity = ctypes.c_uint(64)
            buffer = (structure * 64)()
            if query(handle, ctypes.byref(capacity), buffer) != 0:
                continue
            for index in range(min(capacity.value, 64)):
                consumers.add(int(buffer[index].pid))
    except Exception:  # noqa: BLE001 - any NVML failure means no GPU attribution
        return None
    finally:
        try:
            library.nvmlShutdown()
        except Exception:  # noqa: BLE001
            pass
    return {
        "name": name.value.decode("utf-8", "replace"),
        "uuid": uuid.value.decode("utf-8", "replace"),
        "total_bytes": float(memory.total),
        "used_bytes": float(memory.used),
        "consumers": tuple(sorted(consumers)),
    }


def read_nvml_device(device_index: int = 0) -> Mapping[str, object] | None:
    """Public whole-device NVML read; None when the device cannot be inspected."""

    return _nvml_device(int(device_index), os.getuid())


def probe_host_facts(
    environment: Mapping[str, str] | None = None, *,
    gpu_device_index: int = 0, cpu_window_s: float = 0.1, uid: int | None = None,
) -> HostFacts:
    """Read effective capacities, background usage and attribution from the kernel."""

    environment = dict(os.environ if environment is None else environment)
    uid = os.getuid() if uid is None else int(uid)
    try:
        memory = _read_meminfo_values()
        ancestors = _cgroup_ancestors()
        swap_pages = _read_swap_pages()
        psi_full_s = _read_psi_full_s()
        cpuset = _effective_cpuset(ancestors)
        quota = _quota_core_equivalent(ancestors)
        usage_usec, nr_throttled = _cgroup_counters(ancestors)
        del usage_usec
        set_used, host_used = _cpu_window(cpuset, float(cpu_window_s))
    except ContractError:
        raise
    except Exception as error:  # noqa: BLE001 - an unreadable probe is never a pass
        raise ContractError("RESOURCE_PROBE_FAILED") from error
    pids, _ = _same_uid_consumers(uid)
    device = _nvml_device(gpu_device_index, uid)
    cpu_capacity = float(len(cpuset)) if cpuset else 0.0
    if quota is not None:
        cpu_capacity = min(cpu_capacity, float(quota)) if cpu_capacity else float(quota)
    if cpu_capacity <= 0:
        raise ContractError("RESOURCE_PROBE_FAILED")
    own_rss = _own_tree_rss()
    facts: dict[str, object] = {
        "cgroup": str(ancestors[0]),
        "container_marker": _container_marker(ancestors[0]),
        "cpu_model": _cpu_model(),
        "cpu_host_cores": len(os.sched_getaffinity(0)) or (os.cpu_count() or 0),
        "cpuset": ",".join(str(cpu) for cpu in sorted(cpuset)),
        "cpu_quota_core_equivalent": None if quota is None else round(float(quota), 6),
        "cuda_visible_devices": environment.get("CUDA_VISIBLE_DEVICES", ""),
        "gpu_index": int(gpu_device_index),
        "gpu_name": "" if device is None else device["name"],
        "gpu_total_bytes": 0.0 if device is None else device["total_bytes"],
        "gpu_uuid": "" if device is None else device["uuid"],
        "install_kind": "", "install_prefix": "", "provenance_binding_sha256": "",
        "kernel": platform.release(),
        "mem_total_bytes": int(memory["MemTotal"]),
        "mujoco_gl": environment.get("MUJOCO_GL", ""),
        "python": platform.python_version(),
        "ros_domain_id": environment.get("ROS_DOMAIN_ID", ""),
        "source_commit": "",
        "swap_total_bytes": int(memory.get("SwapTotal", 0)),
        "thread_environment": {
            name: environment.get(name, "")
            for name in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS",
                         "TORCH_NUM_THREADS", "NUMEXPR_NUM_THREADS")
        },
    }
    return HostFacts(
        mem_total_bytes=int(memory["MemTotal"]),
        mem_available_bytes=int(memory["MemAvailable"]),
        swap_total_bytes=int(memory.get("SwapTotal", 0)),
        swap_pages=int(swap_pages),
        psi_full_s=float(psi_full_s),
        cpu_capacity=cpu_capacity,
        cpu_host_cores=int(facts["cpu_host_cores"]),
        cpu_set_used_core_equivalent=round(float(set_used), 6),
        cpu_host_used_core_equivalent=round(float(host_used), 6),
        cpu_quota_core_equivalent=None if quota is None else float(quota),
        cpuset=str(facts["cpuset"]),
        nr_throttled=int(nr_throttled),
        gpu_index=int(gpu_device_index),
        gpu_name=str(facts["gpu_name"]),
        gpu_uuid=str(facts["gpu_uuid"]),
        gpu_total_bytes=0.0 if device is None else float(device["total_bytes"]),
        gpu_used_bytes=0.0 if device is None else float(device["used_bytes"]),
        gpu_consumers=() if device is None else tuple(device["consumers"]),
        same_uid_pids=pids,
        own_tree_rss_bytes=own_rss,
        own_tree_gpu_bytes=0.0,
        attributed=device is not None and bool(cpuset),
        facts=facts,
    )


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.startswith("model name"):
                return line.split(":", 1)[1].strip()
    except OSError:
        return ""
    return ""


def _container_marker(cgroup_path: Path) -> str:
    if Path("/.dockerenv").exists() or "docker" in str(cgroup_path):
        return "docker"
    if "kubepods" in str(cgroup_path):
        return "kubernetes"
    return "none"


def _own_tree_rss() -> int:
    """Resident bytes of the measurement/owner tree, read child by child."""

    page = os.sysconf("SC_PAGE_SIZE")
    pids = {os.getpid()}
    for task in Path("/proc/self/task").glob("*/children"):
        try:
            pids.update(int(item) for item in task.read_text().split())
        except (OSError, ValueError):
            continue
    total = 0
    for pid in sorted(pids):
        try:
            total += int(Path(f"/proc/{pid}/statm").read_text().split()[1]) * page
        except (OSError, ValueError, IndexError):
            continue
    if total <= 0:
        raise ContractError("RESOURCE_PROBE_FAILED")
    return total


class LiveObservationSource:
    """Fresh, attributed whole-host observation; deltas come from real counters."""

    def __init__(
        self, *, environment: Mapping[str, str] | None = None, gpu_device_index: int = 0,
        host_probe=None, clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if host_probe is not None and not callable(host_probe):
            raise ContractError("RESOURCE_PROBE_FAILED")
        self.environment = dict(os.environ if environment is None else environment)
        self.gpu_device_index = int(gpu_device_index)
        self._host_probe = host_probe
        self._clock = clock
        self._previous: tuple[int, float, int] | None = None

    def _facts(self) -> HostFacts:
        if self._host_probe is not None:
            return self._host_probe()
        return probe_host_facts(self.environment, gpu_device_index=self.gpu_device_index)

    def __call__(self) -> LiveResourceObservation:
        facts = self._facts()
        previous = self._previous
        counters = (facts.swap_pages, facts.psi_full_s, facts.nr_throttled)
        self._previous = counters
        if previous is None:
            swap_delta, psi_delta, throttle_delta = 0, 0.0, 0
        else:
            swap_delta = max(0, facts.swap_pages - previous[0])
            psi_delta = max(0.0, facts.psi_full_s - previous[1])
            throttle_delta = max(0, facts.nr_throttled - previous[2])
        background = {
            "ram_bytes": float(facts.mem_total_bytes - facts.mem_available_bytes),
            "gpu_bytes": float(facts.gpu_used_bytes),
            "cpu_core_equivalent": float(facts.cpu_set_used_core_equivalent),
        }
        tool_overhead = {
            "ram_bytes": float(facts.own_tree_rss_bytes),
            "gpu_bytes": float(facts.own_tree_gpu_bytes),
            "cpu_core_equivalent": 0.0,
        }
        capacity = {
            "ram_bytes": float(facts.mem_total_bytes),
            "gpu_bytes": float(facts.gpu_total_bytes),
            "cpu_core_equivalent": float(facts.cpu_capacity),
        }
        if any(value <= 0 for value in capacity.values()):
            raise ContractError("RESOURCE_PROBE_FAILED")
        observed = {
            name: float(background[name] + tool_overhead[name]) for name in DIMENSIONS
        }
        return LiveResourceObservation(
            monotonic_s=float(self._clock()),
            capacity=capacity,
            observed=observed,
            background=background,
            tool_overhead=tool_overhead,
            remaining={name: 0.0 for name in DIMENSIONS},
            error={name: 0.0 for name in DIMENSIONS},
            attribution_complete=bool(facts.attributed),
            swap_delta=int(swap_delta),
            psi_full_delta=float(psi_delta),
            throttled=bool(throttle_delta > 0),
        )


def build_live_observation(*, environment: Mapping[str, str] | None = None) -> LiveResourceObservation:
    """Fresh effective observation for admission; fail closed if unreadable."""

    return LiveObservationSource(environment=environment)()


def _conservative_stage_envelope(
    live: LiveResourceObservation, envelope: StageEnvelope
) -> LiveResourceObservation:
    """Pre-spawn `B+H+D+J`: never lower a measured value with a declared one."""

    background = {
        name: max(live.background[name], float(envelope.background[name]))
        for name in DIMENSIONS
    }
    tool_overhead = {
        name: max(live.tool_overhead[name], float(envelope.tool_overhead[name]))
        for name in DIMENSIONS
    }
    remaining = {
        name: max(live.remaining[name], float(envelope.demand[name])) for name in DIMENSIONS
    }
    error = {
        name: max(live.error[name], float(envelope.uncertainty[name]))
        for name in DIMENSIONS
    }
    observed = {
        name: max(live.observed[name], background[name] + tool_overhead[name])
        for name in DIMENSIONS
    }
    return replace(
        live, background=background, tool_overhead=tool_overhead, remaining=remaining,
        error=error, observed=observed)


# --- Derived runtime fingerprint (R) --------------------------------------------------

_INVENTORY_PATTERNS = {
    "source": (
        "src/so101_demo_py/src/parallel_batch/*.py",
        "src/so101_demo_py/src/cli/mujoco_parallel_batch.py",
        "src/so101_demo_py/src/cli/measure_parallel_resources.py",
        "src/so101_teleop/so101_teleop/expert_validation/*.py",
    ),
    "installed": (
        "so101_demo_py/lib/python*/site-packages/so101_demo/parallel_batch/*.py",
        "so101_demo_py/lib/python*/site-packages/so101_demo/cli/mujoco_parallel_batch.py",
        "so101_demo_py/lib/python*/site-packages/so101_demo/cli/measure_parallel_resources.py",
        "so101_teleop/lib/python*/site-packages/so101_teleop/expert_validation/*.py",
    ),
}


def default_inventory_reader(root: Path, kind: str) -> dict[str, bytes]:
    """Read the declared execution files under one root; a missing set is a refusal."""

    root = Path(root)
    if kind not in _INVENTORY_PATTERNS:
        raise ContractError(f"INVENTORY_KIND: {kind}")
    files: dict[str, bytes] = {}
    for pattern in _INVENTORY_PATTERNS[kind]:
        for path in sorted(root.glob(pattern)):
            if not path.is_file() or path.is_symlink():
                continue
            logical = (path.relative_to(root).as_posix() if kind == "source"
                       else path.as_posix().split("/site-packages/", 1)[-1])
            files[logical] = path.read_bytes()
    if not files:
        raise ContractError(f"INVENTORY_UNAVAILABLE: {kind}")
    return files


def build_runtime_fingerprint_from_environment(
    environment: Mapping[str, str], *, identity: str | None = None,
    config_path: Path | None = None, source_root: Path | None = None,
    install_prefix: Path | None = None, host_probe=None, inventory_reader=None,
) -> RuntimeFingerprint:
    """Recompute R from verified config/inventory/hardware bytes, then check it."""

    import yaml

    from .resource_identity import (
        build_inventory, build_runtime_fingerprint, verify_runtime_identity)

    environment = dict(environment)
    facts_source = host_probe or probe_host_facts
    reader = inventory_reader or default_inventory_reader
    binding_path = environment.get("SO101_VALIDATION_PROVENANCE_BINDING")
    binding: dict[str, object] = {}
    if binding_path:
        binding, binding_sha = read_private_document(Path(binding_path))
    else:
        binding_sha = ""
    if source_root is None:
        source_root = binding.get("source_root") or environment.get(
            "SO101_VALIDATION_SOURCE_ROOT")
    if install_prefix is None:
        install_prefix = binding.get("install_prefix") or environment.get(
            "SO101_VALIDATION_INSTALL_PREFIX")
    if config_path is None:
        configured = environment.get("SO101_PARALLEL_RUNTIME_CONFIG")
        config_path = Path(configured) if configured else None
    if config_path is None or source_root is None or install_prefix is None:
        raise ContractError("SEMANTIC_CONFIG_IDENTITY_REQUIRED")
    config_path = Path(config_path)
    if not config_path.is_file():
        raise ContractError("CONFIG_READ_FAILED")
    document = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    facts = dict(facts_source(environment).facts)
    facts.update({
        "install_kind": str(binding.get("install_kind", "")),
        "install_prefix": str(install_prefix),
        "provenance_binding_sha256": str(binding_sha),
        "source_commit": str(binding.get("source_commit", "")),
    })
    fingerprint = build_runtime_fingerprint(
        config=document,
        source_inventory=build_inventory(reader(Path(source_root), "source")),
        installed_inventory=build_inventory(reader(Path(install_prefix), "installed")),
        runtime_facts=facts,
    )
    verify_runtime_identity(fingerprint, identity)
    return fingerprint
