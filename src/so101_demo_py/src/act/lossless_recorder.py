"""One bounded sample writer for the existing EpisodeRecorder, with no motion authority."""

from collections import deque
import copy
import threading
import time
import math

from .collection_config import validate_recorder_policy
from .deadline import ACT_TIMEOUT_S
from .exception_chain import chain_text
from .recorder import RecorderInfraError


class LosslessRecorderQueue:
    """Copy accepted original samples, preserve order and flush before any terminal seal.

    Capacity counts every accepted sample not yet written, including the active write. A sustained
    high watermark latches an infrastructure failure. Control progress observes that failure and
    owns the existing scoped stop; this writer never sends commands or opens another executor.
    """

    def __init__(self, recorder, *, policy, monotonic=time.monotonic):
        self.policy = validate_recorder_policy(policy)
        if not callable(monotonic):
            raise ValueError("RECORDER_QUEUE_CLOCK_INVALID")
        self.recorder = recorder
        self._clock = monotonic
        self._condition = threading.Condition()
        self._pending = deque()
        self._worker = None
        self._closing = False
        self._closed = False
        self._failure = None
        self._writer_error = None
        self._accepted = 0
        self._written = 0
        self._high_started = None
        self._backpressure_active = False
        self._peak = 0
        self._events = []

    @property
    def provenance(self):
        return self.recorder.provenance

    @property
    def root(self):
        return self.recorder.root

    @property
    def worker_alive(self):
        return self._worker is not None and self._worker.is_alive()

    def _event(self, kind):
        self._events.append({"sequence": len(self._events) + 1, "kind": kind,
            "monotonic_s": self._clock(), "accepted_samples": self._accepted,
            "written_samples": self._written, "outstanding_samples": self._accepted - self._written})

    def _fail(self, reason):
        if self._failure is None:
            self._failure = reason
            self._event(reason)
        self._condition.notify_all()

    def _watermark(self, *, transition_at=None):
        count = self._accepted - self._written
        boundary = self._clock() if transition_at is None else transition_at
        if (self._high_started is not None and boundary - self._high_started
                >= self.policy["queue_high_watermark_hold_s"]):
            self._fail("RECORDER_QUEUE_HIGH_WATERMARK")
        if count >= self.policy["queue_high_watermark_samples"] and self._high_started is None:
            self._high_started = self._events[-1]["monotonic_s"]
            self._backpressure_active = True
            self._event("high_watermark")
        elif count < self.policy["queue_high_watermark_samples"] and self._high_started is not None:
            self._event("below_high_watermark")
            self._high_started = None
        if count <= self.policy["queue_recovery_watermark_samples"] and self._backpressure_active:
            self._event("recovery_watermark")
            self._backpressure_active = False
        if (self._high_started is not None and self._clock() - self._high_started
                >= self.policy["queue_high_watermark_hold_s"]):
            self._fail("RECORDER_QUEUE_HIGH_WATERMARK")

    def check(self):
        with self._condition:
            self._watermark()
            if self._failure is not None:
                raise RecorderInfraError(self._failure)

    def append(self, observation, action, audit):
        # Copy before publishing the job to the writer. No caller-owned pixels or nested audit
        # values remain mutable through the queued reference.
        job = copy.deepcopy((observation, action, audit))
        with self._condition:
            self.check()
            if self._closing:
                raise RecorderInfraError("RECORDER_QUEUE_CLOSED")
            if self._accepted - self._written >= self.policy["queue_capacity_samples"]:
                self._fail("RECORDER_QUEUE_OVERFLOW")
                raise RecorderInfraError(self._failure)
            self._pending.append(job)
            self._accepted += 1
            self._peak = max(self._peak, self._accepted - self._written)
            self._event("accepted")
            self._watermark(transition_at=self._events[-1]["monotonic_s"])
            if self._worker is None:
                self._worker = threading.Thread(target=self._write, name="act-recorder-writer")
                self._worker.start()
            self._condition.notify_all()
            if self._accepted - self._written == self.policy["queue_capacity_samples"]:
                # The approved contract stops at the admission reaching 16. Retain that sample
                # and drain all accepted work; the terminal refusal cannot become a success seal.
                self._fail("RECORDER_QUEUE_OVERFLOW")
                raise RecorderInfraError(self._failure)

    def _write(self):
        while True:
            with self._condition:
                self._watermark()
                while not self._pending and not self._closing:
                    self._condition.wait()
                    self._watermark()
                if not self._pending:
                    return
                job = self._pending[0]
            try:
                self.recorder.append(*job)
            except Exception as error:  # A refused durable write can never be a business outcome.
                with self._condition:
                    self._writer_error = chain_text(error)    # the whole chain: the wrapper's cause is the point
                    self._fail("RECORDER_QUEUE_WRITE_FAILED")
                return
            with self._condition:
                self._pending.popleft()
                self._written += 1
                self._event("written")
                self._watermark(transition_at=self._events[-1]["monotonic_s"])
                self._condition.notify_all()

    def flush(self):
        deadline = time.monotonic() + ACT_TIMEOUT_S
        with self._condition:
            while self._written != self._accepted and self._writer_error is None:
                self.check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._fail("RECORDER_QUEUE_FLUSH_TIMEOUT")
                    break
                self._condition.wait(timeout=min(remaining, self.policy["queue_high_watermark_hold_s"]))
            self.check()

    def close(self):
        """Stop ingress and retain/drain accepted work even after a queue safety refusal."""
        with self._condition:
            self._closing = True
            self._condition.notify_all()
            worker = self._worker
        if worker is not None:
            worker.join(timeout=ACT_TIMEOUT_S)
        with self._condition:
            if worker is not None and worker.is_alive():
                self._fail("RECORDER_QUEUE_CLOSE_TIMEOUT")
                raise RecorderInfraError(self._failure)
            if not self._closed:
                self._closed = True
                self._event("closed")

    def snapshot(self):
        with self._condition:
            return {"kind": "ACT_LOSSLESS_RECORDER_QUEUE", "schema_version": 1,
                "policy": dict(self.policy), "accepted_samples": self._accepted,
                "written_samples": self._written, "outstanding_samples": self._accepted - self._written,
                "peak_samples": self._peak, "dropped_samples": 0, "failure": self._failure,
                "writer_error": self._writer_error, "closed": self._closed,
                "events": copy.deepcopy(self._events)}

    def finish(self, *args, **kwargs):
        self.flush()
        self.close()
        self.check()
        return self.recorder.finish(*args, **kwargs)


