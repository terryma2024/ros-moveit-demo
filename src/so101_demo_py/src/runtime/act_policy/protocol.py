"""The wire format between a rollout shard and the host's ACT policy service.

Frame layout and bounds are those of `runtime/inference/codec.py` (the Teacher inference service): a 4-byte body size, a 4-byte
header size, a canonical JSON header and a raw payload. The Teacher contract itself is closed on one RGB image and a detection
result, so it cannot carry an ACT observation (state plus one image per camera) or an action chunk; this module therefore adds its
own closed message kinds, over the same framing and the same socket helpers (`open_socket_parent`, `transport_address`):

    policy_request       one observation: sim time, state, and the cameras' images (the payload is their bytes, in order)
    policy_response      the action chunk (or the reason there is none), the bundle identity, the sequence, the observation
                         stamp, and the service's timing for this request (queue wait, inference time)
    policy_ready_query / policy_ready, policy_health_query / policy_health

One request per connection, answered by one response, then the connection is closed (as for the Teacher service).
"""

from __future__ import annotations

import copy
import math
import re
import socket
import struct

from so101_demo.runtime.inference.codec import _receive_exact
from so101_demo.runtime.parallel_ipc.frames import IpcError, _decode_payload, canonical_json

SCHEMA_VERSION = 1
OUTCOMES = frozenset({"OK", "QUEUE_FULL", "QUEUE_TIMEOUT", "INFERENCE_TIMEOUT", "INPUT_INVALID", "MODEL_ERROR", "INFRA_ERROR"})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_NAME = re.compile(r"[a-z][a-z0-9_]{0,31}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
TIMING_FIELDS = ("received_monotonic_ns", "queued_monotonic_ns", "started_monotonic_ns", "completed_monotonic_ns")
MAX_IMAGES = 4
MAX_CHUNK_ROWS = 512
MAX_ACTION_WIDTH = 32
#: a header is metadata (a response with a whole action chunk is the largest); the payload is bounded by the frame limit
MAX_HEADER_BYTES = 1024 * 1024


def _require(condition):
    if not condition:
        raise ValueError("field contract")


def _keys(document, fields):
    _require(type(document) is dict and set(document) == set(fields))


def _int(value, minimum=0):
    _require(type(value) is int and value >= minimum)


def _number(value):
    _require(type(value) in (int, float) and math.isfinite(value))


def _text(value):
    _require(type(value) is str and bool(value) and "\x00" not in value)


def _ident(value):
    _require(type(value) is str and _ID.fullmatch(value) is not None)


def _sha(value):
    _require(type(value) is str and _SHA.fullmatch(value) is not None)


def _limit(value):
    if type(value) is not int or not 4 < value <= 2**32 - 1:
        raise ValueError("POLICY_FRAME_INVALID: limit")


def validate_observation(observation):
    """Closed shape of the observation block; the images are described, never carried."""

    _keys(observation, ("sim_time_s", "state", "images"))
    _number(observation["sim_time_s"])
    state = observation["state"]
    _require(type(state) is list and 0 < len(state) <= 64)
    for value in state:
        _number(value)
    images = observation["images"]
    _require(type(images) is list and 0 < len(images) <= MAX_IMAGES)
    names = set()
    for image in images:
        _keys(image, ("name", "shape", "byte_length"))
        _require(type(image["name"]) is str and _NAME.fullmatch(image["name"]) is not None and image["name"] not in names)
        names.add(image["name"])
        shape = image["shape"]
        _require(type(shape) is list and len(shape) == 3 and shape[2] == 3)
        for item in shape:
            _int(item, 1)
        _require(image["byte_length"] == math.prod(shape))


def validate_request(document):
    try:
        _keys(document, ("schema_version", "kind", "request_id", "client_id", "sequence", "deadline_monotonic_ns",
                         "observation"))
        _require(document["schema_version"] == SCHEMA_VERSION and type(document["schema_version"]) is int
                 and document["kind"] == "policy_request")
        _ident(document["request_id"])
        _ident(document["client_id"])
        _int(document["sequence"])
        _int(document["deadline_monotonic_ns"], 1)
        validate_observation(document["observation"])
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        raise ValueError("POLICY_REQUEST_INVALID") from error
    return copy.deepcopy(document)


def _timing(timing):
    _keys(timing, (*TIMING_FIELDS, "queue_wait_ms", "inference_ms", "inflight_at_receipt"))
    previous = -1
    missing = False
    for name in TIMING_FIELDS:
        value = timing[name]
        if value is None:
            missing = True
        else:
            _int(value)
            _require(not missing and value >= previous)
            previous = value
    for name in ("queue_wait_ms", "inference_ms"):
        if timing[name] is not None:
            _number(timing[name])
            _require(timing[name] >= 0)
    _int(timing["inflight_at_receipt"])


def validate_response(document):
    try:
        _keys(document, ("schema_version", "kind", "request_id", "client_id", "sequence", "observation_sim_s",
                         "service_generation", "bundle_sha256", "policy_sha256", "outcome", "reason", "actions", "timing"))
        _require(document["schema_version"] == SCHEMA_VERSION and type(document["schema_version"]) is int
                 and document["kind"] == "policy_response")
        _ident(document["request_id"])
        _ident(document["client_id"])
        _int(document["sequence"])
        _number(document["observation_sim_s"])
        _text(document["service_generation"])
        _sha(document["bundle_sha256"])
        _sha(document["policy_sha256"])
        _require(type(document["outcome"]) is str and document["outcome"] in OUTCOMES)
        _require(type(document["reason"]) is str)
        _timing(document["timing"])
        actions = document["actions"]
        if document["outcome"] != "OK":
            _require(actions is None)
        else:
            _require(type(actions) is list and 0 < len(actions) <= MAX_CHUNK_ROWS)
            width = len(actions[0]) if type(actions[0]) is list else 0
            _require(0 < width <= MAX_ACTION_WIDTH)
            for row in actions:
                _require(type(row) is list and len(row) == width)
                for value in row:
                    _number(value)
    except (ValueError, KeyError, TypeError, OverflowError, IndexError) as error:
        raise ValueError("POLICY_RESPONSE_INVALID") from error
    return copy.deepcopy(document)


_QUERY_KINDS = ("policy_ready_query", "policy_health_query")
#: outcomes that say the service or the request is wrong; a refusal for load (full, late) is not one of them
ERROR_OUTCOMES = frozenset({"MODEL_ERROR", "INFRA_ERROR", "INPUT_INVALID"})


def validate_query(document):
    try:
        _keys(document, ("schema_version", "kind", "request_id"))
        _require(document["schema_version"] == SCHEMA_VERSION and document["kind"] in _QUERY_KINDS)
        _ident(document["request_id"])
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("POLICY_QUERY_INVALID") from error
    return copy.deepcopy(document)


def validate_service_reply(document):
    try:
        _require(type(document) is dict and type(document.get("kind")) is str)
        common = ("schema_version", "kind", "request_id", "service_generation")
        if document["kind"] == "policy_ready":
            _keys(document, common + ("bundle_sha256", "policy_sha256", "device", "gpu_uuid", "cameras", "state_dim",
                                      "image_shape", "chunk_size", "max_inflight", "pid", "warm_up_s", "ready"))
            _sha(document["bundle_sha256"])
            _sha(document["policy_sha256"])
            _text(document["device"])
            _text(document["gpu_uuid"])
            _require(type(document["cameras"]) is list and all(type(item) is str for item in document["cameras"]))
            _int(document["state_dim"], 1)
            _require(type(document["image_shape"]) is list and len(document["image_shape"]) == 3)
            _int(document["chunk_size"], 1)
            _int(document["max_inflight"], 1)
            _int(document["pid"], 1)
            _require(type(document["warm_up_s"]) is list)
            _require(type(document["ready"]) is bool)
        else:
            _require(document["kind"] == "policy_health")
            _keys(document, common + ("available", "reason", "inflight", "served", "refused", "consecutive_errors"))
            _require(type(document["available"]) is bool and type(document["reason"]) is str)
            for name in ("inflight", "served", "refused", "consecutive_errors"):
                _int(document[name])
        _require(document["schema_version"] == SCHEMA_VERSION)
        _ident(document["request_id"])
        _text(document["service_generation"])
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("POLICY_SERVICE_REPLY_INVALID") from error
    return copy.deepcopy(document)


def validate_message(document):
    if type(document) is not dict:
        raise ValueError("POLICY_MESSAGE_INVALID")
    kind = document.get("kind")
    if kind == "policy_request":
        return validate_request(document)
    if kind == "policy_response":
        return validate_response(document)
    if kind in _QUERY_KINDS:
        return validate_query(document)
    if kind in ("policy_ready", "policy_health"):
        return validate_service_reply(document)
    raise ValueError("POLICY_MESSAGE_INVALID")


def _expected_payload(document):
    if document["kind"] != "policy_request":
        return 0
    return sum(image["byte_length"] for image in document["observation"]["images"])


def encode_frame(document, payload=b"", *, max_frame_bytes):
    _limit(max_frame_bytes)
    try:
        document = validate_message(document)
        if type(payload) is not bytes or len(payload) != _expected_payload(document):
            raise ValueError("payload")
        header = canonical_json(document)
    except (ValueError, IpcError) as error:
        raise ValueError("POLICY_FRAME_INVALID: header or payload") from error
    size = 4 + len(header) + len(payload)
    if size > max_frame_bytes:
        raise ValueError("POLICY_FRAME_INVALID: body size")
    return struct.pack(">II", size, len(header)) + header + payload


def decode_frame(frame, *, max_frame_bytes):
    _limit(max_frame_bytes)
    if type(frame) is not bytes or len(frame) < 8:
        raise ValueError("POLICY_FRAME_INVALID: incomplete")
    body, header_size = struct.unpack(">II", frame[:8])
    if not 4 < body <= max_frame_bytes or len(frame) != body + 4 or not 0 < header_size <= body - 4:
        raise ValueError("POLICY_FRAME_INVALID: lengths")
    try:
        document = validate_message(_decode_payload(frame[8:8 + header_size]))
        payload = frame[8 + header_size:]
        if len(payload) != _expected_payload(document):
            raise ValueError("payload")
    except (ValueError, IpcError) as error:
        raise ValueError("POLICY_FRAME_INVALID: header or payload") from error
    return document, payload


def receive_header(connection, *, deadline_monotonic_ns, max_frame_bytes, max_header_bytes=MAX_HEADER_BYTES):
    """Read and validate the bounded metadata of one frame; never read or allocate the payload here.

    Returns `(document, payload_size)`. A caller that has no slot for the payload answers from the header alone."""
    _limit(max_frame_bytes)
    if type(deadline_monotonic_ns) is not int or deadline_monotonic_ns <= 0:
        raise ValueError("POLICY_FRAME_INVALID: deadline")
    size = struct.unpack(">I", _receive_exact(connection, 4, deadline_monotonic_ns))[0]
    if not 4 < size <= max_frame_bytes:
        raise ValueError("POLICY_FRAME_INVALID: body size")
    header_size = struct.unpack(">I", _receive_exact(connection, 4, deadline_monotonic_ns))[0]
    if not 0 < header_size <= min(size - 4, max_header_bytes):
        raise ValueError("POLICY_FRAME_INVALID: header size")
    header = _receive_exact(connection, header_size, deadline_monotonic_ns)
    try:
        document = validate_message(_decode_payload(header))
    except (ValueError, IpcError) as error:
        raise ValueError("POLICY_FRAME_INVALID: header") from error
    payload_size = size - 4 - header_size
    if payload_size != _expected_payload(document):
        raise ValueError("POLICY_FRAME_INVALID: payload size")
    return document, payload_size


def receive_frame(connection, *, deadline_monotonic_ns, max_frame_bytes):
    """The caller holds an in-flight slot before it enters this bounded read of the payload."""
    document, payload_size = receive_header(connection, deadline_monotonic_ns=deadline_monotonic_ns,
                                            max_frame_bytes=max_frame_bytes)
    payload = _receive_exact(connection, payload_size, deadline_monotonic_ns) if payload_size else b""
    previous_timeout = connection.gettimeout()
    try:
        connection.setblocking(False)
        try:
            extra = connection.recv(1, socket.MSG_PEEK)
        except (BlockingIOError, ConnectionResetError):
            extra = b""
    finally:
        connection.settimeout(previous_timeout)
    if extra:
        raise ValueError("POLICY_FRAME_INVALID: overlong")
    return document, payload


def encode_frame_parts(document, payloads, *, max_frame_bytes):
    """The frame of `encode_frame` as `(head, buffers)`: the two size words and the header in `head`, the payload left in place.

    The bytes on the wire are identical to `encode_frame(document, b"".join(payloads))`; the images are not copied to build it."""
    _limit(max_frame_bytes)
    try:
        document = validate_message(document)
        views = [memoryview(item).cast("B") if memoryview(item).format != "B" or memoryview(item).ndim != 1 else memoryview(item)
                 for item in payloads]
        if sum(len(view) for view in views) != _expected_payload(document):
            raise ValueError("payload")
        header = canonical_json(document)
    except (ValueError, TypeError, IpcError) as error:
        raise ValueError("POLICY_FRAME_INVALID: header or payload") from error
    size = 4 + len(header) + sum(len(view) for view in views)
    if size > max_frame_bytes:
        raise ValueError("POLICY_FRAME_INVALID: body size")
    return struct.pack(">II", size, len(header)) + header, views


def send_frame_parts(connection, head, buffers):
    """Send `head` and then every buffer with `sendmsg`, without joining them; handles a partial send."""
    pending = [memoryview(head)] + [view for view in buffers if len(view)]
    while pending:
        sent = connection.sendmsg(pending)
        while sent:
            first = pending[0]
            if sent >= len(first):
                sent -= len(first)
                pending.pop(0)
            else:
                pending[0] = first[sent:]
                sent = 0


def pack_observation_views(observation, *, cameras):
    """`(description, buffers)` like `pack_observation`, with the images' own memory as the buffers (no copy of a contiguous array)."""
    import numpy as np

    images, buffers = [], []
    for name in cameras:
        array = observation[name]
        if (not isinstance(array, np.ndarray) or array.dtype != np.uint8 or array.ndim != 3 or array.shape[2] != 3
                or min(array.shape) <= 0):
            raise ValueError("POLICY_OBSERVATION_IMAGE_INVALID")
        array = np.ascontiguousarray(array)          # a no-op for a contiguous array
        images.append({"name": name, "shape": list(array.shape), "byte_length": int(array.size)})
        buffers.append(memoryview(array).cast("B"))
    return ({"sim_time_s": float(observation["sim_time_s"]), "state": [float(value) for value in observation["state"]],
             "images": images}, buffers)


def pack_observation(observation, *, cameras):
    """`(description, payload)` of a runtime observation `{sim_time_s, state, <camera>: HxWx3 uint8}` in `cameras` order."""
    import numpy as np

    images, chunks = [], []
    for name in cameras:
        array = observation[name]
        if (not isinstance(array, np.ndarray) or array.dtype != np.uint8 or array.ndim != 3 or array.shape[2] != 3
                or min(array.shape) <= 0):
            raise ValueError("POLICY_OBSERVATION_IMAGE_INVALID")
        data = np.ascontiguousarray(array).tobytes(order="C")
        images.append({"name": name, "shape": list(array.shape), "byte_length": len(data)})
        chunks.append(data)
    description = {"sim_time_s": float(observation["sim_time_s"]), "state": [float(value) for value in observation["state"]],
                   "images": images}
    return description, b"".join(chunks)


def unpack_observation(description, payload):
    """The runtime observation a model call takes, from a validated description and its payload."""
    import numpy as np

    observation = {"sim_time_s": description["sim_time_s"], "state": list(description["state"])}
    offset = 0
    for image in description["images"]:
        height, width, _ = image["shape"]
        end = offset + image["byte_length"]
        observation[image["name"]] = np.frombuffer(bytearray(payload[offset:end]), dtype=np.uint8).reshape(height, width, 3)
        offset = end
    if offset != len(payload):
        raise ValueError("POLICY_FRAME_INVALID: payload length")
    return observation
