"""Continuous, causal capture at the 10 Hz sim-time grid.

One simulator owns motion and pixels; this module owns the cadence that turns those frames into
training rows. It selects, for each grid instant `t`, only inputs that were already causal for that
instant (`stamp <= t` and within the frozen source age), binds each row to the *new* acquisition of
each camera, and joins the row to the controller reference the run actually accepted at `t + 0.1 s`.
A row whose future reference never materialised stays in the audit; it is never given an invented
action.

Callbacks never perform IO: `on_acquisition`, `on_reference` and `on_event` only record. `drain()` is
the single place that mints and writes rows, so the action path never waits on a PNG write.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import time

from .acquisition import Acquisition, AcquisitionGuard
from .deadline import ACT_TIMEOUT_S

_TOLERANCE_S = 1e-6
_REFERENCE_SOURCE = "CONTROLLER_REFERENCE"


@dataclass(frozen=True)
class CaptureSummary:
    """What a finished capture can report. There is deliberately no `committed` field."""

    sample_count: int
    label_cutoff_s: float
    audit_files: tuple


class ContinuousEpisodeCapture:
    def __init__(self, *, recorder, sampler, physical_audit, guard=None, dt_s: float = 0.1,
                 max_source_age_s: float = 0.1, max_skew_s: float = 0.0,
                 deadline_s: float = ACT_TIMEOUT_S, monotonic=time.monotonic,
                 frame_capacity: int = 8, reference_capacity: int = 128) -> None:
        if dt_s != 0.1 or max_source_age_s != 0.1:
            raise ValueError("CAPTURE_GRID_INVALID")
        if isinstance(max_skew_s, bool) or not isinstance(max_skew_s, (int, float)) \
                or not math.isfinite(max_skew_s) or max_skew_s < 0:
            raise ValueError("CAPTURE_GRID_INVALID")
        if not callable(monotonic):
            raise ValueError("CAPTURE_CLOCK_INVALID")
        self.recorder = recorder
        self.sampler = sampler
        self.physical_audit = physical_audit
        self.guard = guard if guard is not None else AcquisitionGuard()
        self.dt_s = dt_s
        self.max_source_age_s = max_source_age_s
        self.max_skew_s = float(max_skew_s)
        self.deadline_s = float(deadline_s)
        self._monotonic = monotonic
        self._frame_capacity = frame_capacity
        self._reference_capacity = reference_capacity
        self._frames: dict = {camera: deque(maxlen=frame_capacity) for camera in ("head", "wrist")}
        self._references: deque = deque(maxlen=reference_capacity)
        self._events: list = []
        self._minted: list = []
        self._session_id = None
        self._attempt_id = None
        self._reset_epoch = None
        self._next_grid_s = None
        self._physical_end_s = None
        self._deadline_started = None
        self._stopped = False
        self._finished = False
        self._failed = False
        self._written = 0

    # -- lifecycle ---------------------------------------------------------

    def start(self, session_id, attempt_id, reset_epoch, start_s) -> None:
        if self._session_id is not None:
            raise ValueError("CAPTURE_ALREADY_STARTED")
        if not isinstance(session_id, str) or not session_id or not isinstance(attempt_id, str) \
                or not attempt_id:
            raise ValueError("CAPTURE_IDENTITY_INVALID")
        if type(reset_epoch) is not int or reset_epoch < 0:
            raise ValueError("CAPTURE_IDENTITY_INVALID")
        if isinstance(start_s, bool) or not isinstance(start_s, (int, float)) \
                or not math.isfinite(start_s) or start_s < 0:
            raise ValueError("CAPTURE_IDENTITY_INVALID")
        self._session_id = session_id
        self._attempt_id = attempt_id
        self._reset_epoch = reset_epoch
        self._next_grid_s = float(start_s)

    def on_acquisition(self, frame: Acquisition, pixels) -> None:
        self._require_running()
        self._check_deadline()
        if not isinstance(frame, Acquisition):
            raise ValueError("ACQUISITION_INVALID")
        if frame.session_id != self._session_id:
            raise ValueError("ACQUISITION_SESSION_MISMATCH")
        if frame.reset_epoch != self._reset_epoch:
            raise ValueError("ACQUISITION_RESET_MISMATCH")
        if frame.camera not in self._frames:
            raise ValueError("ACQUISITION_CAMERA_INVALID")
        self._frames[frame.camera].append(frame)

    def on_reference(self, message) -> None:
        self._require_running()
        self._check_deadline()
        if not isinstance(message, dict) or message.get("source") != _REFERENCE_SOURCE:
            raise ValueError("CAPTURE_REFERENCE_INVALID")
        at_s = message.get("requested_sim_time_s")
        if isinstance(at_s, bool) or not isinstance(at_s, (int, float)) or not math.isfinite(at_s):
            raise ValueError("CAPTURE_REFERENCE_INVALID")
        positions = message.get("positions")
        if not isinstance(positions, (list, tuple)) or len(positions) != 6:
            raise ValueError("CAPTURE_REFERENCE_INVALID")
        self._references.append({"requested_sim_time_s": float(at_s),
                                 "positions": [float(value) for value in positions],
                                 "accepted": message.get("accepted") is True,
                                 "received_monotonic_ns": int(self._monotonic() * 1e9)})

    def on_event(self, event) -> None:
        if self._session_id is None:
            raise ValueError("CAPTURE_NOT_STARTED")
        if self._finished:
            raise ValueError("CAPTURE_FINISHED")
        kind = event.get("kind") if isinstance(event, dict) else None
        if kind == "first_command":
            if self._deadline_started is not None:
                # the motion deadline starts once and is never reset
                raise ValueError("CAPTURE_DEADLINE_FIXED")
            self._deadline_started = self._monotonic()
        # the budget is checked before the stopped flag: a run past its deadline stops either way
        self._check_deadline()
        if self._stopped:
            raise ValueError("CAPTURE_STOPPED")
        if kind == "stop":
            self._stopped = True
        self._events.append({"sequence": len(self._events) + 1, "kind": kind,
                             "sim_time_s": event.get("sim_time_s") if isinstance(event, dict) else None})

    # -- the single IO step -------------------------------------------------

    def drain(self) -> int:
        self._require_running()
        self._check_deadline()
        return self._drain(strict=True)

    def finish(self, physical_end_s) -> CaptureSummary:
        if self._finished:
            raise ValueError("CAPTURE_FINISHED")
        if isinstance(physical_end_s, bool) or not isinstance(physical_end_s, (int, float)) \
                or not math.isfinite(physical_end_s):
            raise ValueError("CAPTURE_IDENTITY_INVALID")
        self._physical_end_s = float(physical_end_s)
        if not self._stopped:
            self._drain(strict=False)
        self._finished = True
        return CaptureSummary(sample_count=self._written,
                              label_cutoff_s=self.label_cutoff_s,
                              audit_files=tuple(self._audit_files()))

    # -- internals ---------------------------------------------------------

    @property
    def pending_rows(self) -> int:
        return sum(1 for row in self._minted if row["reference"] is None)

    @property
    def label_cutoff_s(self) -> float:
        return max((row["observation"]["sim_time_s"] for row in self._minted
                    if row["reference"] is not None), default=0.0)

    def _audit_files(self) -> list:
        return [row["audit"] for row in self._minted if row["reference"] is not None]

    def _require_running(self) -> None:
        if self._session_id is None:
            raise ValueError("CAPTURE_NOT_STARTED")
        if self._finished:
            raise ValueError("CAPTURE_FINISHED")
        if self._stopped:
            raise ValueError("CAPTURE_STOPPED")

    def _check_deadline(self) -> None:
        if self._deadline_started is None:
            return
        if self._monotonic() - self._deadline_started > self.deadline_s:
            self._failed = True
            raise ValueError("CAPTURE_DEADLINE_EXCEEDED")

    def _causal(self, camera: str, at_s: float):
        for frame in reversed(self._frames[camera]):
            if frame.stamp_s > at_s + _TOLERANCE_S:
                continue
            if at_s - frame.stamp_s > self.max_source_age_s + _TOLERANCE_S:
                return None
            return frame
        return None

    def _drain(self, *, strict: bool) -> int:
        written = 0
        while True:
            at_s = round(self._next_grid_s, 6)
            if self._physical_end_s is not None and at_s > self._physical_end_s + _TOLERANCE_S:
                break
            head = self._causal("head", at_s)
            wrist = self._causal("wrist", at_s)
            if head is None or wrist is None:
                if not self._frames["head"] and not self._frames["wrist"]:
                    # both sources have run dry: this is the tail, not a hole
                    break
                if strict:
                    # a source still holds something but cannot serve this instant with a new
                    # acquisition, so the 10 Hz grid would have a hole before the label cutoff
                    self._failed = True
                    raise ValueError("NO_NEW_ACQUISITION")
                break
            self._mint(at_s, head, wrist)
            written += self._complete(at_s)
            self._frames["head"].remove(head)
            self._frames["wrist"].remove(wrist)
            self._next_grid_s = at_s + self.dt_s
        return written

    def _mint(self, at_s: float, head: Acquisition, wrist: Acquisition) -> None:
        self.guard.accept(head)
        self.guard.accept(wrist)
        if abs(head.stamp_s - wrist.stamp_s) > self.max_skew_s + _TOLERANCE_S:
            raise ValueError("CAPTURE_SOURCE_SKEW")
        observation, source_audit = self.sampler.sample_with_audit(
            self._session_id, self._attempt_id, at_s)
        selected = source_audit.get("source_stamps", {})
        if (abs(selected.get("head", -1) - head.stamp_s) > _TOLERANCE_S
                or abs(selected.get("wrist", -1) - wrist.stamp_s) > _TOLERANCE_S):
            # the synchronizer must have selected exactly the acquisitions this row is bound to
            raise ValueError("ACQUISITION_SELECTION_MISMATCH")
        audit = dict(self.physical_audit(at_s))
        audit.update(source_audit)
        audit.update({"head_acquisition_id": head.acquisition_id,
                      "wrist_acquisition_id": wrist.acquisition_id})
        self._minted.append({"observation": observation, "audit": audit, "reference": None,
                             "acquisitions": (head, wrist)})

    def _complete(self, at_s: float) -> int:
        row = self._minted[-1]
        if row["observation"]["sim_time_s"] != at_s:
            return 0
        for message in reversed(self._references):
            if abs(message["requested_sim_time_s"] - (at_s + self.dt_s)) <= _TOLERANCE_S:
                if not message["accepted"]:
                    # the controller revoked this trajectory: it may not label the row
                    return 0
                row["reference"] = message
                break
        if row["reference"] is None:
            return 0
        audit = dict(row["audit"], reference_time_s=at_s + self.dt_s,
                     reference_source=_REFERENCE_SOURCE,
                     reference_positions=list(row["reference"]["positions"]))
        row["audit"] = audit
        self.recorder.append(row["observation"], row["reference"]["positions"], audit)
        self._written += 1
        return 1
