"""Catch channel changes, unbounded reads, and malformed binary RGB framing."""

import importlib
import socket
import struct
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from test_contract import request_document


def codec():
    return importlib.import_module("so101_demo.runtime.inference.codec")


def test_rgb_bytes_stamp_and_channels_survive_roundtrip():
    rgb = np.arange(18, dtype=np.uint8).reshape(2, 3, 3)
    image, payload = codec().pack_rgb(rgb, stamp_ns=7, frame_id="head")
    assert payload == bytes(range(18))
    assert image == request_document()["image"]
    frame = codec().encode_inference_frame(request_document(), payload, max_frame_bytes=4096)
    body, header = struct.unpack(">II", frame[:8])
    assert body == len(frame) - 4
    assert frame[8 + header:] == bytes(range(18))
    document, decoded = codec().decode_inference_frame(frame, max_frame_bytes=4096)
    assert document == request_document()
    result = codec().unpack_rgb(image, decoded, limits={"max_image_height": 2, "max_image_width": 3})
    np.testing.assert_array_equal(result, rgb)


def test_camera_rgb_has_exact_921600_byte_payload():
    _, payload = codec().pack_rgb(np.zeros((480, 640, 3), np.uint8), stamp_ns=7, frame_id="head")
    assert len(payload) == 921600


@pytest.mark.parametrize("rgb", [np.zeros((2, 3, 3), np.float32), np.zeros((2, 3, 4), np.uint8),
    np.zeros((0, 3, 3), np.uint8), np.zeros((2, 6, 3), np.uint8)[:, ::2, :]])
def test_pack_rejects_non_rgb8_and_noncontiguous_input(rgb):
    with pytest.raises(ValueError, match="RGB_INVALID"):
        codec().pack_rgb(rgb, stamp_ns=7, frame_id="head")


@pytest.mark.parametrize("mutation", ["truncated", "extra", "header_zero", "header_overflow", "body_overflow"])
def test_decode_rejects_bad_envelope(mutation):
    frame = codec().encode_inference_frame(request_document(), bytes(range(18)), max_frame_bytes=4096)
    if mutation == "truncated": frame = frame[:-1]
    elif mutation == "extra": frame += b"x"
    elif mutation == "header_zero": frame = frame[:4] + struct.pack(">I", 0) + frame[8:]
    elif mutation == "header_overflow": frame = frame[:4] + struct.pack(">I", 4096) + frame[8:]
    elif mutation == "body_overflow": frame = struct.pack(">I", 4097) + frame[4:]
    with pytest.raises(ValueError, match="INFERENCE_FRAME_INVALID"):
        codec().decode_inference_frame(frame, max_frame_bytes=4096)


@pytest.mark.parametrize("header", [b'{"kind":"service_health","request_id":"q","schema_version":1,"schema_version":1}',
    b'{"kind":"service_health","request_id":"q","schema_version":NaN}',
    b'{ "kind": "service_health", "request_id": "q", "schema_version": 1 }'])
def test_header_rejects_duplicate_nonfinite_and_noncanonical_json(header):
    frame = struct.pack(">II", len(header) + 4, len(header)) + header
    with pytest.raises(ValueError, match="INFERENCE_FRAME_INVALID"):
        codec().decode_inference_frame(frame, max_frame_bytes=4096)


@pytest.mark.parametrize("payload", [b"", bytes(17), bytes(19)])
def test_request_rejects_wrong_payload_length(payload):
    with pytest.raises(ValueError, match="INFERENCE_FRAME_INVALID"):
        codec().encode_inference_frame(request_document(), payload, max_frame_bytes=4096)


def test_queries_cannot_carry_payload():
    query = {"schema_version": 1, "kind": "service_health", "request_id": "q"}
    with pytest.raises(ValueError, match="INFERENCE_FRAME_INVALID"):
        codec().encode_inference_frame(query, b"x", max_frame_bytes=4096)


def test_shape_limit_is_enforced_before_numpy_decode():
    with pytest.raises(ValueError, match="RGB_INVALID"):
        codec().unpack_rgb(request_document()["image"], bytes(18),
                           limits={"max_image_height": 1, "max_image_width": 3})


def test_oversize_prefix_does_not_read_declared_body():
    class PrefixOnly:
        def settimeout(self, value): pass
        def recv(self, size):
            assert size == 4
            return struct.pack(">I", 2**32 - 1)
    with pytest.raises(ValueError, match="INFERENCE_FRAME_INVALID"):
        codec().receive_inference_frame(PrefixOnly(), deadline_monotonic_ns=2**63,
                                       max_frame_bytes=4096)


def test_unix_frame_read_does_not_wait_for_peer_disconnect():
    query = {"schema_version": 1, "kind": "service_health", "request_id": "q"}
    frame = codec().encode_inference_frame(query, b"", max_frame_bytes=4096)
    sender, receiver = socket.socketpair()
    with sender, receiver, ThreadPoolExecutor(max_workers=1) as pool:
        sender.sendall(frame)
        future = pool.submit(codec().receive_inference_frame, receiver,
            deadline_monotonic_ns=time.monotonic_ns() + 10_000_000_000, max_frame_bytes=4096)
        try:
            assert future.result(timeout=2) == (query, b"")
        finally:
            sender.shutdown(socket.SHUT_WR)
