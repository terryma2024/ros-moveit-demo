"""Event stream, process summary and failure evidence of the dynamic execution."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import sys
import time

from so101_demo.core.domain import State
from so101_demo.ros.dynamic_execution.common import (
    _DATA_REASON_MAX_CHARS,
    _STREAM_FLUSH_S,
    _SUMMARY_JOIN_S,
    _spin_burst,
)


class ExecutionEvidence:
    @property
    def evidence_file(self) -> Path:
        return self._evidence_file

    def _write(self) -> None:
        self._evidence_file.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._evidence_file.with_name(f".{self._evidence_file.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(self._document, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temporary, self._evidence_file)

    def _start_event_stream(self, node, session_id, reset_epoch, lease_identity, request_id, *, existing=None) -> None:
        """Use (or create) the ROS publisher and the stream. Any failure leaves the Teacher without a stream, never
        without a run."""
        from so101_demo.act.teacher_event_stream import StreamEventSink

        if existing is not None:
            self._event_stream = existing
            self._event_sink = StreamEventSink(existing)
            return
        from so101_demo.adapters.act.ros_teacher_event_stream import start_teacher_event_stream

        stream, close, error = start_teacher_event_stream(node, session_id, reset_epoch, lease_identity, request_id)
        if stream is None:
            self._event_stream, self._event_stream_error = None, error
            return
        stream.close_publisher = close
        self._event_stream = stream
        self._event_sink = StreamEventSink(stream)

    def _stream_emit(self, event_type, payload) -> None:
        """Offer one Teacher fact to the stream. Never blocks, never raises into control."""
        try:
            stream = getattr(self, "_event_stream", None)
            if stream is not None:
                stream.offer(event_type, payload)
        except Exception:
            pass

    def _stream_manifest_block(self) -> None:
        """Record the drop counter and last published seq in the manifest (best effort, never raises)."""
        try:
            stream = getattr(self, "_event_stream", None)
            if stream is not None:
                self._document["teacher_event_stream"] = stream.snapshot()
        except Exception:
            pass

    def _close_event_stream(self) -> None:
        """Flush the stream (bounded), publish the final counters and release the ROS publisher. Never raises."""
        try:
            stream = getattr(self, "_event_stream", None)
            if stream is None:
                return
            stream.close(flush_timeout_s=_STREAM_FLUSH_S)
            self._stream_manifest_block()
            try:
                self._write()
            except Exception:
                pass
            closer = getattr(stream, "close_publisher", None)
            if callable(closer):
                closer()
        except Exception:
            pass

    def _record_process_diagnostic(self, code: str, state, *, sample=None, facts=None, **details) -> None:
        """Record one audit-only process-quality observation. Never raises into, cancels or fails the state.

        The first occurrence of a code in a state is written with its sample and contacts; repeats only count.
        """

        try:
            key = (code, None if state is None else state.value)
            index = self.__dict__.setdefault("_process_diagnostic_index", {})
            if key in index:
                index[key]["count"] += 1
                return
            entry: dict[str, object] = {
                "code": code, "state": key[1], "audit_only": True, "count": 1,
                "monotonic_s": getattr(self, "_monotonic", time.monotonic)(), **details,
            }
            if facts is not None:
                entry["facts"] = facts
            if sample is not None:
                entry["sample"] = self._evidence(sample)
                entry["contacts"] = {
                    "left": self._contact_documents(sample.left_fingertip_contacts),
                    "right": self._contact_documents(sample.right_fingertip_contacts),
                    "other": self._contact_documents(sample.other_object_contacts),
                }
            index[key] = entry
            self._document.setdefault("process_diagnostics", []).append(entry)
            self._write()
        except Exception as error:
            print(f"DYNAMIC_PROCESS_DIAGNOSTIC_FAILED {code} {error}", file=sys.stderr, flush=True)

    def _publish_final_normal_stop(self) -> None:
        """Publish the confirmed normal-stop proof after the sequence closed, for the Recorder's final boundary.

        Teacher side, after its own sequence: the owner's stop baseline is the one the release preflight already uses.
        A failure is recorded in the manifest and never changes the Teacher result.
        """
        if not self.final_stop_proof_enabled:
            return
        try:
            proof = self._normal_stop_proof()
            self._publish_teacher_event("normal_stop", {"proof": proof})
        except Exception as error:
            self._document["teacher_final_stop_error"] = str(error)[:_DATA_REASON_MAX_CHARS]

    def finish(self, result) -> None:
        # After a stop the flags stay set: the failure evidence, the end observation and the manifest are still taken.
        self._stop_suspended = True
        failure_evidence = None
        done = result.status.value == "DONE"
        if done:
            self._publish_final_normal_stop()
        if not done:
            failure_evidence = self._capture_failure_evidence(result)
        end_observation = end_problem = None
        if done:
            end_observation, end_problem = self._take_teacher_end_observation()
        if self._teacher_run():
            self._document["teacher_process_summary"] = self._build_process_summary(end_observation)
        self._document.update(self._teacher_manifest_fields(result, failure_evidence, end_observation, end_problem))
        self._stream_emit("teacher_end_observation", {
            "observation": copy.deepcopy(end_observation),
            "problem": end_problem})
        self._document.update(
            {
                "status": "DONE" if done else "ERROR",
                "current_state": result.current_state.value,
                "transition_count": result.transition_count,
                "state_trace": [state.value for state in result.state_trace],
                "failure": None if result.failure is None else result.failure.code,
                "release_marker_sequence": self._release_marker_sequence,
                "planning_scene_readback": self._scene_readback,
                "failure_evidence": failure_evidence,
            }
        )
        self._stream_emit("terminal", {
            "status": self._document["status"],
            "teacher_execution_status": self._document["teacher_execution_status"],
            "teacher_task_result": self._document["teacher_task_result"]["result"],
            "failure": self._document["failure"]})
        self._stream_manifest_block()
        self._write()

    def _build_process_summary(self, end_observation) -> dict[str, object]:
        """The `teacher_process_summary` document, aggregated on its own thread and awaited with a bound. Never raises."""
        from so101_demo.core.process_summary import failure_summary

        policy = getattr(self, "_execution_policy", None)
        try:
            summary = self._process_summary
            if summary.limits is None and getattr(self, "_safety_limits", None) is not None:
                summary.limits = self._safety_limits
            if summary.limits is None:
                summary._limits_error = getattr(self, "_safety_limits_error", None) or "THRESHOLDS_UNAVAILABLE"
            extra = []
            expected = []
            physics = getattr(self, "_physics_hazard_watch", None)
            if physics is not None:
                expected.append("physics")
                if getattr(physics, "chunks_seen", 1) == 0:
                    extra.append("PHYSICS_CHUNKS_NEVER_RECEIVED")
            collision = getattr(self, "_collision_watch", None)
            if collision is not None:
                expected.append("collision")
                if getattr(collision, "frames_seen", 1) == 0:
                    extra.append("COLLISION_FRAMES_NEVER_RECEIVED")
            summary.check_streams(self._monotonic(), expected)
            truncated = getattr(getattr(self, "observer", None), "truncated_count", 0)
            if isinstance(truncated, int) and truncated > 0:
                extra.append("WORLD_TRUNCATED")
            waiter = summary.compute_in_thread(
                policy=policy, place_height=self._document.get("place_height"), end_observation=end_observation,
                perception_error=getattr(self, "_perception_error", None), extra_incomplete=extra)
            document = waiter(_SUMMARY_JOIN_S)
            if document is None:
                return failure_summary(waiter.error() or "SUMMARY_TIMEOUT", policy=policy)
            return document
        except Exception as error:
            return failure_summary(f"SUMMARY_FAILED: {type(error).__name__}: {error}"[:300], policy=policy)

    @staticmethod
    def _failure_boundary(state_trace, failure=None, workflow=None) -> State | None:
        from so101_demo.core.workflow import SO101_WORKFLOW

        workflow = SO101_WORKFLOW if workflow is None else workflow
        terminal = failure is not None and failure.code in workflow.terminal_stop_codes
        for current, following in zip(state_trace, state_trace[1:]):
            transition = workflow.transitions.get(current)
            if transition is not None and (following is transition[1] or terminal and following is State.ERROR):
                return current
        return None

    def _capture_failure_evidence(self, result) -> dict[str, object]:
        if self._teacher_run():
            from so101_demo.core.workflow import TEACHER_WORKFLOW
            boundary = self._failure_boundary(result.state_trace, result.failure, TEACHER_WORKFLOW)
        else:
            boundary = self._failure_boundary(result.state_trace, result.failure)
        no_action = (
            tuple(result.state_trace) == (State.IDLE, State.ERROR)
            and not self._state_events
            and not self._planning_attempts
        )
        evidence: dict[str, object] = {
            "failure_boundary_state": None if boundary is None else boundary.value,
            "physical_action_proven_absent": no_action,
            "terminal_sample": None,
            "planning_scene_readback": None,
            "capture_errors": [],
        }
        if no_action:
            return evidence
        prior_sequences = [
            value.get("publisher_sequence")
            for event in self._state_events
            for value in (event.get("before"), event.get("after"))
            if isinstance(value, dict)
            and type(value.get("publisher_sequence")) is int
        ]
        freshness_floor = max(
            [0, *prior_sequences, self._release_marker_sequence or 0]
        )
        try:
            deadline = time.monotonic() + 2.0
            terminal = self._snapshot()
            while terminal.publisher_sequence <= freshness_floor:
                if time.monotonic() >= deadline:
                    raise RuntimeError("DYNAMIC_FAILURE_EVIDENCE_STALE")
                terminal = self._snapshot()
            evidence["terminal_sample"] = self._evidence(terminal)
        except Exception as error:
            evidence["capture_errors"].append(
                f"PHYSICAL:{str(error).split(':', 1)[0]}"
            )
        try:
            attached, world = self._scene_membership()
            evidence["planning_scene_readback"] = {
                "attached_object_ids": attached,
                "world_primitive_counts": world,
            }
        except Exception as error:
            evidence["capture_errors"].append(
                f"SCENE:{str(error).split(':', 1)[0]}"
            )
        return evidence

    def _progress(self) -> None:
        import rclpy

        # Observation only (D12): time each sub-step so one slow call is explained by its parts.
        began = time.monotonic()
        lap = began
        substeps = {}

        def tick(name):
            nonlocal lap
            now = time.monotonic()
            substeps[name] = round((now - lap) * 1e3, 3)
            lap = now

        try:
            # Control needs exactly one thing here: its own callbacks (world observer, joint states, controller
            # results). A failure of those is an execution error and propagates.
            _spin_burst(self._node, spin=rclpy.spin_once)
            tick("spin_once")
        finally:
            self._report_slow_progress(began, substeps)

    def _report_slow_progress(self, began, substeps):
        """Emit a bounded fact line for one slow `_progress` call; never raises."""
        try:
            total_ms = (time.monotonic() - began) * 1e3
            emitted = getattr(self, "_progress_slow_lines", 0)
            if total_ms <= 50.0 or emitted >= 20:
                return
            self._progress_slow_lines = emitted + 1
            substeps.setdefault("spin_once", 0.0)
            document = {"total_ms": round(total_ms, 3), "substeps_ms": substeps}
            line = "DYNAMIC_PROGRESS_SLOW " + json.dumps(document, sort_keys=True, separators=(",", ":"))
            print(line.encode()[:2000].decode(errors="ignore"), file=sys.stderr, flush=True)
        except Exception:
            pass

    def _identity_detail(self, value) -> str:
        """What a world identity failure saw: the failing frame and the observer's last frames (observation only)."""
        recent = []
        recorder = getattr(self.observer, "recent_summaries", None)
        if recorder is not None:
            try:
                recent = recorder(5)
            except Exception:   # noqa: BLE001  (an observation can never replace the failure it explains)
                recent = []
        age = recent[-1].get("age_s") if recent else None
        return json.dumps({
            "paused": bool(value.paused), "reset_epoch": value.reset_epoch, "expected_reset_epoch": self._expected_reset_epoch,
            "simulation_step": value.simulation_step, "publisher_sequence": value.publisher_sequence,
            "receive_age_s": age, "recent": recent}, sort_keys=True)

    @staticmethod
    def _evidence(value) -> dict[str, object]:
        return {
            "publisher_sequence": value.publisher_sequence,
            "simulation_step": value.simulation_step,
            "reset_epoch": value.reset_epoch,
            "cup_position_world_m": list(value.object_state.position_world),
            "cup_orientation_world_xyzw": list(value.object_state.orientation_xyzw),
            "cup_linear_velocity_world_m_s": list(value.object_state.linear_velocity_world),
            "cup_angular_velocity_world_rad_s": list(value.object_state.angular_velocity_world),
            "left_contact_count": len(value.left_fingertip_contacts),
            "right_contact_count": len(value.right_fingertip_contacts),
            "maximum_normal_force_n": value.maximum_normal_force_n,
            "table_contact": any(
                item.geom2 == "table_collision" for item in value.other_object_contacts
            ),
        }

    def _record_monitor_violation(self, state: State, reason: str, value) -> None:
        def contacts(items) -> list[dict[str, object]]:
            return [
                {
                    "geom1": getattr(item, "geom1", None),
                    "geom2": getattr(item, "geom2", None),
                    "position_world_m": (
                        None if getattr(item, "position_world", None) is None
                        else list(item.position_world)
                    ),
                    "signed_distance_m": getattr(item, "signed_distance_m", None),
                    "normal_force_n": getattr(item, "normal_force_n", None),
                }
                for item in items
            ]

        violation = {
            "state": state.value,
            "reason": reason,
            "sample": self._evidence(value),
            "contacts": {
                "left": contacts(value.left_fingertip_contacts),
                "right": contacts(value.right_fingertip_contacts),
                "other": contacts(value.other_object_contacts),
            },
            "last_joint_positions_rad": {
                name: self._positions.get(name) for name in (*self._ARM_JOINTS, "6")
            },
            "last_joint_state_received_monotonic_s": self._joint_state_received_monotonic_s,
        }
        self._document.setdefault("monitor_violation", violation)
        self._document.setdefault("monitor_violations", []).append(violation)

    def _record(self, state: State, before, after, **details: object) -> None:
        self._state_events.append(
            {
                "state": state.value,
                "before": None if before is None else self._evidence(before),
                "after": None if after is None else self._evidence(after),
                **details,
            }
        )
        self._write()

    def _record_planning_attempt(self, document: dict[str, object]) -> None:
        attempts = getattr(self, "_planning_attempts", None)
        if attempts is None:
            attempts = []
            self._planning_attempts = attempts
            self._document["planning_attempts"] = attempts
        attempts.append(document)
        self._write()

    def _record_per_step_violation(self, state: State, plugin) -> None:
        self._document.setdefault("monitor_violation", {
            "state": state.value, "reason": plugin.limit_code, "sample": None,
            "per_step": {"step": plugin.limit_step, "state": plugin.limit_state, "value": plugin.limit_value,
                         "limit": plugin.limit_limit, "kind": plugin.limit_kind},
            "last_joint_positions_rad": {
                name: self._positions.get(name) for name in (*self._ARM_JOINTS, "6")},
            "last_joint_state_received_monotonic_s": self._joint_state_received_monotonic_s,
        })

    def _publish_teacher_event(self, kind, payload) -> None:
        """Offer one Teacher fact to the stream. Bounded, non-blocking, never raises into control."""
        try:
            self._event_sink.publish(kind, payload)
        except Exception:
            pass
