"""Read-only source-clock history for complete MuJoCo physics samples."""

from __future__ import annotations

import copy
import json
import logging
import math
import threading
from types import MappingProxyType
import time
from collections import deque

from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk


_STEP_NS = 2_000_000
_ARRIVAL_GAP_NS = 100_000_000
_ARRIVAL_GAP_LINES_PER_EPOCH = 20
_INTEGRITY_AUDIT_LINES = 20
_INTEGRITY_AUDIT_REASONS = 16
# In audit mode these external latch requests describe raw-stream completeness,
# not control identity, so they are recorded instead of latching a hazard.
_AUDIT_ONLY_LATCH_REASONS = frozenset({
    "PHYSICS_CHUNK_CALLBACK_INVALID", "PHYSICS_CHUNK_PREARM_LOSS"})
_LOGGER = logging.getLogger(__name__)


class _IdentityRefused(ValueError):
    """Session or epoch mismatch: a control-identity fault that latches in every mode."""


def _integer(value, name, minimum=0):
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} invalid")
    return value


def _simulation_ns(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("PHYSICS_SIMULATION_TIME_INVALID")
    if value < 0:
        raise ValueError("PHYSICS_SIMULATION_TIME_INVALID")
    return round(value * 1_000_000_000)


def _optional_duration_ns(value, name):
    if value is None:
        return None
    if (isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value <= 0):
        raise ValueError(f"{name} invalid")
    duration = round(value * 1_000_000_000)
    if duration < 1:
        raise ValueError(f"{name} invalid")
    return duration


class PhysicsClockHistory:
    """Validate every source step without granting a goal or collection permit."""

    def __init__(self, session_id, *, nq, nv, max_age_s,
                 max_source_step_gap_ns, max_silence_s=None,
                 first_chunk_timeout_s=None, incarnation=None,
                 clock_ns=time.monotonic_ns, audit_integrity=False, history_capacity=512):
        if (not isinstance(session_id, str) or not session_id or not callable(clock_ns)
                or type(audit_integrity) is not bool):
            raise ValueError("PHYSICS_CLOCK_CONFIG_INVALID")
        # Audit mode (the Teacher's own history): raw-stream completeness conditions
        # (chunk gaps, loss, truncation or hazard markers, source clock bounds, silence,
        # staleness) are recorded as bounded audit diagnostics and never latch a hazard.
        # Identity faults (session, epoch, foreign or future chunks) still latch.
        self.audit_integrity = audit_integrity
        self.nq = _integer(nq, "nq", 1)
        self.nv = _integer(nv, "nv", 1)
        self.max_source_step_gap_ns = _integer(
            max_source_step_gap_ns, "max_source_step_gap_ns", 1)
        if (isinstance(max_age_s, bool) or not isinstance(max_age_s, (int, float))
                or not math.isfinite(max_age_s) or max_age_s <= 0):
            raise ValueError("PHYSICS_CLOCK_CONFIG_INVALID")
        self.max_age_ns = round(max_age_s * 1_000_000_000)
        if self.max_age_ns < 1:
            raise ValueError("PHYSICS_CLOCK_CONFIG_INVALID")
        self.max_silence_ns = _optional_duration_ns(max_silence_s, "max_silence_s")
        self.first_chunk_timeout_ns = _optional_duration_ns(
            first_chunk_timeout_s, "first_chunk_timeout_s")
        self.session_id = session_id
        self.incarnation = incarnation if incarnation is not None else session_id
        self.version = 0
        self.clock_ns = clock_ns
        self._lock = threading.RLock()
        # Retention sizing only (samples, not a protection bound): fresh windows age at max_age_s regardless.
        self.history_capacity = _integer(history_capacity, "history_capacity", 1)
        self._history = deque(maxlen=self.history_capacity)
        self._by_step = {}
        self.epoch = None
        self.hazard = None
        self._last_sequence = -1
        self._last_step = 0
        self._last_sim_ns = 0
        self._last_source_begin_ns = 0
        self._last_source_end_ns = 0
        self._armed_monotonic_ns = 0
        self._first_chunk_seen = False
        self._original_window_attempted = False
        self._original_window_start = None
        # Observation-only diagnostics: never read by any decision.
        self.last_refusal_facts = None
        self.accepted_count = 0
        self.rejected_count = 0
        self.last_accept_received_ns = None
        self.last_rejection_reason = None
        self._gap_lines = 0
        self.integrity_audit_count = 0
        self.integrity_audit_reasons = {}
        self.last_integrity_reason = None
        self._integrity_lines = 0
        self._deadline_noted = False
        self._stale_noted = False

    def _audit(self, reason, now_ns=None):
        """Record one raw-stream completeness observation. Never raises, never latches."""
        try:
            with self._lock:
                self.integrity_audit_count += 1
                self.last_integrity_reason = str(reason)[:256]
                key = self.last_integrity_reason
                if key not in self.integrity_audit_reasons and len(
                        self.integrity_audit_reasons) >= _INTEGRITY_AUDIT_REASONS:
                    key = "OTHER"
                self.integrity_audit_reasons[key] = self.integrity_audit_reasons.get(key, 0) + 1
                emit = self._integrity_lines < _INTEGRITY_AUDIT_LINES
                if emit:
                    self._integrity_lines += 1
                fields = {"reason": self.last_integrity_reason, "epoch": self.epoch,
                          "count": self.integrity_audit_count, "version": self.version,
                          "last_step": self._last_step, "last_sequence": self._last_sequence}
            if emit:
                _LOGGER.error("PHYSICS_CLOCK_INTEGRITY_AUDIT %s",
                              json.dumps(fields, sort_keys=True, separators=(",", ":")))
        except Exception:
            pass

    def integrity_audit(self):
        """Bounded copy of the audit counters for the broker audit; observation only."""
        with self._lock:
            return {"count": self.integrity_audit_count,
                    "reasons": dict(self.integrity_audit_reasons),
                    "last_reason": self.last_integrity_reason}

    def arm(self, reset_epoch, *, source_floor_s):
        epoch = _integer(reset_epoch, "reset_epoch", 1)
        floor_ns = _simulation_ns(source_floor_s)
        with self._lock:
            if self._original_window_attempted:
                raise ValueError("PHYSICS_ORIGINAL_WINDOW_REARM_FORBIDDEN")
            if self.epoch is not None and epoch <= self.epoch:
                raise ValueError("PHYSICS_CLOCK_EPOCH_INVALID")
            self._initialize_window(epoch, floor_ns)

    def _initialize_window(self, epoch, floor_ns, *, first_step=1, first_sequence=0):
        """Initialize structural predecessors; caller holds the history lock."""
        self.epoch = epoch
        self.hazard = None
        self._history.clear()
        self._by_step.clear()
        self._last_sequence = first_sequence - 1
        self._last_step = first_step - 1
        self._last_sim_ns = floor_ns
        self._last_source_begin_ns = 0
        self._last_source_end_ns = 0
        self._armed_monotonic_ns = _integer(self.clock_ns(), "readback_ns", 1)
        self._first_chunk_seen = False
        self.last_accept_received_ns = None
        self._gap_lines = 0
        self._integrity_lines = 0
        self._deadline_noted = False
        self._stale_noted = False
        self.version += 1

    def _record_refusal(self, reason, now_ns):
        """Store one bounded refusal snapshot. Caller holds the lock; never raises."""
        try:
            self.last_refusal_facts = {
                "reason": reason, "now_ns": now_ns, "max_age_ns": self.max_age_ns,
                "history_len": len(self._history),
                "recent": [{"physics_step": entry["sample"].physics_step,
                            "clock_interval_end_ns":
                                entry["sample"].clock_interval_end_monotonic_ns,
                            "received_ns": entry["received_monotonic_ns"]}
                           for entry in list(self._history)[-5:]],
                "accepted_count": self.accepted_count,
                "rejected_count": self.rejected_count,
                "last_accept_received_ns": self.last_accept_received_ns,
                "last_rejection_reason": self.last_rejection_reason,
                "first_chunk_seen": self._first_chunk_seen, "epoch": self.epoch}
        except Exception:
            pass

    def _log_arrival_gap(self, gap):
        """Emit one arrival-gap line. Called outside the history lock; never raises."""
        try:
            gap = dict(gap, gap_ms=(gap["received_ns"] - gap["prev_received_ns"]) / 1e6)
            _LOGGER.error("PHYSICS_CLOCK_ARRIVAL_GAP %s",
                          json.dumps(gap, sort_keys=True, separators=(",", ":")))
        except Exception:
            pass

    def arm_original_window(self, chunk, *, after_monotonic_ns,
                            received_monotonic_ns=None):
        """Start a read-only view at one whole original postresume chunk.

        This is not a reset, native rearm, or command permit. Original steps,
        sequence numbers and source clocks remain unchanged. The caller must
        bind the floor to its actual execution-resume observation; this reader
        cannot establish that external authority. A failed first attempt closes
        this reader permanently, including its ordinary reset-arm entry point.
        """
        with self._lock:
            if self._original_window_attempted or self.epoch is not None:
                raise ValueError("PHYSICS_ORIGINAL_WINDOW_REARM_FORBIDDEN")
            self._original_window_attempted = True
            try:
                floor = _integer(after_monotonic_ns, "after_monotonic_ns", 1)
                owned = copy.deepcopy(chunk)
                if not isinstance(owned, PhysicsStepEvidenceChunk) or not owned.samples:
                    raise ValueError("PHYSICS_CHUNK_TYPE_INVALID")
                first = owned.samples[0]
                first_step = _integer(first.physics_step, "first_physics_step", 1)
                first_sequence = _integer(owned.chunk_sequence, "chunk_sequence")
                epoch = _integer(owned.reset_epoch, "reset_epoch", 1)
                first_sim_ns = _simulation_ns(first.simulation_time_s)
                if first_sim_ns < _STEP_NS or any(
                        _integer(sample.clock_interval_begin_monotonic_ns,
                                 "source_begin_ns", 1) < floor
                        for sample in owned.samples):
                    raise ValueError("PHYSICS_ORIGINAL_WINDOW_BEFORE_RESUME")
                self._initialize_window(epoch, first_sim_ns - _STEP_NS,
                                        first_step=first_step,
                                        first_sequence=first_sequence)
                if self.accept_chunk(owned, received_monotonic_ns=received_monotonic_ns) is not True:
                    raise ValueError("PHYSICS_ORIGINAL_WINDOW_INVALID")
                self._original_window_start = MappingProxyType({
                    "session_id": self.session_id, "reset_epoch": epoch,
                    "first_physics_step": first_step,
                    "first_chunk_sequence": first_sequence,
                    "first_simulation_time_s": first.simulation_time_s,
                    "after_monotonic_ns": floor,
                    "received_monotonic_ns": self._history[0]["received_monotonic_ns"],
                    "command_authority": False,
                })
            except (AttributeError, TypeError, ValueError, OverflowError) as error:
                self.latch("PHYSICS_ORIGINAL_WINDOW_INVALID")
                raise ValueError("PHYSICS_ORIGINAL_WINDOW_INVALID") from error

    @property
    def original_window_start(self):
        with self._lock:
            if self._original_window_start is None:
                raise ValueError("PHYSICS_ORIGINAL_WINDOW_UNAVAILABLE")
            return self._original_window_start

    def latch(self, reason):
        if not isinstance(reason, str) or not reason:
            raise ValueError("PHYSICS_CLOCK_HAZARD_INVALID")
        if self.audit_integrity and reason in _AUDIT_ONLY_LATCH_REASONS:
            self._audit(reason)
            return
        with self._lock:
            if self.hazard is None:
                self.hazard = reason
                self.version += 1

    def commit_state(self):
        """Unified version/incarnation/epoch/time state for one commit validation."""

        with self._lock:
            return {"version": self.version, "session_id": self.session_id,
                    "incarnation": self.incarnation, "epoch": self.epoch,
                    "hazard": self.hazard, "last_source_end_ns": self._last_source_end_ns,
                    "evidence_ready": (self.epoch is not None and self.hazard is None
                                       and self._first_chunk_seen)}

    def commit_receipt(self, *, expected_version, expected_incarnation, expected_epoch, step,
                       max_age_ns, enforce_age=True, require_retained=True):
        """O(1) final commit primitive: one history lock, fresh time, full validation.

        This is the single linearization point for admission and authority claims.
        It reads its own monotonic time, latches any expired deadline/hazard inside
        the same lock, and validates the expected version/incarnation/epoch, the
        readiness of the epoch, the selected step and its selected-state age. It
        returns an immutable scalar receipt; no large copy happens under the lock.

        ``expected_version=None`` (the Teacher's commit) does not compare the global
        version: a normally accepted chunk append only grows the history and says
        nothing about the selected state. Every other check still applies.
        """

        if ((expected_version is not None
                and (type(expected_version) is not int or expected_version < 0))
                or type(expected_epoch) is not int or expected_epoch < 1
                or not isinstance(expected_incarnation, str) or not expected_incarnation
                or type(step) is not int or step < 1
                or type(max_age_ns) is not int or max_age_ns < 1):
            raise ValueError("PHYSICS_COMMIT_ARGUMENT_INVALID")
        with self._lock:
            now_ns = _integer(self.clock_ns(), "readback_ns", 1)
            self._expire_deadlines(now_ns)
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if self.epoch is None or not self._first_chunk_seen:
                raise ValueError("PHYSICS_CLOCK_UNAVAILABLE")
            if expected_version is not None and self.version != expected_version:
                raise ValueError("PHYSICS_COMMIT_VERSION_CHANGED")
            if self.incarnation != expected_incarnation or self.epoch != expected_epoch:
                raise ValueError("PHYSICS_COMMIT_INCARNATION_CHANGED")
            # O(1) lookup through the step index maintained by the accept path;
            # the receipt is returned as a read-only view so it cannot be mutated.
            candidate = self._by_step.get(step)
            if candidate is None:
                if require_retained:
                    raise ValueError("PHYSICS_COMMIT_STEP_UNAVAILABLE")
                # Plan A19: a per-row guard of slow work (enforce_age=False callers) only needs the session, epoch,
                # incarnation and hazard checks above; the selection object already holds its own sample data and the
                # strict end-of-check fresh select() carries currency. No age can be computed for a step that has
                # left the retained window, so none is reported.
                return MappingProxyType({"version": self.version, "incarnation": self.incarnation,
                                         "epoch": self.epoch, "step": step, "age_ns": None,
                                         "commit_monotonic_ns": now_ns, "retained": False,
                                         "source_end_monotonic_ns": None})
            sample = candidate["sample"]
            age_ns = now_ns - sample.clock_interval_end_monotonic_ns
            # `enforce_age=False` (plan D8b) keeps every identity/epoch/retention check but not the age: slow work
            # (the path check, scene read-back) runs against one selection and freshness is re-established by a
            # fresh selection at the point of use. A negative age (clock regression) is still refused.
            if age_ns < 0 or (enforce_age and age_ns > max_age_ns):
                raise ValueError("PHYSICS_COMMIT_SELECTED_STALE")
            # a read-only view: the receipt cannot be mutated by its holder
            return MappingProxyType({"version": self.version, "incarnation": self.incarnation,
                                     "epoch": self.epoch, "step": step, "age_ns": age_ns,
                                     "commit_monotonic_ns": now_ns, "retained": True,
                                     "source_end_monotonic_ns":
                                         sample.clock_interval_end_monotonic_ns})

    def snapshot(self):
        """Versioned view of the current history state for commit revalidation."""

        with self._lock:
            return {"version": self.version, "session_id": self.session_id,
                    "incarnation": self.incarnation, "epoch": self.epoch,
                    "hazard": self.hazard,
                    "evidence_ready": (self.epoch is not None and self.hazard is None
                                       and self._first_chunk_seen)}

    def _expire_deadlines(self, now_ns):
        """Latch an expired first-chunk or silence deadline. Caller holds the lock.

        In audit mode the expiry is only recorded, once per quiet period, and the
        epoch stays open; availability is judged by the Teacher's own state health.
        """

        if self.epoch is None or self.hazard is not None:
            return
        if not self._first_chunk_seen:
            if (self.first_chunk_timeout_ns is not None
                    and now_ns - self._armed_monotonic_ns > self.first_chunk_timeout_ns):
                if self.audit_integrity:
                    self._note_deadline("PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT")
                    return
                # Hazard transitions from None exactly once, so the version
                # advances exactly once per real transition.
                self.hazard = "PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT"
                self.version += 1
        elif (self.max_silence_ns is not None
                and now_ns - self._last_source_end_ns > self.max_silence_ns):
            if self.audit_integrity:
                self._note_deadline("PHYSICS_CLOCK_SILENT")
                return
            self.hazard = "PHYSICS_CLOCK_SILENT"
            self.version += 1
            self._record_refusal("PHYSICS_CLOCK_SILENT", now_ns)

    def _note_deadline(self, reason):
        if not self._deadline_noted:
            self._deadline_noted = True
            self._audit(reason)

    def _stale(self, now_ns):
        """Report a readback that found no fresh sample; latch it only in strict mode."""

        if self.audit_integrity:
            if not self._stale_noted:
                self._stale_noted = True
                self._audit("PHYSICS_CLOCK_STALE")
        elif self.hazard is None:
            self.hazard = "PHYSICS_CLOCK_STALE"
            self.version += 1
        self._record_refusal("PHYSICS_CLOCK_STALE", now_ns)
        raise ValueError("PHYSICS_CLOCK_STALE")

    def accept_chunk(self, chunk, *, received_monotonic_ns=None):
        gaps = []
        try:
            return self._accept_chunk(chunk, received_monotonic_ns, gaps)
        finally:
            for gap in gaps:
                self._log_arrival_gap(gap)

    def _accept_chunk(self, chunk, received_monotonic_ns, gaps):
        audit = self.audit_integrity
        notes = []  # audit mode: completeness observations of an accepted chunk
        with self._lock:
            if self.epoch is None or self.hazard is not None:
                raise ValueError(self.hazard or "PHYSICS_CLOCK_UNARMED")
            now_ns = _integer(self.clock_ns(), "readback_ns", 1)
            # An expired deadline must close the epoch before acceptance updates
            # history, even if the owner never polled check_health().
            self._expire_deadlines(now_ns)
            if self.hazard is not None:
                raise ValueError(self.hazard)
            try:
                receipt_ns = (now_ns if received_monotonic_ns is None else
                              _integer(received_monotonic_ns, "receipt_ns", 1))
                if receipt_ns > now_ns:
                    raise ValueError("PHYSICS_RECEIPT_FUTURE")
                if not isinstance(chunk, PhysicsStepEvidenceChunk):
                    raise ValueError("PHYSICS_CHUNK_TYPE_INVALID")
                if (chunk.simulation_session_id != self.session_id
                        or chunk.reset_epoch != self.epoch):
                    # control identity: never audit-only
                    raise _IdentityRefused("PHYSICS_CHUNK_SCOPE_OR_LOSS")
                if (_integer(chunk.chunk_sequence, "chunk_sequence") !=
                           self._last_sequence + 1
                        or chunk.evidence_loss is not False
                        or _integer(chunk.failed_publish_attempts,
                                    "failed_publish_attempts") != 0):
                    if not audit:
                        raise ValueError("PHYSICS_CHUNK_SCOPE_OR_LOSS")
                    notes.append("PHYSICS_CHUNK_SCOPE_OR_LOSS")
                samples = chunk.samples
                step = self._last_step
                sim_ns = self._last_sim_ns
                if not samples:
                    raise ValueError("PHYSICS_CHUNK_STEP_GAP")
                first_step = _integer(chunk.first_physics_step, "first_physics_step", 1)
                last_step = _integer(chunk.last_physics_step, "last_physics_step", 1)
                if audit:
                    if last_step != first_step + len(samples) - 1 or first_step <= self._last_step:
                        # an inconsistent envelope, a duplicate or a backward step: nothing to keep
                        raise ValueError("PHYSICS_CHUNK_STEP_GAP")
                    if first_step != self._last_step + 1:
                        notes.append("PHYSICS_CHUNK_STEP_GAP")
                    step = first_step - 1  # resynchronise on this chunk's own numbering
                elif (first_step != self._last_step + 1
                        or last_step != self._last_step + len(samples)):
                    raise ValueError("PHYSICS_CHUNK_STEP_GAP")
                begin_previous = self._last_source_begin_ns
                end_previous = self._last_source_end_ns
                accepted = []
                for sample in samples:
                    step += 1
                    # Owned snapshot first: the callback message is borrowed for the
                    # duration of the callback only, so validation and retention must
                    # both apply to one private copy of the same bytes.
                    owned = copy.deepcopy(sample)
                    if (not isinstance(owned, PhysicsStepEvidence)
                            or owned.simulation_session_id != self.session_id
                            or owned.reset_epoch != self.epoch
                            or _integer(owned.physics_step, "physics_step", 1) != step
                            or len(owned.model_qpos) != self.nq
                            or len(owned.model_qvel) != self.nv
                            or any(not math.isfinite(value) for value in owned.model_qpos)
                            or any(not math.isfinite(value) for value in owned.model_qvel)):
                        raise ValueError("PHYSICS_SAMPLE_INVALID")
                    if owned.truncated is not False or owned.diagnostic_hazard_breached is not False:
                        if not audit:
                            raise ValueError("PHYSICS_SAMPLE_INVALID")
                        # The original keeps its markers for the force supervision and the
                        # selection; this history only records that they were seen.
                        if owned.truncated is not False:
                            notes.append("PHYSICS_SAMPLE_TRUNCATED")
                        if owned.diagnostic_hazard_breached is not False:
                            notes.append("PHYSICS_SAMPLE_HAZARD_MARKED")
                    current_sim_ns = _simulation_ns(owned.simulation_time_s)
                    if audit:
                        if current_sim_ns <= sim_ns:
                            raise ValueError("PHYSICS_SIMULATION_STEP_GAP")
                        if current_sim_ns - sim_ns != _STEP_NS:
                            notes.append("PHYSICS_SIMULATION_STEP_GAP")
                    elif current_sim_ns - sim_ns != _STEP_NS:
                        raise ValueError("PHYSICS_SIMULATION_STEP_GAP")
                    begin = _integer(owned.clock_interval_begin_monotonic_ns,
                                     "source_begin_ns", 1)
                    end = _integer(owned.clock_interval_end_monotonic_ns,
                                   "source_end_ns", 1)
                    clock_invalid = (begin < end_previous or end < begin or
                            end - begin > self.max_source_step_gap_ns or
                            begin_previous and
                            begin - begin_previous > self.max_source_step_gap_ns or
                            not 0 <= receipt_ns - end <= self.max_age_ns or
                            not 0 <= now_ns - end <= self.max_age_ns)
                    if clock_invalid:
                        if not audit:
                            raise ValueError("PHYSICS_SOURCE_CLOCK_INVALID")
                        notes.append("PHYSICS_SOURCE_CLOCK_INVALID")
                    accepted.append({
                        "sample": owned,
                        "received_monotonic_ns": receipt_ns,
                        "command_authority": False,
                    })
                    sim_ns = current_sim_ns
                    begin_previous = begin
                    end_previous = end
                if (_simulation_ns(chunk.first_simulation_time_s) !=
                        _simulation_ns(samples[0].simulation_time_s) or
                        _simulation_ns(chunk.last_simulation_time_s) != sim_ns):
                    if not audit:
                        raise ValueError("PHYSICS_CHUNK_TIME_ENVELOPE_INVALID")
                    notes.append("PHYSICS_CHUNK_TIME_ENVELOPE_INVALID")
                # Acceptance linearization point: validation and copying above can
                # take milliseconds, so the clock is resampled and both the health
                # deadlines and every accepted sample's freshness are revalidated
                # before any history state is committed.
                confirm_ns = _integer(self.clock_ns(), "readback_ns", 1)
                if confirm_ns < receipt_ns:
                    raise ValueError("PHYSICS_RECEIPT_FUTURE")
                self._expire_deadlines(confirm_ns)
                if self.hazard is not None:
                    raise ValueError(self.hazard)
                if any(not 0 <= confirm_ns - entry["sample"].clock_interval_end_monotonic_ns
                       <= self.max_age_ns for entry in accepted):
                    if not audit:
                        raise ValueError("PHYSICS_SOURCE_CLOCK_INVALID")
                    notes.append("PHYSICS_SOURCE_CLOCK_INVALID")
                previous_receipt_ns = self.last_accept_received_ns
                self._history.extend(accepted)
                try:
                    self.accepted_count += len(accepted)
                    self.last_accept_received_ns = receipt_ns
                    if (previous_receipt_ns is not None
                            and receipt_ns - previous_receipt_ns > _ARRIVAL_GAP_NS
                            and self._gap_lines < _ARRIVAL_GAP_LINES_PER_EPOCH):
                        self._gap_lines += 1
                        gaps.append({
                            "prev_received_ns": previous_receipt_ns,
                            "received_ns": receipt_ns,
                            "physics_step": accepted[-1]["sample"].physics_step,
                            "clock_interval_end_ns":
                                accepted[-1]["sample"].clock_interval_end_monotonic_ns})
                except Exception:
                    pass
                # rebuild the step index for the retained window (O(window), amortised
                # into the accept path) so the commit lookup is genuinely O(1)
                self._by_step = {entry["sample"].physics_step: entry
                                 for entry in self._history}
                self._last_sequence = chunk.chunk_sequence
                self._last_step = step
                self._last_sim_ns = sim_ns
                self._last_source_begin_ns = begin_previous
                self._last_source_end_ns = end_previous
                self._first_chunk_seen = True
                self._deadline_noted = False
                self._stale_noted = False
                self.version += 1
                for reason in dict.fromkeys(notes):
                    self._audit(reason)
                return True
            except (AttributeError, TypeError, ValueError, OverflowError) as error:
                try:
                    self.rejected_count += 1
                    self.last_rejection_reason = str(error)[:256]
                except Exception:
                    pass
                if audit and not isinstance(error, _IdentityRefused):
                    # Raw-stream completeness only: the chunk is not retained, nothing latches
                    # and the stream resynchronises on the next valid chunk.
                    self._audit(str(error))
                    return False
                if self.hazard is None:
                    self.version += 1
                self.hazard = str(error)
                raise ValueError("PHYSICS_CLOCK_HISTORY_INVALID") from error

    def retained_step_range(self):
        """(oldest, newest) retained raw physics step, or None before any raw chunk is retained."""
        with self._lock:
            if not self._by_step:
                return None
            return min(self._by_step), max(self._by_step)

    def source_end_ns(self, step):
        """Producer clock (`clock_interval_end_monotonic_ns`) of a retained physics step, else None.

        Used to age streams that carry no producer clock themselves (contacts) on producer time; a step
        that is not retained is unmappable and therefore never fresh.
        """
        with self._lock:
            entry = self._by_step.get(step)
            return None if entry is None else entry["sample"].clock_interval_end_monotonic_ns

    def recent_with_receipts(self):
        return self._recent_entries(copy.deepcopy)

    def recent_steps(self):
        """Return the physics steps `recent_with_receipts` would return, without copying.

        Same lock, hazard checks, deadline expiry, freshness filters and
        epoch-closing refusal as `recent_with_receipts` (one shared body), so a
        cheap readiness poll can never disagree with the full readback.
        """
        return tuple(entry["sample"].physics_step
                     for entry in self._recent_entries(None))

    def ready_steps(self):
        """Fresh physics steps for the readiness gate: never raises for an empty or stale window.

        Same lock, hazard checks and deadline expiry as `recent_steps`, but a window with no fresh sample is an
        empty answer ("not ready") instead of PHYSICS_CLOCK_UNAVAILABLE / PHYSICS_CLOCK_STALE, and it does not
        close the epoch or record a refusal: readiness is a gate, not a proof (plan A17). Point-of-use readbacks
        keep their strict `recent_with_receipts`.
        """
        with self._lock:
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if not self._history:
                return ()
            now_ns = _integer(self.clock_ns(), "readback_ns", 1)
            self._expire_deadlines(now_ns)
            if self.hazard is not None:
                raise ValueError(self.hazard)
            return tuple(entry["sample"].physics_step for entry in self._history
                         if 0 <= now_ns - entry["sample"].clock_interval_end_monotonic_ns
                         <= self.max_age_ns)

    def _recent_entries(self, copier):
        with self._lock:
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if not self._history:
                raise ValueError("PHYSICS_CLOCK_UNAVAILABLE")
            now_ns = _integer(self.clock_ns(), "readback_ns", 1)
            self._expire_deadlines(now_ns)
            if self.hazard is not None:
                raise ValueError(self.hazard)
            recent = tuple(entry if copier is None else copier(entry)
                           for entry in self._history
                           if 0 <= now_ns - entry["sample"].clock_interval_end_monotonic_ns
                           <= self.max_age_ns)
            if not recent:
                # Strict mode: a readback that finds no fresh sample closes the epoch;
                # raising alone would let a later chunk revive a stream that already
                # stalled. Audit mode records it and lets the next fresh chunk recover.
                self._stale(now_ns)
            # Readback linearization point: copying the window can cross a
            # deadline, so freshness and health are revalidated before returning.
            confirm_ns = _integer(self.clock_ns(), "readback_ns", 1)
            self._expire_deadlines(confirm_ns)
            if self.hazard is not None:
                raise ValueError(self.hazard)
            # A continuous stream always has an entry at the max_age edge, so a
            # slow copy ages out only the oldest entries. Return the suffix that
            # is still fresh at confirm time; refuse only when none remains.
            recent = tuple(entry for entry in recent
                           if 0 <= confirm_ns - entry["sample"].clock_interval_end_monotonic_ns
                           <= self.max_age_ns)
            if not recent:
                self._stale(confirm_ns)
            return recent

    @property
    def evidence_ready(self):
        """True only for an armed, hazard-free epoch with currently fresh evidence.

        This predicate never latches anything. An armed epoch without an accepted
        chunk is **not** ready even while `check_health()` is still True, because
        that verdict only means no deadline has expired yet; production must
        require this property before any sample, permit or goal is used.
        """
        with self._lock:
            if self.epoch is None or self.hazard is not None or not self._first_chunk_seen:
                return False
            now_ns = _integer(self.clock_ns(), "readback_ns", 1)
            if (self.max_silence_ns is not None
                    and now_ns - self._last_source_end_ns > self.max_silence_ns):
                return False
            return any(0 <= now_ns - entry["sample"].clock_interval_end_monotonic_ns
                       <= self.max_age_ns for entry in self._history)

    def check_health(self, *, now_ns=None):
        """Latch an expired health deadline and report whether the epoch is still open.

        True means only "armed and no deadline has expired yet". It is explicitly
        **not** evidence: before the first accepted chunk it says nothing about
        availability, and callers must require `evidence_ready` before using any
        sample, permit or goal.
        """
        with self._lock:
            if self.epoch is None or self.hazard is not None:
                return False
            now = _integer(self.clock_ns() if now_ns is None else now_ns, "readback_ns", 1)
            self._expire_deadlines(now)
            return self.hazard is None

    def step_at(self, physics_step, *, max_age_ns=None):
        """Return one isolated copy of a fresh retained step, not the whole window.

        Freshness, hazard latching and error semantics match
        `recent_with_receipts`; only the selected entry is deep-copied so a
        targeted read stays cheap on the executor. ``max_age_ns`` replaces the
        history age for this read only (the Teacher proofs use the Teacher state age).
        """
        step = _integer(physics_step, "physics_step", 1)
        limit_ns = self.max_age_ns if max_age_ns is None else _integer(max_age_ns, "max_age_ns", 1)
        with self._lock:
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if not self._history:
                raise ValueError("PHYSICS_CLOCK_UNAVAILABLE")
            now_ns = _integer(self.clock_ns(), "readback_ns", 1)
            self._expire_deadlines(now_ns)
            if self.hazard is not None:
                raise ValueError(self.hazard)
            any_fresh = False
            selected = None
            for entry in reversed(self._history):
                fresh = 0 <= now_ns - entry["sample"].clock_interval_end_monotonic_ns <= limit_ns
                any_fresh = any_fresh or fresh
                if fresh and entry["sample"].physics_step == step:
                    selected = {"sample": copy.deepcopy(entry["sample"]),
                                "received_monotonic_ns": entry["received_monotonic_ns"],
                                "command_authority": False}
                    break
            if selected is None:
                if not any_fresh:
                    self._stale(now_ns)
                raise ValueError("PHYSICS_CLOCK_STEP_UNAVAILABLE")
            # The copy above can cross a deadline; revalidate before returning.
            confirm_ns = _integer(self.clock_ns(), "readback_ns", 1)
            self._expire_deadlines(confirm_ns)
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if not (0 <= confirm_ns - selected["sample"].clock_interval_end_monotonic_ns
                    <= limit_ns):
                self._stale(confirm_ns)
            # (the STALE branch above and the no-fresh-sample branch below each
            # advance the version exactly once per real hazard transition)
            return selected
