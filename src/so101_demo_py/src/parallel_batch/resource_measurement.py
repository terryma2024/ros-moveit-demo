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
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from .contracts import ContractError
from .measurement_control import ProcessIdentity
from .resource_budget import (
    DIMENSIONS,
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
        elapsed = monotonic_s - state.get("monotonic_s", monotonic_s)
        cpu_delta = 0.0 if elapsed <= 0 else (cpu_usage_us - state.get("cpu_usage_us", cpu_usage_us)) / 1e6 / elapsed
        swap_delta = max(0, swap_total - state.get("swap_total", swap_total))
        psi_delta = max(0.0, psi_total - state.get("psi_total", psi_total))
        cpu_delta = max(0.0, cpu_delta)
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
    "safety_policy_sha256", "intent", "calibration_sha256",
)


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
) -> Path:
    """Seal one raw measurement batch (B). It cannot reference a future profile."""

    if not isinstance(authorization, MeasurementAuthorization):
        raise ContractError("AUTHORIZATION")
    _require_sha256("execution_identity_sha256", execution_identity_sha256)
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
    }
    encoded = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    sealed_root = Path(authorization.batch_root) / "sealed"
    sealed_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    target = sealed_root / f"sealed-{authorization.dispatch_id}-{len(files)}-{document['sealed_at_ns']}.json"
    _write_private(target, encoded)
    return target
