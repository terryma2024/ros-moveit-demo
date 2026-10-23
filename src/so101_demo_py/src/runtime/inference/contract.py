"""One closed ACT inference format, independent of scheduling authority."""

from __future__ import annotations

import copy
import math
import re


OUTCOMES = frozenset({"DETECTED", "NOT_DETECTED", "INPUT_INVALID", "QUEUE_FULL",
                      "QUEUE_TIMEOUT", "INFERENCE_TIMEOUT", "MODEL_ERROR", "INFRA_ERROR"})
_SHA = re.compile(r"[0-9a-f]{64}\Z")
_CLASS = re.compile(r"[a-z][a-z0-9_]*\Z")
_TIMING = ("received_monotonic_ns", "queued_monotonic_ns",
           "started_monotonic_ns", "completed_monotonic_ns")


def _require(condition):
    if not condition:
        raise ValueError("field contract")


def _keys(document, fields):
    _require(type(document) is dict and set(document) == set(fields))


def _text(value):
    _require(type(value) is str and bool(value) and "\x00" not in value)


def _integer(value, minimum=1):
    _require(type(value) is int and value >= minimum)


def _number(value, minimum=0, maximum=None):
    _require(type(value) in (float, int) and math.isfinite(value) and value >= minimum
             and (maximum is None or value <= maximum))


def _sha(value):
    _require(type(value) is str and _SHA.fullmatch(value) is not None)


def _shape(value, channels=True):
    _require(type(value) is list and len(value) == (3 if channels else 2))
    for item in value:
        _integer(item)
    if channels:
        _require(value[2] == 3)


def _common(document, kind):
    _require(type(document["schema_version"]) is int and document["schema_version"] == 1)
    _require(document["kind"] == kind)
    _text(document["request_id"])


def validate_image(image):
    """Validate metadata without allocating a pixel array."""
    try:
        _keys(image, ("format", "byte_length", "shape", "source_stamp_ns", "source_frame_id"))
        _require(image["format"] == "RGB8")
        _shape(image["shape"])
        _integer(image["byte_length"])
        _require(image["byte_length"] == math.prod(image["shape"]))
        _integer(image["source_stamp_ns"])
        _text(image["source_frame_id"])
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        raise ValueError("INFERENCE_REQUEST_INVALID: image") from error
    return copy.deepcopy(image)


def validate_inference_request(document):
    try:
        _keys(document, ("schema_version", "kind", "request_id", "image",
                         "query_class_id", "deadline_monotonic_ns"))
        _common(document, "inference_request")
        validate_image(document["image"])
        _require(type(document["query_class_id"]) is str
                 and _CLASS.fullmatch(document["query_class_id"]) is not None)
        _integer(document["deadline_monotonic_ns"])
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        raise ValueError("INFERENCE_REQUEST_INVALID") from error
    return copy.deepcopy(document)


def _candidate(candidate, shape):
    _keys(candidate, ("instance_id", "class_id", "confidence", "bbox_xyxy",
                      "segmentation_quality", "mask_rle"))
    _text(candidate["instance_id"])
    _require(type(candidate["class_id"]) is str
             and _CLASS.fullmatch(candidate["class_id"]) is not None)
    _number(candidate["confidence"], maximum=1)
    if candidate["segmentation_quality"] is not None:
        _number(candidate["segmentation_quality"], maximum=1)
    box = candidate["bbox_xyxy"]
    _require(type(box) is list and len(box) == 4)
    for value in box:
        _number(value)
    _require(0 <= box[0] < box[2] <= shape[1] and 0 <= box[1] < box[3] <= shape[0])
    rle = candidate["mask_rle"]
    _keys(rle, ("shape", "counts"))
    _shape(rle["shape"], channels=False)
    _require(rle["shape"] == shape[:2])
    counts = rle["counts"]
    _require(type(counts) is list and bool(counts))
    for index, count in enumerate(counts):
        _integer(count, minimum=0 if index == 0 else 1)
    _require(sum(counts) == shape[0] * shape[1] and sum(counts[1::2]) > 0)


