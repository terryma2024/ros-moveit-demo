"""Lease, attempt and validation identities, inference records, the batch summary and the closed YAML loader."""

from __future__ import annotations

from dataclasses import dataclass, field
import math
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import yaml

from so101_demo.parallel_batch.contracts.common import (
    ContractError,
    ExecutionKind,
    PointStatus,
    RunMode,
    ValidationStatus,
    _require_enum,
    _require_finite,
    _require_id,
    _require_positive_int,
    _require_safe_relative_path,
    _require_sha256,
)


@dataclass(frozen=True, slots=True)
class LeaseIdentity:
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    point_id: str
    attempt_id: str
    lease_generation: int
    lease_issued_monotonic_s: float
    lease_deadline_monotonic_s: float

    def __post_init__(self) -> None:
        for name in ("batch_id", "worker_id", "point_id", "attempt_id"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        for name in ("coordinator_epoch", "worker_generation", "lease_generation"):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))
        issued = _require_finite("lease_issued_monotonic_s", self.lease_issued_monotonic_s)
        deadline = _require_finite("lease_deadline_monotonic_s", self.lease_deadline_monotonic_s)
        if deadline <= issued:
            raise ContractError("LEASE_DEADLINE_ORDER")
        object.__setattr__(self, "lease_issued_monotonic_s", issued)
        object.__setattr__(self, "lease_deadline_monotonic_s", deadline)


@dataclass(frozen=True, slots=True)
class AttemptIdentity:
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    point_id: str
    attempt_id: str
    lease_generation: int

    def __post_init__(self) -> None:
        for name in ("batch_id", "worker_id", "point_id", "attempt_id"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        for name in ("coordinator_epoch", "worker_generation", "lease_generation"):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))


@dataclass(frozen=True, slots=True)
class ValidationIdentity:
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    point_id: str
    validation_id: str
    lease_generation: int

    def __post_init__(self) -> None:
        for name in ("batch_id", "worker_id", "point_id", "validation_id"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        for name in ("coordinator_epoch", "worker_generation", "lease_generation"):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))


def _validate_execution_identity(
    *,
    execution_kind: ExecutionKind,
    attempt_id: str | None,
    validation_id: str | None,
) -> tuple[str | None, str | None]:
    _require_enum("execution_kind", execution_kind, ExecutionKind)
    if execution_kind is ExecutionKind.ATTEMPT:
        if validation_id is not None or attempt_id is None:
            raise ContractError("MIXED_EXECUTION_IDENTITY")
        return _require_id("attempt_id", attempt_id), None
    if attempt_id is not None or validation_id is None:
        raise ContractError("MIXED_EXECUTION_IDENTITY")
    return None, _require_id("validation_id", validation_id)


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    request_id: str
    model_id: str
    image_timestamp_s: float
    input_relative_path: str
    input_sha256: str
    deadline_s: float
    execution_kind: ExecutionKind | None = None
    batch_id: str | None = None
    coordinator_epoch: int | None = None
    worker_id: str | None = None
    worker_generation: int | None = None
    point_id: str | None = None
    lease_generation: int | None = None
    reset_epoch: str | None = None
    attempt_id: str | None = None
    validation_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "model_id"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        scheduling = (
            self.execution_kind,
            self.batch_id,
            self.coordinator_epoch,
            self.worker_id,
            self.worker_generation,
            self.point_id,
            self.lease_generation,
            self.reset_epoch,
            self.attempt_id,
            self.validation_id,
        )
        if any(value is not None for value in scheduling):
            for name in ("batch_id", "worker_id", "point_id", "reset_epoch"):
                object.__setattr__(
                    self, name, _require_id(name, getattr(self, name))
                )
            for name in (
                "coordinator_epoch",
                "worker_generation",
                "lease_generation",
            ):
                object.__setattr__(
                    self,
                    name,
                    _require_positive_int(name, getattr(self, name)),
                )
            attempt_id, validation_id = _validate_execution_identity(
                execution_kind=self.execution_kind,
                attempt_id=self.attempt_id,
                validation_id=self.validation_id,
            )
            object.__setattr__(self, "attempt_id", attempt_id)
            object.__setattr__(self, "validation_id", validation_id)
        object.__setattr__(
            self,
            "image_timestamp_s",
            _require_finite("image_timestamp_s", self.image_timestamp_s),
        )
        deadline_s = _require_finite("deadline_s", self.deadline_s)
        if deadline_s <= 0:
            raise ContractError("deadline_s")
        object.__setattr__(self, "deadline_s", deadline_s)
        object.__setattr__(
            self,
            "input_relative_path",
            _require_safe_relative_path("input_relative_path", self.input_relative_path),
        )
        object.__setattr__(
            self, "input_sha256", _require_sha256("input_sha256", self.input_sha256)
        )


