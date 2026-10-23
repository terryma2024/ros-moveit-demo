"""Worker-local ACT identity never enters the shared model wire."""

import importlib
import time
from types import SimpleNamespace as NS

import numpy as np
import pytest


def client_case():
    from so101_demo.parallel_batch.act_inference import ActInferenceFrame
    from so101_demo.parallel_batch.contracts.common import ExecutionKind
    module = importlib.import_module("so101_demo.runtime.act_teacher_client")
    lease = NS(batch_id="batch", coordinator_epoch=1, worker_id="worker", worker_generation=1,
        point_id="point", attempt_id="attempt", lease_generation=1)
    frame = ActInferenceFrame(np.arange(18, dtype=np.uint8).reshape(2, 3, 3), 1., 12_000_000_000,
                              "camera_optical", "session", "ros_sim", 1)
    context = dict(vars(lease), reset_epoch="reset-2", session_id="session")
    calls, starts = [], []
    def infer(request, payload):
        calls.append((request, payload))
        return {"schema_version": 1, "kind": "inference_response", "request_id": request["request_id"],
            "service_generation": "teacher-g1", "source_stamp_ns": 12_000_000_000,
            "source_frame_id": "camera_optical", "outcome": "NOT_DETECTED", "reason": "no cup",
            "batch": None, "timing": dict(received_monotonic_ns=1, queued_monotonic_ns=2,
                                        started_monotonic_ns=3, completed_monotonic_ns=4)}
    client = NS(generation="teacher-g1", new_request_id=lambda: "unique-r1", infer=infer)
    owner = module.ActTeacherClient(client=client, model_id="configured-model", weights_sha256="a"*64,
        resources=NS(worker_id="worker", generation=1, session_id="session"),
        classes={"0": "plastic_cup"}, query_class_id="plastic_cup", launch_generation=1,
        request_budget_s=0.5, context_probe=lambda *_args: context.copy(),
        perception_runner=lambda lease, kind, snapshot, send: send("configured-model", before_send=starts.append))
    def call():
        return owner.request_model(lease, ExecutionKind.ATTEMPT, snapshot=frame,
            start_event_id="attempt-start-attempt", start_event_type="ATTEMPT_STARTED", reset_epoch="reset-2")
    return NS(owner=owner, call=call, context=context, frame=frame, calls=calls, starts=starts,
              lease=lease, client=client)


def test_local_context_stays_local_and_rgb_is_original():
    h = client_case()
    result = h.call()
    wire, pixels = h.calls[0]
    assert set(wire) == {"schema_version", "kind", "request_id", "image", "query_class_id", "deadline_monotonic_ns"}
    assert pixels == bytes(range(18))
    assert result.request is h.starts[0]
    assert result.request.attempt_id == "attempt" and result.response["outcome"] == "NOT_DETECTED"
    assert not hasattr(result.request, "input_relative_path")


@pytest.mark.parametrize("field, value", [("worker_generation", 2), ("lease_generation", 2),
    ("reset_epoch", "reset-3"), ("session_id", "other"), ("attempt_id", "other")])
def test_stale_context_refused_before_any_wire_send(field, value):
    h = client_case()
    h.context[field] = value
    with pytest.raises(RuntimeError, match="ACT_TEACHER_CONTEXT_CHANGED"):
        h.call()
    assert h.calls == [] and h.starts == []


def test_late_context_change_cancels_local_result_without_altering_wire_outcome():
    from so101_demo.parallel_batch.contracts.common import ModelOutcome
    h = client_case()
    original = h.client.infer
    def changed(request, payload):
        response = original(request, payload)
        h.context["reset_epoch"] = "reset-3"
        return response
    h.client.infer = changed
    result = h.call()
    assert result.outcome is ModelOutcome.CANCELLED
    assert result.response["outcome"] == "NOT_DETECTED" and len(h.calls) == 1


def test_local_cancel_never_sends_service_reset_or_retries():
    h = client_case()
    assert h.owner.cancel_generation("worker", 1) is True
    with pytest.raises(RuntimeError, match="ACT_TEACHER_GENERATION_FENCED"):
        h.call()
    assert h.calls == []


def test_transport_error_is_one_call_and_no_retry():
    h = client_case()
    def broken(request, payload):
        h.calls.append((request, payload))
        raise ConnectionResetError("original failure")
    h.client.infer = broken
    with pytest.raises(ConnectionResetError, match="original failure"):
        h.call()
    assert len(h.calls) == 1


def test_budget_includes_local_registration_and_rgb_serialization():
    h = client_case()
    now = NS(ns=time.monotonic_ns())
    h.owner._clock = lambda: now.ns
    h.owner._request_budget_ns = 40_000_000
    def slow(request):
        h.starts.append(request)
        now.ns += 50_000_000
    h.owner.perception_runner = lambda lease, kind, snapshot, send: send("configured-model", before_send=slow)
    with pytest.raises(TimeoutError, match="ACT_TEACHER_REQUEST_DEADLINE"):
        h.call()
    assert h.calls == []
