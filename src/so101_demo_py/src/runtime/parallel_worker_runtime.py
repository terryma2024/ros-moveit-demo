"""Isolated, injectable runtime boundary for one parallel MuJoCo Worker."""

from __future__ import annotations

import math
from pathlib import Path
import threading
import time
from typing import Any, Callable

from so101_demo.core.domain import State
from so101_demo.parallel_batch.contracts.common import RunMode, ValidationStatus
from so101_demo.parallel_batch.resource_allocation.models import WorkerResources
from so101_demo.runtime.parallel_worker_parts.captures import WorkerCaptures
from so101_demo.runtime.parallel_worker_parts.collection import CollectionRecorder
from so101_demo.runtime.parallel_worker_parts.execution_recovery import ExecutionRecovery
from so101_demo.runtime.parallel_worker_parts.point_protocol import PointProtocol
from so101_demo.runtime.parallel_worker_parts.process_tree import (
    _READY_REQUIREMENTS,
    SourceStampedCapture,
    WorkerOwnedProcessTree,
)
from so101_demo.runtime.parallel_worker_parts.receipts import (
    InferenceSnapshotReceipt,
    NumericEvidenceReceipt,
    RuntimeDecision,
)
from so101_demo.runtime.parallel_worker_parts.station import _required, task_station_config
from so101_demo.runtime.task_stack import (
    OwnedProcessManifest,
    PersistentStackConfig,
)


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


