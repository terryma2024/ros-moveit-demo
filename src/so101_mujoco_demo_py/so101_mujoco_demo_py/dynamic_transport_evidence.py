"""Replayable per-physics-step evidence for dynamic transport diagnostics."""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class EvidenceInvalid(ValueError):
    """Raised when a transport trace cannot support a diagnostic conclusion."""


class ContactForceMode(StrEnum):
    PRE_TRANSPORT_STATIC_HOLD = "PRE_TRANSPORT_STATIC_HOLD"
    DYNAMIC_TRANSPORT_SHADOW = "DYNAMIC_TRANSPORT_SHADOW"


class TransportBoundaryKind(StrEnum):
    PHASE_START = "PHASE_START"
    WAYPOINT_START = "WAYPOINT_START"
    WAYPOINT_END = "WAYPOINT_END"
    PHASE_END = "PHASE_END"


def _finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _finite_tuple(name: str, value: tuple[float, ...], size: int) -> None:
    if not isinstance(value, tuple) or len(value) != size:
        raise ValueError(f"{name} must contain {size} values")
    for item in value:
        _finite(name, item)


@dataclass(frozen=True, slots=True)
class PhysicsContactSample:
    side: str
    object_body: str
    object_geom: str
    other_body: str
    other_geom: str
    signed_distance_m: float
    normal_force_n: float
    normal_world: tuple[float, float, float]

    def __post_init__(self) -> None:
        if self.side not in {"left", "right", "other"}:
            raise ValueError("contact side must be left, right, or other")
        if any(
            not isinstance(value, str) or not value
            for value in (self.object_body, self.object_geom, self.other_body, self.other_geom)
        ):
            raise ValueError("contact identities must be non-empty")
        _finite("signed_distance_m", self.signed_distance_m)
        _finite("normal_force_n", self.normal_force_n)
        if self.normal_force_n < 0.0:
            raise ValueError("normal_force_n must be non-negative")
        _finite_tuple("normal_world", self.normal_world, 3)
        magnitude = math.sqrt(sum(component * component for component in self.normal_world))
        if not math.isclose(magnitude, 1.0, rel_tol=1e-12, abs_tol=1e-12):
            raise ValueError("normal_world must be a unit vector")