def validate_inference_response(document):
    try:
        _keys(document, ("schema_version", "kind", "request_id", "service_generation",
                         "source_stamp_ns", "source_frame_id", "outcome", "reason", "batch", "timing"))
        _common(document, "inference_response")
        _text(document["service_generation"])
        _integer(document["source_stamp_ns"])
        _text(document["source_frame_id"])
        _require(type(document["outcome"]) is str and document["outcome"] in OUTCOMES)
        _require(type(document["reason"]) is str)
        _keys(document["timing"], _TIMING)
        previous = -1
        missing = False
        for name in _TIMING:
            value = document["timing"][name]
            if value is None:
                missing = True
            else:
                _integer(value, minimum=0)
                _require(not missing and value >= previous)
                previous = value
        batch = document["batch"]
        if document["outcome"] != "DETECTED":
            _require(batch is None)
        else:
            _keys(batch, ("model_id", "weights_sha256", "runtime_device", "inference_latency_ms",
                          "shape", "source_stamp_ns", "source_frame_id", "candidates"))
            _text(batch["model_id"])
            _sha(batch["weights_sha256"])
            _require(batch["runtime_device"] == "cuda")
            _number(batch["inference_latency_ms"])
            _shape(batch["shape"])
            _integer(batch["source_stamp_ns"])
            _require(batch["source_stamp_ns"] == document["source_stamp_ns"]
                     and batch["source_frame_id"] == document["source_frame_id"])
            _require(type(batch["candidates"]) is list and bool(batch["candidates"]))
            identifiers = set()
            for candidate in batch["candidates"]:
                _candidate(candidate, batch["shape"])
                _require(candidate["instance_id"] not in identifiers)
                identifiers.add(candidate["instance_id"])
    except (ValueError, KeyError, TypeError, OverflowError) as error:
        raise ValueError("INFERENCE_RESPONSE_INVALID") from error
    return copy.deepcopy(document)


def validate_service_query(document):
    try:
        _keys(document, ("schema_version", "kind", "request_id"))
        _require(document["kind"] in ("service_ready", "service_health"))
        _common(document, document["kind"])
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("SERVICE_QUERY_INVALID") from error
    return copy.deepcopy(document)


def validate_service_response(document):
    try:
        _require(type(document) is dict)
        common = ("schema_version", "kind", "request_id", "service_generation")
        if document["kind"] == "service_ready":
            _keys(document, common + ("image_digest", "package_source_sha256", "model_id",
                "weights_sha256", "service_config_sha256", "gpu_uuid", "configured_instances",
                "loaded_instances", "ready"))
            _text(document["image_digest"])
            _require(document["image_digest"].startswith("sha256:"))
            _sha(document["image_digest"][7:])
            for key in ("package_source_sha256", "weights_sha256", "service_config_sha256"):
                _sha(document[key])
            _text(document["model_id"])
            _text(document["gpu_uuid"])
            _integer(document["configured_instances"])
            _integer(document["loaded_instances"], minimum=0)
            _require(document["loaded_instances"] <= document["configured_instances"])
            _require(type(document["ready"]) is bool)
            _require(not document["ready"] or document["configured_instances"] == document["loaded_instances"])
        else:
            _require(document["kind"] == "service_health")
            _keys(document, common + ("available", "reason"))
            _require(type(document["available"]) is bool and type(document["reason"]) is str)
        _common(document, document["kind"])
        _text(document["service_generation"])
    except (ValueError, KeyError, TypeError) as error:
        raise ValueError("SERVICE_RESPONSE_INVALID") from error
    return copy.deepcopy(document)


def validate_message(document):
    """Route the four message kinds without legacy formats or authority fields."""
    if type(document) is not dict:
        raise ValueError("INFERENCE_MESSAGE_INVALID")
    kind = document.get("kind")
    if kind == "inference_request":
        return validate_inference_request(document)
    if kind == "inference_response":
        return validate_inference_response(document)
    if kind in ("service_ready", "service_health"):
        if "service_generation" in document:
            return validate_service_response(document)
        return validate_service_query(document)
    raise ValueError("INFERENCE_MESSAGE_INVALID")