class ParallelWorkerRuntime(WorkerCaptures, PointProtocol, CollectionRecorder, ExecutionRecovery):
    """Own one headless station and all lease-scoped Worker operations."""

    def __init__(
        self,
        resources: WorkerResources,
        run_mode: RunMode,
        *,
        process_group: Any | None = None,
        station_config: Callable[[WorkerResources], PersistentStackConfig] | None = None,
        ready_probe: Callable[[tuple[str, ...]], bool] | None = None,
        initializing_acknowledged: Callable[[Any], Any] | None = None,
        heartbeat_acknowledged: Callable[[Any], Any] | None = None,
        attempt_started_acknowledged: Callable[[Any], Any] | None = None,
        finalizing_acknowledged: Callable[[Any], Any] | None = None,
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
        open_episode: Callable[[Any], Any] | None = None,
        episode_scope_path: str | None = None,
        episode_inputs_manifest: str | None = None,
        collection: Any | None = None,
        recorder_policy: dict | None = None,
        recorder_clock: Callable[[], float] = time.monotonic,
        recorder_sleep: Callable[[float], None] = time.sleep,
        capture_numeric_evidence: Callable[
            [Any, Any, Path, float], NumericEvidenceReceipt
        ]
        | None = None,
        cancel_motion: Callable[[Any], bool] | None = None,
        confirm_no_controller_goal: Callable[[Any], bool] | None = None,
        pause_physics: Callable[[Any, Any], bool] | None = None,
        resume_physics: Callable[[Any, Any], bool] | None = None,
        recovery: Callable[[str, int, float], bool] | None = None,
        replace_resources: Callable[..., WorkerResources] | None = None,
        rebind_resources: Callable[[WorkerResources], bool] | None = None,
        close_runtime: Callable[[], None] | None = None,
        pose_receive_timeout_s: float = 240.0,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if not isinstance(resources, WorkerResources):
            raise TypeError("WorkerResources are required")
        if run_mode not in (RunMode.PLAN_ONLY, RunMode.EXECUTE):
            raise ValueError("physical Worker runtime requires plan_only or execute")
        if (
            isinstance(pose_receive_timeout_s, bool)
            or not isinstance(pose_receive_timeout_s, (int, float))
            or not math.isfinite(pose_receive_timeout_s)
            or pose_receive_timeout_s <= 0.0
        ):
            raise ValueError("pose receive timeout must be finite and positive")
        self.resources = resources
        self.run_mode = run_mode
        self._pose_receive_timeout_s = float(pose_receive_timeout_s)
        self._processes = process_group or WorkerOwnedProcessTree(
            manifest_path=resources.worker_root / "owned-runtime-processes.json"
        )
        # The station shape is a platform decision (Linux headless, Darwin visible), so it is a
        # port with a default rather than a hard-coded launch command.
        self._station_config = station_config or task_station_config
        if station_config is None and episode_inputs_manifest is not None:
            # A diagnostic-episode run is the ACT station, chosen by the frozen inputs (never by the ambient environment).
            from dataclasses import replace

            from so101_demo.runtime.act_diagnostic_episode_station import DiagnosticEpisodeStation
            self._station_config = DiagnosticEpisodeStation.bind(episode_inputs_manifest, episode_scope_path)
            self.resources = replace(resources, environment=self._station_config.environment(resources))
        if not callable(self._station_config):
            raise TypeError("station_config must be callable")
        self._ready_probe = ready_probe or _required("ready_probe")
        if initializing_acknowledged is not None and not callable(initializing_acknowledged):
            raise TypeError("initializing ACK hook must be callable")
        self._initializing_acknowledged=initializing_acknowledged
        if heartbeat_acknowledged is not None and not callable(heartbeat_acknowledged):
            raise TypeError("heartbeat ACK hook must be callable")
        self._heartbeat_acknowledged=heartbeat_acknowledged
        if attempt_started_acknowledged is not None and not callable(attempt_started_acknowledged):
            raise TypeError("attempt-started ACK hook must be callable")
        self._attempt_started_acknowledged=attempt_started_acknowledged
        if finalizing_acknowledged is not None and not callable(finalizing_acknowledged):
            raise TypeError("finalizing ACK hook must be callable")
        self._finalizing_acknowledged=finalizing_acknowledged
        self._started_leases={}
        self._reset_point = reset_point or _required("reset_point")
        # Production always supplies the durable reservation owner.  The
        # no-op default preserves the reusable unit-test seam.
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
        # the episode being recorded for a point, opened by whoever holds the frozen inputs and the episode's own root
        # the scope document the parent wrote for this episode, if it wrote one: the consumer it spawns is given
        # this path rather than the frozen values, because a scope assembled from a second reading is how
        # a document and the run it describes drift apart. None means no episode is recorded.
        self.episode_scope_path = None if episode_scope_path is None else str(episode_scope_path)
        self.episode_inputs_manifest = (None if episode_inputs_manifest is None
                                        else str(episode_inputs_manifest))
        # (the CLI, which also knows the scope values and where the audit pair goes). Optional: a runtime that does not
        # record is still a valid runtime, which is why this is not among REQUIRED.
        self._open_episode = open_episode
        # Collection (Phase A4c): `collection` is a CollectionOptions. Enabled, every attempt records a raw bag
        # before its Teacher and is processed offline afterwards, with the bounds frozen in episode_recorder.
        self._collection = collection
        self._recorders: dict[tuple[object, ...], Any] = {}
        #: lease key -> whether the recorder was proven stopped when the attempt was retired (design 2026-10-10 section 1.2)
        self._recorder_stop_proofs: dict[tuple[object, ...], bool] = {}
        self._teacher_exit_callback: Callable[[], None] | None = None
        self._recorder_clock = recorder_clock
        self._recorder_sleep = recorder_sleep
        self._recorder_policy = recorder_policy
        if collection is not None and collection.enabled:
            if episode_inputs_manifest is None or episode_scope_path is None:
                raise TypeError("collection on requires the frozen inputs manifest and the episode scope")
            if self._recorder_policy is None:
                from so101_demo.act.frozen_runtime_inputs import load_recorder_frozen_policy
                self._recorder_policy = load_recorder_frozen_policy(Path(episode_inputs_manifest))
        self._cancel_motion = cancel_motion or (lambda _lease: True)
        self._confirm_no_controller_goal = confirm_no_controller_goal or (
            lambda _lease: True
        )
        self._pause_physics = pause_physics or (lambda _lease, _reset: True)
        self._resume_physics = resume_physics or (lambda _lease, _reset: True)
        self._recovery = recovery or (lambda _worker, _generation, _deadline: True)
        self._replace_resources = replace_resources or _required("replace_resources")
        self._rebind_resources = rebind_resources or (lambda _resources: True)
        self._close_runtime = close_runtime or (lambda: None)
        self._monotonic = monotonic
        self._physical_started = False
        self._captured: list[Path] = []
        self._used_session_ids = {resources.session_id}
        self._batch_id: str | None = None
        self._reset_boundaries: dict[tuple[object, ...], float] = {}
        self._reset_receipts: dict[tuple[object, ...], Any] = {}
        self._numeric_receipts: dict[
            tuple[object, ...], NumericEvidenceReceipt
        ] = {}
        self._inference_receipts: dict[
            tuple[object, ...], InferenceSnapshotReceipt
        ] = {}
        self._accepted_poses: dict[tuple[object, ...], Any] = {}
        # the episode being recorded for a point: the synchronizer the captures are pushed into, the capture built
        # around it, and the coordinates the row audit and the seal need. Kept per lease key like the receipts above,
        # so a point's episode state is created when it starts and cleared when it ends.
        self._episode_state: dict[tuple[object, ...], dict[str, Any]] = {}
        self._published_pose_keys: set[tuple[object, ...]] = set()
        self._execute_consumers: dict[tuple[object, ...], Any] = {}
        self._paused_for_inference: set[tuple[object, ...]] = set()
        self._active_lease: Any | None = None
        self._stop_requested = threading.Event()
        self._revocation_receipt_lock = threading.Lock()

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    def _execution_allowed(self) -> None:
        if self._stop_requested.is_set():
            raise RuntimeError("STOP_REQUESTED")

    @property
    def owned_process_manifest(self) -> OwnedProcessManifest:
        return self._processes.manifest

    @property
    def captured_artifacts(self) -> tuple[Path, ...]:
        return tuple(self._captured)

    def start_physical_runtime(self) -> None:
        if self._physical_started:
            raise RuntimeError("parallel Worker physical runtime already started")
        config = self._station_config(self.resources)
        for spec in config.processes:
            self._processes.start(spec, environment=self.resources.environment)
        self._physical_started = True

    def worker_ready_gate(self) -> bool:
        return self._physical_started and self._ready_probe(_READY_REQUIREMENTS) is True

    def ready_failure(self) -> str | None:
        """Why the last ready probe refused, when its owner recorded a reason (surfaced in the worker result)."""
        owner = getattr(self._ready_probe, "__self__", None)
        message = getattr(owner, "ready_failure_message", None)
        return message if isinstance(message, str) and message else None

    # ---- the data side: a record-only bag during the run, the offline processor after it ------------------


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
