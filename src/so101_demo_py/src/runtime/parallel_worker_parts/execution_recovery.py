"""Expert execution, terminal capture, revocation, recovery and shutdown."""

from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import threading
import time
from typing import Any

from so101_demo.parallel_batch.contracts.common import AttemptStatus, RunMode
from so101_demo.parallel_batch.resource_allocation.models import WorkerResources
from so101_demo.runtime.parallel_worker_parts.process_tree import _finite_timestamp
from so101_demo.runtime.parallel_worker_parts.receipts import (
    ExecutionCompletionReceipt,
    RuntimeDecision,
)


class ExecutionRecovery:
    def execute_expert(self, lease: Any, admitted: Any):
        self._execution_allowed()
        if self.run_mode is not RunMode.EXECUTE:
            raise RuntimeError("expert execution requires execute")
        key = self._lease_key(lease)
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
        if self._accepted_poses.get(key) is not admitted:
            raise RuntimeError("expert execution requires the admitted pose")
        if key in self._published_pose_keys:
            raise RuntimeError("accepted pose was published before consumer readiness")
        try:
            child = self._execute_consumers[key]
        except KeyError as error:
            raise RuntimeError("execute consumer was not ready before inference") from error
        if self._publish_pose(admitted) is False:
            raise RuntimeError("POSE_ACCEPTED_PUBLICATION_FAILED")
        self._published_pose_keys.add(key)
        receipt = self._execute_result(lease, admitted, child)
        if type(receipt) is not ExecutionCompletionReceipt:
            raise RuntimeError("execute result lacks an authoritative completion receipt")
        teacher_stopped = True
        if receipt.teacher_child_exited:
            self._teacher_has_exited()
        else:
            # The wait gave up with the Teacher child alive. It is stopped first, by the same path the Teacher-deadline
            # revocation uses (`cancel_motion`: the consumer child and the controller goal); only then is the window closed. If it cannot be
            # stopped the window and its deadline guard stay open, and no data work runs.
            try:
                teacher_stopped = self.cancel_motion(lease) is True
            except Exception:   # noqa: BLE001
                teacher_stopped = False
            if teacher_stopped:
                self._teacher_has_exited()
        decision = receipt.decision
        if not receipt.teacher_child_exited:
            decision = replace(decision, act_data_status="INVALID",
                               act_data_reason="TEACHER_CHILD_TIMED_OUT" if teacher_stopped else "TEACHER_CHILD_NOT_STOPPED")
        if receipt.completion_monotonic_s <= self._reset_boundaries[key]:
            raise RuntimeError("execution completion is not newer than the reset boundary")
        try:
            terminal = self.capture_terminal(
                lease,
                action_boundary_monotonic_s=receipt.completion_monotonic_s,
            )
        except Exception as error:
            # Terminal capture and the episode seal are data work. The Teacher has already finished and its result
            # is the manifest's: a failure here makes the data INVALID and never changes that result.
            terminal = ()
            decision = replace(
                decision, act_data_status="INVALID",
                act_data_reason=("TERMINAL_CAPTURE_FAILED: " + (str(error) or type(error).__name__))[:300])
        decision = self._finish_collection(lease, decision)
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
        # the episode ends here: the boundary the caller passes is the run's own end instant, and the window
        # the capture needs is built from the instant it started at. Sealing goes through the sink because the
        # outcome belongs to whoever knows the run's decision - a recorder that invented one would make the
        # episode's own status worthless.
        _sink = getattr(self, "episode_sink", None)
        if _sink is not None and _sink.current is not None:
            _sink.finish(boundary)
        return (capture.path,)

    def cancel_motion(self, lease: Any) -> bool:
        key = self._lease_key(lease)
        active = self._active_lease
        if active is None or self._lease_key(active) != key:
            return False
        child = self._execute_consumers.get(key)
        consumer_stopped = True
        stop_thread = None
        if child is not None:
            consumer_stopped = False

            def stop_consumer():
                nonlocal consumer_stopped
                try:
                    consumer_stopped = self._processes.stop(child) is not False
                except Exception:
                    consumer_stopped = False

            stop_thread = threading.Thread(
                target=stop_consumer,
                name=f"parallel-consumer-stop-{self.resources.worker_id}",
                daemon=True,
            )
            stop_thread.start()
        controller_stopped = self._cancel_motion(lease) is True
        if stop_thread is not None:
            stop_thread.join()
            if consumer_stopped:
                self._execute_consumers.pop(key, None)
        self._retire_recorder(key)
        return consumer_stopped and controller_stopped

    def record_revocation(
        self,
        lease: Any,
        phase: str,
        *,
        recorded_wall_time_ns: int | None = None,
        recorded_monotonic_ns: int | None = None,
        **details: object,
    ) -> bool:
        """Append one durable, exact-lease revocation phase receipt."""
        if phase not in {
            "WATCHDOG_REVOKED", "CANCEL_REQUESTED",
            "CONTROLLER_CANCEL_RESULT", "CANCEL_RESULT",
        }:
            raise ValueError("revocation phase is not canonical")
        key = self._lease_key(lease)
        if key != self._lease_key(self._active_lease):
            raise RuntimeError("revocation receipt lease is not active")
        identity = {
            "batch_id": lease.batch_id,
            "coordinator_epoch": lease.coordinator_epoch,
            "worker_id": lease.worker_id,
            "worker_generation": lease.worker_generation,
            "point_id": lease.point_id,
            "attempt_id": lease.attempt_id,
            "lease_generation": lease.lease_generation,
        }
        if any(type(value) is not bool for value in details.values()
               if phase in {"CONTROLLER_CANCEL_RESULT", "CANCEL_RESULT"}):
            raise ValueError("cancel result details must be boolean")
        if phase == "WATCHDOG_REVOKED" and (
            set(details) != {"reason"}
            or not isinstance(details["reason"], str)
            or not details["reason"]
        ):
            raise ValueError("watchdog revocation reason is required")
        if phase == "CANCEL_REQUESTED" and details:
            raise ValueError("cancel request details are not canonical")
        if phase == "CONTROLLER_CANCEL_RESULT" and set(details) != {
            "motion_stopped", "controllers_confirmed"
        }:
            raise ValueError("controller cancel result details are incomplete")
        if phase == "CANCEL_RESULT" and set(details) != {
            "broker_fenced", "motion_stopped", "controllers_confirmed"
        }:
            raise ValueError("cancel result details are incomplete")
        if recorded_wall_time_ns is None:
            recorded_wall_time_ns = time.time_ns()
        if recorded_monotonic_ns is None:
            recorded_monotonic_ns = time.monotonic_ns()
        if (
            type(recorded_wall_time_ns) is not int
            or recorded_wall_time_ns <= 0
            or type(recorded_monotonic_ns) is not int
            or recorded_monotonic_ns <= 0
        ):
            raise ValueError("revocation event timestamps are invalid")
        receipt = {
            "schema_version": 1,
            "kind": "SO101_PARALLEL_REVOCATION_EVENT",
            "phase": phase,
            "wall_time_ns": recorded_wall_time_ns,
            "monotonic_ns": recorded_monotonic_ns,
            **identity,
            **details,
        }
        payload = (json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n").encode()
        path = self.resources.worker_root / "revocation-events.jsonl"
        with self._revocation_receipt_lock:
            descriptor = os.open(
                path,
                os.O_APPEND | os.O_CREAT | os.O_CLOEXEC | os.O_WRONLY,
                0o600,
            )
            try:
                if os.write(descriptor, payload) != len(payload):
                    raise OSError("short revocation receipt write")
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        return True

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
        if self._rebind_resources(replacement) is not True:
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
            self._close_runtime()
        finally:
            try:
                self._processes.shutdown()
            finally:
                self._physical_started = False

    def shutdown_control(self, operation: str, *, deadline_monotonic_s: float) -> bool:
        """Perform one exact parent-requested shutdown action inside this Worker."""
        if operation == "stop":
            self._stop_requested.set()
            return True
        lease = self._active_lease
        if operation == "cancel_motion":
            return lease is None or self.cancel_motion(lease)
        if operation == "confirm_no_controller_goal":
            return lease is None or self.confirm_no_controller_goal(lease)
        if operation == "recover":
            if self._monotonic() >= deadline_monotonic_s:
                return False
            self.shutdown_owned()
            if self._monotonic() >= deadline_monotonic_s:
                return False
            return self._recovery(
                self.resources.worker_id,
                self.resources.generation,
                deadline_monotonic_s,
            ) is True
        raise RuntimeError("unknown Worker shutdown operation")
