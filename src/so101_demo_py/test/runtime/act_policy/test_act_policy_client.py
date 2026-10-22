"""The shard-side socket transport behind the unchanged `ActInferenceProcess` rules (fake policy service, no model, no GPU)."""

import threading
import time

import numpy as np
import pytest

from so101_demo.adapters.act.inference_process import ActInferenceProcess
from so101_demo.runtime.act_policy.client import PolicyClient, RemotePolicy, SocketInferenceTransport

from test_act_policy_service import BUNDLE, POLICY, Rig, observation

CONFIG = {"inference": {"device": "cuda", "request_timeout_s": 0.5, "max_reply_age_s": 0.3}}


def response(outcome="OK", sequence=1, **changes):
    timing = {"received_monotonic_ns": 1, "queued_monotonic_ns": 2, "started_monotonic_ns": 3, "completed_monotonic_ns": 4,
              "queue_wait_ms": 1.5, "inference_ms": 2.5, "inflight_at_receipt": 2}
    document = {"schema_version": 1, "kind": "policy_response", "request_id": "c-r1", "client_id": "c", "sequence": sequence,
                "observation_sim_s": 1.0, "service_generation": "gen-1", "bundle_sha256": BUNDLE, "policy_sha256": POLICY,
                "outcome": outcome, "reason": "" if outcome == "OK" else "WHY",
                "actions": [[0.1] * 6, [0.2] * 6] if outcome == "OK" else None, "timing": timing}
    document.update(changes)
    return document


class FakeClient:
    """Stands in for `PolicyClient`: `script` entries are a response, an exception, or a callable."""

    def __init__(self, script):
        self.script, self.calls = list(script), []

    def infer(self, observation, *, sequence, deadline_ns):
        self.calls.append((sequence, deadline_ns))
        item = self.script.pop(0)
        if callable(item):
            item = item(sequence)
        if isinstance(item, BaseException):
            raise item
        return dict(item, sequence=sequence)


def boundary(client, request_timeout_s=0.5):
    transport = SocketInferenceTransport(client, request_timeout_s=request_timeout_s)
    return ActInferenceProcess(config=CONFIG, transport=transport, clock=time.monotonic), transport


def wait_reply(process, limit=3.0):
    stop = time.monotonic() + limit
    while time.monotonic() < stop:
        reply = process.poll()
        if reply:
            return reply
        time.sleep(0.002)
    raise AssertionError("no reply")


def test_an_ok_answer_is_delivered_as_a_chunk_with_its_age_and_the_services_account():
    process, transport = boundary(FakeClient([response()]))
    process.submit(observation(), sequence=1)
    reply = wait_reply(process)
    assert reply["sequence"] == 1 and reply["actions"] == ((0.1,) * 6, (0.2,) * 6)
    assert 0 <= reply["age_s"] < 0.3
    assert reply["service"]["queue_wait_ms"] == 1.5 and reply["service"]["inference_ms"] == 2.5
    assert reply["service"]["outcome"] == "OK" and reply["service"]["bundle_sha256"] == BUNDLE
    assert process.last_service == reply["service"]
    process.close()


@pytest.mark.parametrize("outcome", ["QUEUE_FULL", "QUEUE_TIMEOUT", "INFERENCE_TIMEOUT"])
def test_a_service_refusal_is_a_stale_reply_not_a_command_and_not_a_fault(outcome):
    process, transport = boundary(FakeClient([response(outcome)]))
    process.submit(observation(), sequence=1)
    with pytest.raises(ValueError, match="INFERENCE_REPLY_STALE"):
        stop = time.monotonic() + 3
        while time.monotonic() < stop:
            process.poll()
            time.sleep(0.002)
    assert process.last_service["outcome"] == outcome
    process.abandon()
    process.close()


@pytest.mark.parametrize("outcome", ["MODEL_ERROR", "INPUT_INVALID", "INFRA_ERROR"])
def test_a_service_error_is_an_invalid_reply(outcome):
    process, transport = boundary(FakeClient([response(outcome)]))
    process.submit(observation(), sequence=1)
    with pytest.raises(ValueError, match="INFERENCE_REPLY_INVALID"):
        stop = time.monotonic() + 3
        while time.monotonic() < stop:
            process.poll()
            time.sleep(0.002)
    process.close()


