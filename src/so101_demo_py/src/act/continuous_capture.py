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
import copy
import threading
from functools import wraps
import time
from pathlib import Path

from .acquisition import Acquisition, AcquisitionGuard, pixel_digest
from .deadline import ACT_TIMEOUT_S
from .synchronizer import source_age_ok_ns, time_ns

_TOLERANCE_S = 1e-6
_REFERENCE_SOURCE = "CONTROLLER_REFERENCE"
_STREAMS = ("head", "wrist")
# the observer's raw frame fields, forwarded to the audit when the observer supplies them
_RAW_REFERENCE_FIELDS = ("joint_names", "sim_stamp_ns", "received_monotonic_ns", "velocities")
# the ratified Proposal A shape; the two groups are alternatives and never travel together
# A.1 moved the evaluation inside each frame, so it is no longer a record-level key and forwarding
# it would be refused by the audit's closed schema
_PACKED_REFERENCE_FIELDS = ("frames", "projected_positions", "projection_map")


def _serialized(method):
    @wraps(method)
    def invoke(self, *args, **kwargs):
        with self._ingress_lock:
            return method(self, *args, **kwargs)
    return invoke


@dataclass(frozen=True)
class CaptureSummary:
    """What a finished capture can report. There is deliberately no `committed` field."""

    sample_count: int
    label_cutoff_s: float
    audit_files: tuple


_RECORDER_LOCAL_KEYS = frozenset({"head_acquisition_id", "wrist_acquisition_id"})