@dataclass(frozen=True, slots=True)
class NormalizedInferenceResponseIdentity:
    request_id: str
    execution_kind: ExecutionKind
    batch_id: str
    coordinator_epoch: int
    worker_id: str
    worker_generation: int
    point_id: str
    lease_generation: int
    attempt_id: str | None = None
    validation_id: str | None = None

    def __post_init__(self) -> None:
        for name in ("request_id", "batch_id", "worker_id", "point_id"):
            object.__setattr__(self, name, _require_id(name, getattr(self, name)))
        for name in ("coordinator_epoch", "worker_generation", "lease_generation"):
            object.__setattr__(self, name, _require_positive_int(name, getattr(self, name)))
        attempt_id, validation_id = _validate_execution_identity(
            execution_kind=self.execution_kind,
            attempt_id=self.attempt_id,
            validation_id=self.validation_id,
        )
        object.__setattr__(self, "attempt_id", attempt_id)
        object.__setattr__(self, "validation_id", validation_id)

    @classmethod
    def from_request(cls, request: InferenceRequest) -> "NormalizedInferenceResponseIdentity":
        if not isinstance(request, InferenceRequest):
            raise ContractError("INFERENCE_REQUEST")
        return cls(
            request_id=request.request_id,
            execution_kind=request.execution_kind,
            batch_id=request.batch_id,
            coordinator_epoch=request.coordinator_epoch,
            worker_id=request.worker_id,
            worker_generation=request.worker_generation,
            point_id=request.point_id,
            lease_generation=request.lease_generation,
            attempt_id=request.attempt_id,
            validation_id=request.validation_id,
        )


_TEACHER_STARTED = frozenset({PointStatus.PASSED, PointStatus.FAILED, PointStatus.INDETERMINATE})


