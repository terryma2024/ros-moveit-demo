"""ACT Teacher adapter: local authorization context and the sole raw inference wire."""

from __future__ import annotations

import threading
import time

from so101_demo.parallel_batch.act_inference import (
    ActInferenceFrame, ActInferenceRequest, ActInferenceResult,
)
from so101_demo.parallel_batch.contracts.common import (
    ExecutionKind, _require_id, _require_positive_int, _require_sha256,
)
from so101_demo.runtime.inference.codec import pack_rgb


_LEASE_FIELDS = ("batch_id", "coordinator_epoch", "worker_id", "worker_generation",
                 "point_id", "attempt_id", "lease_generation")


class ActTeacherClient:
    def __init__(self, *, client, resources, model_id, weights_sha256, classes,
                 query_class_id, launch_generation, request_budget_s,
                 context_probe, perception_runner, monotonic_ns=time.monotonic_ns):
        _require_id("model_id", model_id)
        _require_sha256("weights_sha256", weights_sha256)
        _require_positive_int("launch_generation", launch_generation)
        if (type(request_budget_s) not in (int, float) or not 0 < request_budget_s < float("inf")
                or type(classes) is not dict or not classes
                or any(type(value) is not str for value in classes.values())
                or query_class_id not in {"cup", "plastic_cup"}
                or query_class_id not in classes.values()
                or not callable(context_probe) or not callable(perception_runner)):
            raise ValueError("ACT_TEACHER_CLIENT_CONFIG_INVALID")
        self.client, self.resources = client, resources
        self.model_id, self.weights_sha256 = model_id, weights_sha256
        self.classes, self.query_class_id = frozenset(classes.values()), query_class_id
        self.broker_generation = launch_generation
        self.service_generation = client.generation
        self.context_probe, self.perception_runner = context_probe, perception_runner
        self._clock = monotonic_ns
        self._request_budget_ns = int(request_budget_s * 1e9)
        self._request_lock = threading.Lock()
        self._fence_lock = threading.Lock()
        self._fenced = False

    def cancel_generation(self, worker_id, generation):
        """Fence this Worker locally; shared services never receive lease/reset controls."""
        if (worker_id, generation) != (self.resources.worker_id, self.resources.generation):
            return False
        with self._fence_lock:
            self._fenced = True
        return True

    def _is_fenced(self):
        with self._fence_lock:
            return self._fenced

    def request_model(self, lease, execution_kind, *, snapshot, start_event_id,
                      start_event_type, reset_epoch):
        if not self._request_lock.acquire(blocking=False):
            raise RuntimeError("ACT_TEACHER_REQUEST_PENDING")
        try:
            if self._is_fenced():
                raise RuntimeError("ACT_TEACHER_GENERATION_FENCED")
            expected_type = {ExecutionKind.ATTEMPT: "ATTEMPT_STARTED",
                             ExecutionKind.VALIDATION: "VALIDATION_STARTED"}.get(execution_kind)
            if (expected_type is None or start_event_type != expected_type
                    or type(start_event_id) is not str or not start_event_id):
                raise RuntimeError("ACT_TEACHER_LOCAL_START_REQUIRED")
            if (type(snapshot) is not ActInferenceFrame
                    or snapshot.simulation_session_id != self.resources.session_id
                    or (lease.worker_id, lease.worker_generation) != (
                        self.resources.worker_id, self.resources.generation)):
                raise RuntimeError("ACT_TEACHER_CONTEXT_CHANGED")
            expected = {field: getattr(lease, field) for field in _LEASE_FIELDS}
            expected.update(reset_epoch=reset_epoch, session_id=self.resources.session_id)
            probe = lambda: self.context_probe(lease, execution_kind, start_event_id, start_event_type)
            if probe() != expected:
                raise RuntimeError("ACT_TEACHER_CONTEXT_CHANGED")
            return self.perception_runner(lease, execution_kind, snapshot,
                lambda model_id, before_send: self._request_one(lease, execution_kind,
                    model_id=model_id, snapshot=snapshot, reset_epoch=reset_epoch,
                    expected=expected, probe=probe, before_send=before_send))
        finally:
            self._request_lock.release()

    def _request_one(self, lease, execution_kind, *, model_id, snapshot, reset_epoch,
                     expected, probe, before_send):
        if model_id != self.model_id:
            raise RuntimeError("ACT_TEACHER_MODEL_SEQUENCE")
        started = self._clock()
        deadline = started + self._request_budget_ns
        identity = {field: getattr(lease, field) for field in _LEASE_FIELDS if field != "attempt_id"}
        identity["attempt_id" if execution_kind is ExecutionKind.ATTEMPT else "validation_id"] = lease.attempt_id
        request = ActInferenceRequest(**identity, request_id=self.client.new_request_id(), model_id=model_id,
            execution_kind=execution_kind, reset_epoch=reset_epoch,
            image_timestamp_s=snapshot.source_stamp_ns / 1e9,
            source_stamp_ns=snapshot.source_stamp_ns, source_frame_id=snapshot.source_frame_id,
            image_shape=snapshot.shape, simulation_session_id=snapshot.simulation_session_id,
            frame_sequence=snapshot.sequence, service_generation=self.service_generation,
            deadline_monotonic_ns=deadline)
        before_send(request)
        image, payload = pack_rgb(snapshot.rgb8, stamp_ns=snapshot.source_stamp_ns,
                                  frame_id=snapshot.source_frame_id)
        if self._is_fenced() or probe() != expected:
            raise RuntimeError("ACT_TEACHER_CONTEXT_CHANGED")
        if self._clock() >= deadline:
            raise TimeoutError("ACT_TEACHER_REQUEST_DEADLINE")
        wire = self.client.infer({"schema_version": 1, "kind": "inference_request",
            "request_id": request.request_id, "image": image, "query_class_id": self.query_class_id,
            "deadline_monotonic_ns": deadline}, payload)
        completed = self._clock()
        if completed >= deadline:
            raise TimeoutError("ACT_TEACHER_REQUEST_DEADLINE")
        result = ActInferenceResult(request, self.broker_generation, wire, started, completed,
                                    cancelled=self._is_fenced() or probe() != expected)
        batch = result.candidate
        if batch is not None and (batch["weights_sha256"] != self.weights_sha256
                or any(item["class_id"] not in self.classes for item in batch["candidates"])):
            raise RuntimeError("ACT_TEACHER_MODEL_IDENTITY_MISMATCH")
        return result
