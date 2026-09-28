"""Read-only source-clock history for complete MuJoCo physics samples."""

from __future__ import annotations

import copy
import math
import threading
from types import MappingProxyType
import time
from collections import deque

from so101_mujoco_support.msg import PhysicsStepEvidence, PhysicsStepEvidenceChunk


_STEP_NS = 2_000_000


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
                 clock_ns=time.monotonic_ns):
        if not isinstance(session_id, str) or not session_id or not callable(clock_ns):
            raise ValueError("PHYSICS_CLOCK_CONFIG_INVALID")
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
        self._history = deque(maxlen=512)
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

    def arm(self, reset_epoch, *, source_floor_s):
        epoch = _integer(reset_epoch, "reset_epoch", 1)
        floor_ns = _simulation_ns(source_floor_s)
        with self._lock:
            if self.epoch is not None and epoch <= self.epoch:
                raise ValueError("PHYSICS_CLOCK_EPOCH_INVALID")
            self.epoch = epoch
            self.hazard = None
            self._history.clear()
            self._last_sequence = -1
            self._last_step = 0
            self._last_sim_ns = floor_ns
            self._last_source_begin_ns = 0
            self._last_source_end_ns = 0
            self._armed_monotonic_ns = _integer(self.clock_ns(), "readback_ns", 1)
            self._first_chunk_seen = False
            self.version += 1

    def latch(self, reason):
        if not isinstance(reason, str) or not reason:
            raise ValueError("PHYSICS_CLOCK_HAZARD_INVALID")
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
                       max_age_ns):
        """O(1) final commit primitive: one history lock, fresh time, full validation.

        This is the single linearization point for admission and authority claims.
        It reads its own monotonic time, latches any expired deadline/hazard inside
        the same lock, and validates the expected version/incarnation/epoch, the
        readiness of the epoch, the selected step and its selected-state age. It
        returns an immutable scalar receipt; no large copy happens under the lock.
        """

        if (type(expected_version) is not int or expected_version < 0
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
            if self.version != expected_version:
                raise ValueError("PHYSICS_COMMIT_VERSION_CHANGED")
            if self.incarnation != expected_incarnation or self.epoch != expected_epoch:
                raise ValueError("PHYSICS_COMMIT_INCARNATION_CHANGED")
            # bounded scan over the retained window (max 512 entries); the
            # receipt itself is returned as a read-only view, so this is *not*
            # claimed to be an O(1) lookup.
            for candidate in reversed(self._history):
                if candidate["sample"].physics_step == step:
                    break
            else:
                raise ValueError("PHYSICS_COMMIT_STEP_UNAVAILABLE")
            sample = candidate["sample"]
            age_ns = now_ns - sample.clock_interval_end_monotonic_ns
            if age_ns < 0 or age_ns > max_age_ns:
                raise ValueError("PHYSICS_COMMIT_SELECTED_STALE")
            # a read-only view: the receipt cannot be mutated by its holder
            return MappingProxyType({"version": self.version, "incarnation": self.incarnation,
                                     "epoch": self.epoch, "step": step, "age_ns": age_ns,
                                     "commit_monotonic_ns": now_ns,
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
        """Latch an expired first-chunk or silence deadline. Caller holds the lock."""

        if self.epoch is None or self.hazard is not None:
            return
        if not self._first_chunk_seen:
            if (self.first_chunk_timeout_ns is not None
                    and now_ns - self._armed_monotonic_ns > self.first_chunk_timeout_ns):
                # Hazard transitions from None exactly once, so the version
                # advances exactly once per real transition.
                self.hazard = "PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT"
                self.version += 1
        elif (self.max_silence_ns is not None
                and now_ns - self._last_source_end_ns > self.max_silence_ns):
            self.hazard = "PHYSICS_CLOCK_SILENT"
            self.version += 1

    def accept_chunk(self, chunk, *, received_monotonic_ns=None):
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
                        or chunk.reset_epoch != self.epoch
                        or _integer(chunk.chunk_sequence, "chunk_sequence") !=
                           self._last_sequence + 1
                        or chunk.evidence_loss is not False
                        or _integer(chunk.failed_publish_attempts,
                                    "failed_publish_attempts") != 0):
                    raise ValueError("PHYSICS_CHUNK_SCOPE_OR_LOSS")
                samples = chunk.samples
                if (not samples or
                        _integer(chunk.first_physics_step, "first_physics_step", 1) !=
                        self._last_step + 1 or
                        _integer(chunk.last_physics_step, "last_physics_step", 1) !=
                        self._last_step + len(samples)):
                    raise ValueError("PHYSICS_CHUNK_STEP_GAP")
                step = self._last_step
                sim_ns = self._last_sim_ns
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
                            or owned.truncated is not False
                            or owned.diagnostic_hazard_breached is not False
                            or len(owned.model_qpos) != self.nq
                            or len(owned.model_qvel) != self.nv
                            or any(not math.isfinite(value) for value in owned.model_qpos)
                            or any(not math.isfinite(value) for value in owned.model_qvel)):
                        raise ValueError("PHYSICS_SAMPLE_INVALID")
                    current_sim_ns = _simulation_ns(owned.simulation_time_s)
                    if current_sim_ns - sim_ns != _STEP_NS:
                        raise ValueError("PHYSICS_SIMULATION_STEP_GAP")
                    begin = _integer(owned.clock_interval_begin_monotonic_ns,
                                     "source_begin_ns", 1)
                    end = _integer(owned.clock_interval_end_monotonic_ns,
                                   "source_end_ns", 1)
                    if (begin < end_previous or end < begin or
                            end - begin > self.max_source_step_gap_ns or
                            begin_previous and
                            begin - begin_previous > self.max_source_step_gap_ns or
                            not 0 <= receipt_ns - end <= self.max_age_ns or
                            not 0 <= now_ns - end <= self.max_age_ns):
                        raise ValueError("PHYSICS_SOURCE_CLOCK_INVALID")
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
                    raise ValueError("PHYSICS_CHUNK_TIME_ENVELOPE_INVALID")
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
                    raise ValueError("PHYSICS_SOURCE_CLOCK_INVALID")
                self._history.extend(accepted)
                self._last_sequence = chunk.chunk_sequence
                self._last_step = step
                self._last_sim_ns = sim_ns
                self._last_source_begin_ns = begin_previous
                self._last_source_end_ns = end_previous
                self._first_chunk_seen = True
                self.version += 1
                return True
            except (AttributeError, TypeError, ValueError, OverflowError) as error:
                if self.hazard is None:
                    self.version += 1
                self.hazard = str(error)
                raise ValueError("PHYSICS_CLOCK_HISTORY_INVALID") from error

    def recent_with_receipts(self):
        with self._lock:
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if not self._history:
                raise ValueError("PHYSICS_CLOCK_UNAVAILABLE")
            now_ns = _integer(self.clock_ns(), "readback_ns", 1)
            self._expire_deadlines(now_ns)
            if self.hazard is not None:
                raise ValueError(self.hazard)
            recent = tuple(copy.deepcopy(entry) for entry in self._history
                           if 0 <= now_ns - entry["sample"].clock_interval_end_monotonic_ns
                           <= self.max_age_ns)
            if not recent:
                # A readback that finds no fresh sample closes the epoch; raising
                # alone would let a later chunk revive a stream that already stalled.
                if self.hazard is None:
                    self.hazard = "PHYSICS_CLOCK_STALE"
                    self.version += 1
                raise ValueError("PHYSICS_CLOCK_STALE")
            # Readback linearization point: copying the window can cross a
            # deadline, so freshness and health are revalidated before returning.
            confirm_ns = _integer(self.clock_ns(), "readback_ns", 1)
            self._expire_deadlines(confirm_ns)
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if any(not 0 <= confirm_ns - entry["sample"].clock_interval_end_monotonic_ns
                   <= self.max_age_ns for entry in recent):
                if self.hazard is None:
                    self.hazard = "PHYSICS_CLOCK_STALE"
                    self.version += 1
                raise ValueError("PHYSICS_CLOCK_STALE")
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

    def step_at(self, physics_step):
        """Return one isolated copy of a fresh retained step, not the whole window.

        Freshness, hazard latching and error semantics match
        `recent_with_receipts`; only the selected entry is deep-copied so a
        targeted read stays cheap on the executor.
        """
        step = _integer(physics_step, "physics_step", 1)
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
                fresh = 0 <= now_ns - entry["sample"].clock_interval_end_monotonic_ns <= self.max_age_ns
                any_fresh = any_fresh or fresh
                if fresh and entry["sample"].physics_step == step:
                    selected = {"sample": copy.deepcopy(entry["sample"]),
                                "received_monotonic_ns": entry["received_monotonic_ns"],
                                "command_authority": False}
                    break
            if selected is None:
                if not any_fresh:
                    if self.hazard is None:
                        self.hazard = "PHYSICS_CLOCK_STALE"
                        self.version += 1
                    raise ValueError("PHYSICS_CLOCK_STALE")
                raise ValueError("PHYSICS_CLOCK_STEP_UNAVAILABLE")
            # The copy above can cross a deadline; revalidate before returning.
            confirm_ns = _integer(self.clock_ns(), "readback_ns", 1)
            self._expire_deadlines(confirm_ns)
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if not (0 <= confirm_ns - selected["sample"].clock_interval_end_monotonic_ns
                    <= self.max_age_ns):
                if self.hazard is None:
                    self.hazard = "PHYSICS_CLOCK_STALE"
                    self.version += 1
                raise ValueError("PHYSICS_CLOCK_STALE")
            # (the STALE branch above and the no-fresh-sample branch below each
            # advance the version exactly once per real hazard transition)
            return selected
