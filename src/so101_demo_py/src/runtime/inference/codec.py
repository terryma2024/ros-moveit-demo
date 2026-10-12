"""Bounded canonical JSON header plus unchanged, row-major RGB8 bytes."""

from __future__ import annotations

import socket
import struct
import time

import numpy as np

from so101_demo.runtime.inference.contract import validate_image, validate_message
from so101_demo.runtime.parallel_ipc.frames import IpcError, _decode_payload, canonical_json


def _limit(value):
    if type(value) is not int or not 4 < value <= 2**32 - 1:
        raise ValueError("INFERENCE_FRAME_INVALID: limit")


def _payload(document, payload):
    if type(payload) is not bytes:
        raise ValueError("INFERENCE_FRAME_INVALID: payload type")
    expected = document["image"]["byte_length"] if document["kind"] == "inference_request" else 0
    if len(payload) != expected:
        raise ValueError("INFERENCE_FRAME_INVALID: payload length")


def encode_inference_frame(document, payload, *, max_frame_bytes):
    _limit(max_frame_bytes)
    try:
        document = validate_message(document)
        _payload(document, payload)
        header = canonical_json(document)
    except (ValueError, IpcError) as error:
        raise ValueError("INFERENCE_FRAME_INVALID: header or payload") from error
    size = 4 + len(header) + len(payload)
    if size > max_frame_bytes:
        raise ValueError("INFERENCE_FRAME_INVALID: body size")
    return struct.pack(">II", size, len(header)) + header + payload


def decode_inference_frame(frame, *, max_frame_bytes):
    _limit(max_frame_bytes)
    if type(frame) is not bytes or len(frame) < 8:
        raise ValueError("INFERENCE_FRAME_INVALID: incomplete")
    body, header_size = struct.unpack(">II", frame[:8])
    if not 4 < body <= max_frame_bytes or len(frame) != body + 4 or not 0 < header_size <= body - 4:
        raise ValueError("INFERENCE_FRAME_INVALID: lengths")
    try:
        document = validate_message(_decode_payload(frame[8:8 + header_size]))
        payload = frame[8 + header_size:]
        _payload(document, payload)
    except (ValueError, IpcError) as error:
        raise ValueError("INFERENCE_FRAME_INVALID: header or payload") from error
    return document, payload


def _receive_exact(connection, size, deadline_monotonic_ns):
    buffer = bytearray()
    while len(buffer) < size:
        remaining = (deadline_monotonic_ns - time.monotonic_ns()) / 1e9
        if remaining <= 0:
            raise TimeoutError("INFERENCE_DEADLINE_EXCEEDED")
        connection.settimeout(remaining)
        part = connection.recv(size - len(buffer))
        if not part:
            raise ValueError("INFERENCE_FRAME_INVALID: truncated")
        buffer.extend(part)
    return bytes(buffer)


def receive_inference_frame(connection, *, deadline_monotonic_ns, max_frame_bytes):
    """Caller reserves an inflight slot before entering this bounded read."""
    _limit(max_frame_bytes)
    if type(deadline_monotonic_ns) is not int or deadline_monotonic_ns <= 0:
        raise ValueError("INFERENCE_FRAME_INVALID: deadline")
    prefix = _receive_exact(connection, 4, deadline_monotonic_ns)
    size = struct.unpack(">I", prefix)[0]
    if not 4 < size <= max_frame_bytes:
        raise ValueError("INFERENCE_FRAME_INVALID: body size")
    # Decode and validate metadata before reading/allocating the declared RGB payload.
    header_prefix = _receive_exact(connection, 4, deadline_monotonic_ns)
    header_size = struct.unpack(">I", header_prefix)[0]
    if not 0 < header_size <= size - 4:
        raise ValueError("INFERENCE_FRAME_INVALID: header size")
    header = _receive_exact(connection, header_size, deadline_monotonic_ns)
    try:
        document = validate_message(_decode_payload(header))
    except (ValueError, IpcError) as error:
        raise ValueError("INFERENCE_FRAME_INVALID: header") from error
    payload_size = size - 4 - header_size
    expected = document["image"]["byte_length"] if document["kind"] == "inference_request" else 0
    if payload_size != expected:
        raise ValueError("INFERENCE_FRAME_INVALID: payload size")
    payload = _receive_exact(connection, payload_size, deadline_monotonic_ns)
    # Python's positive timeout polls before recv even with MSG_DONTWAIT.
    # The frame is complete; checking trailing bytes must not await peer EOF.
    previous_timeout = connection.gettimeout()
    try:
        connection.setblocking(False)
        try:
            extra = connection.recv(1, socket.MSG_PEEK)
        except BlockingIOError:
            extra = b""
    finally:
        connection.settimeout(previous_timeout)
    if extra:
        raise ValueError("INFERENCE_FRAME_INVALID: overlong")
    return document, payload


def pack_rgb(rgb, *, stamp_ns, frame_id):
    if (not isinstance(rgb, np.ndarray) or rgb.dtype != np.uint8 or rgb.ndim != 3
            or rgb.shape[2] != 3 or not rgb.flags.c_contiguous or min(rgb.shape) <= 0):
        raise ValueError("RGB_INVALID: contiguous uint8 HxWx3 required")
    image = {"format": "RGB8", "shape": list(rgb.shape), "byte_length": int(rgb.size),
             "source_stamp_ns": stamp_ns, "source_frame_id": frame_id}
    try:
        validate_image(image)
    except ValueError as error:
        raise ValueError("RGB_INVALID: metadata") from error
    return image, rgb.tobytes(order="C")


def unpack_rgb(image, payload, *, limits):
    try:
        validate_image(image)
        height, width, _ = image["shape"]
        for key, actual in (("max_image_height", height), ("max_image_width", width)):
            maximum = limits[key]
            if type(maximum) is not int or maximum <= 0 or actual > maximum:
                raise ValueError("shape limit")
        if type(payload) is not bytes or len(payload) != image["byte_length"]:
            raise ValueError("payload length")
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("RGB_INVALID") from error
    return np.frombuffer(payload, dtype=np.uint8).reshape(height, width, 3)
