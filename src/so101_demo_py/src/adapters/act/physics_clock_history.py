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


class PhysicsClockHistory:
    """Validate every source step without granting a goal or collection permit."""

    def __init__(self, session_id, *, nq, nv, max_age_s,
                 max_source_step_gap_ns, clock_ns=time.monotonic_ns):
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

    def accept_chunk(self, chunk):
        with self._lock:
            if self.epoch is None or self.hazard is not None:
                raise ValueError(self.hazard or "PHYSICS_CLOCK_UNARMED")
            try:
                receipt_ns = _integer(self.clock_ns(), "receipt_ns", 1)
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
                            not 0 <= receipt_ns - end <= self.max_age_ns):
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
                raise ValueError("PHYSICS_CLOCK_STALE")
            return recent

    def step_at(self, physics_step):
        step = _integer(physics_step, "physics_step", 1)
        for entry in reversed(self.recent_with_receipts()):
            if entry["sample"].physics_step == step:
                return entry
        raise ValueError("PHYSICS_CLOCK_STEP_UNAVAILABLE")
