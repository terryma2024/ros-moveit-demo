"""
Bounded, thread-safe model scheduling; candidates never authorize motion.

The owner supplies current lease/start authorization and a monotonic host clock.
Model warmup, transport, input verification and GPU process recovery live in the
runtime adapter. Keep this instance for a batch; restart() advances its epoch.
A replacement process must receive the supervisor's new generation and reject
old transport envelopes before calling submit().
"""

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
import threading
import time

from .contracts import (
    _require_finite, _require_id, _require_positive_int, InferenceRequest,
    ModelOutcome, NormalizedInferenceResponseIdentity, ParallelRuntimeConfig,
)


@dataclass(frozen=True)
class ModelResult:
    """A runtime-classified model result; QUALIFIED is only a candidate."""

    outcome: ModelOutcome
    candidate: object = None
    reason: str | None = None


@dataclass(frozen=True)
class BrokerSubmission:
    """Stable admission receipt, with a terminal response when available."""

    accepted: bool
    reason: str | None = None
    response: object = None


class BrokerError(ValueError):
    """An invalid broker operation."""


@dataclass(frozen=True)
class BrokerResponse:
    """Attributed result and independent queue/inference timing evidence."""

    request: InferenceRequest
    broker_generation: int
    outcome: ModelOutcome
    candidate: object
    reason: str | None
    queued_monotonic_s: float
    queue_deadline_monotonic_s: float
    started_monotonic_s: float | None
    inference_deadline_monotonic_s: float | None
    completed_monotonic_s: float

    @property
    def identity(self):
        """Use the canonical response identity owned by contracts.py."""
        return NormalizedInferenceResponseIdentity.from_request(self.request)


@dataclass
class _Entry:
    request: InferenceRequest
    generation: int
    queued: float
    queue_deadline: float
    admission: BrokerSubmission
    started: float | None = None
    inference_deadline: float | None = None
    response: BrokerResponse | None = None


