"""Bounded full native chunk ingress into the executing child's single audit writer."""

from collections import deque
import copy
import base64
import json
import math
import os
import sys
import threading
import time

from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from so101_mujoco_support.msg import PhysicsStepEvidenceChunk

from so101_demo.act.raw_physics_chunks import raw_chunk_from_ros, verify_raw_chunk


# Observation-only receipt-delay diagnostics: never alter admission, bounded output.
_LATE_DELAY_NS = 50_000_000
_LATE_LINE_LIMIT = 20
#: bounded samples kept per latency leg for the percentiles (about 6.8 min of chunks at 10 Hz)
_LATENCY_WINDOW = 4096
_LATENCY_LEGS = ("sample_to_handoff", "handoff_to_publish", "publish_to_receipt", "total")


class RosEpisodePhysicsAdapter:
    def __init__(self, node, *, session_id, reset_epoch, nq, nv, audit,
                 clock_ns=time.monotonic_ns, pending_capacity=128, max_age_s=.1,   # max_age_s: the sim-time causal join window of source_at, not a delivery rule
                 max_samples=None, max_contacts=None, history_capacity=256,
                 dedicated_receiver=False, spool=None, spool_backlog_max_frames=None, receiver_lag_max_s=None):
        if (not isinstance(session_id, str) or not session_id or type(reset_epoch) is not int
                or reset_epoch < 1 or type(nq) is not int or nq < 1
                or type(nv) is not int or nv < 1 or not callable(clock_ns)
                or type(pending_capacity) is not int or pending_capacity < 1
                or type(history_capacity) is not int or history_capacity < 1
                or not callable(getattr(audit, "append_raw_physics", None))
                or type(max_age_s) not in (int, float) or not 0 < max_age_s <= .1
                or max_samples is not None and (type(max_samples) is not int or max_samples < 1)
                or max_contacts is not None and (type(max_contacts) is not int or max_contacts < 0)):
            raise ValueError("PHYSICS_RAW_ADAPTER_CONFIG_INVALID")
        self.session_id, self.reset_epoch = session_id, reset_epoch
        self.nq, self.nv = nq, nv
        self.audit, self.clock_ns = audit, clock_ns
        self.capacity, self.max_age_s = pending_capacity, max_age_s
        self.max_samples, self.max_contacts = max_samples, max_contacts
        self.hazard = None
        self._node = node
        self._lock = threading.RLock()
        self._drain_lock = threading.RLock()
        self._pending = deque()
        # Derived lookup only: originals remain in the complete durable chunk stream.
        # Callback admission cannot publish a source until the sole writer appends it.
        self._history = deque(maxlen=history_capacity)
        self._previous = None
        # CP-3410 policy (frozen in episode_recorder_v1): the data fails on a backlog, not on a late chunk.
        self._backlog_max = spool_backlog_max_frames
        self._lag_max_ns = None if receiver_lag_max_s is None else round(receiver_lag_max_s * 1e9)
        self._lag_check_ended = False
        self._latency = {leg: deque(maxlen=_LATENCY_WINDOW) for leg in _LATENCY_LEGS}
        self._latency_peaks = {"max_spool_backlog_frames": 0, "max_publish_deferrals_total": 0, "max_receiver_lag_ns": 0}
        self._rejected = None
        self._closed = False
        self._closing = False
        self._receipt = {"chunk_count": 0, "late_count": 0, "late_lines": 0, "max_delay_ns": None,
                         "max_delay_sequence": None, "last_delay_ns": None, "last_sequence": None,
                         "last_receipt_ns": None}
        self._rx_node = self._rx_executor = self._receiver_thread = None
        self._spool = spool
        self._receiver_stop = threading.Event()
        self._receiver_end_reason = None
        self._shutdown_destroy_notes = []
        qos = QoSProfile(depth=100, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.VOLATILE)
        if spool is not None:
            # The chunk receipt lives in the spooler process (act/chunk_spool.py): nothing to subscribe here.
            self.subscription = None
            return
        if not dedicated_receiver:
            self.subscription = node.create_subscription(PhysicsStepEvidenceChunk,
                "/so101/simulation/physics_step_chunks", self.accept_message, qos)
            return
        # Receipt freshness is a property of this receiver, not of whether the runtime thread is
        # spinning: the same subscription lives on a private node served by its own thread.
        import rclpy
        from rclpy.executors import SingleThreadedExecutor
        self._rx_node = rclpy.create_node(f"so101_episode_physics_rx_{os.getpid()}", context=node.context)
        try:
            self._rx_executor = SingleThreadedExecutor(context=node.context)
            self._rx_executor.add_node(self._rx_node)
            self.subscription = self._rx_node.create_subscription(PhysicsStepEvidenceChunk,
                "/so101/simulation/physics_step_chunks", self.accept_message, qos)
        except BaseException:
            self._destroy_receiver()
            raise
        self._receiver_thread = threading.Thread(target=self._receiver_loop, daemon=True,
                                                 name="so101-episode-physics-receiver")
        self._receiver_thread.start()

    def start_spool_reader(self):
        """Start the thread that ingests the spooler's frames with the spooler's own receipt stamps."""
        self._receiver_thread = threading.Thread(target=self._spool_loop, daemon=True,
                                                 name="so101-episode-physics-spool-reader")
        self._receiver_thread.start()

    def _spool_loop(self):
        from rclpy.serialization import deserialize_message
        try:
            while not self._receiver_stop.is_set():
                frames = self._spool.read_frames()
                with self._lock:
                    self._note_backlog(len(frames))       # every frame read and not yet processed is backlog
                    self._check_lag()
                for position, (is_record, receipt, data) in enumerate(frames):
                    if self.hazard is not None:
                        break                       # nothing more is admitted: do not spend the GIL deserializing the rest
                    try:
                        if is_record:
                            # converted by the spooler, in its own process (the main process no longer pays ~25 ms per chunk)
                            decoded = json.loads(data)
                        else:
                            decoded = deserialize_message(data, PhysicsStepEvidenceChunk)
                    except Exception:
                        with self._lock:
                            if self.hazard is None:
                                self.hazard = "PHYSICS_RAW_DESERIALIZE_FAILED"
                        break
                    if is_record:
                        self.accept_record(decoded, receipt_ns=receipt)
                    else:
                        self.accept_message(decoded, receipt_ns=receipt)
                    with self._lock:
                        self._note_backlog(len(frames) - position - 1)
                        self._check_lag()
                failure = self._spool.failure()
                if failure is not None:
                    with self._lock:
                        if self.hazard is None:
                            self.hazard = failure
                    return
                if not frames:
                    self._receiver_stop.wait(0.005)
        except BaseException as error:
            with self._lock:
                if self.hazard is None:
                    self.hazard = "PHYSICS_RAW_RECEIVER_FAILED" if not isinstance(error, ValueError) else str(error)

    def _receiver_loop(self):
        try:
            while not self._receiver_stop.is_set():
                self._rx_executor.spin_once(timeout_sec=0.05)
        except BaseException:
            if not self._receiver_stop.is_set():
                try:
                    context_ok = bool(self._rx_node.context.ok())
                except BaseException:
                    context_ok = True  # an unreadable context is not proof of an orderly shutdown
                if not context_ok:
                    # Orderly rclpy shutdown before close(): no chunk can arrive any more, so the
                    # receiver ends without a hazard. Incomplete data is still caught by the
                    # continuity, terminal and seal checks; nothing is fabricated here.
                    self._receiver_end_reason = "CONTEXT_SHUTDOWN"
                    return
                with self._lock:
                    if self.hazard is None:
                        self.hazard = "PHYSICS_RAW_RECEIVER_FAILED"

    def _destroy_receiver(self, subscription=None):
        """Destroy the private receiver resources; return every failure, first one first."""
        errors = []
        try:
            context_ok = bool(self._rx_node.context.ok())
        except BaseException:
            context_ok = True
        for operation in (
                *(() if subscription is None else (lambda: self._rx_node.destroy_subscription(subscription),)),
                lambda: self._rx_executor is None or self._rx_executor.shutdown(),
                lambda: self._rx_node is None or self._rx_node.destroy_node()):
            try:
                operation()
            except BaseException as error:
                if context_ok:
                    errors.append(error)
                else:
                    # Destruction after an orderly context shutdown is a note, not a failure.
                    self._shutdown_destroy_notes.append(repr(error))
        self._rx_node = self._rx_executor = None
        return errors

    def _stop_receiver(self):
        """Join the receiver thread (2 s bound), then destroy its subscription, executor and node."""
        if self._spool is not None:
            self._receiver_stop.set()
            errors = []
            thread = self._receiver_thread
            if thread is not None:
                thread.join(2.0)
                if thread.is_alive():
                    errors.append(RuntimeError("PHYSICS_RAW_RECEIVER_JOIN_TIMEOUT"))
            try:
                self._spool.close()
            except BaseException as error:
                errors.append(error)
            return errors
        if self._rx_node is None:
            return []
        errors = []
        self._receiver_stop.set()
        thread = self._receiver_thread
        thread.join(2.0)
        if thread.is_alive():
            errors.append(RuntimeError("PHYSICS_RAW_RECEIVER_JOIN_TIMEOUT"))
        errors.extend(self._destroy_receiver(self.subscription))
        return errors

    def accept_message(self, message, receipt_ns=None):
        receipt = self.clock_ns() if receipt_ns is None else receipt_ns
        with self._lock:
            if self._closed or self._closing or self.hazard is not None:
                return
            self._note_receipt(message, receipt)
            try:
                self._admit(message, receipt)
            except (AttributeError, TypeError, ValueError, OverflowError) as error:
                self._refuse(message, receipt, error)

    def accept_record(self, record, receipt_ns=None):
        """`accept_message` for a chunk the spooler already converted to its record (same rules, same hazards)."""
        receipt = self.clock_ns() if receipt_ns is None else receipt_ns
        with self._lock:
            if self._closed or self._closing or self.hazard is not None:
                return
            self._note_receipt_record(record, receipt)
            try:
                self._admit_record(record)
            except (AttributeError, TypeError, ValueError, OverflowError, KeyError) as error:
                self._refuse_record(record, receipt, error)

    def _admit_record(self, record):
        if len(self._pending) >= self.capacity:
            raise ValueError("PHYSICS_RAW_PENDING_OVERFLOW")
        verify_raw_chunk(record, previous=self._previous, session_id=self.session_id,
            reset_epoch=self.reset_epoch, nq=self.nq, nv=self.nv,
            max_samples=self.max_samples, max_contacts=self.max_contacts)
        self._pending.append(record)
        self._previous = record

    def _refuse_record(self, record, receipt, error):
        self.hazard = str(error) or "PHYSICS_RAW_CALLBACK_INVALID"
        # the original ROS message was converted in the spooler; the converted original is what is kept for failure readback
        self._rejected = {"received_monotonic_ns": receipt, "reason": self.hazard, "record": record}

    def _admit(self, message, receipt):
        if len(self._pending) >= self.capacity:
            raise ValueError("PHYSICS_RAW_PENDING_OVERFLOW")
        record = raw_chunk_from_ros(message, received_monotonic_ns=receipt,
            max_samples=self.max_samples, max_contacts=self.max_contacts)
        verify_raw_chunk(record, previous=self._previous, session_id=self.session_id,
            reset_epoch=self.reset_epoch, nq=self.nq, nv=self.nv,
            max_samples=self.max_samples, max_contacts=self.max_contacts)
        self._pending.append(record)
        self._previous = record

    def _refuse(self, message, receipt, error):
        self.hazard = str(error) or "PHYSICS_RAW_CALLBACK_INVALID"
        # A refused original cannot enter the success audit schema. Preserve its
        # actual CDR bytes (including invalid floating values) for failure readback.
        self._rejected = {"received_monotonic_ns": receipt, "reason": self.hazard}
        try:
            from rclpy.serialization import serialize_message
            self._rejected["ros_type"] = "so101_mujoco_support/msg/PhysicsStepEvidenceChunk"
            self._rejected["cdr_base64"] = base64.b64encode(serialize_message(message)).decode("ascii")
        except Exception as serialization_error:
            self._rejected["serialization_error"] = str(serialization_error)

    # ---- backlog and receiver lag: the data fails on these, never on one late chunk (CP-3410) ---------------------------

    def end_lag_check(self):
        """The recording is over: the simulation may stop publishing, so a growing lag is no longer a defect."""
        with self._lock:
            self._lag_check_ended = True

    def _check_lag(self):
        """Fail the data when the newest received sample is more than the policy's lag behind now. Needs the lock."""
        if self._lag_max_ns is None or self._lag_check_ended or self.hazard is not None or self._previous is None:
            return
        newest = self._previous["chunk"]["samples"][-1]["clock_interval_begin_monotonic_ns"]
        lag = int(self.clock_ns()) - newest
        self._latency_peaks["max_receiver_lag_ns"] = max(self._latency_peaks["max_receiver_lag_ns"], lag)
        if lag > self._lag_max_ns:
            self.hazard = "PHYSICS_RAW_RECEIVER_LAG_EXCEEDED"

    def _note_backlog(self, frames):
        """Unprocessed spool frames at this instant; fail the data beyond the policy. Needs the lock."""
        self._latency_peaks["max_spool_backlog_frames"] = max(self._latency_peaks["max_spool_backlog_frames"], frames)
        if self._backlog_max is not None and frames > self._backlog_max and self.hazard is None:
            self.hazard = "PHYSICS_RAW_SPOOL_BACKLOG_EXCEEDED"

    # ---- lateness telemetry -------------------------------------------------------------------------------------------

    def _count_receipt(self, receipt):
        state = self._receipt
        state["chunk_count"] += 1
        state["last_receipt_ns"] = receipt
        state["last_delay_ns"] = state["last_sequence"] = None
        return state["last_receipt_ns"]

    def _note_receipt(self, message, receipt):
        """Record how long after its newest clock interval began the chunk reached this callback."""
        previous = self._receipt["last_receipt_ns"]
        self._count_receipt(receipt)
        try:
            self._note_delay(int(message.chunk_sequence), int(message.samples[-1].clock_interval_begin_monotonic_ns),
                             int(message.samples[-1].clock_interval_end_monotonic_ns), receipt, previous,
                             int(message.handoff_monotonic_ns), int(message.publish_monotonic_ns),
                             int(message.publish_deferrals_total))
        except Exception:
            pass

    def _note_receipt_record(self, record, receipt):
        previous = self._receipt["last_receipt_ns"]
        self._count_receipt(receipt)
        try:
            chunk = record["chunk"]
            last = chunk["samples"][-1]
            self._note_delay(int(chunk["chunk_sequence"]), int(last["clock_interval_begin_monotonic_ns"]),
                             int(last["clock_interval_end_monotonic_ns"]), receipt, previous,
                             int(chunk["handoff_monotonic_ns"]), int(chunk["publish_monotonic_ns"]),
                             int(chunk["publish_deferrals_total"]))
        except Exception:
            pass

    def _note_delay(self, sequence, newest_begin_ns, newest_end_ns, receipt, previous, handoff_ns, publish_ns, deferrals):
        state = self._receipt
        delay = int(receipt) - newest_begin_ns
        state["last_delay_ns"], state["last_sequence"] = delay, sequence
        if state["max_delay_ns"] is None or delay > state["max_delay_ns"]:
            state["max_delay_ns"], state["max_delay_sequence"] = delay, sequence
        self._latency["total"].append(delay)
        if handoff_ns and publish_ns:                # a plugin that stamps: split the path into its legs
            self._latency["sample_to_handoff"].append(handoff_ns - newest_end_ns)
            self._latency["handoff_to_publish"].append(publish_ns - handoff_ns)
            self._latency["publish_to_receipt"].append(int(receipt) - publish_ns)
        self._latency_peaks["max_publish_deferrals_total"] = max(self._latency_peaks["max_publish_deferrals_total"], deferrals)
        if delay > _LATE_DELAY_NS:
            state["late_count"] += 1
            if state["late_lines"] < _LATE_LINE_LIMIT:
                state["late_lines"] += 1
                print("EPISODE_PHYSICS_CHUNK_LATE " + json.dumps({"seq": sequence,
                    "delay_ms": delay / 1e6, "receipt_ns": int(receipt),
                    "prev_receipt_ns": previous,
                    "callback_gap_ms": None if previous is None else (receipt - previous) / 1e6,
                    "handoff_to_publish_ms": None if not (handoff_ns and publish_ns) else (publish_ns - handoff_ns) / 1e6,
                    "publish_to_receipt_ms": None if not (handoff_ns and publish_ns) else (int(receipt) - publish_ns) / 1e6,
                    "publish_deferrals_total": deferrals},
                    sort_keys=True, separators=(",", ":")), file=sys.stderr, flush=True)

    def _latency_summary(self):
        summary = {}
        for leg in _LATENCY_LEGS:
            values = sorted(self._latency[leg])
            count = len(values)

            def percentile(fraction, values=values, count=count):
                return None if not count else round(values[min(count - 1, int(fraction * count))] / 1e6, 3)
            summary[leg] = {"count": count, "p50": percentile(.5), "p90": percentile(.9), "p99": percentile(.99),
                            "max": None if not count else round(values[-1] / 1e6, 3)}
        return summary

    def receipt_diagnostics(self):
        """Copy the observation-only receipt counters and the latency split (telemetry; never a rule)."""
        with self._lock:
            state = dict(self._receipt)
            summary = self._latency_summary()
            peaks = dict(self._latency_peaks)
        return {"chunk_count": state["chunk_count"], "late_count": state["late_count"],
            "late_threshold_ms": _LATE_DELAY_NS / 1e6,
            "max_delay_ms": None if state["max_delay_ns"] is None else state["max_delay_ns"] / 1e6,
            "max_delay_sequence": state["max_delay_sequence"],
            "last_delay_ms": None if state["last_delay_ns"] is None else state["last_delay_ns"] / 1e6,
            "last_sequence": state["last_sequence"], "last_receipt_ns": state["last_receipt_ns"],
            "latency_ms": summary, "max_spool_backlog_frames": peaks["max_spool_backlog_frames"],
            "max_publish_deferrals_total": peaks["max_publish_deferrals_total"],
            "max_receiver_lag_ms": peaks["max_receiver_lag_ns"] / 1e6}

    def _emit_drain_failure(self, error, record):
        """Observation only: one stderr line for an audit-append failure; never raises."""
        try:
            chunk = record["chunk"]
            samples = chunk["samples"]
            with self._lock:
                last = self._history[-1] if self._history else None
                doc = {"error_type": type(error).__name__, "error_message": str(error)[:200],
                    "chunk_sequence": chunk["chunk_sequence"],
                    "first_physics_step": samples[0]["physics_step"],
                    "last_physics_step": samples[-1]["physics_step"],
                    "received_monotonic_ns": record["received_monotonic_ns"],
                    "last_durable_chunk_sequence": None if last is None else last["chunk_sequence"],
                    "last_durable_physics_step": None if last is None else last["sample"]["physics_step"],
                    "pending_count": len(self._pending), "closing": self._closing,
                    "closed": self._closed, "hazard": self.hazard,
                    "hazard_monotonic_ns": time.monotonic_ns()}
            print("PHYSICS_RAW_DRAIN_FAILURE " + json.dumps(doc, sort_keys=True, default=str),
                file=sys.stderr, flush=True)
        except BaseException:
            pass

    def drain(self, *, retain_failed=False):
        # Same runtime thread owns all audit appends. The callback retains original data only.
        with self._drain_lock:
            with self._lock:
                self._check_lag()
                if self.hazard is not None and not retain_failed:
                    raise ValueError(self.hazard)
            written = 0
            while True:
                with self._lock:
                    if self.hazard is not None and not retain_failed:
                        raise ValueError(self.hazard)
                    if not self._pending:
                        break
                    record = self._pending[0]
                try:
                    self.audit.append_raw_physics(record)
                except Exception as error:
                    with self._lock:
                        self.hazard = self.hazard or str(error) or "PHYSICS_RAW_AUDIT_WRITE_FAILED"
                    self._emit_drain_failure(error, record)
                    raise ValueError(self.hazard) from error
                # The record is exclusively owned (callback-retained); every history reader copies or reads scalars.
                history = [{"sample": sample,
                    "received_monotonic_ns": record["received_monotonic_ns"],
                    "chunk_sequence": record["chunk"]["chunk_sequence"]}
                    for sample in record["chunk"]["samples"]]
                with self._lock:
                    self._pending.popleft()
                    self._history.extend(history)
                written += 1
            with self._lock:
                if self.hazard is not None:
                    raise ValueError(self.hazard)
            return written

    def original_durable_steps(self, min_physics_step=None):
        """Copy the bounded original lookup history; callback-only samples are excluded.

        With min_physics_step, only samples at or after that step are copied (filter before copy).
        """
        if min_physics_step is not None and (type(min_physics_step) is not int or min_physics_step < 0):
            raise ValueError('PHYSICS_RAW_QUERY_INVALID')
        with self._lock:
            if self.hazard is not None:
                raise ValueError(self.hazard)
            return [copy.deepcopy(record['sample']) for record in self._history
                    if min_physics_step is None or record['sample']['physics_step'] >= min_physics_step]

    def first_original_durable_step(self, min_physics_step):
        """The first durable sample at or after `min_physics_step` (history order), deep-copied alone, or None.

        Same sample, copy guarantee and errors as `original_durable_steps(min_physics_step=...)[:1]`, without
        copying the rest of the retained tail.
        """
        if type(min_physics_step) is not int or min_physics_step < 0:
            raise ValueError('PHYSICS_RAW_QUERY_INVALID')
        with self._lock:
            if self.hazard is not None:
                raise ValueError(self.hazard)
            for record in self._history:
                if record['sample']['physics_step'] >= min_physics_step:
                    return copy.deepcopy(record['sample'])
            return None

    def earliest_sample_time_s(self):
        """Simulation time of the oldest sample still in the bounded lookup history, or None when it is empty."""
        with self._lock:
            if not self._history:
                return None
            return self._history[0]['sample']['simulation_time_s']

    def latest_sample_time_s(self):
        """Simulation time of the newest sample received (pending or drained), or None before the first chunk."""
        with self._lock:
            if self._previous is None:
                return None
            return self._previous["chunk"]["samples"][-1]["simulation_time_s"]

    def received_max_step(self):
        """Return the newest accepted and verified chunk's last physics step (pending or drained), or None."""
        with self._lock:
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if self._previous is None:
                return None
            return self._previous["chunk"]["samples"][-1]["physics_step"]

    def retained_step_range(self):
        """Return (min_step, max_step) of the bounded lookup history, or None, without copying samples."""
        with self._lock:
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if not self._history:
                return None
            steps = [record['sample']['physics_step'] for record in self._history]
            return (min(steps), max(steps))

    def history_summary(self):
        """Observation only: read-only retained-history and pending counts, no copies of samples."""
        with self._lock:
            history = self._history
            first = history[0]["sample"] if history else None
            last = history[-1]["sample"] if history else None
            return {"count": len(history),
                "first_physics_step": None if first is None else first["physics_step"],
                "last_physics_step": None if last is None else last["physics_step"],
                "first_simulation_time_s": None if first is None else first["simulation_time_s"],
                "last_simulation_time_s": None if last is None else last["simulation_time_s"],
                "pending": len(self._pending)}

    def source_at(self, at_s, *, physics_step=None):
        """Return the latest causal durable native source, with no stale/future fallback."""
        if (type(at_s) not in (int, float) or not math.isfinite(at_s) or at_s < 0
                or physics_step is not None and (type(physics_step) is not int or physics_step < 1)):
            raise ValueError("PHYSICS_GRID_INVALID")
        with self._lock:
            if self.hazard is not None:
                raise ValueError(self.hazard)
            at_ns, max_age_ns = round(at_s * 1e9), round(self.max_age_s * 1e9)
            for record in reversed(self._history):
                sample = record["sample"]
                if (physics_step is None or sample["physics_step"] == physics_step) and (
                        0 <= at_ns - round(sample["simulation_time_s"] * 1e9) <= max_age_ns):
                    return copy.deepcopy(record)
            return None

    def snapshot(self):
        with self._lock:
            return copy.deepcopy({"hazard": self.hazard, "closed": self._closed,
                "admission_closed": self._closed or self._closing,
                "pending_originals": list(self._pending), "rejected_original": self._rejected})

    def close(self):
        # Admission is fenced immediately, even while an existing durable append is blocked.
        with self._lock:
            self._closing = True
        with self._drain_lock:
            with self._lock:
                if self._closed:
                    return
            if self._closing:
                failure = None
                for error in self._stop_receiver():
                    if failure is None:
                        failure = error
                    else:
                        failure.add_note("Owned physics receiver close failed: " + str(error))
                try:
                    self.drain(retain_failed=True)
                except BaseException as error:
                    if failure is None:
                        failure = error
                    else:
                        failure.add_note("Physics drain failed: " + str(error))
                finally:
                    try:
                        if self._receiver_thread is None and self._spool is None:
                            self._node.destroy_subscription(self.subscription)
                    except BaseException as error:
                        if failure is None:
                            failure = error
                        else:
                            failure.add_note("Owned physics subscription close failed: " + str(error))
                    self._closed = True
                    if self.hazard is not None and getattr(self.audit, "root", None) is not None:
                        # Failure may happen before the execution object exists. Its diagnostic
                        # document therefore lives beside the owned episode, outside the seal's
                        # success inventory, and is written once by the same runtime thread.
                        try:
                            from so101_demo.runtime.task_artifacts import fsync_directory
                            path = self.audit.root.parent / "physics-source-failure.json"
                            source = self.snapshot()
                            source["receipt_diagnostics"] = self.receipt_diagnostics()
                            document = {"kind": "ACT_PHYSICS_SOURCE_FAILURE", "schema_version": 1,
                                        "identity": self.audit.identity, "source": source}
                            with path.open("xb") as stream:
                                stream.write(json.dumps(document, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode() + b"\n")
                                stream.flush()
                                os.fsync(stream.fileno())
                            fsync_directory(path.parent)
                        except BaseException as error:
                            if failure is None:
                                failure = error
                            else:
                                failure.add_note("Physics failure evidence retention failed: " + str(error))
                if failure is not None:
                    raise failure
