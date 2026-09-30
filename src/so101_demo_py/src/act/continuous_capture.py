"""Continuous, causal capture at the 10 Hz sim-time grid.

One simulator owns motion and pixels; this module owns the cadence that turns those frames into
training rows. For each grid instant `t` it selects only inputs that were already causal for that
instant, binds the row to the *new* acquisition of each camera, verifies the recorded pixels against
those acquisitions' digests, and labels the row only from a controller reference that was accepted at
`t + 0.1 s` and whose acceptance is still valid once that instant has provably passed.

Rows keep their order. A row that cannot be labelled while a later row could be is a hole and fails the
run; only a genuinely terminal row, whose instant never received a legal reference, stays in the audit.
Callbacks never perform IO: `drain()` and the finalization step are the only places that write.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import math
import time

from .acquisition import Acquisition, AcquisitionGuard, pixel_digest
from .deadline import ACT_TIMEOUT_S

_TOLERANCE_S = 1e-6
_REFERENCE_SOURCE = "CONTROLLER_REFERENCE"
_STREAMS = ("head", "wrist")
# the observer's raw frame fields, forwarded to the audit when the observer supplies them
_RAW_REFERENCE_FIELDS = ("joint_names", "sim_stamp_ns", "received_monotonic_ns", "velocities")


@dataclass(frozen=True)
class CaptureSummary:
    """What a finished capture can report. There is deliberately no `committed` field."""

    sample_count: int
    label_cutoff_s: float
    audit_files: tuple


class ContinuousEpisodeCapture:
    def __init__(self, *, recorder, sampler, physical_audit, guard=None, audit_writer=None,
                 audit=None,
                 dt_s: float = 0.1, max_source_age_s: float = 0.1, max_skew_s: float = 0.0,
                 deadline_s: float = ACT_TIMEOUT_S, monotonic=time.monotonic,
                 frame_capacity: int = 8, reference_capacity: int = 128,
                 pending_capacity: int = 32) -> None:
        if dt_s != 0.1 or max_source_age_s != 0.1:
            raise ValueError("CAPTURE_GRID_INVALID")
        if isinstance(deadline_s, bool) or not isinstance(deadline_s, (int, float)) \
                or not math.isfinite(deadline_s) or not 0 < deadline_s <= ACT_TIMEOUT_S:
            # the motion budget is frozen at 120 s: no configuration may lengthen it
            raise ValueError("CAPTURE_DEADLINE_INVALID")
        if isinstance(max_skew_s, bool) or not isinstance(max_skew_s, (int, float)) \
                or not math.isfinite(max_skew_s) or max_skew_s < 0:
            raise ValueError("CAPTURE_GRID_INVALID")
        if not callable(monotonic):
            raise ValueError("CAPTURE_CLOCK_INVALID")
        if type(pending_capacity) is not int or pending_capacity < 1:
            raise ValueError("CAPTURE_GRID_INVALID")
        self.recorder = recorder
        self.sampler = sampler
        self.physical_audit = physical_audit
        self.audit_writer = audit_writer
        # the raw controller reference history goes to the episode audit when one is wired
        self.audit = audit
        self.guard = guard if guard is not None else AcquisitionGuard()
        self.dt_s = dt_s
        self.max_source_age_s = max_source_age_s
        self.max_skew_s = float(max_skew_s)
        self.deadline_s = float(deadline_s)
        self._monotonic = monotonic
        self._pending_capacity = pending_capacity
        self._reference_capacity = reference_capacity
        self._frames: dict = {camera: deque(maxlen=frame_capacity) for camera in _STREAMS}
        self._references: dict = {}
        self._pending: deque = deque()
        self._completed: list = []
        self._events: list = []
        self._session_id = None
        self._attempt_id = None
        self._reset_epoch = None
        self._next_grid_s = None
        self._physical_end_s = None
        self._observed_sim_s = None
        self._collection_start_s = None
        self._first_command_s = None
        self._reference_horizon_s = None
        self._last_labelled_target_s = None
        self._stopped_at_s = None
        self._deadline_started = None
        self._stopped = False
        self._finished = False
        self._failure = None
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
            self._reject("ACQUISITION_INVALID")
        if frame.session_id != self._session_id:
            self._reject("ACQUISITION_SESSION_MISMATCH")
        if frame.reset_epoch != self._reset_epoch:
            self._reject("ACQUISITION_RESET_MISMATCH")
        # the pixels are checked against the identity they claim, at receipt, not at selection; a
        # helper that refuses the array itself is the same terminal class of failure
        try:
            digest = pixel_digest(pixels)
        except ValueError as error:
            self._reject(str(error))
        if digest != frame.pixel_sha256:
            self._reject("ACQUISITION_PIXEL_MISMATCH")
        self._frames[frame.camera].append(frame)
        self._observe(frame.stamp_s)

    def on_reference(self, message) -> None:
        self._require_running()
        self._check_deadline()
        self._record_reference(message)

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
            if isinstance(event.get("sim_time_s"), (int, float)) \
                    and not isinstance(event.get("sim_time_s"), bool):
                self._first_command_s = float(event["sim_time_s"])
        self._check_deadline()
        if self._failure is not None:
            raise ValueError(self._failure)
        if self._stopped:
            raise ValueError("CAPTURE_STOPPED")
        sim_time_s = event.get("sim_time_s") if isinstance(event, dict) else None
        if isinstance(sim_time_s, (int, float)) and not isinstance(sim_time_s, bool):
            self._observe(float(sim_time_s))
        if kind == "stop":
            stop_s = float(sim_time_s) if isinstance(sim_time_s, (int, float)) \
                and not isinstance(sim_time_s, bool) else self._observed_sim_s
            if (stop_s is not None and self._last_labelled_target_s is not None
                    and stop_s <= self._last_labelled_target_s + _TOLERANCE_S):
                # a stop delivered after the label still voids that action instant
                self._fail("CAPTURE_LABEL_REVOKED")
            self._stopped = True
            self._stopped_at_s = stop_s
        self._events.append({"sequence": len(self._events) + 1, "kind": kind,
                             "sim_time_s": sim_time_s})

    # -- the only IO steps -------------------------------------------------

    def drain(self) -> int:
        self._require_running()
        self._check_deadline()
        if self._failure is not None:
            raise ValueError(self._failure)
        return self._service()

    def finish(self, physical_end_s) -> CaptureSummary:
        if self._session_id is None:
            raise ValueError("CAPTURE_NOT_STARTED")
        if self._finished:
            raise ValueError("CAPTURE_FINISHED")
        if isinstance(physical_end_s, bool) or not isinstance(physical_end_s, (int, float)) \
                or not math.isfinite(physical_end_s):
            raise ValueError("CAPTURE_IDENTITY_INVALID")
        if self._failure is not None:
            # a latched failure is never turned into a normal-looking summary
            raise ValueError(self._failure)
        if not self._stopped:
            # an on-time stop may finalize later; continued motion may not outlive its budget
            self._check_deadline()
        self._physical_end_s = float(physical_end_s)
        self._observe(self._physical_end_s)
        self._service()
        # the tail is handed off before finalization is declared, so a refusing writer leaves the
        # capture retryable and reported with its own reason instead of finished
        paths = tuple(self._tail_paths())
        self._finished = True
        return CaptureSummary(sample_count=self._written, label_cutoff_s=self.label_cutoff_s,
                              audit_files=paths)

    # -- views -------------------------------------------------------------

    @property
    def window(self) -> dict:
        """The observable collection window.

        Only facts this capture actually observed are reported; a fact that never happened is `None`
        rather than an invented instant, which is what lets a reader tell "no command was issued" and
        "nothing was labelled" apart from a real timestamp. The source schedule, cadence and permitted
        gaps come from the frozen inputs in the composition, not from here.
        """

        instants = [value for value in (self._observed_sim_s,) if value is not None]
        return {"collection_start_s": self._collection_start_s,
                "collection_end_s": max(instants) if instants else None,
                "first_command_s": self._first_command_s,
                "physics_end_s": self._physical_end_s,
                "label_cutoff_s": self.label_cutoff_s if self._written else None}

    @property
    def pending_rows(self) -> int:
        return len(self._pending)

    @property
    def unlabelled_rows(self) -> tuple:
        """The audit-only tail: rows whose instant never received a legal reference."""

        return tuple(dict(row["audit"]) for row in self._pending)

    @property
    def label_cutoff_s(self) -> float:
        return max((row["observation"]["sim_time_s"] for row in self._completed), default=0.0)

    # -- internals ---------------------------------------------------------

    def _require_running(self) -> None:
        if self._session_id is None:
            raise ValueError("CAPTURE_NOT_STARTED")
        if self._failure is not None:
            # a latched failure outranks the lifecycle state, so callers keep seeing the real reason
            raise ValueError(self._failure)
        if self._finished:
            raise ValueError("CAPTURE_FINISHED")
        if self._stopped:
            raise ValueError("CAPTURE_STOPPED")

    def _reason(self, error, default: str) -> str:
        text = str(error)
        return text if text else default

    def _reject(self, code: str):
        """A capture integrity failure is terminal: the first reason is kept and re-raised."""

        self._failure = code if self._failure is None else self._failure
        raise ValueError(self._failure)

    def _observe(self, sim_time_s: float) -> None:
        if self._collection_start_s is None or sim_time_s < self._collection_start_s:
            self._collection_start_s = float(sim_time_s)
        if self._observed_sim_s is None or sim_time_s > self._observed_sim_s:
            self._observed_sim_s = float(sim_time_s)

    def _check_deadline(self) -> None:
        if self._deadline_started is None:
            return
        if self._monotonic() - self._deadline_started > self.deadline_s:
            self._fail("CAPTURE_DEADLINE_EXCEEDED")

    def _fail(self, code: str):
        # the first reason is the one that explains the episode; a later deadline or lifecycle state
        # must not overwrite it
        self._failure = code if self._failure is None else self._failure
        raise ValueError(self._failure)

    def _record_reference(self, message) -> None:
        if not isinstance(message, dict) or message.get("source") != _REFERENCE_SOURCE:
            self._reject("CAPTURE_REFERENCE_INVALID")
        at_s = message.get("requested_sim_time_s")
        if isinstance(at_s, bool) or not isinstance(at_s, (int, float)) or not math.isfinite(at_s):
            self._reject("CAPTURE_REFERENCE_INVALID")
        positions = message.get("positions")
        if not isinstance(positions, (list, tuple)) or len(positions) != 6:
            self._reject("CAPTURE_REFERENCE_INVALID")
        try:
            values = [float(value) for value in positions]
        except (TypeError, ValueError):
            self._reject("CAPTURE_REFERENCE_INVALID")
        if any(not math.isfinite(value) for value in values):
            self._reject("CAPTURE_REFERENCE_INVALID")
        key = round(float(at_s), 6)
        accepted = message.get("accepted") is True
        if self.audit is not None:
            # every message is kept, acceptance and revocation alike, so the audit holds the raw
            # history the run actually received rather than only its final state; a refusing writer
            # is terminal like every other dependency
            raw = {name: message[name] for name in _RAW_REFERENCE_FIELDS if name in message}
            try:
                self.audit.append_source("references", {"reference_time_s": key,
                                                        "source": _REFERENCE_SOURCE,
                                                        "positions": values, "accepted": accepted,
                                                        **raw})
            except Exception as error:  # noqa: BLE001
                self._reject(self._reason(error, "CAPTURE_AUDIT_WRITE_FAILED"))
        if (not accepted and self._last_labelled_target_s is not None
                and key <= self._last_labelled_target_s + _TOLERANCE_S):
            # a trajectory revoked after its instant was labelled voids that label: an irreversible
            # recorder row may not be silently kept
            self._fail("CAPTURE_LABEL_REVOKED")
        existing = self._references.get(key)
        if existing is not None and existing["accepted"] and not accepted:
            # accepted then revoked before its instant: the label it would have given is void
            existing["accepted"] = False
            existing["revoked"] = True
        elif existing is None:
            if len(self._references) >= self._reference_capacity:
                self._fail("CAPTURE_REFERENCE_OVERFLOW")
            self._references[key] = {"positions": values,
                                     "accepted": accepted, "revoked": not accepted}
        self._reference_horizon_s = max(self._reference_horizon_s or 0.0, key)

    def _causal(self, camera: str, at_s: float):
        for frame in reversed(self._frames[camera]):
            if frame.stamp_s > at_s + _TOLERANCE_S:
                continue
            if at_s - frame.stamp_s > self.max_source_age_s + _TOLERANCE_S:
                return None
            return frame
        return None

    def _service(self) -> int:
        self._mint_rows()
        return self._service_pending()

    def _mint_rows(self) -> None:
        while True:
            at_s = round(self._next_grid_s, 6)
            if self._physical_end_s is not None and at_s > self._physical_end_s + _TOLERANCE_S:
                break
            head = self._causal("head", at_s)
            wrist = self._causal("wrist", at_s)
            if head is None or wrist is None:
                if not self._frames["head"] and not self._frames["wrist"]:
                    # both sources have run dry: a genuine terminal tail
                    break
                # a source still holds frames but cannot serve this instant with a new acquisition,
                # so the 10 Hz grid would have a hole before the label cutoff
                self._fail("NO_NEW_ACQUISITION")
            self._mint(at_s, head, wrist)
            self._frames["head"].remove(head)
            self._frames["wrist"].remove(wrist)
            self._next_grid_s = at_s + self.dt_s

    def _mint(self, at_s: float, head: Acquisition, wrist: Acquisition) -> None:
        try:
            self.guard.accept(head)
            self.guard.accept(wrist)
        except ValueError as error:
            # the guard's own refusal (reuse, regression) is terminal for the capture too
            self._reject(str(error))
        if abs(head.stamp_s - wrist.stamp_s) > self.max_skew_s + _TOLERANCE_S:
            self._fail("CAPTURE_SOURCE_SKEW")
        try:
            observation, source_audit = self.sampler.sample_with_audit(
                self._session_id, self._attempt_id, at_s)
        except Exception as error:  # noqa: BLE001 - a refusing dependency is terminal
            # the production synchronizer refuses with INPUT_STALE / INPUT_SKEW here
            self._reject(self._reason(error, "CAPTURE_SAMPLE_INVALID"))
        selected = source_audit.get("source_stamps", {})
        if (abs(selected.get("head", -1) - head.stamp_s) > _TOLERANCE_S
                or abs(selected.get("wrist", -1) - wrist.stamp_s) > _TOLERANCE_S):
            self._fail("ACQUISITION_SELECTION_MISMATCH")
        # the images the row will store must be the ones whose identity it carries
        for camera, frame in (("head", head), ("wrist", wrist)):
            try:
                selected_digest = pixel_digest(observation[camera])
            except (ValueError, TypeError, KeyError) as error:
                # the sampler's own image may be malformed: that failure latches like any other
                self._reject(str(error) or "CAPTURE_SAMPLE_INVALID")
            if selected_digest != frame.pixel_sha256:
                self._reject("ACQUISITION_PIXEL_MISMATCH")
        if len(self._pending) >= self._pending_capacity:
            self._fail("CAPTURE_PENDING_OVERFLOW")
        try:
            physical = self.physical_audit(at_s)
        except Exception as error:  # noqa: BLE001
            self._reject(self._reason(error, "CAPTURE_PHYSICAL_AUDIT_INVALID"))
        audit = dict(physical)
        audit.update(source_audit)
        audit.update({"head_acquisition_id": head.acquisition_id,
                      "wrist_acquisition_id": wrist.acquisition_id})
        self._pending.append({"observation": observation, "audit": audit,
                              "acquisitions": (head, wrist), "target_s": round(at_s + self.dt_s, 6),
                              "labelled": False, "reference": None})

    def _reference_state(self, row) -> str:
        """ready, waiting or void for one row's target instant.

        Absence is not proof: the observer's delivery can lag the sim clock, so a reference that has
        simply not arrived yet leaves the row waiting. Only an explicit revocation (or a stop before
        the instant) is void, and either way the row is a hole only once a later row can be labelled.
        """

        target = row["target_s"]
        if self._stopped_at_s is not None and self._stopped_at_s <= target + _TOLERANCE_S:
            return "void"
        entry = self._references.get(target)
        if entry is None:
            return "waiting"
        if not entry["accepted"]:
            return "void"
        if self._observed_sim_s is None or self._observed_sim_s <= target + _TOLERANCE_S:
            # accepted, but the instant has not passed: its acceptance could still be revoked
            return "waiting"
        return "ready"

    def _service_pending(self) -> int:
        written = 0
        while self._pending and self._reference_state(self._pending[0]) == "ready":
            row = self._pending[0]
            entry = self._references[row["target_s"]]
            audit = dict(row["audit"], reference_time_s=row["target_s"],
                         reference_source=_REFERENCE_SOURCE,
                         reference_positions=list(entry["positions"]))
            try:
                # the row leaves pending work only once the recorder accepted it, so a refusal
                # cannot silently drop evidence
                self.recorder.append(row["observation"], entry["positions"], audit)
            except Exception as error:  # noqa: BLE001 - a refusing writer is terminal
                self._reject(self._reason(error, "CAPTURE_RECORD_FAILED"))
            row["audit"] = audit
            row["reference"] = entry
            row["labelled"] = True
            self._pending.popleft()
            self._completed.append(row)
            self._written += 1
            self._last_labelled_target_s = row["target_s"]
            written += 1
        if self._pending:
            # an unresolved head is fine while its evidence may still arrive, but if a later row can
            # already be labelled the grid would have a hole before the label cutoff
            if any(self._reference_state(later) == "ready" for later in list(self._pending)[1:]):
                self._fail("CAPTURE_LABEL_GAP")
        # references that belong to rows already written are retired; a revocation for one of them
        # is still caught explicitly below rather than being dropped silently
        if self._last_labelled_target_s is not None:
            self._references = {key: value for key, value in self._references.items()
                                if key > self._last_labelled_target_s + _TOLERANCE_S}
        return written

    def _tail_paths(self) -> list:
        paths = []
        for row in self._pending:
            if self.audit_writer is None:
                continue
            try:
                paths.append(self.audit_writer(row["observation"], row["audit"]))
            except Exception as error:  # noqa: BLE001
                self._reject(self._reason(error, "CAPTURE_AUDIT_WRITE_FAILED"))
        return paths
