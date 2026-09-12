"""Isolated, injectable runtime boundary for one parallel MuJoCo Worker."""

from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import io
import math
import os
from pathlib import Path
import re
import stat
import time
from typing import Any, Callable

import numpy as np

from ..application.qualification_stack import ros2_command
from ..core.domain import State
from ..core.dynamic_pick import DYNAMIC_REACHABILITY_STATES
from ..parallel_batch.contracts import AttemptStatus, RunMode, ValidationStatus
from ..parallel_batch.resources import WorkerResources
from .task_stack import (
    OwnedProcessGroup,
    OwnedProcessManifest,
    PersistentStackConfig,
    StackProcessSpec,
)


_READY_REQUIREMENTS = (
    "controllers",
    "move_group",
    "joint_states",
    "planning_scene",
)

_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def _finite_timestamp(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be finite")
    result = float(value)
    if not math.isfinite(result) or result < 0.0:
        raise ValueError(f"{name} must be finite")
    return result


@dataclass(frozen=True, slots=True)
class SourceStampedCapture:
    path: Path
    source_stamp_monotonic_s: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", Path(self.path))
        object.__setattr__(
            self,
            "source_stamp_monotonic_s",
            _finite_timestamp(
                "capture source stamp", self.source_stamp_monotonic_s
            ),
        )


@dataclass(frozen=True, slots=True)
class InferenceSnapshotReceipt:
    """Immutable canonical RGB input identity exported to the Broker."""

    path: Path
    source_stamp_monotonic_s: float
    source_stamp_ns: int
    source_frame_id: str
    shape: tuple[int, int, int]
    input_sha256: str

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


@dataclass(frozen=True, slots=True)
class ExecutionCompletionReceipt:
    decision: RuntimeDecision
    completion_monotonic_s: float

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


class _ChainedPlanningControl:
    def __init__(self, control: Any) -> None:
        self._control = control
        self._start_state = None

    def plan_tcp_motion(self, request: Any):
        if self._start_state is not None:
            request = replace(request, start_state=self._start_state)
        plan = self._control.plan_tcp_motion(request)
        if getattr(plan, "accepted", None) is True:
            terminal = getattr(plan, "terminal_state", None)
            if terminal is None:
                raise RuntimeError("CUP_POSE_PLAN_TERMINAL_STATE_MISSING")
            self._start_state = terminal
        return plan


class RosDynamicPlanPrefixAdapter:
    """Use ``RosDynamicPlanner`` for every dynamic plan-only motion state."""

    def __init__(
        self,
        node: Any,
        template: Any,
        scene: Any,
        *,
        planner_factory: Callable[[Any, tuple[str, ...]], Any] | None = None,
        target_resolver: Callable[[Any, Any], Any] | None = None,
        plan_state: Callable[..., Any] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if planner_factory is None:
            from ..ros.dynamic_planner import RosDynamicPlanner

            planner_factory = RosDynamicPlanner
        if target_resolver is None:
            from ..core.dynamic_pick import resolve_motion_targets

            target_resolver = resolve_motion_targets
        if plan_state is None:
            from ..application.dynamic_plan_only import plan_dynamic_state_with_scene_gates

            plan_state = plan_dynamic_state_with_scene_gates
        from ..application.dynamic_plan_only import DynamicPlanningOptions

        self._template = template
        self._scene = scene
        self._planner = planner_factory(node, template.arm_joint_names)
        self._target_resolver = target_resolver
        self._plan_state = plan_state
        self._clock = clock
        self._options = DynamicPlanningOptions(
            template.planning_frame,
            template.planning_group,
            template.tcp_link,
            template.position_tolerance_m,
            template.orientation_tolerance_rad,
            template.planning_timeout_s,
            template.velocity_scaling,
            template.acceleration_scaling,
        )

    def __call__(self, lease: Any, admitted: Any, states: tuple[State, ...]):
        del lease
        if states != DYNAMIC_REACHABILITY_STATES:
            raise RuntimeError("PLAN_PREFIX_STATES_NOT_AUTHORITATIVE")
        targets = self._target_resolver(admitted, self._template)
        control = _ChainedPlanningControl(self._planner.control)
        segments = []
        for state in states:
            plan, before, after = self._plan_state(
                state=state,
                provider=targets,
                control=control,
                options=self._options,
                scene=self._scene,
                sample=admitted,
                template=self._template,
            )
            if getattr(plan, "accepted", None) is not True:
                raise RuntimeError("CUP_POSE_PLAN_FAILED")
            terminal = getattr(plan, "terminal_state", None)
            if terminal is None:
                raise RuntimeError("CUP_POSE_PLAN_TERMINAL_STATE_MISSING")
            segments.append(
                PlanSegmentReceipt(
                    state,
                    getattr(plan, "start_state", None),
                    terminal,
                    plan,
                    before,
                    after,
                )
            )
        return PlanPrefixReceipt(tuple(segments), self._clock())

    def close(self) -> None:
        self._planner.close()


def headless_task_station_config(resources: WorkerResources) -> PersistentStackConfig:
    """Construct the single supported Linux headless Worker launch command."""

    if not isinstance(resources, WorkerResources):
        raise TypeError("WorkerResources are required")
    command = ros2_command(
        "launch",
        "so101_demo_py",
        "so101_mujoco_task_station.launch.py",
        "headless:=true",
        "sensor_rendering:=true",
        "include_teleop:=false",
        f"session_id:={resources.session_id}",
        f"task_evidence_root:={resources.worker_root}",
    )
    return PersistentStackConfig(
        resources.session_id,
        True,
        resources.worker_root,
        (StackProcessSpec("task-station", tuple(command)),),
    )


def _required(name: str):
    def missing(*_args, **_kwargs):
        raise RuntimeError(f"parallel Worker runtime port is required: {name}")

    return missing


class DryRunWorkerRuntime:
    """Scheduler-only Worker runtime that cannot construct a ROS command."""

    def __init__(self, resources: WorkerResources) -> None:
        self.resources = resources

    @property
    def owned_process_manifest(self) -> OwnedProcessManifest:
        return OwnedProcessManifest(tuple())

    @property
    def captured_artifacts(self) -> tuple[Path, ...]:
        return tuple()

    def start_physical_runtime(self) -> None:
        return None

    def worker_ready_gate(self) -> bool:
        return True

    def consumer_argv(self, reset_epoch: object) -> None:
        del reset_epoch
        return None

    def scheduler_trace(self, lease: Any) -> RuntimeDecision:
        del lease
        return RuntimeDecision(ValidationStatus.VALIDATION_PASSED)

    def reset_and_validate_point(self, lease: Any):
        del lease
        raise RuntimeError("dry-run has no physical point gate")

    def localize_and_admit_pose(self, lease: Any, broker_result: Any):
        del lease, broker_result
        raise RuntimeError("dry-run has no perception admission")

    reset_point = reset_and_validate_point
    admit_pose = localize_and_admit_pose

    def plan_expert(self, lease: Any, admitted: Any):
        del lease, admitted
        raise RuntimeError("dry-run cannot plan")

    def execute_expert(self, lease: Any, admitted: Any):
        del lease, admitted
        raise RuntimeError("dry-run cannot execute")

    def capture_terminal(self, lease: Any, **kwargs):
        del lease, kwargs
        return tuple()

    def cancel_motion(self, lease: Any) -> bool:
        del lease
        return True

    def confirm_no_controller_goal(self, lease: Any) -> bool:
        del lease
        return True

    def recover(self, worker_id: str, generation: int, deadline_monotonic_s: float) -> bool:
        del worker_id, generation, deadline_monotonic_s
        return True

    def shutdown_owned(self) -> None:
        return None


class ParallelWorkerRuntime:
    """Own one headless station and all lease-scoped Worker operations."""

    def __init__(
        self,
        resources: WorkerResources,
        run_mode: RunMode,
        *,
        process_group: Any | None = None,
        ready_probe: Callable[[tuple[str, ...]], bool] | None = None,
        reset_point: Callable[[Any], Any] | None = None,
        reserve_workspace: Callable[[Any, Any], Any] | None = None,
        initial_gate: Callable[[Any, Any], Any] | None = None,
        localize: Callable[[Any, Any], Any] | None = None,
        admit_pose: Callable[[Any, Any], Any] | None = None,
        publish_pose: Callable[[Any], Any] | None = None,
        plan_prefix: Callable[[Any, Any, tuple[State, ...]], Any] | None = None,
        execute_result: Callable[[Any, Any, Any], Any] | None = None,
        consumer_ready: Callable[[Any], bool] | None = None,
        capture_rgb: Callable[[Path, float], SourceStampedCapture] | None = None,
        capture_numeric_evidence: Callable[
            [Any, Any, Path, float], NumericEvidenceReceipt
        ]
        | None = None,
        cancel_motion: Callable[[Any], bool] | None = None,
        confirm_no_controller_goal: Callable[[Any], bool] | None = None,
        recovery: Callable[[str, int, float], bool] | None = None,
        replace_resources: Callable[..., WorkerResources] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(resources, WorkerResources):
            raise TypeError("WorkerResources are required")
        if run_mode not in (RunMode.PLAN_ONLY, RunMode.EXECUTE):
            raise ValueError("physical Worker runtime requires plan_only or execute")
        self.resources = resources
        self.run_mode = run_mode
        self._processes = process_group or OwnedProcessGroup()
        self._ready_probe = ready_probe or _required("ready_probe")
        self._reset_point = reset_point or _required("reset_point")
        # Task 11 production always supplies the durable reservation owner.  The
        # no-op default preserves the reusable Task 10 unit-test seam.
        self._reserve_workspace = reserve_workspace or (lambda _lease, _receipt: True)
        self._initial_gate = initial_gate or _required("initial_gate")
        self._localize = localize or _required("localize")
        self._admit_pose = admit_pose or _required("admit_pose")
        self._publish_pose = publish_pose or _required("publish_pose")
        self._plan_prefix = plan_prefix or _required("plan_prefix")
        self._execute_result = execute_result or _required("execute_result")
        self._consumer_ready = consumer_ready or _required("consumer_ready")
        self._capture_rgb = capture_rgb or _required("capture_rgb")
        self._capture_numeric_evidence = capture_numeric_evidence or _required(
            "capture_numeric_evidence"
        )
        self._cancel_motion = cancel_motion or (lambda _lease: True)
        self._confirm_no_controller_goal = confirm_no_controller_goal or (
            lambda _lease: True
        )
        self._recovery = recovery or (lambda _worker, _generation, _deadline: True)
        self._replace_resources = replace_resources or _required("replace_resources")
        self._monotonic = monotonic
        self._physical_started = False
        self._captured: list[Path] = []
        self._used_session_ids = {resources.session_id}
        self._batch_id: str | None = None
        self._reset_boundaries: dict[tuple[object, ...], float] = {}
        self._numeric_receipts: dict[
            tuple[object, ...], NumericEvidenceReceipt
        ] = {}
        self._inference_receipts: dict[
            tuple[object, ...], InferenceSnapshotReceipt
        ] = {}
        self._accepted_poses: dict[tuple[object, ...], Any] = {}
        self._published_pose_keys: set[tuple[object, ...]] = set()

    @property
    def owned_process_manifest(self) -> OwnedProcessManifest:
        return self._processes.manifest

    @property
    def captured_artifacts(self) -> tuple[Path, ...]:
        return tuple(self._captured)

    def start_physical_runtime(self) -> None:
        if self._physical_started:
            raise RuntimeError("parallel Worker physical runtime already started")
        config = headless_task_station_config(self.resources)
        for spec in config.processes:
            self._processes.start(spec, environment=self.resources.environment)
        self._physical_started = True

    def worker_ready_gate(self) -> bool:
        return self._physical_started and self._ready_probe(_READY_REQUIREMENTS) is True

    @staticmethod
    def _lease_value(lease: Any, name: str) -> Any:
        value = getattr(lease, name, None)
        if name in {"batch_id", "worker_id", "point_id", "attempt_id"}:
            if not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None:
                raise RuntimeError(f"lease {name} is not a canonical identity")
        elif isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise RuntimeError(f"lease {name} is not a canonical identity")
        return value

    def _lease_key(self, lease: Any) -> tuple[object, ...]:
        key = tuple(
            self._lease_value(lease, name)
            for name in (
                "batch_id",
                "coordinator_epoch",
                "worker_id",
                "worker_generation",
                "point_id",
                "attempt_id",
                "lease_generation",
            )
        )
        if key[2] != self.resources.worker_id or key[3] != self.resources.generation:
            raise RuntimeError("lease identity does not own this Worker root")
        if self._batch_id is None:
            self._batch_id = str(key[0])
        elif key[0] != self._batch_id:
            raise RuntimeError("lease batch identity does not own this Worker root")
        return key

    def _assert_safe_path(self, path: Path) -> None:
        root = self.resources.worker_root.absolute()
        target = Path(path).absolute()
        try:
            relative = target.relative_to(root)
        except ValueError as error:
            raise RuntimeError("artifact path escaped the Worker root") from error
        current = root
        if current.is_symlink():
            raise RuntimeError("artifact path contains a symlink")
        for part in relative.parts:
            current = current / part
            if current.is_symlink():
                raise RuntimeError("artifact path contains a symlink")

    def _point_root(self, lease: Any) -> tuple[tuple[object, ...], Path]:
        key = self._lease_key(lease)
        collection = "attempts" if self.run_mode is RunMode.EXECUTE else "validations"
        root = (
            self.resources.worker_root
            / collection
            / str(key[4])
            / str(key[5])
            / "working"
        )
        self._assert_safe_path(root)
        return key, root

    def _validate_regular_receipt_path(
        self, actual: Path, expected: Path, *, label: str
    ) -> Path:
        actual = Path(actual)
        if actual != expected:
            raise RuntimeError(f"{label} receipt escaped its canonical point identity")
        self._assert_safe_path(actual)
        if actual.is_symlink() or not actual.is_file():
            raise RuntimeError(f"{label} receipt is not a regular artifact")
        return actual

    def _capture_fresh_rgb(
        self, lease: Any, name: str, boundary: float
    ) -> SourceStampedCapture:
        boundary = _finite_timestamp("capture boundary", boundary)
        _key, point_root = self._point_root(lease)
        path = point_root / name
        self._assert_safe_path(path)
        if path.exists() or path.is_symlink():
            raise RuntimeError(f"{name} capture would overwrite point evidence")
        captured = self._capture_rgb(path, boundary)
        if type(captured) is not SourceStampedCapture:
            raise RuntimeError(f"{name} capture lacks a source-stamped receipt")
        self._validate_regular_receipt_path(captured.path, path, label=name)
        if captured.source_stamp_monotonic_s <= boundary:
            raise RuntimeError(f"{name} source stamp is not newer than boundary")
        self._captured.append(path)
        return captured

    def _capture_inference_rgb(
        self, lease: Any, boundary: float
    ) -> InferenceSnapshotReceipt:
        boundary = _finite_timestamp("capture boundary", boundary)
        key, point_root = self._point_root(lease)
        path = point_root / "perception/input/rgb.npy"
        self._assert_safe_path(path)
        if path.exists() or path.is_symlink():
            raise RuntimeError("inference RGB would overwrite point evidence")
        captured = self._capture_rgb(path, boundary)
        if type(captured) is not InferenceSnapshotReceipt:
            raise RuntimeError("inference RGB lacks an immutable snapshot receipt")
        self._validate_regular_receipt_path(
            captured.path, path, label="inference RGB"
        )
        info = path.stat()
        if stat.S_IMODE(info.st_mode) != 0o400 or info.st_uid != os.getuid():
            raise RuntimeError("inference RGB is not immutable and Worker-owned")
        if captured.source_stamp_monotonic_s <= boundary:
            raise RuntimeError("inference RGB source stamp is not newer than boundary")
        payload = path.read_bytes()
        if hashlib.sha256(payload).hexdigest() != captured.input_sha256:
            raise RuntimeError("inference RGB hash does not match its receipt")
        try:
            rgb = np.load(io.BytesIO(payload), allow_pickle=False)
        except (OSError, ValueError) as error:
            raise RuntimeError("inference RGB is not canonical NPY") from error
        if (
            rgb.dtype != np.uint8
            or tuple(rgb.shape) != captured.shape
            or rgb.ndim != 3
            or rgb.shape[2] != 3
        ):
            raise RuntimeError("inference RGB shape or dtype does not match its receipt")
        self._captured.append(path)
        self._inference_receipts[key] = captured
        return captured

    def _capture_numeric(
        self, lease: Any, localized: Any, boundary: float
    ) -> NumericEvidenceReceipt:
        key, point_root = self._point_root(lease)
        numeric_root = point_root / "numeric"
        self._assert_safe_path(numeric_root)
        if any(
            (numeric_root / name).exists()
            for name in ("depth.json", "tf.json", "physical.json")
        ):
            raise RuntimeError("numeric evidence would overwrite point evidence")
        receipt = self._capture_numeric_evidence(
            lease, localized, numeric_root, boundary
        )
        if type(receipt) is not NumericEvidenceReceipt:
            raise RuntimeError("numeric evidence lacks a strict source-stamped receipt")
        expected = (
            numeric_root / "depth.json",
            numeric_root / "tf.json",
            numeric_root / "physical.json",
        )
        for actual, path, label in zip(
            (receipt.depth_path, receipt.tf_path, receipt.physical_path),
            expected,
            ("depth", "TF", "physical"),
        ):
            self._validate_regular_receipt_path(actual, path, label=label)
        if receipt.source_stamp_monotonic_s <= boundary:
            raise RuntimeError(
                "numeric evidence source stamp is not newer than reset boundary"
            )
        self._numeric_receipts[key] = receipt
        return receipt

    def reset_point(self, lease: Any):
        if not self._physical_started:
            raise RuntimeError("parallel Worker physical runtime is not started")
        key, _point_root = self._point_root(lease)
        if key in self._reset_boundaries:
            raise RuntimeError("point reset evidence already exists")
        receipt = self._reset_point(lease)
        boundary = getattr(receipt, "reset_completed_monotonic_s", None)
        try:
            boundary = _finite_timestamp("reset boundary", boundary)
        except ValueError as error:
            raise RuntimeError("reset receipt lacks a source-frame boundary") from error
        if self._reserve_workspace(lease, receipt) is not True:
            raise RuntimeError("point workspace was not durably reserved")
        self._capture_fresh_rgb(lease, "initial-rgb.png", boundary)
        self._reset_boundaries[key] = boundary
        return receipt

    def inference_snapshot(self, lease: Any) -> InferenceSnapshotReceipt:
        """Return only the post-reset snapshot bound to this exact lease."""

        key = self._lease_key(lease)
        try:
            receipt = self._inference_receipts[key]
        except KeyError as error:
            raise RuntimeError("lease identity has no inference snapshot") from error
        if (
            not receipt.path.is_file()
            or receipt.path.is_symlink()
            or stat.S_IMODE(receipt.path.stat().st_mode) != 0o400
            or hashlib.sha256(receipt.path.read_bytes()).hexdigest()
            != receipt.input_sha256
        ):
            raise RuntimeError("inference snapshot identity changed")
        return receipt

    def point_initial_gate(self, lease: Any, reset_receipt: Any):
        gate = self._initial_gate(lease, reset_receipt)
        key = self._lease_key(lease)
        try:
            boundary = self._reset_boundaries[key]
        except KeyError as error:
            raise RuntimeError("point gate lacks a reset boundary") from error
        self._capture_inference_rgb(lease, boundary)
        return gate

    def reset_and_validate_point(self, lease: Any):
        receipt = self.reset_point(lease)
        return receipt, self.point_initial_gate(lease, receipt)

    def localize_and_admit_pose(self, lease: Any, broker_result: Any):
        key = self._lease_key(lease)
        try:
            boundary = self._reset_boundaries[key]
        except KeyError as error:
            raise RuntimeError("point localization lacks a reset boundary") from error
        if key in self._accepted_poses:
            raise RuntimeError("point pose was already admitted")
        if getattr(broker_result, "perception_chain_complete", False) is True:
            if getattr(broker_result, "perception_terminal", False) is True:
                return broker_result
            localized = getattr(broker_result, "localized", None)
            numeric = self._capture_numeric(lease, localized, boundary)
            self._accepted_poses[key] = broker_result
            self._numeric_receipts[key] = numeric
            if self.run_mode is RunMode.PLAN_ONLY:
                if self._publish_pose(broker_result) is False:
                    raise RuntimeError("POSE_ACCEPTED_PUBLICATION_FAILED")
                self._published_pose_keys.add(key)
            return broker_result
        localized = self._localize(lease, broker_result)
        numeric = self._capture_numeric(lease, localized, boundary)
        admitted = self._admit_pose(lease, localized)
        if admitted is None or admitted is False:
            raise RuntimeError("POSE_ADMISSION_REJECTED")
        self._accepted_poses[key] = admitted
        self._numeric_receipts[key] = numeric
        if self.run_mode is RunMode.PLAN_ONLY:
            published = self._publish_pose(admitted)
            if published is False:
                raise RuntimeError("POSE_ACCEPTED_PUBLICATION_FAILED")
            self._published_pose_keys.add(key)
        return admitted

    def admit_pose(self, lease: Any, broker_result: Any):
        return self.localize_and_admit_pose(lease, broker_result)

    def plan_expert(self, lease: Any, admitted: Any):
        if self.run_mode is not RunMode.PLAN_ONLY:
            raise RuntimeError("expert planning requires plan_only")
        if getattr(admitted, "perception_terminal", False) is True:
            status = (
                ValidationStatus.VALIDATION_FAILED
                if getattr(admitted, "disposition", None) == "FAILED"
                else ValidationStatus.VALIDATION_INVALID
            )
            return RuntimeDecision(status, getattr(admitted, "reason", None))
        key = self._lease_key(lease)
        if (
            self._accepted_poses.get(key) is not admitted
            or key not in self._published_pose_keys
        ):
            raise RuntimeError("expert planning requires the admitted published pose")
        prefix = self._plan_prefix(lease, admitted, DYNAMIC_REACHABILITY_STATES)
        if type(prefix) is not PlanPrefixReceipt:
            raise RuntimeError("expert planning lacks complete segment receipts")
        if prefix.completion_monotonic_s <= self._reset_boundaries[key]:
            raise RuntimeError("plan completion is not newer than the reset boundary")
        terminal = self.capture_terminal(
            lease, action_boundary_monotonic_s=prefix.completion_monotonic_s
        )
        return RuntimeDecision(
            ValidationStatus.VALIDATION_PASSED,
            segment_receipts=prefix.segments,
            numeric_evidence=self._numeric_receipts[key],
            terminal_artifacts=terminal,
            completion_monotonic_s=prefix.completion_monotonic_s,
        )

    def consumer_argv(
        self, reset_epoch: object, lease: Any | None = None
    ) -> tuple[str, ...] | None:
        if self.run_mode is not RunMode.EXECUTE:
            return None
        if lease is None:
            raise RuntimeError("execute consumer command requires a lease identity")
        _key, point_root = self._point_root(lease)
        return tuple(
            ros2_command(
                "run",
                "so101_demo_py",
                "dynamic_cup_pick_place",
                "--backend",
                "mujoco",
                "--mode",
                "execute",
                "--execute",
                "--expected-reset-epoch",
                str(reset_epoch),
                "--session-id",
                self.resources.session_id,
                "--evidence-root",
                str(point_root / "dynamic"),
                "--scene-source",
                "observe_only",
            )
        )

    def execute_expert(self, lease: Any, admitted: Any):
        if self.run_mode is not RunMode.EXECUTE:
            raise RuntimeError("expert execution requires execute")
        if getattr(admitted, "perception_terminal", False) is True:
            status = (
                AttemptStatus.FAILED
                if getattr(admitted, "disposition", None) == "FAILED"
                else AttemptStatus.INVALID
            )
            return RuntimeDecision(
                status,
                getattr(admitted, "reason", None),
                physical_action_proven_absent=True,
            )
        reset_epoch = getattr(admitted, "reset_epoch", None)
        if reset_epoch is None:
            raise RuntimeError("accepted pose lacks reset epoch")
        key = self._lease_key(lease)
        if self._accepted_poses.get(key) is not admitted:
            raise RuntimeError("expert execution requires the admitted pose")
        if key in self._published_pose_keys:
            raise RuntimeError("accepted pose was published before consumer readiness")
        argv = self.consumer_argv(reset_epoch, lease)
        if argv is None:
            raise RuntimeError("execute consumer command is unavailable")
        child = self._processes.start(
            StackProcessSpec("dynamic-consumer", argv),
            environment=self.resources.environment,
        )
        if self._consumer_ready(child) is not True:
            raise RuntimeError("dynamic consumer subscription is not ready")
        if self._publish_pose(admitted) is False:
            raise RuntimeError("POSE_ACCEPTED_PUBLICATION_FAILED")
        self._published_pose_keys.add(key)
        receipt = self._execute_result(lease, admitted, child)
        if type(receipt) is not ExecutionCompletionReceipt:
            raise RuntimeError("execute result lacks an authoritative completion receipt")
        decision = receipt.decision
        if receipt.completion_monotonic_s <= self._reset_boundaries[key]:
            raise RuntimeError("execution completion is not newer than the reset boundary")
        terminal = self.capture_terminal(
            lease,
            action_boundary_monotonic_s=receipt.completion_monotonic_s,
        )
        return replace(
            decision,
            numeric_evidence=self._numeric_receipts[key],
            terminal_artifacts=terminal,
            completion_monotonic_s=receipt.completion_monotonic_s,
        )

    def capture_terminal(
        self,
        lease: Any,
        *,
        action_boundary_monotonic_s: float,
    ) -> tuple[Path, ...]:
        try:
            boundary = _finite_timestamp(
                "terminal capture boundary", action_boundary_monotonic_s
            )
        except ValueError as error:
            raise RuntimeError("terminal capture boundary is required") from error
        capture = self._capture_fresh_rgb(lease, "terminal-rgb.png", boundary)
        return (capture.path,)

    def cancel_motion(self, lease: Any) -> bool:
        return self._cancel_motion(lease) is True

    def confirm_no_controller_goal(self, lease: Any) -> bool:
        return self._confirm_no_controller_goal(lease) is True

    def _valid_replacement(
        self, replacement: object, *, expected_generation: int
    ) -> bool:
        if type(replacement) is not WorkerResources:
            return False
        current = self.resources
        if replacement.generation != expected_generation + 1:
            return False
        invariant_fields = (
            "worker_id",
            "slot_index",
            "ros_domain_id",
            "simulation_port",
            "bridge_port",
            "gz_partition",
            "controller_namespace",
            "render_backend",
            "render_context_id",
            "render_context_namespace",
            "virtual_display",
            "ros_home",
            "ros_log_dir",
            "temp_dir",
            "socket_namespace",
            "socket_path",
            "worker_root",
        )
        if any(
            getattr(replacement, name) != getattr(current, name)
            for name in invariant_fields
        ):
            return False
        if (
            not isinstance(replacement.session_id, str)
            or not replacement.session_id
            or replacement.session_id in self._used_session_ids
        ):
            return False
        expected_environment = dict(current.environment)
        expected_environment["SO101_WORKER_GENERATION"] = str(
            replacement.generation
        )
        expected_environment["SO101_SESSION_ID"] = replacement.session_id
        return dict(replacement.environment) == expected_environment

    def recover(self, worker_id: str, generation: int, deadline_monotonic_s: float) -> bool:
        if (
            not isinstance(worker_id, str)
            or worker_id != self.resources.worker_id
            or type(generation) is not int
            or generation != self.resources.generation
        ):
            return False
        try:
            deadline = _finite_timestamp("recovery deadline", deadline_monotonic_s)
        except ValueError:
            return False
        if self._monotonic() >= deadline:
            return False
        self.shutdown_owned()
        if self._monotonic() >= deadline:
            return False
        recovered = self._recovery(worker_id, generation, deadline) is True
        if not recovered or self._monotonic() >= deadline:
            return False
        try:
            replacement = self._replace_resources(
                worker_id, expected_generation=generation
            )
        except Exception:
            return False
        if self._monotonic() >= deadline:
            return False
        if not self._valid_replacement(
            replacement, expected_generation=generation
        ):
            return False
        if self._monotonic() >= deadline:
            return False
        self.resources = replacement
        self._used_session_ids.add(replacement.session_id)
        if self._monotonic() >= deadline:
            return False
        try:
            self.start_physical_runtime()
        except Exception:
            return False
        if self._monotonic() >= deadline:
            try:
                self.shutdown_owned()
            except Exception:
                pass
            return False
        return True

    def shutdown_owned(self) -> None:
        try:
            self._processes.shutdown()
        finally:
            self._physical_started = False


def build_worker_runtime(
    resources: WorkerResources,
    run_mode: RunMode,
    **ports,
) -> DryRunWorkerRuntime | ParallelWorkerRuntime:
    """Select scheduler-only or physical runtime without constructing side effects."""

    if not isinstance(run_mode, RunMode):
        raise TypeError("run_mode must be a RunMode")
    if run_mode is RunMode.DRY_RUN:
        return DryRunWorkerRuntime(resources)
    return ParallelWorkerRuntime(resources, run_mode, **ports)
