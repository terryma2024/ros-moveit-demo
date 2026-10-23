"""Inference, numeric evidence, plan and execution receipts and the runtime decision."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from so101_demo.core.domain import State
from so101_demo.core.dynamic_pick import DYNAMIC_REACHABILITY_STATES
from so101_demo.parallel_batch.contracts.common import AttemptStatus, ValidationStatus
from so101_demo.runtime.parallel_worker_parts.process_tree import _finite_timestamp


@dataclass(frozen=True, slots=True)
class InferenceSnapshotReceipt:
    """Immutable canonical RGB input identity exported to the Broker."""

    path: Path
    source_stamp_monotonic_s: float
    source_stamp_ns: int
    source_frame_id: str
    shape: tuple[int, int, int]
    input_sha256: str
    simulation_session_id: str | None = None
    source_clock: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(
            self,
            "source_stamp_monotonic_s",
            _finite_timestamp(
                "capture source stamp", self.source_stamp_monotonic_s
            ),
        )
        if type(self.source_stamp_ns) is not int or self.source_stamp_ns <= 0:
            raise ValueError("capture source stamp ns must be positive")
        if (
            not isinstance(self.source_frame_id, str)
            or not self.source_frame_id.strip()
            or any(character.isspace() for character in self.source_frame_id)
        ):
            raise ValueError("capture source frame must be canonical")
        if (
            type(self.shape) is not tuple
            or len(self.shape) != 3
            or self.shape[2] != 3
            or any(type(value) is not int or value <= 0 for value in self.shape)
        ):
            raise ValueError("capture shape must be positive RGB")
        if (
            not isinstance(self.input_sha256, str)
            or len(self.input_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.input_sha256)
        ):
            raise ValueError("capture input SHA256 must be canonical")
        if self.simulation_session_id is not None and (
            not isinstance(self.simulation_session_id, str)
            or not self.simulation_session_id.strip()
        ):
            raise ValueError("capture simulation session must be canonical")
        if self.source_clock is not None and self.source_clock != "ros_sim":
            raise ValueError("capture source clock must be ros_sim")


@dataclass(frozen=True, slots=True)
class NumericEvidenceReceipt:
    depth_path: Path
    tf_path: Path
    physical_path: Path
    source_stamp_monotonic_s: float

    def __post_init__(self) -> None:
        for name in ("depth_path", "tf_path", "physical_path"):
            object.__setattr__(self, name, Path(getattr(self, name)))
        object.__setattr__(
            self,
            "source_stamp_monotonic_s",
            _finite_timestamp(
                "numeric evidence source stamp", self.source_stamp_monotonic_s
            ),
        )


@dataclass(frozen=True, slots=True)
class PlanSegmentReceipt:
    state: State
    start_state: Any
    terminal_state: Any
    plan: Any
    before_scene: Any
    after_scene: Any

    def __post_init__(self) -> None:
        if self.state not in DYNAMIC_REACHABILITY_STATES:
            raise ValueError("plan segment state is not authoritative")
        if self.start_state is None or self.terminal_state is None or self.plan is None:
            raise ValueError("plan segment receipt is incomplete")
        if self.before_scene is None or self.after_scene is None:
            raise ValueError("plan segment scene receipt is incomplete")


@dataclass(frozen=True, slots=True)
class PlanPrefixReceipt:
    segments: tuple[PlanSegmentReceipt, ...]
    completion_monotonic_s: float

    def __post_init__(self) -> None:
        if tuple(segment.state for segment in self.segments) != DYNAMIC_REACHABILITY_STATES:
            raise ValueError("plan prefix does not cover authoritative reachability states")
        for previous, current in zip(self.segments, self.segments[1:]):
            if current.start_state != previous.terminal_state:
                raise ValueError("plan prefix start state is not chained")
        object.__setattr__(
            self,
            "completion_monotonic_s",
            _finite_timestamp("plan completion", self.completion_monotonic_s),
        )


@dataclass(frozen=True, slots=True)
class RuntimeDecision:
    status: AttemptStatus | ValidationStatus
    reason: str = "OK"
    physical_action_proven_absent: bool = True
    segment_receipts: tuple[PlanSegmentReceipt, ...] = ()
    numeric_evidence: NumericEvidenceReceipt | None = None
    terminal_artifacts: tuple[Path, ...] = ()
    completion_monotonic_s: float | None = None
    #: the Teacher's own result (from its child's manifest) and the data status that child reported; the attempt
    #: status above is derived from the first two alone. None outside an ACT Teacher execution.
    teacher_execution_status: str | None = None
    teacher_task_result: str | None = None
    act_data_status: str | None = None
    act_data_reason: str | None = None
    #: the independent fresh-process QC report written beside the episode (Phase A4c); None when QC did not produce one
    qc_report_path: Path | None = None
    #: phase 1 of the two-phase collection: the recording receipt (`raw/recording-receipt.json`) that makes PENDING_QC data sealable
    #: without an episode; None for every other decision
    recording_receipt_path: Path | None = None


@dataclass(frozen=True, slots=True)
class ExecutionCompletionReceipt:
    decision: RuntimeDecision
    completion_monotonic_s: float
    #: False when the wait for the Teacher child gave up with the child still alive: the Teacher has not exited
    teacher_child_exited: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.decision, RuntimeDecision):
            raise TypeError("execution completion decision is required")
        if not isinstance(self.decision.status, AttemptStatus):
            raise ValueError("execution completion requires AttemptStatus")
        object.__setattr__(
            self,
            "completion_monotonic_s",
            _finite_timestamp("execution completion", self.completion_monotonic_s),
        )
