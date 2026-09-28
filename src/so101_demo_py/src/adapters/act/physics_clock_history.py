"""Read-only source-clock history for complete MuJoCo physics samples."""

from __future__ import annotations

import copy
import math
import threading
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
                 first_chunk_timeout_s=None, clock_ns=time.monotonic_ns):
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
        self.clock_ns = clock_ns
        self._lock = threading.RLock()
        self._history = deque(maxlen=512)
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

    def latch(self, reason):
        if not isinstance(reason, str) or not reason:
            raise ValueError("PHYSICS_CLOCK_HAZARD_INVALID")
        with self._lock:
            self.hazard = self.hazard or reason

    def accept_chunk(self, chunk, *, received_monotonic_ns=None):
        with self._lock:
            if self.epoch is None or self.hazard is not None:
                raise ValueError(self.hazard or "PHYSICS_CLOCK_UNARMED")
            try:
                now_ns = _integer(self.clock_ns(), "readback_ns", 1)
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
                    if (not isinstance(sample, PhysicsStepEvidence)
                            or sample.simulation_session_id != self.session_id
                            or sample.reset_epoch != self.epoch
                            or _integer(sample.physics_step, "physics_step", 1) != step
                            or sample.truncated is not False
                            or sample.diagnostic_hazard_breached is not False
                            or len(sample.model_qpos) != self.nq
                            or len(sample.model_qvel) != self.nv
                            or any(not math.isfinite(value) for value in sample.model_qpos)
                            or any(not math.isfinite(value) for value in sample.model_qvel)):
                        raise ValueError("PHYSICS_SAMPLE_INVALID")
                    current_sim_ns = _simulation_ns(sample.simulation_time_s)
                    if current_sim_ns - sim_ns != _STEP_NS:
                        raise ValueError("PHYSICS_SIMULATION_STEP_GAP")
                    begin = _integer(sample.clock_interval_begin_monotonic_ns,
                                     "source_begin_ns", 1)
                    end = _integer(sample.clock_interval_end_monotonic_ns,
                                   "source_end_ns", 1)
                    if (begin < end_previous or end < begin or
                            end - begin > self.max_source_step_gap_ns or
                            begin_previous and
                            begin - begin_previous > self.max_source_step_gap_ns or
                            not 0 <= receipt_ns - end <= self.max_age_ns or
                            not 0 <= now_ns - end <= self.max_age_ns):
                        raise ValueError("PHYSICS_SOURCE_CLOCK_INVALID")
                    accepted.append({
                        "sample": copy.deepcopy(sample),
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
                self._history.extend(accepted)
                self._last_sequence = chunk.chunk_sequence
                self._last_step = step
                self._last_sim_ns = sim_ns
                self._last_source_begin_ns = begin_previous
                self._last_source_end_ns = end_previous
                self._first_chunk_seen = True
                return True
            except (AttributeError, TypeError, ValueError, OverflowError) as error:
                self.hazard = str(error)
                raise ValueError("PHYSICS_CLOCK_HISTORY_INVALID") from error

    def recent_with_receipts(self):
        with self._lock:
            if self.hazard is not None:
                raise ValueError(self.hazard)
            if not self._history:
                raise ValueError("PHYSICS_CLOCK_UNAVAILABLE")
            now_ns = _integer(self.clock_ns(), "readback_ns", 1)
            recent = tuple(copy.deepcopy(entry) for entry in self._history
                           if 0 <= now_ns - entry["sample"].clock_interval_end_monotonic_ns
                           <= self.max_age_ns)
            if not recent:
                # A readback that finds no fresh sample closes the epoch; raising
                # alone would let a later chunk revive a stream that already stalled.
                self.hazard = self.hazard or "PHYSICS_CLOCK_STALE"
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
        """Latch a bounded silence or first-chunk failure and report health.

        Returns True only while the armed epoch has produced at least one chunk
        and neither the configured silence bound nor the first-chunk deadline has
        been exceeded. The verdict is sticky: only a new arm clears it. Without
        explicit bounds no silence claim is made, so production wiring must
        supply them.
        """
        with self._lock:
            if self.epoch is None or self.hazard is not None:
                return False
            now = _integer(self.clock_ns() if now_ns is None else now_ns, "readback_ns", 1)
            if not self._first_chunk_seen:
                if (self.first_chunk_timeout_ns is not None
                        and now - self._armed_monotonic_ns > self.first_chunk_timeout_ns):
                    self.hazard = "PHYSICS_CLOCK_FIRST_CHUNK_TIMEOUT"
            elif (self.max_silence_ns is not None
                    and now - self._last_source_end_ns > self.max_silence_ns):
                self.hazard = "PHYSICS_CLOCK_SILENT"
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
            any_fresh = False
            for entry in reversed(self._history):
                fresh = 0 <= now_ns - entry["sample"].clock_interval_end_monotonic_ns <= self.max_age_ns
                any_fresh = any_fresh or fresh
                if fresh and entry["sample"].physics_step == step:
                    return {"sample": copy.deepcopy(entry["sample"]),
                            "received_monotonic_ns": entry["received_monotonic_ns"],
                            "command_authority": False}
            if not any_fresh:
                self.hazard = self.hazard or "PHYSICS_CLOCK_STALE"
                raise ValueError("PHYSICS_CLOCK_STALE")
            raise ValueError("PHYSICS_CLOCK_STEP_UNAVAILABLE")
