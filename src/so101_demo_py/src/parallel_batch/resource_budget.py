"""Exact-N resource admission: closed contexts, arithmetic, profiles and authorities.

This module is the single resource gate shared by the production consumers. It
never computes headroom from a per-consumer formula and never turns a factory
token into an approval: every issuance re-reads the external authority bytes.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
from dataclasses import dataclass, field, fields
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

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
            if set(self.stages) != set(_STAGES):
                raise ContractError("ENTRY_STAGE_COVERAGE")
        if self.status == "APPROVED":
            if self.qualification_sha256 is None or self.review_reference is None:
                raise ContractError("APPROVED_ENTRY_INCOMPLETE")
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
    live: LiveResourceObservation, *, now_monotonic_s: float | None
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
        if not headroom_ok(capacity, observed, live.remaining[dimension], live.error[dimension]):
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
        else:
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
    ) -> ResourceBudgetAdmission:
        if not isinstance(context, MeasurementContext):
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if context.scope.execution_identity_sha256 != current.sha256:
            raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")
        codes = tuple(sorted(set(_live_reasons(live, now_monotonic_s=now_monotonic_s))))
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
) -> FixedProductionContext:
    """Issue the production context only from an externally verified chain."""

    if not isinstance(provider, ResourceBudgetProvider):
        raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
    if scope.request_kind != "FIXED_PRODUCTION":
        raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
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
    if promotion.get("schema_version") != 2:
        raise ContractError("PROMOTION_SCHEMA_VERSION")
    if promotion.get("profile_sha256") != expected_profile_sha256:
        raise ContractError("PROMOTION_PROFILE_MISMATCH")
    if promotion.get("exact_worker_count") != scope.worker_count:
        raise ContractError("PROMOTION_EXACT_N_MISMATCH")
    if type(promotion.get("operator_approval_uid")) is not int:
        raise ContractError("PROMOTION_OPERATOR_APPROVAL")
    reviews = promotion.get("reviews")
    if not isinstance(reviews, (list, tuple)) or not reviews:
        raise ContractError("PROMOTION_REVIEWS")
    receipt, receipt_sha = read_private_document(deployment_receipt_path)
    if receipt.get("schema_version") != 2:
        raise ContractError("DEPLOYMENT_RECEIPT_SCHEMA_VERSION")
    if receipt.get("profile_sha256") != expected_profile_sha256:
        raise ContractError("DEPLOYMENT_RECEIPT_PROFILE_MISMATCH")
    if receipt.get("promotion_sha256") != promotion_sha:
        raise ContractError("DEPLOYMENT_RECEIPT_PROMOTION_MISMATCH")
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


class FixedAdmissionGate:
    """The single provider seam shared by the Web probe, CLI prepare and the allocator."""

    def __init__(
        self,
        provider: ResourceBudgetProvider,
        *,
        context: FixedProductionContext | MeasurementContext | None = None,
        current: RuntimeFingerprint | None = None,
        live: LiveResourceObservation | None = None,
        now_monotonic_s: float | None = None,
    ) -> None:
        if not isinstance(provider, ResourceBudgetProvider):
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if context is not None and not isinstance(
            context, (FixedProductionContext, MeasurementContext)
        ):
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        self.provider = provider
        self.context = context
        self.current = current
        self.live = live
        self.now_monotonic_s = now_monotonic_s

    @property
    def execution_identity_sha256(self) -> str | None:
        return None if self.current is None else self.current.sha256

    def admit(self, request: FixedAdmissionRequest) -> ResourceBudgetAdmission:
        """Answer one admission question; a missing probe is never a pass."""

        if self.current is None or self.live is None:
            return ResourceBudgetAdmission(
                admitted=False,
                reason_codes=("RESOURCE_PROBE_FAILED",),
                worker_count=request.worker_count,
                profile_sha256=self.provider.profile_sha256,
                qualification_sha256=None,
                execution_identity_sha256=request.execution_identity_sha256,
                observation_monotonic_s=0.0,
            )
        if request.request_kind == "MEASUREMENT":
            if not isinstance(self.context, MeasurementContext):
                raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
            if self.context.scope.worker_count != request.worker_count:
                raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
            return self.provider.admit_measurement(
                context=self.context, current=self.current, live=self.live,
                now_monotonic_s=self.now_monotonic_s)
        if not isinstance(self.context, FixedProductionContext):
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        if self.context.scope.worker_count != request.worker_count:
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        return self.provider.admit_production(
            context=self.context, current=self.current, live=self.live,
            now_monotonic_s=self.now_monotonic_s)