class ContinuousEpisodeCapture:
    def __init__(self, *, recorder, sampler, physical_audit, guard=None, audit_writer=None,
                 audit=None, scope=None,
                 dt_s: float = 0.1, max_source_age_s: float = 0.1, max_skew_s: float = 0.0,
                 deadline_s: float = ACT_TIMEOUT_S, monotonic=time.monotonic,
                 frame_capacity: int = 8, reference_capacity: int = 128,
                 pending_capacity: int = 32, asynchronous_sources: bool = False) -> None:
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
        if (type(frame_capacity) is not int or frame_capacity < 1
                or type(reference_capacity) is not int or reference_capacity < 1
                or type(asynchronous_sources) is not bool):
            raise ValueError("CAPTURE_GRID_INVALID")
        self.recorder = recorder
        self._ingress_lock = threading.RLock()
        self.sampler = sampler
        self.physical_audit = physical_audit
        self.audit_writer = audit_writer
        # the raw controller reference history goes to the episode audit when one is wired
        self.audit = audit
        #: the **path** of the scope document the freezer wrote - the recorder's `finish` requires an absolute
        #: regular file there and cross-checks it against the episode, while the audit writer was handed the
        #: document itself at construction (CP-2711/2712)
        self.scope = Path(scope) if scope is not None else None
        if self.scope is not None and (not self.scope.is_absolute() or ".." in self.scope.parts):
            raise ValueError("CAPTURE_SCOPE_INVALID")
        self.guard = guard if guard is not None else AcquisitionGuard()
        self.dt_s = dt_s
        self.max_source_age_s = max_source_age_s
        self.max_skew_s = float(max_skew_s)
        self.deadline_s = float(deadline_s)
        self._monotonic = monotonic
        self._pending_capacity = pending_capacity
        self._reference_capacity = reference_capacity
        self._raw_references = deque()
        self._reference_ordinal = 0
        self._asynchronous_sources = asynchronous_sources
        self._source_wait_started = None
        self._frames: dict = {camera: deque(maxlen=frame_capacity) for camera in _STREAMS}
        self._acquisition_audit_queue = deque()
        self._acquisition_audit_capacity = 2 * frame_capacity
        self._references: dict = {}
        self._pending: deque = deque()
        self._completed: list = []
        self._events: list = []
        self._session_id = None
        self._attempt_id = None
        self._reset_epoch = None
        self._next_grid_s = None
        self._next_grid_ns = None
        self._physical_end_s = None
        self._observed_sim_s = None
        self._collection_start_s = None
        self._first_command_s = None
        self._reference_horizon_s = None
        self._last_labelled_target_s = None
        self._stopped_at_s = None
        self._normal_end_clock = None
        self._deadline_started = None
        self._stopped = False
        self._finished = False
        self._failure = None
        self._written = 0

    # -- lifecycle ---------------------------------------------------------

    @_serialized
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
        self._next_grid_ns = time_ns(start_s)
        self._next_grid_s = self._next_grid_ns / 1e9

    @_serialized
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
        if len(self._frames[frame.camera]) >= self._frames[frame.camera].maxlen:
            self._fail("CAPTURE_ACQUISITION_OVERFLOW")
        if self.audit is not None:
            if len(self._acquisition_audit_queue) >= self._acquisition_audit_capacity:
                self._fail("CAPTURE_ACQUISITION_OVERFLOW")
            # Retain original identities, including frames never selected for a label.
            # IO remains in the existing drain path, outside the camera callback.
            self._acquisition_audit_queue.append(frame)
        self._frames[frame.camera].append(frame)
        self._observe(frame.stamp_s)

    @_serialized
    def on_reference(self, message) -> None:
        self._require_running()
        self._check_deadline()
        self._record_reference(message)

    @_serialized
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
            now=self._monotonic()
            original=event.get('source_clock')
            if original is not None:
                from .native_endpoints import validate_source_clock
                try:
                    validate_source_clock(original)
                    if (original['end_monotonic_ns']>round(now*1e9)
                            or round(event['sim_time_s']*1e9)!=original['sim_time_ns']):
                        raise ValueError('mapping')
                except (ValueError,KeyError,TypeError) as error:
                    self._fail('CAPTURE_DISPATCH_CLOCK_INVALID')
                    raise ValueError('CAPTURE_DISPATCH_CLOCK_INVALID') from error
                self._deadline_started=original['begin_monotonic_ns']/1e9
            else:
                self._deadline_started=now
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

    @_serialized
    def on_normal_motion_end(self, source_clock):
        """Fixed confirmed motion end; original ingress remains open for the endpoint tail.

        The existing owner supplies its independently confirmed normal-stop clock.
        This is bookkeeping, and grants no command or stopping authority.
        """
        self._require_running()
        self._check_deadline()
        if self._normal_end_clock is not None:
            self._fail('CAPTURE_NORMAL_END_FIXED')
        from .native_endpoints import validate_source_clock
        try:
            validate_source_clock(source_clock)
            if (source_clock['end_monotonic_ns']>round(self._monotonic()*1e9)
                    or self._first_command_s is None
                    or source_clock['sim_time_ns']/1e9<self._first_command_s):
                raise ValueError('mapping')
        except (ValueError,TypeError,KeyError) as error:
            self._fail('CAPTURE_NORMAL_END_INVALID')
            raise ValueError('CAPTURE_NORMAL_END_INVALID') from error
        when=source_clock['sim_time_ns']/1e9
        if self._last_labelled_target_s is not None and when<=self._last_labelled_target_s+_TOLERANCE_S:
            self._fail('CAPTURE_LABEL_REVOKED')
        self._normal_end_clock=dict(source_clock)
        self._stopped_at_s=self._physical_end_s=when
        self._observe(when)

    @_serialized
    def drain(self) -> int:
        self._require_running()
        self._check_deadline()
        if self._failure is not None:
            raise ValueError(self._failure)
        return self._service()

    @_serialized
    def reference_requests(self, through_s):
        """Expose due unserved row targets without advancing or relabelling any row."""
        self._require_running()
        if type(through_s) not in (int, float) or not math.isfinite(through_s) or through_s < 0:
            raise ValueError("CAPTURE_REFERENCE_CLOCK_INVALID")
        self._check_deadline()
        if self._failure is not None:
            raise ValueError(self._failure)
        return tuple(row["target_s"] for row in self._pending
                     if round(row["target_s"] * 1e9) <= round(through_s * 1e9)
                     and (self._normal_end_clock is None or row['target_s']<self._stopped_at_s-_TOLERANCE_S)
                     and row["target_s"] not in self._references)

    @_serialized
    def reject_source(self, reason: str) -> None:
        """Latch an actual producer refusal so later good input cannot restore collection."""
        if not isinstance(reason, str) or not reason:
            raise ValueError("CAPTURE_SOURCE_HAZARD_INVALID")
        self._reject(reason)

    @_serialized
    def check_health(self) -> None:
        if self._failure is not None:
            raise ValueError(self._failure)
        self._check_deadline()
        if hasattr(self.recorder, "check"):
            self.recorder.check()

    @_serialized
    def on_source_clock(self, sim_time_s: float) -> None:
        self._require_running()
        if type(sim_time_s) not in (int, float) or not math.isfinite(sim_time_s) or sim_time_s < 0:
            self._fail("CAPTURE_SOURCE_CLOCK_INVALID")
        self._observe(float(sim_time_s))

    @property
    def started(self) -> bool:
        return self._session_id is not None

    @property
    def active(self) -> bool:
        return self._session_id is not None and not self._finished and not self._stopped

    @property
    def ingress_lock(self):
        return self._ingress_lock

    @_serialized
    def finish(self, physical_end_s, *, window=None, outcome=None, derive_window=False) -> CaptureSummary:
        failure = None
        try:
            return self._finish(physical_end_s, window=window, outcome=outcome,
                                derive_window=derive_window)
        except BaseException as error:
            failure = error
            raise
        finally:
            if hasattr(self.recorder, "close"):
                try:
                    self.recorder.close()
                except Exception as error:
                    if failure is None:
                        raise
                    failure.add_note("Owned Recorder close also failed: " + str(error))

    def _finish(self, physical_end_s, *, window=None, outcome=None, derive_window=False) -> CaptureSummary:
        if type(derive_window) is not bool or (derive_window and (window is not None or self.audit is None)):
            raise ValueError("CAPTURE_WINDOW_INVALID")
        if self._session_id is None:
            raise ValueError("CAPTURE_NOT_STARTED")
        if self._finished:
            raise ValueError("CAPTURE_FINISHED")
        if isinstance(physical_end_s, bool) or not isinstance(physical_end_s, (int, float)) \
                or not math.isfinite(physical_end_s):
            raise ValueError("CAPTURE_IDENTITY_INVALID")
        if self._normal_end_clock is not None and round(physical_end_s*1e9)!=self._normal_end_clock['sim_time_ns']:
            self._fail('CAPTURE_NORMAL_END_CHANGED')
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
        if derive_window:
            window = self.audit.observed_collection_window(self.window, cadence_s=self.dt_s)
        # a v2 episode binds its raw audit and the scope it was collected under, so when those are supplied the
        # audit is sealed here and the recorder is finished with both - and when they are not, nothing changes
        if self.audit is not None and window is not None:
            if hasattr(self.recorder, "flush"):
                self.recorder.flush()
                self.recorder.close()
                self.recorder.check()
                self.audit.append_recorder_queue(self.recorder.snapshot(), sim_time_s=float(physical_end_s))
            audit_manifest = self.audit.seal(window)
            if self.recorder is not None and self.scope is not None and outcome is not None:
                self.recorder.finish(outcome, audit_manifest=audit_manifest, scope=self.scope)
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
        if self._deadline_started is None or self._normal_end_clock is not None:
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
        if isinstance(at_s, bool) or not isinstance(at_s, (int, float)) or not math.isfinite(at_s) or at_s < 0:
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
        key = time_ns(at_s) / 1e9
        accepted = message.get("accepted") is True
        if self.audit is not None:
            # every message is kept, acceptance and revocation alike, so the audit holds the raw
            # history the run actually received rather than only its final state; a refusing writer
            # is terminal like every other dependency
            raw = {name: message[name] for name in (*_RAW_REFERENCE_FIELDS,
                                                     *_PACKED_REFERENCE_FIELDS) if name in message}
            if len(self._raw_references) >= self._reference_capacity:
                self._fail("CAPTURE_REFERENCE_OVERFLOW")
            self._raw_references.append(copy.deepcopy({"reference_time_s": key,
                "source": _REFERENCE_SOURCE, "positions": values, "accepted": accepted, **raw}))
        # The reference sequence names the raw stream ordinal, including repeated and revoked
        # publications. It is never derived from the number of distinct action instants.
        self._reference_ordinal += 1
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
            self._references[key] = {"sequence": self._reference_ordinal, "positions": values,
                                     "accepted": accepted, "revoked": not accepted}
        self._reference_horizon_s = max(self._reference_horizon_s or 0.0, key)

    def _causal(self, camera: str, at_s: float):
        at_ns = time_ns(at_s)
        for frame in reversed(self._frames[camera]):
            stamp_ns = time_ns(frame.stamp_s)
            if stamp_ns > at_ns:
                continue
            if not source_age_ok_ns(at_ns, stamp_ns, time_ns(self.max_source_age_s)):
                return None
            return frame
        return None

    def _service(self) -> int:
        while self._acquisition_audit_queue:
            try:
                self.audit.append_acquisition(self._acquisition_audit_queue[0])
            except Exception as error:  # noqa: BLE001
                self._reject(self._reason(error, "CAPTURE_AUDIT_WRITE_FAILED"))
            self._acquisition_audit_queue.popleft()
        while self._raw_references:
            try:
                self.audit.append_source("references", self._raw_references[0])
            except Exception as error:  # noqa: BLE001
                self._reject(self._reason(error, "CAPTURE_AUDIT_WRITE_FAILED"))
            self._raw_references.popleft()
        self._mint_rows()
        return self._service_pending()

    def _mint_rows(self) -> None:
        while True:
            at_s = self._next_grid_ns / 1e9
            if self._physical_end_s is not None and at_s > self._physical_end_s + _TOLERANCE_S:
                break
            head = self._causal("head", at_s)
            wrist = self._causal("wrist", at_s)
            if head is None or wrist is None:
                if self._asynchronous_sources and self._physical_end_s is None:
                    if self._observed_sim_s is None or self._observed_sim_s < at_s - _TOLERANCE_S:
                        break  # No actual source has established eligibility for this next slot.
                    # Ordered camera delivery can still supply the original missing partner.
                    # Once that camera has advanced beyond this grid instant, no future callback
                    # can supply a causal frame. Otherwise retain this exact grid slot for <=.1s.
                    missing = (camera for camera, frame in (("head", head), ("wrist", wrist))
                               if frame is None)
                    if any(self._frames[camera]
                           and self._frames[camera][-1].stamp_s > at_s + _TOLERANCE_S
                           for camera in missing):
                        self._fail("NO_NEW_ACQUISITION")
                    if self._source_wait_started is None:
                        self._source_wait_started = self._monotonic()
                    if self._monotonic() - self._source_wait_started > self.max_source_age_s:
                        self._fail("NO_NEW_ACQUISITION")
                    break
                if not self._frames["head"] and not self._frames["wrist"]:
                    # both sources have run dry: a genuine terminal tail
                    break
                # a source still holds frames but cannot serve this instant with a new acquisition,
                # so the 10 Hz grid would have a hole before the label cutoff
                self._fail("NO_NEW_ACQUISITION")
            if self._asynchronous_sources and not self._sources_ready(at_s):
                if self._awaiting_arrival(at_s):
                    # A source is still IN FLIGHT (CP-3410: a late physics chunk is no failure). Its arrival is bounded by the
                    # receiver-lag policy of the adapter that owns it, not by this wall-clock wait.
                    self._source_wait_started = None
                    break
                if self._source_wait_started is None:
                    self._source_wait_started = self._monotonic()
                if (self._physical_end_s is not None
                        or self._monotonic() - self._source_wait_started > self.max_source_age_s):
                    self._fail("INPUT_STALE")
                break
            self._source_wait_started = None
            self._mint(at_s, head, wrist)
            self._frames["head"].remove(head)
            self._frames["wrist"].remove(wrist)
            self._next_grid_ns += time_ns(self.dt_s)
            self._next_grid_s = self._next_grid_ns / 1e9

    def _awaiting_arrival(self, at_s) -> bool:
        hook = getattr(self.physical_audit, "awaiting_arrival", None)
        if hook is None:
            return False
        try:
            return hook(at_s) is True
        except Exception:  # noqa: BLE001 - a hook that fails is "not in flight": the ordinary wait applies
            return False

    def _sources_ready(self, at_s):
        for source in (self.sampler, self.physical_audit):
            ready = getattr(source, "ready", None)
            if ready is None:
                continue
            try:
                available = ready(at_s)
                if type(available) is not bool:
                    raise ValueError("CAPTURE_SOURCE_READINESS_INVALID")
            except Exception as error:
                self._reject(self._reason(error, "CAPTURE_PHYSICAL_AUDIT_INVALID"))
            if not available:
                return False
        return True

    def _mint(self, at_s: float, head: Acquisition, wrist: Acquisition) -> None:
        try:
            self.guard.accept(head)
            self.guard.accept(wrist)
        except ValueError as error:
            # the guard's own refusal (reuse, regression) is terminal for the capture too
            self._reject(str(error))
        if abs(time_ns(head.stamp_s) - time_ns(wrist.stamp_s)) > time_ns(self.max_skew_s):
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
        # The recorder's closed audit set names the episode it belongs to; the physical half and the sampler do not supply
        # it, the capture owns it (CP-3407: without these two keys the first live row was refused with EPISODE_AUDIT_SCHEMA).
        audit.update({"head_acquisition_id": head.acquisition_id,
                      "wrist_acquisition_id": wrist.acquisition_id,
                      "session_id": self._session_id, "attempt_id": self._attempt_id})
        self._pending.append({"observation": observation, "audit": audit,
                              "acquisitions": (head, wrist), "target_s": (time_ns(at_s) + time_ns(self.dt_s)) / 1e9,
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
                # the recorder's audit channel is a closed sixteen-key set, while the acquisition identifiers
                # belong to the audit's row-bindings records (CP-2727/2728): the row keeps them for the audit
                # writer, and the recorder is handed the dictionary without them
                self.recorder.append(row["observation"], entry["positions"],
                                     {k: v for k, v in audit.items() if k not in _RECORDER_LOCAL_KEYS})
            except Exception as error:  # noqa: BLE001 - a refusing writer is terminal
                self._reject(self._reason(error, "CAPTURE_RECORD_FAILED"))
            index = self._written
            row["audit"] = audit
            row["reference"] = entry
            row["labelled"] = True
            self._pending.popleft()
            self._completed.append(row)
            self._written += 1
            if self.audit is not None and entry.get("sequence") is not None:
                # the seal requires every recorded row to be bound to the acquisitions it consumed, and that binding
                # goes to the episode's audit writer directly - `audit_writer` stays the tail's callback for the
                # evidence that never became a row (CP-2757/CP-2793)
                try:
                    self.audit.bind_row(index, row["observation"]["sim_time_s"],
                                        audit["head_acquisition_id"], audit["wrist_acquisition_id"],
                                        entry["sequence"])
                except Exception as error:  # noqa: BLE001
                    self._reject(self._reason(error, "CAPTURE_AUDIT_WRITE_FAILED"))
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
