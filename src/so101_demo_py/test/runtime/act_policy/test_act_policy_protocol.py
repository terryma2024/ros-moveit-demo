"""The policy service's wire format: closed messages over the Teacher codec's framing (no service, no model, no GPU)."""

import socket

import numpy as np
import pytest

from so101_demo.runtime.act_policy import protocol

SHA = "a" * 64
LIMIT = 8 * 1024 * 1024


def image(name="head", shape=(4, 6, 3)):
    return {"name": name, "shape": list(shape), "byte_length": int(np.prod(shape))}


def request(**changes):
    document = {"schema_version": 1, "kind": "policy_request", "request_id": "c0-r1", "client_id": "c0", "sequence": 3,
                "deadline_monotonic_ns": 10**12,
                "observation": {"sim_time_s": 1.5, "state": [0.0] * 8, "images": [image("head"), image("wrist")]}}
    document.update(changes)
    return document


def timing(**changes):
    document = {"received_monotonic_ns": 5, "queued_monotonic_ns": 6, "started_monotonic_ns": 7, "completed_monotonic_ns": 9,
                "queue_wait_ms": 0.001, "inference_ms": 0.002, "inflight_at_receipt": 2}
    document.update(changes)
    return document


def response(**changes):
    document = {"schema_version": 1, "kind": "policy_response", "request_id": "c0-r1", "client_id": "c0", "sequence": 3,
                "observation_sim_s": 1.5, "service_generation": "g1", "bundle_sha256": SHA, "policy_sha256": "b" * 64,
                "outcome": "OK", "reason": "", "actions": [[0.0] * 6, [0.1] * 6], "timing": timing()}
    document.update(changes)
    return document


def test_a_request_round_trips_with_its_image_bytes():
    payload = bytes(range(72)) + bytes(range(72))
    frame = protocol.encode_frame(request(), payload, max_frame_bytes=LIMIT)
    document, received = protocol.decode_frame(frame, max_frame_bytes=LIMIT)
    assert document == request() and received == payload


def test_a_response_carries_identity_sequence_stamp_and_timing():
    frame = protocol.encode_frame(response(), b"", max_frame_bytes=LIMIT)
    document, payload = protocol.decode_frame(frame, max_frame_bytes=LIMIT)
    assert payload == b"" and document["bundle_sha256"] == SHA and document["sequence"] == 3
    assert document["observation_sim_s"] == 1.5 and document["timing"]["queue_wait_ms"] == 0.001
    assert document["timing"]["inference_ms"] == 0.002


@pytest.mark.parametrize("changes", [
    {"kind": "inference_request"}, {"extra": 1}, {"sequence": -1}, {"sequence": True}, {"request_id": ""},
    {"client_id": "bad id"}, {"deadline_monotonic_ns": 0},
    {"observation": {"sim_time_s": float("nan"), "state": [0.0], "images": [image()]}},
    {"observation": {"sim_time_s": 1.0, "state": [], "images": [image()]}},
    {"observation": {"sim_time_s": 1.0, "state": [0.0], "images": []}},
    {"observation": {"sim_time_s": 1.0, "state": [0.0], "images": [image("Head")]}},
    {"observation": {"sim_time_s": 1.0, "state": [0.0], "images": [image("head"), image("head")]}},
    {"observation": {"sim_time_s": 1.0, "state": [0.0], "images": [dict(image(), byte_length=5)]}},
    {"observation": {"sim_time_s": 1.0, "state": [0.0], "images": [dict(image(), shape=[4, 6, 1])]}},
])
def test_a_malformed_request_is_refused(changes):
    with pytest.raises(ValueError, match="POLICY_(REQUEST|MESSAGE)_INVALID"):
        protocol.validate_message(request(**changes))


@pytest.mark.parametrize("changes", [
    {"outcome": "OK", "actions": None}, {"outcome": "QUEUE_FULL", "actions": [[0.0]]}, {"outcome": "SURPRISE", "actions": None},
    {"actions": [[0.0] * 6, [0.0] * 5]}, {"actions": []}, {"bundle_sha256": "xyz"}, {"timing": timing(started_monotonic_ns=None)},
    {"timing": timing(completed_monotonic_ns=1)}, {"timing": timing(inference_ms=-1.0)}, {"observation_sim_s": float("inf")},
])
def test_a_malformed_response_is_refused(changes):
    with pytest.raises(ValueError, match="POLICY_RESPONSE_INVALID"):
        protocol.validate_message(response(**changes))