@dataclass(frozen=True, slots=True)
class BatchSummary:
    run_mode: RunMode
    point_statuses: Mapping[str, PointStatus]
    batch_terminal: bool = False
    validation_statuses: Mapping[str, ValidationStatus] = field(default_factory=dict)
    batch_cleanup_complete: bool = False
    terminal_reason: str | None = None
    #: per committed ACT point: its data verdict, kept apart from the Teacher status in `point_statuses`
    act_results: Mapping[str, Mapping[str, object]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_enum("run_mode", self.run_mode, RunMode)
        if not isinstance(self.batch_terminal, bool):
            raise ContractError("BOOLEAN: batch_terminal")
        if not isinstance(self.batch_cleanup_complete, bool):
            raise ContractError("BOOLEAN: batch_cleanup_complete")
        if self.terminal_reason is not None:
            object.__setattr__(
                self,
                "terminal_reason",
                _require_id("terminal_reason", self.terminal_reason),
            )
        if not isinstance(self.point_statuses, Mapping):
            raise ContractError("POINT_STATUSES")
        if not isinstance(self.validation_statuses, Mapping):
            raise ContractError("VALIDATION_STATUSES")
        points = dict(self.point_statuses)
        validations = dict(self.validation_statuses)
        if not points:
            raise ContractError("POINT_STATUSES")
        for point_id, status in points.items():
            _require_id("point_id", point_id)
            _require_enum("point_status", status, PointStatus)
        for point_id, status in validations.items():
            _require_id("validation_point_id", point_id)
            _require_enum("validation_status", status, ValidationStatus)
        if self.run_mode is RunMode.EXECUTE:
            if validations:
                raise ContractError("EXECUTE_VALIDATION_MIX")
        else:
            if not set(validations).issubset(points) or any(
                status is not PointStatus.UNRUN for status in points.values()
            ):
                raise ContractError("VALIDATION_PHYSICAL_UNRUN")
        if not isinstance(self.act_results, Mapping) or not set(self.act_results).issubset(points):
            raise ContractError("ACT_RESULTS")
        object.__setattr__(self, "point_statuses", MappingProxyType(points))
        object.__setattr__(self, "validation_statuses", MappingProxyType(validations))
        object.__setattr__(self, "act_results", MappingProxyType(dict(self.act_results)))

    @property
    def teacher_attempts_started(self) -> int:
        """Started, legal Teacher attempts: every point with a recorded Teacher outcome.

        PASSED, FAILED and INDETERMINATE all started a Teacher attempt, whatever happened to their data. INVALID
        (no valid attempt) and UNRUN are not attempts. This is the denominator of the Teacher success rate: it never
        shrinks to the data-QC subset.
        """
        return sum(status in _TEACHER_STARTED for status in self.point_statuses.values())

    @property
    def teacher_passed(self) -> int:
        return sum(status is PointStatus.PASSED for status in self.point_statuses.values())

    @property
    def teacher_success_rate(self) -> float | None:
        started = self.teacher_attempts_started
        return None if started == 0 else self.teacher_passed / started

    @property
    def act_data_qc_passed(self) -> int:
        """Committed ACT points whose independent data QC passed (a Teacher failure may still be among them)."""
        return sum(record.get("act_data_qc") == "PASS" for record in self.act_results.values())

    @property
    def act_data_pass_rate(self) -> float | None:
        """Data QC passes over the committed ACT results, reported apart from the Teacher success rate."""
        return None if not self.act_results else self.act_data_qc_passed / len(self.act_results)

    @property
    def committable_episodes(self) -> int:
        """Episodes exportable for training: Teacher PASS and data QC PASS."""
        return sum(record.get("export_eligible") is True for record in self.act_results.values())

    @property
    def coverage_complete(self) -> bool:
        return self.batch_terminal and self.run_mode is RunMode.EXECUTE and all(
            status in {PointStatus.PASSED, PointStatus.FAILED}
            for status in self.point_statuses.values()
        )

    @property
    def execution_complete(self) -> bool:
        return self.batch_terminal and self.run_mode is RunMode.EXECUTE

    @property
    def validation_complete(self) -> bool:
        return (
            self.batch_terminal
            and self.run_mode is not RunMode.EXECUTE
            and set(self.validation_statuses) == set(self.point_statuses)
        )

    @property
    def validation_passed(self) -> bool:
        return (
            self.terminal_reason == "POINTS_COMPLETE"
            and self.validation_complete
            and all(
                status is ValidationStatus.VALIDATION_PASSED
                for status in self.validation_statuses.values()
            )
        )

    @property
    def qualification_applicable(self) -> bool:
        return self.run_mode is RunMode.EXECUTE

    @property
    def qualification_passed(self) -> bool:
        return (
            self.terminal_reason == "POINTS_COMPLETE"
            and self.coverage_complete
            and self.batch_cleanup_complete
            and all(
                status is PointStatus.PASSED for status in self.point_statuses.values()
            )
        )


class _ClosedSafeLoader(yaml.SafeLoader):
    """SafeLoader that rejects duplicate mapping keys instead of last-one-wins."""


def _closed_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, (str, int, float, bool, type(None))):
            raise ContractError("MAPPING_KEY_TYPE")
        if key in mapping:
            raise ContractError("DUPLICATE_KEY")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_ClosedSafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _closed_mapping
)


def _reject_nonfinite(value: object, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ContractError(f"NONFINITE: {path}")
    if isinstance(value, Mapping):
        for key, item in value.items():
            _reject_nonfinite(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _reject_nonfinite(item, f"{path}[{index}]")


def _load_closed_yaml(path: Path) -> object:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as error:
        raise ContractError(f"CONFIG_READ_FAILED: {path}") from error
    try:
        document = yaml.load(text, Loader=_ClosedSafeLoader)
    except ContractError:
        raise
    except yaml.YAMLError as error:
        raise ContractError(f"CONFIG_YAML_INVALID: {path}") from error
    _reject_nonfinite(document)
    return document


def _closed_mapping_fields(name: str, document: object, expected: set[str],
                           optional: set[str] | None = None) -> dict:
    """Validate a closed mapping: no unknown keys, and no missing key outside ``optional``."""

    if not isinstance(document, Mapping):
        raise ContractError(f"{name}_MAPPING")
    unknown = set(document) - expected
    missing = (expected - set(optional or ())) - set(document)
    if unknown:
        raise ContractError(f"UNKNOWN_{name}_FIELD: {sorted(unknown)!r}")
    if missing:
        raise ContractError(f"MISSING_{name}_FIELD: {sorted(missing)!r}")
    return dict(document)