def test_an_unreachable_service_or_a_wrong_identity_is_an_invalid_reply():
    for failure in (FileNotFoundError("no socket"), ValueError("POLICY_RESPONSE_IDENTITY_MISMATCH")):
        process, transport = boundary(FakeClient([failure]))
        process.submit(observation(), sequence=1)
        with pytest.raises(ValueError, match="INFERENCE_REPLY_INVALID"):
            stop = time.monotonic() + 3
            while time.monotonic() < stop:
                process.poll()
                time.sleep(0.002)
        process.close()


def test_no_answer_before_the_request_deadline_is_the_boundarys_own_timeout():
    process, transport = boundary(FakeClient([TimeoutError("POLICY_DEADLINE_EXCEEDED")]), request_timeout_s=0.05)
    process.submit(observation(), sequence=1)
    with pytest.raises(ValueError, match="INFERENCE_TIMEOUT"):
        stop = time.monotonic() + 3
        while time.monotonic() < stop:
            process.poll()
            time.sleep(0.002)
    process.abandon()
    process.close()


def test_the_boundary_still_admits_one_request_at_a_time():
    gate = threading.Event()
    process, transport = boundary(FakeClient([lambda sequence: (gate.wait(5), response())[1]]))
    process.submit(observation(), sequence=1)
    with pytest.raises(ValueError, match="INFERENCE_REQUEST_IN_FLIGHT"):
        process.submit(observation(), sequence=2)
    gate.set()
    wait_reply(process)
    process.close()


def test_a_reply_of_an_abandoned_request_is_dropped_by_sequence():
    gate = threading.Event()
    client = FakeClient([lambda sequence: (gate.wait(5), response())[1], response()])
    process, transport = boundary(client)
    process.submit(observation(), sequence=1)
    process.abandon()
    process.submit(observation(), sequence=2)
    gate.set()
    reply = wait_reply(process)
    assert reply["sequence"] == 2
    process.close()


def test_quiesce_waits_for_the_exchange_in_progress():
    gate = threading.Event()
    client = FakeClient([lambda sequence: (gate.wait(5), response())[1]])
    process, transport = boundary(client)
    process.submit(observation(), sequence=1)
    while not client.calls:
        time.sleep(0.001)
    assert transport.quiesce(0.05) is False
    gate.set()
    assert transport.quiesce(2.0) is True
    process.close()


def test_the_transport_closes_its_thread_and_refuses_later_requests():
    process, transport = boundary(FakeClient([]))
    assert transport.close() is True
    with pytest.raises(ValueError, match="INFERENCE_PROCESS_CLOSED"):
        transport.send({"sequence": 1, "observation": observation()})


def test_the_remote_policy_never_infers_and_resets_to_nothing():
    policy = RemotePolicy()
    assert policy.reset() is None
    with pytest.raises(AssertionError):
        policy.infer(observation())


def test_a_boundary_over_the_real_socket_and_service_returns_the_models_chunk(tmp_path):
    rig = Rig(tmp_path)
    try:
        client = PolicyClient(socket_path=rig.socket, client_id="shard0", bundle_sha256=BUNDLE, policy_sha256=POLICY,
                              cameras=("head", "wrist"), max_frame_bytes=1 << 22, service_generation="gen-1")
        process, transport = boundary(client, request_timeout_s=2.0)
        process.submit(observation(stamp=3.0), sequence=9)
        reply = wait_reply(process, 5.0)
        assert reply["sequence"] == 9 and len(reply["actions"]) == 3 and reply["service"]["outcome"] == "OK"
        assert reply["actions"][0][0] == pytest.approx(3.0)
        assert reply["service"]["queue_wait_ms"] is not None and reply["service"]["inference_ms"] is not None
        process.close()
    finally:
        rig.close()
