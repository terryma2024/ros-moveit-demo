"""Candidate resource measurement: authorization, sampling, clock qualification, sealing.

The module produces raw observations, a clock/lag decision and a sealed B
document. It never reads or writes an approved profile, promotion record or
deployment receipt, and it cannot grant production admission.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from .contracts import ContractError
from .measurement_control import ProcessIdentity
from .resource_budget import (
    DIMENSIONS,
    ApprovedBudgetProfile,
    ExactNQualification,
    LiveResourceObservation,
    QualificationDecision,
    read_private_document,
)
from .resource_identity import canonical_sha256

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")
_ACTIVE_PHASES = ("AVAILABLE", "INITIALIZING", "EXECUTING", "FINALIZING", "STEADY")
_INTENTS = ("CALIBRATION_ONLY", "QUALIFICATION")
_BATCH_DEADLINE_S = 5400.0


def _require_identifier(name: str, value: object) -> str:
    if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
        raise ContractError(f"IDENTIFIER: {name}")
    return value


def _require_sha256(name: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ContractError(f"SHA256: {name}")
    return value


def _require_finite(name: str, value: object, *, minimum: float = 0.0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"FINITE: {name}")
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ContractError(f"FINITE: {name}")
    return result


@dataclass(frozen=True, slots=True)
class ClockEpoch:
    worker_id: str
    generation: int
    session_id: str
    reset_epoch: str
    publisher: ProcessIdentity
    ros_domain_id: int

    def __post_init__(self) -> None:
        for name in ("worker_id", "session_id", "reset_epoch"):
            value = getattr(self, name)
            if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
                raise ContractError(f"IDENTIFIER: {name}")
        if type(self.generation) is not int or self.generation < 1:
            raise ContractError("GENERATION")
        if not isinstance(self.publisher, ProcessIdentity):
            raise ContractError("CLOCK_PUBLISHER")
        if type(self.ros_domain_id) is not int or not 0 <= self.ros_domain_id <= 232:
            raise ContractError("ROS_DOMAIN_ID")

    @property
    def sha256(self) -> str:
        return canonical_sha256(
            {
                "worker_id": self.worker_id,
                "generation": self.generation,
                "session_id": self.session_id,
                "reset_epoch": self.reset_epoch,
                "publisher": {
                    "pid": self.publisher.pid,
                    "starttime_ticks": self.publisher.starttime_ticks,
                    "uid": self.publisher.uid,
                    "pgid": self.publisher.pgid,
                },
                "ros_domain_id": self.ros_domain_id,
            }
        )


@dataclass(frozen=True, slots=True)
class ClockWindow:
    epoch: ClockEpoch
    wall_start_s: float
    wall_end_s: float
    sim_start_s: float
    sim_end_s: float
    epsilon_t_s: float
    epsilon_s_s: float
    expected_pace: float
    eligible: bool
    phase: str
    phase_started_s: float
    readiness_completed_s: float
    maximum_sample_gap_s: float
    boundary_sample_age_s: float
    clock_age_s: float

    def __post_init__(self) -> None:
        if not isinstance(self.epoch, ClockEpoch):
            raise ContractError("CLOCK_EPOCH")
        for name in ("wall_start_s", "wall_end_s", "sim_start_s", "sim_end_s", "epsilon_t_s",
                     "epsilon_s_s", "phase_started_s", "readiness_completed_s",
                     "maximum_sample_gap_s", "boundary_sample_age_s", "clock_age_s"):
            object.__setattr__(self, name, _require_finite(name, getattr(self, name)))
        object.__setattr__(
            self, "expected_pace", _require_finite("expected_pace", self.expected_pace,
                                                    minimum=0.000001))
        if self.wall_end_s <= self.wall_start_s:
            raise ContractError("WALL_INTERVAL")
        if not isinstance(self.eligible, bool):
            raise ContractError("ELIGIBLE")
        if self.phase not in (*_ACTIVE_PHASES, "STARTUP", "TEARDOWN", "IDLE", "RESET"):
            raise ContractError("PHASE")

    @property
    def epoch_sha256(self) -> str:
        return self.epoch.sha256


def rtf_interval(window: ClockWindow) -> tuple[float, float]:
    """Conservative RTF interval from absolute wall/sim boundaries only."""

    if not isinstance(window, ClockWindow):
        raise ContractError("CLOCK_WINDOW")
    sim_delta = window.sim_end_s - window.sim_start_s
    wall_delta = window.wall_end_s - window.wall_start_s
    denominator_low = wall_delta - window.epsilon_t_s
    denominator_high = wall_delta + window.epsilon_t_s
    high = math.inf if denominator_low <= 0 else (sim_delta + window.epsilon_s_s) / denominator_low
    low = math.inf if denominator_high <= 0 else (sim_delta - window.epsilon_s_s) / denominator_high
    return (max(low, 0.0), high)


@dataclass(frozen=True, slots=True)
class ClockQualification:
    """Per-epoch deficit counting over complete, non-overlapping active windows."""

    lag_error_s: float
    maximum_gap_s: float
    maximum_boundary_age_s: float
    maximum_clock_age_s: float = 5.0
    _state: dict = field(default_factory=dict, compare=False, repr=False)

    def __post_init__(self) -> None:
        for name in ("lag_error_s", "maximum_gap_s", "maximum_boundary_age_s",
                     "maximum_clock_age_s"):
            object.__setattr__(self, name, _require_finite(name, getattr(self, name)))

    def observe(self, window: ClockWindow, *, cumulative_lag_s: float) -> QualificationDecision:
        if not isinstance(window, ClockWindow):
            raise ContractError("CLOCK_WINDOW")
        lag = _require_finite("cumulative_lag_s", cumulative_lag_s)
        if not window.eligible:
            return QualificationDecision(False, ("WINDOW_INELIGIBLE",))
        if window.phase not in _ACTIVE_PHASES:
            return QualificationDecision(False, ("PHASE_NOT_ACTIVE",))
        if (
            window.maximum_sample_gap_s > self.maximum_gap_s
            or window.boundary_sample_age_s > self.maximum_boundary_age_s
            or window.clock_age_s > self.maximum_clock_age_s
        ):
            return QualificationDecision(False, ("CLOCK_STALE",))
        previous = self._state.get("previous")
        same_epoch = previous is not None and previous.epoch.sha256 == window.epoch.sha256
        if previous is not None and not same_epoch:
            self._state["streak"] = 0
            self._state["lag_anchor"] = None
        if same_epoch and window.wall_start_s < previous.wall_end_s:
            # Overlapping rolling samples never count the same disturbance twice.
            return QualificationDecision(True, ())
        _, upper = rtf_interval(window)
        deficit = upper < window.expected_pace
        streak = self._state.get("streak", 0) + 1 if deficit else 0
        self._state["streak"] = streak
        self._state["previous"] = window
        anchor = self._state.get("lag_anchor")
        if anchor is None or not same_epoch:
            self._state["lag_anchor"] = (window.wall_end_s, lag)
        else:
            _, previous_lag = anchor
            growth = lag - previous_lag
            self._state["lag_anchor"] = (window.wall_end_s, lag)
            if deficit and growth > self.lag_error_s:
                return QualificationDecision(False, ("SUSTAINED_LAG",))
        if streak >= 2:
            return QualificationDecision(False, ("RTF_DEFICIT",))
        return QualificationDecision(True, ())


@dataclass(frozen=True, slots=True)
class ResourceSample:
    sequence: int
    monotonic_s: float
    observation: LiveResourceObservation
    process_inventory: tuple[ProcessIdentity, ...]
    diagnostics: Mapping[str, object]

    def __post_init__(self) -> None:
        if type(self.sequence) is not int or self.sequence < 1:
            raise ContractError("SAMPLE_SEQUENCE")
        object.__setattr__(self, "monotonic_s", _require_finite("monotonic_s", self.monotonic_s))
        if not isinstance(self.observation, LiveResourceObservation):
            raise ContractError("OBSERVATION")
        inventory = tuple(self.process_inventory)
        for identity in inventory:
            if not isinstance(identity, ProcessIdentity):
                raise ContractError("PROCESS_IDENTITY")
        object.__setattr__(self, "process_inventory", inventory)
        if not isinstance(self.diagnostics, Mapping):
            raise ContractError("DIAGNOSTICS")
        object.__setattr__(self, "diagnostics", MappingProxyType(dict(self.diagnostics)))


def _read_meminfo() -> dict[str, int]:
    values = {}
    for line in Path("/proc/meminfo").read_text().splitlines():
        key, _, rest = line.partition(":")
        if rest.strip().endswith("kB"):
            values[key] = int(rest.split()[0]) * 1024
    if "MemTotal" not in values or "MemAvailable" not in values:
        raise ContractError("RESOURCE_PROBE_FAILED")
    return values


def _read_swap_and_psi() -> tuple[int, float]:
    swap = 0
    try:
        for line in Path("/proc/vmstat").read_text().splitlines():
            name, _, value = line.partition(" ")
            if name in ("pswpin", "pswpout"):
                swap += int(value)
    except OSError as error:
        raise ContractError("RESOURCE_PROBE_FAILED") from error
    psi_full = 0.0
    try:
        for line in Path("/proc/pressure/memory").read_text().splitlines():
            if line.startswith("full "):
                for token in line.split()[1:]:
                    if token.startswith("total="):
                        psi_full = float(token.split("=", 1)[1]) / 1_000_000.0
    except OSError:
        psi_full = 0.0
    return swap, psi_full


def sample_resources(
    *,
    owned_inventory: Sequence[ProcessIdentity],
    cgroup,
    device,
    sequence: int,
    state: dict | None = None,
) -> ResourceSample:
    """One resource observation; capability gaps fail closed instead of guessing."""

    if cgroup is None or device is None:
        raise ContractError("MEASUREMENT_CAPABILITY_MISSING")
    if not hasattr(cgroup, "cpu_usage_us") or not hasattr(cgroup, "memory_current"):
        raise ContractError("MEASUREMENT_CAPABILITY_MISSING")
    if not hasattr(device, "total_bytes") or not hasattr(device, "used_bytes"):
        raise ContractError("MEASUREMENT_CAPABILITY_MISSING")
    memory = _read_meminfo()
    swap_total, psi_total = _read_swap_and_psi()
    monotonic_s = time.monotonic()
    cpu_usage_us = int(cgroup.cpu_usage_us())
    cpu_capacity = float(getattr(cgroup, "cpu_capacity_core_equivalent", os.cpu_count() or 1))
    if state is None:
        cpu_delta = 0.0
        swap_delta = 0
        psi_delta = 0.0
    else:
        swap_delta = max(0, swap_total - state.get("swap_total", swap_total))
        psi_delta = max(0.0, psi_total - state.get("psi_total", psi_total))
        # A cgroup may spend a whole cpu.max quota inside a single period, so a rate
        # measured over less than a period can read up to twice the enforced cap: the
        # 22.43 cores observed against an 18.6-core quota were exactly that artifact.
        # The rate is measured over at least cpu_window_s and held between boundaries.
        window_s = float(state.get("cpu_window_s", 0.0) or 0.0)
        start_s = state.get("window_start_s")
        start_usage = state.get("window_start_usage_us")
        cpu_delta = float(state.get("cpu_rate", 0.0))
        if start_s is None or start_usage is None:
            state["window_start_s"] = monotonic_s
            state["window_start_usage_us"] = cpu_usage_us
            cpu_delta = 0.0
        else:
            span = monotonic_s - float(start_s)
            # A monotonic span that should equal the window can miss it by a few
            # float ulps, which would only delay the rate by one sample.
            complete = (span >= window_s - 1e-9 if window_s > 0.0 else span > 0.0)
            if complete:
                cpu_delta = max(0.0, (cpu_usage_us - int(start_usage)) / 1e6 / span)
                state["window_start_s"] = monotonic_s
                state["window_start_usage_us"] = cpu_usage_us
                state["cpu_rate"] = cpu_delta
    observation = LiveResourceObservation(
        monotonic_s=monotonic_s,
        capacity={
            "ram_bytes": float(memory["MemTotal"]),
            "gpu_bytes": float(device.total_bytes),
            "cpu_core_equivalent": cpu_capacity,
        },
        observed={
            "ram_bytes": float(cgroup.memory_current()),
            "gpu_bytes": float(device.used_bytes),
            "cpu_core_equivalent": cpu_delta,
        },
        background={
            "ram_bytes": float(memory["MemTotal"] - memory["MemAvailable"]),
            "gpu_bytes": float(device.used_bytes),
            "cpu_core_equivalent": 0.0,
        },
        tool_overhead={key: 0.0 for key in DIMENSIONS},
        remaining={key: 0.0 for key in DIMENSIONS},
        error={key: 0.0 for key in DIMENSIONS},
        attribution_complete=bool(getattr(cgroup, "attribution_complete", True)),
        swap_delta=int(swap_delta),
        psi_full_delta=float(psi_delta),
        throttled=bool(getattr(cgroup, "throttled", False)),
    )
    diagnostics = {
        "mem_available_bytes": memory["MemAvailable"],
        "cpu_usage_us": cpu_usage_us,
        "swap_total": swap_total,
    }
    sample = ResourceSample(
        sequence=sequence, monotonic_s=monotonic_s, observation=observation,
        process_inventory=tuple(owned_inventory), diagnostics=diagnostics)
    if state is not None:
        state.update(
            monotonic_s=monotonic_s, cpu_usage_us=cpu_usage_us, swap_total=swap_total,
            psi_total=psi_total)
    return sample


_AUTHORIZATION_FIELDS = (
    "schema_version", "operator_uid", "dispatch_id", "task_id", "source_commit",
    "execution_identity_sha256", "worker_count", "catalog_sha256", "seed", "lifecycle",
    "maximum_batches", "batch_deadline_s", "expires_at_ns", "batch_root", "owned_scope_sha256",
    "safety_policy_sha256", "intent", "calibration_sha256", "runtime_bindings",
)

_RUNTIME_BINDING_FIELDS = (
    "points_path", "points_sha256", "yolo_weights_path", "yolo_weights_sha256",
    "grounded_root", "grounded_manifest_sha256", "broker_image_id",
    "provenance_binding_path", "provenance_binding_sha256",
)


@dataclass(frozen=True, slots=True)
class MeasurementRuntimeBindings:
    """Closed runtime bindings a sealed candidate authorization must carry."""

    points_path: str
    points_sha256: str
    yolo_weights_path: str
    yolo_weights_sha256: str
    grounded_root: str
    grounded_manifest_sha256: str
    broker_image_id: str
    provenance_binding_path: str
    provenance_binding_sha256: str

    def __post_init__(self) -> None:
        for name in ("points_path", "yolo_weights_path", "grounded_root",
                     "provenance_binding_path"):
            value = getattr(self, name)
            if not isinstance(value, str) or not Path(value).is_absolute():
                raise ContractError(f"BINDING_PATH: {name}")
        for name in ("points_sha256", "yolo_weights_sha256", "grounded_manifest_sha256",
                     "provenance_binding_sha256"):
            _require_sha256(name, getattr(self, name))
        broker = self.broker_image_id
        if not isinstance(broker, str) or not broker.startswith("sha256:") or len(broker) != 71:
            raise ContractError("BROKER_IMAGE_ID")

    @classmethod
    def from_document(cls, document: object) -> "MeasurementRuntimeBindings":
        if not isinstance(document, Mapping):
            raise ContractError("RUNTIME_BINDINGS_MAPPING")
        unknown = set(document) - set(_RUNTIME_BINDING_FIELDS)
        missing = set(_RUNTIME_BINDING_FIELDS) - set(document)
        if unknown:
            raise ContractError(f"RUNTIME_BINDINGS_UNKNOWN_FIELD: {sorted(unknown)!r}")
        if missing:
            raise ContractError(f"RUNTIME_BINDINGS_MISSING_FIELD: {sorted(missing)!r}")
        return cls(**{name: document[name] for name in _RUNTIME_BINDING_FIELDS})

    def as_document(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in _RUNTIME_BINDING_FIELDS}


@dataclass(frozen=True, slots=True)
class MeasurementAuthorization:
    schema_version: int
    operator_uid: int
    dispatch_id: str
    task_id: str
    source_commit: str
    execution_identity_sha256: str
    worker_count: int
    catalog_sha256: str
    seed: int
    lifecycle: str
    maximum_batches: int
    batch_deadline_s: float
    expires_at_ns: int
    batch_root: Path
    owned_scope_sha256: str
    safety_policy_sha256: str
    intent: str
    calibration_sha256: str | None
    runtime_bindings: MeasurementRuntimeBindings
    raw_sha256: str

    @classmethod
    def from_document(cls, document: object, *, raw_sha256: str) -> "MeasurementAuthorization":
        if not isinstance(document, Mapping):
            raise ContractError("AUTHORIZATION_MAPPING")
        unknown = set(document) - set(_AUTHORIZATION_FIELDS)
        missing = set(_AUTHORIZATION_FIELDS) - set(document)
        if unknown:
            raise ContractError(f"AUTHORIZATION_UNKNOWN_FIELD: {sorted(unknown)!r}")
        if missing:
            raise ContractError(f"AUTHORIZATION_MISSING_FIELD: {sorted(missing)!r}")
        if type(document["schema_version"]) is not int or document["schema_version"] != 2:
            raise ContractError("AUTHORIZATION_SCHEMA_VERSION")
        if type(document["operator_uid"]) is not int or document["operator_uid"] != os.getuid():
            raise ContractError("OPERATOR_UID")
        for name in ("dispatch_id", "task_id"):
            value = document[name]
            if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
                raise ContractError(f"IDENTIFIER: {name}")
        if not isinstance(document["source_commit"], str) or _COMMIT.fullmatch(
            document["source_commit"]
        ) is None:
            raise ContractError("SOURCE_COMMIT")
        for name in ("execution_identity_sha256", "catalog_sha256", "owned_scope_sha256",
                     "safety_policy_sha256"):
            _require_sha256(name, document[name])
        worker_count = document["worker_count"]
        if type(worker_count) is not int or not 1 <= worker_count <= 8:
            raise ContractError("WORKER_COUNT")
        if type(document["seed"]) is not int or document["seed"] < 0:
            raise ContractError("SEED")
        if document["lifecycle"] != "FULL_RESTART":
            raise ContractError("LIFECYCLE")
        if type(document["maximum_batches"]) is not int or document["maximum_batches"] < 1:
            raise ContractError("MAXIMUM_BATCHES")
        if _require_finite("batch_deadline_s", document["batch_deadline_s"]) != _BATCH_DEADLINE_S:
            raise ContractError("BATCH_DEADLINE")
        if type(document["expires_at_ns"]) is not int or document["expires_at_ns"] <= 0:
            raise ContractError("EXPIRY")
        batch_root = Path(document["batch_root"])
        if not batch_root.is_absolute():
            raise ContractError("BATCH_ROOT")
        intent = document["intent"]
        if intent not in _INTENTS:
            raise ContractError("INTENT")
        calibration = document["calibration_sha256"]
        if intent == "QUALIFICATION":
            if calibration is None:
                raise ContractError("CALIBRATION_EVIDENCE_REQUIRED")
            _require_sha256("calibration_sha256", calibration)
        elif calibration is not None:
            _require_sha256("calibration_sha256", calibration)
            raise ContractError("CALIBRATION_HASH_FORBIDDEN")
        return cls(
            schema_version=2,
            runtime_bindings=MeasurementRuntimeBindings.from_document(
                document["runtime_bindings"]),
            operator_uid=document["operator_uid"],
            dispatch_id=document["dispatch_id"],
            task_id=document["task_id"],
            source_commit=document["source_commit"],
            execution_identity_sha256=document["execution_identity_sha256"],
            worker_count=worker_count,
            catalog_sha256=document["catalog_sha256"],
            seed=document["seed"],
            lifecycle=document["lifecycle"],
            maximum_batches=document["maximum_batches"],
            batch_deadline_s=float(document["batch_deadline_s"]),
            expires_at_ns=document["expires_at_ns"],
            batch_root=batch_root,
            owned_scope_sha256=document["owned_scope_sha256"],
            safety_policy_sha256=document["safety_policy_sha256"],
            intent=intent,
            calibration_sha256=calibration,
            raw_sha256=_require_sha256("raw_sha256", raw_sha256),
        )

    @classmethod
    def load(cls, path: Path, *, expected_sha256: str) -> "MeasurementAuthorization":
        document, digest = read_private_document(path, expected_sha256=expected_sha256)
        return cls.from_document(document, raw_sha256=digest)

    def is_expired(self, *, now_ns: int) -> bool:
        return int(now_ns) > self.expires_at_ns

    def as_document(self) -> dict[str, object]:
        """The exact sealed document, for byte comparison during re-verification."""

        return {
            "schema_version": self.schema_version,
            "operator_uid": self.operator_uid,
            "dispatch_id": self.dispatch_id,
            "task_id": self.task_id,
            "source_commit": self.source_commit,
            "execution_identity_sha256": self.execution_identity_sha256,
            "worker_count": self.worker_count,
            "catalog_sha256": self.catalog_sha256,
            "seed": self.seed,
            "lifecycle": self.lifecycle,
            "maximum_batches": self.maximum_batches,
            "batch_deadline_s": self.batch_deadline_s,
            "expires_at_ns": self.expires_at_ns,
            "batch_root": str(self.batch_root),
            "owned_scope_sha256": self.owned_scope_sha256,
            "safety_policy_sha256": self.safety_policy_sha256,
            "intent": self.intent,
            "calibration_sha256": self.calibration_sha256,
            "runtime_bindings": self.runtime_bindings.as_document(),
        }


def _write_private(path: Path, data: bytes) -> str:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        os.write(descriptor, data)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
    return hashlib.sha256(data).hexdigest()


def seal_measurement(
    *,
    authorization: MeasurementAuthorization,
    execution_identity_sha256: str,
    raw_files: Sequence[Path],
    coverage_events: Path,
    result: Mapping[str, object],
    batch_root: Path | None = None,
) -> Path:
    """Seal one raw measurement batch (B) inside the authorized per-batch root."""

    if not isinstance(authorization, MeasurementAuthorization):
        raise ContractError("AUTHORIZATION")
    _require_sha256("execution_identity_sha256", execution_identity_sha256)
    if execution_identity_sha256 != authorization.execution_identity_sha256:
        raise ContractError("RUNTIME_FINGERPRINT_MISMATCH")
    sealed_at_root = Path(authorization.batch_root) if batch_root is None else Path(batch_root)
    if not sealed_at_root.resolve().is_relative_to(Path(authorization.batch_root).resolve()):
        raise ContractError("BATCH_ROOT_OUTSIDE_AUTHORIZATION")
    files = []
    for path in raw_files:
        data = Path(path).read_bytes()
        files.append({"name": Path(path).name, "sha256": hashlib.sha256(data).hexdigest(),
                      "size": len(data)})
    coverage_bytes = Path(coverage_events).read_bytes()
    document = {
        "schema_version": 2,
        "sealed_at_ns": time.time_ns(),
        "authorization_sha256": authorization.raw_sha256,
        "dispatch_id": authorization.dispatch_id,
        "task_id": authorization.task_id,
        "source_commit": authorization.source_commit,
        "execution_identity_sha256": execution_identity_sha256,
        "worker_count": authorization.worker_count,
        "catalog_sha256": authorization.catalog_sha256,
        "seed": authorization.seed,
        "intent": authorization.intent,
        "safety_policy_sha256": authorization.safety_policy_sha256,
        "owned_scope_sha256": authorization.owned_scope_sha256,
        "calibration_sha256": authorization.calibration_sha256,
        "coverage_events_sha256": hashlib.sha256(coverage_bytes).hexdigest(),
        "raw_files": files,
        "result": dict(result),
        "batch_id": sealed_at_root.name,
        "batch_root": str(sealed_at_root),
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sealed_root = sealed_at_root / "sealed"
    sealed_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = sealed_root / f"sealed-{authorization.dispatch_id}-{len(files)}-{document['sealed_at_ns']}.json"
    _write_private(target, encoded)
    return target


# --- Exact-N qualification aggregation (Task 13, offline) ---------------------------


class CoverageCell(StrEnum):
    COLD_START = "COLD_START"
    STEADY_YOLO = "STEADY_YOLO"
    STEADY_GROUNDED_SAM = "STEADY_GROUNDED_SAM"
    STEADY_MIXED = "STEADY_MIXED"
    MOTION_RELEASE = "MOTION_RELEASE"
    BROKER_RELOAD_WITH_N_RESIDENT = "BROKER_RELOAD_WITH_N_RESIDENT"
    WORKER_RECOVERY_WITH_N_RESIDENT = "WORKER_RECOVERY_WITH_N_RESIDENT"
    FINALIZATION_CLEANUP = "FINALIZATION_CLEANUP"


_REQUIRED_NORMAL_RUNS = 5
_REQUIRED_POINT_COUNT = 20
_REQUIRED_CELL_RUNS = 2
_VALIDITY_STATES = ("VALID", "INVALID", "UNKNOWN", "INDETERMINATE")
_OUTCOMES = ("PASSED", "FAILED", "INFRA_FAILURE")


@dataclass(frozen=True, slots=True)
class RunEvidence:
    """One sealed candidate run; never a substitute for independent physics evidence."""

    batch_id: str
    worker_count: int
    execution_identity_sha256: str
    validity: str
    outcome: str
    full_restart: bool
    point_count: int
    actual_worker_identities: tuple[ProcessIdentity, ...]
    concurrent_window: tuple[float, float] | None
    coverage: Mapping[str, tuple[str, ...]]
    sealed_manifest_sha256: str
    independent_physics_verified: bool
    resource_contract_verified: bool
    cleanup_verified: bool
    point_evidence: tuple[Mapping[str, object], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.batch_id, str) or not self.batch_id:
            raise ContractError("BATCH_ID")
        if type(self.worker_count) is not int or not 1 <= self.worker_count <= 8:
            raise ContractError("WORKER_COUNT")
        _require_sha256("execution_identity_sha256", self.execution_identity_sha256)
        if self.validity not in _VALIDITY_STATES:
            raise ContractError("VALIDITY")
        if self.outcome not in _OUTCOMES:
            raise ContractError("OUTCOME")
        for name in ("full_restart", "independent_physics_verified",
                     "resource_contract_verified", "cleanup_verified"):
            if not isinstance(getattr(self, name), bool):
                raise ContractError(f"BOOLEAN: {name}")
        if type(self.point_count) is not int or self.point_count < 0:
            raise ContractError("POINT_COUNT")
        identities = tuple(self.actual_worker_identities)
        for identity in identities:
            if not isinstance(identity, ProcessIdentity):
                raise ContractError("PROCESS_IDENTITY")
        object.__setattr__(self, "actual_worker_identities", identities)
        window = self.concurrent_window
        if window is not None:
            if (
                not isinstance(window, (list, tuple)) or len(window) != 2
                or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in window)
                or float(window[1]) <= float(window[0])
            ):
                raise ContractError("CONCURRENT_WINDOW")
            object.__setattr__(self, "concurrent_window", (float(window[0]), float(window[1])))
        cells: dict[str, tuple[str, ...]] = {}
        if not isinstance(self.coverage, Mapping):
            raise ContractError("COVERAGE")
        for cell, outcomes in self.coverage.items():
            if cell not in tuple(item.value for item in CoverageCell):
                raise ContractError(f"COVERAGE_CELL: {cell}")
            if not isinstance(outcomes, (list, tuple)) or not outcomes:
                raise ContractError(f"COVERAGE_OUTCOMES: {cell}")
            cells[cell] = tuple(str(outcome) for outcome in outcomes)
        object.__setattr__(self, "coverage", MappingProxyType(cells))
        _require_sha256("sealed_manifest_sha256", self.sealed_manifest_sha256)
        evidence = tuple(dict(item) for item in self.point_evidence)
        object.__setattr__(self, "point_evidence", evidence)

    @property
    def is_valid(self) -> bool:
        return self.validity == "VALID"

    @property
    def establishes_exact_n(self) -> bool:
        return (
            self.is_valid
            and len(self.actual_worker_identities) == self.worker_count
            and self.concurrent_window is not None
        )

    @property
    def complete_point_evidence(self) -> bool:
        return (
            self.independent_physics_verified
            and self.resource_contract_verified
            and self.cleanup_verified
        )


class QualificationAccumulator:
    """Counts normal, coverage and fault evidence for one exact N and identity."""

    def __init__(
        self, worker_count: int, execution_identity_sha256: str, coverage_policy_sha256: str
    ) -> None:
        if type(worker_count) is not int or not 1 <= worker_count <= 8:
            raise ContractError("WORKER_COUNT")
        self.worker_count = worker_count
        self.execution_identity_sha256 = _require_sha256(
            "execution_identity_sha256", execution_identity_sha256)
        self.coverage_policy_sha256 = _require_sha256(
            "coverage_policy_sha256", coverage_policy_sha256)
        self._normal: list[RunEvidence] = []
        self._fault: list[RunEvidence] = []
        self._rejected: list[RunEvidence] = []
        self._coverage: dict[str, list[tuple[RunEvidence, bool]]] = {}

    # -- evidence intake ------------------------------------------------------
    def _require_own_identity(self, run: RunEvidence, reason: str) -> bool:
        """Different worker count is retained as rejected evidence, never consumed."""

        if run.worker_count != self.worker_count:
            self._rejected.append(run)
            return False
        if run.execution_identity_sha256 != self.execution_identity_sha256:
            self._rejected.append(run)
            return False
        return True

    def add_normal(self, run: RunEvidence) -> None:
        """A normal run counts only when it is VALID, full-restart and exact-N."""

        if not isinstance(run, RunEvidence):
            raise ContractError("RUN_EVIDENCE")
        if not self._require_own_identity(run, "normal"):
            return
        if run.is_valid and not self._counts_as_normal(run):
            # A structurally incomplete run is retained as untrusted evidence.
            self._fault.append(run)
            return
        self._normal.append(run)
        for cell in run.coverage:
            self._coverage.setdefault(cell, []).append((run, False))

    @staticmethod
    def _counts_as_normal(run: RunEvidence) -> bool:
        return (
            run.full_restart
            and run.point_count >= _REQUIRED_POINT_COUNT
            and run.actual_worker_identities
            and len(run.actual_worker_identities) == run.worker_count
            and run.concurrent_window is not None
        )

    def add_coverage(self, run: RunEvidence, *, fast_channel: bool) -> None:
        if not isinstance(run, RunEvidence):
            raise ContractError("RUN_EVIDENCE")
        if not isinstance(fast_channel, bool):
            raise ContractError("FAST_CHANNEL")
        if not self._require_own_identity(run, "coverage"):
            return
        if not run.is_valid:
            return
        for cell in run.coverage:
            self._coverage.setdefault(cell, []).append((run, fast_channel))

    def add_fault(self, run: RunEvidence) -> None:
        """Fault pressure informs the envelope; it never enters a success sequence."""

        if not isinstance(run, RunEvidence):
            raise ContractError("RUN_EVIDENCE")
        if not self._require_own_identity(run, "fault"):
            return
        self._fault.append(run)

    # -- views ----------------------------------------------------------------
    @property
    def normal_run_count(self) -> int:
        return self._valid_normal_streak()

    @property
    def product_success_count(self) -> int:
        return self._valid_normal_streak(require_passed=True)

    @property
    def fault_run_count(self) -> int:
        return len(self._fault)

    def coverage_counts(self) -> dict[str, int]:
        return {
            cell: len(
                [run for run, _ in self._coverage.get(cell, [])
                 if run.establishes_exact_n and run.independent_physics_verified]
            )
            for cell in (item.value for item in CoverageCell)
        }

    def _valid_normal_streak(self, *, require_passed: bool = False) -> int:
        """Consecutive VALID complete runs; an infra failure or invalid run stops it."""

        streak = 0
        for run in self._normal:
            if (
                run.is_valid
                and run.complete_point_evidence
                and self._counts_as_normal(run)
                and run.outcome != "INFRA_FAILURE"
                and (not require_passed or run.outcome == "PASSED")
            ):
                streak += 1
                continue
            streak = 0
        return streak

    @property
    def sequence_terminated(self) -> bool:
        """An invalid or infrastructure-failed run ends this qualification sequence."""

        return any(
            run.outcome == "INFRA_FAILURE" or not run.is_valid for run in self._normal
        )

    def decision(self) -> QualificationDecision:
        reasons: list[str] = []
        if self.sequence_terminated:
            reasons.append("SEQUENCE_TERMINATED")
        if self._valid_normal_streak() < _REQUIRED_NORMAL_RUNS:
            reasons.append("NORMAL_RUNS_INSUFFICIENT")
        counts = self.coverage_counts()
        missing = [
            cell for cell in (item.value for item in CoverageCell)
            if counts.get(cell, 0) < _REQUIRED_CELL_RUNS
        ]
        if missing:
            reasons.append("COVERAGE_INCOMPLETE")
        if not self._normal or self._rejected:
            reasons.append("EXACT_N_UNQUALIFIED")
        return QualificationDecision(not reasons, tuple(reasons))

    def seal_index(self) -> "ExactNQualification":
        """Seal Q: it references sealed B manifests and can never reference P/M/D."""

        decision = self.decision()
        manifests = []
        for run in [*self._normal, *(run for run, _ in
                                 (item for group in self._coverage.values() for item in group)),
                    *self._fault]:
            if run.sealed_manifest_sha256 not in manifests:
                manifests.append(run.sealed_manifest_sha256)
        record = ExactNQualification(
            schema_version=2,
            execution_identity_sha256=self.execution_identity_sha256,
            worker_count=self.worker_count,
            coverage_policy_sha256=self.coverage_policy_sha256,
            sealed_manifest_sha256s=tuple(manifests or ['0' * 64]),
            normal_valid_runs=self._valid_normal_streak(),
            normal_required_runs=_REQUIRED_NORMAL_RUNS,
            coverage_complete=decision.qualified,
            cleanup_verified=all(
                run.cleanup_verified for run in self._normal if run.is_valid
            ) if self._normal else False,
            independent_physics_verified=all(
                run.independent_physics_verified for run in self._normal if run.is_valid
            ) if self._normal else False,
            resource_contract_verified=all(
                run.resource_contract_verified for run in self._normal if run.is_valid
            ) if self._normal else False,
            raw_sha256=canonical_sha256(
                {
                    "worker_count": self.worker_count,
                    "execution_identity_sha256": self.execution_identity_sha256,
                    "manifest_sha256s": manifests,
                    "normal_runs": self._valid_normal_streak(),
                    "coverage": {cell: counts for cell, counts in self.coverage_counts().items()},
                }
            ),
        )
        return record


def build_candidate_profile(
    *,
    execution_identity_sha256: str,
    coverage_policy_sha256: str,
    qualifications: Sequence[ExactNQualification],
    covered_demands: Mapping[int, Mapping[str, Mapping[str, float]]],
    uncertainty: Mapping[int, Mapping[str, Mapping[str, float]]],
    baseline: Mapping[int, Mapping[str, float]],
    audits: Mapping[str, object],
) -> ApprovedBudgetProfile:
    """Build a CANDIDATE profile; only an operator promotion may approve it."""

    from .resource_budget import (
        ExactNProfileEntry,
        StageEnvelope,
    )

    entries: dict[int, ExactNProfileEntry] = {}
    manifests = tuple(str(item) for item in audits.get("raw_manifest_sha256s", ()))
    for worker_count, stages in covered_demands.items():
        stage_documents = {}
        for stage, demand in stages.items():
            zeros = {key: 0.0 for key in demand}
            stage_documents[stage] = StageEnvelope.from_document(
                stage,
                {
                    "demand": dict(demand),
                    "uncertainty": dict(uncertainty.get(worker_count, {}).get(stage, zeros)),
                    "background": dict(baseline.get(worker_count, zeros)),
                    "tool_overhead": dict(zeros),
                    "available_headroom": dict(zeros),
                },
            )
        entries[worker_count] = ExactNProfileEntry(
            worker_count=worker_count,
            status="CANDIDATE",
            qualification_sha256=next(
                (record.raw_sha256 for record in qualifications
                 if record.worker_count == worker_count), None),
            raw_manifest_sha256s=manifests,
            coverage=MappingProxyType({}),
            stages=MappingProxyType(stage_documents),
            review_reference=None,
        )
    return ApprovedBudgetProfile(
        schema_version=2,
        execution_identity_sha256=_require_sha256(
            "execution_identity_sha256", execution_identity_sha256),
        coverage_policy_sha256=_require_sha256(
            "coverage_policy_sha256", coverage_policy_sha256),
        entries=MappingProxyType(entries),
        raw_sha256=canonical_sha256(
            {
                "kind": "CANDIDATE_PROFILE",
                "entries": sorted(entries),
                "execution_identity_sha256": execution_identity_sha256,
            }
        ),
    )


# --- Candidate runtime composition (F1) ---------------------------------------------


def _hash_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class CandidateRunPlan:
    """Everything one authorized candidate batch needs, derived from sealed bindings.

    The original immutable authorization is carried, never a reconstruction: the child
    re-reads the same sealed bytes and the seal records the original dispatch, task,
    source commit, safety policy, owned scope, calibration and lifecycle values.
    """

    authorization: MeasurementAuthorization
    authorization_path: Path
    batch_id: str
    batch_root: Path
    evidence_root: Path
    config_path: Path
    bindings: MeasurementRuntimeBindings
    schema_version: int = 2
    run_mode: str = "execute"
    batch_kind: str = "FIRST_PASS"

    @property
    def authorization_sha256(self) -> str:
        return self.authorization.raw_sha256

    @property
    def worker_count(self) -> int:
        return self.authorization.worker_count

    @property
    def execution_identity_sha256(self) -> str:
        return self.authorization.execution_identity_sha256

    @property
    def seed(self) -> int:
        return self.authorization.seed

    @property
    def catalog_sha256(self) -> str:
        return self.authorization.catalog_sha256

    @property
    def intent(self) -> str:
        return self.authorization.intent

    def runner_argv(self, *, broker_image: str | None = None) -> tuple[str, ...]:
        """Existing composition argv plus the sealed measurement authority.

        The sealed binding is the image digest; the launcher compares the local tag it
        knows, so a caller that has verified the tag against that digest passes it here.
        """

        return (
            "--points", self.bindings.points_path,
            "--config", str(self.config_path),
            "--batch-id", self.batch_id,
            "--worker-count", str(self.worker_count),
            "--evidence-root", str(self.batch_root),
            "--broker-image",
            self.bindings.broker_image_id if broker_image is None else broker_image,
            "--broker-image-id", self.bindings.broker_image_id,
            "--yolo-weights", self.bindings.yolo_weights_path,
            "--yolo-weights-sha256", self.bindings.yolo_weights_sha256,
            "--grounded-root", self.bindings.grounded_root,
            "--grounded-manifest-sha256", self.bindings.grounded_manifest_sha256,
            "--run-mode", "execute",
            "--contract-version", "2",
            "--batch-kind", self.batch_kind,
            "--measurement-authorization", str(self.authorization_path),
            "--measurement-authorization-sha256", self.authorization.raw_sha256,
            "--provenance-binding", self.bindings.provenance_binding_path,
        )

    def verify_bindings(self) -> None:
        """Re-verify every binding byte and the sealed authority at use time."""

        document, digest = read_private_document(
            Path(self.authorization_path), expected_sha256=self.authorization.raw_sha256)
        if digest != self.authorization.raw_sha256:
            raise ContractError("AUTHORIZATION_HASH_MISMATCH")
        reloaded = MeasurementAuthorization.from_document(document, raw_sha256=digest)
        if reloaded.as_document() != self.authorization.as_document():
            raise ContractError("AUTHORIZATION_HASH_MISMATCH")
        if self.batch_root != reloaded.batch_root / self.batch_id:
            raise ContractError("BATCH_ROOT_OUTSIDE_AUTHORIZATION")
        checks = (
            ("points", self.bindings.points_path, self.bindings.points_sha256),
            ("yolo_weights", self.bindings.yolo_weights_path,
             self.bindings.yolo_weights_sha256),
            ("provenance_binding", self.bindings.provenance_binding_path,
             self.bindings.provenance_binding_sha256),
        )
        for name, raw_path, expected in checks:
            path = Path(raw_path)
            if not path.is_absolute() or not path.is_file():
                raise ContractError(f"BINDING_PATH: {name}")
            if _hash_file(path) != expected:
                raise ContractError(f"BINDING_HASH_MISMATCH: {name}")
        grounded = Path(self.bindings.grounded_root)
        manifest = grounded / "manifest.json"
        if not grounded.is_dir() or not manifest.is_file():
            raise ContractError("BINDING_PATH: grounded_root")
        if _hash_file(manifest) != self.bindings.grounded_manifest_sha256:
            raise ContractError("BINDING_HASH_MISMATCH: grounded_manifest")
        if self.bindings.points_sha256 != self.catalog_sha256:
            raise ContractError("BINDING_HASH_MISMATCH: catalog")
        if not Path(self.config_path).is_file():
            raise ContractError("BINDING_PATH: config")


def build_candidate_plan(
    *,
    authorization: MeasurementAuthorization,
    authorization_path: Path,
    config_path: Path,
    evidence_root: Path,
    batch_id: str,
) -> CandidateRunPlan:
    """Derive the composition plan from the sealed authorization and verify it now."""

    if not isinstance(authorization, MeasurementAuthorization):
        raise ContractError("AUTHORIZATION")
    _require_identifier("batch_id", batch_id)
    evidence_root = Path(evidence_root).resolve()
    if not evidence_root.is_dir():
        raise ContractError("EVIDENCE_ROOT_UNAVAILABLE")
    if not authorization.batch_root.is_relative_to(evidence_root):
        raise ContractError("BATCH_ROOT_OUTSIDE_EVIDENCE_ROOT")
    batch_root = authorization.batch_root / batch_id
    plan = CandidateRunPlan(
        authorization=authorization,
        authorization_path=Path(authorization_path),
        batch_id=batch_id,
        batch_root=batch_root,
        evidence_root=evidence_root,
        config_path=Path(config_path),
        bindings=authorization.runtime_bindings,
    )
    plan.verify_bindings()
    return plan


def run_candidate_batch(
    *,
    plan: CandidateRunPlan,
    runner,
    session,
    sealer=None,
) -> dict:
    """Compose owned limits -> sampler -> authorized workload -> seal.

    The session owns the delegated cgroup, the real sampler thread, the abort latch,
    the batch deadline and the verified cleanup; the runner only starts the workload
    through that session. Every failure keeps its own code and no seal is written.
    """

    if not isinstance(plan, CandidateRunPlan):
        raise ContractError("CANDIDATE_PLAN")
    if not callable(runner):
        raise ContractError("CANDIDATE_RUNNER")
    if session is None:
        raise ContractError("CANDIDATE_SESSION")
    if sealer is None:
        sealer = seal_measurement
    plan.batch_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    session.begin()
    receipt: Mapping[str, object] | None = None
    try:
        session.permit_side_effect()
        plan.verify_bindings()
        session.start_sampling()
        try:
            outcome = runner(plan, session)
        except ContractError as error:
            # A latched abort or an expired deadline is the real reason, not the
            # signal the workload received because of it.
            if session.deadline_exceeded:
                raise ContractError("MEASUREMENT_DEADLINE_EXCEEDED") from error
            if session.abort_reason:
                raise ContractError(
                    f"MEASUREMENT_ABORT_LATCHED: {session.abort_reason}") from error
            raise
        except Exception as error:  # noqa: BLE001 - any workload failure is fenced
            raise ContractError(
                f"MEASUREMENT_WORKLOAD_FAILED: {type(error).__name__}") from error
    finally:
        receipt = session.finish()
    if session.deadline_exceeded:
        raise ContractError("MEASUREMENT_DEADLINE_EXCEEDED")
    if session.abort_reason:
        raise ContractError(f"MEASUREMENT_ABORT_LATCHED: {session.abort_reason}")
    if not isinstance(outcome, Mapping):
        raise ContractError("MEASUREMENT_WORKLOAD_RESULT")
    raw_files = tuple(Path(item) for item in outcome.get("raw_files", ()))
    if session.receipt_path.is_file() and session.receipt_path not in raw_files:
        # The verified cleanup receipt is part of this batch's raw stream set.
        raw_files = (*raw_files, session.receipt_path)
    coverage_events = Path(outcome["coverage_events"])
    plan.verify_bindings()
    result = dict(outcome.get("result", {}))
    result["cleanup_receipt"] = dict(receipt)
    try:
        sealed = sealer(
            authorization=plan.authorization,
            batch_root=plan.batch_root,
            execution_identity_sha256=plan.execution_identity_sha256,
            raw_files=raw_files,
            coverage_events=coverage_events,
            result=result,
        )
    except ContractError:
        raise
    except Exception as error:  # noqa: BLE001 - sealing failures keep their own code
        raise ContractError(f"MEASUREMENT_SEAL_FAILED: {type(error).__name__}") from error
    return {
        "status": "SEALED",
        "sealed_path": str(sealed),
        "authorization_sha256": plan.authorization_sha256,
        "batch_id": plan.batch_id,
        "worker_count": plan.worker_count,
        "execution_identity_sha256": plan.execution_identity_sha256,
        "limits": dict(session.limits or {}),
        "samples": session.samples,
    }


def measurement_child_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Drop every production authority name: measurement grants nothing by inheritance."""

    from .resource_budget import _AUTHORITY_ENV

    values = dict(environment)
    for name in _AUTHORITY_ENV.values():
        values.pop(name, None)
    return values