def test_a_refusal_has_no_actions_and_may_have_no_timing_beyond_receipt():
    refusal = response(outcome="QUEUE_FULL", reason="MAX_INFLIGHT_REQUESTS", actions=None,
                       timing=timing(queued_monotonic_ns=None, started_monotonic_ns=None, completed_monotonic_ns=None,
                                     queue_wait_ms=None, inference_ms=None))
    assert protocol.validate_message(refusal)["outcome"] == "QUEUE_FULL"


def test_the_frame_bounds_and_the_payload_length_are_enforced():
    payload = bytes(144)
    with pytest.raises(ValueError, match="POLICY_FRAME_INVALID"):
        protocol.encode_frame(request(), payload[:-1], max_frame_bytes=LIMIT)
    with pytest.raises(ValueError, match="POLICY_FRAME_INVALID"):
        protocol.encode_frame(request(), payload, max_frame_bytes=100)
    frame = protocol.encode_frame(request(), payload, max_frame_bytes=LIMIT)
    with pytest.raises(ValueError, match="POLICY_FRAME_INVALID"):
        protocol.decode_frame(frame + b"x", max_frame_bytes=LIMIT)
    with pytest.raises(ValueError, match="POLICY_FRAME_INVALID"):
        protocol.decode_frame(frame[:-1], max_frame_bytes=LIMIT)


def test_queries_and_service_replies_are_closed_kinds():
    query = {"schema_version": 1, "kind": "policy_ready_query", "request_id": "q1"}
    assert protocol.decode_frame(protocol.encode_frame(query, b"", max_frame_bytes=LIMIT), max_frame_bytes=LIMIT)[0] == query
    health = {"schema_version": 1, "kind": "policy_health", "request_id": "q2", "service_generation": "g1",
              "available": True, "reason": "", "inflight": 0, "served": 4, "refused": 1}
    assert protocol.validate_message(health) == health
    with pytest.raises(ValueError, match="POLICY_SERVICE_REPLY_INVALID"):
        protocol.validate_message(dict(health, extra=1))
    with pytest.raises(ValueError, match="POLICY_QUERY_INVALID"):
        protocol.validate_message(dict(query, kind="policy_health_query", extra=1))


def test_an_observation_packs_in_camera_order_and_unpacks_to_the_same_arrays():
    head = np.arange(72, dtype=np.uint8).reshape(4, 6, 3)
    wrist = (np.arange(72, dtype=np.uint8)[::-1]).reshape(4, 6, 3).copy()
    description, payload = protocol.pack_observation({"sim_time_s": 2, "state": [1, 2.5], "head": head, "wrist": wrist},
                                                     cameras=("wrist", "head"))
    assert [item["name"] for item in description["images"]] == ["wrist", "head"]
    assert description["sim_time_s"] == 2.0 and description["state"] == [1.0, 2.5]
    unpacked = protocol.unpack_observation(description, payload)
    assert np.array_equal(unpacked["head"], head) and np.array_equal(unpacked["wrist"], wrist)
    assert unpacked["head"].flags.writeable
    with pytest.raises(ValueError, match="POLICY_OBSERVATION_IMAGE_INVALID"):
        protocol.pack_observation({"sim_time_s": 0, "state": [0], "head": head.astype(np.float32)}, cameras=("head",))
    with pytest.raises(ValueError, match="payload length"):
        protocol.unpack_observation(description, payload + b"x")


def test_the_header_is_read_and_judged_without_reading_the_payload():
    left, right = socket.socketpair()
    try:
        frame = protocol.encode_frame(request(), bytes(144), max_frame_bytes=LIMIT)
        header_end = len(frame) - 144
        right.sendall(frame[:header_end])           # the payload has not arrived
        import time
        document, size = protocol.receive_header(left, deadline_monotonic_ns=time.monotonic_ns() + 2 * 10**9,
                                                 max_frame_bytes=LIMIT)
        assert document["sequence"] == 3 and size == 144
    finally:
        left.close()
        right.close()


def test_an_oversize_header_declaration_is_refused_before_it_is_buffered():
    import struct
    import time

    left, right = socket.socketpair()
    try:
        right.sendall(struct.pack(">II", 4 + 2_000_000, 2_000_000))
        with pytest.raises(ValueError, match="POLICY_FRAME_INVALID: header size"):
            protocol.receive_header(left, deadline_monotonic_ns=time.monotonic_ns() + 10**9, max_frame_bytes=16 * 1024 * 1024)
    finally:
        left.close()
        right.close()