class PerceptionBroker:
    """Linearize admission, dispatch, completion and permanent fencing."""

    def __init__(self, config, *, grounded_model_id, authorize, clock=time.monotonic, generation=1,
                 detectors=None):
        """Bind the frozen model limits and injected host authorization ports."""
        if type(config) is not ParallelRuntimeConfig:
            raise BrokerError('RUNTIME_CONFIG_REQUIRED')
        _require_id('grounded_model_id', grounded_model_id)
        if grounded_model_id == config.yolo_model_id:
            raise BrokerError('DISTINCT_MODEL_IDS_REQUIRED')
        if not callable(authorize) or not callable(clock):
            raise BrokerError('CALLABLE_PORTS_REQUIRED')
        self._generation = _require_positive_int('broker_generation', generation)
        self._models = (config.yolo_model_id, grounded_model_id)
        self._queue_timeout = dict(zip(self._models, (
            config.yolo_queue_timeout_s, config.grounded_sam_queue_timeout_s)))
        self._inference_timeout = dict(zip(self._models, (
            config.yolo_inference_timeout_s, config.grounded_sam_inference_timeout_s)))
        self._capacity = config.broker_queue_capacity_per_model
        self._total_capacity = self._capacity * len(self._models)
        self._detectors = dict(detectors or {})
        if any(model not in self._models or not callable(detector)
               for model, detector in self._detectors.items()):
            raise BrokerError('MODEL_DETECTORS_REQUIRED')
        self._authorize, self._clock = authorize, clock
        self._lock = threading.RLock()
        self._ready = dict.fromkeys(self._models, False)
        self._queues = {model: {} for model in self._models}
        self._workers = {model: deque() for model in self._models}
        self._model_turns = deque(self._models)
        self._entries = {}
        self._inflight = {}
        self._fenced_generations = set()
        self._last_clock = None

    @property
    def generation(self):
        """Return the supervisor-visible generation, advanced only by restart."""
        with self._lock:
            return self._generation

    @property
    def healthy(self):
        """Both models must have passed runtime warmup/self-test."""
        with self._lock:
            return all(self._ready.values())

    def _now(self):
        try:
            now = _require_finite('monotonic_clock', self._clock())
        except Exception as error:
            self._clock_fault('MONOTONIC_CLOCK_INVALID')
            raise BrokerError('MONOTONIC_CLOCK_INVALID') from error
        if self._last_clock is not None and now < self._last_clock:
            self._clock_fault('MONOTONIC_CLOCK_REGRESSION')
            raise BrokerError('MONOTONIC_CLOCK_REGRESSION')
        self._last_clock = now
        return now

    def _clock_fault(self, reason):
        self._ready = dict.fromkeys(self._models, False)
        for entry in self._entries.values():
            if entry.response is None or entry.response.outcome is ModelOutcome.QUALIFIED:
                # The failed clock must not be sampled while invalidating work.
                self._finish(entry, ModelOutcome.INFRA_ERROR, reason,
                             completed=self._last_clock)

    def _lookup(self, request):
        if type(request) is not InferenceRequest:
            raise BrokerError('INFERENCE_REQUEST_REQUIRED')
        if request.model_id not in self._models:
            raise BrokerError('UNKNOWN_MODEL')
        entry = self._entries.get(request.request_id)
        if entry is not None and entry.request != request:
            raise BrokerError('REQUEST_IDENTITY_MISMATCH')
        return entry

    def _fenced(self, entry):
        request = entry.request
        return (entry.generation != self._generation or
                (request.worker_id, request.worker_generation) in self._fenced_generations)

    def _finish(self, entry, outcome, reason=None, candidate=None, *, completed=None,
                model_result=False):
        original_response = entry.response
        copied_candidate = None
        if outcome is ModelOutcome.QUALIFIED:
            try:
                copied_candidate = deepcopy(candidate)
            except Exception:
                if entry.response is not original_response:
                    return entry.response
                return self._copy_failure(entry)
            if entry.response is not original_response:
                return entry.response
        now = self._now() if completed is None else completed
        # Any callback may publish a result, not just a cancellation. The first
        # publication owns this completion; never replace it with an outer call.
        if entry.response is not original_response:
            return entry.response
        if model_result:
            # All model outcomes must survive the same final boundary. Broker
            # invalidations use their own explicit terminal reason instead.
            if self._fenced(entry):
                outcome, reason = ModelOutcome.CANCELLED, 'GENERATION_FENCED'
            elif not self.healthy:
                outcome, reason = ModelOutcome.INFRA_ERROR, 'BROKER_NOT_READY'
            elif now >= entry.inference_deadline:
                outcome, reason = ModelOutcome.INFERENCE_TIMEOUT, 'INFERENCE_DEADLINE_EXCEEDED'
        request = entry.request
        response = BrokerResponse(
            request, entry.generation, outcome,
            copied_candidate if outcome is ModelOutcome.QUALIFIED else None, reason,
            entry.queued, entry.queue_deadline, entry.started, entry.inference_deadline, now)
        # All fallible/callback work precedes this atomic terminal publication
        # and reservation release under the state lock.
        queue = self._queues[request.model_id]
        if request.worker_id in queue and request.request_id in queue[request.worker_id]:
            queue[request.worker_id].remove(request.request_id)
            if not queue[request.worker_id]:
                del queue[request.worker_id]
                self._workers[request.model_id].remove(request.worker_id)
        key = (request.worker_id, request.model_id)
        if self._inflight.get(key) == request.request_id:
            del self._inflight[key]
        entry.response = response
        return entry.response

    def _copy_failure(self, entry):
        if entry.response is None or entry.response.outcome is ModelOutcome.QUALIFIED:
            self._finish(entry, ModelOutcome.INFRA_ERROR, 'RESULT_COPY_FAILED')
        self.set_model_ready(entry.request.model_id, False)
        return entry.response

    def _guard(self, entry):
        # Terminal rejections never regain a candidate, even after recovery.
        if entry.response is not None and entry.response.outcome is not ModelOutcome.QUALIFIED:
            return
        if self._fenced(entry):
            self._finish(entry, ModelOutcome.CANCELLED, 'GENERATION_FENCED')
            return
        try:
            authorized = self._authorize(entry.request) is True
        except Exception:
            self._finish(entry, ModelOutcome.INFRA_ERROR, 'AUTHORIZATION_UNAVAILABLE')
            self.set_model_ready(entry.request.model_id, False)
            return
        # The callback may block or reenter restart/cancel; recheck state afterward.
        if self._fenced(entry):
            self._finish(entry, ModelOutcome.CANCELLED, 'GENERATION_FENCED')
        elif entry.response is not None and entry.response.outcome is not ModelOutcome.QUALIFIED:
            return
        elif not authorized:
            self._finish(entry, ModelOutcome.CANCELLED, 'REQUEST_NOT_AUTHORIZED')
        elif not self.healthy:
            self._finish(entry, ModelOutcome.INFRA_ERROR, 'BROKER_NOT_READY')
        elif entry.started is None and self._now() >= entry.queue_deadline:
            self._finish(entry, ModelOutcome.QUEUE_TIMEOUT, 'QUEUE_DEADLINE_EXCEEDED')
        elif entry.started is not None and self._now() >= entry.inference_deadline:
            self._finish(entry, ModelOutcome.INFERENCE_TIMEOUT, 'INFERENCE_DEADLINE_EXCEEDED')

    def set_model_ready(self, model_id, ready):
        """Runtime health loss invalidates every pending model request."""
        with self._lock:
            if model_id not in self._models or type(ready) is not bool:
                raise BrokerError('MODEL_READY_CONTRACT')
            self._ready[model_id] = ready
            if not ready:
                for entry in self._entries.values():
                    if (entry.response is None or
                            entry.response.outcome is ModelOutcome.QUALIFIED):
                        self._finish(entry, ModelOutcome.INFRA_ERROR, 'BROKER_NOT_READY')

    def _copy_response(self, entry):
        original = entry.response
        try:
            copied = deepcopy(original)
        except Exception:
            return self._copy_failure(entry)
        # No candidate copying or callback follows this final return guard.
        # Any invalidation replaces the immutable response with a candidate-free
        # terminal record, which is safe to return directly.
        self._guard(entry)
        return copied if entry.response is original else entry.response

    def submit(self, request):
        """Accept once or return the first rejection; never evict queued work."""
        with self._lock:
            entry = self._lookup(request)
            if entry is None:
                now = self._now()
                entry = _Entry(request, self._generation, now,
                               now + self._queue_timeout[request.model_id],
                               BrokerSubmission(False))
                self._entries[request.request_id] = entry
                self._guard(entry)
                if entry.response is None:
                    key = (request.worker_id, request.model_id)
                    counts = {model: sum(map(len, queue.values()))
                              for model, queue in self._queues.items()}
                    reason = ('WORKER_MODEL_INFLIGHT' if key in self._inflight else
                              'QUEUE_FULL' if counts[request.model_id] >= self._capacity or
                              sum(counts.values()) >= self._total_capacity else None)
                    if reason is None:
                        self._queues[request.model_id][request.worker_id] = deque(
                            (request.request_id,))
                        self._workers[request.model_id].append(request.worker_id)
                        self._inflight[key] = request.request_id
                        entry.admission = BrokerSubmission(True)
                    else:
                        self._finish(entry, ModelOutcome.INFRA_ERROR, reason)
                if entry.response is not None:
                    entry.admission = BrokerSubmission(False, entry.response.reason)
            else:
                self._guard(entry)
            response = self._copy_response(entry)
            if response is not None and response.outcome is ModelOutcome.CANCELLED:
                return BrokerSubmission(False, response.reason, response)
            return BrokerSubmission(entry.admission.accepted, entry.admission.reason, response)

    def next_ready_request(self):
        """Dispatch in model/Worker round-robin, after fresh lease/deadline checks."""
        with self._lock:
            for entry in tuple(self._entries.values()):
                if entry.response is None:
                    self._guard(entry)
            if not self.healthy:
                return None
            for _ in self._models:
                model = self._model_turns[0]
                self._model_turns.rotate(-1)
                workers = self._workers[model]
                while workers:
                    worker = workers[0]
                    entry = self._entries[self._queues[model][worker][0]]
                    self._guard(entry)
                    if entry.response is not None:
                        continue
                    started = self._now()
                    if entry.response is not None:
                        continue
                    if started >= entry.queue_deadline:
                        self._finish(entry, ModelOutcome.QUEUE_TIMEOUT,
                                     'QUEUE_DEADLINE_EXCEEDED', completed=started)
                        continue
                    workers.popleft()
                    self._queues[model][worker].popleft()
                    del self._queues[model][worker]
                    entry.started = started
                    entry.inference_deadline = entry.started + self._inference_timeout[model]
                    return entry.request
            return None

    def complete(self, request, result):
        """Return only current, timely results; duplicate completions cannot replace one."""
        with self._lock:
            entry = self._lookup(request)
            if entry is None:
                raise BrokerError('UNKNOWN_REQUEST')
            self._guard(entry)
            if entry.response is not None:
                return self._copy_response(entry)
            if entry.started is None:
                raise BrokerError('REQUEST_NOT_RUNNING')
            if (type(result) is not ModelResult or not isinstance(result.outcome, ModelOutcome)
                    or (result.outcome is ModelOutcome.QUALIFIED) !=
                    (result.candidate is not None)):
                self.set_model_ready(request.model_id, False)
                return self._copy_response(entry)
            self._finish(entry, result.outcome, result.reason, result.candidate, model_result=True)
            if entry.response.outcome is ModelOutcome.INFRA_ERROR:
                self.set_model_ready(request.model_id, False)
            # Copying a candidate can take time. Recheck the completion boundary
            # after ownership transfer, just as after the authorization callback.
            self._guard(entry)
            return self._copy_response(entry)

    def cancel_generation(self, worker_id, generation):
        """Permanently fence this Worker generation, including unseen request IDs."""
        _require_id('worker_id', worker_id)
        _require_positive_int('worker_generation', generation)
        with self._lock:
            self._fenced_generations.add((worker_id, generation))
            for entry in self._entries.values():
                if (entry.request.worker_id, entry.request.worker_generation) == (
                        worker_id, generation):
                    self._finish(entry, ModelOutcome.CANCELLED, 'GENERATION_FENCED')

    def restart(self):
        """Advance epoch and require both models to pass warmup again."""
        with self._lock:
            self._generation += 1
            self._ready = dict.fromkeys(self._models, False)
            for entry in self._entries.values():
                self._finish(entry, ModelOutcome.CANCELLED, 'GENERATION_FENCED')
            return self._generation

    def poll_response(self, request):
        """Poll terminal/audit evidence, expiring work even when no detector returns."""
        with self._lock:
            entry = self._lookup(request)
            if entry is None:
                raise BrokerError('UNKNOWN_REQUEST')
            self._guard(entry)
            return self._copy_response(entry)

    def run_next(self):
        """Run one injected detector outside the state lock; watchdogs stay responsive."""
        request = self.next_ready_request()
        if request is None:
            return None
        try:
            result = self._detectors[request.model_id](request)
        except Exception:
            result = ModelResult(ModelOutcome.INFRA_ERROR, reason='DETECTOR_RUNTIME_ERROR')
        return self.complete(request, result)