def verify_measurement_arguments(
    *,
    authorization: MeasurementAuthorization,
    batch_id: str,
    worker_count: int,
    evidence_root: Path,
    points_path: Path,
    points_sha256: str,
    yolo_weights_path: Path,
    yolo_weights_sha256: str,
    grounded_root: Path,
    grounded_manifest_sha256: str,
    broker_image: str,
    config_path: Path,
) -> None:
    """A measurement child may only run the exact composition the operator sealed."""

    bindings = authorization.runtime_bindings
    checks = (
        ("BATCH_ID", batch_id == Path(evidence_root).name),
        ("EVIDENCE_ROOT", Path(evidence_root).resolve()
         == (authorization.batch_root / batch_id).resolve()),
        ("WORKER_COUNT", int(worker_count) == authorization.worker_count),
        ("POINTS", str(points_path) == bindings.points_path
         and points_sha256 == authorization.catalog_sha256),
        ("YOLO_WEIGHTS", str(yolo_weights_path) == bindings.yolo_weights_path
         and yolo_weights_sha256 == bindings.yolo_weights_sha256),
        ("GROUNDED_ROOT", str(grounded_root) == bindings.grounded_root
         and grounded_manifest_sha256 == bindings.grounded_manifest_sha256),
        ("BROKER_IMAGE", broker_image == bindings.broker_image_id),
        ("CONFIG", Path(config_path).is_file()),
    )
    for code, ok in checks:
        if not ok:
            raise ContractError(f"MEASUREMENT_ARGUMENT_MISMATCH: {code}")