def verify_queue_evidence(document):
    """Reconstruct the complete versioned queue accounting from its original ordered events."""
    fields = {"kind", "schema_version", "policy", "accepted_samples", "written_samples",
        "outstanding_samples", "peak_samples", "dropped_samples", "failure", "writer_error",
        "closed", "events"}
    if (type(document) is not dict or set(document) != fields
            or document["kind"] != "ACT_LOSSLESS_RECORDER_QUEUE"
            or type(document["schema_version"]) is not int or document["schema_version"] != 1):
        raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
    policy = validate_recorder_policy(document["policy"])
    if (document["failure"] is not None or document["writer_error"] is not None
            or document["closed"] is not True or type(document["events"]) is not list):
        raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
    accepted = written = peak = 0
    previous_time = None
    high_since = None
    backpressure = False
    closed = False
    expected_markers = deque()
    event_fields = {"sequence", "kind", "monotonic_s", "accepted_samples", "written_samples",
                    "outstanding_samples"}
    for sequence, event in enumerate(document["events"], 1):
        if (type(event) is not dict or set(event) != event_fields or closed
                or type(event["sequence"]) is not int or event["sequence"] != sequence
                or type(event["monotonic_s"]) not in (float, int)
                or not math.isfinite(event["monotonic_s"]) or event["monotonic_s"] < 0
                or previous_time is not None and event["monotonic_s"] < previous_time):
            raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
        previous_time = event["monotonic_s"]
        if high_since is not None and previous_time - high_since >= policy["queue_high_watermark_hold_s"]:
            raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
        kind = event["kind"]
        if kind == "accepted":
            if expected_markers:
                raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
            accepted += 1
        elif kind == "written":
            if expected_markers:
                raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
            written += 1
        elif kind in ("high_watermark", "below_high_watermark", "recovery_watermark"):
            if not expected_markers or kind != expected_markers.popleft():
                raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
        elif kind == "closed":
            if expected_markers:
                raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
            closed = True
        else:
            raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
        outstanding = accepted - written
        if (not 0 <= outstanding < policy["queue_capacity_samples"]
                or any(type(event[key]) is not int for key in
                       ("accepted_samples", "written_samples", "outstanding_samples"))
                or (event["accepted_samples"], event["written_samples"], event["outstanding_samples"])
                    != (accepted, written, outstanding)):
            raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
        peak = max(peak, outstanding)
        if kind in ("accepted", "written"):
            if outstanding >= policy["queue_high_watermark_samples"] and high_since is None:
                high_since = previous_time
                backpressure = True
                expected_markers.append("high_watermark")
            elif outstanding < policy["queue_high_watermark_samples"] and high_since is not None:
                high_since = None
                expected_markers.append("below_high_watermark")
            if outstanding <= policy["queue_recovery_watermark_samples"] and backpressure:
                backpressure = False
                expected_markers.append("recovery_watermark")
    values = {"accepted_samples": accepted, "written_samples": written, "outstanding_samples": 0,
              "peak_samples": peak, "dropped_samples": 0}
    if (not closed or accepted != written or high_since is not None or backpressure
            or any(type(document[key]) is not int or document[key] != value for key, value in values.items())):
        raise ValueError("RECORDER_QUEUE_EVIDENCE_INVALID")
    return document