@dataclass(frozen=True, slots=True)
class PhysicsStepSample:
    simulation_session_id: str
    reset_epoch: int
    physics_step: int
    simulation_time_s: float
    object_pose_world_xyz_xyzw: tuple[float, float, float, float, float, float, float]
    object_twist_world_linear_angular: tuple[float, float, float, float, float, float]
    maximum_normal_force_n: float
    left_fingertip_total_normal_force_n: float
    right_fingertip_total_normal_force_n: float
    fingertip_max_single_contact_force_n: float
    global_max_single_contact_force_n: float
    left_fingertip_compression_m: float
    right_fingertip_compression_m: float
    net_contact_force_world_n: tuple[float, float, float]
    truncated: bool
    left_fingertip_contacts: tuple[PhysicsContactSample, ...]
    right_fingertip_contacts: tuple[PhysicsContactSample, ...]
    other_object_contacts: tuple[PhysicsContactSample, ...]

    def __post_init__(self) -> None:
        if not self.simulation_session_id:
            raise ValueError("simulation_session_id must be non-empty")
        for name in ("reset_epoch", "physics_step"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        _finite("simulation_time_s", self.simulation_time_s)
        if self.simulation_time_s < 0.0:
            raise ValueError("simulation_time_s must be non-negative")
        _finite_tuple("object_pose_world_xyz_xyzw", self.object_pose_world_xyz_xyzw, 7)
        _finite_tuple(
            "object_twist_world_linear_angular", self.object_twist_world_linear_angular, 6
        )
        for name in (
            "maximum_normal_force_n",
            "left_fingertip_total_normal_force_n",
            "right_fingertip_total_normal_force_n",
            "fingertip_max_single_contact_force_n",
            "global_max_single_contact_force_n",
            "left_fingertip_compression_m",
            "right_fingertip_compression_m",
        ):
            value = getattr(self, name)
            _finite(name, value)
            if value < 0.0:
                raise ValueError(f"{name} must be non-negative")
        _finite_tuple("net_contact_force_world_n", self.net_contact_force_world_n, 3)
        if not isinstance(self.truncated, bool):
            raise TypeError("truncated must be bool")
        arrays = (
            self.left_fingertip_contacts,
            self.right_fingertip_contacts,
            self.other_object_contacts,
        )
        if any(not isinstance(items, tuple) for items in arrays):
            raise TypeError("contact arrays must be tuples")
        if any(not isinstance(item, PhysicsContactSample) for items in arrays for item in items):
            raise TypeError("contact arrays must contain PhysicsContactSample")
        if not math.isclose(
            self.maximum_normal_force_n,
            self.global_max_single_contact_force_n,
            rel_tol=0.0,
            abs_tol=1e-12,
        ):
            raise ValueError("global maximum must preserve maximum_normal_force_n semantics")


@dataclass(frozen=True, slots=True)
class PhysicsStepChunk:
    chunk_sequence: int
    simulation_session_id: str
    reset_epoch: int
    first_physics_step: int
    last_physics_step: int
    first_simulation_time_s: float
    last_simulation_time_s: float
    failed_publish_attempts: int
    evidence_loss: bool
    samples: tuple[PhysicsStepSample, ...]


@dataclass(frozen=True, slots=True)
class TransportBoundary:
    kind: TransportBoundaryKind
    waypoint: int
    physics_step: int

    def __post_init__(self) -> None:
        if not isinstance(self.kind, TransportBoundaryKind):
            raise TypeError("boundary kind must be TransportBoundaryKind")
        if (
            isinstance(self.waypoint, bool)
            or not isinstance(self.waypoint, int)
            or self.waypoint <= 0
        ):
            raise ValueError("waypoint must be positive")
        if (
            isinstance(self.physics_step, bool)
            or not isinstance(self.physics_step, int)
            or self.physics_step < 0
        ):
            raise ValueError("physics_step must be non-negative")


@dataclass(frozen=True, slots=True)
class DynamicTransportRun:
    run_id: str
    simulation_session_id: str
    reset_epoch: int
    physics_timestep_s: float
    chunks: tuple[PhysicsStepChunk, ...]
    boundaries: tuple[TransportBoundary, ...]
    physical_transport_outcome: str


@dataclass(frozen=True, slots=True)
class OverpressureWindow:
    waypoint: int
    first_physics_step: int
    last_physics_step: int
    sample_count: int
    duration_s: float
    peak_maximum_normal_force_n: float
    force_time_exposure_n_s: float
    shadow_excess_force_time_exposure_n_s: float


@dataclass(frozen=True, slots=True)
class WaypointDiagnostic:
    waypoint: int
    statistical_role: str
    first_physics_step: int
    last_physics_step: int
    peak_global_max_single_contact_force_n: float
    force_time_exposure_n_s: float
    shadow_excess_force_time_exposure_n_s: float
    net_contact_impulse_vector_n_s: tuple[float, float, float]
    maximum_left_fingertip_compression_m: float
    maximum_right_fingertip_compression_m: float


@dataclass(frozen=True, slots=True)
class DynamicTransportSummary:
    run_id: str
    acceptance_role: str
    independent_experiment_units: int
    peak_global_max_single_contact_force_n: float
    force_time_exposure_n_s: float
    shadow_excess_force_time_exposure_n_s: float
    net_contact_impulse_vector_n_s: tuple[float, float, float]
    maximum_left_fingertip_compression_m: float
    maximum_right_fingertip_compression_m: float
    sustained_overpressure_windows: tuple[OverpressureWindow, ...]
    waypoints: tuple[WaypointDiagnostic, ...]


def _trapezoid(samples: tuple[PhysicsStepSample, ...], value) -> float:
    return sum(
        0.5 * (value(left) + value(right)) * (right.simulation_time_s - left.simulation_time_s)
        for left, right in zip(samples, samples[1:], strict=False)
    )


def _vector_trapezoid(samples: tuple[PhysicsStepSample, ...]) -> tuple[float, float, float]:
    return tuple(
        _trapezoid(samples, lambda item, axis=axis: item.net_contact_force_world_n[axis])
        for axis in range(3)
    )


def _require_replayed_scalar(name: str, actual: float, expected: float) -> None:
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise EvidenceInvalid(f"{name} does not replay from raw contacts")


def _validate_raw_contact_replay(sample: PhysicsStepSample) -> None:
    groups = (
        ("left", sample.left_fingertip_contacts),
        ("right", sample.right_fingertip_contacts),
        ("other", sample.other_object_contacts),
    )
    for expected_side, contacts in groups:
        if any(contact.side != expected_side for contact in contacts):
            raise EvidenceInvalid(f"{expected_side} contact array contains a different side")
    left = sample.left_fingertip_contacts
    right = sample.right_fingertip_contacts
    all_contacts = left + right + sample.other_object_contacts
    fingertip_contacts = left + right
    _require_replayed_scalar(
        "left fingertip total",
        sample.left_fingertip_total_normal_force_n,
        sum(contact.normal_force_n for contact in left),
    )
    _require_replayed_scalar(
        "right fingertip total",
        sample.right_fingertip_total_normal_force_n,
        sum(contact.normal_force_n for contact in right),
    )
    _require_replayed_scalar(
        "fingertip maximum",
        sample.fingertip_max_single_contact_force_n,
        max((contact.normal_force_n for contact in fingertip_contacts), default=0.0),
    )
    global_maximum = max((contact.normal_force_n for contact in all_contacts), default=0.0)
    _require_replayed_scalar(
        "global maximum", sample.global_max_single_contact_force_n, global_maximum
    )
    _require_replayed_scalar("maximum normal force", sample.maximum_normal_force_n, global_maximum)
    _require_replayed_scalar(
        "left fingertip compression",
        sample.left_fingertip_compression_m,
        max((max(0.0, -contact.signed_distance_m) for contact in left), default=0.0),
    )
    _require_replayed_scalar(
        "right fingertip compression",
        sample.right_fingertip_compression_m,
        max((max(0.0, -contact.signed_distance_m) for contact in right), default=0.0),
    )
    replayed_net_force = tuple(
        sum(contact.normal_world[axis] * contact.normal_force_n for contact in all_contacts)
        for axis in range(3)
    )
    if any(
        not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
        for actual, expected in zip(
            sample.net_contact_force_world_n, replayed_net_force, strict=True
        )
    ):
        raise EvidenceInvalid("net contact force does not replay from raw contacts")


def _validate_and_flatten(run: DynamicTransportRun) -> tuple[PhysicsStepSample, ...]:
    if not run.run_id or not run.simulation_session_id or not run.physical_transport_outcome:
        raise EvidenceInvalid("run identity is incomplete")
    _finite("physics_timestep_s", run.physics_timestep_s)
    if run.physics_timestep_s <= 0.0 or not run.chunks:
        raise EvidenceInvalid("run must contain chunks at a positive timestep")
    flattened: list[PhysicsStepSample] = []
    first_chunk_sequence = run.chunks[0].chunk_sequence
    for offset, item in enumerate(run.chunks):
        expected_sequence = first_chunk_sequence + offset
        if item.chunk_sequence != expected_sequence:
            raise EvidenceInvalid("chunk sequence mismatch")
        if item.evidence_loss:
            raise EvidenceInvalid("evidence loss latched")
        if not item.samples:
            raise EvidenceInvalid("empty physics-step chunk")
        if item.simulation_session_id != run.simulation_session_id:
            raise EvidenceInvalid("simulation session mismatch")
        if item.reset_epoch != run.reset_epoch:
            raise EvidenceInvalid("reset epoch mismatch")
        if (
            item.first_physics_step != item.samples[0].physics_step
            or item.last_physics_step != item.samples[-1].physics_step
            or not math.isclose(
                item.first_simulation_time_s,
                item.samples[0].simulation_time_s,
                abs_tol=1e-12,
            )
            or not math.isclose(
                item.last_simulation_time_s,
                item.samples[-1].simulation_time_s,
                abs_tol=1e-12,
            )
        ):
            raise EvidenceInvalid("chunk range mismatch")
        flattened.extend(item.samples)
    samples = tuple(flattened)
    for index, current in enumerate(samples):
        if current.simulation_session_id != run.simulation_session_id:
            raise EvidenceInvalid("simulation session mismatch")
        if current.reset_epoch != run.reset_epoch:
            raise EvidenceInvalid("reset epoch mismatch")
        if current.truncated:
            raise EvidenceInvalid("truncated contact evidence")
        _validate_raw_contact_replay(current)
        if index == 0:
            continue
        previous = samples[index - 1]
        if current.physics_step == previous.physics_step:
            raise EvidenceInvalid("duplicate physics step")
        if current.physics_step < previous.physics_step:
            raise EvidenceInvalid("reversed physics step")
        if current.physics_step != previous.physics_step + 1:
            raise EvidenceInvalid("missing physics step")
        expected_time = previous.simulation_time_s + run.physics_timestep_s
        if not math.isclose(current.simulation_time_s, expected_time, abs_tol=1e-12):
            raise EvidenceInvalid("simulation time is inconsistent with physics step")
    return samples


def _waypoint_ranges(
    run: DynamicTransportRun, samples: tuple[PhysicsStepSample, ...]
) -> tuple[tuple[int, int, int], ...]:
    if not run.boundaries:
        raise EvidenceInvalid("transport boundaries are missing")
    if (
        run.boundaries[0].kind is not TransportBoundaryKind.PHASE_START
        or run.boundaries[0].physics_step not in {item.physics_step for item in samples}
        or run.boundaries[-1].kind is not TransportBoundaryKind.PHASE_END
        or run.boundaries[-1].physics_step != samples[-1].physics_step
    ):
        raise EvidenceInvalid("phase boundary is not closed on raw evidence")
    open_waypoints: dict[int, int] = {}
    ranges: list[tuple[int, int, int]] = []
    previous_step = samples[0].physics_step
    for boundary in run.boundaries:
        if boundary.physics_step < previous_step:
            raise EvidenceInvalid("boundary order reversed")
        previous_step = boundary.physics_step
        if boundary.kind is TransportBoundaryKind.WAYPOINT_START:
            if boundary.waypoint in open_waypoints:
                raise EvidenceInvalid("duplicate waypoint boundary")
            open_waypoints[boundary.waypoint] = boundary.physics_step
        elif boundary.kind is TransportBoundaryKind.WAYPOINT_END:
            start = open_waypoints.pop(boundary.waypoint, None)
            if start is None:
                raise EvidenceInvalid("waypoint end has no start")
            if boundary.physics_step < start:
                raise EvidenceInvalid("waypoint boundary reversed")
            ranges.append((boundary.waypoint, start, boundary.physics_step))
    if open_waypoints:
        raise EvidenceInvalid("unclosed waypoint boundary")
    if not ranges:
        raise EvidenceInvalid("no closed waypoint boundary")
    ranges.sort()
    return tuple(ranges)


def _overpressure_windows(
    waypoint: int,
    samples: tuple[PhysicsStepSample, ...],
    shadow_force_n: float,
    timestep_s: float,
) -> tuple[OverpressureWindow, ...]:
    windows: list[OverpressureWindow] = []
    start = 0
    while start < len(samples):
        if samples[start].maximum_normal_force_n <= shadow_force_n:
            start += 1
            continue
        end = start
        while end + 1 < len(samples) and samples[end + 1].maximum_normal_force_n > shadow_force_n:
            end += 1
        selected = samples[start : end + 1]
        windows.append(
            OverpressureWindow(
                waypoint=waypoint,
                first_physics_step=selected[0].physics_step,
                last_physics_step=selected[-1].physics_step,
                sample_count=len(selected),
                duration_s=len(selected) * timestep_s,
                peak_maximum_normal_force_n=max(item.maximum_normal_force_n for item in selected),
                force_time_exposure_n_s=_trapezoid(
                    selected, lambda item: item.maximum_normal_force_n
                ),
                shadow_excess_force_time_exposure_n_s=_trapezoid(
                    selected,
                    lambda item: max(item.maximum_normal_force_n - shadow_force_n, 0.0),
                ),
            )
        )
        start = end + 1
    return tuple(windows)


def analyze_dynamic_transport(
    run: DynamicTransportRun, *, shadow_force_n: float
) -> DynamicTransportSummary:
    _finite("shadow_force_n", shadow_force_n)
    if shadow_force_n <= 0.0:
        raise ValueError("shadow_force_n must be positive")
    samples = _validate_and_flatten(run)
    sample_by_step = {item.physics_step: item for item in samples}
    waypoint_diagnostics: list[WaypointDiagnostic] = []
    windows: list[OverpressureWindow] = []
    for waypoint, start, end in _waypoint_ranges(run, samples):
        try:
            selected = tuple(sample_by_step[step] for step in range(start, end + 1))
        except KeyError as error:
            raise EvidenceInvalid("waypoint boundary crosses missing physics step") from error
        exposure = _trapezoid(selected, lambda item: item.maximum_normal_force_n)
        excess = _trapezoid(
            selected, lambda item: max(item.maximum_normal_force_n - shadow_force_n, 0.0)
        )
        waypoint_diagnostics.append(
            WaypointDiagnostic(
                waypoint=waypoint,
                statistical_role="repeated_measure",
                first_physics_step=start,
                last_physics_step=end,
                peak_global_max_single_contact_force_n=max(
                    item.global_max_single_contact_force_n for item in selected
                ),
                force_time_exposure_n_s=exposure,
                shadow_excess_force_time_exposure_n_s=excess,
                net_contact_impulse_vector_n_s=_vector_trapezoid(selected),
                maximum_left_fingertip_compression_m=max(
                    item.left_fingertip_compression_m for item in selected
                ),
                maximum_right_fingertip_compression_m=max(
                    item.right_fingertip_compression_m for item in selected
                ),
            )
        )
        windows.extend(
            _overpressure_windows(waypoint, selected, shadow_force_n, run.physics_timestep_s)
        )
    return DynamicTransportSummary(
        run_id=run.run_id,
        acceptance_role="diagnostic_only",
        independent_experiment_units=1,
        peak_global_max_single_contact_force_n=max(
            item.peak_global_max_single_contact_force_n for item in waypoint_diagnostics
        ),
        force_time_exposure_n_s=sum(item.force_time_exposure_n_s for item in waypoint_diagnostics),
        shadow_excess_force_time_exposure_n_s=sum(
            item.shadow_excess_force_time_exposure_n_s for item in waypoint_diagnostics
        ),
        net_contact_impulse_vector_n_s=tuple(
            sum(item.net_contact_impulse_vector_n_s[axis] for item in waypoint_diagnostics)
            for axis in range(3)
        ),
        maximum_left_fingertip_compression_m=max(
            item.maximum_left_fingertip_compression_m for item in waypoint_diagnostics
        ),
        maximum_right_fingertip_compression_m=max(
            item.maximum_right_fingertip_compression_m for item in waypoint_diagnostics
        ),
        sustained_overpressure_windows=tuple(windows),
        waypoints=tuple(waypoint_diagnostics),
    )


def _canonical_json(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary.exists():
            temporary.unlink()


class AtomicTransportEvidenceStore:
    """Content-addressed chunks plus an atomically replaced run index."""

    def __init__(self, root: Path, *, run_id: str) -> None:
        if not run_id:
            raise ValueError("run_id must be non-empty")
        self.root = root
        self.run_id = run_id
        self._chunks: list[dict[str, Any]] = []
        self._boundaries: list[dict[str, Any]] = []
        self._metadata: dict[str, Any] = {}
        self._index_path = root / "run-index.json"

    def _write_index(self, **terminal: Any) -> Path:
        document: dict[str, Any] = {
            "schema": "so101-dynamic-transport-raw-v4",
            "run_id": self.run_id,
            "chunks": list(self._chunks),
            "boundaries": list(self._boundaries),
            "status": "RUNNING",
        }
        document.update(self._metadata)
        document.update(terminal)
        _atomic_write(self._index_path, _canonical_json(document))
        return self._index_path

    def checkpoint_metadata(self, **metadata: Any) -> Path:
        self._metadata.update(metadata)
        return self._write_index()

    def checkpoint_chunk(self, chunk: PhysicsStepChunk) -> str:
        expected_sequence = (
            chunk.chunk_sequence if not self._chunks else self._chunks[-1]["chunk_sequence"] + 1
        )
        if chunk.chunk_sequence != expected_sequence:
            raise EvidenceInvalid("chunk sequence mismatch at checkpoint")
        document = asdict(chunk)
        content = _canonical_json(document)
        digest = hashlib.sha256(content).hexdigest()
        relative = Path("chunks") / f"{chunk.chunk_sequence:06d}-{digest}.json"
        _atomic_write(self.root / relative, content)
        self._chunks.append(
            {
                "chunk_sequence": chunk.chunk_sequence,
                "first_physics_step": chunk.first_physics_step,
                "last_physics_step": chunk.last_physics_step,
                "path": str(relative),
                "sha256": digest,
            }
        )
        self._write_index()
        return digest

    def checkpoint_boundary(self, boundary: TransportBoundary) -> Path:
        if not isinstance(boundary, TransportBoundary):
            raise TypeError("boundary must be TransportBoundary")
        if self._boundaries and boundary.physics_step < self._boundaries[-1]["physics_step"]:
            raise EvidenceInvalid("boundary order reversed at checkpoint")
        self._boundaries.append(
            {
                "kind": boundary.kind.value,
                "waypoint": boundary.waypoint,
                "physics_step": boundary.physics_step,
            }
        )
        return self._write_index()

    def close_partial(
        self, *, outcome_class: str, trigger_physics_step: int, **terminal: Any
    ) -> Path:
        if not outcome_class:
            raise ValueError("outcome_class must be non-empty")
        if isinstance(trigger_physics_step, bool) or trigger_physics_step < 0:
            raise ValueError("trigger_physics_step must be non-negative")
        return self._write_index(
            status="PARTIAL_CLOSED",
            outcome_class=outcome_class,
            trigger_physics_step=trigger_physics_step,
            **terminal,
        )

    def close_complete(self, *, physical_transport_outcome: str, **terminal: Any) -> Path:
        if not physical_transport_outcome:
            raise ValueError("physical_transport_outcome must be non-empty")
        return self._write_index(
            status="COMPLETE",
            outcome_class="PHYSICAL_TRANSPORT_SUCCESS",
            physical_transport_outcome=physical_transport_outcome,
            **terminal,
        )

    def close_invalid(self, *, invalid_reason: str, **terminal: Any) -> Path:
        if not invalid_reason:
            raise ValueError("invalid_reason must be non-empty")
        return self._write_index(
            status="PARTIAL_CLOSED",
            outcome_class="INVALID_EVIDENCE",
            invalid_reason=invalid_reason,
            **terminal,
        )