def compose_measurement_admission(
    *, authorization_path: Path, authorization_sha256: str,
    environment: Mapping[str, str] | None = None, config_path: Path | None = None,
    source_root: Path | None = None, install_prefix: Path | None = None,
    observation_source=None, fingerprint_source=None, host_probe=None,
    inventory_reader=None,
):
    """Issue the one-shot measurement context and its MEASUREMENT-kind gate.

    The sealed authorization is re-read from its own bytes, an inherited production
    authority is refused instead of granting anything, and the runtime identity is
    derived from real config/inventory/hardware bytes and checked against the sealed
    identity before any admission.
    """

    from .contracts import ContractError as _ContractError
    from .resource_budget import (
        AllocationScope, FixedAdmissionGate, LiveObservationSource,
        ResourceBudgetProvider, build_runtime_fingerprint_from_environment,
        issue_measurement_context)

    del _ContractError
    authorization = MeasurementAuthorization.load(
        Path(authorization_path), expected_sha256=authorization_sha256)
    values = dict(os.environ if environment is None else environment)
    conflicts = sorted(
        name for name in _PRODUCTION_AUTHORITY_ENV.values() if values.get(name))
    if conflicts:
        raise ContractError(f"MEASUREMENT_AUTHORITY_ENV_CONFLICT: {conflicts}")
    bindings = authorization.runtime_bindings
    values["SO101_VALIDATION_PROVENANCE_BINDING"] = bindings.provenance_binding_path
    if config_path is not None:
        values["SO101_PARALLEL_RUNTIME_CONFIG"] = str(config_path)
    provider = ResourceBudgetProvider()

    def derive():
        return build_runtime_fingerprint_from_environment(
            values, identity=authorization.execution_identity_sha256,
            config_path=config_path, source_root=source_root,
            install_prefix=install_prefix, host_probe=host_probe,
            inventory_reader=inventory_reader)

    current = derive()

    def context_factory(request):
        if request.request_kind != "MEASUREMENT":
            raise ContractError("ALLOCATION_CONTEXT_MISMATCH")
        scope = AllocationScope(
            batch_id=request.batch_id, epoch=request.epoch,
            worker_count=request.worker_count, request_kind="MEASUREMENT",
            execution_identity_sha256=request.execution_identity_sha256)
        return issue_measurement_context(
            provider=provider, scope=scope, authorization_path=Path(authorization_path),
            owner_binding={
                "authorization_sha256": authorization.raw_sha256,
                "owned_scope_sha256": authorization.owned_scope_sha256,
            })

    source = observation_source or LiveObservationSource(
        environment=values, host_probe=host_probe)
    gate = FixedAdmissionGate(
        provider, context_factory=context_factory, current=current, live=None,
        observation_source=source, fingerprint_source=fingerprint_source or derive,
        request_kind="MEASUREMENT")
    return authorization, gate


_PRODUCTION_AUTHORITY_ENV = {
    "profile": "SO101_VALIDATION_BUDGET_PROFILE",
    "promotion": "SO101_VALIDATION_PROMOTION_RECORD",
    "deployment_receipt": "SO101_VALIDATION_DEPLOYMENT_RECEIPT",
    "installed_audit": "SO101_VALIDATION_INSTALLED_AUDIT",
    "location_binding": "SO101_VALIDATION_LOCATION_BINDING",
}
