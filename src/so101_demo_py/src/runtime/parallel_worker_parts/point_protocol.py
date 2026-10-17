"""The point protocol: reset, acknowledgements, the initial gate, pose admission and planning."""

from __future__ import annotations

import hashlib
import stat
import sys
from typing import Any

from so101_demo.core.dynamic_pick import DYNAMIC_REACHABILITY_STATES
from so101_demo.parallel_batch.contracts.common import RunMode, ValidationStatus
from so101_demo.runtime.parallel_worker_parts.process_tree import _finite_timestamp
from so101_demo.runtime.parallel_worker_parts.receipts import (
    InferenceSnapshotReceipt,
    PlanPrefixReceipt,
    RuntimeDecision,
)
from so101_demo.runtime.task_stack import (
    StackProcessSpec,
)


class PointProtocol:
    def reset_point(self, lease: Any):
        self._execution_allowed()
        if not self._physical_started:
            raise RuntimeError("parallel Worker physical runtime is not started")
        key, _point_root = self._point_root(lease)
        if key in self._reset_boundaries:
            raise RuntimeError("point reset evidence already exists")
        self._active_lease = lease
        self._physics_held.add(key)   # the reset leaves physics paused until the point gate resumes it, even if it faults
        receipt = self._reset_point(lease)
        boundary = getattr(receipt, "reset_completed_monotonic_s", None)
        try:
            boundary = _finite_timestamp("reset boundary", boundary)
        except ValueError as error:
            raise RuntimeError("reset receipt lacks a source-frame boundary") from error
        if self._reserve_workspace(lease, receipt) is not True:
            raise RuntimeError("point workspace was not durably reserved")
        self._reset_boundaries[key] = boundary
        self._reset_receipts[key] = receipt
        return receipt

    def initializing_acknowledged(self,lease):
        if self._initializing_acknowledged is not None:
            self._execution_allowed()
            if not self._physical_started:
                raise RuntimeError("teacher initializing ACK requires the existing physical station")
            self._initializing_acknowledged(lease)

    def heartbeat_acknowledged(self,lease):
        if self._heartbeat_acknowledged is not None:
            self._execution_allowed()
            if not self._physical_started:
                raise RuntimeError("teacher heartbeat ACK requires the existing physical station")
            self._heartbeat_acknowledged(lease)

    def attempt_started_acknowledged(self,lease):
        if self._attempt_started_acknowledged is not None:
            self._execution_allowed()
            key=self._lease_key(lease)
            if (self.run_mode is not RunMode.EXECUTE or not self._physical_started
                    or key not in self._reset_receipts or key not in self._paused_for_inference
                    or key in self._started_leases):
                raise RuntimeError("teacher start ACK requires the original paused point gate")
            self._attempt_started_acknowledged(lease)
            self._execution_allowed()
            self._started_leases[key]=lease

    def finalizing_acknowledged(self,lease):
        if self._finalizing_acknowledged is not None:
            self._execution_allowed()
            if self.run_mode is not RunMode.EXECUTE or not self._physical_started:
                raise RuntimeError("teacher finalizing ACK requires the existing physical station")
            self._finalizing_acknowledged(lease)
            self._execution_allowed()

    def inference_snapshot(self, lease: Any) -> InferenceSnapshotReceipt:
        """Return only the post-reset snapshot bound to this exact lease."""

        self._execution_allowed()
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
        self._execution_allowed()
        gate = self._initial_gate(lease, reset_receipt)
        key = self._lease_key(lease)
        try:
            boundary = self._reset_boundaries[key]
        except KeyError as error:
            raise RuntimeError("point gate lacks a reset boundary") from error
        if self._resume_physics(lease, reset_receipt) is not True:
            raise RuntimeError("qualified point boundary did not resume simulation")
        self._physics_held.discard(key)
        initial = self._capture_fresh_rgb(lease, "initial-rgb.png", boundary)
        simulation_time = getattr(reset_receipt, "simulation_time_s", None)
        if simulation_time is not None and (
            isinstance(simulation_time, bool)
            or not isinstance(simulation_time, (int, float))
            or type(initial.source_stamp_ns) is not int
            or initial.source_stamp_ns / 1_000_000_000.0 <= float(simulation_time)
        ):
            raise RuntimeError(
                "initial camera frame is not newer than reset simulation watermark"
            )
        if self.run_mode is RunMode.EXECUTE:
            # The Recorder starts first and is waited for a bounded time; the Teacher starts whatever happened to it.
            self._start_recorder_first(lease, reset_receipt)
            self._start_execute_consumer(lease)
            self._recorder_teacher_started(lease)
        inference = self._capture_inference_rgb(lease, boundary)
        reset_session = getattr(reset_receipt, "simulation_session_id", None)
        if simulation_time is not None and (
            inference.source_clock != "ros_sim"
            or inference.source_stamp_ns / 1_000_000_000.0 <= float(simulation_time)
        ):
            raise RuntimeError(
                "inference RGB is not newer than reset simulation watermark"
            )
        if reset_session is not None and inference.simulation_session_id != reset_session:
            raise RuntimeError("inference RGB simulation session mismatch")
        if self.run_mode is RunMode.EXECUTE:
            if self._pause_physics(lease, reset_receipt) is not True:
                raise RuntimeError("inference snapshot could not freeze simulation")
            self._paused_for_inference.add(key)
            self._physics_held.add(key)
        return gate

        # the episode begins here: whoever holds the frozen inputs and the episode's own root opens it, and
        # the reset boundary this gate was given is the instant it starts at. Optional by design, so a runtime without
        # the port keeps working exactly as before.
        if self._open_episode is not None:
            episode = self._open_episode(lease)
            if episode is not None:
                episode.start(boundary)
                self._episode_state[key] = episode

    def release_physics_hold(self, lease: Any) -> bool:
        """Resume the simulation if this lease's reset or inference freeze still holds it paused.

        The point gate and pose localization resume it on the way forward. A fault before either leaves it frozen, and a
        frozen simulation cannot be observed stopped: its physics does not advance and its camera and joint samples go stale.
        True when nothing is held or the resume was accepted; the hold stays recorded when it was not."""
        key = self._lease_key(lease)
        if key not in self._physics_held:
            return True
        receipt = self._reset_receipts.get(key)   # None when the reset faulted before it produced one
        if self._resume_physics(lease, receipt) is not True:
            return False
        self._physics_held.discard(key)
        self._paused_for_inference.discard(key)
        return True

    def reset_and_validate_point(self, lease: Any):
        receipt = self.reset_point(lease)
        return receipt, self.point_initial_gate(lease, receipt)

    def _start_execute_consumer(self,lease):
        self._execution_allowed()
        key=self._lease_key(lease)
        if key in self._execute_consumers:
            raise RuntimeError("execute consumer was already started")
        reset=self._reset_receipts[key]
        argv=self.consumer_argv(getattr(reset,"reset_epoch",None),lease)
        if argv is None:
            raise RuntimeError("execute consumer command is unavailable")
        environment=dict(self.resources.environment)
        self._execution_allowed()
        child=self._processes.start(StackProcessSpec("dynamic-consumer",argv),environment=environment)
        if self._consumer_ready(child) is not True:
            raise RuntimeError("dynamic consumer subscription is not ready")
        self._execution_allowed()
        self._execute_consumers[key]=child

    def localize_and_admit_pose(self, lease: Any, broker_result: Any):
        self._execution_allowed()
        key = self._lease_key(lease)
        try:
            boundary = self._reset_boundaries[key]
        except KeyError as error:
            raise RuntimeError("point localization lacks a reset boundary") from error
        if key in self._accepted_poses:
            raise RuntimeError("point pose was already admitted")
        if self.run_mode is RunMode.EXECUTE and key in self._paused_for_inference:
            if self._resume_physics(lease, self._reset_receipts[key]) is not True:
                raise RuntimeError("inference hold could not resume simulation")
            self._paused_for_inference.remove(key)
            self._physics_held.discard(key)
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
        self._execution_allowed()
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
        argv = tuple(
            (
                sys.executable,
                "-m",
                "so101_demo.cli.dynamic_cup_pick_place",
                "--backend",
                "mujoco",
                "--mode",
                "execute",
                "--execute",
                "--expected-reset-epoch",
                str(self._reset_epoch_integer(reset_epoch)),
                "--cup-pose-timeout-s",
                str(self._pose_receive_timeout_s),
                "--session-id",
                self.resources.session_id,
                "--batch-id",
                lease.batch_id,
                "--coordinator-epoch",
                str(lease.coordinator_epoch),
                "--worker-id",
                lease.worker_id,
                "--worker-generation",
                str(lease.worker_generation),
                "--point-id",
                lease.point_id,
                "--attempt-id",
                lease.attempt_id,
                "--lease-generation",
                str(lease.lease_generation),
                "--lease-issued-monotonic-s",
                str(lease.lease_issued_monotonic_s),
                "--lease-deadline-monotonic-s",
                str(lease.lease_deadline_monotonic_s),
                "--evidence-root",
                str(point_root / "dynamic"),
                "--ready-receipt",
                str(point_root / "dynamic" / "consumer-ready.json"),
                "--scene-source",
                "observe_only",
            )
        )
        if self.episode_inputs_manifest is not None:
            # the Teacher loads its snapshot and policies from the frozen set and refuses a mismatch before motion
            argv = argv + ("--frozen-inputs-manifest", self.episode_inputs_manifest)
        if self._collection is not None and self._collection.enabled:
            # the only Teacher-side difference collection makes: the confirmed final normal-stop proof
            argv = argv + ("--final-stop-proof",)
        if self._collection is not None and getattr(self._collection, "inject_failure_at", None) is not None:
            # Diagnostic only (validated when the request was made): the Teacher injects one execution failure there
            argv = argv + ("--inject-failure-at", self._collection.inject_failure_at)
        return argv
